# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Rule D pad entries and rail widths for kae's Freerouting fork, written into the DSN.

Freerouting ends every trace at the pin centre (its contact model). The fork
(magnetic-trowel/freerouting, branch kae-pad-entry, setting `router.kae_pin_entries`) can make
the last piece of such a trace follow rule D (docs/research/routing/kae-pad-edge-entry.md): it
reads, per pin and layer, where a trace should arrive (the approach point a, one stub outside
the outline) and where rule D ends it (the end e, on the land's long centre line), and makes
the tail a -> e -> centre a fixed piece that pull-tight tightens up to. Freerouting never
re-derives the rule: every point comes from `pad_entry.centreline_targets` here (one copy of
the rule, routing-stages P3).

The DSN extension is one scope at the end of the `pcb` scope:

    (kae_pin_entries (version 1) [(mode plan)]
      (pin REF PIN (layer L) (centre x y) (frame ux uy w h cx cy) [(radial)]
        (entry KIND (width W) [(neck N)] (approach x y) (end x y)) ...)
      (class_floor CLASS (width W) (layer_rule L (width W)) ...))

in DSN units. Stock Freerouting skips a scope it does not know (ScopeKeyword.readScope), so a
DSN with it routes as before there. `(radial)` marks a round land: any centre-aimed approach
is normal to its outline, so only the approach depth is checked.

Rails (`rails=True`): each power or ground net whose operating current asks for more than
nothing (power_copper.current_need) gets a routing class of its own, a copy of its class with
the width raised to that need on every layer, and the need as the class's width floor
(`class_floor`, the fork's per-class floor under every neck-down). With `gaps`, the class
pairs of a rail class and a victim class get power_copper.victim_gap as their clearance.

What the plan may supply (rf-plan; computed here until it does): `plan.pin_entries`
({(ref, pin): {layer: entries}}), `plan.rail_need` ({net: {layer: mm}}), `plan.victims`
(net names). Settings: env KAE_FR_PIN_ENTRIES (off, on or plan; mode()), KAE_FR_RAILS (on/off),
KAE_FR_RAIL_GAPS (on/off), KAE_OPERATING (operating facts JSON, for the currents).
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path

from shapely.geometry import LineString, Point

from . import pad_entry as PE
from .specctra import Q, find, findall, fmt

SCOPE = "kae_pin_entries"
RELEASE_MM = 3.0         # release points this far outside the frame, one per frame direction
BALL_GRID_MIN = 9        # pad_trim.BALL_GRID_MIN: ball grids are the escape stage's
ON_LAND_TOL = 0.002      # mm: the end-to-centre run may lie this far outside the land


def _on(name, default="off"):
    return (os.environ.get(name) or default).strip().lower() in ("1", "on", "true", "yes")


def mode():
    """KAE_FR_PIN_ENTRIES: "off" (default), "on" (phase 1: the fork re-ends traces at listed pins
    with fixed tails) or "plan" (phase 2: the fork plans each tail before it searches, as routing)."""
    v = (os.environ.get("KAE_FR_PIN_ENTRIES") or "off").strip().lower()
    if v == "plan":
        return "plan"
    return "on" if v in ("1", "on", "true", "yes") else "off"


def enabled():
    return mode() != "off"


# ----------------------------------------------------------------------------- entries
def _releases(pad):
    """Release points around a land: one beyond each side and each corner of its frame."""
    c, u, v, w, h = PE.pad_frame(pad)
    out = []
    for su, sv in ((0, 1), (0, -1), (1, 0), (-1, 0), (1, 1), (1, -1), (-1, 1), (-1, -1)):
        du, dv = su * (w / 2 + RELEASE_MM), sv * (h / 2 + RELEASE_MM)
        out.append((c[0] + du * u[0] + dv * v[0], c[1] + du * u[1] + dv * v[1]))
    return out


def _runs_inside(pad, a, b, w):
    """Whether a piece a -> b of width w lies inside the land (the run from rule D's end to the
    pin centre, which Freerouting needs: its copper must add nothing beside the land)."""
    if math.dist(a, b) < 1e-9:
        return True
    return pad.buffer(ON_LAND_TOL).contains(LineString([a, b]).buffer(w / 2, quad_segs=8))


def is_round(pad):
    c, u, v, w, h = PE.pad_frame(pad)
    return w > 0 and h > 0 and w - h <= PE.SQUARE_TOL * w and pad.area < PE.ROUND_AREA * w * h


def land_entries(pad, centre, width, need=0.0, min_w=0.0):
    """Rule D entries of one land for a track of `width` arriving from any side:
    [dict(kind, a, end, width, neck)], shortest-kind order, deduplicated. Each end is joined to
    `centre` (Freerouting's pin centre) inside the land; a candidate whose end-to-centre run
    would leave the land is dropped. A width no entry fits is necked (pad_entry.neck_width, at
    least `need` and `min_w`), its approach neck_len + w/2 outside the outline. [] when nothing
    fits (the pin keeps Freerouting's own end)."""
    out, seen = [], set()
    for rel in _releases(pad):
        ts = PE.centreline_targets(pad, rel, width)
        neck = None
        if not ts:
            fit, ts = PE.neck_width(pad, rel, width, need, min_w, stub=PE.NECK_LEN + width / 2)
            if fit is None or fit >= width - 1e-9:
                continue
            neck = fit
        for a, end, kind in ts:
            if not _runs_inside(pad, end, centre, neck or width):
                continue
            k = (round(a[0], 4), round(a[1], 4), round(end[0], 4), round(end[1], 4))
            if k in seen:
                continue
            seen.add(k)
            out.append(dict(kind=kind, a=a, end=end, width=width, neck=neck))
    return out


def _ball_grids(info):
    n = {}
    for pd in info.get("pads") or []:
        if pd.get("attr") == "smd" and pd.get("net"):
            from .constraints import _pad_shapes
            _d, real = _pad_shapes(pd)
            g = next((x for x in (real or {}).values() if x is not None and not x.is_empty), None)
            if g is not None and is_round(g):
                k = pd.get("fp_index", pd.get("ref"))
                n[k] = n.get(k, 0) + 1
    return {k for k, v in n.items() if v >= BALL_GRID_MIN}


def _holes(info):
    """Every pad hole of the board as a shapely shape (board mm), with its pad record."""
    out = []
    for pd in info.get("pads") or []:
        h = pd.get("hole")
        if h and h.get("a") and h.get("b") and h.get("width"):
            out.append((LineString([tuple(h["a"]), tuple(h["b"])]).buffer(float(h["width"]) / 2)
                        if tuple(h["a"]) != tuple(h["b"]) else Point(h["a"]).buffer(float(h["width"]) / 2), pd))
    return out


THERMAL_HALO = 0.5        # mm beyond a thermal pad's relief gap kept free of other nets' tails when
                          # neither pad nor zone gives a spoke width


def _keep_clear(info, plan, layer_pads):
    """Per copper layer, [(shape, pad uuid)] a tail of another pad must not touch: the thermal-spoke
    corridors of zone-connected pads (constraints.thermal_corridors, so a tail never takes a spoke's
    room: starved_thermal), and every pad's solder-mask opening (copper grown by its mask expansion
    plus the board's mask-to-copper clearance, so a tail never lies exposed in a neighbour's
    opening: solder_mask_bridge)."""
    from .constraints import thermal_corridors
    out = {}
    try:
        cors = thermal_corridors(info, plan, None, getattr(plan, "severities", None))
    except Exception:          # the corridors need the plan's classes; without them, none
        cors = []
    for geo, layer, pad in cors:
        out.setdefault(layer, []).append((geo, pad.get("uuid"), pad.get("net")))
    # the whole relief ring of every thermal pad of a zone net: the corridors above give way to
    # other pins' escapes, so on fine-pitch parts they leave the spokes unprotected (redbot U2's and
    # dream117er's USB-C GND pads starved under planned tails of their neighbours)
    zones = {}
    for z in info.get("zones") or []:
        if z.get("net") and not z.get("rule_area"):
            for l in z.get("layers") or []:
                zones.setdefault((z["net"], l), z)
    for layer, items in layer_pads.items():
        for pd, g in items:
            z = zones.get((pd.get("net"), layer))
            if z is None or pd.get("zone_connection") in ("full", "none"):
                continue
            gap = pd.get("thermal_gap") or z.get("thermal_gap") or 0.0
            spoke = pd.get("spoke_width") or z.get("spoke_width") or THERMAL_HALO
            out.setdefault(layer, []).append((g.buffer(float(gap) + float(spoke)), pd.get("uuid"), pd.get("net")))
    m2c = float(((info.get("settings") or {}).get("mask_to_copper")) or 0.0)
    cu = list(info.get("copper") or [])
    for layer, items in layer_pads.items():
        side = "F" if cu and layer == cu[0] else ("B" if cu and layer == cu[-1] else None)
        if side is None:
            continue
        for pd, g in items:
            exp = (pd.get("mask") or {}).get(side)
            if exp is None:
                continue
            out.setdefault(layer, []).append((g.buffer(max(float(exp) + m2c, 0.0)), pd.get("uuid"), pd.get("net")))
    return out


def _tail_clear(e, centre, g, w, uuid, net, tree_of):
    """Whether entry e's tail (approach, end, centre at width w, outside its own land g) keeps out of
    the keep-clear shapes of every pad of another net."""
    pts = [e["a"], e["end"]] + ([centre] if math.dist(e["end"], centre) > 1e-9 else [])
    cu = LineString(pts).buffer((e.get("neck") or w) / 2, quad_segs=8).difference(g.buffer(1e-6))
    if cu.is_empty:
        return True
    tree, items = tree_of
    for i in tree.query(cu):
        geo, owner, onet = items[i]
        if owner != uuid and onet != net and geo.intersects(cu):
            return False
    return True


def pin_entries(tree, plan, info, need_of=None):
    """{(ref, pin): (centre, {layer: (pad, entries)})} for every pin routing may end on: a pin with
    a net in a routing class, its copper on a layer, and its DSN centre inside that copper. Pads
    of ball grids are left to the escape stage, and so are lands that hold another pad's hole. Pads
    of a net with a zone on the layer (unless solidly or not connected) keep Freerouting's end: a tail
    would break KiCad's count of their thermal spokes. An entry whose tail would touch another
    pad's thermal-spoke corridor or solder-mask opening is dropped (_keep_clear). `need_of(ref, net)`: the width (mm) the pad's
    current needs (necks are never narrower)."""
    from .constraints import _pad_shapes
    from .translate import dsn_pins
    given = getattr(plan, "pin_entries", None)
    if given:
        return given
    pads = {(p.get("comp"), p.get("pin")): p for p in info.get("pads") or []}
    balls = _ball_grids(info)
    holes = _holes(info)
    import shapely
    layer_pads = {}
    for q in info.get("pads") or []:
        for l, g in ((_pad_shapes(q)[1]) or {}).items():
            if g is not None and not g.is_empty:
                layer_pads.setdefault(l, []).append((q, g))
    clear = _keep_clear(info, plan, layer_pads)
    # nets with a zone on a layer: their pads there join the fill by thermal spokes, and KiCad
    # counts a track as a spoke only as one segment from inside the pad into the fill; a tail ending
    # at its approach point in the thermal gap breaks that (starved_thermal: dream117er's USB-C
    # GND pads, redbot's motor and GND pads), so such pads keep Freerouting's own end
    zoned = {(z.get("net"), l) for z in info.get("zones") or []
             if z.get("net") and not z.get("rule_area") for l in z.get("layers") or []}
    trees = {l: (shapely.STRtree([x[0] for x in v]), v) for l, v in clear.items()}
    dropped = 0
    min_w = float(getattr(plan, "min_width", 0.0) or 0.0)
    out = {}
    for ref, num, _ps, _side, m in dsn_pins(tree):
        pd = pads.get((ref, num))
        if pd is None or not pd.get("net") or pd.get("fp_index", pd.get("ref")) in balls:
            continue
        cls = plan.net_class.get(pd["net"])
        rc = plan.classes.get(cls) if cls else None
        if rc is None:
            continue
        centre = (m[2], m[5])
        _d, real = _pad_shapes(pd)
        need = need_of(pd.get("ref"), pd["net"]) if need_of else 0.0
        per = {}
        for layer in plan.copper:
            g = (real or {}).get(layer)
            if g is None or g.is_empty or g.geom_type != "Polygon" or not g.buffer(1e-6).contains(Point(centre)):
                continue
            if (pd["net"], layer) in zoned and pd.get("zone_connection") not in ("full", "none"):
                continue
            if any(hp is not pd and hg.intersects(g) for hg, hp in holes):
                continue          # a land holding another pad's hole (a switch's NPTH peg): a tail would cut it
            w = rc.widths.get(layer)
            if not w:
                continue
            es = land_entries(g, centre, w, need, min_w)
            if layer in trees:
                kept = [e for e in es if _tail_clear(e, centre, g, w, pd.get("uuid"), pd["net"], trees[layer])]
                dropped += len(es) - len(kept)
                es = kept
            if es:
                per[layer] = (g, es)
        if per:
            out[(ref, num)] = (centre, per)
    if isinstance(getattr(plan, "notes", None), dict):
        plan.notes["fr_entry_dropped"] = dropped
    return out


# ----------------------------------------------------------------------------- rails
def _operating():
    p = os.environ.get("KAE_OPERATING")
    if not p:
        return None
    try:
        return json.loads(Path(p).read_text())
    except (OSError, ValueError):
        return None


def rail_needs(plan, info):
    """({net: mm}, need_of): the width each rail's and ground's operating current asks
    (power_copper.current_need of power_copper.net_currents), and the per-pad need function for
    necks (power_copper.pad_currents). Rails and grounds by kae's name rules (pad_entry), until
    the plan carries the brief's. Empty without operating facts."""
    from . import power_copper as PC
    given = getattr(plan, "rail_need", None)
    op = _operating()
    if given is not None:
        nets = {n: max(v.values()) if isinstance(v, dict) else float(v) for n, v in given.items()}
    elif not op:
        return {}, None
    else:
        names = [n for n in info.get("nets") or {} if n]
        ground = {n for n in names if PE.GND_RE.search(n.rsplit("/", 1)[-1] or "")}
        power = {n for n in names if PE.current_net(n)} - ground
        by_ref = {}
        for pd in info.get("pads") or []:
            if pd.get("ref") and pd.get("net"):
                by_ref.setdefault(pd["ref"], set()).add(pd["net"])
        cur = PC.net_currents(op, by_ref, power, ground)
        nets = {n: PC.current_need(a) for n, a in cur.items() if a > 0}
        pads = [(pd.get("ref"), pd.get("net")) for pd in info.get("pads") or []]
        pc = PC.pad_currents(op, pads, power, ground)

        def need_of(ref, net):
            return PC.current_need(pc.get((ref, net), 0.0))
        return {n: w for n, w in nets.items() if w > 0}, need_of
    return {n: w for n, w in nets.items() if w > 0}, None


def _class_nodes(network):
    return {str(c[1]): c for c in findall(network, "class") if len(c) > 1}


def _set_widths(node, widths_um, lname, cu):
    """Raise a class node's width to widths_um[layer] on every layer: the base (rule ...) holds the
    first layer's, a (layer_rule L (rule ...)) each other layer's that differs (as
    translate._class_rule_nodes writes them). Clearances are kept."""
    def put(rule, w):
        old = find(rule, "width")
        if old is None:
            rule.append(["width", fmt(w)])
        else:
            old[1] = fmt(max(float(old[1]), w))
    rule = find(node, "rule")
    if rule is None:
        rule = ["rule"]
        node.append(rule)
    put(rule, widths_um[cu[0]])
    lrs = {str(lr[1]): lr for lr in findall(node, "layer_rule") if len(lr) > 2}
    for l in cu[1:]:
        lr = lrs.get(lname(l))
        if lr is None:
            if abs(widths_um[l] - widths_um[cu[0]]) < 1e-9:
                continue
            lr = ["layer_rule", lname(l), ["rule"]]
            node.append(lr)
        put(find(lr, "rule"), widths_um[l])


def rail_classes(tree, plan, needs, lname, scale, gaps=False, victims=()):
    """Move each rail net with a need into a class of its own (a copy of its class, width raised
    to the need on every layer), copying the class's class_class rules; with `gaps`, rail-victim
    class pairs get power_copper.victim_gap. Returns ({class: {layer: floor um}}, summary)."""
    from . import power_copper as PC
    network = find(tree, "network")
    if network is None or not needs:
        return {}, {}
    classes = _class_nodes(network)
    cu = plan.copper
    floors, made = {}, []
    pairs = [c for c in findall(network, "class_class")]
    for k, net in enumerate(sorted(needs)):
        cls = plan.net_class.get(net)
        node = classes.get(cls)
        if node is None:
            continue
        need_um = needs[net] * scale
        rc = plan.classes[cls]
        widths = {l: max(rc.widths[l] * scale, need_um) for l in cu}
        name = f"{cls}__rail{k}"
        new = [c if not isinstance(c, list) else json.loads(json.dumps(c)) for c in node]
        new[1] = name
        qn = [i for i, c in enumerate(new) if i > 1 and not isinstance(c, list) and str(c) == net]
        if not qn:
            continue
        new = [new[0], name, Q(net)] + [c for c in new[2:] if isinstance(c, list)]
        node[:] = [c for c in node if isinstance(c, list) or str(c) != net]
        _set_widths(new, widths, lname, cu)
        network.insert(network.index(node) + 1, new)
        for pc in pairs:
            cl = find(pc, "classes")
            if cl is None or cls not in [str(x) for x in cl[1:]]:
                continue
            cp = json.loads(json.dumps(pc))
            cpc = find(cp, "classes")
            cpc[1:] = [name if str(x) == cls else x for x in cpc[1:]]
            network.append(cp)
        # the rail against its old class: the class's own clearance (its rule's), as before
        own = [json.loads(json.dumps(c)) for c in node if isinstance(c, list) and c and c[0] in ("rule", "layer_rule")]
        for r in own:
            for sub in [r] + [x for x in r if isinstance(x, list) and x and x[0] == "rule"]:
                sub[:] = [x for x in sub if not (isinstance(x, list) and x and x[0] == "width")]
        network.append(["class_class", ["classes", cls, name], *own])
        floors[name] = {l: need_um for l in cu}
        made.append(dict(net=net, cls=name, need_mm=round(needs[net], 4)))
    if gaps and victims and made:
        h = min(float(getattr(plan, "dielectric_mm", 0.2) or 0.2), 1.0)
        gap = PC.victim_gap(h) * scale
        vcls = sorted({plan.net_class[v] for v in victims if v in plan.net_class})
        for m in made:
            for vc in vcls:
                network.append(["class_class", ["classes", m["cls"], vc], ["rule", ["clearance", fmt(gap)]]])
    return floors, dict(rail_classes=made)


# ----------------------------------------------------------------------------- the DSN scope
def scope_node(entries, scale, lname, floors=None, planned=False):
    """The kae_pin_entries node: pins in (ref, pin) order, layers in plan order, entries in
    land_entries order."""
    def xy(p):
        return [fmt(p[0] * scale), fmt(-p[1] * scale)]
    node = [SCOPE, ["version", "1"]] + ([["mode", "plan"]] if planned else [])
    for (ref, num) in sorted(entries, key=lambda k: (str(k[0]), str(k[1]))):
        centre, per = entries[(ref, num)]
        for layer, (g, es) in per.items():
            c, u, v, w, h = PE.pad_frame(g)
            pin = ["pin", Q(ref), Q(num), ["layer", lname(layer)], ["centre", *xy(centre)],
                   ["frame", fmt(u[0]), fmt(-u[1]), fmt(w * scale), fmt(h * scale), *xy(c)]]
            if is_round(g):
                pin.append(["radial"])
            for e in es:
                ent = ["entry", e["kind"], ["width", fmt(e["width"] * scale)]]
                if e.get("neck"):
                    ent.append(["neck", fmt(e["neck"] * scale)])
                ent += [["approach", *xy(e["a"])], ["end", *xy(e["end"])]]
                pin.append(ent)
            node.append(pin)
    for cls in sorted(floors or {}):
        f = floors[cls]
        first = next(iter(f))
        cf = ["class_floor", cls, ["width", fmt(f[first])]]
        for l, w in f.items():
            if l != first and abs(w - f[first]) > 1e-9:
                cf.append(["layer_rule", lname(l), ["width", fmt(w)]])
        node.append(cf)
    return node


def apply(tree, plan, info, lname, entries=None, rails=None, gaps=None):
    """Write the entry table (and, with `rails`, the rail classes and floors) into a DSN `tree`
    already rewritten by translate.apply. Settings default to the environment (module doc).
    Returns a summary."""
    from .specctra import unit_scale
    entries = enabled() if entries is None else entries
    rails = _on("KAE_FR_RAILS") if rails is None else rails
    gaps = _on("KAE_FR_RAIL_GAPS") if gaps is None else gaps
    if not entries and not rails:
        return {}
    for c in list(tree):
        if isinstance(c, list) and c and c[0] == SCOPE:
            tree.remove(c)
    scale = unit_scale(tree)
    needs, need_of = rail_needs(plan, info) if rails else ({}, None)
    floors, summary = rail_classes(tree, plan, needs, lname, scale, gaps, getattr(plan, "victims", ()) or ()) \
        if rails else ({}, {})
    table = pin_entries(tree, plan, info, need_of) if entries else {}
    tree.append(scope_node(table, scale, lname, floors, planned=entries and mode() == "plan"))
    n_ent = sum(len(es) for _c, per in table.values() for _g, es in per.values())
    summary.update(pins=len(table), pin_layers=sum(len(per) for _c, per in table.values()), entries=n_ent,
                   necked=sum(1 for _c, per in table.values() for _g, es in per.values() for e in es if e.get("neck")),
                   class_floors=len(floors))
    return summary


def read_scope(tree):
    """The kae_pin_entries scope of a DSN tree as {(ref, pin, layer): dict(centre, frame, radial,
    entries=[dict(kind, width, neck, approach, end)])} in DSN units, plus {class: floor node}
    (the reader the round-trip tests use; the fork has its own)."""
    node = find(tree, SCOPE)
    pins, floors = {}, {}
    if node is None:
        return pins, floors
    for p in findall(node, "pin"):
        lay = str(find(p, "layer")[1])
        rec = dict(centre=tuple(float(x) for x in find(p, "centre")[1:3]),
                   frame=tuple(float(x) for x in find(p, "frame")[1:7]),
                   radial=find(p, "radial") is not None, entries=[])
        for e in findall(p, "entry"):
            nk = find(e, "neck")
            rec["entries"].append(dict(kind=str(e[1]), width=float(find(e, "width")[1]),
                                       neck=float(nk[1]) if nk is not None else None,
                                       approach=tuple(float(x) for x in find(e, "approach")[1:3]),
                                       end=tuple(float(x) for x in find(e, "end")[1:3])))
        pins[(str(p[1]), str(p[2]), lay)] = rec
    for f in findall(node, "class_floor"):
        floors[str(f[1])] = f
    return pins, floors
