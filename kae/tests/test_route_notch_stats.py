# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""tools/research/routing/notch_stats.py: acute notches in the outline of merged copper."""
import importlib.util
import math
from pathlib import Path

from shapely.geometry import LineString, box
from shapely.geometry.polygon import orient
from shapely.ops import unary_union

spec = importlib.util.spec_from_file_location(
    "notch_stats", Path(__file__).resolve().parents[2] / "tools" / "research" / "routing" / "notch_stats.py")
N = importlib.util.module_from_spec(spec)
spec.loader.exec_module(N)


def _notches(*geoms):
    u = orient(unary_union(list(geoms)), 1.0)
    return [x for r in [u.exterior, *u.interiors] for x in N.ring_notches(r.coords) if x[3] >= 0.05]


def _t(a, b, w=0.25):
    return LineString([a, b]).buffer(w / 2, quad_segs=16)


def _ray(deg, L=5.0):
    return (L * math.cos(math.radians(deg)), L * math.sin(math.radians(deg)))


def test_a_30_degree_branch_is_one_deep_notch():
    got = _notches(_t((0, 0), _ray(0)), _t((0, 0), _ray(30)), _t((-5, 0), (0, 0)))
    assert len(got) == 1
    assert 25 < got[0][2] < 35 and got[0][3] > 0.2


def test_square_corner_and_t_join_and_obtuse_bend_are_not():
    assert _notches(_t((0, 0), (5, 0)), _t((0, 0), (0, 5))) == []                     # L
    assert _notches(_t((-5, 0), (5, 0)), _t((0, 0), (0, 5))) == []                    # T
    assert _notches(_t((0, 0), _ray(0)), _t((0, 0), _ray(135))) == []                 # 45 degree bend


def test_a_track_inside_wider_copper_makes_no_notch():
    assert _notches(_t((0, 0), (5, 0), 2.0), _t((1, 0), (4, 0.3), 0.25)) == []


def test_an_oblique_entry_into_a_pad_is_a_notch_and_a_square_one_is_not():
    pad = box(-0.5, -0.5, 0.5, 0.5)
    assert len(_notches(pad, _t((0, 0), (5, 1.5)))) == 1                               # 17 degrees off the edge
    assert _notches(pad, _t((0, 0), (5, 0))) == []


def test_a_very_shallow_notch_is_below_the_depth():
    # a round end poking just past a wide track's side: the wedge closes within microns
    assert _notches(_t((0, 0), (5, 0), 1.0), _t((2, 0), (2, 0.52), 0.1)) == []
