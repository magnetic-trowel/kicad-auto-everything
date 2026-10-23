# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Local re-placement of one window: only its parts move, everything else is fixed.

    res = replace_window(board, window, brief, history=h, seed=7, time_s=20)
    res.poses     # {uuid: (x, y, rot, side)} of the window's parts that moved (empty: none)
    res.report

The placer's own machinery does the work (kae.place: Problem, State, make_annealer with
`subset` and `window`, legalize.greedy, exact_check):

1. The placement problem is built from the current board with every footprint outside the
   window marked locked, so those parts are fixed obstacles at their exact poses (any
   angle) and their pins fixed net terminals.
2. The window's parts start at their current poses. Parts named by an unrouted connection
   are bumped (Problem.bump: `bump_mm` more occupancy on every side), which makes room for
   the corridor the router could not find.
3. The annealer (physics terms, routability, legality, displacement) runs on the window's
   parts inside the window rectangle, with the congestion weight raised by `cong_mult` and
   the routing history added as RUDY demand (penalty.apply_history).
4. Legality is hard: grid legality, then the routing margin and bumps are dropped if they
   are what is illegal, a greedy repair, then the exact polygon check. A window that ends
   illegal returns no poses.
"""
from __future__ import annotations

import dataclasses
import math
import time
from dataclasses import dataclass, field

from .penalty import apply_history

ROLE_KIND = {"ground": "ground", "rail": "power", "power": "power"}


@dataclass
class Result:
    poses: dict = field(default_factory=dict)
    report: dict = field(default_factory=dict)


def net_kinds(brief):
    """{net: ground | power | signal} from the brief's net roles (as kae.place.pipeline)."""
    out = {}
    for name, d in ((brief or {}).get("nets") or {}).items():
        role = (d or {}).get("role") if isinstance(d, dict) else d
        if role:
            out[name] = ROLE_KIND.get(role, "signal")
    return out


def _right(rot):
    a = rot % 90.0
    return min(a, 90.0 - a) < 1e-6


def window_board(board, parts):
    """A copy of the board model where every footprint not in `parts` is locked."""
    want = set(parts)
    fps = [fp if (fp.uuid in want or fp.locked) else dataclasses.replace(fp, locked=True) for fp in board.footprints]
    return dataclasses.replace(board, footprints=fps)


def replace_window(board, window, brief, history=None, seed=0, time_s=20.0, terms=None, physics=True,
                   cong_mult=2.0, history_scale=1.0, bump_mm=0.25, bump_refs=(), margin=0.3, moves_per_part=6000,
                   log=None):
    """See the module docstring. `board` is a kae.board.model.Board at the current poses;
    `window` a feedback.Window. `terms`: place terms built on the full board (the brief's
    structures), else built here when `physics`."""
    from kae.place import clusters
    from kae.place.anneal import make_annealer
    from kae.place.legalize import exact_check, greedy
    from kae.place.problem import Problem
    from kae.place.state import State, grid_violations

    t0 = time.monotonic()
    log = log or (lambda *a, **k: None)
    rep = dict(window=window.to_dict(), seed=seed)
    fp_of = {fp.uuid: fp for fp in board.footprints}
    parts = [u for u in window.parts if u in fp_of and not fp_of[u].locked and not fp_of[u].edge_cuts]
    if not parts:
        rep["skipped"] = "no movable part"
        return Result(report=rep)
    odd = any(not _right(fp_of[u].rot) for u in parts)
    b2 = window_board(board, parts)
    P = Problem.build(b2, net_kinds=net_kinds(brief), angle_step=15.0 if odd else None)
    P.set_margin(max(0.0, float(margin)))
    sub = list(P.mov)
    if not sub:
        rep["skipped"] = "no movable part in the problem"
        return Result(report=rep)
    bumped = []
    if bump_mm > 0 and bump_refs:
        for i in sub:
            if P.parts[i].ref in set(bump_refs):
                P.bump(i, bump_mm)
                bumped.append(P.parts[i].ref)
    rep["bumped"] = bumped
    st = State(P)
    for i in sub:
        p = P.parts[i]
        X, Y = P.grid_of(p.x0, p.y0)
        rots = [r.rot for r in p.rots]
        k = min(range(len(rots)), key=lambda kk: min(abs(rots[kk] - p.rot0) % 360, 360 - abs(rots[kk] - p.rot0) % 360))
        st.X[i], st.Y[i], st.K[i] = X, Y, k
    x0, y0, x1, y1 = window.rect
    gwin = (int(math.floor((x0 - P.ox) / P.g)), int(math.ceil((x1 - P.ox) / P.g)),
            int(math.floor((y0 - P.oy) / P.g)), int(math.ceil((y1 - P.oy) / P.g)))
    if terms is None and physics and (brief or {}).get("structures"):
        try:
            from kae.place.stubs import make_terms
            terms, _ = make_terms(b2, brief, barrier=0.0, u_sat=3.0)
        except Exception as e:  # noqa: BLE001 - the window still re-places on routability
            log(f"place terms failed ({type(e).__name__}: {e})")
            terms = None
    order = clusters.protection_order(P, brief) if physics else []
    ann = make_annealer(P, st.copy(), terms=terms, seed=seed, w_phys=1.0 if terms is not None else 0.0,
                        w_cong=30.0 * cong_mult, order=order, subset=sub, window=gwin, log=None)
    rep["history"] = apply_history(ann, history, scale=history_scale, window=window.rect)
    rep["cost_before"] = round(float(ann.cost(ann.lam1)), 5)
    # a fixed move count (not the engine's adaptive one): the same seed gives the same window
    # whenever the time budget does not bind
    rep["anneal"] = ann.run(cpu_s=max(0.5, 0.75 * time_s), deadline=t0 + 0.8 * time_s,
                            max_moves=int(moves_per_part) * len(sub))
    ann.write_back(use_best_legal=True)
    st = ann.st
    rep["cost_after"] = round(float(ann.cost(ann.lam1)), 5)
    bad = grid_violations(st)
    if bad and (bumped or P.margin > 0):
        P.extra_cells = {}
        P.set_margin(0.0)
        rep["relaxed"] = True
        bad = grid_violations(st)
    if bad:
        rep["greedy"] = greedy(P, st, sorted(bad), log=None, time_s=max(1.0, 0.15 * time_s))
        bad = grid_violations(st)
    rep["legal_grid"] = not bad
    if bad:
        rep["rejected"] = "illegal after repair"
        rep["seconds"] = round(time.monotonic() - t0, 2)
        return Result(report=rep)
    ex = exact_check(P, st)
    rep["exact"] = ex
    if ex:
        rep["rejected"] = f"{len(ex)} exact violations"
        rep["seconds"] = round(time.monotonic() - t0, 2)
        return Result(report=rep)
    poses = {}
    for i in sub:
        p = P.parts[i]
        new = st.pose(i)
        old = (p.x0, p.y0, p.rot0 % 360.0, p.side)
        if math.dist(new[:2], old[:2]) > 1e-4 or abs((new[2] - old[2] + 180) % 360 - 180) > 1e-3:
            poses[p.uuid] = new
    rep["moved"] = sorted(P.parts[i].ref for i in sub if P.parts[i].uuid in poses)
    rep["seconds"] = round(time.monotonic() - t0, 2)
    return Result(poses=poses, report=rep)
