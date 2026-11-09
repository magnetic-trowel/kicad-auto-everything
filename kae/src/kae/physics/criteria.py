# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Pass/fail criteria shared by the placer (kae.physics), the router's prices (kae.em.spectral) and the
evaluators (kae.excite.evaluate, kae.excite.wideband, kae.intent): one number per criterion, so a
layout the placer calls within budget is one the evaluator calls within budget.

Switch-node overshoot (docs/topics/rules/power/hot-loops.md, place-terms.md section 1):
    the switch node's peak, V_bus + overshoot, stays at or below OVERSHOOT_DERATE (0.85) of the
    switch's absolute maximum V_abs. V_abs is the part's stated rating (the SW pin's transient rating
    where its datasheet gives one) when known, else the prior: the smallest standard rating at least
    RATING_MARGIN (1.25) times the bus voltage. Above the derated line the switch runs without its
    reliability margin (a warning); above V_abs itself it is outside its rating and fails in use (a
    block hazard, `overshoot_hazard`).

Cable common mode (docs/topics/physics/fields-emi-budget.md section 1, step 5'):
    a cable of length l carrying common-mode current I radiates at distance r, over a ground plane,
        E = 1.257e-6 f l I / r      (Ott, EMC Engineering, eq. 12-7: a short dipole, l << lambda/2)
    capped at the resonant cable's
        E = 2 x 60 I / r            (a half-wave dipole's broadside field 60 I / r, Balanis, Antenna
                                     Theory, sec. 4.6; doubled by the ground reflection as in 12-7)
    The cap takes over at f = 120 / (1.257e-6 l): 95 MHz for 1 m. The limit is CISPR 32 class B at
    10 m, 30 dBuV/m over 30-230 MHz.
"""
from __future__ import annotations

import math

# ----------------------------------------------------------------------------- switch-node overshoot
V_ABS_LADDER = (5.5, 6.0, 7.0, 10.0, 12.0, 16.0, 18.0, 20.0, 24.0, 28.0, 30.0, 36.0, 40.0, 42.0, 50.0,
                60.0, 65.0, 80.0, 100.0, 150.0, 200.0, 250.0, 400.0, 600.0)
RATING_MARGIN = 1.25            # parts are rated one standard step above 1.25 x their bus (E5)
OVERSHOOT_DERATE = 0.85         # peak stress <= 85 % of the absolute maximum (see hot-loops.md)


def shared_overshoot():
    """Whether the methods (the placer's hot-loop allocation, the router's spectral prices) use this
    criterion with the switch's own rating: KAE_SHARED_OVERSHOOT=1. Off by default, so a run reproduces
    the methods as they were until the A/B (docs/research/physics/component-priors.md) decides; the
    evaluators and the hazards always use it."""
    import os
    return os.environ.get("KAE_SHARED_OVERSHOOT", "0").strip().lower() in ("1", "true", "yes", "on")


def v_abs_prior(v_bus, margin=RATING_MARGIN):
    """Smallest standard rating >= margin * V_bus: the switch's absolute maximum when no datasheet says."""
    for v in V_ABS_LADDER:
        if v >= margin * v_bus:
            return v
    return margin * v_bus


def overshoot_limits(v_bus, v_abs=None, derate=OVERSHOOT_DERATE):
    """(allowed overshoot above V_bus at the derated line, overshoot that reaches V_abs itself, V_abs used,
    whether V_abs is the part's own rating). Overshoots are in V above the bus."""
    known = v_abs is not None and v_abs > 0
    va = float(v_abs) if known else v_abs_prior(max(v_bus, 1e-3))
    return max(derate * va - v_bus, 1e-3), max(va - v_bus, 1e-3), va, known


def overshoot_basis(v_bus, v_abs=None, derate=OVERSHOOT_DERATE):
    _, _, va, known = overshoot_limits(v_bus, v_abs, derate)
    src = "the switch's rating" if known else f"prior: the next standard rating >= {RATING_MARGIN:g} x V"
    return f"peak <= {derate:g} x V_abs ({va:g} V, {src}) on a {v_bus:g} V bus"


def overshoot_hazard(cell, objects, v_bus, overshoot, v_abs=None, derate=OVERSHOOT_DERATE, where=""):
    """A hazard (docs: the shared schema of kae reports) when the switch node's peak V_bus + overshoot
    passes the derated line (warn) or the absolute maximum itself (block when the rating is the part's,
    warn when it is the prior's: the part may be rated higher). None when within the derated line."""
    ok, at_abs, va, known = overshoot_limits(v_bus, v_abs, derate)
    if overshoot <= ok:
        return None
    peak = v_bus + overshoot
    ev = dict(V_bus=round(v_bus, 3), overshoot_V=round(overshoot, 3), peak_V=round(peak, 3), V_abs=va,
              V_abs_source="part" if known else "prior", derated_peak_V=round(derate * va, 3),
              limit_source="hot-loops.md: peak <= 0.85 x V_abs; above V_abs the switch is outside its rating")
    if overshoot > at_abs:
        sev = "block" if known else "warn"
        msg = (f"{cell}: the switch node rings to {peak:.3g} V{where}, above the switch's absolute maximum "
               f"{va:g} V" + ("" if known else " (a prior: no rating known)") + ": the part would fail in use")
        code = "overshoot_over_abs_max"
    else:
        sev = "warn"
        msg = (f"{cell}: the switch node rings to {peak:.3g} V{where}, above {derate:g} x its {va:g} V rating "
               f"({derate * va:.3g} V): no reliability margin left")
        code = "overshoot_over_derating"
    fix = ("shrink the hot loop (input capacitor beside the switch and its ground, on the same layer, "
           "return on the adjacent plane), or slow the edge / add a snubber")
    if not known:
        fix += "; state the switch's V_max (intent cells.<id>.V_max_V or kae/src/kae/excite/parts.json)"
    return dict(code=code, severity=sev, category="electrical", message=msg, objects=list(objects),
                evidence=ev, fix=fix)


# ----------------------------------------------------------------------------- cable common mode
OTT_K = 1.257e-6                # V/m per (Hz m A / m): mu0 f l I / r x 2 (ground reflection)
E_CAP_K = 2 * 60.0              # V/m per (A / m): a resonant cable's field, ground reflection included
CISPR32_B_10M = 10 ** (30.0 / 20) * 1e-6     # V/m, 30-230 MHz at 10 m
F_CM = (30e6, 230e6)
R_CM = 10.0                     # m, the CISPR 32 class B distance
L_CABLE_M = 1.0
Z_CM = 150.0                    # ohm, a typical cable's common-mode impedance (fields-emi-budget.md)


def cable_e(f, i, l=L_CABLE_M, r=R_CM):
    """Field (V/m) at r from a cable of length l carrying common-mode current i (A) at f (Hz)."""
    return min(OTT_K * f * l, E_CAP_K) * i / r


def cable_i_lim(f, l=L_CABLE_M, r=R_CM, e_lim=CISPR32_B_10M):
    """The common-mode current (A) at f that radiates the limit field."""
    return e_lim * r / min(OTT_K * f * l, E_CAP_K)


def cable_v_lim(f, l=L_CABLE_M, z_cm=Z_CM):
    """The common-mode voltage (V) at f between two cable attachment points that drives the limit current
    through the cable's common-mode impedance."""
    return z_cm * cable_i_lim(f, l)
