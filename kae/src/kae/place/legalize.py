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
import re
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


def legalize(P, st, time_s=30.0, workers=2, seed=0, k=8, max_rounds=8, log=None, force=()):
    """Repair grid violations in place (parts in `force` are re-placed in the first round even
    when the grid finds them legal, e.g. after a KiCad violation). Returns a report dict."""
    t0 = time.monotonic()
    deadline = t0 + time_s
    rep = dict(rounds=0, windows=0, solved=0, global_used=False, start_violators=0)
    kk = {}
    force = {i for i in force if P.parts[i].movable}
    for rnd in range(max_rounds):
        viol = grid_violations(st)
        if rnd == 0:
            rep["start_violators"] = len(viol)
            for i in force:
                viol.setdefault(i, []).append(("kicad", None))
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


def greedy(P, st, parts, log=None, w_rot=None):
    """Put `parts` back one by one, largest first, at the nearest grid origin (L1, plus a
    charge for turning) where none of their rectangles meets an obstacle or another part on
    its side and their board rectangles lie inside the outline; every other movable part
    stays where it is. The search window around the current origin doubles until a spot is
    found or it covers the board. Always ends legal for the parts it places; returns
    {placed, unplaced: [refs], moved_mm}."""
    t0 = time.monotonic()
    parts = sorted({i for i in parts if P.parts[i].movable}, key=lambda i: -P.parts[i].area)
    if not parts:
        return dict(placed=0, unplaced=[], moved_mm=0.0, seconds=0.0)
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
    placed, unplaced, moved = 0, [], 0.0
    for i in parts:
        p = P.parts[i]
        si = 0 if p.s > 0 else 1
        X0, Y0, K0 = int(st.X[i]), int(st.Y[i]), int(st.K[i])
        size = max(max(r.g_own[1] - r.g_own[0], r.g_own[3] - r.g_own[2]) for r in p.rots)
        R = max(20, 2 * size)
        best = None
        while True:
            xa, xb, ya, yb = X0 - R, X0 + R, Y0 - R, Y0 + R
            for k, r in enumerate(p.rots):
                ok = np.ones((xb - xa + 1, yb - ya + 1), dtype=bool)
                for brd in (r.g_boards or (r.g_board,)):
                    ok &= _inside_origins(P, brd, xa, xb, ya, yb)
                    if not ok.any():
                        break
                if not ok.any():
                    continue
                ok &= _free_origins(occ[si], r.g_own, pad, xa, xb, ya, yb)
                for o in r.g_opp:
                    if not ok.any():
                        break
                    ok &= _free_origins(occ[1 - si], o, pad, xa, xb, ya, yb)
                if not ok.any():
                    continue
                xs, ys = np.nonzero(ok)
                cost = np.abs(xs + xa - X0) + np.abs(ys + ya - Y0) + (w_rot if k != K0 else 0.0)
                j = int(np.argmin(cost))
                if best is None or cost[j] < best[0]:
                    best = (float(cost[j]), int(xs[j] + xa), int(ys[j] + ya), k)
            # a spot within R of the origin can still lose to one just outside when the best
            # cost exceeds R (L1 vs the square window): widen once more in that case
            if (best is not None and best[0] <= R) or R >= span:
                break
            R = min(span, 2 * R)
        if best is None:
            unplaced.append(i)
            continue
        _, X, Y, k = best
        moved += math.hypot((X - X0) * P.g, (Y - Y0) * P.g)
        st.X[i], st.Y[i], st.K[i] = X, Y, k
        for side, r, _ in st.grid_rects(i):
            _mark(occ[side], r, pad, 1)
        placed += 1
    rep = dict(placed=placed, unplaced=[P.parts[i].ref for i in unplaced], moved_mm=round(moved, 2),
               seconds=round(time.monotonic() - t0, 2))
    if log:
        log(f"greedy legalization: {placed} placed, {len(unplaced)} without a spot, moved {moved:.1f} mm "
            f"({rep['seconds']}s)")
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
    C3 on F.Cu', 'Footprint U1'), else the part with a pad nearest the item's position."""
    by_ref = {}
    for p in P.parts:
        by_ref.setdefault(p.ref, []).append(p.i)
    out = set()
    for it in v.get("items", []):
        d = it.get("description", "")
        m = _OF_REF.search(d) or _FP_REF.search(d)
        cands = by_ref.get(m.group(1), []) if m else []
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
            (i, _k, pa), (j, _l, pb) = meta[ia], meta[ib]
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
