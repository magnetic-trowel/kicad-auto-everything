# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Small coupling "oracles" used in the worked thought experiments.

Each block prints one table.  All are first-order physics, not field solves;
they show magnitudes and scaling, and give the numbers quoted in
docs/topics/physics/worked-thought-experiments.md.

1. mutual inductance between a lateral hot loop and a victim loop on the same
   layer, with and without a perfect ground plane under both (image method,
   Neumann double line integral), vs separation; plus the induced voltage
   M*di/dt and its volt-second area M*dI.
2. DC current spreading in a 1 oz ground plane (finite-difference Laplace on a
   60 x 40 mm sheet): voltage gradient in uV/mm at candidate ADC locations, for
   0.3 A of load return between a buck and an MCU.
3. capacitive coupling of a switch node (dv/dt) into a crystal input, with the
   crosstalk factor K = 1/(1+(s/h)^2) applied to the self capacitance, for a
   4-layer (h = 0.1 mm) and a 2-layer (h = 1.5 mm) board.
4. source envelopes: trapezoid harmonic amplitude of a 48 MHz clock at the
   2.4 GHz ISM band for two edge rates, and USB 2.0 HS common-mode voltage
   from intra-pair skew.
5. in-plane temperature gradient around a 0.4 W converter on a 4-layer board
   (fin model: T ~ K0(r/lambda), two 1 oz inner planes, h = 10 W/m^2K per side)
   and the thermal EMF across an 0603 resistor aligned with the gradient.
6. one-line checks: via inductance and ESD voltage, plane-pair capacitance,
   heatsink tab capacitance and C*dv/dt current, shunt ESL spike vs signal.

Run:  python dr_coupling_oracles.py        (numpy + scipy, < 10 s, deterministic)
"""
from __future__ import annotations

import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as spla

MU0 = 4e-7 * np.pi
EPS0 = 8.854e-12


# ---------------------------------------------------------------- 1. mutual L
def rect_segments(x0, y0, w, h, z, step=0.1e-3):
    """Counter-clockwise rectangle as (midpoints, dl vectors)."""
    pts = [(x0, y0), (x0 + w, y0), (x0 + w, y0 + h), (x0, y0 + h), (x0, y0)]
    mids, dls = [], []
    for (xa, ya), (xb, yb) in zip(pts[:-1], pts[1:]):
        n = max(1, int(np.hypot(xb - xa, yb - ya) / step))
        t = (np.arange(n) + 0.5) / n
        mids.append(np.c_[xa + (xb - xa) * t, ya + (yb - ya) * t, np.full(n, z)])
        dls.append(np.tile([(xb - xa) / n, (yb - ya) / n, 0.0], (n, 1)))
    return np.vstack(mids), np.vstack(dls)


def neumann(a, b):
    (p1, d1), (p2, d2) = a, b
    r = np.linalg.norm(p1[:, None, :] - p2[None, :, :], axis=2)
    return MU0 / (4 * np.pi) * np.sum((d1 @ d2.T) / r)


def mutual_table():
    h = 0.1e-3                      # both loops 0.1 mm above the return plane
    hot = (0.0, 0.0, 6e-3, 3e-3)    # 6 x 3 mm lateral hot loop (18 mm^2)
    vic_w, vic_h = 10e-3, 1e-3      # 10 x 1 mm victim loop (input pair, 1 mm apart)
    didt = 2.0 / 2e-9               # 2 A commutated in 2 ns = 1 A/ns
    print("\n[1] hot loop 6x3 mm vs victim loop 10x1 mm, same layer, edge gap d")
    print(f"{'gap mm':>6} {'M no plane pH':>14} {'M plane h=0.1mm pH':>19} "
          f"{'V=M di/dt (plane) mV':>21} {'M*dI (plane) V*ns':>18}")
    for gap in (2e-3, 5e-3, 10e-3, 20e-3, 40e-3):
        a = rect_segments(*hot, z=h)
        b = rect_segments(hot[2] + gap, 1e-3, vic_w, vic_h, z=h)
        b_img = rect_segments(hot[2] + gap, 1e-3, vic_w, vic_h, z=-h)
        m_free = neumann(a, b)
        m_plane = m_free - neumann(a, b_img)    # image loop carries reversed current
        print(f"{gap*1e3:6.0f} {m_free*1e12:14.2f} {m_plane*1e12:19.4f} "
              f"{m_plane*didt*1e3:21.4f} {m_plane*2.0*1e9:18.6f}")


# ---------------------------------------------------------------- 2. plane DC
def solve_plane(W, H, dx, sources, cut=None):
    """Sheet potential for point-pad current sources [(x, y, I)].  `cut(i, j,
    i2, j2)` returns True for cell links that a slot removes."""
    nx, ny = int(W / dx), int(H / dx)
    g = 1.0 / (1.72e-8 / 35e-6)     # 1 oz copper conductance per square
    idx = np.arange(nx * ny).reshape(ny, nx)
    rows, cols, vals = [], [], []
    for j in range(ny):
        for i in range(nx):
            for dj, di in ((0, 1), (1, 0)):
                jj, ii = j + dj, i + di
                if jj < ny and ii < nx and not (cut and cut(i, j, ii, jj)):
                    k, k2 = idx[j, i], idx[jj, ii]
                    rows += [k, k2, k, k2]
                    cols += [k, k2, k2, k]
                    vals += [g, g, -g, -g]
    G = sp.csr_matrix((vals, (rows, cols)), shape=(nx * ny, nx * ny))
    I = np.zeros(nx * ny)
    for x, y, cur in sources:       # 2 x 2 mm pads
        ii = np.arange(int((x - 1e-3) / dx), int((x + 1e-3) / dx))
        jj = np.arange(int((y - 1e-3) / dx), int((y + 1e-3) / dx))
        pads = idx[np.ix_(jj, ii)].ravel()
        I[pads] += cur / len(pads)
    keep = np.arange(1, nx * ny)    # node 0 is the reference
    V = np.zeros(nx * ny)
    V[keep] = spla.spsolve(G[keep][:, keep].tocsc(), I[keep])
    V = V.reshape(ny, nx)
    gy, gx = np.gradient(V, dx)
    return np.hypot(gx, gy)


def plane_gradient_table():
    W, H, dx = 60e-3, 40e-3, 0.5e-3
    load = 0.3                      # A of 3.3 V load return: MCU (55,30) -> buck (12,30)
    src = [(55e-3, 30e-3, load), (12e-3, 30e-3, -load)]
    # optional slot: isolates the region x > 36 mm, y < 16 mm except a 4 mm
    # neck at x = 36..40 mm along y = 16 mm (ADC sits at the neck)
    xs, ys = int(36e-3 / dx), int(16e-3 / dx)
    neck = (int(36e-3 / dx), int(40e-3 / dx))

    def cut(i, j, i2, j2):
        if j2 == j + 1 and j == ys - 1 and i >= xs and not (neck[0] <= i < neck[1]):
            return True             # horizontal slot along y = 16 mm
        if i2 == i + 1 and i == xs - 1 and j < ys:
            return True             # vertical slot along x = 36 mm
        return False

    grad_solid = solve_plane(W, H, dx, src)
    grad_slot = solve_plane(W, H, dx, src, cut)
    print("\n[2] 0.3 A load return, MCU (55,30) mm -> buck (12,30) mm, 60x40 mm 1 oz plane")
    print(f"    R_sq = {1.72e-8/35e-6*1e3:.2f} mOhm/sq; 24-bit LSB at gain 32 (+-78 mV FS) = "
          f"{2*0.078/2**24*1e9:.1f} nV")
    print(f"{'location':>22} {'solid uV/mm':>12} {'3 mm drop nV':>13} {'peninsula uV/mm':>16}")
    for name, (x, y) in {"on the current path": (33, 30), "5 mm off the path": (33, 25),
                         "bottom edge, middle": (33, 3), "bottom-right corner": (55, 3),
                         "bottom-left corner": (5, 3), "peninsula interior": (48, 8)}.items():
        i, j = int(x * 1e-3 / dx), int(y * 1e-3 / dx)
        print(f"{name:>16} ({x:2d},{y:2d}) {grad_solid[j, i]*1e3:12.3f} "
              f"{grad_solid[j, i]*3e-3*1e9:13.0f} {grad_slot[j, i]*1e3:16.4f}")


# ---------------------------------------------------------------- 3. C dv/dt
def cap_coupling_table():
    print("\n[3] switch node -> crystal XIN, 3 mm parallel exposure, 12 V edge, 20 pF node")
    print(f"{'board':>10} {'h mm':>5} {'gap mm':>6} {'K':>7} {'C_m fF':>7} {'dQ pC':>6} {'dV mV':>6}")
    for board, h, c_self in (("4-layer", 0.1e-3, 1.2e-10), ("2-layer", 1.5e-3, 0.55e-10)):
        for gap in (1e-3, 3e-3, 6e-3):
            K = 1.0 / (1.0 + (gap / h) ** 2)
            cm = c_self * K * 3e-3
            dq = cm * 12.0
            print(f"{board:>10} {h*1e3:5.1f} {gap*1e3:6.0f} {K:7.4f} {cm*1e15:7.2f} "
                  f"{dq*1e12:6.3f} {dq/20e-12*1e3:6.2f}")


# ---------------------------------------------------------------- 4. envelopes
def trapezoid_harmonic(V, f0, duty, tr, n):
    T = 1.0 / f0
    s1 = np.sinc(n * duty)          # numpy sinc = sin(pi x)/(pi x)
    s2 = np.sinc(n * tr / T)
    return 2 * V * duty * abs(s1 * s2)


def envelope_table():
    print("\n[4a] 48 MHz, 3.3 V clock: harmonic nearest 2.44 GHz (n = 51)")
    for tr in (1e-9, 4e-9):
        # duty slightly off 50 % so even/odd harmonics both exist; use envelope
        a = 2 * 3.3 / (np.pi * 51) * min(1.0, 1.0 / (np.pi * 51 * tr * 48e6))
        dbm = 10 * np.log10((a / np.sqrt(2)) ** 2 / 50 / 1e-3)
        print(f"    t_r = {tr*1e9:.0f} ns: envelope {a*1e3:6.2f} mV -> {dbm:6.1f} dBm "
              f"(as a 50-ohm source); isolation to reach -105 dBm: {dbm+105:5.1f} dB")
    print("\n[4b] USB 2.0 HS: common-mode spike from intra-pair skew (400 mV swing, t_r 500 ps)")
    for mm in (0.25, 1.27, 5.0):
        dt = mm * 6.0e-12 / 1.0     # ~6 ps/mm outer-layer microstrip
        vcm = 0.5 * 0.4 * min(1.0, dt / 500e-12)
        print(f"    skew {mm:5.2f} mm = {dt*1e12:5.1f} ps -> V_cm,pk ~ {vcm*1e3:5.2f} mV "
              f"for ~{500:.0f} ps per edge")


# ---------------------------------------------------------------- 5. thermal
def thermal_table():
    from scipy.special import k1
    P, kt, h2 = 0.4, 2 * 35e-6 * 390 + 1.6e-3 * 0.3, 2 * 10.0
    lam = np.sqrt(kt / h2)
    print(f"\n[5] 0.4 W source, sheet conductance k*t = {kt*1e3:.1f} mW/K, fin length "
          f"lambda = {lam*1e3:.0f} mm")
    print(f"{'r mm':>5} {'dT/dr K/mm':>11} {'dT over 0603 (1.6 mm)':>22} {'EMF @1-3 uV/K, nV':>18}")
    for r in (5e-3, 10e-3, 20e-3, 40e-3):
        g = P / (2 * np.pi * kt * lam) * k1(r / lam)      # K/m
        dT = g * 1.6e-3
        print(f"{r*1e3:5.0f} {g*1e-3:11.3f} {dT:22.3f} {dT*1e3:9.0f}-{dT*3e3:.0f}")


# ---------------------------------------------------------------- 6. checks
def misc_checks():
    print("\n[6] one-line checks")
    for h_mm in (0.1, 1.6):         # via to a plane h mm away, 0.3 mm drill (Johnson approx.)
        h, d = h_mm / 25.4, 0.3 / 25.4
        L = 5.08 * h * (np.log(4 * h / d) + 1)        # nH
        print(f"    via 0.3 mm drill, {h_mm} mm to plane: ~{L:.2f} nH -> "
              f"{L*30:.1f} V at 30 A/ns (IEC 61000-4-2 8 kV contact)")
    c_pp = EPS0 * 4.3 / 1.1e-3
    print(f"    L2-L3 plane pair, 1.1 mm core, er 4.3: {c_pp*1e8:.1f} pF/cm^2 "
          f"-> {c_pp*17e-4*1e12:.0f} pF for 17 cm^2")
    c_tab = EPS0 * 5 * 100e-6 / 0.2e-3
    print(f"    TO-220 tab 100 mm^2 on 0.2 mm pad (er 5): {c_tab*1e12:.0f} pF; "
          f"48 V in 15 ns -> {c_tab*48/15e-9*1e3:.0f} mA CM pulses")
    didt = 20 / 15e-9
    print(f"    shunt ESL 1 nH at {didt*1e-9:.2f} A/ns -> {1e-9*didt:.2f} V spike vs "
          f"20 A x 2 mOhm = 40 mV signal")


if __name__ == "__main__":
    mutual_table()
    plane_gradient_table()
    cap_coupling_table()
    envelope_table()
    thermal_table()
    misc_checks()
