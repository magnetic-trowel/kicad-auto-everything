# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Dog-bones of a synthetic ball grid (kae.route.escape, no KiCad): the rings the surface
cannot escape get one each, in a diagonal gap, legal exactly; the outer rings are left."""
import math

from kae.board.kicad_file import load
from kae.route import constraints as CN
from kae.route import escape
from kae.route.critical_space import Space

import critical_fixtures as F

N = 8           # 8 x 8 balls
PITCH = 1.27    # 0.4 mm balls 0.87 mm apart: one 0.25 mm track at 0.2 mm clearance between them
BALLS = [(f"{chr(65 + r)}{c + 1}", f"S{r}{c}", (c - (N - 1) / 2) * PITCH, (r - (N - 1) / 2) * PITCH,
          0.4, 0.4, "smd", 0.0, "", "passive") for r in range(N) for c in range(N)]
GRID = ("U7", "BGA", "Package_BGA:Grid", 134.5, 121.0, 0.0, BALLS, (4.8, 4.8))
# each ball's partner, so every net needs routing
PARTNER = ("P7", "Pads", "x:Pads", 104.0, 125.0, 0.0,
           [(str(k + 1), b[1], (k % 9) * 0.5 - 2.0, (k // 9) * 0.6 - 1.0, 0.3, 0.3, "smd", 0.0, "", "passive")
            for k, b in enumerate(BALLS)], (2.5, 1.5))


def test_dog_bones_for_inner_rings_in_diagonal_gaps(tmp_path):
    p = F.write_board(tmp_path, extra=[GRID, PARTNER])
    info = F.synth_info(load(p))
    sp = Space(load(p), info, plan=CN.plan(info, p, {}))
    assert escape.dog_bones(sp, info, log=lambda m: None) == (16, 16)    # rings 2 and 3: the inner 4 x 4
    vias = [it for it in sp.routed if it.kind == "via"]
    tracks = [it for it in sp.routed if it.kind == "track"]
    balls = {b[1]: (134.5 + b[2], 121.0 + b[3]) for b in BALLS}
    outer = {n for n, (x, y) in balls.items() if max(abs(x - 134.5), abs(y - 121.0)) > 2 * PITCH}
    assert len(tracks) == 16 and not outer & {v.net for v in vias}
    for v in vias:
        bx, by = balls[v.net]
        assert abs(abs(v.geom.x - bx) - PITCH / 2) < 1e-9 and abs(abs(v.geom.y - by) - PITCH / 2) < 1e-9
        # pointing away from the package centre
        assert (v.geom.x - bx) * (bx - 134.5) > 0 and (v.geom.y - by) * (by - 121.0) > 0
    for it in sp.routed:
        if it.kind == "via":
            assert not sp.via_violations(it.net, it.geom.x, it.geom.y, ignore=(it,))
        else:
            a, b = it.geom.coords
            assert math.dist(a, balls[it.net]) < 1e-9
            assert not sp.track_violations(it.net, next(iter(it.layers)), it.width, a, b, ignore=(it,))
