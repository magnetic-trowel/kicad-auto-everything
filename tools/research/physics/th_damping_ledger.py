# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Where ringing energy goes: copper-loss Q, snubber reach and tuning, plane-cavity damping.

Round-2 lens TH (thermodynamics, dissipation, noise, irreversibility),
docs/topics/physics/lens-th.md. Every resonant mode m of a board loses its energy
through parallel channels k (copper, dielectric, devices, a designed resistor,
radiation): 1/Q_m = sum_k 1/Q_mk, and channel k receives the share Q_m/Q_mk. This
script checks three claims of that "Q ledger":

  qcu      Copper alone cannot damp. For any parallel-plate-like structure (a hot loop
           over its return, a plane pair, a wide microstrip) the copper-loss Q is
           h/delta (+1 for internal inductance): field gap over skin depth, independent
           of length and width. Exact two-slab surface-impedance formula vs h/delta, and
           round 1's "Q 31-173" (pw_cells.py ring) reproduced as h/delta at the heights
           its inductances imply (L = mu0 h * 2 squares).
  snubber  An RC snubber across the switch, with its own connection inductance L_s.
           Normalised hot loop L = 1, C_oss = 1 (Z0 = 1, w0 = 1), copper Q = 50.
           (a) min over R_s of the worst modal Q vs l = L_s/L and n = C_s/C_oss;
           (b) the tuned-absorber optimum (Den Hartog): best l is about 1/n, i.e.
               L_s C_s = L C_oss; robustness when C_oss moves 0.5x..2x;
           (c) time-domain switch-node ringing for selected designs (impulse response);
           (d) ring-band emission: peak of the loop-current spectrum vs Q (20 dB/decade);
           (e) the price of damping in watts for a 12 V / 10 A / 500 kHz buck.
  cavity   Plane-pair (PWR-GND) cavity, 100 x 80 mm, probe near a corner, using the
           fe_cavity.py modal model (loss term tan(d) + delta/d in k^2):
           (a) peak |Z| (0.3-2.5 GHz) vs plane spacing d for FR-4 (tan d 0.02) and a
               low-loss laminate (0.004): Z_peak ~ d * Q(d), Q = 1/(tan d + delta/d);
           (b) designed dissipation at the voltage antinodes of every open-edge mode:
               RC terminations along all four edges, R vs the matched value
               R_m = eta0 d / (sqrt(er) p), with and without 0.5 nH of mounting ESL.

Run:  python tools/research/physics/th_damping_ledger.py [qcu|snubber|cavity|all]
numpy + scipy; about 30 s on one core. Quasi-static and lumped; uncalibrated against
measurement (see the lens doc for caveats).
"""
import math
import os
import sys
import warnings

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")

import numpy as np  # noqa: E402
from scipy.signal import BadCoefficients, impulse, lti  # noqa: E402

warnings.filterwarnings("ignore", category=BadCoefficients)  # tiny leading numerator terms; results checked

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fe_cavity as fc  # noqa: E402

MU0 = 4e-7 * math.pi
EPS0 = 8.854e-12
RHO_CU = 1.72e-8
SIG_CU = 1 / RHO_CU


def skin_depth(f):
    return math.sqrt(RHO_CU / (math.pi * f * MU0))


def q_two_plates(f, h, t=35e-6):
    """Q = wL/R of two wide parallel plates (gap h, thickness t each), exact slab surface impedance.

    Per square: Z = j w mu0 h + 2 Z_s, Z_s = (gamma/sigma) coth(gamma t), gamma = (1+j)/delta
    (field on the facing side only, zero on the outer side).
    """
    w = 2 * math.pi * f
    g = (1 + 1j) / skin_depth(f)
    zs = g / SIG_CU / np.tanh(g * t)
    return (w * MU0 * h + 2 * zs.imag) / (2 * zs.real)


def exp_qcu():
    print("== qcu: copper-loss Q of parallel-plate structures = h/delta (+1); exact slab model / h/delta")
    hs = (0.05e-3, 0.1e-3, 0.2e-3, 0.5e-3, 1.5e-3)
    print("   f        delta  " + "".join(f"  h={h*1e3:4.2f} mm  " for h in hs))
    for f in (10e6, 100e6, 300e6, 1e9):
        row = "".join(f" {q_two_plates(f, h):6.1f}/{h/skin_depth(f):6.1f}" for h in hs)
        print(f"  {f/1e6:6.0f} MHz {skin_depth(f)*1e6:5.2f} um {row}")
    print("  round 1 (pw_cells.py ring): copper Q of a 2-square loop with L and C_oss given;")
    print("  the implied gap is h = L/(2 mu0), and Q_cu = h/delta reproduces every value:")
    for L, C, q_r1 in ((0.3e-9, 1e-9, 31), (1e-9, 1e-9, 76), (3e-9, 1e-9, 173), (1e-9, 0.3e-9, 103)):
        fr = 1 / (2 * math.pi * math.sqrt(L * C))
        h = L / (2 * MU0)
        print(f"    L {L*1e9:3.1f} nH, C_oss {C*1e9:3.1f} nF: f_ring {fr/1e6:4.0f} MHz, h {h*1e3:5.3f} mm,"
              f" h/delta {h/skin_depth(fr):6.1f}, exact {q_two_plates(fr, h):6.1f} (round 1: {q_r1})")
    print("  -> copper damping needs h ~ delta (a few um above 100 MHz). Every PCB gap is 10-500x larger,")
    print("     so damping must be a designed loss channel (device, ESR, snubber, termination, lossy dielectric).")


# --------------------------------------------------------------------------
# snubber: hot loop L (with copper R) in series with C_oss || (L_s + R_s + 1/(s C_s))
# --------------------------------------------------------------------------
def char_poly(n, ell, r, co=1.0, qcu=50.0):
    """Characteristic polynomial (descending powers) of the normalised loop; L = 1, Z0 = 1."""
    L, cs, ls, rs, rcu = 1.0, n, ell, r, 1.0 / qcu
    a, b = ls * cs, rs * cs
    if a > 0:
        return [L * co * a, L * co * b + rcu * co * a, L * (co + cs) + rcu * co * b + a, rcu * (co + cs) + b, 1.0]
    return [L * co * b, L * (co + cs) + rcu * co * b, rcu * (co + cs) + b, 1.0]


def worst_q(n, ell, r, co=1.0, qcu=50.0):
    p = np.roots(char_poly(n, ell, r, co, qcu))
    qs = [abs(z) / (2 * abs(z.real)) for z in p if abs(z.imag) > 1e-9]
    return max(qs) if qs else 0.5


RS = np.logspace(-2, 1.5, 300)


def best_r(n, ell, co=1.0):
    q = [worst_q(n, ell, r, co) for r in RS]
    i = int(np.argmin(q))
    return RS[i], q[i]


def zpar_coeffs(n, ell, r, co=1.0, snub=True):
    """Z_par(s) = num/den (ascending powers) for C_oss || snubber branch."""
    P = np.polynomial.polynomial
    if not snub:
        return np.array([1.0]), np.array([0.0, co])
    num = np.array([1.0, r * n, ell * n])          # (ell n s^2 + r n s + 1) / (n s) is the branch
    den = P.polyadd(np.array([0.0, n]), P.polymul([0.0, co], num))
    return num, den


def loop_current_peak(n, ell, r, co=1.0, qcu=50.0, snub=True):
    """Peak over w of |I(jw)| for an initial loop current (source L*I0 = 1): emission proxy."""
    w = np.logspace(-1.0, 1.6, 6000)
    s = 1j * w
    zo = 1 / (s * co)
    if snub:
        zsn = s * ell + r + 1 / (s * n)
        zp = zo * zsn / (zo + zsn)
    else:
        zp = zo
    i = np.abs(1.0 / (s + 1.0 / qcu + zp))
    k = int(np.argmax(i))
    return i[k], w[k]


def ring_time_domain(n, ell, r, snub=True, qcu=50.0):
    """Switch-node voltage deviation after a unit loop-current step (impulse of V = L*I0 * Zp/(sL+R+Zp))."""
    P = np.polynomial.polynomial
    num, den_z = zpar_coeffs(n, ell, r, snub=snub)
    den = P.polyadd(P.polymul([1.0 / qcu, 1.0], den_z), num)
    t = np.linspace(0, 120, 40000)
    sysm = lti(num[::-1], den[::-1])
    t, y = impulse(sysm, T=t)
    return t, y


def exp_snubber():
    print("== snubber: hot loop L, C_oss; snubber R_s + C_s (= n C_oss) with its own inductance L_s (= l L); copper Q 50")
    base_pk, _ = loop_current_peak(3, 0, None, snub=False)
    print("  (a) min over R_s of the worst modal Q, and the ring-band loop-current peak vs no snubber")
    print("      l = L_s/L:   " + "".join(f"{ell:>14.2f}" for ell in (0, 0.1, 0.3, 0.5, 1.0, 2.0)))
    for n in (1, 3, 10):
        cells = []
        for ell in (0, 0.1, 0.3, 0.5, 1.0, 2.0):
            r, q = best_r(n, ell)
            pk, _ = loop_current_peak(n, ell, r)
            cells.append(f"  Q{q:4.2f} {20*math.log10(pk/base_pk):5.1f}dB")
        print(f"      n = {n:2d}:     " + "".join(cells))
    print("  (b) tuned absorber: best l for each n (designed at C_oss = 1), worst Q when C_oss moves 0.5x..2x")
    for n in (0.5, 1, 2, 3, 5, 10):
        best = None
        for ell in np.concatenate([[0.0], np.logspace(-2, 0.8, 70)]):
            r, q = best_r(n, ell)
            if best is None or q < best[0]:
                best = (q, ell, r)
        q0, ell, r = best
        rob = max(worst_q(n, ell, r, co) for co in (0.5, 0.7, 1.0, 1.4, 2.0))
        r0, q00 = best_r(n, 0.0)
        rob0 = max(worst_q(n, 0.0, r0, co) for co in (0.5, 0.7, 1.0, 1.4, 2.0))
        print(f"      n = {n:4.1f} (snubber loss = n x C_oss V^2 f): best l = {ell:5.3f} (1/n = {1/n:5.3f}),"
              f" R_s = {r:4.2f} Z0, Q = {q0:4.2f}, worst {rob:4.2f} | l = 0: Q = {q00:4.2f}, worst {rob0:4.2f}")
    print("  (c) time domain, switch-node deviation after the step (units of I0*Z0); |v| after 1 and 3 ring periods")
    T0 = 2 * math.pi
    t, y = ring_time_domain(1, 0, 0, snub=False)
    print(f"      no snubber:                 first peak {y.max():5.3f}, after 1 period {np.abs(y[t > T0]).max():6.4f},"
          f" after 3 {np.abs(y[t > 3*T0]).max():6.4f}")
    for (n, ell) in ((1, 0.0), (1, 0.93), (3, 0.0), (3, 0.32), (3, 1.0)):
        r, _ = best_r(n, ell)
        t, y = ring_time_domain(n, ell, r)
        print(f"      n = {n}, l = {ell:4.2f}, R_s = {r:4.2f}: first peak {y.max():5.3f}, after 1 period"
              f" {np.abs(y[t > T0]).max():6.4f}, after 3 {np.abs(y[t > 3*T0]).max():6.4f}")
    print("  (d) emission proxy vs Q (n = 3, l = 0, R_s swept): loop-current spectral peak relative to Q_cu = 50")
    pts = []
    for r in (0.02, 0.05, 0.1, 0.2, 0.5, 0.92):
        q = worst_q(3, 0.0, r)
        pk, _ = loop_current_peak(3, 0.0, r)
        pts.append((q, 20 * math.log10(pk / base_pk)))
    print("      " + "; ".join(f"Q {q:5.1f}: {d:6.1f} dB" for q, d in pts))
    qa, da = pts[0]
    qb, db = pts[3]
    print(f"      slope between Q {qa:.0f} and {qb:.1f}: {(da-db)/math.log10(qa/qb):.1f} dB per decade of Q")
    print("  (e) price of damping, 12 V / 10 A / 500 kHz buck, L_loop 1 nH, C_oss 1 nF (f_ring 159 MHz, Z0 1 ohm):")
    V, I, f, L, C = 12.0, 10.0, 5e5, 1e-9, 1e-9
    print(f"      unavoidable turn-off energy 1/2 L I^2 f = {0.5*L*I*I*f*1e3:.0f} mW, 1/2 C_oss V^2 f = {0.5*C*V*V*f*1e3:.0f} mW")
    for n, ell in ((3, 0.0), (1, 0.93), (3, 1.0)):
        r, q = best_r(n, ell)
        print(f"      snubber n = {n} (C_s {n*C*1e9:.0f} nF), L_s = {ell*L*1e9:4.2f} nH, R_s = {r*1.0:4.2f} ohm: Q {q:4.2f},"
              f" loss C_s V^2 f = {n*C*V*V*f*1e3:5.0f} mW")


# --------------------------------------------------------------------------
# cavity: fe_cavity modal model with resistive edge terminations
# --------------------------------------------------------------------------
CAV_A, CAV_B = 100e-3, 80e-3
PROBE = np.array([[12e-3, 9e-3]])


def edge_points(p, inset=0.5e-3):
    pts = []
    for x in np.arange(p / 2, CAV_A, p):
        pts += [(x, inset), (x, CAV_B - inset)]
    for y in np.arange(p / 2, CAV_B, p):
        pts += [(inset, y), (CAV_A - inset, y)]
    return np.array(pts)


def cavity_curve(d, tand, freqs, term=None, modes=24):
    fc.TAND = tand
    cav = fc.Cavity(CAV_A, CAV_B, d, modes, modes)
    pts = PROBE if term is None else np.vstack([PROBE, term[0]])
    phi = cav.phi(pts)
    out = np.empty(len(freqs))
    for i, f in enumerate(freqs):
        z = cav.Z(phi, f)
        if term is not None:
            w = 2 * math.pi * f
            zl = term[1] + 1j * w * term[2] + 1 / (1j * w * term[3])
            zps, zss = z[:1, 1:], z[1:, 1:]
            z = z[:1, :1] - zps @ np.linalg.solve(zss + zl * np.eye(zss.shape[0]), zps.T)
        out[i] = abs(z[0, 0])
    return out


def peak_of(z):
    idx = [k for k in range(1, len(z) - 1) if z[k] > z[k - 1] and z[k] >= z[k + 1]]
    return max(z[idx]) if idx else float(z.max())


def exp_cavity():
    print("== cavity: PWR-GND plane pair 100 x 80 mm, probe at (12, 9) mm, eps_r 4.3 (fe_cavity.py model)")
    freqs = np.linspace(0.3e9, 2.5e9, 441)
    d1 = skin_depth(0.72e9)
    print("  (a) peak |Z| over 0.3-2.5 GHz vs spacing d; Q of the first mode (0.72 GHz) = 1/(tan d + delta/d)")
    ds = (0.025e-3, 0.05e-3, 0.1e-3, 0.2e-3, 0.4e-3, 0.8e-3, 1.5e-3)
    print("      d (mm):          " + "".join(f"{d*1e3:>9.3f}" for d in ds))
    for tand in (0.02, 0.004):
        pk = [peak_of(cavity_curve(d, tand, freqs)) for d in ds]
        qs = [1 / (tand + d1 / d) for d in ds]
        print(f"      tan d {tand:5.3f} |Z|pk: " + "".join(f"{p:9.3f}" for p in pk) + " ohm")
        print(f"                 Q1:   " + "".join(f"{q:9.1f}" for q in qs))
        slopes = [math.log(pk[i + 1] / pk[i]) / math.log(ds[i + 1] / ds[i]) for i in range(len(ds) - 1)]
        print("                 local exponent of |Z|pk vs d: " + " ".join(f"{s:4.2f}" for s in slopes))
    print("  (b) RC terminations (C_b 10 nF) every p = 10 mm along all edges (36 parts); R in units of the matched")
    print("      R_m = eta0 d/(sqrt(er) p); with ideal parts and with 0.5 nH mounting ESL each. Peak |Z| (ohm):")
    eta0 = math.sqrt(MU0 / EPS0)
    freqs_b = np.linspace(0.3e9, 2.0e9, 341)
    for tand in (0.02, 0.004):
        for d in (0.1e-3, 0.4e-3):
            bare = peak_of(cavity_curve(d, tand, freqs_b))
            pts = edge_points(10e-3)
            rm = eta0 * d / (math.sqrt(fc.ER) * 10e-3)
            cells = []
            for mult in (0.25, 1.0, 4.0):
                for lesl in (0.0, 0.5e-9):
                    z = peak_of(cavity_curve(d, tand, freqs_b, (pts, mult * rm, lesl, 10e-9)))
                    cells.append(f"{mult:4.2f}R_m/{lesl*1e9:.1f}nH {z:6.3f}")
            print(f"      tan d {tand:5.3f}, d {d*1e3:3.1f} mm, R_m {rm:5.2f} ohm: bare {bare:6.3f} -> " + "; ".join(cells))
    print("  ESL limit: a termination works while w L_esl < R_m, i.e. pitch p < eta0 d/(sqrt(er) w L_esl):")
    for d in (0.1e-3, 0.4e-3):
        pmax = eta0 * d / (math.sqrt(fc.ER) * 2 * math.pi * 1e9 * 0.5e-9)
        print(f"      d {d*1e3:3.1f} mm, 0.5 nH, 1 GHz: p < {pmax*1e3:4.1f} mm")


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    for name, fn in (("qcu", exp_qcu), ("snubber", exp_snubber), ("cavity", exp_cavity)):
        if which in (name, "all"):
            fn()
