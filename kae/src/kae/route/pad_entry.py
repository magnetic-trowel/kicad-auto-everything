# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Where a track meets a pad: at the edge it approaches from, not at the pad's centre.

A connection's target is the pad's copper, not its centre point. `entries` says where a track
coming from a point outside the pad should end and how it should cross the edge:

- **The edge.** The pad edge nearest the approach point. On a straight edge at least as long as
  the track is wide, the crossing is the approach point's foot on that edge, kept a half width
  from the edge's ends, so the whole track width lands on one edge (no notch across a corner).
  It is the edge's middle when `centred` (current-carrying copper; small two-terminal lands, so
  both lands of a part see the same joint). On a round pad, or an edge shorter than the track
  width, the track runs radially toward the centre (perpendicular to a circle).
- **Perpendicular, not acute.** A track that crosses an edge at an angle leaves an acute wedge
  between its side and the pad edge: an acid trap where etchant pools (IPC-2221 and fab DFM
  guides flag acute copper angles; docs/topics/rules/rf.md, autorouter-skepticism.md "acute
  angles"). The first candidate therefore turns onto the edge normal `stub` before the edge
  (at least the track width, so the bend's outer corner stays off the pad) and runs straight in.
  A direct piece is offered second, only when it is within `max_angle` of the normal.
- **Overlap.** The end lies `depth` inside the edge along the track's axis: at least
  `pad_entry_overlap` (constraints.DEFAULTS, the same setting the rim entries of
  critical_grid._escapes use), and at least the track width for current-carrying copper, whose
  joint an edge entry would otherwise halve. An end that would pass the pad's centre, or whose
  round end would poke out of the far side, is no edge entry: the caller keeps the centre.

The caller checks each candidate piece exactly (Space.track_violations) and falls back to the
centre when none is legal. Nothing here knows the board; it is plane geometry on shapely shapes.
"""
from __future__ import annotations

import math
import re

from shapely.geometry import LineString, Point

MODES = ("centre", "edge")
MAX_ANGLE = 20.0          # degrees off the edge normal a direct piece may enter at
EPS = 1e-6

# rails and grounds: their joints carry current (kae.physics.provisional_brief's name rules)
GND_RE = re.compile(r'(^|[^A-Z])(A|D|P|S|C)?GND|^/?VSS|^0V$|GROUND|EARTH', re.I)
PWR_RE = re.compile(r'^/?(\+?\d+(\.\d+)?V\d*|\+[A-Z0-9_.]+|V(CC|DD|BUS|IN|SYS|BAT|MOT|M|PP|REG|CORE|CAP|S)[A-Z0-9_.]*|'
                    r'[AD]V(DD|CC)[A-Z0-9_]*|\d+V\d+|[0-9]+V[0-9]*_?[A-Z]*)$', re.I)


def current_net(net):
    """Whether a net's name says it is a rail or a ground."""
    name = (net or "").rsplit("/", 1)[-1]
    return bool(name) and bool(GND_RE.search(name) or PWR_RE.match(name))


def _unit(dx, dy):
    n = math.hypot(dx, dy)
    return (dx / n, dy / n) if n > EPS else None


def _ring(pad):
    g = pad if pad.geom_type == "Polygon" else max(getattr(pad, "geoms", [pad]), key=lambda x: x.area)
    return g, list(g.exterior.coords)


def nearest_edge(pad, p):
    """(a, b, foot) of the pad's boundary segment nearest point p, and p's nearest point on it.
    Where several are as near (p faces a corner), the one p lies most squarely in front of."""
    g, pts = _ring(pad)
    found = []
    P = Point(p)
    for a, b in zip(pts[:-1], pts[1:]):
        if math.dist(a, b) < EPS:
            continue
        seg = LineString([a, b])
        f = seg.interpolate(seg.project(P))
        found.append((seg.distance(P), a, b, (f.x, f.y)))
    if not found:
        return None
    d0 = min(x[0] for x in found)
    near = [x for x in found if x[0] <= d0 + 1e-9]

    def square(x):
        t = _unit(x[2][0] - x[1][0], x[2][1] - x[1][1])
        return abs((p[0] - x[3][0]) * t[1] - (p[1] - x[3][1]) * t[0])
    return max(near, key=square)[1:]


def _inward(pad, a, b):
    """Unit normal of edge a-b pointing into the pad."""
    t = _unit(b[0] - a[0], b[1] - a[1])
    n = (-t[1], t[0])
    m = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
    h = 1e-4
    if pad.contains(Point(m[0] + h * n[0], m[1] + h * n[1])):
        return n
    return (-n[0], -n[1])


def crossing(pad, p, q):
    """The first point where the segment p (outside) -> q (inside) enters the pad, or None."""
    seg = LineString([p, q])
    x = seg.intersection(pad.boundary)
    if x.is_empty:
        return None
    pts = [(c[0], c[1]) for g in getattr(x, "geoms", [x]) for c in g.coords]
    return min(pts, key=lambda c: math.dist(c, p)) if pts else None


def entry(pad, centre, p, width, overlap, centred=False, current=False):
    """Where a track of `width` from p (outside `pad`) should end: (e, u, end), with e the
    crossing on the pad edge, u the unit direction the track enters along, end = e + depth u.
    None when p is inside the pad or no edge entry fits (the caller keeps the centre)."""
    P = Point(p)
    if pad.is_empty or pad.contains(P):
        return None
    depth = max(overlap, width if current else 0.0, EPS)
    ne = nearest_edge(pad, p)
    if ne is None:
        return None
    a, b, foot = ne
    L = math.dist(a, b)
    if L + EPS >= width:
        t = _unit(b[0] - a[0], b[1] - a[1])
        u = _inward(pad, a, b)
        if centred or current:
            s = L / 2
        else:
            s = (foot[0] - a[0]) * t[0] + (foot[1] - a[1]) * t[1]
            s = min(max(s, width / 2), L - width / 2)
        e = (a[0] + s * t[0], a[1] + s * t[1])
    else:
        # round pad or short edge: radially toward the centre
        u = _unit(centre[0] - p[0], centre[1] - p[1])
        if u is None:
            return None
        e = crossing(pad, p, centre)
        if e is None:
            return None
    end = (e[0] + depth * u[0], e[1] + depth * u[1])
    # past the centre (along u) the centre itself is the better end
    if (centre[0] - e[0]) * u[0] + (centre[1] - e[1]) * u[1] < depth - EPS:
        return None
    if not pad.buffer(EPS).contains(Point(end)):
        return None
    # the round end must not poke out of the far side of the pad
    tip = (end[0] + width / 2 * u[0], end[1] + width / 2 * u[1])
    if not pad.buffer(EPS).contains(Point(tip)):
        return None
    return e, u, end


def entries(pad, centre, p, width, overlap, centred=False, current=False, max_angle=MAX_ANGLE, stub=None):
    """Candidate tails from p into the pad, best first: lists of points to append after p
    (perpendicular: [s, end], s the turn onto the edge normal `stub` before the edge; direct:
    [end] when p -> end is within `max_angle` of the normal). [] when no edge entry fits."""
    got = entry(pad, centre, p, width, overlap, centred=centred, current=current)
    if got is None:
        return []
    e, u, end = got
    stub = max(width, 0.1) if stub is None else stub
    out = []
    d = _unit(end[0] - p[0], end[1] - p[1])
    ang = math.degrees(math.acos(max(-1.0, min(1.0, d[0] * u[0] + d[1] * u[1])))) if d else 180.0
    if ang <= 1.0:
        return [[end]]
    s = (e[0] - stub * u[0], e[1] - stub * u[1])
    if not pad.contains(Point(s)) and math.dist(p, s) > EPS:
        out.append([s, end])
    if ang <= max_angle:
        out.append([end])
    return out


def entry_angle(pad, a, b):
    """Angle (degrees) between a track piece a -> b that ends in or on the pad and the pad edge's
    normal where it crosses: 0 = perpendicular. None if the piece does not cross the edge."""
    if pad.contains(Point(a)):
        a, b = b, a
    if pad.contains(Point(a)) or not pad.buffer(1e-4).contains(Point(b)):
        return None
    x = crossing(pad, a, b)
    if x is None:
        x = b
    ne = nearest_edge(pad, x)
    if ne is None:
        return None
    ea, eb, _ = ne
    if math.dist(ea, eb) < 1e-3:
        return None
    n = _inward(pad, ea, eb)
    d = _unit(b[0] - a[0], b[1] - a[1])
    if d is None:
        return None
    return math.degrees(math.acos(max(-1.0, min(1.0, abs(d[0] * n[0] + d[1] * n[1])))))
