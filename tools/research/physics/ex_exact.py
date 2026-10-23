# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Exact (finer) evaluators of the place-term structures at given poses, on real board
geometry (docs/topics/physics/exact-physics-options.md).

The place terms (kae.physics.place_terms.Terms) price each structure from straight
pad-to-pad hops with closed forms. This module evaluates the same structure, at the same
poses, with the geometry and solvers the validation used as references
(docs/topics/physics/place-terms.md), so that ex_cost_table.py can time them and
ex_decision_flips.py can count where they rank candidate placements differently.

Loops (commutation cells, decap loops, ESD surge paths). Every board hop is routed around
other nets' pads (pads inflated by half the minimum track width plus the clearance, as
pt_grid_route.HopRouter) and around the loop's copper already routed for other nets (two nets
cannot cross on one layer), on a 0.1 mm grid, in one of two styles:
  any        8-connected Dijkstra, then string-pulled on the obstacle raster (any angle, as
             the critical router's A* plus string pulling);
  manhattan  4-connected Dijkstra with a turn penalty (axis-aligned, so pw_peec can mesh it).
Hops leave from the terminal pad nearest the next terminal; a part's internal path runs from
the pad the current arrives at to the pad it leaves from (body strip at the body height with
vertical ties, as kae.physics.structures.LoopComp); a ground hop over a plane of its own net is
the routed surface track in parallel with two vias through the plane. Evaluators (mode):
  cf         closed forms on the any-angle routed pieces (kae.route.critical_physics.Loop:
             partial inductances with images, Hammerstad-Jensen strip self terms, energy-
             minimizing split between parallel return paths), i.e. the module stage's model;
  cfm        the same closed forms on the Manhattan route;
  peec       multi-filament PEEC (pw_peec filaments, PEC image plane) on the Manhattan route,
             solved in the inductive limit (real arithmetic: L_port = [(A L^-1 A')^-1]_pp);
  detour     the estimator plus L'(w, h) x (routed - straight length) per board hop
             (pt_human_perturb.hop_detour_nH): the cheapest route-aware correction.
A loop whose terminals sit on both board sides, or a hop with no single-layer route (BGA
escapes, enclosed pins), has no value here (None with a reason): it needs vias and a
multi-plane model. Plane-pair decap loops keep the estimator's closed form, which matches a
sheet solve to 0.4 %.

Crystal: Pierce pulling with the per-length capacitance from fe_field2d (cached per height)
times the routed length of the XIN/XOUT connections.

Thermal: steady 2.5-D finite volume (tm_board_thermal_fv's operator) over the board's
bounding box with every copper layer, the zones' coverage per layer as placed, FR-4 and
h = 10 W/m^2 K per side; heat enters the part's courtyard box on its outer layer
(inject='surface') or every layer under it (inject='stack': a perfectly stitched footprint).
One factorization per board, one solve per source position (superposition), cached by
source pose, so a victim's move costs a lookup.

Coupling (inductive part): the aggressor loop's filament currents from PEEC on its Manhattan
route, and the EMF they induce along the victim's Manhattan-routed probe path
(pw_peec.Net.induced); the capacitive part is left to the estimator.

Not a script: imported by the other ex_*.py scripts. Needs kae (kae/.venv).
"""
from __future__ import annotations

import math
import os
import sys
import time
from pathlib import Path

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / 'kae' / 'src'))
sys.path.insert(0, str(HERE))

import numpy as np  # noqa: E402
import scipy.linalg as sla  # noqa: E402
import scipy.sparse as sp  # noqa: E402
import scipy.sparse.linalg as spla  # noqa: E402
from scipy.sparse.csgraph import dijkstra  # noqa: E402

import pw_peec as pw  # noqa: E402
from kae.physics.kernels import cprime_hj, lprime_hj  # noqa: E402
from kae.physics.structures import (CouplingComp, CrystalComp, EsdComp, LoopComp, NearestLoopComp,  # noqa: E402
                                    PlanePairLoop, txy)
from kae.route.critical_physics import Loop  # noqa: E402

INF = float('inf')
MM = 1e-3
RVIA = 0.15
T_CU = 0.035
# Overlapping filaments (a route jogging by less than its own width) make the partial-
# inductance matrix indefinite. False: such a geometry has no PEEC value (excluded);
# True: clip the negative eigenvalues (counted in PEEC_CLIPPED).
PEEC_CLIP = False
PEEC_CLIPPED = [0]


# ============================================================================ routing
class Router:
    """Shortest legal route of one hop on one side, around other nets' pads (mm)."""

    def __init__(self, T, res=0.1, margin=3.0, max_cells=90_000, turn=0.2):
        from pt_grid_route import HopRouter
        self.T = T
        self.hr = HopRouter(T.bv, res=res, margin=margin, max_cells=max_cells)
        self.res = res
        self.margin = margin
        self.max_cells = max_cells
        self.turn = turn
        self.pads = None
        self.stats = dict(calls=0, seconds=0.0, cells=0)

    def refresh(self):
        """Pad positions at the current state (call after the poses change)."""
        self.pads = self.hr.pads_board(self.T.st)

    def _raster(self, side, a, b, nets, w, avoid=()):
        bv = self.T.bv
        (ax, ay), (bx, by) = a, b
        straight = math.hypot(bx - ax, by - ay)
        res = self.res
        m = max(self.margin, 0.5 * straight)
        x0, y0 = min(ax, bx) - m, min(ay, by) - m
        x1, y1 = max(ax, bx) + m, max(ay, by) + m
        nx = int(math.ceil((x1 - x0) / res)) + 1
        ny = int(math.ceil((y1 - y0) / res)) + 1
        while nx * ny > self.max_cells:
            res *= 1.5
            nx = int(math.ceil((x1 - x0) / res)) + 1
            ny = int(math.ceil((y1 - y0) / res)) + 1
        px, py, hx, hy, G = self.pads
        hr = self.hr
        own = np.array([hr.net_id.get(n, -1) for n in nets], np.int64)
        on_side = hr.tht | (G == side)
        infl = 0.5 * min(w, bv.track_min) + bv.clearance
        sel = on_side & ~np.isin(hr.nid, own) & (px + hx + infl >= x0) & (px - hx - infl <= x1) & \
            (py + hy + infl >= y0) & (py - hy - infl <= y1)
        blocked = np.zeros((ny, nx), bool)
        for cx, cy, ex, ey in zip(px[sel], py[sel], hx[sel] + infl, hy[sel] + infl):
            i0 = max(0, int(math.ceil((cx - ex - x0) / res)))
            i1 = min(nx - 1, int(math.floor((cx + ex - x0) / res)))
            j0 = max(0, int(math.ceil((cy - ey - y0) / res)))
            j1 = min(ny - 1, int(math.floor((cy + ey - y0) / res)))
            if i1 >= i0 and j1 >= j0:
                blocked[j0:j1 + 1, i0:i1 + 1] = True
        yy, xx = np.mgrid[0:ny, 0:nx]
        if avoid:
            # copper of the same loop already routed (other nets): a trace cannot cross it
            X = xx * res + x0
            Y = yy * res + y0
            for pts, hw in avoid:
                for (p0x, p0y), (p1x, p1y) in zip(pts[:-1], pts[1:]):
                    dx, dy = p1x - p0x, p1y - p0y
                    l2 = dx * dx + dy * dy
                    t = np.clip(((X - p0x) * dx + (Y - p0y) * dy) / l2, 0.0, 1.0) if l2 > 1e-12 else 0.0
                    d2 = (X - p0x - t * dx) ** 2 + (Y - p0y - t * dy) ** 2
                    blocked |= d2 <= (hw + infl) ** 2
        r = max(infl, 0.3)
        for (qx, qy) in ((ax, ay), (bx, by)):
            blocked[((xx * res + x0 - qx) ** 2 + (yy * res + y0 - qy) ** 2) <= r * r] = False
        s = (min(ny - 1, max(0, int(round((ay - y0) / res)))), min(nx - 1, max(0, int(round((ax - x0) / res)))))
        g = (min(ny - 1, max(0, int(round((by - y0) / res)))), min(nx - 1, max(0, int(round((bx - x0) / res)))))
        blocked[s] = False
        blocked[g] = False
        return ~blocked, s, g, x0, y0, res, straight

    def route(self, side, a, b, nets, w, style='any', avoid=()):
        """Polyline [(x, y), ...] from a to b, or None when no route exists in the window.
        avoid: [(polyline, half width)] of copper already routed for other nets."""
        t0 = time.process_time()
        try:
            free, s, g, x0, y0, res, straight = self._raster(side, a, b, nets, w, avoid)
            if straight < 1e-6:
                return [tuple(a), tuple(b)]
            if style == 'manhattan':
                cells = _route_manhattan(free, s, g, res, self.turn)
            else:
                cells = _route_any(free, s, g, res)
            if cells is None:
                return None
            pts = [(x0 + i * res, y0 + j * res) for (j, i) in cells]
            if style == 'manhattan':
                pts = _simplify_manhattan(pts)
                return _manhattan_ends(pts, a, b)
            pts = _pull(free, cells, x0, y0, res)
            pts[0], pts[-1] = tuple(a), tuple(b)
            return pts
        finally:
            self.stats['calls'] += 1
            self.stats['seconds'] += time.process_time() - t0     # CPU seconds


def _grid_edges(free, dirs):
    ny, nx = free.shape
    idx = -np.ones((ny, nx), np.int64)
    nf = int(free.sum())
    idx[free] = np.arange(nf)
    out = []
    for d, (dj, di, cost) in enumerate(dirs):
        Aj = slice(max(0, -dj), ny - max(0, dj))
        Ai = slice(max(0, -di), nx - max(0, di))
        Bj = slice(max(0, dj), ny - max(0, -dj))
        Bi = slice(max(0, di), nx - max(0, -di))
        ok = free[Aj, Ai] & free[Bj, Bi]
        if di != 0 and dj != 0:
            ok &= free[Aj, Bi] & free[Bj, Ai]
        out.append((d, idx[Aj, Ai][ok], idx[Bj, Bi][ok], cost))
    return idx, nf, out


def _route_any(free, s, g, res):
    r2 = res * math.sqrt(2.0)
    dirs = ((0, 1, res), (1, 0, res), (1, 1, r2), (1, -1, r2))
    idx, nf, E = _grid_edges(free, dirs)
    r = np.concatenate([e[1] for e in E] + [e[2] for e in E])
    c = np.concatenate([e[2] for e in E] + [e[1] for e in E])
    wv = np.concatenate([np.full(e[1].size, e[3]) for e in E] * 2)
    M = sp.csr_matrix((wv, (r, c)), shape=(nf, nf))
    si, gi = idx[s], idx[g]
    dist, pred = dijkstra(M, directed=True, indices=si, return_predecessors=True)
    if not np.isfinite(dist[gi]):
        return None
    jj, ii = np.nonzero(free)
    path = []
    k = gi
    while k >= 0:
        path.append((int(jj[k]), int(ii[k])))
        if k == si:
            break
        k = pred[k]
    return path[::-1]


def _route_manhattan(free, s, g, res, turn):
    """4-connected shortest path with a turn penalty (state = cell x direction)."""
    dirs = ((0, 1, res), (1, 0, res), (0, -1, res), (-1, 0, res))
    idx, nf, E = _grid_edges(free, dirs)
    D = 4
    rows, cols, wts = [], [], []
    for d, a, b, cost in E:
        rows.append(a * D + d)
        cols.append(b * D + d)
        wts.append(np.full(a.size, cost))
    allc = np.arange(nf)
    for d in range(D):
        for d2 in ((d + 1) % D, (d + 3) % D):
            rows.append(allc * D + d)
            cols.append(allc * D + d2)
            wts.append(np.full(nf, turn))
    M = sp.csr_matrix((np.concatenate(wts), (np.concatenate(rows), np.concatenate(cols))), shape=(nf * D, nf * D))
    si, gi = idx[s], idx[g]
    dist, pred, src = dijkstra(M, directed=True, indices=[si * D + d for d in range(D)], min_only=True,
                               return_predecessors=True)
    best = min(range(D), key=lambda d: dist[gi * D + d])
    k = gi * D + best
    if not np.isfinite(dist[k]):
        return None
    jj, ii = np.nonzero(free)
    path = []
    while k >= 0:
        c = k // D
        if not path or path[-1] != (int(jj[c]), int(ii[c])):
            path.append((int(jj[c]), int(ii[c])))
        if c == si and src[k] == k:
            break
        k = pred[k]
    return path[::-1]


def _simplify_manhattan(pts):
    """Merge consecutive collinear runs that keep their direction."""
    out = [pts[0]]
    for p in pts[1:]:
        if len(out) >= 2:
            a, b = out[-2], out[-1]
            same_x = abs(a[0] - b[0]) < 1e-9 and abs(b[0] - p[0]) < 1e-9
            same_y = abs(a[1] - b[1]) < 1e-9 and abs(b[1] - p[1]) < 1e-9
            forward = (b[0] - a[0]) * (p[0] - b[0]) + (b[1] - a[1]) * (p[1] - b[1]) >= 0.0
            if (same_x or same_y) and forward:
                out[-1] = p
                continue
        out.append(p)
    return out


def _manhattan_ends(pts, a, b):
    """Move the grid-snapped end points onto the true ones (less than half a cell away),
    shifting the first and last runs sideways so that every run stays axis-aligned."""
    pts = [list(p) for p in pts]
    if len(pts) == 1:
        pts.append(list(pts[0]))
    if len(pts) == 2:
        # one straight run: an L between the true end points
        out = [tuple(a), (b[0], a[1]), tuple(b)] if abs(pts[0][1] - pts[1][1]) < 1e-9 else \
            [tuple(a), (a[0], b[1]), tuple(b)]
    else:
        horiz0 = abs(pts[0][1] - pts[1][1]) < 1e-9
        pts[0] = [a[0], a[1]]
        if horiz0:
            pts[1][1] = a[1]
        else:
            pts[1][0] = a[0]
        horiz1 = abs(pts[-1][1] - pts[-2][1]) < 1e-9
        pts[-1] = [b[0], b[1]]
        if horiz1:
            pts[-2][1] = b[1]
        else:
            pts[-2][0] = b[0]
        out = [tuple(p) for p in pts]
    clean = [out[0]]
    for p in out[1:]:
        if math.hypot(p[0] - clean[-1][0], p[1] - clean[-1][1]) > 1e-6:
            clean.append(p)
    return _simplify_manhattan(clean)


def _visible(free, x0, y0, res, p, q):
    n = max(2, int(math.hypot(q[0] - p[0], q[1] - p[1]) / (0.3 * res)) + 1)
    t = np.linspace(0.0, 1.0, n)
    xs = p[0] + t * (q[0] - p[0])
    ys = p[1] + t * (q[1] - p[1])
    ii = np.clip(np.round((xs - x0) / res).astype(int), 0, free.shape[1] - 1)
    jj = np.clip(np.round((ys - y0) / res).astype(int), 0, free.shape[0] - 1)
    return bool(free[jj, ii].all())


def _pull(free, cells, x0, y0, res):
    """Line-of-sight smoothing: from each anchor, extend while the straight piece stays on
    free cells."""
    pts = [(x0 + i * res, y0 + j * res) for (j, i) in cells]
    out = [pts[0]]
    k = 0
    n = len(pts)
    while k < n - 1:
        j = k + 1
        while j + 1 < n and _visible(free, x0, y0, res, pts[k], pts[j + 1]):
            j += 1
        out.append(pts[j])
        k = j
    return out


def path_length(pts):
    return sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(pts[:-1], pts[1:]))


# ============================================================================ loop geometry
def _nearest_pad(bv, st, t, toward):
    if not t.ks:
        return txy(st, t)
    best = None
    for k in t.ks:
        x, y = bv.pad_xy(t.i, k, st.X[t.i], st.Y[t.i], st.R[t.i], st.G[t.i])
        d = math.hypot(x - toward[0], y - toward[1])
        if best is None or d < best[0]:
            best = (d, (x, y))
    return best[1]


class LoopGeo:
    """Routed geometry of one loop: branches between named nodes, each a list of pieces.

    piece: ('strip', (x0, y0), (x1, y1), w, z) | ('vert', (x, y), z0, z1, r) | ('tie', (x, y), z0, z1, w)
    The chain is N0 -> N1 -> ... -> NE (the port closes it); a parallel return gives two
    branches between the same pair of nodes (element names 'lat' and 'via')."""

    def __init__(self, h):
        self.h = h
        self.branches = []      # (node_a, node_b, element, [pieces])
        self.routed = 0.0       # routed board-hop length (mm)
        self.straight = 0.0     # straight board-hop length (mm)
        self.hops = {}          # hop index -> (routed, straight) length (mm)


def loop_geometry(T, comp, router, style):
    """LoopGeo of a LoopComp at the current state, or a reason string when it cannot be built."""
    bv, st = T.bv, T.st
    terms = comp.T
    n = comp.n
    sides = {st.G[t.i] for t in terms}
    if len(sides) > 1:
        return 'mixed sides'
    side = sides.pop()
    P = [txy(st, t) for t in terms]
    cx = sum(p[0] for p in P) / n
    cy = sum(p[1] for p in P) / n
    h = bv.h_ref(side, cx, cy)
    # departure (a) and arrival (b) pads of each board hop
    dep, arr = {}, {}
    for k in range(n):
        if comp.kinds[k] != 'board':
            continue
        k1 = (k + 1) % n
        a = _nearest_pad(bv, st, terms[k], P[k1])
        b = _nearest_pad(bv, st, terms[k1], a)
        dep[k] = a
        arr[k1] = b
    g = LoopGeo(h)
    hz = 0.0 if h == INF else h
    nodes = [f'N{k}' for k in range(n)] + ['NE']
    # route the board hops one after another, each avoiding the loop's copper already routed
    # for other nets (two nets cannot cross on one layer); hops that can return through a
    # plane of their own net go last
    own = {}
    for k in range(n):
        if comp.kinds[k] != 'board':
            continue
        k1 = (k + 1) % n
        own[k] = False
        if k == comp.g and h != INF:
            mx, my = 0.5 * (P[k][0] + P[k1][0]), 0.5 * (P[k][1] + P[k1][1])
            own[k] = bv.plane_net(side, mx, my) in comp.gnd_nets
    routes = {}
    done = []
    for k in sorted(own, key=lambda q: (own[q], q)):
        k1 = (k + 1) % n
        a, b = dep[k], arr[k1]
        nets = tuple({terms[k].net, terms[k1].net} - {''}) or ('',)
        avoid = [(pts, 0.5 * w) for pts, w, nn in done if not set(nn) & set(nets)]
        pts = router.route(side, a, b, nets, comp.w[k], style, avoid=avoid)
        if pts is None and not own[k]:
            return 'unroutable'
        routes[k] = pts
        if pts is not None:
            done.append((pts, comp.w[k], nets))
    for k in range(n):
        k1 = (k + 1) % n
        na, nb = nodes[k], nodes[k + 1] if k + 1 < n else 'NE'
        if comp.kinds[k] == 'body':
            a = arr.get(k, P[k])
            b = dep.get(k1, P[k1])
            zb = comp.zb[k]
            w = comp.w[k]
            pieces = []
            if math.hypot(b[0] - a[0], b[1] - a[1]) > 1e-6:
                if h == INF:
                    pieces.append(('strip', a, b, w, zb))
                else:
                    pieces += [('tie', a, hz, hz + zb, w), ('strip', a, b, w, hz + zb), ('tie', b, hz + zb, hz, w)]
            g.branches.append((na, nb, 'A', pieces, 'body'))
            continue
        a, b = dep[k], arr[k1]
        w = comp.w[k]
        pts = routes[k]
        straight = math.hypot(b[0] - a[0], b[1] - a[1])
        g.straight += straight
        strips = []
        if pts is not None:
            g.routed += path_length(pts)
            g.hops[k] = (path_length(pts), straight)
            strips = [('strip', p, q, w, hz) for p, q in zip(pts[:-1], pts[1:]) if math.hypot(q[0] - p[0], q[1] - p[1]) > 1e-6]
        else:
            g.routed += straight
            g.hops[k] = (straight, straight)
        if own[k]:
            vias = [('vert', a, hz, 0.0, RVIA), ('vert', b, 0.0, hz, RVIA)]
            if strips:
                g.branches.append((na, nb, 'lat', strips, 'board'))
            g.branches.append((na, nb, 'via', vias, 'via'))
        else:
            g.branches.append((na, nb, 'A', strips, 'board'))
    return g


def board_hops(T, comp):
    """Board hops of a LoopComp at the current state, without routing:
    [(hop index, departure pad (x, y), arrival pad (x, y), width, own-plane return, h)]."""
    bv, st = T.bv, T.st
    terms = comp.T
    n = comp.n
    side = st.G[terms[0].i]
    P = [txy(st, t) for t in terms]
    h = bv.h_ref(side, sum(p[0] for p in P) / n, sum(p[1] for p in P) / n)
    out = []
    for k in range(n):
        if comp.kinds[k] != 'board':
            continue
        k1 = (k + 1) % n
        a = _nearest_pad(bv, st, terms[k], P[k1])
        b = _nearest_pad(bv, st, terms[k1], a)
        own = False
        if k == comp.g and h != INF:
            mx, my = 0.5 * (P[k][0] + P[k1][0]), 0.5 * (P[k][1] + P[k1][1])
            own = bv.plane_net(side, mx, my) in comp.gnd_nets
        out.append((k, a, b, comp.w[k], own, h))
    return out


def closed_form_L(g):
    """Loop inductance (nH) of a LoopGeo by the closed forms (critical_physics.Loop)."""
    lp = Loop()
    h = g.h
    elements = set()
    for na, nb, el, pieces, kind in g.branches:
        elements.add(el)
        for pc in pieces:
            if pc[0] == 'strip':
                lp.strip(pc[1], pc[2], pc[3], INF if h == INF else pc[4], el)
            elif pc[0] == 'vert':
                lp.vert(pc[1][0], pc[1][1], pc[2], pc[3], pc[4], el)
            elif pc[0] == 'tie':
                from kae.physics.kernels import gmd_rect
                lp.vert(pc[1][0], pc[1][1], pc[2], pc[3], gmd_rect(max(pc[4], 0.1)), el)
    if 'lat' in elements and 'via' in elements:
        lp.kcl({'lat': 1.0, 'via': 1.0})
    elif 'via' in elements:
        lp.kcl({'via': 1.0})
    return lp.value()


# ---------------------------------------------------------------------------- PEEC
def _nw(w, z, t=T_CU):
    return max(1, min(pw._nw(w * MM, z * MM) if z > 0 else 8, 60, int(w / (1.2 * t))))


def peec_net(g):
    """pw_peec.Net of a LoopGeo whose strips are axis-aligned (Manhattan routes); body
    strips that are not axis-aligned are bent into an L. Returns (net, port_p, port_n)."""
    h = g.h
    net = pw.Net(plane_z=None if h == INF else 0.0)
    cnt = [0]

    def node():
        cnt[0] += 1
        return f'i{cnt[0]}'

    def strip(na, nb, p, q, w, z, t=T_CU):
        if abs(p[1] - q[1]) < 1e-9:
            ax = 0
        elif abs(p[0] - q[0]) < 1e-9:
            ax = 1
        else:
            m = node()
            strip(na, m, p, (q[0], p[1]), w, z, t)
            strip(m, nb, (q[0], p[1]), q, w, z, t)
            return
        L = abs(q[ax] - p[ax])
        if L < 1e-9:
            net.tie(na, nb)
            return
        nw = _nw(w, z if h != INF else 1.0, t)
        lo = min(p[ax], q[ax])
        if ax == 0:
            corner = (lo * MM, (p[1] - w / 2) * MM, z * MM)
        else:
            corner = ((p[0] - w / 2) * MM, lo * MM, z * MM)
        lo_node, hi_node = (na, nb) if q[ax] > p[ax] else (nb, na)
        net.bar(lo_node, hi_node, corner, ax, L * MM, w * MM, t * MM, nw=nw, nt=1)

    for na, nb, el, pieces, kind in g.branches:
        cur = na
        for k, pc in enumerate(pieces):
            last = k == len(pieces) - 1
            nxt = nb if last else node()
            if pc[0] == 'strip':
                strip(cur, nxt, pc[1], pc[2], pc[3], pc[4], T_CU if kind != 'body' else 0.1)
            elif pc[0] == 'vert':
                (x, y), z0, z1, r = pc[1], pc[2], pc[3], pc[4]
                if abs(z1 - z0) < 1e-9:
                    net.tie(cur, nxt)
                elif z0 > z1:
                    net.via(cur, nxt, x * MM, y * MM, z0 * MM, z1 * MM, r=r * MM, n=6)
                else:
                    net.via(nxt, cur, x * MM, y * MM, z1 * MM, z0 * MM, r=r * MM, n=6)
                if (z1 == 0.0 or z0 == 0.0) and h != INF:
                    # the plane end of a via: one node for all via feet (the image plane);
                    # the port node N0 stays apart (a plane-ended chain's source sits there)
                    foot = nxt if z1 == 0.0 else cur
                    if foot != 'N0' and net.find(foot) != net.find('PLANE'):
                        net.tie('PLANE', foot)
            elif pc[0] == 'tie':
                (x, y), z0, z1, bw = pc[1], pc[2], pc[3], pc[4]
                lo = min(z0, z1)
                Lz = abs(z1 - z0)
                if Lz < 1e-9:
                    net.tie(cur, nxt)
                else:
                    a, b = (cur, nxt) if z1 > z0 else (nxt, cur)
                    net.bar(a, b, ((x - 0.015) * MM, (y - bw / 2) * MM, lo * MM), 2, Lz * MM, 0.03 * MM, bw * MM,
                            nw=1, nt=8)
            cur = nxt
        if not pieces:
            net.tie(na, nb)
    return net, 'N0', 'NE'


def peec_solve(net, port_p, port_n):
    """Inductive-limit port inductance (nH) and filament currents for 1 A, real arithmetic."""
    L = net.Lmatrix()
    n = L.shape[0]
    nodes = {}
    for bb in net.bars:
        for nd in bb[:2]:
            nodes.setdefault(net.find(nd), len(nodes))
    pp, pn = net.find(port_p), net.find(port_n)
    A = np.zeros((len(nodes), n))
    for bb in net.bars:
        a, b, ids = net.find(bb[0]), net.find(bb[1]), bb[2]
        s = bb[3] if len(bb) > 3 else 1
        for i in ids:
            A[nodes[a], i] += s
            A[nodes[b], i] -= s
    keep = [k for nd, k in nodes.items() if nd != pn]
    Ar = A[keep]
    try:
        cho = sla.cho_factor(L)
        X = sla.cho_solve(cho, Ar.T)
    except np.linalg.LinAlgError:
        if not PEEC_CLIP:
            raise
        PEEC_CLIPPED[0] += 1
        ev, V = np.linalg.eigh(L)
        ev = np.maximum(ev, 1e-6 * ev.max())
        X = V @ ((V.T @ Ar.T) / ev[:, None])
    Y = Ar @ X
    src = np.zeros(len(keep))
    kp = keep.index(nodes[pp])
    src[kp] = 1.0
    v = np.linalg.solve(Y, src)
    I = X @ v
    return float(v[kp]) * 1e9, I, n


def peec_L(g):
    net, p, q = peec_net(g)
    L, I, n = peec_solve(net, p, q)
    return L, n


# ============================================================================ structures
def loop_comps(comp, st):
    """The LoopComps a component stands for at the current state (NearestLoopComp picks
    the nearest load, as the estimator does)."""
    if isinstance(comp, NearestLoopComp):
        x, y = txy(st, comp.tr)
        best, bd = None, INF
        for c in comp.loops:
            px, py = txy(st, c.T[0])
            d = (px - x) ** 2 + (py - y) ** 2
            if d < bd:
                bd, best = d, c
        return best
    return comp


def eval_loop(T, comp, router, mode):
    """Exact value (nH) of one loop component: mode cf (any-angle route, closed forms),
    cfm (Manhattan route, closed forms), peec (Manhattan route, PEEC), detour (estimator +
    L' x extra routed length). Returns (value or None, info)."""
    c = loop_comps(comp, T.st)
    if isinstance(c, PlanePairLoop):
        # mounting closed form + plane-pair spreading within 0.4 % of a sheet solve: taken as exact
        return c.value(T.st), dict(note='plane pair')
    if not isinstance(c, LoopComp):
        return None, dict(note=type(c).__name__)
    if mode == 'detour':
        g = loop_geometry(T, c, router, 'any')
        if isinstance(g, str):
            return None, dict(note=g)
        hh = g.h if g.h != INF else T.bv.thickness
        extra = 0.0
        for na, nb, el, pieces, kind in g.branches:
            if kind != 'board' or el in ('via', 'lat'):
                continue        # a ground hop over its own plane is not routed (pt_human_perturb)
            ln = sum(math.hypot(p[2][0] - p[1][0], p[2][1] - p[1][1]) for p in pieces)
            a = pieces[0][1] if pieces else None
            b = pieces[-1][2] if pieces else None
            if a is None:
                continue
            extra += lprime_hj(pieces[0][3], hh) * max(0.0, ln - math.hypot(b[0] - a[0], b[1] - a[1]))
        return c.value(T.st) + extra, dict(routed=g.routed, straight=g.straight, hops=g.hops)
    style = 'any' if mode == 'cf' else 'manhattan'
    g = loop_geometry(T, c, router, style)
    if isinstance(g, str):
        return None, dict(note=g)
    if mode in ('cf', 'cfm'):
        return closed_form_L(g), dict(routed=g.routed, straight=g.straight, hops=g.hops)
    try:
        L, nfil = peec_L(g)
    except (np.linalg.LinAlgError, ValueError) as e:
        return None, dict(note=f'peec: {type(e).__name__}')
    return L, dict(routed=g.routed, straight=g.straight, filaments=nfil)


def eval_esd(T, comp, router, mode):
    """Surge path: routed strip connector pin -> protector pad at height h, via into the
    plane at the protector (and the connector side closed through its own via), plus the
    estimator's double charge for a protector beyond the protected pin."""
    bv, st = T.bv, T.st
    est = comp.value(st)
    ax, ay = txy(st, comp.tc)
    px, py = txy(st, comp.tp)
    side = st.G[comp.tp.i]
    if st.G[comp.tc.i] != side:
        cp = bv.parts[comp.tc.i]
        if not comp.tc.ks or any(cp.pad_kind[k] == 'smd' for k in comp.tc.ks):
            return None, dict(note='mixed sides')
        # a through-hole connector pin reaches the protector's side directly
    h = bv.h_ref(side, px, py)
    hh = bv.thickness if h == INF else h
    # the estimator is L'(l + 2 beyond) + L_via; the 2 L' beyond part is an order rule, kept
    lp = lprime_hj(comp.w, hh)
    beyond = 0.0
    if comp.ti is not None:
        bx, by = txy(st, comp.ti)
        ux, uy = bx - ax, by - ay
        lab = math.hypot(ux, uy)
        if lab > 1e-9:
            beyond = max(0.0, ((px - ax) * ux + (py - ay) * uy) / lab - lab)
    beyond_term = 2.0 * lp * beyond
    a = _nearest_pad(bv, st, comp.tc, (px, py))
    b = _nearest_pad(bv, st, comp.tp, a)
    nets = (comp.tc.net,)
    if mode == 'detour':
        pts = router.route(side, a, b, nets, comp.w, 'any')
        if pts is None:
            return None, dict(note='unroutable')
        return est + lp * max(0.0, path_length(pts) - math.hypot(b[0] - a[0], b[1] - a[1])), {}
    style = 'any' if mode == 'cf' else 'manhattan'
    pts = router.route(side, a, b, nets, comp.w, style)
    if pts is None:
        return None, dict(note='unroutable')
    g = LoopGeo(h)
    hz = 0.0 if h == INF else h
    strips = [('strip', p, q, comp.w, hz) for p, q in zip(pts[:-1], pts[1:]) if math.hypot(q[0] - p[0], q[1] - p[1]) > 1e-6]
    if h == INF:
        g.branches.append(('N0', 'NE', 'A', strips, 'board'))
    else:
        g.branches.append(('N0', 'N1', 'A', [('vert', a, 0.0, hz, RVIA)], 'via'))
        g.branches.append(('N1', 'N2', 'A', strips, 'board'))
        g.branches.append(('N2', 'NE', 'A', [('vert', b, hz, 0.0, RVIA)], 'via'))
    g.routed = path_length(pts)
    if mode in ('cf', 'cfm'):
        if h == INF:
            return lp * g.routed + beyond_term, dict(note='no plane: L x length')
        return closed_form_L(g) + beyond_term, dict(routed=g.routed)
    if h == INF:
        return lp * g.routed + beyond_term, dict(note='no plane: L x length')
    try:
        net, p0, pe = peec_net(g)
        # plane-ended chain: the source sits between the first via's foot (N0, kept off the
        # plane node) and the plane
        L, I, nfil = peec_solve(net, 'N0', 'NE')
    except (np.linalg.LinAlgError, ValueError) as e:
        return None, dict(note=f'peec: {type(e).__name__}')
    return L + beyond_term, dict(routed=g.routed, filaments=nfil)


# ---------------------------------------------------------------------------- crystal
_CP = {}


def field_cprime(w, h, er):
    """Per-length capacitance (pF/mm) of a microstrip from fe_field2d (cached)."""
    key = (round(w, 3), round(h, 3), round(er, 2))
    v = _CP.get(key)
    if v is None:
        import fe_field2d as fe
        dx = min(w, h) / 8.0
        X, Y = max(2.0, 6 * h + 3 * w) * MM, max(2.0, 8 * h) * MM
        C = fe.solve_caps(X, Y, dx * MM, [(0, h * MM, er)], [(-w / 2 * MM, w / 2 * MM, h * MM, (h + T_CU) * MM)])
        v = C[0, 0] * 1e12 / 1e3
        _CP[key] = v
    return v


def eval_crystal(T, comp, router, mode):
    """Pulling (ppm) with routed XIN/XOUT lengths (each load pad routed to the IC pin via
    the crystal pad: IC -> crystal, cap -> crystal) and C' from the field solver."""
    bv, st = T.bv, T.st
    x0, y0 = txy(st, comp.ti[0])
    side = st.G[comp.ti[0].i]
    h = bv.h_ref(side, x0, y0)
    if mode == 'detour':
        cp = comp._cprime(h)
    else:
        cp = (cprime_hj(comp.w, bv.thickness, 1.0) * 0.6) if h == INF else field_cprime(comp.w, h, bv.er)
    total = 0.0
    for terms in (comp.ti, comp.to):
        if len(terms) < 2:
            continue
        hub = terms[1]      # the crystal pad
        hub_xy = txy(st, hub)
        for t in [terms[0]] + list(terms[2:]):
            a = txy(st, t)
            sides = {st.G[t.i], st.G[hub.i]}
            if len(sides) > 1:
                total += math.hypot(a[0] - hub_xy[0], a[1] - hub_xy[1])
                continue
            pts = router.route(side, a, hub_xy, (t.net,), comp.w, 'any')
            if pts is None:
                return None, dict(note='unroutable')
            total += path_length(pts)
    return comp.s * cp * total / 4.0, dict(length=total, cprime=cp)


# ---------------------------------------------------------------------------- coupling
def eval_coupling(T, comp, router, mode, cache=None):
    """Noise (mV): inductive part from PEEC currents of the routed aggressor and the EMF
    along the routed victim path; capacitive part as the estimator."""
    bv, st = T.bv, T.st
    if mode == 'detour':
        return comp.value(st), {}
    v_ind_est = 0.0
    v_cap = comp.value(st)
    from kae.physics.structures import _mutual
    if comp.al is not None and comp.vl is not None and comp.didt > 0:
        ga = comp.al.geo(st)
        h = bv.h_ref(st.G[comp.al.T[0].i], ga[1][0], ga[1][1])
        v_ind_est = _mutual(comp.kern, comp.al, comp.vl, st, h) * comp.didt * 1e3
    v_cap -= v_ind_est
    if comp.al is None or comp.vl is None or comp.didt <= 0:
        return v_cap, dict(note='capacitive only')
    agg = comp.aloop_comp
    if agg is None:
        return None, dict(note='no aggressor loop')
    g = loop_geometry(T, agg, router, 'manhattan')
    if isinstance(g, str):
        return None, dict(note='aggressor ' + g)
    try:
        net, p, q = peec_net(g)
        La, I, nfil = peec_solve(net, p, q)
    except (np.linalg.LinAlgError, ValueError) as e:
        return None, dict(note=f'peec: {type(e).__name__}')
    # victim path: its terminals in order, routed Manhattan at the victim's plane height
    vl = comp.vl
    sides = {st.G[t.i] for t in vl.T}
    if len(sides) > 1 or sides != {st.G[t.i] for t in agg.T}:
        return None, dict(note='victim and aggressor on different sides')
    side = sides.pop()
    pts_v = [txy(st, t) for t in vl.T]
    hv = bv.h_ref(side, *pts_v[0])
    hz = 0.0 if hv == INF else hv
    hops = list(zip(pts_v[:-1], pts_v[1:])) + ([(pts_v[-1], pts_v[0])] if vl.closed else [])
    path = []
    if not vl.closed and hv != INF:
        path.append(((pts_v[0][0] * MM, pts_v[0][1] * MM, 0.0), 2, hz * MM))
    for k, (a, b) in enumerate(hops):
        t0 = vl.T[k]
        t1 = vl.T[(k + 1) % len(vl.T)]
        if t0.i == t1.i:
            seg = _simplify_manhattan([a, (b[0], a[1]), b]) if abs(a[0] - b[0]) > 1e-9 and abs(a[1] - b[1]) > 1e-9 else [a, b]
        else:
            seg = router.route(side, a, b, tuple({t0.net, t1.net} - {''}) or ('',), 0.2, 'manhattan')
            if seg is None:
                return None, dict(note='victim unroutable')
        for p, q in zip(seg[:-1], seg[1:]):
            if abs(p[1] - q[1]) < 1e-9 and abs(p[0] - q[0]) > 1e-9:
                path.append(((p[0] * MM, p[1] * MM, hz * MM), 0, (q[0] - p[0]) * MM))
            elif abs(p[1] - q[1]) > 1e-9:
                path.append(((p[0] * MM, p[1] * MM, hz * MM), 1, (q[1] - p[1]) * MM))
    if not vl.closed and hv != INF:
        path.append(((pts_v[-1][0] * MM, pts_v[-1][1] * MM, hz * MM), 2, -hz * MM))
    M = abs(net.induced(path, I)) * 1e9
    return M * comp.didt * 1e3 + v_cap, dict(M_nH=M, filaments=nfil)


def attach_aggressors(T):
    """Give each CouplingComp the commutation LoopComp its aggressor loop came from."""
    by_terms = {}
    for s in T.structs:
        if s.kind == 'commutation' and s.comps:
            by_terms[id(s.comps[0].T)] = s.comps[0]
    for s in T.structs:
        if s.kind != 'coupling':
            continue
        for c in s.comps:
            c.aloop_comp = None
            if c.al is not None:
                c.aloop_comp = by_terms.get(id(c.al.T))


# ---------------------------------------------------------------------------- dispatch
def struct_value(T, k, router, mode):
    """Exact value of structure k in the given mode, reduced as Terms reduces it."""
    from kae.physics.place_terms import _red
    s = T.structs[k]
    vals, infos = [], []
    for c in s.comps:
        if isinstance(c, (LoopComp, NearestLoopComp, PlanePairLoop)):
            v, info = eval_loop(T, c, router, mode)
        elif isinstance(c, EsdComp):
            v, info = eval_esd(T, c, router, mode)
        elif isinstance(c, CrystalComp):
            v, info = eval_crystal(T, c, router, mode)
        elif isinstance(c, CouplingComp):
            v, info = eval_coupling(T, c, router, mode)
        else:
            v, info = c.value(T.st), dict(note='estimator')
        if v is None:
            return None, info
        vals.append(v)
        infos.append(info)
    return _red(s.reduce, vals, s.info.get('weights')), infos


# ============================================================================ thermal (FV)
class FVThermal:
    """Finite-volume rise at the thermal targets (sources: mean over their footprint box;
    victims: their centre), over the board's bounding box with each layer's zone coverage.
    Factor once; one solve per distinct source pose (superposition)."""

    def __init__(self, T, dx=0.5, h_conv=10.0, max_nodes=400_000, inject='surface'):
        import tm_board_thermal_fv as tm
        self.inject = inject      # surface: into the part's outer layer; stack: all layers under it (stitched)
        self.tm = tm
        self.T = T
        bv = T.bv
        th = T.thermal
        x0, y0, x1, y1 = bv.bbox
        nl = len(bv.copper)
        while ((x1 - x0) / dx) * ((y1 - y0) / dx) * nl > max_nodes:
            dx *= 1.25
        self.dx = dx
        self.x0, self.y0 = x0, y0
        self.nx = max(2, int(round((x1 - x0) / dx)))
        self.ny = max(2, int(round((y1 - y0) / dx)))
        t_cu = [bv.tcu.get(ly, 0.035) * MM for ly in bv.copper]
        gaps = [g * MM for g in (bv.gaps if hasattr(bv, 'gaps') and len(bv.gaps) == nl - 1 else
                                 [bv.thickness / max(1, nl - 1)] * (nl - 1))]
        b = tm.Board((x1 - x0) * MM, (y1 - y0) * MM, dx * MM, t_cu, gaps, h_conv, h_conv)
        b.nx, b.ny = self.nx, self.ny
        b.cov = np.zeros((nl, self.nx, self.ny), bool)
        b.via = np.zeros((self.nx, self.ny))
        b.p = np.zeros((nl, self.nx, self.ny))
        X = x0 + (np.arange(self.nx) + 0.5) * dx
        Y = y0 + (np.arange(self.ny) + 0.5) * dx
        cx0, cy0, cres, cnx, cny = bv.cover_grid
        ii = np.clip(np.round((X - cx0) / cres).astype(int), 0, cnx - 1)
        jj = np.clip(np.round((Y - cy0) / cres).astype(int), 0, cny - 1)
        for li, ly in enumerate(bv.copper):
            C = bv.cover.get(ly)
            if C is not None:
                b.cov[li] = (C[np.ix_(jj, ii)] >= 0).T
        self.b = b
        self.nl = nl
        t0 = time.perf_counter()
        self.A = self._assemble()
        self.t_build = time.perf_counter() - t0
        t0 = time.perf_counter()
        self.lu = spla.splu(self.A.tocsc(), permc_spec='MMD_AT_PLUS_A')
        self.t_factor = time.perf_counter() - t0
        self.nnz_lu = int(self.lu.L.nnz + self.lu.U.nnz)
        self.nodes = self.A.shape[0]
        self.cache = {}
        self.solves = 0
        self.t_solve = 0.0
        self.src = list(th.src)
        self.P = np.array(th.P, float)
        self.targets = list(th.targets)
        self.Lx, self.Ly = (x1 - x0), (y1 - y0)
        self.hsum = 2 * h_conv

    def _assemble(self):
        b = self.b
        nl, nx, ny, dx = b.nl, b.nx, b.ny, b.dx
        tm = self.tm
        n = nl * nx * ny
        idx = np.arange(n).reshape(nl, nx, ny)
        rows, cols, vals = [], [], []
        diag = np.zeros(n)

        def couple(a, c, g):
            a, c, g = a.ravel(), c.ravel(), np.broadcast_to(g, a.shape).ravel()
            rows.extend([a, c])
            cols.extend([c, a])
            vals.extend([-g, -g])
            np.add.at(diag, a, g)
            np.add.at(diag, c, g)
        for l in range(nl):
            share = 0.0
            if l > 0:
                share += b.d[l - 1] / 2
            if l < nl - 1:
                share += b.d[l] / 2
            gs = tm.K_XY * share + tm.K_CU * b.t_cu[l] * b.cov[l]
            gx = 2 * gs[:-1, :] * gs[1:, :] / (gs[:-1, :] + gs[1:, :])
            gy = 2 * gs[:, :-1] * gs[:, 1:] / (gs[:, :-1] + gs[:, 1:])
            couple(idx[l, :-1, :], idx[l, 1:, :], gx)
            couple(idx[l, :, :-1], idx[l, :, 1:], gy)
        for l in range(nl - 1):
            g = tm.K_Z * dx * dx / b.d[l] + b.via / b.d[l]
            couple(idx[l], idx[l + 1], g)
        diag[idx[0].ravel()] += b.h[0] * dx * dx
        diag[idx[-1].ravel()] += b.h[1] * dx * dx
        rows.append(np.arange(n))
        cols.append(np.arange(n))
        vals.append(diag)
        return sp.coo_matrix((np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))), shape=(n, n)).tocsr()

    def _box(self, i):
        st = self.T.st
        bv = self.T.bv
        x0, y0, x1, y1 = bv.courtyard_obb(i, st.X[i], st.Y[i], st.R[i], st.G[i])
        i0 = int(np.clip((x0 - self.x0) / self.dx, 0, self.nx - 1))
        i1 = int(np.clip((x1 - self.x0) / self.dx, 0, self.nx - 1))
        j0 = int(np.clip((y0 - self.y0) / self.dx, 0, self.ny - 1))
        j1 = int(np.clip((y1 - self.y0) / self.dx, 0, self.ny - 1))
        layer = 0 if st.G[i] > 0 else self.nl - 1
        return layer, i0, i1, j0, j1

    def field(self, k):
        """Temperature field (nl, nx, ny) of 1 W from source k at its current pose."""
        i = self.src[k]
        key = (k, self._box(i))
        f = self.cache.get(key)
        if f is None:
            layer, i0, i1, j0, j1 = key[1]
            p = np.zeros((self.nl, self.nx, self.ny))
            if self.inject == 'stack':
                p[:, i0:i1 + 1, j0:j1 + 1] = 1.0 / ((i1 - i0 + 1) * (j1 - j0 + 1) * self.nl)
            else:
                p[layer, i0:i1 + 1, j0:j1 + 1] = 1.0 / ((i1 - i0 + 1) * (j1 - j0 + 1))
            t0 = time.perf_counter()
            f = self.lu.solve(p.ravel()).reshape(self.nl, self.nx, self.ny)
            self.t_solve += time.perf_counter() - t0
            self.solves += 1
            if len(self.cache) > 4000:
                self.cache.clear()
            self.cache[key] = f
        return f

    def rise(self):
        """(rise at each target (K), board mean rise (K)) at the current poses."""
        st = self.T.st
        out = np.zeros(len(self.targets))
        fields = [self.field(k) for k in range(len(self.src))]
        for t, i in enumerate(self.targets):
            layer, i0, i1, j0, j1 = self._box(i)
            if t < len(self.src):
                val = sum(self.P[k] * fields[k][layer, i0:i1 + 1, j0:j1 + 1].mean() for k in range(len(self.src)))
            else:
                ci = int(np.clip((st.X[i] - self.x0) / self.dx, 0, self.nx - 1))
                cj = int(np.clip((st.Y[i] - self.y0) / self.dx, 0, self.ny - 1))
                val = sum(self.P[k] * fields[k][layer, ci, cj] for k in range(len(self.src)))
            out[t] = val
        mean = float(self.P.sum()) / (self.hsum * self.Lx * self.Ly * MM * MM)
        return out, mean


def thermal_cost(T, rise, mean):
    from kae.physics import priors as PR
    b = T.knobs.barrier
    return float(sum(c * PR.phi(max(rise[t] - mean, 0.0) / a.value, b, T.knobs.u_sat)
                     for t, (a, c) in enumerate(zip(T._th_alloc, T._th_conf))))


def fast_rise(T):
    th = T.thermal
    th.full(T.st)
    return th.G @ th.P, th.T_mean
