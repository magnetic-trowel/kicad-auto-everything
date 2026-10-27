# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Red-team re-derivation of the cut law (lenses CT, SY, CD, VP) by a method none of them used.

(1) strip   A centred slit of length 2a across a strip of width W (insulating edges) is, by
            mirroring at the edges, a periodic row of collinear cracks of period W. The crack
            opening g(y) is expanded in sqrt(1 - s^2) U_2m(s), s = y/a (the exact edge behaviour),
            whose cosine transforms are closed form, a pi (2m+1) (-1)^m J_{2m+1}(ka)/(ka). A Galerkin
            projection of the zero-normal-current condition on the crack faces gives the
            coefficients; the extra resistance is dR/R_s = pi a^2 c_0 / W^2. Compared with
            (2/pi) ln sec(pi x / 2), x = 2a/W (CT, SY), and its small-cut limit (pi/4) x^2.
            Single-crack check: W -> infinity gives c_0 = 1 exactly.
(2) mesh    CD's 'leverage rho = 1/2 in a sheet, so deleting a strip costs exactly 2x its
            first-order price'. On an infinite lattice rho = 2/z (z = edges per node; Foster),
            so the factor 1/(1 - rho) is 2 on a square grid, 1.5 on a triangular grid and 3 on a
            hexagonal grid: a property of the discretisation, not of the sheet. Finite-lattice
            check by exact rank-1 removal; continuum statement: the cost of removing a small
            region is its polarization tensor (2 x area x energy density for a disc).

Run: OMP_NUM_THREADS=1 python tools/research/physics/rt_cut_law.py   (seconds)
"""
import math

import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as spla
from scipy.special import jv


def crack_row_dR(x, m_basis=10, n_terms=400000):
    """dR / R_s for a centred slit of relative length x = 2a/W in a strip of width W (set W = 1)."""
    W = 1.0
    a = x * W / 2
    n = np.arange(1, n_terms + 1)
    k = 2 * math.pi * n / W
    ka = k * a
    B = np.array([a * math.pi * (2 * m + 1) * (-1) ** m * jv(2 * m + 1, ka) / ka for m in range(m_basis)])
    # A_lm = (a/W) sum_n 2 k_n B_m(k_n) B_l(k_n); the tail falls as 1/n^2 (truncation checked in sec_strip)
    A = (a / W) * (2 * k * B) @ B.T
    rhs = np.zeros(m_basis)
    rhs[0] = a * math.pi / 2
    c = np.linalg.solve(A, rhs)
    return math.pi * a * a * c[0] / W ** 2


def sec_strip():
    print("== strip: Galerkin crack-row solution vs the ln sec law; dR in squares (R_s = 1)")
    print("   check W -> inf (x small): c_0 -> 1, i.e. dR -> (pi/4) x^2")
    print("     x      Galerkin    (2/pi) ln sec(pi x/2)   ratio    (pi/4) x^2   ratio   notch = 2x centred (mirror)")
    for x in (0.02, 0.1, 0.25, 0.5, 0.75, 0.9):
        g = crack_row_dR(x)
        ex = (2 / math.pi) * (-math.log(math.cos(math.pi * x / 2)))
        sm = math.pi / 4 * x * x
        print(f"   {x:5.2f}   {g:10.6f}   {ex:10.6f}              {g/ex:7.4f}   {sm:9.6f}   {g/sm:6.3f}"
              f"   {2*g:9.6f}")
    print("   convergence at x = 0.75 (basis size / terms):",
          ", ".join(f"{mb}/{nt}: {crack_row_dR(0.75, mb, nt):.6f}" for mb, nt in ((4, 100000), (8, 200000), (12, 400000))))


def lattice(kind, n):
    """Edges of an n x n patch of a square, triangular or hexagonal (honeycomb) lattice."""
    edges = []
    idx = lambda i, j: i * n + j  # noqa: E731
    if kind in ("square", "triangular"):
        for i in range(n):
            for j in range(n):
                if j + 1 < n:
                    edges.append((idx(i, j), idx(i, j + 1)))
                if i + 1 < n:
                    edges.append((idx(i, j), idx(i + 1, j)))
                if kind == "triangular" and i + 1 < n and j + 1 < n:
                    edges.append((idx(i, j), idx(i + 1, j + 1)))
        return n * n, edges
    # honeycomb as a brick-wall lattice: horizontal edges everywhere, vertical edges on alternate sites
    for i in range(n):
        for j in range(n):
            if j + 1 < n:
                edges.append((idx(i, j), idx(i, j + 1)))
            if i + 1 < n and (i + j) % 2 == 0:
                edges.append((idx(i, j), idx(i + 1, j)))
    return n * n, edges


def leverage_centre(kind, n=61):
    """Leverage rho = R_eff(edge) / R(edge) for unit resistors, edges near the patch centre."""
    nn, edges = lattice(kind, n)
    E = np.array(edges)
    m = len(E)
    B = sp.csr_matrix((np.r_[np.ones(m), -np.ones(m)], (np.r_[np.arange(m), np.arange(m)], np.r_[E[:, 0], E[:, 1]])),
                      shape=(m, nn))
    G = (B.T @ B).tocsc()
    keep = np.arange(1, nn)
    lu = spla.splu(G[keep][:, keep])
    c = (n // 2) * n + n // 2
    sel = [e for e in range(m) if c in (E[e, 0], E[e, 1])]
    rhos = []
    for e in sel:
        s = np.zeros(nn)
        s[E[e, 0]], s[E[e, 1]] = 1.0, -1.0
        v = np.zeros(nn)
        v[keep] = lu.solve(s[keep])
        rhos.append(v[E[e, 0]] - v[E[e, 1]])
    return np.array(rhos), 2 * (nn - 1) / m


def sec_mesh():
    print("== mesh: leverage rho of edges at the centre of a 61 x 61 patch; exact removal / first-order = 1/(1 - rho)")
    for kind in ("square", "triangular", "honeycomb"):
        rho, mean_rho = leverage_centre(kind)
        print(f"   {kind:10s}: rho at centre {np.round(rho, 3)} (Foster mean (n-1)/m = {mean_rho/2:.3f});"
              f" removal factor {1/(1-rho.mean()):.2f}x")
    print("   -> the 'exactly 2x' is the square grid's coordination (rho = 2/z), not a sheet property;")
    print("      the mesh-independent statement is the polarization tensor of the removed region")
    print("      (a disc costs 2 x area x R_s |J|^2; a slit of length l across the flow (pi/4) R_s (J l)^2).")


if __name__ == "__main__":
    sec_strip()
    print()
    sec_mesh()
