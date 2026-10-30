# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Human vs route escapes of every dense-package pin; writes pins.jsonl."""
import json, os, sys, math
from collections import Counter, defaultdict
sys.path.insert(0, os.path.dirname(__file__))
import pkg, esc
D = os.path.join(os.environ.get('ESC_WORK', '.'), 'dump')
boards = {b['board']: b for b in json.load(open(os.environ.get('BOARDS_JSON', 'boards.json')))}
opens = json.load(open(os.path.join(os.environ.get('ESC_WORK', '.'), 'opens.json')))
openpins = defaultdict(set)
for r in opens:
    for d in r['dense']:
        openpins[(r['board'], r['run'])].add((d['ref'], d['n']))
out = open(os.path.join(os.environ.get('ESC_WORK', '.'), 'pins.jsonl'), 'w')
for name, b in boards.items():
    hp, rp = f'{D}/{name}.human.json', f'{D}/{name}.route.json'
    if not (os.path.exists(hp) and os.path.exists(rp)): continue
    H, R = pkg.load(hp), pkg.load(rp)
    HB, RB = esc.Board(H), esc.Board(R)
    rfp = {f['ref']: f for f in R['fps']}
    ncw = {k: v['track'] for k, v in H['netclasses'].items()}
    for ref, cls, p in esc.dense_pins(H):
        f = HB.fp[ref]
        he = HB.escape(p, cls, cls['cx'], cls['cy'])
        rf = rfp.get(ref)
        rp_ = next((q for q in rf['pads'] if q['n'] == p['n'] and abs(q['x'] - p['x']) < 1e-3 and abs(q['y'] - p['y']) < 1e-3), None) if rf else None
        re_ = RB.escape(rp_, cls, cls['cx'], cls['cy']) if rp_ else None
        row = dict(board=name, ref=ref, n=p['n'], net=p['net'], nc=p['nc'], pkg=cls['kind'], pitch=cls['pitch'],
                   ring=cls['rings'].get(p['n']), nsig=cls['nsig'], fpid=cls['fpid'], layers=H['copper'],
                   padw=min(p['sx'], p['sy']), ncw=ncw.get(p['nc'] or 'Default', ncw.get('Default')),
                   minw=H['min_track'], minclear=H['min_clear'],
                   human=he, route=re_, open=(ref, p['n']) in openpins[(name, 'route')],
                   zone_net=bool(HB.zone_nets.get(p['net'])))
        out.write(json.dumps(row) + '\n')
out.close()
