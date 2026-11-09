# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Ratsnest crossings: what HPWL cannot see, and a post-legalization pass that removes them.

Every signal net with 2..MAX_PINS pins is drawn as its minimum spanning tree over its pins (the
ratsnest); two segments of different nets that cross properly count one crossing. Two parallel
connections have the same bounding boxes crossed or not, so HPWL and RUDY are blind to it, while
a crossing is a real obligation: one of the two must change layer, and the vias take room on
every layer. On the 52 boards where our placement routed worse than the human's (kae staged vs
the bridge on the human placement) the nets left open had a median of 17 crossings against 8.5
at the human's placement of the same nets; E108 (213 boards, within board, seed pairs): crossings
rho +0.27 with opens, HPWL +0.01, RUDY flat.

`Crossings(P, view)` keeps the nets' segments in a uniform grid; `view` exposes nx, ny (pin
lists per net) and frozen (nets left out). `trial(nets)` is the change if the touched nets take
their current pins; `commit()` / `revert()` close it, as Congestion's trial does.

`untangle(P, st, ...)` is the pass: after legalization it tries the moves that keep every grid
rectangle and so legality: swaps of parts with the same shape_key, half turns of parts whose
rectangles a half turn leaves unchanged. A move is taken when it removes crossings, costs at
most `x_mm` of weighted HPWL per crossing removed, and does not worsen physics (`terms`), the
parts' zone cost (`zones`). Parts in `hold` (labelled, protection-order, zone-pinned) stay.
"""
from __future__ import annotations

import math
import time

from .state import grid_violations

MAX_PINS = 12


def _mst(xs, ys):
    n = len(xs)
    if n < 2:
        return []
    if n == 2:
        return [(xs[0], ys[0], xs[1], ys[1])]
    in_tree = [False] * n
    in_tree[0] = True
    d = [math.hypot(xs[k] - xs[0], ys[k] - ys[0]) for k in range(n)]
    par = [0] * n
    out = []
    for _ in range(n - 1):
        j, best = -1, math.inf
        for k in range(n):
            if not in_tree[k] and d[k] < best:
                j, best = k, d[k]
        in_tree[j] = True
        out.append((xs[par[j]], ys[par[j]], xs[j], ys[j]))
        for k in range(n):
            if not in_tree[k]:
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
    def __init__(self, P, view, cell=None):
        self.view = view
        x0, y0, x1, y1 = P.outline.bounds
        self.x0, self.y0 = x0, y0
        self.c = cell or max(1.0, max(x1 - x0, y1 - y0) / 24.0)
        self.nets = {net.i for net in P.nets
                     if net.kind == "signal" and 2 <= len(net.pins) <= MAX_PINS and net.i not in view.frozen}
        self.seg = {}          # net -> [segments]
        self.cells = {}        # cell -> set(nets)
        self.ncells = {}       # net -> [cells]
        for j in self.nets:
            self._set(j, _mst(view.nx[j], view.ny[j]))
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
        view = self.view
        T = [j for j in nets if j in self.nets]
        if not T:
            self.pending = None
            return 0
        Ts = set(T)
        new = {j: _mst(view.nx[j], view.ny[j]) for j in T}
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


def swap_pairs(P, st, hold=(), per_part=8):
    """Interchangeable pairs (equal shape_key) to try: each part with its nearest `per_part`
    same-shape parts, so a footprint used a hundred times on a dense board is still covered
    (a swap between far-apart parts pays in HPWL and would be refused anyway)."""
    groups = {}
    for i in P.mov:
        if i not in hold:
            groups.setdefault(P.parts[i].shape_key, []).append(i)
    pairs = set()
    for g in groups.values():
        if len(g) < 2:
            continue
        centers = {i: (int(st.X[i]), int(st.Y[i])) for i in g}
        for a in g:
            ax, ay = centers[a]
            near = sorted((b for b in g if b != a),
                          key=lambda b: ((centers[b][0] - ax) ** 2 + (centers[b][1] - ay) ** 2, b))[:per_part]
            pairs.update((min(a, b), max(a, b)) for b in near)
    return sorted(pairs)


def half_turn(p, k0):
    """(rotation index of a half turn of part p from k0, whether it keeps every grid rectangle),
    or None for a part with no half turn. A footprint not centred on its origin moves its
    rectangles by a cell or so: the turn is still a candidate, checked for legality."""
    if len(p.rots) < 4 or not hasattr(p, "turn"):
        return None
    k1 = p.turn[k0][2]
    if k1 == k0:
        return None
    r0, r1 = p.rots[k0], p.rots[k1]
    same = r0.g_own == r1.g_own and r0.g_board == r1.g_board
    # the same rectangles in another order (a half turn swaps which pad's rectangle comes first)
    for a, b in ((r0.g_own_rects, r1.g_own_rects), (r0.g_opp, r1.g_opp), (r0.g_boards, r1.g_boards)):
        if sorted(tuple(x) for x in (a or ())) != sorted(tuple(x) for x in (b or ())):
            same = False
    return k1, same


def untangle(P, st, terms=None, zones=None, hold=(), x_mm=2.0, max_sweeps=8, time_s=20.0, log=None):
    """Greedy pass after legalization (module docstring). Sweeps the moves until a sweep takes
    none, `max_sweeps` or `time_s` ends it. Returns a report."""
    t_end = time.monotonic() + time_s
    hold = set(hold)
    pins = _Pins(P, st)
    pins.frozen = {net.i for net in P.nets if net.kind in ("ground", "power") and len(net.pins) > 40}
    xc = Crossings(P, pins)
    start = xc.total
    hp0 = hp = st.hpwl()
    tparts = set(terms.parts()) if terms is not None else set()
    uuid = {p.i: p.uuid for p in P.parts}
    poses = {p.uuid: st.pose(p.i) for p in P.parts} if terms is not None else None
    swaps = swap_pairs(P, st, hold)
    turns = [i for i in P.mov if i not in hold]
    moved = dict(swap=0, turn=0)
    sweeps = 0
    timed_out = False

    def physics_ok(parts):
        changed = [uuid[q] for q in parts if uuid[q] in tparts]
        if not changed:
            return True, 0.0
        new = {uuid[q]: st.pose(q) for q in parts if uuid[q] in tparts}
        d = terms.delta(poses, changed, new)
        return d <= 1e-9, d

    def zone_cost(parts):
        if zones is None:
            return 0.0
        return sum(zones.part(q, int(st.X[q]), int(st.Y[q]), int(st.K[q])) for q in parts)

    def attempt(parts, apply, undo, check_grid=False):
        nonlocal hp
        z0 = zone_cost(parts)
        apply()
        nets = set()
        for q in parts:
            nets |= pins.refresh(q)
        d = xc.trial(nets)
        ok = False
        hp1 = hp
        if d < 0:
            hp1 = st.hpwl()
            ok = hp1 - hp <= x_mm * (-d) and zone_cost(parts) <= z0 + 1e-9
            if ok and check_grid:
                ok = not grid_violations(st)
            if ok and terms is not None:
                ok = physics_ok(parts)[0]
        if ok:
            xc.commit()
            hp = hp1
            if poses is not None:
                for q in parts:
                    poses[uuid[q]] = st.pose(q)
            return True
        xc.revert()
        undo()
        for q in parts:
            pins.refresh(q)
        return False

    improved = True
    while improved and sweeps < max_sweeps:
        improved = False
        sweeps += 1
        for (a, b) in swaps:
            if time.monotonic() > t_end:
                timed_out = True
                break
            old = (st.X[a], st.Y[a], st.K[a], st.X[b], st.Y[b], st.K[b])

            def apply_swap():
                st.X[a], st.Y[a], st.K[a], st.X[b], st.Y[b], st.K[b] = old[3], old[4], old[5], old[0], old[1], old[2]

            def undo_swap():
                st.X[a], st.Y[a], st.K[a], st.X[b], st.Y[b], st.K[b] = old
            if attempt((a, b), apply_swap, undo_swap):
                moved["swap"] += 1
                improved = True
        for i in turns:
            if timed_out or time.monotonic() > t_end:
                timed_out = True
                break
            k0 = int(st.K[i])
            ht = half_turn(P.parts[i], k0)
            if ht is None:
                continue
            k1, same = ht

            def apply_turn():
                st.K[i] = k1

            def undo_turn():
                st.K[i] = k0
            if attempt((i,), apply_turn, undo_turn, check_grid=not same):
                moved["turn"] += 1
                improved = True
        if timed_out:
            break
    rep = dict(crossings=start, after=xc.total, swaps=moved["swap"], turns=moved["turn"], sweeps=sweeps,
               hpwl_before=round(hp0, 3), hpwl_after=round(hp, 3), candidates=dict(swaps=len(swaps), turns=len(turns)),
               timed_out=timed_out)
    if log:
        log(f"untangle: ratsnest crossings {start} -> {xc.total} ({moved['swap']} swaps, {moved['turn']} half turns, "
            f"HPWL {hp0:.1f} -> {hp:.1f})")
    return rep
