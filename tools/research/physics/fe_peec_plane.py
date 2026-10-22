# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Small quasi-static PEEC solver for return current in a thin reference plane.

Used by docs/topics/physics/fields-si-emi.md and fields-emi-budget.md ([C] numbers).

Model: a trace (3 parallel filaments, width w) at height h above a zero-thickness
plane that is meshed as a graded rectilinear grid of x- and y-directed strips.
The trace current is fixed (1 A); the plane current is free subject to KCL
(injection at the two trace ends). At high frequency (inductive limit) the plane
current minimises magnetic energy, so we solve the quadratic programme with a
mesh-current (face) basis: (N^T L N) z = -N^T (L I_p + m).
Partial inductances: Neumann closed form for parallel filaments; flat strips use
the exact geometric mean distance (GMD) of their cross-section segments.

Outputs (all inductances scale linearly with geometry, so lengths are in units
of h and results in nH for h = 1 mm; multiply by h[mm] for a real stackup):
  1. validation: loop L' of an uninterrupted microstrip vs the air-microstrip
     closed form (Z0_air / c), and lateral return-current spread vs 2/pi*atan(x/h);
  2. slot crossing: extra loop inductance vs slot length and width, compared with
     the slotline estimate dL ~ mu0*l / (2*ln(4*l/g));
  3. "net plane inductance" between the two board ends (cable attachment
     points), i.e. the current-driven common-mode source, vs the LearnEMC MREMC
     closed form (mu0/pi)*h*l/W, for a centred trace and a trace near an edge.

Run (about 1-2 min, ~0.5 GB RAM):
    python tools/research/physics/fe_peec_plane.py
"""
import math

import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as spla

MU0_4PI_NH_PER_MM = 0.1  # mu0/(4 pi) = 1e-7 H/m = 0.1 nH/mm


def graded_lines(lo, hi, keys, max_pitch, growth=1.3):
    """Grid lines on [lo, hi]; keys = [(position, local_pitch)]; geometric grading.

    Key positions (and lo, hi) are always grid lines."""
    def pitch(x):
        return min([max_pitch] + [p + (growth - 1.0) * abs(x - k) for k, p in keys])
    forced = sorted(set([lo, hi] + [k for k, _ in keys if lo < k < hi]))
    lines = []
    for a, b in zip(forced[:-1], forced[1:]):
        x = a
        lines.append(a)
        while True:
            p = pitch(x)
            if x + p >= b - 0.3 * pitch(b):
                break
            x += p
            lines.append(x)
    lines.append(hi)
    return np.array(lines)


def Kfun(s, d):
    return s * np.arcsinh(s / d) - np.sqrt(s * s + d * d)


def mutual_parallel(a1, a2, b1, b2, d):
    """Neumann mutual of parallel filaments [a1,a2], [b1,b2] at distance d (nH, mm)."""
    return MU0_4PI_NH_PER_MM * (Kfun(a2 - b1, d) - Kfun(a1 - b1, d)
                                - Kfun(a2 - b2, d) + Kfun(a1 - b2, d))


def _G(s):
    s = np.asarray(s, dtype=float)
    out = np.zeros_like(s)
    nz = np.abs(s) > 1e-300
    out[nz] = 0.5 * s[nz] ** 2 * np.log(np.abs(s[nz])) - 0.75 * s[nz] ** 2
    return out


def gmd_segments(c1, w1, c2, w2):
    """Exact GMD of two collinear segments centred c1, c2 with widths w1, w2."""
    a1, a2 = c1 - w1 / 2, c1 + w1 / 2
    b1, b2 = c2 - w2 / 2, c2 + w2 / 2
    integ = _G(a2 - b1) - _G(a1 - b1) - _G(a2 - b2) + _G(a1 - b2)
    return np.exp(integ / (w1 * w2))


class Plane:
    def __init__(self, xs, ys, removed_x=None):
        """removed_x(xc, y) -> True removes the x-branch centred at xc on line y."""
        self.xs, self.ys = xs, ys
        nx, ny = len(xs), len(ys)
        self.nx, self.ny = nx, ny
        nid = lambda i, j: i * ny + j
        self.nid = nid
        wy = np.empty(ny)
        wy[1:-1] = (ys[2:] - ys[:-2]) / 2
        wy[0] = (ys[1] - ys[0]) / 2
        wy[-1] = (ys[-1] - ys[-2]) / 2
        wx = np.empty(nx)
        wx[1:-1] = (xs[2:] - xs[:-2]) / 2
        wx[0] = (xs[1] - xs[0]) / 2
        wx[-1] = (xs[-1] - xs[-2]) / 2
        # x-branches
        xb = []
        for i in range(nx - 1):
            for j in range(ny):
                xc = 0.5 * (xs[i] + xs[i + 1])
                if removed_x is not None and removed_x(xc, ys[j]):
                    continue
                xb.append((nid(i, j), nid(i + 1, j), xs[i], xs[i + 1], ys[j], wy[j], i, j))
        yb = []
        for i in range(nx):
            for j in range(ny - 1):
                yb.append((nid(i, j), nid(i, j + 1), ys[j], ys[j + 1], xs[i], wx[i], i, j))
        self.xb = np.array([b[:6] for b in xb], dtype=float)
        self.yb = np.array([b[:6] for b in yb], dtype=float)
        self.xb_ij = {(b[6], b[7]): k for k, b in enumerate(xb)}
        self.yb_ij = {(b[6], b[7]): k for k, b in enumerate(yb)}
        self.nxb, self.nyb = len(xb), len(yb)
        self.nb = self.nxb + self.nyb
        self.nn = nx * ny

    def incidence(self):
        rows, cols, vals = [], [], []
        for k, b in enumerate(self.xb):
            rows += [int(b[0]), int(b[1])]; cols += [k, k]; vals += [1.0, -1.0]
        for k, b in enumerate(self.yb):
            kk = self.nxb + k
            rows += [int(b[0]), int(b[1])]; cols += [kk, kk]; vals += [1.0, -1.0]
        return sp.csr_matrix((vals, (rows, cols)), shape=(self.nn, self.nb))

    def mesh_basis(self):
        """Faces = grid cells, merged across removed x-branches (union-find)."""
        nx, ny = self.nx, self.ny
        ncell = (nx - 1) * (ny - 1)
        parent = list(range(ncell))
        cid = lambda i, j: i * (ny - 1) + j

        def find(a):
            while parent[a] != a:
                parent[a] = parent[parent[a]]
                a = parent[a]
            return a
        for i in range(nx - 1):
            for j in range(1, ny - 1):
                if (i, j) not in self.xb_ij:  # removed x-branch between cell (i,j-1) and (i,j)
                    ra, rb = find(cid(i, j - 1)), find(cid(i, j))
                    if ra != rb:
                        parent[ra] = rb
        roots = {}
        rows, cols, vals = [], [], []
        for i in range(nx - 1):
            for j in range(ny - 1):
                r = find(cid(i, j))
                col = roots.setdefault(r, len(roots))
                # counter-clockwise: bottom +x, right +y, top -x, left -y
                for key, sgn, isx in (((i, j), 1.0, True), ((i + 1, j), 1.0, False),
                                      ((i, j + 1), -1.0, True), ((i, j), -1.0, False)):
                    if isx:
                        k = self.xb_ij.get(key)
                        if k is None:
                            continue
                    else:
                        k = self.nxb + self.yb_ij[key]
                    rows.append(k); cols.append(col); vals.append(sgn)
        N = sp.csr_matrix((vals, (rows, cols)), shape=(self.nb, len(roots)))
        N.sum_duplicates()
        N.eliminate_zeros()
        return N

    def L_block(self, br):
        """Dense partial-inductance matrix for one family of parallel strips."""
        a1, a2, c, w = br[:, 2], br[:, 3], br[:, 4], br[:, 5]
        dc = np.abs(c[:, None] - c[None, :])
        wm = np.maximum(w[:, None], w[None, :])
        d = np.maximum(dc, 1e-12)
        near = dc < 3.0 * wm
        ii, jj = np.nonzero(near)
        d[ii, jj] = gmd_segments(c[ii], w[ii], c[jj], w[jj])
        return mutual_parallel(a1[:, None], a2[:, None], a1[None, :], a2[None, :], d)


def solve_loop(plane, trace_y, h, w, x0, x1, nfil=3, want_potential=False):
    """Loop inductance (nH, mm units) for a trace from x0 to x1 at y=trace_y, height h."""
    A = plane.incidence()
    Lxx = plane.L_block(plane.xb)
    Lyy = plane.L_block(plane.yb)
    # trace filaments
    fy = trace_y + (np.arange(nfil) - (nfil - 1) / 2) * (w / nfil)
    fI = np.full(nfil, 1.0 / nfil)
    xb = plane.xb
    m = np.zeros(plane.nb)
    for y, I in zip(fy, fI):
        d = np.sqrt((xb[:, 4] - y) ** 2 + h * h)
        m[:plane.nxb] += I * mutual_parallel(xb[:, 2], xb[:, 3], x0, x1, d)
    Ltt = 0.0
    for a, Ia in zip(fy, fI):
        for b, Ib in zip(fy, fI):
            dd = abs(a - b) if a != b else 0.2231 * w / nfil
            Ltt += Ia * Ib * mutual_parallel(x0, x1, x0, x1, dd)
    # injection: return current enters the plane under x1 and leaves under x0
    def nearest(x, y):
        i = int(np.argmin(np.abs(plane.xs - x))); j = int(np.argmin(np.abs(plane.ys - y)))
        return plane.nid(i, j)
    s = np.zeros(plane.nn)
    s[nearest(x1, trace_y)] += 1.0
    s[nearest(x0, trace_y)] -= 1.0
    Lap = (A @ A.T).tocsc()
    keep = np.arange(1, plane.nn)
    phi = np.zeros(plane.nn)
    phi[keep] = spla.spsolve(Lap[keep][:, keep], s[keep])
    Ip = A.T @ phi
    N = plane.mesh_basis()
    assert abs(A @ N).max() < 1e-9, 'mesh basis is not divergence-free'
    Nx, Ny = N[:plane.nxb], N[plane.nxb:]
    LN = np.vstack([Lxx @ Nx.toarray(), Lyy @ Ny.toarray()])
    K = (N.T @ LN)
    LIp = np.concatenate([Lxx @ Ip[:plane.nxb], Lyy @ Ip[plane.nxb:]])
    rhs = -(N.T @ (LIp + m))
    z = np.linalg.solve(K, rhs)
    I = Ip + N @ z
    LI = np.concatenate([Lxx @ I[:plane.nxb], Lyy @ I[plane.nxb:]])
    W = 0.5 * I @ LI + I @ m + 0.5 * Ltt
    out = {"L": 2 * W, "I": I}
    if want_potential:
        # node potentials (per j*omega*1A, i.e. nH): A^T phi = L I + m  =>  (A A^T) phi = A (L I + m)
        phi = np.zeros(plane.nn)
        phi[keep] = spla.spsolve(Lap[keep][:, keep], (A @ (LI + m))[keep])
        out["phi"] = phi
    return out


def phi_at(plane, phi, x, y):
    i = int(np.argmin(np.abs(plane.xs - x))); j = int(np.argmin(np.abs(plane.ys - y)))
    return phi[plane.nid(i, j)]


def lateral_fraction(plane, I, x_probe, width):
    """Fraction of x-directed plane current within |y - yc| <= width at x_probe."""
    xb = plane.xb
    sel = (xb[:, 2] <= x_probe) & (xb[:, 3] > x_probe)
    tot = -I[:plane.nxb][sel].sum()
    yy = xb[sel, 4]
    return {k: -I[:plane.nxb][sel][np.abs(yy) <= k].sum() / tot for k in width}


def main():
    h, w = 1.0, 2.0  # units of h; w = 2h ~ 50 ohm in FR-4
    print("Units: h = 1 (results in nH for h = 1 mm; scale by h[mm]). Trace w = 2h.")

    # 1. validation: uninterrupted microstrip, two trace lengths -> L'
    Ls = {}
    for Lt in (20.0, 40.0):
        X, Y = Lt / 2 + 25, 40.0
        xs = graded_lines(-X, X, [(-Lt / 2, 0.5), (Lt / 2, 0.5), (0, 1.0)], 6.0)
        ys = graded_lines(-Y, Y, [(0.0, 0.33)], 6.0)
        pl = Plane(xs, ys)
        r = solve_loop(pl, 0.0, h, w, -Lt / 2, Lt / 2)
        Ls[Lt] = r["L"]
        if Lt == 40.0:
            fr = lateral_fraction(pl, r["I"], 0.0, (1.0, 3.0, 10.0))
            print("lateral return-current fraction at mid-trace (PEEC, w=2h):",
                  {k: round(v, 3) for k, v in fr.items()},
                  "| filament theory 2/pi*atan(k):",
                  {k: round(2 / math.pi * math.atan(k), 3) for k in (1, 3, 10)})
        print(f"  Lt={Lt:4.0f}h nodes={pl.nn} branches={pl.nb} L_loop={r['L']:.3f} nH")
    Lp = (Ls[40.0] - Ls[20.0]) / 20.0
    u = w / h
    z_air = 120 * math.pi / (u + 1.393 + 0.667 * math.log(u + 1.444))
    print(f"PEEC L' = {Lp:.3f} nH/mm  vs air-microstrip Z0/c = {z_air / 2.998e8 * 1e6:.3f} nH/mm "
          f"(Z0_air={z_air:.1f} ohm)")

    # 2. slot crossing at mid-trace, slot along y, width g
    Lt = 30.0
    print("\nSlot crossing (trace crosses the slot centre at right angles):")
    print(" l/h   g/h   dL_PEEC[nH per mm of h]  slotline est mu0*l/(2ln(4l/g))")
    base = {}
    for g in (0.5, 2.0):
        for l in (0.0, 10.0, 25.0, 50.0, 100.0):
            X, Y = Lt / 2 + 25, max(40.0, l / 2 + 30)
            xkeys = [(-Lt / 2, 0.5), (Lt / 2, 0.5), (-g / 2, min(0.5, g)), (g / 2, min(0.5, g))]
            ykeys = [(0.0, 0.33)] + ([(-l / 2, 0.5), (l / 2, 0.5)] if l > 0 else [])
            xs = graded_lines(-X, X, xkeys, 8.0)
            ys = graded_lines(-Y, Y, ykeys, 8.0)
            rem = (lambda xc, y, l=l, g=g: abs(xc) < g / 2 and abs(y) <= l / 2 + 1e-9) if l > 0 else None
            pl = Plane(xs, ys, rem)
            r = solve_loop(pl, 0.0, h, w, -Lt / 2, Lt / 2)
            if l == 0:
                base[g] = r["L"]
                continue
            dL = r["L"] - base[g]
            est = 2 * math.pi * MU0_4PI_NH_PER_MM * 2 * l / (2 * math.log(4 * l / g))
            print(f" {l:5.0f} {g:5.1f}   {dL:8.3f}               {est:8.3f}   (branches {pl.nb})")

    # 3. net plane inductance between board ends (current-driven CM source)
    Lt, Wb, Lb = 50.0, 250.0, 300.0  # e.g. h=0.2 mm: 10 mm trace on a 60 x 50 mm board
    print("\nNet plane inductance between the two board ends (cables attach at the ends),"
          " trace length 50h along x, board 300h x 250h:")
    print(" edge dist/h | V(end centres) | V(end corners, trace side) | V(far corners) | MREMC  [nH per mm of h]")
    for yt in (0.0, 75.0, 115.0, 122.0):
        xs = graded_lines(-Lb / 2, Lb / 2, [(-Lt / 2, 0.7), (Lt / 2, 0.7)], 14.0)
        ys = graded_lines(-Wb / 2, Wb / 2, [(yt, 0.4), (0.0, 3.0), (-Wb / 2, 2.0), (Wb / 2, 1.0)], 14.0)
        pl = Plane(xs, ys)
        r = solve_loop(pl, yt, h, w, -Lt / 2, Lt / 2, want_potential=True)
        ph = r["phi"]
        vc = abs(phi_at(pl, ph, -Lb / 2, 0) - phi_at(pl, ph, Lb / 2, 0))
        vn = abs(phi_at(pl, ph, -Lb / 2, Wb / 2) - phi_at(pl, ph, Lb / 2, Wb / 2))
        vf = abs(phi_at(pl, ph, -Lb / 2, -Wb / 2) - phi_at(pl, ph, Lb / 2, -Wb / 2))
        d1, d2 = Wb / 2 - yt, Wb / 2 + yt
        we, off = d1 + d2, abs(d1 - d2) / 2
        mremc = 4 * MU0_4PI_NH_PER_MM * h * Lt / we / math.sqrt(1 - 4 * (1 - 2 * h / we) * off ** 2 / we ** 2)
        print(f"   {min(d1, d2):6.1f}     {vc:8.4f}        {vn:8.4f}                  {vf:8.4f}       {mremc:8.4f}")

    # 4. the same board with a slot under the trace: cables on opposite ends vs same end
    print("\nSlot under the trace (slot at x=0 along y, g=2h), same 300h x 250h board, trace centred:")
    print(" slot l/h | V(left end centre - right end centre) | V(left end, two corners) [nH per mm of h]")
    for l in (0.0, 50.0, 100.0):
        g = 2.0
        xs = graded_lines(-Lb / 2, Lb / 2, [(-Lt / 2, 0.7), (Lt / 2, 0.7), (-g / 2, 1.0), (g / 2, 1.0)], 14.0)
        ykeys = [(0.0, 0.4), (-Wb / 2, 2.0), (Wb / 2, 2.0)] + ([(-l / 2, 1.0), (l / 2, 1.0)] if l else [])
        ys = graded_lines(-Wb / 2, Wb / 2, ykeys, 14.0)
        rem = (lambda xc, y, l=l, g=g: abs(xc) < g / 2 and abs(y) <= l / 2 + 1e-9) if l > 0 else None
        pl = Plane(xs, ys, rem)
        r = solve_loop(pl, 0.0, h, w, -Lt / 2, Lt / 2, want_potential=True)
        ph = r["phi"]
        vo = abs(phi_at(pl, ph, -Lb / 2, 0) - phi_at(pl, ph, Lb / 2, 0))
        vs = abs(phi_at(pl, ph, -Lb / 2, -Wb / 2) - phi_at(pl, ph, -Lb / 2, Wb / 2))
        print(f"   {l:5.0f}    {vo:8.4f}                                {vs:8.4f}")


if __name__ == "__main__":
    main()
