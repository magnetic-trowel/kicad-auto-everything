# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Acid traps as etchant sees them: acute notches in the outline of each net's merged copper.

    python3 tools/research/routing/notch_stats.py BOARD.kicad_pcb [--json OUT]

Two centrelines meeting at a small angle say little: inside solid copper there is nothing to etch.
Here each net's copper on each layer (tracks and arcs at their widths, vias, pads, refilled zones) is
merged, and every concave vertex of the outline where the exposed wedge is acute is a candidate.

  gap angle   the wedge between the two sides, chords 20 um long from the vertex (< GAP_MAX degrees)
  depth       how far along both sides the wedge stays acute (walked in 5 um steps, up to 1 mm)
  counted     depth >= each of DEPTHS (50 um: about the copper's own etch-back at 1 oz; 100 um: a
              typical fab's minimum feature), and at least one track touches the vertex (a footprint's
              own outline is not routing)

Classes by what meets at the vertex: pad, fill, via (one of them and a track), or track-track, split
into width step (two widths), arc, same width. A fold is two tracks of a net and layer leaving a shared end
in the same direction (FOLD_DEG): copper going out and back over itself, never legitimate.
Sums per metre of track are the caller's (the report carries track_m)."""
from __future__ import annotations

import json
import math
import sys
import tempfile
from pathlib import Path

import numpy as np
import shapely
from shapely.geometry import LineString, Point
from shapely.geometry.polygon import orient
from shapely.ops import unary_union

GAP_MAX = 89.5          # degrees: below 90, so a square corner (exactly 90) is not counted through rounding
CHORD = 0.02
STEP = 0.005
MAX_DEPTH = 1.0
DEPTHS = (0.05, 0.1)
FOLD_DEG = 2.0
TOUCH = 0.003


def gap_angle(v, a, b):
    """Degrees between v->a and v->b."""
    ax, ay, bx, by = a[0] - v[0], a[1] - v[1], b[0] - v[0], b[1] - v[1]
    na, nb = math.hypot(ax, ay), math.hypot(bx, by)
    if na < 1e-9 or nb < 1e-9:
        return 180.0
    return math.degrees(math.acos(max(-1.0, min(1.0, (ax * bx + ay * by) / (na * nb)))))


def ring_notches(coords):
    """[(x, y, gap degrees, depth mm)] of the acute concave vertices of a ring whose copper lies on its left."""
    c = np.asarray(coords)[:-1, :2]
    n = len(c)
    if n < 4:
        return []
    u = c - np.roll(c, 1, axis=0)
    w = np.roll(c, -1, axis=0) - c
    cross = u[:, 0] * w[:, 1] - u[:, 1] * w[:, 0]
    dot = (u * w).sum(axis=1)
    turn = np.degrees(np.arctan2(cross, dot))
    cand = np.nonzero(turn < -20.0)[0]               # a right turn: copper's interior angle above 180
    if not len(cand):
        return []
    closed = np.vstack([c, c[:1]])
    d = np.r_[0.0, np.cumsum(np.hypot(*np.diff(closed, axis=0).T))]
    L = d[-1]

    def at(s):
        s = s % L
        return float(np.interp(s, d, closed[:, 0])), float(np.interp(s, d, closed[:, 1]))
    out = []
    for i in cand:
        v = tuple(c[i])
        s0 = d[i]
        if gap_angle(v, at(s0 - CHORD), at(s0 + CHORD)) >= GAP_MAX:
            continue
        depth = CHORD
        s = CHORD + STEP
        while s <= min(MAX_DEPTH, L / 2.0 - STEP) and gap_angle(v, at(s0 - s), at(s0 + s)) < GAP_MAX:
            depth = s
            s += STEP
        out.append((v[0], v[1], gap_angle(v, at(s0 - CHORD), at(s0 + CHORD)), depth))
    return out


def _far(leg, x, y):
    """The end of leg (.., t) away from (x, y), rounded as the node keys are."""
    t = leg[2]
    a, b = (round(t.start[0], 3), round(t.start[1], 3)), (round(t.end[0], 3), round(t.end[1], 3))
    return b if a == (x, y) else a


def analyse(board, fills=None):
    from kae.board import pcbnew_io
    from kae.board.kicad_file import load
    from kae.route import arcs as A
    from kae.route.constraints import _pad_shapes
    b = load(Path(board))
    with tempfile.TemporaryDirectory(prefix="kae-notch-") as d:
        info = pcbnew_io.export_dsn(Path(board), Path(d) / "board.dsn", probes=False)
    if fills is None:
        from kae.route.critical_recheck import fills_of
        fills = fills_of(Path(board))
    pads, tracks, vias = {}, {}, {}
    for pd in info.get("pads") or []:
        dsn, real = _pad_shapes(pd)
        for l in pd.get("layers") or []:
            g = real.get(l) or dsn
            if g is not None and not g.is_empty and pd.get("net"):
                pads.setdefault((pd["net"], l), []).append(g)
    length = 0.0
    ends = {}
    for t in b.tracks:
        if not t.net:
            continue
        cs = A.track_coords(t)
        if len(cs) < 2:
            continue
        L = A.track_length(t)
        length += L
        tracks.setdefault((t.net, t.layer), []).append((LineString(cs).buffer(t.width / 2, quad_segs=16), t, LineString(cs)))
        d0 = math.atan2(cs[1][1] - cs[0][1], cs[1][0] - cs[0][0])
        d1 = math.atan2(cs[-2][1] - cs[-1][1], cs[-2][0] - cs[-1][0])
        ends.setdefault((t.net, t.layer, round(cs[0][0], 3), round(cs[0][1], 3)), []).append((d0, L, t))
        ends.setdefault((t.net, t.layer, round(cs[-1][0], 3), round(cs[-1][1], 3)), []).append((d1, L, t))
    for v in b.vias:
        if v.net:
            for l in {x for n, x in tracks if n == v.net} or ():
                vias.setdefault((v.net, l), []).append(Point(v.x, v.y).buffer(v.size / 2, quad_segs=16))
    folds = []
    for (net, layer, x, y), its in ends.items():
        for i in range(len(its)):
            for j in range(i + 1, len(its)):
                dd = abs(math.degrees(math.remainder(its[i][0] - its[j][0], 2 * math.pi)))
                if dd < FOLD_DEG:
                    folds.append(dict(net=net, layer=layer, x=x, y=y, deg=round(dd, 2), n_at_node=len(its),
                                      lens=[round(its[i][1], 3), round(its[j][1], 3)],
                                      widths=[its[i][2].width, its[j][2].width], far=_far(its[i] if its[i][1] <= its[j][1] else its[j], x, y),
                                      arc=its[i][2].mid is not None or its[j][2].mid is not None))
    # a spike: the shorter leg's far end joins nothing (no other track, via or pad); the rest are overlaps
    # at a T or a pad (two branches along one line, inside the same copper)
    degree = {k: len(v) for k, v in ends.items()}
    via_at = {(v.net, round(v.x, 3), round(v.y, 3)) for v in b.vias}
    for f in folds:
        far = f.pop("far")
        f["spike"] = degree.get((f["net"], f["layer"], far[0], far[1]), 0) <= 1 and (f["net"], far[0], far[1]) not in via_at \
            and not any(g.distance(Point(far)) <= 1e-3 for g in pads.get((f["net"], f["layer"]), ()))
    notches = []
    for (net, layer), ts in tracks.items():
        fill = [g for g in ((fills.get(net) or {}).get(layer) or [])]
        ps, vs = pads.get((net, layer), []), vias.get((net, layer), [])
        u = unary_union([x[0] for x in ts] + ps + vs + fill)
        if u.is_empty:
            continue
        tree = shapely.STRtree([x[0] for x in ts])
        for poly in getattr(u, "geoms", [u]):
            if poly.geom_type != "Polygon":
                continue
            poly = orient(poly, 1.0)                 # exterior counter-clockwise, holes clockwise: copper on the left
            for ring in [poly.exterior, *poly.interiors]:
                seen = []
                for x, y, gap, depth in ring_notches(ring.coords):
                    if depth < min(DEPTHS) or any(math.hypot(x - a, y - b) < CHORD for a, b in seen):
                        continue
                    p = Point(x, y)
                    touch = [ts[int(k)][1] for k in tree.query(p.buffer(TOUCH))
                             if ts[int(k)][0].exterior.distance(p) <= TOUCH or ts[int(k)][0].distance(p) <= TOUCH]
                    if not touch:
                        continue
                    seen.append((x, y))
                    def near(gs):
                        return any(g.distance(p) <= TOUCH for g in gs)
                    widths = {round(t.width, 3) for t in touch}
                    if near(ps):
                        kind = "pad"
                    elif near(fill):
                        kind = "fill"
                    elif near(vs):
                        kind = "via"
                    elif len(touch) < 2:
                        kind = "track-self"           # the inside of one arc or a sliver of one track
                    elif len(widths) > 1:
                        kind = "track-widthstep"
                    elif any(t.mid is not None for t in touch):
                        kind = "track-arc"
                    else:
                        kind = "track-same"
                    notches.append(dict(net=net, layer=layer, x=round(x, 3), y=round(y, 3), gap=round(gap, 1),
                                        depth=round(depth, 3), kind=kind, widths=sorted(widths), n_tracks=len(touch),
                                        wide=max(widths) >= 0.4))
    by = {}
    for d_ in DEPTHS:
        c = {}
        for n in notches:
            if n["depth"] >= d_:
                c[n["kind"]] = c.get(n["kind"], 0) + 1
        by[str(d_)] = dict(total=sum(c.values()), kinds=c, wide=sum(1 for n in notches if n["depth"] >= d_ and n["wide"]),
                           below80=sum(1 for n in notches if n["depth"] >= d_ and n["gap"] < 80.0))
    micro = sum(1 for f in folds if min(f["lens"]) < 0.01)
    spikes = sum(1 for f in folds if f["spike"] and min(f["lens"]) >= 0.01)
    return dict(track_m=round(length / 1000.0, 3), notches=by, folds=len(folds), fold_micro=micro, fold_spikes=spikes,
                fold_overlap=len(folds) - micro - spikes, notch_list=notches, fold_list=folds)


def main(argv):
    rep = analyse(argv[0])
    if "--json" in argv:
        Path(argv[argv.index("--json") + 1]).write_text(json.dumps(rep))
    print(json.dumps({k: v for k, v in rep.items() if not k.endswith("_list")}))


if __name__ == "__main__":
    main(sys.argv[1:])
