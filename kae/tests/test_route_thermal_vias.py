# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""kae.route.thermal_vias: a hot part gets vias from its thermal pad into the same net's copper on
the other face (a heat-sink plate's face, or without one the net's pour there), each exactly legal;
none without the operating facts, none for a net with no copper on the other face. The pass against KiCad's DRC is
skipped without KiCad."""
import json

import pytest
from shapely.geometry import box

import critical_fixtures as F
from kae.route import thermal_vias as TV

# a SOT-223-like regulator with its tab (pad 4) on `tab` and three leads; right of U2, clear of all
# the fixture's parts
def hot_part(tab="GND"):
    return ("U3", "LM1117-3.3", "Package_TO_SOT_SMD:SOT-223-3_TabPin2", 134.0, 120.0, 0.0,
            [("1", "GND", -2.3, 3.15, 1.0, 1.5, "smd", 0.0, "GND", "power_in"),
             ("2", "+3V3", 0.0, 3.15, 1.0, 1.5, "smd", 0.0, "VO", "power_out"),
             ("3", "VIN", 2.3, 3.15, 1.0, 1.5, "smd", 0.0, "VI", "power_in"),
             ("4", tab, 0.0, -3.15, 3.6, 2.0, "smd", 0.0, "TAB", "passive")], (3.5, 4.4))


def op(side="bottom", W=1.2, region="board", part_sink=False, sinks=True):
    hs = [dict(side=side, region=region, theta_C_W=0.5, T_C=35)] if sinks else []
    if part_sink:
        hs = [dict(part="U3", theta_sa_C_W=25)]
    return dict(parts={"U3": dict(P_sustained_W=W), "U2": dict(P_sustained_W=0.01)},
                requirements=dict(thermal=dict(heatsinks=hs)))


B_POUR = box(100.5, 100.5, 139.5, 129.5)      # the fixture's B.Cu GND pour, filled


def fills(front=None):
    f = {"GND": {"B.Cu": [B_POUR]}}
    if front is not None:
        f["GND"]["F.Cu"] = [front]
    return f


def _session(tmp_path, tab="GND"):
    return F.session(tmp_path, extra=[hot_part(tab)])


def test_targets_hot_parts_by_mode(tmp_path):
    s = _session(tmp_path)
    b = s.board

    def modes(o, **kw):
        return [(t["ref"], t["mode"], t["sink_side"]) for t in TV.targets(b, o, **kw)[0]]
    assert modes(op()) == [("U3", "sink", "bottom")]                  # U2's 10 mW is below heat_min_W
    assert modes({}) == []                                             # no operating facts
    assert modes(op(W=0.1)) == []                                      # not hot
    assert modes(op(sinks=False)) == [("U3", "both faces", "bottom")]  # no plate: stitch both faces
    assert modes(op(side="top")) == [("U3", "both faces", "bottom")]   # a sink on its own face only
    assert modes(op(region=[100, 100, 110, 110])) == [("U3", "both faces", "bottom")]   # region elsewhere
    assert modes(op(region=[130, 115, 138, 125])) == [("U3", "sink", "bottom")]
    assert modes(op(part_sink=True)) == [("U3", "both faces", "bottom")]
    assert modes(op(), opts=dict(thermal_vias=0)) == []                # switched off


def _front_gnd_zone(sp):
    """A GND zone on F.Cu as well (the fixture pours GND on B.Cu only)."""
    sp.zones.append(("GND", "F.Cu", box(100.5, 100.5, 139.5, 129.5), {}))


def test_without_a_plate_vias_need_the_pour_on_both_faces(tmp_path):
    s = _session(tmp_path)
    sp, b = s.space, s.board
    tg, _ = TV.targets(b, op(sinks=False))
    vias, rows = TV.place(sp, b, tg, fills(), log=lambda *a: None)
    assert vias == [] and any("no copper on the other face" in n for n in rows[0]["notes"])
    _front_gnd_zone(sp)
    u3 = next(f for f in b.footprints if f.ref == "U3")
    tab = sp.terminal(u3.uuid, ["4"]).geom
    front = tab.buffer(2.0)
    vias, rows = TV.place(sp, b, tg, fills(front), log=lambda *a: None)
    assert len(vias) >= 6 and rows[0]["mode"] == "both faces"
    for v in vias:
        assert B_POUR.contains(v.geom.buffer(v.r))
        assert tab.contains(v.geom.buffer(v.r)) or front.contains(v.geom.buffer(v.r))
    assert not any("thermal reliefs" in n for n in rows[0]["notes"]) and rows[0]["via_mm"] == [(0.6, 0.3)]


def test_reliefs_on_the_thermal_pad_are_reported_not_changed(tmp_path):
    """A pour that joins the exposed pad through thermal reliefs chokes the heat path: the report
    says so (the board's setting stands) and the vias still go in."""
    s = _session(tmp_path)
    sp, b = s.space, s.board
    _front_gnd_zone(sp)
    sp.info["zones"].append(dict(net="GND", layers=["F.Cu"], pad_connection="thermal", rule_area=False))
    tg, _ = TV.targets(b, op(sinks=False))
    vias, rows = TV.place(sp, b, tg, fills(), log=lambda *a: None)
    assert vias and any("thermal reliefs" in n for n in rows[0]["notes"])


def test_vias_in_the_exposed_pad_are_legal_and_land_on_the_sink_pour(tmp_path):
    s = _session(tmp_path)
    sp, b = s.space, s.board
    tg, _ = TV.targets(b, op())
    vias, rows = TV.place(sp, b, tg, fills(), log=lambda *a: None)
    u3 = next(f for f in b.footprints if f.ref == "U3")
    tab = sp.terminal(u3.uuid, ["4"]).geom
    assert rows[0]["vias"] == len(vias) >= 4
    assert rows[0]["nets"]["GND"]["in_pad"] == len(vias)       # no F.Cu pour: inside the pad only
    sp.via_in_pad = True                                         # the pass checked them so: an exposed pad
    for v in vias:
        assert v.net == "GND" and tab.contains(v.geom.buffer(v.r))
        assert B_POUR.contains(v.geom.buffer(v.r))
        assert not sp.via_violations("GND", v.geom.x, v.geom.y, ignore=[v])
    sp.via_in_pad = False
    pts = [(v.geom.x, v.geom.y) for v in vias]
    assert min(((a[0] - c[0]) ** 2 + (a[1] - c[1]) ** 2) ** 0.5 for i, a in enumerate(pts) for c in pts[i + 1:]) \
        >= 1.0 - 1e-6                                            # the default pitch


def test_around_the_pad_on_its_pour_when_vias_stay_out_of_pads(tmp_path):
    s = _session(tmp_path)
    sp, b = s.space, s.board
    u3 = next(f for f in b.footprints if f.ref == "U3")
    tab = sp.terminal(u3.uuid, ["4"]).geom
    front = tab.buffer(2.0)                                       # an F.Cu GND pour piece around the tab
    tg, _ = TV.targets(b, op())
    vias, rows = TV.place(sp, b, tg, fills(front), opts=dict(thermal_via_in_pad=0, thermal_via_max=6),
                          log=lambda *a: None)
    assert 1 <= len(vias) <= 6 and rows[0]["nets"]["GND"]["in_pad"] == 0
    for v in vias:
        assert not tab.intersects(v.geom.buffer(v.r))
        assert front.contains(v.geom.buffer(v.r)) and B_POUR.contains(v.geom.buffer(v.r))
        assert not sp.via_violations("GND", v.geom.x, v.geom.y, ignore=[v])


def test_max_per_part(tmp_path):
    s = _session(tmp_path)
    tg, _ = TV.targets(s.board, op())
    vias, _ = TV.place(s.space, s.board, tg, fills(), opts=dict(thermal_via_max=2), log=lambda *a: None)
    assert len(vias) == 2


def test_no_vias_for_a_net_without_copper_on_the_sink_face(tmp_path):
    """The tab on VIN, which has no zone on B.Cu: nothing for it, and the report says why; the GND
    lead has no pour on the part's face, so it gets none either."""
    s = _session(tmp_path, tab="VIN")
    tg, _ = TV.targets(s.board, op())
    vias, rows = TV.place(s.space, s.board, tg, fills(), log=lambda *a: None)
    assert vias == [] and rows[0]["vias"] == 0
    assert any(n.startswith("VIN (thermal pad):") and "no copper on the other face" in n for n in rows[0]["notes"])


# ----------------------------------------------------------------------------- against KiCad
def _kicad():
    from kae.board import pcbnew_io
    return pcbnew_io.available()


@pytest.mark.kicad
@pytest.mark.skipif(not _kicad(), reason="no Python with pcbnew")
def test_pass_adds_vias_without_a_drc_error(tmp_path):
    from kae.board import pcbnew_io
    from kae.board.kicad_file import load
    from kae.route import bridge, constraints, drc
    src = F.write_board(tmp_path / "in", extra=[hot_part()])
    opf = tmp_path / "op.json"
    opf.write_text(json.dumps(op()))
    info = pcbnew_io.export_dsn(src, tmp_path / "board.dsn")
    opts = dict(operating=str(opf), severities=bridge.severities(src))
    plan = constraints.plan(info, src, opts)
    out = tmp_path / "out" / "board.kicad_pcb"
    out.parent.mkdir()
    out.write_bytes(src.read_bytes())
    import time
    rep = TV.run(src, out, tmp_path / "wd", plan, info, opts, deadline=time.monotonic() + 300, log=lambda *a: None)
    assert rep["status"] == "kept", rep
    assert rep["added"] >= 4 and rep["vias_per_part"] == {"U3": rep["added"]}
    assert rep["after"]["errors"] <= rep["before"]["errors"]
    assert rep["after"]["unconnected"] <= rep["before"]["unconnected"]
    assert len(load(out).vias) == rep["added"]
    d = drc.run(out, tmp_path / "check.json")
    assert drc.summary(d)["errors"] == rep["after"]["errors"]
    # without the operating facts: nothing
    rep0 = TV.run(src, out, tmp_path / "wd0", plan, info, dict(opts, operating=""), deadline=time.monotonic() + 60)
    assert rep0["status"] == "no part needs thermal vias"
