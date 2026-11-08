# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""kae.place.heat: heat-sink keepouts and the pull of hot parts into cooled regions."""
import json
from pathlib import Path

from kae.board.kicad_file import load
from kae.place import heat as H
from kae.place.problem import Problem

FIXTURE = Path(__file__).parent / "data" / "board" / "fixture.kicad_pcb"


def _P():
    P = Problem.build(load(FIXTURE))
    P.set_margin(0.0)
    return P


def _part(P):
    return next(q for q in P.parts if q.movable and len(q.fp.pads) >= 3)


def test_a_part_sink_reserves_its_overhang_beyond_the_part():
    P = _P()
    p = _part(P)
    x0, y0, x1, y1 = H._extent(p.fp)
    w, l = (x1 - x0) + 4.0, (y1 - y0) + 2.0             # 2 mm beyond each side in x, 1 mm in y
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    op = {"requirements": {"thermal": {"heatsinks": [
        {"part": p.ref, "theta_sa_C_W": 20, "outline_mm": [w, l], "offset_mm": [cx, cy]}]}}}
    bands, rows = H.sink_bands(P, op)
    assert [round(b, 6) for b in bands[p.i]] == [2.0, 1.0, 2.0, 1.0]
    assert rows[0]["part"] == p.ref


def test_a_part_sink_without_an_outline_reserves_nothing_and_says_so():
    P = _P()
    p = _part(P)
    bands, rows = H.sink_bands(P, {"requirements": {"thermal": {"heatsinks": [{"part": p.ref, "theta_sa_C_W": 20}]}}})
    assert bands == {} and "no outline_mm" in rows[0]["skipped"]


def test_hot_parts_are_pulled_to_the_nearest_region_and_weak_ones_are_not():
    P = _P()
    p = _part(P)
    q = next(x for x in P.parts if x.movable and x is not p)
    region = [P.ox + 2.0, P.oy + 2.0, P.ox + 8.0, P.oy + 6.0]
    op = {"requirements": {"thermal": {"heatsinks": [{"side": "bottom", "region": region, "theta_C_W": 1.0}]}},
          "parts": {p.ref: {"P_sustained_W": 1.5}, q.ref: {"P_sustained_W": 0.05}}}
    pulls, rows = H.pull_anchors(P, op, opts={"heat_pull_w": 2.0})
    assert set(pulls) == {p.i} and pulls[p.i][2] == 3.0
    tg, (rx, ry), _ = pulls[p.i]
    for (X, Y), r in zip(tg, p.rots):                    # the part's centre at the region's centre
        a, b, c, d = r.own
        assert abs(P.ox + X * P.g + (a + c) / 2 - 5.0 - P.ox) <= P.g
        assert abs(P.oy + Y * P.g + (b + d) / 2 - 4.0 - P.oy) <= P.g
    assert rx >= 0 and ry >= 0
    # the whole board is cooled everywhere: no pull
    op["requirements"]["thermal"]["heatsinks"][0]["region"] = "board"
    assert H.pull_anchors(P, op)[0] == {}


def test_operating_facts_come_from_the_option(tmp_path):
    f = tmp_path / "op.json"
    f.write_text(json.dumps({"parts": {"U1": {"P_sustained_W": 0.8}}}))
    assert H.watts(H.operating(opts={"operating": str(f)})) == {"U1": 0.8}
    assert H.operating(opts={}) == {}
    assert H.operating(opts={"operating": str(tmp_path / "missing.json")}) == {}


def test_placement_pulls_a_hot_part_into_its_region(tmp_path):
    from kae.place.pipeline import place
    P = _P()
    p = _part(P)
    bx0, by0, bx1, by1 = P.outline.bounds
    # far from the part's input pose: without the pull it lands outside (seed 0: at 23.8, 15.0)
    region = [bx0 + 0.55 * (bx1 - bx0), by0 + 0.4 * (by1 - by0), bx1 - 1.0, by1 - 1.0]
    f = tmp_path / "op.json"
    f.write_text(json.dumps({"requirements": {"thermal": {"heatsinks": [{"side": "bottom", "region": region, "theta_C_W": 1}]}},
                             "parts": {p.ref: {"P_sustained_W": 5.0}}}))
    res = place(load(FIXTURE), seed=0, time_s=10.0, physics=False, workers=1,
                opts={"operating": str(f), "heat_pull_w": 20.0})
    assert res.report["heat_pulls"][0]["part"] == p.ref
    x, y = res.poses[p.uuid][:2]
    assert region[0] <= x <= region[2] and region[1] <= y <= region[3]
