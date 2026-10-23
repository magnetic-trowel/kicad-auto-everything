# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Place terms' straight hops vs the human boards' routed copper (docs/topics/physics/place-terms.md).

Phase 1 (--routed, slow: KiCad zone refill): for every board, the routed-copper value of each
module (kae.route.critical_recheck.board_physics, the routed estimator the critical router
scores with) and, per board hop of the place terms' loops, the straight length and the
length of the least-L' copper path on the routed board:

  decap   per (power pin, capacitor) pair: the rail hop (pin -> cap rail pad) and the ground
          hop (cap ground pad -> nearest IC ground pin); pieces on the ground plane layer are
          the image current and are counted apart;
  cell    each hop of the commutation loop between different parts;
  chain   connector pin -> ... -> first protector, hop by hop;
  crystal per crystal net, the member pads' HPWL and the routed track length.

Phase 2 (default): the place terms on the same boards and briefs, for the knob variants
given (--variants), compared with the routed values: per kind the ratio routed / place
terms (median, p10, p90, geometric mean) and, per hop class, routed / straight length.

Usage:
  python tools/research/physics/pt_routed_calib.py --routed --out DIR [-j 2] [--only id1,id2]
  python tools/research/physics/pt_routed_calib.py --out DIR [--variants base,cal]
Needs kae (kae/.venv) and, for --routed, KiCad (kae.board.pcbnew_io).
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import math
import os
import statistics as stat
import sys
import traceback
from collections import defaultdict
from pathlib import Path

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'kae' / 'src'))
TASKS = ROOT / 'kae-work-v2' / 'tasks'
DEFAULT_IDS = ('olimex-dcdc-50-5-12-dcdc-50-5-12-rev-a1,pcbcorpus-badjeff-paw3222-pcb-paw3222,'
               'pcbcorpus-badjeff-paw3395-pcb-paw3395,pcbcorpus-badjeff-pmw3610-pcb-pmw3610-pcb,'
               'pcbcorpus-blueokiris-ch552g-dev-board-ch552g-dev-board,'
               'pcbcorpus-jvedder-biploar-power-supply-kicad-bipolar-power-supply,'
               'pcbcorpus-lambdakb-trackball-lt6c-lt6c-pcb,pcbcorpus-siderakb-pmw3360-pcb-pmw3360-pcb-jst,'
               'pcbcorpus-siderakb-pmw3610-pcb-pmw3610-pcb,pcbcorpus-tcsullivan-noisecard-noisecard,'
               'pcbcorpus-brenocq-bldc-motor-bldcm-power,'
               'pcbcorpus-caffeinated-labs-caffeinated-aftonsparv-caffeinated-aftonsparv,libresolar-bms-c1-bms-c1,'
               'pcbcorpus-azoninc-doorman-doorman,pcbcorpus-waterloo-rocketry-canhw-processor,'
               'pcbcorpus-justbuchanan-oasis-pcb')


def _boards(tid):
    from kae.board.kicad_file import load
    from kae.circuit.brief import build
    T = TASKS / tid
    b = load(str(T / 'reference' / 'board.kicad_pcb'))
    brief = build(load(str(T / 'route' / 'input' / 'board.kicad_pcb')))
    return b, brief


# ----------------------------------------------------------------------------- phase 1
def _hop(CR, rb, net, ta, tb, gl):
    """Straight and routed length of one hop on `net`'s copper (None when not connected)."""
    st = math.dist((ta['x'], ta['y']), (tb['x'], tb['y']))
    pcs = CR.hop_pieces(rb, net, ta, tb)
    if pcs is None:
        return dict(straight=st, routed=None)
    off = on = 0.0
    vias = 0
    layers = set()
    for pc in pcs:
        if pc[0] == 'via':
            vias += 1
            continue
        _, l, a, c, _w = pc
        layers.add(l)
        if l == gl:
            on += math.dist(a, c)
        else:
            off += math.dist(a, c)
    return dict(straight=st, routed=off + on, routed_off_plane=off, vias=vias, layers=sorted(layers))


def _decap_hops(CR, rb, s):
    from kae.route.critical_modules import GND_RE
    ic, rail = s.get('ic'), s.get('rail')
    caps = s.get('hf_caps') or s.get('caps') or []
    pins = [str(p) for p in s.get('power_pins') or []]
    pc = s.get('pin_caps') or {}
    pairs = [(str(p), c) for p, cs in pc.items() for c in cs if c in caps or c in (s.get('caps') or [])]
    for c in caps:
        if any(c == x for _, x in pairs) or not pins:
            continue
        pairs.append((pins[0], c))
    fic = rb.fp.get(ic)
    out = []
    if fic is None:
        return out
    for pin, cap in pairs:
        fc = rb.fp.get(cap)
        if fc is None:
            continue
        tp = rb.terminal(ic, [pin])
        rp = next((p.number for p in fc.pads if p.net == rail), None)
        gp = next((p.number for p in fc.pads if p.net and p.net != rail and (p.net == s.get('ground') or p.net in rb.gnd
                                                                              or GND_RE.search(p.net))), None)
        if tp is None or rp is None or gp is None:
            continue
        tr, tg = rb.terminal(cap, [rp]), rb.terminal(cap, [gp])
        gpins = [str(x) for x in s.get('ground_pins') or []] or [p.number for p in fic.pads if p.net == tg['net']]
        tG = None
        for g in gpins:
            t = rb.terminal(ic, [g])
            if t is not None and (tG is None or math.dist((t['x'], t['y']), (tp['x'], tp['y'])) <
                                  math.dist((tG['x'], tG['y']), (tp['x'], tp['y']))):
                tG = t
        layer = rb.cu[0] if fc.side == 'F' else rb.cu[-1]
        gl = CR._gnd_layer(rb, layer, tg['x'], tg['y'])
        out.append(dict(cls='decap_rail', pin=pin, cap=fc.ref, **_hop(CR, rb, rail, tp, tr, gl)))
        if tG is not None:
            out.append(dict(cls='decap_gnd', pin=pin, cap=fc.ref, **_hop(CR, rb, tg['net'], tg, tG, gl)))
    return out


def _cell_hops(CR, rb, s):
    T = [rb.terminal(m[0], m[1]) for m in s.get('loop') or []]
    if len(T) < 3 or any(t is None for t in T):
        return []
    side = rb.fp[T[0]['fp']].side
    layer = rb.cu[0] if side == 'F' else rb.cu[-1]
    cx = sum(t['x'] for t in T) / len(T)
    cy = sum(t['y'] for t in T) / len(T)
    gl = CR._gnd_layer(rb, layer, cx, cy) or CR._gnd_layer(rb, layer, cx, cy, outlines=True)
    out = []
    for k in range(len(T)):
        ta, tb = T[k], T[(k + 1) % len(T)]
        if ta['fp'] == tb['fp']:
            continue
        cls = 'cell_gnd' if ta['net'] in rb.gnd else 'cell'
        out.append(dict(cls=cls, net=ta['net'], **_hop(CR, rb, ta['net'], ta, tb, gl)))
    return out


def _chain_hops(CR, rb, s):
    ch = [x for x in (s.get('chain') or []) if x]
    prot = set(s.get('protection') or [])
    if len(ch) < 2 or not prot:
        return []
    T = [rb.terminal(m[0], m[1]) for m in ch]
    if any(t is None for t in T):
        return []
    out = []
    for k in range(len(T) - 1):
        ta, tb = T[k], T[k + 1]
        if ta['fp'] == tb['fp']:
            continue
        out.append(dict(cls='chain', net=ta['net'], **_hop(CR, rb, ta['net'], ta, tb, None)))
        if tb['fp'] in prot:
            break
    return out


def _crystal_hops(CR, rb, s):
    """Per crystal net: the HPWL of the member pads on it (the place terms' RSMT for <= 3
    pins) and the routed track length on the net."""
    nets = list(s.get('nets') or [])
    members = [s.get('ic'), s.get('crystal')] + list(s.get('load_caps') or [])
    out = []
    for net in nets:
        pts = []
        for u in members:
            f = rb.fp.get(u)
            if f is None:
                continue
            for p in f.pads:
                if p.net == net:
                    t = rb.terminal(u, [p.number])
                    pts.append((t['x'], t['y']))
        if len(pts) < 2:
            continue
        xs, ys = zip(*pts)
        hp = (max(xs) - min(xs)) + (max(ys) - min(ys))
        ln = sum(math.dist(t.start, t.end) for t in rb.board.tracks if t.net == net)
        out.append(dict(cls='crystal', net=net, straight=hp, routed=ln, routed_off_plane=ln, vias=0, layers=[]))
    return out


def routed_board(tid):
    from kae.route import critical_recheck as CR
    from kae.route.critical_modules import modules_from_brief
    b, brief = _boards(tid)
    fills = CR.fills_of(b.path)
    ph = CR.board_physics(b, brief=brief, fills=fills)
    rb = CR.RoutedBoard(b, fills=fills, brief=brief)
    rows = []
    for m in modules_from_brief(brief, ('cell', 'decap', 'chain', 'crystal')):
        v = ph.get(m.id) or {}
        if v.get('value') is None:
            continue
        fn = dict(decap=_decap_hops, cell=_cell_hops, chain=_chain_hops, crystal=_crystal_hops)[m.kind]
        try:
            hops = fn(CR, rb, m.spec)
        except Exception as e:  # noqa: BLE001
            hops = [dict(error=f'{type(e).__name__}: {e}')]
        rows.append(dict(id=tid, module=m.id, kind=m.kind, routed=v['value'], unit=v.get('unit'),
                         open_hops=v.get('open_hops'), cover=v.get('plane_cover'), hops=hops))
    return rows


# ----------------------------------------------------------------------------- phase 2
VARIANTS = {
    'base': dict(knobs=dict(hop_detour=0.0)),                       # straight hops
    'cal': dict(knobs=dict()),                                       # priors.HOP_DETOUR, pour-aware decaps
    'nopour': dict(knobs=dict(pour_decaps=False)),                   # calibrated, decaps by straight hops only
}


def terms_board(tid, routed_rows, variants):
    from kae.physics import priors as PR
    from kae.physics.place_terms import Terms
    b, brief = _boards(tid)
    out = []
    by_mod = {r['module']: r for r in routed_rows}
    for name in variants:
        v = VARIANTS[name]
        knobs = PR.Knobs(**v['knobs'])
        t = Terms(b, brief, knobs=knobs)
        rows = t.breakdown(t.bv.pose0())
        modes = {}
        first = {}
        vias = {}
        import kae.physics.fastloop as FL
        th = t.bv.thickness
        lv_full = FL.m_self(th, 0.15) + FL._collinear(th, th, 0.0)
        for k, s in enumerate(t.structs):
            modes[s.id] = [getattr(c, 'mode', None) for c in s.comps]
            if s.kind == 'esd' and s.comps:
                # the routed reference's via runs through the whole board; ours to the plane
                vias[s.id] = (s.comps[0].via(t.st), lv_full)
            if s.kind == 'commutation' and s.comps:
                # the loop through the brief loop's own capacitor (the routed reference's loop),
                # when the ownership filter kept it: it is the first variant
                lc = s.comps[0].T[0]
                if t.bv.parts[lc.i].ref == s.labels[0]:
                    first[s.id] = t._cv[k][0]
        pt = {}
        for r in rows:
            base = r['id'].split('#')[0]
            pt.setdefault(base, []).append(r)
        for mod, rr in by_mod.items():
            mine = pt.get(mod)
            if not mine:
                continue
            # a decap split into pin clusters: the worst cluster, as the routed worst per-pin value
            r = max(mine, key=lambda x: x['value'])
            out.append(dict(id=tid, module=mod, kind=rr['kind'], variant=name, routed=rr['routed'],
                            value=r['value'], util=r['util'], alloc=r['alloc']['value'], modes=modes.get(r['id']),
                            loop_cap_value=first.get(r['id']), n_comps=len(r.get('components') or []),
                            pt_id=r['id'], pairing=(r.get('info') or {}).get('pairing'),
                            via=vias.get(r['id']),
                            function=(r.get('info') or {}).get('function')))
    return out


def _q(v, p):
    v = sorted(v)
    if not v:
        return float('nan')
    k = (len(v) - 1) * p
    f, c = math.floor(k), math.ceil(k)
    return v[f] + (v[c] - v[f]) * (k - f)


def _stats(rat):
    rat = [x for x in rat if x and x > 0 and math.isfinite(x)]
    if not rat:
        return dict(n=0)
    lg = [math.log(x) for x in rat]
    return dict(n=len(rat), median=round(stat.median(rat), 3), p10=round(_q(rat, .1), 3), p90=round(_q(rat, .9), 3),
                geo=round(math.exp(stat.mean(lg)), 3), mad_log=round(stat.median([abs(x - stat.median(lg)) for x in lg]), 3))


def summarize(routed, terms):
    out = dict(hops={}, values={})
    by = defaultdict(list)
    by_len = defaultdict(list)
    for r in routed:
        for h in r['hops']:
            if h.get('routed') is None or h.get('straight', 0) < 0.5:
                continue
            by[h['cls']].append(h['routed'] / h['straight'])
            by[h['cls'] + ':off_plane'].append(max(h['routed_off_plane'], 1e-6) / h['straight'])
            by_len[h['cls']].append((h['straight'], h['routed']))
    for k, v in sorted(by.items()):
        out['hops'][k] = _stats(v)
    # length-weighted ratio (sum routed / sum straight) per class
    for k, v in sorted(by_len.items()):
        out['hops'][k]['sum_ratio'] = round(sum(b for _, b in v) / sum(a for a, _ in v), 3)
    byv = defaultdict(list)
    for r in terms:
        if r['value'] > 0 and r['routed'] > 0:
            byv[(r['variant'], r['kind'])].append(r['routed'] / r['value'])
            if r.get('loop_cap_value'):
                # like for like: the routed reference charges the brief loop's capacitor alone
                byv[(r['variant'], 'cell_loop_cap')].append(r['routed'] / r['loop_cap_value'])
            if r['kind'] == 'decap' and r.get('pairing') == 'pin' and '#' not in r.get('pt_id', '#'):
                # like for like: one pin cluster with its caps in parallel, as the reference
                byv[(r['variant'], 'decap_pin')].append(r['routed'] / r['value'])
            if r.get('via'):
                # like for like: with the reference's whole-board via
                mine, full = r['via']
                byv[(r['variant'], 'chain_full_via')].append(r['routed'] / (r['value'] - mine + full))
    for (var, kind), v in sorted(byv.items()):
        out['values'][f'{var}:{kind}'] = _stats(v)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', required=True)
    ap.add_argument('--routed', action='store_true')
    ap.add_argument('--only', default=DEFAULT_IDS)
    ap.add_argument('-j', type=int, default=2)
    ap.add_argument('--variants', default='base,cal,nopour')
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    ids = [x for x in a.only.split(',') if x]
    rpath = out / 'routed.jsonl'
    if a.routed:
        done = set()
        if rpath.exists():
            done = {json.loads(line)['id'] for line in rpath.open()}
        todo = [t for t in ids if t not in done]
        with cf.ProcessPoolExecutor(a.j) as ex, rpath.open('a') as f:
            futs = {ex.submit(routed_board, t): t for t in todo}
            for fu in cf.as_completed(futs):
                t = futs[fu]
                try:
                    rows = fu.result()
                except Exception:  # noqa: BLE001
                    print(t, 'ERROR', traceback.format_exc().splitlines()[-1], flush=True)
                    continue
                if not rows:
                    rows = [dict(id=t, module=None)]
                for r in rows:
                    f.write(json.dumps(r) + '\n')
                f.flush()
                print(t, len(rows), flush=True)
        return
    routed = [json.loads(line) for line in rpath.open()]
    routed = [r for r in routed if r.get('module') and r['id'] in ids]
    by_id = defaultdict(list)
    for r in routed:
        by_id[r['id']].append(r)
    variants = a.variants.split(',')
    terms = []
    with cf.ProcessPoolExecutor(a.j) as ex:
        futs = {ex.submit(terms_board, t, rows, variants): t for t, rows in by_id.items()}
        for fu in cf.as_completed(futs):
            try:
                terms.extend(fu.result())
            except Exception:  # noqa: BLE001
                print(futs[fu], 'ERROR', traceback.format_exc().splitlines()[-1], flush=True)
    (out / 'terms.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in terms))
    s = summarize(routed, terms)
    (out / 'summary.json').write_text(json.dumps(s, indent=1))
    print(json.dumps(s, indent=1))


if __name__ == '__main__':
    main()
