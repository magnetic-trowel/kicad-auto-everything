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
  graphics that carry a net, and the fills of kae.route.critical's zones, are pins of that
  component (centred inside their copper), listed in their net;
- vias: one padstack per routing class at its real size, named Via[0-n]_<D>:<d>_um in
  whole micrometres (Freerouting drops decimal fractions from via names, KiCad reads the
  drill from the name); the class rule's typed clearances (wire_via, via_via) carry what
  KiCad asks of vias only (hole clearance, hole-to-hole);
- layers: when every copper layer is a "power" layer they become signal layers
  (Freerouting refuses a board without one and 2.5.0 hangs). Inner plane layers (one net's
  zones cover >= PLANE_SHARE of the board, as the PLANE-PERF critic reads it; KiCad marks
  most of them "signal") are kept for the return currents by plan.plane_policy:
  "cost" (soft) leaves them signal layers and gives Freerouting per-layer trace costs in a
  `board.rules` file beside the DSN (autoroute_settings layer_rule, which Freerouting loads
  with the DSN and keeps over its own defaults): a trace there costs PLANE_COST times one on
  a routing layer, so it goes there only when nothing shorter exists; "power" (hard) writes
  them `(type power)`, which Freerouting never routes on (and which also turns off its own
  detection of plane nets on the remaining layers); "signal" leaves KiCad's types.

- wiring: KiCad writes DSN coordinates with %.6g, so at x or y >= 100 mm half a micrometre
  is lost: a locked track ending exactly on a pad centre such as 137.2875 mm is written
  137288 um while the pin centre (placement 136250 + pin offset 1037.5) stays 137287.5.
  Freerouting joins a wire to a pin or a via only at its centre and to another wire only at
  a corner, so it read such pre-routes as floating, spent its passes on them and left other
  connections open (kae.route.critical's decap stubs, human pre-routes). Every wiring point
  within SNAP_TOL_UM of a same-net pin centre is moved onto that centre, and a point within
  it of another same-net wiring corner onto that corner (snap_wiring).

Session changes before KiCad imports it: the placement block is removed (KiCad would move
footprints and fails on renamed references), bare net names are quoted (`ADD|SUB` fails
the whole import), via shapes get their real diameters back, and wiring points the DSN
snap moved (Freerouting returns the unfixed ones it keeps) get their KiCad coordinates back.
Fixed wiring is never returned: KiCad's import keeps locked copper byte for byte.
"""
import math
import random

from shapely.geometry import MultiPolygon, Polygon

from . import specctra as S
from .constraints import via_name
from .specctra import Q, find, findall, fmt

PLANE_SHARE = 0.30         # an inner layer is a plane when one net's zones cover this share of the board
PLANE_COST = 4.0           # trace cost on a plane layer, in units of a routing layer's (plane_policy "cost")
SNAP_TOL_UM = 1.5          # > the %.6g rounding (0.5 um per coordinate at >= 100 mm) on both axes

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


def dsn_pin_centres(tree):
    """{net: [(x, y)]}: every component pin's centre as Freerouting reads it from the DSN
    (DSN units): the placement plus the image's pin offset, a back-side image mirrored in x
    before the rotation (checked against KiCad's pad positions to 0.002 um)."""
    lib = find(tree, "library")
    placement = find(tree, "placement")
    network = find(tree, "network")
    if lib is None or placement is None or network is None:
        return {}
    imgs = {}
    for im in findall(lib, "image"):
        pins = []
        for p in findall(im, "pin"):
            rest = [c for c in p[2:] if not isinstance(c, list)]
            if len(rest) >= 3:
                pins.append((str(rest[0]), float(rest[1]), float(rest[2])))
        imgs[str(im[1])] = pins
    where = {}
    for comp in findall(placement, "component"):
        pins = imgs.get(str(comp[1])) or []
        for pl in findall(comp, "place"):
            if len(pl) < 6:
                continue
            ref, x, y, side, rot = str(pl[1]), float(pl[2]), float(pl[3]), str(pl[4]), float(pl[5])
            a = math.radians(rot)
            ca, sa = math.cos(a), math.sin(a)
            for num, px, py in pins:
                if side == "back":
                    px = -px
                where[f"{ref}-{num}"] = (x + px * ca - py * sa, y + px * sa + py * ca)
    out = {}
    for net in findall(network, "net"):
        if len(net) < 2:
            continue
        pts = [where[str(t)] for pn in findall(net, "pins") for t in pn[1:] if str(t) in where]
        if pts:
            out[str(net[1])] = pts
    return out


def _affine(*ms):
    """Compose 2x3 affine matrices (a, b, c, d, e, f: x' = ax + by + c, y' = dx + ey + f),
    the last one applied first."""
    out = (1.0, 0.0, 0.0, 0.0, 1.0, 0.0)
    for m in ms:
        a, b, c, d, e, f = out
        A, B, C, D, E, F = m
        out = (a * A + b * D, a * B + b * E, a * C + b * F + c, d * A + e * D, d * B + e * E, d * C + e * F + f)
    return out


def _rot(deg):
    r = math.radians(deg)
    return (math.cos(r), -math.sin(r), 0.0, math.sin(r), math.cos(r), 0.0)


def _inverse(m):
    a, b, c, d, e, f = m
    det = a * e - b * d
    return (e / det, -b / det, (b * f - c * e) / det, -d / det, a / det, (c * d - a * f) / det)


def _apply_affine(geom, m):
    from shapely import affinity
    a, b, c, d, e, f = m
    return affinity.affine_transform(geom, [a, b, d, e, c, f])


def dsn_pins(tree):
    """[(ref, pin id, padstack name, side, matrix)] for every component pin of a DSN, the
    matrix taking padstack coordinates (DSN units) to board mm (y down): the pin's rotation
    and offset, a back-side image mirrored in x, the placement's rotation and position
    (Freerouting's order, as dsn_pin_centres)."""
    lib = find(tree, "library")
    placement = find(tree, "placement")
    if lib is None or placement is None:
        return []
    scale = S.unit_scale(tree)
    imgs = {}
    for im in findall(lib, "image"):
        pins = []
        for p in findall(im, "pin"):
            rest = [c for c in p[2:] if not isinstance(c, list)]
            rot = next((float(c[1]) for c in p[2:] if isinstance(c, list) and c and c[0] == "rotate"
                        and len(c) > 1), 0.0)
            if len(rest) >= 3:
                pins.append((str(p[1]), str(rest[0]), float(rest[1]), float(rest[2]), rot))
        imgs[str(im[1])] = pins
    out = []
    to_mm = (1.0 / scale, 0.0, 0.0, 0.0, -1.0 / scale, 0.0)
    for comp in findall(placement, "component"):
        for pl in findall(comp, "place"):
            if len(pl) < 6:
                continue
            ref, x, y, side, rot = str(pl[1]), float(pl[2]), float(pl[3]), str(pl[4]), float(pl[5])
            mirror = (-1.0, 0.0, 0.0, 0.0, 1.0, 0.0) if side == "back" else (1.0, 0.0, 0.0, 0.0, 1.0, 0.0)
            for ps, num, px, py, prot in imgs.get(str(comp[1])) or []:
                m = _affine(to_mm, (1.0, 0.0, x, 0.0, 1.0, y), _rot(rot), mirror, (1.0, 0.0, px, 0.0, 1.0, py),
                            _rot(prot))
                out.append((ref, num, ps, side, m))
    return out


def _pad_copper(pad, layer):
    from shapely.ops import unary_union
    rings = pad.get("poly") if "poly" in pad else (pad.get("poly_by_layer") or {}).get(layer)
    gs = []
    for r in rings or []:
        if r and len(r[0]) >= 3:
            g = Polygon(r[0], [h for h in r[1:] if len(h) >= 3])
            gs.append(g if g.is_valid else g.buffer(0))
    return unary_union(gs) if gs else None


def circumscribe_pins(tree, info, tol_mm=0.0005):
    """Make every pin's polygon contain the pad's copper (in place). KiCad's DSN export
    writes roundrect, chamfered and custom pads as polygons whose arc chords lie inside the
    true outline (oasis: 3.9 um at a 0.25 mm corner radius, 10 um on its custom pads), so
    Freerouting's clearance from them falls short of KiCad's by that much. Each such
    padstack polygon (its copper reaching more than `tol_mm` beyond it) is replaced by the
    pad's copper as KiCad's export gives it (ERROR_OUTSIDE: contains the true outline, at
    most max_error beyond it), taken back into the padstack's frame and grown by 0.2 um
    against coordinate rounding. A replacement is kept only when it contains the copper of
    every pin that uses the padstack. Circles, paths (ovals) and rectangles are exact and
    stay. Returns a summary."""
    from .constraints import _excess
    lib = find(tree, "library")
    struct = find(tree, "structure")
    if lib is None or struct is None or not info:
        return {}
    dsn_l = [str(l[1]) for l in findall(struct, "layer")]
    cu = list(info.get("copper") or [])
    if len(cu) != len(dsn_l):
        return {}
    pads = {(p.get("comp"), p.get("pin")): p for p in info.get("pads") or []}
    stacks = {str(ps[1]): ps for ps in findall(lib, "padstack") if len(ps) > 1}
    scale = S.unit_scale(tree)
    uses = {}      # (padstack, shape index) -> [(deficit mm, copper in padstack frame, copper on board, matrix)]
    for ref, num, psn, side, m in dsn_pins(tree):
        pad, ps = pads.get((ref, num)), stacks.get(psn)
        if pad is None or ps is None:
            continue
        for k, sh in enumerate(findall(ps, "shape")):
            node = sh[1] if len(sh) > 1 and isinstance(sh[1], list) else None
            if node is None or node[0] != "polygon" or len(node) < 9 or str(node[1]) not in dsn_l:
                continue
            try:
                if float(node[2]) != 0.0:
                    continue
                v = [float(t) for t in node[3:] if not isinstance(t, list)]
            except ValueError:
                continue
            g = Polygon(list(zip(v[0::2], v[1::2])))
            if not g.is_valid:
                g = g.buffer(0)
            i = dsn_l.index(str(node[1]))
            if side == "back":
                i = len(cu) - 1 - i
            real = _pad_copper(pad, cu[i])
            if real is None or real.is_empty:
                continue
            e = _excess(real, _apply_affine(g, m))
            uses.setdefault((psn, k), []).append((e, _apply_affine(real, _inverse(m)), real, m))
    out = dict(pin_shapes_circumscribed=0, pin_shapes_kept=0, pin_deficit_um_max=0.0)
    grow = 0.0002 * scale
    for (psn, k), us in uses.items():
        worst = max(u[0] for u in us)
        out["pin_deficit_um_max"] = max(out["pin_deficit_um_max"], round(worst * 1000.0, 2))
        if worst <= tol_mm:
            continue
        cand = us[0][1]
        if not isinstance(cand, Polygon) or cand.is_empty:
            out["pin_shapes_kept"] += 1
            continue
        cand = Polygon(cand.exterior).buffer(grow, quad_segs=2, join_style="mitre", mitre_limit=2.0)
        cand = cand.simplify(grow, preserve_topology=True)
        if not all(_apply_affine(cand, u[3]).buffer(1e-6).contains(u[2]) for u in us):
            out["pin_shapes_kept"] += 1
            continue
        shapes = findall(stacks[psn], "shape")
        node = shapes[k][1]
        pts = list(cand.exterior.coords)
        if not Polygon(pts).exterior.is_ccw:
            pts = pts[::-1]
        flat = []
        for x, y in pts[:-1] + [pts[0]]:
            flat += [fmt(x), fmt(y)]
        shapes[k][1] = ["polygon", node[1], "0", *flat]
        out["pin_shapes_circumscribed"] += 1
    return out


def snap_wiring(tree, pads=None, tol_um=SNAP_TOL_UM):
    """Move the DSN wiring's points (wire path points, via centres) that lie within `tol_um`
    of a same-net pin centre exactly onto it, and the rest within `tol_um` of another
    same-net wiring point onto that point (see the module docstring). pads: KiCad's pad
    records (pcbnew_io.export_dsn info) for the map back. Returns (summary, snaps) with
    snaps {net: [(x, y snapped, x, y of the KiCad pad), mm in the DSN frame]} for
    fix_session."""
    wiring = find(tree, "wiring")
    summary = dict(points=0, to_pins=0, to_corners=0)
    snaps = {}
    if wiring is None:
        return summary, snaps
    scale = S.unit_scale(tree)                      # DSN units per mm
    tol = tol_um * 1e-3 * scale
    eps = 1e-6 * scale
    centres = dsn_pin_centres(tree)
    exact = {}
    for pd in pads or []:
        if pd.get("net") and pd.get("pos"):
            exact.setdefault(pd["net"], []).append((pd["pos"][0] * scale, -pd["pos"][1] * scale))
    refs = []                                       # (net, node, index of x)
    for w in findall(wiring, "wire"):
        path, net = find(w, "path"), find(w, "net")
        if path is None or net is None:
            continue
        for i in range(3, len(path) - 1, 2):
            refs.append((str(net[1]), path, i))
    for v in findall(wiring, "via"):
        net = find(v, "net")
        if net is not None and len(v) > 3:
            refs.append((str(net[1]), v, 2))
    cgrid = {}
    for net, pts in centres.items():
        for c in pts:
            cgrid.setdefault((net, math.floor(c[0] / tol), math.floor(c[1] / tol)), []).append(c)

    def near(grid, net, x, y):
        gx, gy = math.floor(x / tol), math.floor(y / tol)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                yield from grid.get((net, gx + dx, gy + dy), ())
    rest = []                                       # (net, x, y, node, i, is_via)
    for netname, node, i in refs:
        try:
            x, y = float(node[i]), float(node[i + 1])
        except (TypeError, ValueError):
            continue
        summary["points"] += 1
        tgt, best = None, tol
        for c in near(cgrid, netname, x, y):
            d = math.dist(c, (x, y))
            if d <= best:
                best, tgt = d, c
        if tgt is None:
            rest.append((netname, x, y, node, i, node[0] == "via"))
            continue
        if best > eps:
            sx, sy = round(tgt[0], 4), round(tgt[1], 4)
            node[i], node[i + 1] = fmt(sx), fmt(sy)
            summary["to_pins"] += 1
            true = min(exact.get(netname, ()), key=lambda c: math.dist(c, tgt), default=None)
            if true is not None and math.dist(true, tgt) <= tol:
                snaps.setdefault(netname, []).append((sx / scale, sy / scale, true[0] / scale, true[1] / scale))
    # near-coincident corners: each cluster onto its most frequent point (a via centre first)
    pgrid = {}
    for k, r in enumerate(rest):
        pgrid.setdefault((r[0], math.floor(r[1] / tol), math.floor(r[2] / tol)), []).append(k)
    done = set()
    for k, (netname, x0, y0, _, _, _) in enumerate(rest):
        if k in done:
            continue
        grp = [j for j in near(pgrid, netname, x0, y0)
               if j not in done and math.dist(rest[j][1:3], (x0, y0)) <= tol]
        done.update(grp)
        if len({rest[j][1:3] for j in grp}) < 2:
            continue
        count = {}
        for j in grp:
            q = rest[j][1:3]
            count[q] = count.get(q, 0) + 1 + (10 if rest[j][5] else 0)
        rx, ry = max(count, key=count.get)
        for j in grp:
            _, x, y, node, i, _ = rest[j]
            if (x, y) != (rx, ry):
                node[i], node[i + 1] = fmt(rx), fmt(ry)
                summary["to_corners"] += 1
    return summary, snaps


def plane_layers(info, share=PLANE_SHARE):
    """{inner copper layer: net} of the layers where one net's zones (not rule areas, not
    teardrops) cover at least `share` of the board outline."""
    from shapely.ops import unary_union
    cu = list(info.get("copper") or [])
    inner = set(cu[1:-1])
    if not inner:
        return {}

    def polys(rings_list):
        out = []
        for rings in rings_list or []:
            if rings and len(rings[0]) >= 3:
                pg = Polygon(rings[0], [h for h in rings[1:] if len(h) >= 3])
                out.append(pg if pg.is_valid else pg.buffer(0))
        return out
    board = unary_union(polys(info.get("outline")))
    area = board.area
    if area <= 0:
        return {}
    by = {}
    for z in info.get("zones") or []:
        if z.get("rule_area") or z.get("teardrop") or not z.get("net"):
            continue
        for l in z.get("layers") or []:
            if l in inner:
                by.setdefault((l, z["net"]), []).extend(polys(z.get("rings")))
    out = {}
    for (l, net), ps in by.items():
        a = unary_union(ps).intersection(board).area
        if a >= share * area and a > out.get(l, (None, 0.0))[1]:
            out[l] = (net, a)
    return {l: v[0] for l, v in out.items()}


def layer_rules(names, is_plane, is_signal, k=PLANE_COST):
    """A Specctra rules file (text) whose autoroute_settings give every layer its trace costs:
    1 per unit length in the preferred direction and 2 against it, outer layers 0.2 per
    signal layer more when there are more than two (Freerouting's own defaults), and plane
    layers k times that. None when no layer is a plane."""
    if not any(is_plane):
        return None
    n = len(names)
    sig = sum(1 for x in is_signal if x)
    out = ["(rules PCB board", "  (autoroute_settings"]
    for i, (name, pl) in enumerate(zip(names, is_plane)):
        base = 1.0 + (0.2 * sig if sig > 2 and i in (0, n - 1) else 0.0)
        c = base * (k if pl else 1.0)
        out.append(f"    (layer_rule {atom_name(name)} (preferred_direction_trace_costs {fmt(c)})"
                   f" (against_preferred_direction_trace_costs {fmt(2.0 * c)}))")
    out += ["  )", ")"]
    return "\n".join(out) + "\n"


def atom_name(name):
    return S.atom(name)


def write_rules(plan, dsn_path):
    """The plan's layer_rules beside the DSN as `<stem>.rules` (Freerouting loads it with the
    DSN); a stale one is removed."""
    from pathlib import Path
    r = Path(dsn_path).with_suffix(".rules")
    text = getattr(plan, "layer_rules", None)
    if text:
        r.write_text(text)
    elif r.exists():
        r.unlink()


def mark_plane_layers(layers, cu, info):
    """Write `(type power)` on the DSN `layers` (structure layer nodes, in `cu` order) that
    are inner planes (plane_layers). Returns the layers changed."""
    planes = plane_layers(info)
    made = []
    for c, l in zip(cu, layers):
        k = find(l, "type")
        if c in planes and k is not None and len(k) > 1 and k[1] != "power":
            k[1] = "power"
            made.append(c)
    return made


def apply(tree, plan, info):
    """Rewrite a parsed KiCad DSN `tree` in place according to `plan`. Returns a summary."""
    cu = plan.copper
    # wiring onto the pin centres first, while the placement holds only KiCad's parts
    snap_sum, snaps = snap_wiring(tree, (info or {}).get("pads"))
    plan.wire_snaps = snaps
    struct = find(tree, "structure")
    lib = find(tree, "library")
    placement = find(tree, "placement")
    network = find(tree, "network")
    if struct is None or lib is None or network is None:
        raise ValueError("not a KiCad DSN (structure, library or network missing)")
    if placement is None:
        placement = ["placement"]
        tree.insert(tree.index(lib), placement)
    summary = {"wiring_snapped": snap_sum}

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
    elif getattr(plan, "plane_policy", "signal") == "power":
        made = mark_plane_layers(layers, cu, info)
        if made:
            summary["plane_layers_power"] = made
    strict = set(getattr(plan, "strict_planes", None) or ())
    if strict and getattr(plan, "plane_policy", "signal") == "cost":
        made = []
        for c, l in zip(cu, layers):
            k = find(l, "type")
            if c in strict and k is not None and len(k) > 1 and k[1] != "power":
                k[1] = "power"
                made.append(c)
        if made:
            summary["plane_layers_power"] = made
    plan.layer_rules = None
    if getattr(plan, "plane_policy", "signal") == "cost":
        plan.layer_rules = layer_rules(dsn_names, [c in plane_layers(info) for c in cu],
                                       [str((find(l, "type") or [None, "signal"])[1]) == "signal" for l in layers],
                                       getattr(plan, "plane_cost", None) or PLANE_COST)
        if plan.layer_rules:
            summary["plane_layers_costed"] = [c for c in cu if c in plane_layers(info)]

    # ---- pins: polygons that contain the pad's copper (plan.pad_shapes "outside")
    if getattr(plan, "pad_shapes", "kicad") == "outside":
        summary["pin_shapes"] = circumscribe_pins(tree, info)

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
        # Freerouting joins a trace to a pin only at the pin's centre: the centre lies inside
        # the copper, the shapes are relative to it
        largest = {l: max(_polygons(geo), key=lambda g: g.area, default=None) for l, geo in shapes.items()}
        largest = {l: g for l, g in largest.items() if g is not None}
        if not largest:
            continue
        c = max(largest.values(), key=lambda g: g.area).representative_point()
        shp = [["shape", ["polygon", lname(l), "0", *_ring((x - c.x, y - c.y) for x, y in pg.exterior.coords)]]
               for l, pg in largest.items()]
        ps_name, pin_id = f"kae_gfx{i}", f"g{i}"
        lib.append(["padstack", Q(ps_name), *shp, ["attach", "off"]])
        image.append(["pin", Q(ps_name), pin_id, *_xy(c.x, c.y)])
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
    snaps = getattr(plan, "wire_snaps", None) or {}
    if snaps:
        out["points_restored"] = _unsnap(net_out, snaps, scale)
    return out


def _unsnap(net_out, snaps, scale):
    """Wiring points of the session that sit where snap_wiring moved a DSN point (a pre-route
    Freerouting kept, or a new wire ending on that pin centre) get the KiCad coordinates
    back. snaps in mm (DSN frame); the session in its own `scale` (units per mm)."""
    if not snaps or net_out is None:
        return 0
    k = scale
    tol = 0.05 * 1e-3 * scale                       # 0.05 um
    n = 0
    for net in findall(net_out, "net"):
        pts = snaps.get(str(net[1])) if len(net) > 1 else None
        if not pts:
            continue
        nodes = [(p, i) for w in findall(net, "wire") for p in findall(w, "path") for i in range(3, len(p) - 1, 2)]
        nodes += [(v, 2) for v in findall(net, "via") if len(v) > 3]
        for node, i in nodes:
            try:
                x, y = float(node[i]), float(node[i + 1])
            except (TypeError, ValueError):
                continue
            for sx, sy, tx, ty in pts:
                if abs(x - sx * k) <= tol and abs(y - sy * k) <= tol:
                    node[i], node[i + 1] = fmt(tx * k), fmt(ty * k)
                    n += 1
                    break
    return n


def fill_planes(info, fills):
    """{inner copper layer: (net, share)}: the net whose refilled zone copper (pcbnew_io.zone_fills
    records) covers the most of the board outline on each inner layer, and that share."""
    from shapely.ops import unary_union
    cu = list(info.get("copper") or [])
    inner = set(cu[1:-1])
    if not inner:
        return {}

    def polys(rings_list):
        out = []
        for rings in rings_list or []:
            if rings and len(rings[0]) >= 3:
                pg = Polygon(rings[0], [h for h in rings[1:] if len(h) >= 3])
                out.append(pg if pg.is_valid else pg.buffer(0))
        return out
    board = unary_union(polys(info.get("outline")))
    if board.area <= 0:
        return {}
    by = {}
    for z in fills or []:
        if z.get("teardrop") or not z.get("net"):
            continue
        for l, rl in (z.get("layers") or {}).items():
            if l in inner:
                by.setdefault((l, z["net"]), []).extend(polys(rl))
    out = {}
    for (l, net), ps in by.items():
        a = unary_union(ps).intersection(board).area / board.area
        if a > out.get(l, (None, 0.0))[1]:
            out[l] = (net, a)
    return out
