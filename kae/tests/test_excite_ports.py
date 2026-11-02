# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Ports (kae.excite.models): a signal or supply arriving from off the board is driven at its connector
(or module) pin and returns through that part's ground pins; a rail with nothing on it stays dangling."""
from types import SimpleNamespace as NS

from kae.excite import models as M
from kae.excite.circuit import Circuit
from kae.excite.evaluate import NO_COPPER
from kae.excite.sources import clock_driver


def _part(value="", lib_id=""):
    return NS(value=value, lib_id=lib_id)


def test_a_jp_header_and_an_unclassified_socket_are_connectors_and_a_solder_jumper_is_not():
    assert M.port_kind("jumper", _part("", "1X07_ROUND_76"), 7) == "connector"
    assert M.port_kind("unknown", _part("EINK_24PIN_CONNECTOR_TOPCONTACT", "EINK_24PIN_TOPCONTACT"), 26) == "connector"
    assert M.port_kind("unknown", _part("SIM_LOCKAMPHENOL", "C707_10M006_512_2"), 6) == "connector"
    assert M.port_kind("jumper", _part("", "SOLDERJUMPER_2WAY_OPEN_NOPASTE"), 3) is None
    assert M.port_kind("module", _part("ESP32-S2"), 63) == "module"
    assert M.port_kind("ic", _part("MAX98357A", "QFN16_3MM"), 17) is None
    assert M.port_kind("unknown", _part("XYZ", "SOT23-6"), 6) is None


def _board(extra=()):
    """U1 (logic) on VIO and GND; VIO also reaches header J1.1, ground J1.2 (and the parts in extra)."""
    bd = M.Board(Circuit("GND"), "GND", {"GND"}, {"VIO": 3.3}, {}, {}, {})
    pins = [NS(net="GND", number="1", ptype="power_in", fn="GND"), NS(net="VIO", number="2", ptype="power_in", fn="VCC")]
    toks = {"U1.1": "GND", "U1.2": "VIO", "J1.1": "VIO", "J1.2": "GND", **dict(extra)}
    for t, n in toks.items():
        bd.net_of[t] = n
        bd.pads_of.setdefault(n, []).append(t)
    bd.part_kind.update({"U1": ("ic", "logic", ""), "J1": ("connector", None, "")})
    bd.port["J1"] = "connector"
    bd.pad_xy.update({"J1.1": (0.0, 0.0), "J1.2": (2.54, 0.0)})
    M._ic(bd, "U1", None, pins, "logic", "")
    return bd


def _core_ja(bd, f=50e6):
    s = bd.circuit.src("core", bd.ic_nodes["U1"]["VIO"], bd.ic_nodes["U1"]["g"])
    return bd.circuit.solve(f, [s])["core"]["Ja"]


def test_a_rail_fed_only_by_a_connector_takes_the_core_current_through_the_cable():
    bd = _board()
    assert all(abs(j) < NO_COPPER for j in _core_ja(_board()).values())       # unmodelled: nothing reaches copper
    M._port_supplies(bd)
    (e,) = [e for e in bd.circuit.elems if e.kind == "port"]
    assert (e.a, e.b, e.pa, e.pb) == ("VIO", "GND", "J1.1", "J1.2")
    ja = _core_ja(bd)
    # the copper carries the current from U1's supply pin to the header and back from its ground pin
    assert abs(ja["U1.2"]) > 0.05 and abs(ja["U1.2"] + ja["U1.1"]) < 1e-6
    assert "J1.1" not in ja                              # the cable is lumped into the copper with the pads it joins


def test_a_rail_with_a_capacitor_on_the_board_keeps_its_model():
    bd = _board([("C1.1", "VIO"), ("C1.2", "GND")])
    bd.circuit.z("C1", "VIO", "GND", M._rlc(0.01, 0.5e-9, 1e-7), "C1.1", "C1.2", "C")
    n = len(bd.circuit.elems)
    M._port_supplies(bd)
    assert len(bd.circuit.elems) == n


def test_a_module_drives_a_clock_before_a_connector_and_an_untyped_ic_pin():
    bd = NS(pads_of={"CLK": ["U1.16", "JP1.6", "U3.30"]}, pin_type={}, ic_nodes={"U1": {}},
            part_kind={"U1": ("ic", None, ""), "JP1": ("jumper", None, ""), "U3": ("module", None, "")},
            port={"JP1": "connector", "U3": "module"})
    assert clock_driver(bd, "CLK") == "U3.30"
    bd.pads_of["CLK"] = ["U1.16", "JP1.6"]
    assert clock_driver(bd, "CLK") == "JP1.6"            # the I2S clock arrives on the header, not at the amp's input
