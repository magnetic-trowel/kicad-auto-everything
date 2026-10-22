# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Joint vs sequential placement + routing on small synthetic boards (proof of concept).

What it computes
  Instances come from ../solver-bench/pcbgen.py (same footprints, mounting-hole and antenna keep-outs,
  decaps with an L1 <= 3 mm rule), plus:
    * k "hot loops": IC VIN pin -> C0603 pin 1, C0603 pin 2 -> adjacent IC GND pin (two 2-pin nets);
    * one 2x5 header fixed at the bottom edge (a boundary condition the optimizer may not move).
  Router: 2-layer grid at 0.5 mm pitch, node capacity 1, SMD pads block the top layer, THT pads both,
  via cost VIA cells. Every arm is scored by the same referee: PathFinder (VPR-like schedule) routing the
  final placement from scratch.

  Routed objective used to rank everything (mm-equivalent):
    J = wirelength + VIA_MM*vias + W_BOT*bottom-layer length + W_LOOP*hot-loop area (mm^2)
        + W_FAIL*failed nets + W_ILLEGAL*(overlaps + keep-out intrusions + decap violations)
  where a net "fails" if the referee leaves it unrouted or sharing a node with another net. The bottom
  layer is meant to stay a solid ground plane, so bottom copper is "plane-cut length" (a return-path
  physics term), and the hot-loop area counts 1.5 mm of vertical extent per mm of loop on the bottom.
  Plan-view loop area is a 2-layer, far-plane simplification; with a plane within ~0.2 mm, loop
  inductance follows height x squares (sum of mu0*h*dl/w) or the MS2 proxy instead
  (docs/topics/physics/solver-ladder.md).

  Arms (B = TP + TJ seconds of process CPU time for all but `seq` and `seqx`; budgets use CPU time so that
  a busy machine does not change the comparison):
    seq       SA on HPWL + straight-line hot-loop area proxy for TP s, then referee
    seqx      as seq plus a net-crossing proxy (--w-cross mm per crossing of star-decomposed nets; default
              0.5, the best of {0.5, 1.5, 3} on held-out seed 9); informational, same TP budget
    seq_long  the seq SA for B s, then referee
    seq_port  `seq`, then more (seq SA for TP s with a new seed + referee) until B s are used; best J
    joint     seq's placement + its referee routes as warm start, then SA for TJ s. Moves that create an
              overlap or keep-out intrusion are rejected before routing (hard); legal moves rip up and
              A*-re-route the affected nets (nets on moved parts plus nets crossing the new pads) and are
              accepted on the routed objective (+ an overflow penalty; decap violations priced as in J);
              then referee from scratch.
    joint_nophys  ablation: as joint but the optimizer ignores hot-loop area and bottom-layer length.
    long_joint    seq_long's placement (B s), then TJ s of joint SA (total B + TJ); optional
    seq_longer    control for long_joint: seq SA for B + TJ s; optional

How to run (Python 3.11+, numpy, shapely, scipy; imports ../solver-bench/pcbgen.py):
  python jpr_joint_vs_sequential.py --n 30 --seed 0 --util 0.6 --tp 10 --tj 40
  python jpr_joint_vs_sequential.py --n 50 --seed 1 --util 0.6 --arms seq,joint
  python jpr_joint_vs_sequential.py --n 30 --seed 0 --util 0.6 --tp 3 --proxy-study 40
Prints one JSON line per arm. Deterministic for a given seed except for CPU-time budgets (SA move
counts depend on machine speed). Results: docs/topics/physics/joint-place-route-experiment.md.
"""
import argparse
import heapq
import json
import math
import os
import random
import sys
import time

import numpy as np
from shapely import make_valid
from shapely.geometry import Polygon

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "solver-bench"))
from pcbgen import make_instance  # noqa: E402

G = 0.5            # grid pitch, mm (= track + clearance)
VIA = 4            # via cost in grid steps for the router (2 mm)
VIA_MM = 2.0       # via weight in J, mm-equivalent
W_BOT = 1.0        # extra cost per mm of bottom-layer copper (cuts the ground plane); also used by the router
W_ILLEGAL = 100.0  # per overlap / keep-out intrusion / decap violation in the final placement
W_LOOP = 4.0       # hot-loop area weight, mm per mm^2
W_FAIL = 40.0      # failed-net weight in J, mm
H_DIEL = 1.5       # top-to-bottom copper spacing of the 2-layer board, mm (vertical extent of a loop)
IC_NAMES = ("QFN32", "TQFP64", "SOIC8")


def rot(fp, k):
    """(W, H, pin offsets) in grid cells for rotation k*90, offsets from the bottom-left corner."""
    w, h = (fp.w, fp.h) if k % 2 == 0 else (fp.h, fp.w)
    W, H = math.ceil(w / G), math.ceil(h / G)
    out = []
    for (dx, dy) in fp.pins:
        rx, ry = [(dx, dy), (-dy, dx), (-dx, -dy), (dy, -dx)][k]
        out.append((math.floor(W / 2 + rx / G + 0.5), math.floor(H / 2 + ry / G + 0.5)))
    return W, H, out


def build_instance(n, seed, util, n_hot):
    inst = make_instance(n, seed=seed, util=util)
    rnd = random.Random(seed + 1000)
    comps = inst.comps
    used = {(c, p) for net in inst.nets for (c, p) in net} | {(d[0], 1) for d in inst.decaps}
    ics = [c for c in comps if c.fp.name in IC_NAMES]
    decap_ids = {d[0] for d in inst.decaps}
    caps = sorted((c for c in comps if c.fp.name in ("C0603", "C0402", "R0402") and c.id not in decap_ids),
                  key=lambda c: (c.fp.name != "C0603", c.id))
    hot = []
    for ic in ics[:n_hot]:
        if not caps:
            break
        cap = min(caps, key=lambda c: (c.fp.name != "C0603", c.cluster != ic.cluster, c.id))
        caps.remove(cap)
        npins = len(ic.fp.pins)
        cand = [(p, q) for p in range(npins) for q in range(npins) if p != q and (ic.id, p) not in used
                and (ic.id, q) not in used and abs(ic.fp.pins[p][0] - ic.fp.pins[q][0]) + abs(ic.fp.pins[p][1] - ic.fp.pins[q][1]) < 1.6]
        if not cand:
            continue
        vin, gnd = rnd.choice(cand)
        nets = []
        for net in inst.nets:   # free the cap's pins
            net = [t for t in net if t[0] != cap.id]
            if len(net) >= 2:
                nets.append(net)
        inst.nets = nets
        inst.nets.append([(ic.id, vin), (cap.id, 0)])
        inst.nets.append([(cap.id, 1), (ic.id, gnd)])
        used |= {(ic.id, vin), (ic.id, gnd), (cap.id, 0), (cap.id, 1)}
        hot.append((len(inst.nets) - 2, len(inst.nets) - 1, ic.id, vin, cap.id, gnd))
    inst.hot = hot
    return inst


class Board:
    def __init__(self, inst):
        self.inst = inst
        self.nx, self.ny = math.floor(inst.board_w / G), math.floor(inst.board_h / G)
        self.NN = self.nx * self.ny * 2
        self.N = len(inst.comps)
        self.dims = [[rot(c.fp, k) for k in range(4)] for c in inst.comps]
        self.tht = [c.fp.tht for c in inst.comps]
        self.nets = inst.nets
        self.M = len(self.nets)
        self.pin_net = {}
        for ni, net in enumerate(self.nets):
            for t in net:
                self.pin_net[t] = ni
        self.nets_of = [sorted({ni for ni, net in enumerate(self.nets) for (c, _) in net if c == i}) for i in range(self.N)]
        self.dec_of = [[] for _ in range(self.N)]
        for di, d in enumerate(inst.decaps):
            self.dec_of[d[0]].append(di); self.dec_of[d[2]].append(di)
        self.hot = inst.hot
        self.hot_of_net = {}
        for hi, h in enumerate(self.hot):
            self.hot_of_net[h[0]] = hi; self.hot_of_net[h[1]] = hi
        self.KO = [(math.floor(kx / G), math.floor(ky / G), math.ceil((kx + kw) / G), math.ceil((ky + kh) / G))
                   for (kx, ky, kw, kh) in inst.keepouts]
        # fixed connector: first header, bottom edge, centred
        self.fixed = {}
        for c in inst.comps:
            if c.fp.name == "HDR2x5":
                W, H, _ = self.dims[c.id][0]
                self.fixed[c.id] = ((self.nx - W) // 2, 0, 0)
                break

    def xmax(self, i, k):
        return self.nx - 1 - self.dims[i][k][0]

    def ymax(self, i, k):
        return self.ny - 1 - self.dims[i][k][1]


class State:
    """Placement (X, Y, K) + pads + routes + incremental cost terms."""

    def __init__(self, b, X, Y, K):
        self.b = b
        self.X, self.Y, self.K = list(X), list(Y), list(K)
        nx, ny = b.nx, b.ny
        self.padnet = [-1] * b.NN     # -1 free, >=0 owning net, -2 pad of an unconnected pin / conflict
        self.padcnt = [0] * b.NN
        self.occ = [0] * b.NN
        self.hist = [0.0] * b.NN
        self.ovf = 0
        self.rnodes = [set() for _ in range(b.M)]
        self.rlen = [0] * b.M
        self.rvia = [0] * b.M
        self.rbot = [0] * b.M
        self.rpath = [None] * b.M
        self.routed = [False] * b.M
        for i in range(b.N):
            self.add_pads(i)
        self.nxny = nx * ny

    # ---------- geometry ----------
    def pin_xy(self, c, p):
        o = self.b.dims[c][self.K[c]][2][p]
        return self.X[c] + o[0], self.Y[c] + o[1]

    def pad_nodes(self, i):
        b = self.b
        out = []
        for p, (ox, oy) in enumerate(b.dims[i][self.K[i]][2]):
            n0 = (self.Y[i] + oy) * b.nx + self.X[i] + ox
            out.append((p, n0))
            if b.tht[i]:
                out.append((p, n0 + b.nx * b.ny))
        return out

    def add_pads(self, i):
        for p, v in self.pad_nodes(i):
            ni = self.b.pin_net.get((i, p), -2)
            self.padcnt[v] += 1
            self.padnet[v] = ni if self.padcnt[v] == 1 else -2

    def del_pads(self, i):
        for p, v in self.pad_nodes(i):
            self.padcnt[v] -= 1
            if self.padcnt[v] == 0:
                self.padnet[v] = -1
            # padcnt > 0 after removal: leave as -2 (blocked); recomputed exactly by refresh_pad()
        for p, v in self.pad_nodes(i):
            if self.padcnt[v] > 0:
                self.refresh_pad(v)

    def refresh_pad(self, v):
        owners = []
        b = self.b
        for i in range(b.N):
            for p, u in self.pad_nodes(i):
                if u == v:
                    owners.append(b.pin_net.get((i, p), -2))
        self.padnet[v] = owners[0] if len(owners) == 1 else (-2 if owners else -1)

    def pin_nodes(self, ni):
        b = self.b
        out = []
        for (c, p) in b.nets[ni]:
            x, y = self.pin_xy(c, p)
            n0 = y * b.nx + x
            out.append([n0, n0 + b.nx * b.ny] if b.tht[c] else [n0])
        return out

    # ---------- placement penalties ----------
    def rect(self, i):
        W, H, _ = self.b.dims[i][self.K[i]]
        return self.X[i], self.Y[i], self.X[i] + W, self.Y[i] + H

    def pen_one(self, i, skip=()):
        x0, y0, x1, y1 = self.rect(i)
        s = 0.0
        for j in range(self.b.N):
            if j == i or j in skip:
                continue
            a0, b0, a1, b1 = self.rect(j)
            ox = min(x1, a1) - max(x0, a0)
            if ox > 0:
                oy = min(y1, b1) - max(y0, b0)
                if oy > 0:
                    s += ox * oy
        for (k0, l0, k1, l1) in self.b.KO:
            ox = min(x1, k1) - max(x0, k0); oy = min(y1, l1) - max(y0, l0)
            if ox > 0 and oy > 0:
                s += ox * oy
        return s

    def dec_ex(self, di):
        cc, cp, ic, ip, dmax = self.b.inst.decaps[di]
        (ax, ay), (bx, by) = self.pin_xy(cc, cp), self.pin_xy(ic, ip)
        return max(0, abs(ax - bx) + abs(ay - by) - math.floor(dmax / G))

    def pen_local(self, ids):
        s = sum(self.pen_one(i, skip=ids[:k]) for k, i in enumerate(ids))
        decs = {d for i in ids for d in self.b.dec_of[i]}
        return s + 3.0 * sum(self.dec_ex(d) for d in decs)

    def pen_total(self):
        return sum(self.pen_one(i, skip=range(i)) for i in range(self.b.N)) + 3.0 * sum(
            self.dec_ex(d) for d in range(len(self.b.inst.decaps)))

    def legality(self):
        b = self.b
        ov = sum(1 for i in range(b.N) for j in range(i + 1, b.N)
                 if (lambda r, s: min(r[2], s[2]) > max(r[0], s[0]) and min(r[3], s[3]) > max(r[1], s[1]))(self.rect(i), self.rect(j)))
        ko = sum(1 for i in range(b.N) for (k0, l0, k1, l1) in b.KO
                 if min(self.rect(i)[2], k1) > max(self.rect(i)[0], k0) and min(self.rect(i)[3], l1) > max(self.rect(i)[1], l0))
        dv = sum(1 for d in range(len(b.inst.decaps)) if self.dec_ex(d) > 0)
        return dict(overlaps=ov, keepout=ko, decap_viol=dv)

    # ---------- proxies ----------
    def net_hpwl(self, ni):
        xs, ys = zip(*(self.pin_xy(c, p) for (c, p) in self.b.nets[ni]))
        return (max(xs) - min(xs) + max(ys) - min(ys)) * G

    def loop_proxy(self, hi):
        _, _, ic, vin, cap, gnd = self.b.hot[hi]
        pts = [self.pin_xy(ic, vin), self.pin_xy(cap, 0), self.pin_xy(cap, 1), self.pin_xy(ic, gnd)]
        return loop_area(pts) * G * G

    def loop_routed(self, hi):
        n1, n2, ic, vin, cap, gnd = self.b.hot[hi]
        if not (self.routed[n1] and self.routed[n2]):
            return self.loop_proxy(hi) + 10.0
        nx, nxny = self.b.nx, self.b.nx * self.b.ny
        path = self.rpath[n1] + self.rpath[n2]
        pts = [(v % nx, (v // nx) % self.b.ny) for v in path]
        bottom = sum(1 for a, c in zip(path, path[1:]) if a >= nxny and c >= nxny)
        return loop_area(pts) * G * G + H_DIEL * bottom * G

    # ---------- routing ----------
    def occ_add(self, ni, sign):
        occ = self.occ
        for v in self.rnodes[ni]:
            if sign > 0:
                if occ[v] >= 1:
                    self.ovf += 1
                occ[v] += 1
            else:
                occ[v] -= 1
                if occ[v] >= 1:
                    self.ovf -= 1

    def route(self, ni, pres, use_hist, margin=6):
        """Route net ni (tree growth by multi-source A*). Sets rnodes/rlen/rvia/rpath/routed. occ not touched."""
        b = self.b
        nx, ny, nxny = b.nx, b.ny, b.nx * b.ny
        pins = self.pin_nodes(ni)
        xs = [v % nx for pn in pins for v in pn]; ys = [(v // nx) % ny for pn in pins for v in pn]
        for attempt in (0, 1):
            m = margin if attempt == 0 else max(nx, ny)
            wx0, wx1 = max(0, min(xs) - m), min(nx - 1, max(xs) + m)
            wy0, wy1 = max(0, min(ys) - m), min(ny - 1, max(ys) + m)
            tree = set(pins[0])
            pad_set = {v for pn in pins for v in pn}
            ln, nv, nb_, path_out = 0, 0, 0, None
            ok = True
            remaining = [list(pn) for pn in pins[1:]]
            while remaining:
                tgt = {}
                for k, pn in enumerate(remaining):
                    for v in pn:
                        tgt[v] = k
                res = self._astar(tree, tgt, ni, pres, use_hist, wx0, wx1, wy0, wy1)
                if res is None:
                    ok = False
                    break
                path, k = res
                for a, c in zip(path, path[1:]):
                    if a // nxny != c // nxny:
                        nv += 1
                    else:
                        ln += 1
                        if a >= nxny:
                            nb_ += 1
                tree.update(path)
                remaining.pop(k)
                if len(pins) == 2:
                    path_out = path
            if ok:
                self.rnodes[ni] = {v for v in tree if v not in pad_set}
                self.rlen[ni], self.rvia[ni], self.rpath[ni], self.routed[ni] = ln, nv, path_out, True
                self.rbot[ni] = nb_
                return True
        self.rnodes[ni] = set(); self.rlen[ni] = 0; self.rvia[ni] = 0; self.rpath[ni] = None; self.routed[ni] = False
        self.rbot[ni] = 0
        return False

    def _astar(self, sources, tgt, ni, pres, use_hist, wx0, wx1, wy0, wy1):
        b = self.b
        nx, ny, nxny = b.nx, b.ny, b.nx * b.ny
        occ, padnet, hist = self.occ, self.padnet, self.hist
        txy = [(v % nx, (v // nx) % ny) for v in tgt]
        if len(txy) == 1:
            tx, ty = txy[0]
            h = lambda x, y: abs(x - tx) + abs(y - ty)
        else:
            h = lambda x, y: min(abs(x - a) + abs(y - c) for a, c in txy)
        gs = {}
        prev = {}
        pq = []
        for s in sources:
            gs[s] = 0.0
            x = s % nx; y = (s // nx) % ny
            heapq.heappush(pq, (h(x, y), 0.0, s))
            prev[s] = -1
        done = set()
        while pq:
            f, gu, u = heapq.heappop(pq)
            if u in done:
                continue
            if u in tgt:
                path = [u]
                while prev[path[-1]] != -1:
                    path.append(prev[path[-1]])
                path.reverse()
                return path, tgt[u]
            done.add(u)
            l = u // nxny; r = u - l * nxny; y = r // nx; x = r - y * nx
            nb = []
            bc = 1.0 if l == 0 else 1.0 + W_BOT
            if x > wx0: nb.append((u - 1, x - 1, y, bc))
            if x < wx1: nb.append((u + 1, x + 1, y, bc))
            if y > wy0: nb.append((u - nx, x, y - 1, bc))
            if y < wy1: nb.append((u + nx, x, y + 1, bc))
            nb.append((u + nxny if l == 0 else u - nxny, x, y, VIA))
            for v, vx, vy, base in nb:
                pv = padnet[v]
                if pv != -1 and pv != ni:
                    continue
                if v in done:
                    continue
                c = base
                if use_hist:
                    c = base * (1.0 + hist[v]) * (1.0 + pres * occ[v])
                elif occ[v]:
                    c = base + pres * occ[v]
                ng = gu + c
                if ng < gs.get(v, 1e18):
                    gs[v] = ng; prev[v] = u
                    heapq.heappush(pq, (ng + h(vx, vy), ng, v))
        return None

    def rip(self, ni):
        self.occ_add(ni, -1)
        self.rnodes[ni] = set(); self.routed[ni] = False

    def referee(self, iters=40):
        """PathFinder from scratch on the current placement."""
        b = self.b
        for ni in range(b.M):
            if self.rnodes[ni]:
                self.occ_add(ni, -1)
            self.rnodes[ni] = set(); self.routed[ni] = False
        self.hist = [0.0] * b.NN
        order = sorted(range(b.M), key=lambda ni: (self.net_hpwl(ni), ni))
        pres = 0.0
        it = 0
        for it in range(iters):
            for ni in order:
                if it > 0 and self.routed[ni] and not any(self.occ[v] > 1 for v in self.rnodes[ni]):
                    continue
                if self.rnodes[ni]:
                    self.occ_add(ni, -1)
                self.route(ni, pres, True, margin=6 + 2 * it)
                self.occ_add(ni, +1)
            if self.ovf == 0:
                break
            for v in range(b.NN):
                if self.occ[v] > 1:
                    self.hist[v] += 1.0
            pres = 0.5 if it == 0 else min(pres * 1.3, 1000.0)
        return it + 1

    def score(self):
        b = self.b
        fail = [ni for ni in range(b.M) if not self.routed[ni] or any(self.occ[v] > 1 for v in self.rnodes[ni])]
        wl = sum(self.rlen) * G
        vias = sum(self.rvia)
        loop = sum(self.loop_routed(hi) for hi in range(len(b.hot)))
        bot = sum(self.rbot) * G
        J = wl + VIA_MM * vias + W_BOT * bot + W_LOOP * loop + W_FAIL * len(fail)
        return dict(J=round(J, 1), completion=round(1 - len(fail) / b.M, 4), failed_nets=len(fail),
                    overused_nodes=sum(1 for v in range(b.NN) if self.occ[v] > 1), wirelength_mm=round(wl, 1),
                    vias=vias, bottom_mm=round(bot, 1), hot_loop_mm2=round(loop, 2), hpwl_mm=round(sum(self.net_hpwl(n) for n in range(b.M)), 1))


def loop_area(pts):
    """Enclosed area of a closed, possibly self-intersecting polyline (lobes add, they do not cancel)."""
    if len(pts) < 3:
        return 0.0
    return make_valid(Polygon(pts)).area


def random_placement(b, rnd):
    X, Y, K = [], [], []
    for i in range(b.N):
        if i in b.fixed:
            x, y, k = b.fixed[i]
        else:
            k = rnd.randrange(4); x = rnd.randint(0, b.xmax(i, k)); y = rnd.randint(0, b.ymax(i, k))
        X.append(x); Y.append(y); K.append(k)
    return X, Y, K


def propose(b, s, rnd, rad, movable):
    """Returns (ids, new poses) or None. Parts stay inside the board (hard domain constraint)."""
    r = rnd.random()
    i = rnd.choice(movable)
    if r < 0.7:
        k = s.K[i]
        x = min(max(0, s.X[i] + rnd.randint(-rad, rad)), b.xmax(i, k))
        y = min(max(0, s.Y[i] + rnd.randint(-rad, rad)), b.ymax(i, k))
        return (i,), [(x, y, k)]
    if r < 0.85:
        k = rnd.randrange(4)
        return (i,), [(min(s.X[i], b.xmax(i, k)), min(s.Y[i], b.ymax(i, k)), k)]
    j = rnd.choice(movable)
    if i == j:
        return None
    pi = (min(s.X[j], b.xmax(i, s.K[i])), min(s.Y[j], b.ymax(i, s.K[i])), s.K[i])
    pj = (min(s.X[i], b.xmax(j, s.K[j])), min(s.Y[i], b.ymax(j, s.K[j])), s.K[j])
    return (i, j), [pi, pj]


def sa_hpwl(b, X, Y, K, secs, seed, w_loop=W_LOOP, w_cross=0.0):
    """Sequential arm: SA on HPWL + loop-area proxy (+ optional net-crossing proxy, Cypress-style, counted
    on a star decomposition of each net) + penalties. Pads/routes are not maintained."""
    rnd = random.Random(seed)
    s = State(b, X, Y, K)
    movable = [i for i in range(b.N) if i not in b.fixed]
    hot_of = [[hi for hi, h in enumerate(b.hot) if i in (h[2], h[4])] for i in range(b.N)]
    segs = [(ni, net[0], t) for ni, net in enumerate(b.nets) for t in net[1:]]
    seg_net = np.array([sg[0] for sg in segs])
    segs_of = [[k for k, sg in enumerate(segs) if sg[0] in set(b.nets_of[i])] for i in range(b.N)]

    P = np.array([s.pin_xy(*sg[1]) + s.pin_xy(*sg[2]) for sg in segs], dtype=float)

    def refresh(ids):
        if w_cross:
            for k in {k for i in ids for k in segs_of[i]}:
                P[k] = s.pin_xy(*segs[k][1]) + s.pin_xy(*segs[k][2])

    def crossings(ids):
        mine = sorted({k for i in ids for k in segs_of[i]})
        if not mine or w_cross == 0:
            return 0
        A, Bq = P[mine][:, None, :], P[None, :, :]

        def orient(px, py, qx, qy, rx, ry):
            return np.sign((qx - px) * (ry - py) - (qy - py) * (rx - px))
        o1 = orient(A[..., 0], A[..., 1], A[..., 2], A[..., 3], Bq[..., 0], Bq[..., 1])
        o2 = orient(A[..., 0], A[..., 1], A[..., 2], A[..., 3], Bq[..., 2], Bq[..., 3])
        o3 = orient(Bq[..., 0], Bq[..., 1], Bq[..., 2], Bq[..., 3], A[..., 0], A[..., 1])
        o4 = orient(Bq[..., 0], Bq[..., 1], Bq[..., 2], Bq[..., 3], A[..., 2], A[..., 3])
        x = (o1 * o2 < 0) & (o3 * o4 < 0) & (seg_net[mine][:, None] != seg_net[None, :])
        inmine = np.zeros(len(segs), bool); inmine[mine] = True
        # pairs with both segments in `mine` are seen twice
        return int(x[:, ~inmine].sum() + x[:, inmine].sum() // 2)

    def local(ids):
        nets = {n for i in ids for n in b.nets_of[i]}
        hots = {h for i in ids for h in hot_of[i]}
        c = sum(s.net_hpwl(n) for n in nets) + w_loop * sum(s.loop_proxy(h) for h in hots)
        return c + w_cross * crossings(ids), s.pen_local(ids)

    t0 = time.process_time(); T0, T1 = b.nx * 0.25, 0.02
    moves = 0
    while True:
        frac = (time.process_time() - t0) / secs
        if frac >= 1:
            break
        T = T0 * (T1 / T0) ** frac
        lam = 0.5 * (4000.0 / 0.5) ** frac
        rad = max(1, int(b.nx * 0.3 * (1 - frac) ** 2))
        for _ in range(100):
            mv = propose(b, s, rnd, rad, movable)
            if mv is None:
                continue
            moves += 1
            ids, new = mv
            c0, p0 = local(ids)
            old = [(s.X[i], s.Y[i], s.K[i]) for i in ids]
            for i, (x, y, k) in zip(ids, new):
                s.X[i], s.Y[i], s.K[i] = x, y, k
            refresh(ids)
            c1, p1 = local(ids)
            d = (c1 - c0) + lam * G * G * (p1 - p0)
            if not (d <= 0 or rnd.random() < math.exp(-d / T)):
                for i, (x, y, k) in zip(ids, old):
                    s.X[i], s.Y[i], s.K[i] = x, y, k
                refresh(ids)
    repair(b, s)
    return s.X, s.Y, s.K, moves


def repair(b, s, sweeps=4):
    """Greedy legalizer, same for every arm: each part that overlaps another part or a keep-out moves to the
    nearest overlap-free pose (spiral search, 4 rotations), choosing by decap excess, then HPWL."""
    movable = [i for i in range(b.N) if i not in b.fixed]
    for _ in range(sweeps):
        bad = [i for i in movable if s.pen_one(i) > 0]
        if not bad:
            break
        for i in bad:
            if s.pen_one(i) == 0:
                continue
            x0, y0, k0 = s.X[i], s.Y[i], s.K[i]
            best = None
            for r in range(1, max(b.nx, b.ny)):
                for k in range(4):
                    for dx in range(-r, r + 1):
                        for dy in (-r, r) if abs(dx) < r else range(-r, r + 1):
                            x, y = x0 + dx, y0 + dy
                            if not (0 <= x <= b.xmax(i, k) and 0 <= y <= b.ymax(i, k)):
                                continue
                            s.X[i], s.Y[i], s.K[i] = x, y, k
                            if s.pen_one(i) == 0:
                                dec = sum(s.dec_ex(d) for d in b.dec_of[i])
                                c = (dec, sum(s.net_hpwl(n) for n in b.nets_of[i]) + 0.01 * (abs(dx) + abs(dy)))
                                if best is None or c < best[0]:
                                    best = (c, x, y, k)
                if best is not None and (best[0][0] == 0 or r > 8):
                    break
            if best is None:
                s.X[i], s.Y[i], s.K[i] = x0, y0, k0
            else:
                s.X[i], s.Y[i], s.K[i] = best[1:]


def sa_joint(b, X, Y, K, secs, seed, w_loop=W_LOOP, bottom_cost=True):
    """Joint arm: SA whose moves rip up and re-route affected nets; cost = routed objective.
    Overlaps and keep-out intrusions are hard: such moves are rejected before any routing (the start is
    legal after `repair`). Decap violations are priced as in J (W_ILLEGAL each, plus 1 mm per cell of
    excess). w_loop=0, bottom_cost=False gives the `joint_nophys` ablation (routed length + vias +
    overflow only; the router's own A* costs are unchanged)."""
    wbot = W_BOT if bottom_cost else 0.0
    rnd = random.Random(seed + 7)
    s = State(b, X, Y, K)
    s.referee()                                   # warm start: negotiated routes of the start placement
    start = s.score()
    start.update(s.legality())

    def dec_cost(ids):
        ex = [s.dec_ex(d) for d in {d for i in ids for d in b.dec_of[i]}]
        return W_ILLEGAL * sum(1 for e in ex if e > 0) + G * sum(ex)
    movable = [i for i in range(b.N) if i not in b.fixed]
    hot_of = [[hi for hi, h in enumerate(b.hot) if i in (h[2], h[4])] for i in range(b.N)]

    def net_cost(n):
        return (s.rlen[n] * G + VIA_MM * s.rvia[n] + wbot * s.rbot[n] * G) if s.routed[n] else W_FAIL

    t0 = time.process_time()
    T0, T1 = 3.0, 0.02
    moves = acc = routed_moves = 0
    reroutes = 0
    while True:
        frac = (time.process_time() - t0) / secs
        if frac >= 1:
            break
        T = T0 * (T1 / T0) ** frac
        w_ovf = 2.0 * (40.0 / 2.0) ** frac            # overflow weight (mm per overused node)
        pres = 1.0 + 9.0 * frac                       # router's present-congestion cost (steps per sharer)
        rad = max(1, int(6 * (1 - frac)) + 1)
        mv = propose(b, s, rnd, rad, movable)
        if mv is None:
            continue
        moves += 1
        ids, new = mv
        old = [(s.X[i], s.Y[i], s.K[i]) for i in ids]
        p0 = dec_cost(ids)
        for i, (x, y, k) in zip(ids, new):
            s.X[i], s.Y[i], s.K[i] = x, y, k
        geo = sum(s.pen_one(i, skip=ids[:k]) for k, i in enumerate(ids))
        p1 = dec_cost(ids)
        for i, (x, y, k) in zip(ids, old):
            s.X[i], s.Y[i], s.K[i] = x, y, k
        if geo > 0:                                   # hard: no overlaps or keep-out intrusions
            continue
        routed_moves += 1
        hots = {h for i in ids for h in hot_of[i]}
        for i in ids:
            s.del_pads(i)
        for i, (x, y, k) in zip(ids, new):
            s.X[i], s.Y[i], s.K[i] = x, y, k
        for i in ids:
            s.add_pads(i)
        newpads = {v for i in ids for _, v in s.pad_nodes(i)}
        aff = {n for i in ids for n in b.nets_of[i]}
        for n in range(b.M):
            if n not in aff and s.rnodes[n] and not newpads.isdisjoint(s.rnodes[n]):
                aff.add(n)
        hots |= {b.hot_of_net[n] for n in aff if n in b.hot_of_net}
        aff = sorted(aff, key=lambda n: (s.net_hpwl(n), n))
        saved = {n: (s.rnodes[n], s.rlen[n], s.rvia[n], s.rpath[n], s.routed[n], s.rbot[n]) for n in aff}
        c0 = sum(net_cost(n) for n in aff) + w_loop * sum(s.loop_routed(h) for h in hots)
        ovf0 = s.ovf
        for n in aff:
            s.occ_add(n, -1)
        for n in aff:
            s.route(n, pres, False)
            s.occ_add(n, +1)
        reroutes += len(aff)
        c1 = sum(net_cost(n) for n in aff) + w_loop * sum(s.loop_routed(h) for h in hots)
        d = (c1 - c0) + w_ovf * (s.ovf - ovf0) + (p1 - p0)
        if d <= 0 or rnd.random() < math.exp(-d / T):
            acc += 1
            continue
        for n in aff:
            s.occ_add(n, -1)
        for i in ids:
            s.del_pads(i)
        for i, (x, y, k) in zip(ids, old):
            s.X[i], s.Y[i], s.K[i] = x, y, k
        for i in ids:
            s.add_pads(i)
        for n in aff:
            s.rnodes[n], s.rlen[n], s.rvia[n], s.rpath[n], s.routed[n], s.rbot[n] = saved[n]
            s.occ_add(n, +1)
    own = s.score()                               # the joint optimizer's own maintained routes
    own.update(s.legality())
    own["routed_moves"] = routed_moves
    own["start_J_routes"] = start["J"]            # the start placement's referee J (before illegal terms)
    own["start_legality"] = {k: start[k] for k in ("overlaps", "keepout", "decap_viol")}
    repair(b, s)                                  # no-op unless the start was illegal
    return s.X, s.Y, s.K, moves, acc, reroutes, own


def evaluate(b, X, Y, K):
    s = State(b, X, Y, K)
    t = time.process_time()
    iters = s.referee()
    out = s.score()
    leg = s.legality()
    out.update(leg)
    out["J"] = round(out["J"] + W_ILLEGAL * sum(leg.values()), 1)
    out.update(route_s=round(time.process_time() - t, 2), pf_iters=iters)
    return out


def proxy_study(b, k_place, tp):
    """How well do placement proxies rank routed outcomes? K placements of varying quality (SA from random
    starts with 0.3-1.0 x tp CPU-s), each routed by the referee; Spearman rho of proxy vs routed value, and
    how often two placements within 3% HPWL differ by more than 10% in routed J."""
    from scipy.stats import spearmanr
    rows = []
    for k in range(k_place):
        X0, Y0, K0 = random_placement(b, random.Random(1000 + k))
        X, Y, K, _ = sa_hpwl(b, X0, Y0, K0, tp * (0.3 + 0.7 * (k % 4) / 3), 1000 + k)
        s = State(b, X, Y, K)
        leg = s.legality()
        if leg["overlaps"] + leg["keepout"]:
            continue
        segs = [(s.pin_xy(*net[0]), s.pin_xy(*t)) for net in b.nets for t in net[1:]]
        sn = [ni for ni, net in enumerate(b.nets) for t in net[1:]]
        orient = lambda p, q, r: (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
        cross = sum(1 for i in range(len(segs)) for j in range(i + 1, len(segs)) if sn[i] != sn[j]
                    and orient(*segs[i], segs[j][0]) * orient(*segs[i], segs[j][1]) < 0
                    and orient(*segs[j], segs[i][0]) * orient(*segs[j], segs[i][1]) < 0)
        hp = sum(s.net_hpwl(i) for i in range(b.M))
        lp = sum(s.loop_proxy(h) for h in range(len(b.hot)))
        s.referee()
        sc = s.score()
        rows.append(dict(hpwl=hp, cross=cross, loop_proxy=lp, J=sc["J"], wl=sc["wirelength_mm"], vias=sc["vias"],
                         loop=sc["hot_loop_mm2"]))
    rho = lambda x, y: round(float(spearmanr([r[x] for r in rows], [r[y] for r in rows]).correlation), 3)
    pairs = [(a_, c_) for i, a_ in enumerate(rows) for c_ in rows[i + 1:]
             if abs(a_["hpwl"] - c_["hpwl"]) / min(a_["hpwl"], c_["hpwl"]) < 0.03]
    return dict(placements=len(rows), rho_hpwl_J=rho("hpwl", "J"), rho_hpwl_wl=rho("hpwl", "wl"),
                rho_cross_J=rho("cross", "J"), rho_cross_vias=rho("cross", "vias"),
                rho_loopproxy_loop=rho("loop_proxy", "loop") if b.hot else None,
                near_equal_hpwl_pairs=len(pairs),
                pairs_J_differs_gt10pct=sum(1 for a_, c_ in pairs if abs(a_["J"] - c_["J"]) / min(a_["J"], c_["J"]) > 0.10))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=30); ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--util", type=float, default=0.5); ap.add_argument("--hot", type=int, default=3)
    ap.add_argument("--tp", type=float, default=10.0); ap.add_argument("--tj", type=float, default=50.0)
    ap.add_argument("--w-cross", type=float, default=0.5)   # tuned on seed 9 (held out)
    ap.add_argument("--arms", default="seq,seqx,seq_long,seq_port,joint,joint_nophys")
    ap.add_argument("--proxy-study", type=int, default=0, help="K placements: proxy-vs-routed study, then exit")
    a = ap.parse_args()
    inst = build_instance(a.n, a.seed, a.util, a.hot)
    b = Board(inst)
    if a.proxy_study:
        print(json.dumps(dict(n=a.n, seed=a.seed, util=a.util, hot_loops=len(b.hot), study="proxy",
                              **proxy_study(b, a.proxy_study, a.tp))), flush=True)
        return
    arms = a.arms.split(",")
    B = a.tp + a.tj
    meta = dict(n=a.n, seed=a.seed, util=a.util, nets=b.M, hot_loops=len(b.hot), grid=[b.nx, b.ny, 2],
                board_mm=inst.meta["board_mm"], tp=a.tp, tj=a.tj)
    X0, Y0, K0 = random_placement(b, random.Random(a.seed))
    wx = a.w_cross

    def report(arm, X, Y, K, wall, **extra):
        r = evaluate(b, X, Y, K)
        print(json.dumps(dict(meta, arm=arm, cpu_s=round(wall + r["route_s"], 1), **extra, **r)), flush=True)

    t = time.process_time()
    Xs, Ys, Ks, mv = sa_hpwl(b, X0, Y0, K0, a.tp, a.seed)
    t_seq = time.process_time() - t
    if "seq" in arms:
        report("seq", Xs, Ys, Ks, t_seq, sa_moves=mv)
    if "seqx" in arms:
        t = time.process_time()
        X, Y, K, mvx = sa_hpwl(b, X0, Y0, K0, a.tp, a.seed, w_cross=wx)
        report("seqx", X, Y, K, time.process_time() - t, sa_moves=mvx)
    if "seq_long" in arms or "long_joint" in arms:
        t = time.process_time()
        Xl, Yl, Kl, mv2 = sa_hpwl(b, X0, Y0, K0, B, a.seed)
        t_long = time.process_time() - t
        if "seq_long" in arms:
            report("seq_long", Xl, Yl, Kl, t_long, sa_moves=mv2)
        if "long_joint" in arms:   # converged sequential placement, then TJ s of joint SA (total B + TJ)
            t = time.process_time()
            X, Y, K, mvj, acc, rr, own = sa_joint(b, Xl, Yl, Kl, a.tj, a.seed)
            report("long_joint", X, Y, K, t_long + time.process_time() - t, joint_moves=mvj, accepted=acc,
                   reroutes=rr, own_routes=own)
    if "seq_longer" in arms:       # control for long_joint: seq SA for B + TJ s
        t = time.process_time()
        X, Y, K, mv3 = sa_hpwl(b, X0, Y0, K0, B + a.tj, a.seed)
        report("seq_longer", X, Y, K, time.process_time() - t, sa_moves=mv3)
    if "seq_port" in arms:   # restart 0 repeats `seq` (same start and seed); then new seeds until B CPU-s
        t = time.process_time(); best = None; k = 0
        while time.process_time() - t < B:
            sd = a.seed if k == 0 else a.seed * 100 + k
            Xr, Yr, Kr = (X0, Y0, K0) if k == 0 else random_placement(b, random.Random(sd))
            X, Y, K, _ = sa_hpwl(b, Xr, Yr, Kr, a.tp, sd)
            r = evaluate(b, X, Y, K)
            k += 1
            if best is None or r["J"] < best["J"]:
                best = r
        print(json.dumps(dict(meta, arm="seq_port", cpu_s=round(time.process_time() - t, 1), restarts=k, **best)), flush=True)
    for arm, wl, wb in (("joint", W_LOOP, True), ("joint_nophys", 0.0, False)):
        if arm in arms:
            t = time.process_time()
            X, Y, K, mvj, acc, rr, own = sa_joint(b, Xs, Ys, Ks, a.tj, a.seed, w_loop=wl, bottom_cost=wb)
            report(arm, X, Y, K, t_seq + time.process_time() - t, joint_moves=mvj, accepted=acc, reroutes=rr, own_routes=own)


if __name__ == "__main__":
    main()
