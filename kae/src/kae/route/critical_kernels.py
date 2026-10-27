# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Kernel source of the critical router's grid search (see kae.route.critical_grid, which
loads this file twice: as plain Python, the fallback, and compiled by numba with an on-disk
cache, as kae.physics.jit does for the place terms). Module-level functions only.

`astar` is A* over a stack of 8-connected grids (one per copper layer) joined by through
vias: a move costs its length times the mean of the two cells' cost multipliers (inf =
blocked; diagonal moves need both orthogonal neighbours free, so a path never cuts a
blocked corner), a via costs `via_cost` (mm-equivalent) where `via` allows one. The
heuristic is the octile distance to the target cells' bounding box (admissible: every cost
multiplier is >= 1)."""
import heapq
import math

import numpy as np

try:
    jit = _JIT          # noqa: F821  (injected by the loader before execution)
except NameError:       # imported directly: plain Python
    def jit(f):
        return f

INF = math.inf
SQ2 = math.sqrt(2.0)


@jit
def octile(i, j, tx0, tx1, ty0, ty1, res):
    dx = 0
    if i < tx0:
        dx = tx0 - i
    elif i > tx1:
        dx = i - tx1
    dy = 0
    if j < ty0:
        dy = ty0 - j
    elif j > ty1:
        dy = j - ty1
    if dx > dy:
        return res * (dx + (SQ2 - 1.0) * dy)
    return res * (dy + (SQ2 - 1.0) * dx)


@jit
def astar(cost, via, src, dst, nl, ny, nx, res, via_cost, tx0, tx1, ty0, ty1, max_exp):
    """A* from the cells `src` (flat indices) to any cell with dst[k]; returns
    (path as flat indices from source to target, expansions); an empty path when no route
    exists or `max_exp` expansions are exceeded. Flat index k = (layer * ny + j) * nx + i."""
    plane = ny * nx
    n = nl * plane
    g = np.full(n, INF)
    par = np.full(n, -1, np.int64)
    done = np.zeros(n, np.bool_)
    heap = [(0.0, np.int64(0))]
    heap.pop()
    for q in range(src.shape[0]):
        k = src[q]
        if cost[k] < INF and g[k] > 0.0:
            g[k] = 0.0
            r = k % plane
            heapq.heappush(heap, (octile(r % nx, r // nx, tx0, tx1, ty0, ty1, res), np.int64(k)))
    nexp = 0
    goal = -1
    while len(heap) > 0:
        item = heapq.heappop(heap)
        k = item[1]
        if done[k]:
            continue
        done[k] = True
        if dst[k]:
            goal = k
            break
        nexp += 1
        if nexp > max_exp:
            break
        l = k // plane
        r = k - l * plane
        j = r // nx
        i = r - j * nx
        ck = cost[k]
        gk = g[k]
        base = l * plane
        for d in range(8):
            if d == 0:
                di, dj = 1, 0
            elif d == 1:
                di, dj = -1, 0
            elif d == 2:
                di, dj = 0, 1
            elif d == 3:
                di, dj = 0, -1
            elif d == 4:
                di, dj = 1, 1
            elif d == 5:
                di, dj = 1, -1
            elif d == 6:
                di, dj = -1, 1
            else:
                di, dj = -1, -1
            ii = i + di
            jj = j + dj
            if ii < 0 or jj < 0 or ii >= nx or jj >= ny:
                continue
            kk = base + jj * nx + ii
            c = cost[kk]
            if c == INF or done[kk]:
                continue
            if di != 0 and dj != 0:
                if cost[base + j * nx + ii] == INF or cost[base + jj * nx + i] == INF:
                    continue
                step = res * SQ2 * 0.5 * (ck + c)
            else:
                step = res * 0.5 * (ck + c)
            ng = gk + step
            if ng < g[kk]:
                g[kk] = ng
                par[kk] = k
                heapq.heappush(heap, (ng + octile(ii, jj, tx0, tx1, ty0, ty1, res), np.int64(kk)))
        if via[r]:
            for l2 in range(nl):
                if l2 == l:
                    continue
                kk = l2 * plane + r
                if cost[kk] == INF or done[kk]:
                    continue
                ng = gk + via_cost
                if ng < g[kk]:
                    g[kk] = ng
                    par[kk] = k
                    heapq.heappush(heap, (ng + octile(i, j, tx0, tx1, ty0, ty1, res), np.int64(kk)))
    if goal < 0:
        return np.zeros(0, np.int64), nexp
    m = 1
    k = goal
    while par[k] >= 0:
        k = par[k]
        m += 1
    out = np.zeros(m, np.int64)
    k = goal
    q = m - 1
    out[q] = k
    while par[k] >= 0:
        k = par[k]
        q -= 1
        out[q] = k
    return out, nexp
