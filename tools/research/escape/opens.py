# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Opens at dense-package pins across boards: opens.py -> opens.json + summary."""
import json, gzip, os, sys, math
from collections import Counter, defaultdict
sys.path.insert(0, os.path.dirname(__file__))
import pkg
D = os.path.join(os.environ.get('ESC_WORK', '.'), 'dump')
boards = json.load(open(os.environ.get('BOARDS_JSON', 'boards.json')))
rows = []
tot = Counter()
for b in boards:
    name = b['board']
    hp = f'{D}/{name}.human.json'
    if not os.path.exists(hp):
        continue
    H = pkg.load(hp)
    cls = {fp['ref']: pkg.classify(fp) for fp in H['fps']}
    for kind in ('route', 'joint'):
        r = b.get(kind) or {}
        if not r.get('run') or not r.get('unconnected'):
            continue
        f = r['run'] + '/evals/98dc632c1679.drc.json.gz'
        if not os.path.exists(f):
            continue
        rep = json.load(gzip.open(f))
        for u in rep['unconnected_items']:
            its = [pkg.parse_item(i['description']) for i in u['items']]
            dense = []
            for it, raw in zip(its, u['items']):
                if it['kind'] == 'pad':
                    c = cls.get(it['ref'])
                    if c and c['dense'] and it['n'] in c.get('sig', ()):
                        dense.append(dict(ref=it['ref'], n=it['n'], net=it['net'], pkg=c['kind'], pitch=c['pitch'],
                                          ring=c['rings'].get(it['n']), fpid=c['fpid'], nsig=c['nsig'],
                                          pos=raw['pos']))
            net = next((i['net'] for i in its if i.get('net')), None)
            rows.append(dict(board=name, run=kind, net=net, items=[i['kind'] for i in its], dense=dense,
                             pos=[(i['pos']['x'], i['pos']['y']) for i in u['items']]))
json.dump(rows, open(os.path.join(os.environ.get('ESC_WORK', '.'), 'opens.json'), 'w'))
# summary
for kind in ('route', 'joint'):
    R = [r for r in rows if r['run'] == kind]
    nb = len({r['board'] for r in R}); nd = [r for r in R if r['dense']]
    print(f'{kind}: {len(R)} opens on {nb} boards; at a dense pin: {len(nd)} on {len({r["board"] for r in nd})} boards')
    c = Counter(); cb = defaultdict(set)
    for r in nd:
        k = sorted({d['pkg'] for d in r['dense']})[0]
        c[k] += 1; cb[k].add(r['board'])
    print('  by pkg', {k: (v, len(cb[k])) for k, v in c.items()})
    per = Counter(r['board'] for r in R); perd = Counter(r['board'] for r in nd)
    for bname, n in per.most_common():
        print(f'   {bname[:60]:60s} open={n:5d} dense={perd[bname]:5d}')
