# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Escape feasibility of every dense footprint under the board's own (Default-class) rules."""
import json, sys, os, math
from collections import defaultdict, Counter
sys.path.insert(0, os.path.dirname(__file__))
import pkg
from filt import pins
RULES = json.load(open(os.path.join(os.environ.get('ESC_WORK', '.'), 'rules.json')))
KDEF = dict(min_track=0.2, min_clear=0.0, min_via=0.5, min_drill=0.3, classes={'Default': dict(track=0.2, clear=0.2, via=0.6, drill=0.3)})
def rules(b):
    r = RULES.get(b)
    if not r or 'err' in r: return KDEF, False
    return r, True
P, cap, bad = pins()
fp = defaultdict(list)
for p in P: fp[(p['board'], p['ref'])].append(p)
rows = []
for (b, ref), ps in fp.items():
    r, has = rules(b)
    d = r['classes'].get('Default') or KDEF['classes']['Default']
    clear, wc, vd = d['clear'] or 0.2, d['track'] or 0.2, d['via'] or 0.6
    wmin = max(r.get('min_track') or 0.0, 0.0)
    p0 = ps[0]; pitch = p0['pitch']; padw = sorted(x['padw'] for x in ps)[len(ps) // 2]
    if p0['pkg'] in ('bga', 'wlcsp'):
        chan = pitch - padw - 2 * clear            # room for a track between two balls
        tracks_between = 0 if chan < max(wmin, 0.05) else 1 + int((chan - max(wmin,0.05)) // (max(wmin,0.05) + clear))
        via_fit = pitch * math.sqrt(2) - padw - vd - 2 * clear   # dog-bone via in the diagonal gap
        kind = 'grid'
        s_cls = chan - wc; s_min = chan - max(wmin, 0.05)
    else:
        s_cls = pitch - padw / 2 - wc / 2 - clear
        s_min = pitch - padw / 2 - max(wmin, 0.0) / 2 - clear if wmin > 0 else pitch - padw / 2 - clear
        via_fit = None; tracks_between = None; kind = 'row'
    rows.append(dict(board=b, ref=ref, pkg=p0['pkg'], pitch=pitch, padw=padw, clear=clear, wc=wc, wmin=wmin, vd=vd, proj=has,
                     s_cls=round(s_cls, 4), s_min=round(s_min, 4), via_fit=via_fit and round(via_fit, 4), between=tracks_between,
                     n=len(ps), open=sum(x['open'] for x in ps)))
json.dump(rows, open(os.path.join(os.environ.get('ESC_WORK', '.'), 'slack.json'), 'w'))
def cat(x):
    if x['s_min'] < -0.001: return 'A impossible at board min'
    if x['s_cls'] < -0.001: return 'B needs neck-down below class'
    if x['s_cls'] < 0.02: return 'C class width, <20um slack'
    return 'D slack >= 20um'
for grp in (('row',), ('grid',)):
    c = defaultdict(lambda: [0, 0, 0, set(), set()])
    for x in rows:
        if (x['pkg'] in ('bga', 'wlcsp')) != (grp[0] == 'grid'): continue
        k = cat(x); c[k][0] += 1; c[k][1] += x['n']; c[k][2] += x['open']; c[k][3].add(x['board'])
        if x['open']: c[k][4].add(x['board'])
    print(grp[0])
    for k in sorted(c): print(f'  {k:32s} fps {c[k][0]:4d} pins {c[k][1]:5d} open {c[k][2]:5d} ({100*c[k][2]/max(1,c[k][1]):.0f}%) boards {len(c[k][3])} w/open {len(c[k][4])}')
print('fps with opens:')
for x in sorted(rows, key=lambda x: -x['open']):
    if x['open']: print(f"  {x['board'][:34]:34s} {x['ref']:6s} {x['pkg']:9s} p={x['pitch']} pad={x['padw']} clr={x['clear']} wc={x['wc']} wmin={x['wmin']} via={x['vd']} s_cls={x['s_cls']} s_min={x['s_min']} viafit={x['via_fit']} betw={x['between']} proj={x['proj']} {x['open']}/{x['n']}")
