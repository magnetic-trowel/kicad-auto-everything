# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Hot kernels of the place terms, written once and run either interpreted or JIT-compiled.

The kernels live in `_kernels.py` as module-level functions. This module loads that file
twice: `PY` executes it as plain Python (the fallback); `nb()` executes it with every kernel
wrapped in numba.njit(cache=True) (`kae[fast]`), on first use only, never at import. Both
run the same code, so they agree to rounding (kae/tests/test_place_terms_jit.py checks
1e-12 relative). numba compiles a kernel on its first call and caches the machine code
next to the source, so later processes load it instead of compiling. Set KAE_NO_NUMBA=1
to force the fallback. `warm()` compiles (or loads) everything at once and
`compile_seconds()` reports what that cost.

Kernels (units mm, nH):
  loop_core         loop inductance of a chain of terminals over the reference plane
                    (partial inductances with images; Hammerstad-Jensen strip self terms;
                    plane height per hop; expected detours; ground hop in parallel with a
                    via return through a ground plane)
  loop_mutual_core  |M| between an aggressor and a victim loop over the plane: dipoles of
                    each loop and its image far apart, segment-pair Neumann integrals near
  patches_cm_core   first-order mutual capacitance between two sets of copper patches
  eng_eval          any selection of coupling sub-terms (inductive, capacitive) from the
                    pose arrays in one call (structures.CouplingEngine)
  k0, fin_sum, fin_col_xy, fin_row_xy
                    board fin temperature kernel K0(r/lam) with adiabatic-edge images
  phi_sum, mst_len  thermal cost over the targets; antenna feed spanning tree
"""
from __future__ import annotations

import importlib.util
import math
import os
import sys
import time

import numpy as np

_SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), '_kernels.py')


def _load(name, jit):
    """Execute _kernels.py as module `name` with decorator `jit`."""
    mod = sys.modules.get(name)
    if mod is not None:
        return mod
    spec = importlib.util.spec_from_file_location(name, _SRC)
    mod = importlib.util.module_from_spec(spec)
    mod._JIT = jit
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _gauss(n):
    x, w = np.polynomial.legendre.leggauss(n)
    return 0.5 * (x + 1.0), 0.5 * w


GAUSS = (*_gauss(3), *_gauss(6))
PY = _load('kae.physics._kernels_py', lambda f: f)
_NB = None
_COMPILE_S = 0.0


def enabled():
    if os.environ.get('KAE_NO_NUMBA'):
        return False
    try:
        import numba  # noqa: F401
    except ImportError:
        return False
    return True


def nb():
    """The numba kernels (module loaded on first use; each kernel compiles, or loads from the
    on-disk cache, on its first call)."""
    global _NB
    if _NB is None:
        import numba
        _NB = _load('kae.physics._kernels_nb', numba.njit(cache=True))
    return _NB


def compile_seconds():
    return _COMPILE_S


def warm(nbk):
    """Compile the numba kernels on representative arguments; returns seconds spent."""
    global _COMPILE_S
    t0 = time.perf_counter()
    f = np.zeros(4)
    ii = np.zeros(4, np.int64)
    bb = np.zeros(4, np.bool_)
    H = np.zeros((2, 2))
    N = np.zeros((2, 2), np.int32)
    g = np.zeros(1, np.bool_)
    nbk.loop_core(f, f, f + 1, f, f + 1, ii, f, f, bb, f + 0.2, f, f, 4, -1, 0.3, 0.15, 1.0, 1.6, 0.15,
                  H, H, N, N, g, 0.0, 0.0, 1.0, np.zeros(8), np.zeros(8), np.zeros(8), np.zeros(8))
    nbk.patches_cm_core(f, f, f + 1, f + 1, f, f + 1, 0.2, 4.3, 8.85e-3)
    Q = np.array([[0.0, 0.0], [1.0, 0.0], [1.0, 1.0]])
    sc = [np.zeros((64, 3)) for _ in range(4)]
    for ca in (True, False):
        for hh in (0.2, math.inf):
            nbk.loop_mutual_core(Q, ca, 0.2, Q + 0.5, ca, 0.2, hh, *GAUSS, *sc)
    nbk.fin_sum(0.0, 0.0, f + 1, f + 1, 0.5, 40.0)
    ms = np.arange(-1.0, 2.0)
    box = np.array([0.0, 0.0, 50.0, 30.0])
    nbk.fin_col_xy(f, f, ii[:2], 1.0, 1.0, box, ms, 0.5, 40.0, np.zeros(2))
    nbk.fin_row_xy(f, f, ii[:2], 1.0, 1.0, box, ms, f[:2] + 0.5, 40.0, np.zeros(2))
    nbk.phi_sum(f, 0.1, f + 1.0, f + 1.0, 4.0, 10.0)
    nbk.mst_len(f, f, f + 1, f, f + 1, ii, f, f, np.zeros(4), np.zeros(4), np.zeros(4), bb)
    # the coupling engine on two two-terminal loops and nodes
    i2 = np.array([0, 1, 1, 0], np.int64)
    xy = np.array([[0.0, 0.0], [1.0, 0.0], [0.0, 0.0], [1.0, 0.0]])
    xya = np.array([[0.0, 0.0, 0.5], [1.0, 0.0, 0.5], [0.0, 0.0, 0.5], [1.0, 0.0, 0.5]])
    X, Y = np.array([0.0, 5.0]), np.array([0.0, 3.0])
    C1, S0, G1 = np.ones(2), np.zeros(2), np.ones(2)
    nbk.eng_eval(X, Y, C1, S0, G1, i2, xy, np.array([[0, 2], [2, 2]], np.int64), np.array([[1.0, 0.0], [0.0, 0.0]]),
                 i2, xya, np.array([[0, 2, 0, 3], [2, 2, 3, 3]], np.int64), np.array([0.2, 0.2]), H + 0.2, H + 0.2,
                 0.0, 0.0, 1.0, 4.3, np.array([[0, 1, 0]], np.int64), np.ones(1), np.array([[0, 1, 1]], np.int64),
                 np.ones((1, 2)), np.zeros(1, np.int64), np.zeros(1, np.int64), 15.0, 30.0, np.zeros((4, 2)),
                 np.zeros((2, 3)), -np.ones(2, np.int64), np.zeros(6), np.zeros(6), np.zeros(6), np.zeros(6),
                 np.zeros((2, 4)), -np.ones(2, np.int64), 1, *GAUSS, *sc, np.zeros(1), np.zeros(1))
    _COMPILE_S += time.perf_counter() - t0
    return _COMPILE_S
