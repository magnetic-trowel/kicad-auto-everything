# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Red-team check of lens TH's damping claims (snubber as tuned absorber, ring-band dB per Q).

Independent of th_damping_ledger.py: the hot loop is written as a state-space system
(states i_L, v_oss, i_s, v_s) and its modal Q read from the eigenvalues; the ring-band
emission is taken from the full switch-node waveform (finite edge plus ring), not from the
loop-current resonance alone, so the edge spectrum sets a floor.

Normalised loop: L = 1, C_oss = 1 (Z0 = 1, w0 = 1); loop resistance R_loop = 1/Q0.
Snubber across C_oss: R_s + L_s (= l L) + C_s (= n C_oss).

Sections (python rt_damping.py [snubber|edge|all]):
  snubber  min over R_s of the worst modal Q for (n, l); robustness for C_oss 0.5-2x;
           TH: n = 3, l = 0 -> Q 0.96 (C_oss 0.5-2x: 1.59); n = 1 tuned (l ~ 1) -> Q 1.01 (2.72).
           Repeated with an undamped loop Q0 = 10 (device and capacitor losses) instead of 50.
  edge     switch-node spectrum of one switching event: a linear edge of duration t_r to V,
           then the ring left by the loop current (initial amplitude I*Z0). Spectral magnitude
           at the ring frequency for Q = 50, 20, 10, 5, 2, 1 relative to Q = 1, and relative to
           the edge alone. TH: 'damping is a 20-27 dB lever'.

Run: OMP_NUM_THREADS=1 python tools/research/physics/rt_damping.py   (seconds)
"""
import math
import sys

import numpy as np
from scipy.optimize import minimize_scalar


def system(n, ell, rs, q0=50.0, co=1.0):
    """State matrix of the loop. States: i_L, v_o, (i_s, v_s) or (v_s) when ell = 0."""
    rl = 1.0 / q0
    if ell > 0:
        # L di/dt = -rl i - v_o ; co dv_o/dt = i - i_s ; ell di_s/dt = v_o - rs i_s - v_s ; n dv_s/dt = i_s
        return np.array([[-rl, -1.0, 0.0, 0.0],
                         [1.0 / co, 0.0, -1.0 / co, 0.0],
                         [0.0, 1.0 / ell, -rs / ell, -1.0 / ell],
                         [0.0, 0.0, 1.0 / n, 0.0]])
    # i_s = (v_o - v_s)/rs
    return np.array([[-rl, -1.0, 0.0],
                     [1.0 / co, -1.0 / (co * rs), 1.0 / (co * rs)],
                     [0.0, 1.0 / (n * rs), -1.0 / (n * rs)]])


def worst_q(n, ell, rs, q0=50.0, co=1.0):
    ev = np.linalg.eigvals(system(n, ell, rs, q0, co))
    qs = [abs(z) / (2 * abs(z.real)) for z in ev if abs(z.imag) > 1e-9 and z.real < 0]
    return max(qs) if qs else 0.5


def best_rs(n, ell, q0=50.0):
    res = minimize_scalar(lambda lr: worst_q(n, ell, 10 ** lr, q0), bounds=(-2.5, 1.5), method="bounded",
                          options={"xatol": 1e-4})
    # guard against local minima: coarse scan
    grid = np.linspace(-2.5, 1.5, 161)
    qg = [worst_q(n, ell, 10 ** g, q0) for g in grid]
    g0 = grid[int(np.argmin(qg))]
    res2 = minimize_scalar(lambda lr: worst_q(n, ell, 10 ** lr, q0), bounds=(g0 - 0.05, g0 + 0.05), method="bounded")
    best = min((res.fun, res.x), (res2.fun, res2.x))
    return 10 ** best[1], best[0]


def sec_snubber():
    for q0 in (50.0, 10.0):
        print(f"== snubber: loop L = 1, C_oss = 1, undamped loop Q0 = {q0:.0f}; snubber C_s = n, L_s = l, R_s optimised")
        print("   n     l      R_s/Z0   worst Q   worst Q for C_oss 0.5-2x   snubber loss / (C_oss V^2 f)")
        for n, ells in ((3, (0.0, 0.32, 1.0)), (1, (0.0, 0.5, 0.93, 1.0)), (2, (0.0, 0.46)), (0.5, (0.0, 1.9))):
            for ell in ells:
                r, q = best_rs(n, ell, q0)
                rob = max(worst_q(n, ell, r, q0, co) for co in (0.5, 0.7, 1.0, 1.4, 2.0))
                print(f"   {n:3.1f}  {ell:5.2f}   {r:6.3f}   {q:6.2f}     {rob:6.2f}                    {n:4.1f}")
        print()
    print("   (an RC snubber dissipates C_s V^2 f whatever R_s is; 'a third of the loss' = n 1 vs 3)")


def edge_ring_spectrum(f, V, tr, A, fr, Q):
    """|X(f)| of one event: a linear ramp 0 -> V over tr (as a step response), plus a damped ring of amplitude A starting at tr.

    Ramp step: X_e(f) = V * exp(-j pi f tr) * sinc(f tr) / (j 2 pi f).
    Ring: A exp(-a t) sin(wr t) from t = tr, a = wr/(2Q): X_r = A wr / ((a + j w)^2 + wr^2) * exp(-j w tr).
    """
    w = 2 * math.pi * f
    xe = V * np.exp(-1j * math.pi * f * tr) * np.sinc(f * tr) / (1j * w)
    wr = 2 * math.pi * fr
    a = wr / (2 * Q)
    xr = A * wr / ((a + 1j * w) ** 2 + wr ** 2) * np.exp(-1j * w * tr)
    return np.abs(xe + xr), np.abs(xe)


def sec_edge():
    print("== edge: switch-node spectrum near the ring frequency, edge + ring (12 V, 10 A, Z0 1 ohm -> ring amplitude ~10 V)")
    V, A = 12.0, 10.0
    for tr, fr in ((2e-9, 160e6), (5e-9, 160e6), (1e-9, 300e6)):
        f = np.linspace(0.7 * fr, 1.3 * fr, 2001)
        ref = None
        cells = []
        _, edge_only = edge_ring_spectrum(f, V, tr, A, fr, 1.0)
        for Q in (50, 20, 10, 5, 2, 1):
            x, _ = edge_ring_spectrum(f, V, tr, A, fr, Q)
            pk = x.max()
            if Q == 1:
                ref = pk
            cells.append((Q, pk))
        e_pk = edge_only.max()
        txt = "; ".join(f"Q {Q:2d}: {20*math.log10(pk/ref):+5.1f} dB" for Q, pk in cells)
        print(f"   t_r {tr*1e9:.0f} ns, f_ring {fr/1e6:.0f} MHz (pi f t_r = {math.pi*fr*tr:.2f}): ring-band peak vs Q = 1: {txt};"
              f" Q = 1 vs edge alone {20*math.log10(ref/e_pk):+.1f} dB")
    print("   so the damping lever is ~20 log10(Q0) only while the ring dominates the edge spectrum near f_ring;")
    print("   from a realistic undamped Q0 of 5-10 it is ~12-19 dB, from copper-only Q 30-170 it would be 27-42 dB.")


SECTIONS = {"snubber": sec_snubber, "edge": sec_edge}

if __name__ == "__main__":
    which = sys.argv[1:] or ["all"]
    for name, fn in SECTIONS.items():
        if "all" in which or name in which:
            fn()
            print()
