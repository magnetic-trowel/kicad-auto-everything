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
taken out and priced per cell crossed (RIP_COST). Of those, only the ones the new copper
would violate are ripped. A ripped net goes back on the queue and is joined again by the
same search (negotiated rip-up and re-route, PathFinder-like: a net's copper gets dearer to
rip each time, HIST_WEIGHT, and is left alone after HIST_MAX rip-ups; MAX_JOINS bounds the
whole). What stays open goes to the repair loop, which routes it with the new copper fixed. A pad walled in by its own footprint (a microphone's centre pad
inside its ring) is left through a via in the pad, as the human board does.

The bridge runs it after its repair rounds with `last_mile` (off by default; repair._last_mile).

    close(board, info, plan, fills, out, nets=open_nets(drc_report)) -> report

Lengths are mm. Nothing here changes how a board is scored: the caller keeps a result only
when KiCad's DRC on the re-opened board is better.
"""
from __future__ import annotations

import numpy as np
from shapely import STRtree
from shapely.geometry import Point, Polygon, box
from shapely.ops import unary_union

from kae.board.kicad_file import load

from . import critical_write as W
from .critical_grid import Anchor, GridRouter
from .critical_space import Space

MARGINS = (1.0, 3.0, 8.0)       # mm around a part and the nearest other part: search windows
WIDE = 15.0                     # mm around a part: the last window, before any rip-up
RIP_MARGINS = (1.0, 3.0)        # windows whose foreign unlocked copper may be ripped
MAX_RIP = 40                    # tracks and vias ripped for one connection at most
VIA_COSTS = (None, 12.0)        # the grid router's via cost, then a dear one (cells per via)
MAX_JOINS = 40                  # joins per close() at most (the negotiated re-routes included)
HIST_WEIGHT = 2.0               # a net's copper costs (1 + HIST_WEIGHT * times ripped) x RIP_COST
HIST_MAX = 3                    # a net ripped this often is not ripped again
SOFT_FACTOR = 3.0               # critical copper (close's `soft`) costs this many times more to rip
TXN_JOINS = 24                  # joins one rip-up transaction (close) makes at most
RIP_COST = 20.0                 # per cell of foreign copper crossed in a rip-up search (crossing a
                                # 0.25 mm track at 0.2 mm clearance costs as much as an 18 mm detour)


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
    tree = STRtree([n.copper for n in nodes]) if nodes else None
    for i, a in enumerate(nodes):
        for j in tree.query(a.copper.buffer(eps)):
            j = int(j)
            if j <= i:
                continue
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
    space for a rip-up search) at a price per cell crossed, so a route rips only what a
    detour of that many cells per cell cannot avoid. `soft`: [(item, cost per cell)]."""

    def __init__(self, sp, **kw):
        super().__init__(sp, **kw)
        self.soft = []

    def cost_layer(self, grid, net, layer, w, layer_factor=1.0, skip=()):
        c = super().cost_layer(grid, net, layer, w, layer_factor, skip)
        if self.soft:
            fin = np.isfinite(c)
            for it, k in self.soft:
                if layer in it.layers and k > 0:
                    m = np.zeros(c.shape, bool)
                    nd = self.sp.need(it, net, "track", layer) or 0.0
                    grid.within(it.geom, it.r + nd + w / 2.0, m)
                    c[m & fin] += k * layer_factor
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
    """A route from `src` to the other parts' copper inside `win`, committed: (route, new
    items) or None. A route whose own vias crowd each other (the search checks a via only
    against committed copper) is searched again with vias dearer."""
    dst = [a for p in others for a in _anchors(p, max(widths) / 2 + 0.02, clip=win)]
    if not dst:
        return None
    grid = gr.window([Anchor(win, tuple(sp.cu))], margin=0.0)
    for w in widths:
        # only the layers whose rules allow this width (sdi-mipi: ddr3 0.2 mm outside, at most
        # 0.162 mm inside; one width for all layers made 50 track_width errors)
        cu = [l for l in sp.cu if _width_ok(sp, net, l, w)]
        if not cu:
            continue
        for vc in VIA_COSTS:
            rt = gr.connect(net, src, dst, w, cu, via=len(cu) > 1, window=grid, via_cost=vc)
            if rt is None or not (rt.segs or rt.vias):
                break
            new = _commit(sp, rt)
            if new is not None:
                return rt, new
    return None


def _width_ok(sp, net, layer, w):
    mn, _opt, mx = sp.width_limits(net, layer)
    return w >= (mn or 0.0) - 1e-6 and (mx is None or w <= mx + 1e-6)


def widths_of(sp, net):
    """The track widths to try for `net`, widest first: each layer's opt and min."""
    ws = {round(w, 4) for l in sp.cu for w in sp.width_limits(net, l)[:2] if w and w > 0}
    return sorted(ws, reverse=True) or [0.2]


def _own(it):
    """Whether `it` is copper this close() added (owner ("lastmile", join number))."""
    return isinstance(it.owner, tuple) and it.owner[:1] == ("lastmile",)


def _restore(sp, items):
    for it in items:
        (sp.routed if _own(it) else sp.existing).append(it)
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


def _join(gr, sp, net, src, others, widths, fixed, hist=None, soft=(), rip=True):
    """One route from `src` to the other parts: (route, new items, ripped items) or None.
    `hist` {net: times ripped} prices a net's copper RIP_COST * (1 + HIST_WEIGHT * times)
    per cell (PathFinder's history cost) and leaves it alone after HIST_MAX rip-ups. `soft`:
    uuids of locked copper (critical copper) that a last rip-up tier may take out too, at
    SOFT_FACTOR times the price, when nothing else lets the join through."""
    hist = hist if hist is not None else {}
    x0, y0, x1, y1 = _bounds(src)
    wide = box(x0 - WIDE, y0 - WIDE, x1 + WIDE, y1 + WIDE)    # every direction, not only the nearest part's
    for win in [_window(src, others, m) for m in MARGINS] + [wide]:
        got = _try(gr, sp, net, src, others, win, widths)
        if got is not None:
            return got[0], got[1], []
    if not rip:
        return None
    tiers = [(m, False) for m in RIP_MARGINS] + ([(m, True) for m in RIP_MARGINS] if soft else [])
    for m, with_soft in tiers:
        win = _window(src, others, m)

        def rippable(it):
            if it.uuid in soft:
                return with_soft
            return not it.locked and it.uuid not in fixed
        # the board's unlocked copper, and what earlier joins of this close() laid (a join is
        # not final: the first nets through a 0.4 mm-pitch row can wall in a later one, qubik
        # bmps U2.11 behind /CELLX's via); each net at most HIST_MAX times
        cand = {id(it): it for l in sp.cu for it in sp.query(l, win.bounds)
                if it.kind in ("track", "via") and it.net != net
                and (it.owner == "existing" and rippable(it) or _own(it))
                and it.geom.intersects(win) and hist.get(it.net, 0) < HIST_MAX}
        cand = list(cand.values())
        if not cand or (with_soft and not any(it.uuid in soft for it in cand)):
            continue
        sp.remove(cand)
        gr.soft = [(it, RIP_COST * (1.0 + HIST_WEIGHT * hist.get(it.net, 0)) * (SOFT_FACTOR if it.uuid in soft else 1.0))
                   for it in cand]
        try:
            got = _try(gr, sp, net, src, others, win, widths)
        finally:
            gr.soft = []
        if got is None:
            _restore(sp, cand)
            continue
        rt, new = got
        keep = [it for it in cand if not _conflicts(sp, it, set(new))]
        # an earlier join goes as a whole when any piece of it must (no dangling remains)
        gone = {it.owner for it in cand if _own(it) and it not in keep}
        keep = [it for it in keep if not (_own(it) and it.owner in gone)]
        _restore(sp, keep)
        ripped = [it for it in cand if it not in keep]
        rest = [it for it in sp.routed if _own(it) and it.owner in gone]
        if rest:
            sp.remove(rest)
            ripped += rest
        if len(ripped) > MAX_RIP:
            sp.remove(new)
            _restore(sp, ripped)
            continue
        return rt, new, ripped
    return None


# KiCad escapes these characters in net names in the board file and shows them unescaped in
# its DRC report (EscapeString / UnescapeString)
_ESCAPES = {"{slash}": "/", "{backslash}": "\\", "{lt}": "<", "{gt}": ">", "{colon}": ":", "{dblquote}": '"',
            "{quote}": "'", "{space}": " ", "{tab}": "\t", "{return}": "\n", "{brace}": "{", "{comma}": ","}


def unescape(name):
    """A board net name as KiCad's DRC report writes it."""
    for k, v in _ESCAPES.items():
        name = name.replace(k, v)
    return name


def open_nets(report):
    """Nets of the unconnected items of a KiCad DRC report (the name in brackets)."""
    out = set()
    for u in report.get("unconnected_items") or []:
        for it in u.get("items") or []:
            d = it.get("description") or ""
            if "[" in d and "]" in d:
                out.add(d[d.index("[") + 1:d.index("]")])
    return sorted(out)


def close(board, info, plan, fills, out, nets=None, sev=None, fixed=(), log=print, max_parts=8, soft=(),
          max_joins=MAX_JOINS, deadline=None, rip=True, txn=True):
    """Join the parts of the open nets of `board` (`nets`, default every net with more
    than one part; see the module docstring) and write the result to `out`, the new copper
    locked. `board` has its project files beside it; `fills`: pcbnew_io.zone_fills(board)
    ["zones"] (refilled with those rules); `fixed`: uuids never ripped (pre-routes); `soft`:
    locked uuids a last rip-up tier may take out (critical copper; the caller judges the
    physics). `max_joins` bounds the joins (None: no bound), `deadline` (time.monotonic())
    the time: no join starts after it; `rip` False: joins around everything only, nothing is
    ripped. Rip-up works in transactions (see below); `txn` False keeps every join (for a caller
    that reroutes the ripped nets afterwards). Returns {joined, failed, ripped: [uuid],
    ripped_soft: [uuid], rerouted: [net], added: [uuid], nets: {net: status}, undone}."""
    import time
    cap = max_joins if max_joins is not None else float("inf")

    def more():
        return joins < cap and (deadline is None or time.monotonic() < deadline)
    soft = set(soft or ())
    b = load(board)
    sp = Space(b, info, plan=plan, sev=sev or {})
    gr = _SoftRouter(sp)
    fp = _fill_polys(fills)
    fixed = set(fixed)
    rep = dict(joined=0, failed=0, ripped=[], added=[], nets={})
    known = sorted({it.net for it in sp.pads if it.net and it.kind == "pad"})
    if nets is None:
        nets = known
    else:
        # the DRC report names nets unescaped ("A/B" for the board's "A{slash}B")
        by_shown = {unescape(n): n for n in known}
        nets = [n if n in known else by_shown.get(n, n) for n in nets]
    queue = [net for net in nets if len([p for p in parts(sp, fp, net) if _relevant(p)]) > 1]
    # rip-up as transactions: an open net's join, and the re-joins of the nets it rips (and of
    # the nets those rip), are kept only when the nets touched end with fewer missing connections
    # than before; otherwise the new copper goes and the ripped copper comes back. A greedy
    # cascade made things worse in 16 of 20 rounds that ripped 30 or more items (fm4dd
    # i2c24io: 5 open -> 30); a net's copper gets dearer to rip each time (hist), and is left
    # alone after HIST_MAX rip-ups; what stays open goes back to the repair loop's router
    hist = {}
    ripped_ids = {}
    joins = 0
    open_now = {n: _open_count(sp, fp, n) for n in queue}   # nets the DRC did not name are whole

    def join_net(net, local, added, removed, before):
        """Join `net`'s parts (at most max_parts joins); nets it rips go to `local`. True when
        parts are still left after max_parts joins (a pour in many pieces)."""
        nonlocal joins
        widths = widths_of(sp, net)
        status = rep["nets"].setdefault(net, [])
        for _ in range(max_parts):
            ps = [p for p in parts(sp, fp, net) if _relevant(p)]
            if len(ps) < 2 or not more():
                return False
            small = ps[-1]
            src = _anchors(small, max(widths) / 2 + 0.02)
            if not src:
                status.append("no anchors")
                return False
            got = _join(gr, sp, net, src, ps[:-1], widths, fixed, hist, soft, rip)
            if got is None and not sp.via_in_pad:
                # a pad walled in by its own footprint (a microphone's centre pad inside its
                # ring) is left only through a via in the pad, as the human boards do it
                sp.via_in_pad = True
                try:
                    got = _join(gr, sp, net, src, ps[:-1], widths, fixed, hist, soft, rip)
                finally:
                    sp.via_in_pad = False
                if got is not None:
                    status.append("via in pad")
            if got is None:
                status.append("no route")
                rep["failed"] += 1
                return False
            rt, new, ripped = got
            joins += 1
            rep["joined"] += 1
            for it in new:
                it.owner = ("lastmile", joins)
            added += new
            removed += ripped
            hit = set()
            for it in ripped:
                if not _own(it):
                    ripped_ids[it.uuid] = it.net
                if it.net not in hit:
                    hit.add(it.net)
                    hist[it.net] = hist.get(it.net, 0) + 1
                before.setdefault(it.net, open_now.get(it.net, 0))
                if it.net != net and it.net not in local:
                    local.append(it.net)
            status.append(f"joined ({len(rt.segs)} segs, {len(rt.vias)} vias, ripped {len(ripped)})")
        return True

    while queue and more():
        root = queue.pop(0)
        added, removed, before, local = [], [], {root: open_now.get(root, 0)}, [root]
        saved = (dict(hist), dict(ripped_ids), rep["joined"], rep["failed"], joins)
        left = False
        while local and more() and joins - saved[4] < TXN_JOINS:
            net = local.pop(0)
            left |= join_net(net, local, added, removed, before) and net == root
        after = {n: _open_count(sp, fp, n) for n in before}
        if not txn or sum(after.values()) < sum(before.values()):
            open_now.update(after)
            # nets still open (a pour in many pieces, a ripped net not re-joined): their turn later
            queue += [n for n, v in after.items() if v and n not in queue and (n != root or left)]
            log(f"last mile {root}: kept, {sum(before.values())} -> {sum(after.values())} open on "
                f"{len(before)} nets ({joins - saved[4]} joins)")
            continue
        mine = {id(it) for it in added}
        sp.remove(added)
        _restore(sp, [it for it in removed if id(it) not in mine])
        hist.clear(); hist.update(saved[0])
        ripped_ids.clear(); ripped_ids.update(saved[1])
        rep["joined"], rep["failed"] = saved[2], saved[3] + 1
        rep["undone"] = rep.get("undone", 0) + 1
        log(f"last mile {root}: undone, {sum(before.values())} -> {sum(after.values())} open on "
            f"{len(before)} nets ({joins - saved[4]} joins)")
    rep["ripped"] = sorted(ripped_ids)
    rep["ripped_soft"] = sorted(u for u in ripped_ids if u in soft)
    rep["rerouted"] = sorted(n for n in set(ripped_ids.values())
                             if len([p for p in parts(sp, fp, n) if _relevant(p)]) < 2)
    rep["added"] = _write(sp, board, out, remove=rep["ripped"])
    # which join laid each new item: a caller may take out the joins KiCad's DRC faults
    rep["join_of"] = {it.uuid: it.owner[1] for it in sp.routed if _own(it)}
    boxes = {}
    for it in sp.routed:
        if _own(it):
            b, j = it.bbox, it.owner[1]
            o = boxes.get(j, b)
            boxes[j] = (min(o[0], b[0]), min(o[1], b[1]), max(o[2], b[2]), max(o[3], b[3]))
    rep["join_box"] = boxes
    return rep


DROP_NEAR = 0.5     # mm: an error that names no join's copper is put on the joins this close to it


def drop_joins(board, out, rep, report, types=None):
    """`out` = `board` without the joins (lastmile.close's `rep`) that an error of KiCad's DRC
    `report` of one of `types` (None: all) names, or, when it names none of them (a starved
    thermal names the zone and the pad), whose copper lies within DROP_NEAR of it. Returns
    the joins taken out (a set of join numbers)."""
    join_of = rep.get("join_of") or {}
    boxes = rep.get("join_box") or {}
    bad = set()
    for v in report.get("violations") or []:
        if v.get("severity") != "error" or (types is not None and v.get("type") not in types):
            continue
        named = {join_of[i.get("uuid")] for i in v.get("items") or [] if i.get("uuid") in join_of}
        if not named:
            for i in v.get("items") or []:
                p = i.get("pos") or {}
                x, y = p.get("x"), p.get("y")
                if x is None:
                    continue
                named |= {j for j, b in boxes.items() if b[0] - DROP_NEAR <= x <= b[2] + DROP_NEAR
                          and b[1] - DROP_NEAR <= y <= b[3] + DROP_NEAR}
        bad |= named
    if bad:
        W.edit(board, out, remove=[u for u, j in join_of.items() if j in bad])
    return bad


def _write(sp, board, out, remove=(), locked=True):
    """`out` = `board` without `remove` (uuids) plus the space's new copper (`locked` or not);
    returns the new copper's uuids."""
    tracks = [(it.net, next(iter(it.layers)), it.width, tuple(it.geom.coords[0]), tuple(it.geom.coords[-1]),
               it.uuid, locked) for it in sp.routed if it.kind == "track"]
    vias = [(it.net, it.geom.x, it.geom.y, it.width, it.drill, it.uuid, locked) for it in sp.routed if it.kind == "via"]
    W.edit(board, out, remove=list(remove)) if remove else W.edit(board, out)
    if tracks or vias:
        W.append_items(out, out, tracks=tracks, vias=vias)
    return [it.uuid for it in sp.routed]


def _open_count(sp, fp, net):
    """Missing connections of `net` as its parts count them (parts - 1)."""
    return max(0, len([p for p in parts(sp, fp, net) if _relevant(p)]) - 1)


def _relevant(part):
    """A part KiCad's ratsnest counts: it holds a pad, or zone fill that a track or via of the
    net reaches (track-only parts are tails; a fill piece nothing reaches is an island KiCad
    keeps or drops by the zone's island rule, never a missing connection)."""
    kinds = {n.kind for n in part}
    return "pad" in kinds or ("fill" in kinds and bool(kinds & {"track", "via"}))


def _commit(sp, rt):
    """Add a route's copper to the space; None (nothing added) when two of its own vias
    break the same-net pitch or hole-to-hole distance (the search checks each via only
    against committed copper)."""
    new = []
    for (x, y) in rt.vias:
        if sp.via_violations(rt.net, x, y):
            sp.remove(new)
            return None
        it = sp.add_via(rt.net, x, y, owner=("lastmile", ""))
        it.uuid = W.new_uuid()
        new.append(it)
    for l, a, b2 in rt.segs:
        it = sp.add_track(rt.net, l, rt.width, a, b2, owner=("lastmile", ""))
        it.uuid = W.new_uuid()
        new.append(it)
    return new


# ----------------------------------------------------------------------------- plane escapes
ESCAPE_MARGINS = (0.5, 1.5)        # mm windows for a pad's escape to its plane: short ones only (a 3 mm one
                                   # took a channel on fm4dd i2c24io: 5 -> 10 open)


def plane_escapes(board, info, plan, fills, out, sev=None, log=print, deadline=None, margins=ESCAPE_MARGINS,
                  balls=True, escape_opts=None):
    """Join every pad of a plane net (a net with zone fill) that the fill does not reach to
    that fill, before any routing: a short stub and, where the fill is on another layer, a
    via (the human boards' "power first": a GND pin of a QFN gets its own via to the GND
    plane next to it); with `balls`, the ball grids' escape plans first (escape.run: dog-bones
    and escapes, `escape_opts`).
    `board` is the unrouted input with its project files beside it, `fills` its refilled
    zones (pcbnew_io.zone_fills). Searches stay within `margins` of the pad (no rip-up;
    what does not fit is left to the router). The new copper is written unlocked to `out`
    (the router may move or rip it). Returns {escaped, failed, nets: {net: [escaped,
    failed]}, added, escape (escape.run's report), dog_bones: (vias laid, balls planned)}."""
    import time
    b = load(board)
    sp = Space(b, info, plan=plan, sev=sev or {})
    gr = GridRouter(sp)
    fp = _fill_polys(fills)
    rep = dict(escaped=0, failed=0, nets={}, added=[])
    if balls:
        # whole-package escape plans first (kae.route.escape): dog-bones and escapes of the
        # ball grids, and the certificate of what no routing can escape under the rules
        from . import escape
        esc = escape.run(sp, info, escape_opts, log=log,
                         deadline=None if deadline is None else time.monotonic() + 0.7 * max(0.0, deadline - time.monotonic()))
        rep["escape"] = esc
        rep["dog_bones"] = (sum(p.get("vias_laid", 0) for p in esc["packages"]), esc["wanted"])
    for net in sorted(fp):
        if deadline is not None and time.monotonic() > deadline:
            break
        if not any(it.net == net and it.kind == "pad" for it in sp.pads):
            continue
        mn, opt, _mx = sp.width_limits(net, sp.cu[0])
        widths = sorted({round(w, 4) for w in (opt, mn) if w and w > 0}, reverse=True) or [0.2]
        st = rep["nets"].setdefault(net, [0, 0])
        ps = parts(sp, fp, net)
        planes = [p for p in ps if any(n.kind == "fill" for n in p)]
        if not planes:
            continue
        for p in ps:
            if deadline is not None and time.monotonic() > deadline:
                break
            if any(n.kind == "fill" for n in p) or not any(n.kind == "pad" for n in p):
                continue
            src = _anchors(p, max(widths) / 2 + 0.02)
            if not src:
                continue
            got = None
            for m in margins:
                x0, y0, x1, y1 = _bounds(src)
                win = box(x0 - m, y0 - m, x1 + m, y1 + m)
                got = _try(gr, sp, net, src, planes, win, widths)
                if got is not None:
                    break
            if got is None:
                st[1] += 1
                rep["failed"] += 1
                continue
            st[0] += 1
            rep["escaped"] += 1
    # unlocked: ordinary copper the router may move or rip where a signal needs the room (locked,
    # one escape on fm4dd i2c24io took a channel: 5 -> 10 open)
    rep["added"] = _write(sp, board, out, locked=False)
    log(f"plane escapes: {rep['escaped']} escaped, {rep['failed']} left to the router "
        f"({', '.join(f'{n} {a}/{a + f}' for n, (a, f) in rep['nets'].items() if a or f)})")
    return rep
