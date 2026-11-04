# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Shortest paths in a homotopy class among grown obstacles, as tangents and true arcs.

    bs = BranchSpace(obstacles, window, outline_inner)      # one net, layer, width
    res = bs.solve(polyline)                                  # None: keep the input
    res.pieces   # [('seg', a, b) | ('arc', centre, r, a0, sweep)], res.length, res.certificate

The path of a track's centreline must stay out of every obstacle grown by its requirement
(configuration space, Lozano-Perez & Wesley 1979): an `Obstacle` is a core geometry (point,
centreline, polygon) and a radius R = item radius + clearance + w/2, so its grown shape is the
Minkowski sum core + disc(R), offset with round joins.

Method (docs/research/routing/kae-taut-arcs.md):

1. Topology. The free space (window, minus the grown obstacles as inscribed polygons of the
   requirement less `eps_topo`, so a legal input lies strictly inside) is triangulated (GEOS constrained Delaunay). The input polyline is traced through
   the triangles; a crossing that is undone at once (out through an edge and back) cancels, which
   leaves the sleeve of the path's class in the universal cover (Hershberger & Snoeyink 1994).
   The funnel (Lee & Preparata 1984) over the sleeve's portals gives the shortest polygonal path
   of that class and, for each apex, the side the obstacle lies on.
2. Atoms. Every apex is a round-join vertex of some grown obstacle, so it lies on an atom: a
   circle (centre a convex core vertex, radius R; co-circular runs of core vertices, as KiCad
   polygonises round pads and roundrect corners, merge into one circle). A run of apexes on one
   atom is one wrap.
3. Exact path. Through the atom sequence with its sides, consecutive wraps are joined by their
   common tangent (outer when both sides agree, inner when they differ) and each atom carries an
   arc between its tangent points (Chen & Wang 2015: shortest paths among curved obstacles are
   free common tangents plus convex boundary arcs). A wrap whose arc would run backwards (its
   obstacle no longer touches the taut path) is dropped; an obstacle the exact path comes too close
   to adds its nearest atom on the side its centre lies. Repeat until stable.
4. Certificate. The result is G1 (tangent continuous), each arc turns toward its atom's centre,
   and every piece keeps its requirement: a locally shortest path in its homotopy class. Free
   space lifted to the universal cover is simply connected and flat, where a locally shortest
   path is the shortest one, so the path is optimal for its class. The atoms are the polygonised
   outlines (pads come from KiCad as polygons a max error outside the true shape), so the
   optimality is relative to those outlines; the requirement margin `margin` (2 um plus the
   arc sampling) is the only other slack.

The window is the convex hull of the input and its fixed points, grown by `margin_win`; a
result that touches its boundary is solved again in a window twice as large.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import shapely
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union

from . import arcs as A

QUAD = 12                      # buffer segments per quarter circle (topology polygons)
COS_Q = math.cos(math.pi / (4 * QUAD))
TWO_PI = 2 * math.pi


# ----------------------------------------------------------------------------- tangents and wraps
def tangent(c1, r1, s1, c2, r2, s2):
    """The common tangent from circle 1 to circle 2 for a path that goes around circle 1 with
    orientation s1 and around circle 2 with s2 (+1: counter-clockwise, the centre on the path's
    left; -1: clockwise; a point has r = 0). Returns (p1, p2), the tangent points, or None when no
    such tangent exists (one circle inside the other, or overlapping circles for an inner tangent).

    With u the travel direction and L = left(u), p = c - s*r*L, so p2 - p1 = d - k*L with
    k = s2*r2 - s1*r1, d = c2 - c1; parallel to u iff d.L = k, i.e. |d| sin(phi - theta) = k."""
    dx, dy = c2[0] - c1[0], c2[1] - c1[1]
    D = math.hypot(dx, dy)
    k = s2 * r2 - s1 * r1
    if D < 1e-12 or abs(k) > D * (1 + 1e-12):
        return None
    phi = math.atan2(dy, dx)
    th = phi - math.asin(max(-1.0, min(1.0, k / D)))
    ux, uy = math.cos(th), math.sin(th)
    Lx, Ly = -uy, ux
    p1 = (c1[0] - s1 * r1 * Lx, c1[1] - s1 * r1 * Ly)
    p2 = (c2[0] - s2 * r2 * Lx, c2[1] - s2 * r2 * Ly)
    return p1, p2


@dataclass
class Wrap:
    """A path node: a fixed point (r = 0) or a wrap around atom circle (c, r) with side s."""
    c: tuple
    r: float = 0.0
    s: int = 0                 # +1 CCW (centre on the left), -1 CW, 0 point
    e: float = 0.0             # expected sweep (from the polygonal path), rad >= 0
    atom: int = -1             # atom id (-1: a fixed point)


def solve_wraps(nodes, max_iter=200):
    """Exact tangent/arc path through `nodes` (first and last fixed points). Drops wraps whose arc
    would sweep backwards. Returns (pieces, nodes kept, owner) or (None, reason, None); owner[k] is
    i for the arc of node i and i + 0.5 for the tangent from node i to node i + 1."""
    nodes = list(nodes)
    for _ in range(max_iter):
        tans = []
        bad = None
        for i in range(len(nodes) - 1):
            a, b = nodes[i], nodes[i + 1]
            t = tangent(a.c, a.r, a.s, b.c, b.r, b.s)
            if t is None:
                bad = i
                break
            tans.append(t)
        if bad is not None:
            a, b = nodes[bad], nodes[bad + 1]
            # same side, one circle inside the other: the inner wrap is redundant
            if a.s == b.s and a.s != 0 and b.s != 0:
                drop = bad if a.r < b.r else bad + 1
                nodes.pop(drop)
                continue
            if a.s == 0 and b.s != 0:
                # a fixed point inside an atom circle: the atom cannot be wrapped from here
                nodes.pop(bad + 1)
                continue
            if b.s == 0 and a.s != 0:
                nodes.pop(bad)
                continue
            return None, f"no tangent between nodes {bad} and {bad + 1}", None
        worst, wv = None, 0.0
        sweeps = [0.0] * len(nodes)
        for i in range(1, len(nodes) - 1):
            n = nodes[i]
            q, p = tans[i - 1][1], tans[i][0]
            aq = math.atan2(q[1] - n.c[1], q[0] - n.c[0])
            ap = math.atan2(p[1] - n.c[1], p[0] - n.c[0])
            sw = (n.s * (ap - aq)) % TWO_PI          # in [0, 2pi)
            # the sweep is sw + 2 pi m; take the m nearest the polygonal path's turn
            m = round((n.e - sw) / TWO_PI)
            val = sw + TWO_PI * m
            if val < -1e-9 and val < wv:
                worst, wv = i, val
            sweeps[i] = val
        if worst is not None:
            nodes.pop(worst)
            # neighbours that are now the same wrap merge
            merged = [nodes[0]]
            for n in nodes[1:]:
                m = merged[-1]
                if n.s != 0 and m.s == n.s and math.dist(m.c, n.c) < 1e-9 and abs(m.r - n.r) < 1e-9:
                    m.e += n.e
                    continue
                merged.append(n)
            nodes = merged
            continue
        pieces, owner = [], []
        for i in range(len(nodes) - 1):
            p1, p2 = tans[i]
            if i > 0:
                n = nodes[i]
                sw = sweeps[i]
                if sw * n.r > 1e-7:
                    a0 = math.atan2(tans[i - 1][1][1] - n.c[1], tans[i - 1][1][0] - n.c[0])
                    pieces.append(("arc", n.c, n.r, a0, n.s * sw))
                    owner.append(i)
            if math.dist(p1, p2) > 1e-7:
                pieces.append(("seg", p1, p2))
                owner.append(i + 0.5)
        pieces = _snap(pieces, nodes[0].c, nodes[-1].c)
        if len(owner) != len(pieces):
            owner = [0.5] * len(pieces)
        return pieces, nodes, owner
    return None, "no convergence", None


def _snap(pieces, a, b):
    """Make the pieces one chain: each piece starts exactly where the previous ended."""
    out = []
    cur = tuple(a)
    for p in pieces:
        s, e = A.piece_ends(p)
        if p[0] == "seg":
            out.append(("seg", cur, tuple(e)))
        else:
            out.append(p)
        cur = tuple(e) if p[0] == "seg" else tuple(A.piece_ends(p)[1])
    if out and out[-1][0] == "seg":
        out[-1] = ("seg", out[-1][1], tuple(b))
    elif not out:
        out = [("seg", tuple(a), tuple(b))]
    return out


def path_length(pieces):
    return sum(A.piece_length(p) for p in pieces)


def g1_defects(pieces, tol=1e-6):
    """Joints where the direction jumps (rad), excluding the first and last points."""
    out = []
    for p, q in zip(pieces[:-1], pieces[1:]):
        out.append(abs(A.norm_angle(_heading(q, 0) - _heading(p, 1))))
    return [x for x in out if x > tol]


def _heading(p, end):
    if p[0] == "seg":
        return math.atan2(p[2][1] - p[1][1], p[2][0] - p[1][0])
    _, c, r, a0, sw = p
    a = a0 + (sw if end else 0.0)
    return a + math.copysign(math.pi / 2, sw)


# ----------------------------------------------------------------------------- obstacles and atoms
@dataclass
class Obstacle:
    """A grown obstacle: core geometry grown by R (centreline distance needed = R)."""
    core: object
    R: float
    key: object = None          # caller's handle (Space item, fill id ...)
    atoms: list = field(default_factory=list)    # [(centre, radius)]
    vmap: list = field(default_factory=list)     # (core vertex, atom index) for apex mapping


def _ccw(a, b, c):
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _cocircular_runs(pts, closed, tol=1e-3, rmax=20.0, max_step=math.radians(30)):
    """Split the vertex list into runs; each run of >= 3 points on one circle (within tol, radius
    <= rmax) becomes (centre, radius, indices); singletons are (vertex, 0, [i])."""
    n = len(pts)
    out = []
    i = 0
    while i < n:
        j = i + 2
        best = None
        while j < n:
            idx = [k % n for k in range(i, j + 1)]
            got = A.circle_through(pts[idx[0]], pts[idx[len(idx) // 2]], pts[idx[-1]])
            if got is None or got[1] > rmax:
                break
            c, r = got
            if max(abs(math.dist(pts[k], c) - r) for k in idx) > tol:
                break
            # an arc's polygonisation, not corners that happen to be co-circular (a rectangle's):
            # consecutive vertices at most max_step apart around the centre
            if any(math.dist(pts[idx[m]], pts[idx[m + 1]]) > 2 * r * math.sin(max_step / 2) + 1e-9
                   for m in range(len(idx) - 1)):
                break
            # one turning sense along the run
            turns = [_ccw(pts[idx[m]], pts[idx[m + 1]], pts[idx[m + 2]]) for m in range(len(idx) - 2)]
            if not (all(t > 0 for t in turns) or all(t < 0 for t in turns)):
                break
            best = (c, r, idx)
            j += 1
        if best is not None:
            out.append(best)
            i = best[2][-1] + 1 if best[2][-1] >= i else n
        else:
            out.append((pts[i], 0.0, [i]))
            i += 1
    return out


def make_obstacle(core, R, key=None, merge=True):
    """Obstacle with its atoms. Core: Point, LineString, Polygon or Multi*."""
    ob = Obstacle(core, R, key)
    geoms = getattr(core, "geoms", [core])
    for g in geoms:
        if g.is_empty:
            continue
        if g.geom_type == "Point":
            ob.atoms.append(((g.x, g.y), R))
            ob.vmap.append(((g.x, g.y), len(ob.atoms) - 1))
            continue
        if g.geom_type == "LineString":
            rings = [(list(g.coords), False)]
        elif g.geom_type == "Polygon":
            g = shapely.geometry.polygon.orient(g, 1.0)
            rings = [(list(g.exterior.coords)[:-1], True)] + [(list(h.coords)[:-1], True) for h in g.interiors]
        else:
            continue
        for pts, closed in rings:
            if not pts:
                continue
            if not closed:
                ends = {0, len(pts) - 1}
                inner = list(range(1, len(pts) - 1))
                for k in ends:
                    ob.atoms.append((tuple(pts[k]), R))
                    ob.vmap.append((tuple(pts[k]), len(ob.atoms) - 1))
                runs = _cocircular_runs([pts[k] for k in inner], False) if merge and len(inner) >= 3 else \
                    [(pts[k], 0.0, [m]) for m, k in enumerate(inner)]
                for c, r, idx in runs:
                    if r > 0:
                        ob.atoms.append((tuple(c), r + R))
                        for m in idx:
                            ob.vmap.append((tuple(pts[inner[m]]), len(ob.atoms) - 1))
                    else:
                        ob.atoms.append((tuple(pts[inner[idx[0]]]), R))
                        ob.vmap.append((tuple(pts[inner[idx[0]]]), len(ob.atoms) - 1))
                continue
            n = len(pts)
            convex = [_ccw(pts[k - 1], pts[k], pts[(k + 1) % n]) > 0 for k in range(n)]
            runs = _cocircular_runs(pts, True) if merge and n >= 3 else [(pts[k], 0.0, [k]) for k in range(n)]
            for c, r, idx in runs:
                if r > 0 and all(convex[k] for k in idx):
                    rr = max(math.dist(pts[k], c) for k in idx)       # conservative: encloses every vertex disc
                    ob.atoms.append((tuple(c), rr + R))
                    for k in idx:
                        ob.vmap.append((tuple(pts[k]), len(ob.atoms) - 1))
                else:
                    for k in idx:
                        if convex[k]:
                            ob.atoms.append((tuple(pts[k]), R))
                            ob.vmap.append((tuple(pts[k]), len(ob.atoms) - 1))
    return ob


# ----------------------------------------------------------------------------- triangulation, sleeve, funnel
class _Tri:
    __slots__ = ("v", "nb")

    def __init__(self, v):
        self.v = v                # 3 vertex ids, CCW
        self.nb = [None, None, None]   # neighbour across edge (v[i], v[i+1])


class Mesh:
    """Constrained Delaunay triangulation of one free-space polygon, with adjacency."""

    def __init__(self, poly):
        tris = shapely.constrained_delaunay_triangles(poly)
        self.xy = []
        ids = {}
        self.tris = []
        for t in getattr(tris, "geoms", []):
            cs = list(t.exterior.coords)[:3]
            vs = []
            for c in cs:
                k = (c[0], c[1])
                if k not in ids:
                    ids[k] = len(self.xy)
                    self.xy.append(k)
                vs.append(ids[k])
            a, b, c = (self.xy[x] for x in vs)
            area = _ccw(a, b, c)
            if abs(area) < 1e-18:
                continue
            if area < 0:
                vs = [vs[0], vs[2], vs[1]]
            self.tris.append(_Tri(vs))
        edges = {}
        for ti, t in enumerate(self.tris):
            for i in range(3):
                a, b = t.v[i], t.v[(i + 1) % 3]
                edges.setdefault((min(a, b), max(a, b)), []).append((ti, i))
        for lst in edges.values():
            if len(lst) == 2:
                (t1, i1), (t2, i2) = lst
                self.tris[t1].nb[i1] = t2
                self.tris[t2].nb[i2] = t1
        self.P = np.array(self.xy) if self.xy else np.zeros((0, 2))
        polys = [Polygon([self.xy[x] for x in t.v]) for t in self.tris]
        self.tree = shapely.STRtree(polys) if polys else None
        self.polys = polys

    def locate(self, p):
        if self.tree is None:
            return None
        P = Point(p)
        best, bd = None, math.inf
        for i in self.tree.query(P.buffer(1e-6)):
            d = self.polys[i].distance(P)
            if d < bd:
                best, bd = int(i), d
        return best if bd < 1e-6 else None

    def trace(self, pts, max_steps=200000):
        """Portals [(left id, right id)] crossed by the polyline, reduced (sleeve), or None."""
        # locate a hair along the first move, so a start on a triangle edge picks the triangle
        # the path enters (the edge it sits on is then behind it, not a crossing)
        p0, p1 = pts[0], pts[1]
        L = math.dist(p0, p1)
        h = min(1e-7, L / 4) if L > 0 else 0.0
        t = self.locate((p0[0] + (p1[0] - p0[0]) * h / L, p0[1] + (p1[1] - p0[1]) * h / L) if L > 0 else p0)
        if t is None:
            return None, None, None
        t0 = t
        stack = []
        steps = 0
        for p, q in zip(pts[:-1], pts[1:]):
            tcur = 0.0
            dx, dy = q[0] - p[0], q[1] - p[1]
            entry = None
            while True:
                steps += 1
                if steps > max_steps:
                    return None, None, None
                tri = self.tris[t]
                best, bi = math.inf, None
                for i in range(3):
                    if i == entry:
                        continue
                    a, b = self.xy[tri.v[i]], self.xy[tri.v[(i + 1) % 3]]
                    ex, ey = b[0] - a[0], b[1] - a[1]
                    # outward when the move crosses to the right of a->b (interior on the left)
                    cr = ex * dy - ey * dx
                    if cr >= 0:
                        continue
                    den = dx * ey - dy * ex
                    if abs(den) < 1e-300:
                        continue
                    tt = ((a[0] - p[0]) * ey - (a[1] - p[1]) * ex) / den
                    if tt < tcur - 1e-12:
                        continue
                    if tt < best:
                        best, bi = tt, i
                if bi is None or best >= 1.0:
                    break
                nb = tri.nb[bi]
                if nb is None:
                    return None, None, None        # the path leaves the free space
                a_id, b_id = tri.v[bi], tri.v[(bi + 1) % 3]
                key = (min(a_id, b_id), max(a_id, b_id))
                if stack and stack[-1][0] == key:
                    stack.pop()
                else:
                    stack.append((key, b_id, a_id))      # left = v[i+1], right = v[i]
                tcur = max(best, tcur)
                ntri = self.tris[nb]
                entry = next(k for k in range(3) if ntri.nb[k] == t)
                t = nb
        return [(l, r) for _, l, r in stack], t0, t


def funnel(xy, portals, start, end):
    """Simple stupid funnel over portals [(left, right)] (vertex ids into xy) from start to end.
    Returns [(point, vertex id or None, side)] with side +1 for a left apex (path turns left
    around it), -1 right, 0 the end points."""
    P = [(start, start, None, None)] + [(xy[l], xy[r], l, r) for l, r in portals] + [(end, end, None, None)]
    n = len(P)
    out = [(start, None, 0)]
    apex = start
    apex_id = None
    left, right = P[0][0], P[0][1]
    lid = rid = None
    ai = li = ri = 0
    i = 1
    guard = 0
    while i < n:
        guard += 1
        if guard > 10 * n * n + 100:
            break
        pl, pr, idl, idr = P[i]
        # right side
        if _ccw(apex, right, pr) >= 0:
            if (apex == right and apex_id == rid) or _ccw(apex, left, pr) < 0:
                right, rid, ri = pr, idr, i
            else:
                out.append((left, lid, +1))
                apex, apex_id, ai = left, lid, li
                left = right = apex
                lid = rid = apex_id
                li = ri = ai
                i = ai + 1
                continue
        # left side
        if _ccw(apex, left, pl) <= 0:
            if (apex == left and apex_id == lid) or _ccw(apex, right, pl) > 0:
                left, lid, li = pl, idl, i
            else:
                out.append((right, rid, -1))
                apex, apex_id, ai = right, rid, ri
                left = right = apex
                lid = rid = apex_id
                li = ri = ai
                i = ai + 1
                continue
        i += 1
    out.append((end, None, 0))
    # drop repeats
    res = [out[0]]
    for o in out[1:]:
        if math.dist(o[0], res[-1][0]) > 1e-12:
            res.append(o)
    if len(res) == 1 or math.dist(res[-1][0], end) > 1e-12:
        res.append((end, None, 0))
    return res


# ----------------------------------------------------------------------------- the branch space
@dataclass
class Result:
    pieces: list
    length: float
    nodes: list
    certificate: dict
    window_grown: int = 0
    inserted: int = 0


class BranchSpace:
    """Free space of one (net, layer, width) around a branch.

    obstacles: [Obstacle] (R = centreline distance needed, already including the margin the
    exact path keeps); window: shapely polygon (convex); inner: the board outline shrunk by the
    edge requirement (or None); check(pieces) -> [obstacle index] that a piece comes too close to.
    """

    def __init__(self, obstacles, window, inner=None, eps_topo=3e-3, check=None, slack=0.0):
        self.obs = obstacles
        self.slack = slack
        self.window = window
        self.inner = inner
        self.eps = eps_topo
        self.check = check
        self._free = None
        self._meshes = {}
        # apex -> atom lookup
        vs, ids, rs = [], [], []
        for oi, ob in enumerate(obstacles):
            for v, ai in ob.vmap:
                vs.append(v)
                ids.append((oi, ai))
                rs.append(ob.R)
        self.V = np.array(vs) if vs else np.zeros((0, 2))
        self.Vid = ids
        self.VR = np.array(rs) if rs else np.zeros(0)

    # -- topology
    def topo_radius(self, ob):
        # inscribed polygon of the requirement less eps: a legal input (at exactly its clearance)
        # lies strictly in the free space; the exact path keeps the full R (atoms, check)
        return ob.R - self.slack - self.eps

    def free(self):
        if self._free is None:
            grown = []
            for ob in self.obs:
                r = self.topo_radius(ob)
                if r <= 0:
                    continue
                grown.append(ob.core.buffer(r, quad_segs=QUAD))
            region = self.window if self.inner is None else self.window.intersection(self.inner)
            if grown:
                region = region.difference(unary_union(grown))
            self._free = [g for g in getattr(region, "geoms", [region]) if g.geom_type == "Polygon" and not g.is_empty]
        return self._free

    def component(self, line):
        for k, g in enumerate(self.free()):
            if g.contains(line):
                return k
        return None

    def mesh(self, k):
        if k not in self._meshes:
            self._meshes[k] = Mesh(self.free()[k])
        return self._meshes[k]

    def map_apex(self, v):
        """(obstacle, atom) whose round join vertex v is: |v - core vertex| = topo radius."""
        if not len(self.V):
            return None
        d = np.hypot(self.V[:, 0] - v[0], self.V[:, 1] - v[1])
        topo = self.VR - self.slack - self.eps
        err = np.abs(d - topo)
        k = int(np.argmin(err))
        if err[k] > 2e-3:
            return None
        return self.Vid[k]

    # -- solve
    def solve(self, pts, max_insert=20):
        """Shortest path homotopic to polyline `pts` (ends fixed); None if pts is not in free space
        or the exact path cannot be made legal."""
        self.fail = None
        line = LineString(pts)
        k = self.component(line)
        if k is None:
            self.fail = "not in free space"
            return None
        mesh = self.mesh(k)
        portals, _, _ = mesh.trace(pts)
        if portals is None:
            self.fail = "trace"
            return None
        apexes = funnel(mesh.xy, portals, tuple(pts[0]), tuple(pts[-1]))
        nodes = [Wrap(tuple(pts[0]))]
        for idx in range(1, len(apexes) - 1):
            v, vid, side = apexes[idx]
            got = self.map_apex(v)
            if got is None:
                self.fail = "apex unmapped"
                return None       # an apex that is no round join (window corner, notch): not expected
            oi, ai = got
            c, r = self.obs[oi].atoms[ai]
            # the polygonal path's turn at this apex
            pa, pb = apexes[idx - 1][0], apexes[idx + 1][0]
            turn = A.norm_angle(math.atan2(pb[1] - v[1], pb[0] - v[0]) - math.atan2(v[1] - pa[1], v[0] - pa[0]))
            e = max(0.0, side * turn)
            if nodes[-1].atom == (oi, ai) and nodes[-1].s == side:
                nodes[-1].e += e
                continue
            nodes.append(Wrap(tuple(c), r, side, e, (oi, ai)))
        nodes.append(Wrap(tuple(pts[-1])))
        inserted = 0
        while True:
            pieces, kept, owner = solve_wraps(nodes)
            if pieces is None:
                self.fail = f"wraps: {kept}"
                return None
            bad = self.check(pieces) if self.check is not None else []
            if not bad:
                break
            if inserted >= max_insert:
                self.fail = "insert limit"
                return None
            # insert the nearest atom of the first offending obstacle, on the side its centre lies
            pi_, oi = bad[0]
            ob = self.obs[oi]
            p = pieces[pi_]
            g = LineString(A.piece_coords(p))
            best = None
            for ai, (c, r) in enumerate(ob.atoms):
                d = g.distance(Point(c)) - r
                if best is None or d < best[0]:
                    best = (d, ai, c, r)
            if best is None:
                return None
            _, ai, c, r = best
            # position: after the node a tangent leaves, or next to the wrap whose arc it is
            o = owner[pi_]
            if o != int(o):
                pos = int(o) + 1
            else:
                ends = A.piece_ends(p)
                pos = int(o) + (1 if math.dist(ends[1], c) < math.dist(ends[0], c) else 0)
            pos = max(1, min(len(kept) - 1, pos))
            # side: the centre's side of the piece direction at its nearest point
            s = _side_of(p, c)
            if any(n.atom == (oi, ai) and n.s == s for n in kept):
                self.fail = "repeat insert"
                return None
            kept.insert(pos, Wrap(tuple(c), r, s, 0.0, (oi, ai)))
            nodes = kept
            inserted += 1
        L = path_length(pieces)
        cert = dict(g1=len(g1_defects(pieces)) == 0, wraps=len(kept) - 2,
                    convex=all(n.e >= -1e-9 for n in kept[1:-1]))
        win = self.window.exterior
        touches = win.distance(LineString(A.pieces_coords(pieces))) < 1e-6
        cert["window"] = not touches
        return Result(pieces, L, kept, cert, inserted=inserted)


def _side_of(p, c):
    if p[0] == "seg":
        a, b = p[1], p[2]
        v = _ccw(a, b, c)
        return 1 if v > 0 else -1
    # an arc: the obstacle is outside the arc (or it would be the wrapped atom): its side is the
    # side opposite the arc's centre
    _, ac, r, a0, sw = p
    inside = math.dist(ac, c) < r
    s = 1 if sw > 0 else -1
    return s if inside else -s


def convex_window(points, margin):
    hull = shapely.convex_hull(shapely.multipoints(np.asarray(points, float)))
    return hull.buffer(margin, quad_segs=4)
