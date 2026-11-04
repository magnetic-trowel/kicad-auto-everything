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
    pairs="fixed",           # diff pairs: "fixed" (left alone)
    respect_locked=True,
    drc_budget=40,
    eps_topo=3e-3,
)

MARGIN = 2e-3 + 2 * A.SAG + 1e-4          # mm the exact path keeps above every requirement (TOL + sampling)
CHECK_TOL = 2e-3                          # mm above every requirement in the exact check (critical_space.TOL)


def _key(p):
    return (round(p[0], 5), round(p[1], 5))


def _ang(a, b):
    return math.atan2(b[1] - a[1], b[0] - a[0])


# ----------------------------------------------------------------------------- the pass
class Taut:
    def __init__(self, board_path, opts=None, log=print):
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
        self.board = load(self.path)
        with tempfile.TemporaryDirectory(prefix="kae-taut-") as d:
            self.info = pcbnew_io.export_dsn(self.path, Path(d) / "board.dsn")
        self.sp = Space(self.board, self.info, sev=severities(self.path))
        A.fix_space_arcs(self.sp, self.board.tracks)
        from kae.circuit.brief import build
        self.brief = build(self.board)
        self.power, self.ground, self.switch, self.victims = PC.classify(self.brief, self.board.nets)
        sp = self.sp
        cu = sp.cu
        self.h = {l: (min(abs(sp.z[l] - sp.z[m]) for m in cu if m != l) if len(cu) > 1 else sp.thickness) for l in cu}
        self.adj = {l: [cu[i] for i in (k - 1, k + 1) if 0 <= i < len(cu)] for k, l in enumerate(cu)}
        self.PC = PC
        self.fills = {}
        if self.o["pours"] == "hold":
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
        for n in nets:
            if R.diff_base(n) is not None and R.complement_net(n) in nets:
                why[n] = "diff pair"
        for dp in self.brief.get("diff_pairs") or []:
            for k in ("p", "n"):
                if dp.get(k) in nets:
                    why[dp[k]] = "diff pair"
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
    def chains(self):
        """[(net, layer, w, [rec], [(x, y) path], (end kinds))] of movable branches."""
        sp = self.sp
        by = {}
        for r in self.recs.values():
            by.setdefault((r["net"], r["layer"]), []).append(r)
        out = []
        for (net, layer), rs in by.items():
            if not net or net in self.fixed_nets:
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

    def _input_gap(self, net, other, layer):
        """Edge-to-edge distance between two nets' input copper on `layer` (or between layers
        (l1, l2) projected): the floor a victim pair keeps when it was already nearer than the
        victim gap. Measured on the input, so passes cannot ratchet it down."""
        c = self.__dict__.setdefault("_ing", {})
        l1, l2 = layer if isinstance(layer, tuple) else (layer, layer)
        k = (net, other, l1, l2)
        if k not in c:
            a, b = self._input_copper(net, l1), self._input_copper(other, l2)
            c[k] = math.inf if a is None or b is None else float(a.distance(b))
        return c[k]

    def obstacles(self, net, layer, w, window, orig_line):
        """[Obstacle] for a branch of `net`, width w on `layer` inside `window`; each Obstacle.key =
        (item or tag, R_need) where R_need is the centreline distance the requirement asks."""
        sp = self.sp
        out = []
        bb = window.bounds
        reach = sp.max_need + w / 2 + 2.5
        half = w / 2
        for it in sp.query(layer, bb, reach):
            nd = sp.need(it, net, "track", layer)
            if nd is None:
                continue
            if it.kind in ("keepout", "corridor"):
                nd = 0.0
            gap = self._sensitive_gap(net, it.net, layer) if it.kind in ("track", "via", "pad") else None
            if gap is not None:
                nd = max(nd, min(gap, self._input_gap(net, it.net, layer)))
            Rn = it.r + nd + half
            if it.geom.distance(window) > Rn + 1e-6:
                continue
            d_in = it.geom.distance(orig_line)
            if d_in < Rn + CHECK_TOL:
                # the input is already this close (a DRC error of the input, a spoke corridor it
                # crosses): the branch may come no closer than the input board's copper of this
                # net did (measured on the input, so passes cannot ratchet it down)
                own = self._input_copper(net, layer)
                d_edge = (it.geom.distance(own) - it.r) if own is not None else 0.0
                d_edge = max(0.0, min(d_edge, d_in - it.r - half))
                Rn = it.r + d_edge + half - MARGIN
                self._floors[id(it)] = d_edge - A.SAG - 1e-4
            out.append(G.make_obstacle(it.geom, Rn + MARGIN, key=(it, Rn)))
        # adjacent layers: sensitive tracks keep the distance they had (broadside coupling)
        if self.o["victims"]:
            for l in self.adj[layer]:
                for it in sp.query(l, bb, 2.5):
                    if it.kind != "track":
                        continue
                    gap = self._sensitive_gap(net, it.net, l)
                    if gap is None:
                        continue
                    d0 = self._input_gap(net, it.net, (layer, l))
                    if d0 <= CHECK_TOL:
                        continue
                    Rn = it.r + min(gap, d0) + half
                    if it.geom.distance(window) > Rn:
                        continue
                    out.append(G.make_obstacle(it.geom, Rn + MARGIN, key=(("adj", l, it.uuid), Rn)))
        # other nets' fills
        if self.o["pours"] == "hold":
            for onet, byl in self.fills.items():
                if onet == net:
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

    def tails(self, net, layer, w, pts):
        """Candidate tails at the start of pts (which begins in a pad of net): [(tail points from
        the pad end to the anchor, anchor, perpendicular, index into pts of the first kept point,
        connector)] best first; [] when the start is no pad end."""
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
        out = []
        stub = max(w, 0.1)
        c = PE.crossing(pad, pts[k], pts[k - 1]) or pts[k - 1]
        seg_out = math.dist(c, pts[k])
        d = ((pts[k][0] - c[0]) / max(seg_out, 1e-12), (pts[k][1] - c[1]) / max(seg_out, 1e-12))
        ang = PE.entry_angle(pad, pts[k], pts[k - 1])
        orig_anchor = (c[0] + d[0] * min(stub, seg_out), c[1] + d[1] * min(stub, seg_out))
        orig_tail = list(pts[:k]) + [orig_anchor]
        from . import constraints as CN
        ovl = float(CN.setting("pad_entry_overlap", self.path))
        cur = self._current(net, w)
        if not (cur and self.o["rails"] == "centre") and seg_out > 1e-9:
            # a signal ends `pad_entry_overlap` inside the edge it crosses, along its own axis
            e_in = (c[0] - d[0] * ovl, c[1] - d[1] * ovl)
            if pad.buffer(1e-6).contains(Point(e_in)):
                orig_tail = [e_in, orig_anchor]
        perp_orig = ang is not None and ang <= self.o["max_angle"] and seg_out >= stub - 1e-9
        bga = self._bga(pd)
        via_in_pad = any(v.geom.distance(pd.geom) <= 1e-6 for v in self.vias if v.net == net)
        if perp_orig or bga or via_in_pad or not self.o["pad_tails"]:
            out.append((orig_tail, orig_anchor, perp_orig, k, None))
            return out
        centre = pd.pos or (pad.centroid.x, pad.centroid.y)
        for a, end, u, facing in PE.approach_targets(pad, centre, pts[k], w, ovl, current=cur, stub=stub, max_targets=3):
            if cur and self.o["rails"] == "centre":
                # rails keep their end where it is when it lies on the entry's normal line, or
                # deeper in the land than the entry (a dog-leg inside the land is same-net copper);
                # an end nearer the edge than that moves to the entry's end (a width deep)
                e_ = (a[0] + stub * u[0], a[1] + stub * u[1])
                depth0 = (pts[0][0] - e_[0]) * u[0] + (pts[0][1] - e_[1]) * u[1]
                off = abs((pts[0][0] - a[0]) * -u[1] + (pts[0][1] - a[1]) * u[0])
                depth = (end[0] - e_[0]) * u[0] + (end[1] - e_[1]) * u[1]
                if off < 1e-4 and depth0 > 0:
                    tail = [pts[0], a]
                elif depth0 >= depth - 1e-9:
                    tail = [pts[0], end, a]
                else:
                    tail = [end, a]
            else:
                tail = [end, a]
            out.append((tail, a, True, k, orig_anchor))
        out.append((orig_tail, orig_anchor, False, k, None))
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
            heads = [([pts[0]], pts[0], True, 1, None)]
            hfix = True
        else:
            hfix = False
        if not tails:
            tails = [([pts[-1]], pts[-1], True, 1, None)]
        ka, kb = heads[-1][3], tails[-1][3]
        if ka >= len(pts) - kb:
            return None
        allp = list(pts) + [h[1] for h in heads] + [t[1] for t in tails]
        orig_line = LineString(pts)
        self._floors = {}
        self._floor_hit = False
        res = None
        for grow in (1, 2, 4):
            window = G.convex_window(allp, self.o["margin_win"] * grow)
            obs = self.obstacles(net, layer, w, window, orig_line)
            bs = G.BranchSpace(obs, window, None, eps_topo=self.o["eps_topo"], check=self.checker(obs, w), slack=MARGIN)
            best = None
            fails = []
            for h in heads:
                for t in tails:
                    mid = [h[1]] + ([h[4]] if h[4] is not None else []) + list(pts[h[3]:len(pts) - t[3]]) \
                        + ([t[4]] if t[4] is not None else []) + [t[1]]
                    mid = _dedupe(mid)
                    if len(mid) < 2:
                        continue
                    if not self._tail_ok(net, layer, w, h[0]) or not self._tail_ok(net, layer, w, t[0]):
                        continue
                    r = bs.solve(mid)
                    if r is None:
                        fails.append(bs.fail)
                        continue
                    r = _fillet_anchors(r, h[0], t[0], w, bs.check)
                    tail_len = _plen(h[0]) + _plen(t[0])
                    L = r.length + tail_len
                    pieces = _tail_pieces(h[0]) + r.pieces + _tail_pieces(t[0][::-1])
                    ac = _acute_corners(pieces)
                    score = (0 if (h[2] and t[2]) else 1, ac, L)
                    if best is None or score < best[0]:
                        best = (score, pieces, L, r)
            if best is None:
                if "apex unmapped" in fails and grow < 4:
                    continue              # the funnel ran along the window: a larger one
                self._skip("solve: " + (fails[0] if fails else "tails illegal"))
                return None
            if best[3].certificate.get("window", True):
                res = best
                break
            res = best
        if res is None:
            return None
        score, pieces, L, r = res
        if L > old_len - self.o["min_gain"]:
            self._skip("no gain")
            return None
        pieces = _merge_tiny(pieces)
        # canonical exact check against the board's Space (the chain's own copper is the same net)
        for p in pieces:
            for it, d, nd in A.polyline_violations(sp, net, layer, w, A.piece_coords(p)):
                fl = self._floors.get(id(it)) if it != "edge" else None
                if fl is not None and d >= fl - 1e-6:
                    continue          # no closer than the input was
                self._skip("space check")
                return None
        return dict(pieces=pieces, length=L, old=old_len, cert=r.certificate, inserted=r.inserted, score=score)

    def _tail_ok(self, net, layer, w, tail):
        for a, b in zip(tail[:-1], tail[1:]):
            if math.dist(a, b) < 1e-9:
                continue
            if self.sp.track_violations(net, layer, w, a, b, first=True):
                return False
        return True

    # ---------------------------------------------------------------- apply
    def apply(self, net, layer, w, recs, pieces):
        sp = self.sp
        rm = []
        for r in recs:
            self.recs.pop(r["uuid"], None)
            it = self.item_of.pop(r["uuid"], None)
            if it is not None:
                rm.append(it)
        if rm:
            self._remove(rm)
        prev = None
        for p in pieces:
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
                self.apply(net, layer, w, recs, got["pieces"])
                gain[net] = gain.get(net, 0.0) + got["old"] - got["length"]
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
    def revert(self, nets):
        """Restore the input copper of `nets`; then revert, exactly, every other changed net whose
        new copper is too close to restored copper. Returns the full set reverted."""
        sp = self.sp
        todo = list(nets)
        done = set()
        while todo:
            net = todo.pop()
            if net in done or net not in self.changed_nets:
                continue
            done.add(net)
            rm = [r for r in self.recs.values() if r["net"] == net]
            for r in rm:
                self.recs.pop(r["uuid"])
                it = self.item_of.pop(r["uuid"], None)
                if it is not None:
                    self._remove([it])
            layers = set()
            for u, r in self.orig.items():
                if r["net"] != net:
                    continue
                rr = dict(r)
                self.recs[u] = rr
                layers.add(r["layer"])
                it = self.Item("track", net, [r["layer"]], LineString(A.track_coords(_T(r))), r["w"] / 2,
                               sp.rc(net), owner="existing")
                it.uuid, it.width, it.locked = u, r["w"], r["locked"]
                sp.items[r["layer"]].append(it)
                self.item_of[u] = it
            for l in layers:
                sp.invalidate(l)
            self.changed_nets.discard(net)
            # cascade
            for r in list(self.recs.values()):
                if r["orig"] or r["net"] in done or r["net"] not in self.changed_nets:
                    continue
                if A.polyline_violations(sp, r["net"], r["layer"], r["w"], A.track_coords(_T(r)), first=True):
                    todo.append(r["net"])
        return done

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


def _fillet_anchors(r, head, tail, w, check):
    """Where the taut path leaves a pad tail's anchor at more than 90 degrees to the tail (an acute
    corner), start it instead with an arc tangent to the tail (radius 2w, w or w/2, the largest that
    is legal): the path out of the anchor is then the shortest one with that initial heading and
    turning radius (a Dubins-type start), still the same homotopy class. The same at the far end."""
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
        if abs(turn) <= math.pi / 2 + 1e-9:
            continue
        sgn = 1 if turn > 0 else -1
        for rho in (2 * w, w, w / 2):
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


def _merge_tiny(pieces):
    """Arcs narrower than arcs.MIN_SWEEP become their chord (checked again by the caller); collinear
    neighbouring segments merge."""
    out = []
    for p in pieces:
        if p[0] == "arc" and abs(p[4]) < A.MIN_SWEEP:
            s, e = A.piece_ends(p)
            p = ("seg", s, e)
        if p[0] == "seg" and math.dist(p[1], p[2]) < 1e-6:
            continue
        if out and p[0] == "seg" and out[-1][0] == "seg" and _deflect(out[-1][1], out[-1][2], p[2]) < 1e-9:
            out[-1] = ("seg", out[-1][1], p[2])
            continue
        out.append(p)
    # re-chain exactly
    for i in range(1, len(out)):
        prev_end = A.piece_ends(out[i - 1])[1]
        if out[i][0] == "seg":
            out[i] = ("seg", prev_end, out[i][2])
    return out


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
              entries=0, perpendicular=0, oblique=0, acute_entries=0)
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
        if not bad:
            # not attributable: halve the changed set (largest gains kept first)
            nets = sorted(tt.changed_nets)
            bad = set(nets[len(nets) // 2:]) if len(nets) > 1 else set(nets)
        reverted |= tt.revert(bad)
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
    rep = dict(board=str(inp), stats=tt.stats, nets_changed=sorted(tt.changed_nets), nets_reverted=sorted(reverted),
               fixed=tt._count_why(), drc_in=base, drc_out=final, rounds=rounds, plan_s=round(t_plan, 2),
               setup_s=round(tt.t_setup, 2), passes_s=round(getattr(tt, "t_passes", 0.0), 2))
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
    s = sub.add_parser("stats")
    s.add_argument("board")
    a = ap.parse_args(argv)
    if a.cmd == "stats":
        print(json.dumps(board_stats(a.board)))
        return
    rep = run(a.input, a.output, dict(pours=a.pours, passes=a.passes, victims=not a.no_victims,
                                      pad_tails=not a.no_tails, power_copper=a.power_copper),
              workdir=a.workdir, timeout=a.timeout)
    txt = json.dumps(rep, indent=1, default=str)
    if a.report:
        Path(a.report).write_text(txt)
    print(json.dumps(dict(stats=rep["stats"], drc_in=rep["drc_in"], drc_out=rep["drc_out"], total_s=rep["total_s"],
                          changed=len(rep["nets_changed"]), reverted=len(rep["nets_reverted"])), default=str))


if __name__ == "__main__":
    main()
