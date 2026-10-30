# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Ratsnest crossings: a planarity term for the annealer.

Every signal net with 2..MAX_PINS pins is drawn as its minimum spanning tree over its pins
(the ratsnest); two segments of different nets that cross properly count one crossing. On the
52 boards where our placement routed worse than the human's (kae staged vs the bridge on the
human placement), the nets left open had a median of 17 crossings against 8.5 at the human's
placement of the same nets, and the board's crossings per ratsnest edge relative to the
human's separated those boards from the rest (AUC 0.70; HPWL alone does not see it: an
uncrossed and a crossed pair of parallel connections have the same bounding boxes).

`Crossings(ann)` keeps the segments of the annealer's nets (`ann.nx`, `ann.ny`) in a uniform
grid; `trial(nets)` returns the change in the crossing count if the touched nets take their
current pins, `commit()` / `revert()` as the congestion term.
"""
from __future__ import annotations

import math

MAX_PINS = 12


def _mst(xs, ys):
    n = len(xs)
    if n < 2:
        return []
    if n == 2:
        return [(xs[0], ys[0], xs[1], ys[1])]
    inT = [False] * n
    inT[0] = True
    d = [math.hypot(xs[k] - xs[0], ys[k] - ys[0]) for k in range(n)]
    par = [0] * n
    out = []
    for _ in range(n - 1):
        j, best = -1, math.inf
        for k in range(n):
            if not inT[k] and d[k] < best:
                j, best = k, d[k]
        inT[j] = True
        out.append((xs[par[j]], ys[par[j]], xs[j], ys[j]))
        for k in range(n):
            if not inT[k]:
                dk = math.hypot(xs[k] - xs[j], ys[k] - ys[j])
                if dk < d[k]:
                    d[k], par[k] = dk, j
    return out


def _cross(a, b):
    ax, ay, bx, by = a
    cx, cy, dx, dy = b

    def o(px, py, qx, qy, rx, ry):
        return (qx - px) * (ry - py) - (qy - py) * (rx - px)
    d1 = o(ax, ay, bx, by, cx, cy)
    d2 = o(ax, ay, bx, by, dx, dy)
    if d1 * d2 >= 0:
        return False
    d3 = o(cx, cy, dx, dy, ax, ay)
    d4 = o(cx, cy, dx, dy, bx, by)
    return d3 * d4 < 0


class Crossings:
    def __init__(self, P, ann, cell=None):
        self.ann = ann
        x0, y0, x1, y1 = P.outline.bounds
        self.x0, self.y0 = x0, y0
        self.c = cell or max(1.0, max(x1 - x0, y1 - y0) / 24.0)
        self.nets = {net.i for net in P.nets
                     if net.kind == "signal" and 2 <= len(net.pins) <= MAX_PINS and net.i not in ann.frozen}
        self.seg = {}          # net -> [segments]
        self.cells = {}        # cell -> set(nets)
        self.ncells = {}       # net -> [cells]
        for j in self.nets:
            self._set(j, _mst(ann.nx[j], ann.ny[j]))
        self.total = self.count_all()
        self.pending = None

    def _cells_of(self, segs):
        out = set()
        c, x0, y0 = self.c, self.x0, self.y0
        for (ax, ay, bx, by) in segs:
            i0, i1 = int((min(ax, bx) - x0) // c), int((max(ax, bx) - x0) // c)
            j0, j1 = int((min(ay, by) - y0) // c), int((max(ay, by) - y0) // c)
            for i in range(i0, i1 + 1):
                for j in range(j0, j1 + 1):
                    out.add((i, j))
        return out

    def _set(self, j, segs):
        for cl in self.ncells.get(j, ()):
            s = self.cells.get(cl)
            if s is not None:
                s.discard(j)
        cs = self._cells_of(segs)
        for cl in cs:
            self.cells.setdefault(cl, set()).add(j)
        self.ncells[j] = cs
        self.seg[j] = segs

    def _count(self, j, segs, cells, skip):
        """Crossings of net j's segments `segs` with every other net's current segments,
        nets in `skip` left out."""
        cand = set()
        for cl in cells:
            s = self.cells.get(cl)
            if s:
                cand |= s
        cand.discard(j)
        n = 0
        for k in cand:
            if k in skip:
                continue
            for b in self.seg[k]:
                for a in segs:
                    if _cross(a, b):
                        n += 1
        return n

    def count_all(self):
        n = 0
        for j in self.nets:
            n += self._count(j, self.seg[j], self.ncells[j], ())
        return n // 2

    def trial(self, nets):
        """Change in crossings if the touched nets take their current pins."""
        ann = self.ann
        T = [j for j in nets if j in self.nets]
        if not T:
            self.pending = None
            return 0
        Ts = set(T)
        new = {j: _mst(ann.nx[j], ann.ny[j]) for j in T}
        newc = {j: self._cells_of(new[j]) for j in T}
        d = 0
        for j in T:      # against nets that did not move
            d += self._count(j, new[j], newc[j], Ts) - self._count(j, self.seg[j], self.ncells[j], Ts)
        for a_i, j in enumerate(T):   # among the touched nets
            for k in T[a_i + 1:]:
                d += sum(_cross(a, b) for a in new[j] for b in new[k])
                d -= sum(_cross(a, b) for a in self.seg[j] for b in self.seg[k])
        self.pending = (new, d)
        return d

    def commit(self):
        if self.pending is None:
            return
        new, d = self.pending
        for j, segs in new.items():
            self._set(j, segs)
        self.total += d
        self.pending = None

    def revert(self):
        self.pending = None


class _Pins:
    """The annealer-like view Crossings reads (nx, ny, frozen) of a State."""

    def __init__(self, P, st):
        self.P, self.st = P, st
        self.frozen = set()
        self.nx, self.ny = [], []
        self.where = {}          # part -> [(net, slot, pad)]
        pos = {}
        for net in P.nets:
            xs, ys = [], []
            for (i, k) in net.pins:
                if i not in pos:
                    pos[i] = st.pins_xy(i)
                self.where.setdefault(i, []).append((net.i, len(xs), k))
                xs.append(float(pos[i][k][0]))
                ys.append(float(pos[i][k][1]))
            self.nx.append(xs)
            self.ny.append(ys)

    def refresh(self, i):
        q = self.st.pins_xy(i)
        nets = set()
        for (j, slot, k) in self.where.get(i, ()):
            self.nx[j][slot] = float(q[k][0])
            self.ny[j][slot] = float(q[k][1])
            nets.add(j)
        return nets


def untangle(P, st, time_s=10.0, wl_tol=0.002, log=None):
    """Greedy pass after legalization: swap interchangeable parts (equal shape_key, so the
    grid rectangles and legality do not change) and turn parts whose rectangles a half turn
    leaves unchanged, whenever that removes ratsnest crossings without lengthening the
    weighted HPWL by more than wl_tol of it. Returns a report."""
    import time
    t_end = time.monotonic() + time_s
    pins = _Pins(P, st)
    pins.frozen = {net.i for net in P.nets if net.kind in ("ground", "power") and len(net.pins) > 40}
    xc = Crossings(P, pins)
    start = xc.total
    hp = st.hpwl()
    groups = {}
    for i in P.mov:
        groups.setdefault(P.parts[i].shape_key, []).append(i)
    swaps = [(a, b) for g in groups.values() if 1 < len(g) <= 40 for x, a in enumerate(g) for b in g[x + 1:]]
    turns = []
    for i in P.mov:
        p = P.parts[i]
        if len(p.rots) < 4 or not hasattr(p, "turn"):
            continue
        turns.append(i)
    moved = dict(swap=0, turn=0)
    improved = True
    while improved and time.monotonic() < t_end:
        improved = False
        for kind, item in [("swap", s) for s in swaps] + [("turn", i) for i in turns]:
            if time.monotonic() > t_end:
                break
            if kind == "swap":
                a, b = item
                old = (st.X[a], st.Y[a], st.K[a], st.X[b], st.Y[b], st.K[b])
                st.X[a], st.Y[a], st.K[a], st.X[b], st.Y[b], st.K[b] = old[3], old[4], old[5], old[0], old[1], old[2]
                parts = (a, b)
            else:
                i = item
                p = P.parts[i]
                k0 = int(st.K[i])
                k1 = p.turn[k0][2]
                r0, r1 = p.rots[k0], p.rots[k1]
                if k1 == k0 or r0.g_own != r1.g_own or tuple(r0.g_own_rects or ()) != tuple(r1.g_own_rects or ()) \
                        or tuple(r0.g_opp) != tuple(r1.g_opp) or r0.g_board != r1.g_board:
                    continue
                old = (k0,)
                st.K[i] = k1
                parts = (i,)
            nets = set()
            for q in parts:
                nets |= pins.refresh(q)
            d = xc.trial(nets)
            hp1 = st.hpwl() if d < 0 else hp
            if d < 0 and hp1 <= hp * (1.0 + wl_tol):
                xc.commit()
                hp = hp1
                moved[kind] += 1
                improved = True
                continue
            xc.revert()
            if kind == "swap":
                st.X[a], st.Y[a], st.K[a], st.X[b], st.Y[b], st.K[b] = old
            else:
                st.K[i] = old[0]
            for q in parts:
                pins.refresh(q)
    rep = dict(crossings=start, after=xc.total, swaps=moved["swap"], turns=moved["turn"])
    if log:
        log(f"untangle: ratsnest crossings {start} -> {xc.total} ({moved['swap']} swaps, {moved['turn']} half turns)")
    return rep
