# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""kae.physics.converter against hand calculations (TI SLVA477, SLVA372, SLVA721, SLVA535, SLYT309), and the
sites that call it: a boost cell's ledger and hot-loop loss, and the DC input current of a boost."""
from types import SimpleNamespace

import pytest

from kae.excite import dc as DC
from kae.excite import params as PA
from kae.excite.beliefs import Ledger, corners
from kae.physics import converter as CV


def test_buck_by_hand():
    # 12 V -> 3.3 V, 2 A, eta 0.9, 4.7 uH at 500 kHz
    o = CV.operating("buck", 12.0, 3.3, 2.0, 0.9, L=4.7e-6, f_sw=500e3)
    assert o.D == pytest.approx(0.275)
    assert o.I_sw == o.I_L == 2.0 and o.loop == "input"
    assert o.I_in == pytest.approx(2.0 * 3.3 / (12.0 * 0.9))          # 0.6111 A
    assert o.dI == pytest.approx((12.0 - 3.3) * 0.275 / (4.7e-6 * 500e3))   # 1.018 A
    assert o.I_pk == pytest.approx(2.0 + 1.01809 / 2, rel=1e-4)


def test_boost_by_hand():
    # 3.7 V -> 5 V, 1 A out, eta 0.9, 4.7 uH at 1.2 MHz: the switch carries the input current
    o = CV.operating("boost", 3.7, 5.0, 1.0, 0.9, L=4.7e-6, f_sw=1.2e6)
    assert o.D == pytest.approx(1 - 3.7 * 0.9 / 5.0)                    # 0.334
    assert o.I_sw == o.I_L == o.I_in == pytest.approx(5.0 / (3.7 * 0.9))   # 1.5015 A, not 1 A
    assert o.I_L == pytest.approx(1.0 / (1 - o.D))
    assert o.loop == "output"
    assert o.dI == pytest.approx(3.7 * 0.334 / (4.7e-6 * 1.2e6))       # 0.2191 A
    assert o.I_pk == pytest.approx(1.5015 + 0.2191 / 2, rel=1e-3)


def test_inverting_buck_boost_by_hand():
    # 5 V -> -5 V, 0.5 A, eta 0.9: D = 5 / (4.5 + 5), I_L = I_out / (1 - D) = I_in + I_out
    o = CV.operating("inverting_buck_boost", 5.0, -5.0, 0.5, 0.9)
    assert o.D == pytest.approx(5.0 / 9.5)
    assert o.I_L == pytest.approx(0.5 / (1 - 5.0 / 9.5))               # 1.0556 A
    assert o.I_L == pytest.approx(o.I_in + o.I_out)
    assert o.V_bus == 10.0 and o.loop == "series"


def test_4switch_buck_boost_by_region():
    # the sstv badge's TPS63001: 3.7 V -> 3.3 V is its buck region; the output leg is static
    bk = CV.operating("buck_boost_4switch", 3.7, 3.3, 0.8, 0.9, leg="buck")
    bo = CV.operating("buck_boost_4switch", 3.7, 3.3, 0.8, 0.9, leg="boost")
    assert bk.mode == bo.mode == "buck"
    assert bk.I_sw == 0.8 and bk.D == pytest.approx(3.3 / 3.7)
    assert bo.I_sw == 0.0 and bo.loop == "none"
    # 2.5 V -> 3.3 V: boost region, the input leg is static, the output leg carries the input current
    bk = CV.operating("buck_boost_4switch", 2.5, 3.3, 0.8, 0.9, leg="buck")
    bo = CV.operating("buck_boost_4switch", 2.5, 3.3, 0.8, 0.9, leg="boost")
    assert bk.I_sw == 0.0 and bo.I_sw == pytest.approx(0.8 * 3.3 / (2.5 * 0.9))
    # between, both legs switch at the inductor current
    a = CV.operating("buck_boost_4switch", 3.3, 3.3, 0.8, 0.9, leg="buck")
    b = CV.operating("buck_boost_4switch", 3.3, 3.3, 0.8, 0.9, leg="boost")
    assert a.mode == "buck_boost" and a.I_sw == b.I_sw == pytest.approx(0.8 / 0.9)


def test_sepic_switch_carries_both_inductors():
    o = CV.operating("sepic", 3.3, 5.0, 0.5, 0.9)
    assert o.D == pytest.approx(5.0 / (3.3 * 0.9 + 5.0))
    assert o.I_sw == pytest.approx(0.5 * 5.0 / (3.3 * 0.9) + 0.5)


def test_intent_override_and_legacy_current():
    assert CV.from_intent({"I_switch_A": 2.0, "I_out_A": 1.0, "V_in_V": 3.7, "V_out_V": 5}, "boost").I == (2.0, 2.0, 2.0)
    assert CV.from_intent({"I_A": [0.3, 1.0]}, "boost").source == "intent"
    cc = CV.from_intent({"I_out_A": 1.0}, "boost")                       # no voltages: kept, and said so
    assert cc.I == (1.0, 1.0, 1.0) and "not converted" in cc.basis


def _boost_cell(intent):
    brief = {"structures": [{"id": "cell:boost:U1", "class": "boost", "vin": "VBAT", "rail": "+5V", "vout": "+5V"}],
             "nets": {"VBAT": {"volts": 3.7}, "+5V": {"volts": 5.0}}}
    s = SimpleNamespace(meta={"cell": "cell:boost:U1", "cls": "boost", "bus": "+5V"}, name="cell:boost:U1")
    L = Ledger()
    return PA.cell(L, s, brief, None, intent, ""), s


def test_a_boost_cells_hot_loop_loss_against_a_hand_estimate():
    """The adafruit powerboost 500c's boost (3.7 V -> 5 V, 1 A): the ledger's commutated current is the input
    current, and the hot loop's 1/2 L I^2 f_sw (kae.excite.evaluate's loss.loop) at a 2 nH loop and 500 kHz is
    the hand estimate at I_in, 2.3 x what the output current gives."""
    intent = {"cells": {"cell:boost:U1": {"I_out_A": 1.0, "V_in_V": 3.7, "V_out_V": 5.0, "eta": 0.9, "f_sw_Hz": 500e3}}}
    P, s = _boost_cell(intent)
    I_in = 1.0 * 5.0 / (3.7 * 0.9)
    assert P["I"].typ == pytest.approx(I_in) and P["I"].source == "physics"
    assert P["D"].typ == pytest.approx(1 - 3.7 * 0.9 / 5.0)
    val = {k[1]: v for k, v in corners(P.values(), n=4)[0].items()}       # the typical point, as evaluate reads it
    L_loop = 2e-9
    loss = 0.5 * L_loop * val["I_A"] ** 2 * val["f_sw_Hz"]
    assert loss == pytest.approx(0.5 * 2e-9 * I_in ** 2 * 500e3)         # 1.13 mW
    assert loss / (0.5 * 2e-9 * 1.0 ** 2 * 500e3) == pytest.approx((5.0 / 3.33) ** 2)
    assert s.meta["eta"] == 0.9


def test_a_boost_without_intent_takes_eta_into_its_duty():
    P, _ = _boost_cell({})
    assert P["D"].typ == pytest.approx(1 - 3.7 * CV.ETA[1] / 5.0)


def test_dc_input_current_of_a_boost_and_a_buck():
    """A boost draws more input current than it delivers, I_out V_out / (V_in eta); a buck draws D I_out / eta."""
    pl = DC.Plan()
    pl.grounds = {"GND"}
    pl.pads = {"J1": [("1", "VBAT", "", ""), ("2", "GND", "", "")],
               "U3": [("1", "SW", "", "SW"), ("2", "GND", "", "GND"), ("3", "VBAT", "power_in", "VIN")],
               "J2": [("1", "5V", "", ""), ("2", "GND", "", "")]}
    pl.volts = {"VBAT": 3.7, "5V": 5.0}
    D = CV.duty("boost", 3.7, 5.0, 0.9)
    cell = dict(id="c", cls="boost", top="boost", eta=0.9, src="cell:c", vin="VBAT", vout="5V", sw="SW", ctrl="U3",
                rect="D1", parts=set())
    pl.feeds = {"VBAT": dict(kind="external", ref="J1", out=["J1.1"], gnd=["J1.2"]),
                "5V": dict(kind="cell", cell=cell, ref="U3")}
    pl.loads = [dict(ref="J2", rail="5V", sup=["J2.1"], gnd=["J2.2"], key=("dc:J2", "I_A"))]
    inj = DC.injections(pl, {("dc:J2", "I_A"): 1.0, "cell:c": {"I_A": 1.5, "D": D}})
    assert inj["J1.1"] == pytest.approx(5.0 / (3.7 * 0.9))               # 1.50 A in for 1 A out
    assert sum(inj.values()) == pytest.approx(0.0, abs=1e-12)
    # the same rail from a buck: 12 V -> 5 V at 1 A draws 5 / (12 x 0.9) A
    pl.volts = {"VBAT": 12.0, "5V": 5.0}
    pl.pads["U3"].append(("4", "5V", "", "VOUT"))
    cell.update(cls="buck", top="buck")
    inj = DC.injections(pl, {("dc:J2", "I_A"): 1.0, "cell:c": {"I_A": 1.0, "D": 5.0 / 12.0}})
    assert inj["J1.1"] == pytest.approx(5.0 / (12.0 * 0.9))
    assert sum(inj.values()) == pytest.approx(0.0, abs=1e-12)


def test_turnoff_current_is_the_inductor_peak_and_dcm_caps_it():
    assert CV.turnoff_current(1.5015, 0.2191) == pytest.approx(1.5015 + 0.2191 / 2)
    assert CV.turnoff_current(0.1, 0.5) == pytest.approx(0.2)        # DCM boundary: dI capped at 2 I_L
    assert CV.turnoff_current(1.0, None) == 1.0                       # inductor unknown: the average


def test_overshoot_edge_term_at_the_turnoff_current():
    from kae.excite import harm as HA
    v, vf, ve = HA.peak(0.01, 1e-9, 1.0, 0.5, 2e-9, I_off=1.2)
    assert ve == pytest.approx(1e-9 * 1.2 / 2e-9) and vf == pytest.approx(0.01 * 2 / 3.141592653589793 * 1.0)
