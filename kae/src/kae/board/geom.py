# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Geometry helpers for KiCad graphics: arcs, circles, Beziers, and outlines chained into
polygons with holes (Edge.Cuts, courtyards).

Arcs are polygonized with vertices on the true arc and a chord error <= `tol` (mm).
`polygons(opens, rings, eps)` follows KiCad's ConvertOutlineToPolygon: open pieces whose
endpoints meet within `eps` are chained into closed contours; a contour whose first point
lies strictly inside an odd number of other contours is a hole of the one that encloses it
one level up, the others are outlines; outlines are then united (KiCad's courtyard and
outline caches go through Clipper, which merges overlapping or repeated outlines).
"""
import math

import shapely
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import polygonize, unary_union

ARC_TOL = 0.001  # mm; KiCad itself uses the board's max_error (default 0.005 mm)


class ArcPiece(list):
    """An arc's polyline that remembers its mid point, so chaining can redefine the arc
    through a snapped start the way KiCad does."""
    __slots__ = ("mid", "tol")

    def __init__(self, pts, mid, tol):
        super().__init__(pts)
        self.mid = tuple(mid)
        self.tol = tol

    def mapped(self, fn):
        return ArcPiece([fn(*p) for p in self], fn(*self.mid), self.tol)


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


def _chain_kicad(opens, eps):
    """Chain open polylines into closed contours as KiCad's ConvertOutlineToPolygon does:
    start at the first unused piece (list order) from its start, then repeatedly take an
    unused piece with an endpoint exactly at the chain's end, else the nearest endpoint of
    any other piece within eps; the joined piece's near endpoint is dropped (the chain keeps
    its own point), its far endpoint appended. A chain closes when no unused piece follows
    and its end is within eps of its start.

    Returns (contours, open_ends, gap): open_ends counts chains that did not close, gap is
    the largest endpoint distance bridged."""
    n = len(opens)
    used = [False] * n
    at = {}
    for k, pl in enumerate(opens):
        at.setdefault(pl[0], []).append(k)
        at.setdefault(pl[-1], []).append(k)
    eps2 = eps * eps
    grid = {}
    if eps > 0:
        for k, pl in enumerate(opens):
            for p in (pl[0], pl[-1]):
                grid.setdefault((int(math.floor(p[0] / eps)), int(math.floor(p[1] / eps))), []).append(k)

    def find_next(cur, pt):
        for k in at.get(pt, ()):
            if k != cur and not used[k]:
                return k
        best, bd = None, eps2
        if eps > 0:
            gx, gy = int(math.floor(pt[0] / eps)), int(math.floor(pt[1] / eps))
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for k in grid.get((gx + dx, gy + dy), ()):
                        if k == cur:
                            continue
                        for q in (opens[k][0], opens[k][-1]):
                            d = (pt[0] - q[0]) ** 2 + (pt[1] - q[1]) ** 2
                            if d < bd or (d == bd and best is not None and k < best):
                                best, bd = k, d
        return best

    contours, open_ends, gap = [], 0, 0.0
    for k0 in range(n):
        if used[k0]:
            continue
        used[k0] = True
        chain = list(opens[k0])
        start, prev, cur = chain[0], chain[-1], k0
        while True:
            k = find_next(cur, prev)
            if k is not None and not used[k]:
                used[k] = True
                pl = opens[k]
                d0 = (pl[0][0] - prev[0]) ** 2 + (pl[0][1] - prev[1]) ** 2
                d1 = (pl[-1][0] - prev[0]) ** 2 + (pl[-1][1] - prev[1]) ** 2
                seg = pl if d0 <= d1 else pl[::-1]
                gap = max(gap, math.sqrt(min(d0, d1)))
                if isinstance(pl, ArcPiece) and seg[0] != prev:
                    # KiCad snaps the arc's start to the chain and redefines the arc
                    # through (chain point, mid, end)
                    seg = arc_points(prev, pl.mid, seg[-1], pl.tol)
                chain.extend(seg[1:])
                prev, cur = chain[-1], k
                continue
            d = math.hypot(prev[0] - start[0], prev[1] - start[1])
            if d <= eps:
                gap = max(gap, d)
                if d > 0 and len(chain) > 2:
                    chain[-1] = start   # KiCad keeps the chain's start, drops the near copy
                contours.append(chain if chain[0] == chain[-1] else chain + [chain[0]])
            else:
                open_ends += 1
            break
    return contours, open_ends, gap


def _nest(rings, info=None):
    """Polygons from closed contours, nested as KiCad's ConvertOutlineToPolygon does.
    A self-touching contour (e.g. two slots closed by one line drawn back over them)
    keeps all its pieces, as KiCad's later Simplify does."""
    polys, firsts = [], []
    for r in rings:
        p = Polygon(r)
        if not p.is_valid:
            parts = _parts(shapely.make_valid(p))
            if not parts:
                continue
            p = parts[0] if len(parts) == 1 else unary_union(parts)
            # drop the zero-width spikes a line drawn back over itself leaves
            p = p.buffer(-1e-7, join_style="mitre").buffer(1e-7, join_style="mitre")
        if p.area > 0:
            polys.append(p)
            firsts.append(Point(r[0]))
    n = len(polys)
    if n == 0:
        return []
    if n == 1:
        return _parts(polys[0])
    parents = [[j for j in range(n) if j != i and polys[j].contains(firsts[i])] for i in range(n)]
    outlines = [i for i in range(n) if len(parents[i]) % 2 == 0]
    holes = {}
    for i in range(n):
        if len(parents[i]) % 2 == 1:
            j = next((j for j in parents[i] if len(parents[j]) == len(parents[i]) - 1), None)
            if j is not None:
                holes.setdefault(j, []).append(i)
    parts = []
    for j in outlines:
        g = polys[j]
        for h in holes.get(j, ()):
            g = g.difference(polys[h])
        parts.append(g)
    if info is not None and len(parts) > 1:
        info["overlap"] = any(parts[a].intersects(parts[b]) for a in range(len(parts))
                              for b in range(a + 1, len(parts)))
    return _parts(parts[0] if len(parts) == 1 else unary_union(parts))


def _parts(g):
    """The polygons in a geometry, flattening (nested) collections."""
    if g.is_empty:
        return []
    if g.geom_type == "Polygon":
        return [g] if g.area > 0 else []
    out = []
    for p in getattr(g, "geoms", []):
        out += _parts(p)
    return out


def polygons(opens, rings, eps=0.01):
    """Closed regions from open polylines and closed rings (lists of (x, y)).

    Returns (polygons, info): shapely Polygons (with holes) and info = {open_ends:
    chains that do not close (KiCad: malformed), gap: the largest endpoint gap bridged,
    overlap: outlines that overlap or touch each other (KiCad then keeps the raw contours
    and does not deflate a courtyard; we return their union)}.
    """
    opens = [pl if isinstance(pl, ArcPiece) else [tuple(p) for p in pl] for pl in opens if len(pl) >= 2]
    rings = [[tuple(p) for p in r] for r in rings if len(r) >= 4]
    chained, open_ends, gap = _chain_kicad(opens, eps) if opens else ([], 0, 0.0)
    info = dict(open_ends=open_ends, gap=gap, overlap=False)
    polys = _nest(rings + chained, info)
    if open_ends and not polys:
        # T-junctions or crossings: node everything and take the faces as contours
        lines = [LineString(pl) for pl in opens if len(set(pl)) >= 2] + [LineString(r) for r in rings]
        faces = list(polygonize(unary_union(lines)))
        polys = _nest([list(f.exterior.coords) for f in faces], info)
    return polys, info
