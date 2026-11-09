# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""kae.place.crossings: the ratsnest crossing count and the untangle pass."""
from pathlib import Path
from types import SimpleNamespace as NS

import numpy as np

from kae.board.kicad_file import load
from kae.place import crossings as C
from kae.place.legalize import legalize
from kae.place.problem import Problem
from kae.place.state import State, grid_violations

FIXTURE = Path(__file__).parent / "data" / "board" / "fixture.kicad_pcb"


def _scene(nx, ny, kinds=None):
    nets = [NS(i=i, kind=(kinds or {}).get(i, "signal"), pins=list(zip(range(len(x)), [0] * len(x))))
            for i, x in enumerate(nx)]
    P = NS(nets=nets, outline=NS(bounds=(0.0, 0.0, 30.0, 30.0)))
    view = NS(nx=nx, ny=ny, frozen=set())
    return P, view


def test_counts_a_crossed_pair_and_not_a_parallel_one():
    P, view = _scene([[0.0, 10.0], [0.0, 10.0]], [[0.0, 10.0], [10.0, 0.0]])
    assert C.Crossings(P, view).total == 1
    P, view = _scene([[0.0, 10.0], [0.0, 10.0]], [[0.0, 0.0], [5.0, 5.0]])
    assert C.Crossings(P, view).total == 0


def test_power_and_big_nets_are_left_out():
    P, view = _scene([[0.0, 10.0], [0.0, 10.0]], [[0.0, 10.0], [10.0, 0.0]], kinds={1: "power"})
    assert C.Crossings(P, view).total == 0
    xs = [float(k) for k in range(C.MAX_PINS + 1)]
    P, view = _scene([[0.0, 10.0], xs], [[0.0, 10.0], [10.0 - x for x in xs]])
    assert C.Crossings(P, view).total == 0


def test_trial_matches_a_full_recount():
    rng = np.random.default_rng(3)
    nx = [list(map(float, rng.uniform(0, 30, rng.integers(2, 7)))) for _ in range(40)]
    ny = [list(map(float, rng.uniform(0, 30, len(x)))) for x in nx]
    P, view = _scene(nx, ny)
    xc = C.Crossings(P, view)
    for _ in range(200):
        touched = list(map(int, rng.choice(40, size=int(rng.integers(1, 4)), replace=False)))
        saved = [(view.nx[j][:], view.ny[j][:]) for j in touched]
        for j in touched:
            view.nx[j] = list(map(float, rng.uniform(0, 30, len(view.nx[j]))))
            view.ny[j] = list(map(float, rng.uniform(0, 30, len(view.ny[j]))))
        d = xc.trial(touched)
        if rng.random() < 0.5:
            before = xc.total
            xc.commit()
            assert xc.total == before + d
            assert xc.total == C.Crossings(P, view).total
        else:
            xc.revert()
            for j, (x, y) in zip(touched, saved):
                view.nx[j], view.ny[j] = x, y


def _legal(seed=0):
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


def test_untangle_keeps_legality_and_never_adds_crossings():
    _, P, st = _legal()
    rep = C.untangle(P, st, x_mm=1e9, time_s=20.0)
    assert not grid_violations(st)
    assert rep["after"] <= rep["crossings"]
    v = C._Pins(P, st)
    v.frozen = {n.i for n in P.nets if n.kind in ("ground", "power") and len(n.pins) > 40}
    assert C.Crossings(P, v).total == rep["after"]


def test_untangle_holds_parts_and_respects_physics():
    _, P, st = _legal(1)
    all_held = set(P.mov)
    x0, y0, k0 = st.X.copy(), st.Y.copy(), st.K.copy()
    rep = C.untangle(P, st, hold=all_held, x_mm=1e9, time_s=20.0)
    assert rep["swaps"] == 0 and rep["turns"] == 0
    assert (st.X == x0).all() and (st.Y == y0).all() and (st.K == k0).all()

    class Never:
        """A physics term every move worsens."""

        def parts(self):
            return [p.uuid for p in P.parts]

        def delta(self, poses, moved, new):
            return 1.0

    rep = C.untangle(P, st, terms=Never(), x_mm=1e9, time_s=20.0)
    assert rep["swaps"] == 0 and rep["turns"] == 0
