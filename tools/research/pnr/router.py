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
import os
import time
from collections import defaultdict

import numpy as np
from numba import njit

from raster import stamp_disc_path

INF = 1e18
SQ2 = math.sqrt(2.0)
STOP = None  # run.py: a callable that is true past the run's CPU deadline (anytime.budget_stop)

# PNR_FAST: comma list of the fast-router changes. Default (unset): D,L,K,B,R,J with
# PNR_STALL=8, measured on two placed boards and pnr seq / jc; "none" routes exactly as the
# original router (keen-wright db10e58); "all" turns on every change:
#   A  pathfinder reroutes only the nets in conflict after its first pass
#   B  pathfinder stops when conflicts + unrouted have not improved for STALL passes
#   C  a failed connection widens its box step by step (x3 margin, then the full grid once per
#      net and pass), instead of retrying the full grid every time
#   D  multi-pin nets connect the terminal nearest to the tree, searching from the tree cells
#      near it, instead of from the whole tree to every remaining terminal
#   K  a net whose tree cannot reach its remaining terminals continues as a forest: a new
#      tree starts at one of them and only that break counts as unrouted (not all of them)
#   R  pathfinder legalizes the best pass seen (fewest conflicted nets, then unrouted), not the last
#   J  legalize drops only a conflicted net's conflicting connections and reconnects the
#      pieces left (pins plus kept paths) in hard mode, instead of rerouting the whole net
#      and dropping all of it when that fails
#   L  hard-mode searches (legalize) do not retry on the full grid: with foreign copper
#      forbidden they rarely succeed there, and each failure floods the whole board
DEFAULT_FAST = "D,L,K,B,R,J"
_F = os.environ.get("PNR_FAST", DEFAULT_FAST).strip()
FAST = (set("ABCDJKLR") if _F.lower() == "all" else set() if _F.lower() in ("", "none")
        else {c.strip().upper() for c in _F.split(",") if c.strip()})
STALL = int(os.environ.get("PNR_STALL", "8"))
# Work counters for every router in the process (run.py writes them to pnr_summary.json):
# A* expansions and calls, by outcome and by why the search ran.
PROF = defaultdict(float)


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
          gcost, parent, visit, hk, hv, path_out, stats):
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
        stats[0] += 1
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
        self.ast = np.zeros(1, np.int64)
        self.phase = "other"  # why route_net runs: pf0 (first pass), pfN (later passes), legal, other
        self.full_tried = set()  # C: nets that used their one full-grid retry in this pass

    def _astar(self, src, sid, bx0, by0, bx1, by1, tcent, hard, pres, net, kind):
        w = self.w
        self.ast[0] = 0
        t0 = time.perf_counter()
        n = astar(w.nl, w.H, w.W, w.blockT, w.blockV, w.DT, w.DV, w.occT, w.occV, net, w.hist,
                  pres, hard, src, self.tgt, sid, bx0, by0, bx1, by1, self.via_cost,
                  self.dir_pen, tcent, self.gcost, self.parent, self.visit, self.hk, self.hv,
                  self.path_buf, self.ast)
        e = int(self.ast[0])
        dt = time.perf_counter() - t0
        out = "ok" if n >= 0 else "fail"
        for key in (f"{kind}.{out}", f"phase.{self.phase}", f"all"):
            PROF["exp." + key] += e
            PROF["calls." + key] += 1
            PROF["s." + key] += dt
        fan = len(w.net_pins[net])
        PROF[f"exp.fanout.{'2' if fan <= 2 else '3-7' if fan < 8 else '8+'}"] += e
        PROF["exp.src_cells"] += len(src)
        return n

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
        terms = [w.terminal_array(pi, k).astype(np.int32) for pi, k in pins]
        terms += getattr(w, "shape_terms", {}).get(net, [])  # the net's board copper drawings
        terms = [t[(t[:, 1] >= 0) & (t[:, 2] >= 0) & (t[:, 1] < w.H) & (t[:, 2] < w.W)] for t in terms]
        # start from the pin closest to the pins' centroid
        cents = np.array([t[:, 1:].mean(0) if len(t) else (0, 0) for t in terms])
        start = int(np.argmin(((cents - cents.mean(0)) ** 2).sum(1)))
        paths, failed = self._grow(net, terms, cents, start, hard, pres)
        self.routes[net] = paths
        if failed:
            self.unrouted[net] = failed
        return failed

    def _grow(self, net, terms, cents, start, hard, pres):
        """Prim-style tree from terms[start] to every other non-empty terms[i] (cell arrays:
        pins, or whole pieces of copper). Stamps the new paths; returns (paths, failed)."""
        w = self.w
        tree = [terms[start]]
        remaining = [i for i in range(len(terms)) if i != start and len(terms[i])]
        paths = []
        failed = 0
        H, W = w.H, w.W
        m = self.margin
        while remaining:
            src_all = np.concatenate(tree)
            n, hit = -1, None
            if "D" in FAST and len(remaining) > 1 and len(src_all):
                # the remaining terminal nearest to the tree, from the tree cells near it (a start
                # pin wholly off the grid leaves the tree empty: the plain search then fails as before)
                ty, tx = src_all[:, 1], src_all[:, 2]
                dmin = [int(np.min(np.maximum(np.abs(ty - cents[i][0]), np.abs(tx - cents[i][1]))))
                        for i in remaining]
                k = int(np.argmin(dmin))
                tgt_i, d = remaining[k], dmin[k]
                near = np.maximum(np.abs(ty - cents[tgt_i][0]), np.abs(tx - cents[tgt_i][1])) <= 2 * d + m
                n, hit = self._search(net, src_all[near], [tgt_i], terms, cents, hard, pres, m, "near")
            if n < 0:
                n, hit = self._search(net, src_all, remaining, terms, cents, hard, pres, m, "box")
            if n < 0 and m < max(H, W) and not (hard and "L" in FAST):
                if "C" in FAST:
                    n, hit = self._search(net, src_all, remaining, terms, cents, hard, pres, 3 * m + 10, "box3")
                    if n < 0 and (net, self.phase) not in self.full_tried:
                        self.full_tried.add((net, self.phase))
                        n, hit = self._search(net, src_all, remaining, terms, cents, hard, pres, None, "full")
                else:
                    n, hit = self._search(net, src_all, remaining, terms, cents, hard, pres, None, "full")
            if n < 0:
                if "K" in FAST and len(remaining) > 1:
                    # a forest: restart from the remaining terminal nearest the tree's start
                    k = min(remaining, key=lambda i: ((cents[i] - cents[start]) ** 2).sum())
                    failed += 1
                    tree.append(terms[k])
                    remaining.remove(k)
                    continue
                failed += len(remaining)
                break
            path = self.path_buf[:n].copy()
            paths.append(path)
            self._stamp(net, path, 1)
            tree.append(path)
            tree.append(terms[hit])
            remaining.remove(hit)
        return paths, failed

    def _search(self, net, src, targets, terms, cents, hard, pres, margin, kind):
        """One A* from src to any of `targets` within the box of everything plus `margin`
        (None: the full grid). Returns (path length or -1, the terminal index hit)."""
        w = self.w
        H, W = w.H, w.W
        self.sid += 1
        sid = self.sid
        tc = []
        for i in targets:
            t = terms[i]
            self.tgt[(t[:, 0] * H + t[:, 1]) * W + t[:, 2]] = sid
            tc.append(cents[i][::-1])  # (x, y)
        tcent = np.array(tc, np.float64)
        if margin is None:
            bx0, by0, bx1, by1 = 0, 0, W - 1, H - 1
        else:
            allp = np.concatenate([src[:, 1:], np.concatenate([terms[i][:, 1:] for i in targets])])
            by0, bx0 = allp.min(0) - margin
            by1, bx1 = allp.max(0) + margin
            bx0, by0 = max(0, bx0), max(0, by0)
            bx1, by1 = min(W - 1, bx1), min(H - 1, by1)
        n = self._astar(src, sid, bx0, by0, bx1, by1, tcent, hard, pres, net, kind)
        if n < 0:
            return -1, None
        end = self.path_buf[n - 1]
        for i in targets:
            t = terms[i]
            if np.any((t[:, 0] == end[0]) & (t[:, 1] == end[1]) & (t[:, 2] == end[2])):
                return n, i
        return -1, None

    def net_conflicts(self, net):
        w = self.w
        return sum(conflicts(p, net, w.DT, w.occT, w.DV, w.occV, w.nl) for p in self.routes.get(net, []))

    def pathfinder(self, nets=None, iters=30, pres0=0.5, pres_mul=1.6, order=None, log=None,
                   finalize=True):
        """Negotiated congestion over `nets` (default: all). Existing routes of other nets
        stay as they are and are priced like any other copper. PNR_FAST A: after the first
        pass only conflicted nets are rerouted; B: stop after STALL passes without progress."""
        w = self.w
        nets = list(nets if nets is not None else w.net_pins)
        if order is not None:
            nets = order(nets)
        self.pres = pres0
        todo = nets
        best, since = None, 0
        snap, snap_score = None, None  # R: the best pass's routes
        for it in range(iters):
            self.phase = "pf0" if it == 0 else "pfN"
            self.full_tried = set()
            for n in todo:
                self.rip(n)
                self.route_net(n)
            PROF["pf.passes"] += 1
            PROF["pf.nets_routed"] += len(todo)
            bad = [n for n in nets if self.net_conflicts(n)]
            unr = sum(self.unrouted.values())
            if "R" in FAST and (snap_score is None or (len(bad), unr) < snap_score):
                snap_score = (len(bad), unr)
                snap = ({n: list(self.routes.get(n, [])) for n in nets},
                        {n: self.unrouted[n] for n in nets if n in self.unrouted})
            if log:
                log(f"  pf it={it} pres={self.pres:.2f} conflicted={len(bad)} "
                    f"unrouted={unr} routed_this_pass={len(todo)}")
            if not bad:
                break
            if STOP is not None and STOP():
                break
            for n in bad:
                for p in self.routes[n]:
                    add_hist(p, n, w.DT, w.occT, w.hist, self.hist_inc)
            self.pres *= pres_mul
            if "B" in FAST:
                score = (len(bad), unr)
                if best is None or score < best:
                    best, since = score, 0
                else:
                    since += 1
                    if since >= STALL:
                        PROF["pf.stalled"] += 1
                        break
            todo = bad if "A" in FAST else nets
        if snap is not None and snap_score < (len(bad), unr):
            PROF["pf.restored_best"] += 1
            for n in nets:
                self.rip(n)
            routes, unrouted = snap
            for n in nets:
                self.routes[n] = routes[n]
                for p in routes[n]:
                    self._stamp(n, p, 1)
                if n in unrouted:
                    self.unrouted[n] = unrouted[n]
        self.phase = "legal"
        if finalize:
            self.legalize(nets)
        self.phase = "other"

    def legalize(self, nets=None):
        """Make every route legal: re-route conflicted nets in hard mode, else drop them."""
        nets = list(nets if nets is not None else self.routes)
        if "J" in FAST:
            for _ in range(3):
                bad = [n for n in nets if self.net_conflicts(n)]
                if not bad:
                    break
                kept = {n: self._drop_conflicting(n) for n in bad}
                for n in bad:
                    self._reconnect(n, kept[n])
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

    def _drop_conflicting(self, net):
        """J: unstamp the net's paths that sit in foreign copper; returns the paths kept."""
        w = self.w
        kept = []
        for p in self.routes.get(net, []):
            if conflicts(p, net, w.DT, w.occT, w.DV, w.occV, w.nl):
                self._stamp(net, p, -1)
                PROF["legal.paths_dropped"] += 1
            else:
                kept.append(p)
        self.routes[net] = kept
        return kept

    def _reconnect(self, net, kept):
        """J: group the net's pins and kept paths into connected pieces (sharing a cell), then
        join the pieces in hard mode from the largest one. Unjoinable pieces count as unrouted."""
        w = self.w
        pins = [(pi, k) for pi, k in w.net_pins[net] if pi in w.pose]
        terms = [w.terminal_array(pi, k).astype(np.int32) for pi, k in pins]
        terms += getattr(w, "shape_terms", {}).get(net, [])
        terms = [t[(t[:, 1] >= 0) & (t[:, 2] >= 0) & (t[:, 1] < w.H) & (t[:, 2] < w.W)] for t in terms]
        items = [t for t in terms if len(t)] + list(kept)
        n_items = len(items)
        parent = list(range(n_items))

        def find(a):
            while parent[a] != a:
                parent[a] = parent[parent[a]]
                a = parent[a]
            return a

        owner = {}
        for i, it in enumerate(items):
            for c in map(tuple, it.tolist()):
                j = owner.setdefault(c, i)
                if j != i:
                    parent[find(i)] = find(j)
        groups = {}
        for i in range(n_items):
            groups.setdefault(find(i), []).append(i)
        pieces = [np.concatenate([items[i] for i in g]) for g in groups.values()]
        self.unrouted.pop(net, None)
        if len(pieces) < 2:
            return
        PROF["legal.reconnect_pieces"] += len(pieces) - 1
        cents = np.array([p[:, 1:].mean(0) for p in pieces])
        start = int(np.argmax([len(g) for g in groups.values()]))
        paths, failed = self._grow(net, pieces, cents, start, True, self.pres)
        self.routes[net] = list(kept) + paths
        if failed:
            self.unrouted[net] = failed
            PROF["legal.reconnect_failed"] += failed

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
