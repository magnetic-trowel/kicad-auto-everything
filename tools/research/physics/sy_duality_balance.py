# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Symmetry, reciprocity and duality checks for the round-2 SY lens (docs/topics/physics/lens-sy.md).

Quasi-static 2-D cross-section solves (graded finite-volume grid, Dirichlet conductors) and
small closed-form calculations. numpy/scipy only; about 1-2 minutes in total.

Sections (run all, or name them: python sy_duality_balance.py duality antenna pair):
  duality  A ground plane breaks electric/magnetic duality. Two strips over a plane:
           mutual capacitance C_m' and mutual inductance L_m' vs plane depth h for wide and
           narrow strips. Prediction (image theory): L_m' ~ mu0*h_a*h_v/(pi*D^2), independent of
           width; C_m' ~ eps0*w_a*w_v/(pi*D^2) for wide strips, independent of h.
           Also: does a grounded coplanar guard between them help?
  antenna  Reciprocity + the Maxwell edge distribution give the MREMC edge law. A trace over a
           finite plane (width W) inside a far "world" box: plane voltage per unit DM current
           L_ret(x) = L22 - L21 vs mu0*h_e/(2*pi*sqrt((W/2)^2 - x^2)); capacitive imbalance
           h_C(x) = C10/(C10+C20) vs w_e/(2*pi*sqrt((W/2)^2 - x^2)). L_ret scales with height,
           h_C with width (the duality break again).
  pair     Mode conversion from geometric asymmetry of a 100-ohm-class microstrip pair:
           current-division (imbalance) factor h = C1g/(C1g+C2g); |V_cm/V_dm| = |h - 1/2| at a
           junction; equivalent skew at 1 GHz. Cases: one-sided pour, third trace, board edge,
           width mismatch, a reference slot under one leg; symmetric controls.
Grid convergence is checked by repeating one case of each section at half the cell size.
"""
import math
import sys
import time

import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as spla

EPS0 = 8.854187e-12
MU0 = 4e-7 * math.pi
ETA0 = math.sqrt(MU0 / EPS0)
MM = 1e-3


# --------------------------------------------------------------------------------------------
# graded tensor grid
def graded_axis(keys, lo, hi, dmin, growth=1.25, dmax=2e-3):
    """Grid points in [lo, hi] that contain every key exactly; spacing dmin at keys, growing
    geometrically (factor `growth`) away from them, capped at dmax."""
    ks = sorted(set([lo, hi] + [k for k in keys if lo < k < hi]))
    pts = [ks[0]]
    for a, b in zip(ks[:-1], ks[1:]):
        seg = [a]
        x = a
        while True:
            d = min(x - a, b - x)
            s = min(dmax, dmin + (growth - 1.0) * d)
            if x + 1.5 * s >= b:
                break
            x += s
            seg.append(x)
        seg = np.array(seg + [b])
        # if the last gap is too big or small relative to the previous, rescale linearly
        seg = a + (seg - a) * (b - a) / (seg[-1] - a)
        pts.extend(seg[1:].tolist())
    return np.array(pts)


def symmetric_axis(keys, half, dmin, growth=1.25, dmax=2e-3):
    """Mirror-symmetric grid about 0 built from folded keys (so symmetric geometries balance)."""
    folded = sorted(set([abs(k) for k in keys] + [0.0]))
    pos = graded_axis(folded, 0.0, half, dmin, growth, dmax)
    return np.concatenate([-pos[::-1], pos[1:]])


class Field2D:
    """Finite-volume Laplace solver div(eps grad phi) = 0 on a tensor grid.

    er_fn(xc, yc) -> relative permittivity of each cell (vectorized).
    Conductors are rectangles (x0, x1, y0, y1) snapped to grid nodes; `ground` rectangles are
    held at 0 V. The outer boundary of the grid is grounded (the far box / the world)."""

    def __init__(self, xs, ys, er_fn):
        self.xs, self.ys = xs, ys
        nx, ny = len(xs), len(ys)
        self.nx, self.ny = nx, ny
        dx, dy = np.diff(xs), np.diff(ys)
        xc = 0.5 * (xs[:-1] + xs[1:])
        yc = 0.5 * (ys[:-1] + ys[1:])
        XC, YC = np.meshgrid(xc, yc, indexing="ij")
        er = er_fn(XC, YC)
        # horizontal edges (i,j)-(i+1,j): conductance = (er below * dy_below/2 + er above * dy_above/2)/dx
        gh = np.zeros((nx - 1, ny))
        gh[:, 1:] += er * dy[None, :] / 2.0
        gh[:, :-1] += er * dy[None, :] / 2.0
        gh /= dx[:, None]
        gv = np.zeros((nx, ny - 1))
        gv[1:, :] += er * dx[:, None] / 2.0
        gv[:-1, :] += er * dx[:, None] / 2.0
        gv /= dy[None, :]
        idx = np.arange(nx * ny).reshape(nx, ny)
        self.e1 = np.concatenate([idx[:-1, :].ravel(), idx[:, :-1].ravel()])
        self.e2 = np.concatenate([idx[1:, :].ravel(), idx[:, 1:].ravel()])
        self.g = np.concatenate([gh.ravel(), gv.ravel()])
        self.X, self.Y = np.meshgrid(xs, ys, indexing="ij")

    def mask(self, rect):
        x0, x1, y0, y1 = rect
        tol = 1e-12
        return ((self.X >= x0 - tol) & (self.X <= x1 + tol) & (self.Y >= y0 - tol) & (self.Y <= y1 + tol)).ravel()

    def caps(self, conductors, grounds=()):
        """Maxwell capacitance matrix (F/m) of `conductors` (list of rect lists)."""
        n = self.nx * self.ny
        fixed = np.zeros(n, bool)
        b = np.zeros((self.nx, self.ny), bool)
        b[0, :] = b[-1, :] = True
        b[:, 0] = b[:, -1] = True
        fixed |= b.ravel()
        for gr in grounds:
            fixed |= self.mask(gr)
        cm = []
        for rects in conductors:
            m = np.zeros(n, bool)
            for r in rects:
                m |= self.mask(r)
            cm.append(m)
            fixed |= m
        free = ~fixed
        fidx = -np.ones(n, int)
        fidx[free] = np.arange(free.sum())
        e1, e2, g = self.e1, self.e2, self.g
        diag = np.bincount(e1, g, n) + np.bincount(e2, g, n)
        both = free[e1] & free[e2]
        rows = np.concatenate([fidx[free], fidx[e1[both]], fidx[e2[both]]])
        cols = np.concatenate([fidx[free], fidx[e2[both]], fidx[e1[both]]])
        vals = np.concatenate([diag[free], -g[both], -g[both]])
        A = sp.csc_matrix((vals, (rows, cols)), shape=(free.sum(), free.sum()))
        lu = spla.splu(A)
        nc = len(conductors)
        C = np.zeros((nc, nc))
        for k in range(nc):
            phi = np.zeros(n)
            phi[cm[k]] = 1.0
            # rhs: sum over edges from free node to fixed node of g*phi_fixed
            rhs = np.zeros(n)
            s1 = free[e1] & ~free[e2]
            s2 = free[e2] & ~free[e1]
            np.add.at(rhs, e1[s1], g[s1] * phi[e2[s1]])
            np.add.at(rhs, e2[s2], g[s2] * phi[e1[s2]])
            phi[free] = lu.solve(rhs[free])
            flux = g * (phi[e1] - phi[e2])  # flux from e1 to e2
            for j in range(nc):
                q = flux[cm[j][e1] & ~cm[j][e2]].sum() - flux[cm[j][e2] & ~cm[j][e1]].sum()
                C[k, j] = EPS0 * q
        return C


def ind_from_air_caps(C0):
    return MU0 * EPS0 * np.linalg.inv(C0)


# --------------------------------------------------------------------------------------------
def sec_duality(fine=1.0):
    print("== duality: two strips over a solid plane (microstrip, er 4.3 below the strips, air above)")
    print("   D = 5 mm centre-to-centre, t = 35 um. C_m' in fF/mm, L_m' in pH/mm. Patch/image predictions:")
    print("   C_m'(wide) = eps0*w_a*w_v/(pi*D^2) [air above]; L_m' = mu0*h_a*h_v/(pi*D^2), h_x = h + t/2")
    t, D, er_sub = 0.035 * MM, 5.0 * MM, 4.3
    half, Y = 60 * MM, 60 * MM
    rows = []
    for (wa, wv, tag) in ((2.0, 2.0, "wide/wide  2.0/2.0 mm"), (2.0, 0.15, "wide/narrow 2.0/0.15"),
                          (0.15, 0.15, "narrow/narrow 0.15/0.15")):
        wa_, wv_ = wa * MM, wv * MM
        res = []
        for h_mm in (0.05, 0.1, 0.2, 0.4, 0.8, 1.6):
            h = h_mm * MM
            ra = (-D / 2 - wa_ / 2, -D / 2 + wa_ / 2, h, h + t)
            rv = (D / 2 - wv_ / 2, D / 2 + wv_ / 2, h, h + t)
            dmin = min(h / 5, t / 2, 0.03 * MM) / fine
            xs = graded_axis([ra[0], ra[1], rv[0], rv[1], 0.0], -half, half, dmin, 1.2, 1.5 * MM)
            ys = graded_axis([0.0, h, h + t], 0.0, Y, dmin, 1.2, 1.5 * MM)
            f = Field2D(xs, ys, lambda xc, yc: np.where(yc < h, er_sub, 1.0))
            fa = Field2D(xs, ys, lambda xc, yc: np.ones_like(xc))
            C = f.caps([[ra], [rv]])
            C0 = fa.caps([[ra], [rv]])
            L = ind_from_air_caps(C0)
            cm = -C[0, 1] * 1e15 * 1e-3      # fF/mm
            lm = L[0, 1] * 1e12 * 1e-3       # pH/mm
            kc = -C[0, 1] / C[1, 1]
            kl = L[0, 1] / L[1, 1]
            he = h + t / 2
            cm_pred = EPS0 * wa_ * wv_ / (math.pi * D ** 2) * 1e15 * 1e-3
            lm_pred = MU0 * he * he / (math.pi * D ** 2) * 1e12 * 1e-3
            res.append((h_mm, cm, cm_pred, lm, lm_pred, kc, kl, len(xs) * len(ys)))
        rows.append((tag, res))
        print(f"  {tag}")
        print("     h(mm)  C_m'(fF/mm) patch-pred  L_m'(pH/mm) image-pred   K_C(victim)  K_L(victim)  nodes")
        for (h_mm, cm, cmp_, lm, lmp, kc, kl, nn) in res:
            print(f"     {h_mm:5.2f}  {cm:10.4f}  {cmp_:9.4f}   {lm:10.5f}  {lmp:9.5f}    {kc:9.2e}   {kl:9.2e}  {nn}")
        hs = np.array([r[0] for r in res])
        cms = np.array([r[1] for r in res])
        lms = np.array([r[3] for r in res])
        sel = hs <= 0.4
        pc = np.polyfit(np.log(hs[sel]), np.log(cms[sel]), 1)[0]
        pl = np.polyfit(np.log(hs[sel]), np.log(lms[sel]), 1)[0]
        print(f"     log-log slope over h = 0.05-0.4 mm:  C_m' ~ h^{pc:+.2f}   L_m' ~ h^{pl:+.2f}")
    # guard between wide strips
    print("  Grounded coplanar guard (0.5 mm wide, centred between the strips, stitched to the plane):")
    for h_mm in (0.1, 1.6):
        h = h_mm * MM
        wa_ = wv_ = 2.0 * MM
        ra = (-D / 2 - wa_ / 2, -D / 2 + wa_ / 2, h, h + t)
        rv = (D / 2 - wv_ / 2, D / 2 + wv_ / 2, h, h + t)
        rg = (-0.25 * MM, 0.25 * MM, h, h + t)
        dmin = min(h / 5, t / 2, 0.03 * MM) / fine
        xs = graded_axis([ra[0], ra[1], rv[0], rv[1], rg[0], rg[1]], -half, half, dmin, 1.2, 1.5 * MM)
        ys = graded_axis([0.0, h, h + t], 0.0, Y, dmin, 1.2, 1.5 * MM)
        f = Field2D(xs, ys, lambda xc, yc: np.where(yc < h, er_sub, 1.0))
        fa = Field2D(xs, ys, lambda xc, yc: np.ones_like(xc))
        c_no = -f.caps([[ra], [rv]])[0, 1]
        c_g = -f.caps([[ra], [rv]], grounds=[rg])[0, 1]
        l_no = ind_from_air_caps(fa.caps([[ra], [rv]]))[0, 1]
        l_g = ind_from_air_caps(fa.caps([[ra], [rv]], grounds=[rg]))[0, 1]
        print(f"     h = {h_mm:4.2f} mm: C_m' x{c_g/c_no:.3f} with guard; L_m' x{l_g/l_no:.3f} with guard")
    return rows


# --------------------------------------------------------------------------------------------
def sec_antenna(fine=1.0):
    print("== antenna: trace over a finite plane (W = 40 mm) in a far grounded box (the 'world', 400 mm)")
    print("   L_ret = L22 - L21 (plane voltage per unit DM current, pH/mm); prediction mu0*h_e/(2*pi*sqrt((W/2)^2-x^2))")
    print("   h_C = C10/(C10+C20) (trace's share of the board's external charge); shape w_e/(2*pi*sqrt((W/2)^2-x^2))")
    t, W, box = 0.035 * MM, 40.0 * MM, 400.0 * MM
    out = []
    for (w_mm, h_mm) in ((0.2, 0.1), (0.2, 0.4), (1.0, 0.1)):
        w, h = w_mm * MM, h_mm * MM
        print(f"  trace w = {w_mm} mm at h = {h_mm} mm above the plane (air; homogeneous so L = mu0 eps0 C0^-1)")
        print("     x(mm)  x/(W/2)  L_ret(pH/mm)  pred     ratio   h_C        w_e = h_C*2pi*sqrt(..)(mm)")
        for xr in (0.0, 0.5, 0.8, 0.9, 0.95, 0.975):
            x0 = xr * W / 2
            if W / 2 - x0 < w / 2 + 2 * h:
                continue
            rt = (x0 - w / 2, x0 + w / 2, h, h + t)
            rp = (-W / 2, W / 2, -t, 0.0)
            dmin = min(h / 5, w / 6, t / 2) / fine
            xs = graded_axis([rp[0], rp[1], rt[0], rt[1]], -box, box, dmin, 1.2, 20 * MM)
            ys = graded_axis([-t, 0.0, h, h + t], -box, box, dmin, 1.2, 20 * MM)
            fa = Field2D(xs, ys, lambda xc, yc: np.ones_like(xc))
            C0 = fa.caps([[rt], [rp]])
            L = ind_from_air_caps(C0)
            lret = (L[1, 1] - L[1, 0]) * 1e12 * 1e-3
            he = h + t / 2
            pred = MU0 * he / (2 * math.pi * math.sqrt((W / 2) ** 2 - x0 ** 2)) * 1e12 * 1e-3
            c10 = C0[0, 0] + C0[0, 1]
            c20 = C0[1, 1] + C0[1, 0]
            hc = c10 / (c10 + c20)
            we = hc * 2 * math.pi * math.sqrt((W / 2) ** 2 - x0 ** 2) / MM
            out.append((w_mm, h_mm, xr, lret, pred, hc, we))
            print(f"     {x0/MM:5.2f}  {xr:5.3f}   {lret:9.4f}   {pred:8.4f}  {lret/pred:5.3f}   {hc:.3e}   {we:.3f}")
    return out


# --------------------------------------------------------------------------------------------
def sec_pair(fine=1.0):
    print("== pair: microstrip pair w = 0.15 mm, gap 0.20 mm, h = 0.10 mm, er 4.3, t = 35 um")
    print("   h_C = C1g/(C1g+C2g) (row sums, plane = ground); |V_cm/V_dm| at a junction = |h_C - 1/2|.")
    print("   dt_eq = skew giving the same conversion at 1 GHz: 2|dh|/(pi f). h_L from the air L matrix.")
    w, s, h, t, er_sub = 0.15 * MM, 0.20 * MM, 0.10 * MM, 0.035 * MM, 4.3
    half, Y = 15 * MM, 15 * MM
    l1 = (-s / 2 - w, -s / 2, h, h + t)
    l2 = (s / 2, s / 2 + w, h, h + t)
    dmin = min(h / 6, t / 2) / fine
    cases = [("symmetric (control)", {}),
             ("pour both sides, g = 0.2 mm (control)", {"pour": [(+1, 0.2), (-1, 0.2)]})]
    for g in (0.1, 0.2, 0.3, 0.5, 1.0, 2.0):
        cases.append((f"pour one side, g = {g:.1f} mm", {"pour": [(+1, g)]}))
    for g in (0.2, 0.5, 1.0):
        cases.append((f"grounded 3rd trace, g = {g:.1f} mm", {"trace3": g}))
    for d in (0.2, 0.5, 1.0, 2.0):
        cases.append((f"board/plane edge {d:.1f} mm from leg 2", {"edge": d}))
    cases.append(("leg 2 wider by 10 um (etch)", {"dw": 0.010}))
    cases.append(("leg 2 wider by 25 um", {"dw": 0.025}))
    cases.append(("slot 0.3 mm in plane under leg 2 (next plane 0.3 mm down)", {"slot": 0.3}))
    results = []
    print("     case                                                h_C - 1/2    dB      h_L - 1/2    dt_eq@1GHz(ps)")
    for name, spec in cases:
        keys = [l1[0], l1[1], l2[0], l2[1]]
        grounds = []
        cond2 = l2
        ylo = 0.0
        plane_edge = None
        if "pour" in spec:
            for side, g in spec["pour"]:
                x0 = s / 2 + w + g * MM
                r = (x0, half, h, h + t) if side > 0 else (-half, -x0, h, h + t)
                grounds.append(r)
                keys += [x0, -x0]
        if "trace3" in spec:
            x0 = s / 2 + w + spec["trace3"] * MM
            grounds.append((x0, x0 + w, h, h + t))
            keys += [x0, x0 + w]
        if "dw" in spec:
            cond2 = (s / 2, s / 2 + w + spec["dw"] * MM, h, h + t)
            keys += [cond2[1]]
        slot = None
        if "edge" in spec:
            plane_edge = s / 2 + w + spec["edge"] * MM
            keys += [plane_edge]
            ylo = -1.0 * MM  # room below the plane level
        if "slot" in spec:
            sw = spec["slot"] * MM
            slot = (s / 2 + w / 2 - sw / 2, s / 2 + w / 2 + sw / 2)
            keys += list(slot)
            ylo = -0.3 * MM
        xs = symmetric_axis(keys, half, dmin, 1.2, 1.0 * MM)
        ykeys = [0.0, h, h + t]
        if ylo < 0:
            ykeys += [ylo, -t]
        ys = graded_axis(ykeys, ylo, Y, dmin, 1.2, 1.0 * MM)
        if plane_edge is not None:
            pe = plane_edge
            erf = lambda xc, yc: np.where((yc < h) & (yc > 0) & (xc < pe), er_sub, 1.0)
            grounds.append((-half, pe, -t, 0.0))
        elif slot is not None:
            sl = slot
            erf = lambda xc, yc: np.where(yc < h, er_sub, 1.0)
            grounds += [(-half, sl[0], -t, 0.0), (sl[1], half, -t, 0.0)]
        else:
            erf = lambda xc, yc: np.where(yc < h, er_sub, 1.0)
        f = Field2D(xs, ys, erf)
        fa = Field2D(xs, ys, lambda xc, yc: np.ones_like(xc))
        C = f.caps([[l1], [cond2]], grounds=grounds)
        C0 = fa.caps([[l1], [cond2]], grounds=grounds)
        c1g, c2g = C[0].sum(), C[1].sum()
        hc = c1g / (c1g + c2g) - 0.5
        L = ind_from_air_caps(C0)
        hl = (L[1, 1] - L[0, 1]) / (L[0, 0] + L[1, 1] - 2 * L[0, 1]) - 0.5
        db = 20 * math.log10(abs(hc)) if abs(hc) > 1e-12 else -999
        dteq = 2 * abs(hc) / (math.pi * 1e9) * 1e12
        results.append((name, hc, hl, db, dteq))
        print(f"     {name:52s} {hc:+.2e}  {db:6.1f}   {hl:+.2e}    {dteq:7.2f}")
    # differential impedance of the symmetric pair, for reference
    xs = symmetric_axis([l1[0], l1[1], l2[0], l2[1]], half, dmin, 1.2, 1.0 * MM)
    ys = graded_axis([0.0, h, h + t], 0.0, Y, dmin, 1.2, 1.0 * MM)
    f = Field2D(xs, ys, lambda xc, yc: np.where(yc < h, er_sub, 1.0))
    fa = Field2D(xs, ys, lambda xc, yc: np.ones_like(xc))
    C = f.caps([[l1], [l2]])
    L = ind_from_air_caps(fa.caps([[l1], [l2]]))
    zd = 2 * math.sqrt((L[0, 0] - L[0, 1]) / (C[0, 0] - C[0, 1]))
    print(f"   (symmetric pair: Zdiff = {zd:.1f} ohm)")
    return results


SECTIONS = {"duality": sec_duality, "antenna": sec_antenna, "pair": sec_pair}


def main(argv):
    names = [a for a in argv if a in SECTIONS] or list(SECTIONS)
    conv = "--converge" in argv
    for n in names:
        t0 = time.time()
        SECTIONS[n]()
        print(f"   [{n}: {time.time()-t0:.1f} s]\n")
    if conv:
        print("== convergence: repeat at half the minimum cell size")
        for n in names:
            t0 = time.time()
            SECTIONS[n](fine=2.0)
            print(f"   [{n} fine: {time.time()-t0:.1f} s]\n")


if __name__ == "__main__":
    main(sys.argv[1:])
