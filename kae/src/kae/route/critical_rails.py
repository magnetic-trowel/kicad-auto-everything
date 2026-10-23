# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Power rails and their ground return: widths from current, a drop budget, zones first.

For every rail of the brief (net role 'rail') with a source and at least one load:

1. **Currents (E5).** Each load gets a supply current by part class (`load_current`; an IC
   or module only through its supply pins, never through FB, EN or sense pins); the
   source a rating by class (`source_rating`). The design current of the rail is the sum
   of the loads with a 3x margin for the E5 uncertainty, capped by the source's rating
   (the most it can deliver); each branch carries its load's current.
2. **Budget and width.** A DC drop budget of 2 % of the rail voltage at the design current,
   rail plus ground: 1 % each, or 1.6 % for the rail when the ground return is a pour. A
   branch of length l then needs w >= rho l I / (t dV) (`drop_width`), never less than
   IPC-2221 at 10 K or the net class width. A branch carrying 0.25 A or more is drawn at
   least as wide as its narrower terminal pad (feed width: the most resistance per area of
   copper, docs/topics/physics/power-copper.md section 3), up to 3 mm, narrower where the
   board has no room.
3. **Zones first.** A terminal whose pad lies in a zone of the rail on its own layer is
   connected by the fill; one under a zone on another layer gets a via beside the pad;
   only the rest get tracks. A rail without zones is routed as a trunk to its farthest
   load at the design current, then a branch per load to the copper laid so far.
4. **Ground.** Load ground pins that a ground pour does not reach on their own layer get
   a via into it; without a ground pour the return of a routed rail is routed like the rail
   (source ground pin to each load's ground pin, same currents and widths).

In 'auto' mode only rails whose design current needs more than the class width get
tracks (zone vias are always placed for routed rails); 'all' routes every rail.

Every branch reports its routed resistance and the drop at its current against the
budget; the DC passport on the finished board is the check.
"""
from __future__ import annotations

import math
import re

from .critical_grid import Anchor
from .critical_modules import Module, _commit_vias, anchor, hop_layers, route_hop, via_candidates, width_ladder
from .critical_physics import drop_width, ipc2221_width, r_track, r_via

DROP_SHARE = 0.02          # rail + ground drop budget, fraction of the rail voltage (E5)

CONNECTOR_A = (            # (lib_id/value pattern, rating A) for connectors (E5, by family)
    (r"BarrelJack|DC_?Jack|Jack_DC|PJ-0\d\d", 5.0),
    (r"USB_C|USB-C|Type-?C", 3.0),
    (r"USB_Micro|Micro-?USB|USB_Mini", 1.8),
    (r"USB_A|USB_B", 1.5),
    (r"TerminalBlock|Terminal_Block|Phoenix|Screw", 10.0),
    (r"XT30|XT60|XT90|Amass", 15.0),
    (r"JST_VH|JST_EH|_VH_|MiniFit|Mini-Fit|Molex_Mini", 5.0),
    (r"JST_XH|_XH_|B\dB-XH", 3.0),
    (r"JST_PH|_PH_|B\dB-PH", 2.0),
    (r"JST_SH|_SH_|JST_GH|_GH_|Qwiic|STEMMA", 1.0),
    (r"PinHeader|PinSocket|Header", 3.0),
    (r"Battery|BatteryHolder|CR20\d\d|18650", 1.0),
)
IC_A = {                   # E5 DC supply current (A) of an IC load by subtype
    "fpga": 1.0, "memory": 0.05, "phy": 0.15, "interface": 0.03, "motor_driver": 1.5, "gate_driver": 0.05,
    "audio_amp": 0.5, "current_sense": 0.002, "adc_dac": 0.01, "reference": 0.001, "rf": 0.12, "sensor": 0.005,
    "opamp": 0.005, "logic": 0.01, "esd_array": 0.0, "usb_pd": 0.01, "battery_monitor": 0.01, "charger": 1.0,
    "pmic": 1.0, "regulator_module": 1.0, "charge_pump": 0.05, "load_switch": 0.5, "regulator_linear": 0.3,
    "regulator_switching": None, "mcu": None,
}


# ----------------------------------------------------------------------------- priors
def _text(ctx, u):
    p = ctx.parts.get(u) or {}
    f = ctx.fp.get(u)
    return f"{p.get('lib_id') or (f.lib_id if f else '')} {p.get('value') or (f.value if f else '')}"


def connector_rating(ctx, u):
    t = _text(ctx, u)
    for pat, a in CONNECTOR_A:
        if re.search(pat, t, re.I):
            return a
    f = ctx.fp.get(u)
    drills = [p.drill for p in f.pads if p.drill] if f else []
    if drills and max(drills) >= 1.0:
        return 5.0
    return 1.0


def ldo_rating(ctx, u):
    t = _text(ctx, u)
    if re.search(r"TO-?252|DPAK|TO-?263|D2PAK|TO-?220", t, re.I):
        return 1.5
    if re.search(r"SOT-?223", t, re.I):
        return 1.0
    if re.search(r"SOT-?89", t, re.I):
        return 0.5
    return 0.3


SUPPLY_PIN = re.compile(r"^(V(CC|DD|IN|BAT|BUS|S|M|PP|IO|CORE|DDA|DDIO|USB|SYS|P|\+)\w*|AVDD|DVDD|IOVDD|PVDD|PVIN|"
                        r"AVCC|DVCC|VIN\d*|PWR|POWER|\+V\w*|V\+|VREG_IN|IN)$", re.I)


def _supply_pins(ctx, u, net):
    """Whether part u takes supply current from `net`: an IC or module only through a
    supply pin (power_in, or a supply name); FB, EN, sense and logic pins draw none."""
    f = ctx.fp.get(u)
    if f is None:
        return False
    for p in f.pads:
        if p.net != net:
            continue
        if p.pintype in ("power_in",) or SUPPLY_PIN.match((p.pinfunction or "").split("/")[0].strip()):
            return True
    return False


def load_current(ctx, u, net, cells):
    """E5 supply current (A) a part draws from rail `net` (see the module docstring)."""
    p = ctx.parts.get(u) or {}
    kind, sub, role = p.get("kind"), p.get("subtype"), p.get("role")
    if kind in ("ic", "module") and not (u in cells and cells[u].get("rail") == net) and not _supply_pins(ctx, u, net):
        return 0.0
    v = ctx.volts(net) or 3.3
    if u in cells:                            # a converter's input: its output power / (eta V_in)
        c = cells[u]
        ex = c.get("excite") or {}
        vin = ex.get("V") or v
        vout = ctx.volts(c.get("vout")) or 0.5 * vin
        i_out = float(ex.get("I") or 1.0)
        if c.get("rail") == net and c.get("class") in ("buck", None):
            return vout * i_out / (0.88 * max(vin, 0.5))
        if c.get("rail") == net:
            return i_out
    if kind == "ic":
        if sub == "mcu":
            from kae.physics.priors import ic_current_prior
            return ic_current_prior(ctx.npins(u))
        a = IC_A.get(sub)
        if a is not None:
            return a
        if p.get("P_W"):
            return min(2.0, float(p["P_W"]) / v)
        from kae.physics.priors import ic_current_prior
        return ic_current_prior(ctx.npins(u))
    if kind == "module":
        return 0.35 if re.search(r"ESP32|ESP8266|WROOM|WROVER|RP2040|Pico|nRF", _text(ctx, u), re.I) else 0.2
    if kind == "led":
        return 0.06 if re.search(r"WS28|SK68|APA10|SK98|NeoPixel|LED_RGB_?\d{4}", _text(ctx, u), re.I) else 0.02
    if kind == "connector":
        return connector_rating(ctx, u)
    if kind == "transistor":
        return 0.5 if re.search(r"FET|MOS|DPAK|TO-?252|SO-?8|PowerPAK", _text(ctx, u), re.I) else 0.1
    if kind == "relay":
        return 0.08
    if kind in ("buzzer", "speaker"):
        return 0.05
    if kind == "resistor":
        ohms = ((p.get("attrs") or {}).get("ohms"))
        if ohms and ohms > 1.0:
            return min(0.05, v / ohms)
        return 0.0
    return 0.0


def source_rating(ctx, u, net, cells):
    """E5 current (A) the source of rail `net` can deliver, or None when unknown."""
    if u is None:
        return None
    p = ctx.parts.get(u) or {}
    kind, sub = p.get("kind"), p.get("subtype")
    for c in cells.values():
        if c.get("vout") == net and (c.get("controller") == u or c.get("inductor") == u):
            return float((c.get("excite") or {}).get("I") or 1.0)
    if kind == "connector":
        return connector_rating(ctx, u)
    if kind == "ic" and sub == "regulator_linear":
        return ldo_rating(ctx, u)
    if kind == "ic" and sub in ("regulator_switching", "pmic", "charger", "regulator_module"):
        return 1.0
    if kind == "battery":
        return 1.0
    if kind == "module":
        return 0.3
    if kind == "inductor":
        a = re.search(r"(\d+(?:\.\d+)?)\s*A\b", p.get("value") or "")
        return 0.6 * float(a.group(1)) if a else 1.0
    return None


# ----------------------------------------------------------------------------- rails
def _rail_parts(ctx, net):
    """{uuid: [pad numbers on net]} for every part with a pad on `net`."""
    out = {}
    for f in ctx.board.footprints:
        for p in f.pads:
            if p.net == net:
                out.setdefault(f.uuid, []).append(p.number)
    return out


def _pads_on_zone(ctx, t, net):
    """True when the terminal's pad sits inside a zone of `net` on one of its own layers."""
    from shapely.geometry import Point
    c = Point(t.x, t.y)
    for l, g in ctx.sp.zones_of(net):
        if l in t.layers and g.contains(c):
            return True
    return False


def _zone_layer_over(ctx, t, net):
    """A layer (not the pad's) where a zone of `net` covers the pad location."""
    for l, g in ctx.sp.zones_of(net):
        if l in t.layers:
            continue
        if ctx.sp.zone_covers(net, l, t.x, t.y, margin=0.5):
            return l
    return None


def _best_term(ctx, u, numbers, toward):
    best = None
    for n in numbers:
        t = ctx.sp.terminal(u, [n])
        if t is None:
            continue
        d = math.hypot(t.x - toward[0], t.y - toward[1]) if toward else 0.0
        if best is None or d < best[0]:
            best = (d, t)
    return best[1] if best else None


def _cells(ctx):
    cells = {}
    for s in ctx.brief.get("structures") or []:
        if s.get("kind") == "commutation_cell" and s.get("controller"):
            cells[s["controller"]] = s
    return cells


def rail_plan(ctx):
    """[{net, src, loads {uuid: A}, rating, design, parts}] for every rail of the brief with a
    source and at least one load (the E5 currents of the module docstring)."""
    nets = ctx.nets
    cells = _cells(ctx)
    rails = []
    for net, r in nets.items():
        if (r or {}).get("role") != "rail" or net not in ctx.board.nets:
            continue
        src = ((r.get("source") or {}).get("part"))
        parts = _rail_parts(ctx, net)
        if src not in parts:
            continue
        loads = {}
        for u in parts:
            if u == src:
                continue
            a = load_current(ctx, u, net, cells)
            if a > 0:
                loads[u] = a
        if not loads:
            continue
        rating = source_rating(ctx, src, net, cells)
        total = sum(loads.values())
        # the source's rating bounds the loads; the loads' E5 sum, with a 3x margin for
        # its uncertainty, bounds what the rail must carry
        design = min(rating, max(3.0 * total, total + 0.1)) if rating else total
        rails.append(dict(net=net, src=src, loads=loads, rating=rating, design=design, parts=parts))
    rails.sort(key=lambda x: -x["design"])
    return rails


def rail_currents(ctx):
    """{rail net: design current (A)}."""
    return {r["net"]: r["design"] for r in rail_plan(ctx)}


def route_rails(ctx, mode="auto"):
    """Route the rails (and ground returns) of the brief; returns a report per rail."""
    rails = rail_plan(ctx)
    report = []
    ground_load = {}
    gnd_pour = any(ctx.sp.zones_of(g) for g in ctx.gnd)
    for rl in rails:
        rep = _route_rail(ctx, rl, mode, gnd_pour)
        report.append(rep)
        if rep.get("routed"):
            for u, a in rl["loads"].items():
                ground_load[u] = ground_load.get(u, 0.0) + min(a, rl["design"])
            ground_load[rl["src"]] = ground_load.get(rl["src"], 0.0) + rl["design"]
    for g in sorted(ctx.gnd):
        if ground_load and ctx.sp.zones_of(g):
            report.append(_route_ground(ctx, g, ground_load, rails, mode))
    return report


def _route_rail(ctx, rl, mode, gnd_pour):
    net, src = rl["net"], rl["src"]
    v = ctx.volts(net) or 3.3
    dv_rail = DROP_SHARE * v * (0.8 if gnd_pour else 0.5)
    design = rl["design"]
    m = Module(id=f"rail:{net}", kind="rail", spec=dict(net=net), parts=[src] + list(rl["loads"]))
    rep = dict(net=net, volts=v, source=ctx.fp[src].ref, design_A=round(design, 3),
               rating_A=rl["rating"], loads={ctx.fp[u].ref: round(a, 3) for u, a in rl["loads"].items()},
               budget_mV=round(1e3 * dv_rail, 1), routed=False, branches=[])
    st = ctx.sp.terminal(src, rl["parts"][src])
    if st is None:
        rep["note"] = "source pads not found"
        return rep
    # trunk estimate: the farthest load
    far = max(rl["loads"], key=lambda u: _dist_part(ctx, u, rl["parts"][u], (st.x, st.y)))
    lmax = _dist_part(ctx, far, rl["parts"][far], (st.x, st.y)) * 1.3
    layer = ctx.side_layer(src)
    t_cu = ctx.sp.tcu.get(layer, 0.035)
    w_need = max(ipc2221_width(design, t_mm=t_cu), drop_width(design, lmax, dv_rail, t_cu))
    mn, opt, mx = ctx.sp.width_limits(net, layer)
    rep["width_needed_mm"] = round(w_need, 3)
    if mode == "auto" and w_need <= 1.2 * opt:
        rep["note"] = f"class width {opt} mm carries {design:.2f} A within budget: left to the general router"
        return rep
    rep["routed"] = True
    has_zone = bool(ctx.sp.zones_of(net))
    order = sorted(rl["loads"], key=lambda u: -_dist_part(ctx, u, rl["parts"][u], (st.x, st.y)))
    first = True
    for u in order:
        a = rl["loads"][u]
        cur = design if first else min(design, max(a, 0.05))
        lt = _best_term(ctx, u, _load_pins(ctx, u, net, rl["parts"][u]), (st.x, st.y))
        if lt is None:
            continue
        b = dict(load=ctx.fp[u].ref, current_A=round(cur, 3))
        # zones first
        if has_zone and _pads_on_zone(ctx, lt, net) and _pads_on_zone(ctx, st, net):
            b["via"] = "zone (same layer)"
            rep["branches"].append(b)
            continue
        zl = _zone_layer_over(ctx, lt, net) if has_zone else None
        if zl is not None and (_pads_on_zone(ctx, st, net) or _zone_layer_over(ctx, st, net)):
            lay = ctx.side_layer(u) if ctx.side_layer(u) in lt.layers else lt.layers[0]
            c = via_candidates(ctx, lt, lay, net, zl, toward=(st.x, st.y))
            if c:
                n_v = max(1, math.ceil(cur / 1.0))
                _commit_vias(ctx, m, net, lay, lt, c[:n_v], f"zone:{u}")
                b["via"] = f"{min(n_v, len(c))} via(s) into the {zl} zone"
                rep["branches"].append(b)
                continue
        if ctx.connected(net, st, lt):
            b["via"] = "already connected"
            rep["branches"].append(b)
            continue
        # tracks: trunk at the design current, branches at their own
        dist = math.hypot(lt.x - st.x, lt.y - st.y)
        lay = ctx.side_layer(u)
        t_cu = ctx.sp.tcu.get(lay, 0.035)
        w_t = max(ipc2221_width(cur, t_mm=t_cu), drop_width(cur, 1.3 * dist, dv_rail, t_cu), opt)
        if cur >= 0.25:
            w_t = max(w_t, min(st.width, lt.width))
        w_t = min(w_t, float(ctx.opts.get("rail_max_mm", 3.0)))
        widths = sorted({round(w, 4) for w in width_ladder(w_t, opt, 4)}, reverse=True)
        srcs = [anchor(st)] + ctx.net_copper_anchors(net, connected_to=st)
        layers = [l for l in (lay, ctx.sp.cu[0], ctx.sp.cu[-1]) if l in ctx.sp.cu]
        layers = list(dict.fromkeys(layers))
        rt = route_hop(ctx, m, f"br:{u}", net, [anchor(lt)], srcs, widths, layers, via=len(layers) > 1,
                       via_cost=5.0, layer_factor={l: (1.0 if l == lay else 1.6) for l in layers})
        if rt is None:
            b["note"] = "not routed"
        else:
            R = sum(r_track(math.dist(a_, b_), rt.width, ctx.sp.tcu.get(l_, 0.035)) for l_, a_, b_ in rt.segs)
            R += len(rt.vias) * r_via(ctx.sp.thickness, ctx.sp.via_size(net)[1])
            b.update(width_mm=rt.width, length_mm=round(rt.length, 2), r_mohm=round(1e3 * R, 3),
                     drop_mV=round(1e3 * R * cur, 2))
            first = False
        rep["branches"].append(b)
    # the rest of the net's pads near the rail copper: joined here, at the class width, so
    # the general router is not left islands to join to the middle of a fixed track
    if m.copper:
        rep["completed"] = _complete_net(ctx, m, net, [(st.geom, st.layers)], opt,
                                         float(ctx.opts.get("rail_complete_mm", 8.0)))
    # the source itself into its zone on other layers
    if has_zone and not _pads_on_zone(ctx, st, net):
        zl = _zone_layer_over(ctx, st, net)
        if zl is not None:
            lay = ctx.side_layer(src) if ctx.side_layer(src) in st.layers else st.layers[0]
            c = via_candidates(ctx, st, lay, net, zl)
            if c:
                _commit_vias(ctx, m, net, lay, st, c[:max(1, math.ceil(design))], f"zone:{src}")
    if not gnd_pour and ctx.gnd:
        rep["ground"] = _ground_return(ctx, m, rl, dv_rail)
    rep["items"] = len(m.copper)
    ctx.rail_modules = getattr(ctx, "rail_modules", []) + [m]
    return rep


def _comp_anchors(ctx, comp):
    """Routing anchors for a set of copper items of one net (pads, tracks, vias)."""
    out = []
    for it in comp:
        if it.kind == "track":
            out.append(Anchor(it.geom, tuple(it.layers), None, grow=it.r * 0.8, kind="track"))
        elif it.kind == "via":
            out.append(Anchor(it.geom, tuple(ctx.sp.cu), (it.geom.x, it.geom.y), grow=it.r * 0.8, kind="via"))
        elif it.kind == "pad":
            out.append(Anchor(it.geom, tuple(it.layers), it.pos, kind="pad"))
    return out


def _complete_net(ctx, m, net, seeds, w, reach):
    """Join each pad of `net` within `reach` mm of the copper connected to `seeds`
    ([(geometry, layers)]), and not already on it nor in a zone of the net, with a track of
    width w (at least the class width); nearest first. Returns the number joined.
    Freerouting does not join an island to the middle of a fixed track, so pads left near
    critical copper would stay unrouted."""
    from shapely.ops import unary_union
    sp = ctx.sp
    seen, todo = set(), []
    for it in sp.pads:
        if it.net != net or it.kind != "pad" or not it.owner:
            continue
        key = (it.fp, it.owner[1])
        if key in seen or it.fp is None:
            continue
        seen.add(key)
        t = sp.terminal(it.fp, [it.owner[1]])
        if t is None or _pads_on_zone(ctx, t, net):
            continue
        todo.append(t)
    n = 0
    for _ in range(len(todo)):
        comp = sp.component(net, seeds)
        if not comp:
            break
        ids = {id(x) for x in comp}
        geo = unary_union([x.geom.buffer(x.r) if x.r > 0 else x.geom for x in comp])
        rest = [t for t in todo if not any(id(x) in ids for x in t.items)]
        if not rest:
            break
        t = min(rest, key=lambda t: geo.distance(t.geom))
        d = geo.distance(t.geom)
        if d > reach:
            break
        todo.remove(t)
        lay = t.layers[0] if ctx.side_layer(t.fp) not in t.layers else ctx.side_layer(t.fp)
        layers = list(dict.fromkeys([lay] + [l for l in (sp.cu[0], sp.cu[-1]) if l in sp.cu]))
        ww = max(w, sp.width_limits(net, lay)[1])
        rt = route_hop(ctx, m, f"pad:{t.fp}:{t.pad}", net, [anchor(t)], _comp_anchors(ctx, comp), [ww], layers,
                       via=len(layers) > 1, via_cost=5.0, layer_factor={l: (1.0 if l == lay else 1.6) for l in layers},
                       max_len=2.0 * d + 3.0, optional=True)
        n += rt is not None
    return n


def complete_module_nets(ctx, reach=8.0, island_reach=20.0):
    """For every net (but ground) that carries critical copper: join the net's pads within
    `reach` of each island of that copper (`_complete_net`), then join the islands to each
    other, nearest pair first, when they lie within `island_reach` (two decaps of one rail,
    say). Returns {net: joins}."""
    sp = ctx.sp
    m = Module(id="complete", kind="complete", spec={}, parts=[])
    out = {}
    for net in sorted({it.net for it in sp.routed if it.net and it.net not in ctx.gnd}):
        done = set()
        n = 0
        for it in [x for x in sp.routed if x.net == net]:
            if id(it) in done:
                continue
            seed = [(it.geom.buffer(it.r) if it.r > 0 else it.geom, tuple(it.layers))]
            done |= {id(x) for x in sp.component(net, seed)}
            if reach > 0:
                n += _complete_net(ctx, m, net, seed, 0.0, reach)
            done |= {id(x) for x in sp.component(net, seed)}
        if island_reach > 0:
            n += _join_islands(ctx, m, net, island_reach)
        if n:
            out[net] = n
    if m.copper:
        ctx.rail_modules = getattr(ctx, "rail_modules", []) + [m]
    return out


def _islands(ctx, net):
    """The connected sets of a net's critical copper (with the pads they touch)."""
    sp = ctx.sp
    seen, out = set(), []
    for it in [x for x in sp.routed if x.net == net]:
        if id(it) in seen:
            continue
        comp = sp.component(net, [(it.geom.buffer(it.r) if it.r > 0 else it.geom, tuple(it.layers))])
        seen |= {id(x) for x in comp}
        out.append(comp)
    return out


def _join_islands(ctx, m, net, reach):
    """Join the islands of a net's critical copper, nearest pair first, while a pair lies
    within `reach`: one class-width track each (optional: never walls in a pin)."""
    from shapely.ops import unary_union
    sp = ctx.sp
    n = 0
    tried = set()
    while True:
        isl = _islands(ctx, net)
        if len(isl) < 2:
            return n
        geos = [unary_union([x.geom.buffer(x.r) if x.r > 0 else x.geom for x in c]) for c in isl]
        pairs = sorted(((geos[i].distance(geos[j]), i, j) for i in range(len(isl)) for j in range(i + 1, len(isl))),
                       key=lambda t: t[0])
        pick = next(((d, i, j) for d, i, j in pairs if d <= reach
                     and (frozenset(id(x) for x in isl[i]), frozenset(id(x) for x in isl[j])) not in tried), None)
        if pick is None:
            return n
        d, i, j = pick
        tried.add((frozenset(id(x) for x in isl[i]), frozenset(id(x) for x in isl[j])))
        a, b = _comp_anchors(ctx, isl[i]), _comp_anchors(ctx, isl[j])
        lay = sp.cu[0]
        layers = list(dict.fromkeys([l for l in (sp.cu[0], sp.cu[-1]) if l in sp.cu]))
        w = sp.width_limits(net, lay)[1]
        rt = route_hop(ctx, m, f"island:{net}:{n}", net, a, b, [w], layers, via=len(layers) > 1, via_cost=5.0,
                       max_len=1.6 * d + 3.0, optional=True)
        n += rt is not None


def _ground_return(ctx, m, rl, dv):
    """Without a ground pour: the source's ground pin to each load's ground pin, trunk first,
    at the rail's currents and widths."""
    src = rl["src"]
    fs = ctx.fp.get(src)
    g = next((p.net for p in fs.pads if p.net in ctx.gnd), None) if fs else None
    if g is None:
        return dict(note="source has no ground pin")
    ns = [p.number for p in fs.pads if p.net == g]
    st = _best_term(ctx, src, ns, None)
    out = []
    order = sorted(rl["loads"], key=lambda u: -_dist_part(ctx, u, rl["parts"][u], (st.x, st.y)))
    first = True
    for u in order:
        f = ctx.fp.get(u)
        nu = [p.number for p in f.pads if p.net == g] if f else []
        if not nu:
            continue
        lt = _best_term(ctx, u, nu, (st.x, st.y))
        cur = rl["design"] if first else min(rl["design"], max(rl["loads"][u], 0.05))
        if ctx.connected(g, st, lt):
            out.append(dict(load=f.ref, note="already connected"))
            continue
        lay = ctx.side_layer(u)
        t_cu = ctx.sp.tcu.get(lay, 0.035)
        mn, opt, mx = ctx.sp.width_limits(g, lay)
        dist = math.hypot(lt.x - st.x, lt.y - st.y)
        w_t = max(ipc2221_width(cur, t_mm=t_cu), drop_width(cur, 1.3 * dist, dv, t_cu), opt)
        if cur >= 0.25:
            w_t = max(w_t, min(st.width, lt.width))
        w_t = min(w_t, float(ctx.opts.get("rail_max_mm", 3.0)))
        widths = sorted({round(w, 4) for w in width_ladder(w_t, opt, 4)}, reverse=True)
        srcs = [anchor(st)] + ctx.net_copper_anchors(g, connected_to=st)
        layers = list(dict.fromkeys([lay, ctx.sp.cu[0], ctx.sp.cu[-1]]))
        rt = route_hop(ctx, m, f"gr:{u}", g, [anchor(lt)], srcs, widths, layers, via=len(layers) > 1,
                       via_cost=5.0, layer_factor={l: (1.0 if l == lay else 1.6) for l in layers})
        b = dict(load=f.ref, current_A=round(cur, 3))
        if rt is not None:
            R = sum(r_track(math.dist(a_, b_), rt.width, ctx.sp.tcu.get(l_, 0.035)) for l_, a_, b_ in rt.segs)
            b.update(width_mm=rt.width, length_mm=round(rt.length, 2), r_mohm=round(1e3 * R, 3))
            first = False
        else:
            b["note"] = "not routed"
        out.append(b)
    return dict(net=g, branches=out)


def _load_pins(ctx, u, net, numbers):
    """A load's pins on the rail where its current enters: supply pins for ICs and modules."""
    p = ctx.parts.get(u) or {}
    if p.get("kind") not in ("ic", "module"):
        return numbers
    f = ctx.fp.get(u)
    sup = [q.number for q in f.pads if q.net == net and (q.pintype == "power_in" or
                                                          SUPPLY_PIN.match((q.pinfunction or "").split("/")[0].strip()))]
    return sup or numbers


def _dist_part(ctx, u, numbers, p):
    best = None
    for n in numbers:
        t = ctx.sp.terminal(u, [n])
        if t is not None:
            d = math.hypot(t.x - p[0], t.y - p[1])
            best = d if best is None else min(best, d)
    return best or 0.0


def _route_ground(ctx, g, ground_load, rails, mode):
    """Ground returns of the routed rails' loads: vias into a ground pour where it exists on
    another layer, else tracks from each load's ground pins to its source's."""
    rep = dict(net=g, kind="ground", vias=0, branches=[])
    m = Module(id=f"ground:{g}", kind="rail", spec=dict(net=g), parts=list(ground_load))
    pours = ctx.sp.zones_of(g)
    src_of = {}
    for rl in rails:
        for u in rl["loads"]:
            src_of.setdefault(u, rl["src"])
    for u, a in sorted(ground_load.items(), key=lambda kv: -kv[1]):
        f = ctx.fp.get(u)
        if f is None:
            continue
        nums = [p.number for p in f.pads if p.net == g]
        if not nums:
            continue
        for n in nums[:4]:
            t = ctx.sp.terminal(u, [n])
            if t is None:
                continue
            if pours:
                if _pads_on_zone(ctx, t, g):
                    continue
                zl = _zone_layer_over(ctx, t, g)
                if zl is None:
                    continue
                lay = ctx.side_layer(u) if ctx.side_layer(u) in t.layers else t.layers[0]
                from .critical_modules import _has_plane_link
                if _has_plane_link(ctx, t, g):
                    continue
                c = via_candidates(ctx, t, lay, g, zl)
                if c:
                    nv = max(1, math.ceil(a / 1.0))
                    _commit_vias(ctx, m, g, lay, t, c[:nv], f"zone:{u}:{n}")
                    rep["vias"] += min(nv, len(c))
            break
    if not pours and mode == "all":
        # no ground pour: each routed load's ground pin to its source's ground pin
        for u, a in sorted(ground_load.items(), key=lambda kv: -kv[1]):
            s = src_of.get(u)
            if s is None or s == u:
                continue
            fu, fs = ctx.fp.get(u), ctx.fp.get(s)
            nu = [p.number for p in fu.pads if p.net == g] if fu else []
            ns = [p.number for p in fs.pads if p.net == g] if fs else []
            if not nu or not ns:
                continue
            st = _best_term(ctx, s, ns, None)
            lt = _best_term(ctx, u, nu, (st.x, st.y))
            lay = ctx.side_layer(u)
            mn, opt, mx = ctx.sp.width_limits(g, lay)
            w_t = max(ipc2221_width(a), opt)
            srcs = [anchor(st)] + ctx.net_copper_anchors(g)
            rt = route_hop(ctx, m, f"gr:{u}", g, [anchor(lt)], srcs, sorted({w_t, opt}, reverse=True),
                           [ctx.sp.cu[0], ctx.sp.cu[-1]], via=True, via_cost=5.0)
            rep["branches"].append(dict(load=fu.ref, routed=rt is not None))
    rep["items"] = len(m.copper)
    ctx.rail_modules = getattr(ctx, "rail_modules", []) + [m]
    return rep
