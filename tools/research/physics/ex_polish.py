# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Does deciding with exact physics give a better placement, and at what cost?
(docs/topics/physics/exact-physics-options.md, designs a, b, h)

A small, controlled stand-in for the placer's endgame on real boards. Start from the human
placement with the loop-structure parts knocked out of place (each sampled part moved 2-4 mm,
one in three also rotated, legal per pt_human_perturb.Legal), then run the same greedy local
search under different evaluators and score every result with the exact reference:

  fast     choose by the place terms (straight hops);
  detour   choose by fast + L' x routed detour (route-aware fast, one route per board hop);
  exact    choose by PEEC on Manhattan routes (a drop-in --physics exact);
  mf3      the place terms rank the proposals, PEEC chooses among the best three and the current
           pose (multi-fidelity);
  mf3cf    as mf3 with closed forms on any-angle routes as the second stage.

Greedy search: two sweeps over the sampled parts; each step proposes the current pose plus
eight legal 0.5-3 mm translations and the legal 90/180/270 degree rotations (the same
proposals for the same pose), and keeps the best by the strategy's evaluator. The objective
is the cost (c phi(u)) of the commutation, decap, ESD and crystal structures the part belongs
to. Every final state is scored by PEEC (crystal: routed length x field-solver C').

Reported per board and pooled: exact cost of the start, of the human placement and of each
strategy's result; exact evaluations and CPU seconds per strategy.

Usage:  python tools/research/physics/ex_polish.py --out kae-work/physics/exact-options/polish [--only ids]
        [--parts 10] [--sweeps 2]
"""
from __future__ import annotations

import argparse
import glob
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

KINDS = ('commutation', 'decap', 'esd', 'crystal')
DEFAULT = ('olimex-dcdc-50-5-12-dcdc-50-5-12-rev-a1', 'pcbcorpus-brenocq-bldc-motor-bldcm-power',
           'olimex-mipi-hdmi-mipi-hdmi-rev-b', 'pcbcorpus-protolux-electronics-trellis-core-trellis-core',
           'pcbcorpus-bentwire-usb-c-fusb302-pi-usb-c-fusb302-pi', 'hackclub-reflow-badge',
           'pcbcorpus-waterloo-rocketry-canhw-processor', 'kicad-demos-stickhub-stickhub',
           'pcbcorpus-ikajdan-reflow-hot-plate-control-board', 'chipsalliance-rocket-pcb-fmc-sdram')


class Ev:
    """Structure costs at the current state under one evaluator, with counters."""

    def __init__(self, T, R, X):
        self.T, self.R, self.X = T, R, X
        self.n_exact = 0
        self.t = 0.0

    def cost(self, ks, mode):
        from kae.physics.place_terms import _red
        T = self.T
        c0 = time.process_time()
        if mode != 'fast':
            self.R.refresh()
        tot = 0.0
        for k in ks:
            s = T.structs[k]
            if mode == 'fast':
                v = _red(s.reduce, [c.value(T.st) for c in s.comps], s.info.get('weights'))
            else:
                v, _ = self.X.struct_value(T, k, self.R, 'cf' if (mode == 'cf' or s.kind == 'crystal') else mode)
                self.n_exact += 1
                if v is None:
                    self.t += time.process_time() - c0
                    return None
            tot += T._cost(s, v)
        self.t += time.process_time() - c0
        return tot


def proposals(legal, i, pose, key):
    rng = random.Random(key)
    x, y, r, s = pose
    out = [pose]
    for k in range(8):
        ang = 2 * math.pi * k / 8 + rng.uniform(-0.3, 0.3)
        d = rng.uniform(0.5, 3.0)
        q = (x + d * math.cos(ang), y + d * math.sin(ang), r, s)
        if legal.ok(i, q):
            out.append(q)
    for dr in (90.0, 180.0, 270.0):
        q = (x, y, (r + dr) % 360.0, s)
        if legal.ok(i, q):
            out.append(q)
    return out


def run_board(bid, out_dir, n_parts, sweeps, seed):
    import ex_exact as X
    from kae.board.kicad_file import load
    from kae.circuit.brief import build
    from kae.physics.place_terms import Terms
    from pt_human_perturb import Legal
    X.PEEC_CLIP = True
    path = ROOT / 'kae-work-v2' / 'tasks' / bid / 'reference' / 'board.kicad_pcb'
    b = load(str(path))
    T = Terms(b, build(b))
    bv = T.bv
    poses0 = bv.pose0()
    T.total(poses0)
    X.attach_aggressors(T)
    R = X.Router(T)
    legal = Legal(T)
    st = T.st
    rng = random.Random(f'{seed}:{bid}')
    locked = {p.i for p in bv.parts if p.locked}
    cand = sorted({i for k, s in enumerate(T.structs) if s.kind in KINDS for i in s.members} - locked)
    ev = Ev(T, R, X)
    # keep parts whose structures have an exact value at the human pose
    good = []
    for i in cand:
        ks = [k for k in T.inc.get(i, ()) if T.structs[k].kind in KINDS]
        if ks and ev.cost(ks, 'peec') is not None:
            good.append(i)
    if not good:
        return dict(id=bid, status='no parts')
    parts = good if len(good) <= n_parts else rng.sample(good, n_parts)
    allks = sorted({k for i in parts for k in T.inc.get(i, ()) if T.structs[k].kind in KINDS})
    human = ev.cost(allks, 'peec')
    human_fast = ev.cost(allks, 'fast')
    # degraded start
    start = {}
    for i in parts:
        x, y, r, s = st.get(i)
        for _ in range(40):
            ang = rng.uniform(0, 2 * math.pi)
            d = rng.uniform(2.0, 4.0)
            rr = (r + rng.choice((90.0, 180.0, 270.0))) % 360.0 if rng.random() < 0.33 else r
            q = (x + d * math.cos(ang), y + d * math.sin(ang), rr, s)
            if legal.ok(i, q):
                st.set(i, *q)
                legal.geo[i] = legal.at(i, q)
                legal._tree()
                break
        start[i] = st.get(i)
    s_exact = ev.cost(allks, 'peec')
    s_fast = ev.cost(allks, 'fast')
    if s_exact is None:
        for i in parts:
            st.set(i, *poses0[T.uids[i]])
        return dict(id=bid, status='start not evaluable')
    out = dict(id=bid, status='ok', parts=len(parts), structures=len(allks), human_exact=human, human_fast=human_fast,
               start_exact=s_exact, start_fast=s_fast, strategies={})
    geo0 = dict(legal.geo)
    for strat in ('fast', 'detour', 'mf3cf', 'mf3', 'exact'):
        for i in parts:
            st.set(i, *start[i])
        legal.geo = dict(geo0)
        legal._tree()
        ev.n_exact = 0
        ev.t = 0.0
        c0 = time.process_time()
        for sw in range(sweeps):
            for i in parts:
                ks = [k for k in T.inc.get(i, ()) if T.structs[k].kind in KINDS]
                cur = st.get(i)
                props = proposals(legal, i, cur, f'{bid}:{T.uids[i]}:{sw}:{cur}')
                scored = []
                for q in props:
                    st.set(i, *q)
                    if strat in ('fast', 'mf3', 'mf3cf'):
                        c = ev.cost(ks, 'fast')
                    elif strat == 'detour':
                        c = ev.cost(ks, 'detour')
                    else:
                        c = ev.cost(ks, 'peec')
                    scored.append((c if c is not None else float('inf'), q))
                if strat in ('mf3', 'mf3cf'):
                    # the exact stage sees the fast top three and the current pose, so it never
                    # accepts a move that is worse by its own measure
                    top = sorted(scored[1:], key=lambda t: t[0])[:3] + [scored[0]]
                    scored = []
                    for _, q in top:
                        st.set(i, *q)
                        c = ev.cost(ks, 'peec' if strat == 'mf3' else 'cf')
                        scored.append((c if c is not None else float('inf'), q))
                best = min(scored, key=lambda t: t[0])[1]
                st.set(i, *best)
                legal.geo[i] = legal.at(i, best)
                legal._tree()
        cpu = time.process_time() - c0
        final = ev.cost(allks, 'peec')
        out['strategies'][strat] = dict(final_exact=final, final_fast=ev.cost(allks, 'fast'), cpu_s=cpu,
                                        exact_evals=ev.n_exact)
        print(f"  {bid[:40]} {strat}: exact {s_exact:.4f} -> {final if final is None else round(final, 4)} "
              f"(human {human:.4f}), {cpu:.1f} s", flush=True)
    for i in parts:
        st.set(i, *poses0[T.uids[i]])
    out['peec_clipped'] = X.PEEC_CLIPPED[0]
    json.dump(out, open(os.path.join(out_dir, bid + '.json'), 'w'), indent=1, default=float)
    return out


def summarize(out_dir):
    recs = [json.load(open(f)) for f in sorted(glob.glob(os.path.join(out_dir, '*.json')))
            if not os.path.basename(f).startswith('summary')]
    recs = [r for r in recs if r.get('status') == 'ok']
    L = ['| board | parts | structures | start | human | fast | detour | mf3cf | mf3 | exact | exact evals (mf3, exact) | CPU s (fast, mf3, exact) |',
         '|---|---|---|---|---|---|---|---|---|---|---|---|']
    gains = {s: [] for s in ('fast', 'detour', 'mf3cf', 'mf3', 'exact')}
    for r in recs:
        S = r['strategies']
        row = f"| {r['id'][:36]} | {r['parts']} | {r['structures']} | {r['start_exact']:.3f} | {r['human_exact']:.3f} |"
        for s in gains:
            v = S.get(s, {}).get('final_exact')
            row += f" {v:.3f} |" if v is not None else ' - |'
            if v is not None:
                gains[s].append((r['start_exact'] - v) / max(r['start_exact'], 1e-12))
        row += f" {S['mf3']['exact_evals']}, {S['exact']['exact_evals']} | {S['fast']['cpu_s']:.1f}, {S['mf3']['cpu_s']:.1f}, {S['exact']['cpu_s']:.1f} |"
        L.append(row)
    L += ['', 'exact-cost reduction from the start, median over boards (mean): ' +
          ', '.join(f"{s} {100 * np.median(v):.1f}% ({100 * np.mean(v):.1f}%)" for s, v in gains.items() if v)]
    rel = []
    for r in recs:
        f, e = r['strategies']['fast']['final_exact'], r['strategies']['exact']['final_exact']
        m = r['strategies']['mf3']['final_exact']
        if f and e and m:
            rel.append(((f - e) / f, (f - m) / f))
    if rel:
        rel = np.array(rel)
        L.append(f"exact vs fast final exact cost: median {100 * np.median(rel[:, 0]):.1f}% lower (mean {100 * rel[:, 0].mean():.1f}%); "
                 f"mf3 vs fast: median {100 * np.median(rel[:, 1]):.1f}% (mean {100 * rel[:, 1].mean():.1f}%)")
    open(os.path.join(out_dir, 'summary.md'), 'w').write('\n'.join(L) + '\n')
    print('\n'.join(L))


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', required=True)
    ap.add_argument('--only', default='')
    ap.add_argument('--parts', type=int, default=10)
    ap.add_argument('--sweeps', type=int, default=2)
    ap.add_argument('--seed', type=int, default=1)
    ap.add_argument('--summary-only', action='store_true')
    a = ap.parse_args(argv)
    os.makedirs(a.out, exist_ok=True)
    if not a.summary_only:
        for bid in (a.only.split(',') if a.only else DEFAULT):
            if os.path.exists(os.path.join(a.out, bid + '.json')):
                continue
            t0 = time.time()
            r = run_board(bid, a.out, a.parts, a.sweeps, a.seed)
            print(f"{bid}: {r.get('status')} {time.time() - t0:.0f} s", flush=True)
    summarize(a.out)


if __name__ == '__main__':
    main()
