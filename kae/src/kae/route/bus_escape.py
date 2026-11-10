# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Bus order for package escapes (kae.route.escape.plan_grid's `order`).

A bus (kae.bus's bare-board detector: netlist, parts and pin positions, never copper) that ends on a ball grid
should leave the grid as a ribbon: every lane on the side that faces the bus's other end, and on each layer in
the order its pins have at that other end, so that the lanes reach a line just outside the package (the compress
line, where the planned escapes end) as ordered ports and the trunk between the two ends needs no crossing on that
layer. Lanes that would arrive out of order go to another layer (a split of the bus into increasing subsequences,
whose least number is the permutation's longest decreasing subsequence, LDS).

orders(board_path) -> {package ref: {net at the package: dict(bus, far, width, kind)}}: for each end part of each
bus of width >= MIN_WIDTH (keyboard matrices excluded), the lane net that touches the part, and the position of
that lane's pin at the bus's other end (`far`). The escape planner turns `far` into a side and a rank.
"""
from __future__ import annotations

import math

MIN_WIDTH = 4                       # lanes: narrower groups are left to the planner as they are
SKIP_EV = ("matrix_lines",)         # no shared second end: not a ribbon


def orders(board_path, log=print):
    """{ref: {net: dict(bus, far, width, kind)}} from the bare-board bus detector (see module docstring)."""
    from kae.board.kicad_file import load
    from kae.bus import detect_board
    from kae.bus.detect import line_pad
    board = load(board_path, rules=False)
    board.tracks, board.vias = [], []          # bare-board detection, whatever the file holds
    bs = detect_board(board)
    out = {}
    n = 0
    for bi, (row, raw) in enumerate(zip(bs.buses, bs.raw)):
        if row.get("width", 0) < MIN_WIDTH or any(e in SKIP_EV for e in row.get("ev") or ()):
            continue
        a, b = raw.get("a"), raw.get("b")
        if not a or not b:
            continue
        for ref, other in ((a, b), (b, a)):
            for ln in raw["lanes"]:
                if ref not in ln.terms or other not in ln.terms:
                    continue
                here, far = line_pad(ln, ref), line_pad(ln, other)
                if not here.net:
                    continue
                out.setdefault(ref, {})[here.net] = dict(bus=bi, far=(far.x, far.y), width=row["width"],
                                                         kind=row.get("kind"))
        n += 1
    log(f"bus order: {n} buses of width >= {MIN_WIDTH}, ends on {len(out)} parts")
    return out


def lis_keep(seq):
    """Indices of a longest non-decreasing subsequence of `seq` (patience sorting, O(n log n))."""
    import bisect
    tails, tails_i, prev = [], [], [None] * len(seq)
    for i, x in enumerate(seq):
        j = bisect.bisect_right(tails, x)
        if j == len(tails):
            tails.append(x)
            tails_i.append(i)
        else:
            tails[j] = x
            tails_i[j] = i
        prev[i] = tails_i[j - 1] if j > 0 else None
    keep, i = [], tails_i[-1] if tails_i else None
    while i is not None:
        keep.append(i)
        i = prev[i]
    return sorted(keep)


def frame(pkg, xy):
    """Board point `xy` in package `pkg`'s frame (u, w), centred on the package."""
    ca, sa = math.cos(-pkg["ang"]), math.sin(-pkg["ang"])
    cx, cy = pkg["centre"]
    dx, dy = xy[0] - cx, xy[1] - cy
    return dx * ca - dy * sa, dx * sa + dy * ca


def bus_side(pkg, fars):
    """The package side ('W', 'E', 'S', 'N') facing the centroid of a bus's far pins."""
    u = sum(frame(pkg, f)[0] for f in fars) / len(fars)
    w = sum(frame(pkg, f)[1] for f in fars) / len(fars)
    if abs(u) >= abs(w):
        return "E" if u > 0 else "W"
    return "N" if w > 0 else "S"
