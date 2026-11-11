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
   distances).

**Pad ends (rule D, `pad_entry` "centreline", the default).** A pad end's goal is the set of
approach anchors of the plan's rule for that pad (constraints.PadRule.targets, i.e.
pad_entry.centreline_targets from release points all round the land): the search ends in a cell
at an anchor a, and the track then runs straight from a to its end on the land's long centre
line, crossing the outline within 10 degrees of its normal, adding no copper past the land and
leaving the solder-mask web to other nets' openings. Where the plan necks the land (a small
two-terminal part, power_copper.neck_rule) the final piece is the neck, and the wider copper
ends neck_len + w/2 off the outline; a track wider than the land is necked to the widest entry
that fits (pad_entry.neck_width). Every piece before the final one keeps off the land. The land
itself and a band of w/2 around it cost extra (ENTRY_PENALTY_MM per crossing), so the old entry
(into a free cell of the pad, then onto its centre when legal) is taken only where no anchor is
reachable, or when a route through an anchor does not verify. With `pad_entry` "centre" every
pad end is the old entry (the A/B arm).

A pad none of whose cells is free (a 0.4 mm-pitch QFN pin 0.2 mm wide, 0.2 mm from its
neighbours at 0.2 mm clearance: the one legal track is exactly as wide as the pad, centred on
it, and the margins above leave it no cell) is left through an escape (`_escapes`): a straight
piece from its centre along one of its axes, legal with no margin at all (EXACT_TOL), to the
nearest free cell past the tight spot; where no piece from the centre is legal, one that starts
on the axis just past the pad, its copper overlapping the pad by `pad_entry_overlap` (KiCad
connects any overlap). A route through an escape is verified the same way.

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

from kae import budget as _budget

from .critical_space import EXACT_TOL, INF, TOL

ENTRY_PENALTY_MM = 2.0     # extra cost (mm of track) of entering a pad other than through a rule-D anchor
GOAL_TRIES = 3             # rule-D anchors whose route fails verification, tried before the old entry

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

    def aligned(self, x, y):
        """The same window shifted by less than half a cell so that (x, y) is a cell centre,
        or None when it already is one."""
        dx = (x - self.x0) / self.res
        dy = (y - self.y0) / self.res
        dx, dy = (dx - round(dx)) * self.res, (dy - round(dy)) * self.res
        if abs(dx) < 1e-6 and abs(dy) < 1e-6:
            return None
        g = Grid(self.x0 + dx, self.y0 + dy, self.x1 + dx, self.y1 + dy, self.res)
        return g

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

def _finest_centre(anchors, layers):
    """The centre of the smallest anchor with one (a pad or via) on one of `layers`, or None."""
    best = None
    for a in anchors:
        for l in layers:
            if l in a.layers:
                c = a.centre_on(l)
                if c is not None:
                    area = a.geom_on(l).area
                    if best is None or area < best[0]:
                        best = (area, tuple(c))
    return None if best is None else best[1]


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
    necks: dict = field(default_factory=dict)  # seg index -> neck width (the final piece into a necked land)
    entries: list = field(default_factory=list)  # how each pad end was reached: "straight", "long", "axial",
                                                 # "radial" (rule D), "centre" / "centre_acute" (the old entry),
                                                 # "physics_exception" (the old entry, kept for the module's physics)
    goals: list = field(default_factory=list)    # rule-D approaches used (connect drop_goals keys)

    def layers(self):
        return sorted({s[0] for s in self.segs})

    def seg_w(self, i):
        """Width of segment i: the route's width, or its neck (never wider than the width)."""
        n = self.necks.get(i)
        return self.width if n is None else min(n, self.width)


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
    pad: int | None = None            # info pad index (the plan's PadRule); found by position when None

    def geom_on(self, layer):
        g = (self.by_layer or {}).get(layer, self.geom)
        return g if self.grow <= 0 else g.buffer(self.grow, quad_segs=4)

    def centre_on(self, layer):
        return (self.centres or {}).get(layer, self.centre)


# ----------------------------------------------------------------------------- router
class GridRouter:
    """Routes single connections in a Space (see the module docstring)."""

    def __init__(self, space, res=0.05, max_cells=1_500_000, halo=0.4, halo_cost=0.6, pour_cost=0.4,
                 via_cost=1.5, max_exp=4_000_000, pad_entry=None):
        self.sp = space
        # "centreline": pad ends by the plan's rule D (module docstring); "centre": they snap onto
        # pad centres (Space.pad_entry from the pad_entry setting by default; "edge" reads as rule D)
        mode = pad_entry or getattr(space, "pad_entry", "centreline")
        self.pad_entry = "centreline" if mode == "edge" else mode
        self._goal_cache = {}
        self.res = res
        self.max_cells = max_cells
        self.halo, self.halo_cost, self.pour_cost = halo, halo_cost, pour_cost
        self.via_cost = via_cost
        self.max_exp = max_exp
        self.K = kernels()
        self.stats = dict(calls=0, found=0, expansions=0, cells=0, entries={}, necks=0, goal_retries=0,
                          fallback_old_entry=0, fallback_crossing=0, lands_kept_out=0, neck_leaf=0)
        self._cross, self._blocked_any, self._had_goals = {}, False, False
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
                        # hole to hole through both drills, as Space.via_violations
                        grid.within(it.geom, pitch + ((it.drill or d) - d) / 2.0 + m + TOL, out)
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
                via_cost=None, skip=(), max_len=None, avoid=(), phys=None, entry=None, drop_goals=(), count=True):
        """Route one track of `width` between anchor sets (see _connect). Stages, each tried only when
        the one before found nothing and had something to give up: other lands of the net and
        necked lands that already have copper kept out of the search (`_free` False), then those
        lands free (a counter `fallback_crossing`).
        `entry`: None / "rule" (rule D, the old entry only as the fallback), "old" (the old entry
        only: a candidate for a caller that prices both, critical_modules.route_hop).
        `drop_goals`: rule-D approaches (Route.goals keys) not to use, for a second candidate.
        `count` False: the caller counts the route it keeps (count_route)."""
        if count:
            self.stats["calls"] += 1
        kw = dict(layer_factor=layer_factor, via=via, window=window, via_cost=via_cost, skip=skip,
                  max_len=max_len, avoid=avoid, phys=phys)
        self._blocked_any, self._had_goals = False, False
        self._drop_goals = set(drop_goals or ())
        legacy = entry == "old"
        rt = self._connect(net, sources, targets, width, layers, _legacy=legacy, **kw)
        if rt is None and self._blocked_any:
            rt = self._connect(net, sources, targets, width, layers, _free=True, _legacy=legacy, **kw)
            if rt is not None and count:
                self.stats["fallback_crossing"] += 1
        self._drop_goals = set()
        if rt is not None and count:
            self._count(rt)
        return rt

    def count_route(self, rt, calls=1):
        """Count a route a caller kept out of several candidates (connect(count=False))."""
        self.stats["calls"] += calls
        if rt is not None:
            self._count(rt)

    def _connect(self, net, sources, targets, width, layers, layer_factor=None, via=True, window=None,
                 via_cost=None, skip=(), max_len=None, avoid=(), phys=None, _aligned=False, _legacy=False,
                 _drop=None, _tries=0, _free=False, _entry="rule"):
        """Route one track of `width` from any source anchor to any target anchor on the
        given layers (vias between them when `via`), keeping the track centre `r` away from
        each (geometry, r, layer) in `avoid`. Returns a Route or None. When the sources or
        the targets have no free cell, the window is shifted (less than half a cell) so the
        smallest pad's centre is a cell centre, and searched once more: a fine-pitch pin
        leaves only a sliver between its neighbours' clearances, which a coarse grid misses
        (siderakb ergo-snm: SCLK at U4's 0.4 mm-pitch pin 34 has 0.025 mm to spare each side
        for a 0.15 mm track, the 0.078 mm grid of a 100 mm window found no cell in it).
        Pad ends follow rule D (module docstring) unless pad_entry is "centre"; a route through
        an anchor that does not verify is searched again without that anchor (GOAL_TRIES), then
        with the old entry only."""
        sp = self.sp
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
        cross = {}
        if self.pad_entry == "centreline" and not _free:
            sources, targets, cross = self._lands_out(grid, net, sources, targets, layers, width)
            for li, l in enumerate(layers):
                for g in cross.get(l, ()):
                    m_ = np.zeros((grid.ny, grid.nx), bool)
                    grid.within(g, width / 2.0 + TOL, m_)
                    cost[li][m_] = INF
            if cross:
                self._blocked_any = True
        self._cross = cross
        flat = cost.reshape(-1)
        if via and nl > 1:
            vmask = self.via_allowed(grid, net, sp.cu).reshape(-1)
        else:
            vmask = np.zeros(plane, bool)
        # rule D: each pad end's approach anchors are goals; the land and a band around it cost
        # extra, so the old entry is taken only where no anchor is reachable
        goal_src, goal_dst = {}, {}
        if self.pad_entry == "centreline" and not _legacy:
            drop = _drop or set()
            for anchors, gd in ((sources, goal_src), (targets, goal_dst)):
                for a in anchors:
                    if a.kind != "pad":
                        continue
                    for li, l in enumerate(layers):
                        if l not in a.layers:
                            continue
                        got = self._goals(net, a, l, width)
                        if not got:
                            continue
                        land, goals = got
                        self._penalize(grid, cost[li], land, width)
                        for goal in goals:
                            if goal["key"] in getattr(self, "_drop_goals", ()):
                                continue
                            for kk in self._disc_cells(grid, goal["a"], li, flat, plane):
                                if kk not in drop:
                                    gd.setdefault(int(kk), goal)
        # a pad whose every cell is blocked (a track as wide as the pad, centred on it, is the
        # only legal way out, with no room left for the raster's margins) is left through an
        # escape: a straight piece from its centre, checked exactly, to a free cell
        esc_src, esc_dst = {}, {}
        src = [np.array(list(goal_src), np.int64)] if goal_src else []
        for a in sources:
            for li, l in enumerate(layers):
                if l in a.layers:
                    k = self._cells(grid, a, li, cost, plane, l)
                    if k.size == 0 and a.kind == "pad":
                        found = self._escapes(grid, net, width, a, l, li, cost, plane)
                        for kk, pts in found:
                            esc_src.setdefault(int(kk), pts)
                        k = np.array([kk for kk, _ in found], np.int64)
                    src.append(k)
        src = np.unique(np.concatenate(src)) if src else np.zeros(0, np.int64)
        dst = np.zeros(nl * plane, bool)
        tb = []

        def bound(k):
            if k.size:
                r = k % plane
                tb.append((r % grid.nx).min())
                tb.append((r % grid.nx).max())
                tb.append((r // grid.nx).min())
                tb.append((r // grid.nx).max())
        if goal_dst:
            k = np.array(list(goal_dst), np.int64)
            dst[k] = True
            bound(k)
        for a in targets:
            for li, l in enumerate(layers):
                if l in a.layers:
                    k = self._cells(grid, a, li, cost, plane, l)
                    if k.size == 0 and a.kind == "pad":
                        found = self._escapes(grid, net, width, a, l, li, cost, plane)
                        for kk, pts in found:
                            esc_dst.setdefault(int(kk), pts[::-1])
                        k = np.array([kk for kk, _ in found], np.int64)
                    dst[k] = True
                    bound(k)
        self.stats["cells"] += int(nl * plane)
        if src.size == 0 or not dst.any():
            c = None if _aligned else _finest_centre(sources if src.size == 0 else targets, layers)
            g2 = grid.aligned(*c) if c is not None else None
            if g2 is None:
                return None
            return self._connect(net, sources, targets, width, layers, layer_factor=layer_factor, via=via, window=g2,
                                 via_cost=via_cost, skip=skip, max_len=max_len, avoid=avoid, phys=phys,
                                 _aligned=True, _legacy=_legacy, _drop=_drop, _tries=_tries, _free=_free,
                                 _entry=_entry)
        special = set(esc_src) | set(esc_dst) | set(goal_src) | set(goal_dst)
        hit = src[dst[src]]
        if hit.size:
            # a shared cell touches both ends only when it is a real anchor cell of both: an
            # escape cell (or a rule-D anchor) is free board reached by a piece _geometry has yet
            # to emit (two same-net balls 0.15 mm apart whose escapes meet in the cell between
            # them were counted routed with no copper)
            if any(k not in special for k in hit.tolist()):
                return Route(net=net, width=width, res=grid.res)     # already touching
            for k in hit.tolist():
                rt = self._geometry(grid, net, width, layers, np.array([k], np.int64), sources, targets,
                                    esc_src, esc_dst, goal_src, goal_dst)
                if rt is not None and (max_len is None or rt.length <= max_len):
                    rt.res = grid.res
                    self._had_goals = bool(goal_src or goal_dst)
                    return rt
            dst = dst.copy()
            dst[hit] = False          # those meetings do not verify: search for another way
            if not dst.any():
                return None
        xs, ys = tb[0::4] + tb[1::4], tb[2::4] + tb[3::4]
        tx0, tx1, ty0, ty1 = min(xs), max(xs), min(ys), max(ys)
        vc = self.via_cost if via_cost is None else via_cost
        # counted work (kae.budget): the module stage's routing spends its budget in work mode too (it charged
        # nothing, so its deadline never bound there): one search (with the work since the last charge: raster,
        # setup, the module's physics), then its A* expansions
        _budget.charge("crit_search", 1.0)
        if phys is not None:
            # physics-priced search (kae.em.route): phys(grid, layers) gives the move-cost arrays
            from kae.em.route import search_flat
            ph = phys(grid, layers)
            path = search_flat(cost, ph["self"], ph["px"], ph["py"], ph["pot"], ph["void"], vmask, src, dst, grid.res,
                               via_cost=float(vc), lam=1.0, floor=ph.get("floor", 0.2),
                               pot2=ph.get("pot2"), void2=ph.get("void2"),
                               theta=ph.get("theta"), th_src=ph.get("th_src"), th_dst=ph.get("th_dst"),
                               vself=ph.get("vself"), cx=ph.get("cx"), cy=ph.get("cy"))
            nexp = 0
        else:
            path, nexp = self.K.astar(flat, vmask, src.astype(np.int64), dst, nl, grid.ny, grid.nx, grid.res, float(vc),
                                      int(tx0), int(tx1), int(ty0), int(ty1), int(self.max_exp))
        self.stats["expansions"] += int(nexp)
        _budget.charge("crit_expansion", float(nexp))
        if path.size == 0:
            # the old entry's cells were goals too (at a price): no path to them either, unless
            # the search ran out of expansions on the dearer board
            if (goal_src or goal_dst) and nexp > self.max_exp:
                self.stats["fallback_old_entry"] += 1
                return self._connect(net, sources, targets, width, layers, layer_factor=layer_factor, via=via,
                                     window=window, via_cost=via_cost, skip=skip, max_len=max_len, avoid=avoid,
                                     phys=phys, _aligned=_aligned, _legacy=True, _free=_free, _entry=_entry)
            return None
        rt = self._geometry(grid, net, width, layers, path, sources, targets, esc_src, esc_dst, goal_src, goal_dst)
        if rt is None:
            ends = [int(k) for k in (path[0], path[-1]) if int(k) in goal_src or int(k) in goal_dst]
            if ends:
                # a route through a rule-D anchor that does not verify: without that anchor, and after
                # GOAL_TRIES of them, the old entry
                drop = set(_drop or ()) | {k for k in ends}
                for k in ends:
                    g = goal_src.get(k) or goal_dst.get(k)
                    drop |= {kk for kk, gg in list(goal_src.items()) + list(goal_dst.items()) if gg is g}
                self.stats["goal_retries"] += 1
                legacy = _tries + 1 >= GOAL_TRIES
                if legacy:
                    self.stats["fallback_old_entry"] += 1
                return self._connect(net, sources, targets, width, layers, layer_factor=layer_factor, via=via,
                                     window=window, via_cost=via_cost, skip=skip, max_len=max_len, avoid=avoid,
                                     phys=phys, _aligned=_aligned, _legacy=legacy, _drop=None if legacy else drop,
                                     _tries=_tries + 1, _free=_free, _entry=_entry)
            return None
        if phys is not None:
            rt.search = (grid, layers, path, ph)          # what the physics search priced (kae.em.pnr.explain)
        rt.expansions = int(nexp)
        rt.res = grid.res
        if max_len is not None and rt.length > max_len:
            return None
        self._had_goals = bool(goal_src or goal_dst)
        return rt

    def _count(self, rt):
        self.stats["found"] += 1
        for k in rt.entries:
            self.stats["entries"][k] = self.stats["entries"].get(k, 0) + 1
        self.stats["necks"] += len(rt.necks)

    # ------------------------------------------------------------------ lands kept out
    def _lands_out(self, grid, net, sources, targets, layers, width):
        """(sources, targets, {layer: [land]}): the lands of `net` the route may not pass over.
        - Every other land of the net in the window (neither a source nor a target): a route
          across it would enter it uncontrolled (ubertooth: 8 overhanging pass-throughs).
        - A necked land (PadRule.neck) that already has copper of its net, dropped from the
          anchors when other anchors remain: a second track would chain the route through the
          neck, which is sized for the land's own current only (a decap carries no DC); the
          route joins that land's track instead (counter `neck_leaf`)."""
        sp = self.sp
        rules = getattr(sp.plan, "pad_rules", None) or {}
        box_ = _box(grid)
        bounds = (grid.x0, grid.y0, grid.x1, grid.y1)

        def has_copper(it, l):
            for x in sp.query(l, it.geom.bounds, 0.0):
                if x.net == net and x.kind in ("track", "via") and x.geom.distance(it.geom) <= x.r + 1e-6:
                    return True
            return False

        def necked(a):
            if a.kind != "pad":
                return None
            for l in a.layers:
                if l not in layers:
                    continue
                r = self._rule_of(net, a, l)
                if r is not None and r.neck is not None and width > r.neck + 1e-9:
                    it = next((x for x in sp.query(l, a.geom_on(l).bounds, 0.0)
                               if x.kind == "pad" and x.idx == r.idx), None)
                    if it is not None and has_copper(it, l):
                        return a.geom_on(l), l
            return None
        cross = {}
        out = []
        for anchors in (sources, targets):
            keep, dropped = [], []
            for a in anchors:
                got = necked(a)
                (dropped if got is not None else keep).append((a, got))
            if dropped and keep:
                for _a, (g, l) in dropped:
                    cross.setdefault(l, []).append(g)
                self.stats["neck_leaf"] += len(dropped)
                out.append([a for a, _ in keep])
            else:
                out.append(list(anchors))
        sources, targets = out
        ends = [(l, a.geom_on(l)) for a in list(sources) + list(targets) for l in a.layers]
        for l in layers:
            mine = [g for ll, g in ends if ll == l]
            for it in sp.query(l, bounds, width):
                if it.kind != "pad" or it.net != net or not it.geom.intersects(box_):
                    continue
                if any(it.geom is g or it.geom.distance(g) < 1e-6 for g in mine):
                    continue
                if any(it.geom is g for g in cross.get(l, ())):
                    continue
                cross.setdefault(l, []).append(it.geom)
                self.stats["lands_kept_out"] += 1
        return sources, targets, cross

    # ------------------------------------------------------------------ rule D goals
    def _rule_of(self, net, a, layer):
        """The plan's PadRule for pad anchor `a` on `layer`, or None."""
        plan = self.sp.plan
        rules = getattr(plan, "pad_rules", None)
        if not rules:
            return None
        if a.pad is not None:
            return rules.get(a.pad)
        g = a.geom_on(layer)
        best = None
        for it in self.sp.query(layer, g.bounds, 0.0):
            if it.kind != "pad" or it.net != net or it.idx < 0 or it.idx not in rules:
                continue
            if it.geom is a.geom or it.geom is g:
                return rules[it.idx]
            if it.pos is not None and g.covers(Point(it.pos)) and it.geom.intersects(g):
                d = math.dist(it.pos, (g.centroid.x, g.centroid.y))
                if best is None or d < best[0]:
                    best = (d, rules[it.idx])
        return best[1] if best else None

    def _goals(self, net, a, layer, w):
        """(land, [goal]) of a pad anchor on `layer` for a track of width w: every rule-D
        approach (PadRule.targets from release points all round the land, the neck applied), each
        goal dict(a, end, kind, wn, w, keep, land, rule, layer); None without a rule or a target.
        Kept per pad, layer and width."""
        rule = self._rule_of(net, a, layer)
        if rule is None:
            return None
        land = a.geom_on(layer)
        if land is None or land.is_empty or land.geom_type not in ("Polygon", "MultiPolygon"):
            return None
        key = (rule.idx, layer, round(w, 5), tuple(round(v, 4) for v in land.bounds))
        hit = self._goal_cache.get(key)
        if hit is not None:
            return hit or None
        from . import pad_entry as PE
        if land.geom_type == "MultiPolygon":
            land = max(land.geoms, key=lambda x: x.area)
        min_w = self.sp.width_limits(net, layer)[0] or 0.0
        wn0, stub0 = rule.width_at(w, min_w)
        c, u, v, W, H = PE.pad_frame(land)
        R = W + H + 2.0
        rels = []
        half = (W - H) / 2 if W - H > PE.SQUARE_TOL * W else 0.0
        for t in sorted({-half, 0.0, half}):
            for sv in (1.0, -1.0):
                rels.append((c[0] + t * u[0] + sv * R * v[0], c[1] + t * u[1] + sv * R * v[1]))
        n_dir = 16 if land.area < PE.ROUND_AREA * W * H else 8
        for k in range(n_dir):
            th = 2 * math.pi * k / n_dir
            ct, st = math.cos(th), math.sin(th)
            rels.append((c[0] + R * (ct * u[0] + st * v[0]), c[1] + R * (ct * u[1] + st * v[1])))
        mask = rule.mask_on(layer)
        goals, seen = [], set()
        for rel in rels:
            wn, stub = wn0, stub0
            ts = rule.targets(rel, wn, land=land, layer=layer, stub=stub)
            if not ts:
                # wider than any entry: the widest that fits, never below the need (pad_entry.neck_width)
                fit, ts2 = PE.neck_width(land, rel, wn, rule.need, min_w, stub=PE.NECK_LEN + w / 2,
                                         max_deg=10.0, mask=mask)
                if fit is not None and fit < wn - 1e-9:
                    ts, wn, stub = ts2, fit, PE.NECK_LEN + w / 2
            if not ts and rule.need > 0:
                # the current needs the width: the wide copper stays (the plan raised the land hazard)
                ts, wn, stub = rule.targets(rel, w, land=land, layer=layer, check_overhang=False), w, None
            for aa, end, kind in ts:
                k2 = (round(aa[0], 4), round(aa[1], 4), round(end[0], 4), round(end[1], 4), round(wn, 4))
                if k2 in seen:
                    continue
                seen.add(k2)
                keep = (w / 2 + PE.NECK_LEN - 1e-3) if wn < w - 1e-9 else w / 2
                goals.append(dict(a=tuple(aa), end=tuple(end), kind=kind, wn=wn, w=w, keep=keep, land=land,
                                  rule=rule, layer=layer, key=(rule.idx, layer) + k2))
        out = (land, goals) if goals else ()
        if len(self._goal_cache) > 20000:
            self._goal_cache.clear()
        self._goal_cache[key] = out
        return out or None

    def _penalize(self, grid, cost, land, w):
        """Raise the cost of the land's cells and of a band of w/2 around it (finite cells only)
        so that entering it other than through an anchor costs about ENTRY_PENALTY_MM."""
        r = w / 2 + 0.5 * grid.res
        m = np.zeros(cost.shape, bool)
        grid.within(land, r, m)
        n = max(1.0, r / grid.res)
        m &= np.isfinite(cost)
        cost[m] += ENTRY_PENALTY_MM / (grid.res * (n + 1.0))

    def _disc_cells(self, grid, p, li, flat, plane):
        """Free cells within 0.75 cell of point p on layer index li, nearest first."""
        ci, cj = grid.ij(*p)
        out = []
        for dj in (-1, 0, 1):
            for di in (-1, 0, 1):
                i, j = ci + di, cj + dj
                if grid.inside(i, j):
                    kk = li * plane + j * grid.nx + i
                    d = math.dist(grid.xy(i, j), p)
                    if d <= 0.75 * grid.res + 1e-9 and np.isfinite(flat[kk]):
                        out.append((d, kk))
        return [kk for _, kk in sorted(out)]

    def _escapes(self, grid, net, width, a, layer, li, cost, plane):
        """Ways out of pad anchor `a` on `layer` when none of its cells is free: [(flat cell
        index, [centre, p])], where the piece centre -> p runs along one of the pad's axes and
        is legal exactly (EXACT_TOL: a 0.2 mm track centred on a 0.2 mm pad between
        neighbours 0.2 mm away at 0.2 mm clearance has nothing to spare), and p -> the free
        cell is legal too. One per direction (both ways along each axis of the pad's
        bounding rectangle), the shortest. The walk along an axis ends where the piece from
        the centre stops being legal (a longer piece only adds copper) or past the pad's
        reach plus the largest requirement, the width and two cells."""
        c = a.centre_on(layer)
        g = a.geom_on(layer)
        if c is None or g is None or g.is_empty:
            return []
        sp = self.sp
        rect = g.minimum_rotated_rectangle
        pts = list(rect.exterior.coords)[:4] if rect.geom_type == "Polygon" else []
        if len(pts) < 4:
            return []
        axes = []
        for p, q in ((pts[0], pts[1]), (pts[1], pts[2])):
            dx, dy = q[0] - p[0], q[1] - p[1]
            n = math.hypot(dx, dy)
            if n > 1e-9:
                axes.append((dx / n, dy / n))
        # a round pad's (polygonized circle's) smallest rectangle turns by whatever angle its
        # vertices give (28 degrees for a 0.24 mm ball): the board's axes too, where they differ
        for ax in ((1.0, 0.0), (0.0, 1.0)):
            if all(abs(ax[0] * v - ax[1] * u) > 1e-3 for u, v in axes):
                axes.append(ax)
        reach = max(math.dist(c, p) for p in pts) + sp.max_need + width + 2 * grid.res
        step = grid.res / 2
        flat = cost.reshape(-1)
        ovl = float(getattr(sp, "pad_overlap", 0.05))

        def walk(s0, dx, dy):
            """The first free cell reached by a legal straight piece from s0 along (dx, dy)."""
            k = 1
            while k * step <= reach:
                p = (s0[0] + k * step * dx, s0[1] + k * step * dy)
                k += 1
                if sp.track_violations(net, layer, width, s0, p, first=True, tol=EXACT_TOL):
                    return None
                i0 = int(math.floor((p[0] - grid.x0) / grid.res))
                j0 = int(math.floor((p[1] - grid.y0) / grid.res))
                cells = [(i, j) for i in (i0, i0 + 1) for j in (j0, j0 + 1) if grid.inside(i, j)]
                cells.sort(key=lambda ij: math.dist(grid.xy(*ij), p))
                for i, j in cells:
                    kk = li * plane + j * grid.nx + i
                    if not np.isfinite(flat[kk]):
                        continue
                    q = grid.xy(i, j)
                    if not sp.track_violations(net, layer, width, p, q, first=True, tol=EXACT_TOL):
                        return (kk, [tuple(s0), p])
            return None

        out = []
        for ux, uy in axes:
            for sx in (1.0, -1.0):
                dx, dy = sx * ux, sx * uy
                hit = walk(tuple(c), dx, dy)
                if hit is None and ovl > 0:
                    # the track's end outside the pad, its copper still overlapping the pad by
                    # `ovl` (KiCad connects any overlap): beside a 0.4 mm-pitch ball the centre is
                    # 0.18 mm from the neighbours for a 0.2 mm track at 0.2 mm clearance, while
                    # just past the rim the gap opens (circuitmonkey chips-0123's U1, 4 balls)
                    h = max((p[0] - c[0]) * dx + (p[1] - c[1]) * dy for p in pts)
                    d = step / 2
                    while hit is None and d <= h + width / 2 - ovl + 1e-9:
                        s0 = (c[0] + d * dx, c[1] + d * dy)
                        d += step / 2
                        if g.distance(Point(s0)) > width / 2 - ovl + 1e-9:
                            break
                        hit = walk(s0, dx, dy)
                if hit is not None:
                    out.append(hit)
        return out

    # ------------------------------------------------------------------ path -> geometry
    def _geometry(self, grid, net, width, layers, path, sources, targets, esc_src=None, esc_dst=None,
                  goal_src=None, goal_dst=None):
        sp = self.sp
        plane = grid.nx * grid.ny
        runs = []      # [layer, [pts]]
        vias = []
        prev_l = None
        path_l = path.tolist()
        pre = (esc_src or {}).get(path_l[0]) if path_l else None
        post = (esc_dst or {}).get(path_l[-1]) if path_l else None
        gpre = (goal_src or {}).get(path_l[0]) if path_l else None
        gpost = (goal_dst or {}).get(path_l[-1]) if path_l else None
        if gpre is not None:
            pre = None
        if gpost is not None:
            post = None
        for k in path_l:
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
        if runs and pre:
            runs[0][1] = list(pre) + runs[0][1]
        if runs and post:
            runs[-1][1] = runs[-1][1] + list(post)
        if runs and gpre is not None:
            runs[0][1] = [gpre["a"]] + runs[0][1]
        if runs and gpost is not None:
            runs[-1][1] = runs[-1][1] + [gpost["a"]]
        # a route through an escape holds pieces with no room beyond the requirement: it is
        # verified without our margin (KiCad's requirement exactly)
        tol = EXACT_TOL if (pre or post) else TOL
        segs, necks, entries = [], {}, []
        for ri, (l, pts) in enumerate(runs):
            pts = _merge_collinear(pts)
            first, last = ri == 0, ri == len(runs) - 1
            head, tail = first and not pre and gpre is None, last and not post and gpost is None
            keep = [(g["land"], g["keep"]) for g, on in ((gpre, first), (gpost, last)) if g is not None and on]
            keep += [(g, width / 2) for g in (self._cross or {}).get(l, ())]
            if head:
                pts = self._snap_end(net, l, width, pts, sources, first=True)
            if tail:
                pts = self._snap_end(net, l, width, pts, targets, first=False)
            pts = self._pull(net, l, width, pts, tol, keep=keep)
            if any(g.distance(LineString([u, v])) < r - 1e-6 for u, v in zip(pts[:-1], pts[1:]) for g, r in keep):
                return None                     # a piece before the final one runs over the land
            lead = trail = None
            if first and gpre is not None:
                lead = self._final(net, l, gpre, pts[1] if len(pts) > 1 else None, tol)
                if lead is None:
                    return None
                if lead[1]:
                    pts = pts[1:]           # straight in from the point before the anchor: no corner
                pts = [lead[0]] + pts
                entries.append(lead[2])
            elif first and not pre and self._ends_at_pad(pts[0], sources, l):
                entries.append(self._old_kind(pts[0], pts[1] if len(pts) > 1 else None, sources, l))
            if last and gpost is not None:
                q = pts[-2] if len(pts) > 1 and not (lead is not None and len(pts) <= 2) else None
                trail = self._final(net, l, gpost, q, tol)
                if trail is None:
                    return None
                if trail[1]:
                    pts = pts[:-1]
                pts = pts + [trail[0]]
                entries.append(trail[2])
            elif last and not post and self._ends_at_pad(pts[-1], targets, l):
                entries.append(self._old_kind(pts[-1], pts[-2] if len(pts) > 1 else None, targets, l))
            if not (lead is not None and not lead[1] and gpre["wn"] < width - 1e-9) and \
                    not (trail is not None and not trail[1] and gpost["wn"] < width - 1e-9):
                pts = _merge_collinear(pts)     # a straight end in line with the rest is one piece
            n0 = len(segs)
            for u, v in zip(pts[:-1], pts[1:]):
                if math.dist(u, v) > 1e-6:
                    segs.append((l, u, v))
            if lead is not None and not lead[1] and gpre["wn"] < width - 1e-9 and len(segs) > n0:
                necks[n0] = gpre["wn"]
            if trail is not None and not trail[1] and gpost["wn"] < width - 1e-9 and len(segs) > n0:
                necks[len(segs) - 1] = gpost["wn"]
        # exact verification of every piece (the final piece into a necked land at the neck)
        for i, (l, a, b) in enumerate(segs):
            w = necks.get(i, width)
            if sp.track_violations(net, l, w, a, b, first=True, tol=tol):
                return None
        for (x, y) in vias:
            if sp.via_violations(net, x, y, first=True):
                return None
        length = sum(math.dist(a, b) for _, a, b in segs)
        rt = Route(net=net, width=width, segs=segs, vias=vias, length=length, necks=necks, entries=entries)
        rt.goals = [g["key"] for g in (gpre, gpost) if g is not None]
        return rt

    def _final(self, net, layer, goal, p, tol):
        """The final piece of a rule-D end: (end, straight, kind). From the anchor a by default;
        straight from p (the point before a) when the rule offers a straight entry from p (within
        10 degrees of the outline normal, no corner) at the full width and that piece is legal.
        None when the piece from a is not legal at its width."""
        rule, land, w = goal["rule"], goal["land"], goal["w"]
        if p is not None and goal["wn"] >= w - 1e-9 and math.dist(p, goal["a"]) > 1e-6:
            for _a2, end2, kind in rule.targets(p, w, land=land, layer=layer):
                if kind == "straight" and not self.sp.track_violations(net, layer, w, p, end2, first=True, tol=tol):
                    return (tuple(end2), True, "straight")
        if self.sp.track_violations(net, layer, goal["wn"], goal["a"], goal["end"], first=True, tol=tol):
            return None
        return (goal["end"], False, goal["kind"])

    def _old_kind(self, end, prev, anchors, layer):
        """"centre", or "centre_acute" when the old entry's piece crosses the land more than 45
        degrees off its normal (an acid trap)."""
        from . import pad_entry as PE
        if prev is None:
            return "centre"
        for a in anchors:
            if a.kind == "pad" and layer in a.layers and a.geom_on(layer).distance(Point(end)) <= 1e-6:
                ang = PE.entry_angle(a.geom_on(layer), prev, end)
                return "centre_acute" if ang is not None and ang > 45.0 else "centre"
        return "centre"

    def _ends_at_pad(self, p, anchors, layer):
        return any(a.kind == "pad" and layer in a.layers and a.geom_on(layer).distance(Point(p)) <= 1e-6
                   for a in anchors)

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

    def _pull(self, net, layer, w, pts, tol=TOL, keep=()):
        """String pulling: keep the farthest straight shortcut that is exactly legal and keeps
        each (land, r) of `keep` at least r from its centre line (rule-D lands: only the final
        piece enters them)."""
        if len(pts) <= 2:
            return pts
        sp = self.sp
        out = [pts[0]]
        i = 0
        n = len(pts)

        def clear(a, b):
            if not keep:
                return True
            seg = LineString([a, b])
            return all(g.distance(seg) >= r - 1e-6 for g, r in keep)
        while i < n - 1:
            cand = i + 1
            for j in range(n - 1, i + 1, -1):
                if clear(pts[i], pts[j]) and \
                        not sp.track_violations(net, layer, w, pts[i], pts[j], first=True, tol=tol):
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
