# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Write a routing plan (kae.route.constraints) into KiCad's Specctra DSN, and prepare
Freerouting's session for KiCad's import.

DSN changes (KiCad's export is the starting point; its pads, placement, nets, planes and
fixed wiring are kept):

- net classes: KiCad's (netclass width and clearance only) are replaced by the plan's
  routing classes, each with its width per layer (layer_rule), its via padstack and its
  clearance per layer; every pair of classes gets an explicit class_class rule;
- obstacle classes: one net-less class per distinct requirement vector (pins, holes, edges,
  copper graphics, zero), with class_class rules against every routing class;
- pins: each component placement names a clearance class for each of its pins;
- obstacles: KiCad's keepouts (outline holes, rule areas, NPTH holes) are replaced by the
  plan's, held in one virtual component placed at the origin (a component's keepouts can
  name a clearance class; board-level keepouts are read before the classes exist); copper
  graphics that carry a net are pins of that component, listed in their net;
- vias: one padstack per routing class at its real size, named Via[0-n]_<D>:<d>_um in
  whole micrometres (Freerouting drops decimal fractions from via names, KiCad reads the
  drill from the name); the class rule's typed clearances (wire_via, via_via) carry what
  KiCad asks of vias only (hole clearance, hole-to-hole);
- layers: when every copper layer is a "power" layer they become signal layers
  (Freerouting refuses a board without one and 2.5.0 hangs).

Session changes before KiCad imports it: the placement block is removed (KiCad would move
footprints and fails on renamed references), bare net names are quoted (`ADD|SUB` fails
the whole import), and via shapes get their real diameters back.
"""
import math
import random

from shapely.geometry import MultiPolygon, Polygon

from . import specctra as S
from .constraints import via_name
from .specctra import Q, find, findall, fmt

OBSTACLE_IMAGE = "kae_obstacles"
OBSTACLE_REF = "KAE_OBSTACLES"


def _um(mm):
    return fmt(mm * 1000.0)


def _xy(x, y):
    """Board mm (y down) -> DSN um (y up), as KiCad's exporter maps points."""
    return [fmt(x * 1000.0), fmt(-y * 1000.0)]


def _ring(coords):
    pts = list(coords)
    if len(pts) > 1 and pts[0] == pts[-1]:
        pts = pts[:-1]
    out = []
    for x, y in pts:
        out += _xy(x, y)
    if pts:
        out += _xy(*pts[0])
    return out


def _polygons(geom, tol=0.0005):
    """Simple polygons (with holes) of a shapely geometry, grown by `tol` and simplified by
    it, so the result never lies inside the original."""
    if geom.is_empty:
        return []
    g = geom.buffer(tol, quad_segs=4, join_style="mitre", mitre_limit=2.0).simplify(tol, preserve_topology=True)
    if isinstance(g, Polygon):
        return [g] if not g.is_empty else []
    if isinstance(g, MultiPolygon):
        return [x for x in g.geoms if not x.is_empty]
    return [x for x in getattr(g, "geoms", []) if isinstance(x, Polygon) and not x.is_empty]


def _shape_nodes(ob, lname, copper):
    """DSN shapes of one obstacle: [(main shape node, [window nodes])], one per copper layer
    it covers (Freerouting applies a "signal" shape to signal layers only, and treats a power
    layer without a plane as a routing layer)."""
    layers = copper if ob.layer == "signal" else [ob.layer]
    out = []
    if isinstance(ob.geom, tuple) and ob.geom[0] == "circle":
        _, x, y, d = ob.geom
        return [(["circle", lname(l), _um(d), *_xy(x, y)], []) for l in layers]
    polys = _polygons(ob.geom)
    for l in layers:
        for pg in polys:
            main = ["polygon", lname(l), "0", *_ring(pg.exterior.coords)]
            windows = [["window", ["polygon", lname(l), "0", *_ring(h.coords)]] for h in pg.interiors]
            out.append((main, windows))
    return out


def _class_rule_nodes(widths, clearances, copper, lname=lambda l: l):
    """(rule ...) and (layer_rule ...) nodes. widths: layer -> mm or None; clearances: layer ->
    (track-track, track-via, via-via) mm or None. Typed clearances give the class's vias a
    clearance class of their own in Freerouting."""
    def rule(l, base=None):
        r = ["rule"]
        if widths and (base is None or abs(widths[l] - widths[base]) > 1e-9):
            r.append(["width", _um(widths[l])])
        if clearances:
            c = clearances[l]
            cb = clearances[base] if base is not None else None
            for v, kind, i in ((c[0], None, 0), (c[1], "wire_via", 1), (c[2], "via_via", 2)):
                if v is None or (cb is not None and cb[i] is not None and abs(v - cb[i]) < 1e-9):
                    continue
                r.append(["clearance", _um(v)] + ([["type", kind]] if kind else []))
        return r
    base_l = copper[0]
    out = [rule(base_l)]
    for l in copper[1:]:
        lr = rule(l, base_l)
        if len(lr) > 1:
            out.append(["layer_rule", lname(l), lr])
    return out


def apply(tree, plan, info):
    """Rewrite a parsed KiCad DSN `tree` in place according to `plan`. Returns a summary."""
    cu = plan.copper
    struct = find(tree, "structure")
    lib = find(tree, "library")
    placement = find(tree, "placement")
    network = find(tree, "network")
    if struct is None or lib is None or network is None:
        raise ValueError("not a KiCad DSN (structure, library or network missing)")
    if placement is None:
        placement = ["placement"]
        tree.insert(tree.index(lib), placement)
    summary = {}

    # ---- layers: KiCad names DSN layers by their user names (In1.Cu may be "GND"), in
    # stack order; the plan uses canonical names
    layers = findall(struct, "layer")
    dsn_names = [str(l[1]) for l in layers]
    if len(dsn_names) != len(cu):
        raise ValueError(f"DSN has {len(dsn_names)} copper layers, the board {len(cu)}")
    names_of = dict(zip(cu, dsn_names))

    def lname(l):
        return names_of.get(l, l)
    summary["layer_names"] = {c: d for c, d in names_of.items() if c != d}
    # all-power boards get signal layers
    kinds = [find(l, "type") for l in layers]
    if kinds and all(k is not None and len(k) > 1 and k[1] == "power" for k in kinds):
        for k in kinds:
            k[1] = "signal"
        summary["power_layers_unblocked"] = len(kinds)

    # ---- structure: KiCad's keepouts, via list and global rule are replaced
    removed = 0
    for c in list(struct):
        if isinstance(c, list) and c and c[0] in ("keepout", "via_keepout", "wire_keepout", "via", "rule"):
            struct.remove(c)
            removed += c[0] != "via" and c[0] != "rule"
    summary["kicad_keepouts_removed"] = removed
    vias = {n: via_name(rc, len(cu)) for n, rc in plan.classes.items()}
    struct.append(["via", *[Q(v) for v in sorted(set(vias.values()))]])
    # Freerouting's default class holds no nets (every net is in a plan class); its rule
    # only has to be valid
    dflt = next(iter(plan.classes.values()))
    struct.append(["rule", ["width", _um(dflt.widths[cu[0]])], ["clearance", _um(0.1)]])

    # ---- library: image keepouts out, KiCad's vias out, ours in, the obstacle image in
    for img in findall(lib, "image"):
        for c in list(img):
            if isinstance(c, list) and c and c[0] in ("keepout", "via_keepout", "wire_keepout"):
                img.remove(c)
    kicad_vias = {}   # KiCad's via padstacks: name -> copper diameter (DSN units)
    for ps in findall(lib, "padstack"):
        if len(ps) > 1 and str(ps[1]).startswith("Via["):
            circ = next((c for sh in findall(ps, "shape") for c in findall(sh, "circle")), None)
            if circ is not None and len(circ) > 2:
                kicad_vias[str(ps[1])] = float(circ[2])
            lib.remove(ps)
    for n, rc in sorted(plan.classes.items()):
        name = vias[n]
        if any(len(ps) > 1 and ps[1] == name for ps in findall(lib, "padstack")):
            continue
        dia = _um(rc.via[0])
        lib.append(["padstack", Q(name), *[["shape", ["circle", lname(l), dia, "0", "0"]] for l in cu],
                    ["attach", "off"]])
    # fixed vias in the wiring (locked routing) keep KiCad's padstack (sizes in whole um)
    wiring = find(tree, "wiring")
    have = {str(ps[1]) for ps in findall(lib, "padstack") if len(ps) > 1}
    for wv in findall(wiring or [], "via"):
        if len(wv) < 2 or str(wv[1]) not in kicad_vias:
            continue
        real_um = kicad_vias[str(wv[1])]
        drill = str(wv[1]).split(":")[1].split("_")[0] if ":" in str(wv[1]) else "0"
        name = f"Via[0-{len(cu) - 1}]_{round(real_um)}:{round(float(drill or 0))}_um"
        if name not in have:
            lib.append(["padstack", Q(name), *[["shape", ["circle", lname(l), fmt(real_um), "0", "0"]] for l in cu],
                        ["attach", "off"]])
            have.add(name)
        wv[1] = Q(name)
    image = ["image", OBSTACLE_IMAGE]
    place = ["place", OBSTACLE_REF, "0", "0", "front", "0"]
    n_ko = 0
    for ob in plan.obstacles:
        for main, windows in _shape_nodes(ob, lname, cu):
            name = f"ko{n_ko}"
            n_ko += 1
            image.append([ob.kind, name, main, *windows])
            place.append([ob.kind, name, ["clearance_class", ob.cls]])
    # copper graphics of a net: pins of the obstacle component in that net
    dsn_nets = {str(n[1]): n for n in findall(network, "net") if len(n) > 1}
    n_gp = 0
    for i, (net, shapes, cls, _why) in enumerate(plan.net_graphics):
        if net not in dsn_nets:
            continue
        shp = []
        for l, geo in shapes.items():
            polys = _polygons(geo)
            if polys:
                pg = max(polys, key=lambda g: g.area)
                shp.append(["shape", ["polygon", lname(l), "0", *_ring(pg.exterior.coords)]])
        if not shp:
            continue
        ps_name, pin_id = f"kae_gfx{i}", f"g{i}"
        lib.append(["padstack", Q(ps_name), *shp, ["attach", "off"]])
        image.append(["pin", Q(ps_name), pin_id, "0", "0"])
        place.append(["pin", pin_id, ["clearance_class", cls]])
        pins = find(dsn_nets[net], "pins")
        if pins is None:
            pins = ["pins"]
            dsn_nets[net].append(pins)
        pins.append(f"{OBSTACLE_REF}-{pin_id}")
        n_gp += 1
    if n_ko or n_gp:
        lib.append(image)
        placement.append(["component", OBSTACLE_IMAGE, place])
    summary["obstacles"] = n_ko
    summary["net_graphics"] = n_gp

    # ---- placement: a clearance class per pin
    pins_set = 0
    for comp in findall(placement, "component"):
        for pl in findall(comp, "place"):
            if len(pl) < 2 or pl[1] == OBSTACLE_REF:
                continue
            ref = str(pl[1])
            for c in list(pl):
                if isinstance(c, list) and c and c[0] == "pin":
                    pl.remove(c)
            for (cref, pin), cls in plan.pin_class.items():
                if cref == ref:
                    pl.append(["pin", Q(pin), ["clearance_class", cls]])
                    pins_set += 1
    summary["pins_classed"] = pins_set

    # ---- network: classes and the clearance matrix
    for c in list(network):
        if isinstance(c, list) and c and c[0] in ("class", "class_class"):
            network.remove(c)
    known = set(info["nets"])
    for n, rc in sorted(plan.classes.items()):
        # a class's own rule must hold typed clearances, so that its vias get their own
        # clearance class before Freerouting creates the class's via infos
        d0 = plan.matrix.get((n, n, cu[0]))
        diag = {l: plan.matrix.get((n, n, l)) or d0 or (0.2, 0.2, 0.2) for l in cu}
        nets = [Q(x) for x in rc.nets if x in known]
        network.append(["class", n, *nets, ["circuit", ["use_via", Q(vias[n])]],
                        *_class_rule_nodes(rc.widths, diag, cu, lname)])
    for oname, oc in sorted(plan.obstacle_classes.items()):
        vals = [max(v) for v in oc.values.values()]
        network.append(["class", oname, ["rule", ["clearance", _um(max(vals) if vals else 0.0)]]])
    names = sorted(plan.classes)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            vals = {l: plan.matrix.get((a, b, l)) for l in cu}
            if any(v is None for v in vals.values()):
                continue
            network.append(["class_class", ["classes", a, b], *_class_rule_nodes(None, vals, cu, lname)])
    for oname, oc in sorted(plan.obstacle_classes.items()):
        for n in names:
            vals = {l: oc.values.get((n, l)) for l in cu}
            have = [v for v in vals.values() if v is not None]
            if not have:
                continue
            fill = (max(v[0] for v in have), max(v[1] for v in have))
            vals = {l: ((v if v is not None else fill)[0], (v if v is not None else fill)[1], None)
                    for l, v in vals.items()}
            network.append(["class_class", ["classes", oname, n], *_class_rule_nodes(None, vals, cu, lname)])
    summary["classes"] = len(plan.classes)
    summary["obstacle_classes"] = len(plan.obstacle_classes)
    return summary


def permute(tree, seed):
    """Shuffle the order of components, of their placements and of nets in a DSN `tree`
    (in place, reproducibly from `seed`; 0 leaves it as it is). Returns whether it changed.

    Freerouting 2.5.0 is deterministic and routes the open items in the order the DSN
    created them (pins in placement order; net numbers in network order break ties), so an
    attempt with another order is another, equally valid attempt."""
    if not seed:
        return False
    rnd = random.Random(seed)

    def shuffle_children(node, head):
        idx = [i for i, c in enumerate(node) if isinstance(c, list) and c and c[0] == head]
        kids = [node[i] for i in idx]
        rnd.shuffle(kids)
        for i, c in zip(idx, kids):
            node[i] = c
        return kids

    placement = find(tree, "placement")
    if placement is not None:
        for comp in shuffle_children(placement, "component"):
            shuffle_children(comp, "place")
    network = find(tree, "network")
    if network is not None:
        shuffle_children(network, "net")
    return True


# ----------------------------------------------------------------------------- session
def fix_session(ses_tree, plan):
    """Prepare Freerouting's session for KiCad: drop the placement, quote net names, restore
    real via diameters. Returns a summary."""
    out = dict(placement_stripped=False, nets_quoted=0, vias_restored=0)
    pl = find(ses_tree, "placement")
    if pl is not None:
        S.remove(ses_tree, pl)
        out["placement_stripped"] = True
    routes = find(ses_tree, "routes")
    if routes is None:
        return out
    scale = S.unit_scale(routes)  # units per mm
    real = {via_name(rc, len(plan.copper)): rc.via[0] for rc in plan.classes.values()}
    lib = find(routes, "library_out")
    for ps in findall(lib or [], "padstack"):
        name = str(ps[1]) if len(ps) > 1 else ""
        if name in real:
            for shp in findall(ps, "shape"):
                for circ in findall(shp, "circle"):
                    if len(circ) > 2:
                        circ[2] = fmt(real[name] * scale)
                        out["vias_restored"] += 1
    net_out = find(routes, "network_out")
    for net in findall(net_out or [], "net"):
        if len(net) > 1 and not isinstance(net[1], Q):
            net[1] = Q(net[1])
            out["nets_quoted"] += 1
    return out
