# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Dog-bones for ball grids (BGA, WLCSP, LGA), laid before routing with the plane escapes
(lastmile.plane_escapes, unlocked).

Human boards escape a ball grid ring by ring: the outer rings on the surface (as many as
tracks fit between two balls, plus one), each inner ball through a short stub to a via in
the diagonal gap of four balls, and each ball of a plane net through its own dog-bone. On
six BGAs of merit boards the human did so on 92 % of ring >= 2 balls; our routes left
39-49 % of ring 1-3 balls open while most of their via sites were still free (Freerouting
takes the outer rings' channels first and never plans the sites). With the dog-bones laid
first, opens fell 8-31 % (gecko5education, nekoink, sdi-mipi; tools/research/escape).

`dog_bones(sp)` adds them to the Space: inner rings first, the diagonal pointing away from
the package centre first, the net's routing width (then its minimum), the net's via; each
checked exactly (Space) against everything there. Nothing is a limit of our own: which
rings get one follows from the board's widths and clearances (`_capacity`).
"""
from __future__ import annotations

import math

from shapely.geometry import LineString, Point

from . import critical_write as W

MIN_BALLS = 16          # a ball grid has at least this many pads


def _grid(pts):
    """(pitch, angle, ring of each point) when `pts` form a square grid, else None."""
    nn = []
    for i, a in enumerate(pts):
        d, v = min((math.dist(a, b), (b[0] - a[0], b[1] - a[1])) for j, b in enumerate(pts) if j != i)
        nn.append((d, v))
    pitch, v = sorted(nn)[len(nn) // 2]
    tol = 0.03 * pitch + 0.005
    if pitch < 1e-3 or sum(1 for a in pts if sum(abs(math.dist(a, b) - pitch) < tol for b in pts) >= 4) < 4:
        return None
    ang = math.atan2(v[1], v[0]) % (math.pi / 2)
    cx, cy = sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)
    c, s = math.cos(-ang), math.sin(-ang)
    loc = [((x - cx) * c - (y - cy) * s, (x - cx) * s + (y - cy) * c) for x, y in pts]
    hx, hy = max(abs(u) for u, _ in loc), max(abs(w) for _, w in loc)
    return pitch, ang, loc, [round(min(hx - abs(u), hy - abs(w)) / pitch) for u, w in loc]


def _capacity(sp, net, layer, pitch, ball):
    """Tracks of `net`'s routing width that fit between two balls `ball` mm wide."""
    mn, opt, _ = sp.width_limits(net, layer)
    w, clr = opt or mn or 0.1, sp._generic_need(net, "track", layer) or 0.0
    return max(0, int((pitch - ball - clr + 1e-9) // (w + clr)))


def _starves(sp, net, geom, r, layers, zclr):
    """Copper of `net` (`geom` grown by r) within a zone clearance of another net's thermal-
    spoke strip: the filler pulls the pour back from it and cuts the spoke's landing
    (nekoink: decoupling caps under U100)."""
    return any(it.kind == "corridor" and it.net != net and it.geom.distance(geom) < r + zclr
               for l in layers for it in sp.query(l, geom.bounds, r + zclr))


def dog_bones(sp, info, log=print):
    """Lay the ball grids' dog-bones in `sp` (critical_space.Space) -> (laid, wanted)."""
    count = {}
    for it in sp.pads:
        if it.kind == "pad" and it.net:
            count[it.net] = count.get(it.net, 0) + 1
    zclr = max([float(z.get("clearance") or 0.0) for z in info.get("zones") or []] + [0.0])
    laid = wanted = 0
    for pads in sp.pads_by_fp.values():
        smd = [p for p in pads if p.kind == "pad" and p.smd and len(p.layers) == 1 and p.hole is None]
        if len(smd) < MIN_BALLS:
            continue
        med = sorted(p.geom.area for p in smd)[len(smd) // 2]
        balls = [p for p in smd if p.geom.area <= 4 * med]
        g = _grid([p.pos for p in balls]) if len(balls) >= MIN_BALLS else None
        if g is None:
            continue
        pitch, ang, loc, rings = g
        layer = next(iter(balls[0].layers))
        b = balls[0].geom.bounds
        first = _capacity(sp, balls[0].net or "", layer, pitch, min(b[2] - b[0], b[3] - b[1])) + 1
        todo = []
        for p, (u, w), r in zip(balls, loc, rings):
            plane = p.net and any(z[0] == p.net and z[1] != layer for z in sp.zones)
            if p.net and (plane or (r >= first and count[p.net] >= 2)):
                todo.append((-r, str(p.owner), p, u, w))
        n0 = laid
        ca, sa = math.cos(ang), math.sin(ang)
        for _r, _o, p, u, w in sorted(todo, key=lambda t: t[:2]):
            mn, opt, _ = sp.width_limits(p.net, layer)
            diags = sorted(((a, c) for a in (1, -1) for c in (1, -1)), key=lambda d: -(d[0] * u + d[1] * w))
            done = False
            for du, dw in diags:
                lu, lw = du * pitch / 2, dw * pitch / 2
                v = (p.pos[0] + lu * ca - lw * sa, p.pos[1] + lu * sa + lw * ca)
                if sp.via_violations(p.net, *v, first=True) or \
                        _starves(sp, p.net, Point(v), sp.via_size(p.net)[0] / 2, sp.cu, zclr):
                    continue
                for wd in [x for x in dict.fromkeys([opt, mn]) if x] or [0.1]:
                    if sp.track_violations(p.net, layer, wd, p.pos, v, first=True) or \
                            _starves(sp, p.net, LineString([p.pos, v]), wd / 2, [layer], zclr):
                        continue
                    sp.add_via(p.net, *v, owner=("escape", ""), uuid=W.new_uuid())
                    sp.add_track(p.net, layer, wd, p.pos, v, owner=("escape", ""), uuid=W.new_uuid())
                    done = True
                    break
                if done:
                    break
            laid += done
        wanted += len(todo)
        log(f"dog-bones {balls[0].owner[0]}: pitch {pitch:.3f}, {len(balls)} balls, from ring {first}: "
            f"{laid - n0} of {len(todo)}")
    return laid, wanted
