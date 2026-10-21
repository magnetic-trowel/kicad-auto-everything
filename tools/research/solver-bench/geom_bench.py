# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Incremental overlap/clearance-check micro-benchmark (the inner loop of SA / LNS placement).

Scenario: N courtyard rectangles on a board; repeatedly move ONE component to a random nearby
position and ask "does it violate clearance (0.2 mm) with any other component?".
Methods:
  numpy_aabb   : vectorised AABB test of moved box vs all N (O(N) but in C)
  grid_hash    : pure-Python uniform grid (cell = 2 mm), incremental remove/insert
  rtree        : libspatialindex R-tree, delete + insert + intersection per move
  strtree_q    : shapely STRtree built once; per move query(box, 'dwithin', 0.2); stale entry for the
                 moved item is skipped by index (valid when trees are rebuilt every K accepted moves)
  strtree_rb   : rebuild a fresh STRtree every move (what immutability forces if you don't batch)
  shapely_poly : exact polygon dwithin test (octagon courtyards) on candidates from STRtree
Also: one-shot full all-pairs check with STRtree.query(all, 'dwithin') and pyclipper offset time.
Prints JSON lines.
"""
import json
import random
import sys
import time

import numpy as np
import shapely
from shapely import box
from rtree import index as rindex

from pcbgen import make_instance

CLR = 0.2


def layout(n, seed=0):
    inst = make_instance(n, seed=seed, util=0.45)
    rnd = random.Random(seed)
    W, H = inst.board_w, inst.board_h
    rects = []
    for c in inst.comps:
        w, h = (c.fp.w, c.fp.h) if rnd.random() < 0.5 else (c.fp.h, c.fp.w)
        x = rnd.uniform(0, W - w); y = rnd.uniform(0, H - h)
        rects.append([x, y, x + w, y + h])
    return np.array(rects), W, H


def moves(n, W, H, m, seed=1):
    rnd = random.Random(seed)
    return [(rnd.randrange(n), rnd.uniform(-3, 3), rnd.uniform(-3, 3)) for _ in range(m)]


def bench(n, m=5000):
    R, W, H = layout(n)
    mv = moves(n, W, H, m)
    out = dict(n=n, moves=m)

    # numpy
    A = R.copy()
    t = time.perf_counter(); hits = 0
    for (i, dx, dy) in mv:
        b = A[i] + (dx, dy, dx, dy)
        ov = (A[:, 0] < b[2] + CLR) & (b[0] < A[:, 2] + CLR) & (A[:, 1] < b[3] + CLR) & (b[1] < A[:, 3] + CLR)
        ov[i] = False
        hits += int(ov.any())
        A[i] = b
    out["numpy_aabb_us"] = round((time.perf_counter() - t) / m * 1e6, 1)

    # grid hash
    C = 2.0
    A = R.copy()
    cells = {}

    def cells_of(b):
        return [(cx, cy) for cx in range(int((b[0] - CLR) // C), int((b[2] + CLR) // C) + 1)
                for cy in range(int((b[1] - CLR) // C), int((b[3] + CLR) // C) + 1)]
    for i, b in enumerate(A):
        for k in cells_of(b):
            cells.setdefault(k, set()).add(i)
    t = time.perf_counter()
    for (i, dx, dy) in mv:
        old = A[i].copy(); b = old + (dx, dy, dx, dy)
        cand = set()
        for k in cells_of(b):
            cand |= cells.get(k, set())
        cand.discard(i)
        bad = any(A[j, 0] < b[2] + CLR and b[0] < A[j, 2] + CLR and A[j, 1] < b[3] + CLR and b[1] < A[j, 3] + CLR for j in cand)
        for k in cells_of(old):
            cells[k].discard(i)
        for k in cells_of(b):
            cells.setdefault(k, set()).add(i)
        A[i] = b
    out["grid_hash_us"] = round((time.perf_counter() - t) / m * 1e6, 1)

    # rtree
    A = R.copy()
    p = rindex.Property(); p.dimension = 2
    idx = rindex.Index(((i, tuple(b), None) for i, b in enumerate(A)), properties=p)
    t = time.perf_counter()
    for (i, dx, dy) in mv:
        old = A[i].copy(); b = old + (dx, dy, dx, dy)
        q = (b[0] - CLR, b[1] - CLR, b[2] + CLR, b[3] + CLR)
        bad = any(j != i for j in idx.intersection(q))
        idx.delete(i, tuple(old)); idx.insert(i, tuple(b))
        A[i] = b
    out["rtree_us"] = round((time.perf_counter() - t) / m * 1e6, 1)

    # STRtree static query
    geoms = shapely.box(R[:, 0], R[:, 1], R[:, 2], R[:, 3])
    t = time.perf_counter(); tree = shapely.STRtree(geoms); out["strtree_build_ms"] = round((time.perf_counter() - t) * 1e3, 3)
    t = time.perf_counter()
    for (i, dx, dy) in mv:
        b = R[i] + (dx, dy, dx, dy)
        res = tree.query(box(*b), predicate="dwithin", distance=CLR)
        bad = bool((res != i).any())
    out["strtree_query_us"] = round((time.perf_counter() - t) / m * 1e6, 1)
    # rebuild-every-move (sample fewer moves)
    mm = min(m, 500)
    G = list(geoms)
    t = time.perf_counter()
    for (i, dx, dy) in mv[:mm]:
        b = R[i] + (dx, dy, dx, dy)
        G[i] = box(*b)
        tr = shapely.STRtree(G)
        res = tr.query(G[i], predicate="dwithin", distance=CLR)
    out["strtree_rebuild_us"] = round((time.perf_counter() - t) / mm * 1e6, 1)

    # exact polygons (octagonal courtyards ~ chamfered rects) with STRtree candidates
    def octo(b, c=0.25):
        x0, y0, x1, y1 = b
        return shapely.Polygon([(x0 + c, y0), (x1 - c, y0), (x1, y0 + c), (x1, y1 - c), (x1 - c, y1), (x0 + c, y1), (x0, y1 - c), (x0, y0 + c)])
    P = np.array([octo(b) for b in R], dtype=object)
    ptree = shapely.STRtree(P)
    shapely.prepare(P)
    t = time.perf_counter()
    for (i, dx, dy) in mv:
        g = shapely.transform(P[i], lambda xy: xy + (dx, dy))
        res = ptree.query(g, predicate="dwithin", distance=CLR)
        bad = bool((res != i).any())
    out["shapely_poly_us"] = round((time.perf_counter() - t) / m * 1e6, 1)

    # full all-pairs check (one shot)
    t = time.perf_counter()
    pairs = ptree.query(P, predicate="dwithin", distance=CLR)
    out["full_pairs_ms"] = round((time.perf_counter() - t) * 1e3, 2)
    out["violating_pairs"] = int((pairs[0] < pairs[1]).sum())

    # clearance offset of all polygons
    try:
        import pyclipper
        SC = 1e6
        t = time.perf_counter()
        for g in P:
            pco = pyclipper.PyclipperOffset(arc_tolerance=0.005 * SC)
            pco.AddPath([(int(x * SC), int(y * SC)) for x, y in list(g.exterior.coords)[:-1]], pyclipper.JT_ROUND, pyclipper.ET_CLOSEDPOLYGON)
            pco.Execute(CLR / 2 * SC)
        out["pyclipper_offset_us_per_poly"] = round((time.perf_counter() - t) / len(P) * 1e6, 1)
    except ImportError:
        pass
    t = time.perf_counter()
    shapely.buffer(P, CLR / 2, quad_segs=4)
    out["shapely_buffer_us_per_poly"] = round((time.perf_counter() - t) / len(P) * 1e6, 1)
    print(json.dumps(out), flush=True)


if __name__ == "__main__":
    for n in [int(a) for a in sys.argv[1:]] or [100, 300, 1000, 3000]:
        bench(n)
