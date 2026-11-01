# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Legalization: windowed CP-SAT minimum displacement on the grid, then an exact check.

`legalize(P, st, budget)` repairs grid violations window by window (after
tools/research/solver-bench/legalize_clusters.py): violators near each other form a group;
the group and its k nearest movable parts are freed inside a window, everything else is a
fixed obstacle, and CP-SAT minimizes L1 displacement plus a rotation-change charge. A
window that fails grows (k x 1.6, larger margin); if rounds run out, every movable part is
freed at once.

`exact_check(P, st)` re-checks the result with KiCad's shapes (shapely): courtyards per
side (deflated by max_error, as KiCad does), holes inside other courtyards, pad-to-pad
copper clearance, pads inside the outline at the copper-to-edge clearance, and rule areas
that keep out footprints or pads. It reports what remains illegal; DRC on the re-opened
board stays the judge.
"""
from __future__ import annotations

import math
import os
import re
import time

import numpy as np
import shapely
from shapely.geometry import LineString, Point, Polygon

from kae.board import transform

from . import cpsat
from .problem import is_drilled
from .state import grid_violations


# ----------------------------------------------------------------------------- grid repair
def _groups(st, bad, radius_mm):
    pts = {i: st.center(i) for i in bad}
    groups = []
    for b in sorted(bad):
        bx, by = pts[b]
        for gr in groups:
            if any(abs(bx - pts[o][0]) + abs(by - pts[o][1]) < radius_mm for o in gr):
                gr.append(b)
                break
        else:
            groups.append([b])
    return groups


def _window_solve(P, st, free, margin_cells, time_s, workers, seed, w_rot=1.0):
    """Re-place the `free` parts inside a window around them; others are obstacles."""
    g = P.g
    rects = [r for i in free for (_, r, _) in st.grid_rects(i)]
    wi0 = min(r[0] for r in rects) - margin_cells
    wi1 = max(r[1] for r in rects) + margin_cells
    wj0 = min(r[2] for r in rects) - margin_cells
    wj1 = max(r[3] for r in rects) + margin_cells
    # origin box: the window; obstacles: everything that can reach into it
    ext = max(max(r[1] - r[0], r[3] - r[2]) for r in rects) + 2
    obstacles = []
    fs = set(free)
    for i in P.mov:
        if i in fs:
            continue
        for side, r, _ in st.grid_rects(i):
            if r[1] > wi0 - ext and r[0] < wi1 + ext and r[3] > wj0 - ext and r[2] < wj1 + ext:
                obstacles.append((side, r))
    for ob in P.obstacles:
        r = ob.g
        if r[1] > wi0 - ext and r[0] < wi1 + ext and r[3] > wj0 - ext and r[2] < wj1 + ext:
            obstacles.append((ob.side, r))
    items = []
    for i in free:
        it = cpsat.single(P, i, int(st.X[i]), int(st.Y[i]), int(st.K[i]))
        it.bounds = (wi0, wi1, wj0, wj1)
        items.append(it)
    model = cpsat.Model(P, items, obstacles, w_disp=1.0, w_rot=w_rot)
    sol = model.solve(time_s, workers=workers, seed=seed)
    _ = g
    if sol is not None:      # variant index -> rotation index
        sol = [(X, Y, it.variants[v][i][2]) for it, i, (X, Y, v) in zip(items, free, sol)]
    return sol, model


MAX_WINDOW = 40          # parts freed in one CP-SAT window
GLOBAL_MAX = 40          # all parts in one CP-SAT model only up to this many


def legalize(P, st, time_s=30.0, workers=2, seed=0, k=8, max_rounds=8, log=None, force=(), window_share=0.6):
    """Repair grid violations in place (parts in `force` are re-placed in the first round even
    when the grid finds them legal, e.g. after a KiCad violation). Returns a report dict.

    1. Windows: violators within 4 mm form a group; the group and its nearest movable parts
       (k, growing x1.6 on failure, at most MAX_WINDOW) are re-placed by CP-SAT at minimum
       displacement inside a window around them, everything else fixed; rounds repeat while
       violations remain, for at most `window_share` of the budget.
    2. Greedy: whatever is still illegal goes to the nearest free spot, largest first,
       evicting smaller parts when nothing is free nearby (`greedy`).
    3. Small boards only (<= GLOBAL_MAX parts): one CP-SAT model over every part."""
    t0 = time.monotonic()
    deadline = t0 + time_s
    win_deadline = t0 + window_share * time_s
    rep = dict(rounds=0, windows=0, solved=0, global_used=False, start_violators=0)
    kk = {}
    force = {i for i in force if P.parts[i].movable}
    for rnd in range(max_rounds):
        viol = grid_violations(st)
        if rnd == 0:
            rep["start_violators"] = len(viol)
            for i in force:
                viol.setdefault(i, []).append(("kicad", None))
        if not viol or time.monotonic() > win_deadline:
            break
        rep["rounds"] = rnd + 1
        bad = set(viol)
        for gr in _groups(st, bad, radius_mm=4.0):
            now = time.monotonic()
            if now > win_deadline:
                break
            key = tuple(gr)
            kw = min(kk.get(key, k), MAX_WINDOW)
            cx = np.mean([st.center(b)[0] for b in gr])
            cy = np.mean([st.center(b)[1] for b in gr])
            near = sorted(P.mov, key=lambda c: abs(st.center(c)[0] - cx) + abs(st.center(c)[1] - cy))
            free = list(dict.fromkeys(gr[:MAX_WINDOW] + near[:kw]))[:max(MAX_WINDOW, len(gr[:MAX_WINDOW]))]
            margin = int(math.ceil((2.0 + 0.5 * (kw // k)) / P.g))
            budget = min(max(1.0, 0.15 * time_s), win_deadline - now)
            if budget <= 0.2:
                break
            sol, model = _window_solve(P, st, free, margin, budget, workers, seed + rnd)
            rep["windows"] += 1
            if sol is not None:
                rep["solved"] += 1
                for i, (X, Y, v) in zip(free, sol):
                    st.X[i], st.Y[i], st.K[i] = X, Y, v
            else:
                kk[key] = int(kw * 1.6) + 1
            if log:
                log(f"legalize window {gr[:4]} free={len(free)} status={model.status} {model.wall:.2f}s")
    viol = grid_violations(st)
    if viol:
        rep["greedy"] = greedy(P, st, list(viol), log=log, time_s=max(1.0, deadline - time.monotonic()))
        viol = grid_violations(st)
    if viol and time.monotonic() < deadline and len(P.mov) <= GLOBAL_MAX:
        rep["global_used"] = True
        items = [cpsat.single(P, i, int(st.X[i]), int(st.Y[i]), int(st.K[i])) for i in P.mov]
        obstacles = [(ob.side, ob.g) for ob in P.obstacles]
        model = cpsat.Model(P, items, obstacles, w_disp=1.0, w_rot=1.0)
        sol = model.solve(max(1.0, deadline - time.monotonic()), workers=workers, seed=seed)
        rep["global_status"] = model.status
        if sol is not None:
            for it, i, (X, Y, v) in zip(items, P.mov, sol):
                st.X[i], st.Y[i], st.K[i] = X, Y, it.variants[v][i][2]
        viol = grid_violations(st)
    rep["end_violators"] = len(viol)
    rep["violations"] = {P.parts[i].ref: [str(r) for r in rs[:3]] for i, rs in list(viol.items())[:20]}
    rep["seconds"] = round(time.monotonic() - t0, 2)
    return rep


# ----------------------------------------------------------------------------- greedy fallback
def _occupancy(P, st, skip, pad):
    """Per-side cell occupancy counts of obstacles and of movable parts not in `skip`, on the
    grid padded by `pad` cells on every side (courtyards may overhang the board)."""
    occ = [np.zeros((P.ncx + 2 * pad, P.ncy + 2 * pad), dtype=np.int32) for _ in (0, 1)]
    for ob in P.obstacles:
        _mark(occ[ob.side], ob.g, pad, 1)
    for i in P.mov:
        if i in skip:
            continue
        for side, r, _ in st.grid_rects(i):
            _mark(occ[side], r, pad, 1)
    return occ


def _mark(a, r, pad, v):
    i0, i1, j0, j1 = r
    i0, i1 = max(0, i0 + pad), min(a.shape[0], i1 + pad)
    j0, j1 = max(0, j0 + pad), min(a.shape[1], j1 + pad)
    if i1 > i0 and j1 > j0:
        a[i0:i1, j0:j1] += v


def _free_origins(occ, rect, pad, xa, xb, ya, yb):
    """Bool map over origins X in [xa, xb], Y in [ya, yb]: rect (relative to the origin) hits
    no occupied cell. Cells beyond the padded grid count as free (nothing is placed there)."""
    a, b, c, d = rect
    nx, ny = xb - xa + 1, yb - ya + 1
    if b <= a or d <= c:
        return np.ones((nx, ny), dtype=bool)
    # region of the padded array the rect can reach from the window, clipped
    r0, r1 = xa + a + pad, xb + b + pad
    s0, s1 = ya + c + pad, yb + d + pad
    q0, q1 = max(0, r0), min(occ.shape[0], r1)
    t0, t1 = max(0, s0), min(occ.shape[1], s1)
    reg = np.zeros((r1 - r0, s1 - s0), dtype=np.int64)
    if q1 > q0 and t1 > t0:
        reg[q0 - r0:q1 - r0, t0 - s0:t1 - s0] = occ[q0:q1, t0:t1]
    L = np.zeros((reg.shape[0] + 1, reg.shape[1] + 1), dtype=np.int64)
    L[1:, 1:] = reg.cumsum(0).cumsum(1)
    w, h = b - a, d - c
    cnt = L[w:w + nx, h:h + ny] - L[0:nx, h:h + ny] - L[w:w + nx, 0:ny] + L[0:nx, 0:ny]
    return cnt == 0


def _inside_origins(P, rect, xa, xb, ya, yb):
    """Bool map over origins: the board rect lies inside the outline (and the grid)."""
    a, b, c, d = rect
    nx, ny = xb - xa + 1, yb - ya + 1
    ok = np.zeros((nx, ny), dtype=bool)
    # origins keeping the rect on the grid
    lo_x, hi_x = max(xa, -a), min(xb, P.ncx - b)
    lo_y, hi_y = max(ya, -c), min(yb, P.ncy - d)
    if hi_x < lo_x or hi_y < lo_y:
        return ok
    S = P.sat_out
    X0, X1 = lo_x + a, hi_x + a
    Y0, Y1 = lo_y + c, hi_y + c
    w, h = b - a, d - c
    cnt = (S[X0 + w:X1 + w + 1, Y0 + h:Y1 + h + 1] - S[X0:X1 + 1, Y0 + h:Y1 + h + 1]
           - S[X0 + w:X1 + w + 1, Y0:Y1 + 1] + S[X0:X1 + 1, Y0:Y1 + 1])
    ok[lo_x - xa:hi_x - xa + 1, lo_y - ya:hi_y - ya + 1] = cnt == 0
    return ok


def _nearest_spot(P, p, X0, Y0, K0, occ, pad, w_rot, span, cost_occ=None, w_cost=0.0):
    """(cost, X, Y, k) of the nearest origin where part p's rectangles are free in `occ` and
    its board rectangles inside the outline, or None. With `cost_occ` (cells of parts that
    may be evicted) the cost adds w_cost x the cells of those parts its own rectangle covers."""
    si = 0 if p.s > 0 else 1
    size = max(max(r.g_own[1] - r.g_own[0], r.g_own[3] - r.g_own[2]) for r in p.rots)
    R = max(20, 2 * size)
    best = None
    from ._fastlegal import rotations_for_fit
    ks = rotations_for_fit(p, K0)
    while True:
        xa, xb, ya, yb = X0 - R, X0 + R, Y0 - R, Y0 + R
        for k in ks:
            r = p.rots[k]
            ok = np.ones((xb - xa + 1, yb - ya + 1), dtype=bool)
            for brd in (r.g_boards or (r.g_board,)):
                ok &= _inside_origins(P, brd, xa, xb, ya, yb)
                if not ok.any():
                    break
            if not ok.any():
                continue
            for o in (r.g_own_rects or (r.g_own,)):
                ok &= _free_origins(occ[si], o, pad, xa, xb, ya, yb)
            for o in r.g_opp:
                if not ok.any():
                    break
                ok &= _free_origins(occ[1 - si], o, pad, xa, xb, ya, yb)
            if not ok.any():
                continue
            xs, ys = np.nonzero(ok)
            cost = (np.abs(xs + xa - X0) + np.abs(ys + ya - Y0) + (w_rot if k != K0 else 0.0)).astype(float)
            if cost_occ is not None:
                for o in (r.g_own_rects or (r.g_own,)):
                    cost += w_cost * _covered(cost_occ[si], o, pad, xa, xb, ya, yb)[xs, ys]
            j = int(np.argmin(cost))
            if best is None or cost[j] < best[0]:
                best = (float(cost[j]), int(xs[j] + xa), int(ys[j] + ya), k)
        # a spot within R of the origin can still lose to one just outside when the best
        # cost exceeds R (L1 vs the square window): widen once more in that case
        if (best is not None and best[0] <= R) or R >= span:
            return best
        R = min(span, 2 * R)


def _covered(occ, rect, pad, xa, xb, ya, yb):
    """Occupied-cell count under rect for every origin of the window (cf. _free_origins)."""
    a, b, c, d = rect
    nx, ny = xb - xa + 1, yb - ya + 1
    if b <= a or d <= c:
        return np.zeros((nx, ny))
    r0, r1 = xa + a + pad, xb + b + pad
    s0, s1 = ya + c + pad, yb + d + pad
    q0, q1 = max(0, r0), min(occ.shape[0], r1)
    t0, t1 = max(0, s0), min(occ.shape[1], s1)
    reg = np.zeros((r1 - r0, s1 - s0), dtype=np.int64)
    if q1 > q0 and t1 > t0:
        reg[q0 - r0:q1 - r0, t0 - s0:t1 - s0] = occ[q0:q1, t0:t1]
    L = np.zeros((reg.shape[0] + 1, reg.shape[1] + 1), dtype=np.int64)
    L[1:, 1:] = reg.cumsum(0).cumsum(1)
    w, h = b - a, d - c
    return (L[w:w + nx, h:h + ny] - L[0:nx, h:h + ny] - L[w:w + nx, 0:ny] + L[0:nx, 0:ny]).astype(float)


def _greedy_fast(P, st, parts, log, w_rot, ripup, max_ripups, t0, time_s=None):
    """greedy() on the compiled kernels (summed-area tables updated in place)."""
    from . import _fastlegal as FL
    from .problem import sat
    ext = 1
    for i in P.mov:
        for r in P.parts[i].rots:
            for (a, b, c, d) in (r.g_own,) + tuple(r.g_opp):
                ext = max(ext, -a, b, -c, d)
    pad = ext + 1
    skip = set(parts)
    occ = _occupancy(P, st, skip, pad)
    S = [sat(occ[0]), sat(occ[1])]
    SO = P.sat_out
    max_d = P.ncx + P.ncy + 4 * pad
    arrs = {}

    def arrays(i):
        key = (i, int(st.K[i]))
        if key not in arrs:
            ks = FL.rotations_for_fit(P.parts[i], int(st.K[i]))
            arrs[key] = (ks,) + FL.part_arrays(P.parts[i], ks)
        return arrs[key]

    def add(i, v):
        for side, (a, b, c, d), _ in st.grid_rects(i):
            FL.sat_add_rect(S[side], a + pad, b + pad, c + pad, d + pad, v)

    def local(i):
        # the ring walk is cheap only nearby (its cost grows with the square of the reach);
        # farther spots come from the global search
        r = P.parts[i].rots[0].g_own
        return int(min(150, max(60, 4 * max(r[1] - r[0], r[3] - r[2]))))

    def spot(i, reach):
        p = P.parts[i]
        if reach >= max_d:
            return _global_spot(i)
        ks, own, own_n, opp, opp_n, brd, brd_n = arrays(i)
        c, X, Y, k = FL.nearest_spot(S[0], S[1], SO, P.ncx, P.ncy, pad, 0 if p.s > 0 else 1, int(st.X[i]),
                                     int(st.Y[i]), ks.index(int(st.K[i])), float(w_rot), own, own_n, opp, opp_n,
                                     brd, brd_n, int(min(reach, max_d)))
        return None if c < 0 else (c, X, Y, ks[k])

    def _global_spot(i):
        """Nearest free origin anywhere: every origin at once from the summed-area tables
        (numpy slices), so a far spot costs a few array passes instead of a ring walk."""
        p = P.parts[i]
        si = 0 if p.s > 0 else 1
        X0, Y0, K0 = int(st.X[i]), int(st.Y[i]), int(st.K[i])
        nx, ny = P.ncx, P.ncy
        xs = np.arange(nx)[:, None]
        ys = np.arange(ny)[None, :]
        dist = np.abs(xs - X0) + np.abs(ys - Y0)
        best = None
        for k in FL.rotations_for_fit(p, K0):
            r = p.rots[k]
            ok = np.ones((nx, ny), dtype=bool)
            for brd in (r.g_boards or (r.g_board,)):
                ok &= _inside_origins(P, brd, 0, nx - 1, 0, ny - 1)
            if not ok.any():
                continue
            for side, rect in [(si, o) for o in (r.g_own_rects or (r.g_own,))] + [(1 - si, o) for o in r.g_opp]:
                a, b, c, d = rect
                T = S[side]
                cnt = (T[b + pad:b + pad + nx, d + pad:d + pad + ny] - T[a + pad:a + pad + nx, d + pad:d + pad + ny]
                       - T[b + pad:b + pad + nx, c + pad:c + pad + ny] + T[a + pad:a + pad + nx, c + pad:c + pad + ny])
                ok &= cnt == 0
                if not ok.any():
                    break
            if not ok.any():
                continue
            cost = np.where(ok, dist + (w_rot if k != K0 else 0.0), np.inf)
            j = int(np.argmin(cost))
            c = float(cost.flat[j])
            if best is None or c < best[0]:
                best = (c, j // ny, j % ny, k)
        return best
    start = {i: (int(st.X[i]), int(st.Y[i])) for i in parts}
    placed_set, queue = set(), []
    # first pass: a free spot near where the part wants to be
    out_of_time = False
    for i in parts:
        if time_s is not None and time.monotonic() - t0 > time_s:
            out_of_time = True
            queue.append(i)
            continue
        best = spot(i, local(i))
        if best is None:
            queue.append(i)
            continue
        _, st.X[i], st.Y[i], st.K[i] = best
        add(i, 1)
        placed_set.add(i)
    ripups = 0
    max_ripups = max_ripups if max_ripups is not None else 4 * len(queue) + 20
    unplaced = []

    def _ripup_at(i, reach):
        """Spot within reach where part i covers the least of smaller parts (evictable),
        never an obstacle or a part at least as big: (cost, X, Y, k, 'ripup') or None."""
        p = P.parts[i]
        hard = [np.zeros_like(occ[0]) for _ in (0, 1)]
        soft = [np.zeros_like(occ[0]) for _ in (0, 1)]
        for ob in P.obstacles:
            _mark(hard[ob.side], ob.g, pad, 1)
        for j in P.mov:
            if j == i or (j in skip and j not in placed_set):
                continue
            tgt = soft if P.parts[j].area < p.area else hard
            for side, r, _ in st.grid_rects(j):
                _mark(tgt[side], r, pad, 1)
        H = [sat(hard[0]), sat(hard[1])]
        C = [sat(soft[0]), sat(soft[1])]
        ks, own, own_n, opp, opp_n, brd, brd_n = arrays(i)
        c, X, Y, k = FL.ripup_spot(H[0], H[1], C[0], C[1], SO, P.ncx, P.ncy, pad, 0 if p.s > 0 else 1,
                                   int(st.X[i]), int(st.Y[i]), ks.index(int(st.K[i])), float(w_rot), 4.0, own, own_n,
                                   opp, opp_n, brd, brd_n, int(min(reach, max_d)))
        return None if c < 0 else (c, X, Y, ks[k], "ripup")
    while queue:
        if out_of_time or (time_s is not None and time.monotonic() - t0 > time_s):
            out_of_time = True
            break
        i = queue.pop(0)
        p = P.parts[i]
        # nearby first (the space may have changed), then anywhere on the board (the global
        # search is cheap), then evict smaller parts nearby, then anywhere
        for reach, evict_ok in ((local(i), False), (max_d, False), (local(i), True), (max_d, True)):
            if evict_ok and not (ripup and ripups < max_ripups):
                continue
            if not evict_ok:
                best = spot(i, reach)
                if best is not None:
                    break
                continue
            best = _ripup_at(i, reach)
            if best is not None:
                break
        else:
            unplaced.append(i)
            continue
        if not best[-1:] == ("ripup",):
            _, st.X[i], st.Y[i], st.K[i] = best
            add(i, 1)
            placed_set.add(i)
            continue
        ripups += 1
        st.X[i], st.Y[i], st.K[i] = best[1], best[2], best[3]
        mine = st.grid_rects(i)
        evict = []
        for j in list(placed_set) + [j for j in P.mov if j not in skip]:
            if j == i or P.parts[j].area >= p.area:
                continue
            if any(sa == sb and ra[1] > rb[0] and rb[1] > ra[0] and ra[3] > rb[2] and rb[3] > ra[2]
                   for sa, ra, _ in mine for sb, rb, _ in st.grid_rects(j)):
                evict.append(j)
        for j in evict:
            if j in placed_set or j not in skip:
                add(j, -1)
            placed_set.discard(j)
            skip.add(j)
            start.setdefault(j, (int(st.X[j]), int(st.Y[j])))
        queue.extend(sorted(evict, key=lambda j: -P.parts[j].area))
        add(i, 1)
        placed_set.add(i)
    unplaced += queue
    moved = sum(math.hypot((st.X[i] - x) * P.g, (st.Y[i] - y) * P.g) for i, (x, y) in start.items())
    rep = dict(placed=len(placed_set), unplaced=[P.parts[i].ref for i in unplaced], moved_mm=round(moved, 2),
               ripups=ripups, seconds=round(time.monotonic() - t0, 2), compiled=True, out_of_time=out_of_time)
    if log:
        log(f"greedy legalization: {len(placed_set)} placed, {len(unplaced)} without a spot, {ripups} rip-ups, "
            f"moved {moved:.1f} mm ({rep['seconds']}s)")
    return rep


def greedy(P, st, parts, log=None, w_rot=None, ripup=True, max_ripups=None, compiled=None, time_s=None):
    """Put `parts` back one by one, largest first, at the nearest grid origin (L1, plus a
    charge for turning) where none of their rectangles meets an obstacle or another part on
    its side and their board rectangles lie inside the outline; every other movable part
    stays where it is. The search window around the current origin doubles until a spot is
    found or it covers the board. A part that finds no spot (a full board, space cut into
    pieces) takes the nearby spot that covers the least area of smaller parts, which are
    evicted and placed again (rip-up; evictions only go to smaller parts, so it ends).
    Always ends legal for the parts it places; returns {placed, unplaced: [refs], moved_mm,
    ripups}."""
    t0 = time.monotonic()
    parts = sorted({i for i in parts if P.parts[i].movable}, key=lambda i: -P.parts[i].area)
    if not parts:
        return dict(placed=0, unplaced=[], moved_mm=0.0, ripups=0, seconds=0.0)
    if compiled is None:
        from ._fastlegal import HAVE_NUMBA
        compiled = HAVE_NUMBA and not os.environ.get("KAE_NO_NUMBA")
    if compiled:
        return _greedy_fast(P, st, parts, log, (2.0 / P.g) if w_rot is None else w_rot, ripup, max_ripups, t0,
                            time_s=time_s)
    ext = 1
    for i in P.mov:
        for r in P.parts[i].rots:
            for (a, b, c, d) in (r.g_own,) + tuple(r.g_opp):
                ext = max(ext, -a, b, -c, d)
    pad = ext + 1
    skip = set(parts)
    occ = _occupancy(P, st, skip, pad)
    w_rot = (2.0 / P.g) if w_rot is None else w_rot          # turning costs like moving 2 mm
    span = max(P.ncx, P.ncy) + 2 * ext
    start = {i: (int(st.X[i]), int(st.Y[i])) for i in parts}
    placed_set, unplaced = set(), []
    for i in parts:
        p = P.parts[i]
        best = _nearest_spot(P, p, int(st.X[i]), int(st.Y[i]), int(st.K[i]), occ, pad, w_rot, span)
        if best is None:
            unplaced.append(i)
            continue
        _, X, Y, k = best
        st.X[i], st.Y[i], st.K[i] = X, Y, k
        for side, r, _ in st.grid_rects(i):
            _mark(occ[side], r, pad, 1)
        placed_set.add(i)
    ripups = 0
    max_ripups = max_ripups if max_ripups is not None else 4 * len(unplaced) + 20
    queue = list(unplaced)
    unplaced = []
    while queue and ripups < max_ripups and ripup:
        i = queue.pop(0)
        p = P.parts[i]
        best = _nearest_spot(P, p, int(st.X[i]), int(st.Y[i]), int(st.K[i]), occ, pad, w_rot, span)
        if best is None:
            # rip-up: obstacles and parts at least as big are hard, smaller placed parts may go
            hard = [np.zeros_like(occ[0]) for _ in (0, 1)]
            soft = [np.zeros_like(occ[0]) for _ in (0, 1)]
            for ob in P.obstacles:
                _mark(hard[ob.side], ob.g, pad, 1)
            for j in P.mov:
                if j == i or (j in skip and j not in placed_set):
                    continue
                tgt = soft if P.parts[j].area < p.area else hard
                for side, r, _ in st.grid_rects(j):
                    _mark(tgt[side], r, pad, 1)
            best = _nearest_spot(P, p, int(st.X[i]), int(st.Y[i]), int(st.K[i]), hard, pad, w_rot, span,
                                 cost_occ=soft, w_cost=4.0)
            if best is None:
                unplaced.append(i)
                continue
            ripups += 1
            _, X, Y, k = best
            st.X[i], st.Y[i], st.K[i] = X, Y, k
            mine = st.grid_rects(i)
            evict = []
            for j in list(placed_set) + [j for j in P.mov if j not in skip]:
                if j == i or P.parts[j].area >= p.area:
                    continue
                if any(sa == sb and ra[1] > rb[0] and rb[1] > ra[0] and ra[3] > rb[2] and rb[3] > ra[2]
                       for sa, ra, _ in mine for sb, rb, _ in st.grid_rects(j)):
                    evict.append(j)
            for j in evict:
                for side, r, _ in st.grid_rects(j):
                    _mark(occ[side], r, pad, -1)
                placed_set.discard(j)
                skip.add(j)
                start.setdefault(j, (int(st.X[j]), int(st.Y[j])))
            queue.extend(sorted(evict, key=lambda j: -P.parts[j].area))
            for side, r, _ in mine:
                _mark(occ[side], r, pad, 1)
            placed_set.add(i)
            continue
        _, X, Y, k = best
        st.X[i], st.Y[i], st.K[i] = X, Y, k
        for side, r, _ in st.grid_rects(i):
            _mark(occ[side], r, pad, 1)
        placed_set.add(i)
    unplaced += queue
    moved = sum(math.hypot((st.X[i] - x) * P.g, (st.Y[i] - y) * P.g) for i, (x, y) in start.items())
    rep = dict(placed=len(placed_set), unplaced=[P.parts[i].ref for i in unplaced], moved_mm=round(moved, 2),
               ripups=ripups, seconds=round(time.monotonic() - t0, 2))
    if log:
        log(f"greedy legalization: {len(placed_set)} placed, {len(unplaced)} without a spot, {ripups} rip-ups, "
            f"moved {moved:.1f} mm ({rep['seconds']}s)")
    return rep


# ----------------------------------------------------------------------------- KiCad feedback
PLACEMENT_TYPES = ("courtyards_overlap", "copper_edge_clearance", "clearance", "hole_clearance", "hole_to_hole",
                   "holes_co_located", "items_not_allowed", "malformed_courtyard", "npth_inside_courtyard",
                   "pth_inside_courtyard", "shorting_items", "solder_mask_bridge")
_OF_REF = re.compile(r"\bof (\S+)")
_FP_REF = re.compile(r"^(?:Footprint|Courtyard of) (\S+)")


def kicad_violations(drc):
    """Violations from a kicad-cli DRC report (path, JSON text or dict): [{type, severity,
    items: [{description, pos: {x, y}}]}], placement-relevant types only."""
    import json
    from pathlib import Path
    if isinstance(drc, (str, Path)) and Path(str(drc)).exists():
        drc = json.loads(Path(drc).read_text())
    elif isinstance(drc, str):
        drc = json.loads(drc)
    out = []
    for v in (drc or {}).get("violations", []):
        if v.get("type") in PLACEMENT_TYPES and v.get("severity", "error") == "error":
            out.append(dict(type=v.get("type"), severity=v.get("severity"), items=v.get("items", [])))
    return out


def violation_parts(P, st, v):
    """Part indices a KiCad violation names: by reference in an item's text ('Pad 2 [GND] of
    C3 on F.Cu', 'Footprint U1'); a reference that is unknown or repeats, by the part with a
    pad nearest the item's position. Board-level items (no owner named) name no part."""
    by_ref = {}
    for p in P.parts:
        by_ref.setdefault(p.ref, []).append(p.i)
    out = set()
    for it in v.get("items", []):
        d = it.get("description", "")
        m = _OF_REF.search(d) or _FP_REF.search(d)
        if m is None:
            # a board-level item ('Segment on Edge.Cuts', "PCB text '...' on B.Cu", 'Rule Area',
            # 'Track', 'Via', 'Zone'): no part; by position it would name whichever part has a
            # pad nearest the item's anchor (paw3222: an edge error became a pair separation)
            continue
        cands = by_ref.get(m.group(1), [])
        pos = it.get("pos") or {}
        if len(cands) == 1:
            out.add(cands[0])
            continue
        if "x" in pos and "y" in pos:
            pool = cands or [p.i for p in P.parts]
            best = min(pool, key=lambda i: float(np.min(np.hypot(*(st.pins_xy(i) - [pos["x"], pos["y"]]).T)))
                       if len(P.parts[i].fp.pads) else math.hypot(st.xy(i)[0] - pos["x"], st.xy(i)[1] - pos["y"]))
            out.add(best)
    return out


def repair_kicad(P, st, violations, time_s=30.0, workers=2, seed=0, step_mm=0.1, log=None):
    """Feed KiCad's verdict on a candidate placement back as constraints: every movable part
    a placement violation names grows its occupancy rectangle by `step_mm` (kept for the rest
    of the run, P.bump) and is re-placed by the windowed legalizer. Returns a report."""
    if violations and isinstance(violations, (str, dict)):
        violations = kicad_violations(violations)
    parts = set()
    by_type = {}
    for v in violations or []:
        ps = violation_parts(P, st, v)
        by_type[v["type"]] = by_type.get(v["type"], 0) + 1
        parts |= {i for i in ps if P.parts[i].movable}
    for i in parts:
        P.bump(i, step_mm)
    rep = dict(violations=sum(by_type.values()), by_type=by_type, parts=sorted(P.parts[i].ref for i in parts))
    if parts:
        rep["legalize"] = legalize(P, st, time_s=time_s, workers=workers, seed=seed, log=log, force=parts)
    return rep


# ----------------------------------------------------------------------------- exact shapes
def pad_shape(p, layer=None):
    """A pad's copper as a library-frame polygon, as KiCad shapes it: circles, ovals, rounded
    rectangles from the pad's fields; trapezoids, chamfered rectangles and custom pads (anchor
    and primitives) from the outline the loader built (Pad.outline). With `layer`, a padstack's
    override for that copper layer (Pad.layer_shapes) when it has one."""
    ov = (getattr(p, "layer_shapes", None) or {}).get(layer) if layer else None
    shape = ov["shape"] if ov else p.shape
    w, h = ov["size"] if ov else p.size
    ox, oy = (ov.get("offset") if ov and ov.get("offset") is not None else p.offset) or (0.0, 0.0)
    rratio = ov["rratio"] if ov else p.rratio
    outline = ov.get("outline") if ov else getattr(p, "outline", None)
    c, s = transform.cos_sin(p.lrot)

    def lib(u, v):
        return (p.lx + u * c + v * s, p.ly - u * s + v * c)
    if outline is not None and not outline.is_empty:
        from shapely import affinity
        geom = affinity.affine_transform(affinity.translate(outline, ox, oy), [c, s, -s, c, p.lx, p.ly])
    elif shape == "circle":
        cx, cy = lib(ox, oy)
        geom = Point(cx, cy).buffer(max(w, h) / 2, quad_segs=8)
    elif shape == "oval" and abs(w - h) > 1e-9:
        r = min(w, h) / 2
        if w > h:
            a, b = lib(ox - (w / 2 - r), oy), lib(ox + (w / 2 - r), oy)
        else:
            a, b = lib(ox, oy - (h / 2 - r)), lib(ox, oy + (h / 2 - r))
        geom = LineString([a, b]).buffer(r, quad_segs=8)
    elif shape == "oval":
        cx, cy = lib(ox, oy)
        geom = Point(cx, cy).buffer(w / 2, quad_segs=8)
    elif shape == "roundrect" and rratio > 0:
        # KiCad's rounded rectangle: corner radius rratio x the shorter side (as rectangles
        # the corners sat outside the copper; pingdevkit's 0402s read 0.191 mm apart, not 0.2)
        r = min(0.5, float(rratio)) * min(w, h)
        core = Polygon([(ox - w / 2 + r, oy - h / 2 + r), (ox + w / 2 - r, oy - h / 2 + r),
                        (ox + w / 2 - r, oy + h / 2 - r), (ox - w / 2 + r, oy + h / 2 - r)])
        loc = core.buffer(r, quad_segs=8) if r > 0 else core
        geom = Polygon([lib(u, v) for u, v in loc.exterior.coords])
    else:
        geom = Polygon([lib(ox - w / 2, oy - h / 2), lib(ox + w / 2, oy - h / 2), lib(ox + w / 2, oy + h / 2),
                        lib(ox - w / 2, oy + h / 2)])
    if p.drill:
        geom = geom.union(hole_shape(p))
    return geom


def hole_shape(p):
    if not p.drill:
        return None
    c, s = transform.cos_sin(p.lrot)
    if p.slot:
        w, h = p.slot
        r = min(w, h) / 2
        if abs(w - h) > 1e-9:
            if w > h:
                u0, u1, v0, v1 = -(w / 2 - r), (w / 2 - r), 0.0, 0.0
            else:
                u0, u1, v0, v1 = 0.0, 0.0, -(h / 2 - r), (h / 2 - r)
            a = (p.lx + u0 * c + v0 * s, p.ly - u0 * s + v0 * c)
            b = (p.lx + u1 * c + v1 * s, p.ly - u1 * s + v1 * c)
            return LineString([a, b]).buffer(r, quad_segs=8)
    return Point(p.lx, p.ly).buffer(p.drill / 2, quad_segs=8)


def _copper_sides(p, part_side):
    """Copper sides (0 front, 1 back) a pad occupies."""
    if is_drilled(p):
        return (0, 1)
    lays = p.layers or []
    sides = set()
    for ly in lays:
        if ly.startswith("F.Cu"):
            sides.add(0)
        elif ly.startswith("B.Cu"):
            sides.add(1)
        elif ly.endswith(".Cu"):
            sides.update((0, 1))
    if not sides:
        sides.add(0 if part_side == "F" else 1)
    return tuple(sorted(sides))


def exact_check(P, st, parts=None, max_items=60):
    """Exact legality of the placement (movable parts against everything). Returns a list of
    violations {type, refs, detail} (kae.place.exact.ExactModel holds the rules)."""
    from .exact import ExactModel
    return ExactModel(P, st).check(parts=parts, max_items=max_items)


def _net_clr(P, net, cache):
    if net in cache:
        return cache[net]
    v = P.clr_min
    n = P.board.nets.get(net) if net else None
    if n is not None:
        v = P.netclass_clr.get(n.netclass, P.netclass_clr.get(n.netclass.split(",")[0], P.clr_min))
    v = max(v, P.board.rules.clearance if P.board.rules else 0.0)
    cache[net] = v
    return v
