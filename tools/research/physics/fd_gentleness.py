# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""When is physics "gently applied"?  Radius of convergence of circuit + parasitics.

Round-3 foundations (docs/topics/physics/foundations.md, foundations-derivations.md).

Claim checked here: every first-order layout method (parasitic back-annotation, adjoint
edit prices, one-pass electro-thermal, lumped lines) is the first term of a Neumann series
sum_n G^n of a loop-gain operator G that couples the circuit to a hidden degree of freedom
(a resonant mode, a line's reflections, an edit's own redistribution, temperature).  The
series converges iff the spectral radius of G is < 1, i.e. iff no natural mode of the hidden
degree of freedom lies inside the expansion disc.  Three cases, each against a closed form:

  resonance  H(x) = 1/(1 - w^2 (L + x L) C + j w R C) at w0, x = dL/L.  Radius |x| < 1/Q.
  line       Two-port of a lossless line between equal resistive terminations Z,
             m = Z0/Z, theta = w l / v:  H = 1/(2 cos(theta) + j sin(theta) (m + 1/m)).
             Radius of the power series in theta = ln|(m+1)/(m-1)| (the decay rate of the
             line's natural modes); infinite at m = 1 (a pure delay has no modes).
  edit       A slit (k removed edges) across a W-wide strip of a unit-conductance square
             grid.  Exact cost (Woodbury) dR = v^T (I - M)^-1 v with M the edit's leverage
             matrix (diagonal = spanning-tree leverage rho); first order = v^T v.  The
             Neumann series converges at rate lambda_max(M); a full cut has lambda_max = 1.
             Compared with the strip law (2/pi) R_s ln sec(pi x / 2) of lenses CT and SY.
  copperq    The copper-only Q of a wide go/return pair (gap h, copper t) against the
             one-line form Q_cu = h / max(delta, delta^2/t): the R-L band (f_x, where
             delta^2/t = 2h) and "copper cannot damp" (Q = h/delta, lens TH) are one curve.
             Uses the exact two-slab surface-impedance model of th_damping_ledger.py.

Run:  python tools/research/physics/fd_gentleness.py      (numpy + scipy, ~10 s, one core)
"""
import math
import os

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")

import numpy as np  # noqa: E402
import scipy.sparse as sp  # noqa: E402
import scipy.sparse.linalg as spla  # noqa: E402


def taylor_coeffs(f, r0, n=64):
    """Taylor coefficients of an analytic f(z) about 0 from samples on |z| = r0 (Cauchy/FFT)."""
    z = r0 * np.exp(2j * np.pi * np.arange(n) / n)
    c = np.fft.fft(f(z)) / n
    return c / r0 ** np.arange(n)


def root_test_radius(c, lo=8, hi=40):
    """Radius estimate from |c_k|^(-1/k), fitted on k in [lo, hi) (log-linear)."""
    k = np.arange(lo, hi)
    a = np.log(np.abs(c[lo:hi]) + 1e-300)
    slope = np.polyfit(k, a, 1)[0]
    return math.exp(-slope)


def resonance():
    print("== resonance: H(x) at w0 for a parasitic dL = x L; radius predicted 1/Q")
    for Q in (5.0, 30.0, 170.0):
        # normalised: L = C = 1, w0 = 1, R = 1/Q;  H(x) = 1/(1 - (1 + x) + j/Q) = 1/(j/Q - x)
        def H(x, Q=Q):
            return 1.0 / (1j / Q - x)
        c = taylor_coeffs(H, 0.5 / Q)
        rad = root_test_radius(c)
        # first-order error at x = 0.3/Q, 0.9/Q and divergence of partial sums at 1.5/Q
        rows = []
        for xq in (0.3, 0.9, 1.5):
            x = xq / Q
            exact = H(x)
            first = c[0] + c[1] * x
            partial = [abs(np.sum(c[: N + 1] * x ** np.arange(N + 1)) - exact) / abs(exact) for N in (1, 5, 20)]
            rows.append(f"x*Q={xq:3.1f}: |first-order err| {abs(first-exact)/abs(exact):6.3f}, "
                        f"partial sums N=1/5/20 err {partial[0]:.2e}/{partial[1]:.2e}/{partial[2]:.2e}")
        print(f"  Q = {Q:5.0f}: root-test radius {rad:.5f} vs 1/Q = {1/Q:.5f}")
        for r in rows:
            print("     " + r)


def line():
    print("== line between equal terminations Z: series in theta, radius predicted ln|(m+1)/(m-1)|")
    for m in (1.1, 1.5, 3.0, 10.0, 0.1):
        def H(th, m=m):
            return 0.5 / (np.cos(th) + 0.5j * np.sin(th) * (m + 1 / m))  # normalised so H(0) = 1
        pred = math.log(abs((m + 1) / (m - 1)))
        c = taylor_coeffs(H, 0.5 * pred, n=128)
        rad = root_test_radius(c, 10, 60)
        print(f"  m = Z0/Z = {m:5.2f}: root-test radius {rad:6.3f} vs ln|(m+1)/(m-1)| = {pred:6.3f};"
              f" theta*max(m,1/m) at the radius = {pred*max(m,1/m):5.2f}")
    print("  m = 1: H = exp(-j theta) exactly (entire function: infinite radius, a pure delay)")
    th = np.linspace(0, 3 * math.pi, 7)
    H1 = 1.0 / (np.cos(th) + 0.5j * np.sin(th) * 2.0)   # m = 1, normalised so H(0) = 1
    print("     max |H/exp(-j theta) - 1| over theta in [0, 3 pi]:", f"{np.max(np.abs(H1/np.exp(-1j*th) - 1)):.1e}")


def strip_grid(W, L):
    """Unit-conductance square grid, W node rows x (L+1) columns, plus bus nodes S (left), T (right)."""
    def nid(i, j):
        return i * W + j
    n = (L + 1) * W
    S, T = n, n + 1
    edges = []
    for i in range(L + 1):
        for j in range(W):
            if i < L:
                edges.append((nid(i, j), nid(i + 1, j), 1.0))
            if j < W - 1:
                edges.append((nid(i, j), nid(i, j + 1), 1.0))
    gbus = 1e6
    for j in range(W):
        edges.append((S, nid(0, j), gbus))
        edges.append((T, nid(L, j), gbus))
    return edges, n + 2, S, T, nid


def laplacian(edges, nn, ground):
    rows, cols, vals = [], [], []
    for a, b, g in edges:
        rows += [a, b, a, b]
        cols += [a, b, b, a]
        vals += [g, g, -g, -g]
    K = sp.csr_matrix((vals, (rows, cols)), shape=(nn, nn))
    keep = np.array([k for k in range(nn) if k != ground])
    return K[keep][:, keep].tocsc(), keep


def edit():
    print("== finite edit: centred slit of k cells across a W = 24 strip (L = 72), unit R_s")
    W, L = 24, 72
    edges, nn, S, T, nid = strip_grid(W, L)
    K, keep = laplacian(edges, nn, T)
    pos = {v: k for k, v in enumerate(keep)}
    lu = spla.splu(K)
    s = np.zeros(K.shape[0])
    s[pos[S]] = 1.0
    phi = lu.solve(s)
    R0 = phi[pos[S]]
    print(f"  intact strip R = {R0:.4f} (L/W = {L/W:.4f}; bus contacts add {R0 - L/W:+.4f})")
    i0 = L // 2
    print("   k   x=k/W  lam_max(M)  rho_diag  exact dR  first-order  exact/first  strip law  "
          "N terms for 10%  sum of single exact")
    for k in (1, 2, 4, 8, 12, 16, 20, 22):
        j0 = (W - k) // 2
        cut = [(nid(i0, j), nid(i0 + 1, j)) for j in range(j0, j0 + k)]
        U = np.zeros((K.shape[0], k))
        for c, (a, b) in enumerate(cut):
            U[pos[a], c] = 1.0
            U[pos[b], c] = -1.0
        KU = lu.solve(U)
        M = U.T @ KU                         # g = 1, so M = U^T K^-1 U; diag = leverage rho
        v = U.T @ phi                        # voltage across each removed edge (per ampere)
        exact = float(v @ np.linalg.solve(np.eye(k) - M, v))
        first = float(v @ v)
        lam = float(np.max(np.linalg.eigvalsh(M)))
        # Neumann partial sums
        term, acc, nterm = v.copy(), 0.0, None
        for N in range(5000):
            acc += float(v @ term)
            if nterm is None and abs(acc - exact) <= 0.1 * exact:
                nterm = N + 1
                break
            term = M @ term
        single = float(np.sum(v ** 2 / (1 - np.diag(M))))
        x = k / W
        law = (2 / math.pi) * math.log(1 / math.cos(math.pi * x / 2))
        print(f"  {k:3d}  {x:5.3f}  {lam:9.4f}  {np.mean(np.diag(M)):7.3f}  {exact:8.4f}  {first:10.4f}  "
              f"{exact/first:10.2f}  {law:8.4f}  {nterm!s:>10}  {single:12.4f}")
    # direct re-solve check for one case
    k = 12
    j0 = (W - k) // 2
    cutset = {(nid(i0, j), nid(i0 + 1, j)) for j in range(j0, j0 + k)}
    edges2 = [e for e in edges if (e[0], e[1]) not in cutset]
    K2, keep2 = laplacian(edges2, nn, T)
    s2 = np.zeros(K2.shape[0])
    s2[list(keep2).index(S)] = 1.0
    R2 = spla.spsolve(K2, s2)[list(keep2).index(S)]
    print(f"  direct re-solve, k = 12: dR = {R2 - R0:.6f} (Woodbury above must match)")


def copperq():
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import th_damping_ledger as th
    print("== copper Q of a wide go/return pair: exact slab model vs h / max(delta, delta^2/t), 1 oz")
    mu0 = 4e-7 * math.pi
    t = 35e-6
    rs = 1.72e-8 / t
    for h in (0.1e-3, 1.6e-3):
        fx = rs / (2 * math.pi * mu0 * h)
        cells = []
        for f in (0.1 * fx, fx, 3.56e6, 100e6, 1e9):
            d = th.skin_depth(f)
            q = th.q_two_plates(f, h, t)
            cells.append(f"{f/1e6:7.3f} MHz {q:7.2f}/{h/max(d, d*d/t):7.2f}")
        print(f"  h = {h*1e3:3.1f} mm (f_x = {fx/1e3:4.0f} kHz), exact/one-line: " + "; ".join(cells))


if __name__ == "__main__":
    resonance()
    line()
    edit()
    copperq()
