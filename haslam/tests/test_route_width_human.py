# SPDX-FileCopyrightText: 2026 HaslamPCB contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""haslam.route.width_human: power-net width against the human layout of the same net."""
from __future__ import annotations

import gzip

import pytest

from haslam.route import width_human as W


def _fp(ref, x, y, nets):
    pads = "".join(
        f'(pad "{i + 1}" smd rect (at {dx} 0) (size 0.6 0.6) (layers "F.Cu" "F.Paste" "F.Mask") (net {n} "{name}"))'
        for i, (dx, (n, name)) in enumerate(zip((-0.5, 0.5), nets)))
    return f'(footprint "R_0402" (layer "F.Cu") (at {x} {y}) (property "Reference" "{ref}") {pads})'


def _seg(a, b, w, net):
    return f'(segment (start {a[0]} {a[1]}) (end {b[0]} {b[1]}) (width {w}) (layer "F.Cu") (net {net}))'


NETS = [(1, "VBAT"), (2, "SIG"), (3, "SIG2")]


def board(vbat_w, entry_w=None):
    """R1.1 at (10.5, 10) to R2.1 at (29.5, 10) on VBAT (a 20 mm run, pad centre to pad centre), SIG/SIG2 at 0.2 mm elsewhere.
    `entry_w`: the first 0.5 mm out of each pad drawn at this width (a neck at the pad)."""
    fps = (_fp("R1", 10, 10, [NETS[0], NETS[1]]) + _fp("R2", 30, 10, [NETS[0], NETS[2]])
           + _fp("R3", 10, 20, [NETS[1], NETS[2]]))
    segs = [_seg((10.5, 10), (9.5, 20), 0.2, 2), _seg((30.5, 10), (10.5, 20), 0.2, 3)]
    if entry_w is None:
        segs.append(_seg((9.5, 10), (29.5, 10), vbat_w, 1))
    else:
        segs += [_seg((9.5, 10), (10.0, 10), entry_w, 1), _seg((10.0, 10), (29.0, 10), vbat_w, 1),
                 _seg((29.0, 10), (29.5, 10), entry_w, 1)]
    nets = '(net 0 "")' + "".join(f'(net {n} "{s}")' for n, s in NETS)
    return (f'(kicad_pcb (version 20240108) (generator "pcbnew") (general (thickness 1.6)) '
            f'(layers (0 "F.Cu" signal) (31 "B.Cu" signal) (44 "Edge.Cuts" user)) {nets} {fps} {"".join(segs)})')


@pytest.fixture
def human(tmp_path):
    p = tmp_path / "human.kicad_pcb"
    p.write_text(board(1.0))
    return p


def test_wmedian():
    assert W.wmedian([(0.2, 1.0), (1.0, 3.0)]) == 1.0
    assert W.wmedian([(0.2, 3.0), (1.0, 1.0)]) == 0.2
    assert W.wmedian([]) is None


def test_reference_picks_the_wide_net(human):
    ref, w_sig = W.reference(W._load(human))
    assert w_sig == pytest.approx(0.2)
    assert "VBAT" in ref and ref["VBAT"]["w_h"] == pytest.approx(1.0) and ref["VBAT"]["by_width"]
    assert "SIG" not in ref


def test_human_floor_is_zero(human):
    r = W.human_floor(human, {"branch": False})
    assert r["pooled"]["power"]["share"] == 0.0 and r["pooled"]["power"]["deficit"] == 0.0


def test_narrow_routing_counts(tmp_path, human):
    p = tmp_path / "routed.kicad_pcb.gz"
    p.write_bytes(gzip.compress(board(0.2).encode()))
    r = W.measure(p, human, {"branch": False})
    pw = r["pooled"]["power"]
    assert pw["share"] == pytest.approx(1.0)
    assert pw["share_x"] == pytest.approx(1.0)
    assert pw["deficit"] == pytest.approx(0.8)


def test_neck_at_the_pad_is_exempt_only_in_share_x(tmp_path, human):
    p = tmp_path / "routed.kicad_pcb"
    p.write_text(board(1.0, entry_w=0.2))
    r = W.measure(p, human, {"branch": False})
    pw = r["pooled"]["power"]
    assert pw["share"] == pytest.approx(1.0 / 20.0, rel=1e-3)
    assert pw["share_x"] == pytest.approx(0.0)


def test_tolerance(tmp_path, human):
    p = tmp_path / "routed.kicad_pcb"
    p.write_text(board(0.9))
    assert W.measure(p, human, {"branch": False, "tol": 0.05})["pooled"]["power"]["share"] == pytest.approx(1.0)
    assert W.measure(p, human, {"branch": False, "tol": 0.15})["pooled"]["power"]["share"] == pytest.approx(0.0)


def test_narrow_track_under_a_same_net_pour_counts_as_wide(tmp_path, human):
    zone = ('(zone (net 1) (net_name "VBAT") (layer "F.Cu") (hatch edge 0.5) (connect_pads (clearance 0.2)) '
            '(min_thickness 0.2) (fill (thermal_gap 0.5) (thermal_bridge_width 0.5)) '
            '(polygon (pts (xy 14 9) (xy 24 9) (xy 24 11) (xy 14 11))))')
    p = tmp_path / "routed.kicad_pcb"
    p.write_text(board(0.2)[:-1] + zone + ")")
    pw = W.measure(p, human, {"branch": False})["pooled"]["power"]
    assert pw["share"] == pytest.approx(1.0)            # share and deficit look at tracks only
    beyond = 20.0 - 2 * (1.0 + 0.3)                      # the run beyond 1 mm of either 0.6 mm pad
    assert pw["share_x"] == pytest.approx((beyond - 10.0) / beyond, rel=1e-3)
    assert W.measure(p, human, {"branch": False, "pour": False})["pooled"]["power"]["share_x"] == pytest.approx(1.0)


def test_share_neck_separates_class_width_from_necks(tmp_path, human):
    # the human drew VBAT at 1.0; its class says 0.5: a router at 0.5 is narrow but not necked, at 0.2 it is both
    W_class = {"VBAT": 0.5}
    ref, w_sig = W.reference(W._load(human))
    for n in ref:
        ref[n]["w_class"] = W_class.get(n)
    for w, neck in ((0.5, 0.0), (0.2, 1.0)):
        p = tmp_path / f"routed-{w}.kicad_pcb"
        p.write_text(board(w))
        pw = W.measure(p, human, {"branch": False}, ref=(ref, w_sig))["pooled"]["power"]
        assert pw["share_x"] == pytest.approx(1.0)
        assert pw["share_neck"] == pytest.approx(neck)
