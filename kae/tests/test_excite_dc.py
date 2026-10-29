# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""kae.excite.dc: the DC power flow balances on every island, and its heating law is IPC-2221's."""
import pytest

from kae.excite import dc as DC
from kae.route.critical_physics import ipc2221_width


def test_heating_inverts_the_ipc2221_width():
    for I, dT, internal in [(0.5, 10.0, False), (2.0, 20.0, True), (5.0, 5.0, False)]:
        w = ipc2221_width(I, dT, 0.035, internal=internal)
        assert DC.ipc_dT(I, w, 0.035, external=not internal) == pytest.approx(dT, rel=1e-9)


def _plan(rect="D1"):
    """USB (J1) -> VBUS; LDO U1 VBUS -> 3V3 with load U2; boost cell (controller U3, inductor L1,
    rectifier D1) VBUS -> 5V with load J2."""
    pl = DC.Plan()
    g = {"GND"}
    pl.grounds = g
    pl.pads = {
        "J1": [("1", "VBUS", "", ""), ("2", "GND", "", "")],
        "U1": [("1", "VBUS", "power_in", "VIN"), ("2", "3V3", "power_out", "VOUT"), ("3", "GND", "", "GND")],
        "U2": [("1", "3V3", "power_in", "VDD"), ("2", "GND", "", "GND")],
        "U3": [("1", "SW", "", "SW"), ("2", "GND", "", "GND"), ("3", "VBUS", "power_in", "VIN"), ("4", "5V", "", "VOUT")],
        "J2": [("1", "5V", "", ""), ("2", "GND", "", "")],
    }
    pl.volts = {"VBUS": 5.0, "3V3": 3.3, "5V": 12.0}
    cell = dict(id="c", cls="boost", src="cell:c", vin="VBUS", vout="5V", sw="SW", ctrl="U3", rect=rect, parts=set())
    pl.feeds = {"VBUS": dict(kind="external", ref="J1", out=["J1.1"], gnd=["J1.2"], rating=3.0),
                "3V3": dict(kind="linear", ref="U1", rin="VBUS", out=["U1.2"], inp=["U1.1"], gnd=["U1.3"], rating=0.5),
                "5V": dict(kind="cell", cell=cell, ref="U3")}
    pl.loads = [dict(ref="U2", rail="3V3", sup=["U2.1"], gnd=["U2.2"], key=("dc:U2", "I_A")),
                dict(ref="J2", rail="5V", sup=["J2.1"], gnd=["J2.2"], share=1.0, cell=cell)]
    return pl


def _net_sums(pl, inj, lumped):
    """Net injection per group of nets joined by DC-conducting parts (`lumped`: sets of nets)."""
    net_of = {f"{r}.{n}": net for r, pp in pl.pads.items() for n, net, _, _ in pp}
    sums = {}
    for t, a in inj.items():
        net = net_of[t]
        grp = next((frozenset(s) for s in lumped if net in s), frozenset([net]))
        sums[grp] = sums.get(grp, 0.0) + a
    return sums


def test_power_flow_balances_through_ldo_and_boost():
    pl = _plan()
    cv = {("dc:U2", "I_A"): 0.2, "cell:c": {"I_A": 1.0, "D": 0.6}}
    inj = DC.injections(pl, cv)
    # the inductor (VBUS-SW) and the rectifier (SW-5V) conduct: one island with the rails they join
    sums = _net_sums(pl, inj, [{"VBUS", "SW", "5V"}])
    assert all(abs(v) < 1e-12 for v in sums.values()), sums
    assert sum(inj.values()) == pytest.approx(0.0, abs=1e-12)
    # the boost's input is its inductor current, I_out / (1 - D); the source delivers that plus the LDO's
    I_out = 1.0 * (1 - 0.6)
    assert inj["J1.1"] == pytest.approx(I_out / (1 - 0.6) + 0.2)
    assert inj["U3.1"] == pytest.approx(-0.6 * 1.0)          # the switch: D I_L from the switch node
    assert inj["J2.1"] == pytest.approx(-I_out)


def test_synchronous_boost_balances_and_the_ldo_rating_caps_its_load():
    pl = _plan(rect=None)
    cv = {("dc:U2", "I_A"): 2.0, "cell:c": {"I_A": 1.0, "D": 0.3}}
    inj = DC.injections(pl, cv)
    sums = _net_sums(pl, inj, [{"VBUS", "SW"}])
    assert all(abs(v) < 1e-12 for v in sums.values()), sums
    assert inj["U2.1"] == pytest.approx(-0.5)                # the LDO delivers at most its 0.5 A rating
