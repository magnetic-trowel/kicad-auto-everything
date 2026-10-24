# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Numba kernels: polygon rasterization with dilation, disc offsets, stamping."""
import math

import numpy as np
from numba import njit


@njit(cache=True)
def _seg_dist2(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    L = dx * dx + dy * dy
    t = 0.0
    if L > 0:
        t = ((px - ax) * dx + (py - ay) * dy) / L
        t = min(1.0, max(0.0, t))
    qx, qy = ax + t * dx - px, ay + t * dy - py
    return qx * qx + qy * qy


@njit(cache=True)
def poly_dist(px, py, poly):
    """Distance from point to polygon (0 inside). poly: (n, 2) closed implicitly."""
    n = poly.shape[0]
    inside = False
    best = 1e30
    j = n - 1
    for i in range(n):
        xi, yi, xj, yj = poly[i, 0], poly[i, 1], poly[j, 0], poly[j, 1]
        if (yi > py) != (yj > py):
            xc = (xj - xi) * (py - yi) / (yj - yi) + xi
            if px < xc:
                inside = not inside
        d = _seg_dist2(px, py, xi, yi, xj, yj)
        if d < best:
            best = d
        j = i
    if inside:
        return 0.0
    return math.sqrt(best)


@njit(cache=True)
def raster_poly(poly, r, x0, y0, g):
    """Cells (ix, iy) whose centre lies within distance r of the polygon.
    Grid: cell (ix, iy) centre = (x0 + ix*g, y0 + iy*g). Returns (k, 2) int32."""
    minx, maxx = poly[:, 0].min() - r, poly[:, 0].max() + r
    miny, maxy = poly[:, 1].min() - r, poly[:, 1].max() + r
    ix0 = int(math.ceil((minx - x0) / g))
    ix1 = int(math.floor((maxx - x0) / g))
    iy0 = int(math.ceil((miny - y0) / g))
    iy1 = int(math.floor((maxy - y0) / g))
    out = np.empty((max(0, ix1 - ix0 + 1) * max(0, iy1 - iy0 + 1), 2), np.int32)
    k = 0
    for iy in range(iy0, iy1 + 1):
        for ix in range(ix0, ix1 + 1):
            if poly_dist(x0 + ix * g, y0 + iy * g, poly) <= r:
                out[k, 0] = ix
                out[k, 1] = iy
                k += 1
    return out[:k]


@njit(cache=True)
def nearest_cell(px, py, x0, y0, g):
    out = np.empty((1, 2), np.int32)
    out[0, 0] = int(round((px - x0) / g))
    out[0, 1] = int(round((py - y0) / g))
    return out


def disc(r, g):
    """Integer offsets (dx, dy) with |offset|*g <= r."""
    k = int(math.floor(r / g))
    ys, xs = np.mgrid[-k:k + 1, -k:k + 1]
    m = (xs * xs + ys * ys) * g * g <= r * r + 1e-12
    return np.stack([xs[m], ys[m]], axis=1).astype(np.int32)


@njit(cache=True)
def stamp(occ, D, net, layer, cells, ox, oy, delta):
    """Add delta to occ[net, layer] over cells shifted by (ox, oy); keep D = number of
    distinct nets with occ > 0 per cell. Out-of-grid cells are ignored."""
    H, W = D.shape[1], D.shape[2]
    for i in range(cells.shape[0]):
        x = cells[i, 0] + ox
        y = cells[i, 1] + oy
        if x < 0 or y < 0 or x >= W or y >= H:
            continue
        old = occ[net, layer, y, x]
        new = old + delta
        occ[net, layer, y, x] = new
        if old == 0 and new > 0:
            D[layer, y, x] += 1
        elif old > 0 and new == 0:
            D[layer, y, x] -= 1


@njit(cache=True)
def stamp_disc_path(occ, D, net, path, offs, delta, via_layers_all, nl):
    """Stamp a disc of offsets around every path cell (l, y, x). If via_layers_all,
    stamp every layer (used for vias)."""
    H, W = D.shape[1], D.shape[2]
    for i in range(path.shape[0]):
        l0, cy, cx = path[i, 0], path[i, 1], path[i, 2]
        la, lb = l0, l0 + 1
        if via_layers_all:
            la, lb = 0, nl
        for l in range(la, lb):
            for j in range(offs.shape[0]):
                x = cx + offs[j, 0]
                y = cy + offs[j, 1]
                if x < 0 or y < 0 or x >= W or y >= H:
                    continue
                old = occ[net, l, y, x]
                new = old + delta
                occ[net, l, y, x] = new
                if old == 0 and new > 0:
                    D[l, y, x] += 1
                elif old > 0 and new == 0:
                    D[l, y, x] -= 1


@njit(cache=True)
def count_add(arr, side, cells, ox, oy, delta):
    H, W = arr.shape[1], arr.shape[2]
    for i in range(cells.shape[0]):
        x = cells[i, 0] + ox
        y = cells[i, 1] + oy
        if x < 0 or y < 0 or x >= W or y >= H:
            continue
        arr[side, y, x] += delta


@njit(cache=True)
def edge_dist(px, py, poly, out_d, out_in):
    """For each point: min(out_d, distance to polygon boundary); toggle out_in if inside
    (even-odd over outline and holes)."""
    n = poly.shape[0]
    for k in range(px.shape[0]):
        best = 1e30
        ins = False
        j = n - 1
        for i in range(n):
            xi, yi, xj, yj = poly[i, 0], poly[i, 1], poly[j, 0], poly[j, 1]
            if (yi > py[k]) != (yj > py[k]):
                xc = (xj - xi) * (py[k] - yi) / (yj - yi) + xi
                if px[k] < xc:
                    ins = not ins
            d2 = _seg_dist2(px[k], py[k], xi, yi, xj, yj)
            if d2 < best:
                best = d2
            j = i
        d = math.sqrt(best)
        if d < out_d[k]:
            out_d[k] = d
        if ins:
            out_in[k] = not out_in[k]
