# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Grid search with exact verification: how the critical router draws one connection.

`GridRouter.connect(net, sources, targets, width, layers)` routes a track of one width
between two sets of same-net copper (pads, committed tracks and vias) inside a window:

1. **Raster.** One cost grid per allowed copper layer (default resolution 0.05 mm, coarser
   for large windows). A cell is blocked when a track centre there would come closer to an
   obstacle than R = half the width plus KiCad's requirement for that pair (`Space.need`),
   plus a margin m = sqrt(R^2 + res^2/2) - R: a point at R + m or more from both ends of a
   move of length L = res*sqrt(2) is at least sqrt((R+m)^2 - L^2/4) = R from every point of
   it, so the straight piece between two free neighbouring cell centres is legal too (about
   2 um for R = 0.3 mm; a flat 0.71 cell would close the 0.2 mm gaps between 0.5 mm-pitch
   pins). Board edges, rule areas and thermal-spoke corridors block the same way. Free cells get cost multipliers: other nets' pours on the layer (crossing a pour
   cuts it), a halo around other nets' pads (their escape space), and per-layer factors.
   Vias are allowed where a via of the net fits (`Space.via_violations`, rasterized).
2. **Search.** A* (kae.route.critical_kernels; numba when installed) from the source cells
   to the target cells, through vias where allowed.
3. **Geometry.** The cell path becomes one polyline per layer, then string-pulled: each
   straight shortcut is kept only if `Space.track_violations` finds nothing (exact shapely
   distances); ends are moved onto the pad centres when that is legal.

The result is a list of segments and vias, every one checked exactly against KiCad's
requirements; nothing is committed until the caller does so.
"""
from __future__ import annotations

import importlib.util
import math
import os
import sys
from dataclasses import dataclass, field

import numpy as np
import shapely
from shapely.geometry import LineString, Point, Polygon, box

from .critical_space import INF, TOL

_SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "critical_kernels.py")


def _load(name, jit):
    mod = sys.modules.get(name)
    if mod is not None:
        return mod
    spec = importlib.util.spec_from_file_location(name, _SRC)
    mod = importlib.util.module_from_spec(spec)
    mod._JIT = jit
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


PY = _load("kae.route._critical_kernels_py", lambda f: f)
_NB = None


def kernels():
    """The numba kernels when numba is installed (and KAE_NO_NUMBA unset), else Python."""
    global _NB
    if os.environ.get("KAE_NO_NUMBA"):
        return PY
    if _NB is None:
        try:
            import numba
        except ImportError:
            _NB = PY
        else:
            _NB = _load("kae.route._critical_kernels_nb", numba.njit(cache=True))
    return _NB


# ----------------------------------------------------------------------------- grid
class Grid:
    """A window x0..x1, y0..y1 sampled at cell centres x0 + i res, y0 + j res."""

    def __init__(self, x0, y0, x1, y1, res):
        self.res = float(res)
        self.x0, self.y0 = float(x0), float(y0)
        self.nx = max(2, int(math.ceil((x1 - x0) / res)) + 1)
        self.ny = max(2, int(math.ceil((y1 - y0) / res)) + 1)
        self.x1 = self.x0 + (self.nx - 1) * res
        self.y1 = self.y0 + (self.ny - 1) * res

    def xy(self, i, j):
        return (self.x0 + i * self.res, self.y0 + j * self.res)

    def ij(self, x, y):
        return (int(round((x - self.x0) / self.res)), int(round((y - self.y0) / self.res)))

    def inside(self, i, j):
        return 0 <= i < self.nx and 0 <= j < self.ny

    def _span(self, bounds, r):
        gx0, gy0, gx1, gy1 = bounds
        res = self.res
        i0 = max(0, int(math.ceil((gx0 - r - self.x0) / res)))
        i1 = min(self.nx - 1, int(math.floor((gx1 + r - self.x0) / res)))
        j0 = max(0, int(math.ceil((gy0 - r - self.y0) / res)))
        j1 = min(self.ny - 1, int(math.floor((gy1 + r - self.y0) / res)))
        return i0, i1, j0, j1

    def coords(self, i0, i1, j0, j1):
        xs = self.x0 + np.arange(i0, i1 + 1) * self.res
        ys = self.y0 + np.arange(j0, j1 + 1) * self.res
        return np.meshgrid(xs, ys)

    def within(self, geom, r, out=None):
        """Boolean grid: cell centres within distance r of geom (r >= 0); or with `out`,
        those cells are or-ed into out. Points and two-point lines exactly, polygons
        through a circumscribed buffer (axis-aligned rectangles, most pads, in numpy but for
        cells right at the buffer's edge). Windows are rebuilt for every connection and
        candidate route around the same pads, so the cells of (geom, r, window) are kept."""
        if out is None:
            out = np.zeros((self.ny, self.nx), bool)
        key = (id(geom), r, self.x0, self.y0, self.nx, self.ny, self.res)
        hit = _RASTER.get(key)
        if hit is None:
            hit = (geom, self._within(geom, r))
            _keep(_RASTER, key, hit, 200 + (0 if hit[1] is None else hit[1][4].size))
        if hit[1] is not None:
            j0, j1, i0, i1, m = hit[1]
            out[j0:j1 + 1, i0:i1 + 1] |= m
        return out

    def _within(self, geom, r):
        """(j0, j1, i0, i1, cells) of `within` (the cells of that block), or None."""
        bounds, kind, data = _shape(geom)
        i0, i1, j0, j1 = self._span(bounds, r)
        if i0 > i1 or j0 > j1:
            return None
        # a row and a column of cell centres; broadcasting them gives the same values as
        # the full coordinate grids (coords)
        X = (self.x0 + np.arange(i0, i1 + 1) * self.res)[None, :]
        Y = (self.y0 + np.arange(j0, j1 + 1) * self.res)[:, None]
        if kind == "point":
            m = np.hypot(X - data[0], Y - data[1]) <= r
        elif kind == "segment":
            m = _seg_dist(X, Y, *data) <= r
        elif kind == "rect":
            m = _rect_within(geom, data, r, X, Y)
        else:
            g = _buffered(geom, r)
            if g.is_empty:
                return None
            X, Y = np.broadcast_arrays(X, Y)
            m = shapely.contains_xy(g, X, Y)
            if r <= 0:
                m |= shapely.intersects_xy(g, X, Y)
        return j0, j1, i0, i1, m


# Caches of Grid.within, keyed by id(geom) and holding the geometry, so an id cannot be
# reused while its entry lives (shapely geometries are immutable): cells per window,
# buffered polygons, what kind of shape each is. Each is emptied when full.
_BUF_Q = 4
_RASTER = {}
_BUF = {}
_SHAPE = {}
_SIZE = {}
_LIMIT = {id(_RASTER): 100_000_000, id(_BUF): 100_000, id(_SHAPE): 100_000}


def _keep(cache, key, value, size=1):
    """cache[key] = value, emptying the cache first when its size (about bytes for cells,
    else entries) would pass its limit."""
    n = _SIZE.get(id(cache), 0) + max(size, 1)
    if n > _LIMIT[id(cache)]:
        cache.clear()
        n = max(size, 1)
    _SIZE[id(cache)] = n
    cache[key] = value


def _buffered(geom, r):
    """geom buffered by r circumscribed (r / cos(pi/16), quad_segs 4: every point within r
    is inside), prepared; geom itself for r <= 0."""
    key = (id(geom), r)
    hit = _BUF.get(key)
    if hit is None:
        g = geom.buffer(r / math.cos(math.pi / (4 * _BUF_Q)), quad_segs=_BUF_Q) if r > 0 else geom
        if not g.is_empty:
            shapely.prepare(g)      # many points against one polygon: index it once
        hit = (geom, g)
        _keep(_BUF, key, hit)
    return hit[1]


def _shape(geom):
    """(bounds, kind, data) of geom for Grid.within: kind "point" (data x, y), "segment"
    (a two-point LineString; ax, ay, bx, by), "rect" (a Polygon that is exactly an
    axis-aligned rectangle of positive area, four corners and no holes, when shapely buffers
    rectangles as _rect_within expects; x0, y0, x1, y1) or "other"."""
    hit = _SHAPE.get(id(geom))
    if hit is not None:
        return hit[1]
    gt = geom.geom_type
    kind, data = "other", None
    if gt == "Point":
        kind, data = "point", (geom.x, geom.y)
    elif gt == "LineString" and len(geom.coords) == 2:
        (ax, ay), (bx, by) = geom.coords
        kind, data = "segment", (ax, ay, bx, by)
    elif gt == "Polygon" and not geom.interiors and _fillets_ok():
        c = shapely.get_coordinates(geom)
        x0, y0, x1, y1 = geom.bounds
        if (len(c) == 5 and x0 < x1 and y0 < y1 and (c[0] == c[4]).all()
                and len({(float(x), float(y)) for x, y in c[:4]}) == 4
                and np.isin(c[:, 0], (x0, x1)).all() and np.isin(c[:, 1], (y0, y1)).all()
                and ((np.diff(c[:, 0]) == 0) | (np.diff(c[:, 1]) == 0)).all()):
            kind, data = "rect", (x0, y0, x1, y1)
    info = (geom.bounds, kind, data)
    _keep(_SHAPE, id(geom), (geom, info))
    return info


# fillet chords of a quarter circle in quad_segs 4: outward normals (cos, sin) of chords
# between the points at angles k pi/8, k = 0..4
_CHORDS = [(math.cos((k + 0.5) * math.pi / 8), math.sin((k + 0.5) * math.pi / 8)) for k in range(4)]
_FILLETS_OK = []


def _fillets_ok():
    """Whether shapely buffers an axis-aligned rectangle into the polygon _rect_within
    reasons about: the sides moved out by the buffer distance, joined at each corner by
    points on the circle of that radius at angles k pi/8 (checked once per process)."""
    if not _FILLETS_OK:
        ok = True
        rb = 0.37
        for g in (box(0.0, 0.0, 2.0, 1.0), box(0.0, 0.0, 2.0, 1.0, ccw=False),
                  Polygon([(2.0, 1.0), (0.0, 1.0), (0.0, 0.0), (2.0, 0.0)])):
            want = [(cx + sx * rb * math.cos(k * math.pi / 8), cy + sy * rb * math.sin(k * math.pi / 8))
                    for cx, cy, sx, sy in ((2.0, 1.0, 1, 1), (0.0, 1.0, -1, 1), (0.0, 0.0, -1, -1), (2.0, 0.0, 1, -1))
                    for k in range(5)]
            b = g.buffer(rb, quad_segs=_BUF_Q)
            got = shapely.get_coordinates(b.exterior)[:-1] if b.geom_type == "Polygon" and not b.interiors else []
            near = [[math.hypot(x - u, y - v) < 1e-12 for u, v in want] for x, y in got]
            ok = ok and len(got) == 20 and all(map(any, near)) and all(map(any, zip(*near)))
        _FILLETS_OK.append(ok)
    return _FILLETS_OK[0]


def _rect_within(geom, rect, r, X, Y):
    """What the circumscribed-buffer test of `within` gives for the axis-aligned rectangle
    geom (X a row, Y a column of cell centres), without the buffer where the answer is
    certain. r <= 0: the closed rectangle. r > 0: the buffer is the rectangle with its sides
    moved out by r' = r / cos(pi/16), joined at each corner by chords between points on the
    circle of radius r' about the corner, pi/8 apart (_fillets_ok); each chord is r from
    the corner. Beside a side a cell is inside when nearer than r' to it; beyond a corner
    when it is on the corner's side of all four chords. Cells within eps (far more than
    rounding) of an edge of the buffer go to shapely."""
    x0, y0, x1, y1 = rect
    if r <= 0:
        return ((X >= x0) & (X <= x1)) & ((Y >= y0) & (Y <= y1))
    xs, ys = X[0], Y[:, 0]
    u = np.maximum(np.maximum(x0 - xs, xs - x1), 0.0)       # distance beyond the sides, x
    v = np.maximum(np.maximum(y0 - ys, ys - y1), 0.0)       # and y
    rb = r / math.cos(math.pi / (4 * _BUF_Q))
    eps = 1e-9 * (1.0 + r + max(abs(x0), abs(x1), abs(y0), abs(y1)))
    # columns ia:ib have u = 0, rows ja:jb v = 0 (the centres are sorted)
    ia, ib = int(np.searchsorted(xs, x0, "left")), int(np.searchsorted(xs, x1, "right"))
    ja, jb = int(np.searchsorted(ys, y0, "left")), int(np.searchsorted(ys, y1, "right"))
    m = np.empty((ys.size, xs.size), bool)
    # beside a side (or inside): the distance is the other of u, v; inside below rb
    m[:, ia:ib] = (v <= rb - eps)[:, None]
    m[ja:jb, :] = (u <= rb - eps)[None, :]
    near_u, near_v = np.abs(u - rb) <= eps, np.abs(v - rb) <= eps
    # beyond a corner (four blocks): inside on the corner's side of all four chords
    blocks = [(np.s_[rows], np.s_[cols], np.s_[crows], np.s_[ccols])
              for rows, crows in ((np.s_[:ja], np.s_[:ja]), (np.s_[jb:], np.s_[ja:]))
              for cols, ccols in ((np.s_[:ia], np.s_[:ia]), (np.s_[ib:], np.s_[ia:]))]
    cu = np.concatenate((u[:ia], u[ib:]))[None, :]
    cv = np.concatenate((v[:ja], v[jb:]))[:, None]
    near_f = None
    if cu.size and cv.size:
        f = np.maximum(np.maximum(cu * _CHORDS[0][0] + cv * _CHORDS[0][1], cu * _CHORDS[1][0] + cv * _CHORDS[1][1]),
                       np.maximum(cu * _CHORDS[2][0] + cv * _CHORDS[2][1], cu * _CHORDS[3][0] + cv * _CHORDS[3][1]))
        fin = f <= r - eps
        near_f = np.abs(f - r) <= eps
        for rows, cols, crows, ccols in blocks:
            m[rows, cols] = fin[crows, ccols]
    if near_u.any() or near_v.any() or (near_f is not None and near_f.any()):
        # rare: cells within eps of the buffer's edge, decided by shapely
        unsure = np.zeros_like(m)
        unsure[:, ia:ib] |= near_v[:, None]
        unsure[ja:jb, :] |= near_u[None, :]
        if near_f is not None:
            for rows, cols, crows, ccols in blocks:
                unsure[rows, cols] |= near_f[crows, ccols]
        jj, ii = np.nonzero(unsure)
        m[jj, ii] = shapely.contains_xy(_buffered(geom, r), xs[ii], ys[jj])
    return m


def _seg_dist(X, Y, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    l2 = dx * dx + dy * dy
    if l2 < 1e-18:
        return np.hypot(X - ax, Y - ay)
    t = np.clip(((X - ax) * dx + (Y - ay) * dy) / l2, 0.0, 1.0)
    return np.hypot(X - (ax + t * dx), Y - (ay + t * dy))


# ----------------------------------------------------------------------------- results

def _margin(R, res):
    """Inflation beyond a requirement R that keeps the straight move between two free
    neighbouring cell centres (at most res*sqrt(2) long) at R or more from the obstacle."""
    return math.sqrt(R * R + 0.5 * res * res) - R + 1e-4

@dataclass
class Route:
    net: str
    width: float
    segs: list = field(default_factory=list)   # (layer, (x, y), (x, y))
    vias: list = field(default_factory=list)   # (x, y)
    length: float = 0.0
    expansions: int = 0
    res: float = 0.0

    def layers(self):
        return sorted({s[0] for s in self.segs})


@dataclass
class Anchor:
    """A source or target of a connection: copper of the net on some layers.

    geom: board-frame shape of the copper (a pad's DSN shape, a track centreline grown by
    `grow`, a via disc); centre: where a track may end exactly (pad centre, via centre)."""
    geom: object
    layers: tuple
    centre: tuple | None = None
    grow: float = 0.0
    kind: str = "pad"
    by_layer: dict | None = None      # layer -> copper on that layer (pads with an SMD twin)
    centres: dict | None = None       # layer -> a point of that copper (where a track may end)

    def geom_on(self, layer):
        g = (self.by_layer or {}).get(layer, self.geom)
        return g if self.grow <= 0 else g.buffer(self.grow, quad_segs=4)

    def centre_on(self, layer):
        return (self.centres or {}).get(layer, self.centre)


# ----------------------------------------------------------------------------- router
class GridRouter:
    """Routes single connections in a Space (see the module docstring)."""

    def __init__(self, space, res=0.05, max_cells=1_500_000, halo=0.4, halo_cost=0.6, pour_cost=0.4,
                 via_cost=1.5, max_exp=4_000_000):
        self.sp = space
        self.res = res
        self.max_cells = max_cells
        self.halo, self.halo_cost, self.pour_cost = halo, halo_cost, pour_cost
        self.via_cost = via_cost
        self.max_exp = max_exp
        self.K = kernels()
        self.stats = dict(calls=0, found=0, expansions=0, cells=0)
        # escape corridors of dense ICs' signal pins [(geometry, layer, net)]: other nets'
        # tracks pay escape_cost per cell inside them, their vias are not placed there
        self.escapes = []
        self.escape_cost = 0.0

    # ------------------------------------------------------------------ window
    def window(self, anchors, margin=None, extra=()):
        xs0, ys0, xs1, ys1 = [], [], [], []
        for a in anchors:
            b = a.geom.bounds
            xs0.append(b[0])
            ys0.append(b[1])
            xs1.append(b[2])
            ys1.append(b[3])
        for (x, y) in extra:
            xs0.append(x)
            xs1.append(x)
            ys0.append(y)
            ys1.append(y)
        x0, y0, x1, y1 = min(xs0), min(ys0), max(xs1), max(ys1)
        span = max(x1 - x0, y1 - y0)
        m = margin if margin is not None else max(2.0, 0.35 * span)
        x0, y0, x1, y1 = x0 - m, y0 - m, x1 + m, y1 + m
        ob = self.sp.outline.bounds if self.sp.outline is not None else None
        if ob is not None:
            x0, y0 = max(x0, ob[0] - 0.5), max(y0, ob[1] - 0.5)
            x1, y1 = min(x1, ob[2] + 0.5), min(y1, ob[3] + 0.5)
        res = self.res
        while ((x1 - x0) / res + 1) * ((y1 - y0) / res + 1) > self.max_cells:
            res *= 1.25
        return Grid(x0, y0, x1, y1, res)

    # ------------------------------------------------------------------ rasters
    def escape_hit(self, net, geom, r=0.0):
        """Whether `geom` (grown by r) enters another net's escape corridor."""
        return any(n != net and g.distance(geom) < r for g, l, n in self.escapes)

    def blocked(self, grid, net, layer, w, kind="track", skip=()):
        """Cells where a `kind` of `net` (track of width w, or via) centred there breaks a
        requirement on `layer` (with the move margin, `_margin`)."""
        sp = self.sp
        m = 0.71 * grid.res                       # only to size the query
        half = w / 2.0
        out = np.zeros((grid.ny, grid.nx), bool)
        bounds = (grid.x0, grid.y0, grid.x1, grid.y1)
        for it in sp.query(layer, bounds, half + sp.max_need + m + 0.01):
            if it in skip:
                continue
            nd = sp.need(it, net, kind, layer)
            if nd is None:
                continue
            R = half + nd + it.r + TOL
            if it.kind in ("keepout", "corridor"):
                R = half + it.r
            grid.within(it.geom, R + _margin(R, grid.res), out)
        if sp.outline is not None:
            e = sp.edge_need(net, kind, layer)
            if kind == "via":
                e = max(e, sp.plan.notes.get("via_edge_band") or 0.0)
            R = half + e + TOL
            out |= self._off_board(grid, R + _margin(R, grid.res))
        return out

    def via_allowed(self, grid, net, layers_all):
        """Cells where a through via of `net` fits on every copper layer."""
        sp = self.sp
        D, d = sp.via_size(net)
        rv = D / 2.0
        m = 0.0            # a via sits on a cell centre and is checked there exactly
        out = np.zeros((grid.ny, grid.nx), bool)
        h2h = sp.settings.get("hole_to_hole", 0.0) or 0.0
        pitch = sp.same_net_via_pitch(net)
        bounds = (grid.x0, grid.y0, grid.x1, grid.y1)
        seen = set()
        for layer in layers_all:
            for it in sp.query(layer, bounds, rv + sp.max_need + max(h2h, pitch) + m):
                if id(it) in seen:
                    continue
                seen.add(id(it))
                same = it.net is not None and it.net == net and it.kind in ("pad", "track", "via", "corridor", "shape")
                if same:
                    if it.kind == "via":
                        grid.within(it.geom, pitch + m, out)
                    elif it.kind == "pad":
                        if it.hole is not None:
                            hg, hr = it.hole
                            grid.within(hg, hr + d / 2.0 + h2h + m + TOL, out)
                        if it.smd and not sp.via_in_pad:
                            grid.within(it.geom, rv + m, out)
                    continue
                nd = sp.need(it, net, "via", layer)
                if nd is not None:
                    r = rv + nd + it.r + m + TOL
                    if it.kind in ("keepout", "corridor"):
                        r = rv + it.r + m * 0.5
                    grid.within(it.geom, r, out)
                if it.hole is not None and it.kind in ("pad", "via"):
                    hg, hr = it.hole
                    grid.within(hg, hr + d / 2.0 + h2h + m + TOL, out)
        box = _box(grid)
        for g, l, n in self.escapes:
            if n != net and g.intersects(box):
                grid.within(g, rv, out)
        if sp.outline is not None:
            e = max(sp.edge_need(net, "via", l) for l in sp.cu)
            e = max(e, sp.plan.notes.get("via_edge_band") or 0.0)
            out |= self._off_board(grid, rv + e + m + TOL)
        return ~out

    def _off_board(self, grid, d):
        """Cells whose centre is not inside the board outline shrunk by d (quad_segs 4)."""
        outline = self.sp.outline
        key = (id(outline), d)
        hit = _INNER.get(key)
        if hit is None:
            inner = outline.buffer(-d, quad_segs=4)
            if not inner.is_empty:
                shapely.prepare(inner)
            if len(_INNER) >= 1000:
                _INNER.clear()
            _INNER[key] = hit = (outline, inner)
        inner = hit[1]
        if inner.is_empty:
            return np.ones((grid.ny, grid.nx), bool)
        return ~_contains_grid(inner, grid)

    def cost_layer(self, grid, net, layer, w, layer_factor=1.0, skip=()):
        blk = self.blocked(grid, net, layer, w, "track", skip)
        c = np.full((grid.ny, grid.nx), float(layer_factor))
        sp = self.sp
        if self.pour_cost > 0:
            # crossing another net's pour cuts it; a ground pour (the return plane, and the
            # pour a cut leaves as a weakly tied island) costs three times as much
            gnd = getattr(self, "gnd", set())
            for weight, polys in ((1.0, [g for n, l, g, _ in sp.zones if l == layer and n != net and n not in gnd]),
                                  (3.0, [g for n, l, g, _ in sp.zones if l == layer and n != net and n in gnd])):
                box = _box(grid)
                hit = [g for g in polys if g.intersects(box)]
                if hit:
                    c[_pour_mask(grid, hit, box)] += weight * self.pour_cost * layer_factor
        if self.escapes and self.escape_cost > 0:
            box = _box(grid)
            em = np.zeros_like(blk)
            for g, l, n in self.escapes:
                if l == layer and n != net and g.intersects(box):
                    grid.within(g, w / 2.0, em)
            c[em] += self.escape_cost * layer_factor
        if self.halo > 0 and self.halo_cost > 0:
            hm = np.zeros_like(blk)
            bounds = (grid.x0, grid.y0, grid.x1, grid.y1)
            for it in sp.query(layer, bounds, w + self.halo + sp.max_need):
                if it.kind != "pad" or (it.net and it.net == net):
                    continue
                nd = sp.need(it, net, "track", layer) or 0.0
                grid.within(it.geom, w / 2.0 + nd + self.halo, hm)
            c[hm] += self.halo_cost * layer_factor
        c[blk] = INF
        return c

    # ------------------------------------------------------------------ anchors -> cells
    def _cells(self, grid, a, li, cost, plane, layer=None):
        """Flat indices of free cells inside anchor `a` (its copper on `layer`) on layer index li."""
        g = a.geom_on(layer) if layer is not None else (a.geom if a.grow <= 0 else a.geom.buffer(a.grow, quad_segs=4))
        centre = a.centre_on(layer) if layer is not None else a.centre
        i0, i1, j0, j1 = grid._span(g.bounds, 0.0)
        if i0 > i1 or j0 > j1:
            return np.zeros(0, np.int64)
        X, Y = grid.coords(i0, i1, j0, j1)
        m = shapely.contains_xy(g, X, Y)
        jj, ii = np.nonzero(m)
        k = li * plane + (jj + j0) * grid.nx + (ii + i0)
        k = k[np.isfinite(cost.reshape(-1)[k])]
        if k.size == 0 and centre is not None:
            # a pad smaller than a cell: the nearest free cell to its centre within half a cell
            ci, cj = grid.ij(*centre)
            best = None
            for dj in (-1, 0, 1):
                for di in (-1, 0, 1):
                    i, j = ci + di, cj + dj
                    if grid.inside(i, j):
                        kk = li * plane + j * grid.nx + i
                        if np.isfinite(cost.reshape(-1)[kk]):
                            dd = math.hypot(*(np.subtract(grid.xy(i, j), centre)))
                            if g.buffer(0.5 * grid.res).contains(Point(grid.xy(i, j))) and (best is None or dd < best[0]):
                                best = (dd, kk)
            if best is not None:
                k = np.array([best[1]], np.int64)
        return k

    # ------------------------------------------------------------------ connect
    def connect(self, net, sources, targets, width, layers, layer_factor=None, via=True, window=None,
                via_cost=None, skip=(), max_len=None, avoid=(), phys=None):
        """Route one track of `width` from any source anchor to any target anchor on the
        given layers (vias between them when `via`), keeping the track centre `r` away from
        each (geometry, r, layer) in `avoid`. Returns a Route or None."""
        sp = self.sp
        self.stats["calls"] += 1
        grid = window or self.window(list(sources) + list(targets))
        layers = [l for l in sp.cu if l in layers]
        if not layers:
            return None
        nl = len(layers)
        plane = grid.nx * grid.ny
        cost = np.empty((nl, grid.ny, grid.nx))
        for li, l in enumerate(layers):
            f = (layer_factor or {}).get(l, 1.0)
            cost[li] = self.cost_layer(grid, net, l, width, f, skip)
            for g, r, al in avoid:
                if al == l:
                    m_ = np.zeros((grid.ny, grid.nx), bool)
                    grid.within(g, r, m_)
                    cost[li][m_] = INF
        flat = cost.reshape(-1)
        if via and nl > 1:
            vmask = self.via_allowed(grid, net, sp.cu).reshape(-1)
        else:
            vmask = np.zeros(plane, bool)
        src = []
        for a in sources:
            for li, l in enumerate(layers):
                if l in a.layers:
                    src.append(self._cells(grid, a, li, cost, plane, l))
        src = np.unique(np.concatenate(src)) if src else np.zeros(0, np.int64)
        dst = np.zeros(nl * plane, bool)
        tb = []
        for a in targets:
            for li, l in enumerate(layers):
                if l in a.layers:
                    k = self._cells(grid, a, li, cost, plane, l)
                    dst[k] = True
                    if k.size:
                        r = k % plane
                        tb.append((r % grid.nx).min())
                        tb.append((r % grid.nx).max())
                        tb.append((r // grid.nx).min())
                        tb.append((r // grid.nx).max())
        self.stats["cells"] += int(nl * plane)
        if src.size == 0 or not dst.any():
            return None
        if dst[src].any():
            return Route(net=net, width=width, res=grid.res)     # already touching
        xs, ys = tb[0::4] + tb[1::4], tb[2::4] + tb[3::4]
        tx0, tx1, ty0, ty1 = min(xs), max(xs), min(ys), max(ys)
        vc = self.via_cost if via_cost is None else via_cost
        if phys is not None:
            # physics-priced search (kae.em.route): phys(grid, layers) gives the move-cost arrays
            from kae.em.route import search_flat
            ph = phys(grid, layers)
            path = search_flat(cost, ph["self"], ph["px"], ph["py"], ph["pot"], ph["void"], vmask, src, dst, grid.res,
                               via_cost=float(vc), lam=1.0, floor=ph.get("floor", 0.2),
                               target=((ty0 + ty1) // 2, (tx0 + tx1) // 2), pot2=ph.get("pot2"), void2=ph.get("void2"),
                               theta=ph.get("theta"), th_src=ph.get("th_src"), th_dst=ph.get("th_dst"),
                               vself=ph.get("vself"))
            nexp = 0
        else:
            path, nexp = self.K.astar(flat, vmask, src.astype(np.int64), dst, nl, grid.ny, grid.nx, grid.res, float(vc),
                                      int(tx0), int(tx1), int(ty0), int(ty1), int(self.max_exp))
        self.stats["expansions"] += int(nexp)
        if path.size == 0:
            return None
        rt = self._geometry(grid, net, width, layers, path, sources, targets)
        if rt is None:
            return None
        rt.expansions = int(nexp)
        rt.res = grid.res
        if max_len is not None and rt.length > max_len:
            return None
        self.stats["found"] += 1
        return rt

    # ------------------------------------------------------------------ path -> geometry
    def _geometry(self, grid, net, width, layers, path, sources, targets):
        sp = self.sp
        plane = grid.nx * grid.ny
        runs = []      # [layer, [pts]]
        vias = []
        prev_l = None
        for k in path.tolist():
            li, r = divmod(k, plane)
            j, i = divmod(r, grid.nx)
            p = grid.xy(i, j)
            l = layers[li]
            if prev_l is None or l != prev_l:
                if prev_l is not None:
                    vias.append(p)
                runs.append([l, [p]])
                prev_l = l
            else:
                runs[-1][1].append(p)
        segs = []
        for ri, (l, pts) in enumerate(runs):
            pts = _merge_collinear(pts)
            if ri == 0:
                pts = self._snap_end(net, l, width, pts, sources, first=True)
            if ri == len(runs) - 1:
                pts = self._snap_end(net, l, width, pts, targets, first=False)
            pts = self._pull(net, l, width, pts)
            for a, b in zip(pts[:-1], pts[1:]):
                if math.dist(a, b) > 1e-6:
                    segs.append((l, a, b))
        # exact verification of every piece
        for l, a, b in segs:
            if sp.track_violations(net, l, width, a, b, first=True):
                return None
        for (x, y) in vias:
            if sp.via_violations(net, x, y, first=True):
                return None
        length = sum(math.dist(a, b) for _, a, b in segs)
        return Route(net=net, width=width, segs=segs, vias=vias, length=length)

    def boxes_in(self, rt, reach=1.5, radius=3.5):
        """Other nets' single-layer pads that a route `rt` walls off: pads within `reach` of
        its segments (edge to edge) whose copper could reach the edge of a `radius` window,
        or a via site, before the route and cannot after it (a track of the pad net's class
        width, as the general router draws it, at KiCad's clearances). [(pad Item, layer)]"""
        from scipy import ndimage
        sp = self.sp
        out = []
        if rt is None or not rt.segs:
            return out
        for layer in {l for l, _, _ in rt.segs}:
            segs = [LineString([a, b]) for l, a, b in rt.segs if l == layer]
            line = shapely.union_all(segs)
            bb = line.bounds
            for it in sp.query(layer, bb, rt.width / 2 + reach):
                if it.kind != "pad" or not it.net or it.net == rt.net or len(it.layers) > 1:
                    continue
                if line.distance(it.geom) - rt.width / 2 > reach:
                    continue
                if self._connected_pad(it):
                    continue
                x0, y0, x1, y1 = it.geom.bounds
                grid = Grid(x0 - radius, y0 - radius, x1 + radius, y1 + radius, self.res)
                w_p = sp.width_limits(it.net, layer)[1]
                blk = self.blocked(grid, it.net, layer, w_p, "track")
                own = np.zeros_like(blk)
                grid.within(it.geom, 0.0, own)
                if not own.any():
                    continue
                vias = self.via_allowed(grid, it.net, sp.cu)

                def reach_of(free):
                    """(cells reachable from the pad, whether that reaches the window edge or a
                    via site)."""
                    lab, _ = ndimage.label(free | own, structure=np.ones((3, 3), bool))
                    ids = set(np.unique(lab[own])) - {0}
                    if not ids:
                        return 0, False
                    mine = np.isin(lab, list(ids))
                    border = mine[0, :].any() or mine[-1, :].any() or mine[:, 0].any() or mine[:, -1].any()
                    return int(mine.sum()), bool(border or (mine & vias).any())
                n0, ok0 = reach_of(~blk)
                if not ok0:
                    continue                      # boxed in already: not this route's doing
                c = sp._pair(rt.net, it.net, layer)
                gap = (c.track_track if c is not None else sp.max_need) + rt.width / 2 + w_p / 2
                after = blk.copy()
                grid.within(line, gap, after)
                n1, ok1 = reach_of(~after)
                # walled off: no way out, or only a sliver of the room it had (a corridor
                # between the route and the part's other pins)
                if not ok1 or n1 < 0.25 * n0:
                    out.append((it, layer))
        return out

    def _connected_pad(self, it):
        """Whether committed copper of the pad's net already touches it (it has escaped)."""
        for x in self.sp.routed:
            if x.net == it.net and x.geom.distance(it.geom) <= (x.r or 0.0) + 1e-6:
                return True
        return False

    def _snap_end(self, net, layer, w, pts, anchors, first):
        """Move the path end onto the anchor centre (pad centre) when that piece is legal."""
        end = pts[0] if first else pts[-1]
        best = None
        for a in anchors:
            ac = a.centre_on(layer)
            if ac is None or layer not in a.layers:
                continue
            g = a.geom_on(layer)
            if g.distance(Point(end)) > 1e-6 + 0.75 * self.res:
                continue
            d = math.dist(end, ac)
            if best is None or d < best[0]:
                best = (d, ac)
        if best is None or best[0] < 1e-9:
            return pts
        c = tuple(best[1])
        nb = pts[1] if first and len(pts) > 1 else (pts[-2] if not first and len(pts) > 1 else end)
        # try the centre straight to the next point, else to the current end
        for q in (nb, end):
            if not self.sp.track_violations(net, layer, w, c, q, first=True):
                if q is nb and len(pts) > 1:
                    return [c] + pts[1:] if first else pts[:-1] + [c]
                return [c] + pts if first else pts + [c]
        return pts

    def _pull(self, net, layer, w, pts):
        """String pulling: keep the farthest straight shortcut that is exactly legal."""
        if len(pts) <= 2:
            return pts
        sp = self.sp
        out = [pts[0]]
        i = 0
        n = len(pts)
        while i < n - 1:
            cand = i + 1
            for j in range(n - 1, i + 1, -1):
                if not sp.track_violations(net, layer, w, pts[i], pts[j], first=True):
                    cand = j
                    break
            out.append(pts[cand])
            i = cand
        return out


# board outlines shrunk for GridRouter._off_board: (id(outline), d) -> (outline, prepared)
_INNER = {}


def _contains_grid(g, grid, t=16):
    """shapely.contains_xy(g, cell centres) over the whole grid for a prepared polygon g,
    deciding blocks of t x t cells at once: a block whose bounding box lies in g's interior
    (contains_properly) is all inside, one whose box misses g all outside; only the cells of
    the blocks across g's boundary are tested one by one."""
    xs = grid.x0 + np.arange(grid.nx) * grid.res
    ys = grid.y0 + np.arange(grid.ny) * grid.res
    ia = np.arange(0, grid.nx, t)
    ja = np.arange(0, grid.ny, t)
    ib = np.minimum(ia + t - 1, grid.nx - 1)
    jb = np.minimum(ja + t - 1, grid.ny - 1)
    boxes = shapely.box(xs[ia][None, :], ys[ja][:, None], xs[ib][None, :], ys[jb][:, None])
    flat = (xs[ia] < xs[ib])[None, :] & (ys[ja] < ys[jb])[:, None]
    full = shapely.contains_properly(g, boxes) & flat
    miss = ~shapely.intersects(g, boxes) & flat
    cell_full = np.repeat(np.repeat(full, t, axis=0), t, axis=1)[:grid.ny, :grid.nx]
    cell_miss = np.repeat(np.repeat(miss, t, axis=0), t, axis=1)[:grid.ny, :grid.nx]
    out = cell_full.copy()
    unsure = ~(cell_full | cell_miss)
    if unsure.any():
        jj, ii = np.nonzero(unsure)
        out[jj, ii] = shapely.contains_xy(g, xs[ii], ys[jj])
    return out


def _pour_mask(grid, polys, box, step=4):
    """Cells inside any of `polys` (pours), sampled every `step` cells and spread to the
    block: a soft cost needs no cell-exact edge, and a pour with its holes is the slowest
    polygon to test point by point."""
    from shapely.ops import unary_union
    g = unary_union([p.intersection(box) for p in polys])
    if g.is_empty:
        return np.zeros((grid.ny, grid.nx), bool)
    shapely.prepare(g)
    xs = grid.x0 + (np.arange(0, grid.nx, step) + (step - 1) / 2.0) * grid.res
    ys = grid.y0 + (np.arange(0, grid.ny, step) + (step - 1) / 2.0) * grid.res
    X, Y = np.meshgrid(xs, ys)
    m = shapely.contains_xy(g, X, Y)
    full = np.repeat(np.repeat(m, step, axis=0), step, axis=1)
    return full[:grid.ny, :grid.nx]


def _merge_collinear(pts):
    if len(pts) <= 2:
        return list(pts)
    out = [pts[0]]
    for k in range(1, len(pts) - 1):
        a, b, c = out[-1], pts[k], pts[k + 1]
        cr = (b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0])
        if abs(cr) > 1e-12:
            out.append(b)
    out.append(pts[-1])
    return out


def _box(grid):
    from shapely.geometry import box
    return box(grid.x0, grid.y0, grid.x1, grid.y1)
