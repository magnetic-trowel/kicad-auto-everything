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
    sp, info = _space(tmp_path)
    assert escape.dog_bones(sp, info, log=lambda m: None) == (16, 16)    # rings 2 and 3: the inner 4 x 4
    vias = [it for it in sp.routed if it.kind == "via"]
    balls = {b[1]: (134.5 + b[2], 121.0 + b[3]) for b in BALLS}
    for v in vias:
        bx, by = balls[v.net]
        assert (v.geom.x - bx) * (bx - 134.5) > 0 and (v.geom.y - by) * (by - 121.0) > 0


def _space(tmp_path):
    p = F.write_board(tmp_path, extra=[GRID, PARTNER])
    info = F.synth_info(load(p))
    return Space(load(p), info, plan=CN.plan(info, p, {})), info


def test_escape_plan_escapes_every_ball_and_lays_legal_copper(tmp_path):
    sp, info = _space(tmp_path)
    out = escape.run(sp, info, {}, log=lambda m: None)
    (pk,) = out["packages"]
    assert pk["signal"] == 64 and pk["planned"] == 64 and not out["blocked"]
    # the outer rings on the surface, the rest through dog-bones to B.Cu
    assert pk["by_layer"]["F.Cu"] >= 28 and pk["by_layer"]["B.Cu"] >= 4
    assert pk["laid"] >= 44
    balls = {b[1]: (134.5 + b[2], 121.0 + b[3]) for b in BALLS}
    for r in pk["escapes"]:
        if r["via"]:
            bx, by = balls[r["net"]]
            assert abs(abs(r["via"][0] - bx) - PITCH / 2) < 1e-6 and abs(abs(r["via"][1] - by) - PITCH / 2) < 1e-6
    for it in sp.routed:
        if it.kind == "via":
            assert not sp.via_violations(it.net, it.geom.x, it.geom.y, ignore=(it,))
        else:
            a, b = it.geom.coords
            assert not sp.track_violations(it.net, next(iter(it.layers)), it.width, a, b, ignore=(it,))


def test_has_grid_only_for_ball_grids():
    """The bridge's escape stage runs only on boards with a ball grid or a fine-pitch pad ring
    (escape.has_grid)."""
    from kae.route.escape import has_grid
    grid = [dict(attr="smd", layers=["F.Cu"], pos=(x * 0.8, y * 0.8), fp_index=1) for x in range(5) for y in range(5)]
    row = [dict(attr="smd", layers=["F.Cu"], pos=(x * 0.5, 0.0), fp_index=2) for x in range(20)]
    coarse = [dict(attr="smd", layers=["F.Cu"], pos=(x * 1.27, 0.0), fp_index=3) for x in range(20)]
    assert has_grid(dict(pads=grid)) and has_grid(dict(pads=row)) and not has_grid(dict(pads=coarse))
    assert not has_grid({})


def test_escape_bound_proves_too_wide_tracks_cannot_escape(tmp_path):
    sp, info = _space(tmp_path)
    (pkg,) = [p for p in escape.find_packages(sp) if p["kind"] == "grid"]
    ok, meta, _ = escape.bound(sp, pkg, info)
    assert ok >= 64 - 0.5 and escape.certificate(sp, pkg, info, log=lambda m: None) is None
    # 2 mm tracks: no channel holds one; the outer ring leaves straight out, the next one
    # only past its dog-bones, the inner 4 x 4 not at all
    assert escape.fit(PITCH - 0.4, 2.0, 0.2) == 0 and escape.fit(2 * PITCH - 0.6, 2.0, 0.2) == 0
    low, meta, duals = escape.bound(sp, pkg, info, override=dict(w=2.0))
    assert low <= 64 - 16 + 1e-6 and duals


def test_an_unsolved_bound_neither_certifies_nor_throws_away_the_plan(tmp_path, monkeypatch):
    """bound() returns (None, ctx, {}) when the LP relaxation does not solve; certificate()
    did `None + 1e-6`, and the TypeError in run() dropped the plan already computed."""
    monkeypatch.setenv("KAE_ESCAPE_CACHE", str(tmp_path / "cache"))
    sp, info = _space(tmp_path)
    (pkg,) = [p for p in escape.find_packages(sp) if p["kind"] == "grid"]
    monkeypatch.setattr(escape, "bound", lambda *a, **k: (None, {"sig": [1, 2, 3]}, {}))
    assert escape.certificate(sp, pkg, info, log=lambda m: None) is None

    def boom(*a, **k):
        raise RuntimeError("proof failed")
    monkeypatch.setattr(escape, "certificate", boom)
    out = escape.run(sp, info, {}, log=lambda m: None)
    (pk,) = out["packages"]
    assert "error" not in pk and pk["planned"] == 64 and pk["laid"] >= 44 and not out["blocked"]
