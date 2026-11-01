# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Placement helpers on the World grid.

For a part at orientation ri, every candidate origin cell is scored at once:
  legal_map  courtyard free of other parts and inside the board, pad copper inside the
             edge clearance (correlation of occupancy with the part's raster: a summed-area
             table over the raster's rectangles, FFT for rasters of many rectangles)
  hpwl_map   HPWL of the part's nets as a function of its origin (separable: fx + fy)
and the routing state is managed with snapshot/restore so moves can be tried and undone.
"""
import math
import time

import numpy as np
from scipy.signal import correlate

from world import ROTS


RECT_MAX = 64  # more rectangles than this: FFT (about break-even on a 700x300 grid)
_RECTS = {}


def _rects(offs):
    """The kernel's cells as rectangles (dx0, dx1, dy0, dy1), inclusive: each row's runs of
    consecutive cells, merged down while the rows below have the same run."""
    key = (offs.dtype.str, offs.shape, offs.tobytes())
    r = _RECTS.get(key)
    if r is not None:
        return r
    rows = {}
    for dx, dy in {(int(a), int(b)) for a, b in offs}:
        rows.setdefault(dy, []).append(dx)
    runs = {}
    for dy, xs in rows.items():
        xs.sort()
        out, s = [], xs[0]
        for p, q in zip(xs, xs[1:] + [None]):
            if q != p + 1:
                out.append((s, p))
                s = q
        runs[dy] = out
    open_, done = {}, []
    for dy in range(min(runs), max(runs) + 2):
        cur = set(runs.get(dy, ()))
        for run in list(open_):
            if run not in cur:
                done.append((run[0], run[1], open_.pop(run), dy - 1))
        for run in cur:
            open_.setdefault(run, dy)
    if len(_RECTS) > 4096:
        _RECTS.clear()
    _RECTS[key] = done
    return done


_SATS = {}


def _sat(occ, R, pad_value):
    """(S, P): the summed-area table of occ padded by P >= R cells of pad_value, with a
    leading zero row and column."""
    exact = occ.dtype == bool and float(pad_value) in (0.0, 1.0)
    raw = np.ascontiguousarray(occ).tobytes()
    key = (hash(raw), occ.shape, occ.dtype.str, float(pad_value))
    hit = _SATS.get(key)
    if hit is not None and hit[1] >= R and hit[2] == raw:
        return hit[0], hit[1]
    P = -(-max(R, 1) // 16) * 16
    dt = np.int32 if exact else np.float64
    occ_p = np.pad(occ.astype(dt), P, constant_values=dt(pad_value))
    S = np.zeros((occ_p.shape[0] + 1, occ_p.shape[1] + 1), dt)
    np.cumsum(occ_p, 0, out=S[1:, 1:])
    np.cumsum(S[1:, 1:], 1, out=S[1:, 1:])
    if len(_SATS) >= 8:
        _SATS.pop(next(iter(_SATS)))
    _SATS[key] = (S, P, raw)
    return S, P


def corr(occ, offs, pad_value=1.0):
    """result[y, x] = sum_k occ[y + dy_k, x + dx_k]; out-of-grid reads pad_value."""
    if len(offs) == 0:
        return np.zeros(occ.shape)
    R = int(np.abs(offs).max())
    rects = _rects(offs)
    if len(rects) <= RECT_MAX:
        # summed-area table (cached by the map's content: legal_map sweeps reuse one
        # occupancy for every part and rotation); each rectangle is 4 lookups per cell,
        # exact for 0/1 maps
        H, W = occ.shape
        S, P = _sat(occ, R, pad_value)
        out = np.zeros((H, W), S.dtype)
        for x0, x1, y0, y1 in rects:
            ya, yb, xa, xb = P + y0, P + y1 + 1, P + x0, P + x1 + 1
            out += S[yb:yb + H, xb:xb + W]
            out -= S[ya:ya + H, xb:xb + W]
            out -= S[yb:yb + H, xa:xa + W]
            out += S[ya:ya + H, xa:xa + W]
        return out.astype(np.float64)
    K = np.zeros((2 * R + 1, 2 * R + 1))
    K[offs[:, 1] + R, offs[:, 0] + R] = 1.0
    occ_p = np.pad(occ.astype(np.float64), R, constant_values=pad_value)
    if K.sum() < 30:
        from scipy.ndimage import correlate as ncorr
        full = ncorr(occ_p, K, mode="constant", cval=pad_value)
        return full[R:-R, R:-R]
    return correlate(occ_p, K, mode="valid", method="fft")


class Kit:
    def __init__(self, world, router):
        self.w = world
        self.r = router
        g = world.g
        self.X = world.x0 + np.arange(world.W) * g
        self.Y = world.y0 + np.arange(world.H) * g

    def movable(self):
        mech = getattr(self.w, "mech", set())
        return [p.idx for p in self.w.parts if not p.locked and p.idx not in self.w.fixed
                and p.idx not in mech]

    # ------------------------------------------------------------ maps
    def legal_map(self, pi, ri, extra_block=None):
        """Bool map of origin cells where part pi (not placed) fits at orientation ri."""
        w = self.w
        part = w.parts[pi]
        r = w.part_raster(part, ri)
        bad = np.zeros((w.H, w.W))
        for plane, cells in r["keep"]:
            occ = w.court[plane] > 0
            if extra_block is not None and plane < 2:
                occ = occ | extra_block
            bad += corr(occ, cells, pad_value=0.0)
        if len(r["cu"]):
            bad += corr(~w.ok_cu, r["cu"])
        return bad < 0.5

    def overlap_map(self, pi, ri):
        """Courtyard cells of part pi that would overlap other parts, per origin cell
        (outside-board cells count as overlap)."""
        w = self.w
        part = w.parts[pi]
        r = w.part_raster(part, ri)
        tot = np.zeros((w.H, w.W))
        for plane, cells in r["keep"]:
            tot += corr((w.court[plane] > 0).astype(float), cells, pad_value=0.0)
        if len(r["cu"]):
            tot += corr(~w.ok_cu, r["cu"])
        return tot

    def pins_of(self, pi, ri):
        """[(net, (dx, dy))] pad centres relative to the origin cell centre."""
        w = self.w
        r = w.part_raster(w.parts[pi], ri)
        return [(ent["net"], ent["center"]) for ent in r["pads"] if ent["net"] in w.net_pins]

    def hpwl_map(self, pi, ri, weights=None):
        """HPWL (mm) of the nets touching part pi as a function of its origin cell, counting
        only pins of placed parts (pi itself excluded from 'placed')."""
        w = self.w
        by_net = {}
        for n, c in self.pins_of(pi, ri):
            by_net.setdefault(n, []).append(c)
        fx = np.zeros(w.W)
        fy = np.zeros(w.H)
        for n, cs in by_net.items():
            cs = np.array(cs)
            others = [w.pad_world(q, k) for q, k in w.net_pins[n] if q in w.pose and q != pi]
            wt = 1.0 if weights is None else weights.get(n, 1.0)
            if not others:
                continue
            o = np.array(others)
            fx += wt * (np.maximum(o[:, 0].max(), self.X + cs[:, 0].max()) -
                        np.minimum(o[:, 0].min(), self.X + cs[:, 0].min()))
            fy += wt * (np.maximum(o[:, 1].max(), self.Y + cs[:, 1].max()) -
                        np.minimum(o[:, 1].min(), self.Y + cs[:, 1].min()))
        return fy[:, None] + fx[None, :]

    def dist_map(self, tx, ty):
        return np.hypot(self.X[None, :] - tx, self.Y[:, None] - ty)

    def candidates(self, pi, rots=range(4), k=8, cost_extra=None, nms_cells=None, legal_extra=None):
        """Top-k legal poses (cost, cx, cy, ri) by HPWL (+ optional extra cost map per ri),
        with non-maximum suppression so candidates are spread out."""
        w = self.w
        nms = nms_cells or max(3, int(1.0 / w.g))
        out = []
        for ri in rots:
            L = self.legal_map(pi, ri, legal_extra)
            if not L.any():
                continue
            c = self.hpwl_map(pi, ri)
            if cost_extra is not None:
                c = c + cost_extra(pi, ri)
            c = np.where(L, c, np.inf)
            flat = np.argsort(c, axis=None)[: 400 * k]
            taken = []
            for f in flat:
                v = c.flat[f]
                if not np.isfinite(v):
                    break
                cy, cx = divmod(int(f), w.W)
                if any(abs(cx - a) < nms and abs(cy - b) < nms for a, b in taken):
                    continue
                taken.append((cx, cy))
                out.append((float(v), cx, cy, ri))
                if len(taken) >= k:
                    break
        out.sort()
        return out

    # ------------------------------------------------------------ routing state
    def snapshot(self, nets):
        r = self.r
        return {n: ([p.copy() for p in r.routes.get(n, [])], r.unrouted.get(n)) for n in nets}

    def restore(self, snap):
        r = self.r
        for n, (paths, unr) in snap.items():
            r.rip(n)
            r.routes[n] = paths
            for p in paths:
                r._stamp(n, p, 1)
            if unr:
                r.unrouted[n] = unr

    def conflicted_nets(self):
        return [n for n in list(self.r.routes) if self.r.routes[n] and self.r.net_conflicts(n)]

    def part_nets(self, pis):
        w = self.w
        s = set()
        for pi in pis:
            for ent in w.part_raster(w.parts[pi], 0)["pads"]:
                if ent["net"] in w.net_pins:
                    s.add(ent["net"])
        return s

    def net_cost(self, n, via_mm=2.0, unrouted_mm=None):
        w = self.w
        L = 0.0
        v = 0
        for p in self.r.routes.get(n, []):
            d = np.abs(np.diff(p, axis=0))
            same = d[:, 0] == 0
            L += float(np.sum(np.where((d[same, 1] + d[same, 2]) == 2, math.sqrt(2), 1.0))) * w.g
            v += int((~same).sum())
        unr = self.r.unrouted.get(n, 0)
        big = unrouted_mm if unrouted_mm is not None else self.unrouted_mm
        return L + via_mm * v + big * unr

    def total_cost(self):
        return sum(self.net_cost(n) for n in self.w.net_pins)

    @property
    def unrouted_mm(self):
        w = self.w
        return 2.0 * (w.W + w.H) * w.g  # one unrouted connection ~ a board perimeter

    def reroute(self, nets, iters=6):
        """Re-negotiate `nets` (plus any net whose copper became illegal) against the rest."""
        nets = set(nets) | set(self.conflicted_nets())
        nets = [n for n in nets if n in self.w.net_pins]
        if not nets:
            return nets
        self.r.pathfinder(nets=nets, iters=iters, pres0=0.5, pres_mul=1.8)
        return nets


class Clock:
    """Budget in CPU seconds of this process, so results do not depend on machine load."""
    def __init__(self, budget):
        self.t0 = time.process_time()
        self.budget = budget

    def left(self):
        return self.budget - (time.process_time() - self.t0)

    def frac(self):
        return min(1.0, (time.process_time() - self.t0) / max(1e-9, self.budget))
