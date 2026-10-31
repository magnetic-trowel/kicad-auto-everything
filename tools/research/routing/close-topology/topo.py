# SPDX-License-Identifier: GPL-3.0-or-later
"""Topology of the multi-pad signal nets of a routed board, and the buses on it.

usage: topo.py <board.kicad_pcb[.gz]> [out.json]

Per signal net (no zone on it) with >= 3 pads and copper:
  pads, tracks length, vias,
  branch : non-pad points where >= 3 copper branches meet (track ends at a common point or
           via, or a track end on another track's interior: a T),
  thru   : pads that >= 2 branches leave (a chain passes through the pad),
  mst    : the Euclidean MST of the pad centres (a lower-bound-ish yardstick),
  dens   : copper of all nets in the net's pad box per mm^2 (congestion proxy).
Buses: groups of >= 4 nets that each join the same two footprints with pads that are
neighbours on both (pin adjacency on both ends), and name groups (common stem + index).
"""
import gzip, json, math, re, shutil, sys, tempfile
from collections import defaultdict
from pathlib import Path

from shapely.geometry import LineString, Point, box
from shapely.strtree import STRtree

from kae.board import transform
from kae.board.kicad_file import load
from kae.place.legalize import pad_shape

TOL = 0.002


def read(p):
    p = Path(p)
    if p.suffix == ".gz":
        tmp = Path(tempfile.mkdtemp()) / "b.kicad_pcb"
        with gzip.open(p, "rb") as f, open(tmp, "wb") as g:
            shutil.copyfileobj(f, g)
        p = tmp
    return load(p, rules=False)


def cu_layers(layers, cu):
    out = set()
    for l in layers:
        if l in cu:
            out.add(l)
        elif l in ("*.Cu", "F&B.Cu"):
            out |= set(cu)
    return out


def mst_len(pts):
    n = len(pts)
    if n < 2:
        return 0.0
    inn = [False] * n
    d = [math.inf] * n
    d[0] = 0
    tot = 0.0
    for _ in range(n):
        i = min((k for k in range(n) if not inn[k]), key=lambda k: d[k])
        inn[i] = True
        tot += d[i]
        for k in range(n):
            if not inn[k]:
                dd = math.dist(pts[i], pts[k])
                if dd < d[k]:
                    d[k] = dd
    return tot


def analyse(b):
    cu = list(b.stackup.copper) if b.stackup else ["F.Cu", "B.Cu"]
    zone_nets = {z.net for z in b.zones if z.net}
    pads = defaultdict(list)       # net -> [(name, poly, layers, (x, y))]
    for fp in b.footprints:
        for p in fp.pads:
            if not p.net:
                continue
            poly = transform.place_geom(pad_shape(p), fp.x, fp.y, fp.rot, fp.side)
            pads[p.net].append((f"{fp.ref}.{p.number}", poly, cu_layers(p.layers, cu), (p.x, p.y)))
    tracks = defaultdict(list)
    for t in b.tracks:
        if t.net and t.layer in cu:
            tracks[t.net].append(t)
    vias = defaultdict(list)
    for v in b.vias:
        if v.net:
            vias[v.net].append(v)
    # congestion proxy: all copper as lines
    allsegs = [LineString([t.start, t.end]) for t in b.tracks if t.layer in cu and t.start != t.end]
    tree = STRtree(allsegs) if allsegs else None
    nets = {}
    for net, pl in pads.items():
        if net in zone_nets or len(pl) < 3 or not tracks.get(net):
            continue
        tr = tracks[net]
        vs = vias.get(net, [])
        node_of = {}            # endpoint key -> node id
        deg = defaultdict(int)
        kind = {}
        uf = {}

        def find(a):
            while uf.setdefault(a, a) != a:
                uf[a] = uf[uf[a]]
                a = uf[a]
            return a

        def end_node(pt, layer, w):
            P = Point(pt)
            for i, (nm, poly, ls, _) in enumerate(pl):
                if layer in ls and poly.distance(P) <= TOL:
                    kind[("p", i)] = "pad"
                    return ("p", i)
            for i, v in enumerate(vs):
                if math.dist(pt, (v.x, v.y)) <= v.size / 2 + TOL:
                    kind[("v", i)] = "via"
                    return ("v", i)
            k = ("e", layer, round(pt[0] / TOL), round(pt[1] / TOL))
            kind[k] = "pt"
            return k
        segs = [(t, LineString([t.start, t.end])) for t in tr if t.start != t.end]
        length = sum(s.length for _, s in segs)
        for t, s in segs:
            for pt in (t.start, t.end):
                deg[end_node(pt, t.layer, t.width)] += 1
        # T: an end of one track on another's interior, same layer
        for t, s in segs:
            for pt in (t.start, t.end):
                P = Point(pt)
                for u, su in segs:
                    if u is t or u.layer != t.layer:
                        continue
                    if su.distance(P) <= u.width / 2 + TOL and math.dist(pt, u.start) > u.width / 2 + TOL \
                            and math.dist(pt, u.end) > u.width / 2 + TOL:
                        n = end_node(pt, t.layer, t.width)
                        if kind[n] == "pt":
                            deg[n] += 2
                        break
        branch = sum(1 for n, d in deg.items() if kind[n] != "pad" and d >= 3)
        thru = sum(1 for n, d in deg.items() if kind[n] == "pad" and d >= 2)
        xs = [c[0] for *_, c in pl]
        ys = [c[1] for *_, c in pl]
        bb = box(min(xs) - 1, min(ys) - 1, max(xs) + 1, max(ys) + 1)
        dens = 0.0
        if tree is not None:
            idx = tree.query(bb)
            dens = sum(allsegs[i].intersection(bb).length for i in idx) / bb.area
        nets[net] = dict(pads=len(pl), len=round(length, 2), vias=len(vs), branch=branch, thru=thru,
                         mst=round(mst_len([c for *_, c in pl]), 2), dens=round(dens, 3))
    return nets, pads


def pitch(fp):
    """The median nearest-neighbour distance of the footprint's signal pads (pads with a net,
    the largest pad, such as an exposed pad, left out)."""
    ps = [p for p in fp.pads if p.net]
    if len(ps) < 4:
        return math.inf
    big = max(ps, key=lambda p: p.size[0] * p.size[1])
    ps = [p for p in ps if p is not big] if big.size[0] * big.size[1] > 4 * min(p.size[0] * p.size[1] for p in ps) else ps
    nn = []
    for p in ps:
        d = min((math.dist((p.x, p.y), (q.x, q.y)) for q in ps if q is not p), default=math.inf)
        if d > 1e-3:
            nn.append(d)
    nn.sort()
    return nn[len(nn) // 2] if nn else math.inf


STEM = re.compile(r"^(.*?)(\d+)\]?$")


def buses(b):
    fps = {fp.ref: fp for fp in b.footprints}
    pit = {r: pitch(f) for r, f in fps.items() if len(f.pads) >= 4}
    zone_nets = {z.net for z in b.zones if z.net}
    netpads = defaultdict(list)
    for fp in b.footprints:
        for p in fp.pads:
            if p.net and p.net not in zone_nets:
                netpads[p.net].append((fp.ref, p))
    # adjacency buses between footprint pairs
    pair_nets = defaultdict(dict)       # (A, B) -> net -> (padA, padB)
    for net, lst in netpads.items():
        if len(lst) > 6:
            continue
        refs = defaultdict(list)
        for r, p in lst:
            refs[r].append(p)
        rs = sorted(refs)
        for i in range(len(rs)):
            for j in range(i + 1, len(rs)):
                a, c = rs[i], rs[j]
                pair_nets[(a, c)][net] = (refs[a][0], refs[c][0])
    adj_buses = []
    for (a, c), nm in pair_nets.items():
        if len(nm) < 4 or a not in pit or c not in pit:
            continue
        ns = sorted(nm)
        uf = {n: n for n in ns}

        def f(x):
            while uf[x] != x:
                uf[x] = uf[uf[x]]
                x = uf[x]
            return x
        for i in range(len(ns)):
            for j in range(i + 1, len(ns)):
                pa, pc = nm[ns[i]], nm[ns[j]]
                if math.dist((pa[0].x, pa[0].y), (pc[0].x, pc[0].y)) <= 1.6 * pit[a] and \
                        math.dist((pa[1].x, pa[1].y), (pc[1].x, pc[1].y)) <= 1.6 * pit[c]:
                    uf[f(ns[i])] = f(ns[j])
        comp = defaultdict(list)
        for n in ns:
            comp[f(n)].append(n)
        for g in comp.values():
            if len(g) >= 4:
                adj_buses.append(dict(ends=[a, c], nets=sorted(g), pitch=[round(pit[a], 3), round(pit[c], 3)]))
    # name groups
    groups = defaultdict(list)
    for net in netpads:
        short = net.rsplit("/", 1)[-1]
        m = STEM.match(short.replace("[", ""))
        if m and m.group(1):
            groups[m.group(1).upper()].append(net)
    name_buses = {k: sorted(v) for k, v in groups.items() if len(v) >= 4}
    return adj_buses, name_buses


if __name__ == "__main__":
    b = read(sys.argv[1])
    nets, _ = analyse(b)
    ab, nb = buses(b)
    out = dict(nets=nets, adj_buses=ab, name_buses=nb)
    if len(sys.argv) > 2:
        json.dump(out, open(sys.argv[2], "w"), indent=1)
    tot = defaultdict(float)
    for v in nets.values():
        for k in ("pads", "len", "vias", "branch", "thru", "mst"):
            tot[k] += v[k]
    print(len(nets), "nets", {k: round(v, 1) for k, v in tot.items()},
          "adj buses", [(x["ends"], len(x["nets"])) for x in ab], "name buses", {k: len(v) for k, v in nb.items()})
