# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Last mile: close the few connections Freerouting leaves open with the critical router's
grid search, ripping up the unlocked tracks of other nets that stand in the way.

On splits A+B the bridge leaves 1-3 unconnected items on about 30 % of attempts (sk-tibia
v6, 10x budget: 29 of 99, all unconnected-only), and more time does not close them:
Freerouting stops (COMPLETED or STAGNATION) and its own last-mile rip-up has already run.
What is left is of two kinds:

- a signal connection Freerouting found no path for (paw3395: MOSI, J2.4 to U2.11);
- copper of a plane net KiCad sees as cut off: a pad outside the fill of its zone, a fill
  island of a split pour (Freerouting treats a plane as one conduction area, so it never
  sees these as open).

`close` reads the board as KiCad sees it (the routed board's tracks and vias, every zone's
refilled copper), finds each open net's connected parts (copper touching on a layer, a
track joined only at its ends, as KiCad joins them) and joins each smaller part to the
rest: a grid route (GridRouter.connect, every segment and via checked exactly against the
bridge's rules) from the part's copper to the other parts' copper within a growing window,
first around everything, then with the window's unlocked tracks and vias of other nets
taken out. Of those, only the ones the new copper would violate are ripped; their nets are
then open, and the repair loop routes them again with the new copper fixed.

    close(board, info, plan, fills, out, nets=open_nets(drc_report)) -> report

Lengths are mm. Nothing here changes how a board is scored: the caller keeps a result only
when KiCad's DRC on the re-opened board is better.
"""
from __future__ import annotations

import numpy as np
from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import unary_union

from kae.board.kicad_file import load

from . import critical_write as W
from .critical_grid import Anchor, GridRouter
from .critical_space import Space

MARGINS = (1.0, 3.0, 8.0)       # mm around a part and the nearest other part: search windows
RIP_MARGINS = (1.0, 3.0)        # windows whose foreign unlocked copper may be ripped
MAX_RIP = 40                    # tracks and vias ripped for one connection at most
RIP_COST = 20.0                 # per cell of foreign copper crossed in a rip-up search (a detour of
                                # about 10 mm beats ripping one 0.25 mm track)


# ----------------------------------------------------------------------------- connectivity
def _fill_polys(fills):
    """{net: {layer: [Polygon]}} from pcbnew_io.zone_fills()["zones"]."""
    out = {}
    for z in fills or []:
        net = z.get("net")
        if not net:
            continue
        for layer, polys in (z.get("layers") or {}).items():
            for rings in polys:
                if rings and len(rings[0]) >= 3:
                    g = Polygon(rings[0], [h for h in rings[1:] if len(h) >= 3])
                    g = g if g.is_valid else g.buffer(0)
                    for p in getattr(g, "geoms", [g]):
                        if not p.is_empty:
                            out.setdefault(net, {}).setdefault(layer, []).append(p)
    return out


class _Node:
    __slots__ = ("kind", "item", "layers", "copper", "ends", "layer")

    def __init__(self, kind, item, layers, copper, ends=(), layer=None):
        self.kind, self.item, self.layers, self.copper, self.ends, self.layer = kind, item, set(layers), copper, ends, layer


def parts(space, fills, net):
    """The connected parts of `net` as KiCad joins its copper: [[_Node]], largest first
    (by pads, then fill area). A track joins other copper only where one of its ends lies
    on it; pads, vias and fills join what they overlap on a shared layer."""
    nodes = []
    for it in space.pads:
        if it.net == net and it.kind == "pad":
            nodes.append(_Node("pad", it, it.layers, it.geom))
    for it in space.existing + space.routed:
        if it.net != net:
            continue
        if it.kind == "track":
            c = list(it.geom.coords)
            nodes.append(_Node("track", it, it.layers, it.geom.buffer(it.r), ends=(Point(c[0]), Point(c[-1])),
                               layer=next(iter(it.layers))))
        elif it.kind == "via":
            nodes.append(_Node("via", it, it.layers, it.geom.buffer(it.r)))
    for layer, polys in (fills.get(net) or {}).items():
        for p in polys:
            nodes.append(_Node("fill", p, [layer], p, layer=layer))
    parent = list(range(len(nodes)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def join(i, j):
        a, b = find(i), find(j)
        if a != b:
            parent[a] = b

    eps = 1e-6
    for i, a in enumerate(nodes):
        for j in range(i + 1, len(nodes)):
            b = nodes[j]
            shared = a.layers & b.layers
            if not shared:
                continue
            if a.kind == "track" or b.kind == "track":
                t, o = (a, b) if a.kind == "track" else (b, a)
                if o.kind == "track":
                    hit = any(o.copper.distance(e) <= eps for e in t.ends) or any(
                        t.copper.distance(e) <= eps for e in o.ends)
                else:
                    hit = any(o.copper.distance(e) <= eps for e in t.ends)
            else:
                hit = a.copper.distance(b.copper) <= eps
            if hit:
                join(i, j)
    groups = {}
    for i in range(len(nodes)):
        groups.setdefault(find(i), []).append(nodes[i])

    def size(g):
        return (sum(1 for n in g if n.kind == "pad"), sum(n.copper.area for n in g if n.kind == "fill"))
    return sorted(groups.values(), key=size, reverse=True)


def _anchors(part, shrink, clip=None):
    """Routing anchors for the copper of a part (fills shrunk by `shrink`, so a track end
    lands inside them), the ones meeting `clip` (a box) when given."""
    out = []
    for n in part:
        if clip is not None and not n.copper.intersects(clip):
            continue
        it = n.item
        if n.kind == "pad":
            out.append(Anchor(it.geom, tuple(sorted(it.layers)), it.pos, kind="pad"))
        elif n.kind == "track":
            out.append(Anchor(it.geom, tuple(it.layers), None, grow=it.r * 0.8, kind="track"))
        elif n.kind == "via":
            out.append(Anchor(it.geom, tuple(it.layers), (it.geom.x, it.geom.y), grow=it.r * 0.8, kind="via"))
        else:
            g = n.copper.buffer(-shrink)
            if clip is not None:
                g = g.intersection(clip)
            if not g.is_empty and g.area > 1e-4:
                out.append(Anchor(g, (n.layer,), None, kind="zone"))
    return out


# ----------------------------------------------------------------------------- routing
class _SoftRouter(GridRouter):
    """A GridRouter that may cross `soft` copper (foreign tracks and vias taken out of the
    space for a rip-up search) at `soft_cost` per cell, so a route rips only what a detour
    of soft_cost cells per cell crossed cannot avoid."""

    def __init__(self, sp, **kw):
        super().__init__(sp, **kw)
        self.soft = []           # [Item]
        self.soft_cost = 0.0

    def cost_layer(self, grid, net, layer, w, layer_factor=1.0, skip=()):
        c = super().cost_layer(grid, net, layer, w, layer_factor, skip)
        if self.soft and self.soft_cost > 0:
            m = np.zeros(c.shape, bool)
            for it in self.soft:
                if layer in it.layers:
                    nd = self.sp.need(it, net, "track", layer) or 0.0
                    grid.within(it.geom, it.r + nd + w / 2.0, m)
            c[m & np.isfinite(c)] += self.soft_cost * layer_factor
        return c


def _bounds(anchors):
    bs = [a.geom.bounds for a in anchors]
    return min(b[0] for b in bs), min(b[1] for b in bs), max(b[2] for b in bs), max(b[3] for b in bs)


def _window(src, others, margin):
    """The box around a part's anchors and the nearest copper of the other parts, grown by
    `margin` mm."""
    sg = unary_union([a.geom for a in src])
    best = None
    for p in others:
        for n in p:
            d = n.copper.distance(sg)
            if best is None or d < best[0]:
                best = (d, n.copper)
    x0, y0, x1, y1 = _bounds(src)
    if best is not None:
        from shapely.ops import nearest_points
        q = nearest_points(best[1], sg)[0]
        x0, y0, x1, y1 = min(x0, q.x), min(y0, q.y), max(x1, q.x), max(y1, q.y)
    return box(x0 - margin, y0 - margin, x1 + margin, y1 + margin)


def _try(gr, sp, net, src, others, win, widths):
    dst = [a for p in others for a in _anchors(p, max(widths) / 2 + 0.02, clip=win)]
    if not dst:
        return None
    grid = gr.window([Anchor(win, tuple(sp.cu))], margin=0.0)
    for w in widths:
        rt = gr.connect(net, src, dst, w, sp.cu, via=len(sp.cu) > 1, window=grid)
        if rt is not None and (rt.segs or rt.vias):
            return rt
    return None


def _restore(sp, items):
    for it in items:
        sp.existing.append(it)
        for l in it.layers:
            if l in sp.items:
                sp.items[l].append(it)
    sp.invalidate()


def _conflicts(sp, it, new):
    """Whether existing item `it` (of another net) breaks a requirement against the new copper."""
    if it.kind == "track":
        c = list(it.geom.coords)
        layer = next(iter(it.layers))
        for a, b in zip(c[:-1], c[1:]):
            if any(v[0] in new for v in sp.track_violations(it.net, layer, it.width, a, b)):
                return True
        return False
    if it.kind == "via":
        return any(v[0] in new for v in sp.via_violations(it.net, it.geom.x, it.geom.y, size=it.width,
                                                           drill=it.drill, layers=list(it.layers)))
    return True


def _join(gr, sp, net, src, others, widths, fixed):
    """One route from `src` to the other parts: (route, new items, ripped items) or None."""
    for m in MARGINS:
        rt = _try(gr, sp, net, src, others, _window(src, others, m), widths)
        if rt is not None:
            return rt, _commit(sp, rt), []
    for m in RIP_MARGINS:
        win = _window(src, others, m)
        cand = {id(it): it for l in sp.cu for it in sp.query(l, win.bounds)
                if it.kind in ("track", "via") and it.net != net and it.owner == "existing"
                and not it.locked and it.uuid not in fixed and it.geom.intersects(win)}
        cand = list(cand.values())
        if not cand:
            continue
        sp.remove(cand)
        gr.soft, gr.soft_cost = cand, RIP_COST
        try:
            rt = _try(gr, sp, net, src, others, win, widths)
        finally:
            gr.soft, gr.soft_cost = [], 0.0
        if rt is None:
            _restore(sp, cand)
            continue
        new = _commit(sp, rt)
        keep = [it for it in cand if not _conflicts(sp, it, set(new))]
        _restore(sp, keep)
        ripped = [it for it in cand if it not in keep]
        if len(ripped) > MAX_RIP:
            sp.remove(new)
            _restore(sp, ripped)
            continue
        return rt, new, ripped
    return None


def open_nets(report):
    """Nets of the unconnected items of a KiCad DRC report (the name in brackets)."""
    out = set()
    for u in report.get("unconnected_items") or []:
        for it in u.get("items") or []:
            d = it.get("description") or ""
            if "[" in d and "]" in d:
                out.add(d[d.index("[") + 1:d.index("]")])
    return sorted(out)


def close(board, info, plan, fills, out, nets=None, sev=None, fixed=(), log=print, max_parts=8):
    """Join the parts of the open nets of `board` (`nets`, default every net with more
    than one part; see the module docstring) and write the result to `out`, the new copper
    locked. `board` has its project files beside it; `fills`: pcbnew_io.zone_fills(board)
    ["zones"] (refilled with those rules); `fixed`: uuids never ripped (pre-routes).
    Returns {joined, failed, ripped: [uuid], added: [uuid], nets: {net: status}}."""
    b = load(board)
    sp = Space(b, info, plan=plan, sev=sev or {})
    gr = _SoftRouter(sp)
    fp = _fill_polys(fills)
    fixed = set(fixed)
    rep = dict(joined=0, failed=0, ripped=[], added=[], nets={})
    if nets is None:
        nets = sorted({it.net for it in sp.pads if it.net and it.kind == "pad"})
    todo = [net for net in nets if len([p for p in parts(sp, fp, net) if _relevant(p)]) > 1]
    for net in todo:
        mn, opt, _mx = sp.width_limits(net, sp.cu[0])
        widths = sorted({round(opt, 4), round(mn, 4)}, reverse=True)
        status = []
        for _ in range(max_parts):
            ps = [p for p in parts(sp, fp, net) if _relevant(p)]
            if len(ps) < 2:
                break
            small = ps[-1]
            src = _anchors(small, max(widths) / 2 + 0.02)
            if not src:
                status.append("no anchors")
                break
            got = _join(gr, sp, net, src, ps[:-1], widths, fixed)
            if got is None:
                status.append("no route")
                rep["failed"] += 1
                break
            rt, new, ripped = got
            rep["joined"] += 1
            rep["added"] += [it.uuid for it in new]
            rep["ripped"] += [it.uuid for it in ripped]
            status.append(f"joined ({len(rt.segs)} segs, {len(rt.vias)} vias, ripped {len(ripped)})")
        rep["nets"][net] = status
        log(f"last mile {net}: {'; '.join(status) or 'nothing to join'}")
    tracks = [(it.net, next(iter(it.layers)), it.width, tuple(it.geom.coords[0]), tuple(it.geom.coords[-1]),
               it.uuid, True) for it in sp.routed if it.kind == "track"]
    vias = [(it.net, it.geom.x, it.geom.y, it.width, it.drill, it.uuid, True) for it in sp.routed if it.kind == "via"]
    W.edit(board, out, remove=rep["ripped"]) if rep["ripped"] else W.edit(board, out)
    if tracks or vias:
        W.append_items(out, out, tracks=tracks, vias=vias)
    return rep


def _relevant(part):
    """A part KiCad's ratsnest counts: it holds a pad or zone fill (track-only parts are tails)."""
    return any(n.kind in ("pad", "fill") for n in part)


def _commit(sp, rt):
    new = []
    for l, a, b2 in rt.segs:
        it = sp.add_track(rt.net, l, rt.width, a, b2, owner=("lastmile", ""))
        it.uuid = W.new_uuid()
        new.append(it)
    for (x, y) in rt.vias:
        it = sp.add_via(rt.net, x, y, owner=("lastmile", ""))
        it.uuid = W.new_uuid()
        new.append(it)
    return new
