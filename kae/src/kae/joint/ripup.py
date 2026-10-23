# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""What a window's re-placement invalidates: the routing to rip up and the modules to redo.

    plan = plan_ripup(board, window, moved, owners, module_parts)
    plan.remove     # routing uuids to delete
    plan.redo       # module ids whose module stage runs again
    plan.nets       # nets that lose routing (the bridge routes them again)

Rules (only nets touching the window lose copper):
- **Nets on moved parts.** Every unlocked item of such a net is ripped, whole: a fragment
  left behind would be fixed wiring the bridge must join in its middle, which Freerouting
  does not do. Nets that are poured (a zone of the net) or large (`big_pads` pads or more)
  lose only the items inside the window or touching the moved parts' old pads; the rest
  stays connected through the pour.
- **Nets crossing the window.** Unlocked items of other nets inside the window are ripped
  (a moved part may land on them); the `max_cross` shortest such nets are ripped whole, so
  the bridge can re-route them around the new placement.
- **Critical copper** (locked): modules with a moved part or with copper inside the window
  are redone, their copper removed. Locked items no module owns (rails, joins, stitching)
  are removed when they lie inside the window or touch a moved part's old pads.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from shapely.geometry import LineString, Point, box


@dataclass
class RipPlan:
    remove: list = field(default_factory=list)
    redo: list = field(default_factory=list)
    nets: list = field(default_factory=list)
    whole: list = field(default_factory=list)      # nets ripped whole
    partial: list = field(default_factory=list)    # nets ripped inside the window only

    def to_dict(self):
        return dict(items=len(self.remove), redo=list(self.redo), nets=len(self.nets), whole=list(self.whole)[:20],
                    partial=list(self.partial)[:20])


def _geom(it):
    if hasattr(it, "start"):
        a, b = tuple(it.start), tuple(it.end)
        if math.dist(a, b) < 1e-9:
            return Point(a).buffer(it.width / 2)
        return LineString([a, b]).buffer(it.width / 2)
    return Point(it.x, it.y).buffer(it.size / 2)


def _pad_xy(fp, pad):
    from kae.board import transform
    return transform.pad_xy(fp, pad)


def plan_ripup(board, window, moved, owners, module_parts, big_pads=20, max_cross=4, pad_reach=0.3):
    """See the module docstring. board: kae.board.model.Board before the move (old poses);
    window: feedback.Window; moved: uuids of the parts that moved; owners: {routing uuid:
    module id} for critical copper; module_parts: {module id: [part uuid]}."""
    moved = set(moved)
    fp_of = {fp.uuid: fp for fp in board.footprints}
    region = box(*window.rect).buffer(0.25)
    pad_count = {}
    for fp in board.footprints:
        for p in fp.pads:
            if p.net:
                pad_count[p.net] = pad_count.get(p.net, 0) + 1
    poured = {z.net for z in board.zones if z.net and not (z.name or "").startswith("kae-crit:")}

    def big(net):
        return net in poured or pad_count.get(net, 0) >= big_pads

    touch_nets = set()
    old_pads = []
    for u in sorted(moved):
        fp = fp_of.get(u)
        if fp is None:
            continue
        for p in fp.pads:
            x, y = _pad_xy(fp, p)
            old_pads.append(Point(x, y).buffer(max(p.size) / 2 + pad_reach))
            if p.net:
                touch_nets.add(p.net)
    items = list(board.tracks) + list(board.vias)
    geoms = {it.uuid: _geom(it) for it in items}

    def at_pads(g):
        return any(g.intersects(pg) for pg in old_pads)

    remove = set()
    whole, partial = set(), set()
    crossing = {}
    # modules to redo: a moved part, or copper inside the window
    redo = {m for m, parts in module_parts.items() if moved & set(parts)}
    for it in items:
        if it.locked and owners.get(it.uuid) in module_parts and geoms[it.uuid].intersects(region):
            redo.add(owners[it.uuid])
    for it in items:
        g = geoms[it.uuid]
        if it.locked:
            m = owners.get(it.uuid)
            if m in redo or m not in module_parts and (g.intersects(region) or at_pads(g)):
                remove.add(it.uuid)
            continue
        if it.net in touch_nets:
            if big(it.net):
                if g.intersects(region) or at_pads(g):
                    remove.add(it.uuid)
                    partial.add(it.net)
            else:
                remove.add(it.uuid)
                whole.add(it.net)
        elif g.intersects(region):
            remove.add(it.uuid)
            crossing.setdefault(it.net, 0.0)
    if crossing:
        length = {}
        for it in items:
            if not it.locked and it.net in crossing and hasattr(it, "start"):
                length[it.net] = length.get(it.net, 0.0) + math.dist(it.start, it.end)
        small = sorted((n for n in crossing if not big(n)), key=lambda n: (length.get(n, 0.0), n))[:max_cross]
        for it in items:
            if not it.locked and it.net in small:
                remove.add(it.uuid)
        whole |= set(small)
        partial |= set(crossing) - set(small)
    nets = sorted({it.net for it in items if it.uuid in remove} | touch_nets)
    return RipPlan(remove=sorted(remove), redo=sorted(redo), nets=nets, whole=sorted(whole),
                   partial=sorted(partial - whole))
