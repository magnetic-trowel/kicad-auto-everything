# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Congestion penalties in the placer's cost: routing history as extra RUDY demand.

The annealer's routability term (kae.place.cost.Congestion) prices each bin's routing
utilization u_b = (net demand + pin escape demand) / supply above a target, squared. The
joint loop adds the congestion history of the routed board (feedback.CongestionHistory:
where Freerouting failed) to the static demand of those bins, as utilization times the
bin's empty-board supply. Moves that keep nets and pins in a failed region then pay more,
as PathFinder's history cost makes a congested node dearer for every net.

The placer takes it through its hook: `make_annealer(..., cong_history=f)` (also
`local_replace(cong_history=...)`) calls f(x0, y0, b, nbx, nby) once with its bins and adds
the returned (nbx, nby) array, in track mm per bin, to `Congestion.Dp`. The extra demand
never moves with a part, so both engines stay exactly incremental. `history_hook` builds
f; the supply per bin is the placer's own formula (Congestion: copper layers x bin area /
track pitch, pitch = max(0.25, minimum track + minimum clearance)).
"""
from __future__ import annotations

import numpy as np


def bin_supply(P, b):
    """Track mm a bin of size b holds on an empty board (kae.place.cost.Congestion.S0)."""
    board = P.board
    layers = len(board.stackup.copper) if getattr(board, "stackup", None) else 2
    rules = board.rules
    pitch = max(0.25, (rules.track_min if rules and rules.track_min else 0.2) + P.clr_min)
    return layers * b * b / pitch


def history_hook(P, history, scale=1.0, window=None, report=None):
    """The placer's cong_history callable for `history` (feedback.CongestionHistory, in
    utilization units) x `scale`; with `window` = (x0, y0, x1, y1) mm, only bins within two
    bins of it (history far away cannot change a local move's cost, but would shift the
    reported total). `report` (a dict) receives what was added. None when there is nothing
    to add."""
    if history is None or scale <= 0 or not history.h.any():
        return None

    def f(x0, y0, b, nbx, nby):
        extra = history.sample(x0, y0, b, nbx, nby) * float(scale)
        if window is not None:
            wx0, wy0, wx1, wy1 = window
            i0 = max(0, int((wx0 - x0) / b) - 2)
            i1 = min(nbx, int((wx1 - x0) / b) + 3)
            j0 = max(0, int((wy0 - y0) / b) - 2)
            j1 = min(nby, int((wy1 - y0) / b) + 3)
            mask = np.zeros_like(extra, dtype=bool)
            mask[i0:i1, j0:j1] = True
            extra = np.where(mask, extra, 0.0)
        if report is not None:
            report.update(applied=bool(extra.any()), bins=int((extra > 0).sum()),
                          peak=round(float(extra.max()) if extra.size else 0.0, 3))
        return extra * bin_supply(P, b)

    return f
