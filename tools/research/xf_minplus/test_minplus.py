# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Checks of the min-plus distance fields.

    python test_minplus.py                 hand-made grids (exact Dijkstra values)
    python test_minplus.py BOARD_ID ...    real board after a few jc iterations: every field
                                           is >= 0; for 2-pin nets the field from one pin
                                           read at the other pin vs the net's priced routed
                                           cost (the coarse min-pooled field is a lower
                                           bound up to pad-copper and rounding slack)
"""
import math
import random
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import minplus as MPm  # noqa: E402


def dj(costT, costV, src):
    nl, H, W = costT.shape
    n = nl * H * W
    D = np.empty_like(costT)
    MPm.dijkstra(costT, costV, np.array(src, np.int64), D, np.zeros(8 * n + 64), np.zeros(8 * n + 64, np.int64))
    return D


def hand():
    # uniform 1 layer: distance = octile distance
    c = np.ones((1, 7, 9))
    D = dj(c, np.full((7, 9), np.inf), [[0, 3, 4]])
    for y in range(7):
        for x in range(9):
            dx, dy = abs(x - 4), abs(y - 3)
            exp = max(dx, dy) + (math.sqrt(2) - 1) * min(dx, dy)
            assert abs(D[0, y, x] - exp) < 1e-9, (y, x, D[0, y, x], exp)
    # wall with a gap; cost of entering cell counted
    c = np.ones((1, 5, 5))
    c[0, :, 2] = np.inf
    c[0, 4, 2] = 3.0
    D = dj(c, np.full((5, 5), np.inf), [[0, 0, 0]])
    assert np.isinf(D[0, 0, 2]) and abs(D[0, 4, 2] - (3 + 3 * math.sqrt(2) + 0)) > -1
    # path (0,0)->(4,2): must go through (4,2) at cost 3; best = diag to (3,1)? compare to brute force
    D2 = brute(c, np.full((5, 5), np.inf), [(0, 0, 0)])
    assert np.allclose(np.nan_to_num(D, posinf=1e9), np.nan_to_num(D2, posinf=1e9)), (D, D2)
    # two layers, via cost 5, layer 0 blocked in the middle
    c = np.ones((2, 3, 7))
    c[0, :, 3] = np.inf
    v = np.full((3, 7), 5.0)
    D = dj(c, v, [[0, 1, 0]])
    D2 = brute(c, v, [(0, 1, 0)])
    assert np.allclose(np.nan_to_num(D, posinf=1e9), np.nan_to_num(D2, posinf=1e9))
    # random grids vs brute force
    rng = np.random.default_rng(1)
    for _ in range(30):
        nl, H, W = rng.integers(1, 3), rng.integers(2, 9), rng.integers(2, 9)
        c = rng.uniform(0.5, 4, (nl, H, W))
        c[rng.random((nl, H, W)) < 0.2] = np.inf
        v = rng.uniform(1, 6, (H, W))
        v[rng.random((H, W)) < 0.3] = np.inf
        src = [(int(rng.integers(nl)), int(rng.integers(H)), int(rng.integers(W))) for _ in range(rng.integers(1, 4))]
        D = dj(c, v, [list(s) for s in src])
        D2 = brute(c, v, src)
        assert (D >= 0).all()
        assert np.allclose(np.nan_to_num(D, posinf=1e9), np.nan_to_num(D2, posinf=1e9)), (D, D2)
    print("hand-made grids: OK (exact vs Bellman-Ford, 33 grids)")


def brute(c, v, src):
    nl, H, W = c.shape
    D = np.full(c.shape, np.inf)
    for s in src:
        D[s] = 0.0
    nb = [(1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)]
    for _ in range(nl * H * W + 2):
        ch = False
        for l in range(nl):
            for y in range(H):
                for x in range(W):
                    d = D[l, y, x]
                    if not np.isfinite(d):
                        continue
                    for dx, dy in nb:
                        nx, ny = x + dx, y + dy
                        if 0 <= nx < W and 0 <= ny < H and np.isfinite(c[l, ny, nx]):
                            nd = d + (1 if dx == 0 or dy == 0 else math.sqrt(2)) * c[l, ny, nx]
                            if nd < D[l, ny, nx] - 1e-12:
                                D[l, ny, nx] = nd
                                ch = True
                    if np.isfinite(v[y, x]):
                        for ll in range(nl):
                            if ll != l and d + v[y, x] < D[ll, y, x] - 1e-12:
                                D[ll, y, x] = d + v[y, x]
                                ch = True
        if not ch:
            break
    return D


def board(bid):
    import validate as V
    from world import World
    data = V.load(bid, V.ROOT / "kae-work" / "xf_minplus" / "extract")
    w = World(data, g=0.1)
    C = MPm.MPCollapse(w, 0, 1e9, lambda s: None, phys_w=0.0, minplus_w=0.0)
    mov = [q for q in C.kit.movable() if q not in w.pose]
    C.lift(mov)
    mov = [q for q in C.kit.movable() if q in w.pose]
    beta = 0.05
    rng = random.Random(0)
    for it in range(int(__import__("os").environ.get("MP_ITERS", "10"))):
        C.route_all(beta)
        CT, CV, per = C.route_maps()
        for pi in mov:
            C.best_response(pi, beta, CT, CV, per)
        beta *= 1.6
    C.route_all(beta)
    r, kit, f = C.r, C.kit, C.mp.f
    neg = 0
    mins = []
    ratios = []
    own_vals = []
    for pi in rng.sample(mov, min(25, len(mov))):
        nets = sorted(kit.part_nets([pi]))
        cur = w.pose[pi]
        # read the field at the part's own pads (as the map does), before unplacing
        rr = w.raster(pi)
        padcells = {}
        for k, ent in enumerate(rr["pads"]):
            if ent["net"] in nets:
                padcells.setdefault(ent["net"], []).append(np.array(w.terminals(pi, k)).reshape(-1, 3))
        two = [n for n in nets if len(w.net_pins[n]) == 2 and r.routes.get(n) and not r.unrouted.get(n)]
        pc = {n: V.priced(w, r, [n], beta, kit) for n in two}
        snap = kit.snapshot(nets)
        for n in nets:
            r.rip(n)
        w.unplace(pi)
        C.mp.prepare(beta)
        for n in nets:
            cT, cV = C.mp.net_costs(n)
            if (cT < 0).any() or (cV < 0).any():
                print(f"  NEGATIVE COST net {n}: cT min {cT.min():.3g} cV min {cV.min():.3g}")
            D = C.mp.field(n, pi)
            if D is None:
                continue
            mins.append(D.min())
            neg += int((D < 0).any())
            for t in padcells.get(n, []):
                v = D[t[:, 0], t[:, 1] // f, t[:, 2] // f].min()
                own_vals.append(v)
                if n in two:
                    ratios.append(v / max(pc[n], 1e-9))
        w.place(pi, *cur)
        kit.restore(snap)
    print(f"{bid}: beta={beta:.3g} fields with negatives: {neg}; min field {min(mins):.3g}; "
          f"min at own pads {min(own_vals):.3g}")
    if ratios:
        ra = np.array(ratios)
        print(f"  2-pin nets: field at other pin / priced routed cost: n={len(ra)} median {np.median(ra):.3f} "
              f"p10 {np.percentile(ra, 10):.3f} p90 {np.percentile(ra, 90):.3f} max {ra.max():.3f}")


if __name__ == "__main__":
    if len(sys.argv) == 1:
        hand()
    for b in sys.argv[1:]:
        board(b)
