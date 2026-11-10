# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""kae.place.barriers: true region splits from the outline and all-layer keepouts, part assignment by nets."""
import dataclasses
from types import SimpleNamespace as NS

from shapely.geometry import Polygon, box

from kae.place import barriers as B


def pad(x, y, net=""):
    return NS(x=x, y=y, net=net, drill=0.0, kind="smd")


def fp(ref, x, y, pads, locked=False):
    return NS(ref=ref, uuid=ref, x=x, y=y, pads=pads, locked=locked, edge_cuts=[], courtyard=[], body=[], side="F")


def board(outline, fps, keepouts=(), cu=("F.Cu", "B.Cu")):
    return NS(outline=list(outline), footprints=fps, keepouts=list(keepouts), layers={c: "signal" for c in cu})


def ko(poly, layers=("F.Cu", "B.Cu"), tracks=True, footprint=""):
    return NS(outline=poly, layers=list(layers), tracks=tracks, footprint=footprint)


def test_one_outline_no_wall_is_no_split():
    assert B.true_split(board([box(0, 0, 50, 50)], [fp("A", 5, 5, [pad(5, 5, "n")])])) is None


def test_two_outlines_split_and_label_by_anchors_and_nets():
    fps = [fp("J1", 10, 10, [pad(10, 10, "a")], locked=True), fp("R1", 200, 200, [pad(200, 200, "a"), pad(200, 201, "b")]),
           fp("R2", 201, 201, [pad(201, 201, "b")]),
           fp("J2", 110, 10, [pad(110, 10, "c")], locked=True), fp("R3", 300, 300, [pad(300, 300, "c")])]
    s = B.true_split(board([box(0, 0, 50, 50), box(100, 0, 150, 50)], fps))
    assert len(s.regions) == 2
    a, b = s.region_of["J1"], s.region_of["J2"]
    assert a != b and s.region_of["R1"] == a and s.region_of["R2"] == a and s.region_of["R3"] == b
    assert not s.cross_nets and s.how["anchored"] == 2


def test_keepout_wall_splits_only_when_every_layer_is_forbidden():
    wall = box(45, -5, 55, 55)
    fps = [fp("J1", 10, 10, [pad(10, 10, "a")], locked=True), fp("J2", 90, 10, [pad(90, 10, "b")], locked=True)]
    assert len(B.true_split(board([box(0, 0, 100, 50)], fps, [ko(wall)])).regions) == 2
    # F.Cu only leaves the bottom layer to cross on
    assert B.true_split(board([box(0, 0, 100, 50)], fps, [ko(wall, layers=("F.Cu",))])) is None
    # a footprint's own keepout moves with it: not a board wall
    assert B.true_split(board([box(0, 0, 100, 50)], fps, [ko(wall, footprint="u1")])) is None
    # a rule area that does not forbid tracks is no wall
    assert B.true_split(board([box(0, 0, 100, 50)], fps, [ko(wall, tracks=False)])) is None


def test_slivers_are_not_regions():
    # a thin strip left by an edge keepout is under the 2 % share
    wall = box(0, 0.5, 100, 2)
    regs = B.regions(board([box(0, 0, 100, 50)], [], [ko(wall)]))
    assert len(regs) == 1 and abs(regs[0].area - 4800) < 1e-6


def test_cross_nets_are_reported():
    fps = [fp("J1", 10, 10, [pad(10, 10, "x")], locked=True), fp("J2", 110, 10, [pad(110, 10, "x")], locked=True)]
    s = B.true_split(board([box(0, 0, 50, 50), box(100, 0, 150, 50)], fps))
    assert s.cross_nets == ["x"]


def test_unanchored_groups_go_where_there_is_room():
    # no anchors: the two components (a, b) go to different regions: the big group to the big region
    fps = [fp("A", 200, 200, [pad(200, 200, "a"), pad(200, 202, "a2")]), fp("B", 201, 201, [pad(201, 201, "a2")])]
    s = B.true_split(board([box(0, 0, 50, 50), box(100, 0, 110, 10)], fps))
    assert s.region_of["A"] == s.region_of["B"] == 0 and s.how["by_area"] == 2


def test_mst_edges_connect_all_points():
    pts = [(0, 0), (1, 0), (5, 0), (5, 1)]
    e = B._mst_edges(pts)
    assert len(e) == 3 and {tuple(sorted(x)) for x in e} == {(0, 1), (1, 2), (2, 3)}


def test_barriers_include_outline_holes():
    outer = Polygon([(0, 0), (20, 0), (20, 20), (0, 20)], holes=[[(5, 5), (15, 5), (15, 15), (5, 15)]])
    assert abs(sum(p.area for p in B.all_barriers(board([outer], []))) - 100.0) < 1e-6


def test_padless_parts_get_a_region_and_free_anchors_go_everywhere():
    fps = [fp("J1", 10, 10, [pad(10, 10, "a")], locked=True), fp("J2", 110, 10, [pad(110, 10, "b")], locked=True),
           fp("LOGO", 300, 300, []), fp("MB1", 75, 10, [pad(75, 10), pad(76, 10)], locked=True)]
    s = B.true_split(board([box(0, 0, 50, 50), box(100, 0, 150, 50)], fps))
    assert s.region_of["LOGO"] in (0, 1)
    assert s.region_of["MB1"] == -1
    @dataclasses.dataclass
    class Bd:
        footprints: list
        outline: list
    assert all(any(f.ref == "MB1" for f in B.sub_board(Bd(fps, []), s, r).footprints) for r in (0, 1))


def test_a_region_that_cannot_hold_its_parts_is_reported():
    big = [fp(f"U{i}", 300, 300, [pad(300, 300, "n")]) for i in range(3)]
    for f in big:
        f.courtyard = [box(0, 0, 30, 30)]
    s = B.true_split(board([box(0, 0, 10, 10), box(100, 0, 110, 10)], big))
    assert s.over_capacity


def test_full_region_gives_up_its_loosest_part():
    # small region 10 x 10 (capacity 85 a side) anchored by J1; two 50 mm2 parts drawn to it, A also tied to J2: A moves
    a = fp("A", 300, 300, [pad(300, 300, "x"), pad(300, 301, "x2"), pad(300, 302, "y")])
    b = fp("B", 300, 300, [pad(300, 300, "x")])
    for f in (a, b):
        f.courtyard = [box(0, 0, 5, 10)]
    fps = [fp("J1", 5, 5, [pad(5, 5, "x"), pad(5, 6, "x2")], locked=True), fp("J2", 120, 20, [pad(120, 20, "y")], locked=True), a, b]
    s = B.true_split(board([box(0, 0, 10, 10), box(100, 0, 150, 50)], fps))
    assert not s.over_capacity and s.how["moved_for_room"] == 1
    assert s.region_of["A"] == s.region_of["J2"] and s.region_of["B"] == s.region_of["J1"]
