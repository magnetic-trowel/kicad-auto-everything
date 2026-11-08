# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The physics set's evaluator fixes (docs/topics/physics/physics-set-coverage.md):
the schematic's pin facts reach the evaluator, parts that supply and consume are loads, a self-powered module still
heats the board, split footprints are one part, radios are found by part number, and big boards coarsen their raster."""
import pytest

from kae.board import kicad_file, pinfacts as PF
from kae.circuit import brief as B
from kae.circuit.roles import radio_kind
from kae.excite import dc as DC, models as M, observe as O, sources as S
from kae.excite.evaluate import coarsen_pitch, ledger_for


def _pad(num, x, net_id, net, fn="", pt=""):
    extra = (f' (pinfunction "{fn}")' if fn else "") + (f' (pintype "{pt}")' if pt else "")
    return (f'\t\t(pad "{num}" smd rect (at {x} 0) (size 0.8 0.8) (layers "F.Cu") (net {net_id} "{net}"){extra}'
            f' (uuid "00000000-0000-0000-0000-{abs(hash((num, x, net))) % 10**12:012d}"))\n')


def _fp(ref, value, lib, at, pads, k):
    return (f'\t(footprint "{lib}" (layer "F.Cu") (uuid "00000000-0000-0000-0000-{k:012d}") (at {at} 10)\n'
            f'\t\t(property "Reference" "{ref}" (at 0 0) (layer "F.SilkS"))\n'
            f'\t\t(property "Value" "{value}" (at 0 1) (layer "F.Fab"))\n' + "".join(pads) + '\t)\n')


def _board(tmp_path, nets, fps):
    head = '(kicad_pcb (version 20240108) (generator "test")\n\t(net 0 "")\n' + \
           "".join(f'\t(net {i} "{n}")\n' for i, n in enumerate(nets, 1))
    edge = "".join(f'\t(gr_line (start {a} {b}) (end {c} {d}) (stroke (width 0.1) (type solid)) (layer "Edge.Cuts"))\n'
                   for a, b, c, d in ((0, 0, 60, 0), (60, 0, 60, 20), (60, 20, 0, 20), (0, 20, 0, 0)))
    p = tmp_path / "t.kicad_pcb"
    p.write_text(head + edge + "".join(fps) + ")\n")
    return kicad_file.load(p, rules=False)


def _plan(b, intent=None):
    br = B.build(b)
    bd = M.build(b, br)
    srcs = S.add_all(bd, br)
    P, _ = ledger_for(bd, br, srcs, intent)
    return DC.plan(b, br, bd, P, srcs, intent), bd, br, srcs


def test_pin_facts_fill_only_pads_the_board_left_blank(tmp_path):
    n = {"VCC": 1, "GND": 2}
    b = _board(tmp_path, list(n), [_fp("U1", "X", "lib:X", 10, [_pad("1", 0, 1, "VCC"), _pad("2", 1, 2, "GND", "VSS", "power_in")], 1)])
    pins = PF.from_pintypes({"refs": {"U1": {"1": {"type": "power_in", "name": "VDD"}, "2": {"type": "passive", "name": "X"},
                                             "3": {"type": "", "name": ""}}}})
    assert pins == {"U1": {"1": ["power_in", "VDD"], "2": ["passive", "X"]}}
    assert PF.apply(b, pins) == 1
    p1, p2 = b.footprints[0].pads
    assert (p1.pintype, p1.pinfunction) == ("power_in", "VDD")
    assert (p2.pintype, p2.pinfunction) == ("power_in", "VSS")          # the board's own annotation stays


def test_a_self_powered_module_heats_the_board_with_no_dc_flow(tmp_path):
    """A XIAO powered from its own USB is the only part on its 5 V rail: no current flows in the carrier's copper,
    but its own draw is heat (a plan with no loads had no heat band, and the board no observation at all)."""
    nets = ["VCC", "GND", "ROW0"]
    pads = [_pad("1", 0, 1, "VCC", "5V", "power_out"), _pad("2", 1, 2, "GND", "GND", "power_in"),
            _pad("3", 2, 3, "ROW0", "D0", "bidirectional")]
    sw = [_pad("1", 0, 3, "ROW0"), _pad("2", 3, 2, "GND")]
    b = _board(tmp_path, nets, [_fp("U1", "seeed_xiao_rp2040", "Seeed:XIAO", 10, pads, 1),
                                _fp("SW1", "SW_Push", "Button:SW_Push", 40, sw, 2)])
    intent = {"parts": {"U1": {"I_A": [0.02, 0.05], "I_sustained_A": 0.036}}, "nets": {"VCC": {"source": "U1", "V_V": 5.0}}}
    pl, bd, _, _ = _plan(b, intent)
    assert not pl.loads
    assert [(s["ref"], s["rail"]) for s in pl.self_loads] == [("U1", "VCC")]
    assert set(pl.self_loads[0]["pads"]) <= pl.dc_pads
    assert not any(DC.injections(pl, {pl.self_loads[0]["key"]: 0.036}).values())   # nothing in the copper
    from kae.excite import heat as HT
    heat = HT.part_heat(bd, pl, {pl.self_loads[0]["key"]: 0.036}, {}, {})
    assert heat == {"U1": pytest.approx(0.18)}
    assert any(p.subject == "heat:U1" and p.name == "theta_jb" for p in HT.params(bd, pl, {}, intent))


def test_split_footprints_are_one_part_and_a_module_that_regulates_is_also_a_load(tmp_path):
    """A Teensy drawn as two footprints with one reference (edge pins, back pins): the plan sees both footprints'
    pads (the last one alone had no supply or ground pin), its regulator feeds +3.3V from +5V, and its own draw
    is a load on +5V (a feed was never a load before, so the module's MCU drew nothing)."""
    nets = ["+5V", "GND", "+3.3V", "T24", "OUT"]
    edge = [_pad("1", 0, 2, "GND", "GND", "power_in"), _pad("31", 1, 3, "+3.3V", "3V3", "power_out"),
            _pad("33", 2, 1, "+5V", "VIN", "power_in")]
    back = [_pad("35", 0, 4, "T24", "24_A10", "bidirectional")]
    j1 = [_pad("1", 0, 1, "+5V"), _pad("2", 1, 2, "GND")]
    u2 = [_pad("1", 0, 3, "+3.3V", "V+", "power_in"), _pad("2", 1, 2, "GND", "V-", "power_in"),
          _pad("3", 2, 5, "OUT", "OUT", "output")]
    b = _board(tmp_path, nets, [_fp("U1", "Teensy4.0", "Teensy:Teensy40", 10, edge, 1),
                                _fp("U1", "Teensy4.0", "Teensy:Teensy40_back", 20, back, 2),
                                _fp("J1", "Conn_01x02", "Connector:Header_1x02", 40, j1, 3),
                                _fp("U3", "LM358", "Package_SO:SOIC-8", 50, u2, 4)])
    intent = {"parts": {"U1": {"I_A": [0.05, 0.11], "I_sustained_A": 0.1}},
              "nets": {"+5V": {"source": "J1", "V_V": 5.0}, "+3.3V": {"source": "U1", "V_V": 3.3, "from": "+5V"}}}
    pl, _, br, _ = _plan(b, intent)
    assert DC._pads(b)["U1"][-1][0] == "35" and len(DC._pads(b)["U1"]) == 4
    assert pl.feeds["+3.3V"]["kind"] == "linear" and pl.feeds["+3.3V"]["ref"] == "U1"
    assert ("U1", "+5V") in [(ld["ref"], ld["rail"]) for ld in pl.loads]
    assert next(p for p in br["parts"].values() if p["ref"] == "U1")["kind"] == "module"


def test_radios_by_part_number():
    for text, kind in [("ESP32-WROOM-32E RF_Module:ESP32-WROOM-32", "wifi_bt"), ("NEO-M8N", "gnss"),
                       ("SIM800L", "cellular"), ("RFM95W-868S2", "subghz"), ("nRF52840", "wifi_bt"),
                       ("MAX-M10S", "gnss"), ("SX1262", "subghz")]:
        assert radio_kind(text, "ic") == kind, text
    for text in ("seeed_xiao_rp2040", "STM32F103C8", "ESP32-P4", "GPSDO controller", "LM317", "Teensy4.0"):
        assert radio_kind(text, "ic") is None, text
    assert radio_kind("ESP32-C3", "antenna") is None                  # only active parts are radios
    assert radio_kind("BLB01", "ic", "rf") == "rf"


def test_a_radio_module_gets_supply_and_rf_observers_and_drives_the_carrier(tmp_path):
    """A radio module is a port (a board of its own), so it had no supply observer and no aggressor: EMI terms on
    its supply never matched anything. Now it is observed between its supply pin and its nearest ground pin, its
    RF pin is a victim, and its supply current steps are an aggressor."""
    nets = ["+3V3", "GND", "ANT", "VIN"]
    mod = [_pad("1", 0, 1, "+3V3", "VCC", "power_in"), _pad("2", 1, 2, "GND", "GND", "power_in"),
           _pad("3", 2, 3, "ANT", "ANT", "passive")]
    ldo = [_pad("1", 0, 4, "VIN", "VI", "power_in"), _pad("2", 1, 2, "GND", "GND", "power_in"),
           _pad("3", 2, 1, "+3V3", "VO", "power_out")]
    j1 = [_pad("1", 0, 4, "VIN"), _pad("2", 1, 2, "GND")]
    c1 = [_pad("1", 0, 1, "+3V3"), _pad("2", 1, 2, "GND")]
    ant = [_pad("1", 0, 3, "ANT")]
    b = _board(tmp_path, nets, [_fp("U1", "RFM95W", "RF_Module:HOPERF_RFM9XW_SMD", 10, mod, 1),
                                _fp("U2", "AP2112K-3.3", "Package_TO_SOT_SMD:SOT-23-5", 25, ldo, 2),
                                _fp("J1", "Conn_01x02", "Connector:Header_1x02", 40, j1, 3),
                                _fp("C1", "10uF", "Capacitor_SMD:C_0805", 50, c1, 4),
                                _fp("AE1", "Antenna", "RF_Antenna:Antenna", 55, ant, 5)])
    br = B.build(b)
    bd = M.build(b, br)
    srcs = S.add_all(bd, br)
    assert O.radio_parts(bd, br) == {"U1": "subghz"}
    obs = {o.name: o for o in O.observers(bd, br, srcs)}
    # inside the module: its MCU's supply node behind its pin, decoupled by the module's own capacitor
    mn = bd.module_nodes["U1"]
    assert (obs["supply:U1:+3V3"].a, obs["supply:U1:+3V3"].b) == (mn["+3V3"], mn["g"])
    assert "victim:rf:U1.3" in obs and obs["victim:rf:U1.3"].meta["cls"] == "rf"
    core = [s for s in srcs if s.name == "core:U1:+3V3"]
    assert core and (core[0].a, core[0].b) == (mn["+3V3"], mn["g"])
    assert core[0].meta["didt"] == pytest.approx(S.MODULE_I / S.MODULE_TR)
    pkg = {e.name: e for e in bd.circuit.elems if e.name.startswith("U1.")}
    assert pkg["U1.1:mpkg"].pa == "U1.1" and pkg["U1.2:mpkg"].pa == "U1.2"
    # the module's own decoupling carries most of its edge: little of it reaches the carrier's copper
    J = bd.circuit.solve(core[0].meta["f_e"], [core[0]])[core[0].name]["Ja"]
    assert abs(J.get("U1.1", 0)) < 0.5


def test_a_power_module_is_no_clocked_aggressor():
    assert S.NOT_CLOCKED.search("Mini360 DC-DC buck")
    assert not S.NOT_CLOCKED.search("ESP32-WROOM-32E RF_Module")


def test_the_raster_coarsens_only_past_its_budget():
    w = (0.0, 0.0, 236.0, 226.0)                       # a 236 x 226 mm six-layer board: 5.1M cells at 0.25 mm
    p, note = coarsen_pitch(w, 0.25, 6, 3_000_000)
    assert p == 0.5 and "5.12M cells" in note
    assert coarsen_pitch((0, 0, 100, 100), 0.25, 4, 3_000_000) == (0.25, None)
    assert coarsen_pitch(w, 0.25, 6, None) == (0.25, None)


def test_to_part_scopes_a_term_to_the_victim_side():
    from kae.intent import objective as OB
    t = dict(id="E1", tier="limit", obs="supply.peak", where={"to_part": ["U1"]}, max="10 mV", rate="1 mW_eq/mV", why="x")
    into = dict(id="supply.peak", scope=dict(from_parts=["U5"], to_parts=["U1"]))
    out_of = dict(id="supply.peak", scope=dict(from_parts=["U1"], to_parts=["U5"]))
    assert OB._match(t, into, {}) and not OB._match(t, out_of, {})
    assert OB.specificity(t) == 2


def test_a_net_tie_joins_its_nets_and_a_load_on_a_rail_of_unknown_voltage_still_heats(tmp_path):
    """A net tie (an analog ground tied to the power ground) is copper by design: it conducts at DC, or a regulator
    returning at its analog ground pins left the DC flow open. A load on a rail whose voltage nothing states heats
    at the DC band's 3.3 V fallback (it heated at 0 V: an LED digit board had no dissipating part)."""
    nets = ["GND", "GNDA"]
    b = _board(tmp_path, nets, [_fp("NT1", "NetTie_2", "NetTie:NetTie-2_SMD_Pad0.5mm", 10,
                                    [_pad("1", 0, 1, "GND"), _pad("2", 1, 2, "GNDA")], 1)])
    br = B.build(b)
    bd = M.build(b, br)
    assert [e.kind for e in bd.circuit.elems if e.name == "NT1"] == ["short"]
    from types import SimpleNamespace
    from kae.excite import heat as HT
    pl = DC.Plan()
    pl.loads = [dict(ref="D1", rail="N$20", key=("dc:D1@N$20", "I_A"))]
    pl.volts = {"N$20": None}
    heat = HT.part_heat(SimpleNamespace(part_kind={"D1": ("led", None, "")}), pl, {("dc:D1@N$20", "I_A"): 0.02}, {}, {})
    assert heat == {"D1": pytest.approx(0.066)}


def test_a_fuse_conducts(tmp_path):
    """A fuse had no circuit element, so a rail fed through one was open at DC and its board had no DC band."""
    b = _board(tmp_path, ["VIN", "VF"], [_fp("F1", "500mA", "Fuse:Fuse_1206_3216Metric", 10,
                                              [_pad("1", 0, 1, "VIN"), _pad("2", 1, 2, "VF")], 1)])
    br = B.build(b)
    assert next(p for p in br["parts"].values() if p["ref"] == "F1")["kind"] == "fuse"
    bd = M.build(b, br)
    e = [e for e in bd.circuit.elems if e.name == "F1"]
    assert len(e) == 1 and e[0].kind == "R" and e[0].kind in DC.DC_KINDS


def test_the_window_holds_copper_routed_beyond_the_outermost_pad():
    """The window was the pads' extent plus 3 mm: a backplane's 5 V track looping 4 mm past its last connector was cut
    off, and the evaluator found the rail open where KiCad finds it connected (no score)."""
    from types import SimpleNamespace as NS
    from shapely.geometry import box
    from kae.excite.evaluate import board_window
    fp = NS(ref="J1", x=10.0, y=10.0, rot=0.0, side="F", pads=[NS(number="1", lx=0.0, ly=0.0, net="5V")])
    b = NS(footprints=[fp], outline=[], vias=[], zones=[],
           tracks=[NS(start=(10.0, 10.0), end=(17.0, 10.0), width=0.5, mid=None)])
    from kae.board import transform
    x, y = transform.pad_xy(fp, fp.pads[0])
    w = board_window(b)
    assert w[2] >= 17.0 + 0.25 and w[0] <= x - 3
    b.outline = [box(0, 0, 40, 30)]
    assert board_window(b) == (0, 0, 40, 30)


def test_feeds_that_feed_each_other_are_broken_at_the_link_the_pins_deny(tmp_path):
    """An intent fact read an LDO backwards (AMP_VDD from PCM_AVDD through U2) while the pins say PCM_AVDD from AMP_VDD:
    the two feeds formed a cycle with no way in, and the DC band was void. The link the pins contradict is dropped and
    the connector on its rail feeds it."""
    nets = ["AMP_VDD", "GND", "PCM_AVDD"]
    j1 = [_pad("1", 0, 1, "AMP_VDD"), _pad("2", 1, 2, "GND")]
    u2 = [_pad("1", 0, 1, "AMP_VDD", "VIN", "power_in"), _pad("2", 1, 2, "GND", "GND", "power_in"),
          _pad("3", 2, 3, "PCM_AVDD", "VOUT", "power_out")]
    u1 = [_pad("1", 0, 3, "PCM_AVDD", "AVDD", "power_in"), _pad("2", 1, 2, "GND", "AGND", "power_in")]
    b = _board(tmp_path, nets, [_fp("J1", "Conn_01x02", "Connector:Header_1x02", 10, j1, 1),
                                _fp("U2", "TJ9198GSF5-3.3", "Package_TO_SOT_SMD:SOT-23-5", 25, u2, 2),
                                _fp("U1", "PCM5102", "Package_SO:TSSOP-20", 45, u1, 3)])
    intent = {"nets": {"AMP_VDD": {"source": "U2", "from": "PCM_AVDD", "kind": "linear", "V_V": 3.3},
                       "PCM_AVDD": {"source": "U2", "from": "AMP_VDD", "kind": "linear", "V_V": 3.3}}}
    pl, _, _, _ = _plan(b, intent)
    assert pl.feeds["PCM_AVDD"]["ref"] == "U2" and pl.feeds["PCM_AVDD"]["rin"] == "AMP_VDD"
    assert pl.feeds["AMP_VDD"] == dict(kind="external", ref="J1", out=["J1.1"], gnd=["J1.2"], rating=pl.feeds["AMP_VDD"].get("rating"))
    assert any("cycle" in n for n in pl.notes)


def test_a_radio_the_operating_facts_name_is_a_clocked_aggressor(tmp_path):
    """A Bluetooth IC with no recognised subtype (RN42) drew no core current, so a board whose only clocked part is its
    radio had no aggressor and no EMI observation. The operating facts' radios count."""
    nets = ["+3V3", "GND"]
    u1 = [_pad("1", 0, 1, "+3V3", "VDD", "power_in"), _pad("2", 1, 2, "GND", "GND", "power_in"),
          _pad("3", 2, 2, "GND", "GND", "power_in"), _pad("4", 3, 2, "GND", "GND", "power_in")]
    b = _board(tmp_path, nets, [_fp("U1", "RN42", "Lib:RN42", 10, u1, 1)])
    br = B.build(b)
    bd = M.build(b, br)
    assert not [s for s in S.add_all(bd, br) if s.kind == "core"]
    bd = M.build(b, br)
    bd.radios = {"U1": "bluetooth"}
    core = [s for s in S.add_all(bd, br) if s.kind == "core"]
    assert [s.name for s in core] == ["core:U1:+3V3"] and core[0].meta["I"] == S.DYNAMIC["mcu"][0]
