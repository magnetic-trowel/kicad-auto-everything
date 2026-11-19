# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The BLAS thread count of the running process, for results that must not depend on the machine.

A threaded OpenBLAS splits a product or a triangular solve into blocks by its thread count, and the blocks'
partial sums meet in another order: SuperLU's solves (its supernodes call BLAS) differed in the last bits at 1
and 4 threads, and the COCG iterations of the field solve grew that to 1e-9 of the result after ~100 steps. The
evaluator's parallel work is its FFTs and compiled kernels (KAE_EM_THREADS), whose sums do not depend on the
thread count, so BLAS runs on one thread (kae.em.solve; KAE_EM_BLAS_THREADS overrides).

Only libraries already loaded are set (numpy's and scipy's OpenBLAS are, once scipy.sparse.linalg is imported).
"""
from __future__ import annotations

import ctypes
import os

_SETTERS = ("openblas_set_num_threads", "scipy_openblas_set_num_threads", "scipy_openblas_set_num_threads64_",
            "openblas_set_num_threads64_", "MKL_Set_Num_Threads")


def _loaded():
    """Paths of the BLAS libraries mapped into this process (Linux /proc/self/maps; elsewhere none)."""
    try:
        with open("/proc/self/maps") as fh:
            paths = {ln.split()[-1] for ln in fh if "/" in ln}
    except OSError:
        return []
    return sorted(p for p in paths if any(k in os.path.basename(p).lower() for k in ("openblas", "libmkl_rt")))


def set_threads(n):
    """Set every loaded OpenBLAS (and MKL) to n threads. Returns the libraries set. Without /proc, threadpoolctl
    is used when installed; otherwise nothing changes and [] is returned."""
    done = []
    for path in _loaded():
        try:
            lib = ctypes.CDLL(path)
        except OSError:
            continue
        for name in _SETTERS:
            fn = getattr(lib, name, None)
            if fn is not None:
                fn(ctypes.c_int(int(n)))
                done.append(path)
                break
    if not done:
        try:
            import threadpoolctl
            threadpoolctl.threadpool_limits(int(n), "blas")
            done.append("threadpoolctl")
        except ImportError:
            pass
    return done
