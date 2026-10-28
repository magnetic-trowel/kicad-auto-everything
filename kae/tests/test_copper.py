# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""kae.route.copper.NetGraph: connected as KiCad connects copper (shapes colliding on a shared layer)."""
import math
import uuid

import pytest
from shapely.geometry import box

from critical_fixtures import write_board
from kae.board.kicad_file import load
from kae.board.model import Track, Via
from kae.circuit.brief import build
from kae.route.copper import arc_points
from kae.route.critical_recheck import RoutedBoard

NET = "Net-(U2-XTAL1)"          # a fixture net with pads Y1.1, C4.1 and U2.2


def _rb(tmp_path, tracks=(), vias=(), fills=None):
    b = load(write_board(tmp_path))
    for net, layer, w, a, c, *mid in tracks:
        b.tracks.append(Track(uuid=str(uuid.uuid4()), net=net, layer=layer, width=w, start=a, end=c,
                              mid=mid[0] if mid else None))
    for net, x, y, size in vias:
        b.vias.append(Via(uuid=str(uuid.uuid4()), net=net, x=x, y=y, size=size, drill=size / 2,
                          layers=["F.Cu", "B.Cu"]))
    return RoutedBoard(b, fills=fills, brief=build(b))


def _pieces(g):
    """Connected pieces that contain a track keypoint (pads alone are their own piece)."""
    return [c for c in g.components() if any(g.nodes[k][0] == "kp" for k in c)]


def _joined(g, a, b):
    return any({a, b} <= {(g.nodes[k][2], g.nodes[k][3]) for k in c} or
               (any(math.dist((g.nodes[k][2], g.nodes[k][3]), a) < 1e-6 for k in c) and
                any(math.dist((g.nodes[k][2], g.nodes[k][3]), b) < 1e-6 for k in c)) for c in g.components())


@pytest.mark.parametrize("gap,joined", [(0.0, True), (0.0005, True), (0.199, True), (0.201, False)])
def test_offset_ends_touch_within_the_half_widths(tmp_path, gap, joined):
    a, m, c = (105.0, 105.0), (110.0, 105.0), (115.0, 105.0)
    rb = _rb(tmp_path, [(NET, "F.Cu", 0.2, a, m), (NET, "F.Cu", 0.2, (m[0] + gap, m[1]), c)])
    assert _joined(rb.graph(NET), a, c) is joined


def test_offset_overlap_edge_spans_the_real_gap(tmp_path):
    a, m, c = (105.0, 105.0), (110.0, 105.0), (115.0, 105.0)
    rb = _rb(tmp_path, [(NET, "F.Cu", 0.2, a, m), (NET, "F.Cu", 0.2, (m[0], m[1] + 0.1), (c[0], c[1] + 0.1))])
    g = rb.graph(NET)
    ka = next(k for k, n in enumerate(g.nodes) if n[0] == "kp" and math.dist(n[2:4], a) < 1e-9)
    kc = next(k for k, n in enumerate(g.nodes) if n[0] == "kp" and math.dist(n[2:4], (c[0], c[1] + 0.1)) < 1e-9)
    ln = sum(math.dist(p[2], p[3]) for p, _, _ in g.path([ka], [kc]))
    assert ln == pytest.approx(10.0 + 0.1, abs=1e-6)


def test_t_junction_splits_the_track(tmp_path):
    rb = _rb(tmp_path, [(NET, "F.Cu", 0.25, (105.0, 105.0), (115.0, 105.0)),
                        (NET, "F.Cu", 0.25, (110.0, 108.0), (110.0, 105.05))])     # ends inside the first track
    g = rb.graph(NET)
    assert len(_pieces(g)) == 1
    k = next(k for k, n in enumerate(g.nodes) if n[0] == "kp" and math.dist(n[2:4], (110.0, 105.0)) < 1e-6)
    assert len(g.adj[k]) == 3                                                       # left, right, and the stub


def test_crossing_tracks_connect_where_they_cross(tmp_path):
    rb = _rb(tmp_path, [(NET, "F.Cu", 0.2, (105.0, 105.0), (115.0, 105.0)),
                        (NET, "F.Cu", 0.2, (110.0, 100.0), (110.0, 110.0))])
    g = rb.graph(NET)
    assert len(_pieces(g)) == 1
    assert any(n[0] == "kp" and math.dist(n[2:4], (110.0, 105.0)) < 1e-6 for n in g.nodes)


def test_different_layers_do_not_touch(tmp_path):
    rb = _rb(tmp_path, [(NET, "F.Cu", 0.2, (105.0, 105.0), (115.0, 105.0)),
                        (NET, "B.Cu", 0.2, (110.0, 100.0), (110.0, 110.0))])
    assert len(_pieces(rb.graph(NET))) == 2


def test_track_end_overlapping_a_narrow_pad(tmp_path):
    rb = _rb(tmp_path)
    fp = next(f for f in rb.board.footprints if f.ref == "C4")
    pad = next(p for p in fp.pads if p.net == NET)
    from kae.board import transform
    px, py = transform.pad_xy(fp, pad)
    half = min(pad.size) / 2
    # end just outside the pad's short side, but within the track's half width of it
    end = (px, py - (pad.size[1] / 2 + 0.1))
    rb = _rb(tmp_path / "b", [(NET, "F.Cu", 0.4, (px, py - 5.0), end)])
    g = rb.graph(NET)
    k_pad = g.pad_node[(fp.uuid, pad.number)][0]
    assert any(k_pad in c and any(g.nodes[k][0] == "kp" for k in c) for c in g.components()), half


def test_arc_is_chorded_and_connects(tmp_path):
    pts = arc_points((105.0, 105.0), (107.0, 105.0), (109.0, 105.0))
    assert pts == [(105.0, 105.0), (109.0, 105.0)]                                 # collinear: a straight piece
    s, e = (105.0, 105.0), (107.0, 107.0)
    mid = (105.0 + 2 * math.sin(math.pi / 4), 107.0 - 2 * math.cos(math.pi / 4))   # quarter circle about (105, 107)
    q = arc_points(s, mid, e)
    assert len(q) >= 5 and all(abs(math.dist(p, (105.0, 107.0)) - 2.0) < 1e-9 for p in q)
    rb = _rb(tmp_path, [(NET, "F.Cu", 0.2, s, e, mid), (NET, "F.Cu", 0.2, e, (112.0, 107.0))])
    assert len(_pieces(rb.graph(NET))) == 1


def test_via_touched_off_centre(tmp_path):
    rb = _rb(tmp_path, [(NET, "F.Cu", 0.2, (105.0, 105.0), (109.6, 105.0)),
                        (NET, "B.Cu", 0.2, (110.4, 105.0), (115.0, 105.0))],
             vias=[(NET, 110.0, 105.0, 0.6)])                                       # ends 0.4 mm off the via centre
    assert len(_pieces(rb.graph(NET))) == 1


def test_track_entering_a_pour(tmp_path):
    pour = box(110.0, 100.0, 120.0, 110.0)
    rb = _rb(tmp_path, [(NET, "F.Cu", 0.2, (100.0, 105.0), (112.0, 105.0)),        # crosses into the pour
                        (NET, "F.Cu", 0.2, (115.0, 108.0), (125.0, 108.0))],
             fills={NET: {"F.Cu": [pour]}})
    assert len(_pieces(rb.graph(NET))) == 1


def test_jumper_pad_groups_are_read_and_bond_pads(tmp_path):
    p = write_board(tmp_path)
    text = p.read_text()
    head = '(footprint "Package_TO_SOT_SMD:TSOT-23-6"'
    assert head in text
    p.write_text(text.replace(head, head + '\n\t\t(jumper_pad_groups ("2" "3"))', 1))
    b = load(p)
    u1 = next(f for f in b.footprints if f.ref == "U1")
    assert u1.jumpers == [["2", "3"]]
    g = RoutedBoard(b, fills=None, brief=build(b)).graph("VIN")
    k2, k3 = g.pad_node[(u1.uuid, "2")][0], g.pad_node[(u1.uuid, "3")][0]
    assert any({k2, k3} <= c for c in g.components())
    u1.jumpers = []
    g = RoutedBoard(b, fills=None, brief=build(b)).graph("VIN")
    assert not any({k2, k3} <= c for c in g.components())


@pytest.mark.parametrize("with_net,joined", [(True, True), (False, False)])
def test_board_copper_shape_with_a_net_conducts(tmp_path, with_net, joined):
    p = write_board(tmp_path)
    text = p.read_text().rstrip()
    assert text.endswith(")")
    net = f'\n\t\t(net "{NET}")' if with_net else ""
    rect = ('\n\t(gr_rect\n\t\t(start 112 119.5)\n\t\t(end 122 122)\n\t\t(stroke\n\t\t\t(width 0)\n\t\t\t(type default)\n\t\t)'
            f'\n\t\t(fill yes)\n\t\t(layer "F.Cu"){net}\n\t\t(uuid "{uuid.uuid4()}")\n\t)\n')
    p.write_text(text[:-1] + rect + ")\n")
    b = load(p)
    assert (NET in b.copper) is with_net
    g = RoutedBoard(b, fills=None, brief=build(b)).graph(NET)
    c4 = next(f for f in b.footprints if f.ref == "C4")
    u2 = next(f for f in b.footprints if f.ref == "U2")
    k1 = g.pad_node[(c4.uuid, next(q.number for q in c4.pads if q.net == NET))][0]
    k2 = g.pad_node[(u2.uuid, "2")][0]
    assert any({k1, k2} <= c for c in g.components()) is joined


def test_a_pour_is_one_conductor_even_with_distant_contact_clusters(tmp_path):
    pour = box(100.0, 100.0, 140.0, 104.0)
    left = [(NET, "F.Cu", 0.2, (101.0 + 0.3 * i, 106.0), (101.0 + 0.3 * i, 102.0)) for i in range(9)]
    right = [(NET, "F.Cu", 0.2, (136.0 + 0.3 * i, 106.0), (136.0 + 0.3 * i, 102.0)) for i in range(9)]
    rb = _rb(tmp_path, left + right, fills={NET: {"F.Cu": [pour]}})
    assert len(_pieces(rb.graph(NET))) == 1
