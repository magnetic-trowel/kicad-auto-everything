# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Discretization error control for the physics engine: certified pixel brackets and via wells.

Prefix eng (physics-engine design): docs/topics/architecture/physics-engine-design-details.md.

Sections (python eng_discretization.py [bracket|wells|all]):

  bracket  A certified two-sided bound on a sheet resistance from rasters alone. Rayleigh
           monotonicity (more conductor or larger electrodes never raise a self resistance)
           and the two complementary variational principles give
               R(outer pixels, potential Q4) <= R(outer) <= R(true) <= R(inner) <= R(inner, stream Q4)
           where 'inner' keeps the pixels entirely inside the copper and 'outer' every pixel that
           touches it. Test: a quarter annulus 1 < r < 2 between its two straight edges, exact
           R = (pi/2)/ln 2 = 2.26618 squares; the grid is axis-aligned, the arcs are not. Also
           shown: the coverage-weighted cell-centred graph (the rasterizer of rb_board_passports)
           on the true geometry, an estimate with no guarantee, and the same-geometry
           Prager-Synge bracket (vp_floors), which certifies only the pixel geometry.
  wells    Peaceman's well constant for a via much thinner than a cell: the potential of a
           unit point source at its own node equals the continuum potential at r_e = c * dx.
           Computed for the 5-point (cell-centred graph) and Q4 (bilinear) stencils from a
           large Dirichlet box, against e^-gamma / (2 sqrt 2) = 0.1985 for the 5-point stencil.
           Then a 0.3 mm via in a 1 oz plane, ring electrode at 5 mm: spreading resistance
           R_s/(2 pi) ln(R/r_w) exact vs a 0.2 mm grid with a Peaceman well, vs the same grid
           with the via tied to every cell its barrel touches (no well model).

numpy + scipy (+ shapely for coverage); reuses vp_floors._q4_energy_solve. About 30 s on one
core; deterministic. Numbers quoted [C] in the engine design docs come from here.
"""
import os

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")

import math  # noqa: E402
import sys  # noqa: E402

import numpy as np  # noqa: E402
import scipy.sparse as sp  # noqa: E402
import scipy.sparse.linalg as spla  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vp_floors  # noqa: E402  (Q4 energy solve on a pixel mask)

R_EXACT = (math.pi / 2) / math.log(2.0)
A_IN, B_OUT = 1.0, 2.0


# ---------------------------------------------------------------------------- bracket
def annulus_masks(n):
    """Inner and outer pixel approximations of the quarter annulus, n pixels per unit length."""
    m = int(math.ceil(B_OUT * n)) + 1
    i = np.arange(m)
    x0, x1 = i / n, (i + 1) / n
    X0, Y0 = np.meshgrid(x0, x0)
    X1, Y1 = np.meshgrid(x1, x1)
    rmin = np.hypot(X0, Y0)                  # first quadrant: nearest corner to the origin
    rmax = np.hypot(X1, Y1)
    inner = (rmin >= A_IN) & (rmax <= B_OUT)
    outer = (rmax > A_IN) & (rmin < B_OUT)
    return inner, outer


def coverage(n, ss=8):
    m = int(math.ceil(B_OUT * n)) + 1
    sub = (np.arange(ss) + 0.5) / ss
    xs = ((np.arange(m)[:, None] + sub[None, :]) / n).ravel()
    X, Y = np.meshgrid(xs, xs)
    R = np.hypot(X, Y)
    inside = (R > A_IN) & (R < B_OUT)
    cov = inside.reshape(m, ss, m, ss).mean(axis=(1, 3))
    # face coverage: fraction of each vertical face (x = (i+1)/n) and horizontal face inside
    yf = xs
    xf = (np.arange(1, m) / n)
    Xf, Yf = np.meshgrid(xf, yf)
    fx = ((np.hypot(Xf, Yf) > A_IN) & (np.hypot(Xf, Yf) < B_OUT)).reshape(m, ss, m - 1).mean(axis=1)
    fy = fx.T.copy()                           # symmetric geometry: horizontal faces mirror vertical ones
    # boundary faces on the axes (electrodes): x = 0 column faces and y = 0 row faces
    x0f = ((np.hypot(np.zeros_like(yf), yf) > A_IN) & (yf < B_OUT)).reshape(m, ss).mean(axis=1)
    return cov, fx, fy, x0f


def fv_graph_resistance(n):
    """Cell-centred coverage-weighted graph (as rb_board_passports.build_dc), electrodes on the axes."""
    cov, fx, fy, x0f = coverage(n)
    m = cov.shape[0]
    live = cov > 0
    live[:, :-1] |= fx > 0
    live[:, 1:] |= fx > 0
    live[:-1, :] |= fy > 0
    live[1:, :] |= fy > 0
    ids = -np.ones((m, m), int)
    ids[live] = np.arange(live.sum())
    nn = int(live.sum()) + 2
    e1, e2 = nn - 2, nn - 1
    rows, cols, vals = [], [], []

    def add(a, b, g):
        rows.extend([a, b, a, b]); cols.extend([a, b, b, a]); vals.extend([g, g, -g, -g])
    for j in range(m):
        for i in range(m - 1):
            if fx[j, i] > 0 and ids[j, i] >= 0 and ids[j, i + 1] >= 0:
                add(ids[j, i], ids[j, i + 1], fx[j, i])
    for j in range(m - 1):
        for i in range(m):
            if fy[j, i] > 0 and ids[j, i] >= 0 and ids[j + 1, i] >= 0:
                add(ids[j, i], ids[j + 1, i], fy[j, i])
    for k in range(m):
        if x0f[k] > 0 and ids[k, 0] >= 0:        # x = 0 face of cell (row k, col 0): electrode 2 (phi = 1)
            add(ids[k, 0], e2, 2 * x0f[k])
        if x0f[k] > 0 and ids[0, k] >= 0:        # y = 0 face of cell (row 0, col k): electrode 1 (phi = 0)
            add(ids[0, k], e1, 2 * x0f[k])
    G = sp.coo_matrix((vals, (rows, cols)), shape=(nn, nn)).tocsr()
    keep = np.arange(nn - 1)                  # ground electrode 2's partner: solve with e2 driven
    rhs = np.zeros(nn - 1)
    rhs[e1] = 0.0
    # potential phi: e1 = 0 (grounded, removed), e2 = 1: inject unit current at e2, ground e1
    sel = np.r_[np.arange(nn - 2), e2]
    Gs = G[sel][:, sel].tocsc()
    b = np.zeros(len(sel))
    b[-1] = 1.0
    v = spla.spsolve(Gs, b)
    return float(v[-1])


def q4_bounds(mask, n):
    """Potential (lower R) and stream-function (upper R) Q4 solves on one pixel mask."""
    m = mask.shape[0]
    nj, ni = np.mgrid[0:m + 1, 0:m + 1]
    nid = (nj * (m + 1) + ni).ravel()
    used = np.zeros((m + 1) * (m + 1), int)
    cj, ci = np.nonzero(mask)
    for dj, di in ((0, 0), (0, 1), (1, 0), (1, 1)):
        np.add.at(used, (cj + dj) * (m + 1) + ci + di, 1)
    nj, ni = nj.ravel(), ni.ravel()
    # electrodes: nodes on the axes that belong to the mask's boundary
    on_y0 = (nj == 0) & (used > 0)
    on_x0 = (ni == 0) & (used > 0)
    g = vp_floors._q4_energy_solve(mask, np.r_[nid[on_y0], nid[on_x0]],
                                   np.r_[np.zeros(on_y0.sum()), np.ones(on_x0.sum())])
    # stream function: psi = 0 on the inner staircase, 1 on the outer staircase (boundary nodes off the axes)
    bnd = (used > 0) & (used < 4)
    r = np.hypot(ni / n, nj / n)
    off_axes = bnd & (ni > 0) & (nj > 0)
    # the axis end nodes belong to the arcs
    ends = bnd & ((ni == 0) | (nj == 0))
    ax_r = r[ends]
    ends_idx = nid[ends]
    inner_end = ends_idx[ax_r <= 1.5]
    outer_end = ends_idx[ax_r > 1.5]
    # keep only the extreme end nodes of each axis segment
    def extremes(idx, take_min):
        out = []
        for axis in (ni, nj):
            cand = [k for k in idx if axis[k] == 0]
            if cand:
                rr = [r[k] for k in cand]
                out.append(cand[int(np.argmin(rr) if take_min else np.argmax(rr))])
        return out
    inner_nodes = np.r_[nid[off_axes & (r <= 1.5)], extremes(inner_end, True)].astype(int)
    outer_nodes = np.r_[nid[off_axes & (r > 1.5)], extremes(outer_end, False)].astype(int)
    psi = vp_floors._q4_energy_solve(mask, np.r_[inner_nodes, outer_nodes],
                                     np.r_[np.zeros(len(inner_nodes)), np.ones(len(outer_nodes))])
    return 1.0 / g, psi


def sec_bracket():
    print("== bracket: certified sheet resistance from rasters (quarter annulus 1 < r < 2, exact "
          f"{R_EXACT:.5f} squares)")
    print("   n/unit  R_lo = phi-Q4(outer)  R_hi = psi-Q4(inner)  width   contains | pixel-geometry brackets:"
          " outer [lo, hi], inner [lo, hi] | cell graph on true geometry (no guarantee)")
    for n in (4, 8, 16, 32, 64):
        inner, outer = annulus_masks(n)
        lo_o, hi_o = q4_bounds(outer, n)
        lo_i, hi_i = q4_bounds(inner, n)
        fv = fv_graph_resistance(n)
        ok = lo_o <= R_EXACT <= hi_i
        print(f"   {n:5d}   {lo_o:10.5f}            {hi_i:10.5f}         {100 * (hi_i - lo_o) / R_EXACT:5.1f}%  "
              f"{'yes' if ok else 'NO ':3s}      | [{lo_o:.4f}, {hi_o:.4f}], [{lo_i:.4f}, {hi_i:.4f}]"
              f" | {fv:.5f} ({100 * (fv / R_EXACT - 1):+.2f}%)")


# ---------------------------------------------------------------------------- wells
def lattice(n, stencil):
    """Dirichlet box n x n (n odd), unit source at the centre; returns potential field."""
    idx = np.arange(n * n).reshape(n, n)
    rows, cols, vals = [], [], []

    def add(a, b, g):
        rows.extend([a, b, a, b]); cols.extend([a, b, b, a]); vals.extend([g, g, -g, -g])
    if stencil == '5pt':
        for a, b in ((idx[:, :-1], idx[:, 1:]), (idx[:-1, :], idx[1:, :])):
            add(a.ravel(), b.ravel(), np.ones(a.size))
    else:  # Q4 bilinear: edge -1/3... element KE: edge neighbours 1/6 + 1/6, diagonals 1/3 per element pair
        for a, b in ((idx[:, :-1], idx[:, 1:]), (idx[:-1, :], idx[1:, :])):
            add(a.ravel(), b.ravel(), np.full(a.size, 1.0 / 3.0))
        for a, b in ((idx[:-1, :-1], idx[1:, 1:]), (idx[:-1, 1:], idx[1:, :-1])):
            add(a.ravel(), b.ravel(), np.full(a.size, 1.0 / 3.0))
    rows = np.concatenate([np.ravel(x) for x in rows])
    cols = np.concatenate([np.ravel(x) for x in cols])
    vals = np.concatenate([np.ravel(x) for x in vals])
    G = sp.coo_matrix((vals, (rows, cols)), shape=(n * n, n * n)).tocsr()
    bnd = np.zeros((n, n), bool)
    bnd[0, :] = bnd[-1, :] = bnd[:, 0] = bnd[:, -1] = True
    free = np.nonzero(~bnd.ravel())[0]
    b = np.zeros(n * n)
    c = idx[n // 2, n // 2]
    b[c] = 1.0
    v = np.zeros(n * n)
    v[free] = spla.splu(G[free][:, free].tocsc()).solve(b[free])
    return v.reshape(n, n)


def well_constant(stencil, n=401):
    v = lattice(n, stencil)
    c = n // 2
    rs, ps = [], []
    for d in range(12, 60):
        for (dj, di) in ((0, d), (d, 0), (d, d)):
            r = math.hypot(dj, di)
            if r <= 60:
                rs.append(r)
                ps.append(v[c + dj, c + di])
    rs, ps = np.array(rs), np.array(ps)
    # far field: v = -(1/2pi) ln r + C (the box adds a smooth harmonic correction, small near the centre)
    C = np.mean(ps + np.log(rs) / (2 * math.pi))
    return math.exp(2 * math.pi * (C - v[c, c]))


def via_spreading(h=0.2, R=5.0, rw=0.15, rs=0.4914e-3):
    """Via (radius rw) at the centre of a disc plane, ring electrode at R; resistance in ohm."""
    exact = rs / (2 * math.pi) * math.log(R / rw)
    n = int(round(2 * R / h)) + 3
    if n % 2 == 0:
        n += 1
    c = n // 2
    jj, ii = np.mgrid[0:n, 0:n]
    x, y = (ii - c) * h, (jj - c) * h
    disc = np.hypot(x, y) < R
    idx = -np.ones((n, n), int)
    idx[disc] = np.arange(disc.sum())
    m = int(disc.sum())
    rows, cols, vals = [], [], []

    def add(a, b, g):
        rows.extend([a, b, a, b]); cols.extend([a, b, b, a]); vals.extend([g, g, -g, -g])
    for (a, b) in ((idx[:, :-1], idx[:, 1:]), (idx[:-1, :], idx[1:, :])):
        ok = (a >= 0) & (b >= 0)
        add(a[ok], b[ok], np.full(ok.sum(), 1.0 / rs))
    ring = disc & (np.hypot(x, y) >= R - h)        # outermost cells: the electrode
    out = {}
    for mode in ('peaceman', 'touch'):
        r_, c_, v_ = [np.concatenate([np.ravel(q) for q in z]) for z in (rows, cols, vals)]
        G = sp.coo_matrix((v_, (r_, c_)), shape=(m + 1, m + 1)).tolil()
        vn = m                                      # via node
        if mode == 'peaceman':
            g = 2 * math.pi / (rs * math.log(0.1985 * h / rw))
            cells = [idx[c, c]]
            gs = [g]
        else:                                       # every cell whose square the barrel overlaps, rigidly tied
            sel = (np.abs(x) <= rw + h / 2) & (np.abs(y) <= rw + h / 2) & disc
            cells = list(idx[sel])
            gs = [1e6 / rs] * len(cells)
        for cc, g in zip(cells, gs):
            G[vn, vn] += g; G[cc, cc] += g; G[vn, cc] -= g; G[cc, vn] -= g
        G = G.tocsr()
        free = np.r_[np.nonzero(~ring[disc])[0], vn]
        b = np.zeros(m + 1)
        b[vn] = 1.0
        v = np.zeros(m + 1)
        v[free] = spla.splu(G[free][:, free].tocsc()).solve(b[free])
        out[mode] = v[vn]
    return exact, out


def sec_wells():
    print("== wells: Peaceman equivalent radius r_e = c * dx of a point source at a grid node")
    c5 = well_constant('5pt')
    cq = well_constant('q4')
    print(f"   5-point stencil (cell-centred graph): c = {c5:.4f} (lattice Green function: e^-gamma/(2 sqrt 2) ="
          f" {math.exp(-0.5772156649) / (2 * math.sqrt(2)):.4f}); Q4 bilinear stencil: c = {cq:.4f}")
    for h in (0.2, 0.1):
        ex, o = via_spreading(h=h)
        print(f"   via r_w 0.15 mm in a 1 oz plane, ring at 5 mm, grid {h} mm: exact {ex * 1e6:.1f} uOhm; Peaceman well"
              f" {o['peaceman'] * 1e6:.1f} uOhm ({100 * (o['peaceman'] / ex - 1):+.1f}%); barrel tied to the cells it"
              f" touches {o['touch'] * 1e6:.1f} uOhm ({100 * (o['touch'] / ex - 1):+.1f}%)")


if __name__ == "__main__":
    which = sys.argv[1:] or ["all"]
    if "bracket" in which or "all" in which:
        sec_bracket()
    if "wells" in which or "all" in which:
        sec_wells()
