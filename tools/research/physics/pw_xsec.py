# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""2-D cross-section current-distribution solver: skin and proximity effect in power copper.

Workstream 4 (power). Long parallel conductors (go, return, optional floating
plane) are cut into rectangular filaments. Per-unit-length partial inductance
between filaments is -(mu0/2pi) ln(d) (the constant cancels because the total
current is zero); the self term uses the rectangle's geometric mean distance
0.2235 (w + t). All filaments of one conductor share one voltage drop per metre;
each conductor carries a prescribed net current (+1, -1, or 0 for a floating
plane that only carries eddy current). Solving R' + j w L' gives R_ac(f), L'(f)
and where the current flows.

Cases (2 mm wide 1 oz traces unless noted), 1 kHz .. 100 MHz:
  plane    trace over a 20 mm wide return plane at h = 0.1, 0.5, 1.5 mm
  side     go and return side by side on one layer, 0.5 mm gap (no plane)
  side+fp  the same with a floating (zero-net-current) plane 0.1 mm below
  stack    go and return overlapped on adjacent layers, 0.1 mm apart

Run:  python pw_xsec.py        (numpy only, deterministic, about a minute)
"""
import math

import numpy as np

MU0 = 4e-7 * math.pi
RHO = 1.72e-8
mm = 1e-3


def graded(a, b, n, power=2.0):
    """n cells on [a, b], finer near both ends."""
    u = np.linspace(-1, 1, n + 1)
    g = np.sign(u) * np.abs(u) ** power
    e = a + (g + 1) / 2 * (b - a)
    return e


def rect(y0, y1, z0, z1, ny, nz, py=2.0, pz=1.0):
    ey = graded(y0, y1, ny, py)
    ez = graded(z0, z1, nz, pz) if pz != 1.0 else np.linspace(z0, z1, nz + 1)
    cells = []
    for i in range(ny):
        for j in range(nz):
            cells.append(((ey[i] + ey[i + 1]) / 2, (ez[j] + ez[j + 1]) / 2, ey[i + 1] - ey[i], ez[j + 1] - ez[j]))
    return cells


def _G(x, y):
    """4th antiderivative of ln(r)/1 (i.e. d4G/dx2dy2 = ln sqrt(x^2+y^2)), even in x and y (sympy-derived)."""
    x = np.abs(x)
    y = np.abs(y)
    r2 = x * x + y * y
    lg = np.where(r2 > 0, np.log(np.where(r2 > 0, r2, 1.0)), 0.0)
    a1 = np.arctan2(y, x)
    a2 = np.arctan2(x, y)
    return (x ** 3 * y * a1 / 3 + x ** 3 * y * a2 / 6 - 25 * x * x * y * y / 48 + x * y ** 3 * a2 / 6
            + 7 * y ** 4 / 288 + (-x ** 4 / 48 + x * x * y * y / 8 - y ** 4 / 48) * lg)


def lngmd(ya, wa, za, ta, yb, wb, zb, tb):
    """Exact mean of ln(distance) between two axis-aligned rectangles (centre, size), vectorised."""
    tot = 0.0
    for sx1, ex1 in ((1, 0.5), (-1, -0.5)):
        for sx2, ex2 in ((1, 0.5), (-1, -0.5)):
            X = (ya + ex1 * wa) - (yb + ex2 * wb)
            sx = sx1 * sx2 * -1  # (b,a):+ (a,a):- (b,b):- (a,b):+
            for sy1, ey1 in ((1, 0.5), (-1, -0.5)):
                for sy2, ey2 in ((1, 0.5), (-1, -0.5)):
                    Y = (za + ey1 * ta) - (zb + ey2 * tb)
                    sy = sy1 * sy2 * -1
                    tot = tot + sx * sy * _G(X, Y)
    return tot / (wa * ta * wb * tb)


def solve(conductors, currents, f):
    """conductors: list of cell lists; currents: net current per conductor (None = not used).
    Returns Z' (V/m per A) between conductor 0 and 1 for currents (+1, -1, 0...), and filament currents."""
    cells = [c for cond in conductors for c in cond]
    owner = np.concatenate([[k] * len(cond) for k, cond in enumerate(conductors)])
    y = np.array([c[0] for c in cells])
    z = np.array([c[1] for c in cells])
    w = np.array([c[2] for c in cells])
    t = np.array([c[3] for c in cells])
    n = len(cells)
    d = np.hypot(y[:, None] - y[None, :], z[:, None] - z[None, :])
    lnd = np.log(np.where(d > 0, d, 1.0))
    # exact rectangle-rectangle mean log distance for near pairs (and the self terms)
    size = np.maximum(w, t)
    near = d < 6 * np.maximum(size[:, None], size[None, :])
    ii, jj = np.nonzero(near)
    sc = 1e6  # work in micrometres for conditioning
    lnd[ii, jj] = lngmd(y[ii] * sc, w[ii] * sc, z[ii] * sc, t[ii] * sc, y[jj] * sc, w[jj] * sc, z[jj] * sc, t[jj] * sc) - math.log(sc)
    Lp = -MU0 / (2 * math.pi) * lnd
    R = RHO / (w * t)
    om = 2 * math.pi * f
    Z = np.diag(R).astype(complex) + 1j * om * Lp
    K = len(conductors)
    # unknowns: n filament currents, K voltages; rows: n KVL, K KCL
    A = np.zeros((n + K, n + K), complex)
    A[:n, :n] = Z
    for k in range(K):
        A[:n, n + k] = -(owner == k).astype(float)
        A[n + k, :n] = (owner == k).astype(float)
    b = np.zeros(n + K, complex)
    b[n:] = currents
    x = np.linalg.solve(A, b)
    I = x[:n]
    V = x[n:]
    Zp = V[0] - V[1]
    return Zp, I, owner, (y, z, w, t)


def rdc(conds):
    out = []
    for cond in conds:
        area = sum(c[2] * c[3] for c in cond)
        out.append(RHO / area)
    return out


def run_case(name, conds, currents, freqs):
    r0 = rdc(conds)
    rdc_loop = r0[0] + r0[1] if currents[1] != 0 else r0[0]
    print(f"  {name}")
    print("     f        R'/R'dc   L' nH/mm   |current| in the go conductor's half facing the return")
    for f in freqs:
        Zp, I, owner, (y, z, w, t) = solve(conds, currents, f)
        go = owner == 0
        # face toward return: for plane/stack cases, bottom half of go conductor; for side, inner half in y
        if "side" in name:
            face = go & (y > np.median(y[go]))
        else:
            face = go & (z < np.median(z[go]))
        share = abs(I[face].sum()) / abs(I[go].sum())
        print(f"  {f:9.0e}  {Zp.real/rdc_loop:7.2f}   {Zp.imag/(2*math.pi*f)*1e9/1e3:8.4f}   {share:5.2f}")


def main():
    freqs = (1e3, 1e5, 1e6, 1e7, 1e8)
    t = 35e-6
    W = 2 * mm
    for f in (1e6, 1e7, 1e8):
        print(f"skin depth in Cu at {f:.0e} Hz: {math.sqrt(RHO/(math.pi*f*MU0))*1e6:5.1f} um")
    nt = 8
    trace = lambda y0, z0: rect(y0, y0 + W, z0, z0 + t, 40, nt, 2.0, 1.6)
    print("== plane: trace over a 20 mm wide plane (return); DC R' counts trace + plane")
    for h in (0.1 * mm, 0.5 * mm, 1.5 * mm):
        plane = rect(-9 * mm, 11 * mm, -h - t, -h, 80, nt, 2.2, 1.6)
        # grade the plane toward the centre under the trace: map cells with a centre-weighted grid
        nf = int(min(140, max(50, 4.0 / (h / mm / 3))))
        ey = np.concatenate([np.linspace(-9, -1, 17)[:-1], np.linspace(-1, 3, nf)[:-1], np.linspace(3, 11, 17)]) * mm
        ez = np.linspace(-h - t, -h, nt + 1)
        plane = [((ey[i] + ey[i + 1]) / 2, (ez[j] + ez[j + 1]) / 2, ey[i + 1] - ey[i], ez[j + 1] - ez[j])
                 for i in range(len(ey) - 1) for j in range(nt)]
        run_case(f"h = {h/mm:.1f} mm", [trace(0, 0), plane], [1, -1], freqs)
    print("== side: go and return side by side, 0.5 mm gap, same layer, no plane")
    run_case("side", [trace(0, 0), trace(W + 0.5 * mm, 0)], [1, -1], freqs)
    print("== side + floating plane 0.1 mm below (eddy currents only)")
    ey = np.concatenate([np.linspace(-6, -1, 11)[:-1], np.linspace(-1, 5.5, 196)[:-1], np.linspace(5.5, 10.5, 11)]) * mm
    ez = np.linspace(-0.1 * mm - t, -0.1 * mm, nt + 1)
    fplane = [((ey[i] + ey[i + 1]) / 2, (ez[j] + ez[j + 1]) / 2, ey[i + 1] - ey[i], ez[j + 1] - ez[j])
              for i in range(len(ey) - 1) for j in range(nt)]
    run_case("side+fp", [trace(0, 0), trace(W + 0.5 * mm, 0), fplane], [1, -1, 0], freqs)
    print("== stack: go over return on adjacent layers, 0.1 mm apart")
    run_case("stack", [trace(0, 0), trace(0, -0.1 * mm - t)], [1, -1], freqs)
    print("note: R'/R'dc is for the go+return pair (or go+plane).")


if __name__ == "__main__":
    main()
