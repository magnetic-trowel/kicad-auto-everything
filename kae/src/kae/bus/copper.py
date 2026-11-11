# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Copper of one lane of a bus: pad-to-pad path, length, vias, layers, turning, serpentines.

Used by kae.bus.scorecard to measure finished boards (report-only). Nothing here decides routing."""
from __future__ import annotations
import heapq
import math
from collections import defaultdict
import numpy as np

SAMPLE = 0.25


def flatten_tracks(board):
    """net -> [(x1,y1,x2,y2,layer,width)] ; arcs split into 8 chords."""
    tr = defaultdict(list)
    for t in board.tracks:
        if not t.net:
            continue
        if t.mid is not None:
            pts = arc_pts(t.start, t.mid, t.end, 8)
            for (a, b) in zip(pts, pts[1:]):
                tr[t.net].append((a[0], a[1], b[0], b[1], t.layer, t.width))
        else:
            tr[t.net].append((t.start[0], t.start[1], t.end[0], t.end[1], t.layer, t.width))
    vs = defaultdict(list)
    for v in board.vias:
        if v.net:
            vs[v.net].append(v)
    return tr, vs


def arc_pts(a, m, b, n):
    ax, ay = a; mx, my = m; bx, by = b
    d = 2 * (ax * (my - by) + mx * (by - ay) + bx * (ay - my))
    if abs(d) < 1e-9:
        return [a, b]
    ux = ((ax * ax + ay * ay) * (my - by) + (mx * mx + my * my) * (by - ay) + (bx * bx + by * by) * (ay - my)) / d
    uy = ((ax * ax + ay * ay) * (bx - mx) + (mx * mx + my * my) * (ax - bx) + (bx * bx + by * by) * (mx - ax)) / d
    r = math.hypot(ax - ux, ay - uy)
    t0 = math.atan2(ay - uy, ax - ux)
    tm = math.atan2(my - uy, mx - ux)
    t1 = math.atan2(by - uy, bx - ux)
    def diff(x, y):
        return (y - x + math.pi) % (2 * math.pi) - math.pi
    dtm = diff(t0, tm)
    dte = diff(tm, t1)
    tot = dtm + dte
    out = [(ux + r * math.cos(t0 + tot * i / n), uy + r * math.sin(t0 + tot * i / n)) for i in range(n + 1)]
    out[0] = a
    out[-1] = b
    return out


class NetGraph:
    """Graph of one net's copper: nodes (x,y,layer); edges by track length; via nodes join layers; pads attach."""

    def __init__(self, segs, vias, pads=()):
        self.node = {}
        self.xy = []
        self.adj = []
        self.pad_nodes = []
        self.segs = segs
        # split segments where another segment's endpoint lies on the interior (T joints)
        arr = np.array([[s[0], s[1], s[2], s[3]] for s in segs]) if segs else np.zeros((0, 4))
        layers = [s[4] for s in segs]
        widths = [s[5] for s in segs]
        endpoints = defaultdict(list)
        for i, s in enumerate(segs):
            endpoints[s[4]].append((s[0], s[1]))
            endpoints[s[4]].append((s[2], s[3]))
        split = defaultdict(list)
        if len(segs) and len(segs) < 3000:
            for layer, pts in endpoints.items():
                P = np.array(pts)
                idx = [i for i, s in enumerate(segs) if s[4] == layer]
                A = arr[idx]
                for k, i in enumerate(idx):
                    a = A[k, :2]; b = A[k, 2:]
                    ab = b - a
                    L2 = (ab * ab).sum()
                    if L2 < 1e-9:
                        continue
                    t = ((P - a) * ab).sum(axis=1) / L2
                    q = a + np.outer(np.clip(t, 0, 1), ab)
                    d2 = ((P - q) ** 2).sum(axis=1)
                    hit = (t > 1e-4) & (t < 1 - 1e-4) & (d2 < 2.5e-5)
                    for pidx in np.nonzero(hit)[0]:
                        split[i].append((float(t[pidx]), tuple(P[pidx])))
        for i, s in enumerate(segs):
            ts = sorted(set(split.get(i, [])))
            pts = [(s[0], s[1])] + [p for _, p in ts] + [(s[2], s[3])]
            for a, b in zip(pts, pts[1:]):
                ka = self._n(a[0], a[1], s[4])
                kb = self._n(b[0], b[1], s[4])
                if ka != kb:
                    d = math.dist(a, b)
                    self.adj[ka].append((kb, d, False))
                    self.adj[kb].append((ka, d, False))
        # vias: connect nodes across layers within via radius
        self.vias = vias
        layer_nodes = defaultdict(list)
        for key, idx in self.node.items():
            layer_nodes[key[2]].append(idx)
        for v in vias:
            vn = len(self.xy)
            self.xy.append((v.x, v.y, None))
            self.adj.append([])
            r = (v.size or 0.4) / 2 + 0.02
            for lay in layer_nodes:   # any layer: board files with renamed copper layers name via spans differently
                for idx in self._near(lay, v.x, v.y, r, layer_nodes):
                    self.adj[vn].append((idx, 0.0, True))
                    self.adj[idx].append((vn, 0.0, True))
        # pads of the net bridge the tracks they touch (through-hole pads also bridge layers)
        for p in pads:
            r = max(p.size) / 2 + 0.05
            pn = len(self.xy)
            self.xy.append((p.x, p.y, None))
            self.adj.append([])
            self.pad_nodes.append(pn)
            lays = [l for l in p.layers if l in layer_nodes]
            if not lays or p.drill:
                lays = list(layer_nodes)      # renamed copper layers, or a through-hole pad: any layer
            for lay in lays:
                for idx in layer_nodes[lay]:
                    n = self.xy[idx]
                    if abs(n[0] - p.x) <= r and abs(n[1] - p.y) <= r:
                        self.adj[pn].append((idx, 0.0, False))
                        self.adj[idx].append((pn, 0.0, False))
        self.layer_nodes = layer_nodes

    def _n(self, x, y, layer):
        k = (round(x, 3), round(y, 3), layer)
        i = self.node.get(k)
        if i is None:
            i = len(self.xy)
            self.node[k] = i
            self.xy.append((x, y, layer))
            self.adj.append([])
        return i

    def _near(self, layer, x, y, r, layer_nodes=None):
        out = []
        ln = layer_nodes if layer_nodes is not None else self.layer_nodes
        for idx in ln.get(layer, ()):
            n = self.xy[idx]
            if math.hypot(n[0] - x, n[1] - y) <= r:
                out.append(idx)
        return out

    def attach(self, x, y, layers, w, h):
        """Nodes connected to a pad at (x,y) with half-size in any orientation."""
        r = max(w, h) / 2 + 0.05
        out = []
        if not any(l in self.layer_nodes for l in layers):
            layers = list(self.layer_nodes)      # renamed copper layers
        for lay in layers:
            if lay not in self.layer_nodes:
                continue
            for idx in self.layer_nodes[lay]:
                n = self.xy[idx]
                if abs(n[0] - x) <= r and abs(n[1] - y) <= r:
                    out.append(idx)
        return out

    def dijkstra(self, sources, targets):
        tset = set(targets)
        if not sources or not tset:
            return None
        dist = {}
        prev = {}
        hq = []
        for s in sources:
            dist[s] = 0.0
            heapq.heappush(hq, (0.0, s))
        while hq:
            d, u = heapq.heappop(hq)
            if d > dist.get(u, math.inf):
                continue
            if u in tset:
                path = [u]
                while path[-1] in prev:
                    path.append(prev[path[-1]])
                path.reverse()
                return path
            for v, w, isvia in self.adj[u]:
                nd = d + w
                if nd < dist.get(v, math.inf):
                    dist[v] = nd
                    prev[v] = u
                    heapq.heappush(hq, (nd, v))
        return None

    def missing_connections(self):
        """Connected components among the net's pads, minus one: the opens a ratsnest would show (zones ignored)."""
        seen = set()
        comps = 0
        for pn in self.pad_nodes:
            if pn in seen:
                continue
            comps += 1
            stack = [pn]
            seen.add(pn)
            while stack:
                u = stack.pop()
                for v, _w, _i in self.adj[u]:
                    if v not in seen:
                        seen.add(v)
                        stack.append(v)
        return max(0, comps - 1)

    def tree_dist(self, source):
        """All-node distances from a set of sources (for branch analysis)."""
        dist = {}
        hq = []
        for s in source:
            dist[s] = 0.0
            heapq.heappush(hq, (0.0, s))
        while hq:
            d, u = heapq.heappop(hq)
            if d > dist.get(u, math.inf):
                continue
            for v, w, _ in self.adj[u]:
                if d + w < dist.get(v, math.inf):
                    dist[v] = d + w
                    heapq.heappush(hq, (d + w, v))
        return dist


def pad_layers(p, cu):
    l = [x for x in p.layers if not x.endswith(('.Paste', '.Mask', '.SilkS', '.Adhes'))]
    return l or list(cu)


def polyline_from(g, path):
    """path node ids -> list of (x,y,layer) with via moves as repeated xy across layers."""
    pts = []
    for i in path:
        x, y, lay = g.xy[i]
        if lay is None:   # via node: keep position only; layer changes on next node
            continue
        pts.append((x, y, lay))
    return pts


def lane_metrics(chain_pts):
    """chain_pts: list of pieces; piece = list of (x,y,layer). Returns length, vias, layers, turning, samples."""
    vias = 0
    layer_len = defaultdict(float)
    samples = []  # (x, y, layer, s)
    headings = []
    spans = []    # (layer, layer) of each layer change
    s_along = 0.0
    last_layer = None
    for piece in chain_pts:
        for i in range(len(piece) - 1):
            x1, y1, l1 = piece[i]
            x2, y2, l2 = piece[i + 1]
            if l1 != l2:
                continue
            seg = math.hypot(x2 - x1, y2 - y1)
            if seg < 1e-9:
                continue
            hd = math.atan2(y2 - y1, x2 - x1)
            headings.append((s_along, hd, seg))
            n = max(1, int(seg / SAMPLE))
            for k in range(n):
                t = (k + 0.5) / n
                samples.append((x1 + (x2 - x1) * t, y1 + (y2 - y1) * t, l1, s_along + t * seg))
            s_along += seg
            layer_len[l1] += seg
            if last_layer is not None and l1 != last_layer:
                vias += 1
                spans.append(tuple(sorted((last_layer, l1))))
            last_layer = l1
    # turning
    net_turn = 0.0
    abs_turn = 0.0
    for (s1, h1, _), (s2, h2, _) in zip(headings, headings[1:]):
        dt = (h2 - h1 + math.pi) % (2 * math.pi) - math.pi
        if abs(dt) > 3.0:   # U-turn at a pad/stub artefact
            continue
        net_turn += dt
        abs_turn += abs(dt)
    # serpentine: windows of 3 mm arc where path curls (chord/arc small) and heading wiggles
    serp = serpentine(headings, s_along)
    return dict(length=s_along, vias=vias, layer_len=dict(layer_len), net_turn=net_turn, abs_turn=abs_turn, samples=samples,
                serp=serp, n_seg=len(headings), headings=headings, spans=spans)


def serpentine(headings, total):
    """Detect meander runs: consecutive headings alternating around a mean with net arc/chord >= 1.6 over a sliding 6 mm window."""
    if len(headings) < 6 or total < 6:
        return dict(n=0, len=0.0, pos=[], excess=0.0, runs=[])
    # reconstruct points
    pts = [(0.0, 0.0)]
    x = y = 0.0
    arr = []
    for s, h, seg in headings:
        x += math.cos(h) * seg
        y += math.sin(h) * seg
        pts.append((x, y))
        arr.append(seg)
    pts = np.array(pts)
    arc = np.concatenate([[0.0], np.cumsum(arr)])
    # windows by index: for each start, extend until arc >= 6
    runs = []
    n = len(pts)
    i = 0
    W = 6.0
    flagged = np.zeros(n, dtype=bool)
    for i in range(n - 1):
        j = int(np.searchsorted(arc, arc[i] + W))
        if j >= n:
            break
        chord = math.dist(pts[i], pts[j])
        a = arc[j] - arc[i]
        if a <= 0:
            continue
        if a / max(chord, 1e-6) >= 1.5:
            # require wiggle: at least 4 sign changes of heading delta relative to the chord direction
            ang = math.atan2(pts[j][1] - pts[i][1], pts[j][0] - pts[i][0])
            seq = []
            for k in range(i, j):
                d = (headings[k][1] - ang + math.pi) % (2 * math.pi) - math.pi
                if abs(d) > 0.15:
                    seq.append(1 if d > 0 else -1)
            sc = sum(1 for a1, b1 in zip(seq, seq[1:]) if a1 != b1)
            if sc >= 2:
                flagged[i:j + 1] = True
    if not flagged.any():
        return dict(n=0, len=0.0, pos=[], excess=0.0, runs=[])
    # merge
    out = []
    excess = 0.0
    i = 0
    while i < n:
        if flagged[i]:
            j = i
            while j + 1 < n and flagged[j + 1]:
                j += 1
            out.append((float(arc[i]), float(arc[j])))
            excess += max(0.0, float(arc[j] - arc[i]) - math.dist(pts[i], pts[j]))   # length a straight run would not have
            i = j + 1
        else:
            i += 1
    return dict(n=len(out), len=sum(b - a for a, b in out), pos=[((a + b) / 2 / total) for a, b in out], excess=excess, runs=out)
