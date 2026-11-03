# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""kae.board_hazards: the recheck with forced severities, and static project hazards."""
import json
from pathlib import Path

import pytest

from kae import board_hazards as B
from kae import hazards as H
from kae.board.model import NetClass, Rules

TWO_PADS = Path(__file__).parents[2] / "bench" / "tests" / "fixtures" / "two_pads.kicad_pcb"


def _project(tmp_path, sev, name="board"):
    p = tmp_path / f"{name}.kicad_pro"
    p.write_text(json.dumps(dict(board=dict(design_settings=dict(rule_severities=sev)))))
    return tmp_path / f"{name}.kicad_pcb"


def test_downgraded_and_forced_project():
    sev = dict(shorting_items="ignore", courtyards_overlap="warning", hole_to_hole="warning",
               silk_over_copper="ignore", clearance="error")
    d = B.downgraded(sev)
    assert d["shorting_items"] == ("ignore", "error")
    assert "courtyards_overlap" in d                     # warn class, KiCad default error
    assert "hole_to_hole" not in d                       # KiCad ships it as warning
    assert d["silk_over_copper"] == ("ignore", "warning")
    pro = B.forced_project(dict(board=dict(design_settings=dict(rule_severities=sev)), meta=dict(version=3)))
    s = pro["board"]["design_settings"]["rule_severities"]
    assert s["shorting_items"] == "error" and s["silk_over_copper"] == "warning" and s["hole_to_hole"] == "warning"
    assert pro["meta"] == dict(version=3)
    assert sev["shorting_items"] == "ignore"             # the input is not modified


def test_drc_hazards_groups_by_type():
    rep = dict(violations=[
        dict(type="shorting_items", severity="error", description="Items shorting two nets",
             items=[dict(description="Pad 2 [N2] of R2 on F.Cu", pos=dict(x=120.8, y=105)),
                    dict(description="Track [N1] on F.Cu, length 2 mm", pos=dict(x=120, y=106))]),
        dict(type="shorting_items", severity="error", description="Items shorting two nets",
             items=[dict(description="Via [GND] on F.Cu - B.Cu")]),
        dict(type="courtyards_overlap", severity="warning", description="Courtyards overlap",
             items=[dict(description="Footprint U1"), dict(description="Footprint C3")]),
        dict(type="lib_footprint_issues", severity="warning", description="lib", items=[]),
        dict(type="clearance", severity="error", excluded=True, description="excluded", items=[])],
        unconnected_items=[dict(items=[dict(description="Pad 1 [N1] of R1")])], unconnected_count=5)
    hz = {h["code"]: h for h in B.drc_hazards(rep, dict(shorting_items="ignore"))}
    assert set(hz) == {"drc_shorting_items", "drc_courtyards_overlap", "drc_unconnected_items"}
    s = hz["drc_shorting_items"]
    assert s["severity"] == "block" and s["evidence"]["count"] == 2 and s["evidence"]["hidden_by_project"]
    assert s["objects"] == ["R2", "N2", "N1", "GND"]
    assert hz["drc_courtyards_overlap"]["severity"] == "warn" and hz["drc_courtyards_overlap"]["objects"] == ["U1", "C3"]
    assert hz["drc_unconnected_items"]["evidence"]["count"] == 5


def test_ipc2221b_table():
    assert B.ipc2221b_spacing(12) == 0.1
    assert B.ipc2221b_spacing(48) == 0.6
    assert B.ipc2221b_spacing(400) == 2.5 and B.ipc2221b_spacing(400, external=False) == 0.25
    assert B.ipc2221b_spacing(1000) == pytest.approx(5.0)


def test_voltage_and_fab_floor_hazards():
    rules = Rules(clearance=0.05, track_min=0.2, netclasses=dict(Default=NetClass("Default", clearance=0.2),
                                                                  HV=NetClass("HV", clearance=3.0)))
    board = type("Bd", (), dict(rules=rules, nets=dict(VIN=type("N", (), dict(netclass="Default")),
                                                       MAINS=type("N", (), dict(netclass="HV")))))()
    brief = dict(nets=dict(VIN=dict(volts=48.0), MAINS=dict(volts=340.0), V3=dict(volts=3.3), X=dict(volts=None)))
    hz = B._voltage_hazards(rules, brief, board)
    assert [h["code"] for h in hz] == ["hv_clearance_below_ipc"] and hz[0]["objects"][0] == "VIN"
    assert hz[0]["evidence"]["ipc2221b_b2_mm"] == 0.6
    rules.custom = [dict(name="hv", condition="A.NetName == 'VIN'", constraints=[dict(type="clearance", min=0.8)])]
    assert B._voltage_hazards(rules, brief, board) == []
    ff = B._fab_floor_hazards(rules)
    assert [h["objects"] for h in ff] == [["clearance"]]


def test_static_hazards_from_project(tmp_path):
    pcb = _project(tmp_path, dict(shorting_items="ignore", clearance="warning"))
    (tmp_path / "board.kicad_dru").write_text('(version 1)\n(rule "w"\n (severity ignore)\n'
                                               ' (constraint clearance (min 0.1mm))\n (condition "A.NetName == \'X\'"))\n')
    pcb.write_text(TWO_PADS.read_text())
    codes = sorted((h["code"], tuple(h["objects"])) for h in B.static_hazards(pcb))
    assert ("drc_check_downgraded", ("shorting_items",)) in codes
    assert ("drc_check_downgraded", ("clearance",)) in codes
    assert ("dru_rule_downgraded", ("w",)) in codes


def test_recheck_without_kicad(monkeypatch, tmp_path):
    from kae.route import drc

    def none():
        raise drc.DrcError("kicad-cli not found")
    monkeypatch.setattr(drc, "kicad_cli", none)
    hz, meta = B.recheck(tmp_path / "x.kicad_pcb")
    assert [h["code"] for h in hz] == ["recheck_unavailable"] and not meta["ran"]


def _has_kicad():
    from kae.route import drc
    try:
        drc.kicad_cli()
        return True
    except drc.DrcError:
        return False


@pytest.mark.kicad
@pytest.mark.skipif(not _has_kicad(), reason="no kicad-cli")
def test_ignored_short_is_a_block_hazard(tmp_path):
    """A track of N1 runs onto R2's N2 pad; the project ignores shorting_items. KiCad's own DRC
    then reports no short (it reports none of an ignored check's violations, even with
    --severity-all); the recheck reports it as a block hazard."""
    from kae.route import drc
    text = TWO_PADS.read_text().rstrip()
    assert text.endswith(")")
    text = text[:-1] + ('\t(segment (start 119.2 107) (end 120.8 105.2) (width 0.25) (layer "F.Cu") (net 1) '
                        '(uuid "55555555-5555-5555-5555-555555555551"))\n)\n')
    pcb = _project(tmp_path, dict(shorting_items="ignore", clearance="ignore"))
    pcb.write_text(text)
    own = drc.run(pcb, tmp_path / "own.json", timeout=300)
    assert not [v for v in own["violations"] if v["type"] in ("shorting_items", "clearance")]
    assert "shorting_items" in {c["key"] for c in own.get("ignored_checks") or []}
    hz, meta = B.board_hazards(pcb)
    assert meta["ran"] and "shorting_items" in meta["forced"]
    rep = H.finalize(dict(hazards=hz))
    short = next(h for h in rep["hazards"] if h["code"] == "drc_shorting_items")
    assert short["severity"] == "block" and short["evidence"]["hidden_by_project"]
    assert {"N1", "N2"} <= set(short["objects"])
    assert rep["hazard_summary"]["blocked"]
    assert json.loads(pcb.with_suffix(".kicad_pro").read_text())["board"]["design_settings"]["rule_severities"][
        "shorting_items"] == "ignore"                 # the project itself is untouched
