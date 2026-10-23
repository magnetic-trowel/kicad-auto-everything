# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Congestion penalties in the placer's cost: routing history as extra RUDY demand.

The annealer's routability term (kae.place.cost.Congestion) prices each bin's routing
utilization u_b = (net demand + pin escape demand) / supply above a target, squared. The
joint loop adds the congestion history of the routed board (feedback.CongestionHistory:
where Freerouting failed) to the pin-escape demand array of those bins, as utilization
times the bin's supply. Moves that keep nets and pins in a failed region then pay more,
exactly as PathFinder's history cost makes a congested node dearer for every net.

The extra demand is static (it never moves with a part), so the incremental bookkeeping of
both engines stays exact: the reference Annealer reads `cong.Dp` directly; the compiled
FastAnnealer copied it into its engine arrays at construction (and copies it again when it
rebuilds), so both copies get the same addition, and the engine's congestion total is
re-read from the reference.

This reaches into the annealer's congestion arrays; the placer owner has been asked for a
public hook (`cong_args={"history": array}`), which `apply_history` will use once it exists.
"""
from __future__ import annotations

import numpy as np


def _reference(ann):
    """The reference Annealer (the compiled engine keeps one as .ann)."""
    return getattr(ann, "ann", ann)


def apply_history(ann, history, scale=1.0, window=None):
    """Add `scale` x history (feedback.CongestionHistory, in utilization units) as static
    demand to the annealer's congestion bins; with `window` = (x0, y0, x1, y1) mm, only to
    bins within 2 bins of it (history far away cannot change a local move's cost, but would
    shift the reported total). Returns a report dict (applied: False when the annealer has no
    congestion term)."""
    ref = _reference(ann)
    c = getattr(ref, "cong", None)
    if c is None or history is None or scale <= 0:
        return dict(applied=False, reason="no congestion term" if c is None else "no history")
    extra = history.sample(c.x0, c.y0, c.b, c.nbx, c.nby) * float(scale)
    if window is not None:
        x0, y0, x1, y1 = window
        i0 = max(0, int((x0 - c.x0) / c.b) - 2)
        i1 = min(c.nbx, int((x1 - c.x0) / c.b) + 3)
        j0 = max(0, int((y0 - c.y0) / c.b) - 2)
        j1 = min(c.nby, int((y1 - c.y0) / c.b) + 3)
        mask = np.zeros_like(extra, dtype=bool)
        mask[i0:i1, j0:j1] = True
        extra = np.where(mask, extra, 0.0)
    if not extra.any():
        return dict(applied=False, reason="no history in the window")
    demand = extra * c.S0
    before = c.total()
    c.Dp += demand
    E = getattr(ann, "E", None)
    if E is not None and ann is not ref:
        if getattr(E, "Dp", None) is None or E.Dp.shape != demand.shape:
            c.Dp -= demand
            return dict(applied=False, reason="engine without congestion bins")
        E.Dp[:, :] += demand
        try:
            from kae.place.engine import T_CONG
            E.tot[T_CONG] = c.total()
        except ImportError:  # pragma: no cover - the engine module is what built E
            pass
    return dict(applied=True, bins=int((extra > 0).sum()), peak=round(float(extra.max()), 3),
                cong_before=round(before, 6), cong_after=round(c.total(), 6))
