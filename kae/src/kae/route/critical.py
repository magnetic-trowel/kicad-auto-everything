# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Physics-first routing of the decisive nets, before the general router.

The copper whose geometry decides a board's physics is routed first, at its physical
optimum, and locked; the Freerouting bridge (kae.route.bridge) then routes everything else
around it (locked items go to Freerouting as fixed wiring). See
docs/topics/routing/critical-net-routing.md.

    from kae.route import critical
    rep = critical.route_critical("in.kicad_pcb", "out.kicad_pcb")      # critical copper only
    rep = critical.run("in.kicad_pcb", "out.kicad_pcb", time_s=900)     # critical, bridge, recheck

What is routed (critical_modules, critical_rails):
- commutation cells: every board hop of the hot loop, as wide as its terminals, on the
  layer next to the reference plane; return vias where they minimize loop L;
- decoupling: capacitor -> IC power pin; capacitor ground and IC ground -> plane vias;
- crystals: XIN/XOUT and the load capacitors, shortest; load-cap ground into the plane;
- protection chains: connector -> protector -> protected part, in that order;
- power rails: widths from E5 currents and a drop budget, zones used where they exist.

Joint use (the month plan's joint loop):
- `optimize_modules(board, brief, terms, locked)` co-optimizes each module's movable part
  poses and its copper on the routed physics and returns (poses, copper);
- `recheck(board_routed, brief, stage)` recomputes each module on the finished copper and
  returns the modules to re-tweak.
"""
from __future__ import annotations

import json
import math
import tempfile
import time
from pathlib import Path

import numpy as np

from kae.board import pcbnew_io
from kae.board.kicad_file import load
from kae.board.model import Track, Via

from . import critical_write as W
from .critical_grid import GridRouter
from .critical_modules import Ctx, modules_from_brief, route_module
from .critical_space import Space

DEFAULTS = dict(
    kinds=("cell", "path", "decap", "rgroup", "crystal", "chain"),
    rails="auto",          # auto: rails whose E5 current needs more than the class width; all; none
    res=0.05,              # grid resolution (mm)
    via_in_pad=False,      # vias inside small SMD pads (thermal pads always allow them)
    decap_max_mm=10.0,     # a capacitor farther than this from its pin: no local decoupling, left to the bridge
    decap_plane_mm=2.0,    # a decap rail hop longer than this over its own rail plane: a via into the plane instead
    chain_power_a=1.0,     # E5 current of a protected power pin without a rail estimate
    chain_tail=False,      # also route (and lock) a chain's hops after the protector (no surge physics)
    rail_light=False,      # also route rail branches that only need the class width (no drop physics)
    trim_tol=0.05,         # loop hops narrowed to the narrowest width within this of the wide loop (0: off)
    complete_mm=8.0,       # join a critical net's pads within this distance of its critical copper (benchmark
                           # run crit-v3: A+B cp1 0.636 with joins vs 0.515 without; oasis 9 -> 1 unconnected)
    island_mm=20.0,        # and its islands of critical copper to each other within this distance
    escape_mm=0.0,         # escape corridors this long out of dense ICs' signal pins (0: off; see escape_corridors)
    escape_pins=32,        # an IC with at least this many pads is dense
    escape_cost=3.0,       # per-cell cost of a critical track of another net inside a corridor
    corner_joins=True,     # every track end at a pad/via centre or a track corner (what Freerouting sees)
    soft=(),               # joins written unlocked for Freerouting to keep or rip: "complete", "pad" (rail pads)
    guards=("cell", "path", "crystal"),   # modules whose ground plane gets a kae-crit: guard pour for the bridge
    guard_margin=0.5,      # mm around the module's copper and pads
    thermal_spokes=True,   # manual spokes first for pads the placement starves (Session.thermal_spokes)
    lm_soft=False,         # the bridge's last mile may re-lay critical copper, kept by the joint loop's
                           # physics rule (soft_critical)
)


def _log(msg):
    print(f"[kae.critical {time.strftime('%H:%M:%S')}] {msg}", flush=True)


# ----------------------------------------------------------------------------- setup
class Session:
    """Everything critical routing needs for one board: model, brief, rules, space, router."""

    def __init__(self, board_path, brief=None, info=None, opts=None, log=_log, board=None, terms=None):
        t0 = time.monotonic()
        self.path = Path(board_path).resolve()
        self.opts = {**DEFAULTS, **(opts or {})}
        self.log = log
        self.board = board or load(self.path)
        if brief is None:
            from kae.circuit.brief import build
            brief = build(self.board)
        self.brief = brief
        if info is None:
            with tempfile.TemporaryDirectory(prefix="kae-crit-") as d:
                info = pcbnew_io.export_dsn(self.path, Path(d) / "board.dsn")
        self.info = info
        from .bridge import severities
        self.sev = severities(self.path)
        self.space = Space(self.board, info, sev=self.sev, opts=self.opts)
        self.router = GridRouter(self.space, res=self.opts["res"])
        if terms is None and self.opts.get("place_allocs", True):
            # the placer's terms: every module is priced against the allocations the placer
            # optimizes (critical_modules.allocation, decap_spend)
            from .critical_modules import place_terms
            terms = place_terms(self.board, brief, log=log)
        self.terms = terms
        if float(self.opts.get("escape_mm", 0.0) or 0.0) > 0:
            self.router.escapes = self.escape_corridors(float(self.opts["escape_mm"]),
                                                        int(self.opts.get("escape_pins", 32)), brief)
            self.router.escape_cost = float(self.opts.get("escape_cost", 3.0))
        self.ctx = Ctx(self.space, self.router, brief, self.board, dict(self.opts, log=log), terms=terms)
        self.router.gnd = set(self.ctx.gnd)
        self.modules = []
        self.rails = []
        self.t_setup = time.monotonic() - t0

    # ------------------------------------------------------------------ routing
    def route(self, budget_s=None):
        """Route every module, then the rails; stops starting new modules once `budget_s`
        seconds are spent (the rest is left to the general router)."""
        t0 = time.monotonic()
        budget = budget_s if budget_s is not None else self.opts.get("budget_s")
        pre = list(getattr(self, "pre_modules", []) or [])     # laid before the modules (run: thermal spokes)
        from .critical_rails import rail_currents
        try:
            self.ctx.rail_I = rail_currents(self.ctx)
        except Exception as e:  # noqa: BLE001 - currents only refine widths
            self.log(f"rail currents: {type(e).__name__}: {e}")
            self.ctx.rail_I = {}
        mods = modules_from_brief(self.brief, self.opts["kinds"])
        skip = tuple(self.opts.get("skip") or ())
        mods = [m for m in mods if not m.id.startswith(skip)] if skip else mods
        for m in mods:
            t1 = time.monotonic()
            if budget is not None and t1 - t0 > budget:
                m.status = "skipped"
                m.notes.append("time budget spent")
                continue
            route_module(self.ctx, m)
            m.physics["seconds"] = round(time.monotonic() - t1, 3)
            self.log(f"{m.id}: {m.status}, {len(m.copper)} items, "
                     f"{m.physics.get('value')} {m.physics.get('unit', '')} (u {m.physics.get('u')})"
                     + (f" [{'; '.join(m.notes[:3])}]" if m.notes else ""))
        self.modules = pre + mods
        if self.opts.get("rails", "auto") != "none" and (budget is None or time.monotonic() - t0 < budget):
            from .critical_rails import route_rails
            self.rails = route_rails(self.ctx, mode=self.opts.get("rails", "auto"))
        # the pads left near critical copper are joined here (Freerouting does not join an
        # island to the middle of a fixed track)
        self.completed = {}
        reach = float(self.opts.get("complete_mm", 8.0))
        isl = float(self.opts.get("island_mm", 20.0))
        if (reach > 0 or isl > 0) and (budget is None or time.monotonic() - t0 < budget):
            from .critical_rails import complete_module_nets
            self.completed = complete_module_nets(self.ctx, reach, isl)
        if self.opts.get("corner_joins", True):
            self.joins = self.join_at_corners()
        self.t_route = time.monotonic() - t0
        return self

    def thermal_spokes(self):
        """Manual thermal spokes, laid first, for the pads the placement already starves:
        KiCad's DRC on the input names the pads whose zone connection has fewer spokes than
        the zone's minimum (their neighbours leave too little fill), and each gets the
        missing spokes as short tracks of its net from inside the pad into the fill
        (repair.spoke_tracks, KiCad's manual spokes), legal by the exact checks. Critical
        copper laid after them keeps clear of them, so the repair loop is not left with a
        spoke it can no longer draw past locked copper (paw3395: C11's GND pad starved on the
        bare board, crit's VIN copper then took the room of its second spoke). Returns
        [Module] (one, id "spokes") or []."""
        import tempfile
        from kae.board import pcbnew_io
        from . import drc, repair as RP
        from .critical_modules import Module
        with tempfile.TemporaryDirectory(prefix="kae-spokes-") as d:
            staged = drc.stage_board(self.path, self.path, Path(d))
            rep = drc.run(staged, Path(d) / "drc.json", timeout=600)
            starved = [v for v in drc.errors(rep) if v.get("type") == "starved_thermal"]
            if not starved:
                return []
            fills = pcbnew_io.zone_fills(staged)["zones"]
        zones = {z["uuid"]: z for z in fills}
        pads = {p["uuid"]: p for p in self.info["pads"] if p.get("uuid")}
        plan = self.space.plan
        rs = RP._Space({}, self.info, plan)
        m = Module(id="spokes", kind="spokes", spec={}, parts=[])
        for v in starved:
            its = v.get("items") or []
            pad = next((pads[it["uuid"]] for it in its if it.get("uuid") in pads), None)
            zone = next((zones[it["uuid"]] for it in its if it.get("uuid") in zones), None)
            mm = RP._DRC_LAYER.search(v.get("description") or "")
            sp_ = RP._SPOKES.search(v.get("description") or "")
            layer = mm.group(1).strip() if mm else None
            if pad is None or zone is None or layer not in self.space.cu:
                continue
            need = max(1, int(sp_.group(1)) - int(sp_.group(2))) if sp_ else 1
            for t in RP.spoke_tracks(pad, zone, layer, need, plan, rs, taken=[]):
                a, b = tuple(t["a"]), tuple(t["b"])
                if self.space.track_violations(t["net"], layer, t["width"], a, b, first=True):
                    continue
                m.copper.append(self.space.add_track(t["net"], layer, t["width"], a, b,
                                                     owner=("spokes", f"{pad.get('ref')}.{pad.get('number')}")))
        if not m.copper:
            return []
        m.status = "routed"
        self.log(f"thermal spokes: {len(m.copper)} for {len(starved)} starved pad connection(s)")
        return [m]

    def escape_corridors(self, length, min_pads, brief):
        """Escape corridors out of dense ICs (at least `min_pads` pads): for each SMD signal
        pad (not a ground or rail net, aspect >= 1.3), the strip as wide as the pad from its
        outer end `length` mm outward along its long axis, on its layer. Critical tracks of
        other nets pay to cross them and their vias stay out (GridRouter.escapes), so the
        IC's signals keep their way out (canhw: decap stubs and vias round an LQFP-100).
        [(geometry, layer, net)]"""
        from shapely.geometry import LineString
        sp = self.space
        nets = (brief or {}).get("nets") or {}
        out = []
        for fu, pads in sp.pads_by_fp.items():
            if len(pads) < min_pads:
                continue
            f = next((x for x in self.board.footprints if x.uuid == fu), None)
            if f is None:
                continue
            for it in pads:
                if not it.smd or not it.net or it.pos is None:
                    continue
                if (nets.get(it.net) or {}).get("role") in ("ground", "rail"):
                    continue
                r = it.geom.minimum_rotated_rectangle
                cs = list(r.exterior.coords)[:4]
                e1 = (cs[1][0] - cs[0][0], cs[1][1] - cs[0][1])
                e2 = (cs[2][0] - cs[1][0], cs[2][1] - cs[1][1])
                l1, l2 = math.hypot(*e1), math.hypot(*e2)
                if min(l1, l2) <= 0 or max(l1, l2) / min(l1, l2) < 1.3:
                    continue
                (ux, uy), L, W = ((e1[0] / l1, e1[1] / l1), l1, l2) if l1 >= l2 else ((e2[0] / l2, e2[1] / l2), l2, l1)
                if ux * (it.pos[0] - f.x) + uy * (it.pos[1] - f.y) < 0:
                    ux, uy = -ux, -uy
                a = (it.pos[0] + ux * L / 2, it.pos[1] + uy * L / 2)
                b = (a[0] + ux * length, a[1] + uy * length)
                g = LineString([a, b]).buffer(W / 2, cap_style=2)
                for l in it.layers:
                    if l in sp.cu:
                        out.append((g, l, it.net))
        return out

    def join_at_corners(self, max_rounds=4):
        """Make every join of the committed copper one Freerouting can see. Freerouting joins
        a wire to a pin or a via only at its centre and to another wire only at a corner;
        KiCad joins anything that overlaps, so a track that ends inside a pad off its centre,
        or on another track's body, is connected for the DRC but an open connection for the
        bridge, which then spends its passes on it.
        A track end inside a same-net pad or via gets a neck to the centre (the widest of its
        width, 3/4, 1/2, the class minimum that is exactly legal); a track end on the body of
        another committed track splits that track there (and necks onto the split point when
        it lies off the centre line). Input routing is never touched. Returns {necks, splits,
        left}."""
        from shapely.geometry import Point as _Pt
        sp = self.space
        mods = {m.id: m for m in list(self.modules) + list(getattr(self.ctx, "rail_modules", []) or [])}
        out = dict(necks=0, splits=0, left=0)
        tol = 1e-4

        def add_piece(net, layer, w0, a, b, owner):
            mn = sp.width_limits(net, layer)[0] or 0.0
            for w in sorted({w0, 0.75 * w0, 0.5 * w0, max(mn, 0.1)}, reverse=True):
                w = sp.clamp_width(net, layer, w)
                if not sp.track_violations(net, layer, w, a, b, first=True):
                    it = sp.add_track(net, layer, w, a, b, owner=owner)
                    m = mods.get((owner or ("",))[0])
                    if m is not None:
                        m.copper.append(it)
                    return it
            return None

        def at_centre(e, x):
            if x.kind == "track":
                return min(math.dist(e, x.geom.coords[0]), math.dist(e, x.geom.coords[-1])) < tol
            if x.kind == "via":
                return math.dist(e, (x.geom.x, x.geom.y)) < tol
            return x.kind == "pad" and x.pos is not None and math.dist(e, x.pos) < tol

        done = set()
        for _ in range(max_rounds):
            changed = False
            for t in [it for it in sp.routed if it.kind == "track"]:
                if t not in sp.routed:
                    continue
                layer = next(iter(t.layers))
                for e in (tuple(t.geom.coords[0]), tuple(t.geom.coords[-1])):
                    if (id(t), e) in done:
                        continue
                    done.add((id(t), e))
                    pe = _Pt(e)
                    same = [x for x in sp.items[layer] if x.net == t.net and x is not t]
                    if any(at_centre(e, x) for x in same):
                        continue
                    centre = body = None
                    for x in same:
                        if x.kind == "pad" and x.pos is not None and x.geom.distance(pe) < 1e-6:
                            centre = tuple(x.pos)
                            break
                        if x.kind == "via" and math.dist(e, (x.geom.x, x.geom.y)) < x.r:
                            centre = (x.geom.x, x.geom.y)
                            break
                    if centre is None:
                        body = next((x for x in same if x.kind == "track" and x.geom.distance(pe) < x.r + 1e-9), None)
                    if centre is not None:
                        if add_piece(t.net, layer, t.width, e, centre, t.owner) is not None:
                            out["necks"] += 1
                            changed = True
                        else:
                            out["left"] += 1
                        continue
                    if body is None:
                        continue
                    a, b = tuple(body.geom.coords[0]), tuple(body.geom.coords[-1])
                    q = body.geom.interpolate(body.geom.project(pe))
                    P = (q.x, q.y)
                    if min(math.dist(P, a), math.dist(P, b)) < tol:
                        P = a if math.dist(P, a) <= math.dist(P, b) else b
                    elif body in sp.existing or body not in sp.routed:
                        out["left"] += 1
                        continue
                    else:
                        sp.remove([body])
                        parts = [sp.add_track(body.net, layer, body.width, a, P, owner=body.owner),
                                 sp.add_track(body.net, layer, body.width, P, b, owner=body.owner)]
                        m = mods.get((body.owner or ("",))[0])
                        if m is not None:
                            m.copper = [c for c in m.copper if c is not body] + parts
                        out["splits"] += 1
                        changed = True
                    if math.dist(e, P) >= tol:
                        if add_piece(t.net, layer, t.width, e, P, t.owner) is not None:
                            out["necks"] += 1
                            changed = True
                        else:
                            out["left"] += 1
            if not changed:
                break
        return out

    # ------------------------------------------------------------------ output
    def soft(self, it):
        """Whether a committed item is a join without physics (a critical net's nearby pads
        and islands, joined at the class width; opts soft): written unlocked, so the bridge
        hands it to Freerouting as ordinary wiring it may keep, shove or rip up, instead of
        a wall it must route around."""
        kinds = self.opts.get("soft") or ()
        o = it.owner or ("", "")
        if "complete" in kinds and o[0] == "complete":
            return True
        return "pad" in kinds and str(o[0]).startswith("rail:") and str(o[1]).startswith("pad:")

    def copper(self):
        """The committed critical copper as kae.board.model Track and Via objects (locked,
        but for the soft joins)."""
        out_t, out_v = [], []
        for it in self.space.routed:
            if not it.uuid:
                it.uuid = W.new_uuid()
            lk = not self.soft(it)
            if it.kind == "track":
                (x0, y0), (x1, y1) = it.geom.coords[0], it.geom.coords[-1]
                out_t.append(Track(uuid=it.uuid, net=it.net, layer=next(iter(it.layers)), width=it.width,
                                   start=(x0, y0), end=(x1, y1), locked=lk))
            elif it.kind == "via":
                out_v.append(Via(uuid=it.uuid, net=it.net, x=it.geom.x, y=it.geom.y, size=it.width, drill=it.drill,
                                 layers=[self.space.cu[0], self.space.cu[-1]], locked=lk))
        return out_t, out_v

    def guards(self, kinds=None, margin=None):
        """Guard pours over the ground plane under each routed module of `kinds`: zones
        named `kae-crit:<module>` on the plane layer, the module's hull (copper and pads,
        plus `margin`) clipped to the plane's own zone outline and clear of other nets'
        zones, overlapping guards merged (critical_recheck.guard_zones, merge_guards). The
        bridge keeps other nets out of them, so the plane under a hot loop or a crystal
        stays whole; the output never carries them (the transplant keeps routing only).
        [(net, layer, rings, name, priority)]"""
        from .critical_recheck import guard_zones, merge_guards
        kinds = self.opts.get("guards") or () if kinds is None else kinds
        margin = self.opts.get("guard_margin", 0.5) if margin is None else margin
        out = []
        for m in self.modules:
            if m.kind not in kinds or m.status not in ("routed", "partial"):
                continue
            region = self._guard_region(m, margin)
            if region is None or region.is_empty:
                continue
            c = region.centroid
            seen = set()
            for u in m.parts:
                h, pl, pn = self.ctx.plane(self.ctx.side_layer(u), c.x, c.y, gnd=True)
                if pl is None or (pl, pn) in seen:
                    continue
                seen.add((pl, pn))
                out += guard_zones(self.board, region, pn, pl, f"{W.GUARD_PREFIX}{m.id}")
        return merge_guards(out)

    def stitch_ground(self, fills, min_area=0.3, want=3, pitch=2.0):
        """Stitching vias for weakly tied ground islands: per ground net and layer, every
        piece of the refilled pour (`fills`: {net: {layer: [Polygon]}}, KiCad's fill of the
        board with the critical copper) other than the layer's largest, at least `min_area`
        mm2, holding ground pads and tied by fewer than `want` barrels (vias, plated holes),
        gets vias inside it that land in the same net's fill on another layer, `pitch` mm
        apart, each exactly legal. Returns the vias added."""
        from shapely.geometry import Point as _Pt
        from shapely.ops import unary_union
        sp = self.space
        D, _d = 0.0, 0.0
        added = 0
        m = next((x for x in self.modules if x.id == "stitch"), None)
        if m is None:
            from .critical_modules import Module
            m = Module(id="stitch", kind="stitch", spec={}, parts=[])
        for net in sorted(self.ctx.gnd):
            byl = fills.get(net) or {}
            unions = {l: unary_union(v) for l, v in byl.items() if v}
            D, _d = sp.via_size(net)
            for l, u in unions.items():
                pieces = [g for g in getattr(u, "geoms", [u]) if g.area >= min_area]
                if len(pieces) < 2:
                    continue
                big = max(pieces, key=lambda g: g.area)
                for g in pieces:
                    if g is big:
                        continue
                    pads = [it for it in sp.pads if it.net == net and l in it.layers and it.geom.intersects(g)]
                    if not pads:
                        continue
                    bar = sum(1 for it in sp.pads if it.net == net and it.hole is not None and it.geom.intersects(g))
                    bar += sum(1 for it in sp.routed + sp.existing if it.kind == "via" and it.net == net
                               and g.contains(it.geom))
                    if bar >= want:
                        continue
                    inner = g.buffer(-(D / 2 + 0.1))
                    if inner.is_empty:
                        continue
                    others = [unions[k] for k in unions if k != l]
                    if not others:
                        continue
                    placed = []
                    # candidates: near the island's pads first, then over the island
                    x0, y0, x1, y1 = inner.bounds
                    step = max(0.25, D / 2)
                    xs = np.arange(x0, x1 + 1e-9, step)
                    ys = np.arange(y0, y1 + 1e-9, step)
                    cands = [(x, y) for x in xs for y in ys]
                    pc = [p.geom.centroid for p in pads]
                    cands.sort(key=lambda q: min(c.distance(_Pt(q)) for c in pc))
                    for x, y in cands:
                        if bar + len(placed) >= want:
                            break
                        pt = _Pt(x, y)
                        if not inner.contains(pt) or not any(o.contains(pt) for o in others):
                            continue
                        if any(math.dist((x, y), q) < pitch for q in placed):
                            continue
                        if sp.via_violations(net, x, y, first=True):
                            continue
                        m.copper.append(sp.add_via(net, x, y, owner=("stitch", f"{l}:{len(placed)}")))
                        placed.append((x, y))
                    added += len(placed)
        if m.copper and m not in self.modules:
            self.modules.append(m)
        return added

    def _guard_region(self, m, margin):
        """Where a module's loop lives: its copper, plus for a cell the hot-loop terminals,
        for other modules the pads of its small parts and the large parts' pads on its nets."""
        from shapely.ops import unary_union
        own = [it for it in self.space.routed if it.owner and it.owner[0] == m.id]
        geoms = [it.geom.buffer(it.r) for it in own]
        if m.kind == "cell":
            geoms += [t.geom for t in m.spec.get("_T") or []]
        else:
            nets = {it.net for it in own} - set(self.ctx.gnd)
            for u in m.parts:
                pads = self.space.pads_by_fp.get(u, [])
                geoms += [it.geom for it in pads if len(pads) <= 4 or it.net in nets]
        if not geoms:
            return None
        return unary_union(geoms).convex_hull.buffer(margin)

    def write(self, dst, guards=()):
        tracks, vias = self.copper()
        W.append_items(self.path, dst,
                       tracks=[(t.net, t.layer, t.width, t.start, t.end, t.uuid, t.locked) for t in tracks],
                       vias=[(v.net, v.x, v.y, v.size, v.drill, v.uuid, v.locked) for v in vias],
                       zones=list(guards))
        for ext in (".kicad_pro", ".kicad_dru", ".kicad_prl"):
            s = self.path.with_suffix(ext)
            t = Path(dst).with_suffix(ext)
            if s.exists() and s.resolve() != t.resolve():
                import shutil
                shutil.copy2(s, t)
        return len(tracks), len(vias)

    def report(self):
        tracks, vias = self.copper()
        return dict(
            board=str(self.path),
            setup_s=round(self.t_setup, 2), route_s=round(getattr(self, "t_route", 0.0), 2),
            tracks=len(tracks), vias=len(vias),
            track_mm=round(sum(math.dist(t.start, t.end) for t in tracks), 2),
            router=dict(self.router.stats),
            completed=dict(getattr(self, "completed", {}) or {}),
            joins=dict(getattr(self, "joins", {}) or {}),
            stitched=int(getattr(self, "n_stitched", 0) or 0),
            space_notes=list(self.space.notes),
            modules=[dict(id=m.id, kind=m.kind, status=m.status, items=len(m.copper), physics=m.physics,
                          notes=m.notes[:6]) for m in self.modules],
            rails=self.rails,
        )


# ----------------------------------------------------------------------------- API
def route_critical(board_path, out_path=None, brief=None, info=None, opts=None, log=_log):
    """Route the critical copper of a placed board; write `out_path` (input + locked copper)
    when given. Returns (report, session)."""
    s = Session(board_path, brief=brief, info=info, opts=opts, log=log).route()
    if out_path:
        s.write(out_path)
    return s.report(), s


def to_json(rep):
    return json.dumps(rep, default=str)


# ----------------------------------------------------------------------------- full pipeline
def run(input_path, output_path, seed=0, time_s=900.0, opts=None, bridge_opts=None, rounds=0, workdir=None,
        log=_log, bridge=True):
    """Critical routing, then the bridge around the locked copper, then (rounds > 0) the
    recheck / re-tweak loop; OUTPUT = INPUT + all routing (nothing else changes). Returns a
    JSON-able report."""
    t0 = time.monotonic()
    input_path, output_path = Path(input_path).resolve(), Path(output_path).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    own = workdir is None
    wd = Path(workdir) if workdir else Path(tempfile.mkdtemp(prefix="kae-crit-", dir=output_path.parent))
    wd.mkdir(parents=True, exist_ok=True)
    rep = dict(input=str(input_path), seed=seed, budget_s=time_s)

    def left():
        return time_s - (time.monotonic() - t0)
    try:
        w0 = wd / "crit.kicad_pcb"
        s = None
        try:
            crit_budget = min(180.0, 0.2 * time_s)
            s = Session(input_path, opts=opts, log=log)
            if s.opts.get("thermal_spokes", True):
                try:
                    s.pre_modules = s.thermal_spokes()
                except Exception as e:  # noqa: BLE001 - spokes refine; the repair loop also draws them
                    log(f"thermal spokes: {type(e).__name__}: {e}")
            s.route(budget_s=crit_budget)
            if (opts or {}).get("stitch", True):
                # ground pour pieces the critical copper leaves weakly tied get stitching vias
                try:
                    from .critical_recheck import fills_of
                    s.write(w0)
                    s.n_stitched = s.stitch_ground(fills_of(w0))
                except Exception as e:  # noqa: BLE001 - stitching is a refinement
                    log(f"stitching: {type(e).__name__}: {e}")
            rep["critical"] = s.report()
            guards = s.guards() if bridge else []
            rep["critical"]["guards"] = len(guards)
            s.write(w0, guards=guards)
        except Exception as e:  # noqa: BLE001 - the general router still runs
            import traceback
            traceback.print_exc()
            rep["critical_error"] = f"{type(e).__name__}: {e}"
            W.stage(input_path, wd, "crit")
        W.transplant(w0, input_path, output_path)        # a valid output from the start
        best = w0
        if bridge and left() > 30:
            from . import bridge as BR
            r0 = wd / "routed0.kicad_pcb"
            if s is not None and (opts or {}).get("lm_soft", DEFAULTS["lm_soft"]):
                bridge_opts = dict(bridge_opts or {}, **soft_critical(s))
            # the re-tweak rounds keep a reserve: up to 30 % of what is left, at most 180 s
            reserve = min(180.0, 0.3 * left()) if rounds > 0 else 0.0
            b = BR.route(w0, r0, seed=seed, time_s=max(20.0, left() - 15.0 - reserve), workdir=wd / "bridge0",
                         opts=dict(bridge_opts or {}, keep=True), log=log)
            if not r0.exists() and left() > 60:
                # no routed board in that share (Freerouting killed at its deadline): once
                # more with all the time left
                log(f"bridge: {b.get('status')}; again with {left() - 15.0:.0f} s")
                b = BR.route(w0, r0, seed=seed + 1, time_s=left() - 15.0, workdir=wd / "bridge0b",
                             opts=dict(bridge_opts or {}, keep=True), log=log)
            rep["bridge"] = {k: v for k, v in b.items() if k in ("status", "seconds", "router", "repair", "drc")}
            if r0.exists():
                best = r0
                W.transplant(r0, input_path, output_path)
            if rounds > 0 and s is not None and r0.exists() and left() > 60:
                from .critical_recheck import retweak_loop
                rep["retweak"] = retweak_loop(s, r0, input_path, output_path, wd, rounds=rounds, seed=seed,
                                              deadline=t0 + time_s - 10.0, bridge_opts=bridge_opts, log=log)
        rep["status"] = "ok"
    except Exception as e:  # noqa: BLE001 - always leave a report
        import traceback
        traceback.print_exc()
        rep["status"] = "error"
        rep["error"] = f"{type(e).__name__}: {e}"
    finally:
        rep["seconds"] = round(time.monotonic() - t0, 2)
        if own and not (opts or {}).get("keep"):
            import shutil
            shutil.rmtree(wd, ignore_errors=True)
        else:
            rep["workdir"] = str(wd)
    return rep


def soft_critical(s, slack=0.10):
    """Bridge options that let the last mile re-lay critical copper (repair._last_mile):
    `soft_fixed`, the uuids of the session's critical tracks and vias, and `physics_guard`,
    which keeps a re-laid board only by the joint loop's rule (kae.joint.scorecard.accept:
    completion and DRC never worse, routed physics (critical_recheck.board_physics, the
    modules' u) at most `slack` of the incumbent's total worse per connection gained)."""
    tracks, vias = s.copper()
    uuids = sorted({t.uuid for t in tracks} | {v.uuid for v in vias})

    def card(board, summary):
        from kae.joint.scorecard import Scorecard
        from .critical_recheck import board_physics
        ph = board_physics(board, brief=s.brief, terms=s.terms)
        c = Scorecard(unconnected=summary["unconnected"], errors=summary["errors"])
        c.modules = {k: v.get("u") for k, v in ph.items() if not k.startswith("_") and isinstance(v, dict)}
        return c

    def guard(before, before_summary, after, after_summary):
        from kae.joint.scorecard import accept
        return accept(card(before, before_summary), card(after, after_summary), phys_slack=slack)
    return dict(soft_fixed=uuids, physics_guard=guard)


def write_joint(src, dst, poses, copper):
    """dst = src with parts moved to `poses` (pcbnew_io.write_poses: KiCad's own writer, any
    angle) and the critical copper added (locked but for soft joins). Project files are
    copied beside dst."""
    import shutil
    src, dst = Path(src), Path(dst)
    if poses:
        pcbnew_io.write_poses(src, dst, {u: tuple(p) for u, p in poses.items()})
    elif src.resolve() != dst.resolve():
        shutil.copy2(src, dst)
    tracks = [c for c in copper if isinstance(c, Track)]
    vias = [c for c in copper if isinstance(c, Via)]
    W.append_items(dst, dst, tracks=[(t.net, t.layer, t.width, t.start, t.end, t.uuid, t.locked) for t in tracks],
                   vias=[(v.net, v.x, v.y, v.size, v.drill, v.uuid, v.locked) for v in vias])
    for ext in (".kicad_pro", ".kicad_dru", ".kicad_prl"):
        s = src.with_suffix(ext)
        t = dst.with_suffix(ext)
        if s.exists() and s.resolve() != t.resolve():
            shutil.copy2(s, t)
    return dst
