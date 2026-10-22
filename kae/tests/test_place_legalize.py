# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""kae.place.legalize: windowed CP-SAT repair and the exact polygon check."""
from pathlib import Path

from kae.board.kicad_file import load
from kae.place.legalize import exact_check, legalize
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
