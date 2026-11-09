# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The plan's per-pad rules (constraints.PadRule: rule D, necks, current, mask web) and the grid
router born right: GridRouter reaches pads by rule D (straight, corner, axial, necked), every
piece legal, no copper past the land. docs/topics/routing/routing-stages.md stages 1-3."""
import json
import math

import pytest
from shapely.geometry import LineString, Point, box

from kae.board.kicad_file import load
from kae.route import constraints as CN
from kae.route import pad_entry as PE
from kae.route import power_copper as PC
from kae.route.critical_grid import Anchor, GridRouter
from kae.route.critical_space import TOL, Space

import critical_fixtures as F

LAND = ("1", "FA", 0.0, 0.0, 1.0, 1.5, "smd", 0.0, "", "passive")


def _part(ref, x, y, pads=(LAND,), rot=0.0):
    return (ref, "Land", "x:Land", x, y, rot, list(pads), (0.9, 0.9))


def _plan(tmp_path, extra, opts=None):
    p = F.write_board(tmp_path, extra=extra)
    info = F.synth_info(load(p))
    plan = CN.plan(info, p, opts or {})
    return p, info, plan, Space(load(p), info, plan=plan)


def _pad(sp, ref, num="1"):
    return next(it for it in sp.pads if it.owner == (ref, num))


def _anchor(it):
    return Anchor(it.geom, tuple(sorted(it.layers)), it.pos, kind="pad")


def _on_centreline(g, q):
    a, b = PE.centreline(g)
    return LineString([a, b]).distance(Point(q)) < 1e-3 if a != b else math.dist(a, q) < 1e-3


def _check_rule_d(sp, net, rt, pads):
    """Both ends of `rt` end on their land's centre line, the final piece square (<= 10 deg) and
    adding no copper past the land; every piece legal at its width."""
    assert rt is not None and rt.segs
    (_, s0, e0), (_, s1, e1) = rt.segs[0], rt.segs[-1]
    for i, (pad, (u, v)) in enumerate(zip(pads, ((e0, s0), (s1, e1)))):
        g = pad.geom
        w = rt.seg_w(0 if i == 0 else len(rt.segs) - 1)
        assert _on_centreline(g, v), (v, PE.centreline(g))
        assert PE.entry_angle(g, u, v) <= CN.ENTRY_DEG + 1e-6
        assert not PE.overhangs(g, u, v, w)
    for i, (l, a, b) in enumerate(rt.segs):
        assert not sp.track_violations(net, l, rt.seg_w(i), a, b, tol=TOL)


# ----------------------------------------------------------------------------- the plan
def test_land_necks_by_class_process_and_series_current():
    lands = {"C1": [(1, True, "+3V3", 0.5), (2, True, "GND", 0.5)],          # 0402 decap
             "R1": [(3, True, "A", 0.9), (4, True, "B", 0.9)],                # 0603-0805 signal
             "R2": [(5, True, "A", 1.3), (6, True, "B", 1.3)],                # 1206
             "FB1": [(7, True, "+5V", 0.9), (8, True, "VIN", 0.9)],           # in series with a rail
             "U1": [(9, True, "A", 0.3), (10, True, "B", 0.3), (11, True, "C", 0.3)]}
    power, ground = {"+3V3", "+5V", "VIN"}, {"GND"}
    n, ser = PC.land_necks(lands, power, ground, {"+5V": 0.1, "VIN": 0.1}, "reflow")
    assert n[1] == n[2] == 0.25 and n[3] == 0.3 and n[5] == 1.3 and 9 not in n  # 1206: capped at its land
    assert ser[1] == 0.0 and ser[7] == 0.1 and n[7] == pytest.approx(max(0.3, PC.current_need(0.1)))
    assert PC.land_necks(lands, power, ground, {}, "hand")[0][5] == 0.5        # hand: 1206 too
    wave = PC.land_necks(lands, power, ground, {}, "wave")[0]                  # glued chips: land width only
    assert wave[1] == 0.5 and wave[3] == 0.9 and wave[5] == 1.3
    # a rail current that needs more than the land: no neck
    n2, _ = PC.land_necks(lands, power, ground, {"+5V": 5.0}, "reflow")
    assert 7 not in n2 and 8 not in n2


def test_plan_carries_necks_currents_and_the_land_hazard(tmp_path):
    fb = ("FB1", "Ferrite", "x:L_0805", 112.0, 116.0, 0.0,
          [("1", "VIN", -0.9, 0.0, 0.9, 1.2, "smd", 0.0, "", "passive"),
           ("2", "+5V", 0.9, 0.0, 0.9, 1.2, "smd", 0.0, "", "passive")], (1.6, 0.9))
    p, info, plan, sp = _plan(tmp_path, [fb])
    rules = {(r.ref, str(r.number)): r for r in plan.pad_rules.values()}
    c1 = rules[("C1", "1")]
    assert c1.two_terminal and c1.neck == 0.3 and plan.process == "reflow"     # 0805 land, 1.0 mm wide
    assert rules[("U2", "4")].neck is None and not rules[("U2", "4")].two_terminal
    l1 = rules[("L1", "1")]                                                     # 1210: capped at its land in reflow
    assert l1.neck == pytest.approx(1.2)
    assert rules[("FB1", "1")].neck == 0.3 and not plan.hazards
    op = tmp_path / "op.json"
    op.write_text(json.dumps({"parts": {"FB1": {"I_A": 3.0}}, "requirements": {"assembly": {"process": "wave"}}}))
    _, _, plan2, _ = _plan(tmp_path / "b", [fb], {"operating": str(op)})
    r2 = {(r.ref, str(r.number)): r for r in plan2.pad_rules.values()}
    assert plan2.process == "wave" and r2[("C1", "1")].neck == pytest.approx(1.0)  # wave: land width only
    assert r2[("FB1", "1")].series_a == 3.0 and r2[("FB1", "1")].need > 0.9
    hz = [h for h in plan2.hazards if h["code"] == "land_enlarged_by_track"]
    assert len(hz) == 2 and {h["objects"][0] for h in hz} == {"FB1.1", "FB1.2"}
    assert hz[0]["severity"] == "warn" and hz[0]["category"] == "assembly"
    # width_at: the neck, never below the current's need
    w, stub = c1.width_at(0.5)
    assert w == 0.3 and stub == pytest.approx(PE.NECK_LEN + 0.25)
    assert c1.width_at(0.25) == (0.25, None)


def test_settings_arc_policy_and_arm_e(tmp_path, monkeypatch):
    p, info, plan, sp = _plan(tmp_path, [])
    assert plan.arc_policy == "arcs" and plan.pad_entry == "centreline"
    assert CN.arc_policy(p, {"arc_policy": "keep45"}) == "keep45"
    monkeypatch.setenv("KAE_ARC_POLICY", "keep45")
    assert CN.arc_policy(p, {}) == "keep45"
    monkeypatch.setenv("KAE_ARC_POLICY", "bogus")
    assert CN.arc_policy(p, {}) == "arcs"
    assert not CN.setting_env("escape_ground_vias", p, {})
    monkeypatch.setenv("KAE_ESCAPE_GROUND_VIAS", "1")
    assert CN.setting_env("escape_ground_vias", p, {}) == 1.0


def test_mask_web_rejects_an_approach_beside_another_nets_opening():
    pad = box(-0.15, -0.5, 0.15, 0.5)                   # 0.3 x 1.0 land, long axis y
    nb = box(0.45, -0.5, 0.75, 0.5)                     # a neighbour's opening 0.3 mm to the right
    rel = (3.0, 0.0)
    free = PE.centreline_targets(pad, rel, 0.2)
    side = [t for t in free if t[0][0] > 0.15]          # through the long edge facing the neighbour
    assert side
    held = PE.centreline_targets(pad, rel, 0.2, mask=([nb], 0.1))
    assert held and not [t for t in held if t[0][0] > 0.15]        # axial ones stay
    for a, end, _ in held:
        assert PE.mask_ok(pad, a, end, 0.2, ([nb], 0.1))
    # an opening that holds the land (a solder jumper's): no copper beside the land inside it
    jp = box(-0.2, -0.6, 0.8, 0.6)
    assert not any(PE.mask_ok(pad, a, e, 0.2, ([jp], 0.0)) for a, e, k in side)


def test_plan_mask_finds_neighbouring_openings_of_other_nets(tmp_path):
    p, info, plan, sp = _plan(tmp_path, [])
    r = next(r for r in plan.pad_rules.values() if (r.ref, str(r.number)) == ("U2", "2"))
    aps, web = r.mask_on("F.Cu")
    assert aps and web >= 0
    own = r.land
    assert all(ap.distance(own) > 1e-6 for ap in aps)    # its own opening is not foreign
    assert r.mask_on("B.Cu") is None                       # no opening on that side


# ----------------------------------------------------------------------------- the grid router
def _connect(sp, net, a, b, w=0.25, mode=None, layers=("F.Cu",)):
    gr = GridRouter(sp, pad_entry=mode)
    return gr, gr.connect(net, [_anchor(a)], [_anchor(b)], w, list(layers), via=False)


def test_grid_router_reaches_pads_by_rule_d_with_a_corner(tmp_path):
    p, info, plan, sp = _plan(tmp_path, [_part("Q1", 110.0, 110.0), _part("Q2", 116.0, 114.0)])
    a, b = _pad(sp, "Q1"), _pad(sp, "Q2")
    gr, rt = _connect(sp, "FA", a, b)
    _check_rule_d(sp, "FA", rt, (a, b))
    assert len(rt.entries) == 2 and "centre" not in rt.entries
    assert sum(gr.stats["entries"].values()) == 2
    _, rc = _connect(sp, "FA", a, b, mode="centre")
    assert math.dist(rc.segs[0][1], a.pos) < 1e-9 and math.dist(rc.segs[-1][2], b.pos) < 1e-9


def test_grid_router_straight_entry_has_no_corner(tmp_path):
    p, info, plan, sp = _plan(tmp_path, [_part("Q1", 110.0, 110.0), _part("Q2", 116.0, 110.0)])
    a, b = _pad(sp, "Q1"), _pad(sp, "Q2")
    gr, rt = _connect(sp, "FA", a, b)
    _check_rule_d(sp, "FA", rt, (a, b))
    assert len(rt.segs) == 1 and rt.entries == ["straight", "straight"]


def test_grid_router_axial_entry_runs_along_the_axis(tmp_path):
    # Q2 above Q1 on the long axis: in through the short edges, along the axis
    p, info, plan, sp = _plan(tmp_path, [_part("Q1", 137.0, 118.0), _part("Q2", 137.0, 112.0)])
    a, b = _pad(sp, "Q1"), _pad(sp, "Q2")
    gr, rt = _connect(sp, "FA", a, b)
    _check_rule_d(sp, "FA", rt, (a, b))
    for pad, (u, v) in ((a, (rt.segs[0][2], rt.segs[0][1])), (b, (rt.segs[-1][1], rt.segs[-1][2]))):
        assert abs(u[0] - v[0]) < 1e-6                       # along the land's (vertical) axis
        assert math.dist(v, pad.pos) == pytest.approx(0.25, abs=1e-3)    # the centre line's end


def test_grid_router_necks_a_wide_track_at_a_small_two_terminal_land(tmp_path):
    cap = ("C9", "100n", "x:C_0603", 118.0, 112.0, 0.0,
           [("1", "FA", -0.8, 0.0, 0.8, 0.95, "smd", 0.0, "", "passive"),
            ("2", "FB", 0.8, 0.0, 0.8, 0.95, "smd", 0.0, "", "passive")], (1.5, 0.8))
    p, info, plan, sp = _plan(tmp_path, [_part("Q1", 110.0, 112.0), cap])
    a, b = _pad(sp, "Q1"), _pad(sp, "C9", "1")
    rule = plan.pad_rule(b.idx)
    assert rule.neck == 0.3
    gr, rt = _connect(sp, "FA", a, b, w=0.5)
    _check_rule_d(sp, "FA", rt, (a, b))
    last = len(rt.segs) - 1
    assert rt.necks == {last: 0.3} and rt.seg_w(last) == 0.3 and rt.seg_w(0) == 0.5
    # the wide copper ends neck_len off the land; the step is at the end of the wide copper
    for l, u, v in rt.segs[:-1]:
        assert b.geom.distance(LineString([u, v])) - 0.25 >= PE.NECK_LEN - 2e-3
    assert gr.stats["necks"] == 1


def test_grid_router_falls_back_to_the_old_entry_when_no_anchor_is_free(tmp_path):
    """A land boxed in on three sides by another net's copper still connects."""
    p, info, plan, sp = _plan(tmp_path, [_part("Q1", 110.0, 110.0), _part("Q2", 116.0, 110.0)])
    a, b = _pad(sp, "Q1"), _pad(sp, "Q2")
    x, y = b.pos
    for u, v in (((x - 1.2, y - 1.4), (x + 1.2, y - 1.4)), ((x + 1.2, y - 1.4), (x + 1.2, y + 1.4)),
                 ((x - 1.2, y + 1.4), (x + 1.2, y + 1.4))):
        sp.add_track("OTHER", "F.Cu", 0.2, u, v)
    gr, rt = _connect(sp, "FA", a, b)
    assert rt is not None and rt.segs
    for i, (l, u, v) in enumerate(rt.segs):
        assert not sp.track_violations("FA", l, rt.seg_w(i), u, v, tol=TOL)


def test_route_commit_sites_use_the_neck_width(tmp_path):
    from kae.route import lastmile as LM
    cap = ("C9", "100n", "x:C_0603", 118.0, 112.0, 0.0,
           [("1", "FA", -0.8, 0.0, 0.8, 0.95, "smd", 0.0, "", "passive"),
            ("2", "FB", 0.8, 0.0, 0.8, 0.95, "smd", 0.0, "", "passive")], (1.5, 0.8))
    p, info, plan, sp = _plan(tmp_path, [_part("Q1", 110.0, 112.0), cap])
    gr, rt = _connect(sp, "FA", _pad(sp, "Q1"), _pad(sp, "C9", "1"), w=0.5)
    new = LM._commit(sp, rt)
    ws = sorted({round(it.width, 3) for it in new if it.kind == "track"})
    assert ws == [0.3, 0.5]


def test_arm_e_lays_power_coppers_ground_vias_before_routing(tmp_path):
    """lastmile.ground_vias: power copper's selection (capacitor and decoupled IC ground pads)
    and placement, into the B.Cu ground pour, each via and its pad-to-via track legal, a necked
    land's track no wider than its neck."""
    from kae.route import lastmile as LM
    p, info, plan, sp = _plan(tmp_path, [])
    b = load(p)
    fp = {"GND": {"B.Cu": [z.outline for z in b.zones if z.net == "GND"]}}
    n = LM.ground_vias(sp, b, plan, fp, log=lambda *a: None)
    vias = [it for it in sp.routed if it.kind == "via"]
    assert n >= 2 and len(vias) == n and all(it.owner[0] == "escape-gvia" and it.uuid for it in vias)
    from kae.circuit.brief import build
    pads = PC.ground_via_pads(sp, build(b), {"GND"})
    assert {it.owner[0] for it in pads} >= {"C1", "C2"}
    for t in (it for it in sp.routed if it.kind == "track"):
        pad = next(x for x in pads if x.uuid == t.owner[1])
        nk = plan.pad_rule(pad.idx).neck
        assert nk is None or t.width <= nk + 1e-9


def test_arm_e_vias_are_written_locked(tmp_path):
    """plane_escapes with escape_ground_vias: the ground vias and their tracks are fixed wiring
    (locked), so Freerouting keeps the site and the repair loop never rips or unlocks them."""
    from kae.route import critical_write as W
    from kae.route import lastmile as LM
    p, info, plan, sp = _plan(tmp_path, [])
    b = load(p)
    fills = [dict(net="GND", layers={"B.Cu": [[[list(c) for c in z.outline.exterior.coords]]]})
             for z in b.zones if z.net == "GND"]
    out = tmp_path / "esc.kicad_pcb"
    rep = LM.plane_escapes(p, info, plan, fills, out, balls=False, log=lambda *a: None,
                           escape_opts={"escape_ground_vias": 1})
    assert rep["ground_vias"] >= 2
    items = W.routing(out)
    vias = [r for r in items if r["kind"] == "via"]
    assert len(vias) >= rep["ground_vias"] and sum(r["locked"] for r in vias) == rep["ground_vias"]


def test_route_keeps_off_other_lands_of_its_net(tmp_path):
    """Q3, a land of the same net between Q1 and Q2, is passed around, not crossed."""
    p, info, plan, sp = _plan(tmp_path, [_part("Q1", 137.0, 104.0), _part("Q2", 137.0, 112.0),
                                         _part("Q3", 137.0, 108.0)])
    a, b, q3 = _pad(sp, "Q1"), _pad(sp, "Q2"), _pad(sp, "Q3")
    gr, rt = _connect(sp, "FA", a, b)
    _check_rule_d(sp, "FA", rt, (a, b))
    assert all(q3.geom.distance(LineString([u, v])) >= 0.125 - 1e-6 for _, u, v in rt.segs)
    assert gr.stats["lands_kept_out"] >= 1 and gr.stats["fallback_crossing"] == 0
    # boxed in by its own net's land with no way round: crossing it is the fallback, not a failure
    _, rc = _connect(sp, "FA", a, b, mode="centre")
    assert rc is not None


def test_a_necked_land_with_copper_stays_a_leaf(tmp_path):
    """A route of the net does not leave from a necked land that already has its track (the neck
    carries that land's current only); it joins the track instead."""
    cap = ("C9", "100n", "x:C_0603", 118.0, 112.0, 0.0,
           [("1", "FA", -0.8, 0.0, 0.8, 0.95, "smd", 0.0, "", "passive"),
            ("2", "FB", 0.8, 0.0, 0.8, 0.95, "smd", 0.0, "", "passive")], (1.5, 0.8))
    p, info, plan, sp = _plan(tmp_path, [_part("Q1", 110.0, 112.0), cap, _part("Q2", 117.2, 118.0)])
    c9 = _pad(sp, "C9", "1")
    gr, rt = _connect(sp, "FA", _pad(sp, "Q1"), c9, w=0.5)
    from kae.route import lastmile as LM
    new = LM._commit(sp, rt)
    tracks = [Anchor(it.geom, tuple(it.layers), None, grow=it.r * 0.8, kind="track") for it in new if it.kind == "track"]
    gr2 = GridRouter(sp)
    rt2 = gr2.connect("FA", [_anchor(c9)] + tracks, [_anchor(_pad(sp, "Q2"))], 0.5, ["F.Cu"], via=False)
    assert rt2 is not None and gr2.stats["neck_leaf"] == 1
    assert all(c9.geom.distance(LineString([u, v])) >= 0.25 - 1e-6 for _, u, v in rt2.segs)


def test_module_hops_rank_entries_by_the_modules_physics(tmp_path):
    """critical_modules._entry_by_physics: each module's quote with rule-D candidates is no worse
    than with the old entry only (pad_entry "centre"), and no kept entry is acute."""
    old = F.session(tmp_path / "c", pad_entry="centre").route()
    new = F.session(tmp_path / "d", entry_guard=True).route()
    v0 = {m.id: m.physics.get("value") for m in old.modules if m.physics.get("value")}
    v1 = {m.id: m.physics.get("value") for m in new.modules if m.physics.get("value")}
    assert v0 and set(v0) == set(v1)
    acute = {m.id for m in old.modules if any("centre_acute" in (r.entries if r else ()) for r in m.hops.values())}
    for k in v0:
        # an old entry that was acute is forbidden now, so its module may pay for that (U2's decap)
        assert v1[k] <= v0[k] * 1.001 or k in acute, (k, v0[k], v1[k])
    assert any(v1[k] < v0[k] * 0.999 for k in v0)                  # and some module gains (the crystal)
    guarded = [m for m in new.modules if m.physics.get("entry_guard")]
    assert guarded and all(m.physics["entry_guard"]["kept"] in ("rule_d", "old") for m in guarded)
    for m in guarded:                                              # the old routing only where it quotes lower
        g = m.physics["entry_guard"]
        if g["kept"] == "old":
            assert g["old"] < g["rule_d"]
    assert new.router.stats.get("quoted", 0) > 0
    # an acute entry is kept only where nothing else routes the hop: fewer than with the old entry
    def n_acute(s):
        return sum("centre_acute" in (r.entries if r else ()) for m in s.modules for r in m.hops.values())
    assert n_acute(new) < n_acute(old)


def test_join_at_corners_adds_no_copper_at_rule_d_pad_ends(tmp_path):
    """KiCad joins any overlap; Freerouting gets a DSN pin tie. A rule-D end off the pad centre
    gets no extra piece to the centre on the board."""
    s = F.session(tmp_path, corner_joins=False).route()
    sp = s.space
    before = {id(it) for it in sp.routed}
    rep = s.join_at_corners()
    assert rep["pin_ties"] >= 1
    centres = {(round(p.pos[0], 6), round(p.pos[1], 6)) for p in sp.pads if p.kind == "pad" and p.pos is not None}
    for t in (it for it in sp.routed if it.kind == "track" and id(it) not in before):
        assert not any((round(q[0], 6), round(q[1], 6)) in centres for q in (t.geom.coords[0], t.geom.coords[-1]))


def test_space_measures_pads_from_their_real_copper(tmp_path):
    """A pad whose DSN shape lies inside its copper (a custom pad's first outline, chords of
    rounded corners): the DSN pin class adds the largest excess on every side, Space measures from
    the real copper with the plain requirement, so it is exact on every side and never laxer."""
    p = F.write_board(tmp_path, extra=[_part("Q1", 110.0, 110.0)])
    info = F.synth_info(load(p))
    pd = next(x for x in info["pads"] if x["ref"] == "Q1")
    x, y = pd["pos"]
    tab = [[x + 0.5, y - 0.2], [x + 0.6, y - 0.2], [x + 0.6, y + 0.2], [x + 0.5, y + 0.2], [x + 0.5, y - 0.2]]
    pd["poly"] = [pd["poly"][0], [tab]]                  # a second outline: 0.1 mm of copper past the DSN shape
    plan = CN.plan(info, p, {})
    sp = Space(load(p), info, plan=plan)
    it = _pad(sp, "Q1")
    assert (pd["comp"], pd["pin"]) in plan.pin_exact
    dsn_need = plan.obstacle_classes[it.cls].values[(sp.rc("GND"), "F.Cu")][0]
    assert dsn_need == pytest.approx(0.3, abs=1e-3)      # 0.2 clearance + 0.1 excess, on every side
    assert sp.need(it, "GND", "track", "F.Cu") == pytest.approx(0.2, abs=1e-6)
    assert it.geom.contains(Point(x + 0.55, y))          # the tab is copper Space keeps clear of
    # never laxer: a track 0.21 mm from the tab is legal, 0.19 mm is not; on the far side 0.21 mm is
    # legal where the DSN class alone would have asked 0.3 mm
    assert not sp.track_violations("GND", "F.Cu", 0.2, (x + 0.91, y - 1), (x + 0.91, y + 1))
    assert sp.track_violations("GND", "F.Cu", 0.2, (x + 0.89, y - 1), (x + 0.89, y + 1))
    assert not sp.track_violations("GND", "F.Cu", 0.2, (x - 0.81, y - 1), (x - 0.81, y + 1))
