# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Skin and proximity crowding through a copper layer's thickness, and the surface-impedance correction of a
raster whose bars carry only `nsub` filaments through it (kae.em.mesh.Layer).

A slab of thickness t whose magnetic field lies on one side (a trace over its plane, the plane under its trace)
has the exact resistance ratio

    F(D) = R / R_dc = Re[ (1 + j) D coth((1 + j) D) ],   D = t / delta,  delta = sqrt(2 / (w mu0 sigma))

(the surface impedance Z_s = (1 + j) / (sigma delta) of a finite slab; Dowell's single-layer factor). The same
slab cut into n uniform-current filaments (kae.em.mesh's Chebyshev slices) reaches only F_n(D) < F(D) once
delta is thinner than its outer slices: F_2 is 0.60 F at 100 MHz and 0.43 F at 200 MHz in 35 um copper
(tools/research/physics/em_skin_nsub_check.py).

The correction scales a layer's copper resistance by k_n(f) = F / F_n. It assumes one-sided crowding, which is
what a conductor facing its return across a dielectric has; on two-sided crowding (go and return side by side
with no plane, a stripline between two planes) it under-corrects. Measured against nsub = 8 solves of a decap
loop, a buck hot loop and a plane pair: docs/research/physics/field-solver-accuracy.md.
"""
from __future__ import annotations

import math
from functools import lru_cache

import numpy as np

from .mesh import SIGMA_CU

MU0 = 4e-7 * math.pi


def delta(f, sigma=SIGMA_CU):
    """Skin depth (m) at f (Hz)."""
    return math.sqrt(2.0 / (2 * math.pi * f * MU0 * sigma))


def slab(f, t, sigma=SIGMA_CU):
    """F(D): R / R_dc of a slab t (m) thick with its field on one side."""
    if f <= 0:
        return 1.0
    D = t / delta(f, sigma)
    if D > 30:                                    # coth -> 1
        return D
    g = (1 + 1j) * D
    return float((g / np.tanh(g)).real)


@lru_cache(maxsize=4096)
def slab_filaments(f, t, n, sigma=SIGMA_CU, fine=2000):
    """F_n(D): the same slab as n uniform-current filaments at kae.em.mesh's Chebyshev slices, each one's partial
    flux the mean, over its own slice, of the flux between the field-side face and z."""
    if f <= 0 or n < 1:
        return 1.0
    e = (1 - np.cos(np.pi * np.arange(n + 1) / n)) / 2 * t
    z = (np.arange(fine) + 0.5) / fine * t
    dz = t / fine
    H = np.zeros((n, fine))
    for m in range(n):
        a, b = e[m], e[m + 1]
        H[m] = np.where(z < a, 1.0, np.where(z > b, 0.0, (b - z) / (b - a)))
    Phi = MU0 * (np.cumsum(H, 1) - H / 2) * dz
    L = np.zeros((n, n))
    for k in range(n):
        sel = (z >= e[k]) & (z < e[k + 1])
        L[k] = Phi[:, sel].mean(1)
    L = (L + L.T) / 2
    Rk = 1 / (sigma * np.diff(e))
    y = np.linalg.solve(np.diag(Rk) + 2j * math.pi * f * L, np.ones(n))
    K = y / y.sum()
    return float(np.sum(Rk * np.abs(K) ** 2) * sigma * t)


def correction(f, t, n, sigma=SIGMA_CU):
    """k_n(f) = F / F_n >= 1: the factor on an n-filament layer's copper resistance at f."""
    if f <= 0:
        return 1.0
    return max(1.0, slab(f, t, sigma) / slab_filaments(round(float(f), 3), float(t), int(n), sigma))
