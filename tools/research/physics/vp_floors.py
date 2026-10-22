# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Variational floors and bounds for PCB copper (round-2 lens VP: variational principles).

Thomson's principle (current distributes to minimise dissipation for given terminal
currents) and Dirichlet's principle (potential minimises energy for given terminal
voltages) bracket every resistance, sheet inductance and capacitance. This script
turns that into numbers for four round-1 results.

Sections (python vp_floors.py [floor|slot|cluster|lattice|all] [--h 0.2]):

  floor    Floors for the op_topopt_pour.py test pour (24 x 14 mm, 1 oz, 6 A into
           three loads, equal copper area):
           (a) Beckmann/Kantorovich floor R >= R_s * W1^2 / (A * I^2), where
               W1 = sum_k I_k * dist(source, load_k) is the earth-mover distance of
               the currents (Cauchy-Schwarz on Thomson's functional; microseconds);
           (b) the convex "variable-thickness" relaxation (SIMP with p = 1, no filter):
               compliance is convex in the density, so its optimum is a global floor
               for every binary layout of the same area on the grid. The floor is
               certified by the Lagrangian dual: for any trial potential v,
               R >= (f.v)^2 / (I^2 * max_rho v'K(rho)v)  (a fractional knapsack);
           (c) the human trunk-and-branch layout and SIMP (p = 3) designs of round 1,
               re-run on the same grid, placed inside the certified interval.
           Plus an area sweep of the floor.
  slot     The round-1 "slot" variant: the L2 reference has a slot, and the inductive
           sheet coefficient is 1/(mu0*h_eff). Round 1 found the L-only optimum worse
           than the 50/50 DC+L optimum (a local minimum). The inductive objective is a
           compliance too, so (a) its convex floor is computed and (b) SIMP is started
           from the convex optimum (p = 1 -> 3 continuation) instead of a uniform field.
  cluster  Plane-pair spreading inductance of via clusters (pw_sheet.py `cluster`,
           d = 0.1 mm, ring at R = 10 mm) from the logarithmic capacity of the cluster
           (the minimum-energy charge distribution; charge simulation, closed form for
           vias on a circle) and the convex-hull floor L >= (mu0 d/2pi) ln(R/cap(hull)).
  lattice  Sheet-resistance multiplier of a plane perforated by a via-antipad lattice:
           the 2-D Hashin-Shtrikman bound (1+f)/(1-f) (identical to Rayleigh's formula)
           is a rigorous lower bound; square vs hexagonal (staggered) lattices at equal
           via density and antipad size (unit-cell Laplace solves via pw_sheet.squares).

Deterministic. 'all' takes about 2-4 minutes of CPU at --h 0.2 (default); --h 0.1
reproduces round 1's grid (about 4x longer). Needs numpy, scipy, shapely, contourpy.
Imports op_topopt_pour.py and pw_sheet.py from this directory.
"""
import argparse
import math
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import op_topopt_pour as tp  # noqa: E402
import pw_sheet  # noqa: E402

MU0 = 4e-7 * math.pi
EPS = 1e-9          # void conductivity ratio, as in op_topopt_pour.evaluate()


# ----------------------------------------------------------------------------- floors
def beckmann_floor(g, area_mm2, coef_per_sq=None):
    """Kantorovich/Beckmann floor of P/I^2 for any copper of total area <= area_mm2.

    Cauchy-Schwarz on Thomson's functional: P = R_s * int |J|^2 / rho
    >= R_s * (int |J|)^2 / int rho, and int |J| >= W1 (earth-mover distance between
    the current sources and sinks). Euclidean distance <= geodesic distance, so using
    it keeps the bound valid. The source pad is an equipotential (current-free inside),
    so its area is excluded from A.
    """
    rs = tp.RS_1OZ if coef_per_sq is None else 1.0 / coef_per_sq
    sx0, sy0, sx1, sy1 = tp.SRC
    w1 = 0.0
    for (_, _, cur), nodes in zip(tp.LOADS, g.load_nodes):
        x, y = g.xn[nodes], g.yn[nodes]
        dx = np.maximum(np.maximum(sx0 - x, 0.0), x - sx1)
        dy = np.maximum(np.maximum(sy0 - y, 0.0), y - sy1)
        w1 += cur * np.hypot(dx, dy).mean()          # A*mm
    a_eff = area_mm2 - (sx1 - sx0) * (sy1 - sy0)       # mm^2
    return rs * (w1 * 1e-3) ** 2 / (a_eff * 1e-6) / g.itot ** 2, w1


def knapsack_q(g, coef0, e, budget_cells):
    """max over feasible rho of v'K(rho)v = sum_e coef_e(rho_e) * e_e (fractional knapsack)."""
    des = np.flatnonzero(g.des)
    q = np.sum(coef0[g.solid] * e[g.solid]) + EPS * np.sum(coef0[~g.solid] * e[~g.solid])
    ed = (1 - EPS) * coef0[des] * e[des]
    order = np.argsort(-ed)
    k = int(np.floor(budget_cells))
    q += ed[order[:k]].sum()
    if k < len(des):
        q += (budget_cells - k) * ed[order[k]]
    return q


def vts(g, area_mm2, coefs, weights=None, iters=400, eta=0.5, move=0.2, tol=2e-4, x0=None, log=False):
    """Convex variable-thickness relaxation: min sum_i w_i C_i(rho)/C_i(full) over 0<=rho<=1,
    area <= area_mm2, conductance linear in rho (SIMP with p = 1, no filter, OC update).

    Returns (rho, upper, lower): 'upper' is the relaxed objective at the final iterate
    and 'lower' the best Lagrangian-dual bound seen (valid for every rho in the set,
    in particular for every binary layout of that area on this grid).
    """
    weights = [1.0] * len(coefs) if weights is None else weights
    a = g.h ** 2
    budget = area_mm2 - g.solid.sum() * a
    nb = budget / a
    des = np.flatnonzero(g.des)
    full = ~g.void
    cref = [g.f @ g.solve(np.where(full, c0, EPS * c0.max()))[0] for c0 in coefs]
    x = np.zeros(g.nel)
    x[g.solid] = 1.0
    x[des] = np.clip(nb / len(des), 0.0, 1.0) if x0 is None else x0[des]
    best_lb, hist = 0.0, []
    for it in range(iters):
        obj, grad, us, cs = 0.0, np.zeros(len(des)), [], []
        for c0, w, cr in zip(coefs, weights, cref):
            (u,) = g.solve(c0 * (EPS + (1 - EPS) * x))
            c = g.f @ u
            e = g.elem_energy(u)
            obj += w * c / cr
            grad += -w * (1 - EPS) * c0[des] * e[des] / cr
            us.append((u, e, c))
        # dual bound: for each objective use v_i = s_i u_i; with one objective the optimal
        # scaling gives C^2/Q; with several, the unscaled Lagrangian bound is used.
        if len(coefs) == 1:
            c0 = coefs[0]
            u, e, c = us[0]
            lb = c * c / knapsack_q(g, c0, e, nb) / cref[0] * weights[0]
        else:
            lin = sum(w * 2 * c / cr for (u, e, c), w, cr in zip(us, weights, cref))
            fixed = sum(w * (np.sum(c0[g.solid] * e[g.solid]) + EPS * np.sum(c0[~g.solid] * e[~g.solid])) / cr
                        for (u, e, c), c0, w, cr in zip(us, coefs, weights, cref))
            ed = sum(w * (1 - EPS) * c0[des] * e[des] / cr for (u, e, c), c0, w, cr in zip(us, coefs, weights, cref))
            order = np.argsort(-ed)
            k = int(np.floor(nb))
            q = fixed + ed[order[:k]].sum() + ((nb - k) * ed[order[k]] if k < len(des) else 0.0)
            lb = lin - q
        best_lb = max(best_lb, lb)
        gap = (obj - best_lb) / obj
        hist.append((it, obj, best_lb, gap))
        if log and it % 50 == 0:
            print(f"      it {it:3d}  relaxed {obj:.5f}  dual {best_lb:.5f}  gap {gap:.2e}")
        if gap < tol:
            break
        xd = x[des]
        b = np.maximum(-grad, 1e-300)
        lo, hi = 1e-40, 1e40
        while hi / lo > 1 + 1e-10:
            lm = math.sqrt(lo * hi)
            xn = np.clip(np.maximum(xd, 1e-4) * (b / (lm * a)) ** eta,
                         np.maximum(0.0, xd - move), np.minimum(1.0, xd + move))
            if xn.sum() * a > budget:
                lo = lm
            else:
                hi = lm
        x[des] = xn
    return x, obj, best_lb, cref, hist


def simp_warm(g, area_mm2, coefs, weights, x0, p_sched=(1.0, 1.5, 2.0, 3.0), it_per_p=40,
              beta_iters=80, rmin_mm=0.5):
    """SIMP (filter + Heaviside, OC) started from x0, with a p continuation 1 -> 3 and then
    beta doubling to 32 at p = 3. Same machinery as op_topopt_pour.topopt()."""
    hm, hs = tp.build_filter(g, rmin_mm)
    a2 = np.full(g.nel, g.h ** 2)
    budget = area_mm2 - a2[g.solid].sum()
    full = ~g.void
    cref = [g.f @ g.solve(np.where(full, c0, 1e-9 * c0.max()))[0] for c0 in coefs]
    x = x0.copy()
    x[g.solid], x[g.void] = 1.0, 0.0
    sched = [(p, 1.0) for p in p_sched for _ in range(it_per_p)]
    beta = 1.0
    for k in range(beta_iters):
        if k and k % 16 == 0 and beta < 32:
            beta *= 2
        sched.append((p_sched[-1], beta))
    for p, beta in sched:
        xt = (hm @ x) / hs
        rho, drho = tp.project(xt, beta)
        rho[g.solid], rho[g.void] = 1.0, 0.0
        drho[~g.des] = 0.0
        dobj = np.zeros(g.nel)
        for c0, w, cr in zip(coefs, weights, cref):
            cmin = 1e-6 * c0.max()
            (u,) = g.solve(cmin + rho ** p * (c0 - cmin))
            dobj += w * (-p * rho ** (p - 1) * (c0 - cmin) * g.elem_energy(u)) / cr
        dc = np.minimum(hm.T @ (dobj * drho / hs), -1e-30)
        dv = np.maximum(hm.T @ (a2 * drho / hs), 1e-30)
        move = 0.2 if beta < 8 else 0.1
        lo, hi = 1e-20, 1e20
        while hi / lo > 1 + 1e-6:
            lm = math.sqrt(lo * hi)
            xn = x.copy()
            xn[g.des] = np.clip(x[g.des] * np.sqrt(-dc[g.des] / (lm * dv[g.des])),
                                np.maximum(0, x[g.des] - move), np.minimum(1, x[g.des] + move))
            rn, _ = tp.project((hm @ xn) / hs, beta)
            if (a2 * rn)[g.des].sum() > budget:
                lo = lm
            else:
                hi = lm
        x = xn
    rho, _ = tp.project((hm @ x) / hs, beta)
    rho[g.solid], rho[g.void] = 1.0, 0.0
    return rho


def binarize(g, rho):
    return tp.connected_to_pads(g, (rho > 0.5) | g.solid)


def sec_floor(h):
    print(f"== floor: copper-loss floors for the op_topopt_pour.py test pour (grid {h} mm)")
    g = tp.Grid(h)
    g0 = np.full(g.nel, 1.0 / tp.RS_1OZ)
    hum = tp.human_layout(g)
    area = hum.sum() * h ** 2
    r_h = tp.evaluate(g, hum)[0]
    r_full = tp.evaluate(g, ~g.void)[0]
    t0 = time.perf_counter()
    r_b, w1 = beckmann_floor(g, area)
    t_b = time.perf_counter() - t0
    t0 = time.process_time()
    x, up, lb, cref, hist = vts(g, area, [g0], log=True)
    t_v = time.process_time() - t0
    r_up, r_lb = up * cref[0] / g.itot ** 2, lb * cref[0] / g.itot ** 2
    rho = tp.topopt(g, area, [g0], [1.0], rmin_mm=0.5, iters=200)[0]
    cu = binarize(g, rho)
    r_s = tp.evaluate(g, cu)[0]
    xd = x[g.des]
    print(f"  area {area:.1f} mm2 (incl. 34.5 mm2 pads); W1 = sum I*d = {w1:.1f} A*mm")
    print(f"  (a) Beckmann/Kantorovich floor      R >= {r_b * 1e3:.3f} mOhm   ({t_b * 1e6:.0f} us)")
    print(f"  (b) convex relaxation (p=1) floor   R >= {r_lb * 1e3:.3f} mOhm   (relaxed design "
          f"{r_up * 1e3:.3f}; gap {(r_up - r_lb) / r_up:.1e}; {len(hist)} solves, {t_v:.1f} s)")
    print(f"      relaxed design: {np.mean(xd > 0.99):.1%} of design cells full, {np.mean(xd < 0.01):.1%} empty, "
          f"{np.mean((xd >= 0.01) & (xd <= 0.99)):.1%} grey")
    print(f"  (c) SIMP p=3 binary (round 1)       R  = {r_s * 1e3:.3f} mOhm   "
          f"= floor x {r_s / r_lb:.3f}  (area {cu.sum() * h ** 2:.1f} mm2)")
    print(f"      human trunk-and-branch          R  = {r_h * 1e3:.3f} mOhm   = floor x {r_h / r_lb:.3f}")
    print(f"      full pour (323 mm2)             R  = {r_full * 1e3:.3f} mOhm")
    print(f"  => any {area:.0f} mm2 layout lies in [{r_lb * 1e3:.3f}, ...]; SIMP is certified within "
          f"{(r_s / r_lb - 1) * 100:.1f}% of the best possible; the human tree has "
          f"{(1 - r_lb / r_h) * 100:.1f}% of its loss above the floor")
    print("  area sweep (fraction of the 323 mm2 free region):  Beckmann | convex floor | SIMP binary  (x full pour)")
    full_area = (~g.void).sum() * h ** 2
    for frac in (0.2, 0.3, 0.5, 0.7):
        ar = frac * full_area
        rb, _ = beckmann_floor(g, ar)
        _, up2, lb2, cr2, _ = vts(g, ar, [g0], iters=300)
        rl = lb2 * cr2[0] / g.itot ** 2
        rho2 = tp.topopt(g, ar, [g0], [1.0], iters=100)[0]
        rs2 = tp.evaluate(g, binarize(g, rho2))[0]
        tag = "DISCONNECTED" if rs2 > 1 else f"{rs2 / r_full:5.2f}"
        print(f"    {frac:4.0%} ({ar:5.1f} mm2):  {rb / r_full:5.2f} | {rl / r_full:5.2f} | {tag}"
              f"   (SIMP/floor {rs2 / rl:.3f})")
    return dict(r_b=r_b, r_lb=r_lb, r_s=r_s, r_h=r_h)


def sec_slot(h):
    print(f"== slot: inductive objective over a slotted reference (grid {h} mm)")
    g = tp.Grid(h)
    g0 = np.full(g.nel, 1.0 / tp.RS_1OZ)
    hmap = np.where(g.in_rect(g.xc, g.yc, tp.SLOT), tp.H_SLOT, tp.H_REF)
    gl = 1.0 / (MU0 * hmap)
    hum = tp.human_layout(g)
    area = hum.sum() * h ** 2
    full_l = tp.evaluate(g, ~g.void, coef0=gl)[0]
    print(f"  human layout: R {tp.evaluate(g, hum)[0] * 1e3:.3f} mOhm, L_eff {tp.evaluate(g, hum, coef0=gl)[0] * 1e9:.3f} nH;"
          f" full pour L_eff {full_l * 1e9:.3f} nH")
    xl, upl, lbl, crl, hl = vts(g, area, [gl], iters=400)
    l_floor = lbl * crl[0] / g.itot ** 2
    print(f"  convex floor, L only: L_eff >= {l_floor * 1e9:.3f} nH (relaxed {upl * crl[0] / g.itot ** 2 * 1e9:.3f},"
          f" {len(hl)} solves)")
    xm, upm, lbm, crm, hm_ = vts(g, area, [g0, gl], [0.5, 0.5], iters=400)
    print(f"  convex floor, 50/50 normalised objective: >= {lbm:.4f} (relaxed {upm:.4f})")
    rows = []
    for name, w in [("DC only", (1.0, 0.0)), ("50/50", (0.5, 0.5)), ("L only", (0.0, 1.0))]:
        cold = binarize(g, tp.topopt(g, area, [g0, gl], list(w), iters=100)[0])
        if w == (0.0, 1.0):
            x0 = xl
        elif w == (1.0, 0.0):
            x0 = vts(g, area, [g0], iters=300)[0]
        else:
            x0 = xm
        warm = binarize(g, simp_warm(g, area, [g0, gl], list(w), x0))
        for tag, cu in (("cold (uniform start, p=3)", cold), ("warm (convex start, p 1->3)", warm)):
            r, l = tp.evaluate(g, cu)[0], tp.evaluate(g, cu, coef0=gl)[0]
            rows.append((name, tag, r, l))
            print(f"  {name:8s} {tag:28s}: R {r * 1e3:.3f} mOhm  L_eff {l * 1e9:.3f} nH  "
                  f"(L / L-floor {l / l_floor:.3f})  area {cu.sum() * h ** 2:.1f} mm2")
    return rows


# ----------------------------------------------------------------------------- vias
def log_capacity(centers, a, m=64):
    """Logarithmic capacity (transfinite diameter) of a union of discs of radius a.

    The equilibrium (minimum logarithmic energy) charge distribution with unit total
    charge makes every disc an equipotential V0 = -ln(cap). Charge simulation with m
    points per disc; self term = mean of -ln|x| over the point's own arc (1 - ln(s/2)).
    """
    th = (np.arange(m) + 0.5) * 2 * math.pi / m
    pts = np.concatenate([np.stack([cx + a * np.cos(th), cy + a * np.sin(th)], 1) for cx, cy in centers])
    n = len(pts)
    d = np.hypot(pts[:, None, 0] - pts[None, :, 0], pts[:, None, 1] - pts[None, :, 1])
    s = 2 * math.pi * a / m
    gmat = -np.log(np.where(d > 0, d, 1.0))
    np.fill_diagonal(gmat, 1.0 - math.log(s / 2))
    sysm = np.zeros((n + 1, n + 1))
    sysm[:n, :n] = gmat
    sysm[:n, n] = -1.0
    sysm[n, :n] = 1.0
    rhs = np.zeros(n + 1)
    rhs[n] = 1.0
    sol = np.linalg.solve(sysm, rhs)
    return math.exp(-sol[n])


def log_capacity_curve(poly, m=600):
    """Logarithmic capacity of a filled convex polygon (charge simulation on its boundary)."""
    ring = poly.exterior
    s = ring.length / m
    pts = np.array([ring.interpolate((i + 0.5) * s).coords[0] for i in range(m)])
    d = np.hypot(pts[:, None, 0] - pts[None, :, 0], pts[:, None, 1] - pts[None, :, 1])
    gmat = -np.log(np.where(d > 0, d, 1.0))
    np.fill_diagonal(gmat, 1.0 - math.log(s / 2))
    sysm = np.zeros((m + 1, m + 1))
    sysm[:m, :m] = gmat
    sysm[:m, m] = -1.0
    sysm[m, :m] = 1.0
    rhs = np.zeros(m + 1)
    rhs[m] = 1.0
    return math.exp(-np.linalg.solve(sysm, rhs)[m])


def sec_cluster():
    import shapely
    from shapely.geometry import Point
    print("== cluster: plane-pair spreading inductance of via clusters from logarithmic capacity")
    print("   (d = 0.1 mm, via r = 0.15 mm, outer ring R = 10 mm; L = (mu0 d / 2 pi) ln(R / cap))")
    d, a, big_r = 0.1e-3, 0.15, 10.0
    pref = MU0 * d / (2 * math.pi) * 1e12   # pH per neper
    r1 = {(1, 0): 85, (2, 0.6): 70, (2, 2.0): 59, (4, 0.6): 61, (4, 2.0): 44, (9, 1.0): 41,
          (9, 2.0): 30, (16, 0.6): 43, (16, 1.0): 34}   # pw_sheet.py `cluster` (pdn-and-commutation.md)
    print("   N x pitch | round-1 grid solve | log-capacity | closed form | convex-hull floor (L >=)")
    sq = log_capacity_curve(shapely.box(-0.5, -0.5, 0.5, 0.5))
    for (n, p), lr1 in r1.items():
        if n == 1:
            cs = [(0.0, 0.0)]
        elif n == 2:
            cs = [(-p / 2, 0.0), (p / 2, 0.0)]
        else:
            k = int(round(math.sqrt(n)))
            cs = [((i - (k - 1) / 2) * p, (j - (k - 1) / 2) * p) for i in range(k) for j in range(k)]
        cap = log_capacity(cs, a)
        if n == 1:
            cf = a
        elif n == 2:
            cf = math.sqrt(a * p)                                   # two discs, a << p
        elif n == 4:
            rho = p / math.sqrt(2)
            cf = (n * a * rho ** (n - 1)) ** (1.0 / n)              # N discs on a circle
        else:
            cf = float("nan")
        hull = shapely.union_all([Point(c).buffer(a, quad_segs=32) for c in cs]).convex_hull
        hcap = log_capacity_curve(hull)                             # cap(cluster) <= cap(hull)
        cf_txt = f"{pref * math.log(big_r / cf):6.1f}" if cf == cf else "   -  "
        print(f"   {n:2d} x {p:3.1f}   |      {lr1:4d} pH       |   {pref * math.log(big_r / cap):6.1f} pH  |"
              f"  {cf_txt} pH  |  {pref * math.log(big_r / hcap):6.1f} pH")
    print(f"   check: unit square capacity {sq:.4f} (exact Gamma(1/4)^2/(4 pi^1.5) = 0.5902); segment of length l: l/4")


# ----------------------------------------------------------------------------- lattices
def lattice_multiplier(kind, dp, n=200):
    """Sheet-resistance multiplier of a plane perforated by circular holes of diameter D
    on a square or hexagonal lattice of pitch p (current along a lattice row).
    Unit cell bounded by mirror lines: equipotentials across the flow, insulators along it."""
    if kind == "square":
        yy, xx = np.mgrid[0:n, 0:n]
        x, y = (xx + 0.5) / n - 0.5, (yy + 0.5) / n - 0.5
        m = np.hypot(x, y) >= dp / 2
        aspect = 1.0                                   # height / width of the cell
    else:
        ny = int(round(n * math.sqrt(3) / 2))
        yy, xx = np.mgrid[0:ny, 0:n]
        x, y = (xx + 0.5) / n, (yy + 0.5) / n          # cell [0,1] x [0, sqrt(3)/2], pitch 1
        hy = math.sqrt(3) / 2
        m = np.ones_like(x, bool)
        for cx, cy in ((0, 0), (1, 0), (0.5, hy)):
            m &= np.hypot(x - cx, y - cy) >= dp / 2
        aspect = ny / n
    ea = np.zeros_like(m)
    ea[:, 0] = True
    eb = np.zeros_like(m)
    eb[:, -1] = True
    ea &= m
    eb &= m
    nx = m.shape[1]
    nsq = pw_sheet.squares(m, ea, eb) * nx / (nx - 1)
    return nsq * aspect


def sec_lattice():
    print("== lattice: perforated-plane sheet-R multiplier; Hashin-Shtrikman bound (1+f)/(1-f) is a floor")
    print("   square D/p_s | f     | HS floor | square lattice | hex lattice, same via density and D (D/p_h)")
    k = math.sqrt(2 / math.sqrt(3))                    # p_h / p_s at equal density
    for dp in (0.3, 0.5, 0.6, 0.7, 0.8, 0.85, 0.9, 0.95):
        f = math.pi * dp * dp / 4
        hs = (1 + f) / (1 - f)
        sq = lattice_multiplier("square", dp)
        hx = lattice_multiplier("hex", dp / k)
        print(f"   {dp:4.2f}         | {f:5.3f} | {hs:7.3f}  | {sq:8.3f}       | {hx:8.3f}  ({dp / k:4.2f})"
              f"   hex/square {hx / sq:5.3f}")


def _q4_energy_solve(mask, dir_nodes, dir_vals):
    """Q4 FEM Laplace on a pixel mask (unit sheet coefficient): returns u'Ku for the solution."""
    import scipy.sparse as sp
    import scipy.sparse.linalg as spla
    ny, nx = mask.shape
    jj, ii = np.nonzero(mask)
    n1 = jj * (nx + 1) + ii                                   # node (j, i) -> j*(nx+1)+i
    edof = np.stack([n1, n1 + 1, n1 + nx + 2, n1 + nx + 1], 1)  # counter-clockwise
    nn = (ny + 1) * (nx + 1)
    k = sp.csr_matrix((np.tile(tp.KE.ravel(), len(edof)),
                       (np.repeat(edof, 4, 1).ravel(), np.tile(edof, (1, 4)).ravel())), shape=(nn, nn))
    used = np.unique(edof)
    u = np.zeros(nn)
    u[dir_nodes] = dir_vals
    free = np.setdiff1d(used, dir_nodes)
    kff = k[free][:, free].tocsc()
    u[free] = spla.spsolve(kff, -(k[free][:, dir_nodes] @ u[dir_nodes]))
    return u @ (k @ u)


def sec_bracket():
    print("== bracket: certified two-sided bounds for a fixed geometry (Dirichlet vs Thomson)")
    print("   sharp 90-degree L-bend of unit width, arms of A = 4 widths; corner excess squares d = N_sq - 2A")
    print("   potential FEM (Dirichlet): N_sq <= true; stream-function FEM (Thomson): N_sq >= true")
    a_len = 4
    for n in (2, 4, 8, 16, 32):
        s = a_len + 1
        ny = nx = s * n
        jj, ii = np.mgrid[0:ny, 0:nx]
        xc, yc = (ii + 0.5) / n, (jj + 0.5) / n
        mask = ((yc < 1) | (xc > a_len)) & (xc < s) & (yc < s)
        nj, ni = np.mgrid[0:ny + 1, 0:nx + 1]
        xn, yn = (ni / n).ravel(), (nj / n).ravel()
        idx = np.arange(len(xn))
        eps = 1e-9
        # potential: phi = 0 on x = 0 (0<=y<=1), phi = 1 on y = s (a_len<=x<=s)
        t1 = idx[(np.abs(xn) < eps) & (yn <= 1 + eps)]
        t2 = idx[(np.abs(yn - s) < eps) & (xn >= a_len - eps)]
        g = _q4_energy_solve(mask, np.concatenate([t1, t2]), np.concatenate([np.zeros(len(t1)), np.ones(len(t2))]))
        r_lo = 1.0 / g
        # stream function: psi = 0 on the inner boundary, 1 on the outer boundary, free on terminals
        inner = idx[((np.abs(yn - 1) < eps) & (xn <= a_len + eps)) | ((np.abs(xn - a_len) < eps) & (yn >= 1 - eps))]
        outer = idx[(np.abs(yn) < eps) | (np.abs(xn - s) < eps)]
        r_hi = _q4_energy_solve(mask, np.concatenate([inner, outer]),
                                np.concatenate([np.zeros(len(inner)), np.ones(len(outer))]))
        print(f"   {n:2d} cells/width: {r_lo - 2 * a_len:.4f} <= d <= {r_hi - 2 * a_len:.4f}"
              f"   (bracket {r_hi - r_lo:.4f} sq; midpoint {0.5 * (r_lo + r_hi) - 2 * a_len:.4f})")


def sec_braess(h):
    """Rayleigh monotonicity covers self-resistance and total loss, not transfer resistance:
    a copper bridge that lowers total loss can raise the drop at another load."""
    from shapely.geometry import box as sbox
    print(f"== braess: adding copper lowers total loss but can raise one load's drop (grid {h} mm)")
    g = tp.Grid(h)
    hum = tp.human_layout(g)
    r0, d0, _, u0 = tp.evaluate(g, hum)
    for name, rect in (("bridge x 17.0-18.5, y 2.5-12 (A branch to B branch)", (17.0, 2.5, 18.5, 12.0)),
                       ("bridge x 13.0-14.5, y 2.5-12 (A branch to C/B branch)", (13.0, 2.5, 14.5, 12.0))):
        cu = hum | g.rasterize(sbox(*rect))
        cu &= ~g.void
        r1, d1, _, _ = tp.evaluate(g, cu)
        print(f"  {name}: +{(cu.sum() - hum.sum()) * h * h:.1f} mm2 copper")
        print(f"    total loss R {r0 * 1e3:.3f} -> {r1 * 1e3:.3f} mOhm ({(r1 / r0 - 1) * 100:+.1f}%);"
              f" drops A/B/C {d0[0]:.2f}/{d0[1]:.2f}/{d0[2]:.2f} -> {d1[0]:.2f}/{d1[1]:.2f}/{d1[2]:.2f} mV")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("section", nargs="?", default="all",
                    choices=["floor", "slot", "cluster", "lattice", "bracket", "braess", "all"])
    ap.add_argument("--h", type=float, default=0.2, help="grid pitch for floor/slot, mm (round 1 used 0.1)")
    a = ap.parse_args()
    if a.section in ("cluster", "all"):
        sec_cluster()
    if a.section in ("lattice", "all"):
        sec_lattice()
    if a.section in ("bracket", "all"):
        sec_bracket()
    if a.section in ("braess", "all"):
        sec_braess(a.h)
    if a.section in ("floor", "all"):
        sec_floor(a.h)
    if a.section in ("slot", "all"):
        sec_slot(a.h)


if __name__ == "__main__":
    main()
