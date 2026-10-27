# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""kae.board.geom: outline chaining and nesting, matched to what pcbnew 10 builds for
the same courtyards and Edge.Cuts (measured cases; see test docstrings)."""
import math

import pytest
from shapely.geometry import Polygon

from kae.board import geom

SQ = [(-2.2, -1.4), (1.9, -1.4), (1.9, 2.0), (-2.2, 2.0)]


def _ring(pts):
    return list(pts) + [pts[0]]


def _lines(pts):
    return [[pts[i], pts[(i + 1) % len(pts)]] for i in range(len(pts))]


def test_lines_chain_into_one_polygon():
    polys, info = geom.polygons(_lines(SQ), [])
    assert len(polys) == 1 and polys[0].equals(Polygon(SQ))
    assert info == dict(open_ends=0, gap=0.0, overlap=False, degenerate=0)


def test_gap_keeps_the_chain_start():
    """pcbnew kept (-2.19, -1.4) when the first line started 10 um off the corner."""
    pts = [(-2.19, -1.4), (1.9, -1.4), (1.9, 2.0), (-2.2, 2.0), (-2.2, -1.4)]
    opens = [[pts[0], pts[1]], [pts[1], pts[2]], [pts[2], pts[3]], [pts[3], pts[4]]]
    polys, info = geom.polygons(opens, [], eps=0.02)
    coords = set(polys[0].exterior.coords)
    assert (-2.19, -1.4) in coords and (-2.2, -1.4) not in coords
    assert info["gap"] == pytest.approx(0.01)


def test_gap_beyond_epsilon_is_open():
    opens = _lines(SQ)
    opens[0] = [(-2.15, -1.4), (1.9, -1.4)]
    polys, info = geom.polygons(opens, [], eps=0.02)
    assert info["open_ends"] == 1


def test_duplicate_outlines_unite_and_flag_overlap():
    """pcbnew keeps both copies raw (undeflated); the region is the same polygon."""
    polys, info = geom.polygons([], [_ring(SQ), _ring(SQ)])
    assert len(polys) == 1 and polys[0].equals(Polygon(SQ)) and info["overlap"]


def test_touching_and_disjoint_outlines():
    a = [(-2.2, -1.4), (0.0, -1.4), (0.0, 2.0), (-2.2, 2.0)]
    b = [(0.0, -1.4), (1.9, -1.4), (1.9, 2.0), (0.0, 2.0)]
    polys, info = geom.polygons([], [_ring(a), _ring(b)])
    assert len(polys) == 1 and info["overlap"]
    c = [(0.5, -1.4), (1.9, -1.4), (1.9, 2.0), (0.5, 2.0)]
    polys, info = geom.polygons([], [_ring(a[:1] + [(-0.5, -1.4), (-0.5, 2.0)] + a[3:]), _ring(c)])
    assert len(polys) == 2 and not info["overlap"]


def test_contour_whose_first_point_is_inside_is_a_hole():
    """pcbnew cut the second rectangle out of the first (a notch), not a union."""
    r1 = [(-2.2, -1.4), (1.0, -1.4), (1.0, 2.0), (-2.2, 2.0)]
    r2 = [(0.0, -0.5), (1.9, -0.5), (1.9, 0.5), (0.0, 0.5)]
    polys, info = geom.polygons([], [_ring(r1), _ring(r2)])
    assert len(polys) == 1 and polys[0].area == pytest.approx(3.2 * 3.4 - 1.0 * 1.0)
    assert not info["overlap"]


def test_holes_and_islands_nest_even_odd():
    outer = [(0, 0), (10, 0), (10, 10), (0, 10)]
    hole = [(2, 2), (8, 2), (8, 8), (2, 8)]
    island = [(4, 4), (6, 4), (6, 6), (4, 6)]
    polys, _ = geom.polygons([], [_ring(outer), _ring(hole), _ring(island)])
    assert sorted(round(p.area, 6) for p in polys) == [4.0, 64.0]
    assert any(len(p.interiors) == 1 for p in polys)


def test_slots_closed_by_a_line_drawn_back_over_them():
    """A connector's two board-edge slots: U shapes joined along y=0 by short lines and
    one long line drawn back over the whole span; pcbnew makes two slot holes."""
    opens = [[(-3.75, 0.0), (-2.8, 0.0)], [(-2.8, 0.0), (-2.8, -1.0)], [(-2.8, -1.0), (-1.95, -1.0)],
             [(-1.95, -1.0), (-1.95, 0.0)], [(-1.95, 0.0), (1.95, 0.0)], [(1.95, 0.0), (1.95, -1.0)],
             [(1.95, -1.0), (2.8, -1.0)], [(2.8, -1.0), (2.8, 0.0)], [(2.8, 0.0), (3.75, 0.0)],
             [(3.75, 0.0), (-3.75, 0.0)]]
    polys, info = geom.polygons(opens, [])
    assert info["open_ends"] == 0
    assert sorted(round(p.area, 6) for p in polys) == [0.85, 0.85]
    assert all(p.bounds[3] <= 1e-6 and p.bounds[1] >= -1.0 - 1e-6 for p in polys)


def test_arc_start_snaps_to_the_chain():
    """KiCad redefines an arc through (chain point, mid, end) when it bridges a gap."""
    mid = (1.0 + math.cos(math.radians(45)), -math.sin(math.radians(45)))
    arc = geom.ArcPiece(geom.arc_points((2.0, 0.0), mid, (1.0, -1.0)), mid, geom.ARC_TOL)
    line = [(1.0, -1.0), (1.0, 0.0)]
    close = [(1.0, 0.0), (2.005, 0.0)]          # 5 um short of the arc's start
    polys, info = geom.polygons([close, arc, line], [], eps=0.01)
    ring = list(polys[0].exterior.coords)
    assert (2.005, 0.0) in ring and (2.0, 0.0) not in ring and info["gap"] == pytest.approx(0.005)


def test_arc_points_follow_mid_and_tolerance():
    pts = geom.arc_points((1.0, 0.0), (0.0, 1.0), (-1.0, 0.0), tol=0.001)
    assert pts[0] == (1.0, 0.0) and pts[-1] == (-1.0, 0.0)
    assert all(abs(math.hypot(x, y) - 1.0) < 1e-12 and y >= -1e-12 for x, y in pts)
    sag = max(1 - math.hypot((a[0] + b[0]) / 2, (a[1] + b[1]) / 2) for a, b in zip(pts, pts[1:]))
    assert sag <= 0.001
    c = geom.circle_points((0.0, 0.0), 2.0, tol=0.001)
    assert c[0] == c[-1] and Polygon(c).area == pytest.approx(math.pi * 4, rel=1e-3)
