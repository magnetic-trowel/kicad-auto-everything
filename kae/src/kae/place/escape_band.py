# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Escape bands: room the placer keeps free around ball grids and fine-pitch pad rings.

On the place-and-route boards about half the connections left open were ones our placement made
impossible (docs/research/routing/kae-closing-open-connections.md, class c), typically a capacitor
dropped into the strip a BGA's or a fine-pitch QFN's escapes need. The placer saw no difference
between that strip and any other free space.

Per tricky package (a ball grid, down to a 3 x 3 wafer-level package; a pad ring at most `escape_ring_pitch` mm, 0.5 by default) this
module counts the signal escapes that must leave each side of it on the parts' own copper layer,
with the escape planner's own capacity rule (kae.route.escape.fit):

- ball grid: a ball escapes on the surface when its ring (0 = outermost) is at most the number of
  tracks that fit between two outer balls, O = fit(pitch - ball, w, c); the inner rings go down
  through their dog-bones and need no surface room outside the package (the planner's LAYER_COST:
  outer rings stay on the surface, as on the human boards);
- pad ring: every signal pad escapes on the surface;
- only signal pads count: ground and power pads go to their planes or decoupling caps, so a side
  whose edge is mostly power keeps a thin band, or none, and its caps can sit close.

Each side's band is n x (w + c) deep (n escapes on that side; w and c the board's own track width
and clearance; a side's pads go to the courtyard edge nearest them, so a connector's single row
escapes away from its body), scaled by `escape_band_scale` and capped at `escape_band_max_mm`.

How the placer keeps a band (`escape_band`):

- 1 (default): a soft annealer term (escape_grid, priced like silk): a part in a package's band pays
  for the overlap unless it is the package's own (related(): it shares a signal net with the package,
  or it is a decap on the package's rails). On the 67 merit boards with such packages the humans put
  mostly the package's own parts in these bands (series parts, pull-ups, decaps: 718 parts) and fewer
  unrelated ones (148); kae's staged placements put 361 unrelated parts there, 2.7 x the humans' area
  in the ball grids' bands. A band against every part would push the humans' parts away too.
- 2: hard occupancy against every part (Problem.set_escape): the package's own side only, dropped
  with the margin when the parts cannot all fit (pipeline._escalate).
- 0: off.

Either way nothing is written to the board and the router never sees a band.

Switches (kae.route.constraints.setting: the project's KAE_<NAME> text variable, then the option,
then the default): escape_band (1 soft, 2 hard, 0 off), escape_band_w, escape_band_scale, escape_band_max_mm,
escape_ring_pitch.
"""
from __future__ import annotations

import math

from kae.route.constraints import setting

MIN_BALLS = 16          # as kae.route.escape: a ball grid has at least this many pads
MIN_RING = 12           # a pad ring at least this many
SIDES = ("L", "T", "R", "B")   # library frame: -x, -y, +x, +y (y down)


MIN_SMALL = 9           # a small ball grid (wafer-level packages): at least 3 x 3 sites
SMALL_FILL = 0.75       # of which at least this share carry a ball (a QFN ring is hollow)


def _grid(pts):
    """(pitch, angle, local points, ring of each point) of a ball grid, else None: the escape
    planner's test for 16 balls and more, and below that a filled lattice of at least 3 x 3 sites
    (a 12-ball 3 x 4 wafer-level package has 2 interior balls, too few for the planner's test)."""
    from kae.route.escape import _grid as grid
    if len(pts) >= MIN_BALLS:
        return grid(pts)
    return _small_grid(pts) if len(pts) >= MIN_SMALL else None


def _small_grid(pts):
    nn = []
    for i, a in enumerate(pts):
        d, v = min((math.dist(a, b), (b[0] - a[0], b[1] - a[1])) for j, b in enumerate(pts) if j != i)
        nn.append((d, v))
    pitch, v = sorted(nn)[len(nn) // 2]
    if pitch < 1e-3:
        return None
    ang = math.atan2(v[1], v[0]) % (math.pi / 2)
    cx, cy = sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)
    c, s = math.cos(-ang), math.sin(-ang)
    loc = [((x - cx) * c - (y - cy) * s, (x - cx) * s + (y - cy) * c) for x, y in pts]
    u0, w0 = min(u for u, _ in loc), min(w for _, w in loc)
    idx = [((u - u0) / pitch, (w - w0) / pitch) for u, w in loc]
    if any(abs(a - round(a)) > 0.1 or abs(b - round(b)) > 0.1 for a, b in idx):
        return None                                     # not on one lattice
    cols = {round(a) for a, _ in idx}
    rows = {round(b) for _, b in idx}
    nc, nr = max(cols) + 1, max(rows) + 1
    sites = {(round(a), round(b)) for a, b in idx}
    if nc < 3 or nr < 3 or len(sites) < SMALL_FILL * nc * nr:
        return None
    rings = [min(round(a), round(b), nc - 1 - round(a), nr - 1 - round(b)) for a, b in idx]
    return pitch, ang, loc, rings


def _track_and_clearance(board):
    """The board's own track width and clearance: the default net class first, then the setup's
    minimum, then kae's defaults (0.2 mm each) where the board is silent."""
    r = getattr(board, "rules", None)
    w = c = None
    if r is not None:
        nc = (getattr(r, "netclasses", None) or {}).get("Default")
        if nc is not None:
            w = getattr(nc, "track_width", None) or None
            c = getattr(nc, "clearance", None) or None
        w = w or (getattr(r, "track_min", 0.0) or None)
        c = c or (getattr(r, "clearance", 0.0) or None)
    return float(w or 0.2), float(c or 0.2)


def _extent(fp, *pad_box):
    """Library-frame (x0, y0, x1, y1) of the part: its courtyard, else its body, else the pads'."""
    for polys in (getattr(fp, "courtyard", None), getattr(fp, "body", None)):
        bs = [g.bounds for g in (polys or []) if g is not None and not g.is_empty]
        if bs:
            return (min(b[0] for b in bs), min(b[1] for b in bs), max(b[2] for b in bs), max(b[3] for b in bs))
    return pad_box


def package(fp, net_kind, w, c, ring_pitch=0.5):
    """{kind, pitch, counts {side: n}} of a ball grid or fine-pitch pad ring, else None.
    net_kind: {net name: 'ground'|'power'|'signal'}; a pad on no net escapes nothing."""
    from kae.route.escape import fit
    pads = [p for p in fp.pads if p.kind == "smd" and len([l for l in p.layers if l.endswith(".Cu")]) == 1]
    if len(pads) < MIN_SMALL:
        return None
    sizes = sorted(min(p.size) for p in pads)
    med = sizes[len(sizes) // 2]
    pads = [p for p in pads if min(p.size) <= 2.0 * med]      # leave out an exposed pad or shield tabs
    if len(pads) < MIN_SMALL:
        return None
    pts = [(p.lx, p.ly) for p in pads]
    xs, ys = [x for x, _ in pts], [y for _, y in pts]
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    hx, hy = max(max(xs) - cx, 1e-6), max(max(ys) - cy, 1e-6)
    g = _grid(pts)
    if g is not None:
        pitch, _ang, _loc, rings = g
        O = fit(pitch - med, w, c)
        surface = [r <= O for r in rings]
        kind = "grid"
    elif len(pads) < MIN_RING:
        return None
    else:
        # pitch between distinct pad sites: stacked pads (a switch's or a jumper's) are one site
        sites = sorted({(round(x, 3), round(y, 3)) for x, y in pts})
        if len(sites) < MIN_RING:
            return None
        nn = sorted(min(math.dist(a, b) for j, b in enumerate(sites) if j != i) for i, a in enumerate(sites))
        pitch = nn[len(nn) // 2]
        if pitch > ring_pitch + 1e-6:
            return None
        surface = [True] * len(pads)
        kind = "ring"
    x0, y0, x1, y1 = _extent(fp, cx - hx, cy - hy, cx + hx, cy + hy)
    counts = dict.fromkeys(SIDES, 0)
    for p, (x, y), s in zip(pads, pts, surface):
        if not s or not p.net or net_kind.get(p.net, "signal") != "signal":
            continue
        # the courtyard edge nearest the pad: a ring's pads face their own side, a connector's single
        # row faces away from its body (the body side needs no band)
        d = {"L": x - x0, "T": y - y0, "R": x1 - x, "B": y1 - y}
        counts[min(SIDES, key=d.__getitem__)] += 1
    if not any(counts.values()):
        return None
    return dict(kind=kind, pitch=round(pitch, 4), counts=counts)


def bands(P, board_path=None, opts=None, log=None):
    """{part index: (left, top, right, bottom) mm in the library frame} for P's tricky packages,
    and a report row per package. Empty when the switch is off."""
    if not setting("escape_band", board_path, opts):
        return {}, []
    scale = float(setting("escape_band_scale", board_path, opts))
    cap = float(setting("escape_band_max_mm", board_path, opts))
    ring_pitch = float(setting("escape_ring_pitch", board_path, opts))
    w, c = _track_and_clearance(P.board)
    net_kind = {n.name: (n.kind if n.kind in ("ground", "power") else "signal") for n in P.nets}
    out, rows = {}, []
    for p in P.parts:
        if getattr(p, "decor", False):
            continue
        pk = package(p.fp, net_kind, w, c, ring_pitch)
        if pk is None:
            continue
        mm = {s: round(min(cap, scale * n * (w + c)), 4) for s, n in pk["counts"].items()}
        out[p.i] = tuple(mm[s] for s in SIDES)
        rows.append(dict(ref=p.ref, kind=pk["kind"], pitch=pk["pitch"], escapes=pk["counts"], band_mm=mm,
                         movable=p.movable))
    if log and rows:
        log(f"escape bands: {', '.join(r['ref'] + ' ' + str(r['band_mm']) for r in rows[:6])}"
            f"{' ...' if len(rows) > 6 else ''} (track {w:g} + clearance {c:g} mm)")
    return out, rows


def _via_size(board):
    """The board's own via diameter (default net class, then the setup's minimum), else 0.6 mm."""
    r = getattr(board, "rules", None)
    d = None
    if r is not None:
        nc = (getattr(r, "netclasses", None) or {}).get("Default")
        d = (getattr(nc, "via_dia", None) or getattr(nc, "via_diameter", None)) if nc is not None else None
        d = d or getattr(r, "via_min", None) or getattr(r, "via_dia_min", None)
    return float(d or 0.6)


def via_sites(fp, net_kind, w, c, D):
    """Library-frame rectangles of a ball grid's dog-bone via sites: one per inner-ring signal ball
    (it leaves the surface) and per ground or power ball (its plane), at the diagonal site that
    points away from the package's centre (the usual dog-bone direction), D + c wide. [] for a
    pad ring or no grid."""
    from kae.route.escape import fit
    pads = [p for p in fp.pads if p.kind == "smd" and len([l for l in p.layers if l.endswith(".Cu")]) == 1 and p.net]
    if len(pads) < MIN_SMALL:
        return []
    sizes = sorted(min(p.size) for p in pads)
    med = sizes[len(sizes) // 2]
    pads = [p for p in pads if min(p.size) <= 2.0 * med]
    pts = [(p.lx, p.ly) for p in pads]
    g = _grid(pts)
    if g is None:
        return []
    pitch, _ang, _loc, rings = g
    O = fit(pitch - med, w, c)
    xs, ys = [x for x, _ in pts], [y for _, y in pts]
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    h = (D + c) / 2
    out = []
    for p, (x, y), ring in zip(pads, pts, rings):
        plane = net_kind.get(p.net, "signal") in ("ground", "power")
        if not plane and ring <= O:
            continue                     # escapes on the surface: no via
        sx = pitch / 2 * (1 if x >= cx else -1)
        sy = pitch / 2 * (1 if y >= cy else -1)
        vx, vy = x + sx, y + sy
        out.append((vx - h, vy - h, vx + h, vy + h))
    return out


def fanout(P, board_path=None, opts=None, log=None):
    """{part index: [library-frame via-site rectangles]} when escape_fanout is on."""
    if not setting("escape_fanout", board_path, opts):
        return {}
    w, c = _track_and_clearance(P.board)
    D = _via_size(P.board)
    net_kind = {n.name: (n.kind if n.kind in ("ground", "power") else "signal") for n in P.nets}
    out = {}
    for p in P.parts:
        if getattr(p, "decor", False):
            continue
        sites = via_sites(p.fp, net_kind, w, c, D)
        if sites:
            out[p.i] = sites
    if log and out:
        log(f"escape fanout: dog-bone via sites reserved on the other side of "
            f"{', '.join(P.parts[i].ref + ' (' + str(len(s)) + ')' for i, s in list(out.items())[:6])}")
    return out


BAND_CLASS = 2          # soft-overlap classes: silk 0, routing channels 1 (kae.place.exact), bands 2, 3, ...


def related(fp, pkg, net_kind):
    """Part `fp` belongs beside package `pkg` in its escape band: it shares a signal net with the
    package (a series resistor, pull-up, ESD or termination on an escaping net), or it is a decap of
    the package (at most 3 pads, all on the package's ground/power nets, at least one power). On the
    merit boards these are 95 % of the parts humans place inside the bands."""
    pn = {p.net for p in pkg.pads if p.net}
    on = {p.net for p in fp.pads if p.net}
    if any(net_kind.get(n, "signal") == "signal" for n in on & pn):
        return True
    return (len(fp.pads) <= 3 and bool(on) and on <= pn
            and any(net_kind.get(n) == "power" for n in on))


def band_rects(fp, band):
    """Library-frame rectangles (x0, y0, x1, y1) of a package's band (left, top, right, bottom mm),
    outside its courtyard."""
    pts = [(p.lx, p.ly) for p in fp.pads]
    xs, ys = [x for x, _ in pts], [y for _, y in pts]
    x0, y0, x1, y1 = _extent(fp, min(xs), min(ys), max(xs), max(ys))
    l, t, r, b = band
    out = []
    if l > 0:
        out.append((x0 - l, y0, x0, y1))
    if r > 0:
        out.append((x1, y0, x1 + r, y1))
    if t > 0:
        out.append((x0, y0 - t, x1, y0))
    if b > 0:
        out.append((x0, y1, x1, y1 + b))
    return out


def escape_grid(P, bands, weight=1.0):
    """The annealer's escape-band model (a soft term, as kae.place.exact.silk_grid): package k's band
    rectangles are class BAND_CLASS + k sources, and every part on its side that is not related to it
    (related()) carries its own body as a class BAND_CLASS + k target. Related parts sit in the band
    for free; an unrelated one pays weight x overlap / mean part area, as silk does. On the merit
    boards kae's staged placements put 3x as many unrelated parts in these bands as the humans did."""
    from .exact import _grid_rects
    net_kind = {n.name: (n.kind if n.kind in ("ground", "power") else "signal") for n in P.nets}
    out = {}

    def entry(p):
        si = 0 if p.s > 0 else 1
        if p.i not in out:
            out[p.i] = (si, [[] for _ in p.rots], [[] for _ in p.rots])
        return out[p.i]

    for k, (i, band) in enumerate(sorted(bands.items())):
        pk = P.parts[i]
        cls = BAND_CLASS + k
        lib = band_rects(pk.fp, band)
        if not lib:
            continue
        e = entry(pk)
        for kk, rt in enumerate(pk.rots):
            e[1][kk] += [r + (cls, weight) for r in _grid_rects(P, pk, lib, rt.rot)]
        for q in P.parts:
            if q.i == i or q.s != pk.s or getattr(q, "decor", False) or related(q.fp, pk.fp, net_kind):
                continue
            eq = entry(q)
            for kk, rt in enumerate(q.rots):
                a, b, c, d = rt.g_own_exact
                eq[2][kk].append((a, b, c, d, cls))
    return out
