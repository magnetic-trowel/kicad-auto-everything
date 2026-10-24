# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Measure a label map: interfaces, circle fits, triple junctions, contact angles."""
import contourpy
import numpy as np
from scipy import ndimage as ndi
from scipy.optimize import least_squares


def smooth_ind(lab, p, s=1.0):
    return ndi.gaussian_filter((lab == p).astype(float), s, mode="nearest")


def interface_points(lab, p, q, s=1.0, purity=0.9):
    """Sub-pixel points (x, y) of the p|q interface: zero set of Gp - Gq where the two
    phases make up > purity of the smoothed mass (away from junctions/other phases)."""
    up, uq = smooth_ind(lab, p, s), smooth_ind(lab, q, s)
    gen = contourpy.contour_generator(z=up - uq)
    pts = [l for l in gen.lines(0.0) if len(l)]
    if not pts:
        return np.zeros((0, 2))
    pts = np.vstack(pts)
    ix = np.clip(np.round(pts).astype(int), 0, [lab.shape[1] - 1, lab.shape[0] - 1])
    tot = (up + uq)[ix[:, 1], ix[:, 0]]
    return pts[tot > purity]


def fit_circle(pts):
    """Geometric circle fit. Returns (cx, cy, r, rms)."""
    x, y = pts[:, 0], pts[:, 1]
    A = np.c_[2 * x, 2 * y, np.ones_like(x)]
    b = x * x + y * y
    c, *_ = np.linalg.lstsq(A, b, rcond=None)
    cx, cy = c[0], c[1]
    r = np.sqrt(max(c[2] + cx * cx + cy * cy, 1e-9))

    def res(v):
        return np.hypot(x - v[0], y - v[1]) - v[2]
    sol = least_squares(res, [cx, cy, r])
    cx, cy, r = sol.x
    return cx, cy, abs(r), float(np.sqrt(np.mean(res(sol.x) ** 2)))


def fit_line(pts):
    m = pts.mean(0)
    _, _, vt = np.linalg.svd(pts - m)
    d = vt[0]
    rms = float(np.sqrt(np.mean(((pts - m) @ vt[1]) ** 2)))
    return m, d, rms


def junctions(lab, phases=None):
    """Cell corners where >= 3 distinct phases meet in the 2x2 block; clustered.
    Returns list of (x, y, set_of_phases) with x, y at the corner."""
    a, b, c, d = lab[:-1, :-1], lab[:-1, 1:], lab[1:, :-1], lab[1:, 1:]
    st = np.stack([a, b, c, d])
    srt = np.sort(st, 0)
    nd = 1 + (srt[1] != srt[0]) + (srt[2] != srt[1]) + (srt[3] != srt[2])
    m = nd >= 3
    if phases is not None:
        m &= np.isin(st, list(phases)).all(0)
    cc, n = ndi.label(ndi.binary_dilation(m, iterations=2))
    out = []
    for k in range(1, n + 1):
        ys, xs = np.nonzero(m & (cc == k))
        if not len(ys):
            continue
        ph = set(np.unique(st[:, ys, xs]).tolist())
        out.append((xs.mean() + 0.5, ys.mean() + 0.5, ph))
    return out


def tangent_at(J, pts, circle=None, r_line=1e4):
    """Unit tangent at point J of the curve through pts, pointing into the curve."""
    J = np.asarray(J, float)
    away = pts.mean(0) - J
    if circle is not None and circle[2] < r_line:
        cx, cy, r = circle[:3]
        rad = J - np.array([cx, cy])
        t = np.array([-rad[1], rad[0]])
    else:
        _, t, _ = fit_line(pts)
    t = t / np.linalg.norm(t)
    # orientation: toward the nearby part of the curve
    near = pts[np.argsort(np.linalg.norm(pts - J, axis=1))[:max(5, len(pts) // 5)]]
    if np.dot(near.mean(0) - J, t) < 0:
        t = -t
    return t


def angles_between(ts):
    """Sorted angular gaps (degrees) between unit vectors around a point."""
    ang = np.sort(np.mod(np.degrees(np.arctan2([t[1] for t in ts], [t[0] for t in ts])), 360))
    gaps = np.diff(np.r_[ang, ang[0] + 360])
    return gaps


def boundary_normals(lab, p, s=1.0):
    """Outward normal angles (deg) and segment lengths along the p boundary."""
    up = smooth_ind(lab, p, s)
    gen = contourpy.contour_generator(z=up)
    angs, lens = [], []
    for l in gen.lines(0.5):
        d = np.diff(l, axis=0)
        L = np.hypot(d[:, 0], d[:, 1])
        # contour orientation varies; use normal direction modulo 180 then fold
        a = np.degrees(np.arctan2(d[:, 1], d[:, 0])) + 90
        angs.append(a)
        lens.append(L)
    return np.mod(np.concatenate(angs), 180), np.concatenate(lens)


def perimeter(lab, p, s=1.0):
    up = smooth_ind(lab, p, s)
    gen = contourpy.contour_generator(z=up)
    return sum(np.hypot(*np.diff(l, axis=0).T).sum() for l in gen.lines(0.5))
