# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Geometry helpers for KiCad graphics: arcs, circles, Beziers, and outlines chained into
polygons with holes (Edge.Cuts, courtyards).

Arcs are polygonized with vertices on the true arc and a chord error <= `tol` (mm).
`polygons(opens, rings, eps)` follows KiCad's ConvertOutlineToPolygon in effect: open
pieces whose endpoints meet within `eps` are chained into closed loops, and loops nest
by the even-odd rule (a loop inside one loop is a hole, inside two an island).
"""
import math

import shapely
from shapely.geometry import LineString, Polygon
from shapely.ops import polygonize, unary_union

ARC_TOL = 0.001  # mm; KiCad itself uses the board's max_error (default 0.005 mm)


def _nseg(r, sweep, tol):
    if r <= tol:
        return 1
    half = math.acos(max(-1.0, 1.0 - tol / r))
    return max(1, int(math.ceil(abs(sweep) / (2.0 * half) - 1e-9)))


def circle_center(s, m, e):
    """Center of the circle through three points, or None if they are collinear."""
    (x1, y1), (x2, y2), (x3, y3) = s, m, e
    d = 2.0 * (x1 * (y2 - y3) + x2 * (y3 - y1) + x3 * (y1 - y2))
    if abs(d) < 1e-15:
        return None
    a1, a2, a3 = x1 * x1 + y1 * y1, x2 * x2 + y2 * y2, x3 * x3 + y3 * y3
    return ((a1 * (y2 - y3) + a2 * (y3 - y1) + a3 * (y1 - y2)) / d,
            (a1 * (x3 - x2) + a2 * (x1 - x3) + a3 * (x2 - x1)) / d)


def arc_points(s, m, e, tol=ARC_TOL):
    """Polyline from s through m to e on their circle; s and e are kept exactly."""
    c = circle_center(s, m, e)
    if c is None:
        return [tuple(s), tuple(e)]
    ux, uy = c
    r = math.hypot(s[0] - ux, s[1] - uy)
    a1 = math.atan2(s[1] - uy, s[0] - ux)
    a2 = math.atan2(m[1] - uy, m[0] - ux)
    a3 = math.atan2(e[1] - uy, e[0] - ux)
    two_pi = 2.0 * math.pi
    span = (a3 - a1) % two_pi
    if (a2 - a1) % two_pi > span:  # the mid point is on the other way round
        span -= two_pi
    if abs(span) < 1e-12:  # start == end: a full circle through m
        span = two_pi if (a2 - a1) % two_pi < math.pi else -two_pi
    n = _nseg(r, span, tol)
    pts = [tuple(s)]
    for i in range(1, n):
        a = a1 + span * i / n
        pts.append((ux + r * math.cos(a), uy + r * math.sin(a)))
    pts.append(tuple(e))
    return pts


def arc_center_points(c, p, angle_deg, tol=ARC_TOL):
    """KiCad 5 arcs: center c, start p, sweep angle (degrees, clockwise on screen when
    positive, i.e. counter-clockwise in y-down math)."""
    r = math.hypot(p[0] - c[0], p[1] - c[1])
    a1 = math.atan2(p[1] - c[1], p[0] - c[0])
    span = math.radians(angle_deg)
    n = _nseg(r, span, tol)
    return [(c[0] + r * math.cos(a1 + span * i / n), c[1] + r * math.sin(a1 + span * i / n))
            for i in range(n + 1)]


def circle_points(c, r, tol=ARC_TOL):
    """Closed ring (first point repeated) with vertices on the circle."""
    n = max(8, _nseg(r, 2.0 * math.pi, tol))
    pts = [(c[0] + r * math.cos(2.0 * math.pi * i / n), c[1] + r * math.sin(2.0 * math.pi * i / n))
           for i in range(n)]
    pts.append(pts[0])
    return pts


def bezier_points(p0, p1, p2, p3, tol=ARC_TOL):
    """Cubic Bezier as a polyline (uniform in t, enough segments for `tol`)."""
    # control-polygon length bounds the curve length; flatness bound for the count
    dd = max(math.hypot(p0[0] - 2 * p1[0] + p2[0], p0[1] - 2 * p1[1] + p2[1]),
             math.hypot(p1[0] - 2 * p2[0] + p3[0], p1[1] - 2 * p2[1] + p3[1]))
    n = max(2, min(1000, int(math.ceil(math.sqrt(0.75 * dd / max(tol, 1e-9))))))
    pts = []
    for i in range(n + 1):
        t = i / n
        a, b, c, d = (1 - t) ** 3, 3 * (1 - t) ** 2 * t, 3 * (1 - t) * t * t, t ** 3
        pts.append((a * p0[0] + b * p1[0] + c * p2[0] + d * p3[0],
                    a * p0[1] + b * p1[1] + c * p2[1] + d * p3[1]))
    pts[0], pts[-1] = tuple(p0), tuple(p3)
    return pts


def _snap(opens, eps):
    """Make endpoints within eps identical (union of nearby endpoints on a hash grid)."""
    if eps <= 0 or not opens:
        return opens
    ends = []
    for k, pl in enumerate(opens):
        ends.append((k, 0, pl[0]))
        ends.append((k, -1, pl[-1]))
    parent = list(range(len(ends)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    grid = {}
    for i, (_, _, p) in enumerate(ends):
        gx, gy = int(math.floor(p[0] / eps)), int(math.floor(p[1] / eps))
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for j in grid.get((gx + dx, gy + dy), ()):
                    q = ends[j][2]
                    if (p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2 <= eps * eps:
                        ri, rj = find(i), find(j)
                        if ri != rj:
                            parent[max(ri, rj)] = min(ri, rj)
        grid.setdefault((gx, gy), []).append(i)
    out = [list(pl) for pl in opens]
    for i, (k, w, _) in enumerate(ends):
        out[k][w] = ends[find(i)][2]
    return out


def _chain_simple(opens):
    """Join open polylines into closed rings when every endpoint has exactly two
    pieces (the common case); None otherwise."""
    at = {}
    for k, pl in enumerate(opens):
        for p in (pl[0], pl[-1]):
            at.setdefault(p, []).append(k)
    if any(len(v) != 2 for v in at.values()):
        return None
    used = [False] * len(opens)
    rings = []
    for k0 in range(len(opens)):
        if used[k0]:
            continue
        used[k0] = True
        ring = list(opens[k0])
        start = ring[0]
        cur = ring[-1]
        while cur != start:
            nxt = next((k for k in at[cur] if not used[k]), None)
            if nxt is None:
                return None
            used[nxt] = True
            pl = opens[nxt]
            seg = pl if pl[0] == cur else pl[::-1]
            ring.extend(seg[1:])
            cur = ring[-1]
        if len(ring) >= 4:
            rings.append(ring)
    return rings


def _even_odd(rings):
    """Polygons from closed rings nested by the even-odd rule."""
    polys = []
    for r in rings:
        p = Polygon(r)
        if not p.is_valid:
            p = shapely.make_valid(p)
        if p.area > 0:
            polys.append(p)
    if not polys:
        return []
    if len(polys) == 1:
        g = polys[0]
    else:
        polys.sort(key=lambda p: -p.area)
        g = polys[0]
        for p in polys[1:]:
            g = g.symmetric_difference(p)
    return _parts(g)


def _parts(g):
    if g.is_empty:
        return []
    if g.geom_type == "Polygon":
        return [g]
    return [p for p in getattr(g, "geoms", []) if p.geom_type == "Polygon" and p.area > 0]


def polygons(opens, rings, eps=0.01):
    """Closed regions from open polylines and closed rings (lists of (x, y)).

    Returns (polygons, open_ends): shapely Polygons (with holes) and the number of
    piece endpoints (after snapping within eps) that no other piece meets; non-zero means
    some piece is not part of a closed loop (KiCad calls such an outline malformed).
    """
    opens = [[tuple(p) for p in pl] for pl in opens if len(pl) >= 2]
    rings = [[tuple(p) for p in r] for r in rings if len(r) >= 4]
    opens = _snap(opens, eps)
    chained = _chain_simple(opens) if opens else []
    if chained is not None:
        return _even_odd(rings + chained), 0
    deg = {}
    for pl in opens:
        for p in (pl[0], pl[-1]):
            deg[p] = deg.get(p, 0) + 1
    open_ends = sum(1 for d in deg.values() if d % 2)
    # general case: node everything, take the faces, nest by even-odd
    lines = [LineString(pl) for pl in opens if len(set(pl)) >= 2] + [LineString(r) for r in rings]
    faces = list(polygonize(unary_union(lines)))
    return _even_odd([list(f.exterior.coords) for f in faces]), open_ends
