#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""bus-pose-ab: bus metrics per run and the paired tests of PLAN.md.

  analyze.py jobs EXP > CMDS.txt      one busmetrics job per board (tools/research/bus_pose/busmetrics.py)
  analyze.py report EXP               tables and tests from the merged per-run bus records

Bus records are written to ~/kae-baselines/experiments/EXP/bus/<board>.jsonl: one line per (run, bus)
(open lines, vias, track length, layers needed (lds), LIS planar share, foreign crossings, straight
length). Buses come from the human board's netlist and footprints (detection only uses
netlist and pad geometry); the human placement is measured here and is in no arm's input.
"""
import argparse, glob, json, os, sys, collections

HOME = os.path.expanduser('~')
EXP = f'{HOME}/kae-baselines/experiments'
BOARDS = f'{HOME}/kae-baselines/boards'
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', '..', '..', 'research', 'bus_pose'))


def experiment(name):
    e = json.load(open(f'{EXP}/{name}/experiment.json'))
    return e, [b.strip() for b in open(f'{EXP}/{name}/boards.txt') if b.strip()]


def runs_of(board, method_ids):
    out = {}
    for m in method_ids:
        for r in glob.glob(f'{BOARDS}/{board}/runs/*.{m[:8]}.a*'):
            out.setdefault(m, []).append(r)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', choices=['jobs', 'report'])
    ap.add_argument('exp')
    ap.add_argument('--control', help='control method name substring (default: the first method)')
    a = ap.parse_args()
    e, boards = experiment(a.exp)
    methods = e['methods']
    out_dir = f'{EXP}/{a.exp}/bus'
    os.makedirs(out_dir, exist_ok=True)
    if a.cmd == 'jobs':
        repo = os.path.join(HERE, '..', '..', '..', '..')
        py = os.environ.get('BUS_PY') or sys.executable
        for b in boards:
            runs = runs_of(b, [m['id'] for m in methods])
            rlist = [r for rs in runs.values() for r in rs]
            if not rlist:
                continue
            job = dict(board=b, runs=rlist)
            jf = f'{out_dir}/{b}.job.json'
            json.dump(job, open(jf, 'w'))
            print(f'cd {os.path.abspath(repo)} && PYTHONPATH=kae/src BUS_TMP=$(mktemp -d) {py} tools/research/bus_pose/busmetrics_job.py {jf} {out_dir}/{b}.jsonl')
    else:
        report(a.exp, e, boards, out_dir, methods, a.control)


def report(exp, e, boards, out_dir, methods, control):
    import numpy as np
    import pandas as pd
    rows = []
    mid = {m['id'][:8]: m['name'] for m in methods}
    for b in boards:
        f = f'{out_dir}/{b}.jsonl'
        if not os.path.exists(f):
            continue
        for l in open(f):
            d = json.loads(l)
            d.pop('nets_all', None)
            rows.append(d)
    d = pd.DataFrame(rows)
    d.to_pickle(f'{out_dir}/all.pkl')
    print(f'{len(d)} bus-run records, {d.board.nunique()} boards')
    if not len(d):
        return
    d['human'] = d.run.str.startswith('human')
    d['arm'] = d.run.map(lambda r: mid.get(r.split('.')[1], r.split('.')[0]))
    d['attempt'] = d.run.map(lambda r: int(r.split('.a')[-1]))
    # lines counted once: comp buses, plus pair buses with no comp of at least 6 lines
    d['pair_only'] = (d.level == 'pair') & (d.lcomp < 6)
    D = d[(d.level == 'comp') | d.pair_only].copy()
    D['planar'] = D.lis >= 0.999
    D['vias_per_line'] = D.vias / D.n
    D['open_share'] = D.lines_open / D.n
    per = D.groupby(['arm', 'board', 'attempt']).agg(
        buses=('n', 'size'), lines=('n', 'sum'), lines_open=('lines_open', 'sum'), vias=('vias', 'sum'), L=('L', 'sum'),
        lds=('lds', 'mean'), lis=('lis', 'mean'), planar=('planar', 'mean'), foreign_xing=('foreign_xing', 'sum'),
        track_len=('track_len', 'sum'), unconnected=('unconnected', 'first'), errors=('errors', 'first'), legal=('legal', 'first'),
        completion=('completion', 'first')).reset_index()
    per['vias_per_line'] = per.vias / per.lines
    per['foreign_per_line'] = per.foreign_xing / per.lines
    per['open_rate'] = per.lines_open / per.lines
    H = per[per.arm.str.contains('human', case=False)]
    arms = [m['name'] for m in methods]
    ctrl = next((a for a in arms if control and control in a), arms[0])
    per.to_csv(f'{out_dir}/per_run.csv', index=False)
    summ = per[per.arm.isin(arms) | per.arm.str.contains('human')].groupby('arm').agg(
        n=('board', 'nunique'), lines=('lines', 'sum'), lines_open=('lines_open', 'sum'), open_rate=('open_rate', 'mean'),
        vias_per_line=('vias_per_line', 'mean'), lds=('lds', 'mean'), lis=('lis', 'mean'), planar=('planar', 'mean'),
        foreign_per_line=('foreign_per_line', 'mean'), L=('L', 'median'))
    print(summ.round(3).to_string())
    rng = np.random.default_rng(1)

    def test(metric, arm, transform):
        # paired on boards: mean over attempts (seeds) of the metric, arm minus control
        c = per[per.arm == ctrl].groupby('board')[metric].mean().apply(transform)
        x = per[per.arm == arm].groupby('board')[metric].mean().apply(transform)
        j = pd.concat([c.rename('c'), x.rename('x')], axis=1).dropna()
        if not len(j):
            return None
        dif = (j.x - j.c).values
        obs = dif.mean()
        signs = rng.choice([-1.0, 1.0], size=(20000, len(dif)))
        null = (signs * dif).mean(axis=1)
        p = float((np.abs(null) >= abs(obs) - 1e-12).mean())
        return dict(boards=len(j), mean_diff=round(float(obs), 4), p=round(p, 4))
    print('\nPaired sign-flip tests against control, per board mean over seeds')
    for arm in arms:
        if arm == ctrl:
            continue
        print(arm)
        print('  log1p(bus open lines):', test('lines_open', arm, np.log1p))
        print('  log(vias per bus line + 0.1):', test('vias_per_line', arm, lambda x: np.log(x + 0.1)))
        print('  log1p(foreign crossings per line):', test('foreign_per_line', arm, np.log1p))
        print('  lds:', test('lds', arm, lambda x: x), ' planar share:', test('planar', arm, lambda x: x), 'L (log):', test('L', arm, np.log))


if __name__ == '__main__':
    main()
