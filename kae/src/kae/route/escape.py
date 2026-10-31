# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Escape planning for whole packages (ball grids; fine-pitch pad rings are checked), laid
before routing with the plane escapes (lastmile.plane_escapes, unlocked). It replaces the
fixed dog-bone pass.

Every signal ball of a grid gets a layer, a side of the package to leave by (towards its
net's other end) and, off the ball layer, a dog-bone via in one of the four sites around it;
every plane ball its dog-bone. The model is Yan & Wong's tile network (DAC'09; Tan Yan's
thesis ch. 2) on every signal layer (_network):

- on the ball layer the obstacles are the balls and tracks run through the tiles between
  four balls; on the other layers the obstacles are the vias in the sites and the tiles are
  centred on the balls;
- each tile side is a gap node holding O = fit(p - o) tracks (one pitch more per missing
  corner), each inside tile a centre node of D - 2 floor(O/2) with D = fit(sqrt(2) p - o)
  and a shortcut of floor(O/2) round each corner, so that any orthogonal cut holds O and any
  diagonal one D; a via in a ball-layer tile closes its centre (and narrows its shortcuts to
  what passes beside it); a via site's presence on the other layers is a variable;
- fit(g) = floor((g - 2 s + c) / (w + c)): the board's own width w and clearance c (Space:
  net classes, board setup, .kicad_dru), s the obstacle's requirement (c for vias; for balls
  Space.need: the clearance raised by the solder-mask aperture, expansion + mask-to-copper);
  a site is offered only where the via and its stub pass Space's exact checks.

Plan (plan_grid): stage 1 is the LP of all layers with one commodity (which ball goes down,
through which site); its options are rounded greedily, the balls with the fewest legal
options first and the plane balls last (scarce ones get their paths, flexible ones yield; a
site holds one via; each ball's options are recorded as its flexibility for later
negotiation); stage 2 solves
each layer's integer flow with its vias fixed and one commodity per side (falling back to one
commodity, a network flow, when sides cost escapes); balls the rounding left out are offered
to each layer in turn. Outer rings stay on the surface (LAYER_COST), as on the human boards
and in the vendor guides. Plane layers (translate.plane_layers) carry no escapes unless opts
escape_plane_layers. Laying (_lay_grid): the dog-bones, then each escape along its planned
path (through the middle of each gap), checked exactly, else searched with the grid router to
a box past the package's edge. A package whose ball field is routed already (a restart
resuming from its best board) is not planned.

Certificate (certificate): the LP with every side open, the board's legal minimum widths and
no plane vias is an upper bound on the balls that can escape; below the demand, no routing
escapes them all under these rules. The entry names the package, how many balls cannot
escape, the binding cut (the constraints with the largest LP duals: layer, ring, tracks per
gap at which width and clearance), and the relaxations that make it feasible, each found by
solving the bound again with the rule changed (narrower track, smaller clearance, ball-to-
track clearance, smaller via, plane layers opened to signals, more signal layers), with the
KiCad edit that writes it back. Approximation: a site without a via is credited one pitch
more room, not longer runs of empty sites. Pad rings (QFN/QFP rows, ring_certificate): the
pads a track of the board's minimum width cannot leave between its neighbours.

Buses: `plan_grid(..., order=None)` takes no bus order yet; the interface for it is a list
of net lists whose escapes should keep their order on one side.

`run(sp, info, opts)` -> {packages (with per-ball escapes: layer, side, via, exit, laid),
blocked (kae.route.blocked's format: cause "rule", summary), laid, wanted}.
"""
from __future__ import annotations

import math
import time

import numpy as np
from shapely.geometry import LineString, Point, box

from . import critical_write as W

MIN_BALLS = 16          # a ball grid has at least this many pads
MIN_RING = 12           # a pad ring (QFN, QFP) has at least this many pads
RING_PITCH = 0.65       # mm: pad rings at most this fine are checked
SIDES = ("W", "E", "S", "N")   # package-frame sides: -u, +u, -w, +w
SIDE_COST = (0.0, 30.0, 60.0, 90.0)   # objective cost of a ball's sides, best first
PLAN_SIDES = 4                 # sides offered per ball, best first (a track turns towards its
                               # target outside the package)
LAYER_COST = 100.0             # per layer away from the ball layer (more than a side: the outer rings
                               # escape on the surface, as on the human boards)
ESCAPE_GAIN = 1000.0           # objective value of one escaped signal ball
PLANE_GAIN = 500.0             # of one plane ball's dog-bone
EDGE_COST = 1.0                # per tile or cell crossed
MILP_S = 60.0                  # seconds for one package's integer plan
WIDTH_LADDER = (0.15, 0.127, 0.1, 0.075)   # mm: relaxations tried below the board's minimum width
CLEARANCE_STEP = 0.025
BIG = 50                       # tracks: no limit, for an open gap
DEBUG = False


def _grid(pts):
    """(pitch, angle, ring of each point) when `pts` form a square grid, else None."""
    nn = []
    for i, a in enumerate(pts):
        d, v = min((math.dist(a, b), (b[0] - a[0], b[1] - a[1])) for j, b in enumerate(pts) if j != i)
        nn.append((d, v))
    pitch, v = sorted(nn)[len(nn) // 2]
    tol = 0.03 * pitch + 0.005
    if pitch < 1e-3 or sum(1 for a in pts if sum(abs(math.dist(a, b) - pitch) < tol for b in pts) >= 4) < 4:
        return None
    ang = math.atan2(v[1], v[0]) % (math.pi / 2)
    cx, cy = sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)
    c, s = math.cos(-ang), math.sin(-ang)
    loc = [((x - cx) * c - (y - cy) * s, (x - cx) * s + (y - cy) * c) for x, y in pts]
    hx, hy = max(abs(u) for u, _ in loc), max(abs(w) for _, w in loc)
    return pitch, ang, loc, [round(min(hx - abs(u), hy - abs(w)) / pitch) for u, w in loc]


def _capacity(sp, net, layer, pitch, ball):
    """Tracks of `net`'s routing width that fit between two balls `ball` mm wide."""
    mn, opt, _ = sp.width_limits(net, layer)
    w, clr = opt or mn or 0.1, sp._generic_need(net, "track", layer) or 0.0
    return max(0, int((pitch - ball - clr + 1e-9) // (w + clr)))


def _starves(sp, net, geom, r, layers, zclr):
    """Copper of `net` (`geom` grown by r) within a zone clearance of another net's thermal-
    spoke strip: the filler pulls the pour back from it and cuts the spoke's landing
    (nekoink: decoupling caps under U100)."""
    return any(it.kind == "corridor" and it.net != net and it.geom.distance(geom) < r + zclr
               for l in layers for it in sp.query(l, geom.bounds, r + zclr))


def fit(gap, w, c, side=None):
    """Tracks of width `w`, `c` apart, in `gap` mm between two obstacles they keep `side`
    (default c) from."""
    side = c if side is None else side
    return max(0, int((gap - 2 * side + c + 1e-9) // (w + c)))


def _median(xs, default):
    xs = sorted(x for x in xs if x)
    return xs[len(xs) // 2] if xs else default


def _counts(sp):
    count = {}
    for it in sp.pads:
        if it.kind == "pad" and it.net:
            count[it.net] = count.get(it.net, 0) + 1
    return count


# ----------------------------------------------------------------------------- packages
def find_packages(sp):
    """[{ref, kind: 'grid'|'ring', pads, ...}] of the board's ball grids and pad rings."""
    out = []
    for pads in sp.pads_by_fp.values():
        smd = [p for p in pads if p.kind == "pad" and p.smd and len(p.layers) == 1 and p.hole is None]
        if len(smd) < MIN_RING:
            continue
        med = sorted(p.geom.area for p in smd)[len(smd) // 2]
        balls = [p for p in smd if p.geom.area <= 4 * med]
        ref = (balls or smd)[0].owner[0]
        g = _grid([p.pos for p in balls]) if len(balls) >= MIN_BALLS else None
        if g is not None:
            pitch, ang, loc, rings = g
            umin, wmin = min(u for u, _ in loc), min(w for _, w in loc)
            idx = [(round((u - umin) / pitch), round((w - wmin) / pitch)) for u, w in loc]
            cx = sum(p.pos[0] for p in balls) / len(balls)
            cy = sum(p.pos[1] for p in balls) / len(balls)
            out.append(dict(ref=ref, kind="grid", pads=balls, pitch=pitch, ang=ang, idx=idx, rings=rings,
                            layer=next(iter(balls[0].layers)), centre=(cx, cy), umin=umin, wmin=wmin))
        elif len(balls) >= MIN_RING:
            out.append(dict(ref=ref, kind="ring", pads=balls, layer=next(iter(balls[0].layers))))
    return out


def rules_of(sp, nets, layers, minimum=False, override=None):
    """Per layer {w, c, D, drill} for the signal `nets`: the median routing width (the
    board's legal minimum with `minimum`), clearance and via; `override` replaces values."""
    out = {}
    vs = [sp.via_size(n) for n in nets] or [(0.6, 0.3)]
    for l in layers:
        ws, cs = [], []
        for n in nets:
            mn, opt, _mx = sp.width_limits(n, l)
            ws.append((mn or opt) if minimum else (opt or mn))
            cs.append(sp._generic_need(n, "track", l))
        r = dict(w=_median(ws, 0.2), c=_median(cs, 0.2), D=_median([v[0] for v in vs], 0.6),
                 drill=_median([v[1] for v in vs], 0.3), c_pad=None)
        r.update({k: v for k, v in (override or {}).items() if k in r})
        out[l] = r
    return out


# ----------------------------------------------------------------------------- model
class _Model:
    """A (mixed-integer) linear programme: maximise gain . x subject to rows."""

    def __init__(self):
        self.n = 0
        self.gain, self.ub = [], []
        self.rows = []       # (cols, vals, lo, hi, tag)

    def var(self, gain=0.0, ub=np.inf):
        self.gain.append(gain)
        self.ub.append(ub)
        self.n += 1
        return self.n - 1

    def row(self, terms, lo, hi, tag=None):
        terms = [(k, v) for k, v in terms if v]
        if terms:
            self.rows.append(([k for k, _ in terms], [v for _, v in terms], lo, hi, tag))

    def _matrix(self, rows):
        from scipy.sparse import csr_matrix
        data, ri, ci = [], [], []
        for r, (cols, vals, *_rest) in enumerate(rows):
            ri += [r] * len(cols)
            ci += cols
            data += vals
        return csr_matrix((data, (ri, ci)), shape=(len(rows), self.n))

    def solve(self, integer=True, time_limit=MILP_S):
        """(objective, x, duals {tag: |dual|} for the LP) or (None, None, {})."""
        from scipy.optimize import Bounds, LinearConstraint, linprog, milp
        c = -np.asarray(self.gain, float)
        ub = np.asarray(self.ub, float)
        if integer:
            A = self._matrix(self.rows)
            lo = np.array([r[2] for r in self.rows], float)
            hi = np.array([r[3] for r in self.rows], float)
            res = milp(c, constraints=LinearConstraint(A, lo, hi), bounds=Bounds(np.zeros(self.n), ub),
                       integrality=np.ones(self.n, int),
                       options=dict(time_limit=float(time_limit), mip_rel_gap=0.01, disp=False))
            if res.x is None:
                return None, None, {}
            return -res.fun, np.round(res.x), {}
        eq = [r for r in self.rows if r[2] == r[3]]
        le = [r for r in self.rows if r[2] != r[3]]
        res = linprog(c, A_ub=self._matrix(le) if le else None, b_ub=[r[3] for r in le] if le else None,
                      A_eq=self._matrix(eq) if eq else None, b_eq=[r[2] for r in eq] if eq else None,
                      bounds=list(zip([0.0] * self.n, [None if math.isinf(u) else u for u in ub])), method="highs")
        if res.status != 0:
            return None, None, {}
        duals = {}
        for r, m in zip(le, res.ineqlin.marginals):
            if r[4] is not None and abs(m) > 1e-9:
                duals[r[4]] = duals.get(r[4], 0.0) + abs(m)
        return -res.fun, res.x, duals


def _sides_toward(sp, pkg, net, u, w):
    """The package's sides ordered by how well they face `net`'s other pads (package frame)."""
    ca, sa = math.cos(-pkg["ang"]), math.sin(-pkg["ang"])
    cx, cy = pkg["centre"]
    own = {id(p) for p in pkg["pads"]}
    pts = [it.pos for it in sp.pads if it.net == net and it.kind == "pad" and id(it) not in own and it.pos]
    if pts:
        tx = sum(p[0] for p in pts) / len(pts) - cx
        ty = sum(p[1] for p in pts) / len(pts) - cy
        du, dw = tx * ca - ty * sa - u, tx * sa + ty * ca - w
    else:
        du, dw = u, w           # nowhere in particular: straight out
    score = {"W": -du, "E": du, "S": -dw, "N": dw}
    return sorted(SIDES, key=lambda s: -score[s])


# The network: Yan & Wong's tile network (DAC'09), on every layer. Coordinates are doubled
# package indices: ball (i, j) sits at (2i, 2j), the dog-bone site between four balls at odd
# (X, Y). On each layer the obstacles are the corners of a lattice (the balls on the ball
# layer, the via sites on the others) and tracks run through the tiles between four corners
# (centred on the sites on the ball layer, on the balls elsewhere). Each tile side is a gap
# node holding O tracks (one pitch more per missing corner), each inside tile has a centre
# node C (D - 2 floor(O/2)) and a shortcut round each corner (floor(O/2)): any orthogonal cut
# holds O tracks and any diagonal one D. A tile outside the array is its side's sink.
def _setup(sp, pkg, info, opts=None, minimum=False, override=None, extra_layers=0, open_planes=False):
    from .translate import plane_layers
    opts = opts or {}
    p, B = pkg["pitch"], pkg["layer"]
    count = _counts(sp)
    planes = set() if (open_planes or opts.get("escape_plane_layers")) else set(plane_layers(info))
    real = [B] + [l for l in sp.cu if l != B and l not in planes]
    layers = real + [f"extra{k}" for k in range(extra_layers)]
    zone_on = {(z[0], z[1]) for z in sp.zones}
    balls = {ij: (pd, r) for pd, ij, r in zip(pkg["pads"], pkg["idx"], pkg["rings"])}
    nx, ny = max(i for i, _ in balls) + 1, max(j for _, j in balls) + 1
    sig, pln = [], []
    for k, (pd, r) in sorted(balls.items()):
        if not pd.net:
            continue
        if any(n == pd.net and l != B for n, l in zone_on):
            pln.append(k)
        elif count.get(pd.net, 0) >= 2:
            sig.append(k)
    nets = sorted({balls[k][0].net for k in sig})
    R = rules_of(sp, nets or [""], real, minimum=minimum, override=override)
    for l in layers[len(real):]:
        R[l] = dict(R[real[-1]] if len(real) > 1 else R[B])
    d = _median([min(b[2] - b[0], b[3] - b[1]) for b in (pd.geom.bounds for pd, _ in balls.values())], 0.4)
    # a track between two balls keeps the balls' own requirement (the clearance raised by the
    # solder-mask aperture: expansion + mask-to-copper, Space.need)
    cps = []
    for k in sig[:: max(1, len(sig) // 40)]:
        pd = balls[k][0]
        other = next((balls[q][0].net for q in sig if balls[q][0].net != pd.net), "")
        v = sp.need(pd, other, "track", B)
        if v is not None:
            cps.append(v)
    cpad = (override or {}).get("c_pad") or _median(cps, R[B]["c"])
    R[B]["c_pad"] = cpad
    ca, sa = math.cos(pkg["ang"]), math.sin(pkg["ang"])
    cx, cy = pkg["centre"]
    u0, w0 = pkg["umin"], pkg["wmin"]

    def xy(a, b):
        """Board point of package index coordinates (a, b) (ball (i, j) at (i, j))."""
        u, w = u0 + a * p, w0 + b * p
        return (cx + u * ca - w * sa, cy + u * sa + w * ca)
    caps = {}
    for l in layers:
        r_ = R[l]
        w, c = r_["w"], r_["c"]
        o, side = (d, cpad) if l == B else (r_["D"], c)
        O = fit(p - o, w, c, side)
        Dg = fit(math.sqrt(2) * p - o, w, c, side)
        cap = dict(O=O, D=Dg, centre=max(0, Dg - 2 * (O // 2)), shortcut=O // 2,
                   missing=max(0, fit(2 * p - o, w, c, side) - O))
        if l == B:
            # with a via in the tile's centre: what passes between it and a corner ball
            g = math.sqrt(2) * p / 2 - d / 2 - r_["D"] / 2
            cap["beside_via"] = max(0, int((g - cpad + 1e-9) // (w + c)))
        caps[l] = cap
    return dict(p=p, B=B, layers=layers, real=real, R=R, d=d, balls=balls, nx=nx, ny=ny, sig=sig, pln=pln,
                xy=xy, cap=caps, ref=pkg["ref"], pkg=pkg)


def _sites(ctx):
    """The dog-bone sites (doubled coordinates) inside the array."""
    return [(2 * a - 1, 2 * b - 1) for a in range(1, ctx["nx"]) for b in range(1, ctx["ny"])]


def _ring_at(ctx, X, Y):
    """Ring of the ball nearest to doubled point (X, Y)."""
    nx, ny = ctx["nx"], ctx["ny"]
    i, j = min(max(round(X / 2), 0), nx - 1), min(max(round(Y / 2), 0), ny - 1)
    return min(i, j, nx - 1 - i, ny - 1 - j)


def _neighbours(P):
    X, Y = P
    return ((X + 1, Y), (X, Y + 1), (X - 1, Y), (X, Y - 1))


def _network(M, ctx, l, yvar, kinds, sources, tags=True, yfix=()):
    """Add layer `l`'s network to model M. `kinds`: commodities ('*', or sides); `ysites`:
    {site: variable} (vias decided by the model) or {site: 1} (vias fixed); `sources`:
    {(kind, node): [(variable, coefficient)]} with nodes ('ball', P) or ('site', P).
    Returns {flows: {(kind, a, b): var}, adj: {(kind, a): [b]}}."""
    B, cap, balls = ctx["B"], ctx["cap"][l], ctx["balls"]
    nx, ny = ctx["nx"], ctx["ny"]
    par = 0 if l == B else 1                       # parity of the corners
    yfix = set(yfix)
    if l == B:
        cent = [(2 * a - 1, 2 * b - 1) for a in range(0, nx + 1) for b in range(0, ny + 1)]
        lo_x, hi_x, lo_y, hi_y = -1, 2 * nx - 1, -1, 2 * ny - 1
    else:
        cent = [(2 * i, 2 * j) for i in range(-1, nx + 1) for j in range(-1, ny + 1)]
        lo_x, hi_x, lo_y, hi_y = -2, 2 * nx, -2, 2 * ny
    inside, sink = [], {}
    for (X, Y) in cent:
        s = [k for k, ok in (("W", X == lo_x), ("E", X == hi_x), ("S", Y == lo_y), ("N", Y == hi_y)) if ok]
        if s:
            sink[(X, Y)] = s
        else:
            inside.append((X, Y))

    def presence(q):
        """(constant, [(var, coefficient)]): whether an obstacle sits at corner q."""
        if l == B:
            return (1.0 if q[0] % 2 == 0 and q[1] % 2 == 0 and (q[0] // 2, q[1] // 2) in balls else 0.0), []
        if q in yvar:
            return 0.0, [(yvar[q], 1.0)]
        return (1.0 if q in yfix else 0.0), []

    def corners(g):
        gx, gy = g
        return ((gx, gy - 1), (gx, gy + 1)) if gx % 2 == par else ((gx - 1, gy), (gx + 1, gy))
    flows, adj, into = {}, {}, {}

    def arc(k, a_, b_, ub=BIG, cost=-EDGE_COST):
        v = M.var(cost, ub)
        flows[(k, a_, b_)] = v
        adj.setdefault((k, a_), []).append(b_)
        into.setdefault((k, b_), []).append((v, 1))
        into.setdefault((k, a_), []).append((v, -1))
        return v
    gaps = set()
    for P in inside:
        gaps.update(_neighbours(P))
    for P in inside:
        X, Y = P
        sides = _neighbours(P)
        cnr = [(X + 1, Y + 1), (X - 1, Y + 1), (X - 1, Y - 1), (X + 1, Y - 1)]   # between sides a, a + 1
        through, short = [], [[] for _ in range(4)]
        for k in kinds:
            for g in sides:
                through.append((arc(k, ("g", g), ("c", P)), 1))
                arc(k, ("c", P), ("g", g))
            for a_i in range(4):
                g1, g2 = sides[a_i], sides[(a_i + 1) % 4]
                short[a_i] += [(arc(k, ("g", g1), ("g", g2)), 1), (arc(k, ("g", g2), ("g", g1)), 1)]
        pc = [presence(q) for q in cnr]
        miss = cap["missing"]
        cen = cap["centre"] + miss * sum(1 - c for c, _ in pc)
        vt = [(v, miss * cf) for _, vs in pc for v, cf in vs]
        tag = ("centre", l, _ring_at(ctx, X, Y), cap["centre"]) if tags else None
        if l == B and P in yvar:          # a via in the centre closes it
            M.row(through + [(yvar[P], cen)], -np.inf, cen, tag=tag)
        elif l == B and P in yfix:
            M.row(through, -np.inf, 0)
        else:
            M.row(through + vt, -np.inf, cen, tag=tag)
        for a_i in range(4):
            cq, vq = pc[a_i]
            sc = cap["shortcut"] + miss * (1 - cq)
            terms = short[a_i] + [(v, miss * cf) for v, cf in vq]
            if l == B and sc > cap["beside_via"]:
                if P in yvar:
                    terms.append((yvar[P], sc - cap["beside_via"]))
                elif P in yfix:
                    sc = cap["beside_via"]
            M.row(terms, -np.inf, sc, tag=("diagonal", l, _ring_at(ctx, X, Y), cap["D"]) if tags else None)
    for P, ss in sink.items():
        for g in _neighbours(P):
            if g in gaps:
                for k in kinds:
                    for s in ss:
                        if k in ("*", s):
                            arc(k, ("g", g), ("sink", s), cost=0.0)
    for (k, node), terms in sources.items():
        for g in _neighbours(node[1]):
            if g in gaps:
                arc(k, node, ("g", g), ub=1)
        # a corner on the array's edge leaves straight into an outside tile (Yan & Wong's pin
        # edge into a boundary tile), between no two obstacles
        X, Y = node[1]
        for T in ((X + 1, Y + 1), (X - 1, Y + 1), (X - 1, Y - 1), (X + 1, Y - 1)):
            for s in sink.get(T, ()):
                if k in ("*", s) and (k, node, ("sink", s)) not in flows:
                    arc(k, node, ("sink", s), ub=1, cost=0.0)
        into.setdefault((k, node), [])
        into[(k, node)] = into[(k, node)] + list(terms)
    for (k, node), terms in into.items():
        if node[0] != "sink":
            M.row(terms, 0, 0)
    gin = {}
    for (k, a_, b_), v in flows.items():
        if b_[0] == "g":
            gin.setdefault(b_[1], []).append((v, 1))
    for g, terms in gin.items():
        q1, q2 = corners(g)
        c1, v1 = presence(q1)
        c2, v2 = presence(q2)
        const = cap["O"] + cap["missing"] * (2 - c1 - c2)
        M.row(terms + [(v, cap["missing"] * cf) for v, cf in v1 + v2], -np.inf, const,
              tag=("gap", l, min(_ring_at(ctx, *q1), _ring_at(ctx, *q2)), cap["O"]) if tags else None)
    return dict(flows=flows, adj=adj)


def _site_ok(sp, ctx, override=None, check=True):
    """{(ball, site): legal} for every signal and plane ball and its four sites: the via
    (diameter override D) and its stub pass Space's exact checks."""
    out = {}
    B, xy, balls = ctx["B"], ctx["xy"], ctx["balls"]
    sites = set(_sites(ctx))
    dv = (override or {}).get("D")
    for k in ctx["sig"] + ctx["pln"]:
        pd = balls[k][0]
        for t in _neighbours_diag(k):
            if t not in sites:
                continue
            if not check:
                out[(k, t)] = True
                continue
            v = xy(t[0] / 2, t[1] / 2)
            vkw = dict(size=dv, drill=min(sp.via_size(pd.net)[1], dv - 0.1)) if dv else {}
            mn, opt, _ = sp.width_limits(pd.net, B)
            out[(k, t)] = not sp.via_violations(pd.net, *v, first=True, **vkw) and \
                not sp.track_violations(pd.net, B, mn or opt or 0.1, pd.pos, v, first=True)
    return out


def _neighbours_diag(k):
    i, j = k
    return ((2 * i + 1, 2 * j + 1), (2 * i - 1, 2 * j + 1), (2 * i - 1, 2 * j - 1), (2 * i + 1, 2 * j - 1))


def _stage1(sp, ctx, site_ok, planes=True):
    """All layers, one commodity: layer and dog-bone site per ball, vias as variables.
    -> (model, option vars {(ball, layer, site or None): var}, plane vars, nets)."""
    M = _Model()
    B, layers = ctx["B"], ctx["layers"]
    y = {t: M.var(0.0, 1) for t in _sites(ctx)}
    opt, plane = {}, {}
    src = {l: {} for l in layers}
    for k in ctx["sig"]:
        P = (2 * k[0], 2 * k[1])
        v = opt[(k, B, None)] = M.var(ESCAPE_GAIN, 1)
        src[B].setdefault(("*", ("ball", P)), []).append((v, 1))
        for t in _neighbours_diag(k):
            if site_ok.get((k, t)):
                for li, l in enumerate(layers[1:], 1):
                    v = opt[(k, l, t)] = M.var(ESCAPE_GAIN - LAYER_COST * li, 1)
                    src[l].setdefault(("*", ("site", t)), []).append((v, 1))
    for k in ctx["pln"] if planes else ():
        for t in _neighbours_diag(k):
            if site_ok.get((k, t)):
                plane[(k, t)] = M.var(PLANE_GAIN, 1)
    per = {}
    for (k, l, t), v in opt.items():
        per.setdefault(k, []).append(v)
    for (k, t), v in plane.items():
        per.setdefault(k, []).append(v)
    for vs in per.values():
        M.row([(v, 1) for v in vs], -np.inf, 1)
    use = {t: [] for t in y}
    for (k, l, t), v in opt.items():
        if t is not None:
            use[t].append(v)
    for (k, t), v in plane.items():
        use[t].append(v)
    for t, yv in y.items():
        M.row([(v, 1) for v in use[t]] + [(yv, -1)], 0, 0)
    nets = {l: _network(M, ctx, l, y, ["*"], src[l]) for l in layers}
    return M, opt, plane, nets


def _stage2(sp, ctx, l, assigned, taken, time_limit, single=False):
    """One layer, vias fixed: each assigned ball leaves by one of its sides (best first), or
    with `single` by any side (one commodity: a network flow, integral as an LP).
    `assigned`: [(ball, site or None)] -> {ball: (side, node list)}."""
    B = ctx["B"]
    M = _Model()
    sides_of, src, zs = {}, {}, {}
    nx, ny = ctx["nx"], ctx["ny"]
    for k, t in assigned:
        pd = ctx["balls"][k][0]
        u, w = ctx["pkg"]["umin"] + k[0] * ctx["p"], ctx["pkg"]["wmin"] + k[1] * ctx["p"]
        order = _sides_toward(sp, ctx["pkg"], pd.net, u, w)
        own = min((("W", k[0]), ("E", nx - 1 - k[0]), ("S", k[1]), ("N", ny - 1 - k[1])), key=lambda a: a[1])[0]
        ss = ["*"] if single else list(dict.fromkeys(order[:PLAN_SIDES] + [own]))
        sides_of[k] = ss
        node = ("ball", (2 * k[0], 2 * k[1])) if t is None else ("site", t)
        for s in ss:
            v = zs[(k, s)] = M.var(ESCAPE_GAIN - (0.0 if single else SIDE_COST[order.index(s)]), 1)
            src.setdefault((s, node), []).append((v, 1))
        M.row([(zs[(k, s)], 1) for s in ss], -np.inf, 1)
    kinds = sorted({s for ss in sides_of.values() for s in ss})
    net = _network(M, ctx, l, {}, kinds, src, tags=False, yfix=taken)
    obj, x, _ = M.solve(integer=not single, time_limit=time_limit)
    if x is None:
        return None
    out = {}
    rem = {key: int(round(x[v])) for key, v in net["flows"].items() if x[v] > 0.5}
    for (k, s), v in zs.items():
        if x[v] < 0.5:
            continue
        t = dict(assigned)[k]
        node = ("ball", (2 * k[0], 2 * k[1])) if t is None else ("site", t)
        nodes = [node]
        for _ in range(8 * (nx + ny) + 16):
            nxt = next((b_ for b_ in net["adj"].get((s, node), []) if rem.get((s, node, b_), 0) > 0), None)
            if nxt is None:
                break
            rem[(s, node, nxt)] -= 1
            node = nxt
            nodes.append(node)
            if node[0] == "sink":
                break
        out[k] = (nodes[-1][1] if nodes[-1][0] == "sink" else s, nodes)
    return out


def plan_grid(sp, pkg, info, opts=None, deadline=None, order=None):
    """The escape plan of a ball grid -> (plan summary, ctx, {ball: path}, plane vias).
    Stage 1: the LP of all layers (which ball goes down, through which site); its options
    rounded greedily (sites exclusive); stage 2: each layer's integer flow with the vias
    fixed and a commodity per side, so that escapes leave towards their nets' other ends.
    `order`: bus net lists (not used yet)."""
    t0 = time.monotonic()
    ctx = _setup(sp, pkg, info, opts)
    ok = _site_ok(sp, ctx)
    M, opt, plane, _ = _stage1(sp, ctx, ok)
    obj, x, _ = M.solve(integer=False)
    plan = dict(ref=pkg["ref"], kind="grid", pitch=round(ctx["p"], 4), balls=len(ctx["balls"]),
                signal=len(ctx["sig"]), plane=len(ctx["pln"]), layers=ctx["layers"], capacity=ctx["cap"],
                rules={l: {k: round(v, 4) for k, v in r.items() if v is not None} for l, r in ctx["R"].items()},
                variables=M.n, rows=len(M.rows))
    if x is None:
        plan.update(status="no solution", seconds=round(time.monotonic() - t0, 1))
        return plan, ctx, {}, []
    plan["lp"] = round(float(sum(x[v] for v in opt.values())), 1)
    # flexibility: a ball's legal options (layer and site); the scarce ones choose first, the
    # flexible ones (outer rings, plane balls that can stitch anywhere) yield
    # the surface option counts only for the rings the ball layer can serve (O tracks between
    # two balls let O + 1 rings out; the rule the human boards follow)
    surf = ctx["cap"][ctx["B"]]["O"] + 1
    nopt = {}
    for (k, l, t) in opt:
        if t is not None or ctx["balls"][k][1] < surf:
            nopt[k] = nopt.get(k, 0) + 1
    alts = {}
    for (k, l, t), v in opt.items():
        if x[v] > 0.01:
            alts[k] = alts.get(k, 0) + 1
    ctx["flex"] = {k: dict(options=nopt.get(k, 0), lp_alternatives=alts.get(k, 0)) for k in ctx["sig"]}
    cand = sorted(((x[v], k, l, t) for (k, l, t), v in opt.items() if x[v] > 1e-6),
                  key=lambda c: (nopt.get(c[1], 0), -c[0]))
    cand += sorted(((x[v], k, "plane", t) for (k, t), v in plane.items() if x[v] > 1e-6), key=lambda c: -c[0])
    chosen, taken = {}, set()
    for val, k, l, t in cand:
        if k in chosen or (t is not None and t in taken):
            continue
        chosen[k] = (l, t)
        if t is not None:
            taken.add(t)
    plane_vias = [(k, t) for k, (l, t) in chosen.items() if l == "plane"]
    paths = {}

    def layer_plan(l, assigned):
        left = 20.0 if deadline is None else max(3.0, min(20.0, deadline - time.monotonic()))
        got = _stage2(sp, ctx, l, assigned, taken, left)
        if got is None or len(got) < len(assigned):
            # the sides cost escapes (or no integer plan in time): one commodity escapes as
            # many as the layer can, any side
            one = _stage2(sp, ctx, l, assigned, taken, left, single=True)
            if one is not None and (got is None or len(one) > len(got)):
                got = one
                plan.setdefault("single_commodity", []).append(l)
        return got or {}
    real = [l for l in ctx["layers"] if not l.startswith("extra")]
    per_layer = {}
    for l in real:
        assigned = [(k, t) for k, (ll, t) in chosen.items() if ll == l]
        if assigned:
            per_layer[l] = (assigned, layer_plan(l, assigned))
    # the balls the rounding left out: each layer in turn takes them if it then escapes more
    for l in real:
        lost = [k for k in ctx["sig"] if not any(k in got for _a, got in per_layer.values())]
        if not lost or (deadline is not None and time.monotonic() > deadline):
            break
        add = []
        for k in lost:
            if l == ctx["B"]:
                add.append((k, None))
            else:
                t = next((t for t in _neighbours_diag(k) if ok.get((k, t)) and t not in taken), None)
                if t is not None:
                    add.append((k, t))
        if not add:
            continue
        old_a, old_g = per_layer.get(l, ([], {}))
        mine = {k for k, _t in old_a}
        add = [(k, t) for k, t in add if k not in mine]
        if not add:
            continue
        for k, t in add:
            if t is not None:
                taken.add(t)
        got = layer_plan(l, old_a + add)
        if len(got) > len(old_g):
            per_layer[l] = (old_a + add, got)
            for k, t in add:
                chosen[k] = (l, t)
        for k, t in add:
            if t is not None and k not in got:
                taken.discard(t)
    for l, (assigned, got) in per_layer.items():
        for k, (s, nodes) in got.items():
            paths[k] = dict(layer=l, side=s, site=dict(assigned)[k], nodes=nodes)
    plan["planned"] = len(paths)
    plan["plane_vias"] = len(plane_vias)
    plan["by_layer"] = {l: sum(1 for q in paths.values() if q["layer"] == l) for l in ctx["layers"]}
    plan["seconds"] = round(time.monotonic() - t0, 1)
    return plan, ctx, paths, plane_vias


def bound(sp, pkg, info, opts=None, **kw):
    """(LP bound on the escapable signal balls, ctx, duals): one commodity on every layer,
    the board's legal minimum width, and the relaxations in `kw` (override, extra_layers,
    open_planes)."""
    ctx = _setup(sp, pkg, info, opts, minimum=True, **kw)
    ok = _site_ok(sp, ctx, override=kw.get("override"))
    # plane balls' vias left out: the bound only credits the signal balls more room
    M, opt, plane, _ = _stage1(sp, ctx, ok, planes=False)
    obj, x, duals = M.solve(integer=False)
    if x is None:
        return None, ctx, {}
    return float(sum(x[v] for v in opt.values())), ctx, duals


def certificate(sp, pkg, info, opts=None, log=print, deadline=None):
    """None when the LP bound reaches the demand; else the blocked entry for the package."""
    esc, meta, duals = bound(sp, pkg, info, opts)
    demand = len(meta["sig"])
    if esc is None or esc >= demand - 0.5:
        return None
    short = demand - int(math.floor(esc + 1e-6))
    groups = {}
    for tag, dv in duals.items():
        groups[tag] = groups.get(tag, 0.0) + dv
    R = meta["R"]
    cut = [dict(kind=k, layer=l, ring=ring, tracks=cp, width=round(R[l]["w"], 4), clearance=round(R[l]["c"], 4),
                between=(f"balls {meta['d']:.3f} mm, {R[l]['c_pad']:.3f} mm from them" if l == meta["layers"][0]
                         else f"vias {R[l]['D']:.3f} mm"),
                weight=round(w_, 2))
           for (k, l, ring, cp), w_ in sorted(groups.items(), key=lambda kv: -kv[1])[:3]]
    real = meta["real"]
    relax = []

    def ok(e):
        return e is not None and e >= demand - 0.5

    def more_time():
        return deadline is None or time.monotonic() < deadline
    w0 = min(R[l]["w"] for l in real)
    for w in [v for v in WIDTH_LADDER if v < w0 - 1e-6]:
        if not more_time():
            break
        e, _m, _d = bound(sp, pkg, info, opts, override=dict(w=w))
        if ok(e):
            relax.append(dict(rule="track width", value=w, escapable=round(e, 1), all=True))
            break
    c = min(R[l]["c"] for l in real) - CLEARANCE_STEP
    while c >= 0.05 - 1e-9 and more_time():
        e, _m, _d = bound(sp, pkg, info, opts, override=dict(c=round(c, 4)))
        if ok(e):
            relax.append(dict(rule="clearance", value=round(c, 4), escapable=round(e, 1), all=True))
            break
        c -= CLEARANCE_STEP
    cp0 = R[real[0]].get("c_pad") or 0.0
    if cp0 > min(R[l]["c"] for l in real) + 1e-6:
        # the pads' requirement is above the clearance: the solder-mask aperture (expansion,
        # mask-to-copper) or a pad rule binds
        c = cp0 - CLEARANCE_STEP
        while c >= 0.05 - 1e-9 and more_time():
            e, _m, _d = bound(sp, pkg, info, opts, override=dict(c_pad=round(c, 4)))
            if ok(e):
                relax.append(dict(rule="ball-to-track clearance (solder-mask aperture: expansion + mask-to-copper)",
                                  value=round(c, 4), escapable=round(e, 1), all=True))
                break
            c -= CLEARANCE_STEP
    D = min(R[l]["D"] for l in real) - 0.05
    dr = min(R[l]["drill"] for l in real)
    while D >= dr + 0.1 - 1e-9 and more_time():
        e, _m, _d = bound(sp, pkg, info, opts, override=dict(D=round(D, 4)))
        if ok(e):
            relax.append(dict(rule="via diameter", value=round(D, 4), escapable=round(e, 1), all=True))
            break
        D -= 0.05
    from .translate import plane_layers
    pls = sorted(plane_layers(info))
    if pls and more_time():
        e, _m, _d = bound(sp, pkg, info, opts, open_planes=True)
        relax.append(dict(rule="signals on plane layers " + ",".join(pls), escapable=round(e or 0, 1), all=ok(e)))
    for n in (2, 4):
        if not more_time():
            break
        e, _m, _d = bound(sp, pkg, info, opts, extra_layers=n)
        relax.append(dict(rule=f"{n} more signal layers", escapable=round(e or 0, 1), all=ok(e)))
        if ok(e):
            break
    ref = pkg["ref"]
    for r in relax:
        r["kicad"] = _kicad_edit(ref, r, real)
    b = cut[0] if cut else None
    where = (f"the {b['kind']}s of ring {b['ring']} on {b['layer']} hold {b['tracks']} track(s) at "
             f"{b['width']}/{b['clearance']} mm between {b['between']}") if b else "no single cut"
    fixes = [f"{r['rule']} {r['value']} mm" if "value" in r else r["rule"] for r in relax if r.get("all")]
    summary = (f"{pkg['ref']}: {short} of {demand} signal balls can't escape on {len(real)} layers "
               f"({', '.join(real)}; LP bound {esc:.1f}); {where}; feasible with "
               + (" or ".join(fixes) if fixes else "none of the relaxations tried"))
    log("escape certificate " + summary)
    return dict(package=pkg["ref"], cause="rule", constraint="escape", demand=demand, escapable=round(esc, 1),
                short=short, layers=real, cut=cut, relaxations=relax, summary=summary, source="board",
                where=".kicad_pro net classes and board setup, .kicad_dru rules")


def _kicad_edit(ref, r, layers):
    """How a relaxation is written back in KiCad (for the caller; kae never relaxes a rule)."""
    rule, v = r["rule"], r.get("value")
    scope = f"(condition \"A.insideCourtyard('{ref}')\")"
    if rule == "track width":
        return f".kicad_dru: (rule \"{ref} escape\" {scope} (constraint track_width (min {v}mm)))"
    if rule == "clearance":
        return f".kicad_dru: (rule \"{ref} escape\" {scope} (constraint clearance (min {v}mm)))"
    if rule.startswith("ball-to-track"):
        return ("board setup: solder mask expansion / mask-to-copper clearance (or the pads' own mask "
                f"expansion in {ref}) so that a track keeps {v} mm from a ball")
    if rule == "via diameter":
        return f"board setup / net class via diameter {v} mm (or a via type: micro or blind via, via-in-pad)"
    if rule.startswith("signals on plane"):
        return "route signals on the plane layers (kae: --set escape_plane_layers=true, --planes allow)"
    if "more signal layers" in rule:
        return f"stackup: {rule} (board setup, physical stackup), {len(layers)} now"
    return ""


def _across(p, q):
    """`p`'s width across the row it shares with neighbour `q`."""
    ang = math.atan2(q.pos[1] - p.pos[1], q.pos[0] - p.pos[0])
    ux, uy = math.cos(ang), math.sin(ang)
    g = p.geom
    pts = list(g.exterior.coords) if hasattr(g, "exterior") else [(g.bounds[0], g.bounds[1]), (g.bounds[2], g.bounds[3])]
    xs = [(x - p.pos[0]) * ux + (y - p.pos[1]) * uy for x, y in pts]
    return max(xs) - min(xs)


def ring_certificate(sp, pkg, log=print):
    """A fine-pitch pad ring (QFN, QFP): the signal pads a track of the board's minimum width
    cannot leave between its two neighbours (a track's end lies inside its pad, so it runs
    alongside both neighbours) -> the blocked entry, or None."""
    count = _counts(sp)
    bad, total, need_w, need_c, detail = 0, 0, [], [], None
    for p in pkg["pads"]:
        if not p.net or count.get(p.net, 0) < 2:
            continue
        nb = sorted(((math.dist(p.pos, q.pos), id(q), q) for q in pkg["pads"] if q is not p))[:2]
        if len(nb) < 2:
            continue
        pitch = nb[0][0]
        if pitch > RING_PITCH or abs(nb[1][0] - pitch) > 0.05 * pitch:
            continue        # coarse, or a row's end (it can leave sideways)
        total += 1
        a = _across(p, nb[0][2])
        mn, opt, _ = sp.width_limits(p.net, pkg["layer"])
        w = mn or opt or 0.1
        c = sp._generic_need(p.net, "track", pkg["layer"])
        gap = pitch - a / 2 - w / 2
        if gap < c - 1e-6:
            bad += 1
            need_w.append(2 * (pitch - a / 2 - c))
            need_c.append(gap)
            detail = dict(pitch=round(pitch, 4), pad=round(a, 4), width=round(w, 4), clearance=round(c, 4),
                          gap=round(gap, 4))
    if not bad:
        return None
    wmax, cmax = min(need_w), min(need_c)
    fixes = ([f"track width {wmax:.3f} mm"] if wmax > 0.03 else []) + [f"clearance {cmax:.3f} mm"]
    rel = [dict(rule="track width", value=round(wmax, 4), all=wmax > 0.03),
           dict(rule="clearance", value=round(cmax, 4), all=True)]
    for r in rel:
        r["kicad"] = _kicad_edit(pkg["ref"], r, [pkg["layer"]])
    summary = (f"{pkg['ref']}: {bad} of {total} signal pads can't be left by a track: pitch {detail['pitch']} mm, "
               f"pads {detail['pad']} mm wide, a {detail['width']} mm track keeps {detail['gap']} mm of the "
               f"{detail['clearance']} mm clearance to the next pad; feasible with " + " or ".join(fixes))
    log("escape certificate " + summary)
    return dict(package=pkg["ref"], cause="rule", constraint="escape", demand=total, escapable=total - bad,
                short=bad, cut=[dict(kind="pad exit", layer=pkg["layer"], **detail)],
                relaxations=rel,
                summary=summary, source="board", where=".kicad_pro net classes and board setup, .kicad_dru rules")


# ----------------------------------------------------------------------------- laying
def _lay_grid(sp, ctx, paths, plane_vias, info, deadline=None):
    """Lay a plan: the plane balls' and the planned dog-bones, then each escape on its layer
    along its planned path (through the middle of each gap, side by side where several
    share one), checked exactly, else searched with the grid router to a box past the
    package's edge. Returns one record per planned ball."""
    from .critical_grid import Anchor, GridRouter
    from .lastmile import _commit
    zclr = max([float(z.get("clearance") or 0.0) for z in info.get("zones") or []] + [0.0])
    B, xy, p, balls, R = ctx["B"], ctx["xy"], ctx["p"], ctx["balls"], ctx["R"]
    owner = ("escape", ctx["ref"])

    def dog_bone(pd, t):
        v = xy(t[0] / 2, t[1] / 2)
        if sp.via_violations(pd.net, *v, first=True) or \
                _starves(sp, pd.net, Point(v), sp.via_size(pd.net)[0] / 2, sp.cu, zclr):
            return None
        mn, opt, _ = sp.width_limits(pd.net, B)
        for wd in [w for w in dict.fromkeys([opt, mn]) if w] or [0.1]:
            if sp.track_violations(pd.net, B, wd, pd.pos, v, first=True) or \
                    _starves(sp, pd.net, LineString([pd.pos, v]), wd / 2, [B], zclr):
                continue
            sp.add_via(pd.net, *v, owner=owner, uuid=W.new_uuid())
            sp.add_track(pd.net, B, wd, pd.pos, v, owner=owner, uuid=W.new_uuid())
            return v
        return None
    for k, t in plane_vias:
        dog_bone(balls[k][0], t)
    vias = {k: dog_bone(balls[k][0], q["site"]) for k, q in paths.items() if q["site"] is not None}
    slots = {}
    for q in paths.values():
        for nd in q["nodes"]:
            if nd[0] == "g":
                key = (q["layer"], nd[1])
                slots[key] = [slots.get(key, [0, 0])[0] + 1, 0]
    gr = GridRouter(sp)
    recs = []
    # the least flexible first on each layer (fewest options: they cannot go elsewhere)
    flex = ctx.get("flex", {})
    for k in sorted(paths, key=lambda k: (ctx["layers"].index(paths[k]["layer"]),
                                          flex.get(k, {}).get("options", 0), -balls[k][1], len(paths[k]["nodes"]))):
        q, pd = paths[k], balls[k][0]
        l = q["layer"]
        rec = dict(pad=f"{pd.owner[0]}.{pd.owner[1]}", net=pd.net, ring=balls[k][1], layer=l, side=q["side"],
                   via=None, exit=None, laid=False, **flex.get(k, {}))
        recs.append(rec)
        if q["site"] is not None:
            v = vias.get(k)
            if v is None:
                continue
            rec["via"] = [round(v[0], 4), round(v[1], 4)]
        if deadline is not None and time.monotonic() > deadline:
            continue
        start = pd.pos if l == B else tuple(rec["via"])
        pts = _plan_points(ctx, q, start, slots, R[l]["w"] + R[l]["c"])
        rec["exit"] = [round(pts[-1][0], 4), round(pts[-1][1], 4)]
        mn, opt, _ = sp.width_limits(pd.net, l)
        for wd in [w for w in dict.fromkeys([opt, mn]) if w] or [0.1]:
            if DEBUG:
                rec["pts"] = [[round(a, 3), round(b, 3)] for a, b in pts]
                rec["nodes"] = q["nodes"]
                rec["why"] = [str(sp.track_violations(pd.net, l, wd, a_, b_, first=True))[:120] for a_, b_ in zip(pts, pts[1:])]
            if all(not sp.track_violations(pd.net, l, wd, a_, b_, first=True) for a_, b_ in zip(pts, pts[1:])):
                for a_, b_ in zip(pts, pts[1:]):
                    sp.add_track(pd.net, l, wd, a_, b_, owner=owner, uuid=W.new_uuid())
                rec["laid"] = "plan"
                break
        if rec["laid"]:
            continue
        cxy = pts[-1]
        tgt = Anchor(box(cxy[0] - p / 2, cxy[1] - p / 2, cxy[0] + p / 2, cxy[1] + p / 2), (l,), centre=cxy, kind="track")
        if l == B:
            src = [Anchor(pd.geom, (B,), centre=pd.pos)]
        else:
            src = [Anchor(Point(start).buffer(sp.via_size(pd.net)[0] / 2), (l,), centre=start, kind="via")]
        win = gr.window(src + [tgt], margin=1.5 * p)
        for wd in [w for w in dict.fromkeys([opt, mn]) if w] or [0.1]:
            rt = gr.connect(pd.net, src, [tgt], wd, [l], via=False, window=win)
            if rt is not None and (rt.segs or rt.vias):
                new = _commit(sp, rt)
                if new is not None:
                    for it in new:
                        it.owner = owner
                    rec["laid"] = "search"
                    break
    return recs


def _plan_points(ctx, q, start, slots, step):
    """Board points of a planned escape: `start` (ball or via), the middle of each gap on its
    path (the k-th of n tracks in a gap offset by (k - (n - 1) / 2) * step along it) and the
    centre of each tile it turns in, then 0.75 pitch out past the package's edge."""
    xy, p, l = ctx["xy"], ctx["p"], q["layer"]
    par = 0 if l == ctx["B"] else 1
    idx = []
    last_dir = None

    def tiles_of(g):
        gx, gy = g
        return {(gx - 1, gy), (gx + 1, gy)} if gx % 2 == par else {(gx, gy - 1), (gx, gy + 1)}
    prev = None
    for nd in q["nodes"][1:]:
        if nd[0] == "g" and prev is not None and prev[0] == "g":
            # round a corner of the tile both gaps bound: through its centre, clear of the corner
            common = tiles_of(prev[1]) & tiles_of(nd[1])
            if common:
                cx_, cy_ = next(iter(common))
                idx.append((cx_ / 2, cy_ / 2))
        prev = nd
        if nd[0] == "g":
            gx, gy = nd[1]
            key = (l, nd[1])
            n, k = slots.get(key, [1, 0])
            if key in slots:
                slots[key][1] += 1
            off = (k - (n - 1) / 2) * step / p
            along_y = gx % 2 == par            # its corners are above and below each other
            idx.append((gx / 2, gy / 2 + off) if along_y else (gx / 2 + off, gy / 2))
        elif nd[0] == "c":
            continue                           # straight across a tile: the gaps' middles suffice
        elif nd[0] == "sink":
            last_dir = {"W": (-1, 0), "E": (1, 0), "S": (0, -1), "N": (0, 1)}[nd[1]]
    if last_dir is None:
        last_dir = (0, 0)
    s0 = q["nodes"][0][1]
    last = idx[-1] if idx else (s0[0] / 2, s0[1] / 2)
    idx.append((last[0] + 0.75 * last_dir[0], last[1] + 0.75 * last_dir[1]))
    return _simplify([start] + [xy(*m) for m in idx])


def _simplify(pts):
    """`pts` without repeated and collinear points."""
    out = []
    for q in pts:
        q = (float(q[0]), float(q[1]))
        if out and math.dist(out[-1], q) < 1e-6:
            continue
        if len(out) >= 2:
            (x0, y0), (x1, y1) = out[-2], out[-1]
            if abs((x1 - x0) * (q[1] - y0) - (y1 - y0) * (q[0] - x0)) < 1e-9:
                out[-1] = q
                continue
        out.append(q)
    return out


def _routed_inside(sp, pkg):
    """Tracks and vias of the input inside the package's pad box."""
    xs = [p.pos[0] for p in pkg["pads"]]
    ys = [p.pos[1] for p in pkg["pads"]]
    bb = (min(xs), min(ys), max(xs), max(ys))
    seen = set()
    for l in sp.cu:
        for it in sp.query(l, bb):
            if it.kind in ("track", "via"):
                seen.add(id(it))
    return len(seen)


def run(sp, info, opts=None, log=print, deadline=None):
    """Plan, certify and lay the escapes of every ball grid; check fine-pitch pad rings.
    Returns {packages, blocked, laid, wanted} (blocked: kae.route.blocked entries)."""
    opts = opts or {}
    out = dict(packages=[], blocked=[], laid=0, wanted=0)
    lay = opts.get("escape_lay", True)
    for pkg in find_packages(sp):
        try:
            if pkg["kind"] == "ring":
                c = ring_certificate(sp, pkg, log=log)
                if c:
                    out["blocked"].append(c)
                    out["packages"].append(dict(ref=pkg["ref"], kind="ring", certificate=c["summary"]))
                continue
            if deadline is not None and time.monotonic() > deadline:
                log(f"escape plan {pkg['ref']}: no time left")
                continue
            routed = _routed_inside(sp, pkg)
            if routed > 0.2 * len(pkg["pads"]):
                # a board that is routed already (a restart resuming from its best board): its
                # escapes are there; a plan around them would not be laid
                log(f"escape plan {pkg['ref']}: {routed} tracks and vias already in its ball field; not planned")
                continue
            plan, ctx, paths, plane_vias = plan_grid(sp, pkg, info, opts, deadline=deadline)
            cert = certificate(sp, pkg, info, opts, log=log, deadline=deadline)
            if cert:
                out["blocked"].append(cert)
                plan["certificate"] = cert["summary"]
            recs = _lay_grid(sp, ctx, paths, plane_vias, info, deadline=deadline) if lay else []
            plan["escapes"] = recs
            plan["laid"] = sum(1 for r in recs if r["laid"])
            plan["vias_laid"] = sum(1 for r in recs if r["via"])
            out["laid"] += plan["laid"]
            out["wanted"] += plan.get("planned", 0)
            log(f"escape plan {pkg['ref']}: pitch {plan['pitch']:.3f}, {plan['signal']} signal and "
                f"{plan['plane']} plane balls; LP {plan.get('lp')}, planned {plan.get('planned')} {plan.get('by_layer')}, "
                f"{plan.get('plane_vias')} plane dog-bones; laid {plan['laid']} escapes and {plan['vias_laid']} "
                f"vias ({plan.get('seconds')} s, {plan['variables']} variables)")
            out["packages"].append(plan)
        except Exception as e:  # noqa: BLE001 - a plan that fails leaves the package to the router
            import traceback
            log(f"escape plan {pkg['ref']}: failed: {type(e).__name__}: {e} {traceback.format_exc(limit=3)}")
            out["packages"].append(dict(ref=pkg["ref"], error=f"{type(e).__name__}: {e}"))
    return out
