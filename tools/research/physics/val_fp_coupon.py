# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Registered predictions for the plane-pair coupons of the validation program (coupons FP, VC, ET).

Used by docs/topics/physics/validation-coupons.md. All three use the L2-L3 core of a
JLC04161H-3313 board (d = 1.265 mm, er 4.6 assumed, tan d 0.02 assumed at GHz) and the
round-1 cavity model fe_cavity.py (rectangular plane pair, open edges, modal Z matrix,
shorting vias as zero-ohm ports by Schur complement), reused.

  FP  stitching lattice (lens LS's wire medium vs lens VP's empty circle vs round 1's kappa fit
      vs the lambda/20 rule). Square tiles (60, 60, 80, 90 mm) with 0.3 mm vias on a square
      lattice of pitch p = 10, 15, 20, 30 mm, each with a twin tile without vias; two vertical
      SMA ports (centre pin to L3, body to L2), 30 mm apart (40 mm at p = 20), each midway
      between four posts. Predictions: the first S21 resonance, Belov's f_p, and |S21| at 1.0 and 2.45 GHz
      relative to the twin without vias.
  VC  via-cluster inductance (lens VP: logarithmic capacity, "outer size, not count" vs the
      count rule L_via/N). A cluster feeds L1 -> L3 through L2 antipads inside a ring of 24
      vias at R = 10 mm; 2-port shunt-through measurement from L1 at 20-200 MHz.
      L = (mu0 d / 2 pi) [ln(R / cap) + ln(R / (N_ring a)) / N_ring] + L_top.
  ET  edge RC termination of a PWR-GND cavity (lens TH D4): 100 x 80 mm L2/L3 pair, SMA probe
      at (12, 9) mm; 36 series RC terminations (R, 10 nF, mounting ESL 0.5-1.0 nH) every
      10 mm along the edges, populated after the bare measurement. Prediction: the ratio of
      the largest |Z11| peak (0.3-2.5 GHz) before and after, for R = R_m = eta0 d/(sqrt(er) p).

Intervals: er 4.3-4.8, d +-10 %, tan d 0.015-0.025, via radius 0.13-0.17 mm, ESL 0.5-1.0 nH.

Run:  python tools/research/physics/val_fp_coupon.py      (numpy + scipy, ~2-4 min)
"""
import math
import os
import sys

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
import numpy as np  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fe_cavity as fc  # noqa: E402  (round-1 cavity model, reused)
import vp_floors as vf  # noqa: E402  (round-2 VP logarithmic capacity, reused)

MU0, EPS0, C0 = 4e-7 * math.pi, 8.854e-12, 2.998e8
ETA0 = math.sqrt(MU0 / EPS0)
MM = 1e-3
D_CORE, ER_CORE, TAND = 1.265 * MM, 4.6, 0.02
VIA_R, SMA_W = 0.15 * MM, 1.0 * MM
Z0 = 50.0


def phi_pts(cav, pts, widths):
    """Modal port vectors with a square port of width w per point (fe_cavity uses one global width)."""
    x, y = pts[:, 0:1], pts[:, 1:2]
    w = np.asarray(widths)[:, None]
    s = np.sinc(cav.kmr[None, :] * w / (2 * math.pi)) * np.sinc(cav.knr[None, :] * w / (2 * math.pi))
    return np.cos(cav.kmr * x) * np.cos(cav.knr * y) * s * np.sqrt(cav.chi)


def two_port_s21(cav, ports, shorts, freqs, short_r=VIA_R):
    pts = np.vstack([ports, shorts]) if len(shorts) else ports
    widths = [SMA_W] * len(ports) + [1.6 * short_r] * len(shorts)
    phi = phi_pts(cav, pts, widths)
    out = []
    for f in freqs:
        z = cav.Z(phi, f)
        if len(shorts):
            zpp, zps, zss = z[:2, :2], z[:2, 2:], z[2:, 2:]
            z = zpp - zps @ np.linalg.solve(zss, zps.T)
        s = (z - Z0 * np.eye(2)) @ np.linalg.inv(z + Z0 * np.eye(2))
        out.append(s[1, 0])
    return np.array(out)


def belov_fp(p, r=VIA_R, er=ER_CORE):
    kp = math.sqrt(2 * math.pi / (math.log(p / (2 * math.pi * r)) + 0.5275)) / p
    return kp * C0 / (2 * math.pi * math.sqrt(er))


def first_peak(freqs, mag, floor_db=-60.0):
    db = 20 * np.log10(np.maximum(mag, 1e-12))
    for i in range(1, len(freqs) - 1):
        if db[i] > db[i - 1] and db[i] >= db[i + 1] and db[i] > floor_db:
            return freqs[i]
    return float("nan")


def sec_fp():
    print("== FP: stitched L2-L3 cavity tiles; two ports at lattice-cell centres; |S21| relative to the same tile without vias")
    # (pitch, tile side, post offset, port x positions, port y): ports sit midway between four posts
    tiles = [(10 * MM, 60 * MM, 5 * MM, (10 * MM, 40 * MM), 30 * MM),
             (15 * MM, 60 * MM, 7.5 * MM, (15 * MM, 45 * MM), 30 * MM),
             (20 * MM, 80 * MM, 10 * MM, (20 * MM, 60 * MM), 40 * MM),
             (30 * MM, 90 * MM, 15 * MM, (30 * MM, 60 * MM), 30 * MM)]
    freqs = np.arange(0.3e9, 4.0e9 + 1e6, 20e6)
    variants = [("nominal", 4.6, 1.0), ("er 4.3", 4.3, 1.0), ("er 4.8", 4.8, 1.0), ("d -10%", 4.6, 0.9),
                ("d +10%", 4.6, 1.1)]
    print("   pitch  tile   vias  port sep  Belov f_p   first S21 peak [interval]   |S21| 1.0 GHz rel. [int]   2.45 GHz [int]")
    for p, a, off, pxs, py in tiles:
        ports = np.array([[pxs[0], py], [pxs[1], py]])
        xs = np.arange(off, a, p)
        vias = np.array([(x, y) for x in xs for y in xs])
        nm = int(round(2.5 * a / MM))
        fpk, r1, r2 = [], [], []
        i1, i2 = np.argmin(abs(freqs - 1.0e9)), np.argmin(abs(freqs - 2.45e9))
        for vname, er, kd in variants:
            fc.ER, fc.TAND = er, TAND
            cav = fc.Cavity(a, a, D_CORE * kd, nm, nm)
            s_v = np.abs(two_port_s21(cav, ports, vias, freqs))
            s_0 = np.abs(two_port_s21(cav, ports, np.zeros((0, 2)), freqs))
            fpk.append(first_peak(freqs, s_v))
            r1.append(20 * math.log10(s_v[i1] / s_0[i1]))
            r2.append(20 * math.log10(s_v[i2] / s_0[i2]))
        fc.ER, fc.TAND = 4.6, 0.02
        print(f"   {p/MM:3.0f} mm {a/MM:3.0f} mm  {len(vias):4d}  {abs(pxs[1]-pxs[0])/MM:5.1f} mm  {belov_fp(p)/1e9:5.2f} GHz"
              f"    {fpk[0]/1e9:5.2f} GHz [{min(fpk)/1e9:.2f}, {max(fpk)/1e9:.2f}]       {r1[0]:+6.1f} dB [{min(r1):+.1f}, {max(r1):+.1f}]"
              f"    {r2[0]:+6.1f} dB [{min(r2):+.1f}, {max(r2):+.1f}]")
    print("   competing predictions for the first resonance with vias (D = largest empty circle, square lattice D = p sqrt2):")
    for p in (10 * MM, 15 * MM, 20 * MM, 30 * MM):
        d_lec = p * math.sqrt(2)
        print(f"     p {p/MM:3.0f} mm: VP bound f1 <= 0.766 c/(D sqrt er) = {0.766*C0/(d_lec*math.sqrt(ER_CORE))/1e9:5.2f} GHz;"
              f" round-1 kappa 0.32-0.64: {0.32*C0/(d_lec*math.sqrt(ER_CORE))/1e9:4.2f}-{0.64*C0/(d_lec*math.sqrt(ER_CORE))/1e9:4.2f} GHz;"
              f" lambda/20 rule needs p <= {C0/(2.45e9*math.sqrt(ER_CORE))/20/MM:4.1f} mm for 2.45 GHz")


def sec_vc():
    print("\n== VC: via-cluster inductance, L2-L3 core d = 1.265 mm, ring of 24 vias at R = 10 mm (shunt Z = j w L)")
    d, a, R, nr = D_CORE, VIA_R / MM, 10.0, 24
    pref = MU0 * d / (2 * math.pi) * 1e9          # nH per neper
    ring = math.log(R / (nr * a)) / nr
    l_top = MU0 * 0.0994e-3 / (2 * math.pi) * math.log(2.0 / 0.3) * 1e9  # L1-L2 part under a 2 mm pad, rough
    clusters = {
        "1 via": [(0.0, 0.0)],
        "2 vias, 2 mm apart": [(-1.0, 0.0), (1.0, 0.0)],
        "4 vias, 2 mm square": [(-1.0, -1.0), (-1.0, 1.0), (1.0, -1.0), (1.0, 1.0)],
        "9 vias, 3x3 at 1 mm": [(i - 1.0, j - 1.0) for i in range(3) for j in range(3)],
        "4 vias, 0.6 mm square": [(-0.3, -0.3), (-0.3, 0.3), (0.3, -0.3), (0.3, 0.3)],
    }
    l1 = None
    print(f"   prefactor mu0 d/2pi = {pref:.3f} nH/neper; ring term {ring:.3f}; top (L1-L2) allowance {l_top:.3f} nH")
    print("   cluster                    cap (mm)   L capacity [interval]     count rule L_1/N    ratio count/capacity")
    for name, cs in clusters.items():
        vals = []
        for aa in (0.13, 0.15, 0.17):
            for kd in (0.9, 1.0, 1.1):
                cap = vf.log_capacity(cs, aa)
                vals.append(pref * kd * (math.log(R / cap) + ring) + l_top)
        cap = vf.log_capacity(cs, a)
        lc = pref * (math.log(R / cap) + ring) + l_top
        if l1 is None:
            l1 = lc
        n = len(cs)
        print(f"   {name:24s}  {cap:7.3f}   {lc:6.3f} nH [{min(vals):.3f}, {max(vals):.3f}]      {l1/n:6.3f} nH"
              f"          {l1/n/lc:5.2f}")
    print("   registered discriminator: L(9 vias at 1 mm) / L(4 vias at 2 mm) (capacity ~1; count rule 4/9 = 0.44)")
    c9, c4 = vf.log_capacity(clusters["9 vias, 3x3 at 1 mm"], a), vf.log_capacity(clusters["4 vias, 2 mm square"], a)
    print(f"     capacity: {(math.log(R/c9)+ring+l_top/pref)/(math.log(R/c4)+ring+l_top/pref):.3f}")


def edge_pts(a, b, p, inset=0.5 * MM):
    pts = []
    for x in np.arange(p / 2, a, p):
        pts += [(x, inset), (x, b - inset)]
    for y in np.arange(p / 2, b, p):
        pts += [(inset, y), (a - inset, y)]
    return np.array(pts)


def peak_z(cav, probe, term, freqs, widths_term=0.6 * MM):
    pts = probe if term is None else np.vstack([probe, term[0]])
    widths = [SMA_W] + ([] if term is None else [widths_term] * len(term[0]))
    phi = phi_pts(cav, pts, widths)
    zs = []
    for f in freqs:
        z = cav.Z(phi, f)
        if term is not None:
            w = 2 * math.pi * f
            zl = term[1] + 1j * w * term[2] + 1 / (1j * w * term[3])
            zps, zss = z[:1, 1:], z[1:, 1:]
            z = z[:1, :1] - zps @ np.linalg.solve(zss + zl * np.eye(zss.shape[0]), zps.T)
        zs.append(abs(z[0, 0]))
    zs = np.array(zs)
    idx = [k for k in range(1, len(zs) - 1) if zs[k] > zs[k - 1] and zs[k] >= zs[k + 1]]
    return max(zs[idx]) if idx else float(zs.max())


def sec_et():
    print("\n== ET: edge RC terminations on a 100 x 80 mm L2-L3 (PWR-GND) pair, probe at (12, 9) mm, 0.3-2.5 GHz")
    a, b, p = 100 * MM, 80 * MM, 10 * MM
    freqs = np.linspace(0.3e9, 2.5e9, 441)
    probe = np.array([[12 * MM, 9 * MM]])
    pts = edge_pts(a, b, p)
    out = []
    for er, kd, tand in ((4.6, 1.0, 0.02), (4.3, 1.0, 0.02), (4.8, 1.0, 0.02), (4.6, 0.9, 0.02), (4.6, 1.1, 0.02),
                         (4.6, 1.0, 0.015), (4.6, 1.0, 0.025)):
        fc.ER, fc.TAND = er, tand
        cav = fc.Cavity(a, b, D_CORE * kd, 60, 50)
        rm = ETA0 * D_CORE * kd / (math.sqrt(er) * p)
        bare = peak_z(cav, probe, None, freqs)
        row = [bare]
        for esl in (0.5e-9, 1.0e-9):
            row.append(peak_z(cav, probe, (pts, rm, esl, 10e-9), freqs))
        out.append((er, kd, tand, rm, row))
    fc.ER, fc.TAND = 4.6, 0.02
    er, kd, tand, rm, row = out[0]
    print(f"   {len(pts)} terminations, R_m = eta0 d/(sqrt(er) p) = {rm:.1f} ohm, C 10 nF")
    red05 = [o[4][0] / o[4][1] for o in out]
    red10 = [o[4][0] / o[4][2] for o in out]
    print(f"   bare peak |Z11| {row[0]:.2f} ohm [{min(o[4][0] for o in out):.2f}, {max(o[4][0] for o in out):.2f}]")
    print(f"   terminated, ESL 0.5 nH: {row[1]:.2f} ohm -> reduction x{red05[0]:.1f} [{min(red05):.1f}, {max(red05):.1f}]")
    print(f"   terminated, ESL 1.0 nH: {row[2]:.2f} ohm -> reduction x{red10[0]:.1f} [{min(red10):.1f}, {max(red10):.1f}]")
    pmax = ETA0 * D_CORE / (math.sqrt(ER_CORE) * 2 * math.pi * 1e9 * 1.0e-9)
    print(f"   ESL limit (TH): pitch p < eta0 d/(sqrt(er) w L_esl) = {pmax/MM:.0f} mm at 1 GHz, 1 nH: 10 mm is inside it")


if __name__ == "__main__":
    which = sys.argv[1:] or ["fp", "vc", "et"]
    if "fp" in which:
        sec_fp()
    if "vc" in which:
        sec_vc()
    if "et" in which:
        sec_et()
