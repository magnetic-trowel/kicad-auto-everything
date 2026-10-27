# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Negotiated-congestion (PathFinder) router on the halo grid.

Cell cost for net n entering (l, y, x):
    inf                                   if static block, or hard mode and foreign > 0
    (1 + hist) * (1 + pres * foreign)     otherwise
with foreign = D[l,y,x] - (occ[n,l,y,x] > 0). Vias cost via_cost times the same factor
summed over layers. Multi-pin nets grow a tree Prim-style: multi-source A* from the
tree to the nearest unconnected pad.
"""
import math

import numpy as np
from numba import njit

from raster import stamp_disc_path

INF = 1e18
SQ2 = math.sqrt(2.0)
STOP = None  # run.py: a callable that is true past the run's CPU deadline (anytime.budget_stop)


@njit(cache=True)
def _push(hk, hv, n, k, v):
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
def _pop(hk, hv, n):
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
def astar(nl, H, W, blockT, blockV, DT, DV, occT, occV, net, hist, pres, hard,
          src, tgt_mark, sid, bx0, by0, bx1, by1, via_cost, dir_pen, tcent,
          gcost, parent, visit, hk, hv, path_out):
    """Multi-source / multi-target A*. Returns path length written to path_out (cells
    l,y,x from source to target) or -1. tgt_mark[node] == sid marks targets."""
    HW = H * W
    nh = 0
    sid_v = sid
    for i in range(src.shape[0]):
        l, y, x = src[i, 0], src[i, 1], src[i, 2]
        node = (l * H + y) * W + x
        visit[node] = sid_v
        gcost[node] = 0.0
        parent[node] = -1
        h = 0.0
        best = 1e30
        for t in range(tcent.shape[0]):
            dx = abs(tcent[t, 0] - x)
            dy = abs(tcent[t, 1] - y)
            d = max(dx, dy) + (SQ2 - 1) * min(dx, dy)
            if d < best:
                best = d
        h = best
        nh = _push(hk, hv, nh, h, node)
    dxs = (1, -1, 0, 0, 1, 1, -1, -1)
    dys = (0, 0, 1, -1, 1, -1, 1, -1)
    end = -1
    cap = hk.shape[0] - 16
    while nh > 0:
        f, node, nh = _pop(hk, hv, nh)
        l = node // HW
        rem = node - l * HW
        y = rem // W
        x = rem - y * W
        gc = gcost[node]
        if tgt_mark[node] == sid_v:
            end = node
            break
        # stale entry check
        best = 1e30
        for t in range(tcent.shape[0]):
            dx = abs(tcent[t, 0] - x)
            dy = abs(tcent[t, 1] - y)
            d = max(dx, dy) + (SQ2 - 1) * min(dx, dy)
            if d < best:
                best = d
        if f > gc + best + 1e-6:
            continue
        for k in range(8):
            nx = x + dxs[k]
            ny = y + dys[k]
            if nx < bx0 or ny < by0 or nx > bx1 or ny > by1:
                continue
            if blockT[l, ny, nx]:
                continue
            fr = DT[l, ny, nx] - (1 if occT[net, l, ny, nx] > 0 else 0)
            if hard and fr > 0:
                continue
            step = 1.0 if k < 4 else SQ2
            if dir_pen > 0.0 and k < 4:
                horiz = k < 2
                if (l % 2 == 0) != horiz:
                    step *= 1.0 + dir_pen
            c = step * (1.0 + hist[l, ny, nx]) * (1.0 + pres * fr)
            nn = (l * H + ny) * W + nx
            ng = gc + c
            if visit[nn] != sid_v or ng < gcost[nn]:
                visit[nn] = sid_v
                gcost[nn] = ng
                parent[nn] = node
                best = 1e30
                for t in range(tcent.shape[0]):
                    dx = abs(tcent[t, 0] - nx)
                    dy = abs(tcent[t, 1] - ny)
                    d = max(dx, dy) + (SQ2 - 1) * min(dx, dy)
                    if d < best:
                        best = d
                if nh < cap:
                    nh = _push(hk, hv, nh, ng + best, nn)
        # vias: through-hole, to every other layer
        if nl > 1:
            ok = True
            fv = 0
            hsum = 0.0
            for ll in range(nl):
                if blockV[ll, y, x] or blockT[ll, y, x]:
                    ok = False
                    break
                fv += DV[ll, y, x] - (1 if occV[net, ll, y, x] > 0 else 0)
                fv += DT[ll, y, x] - (1 if occT[net, ll, y, x] > 0 else 0)
                hsum += hist[ll, y, x]
            if ok and not (hard and fv > 0):
                c = via_cost * (1.0 + hsum) * (1.0 + pres * fv)
                for ll in range(nl):
                    if ll == l:
                        continue
                    nn = (ll * H + y) * W + x
                    ng = gc + c
                    if visit[nn] != sid_v or ng < gcost[nn]:
                        visit[nn] = sid_v
                        gcost[nn] = ng
                        parent[nn] = node
                        if nh < cap:
                            nh = _push(hk, hv, nh, ng + (f - gc), nn)
    if end < 0:
        return -1
    # reconstruct
    n = 0
    node = end
    while node >= 0:
        l = node // HW
        rem = node - l * HW
        path_out[n, 0] = l
        path_out[n, 1] = rem // W
        path_out[n, 2] = rem - (rem // W) * W
        n += 1
        node = parent[node]
        if n >= path_out.shape[0]:
            return -1
    # reverse to source -> target
    for i in range(n // 2):
        for j in range(3):
            path_out[i, j], path_out[n - 1 - i, j] = path_out[n - 1 - i, j], path_out[i, j]
    return n


@njit(cache=True)
def conflicts(path, net, DT, occT, DV, occV, nl):
    """Number of path cells (and via cells) that sit in a foreign halo."""
    c = 0
    for i in range(path.shape[0]):
        l, y, x = path[i, 0], path[i, 1], path[i, 2]
        if DT[l, y, x] - (1 if occT[net, l, y, x] > 0 else 0) > 0:
            c += 1
        if i > 0 and path[i - 1, 0] != l and path[i - 1, 1] == y and path[i - 1, 2] == x:
            for ll in range(nl):
                if DV[ll, y, x] - (1 if occV[net, ll, y, x] > 0 else 0) > 0:
                    c += 1
    return c


@njit(cache=True)
def add_hist(path, net, DT, occT, hist, inc):
    for i in range(path.shape[0]):
        l, y, x = path[i, 0], path[i, 1], path[i, 2]
        if DT[l, y, x] - (1 if occT[net, l, y, x] > 0 else 0) > 0:
            hist[l, y, x] += inc


def vias_of(path):
    """(0, y, x) rows for every layer change in a path."""
    v = []
    for i in range(1, len(path)):
        if path[i, 0] != path[i - 1, 0]:
            v.append((0, path[i, 1], path[i, 2]))
    return np.array(v, np.int32).reshape(-1, 3)


class Router:
    def __init__(self, world, via_cost_mm=2.0, dir_pen=0.0, bbox_margin_mm=3.0):
        self.w = world
        L, H, W = world.nl, world.H, world.W
        n = L * H * W
        self.gcost = np.zeros(n, np.float64)
        self.parent = np.zeros(n, np.int64)
        self.visit = np.zeros(n, np.int32)
        self.tgt = np.zeros(n, np.int32)
        self.hk = np.zeros(8 * n + 64, np.float64)
        self.hv = np.zeros(8 * n + 64, np.int64)
        self.path_buf = np.zeros((n, 3), np.int32)
        self.sid = 0
        self.via_cost = via_cost_mm / world.g
        self.dir_pen = dir_pen
        self.margin = int(bbox_margin_mm / world.g)
        self.routes = {}  # net -> list of path arrays
        self.unrouted = {}  # net -> number of pins not reached
        self.pres = 0.0
        self.hist_inc = 0.3

    # ------------------------------------------------------------ stamping
    def _stamp(self, net, path, delta):
        w = self.w
        stamp_disc_path(w.occT, w.DT, net, path, w.offs_TT, delta, False, w.nl)
        stamp_disc_path(w.occV, w.DV, net, path, w.offs_TV, delta, False, w.nl)
        v = vias_of(path)
        if len(v):
            stamp_disc_path(w.occT, w.DT, net, v, w.offs_TV, delta, True, w.nl)
            stamp_disc_path(w.occV, w.DV, net, v, w.offs_VV, delta, True, w.nl)

    def rip(self, net):
        for p in self.routes.pop(net, []):
            self._stamp(net, p, -1)
        self.unrouted.pop(net, None)

    def rip_all(self):
        for n in list(self.routes):
            self.rip(n)

    # ------------------------------------------------------------ routing
    def route_net(self, net, hard=False, pres=None):
        """Route one net (must be ripped up). Pins of unplaced parts are skipped."""
        w = self.w
        pres = self.pres if pres is None else pres
        pins = [(pi, k) for pi, k in w.net_pins[net] if pi in w.pose]
        if len(pins) < 2:
            self.routes[net] = []
            return 0
        terms = [np.array(w.terminals(pi, k), np.int32).reshape(-1, 3) for pi, k in pins]
        terms += getattr(w, "shape_terms", {}).get(net, [])  # the net's board copper drawings
        terms = [t[(t[:, 1] >= 0) & (t[:, 2] >= 0) & (t[:, 1] < w.H) & (t[:, 2] < w.W)] for t in terms]
        # start from the pin closest to the pins' centroid
        cents = np.array([t[:, 1:].mean(0) if len(t) else (0, 0) for t in terms])
        start = int(np.argmin(((cents - cents.mean(0)) ** 2).sum(1)))
        tree = [terms[start]]
        remaining = [i for i in range(len(terms)) if i != start and len(terms[i])]
        paths = []
        failed = 0
        while remaining:
            self.sid += 1
            sid = self.sid
            src = np.concatenate(tree)
            tc = []
            H, W = w.H, w.W
            for i in remaining:
                t = terms[i]
                idx = (t[:, 0] * H + t[:, 1]) * W + t[:, 2]
                self.tgt[idx] = sid
                tc.append(cents[i][::-1])  # (x, y)
            tcent = np.array(tc, np.float64)
            allp = np.concatenate([src[:, 1:], np.concatenate([terms[i][:, 1:] for i in remaining])])
            m = self.margin
            by0, bx0 = allp.min(0) - m
            by1, bx1 = allp.max(0) + m
            bx0, by0 = max(0, bx0), max(0, by0)
            bx1, by1 = min(W - 1, bx1), min(H - 1, by1)
            n = astar(w.nl, H, W, w.blockT, w.blockV, w.DT, w.DV, w.occT, w.occV, net, w.hist,
                      pres, hard, src, self.tgt, sid, bx0, by0, bx1, by1, self.via_cost,
                      self.dir_pen, tcent, self.gcost, self.parent, self.visit, self.hk, self.hv,
                      self.path_buf)
            if n < 0 and m < max(H, W):
                # retry with the full grid
                self.sid += 1
                sid = self.sid
                for i in remaining:
                    t = terms[i]
                    self.tgt[(t[:, 0] * H + t[:, 1]) * W + t[:, 2]] = sid
                n = astar(w.nl, H, W, w.blockT, w.blockV, w.DT, w.DV, w.occT, w.occV, net, w.hist,
                          pres, hard, src, self.tgt, sid, 0, 0, W - 1, H - 1, self.via_cost,
                          self.dir_pen, tcent, self.gcost, self.parent, self.visit, self.hk,
                          self.hv, self.path_buf)
            if n < 0:
                failed += len(remaining)
                break
            path = self.path_buf[:n].copy()
            end = path[-1]
            hit = None
            for i in remaining:
                t = terms[i]
                if np.any((t[:, 0] == end[0]) & (t[:, 1] == end[1]) & (t[:, 2] == end[2])):
                    hit = i
                    break
            paths.append(path)
            self._stamp(net, path, 1)
            tree.append(path)
            tree.append(terms[hit])
            remaining.remove(hit)
        self.routes[net] = paths
        if failed:
            self.unrouted[net] = failed
        return failed

    def net_conflicts(self, net):
        w = self.w
        return sum(conflicts(p, net, w.DT, w.occT, w.DV, w.occV, w.nl) for p in self.routes.get(net, []))

    def pathfinder(self, nets=None, iters=30, pres0=0.5, pres_mul=1.6, order=None, log=None,
                   finalize=True):
        """Negotiated congestion over `nets` (default: all). Existing routes of other nets
        stay as they are and are priced like any other copper."""
        w = self.w
        nets = list(nets if nets is not None else w.net_pins)
        if order is not None:
            nets = order(nets)
        self.pres = pres0
        for it in range(iters):
            for n in nets:
                self.rip(n)
                self.route_net(n)
            bad = [n for n in nets if self.net_conflicts(n)]
            if log:
                log(f"  pf it={it} pres={self.pres:.2f} conflicted={len(bad)} "
                    f"unrouted={sum(self.unrouted.values())}")
            if not bad:
                break
            if STOP is not None and STOP():
                break
            for n in bad:
                for p in self.routes[n]:
                    add_hist(p, n, w.DT, w.occT, w.hist, self.hist_inc)
            self.pres *= pres_mul
        if finalize:
            self.legalize(nets)

    def legalize(self, nets=None):
        """Make every route legal: re-route conflicted nets in hard mode, else drop them."""
        nets = list(nets if nets is not None else self.routes)
        for _ in range(3):
            bad = [n for n in nets if self.net_conflicts(n)]
            if not bad:
                break
            for n in bad:
                self.rip(n)
            for n in bad:
                self.route_net(n, hard=True)
                if self.net_conflicts(n):
                    self.rip(n)
                    self.routes[n] = []
                    self.unrouted[n] = len(self.w.net_pins[n]) - 1 + len(getattr(self.w, "shape_terms", {}).get(n, []))

    # ------------------------------------------------------------ metrics
    def stats(self):
        w = self.w
        length = 0.0
        vias = 0
        for n, ps in self.routes.items():
            for p in ps:
                d = np.abs(np.diff(p, axis=0))
                same = d[:, 0] == 0
                length += float(np.sum(np.where((d[same, 1] + d[same, 2]) == 2, SQ2, 1.0))) * w.g
                vias += int((~same).sum())
        st = getattr(w, "shape_terms", {})
        total_conn = sum(len([1 for pi, k in pins if pi in w.pose]) - 1 + len(st.get(n, []))
                         for n, pins in w.net_pins.items())
        unr = sum(self.unrouted.values())
        return dict(length_mm=round(length, 2), vias=vias, unrouted=unr, connections=total_conn)

    # ------------------------------------------------------------ export
    def export(self):
        """Tracks and vias in board coordinates (mm)."""
        w = self.w
        tracks, vias = [], []
        R = w.R
        for net, paths in self.routes.items():
            name = w.net_names[net]
            junc = set()
            for p in paths:
                junc.add((int(p[0, 0]), int(p[0, 1]), int(p[0, 2])))
            for p in paths:
                segs = _segments(p, junc)
                for (l, y1, x1, y2, x2) in segs:
                    xa, ya = w.xy(x1, y1)
                    xb, yb = w.xy(x2, y2)
                    tracks.append(dict(net=name, layer=int(l), x1=xa, y1=ya, x2=xb, y2=yb, w=R.w))
                for i in range(1, len(p)):
                    if p[i, 0] != p[i - 1, 0]:
                        x, y = w.xy(p[i, 2], p[i, 1])
                        vias.append(dict(net=name, x=x, y=y, d=R.via_d, drill=R.via_drill))
        return tracks, vias


def _segments(p, junc):
    """Compress a cell path into straight segments, breaking at junction cells."""
    segs = []
    n = len(p)
    i = 0
    while i < n - 1:
        if p[i + 1, 0] != p[i, 0]:  # via
            i += 1
            continue
        l = p[i, 0]
        dy, dx = p[i + 1, 1] - p[i, 1], p[i + 1, 2] - p[i, 2]
        j = i + 1
        while (j + 1 < n and p[j + 1, 0] == l and p[j + 1, 1] - p[j, 1] == dy and p[j + 1, 2] - p[j, 2] == dx
               and (int(p[j, 0]), int(p[j, 1]), int(p[j, 2])) not in junc):
            j += 1
        segs.append((l, p[i, 1], p[i, 2], p[j, 1], p[j, 2]))
        i = j
    return segs
