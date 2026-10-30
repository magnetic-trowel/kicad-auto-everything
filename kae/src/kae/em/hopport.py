# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""A hop priced through the port of the unrouted connection it replaces (stage R4b of
docs/topics/architecture/physics-frequency-coverage.md).

Before a hop is routed, its connection is a part of negligible impedance, branch b, in the board's reduced
model (kae.em.spectral), and a unit series EMF in b is one more port of the model. From that model alone, at
every frequency:
- I_P: the current every port's pattern drives through b. It is exact, so the islands downstream of the
  hop are included.
- Y = I_e(b): the admittance of the loop b closes through the rest of the board.
- l_e = x_e / Y: that loop's currents.
- x_P^o = x_P - (I_P / Y) x_e: each pattern with b opened, the other currents of the hop's loop.

Exact first order for a pattern P that does not flow through the hop (one solution exact, one unperturbed:
Z'_vs - Z_vs = x'_v^T (A' - A) x_s) gives dZ_vs = I'_v jw Phi_s(hop). Here Phi_s is the raw flux of s along
the hop, with no return subtracted: the return the short already had and the one the hop takes form a
closed current whose coupling is a potential difference, i.e. zero. tools/research/physics/em_r4_check.py
finds 1.003-1.018 from 1 kHz to 300 MHz, across a slot.

The hop's own loop is where the return goes. It is the stationary energy of h + sum_j be_j ret_j,
sum be = 1, over trial returns:
- l_e's own return (exact at low frequency);
- a strip's image current in the plane below the hop at three widths (1/pi h / (dy^2 + h^2) over the
  strip, h = 0.5, 1, 2 times the gap).
Its change against the old loop, dZ = Z_loop - Z(l_e), enters as a rank-one compensation, which carries the
resonance shift and the current the hop's loop picks up from the other patterns:

    dZ_ks = kap [I_k I_s dZ + jw (I_k Phi_s^o + I_s Phi_k^o)] - Y kap (jw Phi_k^o)(jw Phi_s^o),
    kap = 1 / (1 + Y dZ)

tools/research/physics/em_r4b_check.py --case self, a hop carrying the aggressor's own loop current: ss
0.99-1.00 to 3 MHz, 0.84-0.96 above; vs 1.00-1.15; 1.4-1.6 on the shifted resonance itself.
"""
from __future__ import annotations

import math

import numpy as np

from . import fields as EF
from . import t1 as T1

RHO = 1.72e-8               # ohm m
SPREADS = (0.5, 1.0, 2.0)   # trial return widths, in units of the gap to the plane


def path_bars(m, segs, layer_names, width=None):
    """[(layer, o, j, i, current)]: the unit-current x/y bars of a path of segments [(layer name, p0, p1)]
    on the mesh (a staircase through the cells it crosses), and its length (mm). width: the current split
    over round(width / pitch) parallel staircases across it, as the raster meshes the track."""
    n = max(1, int(round((width or 0) / m.pitch)))
    if n > 1:
        out, ln = {}, 0.0
        for q in range(n):
            off = (q - (n - 1) / 2) * m.pitch
            sh = []
            for l, p0, p1 in segs:
                d = np.subtract(p1, p0)
                nn = np.array([-d[1], d[0]]) / (np.hypot(*d) or 1.0)
                sh.append((l, tuple(np.add(p0, off * nn)), tuple(np.add(p1, off * nn))))
            b, ln = path_bars(m, sh, layer_names)
            for (L, o, j, i, c) in b:
                out[(L, o, j, i)] = out.get((L, o, j, i), 0.0) + c / n
        return [(L, o, j, i, c) for (L, o, j, i), c in out.items() if c], ln
    bars, ln = [], 0.0
    for l, p0, p1 in segs:
        if l not in layer_names:
            continue
        L = layer_names.index(l)
        ln += math.dist(p0, p1)
        n = max(2, int(math.ceil(math.dist(p0, p1) / (m.pitch / 2))) + 1)
        prev = None
        for t in np.linspace(0, 1, n):
            c = m.cell(p0[0] + (p1[0] - p0[0]) * t, p0[1] + (p1[1] - p0[1]) * t)
            if not (0 <= c[0] < m.ny and 0 <= c[1] < m.nx):
                continue
            if prev is not None and c != prev:
                (j0, i0), (j1, i1) = prev, c
                for (ja, ia), (jb, ib) in (((j0, i0), (j0, i1)), ((j0, i1), (j1, i1))):
                    if (ja, ia) == (jb, ib):
                        continue
                    o = "x" if ja == jb else "y"
                    sg = (ib - ia) if o == "x" else (jb - ja)
                    bars.append((L, o, min(ja, jb), min(ia, ib), float(sg)))
            prev = c
    return bars, ln


def image_bars(m, bars, ref_ids, width, spread):
    """The hop's return in its reference planes (shares as kae.em.t1.references), spread across the bar's
    direction as a strip's image current: (1/pi) [atan((d + w/2)/h) - atan((d - w/2)/h)], h = spread x the
    gap, to 6 h + w/2 either side."""
    out = []
    refs = {}
    for (L, o, j, i, sg) in bars:
        if L not in refs:
            refs[L] = T1.references(m, L, ref_ids)
        up, dn, hu, hd, a_up, a_dn = refs[L]
        for ref, h, a in ((up, hu, a_up), (dn, hd, a_dn)):
            k, aa = int(ref[j, i]), float(a[j, i])
            if k < 0 or aa <= 0 or not np.isfinite(h[j, i]):
                continue
            hh = max(spread * float(h[j, i]), m.pitch / 4)
            n = int(math.ceil((6 * hh + width / 2) / m.pitch))
            d = np.arange(-n, n + 1) * m.pitch
            wt = np.arctan((d + width / 2) / hh) - np.arctan((d - width / 2) / hh)
            wt = wt / wt.sum()
            for dd, c in zip(range(-n, n + 1), wt):
                jj, ii = (j + dd, i) if o == "x" else (j, i + dd)
                if 0 <= jj < m.ny and 0 <= ii < m.nx and c > 1e-4:
                    out.append((k, o, jj, ii, -sg * aa * float(c)))
    return out


def _read(fl, bars):
    return sum(c * fl[(l, o)][j, i] for (l, o, j, i, c) in bars)


class Loop:
    """The geometry of a hop's loop: inductances (H) and resistances (ohm) among the hop's bars and its trial
    image returns, and the hop's line integrals over the basis's raw flux and sheet currents."""

    def __init__(self, op, m, bf, bars, length, width, ref_ids, h_ref=None):
        from .pnr import strip_L_per_mm
        self.bars, self.length = bars, length
        self.imgs = [image_bars(m, bars, ref_ids, width, s) for s in SPREADS]
        vecs = [bars] + self.imgs
        # the hop's and its returns' currents on the faces toward each other (the gap's mid-height)
        zs = [m.layers[l].z + m.layers[l].t / 2 for l in range(len(m.layers))]
        gi = next((g[0][0] for g in self.imgs if g), None)
        face = 0.5 * (zs[bars[0][0]] + zs[gi]) if bars and gi is not None else None
        fls = [EF.flux_of_cells(op, v, face=face) for v in vecs]
        n = len(vecs)
        self.L = np.array([[_read(fls[q], vecs[p]) for q in range(n)] for p in range(n)])
        self.L = 0.5 * (self.L + self.L.T)
        t = {L: m.layers[L].t * 1e-3 for L in range(len(m.layers))}
        Lh = bars[0][0] if bars else 0
        R = np.zeros((n, n))
        R[0, 0] = RHO * length * 1e-3 / (max(width, 1e-3) * 1e-3 * t[Lh])
        for p in range(1, n):
            R[p, p] = sum(c * c * RHO / t[l] for (l, o, j, i, c) in vecs[p])
        self.R = R
        # a track narrower than a cell: its partial inductance at its real width (the closed-form strip loop
        # against the raster's loop with the middle image); wider ones are split over cell rows (path_bars)
        if h_ref and length > 0 and width < 0.75 * m.pitch:
            Ls = float(strip_L_per_mm(width, h_ref)) * length
            Lr = self.L[0, 0] + 2 * self.L[0, 2] + self.L[2, 2]
            self.L[0, 0] += Ls - Lr
        # line integrals over the basis: raw flux along the hop (with l_e: hop-to-old-return mutual), raw flux
        # along each image (image-to-old-return mutual), sheet currents under each image (their shared bars' R)
        self.rh = self._line(bf["Rx"], bf["Ry"], bars)
        self.rg = [self._line(bf["Rx"], bf["Ry"], g) for g in self.imgs]
        self.kg = [self._line(bf["Kx"], bf["Ky"], g, scale=[RHO / t[l] for (l, *_ ) in g]) for g in self.imgs]

    @staticmethod
    def _line(FX, FY, bars, scale=None):
        out = 0.0
        for q, (l, o, j, i, c) in enumerate(bars):
            A = FX if o == "x" else FY
            if l in A:
                out = out + c * (scale[q] if scale else 1.0) * A[l][:, j, i].astype(float)
        return out

    def impedance(self, w, ye, Yb, YZrr):
        """(nF,) the stationary loop impedance and its change against the old loop (dZ = Z_loop - Z(l_e)),
        given the EMF solution's coefficients ye (nF, m), its admittance Yb (nF) and Y Z(l_e) (nF)."""
        nF = len(w)
        Zl, dZ = np.zeros(nF, complex), np.zeros(nF, complex)
        ng = len(self.imgs)
        for f in range(nF):
            jw = 1j * w[f]
            Zg = self.R + jw * self.L                          # hop, images
            use_r = abs(Yb[f]) > 1e-9 and np.isfinite(YZrr[f])
            if use_r:
                le = ye[f] / Yb[f]
                Zrr = YZrr[f] / Yb[f]
                zhr = jw * (self.rh @ le)
                zrg = np.array([jw * (self.rg[q] @ le) + self.kg[q] @ le for q in range(ng)])
                n = ng + 2
                ZZ = np.zeros((n, n), complex)
                ZZ[0, 0] = Zg[0, 0]
                ZZ[0, 2:] = ZZ[2:, 0] = Zg[0, 1:]
                ZZ[2:, 2:] = Zg[1:, 1:]
                ZZ[0, 1] = ZZ[1, 0] = zhr
                ZZ[1, 1] = Zrr
                ZZ[1, 2:] = ZZ[2:, 1] = zrg
            else:
                ZZ = Zg
                n = ng + 1
            # the hop with weight 1, the returns with weights summing to 1: stationary (one multiplier)
            K = np.zeros((n, n), complex)
            K[1:, 1:] = ZZ[1:, 1:]
            K[1:, 0] = 1.0
            K[0, 1:] = 1.0
            sol = np.linalg.solve(K, np.r_[1.0, -ZZ[1:, 0]])
            wv = np.r_[1.0, sol[1:]]
            Zl[f] = wv @ ZZ @ wv
            dZ[f] = (Zl[f] - Zrr) if use_r else Zl[f]
        return Zl, dZ
