# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The board's fixed copper zones as placement facts: parts sit over their own nets' zones,
and other nets' pads stay out of outer-layer zones where their mask opening would bridge.

In the place-fixed and joint-fixed tasks the human's zones stay where they were while every
part moves. A placer that ignores them strands the pours (board studies, kae staged at
21bc53d): polarfire-som's power pads over a zone of their own net, human 404 / 469, kae
148-221 (the FPGA U1 11-21 / 78 core balls; +~217 open at equal routing time); nekoink's
In1 islands left their consumers (+1V35 45 / 50 pads over it for the human, 12-34 for kae)
and the plane escapes left 128-153 pads to the router instead of 15; gecko5 moved the FPGA
off its +1V2 In4 island (25 core balls need routed escapes instead of 3), and every DRC error
of its staged runs is a solder_mask_bridge between a moved pad and a fixed F.Cu power island.

Two annealer terms, both unary (a part's cost depends only on its own pose, as the zones
are fixed), priced on a raster of the zones at the placement grid (cells of `c` grid steps,
c * g ~ 0.1 mm):

- pull: each pad of a movable part whose net owns a fixed zone on a copper layer the pad
  reaches (an SMD pad: its own outer layer, and every inner layer through a via; a drilled
  pad: every layer) costs its weight when its centre is not over that net's fill region
  there (the zone outline less higher-priority zones of other nets, as KiCad fills).
  Weights: net kind (ground / power 1, signal 0.5) / sqrt(the net's eligible pads), so a
  net with many pads does not drown the islands; normalized so that every eligible pad off
  its zone costs `zone_pull`. Nets whose region covers nearly the whole board (a solid
  plane) are left out: every pad is over them wherever it goes.
- keep-out: a pad of another net (or of none) with copper and a mask opening on an outer
  layer whose fixed zone it would bridge: KiCad's test (exact.py, testMaskItemAgainstZones)
  fires when solder_mask_to_copper + the pad's mask expansion exceeds the gap the fill keeps
  from the pad and the pad's copper comes within that reach of the zone outline. Only such
  pads are priced (a board-wide GND pour with the usual mask rules has foreign pads all
  over it, harmlessly); each costs 0.1 x `zone_keepout` x the share of its five sample
  points (centre, corners) inside the outline grown by the reach.

Tables (`ZoneTerm`): `maps` (maps, nzx, nzy) uint16: a pull map holds each cell's distance to
the region in cells (0 inside), a keep-out map 1 inside the reach, else 0;
`ent` float rows: the first n * kmax rows are per (part, rotation) [start, count, 0, 0],
then entries [dx, dy, map, weight]: the pad sample at grid cell (X + dx, Y + dy) of the part
at (X, Y) lies in zone cell ((X + dx) // c, (Y + dy) // c); weight > 0 costs it when the
cell is off map m (pull: half the weight, plus half scaled by the distance up to `dz` cells,
so the annealer sees the way to the zone), weight < 0 costs -weight when on it (keep-out). anneal.Annealer
and engine.FastAnnealer read the same tables, so both price alike.
"""
from __future__ import annotations

import math
from collections import defaultdict

import numpy as np
import shapely

CU = ".Cu"
KIND_W = {"ground": 1.0, "power": 1.0}
SIGNAL_W = 0.5
KEEPOUT_PAD = 0.1        # cost of one bridging pad at zone_keepout 1 (seed HPWL = 1): a DRC error the
                         # exact repair could not undo on gecko5 (17 -> 17 at 0.02, 13 pads left)
FULL_SHARE = 0.9         # a net's region covering this share of the board is a solid plane (the
                         # outline inset by a pull-back: 0.92 on a 60 x 40 mm board with 1 mm)
RASTER_MM = 0.1


def entry_cost(v, w, dz):
    """One entry's cost at map value v (-1: off the raster). Pull (w > 0): 0 over the zone,
    else half its weight plus half scaled by the distance to the zone (cells, saturating at
    dz), so a part far from its zone still feels which way it lies. Keep-out (w < 0): -w
    inside the reach."""
    if w > 0.0:
        if v == 0:
            return 0.0
        if v < 0:
            return w
        f = v / dz
        return w * (0.5 + 0.5 * (f if f < 1.0 else 1.0))
    return -w if v > 0 else 0.0


class ZoneTerm:
    def __init__(self, c, maps, ent, kmax, info, pad=None, dz=1):
        self.c = int(c)
        self.dz = int(dz)
        self.maps = maps
        self.ent = ent
        self.kmax = int(kmax)
        self.info = info
        self.pad = pad            # per entry row: the pad index (reports)
        self.geoms = {}           # pull map -> its region (shapely), for the seed's anchors
        self.pull_of = {}         # movable part -> [(pad, pull map, kind weight)]

    def lattice(self, i, k, Xs, Ys):
        """Cost of part i at rotation k on every (X, Y) of the lattice Xs x Ys (vectorized
        part())."""
        h = i * self.kmax + k
        s, n = int(self.ent[h, 0]), int(self.ent[h, 1])
        out = np.zeros((len(Xs), len(Ys)))
        c = self.c
        nzx, nzy = self.maps.shape[1], self.maps.shape[2]
        for e in range(s, s + n):
            dx, dy, m, w = self.ent[e]
            cx = (Xs + int(dx)) // c
            cy = (Ys + int(dy)) // c
            okx = (cx >= 0) & (cx < nzx)
            oky = (cy >= 0) & (cy < nzy)
            v = self.maps[int(m)][np.clip(cx, 0, nzx - 1)][:, np.clip(cy, 0, nzy - 1)].astype(float)
            v = np.where(okx[:, None] & oky[None, :], v, -1.0)
            if w > 0:
                f = np.minimum(1.0, np.maximum(v, 0.0) / self.dz)
                out += np.where(v == 0, 0.0, np.where(v < 0, w, w * (0.5 + 0.5 * f)))
            else:
                out += np.where(v > 0, -w, 0.0)
        return out

    def part(self, i, X, Y, k):
        """Cost of part i at (X, Y, rotation k) (anneal.Annealer's reference)."""
        h = i * self.kmax + k
        s, n = int(self.ent[h, 0]), int(self.ent[h, 1])
        if n == 0:
            return 0.0
        c = self.c
        maps = self.maps
        nzx, nzy = maps.shape[1], maps.shape[2]
        tot = 0.0
        for e in range(s, s + n):
            dx, dy, m, w = self.ent[e]
            cx = (X + int(dx)) // c
            cy = (Y + int(dy)) // c
            v = int(maps[int(m), cx, cy]) if (0 <= cx < nzx and 0 <= cy < nzy) else -1
            tot += entry_cost(v, w, self.dz)
        return tot


def fixed_zones(board):
    """Board-level copper zones with a net: the ones the task keeps where they are (a
    footprint's own zones move with it; keepouts and rule areas are not zones here)."""
    return [z for z in board.zones or [] if not getattr(z, "footprint", "") and z.net
            and z.outline is not None and not z.outline.is_empty
            and any(ly.endswith(CU) for ly in z.layers or [])
            and not (z.name or "").startswith("kae-")]


def fill_regions(board, zones):
    """{(net, layer): region}: each net's zones on the layer less higher-priority zones of
    other nets kept their clearance away (fills are not read; as exact.ExactModel.zone_fill)."""
    out = {}
    by_layer = defaultdict(list)
    for z in zones:
        for ly in z.layers:
            if ly.endswith(CU):
                by_layer[ly].append(z)
    for ly, zs in by_layer.items():
        parts = defaultdict(list)
        for z in zs:
            g = z.outline
            pz = int(z.priority or 0)
            for h in zs:
                if h.net != z.net and int(h.priority or 0) > pz:
                    g = g.difference(h.outline.buffer(max(float(z.clearance or 0.0), float(h.clearance or 0.0))))
            if not g.is_empty:
                parts[z.net].append(g)
        for net, gs in parts.items():
            out[(net, ly)] = shapely.union_all(gs)
    return out


def _cu_layers(pd):
    return {ly for ly in pd.layers or [] if ly.endswith(CU)}


def pad_reach(pd, inner):
    """Copper layers a pad reaches: its own (a drilled pad lists every layer), and the inner
    layers through a via (an SMD pad on an outer layer)."""
    own = _cu_layers(pd)
    if not own:
        return set()
    return own | set(inner)


def _distance(inside):
    """uint16 cells to the nearest inside cell (0 inside; all cap when nothing is inside)."""
    from scipy.ndimage import distance_transform_edt
    if not inside.any():
        return np.full(inside.shape, 65535, np.uint16)
    d = np.ceil(distance_transform_edt(~inside))
    return np.minimum(d, 65535).astype(np.uint16)


def _raster(P, c, geom):
    """bool (nzx, nzy): zone cells (c grid steps) whose centre lies in geom."""
    g = P.g * c
    nzx, nzy = P.ncx // c + 2, P.ncy // c + 2
    out = np.zeros((nzx, nzy), bool)
    if geom is None or geom.is_empty:
        return out
    x0, y0, x1, y1 = geom.bounds
    i0 = max(0, int(math.floor((x0 - P.ox) / g)) - 1)
    i1 = min(nzx, int(math.ceil((x1 - P.ox) / g)) + 1)
    j0 = max(0, int(math.floor((y0 - P.oy) / g)) - 1)
    j1 = min(nzy, int(math.ceil((y1 - P.oy) / g)) + 1)
    if i1 <= i0 or j1 <= j0:
        return out
    xs = P.ox + (np.arange(i0, i1) + 0.5) * g
    ys = P.oy + (np.arange(j0, j1) + 0.5) * g
    XX, YY = np.meshgrid(xs, ys, indexing="ij")
    shapely.prepare(geom)
    out[i0:i1, j0:j1] = shapely.contains_xy(geom, XX, YY)
    return out


def _cell_off(v, g):
    """Grid cells from a part's origin to a point v mm from it (floor, as the lookup)."""
    return int(math.floor(v / g + 1e-9))


def build(P, pull=1.0, keepout=1.0, parts=None):
    """ZoneTerm for Problem P (None when no fixed zone prices anything). pull / keepout are
    the weights (0 = off); `parts`: the part indices to tabulate (default: every part, fixed
    ones too, so the report counts the whole board; the annealer moves only movable ones)."""
    from .exact import _local_clr, _npth_without_copper, mask_margin, mask_sides
    from .legalize import _net_clr
    from .problem import pad_corners
    from kae.board import transform
    board = P.board
    zones = fixed_zones(board)
    if not zones or (pull <= 0 and keepout <= 0):
        return None
    # zone cells ~0.1 mm, coarser on big boards (at most ~1M cells a map)
    cell = max(RASTER_MM, math.sqrt(max(1.0, P.ncx * P.ncy) * P.g * P.g / 1e6))
    c = max(1, int(round(cell / P.g)))
    regions = fill_regions(board, zones)
    inner = sorted({ly for (_, ly) in regions if not ly.startswith(("F.", "B."))})
    board_area = max(1e-9, float(P.outline.area)) if P.outline is not None else None
    maps = []                    # bool rasters
    key_map = {}

    geoms = {}

    def map_of(key, geom_fn):
        m = key_map.get(key)
        if m is None:
            m = len(maps)
            g = geom_fn()
            if key[0] == "pull":
                geoms[m] = g
            r = _raster(P, c, g)
            maps.append(_distance(r) if key[0] == "pull" else r.astype(np.uint16))
            key_map[key] = m
        return m

    net_layers = defaultdict(set)
    for (net, ly) in regions:
        net_layers[net].add(ly)
    name_kind = {n.name: n.kind for n in P.nets}
    clr_cache = {}
    rules = getattr(board, "rules", None)
    s2c = float(getattr(rules, "mask_to_copper", 0.0) or 0.0) if rules is not None else 0.0
    # no arc tolerance here: the fill keeps exactly the gap from a straight pad edge, and KiCad
    # flags a 0.102 mm mask expansion against a 0.1 mm gap (gecko5 U3 against +2V5 / +3.3V)
    tol = 1e-6
    outer_zones = defaultdict(list)          # layer -> [(net, outline, clearance)]
    for z in zones:
        for ly in z.layers:
            if ly in ("F.Cu", "B.Cu"):
                outer_zones[ly].append((z.net, z.outline, float(z.clearance or 0.0)))
    full = set()                             # (net, reach) whose region is a solid plane
    region_cache = {}

    def region(net, reach):
        k = (net, reach)
        if k not in region_cache:
            gs = [regions[(net, ly)] for ly in reach if (net, ly) in regions]
            region_cache[k] = shapely.union_all(gs) if gs else None
            r = region_cache[k]
            if r is not None and board_area is not None and P.outline is not None:
                if r.intersection(P.outline).area >= FULL_SHARE * board_area:
                    full.add(k)
        return region_cache[k]

    todo = range(len(P.parts)) if parts is None else parts
    raw = defaultdict(list)     # i -> [(pad k, kind, map, base weight, (lx, ly) library point)]
    pull_pads = defaultdict(list)    # net -> [(i, k)] movable eligible pads
    n_keep = 0
    for i in todo:
        p = P.parts[i]
        side = "F" if p.s > 0 else "B"
        for k, pd in enumerate(p.fp.pads):
            if _npth_without_copper(pd):
                continue
            cu = _cu_layers(pd)
            if not cu:
                continue
            if pull > 0 and pd.net and pd.net in net_layers:
                reach = tuple(sorted(pad_reach(pd, inner) & net_layers[pd.net]))
                if reach:
                    geom = region(pd.net, reach)
                    if geom is not None and (pd.net, reach) not in full:
                        m = map_of(("pull", pd.net, reach), lambda: geom)
                        raw[i].append((k, "pull", m, 1.0, (pd.lx, pd.ly)))
                        if p.movable:
                            pull_pads[pd.net].append((i, k))
            if keepout > 0:
                ms = mask_sides(pd)
                mm = mask_margin(P, pd)
                hit = False
                for ly, sd in (("F.Cu", 0), ("B.Cu", 1)):
                    if ly not in cu or sd not in ms:
                        continue
                    for net, outline, zc in outer_zones.get(ly, ()):
                        if pd.net and net == pd.net:
                            continue
                        gap = max(zc, _net_clr(P, pd.net, clr_cache), _net_clr(P, net, clr_cache), _local_clr(pd))
                        reach_mm = s2c + mm
                        if reach_mm <= gap + tol:
                            continue
                        rk = round(reach_mm, 3)
                        m = map_of(("keep", ly, net, rk), lambda o=outline, r=rk: o.buffer(r))
                        pts = [(pd.lx, pd.ly)] + [tuple(v) for v in pad_corners(pd)]
                        for q in pts:
                            raw[i].append((k, "keep", m, 1.0 / len(pts), q))
                        hit = True
                n_keep += hit
    if not maps:
        return None
    # pull weights: kind / sqrt(eligible pads of the net), normalized to zone_pull in total
    pw = {}
    for net, lst in pull_pads.items():
        kind = name_kind.get(net, "signal")
        pw[net] = KIND_W.get(kind, SIGNAL_W) / math.sqrt(len(lst))
    tot_pull = sum(pw[net] * len(lst) for net, lst in pull_pads.items()) or 1.0
    kmax = max([1] + [len(p.rots) for p in P.parts])
    n = len(P.parts)
    heads = np.zeros((n * kmax, 4))
    rows = []
    row_pad = []
    g = P.g
    for i in range(n):
        p = P.parts[i]
        ents = raw.get(i, [])
        if not ents:
            continue
        for kr, r in enumerate(p.rots[:kmax]):
            heads[i * kmax + kr, 0] = n * kmax + len(rows)
            cnt = 0
            for (k, kind, m, bw, (lx, ly)) in ents:
                if kind == "pull":
                    w = pull * pw.get(p.fp.pads[k].net, 0.0) / tot_pull if p.movable else 1.0
                    if w <= 0:
                        continue
                    vx, vy = float(r.pins[k, 0]), float(r.pins[k, 1])
                else:
                    w = -(keepout * KEEPOUT_PAD * bw if p.movable else bw)
                    px, py = transform.pads_xy(np.array([lx]), np.array([ly]), 0.0, 0.0, r.rot, p.s)
                    vx, vy = float(px[0]), float(py[0])
                if p.movable:
                    dx, dy = _cell_off(vx, g), _cell_off(vy, g)
                else:       # fixed parts: their input pose, as an offset from grid origin 0
                    dx, dy = _cell_off(p.x0 - P.ox + vx, g), _cell_off(p.y0 - P.oy + vy, g)
                rows.append((dx, dy, m, w))
                row_pad.append(k)
                cnt += 1
            heads[i * kmax + kr, 1] = cnt
    ent = np.vstack([heads, np.array(rows, float).reshape(-1, 4)]) if rows else heads
    planes = np.stack(maps).astype(np.uint16)
    nzx, nzy = planes.shape[1], planes.shape[2]
    dz = max(1, int(round(0.5 * max(nzx, nzy))))
    info = dict(zones=len(zones), maps=len(maps), cell_mm=round(c * g, 4),
                pull_nets=len(pull_pads), pull_pads=sum(len(v) for v in pull_pads.values()),
                keepout_pads=n_keep, solid_planes=sorted({k[0] for k in full}),
                pull=pull, keepout=keepout)
    pad = np.concatenate([np.full(n * kmax, -1, np.int64), np.array(row_pad, np.int64)])
    Z = ZoneTerm(c, planes, ent, kmax, info, pad=pad, dz=dz)
    Z.geoms = geoms
    for i, ents in raw.items():
        if P.parts[i].movable:
            lst = [(k, m, KIND_W.get(name_kind.get(P.parts[i].fp.pads[k].net, "signal"), SIGNAL_W))
                   for (k, kind, m, _, _) in ents if kind == "pull"]
            if lst:
                Z.pull_of[i] = lst
    return Z


def seed_anchors(Z, P, objs, pos, weight):
    """Quadratic-seed anchors {object: (x, y, w)} pulling each seed object that holds pads
    with a fixed zone of their net toward it: the target moves the object by the kind-weighted
    mean of its pads' steps to the nearest point of their zone; the anchor weight grows with
    those pads (weight x min(5, their kind weight / 4): the FPGA's 25 core balls as strongly
    as a connector's edge anchor, one capacitor pad a twentieth of that). The annealer alone
    cannot carry a big package back over its island (gecko5's U6, polarfire's U1)."""
    from shapely.geometry import Point
    from shapely.ops import nearest_points
    out = {}
    if Z is None or not Z.pull_of:
        return out
    for o, (members, w, h, rel) in enumerate(objs):
        sx = sy = sw = 0.0
        for i in members:
            for (k, m, kw) in Z.pull_of.get(i, ()):
                g = Z.geoms.get(m)
                if g is None or g.is_empty:
                    continue
                pin = P.parts[i].rots[0].pins[k]
                x = pos[o, 0] + rel[i][0] + pin[0]
                y = pos[o, 1] + rel[i][1] + pin[1]
                pt = Point(x, y)
                if g.contains(pt):
                    q = (x, y)
                else:
                    a = nearest_points(g, pt)[0]
                    q = (a.x, a.y)
                sx += kw * (q[0] - x)
                sy += kw * (q[1] - y)
                sw += kw
        if sw > 0:
            out[o] = (pos[o, 0] + sx / sw, pos[o, 1] + sy / sw, weight * min(5.0, sw / 4.0))
    return out


def report(P, st, Z=None):
    """Pads over their own net's fixed zone (of those that reach one; solid planes left out)
    and pads whose mask opening would bridge another net's outer fixed zone (any sample
    point in reach), for the whole board at state st (fixed parts at their input pose), as
    the board studies count them. Z: a table from build(P) (every part)."""
    if Z is None:
        Z = build(P, pull=1.0, keepout=1.0)
    out = dict(pads_on_own_zone=0, pads_with_zone=0, foreign_in_outer_zone=0)
    if Z is None:
        return out
    c = Z.c
    maps = Z.maps
    nzx, nzy = maps.shape[1], maps.shape[2]
    by_net = defaultdict(lambda: [0, 0])
    moved = [0, 0]
    foreign = set()
    for p in P.parts:
        i = p.i
        X, Y, k = (int(st.X[i]), int(st.Y[i]), int(st.K[i])) if p.movable else (0, 0, 0)
        h = i * Z.kmax + k
        s, cnt = int(Z.ent[h, 0]), int(Z.ent[h, 1])
        for e in range(s, s + cnt):
            dx, dy, m, w = Z.ent[e]
            cx, cy, m = (X + int(dx)) // c, (Y + int(dy)) // c, int(m)
            v = int(maps[m, cx, cy]) if (0 <= cx < nzx and 0 <= cy < nzy) else -1
            hit = v == 0 if w > 0 else v > 0
            pk = int(Z.pad[e])
            if w > 0:
                net = p.fp.pads[pk].net
                by_net[net][0] += hit
                by_net[net][1] += 1
                if p.movable:
                    moved[0] += hit
                    moved[1] += 1
            elif hit:
                foreign.add((i, pk))
    out.update(pads_on_own_zone=sum(v[0] for v in by_net.values()), pads_with_zone=sum(v[1] for v in by_net.values()),
               movable_on_own_zone=moved[0], movable_with_zone=moved[1], foreign_in_outer_zone=len(foreign),
               foreign_movable=sum(1 for (i, _) in foreign if P.parts[i].movable),
               by_net={n: v for n, v in sorted(by_net.items(), key=lambda t: -t[1][1])[:12]})
    return out


PIN_MIN = 8.0            # kind-weighted pads with a zone a part needs to be pinned over it


def pin_packages(Z, P, objs, pos, min_pads=PIN_MIN, step_mm=0.5):
    """{object: (X, Y, K)}: single-part seed objects with at least `min_pads` (kind-weighted)
    pads on fixed zones of their nets, put where the zone term is least (searched on a
    step_mm lattice, every right-angle rotation, inside the outline and off fixed obstacles
    and each other; nearest the quadratic position on a tie), largest first. A big package
    owns its island: gecko5's FPGA U6 has 25 +1V2 core balls over a fixed In4 island and the
    quadratic seed put it near it (125, 70 mm; island 114-142 x 65-106), but the density
    spread then moved it 50 mm away, where the annealer cannot bring it back."""
    if Z is None or not Z.pull_of:
        return {}
    g = P.g
    s = max(1, int(round(step_mm / g)))
    cand = []
    for o, (members, w, h, rel) in enumerate(objs):
        if len(members) != 1:
            continue
        i = members[0]
        kw = sum(k for (_, _, k) in Z.pull_of.get(i, ()))
        if kw >= min_pads:
            cand.append((-P.parts[i].area, o, i))
    out = {}
    taken = []                  # (side, grid rect) of the pinned ones
    for _, o, i in sorted(cand):
        p = P.parts[i]
        side = 0 if p.s > 0 else 1
        n_ortho = getattr(p, "n_ortho", len(p.rots))
        qx, qy = pos[o, 0] + objs[o][3][i][0], pos[o, 1] + objs[o][3][i][1]   # quadratic origin, mm
        best = None
        for k in range(n_ortho):
            r = p.rots[k]
            a, b, c, d = r.g_own
            blocks = [ob.g for ob in P.obstacles if ob.side == side or p.tht] + \
                     [t for sd, t in taken if sd == side or p.tht]
            Xs = np.arange(-a, P.ncx - b + 1, s)
            Ys = np.arange(-c, P.ncy - d + 1, s)
            if not len(Xs) or not len(Ys):
                continue
            cost = Z.lattice(i, k, Xs, Ys)
            ok = np.ones(cost.shape, bool)
            for (t0, t1, u0, u1) in blocks:
                ok &= ~(((Xs + a) < t1) & (t0 < (Xs + b)))[:, None] | ~(((Ys + c) < u1) & (u0 < (Ys + d)))[None, :]
            dist = np.sqrt(((P.ox + Xs * g - qx) ** 2)[:, None] + ((P.oy + Ys * g - qy) ** 2)[None, :])
            key = np.where(ok, np.round(cost, 9) * 1e9 + dist * 1e-3, np.inf)
            for _ in range(64):         # the best few by the lattice key, checked on the outline
                f = int(np.argmin(key))
                if not np.isfinite(key.flat[f]):
                    break
                xi, yi = np.unravel_index(f, key.shape)
                X, Y = int(Xs[xi]), int(Ys[yi])
                if P.outside_cells_all(X, Y, r.g_boards or (r.g_board,)):
                    key[xi, yi] = np.inf
                    continue
                kk = (round(float(cost[xi, yi]), 9), float(dist[xi, yi]))
                if best is None or kk < best[0]:
                    best = (kk, X, Y, k)
                break
        if best is None:
            continue
        _, X, Y, k = best
        a, b, c, d = p.rots[k].g_own
        taken.append((side, (X + a, X + b, Y + c, Y + d)))
        out[o] = (X, Y, k)
    return out


def annealer_args(P, board_path=None, opts=None):
    """{zones, w_zone} for make_annealer with the run's zone_pull / zone_keepout settings
    (kae.route.constraints), {} when off or nothing to price: the joint loop's local
    re-placements keep parts on their zones as the first placement did."""
    from kae.route.constraints import setting
    pull = float(setting("zone_pull", board_path, opts))
    keep = float(setting("zone_keepout", board_path, opts))
    Z = build(P, pull=pull, keepout=keep) if (pull > 0 or keep > 0) else None
    return dict(zones=Z, w_zone=1.0) if Z is not None else {}
