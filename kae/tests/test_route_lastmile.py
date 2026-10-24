# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""kae.route.lastmile: joining the parts of open nets on the synthetic board (no KiCad)."""
from kae.board.kicad_file import load
from kae.route import constraints as CN
from kae.route import critical_write as W
from kae.route import lastmile as LM
from kae.route.critical_space import Space

import critical_fixtures as F

NET = "Net-(U2-XTAL1)"      # U2.2, Y1.1, C4.1: three pads, no copper yet


def _space(p, info):
    b = load(p)
    return Space(b, info, plan=CN.plan(info, p, {}))


def test_parts_follow_kicads_joins(tmp_path):
    """A track joins copper only where an end lies on it: a track crossing a pad's net
    neighbour mid-body leaves them apart."""
    p = F.write_board(tmp_path)
    info = F.synth_info(load(p))
    sp = _space(p, info)
    assert len(LM.parts(sp, {}, NET)) == 3
    y1 = next(it for it in sp.pads if it.owner == ("Y1", "1"))
    u2 = next(it for it in sp.pads if it.owner == ("U2", "2"))
    W.append_items(p, p, tracks=[(NET, "F.Cu", 0.25, y1.pos, u2.pos, W.new_uuid(), False)])
    sp = _space(p, info)
    ps = LM.parts(sp, {}, NET)
    assert len(ps) == 2 and {n.item.owner for n in ps[0] if n.kind == "pad"} == {("Y1", "1"), ("U2", "2")}


def test_close_joins_every_part_legally(tmp_path):
    p = F.write_board(tmp_path)
    info = F.synth_info(load(p))
    sp = _space(p, info)
    out = tmp_path / "out.kicad_pcb"
    rep = LM.close(p, info, sp.plan, [], out, nets=[NET], log=lambda *a: None)
    assert rep["joined"] == 2 and rep["failed"] == 0 and not rep["ripped"]
    sp2 = _space(out, info)
    assert len(LM.parts(sp2, {}, NET)) == 1
    new = [it for it in sp2.existing if it.net == NET]
    assert new and all(it.locked for it in new)
    for it in new:
        if it.kind == "track":
            a, b = it.geom.coords[0], it.geom.coords[-1]
            assert not sp2.track_violations(NET, next(iter(it.layers)), it.width, a, b, ignore=[it])
        else:
            assert not sp2.via_violations(NET, it.geom.x, it.geom.y, ignore=[it])


def test_close_rips_only_the_wall_it_must_cross(tmp_path):
    """C4.1 is walled off from Y1.1 and U2.2 by +3V3 tracks across the board on both layers:
    the join rips what it crosses (unlocked) and nothing else, and the ripped net is joined
    again by the same search (negotiated re-route); a fixed wall stays."""
    p = F.write_board(tmp_path)
    info = F.synth_info(load(p))
    x = 114.7
    wall = [("+3V3", l, 0.25, (x, 100.6), (x, 129.4), W.new_uuid(), False) for l in ("F.Cu", "B.Cu")]
    other = ("+3V3", "F.Cu", 0.25, (136.0, 101.0), (136.0, 105.0), W.new_uuid(), False)
    W.append_items(p, p, tracks=wall + [other])
    sp = _space(p, info)
    out = tmp_path / "out.kicad_pcb"
    rep = LM.close(p, info, sp.plan, [], out, nets=[NET], log=lambda *a: None)
    assert rep["failed"] == 0 and sum(st.startswith("joined") for st in rep["nets"][NET]) == 2
    assert rep["ripped"] and set(rep["ripped"]) <= {w[5] for w in wall}
    assert rep["rerouted"] == ["+3V3"]
    sp2 = _space(out, info)
    assert len(LM.parts(sp2, {}, NET)) == 1
    assert len([q for q in LM.parts(sp2, {}, "+3V3") if LM._relevant(q)]) == 1     # tails aside
    # fixed (pre-routed) copper is never ripped: with the whole wall fixed, C4 stays apart
    rep2 = LM.close(p, info, sp.plan, [], tmp_path / "out2.kicad_pcb", nets=[NET], fixed=[w[5] for w in wall],
                    log=lambda *a: None)
    assert not rep2["ripped"] and rep2["failed"] == 1


def test_open_nets_reads_kicads_report():
    rep = {"unconnected_items": [{"items": [{"description": "PTH pad 4 [MOSI] of J2"},
                                            {"description": "Zone [/GND] on B.Cu, priority 0"}]}]}
    assert LM.open_nets(rep) == ["/GND", "MOSI"]


def test_critical_copper_is_ripped_only_as_the_soft_last_tier(tmp_path):
    """A locked (critical) wall blocks the join: without `soft` nothing is ripped; with the
    wall's uuids soft, the last tier rips what the join crosses and reports it as ripped_soft
    (the caller then judges the physics)."""
    p = F.write_board(tmp_path)
    info = F.synth_info(load(p))
    x = 114.7
    wall = [("+3V3", l, 0.25, (x, 100.6), (x, 129.4), W.new_uuid(), True) for l in ("F.Cu", "B.Cu")]
    W.append_items(p, p, tracks=wall)
    sp = _space(p, info)
    rep = LM.close(p, info, sp.plan, [], tmp_path / "a.kicad_pcb", nets=[NET], log=lambda *a: None)
    assert not rep["ripped"] and rep["failed"] == 1
    rep = LM.close(p, info, sp.plan, [], tmp_path / "b.kicad_pcb", nets=[NET], log=lambda *a: None,
                   soft=[w[5] for w in wall])
    assert rep["ripped_soft"] and set(rep["ripped_soft"]) == set(rep["ripped"]) <= {w[5] for w in wall}
    assert len(LM.parts(_space(tmp_path / "b.kicad_pcb", info), {}, NET)) == 1


def test_report_names_map_back_to_escaped_board_names():
    """KiCad's DRC report shows "Net-(U1-PA12/PA10)" for the board's "Net-(U1-PA12{slash}PA10)"
    (noisecard: the last mile found nothing to join until the names were mapped back)."""
    assert LM.unescape("Net-(U1-PA12{slash}PA10)") == "Net-(U1-PA12/PA10)"
    assert LM.unescape("/mcu/TMS") == "/mcu/TMS"


def test_close_finds_a_net_named_with_an_escaped_slash(tmp_path):
    """A net KiCad escapes in the board ("SIG{slash}X") and unescapes in its DRC report
    ("SIG/X") is still found and joined."""
    net = "SIG{slash}X"
    extra = [("R21", "1k", "Resistor_SMD:R_0402_1005Metric", 136.0, 124.0, 0.0,
              [("1", net, -0.48, 0.0, 0.56, 0.62, "smd", 0.0, "", "passive"),
               ("2", "", 0.48, 0.0, 0.56, 0.62, "smd", 0.0, "", "passive")], (0.95, 0.5)),
              ("R22", "1k", "Resistor_SMD:R_0402_1005Metric", 136.0, 127.0, 0.0,
               [("1", net, -0.48, 0.0, 0.56, 0.62, "smd", 0.0, "", "passive"),
                ("2", "", 0.48, 0.0, 0.56, 0.62, "smd", 0.0, "", "passive")], (0.95, 0.5))]
    p = F.write_board(tmp_path, extra=extra)
    info = F.synth_info(load(p))
    sp = _space(p, info)
    rep = {"unconnected_items": [{"items": [{"description": "Pad 1 [SIG/X] of R21 on F.Cu"},
                                            {"description": "Pad 1 [SIG/X] of R22 on F.Cu"}]}]}
    out = tmp_path / "out.kicad_pcb"
    r = LM.close(p, info, sp.plan, [], out, nets=LM.open_nets(rep), log=lambda *a: None)
    assert r["joined"] == 1 and list(r["nets"]) == [net]
    assert len(LM.parts(_space(out, info), {}, net)) == 1
