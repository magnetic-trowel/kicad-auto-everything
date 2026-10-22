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
