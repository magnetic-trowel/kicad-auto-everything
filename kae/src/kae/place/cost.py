# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Routability terms (the placer's own; physics comes from kae.physics.place_terms).

- Weighted HPWL lives in the annealer (per-net bounding boxes; ground and power nets
  down-weighted, H11).
- `Congestion`: RUDY (Spindler & Johannes 2007) on a coarse bin grid. Each net spreads its
  expected wire length (w + h of its pin box) uniformly over the box; each pin adds escape
  demand in its bin; pads (with their clearance halo) take routing supply away from their
  bin. Bin supply = routable layers x bin area / track pitch x (1 - beta * blocked share).
  Cost = mean of max(0, utilization - target)^2, so only crowded bins pay.
  Incremental: the overlap of a box with the bins factorizes into x and y weights, so a
  net's contribution is an outer product; a move re-adds only the touched nets and the
  moved parts' pads, inside the bins they cover, before and after.
- `routability_report(P, st)`: signal-only HPWL and RUDY peak/overflow for reports.
"""
from __future__ import annotations

import math

import numpy as np


def _axis_weights(lo, hi, edges):
    """Overlap length of [lo, hi] with each bin [edges[k], edges[k+1]]; returns (k0, weights)."""
    nb = len(edges) - 1
    k0 = int(np.searchsorted(edges, lo, side="right")) - 1
    k1 = int(np.searchsorted(edges, hi, side="left"))
    k0 = min(max(k0, 0), nb - 1)
    k1 = min(max(k1, k0 + 1), nb)
    e = edges[k0:k1 + 1]
    w = np.minimum(e[1:], hi) - np.maximum(e[:-1], lo)
    return k0, np.maximum(w, 0.0)


class Congestion:
    """RUDY congestion with pad blockage and pin escape, tied to an Annealer (its net pin
    lists `ann.nx`, `ann.ny` and part poses).

    Per bin b (area A):
      demand  D_b = sum of nets' RUDY in b + escape * (pins with a net centred in b)
      supply  S_b = layers * A / pitch * max(smin, 1 - beta * blocked_b / A)
      blocked_b = sum over pads centred in b of (w + 2c)(h + 2c) * layer share
                  (c = minimum clearance; drilled pads block every layer, SMD pads one)
    cost = mean over bins of max(0, D_b / S_b - target)^2.
    Pads are point masses at their centres (bins are about a millimetre or more).
    """

    # Calibrated on 55 probed split-A placements (human and kae, probe unconnected > 0 as the
    # positives): escape demand separates (peak AUC 0.84, p95 0.95), pad blockage only adds
    # noise (beta 0), and target 0.5 leaves 30 of 42 negatives at zero cost.
    # Checked across boards on the human placements of splits B and C (75 boards whose three
    # Freerouting attempts completed below the 499 report cap; label = unconnected / start):
    # the overflow at target 0.5 ranks them with Spearman +0.42 (B alone +0.54) with escape 2
    # against +0.29 without escape demand; escape 4 is no better; pad blockage halves the
    # peak's correlation (+0.40 -> +0.18); coarser bins (1.6, 2.4 mm minimum) are worse.
    # Across boards, signal HPWL per layer-area does as well (+0.61): hotspots add little to
    # density there, and timeouts follow board size (pins AUC 0.92), not congestion (< 0.5).
    def __init__(self, P, ann, bins=None, target=0.5, escape=2.0, beta=0.0, smin=0.1, signal_only=False):
        self.P = P
        self.ann = ann
        x0, y0, x1, y1 = P.outline.bounds
        self.x0, self.y0 = x0, y0
        span = max(x1 - x0, y1 - y0)
        b = bins or max(0.8, span / 32.0)
        self.b = b
        self.nbx = max(1, int(math.ceil((x1 - x0) / b)))
        self.nby = max(1, int(math.ceil((y1 - y0) / b)))
        self.ex = np.linspace(x0, x0 + self.nbx * b, self.nbx + 1)
        self.ey = np.linspace(y0, y0 + self.nby * b, self.nby + 1)
        self.bin_area = b * b
        layers = len(P.board.stackup.copper) if P.board.stackup else 2
        rules = P.board.rules
        pitch = max(0.25, (rules.track_min if rules and rules.track_min else 0.2) + P.clr_min)
        self.S0 = layers * self.bin_area / pitch     # mm of track per bin on an empty board
        self.supply = self.S0
        self.target, self.escape, self.beta, self.smin = target, escape, beta, smin
        self.Dn = np.zeros((self.nbx, self.nby))
        self.Dp = np.zeros((self.nbx, self.nby))
        self.Bk = np.zeros((self.nbx, self.nby))
        self.contrib = {}      # net -> (kx0, ky0, block) currently added
        self.w = []
        for net in P.nets:
            w = net.weight
            if signal_only and net.kind in ("ground", "power"):
                w = 0.0
            self.w.append(w)
        # pads: blocked area (with the clearance halo, by layer share) and escape demand
        c = P.clr_min
        self.pad_blk, self.pad_esc = [], []
        for p in P.parts:
            blk, esc = [], []
            for pd in p.fp.pads:
                w, h = pd.size
                if pd.shape == "circle":
                    area = math.pi * (max(w, h) / 2 + c) ** 2
                else:
                    area = (w + 2 * c) * (h + 2 * c)
                drilled = pd.kind in ("thru_hole", "np_thru_hole") or bool(pd.drill)
                blk.append(area * (1.0 if drilled else 1.0 / layers))
                esc.append(escape if pd.net else 0.0)
            self.pad_blk.append(np.array(blk))
            self.pad_esc.append(np.array(esc))
        for i in range(len(P.parts)):
            bx, by = self._pad_bins(i)
            if len(bx):
                np.add.at(self.Dp, (bx, by), self.pad_esc[i])
                np.add.at(self.Bk, (bx, by), self.pad_blk[i])
        self.pending = None
        for j in range(len(P.nets)):
            cb = self._net_block(j)
            if cb is not None:
                self._add(cb, +1.0, self.Dn)
                self.contrib[j] = cb
        self.norm = 1.0 / (self.nbx * self.nby)

    # ---------------------------------------------------------------- pads
    def _pad_xy(self, i, pose=None):
        ann, P = self.ann, self.P
        p = P.parts[i]
        if not p.movable:
            r = p.rots[0]
            return p.x0 + r.pins[:, 0], p.y0 + r.pins[:, 1]
        X, Y, K = pose if pose is not None else (ann.X[i], ann.Y[i], ann.K[i])
        x = P.ox + X * P.g
        y = P.oy + Y * P.g
        r = p.rots[K]
        return x + r.pins[:, 0], y + r.pins[:, 1]

    def _pad_bins(self, i, pose=None):
        px, py = self._pad_xy(i, pose)
        bx = np.clip(((px - self.x0) / self.b).astype(int), 0, self.nbx - 1)
        by = np.clip(((py - self.y0) / self.b).astype(int), 0, self.nby - 1)
        return bx, by

    # ---------------------------------------------------------------- nets
    def _net_block(self, j):
        w = self.w[j]
        xs, ys = self.ann.nx[j], self.ann.ny[j]
        if w <= 0 or len(xs) < 2:
            return None
        lo_x, hi_x = min(xs) - 0.2, max(xs) + 0.2
        lo_y, hi_y = min(ys) - 0.2, max(ys) + 0.2
        W, H = hi_x - lo_x, hi_y - lo_y
        dens = w * (W + H) / (W * H)                     # mm of wire per mm^2
        kx, wx = _axis_weights(lo_x, hi_x, self.ex)
        ky, wy = _axis_weights(lo_y, hi_y, self.ey)
        block = dens * np.outer(wx, wy)
        return (kx, ky, block)

    def _add(self, c, s, D, ox=0, oy=0):
        kx, ky, block = c
        D[kx - ox:kx - ox + block.shape[0], ky - oy:ky - oy + block.shape[1]] += s * block

    # ---------------------------------------------------------------- cost
    def _f(self, Dn, Dp, Bk):
        S = self.S0 * np.maximum(self.smin, 1.0 - self.beta * Bk / self.bin_area)
        u = (Dn + Dp) / S - self.target
        return float(np.square(np.clip(u, 0.0, None)).sum())

    def utilization(self):
        S = self.S0 * np.maximum(self.smin, 1.0 - self.beta * self.Bk / self.bin_area)
        return (self.Dn + self.Dp) / S

    def local_cost(self, nets):
        return 0.0

    def trial(self, nets, moved=()):
        """Cost change if the touched nets take their current (moved) pin boxes and the moved
        parts' pads their current bins. moved: [(part, old (X, Y, K))]."""
        olds = {j: self.contrib.get(j) for j in nets}
        news = {j: self._net_block(j) for j in nets}
        pads = []
        for i, old in moved:
            if not self.P.parts[i].movable or not len(self.pad_blk[i]):
                continue
            b0 = self._pad_bins(i, old)
            b1 = self._pad_bins(i)
            if np.array_equal(b0[0], b1[0]) and np.array_equal(b0[1], b1[1]):
                continue
            pads.append((b0, -1.0, i))
            pads.append((b1, +1.0, i))
        spans = [(c[0], c[0] + c[2].shape[0], c[1], c[1] + c[2].shape[1])
                 for c in list(olds.values()) + list(news.values()) if c is not None]
        spans += [(int(bx.min()), int(bx.max()) + 1, int(by.min()), int(by.max()) + 1) for (bx, by), _, _ in pads]
        if not spans:
            self.pending = None
            return 0.0
        x0 = min(sp[0] for sp in spans)
        x1 = max(sp[1] for sp in spans)
        y0 = min(sp[2] for sp in spans)
        y1 = max(sp[3] for sp in spans)
        Dn, Dp, Bk = self.Dn[x0:x1, y0:y1], self.Dp[x0:x1, y0:y1], self.Bk[x0:x1, y0:y1]
        before = self._f(Dn, Dp, Bk)
        Dn2 = Dn.copy()
        for j in nets:
            if olds[j] is not None:
                self._add(olds[j], -1.0, Dn2, x0, y0)
            if news[j] is not None:
                self._add(news[j], +1.0, Dn2, x0, y0)
        if pads:
            Dp2, Bk2 = Dp.copy(), Bk.copy()
            for (bx, by), sgn, i in pads:
                np.add.at(Dp2, (bx - x0, by - y0), sgn * self.pad_esc[i])
                np.add.at(Bk2, (bx - x0, by - y0), sgn * self.pad_blk[i])
        else:
            Dp2, Bk2 = Dp, Bk
        after = self._f(Dn2, Dp2, Bk2)
        self.pending = (x0, x1, y0, y1, Dn2, Dp2 if pads else None, Bk2 if pads else None, news)
        return (after - before) * self.norm

    def commit(self):
        if self.pending is None:
            return
        x0, x1, y0, y1, Dn2, Dp2, Bk2, news = self.pending
        self.Dn[x0:x1, y0:y1] = Dn2
        if Dp2 is not None:
            self.Dp[x0:x1, y0:y1] = Dp2
            self.Bk[x0:x1, y0:y1] = Bk2
        for j, c in news.items():
            if c is None:
                self.contrib.pop(j, None)
            else:
                self.contrib[j] = c
        self.pending = None

    def revert(self):
        self.pending = None

    def total(self):
        return self._f(self.Dn, self.Dp, self.Bk) * self.norm

    def peak(self):
        return float(self.utilization().max()) if self.Dn.size else 0.0


def routability_report(P, st, cong_args=None):
    """Signal-only HPWL (H11) and RUDY numbers of a placement, for reports."""
    from .anneal import Annealer
    ann = Annealer(P, st.copy(), terms=None, w_cong=1.0, **({"cong_args": cong_args} if cong_args else {}))
    c = ann.cong
    util = c.utilization()
    return dict(hpwl=round(st.hpwl(), 2), hpwl_signal=round(st.hpwl(signal_only=True), 2),
                rudy_peak=round(float(util.max()), 3), rudy_mean=round(float(util.mean()), 3),
                rudy_p95=round(float(np.percentile(util, 95)), 3), rudy_overflow=round(c.total(), 5))
