# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""intent_from_spec: a converter's operating facts (I_out_A, V_in_V, V_out_V, eta) from which the evaluator derives its
commutated current by topology (kae.physics.converter); I_switch_A, stated, overrides; per-field provenance rides along."""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import intent_from_spec as I  # noqa: E402

SUMMARY = {"parts": [{"ref": "U1", "kind": "ic", "value": "XYZ123", "lib_id": "", "nets": {"VIN": 1, "SW": 1, "GND": 1}}],
           "rails": {"VIN": {}, "+5V": {}}, "ground_nets": ["GND"],
           "sections": [{"id": "cell:boost:U1", "kind": "commutation_cell", "parts": ["U1"], "nets": ["SW", "+5V"]}]}


def conv(**kw):
    c = {"cell": "cell:boost:U1", "V_in_V": 3.7, "V_out_V": 5.0, "f_sw_Hz": 1e6, "I_out_A": 0.5, "basis": "datasheet",
         "why": "test"}
    c.update(kw)
    return {"schema": "kae.board-spec/1", "rails": [], "loads": [], "converters": [c]}


def test_switch_current_wins_over_output_current():
    _, op = I.compile_spec(conv(I_switch_A=0.75), SUMMARY)
    c = op["cells"]["cell:boost:U1"]
    assert c["I_switch_A"] == [0.225, 0.75] and "override" in op["provenance"]["why"]["cells.cell:boost:U1"]


def test_a_boost_states_its_operating_point_and_the_switch_current_is_derived():
    """Without I_switch_A the compiler writes the facts (I_out, V_in, V_out) and the derived switch current's
    provenance; the evaluator converts with the same module: a boost's switch carries I_out V_out / (V_in eta)."""
    from kae.physics import converter as CV
    _, op = I.compile_spec(conv(), SUMMARY)
    c = op["cells"]["cell:boost:U1"]
    assert "I_A" not in c and "I_switch_A" not in c
    assert c["I_out_A"] == [0.15, 0.5] and c["V_in_V"] == 3.7 and c["V_out_V"] == 5.0
    assert c["V_V"] == [4.5, 5.5]                         # the boost's bus is its output
    cc = CV.from_intent(c, "boost")
    assert cc.I[2] == pytest.approx(0.5 * 5.0 / (3.7 * 0.8))   # its upper end: I_out V_out / (V_in eta_lo)
    assert "derived" in op["provenance"]["why"]["cells.cell:boost:U1"]


def test_a_4switch_buck_boost_in_its_buck_region_leaves_the_boost_leg_static():
    sm = {"parts": [{"ref": "U5", "kind": "ic", "value": "TPS63001", "lib_id": "", "nets": {}}],
          "rails": {"VSYS": {}, "+3V3": {}}, "ground_nets": ["GND"],
          "sections": [{"id": "cell:buck:U5", "kind": "commutation_cell", "parts": ["C12", "L1", "U5"], "nets": ["VSYS", "A"]},
                       {"id": "cell:boost:U5", "kind": "commutation_cell", "parts": ["C14", "L1", "U5"], "nets": ["+3V3", "B"]}]}
    spec = {"converters": [dict(cell=f"cell:{k}:U5", V_in_V=3.7, V_out_V=3.3, f_sw_Hz=1.2e6, I_out_A=0.8, basis="datasheet",
                                why="t") for k in ("buck", "boost")]}
    _, op = I.compile_spec(spec, sm)
    assert op["cells"]["cell:boost:U5"]["V_V"] == [2.97, 3.63]   # the output leg's bus
    w = op["provenance"]["why"]
    assert "static" in w["cells.cell:boost:U5"] and "I_switch 0.24-0.8 A" in w["cells.cell:buck:U5"]


def test_field_bases_in_the_operating_provenance():
    _, op = I.compile_spec(conv(fields={"V_out_V": {"basis": "board", "why": "FB divider"},
                                        "I_out_A": {"basis": "guess", "why": "no load stated"}}), SUMMARY)
    w = op["provenance"]["why"]["cells.cell:boost:U1"]
    assert "V_out_V board" in w and "I_out_A guess" in w
