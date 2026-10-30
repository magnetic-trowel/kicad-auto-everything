# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""For row-package pins: first foreign copper in the straight outward corridor and in the
inward one, route vs human, open vs connected."""
import json, sys, os, math
from collections import Counter, defaultdict
sys.path.insert(0, os.path.dirname(__file__))
from filt import pins
from sites import segd
P, cap, bad = pins()
D = os.path.join(os.environ.get('ESC_WORK', '.'), 'dump')
def first_block(B, pd, d, net, half, L=2.0, step=0.05):
    layer = pd['layers'][0]
    ext = (abs(d[0]) * pd['sx'] + abs(d[1]) * pd['sy']) / 2 if abs(pd['rot']) % 180 < 1 else (abs(d[0]) * pd['sy'] + abs(d[1]) * pd['sx']) / 2
    k = 0
    cand_t = [t for t in B['tracks'] if t['l'] == layer and t['net'] != net and min(math.hypot(t['x1']-pd['x'],t['y1']-pd['y']), math.hypot(t['x2']-pd['x'],t['y2']-pd['y']), segd(pd['x'],pd['y'],t)) < L + 3]
    cand_v = [v for v in B['vias'] if v['net'] != net and math.hypot(v['x']-pd['x'], v['y']-pd['y']) < L + 1]
    while k * step <= L:
        s = ext + k * step
        x, y = pd['x'] + d[0] * s, pd['y'] + d[1] * s
        for t in cand_t:
            if segd(x, y, t) < half + t['w'] / 2:
                return round(s - ext, 2), 'track', t['net'], t['w']
        for v in cand_v:
            if math.hypot(v['x'] - x, v['y'] - y) < half + v['d'] / 2:
                return round(s - ext, 2), 'via', v['net'], v['d']
        k += 1
    return None
sel = defaultdict(list)
for p in P:
    if p['pkg'] in ('qfn', 'qfp', 'connector', 'other-smd') and not p['zone_net']: sel[p['board']].append(p)
res = defaultdict(Counter); dist = defaultdict(list)
ex = []
for b, ps in sel.items():
    for kind in ('human', 'route'):
        B = json.load(open(f'{D}/{b}.{kind}.json'))
        fps = {f['ref']: f for f in B['fps']}
        for p in ps:
            f = fps[p['ref']]
            pd = next(q for q in f['pads'] if q['n'] == p['n'])
            # outward axis: dominant axis of pad - footprint centre (signal pads' centroid)
            sig = [q for q in f['pads'] if q['n'] in {pp['n'] for pp in ps if pp['ref'] == p['ref']}] or f['pads']
            cx = sum(q['x'] for q in f['pads']) / len(f['pads']); cy = sum(q['y'] for q in f['pads']) / len(f['pads'])
            ox, oy = pd['x'] - cx, pd['y'] - cy
            d = ((1 if ox > 0 else -1), 0) if abs(ox) >= abs(oy) else (0, (1 if oy > 0 else -1))
            fb = first_block(B, pd, d, p['net'], 0.05 + 0.1)
            fi = first_block(B, pd, (-d[0], -d[1]), p['net'], 0.05 + 0.1)
            key = (kind, 'open' if p['open'] else 'ok')
            o = 'out blocked<0.5' if fb and fb[0] < 0.5 else 'out free 0.5'
            i = 'in blocked<0.5' if fi and fi[0] < 0.5 else 'in free 0.5'
            res[key][o + ' & ' + i] += 1
            if kind == 'route' and p['open'] and len(ex) < 400: ex.append((b[:30], p['ref'], p['n'], p['net'], fb, fi))
for k in sorted(res):
    n = sum(res[k].values()); print(k, n, {a: f'{100*v/n:.0f}%' for a, v in res[k].most_common()})
json.dump(ex, open(os.path.join(os.environ.get('ESC_WORK', '.'), 'corridor_ex.json'), 'w'))
for e in ex[:40]: print(e)
