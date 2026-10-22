# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Steady-state 2-D finite-volume board thermal solver (multi-layer, vias, h).

Model: each copper layer is a 2-D grid of nodes. A node's in-plane sheet
conductance is k_cu*t_cu where the layer has copper, plus k_xy*(half of each
adjacent dielectric thickness) everywhere (FR-4 in-plane conduction). Adjacent
layers couple vertically through the dielectric (k_z*dx^2/d) and through via
barrels (k_cu*pi*t_p*(D-t_p)/d). The two outer layers lose heat to ambient
with a combined convection+radiation coefficient h (W/m^2K) per side. Sources
are watts spread over a rectangle on layer 0. The system G*T = P is solved
with SuperLU. Everything is linear, so superposition of single-source
responses is exact; the only approximation in "Green's-function placement
scoring" is replacing the exact response with a shift-invariant kernel.

Experiments printed (all 1.6 mm FR-4, k_xy 0.8, k_z 0.3 W/mK, h 10 W/m^2K per
side unless stated):
  E0  validation: uniform 2-layer sheet vs the analytic fin kernel K0(r/lambda)
  E1  copper area per watt: 1 W in a 3x3 mm exposed pad, two-sided square pour
      of side s with 9 EP vias and stitching vias; area needed for 40 K rise
      (checks TI SNVA419's 15.3 cm^2/W)
  E2  EP via count 0..9 (diminishing returns), plating 17.5 vs 25 um
  E3  copper weight 0.5..4 oz
  E4  a 20 mm copper cut 5 mm from the source, perpendicular vs radial
      (cf. SNVA419 rule 4: +5.5 K vs +1.5 K)
  E5  thermal coupling vs distance on 2-layer and 4-layer boards
  E6  placement scoring: exact multi-source solve vs (a) shift-invariant kernel
      and (b) kernel + method of images for the adiabatic board edges

Run (numpy, scipy; about 1 minute on one core):

    python tools/research/physics/tm_board_thermal_fv.py
"""
import math

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.linalg import spsolve
from scipy.special import k0

K_CU = 390.0       # W/mK, electrodeposited copper ~ 385-400
K_XY = 0.8         # W/mK, FR-4 in-plane (glass direction), typ. 0.6-1.0
K_Z = 0.3          # W/mK, FR-4 through-plane, typ. 0.25-0.4
OZ = 34.8e-6       # m per oz/ft^2


class Board:
    """Rectangular board, n copper layers, uniform grid of pitch dx (m)."""

    def __init__(self, lx, ly, dx, t_cu, d_diel, h_top=10.0, h_bot=10.0):
        self.nx, self.ny = int(round(lx / dx)), int(round(ly / dx))
        self.dx = dx
        self.t_cu = list(t_cu)            # copper thickness per layer (m)
        self.d = list(d_diel)             # dielectric thickness between layers (m)
        self.nl = len(self.t_cu)
        assert len(self.d) == self.nl - 1
        self.cov = np.zeros((self.nl, self.nx, self.ny), bool)   # copper mask
        self.via = np.zeros((self.nx, self.ny))  # via barrel conductance-area k*A (W*m/K)
        self.h = (h_top, h_bot)
        self.p = np.zeros((self.nl, self.nx, self.ny))

    def xy(self):
        x = (np.arange(self.nx) + 0.5) * self.dx
        y = (np.arange(self.ny) + 0.5) * self.dx
        return np.meshgrid(x, y, indexing="ij")

    def rect(self, x0, y0, x1, y1):
        X, Y = self.xy()
        return (X >= x0) & (X < x1) & (Y >= y0) & (Y < y1)

    def add_via(self, x, y, drill=0.3e-3, plating=25e-6, fill_k=0.0):
        i, j = int(x / self.dx), int(y / self.dx)
        a_barrel = math.pi * plating * (drill - plating)   # finished hole = drill - 2t? keep drill as outer
        a_core = math.pi * (drill / 2 - plating) ** 2
        self.via[i, j] += K_CU * a_barrel + fill_k * a_core

    def add_power(self, mask, watts, layer=0):
        n = mask.sum()
        self.p[layer][mask] += watts / n

    def solve(self, p=None):
        nl, nx, ny, dx = self.nl, self.nx, self.ny, self.dx
        p = self.p if p is None else p
        n = nl * nx * ny
        idx = np.arange(n).reshape(nl, nx, ny)
        rows, cols, vals = [], [], []
        diag = np.zeros(n)

        def couple(a, b, g):
            a, b, g = a.ravel(), b.ravel(), np.broadcast_to(g, a.shape).ravel()
            rows.extend([a, b]); cols.extend([b, a]); vals.extend([-g, -g])
            np.add.at(diag, a, g); np.add.at(diag, b, g)

        for l in range(nl):
            share = 0.0
            if l > 0:
                share += self.d[l - 1] / 2
            if l < nl - 1:
                share += self.d[l] / 2
            gs = K_XY * share + K_CU * self.t_cu[l] * self.cov[l]
            # face conductance between neighbours: harmonic mean of 2*gs
            gx = 2 * gs[:-1, :] * gs[1:, :] / (gs[:-1, :] + gs[1:, :])
            gy = 2 * gs[:, :-1] * gs[:, 1:] / (gs[:, :-1] + gs[:, 1:])
            couple(idx[l, :-1, :], idx[l, 1:, :], gx)
            couple(idx[l, :, :-1], idx[l, :, 1:], gy)
        for l in range(nl - 1):
            g = K_Z * dx * dx / self.d[l] + self.via / self.d[l]
            couple(idx[l], idx[l + 1], g)
        diag[idx[0].ravel()] += self.h[0] * dx * dx
        diag[idx[-1].ravel()] += self.h[1] * dx * dx
        rows.append(np.arange(n)); cols.append(np.arange(n)); vals.append(diag)
        A = coo_matrix((np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))),
                       shape=(n, n)).tocsc()
        T = spsolve(A, p.ravel())
        return T.reshape(nl, nx, ny)


def two_layer(lx=100e-3, ly=100e-3, dx=0.5e-3, oz=1.0, h=10.0):
    return Board(lx, ly, dx, [oz * OZ, oz * OZ], [1.6e-3 - 2 * oz * OZ], h, h)


def ep_setup(b, cx, cy, ep=3e-3, nvia=9, plating=25e-6, pitch=1e-3):
    """1 W on a 3x3 mm exposed pad at (cx, cy); nvia in a centred grid."""
    m = b.rect(cx - ep / 2, cy - ep / 2, cx + ep / 2, cy + ep / 2)
    b.cov[0][m] = True
    b.add_power(m, 1.0)
    k = int(round(math.sqrt(nvia))) if nvia > 0 else 0
    if nvia == 2:
        pts = [(-0.5, 0), (0.5, 0)]
    else:
        pts = [((i - (k - 1) / 2), (j - (k - 1) / 2)) for i in range(k) for j in range(k)]
    for (u, v) in pts[:nvia]:
        b.add_via(cx + u * pitch, cy + v * pitch, plating=plating)
    return m


def fin_lambda(gs_total, h_total):
    return math.sqrt(gs_total / h_total)


def e0_validation():
    print("E0  validation: 2-layer 1 oz full copper both sides, 1 W point-ish source")
    b = two_layer(lx=200e-3, ly=200e-3, dx=1e-3)
    b.cov[:] = True
    c = 100e-3
    m = b.rect(c - 1e-3, c - 1e-3, c + 1e-3, c + 1e-3)
    b.add_power(m, 1.0)
    for x in np.arange(c - 3e-3, c + 4e-3, 1e-3):
        for y in np.arange(c - 3e-3, c + 4e-3, 1e-3):
            b.add_via(x + 0.5e-3, y + 0.5e-3)
    T = b.solve()
    gs = 2 * K_CU * OZ + K_XY * 1.53e-3
    lam = fin_lambda(gs, 20.0)
    print(f"    sheet G_s = {gs*1e3:.1f} mW/K, lambda = sqrt(G_s/h_tot) = {lam*1e3:.1f} mm")
    for r in (5e-3, 10e-3, 20e-3, 40e-3, 80e-3):
        i = int((c + r) / b.dx)
        tfv = 0.5 * (T[0, i, int(c / b.dx)] + T[1, i, int(c / b.dx)])
        tan = 1.0 / (2 * math.pi * gs) * k0(r / lam)
        print(f"    r={r*1e3:5.0f} mm  FV {tfv:6.2f} K   analytic K0 {tan:6.2f} K")


def e1_area_per_watt():
    print("E1  1 W, 3x3 mm EP, 9 vias, two-sided square pour of side s (stitched 5 mm grid)")
    res = []
    for s in (10e-3, 15e-3, 20e-3, 30e-3, 40e-3, 50e-3, 60e-3, 80e-3):
        b = two_layer(lx=120e-3, ly=120e-3)
        c = 60e-3
        pour = b.rect(c - s / 2, c - s / 2, c + s / 2, c + s / 2)
        b.cov[0][pour] = True
        b.cov[1][pour] = True
        ep_setup(b, c, c)
        for x in np.arange(c - s / 2 + 2.5e-3, c + s / 2, 5e-3):
            for y in np.arange(c - s / 2 + 2.5e-3, c + s / 2, 5e-3):
                if abs(x - c) > 2.5e-3 or abs(y - c) > 2.5e-3:
                    b.add_via(x, y)
        T = b.solve()
        tmax = T[0].max()
        res.append((s, tmax))
        print(f"    s={s*1e3:4.0f} mm  area {s*s*1e4:6.1f} cm^2   pad rise {tmax:6.1f} K")
    # interpolate area for 40 K
    for (s0, t0), (s1, t1) in zip(res, res[1:]):
        if t0 >= 40 > t1:
            s = s0 + (t0 - 40) / (t0 - t1) * (s1 - s0)
            print(f"    -> 40 K reached at s ~ {s*1e3:.0f} mm, area ~ {s*s*1e4:.1f} cm^2 (TI rule: 15.3 cm^2)")
    print("    isothermal-plate bound A = 1/(2*h*dT) = %.1f cm^2 at h=10, dT=40" % (1 / (2 * 10 * 40) * 1e4))


def e2_vias():
    print("E2  1 W, 3x3 mm EP, vary EP vias (0.3 mm drill), 80x80 mm 2-layer 1 oz board")
    for case in ("top+bottom 40x40 pours", "top = EP only, bottom full plane"):
        for plating in (17.5e-6, 25e-6):
            out = []
            for nv in (0, 1, 2, 4, 9):
                b = two_layer(lx=80e-3, ly=80e-3)
                c = 40e-3
                if case.startswith("top+"):
                    pour = b.rect(c - 20e-3, c - 20e-3, c + 20e-3, c + 20e-3)
                    b.cov[0][pour] = True
                    b.cov[1][pour] = True
                else:
                    b.cov[1][:] = True
                    b.cov[0][b.rect(c - 2e-3, c - 2e-3, c + 2e-3, c + 2e-3)] = True
                ep_setup(b, c, c, nvia=nv, plating=plating)
                T = b.solve()
                out.append(f"{nv}:{T[0].max():.1f}")
            print(f"    {case:33s} plating {plating*1e6:4.1f} um  vias:pad-rise K  " + "  ".join(out))


def e3_weight():
    print("E3  copper weight, 1 W, 3x3 EP, 9 vias, 40x40 mm two-sided pour")
    for oz in (0.5, 1, 2, 4):
        b = two_layer(lx=80e-3, ly=80e-3, oz=oz)
        c = 40e-3
        pour = b.rect(c - 20e-3, c - 20e-3, c + 20e-3, c + 20e-3)
        b.cov[0][pour] = True
        b.cov[1][pour] = True
        ep_setup(b, c, c)
        T = b.solve()
        print(f"    {oz:3.1f} oz  pad rise {T[0].max():5.1f} K   pour-edge rise {T[0][int((c+19e-3)/b.dx), int(c/b.dx)]:5.1f} K")


def e4_cuts():
    print("E4  20 x 0.5 mm cut in top copper, 5 mm from a 1 W EP, 2-layer 1 oz, 50x50 pour")
    base = None
    for kind in ("none", "perpendicular", "radial", "perp, both layers", "radial, both layers"):
        b = two_layer(lx=80e-3, ly=80e-3)
        c = 40e-3
        pour = b.rect(c - 25e-3, c - 25e-3, c + 25e-3, c + 25e-3)
        b.cov[0][pour] = True
        b.cov[1][pour] = True
        ep_setup(b, c, c)
        for x in np.arange(c - 22.5e-3, c + 25e-3, 5e-3):
            for y in np.arange(c - 22.5e-3, c + 25e-3, 5e-3):
                if abs(x - c) > 2.5e-3 or abs(y - c) > 2.5e-3:
                    b.add_via(x, y)
        layers = [0, 1] if "both" in kind else [0]
        for l in layers:
            if kind.startswith("perp"):
                b.cov[l][b.rect(c + 5e-3, c - 10e-3, c + 5.5e-3, c + 10e-3)] = False
            elif kind.startswith("radial"):
                b.cov[l][b.rect(c + 5e-3, c - 0.25e-3, c + 25e-3, c + 0.25e-3)] = False
        T = b.solve()
        t = T[0].max()
        base = t if base is None else base
        print(f"    {kind:19s} pad rise {t:5.2f} K  (delta {t-base:+.2f} K)")


def e5_coupling():
    print("E5  rise at distance d from a 1 W source (10x10 cm board, full planes)")
    for name, tcu, dd in (("2L 1oz", [OZ, OZ], [1.53e-3]),
                          ("4L 1/0.5/0.5/1 oz", [OZ, OZ / 2, OZ / 2, OZ], [0.2e-3, 1.1e-3, 0.2e-3])):
        b = Board(100e-3, 100e-3, 0.5e-3, tcu, dd)
        b.cov[:] = True
        c = 50e-3
        ep_setup(b, c, c)
        T = b.solve()
        j = int(c / b.dx)
        vals = []
        for d in (0, 5e-3, 10e-3, 20e-3, 30e-3, 45e-3):
            vals.append(f"{d*1e3:.0f}mm:{T[0][int((c+d)/b.dx), j]:.1f}")
        gs = sum(K_CU * t for t in tcu) + K_XY * sum(dd)
        print(f"    {name:18s} lambda={fin_lambda(gs, 20)*1e3:4.0f} mm  " + "  ".join(vals))


def e6_superposition():
    print("E6  placement scoring: 4 sources on a 60x40 mm 2-layer board with full planes")
    lx, ly = 60e-3, 40e-3
    srcs = [(10e-3, 10e-3, 1.0), (30e-3, 20e-3, 0.5), (52e-3, 32e-3, 0.8), (45e-3, 8e-3, 0.3)]

    def board():
        b = two_layer(lx=lx, ly=ly)
        b.cov[:] = True
        return b
    b = board()
    for (x, y, w) in srcs:
        m = b.rect(x - 1.5e-3, y - 1.5e-3, x + 1.5e-3, y + 1.5e-3)
        b.add_power(m, w)
    T = b.solve()
    # shift-invariant kernel: FV response to 1 W at the centre of a large board
    # (near field), analytic fin kernel K0 beyond 60 mm (far field)
    kb = two_layer(lx=200e-3, ly=200e-3)
    kb.cov[:] = True
    c = 100e-3
    kb.add_power(kb.rect(c - 1.5e-3, c - 1.5e-3, c + 1.5e-3, c + 1.5e-3), 1.0)
    K = kb.solve()[0]
    ci = int(c / kb.dx)
    gs = 2 * K_CU * OZ + K_XY * 1.53e-3
    lam = fin_lambda(gs, 20.0)

    def kern(dxm, dym):
        r = math.hypot(dxm, dym)
        if r < 60e-3:
            return K[ci + int(round(dxm / kb.dx)), ci + int(round(dym / kb.dx))]
        return k0(r / lam) / (2 * math.pi * gs)

    def predict(px, py, nimg):
        tot = 0.0
        for (x, y, w) in srcs:
            for m in range(-nimg, nimg + 1):
                for xi in ((2 * m * lx + x, 2 * m * lx - x) if nimg else (x,)):
                    for n in range(-nimg, nimg + 1):
                        for yi in ((2 * n * ly + y, 2 * n * ly - y) if nimg else (y,)):
                            tot += w * kern(px - xi, py - yi)
        return tot

    for (x, y, w) in srcs:
        exact = T[0][int(x / b.dx), int(y / b.dx)]
        print(f"    {w:.1f} W at ({x*1e3:.0f},{y*1e3:.0f}) mm: exact {exact:5.1f} K | kernel only "
              f"{predict(x, y, 0):5.1f} | +images(1) {predict(x, y, 1):5.1f} | +images(6) {predict(x, y, 6):5.1f}")


if __name__ == "__main__":
    e0_validation()
    e1_area_per_watt()
    e2_vias()
    e3_weight()
    e4_cuts()
    e5_coupling()
    e6_superposition()
