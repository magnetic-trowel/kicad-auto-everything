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
4. Anneal (kae.place.anneal): physics + routability + legality ramp + displacement.
5. Legalize (kae.place.legalize): windowed CP-SAT, then the exact polygon check. The
   annealed result is kept only if it is grid-legal after legalization and does not cost
   more than the legal seed; otherwise the seed is returned.

Budgets: `time_s` is the wall time the caller allows (kaebench's --timeout). The pipeline
plans to finish in min(0.85 * time_s - 10, 20 s + 3 s per movable part), so small boards
do not idle away a long timeout. The annealer budgets CPU seconds; CP-SAT stages wall
seconds with `workers` threads.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field

from . import clusters, cpsat, seed as seedmod
from .anneal import Annealer
from .legalize import exact_check, legalize
from .problem import Problem
from .state import State, grid_violations
from .stubs import make_brief, make_terms

ROLE_KIND = {"ground": "ground", "rail": "power", "power": "power"}
ROLE_WEIGHT = {"clock": 1.5, "high_speed": 1.5, "analog": 1.2, "rf": 1.5, "switch_node": 1.0}


@dataclass
class Result:
    poses: dict
    report: dict = field(default_factory=dict)
    state: object = None
    problem: object = None


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


def _seed_state(P, macros, net_w, seed, log):
    """Quadratic + spread: an initial state (macros at their best layout)."""
    objs, owner = seedmod._objects(P, macros)
    pos = seedmod.quadratic(P, objs, owner, net_w)
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


def _cost(ann_like):
    return ann_like.cost(ann_like.lam1)


def place(board, seed=0, time_s=300.0, physics=True, brief=None, workers=None, log=None, anneal=True):
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
    P = Problem.build(board, net_kinds=_net_kinds(brief))
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
        rep.update(legal_grid=True, exact=[])
        return Result(poses={}, report=rep, state=st, problem=P)

    # ---- physics: structures -> macros, place terms
    macros, terms = [], None
    if physics:
        t = time.monotonic()
        structs = clusters.structures(P, brief)
        macros = clusters.build_macros(P, structs, time_s=min(0.1 * budget, 30.0), workers=workers,
                                       seed=seed, log=log)
        try:
            terms, tsrc = make_terms(board, brief)
        except Exception as e:
            log(f"place terms failed ({type(e).__name__}: {e}); physics proxy off")
            terms, tsrc = None, "none"
        rep["physics_terms"] = dict(source=tsrc, structures=len(structs), macros=len(macros),
                                    macro_sizes=[len(m.members) for m in macros])
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
    st, _ = _seed_state(P, [m for m in macros if not m.anchored], net_w, seed, log)
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
    fp_time = max(2.0, 0.25 * (deadline - time.monotonic()))
    w_wl = 1.0 if n <= 150 else 0.0
    sol, model = seedmod.floorplan(P, items, fp_time, workers=workers, seed=seed, w_wl=w_wl,
                                   w_disp=0.05 if w_wl else 1.0, net_w=net_w, log=log)
    rep["floorplan"] = dict(status=model.status, seconds=round(model.wall, 2), items=len(items),
                            infeasible=model.infeasible_items)
    if sol is None and macros:
        # macros may not fit as rigid blocks: free their members
        log("floorplan with macros failed; retrying with single parts")
        items = [cpsat.single(P, i, int(st.X[i]), int(st.Y[i]), int(st.K[i])) for i in P.mov]
        sol, model = seedmod.floorplan(P, items, max(2.0, 0.2 * (deadline - time.monotonic())), workers=workers,
                                       seed=seed, w_wl=w_wl, w_disp=0.05 if w_wl else 1.0, net_w=net_w, log=log)
        rep["floorplan_retry"] = dict(status=model.status, seconds=round(model.wall, 2))
    if sol is not None:
        for it, (X, Y, v) in zip(items, sol):
            for i, (dx, dy, k) in it.variants[v].items():
                if P.parts[i].movable:
                    st.X[i], st.Y[i], st.K[i] = X + dx, Y + dy, k
    stage("floorplan", t)
    viol = grid_violations(st)
    if viol:
        t = time.monotonic()
        rep["legalize_seed"] = legalize(P, st, time_s=max(3.0, 0.15 * (deadline - time.monotonic())),
                                        workers=workers, seed=seed, log=log)
        stage("legalize_seed", t)
    seed_state = st.copy()
    seed_legal = not grid_violations(seed_state)
    rep["seed"] = dict(legal=seed_legal, hpwl=round(st.hpwl(), 2))

    # ---- anneal
    final = seed_state
    if anneal:
        t = time.monotonic()
        ann = Annealer(P, st.copy(), terms=terms, macros=[m for m in macros if not m.anchored], seed=seed,
                       w_phys=1.0 if terms is not None else 0.0, log=log)
        seed_cost = ann.cost(ann.lam1) if seed_legal else None
        seed_terms = ann.terms_report()
        cpu = max(1.0, 0.6 * (deadline - time.monotonic() - 3.0))
        arep = ann.run(cpu_s=cpu)
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
    if viol and time.monotonic() < deadline + 0.1 * budget:
        rep["legalize_final"] = legalize(P, st, time_s=max(3.0, 0.1 * budget), workers=workers, seed=seed, log=log)
        viol = grid_violations(st)
    rep["legal_grid"] = not viol
    t = time.monotonic()
    rep["exact"] = exact_check(P, st)
    stage("exact_check", t)
    rep["hpwl"] = round(st.hpwl(), 2)
    rep["hpwl_signal"] = round(st.hpwl(signal_only=True), 2)
    if terms is not None:
        try:
            poses = {p.uuid: st.pose(p.i) for p in P.parts}
            rep["physics_total"] = round(float(terms.total(poses)), 4)
            rep["physics_breakdown"] = terms.breakdown(poses)[:30]
        except Exception as e:
            rep["physics_error"] = f"{type(e).__name__}: {e}"
    rep["seconds"] = round(time.monotonic() - t0, 2)
    return Result(poses=st.poses(), report=rep, state=st, problem=P)
