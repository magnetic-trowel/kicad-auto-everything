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
floored at `floor` times its length so the search stays well-posed, and the heuristic, the smallest
per-length cost any cell offers (only `floor` where void crossings can be gains) times the distance to
the destination cells' bounding box, less the largest target-plane credit, stays admissible.
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
def _astar(base, selfc, px, py, pot, void, pot2, void2, theta, th_src, th_dst, vself, cx, cy, via_ok, src, dst, nl, ny,
           nx, res, via_cost, lam, floor, hmin, hoff, ti0, ti1, tj0, tj1):
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
            g[k] = lam * th_src[k]                    # the return leaves its terminal's plane here
            heapq.heappush(heap, (g[k], k))
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
            if void2[k] or void2[k2]:
                c += lam * (pot2[k2] - pot2[k])        # the same for the return plane on the other side
            # cutting a return pour on this layer: per step across the current it interrupts
            c += 0.5 * (cx[k] + cx[k2]) * abs(di[m]) + 0.5 * (cy[k] + cy[k2]) * abs(dj[m])
            if c < floor * ln:
                c = floor * ln
            ng = g[k] + c
            if dst[k2]:
                ng -= lam * th_dst[k2]                # and joins the target terminal's plane
            if ng < g[k2]:
                g[k2] = ng
                par[k2] = k
                h = hmin * res * max(0, ti0 - i2, i2 - ti1, tj0 - j2, j2 - tj1) - hoff
                heapq.heappush(heap, (ng + h, k2))
        if via_ok[r]:
            for l2 in range(nl):
                if l2 == l:
                    continue
                k2 = l2 * plane + r
                if base[k2] == np.inf or done[k2]:
                    continue
                # the return changes planes at the via: the hop's own detour to the nearest return
                # transfer (vself, never below zero) plus the coupling of that transfer (theta); the
                # coupling may lower the cost but never below the plain via cost
                tr = lam * (theta[k2] - theta[k])
                if tr < 0.0:
                    tr = 0.0 if -tr > vself[r] else tr
                ng = g[k] + via_cost + vself[r] + tr
                if dst[k2]:
                    ng -= lam * th_dst[k2]
                if ng < g[k2]:
                    g[k2] = ng
                    par[k2] = k
                    h = hmin * res * max(0, ti0 - i, i - ti1, tj0 - j, j - tj1) - hoff
                    heapq.heappush(heap, (ng + h, k2))
    return [np.int64(-1)][:0]


def _heuristic(base, selfc, px, py, lam, floor, voids, th_dst, dst):
    """(hmin, hoff): A*'s admissible per-length lower bound and the largest credit for joining the
    target terminal's plane. The crossing terms over a void (pot steps) can be gains, so with a
    void the bound is the move floor alone."""
    per = base + lam * selfc - lam * (np.abs(px) + np.abs(py))
    fin = np.isfinite(per)
    hmin = max(float(np.min(per[fin])) if fin.any() else floor, floor)
    hmin = min(hmin, 1.0)
    if any(v is not None and np.any(v) for v in voids):
        hmin = floor
    hoff = max(0.0, float(lam * np.max(th_dst[dst]))) if th_dst is not None and dst.any() else 0.0
    return hmin, hoff


def _box(dst, ny, nx):
    """(i0, i1, j0, j1): the destination cells' bounding box (the heuristic's target; a mean point
    overestimates when the destinations are spread out)."""
    k = np.nonzero(dst)[0] % (ny * nx)
    if not k.size:
        return 0, -1, 0, -1
    j, i = k // nx, k % nx
    return int(i.min()), int(i.max()), int(j.min()), int(j.max())


def search_flat(base, selfc, px, py, pot, void, via_ok, src, dst, res, via_cost=1.0, lam=1.0, floor=0.05,
                pot2=None, void2=None, theta=None, th_src=None, th_dst=None, vself=None, cx=None, cy=None):
    """As `search` with flat cell indices: src (int array), dst (bool array over all cells); returns a
    flat index array (empty: no route)."""
    nl, ny, nx = base.shape
    dst = np.asarray(dst, np.bool_)
    ti0, ti1, tj0, tj1 = _box(dst, ny, nx)
    pot2 = np.zeros_like(pot) if pot2 is None else pot2
    void2 = np.zeros(pot.shape, bool) if void2 is None else void2
    theta = np.zeros_like(pot) if theta is None else theta
    th_src = theta if th_src is None else th_src
    th_dst = theta if th_dst is None else th_dst
    hmin, hoff = _heuristic(base, selfc, px, py, lam, floor, (void, void2), np.asarray(th_dst, float).ravel(), dst)
    vself = np.zeros(ny * nx) if vself is None else np.asarray(vself, float).ravel()
    cx = np.zeros(pot.size) if cx is None else np.asarray(cx, float).ravel()
    cy = np.zeros(pot.size) if cy is None else np.asarray(cy, float).ravel()
    path = _astar(base.ravel().astype(float), selfc.ravel().astype(float), px.ravel().astype(float),
                  py.ravel().astype(float), pot.ravel().astype(float), void.ravel().astype(np.bool_),
                  pot2.ravel().astype(float), void2.ravel().astype(np.bool_), theta.ravel().astype(float),
                  th_src.ravel().astype(float), th_dst.ravel().astype(float), vself, cx, cy,
                  via_ok.ravel().astype(np.bool_), np.asarray(src, np.int64), dst, nl, ny, nx,
                  float(res), float(via_cost), float(lam), float(floor), hmin, hoff, ti0, ti1, tj0, tj1)
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
    ti0, ti1, tj0, tj1 = _box(d, ny, nx)
    z0 = np.zeros(base.size)
    hmin, _ = _heuristic(base, selfc, px, py, lam, floor, (void,), None, d)
    path = _astar(base.ravel().astype(float), selfc.ravel().astype(float), px.ravel().astype(float),
                  py.ravel().astype(float), pot.ravel().astype(float), void.ravel().astype(np.bool_),
                  z0, z0.astype(np.bool_), z0, z0, z0, np.zeros(ny * nx), z0, z0, via_ok.ravel().astype(np.bool_), s, d, nl,
                  ny, nx,
                  float(res),
                  float(via_cost), float(lam), float(floor), hmin, 0.0, ti0, ti1, tj0, tj1)
    out = []
    for k in path:
        l, r = divmod(int(k), ny * nx)
        j, i = divmod(r, nx)
        out.append((l, j, i))
    return out
