# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""When do trace corners matter? Two checks behind docs/topics/physics/rule-genealogy-*.md.

1. RF/SI: excess capacitance (Gupta and Kirschning closed forms) and inductance
   (Gupta) of an unmitred 90-degree bend in a 50-ohm FR-4 microstrip, as a
   function of substrate height h. Prints the frequency at which the bend alone
   reaches -20 dB and -30 dB return loss, and the step-reflection peak for a
   given rise time (|G| ~ Z0*C/(2*t_r), capacitance only = worst case).
2. DC/power: resistance of an L-shaped copper bend (unit width, sheet
   resistance 1) by a finite-difference Laplace solve, for a sharp corner, a 45
   degree outer chamfer, an inner fillet and a rounded (annular) bend. Reports
   the corner's resistance in "squares" and the current-density peak near the
   inner corner.

Run (needs numpy and scipy):

    python tools/research/physics/rg_corners.py
"""
import math

import numpy as np
from scipy.sparse import lil_matrix
from scipy.sparse.linalg import spsolve

ER = 4.3
C0 = 2.998e8


def ms_z0(w, h, er=ER):
    u = w / h
    if u <= 1:
        ee = (er + 1) / 2 + (er - 1) / 2 * ((1 + 12 / u) ** -0.5 + 0.04 * (1 - u) ** 2)
        z0 = 60 / math.sqrt(ee) * math.log(8 / u + u / 4)
    else:
        ee = (er + 1) / 2 + (er - 1) / 2 * (1 + 12 / u) ** -0.5
        z0 = 120 * math.pi / (math.sqrt(ee) * (u + 1.393 + 0.667 * math.log(u + 1.444)))
    return z0, ee


def w_for_z0(z0_target, h, er=ER):
    lo, hi = 0.01 * h, 30 * h
    for _ in range(100):
        mid = math.sqrt(lo * hi)
        if ms_z0(mid, h, er)[0] > z0_target:
            lo = mid
        else:
            hi = mid
    return mid


def bend_rf():
    print("== 1. Unmitred 90-degree bend, 50-ohm microstrip, er=4.3")
    print("h[mm]  w[mm]  C_gupta[fF] C_kirsch[fF] L_gupta[pH]  f(-20dB) C-only / with L   f(-30dB) C-only  |G| @ t_r=100ps")
    for h_mm in (0.1, 0.2, 0.36, 0.8, 1.5):
        h = h_mm * 1e-3
        w = w_for_z0(50, h)
        u = w / h
        c_g = w * ((9.5 * ER + 1.25) * u + 5.2 * ER + 7.0) * 1e-12          # Gupta, pF/m * m
        c_k = w * ((10.35 * ER + 2.5) * u + (2.6 * ER + 5.64)) * 1e-12     # Kirschning (Qucs eq. 11.84)
        l_g = h * 100 * (4 * math.sqrt(u) - 4.21) * 1e-9                    # Gupta, nH/m * m (0.5<=u<=2)
        z0 = 50.0
        tau_c = c_g * z0 / 2
        tau_lc = abs(l_g / z0 - c_g * z0) / 2
        f20c = 0.1 / (2 * math.pi * tau_c)
        f20lc = 0.1 / (2 * math.pi * tau_lc)
        f30c = 0.0316 / (2 * math.pi * tau_c)
        g_step = c_g * z0 / (2 * 100e-12)
        print(f"{h_mm:5.2f} {w*1e3:6.2f} {c_g*1e15:10.1f} {c_k*1e15:11.1f} {l_g*1e12:11.1f}"
              f"   {f20c/1e9:6.1f} / {f20lc/1e9:6.1f} GHz      {f30c/1e9:6.1f} GHz     {g_step*100:5.2f} %")
    print("rule of thumb from the C-only column: f(-20 dB) ~ 3 GHz*mm / h[mm]; with bend L ~ 4 GHz*mm / h")


def solve_bend(mask, dx):
    """Sheet conductor on a grid; V=1 on the left edge cells of the bottom arm, V=0 on the top edge cells."""
    ny, nx = mask.shape
    idx = -np.ones(mask.shape, dtype=int)
    cells = np.argwhere(mask)
    for k, (j, i) in enumerate(cells):
        idx[j, i] = k
    n = len(cells)
    a = lil_matrix((n, n))
    b = np.zeros(n)
    for k, (j, i) in enumerate(cells):
        diag = 0.0
        for dj, di in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            jj, ii = j + dj, i + di
            if 0 <= jj < ny and 0 <= ii < nx and mask[jj, ii]:
                a[k, idx[jj, ii]] -= 1
                diag += 1
        # Dirichlet contacts: half-cell link to an electrode
        if i == 0:
            diag += 2
            b[k] += 2 * 1.0
        if j == ny - 1:
            diag += 2
        a[k, k] += diag
    v = spsolve(a.tocsr(), b)
    vg = np.full(mask.shape, np.nan)
    for k, (j, i) in enumerate(cells):
        vg[j, i] = v[k]
    left = [k for k, (j, i) in enumerate(cells) if i == 0]
    current = sum(2 * (1.0 - v[k]) for k in left)   # sheet conductance 1, unit depth
    return 1.0 / current, vg


def bend_dc():
    print("\n== 2. DC resistance of an L-bend (width 1, arms 4 squares each), finite differences")
    arm, n = 4.0, 30
    dx = 1.0 / n
    size = int((arm + 1) * n)
    yy, xx = np.mgrid[0:size, 0:size]
    x = (xx + 0.5) * dx
    y = (yy + 0.5) * dx
    base = ((y <= 1) | (x >= arm))           # bottom arm y in [0,1], right arm x in [arm, arm+1]
    variants = {
        "sharp 90": base,
        "outer 45 chamfer, leg 1.0w": base & ~((x - y) > arm),
        "inner fillet, leg 0.5w": base | (((arm - x) + (y - 1)) < 0.5) & (x < arm) & (y > 1),
        "constant-width 45 (chamfer+fillet 1.0w)": (base & ~((x - y) > arm)) | ((((arm - x) + (y - 1)) < 1.0) & (x < arm) & (y > 1)),
        "rounded, r_inner=0.5w": None,
    }
    # rounded bend: replace the corner region by an annulus centred at (arm-0.5, 1.5)
    cx, cy, ri, ro = arm - 0.5, 1.5, 0.5, 1.5
    r = np.hypot(x - cx, y - cy)
    quad = (x >= cx) & (y <= cy)
    arms = ((y <= 1) & (x <= cx)) | ((x >= arm) & (y >= cy))
    variants["rounded, r_inner=0.5w"] = arms | (quad & (r >= ri) & (r <= ro))
    straight = 2 * arm   # squares outside the corner square for the sharp case
    for name, m in variants.items():
        rtot, vg = solve_bend(m.astype(bool), dx)
        # current density near the inner corner (one cell diagonally off it) vs straight arm
        gy, gx = np.gradient(vg, dx)
        jmag = np.hypot(gx, gy)
        j_arm = np.nanmedian(jmag[(y < 1) & (x > 0.5) & (x < 1.5)])
        near = (np.hypot(x - arm, y - 1) < 0.1) & m
        j_peak = np.nanmax(jmag[near]) if near.any() else float("nan")
        print(f"{name:42s} R_total={rtot:6.3f} sq  corner adds {rtot-straight:5.3f} sq   J(inner corner)/J(arm) ~ {j_peak/j_arm:4.1f}")
    print("(grid 1/30 w; the sharp-corner peak is a singularity and grows with refinement)")


if __name__ == "__main__":
    bend_rf()
    bend_dc()
