# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Escape pre-pass: dog-bone fanout of grid packages (BGA, WLCSP, LGA grids) laid before
the router runs.

Human boards escape a ball grid ring by ring: the outer rings on the surface (as many rings
as tracks fit between two balls, plus one), every inner ball through a short stub to a via
in the diagonal gap between four balls (a dog-bone), and every ball of a net with a plane
(power, ground) through its own dog-bone to the plane. On the 6 BGAs of the rules-escape
study (merit boards with a complete human layout) the human used a dog-bone or a via in pad
on 92 % of ring >= 2 balls; our routes left 39-49 % of ring 1-3 balls open, and 56 % of the
open inner balls still had all four diagonal via sites free: Freerouting's maze search
(fanout off, bridge.DEFAULT_OPTS) takes outer rings' surface channels first and never
plans the via sites.

`plan_escapes` finds the grid packages, gives each ball that needs one a dog-bone (stub of
the net's routing width, narrowed to its minimum when that is what fits, and a via of the
net's size, both checked exactly against everything already there and against the escapes
laid before it), trying the diagonal that points away from the package centre first (the
quadrant pattern: inner layers keep channels between the via rows), inner rings first. The
bridge lays them as locked copper before Freerouting (opts escapes "lock") or unlocks them
after the first routing so repair and the last mile may rip them ("soft").

    plan_escapes(board_path, info, plan, sev=None, opts=None) -> dict(tracks, vias, report)

Lengths are mm. Nothing here is a limit of its own: widths, vias and clearances are the
bridge's (critical_space.Space over constraints.plan); which rings get dog-bones is
`escape_ring` (default: the surface capacity, as the human boards do), overridable.
"""
from __future__ import annotations

import math

from shapely.geometry import LineString, Point

from kae.board.kicad_file import load

from .critical_space import EXACT_TOL, TOL, Space

MIN_GRID_PADS = 16      # a grid package has at least this many signal pads
STEP = 0.01             # mm: the walk along a pad axis (row escapes)
WALK = 5.0              # mm beyond the pad at most (row escapes)


def _grid(pads):
    """(pitch, angle, centre, ring of each pad) when `pads` form a 2-D grid, else None."""
    if len(pads) < MIN_GRID_PADS:
        return None
    pts = [p.pos for p in pads]
    nn = []
    vec = []
    for i, a in enumerate(pts):
        best, bv = 1e9, None
        for j, b in enumerate(pts):
            if i != j:
                d = math.dist(a, b)
                if 1e-3 < d < best:
                    best, bv = d, (b[0] - a[0], b[1] - a[1])
        nn.append(best)
        vec.append(bv)
    order = sorted(range(len(nn)), key=lambda k: nn[k])
    pitch = nn[order[len(order) // 2]]
    v = vec[order[len(order) // 2]]
    ang = math.atan2(v[1], v[0]) % (math.pi / 2)
    tol = 0.03 * pitch + 0.005
    four = 0
    for a in pts:
        k = sum(1 for b in pts if b is not a and abs(math.dist(a, b) - pitch) < tol)
        if k >= 4:
            four += 1
    if four < 4:
        return None
    cx = sum(p[0] for p in pts) / len(pts)
    cy = sum(p[1] for p in pts) / len(pts)
    ca, sa = math.cos(-ang), math.sin(-ang)
    loc = [((x - cx) * ca - (y - cy) * sa, (x - cx) * sa + (y - cy) * ca) for x, y in pts]
    hx = max(abs(u) for u, _ in loc)
    hy = max(abs(w) for _, w in loc)
    rings = [int(round(min(hx - abs(u), hy - abs(w)) / pitch)) for u, w in loc]
    return pitch, ang, (cx, cy), loc, rings


def _capacity(sp, net, layer, pitch, ball):
    """Tracks of `net`'s routing width that pass between two balls `ball` mm wide."""
    mn, opt, _ = sp.width_limits(net, layer)
    w = opt or mn or 0.1
    clr = sp._generic_need(net, "track", layer) or 0.0
    room = pitch - ball
    n = 0
    while room >= (n + 1) * w + (n + 2) * clr - 1e-9:
        n += 1
    return n


def plan_escapes(board_path, info, plan, sev=None, opts=None, space=None, log=None):
    """The dog-bones the board's grid packages need (see the module docstring)."""
    opts = opts or {}
    sp = space if space is not None else Space(load(board_path), info, plan=plan, sev=sev or {})
    pads_of_net = {}
    for it in sp.pads:
        if it.kind == "pad" and it.net:
            pads_of_net[it.net] = pads_of_net.get(it.net, 0) + 1
    tracks, vias, rep = [], [], dict(packages=[], escaped=0, failed=0, why={})
    # thermal-spoke strips of other nets' zone pads: the strip is kept clear of copper, but
    # the zone filler also pulls fill back from new copper by the zone's clearance, so a via
    # beside a strip cuts the spoke's landing (nekoink: B.Cu decoupling caps under U100)
    zclr = max([float(z.get("clearance") or 0.0) for z in info.get("zones") or []] + [0.0])
    zmin = max([float(z.get("min_thickness") or 0.0) for z in info.get("zones") or []] + [0.0])
    cors = [c for cs in sp.corridors_by_fp.values() for c in cs]
    guard = opts.get("escape_spoke_guard", True)     # off when the caller checks with KiCad's DRC

    def near_corridor(net, geom, r, layers):
        for c in cors:
            if c.net != net and (c.layers & layers) and c.geom.distance(geom) < r + zclr:
                return True
        return False
    ring_opt = opts.get("escape_ring")
    for fp, pads in sp.pads_by_fp.items():
        smd = [p for p in pads if p.kind == "pad" and p.smd and len(p.layers) == 1 and p.hole is None]
        if len(smd) < MIN_GRID_PADS:
            continue
        areas = sorted(p.geom.area for p in smd)
        med = areas[len(areas) // 2]
        sig = [p for p in smd if p.geom.area <= 4 * med + 1e-12]
        g = _grid(sig)
        if g is None:
            continue
        pitch, ang, (cx, cy), loc, rings = g
        layer = next(iter(sig[0].layers))
        b = sig[0].geom.bounds
        ball = min(b[2] - b[0], b[3] - b[1])
        cap = _capacity(sp, sig[0].net or "", layer, pitch, ball)
        first = cap + 1 if ring_opt is None else int(ring_opt)
        ca, sa = math.cos(ang), math.sin(ang)
        todo = []
        for p, (u, w), r in zip(sig, loc, rings):
            if not p.net:
                continue
            plane = any(z[0] == p.net and z[1] != layer for z in sp.zones)
            if pads_of_net.get(p.net, 0) < 2 and not plane:
                continue
            if r < first and not plane:
                continue
            todo.append((-r, p, u, w))
        todo.sort(key=lambda t: (t[0], str(t[1].owner)))
        done = fail = 0
        for _r, p, u, w in todo:
            su = 1.0 if u > 1e-6 else (-1.0 if u < -1e-6 else 0.0)
            sw = 1.0 if w > 1e-6 else (-1.0 if w < -1e-6 else 0.0)
            diags = [(a, c) for a in (1.0, -1.0) for c in (1.0, -1.0)]
            diags.sort(key=lambda d: -(d[0] * su + d[1] * sw))
            mn, opt, _ = sp.width_limits(p.net, layer)
            widths = [x for x in dict.fromkeys([opt, mn]) if x and x > 0] or [0.1]
            c = p.pos
            ok = False
            for du, dw in diags:
                lu, lw = du * pitch / 2, dw * pitch / 2
                vx, vy = c[0] + lu * ca - lw * sa, c[1] + lu * sa + lw * ca
                bad = sp.via_violations(p.net, vx, vy, first=True)
                if bad:
                    k = getattr(bad[0][0], "kind", bad[0][0])
                    rep["why"][f"via:{k}"] = rep["why"].get(f"via:{k}", 0) + 1
                    continue
                D, d = sp.via_size(p.net)
                if guard and near_corridor(p.net, Point(vx, vy), D / 2, frozenset(sp.cu)):
                    rep["why"]["via:spokes"] = rep["why"].get("via:spokes", 0) + 1
                    continue
                for wd in widths:
                    bad = sp.track_violations(p.net, layer, wd, c, (vx, vy), first=True)
                    if bad:
                        k = getattr(bad[0][0], "kind", bad[0][0])
                        rep["why"][f"stub:{k}"] = rep["why"].get(f"stub:{k}", 0) + 1
                        continue
                    if guard and near_corridor(p.net, LineString([c, (vx, vy)]), wd / 2, frozenset([layer])):
                        rep["why"]["stub:spokes"] = rep["why"].get("stub:spokes", 0) + 1
                        continue
                    sp.add_via(p.net, vx, vy, owner=("escape", ""))
                    sp.add_track(p.net, layer, wd, c, (vx, vy), owner=("escape", ""))
                    vias.append((p.net, vx, vy, D, d))
                    tracks.append((p.net, layer, wd, tuple(c), (vx, vy)))
                    ok = True
                    break
                if ok:
                    break
            done += ok
            fail += not ok
        rep["packages"].append(dict(ref=sig[0].owner[0], pitch=round(pitch, 4), pads=len(sig), capacity=cap,
                                    first_ring=first, wanted=len(todo), escaped=done, failed=fail))
        rep["escaped"] += done
        rep["failed"] += fail
        if log:
            log(f"escapes {sig[0].owner[0]}: pitch {pitch:.3f}, {len(sig)} balls, {cap} track(s) between balls, "
                f"dog-bones from ring {first}: {done} of {len(todo)}")
    if opts.get("row_escapes", True):
        rows = plan_row_escapes(sp, log=log)
        tracks += rows
        rep["row_stubs"] = len(rows)
    return dict(tracks=tracks, vias=vias, report=rep)


# ----------------------------------------------------------------------------- row escapes
def _axes(geom, centre, away):
    """Unit directions along the axes of the pad's bounding rectangle, both ways, the one
    nearest `away` (outward from the footprint) first; and the pad's half diagonal."""
    rect = geom.minimum_rotated_rectangle
    pts = list(rect.exterior.coords)[:4] if rect.geom_type == "Polygon" else []
    if len(pts) < 4:
        return [], 0.0
    out = []
    for p, q in ((pts[0], pts[1]), (pts[1], pts[2])):
        dx, dy = q[0] - p[0], q[1] - p[1]
        n = math.hypot(dx, dy)
        if n > 1e-9:
            out += [(dx / n, dy / n), (-dx / n, -dy / n)]
    out.sort(key=lambda d: -(d[0] * away[0] + d[1] * away[1]))
    return out, max(math.dist(centre, p) for p in pts)


def _walk(sp, net, layer, c, d, reach, w_piece, w_end, tol_piece):
    """The first point p along d from c where the piece c -> p (width w_piece, tol_piece above
    each requirement) is legal and a track of width w_end may start at p; None when the piece
    stops being legal first or `reach` is passed."""
    k = 1
    while k * STEP <= reach:
        p = (c[0] + k * STEP * d[0], c[1] + k * STEP * d[1])
        k += 1
        if sp.track_violations(net, layer, w_piece, c, p, first=True, tol=tol_piece):
            return None
        if not sp.track_violations(net, layer, w_end, p, p, first=True):
            return p
    return None


def plan_row_escapes(sp, log=None):
    """Straight stubs out of pads that no track of the net's routing width can leave (zero
    slack: a 0.4 mm-pitch pin 0.2 mm wide at 0.2 mm clearance): the narrowest legal width,
    from the pad centre along an axis (outward first), checked at EXACT_TOL, out to the first
    point where a track of the routing width can start. Freerouting never enters such a pin
    (its neck-down keeps a board unit); with the stub laid it connects to the stub's end.
    Pads are taken odd numbers first so neighbours' stubs end staggered. -> [(net, layer, w,
    a, b)]"""
    pads_of_net = {}
    for it in sp.pads:
        if it.kind == "pad" and it.net:
            pads_of_net[it.net] = pads_of_net.get(it.net, 0) + 1
    zone_nets = {z[0] for z in sp.zones}
    cand = []
    for it in sp.pads:
        if it.kind != "pad" or not it.net or (pads_of_net.get(it.net, 0) < 2 and it.net not in zone_nets):
            continue
        if it.hole is not None or len(it.layers) != 1:
            continue
        layer = next(iter(it.layers))
        mn, opt, _mx = sp.width_limits(it.net, layer)
        if not opt:
            continue
        mn = mn or opt
        c = it.pos
        own = [p for p in sp.pads_by_fp.get(it.fp) or [] if p.kind == "pad"]
        fx = sum(p.pos[0] for p in own) / len(own) if own else c[0]
        fy = sum(p.pos[1] for p in own) / len(own) if own else c[1]
        away = (c[0] - fx, c[1] - fy)
        n = math.hypot(*away)
        away = (away[0] / n, away[1] / n) if n > 1e-9 else (0.0, 0.0)
        dirs, half = _axes(it.geom, c, away)
        if not dirs:
            continue
        reach = half + WALK
        g = it.geom
        ring = g.exterior if g.geom_type == "Polygon" else g.boundary
        n_pts = max(8, int(ring.length / STEP / 2))
        pts = [c] + [ring.interpolate(k / n_pts, normalized=True).coords[0] for k in range(n_pts)]
        if any(not sp.track_violations(it.net, layer, opt, q, q, first=True) for q in pts):
            continue
        if any(_walk(sp, it.net, layer, c, d, reach, opt, opt, TOL) is not None for d in dirs):
            continue
        num = str((it.owner or ("", ""))[1])
        par = int(num) % 2 == 0 if num.isdigit() else True
        cand.append((par, str(it.owner), it, layer, mn, opt, c, dirs, reach))
    out = []
    for _par, _own, it, layer, mn, opt, c, dirs, reach in sorted(cand, key=lambda t: (t[0], t[1])):
        for w in dict.fromkeys([opt, mn]):
            got = None
            for d in dirs:
                p = _walk(sp, it.net, layer, c, d, reach, w, opt, EXACT_TOL)
                if p is not None:
                    got = p
                    break
            if got is not None:
                sp.add_track(it.net, layer, w, c, got, owner=("escape", ""))
                out.append((it.net, layer, w, tuple(c), got))
                break
    if log:
        log(f"row escapes: {len(out)} of {len(cand)} zero-slack pads")
    return out
