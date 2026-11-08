# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""intent_from_spec: a board's radios come from its parts as well as its spec, their EMI terms price noise into the
radio (not the radio's own noise into other parts), a radio board's cables default to 1 m, and the schematic's pin
facts ride along in the operating facts."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import intent_from_spec as I  # noqa: E402

SUMMARY = {"parts": [{"ref": "U1", "kind": "module", "value": "ESP32-WROOM-32E", "lib_id": "RF_Module:ESP32-WROOM-32",
                      "nets": {"+3V3": 2, "GND": 3}},
                     {"ref": "J1", "kind": "connector", "role": "connector_usb", "value": "USB_C", "lib_id": "",
                      "nets": {"VBUS": 2, "GND": 2}},
                     {"ref": "J2", "kind": "connector", "role": "connector_header", "value": "Conn_01x04", "lib_id": "",
                      "nets": {"+3V3": 1, "GND": 1}}],
           "rails": {"+3V3": {}, "VBUS": {}}, "ground_nets": ["GND"], "sections": []}


def test_a_radio_the_spec_missed_still_gets_emi_terms_scoped_to_its_own_pins():
    spec = {"schema": "kae.board-spec/1", "rails": [], "loads": [], "radio": [], "connectors": []}
    it, op = I.compile_spec(spec, SUMMARY)
    e = {t["id"]: t for t in it["terms"] if t["id"].startswith("E")}
    assert e["E1"]["where"] == {"to_part": ["U1"]} and e["E2"]["where"] == {"to_part": ["U1"]}
    # no cable lengths stated: the USB connector takes CISPR 32's 1 m, the header (a board-to-board mate) none
    assert it["environment"]["cables"] == [dict(connector="J1", length_m=1.0, why=it["environment"]["cables"][0]["why"])]
    assert e["E3"]["obs"] == "emission.cable_E"
    assert "radio.U1" in op["provenance"]["why"]


def test_stated_cables_win_and_a_board_without_a_radio_reports_emission_only():
    spec = {"schema": "kae.board-spec/1", "rails": [], "loads": [], "radio": [{"ref": "U1", "kind": "Wi-Fi"}],
            "connectors": [{"ref": "J2", "cable_length_m": 0.3}]}
    it, _ = I.compile_spec(spec, SUMMARY)
    assert [c["connector"] for c in it["environment"]["cables"]] == ["J2"]
    quiet = dict(SUMMARY, parts=SUMMARY["parts"][1:])
    it, _ = I.compile_spec({"schema": "kae.board-spec/1", "rails": [], "loads": []}, quiet)
    assert [t["tier"] for t in it["terms"] if t["id"].startswith("E")] == ["report"]


def test_pin_facts_ride_in_the_operating_facts(tmp_path):
    spec, summ, pt = tmp_path / "s.json", tmp_path / "m.json", tmp_path / "p.json"
    spec.write_text(json.dumps({"schema": "kae.board-spec/1", "rails": [], "loads": []}))
    summ.write_text(json.dumps(SUMMARY))
    pt.write_text(json.dumps({"schema": "kaeres.pintypes/1", "refs": {"U1": {"2": {"type": "power_in", "name": "3V3"}}}}))
    I.main([str(spec), str(summ), "--intent", str(tmp_path / "i.json"), "--operating", str(tmp_path / "o.json"),
            "--pintypes", str(pt)])
    op = json.loads((tmp_path / "o.json").read_text())
    assert op["pins"] == {"U1": {"2": ["power_in", "3V3"]}}
