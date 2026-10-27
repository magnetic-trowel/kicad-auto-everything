# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""CP-SAT placement models on the problem grid (adapted from
tools/research/solver-bench/cpsat_place.py, hier_place.py and legalize_clusters.py).

An `Item` is what the model moves: one part, or a macro (parts at fixed offsets). Each item
has variants (rotation x internal layout); a variant lists, per member part, its offset from
the item origin and its rotation index. The model has, per item, origin variables X, Y and a
one-hot over variants:
- every member rectangle (own side, plus drilled pads and back courtyards on the other side)
  is an optional interval, present with the variants that put it there; identical
  rectangles of different variants share one interval;
- one NoOverlap2D per side holds them with the fixed obstacles (locked parts, keepouts,
  parts outside the window);
- the outline: the bounding box of a variant's `board` rectangles lies inside one of the
  problem's cover rectangles (Problem.cover), chosen by a one-hot when there are several.
Objective: L1 displacement from a start position, a rotation-change charge, and optionally
weighted half-perimeter wirelength over pins (pin offsets rounded to the grid).
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np
from ortools.sat.python import cp_model


@dataclass
class Item:
    members: list                 # part indices
    variants: list                # [ {part: (dx, dy, k)} ]
    X0: int = 0                   # start (grid) and start variant
    Y0: int = 0
    v0: int = 0
    weight: float = 1.0           # displacement weight
    name: str = ""
    bounds: tuple = None          # optional origin box (xlo, xhi, ylo, yhi), inclusive
    prefer: list = field(default_factory=list)   # optional per-variant extra cost (grid units)


def single(P, i, X0, Y0, k0=0, weight=1.0):
    """One part: its right-angle rotations, plus its current rotation when that is an odd
    angle (CP-SAT stays on the right angles; a part turned freely is repaired at its angle)."""
    p = P.parts[i]
    ks = list(range(getattr(p, "n_ortho", len(p.rots))))
    if k0 not in ks and 0 <= k0 < len(p.rots):
        ks.append(k0)
    vs = [{i: (0, 0, k)} for k in ks]
    return Item(members=[i], variants=vs, X0=X0, Y0=Y0, v0=ks.index(k0) if k0 in ks else 0, weight=weight,
                name=p.ref)


def _rects_of(P, item, v):
    """Per side: grid rectangles (a, b, c, d) relative to the item origin; and the board
    rectangles that must each lie inside the outline (a part that fits contributes its
    bounding box; one that does not, its pad groups)."""
    out = {0: [], 1: []}
    boards = []
    for i, (dx, dy, k) in item.variants[v].items():
        p = P.parts[i]
        r = p.rots[k]
        si = 0 if p.s > 0 else 1
        for (a, b, c, d) in (r.g_own_rects or (r.g_own,)):
            out[si].append((dx + a, dx + b, dy + c, dy + d))
        for (a, b, c, d) in r.g_opp:
            out[1 - si].append((dx + a, dx + b, dy + c, dy + d))
        for (a, b, c, d) in (r.g_boards or (r.g_board,)):
            boards.append((dx + a, dx + b, dy + c, dy + d))
    # one bounding box for the members that fit whole; the rest stay separate
    whole = [b for b in boards]
    if len(whole) > 1 and len(item.members) > 1:
        bb = (min(b[0] for b in whole), max(b[1] for b in whole), min(b[2] for b in whole), max(b[3] for b in whole))
        whole = [bb]
    # an item's own rectangles may overlap each other (drilled pads and a back courtyard):
    # NoOverlap2D needs them as disjoint pieces
    return {side: disjoint_union(rs) for side, rs in out.items()}, whole


def _boxes_one(P, bb):
    a, b, c, d = bb
    out = []
    for (i0, i1, j0, j1) in P.cover:
        xlo, xhi = i0 - a, i1 - b
        ylo, yhi = j0 - c, j1 - d
        if xlo <= xhi and ylo <= yhi:
            out.append((xlo, xhi, ylo, yhi))
    return out


def allowed_boxes(P, boards, cap=32):
    """Origin boxes (xlo, xhi, ylo, yhi), inclusive, for which every board rectangle lies
    inside some cover rectangle (each may pick a different one): the intersection over the
    rectangles of their unions of boxes, largest kept."""
    if isinstance(boards, tuple) and len(boards) == 4 and all(isinstance(v, (int, np.integer)) for v in boards):
        boards = [boards]
    cur = None
    for bb in boards:
        opts = _boxes_one(P, bb)
        if cur is None:
            cur = opts
            continue
        nxt = []
        for (a0, a1, b0, b1) in cur:
            for (c0, c1, d0, d1) in opts:
                x0, x1, y0, y1 = max(a0, c0), min(a1, c1), max(b0, d0), min(b1, d1)
                if x0 <= x1 and y0 <= y1:
                    nxt.append((x0, x1, y0, y1))
        nxt = sorted(set(nxt), key=lambda q: -((q[1] - q[0] + 1) * (q[3] - q[2] + 1)))
        cur = [q for k, q in enumerate(nxt)
               if not any(o[0] <= q[0] and q[1] <= o[1] and o[2] <= q[2] and q[3] <= o[3] for o in nxt[:k])][:cap]
        if not cur:
            return []
    return cur or []


def disjoint_union(rects):
    """Disjoint rectangles (i0, i1, j0, j1) covering exactly the union of `rects`: vertical
    slabs between distinct x edges, merged y intervals per slab, equal neighbouring slabs
    joined."""
    rects = [r for r in rects if r[1] > r[0] and r[3] > r[2]]
    if len(rects) <= 1:
        return rects
    xs = sorted({v for r in rects for v in (r[0], r[1])})
    out = []
    prev = None   # (x0, intervals)
    for x0, x1 in zip(xs[:-1], xs[1:]):
        iv = sorted((r[2], r[3]) for r in rects if r[0] <= x0 and r[1] >= x1)
        merged = []
        for a, b in iv:
            if merged and a <= merged[-1][1]:
                if b > merged[-1][1]:
                    merged[-1][1] = b
            else:
                merged.append([a, b])
        merged = [tuple(v) for v in merged]
        if prev is not None and prev[2] == merged and prev[1] == x0:
            prev = (prev[0], x1, merged)
        else:
            if prev is not None:
                out += [(prev[0], prev[1], a, b) for a, b in prev[2]]
            prev = (x0, x1, merged)
    if prev is not None:
        out += [(prev[0], prev[1], a, b) for a, b in prev[2]]
    return out


class Model:
    """Builds and solves one CP-SAT placement model."""

    def __init__(self, P, items, obstacles=(), hpwl_nets=None, w_disp=1.0, w_rot=None, w_wl=0.0,
                 fixed_pins=None):
        """obstacles: [(side, (i0, i1, j0, j1))] absolute grid rectangles.
        hpwl_nets: [(weight, [(part, pad)], [(x, y) fixed pin grid coordinates])] when w_wl > 0.
        """
        self.P = P
        self.items = items
        m = self.m = cp_model.CpModel()
        g = P.g
        self.w_rot = int(round((w_rot if w_rot is not None else 1.0) / g))   # ~1 mm by default
        xi = {0: [], 1: []}
        yi = {0: [], 1: []}
        self.V = []
        obj = []
        self.infeasible_items = []
        for it in items:
            info = [_rects_of(P, it, v) for v in range(len(it.variants))]
            boxes = [allowed_boxes(P, bb) for (_, bb) in info]
            if it.bounds is not None:
                bx0, bx1, by0, by1 = it.bounds
                boxes = [[(max(a0, bx0), min(a1, bx1), max(b0, by0), min(b1, by1)) for (a0, a1, b0, b1) in bl
                          if max(a0, bx0) <= min(a1, bx1) and max(b0, by0) <= min(b1, by1)] for bl in boxes]
            if not any(boxes):
                # fits nowhere inside the outline: kept where it is, outside the model
                self.infeasible_items.append(it.name)
                X = m.new_constant(it.X0)
                Y = m.new_constant(it.Y0)
                self.V.append((X, Y, [m.new_constant(int(v == it.v0)) for v in range(len(it.variants))]))
                continue
            xlo = min(bx[0] for bl in boxes for bx in bl)
            xhi = max(bx[1] for bl in boxes for bx in bl)
            ylo = min(bx[2] for bl in boxes for bx in bl)
            yhi = max(bx[3] for bl in boxes for bx in bl)
            X = m.new_int_var(xlo, max(xlo, xhi), f"X_{it.name}")
            Y = m.new_int_var(ylo, max(ylo, yhi), f"Y_{it.name}")
            lits = [m.new_bool_var(f"v_{it.name}_{v}") for v in range(len(it.variants))]
            m.add_exactly_one(lits)
            for v, bl in enumerate(boxes):
                if not bl:
                    m.add(lits[v] == 0)
                    continue
                if len(bl) == 1:
                    sel = [lits[v]]
                else:
                    sel = [m.new_bool_var("") for _ in bl]
                    m.add(sum(sel) == lits[v])
                for s_, (a0, a1, b0, b1) in zip(sel, bl):
                    m.add(X >= a0).only_enforce_if(s_)
                    m.add(X <= a1).only_enforce_if(s_)
                    m.add(Y >= b0).only_enforce_if(s_)
                    m.add(Y <= b1).only_enforce_if(s_)
            # intervals, shared between variants with the same rectangle
            for side in (0, 1):
                share = {}
                for v, (rects, _) in enumerate(info):
                    for r in rects[side]:
                        share.setdefault(r, []).append(lits[v])
                for (a, b, c, d), ls in share.items():
                    if b <= a or d <= c:
                        continue
                    if len(ls) == len(lits):
                        xi[side].append(m.new_fixed_size_interval_var(X + a, b - a, ""))
                        yi[side].append(m.new_fixed_size_interval_var(Y + c, d - c, ""))
                    else:
                        pres = ls[0] if len(ls) == 1 else m.new_bool_var("")
                        if len(ls) > 1:
                            m.add(sum(ls) == pres)
                        xi[side].append(m.new_optional_fixed_size_interval_var(X + a, b - a, pres, ""))
                        yi[side].append(m.new_optional_fixed_size_interval_var(Y + c, d - c, pres, ""))
            self.V.append((X, Y, lits))
            # displacement and rotation change
            if w_disp > 0:
                w = max(1, int(round(10 * w_disp * it.weight)))
                dx = m.new_int_var(0, P.ncx + abs(it.X0) + 10, "")
                dy = m.new_int_var(0, P.ncy + abs(it.Y0) + 10, "")
                m.add_abs_equality(dx, X - it.X0)
                m.add_abs_equality(dy, Y - it.Y0)
                obj += [w * dx, w * dy]
                if self.w_rot and 0 <= it.v0 < len(lits):
                    obj.append(w * self.w_rot * (1 - lits[it.v0]))
            if it.prefer:
                obj += [int(c) * lits[v] for v, c in enumerate(it.prefer) if c]
            if 0 <= it.v0 < len(lits):
                m.add_hint(X, min(max(it.X0, xlo), max(xlo, xhi)))
                m.add_hint(Y, min(max(it.Y0, ylo), max(ylo, yhi)))
                for v, l in enumerate(lits):
                    m.add_hint(l, int(v == it.v0))
        for side in (0, 1):
            # fixed rectangles may overlap each other (locked parts, keepouts, parts outside
            # a window): NoOverlap2D needs them disjoint, so add their union as disjoint pieces
            for (i0, i1, j0, j1) in disjoint_union([r for sd, r in obstacles if sd == side]):
                xi[side].append(m.new_fixed_size_interval_var(i0, i1 - i0, ""))
                yi[side].append(m.new_fixed_size_interval_var(j0, j1 - j0, ""))
        for side in (0, 1):
            if xi[side]:
                m.add_no_overlap_2d(xi[side], yi[side])
        if w_wl > 0 and hpwl_nets:
            obj += self._hpwl(hpwl_nets, w_wl)
        if obj:
            m.minimize(sum(obj))

    def _hpwl(self, nets, w_wl):
        P, m, g = self.P, self.m, self.P.g
        owner = {}
        for j, it in enumerate(self.items):
            for i in it.members:
                owner[i] = j
        terms = []
        for weight, pins, fixed in nets:
            xs, ys = [], []
            for (i, k) in pins:
                j = owner.get(i)
                if j is None:
                    continue
                X, Y, lits = self.V[j]
                it = self.items[j]
                ex, ey = X, Y
                cx, cy = [], []
                for v, l in enumerate(lits):
                    dx, dy, rk = it.variants[v][i]
                    px, py = P.parts[i].rots[rk].pins[k]
                    cx.append(dx + int(round(px / g)))
                    cy.append(dy + int(round(py / g)))
                if len(set(cx)) == 1:
                    ex = X + cx[0]
                else:
                    ex = X + sum(c * l for c, l in zip(cx, lits))
                if len(set(cy)) == 1:
                    ey = Y + cy[0]
                else:
                    ey = Y + sum(c * l for c, l in zip(cy, lits))
                xs.append(ex)
                ys.append(ey)
            for (fx, fy) in fixed:
                xs.append(fx)
                ys.append(fy)
            if len(xs) < 2:
                continue
            w = max(1, int(round(10 * w_wl * weight)))
            lo_b = -2 * (P.ncx + P.ncy) - 1000
            hi_b = 3 * (P.ncx + P.ncy) + 1000
            a = m.new_int_var(lo_b, hi_b, "")
            b = m.new_int_var(lo_b, hi_b, "")
            c = m.new_int_var(lo_b, hi_b, "")
            d = m.new_int_var(lo_b, hi_b, "")
            m.add_max_equality(a, xs)
            m.add_min_equality(b, xs)
            m.add_max_equality(c, ys)
            m.add_min_equality(d, ys)
            terms += [w * (a - b), w * (c - d)]
        return terms

    def solve(self, time_s, workers=2, seed=0, log=False, stop_first=False):
        s = cp_model.CpSolver()
        s.parameters.max_time_in_seconds = max(0.05, float(time_s))
        s.parameters.num_workers = max(1, int(workers))
        s.parameters.random_seed = int(seed)
        if stop_first:
            s.parameters.stop_after_first_solution = True
        s.parameters.log_search_progress = bool(log)
        t0 = time.monotonic()
        st = s.solve(self.m)
        self.status = s.status_name(st)
        self.wall = time.monotonic() - t0
        self.solver = s
        if st not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            return None
        out = []
        for (X, Y, lits) in self.V:
            v = next((v for v, l in enumerate(lits) if s.value(l)), 0)
            out.append((s.value(X), s.value(Y), v))
        return out
