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

from . import clusters, cpsat, edges, seed as seedmod
from .anneal import Annealer, make_annealer
from . import exact as exactmod
from .legalize import exact_check, legalize
from .problem import Problem
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


SA_U_SAT = 3.0   # see place(): utilization saturates beyond this in the annealer's terms


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


def _escalate(P, st, workers, seed, log, time_s):
    """Legality before wishes: drop the routing margin, then let bodies without courtyards
    overlap (KiCad does not check them), legalizing again after each step. Returns the steps
    taken with what each left illegal."""
    steps = []
    for step in ("margin 0", "bodies relaxed"):
        if not grid_violations(st):
            break
        if step == "margin 0":
            if P.margin <= 0:
                continue
            P.set_margin(0.0)
        elif not P.relax_bodies():
            continue
        r = legalize(P, st, time_s=time_s, workers=workers, seed=seed, log=log, window_share=0.5)
        steps.append(dict(step=step, end_violators=r.get("end_violators"), violations=r.get("violations")))
        if log:
            log(f"escalation: {step}, {r.get('end_violators')} parts still illegal")
    return steps


def _seed_state(P, macros, net_w, seed, log, partition=False):
    """Quadratic + spread: an initial state (macros at their best layout). `partition`
    spreads by recursive bisection of the free cells (density-feasible, for big boards)
    instead of pairwise repulsion."""
    objs, owner = seedmod._objects(P, macros)
    pos = seedmod.quadratic(P, objs, owner, net_w)
    # connectors are anchors: pinned inside the nearest edge, then the rest re-solved
    wmax = max([net_w.get(net.i, net.weight) for net in P.nets] or [1.0])
    anchors = seedmod.connector_anchors(P, objs, pos, weight=5.0 * wmax)
    if anchors:
        pos = seedmod.quadratic(P, objs, owner, net_w, anchors=anchors)
    if partition:
        pos = seedmod.partition_spread(P, objs, pos)
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
    return st, objs


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
    if breakdown:
        out["breakdown"] = [dict(id=r.get("id"), kind=r.get("kind"), util=round(float(r.get("util", r.get("utilization", 0.0))), 4),
                                 value=round(float(r.get("value", 0.0)), 4), unit=r.get("unit"),
                                 members=r.get("members", [])[:8]) for r in rows[:40]]
    return out


def place(board, seed=0, time_s=300.0, physics=True, brief=None, workers=None, log=None, anneal=True,
          edge_mate=False, anneal_args=None, angle_step=None):
    t0 = time.monotonic()
    log = log or (lambda *a, **k: None)
    workers = workers or _default_workers()
    rep = dict(seed=seed, time_s=time_s, physics=physics, workers=workers, stages={})

    def stage(name, t):
        rep["stages"][name] = round(time.monotonic() - t, 3)

    # ---- brief (net roles for both arms; structures only with physics)
    t = time.monotonic()
    src = "given"
    if brief is None:
        try:
            brief, src = make_brief(board)
        except Exception as e:  # comprehension must not stop placement
            log(f"brief failed ({type(e).__name__}: {e}); placing without it")
            brief, src = {}, "none"
    rep["brief"] = dict(source=src, structures=len((brief or {}).get("structures") or []))
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
    P = Problem.build(board, net_kinds=_net_kinds(brief), held={fp.uuid for fp in held}, angle_step=angle_step)
    if angle_step:
        rep["angle_step"] = angle_step
    if max(P.utilization()) > 0.95:
        rep["bodies_relaxed"] = P.relax_bodies()       # too full to treat bodies as obstacles
    margin = P.auto_margin()
    P.set_margin(margin)
    roles = _net_roles(brief)
    for net in P.nets:
        net.weight *= ROLE_WEIGHT.get(roles.get(net.name), 1.0)
    bparts = (brief or {}).get("parts") or {}
    for p in P.parts:
        p.kind = (bparts.get(p.uuid) or {}).get("kind", "")
    stage("problem", t)
    rep["problem"] = P.summary()
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

    # ---- seed: quadratic + spread, then CP-SAT floorplan
    t = time.monotonic()
    free_macros = [m for m in macros if not m.anchored]
    n_items = len(free_macros) + len(P.mov) - sum(len([i for i in m.members if P.parts[i].movable])
                                                   for m in free_macros)
    big = n_items > FLOORPLAN_MAX_ITEMS
    st, _ = _seed_state(P, free_macros, net_w, seed, log, partition=big)
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
        for m2 in ([margin] if macros else []) + [margin / 2, 0.0, "relax"]:
            if sol is not None or model.status != "INFEASIBLE":
                break
            if m2 == "relax":
                if not P.relax_bodies():
                    break
                rep["bodies_relaxed"] = True
                m2 = 0.0
            if m2 < P.margin or (m2 == P.margin and (macros or rep.get("bodies_relaxed"))):
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
            rep["legalize_seed_escalation"] = _escalate(P, st, workers, seed, log, max(3.0, 0.1 * budget))
        stage("legalize_seed", t)
    if big and not grid_violations(st) and time.monotonic() < deadline - 0.5 * budget:
        # big boards: CP-SAT floorplans region by region (the global one stops at
        # FLOORPLAN_MAX_ITEMS); legal in, legal out
        t = time.monotonic()
        rep["regional_floorplan"] = seedmod.regional_refine(
            P, st, free_macros, net_w, time_s=min(60.0, 0.15 * (deadline - time.monotonic())), workers=workers,
            seed=seed, log=log)
        stage("regional_floorplan", t)
    seed_state = st.copy()
    seed_legal = not grid_violations(seed_state)
    rep["seed"] = dict(legal=seed_legal, hpwl=round(st.hpwl(), 2))

    # ---- anneal
    final = seed_state
    if anneal:
        t = time.monotonic()
        kw = dict(w_phys=1.0 if terms is not None else 0.0, order=order)
        kw.update(anneal_args or {})
        if terms is None:
            kw["w_phys"] = 0.0
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
        if grid_violations(cand):
            rep["legalize"] = legalize(P, cand, time_s=max(3.0, deadline - time.monotonic()), workers=workers,
                                       seed=seed, log=log)
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
        rep["legalize_escalation"] = _escalate(P, st, workers, seed, log, max(3.0, 0.1 * budget))
        viol = grid_violations(st)
    if viol and P.margin > 0:
        # the routing margin is a wish, legality is not: judge (and repair) without it
        P.set_margin(0.0)
        rep["margin_dropped"] = True
        viol = grid_violations(st)
    if viol and time.monotonic() < deadline + 0.1 * budget:
        rep["legalize_final"] = legalize(P, st, time_s=max(3.0, 0.1 * budget), workers=workers, seed=seed, log=log)
        viol = grid_violations(st)
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
        rep["closed_loop"] = exactmod.close_loop(P, st, time_s=left, log=log)
        rep["exact"] = exact_check(P, st)
        stage("closed_loop", t)
    if order:
        # protection-order rules an annealer cut short left broken: the protection part to the
        # nearest clean spot that keeps them, the physics total bounded (kae.place.exact)
        t = time.monotonic()
        reserve = min(0.2 * float(time_s), 5.0 + 0.1 * len(P.parts))
        # a few seconds even when the stages ran over (a loaded host is when it is needed)
        left = max(5.0, min(0.05 * budget + 5.0, t0 + 0.9 * float(time_s) - 15.0 - reserve - t))
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
        stage("order_fix", t)
    rep.update(grid_verdict(P, st, rep["exact"]))
    rep["hpwl"] = round(st.hpwl(), 2)
    rep["hpwl_signal"] = round(st.hpwl(signal_only=True), 2)
    res = Result(poses={}, report=rep, state=st, problem=P, terms=report_terms, order=order)
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
    res.poses = poses
    return res


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
    P = Problem.build(board, net_kinds=_net_kinds(brief), angle_step=angle_step)
    P.set_margin(0.0)
    want = set(parts)
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
                            order=order, subset=sub, window=window, log=log, cong_history=cong_history)
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
