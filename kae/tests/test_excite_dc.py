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


def test_ics_on_boards_without_pin_data_draw_from_their_rails():
    """A pad typed power_in or named as a supply draws; on a board whose pads carry neither name nor
    type (an Eagle or KiCad 5 import), a pad on a rail or a supply-named net draws; a pad typed or
    named otherwise, or on a signal net, does not."""
    rails = {"VBAT", "+3V3"}
    assert DC.draws_from([("1", "+3V3", "power_in", "")], "+3V3", rails)
    assert DC.draws_from([("2", "+3V3", "passive", "3V3")], "+3V3", rails)           # named by its voltage
    assert DC.draws_from([("1", "VBAT", "", ""), ("2", "GND", "", "")], "VBAT", rails)  # unannotated, on a rail
    assert DC.draws_from([("1", "VCC_IO", "", "")], "VCC_IO", set())                 # unannotated, supply name
    assert not DC.draws_from([("1", "+3V3", "input", "EN")], "+3V3", rails)          # an enable tied high
    assert not DC.draws_from([("1", "+3V3", "power_out", "3V3")], "+3V3", rails)     # its output, not a draw
    assert not DC.draws_from([("1", "PWRSTAT", "", "")], "PWRSTAT", set())           # a status line
    assert not DC.draws_from([("1", "VBAT", "", "")], "+3V3", rails)                 # no pad on that rail


def test_a_charger_drawing_from_a_rail_is_not_heated_by_what_it_passes_on():
    """An MCU's draw is its heat; a charger's or regulator's draw goes on to a battery or another
    rail, so it adds no V*I heat as a load (its own loss is a feed's conversion loss)."""
    from types import SimpleNamespace
    from kae.excite import heat as HT
    pl = DC.Plan()
    pl.loads = [dict(ref="U1", rail="VBUS", key=("dc:U1@VBUS", "I_A")), dict(ref="U2", rail="VBUS", key=("dc:U2@VBUS", "I_A"))]
    pl.volts = {"VBUS": 5.0}
    bd = SimpleNamespace(part_kind={"U1": ("ic", "mcu", "mcu"), "U2": ("ic", "charger", "charger")})
    heat = HT.part_heat(bd, pl, {("dc:U1@VBUS", "I_A"): 0.1, ("dc:U2@VBUS", "I_A"): 0.5}, {}, {})
    assert heat == {"U1": pytest.approx(0.5)}


def test_a_rails_demand_follows_its_loads_through_regulators():
    """What a converter's output must deliver: its loads, plus an LDO's load passed through it."""
    from kae.excite import heat as HT
    pl = DC.Plan()
    pl.volts = {"VIN": 12.0, "5V": 5.0, "3V3": 3.3}
    pl.feeds = {"5V": dict(kind="cell", ref="U1", cell=dict(src="cell:c", cls="buck", vin="VIN", vout="5V")),
                "3V3": dict(kind="linear", ref="U2", rin="5V")}
    pl.loads = [dict(ref="U3", rail="5V", key=("dc:U3@5V", "I_A")), dict(ref="U4", rail="3V3", key=("dc:U4@3V3", "I_A"))]
    amps = {("dc:U3@5V", "I_A"): 0.2, ("dc:U4@3V3", "I_A"): 0.05}
    assert HT.rail_demand(pl, "5V", lambda ld: amps[ld["key"]]) == pytest.approx(0.25)
    # the 12 V input carries the buck's output power over 88% efficiency
    assert HT.rail_demand(pl, "VIN", lambda ld: amps[ld["key"]]) == pytest.approx(0.25 * 5 / (0.88 * 12))


def test_part_patterns_match_from_a_word_boundary_and_the_most_specific_wins():
    from kae.excite.beliefs import best_match, match_rank
    assert match_rank("(?i)(ComputeModule5|CM5)", "PCM5102 Package_SO:TSSOP-20") is None
    assert match_rank("(?i)(ComputeModule5|CM5)", "ComputeModule5-CM5") is not None
    entries = [("3.3", r"(?i)^AP2112"), ("1.8", r"(?i)^AP2112K?-?1\.8")]
    assert best_match(entries, lambda e: e[1], "AP2112K-1.8 Package_TO_SOT_SMD:SOT-23-5", "AP2112K-1.8")[0] == "1.8"
    assert best_match(entries, lambda e: e[1], "AP2112K-3.3", "AP2112K-3.3")[0] == "3.3"


def test_heat_accounts_every_dc_loss_vias_and_lumped_parts():
    """The thermal band's heat is the DC flow's whole I^2 R: bars, via barrels (half to each landing)
    and the lumped parts' own loss (an inductor's winding, a ferrite, a shunt) at their pads. Vias
    and lumped branches were left out (a buck inductor's DCR loss never heated its neighbours)."""
    import numpy as np

    from kae.em import solve as ES
    from kae.em.mesh import Layer, Mesh
    from kae.excite import heat as H
    m = Mesh.over(0, 0, 10, 1, 0.25, [Layer("F", 1.6, 0.035, 1), Layer("B", 0, 0.035, 1)])
    m.rect(0, "A", 0, 0, 4.5, 1)
    m.rect(1, "B", 5.5, 0, 10, 1)
    m.rect(0, "B", 8.5, 0, 10, 1)
    m.via(9.0, 0.5, [0, 1], "B", drill=0.3)
    X, _ = m.centres()
    m.terminal("a", 0, mask=X < 0.25)
    m.terminal("m1", 0, mask=(X > 4.25) & (X < 4.5))
    m.terminal("m2", 1, mask=(X > 5.5) & (X < 5.75))
    m.terminal("b", 0, mask=X > 9.75)
    m.part("m1", "m2", R=0.05, name="L1")
    net = ES.Network(m)
    assert len(net.vseg) == 1 and len(net.lump) == 1
    (V, info), = ES.potentials_many(m, [{"a": 2.0, "b": -2.0}], 0.0, net=net)
    P = 2.0 * float(np.real(V["a"] - V["b"]))
    Q = H.copper_heat(info["net"], info["x"], m.lab.shape)
    lump = H.lumped_heat(info["net"], info["x"], {"L1": "L"})
    assert lump["L1"] > 0.19                                  # 2 A through 50 mOhm
    assert Q.sum() + sum(lump.values()) == pytest.approx(P, rel=1e-3)
    assert H.lumped_heat(info["net"], info["x"], {"L1": "D_on"}) == {}     # a diode's loss is V_f I in part_heat


def test_copper_loss_budget_and_drop_share_the_unknown_rail_fallback():
    """With no rail voltage known, the loss budget was 0 and the loss u 0 (perfect) whatever the copper
    lost; it now takes the drop check's 3.3 V. A negative drop is no credit (phi clamps at 0)."""
    from types import SimpleNamespace

    import numpy as np

    from kae.excite import harm as HA
    pl = _plan()
    pl.volts = {}
    pl.loss_share, pl.drop_share, pl.dT_max = DC.LOSS_SHARE, DC.DROP_SHARE, DC.DT_MAX
    cv = {("dc:U2", "I_A"): 0.2, "cell:c": {"I_A": 1.0, "D": 0.6}}
    inj = DC.injections(pl, cv)
    V = {t: (0.01 if a > 0 else 0.0) for t, a in inj.items()}          # 10 mV across the copper per source
    info = dict(net=SimpleNamespace(off={"l": 0}, n_br=0), x=np.zeros(0), sys=SimpleNamespace(zdiag=np.zeros(0)))
    u, P_cu, budget = DC.observe(pl, cv, V, info)["loss"]
    assert P_cu > 0 and budget > 0 and u == pytest.approx(P_cu / budget)
    assert HA.phi(-0.5) == 0.0 and HA.phi(0.5) == 0.5


def test_dc_currents_left_out_of_the_copper_void_the_score():
    """Load and source currents at pads outside the copper model were dropped with a note while the
    total stayed 'complete'; that note now voids the DC band (evaluate/wideband mark it uncomputed)."""
    from types import SimpleNamespace

    from kae.excite import evaluate as E
    pl = _plan()
    pl.params = []
    notes = []
    bm = SimpleNamespace(m=SimpleNamespace(terminals={}))
    b = SimpleNamespace(footprints=[], tracks=[])
    assert E._dc_harms(pl, bm, b, None, None, {}, [], 1, 0, [0.0] * 4, notes, lambda *a: None) == []
    assert any(n.startswith(E.DC_VOID) for n in notes)
    assert E.totals([0.0] * 4, ["dc"])["complete"] is False


def test_a_dc_band_that_solves_nothing_builds_no_system():
    """The DC system the DC and heat bands share is built on first use: a band with nothing to solve builds
    none (eagerly built, it failed on boards whose DC network has no components)."""
    from types import SimpleNamespace

    from kae.excite import evaluate as E
    pl = _plan()
    pl.params = []
    holder = {}
    bm = SimpleNamespace(m=SimpleNamespace(terminals={}))
    b = SimpleNamespace(footprints=[], tracks=[])
    E._dc_harms(pl, bm, b, None, None, {}, [], 1, 0, [0.0] * 4, [], lambda *a: None, system=holder)
    assert holder == {}
