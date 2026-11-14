# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The joint loop: place, route, read what routing says, repair locally, keep what is better.

    loop = JointLoop(stages, opts)
    report = loop.run(output, time_s=900, seed=0)

Iteration 0 is the staged pipeline: place, module stage, bridge, evaluate (KiCad DRC and the
routed-physics recheck). Every later iteration:

1. **Feedback.** Unrouted connections, error-level DRC violations and modules the recheck
   flags become spots (feedback); unrouted corridors also add to the congestion history,
   which persists across iterations whatever their outcome (PathFinder's history cost).
2. **Window.** Spots are clustered into windows (feedback.plan_windows); the first window
   that is not exhausted is repaired. A window that was tried and rejected is retried up to
   `max_attempts` times (by default more with a longer budget), larger (margin x1.5, twice
   at most) and with the congestion weight x1.5; an accepted window resets the count, since
   the board changed (annealed coupling). When every window is exhausted, a new cycle samples
   them again under new seeds, until `patience_cycles` cycles in a row accept nothing
   (stop "no improvement (cycle k)").
3. **Repair.** stages.repair: re-place the window's parts, rip up the nets touching it, redo
   its modules, re-route with everything else locked.
4. **Judge.** scorecard.accept against the incumbent: legality, completion and DRC must not
   get worse, routed physics must not get worse, and something must get better. Otherwise
   the incumbent stays (revert).

Stops when the board is clean with nothing flagged, no window is left, `max_iters` (if set)
is reached, or the time left (minus a reserve for the final write and DRC) is below what an
iteration has been taking. Seeds of every stage derive from the run's seed and the
iteration number, and windows are ordered deterministically, so the same seed gives the
same result whenever no time budget binds (a time-bound stage stops at the clock).
"""
from __future__ import annotations

from kae.budget import now as clock_now
import time

from .feedback import CongestionHistory, error_spots, physics_spots, plan_windows, unrouted_spots
from .scorecard import accept

DEFAULTS = dict(
    max_iters=None,        # repair iterations at most (None: as many as the time allows)
    max_attempts=None,     # tries of one window (each larger, with a higher congestion weight);
                           # None: 2 + one per 30 min of budget (900 s: 2, 3600 s: 4, 9000 s: 7)
    margin=2.0,            # mm around a spot's parts (window_for_spot)
    max_parts=6,           # movable parts per window
    max_part_share=0.35,   # ... and at most this share of the board's movable parts (at least 3)
    max_pins=12,           # first attempt: parts with more connected pads stay fixed (None: any part)
    history_amount=1.0,    # history added per failed connection's corridor bin (utilization units)
    place_share=0.30,      # share of the budget for the placer
    route_share=0.6,       # share of what is left after placing and the module stage, for the first route
    reserve=25.0,          # seconds kept for the final write and DRC (at least 4 % of the budget)
    physics_spots=True,    # flagged modules make windows too
    min_iter_s=60.0,       # an iteration is not started with less than this left
    iter_share=0.25,       # one window's repair gets at most this share of the budget (at least min_iter_s)
    window_budget_factor=0.0,  # extra time for the windows beyond the budget's shares: this many budgets after
                           # iteration 0 (the experiments' knob; 0: windows get what the shares leave)
    phys_slack=0.10,       # routed physics a strict completion/DRC gain may cost (scorecard.accept)
    eff_tiebreak=False,    # equal on everything else: keep a board with dominating copper (length, vias); A/B arm
    rudy_scale=0.5,        # RUDY overflow near failures added to the history (0: off)
    finish=True,           # a finishing stage: the full bridge over the whole board, critical copper locked
    finish_share=0.20,     # time reserved for it up front: max(finish_min_s, finish_share x budget)
    finish_min_s=120.0,
    finish_release=True,   # a second finishing try releases the module copper on open corridors
    last_mile_min_s=60.0,  # with finish: when no finishing try could run (<= 60 s left), the kept
                           # board's open nets still get lastmile.close for at least this long
    diagnose_s=30.0,       # the final board's "blocked" diagnosis: at most this (and 5 % of the budget)
    recycle=True,          # when every window is exhausted and time is left, sample them all again
    min_cycle_s=5.0,       # ... unless the last cycle took less than this (nothing could be routed)
    patience_cycles=2,     # stop after this many full cycles over the windows in a row accept nothing
)


def share_cap(parts, o):
    """The part-share cap: at most max_part_share of the board's movable parts (at least 3)."""
    n_mov = sum(1 for g in parts.values() if not g.locked)
    return max(3, int(round(o["max_part_share"] * n_mov)))


def escalate(win, attempt, parts, bounds, o):
    """Window `win` for its attempt number: the same spots with the margin x1.5, two more
    parts per earlier attempt (never beyond the part-share cap: on a 15-part board 5 -> 7 -> 9
    parts was 60 % of the board, a global re-place), and parts with many pins allowed; the
    highest-priority window they form. Spots are not merged beyond the cap either."""
    if attempt <= 0:
        return win
    k = min(attempt, 2)          # windows stop growing after two escalations; seeds still differ
    cap = min(o["max_parts"] + 2 * k, share_cap(parts, o))
    ws = plan_windows(win.spots, parts, bounds, margin=o["margin"] * (1.5 ** k),
                      max_parts=cap, max_pins=None, merge_factor=1.0)
    return ws[0] if ws else win


def derive_seed(seed, it, k=0):
    """The seed of iteration `it` (and sub-stage k): fixed by the run's seed."""
    return (int(seed) * 1000003 + it * 7919 + k * 104729) % 2_147_483_647


def _route_info(row):
    """The route report of an iteration row (iteration 0: stages; a window: repair; a finish)."""
    return (row.get("route") or (row.get("stages") or {}).get("route")
            or (row.get("repair") or {}).get("route")) or {}


def _packages(rows):
    """(packages, iteration) of the latest BGA escape certificate (balls no routing can escape
    under the board's rules) any bridge run reported, else None."""
    for r in reversed(rows):
        p = (_route_info(r).get("blocked") or {}).get("packages")
        if p:
            return p, r.get("iter")
    return None


class JointLoop:
    def __init__(self, stages, opts=None, log=None):
        self.stages = stages
        self.opts = {**DEFAULTS, **(opts or {})}
        self.log = log or (lambda *a: None)

    # ------------------------------------------------------------------ helpers
    def _spots(self, fb, lay):
        sp = unrouted_spots(fb.get("drc") or {}) + error_spots(fb.get("drc") or {})
        if self.opts["physics_spots"]:
            _, _, centres, refs = self._geom
            mp = getattr(self.stages, "module_parts", {}) or {}
            sp += physics_spots(fb.get("recheck") or {}, mp, centres, refs)
        return sp

    def _history(self, hist, lay, fb):
        """Failed connections into the congestion history, then the placer's RUDY overflow
        around them (stages.rudy, when the stages have it)."""
        spots = unrouted_spots(fb.get("drc") or {})
        for s in spots:
            hist.add_spot(s, amount=self.opts["history_amount"])
        if spots and self.opts["rudy_scale"] > 0 and hasattr(self.stages, "rudy"):
            try:
                x0, y0, b, util = self.stages.rudy(lay)
                hist.add_overflow(x0, y0, b, util, scale=self.opts["rudy_scale"])
            except Exception as e:  # noqa: BLE001 - the history still has the failures
                self.log(f"rudy map failed: {type(e).__name__}: {e}")

    def _save(self, st, lay, output, rep):
        """Write the incumbent to OUTPUT now: a run killed later (an external timeout, a
        stage overrunning its budget) still leaves its best board."""
        try:
            st.finish(lay, output)
        except Exception as e:  # noqa: BLE001 - the final write tries again
            self.log(f"interim write failed: {type(e).__name__}: {e}")
            rep.setdefault("interim_write_errors", []).append(f"{type(e).__name__}: {e}")

    def _row(self, it, card, **kw):
        # a check that did not run reads null, and the stage's note says why (never 0 or 10**6)
        unc, err, phys, flagged = card.reported()
        drc = card.checked.get("drc", True)
        row = dict(iter=it, unconnected=unc, errors=err, placement_errors=card.placement_errors if drc else None,
                   physics=phys, place_terms=None if card.place_terms is None else round(card.place_terms, 4),
                   track_length_mm=None if card.track_length_mm is None else round(card.track_length_mm, 2),
                   vias=card.vias, flagged=flagged, checked=dict(card.checked), note=card.note or None)
        row.update(kw)
        return row

    def _final_blocked(self, st, best, card, fb, best_it, rows, it, to_deadline, time_s):
        """{blocked, blocked_note}: the diagnosis of the final board's open connections, or
        null with the reason it is missing."""
        o = self.opts
        pk = _packages(rows)
        if not card.checked.get("drc", True):
            return dict(blocked=None, blocked_note="not diagnosed: the final board's DRC did not run")
        if card.unconnected == 0:
            return dict(blocked=None, blocked_note="nothing open")
        own = ((getattr(best, "info", None) or {}).get("route") or {}).get("blocked")
        if isinstance(own, dict) and ("undiagnosed" in own or "error" in own):
            blk, note = dict(own), f"the bridge's diagnosis of iteration {best_it}"
        elif not hasattr(st, "diagnose"):
            blk, note = None, "not diagnosed: these stages have no diagnosis"
        else:
            t = min(float(o["diagnose_s"]), 0.05 * time_s, to_deadline() - 10.0)
            if t < 5.0:
                blk, note = None, f"not diagnosed: no time left ({max(0.0, to_deadline()):.0f}s)"
            else:
                try:
                    blk = st.diagnose(best, fb.get("drc") or {}, it + 1, t)
                    note = f"diagnosed on the final board (iteration {best_it}) in at most {t:.0f}s"
                except Exception as e:  # noqa: BLE001 - a diagnosis never costs the board
                    blk, note = None, f"not diagnosed: {type(e).__name__}: {e}"
        if pk is not None and (blk is None or not blk.get("packages")):
            blk = dict(blk or {})
            blk["packages"], blk["packages_iter"] = pk
        return dict(blocked=blk, blocked_note=note)

    # ------------------------------------------------------------------ run
    def run(self, output, time_s=900.0, seed=0, start=None):
        """start: an already placed board path (skip the placer), else the stages place."""
        o = self.opts
        t0 = clock_now()
        reserve = max(float(o["reserve"]), 0.04 * time_s)
        deadline = t0 + time_s

        def left():
            return deadline - clock_now() - reserve

        fin_res = max(float(o["finish_min_s"]), float(o["finish_share"]) * time_s) if o["finish"] else 0.0

        def left_win():           # what the windows may use: the finishing stage keeps its reserve
            return left() - fin_res

        st = self.stages
        rows = []
        rep = dict(seed=seed, time_s=time_s, opts={k: v for k, v in o.items()}, iterations=rows)
        self.rep = rep            # what the run got done so far, if a later stage raises (cli: "partial")
        # ---- iteration 0: the staged pipeline
        t = clock_now()
        if start is None:
            lay = st.place(derive_seed(seed, 0), time_s=max(20.0, o["place_share"] * time_s))
        else:
            lay = st.layout_from(start)
        t_place = clock_now() - t
        if o.get("modules", True):
            lay = st.modules(lay, 0)
        route_s = max(30.0, o["route_share"] * left())
        lay = st.route(lay, 0, seed=seed, time_s=route_s)
        card, fb = st.evaluate(lay, 0)
        t_iter0 = clock_now() - t
        rows.append(self._row(0, card, accepted=True, why="staged pipeline", seconds=round(t_iter0, 1),
                              place_s=round(t_place, 1), stages=dict(lay.info)))
        self.log(f"iter 0: {card.unconnected} unconnected, {card.errors} errors, {card.placement_errors} placement "
                 f"errors, physics {card.physics:.3f}, flagged {card.flagged} ({t_iter0:.0f}s)")
        self._geom = st.geometry(lay)
        hist = CongestionHistory(self._geom[1], bin_mm=1.0)
        self._history(hist, lay, fb)
        best, best_card, best_fb, best_it = lay, card, fb, 0
        self._save(st, best, output, rep)
        if float(o["window_budget_factor"]) > 0:
            # a real window budget, measured: iteration 0 kept its usual shares of time_s
            deadline = max(deadline, clock_now() + float(o["window_budget_factor"]) * time_s + fin_res + reserve)
            rep["window_deadline_s"] = round(deadline - t0, 1)
            # the wall ceiling (work mode) follows the whole budget, as for any run of that length
            from kae import budget
            if budget.work_mode():
                budget.set_ceiling(deadline - t0)
        tries = {}
        max_att = int(o["max_attempts"]) if o["max_attempts"] is not None else 2 + int(time_s // 1800)
        rep["max_attempts"] = max_att
        cycles, cycle_t0, cycle_kept, idle = 0, clock_now(), 0, 0
        # a window costs far less than iteration 0 (local re-place, local rip-up, incremental
        # route): start from the minimum and learn from the windows themselves
        est = float(o["min_iter_s"])
        stop = None
        it = 0
        while True:
            if best_card.unconnected == 0 and best_card.errors == 0 and best_card.placement_errors == 0 \
                    and not best_card.flagged:
                stop = "clean, nothing flagged" if best_card.checked.get("physics", True) else \
                    "clean, physics not checked"
                break
            if o["max_iters"] is not None and it >= o["max_iters"]:
                stop = "iteration cap"
                break
            if left_win() < est:
                stop = f"time ({left_win():.0f}s left for windows, an iteration takes ~{est:.0f}s)"
                break
            spots = self._spots(best_fb, best)
            parts, bounds, _, _ = self._geom
            cap = min(o["max_parts"], share_cap(parts, o))
            o_win = dict(o, max_parts=cap)
            base = [w for w in plan_windows(spots, parts, bounds, margin=o["margin"], max_parts=cap,
                                            max_pins=o["max_pins"], merge_factor=1.0)
                    if tries.get(w.key, 0) < max_att]
            if not base:
                # every window tried max_att times: with time left, a new cycle samples them
                # again under new seeds and the history so far (a long budget keeps searching);
                # a cycle that took no time (nothing could be routed) ends it
                idle = idle + 1 if not cycle_kept else 0
                if idle >= int(o["patience_cycles"]):
                    stop = f"no improvement (cycle {cycles})"
                    break
                if o["recycle"] and spots and clock_now() - cycle_t0 >= o["min_cycle_s"]:
                    tries = {}
                    cycles += 1
                    cycle_t0, cycle_kept = clock_now(), 0
                    self.log(f"cycle {cycles}: all windows tried; again with new seeds")
                    continue
                stop = "no window left to try"
                break
            # the least-tried window first, then by priority (plan_windows' order)
            base0 = min(base, key=lambda w: tries.get(w.key, 0))
            attempt = tries.get(base0.key, 0)
            win = escalate(base0, attempt, parts, bounds, o_win)
            it += 1
            t = clock_now()
            bump = sorted({r for s in win.spots if s.kind == "unrouted" for r in s.refs})
            legal = {}
            for s in win.spots:
                if s.kind == "placement":
                    for r in s.refs:
                        legal[r] = max(legal.get(r, 0.0), s.short_mm)
            budget = min(left_win(), max(o["min_iter_s"], o["iter_share"] * time_s))
            try:
                cand, rrep = st.repair(best, win, hist, it, derive_seed(seed, it), time_s=budget, bump_refs=bump,
                                       attempt=attempt, legal_refs=legal, drc=best_fb.get("drc"))
            except Exception as e:  # noqa: BLE001 - one failed window must not lose the incumbent
                import traceback
                self.log(f"repair failed: {type(e).__name__}: {e}\n{traceback.format_exc(limit=6)}")
                cand, rrep = None, dict(outcome=f"error: {type(e).__name__}: {e}")
            tries[base0.key] = attempt + 1
            if cand is None:
                rows.append(dict(iter=it, window=win.to_dict(), accepted=False, why=rrep.get("outcome"),
                                 seconds=round(clock_now() - t, 1), repair=rrep))
                self.log(f"iter {it}: window {list(win.refs)}: {rrep.get('outcome')}")
                continue
            try:
                card, fb = st.evaluate(cand, it)
            except Exception as e:  # noqa: BLE001
                self.log(f"evaluate failed: {type(e).__name__}: {e}")
                rows.append(dict(iter=it, window=win.to_dict(), accepted=False, why=f"evaluate error: {e}",
                                 seconds=round(clock_now() - t, 1), repair=rrep))
                continue
            self._history(hist, cand, fb)
            keep, why = accept(best_card, card, phys_slack=o["phys_slack"], eff_tiebreak=bool(o["eff_tiebreak"]))
            dt = clock_now() - t
            est = max(float(o["min_iter_s"]), 0.5 * est + 0.5 * dt)
            rows.append(self._row(it, card, window=win.to_dict(), accepted=keep, why=why, seconds=round(dt, 1),
                                  repair=rrep, history=hist.summary()))
            self.log(f"iter {it}: window {list(win.refs)} ({len(win.parts)} parts): {card.unconnected} unconnected, "
                     f"{card.errors} errors, physics {card.physics:.3f} -> {'kept' if keep else 'reverted'} ({why}, "
                     f"{dt:.0f}s)")
            if keep:
                best, best_card, best_fb, best_it = cand, card, fb, it
                self._save(st, best, output, rep)
                self._geom = st.geometry(best)
                tries = {}               # the board changed: earlier failures may now succeed
                cycle_kept += 1
        rep["stop"] = stop
        rep["cycles"] = cycles + 1
        # ---- finishing: the full bridge (repair rounds) over the whole board with the
        # critical copper locked, in the time reserved for it; judged by the same rule. If
        # connections stay open, a second try releases the critical copper of the modules on
        # their corridors (the acceptance rule prices the physics that costs)
        # (a restart portfolio as the finishing stage has its own restarts: one try)
        release = o.get("finish_release", True) and not getattr(st, "finish_restarts", False)
        tries_fin = [None, "release"] if release else [None]
        finished = False          # a finishing try ran on the kept board (it ends in the last mile)
        for mode in tries_fin if o["finish"] else []:
            if best_card.clean or left() <= 60.0:
                break
            base, released = best, []
            if mode == "release":
                try:
                    spots = unrouted_spots(best_fb.get("drc") or {})
                    released = st.release_near(best, spots) if spots and hasattr(st, "release_near") else []
                    base = st.release(best, released) if released else best
                except Exception as e:  # noqa: BLE001
                    self.log(f"release failed: {type(e).__name__}: {e}")
                    released = []
                if not released:
                    break
            it += 1
            t = clock_now()
            try:
                # the first try leaves time for the second one
                share = 0.6 if (mode is None and len(tries_fin) > 1) else 0.85
                cand = st.route(base, it, seed=derive_seed(seed, it), time_s=max(60.0, share * left()), finish=True)
                card, fb = st.evaluate(cand, it)
                keep, why = accept(best_card, card, phys_slack=o["phys_slack"], eff_tiebreak=bool(o["eff_tiebreak"]))
            except Exception as e:  # noqa: BLE001 - the incumbent stands
                cand, card, fb, keep, why = None, None, None, False, f"error: {type(e).__name__}: {e}"
            dt = clock_now() - t
            row = dict(iter=it, finish=mode or True, released=released, accepted=keep, why=why, seconds=round(dt, 1))
            if card is not None:
                row = self._row(it, card, finish=mode or True, released=released, accepted=keep, why=why,
                                seconds=round(dt, 1), route=(cand.info or {}).get("route"))
            finished = finished or card is not None
            rows.append(row)
            self.log(f"finish{' (release ' + ', '.join(released) + ')' if released else ''}: "
                     f"{getattr(card, 'unconnected', '?')} unconnected, {getattr(card, 'errors', '?')} errors, "
                     f"physics {getattr(card, 'physics', float('nan')):.3f} -> {'kept' if keep else 'reverted'} "
                     f"({why}, {dt:.0f}s)")
            if keep:
                best, best_card, best_fb, best_it = cand, card, fb, it
                self._save(st, best, output, rep)
        # ---- the kept board always gets a last mile: when no finishing try could run (time
        # spent, e.g. an iteration 0 that overran), lastmile.close on its open nets for at least
        # last_mile_min_s, however late (it may use the write reserve; OUTPUT already holds the
        # incumbent). The first route skipped its last mile only because a finish follows.
        nets = sorted({n for sp in unrouted_spots(best_fb.get("drc") or {}) for n in sp.nets})
        if (o["finish"] and not finished and not best_card.clean and nets and best_card.checked.get("drc", True)
                and hasattr(st, "close_open")):
            it += 1
            t = clock_now()
            budget = max(float(o["last_mile_min_s"]), left())
            try:
                cand = st.close_open(best, it, nets, time_s=budget)
                card, fb = st.evaluate(cand, it)
                keep, why = accept(best_card, card, phys_slack=o["phys_slack"], eff_tiebreak=bool(o["eff_tiebreak"]))
            except Exception as e:  # noqa: BLE001 - the incumbent stands
                cand, card, fb, keep, why = None, None, None, False, f"error: {type(e).__name__}: {e}"
            dt = clock_now() - t
            row = dict(iter=it, finish="last mile", accepted=keep, why=why, seconds=round(dt, 1), budget_s=round(budget, 1))
            if card is not None:
                row = self._row(it, card, finish="last mile", accepted=keep, why=why, seconds=round(dt, 1),
                                budget_s=round(budget, 1), route=(cand.info or {}).get("route"))
            rows.append(row)
            self.log(f"last mile on the kept board ({len(nets)} nets, {budget:.0f}s): "
                     f"{'kept' if keep else 'reverted'} ({why}, {dt:.0f}s)")
            if keep:
                best, best_card, best_fb, best_it = cand, card, fb, it
                self._save(st, best, output, rep)
        rep["final"] = best_card.to_dict()
        rep["final"]["iter"] = best_it
        rep["initial"] = rows[0] if rows else None
        rep["accepted"] = sum(1 for r in rows[1:] if r.get("accepted"))
        rep["finish"] = st.finish(best, output)
        # ---- what keeps the final board's open connections open (kae.route.blocked): the
        # finishing bridge's own diagnosis when it made this board, else one run now (OUTPUT is
        # written); the BGA escape certificates (balls no routing can escape) ride along
        rep["final"].update(self._final_blocked(st, best, best_card, best_fb, best_it, rows, it,
                                                lambda: deadline - clock_now(), time_s))
        rep["seconds"] = round(clock_now() - t0, 1)
        self.log(f"stop: {stop}; final {best_card.unconnected} unconnected, {best_card.errors} errors, physics "
                 f"{best_card.physics:.3f}; {rep['accepted']} of {len(rows) - 1} iterations kept ({rep['seconds']}s)")
        return rep
