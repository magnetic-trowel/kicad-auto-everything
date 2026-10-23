# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Exact thermal at lookup speed: a precomputed finite-volume Green's table
(docs/topics/physics/exact-physics-options.md, placement-invariant operators).

The board's thermal operator (copper zones as placed, FR-4, convection) does not change when
parts move; only where heat enters does. So one factorization and one solve per source
position on a lattice give the whole response G(x, y) between lattice points of the two outer
layers, and every later placement is priced by lookups (superposition), with no solve.

For a board this script builds:
  direct   ex_exact.FVThermal (heat into the part's courtyard box on its outer layer);
  table    the same operator; a unit source in each pitch x pitch cell of a lattice on both
           outer layers (one solve each); the stored temperatures at every lattice point of both
           outer layers (float32). A part's heat is spread over the lattice cells under its box;
           a victim reads the interpolated temperature at its centre, a source the mean over
           its box;
and compares them on the thermal candidates of ex_decision_flips.py (each part's human pose,
translations, rotations; drawn the same way here when the board has no record yet): rise
error and the decision flips between the two among materially different pairs. Reports the
table's build time, memory and lookup time (numpy prototype).

Usage:  python tools/research/physics/ex_thermal_table.py --flips kae-work/physics/exact-options/flips
        [--only id1,id2] [--pitch 1.0] [--out kae-work/physics/exact-options/thermal-table]
"""
from __future__ import annotations

import argparse
import json
import os
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

DEFAULT = ('olimex-dcdc-50-5-12-dcdc-50-5-12-rev-a1', 'pcbcorpus-brenocq-bldc-motor-bldcm-power',
           'pcbcorpus-mohamedboubaker-battery-powered-stm32-board-with-usb-orbit', 'pcbcorpus-azoninc-doorman-doorman',
           'wntrblm-micronova-board', 'pcbcorpus-uzixls-pc-ega-composite-daughterboard-ega-composite-daughterboard')


class Table:
    def __init__(self, F, pitch):
        self.F = F
        nl, nx, ny, dx = F.nl, F.nx, F.ny, F.dx
        self.step = max(1, int(round(pitch / dx)))
        s = self.step
        self.ix = np.arange(s // 2, nx, s)
        self.iy = np.arange(s // 2, ny, s)
        self.layers = [0, nl - 1] if nl > 1 else [0]
        npts = len(self.ix) * len(self.iy)
        self.npts = npts
        nside = len(self.layers)
        self.G = np.zeros((nside, npts, nside, npts), np.float32)
        t0 = time.process_time()
        for a, la in enumerate(self.layers):
            for p, (i, j) in enumerate((i, j) for i in self.ix for j in self.iy):
                rhs = np.zeros((nl, nx, ny))
                i0, i1 = max(0, i - s // 2), min(nx, i - s // 2 + s)
                j0, j1 = max(0, j - s // 2), min(ny, j - s // 2 + s)
                rhs[la, i0:i1, j0:j1] = 1.0 / ((i1 - i0) * (j1 - j0))
                f = F.lu.solve(rhs.ravel()).reshape(nl, nx, ny)
                for b, lb in enumerate(self.layers):
                    self.G[a, p, b] = f[lb][np.ix_(self.ix, self.iy)].ravel()
        self.t_build = time.process_time() - t0
        self.solves = nside * npts
        self.mb = self.G.nbytes / 2**20

    def cells(self, box):
        """Lattice indices under a (layer, i0, i1, j0, j1) box (at least the nearest one)."""
        layer, i0, i1, j0, j1 = box
        a = self.layers.index(layer) if layer in self.layers else 0
        xi = np.nonzero((self.ix >= i0) & (self.ix <= i1))[0]
        yj = np.nonzero((self.iy >= j0) & (self.iy <= j1))[0]
        if not len(xi):
            xi = np.array([int(np.argmin(np.abs(self.ix - 0.5 * (i0 + i1))))])
        if not len(yj):
            yj = np.array([int(np.argmin(np.abs(self.iy - 0.5 * (j0 + j1))))])
        return a, (xi[:, None] * len(self.iy) + yj[None, :]).ravel()

    def interp(self, i, j):
        """Bilinear weights over lattice points for grid cell (i, j)."""
        fx = np.clip(np.interp(i, self.ix, np.arange(len(self.ix))), 0, len(self.ix) - 1)
        fy = np.clip(np.interp(j, self.iy, np.arange(len(self.iy))), 0, len(self.iy) - 1)
        x0, y0 = int(np.floor(fx)), int(np.floor(fy))
        x1, y1 = min(x0 + 1, len(self.ix) - 1), min(y0 + 1, len(self.iy) - 1)
        tx, ty = fx - x0, fy - y0
        idx = [x0 * len(self.iy) + y0, x1 * len(self.iy) + y0, x0 * len(self.iy) + y1, x1 * len(self.iy) + y1]
        w = [(1 - tx) * (1 - ty), tx * (1 - ty), (1 - tx) * ty, tx * ty]
        return np.array(idx), np.array(w)

    def rise(self):
        F = self.F
        st = F.T.st
        src_cells = [self.cells(F._box(i)) for i in F.src]
        out = np.zeros(len(F.targets))
        for t, i in enumerate(F.targets):
            box = F._box(i)
            if t < len(F.src):
                b, pts = self.cells(box)
                val = 0.0
                for k, (a, cs) in enumerate(src_cells):
                    val += F.P[k] * float(self.G[a][np.ix_(cs, [b])][:, 0][:, pts].mean())
            else:
                layer = box[0]
                b = self.layers.index(layer) if layer in self.layers else 0
                ci = (st.X[i] - F.x0) / F.dx
                cj = (st.Y[i] - F.y0) / F.dx
                idx, w = self.interp(ci, cj)
                val = 0.0
                for k, (a, cs) in enumerate(src_cells):
                    val += F.P[k] * float((self.G[a][cs][:, b][:, idx] @ w).mean())
            out[t] = val
        mean = float(F.P.sum()) / (F.hsum * F.Lx * F.Ly * 1e-6)
        return out, mean


def own_candidates(T, bid, n_parts=6, seed=1):
    """The candidates ex_decision_flips.py would draw for the thermal kind (same moves)."""
    import math
    import random
    from pt_human_perturb import Legal, kind_parts
    rng = random.Random(f'{seed}:{bid}')
    legal = Legal(T)
    bv = T.bv
    poses = bv.pose0()
    locked = {p.i for p in bv.parts if p.locked}
    parts = sorted(kind_parts(T, 'thermal') - locked)
    sample = parts if len(parts) <= n_parts else rng.sample(parts, n_parts)
    out = []
    for i in sample:
        x, y, r, s = poses[T.uids[i]]
        rows = [dict(move='human', pose=[x, y, r, s], thermal={})]
        for _ in range(3):
            for _try in range(20):
                ang = rng.uniform(0, 2 * math.pi)
                d = rng.uniform(1.0, 5.0)
                q = (x + d * math.cos(ang), y + d * math.sin(ang), r, s)
                if legal.ok(i, q):
                    rows.append(dict(move='translate', pose=list(q), thermal={}))
                    break
        for dr in (90.0, 180.0, 270.0):
            q = (x, y, (r + dr) % 360.0, s)
            if legal.ok(i, q):
                rows.append(dict(move='rotate', pose=list(q), thermal={}))
        out.append(dict(kind='thermal', part=bv.parts[i].ref, rows=rows))
    return out


def run(bid, flips_dir, pitch):
    import ex_exact as X
    from kae.board.kicad_file import load
    from kae.circuit.brief import build
    from kae.physics.place_terms import Terms
    import ex_decision_flips as D
    b = load(str(ROOT / 'kae-work-v2' / 'tasks' / bid / 'reference' / 'board.kicad_pcb'))
    T = Terms(b, build(b))
    T.total(T.bv.pose0())
    fp = os.path.join(flips_dir, bid + '.json')
    if os.path.exists(fp):
        cands = [c for c in json.load(open(fp)).get('candidates', []) if c['kind'] == 'thermal']
    else:
        cands = own_candidates(T, bid)
    F = X.FVThermal(T)
    tab = Table(F, pitch)
    out = dict(id=bid, nodes=F.nodes, dx=F.dx, t_factor=F.t_factor, lattice=tab.npts, solves=tab.solves,
               t_build=tab.t_build, table_mb=tab.mb, pairs=0, flips=0, rise_err=[], t_lookup=[], t_direct=[])
    ref2i = {p.ref: p.i for p in T.bv.parts}
    st = T.st
    for cand in cands:
        i = ref2i.get(cand['part'])
        rows = [r for r in cand['rows'] if 'thermal' in r]
        if i is None or len(rows) < 2:
            continue
        cd, ct = [], []
        rises = []
        for r in rows:
            saved = st.get(i)
            st.set(i, *r['pose'])
            c0 = time.process_time()
            rd, md = F.rise()
            out['t_direct'].append(time.process_time() - c0)
            c0 = time.process_time()
            rt, mt = tab.rise()
            out['t_lookup'].append(time.process_time() - c0)
            st.set(i, *saved)
            cd.append(X.thermal_cost(T, rd, md))
            ct.append(X.thermal_cost(T, rt, mt))
            rises.append((rd - md, rt - mt))
            out['rise_err'] += [float(abs(a - b_)) for a, b_ in zip(rd - md, rt - mt)]
        al = [a.value for a in T._th_alloc]
        for x in range(len(rows)):
            for y in range(x + 1, len(rows)):
                if not any(abs(p - q) / a >= D.MATERIAL for p, q, a in zip(rises[x][0], rises[y][0], al)):
                    continue
                out['pairs'] += 1
                da, db = ct[x] - ct[y], cd[x] - cd[y]
                out['flips'] += ((da > 0) != (db > 0)) or abs(da) < 1e-15
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--flips', default=str(ROOT / 'kae-work' / 'physics' / 'exact-options' / 'flips'))
    ap.add_argument('--out', default=str(ROOT / 'kae-work' / 'physics' / 'exact-options' / 'thermal-table'))
    ap.add_argument('--only', default='')
    ap.add_argument('--pitch', type=float, default=1.0)
    a = ap.parse_args(argv)
    os.makedirs(a.out, exist_ok=True)
    res = []
    for bid in (a.only.split(',') if a.only else DEFAULT):
        r = run(bid, a.flips, a.pitch)
        e = np.array(r['rise_err']) if r['rise_err'] else np.zeros(1)
        print(f"{bid[:40]}: FV {r['nodes']} nodes (dx {r['dx']}), factor {r['t_factor']:.2f} s; table {r['lattice']} "
              f"points/side, {r['solves']} solves in {r['t_build']:.1f} s, {r['table_mb']:.0f} MB; lookup "
              f"{1e3 * np.median(r['t_lookup'] or [0]):.2f} ms vs direct {1e3 * np.median(r['t_direct'] or [0]):.1f} ms; "
              f"excess-rise error median {np.median(e):.2f} K (p90 {np.percentile(e, 90):.2f}); flips {r['flips']}/{r['pairs']}",
              flush=True)
        r['rise_err'] = dict(med=float(np.median(e)), p90=float(np.percentile(e, 90)))
        r['t_lookup'] = float(np.median(r['t_lookup'] or [0]))
        r['t_direct'] = float(np.median(r['t_direct'] or [0]))
        res.append(r)
    json.dump(res, open(os.path.join(a.out, 'summary.json'), 'w'), indent=1, default=float)


if __name__ == '__main__':
    main()
