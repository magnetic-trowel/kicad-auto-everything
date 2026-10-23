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
   that is not exhausted is repaired. A window that was tried and rejected is retried at
   most `max_attempts` times, each time larger (margin x1.5) and with the congestion weight
   x1.5 (annealed coupling).
3. **Repair.** stages.repair: re-place the window's parts, rip up the nets touching it, redo
   its modules, re-route with everything else locked.
4. **Judge.** scorecard.accept against the incumbent: legality, completion and DRC must not
   get worse, routed physics must not get worse, and something must get better. Otherwise
   the incumbent stays (revert).

Stops when the board is clean with nothing flagged, no window is left, `max_iters` is
reached, or the time left (minus a reserve for the final write and DRC) is below what an
iteration has been taking. Seeds of every stage derive from the run's seed and the
iteration number, and windows are ordered deterministically, so the same seed gives the
same result whenever no time budget binds (a time-bound stage stops at the clock).
"""
from __future__ import annotations

import time

from .feedback import CongestionHistory, error_spots, physics_spots, plan_windows, unrouted_spots
from .scorecard import accept

DEFAULTS = dict(
    max_iters=12,          # repair iterations at most
    max_attempts=2,        # tries of one window (each larger, with a higher congestion weight)
    margin=2.0,            # mm around a spot's parts (window_for_spot)
    max_parts=8,           # movable parts per window
    max_part_share=0.35,   # ... and at most this share of the board's movable parts (at least 3)
    max_pins=12,           # first attempt: parts with more connected pads stay fixed (None: any part)
    history_amount=1.0,    # history added per failed connection's corridor bin (utilization units)
    place_share=0.30,      # share of the budget for the placer
    route_share=0.6,       # share of what is left after placing and the module stage, for the first route
    reserve=25.0,          # seconds kept for the final write and DRC (at least 4 % of the budget)
    physics_spots=True,    # flagged modules make windows too
    min_iter_s=120.0,      # an iteration is not started with less than this left
    iter_share=0.25,
    phys_slack=0.10,       # routed physics a strict completion/DRC gain may cost (scorecard.accept)
    rudy_scale=0.5,        # RUDY overflow near failures added to the history (0: off)       # one window's repair gets at most this share of the budget (at least 90 s)
)


def escalate(win, attempt, parts, bounds, o):
    """Window `win` for its attempt number: the same spots with the margin x1.5, two more
    parts per earlier attempt, and parts with many pins allowed; the highest-priority window
    they form."""
    if attempt <= 0:
        return win
    ws = plan_windows(win.spots, parts, bounds, margin=o["margin"] * (1.5 ** attempt),
                      max_parts=o["max_parts"] + 2 * attempt, max_pins=None)
    return ws[0] if ws else win


def derive_seed(seed, it, k=0):
    """The seed of iteration `it` (and sub-stage k): fixed by the run's seed."""
    return (int(seed) * 1000003 + it * 7919 + k * 104729) % 2_147_483_647


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

    def _row(self, it, card, **kw):
        row = dict(iter=it, unconnected=card.unconnected, errors=card.errors, placement_errors=card.placement_errors,
                   physics=round(card.physics, 4), place_terms=None if card.place_terms is None else round(card.place_terms, 4),
                   flagged=list(card.flagged))
        row.update(kw)
        return row

    # ------------------------------------------------------------------ run
    def run(self, output, time_s=900.0, seed=0, start=None):
        """start: an already placed board path (skip the placer), else the stages place."""
        o = self.opts
        t0 = time.monotonic()
        reserve = max(float(o["reserve"]), 0.04 * time_s)
        deadline = t0 + time_s

        def left():
            return deadline - time.monotonic() - reserve

        st = self.stages
        rows = []
        rep = dict(seed=seed, time_s=time_s, opts={k: v for k, v in o.items()}, iterations=rows)
        # ---- iteration 0: the staged pipeline
        t = time.monotonic()
        if start is None:
            lay = st.place(derive_seed(seed, 0), time_s=max(20.0, o["place_share"] * time_s))
        else:
            lay = st.layout_from(start)
        t_place = time.monotonic() - t
        if o.get("modules", True):
            lay = st.modules(lay, 0)
        route_s = max(30.0, o["route_share"] * left())
        lay = st.route(lay, 0, seed=seed, time_s=route_s)
        card, fb = st.evaluate(lay, 0)
        t_iter0 = time.monotonic() - t
        rows.append(self._row(0, card, accepted=True, why="staged pipeline", seconds=round(t_iter0, 1),
                              place_s=round(t_place, 1), stages=dict(lay.info)))
        self.log(f"iter 0: {card.unconnected} unconnected, {card.errors} errors, {card.placement_errors} placement "
                 f"errors, physics {card.physics:.3f}, flagged {card.flagged} ({t_iter0:.0f}s)")
        self._geom = st.geometry(lay)
        hist = CongestionHistory(self._geom[1], bin_mm=1.0)
        self._history(hist, lay, fb)
        best, best_card, best_fb = lay, card, fb
        tries = {}
        est = max(float(o["min_iter_s"]), 0.5 * (t_iter0 - t_place))
        stop = None
        it = 0
        while True:
            if best_card.unconnected == 0 and best_card.errors == 0 and best_card.placement_errors == 0 \
                    and not best_card.flagged:
                stop = "clean, nothing flagged"
                break
            if it >= o["max_iters"]:
                stop = "iteration cap"
                break
            if left() < est:
                stop = f"time ({left():.0f}s left, an iteration takes ~{est:.0f}s)"
                break
            spots = self._spots(best_fb, best)
            parts, bounds, _, _ = self._geom
            n_mov = sum(1 for g in parts.values() if not g.locked)
            cap = min(o["max_parts"], max(3, int(round(o["max_part_share"] * n_mov))))
            o_win = dict(o, max_parts=cap)
            base = [w for w in plan_windows(spots, parts, bounds, margin=o["margin"], max_parts=cap,
                                            max_pins=o["max_pins"])
                    if tries.get(w.key, 0) < o["max_attempts"]]
            if not base:
                stop = "no window left to try"
                break
            # the least-tried window first, then by priority (plan_windows' order)
            base0 = min(base, key=lambda w: tries.get(w.key, 0))
            attempt = tries.get(base0.key, 0)
            win = escalate(base0, attempt, parts, bounds, o_win)
            it += 1
            t = time.monotonic()
            bump = sorted({r for s in win.spots if s.kind == "unrouted" for r in s.refs})
            budget = min(left(), max(o["min_iter_s"], o["iter_share"] * time_s))
            cand, rrep = st.repair(best, win, hist, it, derive_seed(seed, it), time_s=budget, bump_refs=bump,
                                   attempt=attempt)
            tries[base0.key] = attempt + 1
            if cand is None:
                rows.append(dict(iter=it, window=win.to_dict(), accepted=False, why=rrep.get("outcome"),
                                 seconds=round(time.monotonic() - t, 1), repair=rrep))
                self.log(f"iter {it}: window {list(win.refs)}: {rrep.get('outcome')}")
                continue
            card, fb = st.evaluate(cand, it)
            self._history(hist, cand, fb)
            keep, why = accept(best_card, card, phys_slack=o["phys_slack"])
            dt = time.monotonic() - t
            est = max(float(o["min_iter_s"]), 0.5 * est + 0.5 * dt)
            rows.append(self._row(it, card, window=win.to_dict(), accepted=keep, why=why, seconds=round(dt, 1),
                                  repair=rrep, history=hist.summary()))
            self.log(f"iter {it}: window {list(win.refs)} ({len(win.parts)} parts): {card.unconnected} unconnected, "
                     f"{card.errors} errors, physics {card.physics:.3f} -> {'kept' if keep else 'reverted'} ({why}, "
                     f"{dt:.0f}s)")
            if keep:
                best, best_card, best_fb = cand, card, fb
                self._geom = st.geometry(best)
        rep["stop"] = stop
        rep["final"] = best_card.to_dict()
        rep["initial"] = rows[0] if rows else None
        rep["accepted"] = sum(1 for r in rows[1:] if r.get("accepted"))
        rep["finish"] = st.finish(best, output)
        rep["seconds"] = round(time.monotonic() - t0, 1)
        self.log(f"stop: {stop}; final {best_card.unconnected} unconnected, {best_card.errors} errors, physics "
                 f"{best_card.physics:.3f}; {rep['accepted']} of {len(rows) - 1} iterations kept ({rep['seconds']}s)")
        return rep
