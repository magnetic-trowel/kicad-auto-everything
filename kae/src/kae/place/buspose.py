# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Bus pose compiler: pick the rotations of a bus's end parts from pin tables alone.

Whether the lines of a bus between two parts can run without crossing, and how long they are,
depends on the end parts' rotations far more than on where along their axis the parts sit: for
each pair of rotations of the two ends the pin order at A against the pin order at B is a table
lookup, computed from footprint geometry. The longest non-crossing subset of the lines (the
planar share) and the minimum number of planar layers (the longest decreasing subsequence, Greene/RSK) follow.
kae's bus gap to the human is mostly a rotation gap (placement.md, section 0).

Input is only the netlist (which parts share at least MIN_LINES signal lines, traced through
two-pin series parts) and the footprints: never a human placement. `detect` finds the buses and
`compile_poses` / `final_pass` / `seed_pose` choose rotations.

Bus quality for a rotation pair (a table lookup, same measure as the campaign's analysis,
tools/research/bus_pose/):
  lis: the largest share of lines with no two crossing (planar share),
  lds: the longest decreasing subsequence, the layers needed,
  L: total line length (straight lines between pads).

`final_pass` runs after legalization: every legal right-angle turn of a bus end that keeps
the part's pad centre (a small nudge allowed) goes into a joint choice per connected set of
parts sharing buses, planarity first (or length first), HPWL of the part's other nets as a
priced term, turns that worsen physics or add a legality finding never kept.
`seed_pose` is the same choice before the floorplan, when nothing is placed yet; the chosen
rotation is then held through the floorplan, annealer and legalizers (Part.rot_hold).

Mirrors (flipping a part to the other side) need a side-assignment move the placer does not
have: a part keeps its side. Not offered here.
"""
from __future__ import annotations

import bisect
import itertools
import math
import time
from collections import defaultdict
from dataclasses import dataclass

import numpy as np

from .state import grid_violations

MIN_LINES = 6             # lines between two parts that make a bus
MAX_NET_PADS = 14         # above this a net is not a bus line (clocks, resets, enables)
MIN_IC_PADS = 6
MIN_IC_SIGNAL = 4
SERIES_NET_PADS = 5
ENUM_LIMIT = 200_000      # product of domain sizes up to which a part group is enumerated exactly
NUDGE_MM = 1.0


@dataclass
class Bus:
    a: int
    b: int
    pa: np.ndarray        # pad indices on part a, one per line
    pb: np.ndarray
    nets: list            # per line: tuple of net indices (series parts joined)
    series: list          # per line: series part indices

    @property
    def n(self):
        return len(self.pa)


def _signal(net):
    return net.kind not in ("ground", "power") and len(net.pins) <= MAX_NET_PADS


def _ic(P):
    """Parts with at least MIN_IC_PADS connected pads, at least MIN_IC_SIGNAL of them signal."""
    out = {}
    for p in P.parts:
        conn = [(k, j) for k, j in enumerate(p.pad_net) if j >= 0]
        if len(conn) >= MIN_IC_PADS and sum(1 for k, j in conn if P.nets[j].kind not in ("ground", "power")) >= MIN_IC_SIGNAL:
            out[p.i] = conn
    return out


def detect(P, min_lines=MIN_LINES):
    """[Bus] between pairs of ICs of the Problem joined by at least min_lines signal lines.

    A line is one signal net or several joined through a two-pin part between signal nets of at
    most SERIES_NET_PADS pads; a line with more than one pad on a part uses its first. Multi-drop
    lines appear in every pair of parts they touch. Uses only the nets and the footprints, not any
    placement."""
    ic = _ic(P)
    par = {net.i: net.i for net in P.nets}

    def find(x):
        while par[x] != x:
            par[x] = par[par[x]]
            x = par[x]
        return x
    series_of = {}
    for p in P.parts:
        if p.i in ic:
            continue
        conn = [j for j in p.pad_net if j >= 0]
        if len(conn) == 2 and conn[0] != conn[1] and _signal(P.nets[conn[0]]) and _signal(P.nets[conn[1]]) \
                and len(P.nets[conn[0]].pins) <= SERIES_NET_PADS and len(P.nets[conn[1]].pins) <= SERIES_NET_PADS:
            par[find(conn[0])] = find(conn[1])
            series_of[frozenset(conn)] = p.i
    groups = defaultdict(list)
    for net in P.nets:
        if _signal(net):
            groups[find(net.i)].append(net.i)
    lines = []
    for nets in groups.values():
        pins = [pin for j in nets for pin in P.nets[j].pins]
        if len(pins) > MAX_NET_PADS:
            continue
        ends = defaultdict(list)
        for (i, k) in pins:
            if i in ic:
                ends[i].append(k)
        if len(ends) < 2:
            continue
        ser = sorted({s for pr, s in series_of.items() if all(j in nets for j in pr)})
        lines.append((tuple(sorted(nets)), dict(ends), ser))
    pairs = defaultdict(list)
    for nets, ends, ser in lines:
        refs = sorted(ends)
        for x in range(len(refs)):
            for y in range(x + 1, len(refs)):
                pairs[(refs[x], refs[y])].append((nets, ends, ser))
    out = []
    for (a, b), L in pairs.items():
        if len(L) >= min_lines:
            out.append(Bus(a, b,
                           np.array([e[a][0] for _, e, _ in L], dtype=int),
                           np.array([e[b][0] for _, e, _ in L], dtype=int),
                           [nt for nt, _, _ in L], [s for _, _, s in L]))
    out.sort(key=lambda B: (-B.n, B.a, B.b))
    return out


# ------------------------------------------------------------------ planarity
def _lnds(seq):
    t = []
    for x in seq:
        k = bisect.bisect_right(t, x)
        if k == len(t):
            t.append(x)
        else:
            t[k] = x
    return len(t)


def _lds_strict(seq):
    t = []
    for x in seq:
        v = -x
        k = bisect.bisect_left(t, v)
        if k == len(t):
            t.append(v)
        else:
            t[k] = v
    return len(t)


def planarity(pa, pb, ca, cb):
    """(lis share, lds, crossing share) of the lines pa[i]-pb[i]: largest planar share of the
    lines and the layers needed, the better of two frames (projection on the bus normal; cyclic
    order around each part's centre from the direction to the other end)."""
    n = len(pa)
    if n < 2:
        return 1.0, 1, 0.0
    u = cb - ca
    L = float(np.hypot(*u))
    if L < 1e-6:
        return 1.0, 1, 0.0
    u = u / L
    nv = np.array([-u[1], u[0]])
    p = np.round((pa - ca) @ nv, 2)
    q = np.round((pb - cb) @ nv, 2)
    order = np.lexsort((q, p))
    qs = [float(x) for x in q[order]]
    lis1, lds1 = _lnds(qs), _lds_strict(qs)

    def ang(pts, c, d):
        v = pts - c
        return np.round(np.arctan2(v @ np.array([-d[1], d[0]]), v @ d), 2)
    pc = ang(pa, ca, u)
    qc = -ang(pb, cb, -u)
    order = np.lexsort((qc, pc))
    qs2 = [float(x) for x in qc[order]]
    lis2, lds2 = _lnds(qs2), _lds_strict(qs2)
    dp = np.sign(p[:, None] - p[None, :])
    dq = np.sign(q[:, None] - q[None, :])
    iu = np.triu_indices(n, 1)
    inv = float(((dp * dq)[iu] < 0).sum()) / (n * (n - 1) / 2)
    return max(lis1, lis2) / n, min(lds1, lds2), inv


# ------------------------------------------------------------------ rotations of one part
def pin_centre(p, k):
    """The centre of part p's pad bounding box at rotation index k, from its origin (mm)."""
    pins = p.rots[k].pins
    return (float(pins[:, 0].min() + pins[:, 0].max()) / 2.0, float(pins[:, 1].min() + pins[:, 1].max()) / 2.0)


def ortho_rots(p, hold):
    """Rotation indices a part may turn to: its right angles (its current one first is the
    caller's business), or nothing if held."""
    if not p.movable or p.i in hold or getattr(p, "rot_hold", False):
        return []
    return list(range(getattr(p, "n_ortho", len(p.rots))))


def turned_origin(P, st, i, k):
    """Grid origin (X, Y) of part i turned to rotation k about its pad centre."""
    p = P.parts[i]
    cx0, cy0 = pin_centre(p, int(st.K[i]))
    cx1, cy1 = pin_centre(p, k)
    x, y = st.xy(i)
    return P.grid_of(x + cx0 - cx1, y + cy0 - cy1)


def bus_positions(P, st, i, pads, k):
    """Part i's pad positions for its rotation index k about its current pad centre (mm), and
    that centre."""
    p = P.parts[i]
    k0 = int(st.K[i]) if p.movable else 0
    cx0, cy0 = pin_centre(p, k0)
    cx1, cy1 = pin_centre(p, k)
    x, y = st.xy(i)
    c = np.array([x + cx0, y + cy0])
    return p.rots[k].pins[pads] - np.array([cx1, cy1]) + c, c


# ------------------------------------------------------------------ legality of one turn
class Occupancy:
    """Grid occupancy of every part and obstacle, for one-against-all checks of a turned part."""

    def __init__(self, P, st):
        self.P, self.st = P, st
        self.rect_lists = {0: [], 1: []}
        self.owner = {0: [], 1: []}
        for i in P.mov:
            for side, r, _ in st.grid_rects(i):
                self.rect_lists[side].append(r)
                self.owner[side].append(i)
        self.obst = {0: [], 1: []}
        for ob in P.obstacles:
            self.obst[ob.side].append(ob.g)
        self.R = {s: np.asarray(v, dtype=np.int64).reshape(-1, 4) for s, v in self.rect_lists.items()}
        self.O = {s: np.asarray(v, dtype=np.int64).reshape(-1, 4) for s, v in self.obst.items()}
        self.own = {s: np.asarray(v, dtype=np.int64) for s, v in self.owner.items()}
        base = grid_violations(st)
        self.base_hits = {}        # part -> set of parts it already overlaps; -1 for an obstacle
        self.base_outline = {}
        for i, why in base.items():
            hits = set()
            for w in why:
                if w[0] == "overlap":
                    hits.add(w[1])
                elif w[0] == "obstacle":
                    hits.add(-1)
                elif w[0] == "outline":
                    self.base_outline[i] = w[1]
            self.base_hits[i] = hits

    def rects_at(self, i, X, Y, k):
        p = self.P.parts[i]
        r = p.rots[k]
        si = 0 if p.s > 0 else 1
        out = [(si, (X + a, X + b, Y + c, Y + d)) for (a, b, c, d) in (r.g_own_rects or (r.g_own,))]
        for (a, b, c, d) in r.g_opp:
            out.append((1 - si, (X + a, X + b, Y + c, Y + d)))
        return out

    def _hits(self, R, r):
        if len(R) == 0:
            return np.array([], dtype=bool)
        a, b, c, d = r
        return (np.minimum(R[:, 1], b) > np.maximum(R[:, 0], a)) & (np.minimum(R[:, 3], d) > np.maximum(R[:, 2], c))

    def legal(self, i, X, Y, k):
        """No grid violation for part i at (X, Y, k) that it does not already have."""
        P = self.P
        base = self.base_hits.get(i, set())
        for side, r in self.rects_at(i, X, Y, k):
            m = self._hits(self.R[side], r)
            if m.any():
                owners = set(int(o) for o in self.own[side][m]) - {i}
                if owners - base:
                    return False
            if self._hits(self.O[side], r).any() and -1 not in base:
                return False
        n = P.outside_cells_all(X, Y, P.parts[i].rots[k].g_boards)
        return n <= self.base_outline.get(i, 0)


def _nudges(step_cells):
    """Grid offsets (dx, dy) within step_cells, nearest first, (0, 0) first."""
    out = [(0, 0)]
    if step_cells <= 0:
        return out
    pts = [(dx, dy) for dx in range(-step_cells, step_cells + 1) for dy in range(-step_cells, step_cells + 1) if (dx, dy) != (0, 0)]
    pts.sort(key=lambda t: (t[0] * t[0] + t[1] * t[1], t))
    return out + pts


# ------------------------------------------------------------------ the choice
def table(P, st, bus, ka, kb):
    """(lis, lds, length mm) of bus for rotations ka, kb of its ends, each ends' turn about its
    current pad centre."""
    pa, ca = bus_positions(P, st, bus.a, bus.pa, ka)
    pb, cb = bus_positions(P, st, bus.b, bus.pb, kb)
    lis, lds, _ = planarity(pa, pb, ca, cb)
    return lis, lds, float(np.hypot(pb[:, 0] - pa[:, 0], pb[:, 1] - pa[:, 1]).sum())


def foreign_hpwl_delta(P, st, i, k, bus_nets):
    """Change in weighted HPWL of part i's nets that are not bus lines when it turns to rotation
    k about its pad centre (mm), the others staying put."""
    p = P.parts[i]
    X, Y = turned_origin(P, st, i, k)
    r_new = p.rots[k]
    x_new, y_new = P.ox + X * P.g, P.oy + Y * P.g
    r_old = p.rots[int(st.K[i])]
    xo, yo = st.xy(i)
    tot = 0.0
    nets = {j for j in p.pad_net if j >= 0 and j not in bus_nets}
    for j in nets:
        net = P.nets[j]
        if len(net.pins) > 60:
            continue
        pts_old, pts_new = [], []
        for (q, pad) in net.pins:
            if q == i:
                pts_old.append(r_old.pins[pad] + np.array([xo, yo]))
                pts_new.append(r_new.pins[pad] + np.array([x_new, y_new]))
            else:
                v = st.pins_xy(q)[pad]
                pts_old.append(v)
                pts_new.append(v)
        A, B = np.array(pts_old), np.array(pts_new)
        tot += net.weight * ((np.ptp(B[:, 0]) + np.ptp(B[:, 1])) - (np.ptp(A[:, 0]) + np.ptp(A[:, 1])))
    return tot


def _cost(mode, lis, lds, L, L0, n):
    if mode == "planar":
        return n * (1.0 - lis) + 0.5 * (lds - 1) + 0.01 * L / max(L0, 1e-6)
    return L / max(L0, 1e-6) * n + 0.05 * n * (1.0 - lis)


def _solve(parts, domains, score, seed=0):
    """argmin over rotation choices (one per part, from domains) of score(assign): exactly
    when the product of domain sizes is small enough, else by coordinate descent from the
    first entries (the current rotations), a few sweeps and two restarts."""
    sizes = [len(domains[i]) for i in parts]
    total = 1
    for s in sizes:
        total *= s
    if total <= ENUM_LIMIT:
        best, bv = None, math.inf
        for combo in itertools.product(*[domains[i] for i in parts]):
            a = dict(zip(parts, combo))
            v = score(a)
            if v < bv - 1e-12:
                best, bv = a, v
        return best
    import random
    rng = random.Random(seed)
    best, bv = None, math.inf
    for restart in range(3):
        a = {i: domains[i][0] for i in parts}
        if restart:
            for i in parts:
                a[i] = rng.choice(domains[i])
        improved = True
        sweeps = 0
        while improved and sweeps < 12:
            improved = False
            sweeps += 1
            for i in parts:
                cur = a[i]
                bk, bv2 = cur, score(a)
                for k in domains[i]:
                    if k == cur:
                        continue
                    a[i] = k
                    v = score(a)
                    if v < bv2 - 1e-12:
                        bv2, bk = v, k
                a[i] = bk
                if bk != cur:
                    improved = True
        v = score(a)
        if v < bv - 1e-12:
            best, bv = dict(a), v
    return best


def components(buses):
    """Connected sets of parts (joined by shared buses)."""
    par = {}

    def find(x):
        while par[x] != x:
            par[x] = par[par[x]]
            x = par[x]
        return x
    for b in buses:
        for x in (b.a, b.b):
            par.setdefault(x, x)
        par[find(b.a)] = find(b.b)
    comp = defaultdict(list)
    for x in par:
        comp[find(x)].append(x)
    return list(comp.values())


def compile_poses(P, st, buses, domains, score_extra, mode="planar", seed=0):
    """Choice of rotation for every part in `domains` ({i: [k, ...]}, the current rotation
    first, tried together by connected group) minimizing the bus scores plus score_extra(i, k).
    Returns {i: k} of parts whose rotation changes."""
    out = {}
    tables = {}
    for B in buses:
        L0 = table(P, st, B, *current_rots(P, st, B))[2]
        tables[id(B)] = (L0, {})

    def bus_val(B, ka, kb):
        L0, t = tables[id(B)]
        key = (ka, kb)
        if key not in t:
            lis, lds, L = table(P, st, B, ka, kb)
            t[key] = _cost(mode, lis, lds, L, L0, B.n)
        return t[key]
    for comp in components(buses):
        free = [i for i in comp if len(domains.get(i, ())) > 1]
        if not free:
            continue
        bs = [B for B in buses if B.a in comp or B.b in comp]

        def score(a):
            v = 0.0
            for B in bs:
                ka = a.get(B.a, int(st.K[B.a]) if P.parts[B.a].movable else 0)
                kb = a.get(B.b, int(st.K[B.b]) if P.parts[B.b].movable else 0)
                v += bus_val(B, ka, kb)
            for i, k in a.items():
                v += score_extra(i, k)
            return v
        res = _solve(free, domains, score, seed=seed)
        for i, k in (res or {}).items():
            if k != int(st.K[i]):
                out[i] = k
    return out


def current_rots(P, st, B):
    return (int(st.K[B.a]) if P.parts[B.a].movable else 0, int(st.K[B.b]) if P.parts[B.b].movable else 0)


def bus_summary(P, st, buses):
    """Per bus: a, b refs, lines, lis, lds, L (straight lines between pads) at the current poses."""
    out = []
    for B in buses:
        ka, kb = current_rots(P, st, B)
        lis, lds, L = table(P, st, B, ka, kb)
        out.append(dict(a=P.parts[B.a].ref, b=P.parts[B.b].ref, n=B.n, lis=round(lis, 3), lds=lds, L=round(L, 2)))
    return out


def final_pass(P, st, terms=None, zones=None, hold=(), mode="planar", x_mm=2.0, time_s=30.0, physics_veto=True,
               nudge_mm=NUDGE_MM, seed=0, log=None, buses=None):
    """After legalization: for each bus choose its ends' rotations (module docstring).

    A turn keeps the part's pad centre (up to nudge_mm); it is a candidate only if it adds no
    grid violation and no finding of the exact check, and, with physics_veto, does not worsen
    the place terms. Candidates of parts joined by buses are chosen together: mode "planar"
    minimizes non-planar lines first and bus length after; "length" the length first. Each
    candidate also pays for its other nets (weighted HPWL, x_mm per non-planar line in planar
    mode, 1 mm per mm of bus in length mode). Applied turns are re-checked jointly. Returns
    a report."""
    t0 = time.monotonic()
    t_end = t0 + time_s
    hold = set(hold)
    from .exact import ExactModel
    buses = list(detect(P)) if buses is None else buses
    rep = dict(mode=mode, buses=len(buses), x_mm=x_mm, physics_veto=bool(physics_veto), nudge_mm=nudge_mm)
    if not buses:
        rep["moved"] = 0
        return rep
    bus_nets = {j for B in buses for nets in B.nets for j in nets}
    rep["before"] = bus_summary(P, st, buses)
    ends = sorted({i for B in buses for i in (B.a, B.b)})
    occ = Occupancy(P, st)
    em = ExactModel(P, st)
    uuid = {p.i: p.uuid for p in P.parts}
    poses = {p.uuid: st.pose(p.i) for p in P.parts} if terms is not None else None
    tparts = set(terms.parts()) if terms is not None else set()
    domains, placements, counts = {}, {}, dict(not_movable=0, turned_candidates=0, grid_illegal=0, exact_illegal=0,
                                               physics_veto=0, zones_veto=0, nudged=0)
    steps = int(round(nudge_mm / P.g))
    grid_x = P.grid_of
    extra = {}

    def physics_ok(i):
        if terms is None or uuid[i] not in tparts or not physics_veto:
            return True
        new = {uuid[i]: st.pose(i)}
        return terms.delta(poses, [uuid[i]], new) <= 1e-9

    for i in ends:
        p = P.parts[i]
        dom = ortho_rots(p, hold)
        k0 = int(st.K[i]) if p.movable else 0
        domains[i] = [k0]
        if not dom:
            if p.movable:
                counts["not_movable"] += 1
            continue
        for k in dom:
            if k == k0:
                continue
            counts["turned_candidates"] += 1
            if time.monotonic() > t_end:
                continue
            X0, Y0 = turned_origin(P, st, i, k)
            spot = None
            for dx, dy in _nudges(steps):
                if occ.legal(i, X0 + dx, Y0 + dy, k):
                    spot = (X0 + dx, Y0 + dy, (dx, dy))
                    break
            if spot is None:
                counts["grid_illegal"] += 1
                continue
            X, Y, nud = spot
            base = {(f["type"], tuple(f["refs"])) for f in em.check(parts=[i])}
            old_pose = (int(st.X[i]), int(st.Y[i]), int(st.K[i]))
            em.set_pose(i, X, Y, k)
            findings = em.check(parts=[i])
            new = [f for f in findings if (f["type"], tuple(f["refs"])) not in base]
            ok = not new
            if ok and not physics_ok(i):
                ok = False
                counts["physics_veto"] += 1
            elif not ok:
                counts["exact_illegal"] += 1
            if ok and zones is not None and zones.part(i, X, Y, k) > zones.part(i, *old_pose) + 1e-9:
                ok = False
                counts["zones_veto"] += 1
            em.set_pose(i, *old_pose)
            if ok:
                domains[i].append(k)
                placements[(i, k)] = (X, Y)
                if nud != (0, 0):
                    counts["nudged"] += 1
    if mode == "planar":
        def score_extra(i, k):
            if (i, k) not in extra:
                extra[(i, k)] = foreign_hpwl_delta(P, st, i, k, bus_nets) / max(x_mm, 1e-3) if k != int(st.K[i]) else 0.0
            return extra[(i, k)]
    else:
        L_tot = sum(table(P, st, B, *current_rots(P, st, B))[2] for B in buses) or 1.0

        def score_extra(i, k):
            if (i, k) not in extra:
                extra[(i, k)] = (foreign_hpwl_delta(P, st, i, k, bus_nets) / L_tot) * sum(B.n for B in buses) if k != int(st.K[i]) else 0.0
            return extra[(i, k)]
    # candidates are chosen with the current rotations first, then applied with the joint check
    choice = compile_poses(P, st, buses, domains, score_extra, mode=mode, seed=seed)
    moved = []
    for i, k in sorted(choice.items()):
        prev = (int(st.X[i]), int(st.Y[i]), int(st.K[i]))
        X, Y = placements[(i, k)]
        st.X[i], st.Y[i], st.K[i] = X, Y, k
        em.set_pose(i, X, Y, k)
        moved.append((i, prev))
    # a joint check: the turned parts may touch each other
    while moved:
        idx = [i for i, _ in moved]
        bad = set(int(q) for q, _ in grid_violations(st).items() if q in idx) - {i for i in idx if i in occ.base_hits}
        exact_bad = {q for f in em.check(parts=idx) for q in f["parts"] if q in idx}
        drop = [i for i, _ in moved if i in bad or (i in exact_bad and i not in occ.base_hits)]
        if not drop:
            break
        for i, prev in [m for m in moved if m[0] in drop]:
            st.X[i], st.Y[i], st.K[i] = prev
            em.set_pose(i, *prev)
            counts.setdefault("joint_reverted", 0)
            counts["joint_reverted"] += 1
        moved = [m for m in moved if m[0] not in drop]
    rep.update(counts)
    rep["moved"] = len(moved)
    rep["turned"] = sorted(P.parts[i].ref for i, _ in moved)
    rep["after"] = bus_summary(P, st, buses)
    rep["seconds"] = round(time.monotonic() - t0, 3)
    if log:
        lis0 = sum(b["n"] * b["lis"] for b in rep["before"]) / max(1, sum(b["n"] for b in rep["before"]))
        lis1 = sum(b["n"] * b["lis"] for b in rep["after"]) / max(1, sum(b["n"] for b in rep["after"]))
        log(f"bus pose final ({mode}): {len(buses)} buses, {len(moved)} parts turned, planar lines {lis0:.3f} -> {lis1:.3f}")
    return rep


def seed_pose(P, st, hold=(), mode="planar", seed=0, log=None, buses=None):
    """Before the floorplan: choose each bus end's rotation from pin tables and set it (st.K,
    keeping the pad centre), holding it through the floorplan, annealer and legalizers (Part.rot_hold)."""
    t0 = time.monotonic()
    hold = set(hold)
    buses = list(detect(P)) if buses is None else buses
    rep = dict(mode=mode, buses=len(buses))
    if not buses:
        rep.update(moved=0, held=0)
        return rep
    ends = sorted({i for B in buses for i in (B.a, B.b)})
    domains = {}
    for i in ends:
        p = P.parts[i]
        dom = ortho_rots(p, hold)
        k0 = int(st.K[i]) if p.movable else 0
        domains[i] = [k0] + [k for k in dom if k != k0]
    choice = compile_poses(P, st, buses, domains, lambda i, k: 0.0, mode=mode, seed=seed)
    for i, k in sorted(choice.items()):
        X, Y = turned_origin(P, st, i, k)
        st.X[i], st.Y[i], st.K[i] = X, Y, k
    held = [i for i in ends if P.parts[i].movable and i not in hold and getattr(P.parts[i], "n_ortho", 1) > 1]
    for i in held:
        P.parts[i].rot_hold = True
    rep.update(moved=len(choice), held=len(held), turned=sorted(P.parts[i].ref for i in choice), seconds=round(time.monotonic() - t0, 3))
    if log:
        log(f"bus pose seed ({mode}): {len(buses)} buses, {len(choice)} parts turned, {len(held)} held")
    return rep
