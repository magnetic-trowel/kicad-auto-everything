# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""kae.place.buspose: pin tables, planarity, bus detection, the joint rotation choice."""
from types import SimpleNamespace as NS

import numpy as np

from kae.place import buspose as BP


def rot_of(pins):
    return NS(pins=np.array(pins, float), rot=0.0)


def parts_two_rows():
    # A: a 1x8 row of pads along x. B: the same row, rotation 2 reverses the pad order.
    # each part also has a pad behind the row, so the pad centre lies off the row, as on a real footprint
    row = [[float(k), 0.0] for k in range(8)] + [[3.5, -4.0]]
    half_turn = [[7.0 - x, 0.0 - y] for x, y in row]
    a = NS(i=0, ref='A', rots=[rot_of(row)], movable=False, pad_net=np.arange(9))
    b = NS(i=1, ref='B', rots=[rot_of(row), rot_of(half_turn)], movable=True, pad_net=np.arange(9), n_ortho=2)
    return a, b


def test_planarity_of_a_ribbon_and_a_reversed_ribbon():
    # two rows of pads facing each other in x: same x order at both ends: straight lines
    pa = np.array([[float(k), 0.0] for k in range(8)])
    pb = np.array([[float(k), 20.0] for k in range(8)])
    lis, lds, inv = BP.planarity(pa, pb, np.array([3.5, -2.0]), np.array([3.5, 22.0]))
    assert lis == 1.0 and lds == 1 and inv == 0.0
    # the far end reversed: every pair crosses; lines are planar only with vias, 8 layers needed (LIS 1 of 8)
    rev = pb[::-1]
    lis, lds, inv = BP.planarity(pa, rev, np.array([3.5, -2.0]), np.array([3.5, 22.0]))
    assert inv == 1.0
    assert lds == 8 and lis == 1 / 8


def test_table_and_compile_choose_the_rotation_that_uncrosses():
    a, b = parts_two_rows()
    g = 0.1
    P = NS(parts=[a, b], g=g, ox=0.0, oy=0.0)
    st = NS(K=np.array([0, 1]), xy=lambda i: {0: (0.0, 0.0), 1: (0.0, 20.0)}[i])
    bus = BP.Bus(a=0, b=1, pa=np.arange(8), pb=np.arange(8), nets=[(i,) for i in range(8)], series=[[] for _ in range(8)])
    lis0, lds0, _ = BP.table(P, st, bus, 0, 1)
    assert lds0 == 8
    lis1, lds1, _ = BP.table(P, st, bus, 0, 0)
    assert lis1 == 1.0
    domains = {1: [1, 0]}
    res = BP.compile_poses(P, st, [bus], domains, lambda i, k: 0.0, mode="planar")
    assert res == {1: 0}


def test_detect_needs_min_lines():
    nets = [NS(i=i, kind="signal", pins=[(0, i), (1, i)]) for i in range(5)]
    parts = [NS(i=0, ref='U1', pad_net=np.arange(5).tolist() + [-1], rots=[], movable=True),
             NS(i=1, ref='U2', pad_net=np.arange(5).tolist() + [-1], rots=[], movable=True)]
    P = NS(parts=parts, nets=nets)
    assert BP.detect(P, min_lines=6) == []
    nets += [NS(i=5, kind="signal", pins=[(0, 5), (1, 5)])]
    P.nets = nets
    parts[0].pad_net = np.arange(6).tolist()
    parts[1].pad_net = np.arange(6).tolist()
    assert [(b.a, b.b, b.n) for b in BP.detect(P, min_lines=6)] == [(0, 1, 6)]
