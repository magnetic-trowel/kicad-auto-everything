# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Electrostatics of the raster: the capacitance matrix of the nets in a window, in the board's
layered dielectric (air above and below, the stackup's dielectrics between copper layers).

Each copper cell is a thin charge panel at its layer's mid-plane. Potentials are P q with the
layered medium's static Green's function G(rho; z, z'), which is laterally shift-invariant, so P
is block-Toeplitz per layer pair and P q costs FFTs, as for the inductance. G is computed in the
spectral domain (Hankel transform of the 1-D layered problem for each k) with the source layer's
singular term 1/(4 pi eps_s r) taken out analytically and integrated exactly over each panel.
A charge on an interface uses the mean permittivity of its two sides for that singular term.

C[i, j] = charge on net i with net j at 1 V and every other net at 0 V (Maxwell's matrix:
positive diagonal, negative off-diagonal; the mutual capacitance is -C[i, j]).
"""
from __future__ import annotations

import numpy as np
import scipy.fft as sfft
from scipy.special import j0

from .mesh import MM

EPS0 = 8.8541878128e-12
WORKERS = 8


def _panel_inv_r(a, b, x, y):
    """Integral over the rectangle [-a/2, a/2] x [-b/2, b/2] of 1 / sqrt((x - u)^2 + (y - v)^2), in its
    own plane (z = 0): the closed form of Durand."""
    def F(u, v):
        r = np.sqrt(u * u + v * v)
        with np.errstate(divide="ignore", invalid="ignore"):
            t1 = np.where(r + v > 0, u * np.log(np.where(r + v > 0, r + v, 1.0)), 0.0)
            t2 = np.where(r + u > 0, v * np.log(np.where(r + u > 0, r + u, 1.0)), 0.0)
        return t1 + t2
    out = 0
    for su, uu in ((1, x + a / 2), (-1, x - a / 2)):
        for sv, vv in ((1, y + b / 2), (-1, y - b / 2)):
            out = out + su * sv * F(uu, vv)
    return out


def _panel_inv_r3d(p, x, y, dz, n=4):
    """Integral of 1/r over a p x p panel seen from (x, y, dz): Gauss quadrature (dz != 0, smooth)."""
    g, w = np.polynomial.legendre.leggauss(n)
    u = g * p / 2
    wu = w * p / 2
    out = 0
    for ui, wi in zip(u, wu):
        for vj, wj in zip(u, wu):
            out = out + wi * wj / np.sqrt((x - ui) ** 2 + (y - vj) ** 2 + dz * dz)
    return out


class Stack:
    """Layered dielectric: interfaces z_b (m, increasing) with eps_r of each slab between them;
    air (eps_r 1) below the first and above the last."""

    def __init__(self, z_if, eps):
        self.z = np.asarray(z_if, float)
        self.eps = np.asarray(eps, float)            # len(z) - 1 slabs

    def eps_at(self, z):
        if z < self.z[0] or z > self.z[-1]:
            return 1.0
        k = np.searchsorted(self.z, z, side="right") - 1
        k = min(max(k, 0), len(self.eps) - 1)
        e = self.eps[k]
        for zi, side in ((self.z[k], -1), (self.z[min(k + 1, len(self.z) - 1)], 1)):
            if abs(z - zi) < 1e-12:                   # on an interface: the mean of its sides
                k2 = k + side
                e2 = 1.0 if k2 < 0 or k2 >= len(self.eps) else self.eps[k2]
                return (e + e2) / 2
        return e

    def spectral(self, k, z, zs):
        """phi~(k; z, zs): potential at height z of a unit point charge at zs, Hankel-transform
        domain (phi = 1/(2 pi) int k J0(k rho) phi~ dk), by solving the 1-D layered problem."""
        zi = self.z
        eps = np.r_[1.0, self.eps, 1.0]
        # regions: 0 = below z0, ..., n = above z_last; split the source region at zs
        bounds = list(zi)
        reg_eps = list(eps)
        # find source region and insert an interface at zs carrying the charge
        r = int(np.searchsorted(bounds, zs, side="right"))
        bounds.insert(r, zs)
        reg_eps.insert(r, reg_eps[r])
        nb = len(bounds)
        nreg = nb + 1
        # unknowns: A_j, B_j per region (phi = A e^{k(z - b)} + B e^{-k(z - b)} with b a local reference)
        ref = [bounds[0]] + [bounds[j - 1] for j in range(1, nreg)]
        M = np.zeros((2 * nreg, 2 * nreg))
        rhs = np.zeros(2 * nreg)
        row = 0
        # bottom region: decays as z -> -inf: B_0 = 0 (with phi = A e^{k(z-b)})
        M[row, 1] = 1
        row += 1
        for j in range(nb):
            zb = bounds[j]
            lo, hi = j, j + 1
            elo, ehi = np.exp(k * (zb - ref[lo])), np.exp(k * (zb - ref[hi]))
            # continuity of phi
            M[row, 2 * lo], M[row, 2 * lo + 1] = elo, 1 / elo
            M[row, 2 * hi], M[row, 2 * hi + 1] = -ehi, -1 / ehi
            row += 1
            # jump of eps dphi/dz = -sigma (unit charge at zs only)
            M[row, 2 * lo], M[row, 2 * lo + 1] = reg_eps[lo] * k * elo, -reg_eps[lo] * k / elo
            M[row, 2 * hi], M[row, 2 * hi + 1] = -reg_eps[hi] * k * ehi, reg_eps[hi] * k / ehi
            if j == r:
                rhs[row] = -1.0 / EPS0
            row += 1
        # top region decays: A_top = 0
        M[row, 2 * (nreg - 1)] = 1
        sol = np.linalg.solve(M, -rhs)
        j = int(np.searchsorted(bounds, z, side="right"))
        e = np.exp(k * (z - ref[j]))
        return sol[2 * j] * e + sol[2 * j + 1] / e


def green_table(stack, z, zs, rho, kmax_h=60.0):
    """G(rho; z, zs) - 1/(4 pi eps0 eps_s r) on the radii rho (m): the layered medium's smooth
    remainder, by a Hankel integral over k (the free part removed in the spectral domain)."""
    es = stack.eps_at(zs)
    dz = abs(z - zs)
    hmin = max(min(np.min(np.abs(stack.z - zs)) if np.min(np.abs(stack.z - zs)) > 1e-12 else 1e-4, 1e-4), 1e-5)
    # free-space term in the spectral domain: e^{-k|dz|} / (2 eps0 eps_s k) (per the 1/(2pi) k J0 transform)
    ks = np.linspace(0, kmax_h / hmin, 6000)[1:]
    ph = np.array([stack.spectral(k, z, zs) for k in ks])
    free = np.exp(-ks * dz) / (2 * EPS0 * es * ks)
    smooth = ph - free
    # trapezoid in k (smooth decays like e^{-2 k h}); add k = 0 limit by extrapolation
    w = np.gradient(ks)
    return np.array([np.sum(w * ks * j0(ks * r) * smooth) / (2 * np.pi) for r in rho])
