# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Electrostatics of the raster: the capacitance of the nets in the board's layered dielectric.

Each copper cell is a uniformly charged panel. Conductors are zero-thickness sheets at the dielectric
interfaces (copper thickness folded out, so two planes' spacing is their dielectric's: parallel
plates and zero-thickness microstrip come out right); air lies above and below the board. Potentials
are P q, with the layered medium's static Green's function G(rho; z, z'), laterally shift-invariant:
P is block-Toeplitz per layer pair and P q costs FFTs, as the inductance does (kae.em.solve).

G is split three ways:
- the source plane's singular term 1/(4 pi eps0 eps_s R) with eps_s the mean permittivity of the
  interface the panel sits on, integrated exactly over the source panel (Durand's closed form in its
  own plane, Gauss quadrature off it);
- the far field: as k -> 0 a finite stack is transparent and G -> 1/(4 pi eps0 rho), so the remainder
  carries (1 - 1/eps_s) / (2 eps0 k) at small k; taken out as e^{-k b} / k, whose transform is the
  closed form (1 - 1/eps_s) / (4 pi eps0 sqrt(rho^2 + b^2));
- the rest, bounded and smooth, by a Hankel integral of the 1-D layered solution, solved per k with
  every exponential referenced so that it is at most 1 (stable at any k).

C[i, j] = charge on net i with net j at 1 V and every other conductor at 0 V (Maxwell's matrix:
positive diagonal, negative off-diagonal; -C[i, j] is the mutual capacitance, and the row sum the
capacitance to the world).
"""
from __future__ import annotations

import math
import os

import numpy as np
import scipy.fft as sfft
from scipy.special import j0

EPS0 = 8.8541878128e-12
MM = 1e-3
WORKERS = int(os.environ.get("KAE_EM_THREADS", "8"))
NEAR = 3                    # offsets (cells) whose smooth remainder is averaged over the source panel


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


def _panel_inv_r3d(p, x, y, dz):
    """Integral of 1/R over a p x p panel seen from (x, y) at height dz: the closed form
    sum of +-[u ln(v + R) + v ln(u + R) - dz atan(u v / (dz R))] over the corners."""
    dz = abs(dz)

    def F(u, v):
        R = np.sqrt(u * u + v * v + dz * dz)
        return u * np.log(v + R) + v * np.log(u + R) - dz * np.arctan2(u * v, dz * R)
    out = 0
    for su, uu in ((1, x + p / 2), (-1, x - p / 2)):
        for sv, vv in ((1, y + p / 2), (-1, y - p / 2)):
            out = out + su * sv * F(uu, vv)
    return out


class Stack:
    """Layered dielectric: interfaces z (m, increasing), eps_r of each slab between them; air (1)
    below the first and above the last. Conductor sheets sit on interfaces."""

    def __init__(self, z_if, eps):
        self.z = np.asarray(z_if, float)
        self.eps = np.asarray(eps, float)
        assert len(self.eps) == len(self.z) - 1

    def eps_of_region(self):
        """Permittivity of each region from below the first interface to above the last."""
        return np.r_[1.0, self.eps, 1.0]

    def eps_at(self, z):
        """Permittivity at z; on an interface, the mean of its two sides."""
        e = self.eps_of_region()
        k = int(np.searchsorted(self.z, z, side="right"))
        on = np.isclose(self.z, z, rtol=0, atol=1e-12)
        if on.any():
            i = int(np.nonzero(on)[0][0])
            return (e[i] + e[i + 1]) / 2
        return e[k]

    def spectral(self, k, z, zs):
        """phi~(k; z, zs) for an array k > 0: the potential at height z of a unit point charge at zs on an
        interface, in the Hankel domain (phi = 1/(2 pi) int k J0(k rho) phi~ dk)."""
        k = np.atleast_1d(np.asarray(k, float))
        b = list(self.z)
        e = list(self.eps_of_region())
        if not np.isclose(b, zs, atol=1e-12).any():
            r = int(np.searchsorted(b, zs))
            b.insert(r, zs)
            e.insert(r + 1, e[r])
        src = int(np.argmin(np.abs(np.asarray(b) - zs)))
        nb, nreg = len(b), len(b) + 1
        # region j spans [b[j-1], b[j]]; phi = A_j e^{k (z - b[j])} + B_j e^{-k (z - b[j-1])}, both <= 1
        # inside; the bottom region keeps only A (decays down), the top only B (decays up)
        nk = len(k)
        M = np.zeros((nk, 2 * nreg, 2 * nreg))
        rhs = np.zeros((nk, 2 * nreg))
        M[:, 0, 1] = 1.0                                 # B_0 = 0
        M[:, 1, 2 * (nreg - 1)] = 1.0                    # A_top = 0
        row = 2
        for i in range(nb):
            lo, hi = i, i + 1
            d_lo = (b[i] - b[i - 1]) if i > 0 else np.inf
            d_hi = (b[i + 1] - b[i]) if i + 1 < nb else np.inf
            e_lo = np.exp(-k * d_lo) if np.isfinite(d_lo) else np.zeros(nk)
            e_hi = np.exp(-k * d_hi) if np.isfinite(d_hi) else np.zeros(nk)
            # at z = b[i]: region lo has A e^0 + B e^{-k d_lo}; region hi has A e^{-k d_hi} + B e^0
            M[:, row, 2 * lo], M[:, row, 2 * lo + 1] = 1.0, e_lo
            M[:, row, 2 * hi], M[:, row, 2 * hi + 1] = -e_hi, -1.0
            row += 1
            # eps dphi/dz: below minus above = sigma / eps0 (unit charge at the source interface)
            M[:, row, 2 * lo], M[:, row, 2 * lo + 1] = e[lo] * k, -e[lo] * k * e_lo
            M[:, row, 2 * hi], M[:, row, 2 * hi + 1] = -e[hi] * k * e_hi, e[hi] * k
            if i == src:
                rhs[:, row] = 1.0 / EPS0
            row += 1
        sol = np.linalg.solve(M, rhs[..., None])[..., 0]
        j = int(np.searchsorted(b, z, side="left")) if not np.isclose(b, z, atol=1e-12).any() else \
            int(np.argmin(np.abs(np.asarray(b) - z)))
        # evaluate in the region at or below z (continuity makes either side equal on an interface)
        reg = j
        top = b[reg] if reg < nb else None
        bot = b[reg - 1] if reg > 0 else None
        A, B = sol[:, 2 * reg], sol[:, 2 * reg + 1]
        val = 0.0
        if top is not None:
            val = val + A * np.exp(np.minimum(k * (z - top), 0.0))
        if bot is not None:
            val = val + B * np.exp(np.minimum(-k * (z - bot), 0.0))
        return val


def smooth_green(stack, z, zs, rho, rho_max=None):
    """G(rho; z, zs) less the source plane's singular term 1/(4 pi eps0 eps_s R), on radii rho (m): the
    far field in closed form plus a Hankel integral of the bounded rest."""
    rho = np.asarray(rho, float)
    es = stack.eps_at(zs)
    dz = abs(z - zs)
    span = float(stack.z[-1] - stack.z[0]) or 1e-3
    bcut = 2.0 * span
    gaps = np.abs(stack.z - zs)
    gaps = gaps[gaps > 1e-12]
    dmin = max(min(float(gaps.min()) if len(gaps) else span, bcut), 1e-5)
    rho_max = float(rho_max if rho_max is not None else rho.max())
    dk = min(math.pi / (8 * max(rho_max, dmin)), 0.05 / dmin)
    kmax = 14.0 / dmin
    ks = np.arange(1, int(kmax / dk) + 2) * dk
    ph = stack.spectral(ks, z, zs)
    free = np.exp(-ks * dz) / (2 * EPS0 * es * ks)
    far = (1.0 - 1.0 / es) * np.exp(-ks * bcut) / (2 * EPS0 * ks)
    rest = ph - free - far
    w = np.full(len(ks), dk)
    w[0] = dk / 2 + dk / 2                       # the k = 0 end: k * rest -> 0, trapezoid from 0
    out = np.empty(len(rho))
    for c0 in range(0, len(rho), 64):
        r = rho[c0:c0 + 64]
        out[c0:c0 + 64] = (j0(np.outer(r, ks)) @ (w * ks * rest)) / (2 * np.pi)
    return out + (1.0 - 1.0 / es) / (4 * np.pi * EPS0 * np.sqrt(rho ** 2 + bcut ** 2))


class Electrostatic:
    """P on the copper cells of a Mesh (kae.em.mesh) in a Stack: z_sheet[l] the height of layer l's
    sheet (an interface of the stack)."""

    def __init__(self, m, stack, z_sheet):
        self.m, self.stack = m, stack
        self.z = list(z_sheet)
        self.L = len(m.layers)
        self.p = m.pitch * MM
        self.Ny = sfft.next_fast_len(2 * m.ny - 1, real=True)
        self.Nx = sfft.next_fast_len(2 * m.nx - 1, real=True)
        self.Kh = self._kernels()

    def table(self, l, ls):
        """T[dj, di] (V per C): the potential at cell centres of layer l of a unit charge spread over
        a cell of layer ls, for offsets -(n-1) .. (n-1)."""
        m, p = self.m, self.p
        dj = np.arange(-(m.ny - 1), m.ny)
        di = np.arange(-(m.nx - 1), m.nx)
        X, Y = np.meshgrid(di * p, dj * p)
        es = self.stack.eps_at(self.z[ls])
        dz = abs(self.z[l] - self.z[ls])
        if dz < 1e-12:
            sing = _panel_inv_r(p, p, X, Y) / (p * p)
        else:
            sing = _panel_inv_r3d(p, X, Y, dz) / (p * p)
        T = sing / (4 * np.pi * EPS0 * es)
        R = np.hypot(X, Y)
        # the smooth remainder on a radial grid fine against the cell (it varies on the dielectric's scale)
        rq = np.arange(0, R.max() + 2 * p, p / 8)
        sg = smooth_green(self.stack, self.z[l], self.z[ls], rq, rho_max=rq[-1])
        T = T + np.interp(R, rq, sg)
        # near offsets: averaged over the source panel (4 x 4 Gauss points)
        g, w = np.polynomial.legendre.leggauss(4)
        pts = [(u * p / 2, v * p / 2, wu * wv / 4) for u, wu in zip(g, w) for v, wv in zip(g, w)]
        c0, c1 = m.ny - 1, m.nx - 1
        for a in range(-NEAR, NEAR + 1):
            for b_ in range(-NEAR, NEAR + 1):
                jj, ii = c0 + a, c1 + b_
                if 0 <= jj < T.shape[0] and 0 <= ii < T.shape[1]:
                    avg = sum(wt * np.interp(math.hypot(b_ * p - u, a * p - v), rq, sg) for u, v, wt in pts)
                    T[jj, ii] += avg - np.interp(math.hypot(b_ * p, a * p), rq, sg)
        return T

    def _kernels(self):
        m = self.m
        jy = np.arange(-(m.ny - 1), m.ny) % self.Ny
        ix = np.arange(-(m.nx - 1), m.nx) % self.Nx
        K = np.empty((self.L, self.L, self.Ny, self.Nx // 2 + 1), complex)
        for l in range(self.L):
            for ls in range(l, self.L):
                C = np.zeros((self.Ny, self.Nx))
                C[np.ix_(jy, ix)] = self.table(l, ls)
                K[l, ls] = K[ls, l] = sfft.rfft2(C, workers=WORKERS)     # reciprocity: symmetric
        return K

    def apply(self, Q):
        """Potentials (V) on every cell of every layer for cell charges Q (L, ny, nx), C."""
        m = self.m
        G = np.zeros((self.L, self.Ny, self.Nx))
        G[:, :m.ny, :m.nx] = Q
        F = sfft.rfft2(G, workers=WORKERS)
        Y = np.einsum("ls...,s...->l...", self.Kh, F)
        return sfft.irfft2(Y, s=(self.Ny, self.Nx), workers=WORKERS)[:, :m.ny, :m.nx]

    def capacitance(self, drive, tol=1e-6, maxiter=2000):
        """Maxwell columns: for each net in `drive`, the charge (C) on every net with it at 1 V and every
        other copper at 0 V. Returns ({driven net: {net: C}}, iterations)."""
        m = self.m
        occ = m.lab >= 0
        idx = np.nonzero(occ)
        t0 = np.array([self._t00(l) for l in range(self.L)])
        out, its_all = {}, []
        for net in drive:
            nid = m.nets.index(net)
            v = np.where(m.lab == nid, 1.0, 0.0)[idx]
            q, its = self._cg(v, idx, t0, tol, maxiter)
            Q = np.zeros(m.lab.shape)
            Q[idx] = q
            out[net] = {n: float(Q[m.lab == k].sum()) for k, n in enumerate(m.nets) if (m.lab == k).any()}
            its_all.append(its)
        return out, its_all

    def _t00(self, l):
        p = self.p
        return _panel_inv_r(p, p, 0.0, 0.0) / (p * p) / (4 * np.pi * EPS0 * self.stack.eps_at(self.z[l]))

    def _cg(self, v, idx, t0, tol, maxiter):
        """P q = v on the copper cells, preconditioned conjugate gradients (P symmetric positive definite);
        Jacobi preconditioner from each layer's self term."""
        m = self.m
        dinv = 1.0 / t0[idx[0]]

        def A(q):
            Q = np.zeros(m.lab.shape)
            Q[idx] = q
            return self.apply(Q)[idx]
        q = v * dinv
        r = v - A(q)
        z = r * dinv
        p_ = z.copy()
        rz = r @ z
        bn = np.linalg.norm(v)
        for it in range(1, maxiter + 1):
            Ap = A(p_)
            a = rz / (p_ @ Ap)
            q += a * p_
            r -= a * Ap
            if np.linalg.norm(r) <= tol * bn:
                return q, it
            z = r * dinv
            rzn = r @ z
            p_ = z + (rzn / rz) * p_
            rz = rzn
        return q, maxiter
