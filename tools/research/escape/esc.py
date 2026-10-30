# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Escape descriptors of dense-package pins in a dumped board."""
import math
from collections import defaultdict
import pkg

def in_pad(p, x, y, grow=0.0):
    a = math.radians(p['rot'])
    dx, dy = x - p['x'], y - p['y']
    u = dx * math.cos(a) - dy * math.sin(a)
    v = dx * math.sin(a) + dy * math.cos(a)
    return abs(u) <= p['sx'] / 2 + grow and abs(v) <= p['sy'] / 2 + grow

class Board:
    def __init__(self, D):
        self.D = D
        self.tr_by_net = defaultdict(list)
        for t in D['tracks']:
            self.tr_by_net[t['net']].append(t)
        self.via_by_net = defaultdict(list)
        for v in D['vias']:
            self.via_by_net[v['net']].append(v)
        self.zone_nets = defaultdict(set)
        for z in D['zones']:
            for l in z['layers']:
                self.zone_nets[z['net']].add(l)
        self.fp = {f['ref']: f for f in D['fps']}

    def escape(self, pad, cls, fpx, fpy):
        """dict(kind, dir, layer_after, width, via_d, len) for one pad."""
        net = pad['net']
        lay = pad['layers'][0] if pad['layers'] else None
        out = dict(kind='none', width=None, dir=None, via_dist=None, after=None, out_dot=None)
        for v in self.via_by_net.get(net, ()):
            if in_pad(pad, v['x'], v['y']):
                out.update(kind='vip', via_dist=0.0)
                return out
        tr = [t for t in self.tr_by_net.get(net, ()) if t['l'] in pad['layers']]
        start = None
        for t in tr:
            for (x1, y1, x2, y2) in ((t['x1'], t['y1'], t['x2'], t['y2']), (t['x2'], t['y2'], t['x1'], t['y1'])):
                if in_pad(pad, x1, y1, 0.005):
                    if start is None or t['w'] > 0: start = (t, (x1, y1), (x2, y2)); break
            if start: break
        if start is None:
            if lay in self.zone_nets.get(net, ()):
                out['kind'] = 'zone'
            return out
        t, a, b = start
        out['width'] = t['w']; out['layer'] = t['l']
        # walk the chain until 1.5 pitch from the pad centre or a via
        pitch = cls['pitch'] or 0.5
        cur = b; seen = {id(t)}; L = math.dist(a, b); via = None
        for _ in range(6):
            for v in self.via_by_net.get(net, ()):
                if math.hypot(v['x'] - cur[0], v['y'] - cur[1]) < 0.02:
                    via = v; break
            if via or math.dist(cur, (pad['x'], pad['y'])) >= 1.5 * pitch + max(pad['sx'], pad['sy']) / 2:
                break
            nxt = None
            for t2 in tr:
                if id(t2) in seen or t2['l'] != t['l']: continue
                for (x1, y1, x2, y2) in ((t2['x1'], t2['y1'], t2['x2'], t2['y2']), (t2['x2'], t2['y2'], t2['x1'], t2['y1'])):
                    if math.hypot(x1 - cur[0], y1 - cur[1]) < 0.005:
                        nxt = (t2, (x2, y2)); break
                if nxt: break
            if not nxt: break
            seen.add(id(nxt[0])); L += math.dist(cur, nxt[1]); cur = nxt[1]
        dx, dy = cur[0] - pad['x'], cur[1] - pad['y']
        n = math.hypot(dx, dy) or 1
        ox, oy = pad['x'] - fpx, pad['y'] - fpy
        # outward normal: dominant axis for row packages, radial for grids
        if cls['kind'] not in ('bga', 'wlcsp'):
            if abs(ox) >= abs(oy): ox, oy = (1 if ox > 0 else -1), 0
            else: ox, oy = 0, (1 if oy > 0 else -1)
        on = math.hypot(ox, oy) or 1
        out['out_dot'] = (dx * ox + dy * oy) / n / on
        out['dir'] = 'out' if out['out_dot'] > 0.5 else ('in' if out['out_dot'] < -0.5 else 'side')
        if via is not None:
            out.update(kind='dogbone', via_dist=round(math.dist((pad['x'], pad['y']), (via['x'], via['y'])), 3))
            # where the net goes after the via
            ls = {t2['l'] for t2 in self.tr_by_net.get(net, ()) if t2['l'] != t['l'] and
                  (math.hypot(t2['x1'] - via['x'], t2['y1'] - via['y']) < 0.02 or math.hypot(t2['x2'] - via['x'], t2['y2'] - via['y']) < 0.02)}
            out['after'] = sorted(ls)
            out['via_d'] = via['d']
        else:
            out['kind'] = 'surface'
        out['len'] = round(L, 3)
        return out

def dense_pins(H):
    """[(ref, cls, pad)] signal pads with a net of dense packages in human dump H."""
    netpads = defaultdict(int)
    for f in H['fps']:
        for p in f['pads']:
            if p['net']: netpads[p['net']] += 1
    res = []
    for f in H['fps']:
        c = pkg.classify(f)
        if not c['dense']: continue
        for p in f['pads']:
            if p['n'] in c['sig'] and p['net'] and not p['net'].startswith('unconnected-') and netpads[p['net']] >= 2 and len(p['layers']) == 1:
                res.append((f['ref'], c, p))
    return res
