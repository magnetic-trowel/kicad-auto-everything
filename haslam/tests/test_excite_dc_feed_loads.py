# SPDX-FileCopyrightText: 2026 HaslamPCB contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The DC plan's loads where the facts state only the converter: a rail whose only loads are unstated connector
exports takes what its feed delivers, and a charger with no load charges the external source one series part away
(obd-solar, FRICTION.md #56, #66)."""
import pytest

from circuit_fixtures import IC, C, D, L, Q, R, board, fp
from haslam.circuit import brief as B
from haslam.excite import dc as DC
from haslam.excite import models as M
from haslam.excite import sources as S
from haslam.excite.beliefs import corners
from haslam.excite.evaluate import ledger_for

CELL = "cell:buck:U1"


def _buck(out="+3V3"):
    """12 V in at J1; a TPS54202 buck (U1, L1) makes `out`."""
    return [
        IC("U1", "TPS54202", "Package_TO_SOT_SMD:SOT-23-6", [
            ("1", "GND", "GND", "power_in"), ("2", "SW", "SW", "power_out"), ("3", "VIN", "+12V", "power_in"),
            ("4", "FB", "FB", "input"), ("5", "EN", "+12V", "input"), ("6", "BOOT", "BST", "passive")]),
        C("C1", "10uF", "+12V", "GND", lib="Capacitor_SMD:C_1206_3216Metric"), C("C3", "100nF", "BST", "SW"),
        L("L1", "10uH 2A", "SW", out), C("C4", "22uF", out, "GND", lib="Capacitor_SMD:C_0805_2012Metric"),
        R("R1", "45.3k", out, "FB"), R("R2", "10k", "FB", "GND"),
        fp("J1", "Barrel_Jack", "Connector_BarrelJack:BarrelJack_Horizontal", [("1", "+12V", "", ""), ("2", "GND", "", "")]),
    ]


def _usb(ref="J2", rail="+3V3"):
    return fp(ref, "USB_A", "Connector_USB:USB_A_Molex_67643_Horizontal",
              [("1", rail, "VBUS", "passive"), ("2", "DM", "", ""), ("3", "DP", "", ""), ("4", "GND", "GND", "passive")])


def _plan(parts, intent):
    b = board(parts)
    br = B.build(b, facts=intent)
    bd = M.build(b, br)
    srcs = S.add_all(bd, br)
    P, _ = ledger_for(bd, br, srcs, intent)
    return DC.plan(b, br, bd, P, srcs, intent), P, srcs


def _balanced(pl, P, srcs):
    """Every corner's injections balance on every piece of the DC circuit; returns the typical point's."""
    cps = {s.name: corners(P[s.name].values(), n=8, seed=0) for s in srcs}
    own = corners(pl.params, n=8, seed=1)
    out = None
    for c, o in enumerate(own):
        cv = dict(o)
        for s in srcs:
            if s.kind == "cell":
                cv[s.name] = {k[1]: v for k, v in cps[s.name][c].items()}
        lost = []
        inj = DC.injections(pl, cv, lost)
        assert DC.imbalance(pl, inj, lost) == []
        out = out or inj
    return out


def _param(pl, subject):
    return next(p for p in pl.params if p.subject == subject and p.name == "I_A")


def test_an_export_alone_on_a_cell_rail_takes_the_cells_stated_current():
    pl, P, srcs = _plan(_buck() + [_usb()], {"cells": {CELL: {"I_A": [0.5, 1.0, 1.5]}}})
    p = _param(pl, "dc:J2@+3V3")
    assert (p.typ, p.lo, p.hi, p.source) == (pytest.approx(1.0), pytest.approx(0.5), pytest.approx(1.5), "intent")
    inj = _balanced(pl, P, srcs)
    assert inj["J2.1"] == pytest.approx(-1.0)
    q = DC.export_questions(pl)[("dc:J2@+3V3", "I_A")]       # still asked: the facts state the converter, not the export
    assert q["from_feed"] == "U1" and "U1 delivers" in q["ask"] and q["assumed_share"] is None


def test_an_unstated_cell_current_leaves_the_one_percent_prior():
    pl, P, srcs = _plan(_buck() + [_usb()], None)
    p = _param(pl, "dc:J2@+3V3")
    assert p.source == "prior" and p.typ == pytest.approx(DC.EXPORT_SHARE * 1.5)
    assert any("U1's current is a prior" in n for n in pl.notes)            # said, and asked with high priority
    q = DC.export_questions(pl)[("dc:J2@+3V3", "I_A")]
    assert q["priority"] == "high" and any("prior current" in w for w in q["might_differ"])
    _balanced(pl, P, srcs)


def test_an_export_beside_another_load_keeps_its_prior():
    mcu = IC("U2", "STM32G071KBT6", "Package_QFP:LQFP-32_7x7mm_P0.8mm",
             [("4", "VDD", "+3V3", "power_in"), ("5", "VSS", "GND", "power_in")])
    pl, P, srcs = _plan(_buck() + [_usb(), mcu], {"cells": {CELL: {"I_A": [0.5, 1.0, 1.5]}}})
    assert _param(pl, "dc:J2@+3V3").source == "prior"


def test_a_cells_stated_output_current_wins_and_is_split_over_the_exports_by_rating():
    j3 = fp("J3", "Conn_01x02", "Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical",
            [("1", "+3V3", "", "passive"), ("2", "GND", "", "passive")])
    pl, P, srcs = _plan(_buck() + [_usb(), j3], {"cells": {CELL: {"I_A": [0.5, 1.0, 1.5], "I_out_A": 0.8}}})
    a, b = _param(pl, "dc:J2@+3V3"), _param(pl, "dc:J3@+3V3")
    rating = {ex["ref"]: ex["rating_A"] for ex in pl.exports_assumed}
    assert a.typ + b.typ == pytest.approx(0.8)
    assert a.typ / b.typ == pytest.approx(rating["J2"] / rating["J3"])      # by the connectors' class ratings
    _balanced(pl, P, srcs)


def _charger(series):
    """The buck charges a 12 V battery off the board (J3 on VBAT, its voltage stated) through `series` from CHG."""
    return _buck("CHG") + [series, C("C5", "100uF", "VBAT", "GND", lib="Capacitor_SMD:C_1210_3225Metric"), fp("J3", "Conn_01x02", "Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical",
                                    [("1", "VBAT", "", "passive"), ("2", "GND", "", "passive")])]


FACTS = {"cells": {CELL: {"I_A": [0.01, 0.6, 0.75]}}, "nets": {"VBAT": {"V_V": 12.6}, "CHG": {"V_V": 13.5}}}


def test_a_charger_with_no_load_charges_the_battery_through_its_blocking_fet():
    pl, P, srcs = _plan(_charger(Q("Q1", "AO3407A", "G", "CHG", "VBAT")), FACTS)
    ld = next(x for x in pl.loads if x.get("charge"))
    assert (ld["ref"], ld["rail"], ld["charge"], ld["sup"]) == ("J3", "CHG", "VBAT", ["Q1.3"])
    p = _param(pl, "dc:J3@CHG")
    assert (p.typ, p.hi, p.source) == (pytest.approx(0.6), pytest.approx(0.75), "intent")
    inj = _balanced(pl, P, srcs)
    # the FET passes the charge on into VBAT, and the battery takes it at its connector
    assert inj["Q1.3"] == pytest.approx(-0.6) and inj["Q1.2"] == pytest.approx(0.6)
    assert inj["J3.1"] == pytest.approx(-0.6) and inj["J3.2"] == pytest.approx(0.6)
    assert not any("nothing draws from it" in n for n in pl.notes)


def test_a_charger_through_a_diode_feeds_its_battery_as_the_rails_only_export():
    """With a blocking diode the brief feeds VBAT from CHG through D1, so the battery's connector is VBAT's only load:
    an export, which takes the charger's current through the diode."""
    pl, P, srcs = _plan(_charger(D("D1", "SS34", "VBAT", "CHG")), FACTS)
    p = _param(pl, "dc:J3@VBAT")
    assert (p.typ, p.hi, p.source) == (pytest.approx(0.6), pytest.approx(0.75), "intent") and "through D1" in p.basis
    inj = _balanced(pl, P, srcs)
    assert inj["J3.1"] == pytest.approx(-0.6)


def test_a_resistor_link_to_a_connector_rail_is_no_charge_path():
    """antmicro sdi-mipi: a buck's 3V3_OUT reaches +3V3 through R40, and the brief reads +3V3 as fed by its connector:
    one rail joined by a link, not a battery being charged (read as one, 1.6 A went into the connector)."""
    pl, _, _ = _plan(_charger(R("R9", "0", "CHG", "VBAT")), FACTS)
    assert not any(x.get("charge") for x in pl.loads)


def test_no_charge_path_when_the_switch_is_off():
    pl, _, _ = _plan(_charger(Q("Q1", "AO3407A", "G", "CHG", "VBAT")), FACTS)
    DC.CHARGE_SINKS, old = False, DC.CHARGE_SINKS
    try:
        pl2, _, _ = _plan(_charger(Q("Q1", "AO3407A", "G", "CHG", "VBAT")), FACTS)
    finally:
        DC.CHARGE_SINKS = old
    assert any(x.get("charge") for x in pl.loads) and not any(x.get("charge") for x in pl2.loads)
    assert any("nothing draws from it" in n for n in pl2.notes)


def test_planned_injections_reads_the_facts_as_the_evaluator_does():
    """The brief is built from the facts: VBAT, with no source part, is fed at J3 because the facts give its voltage,
    and a haslam.intent/1 document is read through its facts. Without them the charge path did not exist."""
    b = board(_charger(Q("Q1", "AO3407A", "G", "CHG", "VBAT")))
    doc = {"schema": "haslam.intent/1", "facts": FACTS}
    for intent in (FACTS, doc):
        inj = DC.planned_injections(b, intent)
        assert inj["Q1.3"] == pytest.approx(-0.6) and inj["J3.1"] == pytest.approx(-0.6)


def test_per_net_injections_put_a_series_parts_current_on_its_pads():
    """A fuse F1 from the input J1 to VIN, a sense resistor R3 to the load's rail, a 100k/100k divider on VIN: per net,
    every net balances, the fuse and shunt carry the whole load current, the divider its few microamperes."""
    from haslam.excite.circuit import Elem
    pads = {"J1": [("1", "RAW", "", ""), ("2", "GND", "", "")], "F1": [("1", "RAW", "", ""), ("2", "VIN", "", "")],
            "R3": [("1", "VIN", "", ""), ("2", "OUT", "", "")], "U1": [("1", "OUT", "", ""), ("2", "GND", "", "")],
            "R1": [("1", "VIN", "", ""), ("2", "MID", "", "")], "R2": [("1", "MID", "", ""), ("2", "GND", "", "")]}

    def el(name, kind, r, pa, pb):
        return Elem(name=name, a=pa, b=pb, z=lambda w, r=r: r, pa=pa, pb=pb, kind=kind)
    elems = [el("F1", "R", 0.01, "F1.1", "F1.2"), el("R3", "R", 0.1, "R3.1", "R3.2"),
             el("R1", "R", 1e5, "R1.1", "R1.2"), el("R2", "R", 1e5, "R2.1", "R2.2")]
    inj = {"J1.1": 1.0, "J1.2": -1.0, "U1.1": -1.0, "U1.2": 1.0}
    out, notes = DC.element_terminals(pads, elems, inj)
    assert notes == []
    net_at = {f"{r}.{n}": net for r, pp in pads.items() for n, net, _, _ in pp}
    for net in set(net_at.values()):
        assert sum(a for t, a in out.items() if net_at[t] == net) == pytest.approx(0.0, abs=1e-12)
    assert out["F1.1"] == pytest.approx(-1.0) and out["F1.2"] == pytest.approx(1.0)
    assert out["R3.1"] == pytest.approx(-1.0, rel=1e-4) and out["R3.2"] == pytest.approx(1.0, rel=1e-4)
    assert abs(out.get("R1.1", 0.0)) < 1e-6                        # the divider: microamperes at most


def test_per_net_injections_of_a_real_plan_balance_net_by_net():
    b = board(_charger(Q("Q1", "AO3407A", "G", "CHG", "VBAT")))
    inj = DC.planned_injections(b, FACTS, per_net=True)
    net_at = {f"{f.ref}.{p.number}": p.net for f in b.footprints for p in f.pads}
    for net in set(net_at.values()):
        assert sum(a for t, a in inj.items() if net_at.get(t) == net) == pytest.approx(0.0, abs=1e-9)
    # the buck's current reaches CHG through its inductor L1, which the per-pad plan never named
    assert inj["L1.2"] == pytest.approx(0.6)
