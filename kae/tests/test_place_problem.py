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


def test_free_angles_keep_right_angles_first_and_rects_conservative():
    """--angles: parts that may turn freely get every multiple of the step after the four
    right angles; quarter-turn and ring tables stay consistent; odd-angle rectangles contain
    the turned courtyard and pads (grid-legal stays legal at the actual angle)."""
    P = Problem.build(load(FIXTURE), angle_step=45.0)
    for p in P.parts:
        if not p.movable:
            assert len(p.rots) == 1
            continue
        angles = [r.rot % 360.0 for r in p.rots]
        assert angles[:4] == [0.0, 90.0, 180.0, 270.0] and p.n_ortho == 4
        assert sorted(angles) == [0.0, 45.0, 90.0, 135.0, 180.0, 225.0, 270.0, 315.0]
        for k, a in enumerate(angles):
            for q in range(4):
                assert abs((angles[p.turn[k][q]] - a - 90.0 * q) % 360.0) < 1e-9
            prv, nxt = p.ring[k]
            assert abs((angles[nxt] - a) % 360.0 - 45.0) < 1e-9 and abs((a - angles[prv]) % 360.0 - 45.0) < 1e-9
        for r in p.rots[4:]:
            poly = transform.courtyard(p.fp, 0.0, 0.0, r.rot, p.side, which="own")
            if poly:
                gx0, gy0, gx1, gy1 = shapely.union_all(poly).bounds
                o = r.own
                assert o[0] <= gx0 + 1e-6 and o[1] <= gy0 + 1e-6 and gx1 <= o[2] + 1e-6 and gy1 <= o[3] + 1e-6
            for x, y in r.pins:
                assert r.own[0] - 1e-6 <= x <= r.own[2] + 1e-6 and r.own[1] - 1e-6 <= y <= r.own[3] + 1e-6


def test_heatsink_mount_packages_keep_right_angles():
    from kae.place.problem import right_angles_only
    b = load(FIXTURE)
    fp = next(f for f in b.footprints if f.ref == "U1")
    assert not right_angles_only(fp)
    fp.lib_id = "Package_TO_SOT_THT:TO-220-3_Vertical"
    pd = fp.pads[0]
    pd.drill, pd.kind, pd.size = 3.2, "np_thru_hole", (3.5, 3.5)
    assert right_angles_only(fp)
    P = Problem.build(b, angle_step=15.0)
    assert len(next(p for p in P.parts if p.ref == "U1").rots) == 4


def test_cluster_rects_is_fast_and_keeps_rows():
    """Regression (latentred-linecard): clustering a 676-ball BGA's pads to 4 groups took the
    O(n^3) pairwise loop minutes (461 s of Problem.build); it is vectorized now."""
    import time as _time
    from kae.place.problem import _cluster_rects
    pads = [(x * 1.0, y * 1.0, x * 1.0 + 0.4, y * 1.0 + 0.4) for x in range(26) for y in range(26)]
    t0 = _time.monotonic()
    out = _cluster_rects(pads, max_n=4)
    assert len(out) == 4 and _time.monotonic() - t0 < 5.0
    for (x0, y0, x1, y1) in pads:                     # every pad stays covered
        assert any(a <= x0 and b <= y0 and x1 <= c and y1 <= d for (a, b, c, d) in out)
    rows = [(x * 2.54, 0, x * 2.54 + 1.7, 1.7) for x in range(10)] + \
        [(x * 2.54, 2.54, x * 2.54 + 1.7, 4.24) for x in range(10)]
    assert sorted(_cluster_rects(rows, 2)) == [(0.0, 0.0, 24.56, 1.7), (0.0, 2.54, 24.56, 4.24)]
    assert sorted(_cluster_rects([(0, 0, 1, 1), (1, 0, 2, 1), (5, 5, 6, 6)])) == [(0, 0, 2, 1), (5, 5, 6, 6)]


def test_occupancy_pieces_follow_an_l_shaped_courtyard():
    """Regression (obsidian): one box per footprint swallowed the space inside L-shaped
    courtyards and between a module's pin rows; occupancy is now pieces (a cover of the
    courtyard, pad groups outside it) and the box only frames them."""
    from shapely.geometry import Polygon
    b = load(FIXTURE)
    fp = next(f for f in b.footprints if f.ref == "U1")
    x0, y0, x1, y1 = shapely.union_all(fp.courtyard).bounds
    w, h = x1 - x0, y1 - y0
    L = Polygon([(x0, y0), (x1, y0), (x1, y0 + h / 3), (x0 + w / 3, y0 + h / 3), (x0 + w / 3, y1), (x0, y1)])
    fp.courtyard = [L]
    P = Problem.build(b)
    p = next(q for q in P.parts if q.ref == "U1")
    pieces = p.rots[0].own_rects
    assert len(pieces) >= 2
    union = shapely.union_all([shapely.box(*r) for r in pieces])
    assert union.buffer(1e-6).contains(L)                       # the courtyard stays covered
    assert all(union.contains(shapely.Point(q.lx, q.ly)) for q in fp.pads)   # and the copper
    assert union.area < 0.9 * w * h                              # but not the whole box:
    assert not union.contains(shapely.Point(x1 - 0.05, y1 - 0.05))   # the notch corner is free
    st_rects = [k for _, _, k in __import__("kae.place.state", fromlist=["State"]).State(P).grid_rects(p.i)]
    assert st_rects.count("own") == len(pieces)


def test_relaxing_bodies_frees_a_locked_module_too():
    """Regression (obsidian): a locked courtyard-less module (an Arduino under its shield)
    kept its whole body as an obstacle when the board was too full; relax_bodies now frees
    locked bodies too, keeping their pads."""
    from shapely.geometry import box as sbox
    b = load(FIXTURE)
    fp = next(f for f in b.footprints if f.ref == "U6")          # locked in the fixture
    fp.courtyard = []
    fp.body = [sbox(-8, -8, 8, 8)]
    P = Problem.build(b)
    big = sum((o.g[1] - o.g[0]) * (o.g[3] - o.g[2]) for o in P.obstacles if "U6" in o.why)
    assert P.relax_bodies()
    small = sum((o.g[1] - o.g[0]) * (o.g[3] - o.g[2]) for o in P.obstacles if "U6" in o.why)
    assert 0 < small < 0.5 * big


def _state_at_input(P):
    from kae.place.state import State
    st = State(P)
    for p in P.parts:
        if p.movable:
            st.X[p.i], st.Y[p.i] = P.grid_of(p.x0, p.y0)
            st.K[p.i] = min(range(len(p.rots)), key=lambda k: abs(((p.rots[k].rot - p.rot0) + 180) % 360 - 180))
    return st


def _with_owned_keepouts(b, layers=("F.Cu",)):
    """U2 (front, 90 deg at (20, 10)) owns a pads/footprints keepout to its right and one
    over itself (its own pads inside: KiCad does not apply it to them)."""
    from shapely.geometry import box as sbox
    from kae.board.model import Keepout
    u2 = next(f for f in b.footprints if f.ref == "U2")
    for n, r in (("right", (22.5, 8.0, 25.5, 12.0)), ("self", (18.0, 8.0, 22.0, 12.0))):
        b.keepouts.append(Keepout(uuid=f"ko-{n}", name=n, layers=list(layers), outline=sbox(*r), pads=True,
                                  footprints=True, footprint=u2.uuid))
    return b


def test_footprint_rule_area_moves_with_its_part():
    """Regression (obsidian): a rule area owned by a footprint (keepout under a module or
    beside a sensor) was a fixed obstacle where the input board had the footprint, and the
    exact check looked for it there too; KiCad moves it with the part and does not apply it
    to the part's own items. It is now part of the owner's occupancy (pieces) and moves."""
    from kae.place.legalize import exact_check
    b = _with_owned_keepouts(load(FIXTURE))
    P = Problem.build(b)
    assert not any(o.why in ("keepout right", "keepout self") for o in P.obstacles)
    u2 = next(p for p in P.parts if p.ref == "U2")
    k90 = next(k for k, r in enumerate(u2.rots) if r.rot == 90.0)
    pieces = shapely.union_all([shapely.box(*(np.add(r, (u2.x0, u2.y0, u2.x0, u2.y0)))) for r in u2.rots[k90].own_rects])
    assert pieces.buffer(1e-6).contains(shapely.box(22.5, 8.0, 25.5, 12.0))
    st = _state_at_input(P)
    ref = {p.ref: p.i for p in P.parts}
    assert not [v for v in exact_check(P, st) if v["type"] == "items_not_allowed"]   # own pads exempt
    # move U2 by (+10, +10): its keepout follows, the old place is free
    st.X[ref["U2"]] += int(round(10 / P.g))
    st.Y[ref["U2"]] += int(round(10 / P.g))
    st.X[ref["U1"]], st.Y[ref["U1"]] = P.grid_of(34.0, 20.0)
    hits = [v for v in exact_check(P, st) if v["type"] == "items_not_allowed"]
    assert hits and all(v["refs"] == ["U1"] for v in hits)
    st.X[ref["U1"]], st.Y[ref["U1"]] = P.grid_of(24.0, 10.0)
    assert not [v for v in exact_check(P, st) if v["type"] == "items_not_allowed"]


def test_rule_areas_follow_project_severity_and_copper_layers(tmp_path):
    """items_not_allowed rated warning (obsidian's project) makes rule areas no obstacle and
    no finding; a rule area only on non-copper layers (a library keepout on Dwgs.User) applies
    to no side (it used to block both)."""
    import json
    import shutil
    from shapely.geometry import box as sbox
    from kae.board.model import Keepout
    from kae.place.legalize import exact_check
    dst = tmp_path / "board.kicad_pcb"
    shutil.copy(FIXTURE, dst)
    shutil.copy(FIXTURE.with_suffix(".kicad_dru"), dst.with_suffix(".kicad_dru"))
    pro = json.loads(FIXTURE.with_suffix(".kicad_pro").read_text())
    pro.setdefault("board", {}).setdefault("design_settings", {})["rule_severities"] = {"items_not_allowed": "warning"}
    dst.with_suffix(".kicad_pro").write_text(json.dumps(pro))
    P = Problem.build(_with_owned_keepouts(load(dst)))
    assert not P.is_error("items_not_allowed")
    u2 = next(p for p in P.parts if p.ref == "U2")
    bare = next(p for p in Problem.build(load(dst)).parts if p.ref == "U2")
    assert u2.rots[0].own_rects == bare.rots[0].own_rects
    assert not any("keepout" in o.why for o in P.obstacles)
    st = _state_at_input(P)
    ref = {p.ref: p.i for p in P.parts}
    st.X[ref["U1"]], st.Y[ref["U1"]] = P.grid_of(24.0, 10.0)
    assert not [v for v in exact_check(P, st) if v["type"] == "items_not_allowed"]
    b = load(FIXTURE)
    b.keepouts.append(Keepout(uuid="ko-dwgs", name="dwgs", layers=["Dwgs.User"], outline=sbox(20, 20, 30, 30),
                              pads=True, footprints=True))
    assert not any(o.why == "keepout dwgs" for o in Problem.build(b).obstacles)


def test_padless_footprint_and_far_side_lands_take_no_room_on_the_near_side():
    """Regression (myra-sip-interposer): a mechanical lid (no pads, no courtyard) took its
    body's room, the whole board, and relax_bodies skipped parts without pads; an LGA
    footprint on F whose lands are all on B.Cu took room on the front."""
    from shapely.geometry import box as sbox
    from kae.place.problem import POINT
    b = load(FIXTURE)
    s1 = next(f for f in b.footprints if f.ref == "S1")
    s1.pads, s1.courtyard, s1.edge_cuts, s1.body = [], [], [], [sbox(-20, -20, 20, 20)]
    u1 = next(f for f in b.footprints if f.ref == "U1")
    u1.courtyard = []
    for pd in u1.pads:
        pd.layers, pd.kind, pd.drill = ["B.Cu", "B.Mask"], "smd", 0.0
    P = Problem.build(b)
    parts = {p.ref: p for p in P.parts}
    assert parts["S1"].rots[0].own_rects != (POINT,)    # a logo's graphics may bridge pads
    P.relax_bodies()                                    # a crowded board frees it
    assert parts["S1"].rots[0].own_rects == (POINT,)
    u = parts["U1"]
    assert u.rots[0].own_rects == (POINT,)
    assert u.rots[0].opp                     # its lands occupy the back


def test_mask_and_copper_graphics_take_room_and_are_checked():
    """Regression (stickhub): logos' and LEDs' mask apertures bridged other parts' pads
    (KiCad solder_mask_bridge) because footprint graphics were not in the model. A mask
    graphic now takes room on its side and the exact check reports a pad under it."""
    from shapely.geometry import box as sbox
    from kae.place.legalize import exact_check
    b = load(FIXTURE)
    u1 = next(f for f in b.footprints if f.ref == "U1")       # front, 0 deg at (10, 10)
    u1.graphics = {"F.Mask": [sbox(3.0, -1.0, 5.0, 1.0)]}      # beyond its courtyard (x < 1.9)
    P = Problem.build(b)
    p = next(q for q in P.parts if q.ref == "U1")
    pieces = shapely.union_all([shapely.box(*r) for r in p.rots[0].own_rects])
    assert pieces.contains(shapely.box(3.0, -1.0, 5.0, 1.0))
    st = _state_at_input(P)
    ref = {q.ref: q.i for q in P.parts}
    u7 = P.parts[ref["U7"]]
    pad = u7.fp.pads[2]                                        # put a U7 pad under the aperture
    st.X[u7.i], st.Y[u7.i] = P.grid_of(14.0 - pad.lx, 10.0 - pad.ly)
    st.K[u7.i] = 0
    hits = [v for v in exact_check(P, st, max_items=500) if v["type"] == "solder_mask_bridge"]
    assert hits and all(set(v["refs"]) == {"U1", "U7"} for v in hits)
