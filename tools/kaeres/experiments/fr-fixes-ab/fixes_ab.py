# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""fr-fixes-ab against its pre-registered rule (tools/kaeres/experiments/fr-fixes-ab/PLAN.md)."""
import collections
import glob
import gzip
import hashlib
import json
import os
import random
import re
import statistics as st
from math import comb

BASE = os.path.expanduser('~/kae-baselines/')
EXP = 'fr-fixes-ab'
D = os.path.join(os.path.dirname(os.path.abspath(__file__)), '')   # the board lists beside this script
sel = open(D + 'selected.txt').read().split()
uns = open(D + 'unselected.txt').read().split()
ARMS = {'fr-fork-2e1125a-nomp-fx': 'ctl', 'fr-fork-c219253-nomp-fx': 'fix'}


def ses_hash(r):
    try:
        lines = gzip.open(r + '/board.ses.gz', 'rt', errors='replace').read().splitlines()
    except OSError:
        return None
    keep = [ln for ln in lines if not re.match(r'\s*\((session|host_cad|host_version)', ln)]
    return hashlib.md5('\n'.join(keep).encode()).hexdigest()


def load(b, slug):
    for r in glob.glob(f'{BASE}boards/{b}/runs/{slug}.*.a0'):
        j = json.load(open(r + '/run.json'))
        if j.get('experiment') != EXP:
            continue
        s = None
        for ev in glob.glob(r + '/evals/*.json'):
            x = json.load(open(ev))
            if x.get('score'):
                s = x['score']
        rr = json.load(open(r + '/router-report.json')) if os.path.exists(r + '/router-report.json') else {}
        log = gzip.open(r + '/adapter.log.gz', 'rt', errors='replace').read()
        return dict(s=s or {}, state=rr.get('final_state'), cpu=(rr.get('resource_usage') or {}).get('cpu_time'),
                    runtime=j.get('runtime_s'), ses=ses_hash(r), status=j.get('status'),
                    poly=log.count('Polyline: must contain'),
                    repair=(re.findall(r'Pour cut-off repair: [^\n]*', log) or [None])[-1],
                    connected=sum(int(x) for x in re.findall(r'Connected (\d+) group', log)))
    return None


def mcnemar(b, c):
    n = b + c
    k = min(b, c)
    return min(1.0, 2 * sum(comb(n, i) for i in range(k + 1)) / 2 ** n) if n else 1.0


def flip(d, n=20000):
    random.seed(1)
    obs = abs(sum(d))
    if obs == 0:
        return 1.0
    hits = sum(1 for _ in range(n) if abs(sum(x if random.random() < .5 else -x for x in d)) >= obs)
    return (hits + 1) / (n + 1)


data = {}
for b in sel + uns:
    a = {arm: load(b, slug) for slug, arm in ARMS.items()}
    if a['ctl'] and a['fix'] and a['ctl']['s'] and a['fix']['s']:
        data[b] = a
print('paired', len(data), 'of', len(sel) + len(uns), 'missing', [b for b in sel + uns if b not in data][:10])

for name, pop in (('SELECTED', sel), ('UNSELECTED', uns)):
    P = [(b, data[b]) for b in pop if b in data]
    C = [a['ctl'] for _, a in P]
    F = [a['fix'] for _, a in P]
    to_c = [x['state'] == 'TIMED_OUT' for x in C]
    to_f = [x['state'] == 'TIMED_OUT' for x in F]
    b_ = sum(1 for x, y in zip(to_c, to_f) if x and not y)
    c_ = sum(1 for x, y in zip(to_c, to_f) if y and not x)
    oc = sum(x['s'].get('unconnected', 0) for x in C)
    of = sum(x['s'].get('unconnected', 0) for x in F)
    cl_c = sum(bool(x['s'].get('clean')) for x in C)
    cl_f = sum(bool(x['s'].get('clean')) for x in F)
    comp_c = st.mean(x['s'].get('completion', 0) for x in C)
    comp_f = st.mean(x['s'].get('completion', 0) for x in F)
    cpu_c = [x['cpu'] for x in C if x['cpu'] is not None]
    cpu_f = [x['cpu'] for x in F if x['cpu'] is not None]
    d_open = [y['s'].get('unconnected', 0) - x['s'].get('unconnected', 0) for x, y in zip(C, F)]
    same = sum(1 for x, y in zip(C, F) if x['ses'] and x['ses'] == y['ses'])
    print(f'\n== {name}: n={len(P)}')
    print(f'timeouts {sum(to_c)} -> {sum(to_f)} (only ctl {b_}, only fix {c_}, McNemar p {mcnemar(b_, c_):.2g})')
    print(f'opens {oc} -> {of} ({100 * (of / max(oc, 1) - 1):+.1f}%), boards better/worse/equal '
          f'{sum(x < 0 for x in d_open)}/{sum(x > 0 for x in d_open)}/{sum(x == 0 for x in d_open)}, flip p {flip(d_open):.3f}')
    print(f'cp1 {cl_c} -> {cl_f}; completion {comp_c:.4f} -> {comp_f:.4f}')
    print(f'router CPU median {st.median(cpu_c):.1f} -> {st.median(cpu_f):.1f} s; total {sum(cpu_c) / 3600:.1f} -> {sum(cpu_f) / 3600:.1f} h')
    print(f'identical sessions {same}/{len(P)}; polyline storms (>1e4) {sum(x["poly"] > 1e4 for x in C)} -> {sum(x["poly"] > 1e4 for x in F)}; '
          f'pour groups connected {sum(x["connected"] for x in C)} -> {sum(x["connected"] for x in F)}; '
          f'repair budget bound {sum(1 for x in F if x["repair"] and "work budget" in x["repair"])}')
    T = collections.Counter()
    U = collections.Counter()
    for x in C:
        T.update(x['s'].get('errors_by_type') or {})
    for x in F:
        U.update(x['s'].get('errors_by_type') or {})
    print(f'DRC errors {sum(T.values())} -> {sum(U.values())}')
    for t in sorted(set(T) | set(U), key=lambda t: -(T[t] + U[t])):
        if max(T[t], U[t]) >= 30 or t == 'hole_to_hole':
            d = [(y['s'].get('errors_by_type') or {}).get(t, 0) - (x['s'].get('errors_by_type') or {}).get(t, 0) for x, y in zip(C, F)]
            ratio = U[t] / T[t] if T[t] else float('inf')
            flag = ' FAIL' if (ratio > 1.25 and flip(d) < 0.05 and sum(d) > 0) else ''
            print(f'   {t}: {T[t]} -> {U[t]} ({100 * (ratio - 1):+.0f}%), boards worse {sum(v > 0 for v in d)} better {sum(v < 0 for v in d)}, flip p {flip(d):.3f}{flag}')
    if name == 'UNSELECTED':
        worst = sorted(P, key=lambda p: -(p[1]['fix']['s'].get('unconnected', 0) - p[1]['ctl']['s'].get('unconnected', 0)))[:8]
        for b, a in worst:
            print('   worst', b[:44], a['ctl']['s'].get('unconnected'), '->', a['fix']['s'].get('unconnected'),
                  a['ctl']['state'], '->', a['fix']['state'], 'same ses', a['ctl']['ses'] == a['fix']['ses'])
        for b, a in P:
            if a['fix']['state'] == 'TIMED_OUT' and a['ctl']['state'] != 'TIMED_OUT':
                print('   NEW TIMEOUT', b, a['ctl']['state'], a['ctl']['runtime'], a['fix']['runtime'], a['fix']['repair'])

P = [(b, data[b]) for b in uns if b in data]
diff = [(b, a['ctl']['state'], a['fix']['state']) for b, a in P if a['ctl']['ses'] != a['fix']['ses']]
print('\nunselected boards with different sessions:', diff)
