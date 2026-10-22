# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Simulated annealing on the grid, with one cost (adapted from
tools/research/solver-bench/sa_place.py):

    cost = w_phys * physics          Terms.total / structures (budget utilization), via Terms.delta
         + w_wl * routability        weighted HPWL / seed HPWL (+ RUDY congestion, escape halos;
                                     kae.place.cost)
         + lam(t) * legality         overlap area of the grid rectangles (own, opposite side,
                                     obstacles) + area outside the outline, / mean part area;
                                     lam ramps up geometrically
         + w_disp * displacement     L1 distance from the seed / (parts * mean part size)

Moves: shift (radius shrinking with the temperature), rotate in place, swap equal
footprints (or similar sizes), macro shift, macro rotate, macro re-layout from its top-K.
Everything is incremental: nets keep their pin coordinates and only touched nets are
re-measured; overlaps come from a spatial hash per side; physics from Terms.delta.
Seeded by `seed`; the budget is CPU seconds (time.process_time), checked between batches,
and the schedule runs over a planned move count so a run is reproducible when the budget
does not bind.
"""
from __future__ import annotations

import math
import random
import time

from .cost import Congestion

BIG_NET = 40   # ground/power nets with more pins are frozen in the annealer


class Annealer:
    def __init__(self, P, st, terms=None, macros=(), seed=0, w_wl=1.0, w_phys=1.0, w_disp=0.05,
                 w_cong=0.3, w_esc=0.3, lam0=1.0, lam1=40.0, wl_slack=0.15, wl_barrier=20.0, log=None):
        self.P = P
        self.st = st
        self.rng = random.Random(seed)
        self.log = log or (lambda *a, **k: None)
        self.g = g = P.g
        self.mov = list(P.mov)
        self.movset = set(self.mov)
        n = len(P.parts)
        X, Y, K = st.X, st.Y, st.K
        self.X = [int(v) for v in X]
        self.Y = [int(v) for v in Y]
        self.K = [int(v) for v in K]
        self.Xs = list(self.X)          # seed positions (displacement term)
        self.Ys = list(self.Y)
        # ---- static geometry per part and rotation
        self.own = [[r.g_own for r in p.rots] for p in P.parts]
        self.opp = [[r.g_opp for r in p.rots] for p in P.parts]
        self.brd = [[r.g_board for r in p.rots] for p in P.parts]
        self.brds = [[r.g_boards for r in p.rots] for p in P.parts]
        self.side = [0 if p.s > 0 else 1 for p in P.parts]
        self.pinx = [[[float(v) for v in r.pins[:, 0]] for r in p.rots] for p in P.parts]
        self.piny = [[[float(v) for v in r.pins[:, 1]] for r in p.rots] for p in P.parts]
        self.nrot = [len(p.rots) for p in P.parts]
        areas = [(r[1] - r[0]) * (r[3] - r[2]) for r in (self.own[i][0] for i in self.mov)] or [1]
        self.A0 = max(1.0, sum(areas) / len(areas))      # mean part area, cells^2
        self.S0 = math.sqrt(self.A0) * g                  # mean part size, mm
        # ---- spatial hash: rect ids per side
        self.B = max(4, int(round(math.sqrt(self.A0) * 1.5)))
        self.buckets = ({}, {})
        self.r_owner = []
        self.r_side = []
        self.r_box = []
        self.r_span = []
        self.part_rects = [[] for _ in range(n)]
        for i in self.mov:
            k = self.K[i]
            rid = self._new_rect(i, self.side[i])
            self.part_rects[i].append(rid)
            for _ in self.opp[i][k]:
                rid = self._new_rect(i, 1 - self.side[i])
                self.part_rects[i].append(rid)
            self._place_rects(i)
        for ob in P.obstacles:
            rid = self._new_rect(-1, ob.side)
            self.r_box[rid] = ob.g
            self._hash_add(rid)
        # ---- nets: pin coordinate lists; per part (net, slot, pad)
        self.net_w = [net.weight for net in P.nets]
        self.nx = []
        self.ny = []
        self.part_pins = [[] for _ in range(n)]
        for net in P.nets:
            xs, ys = [], []
            for (i, k) in net.pins:
                x, y = self._pin_xy(i, k)
                self.part_pins[i].append((net.i, len(xs), k))
                xs.append(x)
                ys.append(y)
            self.nx.append(xs)
            self.ny.append(ys)
        # ground/power nets with many pins span the board whatever one part does, and are
        # poured in practice (H11): their (down-weighted) length is frozen, which keeps every
        # move from re-measuring hundreds of pins
        self.frozen = {net.i for net in P.nets if net.kind in ("ground", "power") and len(net.pins) > BIG_NET}
        self.part_nets = [sorted({nn for (nn, _, _) in pp if nn not in self.frozen}) for pp in self.part_pins]
        self.part_pins = [[(nn, sl, k) for (nn, sl, k) in pp if nn not in self.frozen] for pp in self.part_pins]
        self.ncost = [self._net_cost(j) for j in range(len(P.nets))]
        self.wl = sum(self.ncost)
        self.W0 = max(1e-6, self.wl)
        # ---- physics
        self.terms = terms
        self.tparts = set()
        self.uuid = [p.uuid for p in P.parts]
        self.poses = {p.uuid: st.pose(p.i) for p in P.parts}
        if terms is not None:
            try:
                self.tparts = set(terms.parts())
            except Exception:
                self.tparts = set(self.uuid)
            self.nstruct = max(1, len(getattr(terms, "structs", [])) or len(self.tparts) // 2 or 1)
            self.phys = terms.total(self.poses)
        else:
            self.nstruct = 1
            self.phys = 0.0
        # ---- congestion (RUDY) and escape halos
        self.cong = Congestion(P, self) if w_cong > 0 else None
        # ---- macros
        self.macros = [m for m in macros if len(m.members) >= 2]
        self.macro_of = {}
        for mi, m in enumerate(self.macros):
            for i in m.members:
                if i in self.movset:
                    self.macro_of[i] = mi
        # ---- equal-footprint swap classes
        cls = {}
        for i in self.mov:
            cls.setdefault(P.parts[i].shape_key, []).append(i)
        self.swap_class = {i: c for c in cls.values() if len(c) > 1 for i in c}
        self.w = dict(wl=w_wl, phys=w_phys, disp=w_disp, cong=w_cong, esc=w_esc)
        # routability as a soft budget: free trade up to (1 + slack) x the seed HPWL, steep beyond
        self.wl_slack, self.wl_barrier = wl_slack, wl_barrier
        self.lam0, self.lam1 = lam0, lam1
        self.stats = dict(moves=0, accepted=0, by_move={})
        self.leg_total = self.total_leg()
        self.best_legal = None

    # ------------------------------------------------------------------ geometry
    def _new_rect(self, owner, side):
        self.r_owner.append(owner)
        self.r_side.append(side)
        self.r_box.append((0, 0, 0, 0))
        self.r_span.append(None)
        return len(self.r_owner) - 1

    def _hash_add(self, rid):
        i0, i1, j0, j1 = self.r_box[rid]
        B = self.B
        span = (i0 // B, (i1 - 1) // B, j0 // B, (j1 - 1) // B)
        self.r_span[rid] = span
        bk = self.buckets[self.r_side[rid]]
        for bi in range(span[0], span[1] + 1):
            for bj in range(span[2], span[3] + 1):
                s = bk.get((bi, bj))
                if s is None:
                    bk[(bi, bj)] = {rid}
                else:
                    s.add(rid)

    def _hash_remove(self, rid):
        span = self.r_span[rid]
        if span is None:
            return
        bk = self.buckets[self.r_side[rid]]
        for bi in range(span[0], span[1] + 1):
            for bj in range(span[2], span[3] + 1):
                s = bk.get((bi, bj))
                if s is not None:
                    s.discard(rid)
        self.r_span[rid] = None

    def _place_rects(self, i):
        """(Re)register part i's rectangles at its current X, Y, K."""
        X, Y, k = self.X[i], self.Y[i], self.K[i]
        rids = self.part_rects[i]
        boxes = [self.own[i][k]] + list(self.opp[i][k])
        for rid, (a, b, c, d) in zip(rids, boxes):
            box = (X + a, X + b, Y + c, Y + d)
            if box == self.r_box[rid] and self.r_span[rid] is not None:
                continue
            self._hash_remove(rid)
            self.r_box[rid] = box
            self._hash_add(rid)

    def _overlap_part(self, i, exclude):
        """Overlap area (cells^2) of part i's rectangles with other owners not in exclude."""
        tot = 0
        bks = self.buckets
        r_box, r_owner = self.r_box, self.r_owner
        for rid in self.part_rects[i]:
            i0, i1, j0, j1 = r_box[rid]
            sp = self.r_span[rid]
            bk = bks[self.r_side[rid]]
            seen = set()
            for bi in range(sp[0], sp[1] + 1):
                for bj in range(sp[2], sp[3] + 1):
                    s = bk.get((bi, bj))
                    if not s:
                        continue
                    for o in s:
                        if o in seen:
                            continue
                        seen.add(o)
                        ow = r_owner[o]
                        if ow == i or ow in exclude:
                            continue
                        a0, a1, b0, b1 = r_box[o]
                        dx = (i1 if i1 < a1 else a1) - (i0 if i0 > a0 else a0)
                        if dx <= 0:
                            continue
                        dy = (j1 if j1 < b1 else b1) - (j0 if j0 > b0 else b0)
                        if dy > 0:
                            tot += dx * dy
        return tot

    def _overlap_pair(self, i, j):
        tot = 0
        for ra in self.part_rects[i]:
            for rb in self.part_rects[j]:
                if self.r_side[ra] != self.r_side[rb]:
                    continue
                a0, a1, b0, b1 = self.r_box[ra]
                c0, c1, d0, d1 = self.r_box[rb]
                dx = min(a1, c1) - max(a0, c0)
                dy = min(b1, d1) - max(b0, d0)
                if dx > 0 and dy > 0:
                    tot += dx * dy
        return tot

    def _outline(self, i):
        return self.P.outside_cells_all(self.X[i], self.Y[i], self.brds[i][self.K[i]])

    def _leg(self, S):
        """Legality cost of the parts in S (cells^2), each pair counted once."""
        ex = set(S)
        tot = 0
        for idx, i in enumerate(S):
            tot += self._overlap_part(i, ex) + self._outline(i)
            for j in S[idx + 1:]:
                tot += self._overlap_pair(i, j)
        return tot

    # ------------------------------------------------------------------ nets
    def _pin_xy(self, i, k):
        p = self.P.parts[i]
        if not p.movable:
            r = p.rots[0]
            return p.x0 + float(r.pins[k, 0]), p.y0 + float(r.pins[k, 1])
        kk = self.K[i]
        return (self.P.ox + self.X[i] * self.g + self.pinx[i][kk][k],
                self.P.oy + self.Y[i] * self.g + self.piny[i][kk][k])

    def _net_cost(self, j):
        xs, ys = self.nx[j], self.ny[j]
        if len(xs) < 2:
            return 0.0
        return self.net_w[j] * (max(xs) - min(xs) + max(ys) - min(ys))

    def _update_pins(self, i):
        x0 = self.P.ox + self.X[i] * self.g
        y0 = self.P.oy + self.Y[i] * self.g
        kk = self.K[i]
        px, py = self.pinx[i][kk], self.piny[i][kk]
        nx, ny = self.nx, self.ny
        for (j, slot, k) in self.part_pins[i]:
            nx[j][slot] = x0 + px[k]
            ny[j][slot] = y0 + py[k]

    # ------------------------------------------------------------------ evaluation
    def _apply(self, S, newpos):
        """Move parts S to newpos [(X, Y, K)]; returns the old positions."""
        old = [(self.X[i], self.Y[i], self.K[i]) for i in S]
        for i, (X, Y, K) in zip(S, newpos):
            self.X[i], self.Y[i], self.K[i] = X, Y, K
            self._place_rects(i)
            self._update_pins(i)
        return old

    def _disp(self, S):
        return sum(abs(self.X[i] - self.Xs[i]) + abs(self.Y[i] - self.Ys[i]) for i in S)

    def _pose_of(self, i):
        p = self.P.parts[i]
        return (self.P.ox + self.X[i] * self.g, self.P.oy + self.Y[i] * self.g, p.rots[self.K[i]].rot, p.side)

    def try_move(self, S, newpos, T, lam, kind):
        """Evaluate moving parts S to newpos; accept or revert. Returns accepted."""
        nets = set()
        for i in S:
            nets.update(self.part_nets[i])
        wl_old = sum(self.ncost[j] for j in nets)
        leg_old = self._leg(S)
        disp_old = self._disp(S)
        cong_old = self.cong.local_cost(nets) if self.cong is not None else 0.0
        old = self._apply(S, newpos)
        newc = {j: self._net_cost(j) for j in nets}
        wl_new = sum(newc.values())
        leg_new = self._leg(S)
        disp_new = self._disp(S)
        d_cong = 0.0
        if self.cong is not None:
            d_cong = self.cong.trial(nets) - cong_old
        d_phys = 0.0
        moved_u = [self.uuid[i] for i in S if self.uuid[i] in self.tparts]
        if moved_u:
            newp = {self.uuid[i]: self._pose_of(i) for i in S}
            d_phys = self.terms.delta(self.poses, moved_u, {u: newp[u] for u in moved_u})
        w = self.w
        g2 = 1.0
        delta = (w["wl"] * (self._wl_cost(self.wl + wl_new - wl_old) - self._wl_cost(self.wl))
                 + lam * (leg_new - leg_old) * g2 / self.A0
                 + w["disp"] * (disp_new - disp_old) * self.g / (len(self.mov) * self.S0)
                 + w["phys"] * d_phys / self.nstruct
                 + w["cong"] * d_cong)
        st = self.stats
        st["moves"] += 1
        bm = st["by_move"].setdefault(kind, [0, 0])
        bm[0] += 1
        if delta <= 0 or self.rng.random() < math.exp(-delta / T):
            for j, c in newc.items():
                self.ncost[j] = c
            self.wl += wl_new - wl_old
            self.phys += d_phys
            if self.cong is not None:
                self.cong.commit()
            for i in S:
                self.poses[self.uuid[i]] = self._pose_of(i)
            st["accepted"] += 1
            bm[1] += 1
            self.leg_total += leg_new - leg_old
            return True, delta
        self._apply(S, old)
        if self.cong is not None:
            self.cong.revert()
        return False, delta

    # ------------------------------------------------------------------ moves
    def _clamp(self, i, X, Y, K):
        a, b, c, d = self.brd[i][K]
        lo_x, hi_x = -a, self.P.ncx - b
        lo_y, hi_y = -c, self.P.ncy - d
        X = min(max(X, lo_x), max(lo_x, hi_x))
        Y = min(max(Y, lo_y), max(lo_y, hi_y))
        return X, Y

    def _center2(self, i, k):
        a, b, c, d = self.own[i][k]
        return a + b, c + d

    def propose(self, r):
        rng = self.rng
        i = self.mov[rng.randrange(len(self.mov))]
        u = rng.random()
        mi = self.macro_of.get(i)
        if mi is not None and u < 0.25:
            return self._macro_move(mi, r)
        if u < 0.62:
            X = self.X[i] + rng.randint(-r, r)
            Y = self.Y[i] + rng.randint(-r, r)
            X, Y = self._clamp(i, X, Y, self.K[i])
            return (i,), [(X, Y, self.K[i])], "shift"
        if u < 0.80 and self.nrot[i] > 1:
            k0 = self.K[i]
            k1 = (k0 + rng.choice((1, 2, 3))) % self.nrot[i]
            cx0, cy0 = self._center2(i, k0)
            cx1, cy1 = self._center2(i, k1)
            X = self.X[i] + (cx0 - cx1) // 2
            Y = self.Y[i] + (cy0 - cy1) // 2
            X, Y = self._clamp(i, X, Y, k1)
            return (i,), [(X, Y, k1)], "rotate"
        # swap: an equal footprint if there is one, else any part on the same side
        cls = self.swap_class.get(i)
        if cls and rng.random() < 0.7:
            j = cls[rng.randrange(len(cls))]
            if j != i:
                return (i, j), [(self.X[j], self.Y[j], self.K[j]), (self.X[i], self.Y[i], self.K[i])], "swap_equal"
        j = self.mov[rng.randrange(len(self.mov))]
        if j == i or self.side[j] != self.side[i]:
            X = self.X[i] + rng.randint(-r, r)
            Y = self.Y[i] + rng.randint(-r, r)
            X, Y = self._clamp(i, X, Y, self.K[i])
            return (i,), [(X, Y, self.K[i])], "shift"
        ci = self._center2(i, self.K[i])
        cj = self._center2(j, self.K[j])
        Xi = self.X[j] + (cj[0] - ci[0]) // 2
        Yi = self.Y[j] + (cj[1] - ci[1]) // 2
        Xj = self.X[i] + (ci[0] - cj[0]) // 2
        Yj = self.Y[i] + (ci[1] - cj[1]) // 2
        Xi, Yi = self._clamp(i, Xi, Yi, self.K[i])
        Xj, Yj = self._clamp(j, Xj, Yj, self.K[j])
        return (i, j), [(Xi, Yi, self.K[i]), (Xj, Yj, self.K[j])], "swap"

    def _macro_move(self, mi, r):
        rng = self.rng
        m = self.macros[mi]
        mem = [i for i in m.members if i in self.movset]
        if not mem:
            return None
        u = rng.random()
        if u < 0.5 or m.anchor not in self.movset:
            dX = rng.randint(-r, r)
            dY = rng.randint(-r, r)
            return tuple(mem), [(self.X[i] + dX, self.Y[i] + dY, self.K[i]) for i in mem], "macro_shift"
        a = m.anchor
        AX, AY = self.X[a], self.Y[a]
        if u < 0.8 or len(m.layouts) < 2:
            q = rng.choice((1, 2, 3))
            out = []
            for i in mem:
                dx, dy = self.X[i] - AX, self.Y[i] - AY
                for _ in range(q):
                    dx, dy = dy, -dx      # KiCad +90 degrees, y down
                out.append((AX + dx, AY + dy, (self.K[i] + q) % self.nrot[i]))
            return tuple(mem), out, "macro_rotate"
        lay = m.layouts[rng.randrange(len(m.layouts))]
        # the macro's current turn: the anchor's rotation relative to the layout's
        q = (self.K[a] - lay.offsets[a][2]) % 4
        out = []
        for i in mem:
            dx, dy, k = lay.offsets[i]
            dx -= lay.offsets[a][0]
            dy -= lay.offsets[a][1]
            for _ in range(q):
                dx, dy = dy, -dx
            out.append((AX + dx, AY + dy, (k + q) % self.nrot[i]))
        return tuple(mem), out, "macro_relayout"

    # ------------------------------------------------------------------ schedule
    def total_leg(self):
        tot = 0
        for idx, i in enumerate(self.mov):
            tot += self._overlap_part(i, set(self.mov[:idx + 1])) + self._outline(i)
        return tot

    def _wl_cost(self, wl):
        u = wl / self.W0
        over = u - 1.0 - self.wl_slack
        return u + (self.wl_barrier * over * over if over > 0 else 0.0)

    def cost(self, lam):
        w = self.w
        disp = self._disp(self.mov) * self.g / (len(self.mov) * self.S0)
        c = self.cong.total() if self.cong is not None else 0.0
        return (w["wl"] * self._wl_cost(self.wl) + lam * self.leg_total / self.A0 + w["disp"] * disp
                + w["phys"] * self.phys / self.nstruct + w["cong"] * c)

    def evaluate(self, st):
        """Full cost of another state with this annealer's weights and normalization (seed
        HPWL, mean part area and size, seed positions, final legality weight)."""
        o = Annealer(self.P, st.copy(), terms=self.terms, seed=0, w_wl=self.w["wl"], w_phys=self.w["phys"],
                     w_disp=self.w["disp"], w_cong=self.w["cong"], lam0=self.lam0, lam1=self.lam1,
                     wl_slack=self.wl_slack, wl_barrier=self.wl_barrier)
        o.W0, o.A0, o.S0, o.nstruct = self.W0, self.A0, self.S0, self.nstruct
        o.Xs, o.Ys = self.Xs, self.Ys
        return o.cost(self.lam1), o.terms_report()

    def terms_report(self):
        disp = self._disp(self.mov) * self.g / (len(self.mov) * self.S0) if self.mov else 0.0
        return dict(wl=round(self.wl / self.W0, 5), phys=round(self.phys / self.nstruct, 5),
                    cong=round(self.cong.total(), 6) if self.cong is not None else None,
                    leg=self.leg_total, disp=round(disp, 5))

    def run(self, cpu_s, moves_per_part=4000, max_moves=None, log_every=0.25):
        n = len(self.mov)
        if n == 0:
            return self.report(0.0)
        N = max_moves or moves_per_part * n
        self.leg_total = self.total_leg()
        t0 = time.process_time()
        r0 = max(2, int(0.25 * max(self.P.ncx, self.P.ncy)))
        # initial temperature from uphill deltas of sampled moves (not applied)
        ups = []
        for _ in range(min(200, 20 * n)):
            mv = self.propose(r0)
            if mv is None:
                continue
            S, newpos, kind = mv
            acc, d = self.try_move(S, newpos, 1e-12, self.lam0, kind)
            if acc and d > 0:
                pass
            if d > 0:
                ups.append(d)
        ups.sort()
        T0 = ups[len(ups) // 2] / math.log(1 / 0.3) if ups else 1e-3
        T1 = T0 * 1e-4
        self.T0 = T0
        self.stats = dict(moves=0, accepted=0, by_move={})
        done = 0
        batch = 200
        next_log = log_every
        best = None
        while done < N:
            frac = done / N
            T = T0 * (T1 / T0) ** frac
            lam = self.lam0 * (self.lam1 / self.lam0) ** frac
            r = max(1, int(r0 * (T / T0) ** 0.5))
            for _ in range(batch):
                mv = self.propose(r)
                if mv is None:
                    continue
                S, newpos, kind = mv
                self.try_move(S, newpos, T, lam, kind)
            done += batch
            if self.leg_total == 0:
                c = self.cost(lam)
                if best is None or c < best[0]:
                    best = (c, list(self.X), list(self.Y), list(self.K))
            el = time.process_time() - t0
            if el > cpu_s:
                break
            if done / N >= next_log:
                next_log += log_every
                self.log(f"anneal {100 * done / N:.0f}% T={T:.2e} lam={lam:.1f} r={r} wl={self.wl:.1f} "
                         f"phys={self.phys:.3f} leg={self.leg_total} acc={self.stats['accepted'] / max(1, self.stats['moves']):.2f}")
        self.final_lam = self.lam0 * (self.lam1 / self.lam0) ** min(1.0, done / N)
        self.best_legal = best
        return self.report(time.process_time() - t0, planned=N, done=done)

    def report(self, cpu, planned=0, done=0):
        return dict(cpu_s=round(cpu, 2), planned_moves=planned, moves=done,
                    moves_per_s=round(done / cpu) if cpu > 0 else None,
                    accept=round(self.stats["accepted"] / max(1, self.stats["moves"]), 3),
                    by_move={k: dict(tried=v[0], accepted=v[1]) for k, v in self.stats["by_move"].items()},
                    hpwl=round(self.wl, 2), physics=round(self.phys, 4), leg_cells=self.leg_total,
                    T0=getattr(self, "T0", None))

    def write_back(self, use_best_legal=False):
        X, Y, K = self.X, self.Y, self.K
        if use_best_legal and self.best_legal is not None:
            _, X, Y, K = self.best_legal
        for i in self.mov:
            self.st.X[i], self.st.Y[i], self.st.K[i] = X[i], Y[i], K[i]
