# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Exact physics maps (research_notes/transformations T2, experiment 5.2).

    ph = ExactPhys(world, board_path)       # a physics.Phys
    ph.exact_map(pi, ri, legal=None)        # (H, W): Phys.delta(pi, (x, y, ri)) at every cell
    ph.coarse_map(...)                      # = exact_map (drop-in for every coarse_map caller)

A map is built per structure the part touches, from the change of each component's
spend over the grid, then phi(u) and the structure's reduction applied pointwise, so it is
the same quantity as Terms.delta (the delta of sum_s c_s phi(u_s)):

  thermal     spectral Neumann (DCT-II basis) screened-Poisson solve with kae's G_s and
              lambda: the cosine expansion of the box is kae's adiabatic image lattice with
              all rings. Sources are Gaussian-smoothed (sigma) so the expansion converges;
              within R_c = 7 sigma of every source image the exact floored K0 replaces the
              smoothed kernel (a radial table), and the r = 0 self term takes kae's
              disk-averaged form. Fields: other sources (victim row / source row), one unit
              field per other target (moving source's column), the Green's diagonal (own
              images).
  loops       LoopComp, NearestLoopComp, DecapLoop (hops), PlanePairLoop: kae's own
              loop_core evaluated over the grid in one compiled loop (the hop-mode loop is not
              a few-distance closed form: plane-height rasters, detours, image mutuals);
              DecapLoop pour mode and the nearest-load choice vectorised in numpy.
  ESD, crystal  closed forms vectorised in numpy.
  coupling, cable CM  kae's coupling engine (eng_eval: Neumann segment integrals near,
              dipoles far) over the grid in one compiled loop, only the sub-terms the part
              touches.
  other       per-point Python fallback (c.value).

Non-thermal terms are evaluated on nodes every `stride_mm` (capped at `max_nodes`) and
bilinearly interpolated to the 0.1 mm grid; thermal fields are evaluated at the same nodes.
"""
import math
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
PNR = os.path.join(os.path.dirname(HERE), "pnr")
if PNR not in sys.path:
    sys.path.insert(0, PNR)

from physics import KAE_SRC, Phys  # noqa: E402
from world import ROTS  # noqa: E402

if KAE_SRC not in sys.path:
    sys.path.insert(0, KAE_SRC)

import numba  # noqa: E402
from kae.physics import jit as KJ  # noqa: E402
from kae.physics import fastloop as FL  # noqa: E402
from kae.physics import structures as ST  # noqa: E402
from kae.physics.kernels import lprime_hj  # noqa: E402

_K = KJ.nb()
_loop_core = _K.loop_core
_eng_eval = _K.eng_eval
INF = math.inf


# ---------------------------------------------------------------- compiled grid loops
@numba.njit(cache=True)
def loop_grid(X, Y, C, S, G, i, PXs, PYs, ti, tlx, tly, isbody, w, zb, bodyd, n, gnd, cos_min, clr, detour,
              thick, rvia, Hf, Hb, Nf, Nb, gmask, x0, y0, res, s0, s1, s2, s3, out):
    for p in range(PXs.shape[0]):
        X[i] = PXs[p]
        Y[i] = PYs[p]
        out[p] = _loop_core(X, Y, C, S, G, ti, tlx, tly, isbody, w, zb, bodyd, n, gnd, cos_min, clr, detour,
                            thick, rvia, Hf, Hb, Nf, Nb, gmask, x0, y0, res, s0, s1, s2, s3)


@numba.njit(cache=True)
def eng_grid(X, Y, C, S, G, i, PXs, PYs, LT_i, LT_xy, L_meta, L_f, NT_i, NT_xya, N_meta, N_w, Hf, Hb, rx0, ry0,
             rres, er, Lp, Lk, Cp, Ck, sel_l, sel_c, r0, r1, GP, Lc, Ls, PX, PY, PA, PC, Nc, Ns, stamp,
             gt3, gw3, gt6, gw6, sp, sd, vp, vd, out_l, out_c, ol, oc):
    for p in range(PXs.shape[0]):
        X[i] = PXs[p]
        Y[i] = PYs[p]
        _eng_eval(X, Y, C, S, G, LT_i, LT_xy, L_meta, L_f, NT_i, NT_xya, N_meta, N_w, Hf, Hb, rx0, ry0, rres, er,
                  Lp, Lk, Cp, Ck, sel_l, sel_c, r0, r1, GP, Lc, Ls, PX, PY, PA, PC, Nc, Ns, stamp + p,
                  gt3, gw3, gt6, gw6, sp, sd, vp, vd, ol, oc)
        for q in range(ol.shape[0]):
            out_l[p, q] = ol[q]
        for q in range(oc.shape[0]):
            out_c[p, q] = oc[q]


# ---------------------------------------------------------------- helpers
def phi_vec(u, barrier, usat):
    u = np.asarray(u, float)
    ps = usat + barrier * (usat - 1.0) ** 2
    dps = 1.0 + 2.0 * barrier * (usat - 1.0)
    out = np.where(u <= 1.0, u, u + barrier * (u - 1.0) ** 2)
    hi = u > usat
    if hi.any():
        out = np.where(hi, ps + dps * usat * np.log(np.maximum(u, 1e-300) / usat), out)
    return out


def reduce_vec(kind, vals, weights=None):
    if kind == 'sum':
        return sum(vals)
    if kind in ('parallel', 'wparallel'):
        ws = weights if kind == 'wparallel' else [1.0] * len(vals)
        inv = 0.0
        for v, wt in zip(vals, ws):
            v = np.asarray(v, float)
            inv = inv + np.where(v > 1e-12, wt / np.where(v > 1e-12, v, 1.0), 0.0)
        inv = np.asarray(inv, float)
        return np.where(inv > 0, 1.0 / np.where(inv > 0, inv, 1.0), INF)
    if kind == 'max':
        out = vals[0]
        for v in vals[1:]:
            out = np.maximum(out, v)
        return out
    return vals[0]


def k0_vec(x):
    x = np.asarray(x, float)
    out = np.empty_like(x)
    lo = x <= 2.0
    xl = x[lo]
    t2 = (xl / 3.75) ** 2
    i0 = 1.0 + t2 * (3.5156229 + t2 * (3.0899424 + t2 * (1.2067492 + t2 * (0.2659732 + t2 * (0.0360768
                                                                                            + t2 * 0.0045813)))))
    y = xl * xl / 4.0
    out[lo] = -np.log(xl / 2.0) * i0 + (-0.57721566 + y * (0.42278420 + y * (0.23069756 + y * (0.03488590 + y * (
        0.00262698 + y * (0.00010750 + y * 0.0000074))))))
    xh = x[~lo]
    y = 2.0 / xh
    out[~lo] = np.exp(-xh) / np.sqrt(xh) * (1.25331414 + y * (-0.07832358 + y * (0.02189568 + y * (
        -0.01062446 + y * (0.00587872 + y * (-0.00251540 + y * 0.00053208))))))
    return out


class Bilinear:
    """Nodes every s cells (and the last cell) on each axis; bilinear weights to every cell."""

    def __init__(self, n, s, lo=0, hi=None):
        hi = n - 1 if hi is None else hi
        nodes = np.arange(lo, hi + 1, s)
        if nodes[-1] != hi:
            nodes = np.append(nodes, hi)
        self.nodes = nodes
        cells = np.arange(lo, hi + 1)
        j = np.clip(np.searchsorted(nodes, cells, side='right') - 1, 0, max(0, len(nodes) - 2))
        if len(nodes) == 1:
            self.j0 = self.j1 = np.zeros(len(cells), int)
            self.t = np.zeros(len(cells))
        else:
            self.j0 = j
            self.j1 = j + 1
            self.t = (cells - nodes[j]) / (nodes[j + 1] - nodes[j])
        self.lo, self.hi = lo, hi


def interp2(V, by, bx):
    a = V[by.j0][:, bx.j0] * (1 - bx.t)[None, :] + V[by.j0][:, bx.j1] * bx.t[None, :]
    b = V[by.j1][:, bx.j0] * (1 - bx.t)[None, :] + V[by.j1][:, bx.j1] * bx.t[None, :]
    return a * (1 - by.t)[:, None] + b * by.t[:, None]


# ---------------------------------------------------------------- thermal
class ThermalMaps:
    """Spectral (DCT-II basis) screened-Poisson fields on kae's box with Neumann edges,
    near-field corrected to kae's floored K0 kernel."""

    def __init__(self, th, sigma=0.4, rc_sig=7.0, calibrate=True, coarse_mm=2.0):
        from scipy.integrate import quad
        self.calibrate = calibrate
        self.coarse_mm = coarse_mm
        from scipy.special import j0
        self.th = th
        x0, y0, Lx, Ly = th.box
        self.box = th.box
        lam, gs = th.lam, th.gs
        self.lam, self.gs = lam, gs
        self.norm = th.norm
        self.sig = sigma
        self.rc = rc_sig * sigma
        kmax = 7.0 / sigma
        M = int(kmax * Lx / math.pi) + 2
        N = int(kmax * Ly / math.pi) + 2
        self.kx = math.pi * np.arange(M) / Lx
        self.ky = math.pi * np.arange(N) / Ly
        ex = np.where(np.arange(M) == 0, 1.0, 2.0) * np.exp(-0.5 * (self.kx * sigma) ** 2)
        ey = np.where(np.arange(N) == 0, 1.0, 2.0) * np.exp(-0.5 * (self.ky * sigma) ** 2)
        K2 = self.kx[:, None] ** 2 + self.ky[None, :] ** 2
        self.W = ex[:, None] * ey[None, :] / (Lx * Ly * gs * (K2 + 1.0 / lam ** 2))
        # radial table of the smoothed free-space kernel, in units of K0: f(r) = int J0(kr) k e^{-k^2 s^2/2}/(k^2 + 1/lam^2) dk
        rr = np.linspace(0.0, max(self.rc, float(np.max(th.a)) if len(th.a) else 0.0) * 1.05 + 0.1, 900)
        il2 = 1.0 / lam ** 2
        fv = []
        for r in rr:
            g = (lambda k, r=r: j0(k * r) * k * math.exp(-0.5 * k * k * sigma * sigma) / (k * k + il2))
            v = 0.0
            edges = [0.0, 1.0 / lam, 5.0 / lam, 1.0 / sigma, 3.0 / sigma, 6.0 / sigma, 12.0 / sigma]
            edges = sorted(set(edges))
            for a, b in zip(edges[:-1], edges[1:]):
                v += quad(g, a, b, limit=200)[0]
            fv.append(v)
        self.rr = rr
        self.fr = np.array(fv)

    def f(self, r):
        return np.interp(r, self.rr, self.fr)

    def _cos(self, k, c, c0):
        return np.cos(np.outer(np.asarray(c, float) - c0, k))

    def _images(self, sx, sy):
        x0, y0, Lx, Ly = self.box
        ms = self.th.ms
        u, v = sx - x0, sy - y0
        ix = x0 + np.concatenate([2 * ms * Lx + u, 2 * ms * Lx - u])
        iy = y0 + np.concatenate([2 * ms * Ly + v, 2 * ms * Ly - v])
        return ix, iy

    def _near(self, xs, ys, sx, sy, a):
        """Near-field correction at grid (ys x xs) for a unit source at (sx, sy), floor a:
        sum over its images within R_c of norm (K0(max(r, a)/lam) - f(r))."""
        ix, iy = self._images(sx, sy)
        out = np.zeros((len(ys), len(xs)))
        rc = max(self.rc, a)
        for X in ix:
            dx = xs - X
            mx = np.abs(dx) < rc
            if not mx.any():
                continue
            for Y in iy:
                dy = ys - Y
                my = np.abs(dy) < rc
                if not my.any():
                    continue
                r = np.sqrt(dy[my][:, None] ** 2 + dx[mx][None, :] ** 2)
                c = np.where(r < rc, k0_vec(np.maximum(r, a) / self.lam) - self.f(r), 0.0)
                out[np.ix_(my, mx)] += self.norm * c
        return out

    def field(self, xs, ys, srcs):
        """sum_s P_s G(x, s) at grid (ys x xs) for srcs [(sx, sy, P, a)] (kae's G without the
        disk self term)."""
        x0, y0, Lx, Ly = self.box
        B = np.zeros(self.W.shape)
        for sx, sy, P, a in srcs:
            B += P * np.outer(np.cos(self.kx * (sx - x0)), np.cos(self.ky * (sy - y0)))
        Ex = self._cos(self.kx, xs, x0)
        Ey = self._cos(self.ky, ys, y0)
        F = Ey @ (self.W * B).T @ Ex.T
        for sx, sy, P, a in srcs:
            F += P * self._near(xs, ys, sx, sy, a)
        return F

    # kae's truncated lattice (rings `ms` + continuum tail), evaluated directly: the smooth
    # difference from the full lattice is added to the spectral fields on a coarse grid
    def engine_field(self, xs, ys, srcs):
        th = self.th
        out = np.zeros((len(ys), len(xs)))
        for sx, sy, P, a in srcs:
            ix, iy = self._images(sx, sy)
            acc = np.zeros_like(out)
            for X in ix:
                dx2 = (np.asarray(xs) - X) ** 2
                for Y in iy:
                    r = np.sqrt((np.asarray(ys) - Y)[:, None] ** 2 + dx2[None, :])
                    acc += k0_vec(np.maximum(r, a) / self.lam)
            out += P * (acc * self.norm + th.tail)
        return out

    def engine_diag(self, xs, ys, a, selfcorr):
        th = self.th
        x0, y0, Lx, Ly = self.box
        u = np.asarray(xs, float) - x0
        v = np.asarray(ys, float) - y0
        dxs = [d for m in th.ms for d in (-2 * m * Lx + 0.0 * u, 2 * u - 2 * m * Lx)]
        dys = [d for m in th.ms for d in (-2 * m * Ly + 0.0 * v, 2 * v - 2 * m * Ly)]
        acc = np.zeros((len(ys), len(xs)))
        for dx in dxs:
            for dy in dys:
                r = np.sqrt(dy[:, None] ** 2 + dx[None, :] ** 2)
                acc += k0_vec(np.maximum(r, a) / self.lam)
        return acc * self.norm + th.tail + selfcorr

    def _coarse(self, xs, ys):
        cx = np.linspace(xs[0], xs[-1], max(2, int((xs[-1] - xs[0]) / self.coarse_mm) + 2)) if len(xs) > 1 else xs
        cy = np.linspace(ys[0], ys[-1], max(2, int((ys[-1] - ys[0]) / self.coarse_mm) + 2)) if len(ys) > 1 else ys
        return cx, cy

    @staticmethod
    def _interp(C, cx, cy, xs, ys):
        if len(cx) > 1:
            C = np.stack([np.interp(xs, cx, row) for row in C])
        if len(cy) > 1:
            C = np.stack([np.interp(ys, cy, col) for col in C.T]).T
        return C

    def field_k(self, xs, ys, srcs):
        """field() calibrated to kae's lattice (smooth correction from a coarse grid)."""
        F = self.field(xs, ys, srcs)
        if not self.calibrate:
            return F
        cx, cy = self._coarse(xs, ys)
        C = self.engine_field(cx, cy, srcs) - self.field(cx, cy, srcs)
        return F + self._interp(C, cx, cy, xs, ys)

    def diag_k(self, xs, ys, a, selfcorr):
        D = self.diag(xs, ys, a, selfcorr)
        if not self.calibrate:
            return D
        cx, cy = self._coarse(xs, ys)
        C = self.engine_diag(cx, cy, a, selfcorr) - self.diag(cx, cy, a, selfcorr)
        return D + self._interp(C, cx, cy, xs, ys)

    def diag(self, xs, ys, a, selfcorr):
        """G(x, x) of a source of radius a moved to x (own images, kae's disk self term)."""
        x0, y0, Lx, Ly = self.box
        Ex2 = self._cos(self.kx, xs, x0) ** 2
        Ey2 = self._cos(self.ky, ys, y0) ** 2
        D = Ey2 @ self.W.T @ Ex2.T
        # r = 0 term: kae has K0(a/lam) + selfcorr; the spectral sum has f(0)
        D += self.norm * (k0_vec(np.array([a / self.lam]))[0] - self.fr[0]) + selfcorr
        # own images within R_c (near the edges)
        ms = self.th.ms
        rc = max(self.rc, a)
        u = np.asarray(xs, float) - x0
        v = np.asarray(ys, float) - y0
        dxs = []
        for m in ms:
            dxs.append(-2 * m * Lx + 0.0 * u)          # x - (x0 + 2mLx + u)
            dxs.append(2 * u - 2 * m * Lx)             # x - (x0 + 2mLx - u)
        dys = []
        for m in ms:
            dys.append(-2 * m * Ly + 0.0 * v)
            dys.append(2 * v - 2 * m * Ly)
        i0 = 2 * int(np.nonzero(ms == 0)[0][0])          # (m = 0, +) on each axis: the source itself
        for ax_, dx in enumerate(dxs):
            mx = np.abs(dx) < rc
            if not mx.any():
                continue
            for ay_, dy in enumerate(dys):
                if ax_ == i0 and ay_ == i0:
                    continue
                my = np.abs(dy) < rc
                if not my.any():
                    continue
                r = np.sqrt(dy[my][:, None] ** 2 + dx[mx][None, :] ** 2)
                c = np.where(r < rc, k0_vec(np.maximum(r, a) / self.lam) - self.f(r), 0.0)
                D[np.ix_(my, mx)] += self.norm * c
        return D


# ---------------------------------------------------------------- the map engine
class ExactPhys(Phys):
    def __init__(self, world, board_path, stride_mm=0.4, max_nodes=40000, sigma=0.4, rtol=0.01, atol=1e-3,
                 map_budget=None, max_stride_mm=1.2):
        super().__init__(world, board_path)
        self.stride_mm = stride_mm
        self.max_nodes = max_nodes
        self.tm = ThermalMaps(self.T.thermal, sigma=sigma) if self.T.thermal is not None else None
        self.calls = 0
        self.map_cpu = 0.0
        self.hits = 0
        self.capped = 0
        self.cpp = {}
        self.map_budget = map_budget
        self.max_stride_mm = max_stride_mm
        self.refined = 0
        self.rtol = rtol
        self.atol = atol
        self.cache = {}
        self.uidx = {pi: self.T.u2i[u] for pi, u in self.key.items() if u in self.T.u2i}

    # Phys.coarse_map callers (jc lift, anneal_phys, descent_phys) get the exact map
    def coarse_map(self, pi, ri, step_mm=0.8, legal=None):
        return self.exact_map(pi, ri, legal=legal)

    def _deps(self, i):
        T = self.T
        dep = set(T._nbr.get(i, ()))
        if i in T.th_parts:
            dep |= set(T.thermal.parts)
        dep.discard(i)
        return tuple(sorted(dep))

    def exact_map(self, pi, ri, legal=None, by_kind=False, budget=None):
        """budget (CPU s) overrides map_budget for this call."""
        t0 = time.process_time()
        mb = self.map_budget
        if budget is not None:
            self.map_budget = budget
        try:
            return self._exact_map(pi, ri, legal, by_kind)
        finally:
            self.map_budget = mb
            self.map_cpu += time.process_time() - t0

    def _exact_map(self, pi, ri, legal=None, by_kind=False):
        w = self.w
        if pi not in self.active:
            return np.zeros((w.H, w.W)) if not by_kind else {}
        T = self.T
        i = self.uidx[pi]
        T.total(self.poses)               # cached values in step with the poses
        st = T.st
        dep = self._deps(i)
        # region: bounding box of the legal cells
        if legal is not None:
            ys_, xs_ = np.nonzero(legal)
            if len(ys_) == 0:
                return np.zeros((w.H, w.W)) if not by_kind else {}
            bx0, bx1, by0, by1 = xs_.min(), xs_.max(), ys_.min(), ys_.max()
        else:
            bx0, bx1, by0, by1 = 0, w.W - 1, 0, w.H - 1
        s = max(1, int(round(self.stride_mm / w.g)))
        nx, ny = (bx1 - bx0) // s + 2, (by1 - by0) // s + 2
        key = (pi, ri, bx0, bx1, by0, by1, by_kind, tuple(st.get(j) for j in dep))
        hit = self.cache.get(key)
        if hit is not None:
            self.hits += 1
            return hit
        cap = self.max_nodes
        cpp = self.cpp.get(pi)
        if self.map_budget and cpp:
            cap = min(cap, 0.5 * self.map_budget / cpp)
        smax = max(1, int(round(self.max_stride_mm / w.g)))
        while nx * ny > cap and s < smax:
            s += 1
            nx, ny = (bx1 - bx0) // s + 2, (by1 - by0) // s + 2
        t_start = time.process_time()
        BX = Bilinear(w.W, s, bx0, bx1)
        BY = Bilinear(w.H, s, by0, by1)
        xs = w.x0 + BX.nodes * w.g
        ys = w.y0 + BY.nodes * w.g
        PX = np.repeat(xs[None, :], len(ys), 0).ravel()
        PY = np.repeat(ys[:, None], len(xs), 1).ravel()
        if pi not in self.cpp:
            # cost per point from a small probe, so the first map keeps to the budget too
            q = np.linspace(0, len(PX) - 1, min(48, len(PX))).astype(int)
            tq = time.process_time()
            self.node_maps(i, ROTS[ri], PX[q], PY[q], grid=None)
            self.cpp[pi] = max(time.process_time() - tq, 1e-5) / len(q)
            cap = min(self.max_nodes, 0.5 * self.map_budget / self.cpp[pi]) if self.map_budget else self.max_nodes
            if nx * ny > cap and s < smax:
                while nx * ny > cap and s < smax:
                    s += 1
                    nx, ny = (bx1 - bx0) // s + 2, (by1 - by0) // s + 2
                BX = Bilinear(w.W, s, bx0, bx1)
                BY = Bilinear(w.H, s, by0, by1)
                xs = w.x0 + BX.nodes * w.g
                ys = w.y0 + BY.nodes * w.g
                PX = np.repeat(xs[None, :], len(ys), 0).ravel()
                PY = np.repeat(ys[:, None], len(xs), 1).ravel()
            t_start = time.process_time()
        maps = self.node_maps(i, ROTS[ri], PX, PY, grid=None)
        maps = {k: v.reshape(len(ys), len(xs)) for k, v in maps.items()}
        self.calls += 1
        t_nodes = time.process_time() - t_start
        self.cpp[pi] = max(t_nodes, 1e-4) / len(PX)
        hh, ww = by1 - by0 + 1, bx1 - bx0 + 1
        full = {k: interp2(v, BY, BX) for k, v in maps.items()}
        if self.tm is not None and i in self.T.th_parts:
            # thermal at every cell: the spectral solve is separable matrix products
            fx = w.x0 + np.arange(bx0, bx1 + 1) * w.g
            fy = w.y0 + np.arange(by0, by1 + 1) * w.g
            full['thermal'] = self._thermal(i, ROTS[ri], fx, fy)
        # refinement: blocks whose corner values of the non-thermal terms spread by more than
        # rtol of their magnitude (+ atol) are evaluated exactly at every cell (the loop terms
        # jump where a hop's plane-height samples change, so interpolation cannot be trusted)
        nt = [k for k in maps if k != 'thermal']
        if s > 1 and nt and len(BY.nodes) > 1 and len(BX.nodes) > 1:
            Vn = sum(maps[k] for k in nt)
            # interpolation error estimate at each node: second differences / 8
            e = np.zeros_like(Vn)
            d2x = np.abs(Vn[:, :-2] - 2 * Vn[:, 1:-1] + Vn[:, 2:]) / 8.0
            d2y = np.abs(Vn[:-2, :] - 2 * Vn[1:-1, :] + Vn[2:, :]) / 8.0
            e[:, 1:-1] = np.maximum(e[:, 1:-1], d2x)
            e[1:-1, :] = np.maximum(e[1:-1, :], d2y)
            e = np.where(np.isfinite(e), e, np.inf)
            c = np.stack([e[:-1, :-1], e[1:, :-1], e[:-1, 1:], e[1:, 1:]]).max(0)
            v = np.stack([Vn[:-1, :-1], Vn[1:, :-1], Vn[:-1, 1:], Vn[1:, 1:]])
            mag = np.abs(v).min(0)
            ref = ~np.isfinite(c) | (c > self.rtol * mag + self.atol)
            if ref.any():
                cy = np.arange(hh)
                cx = np.arange(ww)
                rows = ref[np.minimum(BY.j0, ref.shape[0] - 1)]          # (hh, nbx)
                cm = rows[:, np.minimum(BX.j0, ref.shape[1] - 1)]          # (hh, ww)
                # cells on a block's right/bottom edge belong to the next block too
                if self.map_budget:
                    allowed = max(0.0, self.map_budget - (time.process_time() - t_start)) / self.cpp[pi]
                    if cm.sum() > allowed:
                        # refine the blocks with the largest error estimate first
                        bi, bj = np.nonzero(ref)
                        order = np.argsort(-c[bi, bj] / (np.abs(v).min(0)[bi, bj] + self.atol))
                        cells = ((BY.nodes[np.minimum(bi + 1, len(BY.nodes) - 1)] - BY.nodes[bi])
                                 * (BX.nodes[np.minimum(bj + 1, len(BX.nodes) - 1)] - BX.nodes[bj]))[order]
                        keep = order[np.cumsum(cells) <= allowed]
                        ref = np.zeros_like(ref)
                        ref[bi[keep], bj[keep]] = True
                        self.capped += 1
                        rows = ref[np.minimum(BY.j0, ref.shape[0] - 1)]
                        cm = rows[:, np.minimum(BX.j0, ref.shape[1] - 1)]
                ry, rx = np.nonzero(cm)
                if len(ry):
                    qx = w.x0 + (bx0 + rx) * w.g
                    qy = w.y0 + (by0 + ry) * w.g
                    ex = self.node_maps(i, ROTS[ri], qx, qy, grid=None)
                    self.refined += len(ry)
                    for k in nt:
                        full[k][ry, rx] = ex.get(k, 0.0)

        def place(V):
            out = np.zeros((w.H, w.W))
            out[by0:by1 + 1, bx0:bx1 + 1] = V
            return out
        if by_kind:
            res = {k: place(v) for k, v in full.items()}
        else:
            res = place(sum(full.values())) if full else np.zeros((w.H, w.W))
        if len(self.cache) > 4000:
            self.cache.clear()
        self.cache[key] = res
        return res

    # ------------------------------------------------------------ node maps
    def node_maps(self, i, rot, PX, PY, grid=None):
        """{kind: delta of the cost} at points (PX, PY) for part index i at rot; the thermal
        term only when `grid` = (xs, ys) gives the points as that grid (ys outer)."""
        T = self.T
        st = T.st
        side = 'F' if st.G[i] > 0 else 'B'
        saved = (st.get(i), st.V[i])
        st.set(i, st.X[i], st.Y[i], rot, side)        # rotation for the kernels' C, S
        out = {}
        try:
            # every sub-term part i touches, grouped by structure
            subs = {}
            for k, ci, si in T._psub.get(i, ()):
                subs.setdefault(k, {}).setdefault(ci, set()).add(si)
            eng_l, eng_c = [], []
            for k, cis in subs.items():
                for ci, sis in cis.items():
                    c = T.structs[k].comps[ci]
                    if T._nsub[k][ci] > 1:
                        for si in sis:
                            p = c.pid[si]
                            if p >= 0:
                                (eng_l if si == 0 else eng_c).append((p, k, ci))
            eng_vals = self._engine(i, PX, PY, eng_l, eng_c) if (eng_l or eng_c) else {}
            for k, cis in subs.items():
                s_ = T.structs[k]
                vals = list(T._cv[k])
                for ci, sis in cis.items():
                    c = s_.comps[ci]
                    if T._nsub[k][ci] > 1:
                        sub = list(T._sub[k][ci])
                        v = 0.0
                        for si in (0, 1):
                            if (k, ci, si) in eng_vals:
                                v = v + eng_vals[(k, ci, si)]
                            elif si in sis and c.pid[si] < 0:
                                v = v + 0.0
                            else:
                                v = v + sub[si]
                        vals[ci] = v
                    else:
                        vals[ci] = self._comp(c, i, PX, PY)
                v = reduce_vec(s_.reduce, vals, s_.info.get('weights'))
                u = v / s_.alloc.value if s_.alloc.value > 0 else 0.0 * v
                cf = s_.conf if T.knobs.use_confidence else 1.0
                d = cf * phi_vec(u, T.knobs.barrier, T.knobs.u_sat) - T._scost[k]
                out[s_.kind] = out.get(s_.kind, 0.0) + d
        finally:
            st.set(i, *saved[0])
            st.V[i] = saved[1]
        if self.tm is not None and i in T.th_parts and grid is not None:
            out['thermal'] = self._thermal(i, rot, grid[0], grid[1]).ravel()
        return {k: np.array(np.broadcast_to(np.asarray(v, float), PX.shape)) for k, v in out.items()}

    def _arrays(self, i):
        st = self.T.st
        return (st.Xa.copy(), st.Ya.copy(), st.Ca.copy(), st.Sa.copy(), st.Ga.copy())

    def _txy(self, t, i, PX, PY):
        """Terminal position over the grid (moving part i) or a scalar."""
        st = self.T.st
        j = t.i
        c, s, g = st.C[j], st.S[j], st.G[j]
        ly = t.ly * g
        if j == i:
            return PX + t.lx * c + ly * s, PY - t.lx * s + ly * c
        x, y = ST.txy(st, t)
        return np.full(PX.shape, x), np.full(PY.shape, y)

    def _loop(self, lc, i, PX, PY, idx=None):
        bv = lc.bv
        x0, y0, res, Hf, Nf = bv._hraster[1]
        _, _, _, Hb, Nb = bv._hraster[-1]
        X, Y, C, S, G = self._arrays(i)
        if i not in lc.parts:
            return np.full(PX.shape, lc.value(self.T.st))
        if idx is not None:
            PX, PY = PX[idx], PY[idx]
        out = np.empty(PX.shape[0])
        n = lc.n
        scr = tuple(np.zeros(max(n, 1)) for _ in range(4))
        loop_grid(X, Y, C, S, G, i, np.ascontiguousarray(PX, float), np.ascontiguousarray(PY, float), lc.a_ti,
                  lc.a_lx, lc.a_ly, lc.a_body, lc.a_w, lc.a_zb, lc.a_bd, n, lc.g, lc.cos_min, bv.clearance,
                  lc.detour, bv.thickness, lc.rvia, Hf, Hb, Nf, Nb, bv.gmask(lc.gnd_nets), x0, y0, res, *scr, out)
        return out

    def _zone_piece(self, bv, layer, x, y):
        L, _ = bv.zone_labels(layer)
        if L is None:
            return np.full(x.shape, -1)
        x0, y0, res, nx, ny = bv.cover_grid
        ii = np.floor((x - x0) / res + 0.5).astype(int)
        jj = np.floor((y - y0) / res + 0.5).astype(int)
        ok = (ii >= 0) & (jj >= 0) & (ii < nx) & (jj < ny)
        out = np.full(x.shape, -1)
        out[ok] = L[jj[ok], ii[ok]]
        return out

    def _h_ref(self, bv, side, x, y):
        x0, y0, res, H, _ = bv._hraster[1 if side > 0 else -1]
        ii = np.floor((x - x0) / res + 0.5).astype(int)
        jj = np.floor((y - y0) / res + 0.5).astype(int)
        ny, nx = H.shape
        ok = (ii >= 0) & (jj >= 0) & (ii < nx) & (jj < ny)
        out = np.full(x.shape, INF)
        out[ok] = H[jj[ok], ii[ok]]
        return out

    def _comp(self, c, i, PX, PY):
        st = self.T.st
        if isinstance(c, ST.LoopComp):
            return self._loop(c, i, PX, PY)
        if isinstance(c, ST.NearestLoopComp):
            x, y = self._txy(c.tr, i, PX, PY)
            best = np.zeros(PX.shape, int)
            bd = np.full(PX.shape, INF)
            for k, lp in enumerate(c.loops):
                px, py = self._txy(lp.T[0], i, PX, PY)
                d = (px - x) ** 2 + (py - y) ** 2
                better = d < bd
                best[better] = k
                bd[better] = d[better]
            out = np.empty(PX.shape)
            for k, lp in enumerate(c.loops):
                idx = np.nonzero(best == k)[0]
                if len(idx):
                    out[idx] = self._loop(lp, i, PX, PY, idx) if i in lp.parts else lp.value(st)
            return out
        if isinstance(c, ST.DecapLoop):
            out = np.full(PX.shape, np.nan)
            if c.pairs:
                bv = c.bv
                pi_ = self._txy(c.tp, i, PX, PY)
                pr = self._txy(c.tr, i, PX, PY)
                pc = self._txy(c.tc, i, PX, PY)
                pg = self._txy(c.tg, i, PX, PY)
                todo = np.ones(PX.shape, bool)
                for lr, lg, d in c.pairs:
                    a = self._zone_piece(bv, lr, *pi_)
                    lab_r = bv.zone_labels(lr)[1]
                    ok = (a >= 0) & (a == self._zone_piece(bv, lr, *pr))
                    if lab_r is not None:
                        ok &= np.array([lab_r[q] == c.rail if q >= 0 else False for q in a])
                    else:
                        ok &= False
                    b = self._zone_piece(bv, lg, *pc)
                    lab_g = bv.zone_labels(lg)[1]
                    ok &= (b >= 0) & (b == self._zone_piece(bv, lg, *pg))
                    if lab_g is not None:
                        ok &= np.array([lab_g[q] in c.gnd if q >= 0 else False for q in b])
                    else:
                        ok &= False
                    ok &= todo
                    if ok.any():
                        sc = st.G[c.tr.i]
                        si = st.G[c.tp.i]
                        hc = min(c._depth(sc, lr), c._depth(sc, lg))
                        hi = min(c._depth(si, lr), c._depth(si, lg))
                        D = np.maximum(np.hypot(pi_[0] - pr[0], pi_[1] - pr[1]), c.r)
                        out[ok] = (c.mc(hc) + c.mi(hi) + 0.2 * d * np.log(D * D / (c.r * c.r)))[ok]
                        todo &= ~ok
            rest = np.nonzero(np.isnan(out))[0]
            if len(rest):
                out[rest] = self._loop(c.loop, i, PX, PY, rest)
            return out
        if isinstance(c, ST.EsdComp):
            ax, ay = self._txy(c.tc, i, PX, PY)
            px, py = self._txy(c.tp, i, PX, PY)
            h = self._h_ref(c.bv, st.G[c.tp.i], px, py)
            hh = np.where(h == INF, c.bv.thickness, h)
            lp = np.empty(PX.shape)
            lv = np.empty(PX.shape)
            for u in np.unique(hh):
                m = hh == u
                cc = c._hc.get(u)
                if cc is None:
                    cc = (lprime_hj(c.w, u), FL.m_self(u, 0.15) + FL._collinear(u, u, 0.0))
                    c._hc[u] = cc
                lp[m], lv[m] = cc
            ln = np.hypot(px - ax, py - ay)
            beyond = 0.0
            if c.ti is not None:
                bx, by = self._txy(c.ti, i, PX, PY)
                ux, uy = bx - ax, by - ay
                lab = np.hypot(ux, uy)
                beyond = np.where(lab > 1e-9, np.maximum(0.0, ((px - ax) * ux + (py - ay) * uy)
                                                         / np.where(lab > 1e-9, lab, 1.0) - lab), 0.0)
            return lp * (1.0 + c.detour * np.sqrt(ln)) * (ln + 2.0 * beyond) + lv
        if isinstance(c, ST.CrystalComp):
            x0, y0 = self._txy(c.ti[0], i, PX, PY)
            h = self._h_ref(c.bv, st.G[c.ti[0].i], x0, y0)
            cp = np.empty(PX.shape)
            for u in np.unique(h):
                cp[h == u] = c._cprime(u)

            def length(terms):
                P = [self._txy(t, i, PX, PY) for t in terms]
                xs_ = np.array([p[0] for p in P])
                ys_ = np.array([p[1] for p in P])
                return xs_.max(0) - xs_.min(0) + ys_.max(0) - ys_.min(0)
            li, lo = length(c.ti), length(c.to)
            cd = c.detour
            return c.s * cp * (li * (1.0 + cd * np.sqrt(li)) + lo * (1.0 + cd * np.sqrt(lo))) / 4.0
        # fallback: per point
        saved = (st.get(i), st.V[i])
        out = np.empty(PX.shape)
        rot, side = st.R[i], ('F' if st.G[i] > 0 else 'B')
        for p in range(PX.shape[0]):
            st.set(i, PX[p], PY[p], rot, side)
            out[p] = c.value(st)
        st.set(i, *saved[0])
        st.V[i] = saved[1]
        return out

    def _engine(self, i, PX, PY, eng_l, eng_c):
        from kae.physics.jit import GAUSS
        e = self.T.engine
        bv = e.bv
        x0, y0, res, Hf, _ = bv._hraster[1]
        Hb = bv._hraster[-1][3]
        r0, r1 = ST.WIN_R
        X, Y, C, S, G = self._arrays(i)
        sel_l = np.array([p for p, _, _ in eng_l], np.int64)
        sel_c = np.array([p for p, _, _ in eng_c], np.int64)
        n = PX.shape[0]
        out_l = np.zeros((n, len(sel_l)))
        out_c = np.zeros((n, len(sel_c)))
        ol = np.empty(len(sel_l))
        oc = np.empty(len(sel_c))
        e.stamp += 1
        eng_grid(X, Y, C, S, G, i, np.ascontiguousarray(PX, float), np.ascontiguousarray(PY, float), e.LT_i, e.LT_xy,
                 e.L_meta, e.L_f, e.NT_i, e.NT_xya, e.N_meta, e.N_w, Hf, Hb, x0, y0, res, bv.er, e.Lp, e.Lk, e.Cp, e.Ck,
                 sel_l, sel_c, r0, r1, e.GP, e.Lc, e.Ls, e.PX, e.PY, e.PA, e.PC, e.Nc, e.Ns, e.stamp, *GAUSS,
                 *ST._scratch(), out_l, out_c, ol, oc)
        e.stamp += n + 1
        res_ = {}
        for q, (_, k, ci) in enumerate(eng_l):
            res_[(k, ci, 0)] = out_l[:, q]
        for q, (_, k, ci) in enumerate(eng_c):
            res_[(k, ci, 1)] = out_c[:, q]
        return res_

    def _thermal(self, i, rot, xs, ys):
        """Change of the thermal cost with part i at every node (Terms._th_delta)."""
        T = self.T
        th = T.thermal
        tm = self.tm
        st = T.st
        T0 = T._th_current()
        c0 = T._th_c
        t = T._th_ti.get(i)
        if t is None:
            return np.zeros((len(ys), len(xs)))
        ns = len(th.src)
        NY, NX = len(ys), len(xs)
        Tn = np.repeat(T0[:, None], NY * NX, 1)            # (targets, nodes)
        if t < ns:
            k = t
            # column: unit field of the moved source at every other target (symmetry of G)
            for tt, j in enumerate(th.targets):
                if tt == k:
                    continue
                U = tm.field_k(xs, ys, [(st.X[j], st.Y[j], 1.0, th.a[k])])
                Tn[tt] += (U.ravel() - th.G[tt, k]) * th.P[k]
            others = [(st.X[th.src[s]], st.Y[th.src[s]], th.P[s], th.a[s]) for s in range(ns) if s != k]
            row = tm.field_k(xs, ys, others) if others else np.zeros((NY, NX))
            row = row + th.P[k] * tm.diag_k(xs, ys, th.a[k], th.selfcorr[k])
            Tn[t] = row.ravel()
        else:
            srcs = [(st.X[th.src[s]], st.Y[th.src[s]], th.P[s], th.a[s]) for s in range(ns)]
            Tn[t] = tm.field_k(xs, ys, srcs).ravel()
        if getattr(T, '_th_a', None) is None:
            T._th_cost(T0)
        u = np.maximum(Tn - th.T_mean, 0.0) / T._th_a[:, None]
        cost = (T._th_cf[:, None] * phi_vec(u, T.knobs.barrier, T.knobs.u_sat)).sum(0)
        return (cost - c0).reshape(NY, NX)
