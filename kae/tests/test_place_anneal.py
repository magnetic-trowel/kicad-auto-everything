# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""kae.place.anneal and kae.place.cost: incremental terms stay exact; annealing helps."""
from pathlib import Path

import numpy as np

from kae.board.kicad_file import load
from kae.place.anneal import Annealer
from kae.place.legalize import legalize
from kae.place.problem import Problem
from kae.place.state import State, grid_violations
from kae.place.stubs import StubTerms, stub_brief

FIXTURE = Path(__file__).parent / "data" / "board" / "fixture.kicad_pcb"


def _legal_state(seed=0):
    b = load(FIXTURE)
    P = Problem.build(b)
    st = State(P)
    rng = np.random.default_rng(seed)
    for i in P.mov:
        st.X[i] = rng.integers(P.ncx // 4, 3 * P.ncx // 4)
        st.Y[i] = rng.integers(P.ncy // 4, 3 * P.ncy // 4)
    legalize(P, st, time_s=30.0, workers=2, seed=seed)
    assert not grid_violations(st)
    return b, P, st


def test_incremental_terms_match_a_fresh_evaluation():
    b, P, st = _legal_state()
    terms = StubTerms(b, stub_brief(b))
    ann = Annealer(P, st.copy(), terms=terms, seed=4)
    ann.run(cpu_s=20.0, max_moves=4000)
    ann.write_back()
    fresh = Annealer(P, ann.st.copy(), terms=terms, seed=0)
    assert abs(fresh.wl - ann.wl) < 1e-6 * max(1.0, fresh.wl)
    assert fresh.leg_total == ann.leg_total == ann.total_leg()
    for name in ("Dn", "Dp", "Bk"):            # RUDY, pin escape and pad blockage stay exact
        assert np.allclose(getattr(fresh.cong, name), getattr(ann.cong, name), atol=1e-9), name
    assert abs(fresh.phys - ann.phys) < 1e-6 * max(1.0, abs(fresh.phys))
    # the rectangles in the spatial hash are where the parts are
    for i in P.mov:
        rects = [r for _, r, _ in ann.st.grid_rects(i)]
        assert [ann.r_box[rid] for rid in ann.part_rects[i]] == rects


def test_annealing_lowers_wirelength_from_a_legal_start():
    b, P, st = _legal_state(seed=2)
    ann = Annealer(P, st.copy(), terms=None, seed=1, w_cong=0.0)
    w0 = ann.wl
    ann.run(cpu_s=20.0, max_moves=6000)
    assert ann.wl < w0


def test_seeded_runs_repeat():
    b, P, st = _legal_state(seed=3)
    out = []
    for _ in range(2):
        ann = Annealer(P, st.copy(), terms=None, seed=7)
        ann.run(cpu_s=60.0, max_moves=2000)
        out.append((list(ann.X), list(ann.Y), list(ann.K)))
    assert out[0] == out[1]
