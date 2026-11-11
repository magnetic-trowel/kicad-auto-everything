#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""bus-escape-order-2: bus lanes open (grid-end buses of the B1 bus list, lanes open in the human view excluded) from each run's
scoring DRC, on boards whose unconnected list is complete (under 499 items in every arm). Run analyze_ana.py first (meta.json, late.json)."""
import csv, json, gzip, re, os, random
from pathlib import Path
from collections import defaultdict
B1 = os.environ['B1_WORK']   # bus-alone-b1's work directory: busnets/, views/
NET = re.compile(r'\[(.*?)\](?= of | on |\s*$)')
EXP = Path(os.path.expanduser('~/kae-baselines/experiments/bus-escape-order-2'))
NAME = {"be-control 900": "control900", "be-plan 900": "plan900", "be-bus 900": "bus900", "be-buswall 900": "buswall900",
        "be-control 300": "control300", "be-plan 300": "plan300", "be-bus 300": "bus300"}
rows = {}
for r in csv.DictReader(open(EXP / 'results.csv')):
    arm = next((v for k, v in NAME.items() if k in r['method']), None)
    if arm: rows[(r['board'], arm)] = r
boards = sorted({b for b, _ in rows})
late = set(json.load(open('late.json')))
meta = {tuple(k.split('|')): v for k, v in json.load(open('meta.json')).items()}
grid = lambda t: any(k in (t or '') for k in ('bga', 'grid'))
out = {}
for b in boards:
    d = json.load(open(f'{B1}/busnets/{b}.buses.json'))
    lanes = [ln for bus in d['buses'] if grid(bus.get('a_type')) or grid(bus.get('b_type')) for ln in bus['nets']]
    hv = Path(f'{B1}/views/{b}.human.json')
    hum = json.load(open(hv)).get('opens', {}) if hv.exists() else {}
    lanes = [ln for ln in lanes if not any(hum.get(n) for n in ln)]
    for a in NAME.values():
        r = rows.get((b, a))
        if not r: continue
        if r['status'] != 'ok' or r['valid'] != 'True':
            out[(b, a)] = dict(open=len(lanes), lanes=len(lanes), capped=False, nooutput=True); continue
        run = Path(os.path.expanduser(f'~/kae-baselines/boards/{b}/runs/{r["run"]}/evals'))
        f = next(run.glob('afa09d34bc94.drc.json.gz'), None)
        dr = json.load(gzip.open(f))
        u = dr.get('unconnected_items', [])
        nets = set()
        for it in u:
            for x in it.get('items', []):
                m = NET.search(x.get('description', ''))
                if m: nets.add(m.group(1))
        out[(b, a)] = dict(open=sum(1 for ln in lanes if any(n in nets for n in ln)), lanes=len(lanes), capped=len(u) >= 499, nooutput=False)
def boot(pairs, n=2000, seed=1234):
    rng = random.Random(seed); s = []
    for _ in range(n):
        smp = [pairs[rng.randrange(len(pairs))] for _ in pairs]; A = sum(x for x, _ in smp)
        if A: s.append(sum(y for _, y in smp) / A)
    s.sort(); A = sum(x for x, _ in pairs)
    return sum(y for _, y in pairs) / A, s[int(.025 * len(s))], s[int(.975 * len(s)) - 1]
capped = {b for (b, a), v in out.items() if v['capped']}
two = {b for b in boards if ((meta.get((b, 'control900')) or {}).get('loops') or 0) >= 2}
print('boards with grid-end bus lanes:', sum(1 for b in boards if out.get((b,'control900'),{}).get('lanes')), 'capped DRC lists (any arm):', len(capped))
for title, sel in (('uncapped boards', [b for b in boards if b not in capped]), ('uncapped, router on time', [b for b in boards if b not in capped and b not in late]),
                   ('uncapped, control >= 2 passes', [b for b in boards if b not in capped and b in two]), ('uncapped, control < 2 passes', [b for b in boards if b not in capped and b not in two])):
    print(f'\n## bus lanes open (grid-end buses), {title}: {len(sel)} boards, {sum(out[(b,"control900")]["lanes"] for b in sel if (b,"control900") in out)} lanes')
    for base, a in (('control900', 'plan900'), ('control900', 'bus900'), ('control900', 'buswall900'), ('control300', 'plan300'), ('control300', 'bus300'), ('plan900', 'bus900'), ('plan300', 'bus300'), ('bus900', 'buswall900')):
        pr = [(out[(b, base)]['open'], out[(b, a)]['open']) for b in sel if (b, base) in out and (b, a) in out]
        if not pr or not sum(x for x, _ in pr): continue
        r, lo, hi = boot(pr)
        print(f'  {a} vs {base}: {sum(x for x,_ in pr)} -> {sum(y for _,y in pr)}  ratio {r:.3f} [{lo:.3f}, {hi:.3f}]  boards better/worse {sum(1 for x,y in pr if y<x)}/{sum(1 for x,y in pr if y>x)}')
json.dump({'|'.join(k): v for k, v in out.items()}, open('lanes.json', 'w'))
