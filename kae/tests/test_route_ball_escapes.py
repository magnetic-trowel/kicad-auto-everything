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


# ----------------------------------------------------------------------------- the shared grid test
def _lattice(nx, ny, pitch, skip=lambda i, j: False):
    return [(i * pitch, j * pitch) for i in range(nx) for j in range(ny) if not skip(i, j)]


def test_a_small_wafer_level_package_is_a_grid_and_connectors_and_rings_are_not():
    """A 12-ball 3 x 4 WLP (chips-0123's MAX98365) has 2 balls with four neighbours: the
    router's old test (16 balls, 4 such) left it without escape plan or dog-bones."""
    g = escape.ball_grid(_lattice(3, 4, 0.4))
    assert g is not None and abs(g.pitch - 0.4) < 1e-9
    assert sorted(g.rings) == [0] * 10 + [1] * 2 and all(t is None for t in g.toward)
    assert escape.ball_grid(_lattice(6, 2, 0.5)) is None                         # a 2-row connector
    assert escape.ball_grid(_lattice(4, 4, 0.4, lambda i, j: 0 < i < 3 and 0 < j < 3)) is None  # hollow ring
    qfn = [(-1.45, t) for t in (-0.5, 0, 0.5)] + [(1.45, t) for t in (-0.5, 0, 0.5)] + \
          [(t, -1.45) for t in (-0.5, 0, 0.5)] + [(t, 1.45) for t in (-0.5, 0, 0.5)]
    assert escape.ball_grid(qfn) is None                                         # off its own lattice
    assert escape.has_grid(dict(pads=[dict(attr="smd", layers=["F.Cu"], pos=p, fp_index=1)
                                      for p in _lattice(3, 4, 0.4)]))


def test_an_open_channel_is_a_free_side():
    """10 x 10 at 1.27 mm with columns 4 and 5 empty, open at both ends (a DDR x16's centre
    channel, nekoink U202): the balls beside it escape into it (ring 0), the next ones are
    ring 1, and their way out is the channel's mouth, not the package's long side."""
    pts = _lattice(10, 10, 1.27, lambda i, j: i in (4, 5))
    g = escape.ball_grid(pts)
    at = dict(zip(g.idx, range(len(pts))))
    assert [g.site_rings[(i, 5)] for i in range(10)] == [0, 1, 1, 0, 0, 0, 0, 1, 1, 0]
    k = at[(3, 5)]
    assert g.toward[k] is not None and g.toward[k][0] > 0.99                     # towards +x, the channel
    assert g.exits[k][1] < 0 or g.exits[k][1] > 9 * 1.27                         # past a short end
    assert g.toward[at[(1, 5)]] is None                                          # ring 1 from the edge
    # mouths that hold 7 tracks each carry 14 of the 16 balls beside: the channel counts from its
    # ends inward, its middle rows' balls stay ring 1
    g = escape.ball_grid(pts, room=lambda gap: escape.fit(gap - 0.4, 0.25, 0.2))
    (v,) = g.voids
    assert v["tracks"] == 14 and v["demand"] == 16 and 0 < v["counted"] < 20
    assert [g.site_rings[(3, j)] for j in range(10)] == [0, 0, 0, 0, 1, 1, 0, 0, 0, 0]


def test_a_closed_void_is_no_free_side():
    """An empty 2 x 2 in the middle of a 10 x 10: what enters it still has to cross the rings
    round it, so the rings stay those from the edge."""
    pts = _lattice(10, 10, 0.8, lambda i, j: i in (4, 5) and j in (4, 5))
    g = escape.ball_grid(pts)
    full = escape.ball_grid(_lattice(10, 10, 0.8))
    (v,) = g.voids
    assert not v["open"] and not v["counted"]
    assert [g.site_rings[q] for q in g.idx] == [full.site_rings[q] for q in g.idx]


CH = dict(nx=15, ny=8, pitch=PITCH, cx=125.0, cy=140.0)    # below the fixture's parts, on a taller board


def _channel_space(tmp_path, monkeypatch):
    monkeypatch.setattr(F, "SIZE", (60.0, 50.0))
    nx, ny, p = CH["nx"], CH["ny"], CH["pitch"]
    balls = [(f"B{i}_{j}", f"S{i}_{j}", (i - (nx - 1) / 2) * p, (j - (ny - 1) / 2) * p, 0.4, 0.4, "smd", 0.0,
              "", "passive") for i in range(nx) for j in range(ny) if i not in (6, 7, 8)]
    grid = ("U8", "BGA", "Package_BGA:Channel", CH["cx"], CH["cy"], 0.0, balls, (9.5, 5.0))
    partner = ("P8", "Pads", "x:Pads", 104.0, 125.0, 0.0,
               [(str(k + 1), b[1], (k % 9) * 0.5 - 2.0, (k // 9) * 0.6 - 3.0, 0.3, 0.3, "smd", 0.0, "", "passive")
                for k, b in enumerate(balls)], (2.5, 3.5))
    p_ = F.write_board(tmp_path, extra=[grid, partner])
    info = F.synth_info(load(p_))
    return Space(load(p_), info, plan=CN.plan(info, p_, {})), info


def test_dog_bones_leave_a_channel_free_and_point_into_it(tmp_path, monkeypatch):
    """Two 6-column groups round an empty 3-column channel, 1.27 mm pitch (one track between two
    balls: rings 0 and 1 escape on the surface). From the box alone, columns 2-5 have rings up
    to 3 and the balls beside the channel got dog-bones whose vias, pointed away from the
    centre, stood between the channel's two columns (nekoink U202: 9-14 second-column balls
    without copper). With the channel a free side, no ball within one column of it gets a
    dog-bone, and a ball that escapes towards it has its via on the channel's side."""
    sp, info = _channel_space(tmp_path, monkeypatch)
    laid, wanted = escape.dog_bones(sp, info, log=lambda m: None)
    assert wanted == 16 and laid >= 12          # columns 2 and 3 (and 11, 12), rows 2-5
    nx, ny, p = CH["nx"], CH["ny"], CH["pitch"]
    pos = {f"S{i}_{j}": (i, CH["cx"] + (i - (nx - 1) / 2) * p) for i in range(nx) for j in range(ny)}
    vias = [it for it in sp.routed if it.kind == "via"]
    assert vias
    for v in vias:
        i, bx = pos[v.net]
        assert i in (2, 3, 11, 12), v.net
        j = int(v.net.split("_")[1])
        towards_channel = i in (3, 11) and j in (3, 4)          # ring 3 from the box, 2 from the channel
        side = 1 if i < 7 else -1                               # +x is the channel for the left group
        assert ((v.geom.x - bx) * side > 0) == towards_channel, v.net
