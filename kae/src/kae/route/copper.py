# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""One net's copper as a graph, connected the way KiCad connects it.

KiCad's rule (pcbnew/connectivity/connectivity_algo.cpp, CN_VISITOR at 10.0): two items of a net are
connected when their effective shapes collide on a layer they share. A track's shape is a
SHAPE_SEGMENT: its centreline swept by a disc of the track's width, so its ends are round. That is also
the copper a fab makes. A via is a disc on each layer it spans; a pad is its polygon; a zone is its
refilled polygons, which also connect any item with an anchor inside or a shape overlapping them; a
board-level copper shape with a net (KiCad 8+) is a region like a zone fill.

`NetGraph(board, net, cu, pads, fills)` applies that rule exactly. Items are tested analytically
(distance between centrelines against the half-widths, never a polygonised disc):

    track-track   dist(centreline a, centreline b) <= (w_a + w_b) / 2
    track-via     dist(centreline, centre) <= w / 2 + r
    track-pad     dist(centreline, pad polygon) <= w / 2
    via-pad       dist(centre, pad polygon) <= r
    via-via, pad-pad, and every item against a fill polygon, likewise

A contact sits where the current crosses: at the closest points of the two centrelines (or of the
centreline and the via centre, pad or fill). A track is split there and an edge spans the real gap (zero
for ends that coincide, up to the sum of the half-widths for an offset overlap), so path lengths, R and
L stay physical. Pads a footprint bonds inside the part (KiCad 9+ jumper pad groups, or same-numbered
pads with duplicate_pad_numbers_are_jumpers) are joined by a strip between their centres, as KiCad joins
them. Arcs are chords of at most 22.5 degrees. Edge weights are length x L'(w) at 0.5 mm, the
HF current's path cost. A pour links its contacts as 2 mm strips: each to its nearest neighbours,
along the Delaunay edges that stay in the fill, and by the shortest links that join what is still apart,
so one fill polygon is always one conductor.

The graph keeps the interface the physics reads: `nodes` [(kind, layers, x, y, extra)] with kind pad
(extra: polygon), via, or kp (extra: width); `adj` {node: [(node, weight, piece)]} with pieces
('strip' | 'pour', layer, a, b, w); `pad_node` {(footprint uuid, pad number): [nodes]}; `path`.
"""
from __future__ import annotations

import heapq
import math

import numpy as np
from shapely import STRtree
from shapely.geometry import LineString, Point
from shapely.ops import nearest_points

from kae.board import transform
from kae.physics.kernels import lprime_hj

INF = float("inf")
EPS = 1e-6           # mm: shapes closer than this touch (KiCad's integer nanometres)
_KEY = 4             # keypoints merge when equal to 1e-4 mm
ARC_STEP = math.pi / 8
POUR_LINKS = 8
POUR_W = 2.0


def _lp(w):
    """L' weight of a strip of width w at a nominal 0.5 mm height (relative path cost)."""
    return lprime_hj(max(w, 0.05), 0.5)


def arc_points(start, mid, end):
    """Points along a three-point arc, chords of at most ARC_STEP (straight when collinear)."""
    (x1, y1), (x2, y2), (x3, y3) = start, mid, end
    d = 2 * (x1 * (y2 - y3) + x2 * (y3 - y1) + x3 * (y1 - y2))
    if abs(d) < 1e-12:
        return [start, end]
    ux = ((x1 * x1 + y1 * y1) * (y2 - y3) + (x2 * x2 + y2 * y2) * (y3 - y1) + (x3 * x3 + y3 * y3) * (y1 - y2)) / d
    uy = ((x1 * x1 + y1 * y1) * (x3 - x2) + (x2 * x2 + y2 * y2) * (x1 - x3) + (x3 * x3 + y3 * y3) * (x2 - x1)) / d
    r = math.hypot(x1 - ux, y1 - uy)
    a1, a2, a3 = (math.atan2(y - uy, x - ux) for x, y in (start, mid, end))

    def ccw(a, b):
        return (b - a) % (2 * math.pi)
    span = ccw(a1, a3)
    if ccw(a1, a2) > span:                      # the mid point is on the other way round
        span -= 2 * math.pi
    n = max(2, math.ceil(abs(span) / ARC_STEP))
    pts = [start]
    for k in range(1, n):
        a = a1 + span * k / n
        pts.append((ux + r * math.cos(a), uy + r * math.sin(a)))
    pts.append(end)
    return pts


def _pour_links(P, pg):
    """Pairs (i, j) of a fill region's contacts P (n x 2) to join through the pour: each contact's
    POUR_LINKS nearest, the Delaunay neighbours whose midpoint lies in the fill, then the shortest
    links that join what is still apart. A fill polygon is one conductor, so its contacts always end
    up connected (nearest-neighbour links alone split a pour whose contacts sit in distant clusters)."""
    n = len(P)
    pairs = set()
    nn = min(POUR_LINKS, n - 1)
    for i in range(n):
        d = np.hypot(P[:, 0] - P[i, 0], P[:, 1] - P[i, 1])
        for j in np.argsort(d)[1:nn + 1]:
            pairs.add((min(i, int(j)), max(i, int(j))))
    if n >= 4:
        try:
            from scipy.spatial import Delaunay
            for s in Delaunay(P).simplices:
                for a, b in ((s[0], s[1]), (s[1], s[2]), (s[0], s[2])):
                    a, b = int(min(a, b)), int(max(a, b))
                    if (a, b) not in pairs and pg.distance(Point((P[a] + P[b]) / 2)) <= EPS:
                        pairs.add((a, b))
        except Exception:      # noqa: BLE001 - degenerate (collinear) contacts: the joining step covers them
            pass
    parent = list(range(n))

    def f(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    for a, b in pairs:
        parent[f(a)] = f(b)
    while True:
        groups = {}
        for i in range(n):
            groups.setdefault(f(i), []).append(i)
        if len(groups) < 2:
            break
        g = min(groups.values(), key=len)
        rest = np.array([i for i in range(n) if f(i) != f(g[0])])
        best = None
        for i in g:
            d = np.hypot(P[rest, 0] - P[i, 0], P[rest, 1] - P[i, 1])
            j = int(np.argmin(d))
            if best is None or d[j] < best[0]:
                best = (float(d[j]), i, int(rest[j]))
        _, a, b = best
        pairs.add((min(a, b), max(a, b)))
        parent[f(a)] = f(b)
    return sorted(pairs)


class _Seg:
    """A straight piece of a track: centreline a->c, width w, and the points it is split at."""
    __slots__ = ("layer", "a", "c", "w", "line", "splits")

    def __init__(self, layer, a, c, w):
        self.layer, self.a, self.c, self.w = layer, tuple(a), tuple(c), w
        self.line = LineString([a, c])
        self.splits = {self.a: 0.0, self.c: 1.0}

    def split(self, p):
        """Split at the point of the centreline nearest p; returns that point."""
        dx, dy = self.c[0] - self.a[0], self.c[1] - self.a[1]
        l2 = dx * dx + dy * dy
        t = 0.0 if l2 < 1e-18 else max(0.0, min(1.0, ((p[0] - self.a[0]) * dx + (p[1] - self.a[1]) * dy) / l2))
        q = self.a if t <= 1e-9 else self.c if t >= 1 - 1e-9 else (self.a[0] + t * dx, self.a[1] + t * dy)
        self.splits.setdefault(q, t)
        return q


class NetGraph:
    """Conductors of one net as a weighted graph, connected as KiCad connects them (module docstring)."""

    def __init__(self, board, net, cu, pads, fills=None):
        """pads: [(footprint, pad, polygon)] of the net; fills: {layer: [Polygon]} of its refilled
        zones, or None to use the zone outlines."""
        self.net = net
        self.nodes = []
        self.adj = {}
        self.key = {}
        self.pad_node = {}
        self._via_r = {}
        cu = list(cu)
        cuset = set(cu)
        items = {l: [] for l in cu}           # layer -> [(kind, ref, geom, half)]
        # pads
        for f, p, geom in pads:
            x, y = transform.pad_xy(f, p)
            layers = tuple(l for l in p.layers if l in cuset) or ((cu[0],) if f.side == "F" else (cu[-1],))
            k = len(self.nodes)
            self.nodes.append(("pad", layers, x, y, geom))
            self.pad_node.setdefault((f.uuid, p.number), []).append(k)
            for l in layers:
                items[l].append(("pad", k, geom, 0.0))
        # pads bonded inside a part (jumper pad groups; same-numbered pads when those are jumpers)
        bonds = []
        by_fp = {}
        for (fu, num), ks in self.pad_node.items():
            by_fp.setdefault(fu, {})[num] = ks
        for f in {f.uuid: f for f, _p, _g in pads}.values():
            for grp in getattr(f, "jumpers", ()) or ():
                ks = [k for num in grp for k in by_fp.get(f.uuid, {}).get(num, [])]
                bonds += [(a, b) for a, b in zip(ks[:-1], ks[1:])]
        # vias: a disc on each layer they span
        for v in board.vias:
            if v.net != net:
                continue
            layers = tuple(l for l in (v.layers or cu) if l in cuset) or tuple(cu)
            if len(layers) == 2 and v.layers and set(v.layers) == {cu[0], cu[-1]}:
                layers = tuple(cu)                # a through via spans every copper layer
            k = len(self.nodes)
            self.nodes.append(("via", layers, v.x, v.y, None))
            self._via_r[k] = v.size / 2
            for l in layers:
                items[l].append(("via", k, Point(v.x, v.y), v.size / 2))
        # tracks and arcs as straight pieces
        segs = []
        for t in board.tracks:
            if t.net != net or t.layer not in cuset:
                continue
            pts = [t.start, t.end] if t.mid is None else arc_points(t.start, t.mid, t.end)
            for a, c in zip(pts[:-1], pts[1:]):
                s = _Seg(t.layer, a, c, t.width)
                segs.append(s)
                items[t.layer].append(("seg", s, s.line, t.width / 2))
        # contacts on each layer: shapes that collide
        links = []                             # (segment or node, point) <-> (segment or node, point)
        for l, its in items.items():
            if len(its) < 2:
                continue
            geoms = [g for _, _, g, _ in its]
            hmax = max(h for *_, h in its)
            tree = STRtree(geoms)
            for i, (ki, ri, gi, hi) in enumerate(its):
                for j in tree.query(gi, predicate="dwithin", distance=hi + hmax + EPS):
                    j = int(j)
                    if j <= i:
                        continue
                    kj, rj, gj, hj = its[j]
                    if gi.distance(gj) > hi + hj + EPS:
                        continue
                    if ki == "seg" and kj == "seg":
                        pa, pb = nearest_points(gi, gj)
                        links.append((ri, (pa.x, pa.y), rj, (pb.x, pb.y), l))
                    elif ki == "seg" or kj == "seg":
                        s, (kn, rn, gn) = (ri, (kj, rj, gj)) if ki == "seg" else (rj, (ki, ri, gi))
                        links.append((s, self._contact_on(s, kn, rn, gn), rn, None, l))
                    else:
                        links.append((ri, None, rj, None, l))
        # zones (refilled polygons, else outlines)
        regions = []
        if fills is not None:
            regions = [(l, pg) for l, polys in fills.items() if l in cuset for pg in polys]
        else:
            for z in board.zones:
                if z.net == net and z.outline is not None and not z.outline.is_empty:
                    regions += [(l, z.outline) for l in z.layers if l in cuset]
        # board-level copper shapes with this net conduct like a pour (KiCad 8+)
        regions += [(l, pg) for l, polys in (getattr(board, "copper", {}) or {}).get(net, {}).items()
                    if l in cuset for pg in polys]
        # overlapping regions of the net touch: a shared node inside their overlap joins them
        for i, (li, pi) in enumerate(regions):
            for lj, pj in regions[i + 1:]:
                if li == lj and pi.intersects(pj):
                    q = pi.intersection(pj).representative_point()
                    self._kp(li, (q.x, q.y), POUR_W)
        seg_by_layer = {}
        for s in segs:
            seg_by_layer.setdefault(s.layer, []).append(s)
        for l, pg in regions:
            # a track reaching into a fill with no end inside it gets a node where it enters
            for s in seg_by_layer.get(l, ()):
                if s.line.distance(pg) > s.w / 2 + EPS:
                    continue
                if any(pg.distance(Point(p)) <= s.w / 2 + EPS for p in s.splits):
                    continue
                inside = s.line.intersection(pg)
                p = inside.representative_point() if not inside.is_empty else nearest_points(s.line, pg)[0]
                s.split((p.x, p.y))
        # split the tracks at their contacts, then chain their keypoints
        resolved = []
        for ra, pa, rb, pb, l in links:
            na = self._kp(l, ra.split(pa), ra.w) if isinstance(ra, _Seg) else ra
            nb = self._kp(l, rb.split(pb), rb.w) if isinstance(rb, _Seg) else rb
            resolved.append((na, nb, l, ra, rb))
        for s in segs:
            pts = sorted(s.splits.items(), key=lambda kv: kv[1])
            ks = [self._kp(s.layer, p, s.w) for p, _ in pts]
            for (p0, _), (p1, _), k0, k1 in zip(pts[:-1], pts[1:], ks[:-1], ks[1:]):
                self._edge(k0, k1, math.dist(p0, p1) * _lp(s.w), ("strip", s.layer, p0, p1, s.w))
        for na, nb, l, ra, rb in resolved:
            if na == nb:
                continue
            a, b = self._xy(na), self._xy(nb)
            ws = [x.w for x in (ra, rb) if isinstance(x, _Seg)]
            w = min(ws) if ws else min(self._width(x) for x in (ra, rb))
            self._edge(na, nb, math.dist(a, b) * _lp(w), ("strip", l, a, b, w))
        for a, b in bonds:
            la, lb = self.nodes[a][1], self.nodes[b][1]
            l = next((x for x in la if x in lb), la[0])
            pa, pb = self._xy(a), self._xy(b)
            self._edge(a, b, math.dist(pa, pb) * _lp(0.3), ("strip", l, pa, pb, 0.3))   # the part's internal bond
        # zones: every node in or touching a fill region is a contact, joined through the pour
        for l, pg in regions:
            contacts = []
            for k, n in enumerate(self.nodes):
                kind, layers = n[0], n[1]
                if l not in layers:
                    continue
                pt = Point(n[2], n[3])
                if kind == "pad":
                    hit = pg.intersects(n[4])
                elif kind == "via":
                    hit = pg.distance(pt) <= self._via_r[k] + EPS
                else:
                    hit = pg.distance(pt) <= (n[4] or 0.0) / 2 + EPS
                if hit:
                    contacts.append(k)
            if len(contacts) < 2:
                continue
            P = np.array([[self.nodes[k][2], self.nodes[k][3]] for k in contacts])
            for i, j in _pour_links(P, pg):
                a, c = (float(P[i, 0]), float(P[i, 1])), (float(P[j, 0]), float(P[j, 1]))
                self._edge(contacts[i], contacts[j], math.dist(a, c) * _lp(POUR_W), ("pour", l, a, c, POUR_W))

    # ---- contacts
    def _contact_on(self, s, kind, ref, geom):
        """The point of segment s where it meets a pad or via: an end inside the pad, else the
        centreline point nearest the pad's or via's centre."""
        if kind == "pad":
            for p in (s.a, s.c):
                if geom.distance(Point(p)) <= EPS:
                    return p
        x, y = self.nodes[ref][2], self.nodes[ref][3]
        return (x, y)

    def _width(self, k):
        n = self.nodes[k]
        if n[0] == "kp":
            return n[4] or 0.2
        if n[0] == "pad":
            b = n[4].bounds
            return max(min(b[2] - b[0], b[3] - b[1]), 0.2)
        return 0.5

    def _xy(self, k):
        return (self.nodes[k][2], self.nodes[k][3])

    # ---- graph
    def _kp(self, layer, p, w=0.0):
        key = (layer, round(p[0], _KEY), round(p[1], _KEY))
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

    def components(self):
        """Node sets of the graph's connected pieces."""
        seen, out = set(), []
        for s in range(len(self.nodes)):
            if s in seen:
                continue
            comp, st = {s}, [s]
            seen.add(s)
            while st:
                u = st.pop()
                for v, _, _ in self.adj.get(u, ()):
                    if v not in seen:
                        seen.add(v)
                        comp.add(v)
                        st.append(v)
            out.append(comp)
        return out

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
