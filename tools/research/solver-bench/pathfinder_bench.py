# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Negotiated-congestion (PathFinder) grid router prototype: SciPy Dijkstra vs pure-Python heapq A*.

Board: W x H mm, pitch p mm, L layers (node = track position; capacity 1).  Random pad obstacles,
2-pin nets with locality.  Edge weight u->v = base(v) * (1 + pres_fac*over(v)) + hist(v)  (VPR-style:
first_iter_pres_fac=0, initial 0.5, x1.3 per iteration, acc_fac=1). Via edge cost = VIA.
Reports per-iteration overflow, total time, wirelength, vias.
Usage: python pathfinder_bench.py NETS [--w 60 --h 40 --pitch 0.25 --layers 2 --engine scipy|python]
"""
import argparse
import heapq
import json
import math
import random
import time

import numpy as np
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra


def build_grid(nx, ny, L, via_cost):
    N = nx * ny * L
    idx = lambda x, y, l: (l * ny + y) * nx + x
    rows, cols, base = [], [], []
    for l in range(L):
        for y in range(ny):
            for x in range(nx):
                u = idx(x, y, l)
                if x + 1 < nx: rows += [u, idx(x + 1, y, l)]; cols += [idx(x + 1, y, l), u]; base += [1.0, 1.0]
                if y + 1 < ny: rows += [u, idx(x, y + 1, l)]; cols += [idx(x, y + 1, l), u]; base += [1.0, 1.0]
                if l + 1 < L: rows += [u, idx(x, y, l + 1)]; cols += [idx(x, y, l + 1), u]; base += [via_cost, via_cost]
    return N, idx, np.array(rows), np.array(cols), np.array(base)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("nets", type=int); ap.add_argument("--w", type=float, default=60); ap.add_argument("--h", type=float, default=40)
    ap.add_argument("--pitch", type=float, default=0.25); ap.add_argument("--layers", type=int, default=2)
    ap.add_argument("--engine", default="scipy"); ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--iters", type=int, default=50); ap.add_argument("--via", type=float, default=8.0)
    a = ap.parse_args()
    rnd = random.Random(a.seed)
    nx, ny, L = int(a.w / a.pitch), int(a.h / a.pitch), a.layers
    t0 = time.time()
    N, idx, R, C, B = build_grid(nx, ny, L, a.via)
    order = np.lexsort((C, R)); R, C, B = R[order], C[order], B[order]
    t_build = time.time() - t0
    # obstacles: random "pads" (blocked on all layers for SMD-on-top simplification: block top layer only)
    blocked = np.zeros(N, dtype=bool)
    pins = []
    used_xy = set()

    def free_xy(x, y):   # pins unique and at least 2 grid cells apart (no shared / abutting pin nodes)
        return all((x + ddx, y + ddy) not in used_xy for ddx in range(-2, 3) for ddy in range(-2, 3))
    while len(pins) < a.nets:
        cx, cy = rnd.randrange(4, nx - 4), rnd.randrange(4, ny - 4)
        dx, dy = rnd.randint(-nx // 4, nx // 4), rnd.randint(-ny // 4, ny // 4)
        tx, ty = min(max(cx + dx, 4), nx - 5), min(max(cy + dy, 4), ny - 5)
        if (cx, cy) == (tx, ty) or not free_xy(cx, cy) or not free_xy(tx, ty):
            continue
        used_xy.add((cx, cy)); used_xy.add((tx, ty))
        pins.append((idx(cx, cy, 0), idx(tx, ty, 0)))
    pin_nodes = {p for pr in pins for p in pr}
    for _ in range(a.nets * 3):   # extra pad keep-out blobs (2x3 nodes) on top layer
        x, y = rnd.randrange(1, nx - 3), rnd.randrange(1, ny - 4)
        for xx in range(x, x + 2):
            for yy in range(y, y + 3):
                n = idx(xx, yy, 0)
                if n not in pin_nodes and all((xx + ddx, yy + ddy) not in used_xy for ddx in (-1, 0, 1) for ddy in (-1, 0, 1)):
                    blocked[n] = True
    occ = np.zeros(N, dtype=np.int32); hist = np.zeros(N); routes = [None] * a.nets
    pres_fac = 0.0
    log = []
    t_route = time.time()
    for it in range(a.iters):
        for ni, (s, t) in enumerate(pins):
            if routes[ni] is not None:
                if it > 0 and not (occ[routes[ni]] > 1).any():
                    continue
                occ[routes[ni]] -= 1
            over = np.maximum(0, occ + 1 - 1)
            node_cost = (1.0 + hist) * (1.0 + pres_fac * over)
            node_cost[blocked] = 1e9
            w = B * node_cost[C]
            if a.engine == "scipy":
                G = csr_matrix((w, (R, C)), shape=(N, N))
                dist, pred = dijkstra(G, directed=True, indices=s, return_predecessors=True, min_only=False, limit=np.inf)
                path = [t]
                while path[-1] != s:
                    path.append(pred[path[-1]])
            else:  # pure python A* on the same weights
                indptr = np.searchsorted(R, np.arange(N + 1))
                tx, ty = t % nx, (t // nx) % ny
                h = lambda v: abs(v % nx - tx) + abs((v // nx) % ny - ty)
                g = {s: 0.0}; prev = {}; pq = [(h(s), s)]; done = set()
                while pq:
                    f, u = heapq.heappop(pq)
                    if u == t: break
                    if u in done: continue
                    done.add(u)
                    for e in range(indptr[u], indptr[u + 1]):
                        v = C[e]; nd = g[u] + w[e]
                        if nd < g.get(v, 1e18):
                            g[v] = nd; prev[v] = u; heapq.heappush(pq, (nd + h(v), v))
                path = [t]
                while path[-1] != s:
                    path.append(prev[path[-1]])
            routes[ni] = np.array(path)
            occ[routes[ni]] += 1
        overused = int((occ > 1).sum())
        log.append((it, overused, round(time.time() - t_route, 2)))
        if overused == 0:
            break
        hist += 1.0 * np.maximum(0, occ - 1)        # acc_fac = 1
        pres_fac = 0.5 if it == 0 else pres_fac * 1.3
    over_pins = int(sum(1 for v in np.nonzero(occ > 1)[0] if v in pin_nodes))
    wl = sum(len(r) for r in routes) * a.pitch
    vias = sum(int((np.diff(r // (nx * ny)) != 0).sum()) for r in routes)
    print(json.dumps(dict(engine=a.engine, nets=a.nets, grid=[nx, ny, L], nodes=N, edges=len(R), build_s=round(t_build, 2),
                          route_s=round(time.time() - t_route, 2), iterations=len(log), converged=log[-1][1] == 0,
                          wirelength_mm=round(wl, 1), vias=vias, overused_pin_nodes=over_pins, overuse_trace=log[:6] + log[-2:])), flush=True)


if __name__ == "__main__":
    main()
