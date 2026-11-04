# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Arc tracks: geometry, exact clearance checks and KiCad output.

An arc is kept as (centre, radius, start angle, signed sweep) for computing and written as
KiCad's (arc (start) (mid) (end)) (`arc_sexpr`). kae's board model holds an arc as a Track with
`mid` set; `from_track` turns one back into centre form.

Exact checks: an arc is sampled with vertices on the true circle and a chord sagitta of at most
`SAG` (0.2 um). The chords lie inside the circle, so an obstacle on the arc's convex side is up
to SAG nearer the true arc than the polyline: every requirement is raised by SAG
(`polyline_violations`), which makes the check exact to the 2 um margin kae keeps everywhere
(critical_space.TOL).
"""
from __future__ import annotations

import math

import numpy as np
import shapely
from shapely.geometry import LineString, Point

from . import critical_write as W

SAG = 2e-4            # mm: chord sagitta of sampled arcs
MIN_SWEEP = 0.02      # rad: a narrower arc is written as its chord (its sagitta is < 0.02 um at r = 1 mm;
                      # KiCad recomputes the centre from nm-rounded points, ill-conditioned for tiny sweeps)


def norm_angle(a):
    """a in (-pi, pi]."""
    a = math.fmod(a, 2 * math.pi)
    if a <= -math.pi:
        a += 2 * math.pi
    elif a > math.pi:
        a -= 2 * math.pi
    return a


def point_at(c, r, a):
    return (c[0] + r * math.cos(a), c[1] + r * math.sin(a))


def csa_to_sme(c, r, a0, sweep):
    """(start, mid, end) of the arc of circle (c, r) from angle a0 sweeping `sweep` (signed, rad)."""
    return point_at(c, r, a0), point_at(c, r, a0 + sweep / 2), point_at(c, r, a0 + sweep)


def circle_through(s, m, e):
    """(centre, radius) of the circle through s, m, e; None when they are collinear."""
    (x1, y1), (x2, y2), (x3, y3) = s, m, e
    d = 2.0 * (x1 * (y2 - y3) + x2 * (y3 - y1) + x3 * (y1 - y2))
    if abs(d) < 1e-14:
        return None
    a1, a2, a3 = x1 * x1 + y1 * y1, x2 * x2 + y2 * y2, x3 * x3 + y3 * y3
    c = ((a1 * (y2 - y3) + a2 * (y3 - y1) + a3 * (y1 - y2)) / d,
         (a1 * (x3 - x2) + a2 * (x1 - x3) + a3 * (x2 - x1)) / d)
    return c, math.hypot(s[0] - c[0], s[1] - c[1])


def sme_to_csa(s, m, e):
    """(centre, radius, a0, sweep) of the arc start -> mid -> end; None when collinear."""
    got = circle_through(s, m, e)
    if got is None:
        return None
    c, r = got
    a0 = math.atan2(s[1] - c[1], s[0] - c[0])
    am = math.atan2(m[1] - c[1], m[0] - c[0])
    a1 = math.atan2(e[1] - c[1], e[0] - c[0])
    # s -> m -> e turns left on a counter-clockwise (positive sweep) arc
    ccw = ((m[0] - s[0]) * (e[1] - s[1]) - (m[1] - s[1]) * (e[0] - s[0])) > 0
    sw = (a1 - a0) % (2 * math.pi)
    if not ccw:
        sw = sw - 2 * math.pi
    # check that m lies on the chosen side
    mid_a = a0 + sw / 2
    if math.hypot(math.cos(mid_a) - math.cos(am), math.sin(mid_a) - math.sin(am)) > 1e-3:
        sw = (sw - 2 * math.pi) if sw > 0 else (sw + 2 * math.pi)
    return c, r, a0, sw


def arc_length(r, sweep):
    return abs(r * sweep)


def nseg(r, sweep, sag=SAG):
    if r <= sag:
        return 1
    half = math.acos(max(-1.0, 1.0 - sag / r))
    return max(1, int(math.ceil(abs(sweep) / (2.0 * half) - 1e-9)))


def arc_coords(c, r, a0, sweep, sag=SAG):
    """Points on the arc, ends exact, chord sagitta <= sag."""
    n = nseg(r, sweep, sag)
    t = a0 + sweep * np.linspace(0.0, 1.0, n + 1)
    pts = np.c_[c[0] + r * np.cos(t), c[1] + r * np.sin(t)]
    return [tuple(p) for p in pts]


def track_coords(t, sag=SAG):
    """Centreline points of a kae Track (segment or arc)."""
    if t.mid is None:
        return [tuple(t.start), tuple(t.end)]
    got = sme_to_csa(t.start, t.mid, t.end)
    if got is None:
        return [tuple(t.start), tuple(t.end)]
    c, r, a0, sw = got
    pts = arc_coords(c, r, a0, sw, sag)
    pts[0], pts[-1] = tuple(t.start), tuple(t.end)
    return pts


def track_length(t):
    if t.mid is None:
        return math.dist(t.start, t.end)
    got = sme_to_csa(t.start, t.mid, t.end)
    return math.dist(t.start, t.end) if got is None else arc_length(got[1], got[3])


def arc_sexpr(net, layer, width, s, m, e, uid=None, locked=False):
    """A KiCad 8-10 (arc ...) track."""
    lk = "\t\t(locked yes)\n" if locked else ""
    f = W.fmt
    return (f"\t(arc\n\t\t(start {f(s[0])} {f(s[1])})\n\t\t(mid {f(m[0])} {f(m[1])})\n\t\t(end {f(e[0])} {f(e[1])})\n"
            f"\t\t(width {f(width)})\n{lk}\t\t(layer {W.q(layer)})\n\t\t(net {W.q(net)})\n"
            f"\t\t(uuid {W.q(uid or W.new_uuid())})\n\t)\n")


def fix_space_arcs(sp, tracks):
    """Replace the 3-point chords critical_space.Space keeps for existing arc tracks by the sampled
    arc (the chords lie up to r(1 - cos(sweep/4)) inside it)."""
    arcs = {t.uuid: t for t in tracks if t.mid is not None}
    if not arcs:
        return 0
    n = 0
    for it in sp.existing:
        t = arcs.get(it.uuid)
        if it.kind != "track" or t is None:
            continue
        it.geom = LineString(track_coords(t))
        x0, y0, x1, y1 = it.geom.bounds
        it.bbox = (x0 - it.r, y0 - it.r, x1 + it.r, y1 + it.r)
        n += 1
    sp.invalidate()
    return n


def polyline_violations(sp, net, layer, w, coords, ignore=(), first=False, tol=None, sag=SAG):
    """critical_space.Space.track_violations for a polyline centreline (a sampled arc): every
    requirement raised by `sag`."""
    from .critical_space import TOL
    tol = TOL if tol is None else tol
    TOLs = tol + sag
    out = []
    seg = LineString(coords) if len(coords) > 1 else Point(coords[0])
    half = w / 2.0
    x0, y0, x1, y1 = seg.bounds
    reach = half + sp.max_need + TOLs
    for it in sp.query(layer, (x0, y0, x1, y1), reach):
        if it in ignore:
            continue
        nd = sp.need(it, net, "track", layer)
        if nd is None:
            continue
        d = sp._dist(it, seg) - half
        if d < nd + TOLs:
            if it.kind in ("keepout", "corridor") and d >= 0:
                if d > TOLs:
                    continue
            out.append((it, d, nd))
            if first:
                return out
    if sp.outline is not None:
        e = sp.edge_need(net, "track", layer)
        if not sp.outline.contains(seg):
            out.append(("edge", -1.0, e))
        else:
            d = sp.outline_boundary.distance(seg) - half
            if d < e + TOLs:
                out.append(("edge", d, e))
    return out


def pieces_coords(pieces, sag=SAG):
    """Centreline points of a list of pieces ('seg', a, b) / ('arc', c, r, a0, sweep)."""
    out = []
    for p in pieces:
        pts = [p[1], p[2]] if p[0] == "seg" else arc_coords(p[1], p[2], p[3], p[4], sag)
        if out and math.dist(out[-1], pts[0]) < 1e-9:
            pts = pts[1:]
        out.extend(pts)
    return out


def piece_coords(p, sag=SAG):
    return [p[1], p[2]] if p[0] == "seg" else arc_coords(p[1], p[2], p[3], p[4], sag)


def piece_length(p):
    return math.dist(p[1], p[2]) if p[0] == "seg" else arc_length(p[2], p[4])


def piece_ends(p):
    if p[0] == "seg":
        return p[1], p[2]
    return point_at(p[1], p[2], p[3]), point_at(p[1], p[2], p[3] + p[4])


def shapely_arc(c, r, a0, sweep, sag=SAG):
    return LineString(arc_coords(c, r, a0, sweep, sag))
