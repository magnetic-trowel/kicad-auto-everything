# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Escapes out of 0.4 mm-pitch pads whose only legal way out is a track exactly as wide as the
pad, centred on it (no KiCad): the grid router's escape (critical_grid.GridRouter._escapes)
and the thermal-spoke strips beside such pads (constraints.thermal_corridors)."""
import math

from shapely.geometry import LineString

from kae.board.kicad_file import load
from kae.route import constraints as CN
from kae.route.critical_grid import Anchor, GridRouter
from kae.route.critical_space import EXACT_TOL, TOL, Space

import critical_fixtures as F

NETS = ["FA", "FB", "FC", "FD", "FE"]
# a row of five 0.2 x 0.8 mm pads at 0.4 mm pitch (gaps of 0.2 mm: at 0.2 mm clearance, a
# 0.2 mm track centred on a pad has nothing to spare) and their partners 7 mm away
ROW = ("U9", "QFN", "Package_DFN_QFN:Row", 106.0, 127.0, 0.0,
       [(str(k + 1), n, -0.8 + 0.4 * k, 0.0, 0.2, 0.8, "smd", 0.0, "", "passive") for k, n in enumerate(NETS)],
       (1.2, 0.6))
PARTNER = ("P9", "Pads", "x:Pads", 106.0, 120.0, 0.0,
           [(str(k + 1), n, -2.0 + 1.0 * k, 0.0, 0.5, 0.5, "smd", 0.0, "", "passive") for k, n in enumerate(NETS)],
           (2.5, 0.5))


def _setup(tmp_path):
    p = F.write_board(tmp_path, extra=[ROW, PARTNER])
    info = F.synth_info(load(p))
    info["settings"]["min_track"] = 0.2     # the board's minimum: exactly the pads' width
    plan = CN.plan(info, p, {})
    return p, info, plan, Space(load(p), info, plan=plan)


def _pad(sp, ref, num):
    return next(it for it in sp.pads if it.owner == (ref, num))


def test_grid_router_leaves_a_zero_slack_pad_through_its_axis(tmp_path):
    _p, _info, _plan, sp = _setup(tmp_path)
    a, b = _pad(sp, "U9", "3"), _pad(sp, "P9", "3")
    src = Anchor(a.geom, tuple(sorted(a.layers)), a.pos, kind="pad")
    dst = Anchor(b.geom, tuple(sorted(b.layers)), b.pos, kind="pad")
    gr = GridRouter(sp)
    # no room for the routing width, nor for the raster's margins at the minimum width
    assert gr.connect("FC", [src], [dst], 0.25, ["F.Cu"], via=False) is None
    # the centred piece is legal exactly, not with our usual margin
    out = (a.pos[0], a.pos[1] - 0.5)
    assert not sp.track_violations("FC", "F.Cu", 0.2, a.pos, out, tol=EXACT_TOL)
    assert sp.track_violations("FC", "F.Cu", 0.2, a.pos, out, tol=TOL)
    rt = gr.connect("FC", [src], [dst], 0.2, ["F.Cu"], via=False)
    assert rt is not None and rt.segs
    l0, s0, e0 = rt.segs[0]
    assert math.dist(s0, a.pos) < 1e-9 and abs(e0[0] - a.pos[0]) < 1e-9     # straight out along the axis
    for l, s, e in rt.segs:
        assert not sp.track_violations("FC", l, 0.2, s, e, tol=EXACT_TOL)


def test_spoke_strip_is_no_wider_than_the_pad(tmp_path):
    """A zone pad 0.2 mm wide among 0.4 mm-pitch neighbours: KiCad draws its spokes no wider
    than the pad, so the strip kept clear for them leaves the neighbours' centred escapes."""
    p, info, plan, _sp = _setup(tmp_path)
    for pd in info["pads"]:
        if pd["ref"] == "U9" and pd["number"] == "3":
            pd["net"] = "GND"
    info["zones"].append(dict(owner="", name="gnd_f", layers=["F.Cu"],
                              rings=[[[[100.5, 100.5], [139.5, 100.5], [139.5, 129.5], [100.5, 129.5],
                                       [100.5, 100.5]]]],
                              rule_area=False, net="GND", priority=0, clearance=0.15, min_thickness=0.15,
                              pad_connection="thermal", thermal_gap=0.5, spoke_width=0.5, teardrop=False))
    cors = [(g, l) for g, l, pad in CN.thermal_corridors(info, plan) if pad["ref"] == "U9" and pad["number"] == "3"]
    assert cors
    for nb in ("2", "4"):
        pd = next(x for x in info["pads"] if x["ref"] == "U9" and x["number"] == nb)
        x, y = pd["pos"]
        axis = (x, y - 0.4), (x, y + 0.4)
        track = LineString(axis).buffer(0.1)
        assert all(g.intersection(track).area <= 1e-9 for g, _ in cors)
