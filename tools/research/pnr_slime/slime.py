# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Physarum (slime-mould) multicommodity network dynamics coupled to part motion
(catalog idea 20; Tero et al. 2007/2010, Bonifaci et al. multi-commodity Physarum).

Soft routing on a coarse grid (~0.5 mm) per copper layer plus via edges:
  every net is a commodity with its own tube conductivities D_n on the edges of its
  bounding box (+ margin). Each iteration solves the Kirchhoff problem
      L(D_n * s_n / len) p = b      (one RHS per choice of source pin; the other pins sink)
  and relaxes  D_n <- (1 - dt) D_n + dt * f(|Q_n|) * pen_n,  f = Tero's sigmoid.
  s_n is the free fraction of the coarse cell for net n (foreign pad halos, board edge
  and keep-outs -> ~0); pen_n = 1 / (1 + beta * occupancy of OTHER nets' tubes on that
  node and layer + history), so nets compete for edges and separate onto layers.
Part motion: each part is pulled by its pins along the tube leaving each pad (envelope
theorem on the soft network), pushed down the gradient of foreign tube occupancy under its
courtyard and (optionally) down the finite-difference gradient of the physics place terms
(physics.Phys, phys_w mm per unit). It steps, is legalized to the nearest legal origin
(Kit.legal_map), its nets are re-grown, and the move is kept only if network cost
(+ phys_w * physics) dropped; then all flows are re-solved.
Final: route with the engine's PathFinder, optionally with a per-net corridor prior
(extra history cost off the net's final slime tubes) so the slime topology and layer
assignment transfer to real copper. Budgets are CPU seconds (placekit.Clock).

Methods (plug-ins for run.py):
  slime          seq start + slime part motion + corridor prior
  slime_motion   seq start + slime part motion, plain PathFinder
  slime_prior    seq placement, slime solve, corridor-prior PathFinder (no motion)
  slime_phys     seq start + slime part motion with the physics term
  slime_phys2    seq_phys start (methods_phys.descent_phys) + slime motion with physics
"""
import os
import math
import random
import sys

import numpy as np
import scipy.sparse as sp
from scipy.ndimage import maximum_filter
from scipy.sparse.linalg import splu

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "pnr"))

from methods import _place_fixed, descent, greedy_place, growth_order, place_mechanical  # noqa: E402
from placekit import Clock, Kit  # noqa: E402
from router import Router  # noqa: E402


# ---------------------------------------------------------------- the slime mould
class Slime:
    def __init__(self, world, gc_mm=0.5, margin_mm=3.0, via_mm=2.0, mu=2.0, dt=0.5,
                 beta0=0.5, beta_mul=1.15, beta_max=20.0, max_src=6, max_nodes=60000, noise=0.3,
                 seed=0):
        self.w = world
        self.noise = noise
        self.nrng = np.random.default_rng(seed)
        g = world.g
        # coarse factor; grow the cell on big boards so one solve stays small
        f = max(1, int(round(gc_mm / g)))
        while world.nl * math.ceil(world.H / f) * math.ceil(world.W / f) > max_nodes:
            f += 1
        self.f = f
        self.gc = f * g
        self.Hc, self.Wc = math.ceil(world.H / f), math.ceil(world.W / f)
        self.L = world.nl
        self.margin = max(2, int(round(margin_mm / self.gc)))
        self.via_len = via_mm
        self.mu, self.dt = mu, dt
        self.beta, self.beta_mul, self.beta_max = beta0, beta_mul, beta_max
        self.max_src = max_src
        self.nets = [n for n in world.net_pins]
        self.D = {}  # net -> (y0, x0, Dh, Dv, Dz) on its box
        self.occ_n = {}  # net -> (y0, x0, occ (L, h, w))
        self.occ = np.zeros((self.L, self.Hc, self.Wc))
        self.hist = np.zeros((self.L, self.Hc, self.Wc))
        self.vol = {}  # net -> tube volume (mm)
        self.it = 0
        self.hist_rate = 0.1  # congestion history; frozen during part motion so costs compare

    # ------------------------------------------------------------ geometry
    def pins(self, n):
        """[(yc, xc, layers)] coarse cell of each placed pin of net n."""
        w = self.w
        out = []
        for pi, k in w.net_pins[n]:
            if pi not in w.pose:
                continue
            x, y = w.pad_world(pi, k)
            fx, fy = (x - w.x0) / w.g, (y - w.y0) / w.g
            xc = min(self.Wc - 1, max(0, int(fx + 0.5) // self.f))
            yc = min(self.Hc - 1, max(0, int(fy + 0.5) // self.f))
            ent = w.raster(pi)["pads"][k]
            out.append((yc, xc, ent["layers"] or list(range(self.L))))
        return out

    def box(self, pins):
        ys = [p[0] for p in pins]
        xs = [p[1] for p in pins]
        m = self.margin
        return (max(0, min(ys) - m), max(0, min(xs) - m),
                min(self.Hc, max(ys) + m + 1), min(self.Wc, max(xs) + m + 1))

    def free(self, n, y0, x0, y1, x1, pins):
        """Free fraction s (track) and sv (via) per coarse node of the box for net n."""
        w, f = self.w, self.f
        sl = (slice(None), slice(y0 * f, min(y1 * f, w.H)), slice(x0 * f, min(x1 * f, w.W)))
        own = w.occT[(n,) + sl] > 0
        badT = ((w.DT[sl] - own) > 0) | w.blockT[sl]
        ownv = w.occV[(n,) + sl] > 0
        badV = ((w.DV[sl] - ownv) > 0) | w.blockV[sl]

        def cm(a):
            full = np.ones((self.L, (y1 - y0) * f, (x1 - x0) * f), bool)
            full[:, :a.shape[1], :a.shape[2]] = a
            return full.reshape(self.L, y1 - y0, f, x1 - x0, f).mean(axis=(2, 4))
        s = (1.0 - cm(badT)) ** 2
        sv = (1.0 - cm(badV)).min(axis=0) ** 2
        for yc, xc, ls in pins:
            for l in ls:
                s[l, yc - y0, xc - x0] = 1.0
            if len(ls) > 1:
                sv[yc - y0, xc - x0] = 1.0
        return np.maximum(s, 1e-3), np.maximum(sv, 1e-3)

    # ------------------------------------------------------------ one net
    def _get_D(self, n, y0, x0, h, wd):
        # fresh tubes start at 0.5 with noise so parallel layers do not stay symmetric
        L, nr = self.L, self.nrng
        Dh = 0.5 * (1 + self.noise * nr.standard_normal((L, h, wd - 1)))
        Dv = 0.5 * (1 + self.noise * nr.standard_normal((L, h - 1, wd)))
        Dz = np.full((max(L - 1, 0), h, wd), 0.5)
        Dh, Dv = np.clip(Dh, 0.05, 1.0), np.clip(Dv, 0.05, 1.0)
        old = self.D.get(n)
        if old is not None:
            oy, ox, oh, ov, oz = old
            for new, prev in ((Dh, oh), (Dv, ov), (Dz, oz)):
                # copy the overlap of the old box into the new one
                ya, xa = max(y0, oy), max(x0, ox)
                yb = min(y0 + new.shape[1], oy + prev.shape[1])
                xb = min(x0 + new.shape[2], ox + prev.shape[2])
                if ya < yb and xa < xb and new.shape[0]:
                    new[:, ya - y0:yb - y0, xa - x0:xb - x0] = prev[:, ya - oy:yb - oy, xa - ox:xb - ox]
        return Dh, Dv, Dz

    def step_net(self, n, rng, update=True):
        pins = self.pins(n)
        if len(pins) < 2:
            return
        y0, x0, y1, x1 = self.box(pins)
        h, wd, L = y1 - y0, x1 - x0, self.L
        s, sv = self.free(n, y0, x0, y1, x1, pins)
        Dh, Dv, Dz = self._get_D(n, y0, x0, h, wd)
        gc = self.gc
        ch = Dh * np.minimum(s[:, :, :-1], s[:, :, 1:]) / gc
        cv = Dv * np.minimum(s[:, :-1, :], s[:, 1:, :]) / gc
        cz = Dz * (np.minimum(s[:-1], s[1:]) * sv[None]) / self.via_len if L > 1 else Dz
        for yc, xc, ls in pins:
            if len(ls) > 1 and L > 1:  # plated barrel: free layer change at the pad
                cz[:, yc - y0, xc - x0] = 100.0 / gc
        idx = np.arange(L * h * wd).reshape(L, h, wd)
        u = np.concatenate([idx[:, :, :-1].ravel(), idx[:, :-1, :].ravel(), idx[:-1].ravel()])
        v = np.concatenate([idx[:, :, 1:].ravel(), idx[:, 1:, :].ravel(), idx[1:].ravel()])
        c = np.concatenate([ch.ravel(), cv.ravel(), cz.ravel()])
        N = L * h * wd
        deg = np.bincount(u, c, N) + np.bincount(v, c, N)
        A = sp.coo_matrix((np.concatenate([-c, -c, deg + 1e-7 * (deg.mean() + 1e-12)]),
                           (np.concatenate([u, v, np.arange(N)]), np.concatenate([v, u, np.arange(N)]))),
                          shape=(N, N)).tocsc()
        # one RHS per source pin (up to max_src): source +(k-1) units, every other pin -1
        k = len(pins)
        srcs = list(range(k)) if k <= self.max_src else random.Random(n).sample(range(k), self.max_src)
        B = np.zeros((N, len(srcs)))
        for j, si in enumerate(srcs):
            for i, (yc, xc, ls) in enumerate(pins):
                amt = (k - 1.0) if i == si else -1.0
                B[idx[ls[0], yc - y0, xc - x0], j] += amt
        P = splu(A).solve(B)
        Q = np.abs(c[:, None] * (P[u] - P[v])).mean(axis=1)
        nh, nv = ch.size, cv.size
        Qh, Qv, Qz = Q[:nh].reshape(ch.shape), Q[nh:nh + nv].reshape(cv.shape), Q[nh + nv:].reshape(cz.shape)
        if update:
            # competition: other nets' tubes on the same node/layer, plus congestion history
            mine = self.occ_n.get(n)
            oth = self.occ[:, y0:y1, x0:x1].copy()
            if mine is not None:
                my, mx, mo = mine
                ya, xa = max(y0, my), max(x0, mx)
                yb, xb = min(y1, my + mo.shape[1]), min(x1, mx + mo.shape[2])
                if ya < yb and xa < xb:
                    oth[:, ya - y0:yb - y0, xa - x0:xb - x0] -= mo[:, ya - my:yb - my, xa - mx:xb - mx]
            oth = np.maximum(oth, 0.0)
            node_pen = 1.0 / (1.0 + self.beta * oth + self.hist[:, y0:y1, x0:x1])
            ph = np.minimum(node_pen[:, :, :-1], node_pen[:, :, 1:])
            pv = np.minimum(node_pen[:, :-1, :], node_pen[:, 1:, :])
            pz = np.minimum(node_pen[:-1], node_pen[1:]) if L > 1 else Dz

            def fq(q):
                qm = q ** self.mu
                return 2.0 * qm / (1.0 + qm)
            dt = self.dt
            Dh = np.maximum((1 - dt) * Dh + dt * fq(Qh) * ph, 1e-4)
            Dv = np.maximum((1 - dt) * Dv + dt * fq(Qv) * pv, 1e-4)
            if L > 1:
                Dz = np.maximum((1 - dt) * Dz + dt * fq(Qz) * pz, 1e-4)
        self.D[n] = (y0, x0, Dh, Dv, Dz)
        occ = np.zeros((L, h, wd))
        np.maximum(occ[:, :, :-1], Dh, out=occ[:, :, :-1])
        np.maximum(occ[:, :, 1:], Dh, out=occ[:, :, 1:])
        np.maximum(occ[:, :-1, :], Dv, out=occ[:, :-1, :])
        np.maximum(occ[:, 1:, :], Dv, out=occ[:, 1:, :])
        if L > 1:
            for l in range(L - 1):
                np.maximum(occ[l], Dz[l], out=occ[l])
                np.maximum(occ[l + 1], Dz[l], out=occ[l + 1])
        self.occ_n[n] = (y0, x0, np.minimum(occ, 1.0))
        self.vol[n] = gc * (Dh.sum() + Dv.sum()) + self.via_len * Dz.sum()

    def rebuild_occ(self):
        self.occ[:] = 0
        for n, (y0, x0, o) in self.occ_n.items():
            self.occ[:, y0:y0 + o.shape[1], x0:x0 + o.shape[2]] += o

    def iterate(self, k, rng):
        for _ in range(k):
            for n in self.nets:
                self.step_net(n, rng)
            self.rebuild_occ()
            over = np.maximum(self.occ - 1.0, 0.0)
            self.hist += self.hist_rate * over
            self.beta = min(self.beta_max, self.beta * self.beta_mul)
            self.it += 1

    def iterate_nets(self, nets, k, rng):
        """Re-solve only `nets` (the others' tubes stay as they are)."""
        for _ in range(k):
            for n in nets:
                self.step_net(n, rng)
            self.rebuild_occ()

    def snapshot(self, nets):
        return {n: (self.D.get(n), self.occ_n.get(n), self.vol.get(n)) for n in nets}

    def restore(self, snap):
        for n, (d, o, v) in snap.items():
            self.D[n], self.occ_n[n], self.vol[n] = d, o, v
        self.rebuild_occ()

    def local_cost(self, nets):
        over = float(np.maximum(self.occ - 1.0, 0.0).sum()) * self.gc
        return sum(self.vol[n] for n in nets) + 5.0 * over

    def cost(self):
        """Network cost: tube volume + overflow (tubes of several nets on one node/layer)."""
        over = float(np.maximum(self.occ - 1.0, 0.0).sum()) * self.gc
        return sum(self.vol.values()) + 5.0 * over, over

    # ------------------------------------------------------------ outputs
    def tube(self, n, thr=0.3):
        """(y0, x0, bool (L, h, w)) where net n has a tube."""
        y0, x0, o = self.occ_n[n]
        return y0, x0, o >= thr

    def prior(self, n, lam=0.6, thr=0.3, dil=1):
        """Fine (L, H, W) extra history: lam off the net's (dilated) tubes, 0 on them."""
        w, f = self.w, self.f
        if n not in self.occ_n:
            return None
        y0, x0, t = self.tube(n, thr)
        if dil:
            t = maximum_filter(t, size=(1, 2 * dil + 1, 2 * dil + 1))
        pc = np.full((self.L, self.Hc, self.Wc), lam, np.float32)
        pc[:, y0:y0 + t.shape[1], x0:x0 + t.shape[2]] = np.where(t, 0.0, lam)
        fine = np.repeat(np.repeat(pc, f, axis=1), f, axis=2)[:, :w.H, :w.W]
        return np.ascontiguousarray(fine)


# ---------------------------------------------------------------- router with a corridor prior
class PriorRouter(Router):
    """PathFinder whose history cost, while net n is routed, is hist + prior[n]."""

    def __init__(self, world, prior=None, **kw):
        super().__init__(world, **kw)
        self.prior = prior or {}

    def route_net(self, net, hard=False, pres=None):
        pr = self.prior.get(net)
        if pr is None:
            return super().route_net(net, hard=hard, pres=pres)
        base = self.w.hist
        self.w.hist = base + pr
        try:
            return super().route_net(net, hard=hard, pres=pres)
        finally:
            self.w.hist = base


# ---------------------------------------------------------------- part motion
def phys_grad(world, ph, pi, h_mm=1.0):
    """Central finite-difference gradient (per mm) of the place-terms total for part pi."""
    cx, cy, ri = world.pose[pi]
    h = max(1, int(round(h_mm / world.g)))
    gx = (ph.delta(pi, (cx + h, cy, ri)) - ph.delta(pi, (cx - h, cy, ri))) / (2 * h * world.g)
    gy = (ph.delta(pi, (cx, cy + h, ri)) - ph.delta(pi, (cx, cy - h, ri))) / (2 * h * world.g)
    return np.array([gx, gy])


def part_force(world, kit, sl, pi, w_press, look_cells=3, ph=None, phys_w=2.0):
    """Pin pulls along the tube leaving each pad (d tube length / d pin ~ unit vector, so
    the force is in mm of tube per mm of motion) + push down the foreign-tube gradient
    + (optional) -phys_w * gradient of the physics place terms."""
    cx, cy, ri = world.pose[pi]
    rr = world.raster(pi)
    f = sl.f
    F = np.zeros(2)
    pulls = []
    own_nets = set()
    for k, ent in enumerate(rr["pads"]):
        n = ent["net"]
        if n not in sl.occ_n:
            continue
        own_nets.add(n)
        y0, x0, o = sl.occ_n[n]
        px = (cx + ent["center"][0] / world.g) / f
        py = (cy + ent["center"][1] / world.g) / f
        r = look_cells
        ya, yb = int(py) - r, int(py) + r + 1
        xa, xb = int(px) - r, int(px) + r + 1
        ya, xa = max(ya, y0), max(xa, x0)
        yb, xb = min(yb, y0 + o.shape[1]), min(xb, x0 + o.shape[2])
        if ya >= yb or xa >= xb:
            continue
        sub = o[:, ya - y0:yb - y0, xa - x0:xb - x0].max(axis=0)
        yy, xx = np.mgrid[ya:yb, xa:xb]
        dx, dy = xx + 0.5 - px, yy + 0.5 - py
        d = np.hypot(dx, dy)
        m = (d > 0.75) & (d <= r + 0.5)
        if not m.any():
            continue
        vec = np.array([(sub[m] * dx[m] / d[m]).sum(), (sub[m] * dy[m] / d[m]).sum()])
        nv = np.linalg.norm(vec)
        if nv > 1e-9:
            pulls.append((k, vec / nv))
            F += vec / nv
    # pressure from foreign tubes under the courtyard
    oth = sl.occ.sum(0)
    for n in own_nets:
        y0, x0, o = sl.occ_n[n]
        oth[y0:y0 + o.shape[1], x0:x0 + o.shape[2]] -= o.sum(0)
    gy, gx = np.gradient(np.maximum(oth, 0.0))
    c = rr["court"]
    xs = np.clip((c[:, 0] + cx) // f, 0, sl.Wc - 1)
    ys = np.clip((c[:, 1] + cy) // f, 0, sl.Hc - 1)
    G = -np.array([gx[ys, xs].mean(), gy[ys, xs].mean()])
    F += w_press * G * max(1, len(pulls))
    if ph is not None and pi in ph.active:
        F -= phys_w * phys_grad(world, ph, pi)
    return F, pulls


def motion(world, kit, sl, clock, rng, log, frac=0.55, rounds=40, k_iter=6, step_mm=1.5,
           w_press=1.0, allow_rot=True, accept=True, k_local=4, ph=None, phys_w=2.0, restore=True):
    pw = (lambda: phys_w * ph.total()) if ph is not None else (lambda: 0.0)
    mov = [pi for pi in kit.movable() if pi in world.pose and kit.part_nets([pi])]
    sl.iterate(30, rng)  # warm-up: competition price reaches its cap, then stays fixed
    sl.hist_rate = 0.0
    prev = sl.cost()[0]
    for _ in range(10):  # settle: tube volume steady to 0.5 %
        sl.iterate(5, rng)
        c = sl.cost()[0]
        if abs(c - prev) < 0.005 * prev:
            break
        prev = c
    c0, ov0 = sl.cost()
    best = (c0 + pw(), dict(world.pose))
    log(f"  slime start cost={c0:.1f} overflow={ov0:.2f} beta={sl.beta:.2f}")
    t_end = clock.budget * frac
    target = {pi: np.array(world.pose[pi][:2], float) for pi in mov}
    rd = 0
    while rd < rounds and clock.budget - clock.left() < t_end:
        rd += 1
        fr = (clock.budget - clock.left()) / t_end
        step = step_mm * (1.0 - 0.85 * fr) / world.g
        forces = {pi: part_force(world, kit, sl, pi, w_press, ph=ph, phys_w=phys_w) for pi in mov}
        rng.shuffle(mov)
        moved = 0
        for pi in mov:
            F, pulls = forces[pi]
            nF = np.linalg.norm(F)
            npull = max(1, len(pulls))
            cx, cy, ri = world.pose[pi]
            nri = ri
            if allow_rot and pulls:
                score = {}
                for q in range(4):
                    pr = world.part_raster(world.parts[pi], q)["pads"]
                    score[q] = sum(float(np.dot(t, pr[k]["center"])) for k, t in pulls)
                bq = max(score, key=score.get)
                if score[bq] > score[ri] + 0.5 * npull * world.g * 5:
                    nri = bq
            if nF < 1e-6 and nri == ri:
                continue
            # continuous move: magnitude ~ alignment of the pulls (|F| / #pins)
            mag = min(1.0, nF / npull)
            tgt = target[pi] + (F / (nF + 1e-9)) * step * mag
            world.unplace(pi)
            if ph is not None:
                ph.commit(pi)  # no-op for parts no term touches
            L = kit.legal_map(pi, nri)
            if not L.any() and nri != ri:
                nri = ri
                L = kit.legal_map(pi, ri)
            if not L.any():
                world.place(pi, cx, cy, ri)
                continue
            yy, xx = np.nonzero(L)
            j = int(np.argmin((xx - tgt[0]) ** 2 + (yy - tgt[1]) ** 2))
            nx, ny = int(xx[j]), int(yy[j])
            if math.hypot(nx - cx, ny - cy) > 3 * step + 3:
                nx, ny, nri = cx, cy, ri  # blocked: stay, keep the continuous target near
                tgt = 0.5 * (tgt + np.array([cx, cy], float))
            world.place(pi, nx, ny, nri)
            target[pi] = 0.5 * tgt + 0.5 * np.array([nx, ny], float)  # legalized continuous state
            if (nx, ny, nri) == (cx, cy, ri):
                continue
            if accept:
                # descent on the network cost: re-grow the part's nets, keep the move if the
                # tubes got cheaper (volume of its nets + overflow everywhere)
                nets = [n for n in kit.part_nets([pi]) if n in sl.occ_n]
                before = sl.local_cost(nets)
                dphys = phys_w * ph.delta(pi, (nx, ny, nri)) if ph is not None else 0.0
                snap = sl.snapshot(nets)
                sl.iterate_nets(nets, k_local, rng)
                if sl.local_cost(nets) + dphys > before - 1e-6:
                    sl.restore(snap)
                    world.unplace(pi)
                    world.place(pi, cx, cy, ri)
                    target[pi] = np.array([cx, cy], float)
                    continue
            if ph is not None:
                ph.commit(pi)
            moved += 1
        sl.iterate(k_iter, rng)
        c, ov = sl.cost()
        c += pw()
        if c < best[0]:
            best = (c, dict(world.pose))
        log(f"  slime rd={rd} moved={moved} cost={c:.1f} overflow={ov:.2f} best={best[0]:.1f} "
            f"beta={sl.beta:.2f} hpwl={world.hpwl():.1f} t={clock.budget - clock.left():.1f}s")
        if moved == 0 and rd > 3:
            if accept and step_mm > 0.3:
                step_mm *= 0.6  # nothing accepted: shorter steps
                continue
            break
    if not restore:
        if ph is not None:
            ph.sync()
        return best[0]
    # restore the best placement by network cost
    for q in mov:
        world.unplace(q)
    for q in mov:
        world.place(q, *best[1][q])
    if ph is not None:
        ph.sync()
    return best[0]


# ---------------------------------------------------------------- methods
def _phys(world, log):
    """physics.Phys for the input board, or None (no terms / kae not importable)."""
    path = world.data.get("path") or next((a for a in sys.argv if a.endswith(".kicad_pcb")), None)
    try:
        from physics import Phys
        ph = Phys(world, path)
        ph.sync()
    except Exception as e:  # noqa: BLE001 - physics is optional
        log(f"  physics unavailable: {e}")
        return None
    log(f"  physics parts {len(ph.active)} total {ph.total():.2f}")
    return ph if ph.active else None


def _seq_place(world, kit, rng, clock, log):
    place_mechanical(world, kit, log)
    greedy_place(world, kit, growth_order(world, kit, rng), log)
    descent(world, kit, log, clock=clock)


def slime(world, seed=0, budget=120, log=print, move=True, prior=True, lam=0.2, gc_mm=0.5,
          frac=0.55, w_press=1.0, step_mm=1.5, final_iter=25, dil=1, thr=0.3, accept=True,
          phys=False, phys_w=2.0, start="seq", restore=True, **kw):
    rng = random.Random(seed)
    clock = Clock(budget)
    _place_fixed(world)
    r0 = Router(world)
    kit = Kit(world, r0)
    _seq_place(world, kit, rng, clock, log)
    ph = None
    if phys or start == "seq_phys":
        ph = _phys(world, log)
    if ph is not None and start == "seq_phys":
        from methods_phys import descent_phys
        descent_phys(world, kit, ph, phys_w, log, clock=clock)
    log(f"  start placement hpwl={world.hpwl():.1f}" + (f" phys={ph.total():.2f}" if ph else ""))
    if not phys:
        ph = None
    sl = Slime(world, gc_mm=gc_mm)
    log(f"  slime grid {sl.L}x{sl.Hc}x{sl.Wc} cell={sl.gc:.2f} mm nets={len(sl.nets)}")
    if move:
        motion(world, kit, sl, clock, rng, log, frac=frac, w_press=w_press, step_mm=step_mm, accept=accept,
               ph=ph, phys_w=phys_w, restore=restore)
    pri = {}
    if prior:
        # converge the network on the final placement, then turn tubes into corridors
        sl.hist_rate = 0.1
        sl.iterate(final_iter, rng)
        c, ov = sl.cost()
        log(f"  slime final cost={c:.1f} overflow={ov:.2f} beta={sl.beta:.2f}")
        pri = {n: sl.prior(n, lam=lam, thr=thr, dil=dil) for n in sl.nets if n in sl.occ_n}
    r = PriorRouter(world, prior=pri)
    r.pathfinder(log=log, iters=40)
    if ph is not None:
        world.phys = ph
    log(f"slime move={move} prior={prior} phys={phys} {r.stats()} hpwl={world.hpwl():.1f}"
        + (f" phys={ph.total():.2f}" if ph else ""))
    return r


def slime_motion(world, seed=0, budget=120, log=print, **kw):
    return slime(world, seed=seed, budget=budget, log=log, move=True, prior=False, **kw)


def slime_prior(world, seed=0, budget=120, log=print, **kw):
    return slime(world, seed=seed, budget=budget, log=log, move=False, prior=True, **kw)


def slime_phys(world, seed=0, budget=120, log=print, **kw):
    """seq start + slime motion with the physics force/term, plain PathFinder."""
    return slime(world, seed=seed, budget=budget, log=log, move=True, prior=False, phys=True, **kw)


def slime_phys2(world, seed=0, budget=120, log=print, **kw):
    """seq_phys start (HPWL + physics descent) + slime motion with the physics term."""
    return slime(world, seed=seed, budget=budget, log=log, move=True, prior=False, phys=True,
                 start="seq_phys", **kw)
