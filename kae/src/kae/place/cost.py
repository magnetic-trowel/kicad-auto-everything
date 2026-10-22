# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Routability terms (the placer's own; physics comes from kae.physics.place_terms).

- Weighted HPWL lives in the annealer (per-net bounding boxes; ground and power nets
  down-weighted, H11).
- `Congestion`: RUDY (Spindler & Johannes 2007) on a coarse bin grid. Each net spreads its
  expected wire length (w + h of its pin box) uniformly over the box; each pin adds a
  little demand in its bin (escape). Bin supply = routable layers x bin area / track pitch.
  Cost = area-weighted mean of max(0, utilization - target)^2, so only crowded bins pay.
  Incremental: the overlap of a box with the bins factorizes into x and y weights, so a
  net's contribution is an outer product; a move re-adds only the touched nets inside the
  bins they cover, before and after.
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
    """RUDY congestion tied to an Annealer's net pin lists (`ann.nx`, `ann.ny`)."""

    def __init__(self, P, ann, bins=None, target=0.6, pin_demand=0.6, signal_only=False):
        self.P = P
        self.ann = ann
        x0, y0, x1, y1 = P.outline.bounds
        span = max(x1 - x0, y1 - y0)
        b = bins or max(0.8, span / 32.0)
        self.nbx = max(1, int(math.ceil((x1 - x0) / b)))
        self.nby = max(1, int(math.ceil((y1 - y0) / b)))
        self.ex = np.linspace(x0, x0 + self.nbx * b, self.nbx + 1)
        self.ey = np.linspace(y0, y0 + self.nby * b, self.nby + 1)
        self.bin_area = b * b
        layers = len(P.board.stackup.copper) if P.board.stackup else 2
        rules = P.board.rules
        pitch = max(0.25, (rules.track_min if rules and rules.track_min else 0.2) + P.clr_min)
        self.supply = layers * self.bin_area / pitch     # mm of track per bin
        self.target = target
        self.pin_demand = pin_demand
        self.D = np.zeros((self.nbx, self.nby))
        self.contrib = {}      # net -> (kx0, ky0, block) currently added
        self.w = []
        for net in P.nets:
            w = net.weight
            if signal_only and net.kind in ("ground", "power"):
                w = 0.0
            self.w.append(w)
        self.pending = None
        for j in range(len(P.nets)):
            c = self._net_block(j)
            if c is not None:
                self._add(c, +1.0)
                self.contrib[j] = c
        self.norm = 1.0 / (self.nbx * self.nby)

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

    def _add(self, c, s, D=None, ox=0, oy=0):
        kx, ky, block = c
        D = self.D if D is None else D
        D[kx - ox:kx - ox + block.shape[0], ky - oy:ky - oy + block.shape[1]] += s * block

    def _f(self, D):
        u = D / self.supply - self.target
        return float(np.square(np.clip(u, 0.0, None)).sum())

    def local_cost(self, nets):
        return 0.0

    def trial(self, nets):
        """Cost change if the touched nets take their current (moved) pin boxes."""
        olds = {j: self.contrib.get(j) for j in nets}
        news = {j: self._net_block(j) for j in nets}
        boxes = [c for c in list(olds.values()) + list(news.values()) if c is not None]
        if not boxes:
            self.pending = None
            return 0.0
        x0 = min(c[0] for c in boxes)
        x1 = max(c[0] + c[2].shape[0] for c in boxes)
        y0 = min(c[1] for c in boxes)
        y1 = max(c[1] + c[2].shape[1] for c in boxes)
        R = self.D[x0:x1, y0:y1]
        before = self._f(R)
        Rn = R.copy()
        for j in nets:
            if olds[j] is not None:
                self._add(olds[j], -1.0, Rn, x0, y0)
            if news[j] is not None:
                self._add(news[j], +1.0, Rn, x0, y0)
        after = self._f(Rn)
        self.pending = (x0, x1, y0, y1, Rn, news)
        return (after - before) * self.norm

    def commit(self):
        if self.pending is None:
            return
        x0, x1, y0, y1, Rn, news = self.pending
        self.D[x0:x1, y0:y1] = Rn
        for j, c in news.items():
            if c is None:
                self.contrib.pop(j, None)
            else:
                self.contrib[j] = c
        self.pending = None

    def revert(self):
        self.pending = None

    def total(self):
        return self._f(self.D) * self.norm

    def peak(self):
        return float((self.D / self.supply).max()) if self.D.size else 0.0


def routability_report(P, st):
    """Signal-only HPWL (H11) and RUDY numbers of a placement, for reports."""
    from .anneal import Annealer
    ann = Annealer(P, st.copy(), terms=None, w_cong=1.0)
    c = ann.cong
    util = c.D / c.supply
    return dict(hpwl=round(st.hpwl(), 2), hpwl_signal=round(st.hpwl(signal_only=True), 2),
                rudy_peak=round(float(util.max()), 3), rudy_mean=round(float(util.mean()), 3),
                rudy_overflow=round(c.total(), 5))
