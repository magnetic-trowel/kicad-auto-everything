# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Grid router for the place-term validations (docs/topics/physics/place-terms.md).

The place terms model a board hop as the straight segment between two terminals. A real
trace must avoid other nets' pads, so it detours. `HopRouter.length` returns the shortest
8-connected grid path (45-degree routing) on one copper side between two points, avoiding
the pads of other nets inflated by half the minimum track width plus the clearance (a trace
necks down between pins; its own width only sets its inductance per length); the length is
the routed length a hop would need at the current poses. Pads on the hop's side and all
through-hole pads are obstacles; the regions around the two endpoints (their own pads) are
free. Dijkstra on the free cells (scipy.sparse.csgraph), no external router.

Used by pt_human_perturb.py to tell a better-than-human perturbation that only looks better
because its straight hop runs through other parts' pads (estimator: route) from one a
router could realise (human choice).
"""
from __future__ import annotations

import math

import numpy as np
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra

INF = float('inf')


class HopRouter:
    """Shortest legal grid route between two points on one side of a board (mm)."""

    def __init__(self, bv, res=0.1, margin=3.0, max_cells=160_000):
        self.bv = bv
        self.res = res
        self.margin = margin
        self.max_cells = max_cells
        net_id = {}
        rows = []
        for p in bv.parts:
            for k in range(len(p.pad_num)):
                nid = net_id.setdefault(p.pad_net[k] or f'__nc{p.i}_{k}', len(net_id))
                tht = p.pad_kind[k] != 'smd'
                rows.append((p.i, p.pad_lx[k], p.pad_ly[k], 0.5 * p.pad_sx[k], 0.5 * p.pad_sy[k], nid, tht))
        self.net_id = net_id
        self.pi = np.array([r[0] for r in rows], np.int64)
        self.lx = np.array([r[1] for r in rows], float)
        self.ly = np.array([r[2] for r in rows], float)
        self.hx = np.array([r[3] for r in rows], float)
        self.hy = np.array([r[4] for r in rows], float)
        self.nid = np.array([r[5] for r in rows], np.int64)
        self.tht = np.array([r[6] for r in rows], bool)

    def pads_board(self, st):
        """Board-frame pad centres, half extents and side sign at the state's poses."""
        i = self.pi
        X = np.asarray(st.X)[i]
        Y = np.asarray(st.Y)[i]
        C = np.asarray(st.C)[i]
        S = np.asarray(st.S)[i]
        G = np.asarray(st.G)[i]
        ly = self.ly * G
        x = X + self.lx * C + ly * S
        y = Y - self.lx * S + ly * C
        # axis-aligned half extents of the rotated pad rectangle
        hx = np.abs(C) * self.hx + np.abs(S) * self.hy
        hy = np.abs(S) * self.hx + np.abs(C) * self.hy
        return x, y, hx, hy, G

    def length(self, st, side, a, b, net, w, clr=None, pads=None):
        """Routed length (mm) from point a to point b on `side` (+1 front, -1 back) for a trace
        of net `net` (or a tuple of nets: a hop that skips a series part joins two) and width
        w; inf when no route exists in the window."""
        clr = self.bv.clearance if clr is None else clr
        (ax, ay), (bx, by) = a, b
        straight = math.hypot(bx - ax, by - ay)
        if straight < 1e-6:
            return 0.0
        res = self.res
        m = max(self.margin, 0.5 * straight)
        x0, y0 = min(ax, bx) - m, min(ay, by) - m
        x1, y1 = max(ax, bx) + m, max(ay, by) + m
        nx = int(math.ceil((x1 - x0) / res)) + 1
        ny = int(math.ceil((y1 - y0) / res)) + 1
        while nx * ny > self.max_cells:
            res *= 1.5
            nx = int(math.ceil((x1 - x0) / res)) + 1
            ny = int(math.ceil((y1 - y0) / res)) + 1
        px, py, hx, hy, G = pads if pads is not None else self.pads_board(st)
        nets = net if isinstance(net, (tuple, list, set, frozenset)) else (net,)
        own = np.array([self.net_id.get(n, -1) for n in nets], np.int64)
        on_side = self.tht | (G == side)
        # a trace necks down to the minimum width between pins; its own width only sets L'
        infl = 0.5 * min(w, self.bv.track_min) + clr
        sel = on_side & ~np.isin(self.nid, own) & (px + hx + infl >= x0) & (px - hx - infl <= x1) & \
            (py + hy + infl >= y0) & (py - hy - infl <= y1)
        blocked = np.zeros((ny, nx), bool)
        for cx, cy, ex, ey in zip(px[sel], py[sel], hx[sel] + infl, hy[sel] + infl):
            # cells whose centres lie inside the inflated pad
            i0 = max(0, int(math.ceil((cx - ex - x0) / res)))
            i1 = min(nx - 1, int(math.floor((cx + ex - x0) / res)))
            j0 = max(0, int(math.ceil((cy - ey - y0) / res)))
            j1 = min(ny - 1, int(math.floor((cy + ey - y0) / res)))
            if i1 >= i0 and j1 >= j0:
                blocked[j0:j1 + 1, i0:i1 + 1] = True
        # the endpoints sit on their own pads: free a disk around each
        yy, xx = np.mgrid[0:ny, 0:nx]
        for (qx, qy) in ((ax, ay), (bx, by)):
            r = max(infl, 0.3)
            blocked[((xx * res + x0 - qx) ** 2 + (yy * res + y0 - qy) ** 2) <= r * r] = False
        s = (int(round((ay - y0) / res)), int(round((ax - x0) / res)))
        g = (int(round((by - y0) / res)), int(round((bx - x0) / res)))
        blocked[s] = False
        blocked[g] = False
        free = ~blocked
        idx = -np.ones((ny, nx), np.int64)
        nf = int(free.sum())
        idx[free] = np.arange(nf)
        rows, cols, wts = [], [], []
        for dj, di, cost in ((0, 1, res), (1, 0, res), (1, 1, res * math.sqrt(2)), (1, -1, res * math.sqrt(2))):
            Aj = slice(0, ny - dj)
            Ai = slice(max(0, -di), nx - max(0, di))
            Bj = slice(dj, ny)
            Bi = slice(max(0, di), nx - max(0, -di))
            A = free[Aj, Ai]
            B = free[Bj, Bi]
            ok = A & B
            if di != 0 and dj != 0:
                # no corner cutting: both orthogonal neighbours free
                ok &= free[Aj, Bi] & free[Bj, Ai]
            ia = idx[Aj, Ai][ok]
            ib = idx[Bj, Bi][ok]
            rows.append(ia)
            cols.append(ib)
            wts.append(np.full(ia.size, cost))
        r = np.concatenate(rows)
        c = np.concatenate(cols)
        wv = np.concatenate(wts)
        M = csr_matrix((np.concatenate([wv, wv]), (np.concatenate([r, c]), np.concatenate([c, r]))), shape=(nf, nf))
        si = idx[s]
        gi = idx[g]
        d = dijkstra(M, directed=False, indices=si, limit=8.0 * straight + 4.0 * m)
        L = float(d[gi])
        if not np.isfinite(L):
            return INF
        # grid snapping of the two endpoints: add the offsets to the cell centres
        L += math.hypot(ax - (x0 + s[1] * res), ay - (y0 + s[0] * res))
        L += math.hypot(bx - (x0 + g[1] * res), by - (y0 + g[0] * res))
        return max(L, straight)
