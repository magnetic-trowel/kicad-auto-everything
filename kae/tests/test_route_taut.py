# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""kae.route.taut_geom and kae.route.arcs: tangents to discs, arcs, homotopic shortest paths
(the path never jumps an obstacle, it is the analytic optimum where one is known, a second
solve gains nothing), the exact checks, and the board pass's fixed nets."""
import math
import random

import pytest
from shapely.geometry import LineString, Point, box

from kae.route import arcs as A
from kae.route import taut_geom as G


# ----------------------------------------------------------------------------- tangents
@pytest.mark.parametrize("s1,s2", [(1, 1), (-1, -1), (1, -1), (-1, 1)])
def test_tangent_touches_both_circles_and_is_perpendicular_to_radii(s1, s2):
    c1, r1, c2, r2 = (0.0, 0.0), 1.0, (5.0, 1.0), 0.7
    p1, p2 = G.tangent(c1, r1, s1, c2, r2, s2)
    assert math.dist(p1, c1) == pytest.approx(r1)
    assert math.dist(p2, c2) == pytest.approx(r2)
    u = ((p2[0] - p1[0]), (p2[1] - p1[1]))
    # radius perpendicular to the tangent at both ends
    assert (p1[0] - c1[0]) * u[0] + (p1[1] - c1[1]) * u[1] == pytest.approx(0.0, abs=1e-9)
    assert (p2[0] - c2[0]) * u[0] + (p2[1] - c2[1]) * u[1] == pytest.approx(0.0, abs=1e-9)
    # side: s = +1 puts the centre on the left of the travel direction
    left1 = (-u[1]) * (c1[0] - p1[0]) + u[0] * (c1[1] - p1[1])
    left2 = (-u[1]) * (c2[0] - p2[0]) + u[0] * (c2[1] - p2[1])
    assert math.copysign(1, left1) == s1 and math.copysign(1, left2) == s2
    # tangent lengths: sqrt(D^2 - (r2 - r1)^2) outer, sqrt(D^2 - (r1 + r2)^2) inner
    L = math.dist(p1, p2)
    D = math.dist(c1, c2)
    if s1 == s2:
        assert L == pytest.approx(math.sqrt(D * D - (r2 - r1) ** 2))
    else:
        assert L == pytest.approx(math.sqrt(D * D - (r1 + r2) ** 2))


def test_tangent_from_a_point_and_impossible_tangents():
    p1, p2 = G.tangent((-3.0, 0.0), 0.0, 0, (0.0, 0.0), 1.0, -1)
    assert p1 == (-3.0, 0.0)
    assert math.dist(p1, p2) == pytest.approx(math.sqrt(8))
    assert G.tangent((0, 0), 1.0, 1, (1.0, 0), 1.0, -1) is None        # overlapping discs: no inner tangent
    assert G.tangent((0, 0), 2.0, 1, (0.5, 0), 0.5, 1) is None         # one inside the other
    assert G.tangent((0, 0), 0.0, 0, (0.5, 0), 1.0, 1) is None         # a point inside a disc


# ----------------------------------------------------------------------------- arcs
def test_arc_round_trip_and_sampling():
    c, r, a0, sw = (1.0, 2.0), 0.8, 0.3, -2.1
    s, m, e = A.csa_to_sme(c, r, a0, sw)
    c2, r2, b0, sw2 = A.sme_to_csa(s, m, e)
    assert math.dist(c, c2) < 1e-9 and r2 == pytest.approx(r)
    assert sw2 == pytest.approx(sw) and A.norm_angle(b0 - a0) == pytest.approx(0.0, abs=1e-9)
    pts = A.arc_coords(c, r, a0, sw)
    assert pts[0] == pytest.approx(s) and pts[-1] == pytest.approx(e)
    # every chord's sagitta is within SAG
    for p, q in zip(pts[:-1], pts[1:]):
        mid = ((p[0] + q[0]) / 2, (p[1] + q[1]) / 2)
        assert r - math.dist(mid, c) <= A.SAG + 1e-12
    assert A.arc_length(r, sw) == pytest.approx(r * 2.1)
    # a large positive sweep (more than half a turn) survives the round trip
    s, m, e = A.csa_to_sme(c, r, 0.0, 4.0)
    assert A.sme_to_csa(s, m, e)[3] == pytest.approx(4.0)


def test_arc_sexpr_is_kicad_arc():
    txt = A.arc_sexpr("GND", "F.Cu", 0.25, (1, 2), (1.5, 2.5), (2, 2), uid="u")
    assert txt.startswith("\t(arc") and "(mid 1.5 2.5)" in txt and '(net "GND")' in txt and "(width 0.25)" in txt


# ----------------------------------------------------------------------------- shortest homotopic paths
def _space(obs, pts, margin=1.0):
    win = G.convex_window(pts, margin)

    def check(pieces):
        bad = []
        for i, p in enumerate(pieces):
            g = LineString(A.piece_coords(p))
            for oi, o in enumerate(obs):
                if o.core.distance(g) < o.R - A.SAG - 1e-7:
                    bad.append((i, oi))
                    break
        return bad
    return G.BranchSpace(obs, win, check=check)


def _winding(closed, c):
    """Winding number of the closed polyline around point c."""
    tot = 0.0
    for p, q in zip(closed[:-1], closed[1:]):
        a = math.atan2(p[1] - c[1], p[0] - c[0])
        b = math.atan2(q[1] - c[1], q[0] - c[0])
        tot += A.norm_angle(b - a)
    return round(tot / (2 * math.pi))


def test_single_disc_optimum_both_sides():
    obs = [G.make_obstacle(Point(0, 0), 1.0)]
    want = 2 * math.sqrt(8) + (math.pi - 2 * math.acos(1 / 3))
    for mid_y in (2.0, -2.0):
        pts = [(-3, 0), (-1, mid_y), (1, mid_y), (3, 0)]
        r = _space(obs, pts).solve(pts)
        assert r.length == pytest.approx(want, rel=1e-9)
        arc = [p for p in r.pieces if p[0] == "arc"]
        assert len(arc) == 1
        # the arc runs on the side the input passed
        mid = A.arc_coords(*arc[0][1:])[len(A.arc_coords(*arc[0][1:])) // 2]
        assert math.copysign(1, mid[1]) == math.copysign(1, mid_y)
        assert r.certificate["g1"]


def test_path_between_two_discs_keeps_its_slalom():
    # above A, below B: the optimum is tangent - arc - inner tangent - arc - tangent
    obs = [G.make_obstacle(Point(-2, 0), 1.0), G.make_obstacle(Point(2, 0), 1.0)]
    pts = [(-5, 0), (-2, 2), (0, 0), (2, -2), (5, 0)]
    r = _space(obs, pts).solve(pts)
    kinds = [p[0] for p in r.pieces]
    assert kinds == ["seg", "arc", "seg", "arc", "seg"]
    assert r.certificate["g1"]
    # the input and the result bound no obstacle between them (same homotopy class)
    out = A.pieces_coords(r.pieces)
    loop = list(pts) + out[::-1]
    for o in obs:
        assert _winding(loop, (o.core.x, o.core.y)) == 0
    # and it is shorter than going straight past either side
    assert r.length < LineString(pts).length


def test_square_pad_corners_are_separate_atoms():
    # a rectangle's corners are co-circular; they must not merge into one circle
    ob = G.make_obstacle(box(-0.85, -0.85, 0.85, 0.85), 0.3)
    assert len(ob.atoms) == 4
    assert all(r == pytest.approx(0.3) for _, r in ob.atoms)
    # a polygonised circle merges into one atom of radius circle + R
    circ = Point(0, 0).buffer(0.5, quad_segs=16)
    ob2 = G.make_obstacle(circ, 0.2)
    assert len(ob2.atoms) <= 2
    assert max(r for _, r in ob2.atoms) == pytest.approx(0.7, abs=1e-3)


def test_wrap_around_a_rounded_rectangle_is_exact():
    pad = box(-1, -0.5, 1, 0.5)
    obs = [G.make_obstacle(pad, 0.25)]
    pts = [(-2, 0), (-1.5, 1.2), (1.5, 1.2), (2, 0)]
    r = _space(obs, pts).solve(pts)
    # analytic: point (-2,0) to corner disc (-1,0.5) r .25, flat top at y=.75, symmetric
    d = math.dist((-2, 0), (-1, 0.5))
    t = math.sqrt(d * d - 0.25 ** 2)
    # turning: from the tangent direction to horizontal
    phi = math.atan2(0.5, 1.0) + math.asin(0.25 / d)
    want = 2 * t + 2 * 0.25 * phi + 2.0
    assert r.length == pytest.approx(want, rel=1e-6)


@pytest.mark.parametrize("seed", range(12))
def test_random_discs_never_jumped_and_idempotent(seed):
    rnd = random.Random(seed)
    discs = []
    while len(discs) < 9:
        c = (rnd.uniform(-4, 4), rnd.uniform(-3, 3))
        r = rnd.uniform(0.2, 0.7)
        if all(math.dist(c, d) > r + q + 0.3 for d, q in discs) and math.dist(c, (-6, 0)) > 1 and math.dist(c, (6, 0)) > 1:
            discs.append((c, r))
    obs = [G.make_obstacle(Point(c), r) for c, r in discs]
    # a random legal input: a zig-zag through free sample points
    free = [(x, y) for x, y in ((rnd.uniform(-5, 5), rnd.uniform(-3.5, 3.5)) for _ in range(400))
            if all(math.dist((x, y), c) > r + 0.05 for c, r in discs)]
    pts = [(-6.0, 0.0)]
    for p in free:
        if len(pts) > 6:
            break
        seg = LineString([pts[-1], p])
        if all(seg.distance(Point(c)) > r + 0.02 for c, r in discs) and p[0] > pts[-1][0]:
            pts.append(p)
    seg = LineString([pts[-1], (6.0, 0.0)])
    if not all(seg.distance(Point(c)) > r + 0.02 for c, r in discs):
        pytest.skip("no simple random input for this seed")
    pts.append((6.0, 0.0))
    bs = _space(obs, pts)
    r = bs.solve(pts)
    assert r is not None
    out = A.pieces_coords(r.pieces)
    # legal everywhere (to the sampling)
    line = LineString(out)
    for c, rad in discs:
        assert line.distance(Point(c)) >= rad - A.SAG - 1e-7
    # same homotopy class: input + reversed output winds around no obstacle
    loop = list(pts) + out[::-1]
    for c, _ in discs:
        assert _winding(loop, c) == 0
    assert r.length <= LineString(pts).length + 1e-9
    assert r.certificate["g1"]
    # optimal: solving the result again gains nothing
    r2 = _space(obs, out).solve(out)
    assert r2.length == pytest.approx(r.length, abs=1e-6)


def test_wraps_with_backward_sweep_are_dropped():
    # a disc the polygonal path grazes but the exact path does not touch
    nodes = [G.Wrap((0, 0)), G.Wrap((5, -0.2), 0.1, -1, 0.0), G.Wrap((10, 0))]
    pieces, kept, _ = G.solve_wraps(nodes)
    assert len(kept) == 2 and [p[0] for p in pieces] == ["seg"]


# ----------------------------------------------------------------------------- pieces, merging
def test_merge_tiny_arcs_and_collinear_segments():
    from kae.route.taut import _merge_tiny
    pieces = [("seg", (0, 0), (1, 0)), ("arc", (1, 1), 1.0, -math.pi / 2, 0.001), ("seg", (1.001, 0.0000005), (2, 0))]
    out = _merge_tiny(pieces)
    assert all(p[0] == "seg" for p in out)
    assert out[0][1] == (0, 0) and out[-1][2] == (2, 0)


def test_acute_corner_count():
    from kae.route.taut import _acute_corners
    assert _acute_corners([("seg", (0, 0), (1, 0)), ("seg", (1, 0), (0, 0.5))]) == 1
    assert _acute_corners([("seg", (0, 0), (1, 0)), ("seg", (1, 0), (2, 1))]) == 0


# ----------------------------------------------------------------------------- the board pass (KiCad)
def _tp(ref, net, x, y):
    return (ref, "TP", "TestPoint:TestPoint_Pad_1.0x1.0mm", x, y, 0.0,
            [("1", net, 0.0, 0.0, 1.0, 1.0, "smd", 0.0, "", "passive")], (0.7, 0.7))


def _detour_board(tmp_path):
    """The critical-router fixture plus four 2-point nets, each routed with a detour: SIGA (free to
    tighten), the pair USB_D+/USB_D- (left alone), LEN1 (a length rule: left alone)."""
    import critical_fixtures as F
    from kae.route import critical_write as W
    extra = [_tp("TP1", "SIGA", 103.0, 103.0), _tp("TP2", "SIGA", 118.0, 103.0),
             _tp("TP3", "USB_D+", 121.0, 103.0), _tp("TP4", "USB_D+", 137.0, 103.0),
             _tp("TP5", "USB_D-", 121.0, 105.0), _tp("TP6", "USB_D-", 137.0, 105.0),
             _tp("TP7", "LEN1", 103.0, 105.0), _tp("TP8", "LEN1", 118.0, 105.0),
             _tp("TP9", "ETH_P", 103.0, 128.0), _tp("TP10", "ETH_P", 125.0, 128.0),
             _tp("TP11", "ETH_N", 103.0, 126.0), _tp("TP12", "ETH_N", 125.0, 126.0)]
    src = F.write_board(tmp_path / "in", extra=extra)
    (src.with_suffix(".kicad_dru")).write_text(
        '(version 1)\n(rule "len1"\n\t(condition "A.NetName == \'LEN1\'")\n\t(constraint length (min 5mm) (max 40mm))\n)\n')

    def path(net, pts):
        return [(net, "F.Cu", 0.25, a, b, W.new_uuid(), False) for a, b in zip(pts[:-1], pts[1:])]
    tracks = path("SIGA", [(103, 103), (107, 103), (108.4, 101.6), (112.6, 101.6), (114, 103), (118, 103)])
    tracks += path("USB_D+", [(121, 103), (125, 103), (126.4, 101.6), (131.6, 101.6), (133, 103), (137, 103)])
    tracks += path("USB_D-", [(121, 105), (125, 105), (126.4, 103.9), (131.6, 103.9), (133, 105), (137, 105)])
    tracks += path("LEN1", [(103, 105), (107, 105), (108.1, 104.2), (112.9, 104.2), (114, 105), (118, 105)])
    # a coupled pair (0.5 mm pitch) with a common detour down: tightened as a pair
    centre = LineString([(105, 127), (108, 127), (109.5, 128.2), (116.5, 128.2), (118, 127), (123, 127)])
    legs = {}
    for net, o in (("ETH_N", -0.25), ("ETH_P", 0.25)):      # shapely: positive offsets lie to the left (+y here)
        g = centre.offset_curve(o, join_style="mitre")
        cs = [tuple(c) for part in getattr(g, "geoms", [g]) for c in part.coords]
        legs[net] = [c for k, c in enumerate(cs) if k == 0 or math.dist(c, cs[k - 1]) > 1e-9]
    tracks += path("ETH_N", [(103, 126)] + legs["ETH_N"] + [(125, 126)])
    tracks += path("ETH_P", [(103, 128)] + legs["ETH_P"] + [(125, 128)])
    out = tmp_path / "routed" / "board.kicad_pcb"
    out.parent.mkdir()
    W.append_items(src, out, tracks=tracks)
    for ext in (".kicad_pro", ".kicad_dru"):
        (out.with_suffix(ext)).write_text(src.with_suffix(ext).read_text())
    return out


@pytest.mark.kicad
def test_taut_board_pass(tmp_path):
    from kae.board import pcbnew_io
    if not pcbnew_io.available():
        pytest.skip("no Python with pcbnew")
    from kae.board.kicad_file import load
    from kae.route import taut
    src = _detour_board(tmp_path)
    before = load(src)
    rep = taut.run(src, tmp_path / "out.kicad_pcb", workdir=tmp_path / "w", log=lambda *a: None)
    after = load(tmp_path / "out.kicad_pcb")
    # DRC no worse
    for t, n in rep["drc_out"]["by_type"].items():
        assert n <= rep["drc_in"]["by_type"].get(t, 0)
    assert rep["drc_out"]["unconnected"] <= rep["drc_in"]["unconnected"]
    # converged: the last pass shortened no net by more than conv_eps
    assert rep["stats"]["passes"][-1]["max_net_gain_mm"] <= taut.DEFAULTS["conv_eps"]

    def tracks(b, net):
        return sorted((t.start, t.end, t.mid) for t in b.tracks if t.net == net)

    def length(b, net):
        return sum(A.track_length(t) for t in b.tracks if t.net == net)
    # the free net is now (nearly) the straight line between its pads, entering each pad perpendicular
    assert "SIGA" in rep["nets_changed"]
    assert length(after, "SIGA") < 15.0 + 1e-6 < length(before, "SIGA")
    st = taut.board_stats(tmp_path / "out.kicad_pcb")
    assert st["acute_entries"] == 0
    for t in after.tracks:
        if t.net == "SIGA" and t.mid is None:
            assert abs(t.start[1] - 103.0) < 1e-6 and abs(t.end[1] - 103.0) < 1e-6
    # a diff pair and a length-ruled net are untouched
    for net in ("USB_D+", "USB_D-", "LEN1"):
        assert tracks(after, net) == tracks(before, net), net
    assert rep["fixed"].get("diff pair") == 4 and rep["fixed"].get("length rule") == 1
    # the coupled pair: shorter, still at its pitch along the coupled section, skew not worse
    if "ETH_P" in rep["nets_changed"]:
        assert "ETH_N" in rep["nets_changed"]
        assert length(after, "ETH_P") < length(before, "ETH_P")
        skew0 = abs(length(before, "ETH_P") - length(before, "ETH_N"))
        skew1 = abs(length(after, "ETH_P") - length(after, "ETH_N"))
        assert skew1 <= skew0 + 5e-3
        lp = LineString([p for t in after.tracks if t.net == "ETH_P" for p in A.track_coords(t)])
        ln = [t for t in after.tracks if t.net == "ETH_N"]
        for t in ln:
            for q in A.track_coords(t)[1:-1]:
                if 106 < q[0] < 122:
                    assert lp.distance(Point(q)) == pytest.approx(0.5, abs=0.02)
    assert rep["stats"].get("pairs_improved", 0) >= 1


def test_fillet_turns_an_acute_anchor_into_a_tangent_arc():
    from kae.route.taut import _acute_corners, _fillet_anchors
    # a tail along +x ending at (0, 0); the target lies behind it: a corner of about 135 degrees
    head = [(-0.5, 0.0), (0.0, 0.0)]
    tail = [(-3.0, 1.0)]
    bs = _space([], [(0, 0), (-3, 1)], margin=2.0)
    r = bs.solve([(0.0, 0.0), (-3.0, 1.0)])
    pieces = [("seg", head[0], head[1])] + r.pieces
    assert _acute_corners(pieces) == 1
    r2 = _fillet_anchors(r, head, tail, 0.25, bs.check)
    pieces2 = [("seg", head[0], head[1])] + r2.pieces
    assert _acute_corners(pieces2) == 0
    assert r2.pieces[0][0] == "arc" and G.g1_defects(pieces2) == []


# ----------------------------------------------------------------------------- tails into lands narrower than the track
def _fake_taut(currents=None, min_w=0.1):
    from types import SimpleNamespace
    from kae.route import power_copper as PC
    from kae.route.taut import Taut

    class _SP:
        def width_limits(self, net, layer):
            return (min_w, 0.2, None)
    t = SimpleNamespace(PC=PC, sp=_SP(), hazards=[], _flagged=set(), stats={})
    t._pad_current = lambda pd, net: (currents or {}).get(net, 0.0)
    t._land_targets = lambda *a: Taut._land_targets(t, *a)
    return t


def test_taut_tails_use_pad_entry_overhang_neck_and_hazard():
    from types import SimpleNamespace
    from shapely.geometry import box
    from kae.route import pad_entry as PE
    from kae.route.taut import Taut
    land = box(-0.5, -0.3, 0.5, 0.3)
    pd = SimpleNamespace(owner=("R1", "1"))
    t = _fake_taut()
    # narrower than the land: rule D as before, no neck
    ts, neck, wide = Taut._land_targets(t, land, pd, "N", "F.Cu", 0.25, (3.0, 0.1), 0.25, False)
    assert ts and neck is None and not wide
    # wider than the short side: only the long-edge entry, no copper past the land
    ts, neck, wide = Taut._land_targets(t, land, pd, "N", "F.Cu", 0.8, (3.0, 0.1), 0.8, False)
    assert [k for _, _, k in ts] == ["long"] and neck is None
    assert all(PE.overhang(land, a, e, 0.8) <= PE.OVER_AREA for a, e, _ in ts)
    # wider than the land: necked to at most the land width, the wide copper neck_len + w/2 out
    ts, neck, wide = Taut._land_targets(t, land, pd, "N", "F.Cu", 1.2, (3.0, 0.1), 1.2, False)
    assert neck is not None and neck <= 0.6 + 1e-9 and ts
    for a, e, _ in ts:
        assert math.dist(a, PE.crossing(land, a, e)) >= PE.NECK_LEN + 0.6 - 1e-6
    # a current needing more than the land: wide copper kept, one hazard per pad
    t = _fake_taut({"+5V": 2.0})
    for _ in range(2):
        ts, neck, wide = Taut._land_targets(t, land, pd, "+5V", "F.Cu", 1.2, (3.0, 0.1), 1.2, True)
    assert neck is None and wide and ts and len(t.hazards) == 1
    assert t.hazards[0]["code"] == "land_enlarged_by_track" and t.hazards[0]["objects"] == ["R1.1", "+5V"]


def test_merge_tiny_keeps_a_width_step():
    from kae.route.taut import _merge_tiny
    pieces = [("seg", (0, 0), (1, 0)), ("seg", (1, 0), (2, 0)), ("seg", (2, 0), (3, 0))]
    out, ws = _merge_tiny(pieces, [0.6, 1.2, 1.2])
    assert ws == [0.6, 1.2] and out[0] == ("seg", (0, 0), (1, 0)) and out[1][2] == (3, 0)


def _land(ref, net, x, y, s=0.6):
    return (ref, "Land", "x:Land", x, y, 0.0, [("1", net, 0.0, 0.0, s, s, "smd", 0.0, "", "passive")], (0.6, 0.85))


@pytest.mark.kicad
def test_taut_necks_a_track_wider_than_its_lands(tmp_path):
    """A 1.0 mm track with a detour between two 0.6 mm lands: taut pulls it straight and necks both
    ends to at most the land width; no entry hangs copper past its land; DRC no worse."""
    from kae.board import pcbnew_io
    if not pcbnew_io.available():
        pytest.skip("no Python with pcbnew")
    import critical_fixtures as F
    from kae.board.kicad_file import load
    from kae.route import critical_write as W
    from kae.route import taut
    src = F.write_board(tmp_path / "in", extra=[_land("R1", "WIDE", 103.0, 103.0), _land("R2", "WIDE", 118.0, 103.0)])
    pts = [(103, 103), (107, 103), (108.4, 101.6), (112.6, 101.6), (114, 103), (118, 103)]
    tracks = [("WIDE", "F.Cu", 1.0, a, b, W.new_uuid(), False) for a, b in zip(pts[:-1], pts[1:])]
    out = tmp_path / "routed" / "board.kicad_pcb"
    out.parent.mkdir()
    W.append_items(src, out, tracks=tracks)
    for ext in (".kicad_pro", ".kicad_dru"):
        if src.with_suffix(ext).exists():
            (out.with_suffix(ext)).write_text(src.with_suffix(ext).read_text())
    st0 = taut.board_stats(out)
    rep = taut.run(out, tmp_path / "out.kicad_pcb", workdir=tmp_path / "w", log=lambda *a: None)
    for t, n in rep["drc_out"]["by_type"].items():
        assert n <= rep["drc_in"]["by_type"].get(t, 0)
    st1 = taut.board_stats(tmp_path / "out.kicad_pcb")
    assert st0["overhanging"] == 2 and st1["overhanging"] == 0, (st0, st1, rep["stats"])
    assert rep["necks"] == 2 and rep["hazards"] == []
    ws = sorted({round(t.width, 3) for t in load(tmp_path / "out.kicad_pcb").tracks if t.net == "WIDE"})
    assert ws[0] <= 0.6 and ws[-1] == 1.0


def test_merge_tiny_absorbs_micro_segments_and_cuts_a_fold():
    from kae.route.taut import _merge_tiny
    # a 5 um piece between two others: its neighbour takes it, the chain's ends do not move
    got = _merge_tiny([("seg", (0, 0), (2, 0)), ("seg", (2, 0), (2.005, 0.001)), ("seg", (2.005, 0.001), (2.005, 3))])
    assert len(got) == 2 and got[0][1] == (0, 0) and got[-1][2] == (2.005, 3)
    assert got[0][2] == got[1][1]
    # out and back along one line: one segment to the last point
    assert _merge_tiny([("seg", (0, 0), (1, 0)), ("seg", (1, 0), (0.8, 0))]) == [("seg", (0, 0), (0.8, 0))]
    # a 90 degree corner is left alone
    assert len(_merge_tiny([("seg", (0, 0), (1, 0)), ("seg", (1, 0), (1, 1))])) == 2


@pytest.mark.kicad
def test_taut_stops_at_its_deadline_and_keeps_what_it_finished(tmp_path, monkeypatch):
    """A deadline that passes after the first branch: the passes stop cleanly, that branch's copper is
    written and journaled, the report says why (stats stopped, taut_time_limited)."""
    from kae.board import pcbnew_io
    if not pcbnew_io.available():
        pytest.skip("no Python with pcbnew")
    from kae.route import taut
    src = _detour_board(tmp_path)
    full = taut.run(src, tmp_path / "full.kicad_pcb", workdir=tmp_path / "w0", log=lambda *a: None, gate=False)
    assert len(full["nets_changed"]) >= 2 and not full["stats"].get("stopped")
    real, late = taut.clock_now, [False]
    orig = taut.Taut.tighten

    def once(self, *a, **k):
        got = orig(self, *a, **k)
        if got is not None:
            late[0] = True                      # the clock jumps past every deadline after one shorter branch
        return got
    monkeypatch.setattr(taut.Taut, "tighten", once)
    monkeypatch.setattr(taut, "clock_now", lambda: real() + (1e6 if late[0] else 0.0))
    rep = taut.run(src, tmp_path / "out.kicad_pcb", workdir=tmp_path / "w", log=lambda *a: None, gate=False,
                   timeout=600)
    assert rep["stats"]["stopped"] == "time" and len(rep["stats"]["passes"]) == 1
    assert 1 <= len(rep["nets_changed"]) < len(full["nets_changed"])
    assert len(rep["_entries"]) >= 1 and (tmp_path / "out.kicad_pcb").exists()
    assert any(h["code"] == "taut_time_limited" for h in rep["hazards"])


@pytest.mark.kicad
def test_taut_with_a_tiny_budget_returns_in_time(tmp_path):
    from kae.board import pcbnew_io
    if not pcbnew_io.available():
        pytest.skip("no Python with pcbnew")
    from kae.route import taut
    src = _detour_board(tmp_path)
    rep = taut.run(src, tmp_path / "out.kicad_pcb", workdir=tmp_path / "w", log=lambda *a: None, gate=False,
                   timeout=0.01)
    assert rep["stats"]["stopped"] == "time" and rep["stats"]["tried"] == 0 and rep["nets_changed"] == []
