# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Physics-priced path search: A* whose move costs carry the copper's physics.

A move of length l on layer L from cell c to c' in direction (dx, dy) costs

    l * base(L, c, c')                             legality and congestion (mm-equivalent, inf = blocked)
  + lam * l * self(L, c, c')                       the new copper's own loop inductance per length
                                                    over its local reference (priced, H/mm -> cost)
  + lam * (Px(L) dx + Py(L) dy) * p                signed coupling to every existing current (the
                                                    price fields, kae.em.fields), per cell step

with cell-pair means of each array. The coupling term is signed: running beside a current of
the opposite sense (the hop's own return) lowers the loop and is a gain. A move's total is
floored at `floor` times its length so the search stays well-posed, and the heuristic uses the
smallest per-length cost any cell offers, so it stays admissible.
"""
from __future__ import annotations

import heapq
import math

import numpy as np

try:
    import numba
    jit = numba.njit(cache=True)
except ImportError:                       # pragma: no cover
    def jit(f):
        return f

SQ2 = math.sqrt(2.0)


@jit
def _astar(base, selfc, px, py, pot, void, via_ok, src, dst, nl, ny, nx, res, via_cost, lam, floor, hmin, ti, tj):
    plane = ny * nx
    n = nl * plane
    g = np.full(n, np.inf)
    par = np.full(n, -1, np.int64)
    done = np.zeros(n, np.bool_)
    heap = [(0.0, np.int64(0))]
    heap.pop()
    for q in range(src.shape[0]):
        k = src[q]
        if base[k] < np.inf:
            g[k] = 0.0
            heapq.heappush(heap, (0.0, k))
    di = (1, -1, 0, 0, 1, 1, -1, -1)
    dj = (0, 0, 1, -1, 1, -1, 1, -1)
    while heap:
        f, k = heapq.heappop(heap)
        if done[k]:
            continue
        done[k] = True
        if dst[k]:
            path = []
            while k >= 0:
                path.append(k)
                k = par[k]
            return path[::-1]
        l = k // plane
        r = k - l * plane
        j = r // nx
        i = r - j * nx
        for m in range(8):
            i2 = i + di[m]
            j2 = j + dj[m]
            if i2 < 0 or j2 < 0 or i2 >= nx or j2 >= ny:
                continue
            k2 = l * plane + j2 * nx + i2
            if base[k2] == np.inf or done[k2]:
                continue
            diag = m >= 4
            if diag:
                if base[l * plane + j * nx + i2] == np.inf or base[l * plane + j2 * nx + i] == np.inf:
                    continue
            ln = res * (SQ2 if diag else 1.0)
            c = ln * 0.5 * (base[k] + base[k2]) + lam * ln * 0.5 * (selfc[k] + selfc[k2])
            c += lam * res * (0.5 * (px[k] + px[k2]) * di[m] + 0.5 * (py[k] + py[k2]) * dj[m])
            if void[k] or void[k2]:
                c += lam * (pot[k2] - pot[k])          # the crossing term, telescoped over the void
            if c < floor * ln:
                c = floor * ln
            ng = g[k] + c
            if ng < g[k2]:
                g[k2] = ng
                par[k2] = k
                h = hmin * res * max(abs(i2 - ti), abs(j2 - tj))
                heapq.heappush(heap, (ng + h, k2))
        if via_ok[r]:
            for l2 in range(nl):
                if l2 == l:
                    continue
                k2 = l2 * plane + r
                if base[k2] == np.inf or done[k2]:
                    continue
                ng = g[k] + via_cost
                if ng < g[k2]:
                    g[k2] = ng
                    par[k2] = k
                    h = hmin * res * max(abs(i - ti), abs(j - tj))
                    heapq.heappush(heap, (ng + h, k2))
    return [np.int64(-1)][:0]


def search_flat(base, selfc, px, py, pot, void, via_ok, src, dst, res, via_cost=1.0, lam=1.0, floor=0.05, target=None):
    """As `search` with flat cell indices: src (int array), dst (bool array over all cells); returns a
    flat index array (empty: no route)."""
    nl, ny, nx = base.shape
    if target is None:
        k = np.nonzero(dst)[0] % (ny * nx)
        target = (int(np.mean(k // nx)), int(np.mean(k % nx)))
    tj, ti = target
    per = base + lam * selfc - lam * (np.abs(px) + np.abs(py))
    fin = np.isfinite(per)
    hmin = max(float(np.min(per[fin])) if fin.any() else floor, floor)
    hmin = min(hmin, 1.0)
    path = _astar(base.ravel().astype(float), selfc.ravel().astype(float), px.ravel().astype(float),
                  py.ravel().astype(float), pot.ravel().astype(float), void.ravel().astype(np.bool_),
                  via_ok.ravel().astype(np.bool_), np.asarray(src, np.int64), np.asarray(dst, np.bool_), nl, ny, nx,
                  float(res), float(via_cost), float(lam), float(floor), hmin, ti, tj)
    return np.array(path, np.int64)


def search(base, selfc, px, py, via_ok, src, dst, res, via_cost=1.0, lam=1.0, floor=0.05, pot=None, void=None):
    """Path (list of (layer, j, i)) from any src cell to any dst cell (lists of (layer, j, i)).
    Arrays are (layers, ny, nx); via_ok (ny, nx) bool."""
    nl, ny, nx = base.shape
    pot = np.zeros_like(base) if pot is None else pot
    void = np.zeros(base.shape, bool) if void is None else void
    flat = lambda c: (c[0] * ny + c[1]) * nx + c[2]
    s = np.array([flat(c) for c in src], np.int64)
    d = np.zeros(nl * ny * nx, np.bool_)
    for c in dst:
        d[flat(c)] = True
    tj = int(np.mean([c[1] for c in dst]))
    ti = int(np.mean([c[2] for c in dst]))
    per = base + lam * selfc - lam * (np.abs(px) + np.abs(py))
    hmin = max(float(np.min(per[np.isfinite(per)])) if np.isfinite(per).any() else floor, floor)
    hmin = min(hmin, 1.0)
    path = _astar(base.ravel().astype(float), selfc.ravel().astype(float), px.ravel().astype(float),
                  py.ravel().astype(float), pot.ravel().astype(float), void.ravel().astype(np.bool_),
                  via_ok.ravel().astype(np.bool_), s, d, nl, ny, nx, float(res),
                  float(via_cost), float(lam), float(floor), hmin, ti, tj)
    out = []
    for k in path:
        l, r = divmod(int(k), ny * nx)
        j, i = divmod(r, nx)
        out.append((l, j, i))
    return out
