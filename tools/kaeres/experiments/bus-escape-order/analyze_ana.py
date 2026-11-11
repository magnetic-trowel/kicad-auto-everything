#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""bus-escape-order-2: whole-board opens, DRC by type, completion, CPU, router start and escapes laid per arm, paired against
the control, by stratum (router on time in every arm; control finished 2 Freerouting passes). Writes meta.json and late.json in the cwd."""
import csv, json, gzip, re, os, random, sys
from collections import Counter, defaultdict
from pathlib import Path
EXP = Path(os.path.expanduser('~/kae-baselines/experiments/bus-escape-order-2'))
NAME = {"be-control 900": "control900", "be-plan 900": "plan900", "be-bus 900": "bus900", "be-buswall 900": "buswall900",
        "be-control 300": "control300", "be-plan 300": "plan300", "be-bus 300": "bus300"}
rows = {}
for r in csv.DictReader(open(EXP / 'results.csv')):
    m = r['method']
    arm = next((v for k, v in NAME.items() if k in m), None)
    if arm: rows[(r['board'], arm)] = r
PL = re.compile(r'\] plan: .*\(([\d.]+)s\)$')
FR = re.compile(r'freerouting: rc=\S+ ([\d.]+)s state=(\S+)')
def logmeta(b, run):
    p = Path(os.path.expanduser(f'~/kae-baselines/boards/{b}/runs/{run}/adapter.log.gz'))
    out = dict(start=None, fr_s=None, state=None, loops=None, esc=None)
    if not p.exists(): return out
    for line in gzip.open(p, 'rt', errors='replace'):
        if (m := PL.search(line.strip())): out['start'] = float(m.group(1))
        elif (m := FR.search(line)): out['fr_s'], out['state'] = float(m.group(1)), m.group(2)
        elif line.startswith('{"input"'):
            try:
                rep = json.loads(line)
                tel = (((rep.get('router') or {}).get('report') or {}).get('telemetry') or {}).get('loops') or []
                out['loops'] = len(tel[0]['unrouted']) if tel else 0
                pk = (rep.get('escape') or {}).get('packages') or []
                out['esc'] = (sum(p.get('planned') or 0 for p in pk), sum(p.get('laid') or 0 for p in pk))
                out['wt'] = rep.get('wire_types')
            except Exception: pass
    return out
meta = {}
cache = Path('meta.json')
if cache.exists(): meta = {tuple(k.split('|')): v for k, v in json.load(open(cache)).items()}
for (b, a), r in rows.items():
    if (b, a) not in meta: meta[(b, a)] = logmeta(b, r['run'])
json.dump({'|'.join(k): v for k, v in meta.items()}, open(cache, 'w'))
boards = sorted({b for b, a in rows})
def unc(b, a):
    r = rows.get((b, a))
    if not r: return None
    if r['status'] != 'ok' or r['valid'] != 'True' or r['unconnected'] in ('', None): return float(r['start_unconnected'] or 0)   # no output: nothing routed
    return float(r['unconnected'])
def err(b, a):
    r = rows.get((b, a))
    return json.loads(r['errors_by_type'] or '{}') if r and r['status'] == 'ok' and r['errors_by_type'] else {}
def boot_ratio(pairs, n=2000, seed=1234):
    rng = random.Random(seed); s = []
    for _ in range(n):
        smp = [pairs[rng.randrange(len(pairs))] for _ in pairs]
        a = sum(x for x, _ in smp); bb = sum(y for _, y in smp)
        if a: s.append(bb / a)
    s.sort(); A = sum(x for x, _ in pairs); B = sum(y for _, y in pairs)
    return B / A if A else None, s[int(.025 * len(s))], s[int(.975 * len(s)) - 1]
# late start: router started after 25% of budget
late = {b for b in boards for a in NAME.values() if (m := meta.get((b, a))) and m.get('start') and m['start'] > 0.25 * (900 if '900' in a else 300)}
print('boards with a late router start (>25% budget) in any arm:', len(late))
starts = defaultdict(list)
for (b, a), m in meta.items():
    if m.get('start') is not None: starts[a].append(m['start'])
for a, v in sorted(starts.items()):
    v.sort(); print(f'  router start {a}: median {v[len(v)//2]:.0f}s p90 {v[int(.9*len(v))]:.0f}s max {v[-1]:.0f}s')
ctrl_passes = {b: (meta.get((b, 'control900')) or {}).get('loops') for b in boards}
def report(sel, title):
    print(f'\n## {title} ({len(sel)} boards)')
    for base, arms in (('control900', ['plan900', 'bus900', 'buswall900']), ('control300', ['plan300', 'bus300']), ('bus900', ['buswall900']), ('plan900', ['bus900']), ('plan300', ['bus300'])):
        for a in arms:
            pr = [(unc(b, base), unc(b, a)) for b in sel if unc(b, base) is not None and unc(b, a) is not None]
            if not pr: continue
            r, lo, hi = boot_ratio(pr)
            ea = sum(sum(err(b, base).values()) for b in sel); eb = sum(sum(err(b, a).values()) for b in sel)
            better = sum(1 for x, y in pr if y < x); worse = sum(1 for x, y in pr if y > x)
            print(f'  {a} vs {base}: opens {sum(x for x,_ in pr):.0f} -> {sum(y for _,y in pr):.0f} ratio {r:.3f} [{lo:.3f}, {hi:.3f}]  boards better/worse {better}/{worse}  errors {ea} -> {eb}')
report(boards, 'all')
report([b for b in boards if b not in late], 'router started on time in every arm')
report([b for b in boards if (ctrl_passes.get(b) or 0) >= 2], 'control finished >= 2 Freerouting passes')
report([b for b in boards if (ctrl_passes.get(b) or 0) < 2], 'control < 2 passes')
print('\n## DRC errors by type, sum over boards')
types = Counter()
for a in NAME.values():
    c = Counter()
    for b in boards: c.update(err(b, a))
    types[a] = c
allk = sorted({k for c in types.values() for k in c}, key=lambda k: -sum(types[a][k] for a in types))
print('type | ' + ' | '.join(NAME.values()))
for k in allk[:14]: print(k, '|', ' | '.join(str(types[a][k]) for a in NAME.values()))
print('\n## completion mean, cp1, CPU h, no-output, timeouts')
for a in NAME.values():
    rs = [rows[(b, a)] for b in boards if (b, a) in rows]
    comp = [float(r['completion'] or 0) for r in rs]; cpu = [float(r['cpu_s'] or 0) for r in rs]
    print(f"  {a}: completion {sum(comp)/len(comp):.3f}, clean {sum(r['clean']=='True' for r in rs)}, CPU {sum(cpu)/3600:.1f} h, no-output {sum(r['status']!='ok' or r['valid']!='True' for r in rs)}, timed_out {sum(r['timed_out']=='True' for r in rs)}")
print('\n## escapes planned / laid (sum)')
for a in NAME.values():
    pl = sum((meta.get((b, a)) or {}).get('esc', (0, 0))[0] for b in boards if (meta.get((b, a)) or {}).get('esc'))
    ld = sum((meta.get((b, a)) or {}).get('esc', (0, 0))[1] for b in boards if (meta.get((b, a)) or {}).get('esc'))
    print(f'  {a}: planned {pl}, laid {ld}')
json.dump(sorted(late), open('late.json', 'w'))
