# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""How the exact evaluators' cost grows with the problem (docs/topics/physics/exact-physics-options.md).

Three sweeps, CPU seconds on one core:

  peec     a rectangular strip loop over a plane (ex_exact.peec_net/peec_solve) with the strip
           width swept so that the filament count n grows; fits t ~ n^p (dense Cholesky of the
           n x n partial-inductance matrix dominates: p -> 3) and the matrix memory 8 n^2 bytes;
  route    hops of growing length on a real board (ex_exact.Router, any-angle and Manhattan):
           time against the window's cell count;
  fv       the finite-volume thermal operator of ex_exact.FVThermal on one real board at grid
           pitches 1.0 to 0.25 mm: nodes, factorization time, LU fill, one solve; fits t ~ nodes^p.

Usage:  python tools/research/physics/ex_scaling.py [--board ID] [--json OUT]
"""
from __future__ import annotations

import argparse
import json
import math
import os
import random
import sys
import time
from pathlib import Path

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / 'kae' / 'src'))
sys.path.insert(0, str(HERE))

import numpy as np  # noqa: E402


def fit(xs, ys):
    p = np.polyfit(np.log(xs), np.log(ys), 1)
    return float(p[0])


def sweep_peec():
    """A meander hop of m strips (1 mm wide, 0.2 mm over the plane) closed by a part body:
    the filament count grows with m."""
    import ex_exact as X
    rows = []
    for m in (2, 4, 8, 16, 24, 32, 48):
        pts = [(0.0, 0.0)]
        for k in range(m):
            x, y = pts[-1]
            pts.append((x + 2.0, y) if k % 2 == 0 else (x, y + (3.0 if (k // 2) % 2 == 0 else -3.0)))
        g = X.LoopGeo(0.2)
        strips = [('strip', p, q, 1.0, 0.2) for p, q in zip(pts[:-1], pts[1:])]
        end = pts[-1]
        g.branches = [('N0', 'N1', 'A', strips, 'board'),
                      ('N1', 'N2', 'A', [('tie', end, 0.2, 0.6, 1.0), ('strip', end, (end[0], -4.0), 1.0, 0.6),
                                          ('tie', (end[0], -4.0), 0.6, 0.2, 1.0)], 'body'),
                      ('N2', 'N3', 'A', [('strip', (end[0], -4.0), (0.0, -4.0), 1.0, 0.2)], 'board'),
                      ('N3', 'NE', 'A', [('tie', (0.0, -4.0), 0.2, 0.6, 1.0), ('strip', (0.0, -4.0), (0.0, 0.0), 1.0, 0.6),
                                         ('tie', (0.0, 0.0), 0.6, 0.2, 1.0)], 'body')]
        reps = 5 if m <= 16 else 2
        c0 = time.process_time()
        for _ in range(reps):
            net, p, q = X.peec_net(g)
            L, I, n = X.peec_solve(net, p, q)
        t = (time.process_time() - c0) / reps
        c0 = time.process_time()
        for _ in range(reps):
            Lc = X.closed_form_L(g)
        tc = (time.process_time() - c0) / reps
        rows.append(dict(segments=m, filaments=n, t_peec=t, t_cf=tc, L_peec=L, L_cf=Lc, mb=8 * n * n / 2**20))
        print(f"peec: {m} segments: {n} filaments, {1e3 * t:.1f} ms ({8 * n * n / 2**20:.1f} MB), closed forms "
              f"{1e3 * tc:.2f} ms, cf/peec {Lc / L:.3f}", flush=True)
    big = [r for r in rows if r['filaments'] >= 150]
    return dict(rows=rows, exponent=fit([r['filaments'] for r in big], [r['t_peec'] for r in big]) if len(big) > 2 else None,
                exponent_cf=fit([r['segments'] for r in rows], [r['t_cf'] for r in rows]))


def sweep_route(board):
    import ex_exact as X
    from kae.board.kicad_file import load
    from kae.circuit.brief import build
    from kae.physics.place_terms import Terms
    b = load(str(ROOT / 'kae-work-v2' / 'tasks' / board / 'reference' / 'board.kicad_pcb'))
    T = Terms(b, build(b))
    R = X.Router(T, max_cells=10**7)
    R.refresh()
    bv = T.bv
    rng = random.Random(3)
    pads = [(p.i, k) for p in bv.parts for k in range(len(p.pad_num)) if p.pad_net[k]]
    rows = []
    for target in (2.0, 4.0, 8.0, 16.0, 32.0):
        n = 0
        tries = 0
        while n < 6 and tries < 4000:
            tries += 1
            i, k = rng.choice(pads)
            p = bv.parts[i]
            a = bv.pad_xy(i, k, p.x0, p.y0, p.rot0, p.side0)
            j, m = rng.choice(pads)
            q = bv.parts[j]
            bb = bv.pad_xy(j, m, q.x0, q.y0, q.rot0, q.side0)
            d = math.hypot(bb[0] - a[0], bb[1] - a[1])
            if not (0.8 * target <= d <= 1.25 * target) or p.side0 != q.side0:
                continue
            for style in ('any', 'manhattan'):
                free = R._raster(p.side0, a, bb, (p.pad_net[k], q.pad_net[m]), 0.25)[0]
                c0 = time.process_time()
                pts = R.route(p.side0, a, bb, (p.pad_net[k], q.pad_net[m]), 0.25, style)
                t = time.process_time() - c0
                rows.append(dict(style=style, straight=d, cells=int(free.size), t=t, ok=pts is not None,
                                 ratio=(X.path_length(pts) / d) if pts else None))
            n += 1
    out = {}
    for style in ('any', 'manhattan'):
        rr = [r for r in rows if r['style'] == style]
        out[style] = dict(exponent_cells=fit([r['cells'] for r in rr], [r['t'] for r in rr]),
                          by_length=[dict(target=t, med_ms=float(1e3 * np.median([r['t'] for r in rr if 0.8 * t <= r['straight'] <= 1.25 * t])),
                                          med_cells=float(np.median([r['cells'] for r in rr if 0.8 * t <= r['straight'] <= 1.25 * t])),
                                          med_ratio=float(np.median([r['ratio'] for r in rr if r['ratio'] and 0.8 * t <= r['straight'] <= 1.25 * t] or [float('nan')])))
                                     for t in (2.0, 4.0, 8.0, 16.0, 32.0)
                                     if any(0.8 * t <= r['straight'] <= 1.25 * t for r in rr)])
        for row in out[style]['by_length']:
            print(f"route {style}: hop ~{row['target']:.0f} mm: {row['med_ms']:.1f} ms, {row['med_cells']:.0f} cells, "
                  f"routed/straight {row['med_ratio']:.2f}", flush=True)
    return dict(rows=rows, **out)


def sweep_fv(board):
    import ex_exact as X
    from kae.board.kicad_file import load
    from kae.circuit.brief import build
    from kae.physics.place_terms import Terms
    b = load(str(ROOT / 'kae-work-v2' / 'tasks' / board / 'reference' / 'board.kicad_pcb'))
    T = Terms(b, build(b))
    if T.thermal is None:
        return None
    rows = []
    for dx in (1.0, 0.7, 0.5, 0.35, 0.25):
        c0 = time.process_time()
        F = X.FVThermal(T, dx=dx, max_nodes=10**7)
        t_setup = time.process_time() - c0
        c0 = time.process_time()
        F.rise()
        t_rise = time.process_time() - c0
        rows.append(dict(dx=dx, nodes=F.nodes, t_factor=F.t_factor, t_setup=t_setup, nnz_lu=F.nnz_lu,
                         lu_mb=F.nnz_lu * 12 / 2**20, t_solve=F.t_solve / max(1, F.solves)))
        print(f"fv dx {dx}: {F.nodes} nodes, factor {F.t_factor:.2f} s, LU {F.nnz_lu * 12 / 2**20:.0f} MB, "
              f"solve {1e3 * rows[-1]['t_solve']:.1f} ms", flush=True)
        del F
    return dict(rows=rows, exponent=fit([r['nodes'] for r in rows], [r['t_factor'] for r in rows]),
                exponent_solve=fit([r['nodes'] for r in rows], [r['t_solve'] for r in rows]))


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--board', default='olimex-dcdc-50-5-12-dcdc-50-5-12-rev-a1')
    ap.add_argument('--route-board', default='libresolar-bms-c1-bms-c1')
    ap.add_argument('--json', default=None)
    a = ap.parse_args(argv)
    res = dict(peec=sweep_peec())
    print(f"peec time exponent (n >= 100): {res['peec']['exponent']}")
    res['route'] = sweep_route(a.route_board)
    print(f"route time vs cells exponent: any {res['route']['any']['exponent_cells']:.2f}, "
          f"manhattan {res['route']['manhattan']['exponent_cells']:.2f}")
    res['fv'] = sweep_fv(a.board)
    if res['fv']:
        print(f"fv factor exponent {res['fv']['exponent']:.2f}, solve exponent {res['fv']['exponent_solve']:.2f}")
    if a.json:
        os.makedirs(os.path.dirname(a.json), exist_ok=True)
        json.dump(res, open(a.json, 'w'), indent=1, default=float)


if __name__ == '__main__':
    main()
