# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The placement pipeline: board -> problem -> brief -> macros -> seed -> anneal ->
legalize -> exact check -> poses.

    res = place(board, seed=0, time_s=300, physics=True)
    res.poses    # {uuid: (x, y, rot, side)} for every movable footprint
    res.report   # stage timings, costs, legality

Budgets: `time_s` is the wall time the caller allows (kaebench's --timeout). The pipeline
plans to finish in min(0.85 * time_s - 10, an effort cap that grows with the part count),
so small boards do not idle away a long timeout. The annealer budgets in CPU seconds; CP-SAT
stages in wall seconds with `workers` threads.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field

import numpy as np

from . import cpsat, seed as seedmod
from .legalize import exact_check, legalize
from .problem import Problem
from .state import State, grid_violations


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


def place(board, seed=0, time_s=300.0, physics=True, brief=None, workers=None, log=None, anneal=True):
    t0 = time.monotonic()
    log = log or (lambda *a, **k: None)
    workers = workers or _default_workers()
    rep = dict(seed=seed, time_s=time_s, physics=physics, workers=workers, stages={})

    def stage(name, t):
        rep["stages"][name] = round(time.monotonic() - t, 3)

    t = time.monotonic()
    net_kinds = None
    P = Problem.build(board, net_kinds=net_kinds)
    stage("problem", t)
    rep["problem"] = P.summary()
    n = len(P.mov)
    budget = plan_budget(time_s, n)
    rep["budget_s"] = round(budget, 1)
    deadline = t0 + budget
    log(f"problem: {n} movable, {len(P.parts) - n} fixed, {len(P.nets)} nets, grid {P.g} mm, "
        f"budget {budget:.0f}s")
    if n == 0:
        st = State(P)
        rep["legal_grid"] = True
        rep["exact"] = []
        return Result(poses={}, report=rep, state=st, problem=P)

    # ---- seed: quadratic + spread
    t = time.monotonic()
    objs, owner = seedmod._objects(P, None)
    net_w = {net.i: net.weight for net in P.nets}
    pos = seedmod.quadratic(P, objs, owner, net_w)
    pos = seedmod.spread(P, objs, pos, owner, net_w, seed=seed)
    st = State(P)
    for o, (members, w, h, rel) in enumerate(objs):
        for i in members:
            dx, dy = rel[i]
            X, Y = P.grid_of(pos[o, 0] + dx, pos[o, 1] + dy)
            st.X[i], st.Y[i], st.K[i] = X, Y, 0
    stage("seed_spread", t)

    # ---- floorplan: CP-SAT over all movable parts (displacement + weighted HPWL)
    t = time.monotonic()
    items = [cpsat.single(P, i, int(st.X[i]), int(st.Y[i]), int(st.K[i])) for i in P.mov]
    fp_time = max(2.0, 0.3 * (deadline - time.monotonic()))
    w_wl = 1.0 if n <= 150 else 0.0
    sol, model = seedmod.floorplan(P, items, fp_time, workers=workers, seed=seed, w_wl=w_wl,
                                   w_disp=0.05 if w_wl else 1.0, net_w=net_w, log=log)
    rep["floorplan"] = dict(status=model.status, seconds=round(model.wall, 2),
                            infeasible=model.infeasible_items)
    if sol is not None:
        for i, (X, Y, v) in zip(P.mov, sol):
            st.X[i], st.Y[i], st.K[i] = X, Y, v
    stage("floorplan", t)
    rep["hpwl_seed"] = round(st.hpwl(), 2)

    # ---- legalize what is left
    t = time.monotonic()
    viol = grid_violations(st)
    if viol:
        lrep = legalize(P, st, time_s=max(5.0, deadline - time.monotonic()), workers=workers, seed=seed, log=log)
        rep["legalize"] = lrep
    stage("legalize", t)
    viol = grid_violations(st)
    rep["legal_grid"] = not viol
    t = time.monotonic()
    ex = exact_check(P, st)
    stage("exact_check", t)
    rep["exact"] = ex
    rep["hpwl"] = round(st.hpwl(), 2)
    rep["hpwl_signal"] = round(st.hpwl(signal_only=True), 2)
    rep["seconds"] = round(time.monotonic() - t0, 2)
    _ = np
    return Result(poses=st.poses(), report=rep, state=st, problem=P)
