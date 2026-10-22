# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Density-based topology optimization of a single-layer copper power pour.

What it computes (all on one 24 x 14 mm board region, 1 oz copper, one source
pad feeding three loads A=3 A, B=2 A, C=1 A, a mounting-hole keep-out):

1. A "human" baseline: trunk + 45-degree branches sized by IPC-2221-ish widths.
2. A full pour (every allowed cell is copper): the lower bound on DC loss.
3. SIMP topology optimization (density filter + Heaviside projection with beta
   continuation, optimality-criteria update) that minimizes DC copper loss
   (compliance-like, self-adjoint) at the SAME copper area as the baseline,
   plus an area sweep.
4. Two multi-physics variants:
   - "price": copper inside a signal-routing corridor costs 4x area (soft keep-out);
   - "slot": the reference plane under the pour has a slot; the objective adds
     the high-frequency loop inductance (sheet impedance j*w*mu0*h_eff) to DC loss.
5. Adjoint sensitivities on the baseline: adjoint-vs-finite-difference check for
   the IR drop at load A, and adjoint-guided copper growth vs uniform widening.
6. Legalization: threshold, island removal, morphological close/open at the
   minimum width, polygonize with Shapely, round, re-rasterize, re-evaluate.
7. A thermal-relief resistance study and a DC-vs-inductive crossover table.

Physics: 2-D Laplace on bilinear Q4 elements; sheet conductance 1/R_s for DC
(R_s = rho_Cu / t), 1/(mu0*h_eff) per square for the inductive limit of a pour
over a reference plane at depth h_eff (parallel-plate, wide-conductor limit).

Run (about 6-10 minutes on one CPU core at h = 0.1 mm; about 1.5 minutes with --quick):
    python tools/research/physics/op_topopt_pour.py            # default h = 0.1 mm
    python tools/research/physics/op_topopt_pour.py --quick    # h = 0.2 mm, fewer runs
    python tools/research/physics/op_topopt_pour.py --export zone.txt  # KiCad zone text
Needs numpy, scipy, shapely >= 2.0, contourpy (ships with matplotlib). Deterministic (no random numbers).
"""
import argparse
import time

import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as spla
import shapely
from scipy import ndimage
from shapely.geometry import LineString, Point, box

MU0 = 4e-7 * np.pi
RS_1OZ = 1.72e-8 / 35e-6                    # ohm per square, 1 oz (35 um) copper
KE = np.array([[4, -1, -2, -1], [-1, 4, -1, -2], [-2, -1, 4, -1], [-1, -2, -1, 4]], float) / 6.0

BOARD = (24.0, 14.0)
SRC = (0.5, 5.5, 3.5, 8.5)
LOADS = [("A", (20.5, 0.5, 23.5, 3.5), 3.0), ("B", (20.5, 10.5, 23.5, 13.5), 2.0),
         ("C", (10.5, 11.0, 13.5, 13.5), 1.0)]
HOLE = (12.0, 7.0, 2.0)                     # keep-out circle (x, y, r incl. clearance), mm
CORRIDOR = (15.0, 0.0, 17.0, 14.0)          # routing corridor, copper priced 4x
SLOT = (16.0, 0.0, 17.0, 6.5)               # slot in the L2 reference plane
H_REF, H_SLOT = 0.1e-3, 1.5e-3              # reference depth (m): normal, over slot


class Grid:
    """Structured Q4 grid over the board with pads, keep-outs and the reduced system."""

    def __init__(self, h):
        self.h = h
        self.nx, self.ny = int(round(BOARD[0] / h)), int(round(BOARD[1] / h))
        nx, ny = self.nx, self.ny
        self.nel, self.nnod = nx * ny, (nx + 1) * (ny + 1)
        ex, ey = np.meshgrid(np.arange(nx), np.arange(ny), indexing="ij")
        ex, ey = ex.ravel(), ey.ravel()
        self.xc, self.yc = (ex + 0.5) * h, (ey + 0.5) * h
        n1 = ex * (ny + 1) + ey
        self.edof = np.stack([n1, n1 + ny + 1, n1 + ny + 2, n1 + 1], axis=1)
        nxn, nyn = np.meshgrid(np.arange(nx + 1), np.arange(ny + 1), indexing="ij")
        self.xn, self.yn = nxn.ravel() * h, nyn.ravel() * h

        def in_rect(x, y, r):
            return (x >= r[0] - 1e-9) & (x <= r[2] + 1e-9) & (y >= r[1] - 1e-9) & (y <= r[3] + 1e-9)

        self.in_rect = in_rect
        self.solid = in_rect(self.xc, self.yc, SRC)
        self.load_nodes, self.load_I = [], []
        for _, r, i in LOADS:
            self.solid |= in_rect(self.xc, self.yc, r)
            self.load_nodes.append(np.flatnonzero(in_rect(self.xn, self.yn, r)))
            self.load_I.append(i)
        self.void = np.hypot(self.xc - HOLE[0], self.yc - HOLE[1]) < HOLE[2]
        self.des = ~(self.solid | self.void)
        fixed = np.flatnonzero(in_rect(self.xn, self.yn, SRC))
        self.free = np.setdiff1d(np.arange(self.nnod), fixed)
        self.f = np.zeros(self.nnod)
        for nodes, i in zip(self.load_nodes, self.load_I):
            self.f[nodes] -= i / len(nodes)       # loads draw current; source pad at 0 V
        self.itot = sum(self.load_I)
        # reduced-system sparsity pattern
        red = -np.ones(self.nnod, int)
        red[self.free] = np.arange(len(self.free))
        ik = np.repeat(self.edof, 4, axis=1).ravel()
        jk = np.tile(self.edof, (1, 4)).ravel()
        keep = (red[ik] >= 0) & (red[jk] >= 0)
        self.keep, self.ri, self.rj, self.nf = keep, red[ik[keep]], red[jk[keep]], len(self.free)

    def solve(self, coef, rhs_extra=None):
        """Solve K(coef) u = f; coef is per-element sheet coefficient (S/sq or 1/H per sq)."""
        sk = (coef[:, None] * KE.ravel()[None, :]).ravel()[self.keep]
        k = sp.csc_matrix((sk, (self.ri, self.rj)), shape=(self.nf, self.nf))
        lu = spla.splu(k, permc_spec="MMD_AT_PLUS_A")
        u = np.zeros(self.nnod)
        u[self.free] = lu.solve(self.f[self.free])
        out = [u]
        if rhs_extra is not None:
            lam = np.zeros(self.nnod)
            lam[self.free] = lu.solve(rhs_extra[self.free])
            out.append(lam)
        return out

    def elem_energy(self, u, v=None):
        ue = u[self.edof]
        ve = ue if v is None else v[self.edof]
        return np.einsum("ei,ij,ej->e", ue, KE, ve)

    def rasterize(self, geom):
        return shapely.contains_xy(geom, self.xc, self.yc)


def evaluate(g, cu, coef0=None):
    """Binary copper mask -> loss-equivalent R (mOhm), per-load drop (mV), solve time."""
    coef0 = np.full(g.nel, 1.0 / RS_1OZ) if coef0 is None else coef0
    coef = np.where(cu, coef0, 1e-9 * coef0.max())
    t = time.process_time()
    (u,) = g.solve(coef)
    dt = time.process_time() - t
    c = g.f @ u
    drops = [-u[n].mean() * 1e3 for n in g.load_nodes]
    return c / g.itot**2, drops, dt, u


def build_filter(g, rmin_mm):
    r = rmin_mm / g.h
    ri = int(np.ceil(r)) - 1
    ex, ey = np.divmod(np.arange(g.nel), g.ny)
    rows, cols, vals = [], [], []
    for dx in range(-ri, ri + 1):
        for dy in range(-ri, ri + 1):
            w = r - np.hypot(dx, dy)
            if w <= 0:
                continue
            jx, jy = ex + dx, ey + dy
            ok = (jx >= 0) & (jx < g.nx) & (jy >= 0) & (jy < g.ny)
            rows.append(np.flatnonzero(ok))
            cols.append(jx[ok] * g.ny + jy[ok])
            vals.append(np.full(ok.sum(), w))
    hm = sp.csr_matrix((np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))),
                       shape=(g.nel, g.nel))
    return hm, np.asarray(hm.sum(1)).ravel()


def project(xt, beta, eta=0.5):
    tb, den = np.tanh(beta * eta), np.tanh(beta * eta) + np.tanh(beta * (1 - eta))
    th = np.tanh(beta * (xt - eta))
    return (tb + th) / den, beta * (1 - th**2) / den


def topopt(g, area_mm2, coefs, weights, price=None, rmin_mm=0.5, iters=200, p=3.0, log=False):
    """Minimize sum_i w_i c_i / c_i(full pour) s.t. sum(price * rho) * h^2 <= area_mm2."""
    hm, hs = build_filter(g, rmin_mm)
    a = np.ones(g.nel) if price is None else price
    a2 = a * g.h**2
    budget = area_mm2 - a2[g.solid].sum()
    full = ~g.void
    cref = [g.f @ g.solve(np.where(full, c0, 1e-9 * c0.max()))[0] for c0 in coefs]
    x = np.zeros(g.nel)
    x[g.solid] = 1.0
    x[g.des] = np.clip(budget / a2[g.des].sum(), 0.01, 1.0)
    beta, t0, it_beta = 1.0, time.process_time(), 0
    for it in range(iters):
        xt = (hm @ x) / hs
        rho, drho = project(xt, beta)
        rho[g.solid], rho[g.void] = 1.0, 0.0
        drho[~g.des] = 0.0
        obj, dobj = 0.0, np.zeros(g.nel)
        for c0, w, cr in zip(coefs, weights, cref):
            cmin = 1e-6 * c0.max()
            (u,) = g.solve(cmin + rho**p * (c0 - cmin))
            ce = g.elem_energy(u)
            obj += w * (g.f @ u) / cr
            dobj += w * (-p * rho ** (p - 1) * (c0 - cmin) * ce) / cr
        dc = hm.T @ (dobj * drho / hs)
        dv = hm.T @ (a2 * drho / hs)
        dc, dv = np.minimum(dc, -1e-30), np.maximum(dv, 1e-30)
        move = 0.2 if beta < 8 else 0.1
        lo, hi = 1e-20, 1e20
        while hi / lo > 1 + 1e-6:
            lm = np.sqrt(lo * hi)
            xn = x.copy()
            xn[g.des] = np.clip(x[g.des] * np.sqrt(-dc[g.des] / (lm * dv[g.des])),
                                np.maximum(0, x[g.des] - move), np.minimum(1, x[g.des] + move))
            rn, _ = project((hm @ xn) / hs, beta)
            if (a2 * rn)[g.des].sum() > budget:
                lo = lm
            else:
                hi = lm
        change, x = np.abs(xn - x).max(), xn
        it_beta += 1
        if beta < 32 and (it_beta >= 40 or change < 0.01) and it > 30:
            beta, it_beta = beta * 2, 0
        if log and it % 25 == 0:
            print(f"    it {it:3d} obj {obj:.4f} beta {beta:4.0f} change {change:.3f}")
    xt = (hm @ x) / hs
    rho, _ = project(xt, beta)
    rho[g.solid], rho[g.void] = 1.0, 0.0
    gray = 4 * np.mean((rho * (1 - rho))[g.des])
    return rho, (time.process_time() - t0) / iters, gray


def human_layout(g):
    """Trunk + 45-degree branches, widths ~IPC-2221 10 C x 1.1-1.5 (6 A trunk, 3 A, 3 A, 2 A)."""
    segs = [([(2.0, 7.0), (7.0, 7.0)], 4.0),
            ([(7.0, 7.0), (11.5, 2.5), (22.0, 2.5)], 2.0),
            ([(7.0, 7.0), (12.0, 12.0)], 2.0),
            ([(12.0, 12.0), (22.0, 12.0)], 1.5)]
    geom = shapely.union_all([LineString(p).buffer(w / 2, cap_style="square", join_style="mitre")
                              for p, w in segs] + [box(*SRC)] + [box(*r) for _, r, _ in LOADS])
    geom = geom.intersection(box(0, 0, *BOARD)).difference(Point(HOLE[:2]).buffer(HOLE[2]))
    return g.rasterize(geom) | g.solid


def connected_to_pads(g, cu):
    lab, _ = ndimage.label(cu.reshape(g.nx, g.ny))
    lab = lab.ravel()
    keep = np.unique(lab[g.solid & cu])
    return cu & np.isin(lab, keep[keep > 0])


def disk(r_cells):
    r = int(np.ceil(r_cells))
    yy, xx = np.mgrid[-r:r + 1, -r:r + 1]
    return (xx**2 + yy**2) <= r_cells**2 + 1e-9


def min_feature(g, cu, frac=0.02):
    """Largest opening diameter (mm) that keeps every load connected and removes < frac of area."""
    best = 0.0
    m = cu.reshape(g.nx, g.ny)
    for d in np.arange(g.h, 2.0 + 1e-9, g.h):
        op = ndimage.binary_opening(m, structure=disk(d / 2 / g.h)).ravel() | g.solid
        op = connected_to_pads(g, op)
        lab, _ = ndimage.label(op.reshape(g.nx, g.ny))
        lab = lab.ravel()
        src_lab = lab[g.in_rect(g.xc, g.yc, SRC)][0]
        ok = all(lab[g.in_rect(g.xc, g.yc, r)][0] == src_lab for _, r, _ in LOADS)
        if not ok or (cu.sum() - op.sum()) > frac * cu.sum():
            break
        best = d
    return best


def legalize(g, rho, w_min=0.5, gap_min=0.5, simplify=0.01):
    """Density -> DRC-friendly polygon (all steps are Minkowski/morphological on polygons):
    marching-squares contour of the density at 0.5 (contourpy), keep pad-connected islands,
    closing by gap_min (fills slots/notches narrower than gap_min), opening by w_min (removes
    necks/slivers narrower than w_min) with round joins, keep-out and board clip, simplify."""
    import contourpy
    nodal = np.zeros((g.nx + 1, g.ny + 1))
    cnt = np.zeros_like(nodal)
    r2 = rho.reshape(g.nx, g.ny)
    for dx in (0, 1):
        for dy in (0, 1):
            nodal[dx:dx + g.nx, dy:dy + g.ny] += r2
            cnt[dx:dx + g.nx, dy:dy + g.ny] += 1
    nodal /= cnt
    xs, ys = np.arange(g.nx + 1) * g.h, np.arange(g.ny + 1) * g.h
    gen = contourpy.contour_generator(xs, ys, nodal.T, fill_type="OuterOffset")
    polys = []
    for pts, offs in zip(*gen.filled(0.5, 2.0)):
        rings = [pts[offs[i]:offs[i + 1]] for i in range(len(offs) - 1)]
        if len(rings[0]) >= 4:
            polys.append(shapely.Polygon(rings[0], [r for r in rings[1:] if len(r) >= 4]).buffer(0))
    pads = shapely.union_all([box(*SRC)] + [box(*r) for _, r, _ in LOADS])
    raw = shapely.union_all(polys + [pads])
    keep_out = Point(HOLE[:2]).buffer(HOLE[2], quad_segs=16)

    def pad_connected(geom):
        parts = list(geom.geoms) if hasattr(geom, "geoms") else [geom]
        return shapely.union_all([q for q in parts if q.intersects(pads)])

    raw = pad_connected(raw)
    poly = raw.buffer(gap_min / 2, quad_segs=8).buffer(-gap_min / 2, quad_segs=8)       # closing
    poly = poly.buffer(-w_min / 2, quad_segs=8).buffer(w_min / 2, quad_segs=8)          # opening
    poly = poly.difference(keep_out).intersection(box(0, 0, *BOARD))
    poly = pad_connected(shapely.union_all([poly, pads])).simplify(simplify)
    sliver = raw.difference(raw.buffer(-w_min / 2).buffer(w_min / 2)).area           # sub-w_min copper
    return poly, g.rasterize(poly) | g.solid, raw, sliver


def kicad_zone(poly, net="+5V", layer="F.Cu", origin=(100.0, 100.0)):
    """Return KiCad 8/9 zone S-expression text (y flipped) for the largest polygon."""
    geoms = list(poly.geoms) if hasattr(poly, "geoms") else [poly]
    main = max(geoms, key=lambda q: q.area)
    pts = " ".join(f"(xy {origin[0] + x:.4f} {origin[1] + BOARD[1] - y:.4f})"
                   for x, y in list(main.exterior.coords)[:-1])
    return (f'(zone (net 0) (net_name "{net}") (layer "{layer}") (hatch edge 0.5)\n'
            f'  (connect_pads yes (clearance 0.2)) (min_thickness 0.25)\n'
            f'  (fill yes (thermal_gap 0.5) (thermal_bridge_width 0.5) (island_removal_mode 0))\n'
            f'  (polygon (pts {pts})))\n'), len(main.exterior.coords) - 1, len(main.interiors)


def adjoint_study(g, cu):
    """Adjoint IR-drop gradient check and adjoint-guided growth vs uniform widening."""
    g0 = 1.0 / RS_1OZ
    coef = np.where(cu, g0, 1e-9 * g0)
    sel = np.zeros(g.nnod)
    sel[g.load_nodes[0]] = -1.0 / len(g.load_nodes[0])   # J = drop at A = -mean(u_A)
    u, lam = g.solve(coef, rhs_extra=sel)
    dJ = g.elem_energy(u, lam)          # dJ/dcoef_e = -lam^T KE u ... sign folded below
    dJ = -dJ
    j0 = sel @ u
    cand = np.flatnonzero(cu & g.des)
    test = cand[np.argsort(dJ[cand])[[0, len(cand) // 2, -1]]]
    errs = []
    for e in test:                       # central finite difference, +-0.1 %
        jj = []
        for s in (1.001, 0.999):
            c2 = coef.copy()
            c2[e] *= s
            jj.append(sel @ g.solve(c2)[0])
        fd = (jj[0] - jj[1]) / (0.002 * coef[e])
        errs.append(abs(fd - dJ[e]) / max(abs(fd), 1e-30))
    # growth: add boundary void cells ranked by DC-loss topological sensitivity
    r0 = evaluate(g, cu)[0]
    add_target = int(0.25 * cu.sum())
    grown, added = cu.copy(), 0
    while added < add_target:
        (u,) = g.solve(np.where(grown, g0, 1e-9 * g0))
        sens = g.elem_energy(u)          # loss decrease ~ (G_cu - G_void) * u^T KE u
        ring = ndimage.binary_dilation(grown.reshape(g.nx, g.ny)).ravel() & ~grown & g.des
        idx = np.flatnonzero(ring)
        k = min(max(1, add_target // 10), add_target - added, len(idx))
        grown[idx[np.argsort(-sens[idx])[:k]]] = True
        added += k
    r_grow = evaluate(g, grown)[0]
    wid, n = cu.copy(), 0
    while wid.sum() - cu.sum() < add_target and n < 50:
        nxt = ndimage.binary_dilation(wid.reshape(g.nx, g.ny)).ravel() & g.des | wid
        if nxt.sum() - cu.sum() > add_target:   # partial ring: take cells in index order
            ring = np.flatnonzero(nxt & ~wid)
            nxt = wid.copy()
            nxt[ring[:add_target - (wid.sum() - cu.sum())]] = True
        wid, n = nxt, n + 1
    r_wid = evaluate(g, wid)[0]
    rho_t, _, _ = topopt(g, grown.sum() * g.h**2, [np.full(g.nel, g0)], [1.0], iters=120)
    r_topo = evaluate(g, connected_to_pads(g, (rho_t > 0.5) | g.solid))[0]
    # removal: drop the 20% least-loaded non-pad copper cells
    (u,) = g.solve(coef)
    en = g.elem_energy(u)
    body = np.flatnonzero(cu & g.des)
    rem = cu.copy()
    rem[body[np.argsort(en[body])[: int(0.2 * len(body))]]] = False
    rem = connected_to_pads(g, rem)
    r_rem = evaluate(g, rem)[0]
    return dict(j0_mV=j0 * 1e3, grad_rel_err=max(errs), r0=r0, r_grow=r_grow, r_wid=r_wid, r_topo=r_topo,
                added_mm2=add_target * g.h**2, r_remove20=r_rem, removed_mm2=(cu.sum() - rem.sum()) * g.h**2)


def beso_from_full(g, area_mm2, step=0.08):
    """Greedy hard-kill removal (ESO/BESO style): from the full pour, repeatedly delete the
    least-loaded copper cells (energy density), re-solve, until the area target is met."""
    g0 = 1.0 / RS_1OZ
    cu, n = ~g.void, 0
    target = int(round(area_mm2 / g.h**2))
    while cu.sum() > target:
        (u,) = g.solve(np.where(cu, g0, 1e-9 * g0))
        en = g.elem_energy(u)
        body = np.flatnonzero(cu & g.des)
        k = min(int(step * cu.sum()), cu.sum() - target)
        cu = cu.copy()
        cu[body[np.argsort(en[body])[:k]]] = False
        cu = connected_to_pads(g, cu)
        n += 1
    return cu, n


def relief_study(h=0.025, size=8.0, pad=2.0, gap=0.4, spoke=0.3):
    """Added resistance of a thermal relief around a 2x2 mm pad in a pour (1 oz)."""
    n = int(round(size / h))
    xc = (np.arange(n) + 0.5) * h
    X, Y = np.meshgrid(xc, xc, indexing="ij")
    dx, dy = np.abs(X - size / 2).ravel(), np.abs(Y - size / 2).ravel()
    inpad = (dx <= pad / 2) & (dy <= pad / 2)
    ring = (np.maximum(dx, dy) <= pad / 2 + gap) & ~inpad
    res = {}
    for name, nsp in [("solid", None), ("4 spokes", 4), ("2 spokes", 2)]:
        cu = np.ones(n * n, bool)
        if nsp:
            sp_mask = (dy <= spoke / 2) | ((dx <= spoke / 2) if nsp == 4 else False)
            cu &= ~(ring & ~sp_mask)
        res[name] = _pad_resistance(n, h, cu, inpad)
    return res


def _pad_resistance(n, h, cu, inpad):
    ex, ey = np.divmod(np.arange(n * n), n)
    n1 = ex * (n + 1) + ey
    edof = np.stack([n1, n1 + n + 1, n1 + n + 2, n1 + 1], 1)
    coef = np.where(cu, 1 / RS_1OZ, 1e-9 / RS_1OZ)
    nn = (n + 1) ** 2
    k = sp.csc_matrix(((coef[:, None] * KE.ravel()).ravel(),
                       (np.repeat(edof, 4, 1).ravel(), np.tile(edof, (1, 4)).ravel())), shape=(nn, nn))
    ix, iy = np.divmod(np.arange(nn), n + 1)
    pad_nodes = np.unique(edof[inpad])
    edge = np.flatnonzero((ix == 0) | (iy == 0) | (ix == n) | (iy == n))
    fixed = np.union1d(pad_nodes, edge)
    free = np.setdiff1d(np.arange(nn), fixed)
    u = np.zeros(nn)
    u[edge] = 1.0                               # 1 V between pour edge and pad
    rhs = -k[free][:, fixed] @ u[fixed]
    u[free] = spla.spsolve(k[free][:, free].tocsc(), rhs)
    i = (k @ u)[pad_nodes].sum()                 # current into the pad
    return -1.0 / i * 1e3                        # mOhm


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--h", type=float, default=0.1, help="grid pitch, mm")
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--export", default=None, help="write KiCad zone S-expression here")
    a = ap.parse_args()
    h = 0.2 if a.quick else a.h
    print(f"R_s(1 oz) = {RS_1OZ * 1e3:.3f} mOhm/sq; crossover f_c = R_s/(2 pi mu0 h):")
    for oz, t in [(0.5, 17.5e-6), (1, 35e-6), (2, 70e-6)]:
        rs = 1.72e-8 / t
        row = ", ".join(f"h={hh * 1e3:.2f} mm: {rs / (2 * np.pi * MU0 * hh) / 1e3:6.0f} kHz"
                        for hh in (0.1e-3, 0.2e-3, 0.36e-3, 1.5e-3))
        print(f"  {oz} oz: {row}")

    g = Grid(h)
    print(f"\nGrid h={h} mm: {g.nx}x{g.ny} = {g.nel} elements, {g.nnod} nodes")
    hum = human_layout(g)
    area_h = hum.sum() * h**2
    r_h, d_h, t_h, _ = evaluate(g, hum)
    r_f, d_f, _, _ = evaluate(g, ~g.void)
    print(f"solve time (one LU solve): {t_h * 1e3:.0f} ms")
    print(f"human trunk+branches: area {area_h:6.1f} mm2  R_loss {r_h * 1e3:.3f} mOhm  "
          f"drops A/B/C {d_h[0]:.1f}/{d_h[1]:.1f}/{d_h[2]:.1f} mV  P {r_h * 36 * 1e3:.0f} mW")
    print(f"full pour           : area {(~g.void).sum() * h**2:6.1f} mm2  R_loss {r_f * 1e3:.3f} mOhm  "
          f"drops A/B/C {d_f[0]:.1f}/{d_f[1]:.1f}/{d_f[2]:.1f} mV")

    g0 = np.full(g.nel, 1.0 / RS_1OZ)
    rho, t_it, gray = topopt(g, area_h, [g0], [1.0], rmin_mm=0.5, iters=200 if not a.quick else 150)
    cu = connected_to_pads(g, (rho > 0.5) | g.solid)
    r_o, d_o, _, _ = evaluate(g, cu)
    print(f"topopt equal area   : area {cu.sum() * h**2:6.1f} mm2  R_loss {r_o * 1e3:.3f} mOhm  "
          f"drops A/B/C {d_o[0]:.1f}/{d_o[1]:.1f}/{d_o[2]:.1f} mV  ({t_it * 1e3:.0f} ms/iter, gray {gray:.3f}, "
          f"min feature {min_feature(g, cu):.2f} mm)")
    print(ascii_render(g, cu))

    poly, cu_l, raw, sliver = legalize(g, rho)
    r_l, d_l, _, _ = evaluate(g, cu_l)
    txt, nv, nh = kicad_zone(poly)
    print(f"legalized (contour at 0.5, close/open 0.5 mm, round joins): area {poly.area:6.1f} mm2  "
          f"R_loss {r_l * 1e3:.3f} mOhm ({(r_l / r_o - 1) * 100:+.1f}%), polygon {nv} vertices, {nh} holes, "
          f"sub-0.5 mm copper before legalization {sliver:.2f} mm2")
    if a.export:
        with open(a.export, "w") as fh:
            fh.write(txt)
        print(f"  wrote {a.export}")

    print("\nLow-area thin-feature design (15% excess copper over pads, filter radius 0.2 mm), "
          "legalized at w,gap >= 0.5 mm and at 1.0 mm:")
    a_lo = 34.5 + 0.15 * ((~g.void).sum() * h**2 - 34.5)
    rho_t, _, _ = topopt(g, a_lo, [g0], [1.0], rmin_mm=0.2, iters=150)
    cu_t = connected_to_pads(g, (rho_t > 0.5) | g.solid)
    r_t = evaluate(g, cu_t)[0]
    print(f"  raw threshold: R_loss {r_t * 1e3:.3f} mOhm, min feature {min_feature(g, cu_t):.2f} mm, "
          f"area {cu_t.sum() * h**2:.1f} mm2")
    print(ascii_render(g, cu_t))
    for wm in (0.5, 1.0):
        pl, cu_tl, _, sl = legalize(g, rho_t, w_min=wm, gap_min=wm)
        r_tl = evaluate(g, cu_tl)[0]
        tag = "DISCONNECTED (a neck narrower than w_min was cut)" if r_tl > 1 else \
            f"{r_tl * 1e3:.3f} mOhm ({(r_tl / r_t - 1) * 100:+.1f}%)"
        print(f"  legalized w,gap>={wm} mm: R_loss {tag}, area {pl.area:.1f} mm2, "
              f"sub-{wm} mm copper removed {sl:.2f} mm2")
    rho_w, _, _ = topopt(g, a_lo, [g0], [1.0], rmin_mm=1.0, iters=150)
    cu_w = connected_to_pads(g, (rho_w > 0.5) | g.solid)
    pl, cu_wl, _, sl = legalize(g, rho_w, w_min=1.0, gap_min=1.0)
    r_w, r_wl = evaluate(g, cu_w)[0], evaluate(g, cu_wl)[0]
    tag = "DISCONNECTED" if r_wl > 1 else f"{r_wl * 1e3:.3f} mOhm ({(r_wl / r_w - 1) * 100:+.1f}%)"
    print(f"  re-optimized with filter radius 1.0 mm: raw R_loss {r_w * 1e3:.3f} mOhm, min feature "
          f"{min_feature(g, cu_w):.2f} mm; legalized at 1.0 mm: {tag}, sub-1.0 mm copper removed {sl:.2f} mm2")

    cu_b, nb = beso_from_full(g, area_h)
    print(f"\nGreedy energy-ranked removal from full pour to equal area ({nb} re-solves): "
          f"R_loss {evaluate(g, cu_b)[0] * 1e3:.3f} mOhm, area {cu_b.sum() * h**2:.1f} mm2")

    print("\nArea sweep (DC loss only; area includes 34.5 mm2 of pads):")
    full_area = (~g.void).sum() * h**2
    for frac in ([0.25, 0.35, 0.5] if a.quick else [0.2, 0.3, 0.5, 0.7]):
        rho_s, _, _ = topopt(g, frac * full_area, [g0], [1.0], iters=100)
        cu_s = connected_to_pads(g, (rho_s > 0.5) | g.solid)
        r_s = evaluate(g, cu_s)[0]
        tag = "DISCONNECTED" if r_s > 1 else f"{r_s * 1e3:.3f} mOhm = {r_s / r_f:.2f} x full pour"
        print(f"  area {frac:4.0%} ({cu_s.sum() * h**2:6.1f} mm2): R_loss {tag}")

    print("\nVariant 'price': copper in corridor x=15..17 mm costs 4x area")
    price = np.where(g.in_rect(g.xc, g.yc, CORRIDOR), 4.0, 1.0)
    rho_p, _, _ = topopt(g, area_h, [g0], [1.0], price=price, iters=150)
    cu_p = connected_to_pads(g, (rho_p > 0.5) | g.solid)
    corr = g.in_rect(g.xc, g.yc, CORRIDOR)
    print(f"  R_loss {evaluate(g, cu_p)[0] * 1e3:.3f} mOhm; copper in corridor "
          f"{(cu_p & corr).sum() * h**2:.1f} mm2 (unpriced run: {(cu & corr).sum() * h**2:.1f} mm2)")
    print(ascii_render(g, cu_p))

    print("\nVariant 'slot': L2 reference slot at x=16..17, y<6.5; objective = DC + HF inductance")
    hmap = np.where(g.in_rect(g.xc, g.yc, SLOT), H_SLOT, H_REF)
    gl = 1.0 / (MU0 * hmap)
    results = {}
    for name, w in [("DC only", (1.0, 0.0)), ("50/50", (0.5, 0.5)), ("L only", (0.0, 1.0))]:
        coefs, ws = [g0, gl], list(w)
        rho_v, _, _ = topopt(g, area_h, coefs, ws, iters=100)
        cu_v = connected_to_pads(g, (rho_v > 0.5) | g.solid)
        r_v = evaluate(g, cu_v)[0]
        l_v = evaluate(g, cu_v, coef0=gl)[0]
        results[name] = cu_v
        print(f"  {name:8s}: R_loss {r_v * 1e3:.3f} mOhm  L_eff {l_v * 1e9:.3f} nH  "
              f"copper over slot {(cu_v & g.in_rect(g.xc, g.yc, SLOT)).sum() * h**2:.1f} mm2")
    print(f"  human layout: L_eff {evaluate(g, hum, coef0=gl)[0] * 1e9:.3f} nH")
    print(ascii_render(g, results["L only"]))

    print("\nAdjoint study on the human layout:")
    ad = adjoint_study(g, hum)
    print(f"  drop at A {ad['j0_mV']:.2f} mV; adjoint vs finite-difference max rel err {ad['grad_rel_err']:.2e}")
    print(f"  add {ad['added_mm2']:.1f} mm2: adjoint-guided growth R {ad['r0'] * 1e3:.3f} -> {ad['r_grow'] * 1e3:.3f} "
          f"mOhm; uniform widening -> {ad['r_wid'] * 1e3:.3f} mOhm; topopt at that area -> {ad['r_topo'] * 1e3:.3f}")
    print(f"  remove 20% least-loaded copper ({ad['removed_mm2']:.1f} mm2): R -> {ad['r_remove20'] * 1e3:.3f} mOhm")

    print("\nThermal relief around a 2x2 mm pad in an 8x8 mm 1 oz pour (gap 0.4, spoke 0.3 mm):")
    rel = relief_study()
    for k, v in rel.items():
        print(f"  {k:9s}: {v:.3f} mOhm (pad to pour edge)  +{v - rel['solid']:.3f} vs solid")

    if not a.quick:
        print("\nRuntime vs grid (one LU solve; topopt iteration = 1 solve + filter + OC):")
        for hh in (0.4, 0.2, 0.1, 0.05):
            gg = Grid(hh)
            hu = human_layout(gg)
            r_, _, t_, _ = evaluate(gg, hu)
            _, ti, _ = topopt(gg, hu.sum() * hh**2, [np.full(gg.nel, 1 / RS_1OZ)], [1.0], iters=8)
            print(f"  h={hh:4.2f} mm {gg.nx:4d}x{gg.ny:<4d} nodes {gg.nnod:7d}: solve {t_ * 1e3:7.1f} ms, "
                  f"iter {ti * 1e3:7.1f} ms, human R_loss {r_ * 1e3:.3f} mOhm")


def ascii_render(g, cu, cols=60):
    """Coarse ASCII picture: '#' copper, 'o' keep-out, '.' empty; y up."""
    step = g.nx / cols
    rows = int(round(g.ny / step / 2))
    m, v = cu.reshape(g.nx, g.ny), g.void.reshape(g.nx, g.ny)
    lines = []
    for r in range(rows - 1, -1, -1):
        y0, y1 = int(r * 2 * step), int((r + 1) * 2 * step)
        s = ""
        for c in range(cols):
            x0, x1 = int(c * step), int((c + 1) * step)
            blk = m[x0:x1, y0:y1]
            s += "#" if blk.mean() > 0.5 else ("o" if v[x0:x1, y0:y1].mean() > 0.5 else ".")
        lines.append("    " + s)
    return "\n".join(lines)


if __name__ == "__main__":
    main()
