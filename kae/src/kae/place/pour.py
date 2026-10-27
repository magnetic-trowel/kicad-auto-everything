# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Pour fragmentation of a placement, before routing: where each net's copper pours would
fill (fills are not read), and how many separate pieces they break into among that net's pads.

Per (net, copper layer) the fill region is the union of the net's board-level zones on the
layer, each one its outline inside the board edge (less the copper-to-edge clearance), less
higher-priority zones of other nets, copper-pour keepouts, and copper of other nets (pads,
tracks, vias, board copper graphics) grown by the clearance; then opened by the zone's
minimum width (KiCad drops fill thinner than that). The pieces on all layers form a graph:
a pad of the net touching pieces on several layers (through-hole) joins them, as do the
net's vias. Pieces with no pad of the net are islands KiCad removes; the rest are the
pour's components. Every component past the main one (most pads), and every pad on a poured
layer that touches no piece, is a connection the router has to make itself.
"""
from collections import defaultdict

import shapely
from shapely.geometry import Point

from kae.board import transform

CU_SUFFIX = ".Cu"


def _clr(board, net):
    r = board.rules
    v = float(r.clearance or 0.0) if r is not None else 0.0
    n = board.nets.get(net) if net else None
    if n is not None and r is not None:
        for name in (n.netclass, (n.netclass or "").split(",")[0], "Default"):
            nc = r.netclasses.get(name) if name else None
            if nc is not None:
                v = max(v, float(getattr(nc, "clearance", 0.0) or 0.0))
                break
    return v


def _pads(board):
    """[(ref, number, net, layers, geometry)] for every copper pad, in board coordinates."""
    from kae.place.legalize import pad_shape
    out = []
    for f in board.footprints:
        for pd in f.pads:
            lays = {ly for ly in (pd.layers or []) if ly.endswith(CU_SUFFIX)}
            if not lays:
                continue
            g = transform.place_geom(pad_shape(pd), f.x, f.y, f.rot, f.side)
            out.append((f.ref, pd.number, pd.net, lays, g, float(pd.clearance or 0.0)))
    return out


def _union(gs):
    gs = [g for g in gs if g is not None and not g.is_empty]
    return shapely.union_all(gs) if gs else None


def fragmentation(board, nets=None, pads=None, spoke=0.05, join_vias=True, wires=None):
    """{net: dict(layers, pads, poured_pads, components, stranded, unreached, needed,
    main_area, areas)} for each net with a board-level copper zone (or only `nets`).
    `needed` = (components - 1) + unreached: the connections the pour leaves to the router.
    join_vias=False leaves the net's own vias out (on a routed board: the stitching the
    router added, so the count is what the router had to connect). `wires`: extra copper of
    other nets, {layer: [(net, geometry)]} (an estimate of the routing to come)."""
    pads = _pads(board) if pads is None else pads
    edge = float(board.rules.edge_clearance or 0.0) if board.rules is not None else 0.0
    inside = _union([p.buffer(-edge) if edge > 0 else p for p in (board.outline or [])])
    zones = [z for z in board.zones or [] if not getattr(z, "footprint", "") and z.net
             and z.outline is not None and not z.outline.is_empty]
    want = sorted({z.net for z in zones} if nets is None else set(nets))
    cu_layers = sorted({ly for z in zones for ly in z.layers if ly.endswith(CU_SUFFIX)})
    keep = {ly: _union([k.outline for k in board.keepouts or [] if k.copperpour and ly in k.layers]) for ly in cu_layers}
    tracks = defaultdict(list)
    for t in board.tracks or []:
        g = shapely.LineString([t.start, t.end]).buffer(t.width / 2)
        tracks[t.layer].append((t.net, g))
    vias = []
    for v in board.vias or []:
        g = Point(v.x, v.y).buffer(float(v.size) / 2)
        vias.append((v.net, set(cu_layers) if v.type == "through" else set(v.layers or cu_layers), g))
    graphics = getattr(board, "graphics", None) or {}
    out = {}
    for net in want:
        mine = [z for z in zones if z.net == net]
        if not mine:
            continue
        zclr = max(float(z.clearance or 0.0) for z in mine)
        mt = max(float(z.min_thickness or 0.0) for z in mine) or 0.25
        pieces = []            # (layer, polygon)
        for ly in sorted({ly for z in mine for ly in z.layers if ly.endswith(CU_SUFFIX)}):
            regs = []
            for z in mine:
                if ly not in z.layers:
                    continue
                g = z.outline if inside is None else z.outline.intersection(inside)
                pz = int(z.priority or 0)
                for h in zones:
                    if h.net != net and ly in h.layers and int(h.priority or 0) > pz:
                        g = g.difference(h.outline.buffer(max(float(z.clearance or 0.0), float(h.clearance or 0.0))))
                regs.append(g)
            reg = _union(regs)
            if reg is None:
                continue
            if keep.get(ly) is not None:
                reg = reg.difference(keep[ly])
            obst = []
            for ref, num, pn, lays, g, lc in pads:
                if ly in lays and pn != net:
                    obst.append(g.buffer(max(zclr, _clr(board, pn), _clr(board, net), lc)))
            for tn, g in list(tracks.get(ly, ())) + list((wires or {}).get(ly, ())):
                if tn != net:
                    obst.append(g.buffer(max(zclr, _clr(board, tn))))
            for vn, lays, g in vias:
                if ly in lays and vn != net:
                    obst.append(g.buffer(max(zclr, _clr(board, vn))))
            for g in graphics.get(ly, ()):
                obst.append(g.buffer(zclr))
            ob = _union(obst)
            fill = reg.difference(ob) if ob is not None else reg
            fill = fill.buffer(-mt / 2, quad_segs=4).buffer(mt / 2, quad_segs=4)
            for q in getattr(fill, "geoms", [fill]):
                if not q.is_empty and q.area > 1e-6:
                    pieces.append((ly, q))
        # union-find over pieces; pads and vias of the net join the pieces they touch
        parent = list(range(len(pieces)))

        def find(a):
            while parent[a] != a:
                parent[a] = parent[parent[a]]
                a = parent[a]
            return a
        tree = shapely.STRtree([q for _, q in pieces]) if pieces else None
        layers_poured = {ly for ly, _ in pieces} | {ly for z in mine for ly in z.layers if ly.endswith(CU_SUFFIX)}
        pad_hits = []
        for ref, num, pn, lays, g, lc in pads:
            # the pads the pour is drawn over: a pad outside every outline of the net's zones
            # on its layers is the router's to connect, placement or not
            if pn != net or not any(ly in lays and z.outline.intersects(g) for z in mine for ly in z.layers):
                continue
            hit = []
            if tree is not None:
                reach = g.buffer(zclr + spoke)
                for k in tree.query(reach):
                    if pieces[k][0] in lays and pieces[k][1].intersects(reach):
                        hit.append(int(k))
            for k in hit[1:]:
                parent[find(k)] = find(hit[0])
            pad_hits.append(((ref, num), hit))
        for vn, lays, g in vias:
            if join_vias and vn == net and tree is not None:
                hit = [int(k) for k in tree.query(g) if pieces[k][0] in lays and pieces[k][1].intersects(g)]
                for k in hit[1:]:
                    parent[find(k)] = find(hit[0])
        comp_pads = defaultdict(list)
        unreached = []
        for key, hit in pad_hits:
            if hit:
                comp_pads[find(hit[0])].append(key)
            else:
                unreached.append(key)
        area = defaultdict(float)
        for k, (ly, q) in enumerate(pieces):
            area[find(k)] += q.area
        comps = sorted(comp_pads, key=lambda c: (-len(comp_pads[c]), -area[c]))
        main = comps[0] if comps else None
        out[net] = dict(layers=sorted(layers_poured), pads=len(pad_hits), components=len(comps),
                        stranded=sum(len(comp_pads[c]) for c in comps[1:]), unreached=len(unreached),
                        needed=max(0, len(comps) - 1) + len(unreached),
                        main_area=round(area[main], 2) if main is not None else 0.0,
                        areas=[round(area[c], 2) for c in comps], comp_pads=[len(comp_pads[c]) for c in comps],
                        stranded_pads=[f"{r}.{n}" for c in comps[1:] for r, n in comp_pads[c]],
                        unreached_pads=[f"{r}.{n}" for r, n in unreached])
    return out


def mst_wires(board, pads=None, skip=(), width=None):
    """A crude estimate of the routing to come: each net's minimum spanning tree over its
    pads as straight tracks of the net's width, on the layer the two pads share when one of
    them is SMD (SMD-to-SMD on one side; through-hole to SMD on the SMD's side); edges
    between two through-hole pads are left out (the router picks their layer).
    {layer: [(net, LineString buffered to the track)]}."""
    import numpy as np
    pads = _pads(board) if pads is None else pads
    by = defaultdict(list)
    for ref, num, net, lays, g, lc in pads:
        if net and net not in skip:
            c = g.centroid
            by[net].append((c.x, c.y, lays))
    r = board.rules
    out = defaultdict(list)
    for net, pts in by.items():
        if len(pts) < 2:
            continue
        w = width
        if w is None:
            n = board.nets.get(net)
            nc = r.netclasses.get(n.netclass) if (r is not None and n is not None and n.netclass) else None
            w = float(getattr(nc, "track_width", 0.0) or 0.0) or (float(r.track_min or 0.0) if r else 0.0) or 0.2
        xy = np.array([(x, y) for x, y, _ in pts])
        n = len(pts)
        inn = np.zeros(n, bool)
        inn[0] = True
        d = np.hypot(*(xy - xy[0]).T)
        par = np.zeros(n, int)
        for _ in range(n - 1):
            d2 = np.where(inn, np.inf, d)
            k = int(np.argmin(d2))
            inn[k] = True
            a, b = pts[par[k]], pts[k]
            la, lb = a[2], b[2]
            if len(la) == 1 or len(lb) == 1:
                common = (la & lb) if len(la) == 1 and len(lb) == 1 else (la if len(la) == 1 else lb) & (la | lb)
                if common:
                    ly = sorted(common)[0]
                    seg = shapely.LineString([(a[0], a[1]), (b[0], b[1])]).buffer(w / 2, quad_segs=2)
                    out[ly].append((net, seg))
            nd = np.hypot(*(xy - xy[k]).T)
            upd = nd < d
            par[upd] = k
            d = np.minimum(d, nd)
    return dict(out)
