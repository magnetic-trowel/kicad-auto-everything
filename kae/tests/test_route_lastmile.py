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
