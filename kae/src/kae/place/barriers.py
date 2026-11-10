# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Parts that belong on one side of a board's voids and barriers (E104, E105).

The placer sees the outline as a single mask. Copper cannot cross a void, and a rule area that
forbids tracks on every copper layer (HV isolation) is a wall as hard as an edge: a part on the wrong
side of one has opens that no router can close. Two cases:

**True split** (`true_split`): outline minus barriers falls into several regions (a panel of boards in
one file, a modular synth's PCB pair, an HV isolation channel across the board). The parts of a region
cannot reach another region at all, so the assignment is a hard constraint: each region is placed on
its own (`place_split`), with only its parts in the problem and the outline of the region, and the
poses merged. Connected regions need no constraint: copper goes around a slot.

**Soft term** (`reweight_crossing`, only `barrier_net_weight` > 1): a net crossing a barrier on a board
that is not split is a detour the placer does not see. Nets whose MST edges cross a barrier at the seed
get their weight multiplied; `crossings` reports what is left. Slots (oval drills) are holes, not walls.

Assignment (`assign`): each anchored part (locked, or the task's fixed interface) sits in the region
holding most of its pads. A movable part takes the region of the parts it talks to, by breadth-first
label propagation over signal nets, each net voting 1/(pins - 1) so a wide bus does not swamp a point
link; parts no anchor reaches go by power nets, then largest group first into the region with the most
room. Room is counted per side (a through-hole part takes both); a region side over CAPACITY gives up its
movable parts least tied to it to regions with room. A split still over capacity is not applied. Nothing here reads a human placement: only the task's outline, rule areas, anchors and nets.
Pins of nets that span regions are reported (`cross_nets`): a board that connects them with a cable has
those opens whatever the method does, the human layout included.
"""
from __future__ import annotations

import dataclasses
import time
from collections import defaultdict
from dataclasses import dataclass, field

import shapely
from shapely.geometry import LineString, Point, Polygon

MIN_REGION_SHARE = 0.02      # a piece of the outline under this share of the board is no region
CAPACITY = 0.85              # courtyards a region is assumed able to hold on each side, as a share of its area
SPLIT_MIN_S = 20.0           # the least time a region gets
SPLIT_VERIFY_FRAC = 0.1      # share of the budget kept for the caller's check of the merged board
MST_MAX_PINS = 60            # nets with more pins are planes in all but name: their MST says nothing


@dataclass
class Split:
    regions: list                                 # shapely polygons
    region_of: dict = field(default_factory=dict)  # footprint uuid -> region index (-1: none)
    cross_nets: list = field(default_factory=list)
    over_capacity: list = field(default_factory=list)  # regions whose parts exceed CAPACITY of the area
    how: dict = field(default_factory=dict)        # how many parts each rule assigned


def copper_layers(board):
    return sorted(n for n in (board.layers or {}) if n.endswith(".Cu"))


def _covers_all_copper(ko, cu):
    ly = set(ko.layers or ())
    return bool(cu) and ("*.Cu" in ly or all(c in ly for c in cu) or ("F&B.Cu" in ly and len(cu) == 2))


def barrier_polygons(board):
    """Board-level rule areas that no track may cross on any copper layer (a footprint's own
    rule area moves with it: not a wall of the board)."""
    cu = copper_layers(board)
    return [k.outline for k in board.keepouts or []
            if not k.footprint and k.tracks and k.outline is not None and not k.outline.is_empty and _covers_all_copper(k, cu)]


def regions(board):
    """Pieces of the outline minus the barriers, biggest first, those under MIN_REGION_SHARE of the
    board dropped (an edge keepout leaves slivers along the outline)."""
    polys = [p for p in board.outline or [] if p.area > 0]
    if not polys:
        return []
    out = shapely.union_all(polys)
    walls = barrier_polygons(board)
    if walls:
        out = out.difference(shapely.union_all(walls))
    pieces = [g for g in getattr(out, "geoms", [out]) if g.area > 0]
    total = sum(p.area for p in pieces)
    return sorted((g for g in pieces if g.area >= MIN_REGION_SHARE * total), key=lambda g: -g.area)


def _part_area(fp):
    a = sum(c.area for c in fp.courtyard or [])
    if a > 0:
        return a
    a = sum(c.area for c in fp.body or [])
    if a > 0:
        return a
    if not fp.pads:
        return 0.0
    xs, ys = [p.x for p in fp.pads], [p.y for p in fp.pads]
    return (max(xs) - min(xs) + 1.0) * (max(ys) - min(ys) + 1.0)


def _region_of_part(fp, regs):
    """The region holding most of the footprint's pads (its origin when it has none)."""
    pts = [Point(p.x, p.y) for p in fp.pads] or [Point(fp.x, fp.y)]
    votes = [sum(1 for pt in pts if r.covers(pt)) for r in regs]
    best = max(range(len(regs)), key=lambda k: votes[k])
    return best if votes[best] > 0 else -1


def _net_kinds(board):
    from .problem import net_class_guess
    n_parts = max(1, len(board.footprints))
    pins = defaultdict(int)
    for fp in board.footprints:
        for p in fp.pads:
            if p.net:
                pins[p.net] += 1
    return {n: net_class_guess(n, c, n_parts) for n, c in pins.items()}


def _adjacency(board, keep):
    """{part: {other part: weight}} over nets whose kind satisfies keep: 1/(pins - 1) per net."""
    kinds = _net_kinds(board)
    pins = defaultdict(set)
    for i, fp in enumerate(board.footprints):
        for p in fp.pads:
            if p.net and keep(kinds.get(p.net, "signal")):
                pins[p.net].add(i)
    adj = defaultdict(lambda: defaultdict(float))
    for members in pins.values():
        if len(members) < 2:
            continue
        w = 1.0 / (len(members) - 1)
        for a in members:
            for b in members:
                if a != b:
                    adj[a][b] += w
    return adj


def _propagate(label, adj):
    """Breadth-first: each pass, every unlabeled part next to labeled ones takes the region with
    the largest total weight (ties: lower index). In place."""
    while True:
        new = {}
        for i, nbrs in adj.items():
            if i in label:
                continue
            votes = defaultdict(float)
            for j, w in nbrs.items():
                if j in label:
                    votes[label[j]] += w
            if votes:
                new[i] = max(sorted(votes), key=lambda r: votes[r])
        if not new:
            return
        label.update(new)


def _components(idx, adj):
    seen, out = set(), []
    for i in idx:
        if i in seen:
            continue
        comp, todo = [], [i]
        seen.add(i)
        while todo:
            a = todo.pop()
            comp.append(a)
            for b in adj.get(a, ()):
                if b in idx and b not in seen:
                    seen.add(b)
                    todo.append(b)
        out.append(comp)
    return out


def assign(board, regs):
    """(region_of {uuid: region}, how {rule: parts}, over_capacity [regions])."""
    fps = board.footprints
    label = {}
    how = defaultdict(int)
    for i, fp in enumerate(fps):
        if fp.locked or fp.edge_cuts:
            r = _region_of_part(fp, regs)
            if r >= 0:
                label[i] = r
                how["anchored"] += 1
    n0 = len(label)
    _propagate(label, _adjacency(board, lambda k: k == "signal"))
    how["signal_nets"] = len(label) - n0
    n1 = len(label)
    _propagate(label, _adjacency(board, lambda k: k != "signal"))
    how["power_nets"] = len(label) - n1
    def sides(i):
        f = fps[i]
        if any(p.drill for p in f.pads):
            return ("F", "B")
        return (f.side,)
    used = defaultdict(float)          # (region, side) -> courtyard area
    for i, r in label.items():
        for sd in sides(i):
            used[(r, sd)] += _part_area(fps[i])

    def room(r, i):
        return min(CAPACITY * regs[r].area - used[(r, sd)] for sd in sides(i))
    left = [i for i in range(len(fps)) if i not in label and not fps[i].locked and not fps[i].edge_cuts]
    adj = _adjacency(board, lambda k: True)
    comps = _components(set(left), adj)
    comps.sort(key=lambda c: -sum(_part_area(fps[i]) for i in c))
    for comp in comps:
        r = max(range(len(regs)), key=lambda k: min(room(k, i) for i in comp))
        for i in comp:
            label[i] = r
            for sd in sides(i):
                used[(r, sd)] += _part_area(fps[i])
        how["by_area"] += len(comp)
    # an overfull region side gives up the movable parts least tied to it (net weight to it minus to the best
    # other region), to regions with room, until it fits or nothing can move
    for r in range(len(regs)):
        for sd in ("F", "B"):
            if used[(r, sd)] <= CAPACITY * regs[r].area:
                continue
            cand = []
            for i, ri in label.items():
                if ri != r or fps[i].locked or fps[i].edge_cuts or sd not in sides(i):
                    continue
                w = defaultdict(float)
                for j, x in adj.get(i, {}).items():
                    if j in label:
                        w[label[j]] += x
                cand.append((w[r] - max([w[k] for k in range(len(regs)) if k != r] or [0.0]), i))
            for _, i in sorted(cand):
                if used[(r, sd)] <= CAPACITY * regs[r].area:
                    break
                dest = [k for k in range(len(regs)) if k != r and room(k, i) >= _part_area(fps[i])]
                if not dest:
                    continue
                k = max(dest, key=lambda k: room(k, i))
                for s2 in sides(i):
                    used[(r, s2)] -= _part_area(fps[i])
                    used[(k, s2)] += _part_area(fps[i])
                label[i] = k
                how["moved_for_room"] += 1
    over = sorted({r for (r, sd), v in used.items() if v > CAPACITY * regs[r].area})
    return {fps[i].uuid: label.get(i, -1) for i in range(len(fps))}, dict(how), over


def true_split(board):
    """A Split when the outline less the barriers has several regions of a real size, else None.
    A split whose assignment overfills a region is returned with `over_capacity` set: the caller
    places the board whole (an outline that holds a fraction of the parts is a broken outline, not a
    panel: pdp7-memory-display's two 17 mm2 loops)."""
    regs = regions(board)
    if len(regs) < 2:
        return None
    region_of, how, over = assign(board, regs)
    nets = defaultdict(set)
    for fp in board.footprints:
        r = region_of.get(fp.uuid, -1)
        for p in fp.pads:
            if p.net and r >= 0:
                nets[p.net].add(r)
    kinds = _net_kinds(board)
    cross = sorted(n for n, rs in nets.items() if len(rs) > 1 and kinds.get(n) == "signal")
    return Split(regions=regs, region_of=region_of, cross_nets=cross, over_capacity=over, how=how)


def sub_board(board, split, r):
    """The board as region r sees it: its outline, its parts, and anchored parts no region holds
    (fixed obstacles wherever they are: a mouse-bite or a part straddling a wall)."""
    keep = [fp for fp in board.footprints if split.region_of.get(fp.uuid, -1) == r
            or (split.region_of.get(fp.uuid, -1) < 0 and (fp.locked or fp.edge_cuts))]
    return dataclasses.replace(board, outline=[split.regions[r]], footprints=keep)


def _movable(board):
    return sum(1 for fp in board.footprints if not fp.locked and not fp.edge_cuts and fp.pads)


def merge_reports(reps):
    """A placement report for the whole board from the regions' reports: what callers read."""
    main = max(reps, key=lambda r: len(r.get("exact") or ()) * 1000 + float(r.get("seconds") or 0.0))
    out = dict(main)
    out["legal_grid"] = all(r.get("legal_grid") for r in reps)
    out["exact"] = [e for r in reps for e in (r.get("exact") or [])]
    out["hpwl"] = round(sum(float(r.get("hpwl") or 0.0) for r in reps), 2)
    out["hpwl_signal"] = round(sum(float(r.get("hpwl_signal") or 0.0) for r in reps), 2)
    out["budget_s"] = round(sum(float(r.get("budget_s") or 0.0) for r in reps), 2)
    out["seconds"] = round(sum(float(r.get("seconds") or 0.0) for r in reps), 2)
    out["hazards"] = [h for r in reps for h in (r.get("hazards") or [])]
    inc = sorted({x for r in reps for x in (r.get("outline_incomplete") or [])})
    if inc:
        out["outline_incomplete"] = inc
    else:
        out.pop("outline_incomplete", None)
    sc = [r.get("scorecard") or {} for r in reps]
    out["scorecard"] = {k: round(sum(float(c.get(k) or 0.0) for c in sc), 4) for k in ("total", "total_linear", "structures", "over_budget")}
    return out


def place_split(place_fn, board, split, seed=0, time_s=300.0, log=None, verify=None, **kw):
    """Each region placed by itself in a time share proportional to its movable parts; poses merged.
    `verify` (the caller's check of the whole board) runs once on the merged result."""
    log = log or (lambda *a, **k: None)
    from .pipeline import Result
    t0 = time.monotonic()
    reserve = SPLIT_VERIFY_FRAC * float(time_s) if verify is not None else 0.0
    usable = max(float(time_s) - reserve, SPLIT_MIN_S * len(split.regions))
    subs = [sub_board(board, split, r) for r in range(len(split.regions))]
    weight = [max(_movable(b), 1) for b in subs]
    total = sum(weight)
    poses, reports = {}, []
    log(f"barrier split: {len(subs)} regions, movable {weight}, {len(split.cross_nets)} signal nets span regions")
    for r, b in enumerate(subs):
        if not _movable(b):
            continue
        res = place_fn(b, seed=seed, time_s=max(SPLIT_MIN_S, usable * weight[r] / total), brief=None, verify=None, log=log, **kw)
        reports.append(res.report)
        poses.update(res.poses)
    rep = merge_reports(reports) if reports else dict(legal_grid=True, exact=[], hpwl=0.0, seconds=0.0)
    rep["barrier_split"] = dict(regions=len(split.regions), areas=[round(p.area, 1) for p in split.regions],
                                parts=[sum(1 for v in split.region_of.values() if v == r) for r in range(len(split.regions))],
                                assignment=split.how, cross_nets=len(split.cross_nets), cross_net_names=split.cross_nets[:30],
                                over_capacity=split.over_capacity, seconds=round(time.monotonic() - t0, 2))
    if split.over_capacity:
        rep.setdefault("hazards", []).append(dict(code="barrier_region_over_capacity", regions=split.over_capacity))
    out = Result(poses=poses, report=rep)
    if verify is not None:
        out.verified = verify(out, t0 + float(time_s))
    return out


# -------------------------------------------------------------------------- soft term
def all_barriers(board):
    """Holes in the outline and all-copper track keepouts: what no copper can go through."""
    polys = [Polygon(r.coords) for p in board.outline or [] for r in p.interiors]
    return polys + barrier_polygons(board)


def _mst_edges(pts):
    """Prim's algorithm on the points' Euclidean distances: the edge list [(a, b)] as indices."""
    n = len(pts)
    if n < 2:
        return []
    done = [False] * n
    d = [float("inf")] * n
    src = [0] * n
    d[0] = 0.0
    edges = []
    for _ in range(n):
        u = min((k for k in range(n) if not done[k]), key=lambda k: d[k])
        done[u] = True
        if u != 0:
            edges.append((src[u], u))
        for v in range(n):
            if not done[v]:
                dv = (pts[u][0] - pts[v][0]) ** 2 + (pts[u][1] - pts[v][1]) ** 2
                if dv < d[v]:
                    d[v], src[v] = dv, u
    return edges


def crossing_nets(P, st, barrier):
    """[net index] of signal nets with an MST edge whose straight line crosses `barrier`, and how
    many edges do (Problem P at state st; barrier: shapely geometry)."""
    nets, n_edges = [], 0
    for net in P.nets:
        if net.kind in ("ground", "power") or len(net.pins) < 2 or len(net.pins) > MST_MAX_PINS:
            continue
        pts = []
        for (i, k) in net.pins:
            xy = st.pins_xy(i)[k]
            pts.append((float(xy[0]), float(xy[1])))
        hit = 0
        for a, b in _mst_edges(pts):
            if pts[a] == pts[b]:
                continue
            if barrier.intersects(LineString([pts[a], pts[b]])):
                hit += 1
        if hit:
            nets.append(net.i)
            n_edges += hit
    return nets, n_edges


def barrier_union(board):
    bars = all_barriers(board)
    if not bars:
        return None
    u = shapely.union_all(bars)
    shapely.prepare(u)
    return u


def reweight_crossing(P, st, weight):
    """Multiply the weight of the signal nets crossing a barrier at state st. Report."""
    u = barrier_union(P.board)
    if u is None or weight <= 1.0:
        return dict(barriers=0)
    nets, edges = crossing_nets(P, st, u)
    for j in nets:
        P.nets[j].weight *= weight
    return dict(barriers=len(all_barriers(P.board)), nets=len(nets), edges=edges, weight=weight)


def crossings(P, st):
    """Report: signal nets and MST edges crossing a barrier at state st."""
    u = barrier_union(P.board)
    if u is None:
        return None
    nets, edges = crossing_nets(P, st, u)
    return dict(nets=len(nets), edges=edges)
