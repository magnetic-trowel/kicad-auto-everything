# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Corpus scan of crystals and capacitors: what designs actually use.

    python corpus_parts_scan.py BOARDS_DIR -o out.jsonl [-j 16]

Per board, a light regex read of the .kicad_pcb (no KiCad):
- crystals (reference Y*/X*/XTAL*, value or footprint naming a crystal): value, footprint, frequency,
  a C_L stated in the value or properties, and the capacitors from each crystal net to a ground net
  (their values): the designer's load caps, from which C_L = C1 C2 / (C1 + C2) + C_stray;
- capacitors: value, footprint, a voltage rating in the value or properties, and the nominal voltage of
  the non-ground net (from its name): the DC bias each MLCC sits at, relative to its rating.
Feeds the C_L prior of kae.physics.priors.crystal_budget and the bias statistics behind
kae.excite.models' MLCC derating (docs/topics/rules/crystals-clocks.md, decoupling-pdn.md).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from concurrent.futures import ProcessPoolExecutor

from kae.circuit import values as V

FP_START = re.compile(r'^\s*\((footprint|module)\s+"?([^"\s)]+)"?', re.M)
REF5 = re.compile(r'\(fp_text\s+reference\s+"?([^"\s)]+)"?')
VAL5 = re.compile(r'\(fp_text\s+value\s+"((?:[^"\\]|\\.)*)"|\(fp_text\s+value\s+([^\s)]+)')
PROP = re.compile(r'\(property\s+"([^"]+)"\s+"((?:[^"\\]|\\.)*)"')
PAD = re.compile(r'\(pad\s+"?([^"\s)]*)"?\s[^\n]*?(?:\n[^\n]*?){0,12}?\(net\s+\d+\s+"?((?:[^"\\)]|\\.)*)"?\)', re.M)
GND = re.compile(r'(^|[/_\-])(A|D|P|S)?(GND|VSS|0V|GNDA|GNDD|AGND|DGND|PGND)\w*$', re.I)
XTAL = re.compile(r'crystal|xtal|osc|\d\s*(k|m)hz|resonat|abm|fa-?\d|tsx|x\d{3}|hc-?49', re.I)
CL_RE = re.compile(r'(?:C_?L|load)\s*[=:]?\s*(\d+(?:\.\d+)?)\s*p', re.I)
CL_ANY = re.compile(r'(?<![\d.])(\d{1,2}(?:\.\d)?)\s*pF', re.I)


def footprints(text):
    starts = [m.start() for m in FP_START.finditer(text)]
    starts.append(len(text))
    for a, b in zip(starts, starts[1:]):
        blk = text[a:b]
        lib = FP_START.match(text, a).group(2)
        props = dict(PROP.findall(blk))
        ref = props.get('Reference') or (REF5.search(blk).group(1) if REF5.search(blk) else '')
        if 'Value' in props:
            val = props['Value']
        else:
            m = VAL5.search(blk)
            val = ((m.group(1) if m.group(1) is not None else m.group(2)) or '') if m else ''
        pads = [(n, net) for n, net in PAD.findall(blk)]
        yield dict(ref=ref, value=val, lib=lib, props=props, pads=pads)


def scan(path):
    try:
        text = open(path, encoding='utf-8', errors='replace').read()
    except OSError:
        return None
    fps = list(footprints(text))
    caps_on = {}
    caps = []
    for f in fps:
        if re.match(r'^C\d', f['ref']) and len({n for _, n in f['pads'] if n}) == 2:
            nets = sorted({n for _, n in f['pads'] if n})
            caps.append((f, nets))
            for n in nets:
                caps_on.setdefault(n, []).append((f, nets))
    out = dict(crystals=[], caps=[])
    for f in fps:
        txt = ' '.join([f['value'], f['lib']] + [str(v) for k, v in f['props'].items() if k not in ('Reference', 'Datasheet')])
        if not re.match(r'^(Y|X|XTAL|Q)\d', f['ref'], re.I) or not XTAL.search(txt):
            continue
        if re.match(r'^Q\d', f['ref']) and not re.search(r'crystal|xtal', txt, re.I):
            continue
        sig = sorted({n for _, n in f['pads'] if n and not GND.search(n)})
        if len(sig) < 2:
            continue
        loads = {}
        for n in sig[:4]:
            for c, nets in caps_on.get(n, []):
                other = [x for x in nets if x != n][0]
                if GND.search(other):
                    cv = V.capacitance(c['value'])
                    loads.setdefault(n, []).append(cv)
        m = CL_RE.search(txt) or (CL_ANY.search(txt) if re.search(r'hz', txt, re.I) else None)
        out['crystals'].append(dict(ref=f['ref'], value=f['value'], lib=f['lib'], f_Hz=V.frequency(txt),
                                    cl_stated_pF=float(m.group(1)) if m else None,
                                    loads_pF={n: [round(v * 1e12, 2) if v else None for v in vs] for n, vs in loads.items()}))
    for f, nets in caps:
        pkg = V.package(f['lib'])
        txt = ' '.join([f['value']] + [str(v) for k, v in f['props'].items() if k not in ('Reference', 'Datasheet', 'Footprint')])
        nv = [V.net_voltage(V.split_sheet(n)) for n in nets if not GND.search(n)]
        gnd = any(GND.search(n) for n in nets)
        out['caps'].append(dict(C=V.capacitance(f['value']), Vr=V.rated_voltage(txt), size=pkg.size, pol=pkg.polarized,
                                th=pkg.through_hole, die=_dielectric(txt), Vbias=(abs(nv[0][0]) if gnd and nv and nv[0] else None)))
    return out


def _dielectric(t):
    m = re.search(r'\b(X5R|X7R|X7S|X6S|X8R|Y5V|Z5U|C0G|NP0|COG)\b', t, re.I)
    return m.group(1).upper().replace('COG', 'C0G').replace('NP0', 'C0G') if m else None


def one(d):
    p = os.path.join(d, 'board.kicad_pcb')
    try:
        r = scan(p) if os.path.exists(p) else None
    except Exception as e:                       # a malformed board: recorded, not fatal
        r = dict(error=f'{type(e).__name__}: {e}', crystals=[], caps=[])
    return (os.path.basename(d), r)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('boards')
    ap.add_argument('-o', '--out', required=True)
    ap.add_argument('-j', type=int, default=8)
    a = ap.parse_args(argv)
    dirs = sorted(os.path.join(a.boards, x) for x in os.listdir(a.boards))
    with open(a.out, 'w') as fo, ProcessPoolExecutor(a.j) as ex:
        for bid, r in ex.map(one, dirs, chunksize=16):
            if r is not None:
                fo.write(json.dumps(dict(id=bid, **r)) + '\n')


if __name__ == '__main__':
    sys.exit(main())
