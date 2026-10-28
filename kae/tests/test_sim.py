# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""kae.sim: names, the testbench format, copper extraction and an end-to-end DC check."""
import math
import os
import re
import shutil
import uuid

import pytest

from critical_fixtures import write_board
from kae.board.kicad_file import load
from kae.board.model import Track
from kae.circuit.brief import build
from kae.physics.kernels import lprime_hj
from kae.route.critical_physics import r_track
from kae.route.critical_recheck import RoutedBoard
from kae.sim import design as D
from kae.sim import testbench as TB
from kae.sim.extract import GROUND, R_MIN, extract
from kae.sim.names import Namer


# ----------------------------------------------------------------------------- names and numbers
def test_names_are_safe_and_distinct():
    nm = Namer()
    a, b = nm.node("net:CLK"), nm.node("net:clk")
    assert a != b and a.lower() != b.lower()
    for key in ("pin:U1.3", "net:/rp2354b/RUN", "net:+3V3", "net:Net-(R1-Pad2)"):
        n = nm.node(key)
        assert "." not in n and n == n.lower() and all(ch.isalnum() or ch == "_" for ch in n)
        assert nm.back[n] == key
    assert nm.node("0") == "0"


@pytest.mark.parametrize("text,value", [("2.2u", 2.2e-6), ("1meg", 1e6), ("1M", 1e-3), ("300n", 300e-9),
                                        ("3.3", 3.3), ("10k", 1e4), ("5p", 5e-12)])
def test_spice_numbers(text, value):
    assert TB.num(text) == pytest.approx(value)


# ----------------------------------------------------------------------------- testbench format
TB_TEXT = """*@kae-testbench 1
*@test rail_dc:+3V3 kind=rail_dc
*@nets +3V3 GND
*@extract power
*@note the designer's note, with an apostrophe
*@range SCALE 0.2 2 src=prior:"load x0.2 to x2"
.param SCALE=1
Vsrc <C3.1> <C3.2> DC 3.3
Iload <U2.8> <U2.4> DC {0.05*SCALE}
.tran 10n 1u
.meas tran v8 MIN v(<U2.8>) from=0.5u to=1u
*@require v8 >= 3.201 src=datasheet:"U2 VCC min"
*@end
"""


def test_testbench_round_trip():
    t1 = TB.parse(TB_TEXT)
    t2 = TB.parse(TB.render(t1))
    assert len(t1) == len(t2) == 1
    a, b = t1[0], t2[0]
    assert (a.id, a.kind, a.nets, a.extract, a.lines, a.notes) == (b.id, b.kind, b.nets, b.extract, b.lines, b.notes)
    assert a.params["SCALE"] == b.params["SCALE"] and a.params["SCALE"].typ == 1.0
    assert a.requires == b.requires and a.requires[0].src.startswith("datasheet:")


@pytest.mark.parametrize("bad,msg", [
    (TB_TEXT.replace(">= 3.201", "=> 3.201"), "bad operator"),
    (TB_TEXT.replace(".param SCALE=1\n", ""), "without a .param"),
    (TB_TEXT.replace("*@require v8", "*@require v9"), "unknown .meas"),
    (TB_TEXT.replace("src=prior:", "src=guess:"), "unknown source kind"),
    (TB_TEXT.replace("*@end\n", ""), "no *@end"),
    (TB_TEXT.replace(".param SCALE=1", ".param SCALE=5"), "outside"),
])
def test_testbench_errors(bad, msg):
    with pytest.raises(ValueError, match=re.escape(msg)):
        TB.parse(bad)


# ----------------------------------------------------------------------------- extraction
def _board(tmp_path, tracks):
    b = load(write_board(tmp_path))
    for net, layer, w, pts in tracks:
        for a, c in zip(pts[:-1], pts[1:]):
            b.tracks.append(Track(uuid=str(uuid.uuid4()), net=net, layer=layer, width=w, start=a, end=c))
    br = build(b)
    return b, br, RoutedBoard(b, fills=None, brief=br)


# C3 pad 1 (+3V3) at (128.52, 119.0); U2 pad 8 (+3V3) at (126.475, 120.095)
PATH = [(128.52, 119.0), (126.475, 119.0), (126.475, 120.095)]


def test_extract_line_matches_closed_forms(tmp_path):
    b, br, rb = _board(tmp_path, [("+3V3", "F.Cu", 0.25, PATH)])
    net = extract(rb, ["+3V3"], coupling=False)
    assert any({"pin:C3.1", "pin:U2.8"} <= set(g) for g in net.groups["+3V3"])
    ln = math.dist(PATH[0], PATH[1]) + math.dist(PATH[1], PATH[2])
    h = rb.strip_h("F.Cu", PATH[0], PATH[1])
    L = sum(e.value for e in net.elements if e.kind == "L")
    assert L == pytest.approx(lprime_hj(0.25, h) * ln * 1e-9, rel=0.01)
    R = sum(e.value for e in net.elements if e.kind == "R" and e.value > R_MIN * 1.0001)
    assert R == pytest.approx(r_track(ln, 0.25, rb.board.stackup.cu_thickness[0]), rel=0.02)
    C = sum(e.value for e in net.elements if e.kind == "C")
    assert C > 0 and all(e.b == GROUND for e in net.elements if e.kind == "C")


def test_short_pieces_keep_their_resistance(tmp_path):
    stub = [(126.475, 120.095), (126.475, 120.3)]        # 0.2 mm stub off the U2 pad
    b, br, rb = _board(tmp_path, [("+3V3", "F.Cu", 0.25, PATH), ("+3V3", "F.Cu", 0.25, stub)])
    net = extract(rb, ["+3V3"], coupling=False)
    assert net.stats["short_pieces_r_only"] >= 1
    assert any({"pin:C3.1", "pin:U2.8"} <= set(g) for g in net.groups["+3V3"])


def test_parallel_tracks_couple(tmp_path):
    a = [(110.0, 105.0), (120.0, 105.0)]
    c = [(110.0, 105.45), (120.0, 105.45)]               # 0.25 mm gap between 0.2 mm tracks
    b, br, rb = _board(tmp_path, [("Net-(U2-XTAL1)", "F.Cu", 0.2, a), ("Net-(U2-XTAL2)", "F.Cu", 0.2, c)])
    net = extract(rb, ["Net-(U2-XTAL1)", "Net-(U2-XTAL2)"])
    ks = [e for e in net.elements if e.kind == "K"]
    cm = [e for e in net.elements if e.kind == "C" and e.b != GROUND]
    assert ks and all(0 < e.value < 0.9 for e in ks)       # co-directed: positive coupling
    assert cm and sum(e.value for e in cm) > 0
    assert extract(rb, ["Net-(U2-XTAL1)", "Net-(U2-XTAL2)"], profile="power").stats["elements"].get("K", 0) == 0


# ----------------------------------------------------------------------------- end to end
def _have_ngspice():
    return shutil.which("ngspice") or os.environ.get("KAE_KICAD_WRAP")


@pytest.mark.skipif(not _have_ngspice(), reason="ngspice not available")
def test_dc_drop_equals_i_times_r(tmp_path):
    from kae.sim.evaluate import Context, evaluate
    b, br, rb = _board(tmp_path, [("+3V3", "F.Cu", 0.25, PATH)])
    text = """*@test drop kind=custom
*@nets +3V3
*@extract power
*@exclude C2 C3 L1
Vs <C3.1> 0 DC 3.3
Iload <U2.8> 0 DC 1
.tran 10n 1u
.meas tran v8 MIN v(<U2.8>) from=0.5u to=1u
*@info v8
*@end
"""
    ctx = Context(b, br, D.build(b, br), rb=rb, workdir=tmp_path / "sim")
    rep = evaluate(TB.parse(text), ctx, jobs=2)
    t = rep["tests"][0]
    assert "incomplete" not in t, t.get("incomplete")
    ideal = t["info"]["v8"]["ideal"]["typ"]
    routed = t["info"]["v8"]["routed"]["typ"]
    assert ideal == pytest.approx(3.3, abs=1e-6)
    ln = math.dist(PATH[0], PATH[1]) + math.dist(PATH[1], PATH[2])
    R = r_track(ln, 0.25, rb.board.stackup.cu_thickness[0])
    assert 3.3 - routed == pytest.approx(R * 1.0, rel=0.05, abs=5 * R_MIN)
