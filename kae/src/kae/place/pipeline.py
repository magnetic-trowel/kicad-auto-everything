# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The placement pipeline: board -> problem -> brief -> macros -> seed -> anneal ->
legalize -> exact check -> poses.

    res = place(board, seed=0, time_s=300, physics=True)
    res.poses    # {uuid: (x, y, rot, side)} for every movable footprint
    res.report   # stage timings, costs, legality

Stages:
1. Problem (kae.place.problem): movable and fixed parts, grid rectangles, outline cover.
2. Brief (kae.circuit.brief, else kae.place.stubs): net roles weight the nets (ground x0.1,
   power x0.2, H11) in both arms; with physics on, its structures become macros
   (kae.place.clusters) and the place terms (kae.physics.place_terms, else the stub)
   join the annealer's cost.
3. Seed (kae.place.seed): quadratic placement of macros and parts, spreading, then a
   CP-SAT floorplan (macros as rigid items with their top-K layouts x 4 rotations).
4. Anneal (kae.place.anneal): physics + routability + legality ramp + displacement, plus
   the protection-order rules of protected connector chains (physics arm). The physics is
   the place terms with utilization priced linearly and saturated beyond 3x budget
   (SA_U_SAT); the report's scorecard is the terms' own (linear sum and the official total
   with the over-budget barrier).
5. Legalize (kae.place.legalize): windowed CP-SAT, then the exact polygon check. The
   annealed result is kept only if it is grid-legal after legalization and does not cost
   more than the legal seed; otherwise the seed is returned.

Budgets: `time_s` is the wall time the caller allows (kaebench's --timeout). The pipeline
plans to finish in min(0.85 * time_s - 10, 20 s + 3 s per movable part), so small boards
do not idle away a long timeout. The annealer budgets CPU seconds; CP-SAT stages wall
seconds with `workers` threads.
"""
from __future__ import annotations

import math
import os
import time
from dataclasses import dataclass, field

import numpy as np

from . import clusters, cpsat, edges, seed as seedmod
from .anneal import Annealer, make_annealer
from . import exact as exactmod
from . import zones as zonesmod
from .legalize import exact_check, legalize
from .problem import PLACE_SEVERITY, Problem, fixed_text
from .state import State, grid_violations
from .stubs import make_brief, make_terms

ROLE_KIND = {"ground": "ground", "rail": "power", "power": "power"}
FLOORPLAN_MAX_ITEMS = 40   # above this the global HPWL floorplan rarely finds a solution in time
ROLE_WEIGHT = {"clock": 1.5, "high_speed": 1.5, "analog": 1.2, "rf": 1.5, "switch_node": 1.0}


@dataclass
class Result:
    poses: dict
    report: dict = field(default_factory=dict)
    state: object = None
    problem: object = None
    terms: object = None         # the place terms the scorecard uses (None: no structures)
    order: list = field(default_factory=list)    # the protection-order rules
    brief: dict | None = None    # the circuit brief placement used (kae.hazards: net voltages)
    verified: dict | None = None  # place(verify=...): what the caller's check said of the board as written


SA_U_SAT = 3.0   # see place(): utilization saturates beyond this in the annealer's terms
SILK_W = 1.0     # the annealer's silkscreen term (silk_on projects): overlap / mean part area
CHAN_W = 0.0     # the annealer's routing-channel term (pad halos overlapping / mean part area)


def _default_workers():
    env = os.environ.get("KAE_WORKERS")
    if env:
        return max(1, int(env))
    return max(1, min(4, (os.cpu_count() or 2) // 2))


def plan_budget(time_s, n_movable):
    cap = 20.0 + 3.0 * n_movable
    return max(5.0, min(0.85 * float(time_s) - 10.0, cap))


def _net_kinds(brief):
    kinds = {}
    for name, d in ((brief or {}).get("nets") or {}).items():
        role = (d or {}).get("role") if isinstance(d, dict) else d
        if role in ROLE_KIND:
            kinds[name] = ROLE_KIND[role]
        elif role in ("no_connect",):
            kinds[name] = "signal"
        elif role:
            kinds[name] = "signal"
    return kinds


def _net_roles(brief):
    out = {}
    for name, d in ((brief or {}).get("nets") or {}).items():
        out[name] = (d or {}).get("role") if isinstance(d, dict) else d
    return out


def _severity_mode(board, board_path, opts):
    """The project's KAE_PLACE_SEVERITY text variable, else opts['place_severity'], else None (the
    environment, else the default: resolve_severity)."""
    tv = (getattr(getattr(board, "rules", None), "kae_vars", None) or {}).get("KAE_PLACE_SEVERITY")
    if tv or (opts or {}).get("place_severity"):
        return tv or opts["place_severity"]
    return None      # Problem._severities: the environment, else the default


def body_hazards(rep, P, st):
    """(Re)compute the relaxed-body hazards of a report at the state's poses (Problem.
    relaxed_body_hazards); the KiCad loop calls it again after moving parts."""
    hz = [h for h in rep.get("hazards", []) if h.get("code") not in ("body_overlap", "body_relaxed")]
    rep["hazards"] = hz + P.relaxed_body_hazards(st)
    return rep["hazards"]


def _escalate(P, st, workers, seed, log, time_s, relax_ok=False, hard_end=None):
    """Legality before wishes: drop the routing margin, then (relax_ok: relax_bodies 'escalate'
    or 'auto') let bodies without courtyards overlap (KiCad does not check them), legalizing
    again after each step. Returns the steps taken with what each left illegal. `hard_end`
    (monotonic seconds; the severity ladder's rungs): no step starts after it, and none runs past it."""
    steps = []
    for step in ("escape bands off", "margin 0") + (("bodies relaxed",) if relax_ok else ()):
        if not grid_violations(st):
            break
        if step == "escape bands off":
            if not getattr(P, "escape_on", False):
                continue
            P.set_escape(P.escape, on=False)
        elif step == "margin 0":
            if P.margin <= 0:
                continue
            P.set_margin(0.0)
        else:
            relaxed = P.relax_bodies()
            if not relaxed:
                continue
        ts = time_s
        if hard_end is not None:
            ts = min(time_s, hard_end - time.monotonic())
            if ts < 1.0:
                steps.append(dict(step=step, skipped="time"))
                break
        r = legalize(P, st, time_s=ts, workers=workers, seed=seed, log=log, window_share=0.5)
        steps.append(dict(step=step, end_violators=r.get("end_violators"), violations=r.get("violations")))
        if step == "bodies relaxed":
            steps[-1]["relaxed"] = relaxed          # data; hazards: Problem.relaxed_body_hazards
        if log:
            log(f"escalation: {step}, {r.get('end_violators')} parts still illegal")
    return steps


def _seed_state(P, macros, net_w, seed, log, partition=False, jitter=0.0, zones=None, zone_w=0.0):
    """Quadratic + spread: an initial state (macros at their best layout). `partition`
    spreads by recursive bisection of the free cells (density-feasible, for big boards)
    instead of pairwise repulsion. `jitter` > 0 moves every object by a normal offset of
    jitter x the board's span (seeded) before the spread: a different start for the
    floorplan and the annealer (--probe-select's candidates)."""
    objs, owner = seedmod._objects(P, macros)
    pos = seedmod.quadratic(P, objs, owner, net_w)
    # connectors are anchors: pinned inside the nearest edge, then the rest re-solved
    wmax = max([net_w.get(net.i, net.weight) for net in P.nets] or [1.0])
    anchors = seedmod.connector_anchors(P, objs, pos, weight=5.0 * wmax)
    if anchors:
        pos = seedmod.quadratic(P, objs, owner, net_w, anchors=anchors)
    if zones is not None and zone_w > 0:
        # parts with pads on a fixed zone's net toward that zone (kae.place.zones), twice:
        # the second pass from where the first one put them
        for _ in range(2):
            za = zonesmod.seed_anchors(zones, P, objs, pos, weight=zone_w * wmax)
            if not za:
                break
            pos = seedmod.quadratic(P, objs, owner, net_w, anchors={**za, **anchors})
    # big packages (or macros) with many pads on fixed zones go where their zones are, and stay
    lay_k = {i: off[2] for mac in macros for i, off in mac.layouts[0].offsets.items()}
    pinned = zonesmod.pin_packages(zones, P, objs, pos, rot_of=lay_k) if (zones is not None and zone_w > 0) else {}
    pin_spread = {o: (x, y, box) for o, (x, y, _, box) in pinned.items()}
    if jitter > 0:
        x0, y0, x1, y1 = P.outline.bounds
        rng = np.random.default_rng(seed)
        pos = pos + rng.normal(0.0, jitter * max(x1 - x0, y1 - y0), pos.shape)
        pos[:, 0] = np.clip(pos[:, 0], x0, x1)
        pos[:, 1] = np.clip(pos[:, 1], y0, y1)
    if partition:
        pos = seedmod.partition_spread(P, objs, pos, pinned=pin_spread)
    else:
        pos = seedmod.spread(P, objs, pos, owner, net_w, seed=seed)
    st = State(P)
    lay_of = {}
    for mac in macros:
        for i, off in mac.layouts[0].offsets.items():
            lay_of[i] = off
    for o, (members, w, h, rel) in enumerate(objs):
        for i in members:
            dx, dy = rel[i]
            X, Y = P.grid_of(pos[o, 0] + dx, pos[o, 1] + dy)
            st.X[i], st.Y[i] = X, Y
            st.K[i] = lay_of.get(i, (0, 0, 0))[2] if i in lay_of else 0
    for o, (_, _, poses, _) in pinned.items():
        for i, (X, Y, k) in poses.items():
            st.X[i], st.Y[i], st.K[i] = X, Y, k
    # the regional floorplan keeps them (it minimizes HPWL alone)
    P.zone_pinned = {i for o in pinned for i in pinned[o][2]}
    return st, objs


def hot_loop_hazards(rows):
    """Hazards (the shared report schema) for commutation loops whose estimated inductance lets the switch
    node ring past the switch's absolute maximum (kae.physics.criteria): block when the rating is the
    part's, warn when it is the prior's. Over the derated line but under V_abs is the term's own
    over-budget price, not a hazard here (the routed evaluator reports it)."""
    out = []
    for r in rows:
        info = r.get("info") or {}
        if r.get("kind") != "commutation" or not info.get("L_abs_nH"):
            continue
        L, la = float(r.get("value", 0.0)), float(info["L_abs_nH"])
        if L <= la:
            continue
        known = bool(info.get("V_abs_known"))
        out.append(dict(code="hot_loop_over_abs_max", severity="block" if known else "warn", category="electrical",
                        message=(f"{r.get('id')}: the hot loop's estimated {L:.2g} nH lets the switch node ring past "
                                 f"its {info.get('V_abs'):g} V absolute maximum (at most {la:.2g} nH)"
                                 + ("" if known else "; the rating is a prior, the part may be rated higher")),
                        objects=list(r.get("members") or [])[:8],
                        evidence=dict(L_nH=round(L, 3), L_abs_nH=round(la, 3), V_in=info.get("V_in"),
                                      V_abs=info.get("V_abs"), V_abs_source="part" if known else "prior",
                                      limit_source="kae.physics.criteria: peak <= V_abs (derate 1)"),
                        fix="place the input capacitor beside the switch and its ground pin, same side, with the "
                            "return on the adjacent plane" + ("" if known else "; or state the switch's V_max")))
    return out


def physics_summary(terms, poses, breakdown=True):
    """Physics scorecard: the annealer's linear total, the official total with the
    over-budget barrier (priors.phi), and per-structure utilization."""
    rows = terms.breakdown(poses)
    try:
        from kae.physics.priors import Knobs, phi
        beta = Knobs().barrier
    except ImportError:
        def phi(u, b):
            return u
        beta = 0.0
    lin = sum(float(r.get("confidence", 1.0)) * float(r.get("util", r.get("utilization", 0.0))) for r in rows)
    off = sum(float(r.get("confidence", 1.0)) * phi(float(r.get("util", r.get("utilization", 0.0))), beta)
              for r in rows)
    out = dict(total_linear=round(lin, 4), total=round(off, 4), structures=len(rows),
               over_budget=sum(1 for r in rows if float(r.get("util", r.get("utilization", 0.0))) > 1.0))
    hz = hot_loop_hazards(rows)
    if hz:
        out["hazards"] = hz
    if breakdown:
        out["breakdown"] = [dict(id=r.get("id"), kind=r.get("kind"), util=round(float(r.get("util", r.get("utilization", 0.0))), 4),
                                 value=round(float(r.get("value", 0.0)), 4), unit=r.get("unit"),
                                 members=r.get("members", [])[:8]) for r in rows[:40]]
    return out


# The severity ladder (kae-exact-legality.md, "Severity ladder"): strict first, level_c only when
# strict cannot fit. On 113 boards whose projects waive checks (decide-ab, legality-ab2, k=2) strict
# was legal under the real rules on 46% of runs against level_c's 28%, but left 12 boards with
# placement shorts against 6: when the drawn courtyards do not fit, the placer piles parts up.
LADDER = "strict_then_level_c"
LADDER_STRICT_SHARE = 0.55   # strict's share of the caller's time; level_c gets the rest (>= 45%)
LADDER_MIN_S = 20.0          # a level_c rung with less time left than this is not started
LADDER_MAX_UTIL = 1.0        # strict is skipped when drawn courtyards fill more than the board on a side
LADDER_KICAD_FRAC = 0.15     # each rung keeps this share of its time (at least LADDER_KICAD_MIN_S, at most
LADDER_KICAD_MIN_S = 30.0    # half) for the caller's check: KiCad's DRC loop and the write
ELECTRICAL = ("shorting_items", "clearance", "hole_clearance")   # errors that make a board not work


def resolve_severity(board, board_path=None, opts=None):
    """The placement legality mode: the project's KAE_PLACE_SEVERITY text variable, else
    opts['place_severity'], else the KAE_PLACE_SEVERITY environment variable, else
    PLACE_SEVERITY. One of 'strict_then_level_c', 'strict', 'level_c', 'board'."""
    mode = _severity_mode(board, board_path, opts) or os.environ.get("KAE_PLACE_SEVERITY") or PLACE_SEVERITY
    mode = str(mode).strip().lower().replace("-", "_")
    if mode not in (LADDER, "strict", "level_c", "board"):
        raise ValueError(f"place severity {mode!r}: '{LADDER}', 'strict', 'level_c' or 'board'")
    return mode


def waives_courtyards(board):
    """The board's project downgrades courtyards_overlap: the only case where level_c differs
    from strict (Problem._severities: cy_shrink)."""
    sev = getattr(getattr(board, "rules", None), "severities", None) or {}
    return sev.get("courtyards_overlap", "error") != "error"


def placement_errors(res):
    """{type: count} of the placement errors a result leaves: the exact check's findings, and
    KiCad's errors the placer can repair on the board as written (report kicad_verdict, set by
    kae.cli's KiCad loop). Both often name the same error, so a type counts the larger of the two."""
    rep = res.report
    out = {}
    ex = rep.get("exact")
    for v in ex if isinstance(ex, list) else ():
        t = v.get("type", "?")
        out[t] = out.get(t, 0) + 1
    for t, n in ((rep.get("kicad_verdict") or {}).get("by_type") or {}).items():
        out[t] = max(out.get(t, 0), int(n))
    return out


def rung_key(errs):
    """Better is smaller: no shorts or clearance errors first, then fewer of them, then fewer
    placement errors (soldiercrab: strict 18 shorts and 18 clearance but 56 errors in all against
    level_c's 16 and 9 in 78, mostly mask bridges; the total alone kept strict)."""
    el = sum(errs.get(t, 0) for t in ELECTRICAL)
    return (el > 0, el, sum(errs.values()))


def kicad_checked(res):
    """KiCad's DRC judged the result as written (the caller's verify ran its loop)."""
    return (res.verified or {}).get("clean") is not None and "kicad_verdict" in res.report


def rung_rank(res):
    """Smaller is better: a KiCad-judged rung first (an exact-check count alone never beats
    KiCad's: openaio's unjudged strict rung had 3 electrical findings and 38-55 shorts), then
    rung_key of KiCad's placer errors when judged, else of placement_errors."""
    ck = kicad_checked(res)
    errs = dict((res.report.get("kicad_verdict") or {}).get("by_type") or {}) if ck else placement_errors(res)
    return (0 if ck else 1,) + rung_key(errs)


def courtyard_margin_overlaps(P, st, min_area=1e-4, max_pairs=40):
    """Pairs of parts (at least one movable) whose drawn courtyards, deflated as KiCad's DRC does,
    overlap at the state's poses: [(ref, ref, mm^2, layer)], largest first. Under level_c these
    are the margins the take-in let neighbours share."""
    from shapely.strtree import STRtree
    from kae.board import transform
    defl = float(getattr(P, "max_error", 0.0) or 0.0)
    by_layer = {}
    for p in P.parts:
        x, y, rot, side = st.pose(p.i)
        own_l, opp_l = transform.courtyard_layers(p.fp, side)
        for which, layer in (("own", own_l), ("opposite", opp_l)):
            for g in transform.courtyard(p.fp, x, y, rot, side, which=which, deflate=defl) or ():
                if g is not None and not g.is_empty:
                    by_layer.setdefault(layer, []).append((p.i, g))
    out = []
    for layer, items in by_layer.items():
        tree = STRtree([g for _, g in items])
        for a, (i, g) in enumerate(items):
            for b in tree.query(g):
                b = int(b)
                j, h = items[b]
                if b <= a or j == i or not (P.parts[i].movable or P.parts[j].movable):
                    continue
                area = g.intersection(h).area
                if area > min_area:
                    out.append((P.parts[i].ref, P.parts[j].ref, round(area, 4), layer))
    out.sort(key=lambda r: -r[2])
    return out[:max_pairs]


def _rung_summary(res, seconds):
    errs = placement_errors(res)
    return dict(severity=res.report.get("severity_used"), legal=not errs, errors=sum(errs.values()),
                by_type=errs, electrical=sum(errs.get(t, 0) for t in ELECTRICAL),
                relax_bodies=res.report.get("relax_bodies"), hpwl=res.report.get("hpwl"),
                kicad_verified=kicad_checked(res),
                kicad_errors=(res.report.get("kicad_verdict") or {}).get("by_type") if kicad_checked(res) else None,
                seconds=round(seconds, 1))


def place(board, seed=0, time_s=300.0, physics=True, brief=None, workers=None, log=None, anneal=True,
          edge_mate=False, anneal_args=None, angle_step=None, fixed=(), board_path=None, opts=None,
          verify=None):
    """Place the unlocked footprints of `board` within `time_s` seconds (resolve_severity picks
    the legality profile). The default, 'strict_then_level_c', places at 'strict' with body
    relaxation off, in LADDER_STRICT_SHARE of the time; when that leaves placement errors
    (placement_errors: the exact check, and KiCad's verdict when `verify` gives one) it places
    again from a fresh seed at 'level_c', with relax_bodies as set, in the time left, and keeps
    level_c unless strict was better (rung_rank: a KiCad-judged rung first, then rung_key of
    KiCad's counts). Strict is skipped, and level_c gets the whole time, when drawn courtyards
    cover more than the board on a side (LADDER_MAX_UTIL). Each rung ends its placement
    LADDER_KICAD_FRAC of its share early (hard_end), for `verify`. Order of softening: strict courtyards, then
    Level C courtyards, then (relax_bodies 'escalate') bodies freed to their pads, the riskiest.
    A project that does not waive courtyards_overlap has level_c = strict: one strict rung, with
    relax_bodies as set. `verify(res, end)`: the caller's check of a rung (kae.cli: write the
    board and run KiCad's DRC loop until `end`, monotonic seconds), called on each rung of a
    two-rung ladder; its return value is kept as res.verified. Report: severity_used,
    severity_ladder, and a severity_fallback hazard when the fallback ran."""
    log = log or (lambda *a, **k: None)
    kw = dict(seed=seed, physics=physics, workers=workers, log=log, anneal=anneal, edge_mate=edge_mate,
              anneal_args=anneal_args, angle_step=angle_step, fixed=fixed, board_path=board_path, opts=opts)
    from kae.route.constraints import setting
    split_mode = int(setting("barrier_split", board_path, opts))
    if split_mode >= 1:
        # a board split by voids or all-layer keepouts: each region placed on its own (kae.place.barriers);
        # 2 also probes that each region can legalize its parts first, moving those it cannot (fit_split)
        from . import barriers
        t_split = time.monotonic()
        split = barriers.true_split(board)
        skipped, fit = None, None
        kw2 = {k: v for k, v in kw.items() if k not in ("seed", "log")}
        if split is not None and split.over_capacity:
            log(f"barrier split skipped: regions {split.over_capacity} cannot hold their parts")
            skipped = dict(skipped="over_capacity", regions=len(split.regions), over_capacity=split.over_capacity)
        elif split is not None and split_mode >= 2:
            fitted, fit = barriers.fit_split(place, board, split, seed=seed, time_s=barriers.PROBE_FRAC * float(time_s),
                                             log=log, **kw2)
            if fitted is None:
                skipped = dict(skipped="unfit", regions=len(split.regions), fit=fit)
            split = fitted
        # mode 1 keeps its whole budget as before; mode 2 gives the regions what the probes left
        left = time_s if fit is None else max(float(time_s) - (time.monotonic() - t_split), 0.5 * float(time_s))
        if split is not None and skipped is None:
            res = barriers.place_split(place, board, split, seed=seed, time_s=left, log=log, verify=verify, **kw2)
            if fit is not None:
                res.report["barrier_split"]["fit"] = fit
            return res
        if skipped is not None:
            opts = dict(opts or {}, barrier_split=0)
            res = place(board, seed=seed, time_s=left, physics=physics, brief=brief, workers=workers, log=log,
                        anneal=anneal, edge_mate=edge_mate, anneal_args=anneal_args, angle_step=angle_step,
                        fixed=fixed, board_path=board_path, opts=opts, verify=verify)
            res.report["barrier_split"] = skipped
            return res
    mode = resolve_severity(board, board_path, opts)
    if mode != LADDER:
        return _place_rung(board, time_s=time_s, brief=brief, severity=mode, **kw)
    ladder = dict(mode=LADDER, strict_share=LADDER_STRICT_SHARE)
    if not waives_courtyards(board):
        res = _place_rung(board, time_s=time_s, brief=brief, severity="strict", **kw)
        ladder.update(rungs=1, fallback=None,
                      note="the project does not waive courtyards_overlap, so level_c is the same as strict")
        res.report["severity_ladder"] = ladder
        return res
    t0 = time.monotonic()
    end = t0 + float(time_s)
    src = None
    if brief is None:           # once for both rungs
        try:
            brief, src = make_brief(board)
        except Exception as e:  # noqa: BLE001 - comprehension must not stop placement
            log(f"brief failed ({type(e).__name__}: {e}); placing without it")
            brief, src = {}, "none"

    def kicad_reserve(share):
        # the end of a rung's share kept for the caller's check (KiCad's DRC loop, the write)
        return 0.0 if verify is None else min(0.5 * share, max(LADDER_KICAD_MIN_S, LADDER_KICAD_FRAC * share))
    t_strict = LADDER_STRICT_SHARE * float(time_s)
    res1 = kicad_reserve(t_strict)
    ladder.update(kicad_reserve_s=round(res1, 1))
    log(f"severity ladder: strict first ({t_strict:.0f} s of {float(time_s):.0f} s, {res1:.0f} s of it for KiCad), "
        "level_c if it cannot fit")
    r1 = _place_rung(board, time_s=t_strict - res1, brief=brief, severity="strict", relax="off",
                     hard_end=t0 + t_strict - res1, max_util=LADDER_MAX_UTIL, **kw)
    aborted = r1.report.get("aborted")
    if src is not None:
        r1.report["brief"]["source"] = src
    if aborted:
        e1 = {}
        ladder["strict"] = dict(severity="strict", skipped=aborted,
                                utilization=(r1.report.get("problem") or {}).get("utilization"),
                                seconds=round(time.monotonic() - t0, 1))
        why = dict(errors=None, by_type={}, source="occupancy", reason=aborted)
        log(f"severity ladder: strict skipped ({aborted}); level_c with the whole time")
    else:
        if verify is not None and r1.poses:
            r1.verified = verify(r1, t0 + t_strict)
        e1 = placement_errors(r1)
        ladder["strict"] = _rung_summary(r1, time.monotonic() - t0)
        if not e1:
            ladder.update(rungs=1, fallback=None)
            r1.report["severity_ladder"] = ladder
            return r1
        why = dict(errors=sum(e1.values()), by_type=e1,
                   source="exact check and KiCad DRC" if kicad_checked(r1) else "exact check")
    ladder["fallback"] = why
    left = end - time.monotonic()
    if not aborted:
        log(f"severity ladder: strict left {why['errors']} placement errors {e1}; level_c with {left:.0f} s left")
    if left < LADDER_MIN_S and not aborted:
        ladder.update(rungs=1, skipped=f"{left:.0f} s left, under {LADDER_MIN_S:.0f} s")
        r1.report["severity_ladder"] = ladder
        r1.report.setdefault("hazards", []).append(dict(
            code="severity_fallback", severity="warn", category="assembly",
            message=(f"Placed with drawn courtyards (strict), which left {why['errors']} placement errors; "
                     "too little time was left to try IPC Level C courtyards (level_c)."),
            objects=[], evidence=dict(used="strict", strict_errors=e1, seconds_left=round(left, 1)),
            fix="Re-place with more time, or with --severity level_c."))
        return r1
    t1 = time.monotonic()
    res2 = kicad_reserve(left)
    r2 = _place_rung(board, time_s=left - res2, brief=brief, severity="level_c", hard_end=t1 + left - res2, **kw)
    if verify is not None and r2.poses:
        r2.verified = verify(r2, end)
    e2 = placement_errors(r2)
    ladder["level_c"] = _rung_summary(r2, time.monotonic() - t1)
    if src is not None:
        r2.report["brief"]["source"] = src
    # a rung KiCad has judged beats one only the exact check has; two judged rungs compare KiCad's counts
    keep_c = bool(aborted) or rung_rank(r2) < rung_rank(r1)
    res = r2 if keep_c else r1
    ladder.update(rungs=1 if aborted else 2, chosen="level_c" if keep_c else "strict",
                  seconds=round(time.monotonic() - t0, 1))
    res.report["severity_ladder"] = ladder
    if keep_c:
        P, st = r2.problem, r2.state
        pairs = courtyard_margin_overlaps(P, st) if (P is not None and st is not None) else []
        refs = []
        for a, b, _, _ in pairs:
            refs += [r for r in (a, b) if r not in refs]
        left_cy = e2.get("courtyards_overlap", 0)
        what = (f"Drawn courtyards (strict) cannot fit: {aborted}, so strict was not tried. " if aborted else
                f"Drawn courtyards (strict) did not fit: strict left {why['errors']} placement errors "
                f"({', '.join(f'{k} {v}' for k, v in sorted(e1.items()))}). ")
        res.report.setdefault("hazards", []).append(dict(
            code="severity_fallback", severity="warn" if left_cy else "info", category="assembly",
            message=(what + f"kae placed with IPC Level C courtyards (level_c): each courtyard taken in by "
                     f"{P.cy_shrink:.2f} mm, as the project waives courtyards_overlap. {len(pairs)} pairs of parts "
                     "share courtyard margin" + (f"; {left_cy} courtyard overlaps remain even so." if left_cy else ".")),
            objects=refs[:40],
            evidence=dict(used="level_c", courtyard_shrink_mm=P.cy_shrink, strict_errors=e1, level_c_errors=e2,
                          strict_skipped=aborted or None,
                          margin_pairs=[dict(a=a, b=b, mm2=m, layer=ly) for a, b, m, ly in pairs],
                          source="kae.place.pipeline LADDER; IPC-7351 courtyard excess B 0.25 / C 0.10 mm"),
            fix="Check the listed parts' spacing for assembly, give the board more room, or re-place with "
                "--severity strict (full courtyards; the dense parts may then collide)."))
    else:
        res.report.setdefault("hazards", []).append(dict(
            code="severity_fallback", severity="info", category="assembly",
            message=(f"Drawn courtyards (strict) left {why['errors']} placement errors; IPC Level C courtyards "
                     f"(level_c) were tried and left {sum(e2.values())}, no better, so the strict placement is kept."),
            objects=[], evidence=dict(used="strict", strict_errors=e1, level_c_errors=e2),
            fix="Give the board more room, fix parts in place, or remove parts."))
    log(f"severity ladder: kept {ladder['chosen']} (strict {None if aborted else rung_rank(r1)}, "
        f"level_c {rung_rank(r2)})")
    return res


def _place_rung(board, seed=0, time_s=300.0, physics=True, brief=None, workers=None, log=None, anneal=True,
                edge_mate=False, anneal_args=None, angle_step=None, fixed=(), board_path=None, opts=None,
                severity=None, relax=None, hard_end=None, max_util=None):
    """One placement at one legality profile (place() runs one or two of these). `severity`:
    'strict', 'level_c' or 'board' (None: _severity_mode); `relax`: a relax_bodies mode that
    overrides the setting (the strict rung of the severity ladder runs with 'off'). The ladder's
    rungs only: `hard_end` (monotonic seconds) caps the stages that otherwise take a minimum
    time (escalation, final legalization, the closed loop and its diagnosis, the order and silk
    passes), so a rung ends in its share; `max_util`: return at once, with report['aborted'] and
    no poses, when the parts' occupancy on a side is over this fraction of the board (they
    cannot all fit)."""
    t0 = time.monotonic()

    def cap(s):     # a stage's time, within hard_end
        return s if hard_end is None else max(1.0, min(s, hard_end - time.monotonic()))

    def late():
        return hard_end is not None and time.monotonic() >= hard_end - 1.0
    log = log or (lambda *a, **k: None)
    workers = workers or _default_workers()
    rep = dict(seed=seed, time_s=time_s, physics=physics, workers=workers, stages={})

    def stage(name, t):
        rep["stages"][name] = round(time.monotonic() - t, 3)

    def trace(name, state):
        # physics after each stage that can move parts (anneal, legalize, the exact repairs),
        # so a physics-blind stage's cost shows in the report (audit P6)
        if report_terms is not None:
            physics_trace(rep, name, report_terms, {p.uuid: state.pose(p.i) for p in P.parts})

    # ---- brief (net roles for both arms; structures only with physics)
    t = time.monotonic()
    src = "given"
    if brief is None:
        try:
            brief, src = make_brief(board)
        except Exception as e:  # comprehension must not stop placement
            log(f"brief failed ({type(e).__name__}: {e}); placing without it")
            brief, src = {}, "none"
    rejected = getattr(board.rules, "dru_rejected", "") if board.rules else ""
    if rejected:   # kicad_file.read_rules: KiCad drops the file, so no custom rules apply
        rep["dru_rejected"] = rejected
        log(f"rules: KiCad drops the .kicad_dru ({rejected}); placing with net-class and board rules only")
    rep["brief"] = dict(source=src, structures=len((brief or {}).get("structures") or []),
                        labels=len((brief or {}).get("labels") or []))
    stage("brief", t)

    t = time.monotonic()
    # Footprints that carry Edge.Cuts but sit in the staging area: the task does not say where
    # the board edge they draw goes. Held where they are and reported (default), or, with
    # edge_mate, put where their open pieces close the outline exactly.
    mated = edges.mate(board, log=log) if edge_mate else {}
    if mated:
        rep["edge_mated"] = {u: list(p) for u, p in mated.items()}
    # Footprints carrying Edge.Cuts are fixed obstacles (spec-5 tasks keep them in place and
    # score moving them as illegal); staged ones cannot be placed: the board is flagged.
    held = [fp for fp in board.footprints if fp.edge_cuts and not fp.locked]
    staged = [fp for fp in held if not fp.on_board]
    if staged:
        rep["outline_incomplete"] = sorted(fp.ref for fp in staged)
        log(f"outline_incomplete: staged footprints carry Edge.Cuts ({', '.join(rep['outline_incomplete'][:8])}); "
            "held off the board, the board cannot be legal")
    # parts held at their input pose by the caller (kae place --fix / --fix-class: the board's
    # mechanical interface): fixed obstacles like locked parts, their nets still pulling
    fixed = set(fixed or ())
    if fixed:
        staged_fixed = sorted(fp.ref for fp in board.footprints if fp.uuid in fixed and not fp.on_board)
        rep["fixed"] = dict(n=len(fixed), refs=sorted(fp.ref for fp in board.footprints if fp.uuid in fixed)[:80])
        if staged_fixed:
            rep["fixed"]["staged"] = staged_fixed
            log(f"fixed parts off the board (they stay there): {', '.join(staged_fixed[:8])}")
    # user-facing connectors (USB, barrel, audio, RJ, video: on an edge on every human board,
    # kae.place.edge_check) the caller left free: pinned to the board edge, facing out, at the
    # free edge spot nearest their seed position, then held like fixed parts (audit P4)
    from kae.route.constraints import setting
    edge_mode = int(setting("connector_edge", board_path, opts))
    pinned = {}
    if edge_mode >= 2:
        board, pinned = _pin_edge_connectors(board, brief, held, fixed, angle_step, seed, rep, log)
        fixed = fixed | set(pinned)
    P = Problem.build(board, net_kinds=_net_kinds(brief), held={fp.uuid for fp in held} | fixed,
                      angle_step=angle_step, severity=severity or _severity_mode(board, board_path, opts))
    rep["severity"] = dict(mode=P.severity_mode, project_downgrades=dict(P.downgraded))
    rep["severity_used"] = P.severity_mode
    rep.setdefault("hazards", []).extend(P.severity_hazards())
    if fixed_text(board):
        # board-level copper text: KiCad's glyphs for the exact check (and the silk texts with
        # them, one pcbnew call)
        rep["silk_text"] = exactmod.refine_silk_text(P, log=log)
    if angle_step:
        rep["angle_step"] = angle_step
    # relax_bodies (kae-exact-legality.md, "Bodies"): 'escalate' (default, decide-ab tier 1) frees the
    # body of a part without a courtyard to its pads only when legalization or the floorplan fails;
    # 'off' keeps it as an obstacle always (10 pp less probe completion on 52 dense boards); 'auto' also up front on a board over 95% full (the old behaviour)
    from kae.route.constraints import setting
    relax_mode = str(relax or setting("relax_bodies", board_path, opts)).strip().lower()
    if relax_mode not in ("off", "escalate", "auto"):
        raise ValueError(f"relax_bodies {relax_mode!r}: 'off', 'escalate' or 'auto'")
    relax_ok = relax_mode != "off"
    rep["relax_bodies"] = relax_mode
    if relax_mode == "auto" and max(P.utilization()) > 0.95:
        rep["bodies_relaxed"] = P.relax_bodies()       # too full to treat bodies as obstacles
    from kae.route.constraints import setting
    margin = float(setting("place_margin", board_path, opts))
    if margin < 0:
        margin = P.auto_margin()
    else:
        rep["margin_set"] = margin
    P.set_margin(margin)
    # escape bands (kae.place.escape_band): 1 a soft annealer term against parts unrelated to the
    # package, 2 hard occupancy against every part, 0 off
    from . import escape_band as EB
    band_mode = int(setting("escape_band", board_path, opts))
    eb, rep["escape_bands"] = EB.bands(P, board_path, opts, log)
    ef = EB.fanout(P, board_path, opts, log)
    if ef:
        rep["escape_fanout"] = {P.parts[i].ref: len(rs) for i, rs in ef.items()}
    soft_bands = eb if band_mode == 1 else {}
    hard_bands = dict(eb) if band_mode >= 2 else {}
    # heat sinks (kae.place.heat): a part sink's body is hard occupancy on its side, like a band
    from . import heat as heatmod
    op = heatmod.operating(board_path, opts)
    if op:
        sb, rep["heat_sinks"] = heatmod.sink_bands(P, op)
        for i, b in sb.items():
            hard_bands[i] = tuple(max(x, y) for x, y in zip(hard_bands.get(i, (0.0, 0.0, 0.0, 0.0)), b))
    if hard_bands or ef:
        P.set_escape(hard_bands, fanout=ef)
    roles = _net_roles(brief)
    for net in P.nets:
        net.weight *= ROLE_WEIGHT.get(roles.get(net.name), 1.0)
    bparts = (brief or {}).get("parts") or {}
    for p in P.parts:
        p.kind = (bparts.get(p.uuid) or {}).get("kind", "")
    stage("problem", t)
    rep["problem"] = P.summary()
    if max_util is not None and max(rep["problem"].get("utilization") or [0.0]) > max_util:
        u = max(rep["problem"]["utilization"])
        rep["aborted"] = f"occupancy {u:.3f} of the board on a side, over {max_util:g}: the parts cannot all fit"
        log(f"{P.severity_mode}: {rep['aborted']}")
        rep["seconds"] = round(time.monotonic() - t0, 2)
        return Result(poses={}, report=rep, state=None, problem=P)
    n = len(P.mov)
    budget = plan_budget(time_s, n)
    rep["budget_s"] = round(budget, 1)
    deadline = t0 + budget
    log(f"problem: {n} movable, {len(P.parts) - n} fixed, {len(P.nets)} nets, grid {P.g} mm, budget {budget:.0f}s")
    if n == 0:
        st = State(P)
        rep.update(legal_grid=True, exact=exact_check(P, st))
        return Result(poses=dict(mated), report=rep, state=st, problem=P)

    # ---- physics: place terms (both arms report them; only the physics arm optimizes them),
    #      structures -> macros
    macros, terms, report_terms, order = [], None, None, []
    anneal_args = dict(anneal_args or {})
    terms_knobs = anneal_args.pop("terms_knobs", None) or {}
    seed_jitter = float(anneal_args.pop("seed_jitter", 0.0) or 0.0)
    t = time.monotonic()
    if not (brief or {}).get("structures"):
        tsrc = "none (no structures in the brief)"     # nothing to price: skip the build
        rep["scorecard"] = dict(total_linear=0.0, total=0.0, structures=0, over_budget=0)
        rep["scorecard_seed"] = dict(rep["scorecard"])
    else:
        try:
            # the annealer prices utilization linearly (no over-budget barrier) and saturates
            # it beyond 3x budget (log tail), so a structure far over budget for any
            # placement keeps a gradient without outbidding the rest. On the 7 split-B
            # boards with place terms x 2 seeds: linear scorecard 23.2 vs 23.6 with the
            # terms' own u_sat 10, same HPWL, buck hot loops 6.7 vs 8.0 nH (olimex, human
            # 5.9) and 1.70 vs 1.78 nH (noisecard)
            knobs = dict(u_sat=SA_U_SAT)
            knobs.update(terms_knobs)
            report_terms, tsrc = make_terms(board, brief, barrier=0.0, **knobs)
        except Exception as e:
            log(f"place terms failed ({type(e).__name__}: {e})")
            report_terms, tsrc = None, "none"
    stage("terms", t)
    if physics:
        t = time.monotonic()
        terms = report_terms
        structs = clusters.structures(P, brief)
        macros = clusters.build_macros(P, structs, time_s=min(0.1 * budget, 30.0), workers=workers,
                                       seed=seed, log=log, terms=terms)
        order = clusters.protection_order(P, brief)
        P.order_rules = order          # the closed loop's repair keeps them (kae.place.exact)
        rep["physics_terms"] = dict(source=tsrc, structures=len(structs), macros=len(macros),
                                    macro_sizes=[len(m.members) for m in macros], order_rules=len(order))
        # nets inside structures are critical: pull them together harder in the seed
        crit = set()
        for s in structs:
            for (ia, pa), (ib, pb), w in s.segs:
                for (i, pads) in ((ia, pa), (ib, pb)):
                    for k in pads:
                        j = P.parts[i].pad_net[k]
                        if j >= 0:
                            crit.add(j)
        for j in crit:
            if P.nets[j].kind == "signal":
                P.nets[j].weight *= 2.0
        stage("macros", t)
    net_w = {net.i: net.weight for net in P.nets}

    # ---- fixed copper zones (kae.place.zones): the seed's anchors and annealer's table (None
    # when off or nothing to price), and the report's (every part, both terms, any weights)
    t = time.monotonic()
    zone_pull = float(setting("zone_pull", board_path, opts))
    zone_keep = float(setting("zone_keepout", board_path, opts))
    zone_tab = zonesmod.build(P, pull=zone_pull, keepout=zone_keep) if (zone_pull > 0 or zone_keep > 0) else None
    zone_rep = zone_tab if (zone_tab is not None and zone_pull > 0 and zone_keep > 0) else zonesmod.build(P)
    stage("zones", t)

    # ---- seed: quadratic + spread, then CP-SAT floorplan
    t = time.monotonic()
    free_macros = [m for m in macros if not m.anchored]
    n_items = len(free_macros) + len(P.mov) - sum(len([i for i in m.members if P.parts[i].movable])
                                                   for m in free_macros)
    big = n_items > FLOORPLAN_MAX_ITEMS
    st, _ = _seed_state(P, free_macros, net_w, seed, log, partition=big, jitter=seed_jitter,
                        zones=zone_tab, zone_w=zone_pull)
    for mac in macros:
        if mac.anchored:   # members start at their layout around the locked anchor
            a = P.parts[mac.anchor]
            ax, ay = a.x0, a.y0
            for i, (dx, dy, k) in mac.layouts[0].offsets.items():
                if P.parts[i].movable:
                    X, Y = P.grid_of(ax + dx * P.g, ay + dy * P.g)
                    st.X[i], st.Y[i], st.K[i] = X, Y, k
    stage("seed_spread", t)
    t = time.monotonic()
    items = []
    in_macro = set()
    for mac in macros:
        if mac.anchored:
            continue
        a = mac.anchor
        it = clusters.macro_item(P, mac, int(st.X[a]), int(st.Y[a]), 0)
        items.append(it)
        in_macro.update(mac.members)
    for i in P.mov:
        if i not in in_macro:
            items.append(cpsat.single(P, i, int(st.X[i]), int(st.Y[i]), int(st.K[i])))
    sol, model = None, None
    retries = []
    if len(items) <= FLOORPLAN_MAX_ITEMS:
        # small boards: CP-SAT places everything at once (NoOverlap2D, 4 rotations, macros with
        # their layouts), minimizing weighted HPWL with a little displacement from the spread
        fp_time = max(2.0, 0.25 * (deadline - time.monotonic()))
        sol, model = seedmod.floorplan(P, items, fp_time, workers=workers, seed=seed, w_wl=1.0, w_disp=0.05,
                                       net_w=net_w, log=log)
        rep["floorplan"] = dict(status=model.status, seconds=round(model.wall, 2), items=len(items),
                                infeasible=model.infeasible_items)
        # a proven infeasibility (not a timeout) frees the macros, then shrinks the margin, then
        # lets bodies without courtyards overlap
        for m2 in ([margin] if macros else []) + [margin / 2, 0.0] + (["relax"] if relax_ok else []):
            if sol is not None or model.status != "INFEASIBLE":
                break
            if m2 == "relax":
                if not P.relax_bodies():
                    break
                rep["bodies_relaxed"] = True
                m2 = 0.0
            bands_dropped = False
            if m2 == 0.0 and getattr(P, "escape_on", False):
                P.set_escape(P.escape, on=False)        # the bands go with the margin
                rep["escape_bands_dropped"] = "floorplan infeasible"
                bands_dropped = True
            if m2 < P.margin or (m2 == P.margin and (macros or rep.get("bodies_relaxed") or bands_dropped)):
                P.set_margin(m2)
                items = [cpsat.single(P, i, int(st.X[i]), int(st.Y[i]), int(st.K[i])) for i in P.mov]
                sol, model = seedmod.floorplan(P, items, max(2.0, 0.15 * (deadline - time.monotonic())),
                                               workers=workers, seed=seed, w_wl=1.0, w_disp=0.05,
                                               net_w=net_w, log=log)
                retries.append(dict(margin=m2, status=model.status, seconds=round(model.wall, 2)))
    else:
        rep["floorplan"] = dict(status="skipped", items=len(items),
                                reason=f"more than {FLOORPLAN_MAX_ITEMS} items: windowed legalization of the spread")
    if retries:
        rep["floorplan_retry"] = retries
    if sol is not None:
        for it, (X, Y, v) in zip(items, sol):
            for i, (dx, dy, k) in it.variants[v].items():
                if P.parts[i].movable:
                    st.X[i], st.Y[i], st.K[i] = X + dx, Y + dy, k
    stage("floorplan", t)
    viol = grid_violations(st)
    if viol:
        t = time.monotonic()
        # big boards: the bisection spread is density-feasible, so the greedy fit does it
        # (windows would spend the budget on hundreds of small overlaps)
        rep["legalize_seed"] = legalize(P, st, time_s=max(3.0, 0.15 * (deadline - time.monotonic())),
                                        workers=workers, seed=seed, log=log, window_share=0.0 if big else 0.6)
        if grid_violations(st):
            rep["legalize_seed_escalation"] = _escalate(P, st, workers, seed, log, max(3.0, 0.1 * budget), relax_ok,
                                                        hard_end=hard_end)
        stage("legalize_seed", t)
    if big and not grid_violations(st) and time.monotonic() < deadline - 0.5 * budget:
        # big boards: CP-SAT floorplans region by region (the global one stops at
        # FLOORPLAN_MAX_ITEMS); legal in, legal out
        t = time.monotonic()
        rep["regional_floorplan"] = seedmod.regional_refine(
            P, st, free_macros, net_w, time_s=min(60.0, 0.15 * (deadline - time.monotonic())), workers=workers,
            seed=seed, log=log, hold=getattr(P, "zone_pinned", ()))
        stage("regional_floorplan", t)
    seed_state = st.copy()
    seed_legal = not grid_violations(seed_state)
    rep["seed"] = dict(legal=seed_legal, hpwl=round(st.hpwl(), 2))

    if zone_rep is not None:
        rep["zones_seed"] = _zone_summary(zonesmod.report(P, seed_state, zone_rep))
    # nets the seed left across a void or an all-layer keepout pull harder in the annealer (kae.place.barriers)
    from . import barriers as barriersmod
    w_bar = float(setting("barrier_net_weight", board_path, opts))
    if w_bar > 1.0:
        rep["barrier_reweight"] = barriersmod.reweight_crossing(P, seed_state, w_bar)
    # ---- anneal
    final = seed_state
    if anneal:
        t = time.monotonic()
        kw = dict(w_phys=1.0 if terms is not None else 0.0, order=order,
                  w_cong=float(setting("place_w_cong", board_path, opts)))
        kw.update(anneal_args or {})
        if terms is None:
            kw["w_phys"] = 0.0
        rep["w_cong"] = float(kw.get("w_cong", 0.0) or 0.0)
        # parts named by board silk labels beside their label: by default the kinds validated on
        # the human placements (numbered rows) at a modest weight; anneal_args w_label and
        # label_kinds widen or switch it off (w_label 0)
        from . import labels as labelsmod
        kinds = tuple(kw.pop("label_kinds", None) or ((labelsmod.KINDS if "w_label" in (anneal_args or {})
                                                        else labelsmod.DEFAULT_KINDS)))
        kw.setdefault("w_label", labelsmod.DEFAULT_WEIGHT)
        assoc = (brief or {}).get("labels") or []
        if float(kw["w_label"] or 0.0) > 0 and assoc:
            kw["labels"] = labelsmod.anchors(P, assoc, kinds=kinds)
            if kw["labels"]:
                rep["labels"] = dict(associations=len(assoc), kinds=list(kinds), anchored=len(kw["labels"]),
                                     w_label=kw["w_label"])
        # hot parts into region sinks (kae.place.heat), on the same term; a labelled part keeps its label
        if op:
            pulls, rep["heat_pulls"] = heatmod.pull_anchors(P, op, board_path, opts)
            if pulls:
                lab = dict(kw.get("labels") or {})
                for i_, a_ in pulls.items():
                    lab.setdefault(i_, a_)
                kw["labels"] = lab
                if not float(kw.get("w_label") or 0.0) > 0:
                    kw["w_label"] = labelsmod.DEFAULT_WEIGHT
        # soft overlaps: silkscreen where the project makes it an error (on KiCad's glyphs) and
        # routing channels between parts' pads (kae.place.exact.channel_grid)
        w_silk = float(kw.pop("w_silk", SILK_W) or 0.0)
        w_chan = float(kw.pop("w_chan", CHAN_W) or 0.0)
        grids = []
        if exactmod.silk_on(P) and w_silk > 0:
            if "silk_text" not in rep:
                rep["silk_text"] = exactmod.refine_silk_text(P, log=log)
            grids.append(exactmod.silk_grid(P, weight=w_silk))
            rep["silk_term"] = dict(parts=len(grids[-1]), w_silk=w_silk)
        if w_chan > 0:
            grids.append(exactmod.channel_grid(P, weight=w_chan))
            rep["channel_term"] = dict(parts=len(grids[-1]), w_chan=w_chan)
        if soft_bands:
            w_band = float(setting("escape_band_w", board_path, opts))
            grids.append(EB.escape_grid(P, soft_bands, weight=w_band))
            rep["escape_term"] = dict(packages=len(soft_bands), parts=len(grids[-1]), w_band=w_band)
        if grids:
            kw["silk"] = exactmod.soft_grid(*grids)
            kw["w_silk"] = 1.0
        # the board's fixed copper zones (kae.place.zones): pads over their own nets' zones,
        # other nets' pads out of outer zones they would bridge
        if zone_tab is not None and float(kw.get("w_zone", 1.0) or 0.0) > 0:
            kw.setdefault("w_zone", 1.0)
            kw["zones"] = zone_tab
            rep["zone_term"] = dict(zone_tab.info, w_zone=kw["w_zone"])
        ann = make_annealer(P, st.copy(), terms=terms, macros=[m for m in macros if not m.anchored], seed=seed,
                            log=log, **kw)
        if anneal_args:
            rep["anneal_args"] = dict(anneal_args)
        seed_cost = ann.cost(ann.lam1) if seed_legal else None
        seed_terms = ann.terms_report()
        cpu = max(1.0, 0.6 * (deadline - time.monotonic() - 3.0))
        # wall clock too: on a loaded host CPU seconds lag behind the caller's timeout
        arep = ann.run(cpu_s=cpu, deadline=deadline - 0.1 * budget)
        ann.write_back()
        rep["anneal"] = arep
        stage("anneal", t)
        t = time.monotonic()
        cand = ann.st
        trace("seed", seed_state)
        trace("anneal", cand)
        if grid_violations(cand):
            rep["legalize"] = legalize(P, cand, time_s=max(3.0, deadline - time.monotonic()), workers=workers,
                                       seed=seed, log=log)
            trace("legalize", cand)
        stage("legalize", t)
        if not grid_violations(cand):
            # cost of the legal candidate, same weights and normalization as the seed's
            cand_cost, cand_terms = ann.evaluate(cand)
            rep["anneal_cost"] = dict(seed=None if seed_cost is None else round(seed_cost, 5),
                                      annealed=round(cand_cost, 5), seed_terms=seed_terms, annealed_terms=cand_terms)
            if seed_cost is None or cand_cost <= seed_cost + 1e-9 or not seed_legal:
                final = cand
            else:
                rep["anneal_kept_seed"] = True
        elif not seed_legal:
            final = cand
    st = final
    viol = grid_violations(st)
    if viol:
        rep["legalize_escalation"] = _escalate(P, st, workers, seed, log, max(3.0, 0.1 * budget), relax_ok,
                                               hard_end=hard_end)
        viol = grid_violations(st)
    if viol and (P.margin > 0 or getattr(P, "escape_on", False)):
        # the routing margin and the escape bands are wishes, legality is not: judge (and repair)
        # without them
        if getattr(P, "escape_on", False):
            P.set_escape(P.escape, on=False)
            rep["escape_bands_dropped"] = "final legality"
        P.set_margin(0.0)
        rep["margin_dropped"] = True
        viol = grid_violations(st)
    if viol and time.monotonic() < deadline + 0.1 * budget and not late():
        rep["legalize_final"] = legalize(P, st, time_s=cap(max(3.0, 0.1 * budget)), workers=workers, seed=seed,
                                         log=log)
        viol = grid_violations(st)
    if rep.get("legalize_escalation") or rep.get("legalize_final"):
        trace("legalize_escalation", st)
    rep["legal_grid"] = not viol
    rep["margin_mm"] = P.margin
    t = time.monotonic()
    rep["exact"] = exact_check(P, st)
    stage("exact_check", t)
    if rep["exact"]:
        # closed loop: legality is not a score; repair against the exact check until it is
        # clean or the caller's time (less the writer's share) is up, then say why not
        t = time.monotonic()
        # leave the KiCad DRC its share (kae.cli runs it on the written board): ~0.1 s a part
        reserve = min(0.2 * float(time_s), 5.0 + 0.1 * len(P.parts))
        left = max(5.0, t0 + 0.9 * float(time_s) - 15.0 - reserve - t)
        if hard_end is None:
            rep["closed_loop"] = exactmod.close_loop(P, st, time_s=left, log=log)
        else:
            rep["closed_loop"] = exactmod.close_loop(P, st, time_s=cap(left), log=log, deadline=hard_end)
        rep["exact"] = exact_check(P, st)
        stage("closed_loop", t)
        trace("closed_loop", st)
    if order and not late():
        # protection-order rules an annealer cut short left broken: the protection part to the
        # nearest clean spot that keeps them, the physics total bounded (kae.place.exact)
        t = time.monotonic()
        reserve = min(0.2 * float(time_s), 5.0 + 0.1 * len(P.parts))
        # a few seconds even when the stages ran over (a loaded host is when it is needed)
        left = cap(max(5.0, min(0.05 * budget + 5.0, t0 + 0.9 * float(time_s) - 15.0 - reserve - t)))
        phys = None
        if report_terms is not None:
            def phys():
                return physics_summary(report_terms, {p.uuid: st.pose(p.i) for p in P.parts},
                                       breakdown=False)["total_linear"]
        try:
            rep["order_fix"] = exactmod.fix_order(P, st, time_s=left, phys=phys, log=log)
        except Exception as e:      # noqa: BLE001 - a polish pass; never lose the placement
            rep["order_fix"] = dict(error=f"{type(e).__name__}: {e}")
        if rep["order_fix"].get("moved"):
            rep["exact"] = exact_check(P, st)
            trace("order_fix", st)
        stage("order_fix", t)
    if exactmod.silk_on(P) and not late():
        # silkscreen where the project makes it an error: a soft pass, legality kept
        t = time.monotonic()
        if "silk_text" not in rep:
            rep["silk_text"] = exactmod.refine_silk_text(P, log=log)
        reserve = min(0.2 * float(time_s), 5.0 + 0.1 * len(P.parts))
        left = cap(max(5.0, min(0.15 * budget + 10.0, t0 + 0.9 * float(time_s) - 15.0 - reserve - t)))
        phys = None
        if report_terms is not None:
            def phys():
                return physics_summary(report_terms, {p.uuid: st.pose(p.i) for p in P.parts},
                                       breakdown=False)["total_linear"]
        try:
            rep["silk_fix"] = exactmod.fix_silk(P, st, time_s=left, phys=phys, log=log)
        except Exception as e:      # noqa: BLE001 - a polish pass; never lose the placement
            rep["silk_fix"] = dict(error=f"{type(e).__name__}: {e}")
        if rep["silk_fix"].get("moved"):
            rep["exact"] = exact_check(P, st)
            trace("silk_fix", st)
        stage("silk_fix", t)
    rep.update(grid_verdict(P, st, rep["exact"]))
    body_hazards(rep, P, st)
    if zone_rep is not None:
        rep["zones"] = zonesmod.report(P, st, zone_rep)
    rep["barrier_crossings"] = barriersmod.crossings(P, st)
    rep["hpwl"] = round(st.hpwl(), 2)
    rep["hpwl_signal"] = round(st.hpwl(signal_only=True), 2)
    res = Result(poses={}, report=rep, state=st, problem=P, terms=report_terms, order=order, brief=brief)
    final_physics(res)
    if report_terms is not None and "physics_error" not in rep:
        try:
            rep["scorecard_seed"] = physics_summary(report_terms, {p.uuid: seed_state.pose(p.i) for p in P.parts},
                                                    breakdown=False)
        except Exception as e:
            rep["physics_error"] = f"{type(e).__name__}: {e}"
    rep["seconds"] = round(time.monotonic() - t0, 2)
    poses = st.poses()
    poses.update(mated)          # held fixed here, but movable in the file: write them too
    poses.update(pinned)
    res.poses = poses
    if edge_mode >= 1:
        edge_hazards(rep, board, poses)
    return res


def _zone_summary(r):
    return {k: v for k, v in r.items() if k != "by_net"}


def _pin_edge_connectors(board, brief, held, fixed, angle_step, seed, rep, log):
    """The edge connectors' poses from a quick seed (quadratic with connector anchors, spread)
    on a throwaway Problem; returns (board with them moved there, {uuid: pose})."""
    from . import edge_check
    want = {u for u in edge_check.edge_parts(board, edge_check.PIN_KINDS)
            if u not in fixed and not any(fp.uuid == u and fp.locked for fp in board.footprints)}
    if not want:
        return board, {}
    try:
        P0 = Problem.build(board, net_kinds=_net_kinds(brief), held={fp.uuid for fp in held} | set(fixed),
                           angle_step=angle_step)
        idx = [p.i for p in P0.parts if p.movable and p.uuid in want]
        if not idx:
            return board, {}
        net_w = {net.i: net.weight for net in P0.nets}
        st0, _ = _seed_state(P0, [], net_w, seed, log, partition=len(P0.mov) > FLOORPLAN_MAX_ITEMS)
        poses, failed = edge_check.pin_poses(P0, st0, idx, log=log)
    except Exception as e:      # noqa: BLE001 - placing without the pin beats not placing
        rep["edge_pinned"] = dict(error=f"{type(e).__name__}: {e}")
        return board, {}
    by = {fp.uuid: fp.ref for fp in board.footprints}
    rep["edge_pinned"] = dict(pinned=sorted(by[u] for u in poses), failed=failed, uuids=sorted(poses))
    return (edge_check.with_poses(board, poses) if poses else board), poses


def edge_hazards(rep, board, poses):
    """rep['hazards'] gets a connector_off_edge entry for each user-facing connector kae placed
    (`poses`: {uuid: pose} of the parts kae moved) away from the board edge
    (kae.place.edge_check; audit P4). Earlier entries of that code are replaced, so a caller that
    moved parts again (the KiCad loop) calls it again."""
    from . import edge_check
    hz = [h for h in rep.get("hazards", []) if h.get("code") != "connector_off_edge"]
    try:
        hz += edge_check.hazards(board, moved=set(poses), poses=poses)
    except Exception as e:      # noqa: BLE001 - a check must not cost the placement
        hz.append(dict(code="edge_check_failed", severity="info", category="data",
                       message=f"the connector edge check failed ({type(e).__name__}: {e})", objects=[]))
    if hz:
        rep["hazards"] = hz


def physics_trace(rep, name, terms, poses):
    """Append the physics after stage `name` to rep['physics_trace']: the linear total and the
    utilization summed per structure kind (decap loops, crystals, ...). Never raises: a
    diagnostic must not cost the placement."""
    try:
        rows = terms.breakdown(poses)
        kinds = {}
        for r in rows:
            u = float(r.get("confidence", 1.0)) * float(r.get("util", r.get("utilization", 0.0)))
            k = str(r.get("kind"))
            kinds[k] = round(kinds.get(k, 0.0) + u, 4)
        rep.setdefault("physics_trace", []).append(
            dict(stage=name, total_linear=round(sum(kinds.values()), 4), by_kind=kinds))
    except Exception as e:      # noqa: BLE001
        rep.setdefault("physics_trace", []).append(dict(stage=name, error=f"{type(e).__name__}: {e}"))


def final_physics(res):
    """The report's protection_order and scorecard for where res.state stands now (place()
    at its end; kae.cli again after a KiCad DRC round moved parts)."""
    P, st, rep = res.problem, res.state, res.report
    if res.order:
        chk = Annealer(P, st.copy(), terms=None, w_cong=0.0, order=res.order)
        rep["protection_order"] = dict(rules=len(res.order), violated=chk.order_violations())
    if res.terms is not None:
        try:
            rep["scorecard"] = physics_summary(res.terms, {p.uuid: st.pose(p.i) for p in P.parts})
            # the scorecard's hazards at the top, once (source "scorecard"): a second call, after the
            # KiCad rounds moved parts, replaces the first call's, which describe poses no longer written
            sc_hz = [dict(h, source="scorecard") for h in rep["scorecard"].pop("hazards", None) or []]
            rep["hazards"] = [h for h in rep.get("hazards", []) if h.get("source") != "scorecard"] + sc_hz
        except Exception as e:
            rep["physics_error"] = f"{type(e).__name__}: {e}"


def grid_verdict(P, st, exact):
    """The grid model is a conservative prefilter (bodies stand in for missing courtyards,
    rectangles round outward to cells, pads carry clearance and mask room, courtyards stay
    inside the outline); KiCad judges copper, holes and courtyards. legal_grid: no grid
    violator the exact check confirms; grid_conservative: violators only the grid sees, by
    class (no courtyard, relaxed, other)."""
    gv = set(grid_violations(st))
    confirmed = {q for v in exact or [] for q in v.get("parts", [])}
    only = sorted(gv - confirmed)
    cls = {}
    for i in only:
        p = P.parts[i]
        k = "no_courtyard" if not p.has_courtyard else "relaxed" if getattr(p, "relaxed", False) else "rounding"
        cls.setdefault(k, []).append(p.ref)
    return dict(legal_grid=not (gv & confirmed),
                grid_conservative=dict(count=len(only), by_class={k: v[:10] for k, v in cls.items()}))


def local_replace(board, parts, window_mm=None, time_s=30.0, seed=0, physics=True, brief=None, log=None,
                  angle_step=None, workers=1, net_weights=None, cong_history=None, moves_per_part=None):
    """Re-place only `parts` (footprint uuids or references) of an already placed board,
    inside `window_mm` = (x0, y0, x1, y1) when given, with every other footprint where it is
    (fixed geometry and fixed pins): the module and joint loops' local re-placement after
    routing. `net_weights` {net name: factor} scales nets' wirelength weights (routing
    feedback: an unrouted or detoured net pulls its pins together harder). `cong_history`:
    callable (x0, y0, b, nbx, nby) -> (nbx, nby) array added to the congestion bins' static
    demand (Congestion.Dp; track mm per bin, Congestion.S0 a bin's empty-board supply).
    `moves_per_part`: a fixed move budget (moves_per_part x len(parts)) instead of the
    clock, so a windowed re-place is deterministic under load. Ends exactly
    legal for the moved parts when it can (kae.place.exact.repair, only `parts` move).
    Returns Result(poses of the re-placed parts, report, state, problem)."""
    t0 = time.monotonic()
    log = log or (lambda *a, **k: None)
    if brief is None:
        try:
            brief, _ = make_brief(board)
        except Exception:
            brief = {}
    want = set(parts)
    # every other footprint is locked (as joint.replace.window_board does): left movable it
    # was modeled snapped to the grid and to a right angle (a part at 45 deg as 0 deg), so the
    # re-placed parts were judged against neighbours that are not where the board has them
    import dataclasses
    board_w = dataclasses.replace(board, footprints=[
        fp if (fp.locked or fp.uuid in want or fp.ref in want) else dataclasses.replace(fp, locked=True)
        for fp in board.footprints])
    P = Problem.build(board_w, net_kinds=_net_kinds(brief), angle_step=angle_step)
    P.set_margin(0.0)
    sub = [p.i for p in P.parts if p.movable and (p.uuid in want or p.ref in want)]
    st = State(P)
    for p in P.parts:
        if not p.movable:
            continue
        X, Y = P.grid_of(p.x0, p.y0)
        rots = [r.rot for r in p.rots]
        k = min(range(len(rots)), key=lambda kk: min(abs(rots[kk] - p.rot0) % 360, 360 - abs(rots[kk] - p.rot0) % 360))
        st.X[p.i], st.Y[p.i], st.K[p.i] = X, Y, k
    window = None
    if window_mm is not None:
        x0, y0, x1, y1 = window_mm
        window = (int(math.floor((x0 - P.ox) / P.g)), int(math.ceil((x1 - P.ox) / P.g)),
                  int(math.floor((y0 - P.oy) / P.g)), int(math.ceil((y1 - P.oy) / P.g)))
    terms = None
    if physics and (brief or {}).get("structures"):
        try:
            terms, _ = make_terms(board, brief, barrier=0.0, u_sat=SA_U_SAT)
        except Exception as e:
            log(f"place terms failed ({type(e).__name__}: {e})")
    order = clusters.protection_order(P, brief) if physics else []
    P.order_rules = order          # the closed loop's repair keeps them (kae.place.exact)
    for net in P.nets:
        net.weight *= float((net_weights or {}).get(net.name, 1.0))
    rep = dict(parts=[P.parts[i].ref for i in sub], window=window)
    if sub:
        ann = make_annealer(P, st.copy(), terms=terms, seed=seed, w_phys=1.0 if terms is not None else 0.0,
                            order=order, subset=sub, window=window, log=log, cong_history=cong_history,
                            **zonesmod.annealer_args(P))
        if moves_per_part:
            rep["anneal"] = ann.run(cpu_s=1e9, max_moves=int(moves_per_part) * len(sub), deadline=None)
        else:
            rep["anneal"] = ann.run(cpu_s=max(0.5, 0.8 * time_s), deadline=t0 + 0.85 * time_s)
        rep["anneal"]["cong_history"] = getattr(getattr(ann, "ann", ann), "cong_history", None)
        ann.write_back()
        st = ann.st
        bad = [i for i in grid_violations(st) if i in set(sub)]
        if bad:
            rep["greedy"] = greedy_subset(P, st, bad, log)
        rep["exact"] = exact_check(P, st, parts=sub)
        if rep["exact"]:
            left = max(2.0, t0 + time_s - time.monotonic())
            rep["closed_loop"] = exactmod.repair(P, st, time_s=left, log=log, allowed=set(sub))
            rep["closed_loop"].pop("findings", None)
            rep["exact"] = exact_check(P, st, parts=sub)
        gv = grid_verdict(P, st, rep["exact"])
        rep["legal_grid"] = gv["legal_grid"]
        rep["grid_conservative"] = gv["grid_conservative"]
    rep["seconds"] = round(time.monotonic() - t0, 2)
    poses = {P.parts[i].uuid: st.pose(i) for i in sub}
    return Result(poses=poses, report=rep, state=st, problem=P)


def greedy_subset(P, st, parts, log=None):
    from .legalize import greedy
    return greedy(P, st, parts, log=log)
