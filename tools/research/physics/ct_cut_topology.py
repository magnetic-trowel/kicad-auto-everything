# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Conservation-and-topology (CT lens) checks on copper sheets, loops and cut sets.

All sheet models are DC resistor networks on square cells (one node per cell,
conductance 1/Rs between edge-adjacent copper cells). A *zero-width cut* removes
the conductances that cross a line of cell faces, so it changes the topology of
the sheet without removing any copper area: it is a pure "crack".

Sections (each prints a short table):

  strip    Cut law in a uniform strip of width W carrying current I. Zero-width
           centred slits and edge notches on two grids (Richardson-extrapolated)
           against the closed forms, written with x = dpsi/I (the fraction of the
           current the cut intercepts):
               centred slit:  dR = (2/pi) Rs ln sec(pi x / 2)  -> (pi/4) Rs x^2
               edge notch:    dR = (4/pi) Rs ln sec(pi x / 2)  -> (pi/2) Rs x^2
           (conformal-map results behind Johnson's potential-drop crack formula;
           the small-x limits are the 2-D crack polarization). Also an off-centre
           slit, to test "cost depends only on dpsi".
  pour     The solver-ladder pour of sl_tier_costs.py (40x30 mm, 1 oz, cut-out,
           antipad rows, 16 x 0.5 A sinks). (a) Its 6 mm slot, which a first-order
           adjoint underestimated 30x; (b) 60 random zero-width cuts. Exact cost by
           a Woodbury update of the base factorization, against: the first-order
           adjoint, the uniform dpsi^2 law, the Chebyshev crack quadratic form (same
           base solve) and that form times a ligament (finite-width) factor.
  neck     Current-free peninsula: a 12x12 mm island isolated by a slot ring except
           for a neck of width w, in a uniform aggressor current. Potential spread
           over the island's central 6x6 mm vs w, for a neck on a flank (mouth along
           the flow) and at the upstream stagnation point (mouth on an equipotential).
  closure  Partial-inductance attribution vs the EMF a victim actually sees: the
           victim's own closing conductor (a second via, a parallel return trace)
           at distance s from the shared aggressor segment.
  nest     Coplanar square loops: mutual inductance when the victim sits inside the
           aggressor loop (nested) vs just outside, in free space and over a plane.
  cm       Board-world cut set on a lumped half-bridge + heatsink + chassis + LISN
           graph: CM current = d/dt of the board's external charge; heatsink bond
           options as cycle insertion; a cycle census from a minimum-|Z| spanning tree.

Run:  python tools/research/physics/ct_cut_topology.py [strip|pour|neck|closure|nest|cm|all]
Deterministic. 'all' takes about 4-6 min on one CPU (strip ~2-3 min, pour ~1 min).
Needs numpy, scipy, pyamg (strip only).
"""

import math
import os
import sys
import time

import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as spla

MU0 = 4e-7 * math.pi
RS_1OZ = 1.72e-8 / 35e-6  # ohm/sq, 1 oz copper at 20 C


# ----------------------------------------------------------------------------- helpers
def lnsec(x):
    return -np.log(np.cos(x))


def ligament_factor(x):
    """Exact finite-width strip law divided by its small-cut limit, x = cut length / width.

    Same function for a centred slit (x = slit length / strip width) and an edge notch
    (x = notch depth / strip width): F(x) = (8/pi^2) ln sec(pi x/2) / x^2, F(0) = 1.
    """
    x = np.atleast_1d(np.asarray(x, float))
    out = np.ones_like(x)
    m = x > 1e-9
    out[m] = (8 / np.pi ** 2) * lnsec(np.pi * np.minimum(x[m], 0.999999) / 2) / x[m] ** 2
    return out


def sheet_laplacian(mask, g=1.0, cut_h=None, cut_v=None):
    """Graph Laplacian of the copper cells in `mask` (ny, nx).

    cut_h (ny, nx-1) True removes the edge (j,i)-(j,i+1); cut_v (ny-1, nx) removes (j,i)-(j+1,i).
    Returns (L csr, idx) with idx[j,i] = node number or -1.
    """
    ny, nx = mask.shape
    idx = -np.ones(mask.shape, np.int64)
    idx[mask] = np.arange(int(mask.sum()))
    eh = mask[:, :-1] & mask[:, 1:]
    if cut_h is not None:
        eh = eh & ~cut_h
    ev = mask[:-1, :] & mask[1:, :]
    if cut_v is not None:
        ev = ev & ~cut_v
    a = np.concatenate([idx[:, :-1][eh], idx[:-1, :][ev]])
    b = np.concatenate([idx[:, 1:][eh], idx[1:, :][ev]])
    n = int(mask.sum())
    rows = np.concatenate([a, b, a, b])
    cols = np.concatenate([a, b, b, a])
    vals = np.concatenate([np.full(a.size, g), np.full(a.size, g), np.full(a.size, -g), np.full(a.size, -g)])
    return sp.csr_matrix((vals, (rows, cols)), shape=(n, n)), idx


def chebyshev_crack_energy(jn, a, rs, mirrored=False, kmax=12):
    """Crack quadratic form for a straight insulating cut in an infinite sheet.

    jn: normal sheet-current density (A/m) sampled at equal steps along the cut.
    a:  half-length of the (possibly mirrored) crack, m.
    Expands jn in U_{k-1}(xi) with weight sqrt(1-xi^2) and returns
        dP = pi a^2 Rs sum_k c_k^2 / k        (interior crack)
    For an edge-touching cut, pass the samples from the boundary outwards with
    mirrored=True: the crack is reflected about the boundary (a = cut length) and
    half of the reflected crack's energy is returned.
    """
    jn = np.asarray(jn, float)
    n = jn.size
    if mirrored:
        xi = (np.arange(n) + 0.5) / n                    # 0..1 from the boundary
        xi = np.concatenate([-xi[::-1], xi])
        jj = np.concatenate([jn[::-1], jn])
        dxi = 1.0 / n
    else:
        xi = -1 + (np.arange(n) + 0.5) * 2.0 / n
        jj = jn
        dxi = 2.0 / n
    w = np.sqrt(np.clip(1 - xi ** 2, 0, None))
    th = np.arccos(np.clip(xi, -1, 1))
    total = 0.0
    for k in range(1, min(kmax, max(1, n // 2)) + 1):
        uk = np.sin(k * th) / np.where(np.abs(np.sin(th)) < 1e-12, 1e-12, np.sin(th))  # U_{k-1}
        ck = (2 / np.pi) * np.sum(jj * uk * w) * dxi
        total += ck * ck / k
    e = np.pi * a * a * rs * total
    return 0.5 * e if mirrored else e


# ----------------------------------------------------------------------------- strip
def _strip_solver(ny, nx):
    import pyamg
    mask = np.ones((ny, nx), bool)
    L, idx = sheet_laplacian(mask)
    fixed = np.zeros((ny, nx), bool)
    fixed[:, 0] = True
    fixed[:, -1] = True
    f = ~fixed.ravel()
    d = fixed.ravel()
    vd = np.zeros(ny * nx)
    vd[idx[:, 0]] = 1.0
    ml = pyamg.smoothed_aggregation_solver(L[f][:, f].tocsr(), symmetry="symmetric")
    return dict(ny=ny, nx=nx, mask=mask, f=f, d=d, vd=vd, ml=ml, idx=idx)


def _strip_resistance(S, cut_h=None):
    L, idx = sheet_laplacian(S["mask"], cut_h=cut_h)
    f, d, vd = S["f"], S["d"], S["vd"]
    Lff = L[f][:, f].tocsr()
    rhs = -(L[f][:, d] @ vd[d])
    M = S["ml"].aspreconditioner(cycle="V")
    x, info = spla.cg(Lff, rhs, M=M, rtol=1e-12, atol=0.0, maxiter=2000)
    v = vd.copy()
    v[f] = x
    v = v.reshape(S["ny"], S["nx"])
    e = np.ones(S["ny"], bool) if cut_h is None else ~cut_h[:, 0]
    current = float(((1.0 - v[:, 1]) * e).sum())
    return 1.0 / current, info


def sec_strip():
    print("== strip: zero-width cuts across a uniform strip, W = 20 mm, length 60 mm, Rs = 1 (squares)")
    print("   closed forms with x = dpsi/I:  slit (2/pi) ln sec(pi x/2),  notch (4/pi) ln sec(pi x/2)")
    W_mm, L_mm = 20.0, 60.0
    grids = (0.1, 0.05)
    cases = []  # (label, kind, length_mm, y0_mm)
    for x in (0.1, 0.25, 0.5, 0.75, 0.9):
        cases.append((f"centred slit, x={x:.2f}", "slit", x * W_mm, (W_mm - x * W_mm) / 2))
    for x in (0.1, 0.25, 0.5, 0.75, 0.9):
        cases.append((f"edge notch,   x={x:.2f}", "notch", x * W_mm, 0.0))
    cases.append(("off-centre slit x=0.20 at y=2-6 mm", "slit_off", 4.0, 2.0))
    cases.append(("off-centre slit x=0.20 at y=1-5 mm", "slit_off", 4.0, 1.0))
    res = {}
    for dmm in grids:
        t0 = time.perf_counter()
        ny, nx = int(round(W_mm / dmm)), int(round(L_mm / dmm))
        S = _strip_solver(ny, nx)
        R0, _ = _strip_resistance(S)
        print(f"  grid {dmm} mm ({ny}x{nx}): R0 = {R0:.6f} sq (exact {(nx-1)/ny:.6f}); setup {time.perf_counter()-t0:.1f} s")
        ic = nx // 2
        for lab, kind, lmm, y0 in cases:
            j0 = int(round(y0 / dmm))
            j1 = j0 + int(round(lmm / dmm))
            cut = np.zeros((ny, nx - 1), bool)
            cut[j0:j1, ic] = True
            R, info = _strip_resistance(S, cut)
            res[(lab, dmm)] = R - R0
    print("  case                                  x=dpsi/I   dR(0.1)  dR(0.05)  dR(Rich.)  closed form  small-cut law  Rich/closed")
    for lab, kind, lmm, y0 in cases:
        x = lmm / W_mm
        d1, d2 = res[(lab, 0.1)], res[(lab, 0.05)]
        rich = 2 * d2 - d1
        if kind == "notch":
            cf = (4 / np.pi) * lnsec(np.pi * x / 2)
            sm = (np.pi / 2) * x * x
        else:
            cf = (2 / np.pi) * lnsec(np.pi * x / 2) if kind == "slit" else float("nan")
            sm = (np.pi / 4) * x * x
        ratio = rich / cf if np.isfinite(cf) else rich / sm
        tag = "" if np.isfinite(cf) else " (vs small-cut)"
        print(f"  {lab:36s} {x:7.3f}  {d1:8.5f}  {d2:8.5f}  {rich:9.5f}  {cf:11.5f}  {sm:12.5f}   {ratio:6.3f}{tag}")
    xs = [c for c in cases if c[1] in ("slit", "notch")]
    print("  edge/slit ratio at equal dpsi (Richardson):", ", ".join(
        f"x={c[2]/W_mm:.2f}: {(2*res[(c[0],0.05)]-res[(c[0],0.1)])/(2*res[(s[0],0.05)]-res[(s[0],0.1)]):.3f}"
        for c in xs if c[1] == "notch" for s in xs if s[1] == "slit" and abs(s[2] - c[2]) < 1e-9))
    print("  (exact ratio is 2 at every x: the strip edge is a streamline, so a notch is half of a")
    print("   mirrored slit of twice the length that intercepts twice the current)")


# ----------------------------------------------------------------------------- pour
def _load_sl():
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)
    import sl_tier_costs as sl  # noqa: E402  (our own round-1 script)
    return sl


def _pour_system(mask, d, rs, sinks, cut_h=None, cut_v=None, src_cols=2):
    """Same physics as sl_tier_costs.build_ir (source columns tied to 0 V through 1e6 S,
    current sinks), but with optional zero-width cuts."""
    L, idx = sheet_laplacian(mask, g=1.0 / rs, cut_h=cut_h, cut_v=cut_v)
    src = idx[:, :src_cols][mask[:, :src_cols]]
    n = L.shape[0]
    pen = sp.csr_matrix((np.full(src.size, 1e6), (src, src)), shape=(n, n))
    b = np.zeros(n)
    for (j, i), cur in sinks:
        b[idx[j, i]] -= cur
    return (L + pen).tocsc(), b, idx


def _random_cuts(mask, wall, rng, n_each, d, max_len_mm=8.0, min_len_mm=1.0):
    """Generate straight zero-width cuts on cell faces.

    Returns a list of dicts: orient ('v' cuts a line of horizontal edges at face column ic;
    'h' cuts vertical edges at face row jc), start/stop along the line, kind ('interior' or
    'edge'), and ligament lengths to the nearest *wall* (board edge or cut-out; antipads are
    ignored for the ligament) along the cut line.
    """
    ny, nx = mask.shape
    fh = mask[:, :-1] & mask[:, 1:]      # conducting horizontal edges (vertical cut lines)
    fv = mask[:-1, :] & mask[1:, :]      # conducting vertical edges (horizontal cut lines)
    wh = wall[:, :-1] & wall[:, 1:]
    wv = wall[:-1, :] & wall[1:, :]
    cuts = []
    tries = 0
    while len(cuts) < 4 * n_each and tries < 200000:
        tries += 1
        orient = "v" if (len(cuts) % 2 == 0) else "h"
        kind = "edge" if (len(cuts) // 2) % 2 == 0 else "interior"
        nlen = int(rng.integers(int(min_len_mm / (d * 1e3)), int(max_len_mm / (d * 1e3)) + 1))
        if orient == "v":
            ic = int(rng.integers(2, nx - 3))
            col = fh[:, ic]
            wcol = wh[:, ic]
        else:
            jc = int(rng.integers(1, ny - 2))
            col = fv[jc, :]
            wcol = wv[jc, :]
        m = col.size
        if kind == "edge":
            # start at a face whose predecessor is insulating (boundary), go forward
            starts = np.where(col & np.r_[True, ~col[:-1]])[0]
            if starts.size == 0:
                continue
            s0 = int(rng.choice(starts))
            s1 = s0 + nlen
            if s1 >= m or not col[s0:s1].all() or not col[s1]:
                continue   # would sever or run off: skip
        else:
            s0 = int(rng.integers(1, m - nlen - 1))
            s1 = s0 + nlen
            if not col[s0 - 1:s1 + 1].all():
                continue
        # ligaments to the nearest wall along the line
        def run(arr, start, step):
            k = 0
            p = start
            while 0 <= p < m and arr[p]:
                k += 1
                p += step
            return k
        lig_hi = run(wcol, s1, +1)
        lig_lo = run(wcol, s0 - 1, -1) if kind == "interior" else 0
        cut = dict(orient=orient, pos=(ic if orient == "v" else jc), s0=s0, s1=s1, kind=kind,
                   lig_lo=lig_lo * d, lig_hi=lig_hi * d, length=(s1 - s0) * d)
        cuts.append(cut)
    return cuts


def sec_pour():
    sl = _load_sl()
    print("== pour: sl_tier_costs geometry (40x30 mm, 1 oz, cut-out, antipad rows, 16 x 0.5 A sinks), cell 0.1 mm")
    d = 0.1e-3
    rs = 1.72e-8 / 35e-6
    nx, ny = int(0.04 / d), int(0.03 / d)
    mask = sl.pour_mask(nx, ny, d)
    X, Y = np.meshgrid((np.arange(nx) + 0.5) * d, (np.arange(ny) + 0.5) * d)
    wall = ~((X > 0.015) & (X < 0.022) & (Y > 0.008) & (Y < 0.022))   # board edge + cut-out only
    sinks = [((int(cy / d), int(cx / d)), 0.5) for cx in (0.030, 0.032, 0.034, 0.036)
             for cy in (0.011, 0.013, 0.015, 0.017)]

    # (a) the slot that the first-order adjoint missed (cells removed, as in sl_tier_costs)
    A, b, idx = sl.build_ir(mask, d, rs, sinks)
    lu = spla.splu(A)
    v = lu.solve(b)
    P0 = b @ v
    m2 = mask.copy()
    j0, j1, i0, i1 = 0, int(round(0.006 / d)), int(round(0.018 / d)), int(round(0.018 / d)) + 2
    m2[j0:j1, i0:i1] = False
    A2, b2, _ = sl.build_ir(m2, d, rs, sinks)
    exact = spla.splu(A2).solve(b2) @ b2 - P0
    V = np.full(mask.shape, np.nan)
    V[mask] = v[idx[mask]]
    g = 1 / rs
    px = g * np.nan_to_num(np.diff(V, axis=1)) ** 2
    py = g * np.nan_to_num(np.diff(V, axis=0)) ** 2
    E = np.zeros(mask.shape)
    E[:, :-1] += px / 2
    E[:, 1:] += px / 2
    E[:-1, :] += py / 2
    E[1:, :] += py / 2
    adj = 2 * E[j0:j1, i0:i1][mask[j0:j1, i0:i1]].sum()
    # crack law on the cut line x = 18.1 mm (between the two removed columns): normal current
    # density from the base solution, edge-touching at y = 0 (board edge)
    Ih = g * (V[:, i0] - V[:, i0 + 1])          # A per edge across the face x = (i0+1) d
    jn = Ih[j0:j1] / d
    lcut = (j1 - j0) * d
    dpsi = Ih[j0:j1].sum()
    band = Ih[0:int(0.008 / d)].sum()
    crack = chebyshev_crack_energy(jn, lcut, rs, mirrored=True)
    unif = (np.pi / 2) * rs * dpsi ** 2
    wcut = (i1 - i0) * d
    # width correction for a cut of finite width w (thin-ellipse polarization, a(a+b) with b=w/2)
    widthf = 1 + (wcut / 2) / lcut
    lig = ligament_factor(lcut / 0.008)[0]
    print(f"  base loss {P0*1e3:.2f} mW; band under the cut-out carries {band:.3f} A, the 6 mm slot intercepts dpsi = {dpsi:.3f} A")
    print(f"  6 mm x 0.2 mm slot from the board edge (exact re-solve)     : +{exact*1e3:6.3f} mW")
    print(f"    first-order adjoint (cell powers, sl_tier_costs)         : +{adj*1e3:6.3f} mW  ({exact/adj:5.1f}x low)")
    print(f"    uniform crack law (pi/2) Rs dpsi^2                       : +{unif*1e3:6.3f} mW  ({exact/unif:5.2f}x low)")
    print(f"    Chebyshev crack form (non-uniform J_n), same base solve  : +{crack*1e3:6.3f} mW  ({exact/crack:5.2f}x low)")
    print(f"    x width factor {widthf:.3f} x ligament factor F({lcut/0.008:.2f}) = {lig:.3f}       : +{crack*widthf*lig*1e3:6.3f} mW  ({exact/(crack*widthf*lig):5.2f}x)")
    print(f"    adjoint miss: exact/adjoint = {exact/adj:.1f}; aspect-ratio prediction (pi/4)(l/w)F = "
          f"{(np.pi/4)*(lcut/wcut)*lig:.1f} (edge crack (pi/2) l^2 vs cell-power adjoint 4 l d, w = 2d)")

    # (b) random zero-width cuts, exact by Woodbury on the base factorization
    A0, b0, idx0 = _pour_system(mask, d, rs, sinks)
    lu0 = spla.splu(A0)
    v0 = lu0.solve(b0)
    P0b = b0 @ v0
    V0 = np.full(mask.shape, np.nan)
    V0[mask] = v0[idx0[mask]]
    rng = np.random.default_rng(7)
    cuts = _random_cuts(mask, wall, rng, 15, d)
    rows = []
    wood_err = []
    t0 = time.perf_counter()
    for ci, c in enumerate(cuts):
        s = np.arange(c["s0"], c["s1"])
        cut_h = np.zeros((ny, nx - 1), bool)
        cut_v = np.zeros((ny - 1, nx), bool)
        if c["orient"] == "v":
            ic = c["pos"]
            p_nodes = idx0[s, ic]
            q_nodes = idx0[s, ic + 1]
            cut_h[s, ic] = True
        else:
            jc = c["pos"]
            p_nodes = idx0[jc, s]
            q_nodes = idx0[jc + 1, s]
            cut_v[jc, s] = True
        w = v0[p_nodes] - v0[q_nodes]      # base edge voltages (V)
        # exact: re-factorize the cut sheet (independent of the base factorization)
        A1, b1, _ = _pour_system(mask, d, rs, sinks, cut_h=cut_h, cut_v=cut_v)
        try:
            dP_exact = float(b1 @ spla.splu(A1).solve(b1) - P0b)
        except RuntimeError:
            continue
        if ci < 3:
            # Woodbury on the base LU: dP = w^T (D^-1 - U^T G^-1 U)^-1 w; its Neumann series'
            # first term w^T D w is the first-order adjoint
            k = s.size
            n = A0.shape[0]
            U = sp.csc_matrix((np.r_[np.ones(k), -np.ones(k)],
                               (np.r_[p_nodes, q_nodes], np.r_[np.arange(k), np.arange(k)])), shape=(n, k))
            K = U.T @ lu0.solve(U.toarray())
            dP_w = float(w @ np.linalg.solve(np.eye(k) * rs - K, w))
            wood_err.append(abs(dP_w / dP_exact - 1))
        dP_adj = float(g * (w ** 2).sum())
        jn = g * w / d                     # A/m, normal sheet current along the cut
        dpsi = abs(float(g * w.sum()))
        lcut = c["length"]
        if c["kind"] == "edge":
            # samples from the touching end outwards
            crack = chebyshev_crack_energy(jn, lcut, rs, mirrored=True)
            unif = (np.pi / 2) * rs * dpsi ** 2
            x = lcut / (lcut + c["lig_hi"]) if c["lig_hi"] > 0 else 0.0
        else:
            crack = chebyshev_crack_energy(jn, lcut / 2, rs, mirrored=False)
            unif = (np.pi / 4) * rs * dpsi ** 2
            x = lcut / (lcut + c["lig_lo"] + c["lig_hi"])
        lig = ligament_factor(x)[0]
        rows.append((c, dP_exact, dP_adj, unif, crack, crack * lig, x))
    t1 = time.perf_counter()
    n_all = len(rows)
    rows = [r for r in rows if r[1] > 1e-3 * max(rr[1] for rr in rows)]
    print(f"  {len(rows)} of {n_all} random zero-width cuts (1-8 mm; half edge-touching) cost > 0.1% of the largest;"
          f" exact by re-factorization ({t1-t0:.1f} s); Woodbury on the base LU agrees to {max(wood_err):.1e}")
    print("  predictor / exact                      median   10%-90% range      within +-25%   within 2x")
    names = ["first-order adjoint", "uniform dpsi^2 law", "Chebyshev crack form", "Chebyshev x ligament"]
    for col, name in zip(range(2, 6), names):
        rat = np.array([r[col] / r[1] for r in rows])
        print(f"  {name:36s} {np.median(rat):7.3f}   {np.percentile(rat,10):6.3f} - {np.percentile(rat,90):6.3f}"
              f"      {np.mean(np.abs(np.log(rat)) < np.log(1.25))*100:5.0f}%       {np.mean(np.abs(np.log(rat)) < np.log(2))*100:5.0f}%")
    lr = np.array([r[0]["length"] / d for r in rows])
    ra = np.array([r[1] / r[2] for r in rows])
    slope = np.polyfit(np.log(lr), np.log(ra), 1)[0]
    print(f"  adjoint miss factor exact/adjoint grows as (cut length / cell)^{slope:.2f} (crack theory: 1.00)")
    big = [r for r in rows if r[6] > 0.6]
    if big:
        rat = np.array([r[5] / r[1] for r in big])
        print(f"  near-severing cuts (x > 0.6, n={len(big)}): Chebyshev x ligament median {np.median(rat):.3f}")
    print(f"  base loss {P0b*1e3:.2f} mW; largest random-cut cost {max(r[1] for r in rows)*1e3:.2f} mW")


# ----------------------------------------------------------------------------- neck
def sec_neck():
    print("== neck: 60x40 mm sheet, uniform aggressor current along x; 12x12 mm island isolated by a")
    print("   0.4 mm slot ring except a neck of width w. Spread = max-min potential over the island's")
    print("   central 6x6 mm, relative to the same region in a solid sheet. Cell 0.1 mm.")
    d = 0.1e-3
    nx, ny = int(0.060 / d), int(0.040 / d)
    X, Y = np.meshgrid((np.arange(nx) + 0.5) * d, (np.arange(ny) + 0.5) * d)
    cx, cy, half, ring = 0.030, 0.020, 0.006, 0.0004

    def solve(mask):
        L, idx = sheet_laplacian(mask)
        fixed = np.zeros(mask.shape, bool)
        fixed[:, 0] = True
        fixed[:, -1] = True
        fx = fixed[mask]
        vd = np.zeros(int(mask.sum()))
        vd[idx[:, 0][mask[:, 0]]] = 1.0
        f = ~fx
        x = spla.splu(L[f][:, f].tocsc()).solve(-(L[f][:, fx] @ vd[fx]))
        v = vd.copy()
        v[f] = x
        V = np.full(mask.shape, np.nan)
        V[mask] = v[idx[mask]]
        return V

    centre = (np.abs(X - cx) < 0.003) & (np.abs(Y - cy) < 0.003)
    V_solid = solve(np.ones((ny, nx), bool))
    ref = np.nanmax(V_solid[centre]) - np.nanmin(V_solid[centre])
    inner = (np.abs(X - cx) < half) & (np.abs(Y - cy) < half)
    outer = (np.abs(X - cx) < half + ring) & (np.abs(Y - cy) < half + ring)
    ringmask = outer & ~inner
    print("  neck w (mm)   flank (mouth along flow)   stagnation (upstream face)   upstream, 4 mm off-centre")
    out = {"flank": [], "stag": [], "off": []}
    ws = (0.4, 0.8, 1.6, 3.2, 6.4)
    for wmm in ws:
        w = wmm * 1e-3
        vals = []
        for where in ("flank", "stag", "off"):
            m = np.ones((ny, nx), bool)
            m &= ~ringmask
            if where == "flank":     # gap in the top side of the ring, centred on x = cx
                gap = ringmask & (Y > cy + half - 1e-9) & (np.abs(X - cx) < w / 2)
            elif where == "stag":    # gap in the left (upstream) side, centred on y = cy
                gap = ringmask & (X < cx - half + 1e-9) & (np.abs(Y - cy) < w / 2)
            else:
                gap = ringmask & (X < cx - half + 1e-9) & (np.abs(Y - (cy + 0.004)) < w / 2)
            m |= gap
            V = solve(m)
            s = (np.nanmax(V[centre]) - np.nanmin(V[centre])) / ref
            out[where].append(s)
            vals.append(s)
        print(f"  {wmm:8.1f}      {vals[0]:12.3e}             {vals[1]:12.3e}               {vals[2]:12.3e}")
    lw = np.log(np.array(ws))
    for k, lab in (("flank", "flank"), ("stag", "stagnation"), ("off", "off-centre")):
        y = np.log(np.array(out[k]))
        loc = np.diff(y) / np.diff(lw)
        print(f"  local log-log slopes, {lab:11s}: " + ", ".join(
            f"{ws[i]:.1f}-{ws[i+1]:.1f} mm: {loc[i]:.2f}" for i in range(len(loc))))
    print("  stagnation / flank:", ", ".join(f"w={w_:.1f}: {s/f:.1e}" for w_, s, f in zip(ws, out["stag"], out["flank"])))
    print("  (exact zero at w -> 0: a region joined at one point carries no through current. For w >> ring")
    print("   width the leakage is an aperture dipole, ~w^2, driven by the aggressor's tangential field along")
    print("   the mouth; with the mouth on an equipotential (stagnation point) the dipole vanishes and the")
    print("   quadrupole, ~w^4, remains. For w ~ ring width the neck's own resistance steepens both.)")


# ----------------------------------------------------------------------------- closure
def m_par(l, s):
    """Mutual partial inductance of two parallel, aligned filaments of length l at distance s (H)."""
    return MU0 * l / (2 * np.pi) * (np.arcsinh(l / s) - np.sqrt(1 + (s / l) ** 2) + s / l)


def sec_closure():
    print("== closure: what a victim sees from a shared aggressor segment, by the victim's own closure")
    print("   EMF_victim / (jw I_aggr) = Lp(shared) - M(shared, victim's closing conductor) [+ far terms]")
    l, r = 1.6e-3, 0.15e-3
    Lp = m_par(l, r)          # thin-tube via: GMD = r
    print(f"  (a) TVS ground via, 1.6 mm long, r = 0.15 mm: Lp = {Lp*1e9:.3f} nH (partial self, thin tube)")
    print("      victim IC's own ground via at s:   s (mm)   M (nH)   seen (nH)   seen / Lp")
    for s in (0.5, 1.0, 2.0, 5.0, 10.0):
        M = m_par(l, s * 1e-3)
        print(f"                                        {s:5.1f}   {M*1e9:6.3f}   {(Lp-M)*1e9:7.3f}     {(Lp-M)/Lp:6.2f}")
    l2, wtr = 20e-3, 0.5e-3
    gmd = 0.2235 * wtr
    Lp2 = m_par(l2, gmd)
    print(f"  (b) shared ground trace 20 mm x 0.5 mm (2-layer board): Lp = {Lp2*1e9:.2f} nH")
    print("      victim's reference conductor parallel at s:   s (mm)   seen / Lp")
    for s in (0.5, 1.0, 2.0, 5.0, 10.0, 20.0):
        M = m_par(l2, s * 1e-3)
        print(f"                                                  {s:5.1f}     {(Lp2-M)/Lp2:6.2f}")
    print("  (Partial inductance is a gauge-dependent share of a cycle's flux; only cycle sums are physical.")
    print("   It equals the coupling only when the victim closes far away or at right angles.)")


# ----------------------------------------------------------------------------- nest
def _square(cx, cy, side, z, n_per_side=200, ccw=True):
    h = side / 2
    corners = np.array([[cx - h, cy - h], [cx + h, cy - h], [cx + h, cy + h], [cx - h, cy + h]])
    if not ccw:
        corners = corners[::-1]
    pts = []
    for k in range(4):
        p, q = corners[k], corners[(k + 1) % 4]
        t = (np.arange(n_per_side) + 0.5) / n_per_side
        mid = p[None, :] + (q - p)[None, :] * t[:, None]
        dl = np.repeat(((q - p) / n_per_side)[None, :], n_per_side, axis=0)
        pts.append(np.c_[mid, np.full(n_per_side, z), np.c_[dl, np.zeros(n_per_side)]])
    return np.vstack(pts)


def neumann(a, b):
    ra, dla = a[:, :3], a[:, 3:]
    rb, dlb = b[:, :3], b[:, 3:]
    dist = np.linalg.norm(ra[:, None, :] - rb[None, :, :], axis=2)
    return MU0 / (4 * np.pi) * np.sum((dla @ dlb.T) / dist)


def sec_nest():
    print("== nest: aggressor 10x10 mm square loop; victim 3x3 mm, same plane (z = h above a perfect plane)")
    h = 0.1e-3
    agg = _square(0.0, 0.0, 10e-3, h)
    print("  victim centre (mm)   position             M free space (pH)   M over plane h=0.1 mm (pH)")
    for xc, lab in ((0.0, "nested, centred"), (3.0, "nested, 0.5 mm in"), (7.0, "outside, 0.5 mm gap"),
                    (10.0, "outside, 3.5 mm gap"), (15.0, "outside, 8.5 mm gap")):
        vic = _square(xc * 1e-3, 0.0, 3e-3, h, n_per_side=120)
        img = _square(xc * 1e-3, 0.0, 3e-3, -h, n_per_side=120)
        img[:, 3:] *= -1.0           # image current reversed (perfect plane at z = 0)
        Mf = neumann(agg, vic)
        Mp = Mf + neumann(agg, img)
        print(f"  {xc:8.1f}            {lab:20s} {Mf*1e12:12.2f}          {Mp*1e12:12.3f}")
    print("  (free space: nesting fixes the sign and the size of M, a topological class. Over a close plane each")
    print("   conductor closes through its image, so nesting fixes only the sign; distance to the nearest conductor sets the size)")


# ----------------------------------------------------------------------------- cm
def sec_cm():
    print("== cm: lumped extended graph, half-bridge switch node SW driven at 1 V against DC-; heatsink HS")
    print("   (22 pF to SW), chassis CH, LISN (25 ohm CM) to earth E bonded to CH. Board-to-chassis 30 pF.")
    C_sw_hs, C_hs_ch, C_n_ch = 22e-12, 30e-12, 30e-12
    L_strap, L_green = 10e-9, 100e-9
    nodes = ["N", "SW", "HS", "CH"]   # E is the reference (0 V); N is DC- (DC+ tied to N at HF by caps)

    def solve(f, option):
        w = 2 * np.pi * f
        Y = np.zeros((4, 4), complex)
        I = np.zeros(4, complex)

        def add(a, b, y):
            ia = nodes.index(a) if a in nodes else None
            ib = nodes.index(b) if b in nodes else None
            if ia is not None:
                Y[ia, ia] += y
            if ib is not None:
                Y[ib, ib] += y
            if ia is not None and ib is not None:
                Y[ia, ib] -= y
                Y[ib, ia] -= y
        add("N", "E", 1 / 25.0)                        # LISN common mode
        add("CH", "E", 1 / (1j * w * L_green))         # chassis safety bond
        add("SW", "HS", 1j * w * C_sw_hs)
        add("N", "CH", 1j * w * C_n_ch)
        if option == "HS floating":
            add("HS", "CH", 1j * w * C_hs_ch)
        elif option == "HS to chassis":
            add("HS", "CH", 1 / (1j * w * L_strap))
        elif option == "HS to DC-":
            add("HS", "CH", 1j * w * C_hs_ch)
            add("HS", "N", 1 / (1j * w * L_strap))
        elif option == "HS to DC- + 4.7 nF Y-cap N-CH":
            add("HS", "CH", 1j * w * C_hs_ch)
            add("HS", "N", 1 / (1j * w * L_strap))
            add("N", "CH", 1 / (1 / (1j * w * 4.7e-9) + 1j * w * 3e-9))
        # SW is a 1 V source relative to N: enforce with a stiff Norton source
        G = 1e6
        add("SW", "N", G)
        isw, inn = nodes.index("SW"), nodes.index("N")
        I[isw] += G * 1.0
        I[inn] -= G * 1.0
        V = np.linalg.solve(Y, I)
        Vn, Vsw, Vhs, Vch = V
        i_lisn = Vn / 25.0
        # cut-set law: board supernode {N, SW, (HS if galvanically on the board)} vs outside {CH, E}
        q = (C_n_ch * (Vn - Vch))
        if option in ("HS floating", "HS to chassis"):
            q += C_sw_hs * (Vsw - Vhs)       # displacement edge SW-HS crosses the board boundary
        else:
            q += C_hs_ch * (Vhs - Vch)       # HS is on the board side; its C to chassis crosses
        i_cut = 1j * w * q
        if option == "HS to DC- + 4.7 nF Y-cap N-CH":
            i_cut += (Vn - Vch) / (1 / (1j * w * 4.7e-9) + 1j * w * 3e-9)
        i_disp = 1j * w * C_sw_hs * (Vsw - Vhs)
        return i_lisn, i_cut, i_disp

    print("  option                           f (MHz)   |I_LISN| per V_sw (uA)   |share of SW-HS displacement|   cut-set check")
    for option in ("HS floating", "HS to chassis", "HS to DC-", "HS to DC- + 4.7 nF Y-cap N-CH"):
        for f in (3e6, 30e6, 100e6):
            il, ic, idisp = solve(f, option)
            print(f"  {option:32s} {f/1e6:6.0f}     {abs(il)*1e6:10.3f}              {abs(il)/abs(idisp):10.2e}"
                  f"                 {abs(il+ic)/max(abs(il),1e-30):.1e}")
    # Cycle census: fundamental cycles of a minimum-|Z| spanning tree at 30 MHz. The tree holds the
    # low-impedance edges, so each chord's cycle is the least-impedance way that chord's current closes.
    w30 = 2 * np.pi * 30e6
    zc = lambda c: 1 / (w30 * c)       # noqa: E731
    zl = lambda l: w30 * l             # noqa: E731
    base = [("N", "E", "LISN", 25.0), ("CH", "E", "green wire", zl(L_green)), ("SW", "HS", "C_sw-hs", zc(C_sw_hs)),
            ("N", "CH", "C_board-ch", zc(C_n_ch)), ("SW", "N", "switch", 0.0)]
    variants = {"HS to chassis": base + [("HS", "CH", "strap to chassis", zl(L_strap))],
                "HS to DC-": base + [("HS", "CH", "C_hs-ch", zc(C_hs_ch)), ("HS", "N", "strap to DC-", zl(L_strap))]}
    for name, edges in variants.items():
        verts = sorted({e[0] for e in edges} | {e[1] for e in edges})
        parent = {v: v for v in verts}

        def find(x):
            while parent[x] != x:
                x = parent[x]
            return x
        tree, chords = [], []
        for e in sorted(edges, key=lambda e: e[3]):
            ra, rb = find(e[0]), find(e[1])
            if ra != rb:
                parent[ra] = rb
                tree.append(e)
            else:
                chords.append(e)
        adj = {v: [] for v in verts}
        for e in tree:
            adj[e[0]].append((e[1], e))
            adj[e[1]].append((e[0], e))

        def path(a, b):
            prev = {a: None}
            stack = [a]
            while stack:
                x = stack.pop()
                for y, e in adj[x]:
                    if y not in prev:
                        prev[y] = (x, e)
                        stack.append(y)
            out = []
            x = b
            while prev[x] is not None:
                out.append(prev[x][1][2])
                x = prev[x][0]
            return out
        print(f"  cycle census, {name}: V = {len(verts)}, E = {len(edges)}, b1 = {len(edges) - len(verts) + 1}"
              " (fundamental cycles of the minimum-|Z| tree at 30 MHz)")
        for c in chords:
            cyc = [c[2]] + path(c[0], c[1])
            ext = any(k in ("LISN", "green wire") for k in cyc)
            src = "switch" in cyc
            print(f"    chord {c[2]:12s} ({c[3]:6.1f} ohm): {' + '.join(cyc)}   [{'external' if ext else 'internal'}"
                  f"{', driven' if src else ''}]")


SECTIONS = {"strip": sec_strip, "pour": sec_pour, "neck": sec_neck, "closure": sec_closure,
            "nest": sec_nest, "cm": sec_cm}

if __name__ == "__main__":
    which = sys.argv[1:] or ["all"]
    for name, fn in SECTIONS.items():
        if "all" in which or name in which:
            t0 = time.perf_counter()
            fn()
            print(f"  [{name}: {time.perf_counter()-t0:.1f} s]\n")
