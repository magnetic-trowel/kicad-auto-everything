# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Taut routing: every routed branch pulled to the shortest path of its own topology, made of
straight tangents and true arcs around its clearance-grown obstacles. A DRC-gated post-pass.

    from kae.route import taut
    rep = taut.run("routed.kicad_pcb", "out.kicad_pcb")              # taut, then KiCad DRC gate
    rep = taut.run(..., opts=dict(power_copper=True))                 # then the arc-aware power copper

    python -m kae.route.taut run IN OUT [--report R.json] [--power-copper] [--pours hold|refill]
    python -m kae.route.taut stats BOARD

Order (docs/research/routing/kae-taut-arcs.md): route -> pad entry -> taut -> power copper ->
DRC gate. Pad entries are built here (the tail of every pad end runs along the edge normal one
track width out, kae.route.pad_entry's targets), so the input may be the router's output.

What moves: the interior of a branch, the chain of tracks between two fixed points (pads, vias,
T-joins and branch points, width changes, layer ends). Fixed: vias, locked tracks, nets of a diff
pair, nets with a length or skew rule or a tuning pattern, branches that run over a pad or via of
their own net (moving them could cut the joint). Each branch keeps its topology (the same side
of every obstacle) and becomes its homotopic shortest path (kae.route.taut_geom).

Obstacles: every other net's pads, tracks (arcs sampled), vias, holes, keepouts, thermal
corridors, the board edge (Space: the bridge's KiCad rules, custom rules included), grown by the
requirement plus half the width; for sensitive pairs (power_copper.classify's victims against
any non-ground net, switch nodes against victims) the requirement is raised to min(victim gap,
the distance the input kept), on the branch's layer and, for tracks, the adjacent layers. Other
nets' zone fills (KiCad's refill of the input) are obstacles in `pours="hold"` (a branch inside a
pour stays in its knockout, "rails may not cut ground pours"), and ignored in "refill".

Passes: branches by potential gain (length minus chord), all nets, repeated until no net shortens
by more than `conv_eps` (the decrease per pass is reported). Every new piece is checked exactly
(arcs.polyline_violations); the board is then KiCad-DRC gated: no error type and no unconnected
count above the input's; violations naming a changed net revert that net (and, exactly, any net
whose new copper is then too close to the restored copper), then by distance, then batch by batch.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import shutil
import tempfile
import time
from pathlib import Path

import numpy as np
import shapely
from shapely.geometry import LineString, Point
from shapely.ops import unary_union

from . import arcs as A
from . import critical_write as W
from . import pad_entry as PE
from . import taut_geom as G

DEFAULTS = dict(
    pours="hold",            # other nets' fills: "hold" (obstacles; a branch in a pour keeps its knockout) or "refill"
    passes=8,                # at most
    conv_eps=1e-3,           # mm: stop when no net shortened by more than this in a pass
    min_gain=1e-3,           # mm: a branch is rewritten only if this much shorter
    margin_win=1.0,          # mm around the branch's hull (doubled when the result touches it)
    victims=True,            # keep victim gaps (power_copper.victim_gap)
    pad_tails=True,          # pad ends get a tail along the edge normal (pad_entry targets)
    max_angle=10.0,          # degrees: an entry within this of the edge normal is perpendicular
    rails="centre",          # rails, grounds and wide tracks keep their centre ends (tail out through the edge middle)
    pairs="coupled",         # diff pairs: "coupled" (a coupled section is tightened as one centreline at
                             # constant spacing, its ends' headings kept; skew never worse) or "fixed"
    respect_locked=True,
    operating=None,          # operating facts JSON (pad currents: necks and land hazards); default: the project's
                             # KAE_OPERATING text variable (power_copper._operating)
    drc_budget=40,
    eps_topo=3e-3,
)

LEN_ABS, LEN_REL = 1.0, 0.2              # a tail taking copper off a land may grow this much (pad_reroute's limit)
MARGIN = 2e-3 + 2 * A.SAG + 1e-4          # mm the exact path keeps above every requirement (TOL + sampling)
CHECK_TOL = 2e-3                          # mm above every requirement in the exact check (critical_space.TOL)


def _key(p):
    return (round(p[0], 5), round(p[1], 5))


def _ang(a, b):
    return math.atan2(b[1] - a[1], b[0] - a[0])


# ----------------------------------------------------------------------------- the pass
class Taut:
    def __init__(self, board_path, opts=None, log=print, *, board=None, info=None, space=None, brief=None,
                 fills=None):
        """board_path: the board (its text: tuning patterns; its project: operating facts). The
        keywords let a caller that already holds them skip the loading (kae.route.critical_taut:
        the critical stage's Space with its copper as existing tracks): `board` (its tracks are
        the routing), `info` (pcbnew_io.export_dsn), `space` (a critical_space.Space of that board
        and info), `brief`, and `fills` (critical_recheck.fills_of, for pours "hold")."""
        from kae.board import pcbnew_io
        from kae.board.kicad_file import load
        from .bridge import severities
        from .critical_space import Space, Item
        from . import power_copper as PC
        t0 = time.monotonic()
        self.Item = Item
        self.o = {**DEFAULTS, **(opts or {})}
        self.log = log
        self.path = Path(board_path).resolve()
        self.board = board if board is not None else load(self.path)
        if info is None and space is None:
            with tempfile.TemporaryDirectory(prefix="kae-taut-") as d:
                info = pcbnew_io.export_dsn(self.path, Path(d) / "board.dsn")
        self.info = info if info is not None else space.info
        self.sp = space if space is not None else Space(self.board, self.info, sev=severities(self.path))
        A.fix_space_arcs(self.sp, self.board.tracks)
        from kae.circuit.brief import build
        self.brief = brief if brief is not None else build(self.board)
        self.power, self.ground, self.switch, self.victims = PC.classify(self.brief, self.board.nets)
        sp = self.sp
        cu = sp.cu
        self.h = {l: (min(abs(sp.z[l] - sp.z[m]) for m in cu if m != l) if len(cu) > 1 else sp.thickness) for l in cu}
        self.adj = {l: [cu[i] for i in (k - 1, k + 1) if 0 <= i < len(cu)] for k, l in enumerate(cu)}
        self.PC = PC
        self.fills = {}
        if self.o["pours"] == "hold":
            if fills is not None:
                self.fills = fills
            else:
                from .critical_recheck import fills_of
                self.fills = fills_of(self.path)
        self.zone_clr = {}
        for z in self.board.zones:
            for l in z.layers or []:
                k = (z.net, l)
                self.zone_clr[k] = max(self.zone_clr.get(k, 0.0), z.clearance or 0.0)
        # routing state: uuid -> record
        self.recs = {}
        for t in self.board.tracks:
            if t.layer not in sp.items:
                continue
            self.recs[t.uuid] = dict(uuid=t.uuid, net=t.net or "", layer=t.layer, w=t.width, a=tuple(t.start),
                                     b=tuple(t.end), mid=tuple(t.mid) if t.mid is not None else None,
                                     locked=t.locked, parent=t.uuid, orig=True)
        self.item_of = {it.uuid: it for it in sp.existing if it.kind == "track"}
        self.n_split = self._split_tees()
        self.orig = {u: dict(r) for u, r in self.recs.items()}
        self.parts_of = {}
        for r in self.recs.values():
            self.parts_of[r["parent"]] = self.parts_of.get(r["parent"], 0) + 1
        self.vias = [it for it in sp.existing if it.kind == "via"]
        self.fixed_nets, self.why_fixed = self._fixed_nets()
        self.stats = dict(branches=0, tried=0, improved=0, skipped={}, passes=[])
        self.hazards, self._flagged, self._currents = [], set(), None
        self.necks, self.over_fixed = {}, {}           # per net: necks made, overhanging entries removed
        self.changed_nets = set()
        self.t_setup = time.monotonic() - t0
        log(f"[taut] {len(self.recs)} tracks, {len(self.fixed_nets)} nets fixed "
            f"({', '.join(f'{k} {v}' for k, v in self._count_why().items())}); setup {self.t_setup:.1f}s")

    def _split_tees(self):
        """Cut every straight track at the T-joins on its interior (an end of another track of its
        net and layer), so each piece belongs to one branch. A split track is written back as one
        block while none of its pieces changes."""
        by = {}
        for r in self.recs.values():
            by.setdefault((r["net"], r["layer"]), []).append(r)
        n = 0
        for (net, layer), rs in by.items():
            if not net or len(rs) < 3:
                continue
            ends = np.array([p for r in rs for p in (r["a"], r["b"])], float)
            for r in rs:
                if r["mid"] is not None:
                    continue
                a, b = np.array(r["a"]), np.array(r["b"])
                d = b - a
                L2 = float(d @ d)
                if L2 < 1e-12:
                    continue
                t = ((ends - a) @ d) / L2
                foot = a + np.outer(t, d)
                dist = np.hypot(*(ends - foot).T)
                L = math.sqrt(L2)
                k = np.nonzero((dist < 1e-5) & (t * L > 1e-4) & ((1 - t) * L > 1e-4))[0]
                if not len(k):
                    continue
                ts = sorted({round(float(t[i]), 9) for i in k})
                # each cut is the joining end itself (KiCad connects equal points)
                cuts = [tuple(r["a"])] + [tuple(ends[next(i for i in k if round(float(t[i]), 9) == tt_)]) for tt_ in ts] \
                    + [tuple(r["b"])]
                self.recs.pop(r["uuid"])
                it = self.item_of.pop(r["uuid"], None)
                if it is not None:
                    self._remove([it])
                for m, (p, q) in enumerate(zip(cuts[:-1], cuts[1:])):
                    u = f"{r['uuid']}#{m}"
                    nr = dict(r, uuid=u, a=p, b=q, parent=r["uuid"], orig=True)
                    self.recs[u] = nr
                    nit = self.Item("track", net, [layer], LineString([p, q]), r["w"] / 2, self.sp.rc(net), owner="existing")
                    nit.uuid, nit.width, nit.locked = u, r["w"], r["locked"]
                    self.sp.items[layer].append(nit)
                    self.item_of[u] = nit
                self.sp.invalidate(layer)
                n += 1
        return n

    # ---------------------------------------------------------------- what is fixed
    def _count_why(self):
        out = {}
        for v in self.why_fixed.values():
            out[v] = out.get(v, 0) + 1
        return out

    def _fixed_nets(self):
        from . import rules as R
        from . import constraints as CN
        why = {}
        nets = set(self.board.nets) if not isinstance(self.board.nets, dict) else set(self.board.nets)
        nets = {n for n in nets if n}
        self.pair_of = {}
        for n in nets:
            if R.diff_base(n) is not None and R.complement_net(n) in nets:
                why[n] = "diff pair"
                self.pair_of[n] = R.complement_net(n)
        for dp in self.brief.get("diff_pairs") or []:
            if dp.get("p") in nets and dp.get("n") in nets:
                why[dp["p"]] = why[dp["n"]] = "diff pair"
                self.pair_of[dp["p"]], self.pair_of[dp["n"]] = dp["n"], dp["p"]
        rb = self.sp.rb
        layer = self.sp.cu[0]
        for n in nets:
            if n in why:
                continue
            try:
                it = CN.net_item(self.info, n, "track", layer, width=0.2)
                for ct in ("length", "skew"):
                    c = R.strictest(rb, ct, it, None, layer)
                    if c is not None and (getattr(c, "min", None) is not None or getattr(c, "max", None) is not None
                                          or getattr(c, "opt", None) is not None):
                        why[n] = f"{ct} rule"
                        break
            except Exception:       # noqa: BLE001 - a net the rule port cannot represent: leave it alone
                pass
        text = self.path.read_text(encoding="utf-8")
        if "tuning_pattern" in text:
            for m in re.finditer(r"\(generated[\s\S]*?\(type\s+tuning_pattern\)[\s\S]*?\(members([^)]*)\)", text):
                for u in re.findall(r'"([^"]+)"', m.group(1)):
                    t = next((t for t in self.board.tracks if t.uuid == u), None)
                    if t is not None and t.net:
                        why[t.net] = "tuning pattern"
        return set(why), why

    # ---------------------------------------------------------------- chains
    def chains(self, only=None):
        """[(net, layer, w, [rec], [(x, y) path], (end kinds))] of movable branches (of the nets
        `only`, fixed or not, when given)."""
        sp = self.sp
        by = {}
        for r in self.recs.values():
            by.setdefault((r["net"], r["layer"]), []).append(r)
        out = []
        for (net, layer), rs in by.items():
            if not net or (net in self.fixed_nets if only is None else net not in only):
                continue
            ends = {}
            for r in rs:
                for e in ("a", "b"):
                    ends.setdefault(_key(r[e]), []).append((r, e))
            vias = [v for v in self.vias if v.net == net and layer in v.layers]
            pads = [p for p in sp.items[layer] if p.kind == "pad" and p.net == net]
            # T-joins: an end on another track's interior
            tee = set()
            for k, lst in ends.items():
                if len(lst) != 1:
                    continue
                P = Point(lst[0][0][lst[0][1]])
                for r in rs:
                    if r is lst[0][0] or r["mid"] is None:
                        continue              # straight tracks were split at their T-joins
                    g = LineString(A.track_coords(_T(r)))
                    if g.distance(P) < 1e-4 and min(math.dist(r["a"], P.coords[0]), math.dist(r["b"], P.coords[0])) > 1e-4:
                        tee.add(k)
                        tee.add(("tee", r["uuid"]))

            def fixed(k):
                lst = ends[k]
                p = lst[0][0][lst[0][1]]
                P = Point(p)
                for v in vias:
                    if v.geom.distance(P) <= v.r + 1e-6:
                        return "via"
                for pd in pads:
                    if pd.geom.distance(P) <= 1e-6:
                        return "pad"
                if len(lst) != 2 or k in tee:
                    return "node"
                r1, r2 = lst[0][0], lst[1][0]
                if abs(r1["w"] - r2["w"]) > 1e-6:
                    return "width"
                return None

            fx = {k: fixed(k) for k in ends}
            seen = set()
            for r in rs:
                if id(r) in seen:
                    continue
                # walk to a fixed end
                chain = [(r, "a", "b")]
                seen.add(id(r))
                for direction in (0, 1):
                    while True:
                        cr, ein, eout = chain[-1] if direction == 0 else chain[0]
                        k = _key(cr[eout] if direction == 0 else cr[ein])
                        if fx.get(k):
                            break
                        nxt = [(rr, e) for rr, e in ends[k] if rr is not cr]
                        if not nxt or id(nxt[0][0]) in seen:
                            break
                        rr, e = nxt[0]
                        seen.add(id(rr))
                        o = "b" if e == "a" else "a"
                        if direction == 0:
                            chain.append((rr, e, o))
                        else:
                            chain.insert(0, (rr, o, e))
                recs = [c[0] for c in chain]
                pts = []
                for cr, ein, eout in chain:
                    cs = A.track_coords(_T(cr))
                    if ein == "b":
                        cs = cs[::-1]
                    if pts and math.dist(pts[-1], cs[0]) < 1e-5:
                        cs = cs[1:]
                    pts.extend(cs)
                kinds = (fx.get(_key(chain[0][0][chain[0][1]])) or "node", fx.get(_key(chain[-1][0][chain[-1][2]])) or "node")
                if any(cr["locked"] for cr in recs) and self.o["respect_locked"]:
                    self._skip("locked")
                    continue
                if any(("tee", cr["uuid"]) in tee for cr in recs):
                    self._skip("tee carrier")
                    continue
                if len({round(cr["w"], 6) for cr in recs}) != 1:
                    self._skip("width")
                    continue
                if len(pts) < 3 and not any(k == "pad" for k in kinds):
                    continue
                out.append((net, layer, recs[0]["w"], recs, pts, kinds))
        return out

    def _skip(self, why):
        self.stats["skipped"][why] = self.stats["skipped"].get(why, 0) + 1

    # ---------------------------------------------------------------- obstacles
    def _sensitive_gap(self, net, other, layer):
        if not self.o["victims"] or not other or other == net:
            return None
        g = self.PC.victim_gap(self.h[layer])
        if net in self.victims and other in self.switch or other in self.victims and net in self.switch:
            return self.PC.DEFAULTS["victim_gap_max"]
        if (net in self.victims and other not in self.ground) or (other in self.victims and net not in self.ground):
            return g
        return None

    def _input_copper(self, net, layer):
        """The input's copper of `net` on `layer` (tracks, vias, pads) as one shapely geometry."""
        c = self.__dict__.setdefault("_inc", {})
        k = (net, layer)
        if k not in c:
            gs = [LineString(A.track_coords(_T(r))).buffer(r["w"] / 2, quad_segs=16)
                  for r in self.orig.values() if r["net"] == net and r["layer"] == layer]
            gs += [v.geom.buffer(v.r, quad_segs=16) for v in self.vias if v.net == net and layer in v.layers]
            gs += [p.geom for p in self.sp.items[layer] if p.kind == "pad" and p.net == net]
            c[k] = unary_union(gs) if gs else None
        return c[k]

    def _input_parts(self, net, layer):
        """The input's copper of `net` on `layer` as (geometries, radii): track centrelines (arcs
        sampled), via centres, pad shapes; distances to it are exact (no buffered polygons)."""
        c = self.__dict__.setdefault("_inp", {})
        k = (net, layer)
        if k not in c:
            gs, rs = [], []
            for r in self.orig.values():
                if r["net"] == net and r["layer"] == layer:
                    gs.append(LineString(A.track_coords(_T(r))))
                    rs.append(r["w"] / 2)
            for v in self.vias:
                if v.net == net and layer in v.layers:
                    gs.append(v.geom)
                    rs.append(v.r)
            for p in self.sp.items[layer]:
                if p.kind == "pad" and p.net == net:
                    gs.append(p.geom)
                    rs.append(0.0)
            c[k] = (np.array(gs, dtype=object), np.array(rs, float))
        return c[k]

    def _item_gap(self, it, net, layer):
        """Edge-to-edge distance from item `it` to the input copper of `net` on `layer`: the floor
        a pair keeps at this item when the input was already nearer than the rule (a victim gap,
        or a clearance the input broke). Per item, so one pair of adjacent pins does not lift a
        rule along the whole net; measured on the input, so passes cannot ratchet it down."""
        c = self.__dict__.setdefault("_itg", {})
        k = (id(it), net, layer)
        if k not in c:
            gs, rs = self._input_parts(net, layer)
            c[k] = math.inf if not len(gs) else max(0.0, float(np.min(shapely.distance(gs, it.geom) - rs)) - it.r)
        return c[k]

    def obstacles(self, net, layer, w, window, orig_line, skip_nets=()):
        """[Obstacle] for a branch of `net`, width w on `layer` inside `window`; each Obstacle.key =
        (item or tag, R_need) where R_need is the centreline distance the requirement asks."""
        sp = self.sp
        out = []
        bb = window.bounds
        reach = sp.max_need + w / 2 + 2.5
        half = w / 2
        for it in sp.query(layer, bb, reach):
            if it.net and it.net in skip_nets:
                continue
            nd = sp.need(it, net, "track", layer)
            if nd is None:
                continue
            if it.kind in ("keepout", "corridor"):
                nd = 0.0
            gap = self._sensitive_gap(net, it.net, layer) if it.kind in ("track", "via", "pad") else None
            floor = False
            if gap is not None:
                ig = self._item_gap(it, net, layer)
                if min(gap, ig) > nd:
                    nd = min(gap, ig)
                    floor = ig < gap          # held at the input's own distance: no margin on top
                    if floor:
                        self._floors[id(it)] = ig - A.SAG - 1e-4
            Rn = it.r + nd + half - (MARGIN if floor else 0.0)
            if it.geom.distance(window) > Rn + 1e-6:
                continue
            d_in = it.geom.distance(orig_line)
            if it.kind == "corridor" and d_in - it.r <= half + 1e-6:
                # a thermal-spoke corridor (kae's guidance, not a KiCad rule) the input already
                # crosses: no constraint here; the DRC gate judges the spokes (starved_thermal)
                self._floors[id(it)] = -math.inf
                continue
            if d_in < Rn + MARGIN and it.kind not in ("keepout", "corridor"):
                if d_in - it.r - half < nd - 1e-6:
                    # the branch breaks this clearance already (an input DRC error): moving it
                    # could repeat the error along the item, so it stays as it is
                    self._input_bad = True
                # the input keeps the clearance with less than the margin (a gap exactly one track
                # wide): the branch may use the input's own distance, never less than the rule
                d_edge = max(nd, min(self._item_gap(it, net, layer), d_in - it.r - half))
                if d_edge + it.r + half < Rn + MARGIN:
                    Rn = it.r + d_edge + half - MARGIN
                    self._floors[id(it)] = d_edge - A.SAG - 1e-4
            out.append(G.make_obstacle(it.geom, Rn + MARGIN, key=(it, Rn)))
        # adjacent layers: sensitive tracks keep the distance they had (broadside coupling)
        if self.o["victims"]:
            for l in self.adj[layer]:
                for it in sp.query(l, bb, 2.5):
                    if it.kind != "track" or it.net in skip_nets:
                        continue
                    gap = self._sensitive_gap(net, it.net, l)
                    if gap is None:
                        continue
                    d0 = self._item_gap(it, net, layer)
                    if d0 <= CHECK_TOL:
                        continue
                    Rn = it.r + min(gap, d0) + half - (MARGIN if d0 < gap else 0.0)
                    if it.geom.distance(window) > Rn:
                        continue
                    out.append(G.make_obstacle(it.geom, Rn + MARGIN, key=(("adj", l, it.uuid), Rn)))
        # other nets' fills
        if self.o["pours"] == "hold":
            for onet, byl in self.fills.items():
                if onet == net or onet in skip_nets:
                    continue
                for poly in byl.get(layer) or []:
                    if poly.distance(window) > reach:
                        continue
                    c = sp._pair(net, onet, layer)
                    nd = max(c.track_track if c is not None else sp._generic_need(net, "track", layer),
                             self.zone_clr.get((onet, layer), 0.0))
                    Rn = nd + half
                    core = poly.intersection(window.buffer(Rn + 0.5))
                    own = self._input_copper(net, layer)
                    if own is not None:
                        # the knockout the refill made around this net's input copper is free;
                        # measured on the input, so a pass cannot eat into the pour
                        core = core.difference(own.buffer(nd + 0.02, quad_segs=8))
                    if core.is_empty:
                        continue
                    core = shapely.make_valid(core)
                    polys = [g for g in getattr(core, "geoms", [core]) if g.geom_type == "Polygon" and g.area > 1e-8]
                    for g in polys:
                        out.append(G.make_obstacle(g, Rn + MARGIN, key=(("fill", onet), Rn)))
        # the board edge
        if sp.outline is not None:
            e = sp.edge_need(net, "track", layer)
            Rn = e + half
            box = window.buffer(Rn + 1.0)
            outside = box.difference(sp.outline)
            if not outside.is_empty:
                for g in getattr(outside, "geoms", [outside]):
                    if g.geom_type == "Polygon" and g.distance(window) <= Rn:
                        out.append(G.make_obstacle(g, Rn + MARGIN, key=("edge", Rn)))
        return out

    def checker(self, obs, w):
        cores = np.array([o.core for o in obs], dtype=object)
        need = np.array([o.key[1] for o in obs]) if obs else np.zeros(0)
        for o in obs:
            shapely.prepare(o.core)

        def check(pieces):
            bad = []
            for i, p in enumerate(pieces):
                g = LineString(A.piece_coords(p))
                if not len(cores):
                    continue
                d = shapely.distance(cores, g)
                extra = A.SAG if p[0] == "arc" else 0.0
                k = np.nonzero(d < need + CHECK_TOL + extra)[0]
                if len(k):
                    j = int(k[np.argmin(d[k] - need[k])])
                    bad.append((i, j))
            return bad
        return check

    # ---------------------------------------------------------------- pad tails
    def _pad_at(self, net, layer, p):
        best = None
        for pd in self.sp.items[layer]:
            if pd.kind != "pad" or pd.net != net:
                continue
            if pd.geom.distance(Point(p)) <= 1e-6:
                if best is None or pd.geom.area < best.geom.area:
                    best = pd
        return best

    def _bga(self, pd):
        c = self.__dict__.setdefault("_bga_c", {})
        if pd.fp not in c:
            c[pd.fp] = self._bga0(pd)
        return c[pd.fp]

    def _bga0(self, pd):
        pads = [p for p in self.sp.pads_by_fp.get(pd.fp, []) if p.kind == "pad" and p.smd]
        if len(pads) < 9:
            return False
        rnd = 0
        for p in pads:
            g = p.geom
            mrr = g.minimum_rotated_rectangle
            x, y = mrr.exterior.coords.xy
            e = [math.dist((x[i], y[i]), (x[i + 1], y[i + 1])) for i in range(2)]
            if max(e) > 0 and min(e) / max(e) > 0.95 and abs(g.area - math.pi * (max(e) / 2) ** 2) < 0.1 * g.area:
                rnd += 1
        return rnd >= 9

    def _current(self, net, w):
        if net in self.power or net in self.ground or PE.current_net(net):
            return True
        try:
            opt = self.sp.width_limits(net, self.sp.cu[0])[1]
        except Exception:       # noqa: BLE001
            opt = w
        return w >= 0.4 or w > opt + 1e-6

    def _pad_current(self, pd, net):
        """Current (A) through the pad `pd` of `net` (power_copper.pad_currents on the operating facts)."""
        if self._currents is None:
            op = self.PC._operating(self.path, self.o.get("operating"))
            pads = [(f.ref, p.net) for f in self.board.footprints for p in f.pads if p.net]
            self._currents = self.PC.pad_currents(op, pads, self.power, self.ground) if op else {}
        ref = pd.owner[0] if isinstance(pd.owner, tuple) else None
        return self._currents.get((ref, net), 0.0)

    def _land_targets(self, pad, pd, net, layer, w, R, stub, cur):
        """Rule-D targets of pad_entry (centreline_targets: no copper beside or beyond the land) for
        a branch of width w released at R: ([(a, end, kind)], neck width or None, overhang kept).
        A track wider than every entry is necked (pad_entry.neck_width: at most the land width, at
        least the board minimum and what the pad's current needs, the wide copper ending
        neck_len + w/2 off the outline); when the current needs more, the wide copper stays (the
        tip test alone) and a land hazard is recorded."""
        ts = PE.centreline_targets(pad, R, w, stub=stub)
        if ts:
            return ts, None, False
        i_a = self._pad_current(pd, net)
        need = self.PC.current_need(i_a, self.PC.DEFAULTS["current_margin"])
        min_w = self.sp.width_limits(net, layer)[0]
        land = PE.land_width(pad)
        fit, nts = PE.neck_width(pad, R, w, 0.0, min_w, stub=PE.NECK_LEN + w / 2)
        if fit is not None and fit + 1e-9 >= need and fit < w - 1e-9:
            return nts, fit, False
        if need > 0 and (need >= land or fit is not None):
            ref, pin = pd.owner if isinstance(pd.owner, tuple) and len(pd.owner) == 2 else (None, None)
            key = (ref, pin, net)
            if key not in self._flagged:
                self._flagged.add(key)
                self.hazards.append(PE.land_hazard(ref, pin, net, w, land, need, i_a))
            return PE.centreline_targets(pad, R, w, stub=stub, check_overhang=False), None, True
        return [], None, False

    def tails(self, net, layer, w, pts):
        """Candidate tails at the start of pts (which begins in a pad of net), pad-entry rule D:
        every track ends on the pad's long centre line (the segment along the long axis, (w - h)/2
        each side of the centre; a square or round pad's centre; a stadium's end-circle centres),
        and the piece crossing the pad outline is within 10 degrees of the outline's normal.
        [(tail points from the end to the anchor, anchor, square, index into pts of the first kept
        point, connector, pad to check a direct entry against, tail width or None, overhangs)];
        [] when the start is no pad end:
        - direct: the path runs straight to the nearest centre-line point (no tail; kept only when
          its crossing turns out square and adds no copper past the land, checked in tighten);
        - pad_entry.centreline_targets (straight in within 10 deg, square through the long edge to the
          centre line, along the axis through the short edge to the centre line's end, radially into
          a round end; the
          same overhang test as pad_reroute: no copper beside or beyond the land); the anchor is
          one track width outside the outline, the turn there becomes a tangent arc
          (_fillet_anchors). A track wider than every entry is necked to the widest that fits
          (tail width), or kept wide with a land hazard where its current needs the width;
        - the input's own tail as the fallback.
        Current-carrying tracks entering along the axis end at least a width inside the outline."""
        pd = self._pad_at(net, layer, pts[0])
        if pd is None:
            return []
        pad = pd.geom
        if pad.geom_type != "Polygon":
            pad = max(getattr(pad, "geoms", [pad]), key=lambda g: g.area)
        fat = pad.buffer(1e-6)
        k = next((i for i, p in enumerate(pts) if not fat.contains(Point(p))), None)
        if k is None:
            return None            # the branch never leaves the pad
        stub = max(w, 0.1)
        c = PE.crossing(pad, pts[k], pts[k - 1]) or pts[k - 1]
        seg_out = math.dist(c, pts[k])
        d = ((pts[k][0] - c[0]) / max(seg_out, 1e-12), (pts[k][1] - c[1]) / max(seg_out, 1e-12))
        ang = PE.entry_angle(pad, pts[k], pts[k - 1])
        orig_anchor = (c[0] + d[0] * min(stub, seg_out), c[1] + d[1] * min(stub, seg_out))
        orig_tail = list(pts[:k]) + [orig_anchor]
        perp_orig = ang is not None and ang <= self.o["max_angle"] and seg_out >= stub - 1e-9
        over_orig = PE.overhangs(pad, pts[k], pts[k - 1], w)
        fallback = (orig_tail, orig_anchor, perp_orig, k, None, None, None, over_orig)
        if self._bga(pd) or any(v.geom.distance(pd.geom) <= 1e-6 for v in self.vias if v.net == net) \
                or not self.o["pad_tails"]:
            return [fallback]
        fr = _pad_frame(pad)
        if fr is None:
            return [fallback]
        ctr, u, L, H, round_ = fr
        cur = self._current(net, w)
        vx, vy = -u[1], u[0]
        R = pts[k]
        rx = (R[0] - ctr[0]) * u[0] + (R[1] - ctr[1]) * u[1]
        half = max(0.0, (L - H) / 2)
        ts, neck, kept_wide = self._land_targets(pad, pd, net, layer, w, R, stub, cur)
        if neck is not None:
            self.stats["necks_planned"] = self.stats.get("necks_planned", 0) + 1
        out = []
        tw = neck or w
        for a, end, kind in ts:
            # "straight" is kept beside the free direct candidate below: where it coincides with
            # the axial or long target, pad_entry returns it alone, as "straight"
            if kind in ("axial", "straight") and cur and neck is None:
                # current-carrying copper: at least a width deep where that still fits (never past the
                # centre's projection, so a straight entry through the long side stays on the centre line)
                x = PE.crossing(pad, a, end)
                dd = PE._unit(end[0] - a[0], end[1] - a[1])
                if x is not None and dd is not None:
                    t = min(max(math.dist(x, end), w), max(0.0, (ctr[0] - x[0]) * dd[0] + (ctr[1] - x[1]) * dd[1]))
                    e2 = (x[0] + t * dd[0], x[1] + t * dd[1])
                    if kept_wide or not PE.overhangs(pad, a, e2, w):
                        end = e2
            out.append(([end, a], a, True, k, orig_anchor, None, neck, kept_wide))
        if neck is None:
            # direct to the nearest centre-line point, when the crossing is square (checked after the solve)
            e_d = ctr if round_ else (ctr[0] + max(-half, min(half, rx)) * u[0], ctr[1] + max(-half, min(half, rx)) * u[1])
            out.append(([e_d], e_d, True, k, orig_anchor, pad, None, None))
        out.append(fallback)
        return out

    # ---------------------------------------------------------------- one branch
    def tighten(self, net, layer, w, recs, pts, kinds):
        sp = self.sp
        old_len = sum(A.track_length(_T(r)) for r in recs)
        heads = self.tails(net, layer, w, pts) if kinds[0] == "pad" else []
        tails = self.tails(net, layer, w, pts[::-1]) if kinds[1] == "pad" else []
        if heads is None or tails is None:
            return None
        if not heads:
            heads = [([pts[0]], pts[0], True, 1, None, None, None, False)]
        if not tails:
            tails = [([pts[-1]], pts[-1], True, 1, None, None, None, False)]
        over_in = int(bool(heads[-1][7])) + int(bool(tails[-1][7]))     # the input's entries hanging past their lands
        ka, kb = heads[-1][3], tails[-1][3]
        if ka >= len(pts) - kb:
            return None
        allp = list(pts) + [h[1] for h in heads] + [t[1] for t in tails]
        orig_line = LineString(pts)
        self._floors = {}
        cands = []
        # the plain trim: the input's own path with each pad tail cut to its entry (pad_trim's cut,
        # perpendicular where the input already was); a fallback when no taut path is found
        h0, t0 = heads[-1], tails[-1]
        if h0[4] is None and t0[4] is None and all(r["mid"] is None for r in recs):
            # (a branch with arcs is a taut result already: its sampled arcs must not come back
            # as segments)
            mid = _dedupe([h0[1]] + list(pts[h0[3]:len(pts) - t0[3]]) + [t0[1]])
            pieces = _tail_pieces(h0[0]) + _tail_pieces(mid) + _tail_pieces(t0[0][::-1])
            cands.append(((_acute_corners(pieces), 0 if (h0[2] and t0[2]) else 1, over_in, G.path_length(pieces)),
                          pieces, G.path_length(pieces), None, [w] * len(pieces)))
        fails = []
        input_bad = False
        for grow in (1, 2, 4):
            window = G.convex_window(allp, self.o["margin_win"] * grow)
            self._input_bad = False
            obs = self.obstacles(net, layer, w, window, orig_line)
            if self._input_bad:
                input_bad = True
                break
            bs = G.BranchSpace(obs, window, None, eps_topo=self.o["eps_topo"], check=self.checker(obs, w), slack=MARGIN)
            got, fails = [], []
            for h in heads:
                for t in tails:
                    mid = [h[1]] + ([h[4]] if h[4] is not None else []) + list(pts[h[3]:len(pts) - t[3]]) \
                        + ([t[4]] if t[4] is not None else []) + [t[1]]
                    mid = _dedupe(mid)
                    if len(mid) < 2:
                        continue
                    if not self._tail_ok(net, layer, h[6] or w, h[0]) or not self._tail_ok(net, layer, t[6] or w, t[0]):
                        continue
                    r = bs.solve(mid)
                    if r is None:
                        fails.append(bs.fail)
                        continue
                    # a direct entry counts only when the piece crossing the outline is square
                    if h[5] is not None and not _square_entry(h[5], r.pieces, 0, self.o["max_angle"]):
                        continue
                    if t[5] is not None and not _square_entry(t[5], r.pieces, 1, self.o["max_angle"]):
                        continue
                    r = _fillet_anchors(r, h[0], t[0], w, bs.check)
                    # a neck: the wide copper stays neck_len off the land (power_copper's neck rule)
                    if any(x[6] is not None and _near_land(x[0][0], r.pieces, PE.NECK_LEN + w / 2 - 2e-3, self, net, layer)
                           for x in (h, t)):
                        continue
                    L = r.length + _plen(h[0]) + _plen(t[0])
                    hp, tp = _tail_pieces(h[0]), _tail_pieces(t[0][::-1])
                    pieces = hp + r.pieces + tp
                    widths = [h[6] or w] * len(hp) + [w] * len(r.pieces) + [t[6] or w] * len(tp)
                    ov = sum(int(bool(x[7])) if x[7] is not None else
                             int(_direct_overhangs(x[5], r.pieces, e, w)) for x, e in ((h, 0), (t, 1)))
                    got.append(((_acute_corners(pieces), 0 if (h[2] and t[2]) else 1, ov, L), pieces, L, r, widths))
            if not got and "apex unmapped" in fails and grow < 4:
                continue                  # the funnel ran along the window: a larger one
            if got and not all(g[3].certificate.get("window", True) for g in got) and grow < 4:
                continue
            cands += got
            break
        # the best candidate (fewest acute corners: a hairpin at a tail is worse than an oblique entry;
        # then perpendicular entries, then length) that
        # is shorter than the input and passes the board's exact check
        acute_in = _acute_corners(_tail_pieces(pts))     # never more acute corners than the input had
        # shorter than the input; or, where it takes copper off a land the input hung past, at most
        # pad_reroute's length limit longer. Never more acute corners or overhanging entries; ranked
        # by acute corners, square entries, overhanging entries, length.
        ok = sorted((c for c in cands if c[0][0] <= acute_in and c[0][2] <= over_in and
                     (c[2] < old_len - self.o["min_gain"] or
                      (c[0][2] < over_in and c[2] <= old_len * (1 + LEN_REL) + LEN_ABS))), key=lambda c: c[0])
        if not ok:
            self._skip("input breaks a clearance" if input_bad else
                       ("no gain" if cands else "solve: " + (fails[0] if fails else "tails illegal")))
            return None
        for score, pieces, L, r, widths in ok:
            pieces, widths = _merge_tiny(pieces, widths)
            if r is None or self._exact_ok(net, layer, widths, pieces):
                break             # (the plain trim is a subset of the input's copper)
        else:
            self._skip("space check")
            return None
        st = self.stats.setdefault("certificate", dict(g1=0, window=0, fillet=0, inserted=0, perpendicular=0, trim_only=0))
        st["perpendicular"] += score[1] == 0
        necks = sum(1 for x in (widths[0], widths[-1]) if x < w - 1e-9) if len(widths) > 1 else int(widths[0] < w - 1e-9)
        if r is None:
            st["trim_only"] = st.get("trim_only", 0) + 1
            return dict(pieces=pieces, widths=widths, length=L, old=old_len, cert={}, inserted=0, score=score, necks=0,
                        over=score[2], over_in=over_in)
        cert = r.certificate
        st["g1"] += bool(cert.get("g1"))
        st["window"] += bool(cert.get("window", True))
        st["fillet"] += bool(cert.get("fillet"))
        st["inserted"] += r.inserted
        return dict(pieces=pieces, widths=widths, length=L, old=old_len, cert=cert, inserted=r.inserted, score=score,
                    necks=necks, over=score[2], over_in=over_in)

    def _exact_ok(self, net, layer, w, pieces):
        """The board's exact check (critical_space.Space, the chain's own copper is the same net), an
        item the input was already this close to excepted (floors). w: one width, or one per piece."""
        ws = w if isinstance(w, (list, tuple)) else [w] * len(pieces)
        for p, wp in zip(pieces, ws):
            for it, d, nd in A.polyline_violations(self.sp, net, layer, wp, A.piece_coords(p)):
                fl = self._floors.get(id(it)) if it != "edge" else None
                if fl is not None and d >= fl - 1e-6:
                    continue
                return False
        return True

    def _tail_ok(self, net, layer, w, tail):
        for a, b in zip(tail[:-1], tail[1:]):
            if math.dist(a, b) < 1e-9:
                continue
            if self.sp.track_violations(net, layer, w, a, b, first=True):
                return False
        return True

    # ---------------------------------------------------------------- diff pairs
    def pairs_pass(self):
        """Tighten each coupled diff-pair section as a pair: one centreline, legs at its constant
        offset +-D/2. Yields {net: gain} per pair changed."""
        seen = set()
        for p, n in sorted(self.pair_of.items()):
            if (n, p) in seen or p not in self.pair_of:
                continue
            seen.add((p, n))
            ch = self.chains(only={p, n})
            for layer in {c[1] for c in ch}:
                cps = [c for c in ch if c[0] == p and c[1] == layer]
                cns = [c for c in ch if c[0] == n and c[1] == layer]
                for cp in cps:
                    for cn in cns:
                        if abs(cp[2] - cn[2]) > 1e-6:
                            continue
                        self.stats["pairs_tried"] = self.stats.get("pairs_tried", 0) + 1
                        try:
                            got = self.tighten_pair(cp, cn)
                        except Exception as e:      # noqa: BLE001
                            self._skip(f"pair error {type(e).__name__}")
                            got = None
                        if got:
                            self.stats["pairs_improved"] = self.stats.get("pairs_improved", 0) + 1
                            yield got
                            break

    def tighten_pair(self, cp, cn, tol=0.02, step=0.05):
        net_p, layer, w, recs_p, pts_p, _ = cp
        net_n, _, _, recs_n, pts_n, _ = cn
        LP, LN = LineString(pts_p), LineString(pts_n)
        if LP.length < 1.0 or LN.length < 1.0:
            return None
        ss = np.arange(0.0, LP.length + 1e-9, step)
        P = [LP.interpolate(t) for t in ss]
        d = np.array([LN.distance(q) for q in P])
        D = float(np.median(d))
        if D > 1.5 or D < w:
            return None
        self.stats["pairs_coupled"] = self.stats.get("pairs_coupled", 0) + 1
        ok = np.abs(d - D) <= tol

        def head(L, t):
            a, b = L.interpolate(max(0.0, t - 0.02)), L.interpolate(min(L.length, t + 0.02))
            return math.atan2(b.y - a.y, b.x - a.x)
        # coupled = at the pitch and running parallel (a converging fan-out is at the pitch for a moment)
        par = np.array([abs(math.sin(head(LP, t) - head(LN, LN.project(q)))) < math.sin(math.radians(2))
                        for t, q in zip(ss, P)])
        ok &= par
        # corners of a coupled pair (mitred or rounded) leave short dips (the legs turn a pitch apart):
        # close gaps of up to 1.5 pitches
        gap = int(round(max(0.25, 1.5 * D) / step))
        idx = np.nonzero(ok)[0]
        for a_, b_ in zip(idx[:-1], idx[1:]):
            if 1 < b_ - a_ <= gap + 1:
                ok[a_:b_] = True
        # the longest coupled run along P
        best, cur = (0, -1), None
        for i, v in enumerate(ok):
            if v and cur is None:
                cur = i
            if (not v or i == len(ok) - 1) and cur is not None:
                j = i if v else i - 1
                if j - cur > best[1] - best[0]:
                    best = (cur, j)
                cur = None
        i0, i1 = best
        if i1 - i0 < 1.0 / step or (i1 - i0 + 1) < 0.6 * len(ss):
            return None                   # not a coupled pair (Freerouting's pairs mostly are not)
        s0, s1 = ss[i0], ss[i1]

        def frame(s):
            a, b = LP.interpolate(max(0.0, s - 0.01)), LP.interpolate(min(LP.length, s + 0.01))
            t = _ang((a.x, a.y), (b.x, b.y))
            q = LP.interpolate(s)
            m = LN.interpolate(LN.project(q))
            return (q.x, q.y), (m.x, m.y), t
        p0, n0, t0 = frame(s0)
        p1, n1, t1 = frame(s1)
        side = 1 if math.sin(t0) * (n0[0] - p0[0]) * -1 + math.cos(t0) * (n0[1] - p0[1]) < 0 else -1
        # side = +1: P is on the left of the travel direction (N on the right)
        m0 = ((p0[0] + n0[0]) / 2, (p0[1] + n0[1]) / 2)
        m1 = ((p1[0] + n1[0]) / 2, (p1[1] + n1[1]) / 2)
        mids = [m0]
        for s in ss[i0 + 1:i1]:
            q = LP.interpolate(s)
            m = LN.interpolate(LN.project(q))
            mids.append(((q.x + m.x) / 2, (q.y + m.y) / 2))
        mids.append(m1)
        mids = _dedupe(mids)
        if len(mids) < 2:
            return None
        weff = w + D
        cline = LineString(mids)
        window = G.convex_window(list(pts_p) + list(pts_n), self.o["margin_win"])
        self._floors = {}
        self._input_bad = False
        obs = self.obstacles(net_p, layer, weff, window, cline, skip_nets={net_n})
        if self._input_bad:
            self._skip("pair: input breaks a clearance")
            return None
        # the partner's requirements too (a pad of a third net may need more from N than from P)
        obs_n = self.obstacles(net_n, layer, weff, window, cline, skip_nets={net_p})
        if self._input_bad:
            self._skip("pair: input breaks a clearance")
            return None
        obs = obs + obs_n
        bs = G.BranchSpace(obs, window, None, eps_topo=self.o["eps_topo"], check=self.checker(obs, weff), slack=MARGIN)
        r = bs.solve(mids)
        if r is None:
            self._skip("pair: " + str(bs.fail))
            return None
        # keep the section's end headings (the legs then meet the fixed fan-outs): Dubins-type
        # start and end arcs where the free path would turn at an end
        best = None
        rho = D / 2 + w / 2 + 0.05
        for s_a in (0, 1, -1):
            for s_b in (0, 1, -1):
                nodes = [G.Wrap(m0)]
                if s_a:
                    nodes.append(G.Wrap((m0[0] - s_a * rho * math.sin(t0), m0[1] + s_a * rho * math.cos(t0)), rho, s_a, 1.0))
                nodes += r.nodes[1:-1]
                if s_b:
                    nodes.append(G.Wrap((m1[0] - s_b * rho * math.sin(t1), m1[1] + s_b * rho * math.cos(t1)), rho, s_b, 1.0))
                nodes.append(G.Wrap(m1))
                pieces, kept, _ = G.solve_wraps(nodes)
                if pieces is None or bs.check(pieces):
                    continue
                if abs(A.norm_angle(_heading(pieces[0], 0) - t0)) > 1e-6 or abs(A.norm_angle(_heading(pieces[-1], 1) - t1)) > 1e-6:
                    continue
                L = G.path_length(pieces)
                if best is None or L < best[0]:
                    best = (L, pieces)
        if best is None:
            self._skip("pair: end headings")
            return None
        cpieces = best[1]
        legs = {}
        for net, o, recs, pts, L0 in ((net_p, side * D / 2, recs_p, pts_p, LP), (net_n, -side * D / 2, recs_n, pts_n, LN)):
            leg = _offset(cpieces, o)
            if leg is None:
                self._skip("pair: offset")
                return None
            if net == net_p:
                a_s, b_s = s0, s1
            else:
                a_s, b_s = LN.project(Point(n0)), LN.project(Point(n1))
            head = _sub_line(L0, 0.0, a_s)
            tail = _sub_line(L0, b_s, L0.length)
            pieces = _tail_pieces(head + [A.piece_ends(leg[0])[0]]) + leg + _tail_pieces([A.piece_ends(leg[-1])[1]] + tail)
            pieces = _merge_tiny(pieces)
            legs[net] = (pieces, recs, L0.length)
        # skew never worse (the legs differ by D x the net turning, fixed by the kept headings)
        dl_old = legs[net_p][2] - legs[net_n][2]
        dl_new = G.path_length(legs[net_p][0]) - G.path_length(legs[net_n][0])
        if abs(dl_new) > abs(dl_old) + 5e-3:
            self._skip("pair: skew")
            return None
        gain = {k: v[2] - G.path_length(v[0]) for k, v in legs.items()}
        if sum(gain.values()) < 2 * self.o["min_gain"]:
            self._skip("pair: no gain")
            return None
        # exact checks with both nets' old copper out of the way
        olds = [self.item_of[r["uuid"]] for k in legs for r in legs[k][1] if r["uuid"] in self.item_of]
        self._remove(olds)
        try:
            for k, (pieces, _, _) in legs.items():
                for pc in pieces:
                    for it, dd, nd in A.polyline_violations(self.sp, k, layer, w, A.piece_coords(pc)):
                        fl = self._floors.get(id(it)) if it != "edge" else None
                        if it != "edge" and it.net in legs:
                            continue          # the partner's old copper (both move)
                        if fl is not None and dd >= fl - 1e-6:
                            continue
                        self._skip("pair: space check")
                        return None
        finally:
            for it in olds:
                for l in it.layers:
                    self.sp.items[l].append(it)
                self.sp.invalidate()
        for k, (pieces, recs, _) in legs.items():
            self.apply(k, layer, w, recs, pieces)
        return gain

    # ---------------------------------------------------------------- apply
    def apply(self, net, layer, w, recs, pieces, widths=None):
        sp = self.sp
        widths = widths or [w] * len(pieces)
        rm = []
        for r in recs:
            self.recs.pop(r["uuid"], None)
            it = self.item_of.pop(r["uuid"], None)
            if it is not None:
                rm.append(it)
        if rm:
            self._remove(rm)
        prev = None
        for p, w in zip(pieces, widths):
            u = W.new_uuid()
            s, e = A.piece_ends(p)
            if prev is not None:
                s = prev                  # one shared point per joint, so KiCad sees them connected
            prev = tuple(e)
            if p[0] == "seg":
                rec = dict(uuid=u, net=net, layer=layer, w=w, a=tuple(s), b=tuple(e), mid=None,
                           locked=False, parent=None, orig=False)
            else:
                m = A.csa_to_sme(p[1], p[2], p[3], p[4])[1]
                rec = dict(uuid=u, net=net, layer=layer, w=w, a=tuple(s), b=tuple(e), mid=tuple(m),
                           locked=False, parent=None, orig=False)
            self.recs[u] = rec
            it = self.Item("track", net, [layer], LineString(A.piece_coords(p)), w / 2.0, sp.rc(net), owner=("taut", u))
            it.uuid, it.width, it.locked = u, w, False
            sp.items[layer].append(it)
            self.item_of[u] = it
        sp.invalidate(layer)
        self.changed_nets.add(net)

    def _remove(self, items):
        ids = {id(i) for i in items}
        layers = {l for i in items for l in i.layers}
        for l in layers:
            self.sp.items[l] = [it for it in self.sp.items[l] if id(it) not in ids]
            self.sp.invalidate(l)

    # ---------------------------------------------------------------- passes
    def run_passes(self):
        t0 = time.monotonic()
        for k in range(self.o["passes"]):
            t1 = time.monotonic()
            chains = self.chains()
            chains.sort(key=lambda c: -(_plen(c[4]) - math.dist(c[4][0], c[4][-1])))
            gain = {}
            n_imp = 0
            for net, layer, w, recs, pts, kinds in chains:
                self.stats["tried"] += 1
                try:
                    got = self.tighten(net, layer, w, recs, pts, kinds)
                except Exception as e:      # noqa: BLE001 - one branch never costs the board
                    self._skip(f"error {type(e).__name__}")
                    got = None
                if got is None:
                    continue
                self.apply(net, layer, w, recs, got["pieces"], got.get("widths"))
                gain[net] = gain.get(net, 0.0) + got["old"] - got["length"]
                self.necks[net] = self.necks.get(net, 0) + got.get("necks", 0)
                self.over_fixed[net] = self.over_fixed.get(net, 0) + got.get("over_in", 0) - got.get("over", 0)
                n_imp += 1
            if self.o["pairs"] == "coupled" and self.pair_of:
                for got in self.pairs_pass():
                    for net in got:
                        gain[net] = gain.get(net, 0.0) + got[net]
                    n_imp += 1
            tot = sum(gain.values())
            mx = max(gain.values()) if gain else 0.0
            self.stats["passes"].append(dict(branches=len(chains), improved=n_imp, gain_mm=round(tot, 4),
                                             max_net_gain_mm=round(mx, 5), s=round(time.monotonic() - t1, 1)))
            self.log(f"[taut] pass {k}: {len(chains)} branches, {n_imp} shorter, -{tot:.3f} mm "
                     f"(largest net -{mx:.4f} mm) in {time.monotonic() - t1:.1f}s")
            if mx <= self.o["conv_eps"]:
                break
        self.stats["improved"] = sum(p["improved"] for p in self.stats["passes"])
        self.t_passes = time.monotonic() - t0
        return self.stats

    # ---------------------------------------------------------------- revert (exact)
    def _install(self, net, recs):
        """Replace the current copper of `net` by the records `recs` (Space kept in step)."""
        sp = self.sp
        for r in [r for r in self.recs.values() if r["net"] == net]:
            self.recs.pop(r["uuid"])
            it = self.item_of.pop(r["uuid"], None)
            if it is not None:
                self._remove([it])
        layers = set()
        for r in recs:
            rr = dict(r)
            self.recs[rr["uuid"]] = rr
            layers.add(rr["layer"])
            it = self.Item("track", net, [rr["layer"]], LineString(A.track_coords(_T(rr))), rr["w"] / 2,
                           sp.rc(net), owner="existing" if rr["orig"] else ("taut", rr["uuid"]))
            it.uuid, it.width, it.locked = rr["uuid"], rr["w"], rr["locked"]
            sp.items[rr["layer"]].append(it)
            self.item_of[rr["uuid"]] = it
        for l in layers:
            sp.invalidate(l)

    def snapshot(self):
        """Remember the passes' result per changed net (set_kept installs any subset of it)."""
        self._final = {n: [dict(r) for r in self.recs.values() if r["net"] == n] for n in self.changed_nets}
        self._orig_of = {}
        for r in self.orig.values():
            self._orig_of.setdefault(r["net"], []).append(r)

    def set_kept(self, keep):
        """The passes' copper for the nets in `keep` (diff pairs together), the input's for the other
        changed nets; then, exactly, drop every kept net whose new copper is too close to restored
        copper (only conflicts with restored nets count: the rest was checked when it was made).
        Returns the nets kept."""
        keep = set(keep) & set(self._final)
        keep = {n for n in keep if n not in self.pair_of or self.pair_of[n] in keep or self.pair_of[n] not in self._final}
        for n in self._final:
            self._install(n, self._final[n] if n in keep else self._orig_of.get(n, []))
        while True:
            restored = set(self._final) - keep
            drop = set()
            for n in keep:
                for r in self._final[n]:
                    if r["orig"]:
                        continue
                    v = A.polyline_violations(self.sp, n, r["layer"], r["w"], A.track_coords(_T(r)))
                    if any(it != "edge" and it.net in restored for it, _, _ in v):
                        drop.add(n)
                        break
            if not drop:
                break
            for n in list(drop):
                if n in self.pair_of:
                    drop.add(self.pair_of[n])
            keep -= drop
            for n in drop & set(self._final):
                self._install(n, self._orig_of.get(n, []))
        self.changed_nets = set(keep)
        return keep

    def revert(self, nets):
        """Restore the input copper of `nets` (and whatever then conflicts with it, exactly).
        Returns the full set reverted."""
        before = set(self.changed_nets)
        self.set_kept(before - set(nets))
        return before - self.changed_nets

    # ---------------------------------------------------------------- write
    def write(self, dst):
        """dst = the input with the current routing of changed nets. Returns {written uuid: net}."""
        text = self.path.read_text(encoding="utf-8")
        present = {}
        for r in self.recs.values():
            if r["orig"]:
                present.setdefault(r["parent"], []).append(r)
        # an input track stays as it is when all its pieces do; else its kept pieces are rewritten
        drop = {r["parent"] for r in self.orig.values() if r["net"] in self.changed_nets
                and len(present.get(r["parent"], ())) != self.parts_of[r["parent"]]}
        out, pos = [], 0
        for head, a, b in W._blocks(text, ("segment", "arc")):
            u = W._uuid_of(text[a:b])
            if u in drop:
                out.append(text[pos:a])
                pos = W._eat_newline(text, b)
        out.append(text[pos:])
        text = "".join(out)
        chunks = []
        groups = {}
        for r in self.recs.values():
            if r["orig"] and r["parent"] not in drop:
                continue
            if r["orig"]:
                r = dict(r, uuid=W.new_uuid())          # a kept piece of a rewritten track
            groups[r["uuid"]] = r["net"]
            if r["mid"] is None:
                chunks.append(W.track_sexpr(r["net"], r["layer"], r["w"], r["a"], r["b"], uid=r["uuid"], locked=False))
            else:
                chunks.append(A.arc_sexpr(r["net"], r["layer"], r["w"], r["a"], r["mid"], r["b"], uid=r["uuid"]))
        Path(dst).write_text(W._insert(text, chunks), encoding="utf-8")
        for ext in (".kicad_pro", ".kicad_dru"):
            s, t = self.path.with_suffix(ext), Path(dst).with_suffix(ext)
            if s.exists() and s.resolve() != t.resolve():
                shutil.copy2(s, t)
        return groups

    def net_geoms(self):
        out = {}
        for r in self.recs.values():
            if not r["orig"]:
                g = LineString(A.track_coords(_T(r))).buffer(r["w"] / 2, quad_segs=4)
                out[r["net"]] = g if r["net"] not in out else out[r["net"]].union(g)
        return out


class _T:
    """A record seen as a kae Track (start, end, mid)."""
    __slots__ = ("start", "end", "mid")

    def __init__(self, r):
        self.start, self.end, self.mid = r["a"], r["b"], r["mid"]


def _plen(pts):
    return sum(math.dist(a, b) for a, b in zip(pts[:-1], pts[1:]))


def _dedupe(pts):
    out = []
    for p in pts:
        if not out or math.dist(out[-1], p) > 1e-7:
            out.append(tuple(p))
    return out


def _tail_pieces(tail):
    tail = _dedupe(tail)
    return [("seg", a, b) for a, b in zip(tail[:-1], tail[1:])]


def _deflect(a, b, c):
    return abs(A.norm_angle(_ang(b, c) - _ang(a, b)))


def _heading(p, end):
    return G._heading(p, end)


def _pad_frame(pad):
    """(centre, unit long axis, length L, width H, round) of a pad polygon from its minimum rotated
    rectangle; round when its area is a disc's. None for shapes the rule cannot frame (a centre
    line outside the copper)."""
    mrr = pad.minimum_rotated_rectangle
    if mrr.geom_type != "Polygon":
        return None
    cs = list(mrr.exterior.coords)[:4]
    e1 = (cs[1][0] - cs[0][0], cs[1][1] - cs[0][1])
    e2 = (cs[2][0] - cs[1][0], cs[2][1] - cs[1][1])
    l1, l2 = math.hypot(*e1), math.hypot(*e2)
    if min(l1, l2) < 1e-6:
        return None
    (ex, ey), L, H = (e1, l1, l2) if l1 >= l2 else (e2, l2, l1)
    u = (ex / L, ey / L)
    c = mrr.centroid
    ctr = (c.x, c.y)
    round_ = abs(L - H) < 0.02 * L and abs(pad.area - math.pi * L * L / 4) < 0.05 * pad.area
    half = (L - H) / 2
    for x in (-half, half):
        if not pad.buffer(1e-6).contains(Point(ctr[0] + x * u[0], ctr[1] + x * u[1])):
            return None
    return ctr, u, L, H, round_


def _square_entry(pad, pieces, end, max_angle):
    """Whether the path's piece that crosses the pad outline (at its start: end 0, else at its end)
    is a segment within max_angle of the outline's normal."""
    p = pieces[0] if end == 0 else pieces[-1]
    if p[0] != "seg":
        return False
    a, b = (p[2], p[1]) if end == 0 else (p[1], p[2])      # outside -> inside
    ang = PE.entry_angle(pad, a, b)
    return ang is not None and ang <= max_angle


def _of_net(ob, net):
    k = ob.key[0]
    if isinstance(k, tuple) and k and k[0] == "fill":
        return k[1] == net
    if isinstance(k, tuple) and k and k[0] == "adj":
        return False
    return getattr(k, "net", None) == net


def _offset(pieces, o):
    """The tangent/arc path offset by o to its left (o < 0: right): segments shifted along their
    left normal, arcs about the same centre at radius r - o (counter-clockwise) or r + o."""
    out = []
    for p in pieces:
        if p[0] == "seg":
            h = _ang(p[1], p[2])
            nx, ny = -math.sin(h) * o, math.cos(h) * o
            out.append(("seg", (p[1][0] + nx, p[1][1] + ny), (p[2][0] + nx, p[2][1] + ny)))
        else:
            _, c, r, a0, sw = p
            rr = r - o if sw > 0 else r + o
            if rr <= 1e-6:
                return None
            out.append(("arc", c, rr, a0, sw))
    # one shared point per joint
    for i in range(1, len(out)):
        e = A.piece_ends(out[i - 1])[1]
        if out[i][0] == "seg":
            out[i] = ("seg", e, out[i][2])
    return out


def _sub_line(line, a, b):
    """Points of `line` between arc lengths a and b (both ends included)."""
    if b - a < 1e-9:
        q = line.interpolate(a)
        return [(q.x, q.y)]
    cs = list(line.coords)
    out = [tuple(line.interpolate(a).coords[0])]
    acc = 0.0
    for p, q in zip(cs[:-1], cs[1:]):
        L = math.dist(p, q)
        if a < acc + L - 1e-12 and acc + L < b - 1e-12:
            out.append(tuple(q))
        acc += L
    out.append(tuple(line.interpolate(b).coords[0]))
    return _dedupe(out)


def _fillet_anchors(r, head, tail, w, check):
    """Where the taut path turns at a pad tail's anchor (pad-entry rule D: the turn before the
    entry is a tangent arc, not a corner), start it instead with an arc tangent to the tail (radius
    1.5w, w or w/2, the largest that is legal and makes no acute corner): the path out of the
    anchor is then the shortest one with that initial heading and turning radius (a Dubins-type
    start), still the same homotopy class. The same at the far end."""
    nodes = list(r.nodes)
    changed = False
    for end in (0, 1):
        tl = _dedupe(head if end == 0 else tail)
        if len(tl) < 2 or not r.pieces:
            continue
        a = tl[-1]
        hd = _ang(tl[-2], tl[-1])                       # the tail's heading out of the pad
        if end == 0:
            h_path = _heading(r.pieces[0], 0)
            turn = A.norm_angle(h_path - hd)
        else:
            h_path = _heading(r.pieces[-1], 1) + math.pi      # reversed: leaving the far anchor
            turn = A.norm_angle(h_path - hd)
        if abs(turn) <= math.radians(1.0):
            continue
        sgn = 1 if turn > 0 else -1
        for rho in (1.5 * w, w, w / 2):
            # circle tangent to the tail at the anchor, on the side the path turns to
            Lx, Ly = -math.sin(hd), math.cos(hd)
            c = (a[0] + sgn * rho * Lx, a[1] + sgn * rho * Ly)
            if end == 0:
                trial = [nodes[0], G.Wrap(c, rho, sgn, abs(turn))] + nodes[1:]
            else:
                # travelling towards the anchor the turn runs the other way round
                trial = nodes[:-1] + [G.Wrap(c, rho, -sgn, abs(turn)), nodes[-1]]
            pieces, kept, _ = G.solve_wraps(trial)
            if pieces is None or check(pieces) or _acute_corners(pieces):
                continue
            nodes, changed = kept, True
            r = G.Result(pieces, G.path_length(pieces), kept, dict(r.certificate, fillet=True), r.window_grown, r.inserted)
            break
    return r


def _acute_corners(pieces, tol_deg=90.0):
    n = 0
    for p, q in zip(pieces[:-1], pieces[1:]):
        if math.degrees(abs(A.norm_angle(_heading(q, 0) - _heading(p, 1)))) > tol_deg + 1e-6:
            n += 1
    return n


def _merge_tiny(pieces, widths=None):
    """Arcs narrower than arcs.MIN_SWEEP become their chord (checked again by the caller); collinear
    neighbouring segments of one width merge. With `widths` (one per piece): (pieces, widths)."""
    out, ws = [], []
    for p, w in zip(pieces, widths if widths is not None else [None] * len(pieces)):
        if p[0] == "arc" and abs(p[4]) < A.MIN_SWEEP:
            s, e = A.piece_ends(p)
            p = ("seg", s, e)
        if p[0] == "seg" and math.dist(p[1], p[2]) < 1e-6:
            continue
        if out and p[0] == "seg" and out[-1][0] == "seg" and ws[-1] == w \
                and _deflect(out[-1][1], out[-1][2], p[2]) < 1e-9:
            out[-1] = ("seg", out[-1][1], p[2])
            continue
        out.append(p)
        ws.append(w)
    # re-chain exactly
    for i in range(1, len(out)):
        prev_end = A.piece_ends(out[i - 1])[1]
        if out[i][0] == "seg":
            out[i] = ("seg", prev_end, out[i][2])
    return out if widths is None else (out, ws)


def _direct_overhangs(pad, pieces, end, w):
    """Whether a direct entry (the path's own piece crossing into `pad`) hangs copper past the land."""
    if pad is None or not pieces:
        return False
    p = pieces[0] if end == 0 else pieces[-1]
    if p[0] != "seg":
        return True
    a, b = (p[2], p[1]) if end == 0 else (p[1], p[2])      # outside -> inside
    return PE.overhangs(pad, a, b, w)


def _near_land(end, pieces, dist, tt, net, layer):
    """Whether any of the taut pieces comes closer than `dist` (centre line) to the pad holding `end`."""
    pd = tt._pad_at(net, layer, end)
    if pd is None:
        return False
    return any(pd.geom.distance(LineString(A.piece_coords(p))) < dist for p in pieces)


# ----------------------------------------------------------------------------- statistics
def board_stats(board_path, info=None, power=None, ground=None):
    """Length per class (signal, power, ground), corners (deflection > 1 deg at a joint of two
    pieces), acute corners (> 90 deg), arcs, pad entries (perpendicular <= 10 deg, oblique, acute
    > 45) of a board."""
    from kae.board.kicad_file import load
    from kae.board import pcbnew_io
    b = load(Path(board_path))
    if power is None:
        from kae.circuit.brief import build
        from . import power_copper as PC
        power, ground, _, _ = PC.classify(build(b), b.nets)
    st = dict(length=dict(signal=0.0, power=0.0, ground=0.0), corners=0, acute=0, arcs=0, segments=0,
              entries=0, perpendicular=0, oblique=0, acute_entries=0, overhanging=0, overhang_mm2=0.0)
    ends = {}
    for t in b.tracks:
        cls = "ground" if t.net in ground else "power" if t.net in power else "signal"
        st["length"][cls] += A.track_length(t)
        st["arcs" if t.mid is not None else "segments"] += 1
        got = A.sme_to_csa(t.start, t.mid, t.end) if t.mid is not None else None
        if got is not None:
            # exact tangents at the arc's ends (a chord's direction is off by half its angle)
            c, r_, a0, sw = got
            h0 = a0 + math.copysign(math.pi / 2, sw)
            h1 = a0 + sw + math.copysign(math.pi / 2, sw)
        else:
            h0 = h1 = _ang(t.start, t.end)
        ends.setdefault((t.net, t.layer, _key(t.start)), []).append(h0 + math.pi)    # pointing away from the joint
        ends.setdefault((t.net, t.layer, _key(t.end)), []).append(h1)
    vias = {(v.net, _key((v.x, v.y))) for v in b.vias}
    for (net, layer, k), hs in ends.items():
        if len(hs) != 2 or (net, k) in vias:
            continue
        # deflection between the incoming heading and the outgoing one
        d = abs(A.norm_angle(hs[0] - (hs[1] + math.pi)))
        dd = math.degrees(math.pi - abs(A.norm_angle(hs[0] - hs[1])))
        if dd > 1.0:
            st["corners"] += 1
        if dd > 90.0 + 1e-6:
            st["acute"] += 1
    if info is None:
        with tempfile.TemporaryDirectory(prefix="kae-taut-") as d:
            info = pcbnew_io.export_dsn(Path(board_path), Path(d) / "board.dsn", probes=False)
    from .constraints import _pad_shapes
    pads = {}
    for pd in info.get("pads") or []:
        dsn, real = _pad_shapes(pd)
        for l in pd.get("layers") or []:
            g = real.get(l) or dsn
            if g is not None and not g.is_empty:
                pads.setdefault((pd.get("net") or "", l), []).append(g)
    for t in b.tracks:
        if t.mid is not None:
            continue
        for g in pads.get((t.net, t.layer), ()):
            ina, inb = g.contains(Point(t.start)), g.contains(Point(t.end))
            if ina == inb:
                continue
            ang = PE.entry_angle(g, t.start, t.end)
            st["entries"] += 1
            ov = PE.overhang(g, t.end if ina else t.start, t.start if ina else t.end, t.width)
            if ov > PE.OVER_AREA:
                st["overhanging"] += 1
                st["overhang_mm2"] = round(st["overhang_mm2"] + ov, 4)
            if ang is None:
                continue
            st["perpendicular" if ang <= 10 else "oblique" if ang <= 45 else "acute_entries"] += 1
    st["length"] = {k: round(v, 3) for k, v in st["length"].items()}
    return st


# ----------------------------------------------------------------------------- DRC-gated run
def run(input_path, output_path, opts=None, workdir=None, timeout=1800, log=print):
    from . import power_copper as PC
    t0 = time.monotonic()
    o = {**DEFAULTS, **(opts or {})}
    inp = Path(input_path).resolve()
    wd = Path(workdir or tempfile.mkdtemp(prefix="kae-taut-"))
    wd.mkdir(parents=True, exist_ok=True)
    staged = W.stage(inp, wd / "in", "board")
    tt = Taut(staged, o, log=log)
    tt.run_passes()
    t_plan = time.monotonic() - t0
    base_rep, base = PC._drc(staged, wd / "in.drc.json", timeout)
    cand = wd / "out" / "board.kicad_pcb"
    cand.parent.mkdir(parents=True, exist_ok=True)
    rounds = []
    budget = [int(o["drc_budget"])]
    final = None
    reverted = set()

    def check(tag):
        groups = tt.write(cand)
        budget[0] -= 1
        rep, s = PC._drc(cand, wd / f"out.{tag}.json", timeout)
        worse = PC._worse(s, base)
        rounds.append(dict(tag=tag, changed=len(tt.changed_nets), summary=s, worse=worse))
        log(f"[taut] {tag}: {s['errors']} errors, {s['unconnected']} unconnected (input {base['errors']}, "
            f"{base['unconnected']}); {len(tt.changed_nets)} nets changed; worse {worse or 'none'}")
        return rep, worse, groups

    tt.snapshot()
    allnets = sorted(tt._final)
    r = 0
    while tt.changed_nets and budget[0] > 0:
        rep, worse, groups = check(f"r{r}")
        r += 1
        if not worse:
            final = rounds[-1]["summary"]
            break
        geoms = tt.net_geoms()
        bad = PC._culprits(rep, base_rep, groups, geoms) & tt.changed_nets
        if not bad:
            bad = PC._culprits(rep, base_rep, groups, geoms, near=2.5) & tt.changed_nets
        if bad:
            reverted |= tt.revert(bad)
            continue
        # not attributable (a starved thermal spoke, a mask bridge named on neighbours): add the
        # nets back batch by batch from the input, keeping each batch that leaves DRC no worse and
        # splitting the ones that do not (ddmin, as power_copper's gate); the best board seen wins
        cands = sorted(tt.changed_nets)
        accepted = set()
        q = max(1, len(cands) // 4)
        queue = [cands[i:i + q] for i in range(0, len(cands), q)]
        k = 0
        while queue and budget[0] > 0:
            batch = queue.pop(0)
            kept = tt.set_kept(accepted | set(batch))
            if not (kept - accepted):
                continue
            _, w2, _ = check(f"r{r}a{k}")
            k += 1
            if not w2:
                accepted = set(kept)
            elif len(batch) > 1:
                queue[:0] = [batch[:len(batch) // 2], batch[len(batch) // 2:]]
        tt.set_kept(accepted)
        reverted |= set(allnets) - accepted
        if accepted and budget[0] > 0:
            continue                  # the accepted set is checked once more as a whole
        break
    if final is not None and budget[0] > 0:
        # recover: the nets reverted by attribution or by conflict with restored copper, added
        # back batch by batch where DRC stays no worse
        good = set(tt.changed_nets)
        cands = sorted(set(allnets) - good)
        q = max(1, len(cands) // 4)
        queue = [cands[i:i + q] for i in range(0, len(cands), q)]
        k = 0
        while queue and budget[0] > 0:
            batch = queue.pop(0)
            kept = tt.set_kept(good | set(batch))
            if not (kept - good):
                continue
            _, w2, _ = check(f"rec{k}")
            k += 1
            if not w2:
                good = set(kept)
                final = rounds[-1]["summary"]
                shutil.copy2(cand, wd / "best.kicad_pcb")
            elif len(batch) > 1:
                queue[:0] = [batch[:len(batch) // 2], batch[len(batch) // 2:]]
        tt.set_kept(good)
        tt.write(cand)
    out = Path(output_path)
    if final is not None and tt.changed_nets:
        shutil.copy2(cand, out)
    else:
        final = base
        reverted |= set(tt.changed_nets)
        shutil.copy2(staged, out)
        tt.changed_nets = set()
    for ext in (".kicad_pro", ".kicad_dru"):
        s_ = inp.with_suffix(ext)
        if s_.exists() and s_.resolve() != out.with_suffix(ext).resolve():
            shutil.copy2(s_, out.with_suffix(ext))
    reverted = set(getattr(tt, "_final", {})) - set(tt.changed_nets)
    rep = dict(board=str(inp), stats=tt.stats, nets_changed=sorted(tt.changed_nets), nets_reverted=sorted(reverted),
               fixed=tt._count_why(), drc_in=base, drc_out=final, rounds=rounds, plan_s=round(t_plan, 2),
               setup_s=round(tt.t_setup, 2), passes_s=round(getattr(tt, "t_passes", 0.0), 2),
               necks=sum(tt.necks.get(n, 0) for n in tt.changed_nets),
               overhang_fixed=sum(tt.over_fixed.get(n, 0) for n in tt.changed_nets),
               hazards=list(tt.hazards))
    rep["stats"]["hazards"] = len(tt.hazards)
    if o.get("power_copper"):
        t1 = time.monotonic()
        pc_out = out.with_name(out.stem + ".pc.kicad_pcb")
        pc = PC.run(out, pc_out, opts=o.get("power_copper_opts"), workdir=wd / "pc", timeout=timeout, log=log)
        shutil.copy2(pc_out, out)
        pc.pop("rounds", None)
        rep["power_copper"] = pc
        rep["power_copper_s"] = round(time.monotonic() - t1, 2)
    rep["total_s"] = round(time.monotonic() - t0, 2)
    return rep


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m kae.route.taut", description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("input")
    r.add_argument("output")
    r.add_argument("--report")
    r.add_argument("--workdir")
    r.add_argument("--timeout", type=int, default=1800)
    r.add_argument("--pours", choices=("hold", "refill"), default=DEFAULTS["pours"])
    r.add_argument("--passes", type=int, default=DEFAULTS["passes"])
    r.add_argument("--no-victims", action="store_true")
    r.add_argument("--no-tails", action="store_true")
    r.add_argument("--power-copper", action="store_true", help="then the (arc-aware) power copper pass")
    r.add_argument("--operating", help="operating facts JSON (pad currents for necks and land hazards; default: the "
                   "project's KAE_OPERATING text variable)")
    s = sub.add_parser("stats")
    s.add_argument("board")
    a = ap.parse_args(argv)
    if a.cmd == "stats":
        print(json.dumps(board_stats(a.board)))
        return
    rep = run(a.input, a.output, dict(pours=a.pours, passes=a.passes, victims=not a.no_victims,
                                      pad_tails=not a.no_tails, power_copper=a.power_copper, operating=a.operating),
              workdir=a.workdir, timeout=a.timeout)
    txt = json.dumps(rep, indent=1, default=str)
    if a.report:
        Path(a.report).write_text(txt)
    print(json.dumps(dict(stats=rep["stats"], drc_in=rep["drc_in"], drc_out=rep["drc_out"], total_s=rep["total_s"],
                          necks=rep["necks"], overhang_fixed=rep["overhang_fixed"], hazards=len(rep["hazards"]),
                          changed=len(rep["nets_changed"]), reverted=len(rep["nets_reverted"])), default=str))


if __name__ == "__main__":
    main()
