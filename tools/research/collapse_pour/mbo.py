# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Multiphase MBO threshold dynamics for pour partitions (venv Python: numpy/scipy).

Esedoglu-Otto (2015) scheme on a grid. Phases p = 0..P-1 with surface tensions
sigma[p, q]; every step convolves each indicator u_q with a kernel K, forms
psi_p = sum_q sigma[p, q] K*u_q and assigns each live cell to argmin_p psi_p - lam_p.
Volume constraints: lam_p of a constrained phase is chosen so that the phase gets
exactly its target number of cells (exact coordinate ascent on the dual: each update
is an order statistic of the margins). Unconstrained phases keep a fixed lam_p, i.e. a
reward per cell (the "copper reward" of the pour problem).

Cells outside the domain ("dead") belong to no phase and are neutral: the kernel sees
u = 0 there for every phase, which gives a 90 degree contact angle on the free edge.
`pinned` cells (pads of a pour net) are fixed to their phase; `allowed[p]` is False
where phase p may not go (clearance to foreign copper). With `connect[p]` the phase
keeps only the 4-connected components that touch its pinned cells; dropped cells are
re-assigned in the same step.

Kernels: isotropic Gaussian (Wulff shape = disc) and an "octagon" kernel: the sum of
four 1-D Gaussians along 0/45/90/135 degrees (lightly blurred across). Its surface
tension sigma_K(n) = 1/2 int |x.n| K(x) dx is proportional to sum_k |d_k . n|, the
support function of a zonotope = regular octagon with edges along 0/45/90/135 degrees
(Esedoglu-Jacobs-Zhang 2017 give the general sigma_K formula for positive kernels).
"""
import numpy as np
from scipy import ndimage as ndi

SQ2 = np.sqrt(2.0)


def k_gauss(u, s):
    return ndi.gaussian_filter(u, s, mode="constant", cval=0.0, truncate=3.5)


def _diag1d(u, s, anti=False, truncate=3.5):
    """1-D Gaussian (std s in cell lengths) along the (1,1) or (1,-1) diagonal."""
    step = SQ2
    R = int(np.ceil(truncate * s / step))
    k = np.arange(-R, R + 1)
    w = np.exp(-0.5 * (k * step / s) ** 2)
    w /= w.sum()
    H, W = u.shape
    pad = np.zeros((H + 2 * R, W + 2 * R), u.dtype)
    pad[R:R + H, R:R + W] = u
    out = np.zeros_like(u)
    for kk, ww in zip(k, w):
        dy, dx = kk, (-kk if anti else kk)
        out += ww * pad[R + dy:R + dy + H, R + dx:R + dx + W]
    return out


def k_octagon(u, s, blur=0.7):
    """Zonotope kernel: mean of 1-D Gaussians along 0, 90, 45, 135 degrees."""
    v = ndi.gaussian_filter(u, blur, mode="constant", truncate=3.0) if blur > 0 else u
    out = ndi.gaussian_filter1d(v, s, axis=1, mode="constant", truncate=3.5)
    out += ndi.gaussian_filter1d(v, s, axis=0, mode="constant", truncate=3.5)
    out += _diag1d(v, s)
    out += _diag1d(v, s, anti=True)
    return 0.25 * out


KERNELS = dict(iso=k_gauss, oct=k_octagon)


def solve_lambda(a, lam, cons, need, sweeps=60, tol=0.5):
    """Coordinate ascent: lam[p] for p in cons so that phase p wins need[p] cells.

    a: (P, N) scores (-inf = forbidden). Returns updated lam (copy)."""
    lam = lam.copy()
    P, N = a.shape
    for _ in range(sweeps if len(cons) else 0):
        worst = 0.0
        for p in cons:
            b = a + lam[:, None]
            b[p] = -np.inf
            m = b.max(0) - a[p]
            k = int(need[p])
            if k <= 0:
                lam[p] = -1e9
                continue
            k = min(k, N)
            part = np.partition(m, [k - 1, min(k, N - 1)])
            lo, hi = part[k - 1], part[min(k, N - 1)]
            if not np.isfinite(lo):
                lam[p] = 1e9
                continue
            new = lo + 1e-9 if (not np.isfinite(hi) or hi - lo < 2e-9) else 0.5 * (lo + hi)
            worst = max(worst, abs(new - lam[p]))
            lam[p] = new
        if worst < 1e-7:
            break
    lab = np.argmax(a + lam[:, None], 0)
    cnt = np.bincount(lab, minlength=P)
    return lam, cnt


class MBO:
    def __init__(self, alive, P, sigma=None, kernel="iso", allowed=None, pinned=None,
                 target=None, reward=None, connect=None, seed=0, normalize=True):
        self.alive = alive.astype(bool)
        self.P = P
        self.sigma = np.ones((P, P)) - np.eye(P) if sigma is None else np.asarray(sigma, float)
        self.kernel = KERNELS[kernel] if isinstance(kernel, str) else kernel
        self.allowed = np.ones((P,) + alive.shape, bool) if allowed is None else allowed
        self.pinned = -np.ones(alive.shape, int) if pinned is None else pinned
        self.target = np.full(P, np.nan) if target is None else np.asarray(target, float)
        self.reward = np.zeros(P) if reward is None else np.asarray(reward, float)
        self.connect = np.zeros(P, bool) if connect is None else np.asarray(connect, bool)
        self.lam = self.reward.copy()
        self.rng = np.random.default_rng(seed)
        self.free_mask = self.alive & (self.pinned < 0)
        self.idx = np.flatnonzero(self.free_mask)
        self.jitter = 1e-7 * self.rng.random((P, len(self.idx)))
        self.pin_count = np.array([(self.pinned == p).sum() for p in range(P)])
        self.normalize = normalize
        self._mass = {}

    def scores(self, lab, s):
        P = self.P
        conv = np.empty((P,) + lab.shape)
        for q in range(P):
            conv[q] = self.kernel((lab == q).astype(float), s)
        psi = np.tensordot(self.sigma, conv, axes=(1, 0))
        if self.normalize:  # Neumann-type: divide by the kernel mass on live cells
            if s not in self._mass:
                self._mass[s] = np.maximum(self.kernel(self.alive.astype(float), s), 1e-3)
            psi = psi / self._mass[s]
        return -psi

    def step(self, lab, s):
        sc = self.scores(lab, s)
        a = sc.reshape(self.P, -1)[:, self.idx] + self.jitter
        allow = self.allowed.reshape(self.P, -1)[:, self.idx]
        a[~allow] = -np.inf
        cons = [p for p in range(self.P) if np.isfinite(self.target[p])]
        need = np.where(np.isfinite(self.target), self.target - self.pin_count, 0)
        for rnd in range(4):
            self.lam, cnt = solve_lambda(a, self.lam, cons, need)
            win = np.argmax(a + self.lam[:, None], 0)
            new = lab.copy()
            new.reshape(-1)[self.idx] = win
            dropped = 0
            for p in np.flatnonzero(self.connect):
                m = new == p
                cc, n = ndi.label(m)
                ids = np.unique(cc[(self.pinned == p) & (cc > 0)])
                bad = m & ~np.isin(cc, ids)
                if bad.any():
                    sel = bad.reshape(-1)[self.idx]
                    a[p, sel] = -np.inf
                    dropped += int(sel.sum())
            if not dropped:
                break
        return new

    def run(self, lab0, s_sched, log=None):
        lab = lab0.copy()
        lab[~self.alive] = -1
        lab[self.pinned >= 0] = self.pinned[self.pinned >= 0]
        hist = []
        prev = None
        for it, s in enumerate(s_sched):
            lab = self.step(lab, s)
            ch = -1 if prev is None else int((lab != prev).sum())
            hist.append(ch)
            if log and (it % 10 == 0 or it == len(s_sched) - 1):
                log(f"  it {it:3d} s={s:.2f} changed={ch} lam={np.round(self.lam, 4)}")
            if ch == 0 and it > 5 and s == s_sched[-1]:
                break
            prev = lab
        self.hist = hist
        return lab


def schedule(s0, s1, n_anneal, n_final):
    """Kernel width schedule: geometric from s0 down to s1, then n_final steps at s1."""
    return list(np.geomspace(s0, s1, n_anneal)) + [s1] * n_final


def edge_length(lab, p, q, g=1.0):
    """Length (pixel-edge count * g) of the interface between phases p and q (4-neigh)."""
    h = ((lab[:, 1:] == p) & (lab[:, :-1] == q)) | ((lab[:, 1:] == q) & (lab[:, :-1] == p))
    v = ((lab[1:, :] == p) & (lab[:-1, :] == q)) | ((lab[1:, :] == q) & (lab[:-1, :] == p))
    return g * (h.sum() + v.sum())
