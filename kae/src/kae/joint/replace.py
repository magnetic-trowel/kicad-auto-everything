# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Local re-placement of one window: only its parts move, everything else is fixed.

    res = replace_window(board, window, brief, history=h, seed=7, time_s=20)
    res.poses     # {uuid: (x, y, rot, side)} of the window's parts that moved (empty: none)
    res.report

The placer's own machinery does the work (kae.place: Problem, State, make_annealer with
`subset` and `window`; legality closes with the placer's loop, kae.place.exact):

1. The placement problem is built from the current board with every footprint outside the
   window marked locked, so those parts are fixed obstacles at their exact poses (any
   angle) and their pins fixed net terminals.
2. The window's parts start at their current poses. Parts KiCad named in a placement
   error are bumped by `legal_mm` (Problem.bump: more occupancy on every side, the placer's
   own closed-loop legality step), and parts named by an unrouted connection by `bump_mm`,
   which makes room for the corridor the router could not find.
   KiCad's placement errors also become exact constraints (exact.kicad_feedback: the two
   parts keep their distance plus a step), and nets of unrouted connections weigh
   `net_mult` x more (the placer's net_weights hook in local_replace does the same).
3. The annealer (physics terms, routability, legality, displacement) runs on the window's
   parts inside the window rectangle, with the congestion weight raised by `cong_mult` and
   the routing history added as RUDY demand (penalty.history_hook, the placer's cong_history
   hook), for a fixed number of
   moves.
4. Legality is hard: grid legality (routing margin and routing bumps dropped if they are
   what is illegal, then the greedy legalizer), then the placer's exact closed loop scoped
   to the window's parts (exact.repair(allowed=window parts)), as kae.place.pipeline
   .local_replace ends. A window that ends illegal returns no poses.
"""
from __future__ import annotations

import dataclasses
import math
import time
from dataclasses import dataclass, field

from .penalty import history_hook

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
                   legal_refs=(), legal_mm=0.15, drc_report=None, net_weights=None,
                   phys_mult=1.0, log=None):
    """See the module docstring. `board` is a kae.board.model.Board at the current poses;
    `window` a feedback.Window. `terms`: place terms built on the full board (the brief's
    structures), else built here when `physics`. `drc_report`: KiCad's report of the current
    board (its placement errors become exact constraints); `net_weights`: {net: factor}."""
    from kae.place import clusters
    from kae.place import exact as exactmod
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
    # KiCad's placement errors first (kept: they are constraints the model missed), then
    # routing room for parts an unrouted connection names (dropped if they make it illegal)
    # legal_refs: refs, or {ref: mm} with KiCad's shortfall per part (bumped by that plus legal_mm)
    need = dict(legal_refs) if isinstance(legal_refs, dict) else {r: 0.0 for r in legal_refs}
    legal_bumped = []
    for i in sub:
        r = P.parts[i].ref
        if r in need and need[r] + legal_mm > 0:
            P.bump(i, need[r] + legal_mm)
            legal_bumped.append(r)
    legal_cells = dict(getattr(P, "extra_cells", {}))
    bumped = []
    if bump_mm > 0 and bump_refs:
        for i in sub:
            if P.parts[i].ref in set(bump_refs):
                P.bump(i, bump_mm)
                bumped.append(P.parts[i].ref)
    rep["bumped"] = bumped
    rep["legal_bumped"] = legal_bumped
    for net in P.nets:
        net.weight *= float((net_weights or {}).get(net.name, 1.0))
    st = State(P)
    for i in sub:
        p = P.parts[i]
        X, Y = P.grid_of(p.x0, p.y0)
        rots = [r.rot for r in p.rots]
        k = min(range(len(rots)), key=lambda kk: min(abs(rots[kk] - p.rot0) % 360, 360 - abs(rots[kk] - p.rot0) % 360))
        st.X[i], st.Y[i], st.K[i] = X, Y, k
    if drc_report:
        try:
            rep["kicad_feedback"] = exactmod.kicad_feedback(P, st, drc_report)
        except Exception as e:  # noqa: BLE001 - the bumps still carry KiCad's verdict
            log(f"kicad feedback failed ({type(e).__name__}: {e})")
    x0, y0, x1, y1 = window.rect
    gwin = (int(math.floor((x0 - P.ox) / P.g)), int(math.ceil((x1 - P.ox) / P.g)),
            int(math.floor((y0 - P.oy) / P.g)), int(math.ceil((y1 - P.oy) / P.g)))
    if terms is None and physics and (brief or {}).get("structures"):
        try:
            from kae.place.stubs import make_terms
            terms, _ = make_terms(b2, brief, barrier=0.0, u_sat=3.0)
        except Exception as e:
            log(f"place terms failed ({type(e).__name__}: {e})")
            terms = None
    order = clusters.protection_order(P, brief) if physics else []
    hist_rep = dict(applied=False)
    hook = history_hook(P, history, scale=history_scale, window=window.rect, report=hist_rep)
    ann = make_annealer(P, st.copy(), terms=terms, seed=seed, w_phys=float(phys_mult) if terms is not None else 0.0,
                        w_cong=30.0 * cong_mult, order=order, subset=sub, window=gwin, log=None, cong_history=hook)
    rep["history"] = hist_rep
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
        P.extra_cells = dict(legal_cells)
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
    ex = exact_check(P, st, parts=sub)
    if ex:
        left = max(2.0, t0 + time_s - time.monotonic())
        cl = exactmod.repair(P, st, time_s=left, allowed=set(sub))
        cl.pop("findings", None)
        rep["closed_loop"] = cl
        ex = exact_check(P, st, parts=sub) if not grid_violations(st, parts=sub) else ["grid"]
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
