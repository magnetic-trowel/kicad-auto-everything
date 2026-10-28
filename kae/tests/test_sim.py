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
from kae.sim.testbench import fmt
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


# ----------------------------------------------------------------------------- testbench generator rules
def _pads2(n1, net1, n2, net2, pitch=1.6, w=0.8, h=0.9):
    return [(n1, net1, -pitch / 2, 0.0, w, h, "smd", 0.0, "", "passive"), (n2, net2, pitch / 2, 0.0, w, h, "smd", 0.0, "", "passive")]


EXTRA = [
    ("FB1", "600R@100MHz", "Inductor_SMD:L_0603_1608Metric", 110.0, 104.0, 0.0, _pads2("1", "+3V3", "2", "+3V3_A"), (1.3, 0.7)),
    ("U3", "ADS1115IDGS", "Package_SO:MSOP-10_3x3mm_P0.5mm", 110.0, 110.0, 0.0,
     [("1", "+3V3_A", -2.2, -1.0, 1.0, 0.3, "smd", 0.0, "VDD", "power_in"),
      ("2", "GND", -2.2, -0.5, 1.0, 0.3, "smd", 0.0, "GND", "power_in"),
      ("3", "DIV", -2.2, 0.0, 1.0, 0.3, "smd", 0.0, "AIN0", "input"),
      ("4", "SDA_X", -2.2, 0.5, 1.0, 0.3, "smd", 0.0, "SDA", "bidirectional"),
      ("5", "SCL", -2.2, 1.0, 1.0, 0.3, "smd", 0.0, "SCL", "input"),
      ("6", "GND", 2.2, 1.0, 1.0, 0.3, "smd", 0.0, "GND", "power_in")], (3.0, 2.0)),
    ("R10", "10k", "Resistor_SMD:R_0402_1005Metric", 106.0, 108.0, 0.0, _pads2("1", "+3V3_A", "2", "DIV", 1.0, 0.5, 0.6), (0.9, 0.5)),
    ("R11", "10k", "Resistor_SMD:R_0402_1005Metric", 106.0, 110.0, 0.0, _pads2("1", "DIV", "2", "GND", 1.0, 0.5, 0.6), (0.9, 0.5)),
    ("R12", "1k", "Resistor_SMD:R_0402_1005Metric", 106.0, 112.0, 0.0, _pads2("1", "+3V3", "2", "LED_K", 1.0, 0.5, 0.6), (0.9, 0.5)),
    ("R13", "33", "Resistor_SMD:R_0402_1005Metric", 106.0, 114.0, 0.0, _pads2("1", "SDA", "2", "SDA_X", 1.0, 0.5, 0.6), (0.9, 0.5)),
    ("R14", "4.7k", "Resistor_SMD:R_0402_1005Metric", 106.0, 116.0, 0.0, _pads2("1", "+3V3", "2", "SDA", 1.0, 0.5, 0.6), (0.9, 0.5)),
    ("U4", "SN74LVC1G04", "Package_TO_SOT_SMD:SOT-23-5", 114.0, 104.0, 0.0,
     [("1", "", -1.1, -0.95, 1.0, 0.6, "smd", 0.0, "NC", "no_connect"),
      ("2", "SDA", -1.1, 0.0, 1.0, 0.6, "smd", 0.0, "A", "input"),
      ("3", "GND", -1.1, 0.95, 1.0, 0.6, "smd", 0.0, "GND", "power_in"),
      ("4", "LED_K", 1.1, 0.95, 1.0, 0.6, "smd", 0.0, "Y", "output"),
      ("5", "+3V3", 1.1, -0.95, 1.0, 0.6, "smd", 0.0, "VCC", "power_in")], (2.0, 1.8)),
]


def _generated(tmp_path):
    from kae.sim.autotb import _Ctx, generate, rail_trees
    b = load(write_board(tmp_path, extra=EXTRA))
    br = build(b)
    d = D.build(b, br)
    return b, br, generate(b, br, d), rail_trees(_Ctx(b, br, d))


def test_supply_tree_follows_ferrites_and_finds_unnamed_rails(tmp_path):
    b, br, tests, trees = _generated(tmp_path)
    root = next(r for r, t in trees.items() if "+3V3_A" in t["nets"])
    assert trees[root]["nets"][0] == root and "+3V3_A" not in trees
    t = next(x for x in tests if x.id == f"rail_dc:{root}")
    assert "+3V3_A" in t.nets
    assert any(ln.startswith("I_U3_1 ") for ln in t.lines)


def test_ic_current_returns_at_its_nearest_ground_pin(tmp_path):
    b, br, tests, trees = _generated(tmp_path)
    root = next(r for r, t in trees.items() if "+3V3_A" in t["nets"])
    t = next(x for x in tests if x.id == f"rail_dc:{root}")
    line = next(ln for ln in t.lines if ln.startswith("I_U3_1 "))
    assert "<U3.2>" in line and "<U3.6>" not in line          # pin 2 is beside the supply pin; pin 6 is across


def test_dividers_are_simulated_and_pullups_count_at_worst_case(tmp_path):
    b, br, tests, trees = _generated(tmp_path)
    root = next(r for r, t in trees.items() if "+3V3_A" in t["nets"])
    t = next(x for x in tests if x.id == f"rail_dc:{root}")
    assert "DIV" in t.nets and "R10" not in t.exclude          # a divider: its resistors stay in the circuit
    assert "R12" in t.exclude
    assert any(ln.startswith("I_R12_pullup") and ln.endswith(fmt(3.3 / 1000.0)) for ln in t.lines)


def test_i2c_line_follows_series_resistors(tmp_path):
    b, br, tests, trees = _generated(tmp_path)
    t = next((x for x in tests if x.kind == "i2c" and "SDA" in x.nets), None)
    assert t is not None and "SDA_X" in t.nets
    assert any("<U3.4>" in ln for ln in t.lines)


def test_parallel_ideal_sources_merge_or_fail():
    from kae.sim.evaluate import _merge_parallel_sources
    out = _merge_parallel_sources(["V1 n1 0 DC 5", "V2 0 n1 DC 5", "R1 n1 0 1k"])
    assert out[0] == "V1 n1 0 DC 5" and out[1].startswith("* V2 merged") and out[2] == "R1 n1 0 1k"
    with pytest.raises(ValueError, match="different values"):
        _merge_parallel_sources(["V1 n1 0 DC 5", "V2 n1 0 DC 3.3"])
    with pytest.raises(ValueError, match="itself"):
        _merge_parallel_sources(["V1 n1 n1 DC 5"])


# ----------------------------------------------------------------------------- switching cells
def _cell_tests(tmp_path, vin=12.0):
    from kae.sim.autotb import generate
    b = load(write_board(tmp_path))
    br = build(b)
    if vin is not None:
        br["nets"]["VIN"]["volts"] = vin
    return b, br, {t.kind: t for t in generate(b, br, D.build(b, br)) if t.kind in ("cell", "loop")}


def test_cell_models_both_switches_at_their_power_pins(tmp_path):
    b, br, t = _cell_tests(tmp_path)
    cell = t["cell"]
    assert not cell.unknown and cell.exclude == ["L1"]          # the inductor is the load current source
    lines = "\n".join(cell.lines)
    assert "Vloop <U1.3> kae_hb 0" in lines                      # VIN pin, not EN (pin 2, also on VIN)
    assert "Xh kae_hb xhk hs kae_sw\nVXhs xhk <U1.5> 0" in lines
    assert "Xl <U1.5> xlk ls kae_sw\nVXls xlk <U1.4> 0" in lines
    assert "Cossh kae_hb kae_ch 100p\nRossh kae_ch <U1.5>" in lines and "Cossl <U1.5> kae_cl 100p\nRossl kae_cl <U1.4>" in lines
    assert re.search(r"^Iload <L1\.1> far ", lines, re.M)
    ploss = next(ln for ln in cell.lines if ln.startswith("let ploss"))
    assert all(f"i({v})" in ploss for v in ("VXhs", "VXls", "VDbhs", "VDbls")) and "kae_pdiss" in ploss
    assert "p_loss" in cell.meas_names() and not any(ln.startswith("B") and "i(V" in ln for ln in cell.lines)
    assert {"p_loss", "vsw_min", "v_far"} <= set(cell.info) and cell.requires[0].meas == "vsw_max"


def test_loop_is_judged_without_the_bus_voltage(tmp_path):
    b, br, t = _cell_tests(tmp_path, vin=None)
    assert t["cell"].unknown and not t["loop"].unknown
    loop = t["loop"]
    assert loop.exclude == ["C1"] and loop.nets == ["GND", "VIN"]
    assert any(ln.startswith("Iq <U1.4> <U1.3> AC ") for ln in loop.lines)


@pytest.mark.skipif(not _have_ngspice(), reason="ngspice not available")
def test_loop_inductance_ideal_is_the_esl_and_copper_adds_to_it(tmp_path):
    from kae.board import transform
    from kae.sim.evaluate import Context, evaluate
    b, br, t = _cell_tests(tmp_path / "a")
    loop = t["loop"]
    d = D.build(b, br)
    esl = next(p.esl for p in d.parts if p.ref == "C1")
    rep = evaluate([loop], Context(b, br, d, rb=None, workdir=tmp_path / "sim_i"), jobs=1)
    assert rep["tests"][0]["info"]["loop_nH"]["ideal"]["typ"] == pytest.approx(esl * 1e9, rel=1e-3)
    # route C1 to U1's VIN and GND pins: the loop gains the tracks' inductance
    fp = {f.ref: f for f in b.footprints}
    xy = {(r, n): transform.pad_xy(fp[r], next(p for p in fp[r].pads if p.number == n))
          for r, n in (("C1", "1"), ("C1", "2"), ("U1", "3"), ("U1", "4"))}
    for net, a, c in (("VIN", ("C1", "1"), ("U1", "3")), ("GND", ("C1", "2"), ("U1", "4"))):
        b.tracks.append(Track(uuid=str(uuid.uuid4()), net=net, layer="F.Cu", width=0.3, start=xy[a], end=xy[c]))
    rb = RoutedBoard(b, fills=None, brief=br)
    rep = evaluate([loop], Context(b, br, d, rb=rb, workdir=tmp_path / "sim_r"), jobs=1)
    cap = rep["tests"][0]["capability"]
    assert cap["ideal_nH"] == pytest.approx(esl * 1e9, rel=1e-3) and cap["layout_nH"] > 0.5


@pytest.mark.skipif(not _have_ngspice(), reason="ngspice not available")
def test_pdiss_is_the_power_in_board_resistances(tmp_path):
    from kae.sim.evaluate import Context, evaluate
    b = load(write_board(tmp_path, extra=EXTRA))
    br = build(b)
    d = D.build(b, br)
    text = """*@test diss kind=custom
*@nets +3V3 LED_K
Vs <R12.1> 0 DC 2
Vk <R12.2> 0 DC 0
.tran 10n 100n
.control
run
meas tran p AVG kae_pdiss from=50n to=100n
.endc
*@info p
*@end
"""
    rep = evaluate(TB.parse(text), Context(b, br, d, rb=None, workdir=tmp_path / "sim"), jobs=1)
    assert rep["tests"][0]["info"]["p"]["ideal"]["typ"] == pytest.approx(2.0 ** 2 / 1000.0, rel=1e-3)


@pytest.mark.skipif(not _have_ngspice(), reason="ngspice not available")
def test_cell_physics_at_the_typical_corner(tmp_path):
    from kae.sim.evaluate import Context, evaluate
    b, br, t = _cell_tests(tmp_path)
    rep = evaluate([t["cell"]], Context(b, br, D.build(b, br), rb=None, workdir=tmp_path / "sim"), jobs=4)
    r = rep["tests"][0]
    loss = r["info"]["p_loss"]["ideal"]
    assert loss["typ"] is not None and loss["typ"] > 0
    # the switch node swings rail to rail, plus at most a diode drop and the ring of the 1 nH input capacitor
    vmax = r["requirements"][0]["ideal"]
    assert 12.0 <= vmax["typ"] <= 13.5
    # conduction: the load current through one 50 mOhm switch at a time, plus the capacitors' ESR
    i_out = t["cell"].params["I_OUT"].typ
    assert r["info"]["p_cond"]["ideal"]["typ"] == pytest.approx(i_out ** 2 * 0.05, rel=0.1)
    assert r["info"]["e_sw"]["ideal"]["typ"] > 0


@pytest.mark.skipif(not _have_ngspice(), reason="ngspice not available")
def test_cell_converges_at_every_corner(tmp_path):
    from kae.sim.evaluate import Context, evaluate
    b, br, t = _cell_tests(tmp_path)
    rep = evaluate([t["cell"]], Context(b, br, D.build(b, br), rb=None, workdir=tmp_path / "sim"), jobs=4)
    assert not rep["tests"][0]["problems"]


# ----------------------------------------------------------------------------- budgets
def test_budget_crossing_interpolates_to_the_first_failure():
    from kae.sim.budget import _crossing
    assert _crossing([(0, 10.0), (1, 12.0), (2, 14.0)], "<=", 13.0) == (1.5, "")
    assert _crossing([(0, 14.0), (1, 15.0)], "<=", 13.0)[0] == 0.0
    L, note = _crossing([(0, 10.0), (4, 11.0)], "<=", 13.0)
    assert L == 4 and "sweep's end" in note
    L, note = _crossing([(0, 10.0), (1, None), (2, 14.0)], "<=", 13.0)
    assert L == 0 and "converge" in note


def test_budget_sweep_replaces_the_loop_link_and_reaches_the_placer(tmp_path):
    from kae.physics.place_terms import Terms
    from kae.sim.autotb import LOOP_LINK
    from kae.sim.budget import _with_l, apply
    b, br, t = _cell_tests(tmp_path)
    link = next(ln for ln in t["cell"].lines if ln.startswith(LOOP_LINK + " "))
    u = _with_l(t["cell"], 2.0)
    assert link not in u.lines and f"Lloop {' '.join(link.split()[1:3])} 2.0n" in u.lines
    assert _with_l(t["cell"], 0.0).lines == t["cell"].lines
    sid = t["cell"].structure
    assert apply(br, {sid: dict(value=3.25, unit="nH", basis="simulated: test", **{"class": "sim"})}) == [sid]
    st = next(s for s in Terms(b, br).structs if s.id == sid)
    assert st.alloc.value == 3.25 and st.alloc.basis == "simulated: test"
