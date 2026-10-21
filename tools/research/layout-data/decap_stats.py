#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Measure decoupling-capacitor-to-IC-power-pin distances on KiCad boards.

Usage: python3 -I decap_stats.py <list.tsv> <boards_dir> <out.jsonl>
Heuristic, for research statistics only.
"""
import json, math, re, sys, os, statistics as st, collections

TOK = re.compile(r'\(|\)|"(?:[^"\\]|\\.)*"|[^\s()"]+')

def parse(text):
    stack = [[]]
    for m in TOK.finditer(text):
        t = m.group(0)
        if t == '(':
            stack.append([])
        elif t == ')':
            x = stack.pop()
            stack[-1].append(x)
        else:
            if t[0] == '"':
                t = t[1:-1]
            stack[-1].append(t)
    return stack[0][0]

def kids(node, name):
    return [c for c in node if isinstance(c, list) and c and c[0] == name]

def first(node, name):
    k = kids(node, name)
    return k[0] if k else None

def rot(x, y, deg):
    a = math.radians(deg)
    # KiCad: y axis points down; positive angle = counter-clockwise on screen
    return x * math.cos(a) + y * math.sin(a), -x * math.sin(a) + y * math.cos(a)

GND = re.compile(r'(^|[^A-Z])(A|D|P|S)?GND|^VSS|^/?GND|^0V$', re.I)
PWR = re.compile(r'^/?(\+?\d+(\.\d+)?V\d*|\+?\d+V\d+|V?\d+V\d+|\+[A-Z0-9_.]+|VCC.*|VDD.*|AVDD.*|DVDD.*|VDDA.*|VDDIO.*|VBUS.*|VIN.*|VSYS.*|VBAT.*|V3V3|3V3.*|5V.*|1V8.*|1V2.*|VREG.*|VCORE.*|VCAP.*)$', re.I)

def val_farads(v):
    v = v.strip().replace('µ', 'u').replace('μ', 'u')
    m = re.match(r'^(\d+(?:[.,]\d+)?)\s*([pnuµm]?)(?:F)?(\d*)', v, re.I)
    if not m:
        return None
    num = float(m.group(1).replace(',', '.'))
    unit = m.group(2).lower()
    tail = m.group(3)
    mult = {'p': 1e-12, 'n': 1e-9, 'u': 1e-6, 'm': 1e-3, '': None}[unit]
    if mult is None:
        return None
    if tail:  # e.g. 4u7
        num = float(f"{m.group(1)}.{tail}")
    return num * mult

def footprints(tree):
    out = []
    for fp in [c for c in tree if isinstance(c, list) and c and c[0] in ('footprint', 'module')]:
        at = first(fp, 'at')
        if not at:
            continue
        fx, fy = float(at[1]), float(at[2])
        fr = float(at[3]) if len(at) > 3 and re.match(r'^-?[\d.]+$', at[3]) else 0.0
        layer = (first(fp, 'layer') or [None, 'F.Cu'])[1]
        ref = val = None
        for p in kids(fp, 'property'):
            if len(p) > 2 and p[1] == 'Reference':
                ref = p[2]
            if len(p) > 2 and p[1] == 'Value':
                val = p[2]
        for t in kids(fp, 'fp_text'):
            if len(t) > 2 and t[1] == 'reference' and ref is None:
                ref = t[2]
            if len(t) > 2 and t[1] == 'value' and val is None:
                val = t[2]
        pads = []
        for pd in kids(fp, 'pad'):
            pat = first(pd, 'at')
            net = first(pd, 'net')
            if not pat:
                continue
            px, py = float(pat[1]), float(pat[2])
            dx, dy = rot(px, py, fr)
            netname = net[2] if net and len(net) > 2 else (net[1] if net and len(net) > 1 and not re.match(r'^\d+$', net[1]) else None)
            pads.append((fx + dx, fy + dy, netname))
        out.append(dict(ref=ref or '', val=val or '', lib=fp[1] if len(fp) > 1 and isinstance(fp[1], str) else '', layer=layer, x=fx, y=fy, pads=pads))
    return out

def pkg(lib):
    m = re.search(r'(0201|0402|0603|0805|1206|1210|1812)', lib)
    return m.group(1) if m else 'other'

def main():
    lst, bdir, outp = sys.argv[1:4]
    rows = []
    boards_ok = 0
    for line in open(lst):
        bid, repo, commit, path, lic, layers = line.rstrip('\n').split('\t')
        f = os.path.join(bdir, bid + '.kicad_pcb')
        try:
            tree = parse(open(f, encoding='utf-8', errors='ignore').read())
        except Exception as e:
            print('PARSE-FAIL', bid, e, file=sys.stderr)
            continue
        fps = footprints(tree)
        ics = [p for p in fps if re.match(r'^(U|IC)\d', p['ref'])]
        if not ics:
            continue
        boards_ok += 1
        icpads = collections.defaultdict(list)
        for ic in ics:
            for (x, y, n) in ic['pads']:
                if n:
                    icpads[n].append((x, y, ic['ref'], ic['layer']))
        for c in fps:
            if not re.match(r'^C\d', c['ref']) or len(c['pads']) != 2:
                continue
            nets = [p[2] for p in c['pads']]
            if not all(nets):
                continue
            g = [i for i, n in enumerate(nets) if GND.search(n.split('/')[-1])]
            pw = [i for i, n in enumerate(nets) if PWR.match(n.split('/')[-1]) and not GND.search(n.split('/')[-1])]
            if len(g) != 1 or len(pw) != 1:
                continue
            px, py, pnet = c['pads'][pw[0]]
            cands = icpads.get(pnet, [])
            if not cands:
                continue
            d, icref, iclayer = min((math.hypot(px - x, py - y), r, l) for (x, y, r, l) in cands)
            rows.append(dict(board=bid, layers=int(layers), lic=lic, cap=c['ref'], val=c['val'], farad=val_farads(c['val']), pkg=pkg(c['lib']),
                             net=pnet, ic=icref, dist_mm=round(d, 3), same_side=(c['layer'] == iclayer)))
    with open(outp, 'w') as o:
        for r in rows:
            o.write(json.dumps(r) + '\n')
    print('boards with ICs', boards_ok, 'decap rows', len(rows))

if __name__ == '__main__':
    main()
