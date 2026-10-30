# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""What occupies the 4 dog-bone via sites (diagonal gaps) of each BGA ball, human vs route."""
import json, sys, os, math
from collections import Counter, defaultdict
sys.path.insert(0, os.path.dirname(__file__))
import pkg, esc
from filt import pins
P, cap, bad = pins()
D = os.path.join(os.environ.get('ESC_WORK', '.'), 'dump')
def segd(px, py, t):
    ax, ay, bx, by = t['x1'], t['y1'], t['x2'], t['y2']
    dx, dy = bx - ax, by - ay; L = dx * dx + dy * dy
    u = 0 if L == 0 else max(0, min(1, ((px - ax) * dx + (py - ay) * dy) / L))
    return math.hypot(ax + u * dx - px, ay + u * dy - py)
def occupant(B, x, y, layer, net, r):
    vs = [v for v in B['vias'] if math.hypot(v['x'] - x, v['y'] - y) < r]
    if vs:
        return 'own via' if any(v['net'] == net for v in vs) else 'foreign via'
    ts = [t for t in B['tracks'] if t['l'] == layer and segd(x, y, t) < r * 0.75]
    if ts:
        if any(t['net'] == net for t in ts): return 'own track'
        return 'foreign track'
    return 'free'
sel = defaultdict(list)
for p in P:
    if p['pkg'] == 'bga': sel[p['board']].append(p)
tot = {'human': defaultdict(Counter), 'route': defaultdict(Counter)}
for b, ps in sel.items():
    for kind in ('human', 'route'):
        B = json.load(open(f'{D}/{b}.{kind}.json'))
        fps = {f['ref']: f for f in B['fps']}
        for p in ps:
            f = fps[p['ref']]
            pd = next(q for q in f['pads'] if q['n'] == p['n'])
            h = p['pitch'] / 2
            occ = Counter()
            for sx in (-1, 1):
                for sy in (-1, 1):
                    occ[occupant(B, pd['x'] + sx * h, pd['y'] + sy * h, pd['layers'][0], p['net'], h * 0.7)] += 1
            key = ('open' if p['open'] else 'ok', 'inner' if (p['ring'] or 0) >= 2 else 'outer')
            if p['zone_net'] and (p['ring'] or 0) >= 5: key = (key[0], 'centre-power')
            for k, v in occ.items(): tot[kind][key][k] += v
for kind in tot:
    print(kind)
    for k, c in sorted(tot[kind].items()):
        n = sum(c.values()); print('  ', k, n, {a: f'{100*v/n:.0f}%' for a, v in c.most_common()})
