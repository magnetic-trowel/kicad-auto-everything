# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Constructive seed: quadratic placement with net springs, spreading, CP-SAT floorplan.

1. `quadratic`: object centres minimize the weighted squared spring length of every net
   (clique model, weight w_net / (pins - 1); ground and power nets down-weighted, H11;
   structure nets from the brief up-weighted). Locked parts are anchors through their pins;
   connectors are pulled to the nearest point of the board edge; a weak spring to the board
   centre keeps the system non-singular.
2. `spread`: overlap removal by pairwise repulsion of the objects' rectangles, inside the
   board, with the net springs still acting (a few hundred cheap numpy iterations); or, on
   boards too big for the floorplan, `partition_spread`: recursive bisection of the free
   cells per side in proportion to object area (density-feasible, order-preserving).
3. `floorplan`: CP-SAT places the objects (single parts or rigid macros) on the grid with
   4 rotations, NoOverlap2D per side and the outline, minimizing displacement from the
   spread positions plus weighted HPWL.
"""
from __future__ import annotations

import math

import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as spla

from . import cpsat


def _objects(P, macros):
    """Objects of the seed: each macro is one object, each other movable part another.
    Returns (objs, owner): objs = [(members, w, h, rel)] where rel[i] = (dx, dy) mm of the
    member's origin from the object centre; owner[part] = object index."""
    in_macro = {}
    objs = []
    for mac in macros or []:
        lay = mac.layouts[0]
        w, h = lay.size
        # layout offsets are grid cells, its centre is in mm
        rel = {i: (dx * P.g - lay.cx, dy * P.g - lay.cy) for i, (dx, dy, k) in lay.offsets.items()}
        objs.append((list(lay.offsets), w, h, rel))
        for i in lay.offsets:
            in_macro[i] = len(objs) - 1
    for i in P.mov:
        if i in in_macro:
            continue
        r = P.parts[i].rots[0].own
        w, h = r[2] - r[0], r[3] - r[1]
        cx, cy = (r[0] + r[2]) / 2, (r[1] + r[3]) / 2
        objs.append(([i], w, h, {i: (-cx, -cy)}))
        in_macro[i] = len(objs) - 1
    return objs, in_macro


def quadratic(P, objs, owner, net_w, anchors=None, center_w=1e-3):
    """Object centres (n, 2) minimizing the net-spring energy."""
    n = len(objs)
    if n == 0:
        return np.zeros((0, 2))
    x0, y0, x1, y1 = P.outline.bounds
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    rows, cols, vals = [], [], []
    bx = np.zeros(n)
    by = np.zeros(n)
    diag = np.full(n, center_w)
    bx += center_w * cx
    by += center_w * cy
    for net in P.nets:
        w = net_w.get(net.i, net.weight)
        if w <= 0:
            continue
        mov = sorted({owner[i] for (i, k) in net.pins if i in owner})
        fixed = [(i, k) for (i, k) in net.pins if i not in owner]
        npins = len(mov) + len(fixed)
        if npins < 2 or not mov:
            continue
        wc = w / (npins - 1)
        for a_idx in range(len(mov)):
            a = mov[a_idx]
            for b in mov[a_idx + 1:]:
                rows += [a, b]
                cols += [b, a]
                vals += [-wc, -wc]
                diag[a] += wc
                diag[b] += wc
            for (i, k) in fixed:
                fx, fy = P.parts[i].rots[0].pins[k] + np.array([P.parts[i].x0, P.parts[i].y0])
                diag[a] += wc
                bx[a] += wc * fx
                by[a] += wc * fy
    for (o, (ax, ay, w)) in (anchors or {}).items():
        diag[o] += w
        bx[o] += w * ax
        by[o] += w * ay
    L = sp.coo_matrix((vals + diag.tolist(), (rows + list(range(n)), cols + list(range(n)))), shape=(n, n)).tocsr()
    x = spla.spsolve(L, bx)
    y = spla.spsolve(L, by)
    return np.column_stack([x, y])


def _edge_point(P, x, y):
    """Nearest point of the board edge (outline boundary)."""
    from shapely.geometry import Point
    b = P.outline.boundary
    q = b.interpolate(b.project(Point(x, y)))
    return q.x, q.y


def connector_anchors(P, objs, pos, weight):
    """Anchors pulling every object that holds a connector to just inside the nearest board
    edge (mechanics puts connectors there, and it keeps them out of the routing core)."""
    from shapely.geometry import Point
    anchors = {}
    cx, cy = P.outline.centroid.x, P.outline.centroid.y
    for o, (members, w, h, rel) in enumerate(objs):
        if not any(getattr(P.parts[i], "kind", "") == "connector" for i in members):
            continue
        x, y = pos[o]
        qx, qy = _edge_point(P, x, y)
        inside = P.outline.contains(Point(x, y))
        dx, dy = (x - qx, y - qy) if inside else (cx - qx, cy - qy)
        L = math.hypot(dx, dy) or 1.0
        inset = 0.5 * min(w, h) + P.edge_clearance + 0.5
        anchors[o] = (qx + dx / L * inset, qy + dy / L * inset, weight)
    return anchors


def spread(P, objs, pos, owner, net_w, iters=300, seed=0):
    """Push overlapping objects apart inside the board; springs keep nets together."""
    rng = np.random.default_rng(seed)
    n = len(objs)
    if n == 0:
        return pos
    W = np.array([o[1] for o in objs]) + 0.2
    H = np.array([o[2] for o in objs]) + 0.2
    x0, y0, x1, y1 = P.outline.bounds
    pos = pos.copy() + rng.normal(0, 0.05 * max(x1 - x0, y1 - y0) / max(1, math.sqrt(n)), size=pos.shape)
    # board area vs object area: shrink objects in the repulsion if the board is very full
    pairs = []
    for net in P.nets:
        w = net_w.get(net.i, net.weight)
        objs_n = sorted({owner[i] for (i, k) in net.pins if i in owner})
        if len(objs_n) < 2 or w <= 0:
            continue
        wc = w / (len(objs_n) - 1)
        for a_i in range(len(objs_n)):
            for b in objs_n[a_i + 1:]:
                pairs.append((objs_n[a_i], b, wc))
    if pairs:
        pa = np.array([p[0] for p in pairs])
        pb = np.array([p[1] for p in pairs])
        pw = np.array([p[2] for p in pairs])
        pw = pw / pw.max()
    for t in range(iters):
        dx = pos[:, None, 0] - pos[None, :, 0]
        dy = pos[:, None, 1] - pos[None, :, 1]
        ox = (W[:, None] + W[None, :]) / 2 - np.abs(dx)
        oy = (H[:, None] + H[None, :]) / 2 - np.abs(dy)
        ov = (ox > 0) & (oy > 0)
        np.fill_diagonal(ov, False)
        fx = np.zeros(n)
        fy = np.zeros(n)
        if ov.any():
            # separate along the axis of least penetration
            use_x = ox < oy
            sx = np.where(dx >= 0, 1.0, -1.0)
            sy = np.where(dy >= 0, 1.0, -1.0)
            mx = np.where(ov & use_x, ox * sx, 0.0)
            my = np.where(ov & ~use_x, oy * sy, 0.0)
            fx += 0.5 * mx.sum(axis=1)
            fy += 0.5 * my.sum(axis=1)
        if pairs:
            k = 0.05 * (1.0 - t / iters)
            ddx = pos[pb, 0] - pos[pa, 0]
            ddy = pos[pb, 1] - pos[pa, 1]
            np.add.at(fx, pa, k * pw * ddx)
            np.add.at(fx, pb, -k * pw * ddx)
            np.add.at(fy, pa, k * pw * ddy)
            np.add.at(fy, pb, -k * pw * ddy)
        step = 0.5
        pos[:, 0] += step * fx
        pos[:, 1] += step * fy
        pos[:, 0] = np.clip(pos[:, 0], x0 + W / 2, np.maximum(x0 + W / 2, x1 - W / 2))
        pos[:, 1] = np.clip(pos[:, 1], y0 + H / 2, np.maximum(y0 + H / 2, y1 - H / 2))
        if not ov.any() and t > iters // 3:
            break
    return pos


def _object_side(P, members):
    big = max(members, key=lambda i: P.parts[i].area)
    return 0 if P.parts[big].s > 0 else 1


def _free_raster(P, side, extra=()):
    """Cells inside the outline and not under a fixed obstacle on `side` (or a grid rect in
    `extra`)."""
    free = P.inside.copy()
    for ob in list(P.obstacles):
        if ob.side == side:
            i0, i1, j0, j1 = ob.g
            free[max(0, i0):max(0, i1), max(0, j0):max(0, j1)] = False
    for (i0, i1, j0, j1) in extra:
        free[max(0, i0):max(0, i1), max(0, j0):max(0, j1)] = False
    return free


def partition_spread(P, objs, pos, target=0.8):
    """Density-feasible spreading by recursive bisection (quadratic placement followed by
    recursive partitioning, after Gordian): per side, the board's free cells (inside the
    outline, not under a fixed obstacle) are cut in proportion to the area of the objects on
    either side of a cut through their current order, along the longer axis of the region,
    until each region holds one object, which goes to the centroid of its region's free
    cells. The quadratic order and neighbourhoods survive, density follows the board's shape,
    and objects of the other side do not compete for space. Front objects go first; the cells
    their drilled (through) parts take are then closed on the back. Returns positions (n, 2)."""
    from .problem import sat
    g = P.g
    n = len(objs)
    out = np.array(pos, dtype=float).copy()
    if n == 0:
        return out
    m = getattr(P, "margin", 0.0) or 0.0
    area = np.array([max(1.0, (w + m) * (h + m) / (g * g)) for (_, w, h, _) in objs])
    sides = [_object_side(P, members) for (members, _, _, _) in objs]
    through = [any(P.parts[i].tht for i in members) for (members, _, _, _) in objs]
    extra_back = []
    for side in (0, 1):
        ids = [o for o in range(n) if sides[o] == side]
        if not ids:
            continue
        free = _free_raster(P, side, extra_back if side == 1 else ())
        if not free.any():
            continue
        F = sat(free)
        ii = np.arange(P.ncx)[:, None] * free
        jj = np.arange(P.ncy)[None, :] * free
        FI, FJ = sat(ii), sat(jj)

        def q(S, i0, i1, j0, j1):
            return float(S[i1, j1] - S[i0, j1] - S[i1, j0] + S[i0, j0])
        stack = [((0, P.ncx, 0, P.ncy), ids)]
        while stack:
            (i0, i1, j0, j1), objs_r = stack.pop()
            if not objs_r:
                continue
            cap = q(F, i0, i1, j0, j1)
            if len(objs_r) == 1 or (i1 - i0 < 2 and j1 - j0 < 2) or cap <= 0:
                if cap > 0:
                    cx = (q(FI, i0, i1, j0, j1) / cap + 0.5) * g + P.ox
                    cy = (q(FJ, i0, i1, j0, j1) / cap + 0.5) * g + P.oy
                else:
                    cx, cy = P.ox + (i0 + i1) / 2 * g, P.oy + (j0 + j1) / 2 * g
                for o in objs_r:
                    out[o] = (cx, cy)
                continue
            along_x = (i1 - i0) >= (j1 - j0)
            if (i1 - i0 < 2) if along_x else (j1 - j0 < 2):
                along_x = not along_x
            ax = 0 if along_x else 1
            objs_r = sorted(objs_r, key=lambda o: out[o, ax])
            a = area[objs_r]
            cum = np.cumsum(a)
            k = int(np.argmin(np.abs(cum[:-1] - cum[-1] / 2.0))) + 1      # objects [0, k) go low
            frac = cum[k - 1] / cum[-1]
            lo, hi = (i0, i1) if along_x else (j0, j1)
            # capacity below each cut position, then the cut matching the area share
            cuts = np.arange(lo + 1, hi)
            if along_x:
                below = F[cuts, j1] - F[i0, j1] - F[cuts, j0] + F[i0, j0]
            else:
                below = F[i1, cuts] - F[i0, cuts] - F[i1, j0] + F[i0, j0]
            c = int(cuts[int(np.argmin(np.abs(below / cap - frac)))])
            if along_x:
                stack.append(((i0, c, j0, j1), objs_r[:k]))
                stack.append(((c, i1, j0, j1), objs_r[k:]))
            else:
                stack.append(((i0, i1, j0, c), objs_r[:k]))
                stack.append(((i0, i1, c, j1), objs_r[k:]))
        if side == 0:
            for o in ids:
                if through[o]:
                    w, h = objs[o][1], objs[o][2]
                    i_c, j_c = (out[o, 0] - P.ox) / g, (out[o, 1] - P.oy) / g
                    extra_back.append((int(i_c - w / 2 / g), int(math.ceil(i_c + w / 2 / g)),
                                       int(j_c - h / 2 / g), int(math.ceil(j_c + h / 2 / g))))
    return out


def floorplan(P, items, time_s, workers=2, seed=0, w_wl=1.0, w_disp=0.2, net_w=None, log=None):
    """CP-SAT placement of items from their (X0, Y0, v0) starts. Returns [(X, Y, v)] or None."""
    nets = []
    if w_wl > 0:
        owner = {i for it in items for i in it.members}
        for net in P.nets:
            w = (net_w or {}).get(net.i, net.weight)
            if w <= 0:
                continue
            pins = [(i, k) for (i, k) in net.pins if i in owner]
            fixed = []
            for (i, k) in net.pins:
                if i in owner:
                    continue
                p = P.parts[i]
                if p.movable:
                    continue  # a movable part outside the model: ignore
                fx, fy = p.rots[0].pins[k] + np.array([p.x0, p.y0])
                fixed.append((int(round((fx - P.ox) / P.g)), int(round((fy - P.oy) / P.g))))
            if len(pins) + len(fixed) >= 2 and pins:
                nets.append((w, pins, fixed))
    obstacles = [(ob.side, ob.g) for ob in P.obstacles]
    model = cpsat.Model(P, items, obstacles, hpwl_nets=nets, w_disp=w_disp, w_rot=0.0, w_wl=w_wl)
    sol = model.solve(time_s, workers=workers, seed=seed)
    if log:
        log(f"floorplan items={len(items)} nets={len(nets)} status={model.status} {model.wall:.1f}s"
            + (f" infeasible={model.infeasible_items}" if model.infeasible_items else ""))
    return sol, model


def regional_refine(P, st, macros, net_w, time_s, workers=1, seed=0, log=None, max_items=30, margin_mm=2.0):
    """Floorplan a big board region by region (the global CP-SAT floorplan handles at most
    FLOORPLAN_MAX_ITEMS items): the items (unanchored macros as rigid layouts x 4 rotations,
    single parts) are cut by recursive bisection of their centres into regions of at most
    `max_items`; each region is re-placed by CP-SAT inside its window (plus margin_mm),
    minimizing weighted HPWL with a little displacement, with every part outside it fixed (an
    obstacle, and a fixed pin of the nets it shares). Legal in, legal out: a region keeps its
    placement unless CP-SAT returns one. Returns a report."""
    import time as _time
    from . import clusters
    from .state import grid_violations
    t0 = _time.monotonic()
    g = P.g
    items, anchors, owner = [], [], {}
    for mac in macros or []:
        if mac.anchored or not all(P.parts[i].movable for i in mac.members):
            continue
        a = mac.anchor
        it = clusters.macro_item(P, mac, int(st.X[a]), int(st.Y[a]), 0)
        items.append(it)
        anchors.append(a)
        for i in mac.members:
            owner[i] = len(items) - 1
    for i in P.mov:
        if i not in owner:
            items.append(cpsat.single(P, i, int(st.X[i]), int(st.Y[i]), int(st.K[i])))
            anchors.append(i)
            owner[i] = len(items) - 1
    if not items:
        return dict(regions=0)

    def centre(it):
        xs = [st.center(i)[0] for i in it.members]
        ys = [st.center(i)[1] for i in it.members]
        return sum(xs) / len(xs), sum(ys) / len(ys)
    cen = [centre(it) for it in items]
    # regions: recursive bisection of the item centres
    regions = []
    stack = [list(range(len(items)))]
    while stack:
        ids = stack.pop()
        if len(ids) <= max_items:
            regions.append(ids)
            continue
        xs = [cen[o][0] for o in ids]
        ys = [cen[o][1] for o in ids]
        ax = 0 if (max(xs) - min(xs)) >= (max(ys) - min(ys)) else 1
        ids = sorted(ids, key=lambda o: cen[o][ax])
        h = len(ids) // 2
        stack += [ids[:h], ids[h:]]
    per = max(1.0, time_s / max(1, len(regions)))
    m = int(math.ceil(margin_mm / g))
    rep = dict(regions=len(regions), solved=0, hpwl_before=round(st.hpwl(), 2))
    for ids in regions:
        if _time.monotonic() - t0 > time_s:
            break
        mem = {i for o in ids for i in items[o].members}
        rects = [r for i in mem for (_, r, _) in st.grid_rects(i)]
        wi0 = min(r[0] for r in rects) - m
        wi1 = max(r[1] for r in rects) + m
        wj0 = min(r[2] for r in rects) - m
        wj1 = max(r[3] for r in rects) + m
        ext = max(max(r[1] - r[0], r[3] - r[2]) for r in rects) + 2
        obstacles = []
        for i in P.mov:
            if i in mem:
                continue
            for side, r, _ in st.grid_rects(i):
                if r[1] > wi0 - ext and r[0] < wi1 + ext and r[3] > wj0 - ext and r[2] < wj1 + ext:
                    obstacles.append((side, r))
        for ob in P.obstacles:
            r = ob.g
            if r[1] > wi0 - ext and r[0] < wi1 + ext and r[3] > wj0 - ext and r[2] < wj1 + ext:
                obstacles.append((ob.side, r))
        its = []
        for o in ids:
            it = items[o]
            it.X0, it.Y0 = int(st.X[anchors[o]]), int(st.Y[anchors[o]])
            it.bounds = (wi0, wi1, wj0, wj1)
            its.append(it)
        nets = []
        for net in P.nets:
            w = net_w.get(net.i, net.weight)
            if w <= 0:
                continue
            pins = [(i, k) for (i, k) in net.pins if i in mem]
            if not pins:
                continue
            fixed = []
            for (i, k) in net.pins:
                if i in mem:
                    continue
                x, y = st.pins_xy(i)[k]
                fixed.append((int(round((x - P.ox) / g)), int(round((y - P.oy) / g))))
            if len(pins) + len(fixed) >= 2:
                nets.append((w, pins, fixed))
        model = cpsat.Model(P, its, obstacles, hpwl_nets=nets, w_disp=0.05, w_rot=0.0, w_wl=1.0)
        sol = model.solve(min(per, max(0.5, time_s - (_time.monotonic() - t0))), workers=workers, seed=seed)
        if sol is None:
            continue
        before = st.copy()
        for it, (X, Y, v) in zip(its, sol):
            for i, (dx, dy, k) in it.variants[v].items():
                if P.parts[i].movable:
                    st.X[i], st.Y[i], st.K[i] = X + dx, Y + dy, k
        if set(grid_violations(st)) & mem:
            st.X[:], st.Y[:], st.K[:] = before.X, before.Y, before.K
            continue
        rep["solved"] += 1
    rep["hpwl_after"] = round(st.hpwl(), 2)
    rep["seconds"] = round(_time.monotonic() - t0, 2)
    if log:
        log(f"regional floorplan: {rep['solved']}/{rep['regions']} regions, HPWL {rep['hpwl_before']} -> "
            f"{rep['hpwl_after']} ({rep['seconds']}s)")
    return rep
