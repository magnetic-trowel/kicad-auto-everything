# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""intent_from_spec: heat sinks and forced air in a board spec become operating facts, checked against the board."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import intent_from_spec as I  # noqa: E402

SUMMARY = {"parts": [{"ref": "U1", "kind": "ic", "value": "LM1117-5.0", "lib_id": "", "nets": {"+5V": 1, "+12V": 1, "GND": 1}}],
           "rails": {"+5V": {}, "+12V": {}}, "ground_nets": ["GND"], "sections": []}


def compile_thermal(thermal):
    spec = {"schema": "kae.board-spec/1", "purpose": "test", "rails": [], "loads": [], "thermal": thermal}
    intent, op = I.compile_spec(spec, SUMMARY)
    return op["requirements"].get("thermal") or {}, op["provenance"]["rejected"]


def test_heat_sinks_and_airflow_reach_the_operating_facts_and_bad_ones_are_rejected():
    th, rej = compile_thermal({"T_amb_C": [0, 40], "airflow_h_W_m2K": 40, "heatsinks": [
        {"part": "U1", "theta_sa_C_W": 25, "outline_mm": [20, 25], "height_mm": 12, "offset_mm": [0, 3],
         "basis": "typical", "why": "clip-on sink"},
        {"side": "bottom", "region": "board", "theta_C_W": 0.5, "T_C": 45, "why": "enclosure"},
        {"part": "U9", "theta_sa_C_W": 10},                       # not on the board
        {"part": "U1"},                                           # no theta, no sink datasheet
        {"side": "left", "region": "board", "theta_C_W": 1}]})    # not a face
    assert th["airflow_h_W_m2K"] == 40
    part, plate = th["heatsinks"]
    assert part["part"] == "U1" and part["theta_sa_C_W"] == 25
    assert part["outline_mm"] == [20, 25] and part["height_mm"] == 12 and part["offset_mm"] == [0, 3]
    assert plate == {"side": "bottom", "region": "board", "theta_C_W": 0.5, "T_C": 45,
                     "why": "heat sink (guess: enclosure)"}
    assert len(rej) == 3 and any("U9" in r for r in rej) and any("without theta_sa" in r for r in rej)


def test_assembly_process_is_recorded_with_the_boards_own_evidence():
    summary = dict(SUMMARY, parts=SUMMARY["parts"] + [{"ref": "U2", "kind": "ic", "value": "ESP32-C3",
                                                         "lib_id": "Package_DFN_QFN:QFN-32-1EP_5x5mm", "nets": {}}])
    spec = {"schema": "kae.board-spec/1", "rails": [], "loads": [], "assembly": {"process": "hand", "why": "a kit"}}
    _, op = I.compile_spec(spec, summary)
    a = op["requirements"]["assembly"]
    assert a["process"] == "hand" and a["reflow_only_parts"] == ["U2"]
    _, op = I.compile_spec(dict(spec, assembly={"process": "glue"}), summary)
    assert op["requirements"]["assembly"]["process"] == "unknown"
    assert any("assembly.process" in r for r in op["provenance"]["rejected"])
