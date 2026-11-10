#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Summary of legal_turns.py output on the campaign's moved buses. Usage: legal_summary.py ALL.pkl OUT_GLOB"""
import glob, json, sys
import numpy as np, pandas as pd

d = pd.read_pickle(sys.argv[1])
M = d[d.method.str.contains('kae-staged-decide-control') & (d.legal != False) & (d.n >= 6)]  # noqa
hk = d[d.human].set_index(['board', 'bus'])[['L', 'a_rot', 'b_rot']]
j = M.join(hk, on=['board', 'bus'], rsuffix='_h', how='inner')
mv = (abs(j.L / j.L_h - 1) > .005) | (j.a_rot != j.a_rot_h) | (j.b_rot != j.b_rot_h)
moved = set(zip(j[mv].board, j[mv].run, j[mv].bus, j[mv].level))
moved_b = {(b, bus, lv) for b, _, bus, lv in moved}
rows = [json.loads(l) for f in glob.glob(sys.argv[2]) for l in open(f)]
R = pd.DataFrame(rows)
R['human'] = R.run.str.startswith('human')
R['moved'] = [((r.job, r.run, r.bus, r.level) in moved) if not r.human else ((r.job, r.bus, r.level) in moved_b) for r in R.itertuples()]
R = R[R.moved]


def side(s):
    return s['status'] in ('same', 'legal')


def phys_bad(s):
    return s['status'] == 'legal' and s.get('physics', 0) > 1e-9


for who, G in (('kae staged', R[~R.human]), ('human', R[R.human])):
    bl = G.best_lis
    turn = bl.map(lambda x: x['a']['status'] != 'same' or x['b']['status'] != 'same')
    legal = bl.map(lambda x: side(x['a']) and side(x['b']))
    nud1 = bl.map(lambda x: max(x['a'].get('nudge', 0) or 0, x['b'].get('nudge', 0) or 0) <= 1.0)
    veto = bl.map(lambda x: phys_bad(x['a']) or phys_bad(x['b']))
    fixed = bl.map(lambda x: 'fixed' in (x['a']['status'], x['b']['status']))
    grid = bl.map(lambda x: 'grid' in (x['a']['status'], x['b']['status']))
    exact = bl.map(lambda x: 'exact' in (x['a']['status'], x['b']['status']))
    T = turn
    lis_best = bl.map(lambda x: x['lis'])
    lis_legal = [b['lis'] if (lg and n1) else l0 for b, lg, n1, l0 in zip(bl, legal, nud1, G.lis0)]
    lis_lp = [b['lis'] if (lg and n1 and not v) else l0 for b, lg, n1, v, l0 in zip(bl, legal, nud1, veto, G.lis0)]
    print(f'## {who}: {len(G)} bus-runs ({G.job.nunique()} boards); best-planarity pair needs a turn on {T.sum()}')
    print(f'  of those: legal (grid + exact, nudge <= 2 mm) {(legal & T).sum()}, nudge <= 1 mm {(legal & nud1 & T).sum()}; '
          f'end fixed {(fixed & T).sum()}, grid collision {(grid & T).sum()}, exact finding {(exact & T).sum()}; '
          f'legal but physics worse {(legal & nud1 & veto & T).sum()}, legal and physics not worse {(legal & nud1 & ~veto & T).sum()}')
    print(f'  fully planar: now {(G.lis0 >= .999).mean():.2f}, best turn {(lis_best >= .999).mean():.2f}, legal turns {(np.array(lis_legal) >= .999).mean():.2f}, '
          f'legal and physics not worse {(np.array(lis_lp) >= .999).mean():.2f}; median LIS {G.lis0.median():.2f} -> {lis_best.median():.2f} / {np.median(lis_legal):.2f} / {np.median(lis_lp):.2f}')
    ll = G.legal_lis.map(lambda x: x['lis'] if isinstance(x, dict) else np.nan)
    print(f'  best legal pair of any rank (nudge <= 1 mm, physics ignored): fully planar {(ll.fillna(G.lis0) >= .999).mean():.2f}, median LIS {ll.fillna(G.lis0).median():.2f}')
