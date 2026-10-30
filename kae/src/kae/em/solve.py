# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Quasi-static (magneto-quasi-static) solve of a mesh's conductor network: port impedances Z(f).

Unknowns are branch currents I and node potentials phi:

    Z I - D phi = 0          Z = R + jw L_p  (+ lumped parts)
       -D^T I   = -s         s: port current injections

L_p is the full partial-inductance matrix of all filaments: x-filaments couple to x, y to y,
vias to vias. On the raster it is block-Toeplitz per sublayer pair, so L_p I costs a few FFTs
(O(N log N), no dense matrix). The system is solved by GMRES, preconditioned by the same
saddle-point system with L_p replaced by its zero-offset blocks (each bar's coupling to the
bars stacked above and below it at the same position: the plane-pair coupling that carries most
of the energy), whose node Schur complement is sparse and factored once per frequency.

f = inf solves the inductive limit (R = 0): L = Im Z.
"""
from __future__ import annotations

import time

import numpy as np
import scipy.fft as sfft
import scipy.sparse as sp
import scipy.sparse.linalg as sla

from . import kernels as KN
from .mesh import MM, Network

import os

# threads of the FFTs and the compiled kernels: a shared host's other users come first (numba otherwise
# starts one thread per core); KAE_EM_THREADS overrides
WORKERS = int(os.environ.get("KAE_EM_THREADS", "8"))

try:
    import numba
    numba.set_num_threads(max(1, min(WORKERS, numba.config.NUMBA_NUM_THREADS)))

    @numba.njit(parallel=True, cache=True)
    def _kmul(Kh, X):
        """Y[c, r, m] = sum_s Kh[r, s, m] X[c, s, m] over the flattened spectrum m."""
        S, _, M = Kh.shape
        C = X.shape[0]
        Y = np.zeros((C, S, M), np.complex128)
        for m in numba.prange(M):
            for r in range(S):
                for c in range(C):
                    acc = 0j
                    for q in range(S):
                        acc += Kh[r, q, m] * X[c, q, m]
                    Y[c, r, m] = acc
        return Y
except ImportError:                                   # pragma: no cover
    def _kmul(Kh, X):
        return np.einsum("rsm,csm->crm", Kh, X)

# relative residual of the iterative solves: port quantities are variational (their error is second
# order), so 1e-5 gives them to ~3e-7 in about two thirds of the iterations 1e-8 takes
TOL = 1e-5
BATCH = 8               # right-hand sides solved together (memory: FFT arrays per batch)
PATCH = 2               # preconditioner blocks: all filaments of one orientation in PATCH x PATCH cells


class Operator:
    """Z = R + jw L_p as a matrix-free operator on a Network's branch currents."""

    _cache = {}

    def __init__(self, net: Network):
        self.net = net
        m = net.m
        self.p = m.pitch * MM
        self.ny, self.nx = m.ny, m.nx
        self.S = len(net.subs)
        self.Ny = sfft.next_fast_len(2 * m.ny - 1, real=True)
        self.Nx = sfft.next_fast_len(2 * m.nx - 1, real=True)
        # every sublayer, copper or not: price fields are read on empty layers too
        self.used = {o: np.arange(len(net.subs)) for o in ("x", "y")}
        self.Kh = {o: self._kernels(o) for o in ("x", "y")}
        self.Lv = self._via_matrix()

    def _kernels(self, o):
        """{(r, s): rfft2 of the circulant-embedded table} for the sublayers in use."""
        net, m = self.net, self.net.m
        used = list(self.used[o])
        out, centre = {}, {}
        for a, r in enumerate(used):
            for s in used[a:]:
                (z1, t1), (z2, t2) = net.subs[r], net.subs[s]
                key = (o, PATCH, self.p, m.ny, m.nx, round(z1, 12), round(t1, 12), round(z2, 12), round(t2, 12))
                if key not in Operator._cache:
                    if o == "x":
                        T = KN.xbar_kernel(self.p, z1, t1, z2, t2, m.ny, m.nx)
                    else:
                        T = KN.xbar_kernel(self.p, z1, t1, z2, t2, m.nx, m.ny).T
                    C = np.zeros((self.Ny, self.Nx))
                    # circulant embedding: offset d -> index d mod N
                    jy = np.arange(-(m.ny - 1), m.ny) % self.Ny
                    ix = np.arange(-(m.nx - 1), m.nx) % self.Nx
                    C[np.ix_(jy, ix)] = T
                    w_ = PATCH - 1
                    near = T[m.ny - 1 - w_:m.ny + w_, m.nx - 1 - w_:m.nx + w_] if m.ny > w_ and m.nx > w_ else None
                    Operator._cache[key] = (sfft.rfft2(C, workers=WORKERS), near)
                kh, c0 = Operator._cache[key]
                out[(r, s)] = kh
                centre[(r, s)] = centre[(s, r)] = c0      # (2 PATCH - 1)^2 table around offset 0
        self.centre = getattr(self, "centre", {})
        self.centre[o] = centre
        return out

    def _via_matrix(self):
        v = self.net.vseg
        n = len(v)
        if not n:
            return np.zeros((0, 0))
        x, y, z0, z1, r = v[:, 2], v[:, 3], v[:, 4], v[:, 5], v[:, 6]
        d = np.hypot(x[:, None] - x[None], y[:, None] - y[None])
        same = d < 1e-12
        d = np.where(same, np.maximum(r[:, None], r[None]), d)
        return KN.fil_mutual(z0[:, None], z1[:, None], z0[None], z1[None], d)

    def _index(self):
        """Per orientation: the used sublayers, and each filament's slot in the stacked grid."""
        if hasattr(self, "_ix"):
            return self._ix
        self._ix = {}
        for o in ("x", "y"):
            f = self.net.fil[o]
            used = list(self.used[o])
            pos = {s: k for k, s in enumerate(used)}
            slot = np.array([pos[s] for s in f["s"]], np.int64) if len(f["s"]) else np.zeros(0, np.int64)
            S = len(used)
            Kh = None
            if S:
                Kh = np.empty((S, S, self.Kh[o][(used[0], used[0])].size), complex)
                for a, r in enumerate(used):
                    for b, q in enumerate(used):
                        Kh[a, b] = self.Kh[o][(r, q) if (r, q) in self.Kh[o] else (q, r)].ravel()
            self._ix[o] = (S, slot, Kh)
        return self._ix

    def L_apply(self, I):
        """L_p I (the flux, V s; multiply by jw). I: (n_br,) or (n_br, P) for P right-hand sides at once."""
        net = self.net
        one = I.ndim == 1
        I2 = I[:, None] if one else I
        P = I2.shape[1]
        out = np.zeros_like(I2)
        for o, (S, slot, Kh) in self._index().items():
            f = net.fil[o]
            a0 = net.off[o]
            n = len(f["a"])
            if not n:
                continue
            seg = I2[a0:a0 + n]                                       # (n, P)
            G = np.zeros((P, 2, S, self.Ny, self.Nx))
            G[:, 0, slot, f["j"], f["i"]] = seg.real.T
            G[:, 1, slot, f["j"], f["i"]] = seg.imag.T
            G = G.reshape(2 * P, S, self.Ny, self.Nx)
            X = sfft.rfft2(G, workers=WORKERS)                       # (2P, S, Ny, Nx/2+1)
            sh = X.shape
            Y = _kmul(Kh, np.ascontiguousarray(X.reshape(2 * P, S, -1))).reshape(sh)
            Y = sfft.irfft2(Y, s=(self.Ny, self.Nx), workers=WORKERS).reshape(P, 2, S, self.Ny, self.Nx)
            out[a0:a0 + n] = (Y[:, 0, slot, f["j"], f["i"]] + 1j * Y[:, 1, slot, f["j"], f["i"]]).T
        nv = len(net.vseg)
        if nv:
            o = net.off["v"]
            out[o:o + nv] = self.Lv @ I2[o:o + nv]
        return out[:, 0] if one else out


class System:
    """The saddle-point system of one frequency, its preconditioner and its solves."""

    def __init__(self, op: Operator, f):
        net = self.net = op.net
        self.op = op
        self.inf = not np.isfinite(f)
        self.w = 1.0 if self.inf else 2 * np.pi * f
        R = np.zeros(net.n_br) if self.inf else net.R.copy()
        zl = np.array([q.z(self.w) - q.R if self.inf else q.z(self.w) for _, _, q in net.lump], complex)
        self.zdiag = R.astype(complex) + 1j * self.w * net.Lc
        self.zdiag[net.off["l"]:] = zl
        # scale the branch equations to O(1) (potentials come out times kap): residuals then
        # weigh currents and voltages alike
        lself = np.concatenate([np.full(len(net.fil[o]["a"]), op.centre[o][(int(net.fil[o]["s"][0]),) * 2][PATCH - 1, PATCH - 1])
                                for o in ("x", "y") if len(net.fil[o]["a"])] or [np.ones(1)])
        self.kap = 1.0 / float(np.median(np.abs(self.zdiag[:len(lself)] + 1j * self.w * lself)))
        # grounding: one node per connected component
        ground = {}
        for nm, plus, minus in net.m.ports:
            c = net.comp[net.term_node[minus]]
            ground.setdefault(c, net.term_node[minus])
        first = np.full(net.ncomp, -1)
        uc, fi = np.unique(net.comp, return_index=True)
        first[uc] = fi
        g = np.array([ground.get(c, first[c]) for c in range(net.ncomp)])
        free = np.ones(net.n_nodes, bool)
        free[g] = False
        self.free_idx = -np.ones(net.n_nodes, np.int64)
        self.free_idx[free] = np.arange(int(free.sum()))
        self.nfree = int(free.sum())
        a, b = net.br_a, net.br_b
        rows = np.concatenate([np.arange(net.n_br), np.arange(net.n_br)])
        cols = np.concatenate([self.free_idx[a], self.free_idx[b]])
        vals = np.concatenate([np.ones(net.n_br), -np.ones(net.n_br)])
        k = cols >= 0
        self.D = sp.csr_matrix((vals[k], (rows[k], cols[k])), shape=(net.n_br, self.nfree))
        self.DT = self.D.T.tocsr()
        self._precond()

    def _precond(self):
        """Zn: R + jw (zero-offset blocks of L_p) per bar stack; vias and parts diagonal."""
        net, op, w = self.net, self.op, self.w
        rows, cols, vals = [], [], []
        C0 = {}
        b = PATCH
        for o in ("x", "y"):
            C0[o] = np.zeros((len(net.subs), len(net.subs), 2 * b - 1, 2 * b - 1))
            for (r, q), c in op.centre[o].items():
                C0[o][r, q] = c
        for o in ("x", "y"):
            f = net.fil[o]
            a0 = net.off[o]
            n = len(f["a"])
            if not n:
                continue
            key = (f["j"] // b) * (net.m.nx // b + 1) + f["i"] // b
            order = np.argsort(key, kind="stable")
            ks = key[order]
            starts = np.r_[0, np.nonzero(np.diff(ks))[0] + 1]
            sizes = np.diff(np.r_[starts, n])
            for size in np.unique(sizes):
                grp = starts[sizes == size]
                idx = order[grp[:, None] + np.arange(size)[None]]          # (nb, size) filament indices
                ss, jj, ii = f["s"][idx], f["j"][idx], f["i"][idx]
                dj = jj[:, None, :] - jj[:, :, None] + b - 1
                di = ii[:, None, :] - ii[:, :, None] + b - 1
                B = 1j * w * C0[o][ss[:, :, None], ss[:, None, :], dj, di]
                B[:, np.arange(size), np.arange(size)] += self.zdiag[a0 + idx]
                Bi = np.linalg.inv(B * self.kap)
                gi = a0 + idx
                rows.append(np.repeat(gi, size, axis=1).ravel())
                cols.append(np.tile(gi, (1, size)).ravel())
                vals.append(Bi.ravel())
        for o in ("v", "l"):
            lo = net.off[o]
            hi = net.off["l"] if o == "v" else net.n_br
            if hi > lo:
                d = self.zdiag[lo:hi].copy()
                if o == "v":
                    d = d + 1j * w * np.diag(op.Lv)
                rows.append(np.arange(lo, hi)), cols.append(np.arange(lo, hi)), vals.append(1 / (self.kap * d))
        self.Zn_inv = sp.csr_matrix((np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))),
                                    shape=(net.n_br, net.n_br))
        Sn = (self.DT @ self.Zn_inv @ self.D).tocsc()
        t = time.time()
        # Sn is structurally symmetric: a symmetric ordering with diagonal pivots (threshold 0.1) fills
        # 2.9x less than COLAMD, factors 4-6x and solves ~2x faster at equal residuals
        self.lu = sla.splu(Sn, permc_spec="MMD_AT_PLUS_A", options=dict(SymmetricMode=True, DiagPivotThresh=0.1))
        self.t_factor = time.time() - t

    def matvec(self, u):
        nb = self.net.n_br
        I, phi = u[:nb], u[nb:]
        zd = self.zdiag if u.ndim == 1 else self.zdiag[:, None]
        top = self.kap * (zd * I + 1j * self.w * self.op.L_apply(I)) - self.D @ phi
        bot = -(self.DT @ I)
        return np.concatenate([top, bot])

    def psolve(self, r):
        nb = self.net.n_br
        r1, r2 = r[:nb], r[nb:]
        b = self.lu.solve(np.ascontiguousarray(-r2 - self.DT @ (self.Zn_inv @ r1)))
        a = self.Zn_inv @ (r1 + self.D @ b)
        return np.concatenate([a, b])

    def warm(self, prev):
        """An initial guess (n, P) from earlier solutions `prev` = list of (state) from `state_of`, mapped
        onto this network by position: filament currents by (orientation, sublayer, j, i), node potentials
        by (layer, j, i); anything new starts at zero."""
        net = self.net
        n = net.n_br + self.nfree
        X0 = np.zeros((n, len(prev)), complex)
        for q, st in enumerate(prev):
            if st is None:
                continue
            for o in ("x", "y"):
                f = net.fil[o]
                if not len(f["a"]):
                    continue
                d = st["fil"].get(o)
                if d is None:
                    continue
                arr = d
                ok = (f["j"] < arr.shape[1]) & (f["i"] < arr.shape[2])
                vals = np.zeros(len(f["a"]), complex)
                vals[ok] = arr[f["s"][ok], f["j"][ok], f["i"][ok]]
                X0[net.off[o]:net.off[o] + len(f["a"]), q] = vals
            pot = st["pot"]
            occ = net.node >= 0
            cells = np.nonzero(occ)
            nd = net.node[occ]
            k = self.free_idx[nd]
            m = (k >= 0) & (cells[1] < pot.shape[1]) & (cells[2] < pot.shape[2])
            X0[net.n_br + k[m], q] = pot[cells[0][m], cells[1][m], cells[2][m]] * self.kap
        return X0

    def state_of(self, x):
        """A solution as position-keyed arrays (for `warm` on a later, slightly different network)."""
        net, m = self.net, self.net.m
        fil = {}
        for o in ("x", "y"):
            f = net.fil[o]
            arr = np.zeros((len(net.subs), m.ny, m.nx), complex)
            if len(f["a"]):
                arr[f["s"], f["j"], f["i"]] = x[net.off[o]:net.off[o] + len(f["a"])]
            fil[o] = arr
        pot = np.zeros(m.lab.shape, complex)
        occ = net.node >= 0
        k = self.free_idx[net.node[occ]]
        vals = np.where(k >= 0, x[net.n_br + np.maximum(k, 0)], 0.0) / self.kap
        pot[occ] = vals
        return dict(fil=fil, pot=pot)

    def solve_many(self, S_, tol=1e-8, maxiter=1000, X0=None, E=None):
        """COCG on P right-hand sides in lockstep (columns of S_, (nfree, P)): every iteration shares one
        batched FFT pass and one factor solve. E (n_br, P): series EMFs (V) in the branches as well, the
        branch equation reading Z I - D phi = E. Returns (X (n, P), iterations per column)."""
        nb = self.net.n_br
        P = S_.shape[1]
        top = np.zeros((nb, P), complex) if E is None else self.kap * np.asarray(E, complex)
        rhs = np.concatenate([top, -np.asarray(S_, complex)])
        x = self.psolve(rhs)
        if X0 is not None:
            # a warm start: keep the earlier solution's divergence-free part; the preconditioner applied to
            # the residual of rhs fixes the constraint (projected CG stays feasible)
            x = X0 + self.psolve(rhs - self.matvec(X0))
        r = rhs - self.matvec(x)
        bn = np.linalg.norm(rhs, axis=0)
        bn[bn == 0] = 1.0
        act = np.linalg.norm(r, axis=0) > tol * bn
        its = np.zeros(P, int)
        if not act.any():
            return x, its
        z = self.psolve(r)
        p = z.copy()
        rz = np.einsum("ij,ij->j", r, z)
        for it in range(1, maxiter + 1):
            # every column steps together (no gathers); a converged column is frozen by a zero step
            q = self.matvec(p)
            pq = np.einsum("ij,ij->j", p, q)
            a = np.where(act, rz / np.where(act, pq, 1.0), 0.0)
            x += a * p
            r -= a * q
            its[act] = it
            act &= np.linalg.norm(r, axis=0) > tol * bn
            if not act.any():
                break
            z = self.psolve(r)
            rzn = np.einsum("ij,ij->j", r, z)
            beta = np.where(act, rzn / np.where(act, rz, 1.0), 0.0)
            p = z + beta * p
            rz = np.where(act, rzn, rz)
        return x, its

    def solve(self, s, tol=1e-8, maxiter=1000):
        """Preconditioned COCG (conjugate orthogonal CG) for the complex-symmetric saddle system
        (van der Vorst and Melissen 1990): CG's short recurrence with the unconjugated product
        x^T y. The preconditioner keeps the constraint block exact, so the iterates stay in the
        space of currents that satisfy KCL (projected CG). Returns (x, info, iterations)."""
        rhs = np.concatenate([np.zeros(self.net.n_br, complex), -np.asarray(s, complex)])
        x = self.psolve(rhs)
        r = rhs - self.matvec(x)
        bn = np.linalg.norm(rhs)
        if np.linalg.norm(r) <= tol * bn:
            return x, 0, 0                   # the preconditioner is exact here (e.g. DC)
        z = self.psolve(r)
        p = z.copy()
        rz = r @ z
        for it in range(1, maxiter + 1):
            q = self.matvec(p)
            a = rz / (p @ q)
            x += a * p
            r -= a * q
            if np.linalg.norm(r) <= tol * bn:
                return x, 0, it
            z = self.psolve(r)
            rz_new = r @ z
            p = z + (rz_new / rz) * p
            rz = rz_new
        return x, 1, maxiter

    def injection(self, plus, minus):
        s = np.zeros(self.nfree)
        for nd, v in ((self.net.term_node[plus], 1.0), (self.net.term_node[minus], -1.0)):
            k = self.free_idx[nd]
            if k >= 0:
                s[k] += v
        return s

    def potential(self, x, term):
        k = self.free_idx[self.net.term_node[term]]
        return 0.0 if k < 0 else x[self.net.n_br + k] / self.kap


def solve(mesh, freqs, tol=1e-8, maxiter=400):
    """Port impedance matrices of mesh.ports at each frequency (Hz; inf = inductive limit).
    Returns dict(freqs, Z [nf, P, P], R, L, iters, seconds, stats, currents)."""
    t0 = time.time()
    net = Network(mesh)
    for nm, plus, minus in mesh.ports:
        if net.comp[net.term_node[plus]] != net.comp[net.term_node[minus]]:
            raise ValueError(f"port {nm}: {plus} and {minus} are not connected (open loop)")
    op = Operator(net)
    t_setup = time.time() - t0
    P = len(mesh.ports)
    Z = np.zeros((len(freqs), P, P), complex)
    iters, info_all, t_fac, cur = [], [], [], {}
    for k, f in enumerate(freqs):
        sysm = System(op, f)
        t_fac.append(sysm.t_factor)
        for j, (nm, plus, minus) in enumerate(mesh.ports):
            x, info, it = sysm.solve(sysm.injection(plus, minus), tol=tol, maxiter=maxiter)
            iters.append(it)
            info_all.append(info)
            for i, (_, p2, m2) in enumerate(mesh.ports):
                Z[k, i, j] = sysm.potential(x, p2) - sysm.potential(x, m2)
            cur[(k, j)] = x[:net.n_br]
    w = np.array([1.0 if not np.isfinite(f) else (2 * np.pi * f or np.nan) for f in freqs])
    return dict(freqs=list(freqs), Z=Z, R=Z.real, L=Z.imag / w[:, None, None], iters=iters, info=info_all,
                seconds=round(time.time() - t0, 2), setup_s=round(t_setup, 2), factor_s=[round(x, 2) for x in t_fac],
                stats=net.stats(), network=net, currents=cur)


def potentials(mesh, injections, f, read=None, tol=TOL, net=None, op=None):
    """Terminal potentials (V) for currents injected at terminals ({terminal: A}, summing to zero on
    each connected island), at frequency f. A terminal on an island without injection reads nan:
    its potential is undefined (only differences within an island, or sums weighted by
    island-balanced patterns, are physical). Returns ({terminal: complex}, info)."""
    net = net or Network(mesh)
    op = op or Operator(net)
    sysm = System(op, f)
    bal = {}
    for t, cur in injections.items():
        c = net.comp[net.term_node[t]]
        bal[c] = bal.get(c, 0) + cur
    big = max((abs(c) for c in injections.values()), default=1.0) or 1.0
    open_ = [c for c, b in bal.items() if abs(b) > 1e-3 * big]       # an island the current cannot leave
    # a small leak (currents below 0.1% of the largest that reach an island of their own net, e.g. a
    # pad the window cut off): take it from the island's largest injection, so the island balances
    injections = dict(injections)
    for c, b in bal.items():
        if c not in open_ and b != 0:
            tmax = max((t for t in injections if net.comp[net.term_node[t]] == c), key=lambda t: abs(injections[t]))
            injections[tmax] -= b
    s = np.zeros(sysm.nfree)
    for t, cur in injections.items():
        k = sysm.free_idx[net.term_node[t]]
        if k >= 0:
            s = s.astype(complex)
            s[k] += cur
    x, info, it = sysm.solve(s, tol=tol)
    out = {}
    for t in (read or mesh.terminals):
        out[t] = sysm.potential(x, t)
    return out, dict(iters=it, info=info, net=net, op=op, unbalanced=len(open_), I=x[:net.n_br], x=x, sys=sysm,
                     open_terms=[t for t in injections if net.comp[net.term_node[t]] in open_])


def potentials_many(mesh, inj_list, f, read=None, tol=TOL, net=None, op=None, warm=None):
    """potentials() for several injection sets at once (one batched COCG). Returns a list of
    ({terminal: V}, info) in the order given; an unbalanced set returns (None, info)."""
    net = net or Network(mesh)
    op = op or Operator(net)
    sysm = System(op, f)
    cols, infos = [], []
    for injections in inj_list:
        bal = {}
        for t, cur in injections.items():
            c = net.comp[net.term_node[t]]
            bal[c] = bal.get(c, 0) + cur
        big = max((abs(c) for c in injections.values()), default=1.0) or 1.0
        open_ = [c for c, b in bal.items() if abs(b) > 1e-3 * big]
        inj = dict(injections)
        for c, b in bal.items():
            if c not in open_ and b != 0:
                tmax = max((t for t in inj if net.comp[net.term_node[t]] == c), key=lambda t: abs(inj[t]))
                inj[tmax] -= b
        s = np.zeros(sysm.nfree, complex)
        for t, cur in inj.items():
            k = sysm.free_idx[net.term_node[t]]
            if k >= 0:
                s[k] += cur
        cols.append(s)
        infos.append(dict(unbalanced=len(open_), open_terms=[t for t in injections if net.comp[net.term_node[t]] in open_]))
    # batches of BATCH right-hand sides share the factorization; memory grows with the batch (FFT arrays
    # of 2 x batch x sublayers grids)
    Xs, itss = [], []
    for k in range(0, len(cols), BATCH):
        X0 = None
        if warm is not None and any(w is not None for w in warm[k:k + BATCH]):
            X0 = sysm.warm(list(warm[k:k + BATCH]))
        Xk, ik = sysm.solve_many(np.stack(cols[k:k + BATCH], axis=1), tol=tol, X0=X0)
        Xs.append(Xk)
        itss.append(ik)
    X, its = np.concatenate(Xs, axis=1), np.concatenate(itss)
    out = []
    for q, info in enumerate(infos):
        x = X[:, q]
        info.update(iters=int(its[q]), net=net, op=op, sys=sysm, x=x, I=x[:net.n_br], state=sysm.state_of(x))
        if info["unbalanced"]:
            out.append((None, info))
            continue
        out.append(({t: sysm.potential(x, t) for t in (read or mesh.terminals)}, info))
    return out
