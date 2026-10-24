# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""kae.place.legalize: windowed CP-SAT repair and the exact polygon check."""
from pathlib import Path

import numpy as np
import shapely

from kae.board.kicad_file import load
from kae.place.legalize import exact_check, kicad_violations, legalize, repair_kicad, violation_parts
from kae.place.problem import Problem
from kae.place.state import State, grid_violations

FIXTURE = Path(__file__).parent / "data" / "board" / "fixture.kicad_pcb"


def _pile():
    P = Problem.build(load(FIXTURE))
    st = State(P)
    for i in P.mov:                       # every movable part on one spot
        st.X[i], st.Y[i], st.K[i] = P.ncx // 2, P.ncy // 2, 0
    return P, st


def test_legalize_a_pile_then_exact_check_passes():
    P, st = _pile()
    assert grid_violations(st)
    rep = legalize(P, st, time_s=30.0, workers=2, seed=0)
    assert rep["end_violators"] == 0
    assert not grid_violations(st)
    assert exact_check(P, st) == []
    # locked parts and keepouts are respected on their sides
    for ob in P.obstacles:
        for i in P.mov:
            for side, r, _ in st.grid_rects(i):
                if side == ob.side:
                    assert r[1] <= ob.g[0] or ob.g[1] <= r[0] or r[3] <= ob.g[2] or ob.g[3] <= r[2]


def test_exact_check_reports_overlaps_and_outline():
    P, st = _pile()
    legalize(P, st, time_s=30.0, workers=2, seed=0)
    parts = {p.ref: p.i for p in P.parts}
    a, b = parts["U1"], parts["U2"]
    st.X[b], st.Y[b], st.K[b] = st.X[a], st.Y[a], st.K[a]
    types = {v["type"] for v in exact_check(P, st)}
    assert "courtyards_overlap" in types
    st.X[b], st.Y[b] = -400, -400          # far outside the board
    types = {v["type"] for v in exact_check(P, st)}
    assert "pad_outside" in types
    assert ("outline", ) == tuple(r[0] for r in grid_violations(st)[b] if r[0] == "outline")


def test_kicad_violations_become_constraints():
    P, st = _pile()
    legalize(P, st, time_s=30.0, workers=2, seed=0)
    parts = {p.ref: p.i for p in P.parts}
    a, b = parts["U1"], parts["U2"]
    (ax, ay), (bx, by) = st.pins_xy(a)[0], st.pins_xy(b)[0]
    drc = {"violations": [
        {"type": "courtyards_overlap", "severity": "error", "description": "Courtyards overlap",
         "items": [{"description": "Footprint U1", "pos": {"x": ax, "y": ay}},
                   {"description": "Footprint U2", "pos": {"x": bx, "y": by}}]},
        {"type": "silk_overlap", "severity": "warning", "items": []},
        {"type": "clearance", "severity": "error", "description": "Clearance violation",
         "items": [{"description": "Pad 1 [] of nowhere", "pos": {"x": ax, "y": ay}}]}]}
    vs = kicad_violations(drc)
    assert [v["type"] for v in vs] == ["courtyards_overlap", "clearance"]
    assert violation_parts(P, st, vs[0]) == {a, b}
    assert violation_parts(P, st, vs[1]) == {a}            # unknown reference: nearest pad
    before = {i: P.parts[i].rots[0].g_own for i in (a, b)}
    rep = repair_kicad(P, st, vs, time_s=30.0, workers=2, seed=0, step_mm=0.2)
    assert set(rep["parts"]) == {"U1", "U2"} and rep["by_type"] == {"courtyards_overlap": 1, "clearance": 1}
    for i in (a, b):                                       # the rectangles grew for good
        g0, g1 = before[i], P.parts[i].rots[0].g_own
        assert g1[0] < g0[0] and g1[1] > g0[1] and g1[2] < g0[2] and g1[3] > g0[3]
    assert not grid_violations(st) and exact_check(P, st) == []


def test_closed_loop_repair_ends_exactly_legal():
    """The closed loop (kae.place.exact.repair): exact findings -> culprits -> moved to spots
    the exact check passes, until none is left."""
    from kae.place import exact
    P, st = _pile()
    legalize(P, st, time_s=30.0, workers=2, seed=0)
    parts = {p.ref: p.i for p in P.parts}
    a, b = parts["U1"], parts["U2"]
    st.X[b], st.Y[b], st.K[b] = st.X[a], st.Y[a], st.K[a]        # an overlap
    st.X[parts["U3"]], st.Y[parts["U3"]] = 1, 1                 # pads off the board
    assert exact_check(P, st)
    rep = exact.repair(P, st, time_s=30.0)
    assert rep["start"] > 0 and rep["end"] == 0 and not rep["stuck"]
    assert exact_check(P, st) == []


def test_kicad_feedback_becomes_a_constraint_the_repair_honours():
    """KiCad sees what the model cannot (a solder-mask aperture drawn past a courtyard): its
    error between two parts becomes a separation the exact model enforces, so the repair
    moves the culprit and the check stays clean only once they are apart."""
    from kae.place import exact
    P, st = _pile()
    legalize(P, st, time_s=30.0, workers=2, seed=0)
    assert exact_check(P, st) == []
    i, j = P.parts[P.mov[0]], P.parts[P.mov[1]]
    report = {"violations": [{"type": "solder_mask_bridge", "severity": "error", "items": [
        {"description": f"Pad 1 [x] of {i.ref} on F.Cu", "pos": {"x": 0, "y": 0}},
        {"description": f"Pad 2 [y] of {j.ref} on F.Cu", "pos": {"x": 0, "y": 0}}]}]}
    fb = exact.kicad_feedback(P, st, report, step=0.5)
    assert fb["errors"] == 1 and fb["constraints"] == 2
    E = exact.ExactModel(P, st)
    d0 = E.hull(E.sh[i.i]).distance(E.hull(E.sh[j.i]))
    assert any(v["type"] == "kicad_feedback" for v in exact_check(P, st))
    rep = exact.repair(P, st, time_s=30.0)
    assert rep["end"] == 0
    E = exact.ExactModel(P, st)
    assert E.hull(E.sh[i.i]).distance(E.hull(E.sh[j.i])) >= d0 + 0.5 - 1e-6


def test_reseed_places_a_pile_and_overhang_keeps_only_pads_in():
    """Escalation steps of the closed loop: a constructive re-seed (biggest first, each at an
    exactly clean spot, looking ahead for the next big parts) places a pile exactly legal;
    allow_overhang lets a courtyard hang over the edge while its pads stay in."""
    import time
    from kae.place import exact
    P, st = _pile()
    E = exact.ExactModel(P, st)
    failed = exact.reseed(P, st, E, set(P.mov), time.monotonic() + 60)
    assert not failed and exact_check(P, st) == []
    i = max(P.mov, key=lambda q: P.parts[q].area)
    before = P.parts[i].rots[0].g_board
    assert P.allow_overhang([i]) == [P.parts[i].ref]
    a, b = P.parts[i].rots[0].g_board, before
    assert (a[1] - a[0]) * (a[3] - a[2]) <= (b[1] - b[0]) * (b[3] - b[2])


def test_exact_check_reports_hole_clearance():
    """Regression (olimex-mipi-hdmi): KiCad's hole_clearance (a hole's edge to another net's
    copper) was not modelled, so placements the exact check passed had 13 KiCad errors."""
    from kae.place.legalize import exact_check
    P, st = _pile()
    legalize(P, st, time_s=30.0, workers=2, seed=0)
    parts = {p.ref: p.i for p in P.parts}
    j1, u = P.parts[parts["J1"]], parts["U1"]
    hole = next(k for k, pd in enumerate(j1.fp.pads) if pd.drill)
    hx, hy = st.pins_xy(j1.i)[hole]
    r = j1.fp.pads[hole].drill / 2
    pad = P.parts[u].fp.pads[0]                       # SIG1, not J1's net
    w = max(pad.size) / 2
    st.X[u], st.Y[u] = P.grid_of(hx + r + 0.6 + w - pad.lx, hy - pad.ly)
    st.K[u] = 0
    P.board.rules.hole_clearance = 0.0
    assert not [v for v in exact_check(P, st, parts=[u], max_items=500) if v["type"] == "hole_clearance"]
    P.board.rules.hole_clearance = 1.5
    hits = [v for v in exact_check(P, st, parts=[u], max_items=500) if v["type"] == "hole_clearance"]
    assert any(set(v["refs"]) == {"J1", "U1"} for v in hits)


def test_mask_openings_of_different_nets_bridge():
    """Regression (latentred-pdu, envopenpico): KiCad flags solder-mask openings (pad + mask
    expansion) of different nets closer than the board's minimum mask web; the exact model
    did not check them, so KiCad's DRC found bridges on 'legal' placements."""
    from kae.place.legalize import exact_check
    P, st = _pile()
    legalize(P, st, time_s=30.0, workers=2, seed=0)
    parts = {p.ref: p.i for p in P.parts}
    a, b = P.parts[parts["U1"]], P.parts[parts["U2"]]      # both on the front
    pa, pb = a.fp.pads[0], b.fp.pads[0]
    for pd in (pa, pb):
        pd.layers = ["F.Cu", "F.Mask"]
    ax, ay = st.pins_xy(a.i)[0]
    gap = 0.3                                             # copper clearance is met
    P.board.rules.clearance = 0.1
    st.X[b.i], st.Y[b.i] = P.grid_of(ax + max(pa.size) / 2 + gap + max(pb.size) / 2 - pb.lx, ay - pb.ly)
    st.K[b.i] = 0
    P.board.rules.mask_margin = 0.0
    P.board.rules.mask_min_width = 0.0

    def bridges():
        return [v for v in exact_check(P, st, parts=[b.i], max_items=500)
                if v["type"] == "solder_mask_bridge" and set(v["refs"]) == {"U1", "U2"}]
    assert not bridges()
    P.board.rules.mask_margin = 0.2                       # 0.4 of expansion > 0.3 gap
    assert bridges()
    P.board.rules.mask_margin = 0.0
    P.board.rules.mask_min_width = 0.5                    # web too thin
    assert bridges()


def test_kicad_zone_error_keeps_the_part_off_the_whole_zone():
    """Regression (latentred-pdu): KiCad reports a zone at one point; a disc there let the
    culprit slide to another spot of the same zone for 6 rounds. A zone item now keeps the
    part off the zone's outline."""
    from shapely.geometry import box as sbox
    from kae.board.model import Zone
    from kae.place import exact
    P, st = _pile()
    legalize(P, st, time_s=30.0, workers=2, seed=0)
    i = P.parts[P.mov[0]]
    x, y = st.xy(i.i)
    P.board.zones.append(Zone(uuid="z", name="", net="Z", layers=["F.Cu"], outline=sbox(x - 6, y - 6, x + 6, y + 6)))
    report = {"violations": [{"type": "solder_mask_bridge", "severity": "error", "items": [
        {"description": f"Pad 1 [x] of {i.ref} on F.Cu", "pos": {"x": x, "y": y}},
        {"description": "Zone [Z] on F.Cu, priority 0", "pos": {"x": x + 5, "y": y}}]}]}
    fb = exact.kicad_feedback(P, st, report)
    assert fb["constraints"] == 1
    (g, why), = P.feedback["avoid"][i.i]
    assert g.contains(sbox(x - 5.9, y - 5.9, x + 5.9, y + 5.9))


def test_exact_rules_follow_kicad_on_copperless_pads_roundrects_and_custom_rules():
    """Regressions from the human-placement gate (humangate.py: the human placement must show
    no finding KiCad's DRC does not): a paste-only or copperless NPTH pad is no copper; a
    roundrect has rounded corners; a custom .kicad_dru clearance rule for a library replaces
    the netclass clearance; a net-less fiducial whose mask expansion equals its fill gap does
    not bridge to the zone."""
    from kae.board.model import Pad
    from kae.place import exact
    from kae.place.legalize import pad_shape
    paste = Pad(number="", net="", kind="smd", shape="rect", size=(1, 1), lx=0, ly=0, lrot=0, x=0, y=0,
                layers=["F.Paste"])
    npth = Pad(number="", net="", kind="np_thru_hole", shape="circle", size=(2, 2), lx=0, ly=0, lrot=0, x=0, y=0,
               layers=["*.Cu", "*.Mask"], drill=2.0)
    ring = Pad(number="", net="", kind="np_thru_hole", shape="circle", size=(3, 3), lx=0, ly=0, lrot=0, x=0, y=0,
               layers=["*.Cu", "*.Mask"], drill=2.0)
    assert exact._no_copper(paste) and exact._no_copper(npth) and not exact._no_copper(ring)
    rr = Pad(number="1", net="", kind="smd", shape="roundrect", size=(1.0, 0.5), lx=0, ly=0, lrot=0, x=0, y=0,
             layers=["F.Cu"], rratio=0.25)
    assert pad_shape(rr).area < 0.5 - 1e-3                  # corners cut
    P, st = _pile()
    P.board.rules.custom = [dict(name="small", condition="A.memberOfFootprint('kae_test:ASYM3')",
                                 constraints=[dict(type="clearance", min=0.05)])]
    cc = exact._custom_clearances(P)
    assert cc and cc[0][1:] == ("lib", "kae_test:ASYM3", 0.05)
    E = exact.ExactModel(P, st)
    i, j = P.mov[0], P.mov[1]
    assert E._rule_clr(i, E.sh[i], j, E.sh[j]) in (0.05, None)


def _held_chain():
    """The fixture legalized, with a J1 -> U7 -> U1 protection chain that holds: U1 at a clean
    spot far from J1, U7 at the clean spot nearest J1. Returns (P, st, E, guard, ref)."""
    from kae.place import clusters, exact
    P, st = _pile()
    legalize(P, st, time_s=30.0, workers=2, seed=0)
    ref = {p.ref: p for p in P.parts}
    u = {r: p.uuid for r, p in ref.items()}
    brief = {"structures": [
        {"kind": "connector_chain", "connector": u["J1"], "pin": "1", "net": "VCC", "protected": True,
         "protection": [u["U7"]], "chain": [[u["J1"], "1"], [u["U7"], "3"], [u["U1"], "3"]]}]}
    P.order_rules = clusters.protection_order(P, brief)
    E = exact.ExactModel(P, st)
    cx, cy = st.xy(ref["J1"].i)
    guard = exact.OrderGuard(P, st)

    def spots(i):
        return [(X, Y, k) for c, X, Y, k in exact._candidates(P, st, i, *exact._tables(P, st, {i}),
                                                              list(range(4)), 0.0, 4000)]
    i1, i7 = ref["U1"].i, ref["U7"].i
    far = sorted(spots(i1), key=lambda t: -abs(P.ox + t[0] * P.g - cx) - abs(P.oy + t[1] * P.g - cy))
    for X, Y, k in far[:200]:
        if not E.findings_at(i1, X, Y, k):
            E.set_pose(i1, X, Y, k)
            break
    near = sorted(spots(i7), key=lambda t: abs(P.ox + t[0] * P.g - cx) + abs(P.oy + t[1] * P.g - cy))
    for X, Y, k in near[:400]:
        if not E.findings_at(i7, X, Y, k) and guard.count_at(i7, X, Y, k) == 0:
            E.set_pose(i7, X, Y, k)
            break
    assert guard.total() == 0 and not exact_check(P, st)
    return P, st, E, guard, ref


def test_repair_keeps_protection_order():
    """Regression (stickhub at fe68468): the closed loop's repair cleared a mask bridge by
    moving a protection part to the far side of what it protects (3 of its 24 rules broken
    locally, annealed 0). A repair move or eviction may not break an order rule that holds."""
    from shapely.geometry import Point
    from kae.place import exact
    P, st, E, guard, ref = _held_chain()
    # KiCad objects to U7 where it is: the repair must move it and keep the chain
    x7, y7 = st.xy(ref["U7"].i)
    P.feedback = {"sep": {}, "avoid": {ref["U7"].i: [(Point(x7, y7).buffer(1.0), "test")]}}
    rep = exact.repair(P, st, time_s=30.0)
    assert rep["end"] == 0 and "U7" in rep["moved"]
    assert rep["order_broken"] == [0, 0]


def test_move_clean_skips_a_spot_that_breaks_protection_order(monkeypatch):
    """The guard itself: of two exactly clean spots, the nearer one puts the protection part
    farther from the connector than the protected part; the repair takes the other."""
    import time
    from kae.place import exact
    P, st, E, guard, ref = _held_chain()
    i7 = ref["U7"].i
    cands = [(X, Y, k) for c, X, Y, k in exact._candidates(P, st, i7, *exact._tables(P, st, {i7}), list(range(4)),
                                                           0.0, 4000) if not E.findings_at(i7, X, Y, k)]
    bad = next(t for t in cands if guard.count_at(i7, *t) > 0)
    good = next(t for t in cands if guard.count_at(i7, *t) == 0)
    E.set_pose(i7, *good)                                # where it stands, the rule holds
    monkeypatch.setattr(exact, "_candidates", lambda *a, **k: [(0.0, *bad), (1.0, *good)])
    E.findings_at = lambda i, X, Y, K, **kw: []          # both spots clean
    ok, _ = exact.move_clean(P, st, E, i7, time.monotonic() + 30)
    assert ok and (int(st.X[i7]), int(st.Y[i7]), int(st.K[i7])) == tuple(good)
    assert guard.total() == 0


def test_kicad_round_that_moves_parts_refreshes_order_and_physics(monkeypatch):
    """The report's protection order and physics scorecard describe the board as written: a
    KiCad DRC round whose repair moves parts recomputes them (place()'s values stay as
    *_pre_drc); a loop that moves nothing leaves them alone."""
    import time
    from types import SimpleNamespace
    from kae import cli
    from kae.place import exact
    from kae.place.pipeline import Result, final_physics
    from kae.route import drc as kdrc
    P, st, E, guard, ref = _held_chain()
    i7 = ref["U7"].i
    u7 = ref["U7"].uuid

    class Terms:              # a scorecard that follows U7's x
        def breakdown(self, poses):
            return [dict(id="s", kind="k", util=abs(poses[u7][0]) / 100.0, value=0.0, unit="")]
    res = Result(poses=st.poses(), report={}, state=st, problem=P, terms=Terms(), order=P.order_rules)
    final_physics(res)
    assert res.report["protection_order"]["violated"] == 0
    pre = dict(res.report)
    cands = [(X, Y, k) for c, X, Y, k in exact._candidates(P, st, i7, *exact._tables(P, st, {i7}), list(range(4)),
                                                           0.0, 4000) if not E.findings_at(i7, X, Y, k)]
    bad = next(t for t in cands if guard.count_at(i7, *t) > 0)
    errors = iter([1, 0, 0])
    monkeypatch.setattr(kdrc, "kicad_cli", lambda: "kicad-cli")
    monkeypatch.setattr(kdrc, "stage_board", lambda out, inp, tmp: out)
    monkeypatch.setattr(kdrc, "run", lambda staged, path, timeout: {})
    monkeypatch.setattr(exact, "kicad_feedback", lambda P, st, rep: dict(errors=next(errors), by_type={}, fixed_only=0))

    def repair(P, st, time_s, log=None):
        st.X[i7], st.Y[i7], st.K[i7] = bad
        return dict(moved=["U7"], findings=[])
    monkeypatch.setattr(exact, "repair", repair)
    a = SimpleNamespace(drc="on", drc_rounds=2, time=600.0, output="out.kicad_pcb", input="in.kicad_pcb", writer="sexpr")
    clean, _ = cli._kicad_loop(a, res, time.monotonic(), lambda *x, **k: dict(writer="fake"))
    assert clean
    assert res.report["protection_order_pre_drc"] == pre["protection_order"]
    assert res.report["scorecard_pre_drc"] == pre["scorecard"]
    assert res.report["protection_order"]["violated"] == 1
    assert res.report["scorecard"]["total_linear"] != pre["scorecard"]["total_linear"]
    # a clean first round moves nothing: no *_pre_drc
    res2 = Result(poses=st.poses(), report={}, state=st, problem=P, terms=Terms(), order=P.order_rules)
    final_physics(res2)
    errors = iter([0])
    cli._kicad_loop(a, res2, time.monotonic(), lambda *x, **k: dict(writer="fake"))
    assert "protection_order_pre_drc" not in res2.report and "scorecard_pre_drc" not in res2.report


def test_kicad_error_with_board_text_keeps_the_named_part_off_the_text():
    """sparkfun-xrp-controller (seed 2): KiCad's clearance error between J3's pad and the
    copper text 'v20' stayed through 6 rounds. The text item names no part, so matching it by
    position blamed whichever part had a pad nearest the text's anchor; now the named part
    alone keeps off the text, by more each time KiCad still objects."""
    from kae.place import exact
    P, st = _pile()
    legalize(P, st, time_s=30.0, workers=2, seed=0)
    i, j = P.parts[P.mov[0]], P.parts[P.mov[1]]
    jx, jy = (float(c) for c in st.pins_xy(j.i)[0])       # the text's anchor on j's pad
    report = {"violations": [{"type": "clearance", "severity": "error", "items": [
        {"description": f"Pad 1 [x] of {i.ref} on F.Cu", "pos": {"x": 0, "y": 0}},
        {"description": "PCB text 'v20' on F.Cu", "pos": {"x": jx, "y": jy}, "uuid": "no-such-text"}]}]}
    fb = exact.kicad_feedback(P, st, report, step=0.5)
    assert fb["errors"] == 1 and fb["constraints"] == 1
    assert set(P.feedback["avoid"]) == {i.i} and not P.feedback["sep"]
    exact.kicad_feedback(P, st, report, step=0.5)                 # KiCad still objects: wider
    (g1, _), (g2, _) = P.feedback["avoid"][i.i]
    assert g2.area > g1.area
    # only fixed parts named: nothing to move
    fixed = next((p for p in P.parts if not p.movable), None)
    if fixed is not None:
        rep2 = {"violations": [{"type": "clearance", "severity": "error", "items": [
            {"description": f"Footprint {fixed.ref}", "pos": {"x": 0, "y": 0}},
            {"description": "PCB text 'x' on F.Cu", "pos": {"x": jx, "y": jy}}]}]}
        assert exact.kicad_feedback(P, st, rep2)["fixed_only"] == 1


def test_knockout_text_box_carries_kicads_margin(tmp_path):
    """Knockout copper text is copper around the glyphs, grown by max(thickness/2, height/9)."""
    from kae.board import sexpr
    from kae.board.kicad_file import _text_box
    from kae.place.problem import board_texts
    node = ('(gr_text "v20" (at 10 10 0) (layer "B.Cu"{}) (uuid "u1") (effects (font (size 1.27 1.27) '
            '(thickness 0.254) (bold yes)) (justify mirror)))')
    plain = _text_box(sexpr.parse(node.format("")))
    ko = _text_box(sexpr.parse(node.format(" knockout")))
    m = max(0.254 / 2, 1.27 / 9)
    (a0, b0, c0, d0), (a1, b1, c1, d1) = plain.bounds, ko.bounds
    assert abs((a0 - a1) - m) < 1e-9 and abs((d1 - d0) - m) < 1e-9
    f = tmp_path / "t.kicad_pcb"
    f.write_text("(kicad_pcb (version 20240108) " + node.format(" knockout") + ")")
    from types import SimpleNamespace
    assert board_texts(SimpleNamespace(path=str(f)))["u1"].equals(ko)


def test_kicad_edge_error_grows_the_named_parts_edge_clearance():
    """paw3222 (seed 1): KiCad's copper_edge_clearance (0.175 < 0.2 mm, inside the model's
    tolerance for polygonized arcs) named 'Segment on Edge.Cuts' and J1's pad; the edge item
    was matched by position to U1, so the feedback asked J1 and U1 to keep apart and the repair
    never moved anything over 6 rounds. Now the edge item names no part and J1's own edge
    clearance grows until the repair moves it."""
    from kae.place import exact
    P, st = _pile()
    legalize(P, st, time_s=30.0, workers=2, seed=0)
    E = exact.ExactModel(P, st)
    boundary = P.outline.boundary
    dist = {i: min(g.distance(boundary) for g, k, pd in E.sh[i]["pads"]) for i in P.mov if E.sh[i]["pads"]}
    i = min(dist, key=dist.get)                                 # the part nearest the edge
    j = min((q for q in dist if q != i), key=lambda q: float(np.min(np.hypot(*(st.pins_xy(q) - st.pins_xy(i)[0]).T))))
    jx, jy = (float(c) for c in st.pins_xy(j)[0])
    ref = P.parts[i].ref
    report = {"violations": [{"type": "copper_edge_clearance", "severity": "error", "items": [
        {"description": "Segment on Edge.Cuts", "pos": {"x": jx, "y": jy}},      # anchored by another part
        {"description": f"PTH pad 6 [SDIO] of {ref}", "pos": {"x": 0, "y": 0}}]}]}
    assert violation_parts(P, st, kicad_violations(report)[0]) == {i}
    fb = exact.kicad_feedback(P, st, report)
    assert fb["constraints"] == 1 and not P.feedback["sep"] and not P.feedback["avoid"]
    assert P.feedback["edge"] == {i: exact.EDGE_STEP}
    # KiCad keeps objecting until the model sees it too
    while not any(v["type"] == "copper_edge_clearance" and v["parts"] == [i] for v in exact_check(P, st)):
        exact.kicad_feedback(P, st, report)
    rep = exact.repair(P, st, time_s=30.0)
    assert rep["end"] == 0 and P.parts[i].ref in rep["moved"]
    E = exact.ExactModel(P, st)
    assert min(g.distance(boundary) for g, k, pd in E.sh[i]["pads"]) > dist[i]


def test_fix_order_moves_the_protection_part_back_within_the_physics_bound():
    """stickhub at 150 s: an annealer cut short leaves a protection-order rule broken, which the
    guarded repair keeps but does not fix. The final pass moves the protection part to the
    nearest clean spot that keeps the rule, unless the physics total would rise past its bound."""
    from kae.place import exact
    P, st, E, guard, ref = _held_chain()
    i7 = ref["U7"].i
    cands = [(X, Y, k) for c, X, Y, k in exact._candidates(P, st, i7, *exact._tables(P, st, {i7}), list(range(4)),
                                                           0.0, 4000) if not E.findings_at(i7, X, Y, k)]
    bad = next(t for t in reversed(cands) if guard.count_at(i7, *t) > 0)
    E.set_pose(i7, *bad)
    assert guard.total() == 1 and not exact_check(P, st)
    # every move costs more physics than the bound allows: nothing moves
    calls = []

    def phys():
        calls.append(1)
        return 1.0 if len(calls) == 1 else 2.0
    rep = exact.fix_order(P, st, time_s=30.0, phys=phys)
    assert rep["end"] == 1 and not rep["moved"] and rep["refused_physics"] >= 1
    assert (int(st.X[i7]), int(st.Y[i7]), int(st.K[i7])) == tuple(bad)
    # within the bound: U7 moves and the rule holds, exactly clean
    rep = exact.fix_order(P, st, time_s=30.0, phys=lambda: 1.0)
    assert rep["start"] == 1 and rep["end"] == 0 and rep["moved"] == ["U7"]
    assert not exact_check(P, st) and not grid_violations(st)


def test_kicad_loop_writes_the_best_judged_placement_back(monkeypatch):
    """The KiCad loop keeps the placement KiCad judged best: a later round that ends with more
    errors, or a repair KiCad never judged (its DRC failed), puts that one back on disk."""
    import time
    from types import SimpleNamespace
    from kae import cli
    from kae.place import exact
    from kae.place.pipeline import Result
    from kae.route import drc as kdrc
    P, st, E, guard, ref = _held_chain()
    i7 = ref["U7"].i
    spots = [(X, Y, k) for c, X, Y, k in exact._candidates(P, st, i7, *exact._tables(P, st, {i7}), list(range(4)),
                                                           0.0, 400)[1:4]]
    monkeypatch.setattr(kdrc, "kicad_cli", lambda: "kicad-cli")
    monkeypatch.setattr(kdrc, "stage_board", lambda out, inp, tmp: out)
    written = []

    def write(inp, out, poses, **k):
        written.append(dict(poses))
        return dict(writer="fake")

    def run_loop(verdicts, rounds):
        it = iter(verdicts)

        def run(staged, path, timeout):
            v = next(it)
            if v is None:
                raise kdrc.DrcError("kicad-cli failed")
            return {"n": v}
        monkeypatch.setattr(kdrc, "run", run)
        monkeypatch.setattr(exact, "kicad_feedback", lambda P, st, rep: dict(errors=rep["n"], by_type={}, fixed_only=0))
        moves = iter(spots)

        def repair(P, st, time_s, log=None):
            st.X[i7], st.Y[i7], st.K[i7] = next(moves)
            return dict(moved=["U7"], findings=[])
        monkeypatch.setattr(exact, "repair", repair)
        res = Result(poses=st.poses(), report={}, state=st, problem=P)
        a = SimpleNamespace(drc="on", drc_rounds=rounds, time=600.0, output="o", input="i", writer="sexpr")
        return res, cli._kicad_loop(a, res, time.monotonic(), write)

    start = (int(st.X[i7]), int(st.Y[i7]), int(st.K[i7]))
    res, (clean, _) = run_loop([2, 5, 3], 2)          # worse after the first repair: round 0 back
    assert clean is False and res.report["kicad_written_round"] == 0
    assert (int(st.X[i7]), int(st.Y[i7]), int(st.K[i7])) == start and written[-1] == res.poses
    assert res.poses[ref["U7"].uuid] == st.pose(i7)
    st.X[i7], st.Y[i7], st.K[i7] = start
    res, (clean, _) = run_loop([4, 1, None], 3)       # round 1 best; round 2's verdict never came
    assert res.report["kicad_written_round"] == 1
    assert (int(st.X[i7]), int(st.Y[i7]), int(st.K[i7])) == spots[0]
    st.X[i7], st.Y[i7], st.K[i7] = start
    res, (clean, _) = run_loop([3, 0], 2)             # clean: written as it is
    assert clean and res.report["kicad_written_round"] == 1


def test_mask_only_aperture_across_two_zone_fills_is_a_bridge():
    """KiCad 10 (drc_test_provider_solder_mask.cpp, checkMaskAperture): a simple mask aperture
    (a mask graphic with no copper, e.g. a mask-only logo) bridges when it exposes two distinct
    positive nets; zone fills count (stickhub: LOGO4 on B.Mask across the GND and +5V fills).
    Inside one fill it exposes one net; a pad's own opening drawn as a graphic is the pad's."""
    from shapely.geometry import box
    from kae.board.model import Zone
    from kae.place import exact
    P, st = _pile()
    legalize(P, st, time_s=30.0, workers=2, seed=0)
    from kae.place.problem import geom_to_lib
    logo = next(p for p in P.parts if p.ref == "R1")
    # the aperture 3.6 mm from R1 towards the board's middle (clear of its pads, on the board
    # wherever the legalizer put R1: CP-SAT's layout varies with the host's load)
    cx, cy = st.xy(logo.i)
    dy = 3.6 if cy < P.outline.centroid.y else -3.6
    ap_board = box(cx - 0.6, cy + dy - 0.6, cx + 0.6, cy + dy + 0.6)
    logo.fp.graphics = dict(logo.fp.graphics or {}, **{"F.Mask": [geom_to_lib(ap_board, *st.pose(logo.i))]})
    others = [z for z in P.board.zones if z.net != "GND"]

    def zones(vcc_outline):
        P.board.zones = others + [
            Zone(uuid="zg", name="", net="GND", layers=["F.Cu", "B.Cu"], outline=P.outline, priority=0, clearance=0.2),
            Zone(uuid="zv", name="", net="VCC", layers=["F.Cu", "B.Cu"], outline=vcc_outline, priority=1,
                 clearance=0.2)]

    def bridges():
        E = exact.ExactModel(P, st)
        return [v for v in E.part_findings(logo.i) if v["type"] == "solder_mask_bridge"
                and "aperture exposes" in v["detail"]]
    zones(box(0, 0, 1, 1))
    E = exact.ExactModel(P, st)
    A = E.sh[logo.i]
    ap = A["gfx"]["mask"][A["side"]][0]
    assert not any(ap.intersects(g) for g, _, _ in A["pads"])
    ymid = (ap.bounds[1] + ap.bounds[3]) / 2
    zones(box(0, 0, 60, ymid))                         # the VCC fill's edge across the aperture
    found = bridges()
    assert found and "GND" in found[0]["detail"] and "VCC" in found[0]["detail"]
    zones(box(0, 0, 60, 40))                           # all VCC under it: one net
    assert not bridges()
    zones(box(0, 0, 60, ymid))
    g0 = A["pads"][0][0]                               # over its own pad: the pad's opening
    x, y, rot, side = st.pose(logo.i)
    logo.fp.graphics["F.Mask"] = [geom_to_lib(g0, x, y, rot, side).buffer(0.6)]
    E = exact.ExactModel(P, st)
    A = E.sh[logo.i]
    ap = A["gfx"]["mask"][A["side"]][0]
    assert ap.intersects(g0)
    zones(box(0, 0, 60, (ap.bounds[1] + ap.bounds[3]) / 2))
    assert not bridges()


def test_silk_conflicts_are_soft_and_the_silk_pass_clears_them():
    """Silkscreen where the project makes it an error (KiCad's default is a warning): silk over
    another part's silk is silk_overlap, over its pad mask openings silk_over_copper. Not
    legality: the final pass moves the smaller part to the nearest clean spot without one."""
    from shapely.geometry import box
    from kae.place import exact
    P, st = _pile()
    legalize(P, st, time_s=30.0, workers=2, seed=0)
    assert not exact.silk_on(P)
    E = exact.ExactModel(P, st)
    assert E.silk_check() == []
    P.severity = dict(P.severity or {}, silk_overlap="error", silk_over_copper="error")
    for p in P.parts:          # only the silk this test draws (the fixture's own texts would
        p.fp.silk, p.fp.silk_text = {}, {}    # meet wherever CP-SAT happened to put them)
    a = next(p for p in P.parts if p.ref == "U1")
    b = min((p for p in P.parts if p.movable and p.s == a.s and p.i != a.i), key=lambda p: p.area)
    # a wide silk bar under R1 reaching U1's position, and U1's own silk where it stands
    ax, ay = st.xy(a.i)
    bx, by = st.xy(b.i)
    from kae.place.problem import geom_to_lib
    bar = box(min(ax, bx) - 0.5, min(ay, by) - 0.5, max(ax, bx) + 0.5, max(ay, by) + 0.5)
    b.fp.silk = {"F.SilkS" if b.s > 0 else "B.SilkS": [geom_to_lib(bar, *st.pose(b.i))]}
    a.fp.silk = {"F.SilkS" if a.s > 0 else "B.SilkS": [geom_to_lib(box(ax - 0.3, ay - 0.3, ax + 0.3, ay + 0.3), *st.pose(a.i))]}
    E = exact.ExactModel(P, st)
    found = E.silk_check()
    assert a.s == b.s and any(v["type"] == "silk_overlap" and set(v["parts"]) == {a.i, b.i} for v in found)
    assert not exact_check(P, st)                 # soft: legality is untouched
    rep = exact.fix_silk(P, st, time_s=30.0, max_wl_rise=10.0)
    assert rep["start"]["silk_overlap"] >= 1 and rep["end"]["silk_overlap"] < rep["start"]["silk_overlap"]
    assert rep["moved"] and rep["moved"][0] == min((a, b), key=lambda p: p.area).ref
    assert not exact_check(P, st) and not grid_violations(st)


def test_silk_texts_take_kicads_glyphs_inside_their_boxes():
    """refine_silk_text: pcbnew's glyph outlines replace the estimated text boxes, in each
    footprint's library frame (placed back where they were, they sit inside the box)."""
    import pytest
    from kae.board import pcbnew_io
    from kae.place import exact
    if not pcbnew_io.available():
        pytest.skip("no Python with pcbnew")
    P = Problem.build(load(FIXTURE))
    boxes = {p.i: [g for v in p.fp.silk_text.values() for g in v] for p in P.parts}
    rep = exact.refine_silk_text(P)
    assert rep["ok"] and rep["texts"] >= 1
    n = 0
    for p in P.parts:
        glyphs = [g for v in p.fp.silk_text.values() for g in v]
        if not glyphs or not boxes[p.i]:
            continue
        n += 1
        box_u = shapely.union_all(boxes[p.i]).buffer(0.3)
        assert sum(g.area for g in glyphs) < sum(b.area for b in boxes[p.i])
        assert all(box_u.contains(g) for g in glyphs), p.ref
    assert n >= 1


def test_silk_term_prices_alike_in_both_annealers_and_pulls_silk_apart():
    """The annealer's silkscreen term (silk_on projects): overlap area of a part's silk with
    the other parts' silk and pad mask openings (exact.silk_grid), priced the same by the
    compiled engine and anneal.Annealer; annealing lowers it."""
    from shapely.geometry import box
    from kae.place import exact
    from kae.place.anneal import Annealer, make_annealer
    P, st = _pile()
    legalize(P, st, time_s=30.0, workers=2, seed=0)
    for p in P.parts:                              # a wide silk bar on every part
        p.fp.silk = {"F.SilkS": [box(-4.0, -0.3, 4.0, 0.3)]}
    sg = exact.silk_grid(P)
    assert sg and all(len(v[1]) == len(P.parts[i].rots) for i, v in sg.items())
    ref = Annealer(P, st.copy(), terms=None, w_cong=0.0, silk=sg, w_silk=1.0, seed=0)
    fast = make_annealer(P, st.copy(), terms=None, w_cong=0.0, silk=sg, w_silk=1.0, seed=0)
    assert abs(fast.cost(fast.lam1) - ref.cost(ref.lam1)) < 1e-6
    s0 = ref.silk_total()
    fast.run(cpu_s=20.0, max_moves=30000)
    assert fast.terms_report()["silk"] * fast.A0 < s0 or s0 == 0


def test_kicad_loop_runs_a_crashed_drc_again(monkeypatch):
    """kicad-cli killed by a signal (buspirate5: 'DRC failed (rc=-11)') runs again on a fresh
    staged copy; an ordinary failure does not, and leaves the board unverified."""
    import time
    from types import SimpleNamespace
    from kae import cli
    from kae.place import exact
    from kae.place.pipeline import Result
    from kae.route import drc as kdrc
    P, st = _pile()
    legalize(P, st, time_s=30.0, workers=2, seed=0)
    monkeypatch.setattr(kdrc, "kicad_cli", lambda: "kicad-cli")
    monkeypatch.setattr(kdrc, "stage_board", lambda out, inp, tmp: str(Path(tmp) / "board.kicad_pcb"))
    monkeypatch.setattr(exact, "kicad_feedback", lambda P, st, rep: dict(errors=0, by_type={}, fixed_only=0))
    a = SimpleNamespace(drc="on", drc_rounds=2, time=600.0, output="o", input="i", writer="sexpr")
    for verdicts, clean_expected, crashes in (([-11, "ok"], True, 1), (["boom"], None, 0)):
        it = iter(verdicts)

        def run(staged, path, timeout):
            v = next(it)
            if v == -11:
                raise kdrc.DrcError("DRC failed (rc=-11): Segmentation fault")
            if v == "boom":
                raise kdrc.DrcError("DRC failed (rc=2): bad board")
            return {}
        monkeypatch.setattr(kdrc, "run", run)
        res = Result(poses=st.poses(), report={}, state=st, problem=P)
        clean, _ = cli._kicad_loop(a, res, time.monotonic(), lambda *x, **k: dict(writer="fake"))
        assert clean is clean_expected
        assert res.report["kicad_verified"] is (clean_expected is not None)
        assert res.report["kicad_drc"][0].get("crashes", 0) == crashes
