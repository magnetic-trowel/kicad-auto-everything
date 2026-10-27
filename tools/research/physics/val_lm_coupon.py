# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Registered predictions for the l_m (R-L band) coupon of the validation program.

Used by docs/topics/physics/validation-coupons.md (coupon LM). The coupon separates two
competing predictions for where a trace's return current flows at low frequency:

  round 1  one crossover f_x = R_s/(2 pi mu0 h): below it the return spreads uniformly over
           the plane, above it the return sits under the trace; the switch depends on h;
  round 2  a length band (lenses VP, SY, LS): a pattern of size l is mirrored once
           f >~ R_s/(pi mu0 l), whatever h. The plane current at a lateral offset x first
           RISES above its DC value (the return gathers toward the trace) and the
           frequencies involved are set by x, the plane width W and R_s, not by h.

Coupon: one 1.0 mm trace centred over a 40 mm plane lane, 140 mm long, driven at one end,
shorted to the plane at the other. Kelvin sense via pairs on the plane at lateral offsets
x = 1.5-18 mm, 50 mm apart along the trace in the uniform middle region. Sense traces run
0.12 mm from the plane (thin sense loops). Lanes on a JLC04161H-3313 board (prepreg
0.0994 mm, core 1.265 mm, inner copper 15.2 um, outer 35 um):
  A   trace L1 over the L2 plane (h 0.099 mm, 0.5 oz plane), sense traces on L1
  B   trace L1 over the L3 plane, L2 removed in the lane (h 1.38 mm), sense traces on L4
  A'  lane A ordered with 1 oz inner copper (optional second order: R_s scaling)

Prediction: the measured Kelvin voltage per amp, including the sense loop's inductive pickup
(a voltage budget must name its loop, lenses CT and SY):
  V/I = -dz [ R_s K(x)/I + j w (A_z(x, 0) - A_z(x, y_s))/I ]
from the 2-D quasi-static PEEC cross-section of vp_rl_band.py (reused). Registered
observables: |V(x, f)|/|V(x, DC)| on a frequency grid; f_peak(x), the frequency of the
maximum of that ratio near the trace; f_half(x) far from it; and the lane ratio B/A.
Intervals: corners of copper thickness (+-15 %), dielectric thickness (+-10 %) and a
coarser plane mesh. Round 1's f_x is printed for each lane for contrast.

Run:  python tools/research/physics/val_lm_coupon.py      (numpy + scipy, ~30 s)
"""
import math
import os
import sys

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
import numpy as np  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vp_rl_band as vp  # noqa: E402  (round-2 VP cross-section PEEC, reused)

MU0 = 4e-7 * math.pi
RHO = 1.72e-8
MM = 1e-3
PREPREG, CORE, T_IN, T_OUT = 0.0994 * MM, 1.265 * MM, 15.2e-6, 35e-6
W_PLANE, W_TRACE, DZ = 40 * MM, 1.0 * MM, 50 * MM
OFFSETS = (1.5 * MM, 3 * MM, 6 * MM, 12 * MM, 18 * MM)
FREQS = np.logspace(1, 6.5, 67)
REPORT_F = (1e3, 3e3, 1e4, 3e4, 1e5, 3e5)
_EDGES = vp.plane_edges

# lane: (name, dielectric between trace and plane, plane thickness, sense-trace centre height (plane mid = 0))
LANES = [
    ("A  L1 over L2, h 0.10 mm, 0.5 oz", PREPREG, T_IN, +(T_IN / 2 + PREPREG + T_OUT / 2)),
    ("B  L1 over L3, h 1.38 mm, 0.5 oz", PREPREG + T_IN + CORE, T_IN, -(T_IN / 2 + PREPREG + T_OUT / 2)),
    ("A' as A with 1 oz inner (option)", PREPREG, T_OUT, +(T_OUT / 2 + PREPREG + T_OUT / 2)),
]


def mean_log_point(xp, yp, xc, a):
    """Mean of ln sqrt((xp - t)^2 + yp^2) for t uniform on [xc - a/2, xc + a/2] (exact)."""
    yy = abs(yp)

    def prim(u):
        if yy == 0.0:
            return np.where(u != 0, u * np.log(np.abs(np.where(u != 0, u, 1.0))) - u, 0.0)
        return 0.5 * (u * np.log(u * u + yy * yy) - 2 * u + 2 * yy * np.arctan(u / yy))
    return (prim(xc + a / 2 - xp) - prim(xc - a / 2 - xp)) / a


def build_lane(h, t_plane, coarse=False):
    """Cross-section: trace (1 mm, 8 strips) at the centre height hc above the plane mid-plane."""
    vp.RS = RHO / t_plane
    if coarse:
        vp.plane_edges = lambda width, hh, n_fine=96, n_coarse=84, fine_half=8.0: _EDGES(width, hh, 96, 84, fine_half)
    try:
        hc = h + t_plane / 2 + T_OUT / 2
        x, grp, r, lm = vp.build(hc, W_TRACE, W_PLANE, n_tr=8)
        e = vp.plane_edges(W_PLANE, hc)
    finally:
        vp.plane_edges = _EDGES
    return dict(hc=hc, x=x, grp=grp, r=r, lm=lm, xc=(e[1:] + e[:-1]) / 2, a=np.diff(e), rs=RHO / t_plane)


def sense_voltage(f, m, y_s, xs_sense):
    """Complex V/I (ohm) of each 50 mm Kelvin pair."""
    cur, _ = vp.solve(max(f, 1e-3), m["x"], m["grp"], m["r"], m["lm"], {0: 1.0, 1: -1.0})
    tp, pp = np.flatnonzero(m["grp"] == 0), np.flatnonzero(m["grp"] == 1)
    ip, xc, a = cur[pp], m["xc"], m["a"]
    k = ip / a
    at = np.full(len(tp), W_TRACE / len(tp))
    w = 2 * math.pi * f
    out = []
    for xs in xs_sense:
        kk = np.interp(xs, xc, k.real) + 1j * np.interp(xs, xc, k.imag)
        az0 = np.sum(ip * mean_log_point(xs, 0.0, xc, a)) + np.sum(cur[tp] * mean_log_point(xs, m["hc"], m["x"][tp], at))
        azs = (np.sum(ip * mean_log_point(xs, y_s, xc, a))
               + np.sum(cur[tp] * mean_log_point(xs, m["hc"] - y_s, m["x"][tp], at)))
        flux = -(MU0 / (2 * math.pi)) * (az0 - azs)
        out.append(-DZ * (m["rs"] * kk + 1j * w * flux))
    return np.array(out)


def curves(h, t_plane, y_s, coarse=False):
    m = build_lane(h, t_plane, coarse)
    vs = np.array([sense_voltage(f, m, y_s, OFFSETS) for f in FREQS])
    return np.abs(vs) / np.abs(vs[0])[None, :], np.abs(vs[0])


def crossing(fs, y, level):
    i = int(np.argmax(y <= level))
    if y[i] > level or i == 0:
        return float("nan")
    a, b = math.log10(fs[i - 1]), math.log10(fs[i])
    return 10 ** (a + (level - y[i - 1]) * (b - a) / (y[i] - y[i - 1]))


def features(ratio):
    """f_peak and peak ratio for the near offsets; f_half for the far ones."""
    out = []
    for j, xs in enumerate(OFFSETS):
        y = ratio[:, j]
        # first local maximum above 1.02 (at MHz the sense loop's own pickup rises again, so not the global one)
        cand = [i for i in range(1, len(FREQS) - 1) if y[i] >= y[i - 1] and y[i] > y[i + 1] and y[i] > 1.02]
        k = cand[0] if cand else 0
        if k:
            # parabolic refinement in log f
            l0, l1, l2 = np.log10(FREQS[k - 1:k + 2])
            y0, y1, y2 = y[k - 1:k + 2]
            den = y0 - 2 * y1 + y2
            dl = 0.5 * (y0 - y2) / den * (l1 - l0) if den != 0 else 0.0
            out.append(("peak", 10 ** (l1 + dl), y1))
        else:
            out.append(("half", crossing(FREQS, y, 0.5), None))
    return out


def interp_ratio(ratio, f):
    return np.array([np.interp(math.log10(f), np.log10(FREQS), ratio[:, j]) for j in range(len(OFFSETS))])


def main():
    print("== l_m coupon: Kelvin plane voltage per amp (50 mm pairs), 40 mm plane lane, 1 mm trace")
    print("   registered: |V(x,f)|/|V(x,DC)|; f_peak (near offsets) and f_half (far offsets).")
    print("   round-1 picture: ratio stays ~1 until ~f_x, then falls at every offset (no rise).")
    res = {}
    for name, h, tp, y_s in LANES:
        ratio, dc = curves(h, tp, y_s)
        feats = features(ratio)
        corner_feats, corner_ratios = [], []
        for kr in (0.85, 1.15):
            for kh in (0.9, 1.1):
                rr, _ = curves(h * kh, tp / kr, y_s)
                corner_feats.append([v[1] for v in features(rr)])
                corner_ratios.append(rr)
        rr, _ = curves(h, tp, y_s, coarse=True)
        corner_feats.append([v[1] for v in features(rr)])
        corner_ratios.append(rr)
        cf = np.array(corner_feats, float)
        rs = RHO / tp
        fx = rs / (2 * math.pi * MU0 * (h + tp / 2))
        res[name] = (ratio, feats, cf, fx, corner_ratios)
        print(f"\n  lane {name}: R_s {rs*1e3:.3f} mOhm/sq; DC |V| = {dc[0]*1e3:.3f} mV per A"
              f" (R_s dz/W = {rs*DZ/W_PLANE*1e3:.3f}); round-1 f_x = {fx/1e3:.0f} kHz")
        print("     x (mm) | " + " | ".join(f"{f/1e3:6.0f} kHz" for f in REPORT_F) + " |  feature [interval]")
        at_f = [np.array([interp_ratio(c, f) for f in REPORT_F]) for c in corner_ratios]
        lo_r, hi_r = np.min(at_f, axis=0), np.max(at_f, axis=0)
        nom = np.array([interp_ratio(ratio, f) for f in REPORT_F])
        for j, xs in enumerate(OFFSETS):
            kind, fv, pk = feats[j]
            lo, hi = np.nanmin(cf[:, j]), np.nanmax(cf[:, j])
            ft = (f"f_peak {fv/1e3:6.1f} kHz [{lo/1e3:.1f}, {hi/1e3:.1f}], peak x{pk:.2f}" if kind == "peak"
                  else f"f_half {fv/1e3:6.1f} kHz [{lo/1e3:.1f}, {hi/1e3:.1f}]")
            cells = " | ".join(f"{nom[i, j]:4.2f}({lo_r[i, j]:.2f}-{hi_r[i, j]:.2f})"[:16].ljust(10) for i in range(len(REPORT_F)))
            print(f"     {xs/MM:5.1f}  | {cells} | {ft}")
    names = [n for n, *_ in LANES]
    fa_ = res[names[0]][1]
    print("\n== discrimination")
    fb = res[names[1]][1]
    print("   feature frequency, lane B / lane A (h 1.38 vs 0.10 mm): " +
          "; ".join(f"x {OFFSETS[j]/MM:.0f} mm {fb[j][1]/fa_[j][1]:.2f}" for j in range(2, len(OFFSETS)))
          + f"  (round 1: {res[names[1]][3]/res[names[0]][3]:.3f}, i.e. {res[names[0]][3]/res[names[1]][3]:.1f}x lower)")
    fa = res[names[0]][1]
    fpx = [(OFFSETS[j], fa[j][1]) for j in range(3) if fa[j][0] == "peak"]
    if fpx:
        print("   lane A near-trace rise: " + "; ".join(f"x {x/MM:.1f} mm f_peak {f/1e3:.1f} kHz (f_peak*x = {f*x:.0f} Hz m)"
                                               for x, f in fpx))
    print(f"   round 1 would put any change near f_x = {res[names[0]][3]/1e3:.0f} kHz (lane A) and"
          f" {res[names[1]][3]/1e3:.0f} kHz (lane B), with no rise")
    fa2 = res[names[2]][1]
    j = 3
    print(f"   R_s scaling (optional 1 oz order): f_half(12 mm) A/A' = {fa[j][1]/fa2[j][1]:.2f} (R_s ratio {T_OUT/T_IN:.2f})")
    print("\n== sense-loop gauge check, lane A, x = 12 mm: share of |V| that is inductive pickup")
    m = build_lane(PREPREG, T_IN)
    for f in (1e3, 1e4, 1e5, 1e6):
        v_all = sense_voltage(f, m, LANES[0][3], (12 * MM,))[0]
        v_res = sense_voltage(f, m, 0.0, (12 * MM,))[0]       # y_s = 0: no loop flux, resistive term only
        print(f"   {f:8.0e} Hz: |V| {abs(v_all)*1e6:8.2f} uV/A, resistive part {abs(v_res)*1e6:8.2f}, "
              f"pickup {abs(v_all - v_res)*1e6:7.2f}")


if __name__ == "__main__":
    main()
