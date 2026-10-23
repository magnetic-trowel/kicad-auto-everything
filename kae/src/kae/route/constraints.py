# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Effective routing constraints: what KiCad's DRC will require of every track and via the
router may draw, per net, copper layer and partner, reduced to what Freerouting can hold.

Freerouting's model is a set of net classes (a track width per layer, a via padstack, a
clearance matrix between clearance classes per layer) plus obstacles. KiCad's is a rule
engine evaluated per pair of items. `plan(info, board_path)` maps one onto the other:

- **Routing classes.** Nets that KiCad treats alike (same effective netclass, diff-pair
  membership, same width and via limits, same answers to net-specific custom rules) share
  a class. Width per layer = the netclass width (KiCad's "opt") clamped into [min, max] of
  the track-width constraint on that layer; via = netclass size raised to the via-diameter,
  hole-size and annular-ring minimums, in whole micrometres.
- **Vias.** Freerouting holds separate clearances for a class's vias when the class rule
  has typed clearances (wire_via, via_via): KiCad's hole-to-hole and hole clearances, which
  bind only vias, go there, so vias are not over-constrained against tracks or tracks
  against vias.
- **Clearance matrix.** For every pair of classes and layer: track-track, track-via and
  via-via clearances, each KiCad's requirement (rules.strictest) with hole clearance taken
  through the via's annular ring and hole-to-hole through both drills.
- **Pin classes.** Every pad gets a clearance class: its copper clearance to each routing
  class on each layer, raised by hole clearance through its annular ring, by solder-mask
  aperture clearance on outer layers (expansion + mask-to-copper), and by how far its real
  copper on a layer extends beyond the shape the DSN carries (per-layer padstacks, custom
  pads with several outlines).
- **Obstacles.** NPTH holes, board cut-outs and stray Edge.Cuts/Margin shapes, copper
  graphics and texts, rule areas and thermal-spoke corridors become keepouts, each in an
  obstacle class carrying KiCad's requirement (rule areas and corridors: zero). A copper
  graphic that carries a net becomes a pin of that net instead (net_graphics), so the
  router connects its net to it and keeps the other nets away. So does the fill of every
  zone named "kae-crit:..." (opts["crit_zones"], pours that kae.route.critical emitted): a
  hard obstacle for other nets at the zone's clearance, while the zone stays a plane of
  its own net; other zones are planes only, which other nets may cross (KiCad's refill
  flows around them).

All lengths mm. Requirements are rounded up to 0.1 um (the DSN resolution).
"""
import math
from dataclasses import dataclass, field
from pathlib import Path

import shapely
from shapely.geometry import LineString, MultiPolygon, Point, Polygon, box
from shapely.ops import unary_union

from . import rules as R

RES = 1e-4          # mm: DSN resolution (0.1 um)
EPS_SHORT = 0.001   # mm: smallest clearance kept against foreign copper (overlap is a short)


def up(v, q=RES):
    """Round up to a multiple of q (with a little slack for float noise)."""
    return math.ceil(v / q - 1e-6) * q


# ----------------------------------------------------------------------------- items
def net_item(info, net, kind, layer=None, width=None):
    """A routed track or via of `net` as a rules item."""
    nc = info["nets"].get(net, {}).get("netclass", "Default")
    it = dict(type="Track" if kind == "track" else "Via", net=net, netclass=nc,
              constituents=nc.split(","), copper=True, connected=True, layer=layer)
    if kind == "track":
        it.update(width=width, layers=[layer] if layer else [])
    else:
        it.update(via_type="Through", drilled=True, plated=True, layers=list(info["copper"]))
    return it


def pad_item(info, pad):
    net = pad.get("net") or ""
    nc = info["nets"].get(net, {}).get("netclass", "Default") if net else "Default"
    return dict(type="Pad", net=net, netclass=nc, constituents=nc.split(","),
                copper=bool(pad.get("layers")), connected=True,
                pad_type={"pth": "Through-hole", "smd": "SMD", "conn": "Edge connector",
                          "npth": "NPTH, mechanical"}.get(pad.get("attr"), "SMD"),
                fab_property=pad.get("fab") or "None", ref=pad.get("ref"), lib=pad.get("lib"),
                drilled=bool(pad.get("drilled")), override=pad.get("override"),
                local=pad.get("local_clearance"), layers=pad.get("layers") or [])


def graphic_item(info, g):
    net = g.get("net") or ""
    connected = g.get("cls") == "PCB_SHAPE"
    nc = info["nets"].get(net, {}).get("netclass", "Default") if net else "Default"
    it = dict(type="Graphic" if connected else "Text", copper=True, connected=connected,
              layers=list(g.get("layers") or []), ref=None if not g.get("owner") else g["owner"])
    if connected:
        it.update(net=net, netclass=nc, constituents=nc.split(","))
    return it


EDGE_ITEM = dict(type="Graphic", copper=False, connected=False, layer="Edge.Cuts", layers=["Edge.Cuts"])


# ----------------------------------------------------------------------------- data
@dataclass
class RoutingClass:
    name: str
    nets: list
    netclass: str
    widths: dict            # layer -> mm
    via: tuple              # (diameter, drill) mm, the real via
    rep: str = ""           # representative net
    rep2: str = ""          # a second net of the class (for same-class pairs), or ""


@dataclass
class ObstacleClass:
    name: str
    values: dict            # (routing class name, layer) -> clearance mm


@dataclass
class Obstacle:
    kind: str               # 'keepout' | 'via_keepout'
    layer: str              # copper layer name or 'signal'
    geom: object            # shapely Polygon / MultiPolygon, or ('circle', x, y, d)
    cls: str                # obstacle class name
    why: str = ""


@dataclass
class Plan:
    copper: list
    classes: dict = field(default_factory=dict)        # name -> RoutingClass
    net_class: dict = field(default_factory=dict)      # net -> routing class name
    matrix: dict = field(default_factory=dict)         # (R, S, layer) -> mm (R <= S by name)
    pin_class: dict = field(default_factory=dict)      # (comp, pin) -> obstacle class name
    obstacle_classes: dict = field(default_factory=dict)
    obstacles: list = field(default_factory=list)
    net_graphics: list = field(default_factory=list)   # (net, {layer: polygon}, obstacle class, why)
    edge_clearance: float = 0.0                        # for Freerouting's board outline
    neck_width: float | None = None
    notes: dict = field(default_factory=dict)
    rule_board: object = None


# ----------------------------------------------------------------------------- helpers
def rule_board(info, board_path):
    dru = Path(board_path).with_suffix(".kicad_dru")
    return R.build(info["copper"], info["settings"], info["netclasses"], set(info["nets"]),
                   str(dru) if dru.exists() else None)


def _strict_min(rb, ctype, a, b, layer):
    c = R.strictest(rb, ctype, a, b, layer)
    return c.min or 0.0


def _severity_ignored(severities, key):
    return severities.get(key) in ("ignore", "warning", "info", "exclusion")


def _width_choice(probe_w, strict, nc_width):
    """Width for a net on a layer: the opt (netclass) width clamped into [min, max]."""
    mn = max(v for v in ((probe_w or [None])[0], strict.min) if v is not None) if (probe_w or strict.min) else 0.0
    mx_c = [v for v in (((probe_w or [None, None, None])[2]), strict.max) if v is not None]
    mx = min(mx_c) if mx_c else None
    opt = (probe_w or [None, None])[1]
    if opt is None:
        opt = strict.opt if strict.opt is not None else nc_width
    w = opt if opt is not None else mn
    w = max(w, mn or 0.0)
    if mx is not None and w > mx:
        w = max(mx, mn or 0.0)
    return up(w), mn or 0.0, mx


def _via_choice(info, rb, net):
    """(diameter, drill, ring) for through vias of `net`, whole micrometres."""
    pr = info["probes"].get(net, {}).get("via", {})
    vi = net_item(info, net, "via")
    dia = R.strictest(rb, "via_diameter", vi)
    drl = R.strictest(rb, "hole_size", vi)
    ann = max([R.strictest(rb, "annular_width", vi, None, l).min or 0.0 for l in info["copper"]] +
              [v for v in (pr.get("annulus") or {}).values() if v is not None] + [0.0])
    pd, pdr = pr.get("diameter") or [None, None, None], pr.get("drill") or [None, None, None]
    d_min = max(v for v in (pdr[0], drl.min, 0.0) if v is not None)
    d_opt = pdr[1] if pdr[1] is not None else drl.opt
    d = max(d_opt or d_min, d_min)
    d_max = min([v for v in (pdr[2], drl.max) if v is not None] or [None]) if (pdr[2] or drl.max) else None
    if d_max is not None and d > d_max:
        d = max(d_max, d_min)
    D_min = max(v for v in (pd[0], dia.min, 0.0) if v is not None)
    D_opt = pd[1] if pd[1] is not None else dia.opt
    D = max(D_opt or D_min, D_min, d + 2 * ann)
    D_max = min([v for v in (pd[2], dia.max) if v is not None] or [None]) if (pd[2] or dia.max) else None
    if D_max is not None and D > D_max:
        D = max(D_max, D_min, d + 2 * ann)
    d = math.ceil(d * 1000 - 1e-6) / 1000
    D = math.ceil(D * 1000 - 1e-6) / 1000
    return D, d, (D - d) / 2


# ----------------------------------------------------------------------------- planning
def plan(info, board_path, opts=None):
    """The routing plan for a board (see the module docstring)."""
    opts = dict(opts or {})
    rb = rule_board(info, board_path)
    cu = list(info["copper"])
    p = Plan(copper=cu, rule_board=rb)
    sev = opts.get("severities") or {}
    s = info["settings"]

    # ---- per-net limits and signatures
    nets = [n for n in info["nets"] if n]
    custom_net_rules = [r for r in rb.rules if not r.implicit and r.text and
                        any(k in r.text.lower() for k in ("net", "indiffpair", "fromto", "memberof"))]
    sig_of, per_net = {}, {}
    for net in nets:
        pr = info["probes"].get(net, {})
        nc_name = info["nets"][net]["netclass"]
        nc = info["netclasses"].get(nc_name, {})
        widths, wmin = {}, {}
        for l in cu:
            ti = net_item(info, net, "track", l, width=None)
            strict = R.strictest(rb, "track_width", ti, None, l)
            w, mn, mx = _width_choice((pr.get("track") or {}).get(l, {}).get("width"), strict, nc.get("track_width"))
            widths[l], wmin[l] = w, mn
        D, d, ring = _via_choice(info, rb, net)
        dp = R.diff_base(net) is not None and R.complement_net(net) in info["nets"]
        rsig = []
        for r in custom_net_rules:
            for kind in ("track", "via"):
                it = net_item(info, net, kind, cu[0], widths[cu[0]])
                try:
                    rsig.append(R.truth(R.ev(r.condition, R.Ctx(it, None, cu[0], "", False, rb)))
                                if r.condition is not None else True)
                except KeyError:
                    rsig.append(None)
        sig = (nc_name, dp, tuple(widths[l] for l in cu), (D, d), tuple(rsig))
        sig_of[net] = sig
        per_net[net] = dict(widths=widths, wmin=wmin, via=(D, d), ring=ring)
    groups = {}
    for net in nets:
        groups.setdefault(sig_of[net], []).append(net)
    # class names: kae_<netclass>[_k]; never Freerouting's default class (see translate)
    order = sorted(groups.items(), key=lambda kv: (kv[0][0] != "Default", -len(kv[1]), kv[0][0]))
    used = set()
    for i, (sig, members) in enumerate(order):
        name = _class_name(sig[0], used)
        used.add(name)
        members = sorted(members)
        w = per_net[members[0]]["widths"]
        rc = RoutingClass(name=name, nets=members, netclass=sig[0], widths=dict(w), via=per_net[members[0]]["via"],
                          rep=members[0], rep2=members[1] if len(members) > 1 else "")
        p.classes[name] = rc
        for n in members:
            p.net_class[n] = name
    if not p.classes:  # a board with no nets still needs a class
        nc = info["netclasses"].get("Default", {})
        w = up(max(nc.get("track_width") or 0.0, s.get("min_track", 0.0)) or 0.2)
        p.classes["kae_Default"] = RoutingClass("kae_Default", [], "Default", {l: w for l in cu},
                                                  (max(nc.get("via_diameter") or 0.6, s.get("min_via", 0.0)),
                                                   max(nc.get("via_drill") or 0.3, s.get("min_drill", 0.0))))
    # Freerouting retries a connection it failed at min(class width, neck width) along its
    # whole length (one value for every class): the neck must be legal for every class (at
    # least the largest minimum) and is no narrower than the narrowest class width, so a class
    # wider than its pads (a 0.64 mm USB class into a 0.5 mm pitch connector) still connects
    widths_all = [w for rc in p.classes.values() for w in rc.widths.values() if w]
    neck = max([v for pn in per_net.values() for v in pn["wmin"].values()] + [min(widths_all or [0.0])])
    if neck > 0 and any(w > neck + 1e-9 for w in widths_all):
        p.neck_width = up(neck)

    # ---- class pair requirements: tracks and vias of R vs S, per layer
    names = sorted(p.classes)
    req = {}   # (R, S, layer) -> dict(ww, wv, vw, vv)
    for i, a in enumerate(names):
        for b in names[i:]:
            ra, rbc = p.classes[a], p.classes[b]
            na = ra.rep
            nb = rbc.rep if a != b else ra.rep2
            if not na or not nb:
                continue
            for l in cu:
                req[(a, b, l)] = pair_clearances(info, rb, na, nb, l, ra.widths[l], rbc.widths[l], ra.via, rbc.via)
    # same-net via pairs: hole-to-hole between two vias of one net (Freerouting has no
    # clearance within a net; recorded so the repair loop knows what to look for)
    for n in names:
        rc = p.classes[n]
        if rc.rep:
            va = net_item(info, rc.rep, "via")
            h = _strict_min(rb, "hole_to_hole", va, dict(va), None)
            p.notes.setdefault("same_net_via_pitch", {})[n] = up(h + rc.via[1])
    for (a, b, l), r in req.items():
        p.matrix[(a, b, l)] = (up(max(r["ww"], EPS_SHORT)), up(max(r["wv"], r["vw"], EPS_SHORT)),
                               up(max(r["vv"], EPS_SHORT)))

    # ---- pins
    pin_req = {}
    for pad in info["pads"]:
        if not pad.get("pin") or not pad.get("layers"):
            continue
        vec = _pad_requirements(info, rb, p, pad, sev)
        key = tuple(sorted(vec.items()))
        cls = pin_req.get(key)
        if cls is None:
            cls = f"kae_pin{len(pin_req)}"
            pin_req[key] = cls
            p.obstacle_classes[cls] = ObstacleClass(cls, dict(vec))
        p.pin_class[(pad["comp"], pad["pin"])] = cls

    # ---- obstacles
    _obstacles(info, rb, p, sev, opts)

    # ---- the board outline (Freerouting applies one value to every class)
    edge_vals = [v[0] for v in p.obstacle_classes.get("kae_edge", ObstacleClass("", {})).values.values()]
    p.edge_clearance = max(edge_vals) if edge_vals else s.get("edge_clearance", 0.0)
    p.notes["unsupported_functions"] = sorted(rb.unsupported)
    p.notes["rule_errors"] = list(rb.errors)
    return p


def pair_clearances(info, rb, na, nb, layer, wa=None, wb=None, via_a=None, via_b=None):
    """KiCad's requirements between copper of nets `na` and `nb` on `layer`, in mm:
    dict(ww, wv, vw, vv) for track-track, track of a - via of b, via of a - track of b and
    via-via, with hole clearance taken through each via's annular ring and hole-to-hole
    through both drills; a diff pair's own gap raises track-track. `wa`, `wb` are the track
    widths (rules may test Width) and `via_a`, `via_b` the vias as (diameter, drill)."""
    l = layer
    Da, da = via_a or (0.0, 0.0)
    Db, db = via_b or (0.0, 0.0)
    ringa, ringb = (Da - da) / 2, (Db - db) / 2
    ta = net_item(info, na, "track", l, wa)
    tb = net_item(info, nb, "track", l, wb)
    va, vb = net_item(info, na, "via", l), net_item(info, nb, "via", l)
    ww = _strict_min(rb, "clearance", ta, tb, l)
    wv = max(_strict_min(rb, "clearance", ta, vb, l), _strict_min(rb, "hole_clearance", ta, vb, l) - ringb)
    vw = max(_strict_min(rb, "clearance", va, tb, l), _strict_min(rb, "hole_clearance", tb, va, l) - ringa)
    vv = max(_strict_min(rb, "clearance", va, vb, l),
             _strict_min(rb, "hole_to_hole", va, vb, None) + (da + db) / 2 - (Da + Db) / 2,
             _strict_min(rb, "hole_clearance", va, vb, l) - ringb,
             _strict_min(rb, "hole_clearance", vb, va, l) - ringa)
    if R.diff_base(na) is not None and R.complement_net(na) == nb:
        gap = R.strictest(rb, "diff_pair_gap", ta, tb, l).min or 0.0
        ww = max(ww, gap)
    return dict(ww=ww, wv=wv, vw=vw, vv=vv)


def _class_name(netclass, used):
    base = "kae_" + "".join(ch if ch.isalnum() else "_" for ch in netclass)[:40]
    name, k = base, 1
    while name in used:
        k += 1
        name = f"{base}_{k}"
    return name


def via_name(rc, n_layers):
    """A class's via padstack: Via[0-n]_<D>:<d>_um in whole micrometres (Freerouting drops a
    decimal fraction from via names, KiCad reads the drill from the name)."""
    return f"Via[0-{n_layers - 1}]_{round(rc.via[0] * 1000)}:{round(rc.via[1] * 1000)}_um"


# ----------------------------------------------------------------------------- pads
def _poly(rings):
    if not rings or len(rings[0]) < 3:
        return None
    g = Polygon(rings[0], [h for h in rings[1:] if len(h) >= 3])
    return g if g.is_valid else g.buffer(0)


def _pad_shapes(pad):
    """(dsn shape, {layer: real copper}) as shapely geometry. KiCad's DSN pin carries one
    shape for all layers (the pad's ALL_LAYERS shape, first outline of a custom pad)."""
    real = {}
    if "poly" in pad:
        g = unary_union([x for x in (_poly(r) for r in pad["poly"]) if x is not None])
        for l in pad["layers"]:
            real[l] = g
        first = _poly(pad["poly"][0]) if pad["poly"] else None
    else:
        byl = pad.get("poly_by_layer") or {}
        for l, polys in byl.items():
            real[l] = unary_union([x for x in (_poly(r) for r in polys) if x is not None])
        f = byl.get(pad["layers"][0]) if pad["layers"] else None
        first = _poly(f[0]) if f else None
    return first, real


def _excess(real, dsn):
    """How far `real` copper reaches beyond the `dsn` shape (directed Hausdorff, mm)."""
    if real is None or dsn is None or real.is_empty:
        return 0.0
    out = real.difference(dsn.buffer(1e-6))
    if out.is_empty or out.area < 1e-10:
        return 0.0
    pts = shapely.get_coordinates(shapely.segmentize(out.boundary, 0.01))
    return max(float(dsn.distance(Point(x, y))) for x, y in pts) if len(pts) else 0.0


def _ring(pad, dsn):
    """Smallest distance from the pad's hole edge to the DSN shape's boundary (negative when
    the hole is not inside the shape)."""
    h = pad.get("hole")
    if not h or dsn is None:
        return None
    seg = LineString([h["a"], h["b"]]) if h["a"] != h["b"] else Point(h["a"])
    return float(dsn.exterior.distance(seg)) - h["width"] / 2 if dsn.contains(seg) else -h["width"] / 2


def _pad_requirements(info, rb, p, pad, sev):
    """{(routing class, layer): clearance mm} for one pad (see module docstring)."""
    s = info["settings"]
    cu = p.copper
    pi = pad_item(info, pad)
    dsn, real = _pad_shapes(pad)
    ring = _ring(pad, dsn)
    mask_on = not _severity_ignored(sev, "solder_mask_bridge") and not pad.get("allow_bridges")
    out = {}
    for n, rc in p.classes.items():
        if not rc.rep:
            continue
        D, d = rc.via
        rv = (D - d) / 2
        for l in cu:
            if l not in pad["layers"]:
                continue
            e = _excess(real.get(l), dsn)
            t = net_item(info, rc.rep, "track", l, rc.widths[l])
            v = net_item(info, rc.rep, "via", l)
            tw = _strict_min(rb, "clearance", pi, t, l) + e
            vw = _strict_min(rb, "clearance", pi, v, l) + e
            if pad.get("hole"):
                hc_t = _strict_min(rb, "hole_clearance", pi, t, l)
                hc_v = _strict_min(rb, "hole_clearance", pi, v, l)
                if ring is not None:
                    tw = max(tw, hc_t - ring)
                    vw = max(vw, hc_v - ring)
                if pad.get("drilled") and ring is not None:
                    vw = max(vw, _strict_min(rb, "hole_to_hole", pi, v, None) - rv - ring)
            vw = max(vw, _strict_min(rb, "hole_clearance", v, pi, l) - rv + e)
            side = "F" if l == cu[0] else ("B" if l == cu[-1] else None)
            if mask_on and side and side in (pad.get("mask") or {}):
                m = pad["mask"][side] + s.get("mask_to_copper", 0.0) + e
                tw = max(tw, m)
                tented = s.get("tent_vias_front" if side == "F" else "tent_vias_back", True)
                vw = max(vw, m if tented else m + s.get("mask_min_web", 0.0) + s.get("mask_expansion", 0.0))
            if pad.get("attr") == "npth" and pad.get("hole") and pad["hole"]["a"] != pad["hole"]["b"]:
                ec_t = _strict_min(rb, "edge_clearance", t, EDGE_ITEM, l)
                ec_v = _strict_min(rb, "edge_clearance", v, EDGE_ITEM, l)
                tw, vw = max(tw, ec_t + e), max(vw, ec_v + e)
            out[(n, l)] = (up(max(tw, EPS_SHORT)), up(max(vw, EPS_SHORT)))
    return out


# ----------------------------------------------------------------------------- obstacles
def _obstacle_class(p, prefix, vec):
    for name, oc in p.obstacle_classes.items():
        if name.startswith(prefix) and oc.values == vec:
            return name
    name = f"{prefix}{sum(1 for k in p.obstacle_classes if k.startswith(prefix))}"
    p.obstacle_classes[name] = ObstacleClass(name, dict(vec))
    return name


def _zero_class(p):
    name = "kae_zero"
    if name not in p.obstacle_classes:
        p.obstacle_classes[name] = ObstacleClass(name, {(n, l): (0.0, 0.0) for n in p.classes for l in p.copper})
    return name


def _edge_geoms(info):
    """(cut-outs and stray edge geometry as polygons, board region). Edges are Edge.Cuts
    shapes at zero width (board and footprint) and Margin shapes at their stroke width."""
    board = None
    rings = info.get("outline") or []
    polys = [x for x in (_poly(r) for r in rings) if x is not None]
    if polys:
        board = unary_union(polys)
    cut = []
    for pg in polys:
        for h in pg.interiors:
            hp = Polygon(h)
            if hp.area > 1e-8:
                cut.append(hp)
    stray = []
    bnd = board.boundary if board is not None else None
    for e in info.get("edges") or []:
        g = _edge_line(e)
        if g is None:
            continue
        w = e.get("width", 0.0) if e.get("layer") == "Margin" else 0.0
        if e.get("layer") == "Edge.Cuts" and bnd is not None:
            pts = shapely.get_coordinates(shapely.segmentize(g, 0.05))
            if all(bnd.distance(Point(x, y)) < 0.002 for x, y in pts):
                continue  # part of the outline: Freerouting's boundary or a cut-out
        stray.append(g.buffer(max(w / 2, 0.0005), quad_segs=8))
    return cut, stray, board


def _edge_line(e):
    k = e.get("kind")
    if k == "segment":
        return LineString(e["pts"])
    if k == "arc":
        from kae.board.geom import arc_points
        return LineString(arc_points(tuple(e["pts"][0]), tuple(e["pts"][1]), tuple(e["pts"][2]), 0.001))
    if k == "circle":
        return Point(e["center"]).buffer(e["radius"], quad_segs=64).exterior
    if k == "rect":
        (x1, y1), (x2, y2) = e["pts"]
        return box(min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)).exterior
    if k == "poly":
        gs = [x for x in (_poly(r) for r in e.get("rings") or []) if x is not None]
        return unary_union([g.boundary for g in gs]) if gs else None
    if k == "polyline" and len(e.get("pts") or []) >= 2:
        return LineString(e["pts"])
    return None


def _obstacles(info, rb, p, sev, opts):
    cu = p.copper
    # ---- edges: Freerouting's outline and the edge class carry the track requirement; where
    # vias need more (KiCad's board setup often asks more of vias than a custom track rule),
    # a via keepout band of the difference lines every edge
    vec, band = {}, 0.0
    for n, rc in p.classes.items():
        if not rc.rep:
            continue
        for l in cu:
            t = net_item(info, rc.rep, "track", l, rc.widths[l])
            v = net_item(info, rc.rep, "via", l)
            ew = _strict_min(rb, "edge_clearance", t, EDGE_ITEM, l)
            ev_ = _strict_min(rb, "edge_clearance", v, EDGE_ITEM, l)
            vec[(n, l)] = (up(max(ew, 0.0)), up(max(ev_, 0.0)))
            band = max(band, ev_)
    p.obstacle_classes["kae_edge"] = ObstacleClass("kae_edge", vec)
    track_edge = max(v[0] for v in vec.values()) if vec else 0.0
    cut, stray, board = _edge_geoms(info)
    for g in cut:
        p.obstacles.append(Obstacle("keepout", "signal", g, "kae_edge", "board cut-out"))
    for g in stray:
        p.obstacles.append(Obstacle("keepout", "signal", g, "kae_edge", "edge shape"))
    p.notes["via_edge_band"] = round(band, 4)
    if band > track_edge + 1e-6 and board is not None and not opts.get("no_band"):
        # Freerouting's outline has one clearance for tracks and vias: a band inside the
        # outer outline keeps vias at their own distance (cut-outs and stray edges carry
        # both values in their class)
        w = up(band)
        shell = unary_union([Polygon(pg.exterior) for pg in getattr(board, "geoms", [board])])
        inner = shell.buffer(-w, quad_segs=16)
        geo = shell.difference(inner) if not inner.is_empty else shell
        if not geo.is_empty:
            p.obstacles.append(Obstacle("via_keepout", "signal", geo, _zero_class(p), "via edge band"))
    # ---- NPTH round holes (KiCad exports them as round keepouts at hole + board hole clearance)
    for pad in info["pads"]:
        h = pad.get("hole")
        if not h or not pad.get("round_keepout"):
            continue
        pi = pad_item(info, pad)
        vec = {}
        for n, rc in p.classes.items():
            if not rc.rep:
                continue
            D, d = rc.via
            for l in cu:
                t = net_item(info, rc.rep, "track", l, rc.widths[l])
                v = net_item(info, rc.rep, "via", l)
                tw = _strict_min(rb, "hole_clearance", pi, t, l)
                vw = max(_strict_min(rb, "hole_clearance", pi, v, l),
                         _strict_min(rb, "hole_to_hole", pi, v, None) + d / 2 - D / 2)
                if pad.get("attr") != "npth":
                    tw = max(tw, _strict_min(rb, "clearance", pi, t, l))
                    vw = max(vw, _strict_min(rb, "clearance", pi, v, l))
                vec[(n, l)] = (up(max(tw, EPS_SHORT)), up(max(vw, EPS_SHORT)))
        cls = _obstacle_class(p, "kae_hole", vec)
        p.obstacles.append(Obstacle("keepout", "signal", ("circle", h["a"][0], h["a"][1], h["width"]), cls,
                                    f"hole {pad['ref']}.{pad['number']}"))
    # ---- copper graphics and texts (no net: shorts; with a net: foreign copper)
    for g in info.get("graphics") or []:
        gi = graphic_item(info, g)
        vec = {}
        for n, rc in p.classes.items():
            if not rc.rep:
                continue
            for l in cu:
                if l not in g["layers"]:
                    continue
                t = net_item(info, rc.rep, "track", l, rc.widths[l])
                v = net_item(info, rc.rep, "via", l)
                tw = _strict_min(rb, "clearance", gi, t, l)
                vw = _strict_min(rb, "clearance", gi, v, l)
                vec[(n, l)] = (up(max(tw, EPS_SHORT)), up(max(vw, EPS_SHORT)))
        if not vec:
            continue
        cls = _obstacle_class(p, "kae_cu", vec)
        why = f"copper {g.get('cls')} {g.get('owner') or 'board'} {g.get('net') or 'no net'}"
        shapes = {}
        for l, polys in g["layers"].items():
            geo = unary_union([x for x in (_poly(r) for r in polys) if x is not None])
            if not geo.is_empty:
                shapes[l] = geo
        net = g.get("net") or ""
        if net in p.net_class and shapes and all(isinstance(s, Polygon) and len(s.interiors) == 0
                                                 for s in shapes.values()):
            # copper of a net: a pin of that net in the DSN (a connection target for its
            # own net, an obstacle in class `cls` for the others)
            p.net_graphics.append((net, shapes, cls, why))
            continue
        for l, geo in shapes.items():
            p.obstacles.append(Obstacle("keepout", l, geo, cls, why))
    # ---- kae.route.critical's pours: hard obstacles for the other nets
    for z in opts.get("crit_zones") or []:
        net = z.get("net") or ""
        if net not in p.net_class:
            continue
        nc = info["nets"].get(net, {}).get("netclass", "Default")
        zi = dict(type="Zone", net=net, netclass=nc, constituents=nc.split(","), copper=True,
                  connected=True, layers=list(z.get("layers") or []))
        zc = z.get("clearance") or 0.0
        vec = {}
        for n, rc in p.classes.items():
            if not rc.rep:
                continue
            ring = (rc.via[0] - rc.via[1]) / 2
            for l in cu:
                t = net_item(info, rc.rep, "track", l, rc.widths[l])
                v = net_item(info, rc.rep, "via", l)
                tw = max(zc, _strict_min(rb, "clearance", zi, t, l))
                vw = max(zc, _strict_min(rb, "clearance", zi, v, l), _strict_min(rb, "hole_clearance", zi, v, l) - ring)
                vec[(n, l)] = (up(max(tw, EPS_SHORT)), up(max(vw, EPS_SHORT)))
        cls = _obstacle_class(p, "kae_crit", vec)
        for l, polys in (z.get("layers") or {}).items():
            for rings in polys:
                g = _poly(rings)
                for part in (_hole_free(g) if g is not None else []):
                    p.net_graphics.append((net, {l: part}, cls, f"zone {z.get('name')} {net}"))
    # ---- rule areas: KiCad's disallow test is plain intersection
    for z in info.get("zones") or []:
        if not z.get("rule_area") or not (z.get("no_tracks") or z.get("no_vias")):
            continue
        geo = unary_union([x for x in (_poly(r) for r in z["rings"]) if x is not None])
        if geo.is_empty:
            continue
        kind = "keepout" if z.get("no_tracks") else "via_keepout"
        zc = _zero_class(p)
        for l in z["layers"]:
            p.obstacles.append(Obstacle(kind, l, geo, zc, f"rule area {z.get('name') or ''} {z.get('owner') or ''}"))
    # ---- thermal-spoke corridors: for the pads named in opts["thermal_pads"] (pad uuids;
    # the repair loop adds the pads KiCad reports starved), or for all pads with "all"
    pads = opts.get("thermal_pads")
    if pads:
        for geo, layer, pad in thermal_corridors(info, p, None if pads == "all" else set(pads), sev):
            p.obstacles.append(Obstacle("keepout", layer, geo, _zero_class(p),
                                        f"thermal spokes {pad['ref']}.{pad['number']}"))


def _hole_free(g):
    """Simple polygons that together cover polygon `g`: each hole is cut open by a vertical
    line through it (a DSN pin shape has no holes)."""
    from shapely.ops import split
    out, todo = [], [g]
    while todo:
        q = todo.pop()
        if not isinstance(q, Polygon) or q.is_empty or q.area < 1e-9:
            continue
        if not q.interiors:
            out.append(q)
            continue
        x = Polygon(q.interiors[0]).representative_point().x
        _, y0, _, y1 = q.bounds
        pieces = [x_ for x_ in split(q, LineString([(x, y0 - 1), (x, y1 + 1)])).geoms]
        if len(pieces) < 2:
            out.append(Polygon(q.exterior))
            continue
        todo.extend(pieces)
    return out


def thermal_corridors(info, p, pad_uuids=None, sev=None):
    """[(geometry, layer, pad)]: strips to keep foreign copper out of so that KiCad's zone
    filler can draw enough thermal spokes for a pad that connects to a zone of its net with
    thermal relief (starved_thermal; a pad whose spokes are all cut is also left unconnected).

    A spoke runs from the pad along one of four directions (the pad's spoke angle + k*90)
    and must land in zone fill past the thermal gap. Fill can only exist inside the zone,
    away from foreign pads and copper by the zone clearance and from the board edge; so each
    strip (spoke width + 2 clearances wide, reaching past the gap by the zone's minimum width)
    is cut to that potential fill, and only the `min_resolved_spokes` strips with the most
    landing area are kept. `pad_uuids` limits the pads (None: all)."""
    if sev and _severity_ignored(sev, "starved_thermal"):
        return []
    s = info["settings"]
    need = int(s.get("min_resolved_spokes") or 2)
    zones = [z for z in info.get("zones") or [] if not z.get("rule_area") and z.get("net") and not z.get("teardrop")]
    out = []
    if not zones or need <= 0:
        return out
    board = None
    rings = info.get("outline") or []
    polys = [x for x in (_poly(r) for r in rings) if x is not None]
    if polys:
        board = unary_union(polys)
    foreign_cache = {}

    def foreign(layer, net, clr):
        key = (layer, net, round(clr, 4))
        if key not in foreign_cache:
            geos = []
            for q in info["pads"]:
                if q.get("net") == net and net:
                    continue
                _, rq = _pad_shapes(q)
                g = rq.get(layer)
                if g is not None and not g.is_empty:
                    geos.append(g.buffer(clr, quad_segs=4))
                h = q.get("hole")
                if h and not rq.get(layer):
                    geos.append(LineString([h["a"], h["b"]]).buffer(h["width"] / 2 + clr) if h["a"] != h["b"]
                                else Point(h["a"]).buffer(h["width"] / 2 + clr))
            for g in info.get("graphics") or []:
                if g.get("net") == net and net:
                    continue
                for r in (g.get("layers") or {}).get(layer, []):
                    pg = _poly(r)
                    if pg is not None:
                        geos.append(pg.buffer(clr, quad_segs=4))
            foreign_cache[key] = unary_union(geos) if geos else Polygon()
        return foreign_cache[key]

    for pad in info["pads"]:
        if not pad.get("net") or not pad.get("layers"):
            continue
        if pad_uuids is not None and pad.get("uuid") not in pad_uuids:
            continue
        dsn, real = _pad_shapes(pad)
        for z in zones:
            if z["net"] != pad["net"]:
                continue
            conn = pad.get("zone_connection") or "inherited"
            if conn == "inherited":
                conn = z.get("pad_connection") or "thermal"
            if conn == "thru_hole_only":
                conn = "thermal" if pad.get("attr") == "pth" else "full"
            if conn != "thermal":
                continue
            zg = unary_union([x for x in (_poly(r) for r in z["rings"]) if x is not None])
            for l in pad["layers"]:
                if l not in z["layers"]:
                    continue
                cop = real.get(l)
                if cop is None or cop.is_empty or not zg.intersects(cop):
                    continue
                gap = pad.get("thermal_gap") or z.get("thermal_gap") or 0.5
                mt = z.get("min_thickness") or 0.0
                sw = max(pad.get("spoke_width") or z.get("spoke_width") or 0.5, mt)
                clr = max(z.get("clearance") or 0.0, s.get("min_clearance", 0.0))
                fill = zg
                if board is not None:
                    fill = fill.intersection(board.buffer(-s.get("edge_clearance", 0.0)))
                fill = fill.difference(foreign(l, pad["net"], clr))
                if fill.is_empty:
                    continue
                cx, cy = pad["pos"]
                minx, miny, maxx, maxy = cop.bounds
                half = max(maxx - cx, cx - minx, maxy - cy, cy - miny)
                reach = half + gap + max(mt, 0.1) + clr
                ring = cop.buffer(gap, quad_segs=8)
                cand = []
                for k in range(4):
                    a = math.radians((pad.get("spoke_angle") or 0.0) + 90 * k)
                    ex, ey = cx + reach * math.cos(a), cy - reach * math.sin(a)
                    strip = LineString([(cx, cy), (ex, ey)]).buffer(sw / 2 + clr, cap_style="flat")
                    land = strip.intersection(fill).difference(ring)
                    if land.area < sw * max(mt, 0.05):
                        continue
                    cand.append((land.area, strip.intersection(fill.union(ring)).difference(cop.buffer(1e-4))))
                cand.sort(key=lambda t: -t[0])
                corridor = unary_union([g for _, g in cand[:need]]) if cand else None
                if corridor is not None and not corridor.is_empty:
                    out.append((corridor, l, pad))
    return out


# ----------------------------------------------------------------------------- validation
def validate(info, board_path):
    """Compare this module's rule resolution with KiCad's own engine on the probes
    (single-item constraints: track width, via diameter and drill, own clearance of
    tracks, vias and pads). Returns counts and the first mismatches."""
    rb = rule_board(info, board_path)
    cu = info["copper"]
    out = dict(checked=0, mismatched=0, examples=[])

    def check(what, mine, kicad):
        out["checked"] += 1
        if (mine is None) != (kicad is None) or (mine is not None and abs(mine - kicad) > 1e-6):
            out["mismatched"] += 1
            if len(out["examples"]) < 20:
                out["examples"].append(dict(what=what, ours=mine, kicad=kicad))

    for net, pr in info["probes"].items():
        for l in cu:
            ti = net_item(info, net, "track", l, width=0.1)
            c = R.evaluate(rb, "track_width", ti, None, l)
            kw = (pr["track"].get(l) or {}).get("width") or [None, None, None]
            check(f"track_width min {net} {l}", c.min, kw[0])
            check(f"track_width opt {net} {l}", c.opt if c.opt is not None else c.min, kw[1] if kw[1] is not None else kw[0])
            check(f"track_width max {net} {l}", c.max, kw[2])
            cl = R.evaluate(rb, "clearance", ti, None, l)
            check(f"track clearance {net} {l}", cl.min or 0.0, pr["track"][l]["clearance"])
            vi = net_item(info, net, "via", l)
            cv = R.evaluate(rb, "clearance", vi, None, l)
            check(f"via clearance {net} {l}", cv.min or 0.0, pr["via"]["clearance"][l])
            an = R.evaluate(rb, "annular_width", vi, None, l)
            check(f"via annulus {net} {l}", an.min or 0.0, pr["via"]["annulus"][l])
        vi = net_item(info, net, "via")
        for ctype, key in (("via_diameter", "diameter"), ("hole_size", "drill")):
            c = R.evaluate(rb, ctype, vi, None, None)
            k = pr["via"][key] or [None, None, None]
            check(f"{ctype} min {net}", c.min, k[0])
            check(f"{ctype} max {net}", c.max, k[2])
    for pad in info["pads"]:
        pi = pad_item(info, pad)
        ctype = "hole_clearance" if pad.get("attr") == "npth" else "clearance"
        for l, v in (pad.get("own_clearance") or {}).items():
            c = R.evaluate(rb, ctype, pi, None, l)
            check(f"pad {ctype} {pad['ref']}.{pad['number']} {l}", c.min or 0.0, v)
    out["unsupported"] = sorted(rb.unsupported)
    out["rule_errors"] = rb.errors
    return out
