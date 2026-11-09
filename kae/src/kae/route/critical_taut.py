# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Critical copper tightened before it is locked (docs/topics/routing/routing-stages.md, P4,
stage 2): taut on the module and rail copper of a critical Session, guarded by its physics.

    from kae.route import critical_taut
    rep = critical_taut.tighten(session, fills=fills)    # after Session.route(), before write()

What moves: the session's committed tracks (modules, rails, joins), never the input's routing,
thermal spokes or stitching. Each branch between fixed points (pads, vias, T-joins, width
changes) becomes taut's homotopic shortest path, tangents and true arcs, with pad-entry rule D
tails (kae.route.taut.Taut, unchanged, run on a copy of the session's Space in which the critical
copper is the board's routing). Obstacles: pads, keepouts, thermal corridors, the edge, other
nets' critical copper, every requirement of the board's rules (Space), and other nets' fills
when `fills` is given (critical_recheck.fills_of of the board with the critical copper; pours
"hold"), else none ("refill": KiCad refills around the copper, as the grid router assumes).

Guard: shorter is not always a lower loop inductance, so a move is judged by the physics the
module stage quotes, not by length. Branches that share an input track form one group.
- A module (cell, path, decap, crystal, chain) keeps the groups that touch it only if its routed
  value (critical_modules.quote, on its hops rebuilt from the tightened copper) is at most
  (1 + tighten_tol) times the value before. A group touching several modules needs all of them.
- A rail keeps a group only if the group's resistance on that rail (the drop at its current,
  critical_rails' budget) is not above (1 + tighten_tol) times the old one.
- A group whose hops cannot be mapped onto the new copper is refused (never judged blind).
- Groups kept beside a refused one are checked exactly against its restored copper; a conflict
  drops the kept group too, and the guard runs again.

arc_policy "keep45" skips the step: taut has no segment-only mode (every path it builds is
tangents and arcs), so the critical copper keeps its grid shape and the report says so.
"""
from __future__ import annotations

import copy
import dataclasses
import heapq
import math
import time
from types import SimpleNamespace

from shapely.geometry import LineString, MultiLineString, Point

from kae.board.model import Track

from . import arcs as A
from . import critical_write as W
from .critical_space import Item

DEFAULTS = dict(
    tighten=False,           # run this step in the critical stage (critical.run, route_critical, optimize_modules)
    arc_policy="arcs",       # "arcs" or "keep45" (no tightening: taut makes arcs only)
    tighten_tol=0.005,       # a module's quote / a rail's resistance may rise at most this fraction
    tighten_passes=4,        # taut passes at most (it stops earlier when no net shortens by > 1 um)
    tighten_pours="hold",    # with fills given: "hold" (other nets' fills are obstacles) or "refill"
)
QUOTED = ("cell", "path", "decap", "crystal", "chain")
FIXED_OWNERS = ("spokes", "stitch")
TOL = 1e-4


def _taut_cls():
    from .taut import Taut

    class _CritTaut(Taut):
        """Taut on the critical copper only (`cand` uuids), recording which input tracks each
        rewrite replaced."""

        def chains(self, only=None):
            out = super().chains(only)
            return [c for c in out if all(r["parent"] in self.cand for r in c[3])]

        def apply(self, net, layer, w, recs, pieces, widths=None):
            par = set()
            for r in recs:
                par |= self.origin.get(r["uuid"], {r["parent"]})
            before = set(self.recs)
            super().apply(net, layer, w, recs, pieces, widths)
            for u in set(self.recs) - before:
                self.origin[u] = par
            self.events.append(par)
    return _CritTaut


def _owner_id(it):
    o = it.owner
    return str(o[0]) if isinstance(o, tuple) and o else ""


def _rec_coords(r):
    from .taut import _T
    return A.track_coords(_T(r))


def _item_coords(it):
    return list(it.geom.coords)


def _arc_dirs(coords, mid):
    """Unit directions at the start (leaving) and end (arriving) of a piece."""
    if mid is not None:
        got = A.sme_to_csa(coords[0], mid, coords[-1])
        if got is not None:
            c, r, a0, sw = got
            s = 1.0 if sw > 0 else -1.0
            a1 = a0 + sw
            return ((-math.sin(a0) * s, math.cos(a0) * s), (-math.sin(a1) * s, math.cos(a1) * s))
    a, b = coords[0], coords[1]
    c, d = coords[-2], coords[-1]
    la, lb = math.dist(a, b) or 1.0, math.dist(c, d) or 1.0
    return (((b[0] - a[0]) / la, (b[1] - a[1]) / la), ((d[0] - c[0]) / lb, (d[1] - c[1]) / lb))


def copper_stats(s):
    """Length (mm) and corners of the session's critical tracks: a corner is a joint of exactly
    two tracks of one net and layer that turns by more than 5 degrees (tangent arc joints are
    not corners), plus the turns inside a polyline."""
    mids = getattr(s, "arcs", {}) or {}
    ends = {}
    length = 0.0
    n = 0
    for it in s.space.routed:
        if it.kind != "track":
            continue
        cs = _item_coords(it)
        mid = mids.get(it.uuid)
        length += it.geom.length
        n += 1
        d0, d1 = _arc_dirs(cs, mid)
        layer = next(iter(it.layers))
        for p, d in ((cs[0], (-d0[0], -d0[1])), (cs[-1], d1)):
            ends.setdefault((it.net, layer, round(p[0], 4), round(p[1], 4)), []).append(d)
    corners = 0
    for ds in ends.values():
        if len(ds) != 2:
            continue
        (ax, ay), (bx, by) = ds
        # both point out of their track: a straight joint has them opposite
        if -(ax * bx + ay * by) < math.cos(math.radians(5.0)):
            corners += 1
    return dict(tracks=n, length_mm=round(length, 3), corners=corners)


class _Group:
    __slots__ = ("k", "parents", "old", "new", "owners", "nets", "lines", "graph")


def tighten(s, fills=None, opts=None, log=None):
    """Tighten the critical Session `s`'s committed copper under the physics guard (see the
    module docstring). Changes the session in place (space, module copper and hops, physics,
    s.arcs). Returns the report: counters, physics before and after per module, rails'
    resistance, critical copper length and corners before and after, seconds."""
    t0 = time.monotonic()
    o = {**DEFAULTS, **{k: v for k, v in (s.opts or {}).items() if k in DEFAULTS}, **(opts or {})}
    log = log or getattr(s, "log", None) or (lambda *a: None)
    tol = float(o["tighten_tol"])
    rep = dict(arc_policy=o["arc_policy"], tol=tol)
    if not hasattr(s, "arcs"):
        s.arcs = {}
    s._tighten_refuse, s._tighten_new = None, set()
    if o["arc_policy"] == "keep45":
        rep["skipped"] = ("arc_policy keep45: taut has no segment-only mode (its paths are tangents and arcs), "
                          "so the critical copper keeps its grid shape")
        rep["seconds"] = round(time.monotonic() - t0, 3)
        return rep
    if o["arc_policy"] != "arcs":
        raise ValueError(f"arc_policy {o['arc_policy']!r}: 'arcs' or 'keep45'")
    sp = s.space
    s.copper()                                       # every committed item gets its uuid
    rep["before"] = copper_stats(s)
    cand = {it.uuid for it in sp.routed if it.kind == "track" and _owner_id(it) not in FIXED_OWNERS}
    if not cand:
        rep.update(groups=0, seconds=round(time.monotonic() - t0, 3), after=rep["before"])
        return rep
    by_uuid = {it.uuid: it for it in sp.routed}
    mods = {m.id: m for m in list(s.modules) + list(getattr(s.ctx, "rail_modules", []) or [])}

    # ---- taut on a copy of the space: the critical copper is the board's routing
    tracks = [Track(uuid=t.uuid, net=t.net, layer=t.layer, width=t.width, start=t.start, end=t.end, mid=t.mid,
                    locked=True) for t in s.board.tracks]
    for it in sp.routed:
        if it.kind == "track":
            cs = _item_coords(it)
            tracks.append(Track(uuid=it.uuid, net=it.net, layer=next(iter(it.layers)), width=it.width,
                                start=tuple(cs[0]), end=tuple(cs[-1]), mid=s.arcs.get(it.uuid),
                                locked=it.uuid not in cand))
    board = SimpleNamespace(tracks=tracks, vias=[], nets=s.board.nets, zones=s.board.zones,
                            footprints=s.board.footprints, path=s.path)
    tsp = copy.copy(sp)
    tsp.items = {l: list(v) for l, v in sp.items.items()}
    tsp.existing = list(sp.existing) + list(sp.routed)
    tsp.routed = []
    tsp._arr = {}
    pours = o["tighten_pours"] if fills is not None else "refill"
    topts = dict(pours=pours, pairs="fixed", passes=int(o["tighten_passes"]))
    T = _taut_cls()
    t1 = time.monotonic()
    tt = T(s.path, topts, log=lambda m: log(f"tighten: {m}"), board=board, info=s.info, space=tsp,
           brief=s.brief, fills=fills)
    tt.cand, tt.origin, tt.events = cand, {}, []
    tt.run_passes()
    rep["taut"] = dict(tried=tt.stats.get("tried", 0), improved=tt.stats.get("improved", 0),
                       skipped=dict(tt.stats.get("skipped", {})), passes=len(tt.stats.get("passes", [])),
                       seconds=round(time.monotonic() - t1, 2), pours=topts["pours"])

    # ---- groups: branches sharing an input track move together
    up = {}

    def find(x):
        while up.setdefault(x, x) != x:
            up[x] = up[up[x]]
            x = up[x]
        return x
    for par in tt.events:
        par = sorted(par)
        for p in par[1:]:
            ra, rb = find(par[0]), find(p)
            if ra != rb:
                up[rb] = ra
    members = {}
    for par in tt.events:
        for p in par:
            members.setdefault(find(p), set()).add(p)
    groups = []
    for k, (root, ps) in enumerate(sorted(members.items())):
        g = _Group()
        g.k, g.parents = k, ps
        g.old = [by_uuid[p] for p in ps if p in by_uuid]
        recs = [r for r in tt.recs.values()
                if (r["orig"] and r["parent"] in ps) or (not r["orig"] and tt.origin.get(r["uuid"], set()) <= ps
                                                        and tt.origin.get(r["uuid"]))]
        g.new = []
        for r in recs:
            cs = _rec_coords(r)
            line = LineString(cs)
            near = min(g.old, key=lambda it: it.geom.distance(line.interpolate(0.5, normalized=True))) if g.old else None
            it = Item("track", r["net"], [r["layer"]], line, r["w"] / 2.0, sp.rc(r["net"]),
                            owner=near.owner if near is not None else ("tighten", ""))
            it.width, it.uuid = r["w"], W.new_uuid()
            if r["mid"] is not None:
                s.arcs[it.uuid] = tuple(r["mid"])
            g.new.append(it)
        g.owners = {_owner_id(it) for it in g.old}
        g.nets = {it.net for it in g.old}
        # per (net, layer): the old copper as lines (to match hop segments) and the new as a graph
        g.lines = {}
        for it in g.old:
            g.lines.setdefault((it.net, next(iter(it.layers))), []).append(it.geom)
        g.lines = {key: MultiLineString(v) for key, v in g.lines.items()}
        g.graph = {}
        for it in g.new:
            cs = _item_coords(it)
            gr = g.graph.setdefault((it.net, next(iter(it.layers))), {})
            ka, kb = _nk(cs[0]), _nk(cs[-1])
            gr.setdefault(ka, []).append((kb, it.geom.length, cs))
            gr.setdefault(kb, []).append((ka, it.geom.length, cs[::-1]))
        groups.append(g)
    rep["groups"] = len(groups)
    rep["branches_tightened"] = sum(1 for _ in tt.events)
    if not groups:
        rep.update(after=rep["before"], seconds=round(time.monotonic() - t0, 3))
        return rep

    # ---- the guard
    ctx = s.ctx
    from .critical_modules import quote
    from .critical_physics import r_track
    h0 = {mid: dict(m.hops) for mid, m in mods.items()}
    touch = {}                                       # module id -> groups
    for g in groups:
        for ow in g.owners:
            touch.setdefault(ow, []).append(g)
    quoted = [mid for mid in touch if mid in mods and mods[mid].kind in QUOTED and mods[mid].status in ("routed", "partial")]
    before = {}
    for mid in quoted:
        m = mods[mid]
        before[mid] = quote(ctx, m, store=False)
    applied = set()

    def swap(g, on):
        rm, add = (g.old, g.new) if on else (g.new, g.old)
        sp.remove(rm)
        for it in add:
            for l in it.layers:
                sp.items[l].append(it)
            sp.routed.append(it)
        sp.invalidate()
        ids = {id(x) for x in rm}
        for ow in g.owners:
            m = mods.get(ow)
            if m is None:
                continue
            m.copper = [c for c in m.copper if id(c) not in ids] + [c for c in add if _owner_id(c) == ow]
        (applied.add if on else applied.discard)(g.k)

    def hops_for(mid, acc):
        """The module's hops with every segment run on a kept group's old copper replaced by the
        new copper between the same two points; None when a run cannot be mapped."""
        out = {}
        gs = [g for g in touch.get(mid, []) if g.k in acc]
        for key, rt in h0[mid].items():
            if rt is None or not rt.segs or not gs:
                out[key] = rt
                continue
            segs = _split_segs(rt, gs)
            new, run = [], None

            def flush():
                if run is None:
                    return True
                g, l, p, q = run
                path = _path(g.graph.get((rt.net, l)) or {}, p, q)
                if path is None:
                    return False
                new.extend((l, a, b) for a, b in zip(path[:-1], path[1:]) if math.dist(a, b) > 1e-9)
                return True
            for l, a, b in segs:
                g = next((g for g in gs if _on_lines(g.lines.get((rt.net, l)), a, b)), None)
                if g is None:
                    if not flush():
                        return None
                    run = None
                    new.append((l, a, b))
                    continue
                if run is not None and run[0] is g and run[1] == l and math.dist(run[3], a) < TOL:
                    run = (g, l, run[2], b)
                    continue
                if not flush():
                    return None
                run = (g, l, a, b)
            if not flush():
                return None
            out[key] = dataclasses.replace(rt, segs=new, length=sum(math.dist(a, b) for _, a, b in new))
        return out

    def rail_ok(g):
        for ow in g.owners:
            if not ow.startswith("rail:"):
                continue
            r0 = sum(r_track(it.geom.length, it.width, sp.tcu.get(next(iter(it.layers)), 0.035))
                     for it in g.old if _owner_id(it) == ow)
            r1 = sum(r_track(it.geom.length, it.width, sp.tcu.get(next(iter(it.layers)), 0.035))
                     for it in g.new if _owner_id(it) == ow)
            if r1 > r0 * (1 + tol) + 1e-12:
                return False
        return True

    refused = {}                                     # group -> why
    for g in groups:
        if not rail_ok(g):
            refused[g.k] = "rail drop"
    after = {}
    def set_state(acc):
        for g in groups:
            if (g.k in acc) != (g.k in applied):
                swap(g, g.k in acc)

    def value(mid, acc):
        """(quote of module mid with the groups `acc` applied, mapped)."""
        set_state(acc)
        m = mods[mid]
        hp = hops_for(mid, acc)
        if hp is None:
            return None, False
        keep_h = m.hops
        m.hops = hp
        try:
            return quote(ctx, m, store=False), True
        finally:
            m.hops = keep_h

    def worse(v, v0):
        return v0 is not None and (v is None or v > v0 * (1 + tol))

    p0 = {mid: dict(mods[mid].physics) for mid in quoted}
    mids = {it.uuid: s.arcs[it.uuid] for g in groups for it in g.new if it.uuid in s.arcs}

    def settle():
        for _round in range(8):
            acc = {g.k for g in groups} - set(refused)
            set_state(acc)
            changed = False
            for mid in quoted:
                v, mapped = value(mid, acc)
                hit = [g for g in touch[mid] if g.k in acc]
                if not mapped:
                    for g in hit:
                        refused[g.k] = f"unmapped hop of {mid}"
                    changed = True
                    continue
                after[mid] = v
                v0 = before.get(mid)
                if worse(v, v0) and hit:
                    # which of its groups: each alone (the module's other groups as they were);
                    # when none is worse alone, the combination is, and all go
                    bad = [g for g in hit if len(hit) > 1 and worse(value(mid, acc - {h.k for h in hit if h is not g})[0], v0)]
                    for g in bad or hit:
                        refused[g.k] = f"physics of {mid}"
                    changed = True
            if changed:
                continue
            set_state(acc)
            # kept copper against the restored copper of refused groups, exactly
            restored = {id(it) for g in groups if g.k in refused for it in g.old}
            bad = set()
            if restored:
                for g in groups:
                    if g.k not in acc:
                        continue
                    for it in g.new:
                        v = A.polyline_violations(sp, it.net, next(iter(it.layers)), it.width, _item_coords(it))
                        if any(x != "edge" and id(x) in restored for x, _, _ in v):
                            bad.add(g.k)
                            break
            if not bad:
                break
            for k in bad:
                refused[k] = "conflict with restored copper"
        acc = {g.k for g in groups} - set(refused)
        for g in groups:
            if (g.k in acc) != (g.k in applied):
                swap(g, g.k in acc)
        for g in groups:
            for it in g.new:
                if g.k in acc and it.uuid in mids:
                    s.arcs[it.uuid] = mids[it.uuid]
                else:
                    s.arcs.pop(it.uuid, None)

        # ---- the modules keep their rebuilt hops; their stage values are the tightened copper's
        per = []
        for mid in sorted(set(touch) & set(mods)):
            m = mods[mid]
            kept = [g for g in touch[mid] if g.k in acc]
            row = dict(id=mid, kind=m.kind, groups=len(touch[mid]), kept=len(kept))
            if mid in quoted:
                hp = hops_for(mid, acc) if kept else h0[mid]
                if hp is not None:
                    m.hops = hp
                row["before"] = before.get(mid)
                row["u_before"] = p0[mid].get("u")
                if not kept:
                    m.physics = dict(p0[mid])
                v = quote(ctx, m, store=True) if kept else before.get(mid)
                row["after"] = v
                row["u_after"] = m.physics.get("u") if kept else row.get("u_before")
                row["unit"] = m.physics.get("unit")
            elif mid.startswith("rail:"):
                r0 = r1 = 0.0
                for g in touch[mid]:
                    for it in g.old:
                        if _owner_id(it) == mid:
                            r0 += r_track(it.geom.length, it.width, sp.tcu.get(next(iter(it.layers)), 0.035))
                    cur = g.new if g.k in acc else g.old
                    for it in cur:
                        if _owner_id(it) == mid:
                            r1 += r_track(it.geom.length, it.width, sp.tcu.get(next(iter(it.layers)), 0.035))
                row.update(r_before_mohm=round(1e3 * r0, 4), r_after_mohm=round(1e3 * r1, 4))
            per.append(row)
        why = {}
        for k, w in refused.items():
            w0 = w.split(" of ")[0]
            why[w0] = why.get(w0, 0) + 1
        kept_nets = {n for g in groups if g.k in acc for n in g.nets}
        rep.update(kept=len(acc), refused=len(refused), refused_why=why, modules=per,
                   hazards=[h for h in tt.hazards if set(h.get("objects") or []) & kept_nets],
                   after=copper_stats(s), seconds=round(time.monotonic() - t0, 3))
        log(f"tighten: {len(groups)} groups ({rep['branches_tightened']} branch rewrites), {len(acc)} kept, "
            f"{len(refused)} refused {why or ''}; {rep['before']['length_mm']} -> {rep['after']['length_mm']} mm, "
            f"corners {rep['before']['corners']} -> {rep['after']['corners']}; {rep['seconds']:.1f}s")


    def refuse(uuids, why="drc"):
        """Refuse (restore) the groups whose new copper has a uuid in `uuids`, then settle the
        guard again; the stage's KiCad gate (critical.run) calls this. Returns the report."""
        uuids = set(uuids)
        hit = [g for g in groups if g.k not in refused and any(it.uuid in uuids for it in g.new)]
        for g in hit:
            refused[g.k] = why
        if hit:
            settle()
        rep["gate_reverted"] = rep.get("gate_reverted", 0) + len(hit)
        return rep

    settle()
    s._tighten_refuse = refuse
    s._tighten_new = {it.uuid for g in groups for it in g.new}
    return rep


# ----------------------------------------------------------------------------- hop mapping
def _nk(p):
    return (round(p[0], 4), round(p[1], 4))


def _on_lines(ml, a, b):
    if ml is None:
        return False
    m = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
    return all(ml.distance(Point(p)) < TOL for p in (a, b, m))


def _split_segs(rt, gs):
    """rt.segs cut at every old item end of the groups `gs` that lies inside a segment."""
    cuts = {}
    for g in gs:
        for it in g.old:
            if it.net != rt.net:
                continue
            l = next(iter(it.layers))
            cs = _item_coords(it)
            cuts.setdefault(l, []).extend([cs[0], cs[-1]])
    out = []
    for l, a, b in rt.segs:
        L = math.dist(a, b)
        ts = []
        if L > 1e-9:
            for p in cuts.get(l, ()):
                t = ((p[0] - a[0]) * (b[0] - a[0]) + (p[1] - a[1]) * (b[1] - a[1])) / (L * L)
                if TOL / L < t < 1 - TOL / L:
                    f = (a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]))
                    if math.dist(f, p) < TOL:
                        ts.append(t)
        pts = [a] + [(a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])) for t in sorted(set(ts))] + [b]
        out.extend((l, p, q) for p, q in zip(pts[:-1], pts[1:]))
    return out


def _path(gr, p, q):
    """The shortest path (point list) in a group's new copper graph from the node nearest p to
    the node nearest q; None when there is none."""
    if not gr:
        return None
    src = min(gr, key=lambda k: math.dist(k, p))
    dst = min(gr, key=lambda k: math.dist(k, q))
    if src == dst:
        return None
    dist, prev = {src: 0.0}, {}
    hq = [(0.0, src)]
    while hq:
        d, u = heapq.heappop(hq)
        if u == dst:
            break
        if d > dist.get(u, math.inf):
            continue
        for v, L, cs in gr[u]:
            nd = d + L
            if nd < dist.get(v, math.inf):
                dist[v] = nd
                prev[v] = (u, cs)
                heapq.heappush(hq, (nd, v))
    if dst not in prev:
        return None
    pieces = []
    v = dst
    while v != src:
        v, cs = prev[v]
        pieces.append(cs)
    pts = [tuple(pieces[-1][0])]
    for cs in reversed(pieces):
        pts.extend(tuple(x) for x in cs[1:])
    return pts
