# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""A placement on the problem grid, and grid-level legality.

`State` holds, for every part, the grid origin (X, Y) and rotation index K (movable parts;
fixed parts keep their input pose). Grid legality (`grid_violations`) is exact for the
rectangles of kae.place.problem: own/opposite rectangles pairwise per side, fixed
obstacles, and the outline (each part's `board` rectangle on inside cells only). Grid-legal
implies legal for courtyards, copper clearance and edge clearance, up to what the
rectangles over-approximate; kae.place.legalize.exact_check confirms with polygons.
"""
from __future__ import annotations

import numpy as np

from kae.board import transform


class State:
    def __init__(self, P, X=None, Y=None, K=None):
        n = len(P.parts)
        self.P = P
        self.X = np.zeros(n, dtype=np.int64) if X is None else np.asarray(X, dtype=np.int64).copy()
        self.Y = np.zeros(n, dtype=np.int64) if Y is None else np.asarray(Y, dtype=np.int64).copy()
        self.K = np.zeros(n, dtype=np.int64) if K is None else np.asarray(K, dtype=np.int64).copy()

    def copy(self):
        return State(self.P, self.X, self.Y, self.K)

    # ------------------------------------------------------------------ poses
    def xy(self, i):
        """Board mm of part i's origin (fixed parts: their input pose)."""
        p = self.P.parts[i]
        if not p.movable:
            return p.x0, p.y0
        return self.P.ox + self.X[i] * self.P.g, self.P.oy + self.Y[i] * self.P.g

    def rot(self, i):
        p = self.P.parts[i]
        return p.rots[self.K[i]].rot if p.movable else p.rot0

    def pose(self, i):
        x, y = self.xy(i)
        p = self.P.parts[i]
        return (round(float(x), 6), round(float(y), 6), transform.norm_deg(self.rot(i)), p.side)

    def poses(self, movable_only=True):
        """{uuid: (x, y, rot, side)} in board mm and degrees."""
        return {p.uuid: self.pose(p.i) for p in self.P.parts if p.movable or not movable_only}

    def pins_xy(self, i):
        """(n_pads, 2) absolute pad positions of part i."""
        p = self.P.parts[i]
        x, y = self.xy(i)
        r = p.rots[self.K[i]] if p.movable else p.rots[0]
        return r.pins + np.array([x, y])

    def center(self, i):
        p = self.P.parts[i]
        r = p.rots[self.K[i]] if p.movable else p.rots[0]
        x, y = self.xy(i)
        return x + (r.own[0] + r.own[2]) / 2, y + (r.own[1] + r.own[3]) / 2

    # ------------------------------------------------------------------ grid rectangles
    def grid_rects(self, i):
        """[(side, (i0, i1, j0, j1), kind)] absolute grid rectangles of a movable part."""
        p = self.P.parts[i]
        r = p.rots[self.K[i]]
        X, Y = int(self.X[i]), int(self.Y[i])
        si = 0 if p.s > 0 else 1
        a, b, c, d = r.g_own
        out = [(si, (X + a, X + b, Y + c, Y + d), "own")]
        for (a, b, c, d) in r.g_opp:
            out.append((1 - si, (X + a, X + b, Y + c, Y + d), "opp"))
        return out

    def board_rect(self, i):
        p = self.P.parts[i]
        a, b, c, d = p.rots[self.K[i]].g_board
        X, Y = int(self.X[i]), int(self.Y[i])
        return (X + a, X + b, Y + c, Y + d)

    def hpwl(self, signal_only=False):
        """Weighted half-perimeter wirelength in mm over all nets (or signal nets)."""
        P = self.P
        pos = [self.pins_xy(i) for i in range(len(P.parts))]
        tot = 0.0
        for net in P.nets:
            if signal_only and net.kind in ("ground", "power"):
                continue
            pts = np.array([pos[i][k] for (i, k) in net.pins])
            if len(pts) < 2:
                continue
            w = 1.0 if signal_only else net.weight
            tot += w * (np.ptp(pts[:, 0]) + np.ptp(pts[:, 1]))
        return float(tot)


def _overlaps(rects):
    """Pairs (a, b) of indices into rects [(i0, i1, j0, j1)] that overlap (open sets)."""
    if len(rects) < 2:
        return []
    R = np.asarray(rects, dtype=np.int64)
    ox = (np.minimum(R[:, None, 1], R[None, :, 1]) > np.maximum(R[:, None, 0], R[None, :, 0]))
    oy = (np.minimum(R[:, None, 3], R[None, :, 3]) > np.maximum(R[:, None, 2], R[None, :, 2]))
    hit = np.triu(ox & oy, 1)
    a, b = np.nonzero(hit)
    return list(zip(a.tolist(), b.tolist()))


def grid_violations(st, parts=None):
    """Grid-level violations of movable parts: {part: [reason, ...]}.

    Reasons: ('overlap', other part), ('obstacle', why), ('outline', cells outside)."""
    P = st.P
    mov = [i for i in (parts if parts is not None else P.mov)]
    out = {}
    per_side = {0: [], 1: []}
    for i in mov:
        for side, r, kind in st.grid_rects(i):
            per_side[side].append((r, i, kind))
    for ob in P.obstacles:
        per_side[ob.side].append((ob.g, -1, ob.why))
    for side in (0, 1):
        L = per_side[side]
        for a, b in _overlaps([r for r, _, _ in L]):
            ia, ka = L[a][1], L[a][2]
            ib, kb = L[b][1], L[b][2]
            if ia == ib:
                continue
            if ia >= 0 and ib >= 0:
                out.setdefault(ia, []).append(("overlap", ib))
                out.setdefault(ib, []).append(("overlap", ia))
            elif ia >= 0:
                out.setdefault(ia, []).append(("obstacle", kb))
            elif ib >= 0:
                out.setdefault(ib, []).append(("obstacle", ka))
    for i in mov:
        X, Y = int(st.X[i]), int(st.Y[i])
        n = P.outside_cells_all(X, Y, P.parts[i].rots[st.K[i]].g_boards)
        if n:
            out.setdefault(i, []).append(("outline", n))
    return out
