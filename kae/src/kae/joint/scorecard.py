# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The joint loop's judgement of one placed and routed board, and the acceptance rule.

A Scorecard holds what KiCad and the routed-physics recheck say about a board:
- legality: placement errors (exact check of the poses; KiCad's placement-type DRC errors);
- completion: KiCad's unconnected items; DRC: error-level violations (library-environment
  checks excluded, as kaebench);
- physics: per module the routed utilization u = value / allocation (critical_recheck), and
  their sum, each capped at U_CAP, a module without a value counted at U_MISSING; the place
  terms' straight-line total is reported beside it.

`accept(old, new)` compares lexicographically: legality, then completion and DRC
(unconnected + errors, then unconnected), then routed physics. Legality, unconnected items
and DRC errors must never get worse. A strict gain in completion or DRC is kept when routed
physics worsens by at most `phys_slack` (10 % of the incumbent's total); with equal
completion and DRC, physics must improve beyond `phys_tol` (float noise). Anything else is
reverted. (A strict reading, physics never worse, is phys_slack=0: on the noisecard smoke
run it reverted a window that halved the unconnected items, 15 -> 7, at +33 % physics.)
"""
from __future__ import annotations

from dataclasses import dataclass, field

U_CAP = 5.0          # one module far over budget must not hide every other module's change
U_MISSING = 3.0      # a module whose routed value cannot be computed (copper missing)

# KiCad DRC types that make a placement illegal (kaebench's PLACEMENT_ERROR_TYPES). Only
# reported here: a routed board's clearance errors may be the router's, so legality is
# judged by the placer's exact check.
PLACEMENT_TYPES = ("courtyards_overlap", "copper_edge_clearance", "clearance", "hole_clearance", "hole_to_hole",
                   "holes_co_located", "items_not_allowed", "malformed_courtyard", "npth_inside_courtyard",
                   "pth_inside_courtyard", "shorting_items")


def physics_total(modules):
    """Sum of capped routed utilizations: modules {id: u or None}."""
    tot = 0.0
    for _, u in sorted(modules.items()):
        tot += U_MISSING if u is None else min(U_CAP, max(0.0, float(u)))
    return tot


@dataclass
class Scorecard:
    placement_errors: int = 0          # exact placement violations (0 = legal)
    unconnected: int = 0
    errors: int = 0
    errors_by_type: dict = field(default_factory=dict)
    modules: dict = field(default_factory=dict)      # module id -> routed u (None: no value)
    flagged: list = field(default_factory=list)      # modules the recheck flags
    place_terms: float | None = None                 # straight-line place-terms total
    worst_rail_mohm: float | None = None
    note: str = ""

    @property
    def physics(self):
        return physics_total(self.modules)

    @property
    def legal(self):
        return self.placement_errors == 0

    def key(self):
        """Lower is better, lexicographically."""
        return (self.placement_errors, self.unconnected + self.errors, self.unconnected, round(self.physics, 6))

    def to_dict(self):
        return dict(legal=self.legal, placement_errors=self.placement_errors, unconnected=self.unconnected,
                    errors=self.errors, errors_by_type=dict(self.errors_by_type), physics=round(self.physics, 4),
                    modules={k: (None if v is None else round(v, 4)) for k, v in sorted(self.modules.items())},
                    flagged=list(self.flagged), place_terms=None if self.place_terms is None else round(self.place_terms, 4),
                    worst_rail_mohm=self.worst_rail_mohm, **({"note": self.note} if self.note else {}))


def _phys_on(card, ids):
    return physics_total({k: card.modules.get(k) for k in ids})


def accept(old, new, phys_tol=0.005, phys_slack=0.10):
    """(keep, why). See the module docstring. `phys_slack`: how much routed physics (share
    of the incumbent's total) a strict completion/DRC gain may cost; 0 makes physics a hard
    guard even then."""
    if new.placement_errors > old.placement_errors:
        return False, f"legality worse ({old.placement_errors} -> {new.placement_errors} placement errors)"
    if new.unconnected > old.unconnected:
        return False, f"completion dropped ({old.unconnected} -> {new.unconnected} unconnected)"
    if new.errors > old.errors:
        return False, f"DRC errors rose ({old.errors} -> {new.errors})"
    # physics on the modules both boards know (the module set comes from one brief)
    ids = sorted(set(old.modules) | set(new.modules))
    p0, p1 = _phys_on(old, ids), _phys_on(new, ids)
    k0 = (old.placement_errors, old.unconnected + old.errors, old.unconnected)
    k1 = (new.placement_errors, new.unconnected + new.errors, new.unconnected)
    scale = max(1.0, abs(p0))
    if k1 < k0:
        if p1 > p0 + max(phys_tol, phys_slack) * scale:
            return False, f"physics worse beyond the slack ({p0:.4f} -> {p1:.4f}) for {k0} -> {k1}"
        return True, f"better {k0} -> {k1}, physics {p0:.4f} -> {p1:.4f}"
    if p1 > p0 + phys_tol * scale:
        return False, f"physics worse ({p0:.4f} -> {p1:.4f})"
    if p1 < p0 - phys_tol * scale:
        return True, f"physics better ({p0:.4f} -> {p1:.4f})"
    return False, "no improvement"
