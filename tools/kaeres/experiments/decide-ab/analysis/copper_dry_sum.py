"""Hazard counts per copper-ab arm from copper_dry.sh reports ($KAE_AB_WORK/cdry/<id>/rep-<arm>.json)."""
import os
import json, glob, collections, os
arms = ['default', 'rail_over_cap=1', 'via_A=1.0']
tot = {a: collections.Counter() for a in arms}; maxdt = {a: 0.0 for a in arms}; differ = collections.Counter()
for d in sorted(glob.glob(os.path.expandvars('$KAE_AB_WORK/') + 'cdry/*/')):
    per = {}
    for a in arms:
        f = d + f'rep-{a}.json'
        if not os.path.exists(f): continue
        acc = collections.Counter()
        def walk(x):
            if isinstance(x, dict):
                if 'code' in x and 'severity' in x:
                    acc[f"{x['code']}:{x['severity']}"] += 1
                    if x['code'] == 'copper_below_ipc_width':
                        ev = x.get('evidence') or {}
                        for k, v in ev.items():
                            if 'dT_ipc2152' in k and isinstance(v, (int, float)): maxdt[a] = max(maxdt[a], v)
                for v in x.values(): walk(v)
            elif isinstance(x, list):
                for v in x: walk(v)
        walk(json.load(open(f))); per[a] = acc; tot[a].update(acc)
    if 'default' in per:
        for a in arms[1:]:
            if a in per and per[a] != per['default']: differ[a] += 1
print('boards', len(glob.glob(os.path.expandvars('$KAE_AB_WORK/') + 'cdry/*/rep-default.json')), 'boards where the arm changes hazards', dict(differ))
for a in arms:
    print(a, 'max dT_ipc2152', maxdt[a], {k: v for k, v in tot[a].most_common() if not k.startswith('drc_')})
