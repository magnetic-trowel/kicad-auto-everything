# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Grid search with exact verification: how the critical router draws one connection.

`GridRouter.connect(net, sources, targets, width, layers)` routes a track of one width
between two sets of same-net copper (pads, committed tracks and vias) inside a window:

1. **Raster.** One cost grid per allowed copper layer (default resolution 0.05 mm, coarser
   for large windows). A cell is blocked when a track centre there would come closer to an
   obstacle than half the width plus KiCad's requirement for that pair (`Space.need`) plus
   a margin of 0.71 cell, so that the straight piece between two free neighbouring cell
   centres is legal too. Board edges, rule areas and thermal-spoke corridors block the same
   way. Free cells get cost multipliers: other nets' pours on the layer (crossing a pour
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
from shapely.geometry import LineString, Point

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
        through a circumscribed buffer."""
        if out is None:
            out = np.zeros((self.ny, self.nx), bool)
        i0, i1, j0, j1 = self._span(geom.bounds, r)
        if i0 > i1 or j0 > j1:
            return out
        X, Y = self.coords(i0, i1, j0, j1)
        gt = geom.geom_type
        if gt == "Point":
            m = np.hypot(X - geom.x, Y - geom.y) <= r
        elif gt == "LineString" and len(geom.coords) == 2:
            (ax, ay), (bx, by) = geom.coords
            m = _seg_dist(X, Y, ax, ay, bx, by) <= r
        else:
            q = 4
            g = geom.buffer(r / math.cos(math.pi / (4 * q)), quad_segs=q) if r > 0 else geom
            if g.is_empty:
                return out
            m = shapely.contains_xy(g, X, Y)
            if r <= 0:
                m |= shapely.intersects_xy(g, X, Y)
        out[j0:j1 + 1, i0:i1 + 1] |= m
        return out


def _seg_dist(X, Y, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    l2 = dx * dx + dy * dy
    if l2 < 1e-18:
        return np.hypot(X - ax, Y - ay)
    t = np.clip(((X - ax) * dx + (Y - ay) * dy) / l2, 0.0, 1.0)
    return np.hypot(X - (ax + t * dx), Y - (ay + t * dy))


# ----------------------------------------------------------------------------- results
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
    def blocked(self, grid, net, layer, w, kind="track", skip=()):
        """Cells where a `kind` of `net` (track of width w, or via) centred there breaks a
        requirement on `layer` (with the 0.71-cell margin)."""
        sp = self.sp
        m = 0.71 * grid.res
        half = w / 2.0
        out = np.zeros((grid.ny, grid.nx), bool)
        bounds = (grid.x0, grid.y0, grid.x1, grid.y1)
        for it in sp.query(layer, bounds, half + sp.max_need + m + 0.01):
            if it in skip:
                continue
            nd = sp.need(it, net, kind, layer)
            if nd is None:
                continue
            r = half + nd + it.r + m + TOL
            if it.kind in ("keepout", "corridor"):
                r = half + it.r + m * 0.5
            grid.within(it.geom, r, out)
        if sp.outline is not None:
            e = sp.edge_need(net, kind, layer)
            if kind == "via":
                e = max(e, sp.plan.notes.get("via_edge_band") or 0.0)
            inner = sp.outline.buffer(-(half + e + m + TOL), quad_segs=4)
            X, Y = grid.coords(0, grid.nx - 1, 0, grid.ny - 1)
            ok = shapely.contains_xy(inner, X, Y) if not inner.is_empty else np.zeros_like(out)
            out |= ~ok
        return out

    def via_allowed(self, grid, net, layers_all):
        """Cells where a through via of `net` fits on every copper layer."""
        sp = self.sp
        D, d = sp.via_size(net)
        rv = D / 2.0
        m = 0.71 * grid.res
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
                same = it.net is not None and it.net == net and it.kind in ("pad", "track", "via", "corridor")
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
        if sp.outline is not None:
            e = max(sp.edge_need(net, "via", l) for l in sp.cu)
            e = max(e, sp.plan.notes.get("via_edge_band") or 0.0)
            inner = sp.outline.buffer(-(rv + e + m + TOL), quad_segs=4)
            X, Y = grid.coords(0, grid.nx - 1, 0, grid.ny - 1)
            out |= ~shapely.contains_xy(inner, X, Y) if not inner.is_empty else np.ones_like(out)
        return ~out

    def cost_layer(self, grid, net, layer, w, layer_factor=1.0, skip=()):
        blk = self.blocked(grid, net, layer, w, "track", skip)
        c = np.full((grid.ny, grid.nx), float(layer_factor))
        sp = self.sp
        if self.pour_cost > 0:
            pm = np.zeros_like(blk)
            for g in sp.foreign_zone_polys(net, layer):
                if g.intersects(_box(grid)):
                    grid.within(g, 0.0, pm)
            c[pm] += self.pour_cost * layer_factor
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
    def _cells(self, grid, a, li, cost, plane):
        """Flat indices of free cells inside anchor `a` on layer index li."""
        g = a.geom if a.grow <= 0 else a.geom.buffer(a.grow, quad_segs=4)
        i0, i1, j0, j1 = grid._span(g.bounds, 0.0)
        if i0 > i1 or j0 > j1:
            return np.zeros(0, np.int64)
        X, Y = grid.coords(i0, i1, j0, j1)
        m = shapely.contains_xy(g, X, Y)
        jj, ii = np.nonzero(m)
        k = li * plane + (jj + j0) * grid.nx + (ii + i0)
        k = k[np.isfinite(cost.reshape(-1)[k])]
        if k.size == 0 and a.centre is not None:
            # a pad smaller than a cell: the nearest free cell to its centre within half a cell
            ci, cj = grid.ij(*a.centre)
            best = None
            for dj in (-1, 0, 1):
                for di in (-1, 0, 1):
                    i, j = ci + di, cj + dj
                    if grid.inside(i, j):
                        kk = li * plane + j * grid.nx + i
                        if np.isfinite(cost.reshape(-1)[kk]):
                            dd = math.hypot(*(np.subtract(grid.xy(i, j), a.centre)))
                            if g.buffer(0.5 * grid.res).contains(Point(grid.xy(i, j))) and (best is None or dd < best[0]):
                                best = (dd, kk)
            if best is not None:
                k = np.array([best[1]], np.int64)
        return k

    # ------------------------------------------------------------------ connect
    def connect(self, net, sources, targets, width, layers, layer_factor=None, via=True, window=None,
                via_cost=None, skip=(), max_len=None):
        """Route one track of `width` from any source anchor to any target anchor on the
        given layers (vias between them when `via`). Returns a Route or None."""
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
        flat = cost.reshape(-1)
        if via and nl > 1:
            vmask = self.via_allowed(grid, net, sp.cu).reshape(-1)
        else:
            vmask = np.zeros(plane, bool)
        src = []
        for a in sources:
            for li, l in enumerate(layers):
                if l in a.layers:
                    src.append(self._cells(grid, a, li, cost, plane))
        src = np.unique(np.concatenate(src)) if src else np.zeros(0, np.int64)
        dst = np.zeros(nl * plane, bool)
        tb = []
        for a in targets:
            for li, l in enumerate(layers):
                if l in a.layers:
                    k = self._cells(grid, a, li, cost, plane)
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

    def _snap_end(self, net, layer, w, pts, anchors, first):
        """Move the path end onto the anchor centre (pad centre) when that piece is legal."""
        end = pts[0] if first else pts[-1]
        best = None
        for a in anchors:
            if a.centre is None or layer not in a.layers:
                continue
            g = a.geom if a.grow <= 0 else a.geom.buffer(a.grow)
            if g.distance(Point(end)) > 1e-6 + 0.75 * self.res:
                continue
            d = math.dist(end, a.centre)
            if best is None or d < best[0]:
                best = (d, a.centre)
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
