# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""kae.excite.sources.clock_driver: who drives a clock net, from the schematic's pin types."""
from types import SimpleNamespace

from kae.excite.sources import clock_driver


def _bd(pins, kinds, ics=()):
    """pins: [(pad, pin type)] on net CLK; kinds: ref -> part kind."""
    return SimpleNamespace(pads_of={"CLK": [t for t, _ in pins]}, pin_type=dict(pins),
                           part_kind={r: (k, None, "") for r, k in kinds.items()}, ic_nodes={r: {} for r in ics})


def test_an_input_never_drives_and_a_connector_brings_the_clock_from_off_the_board():
    bd = _bd([("U1.H8", "input"), ("J1.173", "passive")], {"U1": "ic", "J1": "connector"}, ics=("U1",))
    assert clock_driver(bd, "CLK") == "J1.173"


def test_an_output_beats_a_bidirectional_pin_listed_first():
    bd = _bd([("U6.51", "bidirectional"), ("U8.1", "output")], {"U6": "ic", "U8": "ic"}, ics=("U6", "U8"))
    assert clock_driver(bd, "CLK") == "U8.1"


def test_only_inputs_have_no_driver():
    bd = _bd([("U1.3", "input"), ("U2.3", "input")], {"U1": "ic", "U2": "ic"}, ics=("U1", "U2"))
    assert clock_driver(bd, "CLK") is None
