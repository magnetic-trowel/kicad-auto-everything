# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""How much does kae.circuit's brief depend on library pin electrical types?

Library pin types are often wrong: VIN typed input, VIN+ typed power_in, GPIOs named after an oscillator
function. The comprehension evidence model should let pin names, values and topology outvote a
contradicting type. This script measures that on the reference boards by rebuilding the brief after
perturbing the types in memory (the board files are never written):

  blank   every pad's type becomes '' (unspecified), as in libraries that never set types;
  flip    contradicting types: supply-named pins (VIN, VDD, VBAT ...) become 'input', logic-named pins
          (GPIO, PA3, SDA, EN ...) and differential inputs (VIN+, IN-) become 'power_in', ground pins 'passive'.

Agreement with the unperturbed brief, pooled over boards:
  net roles   share of nets whose role (rail, ground, switch_node, clock, analog, ...) is unchanged;
  rails       Jaccard of the rail sets;
  cells       Jaccard of commutation-cell ids;
  decaps      Jaccard of (IC, rail, function) decap groups.

Usage:
  python -I cm_pin_type_robustness.py --tasks kae-work/tasks [-j 2] [--only id,id] [--kae-src DIR] [--out FILE]
`--kae-src` points at another copy of kae/src (to compare code versions).
"""
import argparse
import glob
import json
import os
import re
import sys
from multiprocessing import Pool

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

HERE = os.path.dirname(os.path.abspath(__file__))
KAE_SRC = os.path.join(HERE, '..', '..', '..', 'kae', 'src')

SUPPLY = re.compile(r'^(P?VIN\d*|AVIN|VBAT\w*|VDD\w*|VCC\w*|AVDD\w*|DVDD\w*|IOVDD|PVDD\w*|VBUS|VSYS|VDDIO\w*|VDDA\w*|VCCIO\w*)$', re.I)
SIGNAL = re.compile(r'^(GPIO\w*|IO\d+\w*|P[A-K]\d{1,2}\w*|P\d[._]\d+\w*|SDA\w*|SCL\w*|MOSI|MISO|SCK|TXD?\d?|RXD?\d?|EN|ENABLE|INT\w*|'
                    r'IRQ\w*|PWM\w*|D\d{1,2}|CS|NSS|LED\d?)$', re.I)
DIFF = re.compile(r'^(V?IN[+-]|[+-]V?IN|SENSE[+-]|CS[+-])$', re.I)
GROUND = re.compile(r'^(P?GND\w*|AGND\w*|DGND\w*|VSS\w*|EP|EPAD)$', re.I)


def perturb(board, mode):
    for fp in board.footprints:
        for p in fp.pads:
            t = p.pintype or ''
            nc = '+no_connect' if 'no_connect' in t else ''
            fn = (p.pinfunction or '').strip()
            if mode == 'blank':
                p.pintype = '' + nc
            elif mode == 'flip':
                if GROUND.match(fn):
                    p.pintype = 'passive' + nc
                elif SUPPLY.match(fn):
                    p.pintype = 'input' + nc
                elif DIFF.match(fn) or SIGNAL.match(fn):
                    p.pintype = 'power_in' + nc


def summary(br):
    roles = {n: d['role'] for n, d in br['nets'].items()}
    rails = {n for n, r in roles.items() if r == 'rail'}
    cells = {s['id'] for s in br['structures'] if s['kind'] == 'commutation_cell'}
    dec = {(br['parts'].get(s['ic'], {}).get('ref'), str(s['rail']), s.get('function')) for s in br['structures'] if s['kind'] == 'decap'}
    return roles, rails, cells, dec


def jac(a, b):
    return 1.0 if not a and not b else len(a & b) / len(a | b)


def one(args):
    path, src = args
    sys.path.insert(0, src)
    from kae.board.kicad_file import load
    from kae.circuit.brief import build
    bid = path.split('/')[-3]
    try:
        r0, rails0, cells0, dec0 = summary(build(load(path)))
        out = {'id': bid, 'nets': len(r0)}
        for mode in ('blank', 'flip'):
            b = load(path)
            perturb(b, mode)
            r1, rails1, cells1, dec1 = summary(build(b))
            same = sum(1 for n in r0 if r1.get(n) == r0[n])
            out[mode] = {'net_roles': same / max(1, len(r0)), 'rails': jac(rails0, rails1), 'cells': jac(cells0, cells1),
                         'decaps': jac(dec0, dec1), 'rails_n': (len(rails0), len(rails1))}
        return out
    except Exception as e:  # noqa: BLE001
        return {'id': bid, 'error': repr(e)}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--tasks', default='kae-work/tasks')
    ap.add_argument('-j', type=int, default=2)
    ap.add_argument('--only', default='')
    ap.add_argument('--kae-src', default=KAE_SRC)
    ap.add_argument('--out', default='')
    a = ap.parse_args(argv)
    paths = sorted(glob.glob(os.path.join(a.tasks, '*', 'reference', 'board.kicad_pcb')))
    if a.only:
        keep = set(a.only.split(','))
        paths = [p for p in paths if p.split('/')[-3] in keep]
    jobs = [(p, os.path.abspath(a.kae_src)) for p in paths]
    if a.j > 1:
        with Pool(a.j) as pool:
            rows = pool.map(one, jobs, chunksize=1)
    else:
        rows = [one(j) for j in jobs]
    ok = [r for r in rows if 'error' not in r]
    pooled = {}
    for mode in ('blank', 'flip'):
        w = sum(r['nets'] for r in ok)
        pooled[mode] = {'net_roles': round(sum(r[mode]['net_roles'] * r['nets'] for r in ok) / max(1, w), 4)}
        for k in ('rails', 'cells', 'decaps'):
            pooled[mode][k] = round(sum(r[mode][k] for r in ok) / max(1, len(ok)), 4)
    res = {'boards': len(ok), 'errors': [r for r in rows if 'error' in r], 'pooled': pooled, 'rows': rows}
    if a.out:
        with open(a.out, 'w') as f:
            json.dump(res, f, indent=1)
    print(json.dumps({'boards': len(ok), 'errors': len(res['errors']), 'pooled': pooled}, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
