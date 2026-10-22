# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Red-team re-derivation of the plane-return claims (lenses VP, SY, LS, TH; round-1 f_x).

Independent of vp_rl_band.py, ls_thin_sheet.py and sy_images_symmetry.py: different
formulation (closed-form spectral integrals evaluated with scipy.integrate.quad, QAWF for
the oscillatory tails) and an independently written 2-D PEEC for the finite plane.

Physics: a thin copper sheet (sheet resistance R_s) reflects a field pattern of lateral
wavenumber k with Gamma(k) = 1 / (1 - j |k| l_m), l_m = 2 R_s / (omega mu0) = R_s/(pi mu0 f)
(derived in the red-team doc from E = -j w A, K = E / R_s, A_sheet = mu0 K / (2|k|)).

Sections (python rt_sheet_return.py [contain|mirror|carson|finite|q|all]):
  contain  |share of the return within +-l| for a line current at height h over an infinite
           sheet; l50 / l_m vs h / l_m (VP: l50 = l_m / 2 "whatever h"); LS's +-3h shares;
           VP's "return beyond +-5 mm" at 20 kHz / 100 kHz.
  mirror   a 2-D go/return pair (separation a, height h) over the sheet: mirrored fraction
           eta = dL'(f) / dL'(perfect image). Where is eta = 1/2? (SY: "1 oz mirrors a 5 mm
           loop above 12 kHz", i.e. a = l_m/2; LS: half-mirroring at a/l_m = 1.3-4.5.)
  carson   return resistance of the sheet for h -> 0: omega mu0 / 4 (LS).
  finite   own 2-D PEEC of a 0.3 mm trace over a finite 1 oz plane of width W: f10/f50/f90 of
           the DC -> HF inductance drop for W = 50 and 100 mm (VP quotes 17/65/360 kHz).
  q        copper-loss Q(f) of wide plate pairs (slab surface impedance) and of 50-ohm
           microstrip (Wheeler incremental-inductance rule): where copper alone gives Q <= 1-5
           (TH: "copper can never be it").

Run: OMP_NUM_THREADS=1 python tools/research/physics/rt_sheet_return.py   (about 1 minute)
"""
import math
import sys
import warnings

import numpy as np
from scipy.integrate import IntegrationWarning, quad
from scipy.optimize import brentq

warnings.filterwarnings("ignore", category=IntegrationWarning)

MU0 = 4e-7 * math.pi
RHO = 1.72e-8
mm = 1e-3


def rs(t=35e-6):
    return RHO / t


def l_m(f, t=35e-6):
    return rs(t) / (math.pi * MU0 * f)


# ----------------------------------------------------------------------------- contain
def share_within(ell, h, lm):
    """Complex fraction of the sheet return current inside |x| <= ell (line current at height h).

    F = (2/pi) int_0^inf e^{-k h} sin(k ell) / (k (1 - j k lm)) dk,  1/(1 - j k lm) = (1 + j k lm)/(1 + k^2 lm^2).
    Head [0, K] by adaptive Gauss-Kronrod, tail by QAWF (Fourier weight).
    """
    def re_f(k):
        return math.exp(-k * h) / (1 + (k * lm) ** 2)          # times sin(k ell)/k

    def im_f(k):
        return math.exp(-k * h) * lm / (1 + (k * lm) ** 2)     # times sin(k ell)

    K = 60.0 / ell
    re_head = quad(lambda k: re_f(k) * (ell if k == 0 else math.sin(k * ell) / k), 0, K, limit=400)[0]
    re_tail = quad(lambda k: re_f(k) / k, K, np.inf, weight="sin", wvar=ell, limit=400)[0]
    im_head = quad(lambda k: im_f(k) * math.sin(k * ell), 0, K, limit=400)[0]
    im_tail = quad(im_f, K, np.inf, weight="sin", wvar=ell, limit=400)[0]
    return (2 / math.pi) * complex(re_head + re_tail, im_head + im_tail)


def sec_contain():
    print("== contain: share of the return within +-l of a line current over an infinite thin sheet")
    print("   closed check, h = 0: Re F = 1 - exp(-l/l_m) exactly")
    for c in (0.3, 1.0, 3.0):
        F = share_within(c, 1e-9, 1.0)
        print(f"     l/l_m = {c:3.1f}: Re F = {F.real:.5f} (exact {1-math.exp(-c):.5f}), |F| = {abs(F):.4f}")
    print("   l50 / l_m where |F| = 1/2, vs h / l_m (VP: l50 = l_m/2 'whatever h'; f50*l = 62 Hz m <=> l50/l_m = 0.5)")
    print("     h/l_m    l50/l_m    l50/h    f50*l50 for 1 oz (Hz m)")
    k_fl = rs() / (math.pi * MU0)       # l_m * f for 1 oz
    for hr in (0.0, 0.01, 0.03, 0.1, 0.3, 1.0):
        g = lambda c: abs(share_within(c, hr if hr > 0 else 1e-12, 1.0)) - 0.5  # noqa: E731
        c = brentq(g, 1e-4, 50.0, xtol=1e-6)
        print(f"     {hr:5.2f}   {c:8.4f}   {('%8.2f' % (c/hr)) if hr > 0 else '     inf'}   {c*k_fl:8.1f}")
    print("   the ratio l/h at which the law breaks: f50*l for l = 3h, 6h, 10h, 30h (h = 0.1-1.6 mm, 1 oz)")
    for h in (0.1 * mm, 0.5 * mm, 1.6 * mm):
        cells = []
        for m in (3, 6, 10, 30):
            ell = m * h
            g = lambda f: abs(share_within(ell, h, l_m(f))) - 0.5  # noqa: E731
            f50 = brentq(g, 1.0, 1e9, xtol=1e-3, rtol=1e-6)
            cells.append(f"l={m:2d}h: {f50*ell:5.1f}")
        print(f"     h = {h/mm:3.1f} mm: " + "  ".join(cells) + "  Hz m")
    print("   LS: share within +-3h collapses onto l_m/h (0.342 / 0.760 / 0.794 at l_m/h = 10 / 1 / 0.3)")
    for lr in (10.0, 1.0, 0.3):
        F = share_within(3.0, 1.0, lr)
        print(f"     l_m/h = {lr:4.1f}: |F| = {abs(F):.3f}, Re F = {F.real:.3f}")
    print("   VP: return outside +-5 mm (1 oz): '1.3% at h 0.1, 20% at h 1.6 mm at >= 100 kHz; 32-45% at 20 kHz'")
    for f in (20e3, 100e3, 500e3, 1e9):
        cells = []
        for h in (0.1 * mm, 1.6 * mm):
            F = share_within(5 * mm, h, l_m(f))
            cells.append(f"h {h/mm:3.1f} mm: |1-F| {abs(1-F)*100:5.1f}%, 1-|F| {(1-abs(F))*100:5.1f}%")
        print(f"     {f/1e3:8.0f} kHz: " + "; ".join(cells))


# ----------------------------------------------------------------------------- mirror
def mirror_fraction(a, h, lm):
    """eta = dL'(sheet)/dL'(perfect image) for a 2-D go/return pair (separation a) at height h.

    dL'(sheet) = -(2 mu0/pi) int e^{-2kh} sin^2(ka/2) / (k (1 + k^2 lm^2)) dk;  perfect: -(mu0/2pi) ln(1 + a^2/4h^2).
    """
    def f(k):
        return math.exp(-2 * k * h) / (k * (1 + (k * lm) ** 2))  # times sin^2(ka/2) = (1 - cos ka)/2

    K = 80.0 / a
    head = quad(lambda k: (math.exp(-2 * k * h) / (1 + (k * lm) ** 2)) * (a * a / 4 if k == 0 else
                math.sin(k * a / 2) ** 2 / k), 0, K, limit=600)[0]
    # tail: int f (1 - cos ka)/2 = 0.5 int f - 0.5 int f cos(ka)
    tail = 0.5 * quad(f, K, np.inf, limit=400)[0] - 0.5 * quad(f, K, np.inf, weight="cos", wvar=a, limit=400)[0]
    return (head + tail) / (0.25 * math.log(1 + a * a / (4 * h * h)))


def sec_mirror():
    print("== mirror: 2-D go/return pair (separation a, height h) over a thin sheet; eta = mirrored share of dL'")
    print("   check: lm -> 0 gives eta -> 1:", f"{mirror_fraction(10.0, 0.1, 1e-6):.4f}")
    for h_over_a in (0.01, 0.02, 0.1):
        print(f"   h/a = {h_over_a}:  a/l_m -> eta")
        cells = []
        for ar in (0.25, 0.5, 1.0, 2.0, 4.0, 10.0, 30.0):
            cells.append(f"{ar:5.2f}: {mirror_fraction(1.0, h_over_a, 1.0 / ar):.3f}")
        print("     " + "; ".join(cells))
        c = brentq(lambda ar: mirror_fraction(1.0, h_over_a, 1.0 / ar) - 0.5, 0.01, 1000.0, xtol=1e-4)
        c90 = brentq(lambda ar: mirror_fraction(1.0, h_over_a, 1.0 / ar) - 0.9, 0.01, 1e5, xtol=1e-3)
        print(f"     eta = 0.5 at a/l_m = {c:5.2f}; eta = 0.9 at a/l_m = {c90:6.1f}")
    a, h = 5 * mm, 0.1 * mm
    f_sy = rs() / (2 * math.pi * MU0 * a)    # SY: l_d = R_s/(w mu0) = a
    c = brentq(lambda ar: mirror_fraction(1.0, h / a, 1.0 / ar) - 0.5, 0.01, 1000.0, xtol=1e-4)
    f_half = c * rs() / (math.pi * MU0 * a)
    print(f"   SY's case, a = 5 mm, h = 0.1 mm, 1 oz: SY's 'mirrored above' {f_sy/1e3:.1f} kHz gives eta = "
          f"{mirror_fraction(a, h, l_m(f_sy)):.2f}; eta = 0.5 needs {f_half/1e3:.0f} kHz")


# ----------------------------------------------------------------------------- carson
def sec_carson():
    print("== carson: sheet return resistance R' = (R_s/pi) int e^{-2kh}/(1 + k^2 l_m^2) dk -> omega mu0/4 for h << l_m")
    for t in (17.5e-6, 35e-6, 70e-6):
        for f in (1e3, 1e4):
            lm = l_m(f, t)
            h = 0.1 * mm
            val = (rs(t) / math.pi) * quad(lambda k: math.exp(-2 * k * h) / (1 + (k * lm) ** 2), 0, np.inf, limit=400)[0]
            print(f"   t {t*1e6:4.1f} um, f {f/1e3:4.0f} kHz, h 0.1 mm: R' = {val*1e3:.4f} mOhm/m vs omega mu0/4 = "
                  f"{2*math.pi*f*MU0/4*1e3:.4f} mOhm/m (ratio {val/(2*math.pi*f*MU0/4):.3f}; l_m = {lm/mm:.1f} mm)")


# ----------------------------------------------------------------------------- finite
def mean_log_strips(xa, wa, xb, wb, dz, n=24):
    """Mean of ln(distance) between two parallel thin strips (centres xa, xb; widths wa, wb; vertical offset dz)."""
    g, wq = np.polynomial.legendre.leggauss(n)
    ua = xa + 0.5 * wa * g
    ub = xb + 0.5 * wb * g
    d2 = (ua[:, None] - ub[None, :]) ** 2 + dz * dz
    return float(np.sum(wq[:, None] * wq[None, :] * 0.5 * np.log(d2)) / 4.0)


def self_log_strip(w):
    """Mean of ln|u - v| over a thin strip of width w with itself: ln w - 3/2."""
    return math.log(w) - 1.5


def finite_plane_z(freqs, h, w, W, t_tr=35e-6, t_pl=35e-6, n_fine=90, n_out=60):
    """Loop impedance per unit length of a trace (thin strip w at height h) over a plane of width W (2-D PEEC)."""
    fine = np.linspace(-6 * h, 6 * h, n_fine + 1)
    outer = np.geomspace(6 * h, W / 2, n_out + 1)
    edges = np.concatenate([-outer[::-1], fine[1:-1], outer])
    xc = 0.5 * (edges[1:] + edges[:-1])
    wd = np.diff(edges)
    n = len(xc)
    # partial inductance matrix (per unit length), up to a common constant that cancels (zero net current)
    Lm = np.empty((n + 1, n + 1))
    for i in range(n):
        Lm[i, i] = -MU0 / (2 * math.pi) * self_log_strip(wd[i])
        for j in range(i + 1, n):
            d = abs(xc[i] - xc[j])
            if d > 8 * max(wd[i], wd[j]):
                ml = math.log(d)
            else:
                ml = mean_log_strips(xc[i], wd[i], xc[j], wd[j], 0.0)
            Lm[i, j] = Lm[j, i] = -MU0 / (2 * math.pi) * ml
        mlt = mean_log_strips(xc[i], wd[i], 0.0, w, h)
        Lm[i, n] = Lm[n, i] = -MU0 / (2 * math.pi) * mlt
    Lm[n, n] = -MU0 / (2 * math.pi) * math.log(0.2235 * (w + t_tr))
    R = np.concatenate([RHO / t_pl / wd, [RHO / (w * t_tr)]])
    out = []
    for f in freqs:
        Z = np.diag(R) + 1j * 2 * math.pi * f * Lm
        # unknowns: currents i (n plane strips + trace), plane voltage Vp, trace voltage Vt
        A = np.zeros((n + 3, n + 3), complex)
        b = np.zeros(n + 3, complex)
        A[:n + 1, :n + 1] = Z
        A[:n, n + 1] = -1.0          # plane strips: Z i = Vp
        A[n, n + 2] = -1.0           # trace: Z i = Vt
        A[n + 1, :n] = 1.0           # sum plane currents = -1
        b[n + 1] = -1.0
        A[n + 2, n] = 1.0            # trace current = +1
        b[n + 2] = 1.0
        sol = np.linalg.solve(A, b)
        out.append(sol[n + 2] - sol[n + 1])
    return np.array(out)


def sec_finite():
    print("== finite: own 2-D PEEC, 0.3 mm trace over a finite 1 oz plane; DC -> HF inductance drop band")
    freqs = np.logspace(1.5, 8.5, 113)
    for h, W in ((0.1 * mm, 50 * mm), (0.1 * mm, 100 * mm), (0.2 * mm, 50 * mm), (1.6 * mm, 50 * mm)):
        Z = finite_plane_z(freqs, h, 0.3 * mm, W)
        L = Z.imag / (2 * math.pi * freqs)
        drop = (L[0] - L) / (L[0] - L[-1])
        fx = rs() / (2 * math.pi * MU0 * h)
        cells = []
        for lev in (0.1, 0.5, 0.9):
            k = int(np.argmax(drop >= lev))
            fl = np.exp(np.interp(lev, drop[k - 1:k + 1], np.log(freqs[k - 1:k + 1])))
            cells.append(f"f{int(lev*100)} {fl/1e3:7.1f} kHz")
        print(f"   h {h/mm:3.1f} mm, W {W/mm:3.0f} mm: L'(DC) {L[0]*1e6:.3f}, L'(HF) {L[-1]*1e6:.3f} nH/mm; "
              + ", ".join(cells) + f"; f_x {fx/1e3:6.0f} kHz")


# ----------------------------------------------------------------------------- q
def q_plates(f, d, t):
    """Copper-loss Q of wide plates (gap d, thickness t each); slab surface impedance, field on one face."""
    w = 2 * math.pi * f
    delta = math.sqrt(2 * RHO / (w * MU0))
    g = (1 + 1j) / delta
    zs = g * RHO / np.tanh(g * t)
    return (w * MU0 * d + 2 * zs.imag) / (2 * zs.real)


def hj_lprime(w, h):
    """Hammerstad-Jensen air microstrip: L' = Z0_air / c (zero thickness)."""
    u = w / h
    fu = 6 + (2 * math.pi - 6) * math.exp(-((30.666 / u) ** 0.7528))
    z0 = 60.0 * math.log(fu / u + math.sqrt(1 + (2 / u) ** 2))
    return z0 / 299792458.0


def q_microstrip(f, w, h):
    """Wheeler incremental-inductance rule: R' = (R_s,ac/mu0) dL'/dn, surfaces recede by delta/2 (w-delta, h+delta)."""
    om = 2 * math.pi * f
    delta = math.sqrt(2 * RHO / (om * MU0))
    rsac = RHO / delta
    L0 = hj_lprime(w, h)
    dLdn = (hj_lprime(w - delta, h + delta) - L0) / (delta / 2)
    return om * L0 / (rsac / MU0 * dLdn)


def sec_q():
    print("== q: copper-loss Q of plate pairs (exact slab surface impedance), Q = h/delta only when delta << t")
    print("   d (um) t (um) |  Q at 1 MHz   3 MHz  10 MHz  30 MHz 100 MHz 300 MHz  1 GHz | f where Q = 1, 3, 10")
    for d in (25e-6, 50e-6, 100e-6, 200e-6, 1.5e-3):
        for t in (17.5e-6, 35e-6):
            qs = [q_plates(f, d, t) for f in (1e6, 3e6, 10e6, 30e6, 100e6, 300e6, 1e9)]
            fq = []
            for target in (1.0, 3.0, 10.0):
                try:
                    fq.append(brentq(lambda f: q_plates(f, d, t) - target, 1e3, 1e11))
                except ValueError:
                    fq.append(float("nan"))
            print(f"   {d*1e6:6.0f} {t*1e6:5.1f}  | " + " ".join(f"{q:7.2f}" for q in qs)
                  + " | " + ", ".join(f"{x/1e6:7.2f} MHz" for x in fq))
    print("   50-ohm-class microstrip (w = 2h), Wheeler rule vs h/delta (edge crowding):")
    for h in (0.1 * mm, 0.2 * mm):
        for f in (100e6, 300e6):
            delta = math.sqrt(2 * RHO / (2 * math.pi * f * MU0))
            print(f"     h {h/mm:3.1f} mm, {f/1e6:4.0f} MHz: Q_ms {q_microstrip(f, 2*h, h):6.1f} vs h/delta {h/delta:6.1f}"
                  f" (ratio {q_microstrip(f, 2*h, h)/(h/delta):.2f})")
    print("   microstrip Q / (h/delta) vs w/h (h 0.2 mm, 200 MHz; TH: 'edge crowding lowers Q up to ~2x'):")
    h, f = 0.2 * mm, 200e6
    delta = math.sqrt(2 * RHO / (2 * math.pi * f * MU0))
    print("     " + "; ".join(f"w/h {u:5.2f}: {q_microstrip(f, u*h, h)/(h/delta):4.2f}" for u in (0.25, 0.5, 1, 2, 5, 10, 30)))


SECTIONS = {"contain": sec_contain, "mirror": sec_mirror, "carson": sec_carson, "finite": sec_finite, "q": sec_q}

if __name__ == "__main__":
    which = sys.argv[1:] or ["all"]
    for name, fn in SECTIONS.items():
        if "all" in which or name in which:
            fn()
            print()
