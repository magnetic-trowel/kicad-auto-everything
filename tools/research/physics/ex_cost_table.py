# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""What does exact physics cost per evaluation and per placement move, on real boards?
(docs/topics/physics/exact-physics-options.md, cost table)

For each board (kae-work-v2/tasks/<id>/reference/board.kicad_pcb, human placement) this
times, on one core (CPU seconds, time.process_time; wall time beside it):

  fast     Terms construction, a cold `total`, and `delta` for random 1-5 mm moves and
           rotations of physics parts (per moved part's structure kind);
  exact    every structure at the human pose with the ex_exact evaluators: detour (routed
           length correction), cf (any-angle routes + closed forms), cfm (Manhattan routes +
           closed forms), peec (Manhattan routes + multi-filament PEEC; filament count and the
           dense partial-inductance matrix's memory), crystal (field-solver C' + routes),
           coupling (PEEC aggressor currents + EMF on the routed victim);
  per move the exact re-evaluation a drop-in `--physics exact` would do for one move: all
           structures the moved part belongs to, routes and solve, for random moves;
  thermal  the finite-volume board model: nodes, assembly, factorization (SuperLU, MMD on
           A'+A), LU fill and memory, one solve; and the fin kernel's cost for the same targets.

Usage:
  python tools/research/physics/ex_cost_table.py --out kae-work/physics/exact-options/costs [--only id1,id2]
         [--moves 200] [--exact-moves 30]
Deterministic (seeded). Prints one line per board and writes <out>/<id>.json and summary.md.
"""
from __future__ import annotations

import argparse
import glob
import json
import math
import os
import random
import resource
import sys
import time
from collections import defaultdict
from pathlib import Path

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / 'kae' / 'src'))
sys.path.insert(0, str(HERE))

import numpy as np  # noqa: E402

DEFAULT = ('pcbcorpus-badjeff-paw3222-pcb-paw3222', 'pcbcorpus-tcsullivan-noisecard-noisecard',
           'olimex-dcdc-50-5-12-dcdc-50-5-12-rev-a1', 'pcbcorpus-jkramarz-thetick-tick',
           'pcbcorpus-brenocq-bldc-motor-bldcm-power', 'olimex-mipi-hdmi-mipi-hdmi-rev-b',
           'pcbcorpus-ikajdan-reflow-hot-plate-control-board', 'libresolar-bms-c1-bms-c1',
           'sparkfun-sparkfun-xrp-controller-sparkfun-xrp-controller', 'bluerobotics-ping-dev-kit-pingdevkit',
           'azonenberg-latentred-linecard')


class Clock:
    def __enter__(self):
        self.c0 = time.process_time()
        self.w0 = time.perf_counter()
        return self

    def __exit__(self, *a):
        self.cpu = time.process_time() - self.c0
        self.wall = time.perf_counter() - self.w0


def stats(v):
    v = np.asarray(v, float)
    if not len(v):
        return None
    return dict(n=int(len(v)), med=float(np.median(v)), p90=float(np.percentile(v, 90)), max=float(v.max()))


def run_board(bid, out_dir, n_moves, n_exact, seed):
    import ex_exact as X
    from kae.board.kicad_file import load
    from kae.circuit.brief import build
    from kae.physics.place_terms import Terms
    path = ROOT / 'kae-work-v2' / 'tasks' / bid / 'reference' / 'board.kicad_pcb'
    rng = random.Random(f'{seed}:{bid}')
    rec = dict(id=bid)
    task = json.load(open(path.parents[1] / 'task.json'))
    rec['split'] = task.get('split')
    with Clock() as c:
        b = load(str(path))
    rec['t_load'] = c.cpu
    with Clock() as c:
        brief = build(b)
    rec['t_brief'] = c.cpu
    with Clock() as c:
        T = Terms(b, brief)
    rec['t_terms'] = c.cpu
    bv = T.bv
    poses = bv.pose0()
    rec['parts'] = len(bv.parts)
    rec['layers'] = len(bv.copper)
    rec['board_mm'] = [bv.bbox[2] - bv.bbox[0], bv.bbox[3] - bv.bbox[1]]
    kinds = defaultdict(int)
    for s in T.structs:
        kinds[s.kind] += 1
    if T.thermal is not None:
        kinds['thermal'] = len(T.thermal.targets)
    rec['structures'] = dict(kinds)
    T.total(poses)                       # numba load
    with Clock() as c:
        for _ in range(20):
            T._epoch = [e + 1 for e in T._epoch]
            T._scache = [None] * len(T.structs)
            T._ccache = [[None] * len(s.comps) for s in T.structs]
            T._th_epochs = None
            T.total(poses)
    rec['t_total_cold'] = c.cpu / 20
    # ---- fast delta per moved part kind
    phys = sorted(T.inc) + sorted(set(T.th_parts) - set(T.inc))
    locked = {p.i for p in bv.parts if p.locked}
    phys = [i for i in phys if i not in locked]
    rec['physics_parts'] = len(phys)
    dt_by = defaultdict(list)
    moves = []
    for _ in range(n_moves if phys else 0):
        i = rng.choice(phys)
        u = T.uids[i]
        x, y, r, s = poses[u]
        if rng.random() < 0.7:
            ang = rng.uniform(0, 2 * math.pi)
            d = rng.uniform(1.0, 5.0)
            q = (x + d * math.cos(ang), y + d * math.sin(ang), r, s)
        else:
            q = (x, y, (r + rng.choice((90.0, 180.0, 270.0))) % 360.0, s)
        moves.append((i, q))
    T.total(poses)
    for i, q in moves:
        u = T.uids[i]
        kinds_i = sorted({T.structs[k].kind for k in T.inc.get(i, ())} | ({'thermal'} if i in T.th_parts else set()))
        c0 = time.process_time()
        for _ in range(5):
            T.delta(poses, [u], [q])
        dt = (time.process_time() - c0) / 5
        for kd in kinds_i:
            dt_by[kd].append(dt)
        dt_by['all'].append(dt)
    rec['fast_delta_us'] = {k: stats(1e6 * np.array(v)) for k, v in dt_by.items()}
    # ---- exact, every structure at the human pose
    X.attach_aggressors(T)
    R = X.Router(T)
    R.refresh()
    ex = defaultdict(lambda: defaultdict(list))
    fil = defaultdict(list)
    fail = defaultdict(lambda: defaultdict(int))
    for k, s in enumerate(T.structs):
        if s.kind not in ('commutation', 'decap', 'esd', 'crystal', 'coupling'):
            continue
        modes = ('detour', 'cf', 'cfm', 'peec') if s.kind in ('commutation', 'decap', 'esd') else \
            (('cf',) if s.kind in ('crystal', 'coupling') else ())
        for m in modes:
            r0 = R.stats['seconds']
            with Clock() as c:
                v, infos = X.struct_value(T, k, R, m)
            if v is None:
                fail[s.kind][m] += 1
                continue
            ex[s.kind][m].append(c.cpu)
            ex[s.kind][m + '_route'].append(R.stats['seconds'] - r0)
            if m == 'peec' and isinstance(infos, list):
                for inf in infos:
                    if isinstance(inf, dict) and inf.get('filaments'):
                        fil[s.kind].append(inf['filaments'])
            if s.kind == 'coupling' and isinstance(infos, list):
                for inf in infos:
                    if isinstance(inf, dict) and inf.get('filaments'):
                        fil['coupling'].append(inf['filaments'])
    rec['exact_ms'] = {kd: {m: stats(1e3 * np.array(v)) for m, v in d.items()} for kd, d in ex.items()}
    rec['exact_fail'] = {kd: dict(d) for kd, d in fail.items()}
    rec['peec_filaments'] = {kd: stats(v) for kd, v in fil.items()}
    rec['peec_matrix_mb'] = {kd: stats(8.0 * np.array(v) ** 2 / 2**20) for kd, v in fil.items()}
    # ---- exact per move (a drop-in exact Terms.delta: every structure the part belongs to)
    per_move = defaultdict(list)
    st = T.st
    exact_moves = [mv for mv in moves if mv[0] in T.inc][:n_exact]
    for i, q in exact_moves:
        ks = [k for k in T.inc.get(i, ()) if T.structs[k].kind in ('commutation', 'decap', 'esd', 'crystal', 'coupling')]
        if not ks:
            continue
        for m in ('cf', 'peec'):
            saved = st.get(i)
            with Clock() as c:
                st.set(i, *q)
                R.refresh()
                for k in ks:
                    mm = m if T.structs[k].kind in ('commutation', 'decap', 'esd') else 'cf'
                    X.struct_value(T, k, R, mm)
                st.set(i, *saved)
                R.refresh()
                for k in ks:
                    mm = m if T.structs[k].kind in ('commutation', 'decap', 'esd') else 'cf'
                    X.struct_value(T, k, R, mm)
            per_move[m].append(c.cpu)
            per_move[m + '_structs'].append(len(ks))
    rec['exact_move_ms'] = {m: stats(1e3 * np.array(v)) if not m.endswith('_structs') else stats(v)
                            for m, v in per_move.items()}
    # ---- thermal
    if T.thermal is not None:
        with Clock() as c:
            F = X.FVThermal(T)
        th = dict(nodes=F.nodes, dx=F.dx, t_build=F.t_build, t_factor=F.t_factor, t_setup_cpu=c.cpu,
                  nnz_lu=F.nnz_lu, lu_mb=F.nnz_lu * 12 / 2**20, targets=len(F.targets), sources=len(F.src))
        with Clock() as c:
            F.rise()
        th['t_rise_cold'] = c.cpu
        th['solves'] = F.solves
        th['t_per_solve'] = F.t_solve / max(1, F.solves)
        with Clock() as c:
            for _ in range(10):
                X.fast_rise(T)
        th['t_fast_full'] = c.cpu / 10
        rec['thermal'] = th
    rec['router'] = dict(calls=R.stats['calls'], seconds=R.stats['seconds'],
                         ms_per_call=1e3 * R.stats['seconds'] / max(1, R.stats['calls']))
    rec['peak_rss_mb'] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    json.dump(rec, open(os.path.join(out_dir, bid + '.json'), 'w'), indent=1, default=float)
    return rec


def summarize(out_dir):
    recs = [json.load(open(f)) for f in sorted(glob.glob(os.path.join(out_dir, '*.json')))
            if not os.path.basename(f).startswith('summary')]
    recs.sort(key=lambda r: r['parts'])
    L = ['| board | split | parts | layers | structures | fast delta median us (p90) | terms build ms | '
         'exact per move, cf ms | exact per move, peec ms | FV nodes | FV factor s | FV solve ms |',
         '|---|---|---|---|---|---|---|---|---|---|---|---|']
    for r in recs:
        fd = (r.get('fast_delta_us') or {}).get('all')
        em = r.get('exact_move_ms') or {}
        th = r.get('thermal') or {}
        ns = sum(v for k, v in r['structures'].items() if k != 'thermal')
        L.append(f"| {r['id'][:34]} | {r.get('split')} | {r['parts']} | {r['layers']} | {ns} (+{r['structures'].get('thermal', 0)} th) | "
                 f"{fd['med']:.0f} ({fd['p90']:.0f}) | {1e3 * r['t_terms']:.0f} | " if fd else
                 f"| {r['id'][:34]} | {r.get('split')} | {r['parts']} | {r['layers']} | {ns} | - | {1e3 * r['t_terms']:.0f} | ")
        L[-1] += (f"{em['cf']['med']:.0f} ({em['cf']['p90']:.0f}) | " if em.get('cf') else '- | ') + \
                 (f"{em['peec']['med']:.0f} ({em['peec']['p90']:.0f}) | " if em.get('peec') else '- | ') + \
                 (f"{th['nodes']} | {th['t_factor']:.2f} | {1e3 * th['t_per_solve']:.1f} |" if th else '- | - | - |')
    # pooled per kind
    pool = defaultdict(lambda: defaultdict(list))
    for r in recs:
        for kd, d in (r.get('exact_ms') or {}).items():
            for m, s in d.items():
                if s:
                    pool[kd][m].append(s['med'])
    L += ['', 'per-structure exact evaluation, median over boards of the per-board median (ms CPU):']
    for kd, d in pool.items():
        L.append(f"  {kd}: " + ', '.join(f"{m} {np.median(v):.1f}" for m, v in sorted(d.items())))
    fd_kind = defaultdict(list)
    for r in recs:
        for kd, s in (r.get('fast_delta_us') or {}).items():
            if s:
                fd_kind[kd].append(s['med'])
    L += ['', 'fast delta by moved part kind, median over boards (us CPU): ' +
          ', '.join(f'{k} {np.median(v):.0f}' for k, v in sorted(fd_kind.items()))]
    open(os.path.join(out_dir, 'summary.md'), 'w').write('\n'.join(L) + '\n')
    print('\n'.join(L))


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', required=True)
    ap.add_argument('--only', default='')
    ap.add_argument('--moves', type=int, default=200)
    ap.add_argument('--exact-moves', type=int, default=30)
    ap.add_argument('--seed', type=int, default=1)
    ap.add_argument('--summary-only', action='store_true')
    a = ap.parse_args(argv)
    os.makedirs(a.out, exist_ok=True)
    if not a.summary_only:
        ids = a.only.split(',') if a.only else list(DEFAULT)
        for bid in ids:
            if os.path.exists(os.path.join(a.out, bid + '.json')):
                continue
            t0 = time.time()
            r = run_board(bid, a.out, a.moves, a.exact_moves, a.seed)
            print(f"{bid}: {r['parts']} parts, {time.time() - t0:.0f} s", flush=True)
    summarize(a.out)


if __name__ == '__main__':
    main()
