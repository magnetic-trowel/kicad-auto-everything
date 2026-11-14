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
    for t in b.tracks:
        if t.layer == "B.Cu" and t.net != "GND":
            assert not LineString([t.start, t.end]).intersects(region), (t.net, t.start, t.end)
    for v in b.vias:
        if v.net != "GND":
            from shapely.geometry import Point
            assert not Point(v.x, v.y).intersects(region), (v.net, v.x, v.y)
    # the hot-loop copper is kept, locked, and named by no DRC error
    d = drc.run(drc.stage_board(out, src, tmp_path / "drc"), tmp_path / "drc" / "drc.json")
    mine = {r["uuid"] for r in W.routing(out) if r["locked"]}
    assert mine
    assert not [v for v in drc.errors(d) if {i.get("uuid") for i in v.get("items", [])} & mine]
