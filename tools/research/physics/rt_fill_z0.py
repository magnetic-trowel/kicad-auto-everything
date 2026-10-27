# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Red-team resolution of a cross-document conflict: same-layer ground fill at gap g = h beside a
~50-ohm microstrip changes Z0 by -3.7% (rule-genealogy-si-emi-rf.md, rg_fill_and_decaps.py) or by
-6.5% (fields-si-emi.md and rf-geometry.md, fe_field2d.py).

The two scripts differ in conductor thickness (one grid cell, t/h ~ 0.08, vs t = 35 um on h = 0.1 mm,
t/h = 0.35) and grid (12 vs 8 cells per h). This is an independent 2-D finite-difference
electrostatic solve (own code; cell-face permittivities; 20 cells per h; grounded box 40h x 20h),
for t/h = 0.05, 0.175 and 0.35, w/h = 1.9 and 2.0, fill gap g/h = 0.5, 1, 2, 3, 5.
Z0 = 1 / (c sqrt(C C_air)). No solder mask.

Run: OMP_NUM_THREADS=1 python tools/research/physics/rt_fill_z0.py   (about 3-4 minutes; 72 sparse solves)
"""
import math

import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as spla

C0 = 299792458.0
EPS0 = 8.854e-12


def cap_per_length(w_h, t_h, gap_h, er, n=20, half_width=20.0, height=20.0):
    """C/eps0 per unit length; lengths in units of h; plane at y = 0, strip bottom at y = 1."""
    dx = 1.0 / n
    nx, ny = int(2 * half_width * n) + 1, int(height * n) + 1
    x = -half_width + dx * np.arange(nx)
    y = dx * np.arange(ny)
    X, Y = np.meshgrid(x, y, indexing="ij")
    tcells = max(1, int(round(t_h * n)))
    ytop = 1.0 + tcells * dx
    strip = (np.abs(X) <= w_h / 2 + 1e-9) & (Y >= 1.0 - 1e-9) & (Y <= ytop + 1e-9)
    fixed = np.zeros((nx, ny), bool)
    val = np.zeros((nx, ny))
    fixed[0, :] = fixed[-1, :] = True
    fixed[:, 0] = fixed[:, -1] = True
    fixed |= strip
    val[strip] = 1.0
    if gap_h is not None:
        fill = (np.abs(X) >= w_h / 2 + gap_h - 1e-9) & (Y >= 1.0 - 1e-9) & (Y <= ytop + 1e-9)
        fixed |= fill
    # permittivity per cell (between nodes); dielectric below y = 1
    yc = 0.5 * (y[1:] + y[:-1])
    ecell = np.where(yc < 1.0, er, 1.0)[None, :].repeat(nx - 1, axis=0)
    ex = np.zeros((nx - 1, ny))                    # x-edges (i,j)-(i+1,j): average of cells above and below
    ex[:, 1:-1] = 0.5 * (ecell[:, :-1] + ecell[:, 1:])
    ex[:, 0], ex[:, -1] = ecell[:, 0], ecell[:, -1]
    ey = np.zeros((nx, ny - 1))                    # y-edges (i,j)-(i,j+1)
    ey[1:-1, :] = 0.5 * (ecell[:-1, :] + ecell[1:, :])
    ey[0, :], ey[-1, :] = ecell[0, :], ecell[-1, :]
    ids = np.arange(nx * ny).reshape(nx, ny)
    rows, cols, data = [], [], []
    diag = np.zeros((nx, ny))
    for (a_sl, b_sl, e) in (((slice(0, -1), slice(None)), (slice(1, None), slice(None)), ex),
                            ((slice(None), slice(0, -1)), (slice(None), slice(1, None)), ey)):
        a, b = ids[a_sl].ravel(), ids[b_sl].ravel()
        rows += [a, b]
        cols += [b, a]
        data += [-e.ravel(), -e.ravel()]
        diag[a_sl] += e
        diag[b_sl] += e
    K = sp.csr_matrix((np.concatenate(data), (np.concatenate(rows), np.concatenate(cols))), shape=(nx * ny, nx * ny))
    K = K + sp.diags(diag.ravel())
    f = fixed.ravel()
    free = ~f
    v = val.ravel()
    phi = v.copy()
    phi[free] = spla.spsolve(K[free][:, free].tocsc(), -K[free][:, f] @ v[f])
    # energy: C = phi^T K phi (V = 1), per unit length in units of eps0
    return float(phi @ (K @ phi))


def z0(w_h, t_h, gap_h, er=4.3):
    c = cap_per_length(w_h, t_h, gap_h, er)
    ca = cap_per_length(w_h, t_h, gap_h, 1.0)
    return 1.0 / (C0 * EPS0 * math.sqrt(c * ca))


def main():
    print("== fill: Z0 change from a same-layer ground fill at gap g (both sides), er 4.3, no mask")
    for w_h in (1.9, 2.0):
        for t_h in (0.05, 0.175, 0.35):
            zr = z0(w_h, t_h, None)
            cells = []
            for g in (0.5, 1.0, 2.0, 3.0, 5.0):
                cells.append(f"g {g:3.1f}h: {(z0(w_h, t_h, g)/zr-1)*100:+5.1f}%")
            print(f"   w/h {w_h:3.1f}, t/h {t_h:5.3f}: Z0 {zr:5.1f} ohm; " + "; ".join(cells))
    print("   rg_fill_and_decaps.py (t ~ one cell of h/12, w/h 2): -3.7% at g = h;"
          " fe_field2d.py (t/h 0.35, w/h 1.9): -6.5% at g = h")


if __name__ == "__main__":
    main()
