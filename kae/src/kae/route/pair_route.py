# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Route differential pairs as pairs, before the general router (E37, R61).

A pair is one transmission line, so it is searched as one object and only then split:

1. **Ends.** Each pad of P is matched to the nearest pad of N (same footprint first, within
   `end_mm`): an end, at the pads' midpoint. Pads with no near partner stay for the bridge.
   The ends of a pair are joined by a tree (nearest first), one spine per edge.
2. **Spine.** One A* search for the pair's envelope (kae.route.critical_grid): width 2w + g, the
   two legs treated as one net (`merged`), layers from the board's stackup, inner plane layers
   out, a price where the reference plane is missing, vias priced as a pair and placed only
   where two side-by-side vias fit. The spine starts and ends in a small disc around each end
   (growing `radii`), not at the pads: fine-pitch neighbours stay out of the envelope's way.
3. **Legs.** Centreline +- (w + g)/2, mitred at corners; at a via, the legs flare to the two
   via centres. Which leg goes left is chosen to keep the fan-ins shortest. Each leg is checked
   exactly against the board's own rules (Space, the bridge's rule engine), real nets now.
4. **Fan-in.** Each leg end joins its pad with GridRouter.connect, at the pair's width.
5. **Skew.** Running skew comes from the corners and the fan-ins. Each spine is matched near where
   the mismatch arises: symmetric 45-degree bumps on the shorter leg (`max_skew_mm`, `bump_mm`),
   each checked exactly, on the straight piece nearest the mismatch.
6. **Return path** (`stitch`). Where a pair of vias changes the reference plane, a ground via is
   placed beside each signal via when the plane is on both layers.

Everything is written locked (`kae.route.critical_write`): the bridge routes around it. A pair
whose spine or fan-ins do not close is left to the bridge, with a reason in the report. Widths,
gaps and clearances are the board's: the net class's diff_pair_width and diff_pair_gap, then a
custom rule's, clamped by what KiCad will require.
"""
from __future__ import annotations

import math
import re
import tempfile
import time
import uuid as _uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from shapely.geometry import Point

from kae.board import pcbnew_io
from kae.board.kicad_file import load

from . import constraints as CN
from . import critical_write as W
from . import pairs as PAIRS
from . import rules as R
from .critical_grid import Anchor, GridRouter
from .critical_space import TOL, Space

DEFAULTS = dict(
    tiers=("rule", "interface"),    # which pairs to route (kae.route.pairs tiers)
    res=0.1,                        # envelope grid (mm)
    fan_res=0.05,                   # fan-in grid (mm)
    end_mm=6.0,                     # a P pad and an N pad farther apart than this are not an end
    radii=(0.4, 0.7, 1.0, 1.5, 2.0, 3.0, 4.5),          # discs around an end the spine may start in (tried in turn)
    end_group_mm=1.6,               # pads of the same net this close to an end are also landing sites
    short_mm=3.0,                   # ends closer than this: the two legs laid directly, no spine
    via_cost=8.0,                   # mm-equivalent of a pair of vias
    max_vias=4,                     # vias (pairs) per spine
    no_ref_cost=1.5,                # cost multiplier where no plane is adjacent to the layer (boards with planes)
    max_skew_mm=0.1,                # stop tuning a spine below this
    bump_mm=0.0,                    # 0: height from the skew, at most bump_max
    bump_max=1.5,                   # tallest skew bump (mm)
    stitch=True,                    # ground vias beside a via pair that changes reference plane
)


def _log(msg):
    import sys
    print(f"[kae.route.pair_route] {msg}", file=sys.stderr, flush=True)


@contextmanager
def merged(sp, p, n):
    """Within this block the N net's items are P's: the envelope's search treats the two legs as one net."""
    its = [it for lst in sp.items.values() for it in lst if it.net == n]
    for it in its:
        it.net = p
    try:
        yield
    finally:
        for it in its:
            it.net = n


class PairGrid(GridRouter):
    """GridRouter for the pair's envelope: a pair-via site is a cell where two real vias fit side by side (on
    one of four axes); a price where no plane is adjacent."""

    AXES = ((1.0, 0.0), (0.7071, 0.7071), (0.0, 1.0), (0.7071, -0.7071))

    def __init__(self, space, pitch_vv, no_ref_cost=1.5, **kw):
        super().__init__(space, pad_entry="centre", **kw)
        self.pitch_vv = pitch_vv
        self.no_ref_cost = no_ref_cost
        self._refs = {}
        self._axes = None               # (grid, ndarray of allowed-axis bitmasks) of the last via_allowed

    def via_allowed(self, grid, net, layers_all):
        base = super().via_allowed(grid, net, layers_all)
        h = self.pitch_vv / 2.0
        bits = np.zeros(base.shape, np.uint8)
        for k, (ax, ay) in enumerate(self.AXES):
            dx, dy = int(round(h * ax / grid.res)), int(round(h * ay / grid.res))
            a = np.zeros(base.shape, bool)
            b = np.zeros(base.shape, bool)
            for arr, sx, sy in ((a, dx, dy), (b, -dx, -dy)):
                src = base[max(0, sy):base.shape[0] + min(0, sy), max(0, sx):base.shape[1] + min(0, sx)]
                arr[max(0, -sy):base.shape[0] + min(0, -sy), max(0, -sx):base.shape[1] + min(0, -sx)] = src
            bits[a & b] |= 1 << k
        self._axes = (grid, bits)
        return bits > 0

    def axes_at(self, x, y):
        """Unit vectors along which a via pair centred at (x, y) fits, from the last via_allowed."""
        if self._axes is None:
            return list(self.AXES)
        grid, bits = self._axes
        i, j = grid.ij(x, y)
        if not grid.inside(i, j):
            return list(self.AXES)
        return [a for k, a in enumerate(self.AXES) if bits[j, i] >> k & 1] or list(self.AXES)

    def _ref_mask(self, grid, layer):
        key = (layer, grid.x0, grid.y0, grid.nx, grid.ny)
        m = self._refs.get(key)
        if m is None:
            sp = self.sp
            i = sp.cu.index(layer)
            adj = [l for l in (sp.cu[i - 1] if i > 0 else None, sp.cu[i + 1] if i < len(sp.cu) - 1 else None) if l]
            m = np.zeros((grid.ny, grid.nx), bool)
            for n, l, g, _ in sp.zones:
                if l in adj:
                    grid.within(g, 0.0, m)
            self._refs[key] = m
        return m

    def cost_layer(self, grid, net, layer, w, layer_factor=1.0, skip=()):
        c = super().cost_layer(grid, net, layer, w, layer_factor, skip)
        if self.no_ref_cost > 1.0 and self.sp.zones:
            m = self._ref_mask(grid, layer)
            if m.any():
                c[~m & np.isfinite(c)] *= self.no_ref_cost
        return c


# ----------------------------------------------------------------------------- geometry
def _unit(a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    d = math.hypot(dx, dy)
    return (dx / d, dy / d) if d > 1e-9 else (1.0, 0.0)


def _left(u):
    return (-u[1], u[0])


def _dedup(pts):
    out = []
    for p in pts:
        if not out or math.dist(out[-1], p) > 1e-6:
            out.append((float(p[0]), float(p[1])))
    return out


def offset_polyline(pts, d):
    """pts offset by d to the left (mitred at vertices; a corner that folds back is dropped)."""
    pts = _dedup(pts)
    if len(pts) < 2:
        return pts
    norm = [_left(_unit(a, b)) for a, b in zip(pts[:-1], pts[1:])]
    out = [(pts[0][0] + d * norm[0][0], pts[0][1] + d * norm[0][1])]
    for i in range(1, len(pts) - 1):
        n0, n1 = norm[i - 1], norm[i]
        bx, by = n0[0] + n1[0], n0[1] + n1[1]
        bl = math.hypot(bx, by)
        if bl < 1e-6:
            bx, by, s = n0[0], n0[1], d
        else:
            bx, by = bx / bl, by / bl
            cos = bx * n0[0] + by * n0[1]
            s = d / max(cos, 0.33)
        out.append((pts[i][0] + s * bx, pts[i][1] + s * by))
    out.append((pts[-1][0] + d * norm[-1][0], pts[-1][1] + d * norm[-1][1]))
    # drop a vertex whose offset piece runs against its centre piece (the inside of a tight corner)
    i = 1
    while i < len(out) - 1:
        c0 = _unit(pts[i - 1], pts[i])
        o0 = _unit(out[i - 1], out[i])
        if o0[0] * c0[0] + o0[1] * c0[1] < 0:
            del out[i]
            del pts[i]
        else:
            i += 1
    return out


def _cut(pts, f, end):
    """Shorten polyline `pts` by length f at its end (end=True) or start."""
    pts = list(pts)
    if end:
        pts = pts[::-1]
    left = f
    i = 0
    while i < len(pts) - 1:
        L = math.dist(pts[i], pts[i + 1])
        if L > left:
            t = left / L
            q = (pts[i][0] + (pts[i + 1][0] - pts[i][0]) * t, pts[i][1] + (pts[i + 1][1] - pts[i][1]) * t)
            out = [q] + pts[i + 1:]
            return out[::-1] if end else out
        left -= L
        i += 1
    return (pts[::-1] if end else pts)


def _runs(rt):
    """Route segments as [(layer, pts)] in route order."""
    runs = []
    for (l, a, b) in rt.segs:
        if runs and runs[-1][0] == l and math.dist(runs[-1][1][-1], a) < 1e-6:
            runs[-1][1].append(b)
        else:
            runs.append((l, [a, b]))
    return runs


def _clear_ends(sp, net, other, runs, w, step=0.25, tries=12):
    """Shorten each run's outer end until the end piece clears the partner net's pads (the fan-in starts there).
    Only the first and last run have a free end; inner run ends are via sites and stay."""
    runs = [list(r) for r in runs]

    def bad(a, b, layer):
        v = sp.track_violations(net, layer, w, a, b, first=False)
        return any(getattr(x[0], "kind", "") == "pad" and getattr(x[0], "net", "") == other for x in v)

    for idx, is_end in ((0, False), (len(runs) - 1, True)):
        if not runs:
            continue
        layer, pts = runs[idx][0], runs[idx][1]
        pts = list(pts)
        for _ in range(tries):
            if len(pts) < 2:
                break
            a, b = (pts[-2], pts[-1]) if is_end else (pts[0], pts[1])
            if not bad(a, b, layer):
                break
            q = _cut([a, b], step, end=is_end)
            pts = pts[:-2] + q if is_end else q + pts[2:]
        runs[idx] = (layer, pts)
    return runs


def _widths(sp, net, layer, w):
    """Track widths to try: the pair's, then the board minimum (a neck into a fine-pitch pad)."""
    mn = sp.width_limits(net, layer)[0]
    return [w] + ([mn] if mn and mn < w - 1e-6 else [])


def _why(viol, net, layer):
    """A one-line reason for a violation tuple (item or 'edge', distance, needed)."""
    it, dist, need = viol
    owner = f"{getattr(it, 'kind', it)} {getattr(it, 'net', '')!r} {getattr(it, 'owner', '') or ''}"
    return f"{net} on {layer}: {owner} at {dist:.3f}, needs {need:.3f}"


def _with_empty_ends(runs, vias, la, lb):
    """A route that changes layer on its first or last cell has no run on the end layer: add it as a
    one-point run, so len(runs) == len(vias) + 1 and each via joins consecutive runs."""
    runs = [(l, list(p)) for l, p in runs]
    if vias and runs:
        if math.dist(runs[0][1][0], vias[0]) < 1e-6 and (len(runs) <= len(vias)):
            other = next((l for l in la if l != runs[0][0]), runs[0][0])
            runs.insert(0, (other, [runs[0][1][0]]))
        if len(runs) <= len(vias) and math.dist(runs[-1][1][-1], vias[-1]) < 1e-6:
            other = next((l for l in lb if l != runs[-1][0]), runs[-1][0])
            runs.append((other, [runs[-1][1][-1]]))
    return runs


def _bump(a, b, h, side):
    """Replace straight piece a-b by a 45-degree bump of height h on `side` (+1 left), centred, base 2h+t."""
    u = _unit(a, b)
    L = math.dist(a, b)
    n = _left(u)
    base = min(L - 2e-3, 4.0 * h)
    t = max(0.0, base - 2.0 * h)
    s = (L - (2.0 * h + t)) / 2.0
    p = [a]
    x = s
    p.append((a[0] + u[0] * x, a[1] + u[1] * x))
    x += h
    p.append((a[0] + u[0] * x + side * n[0] * h, a[1] + u[1] * x + side * n[1] * h))
    x += t
    p.append((a[0] + u[0] * x + side * n[0] * h, a[1] + u[1] * x + side * n[1] * h))
    x += h
    p.append((a[0] + u[0] * x, a[1] + u[1] * x))
    p.append(b)
    return _dedup(p)


def bump_gain(h):
    return 2.0 * h * (math.sqrt(2.0) - 1.0)


def _rule_width_gap(sp, net_p, net_n, layer):
    """(width, gap) of a pair on `layer` by the board's rules: a custom diff_pair_gap or the net class's
    diff_pair_width/diff_pair_gap, clamped into what KiCad requires; floor the pair's own clearance."""
    nets = sp.board.nets if isinstance(sp.board.nets, dict) else {n.name: n for n in sp.board.nets}
    nc = (getattr(sp.board.rules, "netclasses", {}) or {}).get(getattr(nets.get(net_p), "netclass", ""))
    mn, opt, mx = sp.width_limits(net_p, layer)
    w = getattr(nc, "diff_pair_width", None) or opt
    w = sp.clamp_width(net_p, layer, w)
    ta, tb = CN.net_item(sp.info, net_p, "track", layer, width=w), CN.net_item(sp.info, net_n, "track", layer, width=w)
    rule = None
    try:
        rule = R.strictest(sp.rb, "diff_pair_gap", ta, tb, layer)
    except Exception:  # noqa: BLE001
        rule = None
    g = None
    if rule is not None:
        g = getattr(rule, "opt", None) or getattr(rule, "min", None)
    if not g:
        g = getattr(nc, "diff_pair_gap", None)
    floor = 0.0
    try:
        floor = sp.eff.clearance(net_p, net_n, layer).track_track
    except Exception:  # noqa: BLE001
        floor = sp._generic_need(net_p, "track", layer)
    if not g:
        g = floor
    g = max(g, floor) + 2.5 * TOL
    if rule is not None and getattr(rule, "max", None):
        g = min(g, rule.max)
    return w, math.ceil(g * 1000.0) / 1000.0


@dataclass
class PairResult:
    p: str
    n: str
    tier: str
    interface: str
    status: str = "pending"
    reason: str = ""
    skew: float | None = None
    length: float = 0.0
    width: float = 0.0
    gap: float = 0.0
    vias: int = 0
    stitch: int = 0
    spines: int = 0
    tracks: list = field(default_factory=list)
    via_rec: list = field(default_factory=list)
    items: list = field(default_factory=list)   # Space items committed (rollback)


class Router:
    def __init__(self, board, info, sev, opts=None, log=_log):
        self.o = {**DEFAULTS, **(opts or {})}
        self.log = log
        self.board = board
        self.sp = Space(board, info, sev=sev, opts=self.o)
        self.fan = GridRouter(self.sp, res=self.o["fan_res"], via_cost=3.0, pad_entry="centre")

    # ------------------------------------------------------------------ pairs and ends
    def _pads_of(self, net):
        return [it for it in self.sp.pads if it.net == net and it.pos is not None]

    def ends(self, p, n):
        """Ends of the pair: [(pad P, pad N, midpoint)]. A pad of N matched by at most one pad of P."""
        A, B = self._pads_of(p), self._pads_of(n)
        used = set()
        out = []
        for a in sorted(A, key=lambda it: (it.fp or "", it.owner)):
            best = None
            for b in B:
                if id(b) in used:
                    continue
                d = math.dist(a.pos, b.pos)
                same = a.fp == b.fp
                cost = d + (0.0 if same else 2.0)
                if d <= self.o["end_mm"] and (best is None or cost < best[0]):
                    best = (cost, b)
            if best is not None:
                used.add(id(best[1]))
                b = best[1]
                out.append((a, b, ((a.pos[0] + b.pos[0]) / 2.0, (a.pos[1] + b.pos[1]) / 2.0)))
        # ends that sit on top of each other (a USB-C receptacle's A and B rows: the same two
        # nets on both rows) are one end: the spine lands on the first, the bridge ties the other
        kept = []
        for e in out:
            if all(math.dist(e[2], k[2]) > max(1.0, 1.5 * math.dist(e[0].pos, e[1].pos)) for k in kept):
                kept.append(e)
        # each end may land on any same-net pad within reach (a USB-C row has the partner on both sides)
        r = self.o["end_group_mm"]
        return [(a, b, m, [a] + [x for x in A if x is not a and math.dist(x.pos, m) <= r],
                 [b] + [x for x in B if x is not b and math.dist(x.pos, m) <= r]) for a, b, m in kept]

    def plane_layers(self):
        """Inner copper layers one net's zones fill mostly: not for pairs."""
        sp = self.sp
        out = set()
        if sp.outline is None:
            return out
        area = sp.outline.area or 1.0
        by = {}
        for n, l, g, _ in sp.zones:
            by.setdefault(l, {}).setdefault(n, []).append(g)
        from shapely.ops import unary_union
        for l in sp.cu[1:-1]:
            for n, gs in by.get(l, {}).items():
                if unary_union(gs).area >= 0.5 * area:
                    out.add(l)
                    break
        return out

    def order(self, pairs):
        """High-speed tiers first, short pairs before long ones within a tier."""
        rank = dict(rule=0, interface=1, name=2)
        def span(pr):
            ends = self.ends(pr.p, pr.n)
            if len(ends) < 2:
                return 1e9
            return max(math.dist(a[2], b[2]) for a in ends for b in ends)
        return sorted(pairs, key=lambda pr: (rank.get(pr.tier, 3), span(pr)))

    # ------------------------------------------------------------------ one pair
    def route(self, pr):
        sp = self.sp
        res = PairResult(pr.p, pr.n, pr.tier, pr.interface)
        ends = self.ends(pr.p, pr.n)
        if len(ends) < 2:
            res.status, res.reason = "skipped", f"{len(ends)} pad ends found"
            return res
        layers0 = sp.cu[0]
        w, g = _rule_width_gap(sp, pr.p, pr.n, layers0)
        for l in sp.cu:
            wl, gl = _rule_width_gap(sp, pr.p, pr.n, l)
            w, g = max(w, wl), max(g, gl)
        res.width, res.gap = w, g
        D, d = sp.via_size(pr.p)
        try:
            pitch_vv = D + sp.eff.clearance(pr.p, pr.n, sp.cu[0]).via_via
        except Exception:  # noqa: BLE001
            pitch_vv = D + (sp.settings.get("min_clearance") or 0.2)
        pitch_vv = max(pitch_vv, d + (sp.settings.get("hole_to_hole") or 0.25)) + 2 * TOL
        env = PairGrid(sp, pitch_vv, no_ref_cost=self.o["no_ref_cost"], res=self.o["res"], via_cost=self.o["via_cost"])
        env.max_cells = 2_000_000
        planes = self.plane_layers()
        layers = [l for l in sp.cu if l not in planes]
        # join ends nearest-first (Prim)
        rem = list(range(1, len(ends)))
        done = [0]
        edges = []
        while rem:
            i, j = min(((a, b) for a in done for b in rem), key=lambda t: math.dist(ends[t[0]][2], ends[t[1]][2]))
            edges.append((i, j))
            done.append(j)
            rem.remove(j)
        ok_spines = 0
        reason = ""
        for i, j in edges:
            got = self._spine(res, pr, ends[i], ends[j], w, g, env, layers, pitch_vv, D, d)
            if got == "ok":
                ok_spines += 1
            else:
                reason = got
        res.spines = ok_spines
        if not ok_spines:
            self._rollback(res)
            res.status, res.reason = "failed", reason or "no spine"
            return res
        res.status = "routed"
        res.reason = reason
        L_p = sum(math.dist(a, b) for n, l, wd, a, b in res.tracks if n == pr.p)
        L_n = sum(math.dist(a, b) for n, l, wd, a, b in res.tracks if n == pr.n)
        res.length, res.skew = round((L_p + L_n) / 2, 3), round(abs(L_p - L_n), 3)
        res.vias = len([1 for v in res.via_rec if v[0] in (pr.p, pr.n)])
        return res

    def _spine(self, res, pr, e1, e2, w, g, env, layers, pitch_vv, D, d):
        sp, o = self.sp, self.o
        w_env = 2.0 * w + g
        offs = (w + g) / 2.0
        # end layers: where both pads of each end have copper
        la = sorted(set(e1[0].layers) & set(e1[1].layers) & set(layers))
        lb = sorted(set(e2[0].layers) & set(e2[1].layers) & set(layers))
        if not la or not lb:
            return "end pads not on a usable layer"
        reasons = []
        for r in o["radii"]:
            got = self._try_radius(res, pr, e1, e2, w, g, env, layers, pitch_vv, D, d, la, lb, offs, w_env, r)
            if got == "ok":
                return "ok"
            reasons.append(f"r={r}: {got}")
        # only a very short pair, where a spine cannot start and end clear of the pads, goes without one;
        # a longer pair the spine cannot close stays with the bridge, uncoupled is not better locked
        if math.dist(e1[2], e2[2]) < o["short_mm"] and self._short(res, pr, e1, e2, w, g):
            return "ok"
        return "; ".join(reasons)

    def _short(self, res, pr, e1, e2, w, g):
        """A pair too short for a spine (a series part right beside the IC): each leg straight from pad to pad."""
        sp = self.sp
        added = []
        for attempt in ((pr.p, pr.n), (pr.n, pr.p)):
            n0 = len(added)
            ok = True
            for net in attempt:
                a, b = (e1[0], e2[0]) if net == pr.p else (e1[1], e2[1])
                src, tgt = (Anchor(a.geom, tuple(sorted(a.layers)), a.pos, kind="pad"),
                            Anchor(b.geom, tuple(sorted(b.layers)), b.pos, kind="pad"))
                win = self.fan.window([src, tgt], margin=1.5)
                ls = [l for l in sp.cu if l in a.layers or l in b.layers]
                rt = None
                for fw in _widths(sp, net, ls[0], w):
                    rt = self.fan.connect(net, [src], [tgt], fw, ls, via=len(ls) > 1, window=win, count=False)
                    if rt is not None:
                        break
                if rt is None:
                    ok = False
                    break
                for l, u, v in rt.segs:
                    if sp.track_violations(net, l, fw, u, v, first=True):
                        ok = False
                        break
                    added.append(self._add_track(res, net, l, fw, u, v))
                for (x, y) in rt.vias if ok else ():
                    D, d = sp.via_size(net)
                    added.append(self._add_via(res, net, x, y, D, d))
                if not ok:
                    break
            if ok:
                res.items += added
                return True
            for rec in added[n0:]:
                sp.remove([rec[1]])
                self._forget(res, rec)
            del added[n0:]
        return False

    def _try_radius(self, res, pr, e1, e2, w, g, env, layers, pitch_vv, D, d, la, lb, offs, w_env, r):
        """One spine with its legs and fan-ins at start radius r; "ok" when committed, else the reason."""
        sp, o = self.sp, self.o
        added = []
        r0 = max(r, 0.6 * math.dist(e1[0].pos, e1[1].pos))
        r1 = max(r, 0.6 * math.dist(e2[0].pos, e2[1].pos))
        with merged(sp, pr.p, pr.n):
            src = [Anchor(Point(e1[2]).buffer(r0, quad_segs=6), (l,), None, kind="free") for l in la]
            dst = [Anchor(Point(e2[2]).buffer(r1, quad_segs=6), (l,), None, kind="free") for l in lb]
            rt = env.connect(pr.p, src, dst, w_env, layers, via=len(layers) > 1, skip=(), count=False)
        if rt is None or not rt.segs:
            return f"no spine path (r={r})"
        if len(rt.vias) > o["max_vias"]:
            return f"{len(rt.vias)} via pairs"
        runs = _runs(rt)
        runs = _with_empty_ends(runs, rt.vias, la, lb)
        polarity = self._polarity(runs, offs, e1, e2)
        side = {pr.p: polarity, pr.n: -polarity}
        vias = list(rt.vias)
        built = self._legs(pr, runs, vias, offs, side, pitch_vv, w, env)
        if built is None:
            return "legs do not verify"
        legs, via_sites = built
        # the legs' first and last pieces run over the end pads; a piece the partner's pad would clear only
        # narrowly is left to the fan-in
        other = {pr.p: pr.n, pr.n: pr.p}
        for net in (pr.p, pr.n):
            legs[net] = _clear_ends(sp, net, other[net], legs[net], w)
        if any(not pts for net in (pr.p, pr.n) for layer, pts in legs[net]):
            return "legs do not verify"
        for net in (pr.p, pr.n):
            for (layer, pts) in legs[net]:
                for a, b in zip(pts[:-1], pts[1:]):
                    v = sp.track_violations(net, layer, w, a, b, first=True)
                    if v:
                        self._undo_keep(res, added)
                        return "legs break a rule: " + _why(v[0], net, layer)
                    added.append(self._add_track(res, net, layer, w, a, b))
        for net in (pr.p, pr.n):
            for (x, y) in via_sites[net]:
                v = sp.via_violations(net, x, y, size=D, drill=d, first=True)
                if v:
                    self._undo_keep(res, added)
                    return "via pair breaks a rule: " + _why(v[0], net, "")
                added.append(self._add_via(res, net, x, y, D, d))
        for e, end_idx in ((e1, 0), (e2, -1)):
            pts = {net: (legs[net][end_idx][0], legs[net][end_idx][1][0 if end_idx == 0 else -1]) for net in (pr.p, pr.n)}
            pad = {pr.p: e[3], pr.n: e[4]}
            order = sorted((pr.p, pr.n), key=lambda net: -min(math.dist(pts[net][1], x.pos) for x in pad[net]))   # the farther pad first
            done = False
            for attempt in (order, order[::-1]):
                n0 = len(added)
                good = all(self._fan_in(res, added, net, pad[net], pts[net][0], pts[net][1], w) for net in attempt)
                if good:
                    done = True
                    break
                for rec in added[n0:]:
                    self.sp.remove([rec[1]])
                    self._forget(res, rec)
                del added[n0:]
            if not done:
                self._undo_keep(res, added)
                return f"fan-in at {e[0].owner}"
        self._tune(res, added, pr, legs, w, g)
        if o["stitch"] and vias:
            self._stitch(res, added, pr, via_sites, D, d)
        res.items += added
        return "ok"

    def _forget(self, res, rec):
        if rec[0] == "t":
            res.tracks.remove(rec[2])
        else:
            res.via_rec = [v for v in res.via_rec if v[5] != rec[3]]

    def _undo_keep(self, res, added):
        for rec in added:
            self.sp.remove([rec[1]])
            self._forget(res, rec)
        added.clear()

    def _polarity(self, runs, offs, e1, e2):
        """+1 when P goes on the left of the route, -1 otherwise: the assignment with the shorter fan-ins."""
        all_pts = [p for _, pts in runs for p in pts]
        s = _dedup(all_pts)[:2]
        t = _dedup(all_pts)[-2:]
        ns, nt = _left(_unit(s[0], s[1])), _left(_unit(t[0], t[1]))
        p_s = (s[0][0] + ns[0] * offs, s[0][1] + ns[1] * offs)   # P on the left at the start
        n_s = (s[0][0] - ns[0] * offs, s[0][1] - ns[1] * offs)
        p_t = (t[1][0] + nt[0] * offs, t[1][1] + nt[1] * offs)
        n_t = (t[1][0] - nt[0] * offs, t[1][1] - nt[1] * offs)
        def nd(q, pads):
            return min(math.dist(q, x.pos) for x in pads)
        a = nd(p_s, e1[3]) + nd(n_s, e1[4]) + nd(p_t, e2[3]) + nd(n_t, e2[4])
        b = nd(p_s, e1[4]) + nd(n_s, e1[3]) + nd(p_t, e2[4]) + nd(n_t, e2[3])
        return 1.0 if a <= b else -1.0

    def _legs(self, pr, runs, vias, offs, side, pitch_vv, w, env=None):
        """Per net, [(layer, polyline)] along the route, ending in via sites; (legs, via sites) or None."""
        n_runs = len(runs)
        if len(vias) != n_runs - 1:
            return None
        flare = max(0.0, pitch_vv / 2.0 - offs)
        # via sites (axis perpendicular to the bisector of the directions in and out)
        sites, axes = [], []
        for i, v in enumerate(vias):
            a = _dedup([p for _, pts in runs[:i + 1] for p in pts])
            b = _dedup([p for _, pts in runs[i + 1:] for p in pts])
            d0 = _unit(a[-2], a[-1]) if len(a) >= 2 else _unit(b[0], b[1])
            d1 = _unit(b[0], b[1]) if len(b) >= 2 else d0
            bx, by = d0[0] + d1[0], d0[1] + d1[1]
            n = _left(_unit((0, 0), (bx, by))) if math.hypot(bx, by) > 0.1 else _left(d0)
            if env is not None:           # a side-by-side axis the raster found room for, nearest the ideal one
                cand = env.axes_at(*v)
                best = max(cand, key=lambda a: abs(a[0] * n[0] + a[1] * n[1]))
                if abs(best[0] * n[0] + best[1] * n[1]) < 0.6:
                    return None               # only in-line room: the legs would cross at the vias
                sign = 1.0 if best[0] * n[0] + best[1] * n[1] >= 0 else -1.0
                n = (best[0] * sign, best[1] * sign)
            sites.append(v)
            axes.append(n)
        legs = {pr.p: [], pr.n: []}
        via_sites = {pr.p: [], pr.n: []}
        for net in (pr.p, pr.n):
            s = side[net]
            for k, (layer, pts) in enumerate(runs):
                c = _dedup(pts)
                if k > 0 and len(c) >= 2:
                    c = _cut(c, flare + 0.1, end=False)
                if k < n_runs - 1 and len(c) >= 2:
                    c = _cut(c, flare + 0.1, end=True)
                leg = offset_polyline(c, s * offs) if len(c) >= 2 else []
                if k > 0:
                    v, ax = sites[k - 1], axes[k - 1]
                    sv = (v[0] + s * ax[0] * pitch_vv / 2.0, v[1] + s * ax[1] * pitch_vv / 2.0)
                    leg = [sv] + leg
                if k < n_runs - 1:
                    v, ax = sites[k], axes[k]
                    sv = (v[0] + s * ax[0] * pitch_vv / 2.0, v[1] + s * ax[1] * pitch_vv / 2.0)
                    leg = leg + [sv]
                    via_sites[net].append(sv)
                leg = _dedup(leg)
                if not leg:
                    return None
                legs[net].append((layer, leg))
        return legs, via_sites

    def _add_track(self, res, net, layer, w, a, b):
        uid = str(_uuid.uuid4())
        it = self.sp.add_track(net, layer, w, a, b, owner="pair", uuid=uid)
        res.tracks.append((net, layer, w, a, b))
        return ("t", it, (net, layer, w, a, b), uid)

    def _add_via(self, res, net, x, y, D, d):
        uid = str(_uuid.uuid4())
        it = self.sp.add_via(net, x, y, owner="pair", size=D, drill=d, uuid=uid)
        res.via_rec.append((net, x, y, D, d, uid))
        return ("v", it, (net, x, y, D, d), uid)

    def _rollback(self, res):
        for kind, it, rec, uid in res.items:
            self.sp.remove([it])
        res.items = []
        res.tracks, res.via_rec = [], []

    def _fan_in(self, res, added, net, pad, layer, end_pt, w):
        """Join leg end `end_pt` on `layer` to `pad`."""
        sp = self.sp
        pads = pad if isinstance(pad, (list, tuple)) else [pad]
        if any(layer in x.layers and x.geom.distance(Point(end_pt)) <= 1e-6 for x in pads):
            return True
        src = Anchor(Point(end_pt).buffer(0.02, quad_segs=4), (layer,), end_pt, kind="free")
        tgt = [Anchor(x.geom, tuple(sorted(x.layers)), x.pos, kind="pad") for x in pads]
        win = self.fan.window([src] + tgt, margin=2.0)
        # the pad on this leg's layer first; through another layer (a twist) when the plane is blocked; at the
        # pair's width, then at the board's minimum width (fine-pitch pads narrower than the pair's width)
        rt = None
        for fw in _widths(sp, net, layer, w):
            for vias in (False, True):
                ls = [layer] if not vias else [l for l in sp.cu if l == layer or any(l in x.layers for x in pads) or l in (sp.cu[0], sp.cu[-1])]
                rt = self.fan.connect(net, [src], tgt, fw, ls, via=vias and len(ls) > 1, window=win, count=False)
                if rt is not None and rt.segs:
                    w = fw
                    break
                rt = None
            if rt is not None:
                break
        if rt is None:
            return False
        segs = list(rt.segs)
        s0 = segs[0][1]
        pieces = []
        if math.dist(s0, end_pt) > 1e-6:
            pieces.append((layer, end_pt, s0))
        pieces += segs
        for l, a, b in pieces:
            if sp.track_violations(net, l, w, a, b, first=True):
                return False
            added.append(self._add_track(res, net, l, w, a, b))
        if rt.vias:
            D, d = sp.via_size(net)
            for (x, y) in rt.vias:
                if sp.via_violations(net, x, y, size=D, drill=d, first=True):
                    return False
                added.append(self._add_via(res, net, x, y, D, d))
        return True

    # ------------------------------------------------------------------ skew
    def _tune(self, res, added, pr, legs, w, g):
        """Lengthen the shorter leg with bumps near where the mismatch arises, until skew <= max_skew_mm."""
        sp, o = self.sp, self.o

        def length(net):
            return sum(math.dist(rec[3], rec[4]) for k, it, rec, uid in added if k == "t" and rec[0] == net)
        skew = length(pr.p) - length(pr.n)
        tries = 0
        while abs(skew) > o["max_skew_mm"] and tries < 80:
            short = pr.n if skew > 0 else pr.p
            need = abs(skew)
            # a serpentine: as many bumps as it takes, each at most `bump_max` tall (a tall one hides in no gap)
            h = o["bump_mm"] or min(max(need / (2.0 * (math.sqrt(2.0) - 1.0)), 3.0 * w), max(o["bump_max"], 3.0 * w))
            ok = False
            # the straight pieces of the shorter leg, longest last so a bump goes near the ends first
            segs = [e for e in added if e[0] == "t" and e[2][0] == short and math.dist(e[2][3], e[2][4]) > 2.5 * h]
            segs.sort(key=lambda e: math.dist(e[2][3], e[2][4]))
            for e in segs:
                _, it, rec, uid = e
                net, layer, wd, a, b = rec
                for s in (1.0, -1.0):
                    pts = _bump(a, b, h, s)
                    self.sp.remove([it])
                    vio = any(sp.track_violations(net, layer, wd, u, v, first=True) for u, v in zip(pts[:-1], pts[1:]))
                    if not vio:
                        added.remove(e)
                        res.tracks.remove(rec)
                        for u, v in zip(pts[:-1], pts[1:]):
                            if math.dist(u, v) > 1e-6:
                                added.append(self._add_track(res, net, layer, wd, u, v))
                        ok = True
                        break
                    self.sp.add_track(net, layer, wd, a, b, owner="pair", uuid=uid)
                    # sp.add_track made a new Item: refresh
                    nit = self.sp.routed[-1]
                    idx = added.index(e)
                    added[idx] = ("t", nit, rec, uid)
                    e = added[idx]
                    it = nit
                if ok:
                    break
            if not ok:
                break
            skew = length(pr.p) - length(pr.n)
            tries += 1

    def _stitch(self, res, added, pr, via_sites, D, d):
        """A ground via beside each signal via where the signal changes reference layer, when ground is there."""
        sp = self.sp
        gnd = self._ground()
        if not gnd:
            return
        n0 = len(res.via_rec)
        for net in (pr.p, pr.n):
            for (x, y) in via_sites[net]:
                for ang in (0, 90, 180, 270):
                    a = math.radians(ang)
                    sx, sy = x + (D + 0.4) * math.cos(a), y + (D + 0.4) * math.sin(a)
                    if not (sp.zone_covers(gnd, sp.cu[0], sx, sy) or sp.zone_covers(gnd, sp.cu[-1], sx, sy)):
                        continue
                    if sp.via_violations(gnd, sx, sy, size=D, drill=d, first=True):
                        continue
                    added.append(self._add_via(res, gnd, sx, sy, D, d))
                    break
        res.stitch += len(res.via_rec) - n0

    def _ground(self):
        cand = {}
        for n, l, g, _ in self.sp.zones:
            if n and re.fullmatch(r"(/.*/)?(A|D|P)?GND.*", n, re.I):
                cand[n] = cand.get(n, 0.0) + g.area
        return max(cand, key=cand.get) if cand else None



def post_pass(routed_path, out_path, time_s=120.0, opts=None, log=_log):
    """E37 alternative: re-lay already-routed pairs as pairs inside a finished board. Each pair's existing
    unlocked copper is ripped for its own attempt and restored if the pair does not close, so the pass never
    opens a connection. Returns a JSON-able report; out_path = routed_path with the pairs replaced."""
    t0 = time.monotonic()
    routed_path, out_path = Path(routed_path), Path(out_path)
    board = load(routed_path)
    with tempfile.TemporaryDirectory(prefix="kae-pair-") as d:
        info = pcbnew_io.export_dsn(routed_path, Path(d) / "board.dsn")
    from .bridge import severities
    o = {**DEFAULTS, **(opts or {})}
    brief = o.get("brief")
    if brief is None:
        try:
            from kae.circuit.brief import build
            brief = build(board)
        except Exception:  # noqa: BLE001
            brief = None
    pairs = [p for p in PAIRS.detect(board, brief=brief) if p.tier in tuple(o["tiers"])]
    r = Router(board, info, severities(routed_path), opts=o, log=log)
    rep = dict(pairs=[], counts=dict(detected=len(pairs)))
    tracks, vias, remove = [], [], []
    for pr in r.order(pairs):
        if time.monotonic() - t0 > time_s:
            rep["pairs"].append(dict(p=pr.p, n=pr.n, status="skipped", reason="budget"))
            continue
        old = [it for it in r.sp.existing if it.net in (pr.p, pr.n) and not it.locked and it.kind in ("track", "via")]
        r.sp.remove(old)
        try:
            res = r.route(pr)
        except Exception as e:  # noqa: BLE001 - keep the pair's old copper
            log(f"pair {pr.p}/{pr.n}: {type(e).__name__}: {e}")
            res = PairResult(pr.p, pr.n, pr.tier, pr.interface, status="failed", reason=f"{type(e).__name__}: {e}"[:200])
        if res.status != "routed":
            for it in old:
                r.sp.existing.append(it)
                for l in it.layers:
                    r.sp.items[l].append(it)
            r.sp.invalidate()
        else:
            remove += [it.uuid for it in old]
            for (net, layer, w, a, b) in res.tracks:
                tracks.append((net, layer, w, a, b, W.new_uuid(), False, None))
            for (net, x, y, D, d, uid) in res.via_rec:
                vias.append((net, x, y, D, d, uid, False))
        rep["pairs"].append(dict(p=res.p, n=res.n, tier=res.tier, status=res.status, reason=res.reason, skew=res.skew,
                                 length=res.length, vias=res.vias, stitch=res.stitch))
    tmp = out_path.with_suffix(".tmp.kicad_pcb")
    W.edit(routed_path, tmp, remove=remove)
    W.append_items(tmp, out_path, tracks=tracks, vias=vias)
    tmp.unlink()
    for ext in (".kicad_pro", ".kicad_dru", ".kicad_prl"):
        s = routed_path.with_suffix(ext)
        t = out_path.with_suffix(ext)
        if s.exists() and s.resolve() != t.resolve():
            import shutil
            shutil.copy2(s, t)
    c = {}
    for e in rep["pairs"]:
        c[e["status"]] = c.get(e["status"], 0) + 1
    rep["counts"].update(c, tracks=len(tracks), vias=len(vias))
    rep["seconds"] = round(time.monotonic() - t0, 2)
    return rep


def copper_survival(reserved_path, routed_path):
    """Share of the pair copper in `reserved_path` (the board after route_pairs) still present in `routed_path`:
    per routed pair net, length of the reserved tracks whose midpoint lies within 5 um of a same-net track on the
    same layer, and reserved vias within 5 um of a via of the net. Measures a soft reservation; returns
    {length_mm, kept_mm, share, vias, vias_kept, nets}."""
    pts = load(reserved_path)
    rt = load(routed_path)
    new = {t.net for t in pts.tracks if t.locked} | {v.net for v in pts.vias if v.locked}
    if not new:     # unlocked reservation: the board after pairs holds only pair copper for these nets, unless escapes share them
        new = {t.net for t in pts.tracks} | {v.net for v in pts.vias}
    tol = 0.005
    by = {}
    for t in rt.tracks:
        by.setdefault((t.net, t.layer), []).append((t.start, t.end))
    L = kept = 0.0
    nets = {}
    for t in pts.tracks:
        if t.net not in new:
            continue
        ln = math.dist(t.start, t.end)
        L += ln
        m = ((t.start[0] + t.end[0]) / 2, (t.start[1] + t.end[1]) / 2)
        hit = any(_dist_seg(m, a, b) <= tol for a, b in by.get((t.net, t.layer), ()))
        kept += ln if hit else 0.0
        e = nets.setdefault(t.net, [0.0, 0.0])
        e[0] += ln
        e[1] += ln if hit else 0.0
    rv = [(v.net, v.x, v.y) for v in rt.vias]
    vn = vk = 0
    for v in pts.vias:
        if v.net not in new:
            continue
        vn += 1
        vk += 1 if any(n == v.net and math.hypot(x - v.x, y - v.y) <= tol for n, x, y in rv) else 0
    return dict(length_mm=round(L, 2), kept_mm=round(kept, 2), share=round(kept / L, 4) if L else None, vias=vn, vias_kept=vk,
                nets={n: round(k / l, 3) if l else None for n, (l, k) in nets.items()})


def _dist_seg(p, a, b):
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    l2 = dx * dx + dy * dy
    t = 0.0 if l2 <= 0 else max(0.0, min(1.0, ((p[0] - ax) * dx + (p[1] - ay) * dy) / l2))
    return math.hypot(p[0] - ax - t * dx, p[1] - ay - t * dy)


def route_pairs(board_path, out_path, time_s=120.0, opts=None, log=_log, board=None, info=None, sev=None):
    """Pairs of `board_path` routed and locked into a copy at `out_path`. Returns a JSON-able report."""
    t0 = time.monotonic()
    board_path, out_path = Path(board_path), Path(out_path)
    board = board or load(board_path)
    if info is None:
        with tempfile.TemporaryDirectory(prefix="kae-pair-") as d:
            info = pcbnew_io.export_dsn(board_path, Path(d) / "board.dsn")
    if sev is None:
        from .bridge import severities
        sev = severities(board_path)
    o = {**DEFAULTS, **(opts or {})}
    brief = o.get("brief")
    if brief is None:
        try:
            from kae.circuit.brief import build
            brief = build(board)
        except Exception:  # noqa: BLE001
            brief = None
    pairs = [p for p in PAIRS.detect(board, brief=brief) if p.tier in tuple(o["tiers"])]
    rep = dict(pairs=[], counts=dict(detected=len(pairs)))
    if not pairs:
        import shutil
        shutil.copy2(board_path, out_path)
        for ext in (".kicad_pro", ".kicad_dru", ".kicad_prl"):
            s = board_path.with_suffix(ext)
            if s.exists() and s.resolve() != out_path.with_suffix(ext).resolve():
                shutil.copy2(s, out_path.with_suffix(ext))
        rep["seconds"] = round(time.monotonic() - t0, 2)
        return rep
    r = Router(board, info, sev, opts=o, log=log)
    tracks, vias = [], []
    for pr in r.order(pairs):
        if time.monotonic() - t0 > time_s:
            rep["pairs"].append(dict(p=pr.p, n=pr.n, tier=pr.tier, status="skipped", reason="budget"))
            continue
        try:
            res = r.route(pr)
        except Exception as e:  # noqa: BLE001 - a pair the router cannot handle stays with the general router
            log(f"pair {pr.p}/{pr.n}: {type(e).__name__}: {e}")
            res = PairResult(pr.p, pr.n, pr.tier, pr.interface, status="failed", reason=f"{type(e).__name__}: {e}"[:200])
        rep["pairs"].append(dict(p=res.p, n=res.n, tier=res.tier, interface=res.interface, status=res.status, reason=res.reason,
                                 skew=res.skew, length=res.length, width=res.width, gap=res.gap, vias=res.vias, stitch=res.stitch,
                                 spines=res.spines))
        if res.status == "routed":
            lock = not o.get("unlocked")   # pairs_unlocked: laid as ordinary copper (see bridge wire_type)
            for (net, layer, w, a, b) in res.tracks:
                tracks.append((net, layer, w, a, b, W.new_uuid(), lock, None))
            for (net, x, y, D, d, uid) in res.via_rec:
                vias.append((net, x, y, D, d, uid, lock))
    W.append_items(board_path, out_path, tracks=tracks, vias=vias)
    for ext in (".kicad_pro", ".kicad_dru", ".kicad_prl"):
        s = board_path.with_suffix(ext)
        t = out_path.with_suffix(ext)
        if s.exists() and s.resolve() != t.resolve():
            import shutil
            shutil.copy2(s, t)
    c = {}
    for e in rep["pairs"]:
        c[e["status"]] = c.get(e["status"], 0) + 1
    rep["counts"].update(c, tracks=len(tracks), vias=len(vias))
    rep["seconds"] = round(time.monotonic() - t0, 2)
    return rep
