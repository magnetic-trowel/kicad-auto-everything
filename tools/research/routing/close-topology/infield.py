# SPDX-License-Identifier: GPL-3.0-or-later
"""Copper of foreign nets inside the pin field of fine-pitch perimeter packages (QFN, QFP, SON).

usage: infield.py <board.kicad_pcb[.gz]> [out.json]

For each footprint with >= 16 signal pads at a pitch <= 0.65 mm whose pads are not a grid
(perimeter rows): the pin field is the convex hull of its signal pad centres. Counted inside it:
vias of nets with no pad on the part ("foreign"), vias of the exposed pad's net (own), vias of its other pins' nets (pin), and the length
of foreign tracks per layer (the part's side and the other).
"""
import json, sys
from collections import defaultdict

from shapely.geometry import LineString, MultiPoint, Point

import topo


def fields(b):
    out = []
    for fp in b.footprints:
        ps = [p for p in fp.pads if p.net]
        if len(ps) < 16:
            continue
        pitch = topo.pitch(fp)
        if pitch > 0.65:
            continue
        big = max(ps, key=lambda p: p.size[0] * p.size[1])
        small = [p for p in ps if p is not big] if big.size[0] * big.size[1] > 4 * min(p.size[0] * p.size[1] for p in ps) else ps
        hull = MultiPoint([(p.x, p.y) for p in small]).convex_hull
        # a grid (ball array) has pads inside its hull's interior, a perimeter package none
        inner = hull.buffer(-2 * pitch)
        if inner.is_empty or any(inner.contains(Point(p.x, p.y)) for p in small):
            continue
        out.append((fp, hull, {p.net for p in fp.pads if p.net}, pitch, big.net if len(small) < len(ps) else None))
    return out


def count(b):
    side_cu = lambda fp: "F.Cu" if fp.side == "F" else "B.Cu"
    res = []
    for fp, hull, own, pitch, ep in fields(b):
        r = dict(ref=fp.ref, pitch=round(pitch, 3), pads=len(fp.pads), area=round(hull.area, 1),
                 foreign_vias=0, own_vias=0, pin_vias=0, foreign_len_side=0.0, foreign_len_other=0.0)
        for v in b.vias:
            if hull.contains(Point(v.x, v.y)):
                r["foreign_vias" if v.net not in own else "own_vias" if v.net == ep else "pin_vias"] += 1
        for t in b.tracks:
            if t.net in own or t.start == t.end:
                continue
            seg = LineString([t.start, t.end])
            if not seg.intersects(hull):
                continue
            L = seg.intersection(hull).length
            r["foreign_len_side" if t.layer == side_cu(fp) else "foreign_len_other"] += round(L, 2)
        res.append(r)
    return res


if __name__ == "__main__":
    b = topo.read(sys.argv[1])
    r = count(b)
    if len(sys.argv) > 2:
        json.dump(r, open(sys.argv[2], "w"))
    for x in r:
        print(x)
