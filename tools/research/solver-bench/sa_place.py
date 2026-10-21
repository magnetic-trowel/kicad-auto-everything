# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Plain simulated-annealing placer (pure Python + NumPy) as a baseline for the CP-SAT runs.

Same instances / grid / rotation model / decap constraint as cpsat_place.py. Penalty method:
cost = HPWL + lam(t) * (overlap_area + keepout_area + out_of_board_area + decap_excess)
with lam ramping up over time, geometric cooling, moves = shift (radius shrinks), rotate, swap.
Usage: python sa_place.py N GRID_MM TIME_S [--seed 0]
Prints JSON: final HPWL (mm, exact), legality check (overlaps, decap violations, out-of-board), moves/s.
"""
import argparse
import json
import math
import random
import time

import numpy as np

from pcbgen import make_instance
from cpsat_place import rot_offsets
from hier_place import full_hpwl, check, lns_polish, legalize, legalize_windowed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("n", type=int); ap.add_argument("grid", type=float); ap.add_argument("time", type=float)
    ap.add_argument("--seed", type=int, default=0); ap.add_argument("--util", type=float, default=0.45)
    ap.add_argument("--polish-time", type=float, default=0); ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--windowed", action="store_true"); ap.add_argument("--dump", default="")
    a = ap.parse_args()
    g = a.grid
    rnd = random.Random(a.seed)
    inst = make_instance(a.n, seed=a.seed, util=a.util)
    N = a.n
    BW, BH = math.floor(inst.board_w / g), math.floor(inst.board_h / g)
    dims = [[rot_offsets(c.fp, k, g) for k in range(4)] for c in inst.comps]
    KO = [(math.floor(kx / g), math.floor(ky / g), math.ceil((kx + kw) / g), math.ceil((ky + kh) / g)) for (kx, ky, kw, kh) in inst.keepouts]
    nets_of = [[] for _ in range(N)]
    for ni, net in enumerate(inst.nets):
        for (c, p) in net:
            if ni not in nets_of[c]:
                nets_of[c].append(ni)
    dec_of = [[] for _ in range(N)]
    for di, d in enumerate(inst.decaps):
        dec_of[d[0]].append(di); dec_of[d[2]].append(di)

    X = np.array([rnd.randrange(0, BW - 1) for _ in range(N)]); Y = np.array([rnd.randrange(0, BH - 1) for _ in range(N)])
    K = np.zeros(N, dtype=int)
    Wd = np.array([dims[i][0][0] for i in range(N)]); Hd = np.array([dims[i][0][1] for i in range(N)])

    def pin(c, p):
        o = dims[c][K[c]][2][p]; return X[c] + o[0], Y[c] + o[1]

    def net_hp(ni):
        xs, ys = zip(*(pin(c, p) for (c, p) in inst.nets[ni]))
        return max(xs) - min(xs) + max(ys) - min(ys)

    def dec_ex(di):
        cc, cp, ic, ip, dmax = inst.decaps[di]
        (ax, ay), (bx, by) = pin(cc, cp), pin(ic, ip)
        return max(0, abs(ax - bx) + abs(ay - by) - math.floor(dmax / g))

    def ov_one(i):
        x0, y0, x1, y1 = X[i], Y[i], X[i] + Wd[i], Y[i] + Hd[i]
        ox = np.clip(np.minimum(x1, X + Wd) - np.maximum(x0, X), 0, None)
        oy = np.clip(np.minimum(y1, Y + Hd) - np.maximum(y0, Y), 0, None)
        a_ = ox * oy; a_[i] = 0
        s = float(a_.sum())
        for (kx0, ky0, kx1, ky1) in KO:
            s += max(0, min(x1, kx1) - max(x0, kx0)) * max(0, min(y1, ky1) - max(y0, ky0))
        s += max(0, x1 - BW) * (y1 - y0) + max(0, y1 - BH) * (x1 - x0) + max(0, -x0) * (y1 - y0) + max(0, -y0) * (x1 - x0)
        return s

    def local(ids):
        nets = set(); decs = set()
        for i in ids:
            nets.update(nets_of[i]); decs.update(dec_of[i])
        hp = sum(net_hp(n) for n in nets)
        pen = sum(ov_one(i) for i in ids) + 3.0 * sum(dec_ex(d) for d in decs)
        if len(ids) == 2:  # pair overlap counted twice
            i, j = ids
            ox = max(0, min(X[i] + Wd[i], X[j] + Wd[j]) - max(X[i], X[j])); oy = max(0, min(Y[i] + Hd[i], Y[j] + Hd[j]) - max(Y[i], Y[j]))
            pen -= ox * oy
        return hp, pen

    t0 = time.time(); T_end = t0 + a.time
    T0, T1 = BW * 0.5, 0.05
    moves = 0; acc = 0
    lam = 0.5
    while True:
        now = time.time()
        if now >= T_end:
            break
        frac = (now - t0) / a.time
        T = T0 * (T1 / T0) ** frac
        lam = 0.5 * (200.0 / 0.5) ** frac
        rad = max(1, int(BW * 0.3 * (1 - frac) ** 2))
        for _ in range(200):
            moves += 1
            r = rnd.random()
            if r < 0.7:
                i = rnd.randrange(N); ids = (i,)
                hp0, p0 = local(ids)
                ox_, oy_ = X[i], Y[i]
                X[i] = min(max(0, X[i] + rnd.randint(-rad, rad)), BW - 1); Y[i] = min(max(0, Y[i] + rnd.randint(-rad, rad)), BH - 1)
                undo = lambda: (X.__setitem__(i, ox_), Y.__setitem__(i, oy_))
            elif r < 0.85:
                i = rnd.randrange(N); ids = (i,)
                hp0, p0 = local(ids)
                ok_ = K[i]
                K[i] = rnd.randrange(4); Wd[i] = dims[i][K[i]][0]; Hd[i] = dims[i][K[i]][1]
                undo = lambda: (K.__setitem__(i, ok_), Wd.__setitem__(i, dims[i][ok_][0]), Hd.__setitem__(i, dims[i][ok_][1]))
            else:
                i = rnd.randrange(N); j = rnd.randrange(N)
                if i == j:
                    continue
                ids = (i, j)
                hp0, p0 = local(ids)
                xi, yi, xj, yj = X[i], Y[i], X[j], Y[j]
                X[i], Y[i], X[j], Y[j] = xj, yj, xi, yi
                undo = lambda: (X.__setitem__(i, xi), Y.__setitem__(i, yi), X.__setitem__(j, xj), Y.__setitem__(j, yj))
            hp1, p1 = local(ids)
            d = (hp1 - hp0) + lam * (p1 - p0)
            if d <= 0 or rnd.random() < math.exp(-d / T):
                acc += 1
            else:
                undo()
    pos = {i: (int(X[i]), int(Y[i]), int(K[i])) for i in range(N)}
    if a.dump:
        json.dump({str(k): v for k, v in pos.items()}, open(a.dump, "w"))
    print(json.dumps(dict(n=N, grid_mm=g, method="SA", time_s=a.time, moves=moves, moves_per_s=round(moves / a.time),
                          hpwl_mm=round(full_hpwl(inst, pos, g), 1), check=check(inst, pos, g))), flush=True)
    if a.windowed and check(inst, pos, g) != (0, 0, 0, 0):
        lp, rounds, lsec, ok = legalize_windowed(inst, g, pos, workers=a.workers, seed=a.seed)
        print(json.dumps(dict(n=N, grid_mm=g, method="SA+CP-SAT-windowed-legalize", rounds=rounds, legalize_s=lsec, legal=ok,
                              hpwl_mm=round(full_hpwl(inst, lp, g), 1), check=check(inst, lp, g))), flush=True)
        pos = lp
    if a.polish_time > 0 and check(inst, pos, g) != (0, 0, 0, 0):
        lp, lst, lsec = legalize(inst, g, pos, max(10.0, a.polish_time / 2), workers=a.workers, seed=a.seed)
        print(json.dumps(dict(n=N, grid_mm=g, method="SA+CP-SAT-legalize", status=lst, legalize_s=lsec,
                              hpwl_mm=round(full_hpwl(inst, lp, g), 1) if lp else None,
                              check=check(inst, lp, g) if lp else None)), flush=True)
        if lp:
            pos = lp
    if a.polish_time > 0 and check(inst, pos, g) == (0, 0, 0, 0):
        t1 = time.time()
        best, hp, it, acc = lns_polish(inst, g, pos, a.polish_time, window=min(40, N), iter_time=2.0, workers=a.workers, seed=a.seed)
        print(json.dumps(dict(n=N, grid_mm=g, method="SA+CP-SAT-LNS", polish_s=round(time.time() - t1, 1), iters=it, accepted=acc,
                              hpwl_mm=round(hp, 1), check=check(inst, best, g))), flush=True)


if __name__ == "__main__":
    main()
