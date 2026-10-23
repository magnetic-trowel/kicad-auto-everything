# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""kae.place.engine: the compiled annealer keeps its incremental terms exact, prices like the
reference annealer, repeats with its seed, and re-places a subset inside a window."""
from pathlib import Path

import numpy as np
import pytest

from kae.board.kicad_file import load
from kae.place.anneal import Annealer
from kae.place.legalize import legalize
from kae.place.problem import Problem
from kae.place.state import State, grid_violations
from kae.place.stubs import StubTerms, stub_brief

engine = pytest.importorskip("kae.place.engine")
if not engine.HAVE_NUMBA:
    pytest.skip("numba not installed (kae[fast])", allow_module_level=True)

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


def test_engine_totals_stay_exact_and_match_the_reference():
    b, P, st = _legal_state()
    terms = StubTerms(b, stub_brief(b))
    fa = engine.FastAnnealer(P, st.copy(), terms=terms, seed=4)
    ref0 = Annealer(P, st.copy(), terms=terms, seed=4)
    assert abs(fa.cost(fa.lam1) - ref0.cost(ref0.lam1)) < 1e-9       # same cost to start with
    fa.run(cpu_s=60.0, max_moves=20000)
    fa.write_back()
    ref = Annealer(P, fa.st.copy(), terms=terms, seed=0)
    E = fa.E
    live = [j for j in range(len(P.nets)) if j not in ref.frozen]
    assert abs(sum(E.nc[j] for j in live) - sum(ref.ncost[j] for j in live)) < 1e-6
    assert int(E.tot[engine.T_LEG]) == ref.total_leg()
    assert abs(fa.phys - ref.phys) < 1e-6 * max(1.0, abs(ref.phys))
    assert np.allclose(E.Dp, ref.cong.Dp)
    # RUDY demand equals a rebuild from the engine's own net boxes
    Dn = E.Dn.copy()
    E.Dn[:] = 0.0
    wx, wy = np.zeros(E.Dn.shape[0] + 2), np.zeros(E.Dn.shape[1] + 2)
    for j in range(len(P.nets)):
        if E.has_box[j]:
            engine._net_box_apply(E, j, 1.0, *E.net_box[j], E.net_dens[j], wx, wy)
    assert np.allclose(E.Dn, Dn, atol=1e-9)


def test_engine_repeats_with_its_seed():
    b, P, st = _legal_state(seed=2)
    out = []
    for _ in range(2):
        fa = engine.FastAnnealer(P, st.copy(), terms=None, seed=7, w_phys=0.0)
        fa.run(cpu_s=60.0, max_moves=5000)
        out.append((fa.X.tolist(), fa.Y.tolist(), fa.K.tolist()))
    assert out[0] == out[1]


@pytest.mark.parametrize("cls", ["engine", "reference"])
def test_subset_moves_inside_its_window_only(cls):
    b, P, st = _legal_state(seed=3)
    sub = list(P.mov)[:4]
    xs = [st.X[i] for i in sub]
    ys = [st.Y[i] for i in sub]
    pad = 40
    window = (int(min(xs)) - pad, int(max(xs)) + pad, int(min(ys)) - pad, int(max(ys)) + pad)
    kw = dict(terms=None, seed=1, w_phys=0.0, subset=sub, window=window)
    ann = engine.FastAnnealer(P, st.copy(), **kw) if cls == "engine" else Annealer(P, st.copy(), **kw)
    ann.run(cpu_s=60.0, max_moves=4000)
    ann.write_back()
    moved = [i for i in P.mov if (ann.st.X[i], ann.st.Y[i], ann.st.K[i]) != (st.X[i], st.Y[i], st.K[i])]
    assert moved and set(moved) <= set(sub)
    for i in sub:
        for side, (a, bb, c, d), kind in ann.st.grid_rects(i):
            if kind == "own":
                assert window[0] <= a and bb <= window[1] and window[2] <= c and d <= window[3]


@pytest.mark.parametrize("cls", ["engine", "reference"])
def test_a_run_cut_short_by_its_budget_still_ends_cold(cls):
    """Regression (koron, bms-c1 at v7c): a run whose budget ran out at half its planned moves
    stopped hot and returned a near-random state; the schedule now cools on time as well."""
    b, P, st = _legal_state(seed=5)
    kw = dict(terms=None, seed=2, w_phys=0.0)
    ann = engine.FastAnnealer(P, st.copy(), **kw) if cls == "engine" else Annealer(P, st.copy(), **kw)
    ann.run(cpu_s=1.0, max_moves=10 ** 9)
    assert ann.T_last <= ann.T0 * 1e-3
