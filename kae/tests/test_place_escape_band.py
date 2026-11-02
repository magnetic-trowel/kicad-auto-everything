# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""kae.place.escape_band: the room ball grids and fine-pitch rings need for their escapes."""
from pathlib import Path
from types import SimpleNamespace as NS

from kae.board.kicad_file import load
from kae.place import escape_band as EB
from kae.place.problem import Problem

FIXTURE = Path(__file__).parent / "data" / "board" / "fixture.kicad_pcb"


def _pad(x, y, net, size=0.4):
    return NS(kind="smd", layers=["F.Cu", "F.Paste", "F.Mask"], size=(size, size), lx=x, ly=y, net=net)


def _bga(n=8, pitch=0.8, power=lambda i, j: False):
    """An n x n ball grid centred on the origin; each ball its own signal net unless power(i, j)."""
    off = (n - 1) * pitch / 2
    pads = [_pad(i * pitch - off, j * pitch - off, "GND" if power(i, j) else f"S{i}_{j}")
            for i in range(n) for j in range(n)]
    return NS(pads=pads)


def _qfn(per_side=10, pitch=0.5, span=6.0):
    pads = []
    for k in range(per_side):
        t = (k - (per_side - 1) / 2) * pitch
        pads += [_pad(-span / 2, t, f"L{k}", 0.25), _pad(span / 2, t, f"R{k}", 0.25),
                 _pad(t, -span / 2, f"T{k}", 0.25), _pad(t, span / 2, f"B{k}", 0.25)]
    return NS(pads=pads)


def _kinds(fp):
    return {p.net: ("ground" if p.net == "GND" else "signal") for p in fp.pads}


def test_a_ball_grid_counts_only_its_surface_escapes_per_side():
    fp = _bga()
    pk = EB.package(fp, _kinds(fp), w=0.2, c=0.2)
    assert pk["kind"] == "grid" and abs(pk["pitch"] - 0.8) < 1e-6
    # 0.8 mm pitch, 0.4 mm balls: no track fits between two balls (fit(0.4) = 0), so only the
    # outer ring (28 balls) escapes on the surface: 8 per side, corners on one side each
    assert sum(pk["counts"].values()) == 28
    assert all(6 <= n <= 8 for n in pk["counts"].values())


def test_a_coarser_grid_takes_a_second_ring_to_the_surface():
    fp = _bga(pitch=1.27)
    pk = EB.package(fp, _kinds(fp), w=0.2, c=0.2)
    assert sum(pk["counts"].values()) == 28 + 20          # fit(1.27 - 0.4, 0.2, 0.2) = 1 track: rings 0 and 1
    pk = EB.package(fp, _kinds(fp), w=0.15, c=0.15)
    assert sum(pk["counts"].values()) == 28 + 20 + 12     # narrower rules: 2 tracks, a third ring


def test_power_balls_leave_their_side_open_for_decoupling():
    fp = _bga(power=lambda i, j: i == 7)                   # the +x column is ground
    pk = EB.package(fp, _kinds(fp), w=0.2, c=0.2)
    assert pk["counts"]["R"] == 0 and pk["counts"]["L"] >= 6


def test_a_fine_pitch_ring_escapes_every_signal_pad_and_a_coarse_one_is_left_alone():
    fp = _qfn()
    pk = EB.package(fp, _kinds(fp), w=0.2, c=0.2)
    assert pk["kind"] == "ring" and pk["counts"] == {"L": 10, "T": 10, "R": 10, "B": 10}
    assert EB.package(_qfn(pitch=0.65), _kinds(fp), w=0.2, c=0.2) is None


def test_inner_and_plane_balls_get_a_dog_bone_site_pointing_outward():
    fp = _bga(power=lambda i, j: (i, j) == (0, 0))
    sites = EB.via_sites(fp, _kinds(fp), w=0.2, c=0.2, D=0.45)
    assert len(sites) == 36 + 1                            # the 6 x 6 inner balls and the corner ground ball
    x0, y0, x1, y1 = next(s for s in sites if s[2] < -2.8 and s[3] < -2.8)   # the corner's site, beyond it
    assert abs((x1 - x0) - 0.65) < 1e-9


def _fixture_problem():
    P = Problem.build(load(FIXTURE))
    P.set_margin(0.0)
    return P


def test_a_band_grows_the_occupancy_on_its_sides_in_every_rotation_and_drops_cleanly():
    P = _fixture_problem()
    p = next(q for q in P.parts if q.movable and len(q.fp.pads) > 2)
    exact = [r.g_own for r in p.rots]
    P.set_escape({p.i: (1.0, 0.0, 0.0, 0.0)})              # 1 mm on the library frame's -x side only
    k = round(1.0 / P.g)
    for r, e in zip(p.rots, exact):
        grown = [a - b for a, b in zip((e[0], e[2]), (r.g_own[0], r.g_own[2]))] + \
                [a - b for a, b in zip((r.g_own[1], r.g_own[3]), (e[1], e[3]))]
        assert sorted(grown) == [0, 0, 0, k]               # exactly one side grew, by the band
    P.set_escape(P.escape, on=False)
    assert [r.g_own for r in p.rots] == exact              # dropped: the exact rectangles are back


def test_the_switch_turns_bands_off_and_a_locked_package_becomes_an_obstacle():
    P = _fixture_problem()
    assert EB.bands(P, opts={"escape_band": 0}) == ({}, [])
    fixed = next(q for q in P.parts if not q.movable)
    n0 = len(P.obstacles)
    P.set_escape({fixed.i: (0.5, 0.5, 0.5, 0.5)})
    assert sum(o.why.startswith("escape band") for o in P.obstacles) == 4 and len(P.obstacles) == n0 + 4
    P.set_escape(P.escape, on=False)
    assert len(P.obstacles) == n0


def test_a_connector_row_escapes_away_from_its_body():
    from shapely.geometry import box
    pads = [_pad((k - 7.5) * 0.5, 2.0, f"D{k}", 0.25) for k in range(16)]   # one 0.5 mm row at +y
    fp = NS(pads=pads, courtyard=[box(-5.0, -2.5, 5.0, 2.6)])                # body behind it, at -y
    pk = EB.package(fp, _kinds(fp), w=0.2, c=0.2)
    assert pk["counts"] == {"L": 0, "T": 0, "R": 0, "B": 16}


def test_the_soft_band_prices_only_parts_unrelated_to_the_package():
    P = _fixture_problem()
    kind = {n.name: (n.kind if n.kind in ("ground", "power") else "signal") for n in P.nets}
    pk = max((q for q in P.parts if q.movable), key=lambda q: len(q.fp.pads))
    same = [q for q in P.parts if q.i != pk.i and q.s == pk.s]
    rel = [q for q in same if EB.related(q.fp, pk.fp, kind)]
    unrel = [q for q in same if not EB.related(q.fp, pk.fp, kind) and not getattr(q, "decor", False)]
    assert rel and unrel
    g = EB.escape_grid(P, {pk.i: (1.0, 1.0, 1.0, 1.0)}, weight=2.0)
    side, srcs, _ = g[pk.i]
    assert len(srcs) == len(pk.rots) and all(len(s) == 4 for s in srcs)        # one rect per side
    assert all(r[4] == EB.BAND_CLASS and r[5] == 2.0 for s in srcs for r in s)
    assert all(q.i not in g or not any(g[q.i][2]) for q in rel)                # related: no target
    assert all(any(t[4] == EB.BAND_CLASS for t in g[q.i][2][0]) for q in unrel)


def test_a_placement_with_soft_bands_reports_the_term(monkeypatch):
    from kae.place.pipeline import place
    calls = {}

    def bands(P, board_path=None, opts=None, log=None):      # the fixture has no fine-pitch package
        pk = max((q for q in P.parts if q.movable), key=lambda q: len(q.fp.pads))
        calls["P"] = P
        return {pk.i: (0.5, 0.5, 0.5, 0.5)}, [dict(ref=pk.ref)]
    monkeypatch.setattr(EB, "bands", bands)
    res = place(load(FIXTURE), seed=0, time_s=8.0, physics=False, workers=1, opts={"escape_band": 1})
    assert res.report["escape_term"]["packages"] == 1
    assert not getattr(calls["P"], "escape_on", False)       # soft: the occupancy is untouched


def test_a_small_wafer_level_grid_is_a_grid_not_a_ring():
    fp = _bga(n=3, pitch=0.4)                     # 3 x 3 sites; add a fourth column: a 12-ball 3 x 4 WLP
    fp.pads += [_pad(0.8, (j - 1) * 0.4, f"X{j}", 0.24) for j in range(3)]
    for p in fp.pads:
        p.size = (0.24, 0.24)
    pk = EB.package(fp, _kinds(fp), w=0.2, c=0.2)
    assert pk["kind"] == "grid" and abs(pk["pitch"] - 0.4) < 1e-6
    assert sum(pk["counts"].values()) == 10       # the 2 interior balls go down their dog-bones
    assert EB._grid([(x * 0.5, 0.0) for x in range(6)] + [(x * 0.5, 0.5) for x in range(6)]) is None  # 2 rows


def test_a_hollow_ring_is_not_a_small_grid():
    fp = _qfn(per_side=3, pitch=0.4, span=1.6)    # 12 pads round an empty middle
    assert EB._grid([(p.lx, p.ly) for p in fp.pads]) is None


def test_utilization_counts_each_parts_occupancy_once():
    from shapely.geometry import box
    from shapely.ops import unary_union
    P = _fixture_problem()
    want = [0.0, 0.0]
    for p in P.parts:
        r = p.rots[0]
        g = unary_union([box(*x) for x in (r.own_rects or (r.own,))])
        if not p.movable:
            from shapely.affinity import translate
            g = translate(g, p.x0, p.y0).intersection(P.outline)
        want[0 if p.s > 0 else 1] += g.area
        if r.opp:
            g = unary_union([box(*o) for o in r.opp])
            if not p.movable:
                g = translate(g, p.x0, p.y0).intersection(P.outline)
            want[1 if p.s > 0 else 0] += g.area
    got = P.utilization()
    assert all(abs(a - b / P.outline.area) < 1e-9 for a, b in zip(got, want))


def test_a_surface_mount_body_is_never_relaxed():
    P = _fixture_problem()
    relaxed = set(P.relax_bodies())
    smd = {p.ref for p in P.parts if p.fp.pads and all(pd.kind in ("smd", "connect") for pd in p.fp.pads)}
    assert smd and not (relaxed & smd)
