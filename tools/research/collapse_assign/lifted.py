# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Lifted-conflict placement objective on the pnr World.

    lifted_conflicts(world)            -> dict (one-shot)
    lc = LiftedConflicts(world); lc.stats()
    box = part_box(world, pi); world.place(pi, ...); lc.update([pi], [box]) -> dict

Every net is A*-routed alone on one virtual layer (pads and static blocks only, see
collapse.Lift). From the lifted paths: `conflicts` = run-level conflict edges (two nets
within the track halo), `net_pairs` = conflicting net pairs, and, when exact=True, the
2-layer (L-layer) assignment optimum: `forced_vias` (predicted vias) and `unresolved`
(conflicts no assignment can separate: three or more nets in one corridor, foreign pads).
`cost` = lift_len_mm + 2 * forced_vias + UNRES_MM * unresolved, a single number for a
placer (2 mm per via as in placekit.Kit.total_cost).

The world must carry no routed copper (rip the router first): the lift reads foreign
copper from world.DT, which holds pads, static copper and any stamped routes.
"""
import os
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "pnr"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import collapse  # noqa: E402

UNRES_MM = 5.0  # cost per unresolved conflict (a forced detour), in mm


def part_box(world, pi, pad_cells=0):
    """Courtyard bounding box (y0, x0, y1, x1) in cells of placed part pi."""
    cx, cy, ri = world.pose[pi]
    bx0, by0, bx1, by1 = world.raster(pi)["bbox"]
    return (cy + by0 - pad_cells, cx + bx0 - pad_cells, cy + by1 + pad_cells, cx + bx1 + pad_cells)


class LiftedConflicts:
    def __init__(self, world, spread=0, spread_pres=0.5, exact=True, cpsat_s=5.0):
        self.w = world
        self.spread, self.spread_pres = spread, spread_pres
        self.exact, self.cpsat_s = exact, cpsat_s
        self.lift = collapse.Lift(world)
        if spread:
            self.lift.enable_spread()
        self.lifts = {}
        for n in world.net_pins:
            self._relift(n, first=True)
        for _ in range(spread):
            for n in list(self.lifts):
                self._relift(n, pres=spread_pres)

    def _relift(self, n, pres=0.0, first=False):
        if self.spread and not first and n in self.lifts:
            self.lift.stamp(n, self.lifts[n], -1)
        self.lifts[n] = self.lift.route(n, pres=pres if not first else 0.0)
        if self.spread:
            self.lift.stamp(n, self.lifts[n], 1)

    def update(self, pis, old_boxes=()):
        """Re-lift the nets of parts `pis` and every net whose lifted path enters a box
        (the parts' old boxes, passed in, and their new ones)."""
        w = self.w
        boxes = list(old_boxes) + [part_box(w, pi, 3) for pi in pis if pi in w.pose]
        nets = {w.net_id[p["net"]] for pi in pis for p in w.parts[pi].pads
                if p["net"] and w.net_id.get(p["net"]) in w.net_pins}
        for n, lf in self.lifts.items():
            if n in nets or not lf["paths"]:
                continue
            c = np.concatenate(lf["paths"])
            for (y0, x0, y1, x1) in boxes:
                if np.any((c[:, 0] >= y0) & (c[:, 0] <= y1) & (c[:, 1] >= x0) & (c[:, 1] <= x1)):
                    nets.add(n)
                    break
        for n in nets:
            self._relift(n, pres=self.spread_pres if self.spread else 0.0)
        self.relifted = len(nets)
        return self.stats()

    def stats(self):
        G = collapse.build_graph(self.w, self.lifts, pour=collapse.pour_layers(self.w))
        length = sum(float(np.sum(np.sqrt((np.diff(p, axis=0) ** 2).sum(1))))
                     for lf in self.lifts.values() for p in lf["paths"]) * self.w.g
        out = dict(lift_len_mm=round(length, 2), conflicts=len(G.confl), net_pairs=len(G.net_pairs),
                   runs=G.R, critical=sum(r["critical"] for r in G.runs),
                   pad_forbid=sum(1 for _, _, wg in G.unary if wg == collapse.BIG),
                   lift_failed=sum(lf["failed"] for lf in self.lifts.values()))
        if self.exact and G.R:
            xp = collapse.solve_potts(G, sweeps=150, restarts=1)
            x, status, _ = collapse.solve_cpsat(G, time_limit=self.cpsat_s, hint=xp)
            b = collapse.breakdown(G, x)
            out.update(forced_vias=b["vias"], unresolved=b["unresolved"], exact_status=status)
            out["cost"] = round(length + 2.0 * b["vias"] + UNRES_MM * b["unresolved"], 2)
        self.G = G
        return out


def lifted_conflicts(world, **kw):
    return LiftedConflicts(world, **kw).stats()
