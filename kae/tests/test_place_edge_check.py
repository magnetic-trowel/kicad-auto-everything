# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Edge connectors (audit P4): kinds, distance to the edge, the connector_off_edge hazard."""
import dataclasses
from pathlib import Path

from kae.board import kicad_file
from kae.place import edge_check

FIXTURE = Path(__file__).parent / "data" / "board" / "fixture.kicad_pcb"


def _with_j1(x, y, lib_id="Connector_USB:USB_C_Receptacle_GCT_USB4085", value="USB_C_Receptacle"):
    b = kicad_file.load(FIXTURE)
    fps = []
    for fp in b.footprints:
        if fp.ref == "J1":
            dx, dy = x - fp.x, y - fp.y
            pads = [dataclasses.replace(p, x=p.x + dx, y=p.y + dy) for p in fp.pads]
            fp = dataclasses.replace(fp, x=x, y=y, lib_id=lib_id, value=value, pads=pads)
        fps.append(fp)
    return dataclasses.replace(b, footprints=fps)


def test_kinds():
    b = _with_j1(30, 20)
    j1 = next(f for f in b.footprints if f.ref == "J1")
    assert edge_check.kind(j1) == "usb"
    assert edge_check.edge_parts(b) == {j1.uuid: ("J1", "usb")}
    h = _with_j1(30, 20, lib_id="Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical", value="Conn_01x02")
    assert edge_check.kind(next(f for f in h.footprints if f.ref == "J1")) is None   # headers: anywhere
    assert edge_check.edge_parts(h) == {}
    v = _with_j1(30, 20, lib_id="Connector_USB:USB_A_Molex_67643_Vertical", value="USB_A")
    assert edge_check.kind(next(f for f in v.footprints if f.ref == "J1")) is None   # top entry
    a = _with_j1(30, 20, lib_id="Connector_Audio:Jack_3.5mm_CUI_SJ1-3523N_Horizontal", value="AudioJack3")
    aj = next(f for f in a.footprints if f.ref == "J1")
    assert edge_check.kind(aj) == "audio" and "audio" not in edge_check.PIN_KINDS
    assert edge_check.edge_parts(a) == {aj.uuid: ("J1", "audio")}
    r = next(f for f in b.footprints if f.ref.startswith("R"))
    assert edge_check.kind(r) is None


def test_off_edge_is_a_hazard_and_on_edge_is_not():
    mid = edge_check.hazards(_with_j1(30, 20))      # the fixture board is 60 x 40 mm
    assert [h["code"] for h in mid] == ["connector_off_edge"]
    h = mid[0]
    assert h["severity"] == "warn" and h["category"] == "assembly" and h["objects"] == ["J1"]
    assert h["evidence"]["distance_mm"] > 10 and h["fix"]
    assert edge_check.hazards(_with_j1(1.5, 20)) == []
    # parts kae did not place are the user's choice
    assert edge_check.hazards(_with_j1(30, 20), moved=set()) == []


def test_place_report_hazard_follows_the_last_poses():
    """pipeline.edge_hazards judges the poses it is given and replaces its earlier entries (the
    KiCad loop moves parts after place() reported)."""
    from kae.place.pipeline import edge_hazards
    b = _with_j1(1.5, 20)
    j1 = next(f for f in b.footprints if f.ref == "J1")
    rep = {"hazards": [{"code": "other"}]}
    edge_hazards(rep, b, {j1.uuid: (30.0, 20.0, j1.rot, j1.side)})
    assert [h["code"] for h in rep["hazards"]] == ["other", "connector_off_edge"]
    edge_hazards(rep, b, {j1.uuid: (1.5, 20.0, j1.rot, j1.side)})
    assert [h["code"] for h in rep["hazards"]] == ["other"]


def test_place_pins_a_free_usb_jack_to_the_edge_and_the_switch_turns_it_off():
    from kae.place.pipeline import place
    b = _with_j1(30, 20)
    j1 = next(f for f in b.footprints if f.ref == "J1")
    res = place(b, seed=0, time_s=8, physics=False, workers=1)
    assert res.report["edge_pinned"]["pinned"] == ["J1"]
    assert edge_check.distance(j1, edge_check._outline(b), res.poses[j1.uuid]) <= edge_check.EDGE_TOL
    assert not [h for h in res.report.get("hazards", []) if h["code"] == "connector_off_edge"]
    off = place(_with_j1(30, 20), seed=0, time_s=8, physics=False, workers=1, opts=dict(connector_edge=0))
    assert "edge_pinned" not in off.report and not off.report.get("hazards")
