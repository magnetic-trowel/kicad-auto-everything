# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Post-route repair driven by KiCad's DRC.

Each round runs kicad-cli DRC (zones refilled, as the scorer does) on the current board and
reads every error-level violation and missing connection:

- a track narrower than its rule (track_width on a routed track) is widened to the
  required minimum in place when the plan's clearances leave room, else ripped up;
- any other violation that involves routed copper (a track or via the router drew) rips up
  the routed items involved (escalating to their whole nets, then to a free re-route);
- a pad with too few thermal spokes (starved_thermal), or cut off from its zone, gets
  spokes drawn as tracks from inside the pad into the zone's fill: KiCad counts a track
  connected to the pad, with one end inside the pad's relief outline and the other in the
  zone's fill, as a spoke. Where no such track fits, the pad's spoke corridors are kept
  clear of other nets (constraints.thermal_corridors) and the routed copper in them is
  ripped up;
- a missing connection between parts of a net that other nets' copper cut apart inside a
  zone (Freerouting counts every pin inside a plane as connected; KiCad's fill does not):
  the net's planes are replaced in the next DSN by the fill pieces KiCad's filler actually
  produced, holes as windows, so the router sees the parts KiCad sees and joins them;
- any other missing connection marks its net for routing again, with its planes left out
  of the DSN.

Locked routing in the input (pre-routes, e.g. from kae.route.critical) is never ripped,
widened or unlocked. The remaining routing is locked (exported as fixed wiring), Freerouting
routes only what is open, in a new item order every round (translate.permute), the session is imported on top,
the routing unlocked again, and the result checked by the next round's DRC. A round's board
replaces the output only if it is better (clean; then fewer violations in all; then fewer
missing connections), so the output never gets worse. Stops when the board is clean, nothing
more can be done, FAILS rounds in a row were not better, the round limit is reached, or time
runs out.
"""
import json
import math
import re
import shutil
import time
from pathlib import Path

from kae.board import pcbnew_io

from . import constraints, drc, freerouting, specctra, translate
from .specctra import Q, find, findall

_NET = re.compile(r"\[([^\]]*)\]")
_MIN = re.compile(r"min (?:width )?([\d.]+) mm")
_SPOKES = re.compile(r"min spoke count (\d+); actual (\d+)")
_DRC_LAYER = re.compile(r"\(layer ([^;)]+)")
_ON_LAYERS = re.compile(r" on (.+?)(?:, priority|, length|$)")


def _key(s):
    """Better boards sort higher: clean, then fewer violations in all (errors plus missing
    connections), then fewer missing connections."""
    return (s["errors"] == 0 and s["unconnected"] == 0, -(s["errors"] + s["unconnected"]), -s["unconnected"])


def _nets_of(item_desc):
    return [m for m in _NET.findall(item_desc or "") if m and m != "<no net>"]


def _is_zone(desc):
    return (desc or "").startswith(("Zone", "Teardrop"))


def _routed_geom(r, grow=0.0):
    from shapely.geometry import LineString, Point
    if r["kind"] == "via":
        return Point(r["pos"]).buffer(r["size"] / 2 + grow, quad_segs=16)
    return LineString([r["a"], r["b"]]).buffer(r["width"] / 2 + grow, quad_segs=8)


class _Space:
    """Foreign copper around routed items, with the clearance the plan requires, to decide
    whether a track can be widened in place or a spoke track drawn."""

    def __init__(self, routed, info, plan):
        from shapely.strtree import STRtree
        from .constraints import _pad_shapes, _poly
        self.routed, self.plan = routed, plan
        self.items = []   # (geometry, net, kind, layer or None, obstacle class or None, uuid)
        for u, r in routed.items():
            self.items.append((_routed_geom(r), r["net"], "routed", r.get("layer"), None, u))
        for pd in info.get("pads") or []:
            _, real = _pad_shapes(pd)
            cls = plan.pin_class.get((pd.get("comp"), pd.get("pin")))
            for l, g in real.items():
                if g is not None and not g.is_empty:
                    self.items.append((g, pd.get("net") or "", "pad", l, cls, None))
        for g in info.get("graphics") or []:
            for l, polys in (g.get("layers") or {}).items():
                for rr in polys:
                    pg = _poly(rr)
                    if pg is not None:
                        self.items.append((pg, g.get("net") or "", "graphic", l, None, None))
        for net, shapes, cls, _ in getattr(plan, "net_graphics", []):  # copper pins of a net
            for l, g in shapes.items():
                self.items.append((g, net, "pad", l, cls, None))
        for ob in plan.obstacles:
            if ob.kind != "keepout":
                continue  # via keepouts do not bind tracks
            lay = None if ob.layer == "signal" else ob.layer
            if ob.why.startswith("rule area") and not isinstance(ob.geom, tuple):
                # rule areas forbid tracks of every net
                self.items.append((ob.geom, "", "keepout", lay, None, None))
                continue
            # the plan's other keepouts (NPTH holes, cut-outs and stray edges, mask openings,
            # copper graphics) at their class's clearance: a spoke track drawn across one was
            # an error of its own (a solder mask bridge, a hole or edge clearance)
            g = ob.geom
            if isinstance(g, tuple):
                if g[0] != "circle":
                    continue
                from shapely.geometry import Point
                g = Point(g[1], g[2]).buffer(g[3] / 2, quad_segs=16)
            self.items.append((g, "", "obstacle", lay, ob.cls, None))
        self.tree = STRtree([it[0] for it in self.items]) if self.items else None

    def _need(self, net, layer, it):
        if it[2] == "keepout":
            return 1e-6
        cls = self.plan.net_class.get(net)
        other = it[1]
        if it[2] == "routed":
            ocls = self.plan.net_class.get(other)
            a, b = sorted((cls, ocls)) if cls and ocls else (cls, ocls)
            v = self.plan.matrix.get((a, b, layer), (0.2, 0.2, 0.2))
            r = self.routed.get(it[5])
            return v[1] if r is not None and r["kind"] == "via" else v[0]
        if it[2] in ("pad", "obstacle") and it[4] in self.plan.obstacle_classes:
            return max(self.plan.obstacle_classes[it[4]].values.get((cls, layer), (0.2, 0.2))[0], 1e-6)
        vals = [oc.values.get((cls, layer)) for n, oc in self.plan.obstacle_classes.items() if n.startswith("kae_cu")]
        return max([v[0] for v in vals if v is not None] or [0.2])

    def fits_geom(self, net, layer, geom):
        """Whether copper `geom` of `net` on `layer` keeps every required clearance."""
        if self.tree is None:
            return True
        for i in self.tree.query(geom.buffer(1.0)):
            it = self.items[int(i)]
            if it[1] == net and net:
                continue
            if it[3] is not None and it[3] != layer:
                continue
            if geom.distance(it[0]) < self._need(net, layer, it) - 1e-6:
                return False
        return True

    def fits(self, uuid, width):
        """Whether routed track `uuid` widened to `width` keeps every required clearance."""
        from shapely.geometry import LineString
        r = self.routed[uuid]
        seg = LineString([r["a"], r["b"]]).buffer(width / 2, quad_segs=8)
        return self.fits_geom(r["net"], r["layer"], seg)


# ----------------------------------------------------------------------------- spokes
def spoke_tracks(pad, zone, layer, need, plan, space, taken=None, skip=()):
    """Up to `need` tracks of the pad's net from inside `pad` straight into the fill of
    `zone` (a zone_fills record) on `layer`, each clear of foreign copper, shortest first,
    in directions at least 45 degrees apart: [{net, layer, a, b, width}]. Fill pieces whose
    key (zone uuid, layer, index) is in `skip` are not targets."""
    import shapely
    from shapely.geometry import LineString, Point
    from shapely.ops import unary_union
    from .constraints import _pad_shapes, _poly
    net = pad.get("net")
    cls = plan.net_class.get(net)
    if not net or cls is None or need <= 0:
        return []
    w = plan.classes[cls].widths.get(layer)
    _, real = _pad_shapes(pad)
    cop = real.get(layer)
    if not w or cop is None or cop.is_empty:
        return []
    start = Point(pad["pos"])
    if not cop.contains(start):
        start = cop.representative_point()
    reach = math.sqrt(cop.area) + (pad.get("thermal_gap") or 0.5) + 2.0
    # only the fill near the pad counts: a ray reaches `reach` from it, and the fill clipped to a
    # box `w` + 1 mm wider shrinks the same inside the ray's range (a board-wide pour shrunk whole
    # for every starved pad took 4 of 5 minutes of a repair round on bastardkb dilemma)
    m = reach + w + 1.0
    win = shapely.box(start.x - m, start.y - m, start.x + m, start.y + m)
    pieces = [g.intersection(win) for i, g in enumerate(_poly(r) for r in (zone.get("layers") or {}).get(layer) or [])
              if g is not None and (zone.get("uuid"), layer, i) not in skip and g.intersects(win)]
    if not pieces:
        return []
    core = unary_union(pieces).buffer(-(w / 2 + 0.01))   # track ends this far inside the fill
    if core.is_empty:
        return []
    base = pad.get("spoke_angle") or 0.0
    cands, seen = [], set()
    for ang in [base + 90 * k for k in range(4)] + [base + 15 * k for k in range(24)]:
        a = round(ang % 360, 3)
        if a in seen:
            continue
        seen.add(a)
        r = math.radians(a)
        ray = LineString([(start.x, start.y), (start.x + reach * math.cos(r), start.y + reach * math.sin(r))])
        inter = ray.intersection(core)
        if inter.is_empty:
            continue
        pts = shapely.get_coordinates(inter)
        d0 = min(ray.project(Point(x, y)) for x, y in pts)
        end = None
        for step in (0.05, 0.02, 0.005):
            p = ray.interpolate(d0 + step)
            if core.contains(p):
                end = p
                break
        if end is None:
            continue
        seg = LineString([(start.x, start.y), (end.x, end.y)])
        if space.fits_geom(net, layer, seg.buffer(w / 2, quad_segs=8)):
            cands.append((seg.length, a, seg))
    taken = [] if taken is None else taken
    out = []
    for _, a, seg in sorted(cands):
        if any(abs((a - b + 180) % 360 - 180) < 45 for b in taken):
            continue
        taken.append(a)
        (ax, ay), (bx, by) = seg.coords
        out.append(dict(net=net, layer=layer, a=[round(ax, 6), round(ay, 6)], b=[round(bx, 6), round(by, 6)],
                        width=w))
        if len(out) >= need:
            break
    return out


# ----------------------------------------------------------------------------- analysis
def needs_fills(report):
    """Whether a DRC report has zone trouble the fill geometry helps with."""
    if any(v.get("type") == "starved_thermal" for v in drc.errors(report)):
        return True
    return any(_is_zone(it.get("description")) for u in report.get("unconnected_items") or []
               for it in u.get("items") or [])


def analyse(report, routed, info=None, plan=None, fills=None, layer_map=None, copper=None):
    """What a DRC report asks for, given `routed` = {uuid: routing item} and, optionally,
    KiCad's zone fills (pcbnew_io.zone_fills), user -> canonical layer names and all routing
    on the board (`copper`, default `routed`; locked pre-routes count as copper, are never
    ripped or widened):
    widen {uuid: mm}, items {uuid} and nets {net} to rip up, spokes [track], connect {net}
    (planes to replace by fill pieces), open {net: set(layers) or None}, thermal {pad uuid}
    (spoke corridors), unattributed [type]."""
    widen, items, nets, opened, other = {}, set(), set(), {}, []
    spokes, connect = [], set()
    pads = {pd.get("uuid"): pd for pd in (info or {}).get("pads", []) if pd.get("uuid")}
    zones = {z["uuid"]: z for z in fills or []}
    lmap = layer_map or {}
    want_corridor = set()
    space = None
    taken = {}

    def get_space():
        nonlocal space
        if space is None:
            space = _Space(copper if copper is not None else routed, info, plan)
        return space

    def try_spokes(pad, zone, layers, need, skip=()):
        if not zones or plan is None or info is None or pad is None or zone is None:
            return False
        for l in layers:
            got = spoke_tracks(pad, zone, l, need, plan, get_space(), taken.setdefault((pad["uuid"], l), []),
                               skip=skip)
            if got:
                spokes.extend(got)
                return len(got) >= need
        return False

    parts = {}

    def own_pieces(pad):
        """Fill pieces already joined to `pad` (its part of the net): a spoke into one of them
        joins nothing."""
        net = pad.get("net")
        if net not in parts:
            cu_ = plan.copper if plan is not None else (info or {}).get("copper", [])
            parts[net] = net_clusters(net, info, copper if copper is not None else routed, fills, cu_)
        for c in parts[net]:
            if pad["uuid"] in c["pads"]:
                return set(c["pieces"]) | set(c["teardrops"])
        return set()

    for v in drc.errors(report):
        its = v.get("items") or []
        if v.get("type") == "starved_thermal":
            pad = next((pads[it["uuid"]] for it in its if it.get("uuid") in pads), None)
            zone = next((zones[it["uuid"]] for it in its if it.get("uuid") in zones), None)
            m = _DRC_LAYER.search(v.get("description") or "")
            layer = lmap.get(m.group(1).strip(), m.group(1).strip()) if m else None
            s = _SPOKES.search(v.get("description") or "")
            need = max(1, int(s.group(1)) - int(s.group(2))) if s else 2
            if pad is not None and not (layer and try_spokes(pad, zone, [layer], need)):
                want_corridor.add(pad["uuid"])
            continue
        ours = [it for it in its if it.get("uuid") in routed]
        if not ours:
            other.append(v.get("type"))
            continue
        if v.get("type") == "track_width":
            m = _MIN.search(v.get("description", ""))
            for it in ours:
                r = routed[it["uuid"]]
                w = float(m.group(1)) + 1e-4 if m else None
                if w and r["kind"] in ("track", "arc") and info is not None and plan is not None:
                    if get_space().fits(it["uuid"], w):
                        widen[it["uuid"]] = w
                        continue
                items.add(it["uuid"])
                nets.add(r["net"])
            continue
        for it in ours:
            items.add(it["uuid"])
            nets.add(routed[it["uuid"]]["net"])
    for u in report.get("unconnected_items") or []:
        its = u.get("items") or []
        uns = {n for it in its for n in _nets_of(it.get("description"))}
        zone_its = [it for it in its if _is_zone(it.get("description"))]
        if not zone_its:
            for n in uns:
                opened[n] = None  # re-route; a plane of the net may have hidden the gap
            continue
        pad_its = [it for it in its if it.get("uuid") in pads]
        if pad_its:  # a pad cut off from its zone: a spoke track joins them
            pad = pads[pad_its[0]["uuid"]]
            zone = next((zones[it["uuid"]] for it in zone_its if it.get("uuid") in zones), None)
            layers = [l for l in pad.get("layers") or [] if zone and l in zone.get("layers", {})]
            if zone and try_spokes(pad, zone, layers, 1, skip=own_pieces(pad)):
                continue
            want_corridor.add(pad["uuid"])
        zl = set()
        for it in zone_its:
            m = _ON_LAYERS.search(it.get("description") or "")
            if m:
                zl.update(lmap.get(x.strip(), x.strip()) for x in m.group(1).split(" and "))
        for n in uns:
            if zones:
                connect.add(n)
            cur = opened.get(n, set())
            opened[n] = None if cur is None else (cur | zl)
    thermal = set()
    if want_corridor and info is not None and plan is not None:
        from shapely.strtree import STRtree
        from .constraints import thermal_corridors
        keys = list(routed)
        tree = STRtree([_routed_geom(routed[k]) for k in keys]) if keys else None
        for geo, layer, pad in thermal_corridors(info, plan, want_corridor):
            thermal.add(pad["uuid"])
            if tree is None:
                continue
            for i in tree.query(geo, predicate="intersects"):
                r = routed[keys[int(i)]]
                if r["net"] != pad["net"] and (r["kind"] == "via" or r.get("layer") == layer):
                    items.add(r["uuid"])
                    nets.add(r["net"])
    return dict(widen=widen, items=items, nets=nets, spokes=spokes, connect=connect, open=opened,
                thermal=thermal, unattributed=other)


# ----------------------------------------------------------------------------- DSN edits
def _drop_planes(tree, nets_layers):
    """Remove the planes of nets (on the given layers; all layers when None) from a DSN."""
    struct = find(tree, "structure")
    n = 0
    for pl in findall(struct, "plane"):
        net = str(pl[1]) if len(pl) > 1 else ""
        if net not in nets_layers:
            continue
        layers = nets_layers[net]
        shape = next((c for c in pl[2:] if isinstance(c, list)), None)
        layer = str(shape[1]) if shape is not None and len(shape) > 1 else ""
        if layers is None or not layers or layer in layers:
            struct.remove(pl)
            n += 1
    return n


def net_clusters(net, info, copper, fills, cu):
    """The parts of `net` that KiCad's connectivity sees as connected: items of the net touch
    where their copper overlaps on a layer (fill pieces, pads with their copper on that
    layer, tracks, vias), and pads and vias join their layers. Returns [dict(pads={uuid},
    routed={uuid}, pieces={(zone uuid, layer, index): polygon}, pad_area=float)], the part
    with the most pads first."""
    from shapely.strtree import STRtree
    from .constraints import _pad_shapes, _poly
    nodes = []   # (node id, layer, geometry); pads and vias keep one id on every layer
    for pd in info.get("pads") or []:
        if pd.get("net") != net or not pd.get("uuid"):
            continue
        _, real = _pad_shapes(pd)
        for l, g in real.items():
            if g is not None and not g.is_empty:
                nodes.append((("pad", pd["uuid"]), l, g))
    for u, r in (copper or {}).items():
        if r.get("net") != net:
            continue
        if r["kind"] == "via":
            g = _routed_geom(r)
            for l in cu:
                nodes.append((("routed", u), l, g))
        elif r.get("layer"):
            nodes.append((("routed", u), r["layer"], _routed_geom(r)))
    for z in fills or []:
        if z.get("net") != net:
            continue
        for l, polys in (z.get("layers") or {}).items():
            for i, rings in enumerate(polys):
                g = _poly(rings)
                if g is not None and not g.is_empty:
                    nodes.append((("piece", (z["uuid"], l, i), bool(z.get("teardrop"))), l, g))
    parent = {}

    def root(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for nid, _, _ in nodes:
        root(nid)
    by_layer = {}
    for nid, l, g in nodes:
        by_layer.setdefault(l, []).append((nid, g))
    for items in by_layer.values():
        tree = STRtree([g for _, g in items])
        for nid, g in items:
            for j in tree.query(g, predicate="intersects"):
                other = items[int(j)][0]
                if other != nid:
                    ra, rb = root(nid), root(other)
                    if ra != rb:
                        parent[ra] = rb
    groups = {}
    for nid, l, g in nodes:
        c = groups.setdefault(root(nid), dict(pads=set(), routed=set(), pieces={}, teardrops=set(), pad_area=0.0))
        if nid[0] == "pad":
            if nid[1] not in c["pads"]:
                c["pad_area"] += g.area
            c["pads"].add(nid[1])
        elif nid[0] == "routed":
            c["routed"].add(nid[1])
        elif nid[2]:
            c["teardrops"].add(nid[1])
        else:
            c["pieces"][nid[1]] = g
    return sorted(groups.values(), key=lambda c: (-len(c["pads"]), -sum(g.area for g in c["pieces"].values())))


def _fill_planes(tree, fills, nets, lname, info, copper, cu):
    """Replace the planes of `nets` in a DSN by the fill pieces of their main part (see
    net_clusters): Freerouting connects a pin to a plane that holds the pin's centre, KiCad
    through the fill's spokes, so each piece is joined with the copper of the pads it
    touches; the remaining holes are windows. Pieces of the other parts are left out, so
    Freerouting sees their pads and routing as not connected to any plane and joins them to
    the net (for a net with a plane over 30% of the board it routes only items that touch no
    plane). Pieces are shrunk by 60 um and simplified within 50 um, inside real copper;
    windows below 1 mm2 are dropped unless they hold a pad of the net (Freerouting splits a
    plane into convex pieces, and many small windows make that slow)."""
    from shapely.ops import unary_union
    from .constraints import _pad_shapes
    struct = find(tree, "structure")
    out = dict(removed=0, added=0, parts=0, left_out=0)
    for pl in findall(struct, "plane"):
        if len(pl) > 1 and str(pl[1]) in nets:
            struct.remove(pl)
            out["removed"] += 1
    pads = {pd["uuid"]: pd for pd in info.get("pads") or [] if pd.get("uuid")}
    from shapely.geometry import Point, Polygon as _Polygon
    for net in sorted(nets):
        centres = [Point(pd["pos"]) for pd in pads.values() if pd.get("net") == net]
        parts = net_clusters(net, info, copper, fills, cu)
        if not parts:
            continue
        main = parts[0]
        out["parts"] += len(parts)
        out["left_out"] += sum(len(c["pieces"]) for c in parts[1:])
        pad_cu = {}
        for u in main["pads"]:
            for l, g in _pad_shapes(pads[u])[1].items():
                if g is not None and not g.is_empty:
                    pad_cu.setdefault(l, []).append(g)
        for (zu, layer, i), g in sorted(main["pieces"].items(), key=lambda kv: (kv[0][1], kv[0][2], kv[0][0])):
            touching = [x for x in pad_cu.get(layer, []) if x.intersects(g)]
            if touching:
                g = unary_union([g, *touching])
            g = g.buffer(-0.06, join_style="mitre").simplify(0.05, preserve_topology=True)
            for pg in getattr(g, "geoms", [g]):
                if pg.is_empty or pg.area < 1e-4 or pg.geom_type != "Polygon":
                    continue
                node = ["plane", Q(net), ["polygon", lname(layer), "0", *translate._ring(pg.exterior.coords)]]
                for h in pg.interiors:
                    hp = _Polygon(h)
                    if len(h.coords) >= 4 and (hp.area >= 1.0 or any(hp.contains(c) for c in centres)):
                        node.append(["window", ["polygon", lname(layer), "0", *translate._ring(h.coords)]])
                struct.append(node)
                out["added"] += 1
    return out


def layer_names(dsn_tree, copper):
    """{DSN (user) layer name: canonical name} and its inverse, from a KiCad DSN."""
    names = [str(l[1]) for l in findall(find(dsn_tree, "structure"), "layer")]
    to_canon = dict(zip(names, copper))
    to_canon.update({c: c for c in copper})
    return to_canon, dict(zip(copper, names))


# ----------------------------------------------------------------------------- loop
# Escalation: rip only the offending items with the rest fixed; then their whole nets; then
# their whole nets with the rest of the routing left to the router. Every round routes in a
# new order (translate.permute), so a round that repeats a level is a new attempt; the loop
# stops after FAILS rounds in a row that were not better (on A+B no fourth round in a row
# ever improved a board).
LEVELS = ("items", "nets", "free")
FAILS = 2


AUTO_ROUNDS = 50   # rounds "auto": a bound that only a run of ever-better rounds reaches


def max_rounds(opts):
    """The repair loop's round bound: opts rounds, or AUTO_ROUNDS for "auto" (the loop then
    stops after FAILS rounds in a row that were not better, or on the time)."""
    r = opts.get("rounds", 5)
    return AUTO_ROUNDS if r == "auto" else int(r)


def round_seed(seed, k):
    """The DSN order of repair round k (never 0, which is KiCad's order)."""
    return (seed or 0) * 7919 + k


def loop(input_path, output_path, wd, plan, info, opts, deadline, log=print):
    """Repair `output_path` in place (see the module docstring). Returns a report."""
    wd = Path(wd)
    output_path = Path(output_path)
    rounds = []
    t_start = time.monotonic()
    thermal = set(opts.get("thermal_pads") or []) if opts.get("thermal_pads") != "all" else set()
    sev = opts.get("severities") or {}
    fixed = set(opts.get("fixed_uuids") or [])   # the input's locked routing
    lmap, lname_map = {}, {}
    if (wd / "kicad.dsn").exists():
        lmap, lname_map = layer_names(specctra.read(wd / "kicad.dsn"), plan.copper)

    # with the last mile on, the repair rounds leave it its time (it needs a refill, a few
    # grid searches, possibly a nested repair and one DRC)
    reserve = float(opts.get("last_mile_reserve_s", 90.0)) if opts.get("last_mile") else 0.0

    def left():
        return deadline - time.monotonic()

    def check(board, d):
        staged = drc.stage_board(board, input_path, d)
        return drc.run(staged, d / "drc.json", timeout=max(10, left() - 5))

    base_ = {}

    def no_worse(s_, ref):
        """No more errors than `ref`, or no more beyond the input's own (input_errors, read only
        when a board with more errors in all would otherwise be kept)."""
        if s_["errors"] <= ref["errors"]:
            return True
        if "v" not in base_:
            base_["v"] = input_errors(input_path, wd, deadline)
        return errors_no_worse(s_, ref, base_["v"])

    try:
        best_rep, best_dir = check(output_path, wd / "repair0" / "drc"), wd / "repair0" / "drc"
    except drc.DrcError as e:
        return dict(rounds=[dict(round=0, drc_error=str(e))], final=None)
    best = drc.summary(best_rep)
    rounds.append(dict(round=0, **best))
    log(f"repair round 0: {best['errors']} errors {best['by_type']}, {best['unconnected']} unconnected")
    level, fails, split_failed = 0, 0, False
    for k in range(1, max_rounds(opts) + 1):
        if best["errors"] == 0 and best["unconnected"] == 0:
            break
        rec = dict(round=k)
        rounds.append(rec)
        if left() - reserve < 45:
            rec["stopped"] = "time"
            break
        rdir = wd / f"repair{k}"
        if rdir.exists():
            shutil.rmtree(rdir)
        rdir.mkdir(parents=True)
        listing = pcbnew_io.edit_routing(output_path, rdir / "listing.kicad_pcb")["routing"]
        copper = {r["uuid"]: r for r in listing}
        routed = {u: r for u, r in copper.items() if not r.get("locked") and u not in fixed}
        fills = None
        if needs_fills(best_rep):
            try:  # refilled with the board's rules: next to its project files
                fills = pcbnew_io.zone_fills(drc.stage_board(output_path, input_path, rdir / "fills"))["zones"]
            except pcbnew_io.PcbnewError as e:
                rec["fills_error"] = str(e)
        a = analyse(best_rep, routed, info, plan, fills=fills, layer_map=lmap, copper=copper)
        new_thermal = a["thermal"] - thermal
        if new_thermal and opts.get("thermal_repair", True):
            thermal |= new_thermal
            pol = getattr(plan, "plane_policy", None)
            plan = constraints.plan(info, input_path, dict(opts, severities=sev, thermal_pads=sorted(thermal)))
            plan.plane_policy = pol
        if not (a["widen"] or a["items"] or a["open"] or a["spokes"] or new_thermal):
            rec["stopped"] = "nothing attributable"
            rec["unattributed"] = sorted(set(a["unattributed"]))
            break
        if k > 1 and opts.get("last_mile") and not any(v.get("type") == "starved_thermal" or any(
                it.get("uuid") in routed for it in v.get("items") or []) for v in drc.errors(best_rep)):
            # no error on router copper, only open connections: the last mile joins them, given the
            # time (heypcb kestrel 1,000 s: 28/25/15 open -> 14/6/0)
            rec["stopped"] = "open connections: last mile"
            break
        use_split = bool(a["connect"] and fills and not split_failed)
        if not a["items"] and not a["widen"] and not use_split and level == 0 and a["open"]:
            level = 2  # only open connections: the router needs room, not the same board again
        mode = LEVELS[level]
        rec.update(level=mode, widen=len(a["widen"]), spokes=len(a["spokes"]), rip_items=len(a["items"]),
                   rip_nets=sorted(a["nets"]), connect=sorted(a["connect"]), open=sorted(a["open"]),
                   thermal=len(new_thermal), unattributed=sorted(set(a["unattributed"])))
        if mode == "items":
            rip = _with_via_tracks(output_path, set(a["items"]), routed)
        else:
            rip = {u for u, r in routed.items() if r["net"] in a["nets"]}
        fixed_board = drc.stage_board(output_path, input_path, rdir / "fixed")
        pcbnew_io.edit_routing(fixed_board, fixed_board, delete=sorted(rip), widths=a["widen"], add=a["spokes"],
                               lock_all=mode != "free")
        cand = rdir / "cand.kicad_pcb"
        if rip or a["open"]:
            dsn_k = rdir / "kicad.dsn"
            pcbnew_io.export_dsn(fixed_board, dsn_k, probes=False)
            tree = specctra.read(dsn_k)
            from .bridge import plane_policy
            plan.plane_policy = plane_policy(opts, free_round_with_open=bool(a["open"]))
            plan.plane_cost = opts.get("plane_cost")
            plan.pad_shapes = opts.get("pad_shapes") or "kicad"
            rec["planes"] = plan.plane_policy
            translate.apply(tree, plan, info)
            translate.permute(tree, round_seed(opts.get("seed"), k))
            if use_split:
                now = {u: r for u, r in copper.items() if u not in rip}   # the board as exported
                now.update({f"spoke{i}": dict(kind="track", **s) for i, s in enumerate(a["spokes"])})
                rec["planes_split"] = _fill_planes(tree, fills, a["connect"], lambda l: lname_map.get(l, l),
                                                   info, now, plan.copper)
            rec["planes_dropped"] = _drop_planes(tree, {n: v for n, v in a["open"].items()
                                                        if not use_split or n not in a["connect"]})
            dsn = rdir / "board.dsn"
            specctra.write(tree, dsn)
            translate.write_rules(plan, dsn)
            budget = max(15.0, min((left() - reserve) * 0.5, left() - reserve - 30))
            from .bridge import router_settings
            grace = opts.get("router_grace", freerouting.GRACE_S)
            run = freerouting.route(dsn, rdir / "board.ses", rdir, passes=opts.get("passes") or 0,
                                    settings=router_settings(plan, opts, repair=True), budget_s=budget,
                                    hard_s=max(budget, min(budget + grace, left() - 15)),
                                    log_path=rdir / "freerouting.log")
            rec["router"] = dict(seconds=run.seconds, state=run.report.get("final_state"),
                                 score=run.report.get("router_score"), killed=run.timed_out)
            if run.ses is None:
                # a failed round like any other: the best board stays, the next round escalates
                rec["kept"] = False
                log(f"repair round {k} ({mode}): the router wrote no session "
                    f"({'killed' if run.timed_out else 'rc=' + str(run.rc)})")
                fails += 1
                level = min(level + 1, len(LEVELS) - 1)
                if use_split:
                    split_failed = True
                if fails >= FAILS:
                    rec["stopped"] = "no improvement"
                    break
                continue
            ses = specctra.read(run.ses)
            translate.fix_session(ses, plan)
            ses_k = rdir / "board_kicad.ses"
            specctra.write(ses, ses_k)
            pcbnew_io.import_ses(fixed_board, ses_k, cand)
            pcbnew_io.edit_routing(cand, cand, unlock_all=True, keep_locked=fixed)
        else:
            pcbnew_io.edit_routing(fixed_board, cand, unlock_all=True, keep_locked=fixed)
        if left() < 10:
            rec["stopped"] = "time"
            break
        try:
            rep = check(cand, rdir / "drc")
        except drc.DrcError as e:
            rec["drc_error"] = str(e)
            break
        s_ = drc.summary(rep)
        rec.update(s_)
        # a round never buys a connection with a DRC error beyond the input's own (no_worse): an
        # error is a defect the last mile cannot repair, an open it can join (olimex crit: a free
        # round traded 2 opens for 1 open + 1 starved thermal, and the board kept it)
        rec["kept"] = _key(s_) > _key(best) and no_worse(s_, best)
        log(f"repair round {k} ({mode}{', spokes ' + str(len(a['spokes'])) if a['spokes'] else ''}"
            f"{', split planes ' + str(len(a['connect'])) if use_split else ''}): "
            f"{s_['errors']} errors {s_['by_type']}, {s_['unconnected']} unconnected "
            f"({'kept' if rec['kept'] else 'discarded'})")
        if rec["kept"]:
            shutil.copy2(cand, output_path)
            best, best_rep, best_dir = s_, rep, rdir / "drc"
            level, fails = 0, 0
        else:
            fails += 1
            if use_split:
                # the router could not join the parts with everything else in place: from now
                # on the net's planes are left out and the rest of the routing may move
                split_failed = True
                level = len(LEVELS) - 1 if not (a["items"] or a["widen"]) else min(level + 1, len(LEVELS) - 1)
            else:
                level = min(level + 1, len(LEVELS) - 1)
            if fails >= FAILS:
                rec["stopped"] = "no improvement"
                break
    else:
        # every round allowed ran without a stop of its own (opts rounds; "auto" lifts the cap)
        if len(rounds) > 1 and not rounds[-1].get("stopped"):
            rounds[-1]["stopped"] = "round cap"
    if opts.get("last_mile"):
        # only a board with errors needs the baseline (one more DRC, minutes on big boards)
        base = input_errors(input_path, wd, deadline) if best["errors"] else {}
        _last_mile(input_path, output_path, wd, plan, info, opts, deadline, rounds, best, best_rep, fixed, log,
                   base=base)
        best = next((r for r in reversed(rounds) if r.get("final")), {}).get("final") or best
    return dict(rounds=rounds, final=best, thermal_pads=len(thermal), seconds=round(time.monotonic() - t_start, 1),
                drc_dir=None if opts.get("last_mile") else str(best_dir))   # the DRC of the board kept


RIP_ERROR_TYPES = ("clearance", "hole_clearance", "track_width", "copper_edge_clearance", "shorting_items",
                   "hole_to_hole", "via_diameter", "annular_width", "solder_mask_bridge", "tracks_crossing",
                   "items_not_allowed")


def _with_via_tracks(board, rip, routed):
    """`rip` plus the router tracks that end on a via in it (same net): a via ripped alone left
    two tracks on different layers with no via between them, an open the next rounds kept
    (heypcb kestrel: 6 of 17 open connections)."""
    from kae.board.kicad_file import load
    model = load(board)
    vias = [v for v in model.vias if v.uuid in rip]
    if not vias:
        return set(rip)
    out = set(rip)
    for t in model.tracks:
        if t.uuid in out or t.uuid not in routed:
            continue
        for v in vias:
            if t.net == v.net and any(math.dist(e, (v.x, v.y)) <= v.size / 2 + 1e-3 for e in (t.start, t.end)):
                out.add(t.uuid)
                break
    return out


def _rip_errors(input_path, board, report, d, fixed, left, info=None, plan=None, base=None):
    """(board, report, summary) with the unlocked routing that every error-level violation
    of `report` names taken out (each error must name some; other errors stay as they are),
    or None when that leaves errors or nothing to take out. A starved thermal names a pad
    and a zone, not the copper that starves it: there the unlocked foreign tracks and vias
    in the pad's spoke corridors (constraints.thermal_corridors) are taken out (paw3395
    crit: a Freerouting +1V8 track wrapped round C3's GND pad)."""
    from . import critical_write as W
    routed = {r["uuid"] for r in W.routing(board) if not r["locked"] and r["uuid"] not in fixed}
    rip = set()
    model = None
    for v in drc.errors(report):
        uu = {it.get("uuid") for it in v.get("items") or []}
        if v.get("type") == "starved_thermal" and info is not None and plan is not None:
            if model is None:
                from shapely.geometry import LineString, Point
                from kae.board.kicad_file import load
                model = load(board)
                geo = [(t.uuid, t.net, t.layer, LineString([t.start, t.end]).buffer(t.width / 2)) for t in model.tracks]
                geo += [(x.uuid, x.net, l, Point(x.x, x.y).buffer(x.size / 2)) for x in model.vias for l in plan.copper]
            pads = {p.get("uuid") for p in info.get("pads") or []} & uu
            from .constraints import thermal_corridors
            hit = set()
            for g, layer, pad in thermal_corridors(info, plan, pads):
                hit |= {u for u, net, l, cg in geo if l == layer and net != pad.get("net") and u in routed
                        and cg.intersects(g)}
            if not hit:
                if base is None:
                    return None
                continue  # no router copper in its corridors: the board's own (base counts it)
            rip |= hit
            continue
        ours = uu & routed
        if not ours and base is not None:
            continue  # names no router copper: the board had it before routing
        if v.get("type") not in RIP_ERROR_TYPES or not ours:
            return None
        rip |= ours
    if not rip:
        return None
    rip = _with_via_tracks(board, rip, routed)
    if Path(d).exists():
        shutil.rmtree(d)
    Path(d).mkdir(parents=True)
    cand = Path(d) / "cand.kicad_pcb"
    W.edit(board, cand, remove=sorted(rip))
    try:
        rep = drc.run(drc.stage_board(cand, input_path, Path(d) / "drc"), Path(d) / "drc" / "drc.json",
                      timeout=max(10, left() - 5))
    except drc.DrcError:
        return None
    s_ = drc.summary(rep)
    if drc.excess(s_, base):
        return None
    return cand, rep, s_


GREEDY_MIN_S = 120.0   # time a greedy last-mile round needs: its joins, the nested reroute and two DRCs
LAST_MILE_MIN_S = 30.0 # time a last-mile round needs (was 60: a short attempt, the restart portfolio's first
                       # waves, then had neither repair nor last mile and ended with time unused)

_BASE = {}


def input_errors(input_path, wd, deadline):
    """{type: count} of the error-level violations the board had before routing (its footprints,
    outline, fixed copper and placement), by KiCad's DRC with its project rules; cached per file.
    Routing cannot remove them, so the last mile and its error rip-out count only errors beyond
    these. {} when the check fails (then every error counts, as before)."""
    p = Path(input_path).resolve()
    key = (str(p), p.stat().st_mtime_ns, p.stat().st_size)
    if key not in _BASE:
        d = Path(wd) / "input_drc"
        try:
            rep = drc.run(drc.stage_board(p, p, d), d / "drc.json",
                          timeout=max(10, min(600, deadline - time.monotonic() - 60)))
            _BASE[key] = drc.summary(rep)["by_type"]
        except (drc.DrcError, OSError):
            return {}
    return _BASE[key]


def errors_no_worse(s_, ref, base):
    """Whether board summary `s_` has no more DRC errors than `ref`, counting with a baseline
    (`base`, input_errors: the errors the board had before routing) only those beyond it. A
    count of a type the input already has more of is the board's own, and it moves with the
    routing: KiCad names one solder mask bridge per aperture and net it meets first, so the
    copper that joins a solder jumper's or a reversible footprint's pads changes the count
    (marksard rhymestone: the last mile closed all 8 open connections, mask bridges 152 -> 153
    of the input's 172, and the board was discarded for that one). The count is not even
    stable: KiCad's DRC of one and the same protocentral pulse-express board gave 39 and 40."""
    if s_["errors"] <= ref["errors"]:
        return True
    return bool(base) and drc.excess(s_, base) <= drc.excess(ref, base)


def _last_mile(input_path, output_path, wd, plan, info, opts, deadline, rounds, best, best_rep, fixed, log,
               base=None):
    """Last-mile rounds (kae.route.lastmile) after the repair rounds: join what is still
    open with the grid router, rip what the new copper must cross, and let a nested repair
    loop route the ripped nets with the new copper fixed. Each round works on the previous
    round's board (a join can open the net it ripped, which the next round joins in turn)
    while that board has no more errors beyond the input's (`base`) than the best one; the
    output is replaced only by a board KiCad's DRC finds better with no more errors, or no more
    beyond the input's (errors_no_worse). It runs on boards with errors beyond the input too:
    a join adds only copper checked exactly, and the result is judged by the same rule
    (adafruit ds2482s: a solder-jumper mask bridge beyond the input's 4 kept it from 7 open
    connections). Appends its records to `rounds`
    (each kept one carries `final`)."""
    from . import lastmile

    def left():
        return deadline - time.monotonic()
    sev = opts.get("severities") or {}
    fixed = set(fixed)
    # critical copper the last mile may rip as a last resort (kae.route.critical passes it with
    # a physics guard; without a guard it stays fixed)
    guard = opts.get("physics_guard")
    soft = set(opts.get("soft_fixed") or ()) if guard is not None else set()
    cur, cur_rep, cur_sum = output_path, best_rep, best
    if drc.excess(cur_sum, base) and left() > 90:
        # errors the router keeps making (bms-c1 crit: a Freerouting track 0.19 mm from a
        # 0.3 mm HV tab, in every round): take out the router's own copper that each error
        # names, so the last mile, whose every segment is checked exactly, routes it instead
        got = _rip_errors(input_path, cur, cur_rep, wd / "lastmile0", fixed, left, info=info, plan=plan, base=base)
        if got is not None:
            cur, cur_rep, cur_sum = got
            rounds.append(dict(round="lm0", level="rip errors", **cur_sum))
            log(f"last mile 0: router copper of {best['errors']} errors taken out: {cur_sum['errors']} errors, "
                f"{cur_sum['unconnected']} unconnected")
    # the first round joins only around everything (no rip-up): those joins cost nothing, and a
    # rip-up round whose ripped nets get no reroute in the time left ends worse than it began
    # (siderakb ergo-snm: 16 open; with rip-up 26 joins, 29 ripped, 18 open and discarded, where
    # the free joins alone gave 10)
    free_first = bool(opts.get("last_mile_free_first", True))
    # no bound on the open connections or rounds: joins stop at their deadline, rounds after FAILS in
    # a row not better (a bound of 40 open skipped transistorfet z280's last mile, 2 minutes unused)
    fails = 0
    for j in range(1, AUTO_ROUNDS + 1):
        rip = not (free_first and j == 1)
        # with time for the nested reroute, a rip-up keeps its joins and the reroute takes the
        # ripped nets (judged by KiCad's DRC like any round); without it, rip-ups are transactions,
        # undone unless they leave fewer open connections on the grid alone (heypcb kestrel:
        # transactions throughout 31/22/14 open, greedy with the reroute 18/2/2; fm4dd i2c24io:
        # a greedy cascade with no reroute after it 5 -> 30 open)
        greedy = left() > GREEDY_MIN_S
        if (drc.excess(cur_sum, base) > drc.excess(best, base) or not cur_sum["unconnected"] or fails >= FAILS
                or left() < LAST_MILE_MIN_S):
            break
        rec = dict(round=f"lm{j}", level="last_mile" if rip else "last_mile free")
        rounds.append(rec)
        ldir = wd / f"lastmile{j}"
        if ldir.exists():
            shutil.rmtree(ldir)
        ldir.mkdir(parents=True)
        try:
            staged = drc.stage_board(cur, input_path, ldir / "base")
            fills = pcbnew_io.zone_fills(staged)["zones"]
            cand = ldir / "cand.kicad_pcb"
            # bounded by time, not by a count of joins (kata0510 rp2040: 39 open connections
            # behind 0.4 mm-pitch escapes took 40 joins, the old cap, in 20 s); the round keeps
            # time for its DRC and the rounds after it
            r = lastmile.close(staged, info, plan, fills, cand, nets=lastmile.open_nets(cur_rep), sev=sev,
                               fixed=fixed, log=log, soft=soft, rip=rip, txn=not greedy, max_joins=None,
                               deadline=time.monotonic() + max(LAST_MILE_MIN_S / 2, 0.5 * (left() - LAST_MILE_MIN_S)))
        except Exception as e:  # noqa: BLE001 - the repaired board stays
            rec["error"] = f"{type(e).__name__}: {e}"
            break
        rec.update(joined=r["joined"], failed=r["failed"], added=len(r["added"]), ripped=len(r["ripped"]),
                   ripped_soft=len(r.get("ripped_soft") or ()))
        soft -= set(r["ripped"])
        if not r["joined"]:
            rec["stopped"] = "nothing joined"
            if not rip:
                continue    # the rip-up rounds work on the same board
            break
        fixed |= set(r["added"])
        sub = {}
        if r["ripped"] and left() > 60:
            # the ripped nets go back to the router around the new, fixed copper
            if (wd / "kicad.dsn").exists():
                shutil.copy2(wd / "kicad.dsn", ldir / "kicad.dsn")
            sub = loop(input_path, cand, ldir, plan, info, dict(opts, last_mile=False, fixed_uuids=sorted(fixed)),
                       deadline, log=log)
            rec["reroute"] = [{k: x.get(k) for k in ("round", "level", "errors", "unconnected", "kept")}
                              for x in sub.get("rounds") or []]
        d = Path(sub.get("drc_dir") or ldir / "drc")   # a reroute ends with its DRC of cand: no second one
        if sub.get("drc_dir"):
            rep = json.loads((d / "drc.json").read_text())
        elif left() < 10:
            rec["stopped"] = "time"
            break
        else:
            try:
                rep = drc.run(drc.stage_board(cand, input_path, d), d / "drc.json", timeout=max(10, left() - 5))
            except drc.DrcError as e:
                rec["drc_error"] = str(e)
                break
        s_ = drc.summary(rep)
        rec.update(s_)
        rec["kept"] = _key(s_) > _key(best) and errors_no_worse(s_, best, base)
        if r.get("ripped_soft") and guard is not None:
            # critical copper was re-laid: the routed physics must hold (the joint loop's rule)
            try:
                ok, why = guard(staged, cur_sum, d / "board.kicad_pcb", s_)
            except Exception as e:  # noqa: BLE001 - no physics verdict, no critical copper change
                ok, why = False, f"physics guard failed: {type(e).__name__}: {e}"
            rec["physics"] = why
            log(f"last mile {j}: critical copper re-laid, {why}")
            if not ok:
                # the critical copper stays: the next round works on the same board, without
                # the soft tier
                rec["kept"] = False
                soft = set()
                continue
        log(f"last mile {j}: joined {r['joined']}, ripped {len(r['ripped'])}: {s_['errors']} errors {s_['by_type']}, "
            f"{s_['unconnected']} unconnected ({'kept' if rec['kept'] else 'not better'})")
        if rec["kept"]:
            shutil.copy2(cand, output_path)
            best, best_rep = s_, rep
            rec["final"] = s_
        fails = 0 if rec["kept"] else fails + rip
        if not errors_no_worse(s_, best, base):
            break
        cur, cur_rep, cur_sum = cand, rep, s_
