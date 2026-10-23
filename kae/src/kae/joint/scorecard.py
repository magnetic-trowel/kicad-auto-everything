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

`accept(old, new)` keeps an iteration only when it is no worse in legality, completion and
DRC errors, no worse in routed physics (beyond `phys_tol`, for float noise), and better in
at least one of them, compared lexicographically: legality, then unconnected + errors, then
physics. Anything else is reverted.
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


def accept(old, new, phys_tol=0.005):
    """(keep, why). See the module docstring."""
    if new.placement_errors > old.placement_errors:
        return False, f"legality worse ({old.placement_errors} -> {new.placement_errors} placement errors)"
    if new.unconnected > old.unconnected:
        return False, f"completion dropped ({old.unconnected} -> {new.unconnected} unconnected)"
    if new.errors > old.errors:
        return False, f"DRC errors rose ({old.errors} -> {new.errors})"
    # physics on the modules both boards know (the module set comes from one brief)
    ids = sorted(set(old.modules) | set(new.modules))
    p0, p1 = _phys_on(old, ids), _phys_on(new, ids)
    if p1 > p0 + phys_tol * max(1.0, abs(p0)):
        return False, f"physics worse ({p0:.4f} -> {p1:.4f})"
    k0 = (old.placement_errors, old.unconnected + old.errors, old.unconnected, round(p0, 6))
    k1 = (new.placement_errors, new.unconnected + new.errors, new.unconnected, round(p1, 6))
    if k1 < k0 and (k1[:3] < k0[:3] or p1 < p0 - phys_tol * max(1.0, abs(p0))):
        return True, f"better {k0} -> {k1}"
    return False, "no improvement"
