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
import time

import numpy as np
import shapely
from shapely.geometry import LineString, Point, Polygon
from shapely.strtree import STRtree

from kae.board import transform

from . import cpsat
from .problem import edge_cut_polys, is_drilled
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
    return sol, model


def legalize(P, st, time_s=30.0, workers=2, seed=0, k=8, max_rounds=8, log=None):
    """Repair grid violations in place. Returns a report dict."""
    t0 = time.monotonic()
    deadline = t0 + time_s
    rep = dict(rounds=0, windows=0, solved=0, global_used=False, start_violators=0)
    kk = {}
    for rnd in range(max_rounds):
        viol = grid_violations(st)
        if rnd == 0:
            rep["start_violators"] = len(viol)
        if not viol:
            break
        rep["rounds"] = rnd + 1
        bad = set(viol)
        for gr in _groups(st, bad, radius_mm=4.0):
            now = time.monotonic()
            if now > deadline:
                break
            key = tuple(gr)
            kw = kk.get(key, k)
            cx = np.mean([st.center(b)[0] for b in gr])
            cy = np.mean([st.center(b)[1] for b in gr])
            near = sorted(P.mov, key=lambda c: abs(st.center(c)[0] - cx) + abs(st.center(c)[1] - cy))
            free = list(dict.fromkeys(gr + near[:kw]))
            margin = int(math.ceil((2.0 + 0.5 * (kw // k)) / P.g))
            budget = min(max(1.0, 0.15 * time_s), deadline - now)
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
    if viol and time.monotonic() < deadline:
        rep["global_used"] = True
        items = [cpsat.single(P, i, int(st.X[i]), int(st.Y[i]), int(st.K[i])) for i in P.mov]
        obstacles = [(ob.side, ob.g) for ob in P.obstacles]
        model = cpsat.Model(P, items, obstacles, w_disp=1.0, w_rot=1.0)
        sol = model.solve(max(1.0, deadline - time.monotonic()), workers=workers, seed=seed)
        rep["global_status"] = model.status
        if sol is not None:
            for i, (X, Y, v) in zip(P.mov, sol):
                st.X[i], st.Y[i], st.K[i] = X, Y, v
        viol = grid_violations(st)
    rep["end_violators"] = len(viol)
    rep["violations"] = {P.parts[i].ref: [str(r) for r in rs[:3]] for i, rs in list(viol.items())[:20]}
    rep["seconds"] = round(time.monotonic() - t0, 2)
    return rep


# ----------------------------------------------------------------------------- exact shapes
def pad_shape(p):
    """A pad's copper as a library-frame polygon (rounded rectangles as rectangles)."""
    w, h = p.size
    ox, oy = p.offset or (0.0, 0.0)
    c, s = transform.cos_sin(p.lrot)

    def lib(u, v):
        return (p.lx + u * c + v * s, p.ly - u * s + v * c)
    if p.shape == "circle":
        cx, cy = lib(ox, oy)
        geom = Point(cx, cy).buffer(max(w, h) / 2, quad_segs=8)
    elif p.shape == "oval" and abs(w - h) > 1e-9:
        r = min(w, h) / 2
        if w > h:
            a, b = lib(ox - (w / 2 - r), oy), lib(ox + (w / 2 - r), oy)
        else:
            a, b = lib(ox, oy - (h / 2 - r)), lib(ox, oy + (h / 2 - r))
        geom = LineString([a, b]).buffer(r, quad_segs=8)
    elif p.shape == "oval":
        cx, cy = lib(ox, oy)
        geom = Point(cx, cy).buffer(w / 2, quad_segs=8)
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


def _side_of_layer_pad(p, part, placed_side):
    """Pad layers in the model are for the footprint's current side; a pad keeps its side
    relative to the part (v0: sides never change)."""
    return _copper_sides(p, placed_side)


def exact_check(P, st, parts=None, max_items=60):
    """Exact legality of the placement (movable parts against everything). Returns a list of
    violations {type, refs, detail}."""
    board = P.board
    deflate = P.max_error
    shapes = {}
    for p in P.parts:
        x, y, rot, side = st.pose(p.i)
        fp = p.fp
        own = transform.courtyard(fp, x, y, rot, side, which="own", deflate=deflate)
        back = transform.courtyard(fp, x, y, rot, side, which="opposite", deflate=deflate)
        pads = []
        holes = []
        for k, pd in enumerate(fp.pads):
            geom = transform.place_geom(pad_shape(pd), x, y, rot, side)
            pads.append((geom, k, pd))
            if pd.drill:
                holes.append((transform.place_geom(hole_shape(pd), x, y, rot, side), k))
        si = 0 if p.s > 0 else 1
        cy_side = {si: shapely.union_all(own) if own else None,
                   1 - si: shapely.union_all(back) if back else None}
        shapes[p.i] = dict(cy=cy_side, pads=pads, holes=holes, side=si, body=None)
    check = set(parts if parts is not None else P.mov)
    out = []

    def add(kind, refs, detail=""):
        if len(out) < max_items:
            out.append(dict(type=kind, refs=refs, detail=detail))

    # courtyards per side
    for side in (0, 1):
        geoms, owners = [], []
        for i, sh in shapes.items():
            c = sh["cy"].get(side)
            if c is not None and not c.is_empty:
                geoms.append(c)
                owners.append(i)
        if len(geoms) > 1:
            tree = STRtree(geoms)
            a, b = tree.query(geoms, predicate="intersects")
            for ia, ib in zip(a.tolist(), b.tolist()):
                if ia >= ib:
                    continue
                pa, pb = owners[ia], owners[ib]
                if pa not in check and pb not in check:
                    continue
                if geoms[ia].intersection(geoms[ib]).area > 1e-6:
                    add("courtyards_overlap", [P.parts[pa].ref, P.parts[pb].ref], "FB"[side])
        # holes inside courtyards of other parts
        if geoms:
            tree = STRtree(geoms)
            for i, sh in shapes.items():
                for hgeom, k in sh["holes"]:
                    for j in tree.query(hgeom, predicate="intersects").tolist():
                        o = owners[j]
                        if o == i or (i not in check and o not in check):
                            continue
                        add("pth_inside_courtyard", [P.parts[i].ref, P.parts[o].ref], "FB"[side])
    # pad clearance between parts, per copper side
    clr_of = {}
    for side in (0, 1):
        geoms, meta = [], []
        for i, sh in shapes.items():
            for geom, k, pd in sh["pads"]:
                if side in _copper_sides(pd, P.parts[i].side):
                    geoms.append(geom)
                    meta.append((i, k, pd))
        if len(geoms) < 2:
            continue
        tree = STRtree(geoms)
        qa, qb = tree.query(geoms, predicate="dwithin", distance=P.clr_max)
        for ia, ib in zip(qa.tolist(), qb.tolist()):
            if ia >= ib:
                continue
            (i, k, pa), (j, l, pb) = meta[ia], meta[ib]
            if i == j or (i not in check and j not in check):
                continue
            if pa.net and pa.net == pb.net:
                continue
            need = max(_net_clr(P, pa.net, clr_of), _net_clr(P, pb.net, clr_of))
            d = geoms[ia].distance(geoms[ib])
            if d < need - 1e-4:
                add("clearance", [P.parts[i].ref, P.parts[j].ref], f"{pa.number}-{pb.number} {d:.3f}<{need:.3f}")
    # pads vs outline
    outline = P.outline
    boundary = outline.boundary
    e = P.edge_clearance
    for i in check:
        for geom, k, pd in shapes[i]["pads"]:
            c = geom.centroid
            if not outline.contains(c):
                add("pad_outside", [P.parts[i].ref], pd.number)
            elif e > 0 and geom.distance(boundary) < e - 1e-4:
                add("copper_edge_clearance", [P.parts[i].ref], f"{pd.number} {geom.distance(boundary):.3f}<{e}")
            elif not outline.contains(geom):
                add("copper_edge_clearance", [P.parts[i].ref], f"{pd.number} crosses the edge")
    # cut-outs that placed footprints carry (Edge.Cuts in the footprint)
    for p in P.parts:
        cuts = edge_cut_polys(p.fp)
        if not cuts:
            continue
        x, y, rot, side = st.pose(p.i)
        for c in cuts:
            cg = transform.place_geom(c, x, y, rot, side)
            cb = cg.boundary
            for i in check:
                if i == p.i:
                    continue
                for geom, k, pd in shapes[i]["pads"]:
                    if geom.distance(cb) < e - 1e-4 or cg.contains(geom.centroid):
                        add("copper_edge_clearance", [P.parts[i].ref, p.ref], f"{pd.number} near the cut-out of {p.ref}")
                cyo = shapes[i]["cy"].get(shapes[i]["side"])
                if cyo is not None and cyo.intersection(cg).area > 1e-6:
                    add("over_cutout", [P.parts[i].ref, p.ref], "courtyard over a cut-out")
    # fixed copper graphics (kept by place tasks) against pads of other nets
    for side, gm, net in getattr(P, "fixed_copper", []):
        for i in check:
            for geom, k, pd in shapes[i]["pads"]:
                if side not in _copper_sides(pd, P.parts[i].side) or (net and pd.net == net):
                    continue
                need = max(_net_clr(P, pd.net, clr_of), _net_clr(P, net, clr_of))
                if geom.distance(gm) < need - 1e-4:
                    add("clearance", [P.parts[i].ref], f"pad {pd.number} vs fixed copper {net}")
    # rule areas
    for ko in board.keepouts:
        if not (ko.footprints or ko.pads):
            continue
        for i in check:
            p = P.parts[i]
            if not _keepout_on_side(ko, p.side):
                continue
            sh = shapes[i]
            if ko.footprints:
                c = sh["cy"].get(sh["side"])
                if c is not None and c.intersects(ko.outline) and c.intersection(ko.outline).area > 1e-6:
                    add("items_not_allowed", [p.ref], f"keepout {ko.name}")
                    continue
            if any(g.intersects(ko.outline) for g, _, _ in sh["pads"]):
                add("items_not_allowed", [p.ref], f"keepout {ko.name} (pads)")
    return out


def _keepout_on_side(ko, side):
    lays = ko.layers or []
    if not lays:
        return True
    for ly in lays:
        if ly.startswith(side + ".") or ly in ("*.Cu", "F&B.Cu") or ly.startswith("In"):
            return True
    return False


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
