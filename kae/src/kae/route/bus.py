# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Buses: groups of signal nets that leave one part side by side and arrive at another side by
side, and the order Freerouting routes them in.

A bus here is found from pin adjacency alone (no names): >= MIN_LINES nets of at most
MAX_PADS pads each that join the same two parts (each with >= 4 signal pads) by pads that are
neighbours on both, within 1.6 x the part's pad pitch (the median nearest-neighbour distance of
its signal pads). Names (D0..D23) would find the same groups on the boards that have them and
miss unnamed ones (Net-(U1-Pad12)).

Freerouting routes the open items in the order of their net numbers (the fork's
AutoroutePassRunner.reorderSingleThreadItems: sorted by net number, then item id), and the net
numbers follow the DSN network. translate.permute shuffles that order per seed, which routes a
bus's lines in a random order: a middle line routed last finds its neighbours' tracks already
across its escape. `order(tree, buses)` puts each bus's nets next to each other in pin order
(dense end), at the place of its first net in the current order, so the lines route one after
another and each hugs the one before, as river routing does.
"""
from __future__ import annotations

import math
import re
from collections import defaultdict

MIN_LINES = 4
MAX_PADS = 6


def _pitch(pts):
    nn = []
    for i, a in enumerate(pts):
        d = min((math.dist(a, b) for j, b in enumerate(pts) if j != i), default=math.inf)
        if d > 1e-3:
            nn.append(d)
    nn.sort()
    return nn[len(nn) // 2] if nn else math.inf


def _natural(s):
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", str(s))]


def find(pads, skip_nets=()):
    """Buses among `pads` (route_info pads: ref, number, net, pos) -> [[net, ...]] in pin order
    of the end with the finer pitch; each net in one bus at most (the largest)."""
    skip = set(skip_nets)
    by_ref = defaultdict(list)
    by_net = defaultdict(list)
    for p in pads:
        if p.get("net"):
            by_ref[p["ref"]].append(p)
            if p["net"] not in skip:
                by_net[p["net"]].append(p)
    pitch = {}
    for ref, ps in by_ref.items():
        if len(ps) >= 4:
            pts = [tuple(p["pos"]) for p in ps]
            pitch[ref] = _pitch(pts)
    pairs = defaultdict(dict)               # (ref a, ref b) -> net -> (pad on a, pad on b)
    for net, ps in by_net.items():
        if len(ps) > MAX_PADS:
            continue
        first = {}
        for p in ps:
            first.setdefault(p["ref"], p)
        refs = sorted(r for r in first if r in pitch)
        for i in range(len(refs)):
            for j in range(i + 1, len(refs)):
                pairs[(refs[i], refs[j])][net] = (first[refs[i]], first[refs[j]])
    found = []
    for (a, b), nets in pairs.items():
        if len(nets) < MIN_LINES:
            continue
        ns = sorted(nets)
        parent = {n: n for n in ns}

        def root(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x
        for i in range(len(ns)):
            pa = nets[ns[i]]
            for j in range(i + 1, len(ns)):
                pb = nets[ns[j]]
                if math.dist(pa[0]["pos"], pb[0]["pos"]) <= 1.6 * pitch[a] and \
                        math.dist(pa[1]["pos"], pb[1]["pos"]) <= 1.6 * pitch[b]:
                    parent[root(ns[i])] = root(ns[j])
        comp = defaultdict(list)
        for n in ns:
            comp[root(n)].append(n)
        k = 0 if pitch[a] <= pitch[b] else 1
        for g in comp.values():
            if len(g) >= MIN_LINES:
                found.append(sorted(g, key=lambda n: _natural(nets[n][k]["number"])))
    found.sort(key=lambda g: (-len(g), g))
    taken, out = set(), []
    for g in found:
        g = [n for n in g if n not in taken]
        if len(g) >= MIN_LINES:
            out.append(g)
            taken |= set(g)
    return out


def order(tree, buses):
    """Reorder the `net` nodes of the DSN `tree`'s network so each bus's nets are consecutive,
    in bus order, where its first net was. Returns the number of nets moved."""
    from .translate import find as tfind
    network = tfind(tree, "network")
    if network is None or not buses:
        return 0
    idx = [i for i, c in enumerate(network) if isinstance(c, list) and c and c[0] == "net"]
    nodes = [network[i] for i in idx]
    name = [str(c[1]) if len(c) > 1 else "" for c in nodes]
    bus_of = {}
    for k, g in enumerate(buses):
        for r, n in enumerate(g):
            bus_of[n] = (k, r)
    seq, placed = [], set()
    pos = {n: i for i, n in enumerate(name)}
    for i, n in enumerate(name):
        if n in bus_of:
            k = bus_of[n][0]
            if k not in placed:
                placed.add(k)
                seq += [pos[m] for m in buses[k] if m in pos]
        else:
            seq.append(i)
    moved = sum(1 for a, b in zip(seq, range(len(seq))) if a != b)
    for i, j in zip(idx, seq):
        network[i] = nodes[j]
    return moved


FIELD_PITCH = 0.65      # a perimeter package at this pitch or finer has a pin field
FIELD_PADS = 16


def pin_fields(pads, poly=None):
    """The pin fields of fine-pitch perimeter packages (QFN, QFP, SON; not ball grids) in
    `pads` (route_info pads) -> [(ref, polygon)]: the convex hull of the pad centres, without
    the exposed pad (a pad > 4 x the median pad area) grown by half the pitch.

    On the human boards these are almost free of vias of the pins' nets: every pin escapes
    outwards (tools/research/routing/close-topology/infield.py). Freerouting's maze takes the
    short way in under the package, and the via it leaves there walls in the next pins
    (kata0510 rp2040-8key: 8 such vias in the RP2040's field, the human 2)."""
    from shapely.geometry import LineString, MultiPoint, Point
    from shapely.ops import unary_union

    def copper(p):
        polys = p.get("poly") or next(iter((p.get("poly_by_layer") or {}).values()), None) or []
        gs = [g for g in (poly(r) for r in polys) if g is not None] if poly else []
        return unary_union(gs) if gs else None
    by_ref = defaultdict(list)
    for p in pads:
        if p.get("layers"):
            by_ref[p["ref"]].append(p)
    out = []
    for ref, ps in by_ref.items():
        if len(ps) < FIELD_PADS:
            continue
        geos = [copper(p) for p in ps]
        areas = [g.area if g is not None else 0.0 for g in geos]
        med = sorted(areas)[len(areas) // 2]
        ep_nums = {p["number"] for p, a in zip(ps, areas) if med > 0 and a > 4 * med}
        ep = [g for p, g in zip(ps, geos) if p["number"] in ep_nums and g is not None]
        small = [p for p in ps if p["number"] not in ep_nums and not p.get("hole")]
        if len(small) < FIELD_PADS:
            continue
        pts = [tuple(p["pos"]) for p in small]
        pitch = _pitch(pts)
        if pitch > FIELD_PITCH:
            continue
        hull = MultiPoint(pts).convex_hull
        inner = hull.buffer(-2 * pitch)
        if inner.is_empty or any(inner.contains(Point(x)) for x in pts):
            continue                     # a grid: pads inside, the dog-bones' business
        # pads along all four sides (QFN, QFP), or two rows round an exposed pad (SON);
        # two rows alone are a connector, where vias between the rows are common
        rect = hull.minimum_rotated_rectangle
        c = list(rect.exterior.coords)[:4]
        sides = sum(1 for k in range(4)
                    if sum(1 for x in pts if LineString([c[k], c[(k + 1) % 4]]).distance(Point(x)) < pitch) >= 2)
        if sides < 4 and not (sides >= 2 and ep):
            continue
        geo = hull
        for g in ep:
            geo = geo.difference(g.buffer(pitch / 2))
        if not geo.is_empty:
            out.append((ref, geo))
    return out
