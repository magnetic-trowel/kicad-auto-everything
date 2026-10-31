# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Negotiated routing of a dense window: every net of a ball grid's field and escape ring (or of
a fine-pitch package's pin rows) ripped and re-routed together, PathFinder style.

After Freerouting, the open connections of the boards with a large ball grid sit in its field and
escape ring (nekoink: 38 of 42 congestion opens touch U100, gecko5: 25 of 33 touch U6), and the
human layouts prove the room exists: they escape twice the balls through the same channels. A
greedy join one connection at a time (lastmile._join) closes 0-3 of them: the first nets through
a channel take it. Here the nets of the window share the channels by negotiation (McMurchie and
Ebeling, FPGA'95; docs/topics/routing/pathfinder-negotiated-congestion.md):

1. **Window** (`windows`): a footprint with MIN_PADS pads or more at ball-grid pitch (pads inside
   the outer rows too) or fine pitch, its pad field grown by an escape ring sized from the pitch
   and the rules. Windows are ranked by the open connections that end in them.
2. **Cut**: every unlocked track and via of the window's nets inside the window is taken out; a
   track crossing the border keeps its outside part, which ends on the border: a fixed terminal.
   Each net's copper parts (lastmile.parts: pads, the kept stubs, its fills) that reach into the
   window are joined there; a signal net whose ball field part has no copper reaching its other
   parts gets an escape to the window side facing them (the rest of that connection is the
   router's, after this). Locked copper and the input's pre-routes stay, as obstacles.
3. **Grid**: the critical router's raster (critical_grid.GridRouter.blocked / via_allowed), the
   board's exact per-layer legal widths, clearances, vias and mask openings (constraints.plan,
   critical_space.Space). A net routes at the narrowest width its rules allow on the most layers.
4. **Negotiation**: each iteration rips and re-routes every net (A* over the layers, with a price
   per via site, region_kernels.astar_v). A track or via claims the cells within half its width
   (via: diameter) plus half its clearance of its centreline; two claims that meet are a
   conflict. The price of a cell for a net is (base + history) x (1 + pres_fac x the other nets
   claiming it), the same for via sites over every layer: the channels between balls and the via
   sites between them are the resources, with the capacity the rules give them. pres_fac starts
   at 0 (each net its own shortest path), then PRES_FIRST, times PRES_MULT per iteration; a
   conflicting cell's history grows by HIST_FAC per iteration. Nets are ordered by depth in the
   field (the innermost balls, the most constrained, first), the ones in conflict first after
   the first iteration. It stops when no claim meets another, at MAX_ITER, or at the deadline;
   the iteration with the fewest nets in conflict is kept.
5. **Commit**: the kept routes are laid one by one with every segment and via checked exactly
   against the rules and the copper laid before (Space.track_violations / via_violations), then
   string-pulled; a net whose route fails gets its old copper back where that still fits, else a
   plain grid join (lastmile._join without rip-up), else stays open.

When the negotiation does not converge, `capacity` says where and why: the channels between
neighbouring pads that more nets cross than the rules leave room for ("channel U6.C3-U6.C4 on
F.Cu: 3 nets cross, room for 2 (track 0.100 mm, clearance 0.100 mm)"), the via sites wanted by
more than one net, and the nets in conflict; kae.route.blocked carries it to the caller as the
quantified cause of the congestion.

The caller (repair._region) keeps a result only when KiCad's DRC on the whole board ranks it
better. Deterministic for a given board and seed (the seed only breaks ties in the order of nets
of the same depth); no randomness otherwise. Lengths are mm.

    solve(board, info, plan, fills, out, window, ...) -> report
"""
from __future__ import annotations

import importlib.util
import math
import os
import sys
import time

import numpy as np
from shapely.geometry import LineString, Point, box

from kae.board.kicad_file import load

from . import critical_write as W
from . import lastmile as LM
from .critical_grid import Grid, GridRouter, _margin, _merge_collinear, _pour_mask
from .critical_space import EXACT_TOL, INF, TOL, Space

# ----------------------------------------------------------------------------- parameters
MIN_PADS = 16          # pads of a footprint that can make a dense window
BALL_PITCH = 1.27      # mm: ball grids up to this pitch
FINE_PITCH = 0.65      # mm: rows of pins (QFN, QFP, connectors) up to this pitch
RING_PITCHES = 2.5     # escape ring around the field: this many pitches at least
RING_MIN, RING_MAX = 1.0, 5.0   # mm
GRID_MARGIN = 0.3      # mm of grid beyond the window (the border terminals lie on it)
RES = 0.05             # mm grid (finer for pitches below 16 x RES)
RES_MIN = 0.025
MAX_CELLS = 2_500_000  # cells over all layers at most (the grid gets coarser beyond)
MAX_EXP = 1_500_000    # A* expansions per connection
VIA_COST = 1.5         # mm-equivalent per via (GridRouter's)
MAX_ITER = 40
PRES_FIRST = 0.5       # pres_fac of the second iteration (the first is 0), times PRES_MULT after,
PRES_MULT = 1.3        # up to PRES_MAX: history-centric negotiation (nextpnr router2's alt-weights keep the
PRES_MAX = 5.0         # present weight at 5, history 0.5; fast present growth makes the order decide)
HIST_FAC = 1.0         # history added per iteration to a cell in conflict (in base-cost units)
STALL = 8              # negotiation stops after this many iterations with no better state
NEG_SHARE = 0.6        # share of the time for the negotiation; the neighbourhood repair gets the rest
LNS_SIZE = 8           # nets re-planned together in one repair move (MAPF-LNS2's neighbourhood)
LNS_PRES = 1000.0      # pres_fac of a repair move: another net's cell costs as a long detour
FLOAT_MM = 1.0         # mm along the border either side of a stub: where its net may cross instead
LNS_STALL = 60         # repair moves in a row without fewer conflicts before it stops
MAX_NETS = 600         # nets in one window at most (more: the window is skipped)


def _load_kernels():
    """region_kernels compiled by numba (cached on disk) when numba is installed and
    KAE_NO_NUMBA is unset, else plain Python."""
    src = os.path.join(os.path.dirname(os.path.abspath(__file__)), "region_kernels.py")
    jit, name = (lambda f: f), "kae.route._region_kernels_py"
    if not os.environ.get("KAE_NO_NUMBA"):
        try:
            import numba
            jit, name = numba.njit(cache=True), "kae.route._region_kernels_nb"
        except ImportError:
            pass
    mod = sys.modules.get(name)
    if mod is None:
        spec = importlib.util.spec_from_file_location(name, src)
        mod = importlib.util.module_from_spec(spec)
        mod._JIT = jit
        sys.modules[name] = mod
        spec.loader.exec_module(mod)
    return mod


# ----------------------------------------------------------------------------- windows
def _pitch(P):
    """Median nearest-neighbour distance of the points P (n x 2)."""
    from scipy.spatial import cKDTree
    d, _ = cKDTree(P).query(P, k=2)
    return float(np.median(d[:, 1]))


def windows(sp, focus=(), rules_w=None):
    """The dense windows of the board in Space `sp`: [dict(ref, fp, kind ("ball grid" | "fine
    pitch"), pitch, pads, field (x0, y0, x1, y1), ring, box, opens)], the ones holding most of
    the points `focus` (open connections' ends, (x, y)) first; with focus, only windows holding
    at least one."""
    by_fp = {}
    for it in sp.pads:
        if it.kind == "pad" and it.fp:
            by_fp.setdefault(it.fp, []).append(it)
    out = []
    for fp, pads in by_fp.items():
        if len(pads) < MIN_PADS:
            continue
        P = np.array([p.pos for p in pads], float)
        pitch = _pitch(P)
        x0, y0 = P.min(axis=0)
        x1, y1 = P.max(axis=0)
        # pads off the outer rows: a ball grid has many, a QFN at most its exposed pad
        inner = int(((P[:, 0] > x0 + 0.5 * pitch) & (P[:, 0] < x1 - 0.5 * pitch)
                     & (P[:, 1] > y0 + 0.5 * pitch) & (P[:, 1] < y1 - 0.5 * pitch)).sum())
        if pitch <= BALL_PITCH and inner >= 4 and inner >= 0.1 * len(pads):
            kind = "ball grid"
        elif pitch <= FINE_PITCH:
            kind = "fine pitch"
        else:
            continue
        # depth of the field: rows of balls from the outside to the centre
        depth = max(1, int(round(min(x1 - x0, y1 - y0) / (2 * pitch)))) if kind == "ball grid" else 1
        wc = rules_w or 0.2
        ring = min(RING_MAX, max(RING_MIN, RING_PITCHES * pitch, depth * wc))
        cop = [p.geom.bounds for p in pads]
        fx0, fy0 = min(b[0] for b in cop), min(b[1] for b in cop)
        fx1, fy1 = max(b[2] for b in cop), max(b[3] for b in cop)
        bx = (fx0 - ring, fy0 - ring, fx1 + ring, fy1 + ring)
        if sp.outline is not None:
            ob = sp.outline.bounds
            bx = (max(bx[0], ob[0]), max(bx[1], ob[1]), min(bx[2], ob[2]), min(bx[3], ob[3]))
        n = sum(1 for (x, y) in focus if bx[0] <= x <= bx[2] and bx[1] <= y <= bx[3])
        ref = pads[0].owner[0] if isinstance(pads[0].owner, tuple) else "?"
        out.append(dict(ref=ref, fp=fp, kind=kind, pitch=pitch, pads=len(pads), depth=depth,
                        origin=(float(P[0, 0]), float(P[0, 1])),
                        field=(fx0, fy0, fx1, fy1), ring=round(ring, 3), box=bx, opens=n))
    if focus:
        out = [w for w in out if w["opens"] > 0]
    out.sort(key=lambda w: (-w["opens"], -w["pads"], w["ref"]))
    return out


def focus_points(report):
    """(x, y) of both ends of every unconnected item of a KiCad DRC report."""
    pts = []
    for u in report.get("unconnected_items") or []:
        for it in u.get("items") or []:
            p = it.get("pos") or {}
            if p.get("x") is not None:
                pts.append((float(p["x"]), float(p["y"])))
    return pts


# ----------------------------------------------------------------------------- rasters
class _Route:
    __slots__ = ("net", "width", "runs", "vias", "cells", "vcells", "exact", "length", "conns", "failed",
                 "escape")

    def __init__(self, net, width):
        self.net, self.width = net, width
        self.runs = []      # [(layer, [pts], exact)] polylines per layer
        self.vias = []      # [(x, y)]
        self.cells = []     # flat 3D path cells (for the history)
        self.vcells = []    # in-plane cells of its vias
        self.exact = False
        self.length = 0.0
        self.conns = 0      # connections made
        self.failed = 0     # connections with no path even through others' copper
        self.escape = None  # side of the window an escape went to


# ----------------------------------------------------------------------------- the solve
class Region:
    """One window's negotiation (see the module docstring). Build, then `run`, then `commit`."""

    def __init__(self, sp, fills, win, fixed=(), log=print, seed=0, only=None, quiet=False):
        self.sp, self.win, self.log, self.seed = sp, win, log, seed
        self.only = set(only) if only is not None else None   # the nets that move (a repair step)
        self.quiet = quiet
        if quiet:
            self.log = lambda m: None
        self.deadline = None
        self.fp = LM._fill_polys(fills)
        self.fixed = set(fixed)
        self.gr = GridRouter(sp, halo=0.0)
        self.K = _load_kernels()
        self.W = box(*win["box"])
        self.field = box(*win["field"])
        self.stats = []
        self._cut()

    # ------------------------------------------------------------------ cut
    def _cut(self):
        sp, Wb = self.sp, self.W
        pad_nets = {it.net for it in sp.pads if it.kind == "pad" and it.net and it.geom.intersects(Wb)}
        field_nets = {it.net for it in sp.pads if it.kind == "pad" and it.net and it.fp == self.win["fp"]}
        if self.only is not None:
            pad_nets &= self.only
        rip, keep_arc = [], []
        for it in sp.existing + sp.routed:
            if it.kind not in ("track", "via") or not it.net or it.locked or it.uuid in self.fixed:
                continue
            if self.only is not None and (it.net not in self.only or it.net in self.fp):
                continue    # a step moves only its nets; plane nets' escapes and dog-bones stay
            if it.kind == "via":
                if Wb.contains(it.geom):
                    rip.append(it)
            elif it.geom.intersects(Wb):
                if len(it.geom.coords) > 2 and not Wb.contains(it.geom):
                    keep_arc.append(it)     # an arc across the border: kept whole
                else:
                    rip.append(it)
        self.nets = sorted(pad_nets | {it.net for it in rip}) if self.only is None else sorted(self.only)
        self.field_nets = field_nets
        self.before = {n: LM._open_count(sp, self.fp, n) for n in self.nets}
        self.ripped = rip
        self.ripped_by_net = {}
        for it in rip:
            self.ripped_by_net.setdefault(it.net, []).append(it)
        sp.remove(rip)
        self.stubs = []
        for it in rip:
            if it.kind != "track":
                continue
            rest = it.geom.difference(Wb)
            for g in getattr(rest, "geoms", [rest]):
                if g.is_empty or g.geom_type != "LineString" or g.length < 1e-3:
                    continue
                c = list(g.coords)
                layer = next(iter(it.layers))
                for a, b in zip(c[:-1], c[1:]):
                    s = sp.add_track(it.net, layer, it.width, a, b, owner=("region", "stub"))
                    s.uuid = W.new_uuid()
                    s.locked = False
                    s.pos = it.uuid      # the track it was cut from
                    self.stubs.append(s)
        self.log(f"region {self.win['ref']}: {len(self.nets)} nets, {len(rip)} tracks and vias taken out, "
                 f"{len(self.stubs)} border stubs, {sum(self.before.values())} open on these nets")

    # ------------------------------------------------------------------ setup
    def setup(self):
        sp = self.sp
        x0, y0, x1, y1 = self.W.bounds
        x0, y0, x1, y1 = x0 - GRID_MARGIN, y0 - GRID_MARGIN, x1 + GRID_MARGIN, y1 + GRID_MARGIN
        # the grid divides the pitch in an even number of cells and has a pad centre on a cell:
        # pad centres and the via sites between four balls are cell centres (a via between
        # 0.5 mm balls at 1.0 mm pitch has 7 um to spare; off the grid it finds no cell)
        pitch = self.win["pitch"]
        step = min(RES, max(RES_MIN, pitch / 16.0))
        k = max(2, 2 * int(round(pitch / (2 * step))))
        nl = len(sp.cu)
        while k > 2 and nl * ((x1 - x0) * k / pitch + 1) * ((y1 - y0) * k / pitch + 1) > MAX_CELLS:
            k -= 2
        res = pitch / k
        ox, oy = self.win["origin"]
        x0 = ox - math.ceil((ox - x0) / res) * res
        y0 = oy - math.ceil((oy - y0) / res) * res
        self.grid = g = Grid(x0, y0, x1, y1, res)
        self.nl, self.plane = nl, g.nx * g.ny
        # pours: crossing another net's pour cuts it (GridRouter.cost_layer's pour cost)
        bx = box(g.x0, g.y0, g.x1, g.y1)
        self.pour = np.zeros((nl, g.ny, g.nx), np.float32)
        self.pour_of = {}
        for li, l in enumerate(sp.cu):
            for zn in sorted({n for n, ll, gg, _ in sp.zones if ll == l}):
                polys = [gg for n, ll, gg, _ in sp.zones if ll == l and n == zn and gg.intersects(bx)]
                if polys:
                    m = _pour_mask(g, polys, bx)
                    self.pour[li][m] += self.gr.pour_cost
                    self.pour_of[(zn, li)] = m
        # width, layers and claim radii per net
        classes = {}
        for n in self.nets:
            classes.setdefault(sp.rc(n), n)
        self.width, self.layers, self.rho, self.rhov, self.vsize = {}, {}, {}, {}, {}
        for n in self.nets:
            best = None
            for w in LM.widths_of(sp, n):
                ok = [l for l in sp.cu if LM._width_ok(sp, n, l, w)]
                if ok and (best is None or (len(ok), -w) > (len(best[1]), -best[0])):
                    best = (w, ok)
            if best is None:
                best = (0.2, list(sp.cu))
            self.width[n], self.layers[n] = best
            ct = cv = 0.0
            for rep in classes.values():
                for l in sp.cu:
                    c = sp._pair(n, rep, l) if rep != n else sp._pair(n, n + "\x00", l)
                    if c is not None:
                        ct = max(ct, c.track_track, c.track_via)
                        cv = max(cv, c.via_via, c.via_track, c.track_via)
            if not ct:
                ct = max(sp._generic_need(n, "track", l) for l in sp.cu)
            if not cv:
                cv = ct
            D, _d = sp.via_size(n)
            self.vsize[n] = D
            self.rho[n] = round(best[0] / 2 + ct / 2, 4)
            self.rhov[n] = round(D / 2 + cv / 2, 4)
        self.groups = sorted({self.rho[n] for n in self.nets} | {self.rhov[n] for n in self.nets})
        self.occ = {r: np.zeros((nl, g.ny, g.nx), np.int16) for r in self.groups}
        self.hist = np.zeros((nl, g.ny, g.nx), np.float32)
        self.vhist = np.zeros((g.ny, g.nx), np.float32)
        self.base = {}
        self.claims = {}
        self.routes = {}
        self._terminals()

    def _base(self, n):
        """(blocked bits, via-allowed bits) of net n on the grid, cached packed."""
        hit = self.base.get(n)
        if hit is None:
            g, sp = self.grid, self.sp
            w = self.width[n]
            blk = np.ones((self.nl, g.ny, g.nx), bool)
            for li, l in enumerate(sp.cu):
                if l in self.layers[n]:
                    blk[li] = self.gr.blocked(g, n, l, w, "track")
            if len(self.layers[n]) > 1:
                via = self.gr.via_allowed(g, n, sp.cu)
            else:
                via = np.zeros((g.ny, g.nx), bool)
            hit = (np.packbits(blk), np.packbits(via))
            self.base[n] = hit
        blk = np.unpackbits(hit[0], count=self.nl * self.plane).astype(bool).reshape(self.nl, self.grid.ny,
                                                                                    self.grid.nx)
        via = np.unpackbits(hit[1], count=self.plane).astype(bool).reshape(self.grid.ny, self.grid.nx)
        return blk, via

    # ------------------------------------------------------------------ terminals
    def _terminals(self):
        """Per net: the groups of copper to join inside the window (cell sets) and, for a signal
        net of the field with parts that reach no other part inside, the side to escape to."""
        sp, g = self.sp, self.grid
        clip = self.W.buffer(GRID_MARGIN * 0.5)
        self.terms, self.esc_cells, self.depth, self.term_cells = {}, {}, {}, {}
        self._stencils = {}
        fx0, fy0, fx1, fy1 = self.win["field"]
        pitch = self.win["pitch"]
        for n in self.nets:
            w = self.width[n]
            ps = [p for p in LM.parts(sp, self.fp, n) if LM._relevant(p)]
            blk, _via = self._base(n)
            cost = np.where(blk, INF, 1.0).reshape(-1)
            groups, outside, own = [], [], []
            for p in ps:
                anchors = LM._anchors(p, w / 2 + 0.02, clip=clip)
                cells, esc = self._anchor_cells(n, anchors, cost)
                if cells.size:
                    own.append((cells, esc, 0))
                    fl = self._float(n, p, cost)
                    groups.append((np.union1d(cells, fl) if fl.size else cells, esc,
                                   sum(1 for x in p if x.kind == "pad")))
                elif anchors:
                    groups.append((cells, esc, -1))       # inside, but no free cell: unroutable
                else:
                    outside.append(p)
            groups = [x for x in groups if x[2] >= 0] + [x for x in groups if x[2] < 0]
            side = None
            has_fill = any(x.kind == "fill" for p in ps for x in p)
            if outside and groups and n in self.field_nets and not has_fill and self.only is None:
                # the nearest copper of the other parts: the side of the window it lies beyond
                best = None
                for p in outside:
                    for x in p:
                        d = x.copper.distance(self.field)
                        if best is None or d < best[0]:
                            best = (d, x.copper.centroid)
                q = best[1]
                X0, Y0, X1, Y1 = self.W.bounds
                ex = {"W": X0 - q.x, "E": q.x - X1, "S": Y0 - q.y, "N": q.y - Y1}
                side = max(sorted(ex), key=lambda k: ex[k])
            self.terms[n] = dict(groups=groups, side=side, parts=len(ps))
            self.term_cells[n] = self._deep(own, w)
            # depth: rows of the field from its outside to the net's innermost pad
            dmax = 0
            for it in sp.pads:
                if it.net == n and it.fp == self.win["fp"]:
                    x, y = it.pos
                    dmax = max(dmax, int(min(x - fx0, fx1 - x, y - fy0, fy1 - y) / pitch + 0.5))
            self.depth[n] = dmax
        self.conns = {n: max(0, len([x for x in t["groups"] if x[2] >= 0]) - 1) + (1 if t["side"] else 0)
                      for n, t in self.terms.items()}

    def _float(self, n, part, cost):
        """Floating border terminal of a part that reaches the window through stubs: the free
        cells of the border band within FLOAT_MM of where a stub meets the border, on the net's
        layers (GRIP's floating terminals: a crossing fixed where Freerouting made it can make
        the window infeasible by itself). A route ending there is stitched to the stub outside
        the window after the commit (`commit`)."""
        pts = []
        bd = self.W.boundary
        for x in part:
            it = x.item
            if x.kind == "track" and it.owner == ("region", "stub"):
                for c in (it.geom.coords[0], it.geom.coords[-1]):
                    if bd.distance(Point(c)) < 1e-6:
                        pts.append(c)
        if not pts or FLOAT_MM <= 0:
            return np.zeros(0, np.int64)
        if not hasattr(self, "_band"):
            self._band = np.unique(np.concatenate([self._side_cells(sd) for sd in "WESN"])) % self.plane
            self._band = np.unique(self._band)
        g = self.grid
        bx, by = g.x0 + (self._band % g.nx) * g.res, g.y0 + (self._band // g.nx) * g.res
        near = np.zeros(self._band.size, bool)
        for (x, y) in pts:
            near |= np.hypot(bx - x, by - y) <= FLOAT_MM
        r = self._band[near]
        cells = np.concatenate([self.sp.cu.index(l) * self.plane + r for l in self.layers[n]])
        return cells[np.isfinite(cost[cells])]

    def _deep(self, groups, w):
        """The terminal cells a track of width w centred there keeps inside the terminal's
        copper: the groups' cells, eroded by half the width (and half a cell) on each layer."""
        from scipy import ndimage
        tc = [x[0] for x in groups if x[0].size]
        if not tc:
            return np.zeros(0, np.int64)
        m = np.zeros(self.nl * self.plane, bool)
        m[np.concatenate(tc)] = True
        m = m.reshape(self.nl, self.grid.ny, self.grid.nx)
        r = (w / 2 + 0.5 * self.grid.res) / self.grid.res
        k = int(math.ceil(r))
        dj, di = np.mgrid[-k:k + 1, -k:k + 1]
        st = np.hypot(di, dj) <= r
        out = np.zeros_like(m)
        for li in range(self.nl):
            if m[li].any():
                out[li] = ndimage.binary_erosion(m[li], structure=st, border_value=0)
        return np.flatnonzero(out)

    def _anchor_cells(self, n, anchors, cost):
        """Flat 3D cells of the anchors on the net's layers, and the escape pieces of pads with
        no free cell {cell: [pts]} (GridRouter._escapes)."""
        g, sp, gr = self.grid, self.sp, self.gr
        out, esc = [], {}
        for a in anchors:
            for li, l in enumerate(sp.cu):
                if l not in a.layers or l not in self.layers[n]:
                    continue
                k = gr._cells(g, a, li, cost, self.plane, l)
                if k.size == 0 and a.kind == "pad":
                    found = gr._escapes(g, n, self.width[n], a, l, li, cost, self.plane)
                    for kk, pts in found:
                        esc.setdefault(int(kk), pts)
                    k = np.array([kk for kk, _ in found], np.int64)
                out.append(k)
        cells = np.unique(np.concatenate(out)) if out else np.zeros(0, np.int64)
        return cells, esc

    def _side_cells(self, side):
        """The cells of a band two cells deep along one side of the window, on every layer."""
        g = self.grid
        X0, Y0, X1, Y1 = self.W.bounds
        i0, j0 = g.ij(X0, Y0)
        i1, j1 = g.ij(X1, Y1)
        i0, j0 = max(0, i0), max(0, j0)
        i1, j1 = min(g.nx - 1, i1), min(g.ny - 1, j1)
        m = np.zeros((g.ny, g.nx), bool)
        if side == "W":
            m[j0:j1 + 1, i0:i0 + 2] = True
        elif side == "E":
            m[j0:j1 + 1, i1 - 1:i1 + 1] = True
        elif side == "S":
            m[j0:j0 + 2, i0:i1 + 1] = True
        else:
            m[j1 - 1:j1 + 1, i0:i1 + 1] = True
        r = np.flatnonzero(m)
        return np.concatenate([li * self.plane + r for li in range(self.nl)])

    # ------------------------------------------------------------------ claims
    def _free_cells(self, rt):
        """The route's path cells outside its own terminal copper (pads, stubs, fills): inside
        that copper a track adds nothing another net must keep clear of beyond the copper itself
        (the base raster already keeps other nets clear of it)."""
        c = np.asarray(rt.cells, np.int64)
        if c.size == 0:
            return c
        t = self.term_cells.get(rt.net)
        return c[~np.isin(c, t)] if t is not None and t.size else c

    def _disc(self, cells, R):
        """In-plane flat indices of the cells within R of the in-plane cells `cells`."""
        g = self.grid
        key = round(R, 6)
        st = self._stencils.get(key)
        if st is None:
            k = int(math.ceil(R / g.res))
            dj, di = np.mgrid[-k:k + 1, -k:k + 1]
            m = np.hypot(di, dj) * g.res <= R
            st = self._stencils[key] = (di[m], dj[m])
        ci, cj = cells % g.nx, cells // g.nx
        i = (ci[:, None] + st[0][None, :]).ravel()
        j = (cj[:, None] + st[1][None, :]).ravel()
        ok = (i >= 0) & (j >= 0) & (i < g.nx) & (j < g.ny)
        return np.unique(j[ok] * g.nx + i[ok])

    def _claim(self, rt, sign):
        """Add (sign 1) or take out (-1) the cells route `rt` claims, in every radius group: the
        cells within the two claim radii (and the move margin, critical_grid._margin) of its path
        cells outside its own terminal copper, on their layer, and of its vias, on every layer."""
        n = rt.net
        if sign > 0:
            g = self.grid
            cl = {}
            free = self._free_cells(rt)
            lis = free // self.plane
            for r in self.groups:
                idx = []
                R = self.rho[n] + r + TOL
                R += _margin(R, g.res)
                for li in np.unique(lis):
                    idx.append(li * self.plane + self._disc(free[lis == li] % self.plane, R))
                if rt.vcells:
                    R = self.rhov[n] + r + TOL
                    R += _margin(R, g.res)
                    k = self._disc(np.asarray(rt.vcells, np.int64), R)
                    for li in range(self.nl):
                        idx.append(li * self.plane + k)
                cl[r] = np.unique(np.concatenate(idx)) if idx else np.zeros(0, np.int64)
            self.claims[n] = cl
        cl = self.claims.get(n) or {}
        for r, idx in cl.items():
            if idx.size:
                f = self.occ[r].reshape(-1)
                f[idx] += np.int16(sign)
        if sign < 0:
            self.claims.pop(n, None)

    def _conflicts(self, rt):
        """Path cells (outside its terminal copper) and via cells of route `rt` that other nets
        claim (its own claims counted out); a via cell r is given as -1 - r."""
        n = rt.net
        f = self.occ[self.rho[n]].reshape(-1)
        free = self._free_cells(rt)
        bad = free[f[free] > 1].tolist() if free.size else []
        if rt.vcells:
            fv = self.occ[self.rhov[n]].reshape(self.nl, -1)
            for r in rt.vcells:
                if (fv[:, r] > 1).any():
                    bad.append(-1 - r)
        return bad

    # ------------------------------------------------------------------ one net
    def _route_net(self, n, pf):
        sp, g = self.sp, self.grid
        t = self.terms[n]
        rt = _Route(n, self.width[n])
        groups = [x for x in t["groups"] if x[2] >= 0]
        if not groups or (len(groups) < 2 and not t["side"]):
            return rt
        blk, via = self._base(n)
        li_of = {l: li for li, l in enumerate(sp.cu)}
        occ_t = self.occ[self.rho[n]].astype(np.float32)
        cost = (1.0 + self.pour + self.hist) * (1.0 + pf * occ_t)
        for zl, m in self.pour_of.items():
            if zl[0] == n:
                cost[zl[1]][m] -= self.gr.pour_cost * (1.0 + pf * occ_t[zl[1]][m])
        cost[blk] = INF
        flat = cost.reshape(-1).astype(np.float64)
        if via.any():
            ov = self.occ[self.rhov[n]].sum(axis=0).astype(np.float32)
            viac = np.where(via, VIA_COST * (1.0 + pf * ov) + self.vhist, INF).reshape(-1).astype(np.float64)
        else:
            viac = np.full(self.plane, INF)
        tree = groups[0][0]
        esc = dict(groups[0][1])
        rest = sorted(groups[1:], key=lambda x: self._dist(x[0], tree))
        jobs = [(x[0], x[1], None) for x in rest]
        if t["side"]:
            jobs.append((None, {}, t["side"]))
        for src_cells, src_esc, side in jobs:
            if side is None:
                src, dst_cells, s_esc, d_esc = src_cells, tree, src_esc, esc
            else:
                src, dst_cells, s_esc, d_esc = tree, self._side_cells(side), esc, {}
            dst = np.zeros(self.nl * self.plane, bool)
            dst[dst_cells] = True
            if dst[src].any():
                rt.conns += 1
                if side is None:
                    tree = np.union1d(tree, src_cells)
                    esc.update(src_esc)
                continue
            r = dst_cells % self.plane
            ii, jj = r % g.nx, r // g.nx
            path, _nexp = self.K.astar_v(flat, viac, src.astype(np.int64), dst, self.nl, g.ny, g.nx, g.res,
                                         int(ii.min()), int(ii.max()), int(jj.min()), int(jj.max()), MAX_EXP)
            if path.size == 0:
                rt.failed += 1
                continue
            self._add_path(rt, path, s_esc, d_esc)
            rt.conns += 1
            if side is not None:
                rt.escape = side
            if n in self.fp:
                continue        # a plane net: each part joins its fill on its own, never a tree
            vias = [int(k) % self.plane for k in rt.vcells]
            tree = np.union1d(tree, path)
            if vias:
                tree = np.union1d(tree, np.concatenate([li * self.plane + np.array(vias, np.int64)
                                                        for li in range(self.nl)]))
            if side is None:
                tree = np.union1d(tree, src_cells)
                esc.update(src_esc)
        return rt

    def _dist(self, a, b):
        g = self.grid
        ra, rb = a % self.plane, b % self.plane
        ax, ay = (ra % g.nx).mean(), (ra // g.nx).mean()
        bx, by = (rb % g.nx), (rb // g.nx)
        return float(np.min(np.hypot(bx - ax, by - ay)))

    def _add_path(self, rt, path, s_esc, d_esc):
        g = self.grid
        cu = self.sp.cu
        pl = path.tolist()
        pre, post = s_esc.get(pl[0]), d_esc.get(pl[-1])
        runs, prev = [], None
        for k in pl:
            li, r = divmod(k, self.plane)
            j, i = divmod(r, g.nx)
            p = g.xy(i, j)
            if prev is None or li != prev:
                if prev is not None:
                    rt.vias.append(p)
                    rt.vcells.append(r)
                runs.append([cu[li], [p]])
                prev = li
            else:
                runs[-1][1].append(p)
        if pre:
            runs[0][1] = list(pre) + runs[0][1]
        if post:
            runs[-1][1] = runs[-1][1] + list(post[::-1])
        for ri, (l, pts) in enumerate(runs):
            pts = _merge_collinear(pts)
            exact = bool((ri == 0 and pre) or (ri == len(runs) - 1 and post))
            rt.runs.append((l, pts, exact))
            rt.length += sum(math.dist(a, b) for a, b in zip(pts[:-1], pts[1:]))
        rt.cells.extend(pl)

    # ------------------------------------------------------------------ negotiation
    def _state(self, todo):
        bad = {n: self._conflicts(self.routes[n]) for n in todo if n in self.routes}
        conflict = {n for n, b in bad.items() if b}
        failed = sum(rt.failed for rt in self.routes.values())
        over = int(sum(len(b) for b in bad.values()))
        length = sum(rt.length for rt in self.routes.values())
        return bad, conflict, failed, over, length

    def _record(self, phase, it, pf, conflict, failed, over, length, ti, **kw):
        rec = dict(phase=phase, iter=it, pres_fac=round(pf, 3), nets_in_conflict=len(conflict),
                   conflict_cells=over, failed=failed, length=round(length, 1),
                   seconds=round(time.monotonic() - ti, 2), **kw)
        self.stats.append(rec)
        return rec

    def run(self, deadline=None, max_iter=MAX_ITER):
        """Negotiate (see the module docstring), then repair what still conflicts by large
        neighbourhood search (`_repair`). Returns whether no conflict is left."""
        t0 = time.monotonic()
        self.deadline = deadline
        rng = np.random.default_rng(self.seed)
        todo = [n for n in self.nets if self.conns.get(n)]
        tie = {n: float(rng.random()) for n in todo}
        conflict = set()
        pf = 0.0
        best, since = None, 0
        t_neg = None if deadline is None else t0 + NEG_SHARE * (deadline - t0)
        for it in range(max_iter):
            ti = time.monotonic()
            if it == 0:
                order = sorted(todo, key=lambda n: (-self.depth[n], tie[n]))
            else:
                # only the nets in conflict are ripped (connection-based reroute), in a seeded
                # shuffle (a fixed order lets the same net win every time)
                order = sorted(conflict, key=lambda n: (-self.depth[n], tie[n]))
                order = [order[k] for k in rng.permutation(len(order))]
            for n in order:
                if t_neg is not None and time.monotonic() > t_neg:
                    break
                if n in self.routes:
                    self._claim(self.routes[n], -1)
                rt = self._route_net(n, pf)
                self.routes[n] = rt
                self._claim(rt, 1)
            bad, conflict, failed, over, length = self._state(todo)
            rec = self._record("negotiate", it + 1, pf, conflict, failed, over, length, ti, rerouted=len(order))
            self.log(f"region {self.win['ref']} iteration {it + 1}: {len(conflict)} nets in conflict "
                     f"({over} cells), {failed} connections without a path, pres_fac {pf:.2f}, "
                     f"{len(order)} rerouted ({rec['seconds']} s)")
            key = (len(conflict), failed, over, length)
            if best is None or key < best[0]:
                best, since = (key, it + 1, dict(self.routes), set(conflict)), 0
            else:
                since += 1
            if not conflict or (t_neg is not None and time.monotonic() > t_neg) or since >= STALL:
                break
            for n in conflict:
                for k in bad[n]:
                    if k >= 0:
                        self.hist.reshape(-1)[k] += HIST_FAC
                    else:
                        self.vhist.reshape(-1)[-1 - k] += HIST_FAC * VIA_COST
            pf = PRES_FIRST if pf == 0.0 else min(PRES_MAX, pf * PRES_MULT)
        self.best_iter = best[1] if best else 0
        self.best = best[2] if best else {}
        if self.best_iter != len(self.stats):
            self._reclaim(self.best)
        self.best_conflict = best[3] if best else set()
        if self.best_conflict and (deadline is None or time.monotonic() < deadline):
            self._repair(todo, rng, deadline)
        self.converged = bool(best and not self.best_conflict)
        self.seconds = round(time.monotonic() - t0, 1)
        return self.converged

    def _reclaim(self, routes):
        """Occupancy rebuilt from `routes` (the state kept)."""
        for r in self.groups:
            self.occ[r][:] = 0
        self.claims = {}
        self.routes = dict(routes)
        for rt in self.routes.values():
            self._claim(rt, 1)

    def _repair(self, todo, rng, deadline):
        """Large neighbourhood search on the kept state (MAPF-LNS2, Li et al. AAAI'22): pick up
        to LNS_SIZE nets around a conflict (a random walk in the graph of nets whose claims
        meet), re-route them one by one in a random order at a price that makes another net's
        cell all but forbidden (lexicographic: conflicts first, then length), and keep the move
        only when the nets in conflict (then the cells) are no more than before. Progress never
        goes backwards; it stops at no conflict, the deadline or LNS_STALL moves in a row
        without a gain."""
        bad, conflict, failed, over, length = self._state(todo)
        cur = (len(conflict), failed, over)
        graph = self._graph(conflict)
        stall, k = 0, 0
        ti = time.monotonic()
        while conflict and stall < LNS_STALL and (deadline is None or time.monotonic() < deadline):
            k += 1
            start = sorted(conflict)[int(rng.integers(len(conflict)))]
            nb, at = [start], start
            for _ in range(4 * LNS_SIZE):
                if len(nb) >= LNS_SIZE:
                    break
                nxt = sorted(graph.get(at) or ())
                if not nxt:
                    at = nb[int(rng.integers(len(nb)))]
                    continue
                at = nxt[int(rng.integers(len(nxt)))]
                if at not in nb:
                    nb.append(at)
            old = {n: self.routes[n] for n in nb if n in self.routes}
            for n in nb:
                if n in self.routes:
                    self._claim(self.routes[n], -1)
            for i in rng.permutation(len(nb)):
                n = nb[int(i)]
                rt = self._route_net(n, LNS_PRES)
                self.routes[n] = rt
                self._claim(rt, 1)
            bad2, conflict2, failed2, over2, length2 = self._state(todo)
            new = (len(conflict2), failed2, over2)
            if new <= cur:
                stall = 0 if new < cur else stall + 1
                cur, conflict = new, conflict2
                graph = self._graph(conflict)
            else:
                stall += 1
                for n in nb:
                    self._claim(self.routes[n], -1)
                for n, rt in old.items():
                    self.routes[n] = rt
                    self._claim(rt, 1)
            if k % 10 == 0 or not conflict:
                _b, cf, fl, ov, ln = self._state(todo)
                self._record("repair", k, LNS_PRES, cf, fl, ov, ln, ti, neighbourhood=len(nb))
                self.log(f"region {self.win['ref']} repair {k}: {len(cf)} nets in conflict ({ov} cells)")
                ti = time.monotonic()
        self.best = dict(self.routes)
        _b, self.best_conflict, _f, _o, _l = self._state(todo)
        self.best_iter = len(self.stats)

    def _graph(self, conflict):
        """Nets in conflict whose routes come near each other (bounding boxes of their path
        cells, grown by two claim radii, overlap): {net: {nets}}, the repair's neighbourhoods."""
        g = self.grid
        bb = {}
        for n in conflict:
            rt = self.routes.get(n)
            c = np.asarray(rt.cells if rt else [], np.int64) % self.plane
            if c.size == 0:
                continue
            grow = 2 * max(self.rho[n], self.rhov[n]) / g.res + 1
            i, j = c % g.nx, c // g.nx
            bb[n] = (i.min() - grow, j.min() - grow, i.max() + grow, j.max() + grow)
        names = sorted(bb)
        out = {}
        for x, a in enumerate(names):
            A = bb[a]
            for b_ in names[x + 1:]:
                B = bb[b_]
                if A[0] <= B[2] and B[0] <= A[2] and A[1] <= B[3] and B[1] <= A[3]:
                    out.setdefault(a, set()).add(b_)
                    out.setdefault(b_, set()).add(a)
        return out

    # ------------------------------------------------------------------ commit
    def commit(self):
        """Lay the kept iteration's routes exactly (see the module docstring); returns a summary."""
        sp = self.sp
        laid, rejected, blockers = [], [], {}
        order = sorted(self.best, key=lambda n: (n in self.best_conflict, -self.depth[n], n))
        self.new = []
        for n in order:
            rt = self.best[n]
            if not rt.runs and not rt.vias:
                continue
            items, bad = [], None
            if rt.failed:
                rejected.append(n)       # a connection with no path: the old copper first
                blockers[n] = None
                continue
            for (x, y) in rt.vias:
                v = sp.via_violations(n, x, y, first=True)
                if v:
                    bad = v[0][0]
                    break
                it = sp.add_via(n, x, y, owner=("region", n))
                it.uuid = W.new_uuid()
                items.append(it)
            if bad is None:
                for (l, pts, exact) in rt.runs:
                    tol = EXACT_TOL if exact else TOL
                    for a, b in zip(pts[:-1], pts[1:]):
                        if math.dist(a, b) < 1e-6:
                            continue
                        v = sp.track_violations(n, l, rt.width, a, b, first=True, tol=tol)
                        if v:
                            bad = v[0][0]
                            break
                    if bad is not None:
                        break
            if bad is not None:
                sp.remove(items)
                rejected.append(n)
                blockers[n] = getattr(bad, "net", None) if bad != "edge" else "edge"
                continue
            for (l, pts, exact) in rt.runs:
                for a, b in zip(pts[:-1], pts[1:]):
                    if math.dist(a, b) < 1e-6:
                        continue
                    it = sp.add_track(n, l, rt.width, a, b, owner=("region", n))
                    it.uuid = W.new_uuid()
                    items.append(it)
            self.new += items
            laid.append(n)
        # string pulling once every route lies (pulling one before the next is laid takes the room
        # the negotiation gave that one): each run shortened with all the other copper in place
        for n in laid:
            rt = self.best[n]
            mine = [it for it in self.new if it.kind == "track" and it.owner == ("region", n)]
            sp.remove(mine)
            self.new = [it for it in self.new if not (it.kind == "track" and it.owner == ("region", n))]
            for (l, pts, exact) in rt.runs:
                if not exact:
                    pts = self.gr._pull(n, l, rt.width, pts)
                for a, b in zip(pts[:-1], pts[1:]):
                    if math.dist(a, b) < 1e-6:
                        continue
                    it = sp.add_track(n, l, rt.width, a, b, owner=("region", n))
                    it.uuid = W.new_uuid()
                    self.new.append(it)
        # nets whose route did not fit: their old copper where it still fits, else a plain join
        restored, joined = [], []
        for n in rejected + [n for n in self.nets if n not in self.best]:
            old = self.ripped_by_net.get(n) or []
            if old and not any(self._hits(it) for it in old):
                stubs = [s for s in self.stubs if s.net == n]
                sp.remove(stubs)
                self.stubs = [s for s in self.stubs if s.net != n]
                LM._restore(sp, old)
                restored.append(n)
                for it in old:
                    self.ripped.remove(it)
        # what is still apart (a route that ended on a floating border terminal, a net that did
        # not fit): a plain grid join, around everything (lastmile._join without rip-up)
        stitch = [n for n in rejected if n not in restored] + [n for n in laid if n not in rejected]
        for n in stitch:
            if self.deadline is not None and time.monotonic() > self.deadline:
                break
            ps = [p for p in LM.parts(sp, self.fp, n) if LM._relevant(p)]
            if len(ps) < 2 or not any(self.W.intersects(x.copper) for p in ps[1:] for x in p):
                continue
            k = 0
            while len(ps) > 1 and k < 8:
                k += 1
                widths = LM.widths_of(sp, n)
                src = LM._anchors(ps[-1], max(widths) / 2 + 0.02)
                got = LM._join(self.gr, sp, n, src, ps[:-1], widths, self.fixed, rip=False) if src else None
                if got is None:
                    break
                for it in got[1]:
                    it.owner = ("region", n)
                self.new += got[1]
                ps = [p for p in LM.parts(sp, self.fp, n) if LM._relevant(p)]
            if k and len(ps) <= 1:
                joined.append(n)
        self.after = {n: LM._open_count(sp, self.fp, n) for n in self.nets}
        return dict(laid=len(laid), rejected=len(rejected), restored=len(restored), joined=len(joined),
                    rejected_by={n: blockers.get(n) for n in rejected[:40]},
                    escapes=sum(1 for n in laid if self.best[n].escape))

    def _hits(self, it):
        """Whether old item `it` breaks a requirement against the copper laid (exact)."""
        sp = self.sp
        if it.kind == "track":
            c = list(it.geom.coords)
            layer = next(iter(it.layers))
            return any(sp.track_violations(it.net, layer, it.width, a, b, first=True)
                       for a, b in zip(c[:-1], c[1:]))
        return bool(sp.via_violations(it.net, it.geom.x, it.geom.y, size=it.width, drill=it.drill,
                                      layers=list(it.layers), first=True))

    def write(self, board, out):
        """`out` = `board` without the copper taken out, with the stubs (unlocked, as the tracks
        they come from) and the new copper (locked, as the last mile's). Returns the new uuids."""
        tracks, vias = [], []
        for it in self.stubs:
            tracks.append((it.net, next(iter(it.layers)), it.width, tuple(it.geom.coords[0]),
                           tuple(it.geom.coords[-1]), it.uuid, False))
        for it in self.new:
            if it.kind == "track":
                tracks.append((it.net, next(iter(it.layers)), it.width, tuple(it.geom.coords[0]),
                               tuple(it.geom.coords[-1]), it.uuid, True))
            else:
                vias.append((it.net, it.geom.x, it.geom.y, it.width, it.drill, it.uuid, True))
        W.edit(board, out, remove=[it.uuid for it in self.ripped if it.uuid])
        if tracks or vias:
            W.append_items(out, out, tracks=tracks, vias=vias)
        return [it.uuid for it in self.new]

    # ------------------------------------------------------------------ capacity
    def capacity(self, max_lines=12):
        """Where the kept iteration overflows: channels between neighbouring pads of the window
        that more nets cross than the rules leave room for, and via sites wanted by more than
        one net. [dict(kind, where, layer, needs, holds, nets, line)], worst first."""
        from scipy.spatial import cKDTree
        sp = self.sp
        pads = [it for it in sp.pads if it.kind == "pad" and it.geom.intersects(self.field)
                and it.fp == self.win["fp"]]
        out = []
        if len(pads) < 2:
            return out
        P = np.array([p.pos for p in pads])
        pitch = self.win["pitch"]
        pairs = sorted(cKDTree(P).query_pairs(1.5 * pitch))
        segs_by_layer = {}
        for n, rt in self.best.items():
            for (l, pts, _x) in rt.runs:
                for a, b in zip(pts[:-1], pts[1:]):
                    segs_by_layer.setdefault(l, []).append((n, LineString([a, b])))
        conflict = self.best_conflict
        ws = sorted(self.width[n] for n in self.nets) or [0.2]
        w = ws[0]
        for l in sp.cu:
            segs = segs_by_layer.get(l) or []
            if not segs:
                continue
            for i, j in pairs:
                A, B = pads[i], pads[j]
                if l not in A.layers or l not in B.layers:
                    continue
                cut = LineString([A.pos, B.pos])
                nets = sorted({n for n, s in segs if s.intersects(cut)})
                if len(nets) < 2 or not (set(nets) & conflict):
                    continue
                # room: the copper gap between the two pads on the cut, less a pad clearance at
                # each side; each track takes its width and a track clearance
                gap = cut.length - _along(A.geom, cut) - _along(B.geom, cut)
                n0 = nets[0]
                cp = max(sp.need(A, n0, "track", l) or 0.0, sp.need(B, n0, "track", l) or 0.0)
                c = sp._pair(n0, nets[1], l)
                ct = c.track_track if c is not None else cp
                room = gap - 2 * cp
                holds = 0 if room < w else int((room - w) // (w + ct)) + 1
                if len(nets) > holds:
                    where = f"{A.owner[0]}.{A.owner[1]}-{B.owner[0]}.{B.owner[1]}"
                    out.append(dict(kind="channel", where=where, layer=l, needs=len(nets), holds=holds,
                                    gap=round(gap, 4), track=round(w, 4), clearance=round(ct, 4),
                                    pad_clearance=round(cp, 4), nets=nets,
                                    at=[round((A.pos[0] + B.pos[0]) / 2, 3), round((A.pos[1] + B.pos[1]) / 2, 3)],
                                    line=f"channel {where} on {l}: {len(nets)} nets cross, room for {holds} "
                                         f"(gap {gap:.3f} mm between the pads; track {w:.3f} mm, clearance "
                                         f"{ct:.3f} mm, pad clearance {cp:.3f} mm)"))
        # via sites: vias of different nets closer than their claims allow
        vs = [(n, x, y) for n, rt in self.best.items() for (x, y) in rt.vias]
        if len(vs) > 1:
            V = np.array([(x, y) for _, x, y in vs])
            for i, j in sorted(cKDTree(V).query_pairs(2 * max(self.rhov.values()))):
                a, b = vs[i], vs[j]
                if a[0] == b[0]:
                    continue
                if math.dist(a[1:], b[1:]) < self.rhov[a[0]] + self.rhov[b[0]]:
                    need = self.rhov[a[0]] + self.rhov[b[0]]
                    out.append(dict(kind="via site", where=f"({a[1]:.2f}, {a[2]:.2f})", layer="all", needs=2,
                                    holds=1, nets=sorted({a[0], b[0]}), at=[round(a[1], 3), round(a[2], 3)],
                                    line=f"via site at ({a[1]:.2f}, {a[2]:.2f}): vias of {a[0]} and {b[0]} "
                                         f"{math.dist(a[1:], b[1:]):.3f} mm apart, the rules need {need:.3f} mm "
                                         f"(via {self.vsize[a[0]]:.3f} mm and its clearance)"))
        out.sort(key=lambda r: (-(r["needs"] - r["holds"]), r["kind"], r["where"]))
        return out[:max_lines]

    def conflicts(self, max_items=200, nets=None):
        """The kept iteration's conflicts: [dict(net, others, layer, at, kind ("track" | "via"))],
        one per net and layer cluster of cells (the first cell of each run of conflicting cells)."""
        out = []
        g = self.grid
        for n in sorted(self.best_conflict if nets is None else nets):
            rt = self.routes.get(n)
            if rt is None:
                continue
            bad = self._conflicts(rt)
            seen = set()
            for k in bad:
                if k >= 0:
                    li, r = divmod(int(k), self.plane)
                    kind, lays = "track", [li]
                    grp = self.rho[n]
                else:
                    r, kind, lays = -1 - int(k), "via", list(range(self.nl))
                    grp = self.rhov[n]
                j, i = divmod(r, g.nx)
                key = (kind, lays[0], i // 4, j // 4)
                if key in seen:
                    continue
                seen.add(key)
                others = sorted(m for m, cl in self.claims.items() if m != n and np.isin(
                    [li_ * self.plane + r for li_ in lays], cl.get(grp, np.zeros(0, np.int64))).any())
                x, y = g.xy(i, j)
                out.append(dict(net=n, others=others, kind=kind, layer=self.sp.cu[lays[0]] if kind == "track" else "all",
                                at=[round(x, 3), round(y, 3)]))
                if len(out) >= max_items:
                    return out
        return out

    def bound(self, rounds=3, eps=0.5, deadline=None):
        """A lower bound from weak duality (min-max resource sharing; BonnRoute, Garg and
        Koenemann): for any prices y >= 0 on resources of capacity 1, if the nets' cheapest
        routes cost more in total than all the prices, no routing exists. Resources are blocks
        of b x b cells whose diagonal is shorter than the closest two centrelines of different
        nets may come (the narrowest width plus the smallest clearance of the window), so no
        two nets' tracks pass through one block on a layer; a via takes its block on every
        layer. A route's centreline crosses an 8-connected chain of blocks, so a shortest path
        over blocks priced y, with each move charged at most the mean of its two blocks, is a
        lower bound of what any legal route of the net uses. Prices start from the negotiation
        history and grow multiplicatively on the blocks the cheapest routes use. It holds for
        the window with its border copper fixed (routes inside the window only). Returns
        dict(ratio, proof, rounds, block, bottleneck [(layer, x, y)])."""
        sp, g = self.sp, self.grid
        todo = [n for n in self.nets if self.conns.get(n)]
        if not todo:
            return None
        reps = {}
        for n in todo:
            reps.setdefault(sp.rc(n), n)
        cmin = None
        for a in reps.values():
            for c_ in reps.values():
                for l in sp.cu:
                    c = sp._pair(a, c_ if c_ != a else a + "\x00", l)
                    if c is not None:
                        cmin = c.track_track if cmin is None else min(cmin, c.track_track)
        wmin = min(min(LM.widths_of(sp, n)) for n in todo)
        dmin = wmin + (cmin or 0.0)
        b = max(1, int(math.floor(dmin / (math.sqrt(2) * g.res) - 1e-9)))
        nyb, nxb = -(-g.ny // b), -(-g.nx // b)
        pb = nyb * nxb

        def blocks(a, pad=0):    # (nl, ny, nx) -> (nl, nyb, b, nxb, b), the grid padded with `pad`
            out = np.full((a.shape[0], nyb * b, nxb * b), pad, a.dtype)
            out[:, :g.ny, :g.nx] = a
            return out.reshape(a.shape[0], nyb, b, nxb, b)

        def to_block(cells):
            li, r = cells // self.plane, cells % self.plane
            return np.unique(li * pb + (r // g.nx // b) * nxb + (r % g.nx) // b)
        y = blocks(self.hist.astype(np.float64)).sum(axis=(2, 4)).reshape(-1) + 1e-6
        res_b = g.res * b
        best = dict(ratio=0.0, proof=False, rounds=0, block=round(res_b, 4), bottleneck=[])
        cache = {}
        for rnd in range(rounds):
            if deadline is not None and time.monotonic() > deadline:
                break
            total, used = 0.0, np.zeros_like(y)
            for n in todo:
                if n not in cache:
                    blk, via = self._base(n)
                    free = ~blocks(blk, True).all(axis=(2, 4)).reshape(-1)
                    viab = blocks(via[None].astype(np.uint8)).max(axis=(2, 4)).reshape(-1).astype(bool)
                    t = self.terms[n]
                    gr_ = [to_block(x[0]) for x in t["groups"] if x[2] >= 0]
                    if t["side"]:
                        gr_.append(to_block(self._side_cells(t["side"])))
                    cache[n] = (free, viab, gr_)
                free, viab, gr_ = cache[n]
                if len(gr_) < 2:
                    continue
                cost = np.where(free, y / (res_b * math.sqrt(2)), INF)
                # a via is charged nothing: the blocks it takes on other layers may be the route's own
                vc = np.where(viab, 0.0, INF)
                lb, path_best = 0.0, None
                for k in range(min(3, len(gr_))):
                    src = gr_[k]
                    dst = np.zeros(self.nl * pb, bool)
                    for q, o in enumerate(gr_):
                        if q != k:
                            dst[o] = True
                    if dst[src].any():
                        continue
                    path, _ne = self.K.astar_v(cost, vc, src.astype(np.int64), dst, self.nl, nyb, nxb, res_b,
                                               0, nxb - 1, 0, nyb - 1, 3_000_000)
                    if path.size == 0:
                        continue
                    gsum = 0.0
                    for a_, c_ in zip(path[:-1], path[1:]):
                        la, ra = divmod(int(a_), pb)
                        lc, rc = divmod(int(c_), pb)
                        if la != lc:
                            gsum += vc[ra]
                        else:
                            diag = (ra % nxb != rc % nxb) and (ra // nxb != rc // nxb)
                            gsum += res_b * (math.sqrt(2) if diag else 1.0) * 0.5 * (cost[a_] + cost[c_])
                    if gsum > lb:
                        lb, path_best = gsum, path
                total += lb
                if path_best is not None:
                    used[path_best] += 1.0
            ratio = total / float(y.sum())
            if ratio > best["ratio"]:
                top = np.argsort(-(y * used))[:5]
                bott = []
                for k in top:
                    if used[k] <= 0:
                        continue
                    li, r = divmod(int(k), pb)
                    bott.append((sp.cu[li], round(g.x0 + ((r % nxb) + 0.5) * res_b, 2),
                                 round(g.y0 + ((r // nxb) + 0.5) * res_b, 2)))
                best.update(ratio=round(float(ratio), 4), proof=bool(ratio > 1.0), rounds=rnd + 1, bottleneck=bott)
            y = y * (1.0 + eps * used)
        return best

    def report(self):
        return dict(ref=self.win["ref"], kind=self.win["kind"], pitch=self.win["pitch"],
                    box=[round(v, 3) for v in self.win["box"]], ring=self.win["ring"], nets=len(self.nets),
                    connections=sum(self.conns.values()), grid=[self.grid.nx, self.grid.ny, round(self.grid.res, 4)],
                    iterations=self.stats, best_iteration=getattr(self, "best_iter", 0),
                    converged=getattr(self, "converged", False),
                    in_conflict=sorted(getattr(self, "best_conflict", ()))[:60],
                    open_before=sum(self.before.values()),
                    open_after=sum(getattr(self, "after", self.before).values()),
                    seconds=getattr(self, "seconds", 0.0))


def _along(geom, cut):
    """Length of the cut line inside pad copper `geom`, from the pad's own end."""
    try:
        return geom.intersection(cut).length
    except Exception:  # noqa: BLE001 - odd pad polygon: no length
        return 0.0


def solve(board, info, plan, fills, out, win, sev=None, fixed=(), deadline=None, log=print, seed=0,
          max_iter=MAX_ITER, sp=None):
    """Negotiate window `win` (from `windows`) on `board` (its project files beside it; `fills`
    its refilled zones, pcbnew_io.zone_fills()["zones"]) and write the result to `out` when it
    leaves fewer connections open on the window's nets than before, or the same with escapes
    added. `sp`: a Space of `board` to work in (changed; default a new one). Returns the report
    (Region.report, plus commit, capacity, wrote, added)."""
    t0 = time.monotonic()
    if sp is None:
        sp = Space(load(board), info, plan=plan, sev=sev or {})
    rg = Region(sp, fills, win, fixed=fixed, log=log, seed=seed)
    if len(rg.nets) > MAX_NETS:
        rep = rg.report()
        rep.update(skipped=f"{len(rg.nets)} nets, more than {MAX_NETS}", wrote=False)
        return rep
    rg.setup()
    t_setup = round(time.monotonic() - t0, 1)
    # the commit (exact checks, string pulling, stitches) keeps a share of the time
    rg.run(deadline=None if deadline is None else time.monotonic() + 0.85 * max(0.0, deadline - time.monotonic()),
           max_iter=max_iter)
    rg.deadline = deadline
    cap = [] if rg.converged else rg.capacity()
    bnd = None
    if not rg.converged and (deadline is None or time.monotonic() < deadline):
        try:
            bnd = rg.bound(deadline=deadline)
        except Exception as e:  # noqa: BLE001 - a bound is a report, never the board's cost
            bnd = dict(error=f"{type(e).__name__}: {e}")
    com = rg.commit()
    rep = rg.report()
    rep.update(setup_s=t_setup, commit=com, capacity=cap, bound=bnd)
    before, after = rep["open_before"], rep["open_after"]
    rep["wrote"] = bool(after < before or (after <= before and com["escapes"]))
    if rep["wrote"]:
        rep["added"] = rg.write(board, out)
    rep["seconds"] = round(time.monotonic() - t0, 1)
    log(f"region {win['ref']}: {'converged' if rg.converged else 'not converged'} at iteration "
        f"{rg.best_iter} of {len(rg.stats)}; {com['laid']} nets laid, {com['rejected']} rejected "
        f"({com['restored']} old copper back, {com['joined']} joined), {com['escapes']} escapes; open on its nets "
        f"{before} -> {after} ({rep['seconds']} s)")
    for c in cap:
        log(f"region {win['ref']}: {c['line']}")
    return rep


# ----------------------------------------------------------------------------- monotone repair
STEP_MARGIN = 2.0      # mm around an open connection's two ends: a repair step's window
STEP_MAX = 20.0        # mm: a step's window at most this wide (a farther connection is the router's)
STEP_NETS = 12         # nets a step moves at most (the open one and the ones in its way)
STEP_ITER = 12         # negotiation iterations of a step
STEP_STALL = 40        # steps in a row without fewer open connections before a window stops
STEP_TIME = 60.0       # s a step may take at most


def _open_parts(sp, fp, net, Wb):
    """The relevant parts of `net` (lastmile.parts), and whether two or more reach into Wb."""
    ps = [p for p in LM.parts(sp, fp, net) if LM._relevant(p)]
    inside = [p for p in ps if any(x.copper.intersects(Wb) for x in p)]
    return ps, inside


def _blockers(sp, gr, fp, net, src, others, win, fixed, widths):
    """The nets whose unlocked copper a route of `net` from `src` to `others` inside `win`
    (a box) would cross, cheapest first (lastmile's rip-up search: their copper taken out and
    priced per cell crossed). Plane nets (with fill) are never blockers: their escapes stay."""
    cand = {id(it): it for l in sp.cu for it in sp.query(l, win.bounds)
            if it.kind in ("track", "via") and it.net and it.net != net and not it.locked
            and it.uuid not in fixed and it.net not in fp and it.geom.intersects(win)}
    cand = list(cand.values())
    if not cand:
        return []
    sp.remove(cand)
    gr.soft = [(it, LM.RIP_COST) for it in cand]
    try:
        got = LM._try(gr, sp, net, src, others, win, widths)
    finally:
        gr.soft = []
    out = []
    if got is not None:
        rt, new = got
        hit = [it for it in cand if LM._conflicts(sp, it, set(new))]
        sp.remove(new)
        seen = set()
        for it in hit:
            if it.net not in seen:
                seen.add(it.net)
                out.append(it.net)
    LM._restore(sp, cand)
    return out


def _undo(sp, rg):
    sp.remove(list(rg.stubs) + list(getattr(rg, "new", [])))
    LM._restore(sp, rg.ripped)


def repair_window(board, info, plan, fills, out, win, sev=None, fixed=(), deadline=None, log=print, seed=0,
                  sp=None):
    """Monotone repair of window `win` (from `windows`), starting from the board's routing as it
    is: each open connection that ends in the window is a step. A step takes the nets whose
    unlocked copper is in the connection's way (lastmile's rip-up search; at most STEP_NETS,
    plane nets never: their escapes and dog-bones stay), rips them inside a small window
    around the connection (STEP_MARGIN beyond its two ends; the windows move with the
    connections, as TritonRoute's clips do), and re-routes them together by negotiation
    (Region with `only`), laid with exact checks. A step is kept only when its nets end with
    fewer missing connections than before, or as many (a plateau move, at most STEP_STALL in a
    row); otherwise its copper goes and the old comes back, so the window never gets worse.
    Writes `out` when a step was kept. Returns a report with every step's record."""
    t0 = time.monotonic()
    if sp is None:
        sp = Space(load(board), info, plan=plan, sev=sev or {})
    fp = LM._fill_polys(fills)
    fixed = set(fixed)
    gr = LM._SoftRouter(sp)
    Wb = box(*win["box"])
    rng = np.random.default_rng(seed)
    file_ids = {it.uuid for it in sp.existing}
    nets = sorted({it.net for it in sp.pads if it.kind == "pad" and it.net and it.geom.intersects(Wb)})
    open0 = {n: LM._open_count(sp, fp, n) for n in nets}
    steps, kept, stall, tried = [], 0, 0, {}
    t_step = []
    is_open = {n for n, v in open0.items() if v}
    while deadline is None or time.monotonic() < deadline:
        todo = []
        for n in sorted(is_open):
            ps, inside = _open_parts(sp, fp, n, Wb)
            if len(ps) > 1 and inside and tried.get(n, 0) < 3:
                todo.append(n)
        if not todo or stall >= STEP_STALL:
            break
        n = todo[int(rng.integers(len(todo)))]
        tried[n] = tried.get(n, 0) + 1
        ts = time.monotonic()
        ps, inside = _open_parts(sp, fp, n, Wb)
        small = min(inside, key=lambda p: (sum(1 for x in p if x.kind == "pad"), id(p)))
        others = [p for p in ps if p is not small]
        widths = LM.widths_of(sp, n)
        src = LM._anchors(small, max(widths) / 2 + 0.02)
        rec = dict(net=n)
        if not src:
            rec["skip"] = "no anchors"
            steps.append(rec)
            continue
        sw = LM._window(src, others, STEP_MARGIN)
        x0, y0, x1, y1 = sw.bounds
        if max(x1 - x0, y1 - y0) > STEP_MAX:
            rec["skip"] = "far"
            steps.append(rec)
            continue
        block = _blockers(sp, gr, fp, n, src, others, sw, fixed, widths)
        move = [n] + block[:STEP_NETS - 1]
        sub = dict(win, box=(x0, y0, x1, y1), ref=f"{win['ref']}:{n}")
        before = {m: LM._open_count(sp, fp, m) for m in move}
        rg = Region(sp, fills, sub, fixed=fixed, log=log, seed=int(rng.integers(1 << 30)), only=move, quiet=True)
        rg.fp = fp
        try:
            rg.setup()
            rg.run(deadline=min(deadline or 1e18, time.monotonic() + STEP_TIME), max_iter=STEP_ITER)
            rg.deadline = deadline
            com = rg.commit()
        except Exception as e:  # noqa: BLE001 - a failed step changes nothing
            _undo(sp, rg)
            rec.update(error=f"{type(e).__name__}: {e}")
            steps.append(rec)
            continue
        after = {m: LM._open_count(sp, fp, m) for m in move}
        b_, a_ = sum(before.values()), sum(after.values())
        ok = a_ < b_ or (a_ == b_ and stall < STEP_STALL)
        rec.update(moved=len(move), before=b_, after=a_, converged=rg.converged, iterations=len(rg.stats),
                   conflicts=[x["nets_in_conflict"] for x in rg.stats], laid=com["laid"],
                   kept=bool(ok), seconds=round(time.monotonic() - ts, 1))
        if a_ < b_:
            stall = 0
        else:
            stall += 1
        if not ok:
            _undo(sp, rg)
        else:
            kept += 1
            for it in rg.new + rg.stubs:
                it.locked = False      # a later step may move it; written locked (_write_diff)
            for m in move:
                if after.get(m):
                    is_open.add(m)
                else:
                    is_open.discard(m)
            if a_ < b_:
                tried.pop(n, None)
        steps.append(rec)
        t_step.append(rec["seconds"])
        log(f"region {win['ref']} step {len(steps)} {n}: {len(move)} nets moved, open {b_} -> {a_} "
            f"({'kept' if ok else 'undone'}; {'converged' if rg.converged else 'not converged'} in "
            f"{len(rg.stats)} iterations, {rec['seconds']} s)")
    open1 = {n: LM._open_count(sp, fp, n) for n in nets}
    rep = dict(ref=win["ref"], kind=win["kind"], pitch=win["pitch"], box=[round(v, 3) for v in win["box"]],
               nets=len(nets), mode="repair", steps=steps, kept=kept,
               open_before=sum(open0.values()), open_after=sum(open1.values()),
               step_seconds=dict(n=len(t_step), mean=round(float(np.mean(t_step)), 1) if t_step else 0.0,
                                 max=max(t_step) if t_step else 0.0),
               converged=sum(open1.values()) == 0)
    rep["wrote"] = rep["open_after"] < rep["open_before"]
    if rep["wrote"]:
        rep["added"] = _write_diff(sp, board, out, file_ids)
    rep["seconds"] = round(time.monotonic() - t0, 1)
    log(f"region {win['ref']}: {kept} of {len(steps)} steps kept; open on its nets {rep['open_before']} -> "
        f"{rep['open_after']} ({rep['seconds']} s)")
    return rep


def _write_diff(sp, board, out, file_ids):
    """`out` = `board` with the space's copper: the board's tracks and vias no longer in the space
    taken out, the space's new ones added (stubs unlocked, as the tracks they come from; the rest
    locked, as the last mile's). Returns the new uuids."""
    present = {it.uuid for it in sp.existing + sp.routed if it.kind in ("track", "via")}
    remove = sorted(u for u in file_ids if u and u not in present)
    tracks, vias, added = [], [], []
    for it in sp.existing + sp.routed:
        if it.kind not in ("track", "via") or it.uuid in file_ids:
            continue
        lock = it.owner != ("region", "stub")
        if it.kind == "track":
            tracks.append((it.net, next(iter(it.layers)), it.width, tuple(it.geom.coords[0]),
                           tuple(it.geom.coords[-1]), it.uuid, lock))
        else:
            vias.append((it.net, it.geom.x, it.geom.y, it.width, it.drill, it.uuid, lock))
        added.append(it.uuid)
    W.edit(board, out, remove=remove)
    if tracks or vias:
        W.append_items(out, out, tracks=tracks, vias=vias)
    return added
