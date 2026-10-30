# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Dense-package classification and pad/escape geometry helpers over dump.py JSON."""
import json, math, re
from collections import defaultdict

DENSE = 0.65 + 0.011

def load(p):
    return json.load(open(p))

def nn_pitch(pads):
    out = {}
    for i, a in enumerate(pads):
        best = 1e9
        for j, b in enumerate(pads):
            if i != j:
                d = math.hypot(a['x'] - b['x'], a['y'] - b['y'])
                if d > 1e-4 and d < best: best = d
        out[a['n'] + '@%d' % i] = best
    return out

def classify(fp):
    """-> dict(kind, pitch, dense, rings{padkey: ring}, centre) for a footprint dump."""
    pads = [p for p in fp['pads'] if p['layers']]
    cu1 = [p for p in pads if len(p['layers']) == 1 or p['attr'] == 1]
    res = dict(kind='other', pitch=None, dense=False, n=len(pads))
    if len(cu1) < 4:
        return res
    areas = sorted(p['sx'] * p['sy'] for p in cu1)
    med = areas[len(areas) // 2]
    sig = [p for p in cu1 if p['sx'] * p['sy'] <= 4 * med + 1e-9]
    if len(sig) < 4:
        return res
    nn = []
    for i, a in enumerate(sig):
        d = min((math.hypot(a['x'] - b['x'], a['y'] - b['y']) for j, b in enumerate(sig) if j != i
                 and math.hypot(a['x'] - b['x'], a['y'] - b['y']) > 1e-3), default=1e9)
        nn.append(d)
    nn.sort()
    pitch = nn[len(nn) // 2]
    cx = sum(p['x'] for p in sig) / len(sig); cy = sum(p['y'] for p in sig) / len(sig)
    fpid = fp['fpid'].lower()
    # BGA-like: pads in a 2-D grid (round-ish pads, many with 4 neighbours at pitch)
    four = 0
    for a in sig:
        k = sum(1 for b in sig if b is not a and abs(math.hypot(a['x'] - b['x'], a['y'] - b['y']) - pitch) < 0.02 * pitch + 0.005)
        if k >= 4: four += 1
    roundish = sum(1 for p in sig if abs(p['sx'] - p['sy']) < 0.05) / len(sig)
    if (four >= 4 and roundish > 0.8) or 'bga' in fpid or 'wlcsp' in fpid or 'csp' in fpid:
        kind = 'wlcsp' if ('wlcsp' in fpid or 'csp' in fpid or pitch <= 0.5) else 'bga'
    elif re.search(r'conn|fpc|ffc|usb|hirose|hrs_|df40|df12|molex|jst|header|socket|\bsim\b|micro.?sd|sd.?card|card|m\.2|hdmi|displayport|samtec|ipex|u\.fl|receptacle|plug', fpid):
        kind = 'connector'
    elif re.search(r'qfn|dfn|son|lga|vqfn|wqfn|uqfn|lfcsp|tdfn|mlf|mlp', fpid) or len(sig) < len(cu1):
        kind = 'qfn'
    elif re.search(r'qfp|ssop|tssop|msop|vssop|sot-?5|sot-?6|sc-?70|soic|sop|tsop', fpid):
        kind = 'qfp'
    else:
        kind = 'other-smd'
    dense = (pitch <= DENSE) or kind in ('bga', 'wlcsp')
    rings = {}
    if kind in ('bga', 'wlcsp'):
        xs = sorted({round(p['x'] - cx, 3) for p in sig}); ys = sorted({round(p['y'] - cy, 3) for p in sig})
        hx = (max(p['x'] for p in sig) - min(p['x'] for p in sig)) / 2; hy = (max(p['y'] for p in sig) - min(p['y'] for p in sig)) / 2
        for p in sig:
            r = min((hx - abs(p['x'] - cx)), (hy - abs(p['y'] - cy))) / pitch
            rings[p['n']] = int(round(r))
    else:
        for p in sig: rings[p['n']] = 0
    return dict(kind=kind, pitch=round(pitch, 4), dense=dense, n=len(pads), nsig=len(sig), rings=rings, cx=cx, cy=cy,
                fpid=fp['fpid'], sig={p['n'] for p in sig})

PADRE = re.compile(r'^Pad (\S+) \[(.*?)\] of (\S+) on (\S+)')

def parse_item(desc):
    m = PADRE.match(desc)
    if m:
        return dict(kind='pad', n=m.group(1), net=m.group(2), ref=m.group(3), layer=m.group(4))
    k = desc.split(' ')[0].lower()
    m = re.search(r'\[(.*?)\]', desc)
    return dict(kind=k, net=m.group(1) if m else None)
