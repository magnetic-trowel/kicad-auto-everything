# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Pad-edge entry (kae.route.pad_entry; GridRouter pad_entry="centre"; translate.tie_pins;
pad_trim): a track ends at the edge of the pad it approaches, perpendicular, at least
pad_entry_overlap inside, with no sliver beyond the pad, and on rails at least its width in."""
import math

from shapely.geometry import LineString, Point, box

from kae.board.kicad_file import load
from kae.route import constraints as CN
from kae.route import pad_entry as PE
from kae.route import pad_trim as PT
from kae.route.critical_grid import Anchor, GridRouter
from kae.route.critical_space import TOL, Space

import critical_fixtures as F

PAD = box(-0.5, -0.75, 0.5, 0.75)          # 1.0 x 1.5 mm land centred on the origin
C = (0.0, 0.0)


def _depth(pad, a, b):
    """How far the piece a -> b runs into the pad past the edge it crosses, along its axis."""
    x = PE.crossing(pad, a, b)
    return math.dist(x, b)


def test_entry_ends_overlap_inside_the_nearest_edge_perpendicular():
    p = (3.0, 0.3)                          # to the right, a little above the centre line
    tails = PE.entries(PAD, C, p, 0.25, 0.05)
    assert tails
    s, end = tails[0] if len(tails[0]) == 2 else (p, tails[0][0])
    assert abs(end[0] - 0.45) < 1e-9 and abs(end[1] - 0.3) < 1e-9      # 0.05 inside the right edge
    assert abs(s[1] - end[1]) < 1e-9                                    # last piece horizontal: on the normal
    assert PE.entry_angle(PAD, s, end) < 1e-6
    assert abs(_depth(PAD, s, end) - 0.05) < 1e-9


def test_oblique_approach_turns_onto_the_normal_before_the_edge():
    p = (1.5, 2.5)                          # up and to the right: nearest edge is the top one
    tails = PE.entries(PAD, C, p, 0.2, 0.05)
    s, end = tails[0]
    assert abs(end[1] - 0.70) < 1e-9 and abs(s[0] - end[0]) < 1e-12        # vertical stub into the top edge
    assert s[1] >= 0.75 + 0.2 - 1e-9                                    # the turn is a width off the pad
    assert not PAD.contains(Point(s))
    # the stub keeps the whole width on the edge: a half width from the corner
    assert end[0] <= 0.5 - 0.1 + 1e-9
    assert PE.entry_angle(PAD, s, end) < 1e-6
    # a direct piece is no candidate: it would cross at 45 degrees
    assert all(len(t) == 2 for t in tails)


def test_current_carrying_entry_is_centred_and_a_width_deep():
    p = (3.0, 0.6)
    (t,) = [x for x in PE.entries(PAD, C, p, 0.4, 0.05, centred=True, current=True)][:1]
    end = t[-1]
    assert abs(end[1]) < 1e-9                                           # centre of the right edge
    assert abs((0.5 - end[0]) - 0.4) < 1e-9                             # the width deep


def test_no_edge_entry_past_the_centre_or_poking_out():
    small = box(-0.15, -0.15, 0.15, 0.15)
    # 0.3 mm land, 0.25 mm rail track a width deep would pass the centre: keep the centre
    assert PE.entry(small, C, (2.0, 0.0), 0.25, 0.05, current=True) is None
    # a thin land whose depth leaves the round end beyond the far side: keep the centre
    thin = box(-1.0, -0.1, 1.0, 0.1)
    assert PE.entry(thin, C, (0.0, 2.0), 0.4, 0.05) is None
    assert PE.entry(thin, C, (0.0, 2.0), 0.25, 0.05) is not None      # 0.125 mm round end fits
    # from inside the pad: nothing to do
    assert PE.entries(PAD, C, (0.1, 0.1), 0.2, 0.05) == []


def test_round_pad_is_entered_radially():
    disc = Point(0, 0).buffer(0.5, 32)
    p = (2.0, 1.0)
    tails = PE.entries(disc, C, p, 0.2, 0.05)
    end = tails[-1][-1]
    u = (-2.0 / math.hypot(2, 1), -1.0 / math.hypot(2, 1))
    assert abs(math.hypot(*end) - (0.5 - 0.05)) < 0.01                  # 0.05 inside the rim
    assert abs(end[0] * u[1] - end[1] * u[0]) < 1e-6                    # on the ray to the centre
    assert PE.entry_angle(disc, tails[-1][0] if len(tails[-1]) == 2 else p, end) < 6.0


def test_entry_angle_flags_acute_entries():
    assert PE.entry_angle(PAD, (2.0, 0.0), (0.4, 0.0)) < 1e-6
    assert abs(PE.entry_angle(PAD, (1.5, 1.0), (0.3, -0.2)) - 45.0) < 1e-6
    assert PE.entry_angle(PAD, (2.0, 0.0), (3.0, 0.0)) is None


def test_current_net_names():
    assert PE.current_net("GND") and PE.current_net("/+3V3") and PE.current_net("VBUS")
    assert not PE.current_net("/SDA") and not PE.current_net("")


# ----------------------------------------------------------------------------- the grid router
DIAG = ("Q1", "Land", "x:Land", 110.0, 110.0, 0.0,
        [("1", "FA", 0.0, 0.0, 1.0, 1.5, "smd", 0.0, "", "passive")], (0.6, 0.85))
DIAG2 = ("Q2", "Land", "x:Land", 116.0, 114.0, 0.0,
         [("1", "FA", 0.0, 0.0, 1.0, 1.5, "smd", 0.0, "", "passive")], (0.6, 0.85))


def _route(tmp_path, mode):
    p = F.write_board(tmp_path, extra=[DIAG, DIAG2])
    info = F.synth_info(load(p))
    plan = CN.plan(info, p, {})
    sp = Space(load(p), info, plan=plan)
    a = next(it for it in sp.pads if it.owner == ("Q1", "1"))
    b = next(it for it in sp.pads if it.owner == ("Q2", "1"))
    src = Anchor(a.geom, tuple(sorted(a.layers)), a.pos, kind="pad")
    dst = Anchor(b.geom, tuple(sorted(b.layers)), b.pos, kind="pad")
    rt = GridRouter(sp, pad_entry=mode).connect("FA", [src], [dst], 0.25, ["F.Cu"], via=False)
    return sp, a, b, rt


def test_grid_router_centre_mode_unchanged(tmp_path):
    sp, a, b, rt = _route(tmp_path, "centre")
    assert math.dist(rt.segs[0][1], a.pos) < 1e-9 and math.dist(rt.segs[-1][2], b.pos) < 1e-9


def test_setting_and_env(tmp_path, monkeypatch):
    p = F.write_board(tmp_path)
    assert CN.pad_entry_mode(p, {}) == "centreline"                   # rule D by default
    assert CN.pad_entry_mode(p, {"pad_entry": "centre"}) == "centre"
    assert CN.pad_entry_mode(p, {"pad_entry": "edge"}) == "centreline"   # the superseded edge rule
    monkeypatch.setenv("KAE_PAD_ENTRY", "centre")
    assert CN.pad_entry_mode(p, {}) == "centre"
    monkeypatch.setenv("KAE_PAD_ENTRY", "bogus")
    assert CN.pad_entry_mode(p, {}) == "centreline"


# ----------------------------------------------------------------------------- Freerouting output trim
def _seg(a, b, w=0.25, net="SIG", layer="F.Cu", u="u1"):
    return (f'\t(segment\n\t\t(start {a[0]} {a[1]})\n\t\t(end {b[0]} {b[1]})\n\t\t(width {w})\n'
            f'\t\t(layer "{layer}")\n\t\t(net "{net}")\n\t\t(uuid "{u}")\n\t)\n')


def _info(*pads):
    return dict(pads=[dict(net=n, pos=list(c), layers=["F.Cu"], attr="smd", ref=r, fp_index=i,
                           poly=[[[list(x) for x in g.exterior.coords]]]) for i, (r, n, c, g) in enumerate(pads)])


def test_trim_cuts_back_to_overlap_inside_the_edge():
    g = box(9.5, -0.75, 10.5, 0.75)
    text = "(kicad_pcb\n" + _seg((0.0, 0.0), (10.0, 0.0)) + _seg((10.0, 5.0), (10.0, 0.0), u="u2") + ")\n"
    info = _info(("R1", "SIG", (10.0, 0.0), g))
    trims = PT.plan(text, info, 0.05)
    assert len(trims) == 2
    out = PT.write(text, trims)
    segs = PT._segments(out)
    assert segs[0]["b"] == (9.55, 0.0)                                  # 0.05 past the left edge
    assert segs[1]["b"] == (10.0, 0.7)                                  # 0.05 past the top edge
    st = PT.stats(out, info)
    assert st["entries"] == 2 and st["near_edge"] == 2 and st["perpendicular"] == 2


def test_trim_keeps_rails_a_width_deep_and_skips_vias_and_balls():
    g = box(9.0, -1.0, 11.0, 1.0)
    text = "(kicad_pcb\n" + _seg((0.0, 0.0), (10.0, 0.0), w=0.5, net="GND") + ")\n"
    assert PT.plan(text, _info(("R1", "GND", (10.0, 0.0), g)), 0.05) == []      # rails keep the centre
    trims = PT.plan(text, _info(("R1", "GND", (10.0, 0.0), g)), 0.05, rails="width")
    assert trims and abs(trims[0][2][0] - 9.5) < 1e-9                   # the width (0.5) deep
    via = '\t(via\n\t\t(at 10 0)\n\t\t(size 0.6)\n\t\t(drill 0.3)\n\t\t(layers "F.Cu" "B.Cu")\n\t\t(net "GND")\n\t)\n'
    with_via = "(kicad_pcb\n" + _seg((0.0, 0.0), (10.0, 0.0), w=0.5, net="GND") + via + ")\n"
    assert PT.plan(with_via, _info(("R1", "GND", (10.0, 0.0), g)), 0.05, rails="width") == []
    # a ball grid's pads (escape stage): untouched
    balls = [("U1", "SIG" if k == 0 else f"N{k}", (10.0 + 0.5 * k, 0.0), Point(10.0 + 0.5 * k, 0.0).buffer(0.15, 16))
             for k in range(PT.BALL_GRID_MIN)]
    info = _info(*balls)
    for pd in info["pads"]:
        pd["fp_index"] = 0
    assert PT.plan("(kicad_pcb\n" + _seg((10.0, 5.0), (10.0, 0.0), w=0.1) + ")\n", info, 0.05) == []


# ----------------------------------------------------------------------------- Freerouting's view
TIE_DSN = '''(pcb x
  (resolution um 10)
  (unit um)
  (structure (layer F.Cu (type signal)) (layer B.Cu (type signal)))
  (placement
    (component C0805 (place C2 136250 -107800 front 0))
  )
  (library
    (image C0805
      (pin Rect 1 -1000 0)
      (pin Rect 2 1000 0)
    )
  )
  (network
    (net A (pins C2-2))
    (net B (pins C2-1))
  )
  (wiring
    (wire (path F.Cu 250  137600 -107800  140000 -107800)(net A)(type fix))
    (wire (path F.Cu 250  135250 -107800  133000 -107800)(net B)(type fix))
  )
)
'''


def test_tie_pins_joins_edge_ends_to_the_pin_centre_for_freerouting():
    """Freerouting joins a trace to a pin only at its centre: an end 0.35 mm off C2-2's centre,
    inside its land, gets a fixed tie to the centre; an end at a pin centre gets none."""
    from kae.route import specctra as S
    from kae.route import translate
    t = S.parse(TIE_DSN)
    land = lambda x: [[[[x - 0.5, 107.2], [x + 0.5, 107.2], [x + 0.5, 108.4], [x - 0.5, 108.4], [x - 0.5, 107.2]]]]
    info = dict(pads=[dict(net="A", pos=[137.25, 107.8], layers=["F.Cu"], poly=land(137.25)),
                      dict(net="B", pos=[135.25, 107.8], layers=["F.Cu"], poly=land(135.25))])
    assert translate.tie_pins(t, info, {"F.Cu": "F.Cu", "B.Cu": "B.Cu"}) == 1
    ties = [w for w in S.findall(S.find(t, "wiring"), "wire") if S.find(w, "type")[1] == "fix"][2:]
    (tie,) = ties
    path = S.find(tie, "path")
    assert [float(v) for v in path[3:]] == [137600.0, -107800.0, 137250.0, -107800.0]
    assert str(S.find(tie, "net")[1]) == "A"


def test_reend_turns_an_oblique_entry_onto_the_edge_normal():
    """A 45-degree track into a land's centre: re-ended, the segment stops at a turn a width
    outside the edge and a new piece runs straight in, overlap deep; refused pieces fall back
    to the plain cut along the axis."""
    g = box(9.5, -0.75, 10.5, 0.75)
    text = "(kicad_pcb\n" + _seg((7.0, -3.0), (10.0, 0.0), w=0.2) + ")\n"
    info = _info(("R1", "SIG", (10.0, 0.0), g))
    (t,) = PT.plan(text, info, 0.05, legal=lambda *a: True)
    assert t[4] == "reend" and t[3] is not None
    out = PT._segments(PT.write(text, [t]))
    assert len(out) == 2
    a, b = out[1]["a"], out[1]["b"]
    assert out[0]["b"] == a and g.contains(Point(b)) and not g.contains(Point(a))
    assert PE.entry_angle(g, a, b) < 1e-6 and _depth(g, a, b) >= 0.05 - 1e-9
    st = PT.stats(PT.write(text, [t]), info)
    assert st["perpendicular"] == 1 and st["oblique"] + st["acute"] == 0
    (c,) = PT.plan(text, info, 0.05, legal=lambda *a: False)
    assert c[4] == "cut" and c[3] is None and PE.entry_angle(g, (7.0, -3.0), c[2]) > 40


def test_wide_track_counts_as_current_carrying():
    g = box(9.0, -1.0, 11.0, 1.0)
    text = "(kicad_pcb\n" + _seg((0.0, 0.0), (10.0, 0.0), w=PT.CURRENT_W) + ")\n"
    (t,) = PT.plan(text, _info(("R1", "SIG", (10.0, 0.0), g)), 0.05, rails="width")
    assert abs((t[2][0] - 9.0) - PT.CURRENT_W) < 1e-9


# ----------------------------------------------------------------------------- tail re-route
def test_approach_targets_face_the_release_point_along_the_normal():
    rel = (3.0, 0.4)
    (a, end, u, facing), *_ = PE.approach_targets(PAD, C, rel, 0.2, 0.05)
    assert facing and abs(u[0] + 1) < 1e-9 and abs(u[1]) < 1e-9
    assert abs(end[0] - 0.45) < 1e-9 and abs(end[1] - 0.4) < 1e-9          # the foot, 0.05 deep
    assert abs(a[0] - (0.5 + 0.2)) < 1e-9 and abs(a[1] - 0.4) < 1e-9       # one width outside, on the normal
    assert PE.entry_angle(PAD, a, end) < 1e-9


def test_approach_targets_rails_take_the_edge_middle_a_width_deep():
    (a, end, u, facing), *_ = PE.approach_targets(PAD, C, (3.0, 0.6), 0.3, 0.05, current=True)
    assert abs(end[1]) < 1e-9 and abs((0.5 - end[0]) - 0.3) < 1e-9


def test_approach_targets_prefer_the_facing_edge_over_the_nearest_corner():
    # below and to the right: the bottom edge faces the point as squarely as the right one, but
    # every target listed first is one the release point lies in front of
    ts = PE.approach_targets(PAD, C, (0.9, -3.0), 0.2, 0.05)
    a, end, u, facing = ts[0]
    assert facing and abs(u[1] - 1.0) < 1e-9                                 # the bottom edge (y = -0.75)
    assert abs(end[1] - (-0.70)) < 1e-9 and abs(a[1] - (-0.95)) < 1e-9
    assert not ts[-1][3]                                                      # the far edges come last


def test_doglegs_and_octilinear_share():
    from kae.route import pad_reroute as RR
    for path in RR.doglegs((0.0, 0.0), (3.0, 1.0)):
        assert all(RR._is_octo(p, q) for p, q in zip(path[:-1], path[1:]))
        assert path[-1] == (3.0, 1.0)
    segs = [dict(a=(0, 0), b=(1, 0)), dict(a=(1, 0), b=(2, 1)), dict(a=(2, 1), b=(2.3, 2))]
    assert abs(RR.octilinear_share(segs) - (1 + 2 ** 0.5) / (1 + 2 ** 0.5 + math.hypot(0.3, 1))) < 1e-9


def test_sliver_ratio_flags_corner_crossings():
    from kae.route import pad_reroute as RR
    straight = RR.sliver_ratio(PAD, (3.0, 0.0), (0.0, 0.0), 0.25)
    corner = RR.sliver_ratio(PAD, (2.0, 2.25), (0.0, 0.25), 0.25)
    assert straight < 1.6 and corner > straight


def test_chain_releases_at_a_junction_or_at_R():
    from kae.route import pad_reroute as RR
    s1 = dict(uuid="1", net="N", layer="F.Cu", w=0.2, a=(0.0, 0.0), b=(2.0, 0.0))
    s2 = dict(uuid="2", net="N", layer="F.Cu", w=0.2, a=(2.0, 0.0), b=(2.0, 5.0))
    by = {}
    for s in (s1, s2):
        for p in (s["a"], s["b"]):
            by.setdefault((s["net"], s["layer"], RR._key(p)), []).append(s)
    pieces, rel, kind = RR.chain(by, s1, (0.0, 0.0), 3.0, set())
    assert kind == "split" and abs(rel[1] - 1.0) < 1e-9 and len(pieces) == 2
    pieces, rel, kind = RR.chain(by, s1, (0.0, 0.0), 3.0, {RR._key((2.0, 0.0))})
    assert kind == "node" and rel == (2.0, 0.0) and len(pieces) == 1
    s3 = dict(s2, uuid="3", w=0.4)
    by2 = {k: [s3 if x is s2 else x for x in v] for k, v in by.items()}
    _, rel, kind = RR.chain(by2, s1, (0.0, 0.0), 3.0, set())
    assert kind == "node" and rel == (2.0, 0.0)                             # a width change releases


def test_reroute_plan_on_a_fixture_board_arrives_along_the_normal(tmp_path):
    """An oblique entry into a 1.0 x 1.5 mm land is re-routed from its release point: the new
    tail ends overlap-deep in the land along the edge normal, every piece legal."""
    from kae.route import pad_reroute as RR
    p = F.write_board(tmp_path, extra=[DIAG, DIAG2])
    info = F.synth_info(load(p))
    plan = CN.plan(info, p, {})
    sp = Space(load(p), info, plan=plan)
    gr = GridRouter(sp, pad_entry="centre")
    a = next(it for it in sp.pads if it.owner == ("Q1", "1"))
    b = next(it for it in sp.pads if it.owner == ("Q2", "1"))
    text = "(kicad_pcb\n" + _seg(a.pos, b.pos, w=0.25, net="FA") + ")\n"
    for pd in info["pads"]:
        pd.setdefault("attr", "smd")
    changes, outcome, octo = RR.plan(text, info, sp, gr, 0.05)
    assert outcome.get("rerouted", 0) >= 1
    for ch in changes:
        pts = ch["pts"]
        g = (a if ch["pieces"][0][1] == a.pos else b).geom
        assert PE.entry_angle(g, pts[-2], pts[-1]) <= RR.ENTRY_DEG
        assert _depth(g, pts[-2], pts[-1]) >= 0.05 - 1e-6
        assert math.dist(pts[-2], PE.crossing(g, pts[-2], pts[-1])) >= 0.25 - 1e-6
        for u, v in zip(pts[:-1], pts[1:]):
            assert not sp.track_violations("FA", "F.Cu", 0.25, u, v)
        out = RR.write(text, [ch])
        assert len(PT._segments(out)) >= 2


def test_chain_releases_at_a_t_junction_mid_segment():
    from kae.route import pad_reroute as RR
    s1 = dict(uuid="1", net="N", layer="F.Cu", w=0.2, a=(0.0, 0.0), b=(4.0, 0.0))
    by = {}
    for p in (s1["a"], s1["b"]):
        by.setdefault(("N", "F.Cu", RR._key(p)), []).append(s1)
    pieces, rel, kind = RR.chain(by, s1, (0.0, 0.0), 3.0, set(), taps=[(0.0, 0.0), (4.0, 0.0), (1.2, 0.05)])
    assert kind == "split" and abs(rel[0] - 1.2) < 1e-9 and len(pieces) == 1


# ----------------------------------------------------------------------------- rule D: the long centre line
SOIC = box(-0.975, -0.3, 0.975, 0.3)          # SOIC-8 land 1.95 x 0.60: centre line x in [-0.675, 0.675]


def _kinds(ts):
    return [k for _, _, k in ts]


def test_rule_d_centreline_of_long_round_square_and_stadium_pads():
    a, b = PE.centreline(SOIC)
    assert sorted([round(a[0], 6), round(b[0], 6)]) == [-0.675, 0.675] and abs(a[1]) < 1e-9
    assert PE.centreline(Point(0, 0).buffer(0.85, 64))[0] == PE.centreline(Point(0, 0).buffer(0.85, 64))[1]
    sq = box(-0.45, -0.475, 0.45, 0.475)                         # near square (0603): the centre point
    a, b = PE.centreline(sq)
    assert math.dist(a, b) < 1e-9 and math.dist(a, (0, 0)) < 1e-9
    oval = LineString([(0, -0.45), (0, 0.45)]).buffer(0.85, 64)  # stadium 1.7 x 2.6: end-circle centres
    a, b = PE.centreline(oval)
    assert sorted(round(p[1], 3) for p in (a, b)) == [-0.45, 0.45]


def test_rule_d_straight_case_has_no_corner():
    (a, end, kind), *_ = PE.centreline_targets(SOIC, (0.35, 2.2), 0.25)
    assert kind == "straight" and math.dist(end, (0.35, 0.0)) < 1e-9 and abs(a[0] - 0.35) < 1e-9
    assert PE.entry_angle(SOIC, a, end) <= 10


def test_rule_d_diagonal_past_the_end_takes_a_square_corner():
    ts = PE.centreline_targets(SOIC, (2.6, 1.7), 0.25)
    assert "straight" not in _kinds(ts)                          # the straight line would cross the corner
    for a, end, kind in ts:
        assert kind in ("axial", "long") and PE.entry_angle(SOIC, a, end) < 1e-6
        assert abs(end[1]) < 1e-9 and abs(end[0] - 0.675) < 1e-9   # on the centre line's end
    long = next(t for t in ts if t[2] == "long")
    assert abs(long[0][1] - (0.3 + 0.25)) < 1e-9                 # one width outside the long edge
    axial = next(t for t in ts if t[2] == "axial")
    assert abs(axial[0][0] - (0.975 + 0.25)) < 1e-9 and abs(axial[0][1]) < 1e-9


def test_rule_d_axial_approach_runs_straight_along_the_axis():
    (a, end, kind), *_ = PE.centreline_targets(SOIC, (3.2, 0.25), 0.25)
    assert kind == "straight" and math.dist(end, (0.675, 0.0)) < 1e-9
    assert PE.entry_angle(SOIC, a, end) <= 10


def test_rule_d_round_pad_is_radial_to_the_centre():
    disc = Point(0, 0).buffer(0.85, 64)
    (a, end, kind), *_ = PE.centreline_targets(disc, (2.4, 1.7), 0.3)
    assert kind == "straight" and math.dist(end, (0, 0)) < 1e-9
    assert PE.entry_angle(disc, a, end) < 1.0


def test_rule_d_stadium_square_side_or_radial_end():
    oval = LineString([(0, -0.45), (0, 0.45)]).buffer(0.85, 64)
    (a, end, kind), *_ = PE.centreline_targets(oval, (2.3, 0.2), 0.3)   # beside the straight side
    assert kind == "straight" and math.dist(end, (0.0, 0.2)) < 1e-9 and abs(a[1] - 0.2) < 1e-9
    (a, end, kind), *_ = PE.centreline_targets(oval, (2.3, 2.6), 0.3)   # past the round end: radial
    assert math.dist(end, (0.0, 0.45)) < 1e-9 and PE.entry_angle(oval, a, end) < 1.0


def test_rule_d_square_pad_enters_through_an_edge_middle_to_the_centre():
    sq = box(-0.45, -0.475, 0.45, 0.475)
    ts = PE.centreline_targets(sq, (1.7, 1.4), 0.25)                     # diagonal: the corner is no entry
    assert ts and "straight" not in _kinds(ts)
    for a, end, kind in ts:
        assert math.dist(end, (0, 0)) < 1e-9 and PE.entry_angle(sq, a, end) < 1e-6


def test_rule_d_drops_ends_whose_tip_leaves_the_pad():
    thin = box(-1.0, -0.1, 1.0, 0.1)
    # a 0.4 mm track across a 0.2 mm land: its round end would stick out of the far side
    assert all(k != "long" for _, _, k in PE.centreline_targets(thin, (0.0, 2.0), 0.4))


# ----------------------------------------------------------------------------- rule D: tracks wider than the land
LAND = box(-0.5, -0.3, 0.5, 0.3)              # 1.0 x 0.6 mm land (0603-class)


def test_overhang_measures_sides_and_tip_beyond_the_land():
    # square, narrower than the land: nothing outside it once entered
    assert PE.overhang(LAND, (0.0, 1.0), (0.0, 0.0), 0.25) == 0.0
    # axial 0.8 mm track along a 0.6 mm land: 0.1 mm of each side hangs past the long edges
    assert PE.overhang(LAND, (2.0, 0.0), (0.2, 0.0), 0.8) > 0.1
    # an oblique (10 deg) square-ish entry: the wedge before the edge is approach, not overhang
    t = math.radians(10)
    assert PE.overhang(LAND, (0.5 * math.sin(t), 0.3 + 0.5 * math.cos(t)), (0.0, 0.3 - 0.05), 0.25) <= PE.OVER_AREA
    # 0.8 mm across through the long edge to the centre line: the round end pokes 0.1 mm out
    assert PE.overhang(LAND, (0.0, 1.0), (0.0, 0.0), 0.8) > PE.OVER_AREA
    # radial into a disc, narrower than it: the junction sliver before the sides enter is approach
    disc = Point(0, 0).buffer(0.5, 64)
    assert PE.overhang(disc, (1.5, 0.0), (0.0, 0.0), 0.3) <= PE.OVER_AREA


def test_track_narrower_than_the_land_keeps_rule_d():
    ts = PE.centreline_targets(LAND, (3.0, 0.1), 0.25)
    assert ts and ts[0][2] == "straight"
    for a, end, kind in ts:
        assert PE.overhang(LAND, a, end, 0.25) <= PE.OVER_AREA
        assert abs(end[1]) < 1e-9 and abs(end[0]) <= 0.2 + 1e-9          # on the centre line


def test_track_wider_than_the_short_side_enters_through_the_long_edge():
    """0.8 mm into 1.0 x 0.6: the axial and straight entries hang 0.1 mm past both long edges;
    the long-edge entry fits once its end is pulled back so its round tip stays inside."""
    for rel in ((3.0, 0.1), (0.2, 3.0), (2.0, 2.0)):
        ts = PE.centreline_targets(LAND, rel, 0.8)
        assert [k for _, _, k in ts] == ["long"]
        a, end, _ = ts[0]
        assert PE.overhang(LAND, a, end, 0.8) <= PE.OVER_AREA
        assert PE.entry_angle(LAND, a, end) < 1e-6
        assert 0.3 - abs(end[1]) >= PE.MIN_DEPTH - 1e-9                  # still inside the outline
        assert abs(end[0]) + 0.4 <= 0.5 + PE.OVER_TOL                     # both sides land on the edge
    # the old tip test alone (copper that must stay wide) still offers the axial entry
    assert "axial" in [k for _, _, k in PE.centreline_targets(LAND, (3.0, 0.1), 0.8, check_overhang=False)]


def test_track_wider_than_the_land_is_necked_to_the_widest_entry_that_fits():
    assert PE.centreline_targets(LAND, (3.0, 0.1), 1.2) == []
    wn, ts = PE.neck_width(LAND, (3.0, 0.1), 1.2, stub=PE.NECK_LEN + 0.6)
    assert wn is not None and wn <= PE.land_width(LAND) + 1e-9 and ts
    assert abs(wn - 0.6) < 1e-9                    # the land width caps it (1.0 would fit the long edge)
    wn2, _ = PE.neck_width(box(-0.3, -0.5, 0.3, 0.5).buffer(-0.0), (3.0, 0.1), 1.2)
    assert wn2 is not None and PE.centreline_targets(box(-0.3, -0.5, 0.3, 0.5), (3.0, 0.1), wn2 + 0.01) == [] \
        or abs(wn2 - 0.6) < 1e-9                   # else the widest that fits
    for a, end, kind in ts:
        assert PE.overhang(LAND, a, end, wn) <= PE.OVER_AREA
        x = PE.crossing(LAND, a, end)
        assert math.dist(a, x) >= PE.NECK_LEN + 0.6 - 1e-6                # wide copper neck_len off
    # never below what the current needs
    assert PE.neck_width(LAND, (3.0, 0.1), 1.2, need=0.7)[0] is None
    sq = box(-0.3, -0.3, 0.3, 0.3)
    assert PE.centreline_targets(sq, (2.0, 0.1), 1.0) == []
    wn, ts = PE.neck_width(sq, (2.0, 0.1), 1.0)
    assert wn is not None and wn <= 0.6 + 1e-9 and ts


def test_stadium_and_round_pads_with_wide_tracks():
    oval = LineString([(0, -0.45), (0, 0.45)]).buffer(0.85, 64)         # 1.7 x 2.6 stadium
    for rel in ((2.3, 0.2), (2.3, 2.6)):
        ts = PE.centreline_targets(oval, rel, 1.2)
        assert ts
        for a, end, kind in ts:
            assert PE.overhang(oval, a, end, 1.2) <= PE.OVER_AREA
    assert PE.centreline_targets(oval, (2.3, 0.2), 2.8) == []          # wider than the stadium is long
    wn, ts = PE.neck_width(oval, (2.3, 0.2), 2.8)
    assert wn is not None and wn <= 1.7 + 1e-9 and ts
    disc = Point(0, 0).buffer(0.5, 64)
    (a, end, kind), *_ = PE.centreline_targets(disc, (2.4, 1.7), 0.9)
    assert math.dist(end, (0, 0)) < 1e-9 and PE.overhang(disc, a, end, 0.9) <= PE.OVER_AREA
    assert PE.centreline_targets(disc, (2.4, 1.7), 1.2) == []
    wn, ts = PE.neck_width(disc, (2.4, 1.7), 1.2)
    assert wn is not None and wn <= 1.0 + 1e-9 and ts


class _SP:
    def width_limits(self, net, layer):
        return (0.1, 0.2, None)


def test_current_above_the_land_keeps_the_wide_copper_and_raises_a_hazard():
    from kae.route import pad_reroute as RR
    from kae.route import power_copper as PC
    seg = dict(net="+5V", layer="F.Cu", w=1.2)
    pd = dict(ref="L1", pin="2")
    hz, notes = [], []
    # 2 A through a 0.6 mm land: IPC-2221 at 3 x 2 A asks for far more than the land
    ts, neck, why = RR._neck_or_wide(_SP(), LAND, pd, seg, (3.0, 0.1), 1.2, {("L1", "+5V"): 2.0}, 3.0, hz, set(),
                                     notes.append)
    assert neck is None and ts and why is None
    assert notes == ["hazard"] and len(hz) == 1
    h = hz[0]
    assert h["code"] == "land_enlarged_by_track" and h["severity"] == "warn" and h["category"] == "assembly"
    assert "tombstone" in h["message"] and "wicking" in h["message"]
    assert h["objects"] == ["L1.2", "+5V"]
    ev = h["evidence"]
    assert ev["track_w_mm"] == 1.2 and ev["land_w_mm"] == 0.6 and ev["need_w_mm"] == round(PC.current_need(2.0, 3.0), 4)
    # no current: the same entry is necked instead
    ts, neck, why = RR._neck_or_wide(_SP(), LAND, pd, seg, (3.0, 0.1), 1.2, {}, 3.0, [], set(), notes.append)
    assert neck is not None and neck <= 0.6 and ts


def test_pad_currents_follow_the_neck_rules():
    from kae.route import power_copper as PC
    op = {"parts": {"U1": {"I_A": [0.1, 0.4]}, "F1": {}, "C1": {"I_A": 0.0}}}
    pads = [("U1", "+5V"), ("U1", "+5V"), ("U1", "GND"), ("U1", "SDA"),
            ("F1", "VIN"), ("F1", "+5V"), ("C1", "+5V"), ("C1", "GND")]
    i = PC.pad_currents(op, pads, {"VIN", "+5V"}, {"GND"})
    assert i[("U1", "+5V")] == 0.2 and i[("U1", "GND")] == 0.4 and i[("U1", "SDA")] == 0.0
    assert i[("F1", "VIN")] == i[("F1", "+5V")] == 0.4          # in series with the rail: its current
    assert i[("C1", "GND")] == 0.0 and i[("C1", "+5V")] == 0.0    # a decap carries no DC
    assert PC.current_need(0.0) == 0.0 and PC.current_need(1.0) > PC.current_need(0.5) > 0


SMALL = ("R1", "Land", "x:Land", 110.0, 110.0, 0.0,
         [("1", "FW", 0.0, 0.0, 0.6, 0.6, "smd", 0.0, "", "passive")], (0.6, 0.85))
SMALL2 = ("R2", "Land", "x:Land", 116.0, 114.0, 0.0,
          [("1", "FW", 0.0, 0.0, 0.6, 0.6, "smd", 0.0, "", "passive")], (0.6, 0.85))


def test_reroute_necks_a_track_wider_than_the_land(tmp_path):
    """A 1.0 mm track between two 0.6 mm lands: each end is re-routed with a neck no wider than the
    land, the wide copper stopping neck_len off it, every piece legal; written at both widths."""
    from kae.route import pad_reroute as RR
    p = F.write_board(tmp_path, extra=[SMALL, SMALL2])
    info = F.synth_info(load(p))
    plan = CN.plan(info, p, {})
    sp = Space(load(p), info, plan=plan)
    gr = GridRouter(sp, pad_entry="centre")
    a = next(it for it in sp.pads if it.owner == ("R1", "1"))
    b = next(it for it in sp.pads if it.owner == ("R2", "1"))
    text = "(kicad_pcb\n" + _seg(a.pos, b.pos, w=1.0, net="FW") + ")\n"
    for pd in info["pads"]:
        pd.setdefault("attr", "smd")
    assert PT.stats(text, info)["overhanging"] == 2
    changes, outcome, octo = RR.plan(text, info, sp, gr, 0.05)
    assert outcome.get("necked", 0) >= 1, outcome
    for ch in changes:
        assert ch["neck"] is not None and ch["neck"] <= 0.6 + 1e-9
        pts = ch["pts"]
        g = (a if ch["pieces"][0][1] == a.pos else b).geom
        assert PE.overhang(g, pts[-2], pts[-1], ch["neck"]) <= PE.OVER_AREA
        assert PE.entry_angle(g, pts[-2], pts[-1]) <= RR.ENTRY_DEG
        for u, v in zip(pts[:-2], pts[1:-1]):
            assert g.distance(LineString([u, v])) >= 0.5 + 0.5 - 2e-3       # wide copper neck_len off
            assert not sp.track_violations("FW", "F.Cu", 1.0, u, v)
        assert not sp.track_violations("FW", "F.Cu", ch["neck"], pts[-2], pts[-1])
    out = RR.write(text, changes)
    ws = {s["w"] for s in PT._segments(out)}
    assert 1.0 in ws and any(w <= 0.6 for w in ws)
    assert PT.stats(out, info)["overhanging"] < 2


def test_a_rerouted_tail_may_not_fold_back():
    from kae.route.pad_reroute import _folds_back, _key
    s = dict(uuid="s", net="N", layer="F.Cu", a=(0, 0), b=(2, 0), w=0.2)
    keep = dict(uuid="k", net="N", layer="F.Cu", a=(2, 0), b=(5, 0), w=0.2)
    by = {("N", "F.Cu", _key((2, 0))): [s, keep]}
    pieces = [(s, (0, 0), (2, 0))]
    # the tail leaving the release point along the copper it joins
    assert _folds_back([(2, 0), (4, 0), (4, 1)], (2, 0), s, by, pieces, "node", 1e-3)
    # within itself
    assert _folds_back([(2, 0), (2, 2), (2, 1)], (2, 0), s, by, pieces, "node", 1e-3)
    # a square departure is fine
    assert not _folds_back([(2, 0), (2, 2), (0, 2)], (2, 0), s, by, pieces, "node", 1e-3)
