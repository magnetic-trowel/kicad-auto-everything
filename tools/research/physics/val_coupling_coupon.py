# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Registered predictions for the node-vs-loop coupling coupon (validation program, coupon NL).

Used by docs/topics/physics/validation-coupons.md. Two predictions compete:

  round 1  node/loop duality is symmetric (README principle 2, LA4) and "height to the
           reference is the strongest knob" (principle 3): thinning the dielectric cuts
           capacitive (dv/dt) coupling as it cuts inductive (di/dt) coupling, and a grounded
           guard between aggressor and victim helps;
  lens SY  a plane breaks the duality: mutual L ~ h_a h_v / D^2 but mutual C of wide strips
           barely depends on h (a node over a plane is a potential patch), and a coplanar
           guard does almost nothing over thin dielectric (-1..3 % at h = 0.1 mm).

Coupon (JLC04161H-3313): a 2.0 mm aggressor strip and a victim strip (2.0 mm "wide" or
0.2 mm "narrow"), centres D = 4 mm apart, 60 mm long, each with an SMA at its near end and
a far end that is either open (node mode) or shorted to the plane with two vias (loop mode).
Two heights: L1 over the L2 plane (h = 0.0994 mm) and L1 over the L3 plane with L2 removed
under the coupon (h = 1.38 mm), each with and without a 0.5 mm grounded guard centred
between the strips and stitched every 2.5 mm.

Model: per-unit-length C and L matrices from the 2-D finite-volume field solver of
sy_duality_balance.py (reused: Field2D, graded_axis, ind_from_air_caps), layered dielectric
(prepreg er 4.1, core er 4.6); a lossless two-conductor multiconductor line (matrix
exponential) with 50-ohm ports gives S21 = 2 V_victim / V_source for both modes. Intervals:
corners of er (+-5 %), h (+-10 %) and strip width (+-25 um). Measurement: a NanoVNA-class
2-port at 5-100 MHz (keep |S21| above about -75 dB).

Run:  python tools/research/physics/val_coupling_coupon.py     (numpy + scipy, ~1-2 min)
"""
import math
import os
import sys

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
import numpy as np  # noqa: E402
from scipy.linalg import expm  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sy_duality_balance as sy  # noqa: E402  (round-2 SY 2-D field solver, reused)

MM = 1e-3
EPS0, MU0 = 8.854187e-12, 4e-7 * math.pi
PREPREG, CORE, T_IN, T_CU = 0.0994 * MM, 1.265 * MM, 15.2e-6, 35e-6
ER_PP, ER_CORE = 4.1, 4.6
D, LEN, ZREF = 4.0 * MM, 60 * MM, 50.0
FREQS = (5e6, 10e6, 30e6, 100e6)


def lc_matrices(h, wa, wv, guard, er_scale=1.0, dw=0.0):
    """2x2 C (F/m) and L (H/m) of aggressor/victim strips at height h over the plane (y = 0)."""
    wa, wv = wa + dw, wv + dw
    ra = (-D / 2 - wa / 2, -D / 2 + wa / 2, h, h + T_CU)
    rv = (D / 2 - wv / 2, D / 2 + wv / 2, h, h + T_CU)
    rg = (-0.25 * MM, 0.25 * MM, h, h + T_CU)
    keys_x = [ra[0], ra[1], rv[0], rv[1], 0.0] + ([rg[0], rg[1]] if guard else [])
    if h > 0.5 * MM:   # L1 over L3: core (er 4.6) from the plane up to 1.265 mm, prepreg resin above it
        ykeys = [0.0, CORE, h, h + T_CU]

        def er_fn(xc, yc):
            return np.where(yc < CORE, ER_CORE * er_scale, np.where(yc < h, ER_PP * er_scale, 1.0))
    else:
        ykeys = [0.0, h, h + T_CU]

        def er_fn(xc, yc):
            return np.where(yc < h, ER_PP * er_scale, 1.0)
    dmin = min(h / 5, T_CU / 2, 0.03 * MM)
    xs = sy.graded_axis(keys_x, -50 * MM, 50 * MM, dmin, 1.2, 1.5 * MM)
    ys = sy.graded_axis(ykeys, 0.0, 50 * MM, dmin, 1.2, 1.5 * MM)
    f = sy.Field2D(xs, ys, er_fn)
    fa = sy.Field2D(xs, ys, lambda xc, yc: np.ones_like(xc))
    grounds = [rg] if guard else []
    C = f.caps([[ra], [rv]], grounds=grounds)
    L = sy.ind_from_air_caps(fa.caps([[ra], [rv]], grounds=grounds))
    return C, L


def s21(C, L, f, mode):
    """S21 from the aggressor's near-end port to the victim's near-end port (both 50 ohm).
    mode 'node': both far ends open; 'loop': both far ends shorted to the plane."""
    w = 2 * math.pi * f
    n = 2
    A = np.zeros((2 * n, 2 * n), complex)
    A[:n, n:] = -1j * w * L
    A[n:, :n] = -1j * w * C
    phi = expm(A * LEN)                      # [V(l); I(l)] = phi [V(0); I(0)]
    M = np.zeros((4, 4), complex)
    rhs = np.zeros(4, complex)
    # near end: aggressor V1 + Z I1 = Vs (Vs = 1); victim V2 + Z I2 = 0 (I into the line)
    M[0, 0], M[0, 2], rhs[0] = 1.0, ZREF, 1.0
    M[1, 1], M[1, 3] = 1.0, ZREF
    rows = phi[n:, :] if mode == "node" else phi[:n, :]   # far end: I(l) = 0 (open) or V(l) = 0 (short)
    M[2:, :] = rows
    sol = np.linalg.solve(M, rhs)
    return 2 * sol[1]                        # S21 = 2 V2 / Vs


def db(x):
    return 20 * math.log10(max(abs(x), 1e-30))


def main():
    print(f"== node-vs-loop coupling coupon: strips D = {D/MM:.0f} mm apart, {LEN/MM:.0f} mm long, 50-ohm ports")
    cases = []
    for (wv, tag) in ((2.0 * MM, "wide/wide 2.0/2.0"), (0.2 * MM, "wide/narrow 2.0/0.2")):
        for h, htag in ((PREPREG, "L1/L2 h 0.10"), (PREPREG + T_IN + CORE, "L1/L3 h 1.38")):
            for guard in (False, True):
                C, L = lc_matrices(h, 2.0 * MM, wv, guard)
                spread = []
                for er_s, kh, dw in ((0.95, 0.9, -25e-6), (1.05, 1.1, 25e-6), (0.95, 1.1, 25e-6), (1.05, 0.9, -25e-6)):
                    Cc, Lc = lc_matrices(h * kh, 2.0 * MM, wv, guard, er_s, dw)
                    spread.append((-Cc[0, 1], Lc[0, 1]))
                spread = np.array(spread)
                cases.append(dict(tag=tag, htag=htag, h=h, guard=guard, C=C, L=L, spread=spread))
    print("  per unit length: C_m' (fF/mm), L_m' (pH/mm) [interval over er, h, w corners]; S21 (dB) node / loop mode")
    print("  case                                   C_m'                 L_m'                  " +
          "  ".join(f"{f/1e6:4.0f}MHz n/l" for f in FREQS))
    for c in cases:
        cm, lm = -c["C"][0, 1] * 1e12, c["L"][0, 1] * 1e9           # fF/mm, pH/mm
        sp = c["spread"]
        s = [(db(s21(c["C"], c["L"], f, "node")), db(s21(c["C"], c["L"], f, "loop"))) for f in FREQS]
        c["s"] = s
        print(f"  {c['tag']:18s} {c['htag']:12s} {'guard' if c['guard'] else '     '}  "
              f"{cm:7.4f} [{sp[:,0].min()*1e12:.4f},{sp[:,0].max()*1e12:.4f}]  "
              f"{lm:8.4f} [{sp[:,1].min()*1e9:.4f},{sp[:,1].max()*1e9:.4f}]  " +
              "  ".join(f"{a:6.1f}/{b:6.1f}" for a, b in s))
    print("\n== registered ratios (L1/L3 over L1/L2, i.e. h 1.38 mm vs 0.10 mm), no guard")
    for tag in ("wide/wide 2.0/2.0", "wide/narrow 2.0/0.2"):
        lo = [c for c in cases if c["tag"] == tag and not c["guard"] and c["h"] < 0.5 * MM][0]
        hi = [c for c in cases if c["tag"] == tag and not c["guard"] and c["h"] > 0.5 * MM][0]
        rc = hi["C"][0, 1] / lo["C"][0, 1]
        rl = hi["L"][0, 1] / lo["L"][0, 1]
        # intervals from the corner spreads (worst combinations)
        rc_lo, rc_hi = hi["spread"][:, 0].min() / lo["spread"][:, 0].max(), hi["spread"][:, 0].max() / lo["spread"][:, 0].min()
        rl_lo, rl_hi = hi["spread"][:, 1].min() / lo["spread"][:, 1].max(), hi["spread"][:, 1].max() / lo["spread"][:, 1].min()
        dn = hi["s"][2][0] - lo["s"][2][0]
        dl = hi["s"][2][1] - lo["s"][2][1]
        print(f"  {tag}: C_m ratio {rc:5.2f} [{rc_lo:.2f}, {rc_hi:.2f}] (+{20*math.log10(rc):.1f} dB);"
              f" L_m ratio {rl:6.1f} [{rl_lo:.1f}, {rl_hi:.1f}] (+{20*math.log10(rl):.1f} dB);"
              f" S21 change at 30 MHz: node {dn:+.1f} dB, loop {dl:+.1f} dB")
        print(f"     symmetric-duality alternative (C_m scales like L_m): C_m ratio ~{rl:.0f}, i.e. node S21 +{20*math.log10(rl):.0f} dB")
    print("\n== registered guard effect (guard / no guard)")
    for tag in ("wide/wide 2.0/2.0", "wide/narrow 2.0/0.2"):
        for hcut, htag in ((0.5 * MM, "h 0.10"), (10.0, "h 1.38")):
            ng = [c for c in cases if c["tag"] == tag and not c["guard"] and (c["h"] < 0.5 * MM) == (hcut < 1)][0]
            g = [c for c in cases if c["tag"] == tag and c["guard"] and (c["h"] < 0.5 * MM) == (hcut < 1)][0]
            print(f"  {tag:20s} {htag}: C_m x{g['C'][0,1]/ng['C'][0,1]:.3f}  L_m x{g['L'][0,1]/ng['L'][0,1]:.3f}"
                  f"  S21 at 30 MHz node {g['s'][2][0]-ng['s'][2][0]:+.2f} dB, loop {g['s'][2][1]-ng['s'][2][1]:+.2f} dB")


if __name__ == "__main__":
    main()
