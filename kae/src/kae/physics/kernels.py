# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Closed-form physics kernels for the placement terms (docs/topics/physics/place-terms.md).

Units throughout: lengths in mm, inductance in nH, capacitance in pF, time in ns,
temperature in K, power in W. With lengths in mm, mu0/(4 pi) = 0.1 nH/mm.

Kernels (each cites the exact reference it is validated against in
tools/research/physics/pt_validate_kernels.py):

* `lprime_hj(w, h)`: per-unit-length inductance of a strip of width w at height h over
  an ideal plane, Z0_air / c0 from Hammerstad-Jensen (fringing included, any w/h).
* `cprime_hj(w, h, er)`: per-unit-length capacitance of the same microstrip,
  sqrt(eps_eff) / (c0 Z0), Hammerstad-Jensen eps_eff.
* `m_par`: Grover's exact mutual inductance of two parallel filaments.
* `loop_L(segments, plane)`: loop inductance of a closed chain of straight 3-D segments
  over an ideal plane at z = 0 by partial inductances with images
  (L = sum_ij M(s_i, s_j) + M(s_i, image(s_j)); the image of a segment mirrors z and
  reverses it, which reverses horizontal and keeps vertical currents, as for a PEC).
  Horizontal strips use the Hammerstad-Jensen per-length term in place of the thin-filament
  one (the current spreads across a wide strip); parallel pairs are exact (Grover),
  perpendicular pairs vanish, oblique pairs use Gauss-Legendre quadrature.
* `mutual_polylines`: Neumann mutual between two open or closed polylines with images
  (aggressor-victim coupling).
* `patch_coupling`: mutual capacitance between small copper patches over a plane from
  potential coefficients with images; the far field is eps0 A_a A_v / (2 pi r^3)
  (lens SY, D1).
* `fin_kernel`: steady temperature rise of a convectively cooled board (thin fin),
  P K0(r/lambda) / (2 pi G_s), plus adiabatic-edge images for a rectangular board.
"""
from __future__ import annotations

import math

import numpy as np

MU0_4PI = 0.1          # nH/mm
MU0_2PI = 0.2          # nH/mm
EPS0 = 8.8541878e-3    # pF/mm
C0 = 299.792458        # mm/ns
ETA0 = 376.730313      # ohm
T_CU = 0.035           # mm, default copper thickness

# ----------------------------------------------------------------------------- lines


def z0_air_hj(w, h):
    """Air-filled microstrip Z0 (ohm), Hammerstad-Jensen; scalar."""
    u = max(w, 1e-6) / max(h, 1e-6)
    f = 6.0 + (2.0 * math.pi - 6.0) * math.exp(-((30.666 / u) ** 0.7528))
    return ETA0 / (2.0 * math.pi) * math.log(f / u + math.sqrt(1.0 + (2.0 / u) ** 2))


def lprime_hj(w, h):
    """Per-unit-length inductance (nH/mm) of a strip of width w (mm) at height h over a plane."""
    return z0_air_hj(w, h) / C0


def eps_eff_hj(w, h, er):
    """Hammerstad-Jensen effective permittivity of a microstrip (zero thickness)."""
    u = max(w, 1e-6) / max(h, 1e-6)
    a = 1.0 + math.log((u ** 4 + (u / 52.0) ** 2) / (u ** 4 + 0.432)) / 49.0 \
        + math.log(1.0 + (u / 18.1) ** 3) / 18.7
    b = 0.564 * ((er - 0.9) / (er + 3.0)) ** 0.053
    return (er + 1.0) / 2.0 + (er - 1.0) / 2.0 * (1.0 + 10.0 / u) ** (-a * b)


def cprime_hj(w, h, er):
    """Per-unit-length capacitance to the plane (pF/mm) of a microstrip."""
    ee = eps_eff_hj(w, h, er)
    z0 = z0_air_hj(w, h) / math.sqrt(ee)
    return math.sqrt(ee) / (C0 * z0) * 1e3     # (1/(mm/ns * ohm)) = nF/mm... -> pF/mm


def gmd_rect(w, t=T_CU):
    """Geometric mean distance of a rectangular cross-section (Grover): 0.2235 (w + t)."""
    return 0.2235 * (w + t)


# ----------------------------------------------------------------------------- filaments


def _G(u, d):
    return u * math.asinh(u / d) - math.sqrt(u * u + d * d)


def m_par(l1, l2, s, d):
    """Mutual (nH) of two parallel co-directed filaments (mm): 1 spans [0, l1], 2 spans
    [s, s + l2] along the same axis, perpendicular distance d (Grover)."""
    d = max(d, 1e-9)
    return MU0_4PI * (_G(s + l2, d) - _G(s + l2 - l1, d) - _G(s, d) + _G(s - l1, d))


def _Gv(u, d):
    return u * np.arcsinh(u / d) - np.sqrt(u * u + d * d)


def m_par_v(l1, l2, s, d):
    """Vectorized m_par (numpy arrays broadcast)."""
    d = np.maximum(d, 1e-9)
    return MU0_4PI * (_Gv(s + l2, d) - _Gv(s + l2 - l1, d) - _Gv(s, d) + _Gv(s - l1, d))


_GL = {n: np.polynomial.legendre.leggauss(n) for n in (2, 3, 4, 6, 8, 12, 16)}


def m_quad(p0, p1, q0, q1, n=8):
    """Neumann mutual (nH) of two straight filaments p0->p1 and q0->q1 (3-D, mm) by
    n x n Gauss-Legendre quadrature (any relative orientation; not for touching ends)."""
    x, wq = _GL[n]
    t = 0.5 * (x + 1.0)
    p0 = np.asarray(p0, float)
    q0 = np.asarray(q0, float)
    dp = np.asarray(p1, float) - p0
    dq = np.asarray(q1, float) - q0
    P = p0[None, :] + t[:, None] * dp[None, :]
    Q = q0[None, :] + t[:, None] * dq[None, :]
    R = np.sqrt(((P[:, None, :] - Q[None, :, :]) ** 2).sum(-1))
    R = np.maximum(R, 1e-9)
    W = 0.25 * wq[:, None] * wq[None, :]
    return MU0_4PI * float(np.dot(dp, dq)) * float((W / R).sum())


def m_seg(p0, p1, q0, q1, gmd=None):
    """Signed Neumann mutual (nH) between straight segments p0->p1 and q0->q1 (3-D, mm).

    Parallel (or anti-parallel) segments: exact Grover form (gmd as the distance when the
    segments coincide, i.e. a self term). Perpendicular: 0. Oblique: quadrature, refined
    when the segments are close compared with their lengths."""
    p0 = np.asarray(p0, float)
    p1 = np.asarray(p1, float)
    q0 = np.asarray(q0, float)
    q1 = np.asarray(q1, float)
    dp = p1 - p0
    dq = q1 - q0
    lp = float(np.linalg.norm(dp))
    lq = float(np.linalg.norm(dq))
    if lp < 1e-12 or lq < 1e-12:
        return 0.0
    up = dp / lp
    uq = dq / lq
    c = float(np.dot(up, uq))
    if abs(c) < 1e-9:
        return 0.0
    if abs(abs(c) - 1.0) < 1e-9:
        # parallel: coordinates along up
        a0 = 0.0
        b0 = float(np.dot(q0 - p0, up))
        b1 = float(np.dot(q1 - p0, up))
        perp = (q0 - p0) - b0 * up
        d = float(np.linalg.norm(perp))
        if d < 1e-9 and gmd is not None:
            d = gmd
        lo, hi = (b0, b1) if b1 > b0 else (b1, b0)
        m = m_par(lp, hi - lo, lo - a0, max(d, 1e-9))
        return m if c > 0 else -m
    # oblique
    dist = _seg_dist(p0, p1, q0, q1)
    n = 8 if dist > 0.25 * max(lp, lq) else 16
    return m_quad(p0, p1, q0, q1, n=n)


def _seg_dist(p0, p1, q0, q1):
    """Minimum distance between two 3-D segments (coarse: sampled)."""
    t = np.linspace(0.0, 1.0, 9)
    P = p0[None, :] + t[:, None] * (p1 - p0)[None, :]
    Q = q0[None, :] + t[:, None] * (q1 - q0)[None, :]
    return float(np.sqrt(((P[:, None, :] - Q[None, :, :]) ** 2).sum(-1)).min())


def image(seg):
    """PEC image of a segment for a plane at z = 0: mirror z, reverse direction."""
    (x0, y0, z0), (x1, y1, z1) = seg[0], seg[1]
    return ((x1, y1, -z1), (x0, y0, -z0))


def loop_L(segments, plane=True, t=T_CU):
    """Loop inductance (nH) of a closed chain of straight 3-D segments (mm).

    segments: list of dicts {p0, p1, w (strip width) or r (via/tube radius)}; strips must be
    horizontal (constant z), vias vertical. plane: ideal plane at z = 0 (all z > 0) or none.

    L = sum_ij [M(s_i, s_j) + M(s_i, image(s_j))]. Self terms use the GMD; horizontal
    strips over the plane replace the thin-filament per-length term 0.2 ln(2h/a) by the
    Hammerstad-Jensen L'(w, h) (current spreading across wide strips), keeping the
    finite-length image terms of the filament model."""
    n = len(segments)
    L = 0.0
    S = [(np.asarray(s['p0'], float), np.asarray(s['p1'], float)) for s in segments]
    gm = []
    for s in segments:
        if 'r' in s and s['r']:
            gm.append(float(s['r']))
        else:
            gm.append(gmd_rect(float(s.get('w', 0.2)), t))
    for i in range(n):
        p0, p1 = S[i]
        strip = plane and abs(p0[2] - p1[2]) < 1e-12 and not segments[i].get('r')
        for j in range(n):
            q0, q1 = S[j]
            if i == j:
                if strip:
                    L += strip_self(float(np.linalg.norm(p1 - p0)), float(segments[i].get('w', 0.2)),
                                    float(p0[2]), t)
                    continue
                L += m_seg(p0, p1, q0, q1, gmd=gm[i])
            elif j > i:
                L += 2.0 * m_seg(p0, p1, q0, q1)
            if plane:
                i0, i1 = image((q0, q1))
                L += m_seg(p0, p1, np.asarray(i0), np.asarray(i1))
    return float(L)


def strip_self(ln, w, h, t=T_CU):
    """Self inductance (nH) of a straight strip segment of length ln, width w at height h
    over a plane, including its own image: M(ln, a) - M(ln, d_eff), the thin-filament form
    with the GMD a = 0.2235 (w + t) and an effective image distance d_eff = a exp(L'/0.2)
    chosen so that the per-length term is Hammerstad-Jensen's L'(w, h). For narrow strips
    d_eff -> 2h (filament with image); for wide strips the end terms cancel."""
    a = gmd_rect(w, t)
    d_eff = a * math.exp(lprime_hj(w, h) / MU0_2PI)
    return m_par(ln, ln, 0.0, a) - m_par(ln, ln, 0.0, d_eff)


# ----------------------------------------------------------------------------- coupling


def gauss_points(polyline, n=4, closed=False):
    """Gauss points (P, dl) of a 3-D polyline: P (k, 3) positions, dl (k, 3) weighted
    tangent vectors (sum of dl over a segment = the segment vector)."""
    pts = np.asarray(polyline, float)
    if closed:
        pts = np.vstack([pts, pts[:1]])
    x, wq = _GL[n]
    t = 0.5 * (x + 1.0)
    a = pts[:-1]
    d = pts[1:] - pts[:-1]
    P = (a[:, None, :] + t[None, :, None] * d[:, None, :]).reshape(-1, 3)
    dl = (0.5 * wq[None, :, None] * d[:, None, :]).reshape(-1, 3)
    return P, dl


def mutual_polylines(pa, pv, plane=True, n=4, closed_a=False, closed_v=False):
    """Neumann mutual (nH) between an aggressor and a victim polyline (3-D, mm), with the
    aggressor imaged in a plane at z = 0 (the victim's own image does not change the flux
    through it). Quadrature; for separate structures (distance > segment length / 4)."""
    Pa, dla = gauss_points(pa, n, closed_a)
    Pv, dlv = gauss_points(pv, n, closed_v)
    R = np.sqrt(((Pa[:, None, :] - Pv[None, :, :]) ** 2).sum(-1))
    m = ((dla @ dlv.T) / np.maximum(R, 1e-9)).sum()
    if plane:
        Pi = Pa.copy()
        Pi[:, 2] = -Pi[:, 2]
        dli = -dla.copy()
        dli[:, 2] = -dli[:, 2]     # mirror z of the tangent, then reverse: (-dx, -dy, +dz)
        R2 = np.sqrt(((Pi[:, None, :] - Pv[None, :, :]) ** 2).sum(-1))
        m += ((dli @ dlv.T) / np.maximum(R2, 1e-9)).sum()
    return MU0_4PI * float(m)


def patch_coupling(Aa, Av, r, ha, hv, Ca=None, Cv=None, eps_r=1.0):
    """Mutual capacitance (pF) between two small patches of areas Aa, Av (mm^2) at heights
    ha, hv over a grounded plane, centre distance r (mm).

    First order in the potential coefficients with images:
        p_av = (1/(4 pi eps)) (1/r - 1/sqrt(r^2 + (ha + hv)^2)),  C_av ~ C_a C_v p_av
    with C_a, C_v the patches' own capacitances to the plane (default eps A / h). The far
    field (r >> h) is eps0 A_a A_v / (2 pi r^3), independent of h (lens SY D1)."""
    eps = EPS0 * eps_r
    Ca = eps * Aa / max(ha, 1e-6) if Ca is None else Ca
    Cv = eps * Av / max(hv, 1e-6) if Cv is None else Cv
    r = max(r, 1e-6)
    p = (1.0 / r - 1.0 / math.sqrt(r * r + (ha + hv) ** 2)) / (4.0 * math.pi * EPS0)
    return Ca * Cv * p


# ----------------------------------------------------------------------------- thermal


def fin_params(cu_thickness_mm, cu_fill, fr4_mm, k_cu=390.0, k_fr4=0.8, h_top=10.0, h_bot=10.0):
    """Sheet conductance G_s (W/K) and spreading length lambda (mm) of a board fin.

    G_s = sum_layers k_cu t_i f_i + k_fr4 t_fr4 (W/K per square); lambda = sqrt(G_s / h_tot)."""
    gs = sum(k_cu * t * 1e-3 * f for t, f in zip(cu_thickness_mm, cu_fill)) + k_fr4 * fr4_mm * 1e-3
    htot = h_top + h_bot
    lam = math.sqrt(gs / htot) * 1e3
    return gs, lam


def fin_point(r_mm, gs, lam):
    """Temperature rise (K per W) at distance r from a point source in an infinite fin."""
    from scipy.special import k0
    return k0(np.maximum(r_mm, 1e-6) / lam) / (2.0 * math.pi * gs)


def fin_disk_self(a_mm, gs, lam):
    """Mean-centre rise (K per W) of a uniformly heated disk of radius a in an infinite fin:
    (1 - (a/lam) K1(a/lam)) / (pi a^2 h_tot), with h_tot = G_s / lam^2."""
    from scipy.special import k1
    x = max(a_mm, 1e-3) / lam
    htot_per_mm2 = gs / (lam * lam)          # W/K per mm^2
    return (1.0 - x * k1(x)) / (math.pi * a_mm * a_mm * htot_per_mm2)


def image_offsets(x0, y0, x1, y1, xs, ys, rings=1):
    """Adiabatic-edge image positions of a source at (xs, ys) in the rectangle
    [x0, x1] x [y0, y1]: arrays (X, Y) including the source itself (index 0)."""
    Lx, Ly = x1 - x0, y1 - y0
    u, v = xs - x0, ys - y0
    X, Y = [], []
    for m in range(-rings, rings + 1):
        for ux in ((2 * m * Lx + u), (2 * m * Lx - u)):
            for k in range(-rings, rings + 1):
                for vy in ((2 * k * Ly + v), (2 * k * Ly - v)):
                    X.append(x0 + ux)
                    Y.append(y0 + vy)
    X = np.array(X)
    Y = np.array(Y)
    i0 = int(np.argmin((X - xs) ** 2 + (Y - ys) ** 2))
    X[[0, i0]] = X[[i0, 0]]
    Y[[0, i0]] = Y[[i0, 0]]
    return X, Y


# ----------------------------------------------------------------------------- spectra


def trapezoid_envelope(A, f, period_ns, t_rise_ns, duty=0.5):
    """Upper envelope of a trapezoid's harmonic amplitude at frequency f (GHz):
    min(2 A d, 2 A/(pi f T), 2 A/(pi^2 f^2 T t_r))."""
    T = period_ns
    return min(2.0 * A * duty, 2.0 * A / (math.pi * f * T),
               2.0 * A / (math.pi ** 2 * f * f * T * max(t_rise_ns, 1e-3)))
