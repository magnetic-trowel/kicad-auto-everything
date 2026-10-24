# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Differentiable joint place-and-route by gradient descent (catalog ideas 17, 18, 22, 23).

Parts have continuous origins (x, y) in mm and a soft orientation (softmax over the four
90-degree rotations: pins sit at their expected position, footprints are a mixture of the
four rotated copies). One energy is minimized with Adam:

    E = R(x)                      routing term (mode="route") or smooth HPWL (mode="hpwl")
      + lam_d * N(x)              electrostatic density of the *overflow* (ePlace-like long
                                  range spreading that stops once bins are not overfull)
      + lam_p * sum ov_ij         pairwise courtyard-box overlap area (short range, exact)
      + lam_o * O(x)              courtyard / pad copper outside the board or on fixed parts
      + lam_c * C(x)              routing-capacity overflow of soft routes plus pad halos
    rotation pi = softmax(beta * theta), beta annealed 1 -> 30 (hardens the soft rotation)

Soft routing (mode="route"): soft-min shortest paths on a coarse (0.4-0.8 mm) grid. For
every pin a cost-weighted distance field d_a is computed by Dijkstra (numba); each net is
an MST over its pins under those distances. A connection a-b has soft routed length
D_ab = d_a(b) and soft cell usage u(c) ~ exp(-(d_a(c) + d_b(c) - D_ab) / T) (the
Laplace/saddle form of the soft-min Bellman-Ford edge marginals, normalized to the route
length). Cell cost = 1 + wb * (pad halos of other nets) + congestion price, so
  dD/d(pin b)     = grad d_a at b           (envelope-theorem tension along the route)
  dD/d(part pads) = wb * G * grad(U - U_net) under its halo samples (pushed off busy channels)
  dC/d(part pads) = overflow price gradient under its halos ("copper as charge").
T and wb are annealed (continuation), as are the density/overlap/entropy weights.

At the end: argmax orientation, snap to the 0.1 mm grid, nearest legal pose via
Kit.legal_map (largest parts first), optional HPWL descent, then Router.pathfinder.
"""
import math
import random
import sys
import time

import numpy as np
from numba import njit
from scipy.fft import dctn, idctn
from scipy.ndimage import distance_transform_edt

sys.path.insert(0, "/home/user/kicad-auto-everything/tools/research/pnr")

from methods import (_place_fixed, _router, center_bias, descent, greedy_place, growth_order,
                     place_mechanical)  # noqa: E402
from placekit import Clock, Kit  # noqa: E402
from world import ROTS  # noqa: E402

SQ2 = math.sqrt(2.0)
BIG = 30.0  # cost of a coarse cell outside the routable board


# ---------------------------------------------------------------- numba kernels
@njit(cache=True)
def _hpush(hk, hv, n, k, v):
    i = n
    hk[i] = k
    hv[i] = v
    while i > 0:
        p = (i - 1) >> 1
        if hk[p] <= hk[i]:
            break
        hk[p], hk[i] = hk[i], hk[p]
        hv[p], hv[i] = hv[i], hv[p]
        i = p
    return n + 1


@njit(cache=True)
def _hpop(hk, hv, n):
    k, v = hk[0], hv[0]
    n -= 1
    hk[0] = hk[n]
    hv[0] = hv[n]
    i = 0
    while True:
        l = 2 * i + 1
        if l >= n:
            break
        r = l + 1
        c = l
        if r < n and hk[r] < hk[l]:
            c = r
        if hk[c] >= hk[i]:
            break
        hk[c], hk[i] = hk[i], hk[c]
        hv[c], hv[i] = hv[i], hv[c]
        i = c
    return k, v, n


@njit(cache=True)
def dijkstra(cost, sx, sy, G, out, hk, hv, dmax):
    """Cost-weighted 8-neighbour distances (mm) from the continuous point (sx, sy) given in
    coarse-cell units (cell centres at integers). Edge a-b costs len * (c_a + c_b) / 2."""
    H, W = cost.shape
    for i in range(H * W):
        out.flat[i] = 1e18
    n = 0
    x0 = int(math.floor(sx))
    y0 = int(math.floor(sy))
    for dy in range(2):
        for dx in range(2):
            x, y = x0 + dx, y0 + dy
            if 0 <= x < W and 0 <= y < H:
                d = math.hypot(x - sx, y - sy) * cost[y, x] * G
                if d < out[y, x]:
                    out[y, x] = d
                    n = _hpush(hk, hv, n, d, y * W + x)
    dxs = (1, -1, 0, 0, 1, 1, -1, -1)
    dys = (0, 0, 1, -1, 1, -1, 1, -1)
    while n > 0:
        d, node, n = _hpop(hk, hv, n)
        if d > dmax:
            break
        y = node // W
        x = node - y * W
        if d > out[y, x]:
            continue
        ca = cost[y, x]
        for k in range(8):
            nx, ny = x + dxs[k], y + dys[k]
            if nx < 0 or ny < 0 or nx >= W or ny >= H:
                continue
            step = 1.0 if k < 4 else SQ2
            nd = d + step * 0.5 * (ca + cost[ny, nx]) * G
            if nd < out[ny, nx]:
                out[ny, nx] = nd
                n = _hpush(hk, hv, n, nd, ny * W + nx)


# ---------------------------------------------------------------- small helpers
def bilinear(field, u, v):
    """Value and (d/du, d/dv) of the bilinear interpolant of field[y, x] at (u, v) in cell
    units (u = x index, v = y index); points are clamped to the grid."""
    H, W = field.shape
    u = np.clip(u, 0.0, W - 1.001)
    v = np.clip(v, 0.0, H - 1.001)
    x0 = np.floor(u).astype(np.int64)
    y0 = np.floor(v).astype(np.int64)
    fx, fy = u - x0, v - y0
    f00 = field[y0, x0]
    f10 = field[y0, x0 + 1]
    f01 = field[y0 + 1, x0]
    f11 = field[y0 + 1, x0 + 1]
    val = f00 * (1 - fx) * (1 - fy) + f10 * fx * (1 - fy) + f01 * (1 - fx) * fy + f11 * fx * fy
    du = (f10 - f00) * (1 - fy) + (f11 - f01) * fy
    dv = (f01 - f00) * (1 - fx) + (f11 - f10) * fx
    return val, du, dv


def bilinear_multi(fields, k, u, v):
    """bilinear() of fields[k[i]] at (u[i], v[i])."""
    _, H, W = fields.shape
    u = np.clip(u, 0.0, W - 1.001)
    v = np.clip(v, 0.0, H - 1.001)
    x0 = np.floor(u).astype(np.int64)
    y0 = np.floor(v).astype(np.int64)
    fx, fy = u - x0, v - y0
    f00 = fields[k, y0, x0]
    f10 = fields[k, y0, x0 + 1]
    f01 = fields[k, y0 + 1, x0]
    f11 = fields[k, y0 + 1, x0 + 1]
    val = f00 * (1 - fx) * (1 - fy) + f10 * fx * (1 - fy) + f01 * (1 - fx) * fy + f11 * fx * fy
    du = (f10 - f00) * (1 - fy) + (f11 - f01) * fy
    dv = (f01 - f00) * (1 - fx) + (f11 - f10) * fx
    return val, du, dv


def splat(shape, u, v, wt, out=None):
    """Bilinear splat of weights at (u, v) (cell units) onto a grid."""
    H, W = shape
    if out is None:
        out = np.zeros(shape)
    u = np.clip(u, 0.0, W - 1.001)
    v = np.clip(v, 0.0, H - 1.001)
    x0 = np.floor(u).astype(np.int64)
    y0 = np.floor(v).astype(np.int64)
    fx, fy = u - x0, v - y0
    for dx, dy, ww in ((0, 0, (1 - fx) * (1 - fy)), (1, 0, fx * (1 - fy)),
                       (0, 1, (1 - fx) * fy), (1, 1, fx * fy)):
        np.add.at(out, (y0 + dy, x0 + dx), wt * ww)
    return out


def block_mean(a, f, fill):
    H, W = a.shape
    Hc, Wc = -(-H // f), -(-W // f)
    p = np.full((Hc * f, Wc * f), fill, np.float64)
    p[:H, :W] = a
    return p.reshape(Hc, f, Wc, f).mean(axis=(1, 3))


def subsample(offs, wcell, step):
    """Aggregate integer cell offsets (k, 2) into blocks of `step` cells: (mean offset,
    weight = count * wcell)."""
    if len(offs) == 0:
        return np.zeros((0, 2)), np.zeros(0)
    key = np.floor_divide(offs, step)
    uk, inv, cnt = np.unique(key, axis=0, return_inverse=True, return_counts=True)
    inv = inv.ravel()
    m = np.zeros((len(uk), 2))
    np.add.at(m, inv, offs.astype(float))
    return m / cnt[:, None], cnt * wcell


def softmax(t):
    e = np.exp(t - t.max(1, keepdims=True))
    return e / e.sum(1, keepdims=True)


class Adam:
    def __init__(self, shape, b1=0.9, b2=0.999):
        self.m = np.zeros(shape)
        self.v = np.zeros(shape)
        self.t = 0
        self.b1, self.b2 = b1, b2

    def step(self, g, lr):
        self.t += 1
        self.m = self.b1 * self.m + (1 - self.b1) * g
        self.v = self.b2 * self.v + (1 - self.b2) * g * g
        mh = self.m / (1 - self.b1 ** self.t)
        vh = self.v / (1 - self.b2 ** self.t)
        return lr * mh / (np.sqrt(vh) + 1e-9)


# ---------------------------------------------------------------- model
class Model:
    """Continuous relaxation of the board: movable parts, pins, halos, fixed obstacles."""

    def __init__(self, world, kit, mov, f=None):
        w = self.w = world
        self.kit = kit
        self.mov = mov
        g = w.g
        if f is None:
            f = int(np.clip(math.ceil(math.sqrt(w.W * w.H / 12000.0)), 4, 8))
        self.f = f
        self.G = G = f * g
        self.Hc, self.Wc = -(-w.H // f), -(-w.W // f)
        M = len(mov)
        self.idx = {pi: m for m, pi in enumerate(mov)}
        # ---- per part, per rotation: courtyard box, halo samples, court samples, pad cu samples
        self.box_c = np.zeros((M, 4, 2))  # box centre offset from origin (mm)
        self.box_h = np.zeros((M, 4, 2))  # half sizes (mm)
        self.area = np.zeros(M)
        self.sides = []
        self.halo = []  # [m][r] -> (offs mm (k,2), weight (k,), net (k,))
        self.courts = []  # [m][r] -> (offs mm, weight mm^2)
        self.cus = []  # [m][r] -> (offs mm, weight mm^2)
        sub = max(1, f // 2)
        for m, pi in enumerate(mov):
            part = w.parts[pi]
            # density/overlap sides: courtyard planes 0/1, plus the side of any copper layer
            # its pads keep out (through-hole parts occupy both)
            sd = {p for p in part.sides if p < 2}
            sd |= {0 if p == 2 else 1 for p in part.sides if p == 2 or p == 1 + w.nl}
            self.sides.append(tuple(sorted(sd)) or (part.side,))
            self.area[m] = part.area
            hl, cl, ul = [], [], []
            for r in range(4):
                rr = w.part_raster(part, r)
                x0, y0, x1, y1 = rr["bbox"]
                self.box_c[m, r] = ((x0 + x1) / 2 * g, (y0 + y1) / 2 * g)
                self.box_h[m, r] = ((x1 - x0 + 1) / 2 * g, (y1 - y0 + 1) / 2 * g)
                ho, hw, hn = [], [], []
                for ent in rr["pads"]:
                    if not len(ent["hT"]) or not ent["layers_halo"]:
                        continue
                    o, wt = subsample(ent["hT"], (g / G) ** 2 * len(ent["layers_halo"]) / w.nl, sub)
                    ho.append(o * g)
                    hw.append(wt)
                    hn.append(np.full(len(wt), ent["net"] if ent["net"] in w.net_pins else 0))
                hl.append((np.concatenate(ho) if ho else np.zeros((0, 2)),
                           np.concatenate(hw) if hw else np.zeros(0),
                           np.concatenate(hn).astype(np.int64) if hn else np.zeros(0, np.int64)))
                o, wt = subsample(rr["court"], g * g, sub)
                cl.append((o * g, wt))
                o, wt = subsample(rr["cu"], g * g, sub) if len(rr["cu"]) else (np.zeros((0, 2)), np.zeros(0))
                ul.append((o * g, wt))
            self.halo.append(hl)
            self.courts.append(cl)
            self.cus.append(ul)
        # ---- pins (nets with >= 2 pins), movable ones have per-rotation offsets
        self.nets = sorted(w.net_pins)
        pin_part, pin_off, pin_abs, self.net_slices = [], [], [], {}
        for n in self.nets:
            s = len(pin_part)
            for pi, k in w.net_pins[n]:
                if pi in self.idx:
                    pin_part.append(self.idx[pi])
                    pin_off.append([w.part_raster(w.parts[pi], r)["pads"][k]["center"] for r in range(4)])
                    pin_abs.append((0.0, 0.0))
                elif pi in w.pose:
                    pin_part.append(-1)
                    pin_off.append(np.zeros((4, 2)))
                    pin_abs.append(w.pad_world(pi, k))
            self.net_slices[n] = slice(s, len(pin_part))
        self.pin_part = np.array(pin_part, np.int64)
        self.pin_off = np.array(pin_off, float).reshape(-1, 4, 2)
        self.pin_abs = np.array(pin_abs, float).reshape(-1, 2)
        self.pin_net = np.zeros(len(pin_part), np.int64)
        for n, s in self.net_slices.items():
            self.pin_net[s] = n
        # ---- static maps (fixed + mechanical parts are already placed in the world)
        Hc, Wc = self.Hc, self.Wc
        blk = w.blockT.mean(0)
        bc = block_mean(blk, f, 1.0)
        self.outside_c = bc > 0.9
        self.P_static = np.where(self.outside_c, 0.0, bc)
        self.P_static_net = {}
        for pi in w.pose:
            if pi in self.idx:
                continue
            cx, cy, ri = w.pose[pi]
            rr = w.raster(pi)
            for ent in rr["pads"]:
                if not len(ent["hT"]) or not ent["layers_halo"]:
                    continue
                o = ent["hT"] + np.array([cx, cy])
                ok = (o[:, 0] >= 0) & (o[:, 1] >= 0) & (o[:, 0] < w.W) & (o[:, 1] < w.H)
                o = o[ok]
                wt = (g / G) ** 2 * len(ent["layers_halo"]) / w.nl
                u, v = (o[:, 0] - (f - 1) / 2) / f, (o[:, 1] - (f - 1) / 2) / f
                splat((Hc, Wc), u, v, np.full(len(o), wt), self.P_static)
                if ent["net"] in w.net_pins:
                    if ent["net"] not in self.P_static_net:
                        self.P_static_net[ent["net"]] = np.zeros((Hc, Wc))
                    splat((Hc, Wc), u, v, np.full(len(o), wt), self.P_static_net[ent["net"]])
        # forbidden-for-courtyard distance fields (fine grid, mm) per side, and pad copper
        self.edt_court = []
        self.rho_fixed = []
        for s in (0, 1):
            # courtyards may overhang the board edge (KiCad does not check it); pad copper
            # inside the edge clearance is handled by edt_cu
            forb = w.court[s] > 0
            self.edt_court.append(distance_transform_edt(forb) * g)
            self.rho_fixed.append(np.minimum(1.0, block_mean(forb.astype(float), f, 1.0)))
        self.edt_cu = distance_transform_edt(~w.ok_cu) * g
        # track pitch -> capacity of a coarse cell
        R = w.R
        self.pitch = R.w + R.c
        # DCT eigenvalues for the Poisson solve
        wu = np.pi * np.arange(Wc) / Wc
        wv = np.pi * np.arange(Hc) / Hc
        lam = (2 - 2 * np.cos(wv))[:, None] + (2 - 2 * np.cos(wu))[None, :]
        lam[0, 0] = 1.0
        self.poisson_inv = 1.0 / lam
        self.poisson_inv[0, 0] = 0.0
        # board region bounds for clamping (mm)
        ys, xs = np.nonzero(w.ok_court)
        self.lo = np.array([w.x0 + xs.min() * g, w.y0 + ys.min() * g])
        self.hi = np.array([w.x0 + xs.max() * g, w.y0 + ys.max() * g])
        self.hk = np.zeros(8 * Hc * Wc + 64)
        self.hv = np.zeros(8 * Hc * Wc + 64, np.int64)

    # coordinate maps
    def to_c(self, xy):
        """mm -> coarse cell units (cell centres at integers)."""
        w, f = self.w, self.f
        return ((xy[..., 0] - w.x0) / w.g - (f - 1) / 2) / f, ((xy[..., 1] - w.y0) / w.g - (f - 1) / 2) / f

    def to_f(self, xy):
        w = self.w
        return (xy[..., 0] - w.x0) / w.g, (xy[..., 1] - w.y0) / w.g

    def pins_xy(self, X, pi):
        """Expected pin positions (P, 2) and the movable mask."""
        mv = self.pin_part >= 0
        P = self.pin_abs.copy()
        pp = self.pin_part[mv]
        P[mv] = X[pp] + np.einsum("kr,krd->kd", pi[pp], self.pin_off[mv])
        return P, mv


# ---------------------------------------------------------------- energy terms
def wa_wirelength(model, P, gamma):
    """Weighted-average smooth HPWL per net; returns (value, dE/dP)."""
    gP = np.zeros_like(P)
    tot = 0.0
    for n, s in model.net_slices.items():
        p = P[s]
        if len(p) < 2:
            continue
        for d in range(2):
            x = p[:, d]
            a = np.exp((x - x.max()) / gamma)
            b = np.exp((x.min() - x) / gamma)
            sa, sb = a.sum(), b.sum()
            xa = (x * a).sum() / sa
            xb = (x * b).sum() / sb
            tot += xa - xb
            ga = a / sa * (1 + (x - xa) / gamma)
            gb = b / sb * (1 - (x - xb) / gamma)
            gP[s.start:s.stop, d] += ga - gb
    return tot, gP


def mst_edges(Dm):
    """Prim MST over a symmetric distance matrix; list of (i, j)."""
    k = len(Dm)
    if k < 2:
        return []
    inT = np.zeros(k, bool)
    inT[0] = True
    best = Dm[0].copy()
    par = np.zeros(k, np.int64)
    out = []
    for _ in range(k - 1):
        b = np.where(inT, np.inf, best)
        j = int(np.argmin(b))
        out.append((int(par[j]), j))
        inT[j] = True
        upd = Dm[j] < best
        best = np.where(upd, Dm[j], best)
        par = np.where(upd, j, par)
    return out


class SoftRouter:
    """Soft-min routing fields on the coarse grid."""

    def __init__(self, model):
        self.m = model
        self.fields = None
        self.edges = []
        self.U = np.zeros((model.Hc, model.Wc))
        self.Un = {}
        self.price = np.zeros((model.Hc, model.Wc))

    def update(self, X, pi, P, wb, T, wc):
        """Recompute distance fields from every pin, MSTs, usage maps."""
        m = self.m
        Hc, Wc = m.Hc, m.Wc
        G = m.G
        # dynamic pad-halo blockage of movable parts (mixture over rotations), per net
        Pdyn = np.zeros((Hc, Wc))
        Pnet = {}
        for mi in range(len(m.mov)):
            for r in range(4):
                if pi[mi, r] < 1e-3:
                    continue
                o, wt, nn = m.halo[mi][r]
                if not len(wt):
                    continue
                u, v = m.to_c(X[mi] + o)
                splat((Hc, Wc), u, v, wt * pi[mi, r], Pdyn)
                for n in np.unique(nn):
                    if n == 0:
                        continue
                    sel = nn == n
                    if n not in Pnet:
                        Pnet[n] = np.zeros((Hc, Wc))
                    splat((Hc, Wc), u[sel], v[sel], wt[sel] * pi[mi, r], Pnet[n])
        self.Pall = m.P_static + Pdyn
        base = 1.0 + wb * self.Pall + wc * self.price
        base = np.where(m.outside_c, BIG, base)
        uc, vc = m.to_c(P)
        fields = np.zeros((len(P), Hc, Wc))
        self.edges = []
        U = np.zeros((Hc, Wc))
        self.Un = {}
        tot = 0.0
        for n, s in m.net_slices.items():
            k = s.stop - s.start
            if k < 2:
                continue
            own = Pnet.get(n, 0.0) + m.P_static_net.get(n, 0.0)
            cost = np.where(m.outside_c, BIG, base - wb * own)
            cost = np.maximum(cost, 1.0) if wb > 0 else cost
            for i in range(s.start, s.stop):
                # search radius: far enough for every pin of the net and its corridors
                far = float(np.hypot(uc[s] - uc[i], vc[s] - vc[i]).max()) * G
                dmax = 3.0 * far + 6 * T + 5.0
                dijkstra(cost, uc[i], vc[i], G, fields[i], m.hk, m.hv, dmax)
                np.minimum(fields[i], 2 * dmax, out=fields[i])
            # pairwise distances, symmetrized
            Dm = np.zeros((k, k))
            for a in range(k):
                val, _, _ = bilinear(fields[s.start + a], uc[s], vc[s])
                Dm[a] = val
            Dm = 0.5 * (Dm + Dm.T)
            Un = np.zeros((Hc, Wc))
            for a, b in mst_edges(Dm):
                ia, ib = s.start + a, s.start + b
                D = Dm[a, b]
                tot += D
                # corridor window: cells with d_a + d_b - D < 6 T lie within (D + 6T) / 2 of
                # both pins (costs >= 1)
                rad = int((D + 6 * T) / 2 / G) + 2
                x0 = max(0, int(min(uc[ia], uc[ib])) - rad)
                x1 = min(Wc, int(max(uc[ia], uc[ib])) + rad + 2)
                y0 = max(0, int(min(vc[ia], vc[ib])) - rad)
                y1 = min(Hc, int(max(vc[ia], vc[ib])) + rad + 2)
                sl = (slice(y0, y1), slice(x0, x1))
                ex = np.exp(-np.maximum(fields[ia][sl] + fields[ib][sl] - D, 0.0) / T)
                ssum = ex.sum()
                if ssum > 0:
                    # normalize to the route length in cells (geometric length = D / mean cost)
                    cbar = float((ex * cost[sl]).sum()) / ssum
                    Un[sl] += ex * (D / G / max(1.0, cbar)) / ssum
                self.edges.append((ia, ib))
            self.Un[n] = Un
            U += Un
        self.fields = fields
        self.U = U
        self.cost = base
        return tot

    def congestion(self, nl):
        """Overflow energy of soft routes + halos and its derivative w.r.t. halo density."""
        m = self.m
        dem = self.U * m.pitch / (m.G * nl) + self.Pall
        ov = np.maximum(dem - 1.0, 0.0)
        ov = np.where(m.outside_c, 0.0, ov)
        return float((ov ** 2).sum()), 2.0 * ov


def density_terms(model, X, pi, target=1.0):
    """ePlace electrostatic density per side. Returns energy, dE/dX, dE/dpi, overflow."""
    m = model
    Hc, Wc, G = m.Hc, m.Wc, m.G
    w = m.w
    M = len(m.mov)
    # bin edges (mm)
    bx = w.x0 - w.g / 2 + np.arange(Wc + 1) * G
    by = w.y0 - w.g / 2 + np.arange(Hc + 1) * G
    prof = {}
    rho = [m.rho_fixed[0].copy(), m.rho_fixed[1].copy()]
    rho_mov = [np.zeros((Hc, Wc)), np.zeros((Hc, Wc))]
    for mi in range(M):
        for r in range(4):
            if pi[mi, r] < 1e-3:
                continue
            c = X[mi] + m.box_c[mi, r]
            h = m.box_h[mi, r]
            ox = np.clip(np.minimum(bx[1:], c[0] + h[0]) - np.maximum(bx[:-1], c[0] - h[0]), 0, None) / G
            oy = np.clip(np.minimum(by[1:], c[1] + h[1]) - np.maximum(by[:-1], c[1] - h[1]), 0, None) / G
            d = np.outer(oy, ox) * pi[mi, r]
            prof[mi, r] = d
            for s in m.sides[mi]:
                rho[s] += d
                rho_mov[s] += d
    E = 0.0
    gX = np.zeros((M, 2))
    gpi = np.zeros((M, 4))
    psi_s = []
    for s in (0, 1):
        # charge = overflow above the target density only (full ePlace charge over-spreads
        # sparse boards: the field keeps pushing towards uniform density)
        q = np.maximum(rho[s] - target, 0.0) if target is not None else rho[s]
        a = dctn(q, type=2, norm="ortho")
        psi = idctn(a * m.poisson_inv, type=2, norm="ortho")
        ey, ex = np.gradient(psi)
        psi_s.append((psi, ex / G, ey / G))
        E += 0.5 * float((q * psi).sum())
    for (mi, r), d in prof.items():
        for s in m.sides[mi]:
            psi, ex, ey = psi_s[s]
            gX[mi, 0] += float((d * ex).sum())
            gX[mi, 1] += float((d * ey).sum())
            gpi[mi, r] += float((d * psi).sum()) / max(pi[mi, r], 1e-9)
    tot_area = max(1e-9, m.area.sum())
    over = 0.0
    for s in (0, 1):
        over += float(np.maximum(rho[s] - 1.0, 0.0).sum()) * G * G
    return E, gX, gpi, over / tot_area


def pair_overlap(model, X, pi, margin):
    """Sum of pairwise overlap areas (mm^2) of expected courtyard boxes (+margin)."""
    m = model
    M = len(m.mov)
    C = X + np.einsum("mr,mrd->md", pi, m.box_c)
    Hh = np.einsum("mr,mrd->md", pi, m.box_h) + margin / 2
    gX = np.zeros((M, 2))
    gH = np.zeros((M, 2))
    tot = 0.0
    side = np.array([[1 if 0 in s else 0, 1 if 1 in s else 0] for s in m.sides])
    share = (side @ side.T) > 0
    for i in range(M):
        j = np.arange(i + 1, M)
        j = j[share[i, j]]
        if not len(j):
            continue
        # penetration depth per axis (h_i + h_j - |c_i - c_j|): equals the overlap length
        # for partial overlaps and keeps pushing contained boxes apart (overlap area would not)
        dc = C[i] - C[j]
        pen = Hh[i] + Hh[j] - np.abs(dc)
        hit = (pen[:, 0] > 0) & (pen[:, 1] > 0)
        if not hit.any():
            continue
        j, pen, dc = j[hit], pen[hit], dc[hit]
        tot += float((pen[:, 0] * pen[:, 1]).sum())
        sg = np.sign(dc)
        for d in range(2):
            o_other = pen[:, 1 - d]
            gX[i, d] += float((-sg[:, d] * o_other).sum())
            np.add.at(gX[:, d], j, sg[:, d] * o_other)
            gH[i, d] += float(o_other.sum())
            np.add.at(gH[:, d], j, o_other)
    gpi = np.einsum("md,mrd->mr", gX, m.box_c) + np.einsum("md,mrd->mr", gH, m.box_h)
    return tot, gX, gpi


def outside_terms(model, X, pi):
    """Courtyard samples on forbidden cells (outside board, fixed parts) and pad copper
    outside the copper area: sum w * (d + d^2), d = distance to the nearest allowed cell."""
    m = model
    M = len(m.mov)
    gX = np.zeros((M, 2))
    gpi = np.zeros((M, 4))
    tot = 0.0
    g = m.w.g
    for mi in range(M):
        for r in range(4):
            if pi[mi, r] < 1e-3:
                continue
            for (o, wt), fields in ((m.courts[mi][r], [m.edt_court[s] for s in m.sides[mi]]),
                                    (m.cus[mi][r], [m.edt_cu])):
                if not len(wt):
                    continue
                u, v = m.to_f(X[mi] + o)
                for F in fields:
                    val, du, dv = bilinear(F, u, v)
                    e = val + val * val
                    de = 1 + 2 * val
                    tot += pi[mi, r] * float((wt * e).sum())
                    gX[mi, 0] += pi[mi, r] * float((wt * de * du).sum()) / g
                    gX[mi, 1] += pi[mi, r] * float((wt * de * dv).sum()) / g
                    gpi[mi, r] += float((wt * e).sum())
    return tot, gX, gpi


def halo_force(model, X, pi, maps_all, maps_net):
    """Gradient of sum_c field(c) * halo_density(c) w.r.t. part origins and rotation
    weights, where the field seen by a halo sample of net n is maps_all - maps_net[n]."""
    m = model
    M = len(m.mov)
    gX = np.zeros((M, 2))
    gpi = np.zeros((M, 4))
    G = m.G
    for mi in range(M):
        for r in range(4):
            if pi[mi, r] < 1e-3:
                continue
            o, wt, nn = m.halo[mi][r]
            if not len(wt):
                continue
            u, v = m.to_c(X[mi] + o)
            val, du, dv = bilinear(maps_all, u, v)
            for n in np.unique(nn):
                if n and n in maps_net:
                    sel = nn == n
                    v2, du2, dv2 = bilinear(maps_net[n], u[sel], v[sel])
                    val[sel] -= v2
                    du[sel] -= du2
                    dv[sel] -= dv2
            gX[mi, 0] += pi[mi, r] * float((wt * du).sum()) / G
            gX[mi, 1] += pi[mi, r] * float((wt * dv).sum()) / G
            gpi[mi, r] += float((wt * val).sum())
    return gX, gpi


def physics_grad(ph, model, X, pi, w, gX, gpi, h):
    """Add w * d(physics)/d(origin) and w * physics(rotation r) to the gradients; returns
    the physics total at the current continuous poses (argmax rotation)."""
    world = model.w
    ra = pi.argmax(1)
    T, poses = ph.T, ph.poses
    for m, pi_ in enumerate(model.mov):
        if pi_ in ph.key:
            sd = "B" if world.parts[pi_].side else "F"
            poses[ph.key[pi_]] = (float(X[m, 0]), float(X[m, 1]), ROTS[ra[m]], sd)
    for m, pi_ in enumerate(model.mov):
        if pi_ not in ph.active:
            continue
        u = ph.key[pi_]
        x, y, rot, sd = poses[u]
        d = lambda q: float(T.delta(poses, [u], {u: q}))
        gX[m, 0] += w * (d((x + h, y, rot, sd)) - d((x - h, y, rot, sd))) / (2 * h)
        gX[m, 1] += w * (d((x, y + h, rot, sd)) - d((x, y - h, rot, sd))) / (2 * h)
        for r in range(4):
            if r != ra[m]:
                gpi[m, r] += w * d((x, y, ROTS[r], sd))
    return float(T.total(poses))


# ---------------------------------------------------------------- optimizer
def optimize(world, kit, mov, rng, mode, clock, t_opt, log, kw, start=None, ph=None):
    model = Model(world, kit, mov, f=kw.get("coarse_f"))
    M = len(mov)
    log(f"  grad model: {M} movable, coarse {model.Wc}x{model.Hc} G={model.G:.2f}mm, "
        f"{len(model.pin_part)} pins, {len(model.nets)} nets, mode={mode}")
    # init: free-area centroid + jitter
    ys, xs = np.nonzero(world.ok_court & (world.court[0] == 0))
    cen = np.array([world.x0 + xs.mean() * world.g, world.y0 + ys.mean() * world.g])
    span = model.hi - model.lo
    X = cen + (np.array([[rng.random() - 0.5, rng.random() - 0.5] for _ in range(M)]) *
               span * kw.get("init_spread", 0.3))
    X -= np.einsum("mr,mrd->md", np.full((M, 4), 0.25), model.box_c)
    theta = np.array([[rng.gauss(0, 0.1) for _ in range(4)] for _ in range(M)])
    if start is not None:  # refinement of a given legal placement
        for m, pi_ in enumerate(mov):
            if pi_ not in start:  # the start left it unplaced: keep the random init
                continue
            cx, cy, ri = start[pi_]
            X[m] = world.xy(cx, cy)
            theta[m, ri] += kw.get("theta_start", 2.0)
    optx, optt = Adam((M, 2)), Adam((M, 4))
    rng_np = np.random.default_rng(rng.randrange(1 << 30))
    sr = SoftRouter(model) if mode == "route" else None
    lam_d = lam_p = lam_o = None
    lam_c = kw.get("lam_c", 2.0)
    phys_w = kw.get("phys_w", 0.0)
    Ephys = 0.0
    span_mm = float(np.hypot(*span))
    it = 0
    t0 = time.process_time()  # CPU seconds, like placekit.Clock
    hist = []
    route_every = kw.get("route_every", 3)
    R_val = 0.0
    n_route = 0
    last_route_X = None
    beta0, beta1 = kw.get("beta0", 1.0), kw.get("beta1", 30.0)
    while True:
        if kw.get("iters"):  # deterministic, iteration-based schedule (for ablations)
            frac = min(1.0, it / kw["iters"])
            if it >= kw["iters"]:
                break
        else:
            frac = min(1.0, (time.process_time() - t0) / t_opt)
            if frac >= 1.0 and it > 30:
                break
        beta = beta0 * (beta1 / beta0) ** frac  # rotation softmax sharpness (continuation)
        pi = softmax(beta * theta)
        P, mv = model.pins_xy(X, pi)
        gP = np.zeros_like(P)
        gX = np.zeros((M, 2))
        gpi = np.zeros((M, 4))
        # ---- wiring term
        # smooth HPWL always drives the start; in route mode the soft routed length takes
        # over (s_r: 0 -> 1 between frac = r_start and r_start + r_ramp), because routing
        # costs of a clump of stacked parts carry no information
        gamma = kw.get("gamma0", 2.0) * (kw.get("gamma1", 0.3) / kw.get("gamma0", 2.0)) ** frac
        Rh, gPh = wa_wirelength(model, P, gamma)
        r0, rr = kw.get("r_start", 0.2), kw.get("r_ramp", 0.3)
        s_r = float(np.clip((frac - r0) / rr, 0.0, 1.0)) if mode == "route" else 0.0
        gP = (1 - s_r) * gPh
        Rw = Rh
        if s_r > 0:
            q = (frac - r0) / (1 - r0)
            T = kw.get("T0", 3.0) * (kw.get("T1", 0.4) / kw.get("T0", 3.0)) ** q
            wb = kw.get("wb0", 0.5) + (kw.get("wb1", 4.0) - kw.get("wb0", 0.5)) * q
            if n_route % route_every == 0:
                R_val = sr.update(X, pi, P, wb, T, kw.get("wc", 1.0))
                Ecg, dEdP = sr.congestion(world.nl)
                # congestion price feeds the next cost field (negotiation)
                sr.price = 0.7 * sr.price + 0.3 * dEdP
            n_route += 1
            # pin tensions from the distance fields (envelope theorem)
            uc, vc = model.to_c(P)
            if sr.edges:
                E_ = np.array(sr.edges)
                src = np.concatenate([E_[:, 0], E_[:, 1]])
                dst = np.concatenate([E_[:, 1], E_[:, 0]])
                _, du, dv = bilinear_multi(sr.fields, src, uc[dst], vc[dst])
                np.add.at(gP[:, 0], dst, s_r * 0.5 * du / model.G)
                np.add.at(gP[:, 1], dst, s_r * 0.5 * dv / model.G)
            # obstacle forces: routed length through halos + congestion overflow
            maps_all = wb * model.G * sr.U + lam_c * dEdP
            maps_net = {n: wb * model.G * u for n, u in sr.Un.items()}
            hx, hp = halo_force(model, X, pi, maps_all, maps_net)
            gX += s_r * hx
            gpi += s_r * hp
            Rw = R_val
        # physics place terms (kae.physics via pnr/physics.Phys): central finite differences
        # of the exact delta for the parts a term touches; the soft rotation sees the delta
        # of each of the four orientations (mixture, linearized)
        if ph is not None and phys_w > 0:
            Ephys = physics_grad(ph, model, X, pi, phys_w, gX, gpi, kw.get("phys_h", 0.25))
        # chain pins -> parts
        pp = model.pin_part[mv]
        np.add.at(gX, pp, gP[mv])
        np.add.at(gpi, pp, np.einsum("kd,krd->kr", gP[mv], model.pin_off[mv]))
        gw_norm = np.abs(gX).sum() + 1e-9
        # ---- placement terms
        Ed, gXd, gpd, over = density_terms(model, X, pi, kw.get("target_density", 1.0))
        Ep, gXp, gpp = pair_overlap(model, X, pi, kw.get("margin", 0.3))
        Eo, gXo, gpo = outside_terms(model, X, pi)
        if lam_d is None:  # balance initial gradient norms
            nd = np.abs(gXd).sum()
            lam_d = kw.get("lam_d0", 0.05) * (gw_norm / nd if nd > 1e-6 * gw_norm else 1.0)
            lam_p = kw.get("lam_p0", 0.01) * gw_norm / (np.abs(gXp).sum() + 1e-9) if Ep > 0 else 0.01
            lam_o = kw.get("lam_o0", 0.2)
        gX += lam_d * gXd + lam_p * gXp + lam_o * gXo
        gpi += lam_d * gpd + lam_p * gpp + lam_o * gpo
        # entropy hardening of the soft rotation
        H = -(pi * np.log(pi + 1e-12)).sum(1)
        # dE/dtheta = beta (diag(pi) - pi pi^T) dE/dpi
        gth = beta * pi * (gpi - (pi * gpi).sum(1, keepdims=True))
        lr = kw.get("lr0", 0.01) * span_mm * (kw.get("lr1", 0.0005) / kw.get("lr0", 0.01)) ** frac
        X = X - optx.step(gX, lr)
        if frac < 0.6:
            X += rng_np.normal(0, kw.get("noise", 0.3) * lr * (1 - frac / 0.6), X.shape)
        theta = theta - optt.step(gth, kw.get("lr_rot", 0.1))
        X = np.clip(X, model.lo - 2, model.hi + 2)
        # continuation of penalty weights
        # (grow only while the violation is above what the legalizer can absorb)
        tot_area = model.area.sum()
        if over > kw.get("target_over", 0.05):
            lam_d *= kw.get("mu_d", 1.02)
        if Ep > kw.get("target_pair", 0.01) * tot_area:
            lam_p *= kw.get("mu_p", 1.02)
        if Eo > kw.get("target_out", 0.002) * tot_area:
            lam_o *= kw.get("mu_o", 1.02)
        if it % 25 == 0:
            log(f"  it={it} t={frac:.2f} R={Rw:.1f} dens={Ed:.2f} over={over:.3f} pair={Ep:.2f} "
                f"out={Eo:.2f} phys={Ephys:.2f} H={H.mean():.2f} lam_d={lam_d:.3g} lam_p={lam_p:.3g} lam_o={lam_o:.3g}")
        it += 1
    pi = softmax(beta * theta)
    return X, pi, model, it


# ---------------------------------------------------------------- legalization
def legalize(world, kit, model, X, pi, log, rot_pen_mm=1.0):
    """Largest parts first: argmax orientation, nearest legal origin (other rotations if
    clearly closer)."""
    g = world.g
    mov = model.mov
    order = sorted(range(len(mov)), key=lambda m: -model.area[m])
    fails = 0
    disp = []
    for m in order:
        pi_ = mov[m]
        rbest = int(np.argmax(pi[m]))
        tx, ty = (X[m, 0] - world.x0) / g, (X[m, 1] - world.y0) / g
        best = None
        for r in range(4):
            L = kit.legal_map(pi_, r)
            if not L.any():
                continue
            # keep the pose's box centre where the optimizer put it (rotations move it)
            dcx = (np.einsum("r,rd->d", pi[m], model.box_c[m]) - model.box_c[m, r]) / g
            yy, xx = np.nonzero(L)
            d = np.hypot(xx - (tx + dcx[0]), yy - (ty + dcx[1])) * g + (0 if r == rbest else rot_pen_mm)
            j = int(np.argmin(d))
            if best is None or d[j] < best[0]:
                best = (float(d[j]), int(xx[j]), int(yy[j]), r)
        if best is None:
            fails += 1
            log(f"  no legal spot for {world.parts[pi_].ref}")
            continue
        world.place(pi_, best[1], best[2], best[3])
        disp.append(best[0])
    log(f"  legalized: mean displacement {np.mean(disp) if disp else 0:.2f} mm, "
        f"max {max(disp) if disp else 0:.2f}, fails {fails}")
    return fails


# ---------------------------------------------------------------- method entry points
def grad(world, seed=0, budget=120, log=print, mode="route", **kw):
    """Joint place-and-route by gradient descent on a soft-routing energy."""
    rng = random.Random(seed)
    np.random.seed(seed)
    clock = Clock(budget)
    _place_fixed(world)
    r = _router(world, kw)
    kit = Kit(world, r)
    place_mechanical(world, kit, log)
    mov = [pi for pi in kit.movable() if pi not in world.pose]
    ph = None
    if mov:
        start = None
        if kw.get("init") == "seq":
            # refine the control's placement: same greedy + descent as methods.seq
            greedy_place(world, kit, growth_order(world, kit, rng), log)
            descent(world, kit, log, clock=clock)
            start = {pi: world.pose[pi] for pi in mov if pi in world.pose}
            log(f"  seq start hpwl {world.hpwl():.1f}")
            for pi in start:
                world.unplace(pi)
            for k, v in (("lam_d0", 1.0), ("lam_p0", 1.0), ("lam_o0", 5.0), ("lr0", 0.004),
                         ("lr1", 0.0005), ("beta0", 3.0), ("T0", 1.5), ("wb0", 2.0)):
                kw.setdefault(k, v)
        if kw.get("phys_w", 0.0) > 0:
            from physics import Phys
            ph = Phys(world, world.data["path"])
            ph.sync()
            log(f"  physics parts {len(ph.active & set(mov))} of {len(mov)} movable")
        t_opt = budget * kw.get("opt_frac", 0.45)
        X, pi, model, its = optimize(world, kit, mov, rng, mode, clock, t_opt, log, kw, start=start,
                                     ph=ph)
        log(f"  optimized {its} iterations, {time.process_time() - clock.t0:.1f} CPU s so far")
        legalize(world, kit, model, X, pi, log)
        log(f"  hpwl after legalize {world.hpwl():.1f}")
        if kw.get("post", "none") == "descent":
            descent(world, kit, log, clock=clock, rounds=kw.get("rounds", 6))
        elif kw.get("post") == "phys" and ph is not None:
            # engine-side clean-up after legalization: best-response on HPWL + phys_w *
            # physics (methods_phys.descent_phys), as seq_phys does after its HPWL descent
            from methods_phys import descent_phys
            ph.sync()
            descent_phys(world, kit, ph, kw.get("phys_w", 2.0), log, clock=clock)
        elif kw.get("post") == "local":
            local_descent(world, kit, log, clock, radius_mm=kw.get("radius_mm", 2.0))
        if ph is not None:
            ph.sync()
            log(f"  physics after legalization {ph.total():.2f}")
    r.pathfinder(log=log, iters=40)
    log(f"grad[{mode}] {r.stats()} hpwl={world.hpwl():.1f}")
    return r


def local_descent(world, kit, log, clock, radius_mm=2.0, rounds=4):
    """HPWL best-response restricted to a window around each part's current pose (keeps the
    global arrangement found by the optimizer, cleans up legalization detours)."""
    rad = int(radius_mm / world.g)
    bias = center_bias(kit, 0.002)
    for rd in range(rounds):
        moved = 0
        for pi in kit.movable():
            if pi not in world.pose:
                continue
            cur = world.pose[pi]
            world.unplace(pi)
            here = kit.hpwl_map(pi, cur[2])[cur[1], cur[0]]
            win = np.zeros((world.H, world.W), bool)
            win[max(0, cur[1] - rad):cur[1] + rad + 1, max(0, cur[0] - rad):cur[0] + rad + 1] = True
            c = kit.candidates(pi, rots=[cur[2]], k=1, cost_extra=bias, legal_extra=~win)
            if c and c[0][0] < here - 1e-6:
                world.place(pi, c[0][1], c[0][2], c[0][3])
                moved += 1
            else:
                world.place(pi, *cur)
            if clock.left() < 0:
                return
        log(f"  local descent round {rd}: moved {moved}, hpwl {world.hpwl():.1f}")
        if not moved:
            break


def grad_hpwl(world, seed=0, budget=120, log=print, **kw):
    """Ablation: the same pipeline with the routing term replaced by smooth HPWL."""
    return grad(world, seed=seed, budget=budget, log=log, mode="hpwl", **kw)


def grad_phys(world, seed=0, budget=120, log=print, phys_w=2.0, **kw):
    """Soft-routing energy plus phys_w (mm per unit) times the kae physics place terms."""
    return grad(world, seed=seed, budget=budget, log=log, mode="route", phys_w=phys_w, **kw)


def grad_hpwl_phys(world, seed=0, budget=120, log=print, phys_w=2.0, **kw):
    """Ablation of grad_phys without the routing term."""
    return grad(world, seed=seed, budget=budget, log=log, mode="hpwl", phys_w=phys_w, **kw)
