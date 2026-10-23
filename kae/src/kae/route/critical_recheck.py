# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Routed physics of a finished board, the recheck, and the re-tweak loop.

`board_physics(board)` evaluates every module of the brief on a board's real copper,
whoever routed it (us, the bridge, a human), with the module stage's models
(critical_physics.Loop over kae.physics.fastloop):

- each net's copper is a graph: pads, track end points (T-junctions split the track they
  land on), vias, and the refilled zone regions (kicad-cli's fill, pcbnew_io.zone_fills),
  whose contacts are joined through the pour;
- a hop between two terminals follows the path of least L'(w)-weighted length (the HF
  current's path), as strips, vias and pour pieces; a part's internal path is its body;
- each strip's reference plane is the nearest layer whose refilled copper (any net: every
  plane images the current) lies under it, so tracks of other nets that cut a plane, or
  antipads that perforate it, raise the loop exactly where they are; pieces on the ground
  plane itself are its image current and drop out.

`recheck(board, brief, stage)` compares each module's utilization with its value at the
module stage (`stage`: {module id: u}); a module whose u grew by more than `rise`
(default 15 %) or crossed its budget is returned for a second tweak.

`retweak_loop(...)` runs the second tweak on a board routed by the bridge: the flagged
module's surroundings are cleared of other nets' copper on its reference plane and around
its own copper, a guard pour (`kae-crit:`, a hard obstacle for other nets in the bridge)
covers the plane under the module, the module keeps its own copper (optimal at the module
stage; what worsened it is its neighbours' copper), and the bridge routes what was ripped
up; rounds repeat until nothing is flagged or `rounds` is reached, each
round judged by KiCad's DRC and kept only if it is no worse.
"""
from __future__ import annotations

import heapq
import math
import time
from pathlib import Path

import numpy as np
import shapely
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union

from kae.board import transform
from kae.board.kicad_file import load
from kae.physics.boardview import body_z
from kae.physics.kernels import lprime_hj

from .critical_physics import INF, Loop, r_track, r_via, trace_capacitance_pf

GND_HINT = ("GND", "VSS", "GROUND", "EARTH")


# ----------------------------------------------------------------------------- geometry
def pad_poly(fp, pad):
    """The pad's copper in the board frame (rounded rectangles as rectangles)."""
    from kae.place.legalize import pad_shape
    return transform.place_geom(pad_shape(pad), fp.x, fp.y, fp.rot, fp.side)


def _z_of(board):
    st = board.stackup
    cu = list(st.copper)
    z = [0.0]
    for k in range(1, len(cu)):
        z.append(z[-1] + st.cu_thickness[k - 1] / 2 + st.gaps[k - 1] + st.cu_thickness[k] / 2)
    return cu, dict(zip(cu, z))


# ----------------------------------------------------------------------------- the routed board
class RoutedBoard:
    """A finished board's copper per net, with refilled zones (see the module docstring)."""

    def __init__(self, board, fills=None, brief=None):
        self.board = board if not isinstance(board, (str, Path)) else load(board)
        self.cu, self.z = _z_of(self.board)
        self.fp = {f.uuid: f for f in self.board.footprints}
        self.fills = fills          # {net: {layer: [Polygon]}} or None (zone outlines)
        if brief is None:
            from kae.circuit.brief import build
            brief = build(self.board)
        self.brief = brief
        nets = brief.get("nets") or {}
        self.gnd = {n for n, r in nets.items() if (r or {}).get("role") == "ground"}
        self._graphs = {}
        self._pads = {}
        self._planes = None
        self.thickness = self.z[self.cu[-1]] if self.cu else 1.6
        self.er = (self.board.stackup.er or [4.3])[0] if self.board.stackup else 4.3

    # ---- pads
    def pads(self, net):
        if net not in self._pads:
            out = []
            for f in self.board.footprints:
                for p in f.pads:
                    if p.net == net:
                        out.append((f, p, pad_poly(f, p)))
            self._pads[net] = out
        return self._pads[net]

    def terminal(self, fp_uuid, numbers):
        f = self.fp.get(fp_uuid)
        if f is None:
            return None
        if isinstance(numbers, (str, int)):
            numbers = [numbers]
        want = {str(n) for n in numbers}
        ps = [p for p in f.pads if p.number in want]
        if not ps:
            return None
        geoms = [pad_poly(f, p) for p in ps]
        g = unary_union(geoms)
        xs = [transform.pad_xy(f, p) for p in ps]
        x = sum(a for a, _ in xs) / len(xs)
        y = sum(b for _, b in xs) / len(xs)
        layers = sorted({l for p in ps for l in p.layers if l in self.cu} or {self.cu[0] if f.side == "F" else self.cu[-1]},
                        key=self.cu.index)
        from .critical_space import _dims
        w, ln = _dims(geoms[0])
        return dict(fp=fp_uuid, pad=",".join(sorted(want)), net=ps[0].net, x=x, y=y, geom=g, layers=layers, width=w,
                    numbers=[p.number for p in ps])

    # ---- planes (any net) for image heights
    def planes(self):
        """{layer: union of copper fills (any net)}; zone outlines when no fills are known."""
        if self._planes is None:
            per = {}
            if self.fills is not None:
                for net, byl in self.fills.items():
                    for l, polys in byl.items():
                        per.setdefault(l, []).extend(polys)
            else:
                for z in self.board.zones:
                    if not z.net or z.outline is None or z.outline.is_empty:
                        continue
                    for l in z.layers:
                        per.setdefault(l, []).append(z.outline)
            self._planes = {l: unary_union(v) for l, v in per.items() if v}
            for g in self._planes.values():
                shapely.prepare(g)
        return self._planes

    def h_at(self, layer, x, y, ref=None):
        """Height above the nearest plane layer whose copper lies under (x, y) (any net),
        or above `ref` (a layer) when given and covered; inf without."""
        p = Point(x, y)
        zl = self.z[layer]
        best = INF
        for l, g in self.planes().items():
            if l == layer:
                continue
            d = abs(self.z[l] - zl)
            if d < best and g.contains(p):
                best = d
        return best

    def strip_h(self, layer, a, b, n=5):
        """Median plane height under a strip (sampled), inf when mostly uncovered."""
        hs = []
        for k in range(n):
            t = (k + 0.5) / n
            hs.append(self.h_at(layer, a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])))
        hs.sort()
        return hs[len(hs) // 2]

    # ---- graphs
    def graph(self, net):
        g = self._graphs.get(net)
        if g is None:
            g = NetGraph(self, net)
            self._graphs[net] = g
        return g


# ----------------------------------------------------------------------------- net graphs
def _lp(w):
    """L' weight of a strip of width w at a nominal 0.5 mm height (relative path cost)."""
    return lprime_hj(max(w, 0.05), 0.5)


class NetGraph:
    """Conductors of one net as a weighted graph (see the module docstring)."""

    def __init__(self, rb, net):
        self.rb, self.net = rb, net
        self.nodes = []            # (kind, layers, x, y)
        self.adj = {}
        self.key = {}
        b = rb.board
        cu = rb.cu
        # pads
        self.pad_node = {}
        pads = rb.pads(net)
        for f, p, geom in pads:
            x, y = transform.pad_xy(f, p)
            layers = tuple(l for l in p.layers if l in cu) or ((cu[0],) if f.side == "F" else (cu[-1],))
            k = self._node("pad", layers, x, y)
            self.pad_node[(f.uuid, p.number)] = self.pad_node.get((f.uuid, p.number), []) + [k]
            self.nodes[k] = ("pad", layers, x, y, geom)
        # vias
        vias = []
        for v in b.vias:
            if v.net != net:
                continue
            k = self._node("via", tuple(cu), v.x, v.y)
            vias.append((k, v))
        # track keypoints and segments
        segs = []
        for t in b.tracks:
            if t.net != net or t.layer not in cu:
                continue
            pts = [t.start, t.end] if t.mid is None else [t.start, t.mid, t.end]
            for a, c in zip(pts[:-1], pts[1:]):
                ka = self._kp(t.layer, a, t.width)
                kc = self._kp(t.layer, c, t.width)
                segs.append((ka, kc, t.layer, a, c, t.width))
                self._edge(ka, kc, math.dist(a, c) * _lp(t.width), ("strip", t.layer, a, c, t.width))
        # attachments of keypoints: pads, vias, T-junctions
        kps = [(k, n) for k, n in enumerate(self.nodes) if n[0] == "kp"]
        for k, n in kps:
            _, (l,), x, y, w = n
            p = Point(x, y)
            for (fu, num), ks in self.pad_node.items():
                for kk in ks:
                    _, layers, px, py, geom = self.nodes[kk]
                    if l in layers and geom.distance(p) <= 1e-3:
                        self._edge(k, kk, math.dist((x, y), (px, py)) * _lp(w), ("strip", l, (px, py), (x, y), w))
            for kv, v in vias:
                if math.dist((x, y), (v.x, v.y)) <= v.size / 2 + 1e-3:
                    self._edge(k, kv, math.dist((x, y), (v.x, v.y)) * _lp(w), ("strip", l, (v.x, v.y), (x, y), w))
        for k, n in kps:
            _, (l,), x, y, w = n
            for ka, kc, sl, a, c, sw in segs:
                if sl != l or ka == k or kc == k:
                    continue
                d, q, t = _proj(a, c, (x, y))
                if d <= sw / 2 + 1e-3 and 1e-6 < t < 1 - 1e-6:
                    kq = self._kp(l, q, sw)
                    self._edge(kq, ka, math.dist(q, a) * _lp(sw), ("strip", l, q, a, sw))
                    self._edge(kq, kc, math.dist(q, c) * _lp(sw), ("strip", l, q, c, sw))
                    self._edge(k, kq, max(d, 1e-6) * _lp(w), ("strip", l, q, (x, y), w))
        # vias inside pads
        for kv, v in vias:
            pv = Point(v.x, v.y)
            for (fu, num), ks in self.pad_node.items():
                for kk in ks:
                    _, layers, px, py, geom = self.nodes[kk]
                    if geom.distance(pv) <= v.size / 2:
                        l = layers[0]
                        self._edge(kv, kk, math.dist((v.x, v.y), (px, py)) * _lp(0.5), ("strip", l, (px, py), (v.x, v.y), 0.5))
        # zones: contacts in each filled region, joined through the pour
        fills = (rb.fills or {}).get(net) if rb.fills is not None else None
        regions = []
        if fills is not None:
            for l, polys in fills.items():
                for pg in polys:
                    regions.append((l, pg))
        else:
            for z in b.zones:
                if z.net == net and z.outline is not None and not z.outline.is_empty:
                    for l in z.layers:
                        if l in cu:
                            regions.append((l, z.outline))
        for l, pg in regions:
            contacts = []
            for k, n in enumerate(self.nodes):
                kind, layers = n[0], n[1]
                if l not in layers:
                    continue
                if pg.contains(Point(n[2], n[3])) or (kind == "pad" and pg.intersects(n[4])):
                    contacts.append(k)
            if len(contacts) < 2:
                continue
            P = np.array([[self.nodes[k][2], self.nodes[k][3]] for k in contacts])
            nn = min(8, len(contacts) - 1)
            for i, k in enumerate(contacts):
                d = np.hypot(P[:, 0] - P[i, 0], P[:, 1] - P[i, 1])
                for j in np.argsort(d)[1:nn + 1]:
                    kk = contacts[int(j)]
                    a, c = (P[i, 0], P[i, 1]), (P[int(j), 0], P[int(j), 1])
                    wz = 2.0
                    self._edge(k, kk, float(d[j]) * _lp(wz), ("pour", l, a, c, wz))
        # via barrels: a via node is one node on all layers (its barrel is a vertical piece
        # in the loop model, added between the strips that meet it)

    def _node(self, kind, layers, x, y):
        self.nodes.append((kind, layers, x, y, None))
        return len(self.nodes) - 1

    def _kp(self, layer, p, w=0.0):
        key = (layer, round(p[0], 4), round(p[1], 4))
        k = self.key.get(key)
        if k is None:
            self.nodes.append(("kp", (layer,), float(p[0]), float(p[1]), w))
            k = len(self.nodes) - 1
            self.key[key] = k
        else:
            kind, ly, x, y, w0 = self.nodes[k]
            self.nodes[k] = (kind, ly, x, y, max(w0, w))
        return k

    def _edge(self, a, b, w, piece):
        if a == b:
            return
        self.adj.setdefault(a, []).append((b, w, piece))
        self.adj.setdefault(b, []).append((a, w, piece))

    def path(self, srcs, dsts):
        """Least-cost path from any node in srcs to any in dsts: [(piece, from node, to node)]
        or None."""
        dset = set(dsts)
        dist = {}
        prev = {}
        hp = []
        for s in srcs:
            dist[s] = 0.0
            heapq.heappush(hp, (0.0, s))
        goal = None
        while hp:
            d, u = heapq.heappop(hp)
            if d > dist.get(u, INF):
                continue
            if u in dset:
                goal = u
                break
            for v, w, piece in self.adj.get(u, ()):
                nd = d + w
                if nd < dist.get(v, INF):
                    dist[v] = nd
                    prev[v] = (u, piece)
                    heapq.heappush(hp, (nd, v))
        if goal is None:
            return None
        out = []
        k = goal
        while k in prev:
            u, piece = prev[k]
            out.append((piece, u, k))
            k = u
        return out[::-1]


def _proj(a, c, p):
    dx, dy = c[0] - a[0], c[1] - a[1]
    l2 = dx * dx + dy * dy
    if l2 < 1e-18:
        return math.dist(a, p), a, 0.0
    t = max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / l2))
    q = (a[0] + t * dx, a[1] + t * dy)
    return math.dist(q, p), q, t


# ----------------------------------------------------------------------------- loops on real copper
def _orient(piece, frm_xy):
    kind, l, a, c, w = piece
    if math.dist(a, frm_xy) <= math.dist(c, frm_xy):
        return kind, l, a, c, w
    return kind, l, c, a, w


def hop_pieces(rb, net, ta, tb):
    """The path of a hop's current from terminal ta to tb on net's copper: a list of
    ('strip'|'pour', layer, a, b, w) pieces and ('via', layer_from, layer_to, x, y)
    transitions, or None when the terminals are not connected."""
    g = rb.graph(net)
    srcs = [k for num in ta["numbers"] for k in g.pad_node.get((ta["fp"], num), [])]
    dsts = [k for num in tb["numbers"] for k in g.pad_node.get((tb["fp"], num), [])]
    if not srcs or not dsts:
        return None
    if set(srcs) & set(dsts):
        return []
    p = g.path(srcs, dsts)
    if p is None:
        return None
    out = []
    cur = (ta["x"], ta["y"])
    cur_l = None
    for piece, u, v in p:
        kind, l, a, c, w = _orient(piece, cur)
        if cur_l is not None and l != cur_l:
            out.append(("via", cur_l, l, a[0], a[1]))
        out.append((kind, l, a, c, w))
        cur = c
        cur_l = l
    return out


class LoopBuilder:
    """Builds critical_physics.Loop from terminals and hop paths on a RoutedBoard, with each
    strip's own plane height (see the module docstring)."""

    def __init__(self, rb, ref_layer, gnd_layer=None):
        self.rb = rb
        self.ref = ref_layer          # the cell's own layer
        self.gl = gnd_layer           # the ground plane's layer (pieces on it are the image)
        self.lp = Loop()
        self.open = 0

    def h(self, layer, a, b):
        return self.rb.strip_h(layer, a, b)

    def hz(self, layer):
        """Height of a layer above the ground plane layer (vias), inf without one."""
        if self.gl is None:
            return INF
        return abs(self.rb.z[layer] - self.rb.z[self.gl])

    def hop(self, pieces, ta, tb, el="A"):
        if pieces is None:
            self.open += 1
            h = self.rb.strip_h(ta["layers"][0], (ta["x"], ta["y"]), (tb["x"], tb["y"]))
            self.lp.strip((ta["x"], ta["y"]), (tb["x"], tb["y"]), max(min(ta["width"], tb["width"]), 0.25), h, el)
            return
        for pc in pieces:
            if pc[0] == "via":
                _, la, lb, x, y = pc
                za, zb = self.hz(la), self.hz(lb)
                if za != INF and zb != INF:
                    self.lp.vert(x, y, za, zb, 0.15, el)
                continue
            kind, l, a, c, w = pc
            if l == self.gl:
                continue                      # on the ground plane: the image current
            h = self.h(l, a, c)
            self.lp.strip(a, c, w, h, el)

    def body(self, ta, tb, zb, w):
        h = self.rb.strip_h(ta["layers"][0], (ta["x"], ta["y"]), (tb["x"], tb["y"]))
        self.lp.body((ta["x"], ta["y"]), (tb["x"], tb["y"]), h, zb, w)


def _gnd_layer(rb, layer, x, y, outlines=False):
    """The nearest layer below `layer` with ground fill under (x, y) (with outlines: with a
    ground zone outline there, filled or not)."""
    best = None
    p = Point(x, y)
    for g in rb.gnd:
        if rb.fills is not None and not outlines:
            byl = rb.fills.get(g) or {}
            items = [(l, unary_union(v)) for l, v in byl.items() if v]
        else:
            items = [(l, z.outline) for z in rb.board.zones if z.net == g and not (z.name or "").startswith("kae-crit:")
                     for l in z.layers]
        for l, geom in items:
            if l == layer or geom is None:
                continue
            d = abs(rb.z[l] - rb.z[layer])
            if geom.contains(p) and (best is None or d < best[0]):
                best = (d, l)
    return best[1] if best else None


def plane_cover(rb, layer, region):
    """Share of `region` covered by ground fill on `layer`, out of the part of it inside the
    ground zones' outlines there (so a planned cut-out does not count): 1.0 for a whole
    plane, less where other nets' tracks, vias and their clearances perforate it."""
    if layer is None or region is None or region.is_empty or rb.fills is None:
        return None
    outl = [z.outline for z in rb.board.zones if z.net in rb.gnd and layer in z.layers and z.outline is not None
            and not (z.name or "").startswith("kae-crit:")]
    if not outl:
        return None
    den = region.intersection(unary_union(outl))
    if den.area < 1e-6:
        return None
    fill = [g for n in rb.gnd for g in (rb.fills.get(n) or {}).get(layer, [])]
    if not fill:
        return 0.0
    return min(1.0, den.intersection(unary_union(fill)).area / den.area)


def cell_value(rb, s):
    """Hot-loop inductance (nH) of a commutation cell on the board's copper."""
    T = [rb.terminal(m[0], m[1]) for m in s.get("loop") or []]
    if len(T) < 3 or any(t is None for t in T):
        return None, dict(note="terminals not found")
    n = len(T)
    side = rb.fp[T[0]["fp"]].side
    layer = rb.cu[0] if side == "F" else rb.cu[-1]
    cx = sum(t["x"] for t in T) / n
    cy = sum(t["y"] for t in T) / n
    # the ground plane layer: filled under the loop, else the one whose zone should be there
    # (a cut plane is still the loop's reference, and its cover shows the cut)
    gl = _gnd_layer(rb, layer, cx, cy) or _gnd_layer(rb, layer, cx, cy, outlines=True)
    lb = LoopBuilder(rb, layer, gl)
    for k in range(n):
        ta, tb = T[k], T[(k + 1) % n]
        if ta["fp"] == tb["fp"]:
            f = rb.fp[ta["fp"]]
            w = 0.3 if len(f.pads) > 4 else max(min(ta["width"], tb["width"]), 0.2)
            lb.body(ta, tb, body_z(f.lib_id, f.value), w)
            continue
        lb.hop(hop_pieces(rb, ta["net"], ta, tb), ta, tb)
    pts = [(t["x"], t["y"]) for t in T] + [p for H, _ in lb.lp.el.values() for h in H for p in (h[:2], h[2:4])]
    region = shapely.MultiPoint(pts).convex_hull.buffer(0.5)
    cover = plane_cover(rb, gl, region)
    return lb.lp.value(), dict(open_hops=lb.open, gnd_layer=gl,
                               plane_cover=round(cover, 4) if cover is not None else None)


def decap_values(rb, s):
    """Worst per-pin decoupling-loop inductance (nH) of a decap structure."""
    from .critical_modules import GND_RE
    ic = s.get("ic")
    rail = s.get("rail")
    gnet = s.get("ground")
    caps = s.get("hf_caps") or s.get("caps") or []
    pins = [str(p) for p in s.get("power_pins") or []]
    pc = s.get("pin_caps") or {}
    pairs = [(str(p), c) for p, cs in pc.items() for c in cs if c in caps or c in (s.get("caps") or [])]
    for c in caps:
        if any(c == x for _, x in pairs) or not pins:
            continue
        pairs.append((pins[0], c))
    vals = {}
    opens = 0
    fic = rb.fp.get(ic)
    if fic is None:
        return None, dict(note="ic not found")
    for pin, cap in pairs:
        fc = rb.fp.get(cap)
        if fc is None:
            continue
        tp = rb.terminal(ic, [pin])
        rp = next((p.number for p in fc.pads if p.net == rail), None)
        gp = next((p.number for p in fc.pads if p.net and p.net != rail and (p.net == gnet or p.net in rb.gnd
                                                                              or GND_RE.search(p.net))), None)
        if tp is None or rp is None or gp is None:
            continue
        tr, tg = rb.terminal(cap, [rp]), rb.terminal(cap, [gp])
        gpins = [str(x) for x in s.get("ground_pins") or []] or \
            [p.number for p in fic.pads if p.net and (p.net == tg["net"])]
        tG = None
        for g in gpins:
            t = rb.terminal(ic, [g])
            if t is not None and (tG is None or math.dist((t["x"], t["y"]), (tp["x"], tp["y"])) <
                                  math.dist((tG["x"], tG["y"]), (tp["x"], tp["y"]))):
                tG = t
        side = fc.side
        layer = rb.cu[0] if side == "F" else rb.cu[-1]
        gl = _gnd_layer(rb, layer, tg["x"], tg["y"])
        lb = LoopBuilder(rb, layer, gl)
        lb.hop(hop_pieces(rb, rail, tp, tr), tp, tr)
        lb.body(tr, tg, body_z(fc.lib_id, fc.value), max(min(tr["width"], tg["width"]), 0.2))
        if tG is not None:
            lb.hop(hop_pieces(rb, tg["net"], tg, tG), tg, tG)
            lb.body(tG, tp, body_z(fic.lib_id, fic.value), 0.3 if len(fic.pads) > 4 else 0.5)
        else:
            # no return pin (inductor, diode, connector): the return closes under the
            # power pin, straight back over the plane
            h = rb.strip_h(layer, (tg["x"], tg["y"]), (tp["x"], tp["y"]))
            lb.lp.strip((tg["x"], tg["y"]), (tp["x"], tp["y"]), 0.5, h)
        opens += lb.open
        v = lb.lp.value()
        vals.setdefault(pin, []).append(v)
    per_pin = {}
    for p, vs in vals.items():
        vs = [x for x in vs if x > 1e-9 and math.isfinite(x)]
        if vs:
            per_pin[p] = 1.0 / sum(1.0 / x for x in vs)        # parallel capacitors
    if not per_pin:
        return None, dict(note="no pairs" if not vals else "degenerate loops (all copper on the plane layer)")
    return max(per_pin.values()), dict(per_pin={p: round(v, 3) for p, v in per_pin.items()}, open_hops=opens)


def crystal_value(rb, s):
    """Pulling (ppm) of the trace capacitance of the crystal nets' copper."""
    from kae.physics import priors as PR
    _, S = PR.crystal_budget(s.get("f_Hz"))
    nets = list(s.get("nets") or [])
    C = 0.0
    for t in rb.board.tracks:
        if t.net in nets:
            h = rb.strip_h(t.layer, t.start, t.end, n=3)
            C += trace_capacitance_pf(math.dist(t.start, t.end), t.width, h if h != INF else rb.thickness, rb.er)
    return S * C, dict(c_trace_pf=round(C, 4))


def chain_value(rb, s):
    """Surge-path L (nH): connector pin to the protector along the copper, plus its via."""
    ch = [x for x in (s.get("chain") or []) if x]
    prot = set(s.get("protection") or [])
    if len(ch) < 2 or not prot:
        return None, {}
    T = [rb.terminal(m[0], m[1]) for m in ch]
    if any(t is None for t in T):
        return None, {}
    import kae.physics.fastloop as FL
    total = 0.0
    length = 0.0
    for k in range(len(T) - 1):
        ta, tb = T[k], T[k + 1]
        if ta["fp"] == tb["fp"]:
            continue
        pcs = hop_pieces(rb, ta["net"], ta, tb)
        if pcs is None:
            pcs = [("strip", ta["layers"][0], (ta["x"], ta["y"]), (tb["x"], tb["y"]), 0.25)]
        for pc in pcs:
            if pc[0] == "via":
                continue
            _, l, a, c, w = pc
            h = rb.strip_h(l, a, c, n=3)
            hh = h if h != INF else rb.thickness
            total += lprime_hj(w, hh) * math.dist(a, c)
            length += math.dist(a, c)
        if tb["fp"] in prot:
            break
    hh = rb.thickness
    lv = FL.m_self(hh, 0.15) + FL._collinear(hh, hh, 0.0)
    return total + lv, dict(surge_path_mm=round(length, 3))


VALUES = {"cell": cell_value, "decap": decap_values, "crystal": crystal_value, "chain": chain_value}


# ----------------------------------------------------------------------------- rails (DC)
def rail_drops(rb, brief):
    """Per routed rail: the copper resistance (mOhm) of the least-resistance path from the
    source to each load (tracks R_s l / w, vias, pours as 2 mm strips) and the drop at the
    E5 design current; the DC passport (tools/research/physics/suite_passports.py) is the
    exact check."""
    out = {}
    nets = brief.get("nets") or {}
    for net, r in nets.items():
        if (r or {}).get("role") != "rail":
            continue
        src = (r.get("source") or {}).get("part")
        if src not in rb.fp:
            continue
        g = rb.graph(net)
        ks = [k for (fu, num), kk in g.pad_node.items() if fu == src for k in kk]
        if not ks:
            continue
        loads = {fu for (fu, num) in g.pad_node if fu != src}
        res = {}
        for u in loads:
            kd = [k for (fu, num), kk in g.pad_node.items() if fu == u for k in kk]
            p = g.path(ks, kd)
            if p is None:
                res[rb.fp[u].ref] = None
                continue
            R = 0.0
            last = None
            for piece, a, b in p:
                kind, l, pa, pb, w = piece
                if last is not None and l != last:
                    R += r_via(rb.thickness, 0.3)
                R += r_track(math.dist(pa, pb), w)
                last = l
            res[rb.fp[u].ref] = round(1e3 * R, 3)
        out[net] = res
    return out


# ----------------------------------------------------------------------------- board physics
def board_physics(board, brief=None, fills="kicad", kinds=("cell", "decap", "crystal", "chain"), terms=None):
    """Every module's routed value, allocation and u on a finished board (see the module
    docstring). fills: 'kicad' (refill with KiCad), None (zone outlines) or a dict."""
    b = board if not isinstance(board, (str, Path)) else load(board)
    if brief is None:
        from kae.circuit.brief import build
        brief = build(b)
    fl = None
    if fills == "kicad":
        fl = fills_of(b.path)
    elif isinstance(fills, dict):
        fl = fills
    rb = RoutedBoard(b, fills=fl, brief=brief)
    from .critical_modules import modules_from_brief
    out = {}
    actx = _AllocCtx(rb, brief, terms)
    for m in modules_from_brief(brief, kinds):
        fn = VALUES.get(m.kind)
        try:
            v, extra = fn(rb, m.spec)
        except Exception as e:  # noqa: BLE001
            out[m.id] = dict(kind=m.kind, error=f"{type(e).__name__}: {e}")
            continue
        if v is None:
            out[m.id] = dict(kind=m.kind, **extra)
            continue
        from .critical_modules import allocation
        a = allocation(actx, m)
        out[m.id] = dict(kind=m.kind, value=round(v, 4), unit=a.unit, alloc=round(a.value, 4),
                         u=round(v / a.value, 4) if a.value > 0 else None, **extra)
    out["_rails"] = rail_drops(rb, brief)
    return out


class _AllocCtx:
    """What critical_modules.allocation needs: volts, npins, terms."""

    def __init__(self, rb, brief, terms):
        self.rb, self.terms = rb, terms
        self.nets = brief.get("nets") or {}

    def volts(self, net):
        from .critical_modules import Ctx
        return Ctx.volts(self, net)

    def npins(self, u):
        f = self.rb.fp.get(u)
        return len(f.pads) if f is not None else 2


def fills_of(board_path):
    """{net: {layer: [Polygon]}} of KiCad's refill of a board (pcbnew_io.zone_fills)."""
    from kae.board import pcbnew_io
    d = pcbnew_io.zone_fills(board_path)
    out = {}
    for z in d.get("zones") or []:
        if z.get("teardrop") or not z.get("net") or (z.get("name") or "").startswith("kae-crit:"):
            continue                    # guard pours are the bridge's hint, not copper
        for l, rings_list in (z.get("layers") or {}).items():
            for rings in rings_list:
                if rings and len(rings[0]) >= 3:
                    pg = Polygon(rings[0], [h for h in rings[1:] if len(h) >= 3])
                    if not pg.is_valid:
                        pg = pg.buffer(0)
                    out.setdefault(z["net"], {}).setdefault(l, []).append(pg)
    return out


# ----------------------------------------------------------------------------- recheck
def recheck(board_routed, brief, stage, rise=0.15, fills="kicad", terms=None, cover_drop=0.10):
    """Modules whose routed utilization rose by more than `rise` over `stage` ({id: u} or
    {id: {u, plane_cover}}), crossed the budget, or whose ground plane under the loop lost
    more than `cover_drop` of its cover (other nets' copper perforating it). Returns
    dict(modules={id: {u_stage, u_routed, ...}}, retweak=[ids])."""
    phys = board_physics(board_routed, brief=brief, fills=fills, terms=terms)
    mods = {}
    flagged = []
    for mid, st in (stage or {}).items():
        st = st if isinstance(st, dict) else dict(u=st)
        u0, c0 = st.get("u"), st.get("plane_cover")
        r = phys.get(mid) or {}
        u1, c1 = r.get("u"), r.get("plane_cover")
        rec = dict(u_stage=u0, u_routed=u1, value=r.get("value"), unit=r.get("unit"), cover_stage=c0, cover_routed=c1)
        worse = u0 is not None and u1 is not None and (u1 > u0 * (1.0 + rise) or (u0 <= 1.0 < u1))
        cut = c0 is not None and c1 is not None and c1 < c0 - cover_drop
        rec["flag"] = bool(worse or cut)
        if cut:
            rec["why"] = "plane perforated"
        if worse or cut:
            flagged.append(mid)
        mods[mid] = rec
    return dict(modules=mods, retweak=flagged, rails=phys.get("_rails"))


# ----------------------------------------------------------------------------- stage values
def locked_only(board_routed, dst):
    """dst = the routed board with its unlocked routing removed (the critical copper alone)."""
    from . import critical_write as W
    items = W.routing(board_routed)
    W.edit(board_routed, dst, remove=[r["uuid"] for r in items if not r["locked"]])
    for ext in (".kicad_pro", ".kicad_dru", ".kicad_prl"):
        s = Path(board_routed).with_suffix(ext)
        if s.exists():
            import shutil
            shutil.copy2(s, Path(dst).with_suffix(ext))
    return dst


def stage_values(board, brief, fills="kicad", terms=None):
    """{module id: {u, plane_cover}} on a board (the module stage: its critical copper alone)."""
    ph = board_physics(board, brief=brief, fills=fills, terms=terms)
    return {k: dict(u=v["u"], plane_cover=v.get("plane_cover")) for k, v in ph.items()
            if k != "_rails" and isinstance(v, dict) and v.get("u") is not None}


def routed_stage(stage, sess):
    """The stage values of the modules the critical stage routed: the rest (doubtful
    pairings, skipped kinds) never had critical copper to protect."""
    mine = {m.id for m in sess.modules if m.status in ("routed", "partial")}
    return {k: v for k, v in stage.items() if k in mine}


def modules_to_retweak(board_routed, brief, stage=None, rise=0.15, workdir=None, terms=None):
    """The joint loop's interface: module ids whose routed physics worsened (see recheck);
    without `stage`, the module stage is the routed board's locked (critical) copper alone."""
    import tempfile
    if stage is None:
        with tempfile.TemporaryDirectory(prefix="kae-recheck-", dir=workdir) as d:
            lo = locked_only(board_routed, Path(d) / "locked.kicad_pcb")
            stage = stage_values(lo, brief, terms=terms)
    return recheck(board_routed, brief, stage, rise=rise, terms=terms)


# ----------------------------------------------------------------------------- re-tweak
def module_region(sess, mid, margin=1.0):
    """The board region a module's physics lives in: hull of its copper and terminals."""
    geoms = []
    for it in sess.space.routed:
        if it.owner and it.owner[0] == mid:
            geoms.append(it.geom.buffer(it.r))
    m = next((x for x in sess.modules if x.id == mid), None)
    if m is not None:
        for u in m.parts:
            for it in sess.space.pads_by_fp.get(u, []):
                if it.net:
                    geoms.append(it.geom)
    if not geoms:
        return None
    return unary_union(geoms).convex_hull.buffer(margin)


def guard_zones(board, region, net, layer, name, min_area=0.5):
    """Guard pours [(net, layer, rings, name, priority)] over `region` on `layer`: inside the
    zones of `net` there (the plane they guard), outside every other net's zone on the
    layer, one priority above every zone on it (KiCad reports overlapping zones of equal
    priority as zones_intersect, even of one net)."""
    from shapely.geometry import Polygon as _Poly
    own = [z.outline for z in board.zones if z.net == net and layer in z.layers and z.outline is not None
           and not (z.name or "").startswith("kae-crit:")]
    if not own or region is None or region.is_empty:
        return []
    g = region.intersection(unary_union(own))
    other = [z.outline for z in board.zones if z.net and z.net != net and layer in z.layers and z.outline is not None]
    if other:
        g = g.difference(unary_union(other).buffer(0.05))
    prio = 1 + max([int(z.priority or 0) for z in board.zones if layer in z.layers] or [0])
    out = []
    for part in getattr(g, "geoms", [g]):
        if isinstance(part, _Poly) and part.area > min_area:
            for piece in _hole_free(part):          # a zone is written as one outline
                if piece.area > min_area:
                    out.append((net, layer, [list(piece.exterior.coords)], name, prio))
    return out


def merge_guards(guards, min_area=0.5):
    """Guards of one net and layer united into non-overlapping hole-free pieces, so two
    modules' guards never overlap each other at one priority (zones_intersect); each piece
    keeps the highest priority and the first name of what it merges."""
    from shapely.geometry import Polygon as _Poly
    groups = {}
    for g in guards:
        net, layer, rings, name = g[:4]
        prio = g[4] if len(g) > 4 else 0
        e = groups.setdefault((net, layer), dict(polys=[], prio=prio, names=[]))
        e["polys"].append(_Poly(rings[0]))
        e["prio"] = max(e["prio"], prio)
        e["names"].append(name)
    out = []
    for (net, layer), e in groups.items():
        u = unary_union(e["polys"])
        names = list(dict.fromkeys(e["names"]))
        name = names[0] + (f"+{len(names) - 1}" if len(names) > 1 else "")
        for part in getattr(u, "geoms", [u]):
            if isinstance(part, _Poly) and part.area > min_area:
                for piece in _hole_free(part):
                    if piece.area > min_area:
                        out.append((net, layer, [list(piece.exterior.coords)], name, e["prio"]))
    return out


def _hole_free(poly):
    """Pieces of a polygon without holes: cut through each hole's centroid until none is left."""
    from shapely.geometry import Polygon as _Poly
    from shapely.ops import split
    out, todo = [], [poly]
    while todo:
        p = todo.pop()
        if not p.interiors:
            out.append(p)
            continue
        c = _Poly(p.interiors[0]).centroid
        x0, y0, x1, y1 = p.bounds
        parts = [q for q in split(p, LineString([(c.x, y0 - 1.0), (c.x, y1 + 1.0)])).geoms
                 if isinstance(q, _Poly) and q.area > 1e-9]
        if len(parts) < 2:
            continue                                # cannot be cut: leave it out (never over-cover)
        todo += parts
    return out


def _plane_layers(sess, mid, region):
    """Layers of the planes under a module (where foreign copper perforates its return)."""
    m = next((x for x in sess.modules if x.id == mid), None)
    out = set()
    if m is None or region is None:
        return out
    c = region.centroid
    for u in m.parts:
        side = sess.ctx.side_layer(u)
        h, pl, pn = sess.ctx.plane(side, c.x, c.y, gnd=True)
        if pl is not None:
            out.add((pl, pn))
        h, pl, pn = sess.ctx.plane(side, c.x, c.y, gnd=False)
        if pl is not None:
            out.add((pl, pn))
    return out


def conflicts(board_routed, sess, mid, region):
    """Unlocked routing of other nets that cuts the module's planes inside its region, or
    crowds its own layer there: [uuid]."""
    from kae.board.kicad_file import load as _load
    b = _load(board_routed)
    m = next((x for x in sess.modules if x.id == mid), None)
    nets = {it.net for it in sess.space.routed if it.owner and it.owner[0] == mid}
    planes = _plane_layers(sess, mid, region)
    players = {l for l, _ in planes}
    own_layers = {sess.ctx.side_layer(u) for u in (m.parts if m else [])}
    out = []
    for t in b.tracks:
        if t.locked or t.net in nets:
            continue
        if t.layer not in players and t.layer not in own_layers:
            continue
        if LineString([t.start, t.end]).buffer(t.width / 2).intersects(region):
            out.append(t.uuid)
    for v in b.vias:
        if v.locked or v.net in nets:
            continue
        if Point(v.x, v.y).buffer(v.size / 2).intersects(region):
            out.append(v.uuid)
    return out, planes


def retweak_loop(sess, routed, input_path, output_path, wd, rounds=3, seed=0, deadline=None, bridge_opts=None,
                 rise=0.15, log=print):
    """Recheck the routed board; for flagged modules rip up the conflicting copper of other
    nets in their region, guard their planes, let the bridge re-route, keep the round when
    KiCad's DRC is no worse; repeat up to `rounds` (see the module docstring)."""
    from . import bridge as BR
    from . import critical_write as W
    from . import drc as D
    wd = Path(wd)
    brief = sess.brief
    w0 = wd / "crit.kicad_pcb"
    hist = []
    t0 = time.monotonic()

    def left():
        return (deadline - time.monotonic()) if deadline else 1e9

    def score(board):
        st = D.stage_board(board, input_path, wd / f"drc_{Path(board).stem}")
        rep = D.run(st, st.with_suffix(".json"), timeout=max(30, min(300, left())))
        s_ = D.summary(rep)
        return s_
    try:
        stage = stage_values(w0, brief)
    except Exception as e:  # noqa: BLE001
        return dict(error=f"stage values: {type(e).__name__}: {e}")
    stage = routed_stage(stage, sess)
    cur = Path(routed)
    cur_s = score(cur)
    cur_rc = recheck(cur, brief, stage, rise=rise)
    hist.append(dict(round=0, errors=cur_s["errors"], unconnected=cur_s["unconnected"],
                     u={k: (v.get("u_stage"), v.get("u_routed")) for k, v in cur_rc["modules"].items()},
                     cover={k: (v.get("cover_stage"), v.get("cover_routed")) for k, v in cur_rc["modules"].items()
                            if v.get("cover_stage") is not None},
                     flagged=cur_rc["retweak"]))
    log(f"recheck 0: flagged {cur_rc['retweak']}; {cur_s['errors']} errors, {cur_s['unconnected']} unconnected")
    for k in range(1, rounds + 1):
        if not cur_rc["retweak"] or left() < 90:
            break
        work = wd / f"rt{k}.kicad_pcb"
        W.stage(cur, wd, f"rt{k}")
        rip, guards = [], []
        bcur = load(cur)        # its zones include the first pass's guards: new ones go above them
        for mid in cur_rc["retweak"]:
            region = module_region(sess, mid)
            if region is None:
                continue
            uu, planes = conflicts(cur, sess, mid, region)
            rip += uu
            for (pl, pn) in planes:
                if pn and region.area > 0:
                    guards += guard_zones(bcur, region, pn, pl, f"{W.GUARD_PREFIX}{mid}")
        guards = merge_guards(guards)
        if not rip:
            hist.append(dict(round=k, note="nothing to rip up"))
            break
        W.edit(cur, work, remove=rip, lock="all")
        tmp = wd / f"rt{k}_g.kicad_pcb"
        W.append_items(work, tmp, zones=guards)
        W.stage(tmp, wd, f"rt{k}_g")
        out = wd / f"rt{k}_routed.kicad_pcb"
        b = BR.route(tmp, out, seed=seed + k, time_s=max(30.0, 0.8 * left() - 20.0), workdir=wd / f"bridge_rt{k}",
                     opts=dict(bridge_opts or {}, keep=True), log=log)
        if not out.exists():
            hist.append(dict(round=k, ripped=len(rip), note=f"bridge: {b.get('status')}"))
            break
        clean = wd / f"rt{k}_clean.kicad_pcb"
        # unlock what this round locked (everything but the critical copper), drop the guards
        crit = {r["uuid"] for r in W.routing(w0) if r["locked"]}
        allr = W.routing(out)
        W.edit(out, clean, unlock=[r["uuid"] for r in allr if r["uuid"] not in crit and r["locked"]], drop_guards=True)
        W.stage(clean, wd, f"rt{k}_clean")
        s_ = score(clean)
        rc = recheck(clean, brief, stage, rise=rise)
        def badness(r, ms):
            return sum((r["modules"].get(m, {}).get("u_routed") or 0.0)
                       - (r["modules"].get(m, {}).get("cover_routed") or 0.0) for m in ms)
        better_phys = badness(rc, cur_rc["retweak"]) < badness(cur_rc, cur_rc["retweak"]) - 1e-6
        keep = (s_["errors"] + s_["unconnected"], s_["unconnected"]) <= (cur_s["errors"] + cur_s["unconnected"],
                                                                        cur_s["unconnected"]) and better_phys
        hist.append(dict(round=k, ripped=len(rip), guards=len(guards), errors=s_["errors"], unconnected=s_["unconnected"],
                         u={m: (v.get("u_stage"), v.get("u_routed")) for m, v in rc["modules"].items()},
                         cover={m: (v.get("cover_stage"), v.get("cover_routed")) for m, v in rc["modules"].items()
                                if v.get("cover_stage") is not None},
                         flagged=rc["retweak"], kept=keep))
        log(f"retweak {k}: ripped {len(rip)}, {s_['errors']} errors, {s_['unconnected']} unconnected, "
            f"flagged {rc['retweak']} ({'kept' if keep else 'discarded'})")
        if keep:
            cur, cur_s, cur_rc = clean, s_, rc
            W.transplant(cur, input_path, output_path)
        else:
            break
    return dict(rounds=hist, final=dict(errors=cur_s["errors"], unconnected=cur_s["unconnected"]),
                seconds=round(time.monotonic() - t0, 1))
