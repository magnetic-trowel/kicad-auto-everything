# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Experimental autoplacer for kaebench place tasks (research quality).

Algorithms (--algo):
  rand      random positions and rotations, then the legalizer (measures the legalizer alone)
  greedy    connectivity-ordered constructive placement on a grid, 4 rotations, then legalizer
  sa        greedy seed, then simulated annealing on weighted HPWL + ratsnest (MST) crossings
            + overlap/outside penalty with a sqrt(pins) escape halo, then legalizer
  sa-best   N annealing runs from different seeds; each is routed by a short Freerouting
            run in the loop and the one with fewest unrouted items wins (successive-halving lite)
  sa-loop   anneal, route, raise the weights of failed nets 3x and re-anneal only the parts on
            them; keep a round only if unrouted items drop, else revert and widen the moves
            (KRT place_route_loop, with Freerouting as the router)

Geometry comes from kicad_helper.py (pcbnew in KiCad's Python): rectangles and pad offsets
per rotation are read from pcbnew, never computed here. Footprint sides are kept.

Usage (as a kaebench --command):
  place.py --algo sa --input {input} --output {output} --workdir {workdir} --attempt {attempt} --timeout {timeout}
"""
import argparse
import json
import math
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import shapely
from shapely.geometry import Polygon, box
from shapely.ops import unary_union

HERE = Path(__file__).resolve().parent
POWER_RE = re.compile(r"^(/)?([+-]?\d+V\d*|.*GND.*|VCC.*|VDD.*|VSS.*|VBUS.*|VBAT.*|VIN.*|V\+|V-|.*PWR.*|.*3V3.*|.*5V.*)$", re.I)


SCRIPTS = {"helper": HERE / "kicad_helper.py"}


def stage_scripts(work):
    """Copy the pcbnew scripts into the work dir. Inside the kaebench sandbox the KiCad
    container sees the attempt's work dir but not this checkout."""
    import kaebench.tools as kt
    d = Path(work) / "_scripts"
    d.mkdir(parents=True, exist_ok=True)
    SCRIPTS["helper"] = Path(shutil.copy2(HERE / "kicad_helper.py", d / "kicad_helper.py"))
    ops = Path(shutil.copy2(kt.ops_script(), d / "pcbnew_ops.py"))
    kt.ops_script = lambda: str(ops)


def kicad_py(*args, timeout=600):
    wrap = shlex.split(os.environ.get("KAE_KICAD_WRAP", ""))
    py = os.environ.get("KAE_KICAD_PYTHON", "python3")
    r = subprocess.run([*wrap, *shlex.split(py), str(SCRIPTS["helper"]), *map(str, args)],
                       capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError(f"kicad_helper {args[0]} failed: {r.stderr[-2000:]}")
    return r.stdout


# ---------------------------------------------------------------- problem


def _poly(p):
    return Polygon(p["outer"], p["holes"]).buffer(0)


class Problem:
    def __init__(self, g, halo_base=0.15, halo_coef=0.12, margin=None):
        self.g = g
        board = unary_union([_poly(p) for p in g["outline"]])
        m = max(g.get("edge_clearance") or 0.0, 0.25) if margin is None else margin
        self.board = board
        region = board.buffer(-m, join_style="mitre")
        kf = [unary_union([_poly(p) for p in k["polys"]]) for k in g["keepouts"] if k["front"]]
        kb = [unary_union([_poly(p) for p in k["polys"]]) for k in g["keepouts"] if k["back"]]
        self.region = {False: region.difference(unary_union(kf)) if kf else region,
                       True: region.difference(unary_union(kb)) if kb else region}
        self.region[None] = self.region[False].intersection(self.region[True])  # THT: both sides
        for r in self.region.values():
            shapely.prepare(r)
        self.bbox = np.array(region.bounds)
        self.diag = float(np.hypot(*(self.bbox[2:] - self.bbox[:2])))
        parts = g["free"]
        self.n = n = len(parts)
        self.uuid = [p["uuid"] for p in parts]
        self.ref = [p["ref"] for p in parts]
        self.back = np.array([p["back"] for p in parts])
        self.tht = np.array([p["tht"] for p in parts])
        # rect per part per rotation, relative to the footprint origin
        self.rects = np.array([[r["rect"] for r in p["rots"]] for p in parts]).reshape(n, 4, 4)
        self.npads = np.array([len(p["rots"][0]["pads"]) for p in parts])
        self.area = (self.rects[:, 0, 2] - self.rects[:, 0, 0]) * (self.rects[:, 0, 3] - self.rects[:, 0, 1])
        # escape halo: half on each side of every rectangle, grows with sqrt(pins); shrinks to
        # nothing as the parts fill the board (fill 0.55 -> full halo, 0.75 -> none)
        self.fill = float(self.area.sum() / max(self.region[None].area, 1e-9))
        self.halo_scale = float(np.clip((0.75 - self.fill) / 0.2, 0.0, 1.0))
        self.halo = (halo_base + halo_coef * np.sqrt(self.npads)) * self.halo_scale
        # conflicts: same side, or either part has holes through the board
        same = self.back[:, None] == self.back[None, :]
        self.conflict = same | self.tht[:, None] | self.tht[None, :]
        np.fill_diagonal(self.conflict, False)
        # fixed obstacles (locked footprints)
        fx = g["fixed"]
        self.frects = np.array([f["rect"] for f in fx]).reshape(-1, 4)
        fback = np.array([f["back"] for f in fx], dtype=bool)
        ftht = np.array([f["tht"] for f in fx], dtype=bool)
        self.fconflict = (self.back[:, None] == fback[None, :]) | self.tht[:, None] | ftht[None, :]
        # nets: pins are (part, pad index) or fixed points
        names = {}
        pins_part, pins_pad, pins_fixed = [], [], []
        for i, p in enumerate(parts):
            for k, pad in enumerate(p["rots"][0]["pads"]):
                if pad[2]:
                    names.setdefault(pad[2], []).append(len(pins_part))
                    pins_part.append(i)
                    pins_pad.append(k)
                    pins_fixed.append((0.0, 0.0))
        for f in fx:
            for pad in f["pads"]:
                if pad[2]:
                    names.setdefault(pad[2], []).append(len(pins_part))
                    pins_part.append(-1)
                    pins_pad.append(-1)
                    pins_fixed.append((pad[0], pad[1]))
        self.pin_part = np.array(pins_part, dtype=int)
        self.pin_pad = np.array(pins_pad, dtype=int)
        self.pin_fixed = np.array(pins_fixed, dtype=float).reshape(-1, 2)
        # offsets[p][rot] for each pin of a free part
        maxp = max([len(p["rots"][0]["pads"]) for p in parts] + [1])
        self.offs = np.zeros((n, 4, maxp, 2))
        for i, p in enumerate(parts):
            for r in range(4):
                pads = p["rots"][r]["pads"]
                if pads:
                    self.offs[i, r, :len(pads)] = np.array([q[:2] for q in pads])
        pour = set(g["pour_nets"])
        self.nets = []
        self.net_name = []
        self.weight = []
        self.signal = []
        for name, idx in names.items():
            if len(idx) < 2 or len({(self.pin_part[j], self.pin_pad[j]) if self.pin_part[j] >= 0 else j
                                    for j in idx}) < 2:
                continue
            parts_on = {self.pin_part[j] for j in idx if self.pin_part[j] >= 0}
            if not parts_on:
                continue
            power = name in pour or POWER_RE.match(name) is not None
            w = 0.1 if name in pour else (0.3 if power else 1.0)
            if len(idx) > 12:
                w = min(w, 0.3)
            self.nets.append(np.array(idx))
            self.net_name.append(name)
            self.weight.append(w)
            self.signal.append(not power and len(idx) <= 16)
        self.weight = np.array(self.weight)
        self.base_weight = self.weight.copy()
        self.signal = np.array(self.signal, dtype=bool)
        self.part_nets = [[] for _ in range(n)]
        for k, idx in enumerate(self.nets):
            for i in {self.pin_part[j] for j in idx if self.pin_part[j] >= 0}:
                self.part_nets[i].append(k)
        self.part_pins = [np.nonzero(self.pin_part == i)[0] for i in range(n)]

    # geometry of a state
    def part_rect(self, i, x, y, r, halo=True):
        h = self.halo[i] / 2 if halo else 0.0
        q = self.rects[i, r]
        return np.array([x + q[0] - h, y + q[1] - h, x + q[2] + h, y + q[3] + h])

    def side_key(self, i):
        return None if self.tht[i] else bool(self.back[i])


def _overlap(a, B):
    """Overlap areas of rect a with rects B (n x 4)."""
    if len(B) == 0:
        return np.zeros(0)
    w = np.minimum(a[2], B[:, 2]) - np.maximum(a[0], B[:, 0])
    h = np.minimum(a[3], B[:, 3]) - np.maximum(a[1], B[:, 1])
    return np.clip(w, 0, None) * np.clip(h, 0, None)


def _mst_edges(pts):
    """MST of a small point set (Prim), as an (k-1) x 4 array of segments."""
    k = len(pts)
    if k < 2:
        return np.zeros((0, 4))
    if k == 2:
        return np.array([[*pts[0], *pts[1]]])
    d = np.abs(pts[:, None, :] - pts[None, :, :]).sum(-1)
    inside = np.zeros(k, bool)
    inside[0] = True
    best = d[0].copy()
    parent = np.zeros(k, int)
    out = []
    for _ in range(k - 1):
        b = np.where(inside, np.inf, best)
        j = int(np.argmin(b))
        out.append([*pts[parent[j]], *pts[j]])
        inside[j] = True
        upd = d[j] < best
        parent[upd] = j
        best = np.minimum(best, d[j])
    return np.array(out)


def _crossings(A, B):
    """Proper crossings between segment sets A (m x 4) and B (n x 4)."""
    if len(A) == 0 or len(B) == 0:
        return 0
    p1, p2 = A[:, None, :2], A[:, None, 2:]
    q1, q2 = B[None, :, :2], B[None, :, 2:]

    def orient(a, b, c):
        return (b[..., 0] - a[..., 0]) * (c[..., 1] - a[..., 1]) - (b[..., 1] - a[..., 1]) * (c[..., 0] - a[..., 0])
    d1, d2 = orient(p1, p2, q1), orient(p1, p2, q2)
    d3, d4 = orient(q1, q2, p1), orient(q1, q2, p2)
    eps = 1e-9
    return int(np.count_nonzero((d1 * d2 < -eps) & (d3 * d4 < -eps)))


class State:
    """Placement state with incremental cost: weighted HPWL + crossing weight x crossings
    + mu x violation (halo-inflated overlap area + area outside the allowed region)."""

    def __init__(self, P, x, y, r, cross_w, mu):
        self.P = P
        self.x, self.y, self.r = x.astype(float), y.astype(float), r.astype(int)
        self.cross_w, self.mu = cross_w, mu
        self.pins = P.pin_fixed.copy()
        for i in range(P.n):
            self._set_pins(i)
        self.rect = np.array([P.part_rect(i, self.x[i], self.y[i], self.r[i]) for i in range(P.n)]).reshape(-1, 4)
        self.net_wl = np.array([self._hpwl(k) for k in range(len(P.nets))])
        self.edges = {k: self._mst(k) for k in range(len(P.nets)) if P.signal[k]}
        self.cross = self._all_crossings()
        self.outside = np.array([self._outside(i, self.rect[i]) for i in range(P.n)])
        self.viol = self._total_violation()

    def _set_pins(self, i):
        idx = self.P.part_pins[i]
        self.pins[idx] = self.P.offs[i, self.r[i], self.P.pin_pad[idx]] + (self.x[i], self.y[i])

    def _hpwl(self, k):
        p = self.pins[self.P.nets[k]]
        return float(np.ptp(p[:, 0]) + np.ptp(p[:, 1]))

    def _mst(self, k):
        return _mst_edges(np.unique(self.pins[self.P.nets[k]].round(4), axis=0))

    def _all_crossings(self):
        ks = list(self.edges)
        total = 0
        for a in range(len(ks)):
            rest = [self.edges[k] for k in ks[a + 1:]]
            if rest:
                total += _crossings(self.edges[ks[a]], np.concatenate(rest))
        return total

    def _outside(self, i, rect):
        reg = self.P.region[self.P.side_key(i)]
        b = box(*rect)
        return float(b.area - b.intersection(reg).area) if not reg.contains(b) else 0.0

    def _part_violation(self, i, rect, skip=()):
        P = self.P
        mask = P.conflict[i].copy()
        for j in skip:
            mask[j] = False
        v = _overlap(rect, self.rect[mask]).sum()
        if len(P.frects):
            fr = P.frects[P.fconflict[i]]
            if len(fr):
                h = P.halo[i] / 2
                v += _overlap(rect, fr + np.array([-h, -h, h, h])).sum()
        return float(v)

    def _total_violation(self):
        v = 0.0
        for i in range(self.P.n):
            v += self._part_violation(i, self.rect[i], skip=range(i)) + self.outside[i]
        return v

    def cost(self):
        return float((self.P.weight * self.net_wl).sum()) + self.cross_w * self.cross + self.mu * self.viol

    def violators(self):
        return [i for i in range(self.P.n)
                if self.outside[i] > 1e-6 or self._part_violation(i, self.rect[i]) > 1e-6]

    # a move changes the poses of parts `moved`; returns delta and an undo/commit record
    def try_move(self, moved, poses):
        P = self.P
        old = {i: (self.x[i], self.y[i], self.r[i], self.rect[i].copy(), self.outside[i]) for i in moved}
        v_old = sum(self._part_violation(i, self.rect[i]) + self.outside[i] for i in moved)
        if len(moved) == 2:
            a, b = moved
            v_old -= _overlap(self.rect[a], self.rect[b][None])[0] if P.conflict[a, b] else 0.0
        nets = sorted({k for i in moved for k in P.part_nets[i]})
        wl_old = self.net_wl[nets].copy()
        sig = [k for k in nets if P.signal[k]]
        e_old = {k: self.edges[k] for k in sig}
        for i, (x, y, r) in zip(moved, poses):
            self.x[i], self.y[i], self.r[i] = x, y, r
            self._set_pins(i)
            self.rect[i] = P.part_rect(i, x, y, r)
            self.outside[i] = self._outside(i, self.rect[i])
        v_new = sum(self._part_violation(i, self.rect[i]) + self.outside[i] for i in moved)
        if len(moved) == 2:
            a, b = moved
            v_new -= _overlap(self.rect[a], self.rect[b][None])[0] if P.conflict[a, b] else 0.0
        for k in nets:
            self.net_wl[k] = self._hpwl(k)
        dcross = 0
        if sig:
            others = [self.edges[k] for k in self.edges if k not in e_old]
            others = np.concatenate(others) if others else np.zeros((0, 4))
            e_new = {k: self._mst(k) for k in sig}
            dcross = _crossings(np.concatenate(list(e_new.values())), others) - \
                _crossings(np.concatenate(list(e_old.values())), others)
            dcross += self._within(e_new) - self._within(e_old)
            for k, e in e_new.items():
                self.edges[k] = e
        dwl = float((P.weight[nets] * (self.net_wl[nets] - wl_old)).sum())
        delta = dwl + self.cross_w * dcross + self.mu * (v_new - v_old)
        rec = (moved, old, nets, wl_old, e_old, dcross, v_new - v_old)
        return delta, rec

    @staticmethod
    def _within(es):
        ks = list(es)
        t = 0
        for a in range(len(ks)):
            for b in range(a + 1, len(ks)):
                t += _crossings(es[ks[a]], es[ks[b]])
        return t

    def commit(self, rec):
        _, _, _, _, _, dcross, dviol = rec
        self.cross += dcross
        self.viol += dviol

    def undo(self, rec):
        moved, old, nets, wl_old, e_old, _, _ = rec
        for i in moved:
            self.x[i], self.y[i], self.r[i], self.rect[i], self.outside[i] = old[i]
            self._set_pins(i)
        self.net_wl[nets] = wl_old
        for k, e in e_old.items():
            self.edges[k] = e

    def refresh(self):
        """Recompute everything (after weights or mu change)."""
        self.net_wl = np.array([self._hpwl(k) for k in range(len(self.P.nets))])
        self.cross = self._all_crossings()
        self.viol = self._total_violation()

    def poses(self):
        return {self.P.uuid[i]: [round(float(self.x[i]), 4), round(float(self.y[i]), 4), 90 * int(self.r[i])]
                for i in range(self.P.n)}


# ---------------------------------------------------------------- seeds


def _grid(P, step):
    x0, y0, x1, y1 = P.bbox
    xs = np.arange(x0, x1 + 1e-9, step)
    ys = np.arange(y0, y1 + 1e-9, step)
    gx, gy = np.meshgrid(xs, ys)
    return gx.ravel(), gy.ravel()


def _legal_mask(P, i, r, cx, cy, placed_rects, placed_idx):
    """Candidate rect centres (cx, cy) for part i at rotation r: in region and no conflict."""
    q = P.rects[i, r]
    h = P.halo[i] / 2
    ox, oy = (q[0] + q[2]) / 2, (q[1] + q[3]) / 2
    x, y = cx - ox, cy - oy
    rx0, ry0, rx1, ry1 = x + q[0] - h, y + q[1] - h, x + q[2] + h, y + q[3] + h
    ok = shapely.contains(P.region[P.side_key(i)], shapely.box(rx0, ry0, rx1, ry1))
    if placed_idx:
        B = placed_rects[[j for j in placed_idx if P.conflict[i, j]]]
        if len(B):
            ok &= ~(((np.minimum(rx1[:, None], B[None, :, 2]) - np.maximum(rx0[:, None], B[None, :, 0])) > 1e-6) &
                    ((np.minimum(ry1[:, None], B[None, :, 3]) - np.maximum(ry0[:, None], B[None, :, 1])) > 1e-6)).any(1)
    fr = P.frects[P.fconflict[i]] if len(P.frects) else np.zeros((0, 4))
    if len(fr):
        ok &= ~(((np.minimum(rx1[:, None], fr[None, :, 2] + h) - np.maximum(rx0[:, None], fr[None, :, 0] - h)) > 1e-6) &
                ((np.minimum(ry1[:, None], fr[None, :, 3] + h) - np.maximum(ry0[:, None], fr[None, :, 1] - h)) > 1e-6)).any(1)
    return ok, x, y


def _incremental_wl(P, i, r, x, y, pins, placed_pin):
    """Weighted HPWL of i's nets over already-placed pins plus i's pins at (x, y, r), vectorized
    over candidate origins x, y."""
    cost = np.zeros(len(x))
    for k in P.part_nets[i]:
        idx = P.nets[k]
        mine = idx[P.pin_part[idx] == i]
        other = idx[(P.pin_part[idx] != i) & placed_pin[idx]]
        off = P.offs[i, r, P.pin_pad[mine]]
        px = x[:, None] + off[None, :, 0]
        py = y[:, None] + off[None, :, 1]
        lox, hix, loy, hiy = px.min(1), px.max(1), py.min(1), py.max(1)
        if len(other):
            o = pins[other]
            lox, hix = np.minimum(lox, o[:, 0].min()), np.maximum(hix, o[:, 0].max())
            loy, hiy = np.minimum(loy, o[:, 1].min()), np.maximum(hiy, o[:, 1].max())
        cost += P.weight[k] * (hix - lox + hiy - loy)
    return cost


def place_constructive(P, rng, random_order=False, step=None, jitter=0.0):
    """Greedy: place parts one by one (most connected to what is placed first) at the legal
    grid spot and rotation with the least added wirelength. Parts that fit nowhere go to the
    least-bad spot and are left for the annealer / legalizer."""
    n = P.n
    step = step or float(np.clip(P.diag / 90, 0.25, 1.0))
    gx, gy = _grid(P, step)
    pins = P.pin_fixed.copy()
    placed_pin = P.pin_part < 0
    x, y, r = np.zeros(n), np.zeros(n), np.zeros(n, int)
    rects = np.zeros((n, 4))
    placed = []
    todo = set(range(n))
    centre = np.array(P.region[False].representative_point().coords[0]) if not P.region[False].is_empty else \
        (P.bbox[:2] + P.bbox[2:]) / 2
    while todo:
        if random_order:
            i = int(rng.choice(sorted(todo)))
        else:
            def score(i):
                s = 0.0
                for k in P.part_nets[i]:
                    if placed_pin[P.nets[k]].any():
                        s += P.weight[k]
                return (s, P.npads[i] * P.area[i] ** 0.5)
            i = max(sorted(todo), key=score)
        best = None
        for rot in range(4):
            ok, xx, yy = _legal_mask(P, i, rot, gx, gy, rects, placed)
            if not ok.any():
                continue
            xx, yy = xx[ok], yy[ok]
            c = _incremental_wl(P, i, rot, xx, yy, pins, placed_pin)
            c = c + 0.02 * np.hypot(gx[ok] - centre[0], gy[ok] - centre[1])
            if jitter:
                c = c + jitter * rng.random(len(c)) * (c.std() + 1e-9)
            j = int(np.argmin(c))
            if best is None or c[j] < best[0]:
                best = (c[j], xx[j], yy[j], rot)
        if best is None:  # no legal spot: random spot in the region, fixed up later
            q = P.rects[i, 0]
            x0, y0, x1, y1 = P.bbox
            best = (0, rng.uniform(x0, x1) - (q[0] + q[2]) / 2, rng.uniform(y0, y1) - (q[1] + q[3]) / 2, 0)
        _, x[i], y[i], r[i] = best
        rects[i] = P.part_rect(i, x[i], y[i], r[i])
        idx = P.part_pins[i]
        pins[idx] = P.offs[i, r[i], P.pin_pad[idx]] + (x[i], y[i])
        placed_pin[idx] = True
        placed.append(i)
        todo.discard(i)
    return x, y, r


def place_random(P, rng):
    x0, y0, x1, y1 = P.bbox
    r = rng.integers(0, 4, P.n)
    x = np.zeros(P.n)
    y = np.zeros(P.n)
    for i in range(P.n):
        q = P.rects[i, r[i]]
        x[i] = rng.uniform(x0, x1) - (q[0] + q[2]) / 2
        y[i] = rng.uniform(y0, y1) - (q[1] + q[3]) / 2
    return x, y, r


# ---------------------------------------------------------------- annealing and legalization


def anneal(S, rng, moves, movable=None, t_start=None, t_end_frac=1e-3, max_step=None, mu_end=None):
    P = S.P
    movable = list(range(P.n)) if movable is None else list(movable)
    if not movable:
        return S
    max_step = max_step or P.diag / 3
    mu0 = S.mu
    mu_end = mu_end or mu0 * 30

    def propose(scale):
        u = rng.random()
        i = int(rng.choice(movable))
        if u < 0.55:
            s = max(0.1, scale)
            return [i], [(S.x[i] + rng.normal(0, s), S.y[i] + rng.normal(0, s), S.r[i])]
        if u < 0.75:  # rotate about the rectangle centre
            nr = int((S.r[i] + rng.integers(1, 4)) % 4)
            qa, qb = P.rects[i, S.r[i]], P.rects[i, nr]
            cx, cy = S.x[i] + (qa[0] + qa[2]) / 2, S.y[i] + (qa[1] + qa[3]) / 2
            return [i], [(cx - (qb[0] + qb[2]) / 2, cy - (qb[1] + qb[3]) / 2, nr)]
        if u < 0.92 and len(movable) > 1:  # swap rectangle centres
            j = int(rng.choice(movable))
            if j == i:
                return None
            qi, qj = P.rects[i, S.r[i]], P.rects[j, S.r[j]]
            ci = (S.x[i] + (qi[0] + qi[2]) / 2, S.y[i] + (qi[1] + qi[3]) / 2)
            cj = (S.x[j] + (qj[0] + qj[2]) / 2, S.y[j] + (qj[1] + qj[3]) / 2)
            return [i, j], [(cj[0] - (qi[0] + qi[2]) / 2, cj[1] - (qi[1] + qi[3]) / 2, S.r[i]),
                            (ci[0] - (qj[0] + qj[2]) / 2, ci[1] - (qj[1] + qj[3]) / 2, S.r[j])]
        x0, y0, x1, y1 = P.bbox  # jump
        q = P.rects[i, S.r[i]]
        return [i], [(rng.uniform(x0, x1) - (q[0] + q[2]) / 2, rng.uniform(y0, y1) - (q[1] + q[3]) / 2, S.r[i])]

    # calibrate the start temperature on random moves
    if t_start is None:
        ds = []
        for _ in range(60):
            m = propose(max_step / 3)
            if m is None:
                continue
            d, rec = S.try_move(*m)
            S.undo(rec)
            ds.append(abs(d))
        t_start = float(np.median(ds)) + 1e-6 if ds else 1.0
    t0 = time.monotonic()
    T = t_start
    it = 0
    while True:
        frac = it / moves  # budgets are move counts, so results do not depend on host load
        if frac >= 1 or time.monotonic() - t0 > 900:
            break
        if it % 200 == 0:
            T = t_start * (t_end_frac ** frac)
            new_mu = mu0 * (mu_end / mu0) ** frac
            if abs(new_mu - S.mu) > 1e-9:
                S.mu = new_mu
        it += 1
        m = propose(max_step * (0.02 + 0.98 * (1 - frac)))
        if m is None:
            continue
        d, rec = S.try_move(*m)
        if d <= 0 or rng.random() < math.exp(-d / T):
            S.commit(rec)
        else:
            S.undo(rec)
    S.mu = mu0
    S.refresh()
    S.iterations = it
    return S


def legalize(S, rng, rounds=3):
    """Move each part that overlaps or sticks out to the legal grid spot (any rotation) with
    the least added wirelength plus displacement; finer grid if nothing fits."""
    P = S.P
    for rnd in range(rounds):
        bad = S.violators()
        if not bad:
            return True
        bad.sort(key=lambda i: -P.area[i])
        for i in bad:
            if i not in S.violators():
                continue
            others = [j for j in range(P.n) if j != i]
            pins = S.pins.copy()
            placed_pin = np.ones(len(pins), bool)
            placed_pin[P.part_pins[i]] = False
            q0 = P.rects[i, S.r[i]]
            c0 = np.array([S.x[i] + (q0[0] + q0[2]) / 2, S.y[i] + (q0[1] + q0[3]) / 2])
            best = None
            for step in (float(np.clip(P.diag / 150, 0.1, 0.5)), 0.1, 0.05):
                gx, gy = _grid(P, step)
                for rot in range(4):
                    ok, xx, yy = _legal_mask(P, i, rot, gx, gy, S.rect, others)
                    if not ok.any():
                        continue
                    c = _incremental_wl(P, i, rot, xx[ok], yy[ok], pins, placed_pin)
                    c = c + 0.5 * np.hypot(gx[ok] - c0[0], gy[ok] - c0[1])
                    j = int(np.argmin(c))
                    if best is None or c[j] < best[0]:
                        best = (c[j], xx[ok][j], yy[ok][j], rot)
                if best is not None:
                    break
            if best is None:
                # try evicting: nothing fits; leave it
                continue
            d, rec = S.try_move([i], [best[1:]])
            S.commit(rec)
        S.refresh()
    return not S.violators()


def make_legal(S, rng, moves=4000):
    """legalize(); if parts are still left over, drop the halos, shake the overlaps out with
    a short high-penalty anneal at low temperature, and legalize again. Returns (state, legal)."""
    if legalize(S, rng):
        return S, True
    P = S.P
    P.halo[:] = 0.0
    S = State(P, S.x, S.y, S.r, S.cross_w, S.mu * 50)
    anneal(S, rng, moves, t_start=1.0, max_step=P.diag / 10, mu_end=S.mu * 10)
    S.mu /= 50
    S.refresh()
    return S, legalize(S, rng, rounds=4)


# ---------------------------------------------------------------- router in the loop


def write_board(inp, poses, dst_dir):
    dst_dir = Path(dst_dir)
    dst_dir.mkdir(parents=True, exist_ok=True)
    pj = dst_dir / "poses.json"
    pj.write_text(json.dumps(poses))
    src = Path(inp)
    for f in src.parent.iterdir():  # project files beside the board
        if f.suffix in (".kicad_pro", ".kicad_dru", ".kicad_prl") and f.stem == src.stem:
            shutil.copy2(f, dst_dir / ("board" + f.suffix))
    out = dst_dir / "board.kicad_pcb"
    kicad_py("write", inp, pj, out)
    return out


def route_probe(board, work, passes, timeout):
    """Route a candidate with Freerouting (kaebench's own adapter) and count what is unrouted."""
    from kaebench.adapters import Freerouting
    work = Path(work)
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    t0 = time.monotonic()
    res = Freerouting(passes=passes).run("route", Path(board).parent, work, 0, timeout)
    if not res.output:
        return dict(unconnected=10 ** 6, failed={}, t=time.monotonic() - t0)
    d = json.loads(kicad_py("unconnected", res.output))
    d["t"] = round(time.monotonic() - t0, 1)
    return d


def _rank(d):
    return (d["unconnected"], d.get("vias", 0), d.get("length_mm", 0.0))


# ---------------------------------------------------------------- driver


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--algo", required=True, choices=["rand", "greedy", "sa", "sa-best", "sa-loop"])
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--workdir", default=".")
    ap.add_argument("--attempt", type=int, default=0)
    ap.add_argument("--timeout", type=float, default=600)
    ap.add_argument("--sa-moves", type=int, default=None, help="moves per annealing run (default 1500 x parts)")
    ap.add_argument("--cross-w", type=float, default=None, help="cost of one crossing (mm); default 0.25*diag")
    ap.add_argument("--halo-coef", type=float, default=0.12)
    ap.add_argument("--halo-base", type=float, default=0.15)
    ap.add_argument("--seeds", type=int, default=4)
    ap.add_argument("--seed", type=int, default=0, help="varies all random choices (the attempt index does too)")
    ap.add_argument("--rounds", type=int, default=6)
    ap.add_argument("--probe-passes", type=int, default=4)
    a = ap.parse_args(argv)
    t_start = time.monotonic()
    budget = a.timeout * 0.8 - 30  # leave time for writing and the harness
    work = Path(a.workdir) / "place"
    work.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(1000 + a.attempt + 7919 * a.seed)
    stage_scripts(work)
    gj = work / "geometry.json"
    kicad_py("extract", a.input, gj)
    g = json.loads(gj.read_text())
    P = Problem(g, halo_base=a.halo_base, halo_coef=a.halo_coef)
    log = dict(algo=a.algo, parts=P.n, nets=len(P.nets), signal_nets=int(P.signal.sum()), fixed=len(g["fixed"]))
    print(json.dumps(log), flush=True)
    if P.n == 0:
        shutil.copy2(a.input, a.output)
        return
    cross_w = a.cross_w if a.cross_w is not None else 0.25 * P.diag
    mu = 4.0
    sa_moves = a.sa_moves or int(np.clip(1500 * P.n, 20000, 120000))
    sa_s = sa_moves / 600  # rough seconds per run, used only to plan the time budget

    halo0 = P.halo.copy()
    log.update(fill=round(P.fill, 3), halo_scale=round(P.halo_scale, 2), cross_w=round(cross_w, 2), sa_moves=sa_moves)
    print(json.dumps(log), flush=True)

    def run_sa(seed_rng, jitter):
        P.halo[:] = halo0
        x, y, r = place_constructive(P, seed_rng, jitter=jitter)
        S = State(P, x, y, r, cross_w, mu)
        c0 = (S.cost(), S.cross, S.viol)
        anneal(S, seed_rng, sa_moves)
        S, ok = make_legal(S, seed_rng)
        print(json.dumps(dict(stage="sa", seed_cost=round(c0[0], 1), seed_cross=c0[1], seed_viol=round(c0[2], 1),
                              cost=round(S.cost(), 1), cross=S.cross, wl=round(float((P.weight * S.net_wl).sum()), 1),
                              iters=getattr(S, "iterations", None), legal=ok,
                              halo_dropped=bool(P.halo.sum() == 0 and halo0.sum() > 0))), flush=True)
        return S

    if a.algo == "rand":
        x, y, r = place_random(P, rng)
        S, ok = make_legal(State(P, x, y, r, cross_w, mu), rng)
    elif a.algo == "greedy":
        x, y, r = place_constructive(P, rng)
        S, ok = make_legal(State(P, x, y, r, cross_w, mu), rng)
    elif a.algo == "sa":
        S = run_sa(rng, 0.0)
        ok = not S.violators()
    else:
        probe_t = max(60.0, min(300.0, budget / 5))
        cands = []
        n_seeds = a.seeds if a.algo == "sa-best" else 1
        for s in range(n_seeds):
            if time.monotonic() - t_start > budget - sa_s - probe_t:
                break
            S_ = run_sa(np.random.default_rng(1000 + a.attempt * 100 + s + 7919 * a.seed), 0.0 if s == 0 else 0.3)
            b = write_board(a.input, S_.poses(), work / f"cand-{s}")
            d = route_probe(b, work / f"probe-{s}", a.probe_passes, probe_t)
            print(json.dumps(dict(stage="probe", cand=s, unconnected=d["unconnected"], vias=d.get("vias"),
                                  length=d.get("length_mm"), failed=sorted(d.get("failed", {}))[:12],
                                  t=d["t"], legal=not S_.violators())), flush=True)
            cands.append((not S_.violators(), d, S_))
        cands.sort(key=lambda c: (not c[0], _rank(c[1])))
        ok, best_d, S = cands[0]
        if a.algo == "sa-loop":
            step = P.diag / 12
            for rnd in range(a.rounds):
                if best_d["unconnected"] == 0 or time.monotonic() - t_start > budget - sa_s - probe_t:
                    break
                failed = [P.net_name.index(n) for n in best_d.get("failed", {}) if n in P.net_name]
                movers = sorted({i for k in failed for i in range(P.n) if k in P.part_nets[i]})
                if not movers:
                    break
                trial = State(P, S.x.copy(), S.y.copy(), S.r.copy(), cross_w, mu)
                P.weight[:] = P.base_weight
                P.weight[failed] *= 3.0
                trial.refresh()
                anneal(trial, rng, sa_moves // 2, movable=movers, max_step=step, t_end_frac=1e-2)
                P.weight[:] = P.base_weight
                trial.refresh()
                trial, legal = make_legal(trial, rng)
                b = write_board(a.input, trial.poses(), work / f"loop-{rnd}")
                d = route_probe(b, work / f"loop-probe-{rnd}", a.probe_passes, probe_t)
                better = legal and _rank(d) < _rank(best_d)
                print(json.dumps(dict(stage="loop", round=rnd, movers=len(movers), unconnected=d["unconnected"],
                                      vias=d.get("vias"), kept=better, step=round(step, 2), t=d["t"])), flush=True)
                if better:
                    S, best_d, ok = trial, d, legal
                else:
                    step *= 1.5
    poses = S.poses()
    out = write_board(a.input, poses, work / "final")
    shutil.copy2(out, a.output)
    print(json.dumps(dict(stage="done", legal=bool(ok), violators=[P.ref[i] for i in S.violators()],
                          cross=S.cross, wl=round(float((P.weight * S.net_wl).sum()), 1),
                          seconds=round(time.monotonic() - t_start, 1))), flush=True)


if __name__ == "__main__":
    sys.exit(main())
