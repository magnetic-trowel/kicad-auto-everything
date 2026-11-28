# SPDX-FileCopyrightText: 2026 HaslamPCB contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Peak rise of a thin track neck of length L between two wide tracks: finite volume vs IPC-2221 vs the fin
model of haslam.excite.dc.fin_dT (docs/topics/physics/thermal-physics.md, 'IPC-2221/2152 as a thermal model').

The FV model is tm_board_thermal_fv.Board's (each copper layer a 2-D sheet of k_Cu t_Cu where copper is plus
k_xy times half of each adjacent dielectric, layers coupled by k_z through the dielectric, h on both faces) on a
tensor-product grid that is fine across and at the ends of the neck and grows geometrically to the board edge,
so a 0.127 mm track is ten cells wide on a 60 mm board. Copper resistivity is constant (20 C, no TCR), as the
IPC chart's own fit absorbs TCR (thermal-physics.md, 'TCR feedback').

Case: 2-layer 1.6 mm FR-4, 1 oz, h 10 W/m^2K per side, a 0.127 mm neck of length L on the top layer between two
2 mm wide, 15 mm long tracks, 2 A through all of it (Joule heat I^2 rho/(w t) per metre in each piece).
Check: the uniform-grid Board solver and this one agree on a coarse case (printed first).

Run (numpy, scipy; about a minute):

    python tools/research/physics/tm_track_fin_fv.py
"""
import math
import os
import sys

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.linalg import spsolve

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../../haslam/src"))
from tm_board_thermal_fv import K_CU, K_XY, K_Z, OZ, two_layer  # noqa: E402

from haslam.excite.dc import RHO_CU, fin_dT, ipc_dT  # noqa: E402

T_CU = OZ
D = 1.6e-3 - 2 * OZ
H = 10.0
ALPHA = 0.00393      # 1/K, copper TCR at 20 C


def axis(lo, hi, breaks, foci, d0, cap, grow=0.15):
    """Cell edges from lo to hi through every point of `breaks`: the local spacing is d0 at the nearest of `foci`,
    growing by `grow` times the distance from it, at most cap(x)."""
    breaks = sorted(set([lo, hi] + list(breaks)))
    out = [lo]
    for a, b in zip(breaks, breaks[1:]):
        x = a
        while x < b - 1e-12:
            d = min(cap((x + b) / 2 if b - x < 1e-9 else x), d0 + grow * min(abs(x - f) for f in foci))
            x = b if x + 1.5 * d >= b else x + d
            out.append(x)
    return np.array(out)


def solve(ex, ey, cov, p):
    """Steady T of a 2-layer board on the tensor grid with cell edges ex, ey; cov[l] the copper mask, p[l] watts
    per cell. Same conductances as tm_board_thermal_fv.Board.solve, with each face the two half cells in series."""
    dx, dy = np.diff(ex), np.diff(ey)
    nx, ny, nl = len(dx), len(dy), 2
    idx = np.arange(nl * nx * ny).reshape(nl, nx, ny)
    rows, cols, vals, diag = [], [], [], np.zeros(nl * nx * ny)

    def couple(a, b, g):
        a, b, g = a.ravel(), b.ravel(), np.broadcast_to(g, a.shape).ravel()
        rows.extend([a, b]); cols.extend([b, a]); vals.extend([-g, -g])
        np.add.at(diag, a, g); np.add.at(diag, b, g)

    DX, DY = np.meshgrid(dx, dy, indexing="ij")
    for l in range(nl):
        gs = K_XY * D / 2 + K_CU * T_CU * cov[l]
        rx = DX / (2 * gs * DY)                          # half-cell resistance along x
        ry = DY / (2 * gs * DX)
        couple(idx[l, :-1, :], idx[l, 1:, :], 1 / (rx[:-1, :] + rx[1:, :]))
        couple(idx[l, :, :-1], idx[l, :, 1:], 1 / (ry[:, :-1] + ry[:, 1:]))
    couple(idx[0], idx[1], K_Z * DX * DY / D)
    diag[idx[0].ravel()] += (H * DX * DY).ravel()
    diag[idx[1].ravel()] += (H * DX * DY).ravel()
    rows.append(np.arange(diag.size)); cols.append(np.arange(diag.size)); vals.append(diag)
    A = coo_matrix((np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))), shape=(diag.size,) * 2)
    return spsolve(A.tocsc(), p.ravel()).reshape(nl, nx, ny)


def neck(L, I=2.0, w=0.127e-3, W=2.0e-3, arm=15e-3, margin=25e-3, tcr=False, r=1.0):
    """(peak rise of the neck, rise at its ends) in K: a neck of width w, length L between two arms W wide, arm long.
    tcr: copper heat scaled by 1 + alpha T (ambient 20 C), iterated to its fixed point; r scales the grid spacing."""
    x0, x1 = L / 2 + arm + margin, W / 2 + margin
    ex = axis(-x0, x0, [-L / 2 - arm, -L / 2, 0.0, L / 2, L / 2 + arm], [-L / 2, L / 2], r * w / 5,
              lambda x: r * (min(2e-4, L / 20) if abs(x) < L / 2 else 1e-3))
    ey = axis(-x1, x1, [-W / 2, -w / 2, w / 2, W / 2], [-w / 2, w / 2], r * w / 10,
              lambda y: r * (w / 10 if abs(y) < w / 2 else 1e-3))
    xc, yc = (ex[:-1] + ex[1:]) / 2, (ey[:-1] + ey[1:]) / 2
    X, Y = np.meshgrid(xc, yc, indexing="ij")
    DX, DY = np.meshgrid(np.diff(ex), np.diff(ey), indexing="ij")
    in_neck = (np.abs(X) < L / 2) & (np.abs(Y) < w / 2)
    in_arm = (np.abs(X) >= L / 2) & (np.abs(X) < L / 2 + arm) & (np.abs(Y) < W / 2)
    cov = np.zeros((2,) + X.shape, bool)
    cov[0] = in_neck | in_arm
    p = np.zeros_like(cov, float)
    # Joule heat per unit area of a conductor of width wd carrying I: I^2 rho / (wd^2 t)
    p[0][in_neck] = (I ** 2 * RHO_CU / (w ** 2 * T_CU) * DX * DY)[in_neck]
    p[0][in_arm] = (I ** 2 * RHO_CU / (W ** 2 * T_CU) * DX * DY)[in_arm]
    T = solve(ex, ey, cov, p)[0]
    for _ in range(40 if tcr else 0):
        T1 = solve(ex, ey, cov, p * (1 + ALPHA * np.concatenate([T[None], T[None]])))[0]
        done = np.abs(T1 - T).max() < 1e-3
        T = T1
        if done:
            break
    jy = np.argmin(np.abs(yc))
    end = int(np.searchsorted(xc, L / 2))            # the first cell of the arm
    return float(T[in_neck].max()), float(T[end, jy])


def check_vs_board():
    """The tensor solver against Board on one uniform coarse grid: 1 W in a 2x2 mm copper square."""
    b = two_layer(lx=40e-3, ly=40e-3, dx=0.5e-3, h=H)
    m = b.rect(19e-3, 19e-3, 21e-3, 21e-3)
    b.cov[0][m] = True
    b.add_power(m, 1.0)
    Tb = b.solve()[0].max()
    e = np.linspace(0, 40e-3, 81)
    cov = np.zeros((2, 80, 80), bool)
    cov[0] = m
    p = np.zeros((2, 80, 80))
    p[0][m] = 1.0 / m.sum()
    Tt = solve(e, e, cov, p)[0].max()
    print(f"check: uniform Board {Tb:.3f} K, tensor solver {Tt:.3f} K")


def main():
    check_vs_board()
    I, w, t = 2.0, 0.127, T_CU * 1e3
    for L in (2.0, 60.0):
        a, b = neck(L * 1e-3, I)[0], neck(L * 1e-3, I, r=0.5)[0]
        print(f"mesh: L {L:g} mm peak {a:.2f} K, half spacing {b:.2f} K")
    print(f"{'L mm':>6} {'FV peak':>8} {'FV end':>7} {'FV excess':>9} {'FV+TCR':>7} {'IPC':>7} {'fin':>7} "
          f"{'fin/FVexcess':>12} {'fin/FVpeak':>10}")
    for L in (0.5, 0.8, 1.0, 2.0, 5.0, 8.0, 20.0, 60.0):
        pk, en = neck(L * 1e-3, I)
        pkt, _ = neck(L * 1e-3, I, tcr=True)
        ipc = ipc_dT(I, w, t, True)
        fin = fin_dT(I, w, t, True, L)
        print(f"{L:6.1f} {pk:8.2f} {en:7.2f} {pk - en:9.2f} {pkt:7.2f} {ipc:7.1f} {fin:7.2f} "
              f"{fin / max(pk - en, 1e-9):12.2f} {fin / pk:10.2f}")


if __name__ == "__main__":
    main()
