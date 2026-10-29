# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""A passive reduced-order model of a board's copper and parts, valid over the whole quasi-static range.

The field system of kae.em.solve (physical units),

    [ Z(w)  -D ] [ I   ]   [  0 ]      Z(w) = R + jw (L_p + L_c) + diag(z_l(w))  (lumped parts)
    [ -D^T   0 ] [ phi ] = [ -p ]

is complex symmetric; R, L_p, L_c are symmetric positive semidefinite and every lumped z_l(w) is
passive. Projected by congruence onto a real orthonormal basis V of snapshot solutions,

    A_r(w) = V_I^T (R + jw (L_p + L_c)) V_I + V_l^T diag(z_l(w)) V_l - G_D - G_D^T,  G_D = V_I^T D V_phi,

it has order m (tens to a few hundred), stays passive at every w, and costs O(m^3) per frequency.
Ports are injection vectors p (an aggressor's source, an observer's adjoint port): the model gives
their whole impedance matrix Z_kj(w) = p_k^T phi_j. With every port's own solutions in the basis each
Z_kj is variational (its error is the product of the two ports' errors); with only the sources'
solutions, transfers miss by 5-30 % (docs/topics/architecture/physics-frequency-coverage.md).

Snapshots: DC (exact there: the preconditioner is the operator), then greedily the frequency of a
log grid with the largest estimated error, until it is below `tol`. The estimate of Z_kj's error is
the dual-weighted residual with the dual error approximated by one preconditioner application,
|(M^-1 r_k)^T r_j| / kappa in the solver's scaled variables (the Galerkin error is exactly
-(1/kappa) e_k^T r_j).
"""
from __future__ import annotations

import time

import numpy as np

from . import solve as ES


class _Bare(ES.System):
    """A frequency's operator without the preconditioner's factor (for products only)."""

    def _precond(self):
        pass


class Reduced:
    """The reduced model of one Network for a set of ports.

    ports: list of {terminal: A} injections. Build with `build`; evaluate with `Z(f)`."""

    def __init__(self, op, ports, log=print):
        self.op, self.net = op, op.net
        self.log = log
        self.sys0 = _Bare(op, 1e6)              # grounding, D and free nodes do not depend on f
        self.nb = self.net.n_br
        self.P = np.stack([self._vec(p) for p in ports], 1)        # (nfree, nports)
        self.V = np.zeros((self.nb + self.sys0.nfree, 0))
        self.freqs = []
        self.lo = self.net.off["l"]

    def _vec(self, inj):
        s = np.zeros(self.sys0.nfree, complex)
        for t, a in inj.items():
            k = self.sys0.free_idx[self.net.term_node[t]]
            if k >= 0:
                s[k] += a
        return s

    # ------------------------------------------------------------------ basis
    def snapshot(self, f, tol=1e-8):
        """Solve every port at f and add the solutions to the basis. Returns the iterations."""
        sy = ES.System(self.op, f)
        X, its = sy.solve_many(self.P, tol=tol, maxiter=3000)
        X = np.concatenate([X[:self.nb], X[self.nb:] / sy.kap])
        self._extend(np.concatenate([X.real, X.imag], 1))
        self.freqs.append(f)
        return its

    def _extend(self, W):
        """Orthonormalize W against the basis (classical Gram-Schmidt, twice) and keep what is new."""
        for _ in range(2):
            W = W - self.V @ (self.V.T @ W)
        U, sv, _ = np.linalg.svd(W, full_matrices=False)
        scale = max(np.linalg.norm(W, axis=0).max(), 1e-300)
        keep = sv > 1e-9 * scale
        if keep.any():
            Q = U[:, keep]
            Q = Q - self.V @ (self.V.T @ Q)
            Q, _ = np.linalg.qr(Q)
            self.V = np.concatenate([self.V, Q], 1)
        self._project()

    def _project(self):
        nb, V = self.nb, self.V
        VI, Vp = V[:nb], V[nb:]
        net = self.net
        R = net.R.copy()
        R[self.lo:] = 0.0                       # lumped parts enter through z_l(w)
        self.G_R = VI.T @ (R[:, None] * VI)
        self.G_Lc = VI.T @ (net.Lc[:, None] * VI)
        LV = np.concatenate([self.op.L_apply(VI[:, k:k + ES.BATCH].astype(complex)).real
                             for k in range(0, VI.shape[1], ES.BATCH)], 1)
        self.G_L = VI.T @ LV
        self.G_D = VI.T @ (self.sys0.D @ Vp)
        self.Vl = VI[self.lo:]
        self.Pr = Vp.T @ self.P                 # (m, nports)

    # ------------------------------------------------------------------ evaluation
    def _zl(self, f):
        w = 2 * np.pi * f
        return np.array([q.z(w) for _, _, q in self.net.lump], complex)

    def A(self, f):
        w = 2 * np.pi * f
        return (self.G_R + 1j * w * (self.G_L + self.G_Lc) + self.Vl.T @ (self._zl(f)[:, None] * self.Vl)
                - self.G_D - self.G_D.T)

    def solve(self, f):
        """Reduced coefficients Y (m, nports) of every port's solution at f."""
        return np.linalg.solve(self.A(f), -self.Pr)

    def Z(self, f):
        """Port impedance matrix (nports, nports) at f (Hz): Z_kj = p_k^T phi_j."""
        return self.Pr.T @ self.solve(f)

    def Zs(self, freqs):
        return np.stack([self.Z(f) for f in freqs])

    def powers(self, f, cols=None):
        """Time-average powers (W) and magnetic energy (J) per 1 A peak of each port's current at f:
        dict(Y, Z, delivered (by the port's source, 1/2 Re Z_jj), copper (1/2 I^H R I in the copper),
        parts (n_lumped, ncols): each lumped part's 1/2 |I|^2 Re z, magnetic (1/4 I^H L I)). The first
        equals the sum of the next two in the full system (energy conservation); in the model the
        difference is a check of its currents."""
        cols = list(range(self.P.shape[1])) if cols is None else list(cols)
        Y = np.linalg.solve(self.A(f), -self.Pr[:, cols])
        Z = self.Pr.T @ Y
        quad = (lambda G: np.real(np.einsum("ij,ik,kj->j", Y.conj(), G, Y)))
        Il = self.Vl @ Y
        return dict(Y=Y, Z=Z, delivered=0.5 * np.real(Z[cols, range(len(cols))]), copper=0.5 * quad(self.G_R),
                    parts=0.5 * np.abs(Il) ** 2 * self._zl(f).real[:, None],
                    magnetic=0.25 * quad(self.G_L + self.G_Lc))

    def part_names(self):
        return [q.name for _, _, q in self.net.lump]

    def full(self, f, Y=None):
        """The full solution (n, nports) at f from the reduced coefficients: currents and potentials."""
        return self.V @ (self.solve(f) if Y is None else Y)

    # ------------------------------------------------------------------ error estimate
    def error(self, f, rows=None, cols=None):
        """Estimated |error| of Z_kj at f for ports k in rows, j in cols (all if None)."""
        rows = list(range(self.P.shape[1])) if rows is None else rows
        cols = list(range(self.P.shape[1])) if cols is None else cols
        need = sorted(set(rows) | set(cols))
        sy = ES.System(self.op, f)
        X = self.full(f)[:, need]
        Xs = np.concatenate([X[:self.nb], X[self.nb:] * sy.kap])
        rhs = np.concatenate([np.zeros((self.nb, len(need)), complex), -self.P[:, need]])
        r = rhs - sy.matvec(Xs)
        e = sy.psolve(r)
        at = {k: q for q, k in enumerate(need)}
        E = np.abs(e[:, [at[k] for k in rows]].T @ r[:, [at[j] for j in cols]]) / sy.kap
        return E

    # ------------------------------------------------------------------ greedy build
    def build(self, fmax, fmin=1e3, tol=1e-3, grid=24, max_snapshots=12, rows=None, cols=None, scale=None, f0=(0.0,)):
        """Snapshots at f0, then greedily where the estimated relative error of Z[rows][:, cols] over a log
        grid fmin..fmax is largest, until below tol. scale(f) -> (len(rows), len(cols)) array of the
        magnitudes errors are relative to (default |Z| of the model itself)."""
        t0 = time.time()
        G = np.logspace(np.log10(fmin), np.log10(fmax), grid)
        for f in f0:
            its = self.snapshot(f)
            self.log(f"reduce: snapshot {f / 1e6:.4g} MHz ({int(np.max(its))} iterations), basis {self.V.shape[1]}")
        rows = list(range(self.P.shape[1])) if rows is None else rows
        cols = list(range(self.P.shape[1])) if cols is None else cols
        self.history = []
        while True:
            worst, fw = 0.0, None
            for f in G:
                if any(abs(f - g) <= 1e-9 * max(f, 1.0) for g in self.freqs):
                    continue
                E = self.error(f, rows, cols)
                Zr = self.Z(f)[np.ix_(rows, cols)]
                S = np.abs(Zr) if scale is None else scale(f)
                rel = float(np.max(E / np.maximum(S, 1e-12 * np.max(np.abs(S)) + 1e-300)))
                if rel > worst:
                    worst, fw = rel, f
            self.history.append((self.V.shape[1], worst, fw))
            self.log(f"reduce: basis {self.V.shape[1]}, estimated worst relative error {worst:.1e}"
                     + (f" at {fw / 1e6:.4g} MHz" if fw else ""))
            if worst < tol or fw is None or len(self.freqs) >= max_snapshots:
                break
            its = self.snapshot(fw)
            self.log(f"reduce: snapshot {fw / 1e6:.4g} MHz ({int(np.max(its))} iterations)")
        self.seconds = time.time() - t0
        return self
