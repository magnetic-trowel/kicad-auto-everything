# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Heat sinks in placement: keep a part sink's body clear, pull hot parts towards cooled regions.

The board's operating facts (kae.excite: requirements.thermal, written by
tools/research/physics/intent_from_spec.py) may name heat sinks:

- a part sink {"part": ref, "theta_sa_C_W", ..., "outline_mm": [w, l], "offset_mm": [dx, dy]?,
  "height_mm"?}: the sink's footprint seen from above, in the part's own frame, centred on the
  part's origin unless offset. Other parts on the part's side stay out of it: the part's occupancy
  grows by the sink's overhang on each side (Problem.set_escape, the hard band; legality still comes
  first, pipeline._escalate). A part sink without an outline reserves nothing (reported).
- a region sink {"side": "top"|"bottom", "region": [x0, y0, x1, y1] board mm | "board", ...}: a
  plate or a fan's air under part of the board. Parts that dissipate at least `heat_min_W`
  (parts.<ref>.P_sustained_W) are pulled into the region by the annealer's label term (an L1 pull
  beyond a dead zone, kae.place.labels), weighted by their watts x `heat_pull_w`. A region of the
  whole board pulls nothing: every place is cooled.

Operating facts come from `--set operating=PATH` or the project's KAE_OPERATING text variable
(kae.route.constraints.setting). Nothing here is written to the board.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from kae.route.constraints import setting


def operating(board_path=None, opts=None):
    """The operating facts (a dict), or {} when none are given or the file cannot be read."""
    p = setting("operating", board_path, opts)
    if not p:
        return {}
    try:
        return json.loads(Path(str(p)).read_text())
    except (OSError, ValueError):
        return {}


def sinks(op):
    th = ((op or {}).get("requirements") or {}).get("thermal") or {}
    return [h for h in (th.get("heatsinks") or []) if isinstance(h, dict)]


def watts(op):
    """{ref: sustained dissipation W} of the parts the operating facts give it for."""
    out = {}
    for ref, v in ((op or {}).get("parts") or {}).items():
        w = (v or {}).get("P_sustained_W") if isinstance(v, dict) else None
        if isinstance(w, (int, float)) and w > 0:
            out[ref] = float(w)
    return out


def _extent(fp):
    from .escape_band import _extent as ext
    xs = [p.lx for p in fp.pads] or [0.0]
    ys = [p.ly for p in fp.pads] or [0.0]
    return ext(fp, min(xs), min(ys), max(xs), max(ys))


def sink_bands(P, op):
    """({part index: (left, top, right, bottom) mm, library frame}, report rows) for the part
    sinks with an outline: the sink's overhang beyond the part's own extent on each side."""
    by_ref = {p.ref: p for p in P.parts}
    out, rows = {}, []
    for h in sinks(op):
        ref = h.get("part")
        if not ref:
            continue
        p = by_ref.get(ref)
        ol = h.get("outline_mm")
        if p is None:
            rows.append(dict(part=ref, skipped="no such part"))
            continue
        if not (isinstance(ol, (list, tuple)) and len(ol) == 2 and all(isinstance(x, (int, float)) and x > 0 for x in ol)):
            rows.append(dict(part=ref, skipped="no outline_mm: nothing reserved"))
            continue
        dx, dy = (h.get("offset_mm") or [0.0, 0.0])[:2]
        sx0, sy0, sx1, sy1 = dx - ol[0] / 2, dy - ol[1] / 2, dx + ol[0] / 2, dy + ol[1] / 2
        x0, y0, x1, y1 = _extent(p.fp)
        band = (max(0.0, x0 - sx0), max(0.0, y0 - sy0), max(0.0, sx1 - x1), max(0.0, sy1 - y1))
        out[p.i] = band
        rows.append(dict(part=ref, band_mm=[round(b, 3) for b in band], movable=p.movable))
    return out, rows


def pull_anchors(P, op, board_path=None, opts=None):
    """({part index: ([(X, Y) target origin per rotation], (rx, ry) dead zone cells, weight)}, report
    rows): the annealer's label-term targets that put each hot part inside a region sink."""
    w_per = float(setting("heat_pull_w", board_path, opts))
    w_min = float(setting("heat_min_W", board_path, opts))
    regions = [h for h in sinks(op) if isinstance(h.get("region"), (list, tuple)) and len(h["region"]) == 4]
    hot = {ref: w for ref, w in watts(op).items() if w >= w_min}
    if not regions or not hot or w_per <= 0:
        return {}, []
    by_ref = {p.ref: p for p in P.parts}
    out, rows = {}, []
    g = P.g
    for ref, w in sorted(hot.items(), key=lambda kv: -kv[1]):
        p = by_ref.get(ref)
        if p is None or not p.movable:
            continue
        # the region nearest the part's input pose (its centre's distance to each box)
        def dist(rg):
            x0, y0, x1, y1 = rg["region"]
            return math.hypot(max(x0 - p.x0, 0.0, p.x0 - x1), max(y0 - p.y0, 0.0, p.y0 - y1))
        rg = min(regions, key=dist)
        x0, y0, x1, y1 = (float(v) for v in rg["region"])
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        tg, half = [], [0.0, 0.0]
        for r in p.rots:
            a, b, c, d = r.own
            tg.append((int(round((cx - P.ox - (a + c) / 2) / g)), int(round((cy - P.oy - (b + d) / 2) / g))))
            half = [max(half[0], (c - a) / 2), max(half[1], (d - b) / 2)]
        rx = max(0, int(math.floor(((x1 - x0) / 2 - half[0]) / g)))
        ry = max(0, int(math.floor(((y1 - y0) / 2 - half[1]) / g)))
        out[p.i] = (tg, (rx, ry), w_per * w)
        rows.append(dict(part=ref, W=round(w, 3), region=[x0, y0, x1, y1], side=rg.get("side")))
    return out, rows
