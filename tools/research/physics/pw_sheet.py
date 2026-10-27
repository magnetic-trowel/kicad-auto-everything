# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""2-D current-flow (Laplace) solver for copper masks, plus the power-copper experiments.

Workstream 4 (power). One equation serves three physical questions, because a
thin copper sheet obeys div(grad V) = 0 in all of them:

  * DC resistance of a pour or trace:     R = R_s * N_sq        (R_s = rho/t)
  * Plane-pair spreading inductance:      L = mu0 * d * N_sq    (d = plane spacing,
    below the first cavity resonance; also a vertical / overlapped loop whose
    return copy sits a distance d under the forward copper)
  * Plane-pair capacitance (not from N_sq): C = eps * A / d

N_sq is the number of "squares" between two electrodes, which this solver
computes for any copper mask. Grid: square cells of side dx, one node per copper
cell, unit conductance between edge-neighbours (units of 1/R_s).

Experiments (python pw_sheet.py [corner|thermal|pour|viafield|spread|cluster|terminal|all]):
  corner   squares and current crowding of 90 deg / chamfer / arc bends
  thermal  steady and pulse (adiabatic) temperature penalty of corner crowding
  pour     regulator-to-load: traces vs pours vs full region; entry constriction;
           greedy trimming of low-|J| copper (how much pour is useful)
  viafield effective sheet-resistance multiplier of a plane perforated by antipads
  spread   plane-pair spreading inductance between two vias, with the Peaceman
           sub-cell well correction, checked against (1/pi) ln(D/r) and against
           Archambeault's 154 pH / 545 pH anchors
  cluster  N parallel vias at pitch p feeding a plane pair: diminishing returns
  terminal overlapped-loop plate fed by narrow terminals: where widening stops helping

Deterministic. Each experiment runs in seconds to about a minute on one core
(numpy + scipy only). All numbers quoted with [C] in docs/topics/physics/
power-copper.md and pdn-and-commutation.md come from this file.
"""
import math
import sys

import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as spla
from scipy import ndimage

MU0 = 4e-7 * math.pi
RHO_CU = 1.72e-8       # ohm m, 20 C
K_CU = 390.0           # W/m/K
T_1OZ = 35e-6          # m
RS_1OZ = RHO_CU / T_1OZ
CV_CU = 3.45e6         # volumetric heat capacity J/m^3/K
K_FR4 = 0.3            # W/m/K (through-plane, typical)


# --------------------------------------------------------------------------
# core solver
# --------------------------------------------------------------------------
def solve(mask, electrodes):
    """Solve the sheet Laplace problem.

    mask: 2-D bool array, True = copper.
    electrodes: list of (bool mask, potential). Electrode cells are Dirichlet.
    Returns (V, currents) with V NaN off-copper and currents[i] = net current
    leaving electrode i (units: volts / R_s, i.e. per-square conductance).
    """
    ny, nx = mask.shape
    fixed = np.zeros(mask.shape, bool)
    vfix = np.zeros(mask.shape)
    for em, v in electrodes:
        em = em & mask
        fixed |= em
        vfix[em] = v
    free = mask & ~fixed
    idx = -np.ones(mask.shape, np.int64)
    idx[free] = np.arange(free.sum())
    n = int(free.sum())
    rows, cols, vals = [], [], []
    diag = np.zeros(n)
    rhs = np.zeros(n)
    for dy, dx in ((0, 1), (1, 0)):
        a = mask[: ny - dy, : nx - dx] & mask[dy:, dx:]
        ia = idx[: ny - dy, : nx - dx][a]
        ib = idx[dy:, dx:][a]
        fa = free[: ny - dy, : nx - dx][a]
        fb = free[dy:, dx:][a]
        va = vfix[: ny - dy, : nx - dx][a]
        vb = vfix[dy:, dx:][a]
        # free-free
        ff = fa & fb
        rows += [ia[ff], ib[ff]]
        cols += [ib[ff], ia[ff]]
        vals += [-np.ones(ff.sum()), -np.ones(ff.sum())]
        np.add.at(diag, ia[fa], 1.0)
        np.add.at(diag, ib[fb], 1.0)
        # free-fixed
        m1 = fa & ~fb
        np.add.at(rhs, ia[m1], vb[m1])
        m2 = fb & ~fa
        np.add.at(rhs, ib[m2], va[m2])
    A = sp.csr_matrix((np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))), shape=(n, n))
    A = A + sp.diags(diag)
    x = spla.spsolve(A.tocsc(), rhs) if n else np.zeros(0)
    V = np.full(mask.shape, np.nan)
    V[free] = x
    V[fixed] = vfix[fixed]
    currents = []
    for em, _ in electrodes:
        em = em & mask
        I = 0.0
        for dy, dx in ((0, 1), (1, 0)):
            a = mask[: ny - dy, : nx - dx] & mask[dy:, dx:]
            ea = em[: ny - dy, : nx - dx] & a
            eb = em[dy:, dx:] & a
            Va = V[: ny - dy, : nx - dx]
            Vb = V[dy:, dx:]
            I += np.nansum((Va - Vb)[ea & ~eb[...]])  # leaving through +dir face
            I += np.nansum((Vb - Va)[eb & ~ea])
        currents.append(I)
    return V, currents


def jmag(mask, V):
    """|J| per cell (sheet current, units V/R_s per cell width), centred differences of face currents."""
    ny, nx = mask.shape
    Vz = np.where(mask, V, 0.0)
    jx = np.zeros(mask.shape)
    jy = np.zeros(mask.shape)
    fx = np.zeros((ny, nx + 1))
    fy = np.zeros((ny + 1, nx))
    a = mask[:, :-1] & mask[:, 1:]
    fx[:, 1:-1] = np.where(a, Vz[:, :-1] - Vz[:, 1:], 0.0)
    a = mask[:-1, :] & mask[1:, :]
    fy[1:-1, :] = np.where(a, Vz[:-1, :] - Vz[1:, :], 0.0)
    jx = 0.5 * (fx[:, :-1] + fx[:, 1:])
    jy = 0.5 * (fy[:-1, :] + fy[1:, :])
    return np.where(mask, np.hypot(jx, jy), 0.0)


def squares(mask, ea, eb):
    _, I = solve(mask, [(ea, 1.0), (eb, 0.0)])
    return 1.0 / I[0]


def peaceman_sq(dx, r):
    """Extra squares of a via of radius r modelled as one grid cell (Peaceman 1978, r_o = 0.198 dx)."""
    return math.log(0.198 * dx / r) / (2 * math.pi)


# --------------------------------------------------------------------------
# geometry helpers (all lengths in units of the cell size unless noted)
# --------------------------------------------------------------------------
def bend(kind, n, arm=8.0, ri=0.5):
    """L-bend of unit width w=1 resolved by n cells per width. Arms of centreline
    length `arm` (to the corner centre). Returns mask, eA, eB, ideal centreline squares."""
    pad = 2
    size = int((arm + 1.0 + ri + 2) * n) + 2 * pad
    yy, xx = np.mgrid[0:size, 0:size]
    x = (xx - pad + 0.5) / n
    y = (yy - pad + 0.5) / n
    # corner centre at (c, c); arm 1 horizontal to the right, arm 2 vertical downward... use quadrant layout
    c = 1.0 + ri  # leave room for the inner radius
    # horizontal arm: y in [c-0.5, c+0.5], x from c to c+arm ; vertical arm: x in [c-0.5,c+0.5], y from c to c+arm
    m = np.zeros((size, size), bool)
    if kind in ("sharp", "miter", "chamfer", "fillet"):
        h = (np.abs(y - c) <= 0.5) & (x >= c - 0.5) & (x <= c + arm)
        v = (np.abs(x - c) <= 0.5) & (y >= c - 0.5) & (y <= c + arm)
        m = h | v
        if kind == "miter":    # outer corner cut so the diagonal width stays w; inner corner sharp
            m &= ~((x - (c - 0.5)) + (y - (c - 0.5)) < 2 - math.sqrt(2))
        if kind == "chamfer":  # two 135-degree corners: a constant-width 45-degree segment
            m &= ~((x - (c - 0.5)) + (y - (c - 0.5)) < 1.0)
            m |= (x >= c + 0.5) & (y >= c + 0.5) & ((x - (c + 0.5)) + (y - (c + 0.5)) <= math.sqrt(2) - 1)
        if kind == "fillet":   # inner fillet of radius ri (concave web), outer kept square
            web = (x >= c + 0.5) & (y >= c + 0.5) & (x <= c + 0.5 + ri) & (y <= c + 0.5 + ri)
            out = (x - (c + 0.5 + ri)) ** 2 + (y - (c + 0.5 + ri)) ** 2 >= ri ** 2
            m |= web & out
        ideal = 2 * arm
    elif kind == "arc":  # constant-width annular bend, inner radius ri, centred at (c+0.5+ri, c+0.5+ri)
        cx = cy = c + 0.5 + ri
        r = np.hypot(x - cx, y - cy)
        ring = (r >= ri) & (r <= ri + 1.0) & (x <= cx) & (y <= cy)
        rc = ri + 0.5
        h = (np.abs(y - c) <= 0.5) & (x >= cx) & (x <= c + arm)
        v = (np.abs(x - c) <= 0.5) & (y >= cy) & (y <= c + arm)
        m = ring | h | v
        ideal = 2 * (arm - rc) + 0.5 * math.pi * rc  # centreline length / width
    eA = m & (x > c + arm - 1.0 / n)
    eB = m & (y > c + arm - 1.0 / n)
    return m, eA, eB, ideal


def exp_corner():
    print("== corner: L-bends of unit width, arms 8 w; excess squares and crowding")
    print("kind        n/w  ideal_sq  N_sq   excess   Jpk/J0")
    rows = []
    for kind, ri in (("sharp", 0.5), ("miter", 0.5), ("chamfer", 0.5), ("fillet", 0.5), ("fillet", 1.0), ("arc", 0.5), ("arc", 2.0)):
        for n in (20, 40, 80):
            m, ea, eb, ideal = bend(kind, n, ri=ri)
            V, I = solve(m, [(ea, 1.0), (eb, 0.0)])
            nsq = 1.0 / I[0]
            # jmag is the current through one cell-width face; a straight strip of n cells carries I/n per cell
            jpk = jmag(m, V).max() / (I[0] / n)
            print(f"{kind:7s} ri={ri:<3} {n:3d}  {ideal:7.3f} {nsq:7.3f} {nsq-ideal:+7.3f}  {jpk:6.2f}")
            rows.append((kind, ri, n, ideal, nsq, jpk))
    print("note: sharp-corner peak grows with resolution (r^-1/3 singularity); fillet/arc converge.")
    print("annulus check: arc inner-edge crowding (1/ri)/ln(1+1/ri):",
          {ri: round((1 / ri) / math.log(1 + 1 / ri), 3) for ri in (0.5, 2.0)})
    return rows


# --------------------------------------------------------------------------
# electro-thermal: does corner crowding create a hot spot?
# --------------------------------------------------------------------------
def heat_solve(K, g, q, dxm):
    """Steady sheet heat equation: div(K grad T) - g T + q = 0 on the whole grid.
    K: sheet conductance W/K per square (k*t) per cell; g: W/m^2/K to the sink; q: W per cell."""
    ny, nx = K.shape
    n = ny * nx
    ids = np.arange(n).reshape(ny, nx)
    rows, cols, vals = [], [], []
    diag = g.ravel() * dxm * dxm
    diag = diag.copy()
    for dy, dx in ((0, 1), (1, 0)):
        ka = K[: ny - dy, : nx - dx]
        kb = K[dy:, dx:]
        c = (2 * ka * kb / (ka + kb)).ravel()
        ia = ids[: ny - dy, : nx - dx].ravel()
        ib = ids[dy:, dx:].ravel()
        rows += [ia, ib]
        cols += [ib, ia]
        vals += [-c, -c]
        np.add.at(diag, ia, c)
        np.add.at(diag, ib, c)
    A = sp.csr_matrix((np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))), shape=(n, n)) + sp.diags(diag)
    return spla.spsolve(A.tocsc(), q.ravel()).reshape(ny, nx)


def exp_thermal():
    print("== thermal: does inside-corner crowding make a hot spot? 1 mm wide 1 oz trace, 5 A")
    w = 1e-3
    n = 20                      # cells per width -> dx = 50 um
    I_amp = 5.0
    out = []
    for kind in ("sharp", "arc"):
        m, ea, eb, _ = bend(kind, n, arm=10.0, ri=0.5)
        V, I = solve(m, [(ea, 1.0), (eb, 0.0)])
        scale = I_amp / I[0]   # amps per (V/R_s)
        jcell = jmag(m, V) * scale            # amps through a cell-width face
        dxm = w / n
        Jsheet = jcell / dxm                  # A/m sheet current density
        q = Jsheet ** 2 * RS_1OZ * dxm * dxm  # W per cell
        pad = 150                             # 7.5 mm of laminate around
        mm = np.pad(m, pad)
        qq = np.pad(q, pad)
        for label, g, klam in (("no plane, 1.6 mm FR-4, convection both faces", 20.0, K_FR4 * 1.6e-3),
                               ("plane 0.1 mm below (isothermal sink)", K_FR4 / 1e-4, K_FR4 * 0.1e-3)):
            K = np.where(mm, K_CU * T_1OZ + klam, klam)
            gg = np.full(mm.shape, g)
            T = heat_solve(K, gg, qq, dxm)
            # straight-trace reference: average over arm far from corner
            ys, xs = np.nonzero(mm)
            far = np.zeros(mm.shape, bool)
            cy = int(np.median(ys))
            Tc = T[mm].max()
            # reference: same solve with straight strip of the same length
            out.append((kind, label, Tc))
            print(f"  {kind:5s} | {label:45s} | Tmax {Tc:7.2f} K")
        # straight reference
    for label, g, klam in (("no plane, 1.6 mm FR-4, convection both faces", 20.0, K_FR4 * 1.6e-3),
                           ("plane 0.1 mm below (isothermal sink)", K_FR4 / 1e-4, K_FR4 * 0.1e-3)):
        L = 20.0
        size = int((L + 2) * n)
        mstr = np.zeros((3 * n, size), bool)
        mstr[n:2 * n, n:size - n] = True
        dxm = w / n
        Jsheet = I_amp / w
        q = np.where(mstr, Jsheet ** 2 * RS_1OZ * dxm * dxm, 0.0)
        pad = 150
        mm = np.pad(mstr, pad)
        qq = np.pad(q, pad)
        K = np.where(mm, K_CU * T_1OZ + klam, klam)
        T = heat_solve(K, np.full(mm.shape, g), qq, dxm)
        print(f"  strt  | {label:45s} | Tmax {T[mm].max():7.2f} K (straight 20 mm, same current)")
    # adiabatic pulse: hot-spot factor = (J averaged over the thermal diffusion length)^2
    print("  pulse (adiabatic) hot-spot factor at the sharp inside corner, J^2 averaged over a disk of the")
    print("  copper diffusion length sqrt(alpha t), alpha = k/cv = %.2e m^2/s:" % (K_CU / CV_CU))
    m, ea, eb, _ = bend("sharp", 80, arm=6.0)
    V, I = solve(m, [(ea, 1.0), (eb, 0.0)])
    J = jmag(m, V) / (I[0] / 80)
    yy, xx = np.nonzero(J == J.max())
    for tp in (1e-6, 1e-5, 1e-4, 1e-3, 1e-2):
        ld = math.sqrt(K_CU / CV_CU * tp)
        r = max(ld / 1e-3 * 80, 0.5)  # cells, for w = 1 mm
        Y, X = np.mgrid[0:J.shape[0], 0:J.shape[1]]
        disk = ((Y - yy[0]) ** 2 + (X - xx[0]) ** 2 <= r * r) & m
        f = (J[disk] ** 2).mean()
        print(f"    t = {tp:7.0e} s  l_d = {ld*1e3:6.3f} mm  <J^2>/J0^2 = {f:5.2f}")


# --------------------------------------------------------------------------
# pour vs trace between a regulator pad and a load pad
# --------------------------------------------------------------------------
def exp_pour():
    print("== pour: 2x2 mm source pad -> 2x2 mm load pad, centres 30 mm apart, 1 oz (R_s = %.3f mOhm/sq)" % (RS_1OZ * 1e3))
    dx = 0.1  # mm
    Wd, Hd = 44.0, 30.0
    ny, nx = int(Hd / dx), int(Wd / dx)
    yy, xx = np.mgrid[0:ny, 0:nx]
    x = (xx + 0.5) * dx - 7.0     # source pad centre at x=0, load at x=30
    y = (yy + 0.5) * dx - Hd / 2
    padA = (np.abs(x) <= 1.0) & (np.abs(y) <= 1.0)
    padB = (np.abs(x - 30) <= 1.0) & (np.abs(y) <= 1.0)
    res = []
    print("shape                      area mm2   N_sq    R mOhm   R x area")
    for label, m in (
        ("trace 0.5 mm", (np.abs(y) <= 0.25) & (x >= 0) & (x <= 30)),
        ("trace 1 mm", (np.abs(y) <= 0.5) & (x >= 0) & (x <= 30)),
        ("trace 2 mm (= pad width)", (np.abs(y) <= 1.0) & (x >= 0) & (x <= 30)),
        ("trace 4 mm", (np.abs(y) <= 2.0) & (x >= -1) & (x <= 31)),
        ("pour 8 mm wide", (np.abs(y) <= 4.0) & (x >= -2) & (x <= 32)),
        ("pour 16 mm wide", (np.abs(y) <= 8.0) & (x >= -4) & (x <= 34)),
        ("full region 44x30", np.ones_like(padA)),
    ):
        mm = m | padA | padB
        nsq = squares(mm, padA, padB)
        area = mm.sum() * dx * dx
        res.append((label, area, nsq))
        print(f"{label:26s} {area:8.1f} {nsq:7.2f} {nsq*RS_1OZ*1e3:8.3f}  {nsq*area:8.0f}")
    # where is the resistance? split potential drop in the full region
    mm = np.ones_like(padA)
    V, I = solve(mm, [(padA, 1.0), (padB, 0.0)])
    J = jmag(mm, V)
    P = J ** 2
    order = np.argsort(P.ravel())[::-1]
    cum = np.cumsum(P.ravel()[order]) / P.sum()
    for frac in (0.5, 0.8, 0.9, 0.99):
        k = np.searchsorted(cum, frac) + 1
        print(f"  full region: {frac*100:4.0f}% of the dissipation is in {k*dx*dx:7.1f} mm2 ({k/mm.sum()*100:4.1f}% of area)")
    # entry constriction: potential drop within 3 mm of each pad
    r = np.minimum(np.hypot(np.maximum(np.abs(x) - 1, 0), np.maximum(np.abs(y) - 1, 0)),
                   np.hypot(np.maximum(np.abs(x - 30) - 1, 0), np.maximum(np.abs(y) - 1, 0)))
    for rr in (1.0, 3.0, 5.0):
        Pin = P[(r <= rr)].sum() / P.sum()
        print(f"  full region: {Pin*100:4.1f}% of the dissipation lies within {rr} mm of the two pads")
    # greedy trimming of low-|J| copper from the full region
    print("  greedy trimming of the full region (remove lowest-|J| 10% of removable cells per step):")
    m = np.ones_like(padA)
    base = None
    keep = padA | padB
    for step in range(30):
        V, I = solve(m, [(padA, 1.0), (padB, 0.0)])
        nsq = 1.0 / I[0]
        if base is None:
            base = nsq
        area = m.sum() * dx * dx
        if step % 2 == 0 or area < 60:
            print(f"    area {area:7.1f} mm2 ({m.sum()/m.size*100:5.1f}%)  N_sq {nsq:6.2f}  (+{(nsq/base-1)*100:5.1f}%)")
        if area < 40:
            break
        J = jmag(m, V)
        cand = m & ~keep
        vals = J[cand]
        thr = np.quantile(vals, 0.15)
        m = m & ~(cand & (J <= thr))
        lab, nl = ndimage.label(m)
        la, lb = lab[padA][0], lab[padB][0]
        m = (lab == la) | (lab == lb)
    return res


# --------------------------------------------------------------------------
# plane perforated by antipads (BGA / via field)
# --------------------------------------------------------------------------
def exp_viafield():
    print("== viafield: square array of antipads (diameter D, pitch p) in a plane; sheet-R multiplier")
    print(" D/p   hole frac f   N_sq(cell)  Rayleigh (1+f)/(1-f)")
    n = 200
    yy, xx = np.mgrid[0:n, 0:n]
    x = (xx + 0.5) / n - 0.5
    y = (yy + 0.5) / n - 0.5
    rows = []
    for dp in (0.0, 0.3, 0.5, 0.6, 0.7, 0.8, 0.85, 0.9, 0.95):
        hole = np.hypot(x, y) < dp / 2
        m = ~hole
        # unit cell, mirror symmetry -> insulating top/bottom, electrodes on left/right columns
        ea = np.zeros_like(m)
        ea[:, 0] = True
        eb = np.zeros_like(m)
        eb[:, -1] = True
        nsq = squares(m, ea, eb) * n / (n - 1)  # electrodes at cell centres -> correct span
        f = math.pi * dp * dp / 4
        ray = (1 + f) / (1 - f)
        rows.append((dp, f, nsq, ray))
        print(f" {dp:4.2f}   {f:6.3f}      {nsq:7.3f}     {ray:7.3f}")
    print(" e.g. 1.0 mm BGA pitch, 0.6 mm antipad -> D/p 0.6; 0.8 mm pitch, 0.7 mm antipad -> D/p 0.875")
    return rows


# --------------------------------------------------------------------------
# plane-pair spreading inductance (two vias), Peaceman sub-cell correction
# --------------------------------------------------------------------------
def exp_spread():
    print("== spread: plane-pair spreading inductance between two vias, L = mu0 d N_sq")
    rv = 0.15e-3
    for size_mm, dx_mm, pairs in ((100.0, 0.5, (5.0, 10.0, 25.4, 50.0)), (254.0, 1.0, (25.4, 228.6))):
        n = int(size_mm / dx_mm)
        m = np.ones((n, n), bool)
        c = n // 2
        print(f"  plane {size_mm:.0f} x {size_mm:.0f} mm, dx {dx_mm} mm")
        for D in pairs:
            k = int(round(D / dx_mm))
            if size_mm > 200:
                i0 = int(round(12.7 / dx_mm))   # first via 0.5 in from the left edge, mid-height
                ia, ib = (c, i0), (c, i0 + k)
            else:
                ia, ib = (c, c - k // 2), (c, c - k // 2 + k)
            ea = np.zeros_like(m)
            ea[ia] = True
            eb = np.zeros_like(m)
            eb[ib] = True
            nsq = squares(m, ea, eb) + 2 * peaceman_sq(dx_mm * 1e-3, rv)
            inf = math.log(D * 1e-3 / rv) / math.pi
            print(f"    D = {D:6.1f} mm: N_sq {nsq:5.2f} (infinite-plane (1/pi)ln(D/r) = {inf:5.2f});"
                  f" L = {MU0*0.1e-3*nsq*1e12:5.0f} pH at d=0.1 mm, {MU0*0.075e-3*nsq*1e12:5.0f} pH at d=0.075 mm")
    print("  Archambeault anchors (10 in wide plane): 154 pH at 1 in, 545 pH at 10 in; ratio 3.5")


def exp_cluster():
    print("== cluster: N vias (r = 0.15 mm) at pitch p into a plane pair; squares to a ring at R = 10 mm")
    dx = 0.05  # mm (via radius = 3 cells)
    R = 10.0
    n = int(2 * R / dx) + 4
    yy, xx = np.mgrid[0:n, 0:n]
    x = (xx - n / 2 + 0.5) * dx
    y = (yy - n / 2 + 0.5) * dx
    r = np.hypot(x, y)
    m = r <= R
    ring = m & (r > R - dx)
    rv = 0.15
    print("  N   pitch   N_sq    L(d=0.1mm) pH   vs 1 via   ideal 1/N")
    single = None
    rows = []
    for N, p in ((1, 0), (2, 0.6), (2, 1.0), (2, 2.0), (4, 0.6), (4, 1.0), (4, 2.0), (9, 0.6), (9, 1.0), (9, 2.0), (16, 0.6), (16, 1.0)):
        k = int(round(math.sqrt(N)))
        if k * k != N:
            k = N  # row
        e = np.zeros_like(m)
        if N == 2:
            cs = [(-p / 2, 0), (p / 2, 0)]
        else:
            cs = [((i - (k - 1) / 2) * p, (j - (k - 1) / 2) * p) for i in range(k) for j in range(k)]
        for cx, cy in cs:
            e |= np.hypot(x - cx, y - cy) <= rv
        nsq = squares(m, e, ring)
        if single is None:
            single = nsq
        L = MU0 * 0.1e-3 * nsq * 1e12
        rows.append((N, p, nsq, L))
        print(f"  {N:2d}  {p:4.1f}  {nsq:6.3f}   {L:7.1f}        {nsq/single:5.2f}     {1/N:4.2f}")
    print("  analytic single via: (1/2pi) ln(R/r) =", round(math.log(R / rv) / (2 * math.pi), 3))
    return rows


def exp_terminal():
    print("== terminal: overlapped (vertical) loop plate of length l between two terminal rows of width a;")
    print("   L = mu0 h N_sq (h = 0.1 mm). Widening the plate helps only while the terminals can spread into it.")
    dx = 0.02  # mm
    for l, a in ((2.0, 1.0), (2.0, 3.0), (4.0, 1.0)):
        print(f"  l = {l} mm, terminal width a = {a} mm:")
        for W in (a, 1.5 * a, 2 * a, 3 * a, 6 * a, 12 * a):
            ny, nx = int(round(W / dx)), int(round(l / dx))
            m = np.ones((ny, nx), bool)
            ea = np.zeros_like(m)
            eb = np.zeros_like(m)
            j0, j1 = int(round((W - a) / 2 / dx)), int(round((W + a) / 2 / dx))
            ea[j0:j1, 0] = True
            eb[j0:j1, -1] = True
            nsq = squares(m, ea, eb) * nx / (nx - 1)
            print(f"    W = {W:5.1f} mm: N_sq {nsq:6.3f}  L = {MU0*0.1e-3*nsq*1e12:6.1f} pH  (ideal l/W = {l/W:5.3f} sq)")


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    exps = {"corner": exp_corner, "thermal": exp_thermal, "pour": exp_pour, "viafield": exp_viafield,
            "spread": exp_spread, "cluster": exp_cluster, "terminal": exp_terminal}
    for k, f in exps.items():
        if which in (k, "all"):
            f()
