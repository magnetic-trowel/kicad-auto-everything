# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The numba kernels and the pure-Python fallback run the same source and must agree to
1e-12 relative (kae.physics.jit); skipped when numba is not installed."""
import math

import numpy as np
import pytest

from kae.physics import jit

numba = pytest.importorskip('numba')


def _loop_args(rng, n):
    X = rng.uniform(-10, 10, 3)
    Y = rng.uniform(-10, 10, 3)
    a = rng.uniform(0, 2 * math.pi, 3)
    C, S = np.cos(a), np.sin(a)
    G = rng.choice([-1.0, 1.0], 3)
    ti = rng.integers(0, 3, n).astype(np.int64)
    tlx = rng.uniform(-3, 3, n)
    tly = rng.uniform(-3, 3, n)
    isbody = np.array([ti[k] == ti[(k + 1) % n] for k in range(n)])
    w = rng.uniform(0.15, 2.0, n)
    zb = np.where(isbody, rng.uniform(0.1, 1.0, n), 0.0)
    bodyd = np.where(isbody, rng.uniform(0.0, 3.0, n), 0.0)
    H = np.full((41, 41), rng.choice([0.1, 0.2, 0.8, math.inf]))
    Hb = np.full((41, 41), rng.choice([0.1, 1.4, math.inf]))
    N = np.zeros((41, 41), np.int32)
    gmask = np.array([bool(rng.integers(0, 2))])
    gnd = int(rng.integers(-1, n))
    detour = float(rng.choice([0.0, 0.125]))
    return (X, Y, C, S, G, ti, tlx, tly, isbody, w, zb, bodyd, n, gnd, 0.3, 0.15, detour, 1.6, 0.15, H, Hb, N, N,
            gmask, -20.0, -20.0, 1.0)


def test_loop_core_numba_matches_python():
    nb = jit.nb()
    rng = np.random.default_rng(11)
    for _ in range(300):
        n = int(rng.integers(3, 8))
        args = _loop_args(rng, n)
        a = jit.PY.loop_core(*args, *(np.zeros(n) for _ in range(4)))
        b = nb.loop_core(*args, *(np.zeros(n) for _ in range(4)))
        assert math.isfinite(a) and a >= 0.0
        assert b == pytest.approx(a, rel=1e-12, abs=1e-12)


def test_loop_mutual_and_patches_numba_match_python():
    nb = jit.nb()
    rng = np.random.default_rng(5)
    for _ in range(200):
        PA = rng.uniform(-5, 5, (int(rng.integers(2, 6)), 2))
        PV = rng.uniform(-5, 5, (int(rng.integers(2, 6)), 2)) + rng.uniform(-20, 20, 2)
        ca, cv = bool(rng.integers(0, 2)), bool(rng.integers(0, 2))
        h = float(rng.choice([0.1, 0.4, math.inf]))
        sc = [np.zeros((512, 3)) for _ in range(4)]
        a = jit.PY.loop_mutual_core(PA, ca, 0.2, PV, cv, 0.3, h, *jit.GAUSS, *sc)
        sc = [np.zeros((512, 3)) for _ in range(4)]
        b = nb.loop_mutual_core(PA, ca, 0.2, PV, cv, 0.3, h, *jit.GAUSS, *sc)
        assert b == pytest.approx(a, rel=1e-12, abs=1e-15)
        XA, YA, AA = rng.uniform(-3, 3, 4), rng.uniform(-3, 3, 4), rng.uniform(0.1, 2, 4)
        XV, YV, AV = rng.uniform(2, 9, 3), rng.uniform(-3, 3, 3), rng.uniform(0.1, 2, 3)
        a = jit.PY.patches_cm_core(XA, YA, AA, XV, YV, AV, 0.2, 4.3, 8.854e-3)
        b = nb.patches_cm_core(XA, YA, AA, XV, YV, AV, 0.2, 4.3, 8.854e-3)
        assert b == pytest.approx(a, rel=1e-12)


def test_fin_kernels_numba_match_python():
    nb = jit.nb()
    rng = np.random.default_rng(2)
    IX, IY = rng.uniform(0, 100, 36), rng.uniform(0, 60, 36)
    for _ in range(50):
        tx, ty = float(rng.uniform(0, 100)), float(rng.uniform(0, 60))
        a = jit.PY.fin_sum(tx, ty, IX, IY, 1.5, 40.0)
        b = nb.fin_sum(tx, ty, IX, IY, 1.5, 40.0)
        assert b == pytest.approx(a, rel=1e-12)


def test_warm_reports_compile_seconds():
    s = jit.warm(jit.nb())
    assert s >= 0.0 and jit.compile_seconds() >= s - 1e-9
