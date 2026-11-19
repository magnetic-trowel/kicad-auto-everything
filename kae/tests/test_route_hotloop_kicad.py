# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The hot-loop stage (kae.route.hotloop) against KiCad's DRC and through the whole bridge, on the
synthetic buck board of critical_fixtures (AP63203, C1, L1 on a two-layer board, ground on B.Cu);
skipped without KiCad (and Freerouting for the end-to-end test)."""
import pytest
from shapely.geometry import LineString, Polygon

import critical_fixtures as F
from kae.board import pcbnew_io
from kae.route import critical_write as W
from kae.route import drc, hotloop

pytestmark = [pytest.mark.kicad,
              pytest.mark.skipif(not pcbnew_io.available(), reason="no Python with pcbnew")]

ALL = dict(hotloop_keepout=1, hotloop_cells=1, hotloop_vias=1, hotloop_pours=1)


def _have_freerouting():
    try:
        from kae.route import freerouting
        freerouting.command()
        drc.kicad_cli()
        return True
    except Exception:
        return False


def test_stage_board_adds_no_drc_error(tmp_path):
    src = F.write_board(tmp_path / "in")
    base = drc.errors(drc.run(src, tmp_path / "base.json"))
    info = pcbnew_io.export_dsn(src, tmp_path / "b.dsn")
    rep = hotloop.stage(src, info, tmp_path / "w", ALL, log=lambda *a: None)
    assert rep["board"] and not rep.get("error")
    out = tmp_path / "out.kicad_pcb"
    W.edit(rep["board"], out, drop_guards=True)               # what the output carries: copper and pours
    for ext in (".kicad_pro",):
        (tmp_path / f"out{ext}").write_text((tmp_path / "in" / f"board{ext}").read_text())
    d = drc.run(out, tmp_path / "out.json")
    errs = drc.errors(d)
    mine = {r["uuid"] for r in W.routing(out) if r["locked"]}
    named = [v for v in errs if {i.get("uuid") for i in v.get("items", [])} & mine
             or any("kae-hl" in (i.get("description") or "") for i in v.get("items", []))]
    assert not named, [(v["type"], v["description"]) for v in named]
    assert len(errs) <= len(base), [v["type"] for v in errs]
    fills = pcbnew_io.zone_fills(out)["zones"]
    pours = [z for z in fills if (z.get("name") or "").startswith(hotloop.HL_PREFIX)]
    assert pours and all(z["layers"] for z in pours)          # the pours fill
    assert not [z for z in fills if (z.get("name") or "").startswith(hotloop.GUARD_PREFIX)]


@pytest.mark.skipif(not _have_freerouting(), reason="no Freerouting or kicad-cli")
def test_bridge_keeps_other_nets_off_the_return_plane_under_the_cell(tmp_path):
    from kae.route import bridge
    src = F.write_board(tmp_path / "in")
    out = tmp_path / "out" / "board.kicad_pcb"
    rep = bridge.route(src, out, time_s=240, workdir=tmp_path / "wd", opts=dict(rounds=1, **ALL), log=lambda *a: None)
    assert rep["status"] in ("routed", "no_session") and out.exists()
    assert rep["hotloop"]["board"] and rep["hotloop"]["cells"][0]["status"] == "routed"
    text = out.read_text()
    assert hotloop.GUARD_PREFIX not in text and hotloop.HL_PREFIX in text
    # no other net's track crosses the keep-out on the return layer, nor any of its vias
    guards = [g for g in (rep["hotloop"].get("keepout") or {}).get("cells") or []]
    assert guards and guards[0]["layer"] == "B.Cu"
    from kae.board.kicad_file import load
    region = None
    hl = hotloop.stage(src, pcbnew_io.export_dsn(src, tmp_path / "c.dsn"), tmp_path / "w2", ALL, log=lambda *a: None)
    region = Polygon(hl["guards"][0]["ring"]).buffer(-0.05)
    b = load(out)
    if rep["hotloop"].get("keepout_lifted"):
        return                                   # the cell's own pins needed the plane layer: no keep-out left
    # pins of the cell's parts whose corridor the escape round opened may cross it, in their corridor
    src_b = load(src)
    opened = {p.net for f in src_b.footprints for p in f.pads
              if f"{f.ref}.{p.number}" in (rep["hotloop"].get("escapes_opened") or [])}
    for t in b.tracks:
        if t.layer == "B.Cu" and t.net != "GND" and t.net not in opened:
            assert not LineString([t.start, t.end]).intersects(region), (t.net, t.start, t.end)
    for v in b.vias:
        if v.net != "GND" and v.net not in opened:
            from shapely.geometry import Point
            assert not Point(v.x, v.y).intersects(region), (v.net, v.x, v.y)
    # the hot-loop copper is kept, locked, and named by no DRC error
    d = drc.run(drc.stage_board(out, src, tmp_path / "drc"), tmp_path / "drc" / "drc.json")
    mine = {r["uuid"] for r in W.routing(out) if r["locked"]}
    assert mine
    assert not [v for v in drc.errors(d) if {i.get("uuid") for i in v.get("items", [])} & mine]


# giacobot esp32mp3, minimal copy: a small pour connected solidly (connect_pads yes) to one pin of the
# regulator, inside the loop the cells stage lays. There the cells' +BATT, +3V3 and GND copper beside
# U2's LX pins cut the solid LX pours off both pins; here the cell's GND hop under U1 crosses a +3V3 pour
# beside U1.1 and leaves only slivers narrower than its minimum width.
POUR = ('\t(zone\n\t\t(net "+3V3")\n\t\t(layer "F.Cu")\n\t\t(uuid "00000000-0000-4000-a000-000000000001")\n'
        '\t\t(hatch edge 0.5)\n\t\t(priority 2)\n\t\t(connect_pads yes\n\t\t\t(clearance 0.2)\n\t\t)\n'
        '\t\t(min_thickness 0.25)\n\t\t(fill\n\t\t\t(thermal_gap 0.5)\n\t\t\t(thermal_bridge_width 0.5)\n\t\t)\n'
        '\t\t(polygon\n\t\t\t(pts\n\t\t\t\t(xy 120.2 108.6) (xy 121.6 108.6) (xy 121.6 109.5) (xy 120.2 109.5)\n'
        '\t\t\t)\n\t\t)\n\t)\n')
CELLS = dict(hotloop_cells=1, hotloop_keepout=0, hotloop_vias=0, hotloop_pours=0)


def _pour_board(d):
    src = F.write_board(d)
    text, tail = src.read_text(), "\t(embedded_fonts no)\n)\n"
    assert text.endswith(tail)
    src.write_text(text[:-len(tail)] + POUR + tail)
    return src


def _touches_pour(path, x, y):
    """Whether the TSOT-23-6 pad (1.06 x 0.65 mm) at (x, y) on F.Cu touches the +3V3 fill of `path`
    (refilled)."""
    from shapely.geometry import box
    fills = [Polygon(r[0], r[1:]) for z in pcbnew_io.zone_fills(path)["zones"] if z["net"] == "+3V3"
             for r in z["layers"].get("F.Cu", [])]
    pad = box(x - 0.53, y - 0.325, x + 0.53, y + 0.325)
    return any(f.intersection(pad).area > 1e-4 for f in fills)


def test_cells_leave_a_solid_pour_its_pin(tmp_path):
    """(1) pour links: the cell's GND copper keeps out of the strip from U1.1 into its solid +3V3 pour, so
    the cell stays routed and the pin keeps its pour."""
    src = _pour_board(tmp_path / "in")
    assert _touches_pour(src, 119.69, 109.05)
    info = pcbnew_io.export_dsn(src, tmp_path / "b.dsn")
    rep = hotloop.stage(src, info, tmp_path / "w", CELLS, log=lambda *a: None)
    assert not rep.get("error") and rep["board"]
    assert rep["cells"][0]["status"] == "routed", rep["cells"]
    assert _touches_pour(rep["board"], 119.69, 109.05)
    assert not [h for h in rep["hazards"] if h["code"] == "hotloop_cell_cut_pour"]


def test_a_cell_that_cuts_a_pin_off_its_pour_is_reverted(tmp_path, monkeypatch):
    """(2) the post-cells check: without the pour links the cell cuts U1.1 off its pour; the refill finds
    it, the cell is reverted and a hotloop_cell_cut_pour hazard says so."""
    from kae.route import constraints as CN
    orig = CN.thermal_corridors
    monkeypatch.setattr(CN, "thermal_corridors", lambda *a, solid=False, **k: [] if solid else orig(*a, **k))
    src = _pour_board(tmp_path / "in")
    info = pcbnew_io.export_dsn(src, tmp_path / "b.dsn")
    rep = hotloop.stage(src, info, tmp_path / "w", CELLS, log=lambda *a: None)
    assert not rep.get("error")
    assert rep["cells"][0]["status"] == "reverted", rep["cells"]
    hz = [h for h in rep["hazards"] if h["code"] == "hotloop_cell_cut_pour"]
    assert hz and hz[0]["evidence"]["reverted"] == [rep["cells"][0]["id"]] and hz[0]["evidence"]["restored"]
    assert rep.get("pour_cut") == []
    assert rep["board"] is None or _touches_pour(rep["board"], 119.69, 109.05)
