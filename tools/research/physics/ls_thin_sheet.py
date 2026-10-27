# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The plane as a spatial low-pass filter: one length scale for the f_x transition (lens LS).

Used by docs/topics/physics/lens-ls.md.  Round 1 found two "mirror onset" laws for
copper planes (return localisation under a trace, f_x = R_s/(2 pi mu0 h), from
vo_return_spread.py; the plane mirroring a loop of size a above 1/(pi mu0 sigma t a),
from pw_eddy.py) and listed the transition between them as an open, Tier-1 gap
("neither image-plane PEEC nor DC Laplace models it").  This script checks that both
are one law and that the transition has a closed form for intact planes.

Physics (quasi-static, thin sheet t << skin depth, which holds below ~3.6 MHz for 1 oz
and is harmless above, where the sheet is already a near-perfect mirror):

* A field pattern with lateral wavenumber k above a sheet of sheet resistance R_s is
  reflected with Gamma(k, w) = 1 / (1 + k p),  p = 2 R_s / (j w mu0) = -j l_m,
  l_m(f) = R_s / (pi mu0 f) = delta^2 / t   (the thin-sheet limit of Dodd-Deeds).
  Features larger than l_m are mirrored, smaller ones are not: the plane is a spatial
  low-pass filter whose cut-off length falls as 1/f.  f_x is l_m = 2h; the loop onset is
  l_m = a.  Time domain: Maxwell's receding image, velocity w_s = 2 R_s / mu0.
* Closed forms tested against the exact spectral integral:
  - perfect image (Gamma = 1, today's image-plane PEEC);
  - one complex image at extra depth p (Gamma ~ exp(-k p), the complex-image method of
    earth-return and layered-media work);
  - N complex images from a contour-rotated Gauss-Laguerre rule (exact as N grows):
    Gamma ~ e^{j phi} sum_i w_i exp(-u_i (e^{j phi} - 1)) exp(-k p e^{j phi} u_i).
  Each image is an ordinary image at a complex depth, so existing image-PEEC formulas
  (ln terms, Maxwell's coaxial-loop mutual, Neumann integrals) carry over unchanged.
* "Thin-sheet Carson law": for h << l_m << plane width, the plane's return resistance per
  unit length tends to w mu0 / 4, independent of copper weight.

Cases: (A) a trace over its return plane (2-D, per unit length), compared with the
finite-width filament PEEC of vo_return_spread.py; (B) a go/return pair over a floating
plane (2-D), optionally compared with pw_xsec.py (--xsec, ~1 min); (C) a circular loop and
the pw_eddy.py air-coil over a sheet (3-D, Dodd-Deeds), compared with pw_eddy.py.

Run:  python ls_thin_sheet.py [--xsec]     (numpy + scipy; ~20 s without --xsec)
"""
import math
import os
import sys

import numpy as np
from scipy.special import j1

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pw_eddy  # noqa: E402  (round-1 Dodd-Deeds solver, reused for case C)

MU0 = 4e-7 * math.pi
RHO = 1.72e-8
mm = 1e-3
OZ = {0.5: 17.5e-6, 1: 35e-6, 2: 70e-6}

# log-spaced k grid: integrals are written as int g(k) dk/k = int g(e^u) du
U = np.linspace(math.log(1e-2), math.log(3e6), 60001)
KG = np.exp(U)


def rs(t):
    return RHO / t


def ell_m(f, t):
    """Magnetic resolution length of a thin sheet: R_s/(pi mu0 f) = delta^2/t."""
    return rs(t) / (math.pi * MU0 * f)


def p_of(f, t):
    return 2 * rs(t) / (1j * 2 * math.pi * f * MU0)


def gam_perfect(k, f, t):
    return np.ones_like(k, dtype=complex)


def gam_thin(k, f, t):
    return 1.0 / (1.0 + k * p_of(f, t))


def gam_dd(k, f, t, sigma=1 / RHO):
    """Finite-thickness Dodd-Deeds reflection (pw_eddy.gamma is -Gamma)."""
    return -pw_eddy.gamma(k, f, t, sigma)


def gam_cimg1(k, f, t):
    return np.exp(-k * p_of(f, t))


def make_gam_gl(n, phi=math.pi / 4, beta=1.0):
    """N complex images from 1/(1+kp) = (e/beta) int_0^inf exp(-s e z / beta) ds, z = 1 + kp, e = e^{j phi},
    on Gauss-Laguerre nodes.  Image i sits at complex extra depth p e u_i / beta with weight c_i."""
    u, w = np.polynomial.laguerre.laggauss(n)
    e = np.exp(1j * phi) / beta
    c = e * w * np.exp(-u * (e - 1.0))

    def g(k, f, t):
        p = p_of(f, t)
        out = np.zeros_like(k, dtype=complex)
        for ci, ui in zip(c, u):
            out += ci * np.exp(-k * p * e * ui)
        return out
    g.__name__ = f"gl{n}"
    return g


# 8 images on the plain 45-degree ray need no tuning; 4 and 6 images use (phi, beta) chosen by a grid search on
# cases A and B (20 deg / 25 deg, beta 2) and are tested out of sample on the 3-D coil of case C.
GL8 = make_gam_gl(8)
GL4T = make_gam_gl(4, math.radians(20), 2.0)
GL6T = make_gam_gl(6, math.radians(25), 2.0)
VARIANTS = [("perfect image", gam_perfect), ("thin exact", gam_thin), ("1 complex image", gam_cimg1),
            ("4 images tuned", GL4T), ("6 images tuned", GL6T), ("8 images 45deg", GL8)]


def sinc(x):
    return np.sinc(x / math.pi)


# ---------------------------------------------------------------- case A: trace over its return plane
def trace_z(f, h, w, t, gam):
    """Plane-related loop impedance per metre of a strip (width w, centre height h) over its return sheet:
    Z' - R'_trace = j w (mu0/2pi) int |F|^2 (1 - e^{-2kh} Gamma) dk/k."""
    F2 = sinc(KG * w / 2) ** 2
    g = F2 * (1 - np.exp(-2 * KG * h) * gam(KG, f, t))
    integral = np.trapezoid(g, U)
    return 1j * 2 * math.pi * f * MU0 / (2 * math.pi) * integral


def frac_within(f, h, w, X, t, gam):
    """|share of the return current within +-X of the trace centre|."""
    F = sinc(KG * w / 2)
    g = F * np.exp(-KG * h) * gam(KG, f, t) * np.sin(KG * X)
    return abs(2 / math.pi * np.trapezoid(g, U))


def crossing(fs, ys, level):
    ys = np.asarray(ys)
    i = int(np.argmax(ys >= level))
    if ys[i] < level or i == 0:
        return float("nan")
    a, b = math.log10(fs[i - 1]), math.log10(fs[i])
    return 10 ** (a + (level - ys[i - 1]) * (b - a) / (ys[i] - ys[i - 1]))


def case_a():
    print("== A. trace over its return plane (2-D, infinite plane, uniform strip current)")
    print("   l_m(f) = R_s/(pi mu0 f) = delta^2/t, 1 oz: "
          + ", ".join(f"{f:.0e} Hz: {ell_m(f, OZ[1])/mm:.3g} mm" for f in (1e3, 1e4, 1e5, 1e6)))
    t = OZ[1]
    fs = np.logspace(3, 7.5, 91)
    print("   return share within +-3h; source = filament at centre height h + t over the plane mid-plane, as in")
    print("   vo_return_spread.py (whose trace is one filament; its plane is 50 mm wide and meshed)")
    print("     h      50% at      70% at     | vo_return_spread: 50% / 70%       | l_m/h at 50%, 70% | HF limit (strip 0.3 mm)")
    ref = {0.1: (0.31e6, 1.2e6), 0.2: (0.14e6, 0.43e6), 1.6: (18e3, 46e3)}
    for h in (0.1, 0.2, 1.6):
        fr = [frac_within(f, h * mm + t, 1e-7, 3 * h * mm, t, gam_thin) for f in fs]
        f50, f70 = crossing(fs, fr, 0.5), crossing(fs, fr, 0.7)
        r50, r70 = ref[h]
        hf_strip = frac_within(1e9, h * mm + t, 0.3 * mm, 3 * h * mm, t, gam_perfect)
        print(f"   {h:4.1f} mm  {f50/1e3:8.1f} kHz {f70/1e3:8.1f} kHz |  {r50/1e3:7.1f} / {r70/1e3:7.1f} kHz"
              f" (ratio {f50/r50:4.2f}, {f70/r70:4.2f}) | {ell_m(f50, t)/(h*mm):5.2f}, {ell_m(f70, t)/(h*mm):5.2f}"
              f"        | {hf_strip:.3f}")
    print("   collapse check (filament, w -> 0): share within +-3h depends only on l_m/h")
    for lm_over_h in (10, 3, 1, 0.3, 0.1):
        vals = []
        for h in (0.1, 0.2, 1.6):
            f = rs(t) / (math.pi * MU0 * lm_over_h * h * mm)
            vals.append(frac_within(f, h * mm, 1e-7, 3 * h * mm, t, gam_thin))
        print(f"     l_m/h = {lm_over_h:5.1f}: share = " + ", ".join(f"{v:.4f}" for v in vals)
              + f"   (HF limit (2/pi)atan3 = {2/math.pi*math.atan(3):.4f})")
    print("   loop impedance of a 0.3 mm trace, h = 0.1 mm, 1 oz plane: L' (nH/mm) and plane R' (mOhm/mm)")
    hdr = "     f        " + "".join(f"{n:>22s}" for n, _ in VARIANTS)
    print(hdr)
    errs = {n: [0.0, 0.0] for n, _ in VARIANTS}
    for f in (1e4, 3e4, 1e5, 3e5, 1e6, 3e6, 1e7):
        ex = trace_z(f, 0.1 * mm + t, 0.3 * mm, t, gam_thin)
        row = f"   {f:8.0e}  "
        for n, g in VARIANTS:
            z = trace_z(f, 0.1 * mm + t, 0.3 * mm, t, g)
            L = z.imag / (2 * math.pi * f) * 1e9 / 1e3
            R = z.real * 1e3 / 1e3
            row += f"   {L:6.4f} / {R:8.5f}"
            Lx = ex.imag / (2 * math.pi * f)
            errs[n][0] = max(errs[n][0], abs(z.imag / (2 * math.pi * f) - Lx) / Lx)
            errs[n][1] = max(errs[n][1], abs(z.real - ex.real) / max(abs(ex.real), 1e-30))
        print(row)
    print("   max relative error vs thin exact, 10 kHz-10 MHz:  " +
          "; ".join(f"{n}: L {e[0]*100:.1f}%, R {e[1]*100:.0f}%" for n, e in errs.items() if n != "thin exact"))
    # finite thickness check at the same points
    worst = 0.0
    for f in (1e5, 1e6, 3e6, 1e7):
        a = trace_z(f, 0.1 * mm + t, 0.3 * mm, t, gam_thin)
        b = trace_z(f, 0.1 * mm + t, 0.3 * mm, t, gam_dd)
        worst = max(worst, abs(a.imag - b.imag) / abs(b.imag))
    print(f"   thin-sheet vs finite-thickness Dodd-Deeds reflection, L' over 0.1-10 MHz: max {worst*100:.2f}% apart")
    print("   thin-sheet Carson law: plane R' / (w mu0/4) for h = 0.1 mm, w = 0.3 mm (-> 1 for h << l_m << width)")
    for oz, tt in OZ.items():
        cells = []
        for f in (1e3, 1e4, 1e5, 1e6):
            z = trace_z(f, 0.1 * mm + tt, 0.3 * mm, tt, gam_thin)
            cells.append(f"{f:.0e} Hz {z.real/(2*math.pi*f*MU0/4):5.3f}")
        print(f"     {oz:3} oz: " + ", ".join(cells))
    print(f"     w mu0/4 = {2*math.pi*1e6*MU0/4:.3f} Ohm/m (= mOhm/mm) per MHz of frequency; trace R' (0.3 mm, 1 oz) "
          f"= {RHO/(0.3*mm*OZ[1]):.2f} mOhm/mm; HF plane limit ~ R_s/(2 pi h) = {rs(OZ[1])/(2*math.pi*(0.1*mm+OZ[1])):.2f} mOhm/mm")


# ---------------------------------------------------------------- case B: go/return pair over a floating plane
def pair_dz(f, h, w, s, t, gam):
    """Change of loop impedance per metre caused by the plane: j w L'_img,
    L'_img = -(mu0/pi) int |F|^2 (1 - cos ks) e^{-2kh} Gamma dk/k."""
    F2 = sinc(KG * w / 2) ** 2
    g = F2 * (1 - np.cos(KG * s)) * np.exp(-2 * KG * h) * gam(KG, f, t)
    return 1j * 2 * math.pi * f * (-MU0 / math.pi) * np.trapezoid(g, U)


def pair_free_L(w, s):
    F2 = sinc(KG * w / 2) ** 2
    return MU0 / math.pi * np.trapezoid(F2 * (1 - np.cos(KG * s)), U)


def case_b(run_xsec):
    print("== B. go/return pair over a floating plane (2-D): pw_xsec 'side + floating plane' geometry")
    t = OZ[1]
    w, gap, h = 2 * mm, 0.5 * mm, 0.1 * mm
    s, hc = w + gap, h + t
    L0 = pair_free_L(w, s)
    print(f"   free pair (uniform strips) L' = {L0*1e9/1e3:.4f} nH/mm  (pw_xsec at 1 kHz: 0.66 nH/mm, thick traces)")
    print("     f        " + "".join(f"{n:>18s}" for n, _ in VARIANTS) + "    L' total, nH/mm (thin exact)")
    errs = {n: 0.0 for n, _ in VARIANTS}
    rows = []
    for f in (1e3, 1e4, 3e4, 1e5, 3e5, 1e6, 1e7):
        ex = pair_dz(f, hc, w, s, t, gam_thin)
        row = f"   {f:8.0e}  "
        for n, g in VARIANTS:
            dz = pair_dz(f, hc, w, s, t, g)
            dl = dz.imag / (2 * math.pi * f)
            row += f"   {(L0+dl)*1e9/1e3:6.4f}/{dz.real*1e3/1e3*1e3:6.2f}"
            errs[n] = max(errs[n], abs((L0 + dl) - (L0 + ex.imag / (2 * math.pi * f))) / (L0 + ex.imag / (2 * math.pi * f)))
        tot = (L0 + ex.imag / (2 * math.pi * f)) * 1e9 / 1e3
        rows.append((f, tot))
        print(row + f"    {tot:.4f}")
    print("   (cells: L' nH/mm / eddy R' uOhm/mm)  max L' error vs thin exact: "
          + "; ".join(f"{n} {e*100:.1f}%" for n, e in errs.items() if n != "thin exact"))
    if run_xsec:
        import pw_xsec
        nt = 10
        trace = lambda y0, z0: pw_xsec.rect(y0, y0 + w, z0, z0 + t, 40, nt, 2.0, 1.0)
        ey = np.concatenate([np.linspace(-6, -1, 11)[:-1], np.linspace(-1, 5.5, 196)[:-1], np.linspace(5.5, 10.5, 11)]) * mm
        ez = np.linspace(-0.1 * mm - t, -0.1 * mm, nt + 1)
        fplane = [((ey[i] + ey[i + 1]) / 2, (ez[j] + ez[j + 1]) / 2, ey[i + 1] - ey[i], ez[j + 1] - ez[j])
                  for i in range(len(ey) - 1) for j in range(nt)]
        conds = [trace(0, 0), trace(w + gap, 0), fplane]
        lx = {}
        for f in (1e3, 1e4, 3e4, 1e5, 3e5, 1e6, 1e7):
            zp, *_ = pw_xsec.solve(conds, [1, -1, 0], f)
            lx[f] = zp.imag / (2 * math.pi * f)
        mine = {f: L0 + pair_dz(f, hc, w, s, t, gam_thin).imag / (2 * math.pi * f) for f in lx}
        lperf = L0 + pair_dz(1e6, hc, w, s, t, gam_perfect).imag / (2 * math.pi * 1e6)
        print("   pw_xsec cross-check (thick traces with proximity effect, finite 16.5 mm plane, filament PEEC):")
        print("     transition shape r(f) = (L'(f) - L'(HF)) / (L'(LF) - L'(HF)); pw_xsec uses its own 1 kHz and 10 MHz values")
        for f in (1e4, 3e4, 1e5, 3e5, 1e6):
            rx = (lx[f] - lx[1e7]) / (lx[1e3] - lx[1e7])
            rm = (mine[f] - lperf) / (mine[1e3] - lperf)
            print(f"     {f:8.0e} Hz: pw_xsec L' {lx[f]*1e6:.4f} nH/mm, r = {rx:.3f} | thin-sheet k-space L' {mine[f]*1e6:.4f}, r = {rm:.3f}")


# ---------------------------------------------------------------- case C: loops (3-D)
KL = np.exp(np.linspace(math.log(1e0), math.log(4e6), 40001))
UL = np.log(KL)


def loop_dz(f, a, h, t, gam):
    """Impedance change of a filament loop (radius a, height h) over the sheet:
    dZ = -j w mu0 pi a^2 int J1(ka)^2 e^{-2kh} Gamma dk."""
    g = j1(KL * a) ** 2 * np.exp(-2 * KL * h) * gam(KL, f, t) * KL
    return -1j * 2 * math.pi * f * MU0 * math.pi * a * a * np.trapezoid(g, UL)


def coil_dz(loops, f, t, gam):
    tot = 0j
    for ai, zi in loops:
        for aj, zj in loops:
            g = j1(KL * ai) * j1(KL * aj) * np.exp(-KL * (zi + zj)) * gam(KL, f, t) * KL
            tot += ai * aj * np.trapezoid(g, UL)
    return -1j * 2 * math.pi * f * MU0 * math.pi * tot


def case_c():
    print("== C. loops over a sheet (3-D)")
    t = OZ[1]
    print("   universal curve: mirrored fraction eta = dL(f)/dL(perfect) of a filament loop vs a/l_m(f)")
    print("     a, h (mm)     a/l_m at eta=0.5   eta at a/l_m = 0.3 / 1 / 3 / 10 / 30")
    for a, h in ((1, 0.1), (3, 0.1), (10, 0.1), (3, 0.5), (3, 1.6), (10, 1.6)):
        a_, h_ = a * mm, h * mm
        dperf = loop_dz(1e6, a_, h_, t, gam_perfect).imag / (2 * math.pi * 1e6)

        def eta(x):
            f = rs(t) * x / (math.pi * MU0 * a_)  # a/l_m = x
            return loop_dz(f, a_, h_, t, gam_thin).imag / (2 * math.pi * f) / dperf
        xs = np.logspace(-1.5, 2, 36)
        es = [eta(x) for x in xs]
        x50 = crossing(xs, es, 0.5)
        print(f"     {a:4.1f}, {h:4.1f}        {x50:6.2f}             " + " / ".join(f"{eta(x):.3f}" for x in (0.3, 1, 3, 10, 30)))
    print("   round-1 air-coil (pw_eddy.coil, 1.5-3.0 mm radii, 0.5-3.5 mm above the board), dL/L_air in %:")
    print("     plane depth  f        pw_eddy(finite t)   thin exact   1 complex image   4 images tuned   6 images tuned   perfect")
    for depth in (0.0, 0.1 * mm, 1.6 * mm):
        loops = pw_eddy.coil(1.5 * mm, 3.0 * mm, 0.5 * mm + depth, 3.5 * mm + depth)
        L0 = pw_eddy.self_L(loops)
        for f in (1e5, 5e5, 2e6):
            w = 2 * math.pi * f
            ref = pw_eddy.dZ(loops, f, t).imag / w / L0
            vals = [coil_dz(loops, f, t, g).imag / w / L0 for g in (gam_thin, gam_cimg1, GL4T, GL6T, gam_perfect)]
            print(f"     {depth/mm:4.1f} mm  {f:7.0e}      {ref*100:+7.2f}         " + "      ".join(f"{v*100:+7.2f}" for v in vals))


def receding():
    print("== D. receding image (time domain): w_s = 2 R_s/mu0; shielding of a pattern of size a holds for t < a/w_s")
    for oz, t in OZ.items():
        ws = 2 * rs(t) / MU0
        print(f"   {oz:3} oz: w_s = {ws:6.0f} m/s; hold time for h = 0.1 mm image: {0.1*mm/ws*1e9:5.0f} ns; "
              f"5 mm loop: {5*mm/ws*1e6:5.2f} us; 50 mm board: {50*mm/ws*1e6:6.1f} us")
    print(f"   signal speed in FR-4 / w_s(1 oz) = {3e8/math.sqrt(4.3)/(2*rs(OZ[1])/MU0):.2e}  "
          f"(= eta0/(2 R_s sqrt(er)); eta0/R_s = {376.73/rs(OZ[1]):.2e})")


if __name__ == "__main__":
    receding()
    case_a()
    case_b("--xsec" in sys.argv)
    case_c()
