# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The escape pre-pass (kae.route.escape) on a synthetic ball grid, without KiCad: dog-bones
for the rings the surface cannot escape, each in a diagonal gap and legal exactly."""
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


def _space(tmp_path):
    p = F.write_board(tmp_path, extra=[GRID, PARTNER])
    info = F.synth_info(load(p))
    plan = CN.plan(info, p, {})
    return p, info, plan, Space(load(p), info, plan=plan)


def test_dog_bones_in_diagonal_gaps_for_inner_rings(tmp_path):
    p, info, plan, sp = _space(tmp_path)
    got = escape.plan_escapes(p, info, plan, space=sp, opts=dict(row_escapes=False))
    pk = [x for x in got["report"]["packages"] if x["ref"] == "U7"]
    assert pk and pk[0]["capacity"] == 1 and pk[0]["first_ring"] == 2
    # rings 2 and 3: the inner 4 x 4 balls
    assert len(got["vias"]) == 16 and len(got["tracks"]) == 16
    balls = {b[1]: (134.5 + b[2], 121.0 + b[3]) for b in BALLS}
    for (net, x, y, D, d), (tn, layer, w, a, b) in zip(got["vias"], got["tracks"]):
        assert tn == net and layer == "F.Cu"
        bx, by = balls[net]
        assert abs(abs(x - bx) - PITCH / 2) < 1e-9 and abs(abs(y - by) - PITCH / 2) < 1e-9   # diagonal gap
        assert math.dist(a, (bx, by)) < 1e-9 and math.dist(b, (x, y)) < 1e-9
    # no two dog-bones share a gap, and none breaks a requirement of the final copper
    assert len({(round(x, 6), round(y, 6)) for _n, x, y, _D, _d in got["vias"]}) == 16
    for it in sp.routed:
        if it.kind == "via":
            assert not sp.via_violations(it.net, it.geom.x, it.geom.y, ignore=(it,))
        else:
            a, b = it.geom.coords
            assert not sp.track_violations(it.net, next(iter(it.layers)), it.width, a, b, ignore=(it,))


def test_outer_ring_is_left_to_the_router(tmp_path):
    p, info, plan, sp = _space(tmp_path)
    got = escape.plan_escapes(p, info, plan, space=sp, opts=dict(row_escapes=False))
    outer = {b[1] for b in BALLS if max(abs(b[2]), abs(b[3])) > (N - 1) / 2 * PITCH - PITCH - 1e-9}
    assert not outer & {v[0] for v in got["vias"]}
