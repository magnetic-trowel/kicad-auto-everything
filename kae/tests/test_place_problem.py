# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""kae.place.problem: what moves, what is fixed, and the rectangles legality is judged on."""
import math
import random
from pathlib import Path

import numpy as np
import shapely

from kae.board import transform
from kae.board.kicad_file import load
from kae.place.cpsat import disjoint_union
from kae.place.problem import Problem, cover_rects, rot_rect, sat, sat_query

FIXTURE = Path(__file__).parent / "data" / "board" / "fixture.kicad_pcb"


def _problem():
    return Problem.build(load(FIXTURE))


def test_movable_fixed_and_obstacles():
    P = _problem()
    parts = {p.ref: p for p in P.parts}
    assert not parts["U6"].movable                   # locked: stays, becomes an obstacle
    assert parts["U7"].movable                       # off-board (staged) but unlocked
    assert all(p.side == p.fp.side for p in P.parts)  # v0 keeps sides
    whys = " ".join(o.why for o in P.obstacles)
    assert "locked U6" in whys
    assert "no_tracks" in whys                       # a rule area that keeps out footprints
    assert "ant_keepout" not in whys                 # a tracks/vias-only rule area does not block parts
    assert set(P.mov) == {p.i for p in P.parts if p.movable}


def test_rects_bound_courtyards_pads_and_pins_in_every_rotation():
    P = _problem()
    g = P.g
    for p in P.parts:
        if not p.movable:
            continue
        assert len(p.rots) == 4
        for r in p.rots:
            ext = transform.courtyard(p.fp, 0.0, 0.0, r.rot, p.side, which="extent")
            if ext:
                bx = shapely.total_bounds(np.asarray(ext, dtype=object))
                assert r.own[0] <= bx[0] + 1e-9 and r.own[1] <= bx[1] + 1e-9
                assert r.own[2] >= bx[2] - 1e-9 and r.own[3] >= bx[3] - 1e-9
            for k, pd in enumerate(p.fp.pads):
                ex, ey = transform.pad_xy(p.fp, pd, 0.0, 0.0, r.rot, p.side)
                assert math.hypot(r.pins[k, 0] - ex, r.pins[k, 1] - ey) < 1e-9
                # every pad centre lies inside the occupancy and the board rectangles
                assert r.own[0] <= ex <= r.own[2] and r.own[1] <= ey <= r.own[3]
                assert r.board[0] <= ex <= r.board[2] and r.board[1] <= ey <= r.board[3]
            a, b, c, d = r.g_own                     # grid rectangles round outward
            assert a * g <= r.own[0] + 1e-9 and b * g >= r.own[2] - 1e-9
            assert c * g <= r.own[1] + 1e-9 and d * g >= r.own[3] - 1e-9


def test_quarter_turns_are_rigid():
    """The rectangle at rotation k+1 is the rectangle at k turned by +90 degrees about the
    origin (macros rotate their members this way)."""
    P = _problem()
    for p in P.parts:
        if not p.movable:
            continue
        for k in range(4):
            a, b, c, d = p.rots[k].g_own
            a2, b2, c2, d2 = p.rots[(k + 1) % 4].g_own
            # (x, y) -> (y, -x): x-range of the turned box is the old y-range, y-range is -x
            assert (a2, b2) == (c, d) and (c2, d2) == (-b, -a)


def test_through_hole_parts_block_the_other_side():
    P = _problem()
    tht = [p for p in P.parts if p.tht]
    smd = [p for p in P.parts if not p.tht and not p.fp.courtyard_back and not p.fp.edge_cuts]
    assert tht and smd
    for p in tht:
        assert p.rots[0].opp, p.ref
    for p in smd:
        assert not p.rots[0].opp, p.ref
    j1 = next(p for p in P.parts if p.ref == "J1")
    assert j1.fp.courtyard_back and j1.rots[0].opp


def test_rot_rect_matches_transform():
    rng = random.Random(3)
    for _ in range(50):
        r = sorted([rng.uniform(-5, 5), rng.uniform(-5, 5)])
        q = sorted([rng.uniform(-5, 5), rng.uniform(-5, 5)])
        rect = (r[0], q[0], r[1], q[1])
        for rot in (0, 90, 180, 270):
            for side in ("F", "B"):
                got = rot_rect(rect, rot, transform.side_sign(side))
                pts = transform.transform_coords([(rect[0], rect[1]), (rect[2], rect[1]), (rect[2], rect[3]),
                                                  (rect[0], rect[3])], 0, 0, rot, side)
                exp = (pts[:, 0].min(), pts[:, 1].min(), pts[:, 0].max(), pts[:, 1].max())
                assert np.allclose(got, exp)


def test_outline_raster_and_cover():
    P = _problem()          # the fixture's outline has rounded corners and two cut-outs
    cov = np.zeros_like(P.inside)
    for (i0, i1, j0, j1) in P.cover:
        assert P.inside[i0:i1, j0:j1].all()
        cov[i0:i1, j0:j1] = True
    assert cov.sum() >= 0.95 * P.inside.sum()
    assert not P.rect_board
    # an L-shaped mask: rectangles stay inside and cover nearly all of it
    m = np.ones((40, 30), dtype=bool)
    m[20:, 15:] = False
    rects = cover_rects(m)
    cov = np.zeros_like(m)
    for (a, b, c, d) in rects:
        assert m[a:b, c:d].all()
        cov[a:b, c:d] = True
    assert cov.sum() >= 0.98 * m.sum() and len(rects) >= 2


def test_sat_counts_outside_cells_and_beyond_grid():
    m = np.zeros((10, 8), dtype=bool)
    m[2:5, 3:6] = True
    S = sat(m)
    assert sat_query(S, 0, 10, 0, 8, 10, 8) == 9
    assert sat_query(S, 2, 3, 3, 4, 10, 8) == 1
    assert sat_query(S, -2, 1, 0, 1, 10, 8) == 2     # cells beyond the grid count as set


def test_disjoint_union_is_exact():
    rng = random.Random(1)
    for _ in range(200):
        rs = []
        for _ in range(rng.randint(1, 7)):
            a, c = rng.randint(0, 15), rng.randint(0, 15)
            rs.append((a, a + rng.randint(1, 6), c, c + rng.randint(1, 6)))
        d = disjoint_union(rs)

        def cells(R):
            return {(i, j) for r in R for i in range(r[0], r[1]) for j in range(r[2], r[3])}
        assert cells(rs) == cells(d)
        assert sum((r[1] - r[0]) * (r[3] - r[2]) for r in d) == len(cells(d))


def test_far_side_smd_copper_blocks_the_other_side():
    """Regression (emberone): an SMD pad with copper on the far side of its footprint (a
    back thermal pad under a front part, *.Cu) must take room there, or a back part lands on
    it with zero clearance while the grid calls the placement legal."""
    b = load(FIXTURE)
    fp = next(f for f in b.footprints if f.ref == "U1")
    pd = next(p for p in fp.pads if not p.drill)
    pd.layers = ["B.Cu", "B.Mask"] if fp.side == "F" else ["F.Cu", "F.Mask"]
    P = Problem.build(b)
    p = next(q for q in P.parts if q.ref == "U1")
    k = fp.pads.index(pd)
    for r in p.rots:
        x, y = r.pins[k]
        assert any(o[0] <= x <= o[2] and o[1] <= y <= o[3] for o in r.opp), r.rot


def test_project_severity_relaxes_courtyards(tmp_path):
    """Regression (stickhub): a project that rates courtyards_overlap 'ignore' lets courtyards
    overlap (KiCad reports no error), so only copper takes room."""
    import json
    import shutil
    src = FIXTURE
    dst = tmp_path / "board.kicad_pcb"
    shutil.copy(src, dst)
    shutil.copy(src.with_suffix(".kicad_dru"), dst.with_suffix(".kicad_dru"))
    pro = json.loads(src.with_suffix(".kicad_pro").read_text())
    pro.setdefault("board", {}).setdefault("design_settings", {})["rule_severities"] = {"courtyards_overlap": "ignore"}
    dst.with_suffix(".kicad_pro").write_text(json.dumps(pro))
    strict = {p.ref: p for p in Problem.build(load(FIXTURE)).parts}
    relaxed_P = Problem.build(load(dst))
    assert not relaxed_P.is_error("courtyards_overlap") and relaxed_P.is_error("clearance")
    relaxed = {p.ref: p for p in relaxed_P.parts}
    shrunk = 0
    for ref, p in strict.items():
        a, r = p.rots[0].own, relaxed[ref].rots[0].own
        assert (r[2] - r[0]) * (r[3] - r[1]) <= (a[2] - a[0]) * (a[3] - a[1]) + 1e-9
        if p.has_courtyard and (r[2] - r[0]) * (r[3] - r[1]) < (a[2] - a[0]) * (a[3] - a[1]) - 1e-6:
            shrunk += 1
    assert shrunk > 0
