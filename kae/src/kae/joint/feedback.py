# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Feedback from routing to placement: what went wrong, where, and which parts can fix it.

Three sources, all read from what KiCad and the recheck report on the routed board (a
router's own log is not a score):

- **Unrouted connections** (`unrouted_spots`): every `unconnected_items` entry of KiCad's
  DRC names two items (pads, tracks, vias, zones) with their positions. The connection
  needs a corridor between them; its two ends name the parts (pad descriptions end in
  "of <ref>") whose poses decide whether that corridor exists.
- **DRC errors** (`error_spots`): each error-level violation is attributed to the parts
  its items belong to and to the routing items involved (by uuid).
- **Physics shifts** (`physics_spots`): modules the recheck flagged (routed utilization
  rose beyond the threshold, crossed the budget, or lost plane cover), placed at their
  parts.

`CongestionHistory` keeps PathFinder-style history on a millimetre grid: every failed
connection adds demand along its corridor, so a region where routing failed before stays
expensive for the placer even after one re-placement. `plan_windows` clusters the spots
into windows: a rectangle and the unlocked parts inside it that may move.

Everything here is pure Python (no KiCad), so it is unit-tested directly.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

import numpy as np

# DRC types that depend on the local library setup, not on the board (as kaebench and
# kae.route.drc ignore them)
ENV_DEPENDENT = ("lib_footprint_issues", "lib_footprint_mismatch")

_NET = re.compile(r"\[([^\]]*)\]")
_REF = re.compile(r"\bof (\S+?)(?:\s+on\s|\s*$)")

W_UNROUTED = 3.0     # spot weights: a missing connection outranks an error, which outranks physics
W_ERROR = 2.0
W_PHYSICS = 1.0


@dataclass
class Spot:
    """One problem on the routed board."""
    kind: str                      # unrouted | error | physics
    x: float
    y: float
    points: tuple = ()             # ((x, y), ...) the items' positions
    refs: tuple = ()               # footprint references KiCad names
    nets: tuple = ()
    uuids: tuple = ()              # routing items involved (tracks, vias)
    weight: float = 1.0
    why: str = ""
    module: str = ""               # physics spots: the module id

    def to_dict(self):
        return dict(kind=self.kind, x=round(self.x, 3), y=round(self.y, 3), refs=list(self.refs),
                    nets=list(self.nets), why=self.why, weight=round(self.weight, 3),
                    **({"module": self.module} if self.module else {}))


def parse_item(item):
    """A DRC item -> dict(kind, ref, net, uuid, pos). kind: pad | track | via | zone | other."""
    d = (item or {}).get("description") or ""
    low = d.lower()
    if low.startswith(("pad", "pth pad", "npth pad", "smd pad")):
        kind = "pad"
    elif low.startswith(("track", "arc")):
        kind = "track"
    elif low.startswith("via"):
        kind = "via"
    elif low.startswith(("zone", "teardrop")):
        kind = "zone"
    elif low.startswith("footprint"):
        kind = "footprint"
    else:
        kind = "other"
    nets = [m for m in _NET.findall(d) if m and m != "<no net>"]
    m = _REF.search(d)
    ref = m.group(1) if m and kind in ("pad", "footprint", "other") else ""
    if kind == "footprint" and not ref:
        parts = d.split()
        ref = parts[1] if len(parts) > 1 else ""
    pos = (item or {}).get("pos") or {}
    xy = (float(pos.get("x", 0.0)), float(pos.get("y", 0.0))) if pos else None
    return dict(kind=kind, ref=ref, net=nets[0] if nets else "", uuid=(item or {}).get("uuid") or "", pos=xy,
                description=d)


def _centroid(points):
    if not points:
        return 0.0, 0.0
    return sum(p[0] for p in points) / len(points), sum(p[1] for p in points) / len(points)


def unrouted_spots(drc):
    """One spot per missing connection of a KiCad DRC report."""
    out = []
    for u in (drc or {}).get("unconnected_items") or []:
        items = [parse_item(it) for it in u.get("items") or []]
        pts = tuple(it["pos"] for it in items if it["pos"] is not None)
        if not pts:
            continue
        x, y = _centroid(pts)
        out.append(Spot(kind="unrouted", x=x, y=y, points=pts,
                        refs=tuple(dict.fromkeys(it["ref"] for it in items if it["ref"])),
                        nets=tuple(dict.fromkeys(it["net"] for it in items if it["net"])),
                        uuids=tuple(it["uuid"] for it in items if it["kind"] in ("track", "via") and it["uuid"]),
                        weight=W_UNROUTED, why="unrouted " + " - ".join(it["description"][:40] for it in items)))
    return out


def error_spots(drc, ignore=ENV_DEPENDENT):
    """One spot per error-level DRC violation (unconnected items aside)."""
    out = []
    for v in (drc or {}).get("violations") or []:
        if v.get("severity") != "error" or v.get("type") in ignore:
            continue
        items = [parse_item(it) for it in v.get("items") or []]
        pts = tuple(it["pos"] for it in items if it["pos"] is not None)
        if not pts:
            continue
        x, y = _centroid(pts)
        out.append(Spot(kind="error", x=x, y=y, points=pts,
                        refs=tuple(dict.fromkeys(it["ref"] for it in items if it["ref"])),
                        nets=tuple(dict.fromkeys(it["net"] for it in items if it["net"])),
                        uuids=tuple(it["uuid"] for it in items if it["kind"] in ("track", "via") and it["uuid"]),
                        weight=W_ERROR, why=v.get("type") or "error"))
    return out


def physics_spots(recheck, module_parts, part_xy, ref_of):
    """Spots for the modules the recheck flagged. recheck: dict(modules={id: {u_stage,
    u_routed, cover_stage, cover_routed, flag}}, retweak=[ids]); module_parts: {id: [uuid]};
    part_xy: {uuid: (x, y)}; ref_of: {uuid: ref}."""
    out = []
    mods = (recheck or {}).get("modules") or {}
    for mid in sorted((recheck or {}).get("retweak") or []):
        r = mods.get(mid) or {}
        uu = [u for u in module_parts.get(mid) or [] if u in part_xy]
        if not uu:
            continue
        pts = tuple(part_xy[u] for u in uu)
        x, y = _centroid(pts)
        u0, u1 = r.get("u_stage"), r.get("u_routed")
        rise = (u1 / u0 - 1.0) if (u0 and u1) else 0.0
        c0, c1 = r.get("cover_stage"), r.get("cover_routed")
        cut = (c0 - c1) if (c0 is not None and c1 is not None) else 0.0
        out.append(Spot(kind="physics", x=x, y=y, points=pts, refs=tuple(ref_of.get(u, "") for u in uu),
                        weight=W_PHYSICS * (1.0 + max(0.0, rise) + max(0.0, cut)),
                        why=r.get("why") or f"u {u0} -> {u1}", module=mid))
    return out


# ----------------------------------------------------------------------------- congestion history
class CongestionHistory:
    """History cost on a grid over the board (PathFinder's h_n): demand added where routing
    failed, in units of routing utilization (1.0 = a bin's whole routing supply)."""

    def __init__(self, bounds, bin_mm=1.0):
        x0, y0, x1, y1 = bounds
        self.b = float(bin_mm)
        self.x0, self.y0 = float(x0), float(y0)
        self.nx = max(1, int(math.ceil((x1 - x0) / self.b)))
        self.ny = max(1, int(math.ceil((y1 - y0) / self.b)))
        self.h = np.zeros((self.nx, self.ny))
        cx = self.x0 + (np.arange(self.nx) + 0.5) * self.b
        cy = self.y0 + (np.arange(self.ny) + 0.5) * self.b
        self.cx, self.cy = np.meshgrid(cx, cy, indexing="ij")

    def add_corridor(self, a, b, width, amount=1.0):
        """Add `amount` to every bin whose centre lies within width/2 (+ half a bin) of the
        segment a-b. Returns the number of bins touched."""
        ax, ay = a
        bx, by = b
        dx, dy = bx - ax, by - ay
        L2 = dx * dx + dy * dy
        if L2 < 1e-12:
            t = np.zeros_like(self.cx)
        else:
            t = np.clip(((self.cx - ax) * dx + (self.cy - ay) * dy) / L2, 0.0, 1.0)
        d = np.hypot(self.cx - (ax + t * dx), self.cy - (ay + t * dy))
        hit = d <= width / 2.0 + 0.5 * self.b
        self.h[hit] += amount
        return int(hit.sum())

    def add_spot(self, spot, amount=1.0, min_width=1.0, max_width=4.0):
        """An unrouted spot's corridor: between its two farthest points, as wide as a fifth of
        its length (a router's detour room), within [min_width, max_width] mm."""
        pts = list(spot.points)
        if len(pts) < 2:
            pts = pts * 2
        a, b = max(((p, q) for i, p in enumerate(pts) for q in pts[i:]), key=lambda pq: math.dist(*pq))
        w = min(max_width, max(min_width, 0.2 * math.dist(a, b)))
        return self.add_corridor(a, b, w, amount)

    def add_overflow(self, x0, y0, b, util, target=0.5, scale=0.5, reach_mm=3.0):
        """RUDY overflow (the placer's routing-utilization map: bins of size b from (x0, y0))
        added as history where routing already failed nearby: scale * max(0, u - target) in
        every history bin within `reach_mm` of a bin that has history. Freerouting's failures
        mark the region; RUDY says how crowded it is around them. Returns the amount added."""
        if not self.h.any():
            return 0.0
        util = np.asarray(util, float)
        ix = np.clip(((self.cx - x0) / b).astype(int), 0, util.shape[0] - 1)
        iy = np.clip(((self.cy - y0) / b).astype(int), 0, util.shape[1] - 1)
        over = np.clip(util[ix, iy] - target, 0.0, None)
        k = max(1, int(math.ceil(reach_mm / self.b)))
        hit = self.h > 0
        near = np.zeros_like(hit)
        for dx in range(-k, k + 1):
            for dy in range(-k, k + 1):
                if dx * dx + dy * dy > k * k:
                    continue
                sx = slice(max(0, dx), self.nx + min(0, dx))
                sy = slice(max(0, dy), self.ny + min(0, dy))
                tx = slice(max(0, -dx), self.nx + min(0, -dx))
                ty = slice(max(0, -dy), self.ny + min(0, -dy))
                near[tx, ty] |= hit[sx, sy]
        add = scale * over * near
        self.h += add
        return float(add.sum())

    def sample(self, x0, y0, b, nbx, nby):
        """History resampled onto another grid (bins of size b from (x0, y0)): the mean of
        the history bins whose centres fall in each target bin, else the nearest one."""
        out = np.zeros((nbx, nby))
        if not self.h.any():
            return out
        ix = np.clip(((self.cx - x0) / b).astype(int), -1, nbx)
        iy = np.clip(((self.cy - y0) / b).astype(int), -1, nby)
        ok = (ix >= 0) & (ix < nbx) & (iy >= 0) & (iy < nby)
        cnt = np.zeros((nbx, nby))
        np.add.at(out, (ix[ok], iy[ok]), self.h[ok])
        np.add.at(cnt, (ix[ok], iy[ok]), 1.0)
        filled = cnt > 0
        out[filled] /= cnt[filled]
        # target bins smaller than ours: nearest history bin
        if (~filled).any():
            tx = x0 + (np.arange(nbx) + 0.5) * b
            ty = y0 + (np.arange(nby) + 0.5) * b
            jx = np.clip(((tx - self.x0) / self.b).astype(int), 0, self.nx - 1)
            jy = np.clip(((ty - self.y0) / self.b).astype(int), 0, self.ny - 1)
            near = self.h[np.ix_(jx, jy)]
            inside = ((tx >= self.x0) & (tx <= self.x0 + self.nx * self.b))[:, None] & \
                     ((ty >= self.y0) & (ty <= self.y0 + self.ny * self.b))[None, :]
            out[~filled] = np.where(inside, near, 0.0)[~filled]
        return out

    def total(self):
        return float(self.h.sum())

    def summary(self):
        return dict(bins=int((self.h > 0).sum()), total=round(self.total(), 2), peak=round(float(self.h.max()), 2))


# ----------------------------------------------------------------------------- windows
@dataclass
class PartGeom:
    uuid: str
    ref: str
    bbox: tuple                    # (x0, y0, x1, y1) courtyard (else pads) at the current pose
    locked: bool = False
    side: str = "F"
    pins: int = 0                  # pads with a net

    @property
    def center(self):
        return (self.bbox[0] + self.bbox[2]) / 2.0, (self.bbox[1] + self.bbox[3]) / 2.0


@dataclass
class Window:
    """A rectangle of the board and the unlocked parts in it that may move."""
    rect: tuple                    # (x0, y0, x1, y1) mm
    parts: tuple                   # uuids, sorted
    refs: tuple = ()
    reasons: tuple = ()            # spot kinds and whys
    nets: tuple = ()
    modules: tuple = ()            # modules whose physics flagged it
    priority: float = 0.0
    spots: list = field(default_factory=list)

    @property
    def key(self):
        return self.parts

    def to_dict(self):
        x0, y0, x1, y1 = self.rect
        return dict(rect=[round(v, 3) for v in self.rect], size_mm=[round(x1 - x0, 2), round(y1 - y0, 2)],
                    parts=list(self.refs), reasons=list(self.reasons)[:8], nets=list(self.nets)[:12],
                    modules=list(self.modules), priority=round(self.priority, 3))


def _grow(r, m):
    return (r[0] - m, r[1] - m, r[2] + m, r[3] + m)


def _union(a, b):
    if a is None:
        return b
    if b is None:
        return a
    return (min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3]))


def _clip(r, bounds):
    return (max(r[0], bounds[0]), max(r[1], bounds[1]), min(r[2], bounds[2]), min(r[3], bounds[3]))


def _overlap(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def _contains_pt(r, p):
    return r[0] <= p[0] <= r[2] and r[1] <= p[1] <= r[3]


def window_for_spot(spot, parts, bounds, margin=2.0, max_parts=10, max_pins=None):
    """The window that may fix one spot: its own (unlocked) parts, then the unlocked parts
    whose centres lie in the region they and the spot's points span, grown by `margin`;
    at most `max_parts`, nearest to the spot first (its own parts always stay). Parts with
    more than `max_pins` connected pads stay fixed (moving an IC rips up all its nets). The
    rectangle covers every movable part's current box, so the annealer starts inside it.
    None when no part may move."""
    def movable(g):
        return not g.locked and (max_pins is None or g.pins <= max_pins)

    by_ref = {}
    for g in parts.values():
        by_ref.setdefault(g.ref, []).append(g)
    own = [g for r in spot.refs for g in by_ref.get(r, []) if movable(g)]
    region = None
    for p in spot.points:
        region = _union(region, (p[0], p[1], p[0], p[1]))
    for g in own:
        region = _union(region, g.bbox)
    if region is None:
        return None
    region = _clip(_grow(region, margin), bounds)
    cand = [g for g in parts.values() if movable(g) and _contains_pt(region, g.center)]
    cand.sort(key=lambda g: (math.dist(g.center, (spot.x, spot.y)), g.uuid))
    keep = {g.uuid: g for g in own}
    for g in cand:
        if len(keep) >= max(max_parts, len(own)):
            break
        keep.setdefault(g.uuid, g)
    if not keep:
        return None
    rect = region
    for g in keep.values():
        rect = _union(rect, g.bbox)
    rect = _clip(_grow(rect, 0.0), bounds) if bounds else rect
    for g in keep.values():                 # the window must contain each movable part
        rect = _union(rect, g.bbox)
    ids = tuple(sorted(keep))
    return Window(rect=rect, parts=ids, refs=tuple(parts[u].ref for u in ids), reasons=(f"{spot.kind}: {spot.why}",),
                  nets=spot.nets, modules=(spot.module,) if spot.module else (), priority=spot.weight, spots=[spot])


def merge(a, b):
    parts = tuple(sorted(set(a.parts) | set(b.parts)))
    refs_of = dict(zip(a.parts, a.refs))
    refs_of.update(zip(b.parts, b.refs))
    return Window(rect=_union(a.rect, b.rect), parts=parts, refs=tuple(refs_of.get(u, "") for u in parts),
                  reasons=tuple(dict.fromkeys(a.reasons + b.reasons)), nets=tuple(dict.fromkeys(a.nets + b.nets)),
                  modules=tuple(dict.fromkeys(a.modules + b.modules)), priority=a.priority + b.priority,
                  spots=a.spots + b.spots)


def plan_windows(spots, parts, bounds, margin=2.0, max_parts=10, merge_factor=1.5, max_pins=None):
    """Cluster spots into windows: one per spot (window_for_spot; parts with more than
    `max_pins` connected pads only when nothing smaller can move), then overlapping windows
    merged while the union holds at most merge_factor * max_parts parts. Sorted by priority
    (summed spot weights), ties by position, so the order is deterministic."""
    wins = []
    for s in spots:      # a spot that only big parts can fix gets them
        w = window_for_spot(s, parts, bounds, margin, max_parts, max_pins)
        if w is None and max_pins is not None:
            w = window_for_spot(s, parts, bounds, margin, max_parts, None)
        if w is not None:
            wins.append(w)
    wins.sort(key=lambda w: (w.rect, w.parts))
    changed = True
    while changed:
        changed = False
        for i in range(len(wins)):
            for j in range(i + 1, len(wins)):
                a, b = wins[i], wins[j]
                if not (_overlap(a.rect, b.rect) or set(a.parts) & set(b.parts)):
                    continue
                m = merge(a, b)
                if len(m.parts) > merge_factor * max_parts:
                    continue
                wins[i] = m
                del wins[j]
                changed = True
                break
            if changed:
                break
    wins.sort(key=lambda w: (-w.priority, w.rect, w.parts))
    return wins
