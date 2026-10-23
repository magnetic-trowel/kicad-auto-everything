# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Modules and their critical copper.

A module is a physics structure of the brief (Contract 2) with its parts and the copper
that decides its physics:

| kind | copper | objective |
|---|---|---|
| cell (commutation_cell) | each board hop of the loop, on the layer nearest the reference plane; return vias at both ground terminals | loop L: hops as wide as the terminals (wider does not help, power-copper section 2), never narrower than the current needs; the switch-node hop only as wide as the current needs; return vias at the sites that minimize L |
| decap | capacitor rail pad -> IC power pin; capacitor ground pad and IC ground pin -> vias into the ground plane (or a ground track to the IC pin without a plane) | decoupling-loop L |
| crystal | XIN/XOUT: IC pin -> crystal pad, load capacitors on the shortest stubs, their ground pads into the plane | trace capacitance (pulling, ppm) |
| chain (protected connector pin) | connector pin -> protector pad -> next part, in that order; the protector's ground into the plane | surge-path L ahead of the protector |

Every hop is a GridRouter.connect call (exact KiCad clearances); via sites are quoted
with the routed-loop model (critical_physics.Loop) and the best kept. A module's physics is
quoted as spend / allocation (u) with the place terms' allocations (kae.physics.priors, or
the Terms structure of the same id when one is given).
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

import numpy as np
from shapely.geometry import Point

from kae.physics import priors as PR
from kae.physics.boardview import body_z

from .critical_grid import Anchor
from .critical_physics import INF, Loop, ipc2221_width, trace_capacitance_pf
from kae.physics.kernels import lprime_hj

GND_RE = re.compile(r'(^|[^A-Z])(A|D|P|S|C)?GND|^/?VSS|^0V$|GROUND|EARTH', re.I)


# ----------------------------------------------------------------------------- module
@dataclass
class Module:
    id: str
    kind: str                     # cell | decap | crystal | chain
    spec: dict
    parts: list                   # footprint uuids
    priority: float = 0.0
    confidence: float = 0.5
    copper: list = field(default_factory=list)      # committed Items
    hops: dict = field(default_factory=dict)        # hop key -> Route (or None when it failed)
    vias: dict = field(default_factory=dict)        # terminal key -> [(x, y, stub width)]
    physics: dict = field(default_factory=dict)     # value, unit, alloc, u, ...
    status: str = "pending"
    notes: list = field(default_factory=list)


def modules_from_brief(brief, kinds=("cell", "decap", "crystal", "chain")):
    """Modules in the brief's placement order (physically decisive first)."""
    kmap = {"commutation_cell": "cell", "decap": "decap", "crystal": "crystal", "connector_chain": "chain"}
    out = []
    for s in brief.get("structures") or []:
        k = kmap.get(s.get("kind"))
        if k is None or k not in kinds:
            continue
        if k == "chain" and not s.get("protection"):
            continue
        parts = list((s.get("members_ref") or {}).keys())
        out.append(Module(id=s.get("id") or f"{k}:{len(out)}", kind=k, spec=s, parts=parts,
                          priority=float(s.get("priority") or 0.0), confidence=float(s.get("confidence") or 0.5)))
    out.sort(key=lambda m: (-m.priority, m.id))
    return out


# ----------------------------------------------------------------------------- context
class Ctx:
    """What module routing needs: the Space, a GridRouter, the brief and board, options."""

    def __init__(self, space, router, brief, board, opts=None, terms=None):
        self.sp, self.gr, self.brief, self.board = space, router, brief, board
        self.opts = dict(opts or {})
        self.terms = terms
        self.nets = brief.get("nets") or {}
        self.parts = brief.get("parts") or {}
        gnd = {n for n, r in self.nets.items() if (r or {}).get("role") == "ground"}
        if not gnd:
            gnd = {n for n in board.nets if GND_RE.search(n.split("/")[-1] or n)}
        self.gnd = gnd
        self.fp = {f.uuid: f for f in board.footprints}
        self.log = self.opts.get("log") or (lambda *a: None)

    # ---- parts and terminals
    def side_layer(self, fp_uuid):
        f = self.fp.get(fp_uuid)
        return self.sp.cu[-1] if f is not None and f.side == "B" else self.sp.cu[0]

    def term(self, member, layers=None):
        if not member:
            return None
        pads = member[1] if len(member) > 1 else None
        if pads is None:
            return None
        return self.sp.terminal(member[0], pads, layers)

    def pad_term(self, fp_uuid, net=None, number=None):
        """Terminal of a footprint's pad on `net` (the first one) or with `number`."""
        f = self.fp.get(fp_uuid)
        if f is None:
            return None
        if number is not None:
            return self.sp.terminal(fp_uuid, [number])
        for p in f.pads:
            if p.net == net:
                return self.sp.terminal(fp_uuid, [p.number])
        return None

    def zb(self, fp_uuid):
        f = self.fp.get(fp_uuid)
        return body_z(f.lib_id, f.value) if f is not None else 0.5

    def npins(self, fp_uuid):
        f = self.fp.get(fp_uuid)
        return len(f.pads) if f is not None else 2

    def volts(self, net):
        r = self.nets.get(net) or {}
        v = r.get("volts")
        if v:
            return abs(float(v))
        s = (net or "").split("/")[-1].upper().replace("_", "")
        m = re.search(r"(\d+)V(\d+)", s)
        if m:
            return float(f"{m.group(1)}.{m.group(2)}")
        m = re.search(r"(\d+(?:\.\d+)?)V", s)
        return float(m.group(1)) if m else None

    # ---- planes
    def plane(self, layer, x, y, gnd=True):
        """(h, plane layer, plane net) under copper on `layer` at (x, y): the nearest ground
        plane (gnd=True; the return path), else the nearest plane of any net."""
        if gnd:
            h, pl, pn = self.sp.plane_below(layer, x, y, nets=self.gnd)
            if pl is not None:
                return h, pl, pn
        return self.sp.plane_below(layer, x, y)

    def h(self, layer, plane_layer):
        if plane_layer is None:
            return INF
        return abs(self.sp.z[layer] - self.sp.z[plane_layer])

    # ---- copper
    def commit(self, m, rt, tag):
        items = []
        for l, a, b in rt.segs:
            items.append(self.sp.add_track(rt.net, l, rt.width, a, b, owner=(m.id, tag)))
        for (x, y) in rt.vias:
            items.append(self.sp.add_via(rt.net, x, y, owner=(m.id, tag)))
        m.copper += items
        return items

    def commit_via(self, m, net, layer, c, v, ws, tag):
        items = []
        if math.dist(c, v) > 1e-6:
            items.append(self.sp.add_track(net, layer, ws, c, v, owner=(m.id, tag)))
        items.append(self.sp.add_via(net, v[0], v[1], owner=(m.id, tag)))
        m.copper += items
        return items

    def net_copper_anchors(self, net, exclude_owner=None, connected_to=None):
        """Anchors for the committed copper of `net` (tracks, vias); with `connected_to` (a
        Terminal), only the copper connected to it (pads included)."""
        out = []
        if connected_to is not None:
            comp = self.sp.component(net, [(connected_to.geom, connected_to.layers)])
            pool = [it for it in comp if it.kind in ("track", "via", "pad")]
        else:
            pool = [it for it in self.sp.routed + self.sp.existing if it.net == net]
        for it in pool:
            if exclude_owner is not None and it.owner and it.owner[0] == exclude_owner:
                continue
            if it.kind == "track":
                out.append(Anchor(it.geom, tuple(it.layers), None, grow=it.r * 0.8, kind="track"))
            elif it.kind == "via":
                out.append(Anchor(it.geom, tuple(self.sp.cu), (it.geom.x, it.geom.y), grow=it.r * 0.8, kind="via"))
            elif it.kind == "pad" and connected_to is not None:
                out.append(Anchor(it.geom, tuple(it.layers), it.pos, kind="pad"))
        return out

    def connected(self, net, ta, tb):
        """Whether terminals ta and tb are already joined by committed copper."""
        comp = self.sp.component(net, [(ta.geom, ta.layers)])
        ids = {id(it) for it in comp}
        return any(id(it) in ids for it in tb.items)


# ----------------------------------------------------------------------------- geometry helpers
def extent_across(geom, ux, uy):
    """Width of `geom` across the unit direction (ux, uy)."""
    nx, ny = -uy, ux
    pts = _coords(geom)
    p = pts[:, 0] * nx + pts[:, 1] * ny
    return float(p.max() - p.min())


def support(geom, cx, cy, ux, uy):
    """How far `geom` reaches from (cx, cy) along the unit direction (ux, uy)."""
    pts = _coords(geom)
    return float(((pts[:, 0] - cx) * ux + (pts[:, 1] - cy) * uy).max())


def _coords(g):
    if hasattr(g, "geoms"):
        return np.vstack([_coords(x) for x in g.geoms])
    if g.geom_type == "Polygon":
        return np.asarray(g.exterior.coords)
    return np.asarray(g.coords)


def _on(t, layer):
    """A terminal's copper on `layer` (all of it for objects without per-layer copper)."""
    return t.geom_on(layer) if hasattr(t, "geom_on") else t.geom


def _centre_on(t, layer):
    """Where a stub of `layer` starts on terminal t: its centre when its copper on that
    layer holds it."""
    return t.centre_on(layer) if hasattr(t, "centre_on") else (t.x, t.y)


def anchor(t):
    """A terminal as a routing anchor: its copper per layer, and a point of it on each layer
    where a track may end (a castellated pad's SMD twin is not on the back)."""
    by = getattr(t, "by_layer", None) or None
    centres = {l: t.centre_on(l) for l in t.layers} if by else None
    return Anchor(t.geom, t.layers, (t.x, t.y), by_layer=by, centres=centres)


def width_ladder(w_hi, w_lo, n=5):
    """Widths from w_hi down to w_lo (geometric), deduplicated to whole micrometres."""
    w_hi = max(w_hi, w_lo)
    out = []
    for k in range(n):
        f = k / max(1, n - 1)
        w = w_hi * (w_lo / w_hi) ** f
        w = math.ceil(w * 1000 - 1e-6) / 1000
        if not out or abs(out[-1] - w) > 1e-6:
            out.append(w)
    return out


def route_pts(rt, start=None):
    """The polyline of a single-layer route, oriented from `start` when given."""
    if rt is None or not rt.segs:
        return []
    pts = [rt.segs[0][1]]
    for _, a, b in rt.segs:
        if math.dist(pts[-1], a) > 1e-6:
            pts.append(a)
        pts.append(b)
    if start is not None and math.dist(pts[-1], start) < math.dist(pts[0], start):
        pts = pts[::-1]
    return pts


def hop_layers(ctx, ta, tb, prefer=None):
    """Copper layers a hop between two terminals can run on, best first: common pad layers,
    the one with the nearest reference plane first (ties: the parts' side)."""
    common = [l for l in ctx.sp.cu if l in ta.layers and l in tb.layers]
    if not common:
        return []
    mx, my = (ta.x + tb.x) / 2, (ta.y + tb.y) / 2

    def key(l):
        h, _, _ = ctx.plane(l, mx, my, gnd=False)
        return (0 if l == prefer else 1, h if h != INF else 1e9, ctx.sp.cu.index(l))
    outer = [l for l in common if l in (ctx.sp.cu[0], ctx.sp.cu[-1])] or common
    return sorted(outer, key=key)


def _escape_gap(ctx, net, w, pad, layer):
    """How far a track of `net` (width w) keeps its centre from `pad` so that one track of
    the pad's net still passes between them: half its width, the escape track at its
    minimum width, and the clearance on both sides of it."""
    sp = ctx.sp
    w_p = sp.width_limits(pad.net, layer)[1]
    c = sp._pair(net, pad.net, layer)
    cc = c.track_track if c is not None else sp.max_need
    return w / 2.0 + w_p + 2.0 * cc + 0.05


def route_hop(ctx, m, tag, net, sources, targets, widths, layers, via=False, via_cost=None, layer_factor=None,
              max_len=None, optional=False):
    """Try each width (widest first) on the given layers; commit and return the first route
    (none longer than `max_len`) that walls off no other net's pin (GridRouter.boxes_in). A
    route that does is retried with a keep-out around those pins; when no width avoids it,
    the first such route is kept, unless the hop is `optional` (the plane or the general
    router can carry it): then nothing is."""
    fallback = None
    for w in widths:
        w = ctx.sp.clamp_width(net, layers[0], w)
        avoid = []
        for _ in range(3):
            rt = ctx.gr.connect(net, sources, targets, w, layers, via=via, via_cost=via_cost,
                                layer_factor=layer_factor, max_len=max_len, avoid=avoid)
            if rt is None:
                break
            boxed = ctx.gr.boxes_in(rt) if ctx.opts.get("keep_escapes", True) else []
            if not boxed:
                if rt.segs or rt.vias:
                    ctx.commit(m, rt, tag)
                m.hops[tag] = rt
                return rt
            fallback = fallback or rt
            avoid = avoid + [(it.geom, _escape_gap(ctx, net, w, it, l), l) for it, l in boxed]
    if fallback is not None and optional:
        m.notes.append(f"{tag}: every route walls off a pin of another net; left out")
        m.hops[tag] = None
        return None
    if fallback is not None:
        m.notes.append(f"{tag}: walls off a pin of another net (no alternative)")
        if fallback.segs or fallback.vias:
            ctx.commit(m, fallback, tag)
        m.hops[tag] = fallback
        return fallback
    m.hops[tag] = None
    return None


# ----------------------------------------------------------------------------- vias into a plane
def via_candidates(ctx, t, layer, net, plane_layer, toward=None, n_dirs=24, gaps=(0.0, 0.1, 0.25, 0.5),
                   in_pad=False, max_n=10):
    """Legal sites for a via of `net` beside terminal t (stub on `layer`) that land inside
    a zone of `net` on `plane_layer`: [(x, y, stub width, distance to `toward`)]."""
    sp = ctx.sp
    D, d = sp.via_size(net)
    rv = D / 2.0
    tg = _on(t, layer)                       # the pad's copper on the stub's layer
    c = _centre_on(t, layer)
    out = []
    zone_margin = rv + 0.15
    for k in range(n_dirs):
        th = 2 * math.pi * k / n_dirs
        ux, uy = math.cos(th), math.sin(th)
        s = support(tg, c[0], c[1], ux, uy)
        for g in gaps:
            r = s + rv + g
            v = (c[0] + r * ux, c[1] + r * uy)
            if plane_layer is not None and not sp.zone_covers(net, plane_layer, v[0], v[1], margin=zone_margin):
                continue
            if sp.via_violations(net, v[0], v[1], first=True):
                continue
            ws = sp.clamp_width(net, layer, min(D, max(extent_across(tg, ux, uy), 0.1)))
            if sp.track_violations(net, layer, ws, c, v, first=True):
                ws2 = sp.clamp_width(net, layer, sp.width_limits(net, layer)[1])
                if ws2 >= ws or sp.track_violations(net, layer, ws2, c, v, first=True):
                    continue
                ws = ws2
            dist = math.dist(v, toward) if toward is not None else 0.0
            out.append((v[0], v[1], ws, dist))
            break
    if in_pad:
        # vias inside a large pad (exposed thermal pads): a grid over the pad shrunk by the via radius
        inner = tg.buffer(-rv - 0.05)
        if not inner.is_empty:
            x0, y0, x1, y1 = inner.bounds
            step = max(D + (sp.settings.get("hole_to_hole") or 0.25), 1.0)
            xs = np.arange(x0, x1 + 1e-9, step) if x1 - x0 > step else [0.5 * (x0 + x1)]
            ys = np.arange(y0, y1 + 1e-9, step) if y1 - y0 > step else [0.5 * (y0 + y1)]
            saved = sp.via_in_pad
            sp.via_in_pad = True
            try:
                for x in xs:
                    for y in ys:
                        if not inner.contains(Point(x, y)):
                            continue
                        if plane_layer is not None and not sp.zone_covers(net, plane_layer, x, y, margin=zone_margin):
                            continue
                        if sp.via_violations(net, x, y, first=True):
                            continue
                        dist = math.dist((x, y), toward) if toward is not None else 0.0
                        out.append((float(x), float(y), 0.0, dist))
            finally:
                sp.via_in_pad = saved
    out.sort(key=lambda v: v[3])
    return out[:max_n]


def _plane_ok(ctx, net, layer):
    """Whether `net` has a zone on `layer`."""
    return any(l == layer for l, _ in ctx.sp.zones_of(net))


# ----------------------------------------------------------------------------- cells
def _hop_net(ta, tb):
    return ta.net if ta.net == tb.net else None


def route_cell(ctx, m):
    s = m.spec
    loop = s.get("loop") or []
    T = [ctx.term(mem) for mem in loop]
    if len(T) < 3 or any(t is None for t in T):
        m.status = "skipped"
        m.notes.append("loop terminals not found")
        return m
    n = len(T)
    ex = s.get("excite") or {}
    I = float(ex.get("I") or 1.0)
    sw = s.get("sw")
    m.spec["_T"] = T
    side = ctx.side_layer(T[0].fp)
    hops = []
    for k in range(n):
        ta, tb = T[k], T[(k + 1) % n]
        if ta.fp == tb.fp:
            continue
        net = _hop_net(ta, tb)
        if net is None:
            m.notes.append(f"hop {k}: nets differ ({ta.net} / {tb.net})")
            continue
        hops.append((k, ta, tb, net))
    # forward hops first, the ground hop last (its return may also go through the plane)
    hops.sort(key=lambda h: (h[3] in ctx.gnd, h[0]))
    ok = 0
    for k, ta, tb, net in hops:
        layers = hop_layers(ctx, ta, tb, prefer=side)
        if not layers:
            m.notes.append(f"hop {k}: no common copper layer")
            continue
        L0 = layers[0]
        ux, uy = tb.x - ta.x, tb.y - ta.y
        d = math.hypot(ux, uy) or 1.0
        ux, uy = ux / d, uy / d
        a = min(extent_across(ta.geom, ux, uy), extent_across(tb.geom, ux, uy))
        w_cur = ipc2221_width(I, t_mm=ctx.sp.tcu.get(L0, 0.035))
        mn, opt, mx = ctx.sp.width_limits(net, L0)
        floor = max(mn, min(w_cur, a), 0.0)
        if net == sw:
            hi = max(w_cur, opt)            # the switch node: as narrow as the current allows
        else:
            hi = max(a, w_cur, opt)         # terminal width (wider gains nothing)
        widths = width_ladder(hi, max(floor, mn), 5) + ([opt] if opt < floor else []) + [mn]
        widths = sorted(set(round(w, 4) for w in widths), reverse=True)
        # a ground hop over its own plane has the vias as its return: a detour on the surface
        # buys nothing, so it is routed only when it stays short
        max_len = None
        if net in ctx.gnd:
            h_, pl_, pn_ = ctx.plane(L0, (ta.x + tb.x) / 2, (ta.y + tb.y) / 2, gnd=True)
            if pl_ is not None and pn_ == net:
                max_len = 1.5 * d + 1.0
        rt = route_hop(ctx, m, f"hop{k}", net, [anchor(ta)], [anchor(tb)], widths, [L0], via=False, max_len=max_len,
                       optional=max_len is not None)
        if rt is None and max_len is not None:
            m.notes.append(f"hop {k} ({net}): returns through the plane")
            continue
        if rt is None and len(ctx.sp.cu) > 1:
            outer = [ctx.sp.cu[0], ctx.sp.cu[-1]]
            rt = route_hop(ctx, m, f"hop{k}", net, [anchor(ta)], [anchor(tb)], widths[-3:], outer, via=True,
                           via_cost=4.0)
        if rt is not None:
            ok += 1
        else:
            m.notes.append(f"hop {k} ({net}) not routed")
    # return vias at the ground terminals of the loop
    _return_vias(ctx, m, T, side)
    m.status = "routed" if ok == len(hops) else ("partial" if ok else "failed")
    quote(ctx, m)
    return m


def _ground_hop(ctx, T):
    n = len(T)
    for k in range(n):
        ta, tb = T[k], T[(k + 1) % n]
        if ta.fp != tb.fp and ta.net == tb.net and ta.net in ctx.gnd:
            return k
    return None


def _return_vias(ctx, m, T, side, max_pairs=None):
    """Vias at both ground terminals of the loop into the ground plane, at the sites that
    minimize the routed loop inductance (greedy, pairs first, then single additions)."""
    k = _ground_hop(ctx, T)
    if k is None:
        return
    ta, tb = T[k], T[(k + 1) % len(T)]
    net = ta.net
    cx = sum(t.x for t in T) / len(T)
    cy = sum(t.y for t in T) / len(T)
    layer = side if side in ta.layers else ta.layers[0]
    h, pl, pn = ctx.plane(layer, cx, cy, gnd=True)
    if pl is None or pn != net:
        return
    I = float((m.spec.get("excite") or {}).get("I") or 1.0)
    n_max = max_pairs or int(min(4, max(2, math.ceil(I))))
    ca = via_candidates(ctx, ta, layer, net, pl, toward=(tb.x, tb.y), in_pad=_is_thermal_pad(ta))
    cb = via_candidates(ctx, tb, layer, net, pl, toward=(ta.x, ta.y), in_pad=_is_thermal_pad(tb))
    if not ca or not cb:
        m.notes.append("no legal return-via site")
        return
    key_a, key_b = f"via:{ta.fp}:{ta.pad}", f"via:{tb.fp}:{tb.pad}"
    m.vias.setdefault(key_a, [])
    m.vias.setdefault(key_b, [])
    base = quote(ctx, m, store=False)
    best = None
    for va in ca[:6]:
        for vb in cb[:6]:
            if math.dist(va[:2], vb[:2]) < ctx.sp.same_net_via_pitch(net):
                continue
            m.vias[key_a] = [va]
            m.vias[key_b] = [vb]
            q = quote(ctx, m, store=False)
            if q is not None and (best is None or q < best[0]):
                best = (q, va, vb)
    m.vias[key_a], m.vias[key_b] = [], []
    if best is None or (base is not None and best[0] >= base * 0.995):
        return
    _commit_vias(ctx, m, net, layer, ta, [best[1]], key_a)
    _commit_vias(ctx, m, net, layer, tb, [best[2]], key_b)
    cur = best[0]
    # more vias while each one buys at least 2 %
    for _ in range(2 * (n_max - 1)):
        gain = None
        for t, key, other in ((ta, key_a, tb), (tb, key_b, ta)):
            for v in via_candidates(ctx, t, layer, net, pl, toward=(other.x, other.y), in_pad=_is_thermal_pad(t))[:6]:
                m.vias[key].append(v)
                q = quote(ctx, m, store=False)
                m.vias[key].pop()
                if q is not None and q < cur * 0.98 and (gain is None or q < gain[0]):
                    gain = (q, t, key, v)
        if gain is None:
            break
        _commit_vias(ctx, m, net, layer, gain[1], [gain[3]], gain[2])
        cur = gain[0]


def _commit_vias(ctx, m, net, layer, t, vias, key):
    """Commit vias (with their stubs from the pad centre), each re-checked against the
    copper committed so far (candidates are found before any of them is placed)."""
    n = 0
    sp = ctx.sp
    for (x, y, ws, _) in vias:
        w = ws if ws > 0 else sp.width_limits(net, layer)[1]
        saved = sp.via_in_pad
        sp.via_in_pad = saved or ws <= 0          # ws 0: a via inside a thermal pad
        try:
            bad = sp.via_violations(net, x, y, first=True)
        finally:
            sp.via_in_pad = saved
        if bad:
            continue
        c = _centre_on(t, layer)
        if ws > 0 and math.dist(c, (x, y)) > 1e-6 and sp.track_violations(net, layer, w, c, (x, y), first=True):
            continue
        ctx.commit_via(m, net, layer, c, (x, y), w, key) if ws > 0 else \
            ctx.commit_via(m, net, layer, (x, y), (x, y), w, key)
        m.vias.setdefault(key, []).append((x, y, ws, 0.0))
        n += 1
    return n


def _is_thermal_pad(t):
    """A large pad (exposed or thermal pad, > 4 mm^2) where vias in the pad are customary."""
    return t.geom.area > 4.0 and t.width > 1.5


# ----------------------------------------------------------------------------- loop models
def _hop_into(lp, ctx, rt, a, b, w_default, h, el="A"):
    """The routed path of a hop from terminal a to b as strips (straight when unrouted)."""
    if rt is not None and rt.segs:
        layers = {s[0] for s in rt.segs}
        if len(layers) == 1:
            pts = route_pts(rt, start=(a.x, a.y))
            pts = [(a.x, a.y)] + pts + [(b.x, b.y)]
            lp.path(pts, rt.width, h, el)
            return
        # multi-layer hop: its strips at the starting layer's plane height (an approximation;
        # critical_recheck measures each layer at its own height)
        for l, p0, p1 in rt.segs:
            lp.strip(p0, p1, rt.width, h, el)
        return
    lp.strip((a.x, a.y), (b.x, b.y), w_default, h, el)


def loop_model(ctx, m, T, h, gnd_k=None, vias_by_key=None):
    """The routed loop of a chain of terminals (cells, decaps): bodies inside parts, routed
    hops between them, and for the ground hop the surface track and the vias at its two ends
    as parallel paths through the plane."""
    lp = Loop()
    n = len(T)
    vias_by_key = vias_by_key if vias_by_key is not None else m.vias
    for k in range(n):
        ta, tb = T[k], T[(k + 1) % n]
        if ta.fp == tb.fp:
            npins = ctx.npins(ta.fp)
            wb = 0.3 if npins > 4 else max(min(ta.width, tb.width), 0.2)
            lp.body((ta.x, ta.y), (tb.x, tb.y), h, ctx.zb(ta.fp), wb)
            continue
        rt = m.hops.get(f"hop{k}")
        wdef = max(min(ta.width, tb.width), 0.25)
        if k == gnd_k and h != INF:
            va = vias_by_key.get(f"via:{ta.fp}:{ta.pad}") or []
            vb = vias_by_key.get(f"via:{tb.fp}:{tb.pad}") or []
            if va and vb:
                D = ctx.sp.via_size(ta.net)[0]
                rv = D / 2
                ka, kb = {}, {}
                for i, (x, y, ws, _) in enumerate(va):
                    e = f"va{i}"
                    lp.strip((ta.x, ta.y), (x, y), max(ws, D), h, e)
                    lp.vert(x, y, h, 0.0, rv, e)
                    ka[e] = 1.0
                for j, (x, y, ws, _) in enumerate(vb):
                    e = f"vb{j}"
                    lp.vert(x, y, 0.0, h, rv, e)
                    lp.strip((x, y), (tb.x, tb.y), max(ws, D), h, e)
                    kb[e] = 1.0
                if rt is not None and rt.segs:
                    _hop_into(lp, ctx, rt, ta, tb, wdef, h, "lat")
                    ka["lat"] = 1.0
                    kb["lat"] = 1.0
                lp.kcl(ka)
                lp.kcl(kb)
                continue
        _hop_into(lp, ctx, rt, ta, tb, wdef, h, "A")
    return lp


def quote(ctx, m, store=True):
    """The module's routed physics value (nH for loops, ppm for crystals); with store, also
    m.physics with the allocation and utilization."""
    try:
        if m.kind == "cell":
            val, extra = _cell_value(ctx, m)
        elif m.kind == "decap":
            val, extra = _decap_value(ctx, m)
        elif m.kind == "crystal":
            val, extra = _crystal_value(ctx, m)
        elif m.kind == "chain":
            val, extra = _chain_value(ctx, m)
        else:
            return None
    except Exception as e:  # noqa: BLE001 - a quote must never kill routing
        m.notes.append(f"quote failed: {type(e).__name__}: {e}")
        return None
    if val is not None and not (math.isfinite(val) and val > 0):
        m.notes.append(f"quote rejected: {val}")
        return None
    if store and val is not None:
        alloc = allocation(ctx, m)
        m.physics = dict(value=round(val, 4), unit=alloc.unit, alloc=round(alloc.value, 4),
                         u=round(val / alloc.value, 4) if alloc.value > 0 else None, basis=alloc.basis, **extra)
    return val


def _cell_value(ctx, m):
    T = m.spec.get("_T")
    if not T:
        return None, {}
    cx = sum(t.x for t in T) / len(T)
    cy = sum(t.y for t in T) / len(T)
    side = ctx.side_layer(T[0].fp)
    h, pl, pn = ctx.plane(side, cx, cy, gnd=True)
    lp = loop_model(ctx, m, T, h, gnd_k=_ground_hop(ctx, T))
    return lp.value(), dict(h_mm=round(h, 3) if h != INF else None, plane=pl, plane_net=pn)


# ----------------------------------------------------------------------------- allocations
def allocation(ctx, m):
    """The place terms' allocation for this module (Terms structure of the same id when
    available, else the E5 prior of kae.physics.priors)."""
    t = ctx.terms
    if t is not None:
        for st in t.structs:
            if st.id == m.id or st.id.split("#")[0] == m.id:
                return st.alloc
    s = m.spec
    if m.kind == "cell":
        ex = s.get("excite") or {}
        vin = ex.get("V") or ctx.volts(s.get("rail")) or PR.V_IN_UNKNOWN.value
        return PR.hot_loop_budget(s.get("class") or "unknown", vin, t_sw_ns=ex.get("t_sw_ns"))
    if m.kind == "decap":
        v = ctx.volts(s.get("rail")) or 3.3
        pins = s.get("power_pins") or []
        b = PR.decap_budget(v, ctx.npins(s.get("ic")), max(1, len(pins)))
        return PR.Belief(b.value / max(1, len(pins)), "nH", b.basis + " per pin")
    if m.kind == "crystal":
        return PR.crystal_budget(s.get("f_Hz"))[0]
    if m.kind == "chain":
        return PR.esd_budget()
    return PR.Belief(1.0, "", "none")


# ----------------------------------------------------------------------------- decaps
def _decap_pairs(ctx, s):
    """[(power pin number, cap uuid)] of a decap structure: the brief's pin pairing, else
    each HF cap with the nearest power pin."""
    ic = s.get("ic")
    caps = s.get("hf_caps") or s.get("caps") or []
    pins = [str(p) for p in s.get("power_pins") or []]
    pairs = []
    pc = s.get("pin_caps") or {}
    paired = set()
    for pin, cs in pc.items():
        for c in cs:
            if c in caps or c in (s.get("caps") or []):
                pairs.append((str(pin), c))
                paired.add(c)
    for c in caps:
        if c in paired or not pins:
            continue
        rail = s.get("rail")
        tr = ctx.pad_term(c, net=rail)
        if tr is None:
            continue
        best = None
        for p in pins:
            tp = ctx.sp.terminal(ic, [p])
            if tp is None:
                continue
            d = math.hypot(tp.x - tr.x, tp.y - tr.y)
            if best is None or d < best[0]:
                best = (d, p)
        if best is not None:
            pairs.append((best[1], c))
    return pairs


def _ic_ground(ctx, s, tp):
    """The IC's ground terminal nearest the power pin `tp` (None for parts without one)."""
    ic = s.get("ic")
    gpins = [str(p) for p in s.get("ground_pins") or []]
    if not gpins:
        f = ctx.fp.get(ic)
        if f is None:
            return None
        gnet = s.get("ground")
        gpins = [p.number for p in f.pads if p.net and (p.net == gnet or p.net in ctx.gnd)]
    best = None
    for g in dict.fromkeys(gpins):
        t = ctx.sp.terminal(ic, [g])
        if t is None:
            continue
        d = t.geom.distance(Point(tp.x, tp.y))
        if best is None or d < best[0]:
            best = (d, t)
    return best[1] if best else None


def route_decap(ctx, m):
    s = m.spec
    rail = s.get("rail")
    gnet = s.get("ground") or next(iter(sorted(ctx.gnd)), None)
    pairs = _decap_pairs(ctx, s)
    if not pairs or not rail:
        m.status = "skipped"
        m.notes.append("no capacitor-pin pairs")
        return m
    max_d = float(ctx.opts.get("decap_max_mm", 15.0))
    loops = []
    done = tried = 0
    for pin, cap in pairs:
        tp = ctx.sp.terminal(s.get("ic"), [pin])
        tr = ctx.pad_term(cap, net=rail)
        tg = None
        f = ctx.fp.get(cap)
        if f is not None:
            for p in f.pads:
                if p.net and p.net != rail and (p.net == gnet or p.net in ctx.gnd):
                    tg = ctx.sp.terminal(cap, [p.number])
                    break
        if tp is None or tr is None or tg is None:
            m.notes.append(f"pin {pin}: terminals missing")
            continue
        if math.hypot(tp.x - tr.x, tp.y - tr.y) > max_d:
            m.notes.append(f"pin {pin}: capacitor {ctx.fp[cap].ref} {math.hypot(tp.x - tr.x, tp.y - tr.y):.1f} mm away, "
                           "pairing doubtful: left to the general router")
            continue
        tried += 1
        tG = _ic_ground(ctx, s, tp)
        key = f"{pin}:{cap}"
        side = ctx.side_layer(cap)
        # rail: capacitor rail pad -> IC power pin, as wide as the narrower terminal
        layers = hop_layers(ctx, tr, tp, prefer=side)
        rt = None
        if layers:
            ux, uy = tp.x - tr.x, tp.y - tr.y
            dd = math.hypot(ux, uy) or 1.0
            a = min(extent_across(tr.geom, ux / dd, uy / dd), extent_across(tp.geom, ux / dd, uy / dd))
            mn, opt, mx = ctx.sp.width_limits(rail, layers[0])
            widths = sorted({round(w, 4) for w in width_ladder(max(a, opt), max(mn, min(a, opt)), 4) + [opt, mn]},
                            reverse=True)
            rt = route_hop(ctx, m, f"rail:{key}", rail, [anchor(tr)], [anchor(tp)], widths, [layers[0]], via=False)
        if rt is None and len(ctx.sp.cu) > 1:
            # no common layer (capacitor on the far side of the IC) or no room on it: one
            # through via between the pads
            mn, opt, mx = ctx.sp.width_limits(rail, side)
            rt = route_hop(ctx, m, f"rail:{key}", rail, [anchor(tr)], [anchor(tp)], [opt, mn],
                           [ctx.sp.cu[0], ctx.sp.cu[-1]], via=True, via_cost=3.0)
        if rt is None:
            m.notes.append(f"pin {pin}: rail hop not routed")
        else:
            done += 1
        # ground: vias into the ground plane at the cap and at the IC ground pin, or a track
        lay = side if side in tg.layers else tg.layers[0]
        h, pl, pn = ctx.plane(lay, tg.x, tg.y, gnd=True)
        loops.append(dict(pin=pin, cap=cap, tp=tp, tr=tr, tg=tg, tG=tG, key=key, layer=lay))
        if pl is not None and pn in ctx.gnd:
            gnet2 = tg.net
            _decap_vias(ctx, m, loops[-1], gnet2, lay, pl)
        elif (tG is not None and tG.net == tg.net and lay not in tG.layers
              and ctx.sp.zone_covers(tg.net, lay, tg.x, tg.y)):
            # the capacitor sits in the ground pour of its own layer, across the board from
            # the IC: the IC's ground pin gets a via down into that pour
            _ic_ground_via(ctx, m, loops[-1], tg.net, lay)
        elif tG is not None and tG.net == tg.net:
            lays = hop_layers(ctx, tg, tG, prefer=side)
            if lays:
                mn, opt, mx = ctx.sp.width_limits(tg.net, lays[0])
                route_hop(ctx, m, f"gnd:{key}", tg.net, [anchor(tg)], [anchor(tG)],
                          sorted({max(opt, min(tg.width, tG.width)), opt, mn}, reverse=True), [lays[0]], via=False)
    m.spec["_loops"] = loops
    if not tried:
        m.status = "skipped"
        return m
    m.status = "routed" if done == tried else ("partial" if done else "failed")
    quote(ctx, m)
    return m


def _has_plane_link(ctx, t, net, radius=1.0):
    """Whether terminal t already reaches the plane: a through-hole pad, or a committed via
    of its net within `radius` of the pad."""
    if len(t.layers) > 1:
        return True
    g = t.geom.buffer(radius)
    for it in ctx.sp.routed + ctx.sp.existing:
        if it.kind == "via" and it.net == net and g.contains(it.geom):
            return True
    return False


def _decap_vias(ctx, m, lpd, net, layer, pl):
    """Vias for one capacitor-pin pair: at the capacitor ground pad (best site by the routed
    loop) and at the IC ground pin unless it already reaches the plane."""
    tg, tG = lpd["tg"], lpd["tG"]
    kc = f"via:{tg.fp}:{tg.pad}"
    m.vias.setdefault(kc, [])
    if not m.vias[kc]:
        toward = (lpd["tp"].x, lpd["tp"].y)
        cands = via_candidates(ctx, tg, layer, net, pl, toward=toward)
        best = None
        for v in cands[:8]:
            m.vias[kc] = [v]
            q = _decap_loop_value(ctx, m, lpd)
            if q is not None and (best is None or q < best[0]):
                best = (q, v)
        m.vias[kc] = []
        if best is not None:
            _commit_vias(ctx, m, net, layer, tg, [best[1]], kc)
    if tG is not None and tG.net == net:
        kG = f"via:{tG.fp}:{tG.pad}"
        m.vias.setdefault(kG, [])
        if not m.vias[kG] and not _has_plane_link(ctx, tG, net):
            lay = layer if layer in tG.layers else tG.layers[0]
            cands = via_candidates(ctx, tG, lay, net, pl, toward=(lpd["tr"].x, lpd["tr"].y),
                                   in_pad=_is_thermal_pad(tG))
            best = None
            for v in cands[:8]:
                m.vias[kG] = [v]
                q = _decap_loop_value(ctx, m, lpd)
                if q is not None and (best is None or q < best[0]):
                    best = (q, v)
            m.vias[kG] = []
            if best is not None:
                _commit_vias(ctx, m, net, lay, tG, [best[1]], kG)


def _ic_ground_via(ctx, m, lpd, net, pour_layer):
    """A via from the IC ground pin into the ground pour on `pour_layer` (the layer of a
    capacitor on the far side), the site chosen by the routed loop."""
    tG = lpd["tG"]
    kG = f"via:{tG.fp}:{tG.pad}"
    m.vias.setdefault(kG, [])
    if m.vias[kG] or _has_plane_link(ctx, tG, net):
        return
    lay = tG.layers[0]
    cands = via_candidates(ctx, tG, lay, net, pour_layer, toward=(lpd["tr"].x, lpd["tr"].y),
                           in_pad=_is_thermal_pad(tG))
    best = None
    for v in cands[:8]:
        m.vias[kG] = [v]
        q = _decap_loop_value(ctx, m, lpd)
        if q is not None and (best is None or q < best[0]):
            best = (q, v)
    m.vias[kG] = []
    if best is None and cands:
        best = (None, cands[0])
    if best is not None:
        _commit_vias(ctx, m, net, lay, tG, [best[1]], kG)


def _decap_loop_value(ctx, m, lpd):
    """Routed decoupling loop: IC power pin -> rail hop -> capacitor -> ground (track and/or
    vias through the plane) -> IC ground pin -> IC internal path."""
    tp, tr, tg, tG = lpd["tp"], lpd["tr"], lpd["tg"], lpd["tG"]
    layer = lpd["layer"]
    h, pl, pn = ctx.plane(layer, tg.x, tg.y, gnd=True)
    if pl is None:
        h, pl, pn = ctx.plane(layer, tg.x, tg.y, gnd=False)
    lp = Loop()
    key = lpd["key"]
    rt = m.hops.get(f"rail:{key}")
    # tp -> tr (rail hop, reversed), cap body tr -> tg
    _hop_into(lp, ctx, rt, tp, tr, max(min(tp.width, tr.width), 0.2), h, "A")
    lp.body((tr.x, tr.y), (tg.x, tg.y), h, ctx.zb(tr.fp), max(min(tr.width, tg.width), 0.2))
    D = ctx.sp.via_size(tg.net)[0]
    rv = D / 2
    if tG is None:
        # a part without a return pin closes through the plane under its power pin
        tGx, tGy = tp.x, tp.y
        vG = []
        gl_end = True
    else:
        tGx, tGy = tG.x, tG.y
        vG = m.vias.get(f"via:{tG.fp}:{tG.pad}") or []
        gl_end = tG is not None and _has_plane_link(ctx, tG, tg.net, 0.3)
    vc = m.vias.get(f"via:{tg.fp}:{tg.pad}") or []
    grt = m.hops.get(f"gnd:{key}")
    if h != INF and vc and (vG or gl_end):
        ka, kb = {}, {}
        for i, (x, y, ws, _) in enumerate(vc):
            e = f"vc{i}"
            lp.strip((tg.x, tg.y), (x, y), max(ws, D), h, e)
            lp.vert(x, y, h, 0.0, rv, e)
            ka[e] = 1.0
        if vG:
            for j, (x, y, ws, _) in enumerate(vG):
                e = f"vG{j}"
                lp.vert(x, y, 0.0, h, rv, e)
                lp.strip((x, y), (tGx, tGy), max(ws, D), h, e)
                kb[e] = 1.0
        else:
            e = "vG"
            lp.vert(tGx, tGy, 0.0, h, rv, e)
            kb[e] = 1.0
        if grt is not None and grt.segs and tG is not None:
            _hop_into(lp, ctx, grt, tg, tG, 0.25, h, "lat")
            ka["lat"] = 1.0
            kb["lat"] = 1.0
        lp.kcl(ka)
        lp.kcl(kb)
    elif tG is not None:
        _hop_into(lp, ctx, grt, tg, tG, max(min(tg.width, tG.width), 0.2), h, "A")
    else:
        lp.strip((tg.x, tg.y), (tp.x, tp.y), 0.25, h, "A")
    # IC internal path ground pin -> power pin
    if tG is not None:
        lp.body((tGx, tGy), (tp.x, tp.y), h, ctx.zb(tp.fp), 0.3 if ctx.npins(tp.fp) > 4 else 0.5)
    return lp.value()


def _decap_value(ctx, m):
    loops = m.spec.get("_loops") or []
    if not loops:
        return None, {}
    vals = [v for v in (_decap_loop_value(ctx, m, lpd) for lpd in loops) if v is not None]
    if not vals:
        return None, {}
    # caps on one pin act in parallel; the structure's spend is the worst pin
    by_pin = {}
    for lpd, v in zip(loops, vals):
        by_pin.setdefault(lpd["pin"], []).append(v)
    per_pin = {p: 1.0 / sum(1.0 / x for x in vs if x > 1e-9) for p, vs in by_pin.items()}
    worst = max(per_pin.values())
    return worst, dict(per_pin={p: round(v, 3) for p, v in per_pin.items()})


# ----------------------------------------------------------------------------- crystals
def route_crystal(ctx, m):
    s = m.spec
    ic, y = s.get("ic"), s.get("crystal")
    if ic is None or y is None or ic not in ctx.fp or y not in ctx.fp:
        m.status = "skipped"
        return m
    members = [y] + list(s.get("load_caps") or []) + list(s.get("series_r") or []) + list(s.get("feedback_r") or [])
    nets = []
    for pin in (s.get("xin"), s.get("xout")):
        t = ctx.sp.terminal(ic, [pin]) if pin is not None else None
        if t is not None and t.net and t.net not in nets:
            nets.append(t.net)
    # the nets of the crystal circuit: IC pins' nets and the crystal's non-ground pads' nets
    for u in members:
        f = ctx.fp.get(u)
        if f is None:
            continue
        for p in f.pads:
            if p.net and p.net not in ctx.gnd and p.net not in nets and _net_in_struct(ctx, p.net, [ic] + members):
                nets.append(p.net)
    # each net: IC pin first, then the crystal's (or series resistor's) pad, then the rest;
    # both IC -> crystal hops are routed before any load-capacitor stub
    per = []
    for net in nets:
        terms = []
        for u in [ic, y] + members[1:]:
            f = ctx.fp.get(u)
            if f is None:
                continue
            for p in f.pads:
                if p.net == net:
                    t = ctx.sp.terminal(u, [p.number])
                    if t is not None and not any(t.fp == x.fp and t.pad == x.pad for x in terms):
                        terms.append(t)
        if len(terms) >= 2:
            per.append((net, terms))
    ok = tot = 0
    for net, terms in per:
        a, b = _tree(ctx, m, net, terms[:2], f"xt:{net}:0")
        ok += a
        tot += b
    for net, terms in per:
        if len(terms) > 2:
            a, b = _tree(ctx, m, net, terms, f"xt:{net}:1")
            ok += a
            tot += b
    # load capacitors' ground pads into the plane
    for c in s.get("load_caps") or []:
        f = ctx.fp.get(c)
        if f is None:
            continue
        for p in f.pads:
            if p.net in ctx.gnd:
                t = ctx.sp.terminal(c, [p.number])
                lay = ctx.side_layer(c)
                lay = lay if lay in t.layers else t.layers[0]
                h, pl, pn = ctx.plane(lay, t.x, t.y, gnd=True)
                if pl is not None and pn == p.net and not _has_plane_link(ctx, t, p.net):
                    cands = via_candidates(ctx, t, lay, p.net, pl, toward=(ctx.sp.terminal(ic, [s.get('xin')]).x,
                                                                          ctx.sp.terminal(ic, [s.get('xin')]).y)
                                           if s.get("xin") else None)
                    if cands:
                        _commit_vias(ctx, m, p.net, lay, t, [cands[0]], f"via:{c}:{p.number}")
    m.spec["_nets"] = nets
    m.status = "routed" if ok == tot and tot else ("partial" if ok else "failed")
    quote(ctx, m)
    return m


def _net_in_struct(ctx, net, uuids):
    """Whether every pad of `net` belongs to the structure's parts (a local net)."""
    us = set(uuids)
    n = ctx.board.nets.get(net)
    if n is None:
        return False
    refs = {ctx.fp[u].ref for u in uuids if u in ctx.fp}
    return all(ref in refs for ref, _ in n.pads) and len(n.pads) >= 2 and bool(us)


def _tree(ctx, m, net, terms, tag, widths=None):
    """Connect terminals of one net as a tree: each next terminal (nearest first) to the
    copper routed so far. Returns (connections made, connections needed)."""
    done = [terms[0]]
    left = list(terms[1:])
    ok = 0
    need = len(left)
    k = 0
    while left:
        # the remaining terminal nearest to the connected set
        best = None
        for t in left:
            for d0 in done:
                dd = math.hypot(t.x - d0.x, t.y - d0.y)
                if best is None or dd < best[0]:
                    best = (dd, t, d0)
        _, t, d0 = best
        left.remove(t)
        layers = hop_layers(ctx, t, d0, prefer=ctx.side_layer(t.fp))
        if not layers:
            layers = [ctx.sp.cu[0]]
        mn, opt, mx = ctx.sp.width_limits(net, layers[0])
        ws = widths or sorted({opt, mn}, reverse=True)
        if any(ctx.connected(net, d, t) for d in done):
            ok += 1
            k += 1
            done.append(t)
            continue
        srcs = [anchor(x) for x in done]
        for d in done:
            srcs += ctx.net_copper_anchors(net, connected_to=d)
        rt = route_hop(ctx, m, f"{tag}:{k}", net, [anchor(t)], srcs, ws, [layers[0]], via=False)
        if rt is None and len(ctx.sp.cu) > 1:
            rt = route_hop(ctx, m, f"{tag}:{k}", net, [anchor(t)], srcs, ws[-1:], [ctx.sp.cu[0], ctx.sp.cu[-1]],
                           via=True, via_cost=3.0)
        k += 1
        if rt is not None:
            ok += 1
        done.append(t)
    return ok, need


def _crystal_value(ctx, m):
    nets = m.spec.get("_nets") or []
    s = m.spec
    _, S = PR.crystal_budget(s.get("f_Hz"))
    C = 0.0
    for net in nets:
        for it in ctx.sp.routed:
            if it.kind == "track" and it.net == net and it.owner and it.owner[0] == m.id:
                l = next(iter(it.layers))
                h, pl, _ = ctx.plane(l, it.geom.centroid.x, it.geom.centroid.y, gnd=False)
                er = ctx.sp.er[0] if ctx.sp.er else 4.3
                C += trace_capacitance_pf(it.geom.length, 2 * it.r, h if h != INF else ctx.sp.thickness, er)
    return S * C, dict(c_trace_pf=round(C, 4))


# ----------------------------------------------------------------------------- protection chains
def route_chain(ctx, m):
    s = m.spec
    ch = [x for x in (s.get("chain") or []) if x]
    prot = set(s.get("protection") or [])
    if len(ch) < 2 or not prot:
        m.status = "skipped"
        return m
    T = [ctx.term(x) for x in ch]
    if any(t is None for t in T):
        m.status = "skipped"
        m.notes.append("chain terminals not found")
        return m
    # a protector hanging off the line (not in the chain): insert its pad after the connector
    if not any(t.fp in prot for t in T[1:]):
        u = sorted(prot)[0]
        tp = ctx.pad_term(u, net=T[0].net)
        if tp is not None:
            T.insert(1, tp)
    power = s.get("pin_kind") == "power" or (ctx.nets.get(T[0].net) or {}).get("role") == "rail"
    # hops after the first protector carry no surge-path physics; chain_tail=False leaves
    # them to the general router (less locked copper in its way, the order not enforced)
    first_prot = next((k for k, t in enumerate(T) if k > 0 and t.fp in prot), len(T) - 1)
    ok = need = 0
    for k in range(len(T) - 1):
        ta, tb = T[k], T[k + 1]
        if ta.fp == tb.fp or ta.net != tb.net:
            continue
        if k >= first_prot and not ctx.opts.get("chain_tail", True):
            m.notes.append(f"hop {k} after the protector left to the general router")
            continue
        need += 1
        if ctx.connected(ta.net, ta, tb):
            ok += 1
            continue
        layers = hop_layers(ctx, ta, tb, prefer=ctx.side_layer(tb.fp))
        l0 = layers[0] if layers else ctx.side_layer(tb.fp)
        mn, opt, mx = ctx.sp.width_limits(ta.net, l0)
        ws = [opt, mn]
        if power:
            I = float((getattr(ctx, "rail_I", None) or {}).get(ta.net) or ctx.opts.get("chain_power_a", 1.0))
            w = max(ipc2221_width(I, t_mm=ctx.sp.tcu.get(l0, 0.035)), opt)
            ws = sorted({w, max(opt, min(w, min(ta.width, tb.width))), opt, mn}, reverse=True)
        tgt = [anchor(tb)] + (ctx.net_copper_anchors(ta.net, connected_to=tb) if k == len(T) - 2 else [])
        rt = None
        if layers:
            rt = route_hop(ctx, m, f"hop{k}", ta.net, [anchor(ta)], tgt, ws, [layers[0]], via=False)
        if rt is None and len(ctx.sp.cu) > 1:
            # parts on opposite sides, or no room on the shared layer: through one via
            rt = route_hop(ctx, m, f"hop{k}", ta.net, [anchor(ta)], tgt, ws, [ctx.sp.cu[0], ctx.sp.cu[-1]],
                           via=True, via_cost=3.0)
        if rt is not None:
            ok += 1
        else:
            m.notes.append(f"hop {k} ({ta.net}, {ctx.fp[ta.fp].ref} -> {ctx.fp[tb.fp].ref}) not routed")
    # the protector's ground into the plane (or to the connector's ground pin)
    for u in prot:
        f = ctx.fp.get(u)
        if f is None:
            continue
        for p in f.pads:
            if p.net in ctx.gnd:
                t = ctx.sp.terminal(u, [p.number])
                if t is None:
                    continue
                lay = ctx.side_layer(u)
                lay = lay if lay in t.layers else t.layers[0]
                h, pl, pn = ctx.plane(lay, t.x, t.y, gnd=True)
                if pl is not None and pn == p.net and not _has_plane_link(ctx, t, p.net):
                    cands = via_candidates(ctx, t, lay, p.net, pl, toward=(T[0].x, T[0].y))
                    if cands:
                        _commit_vias(ctx, m, p.net, lay, t, [cands[0]], f"via:{u}:{p.number}")
                break
    m.spec["_T"] = T
    m.status = "routed" if ok == need and need else ("partial" if ok else "failed")
    quote(ctx, m)
    return m


def _chain_value(ctx, m):
    """Surge path ahead of the protector: L'(w, h) times the routed length from the
    connector pin to the protector pad, plus the protector's ground via (place-terms ESD
    model)."""
    T = m.spec.get("_T") or []
    prot = set(m.spec.get("protection") or [])
    if len(T) < 2:
        return None, {}
    length = 0.0
    w = 0.25
    h = INF
    for k in range(len(T) - 1):
        ta, tb = T[k], T[k + 1]
        rt = m.hops.get(f"hop{k}")
        if rt is not None and rt.segs:
            length += rt.length
            w = rt.width
            l = rt.segs[0][0]
        else:
            length += math.hypot(tb.x - ta.x, tb.y - ta.y)
            l = ctx.side_layer(tb.fp)
        h, _, _ = ctx.plane(l, ta.x, ta.y, gnd=False)
        if tb.fp in prot:
            break
    hh = h if h != INF else ctx.sp.thickness
    import kae.physics.fastloop as FL
    lv = FL.m_self(hh, 0.15) + FL._collinear(hh, hh, 0.0)
    return lprime_hj(w, hh) * length + lv, dict(surge_path_mm=round(length, 3))


ROUTERS = {"cell": route_cell, "decap": route_decap, "crystal": route_crystal, "chain": route_chain}


def route_module(ctx, m):
    fn = ROUTERS.get(m.kind)
    if fn is None:
        m.status = "skipped"
        return m
    try:
        return fn(ctx, m)
    except Exception as e:  # noqa: BLE001 - one module must not stop the others
        import traceback
        m.status = "error"
        m.notes.append(f"{type(e).__name__}: {e}")
        ctx.log(f"module {m.id}: {type(e).__name__}: {e}\n{traceback.format_exc()}")
        return m
