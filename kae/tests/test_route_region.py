# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Negotiated routing of a dense window (kae.route.region, no KiCad) on a synthetic ball grid:
the window is found, every ball escapes towards its partner legally, and an over-full channel
is named with the room the rules leave."""
import math

from kae.board.kicad_file import load
from kae.route import constraints as CN
from kae.route import region
from kae.route.critical_space import Space

import critical_fixtures as F

N = 4           # 4 x 4 balls
PITCH = 1.27    # 0.4 mm balls 0.87 mm apart: one 0.15 mm track at 0.2 mm clearance between two
BALLS = [(f"{chr(65 + r)}{c + 1}", f"S{r}{c}", (c - (N - 1) / 2) * PITCH, (r - (N - 1) / 2) * PITCH,
          0.4, 0.4, "smd", 0.0, "", "passive") for r in range(N) for c in range(N)]
GRID = ("U7", "BGA", "Package_BGA:Grid", 134.5, 121.0, 0.0, BALLS, (2.5, 2.5))
# each ball's partner, a row of pads well to the left (outside the window)
PARTNER = ("P7", "Pads", "x:Pads", 104.0, 125.0, 0.0,
           [(str(k + 1), b[1], 0.0, (k - len(BALLS) / 2) * 0.7, 0.4, 0.4, "smd", 0.0, "", "passive")
            for k, b in enumerate(BALLS)], (0.5, 6.0))


def _setup(tmp_path):
    p = F.write_board(tmp_path, extra=[GRID, PARTNER])
    info = F.synth_info(load(p))
    plan = CN.plan(info, p, {})
    sp = Space(load(p), info, plan=plan)
    return p, info, plan, sp


def test_window_found_and_every_ball_escapes_legally(tmp_path):
    p, info, plan, sp = _setup(tmp_path)
    ws = region.windows(sp)
    w = next(x for x in ws if x["ref"] == "U7")
    assert w["kind"] == "ball grid" and abs(w["pitch"] - PITCH) < 1e-6 and w["pads"] == N * N
    assert w["box"][0] < 134.5 - 1.5 * PITCH - w["ring"] + 1e-6
    rg = region.Region(sp, [], w, log=lambda m: None)
    rg.setup()
    # every ball's partner lies outside the window, to the west: one escape each
    assert all(rg.terms[b[1]]["side"] == "W" for b in BALLS)
    rg.run(max_iter=30)
    assert rg.converged and rg.stats[-1]["nets_in_conflict"] == 0
    com = rg.commit()
    assert com["laid"] == N * N and com["escapes"] == N * N and not com["rejected"]
    x0 = w["box"][0]
    for n, rt in rg.best.items():
        ends = [pt for (_l, pts, _e) in rt.runs for pt in (pts[0], pts[-1])]
        assert min(x for x, _ in ends) < x0 + 3 * rg.grid.res      # reaches the west side
    for it in rg.new:
        if it.kind == "via":
            assert not sp.via_violations(it.net, it.geom.x, it.geom.y, ignore=(it,))
        else:
            a, b = it.geom.coords
            assert not sp.track_violations(it.net, next(iter(it.layers)), it.width, a, b, ignore=(it,))


def test_over_full_channel_is_named_with_its_room(tmp_path):
    p, info, plan, sp = _setup(tmp_path)
    w = next(x for x in region.windows(sp) if x["ref"] == "U7")
    rg = region.Region(sp, [], w, log=lambda m: None)
    rg.setup()
    # three nets through the one-track channel between A1 and A2 (y = 121 - 1.5 PITCH): vertical
    # tracks 0.05 mm apart across the cut between the two balls' centres
    x0, y0 = 134.5 - 1.5 * PITCH, 121.0 - 1.5 * PITCH
    routes = {}
    for k, n in enumerate(("S00", "S01", "S02")):
        rt = region._Route(n, rg.width[n])
        x = x0 + PITCH / 2 + (k - 1) * 0.05
        rt.runs = [("F.Cu", [(x, y0 - 0.5), (x, y0 + 0.5)], False)]
        routes[n] = rt
    rg.best, rg.best_conflict = routes, set(routes)
    cap = rg.capacity()
    c = next(r for r in cap if r["kind"] == "channel")
    assert c["layer"] == "F.Cu" and c["needs"] == 3 and c["holds"] == 1
    assert math.isclose(c["gap"], PITCH - 0.4, abs_tol=1e-3)
    assert "room for 1" in c["line"] and "U7.A1-U7.A2" in c["line"]
