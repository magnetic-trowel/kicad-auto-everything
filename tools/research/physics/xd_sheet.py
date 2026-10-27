# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Finite-difference copper-sheet experiments for the cross-domain lessons (xd).

Solves the 2D Laplace equation on a square grid of copper cells (one node per
cell, conductance 1/Rs between edge-adjacent copper cells), optionally on two
layers joined by via conductances. All DC; the same equation governs plane-pair
spreading inductance below cavity resonance (replace Rs by mu0*d).

Experiments (each prints a short table):
  corner  - equivalent squares of a 90-degree corner in a strip (classic ~0.56)
  pour    - pour vs trace resistance between two via contacts; where the loss is
  slot    - extra resistance of a slit vs its stream-function difference (dpsi)
  vias    - current share of each via column in a via field (transfer length)

Run:  python tools/research/physics/xd_sheet.py [corner|pour|slot|vias|all]
Deterministic; each experiment takes seconds to about a minute on one CPU.
"""
import sys

import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as spla

RHO_CU = 1.72e-8  # ohm*m at 20 C
T_1OZ = 35e-6     # m
RS_1OZ = RHO_CU / T_1OZ  # ohm/sq, ~0.49 mOhm/sq


def solve(masks, rs, vias=(), fixed=()):
    """masks: list of 2D bool arrays (one per layer, same shape).
    rs: list of sheet resistances (ohm/sq) per layer.
    vias: iterable of (cells_bool_2d, conductance_S) joining layer 0 and 1 over
          those cells (conductance split evenly over the cells).
    fixed: iterable of (layer, cells_bool_2d, volts) Dirichlet terminals.
    Returns (V list per layer with nan off-copper, index map, solve info)."""
    ny, nx = masks[0].shape
    nl = len(masks)
    idx = -np.ones((nl, ny, nx), dtype=np.int64)
    n = 0
    for l in range(nl):
        k = int(masks[l].sum())
        idx[l][masks[l]] = np.arange(n, n + k)
        n += k
    rows, cols, vals = [], [], []

    def add_g(a, b, g):
        rows.extend([a, b, a, b]); cols.extend([a, b, b, a])
        vals.extend([g, g, -g, -g])

    for l in range(nl):
        g = 1.0 / rs[l]
        m = masks[l]
        h = m[:, :-1] & m[:, 1:]
        a = idx[l][:, :-1][h]; b = idx[l][:, 1:][h]
        rows.extend(np.r_[a, b, a, b]); cols.extend(np.r_[a, b, b, a])
        vals.extend(np.r_[np.full(a.size, g), np.full(a.size, g), np.full(a.size, -g), np.full(a.size, -g)])
        v = m[:-1, :] & m[1:, :]
        a = idx[l][:-1, :][v]; b = idx[l][1:, :][v]
        rows.extend(np.r_[a, b, a, b]); cols.extend(np.r_[a, b, b, a])
        vals.extend(np.r_[np.full(a.size, g), np.full(a.size, g), np.full(a.size, -g), np.full(a.size, -g)])
    for cells, gtot in vias:
        a = idx[0][cells]; b = idx[1][cells]
        ok = (a >= 0) & (b >= 0)
        gi = gtot / ok.sum()
        for i, j in zip(a[ok], b[ok]):
            add_g(i, j, gi)
    G = sp.csr_matrix((vals, (rows, cols)), shape=(n, n))
    vfix = np.full(n, np.nan)
    for l, cells, volts in fixed:
        vfix[idx[l][cells & masks[l]]] = volts
    isf = ~np.isnan(vfix)
    fr = np.where(~isf)[0]
    A = G[fr][:, fr].tocsc()
    b = -G[fr][:, np.where(isf)[0]] @ vfix[isf]
    x = vfix.copy()
    x[fr] = spla.spsolve(A, b)
    # current injected at fixed nodes = (G x) at those nodes
    inj = G @ x
    out = []
    for l in range(nl):
        Vl = np.full((ny, nx), np.nan)
        Vl[masks[l]] = x[idx[l][masks[l]]]
        out.append(Vl)
    return out, idx, inj, x, G


def terminal_current(idx, inj, layer, cells, mask):
    return inj[idx[layer][cells & mask]].sum()


def dissipation_map(V, mask, rs):
    """Power per cell (W) on one layer: sum of edge losses split to cells."""
    P = np.zeros_like(V)
    g = 1.0 / rs
    h = mask[:, :-1] & mask[:, 1:]
    dh = np.where(h, (V[:, :-1] - V[:, 1:]) ** 2 * g, 0.0)
    P[:, :-1] += dh / 2; P[:, 1:] += dh / 2
    v = mask[:-1, :] & mask[1:, :]
    dv = np.where(v, (V[:-1, :] - V[1:, :]) ** 2 * g, 0.0)
    P[:-1, :] += dv / 2; P[1:, :] += dv / 2
    return np.nan_to_num(P)


def disk(ny, nx, cy, cx, r):
    yy, xx = np.mgrid[0:ny, 0:nx]
    return (yy - cy) ** 2 + (xx - cx) ** 2 <= r * r


# --------------------------------------------------------------------------
def exp_corner():
    print("== corner: equivalent squares of a 90-degree corner (Rs=1)")
    for w in (20, 40):
        arm = 8 * w
        ny = nx = arm + w
        m = np.zeros((ny, nx), bool)
        m[:w, :] = True            # horizontal arm along the top
        m[:, nx - w:] = True       # vertical arm down the right side
        t1 = np.zeros_like(m); t1[:w, 0] = True
        t2 = np.zeros_like(m); t2[ny - 1, nx - w:] = True
        (V,), idx, inj, x, G = solve([m], [1.0], fixed=[(0, t1, 1.0), (0, t2, 0.0)])
        I = terminal_current(idx, inj, 0, t1, m)
        R = 1.0 / I
        # arms outside the corner square: (nx - w) and (ny - w) cells long, plus
        # the corner square itself; terminal nodes sit at cell centres, so the
        # straight-strip resistance of n cells between end centres is (n-1)/w.
        straight = ((nx - w) + (ny - w) - 1) / w
        print(f"  w={w:3d} cells: R={R:.4f} sq; arms={straight:.4f} sq; corner square counts as {R - straight:.3f} sq")
    print("  (the corner square counts as ~0.56 sq, i.e. LESS than its 1 sq centreline length)")


def exp_pour():
    print("== pour: two via contacts 20 mm apart, 1 oz copper (Rs=%.3f mOhm/sq), 0.1 mm grid" % (RS_1OZ * 1e3))
    h = 0.1e-3
    rv = 3  # contact radius in cells (0.3 mm land)
    rows = []
    for name, (W, L) in {"pour 40x40mm": (400, 400), "pour 25x40mm": (250, 400)}.items():
        m = np.ones((W, L), bool)
        cy = W // 2
        a = disk(W, L, cy, L // 2 - 100, rv); b = disk(W, L, cy, L // 2 + 100, rv)
        (V,), idx, inj, x, G = solve([m], [RS_1OZ], fixed=[(0, a, 1.0), (0, b, 0.0)])
        I = terminal_current(idx, inj, 0, a, m)
        R = 1.0 / I
        P = dissipation_map(V, m, RS_1OZ) / I ** 2  # normalised to 1 A
        yy, xx = np.mgrid[0:W, 0:L]
        dmin = np.minimum(np.hypot(yy - cy, xx - (L // 2 - 100)), np.hypot(yy - cy, xx - (L // 2 + 100))) * h * 1e3
        frac = [P[dmin <= r].sum() / P.sum() for r in (1.0, 2.0, 5.0)]
        rows.append((name, R, frac))
    # analytic infinite sheet: R = (Rs/pi) ln(d/r)
    Rinf = RS_1OZ / np.pi * np.log(20e-3 / 0.3e-3)
    for name, R, frac in rows:
        print(f"  {name}: R={R*1e3:.3f} mOhm; loss within 1/2/5 mm of the contacts: "
              f"{frac[0]*100:.0f}% / {frac[1]*100:.0f}% / {frac[2]*100:.0f}%")
    print(f"  infinite-sheet formula (Rs/pi) ln(d/r): {Rinf*1e3:.3f} mOhm")
    for wmm in (1, 2, 5, 10):
        print(f"  trace {wmm:2d} mm x 20 mm: {RS_1OZ*20/wmm*1e3:.3f} mOhm (centre-to-centre, no end effects)")
    # many vias at each end: 2x2 and a 1x4 row, pitch 1 mm
    W, L = 400, 400
    m = np.ones((W, L), bool); cy = W // 2
    for label, offs in {"1 via each end": [(0, 0)],
                        "2x2 block, 1 mm pitch": [(-5, -5), (-5, 5), (5, -5), (5, 5)],
                        "1x4 row across flow, 1 mm pitch": [(-15, 0), (-5, 0), (5, 0), (15, 0)],
                        "1x4 row along flow, 1 mm pitch": [(0, -15), (0, -5), (0, 5), (0, 15)]}.items():
        a = np.zeros_like(m); b = np.zeros_like(m)
        for dy, dx in offs:
            a |= disk(W, L, cy + dy, L // 2 - 100 + dx, rv)
            b |= disk(W, L, cy + dy, L // 2 + 100 - dx, rv)
        (V,), idx, inj, x, G = solve([m], [RS_1OZ], fixed=[(0, a, 1.0), (0, b, 0.0)])
        I = terminal_current(idx, inj, 0, a, m)
        print(f"  40x40 pour, {label}: R={1e3/I:.3f} mOhm (sheet only, via barrels ideal)")


def stream_function(V, mask, rs, h=1.0):
    """psi with Jx = dpsi/dy (sheet current, A per cell edge); integrate Jx down columns."""
    Jx = np.zeros_like(V)
    vx = mask[:, :-1] & mask[:, 1:]
    Jx[:, :-1] = np.where(vx, (V[:, :-1] - V[:, 1:]) / rs, 0.0)
    return np.cumsum(Jx, axis=0)


def exp_slot():
    print("== slot: strip 20 mm wide x 60 mm, uniform current; insulating slit (1 cell wide)")
    h = 0.1e-3
    W, L = 200, 600
    m0 = np.ones((W, L), bool)
    t1 = np.zeros_like(m0); t1[:, 0] = True
    t2 = np.zeros_like(m0); t2[:, -1] = True
    (V0,), idx, inj, x, G = solve([m0], [RS_1OZ], fixed=[(0, t1, 1.0), (0, t2, 0.0)])
    I0 = terminal_current(idx, inj, 0, t1, m0)
    R0 = 1 / I0
    psi = stream_function(V0, m0, RS_1OZ) / I0  # fraction of total current
    print(f"  base R = {R0*1e3:.3f} mOhm ({R0/RS_1OZ:.2f} sq)")
    print("  slit                         dpsi/I   dR/Rs (sq)  pi/4*(dpsi/I)^2  ")
    cases = []
    for a_mm in (2, 5, 10):
        n = int(a_mm / 0.1)
        cases.append((f"across flow, centre, {a_mm} mm", ("v", W // 2 - n // 2, W // 2 + n // 2, L // 2)))
    for a_mm in (2, 5):
        n = int(a_mm / 0.1)
        cases.append((f"across flow, from edge, {a_mm} mm", ("v", 0, n, L // 2)))
    cases.append(("along flow, centre, 10 mm", ("h", W // 2, L // 2 - 50, L // 2 + 50)))
    cases.append(("45 deg, centre, 10 mm", ("d", W // 2, L // 2, 71)))
    for name, spec in cases:
        m = m0.copy()
        if spec[0] == "v":
            _, y0, y1, xc = spec; m[y0:y1, xc] = False
            dpsi = abs(psi[y1 - 1, xc] - psi[max(y0 - 1, 0), xc]) if y0 > 0 else abs(psi[y1 - 1, xc])
        elif spec[0] == "h":
            _, yc, x0, x1 = spec; m[yc, x0:x1] = False
            dpsi = abs(psi[yc, x1] - psi[yc, x0])
        else:
            _, yc, xc, k = spec
            for i in range(-k // 2, k // 2):
                m[yc + i, xc + i] = False
                m[yc + i, xc + i + 1] = False  # keep it 4-connected-blocking
            dpsi = abs(psi[yc + k // 2, xc] - psi[yc - k // 2, xc])
        (V,), idx, inj, x, G = solve([m], [RS_1OZ], fixed=[(0, t1, 1.0), (0, t2, 0.0)])
        I = terminal_current(idx, inj, 0, t1, m)
        dR = (1 / I - R0) / RS_1OZ
        print(f"  {name:28s} {dpsi:6.3f}   {dR:8.4f}     {np.pi/4*dpsi**2:8.4f}")
    print("  (interior slit: dR ~ (pi/4) Rs (dpsi/I)^2; edge notch ~ half that of a slit twice as long)")


def exp_vias():
    print("== vias: current transfer between two overlapping 1 oz layers through a via field")
    h = 0.1e-3
    W, L = 40, 300                     # 4 mm wide, 30 mm long
    top = np.zeros((W, L), bool); top[:, :200] = True   # x in [0, 20) mm
    bot = np.zeros((W, L), bool); bot[:, 100:] = True   # x in [10, 30) mm
    t1 = np.zeros_like(top); t1[:, 0] = True
    t2 = np.zeros_like(top); t2[:, -1] = True
    for label, rvia in {"through via 1.6 mm, 0.3 mm drill, 25 um plating": RHO_CU * 1.6e-3 / (np.pi * 0.325e-3 * 25e-6),
                        "blind via 0.2 mm long (L1-L2)": RHO_CU * 0.2e-3 / (np.pi * 0.325e-3 * 25e-6)}.items():
        vias = []
        cols = list(range(105, 200, 10))   # 10 columns at 1 mm pitch in the overlap
        rowsv = [5, 15, 25, 35]            # 4 rows at 1 mm pitch
        for cx in cols:
            for cy in rowsv:
                c = np.zeros_like(top); c[cy - 1:cy + 2, cx - 1:cx + 2] = True
                vias.append((c, 1.0 / rvia))
        (Vt, Vb), idx, inj, x, G = solve([top, bot], [RS_1OZ, RS_1OZ], vias=vias,
                                          fixed=[(0, t1, 1.0), (1, t2, 0.0)])
        I = terminal_current(idx, inj, 0, t1, top)
        colI = []
        for cx in cols:
            s = 0.0
            for cy in rowsv:
                c = np.zeros_like(top); c[cy - 1:cy + 2, cx - 1:cx + 2] = True
                s += ((Vt[c] - Vb[c]) * (1.0 / rvia) / 9).sum()
            colI.append(s / I)
        lt = 1e-3 * np.sqrt(rvia / (2 * RS_1OZ))
        print(f"  {label}: R_via={rvia*1e3:.2f} mOhm, TLM transfer length L_T=p*sqrt(Rvia/(Rs1+Rs2))={lt*1e3:.2f} mm")
        print("   share of current per via column (entry -> exit): " + " ".join(f"{c*100:4.1f}%" for c in colI))
        print(f"   first+last column carry {100*(colI[0]+colI[-1]):.0f}% of the current; middle 6 columns {100*sum(colI[2:8]):.0f}%")
        # keep only the two end columns (8 vias) to show the inner 32 add little
        vias2 = [v for v, cx in zip(vias, [c for c in cols for _ in rowsv]) if cx in (cols[0], cols[-1])]
        (Vt2, Vb2), idx2, inj2, *_ = solve([top, bot], [RS_1OZ, RS_1OZ], vias=vias2,
                                            fixed=[(0, t1, 1.0), (1, t2, 0.0)])
        I2 = terminal_current(idx2, inj2, 0, t1, top)
        print(f"   R with all 40 vias: {1e3/I:.3f} mOhm; with only the 8 vias of the end columns: {1e3/I2:.3f} mOhm")


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    for name, fn in [("corner", exp_corner), ("pour", exp_pour), ("slot", exp_slot), ("vias", exp_vias)]:
        if which in (name, "all"):
            fn()
