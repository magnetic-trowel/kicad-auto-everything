# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Unit tests for the pnr World's legality model (no KiCad needed).

    pytest tools/research/pnr/test_world.py

Each test builds a small synthetic board and checks the grid model against exact geometry
(shapely): every origin legal_map accepts must be legal in KiCad's terms.
"""
import math
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
shapely = pytest.importorskip("shapely")
from shapely.geometry import Point, Polygon  # noqa: E402

from placekit import Kit  # noqa: E402
from router import Router  # noqa: E402
from world import World  # noqa: E402


def circle(r, n=64, cx=0.0, cy=0.0):
    return [[cx + r * math.cos(2 * math.pi * i / n), cy + r * math.sin(2 * math.pi * i / n)] for i in range(n)]


def rect(x0, y0, x1, y1):
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]


def pad(net, poly, x=0.0, y=0.0, drill=None):
    return dict(num="1", net=net, cu="both" if drill else "F", x=x, y=y, clear=None, poly=[poly],
                drill=[drill, drill] if drill else [0.0, 0.0], pth=bool(drill), npth=False)


def footprint(ref, pads, x=0.0, y=0.0, cu_shapes=()):
    return dict(ref=ref, uuid=ref, x=x, y=y, rot=0.0, back=False, locked=False, anchored=False,
                pads=pads, courtyard=[], courtyard_other=[], edges=[], keepouts=[],
                cu_shapes=list(cu_shapes))


def board(outline, footprints, nets, ec=0.01, clearance=0.2, cu_shapes=(), keepouts=()):
    nc = dict(clearance=clearance, width=0.2, via_d=0.6, via_drill=0.3)
    return dict(layers=2, outline=[outline], outline_holes=[], cu_shapes=list(cu_shapes),
                rules=dict(min_clearance=0.0, min_track=0.2, min_via=0.4, hole_clearance=0.0,
                           edge_clearance=ec, min_drill=0.3, hole_to_hole=0.25, min_annular=0.05,
                           mask_exp=0.0, mask_web=0.0),
                default=nc, nets={n: dict(nc) for n in nets}, footprints=footprints,
                keepouts=list(keepouts), zones=[])


def pad_polys(w, pi, cx, cy):
    """Exact pad copper of part pi with its origin at cell (cx, cy), orientation 0."""
    x, y = w.xy(cx, cy)
    return [Polygon(np.array(q, float) + [x, y]) for p in w.parts[pi].pads for q in p["poly"]]


def legal_origins(w, pi, near):
    """Origins accepted by legal_map whose exact pad copper comes within `near` mm of
    the reference geometry (only those can be wrong)."""
    kit = Kit(w, Router(w))
    L = kit.legal_map(pi, 0)
    return [(int(x), int(y)) for y, x in zip(*np.nonzero(L))], kit


# ------------------------------------------------------------------- board edge (bug 1)
def test_edge_clearance_off_grid_outline():
    """A 5.6 mm round mounting pad near an outline that is off the 0.1 mm grid (edge rule
    0.01 mm): no legal origin may put pad copper closer than 0.01 mm to the edge. The old
    check sampled only cells whose centre is inside the pad, so the pad could overhang
    the edge by up to a cell (kicad-demos-ecc83-ecc83-pp-v2: 5 um across the edge)."""
    outline = rect(120.015, 90.805, 168.275, 132.715)  # the ecc83 board's outline
    fp = footprint("P5", [pad("", circle(2.8), drill=3.2)])
    w = World(board(outline, [fp], [], ec=0.01))
    out = Polygon(outline)
    org, _ = legal_origins(w, 0, 0)
    assert org
    worst = math.inf
    for cx, cy in org:
        for p in pad_polys(w, 0, cx, cy):
            d = out.exterior.distance(p) if out.contains(p) else -1.0
            worst = min(worst, d)
    assert worst >= 0.01 - 1e-9, worst
    # the pose that failed DRC before (pad top 5 um above the top edge) is now illegal
    cx, cy = w.cell(165.4, 93.6)
    w.place(0, cx, cy, 0)
    assert w.part_violation(0)[1] > 0


def test_edge_clearance_many_offsets():
    """Square and round pads against outlines at several sub-cell offsets."""
    for off in (0.0, 0.003, 0.0049, 0.051, 0.0751, 0.099):
        outline = rect(off, off, 20 + off, 15 + off)
        for poly in (circle(1.0), rect(-0.6, -0.4, 0.6, 0.4)):
            fp = footprint("U", [pad("", poly)])
            w = World(board(outline, [fp], [], ec=0.05))
            out = Polygon(outline)
            org, _ = legal_origins(w, 0, 0)
            for cx, cy in org:
                p = pad_polys(w, 0, cx, cy)[0]
                assert out.contains(p) and out.exterior.distance(p) >= 0.05 - 1e-9, (off, cx, cy)


# ------------------------------------------------------------------- copper drawings (bug 2)
def arc_strip(cx, cy, r, a0, a1, width, n=40):
    """A stroked arc as a polygon (what TransformShapeToPolygon gives for a gr_arc)."""
    a = np.linspace(a0, a1, n)
    outer = np.stack([cx + (r + width / 2) * np.cos(a), cy + (r + width / 2) * np.sin(a)], 1)
    inner = np.stack([cx + (r - width / 2) * np.cos(a), cy + (r - width / 2) * np.sin(a)], 1)
    return np.concatenate([outer, inner[::-1]]).tolist()


def test_copper_drawing_blocks_foreign_pads_and_wires():
    """A 1 mm copper arc with net A on F.Cu (pcbcorpus-justbuchanan-oasis-ledboard): pads
    of any part keep the copper clearance from it, wires of other nets avoid it, and
    wires of net A may connect to it."""
    arc = arc_strip(20, 20, 12, 0.2, 1.4, 1.0)
    shapes = [dict(net="A", layer=0, poly=[arc], holes=[[]])]
    fps = [footprint("D1", [pad("B", rect(-0.5, -0.4, 0.5, 0.4))]),
           footprint("D2", [pad("A", rect(-0.5, -0.4, 0.5, 0.4))]),
           footprint("D3", [pad("A", rect(-0.5, -0.4, 0.5, 0.4))]),
           footprint("D4", [pad("B", rect(-0.5, -0.4, 0.5, 0.4))])]
    w = World(board(rect(0, 0, 40, 40), fps, ["A", "B"], clearance=0.2, cu_shapes=shapes))
    A = Polygon(arc)
    org, kit = legal_origins(w, 0, 0)
    assert org
    for cx, cy in org:
        p = pad_polys(w, 0, cx, cy)[0]
        assert A.distance(p) >= 0.2 - 1e-9, (cx, cy, A.distance(p))
    # the arc's own cells are illegal for every pad (net-agnostic keep-out)
    x, y = 20 + 12 * math.cos(0.8), 20 + 12 * math.sin(0.8)
    assert not kit.legal_map(1, 0)[w.cell(x, y)[::-1]]
    # net A routes to its arc: D2 and D3 far from it, both connected, and the arc too
    r = Router(w)
    w.place(1, *w.cell(5, 5), 0)
    w.place(2, *w.cell(8, 5), 0)
    w.place(0, *w.cell(22, 22), 0)  # inside the arc's circle
    w.place(3, *w.cell(38, 38), 0)  # outside it: B's wire must pass the arc
    r.pathfinder(iters=10)
    st = r.stats()
    assert st["unrouted"] == 0 and st["connections"] == 3, st
    a_id, b_id = w.net_id["A"], w.net_id["B"]
    ends = [tuple(p[-1]) for p in r.routes[a_id]] + [tuple(p[0]) for p in r.routes[a_id]]
    arc_cells = {tuple(c) for c in w.shape_terms[a_id][0]}
    assert any(e in arc_cells for e in ends)
    # net B's wire (from inside the arc's circle to outside) keeps clear of the arc copper
    for path in r.routes[b_id]:
        for l, cy, cx in path:
            if l == 0:
                x, y = w.xy(cx, cy)
                assert A.distance(Point(x, y)) >= 0.2 + 0.1 - 1e-9


def test_unfilled_ring_is_not_a_disc():
    """An unfilled copper circle is a ring: parts may sit inside it."""
    ring = [circle(15.05, 128, 20, 20)]
    hole = [[circle(14.95, 128, 20, 20)]]
    shapes = [dict(net="", layer=0, poly=ring, holes=hole)]
    fps = [footprint("U1", [pad("B", rect(-0.5, -0.4, 0.5, 0.4))])]
    w = World(board(rect(0, 0, 40, 40), fps, ["B"], cu_shapes=shapes))
    kit = Kit(w, Router(w))
    L = kit.legal_map(0, 0)
    assert L[w.cell(20, 20)[::-1]]  # centre of the ring
    assert not L[w.cell(35, 20)[::-1]]  # on the ring
    assert w.DT[0][w.cell(20, 20)[::-1]] == 0


def test_footprint_copper_drawing_is_part_copper():
    """A footprint's own copper rectangle (no net) moves with the part and is an obstacle
    for other nets' wires (pcbcorpus-badjeff-paw3222-pcb-paw3222, LED D1)."""
    fps = [footprint("D1", [pad("B", rect(-0.5, -0.4, 0.5, 0.4))],
                     cu_shapes=[dict(net="", layer=0, poly=[rect(1.0, -0.75, 2.0, 0.3)], holes=[[]])])]
    w = World(board(rect(0, 0, 20, 20), fps, ["B"]))
    cx, cy = w.cell(10, 10)
    w.place(0, cx, cy, 0)
    c = w.cell(11.5, 9.8)
    assert w.occT[0, 0, c[1], c[0]] > 0  # net-0 halo over the rectangle
    assert w.DT[0, c[1], c[0]] >= 1
    w.unplace(0)
    assert w.DT.sum() == 0 and w.court.sum() == 0


# ------------------------------------------------------------------- v7 baseline fixes
def test_footprint_keepout_moves_with_part():
    """A no-track rule area drawn inside a footprint is an obstacle of no net wherever the
    part goes (pcbcorpus-tcsullivan-noisecard: items_not_allowed in B1's keep-out)."""
    ko = dict(layers=[0], tracks=True, vias=True, pads=False, footprints=False, poly=[rect(1.0, -1.0, 3.0, 1.0)])
    fp = footprint("B1", [pad("B", rect(-0.5, -0.4, 0.5, 0.4))])
    fp["keepouts"] = [ko]
    w = World(board(rect(0, 0, 20, 20), [fp], ["B"]))
    for x0 in (5.0, 12.0):
        cx, cy = w.cell(x0, 10)
        w.place(0, cx, cy, 0)
        c = w.cell(x0 + 2.0, 10)
        assert w.occT[0, 0, c[1], c[0]] > 0 and w.occV[0, 0, c[1], c[0]] > 0
        w.unplace(0)
    assert w.DT.sum() == 0


def test_edge_cuts_footprint_is_anchored():
    """Task spec 5+ keeps footprints carrying Edge.Cuts in place (lambdakb-lt6c U3)."""
    fp = footprint("U3", [pad("B", rect(-0.5, -0.4, 0.5, 0.4))])
    fp["anchored"] = True
    w = World(board(rect(0, 0, 20, 20), [fp], ["B"]))
    assert w.parts[0].locked
    assert 0 not in Kit(w, Router(w)).movable()


def test_custom_pad_terminals_at_anchor():
    """A ring-shaped custom pad: wires may end only on its anchor disc, since KiCad's
    connectivity misses track ends well inside the ring (funkeleinhorn MK1)."""
    ring = circle(1.75, 64, 0, 1.375)
    p = pad("A", ring)
    p["poly_in"] = [ring]
    p.update(custom=True, anchor_r=0.375)
    w = World(board(rect(0, 0, 20, 20), [footprint("MK1", [p])], ["A"]))
    w.place(0, *w.cell(10, 10), 0)
    t = np.array(w.terminals(0, 0))
    x, y = w.xy(t[:, 2], t[:, 1])
    assert len(t) and np.all(np.hypot(x - 10, y - 10) <= 0.375)


def test_jumper_bridge_is_not_an_obstacle():
    """A footprint copper drawing that bridges two of its own pads (a closed solder jumper,
    espprog JP2) is left out: no no-net halo over the pads it touches."""
    pa = pad("A", rect(-1.0, -0.5, -0.2, 0.5))
    pb = pad("B", rect(0.2, -0.5, 1.0, 0.5))
    pb["num"] = "2"
    fp = footprint("JP2", [pa, pb], cu_shapes=[dict(net="", layer=0, poly=[rect(-0.3, -0.2, 0.3, 0.2)], holes=[[]])])
    w = World(board(rect(0, 0, 20, 20), [fp], ["A", "B"]))
    w.place(0, *w.cell(10, 10), 0)
    assert w.occT[0].sum() == 0
