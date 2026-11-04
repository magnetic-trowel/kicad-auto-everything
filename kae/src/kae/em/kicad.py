# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""A KiCad board's copper in a window, as a Mesh: every net's tracks, arcs, pads, vias and
refilled zones on every copper layer, at the stackup's own heights.

All nets are meshed, not only the ones a question names: other nets' copper carries the eddy
currents that partly screen a loop, and a power plane tied to ground by capacitors carries
return current (pass those capacitors as parts). Pads and via landings are equipotential
terminals; through-hole pads and vias are barrels joining their net's copper on each layer.
"""
from __future__ import annotations

import math

import numpy as np

from .mesh import Layer, Mesh


def layers_of(stackup, nsub=2):
    """Layers top to bottom with z measured up from the bottom of B.Cu (mm)."""
    cu, tcu, gaps = list(stackup.copper), list(stackup.cu_thickness), list(stackup.gaps)
    z, out = 0.0, []
    for k in range(len(cu) - 1, -1, -1):          # bottom up
        out.append(Layer(cu[k], z, tcu[k], nsub))
        z += tcu[k] + (gaps[k - 1] if k > 0 else 0.0)
    return out[::-1]


def _arc_points(t, n=16):
    (x0, y0), (xm, ym), (x1, y1) = t.start, t.mid, t.end
    ax, ay, bx, by = x0 - xm, y0 - ym, x1 - xm, y1 - ym
    d = 2 * (ax * by - ay * bx)
    if abs(d) < 1e-12:
        return [t.start, t.end]
    ux = (by * (ax * ax + ay * ay) - ay * (bx * bx + by * by)) / d + xm
    uy = (ax * (bx * bx + by * by) - bx * (ax * ax + ay * ay)) / d + ym
    a0, am, a1 = (math.atan2(p[1] - uy, p[0] - ux) for p in (t.start, t.mid, t.end))

    def norm(a):
        return (a - a0) % (2 * math.pi)
    sweep = norm(a1)
    if norm(am) > sweep:
        sweep -= 2 * math.pi
    r = math.hypot(x0 - ux, y0 - uy)
    return [(ux + r * math.cos(a0 + sweep * k / n), uy + r * math.sin(a0 + sweep * k / n)) for k in range(n + 1)]


class BoardMesh:
    """Mesh of board `path` (or a loaded board b) in window (x0, y0, x1, y1), mm."""

    def __init__(self, path, window, pitch, nsub=2, b=None, fills=None, layers=None, nets=None):
        from shapely.geometry import LineString, Point, box
        from shapely.ops import unary_union

        from kae.board import transform
        from kae.board.kicad_file import load
        from kae.place.legalize import pad_shape
        if b is None:
            b = load(path)
        if fills is None:
            from kae.route.critical_recheck import fills_of
            fills = fills_of(path)
        self.fills = fills                  # {net: {layer: [Polygon]}}: KiCad's refill of the board as it is
        self.b, self.transform, self.pad_shape = b, transform, pad_shape
        lays = layers_of(b.stackup, nsub)
        if layers:
            lays = [l for l in lays if l.name in layers]
        self.li = {l.name: k for k, l in enumerate(lays)}
        win = box(*window)
        self.win = win
        m = self.m = Mesh.over(*window, pitch, lays)
        geo = {}

        def add(net, layer, g):
            if nets is not None and net not in nets:
                return
            if net and layer in self.li and g is not None and g.intersects(win):
                geo.setdefault((net, layer), []).append(g)
        for net, per in fills.items():
            for layer, pgs in per.items():
                for pg in pgs:
                    add(net, layer, pg)
        thin = []
        for t in b.tracks:
            pts = _arc_points(t) if getattr(t, "mid", None) else [t.start, t.end]
            if t.width < 3 * pitch:
                if t.net and t.layer in self.li and LineString(pts).intersects(win):
                    thin.append((t, pts))
                continue
            add(t.net, t.layer, LineString(pts).buffer(t.width / 2, quad_segs=8))
        self.pads = {}
        self.fp_of = fp_of = {}                 # pad token -> its footprint (a pad number may hold a dot: '3.3V')
        for f in b.footprints:
            for p in f.pads:
                cus = [l for l in p.layers if l.endswith(".Cu")]
                for layer in cus:
                    g = transform.place_geom(pad_shape(p, layer), f.x, f.y, f.rot, f.side)
                    add(p.net, layer, g)
                    self.pads.setdefault(f"{f.ref}.{p.number}", []).append((layer, g, p))
                    fp_of[f"{f.ref}.{p.number}"] = f
        order = [l.name for l in layers_of(b.stackup, nsub)]

        def span(ls):
            """A via's copper layers: every layer from its first to its last in stackup order (the file
            lists only the two ends of a through or blind via)."""
            ks = [order.index(l) for l in ls if l in order]
            return order[min(ks):max(ks) + 1] if ks else []
        self.span = span
        for v in b.vias:
            for layer in span(v.layers):
                add(v.net, layer, Point(v.x, v.y).buffer(v.size / 2, quad_segs=8))
        for (net, layer), gs in geo.items():
            m.paint_connected(self.li[layer], net, unary_union(gs).intersection(win))
        for t, pts in thin:
            m.paint_line(self.li[t.layer], t.net, pts, t.width)
        # a pad smaller than a cell still owns the cell under its centre
        for f in b.footprints:
            for p in f.pads:
                if not p.net:
                    continue
                x, y = transform.pad_xy(f, p)
                j, i = m.cell(x, y)
                if not (0 <= j < m.ny and 0 <= i < m.nx):
                    continue
                for layer in p.layers:
                    if layer in self.li:
                        m.lab[self.li[layer], j, i] = m.net_id(p.net)
        self.n_bridges = m.bridge_gaps()        # fine-pitch neighbours' shared cells (Mesh.paint_line)
        for v in b.vias:
            if win.contains(Point(v.x, v.y)) and (nets is None or v.net in nets):
                ls = [self.li[l] for l in span(v.layers) if l in self.li]
                if len(ls) > 1:
                    m.via(v.x, v.y, ls, v.net, drill=v.drill)
        for tok, lst in self.pads.items():
            p = lst[0][2]
            if p.drill and p.net and len(lst) > 1 and (nets is None or p.net in nets):
                x, y = transform.pad_xy(fp_of[tok], p)
                if win.contains(Point(x, y)):
                    m.via(x, y, [self.li[l] for l, _, _ in lst if l in self.li], p.net, drill=p.drill)

    def reliefs(self, max_gap=2.0, step=0.05):
        """Thermal reliefs between pads and their pours, read from KiCad's refill (which has applied every zone's
        and pad's connection setting): around a pad its own net's fill either closes in (a solid connection) or
        leaves a gap that only spokes cross. Per relieved pad and layer: {token, layer (index), gap_mm, spokes:
        [(width_mm, (x, y) inner end, (x, y) outer end)]}. A pad without its own net's fill nearby, or one the fill
        reaches all round, is not listed. Cached."""
        if getattr(self, "_reliefs", None) is not None:
            return self._reliefs
        from shapely.ops import unary_union
        out = []
        fills = {}
        for net, per in (self.fills or {}).items():
            for layer, pgs in per.items():
                if layer in self.li and pgs:
                    fills[(net, layer)] = unary_union(pgs)
        for tok, lst in self.pads.items():
            for layer, g, p in lst:
                f = fills.get((p.net, layer))
                if f is None or g is None or g.is_empty or not f.intersects(g.buffer(max_gap)):
                    continue
                # the gap: the first distance from the pad at which the fill covers most of a thin ring
                gap = None
                d = step
                while d <= max_gap:
                    ring = g.buffer(d + step).difference(g.buffer(d))
                    if ring.area > 0 and f.intersection(ring).area / ring.area > 0.8:
                        gap = d
                        break
                    d += step
                if gap is None or gap <= step:
                    continue                       # no pour around it, or one that reaches it all round: solid
                band = g.buffer(gap).difference(g.buffer(step / 2))
                sp = f.intersection(band)
                pieces = [q for q in getattr(sp, "geoms", [sp]) if q.area > 1e-4]
                spokes = []
                for q in pieces:
                    w = q.area / max(gap - step / 2, 1e-3)
                    # its ends, each in a cell of copper: just inside the pad's edge, and in the pour beyond the gap
                    # (a point on the edge itself falls in a gap cell, which carries no copper)
                    core = g.buffer(-0.6 * self.m.pitch)
                    core = core if not core.is_empty and hasattr(core, "exterior") else None
                    inner = core.exterior.interpolate(core.exterior.project(q.centroid)) if core is not None else g.centroid
                    far = g.buffer(gap + self.m.pitch).exterior
                    outer = far.interpolate(far.project(q.centroid))
                    spokes.append((round(w, 4), (inner.x, inner.y), (outer.x, outer.y)))
                out.append(dict(token=tok, layer=self.li[layer], layer_name=layer, gap_mm=round(gap, 3), spokes=spokes,
                                ring=g.buffer(gap).difference(g)))
        self._reliefs = out
        return out

    def pad(self, token):
        """Terminal for pad REF.NUM: its copper on every layer it has (one equipotential)."""
        if token in self.m.terminals:
            return token
        lst = self.pads.get(token)
        if not lst:
            raise KeyError(f"no pad {token}")
        f = self.fp_of[token]
        for layer, g, p in lst:
            if layer in self.li:
                try:
                    self.m.terminal(token, self.li[layer], geom=g, net=p.net)
                except ValueError:
                    x, y = self.transform.pad_xy(f, p)
                    try:
                        self.m.terminal(token, self.li[layer], xy=(x, y), net=p.net)
                    except ValueError:
                        pass
        if token not in self.m.terminals:
            raise ValueError(f"pad {token} has no copper cells in the window (pitch too coarse?)")
        return token

    def short(self, a, b):
        self.m.part(self.pad(a), self.pad(b))

    def part(self, a, b, R=0.0, L=0.0, C=None, name=""):
        self.m.part(self.pad(a), self.pad(b), R, L, C, name)

    def port(self, name, plus, minus):
        self.m.port(name, self.pad(plus), self.pad(minus))
