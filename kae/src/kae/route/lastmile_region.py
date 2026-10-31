# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Experimental: a region re-route on the last mile's grid (PathFinder-style negotiated
congestion inside one window). Not called by the pipeline.

Measured on the final boards of the merge2 route experiment (seed 0, every open connection,
windows of 1 and 3 mm around the open part and its nearest other part): it closed none of the
open connections on fm4dd i2c24io, kata0510 rp2040, noggin, paicorea, atlantis can485 or
bancouver40, and skipped siderakb ergo-snm (more than REGION_NETS nets). The rounds did not
converge: fm4dd kept 8-15 conflicts between 16-21 nets after 20 rounds, paicorea's USB-C 2-5.
Kept for the record; the repair loop's "region" level (repair.region_rip, the same region
re-routed by Freerouting, opts region_level) was no better.
"""
from __future__ import annotations

from shapely.geometry import box

from . import critical_write as W
from .lastmile import _anchors, _conflicts, _relevant, _restore, _try, _window, parts

REGION_MARGINS = (1.0, 3.0)     # mm around a part and the nearest other part: regions re-routed whole
REGION_ITERS = 20               # negotiation rounds per region at most
REGION_NETS = 30                # nets in a region at most
REGION_PRES = (2.0, 1.5)        # present-congestion cost per cell crossed: first round, growth per round
REGION_HIST = 1.0               # history cost added per round a net's route was in conflict
REGION_DEBUG = False


def _why(sp, it, new):
    if it.kind == "track":
        c = list(it.geom.coords)
        vs = sp.track_violations(it.net, next(iter(it.layers)), it.width, c[0], c[-1])
    else:
        vs = sp.via_violations(it.net, it.geom.x, it.geom.y, size=it.width, drill=it.drill, layers=list(it.layers))
    return [(v[0].net, v[0].kind, [round(x, 3) for x in v[1:3]]) for v in vs if v[0] in new][:2]


def _clip_outside(sp, it, win):
    """The pieces of track `it` outside `win`, added back as copper of the same net (a cut
    track keeps its connection to whatever lies outside the region)."""
    out = []
    rest = it.geom.difference(win)
    layer = next(iter(it.layers))
    for g in getattr(rest, "geoms", [rest]):
        if g.is_empty or g.geom_type != "LineString" or g.length < 1e-4:
            continue
        c = list(g.coords)
        for a, b2 in zip(c[:-1], c[1:]):
            t = sp.add_track(it.net, layer, it.width, a, b2, owner=("lastmile", "clip"))
            t.uuid = W.new_uuid()
            out.append(t)
    return out


def _region(gr, sp, fp, net, src, others, margin, rippable, deadline=None, log=None):
    """Re-route a whole region at once (PathFinder's negotiated congestion inside one window):
    every rippable track and via in the window around `src` and the nearest other part is taken
    out (tracks crossing its border are cut there; the outside pieces stay), and the open net
    plus every net that lost copper are joined again inside the window, all of them each round,
    each free to cross the others' current routes at a price per cell that rises every round
    (present cost) and for nets that were in conflict before (history), until no route breaks a
    requirement against another. A rip-up with a re-route one net at a time fails where two
    nets must change places (paicorea: USB_D+ and USB_D- at a reversible USB-C pair); this
    lets them. Returns (new items, ripped items, rounds) with the new copper committed, or
    None with the space as it was."""
    import time
    win = _window(src, others, margin)
    cand = {id(it): it for l in sp.cu for it in sp.query(l, win.bounds)
            if it.kind in ("track", "via") and it.geom.intersects(win) and rippable(it)}
    cand = list(cand.values())
    nets = sorted({it.net for it in cand} | {net})
    if len(nets) > REGION_NETS:
        return None
    sp.remove(cand)
    clips = [c for it in cand if it.kind == "track" for c in _clip_outside(sp, it, win)]
    # the joins search a little beyond the cut, so the cut pieces' ends lie inside their grid
    x0, y0, x1, y1 = win.bounds
    rwin = box(x0 - 0.6, y0 - 0.6, x1 + 0.6, y1 + 0.6)
    routes = {n: [] for n in nets}
    hist = {}
    widths = {}
    for n in nets:
        mn, opt, _mx = sp.width_limits(n, sp.cu[0])
        widths[n] = sorted({round(w, 4) for w in (opt, mn) if w and w > 0}, reverse=True) or [0.2]

    def undo():
        for n in nets:
            sp.remove(routes[n])
        sp.remove(clips)
        _restore(sp, cand)
        return None

    def wparts(n):
        return [p for p in parts(sp, fp, n) if _relevant(p) and any(nd.copper.intersects(rwin) for nd in p)]

    order = [net] + [n for n in nets if n != net]
    pres = REGION_PRES[0]
    for k in range(REGION_ITERS):
        if deadline is not None and time.monotonic() > deadline:
            return undo()
        for n in order:
            sp.remove(routes[n])
            routes[n] = []
            gr.soft = [(it, pres * (1.0 + REGION_HIST * hist.get(m, 0)))
                       for m in nets if m != n for it in routes[m]]
            # a via of the net must stay further from the others' copper than a track
            gr.soft_grow = max(0.0, sp.via_size(n)[0] / 2.0 - min(widths[n]) / 2.0) if len(sp.cu) > 1 else 0.0
            try:
                for _ in range(8):
                    ps = wparts(n)
                    if len(ps) < 2:
                        break
                    s_ = _anchors(ps[-1], max(widths[n]) / 2 + 0.02)
                    got = _try(gr, sp, n, s_, ps[:-1], rwin, widths[n]) if s_ else None
                    if got is None:
                        if log and REGION_DEBUG:
                            log(f"    no route {n}: {len(ps)} parts, src {[(a.kind, [round(v, 2) for v in a.geom.bounds]) for a in s_][:3]}, "
                                f"widths {widths[n]}")
                        break
                    routes[n] += got[1]
            finally:
                gr.soft, gr.soft_grow = [], 0.0
            sp.remove(routes[n])         # soft for the others until the round ends
        # the round's routes together: which of them break a requirement against another net's
        for n in nets:
            for it in routes[n]:
                for l in it.layers:
                    if l in sp.items:
                        sp.items[l].append(it)
                sp.routed.append(it)
        sp.invalidate()
        allnew = {n: set(map(id, routes[n])) for n in nets}
        bad = set()
        for n in nets:
            theirs = [it for m in nets if m != n for it in routes[m]]
            for it in routes[n]:
                if theirs and _conflicts(sp, it, set(theirs)):
                    bad.add(n)
                    if log and REGION_DEBUG:
                        log(f"    conflict {n} {it.kind} {[round(c, 2) for c in it.geom.coords[0]]} "
                            f"{sorted(it.layers)[:2]} vs {_why(sp, it, set(theirs))}")
                    break
        still = [n for n in nets if len(wparts(n)) > 1]
        if log:
            log(f"  region {net} m={margin} round {k}: {len(nets)} nets, {sum(len(v) for v in allnew.values())} "
                f"items, conflicts {len(bad)}, open {len(still)} {still[:4] if REGION_DEBUG else ''}")
        if not bad and not still:
            new = [it for n in nets for it in routes[n]] + clips
            return new, cand, k + 1
        if still and not bad:
            for n in nets:
                sp.remove(routes[n])
            return undo()     # a net finds no way through even where crossing is allowed
        for n in bad:
            hist[n] = hist.get(n, 0) + 1
        for n in nets:
            sp.remove(routes[n])
        pres *= REGION_PRES[1]
    return undo()
