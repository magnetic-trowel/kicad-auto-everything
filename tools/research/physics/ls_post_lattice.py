# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Decaps and stitching vias are one wire medium: screening length, plasma frequency, cavity modes (lens LS).

Used by docs/topics/physics/lens-ls.md.  Round 1 found, in different workstreams, (1) a decap
"screening length" lambda = sqrt(Lc/(mu0 d n)) (xd_lengths.py, all-inductive lattice, no plane
capacitance), (2) a stitching-via lattice whose first resonance follows the wire-medium cut-off
of Belov et al. (fe_cavity.py), and (3) the lumped PDN anti-resonance between plane capacitance
and decap inductance.  This script checks that they are one dispersion relation.

A plane pair (spacing d, series impedance per square Z_sq = 2 R_s + j w mu0 d, capacitance per area
C' = eps/d) loaded by n posts per unit area (each a decap or a via with impedance Z_post) obeys
the 2-D telegrapher equation  lap V = gamma^2 V,  gamma^2 = Z_sq * (j w C' + n / Z_post).
For inductive posts (decaps above their SRF, stitching vias) this is a plasma:
    w^2 = w_p^2 + v^2 k^2,   w_p^2 = n / (L_post C'),   v = 1/sqrt(mu0 eps)
* below w_p: screening, lambda(f) = v / sqrt(w_p^2 - w^2)  (decap reach; stitching attenuation);
* at w_p: the k = 0 mode, i.e. the PDN anti-resonance; lambda diverges, all posts act together;
* above w_p: propagating cavity modes, shifted to sqrt(f_mn^2 + f_p^2).
For vias, L_post = (mu0 d / 2 pi)(ln(a/2 pi r) + 0.5275) and w_p is Belov's wire-medium cut-off.
The dimensionless number N_sq = L_post/(mu0 d) (decap inductance in plane-pair squares, independent
of pitch) separates the continuum regime (many posts within lambda; input inductance
~ (mu0 d / 2 pi) ln(1.12 lambda / r), only logarithmic in Lc) from the discrete regime (the nearest
post dominates and its distance matters).

Checks: a finite-difference lattice of the plane pair (nodes every D, posts as nodal admittances
with a Peaceman correction for vias) is solved at each frequency (sparse LU): driving-point
impedance at a central load, share of post current within radius R, compared with the continuum
1 - gamma R K1(gamma R) and with w_p.

Run:  python ls_post_lattice.py      (numpy + scipy, about a minute)
"""
import math

import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as spla
from scipy.special import kv

MU0 = 4e-7 * math.pi
EPS0 = 8.854e-12
C0 = 299792458.0
RHO = 1.72e-8
ER, TAND = 4.3, 0.02
mm = 1e-3


def rs_f(f, t=17.5e-6):
    """Sheet resistance of one plane, thin-sheet below the skin crossover, rho/delta above."""
    delta = math.sqrt(RHO / (math.pi * f * MU0))
    return RHO / min(t, delta)


def via_post_L(a, r, d):
    """Inductance of one post in a square wire-medium lattice (Belov): (mu0 d/2pi)(ln(a/2pi r) + 0.5275)."""
    return MU0 * d / (2 * math.pi) * (math.log(a / (2 * math.pi * r)) + 0.5275)


def plasma(n, Lpost, d):
    cp = EPS0 * ER / d
    return math.sqrt(n / (Lpost * cp)) / (2 * math.pi)


class Lattice:
    def __init__(self, size, dx, d, pitch, post_z, peaceman_r=None, load_offset=(0.5, 0.5)):
        """size: board side (m); dx: grid; d: plane spacing; pitch: post pitch;
        post_z(f) -> impedance of one post; peaceman_r: via radius for the sub-cell correction."""
        self.N = int(round(size / dx))
        self.dx, self.d, self.pitch = dx, d, pitch
        self.post_z, self.pr = post_z, peaceman_r
        N = self.N
        m = int(round(pitch / dx))
        idx = np.arange(N * N).reshape(N, N)
        c = N // 2
        # load at the centre, posts on a lattice offset by half a pitch (load midway between 4 posts)
        off = (c + int(round(load_offset[0] * m))) % m, (c + int(round(load_offset[1] * m))) % m
        self.posts = idx[off[0]::m, off[1]::m].ravel()
        self.load = idx[c, c]
        py, px = np.divmod(self.posts, N)
        self.r_post = np.hypot(py - c, px - c) * dx
        rows, cols = [], []
        for A, B in ((idx[:, :-1], idx[:, 1:]), (idx[:-1, :], idx[1:, :])):
            rows.append(A.ravel()); cols.append(B.ravel())
        a_, b_ = np.concatenate(rows), np.concatenate(cols)
        ones = np.ones(a_.size)
        adj = sp.coo_matrix((ones, (a_, b_)), shape=(N * N, N * N))
        adj = adj + adj.T
        deg = np.asarray(adj.sum(axis=1)).ravel()
        self.lap = (sp.diags(deg) - adj).tocsc()  # graph Laplacian (positive semidefinite)
        self.n_area = 1.0 / pitch ** 2

    def solve(self, f):
        w = 2 * math.pi * f
        zsq = 2 * rs_f(f) + 1j * w * MU0 * self.d
        cp = EPS0 * ER / self.d
        yn = 1j * w * cp * (1 - 1j * TAND) * self.dx ** 2
        zpost = self.post_z(f)
        if self.pr is not None:  # Peaceman well term: a node stands for radius 0.198 dx; add the spreading to r
            zpost = zpost + zsq / (2 * math.pi) * math.log(0.198 * self.dx / self.pr)
        diag = np.full(self.N * self.N, yn, dtype=complex)
        diag[self.posts] += 1.0 / zpost
        Y = (self.lap / zsq + sp.diags(diag)).tocsc()
        b = np.zeros(self.N * self.N, complex)
        b[self.load] = 1.0
        V = spla.spsolve(Y, b)
        ip = V[self.posts] / zpost
        return V, ip, zsq, zpost

    def gamma(self, f, zsq, zpost):
        w = 2 * math.pi * f
        cp = EPS0 * ER / self.d
        yp = 1j * w * cp * (1 - 1j * TAND) + self.n_area / zpost
        g = np.sqrt(zsq * yp)
        return g if g.real >= 0 else -g


def share(r, ip, R):
    o = np.argsort(r)
    cum = np.cumsum(ip[o])
    k = np.searchsorted(r[o], R, side="right") - 1
    return abs(cum[k]) / abs(cum[-1]) if k >= 0 else 0.0


def decap_z(Lc=0.7e-9, C=100e-9, esr=0.010):
    return lambda f: esr + 1j * 2 * math.pi * f * Lc + 1 / (1j * 2 * math.pi * f * C)


def closed_forms():
    print("== closed forms: plasma frequency f_p = sqrt(n/(L_post C'))/2pi, static reach lambda_0 = v/w_p, "
          "N_sq = L_post/(mu0 d)")
    v = C0 / math.sqrt(ER)
    for d in (0.05e-3, 0.1e-3, 0.2e-3, 1.0e-3):
        for pitch in (5e-3, 10e-3):
            for Lc in (0.4e-9, 0.7e-9, 1.5e-9):
                n = 1 / pitch ** 2
                fp = plasma(n, Lc, d)
                lam = v / (2 * math.pi * fp)
                print(f"   decaps  d={d*1e3:4.2f} mm pitch={pitch*1e3:4.1f} mm Lc={Lc*1e9:3.1f} nH: f_p={fp/1e6:7.0f} MHz, "
                      f"lambda_0={lam*1e3:5.1f} mm (=sqrt(Lc/(mu0 d n))), N_sq={Lc/(MU0*d):5.2f}, "
                      f"posts per lambda^2 disc = {math.pi*lam**2*n:5.1f}")
    for pitch in (2.5e-3, 5e-3, 10e-3, 20e-3):
        Lp = via_post_L(pitch, 0.15e-3, 0.2e-3)
        fp = plasma(1 / pitch ** 2, Lp, 0.2e-3)
        kp = math.sqrt(2 * math.pi / (pitch ** 2 * (math.log(pitch / (2 * math.pi * 0.15e-3)) + 0.5275)))
        print(f"   vias    r=0.15 mm pitch={pitch*1e3:4.1f} mm: f_p={fp/1e9:5.2f} GHz (Belov k_p c/(2 pi sqrt er) = "
              f"{kp*C0/(2*math.pi*math.sqrt(ER))/1e9:5.2f} GHz), lambda_0={1/kp*1e3:5.2f} mm = {1/kp/pitch:4.2f} pitch, "
              f"attenuation {pitch*kp*8.686:4.1f} dB per pitch")


def run_decaps(d, pitch, size, dx, freqs_share, label):
    lat = Lattice(size, dx, d, pitch, decap_z())
    n = 1 / pitch ** 2
    Lc = 0.7e-9
    fp = plasma(n, Lc, d)
    fsrf = 1 / (2 * math.pi * math.sqrt(Lc * 100e-9))
    print(f"== decap lattice {label}: d={d*1e3} mm, pitch {pitch*1e3:.0f} mm, Lc 0.7 nH, 100 nF, ESR 10 mOhm, "
          f"board {size*1e3:.0f} mm, grid {dx*1e3} mm")
    print(f"   SRF {fsrf/1e6:.1f} MHz, predicted f_p {fp/1e6:.0f} MHz, N_sq = {Lc/(MU0*d):.2f}")
    print("     f (MHz)   |Z_in| (mOhm)  share of post current within 0.5/1/2/3 lambda: lattice | continuum 1-gR K1(gR)"
          "   lambda=1/Re(gamma) mm")
    for f in freqs_share:
        V, ip, zsq, zpost = lat.solve(f)
        g = lat.gamma(f, zsq, zpost)
        lam = 1 / g.real
        sl = [share(lat.r_post, ip, x * lam) for x in (0.5, 1, 2, 3)]
        sc = [abs(1 - g * x * lam * kv(1, g * x * lam)) for x in (0.5, 1, 2, 3)]
        print(f"   {f/1e6:8.0f}    {abs(V[lat.load])*1e3:8.2f}       " + " ".join(f"{v:5.2f}" for v in sl)
              + "  |  " + " ".join(f"{v:5.2f}" for v in sc) + f"     {lam*1e3:6.1f}")
    fs = np.logspace(math.log10(5e6), math.log10(4e9), 70)
    z = np.array([abs(lat.solve(f)[0][lat.load]) for f in fs])
    peaks = [i for i in range(1, len(fs) - 1) if z[i] > z[i - 1] and z[i] > z[i + 1]]
    print("   |Z_in| local maxima (MHz): " + ", ".join(f"{fs[i]/1e6:.0f} ({z[i]*1e3:.0f} mOhm)" for i in peaks[:4])
          + f"; minimum near SRF at {fs[int(np.argmin(z[:30]))]/1e6:.0f} MHz")
    return lat


def continuum_zin(f, d, n, Lc, rload):
    w = 2 * math.pi * f
    zsq = 2 * rs_f(f) + 1j * w * MU0 * d
    zpost = decap_z(Lc)(f)
    g = np.sqrt(zsq * (1j * w * EPS0 * ER / d * (1 - 1j * TAND) + n / zpost))
    g = g if g.real >= 0 else -g
    return zsq / (2 * math.pi) * kv(0, g * rload)


def lc_sensitivity():
    print("== input inductance seen by a load (via r = 0.15 mm) in a decap field at 100 MHz: continuum vs lattice")
    print("   (continuum: Z = (Z_sq/2pi) K0(gamma r); log in Lc while N_sq >> 1)")
    for d, pitch, size in ((0.1e-3, 5e-3, 0.1), (1.0e-3, 5e-3, 0.1)):
        out = []
        for Lc in (0.35e-9, 0.7e-9, 1.4e-9):
            lat = Lattice(size, 0.5e-3, d, pitch, decap_z(Lc), peaceman_r=None)
            V, *_ = lat.solve(1e8)
            # lattice node equivalent radius 0.198 dx; report both
            zc = continuum_zin(1e8, d, 1 / pitch ** 2, Lc, 0.198 * 0.5e-3)
            out.append((Lc, V[lat.load].imag / (2 * math.pi * 1e8), zc.imag / (2 * math.pi * 1e8)))
        s_lat = math.log(out[2][1] / out[0][1]) / math.log(4)
        s_con = math.log(out[2][2] / out[0][2]) / math.log(4)
        print(f"   d = {d*1e3:.1f} mm (N_sq = {0.7e-9/(MU0*d):.2f}): L_in for Lc 0.35/0.7/1.4 nH = "
              + " / ".join(f"{o[1]*1e12:.0f}" for o in out) + " pH (lattice), "
              + " / ".join(f"{o[2]*1e12:.0f}" for o in out) + f" pH (continuum); d ln L_in / d ln Lc = {s_lat:.2f} "
              f"(lattice), {s_con:.2f} (continuum); 1 means 'each decap counts', ~0 means 'the plane counts'")


def run_vias(pitch, size, dx):
    d, r = 0.2e-3, 0.15e-3
    lat = Lattice(size, dx, d, pitch, lambda f: 1e-6 + 0j, peaceman_r=r)  # shorting via + Peaceman spreading
    kp = math.sqrt(2 * math.pi / (pitch ** 2 * (math.log(pitch / (2 * math.pi * r)) + 0.5275)))
    fp = kp * C0 / (2 * math.pi * math.sqrt(ER))
    print(f"== stitching-via lattice in a GND-GND pair: pitch {pitch*1e3:.0f} mm, r = 0.15 mm, d = 0.2 mm, "
          f"board {size*1e3:.0f} mm, grid {dx*1e3} mm; Belov f_p = {fp/1e9:.2f} GHz, 1/k_p = {1/kp*1e3:.2f} mm")
    for f in (0.5e9, 0.5 * fp, 0.8 * fp):
        V, ip, zsq, zpost = lat.solve(f)
        # decay of |V| between posts along the row through the load: fit an exponential over 1..4 pitches
        N = lat.N
        c = N // 2
        row = np.abs(V.reshape(N, N)[c, c:])
        xs = np.arange(row.size) * dx
        sel = (xs > 1.0 * pitch) & (xs < min(4.0 * pitch, 0.45 * size))
        slope = np.polyfit(xs[sel], np.log(row[sel] * np.sqrt(xs[sel])), 1)[0]  # K0 ~ e^{-x}/sqrt(x)
        lam_pred = (C0 / math.sqrt(ER)) / math.sqrt((2 * math.pi * fp) ** 2 - (2 * math.pi * f) ** 2)
        print(f"   f = {f/1e9:5.2f} GHz: |V| decay length along the row {-1/slope*1e3:5.2f} mm; predicted "
              f"v/sqrt(w_p^2 - w^2) = {lam_pred*1e3:5.2f} mm")
    fs = np.linspace(0.2 * fp, 1.6 * fp, 57)
    z = np.array([abs(lat.solve(f)[0][lat.load]) for f in fs])
    i = int(np.argmax(z))
    print(f"   first |Z_in| peak at the central launch: {fs[i]/1e9:.2f} GHz (Belov f_p {fp/1e9:.2f} GHz, "
          f"ratio {fs[i]/fp:.3f})")


if __name__ == "__main__":
    closed_forms()
    run_decaps(0.1e-3, 5e-3, 0.10, 0.5e-3, (50e6, 200e6, 500e6, 1000e6, 1500e6), "A (thin, continuum)")
    run_decaps(0.1e-3, 10e-3, 0.06, 0.5e-3, (200e6,), "B (60 mm board, 10 mm pitch: cavity modes)")
    lc_sensitivity()
    run_vias(5e-3, 0.08, 0.8e-3)
    run_vias(10e-3, 0.12, 1.0e-3)
