# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Walls: foreign tracks on a row package's pad layer that cross the escape corridors (pad
tip out to BAND mm, both sides) of >= 3 signal pins. Human vs route, and opens."""
import json, sys, os, math
from collections import Counter, defaultdict
sys.path.insert(0, os.path.dirname(__file__))
from filt import pins
P, cap, bad = pins()
D = os.path.join(os.environ.get('ESC_WORK', '.'), 'dump')
BAND = float(os.environ.get('BAND', '1.0'))
def seg_rect_hit(t, rect):
    # rect: (cx, cy, ux, uy, hl, hw) oriented rectangle centre, axis u (length hl along u), half width hw
    cx, cy, ux, uy, hl, hw = rect
    # sample the segment
    n = max(2, int(math.dist((t['x1'], t['y1']), (t['x2'], t['y2'])) / 0.02))
    for k in range(n + 1):
        x = t['x1'] + (t['x2'] - t['x1']) * k / n; y = t['y1'] + (t['y2'] - t['y1']) * k / n
        dx, dy = x - cx, y - cy
        a = dx * ux + dy * uy; b = -dx * uy + dy * ux
        if abs(a) <= hl and abs(b) <= hw + t['w'] / 2: return True
    return False
sel = defaultdict(list)
for p in P:
    if p['pkg'] in ('qfn', 'qfp', 'connector', 'other-smd'): sel[(p['board'], p['ref'])].append(p)
res = Counter(); per = defaultdict(Counter)
for (b, ref), ps in sel.items():
    for kind in ('human', 'route'):
        B = json.load(open(f'{D}/{b}.{kind}.json'))
        f = next(x for x in B['fps'] if x['ref'] == ref)
        cx = sum(q['x'] for q in f['pads']) / len(f['pads']); cy = sum(q['y'] for q in f['pads']) / len(f['pads'])
        nets = {p['net'] for p in ps}
        rects = []
        for p in ps:
            pd = next((q for q in f['pads'] if q['n'] == p['n']), None)
            if pd is None or not pd['layers']: continue
            ox, oy = pd['x'] - cx, pd['y'] - cy
            ux, uy = ((1 if ox > 0 else -1), 0) if abs(ox) >= abs(oy) else (0, (1 if oy > 0 else -1))
            along = max(pd['sx'], pd['sy']) / 2
            for s in (1, -1):
                c = (pd['x'] + s * ux * (along + BAND / 2), pd['y'] + s * uy * (along + BAND / 2))
                rects.append((p, s, pd['layers'][0], (c[0], c[1], ux, uy, BAND / 2, p['pitch'] / 2 * 0.5)))
        lays = {r[2] for r in rects}
        bb = (min(r[3][0] for r in rects) - 2, min(r[3][1] for r in rects) - 2, max(r[3][0] for r in rects) + 2, max(r[3][1] for r in rects) + 2)
        cand = [t for t in B['tracks'] if t['l'] in lays and not (max(t['x1'], t['x2']) < bb[0] or min(t['x1'], t['x2']) > bb[2] or max(t['y1'], t['y2']) < bb[1] or min(t['y1'], t['y2']) > bb[3])]
        hits = defaultdict(set)    # track idx -> pins whose corridor it crosses (not its own net)
        for i, t in enumerate(cand):
            for p, s, l, rc in rects:
                if t['l'] == l and t['net'] != p['net'] and seg_rect_hit(t, rc):
                    hits[i].add((p['n'], s))
        walled = defaultdict(set)
        for i, hs in hits.items():
            sides = Counter(s for _, s in hs)
            for s, n in sides.items():
                if n >= 3:
                    for pn, ss in hs:
                        if ss == s: walled[pn].add(s)
        for p in ps:
            w = walled.get(p['n'], set())
            k = 'both' if len(w) == 2 else ('one' if w else 'none')
            res[(kind, p['open'], k)] += 1
            per[(b[:30], ref, kind)][k] += 1
for kind in ('human', 'route'):
    for op in (False, True):
        tot = sum(v for (k, o, _), v in res.items() if k == kind and o == op)
        print(kind, 'open' if op else 'ok', tot, {w: f'{100*res[(kind, op, w)]/tot:.0f}%' for w in ('none', 'one', 'both')})
