# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""kae.route.critical_grid rasters: the shortcuts of Grid.within (axis-aligned rectangles
in numpy, cached buffers) and of the board-outline test (blocks of cells decided at once)
give exactly the cells of the plain shapely tests, on random shapes and windows including
cell centres exactly on edges and exactly r from them."""
import math
import random

import numpy as np
import pytest
import shapely
from shapely import affinity
from shapely.geometry import LineString, MultiPolygon, Point, Polygon, box

from kae.route import critical_grid as CG


def _within_ref(grid, geom, r):
    """Grid.within as it was before the shortcuts: every cell of the window against the
    circumscribed buffer."""
    out = np.zeros((grid.ny, grid.nx), bool)
    i0, i1, j0, j1 = grid._span(geom.bounds, r)
    if i0 > i1 or j0 > j1:
        return out
    X, Y = grid.coords(i0, i1, j0, j1)
    gt = geom.geom_type
    if gt == "Point":
        m = np.hypot(X - geom.x, Y - geom.y) <= r
    elif gt == "LineString" and len(geom.coords) == 2:
        (ax, ay), (bx, by) = geom.coords
        m = CG._seg_dist(X, Y, ax, ay, bx, by) <= r
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


def _shape(rng, x0, y0, res):
    """A random shape near (x0, y0); half of the time with corners on cell centres."""
    snap = rng.random() < 0.5

    def c(v):
        return x0 + round((v - x0) / res) * res if snap else v

    cx, cy = c(x0 + rng.uniform(1, 3)), c(y0 + rng.uniform(1, 3))
    w, h = rng.uniform(0.05, 2.0), rng.uniform(0.05, 2.0)
    if snap:
        w, h = max(res, round(w / res) * res), max(res, round(h / res) * res)
    k = rng.randrange(9)
    if k <= 2:
        g = box(cx, cy, cx + w, cy + h, ccw=rng.random() < 0.5)
        if k == 1:          # same rectangle, ring starting at another corner
            cs = list(g.exterior.coords)[:4]
            s = rng.randrange(4)
            g = Polygon(cs[s:] + cs[:s])
        return g
    if k == 3:
        return affinity.rotate(box(cx, cy, cx + w, cy + h), rng.choice([90, 180, 30, 45, 1e-9]), origin=(cx, cy))
    if k == 4:
        return box(cx, cy, cx + w, cy + h).buffer(rng.uniform(0.01, 0.3), quad_segs=rng.choice([2, 4, 8]))
    if k == 5:
        return Point(cx, cy).buffer(w / 2, quad_segs=rng.choice([4, 8, 16]))
    if k == 6:
        return box(cx, cy, cx + w + 0.5, cy + h + 0.5).difference(box(cx + 0.2, cy + 0.2, cx + w + 0.3, cy + h + 0.3))
    if k == 7:
        return MultiPolygon([box(cx, cy, cx + w, cy + h), box(cx + w + 0.3, cy, cx + 2 * w + 0.3, cy + h)])
    return rng.choice([Point(cx, cy), LineString([(cx, cy), (cx + w, cy + h)]),
                       LineString([(cx, cy), (cx + w, cy), (cx + w, cy + h)])])


def test_within_matches_plain_buffer_test():
    rng = random.Random(7)
    n_rect = 0
    for _ in range(3000):
        res = rng.choice([0.05, 0.05, 0.0625, 0.03])
        x0, y0 = rng.choice([(0.0, 0.0), (rng.uniform(-50, 50), rng.uniform(-50, 50)), (100.137, -73.411)])
        geom = _shape(rng, x0, y0, res)
        n_rect += CG._shape(geom)[1] == "rect"
        grid = CG.Grid(x0 + rng.uniform(-0.5, 1.5), y0 + rng.uniform(-0.5, 1.5),
                       x0 + rng.uniform(2.5, 6), y0 + rng.uniform(2.5, 6), res)
        grid.x0, grid.y0 = (x0, y0) if rng.random() < 0.5 else (grid.x0, grid.y0)
        for r in (0.0, -0.05, 1e-7, res, 2 * res, 0.2 + 0.0001, rng.uniform(0.0, 1.5), rng.uniform(0.1, 0.5)):
            want = _within_ref(grid, geom, r)
            got = grid.within(geom, r)
            assert np.array_equal(got, want), (geom.wkt, r, grid.x0, grid.y0, grid.res)
            pre = np.zeros_like(want)
            pre[::3, ::2] = True
            assert np.array_equal(grid.within(geom, r, pre.copy()), want | pre)
    assert n_rect > 600


@pytest.mark.parametrize("t", [2, 3, 16])
def test_contains_grid_matches_contains_xy(t):
    rng = random.Random(t)
    for _ in range(300):
        res = rng.choice([0.05, 0.1, 0.0625])
        x0, y0 = rng.uniform(-5, 5), rng.uniform(-5, 5)
        # a board with a cut-out and a notch, edges often on cell centres
        a = x0 + rng.choice([round(rng.uniform(0, 1) / res) * res, rng.uniform(0, 1)])
        b = y0 + rng.choice([round(rng.uniform(0, 1) / res) * res, rng.uniform(0, 1)])
        board = box(a, b, a + rng.uniform(1, 6), b + rng.uniform(1, 6))
        board = board.difference(Point(a + 1, b + 1).buffer(rng.uniform(0.1, 0.6)))
        board = board.difference(box(a - 1, b + 0.5, a + 0.4, b + 0.7))
        g = board.buffer(-rng.uniform(0, 0.4), quad_segs=4)
        if g.is_empty:
            continue
        shapely.prepare(g)
        grid = CG.Grid(x0, y0, x0 + rng.uniform(0.1, 8), y0 + rng.uniform(0.1, 8), res)
        X, Y = grid.coords(0, grid.nx - 1, 0, grid.ny - 1)
        assert np.array_equal(CG._contains_grid(g, grid, t), shapely.contains_xy(g, X, Y))
