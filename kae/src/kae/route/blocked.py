# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Why the connections still open are open: a diagnosis for the caller, never a relaxation.

The router never relaxes a board's rules on its own. Where a rule makes a connection
impossible, this says which rule, by how much and where, so the caller (an LLM driving kae,
or a person) can change the rule, move a part, or accept the open connection.

`diagnose(board, info, plan, fills, drc_report, ...)` runs once, on the final board. For each
missing connection (each smaller connected part of an open net, as lastmile.parts counts
them) it asks lastmile's grid router, in the same Space with the same rules:

1. is there a path with the router's own copper of other nets taken out? Then the copper we
   laid is in the way: "congestion" (not a rule; more search or rip-up can close it).
2. with the input's copper of other nets (its pre-routes) taken out too? "fixed copper": the
   pre-routes named are in the way.
3. otherwise the rules or the geometry block it. A relaxed search finds the cheapest path
   that keeps only physical overlap with foreign copper and the board outline hard (every
   clearance, keepout and corridor becomes a price per cell instead), at the narrowest
   legal width. Each piece of that path is checked against the real rules
   (Space.track_violations / via_violations); the narrowest gap on it is the binding
   constraint, attributed to the rule that sets it: a net class, board setup minimum or
   footprint value in the .kicad_pro / board, a .kicad_dru rule by name, a rule area, the
   solder-mask opening of a pad, or one of kae's own defaults with its override
   (KAE_<NAME> text variable or --set name=value). "geometry": no path even then.

The result is data: {"blocked": [...], "congestion": [...], "summary": [lines]} with the
value required and the value available for each binding gap, its layer, position and items.
It is deterministic (no seeds) and bounded by `deadline`. Lengths are mm.
"""
from __future__ import annotations

import math
import time

import numpy as np

from kae.board.kicad_file import load

from . import constraints as CN
from . import lastmile as LM
from . import rules as R
from .critical_grid import GridRouter
from .critical_space import Space

PENALTY = 60.0        # cells of detour one cell inside a real requirement costs in the relaxed search
SHORT = 0.001         # mm: what stays of every clearance in the relaxed search (overlap is a short)
WINDOWS = (1.0, 4.0, 12.0)
MAX_EXP = 1_000_000   # grid expansions per search of the width that fits (a search with no path
                      # explores its whole window)
RELAXED_W = 0.05      # mm: the track width of the relaxed search, and the narrowest width tried
FIT_RES = 0.02        # mm: grid of the search for the track width that fits
FIT_MARGIN = 1.0      # mm around the relaxed route: the window of that search
FIT_LADDER = ((0.8,), (0.15, 0.127, 0.1, 0.075, RELAXED_W))   # widths tried: shares of the rules'
                      # minimum, then common fab minimums (6, 5, 4, 3 mil)


# ----------------------------------------------------------------------------- relaxed search
class _Relaxed:
    """A context in which `sp` keeps only overlap: clearances SHORT, no keepouts, corridors
    or edge clearance (the outline itself stays)."""

    def __init__(self, sp):
        self.sp = sp
        self.on = False

    def __enter__(self):
        sp, real_need = self.sp, self.sp.need

        def need(it, net, kind, layer):
            v = real_need(it, net, kind, layer)
            if v is None or it.kind in ("keepout", "corridor"):
                return None
            return SHORT
        sp.need = need
        sp.edge_need = lambda net, kind, layer: 0.0
        sp.max_need = SHORT
        self.on = True
        return self

    def __exit__(self, *exc):
        for k in ("need", "edge_need"):
            self.sp.__dict__.pop(k, None)
        self.sp.max_need = self.sp._max_need()
        self.on = False


class _RelaxedRouter(GridRouter):
    """Grid search under _Relaxed where cells the real rules forbid (at the real width
    `self.w_real`) cost PENALTY each; vias only where the real rules allow them unless
    `self.free_vias`. No pulling of the path: it is evaluated as searched."""

    def __init__(self, sp, relax, **kw):
        super().__init__(sp, halo=0.0, pour_cost=0.0, **kw)
        self.relax = relax
        self.w_real = 0.2
        self.free_vias = False

    def _real(self, fn):
        self.relax.__exit__()
        try:
            return fn()
        finally:
            self.relax.__enter__()

    def cost_layer(self, grid, net, layer, w, layer_factor=1.0, skip=()):
        hard = self.blocked(grid, net, layer, w, "track", skip)
        real = self._real(lambda: self.blocked(grid, net, layer, self.w_real, "track", skip))
        c = np.full((grid.ny, grid.nx), float(layer_factor))
        c[real] += PENALTY * layer_factor
        c[hard] = np.inf
        return c

    def via_allowed(self, grid, net, layers_all):
        if self.free_vias:
            return super().via_allowed(grid, net, layers_all)
        return self._real(lambda: GridRouter.via_allowed(self, grid, net, layers_all))

    def _pull(self, net, layer, w, pts, tol=None):
        return pts


# ----------------------------------------------------------------------------- rule sources
def _source(rule):
    """(kind, where, override) for a rules.Constraint.rule name."""
    rule = rule or ""
    if "not checked on this board" in rule:
        return ("kae", "kae default ignored_clearance_floor (the board turns this check off)",
                "KAE_IGNORED_CLEARANCE_FLOOR / --set ignored_clearance_floor=")
    if rule.startswith("netclass '"):
        return ("board", f".kicad_pro net class {rule[len('netclass '):].split(' (')[0]}", None)
    if rule.startswith(("board setup", "board minimum")) or not rule:
        return ("board", ".kicad_pro board setup (design rules: constraints)", None)
    if rule.startswith(("local override", "local clearance")):
        return ("board", "footprint or pad local clearance (.kicad_pcb)", None)
    return ("board", f".kicad_dru rule '{rule.split(' (inside')[0]}'", None)


def _c(rb, ctype, a, b, layer):
    c = R.strictest(rb, ctype, a, b, layer)
    return (c.min or 0.0), c.rule


def _terms(sp, it, net, kind, layer, width):
    """[(value, constraint, kind, where, override)]: what makes up the requirement of
    `it` against a `kind` of `net` on `layer` (Space.need), largest first."""
    info, plan, rb = sp.info, sp.plan, sp.rb
    me = CN.net_item(info, net, kind, layer, width=width if kind == "track" else None)
    out = []
    if it == "edge":
        v, rule = _c(rb, "edge_clearance", me, CN.EDGE_ITEM, layer)
        out.append((v, "edge_clearance", *_source(rule)))
        if kind == "via" and (plan.notes.get("via_edge_band") or 0) > v:
            out.append((plan.notes["via_edge_band"], "edge_clearance", "board",
                        ".kicad_pro board setup or .kicad_dru (vias' edge clearance)", None))
        return sorted(out, key=lambda t: -t[0])
    k = it.kind
    if k == "corridor":
        out.append((0.0, "thermal_corridor", "kae",
                    f"kae thermal-spoke corridor of {it.owner} (constraints.thermal_corridors: keeps room for the "
                    f"board's min_resolved_spokes={sp.settings.get('min_resolved_spokes', 2)}; the board's "
                    f"starved_thermal severity 'ignore' turns it off)", None))
    elif k == "keepout":
        out.append((0.0, "keepout", "board", f"{it.owner or 'rule area'} (.kicad_pcb rule area)", None))
    elif k in ("track", "via"):
        other = CN.net_item(info, it.net, it.kind, layer, width=getattr(it, "width", None))
        v, rule = _c(rb, "clearance", me, other, layer)
        out.append((v, "clearance", *_source(rule)))
        if it.kind == "via" or kind == "via":
            v, rule = _c(rb, "hole_clearance", other if it.kind == "via" else me, me if it.kind == "via" else other,
                         layer)
            out.append((v - (it.width - it.drill) / 2 if it.kind == "via" else v, "hole_clearance", *_source(rule)))
    elif k in ("pad", "pad_nopin") and 0 <= it.idx < len(info.get("pads") or []):
        pad = info["pads"][it.idx]
        pi = CN.pad_item(info, pad)
        dsn, real = CN._pad_shapes(pad)
        e = CN._excess(real.get(layer), dsn)
        v, rule = _c(rb, "clearance", pi, me, layer)
        out.append((v + e, "clearance", *_source(rule)))
        ring = CN._ring(pad, dsn)
        if pad.get("hole") and ring is not None:
            v, rule = _c(rb, "hole_clearance", pi, me, layer)
            out.append((v - ring, "hole_clearance", *_source(rule)))
        side = "F" if layer == sp.cu[0] else ("B" if layer == sp.cu[-1] else None)
        mask_on = not CN._severity_ignored(sp.sev, "solder_mask_bridge") and not pad.get("allow_bridges")
        if mask_on and side and side in (pad.get("mask") or {}):
            m, m2c = pad["mask"][side], sp.settings.get("mask_to_copper", 0.0)
            out.append((m + m2c + e, "solder_mask", "board",
                        f"solder-mask opening of {pad.get('ref')}.{pad.get('number')}: margin {m:g} mm (pad, "
                        f"footprint or board setup solder_mask_margin) + mask-to-copper clearance {m2c:g} mm "
                        f"(.kicad_pro board setup); off with solder_mask_bridge severity 'ignore' or the footprint's "
                        f"'allow soldermask bridges'", None))
        if e > 1e-4:
            out.append((e, "pad_shape", "kae", f"pad {pad.get('ref')}.{pad.get('number')} copper beyond its DSN shape "
                                               f"({e:.3f} mm, --set pad_shapes=outside)", None))
    elif k == "hole":
        out.append((sp.need(it, net, kind, layer) or 0.0, "hole_clearance", "board",
                    f"{it.owner} (.kicad_pro board setup hole clearance, or a .kicad_dru rule)", None))
    elif k == "shape":
        why = str(it.owner or "")
        cons = "edge_clearance" if ("cut-out" in why or "edge" in why) else (
            "solder_mask" if "mask" in why else "clearance")
        out.append((sp.need(it, net, kind, layer) or 0.0, cons, "board", f"{why} (.kicad_pcb)", None))
    if not out:
        out.append((sp.need(it, net, kind, layer) or 0.0, "clearance", "board", str(getattr(it, "owner", "")), None))
    return sorted(out, key=lambda t: -t[0])


def _width_source(sp, net, layer):
    me = CN.net_item(sp.info, net, "track", layer, width=None)
    c = R.strictest(sp.rb, "track_width", me, None, layer)
    mt = sp.settings.get("min_track") or 0.0
    if c.rule.startswith(("netclass", "board")) and c.min is not None and abs(c.min - mt) < 1e-6:
        # a net class's track rule carries the board's minimum (rules.build): the board setup sets it
        return ("board", ".kicad_pro board setup minimum track width", None)
    return _source(c.rule)


def _desc(it):
    if it == "edge":
        return "board edge"
    if it.kind in ("pad", "pad_nopin"):
        return f"pad {it.owner[0]}.{it.owner[1]} ({it.net or 'no net'})"
    if it.kind in ("track", "via"):
        return f"{it.kind} of {it.net}"
    return f"{it.kind} {it.owner}"


def _bridging_openings(sp):
    """KiCad's solder-mask bridge rule where the router's model is looser: a mask opening that
    shuts a pad in, or that exposes pads of two nets (a solder jumper's), lets the pads' own
    nets in for the router (constraints._mask_openings), which then joins them at the price of
    bridge errors. Here every net keeps out of it (zero clearance), but the one net it exposes
    when there is only one."""
    from .critical_space import Item
    for layer, geo, why, nets in getattr(sp.plan, "bridging_openings", None) or []:
        if layer not in sp.items:
            continue
        it = Item("shape", nets[0] if len(nets) == 1 else None, [layer], geo, 0.0, CN._zero_class(sp.plan),
                  owner=f"{why} (exposes pads of {', '.join(n for n in nets if n) or 'no net'})")
        sp.items[layer].append(it)
    sp.invalidate()


# ----------------------------------------------------------------------------- one connection
def _gaps(sp, net, rt, w):
    """The real-rule violations of route `rt` at width `w`: [dict] per track piece or via,
    narrowest (largest deficit) first."""
    out = []
    for l, a, b in rt.segs:
        vs = [v for v in sp.track_violations(net, l, w, a, b) if v[0] == "edge" or v[0].net != net]
        if vs:
            worst = max(vs, key=lambda v: v[2] - v[1])
            out.append(dict(kind="track", layer=l, a=a, b=b, w=w, vs=vs, deficit=worst[2] - worst[1], worst=worst))
    for (x, y) in rt.vias:
        vs = sp.via_violations(net, x, y)
        if vs:
            worst = max(vs, key=lambda v: v[2] - v[1])
            out.append(dict(kind="via", layer=None, a=(x, y), b=(x, y), vs=vs, deficit=worst[2] - worst[1],
                            worst=worst))
    return sorted(out, key=lambda g: -g["deficit"])


def _at(g):
    it = g["worst"][0]
    from shapely.geometry import LineString, Point
    seg = Point(g["a"]) if g["a"] == g["b"] else LineString([g["a"], g["b"]])
    if it == "edge":
        p = seg.interpolate(0.5, normalized=True)
    else:
        from shapely.ops import nearest_points
        p = nearest_points(seg, it.geom)[0]
    return [round(p.x, 3), round(p.y, 3)]


def _explain(sp, net, g, wmin, fit=None):
    """The binding constraint of gap `g`: dict(constraint, required, available, ...)."""
    it, d, nd = g["worst"]
    layer = g["layer"] or sp.cu[0]
    if g["kind"] == "via":
        D, drill = sp.via_size(net)
        terms = _terms(sp, it, net, "via", layer, None)
        top = terms[0]
        return dict(constraint=top[1], required=round(nd, 4), available=round(d, 4), via=[D, drill],
                    fits_via=round(D - 2 * (nd - d), 4), source=top[2], where=top[3], override=top[4],
                    against=_desc(it), layer=layer, at=_at(g))
    terms = _terms(sp, it, net, "track", layer, g["w"])
    top = terms[0]
    rec = dict(constraint=top[1], required=round(nd, 4), available=round(d, 4), track=round(g["w"], 4),
               source=top[2], where=top[3], override=top[4],
               against=_desc(it), layer=layer, at=_at(g))
    if top[1] in ("keepout", "thermal_corridor"):
        rec["available"] = round(min(0.0, d), 4)
    if fit:
        # the rules' track width is what binds: the real search joins it with a `fit` track
        ks, kw, ko = _width_source(sp, net, layer)
        rec.update(constraint="track_width", required=round(g["w"], 4), available=round(fit, 4),
                   clearance=dict(required=round(nd, 4), available=round(d, 4), where=top[3]),
                   source=ks, where=kw, override=ko)
    return rec


def _line(net, pads, cause, b):
    who = (",".join(pads) or "copper") + f" {net}"
    if cause == "congestion":
        return f"{who}: congestion, a path exists without our other copper (not a rule)"
    if cause == "fixed copper":
        return f"{who}: blocked by the input's own copper of {b}"
    if cause == "geometry":
        return (f"{who}: no path even with every clearance at zero, walled in by "
                f"{'; '.join(b or []) or 'copper or the outline'}")
    at = f" at ({b['at'][0]:.2f}, {b['at'][1]:.2f}) {b['layer']}"
    src = b["where"] + (f"; override {b['override']}" if b.get("override") else "")
    if b["constraint"] == "track_width":
        return (f"{who}: needs a {b['available']:.3f} mm track{at}, minimum track width {b['required']:.3f} mm "
                f"({src}); relax to {math.floor(b['available'] * 1000) / 1000:.3f} to allow")
    if b["constraint"] in ("keepout", "thermal_corridor"):
        return f"{who}: crosses a {b['constraint'].replace('_', ' ')}{at} ({src})"
    if "fits_via" in b:
        size = f"a {b['via'][0]:.3f}/{b['via'][1]:.3f} mm via"
        alt = f"; a {b['fits_via']:.3f} mm via would fit" if b["fits_via"] > 0 else ""
    else:
        size = f"a {b['track']:.3f} mm track"
        alt = ""
    return (f"{who}: {b['constraint'].replace('_', ' ')} to {b['against']}{at}: needs {b['required']:.3f} mm, "
            f"{b['available']:.3f} mm available with {size} ({src}){alt}")


# ----------------------------------------------------------------------------- the board
def diagnose(board, info, plan, fills, report, sev=None, input_ids=(), deadline=None, log=print, max_conns=60):
    """Diagnose the open connections of `board` (see the module docstring). `board`: the
    final board with its project files beside it (drc.stage_board), `fills` its refilled
    zones (pcbnew_io.zone_fills()["zones"]), `report` its KiCad DRC report, `input_ids` the
    uuids of the input's tracks and vias (pre-routes: not ours to take out)."""
    t0 = time.monotonic()
    b = load(board)
    sp = Space(b, info, plan=plan, sev=sev or {})
    _bridging_openings(sp)
    relax = _Relaxed(sp)
    gr = GridRouter(sp)          # the last mile's search: a smaller bound blamed rules for congestion
    rgr = _RelaxedRouter(sp, relax)
    fp = LM._fill_polys(fills)
    input_ids = set(input_ids)
    known = sorted({it.net for it in sp.pads if it.net and it.kind == "pad"})
    by_shown = {LM.unescape(n): n for n in known}
    nets = [n if n in known else by_shown.get(n, n) for n in LM.open_nets(report)]
    out = dict(blocked=[], congestion=[], summary=[], undiagnosed=0)
    n = 0
    for net in nets:
        ps = [p for p in LM.parts(sp, fp, net) if LM._relevant(p)]
        widths = LM.widths_of(sp, net)
        wmin = min(widths)
        for k in range(len(ps) - 1, 0, -1):
            if n >= max_conns or (deadline is not None and time.monotonic() > deadline):
                out["undiagnosed"] += 1
                continue
            n += 1
            small, others = ps[k], ps[:k] + ps[k + 1:]
            src = LM._anchors(small, max(widths) / 2 + 0.02)
            pads = [f"{x.item.owner[0]}.{x.item.owner[1]}" for x in small if x.kind == "pad"][:4]
            rec = dict(net=net, pads=pads, kinds=sorted({x.kind for x in small}))
            if not src:
                continue
            rec["cause"], b_ = _one(sp, gr, rgr, relax, net, src, others, widths, wmin, input_ids)
            if rec["cause"] in ("rule", "kae default"):
                rec["binding"] = b_
            elif rec["cause"] == "fixed copper":
                rec["fixed_nets"] = b_
            elif rec["cause"] == "geometry":
                rec["walled_by"] = b_
            rec["line"] = _line(net, pads, "rule" if rec["cause"] == "kae default" else rec["cause"],
                                ", ".join(b_) if rec["cause"] == "fixed copper" else b_)
            (out["congestion"] if rec["cause"] == "congestion" else out["blocked"]).append(rec)
            log("blocked: " + rec["line"])
    out["summary"] = [r["line"] for r in out["blocked"]]
    out["seconds"] = round(time.monotonic() - t0, 1)
    return out


def _enclosing(sp, net, src, w):
    """What touches the part's copper (within a track width): the items that wall it in."""
    out = []
    for a in src:
        for l in a.layers:
            for it in sp.query(l, a.geom.bounds, w):
                if it.kind in ("pad", "track", "via", "shape", "hole", "keepout") and it.net != net and \
                        it.geom.distance(a.geom) - it.r < w and not any(o.startswith(_desc(it)) for o in out):
                    out.append(f"{_desc(it)} on {l}" + (f" (touches {_anchor_desc(sp, a)})" if a.kind == "pad" else ""))
    return out[:6]


def _anchor_desc(sp, a):
    for it in sp.pads:
        if it.geom is a.geom:
            return f"{it.owner[0]}.{it.owner[1]}"
    return "the pad"


def _relaxed_route(sp, rgr, relax, net, src, others, wmin):
    """(route, window margin) of the cheapest path under _Relaxed, or (None, None)."""
    rgr.w_real = wmin
    try:
        with relax:
            for free in (False, True):
                # last: vias anywhere the relaxed rules allow, in the pad too (the last mile
                # tries a via in the pad when nothing else joins)
                rgr.free_vias = sp.via_in_pad = free
                for m in WINDOWS:
                    win = LM._window(src, others, m)
                    dst = [a for p in others for a in LM._anchors(p, wmin / 2 + 0.02, clip=win)]
                    if not dst:
                        continue
                    grid = rgr.window([LM.Anchor(win, tuple(sp.cu))], margin=0.0)
                    rt = rgr.connect(net, src, dst, min(wmin, RELAXED_W), sp.cu, via=len(sp.cu) > 1, window=grid)
                    if rt is not None:
                        return rt, m
    finally:
        sp.via_in_pad = False
    return None, None


def _width_fit(sp, net, src, others, wmin, rt):
    """The widest track of FIT_LADDER (below the rules' minimum `wmin`) that the real rules let
    through, every clearance as it is, near the relaxed route `rt` (its box grown by
    FIT_MARGIN), or None when not even the narrowest fits."""
    from shapely.geometry import box
    pts = [p for _, a, b in rt.segs for p in (a, b)] + list(rt.vias)
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    win = box(min(xs) - FIT_MARGIN, min(ys) - FIT_MARGIN, max(xs) + FIT_MARGIN, max(ys) + FIT_MARGIN)
    dst = [a for p in others for a in LM._anchors(p, wmin / 2 + 0.02, clip=win)]
    if not dst:
        return None
    gr = GridRouter(sp, res=FIT_RES, max_exp=MAX_EXP)     # a fine grid: the slivers between fine-pitch pins
    grid = gr.window([LM.Anchor(win, tuple(sp.cu))], margin=0.0)

    def ok(w):
        return gr.connect(net, src, dst, w, sp.cu, via=len(sp.cu) > 1, window=grid) is not None
    ladder = sorted({round(f * wmin, 3) for f in FIT_LADDER[0]} | set(FIT_LADDER[1]), reverse=True)
    ladder = [w for w in ladder if w < wmin - 1e-6]
    if not ladder or not ok(ladder[-1]):
        return None
    for w in ladder[:-1]:
        if ok(w):
            return w
    return ladder[-1]


def _route(gr, sp, net, src, others, widths):
    for m in WINDOWS:
        got = LM._try(gr, sp, net, src, others, LM._window(src, others, m), widths)
        if got:
            sp.remove(got[1])
            return got[0]
    return None


def _one(sp, gr, rgr, relax, net, src, others, widths, wmin, input_ids):
    """(cause, detail) for one missing connection."""
    foreign = [it for it in sp.existing if it.kind in ("track", "via") and it.net != net]
    ours = [it for it in foreign if it.uuid not in input_ids]
    theirs = [it for it in foreign if it.uuid in input_ids]
    sp.remove(ours)
    try:
        if _route(gr, sp, net, src, others, widths) is not None:
            return "congestion", None
        if theirs:
            sp.remove(theirs)
            try:
                rt = _route(gr, sp, net, src, others, widths)
            finally:
                LM._restore(sp, theirs)
            if rt is not None:
                from shapely.geometry import LineString
                hit = sorted({it.net for it in theirs for l, a, b in rt.segs if l in it.layers and
                              it.geom.distance(LineString([a, b])) < it.r + rt.width / 2 + sp.max_need})
                return "fixed copper", hit or ["pre-routes"]
        # the rules: the cheapest path with only overlap hard, then its narrowest real gap
        sp.remove(theirs)
        try:
            rt, m = _relaxed_route(sp, rgr, relax, net, src, others, wmin)
            if rt is None:
                win = LM._window(src, others, WINDOWS[-1])
                ends = [a for p in others for a in LM._anchors(p, wmin / 2 + 0.02, clip=win) if a.kind == "pad"]
                return "geometry", _enclosing(sp, net, src, wmin) or _enclosing(sp, net, ends, wmin)
            gaps = _gaps(sp, net, rt, wmin)
            if not gaps:
                # the relaxed path is legal as it stands (the real search missed it on its grid)
                return "congestion", None
            g = gaps[0]
            fit = None
            if g["kind"] == "track" and (g["worst"][0] == "edge" or g["worst"][0].kind not in ("keepout", "corridor")):
                fit = _width_fit(sp, net, src, others, wmin, rt)
            b = _explain(sp, net, g, wmin, fit)
        finally:
            LM._restore(sp, theirs)
        b["path"] = dict(length=round(rt.length, 2), vias=len(rt.vias), gaps=len(gaps))
        b["others"] = [dict(constraint=_terms(sp, x["worst"][0], net, x["kind"], x["layer"] or sp.cu[0],
                                              x.get("w"))[0][1], against=_desc(x["worst"][0]),
                            required=round(x["worst"][2], 4), available=round(x["worst"][1], 4))
                       for x in gaps[1:4]]
        return ("kae default" if b["source"] == "kae" else "rule"), b
    finally:
        LM._restore(sp, ours)


# ----------------------------------------------------------------------------- command line
def main(argv=None):
    """python -m kae.route.blocked ROUTED INPUT [--drc REPORT.json[.gz]] [--out FILE] [--time S]

    ROUTED: the routed board; INPUT: the task's input board, with its project files beside it
    (their rules decide). Without --drc, kicad-cli's DRC runs on ROUTED. Prints one line per
    blocked connection and writes the JSON to --out."""
    import argparse
    import gzip
    import json
    import shutil
    import tempfile
    from pathlib import Path

    from kae.board import pcbnew_io

    from . import bridge, drc
    ap = argparse.ArgumentParser(prog="kae.route.blocked")
    ap.add_argument("routed")
    ap.add_argument("input")
    ap.add_argument("--drc")
    ap.add_argument("--out")
    ap.add_argument("--time", type=float, default=120.0)
    a = ap.parse_args(argv)
    wd = Path(tempfile.mkdtemp(prefix="kae-blocked-"))
    try:
        src = Path(a.routed)
        if src.suffix == ".gz":
            with gzip.open(src, "rb") as f, open(wd / "routed.kicad_pcb", "wb") as g:
                shutil.copyfileobj(f, g)
            src = wd / "routed.kicad_pcb"
        staged = drc.stage_board(src, a.input, wd / "b")
        if a.drc:
            op = gzip.open if a.drc.endswith(".gz") else open
            with op(a.drc, "rt") as f:
                rep = json.load(f)
        else:
            rep = drc.run(staged, wd / "drc.json")
        info = pcbnew_io.export_dsn(a.input, wd / "k.dsn")
        opts = dict(bridge.DEFAULT_OPTS, severities=bridge.severities(a.input))
        plan = constraints_plan(info, a.input, opts)
        fills = pcbnew_io.zone_fills(staged)["zones"]
        inb = load(a.input)
        ids = {t.uuid for t in inb.tracks} | {v.uuid for v in inb.vias}
        res = diagnose(staged, info, plan, fills, rep, sev=opts["severities"], input_ids=ids,
                       deadline=time.monotonic() + a.time, log=lambda m: None)
        for line in res["summary"]:
            print(line)
        print(f"{len(res['blocked'])} blocked, {len(res['congestion'])} congestion, "
              f"{res['undiagnosed']} not diagnosed ({res['seconds']} s)")
        if a.out:
            Path(a.out).write_text(json.dumps(res, indent=1, default=str))
    finally:
        shutil.rmtree(wd, ignore_errors=True)


def constraints_plan(info, board_path, opts):
    from .bridge import plane_policy
    p = CN.plan(info, board_path, opts)
    p.plane_policy = plane_policy(opts)
    p.plane_cost = opts.get("plane_cost")
    p.pad_shapes = opts.get("pad_shapes") or "kicad"
    return p


if __name__ == "__main__":
    main()
