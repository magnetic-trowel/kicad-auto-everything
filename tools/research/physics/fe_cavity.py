# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Plane-pair cavity model with shorting (stitching) vias and via fences.

Used by docs/topics/physics/fields-si-emi.md and rf-geometry.md ([C] numbers).

Model: rectangular plane pair a x b, separation d, open (PMC) edges, the classic
cavity-mode impedance matrix (Okoshi; Lei, Techentin & Gilbert 1999):
  Z_ij = (j w mu d / (a b)) sum_mn chi_m^2 chi_n^2 N_i N_j / (k_mn^2 - k^2),
  N_i = cos(k_m x_i) cos(k_n y_i) sinc(k_m w/2) sinc(k_n w/2),
with dielectric + conductor loss in k^2. Stitching vias are ports shorted to 0 ohm
(Schur complement). Questions answered:
  1. first resonance seen anywhere on a GND-GND plane pair vs via pattern
     (none, perimeter ring, distributed grids, random), compared with
     (a) the Belov wire-medium cut-off for square grids,
     (b) the "largest empty circle" metric (open edges handled by mirror images);
  2. isolation across a single via-fence row vs pitch, compared with the
     inductive-post closed form |T| = 2/sqrt(4 + B^2), B = lambda/(s ln(s/(2 pi r))).
Run:  python tools/research/physics/fe_cavity.py      (a few minutes on 4 cores)
"""
import math

import numpy as np
from scipy.spatial import Voronoi

MU0 = 4e-7 * math.pi
EPS0 = 8.854e-12
C0 = 1 / math.sqrt(MU0 * EPS0)
ER, TAND = 4.3, 0.02
VIA_R = 0.15e-3
PORT_W = 0.8 * 2 * VIA_R  # square port of roughly equal inductance


class Cavity:
    def __init__(self, a, b, d, M, N):
        self.a, self.b, self.d = a, b, d
        m = np.arange(M)[:, None]
        n = np.arange(N)[None, :]
        self.km = (m * math.pi / a) * np.ones_like(n)
        self.kn = (n * math.pi / b) * np.ones_like(m)
        chi = np.where(m == 0, 1.0, 2.0) * np.where(n == 0, 1.0, 2.0)
        self.k2 = (self.km ** 2 + self.kn ** 2).ravel()
        self.chi = chi.ravel()
        self.kmr, self.knr = self.km.ravel(), self.kn.ravel()

    def phi(self, pts):
        x, y = pts[:, 0:1], pts[:, 1:2]
        s = np.sinc(self.kmr * PORT_W / (2 * math.pi)) * np.sinc(self.knr * PORT_W / (2 * math.pi))
        return np.cos(self.kmr * x) * np.cos(self.knr * y) * s * np.sqrt(self.chi)

    def Z(self, Phi, f):
        w = 2 * math.pi * f
        delta = math.sqrt(2 / (w * MU0 * 5.8e7))
        k2 = w * w * MU0 * EPS0 * ER * (1 - 1j * (TAND + delta / self.d))
        g = 1.0 / (self.k2 - k2)
        return (1j * w * MU0 * self.d / (self.a * self.b)) * (Phi * g) @ Phi.T


def reduced_Z(cav, probes, shorts, freqs):
    pts = np.vstack([probes, shorts]) if len(shorts) else probes
    Phi = cav.phi(pts)
    P = len(probes)
    out = []
    for f in freqs:
        Z = cav.Z(Phi, f)
        if len(shorts):
            Zpp, Zps, Zss = Z[:P, :P], Z[:P, P:], Z[P:, P:]
            Z = Zpp - Zps @ np.linalg.solve(Zss, Zps.T)
        out.append(Z)
    return np.array(out)


def first_peak(freqs, zmag, need_rise=True):
    """First local maximum; with shorting vias |Z| starts small (inductive), so also
    require it to exceed 3x its low-frequency value. An open board starts capacitive."""
    for i in range(1, len(freqs) - 1):
        if zmag[i] > zmag[i - 1] and zmag[i] >= zmag[i + 1] and (not need_rise or zmag[i] > 3 * zmag[0]):
            return freqs[i]
    return float("nan")


def first_resonance(cav, probes, vias, fmax=13e9, coarse=0.25e9, fine=0.05e9):
    """Coarse scan for the first peak of max_i |Z_ii|, then refine around it."""
    freqs = np.arange(0.1e9, fmax, coarse)
    Z = reduced_Z(cav, probes, vias, freqs)
    zmax = np.max(np.abs(np.diagonal(Z, axis1=1, axis2=2)), axis=1)
    f1 = first_peak(freqs, zmax, need_rise=len(vias) > 0)
    if not np.isfinite(f1):
        return f1
    ff = np.arange(f1 - coarse, f1 + coarse + fine / 2, fine)
    Z = reduced_Z(cav, probes, vias, ff)
    zm = np.max(np.abs(np.diagonal(Z, axis1=1, axis2=2)), axis=1)
    return ff[int(np.argmax(zm))]


def largest_empty_circle(vias, a, b):
    """Largest empty circle with centre inside the board; open edges = mirror images."""
    if len(vias) == 0:
        return float("inf")
    mirrored = [vias]
    for (mx, my) in ((True, False), (False, True), (True, True)):
        for ex in ((0.0, a) if mx else (None,)):
            for ey in ((0.0, b) if my else (None,)):
                v = vias.copy()
                if ex is not None:
                    v[:, 0] = 2 * ex - v[:, 0]
                if ey is not None:
                    v[:, 1] = 2 * ey - v[:, 1]
                mirrored.append(v)
    allp = np.vstack(mirrored)
    vor = Voronoi(allp)
    best = 0.0
    cand = [vv for vv in vor.vertices if 0 <= vv[0] <= a and 0 <= vv[1] <= b]
    cand += [np.array([x, y]) for x in np.linspace(0, a, 41) for y in (0.0, b)]
    cand += [np.array([x, y]) for y in np.linspace(0, b, 31) for x in (0.0, a)]
    for c in cand:
        r = np.min(np.hypot(allp[:, 0] - c[0], allp[:, 1] - c[1]))
        best = max(best, r)
    return 2 * best


def grid(a, b, p, off=None):
    off = p / 2 if off is None else off
    xs = np.arange(off, a, p)
    ys = np.arange(off, b, p)
    return np.array([(x, y) for x in xs for y in ys])


def perimeter(a, b, p, inset=0.5e-3):
    pts = []
    for x in np.arange(inset, a, p):
        pts += [(x, inset), (x, b - inset)]
    for y in np.arange(inset + p, b - inset, p):
        pts += [(inset, y), (a - inset, y)]
    return np.array(pts)


def wire_medium_fp(p, r=VIA_R, er=ER):
    kp = math.sqrt(2 * math.pi / (math.log(p / (2 * math.pi * r)) + 0.5275)) / p
    return kp * C0 / (2 * math.pi * math.sqrt(er))


def main():
    a, b, d = 40e-3, 30e-3, 0.2e-3
    cav = Cavity(a, b, d, 120, 90)
    rng = np.random.default_rng(1)

    def probes_away(vias, n=10):
        pr = []
        while len(pr) < n:
            p = rng.uniform([1e-3, 1e-3], [a - 1e-3, b - 1e-3])
            if len(vias) == 0 or np.min(np.hypot(*(vias - p).T)) > 1.0e-3:
                pr.append(p)
        return np.array(pr)

    pats = {
        "none (open board)": np.zeros((0, 2)),
        "perimeter ring, 5 mm pitch": perimeter(a, b, 5e-3),
        "grid 10 mm": grid(a, b, 10e-3),
        "grid 7.5 mm": grid(a, b, 7.5e-3),
        "grid 5 mm": grid(a, b, 5e-3),
        "perimeter 5 mm + grid 10 mm": np.vstack([perimeter(a, b, 5e-3), grid(a, b, 10e-3)]),
    }
    for nvia in (12, 28, 48):
        for seed in range(2):
            r2 = np.random.default_rng(100 + seed)
            pats[f"random N={nvia} seed{seed}"] = r2.uniform([0.5e-3, 0.5e-3], [a - 0.5e-3, b - 0.5e-3], (nvia, 2))
    print(f"Board {a*1e3:.0f} x {b*1e3:.0f} mm, d = {d*1e3:.1f} mm, er = {ER}, via r = {VIA_R*1e3:.2f} mm")
    print(f"open-board TM10 = {C0/(2*a*math.sqrt(ER))/1e9:.2f} GHz; PEC-walled TM11 = "
          f"{C0/(2*math.sqrt(ER))*math.hypot(1/a,1/b)/1e9:.2f} GHz")
    print("pattern                         N   f_first[GHz]  LEC D[mm]  0.766c/(D sqrt er)  c/(2 D sqrt er)  wire-medium f_p")
    rows = []
    for name, vias in pats.items():
        pr = probes_away(vias)
        f1 = first_resonance(cav, pr, vias)
        D = largest_empty_circle(vias, a, b)
        fpec = 2.405 * C0 / (math.pi * D * math.sqrt(ER)) if np.isfinite(D) else float("nan")
        fhalf = C0 / (2 * D * math.sqrt(ER)) if np.isfinite(D) else float("nan")
        fp = ""
        if name.startswith("grid"):
            fp = f"{wire_medium_fp(float(name.split()[1]) * 1e-3)/1e9:.2f}"
        rows.append((name, len(vias), f1, D, fpec, fhalf))
        print(f"{name:30s} {len(vias):3d}   {f1/1e9:6.2f}        {D*1e3:6.1f}      {fpec/1e9:6.2f}"
              f"             {fhalf/1e9:6.2f}          {fp}")
    rr = [(f1, D) for (n, N, f1, D, _, _) in rows if np.isfinite(D) and np.isfinite(f1)]
    kap = [f1 * D * math.sqrt(ER) / C0 for f1, D in rr]
    print(f"fit f_first = kappa * c / (D sqrt(er)): kappa = {np.mean(kap):.3f} +/- {np.std(kap):.3f} "
          f"(n={len(kap)}); naive c/(2D) uses 0.5, PEC circle 0.766")

    # 2. fence isolation
    print("\nVia fence across a 60 x 30 mm GND-GND pair (fence at x = 30 mm), |Z21| ratio fence/no fence:")
    a2, b2 = 60e-3, 30e-3
    cav2 = Cavity(a2, b2, d, 180, 90)
    p2 = np.array([[15e-3, 15e-3], [45e-3, 15e-3]])
    fr = np.array([1e9, 2.4e9, 5e9])
    Z0 = reduced_Z(cav2, p2, np.zeros((0, 2)), fr)
    print("  pitch s    f[GHz]   sim isolation[dB]   closed form 20log|T| (one row)")
    for s in (1.5e-3, 3e-3, 6e-3):
        ys = np.arange(s / 2, b2, s)
        fence = np.array([(30e-3, y) for y in ys])
        Zf = reduced_Z(cav2, p2, fence, fr)
        for k, f in enumerate(fr):
            iso = 20 * math.log10(abs(Zf[k, 0, 1]) / abs(Z0[k, 0, 1]))
            lam = C0 / (f * math.sqrt(ER))
            B = lam / (s * math.log(s / (2 * math.pi * VIA_R)))
            T = 2 / math.sqrt(4 + B * B)
            print(f"  {s*1e3:4.1f} mm  {f/1e9:5.1f}      {iso:7.1f}              {20*math.log10(T):7.1f}"
                  f"   (s = lambda_d/{lam/s:.0f})")


if __name__ == "__main__":
    main()
