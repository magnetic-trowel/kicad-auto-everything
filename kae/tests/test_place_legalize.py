# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""kae.place.legalize: windowed CP-SAT repair and the exact polygon check."""
from pathlib import Path

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
