# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Weak-label validation of kae.circuit (comprehension) against human placements.

The brief is inferred without positions. This script then reads the human layout of each
reference board and asks whether the inferred structures are where a designer would have put
them, against random baselines. Positions score the inference; they never feed it.

Weak labels:
  decap ownership   on rails shared by several ICs, is the IC a capacitor is assigned to the
                    owner of the nearest power pin on that rail? Baseline: an owner drawn with
                    probability proportional to its power-pin count.
  cap ownership     the same question for every rail-to-ground capacitor on a rail with two or more
    (all owners)    candidate owners: decap groups (their power pins), commutation cells (the IC's loop
                    pins), a connector-fed rail's entry (the source part's pins) and a converter's output
                    (the inductor's far pad); the entry and converter-output owners are candidates even when
                    the brief does not name them. Baseline: owner drawn in proportion to its pin count.
  decap k-nearest   is the cap assigned to a power pin among the k nearest capacitors to that
                    pin (k = 1, 2, 3), and among the k nearest capacitors on the same rail?
                    Baseline: a capacitor drawn uniformly from the same rail.
  cell compactness  the commutation loop's length (pad to pad, in loop order, closed) against
                    the same parts dropped at random on the board (uniform in the board's
                    bounding box, 400 draws): the percentile of the human loop.
  crystal distance  crystal to its IC's oscillator pins, and load caps to the crystal; with the
                    same random baseline.
  member spread     for every structure kind, the mean member distance to the members'
                    centroid against random placement (percentile).

Usage:
  python -I cm_comprehension_eval.py --tasks kae-work/tasks --out DIR [-j 2] [--only id,id] [--no-sheets] [--rank-w W] [--tie random]
Writes DIR/eval.json (per-board rows and pooled numbers) and DIR/suite.md (tables).
Needs kae (kae/src on sys.path is added here) and numpy. Deterministic (fixed seeds).
"""
import os

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

import argparse  # noqa: E402
import glob  # noqa: E402
import json  # noqa: E402
import math  # noqa: E402
import sys  # noqa: E402
import time  # noqa: E402
import traceback  # noqa: E402
from collections import defaultdict  # noqa: E402
from multiprocessing import Pool  # noqa: E402

import numpy as np  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', '..', '..', 'kae', 'src'))
from kae.board.kicad_file import load  # noqa: E402
from kae.circuit.brief import build  # noqa: E402

N_RAND = 400


def _pad_xy(fp, num):
    pts = [(p.x, p.y) for p in fp.pads if p.number == str(num)]
    if not pts:
        return (fp.x, fp.y)
    return (sum(x for x, _ in pts) / len(pts), sum(y for _, y in pts) / len(pts))


def _bbox(board):
    xs = [fp.x for fp in board.footprints if fp.on_board]
    ys = [fp.y for fp in board.footprints if fp.on_board]
    if board.outline:
        b = board.outline[0].bounds
        for g in board.outline[1:]:
            bb = g.bounds
            b = (min(b[0], bb[0]), min(b[1], bb[1]), max(b[2], bb[2]), max(b[3], bb[3]))
        return b
    return (min(xs), min(ys), max(xs), max(ys))


def _loop_len(pts):
    if len(pts) < 2:
        return 0.0
    tot = 0.0
    for a, b in zip(pts, pts[1:] + pts[:1]):
        tot += math.hypot(a[0] - b[0], a[1] - b[1])
    return tot


def _pct_random_loop(term_parts, offsets, human_len, bbox, rng):
    """Percentile of the human loop length among loops whose parts sit at random places.
    Each loop terminal keeps its offset from its part's origin (the pads stay where the
    footprint puts them; rotation is ignored, which matters little at board scale)."""
    parts = sorted(set(term_parts))
    k = len(parts)
    if k < 2:
        return None
    x0, y0, x1, y1 = bbox
    lens = np.empty(N_RAND)
    idx = [parts.index(p) for p in term_parts]
    off = np.array(offsets)
    for i in range(N_RAND):
        pos = np.column_stack([rng.uniform(x0, x1, k), rng.uniform(y0, y1, k)])
        pts = pos[idx] + off
        d = np.diff(np.vstack([pts, pts[:1]]), axis=0)
        lens[i] = np.hypot(d[:, 0], d[:, 1]).sum()
    return float((lens <= human_len).mean())


def _spread(pts):
    c = np.mean(pts, axis=0)
    return float(np.mean(np.hypot(pts[:, 0] - c[0], pts[:, 1] - c[1])))


def _pct_random_spread(k, human, bbox, rng):
    x0, y0, x1, y1 = bbox
    v = np.empty(N_RAND)
    for i in range(N_RAND):
        pts = np.column_stack([rng.uniform(x0, x1, k), rng.uniform(y0, y1, k)])
        v[i] = _spread(pts)
    return float((v <= human).mean())


def eval_board(args):
    path, use_sheets = args
    bid = path.split('/')[-3]
    t0 = time.perf_counter()
    try:
        board = load(path)
    except Exception as e:  # noqa: BLE001
        return {'id': bid, 'error': f'load: {e!r}'}
    t1 = time.perf_counter()
    try:
        br = build(board, use_sheets=use_sheets)
    except Exception as e:  # noqa: BLE001
        return {'id': bid, 'error': f'build: {e!r}', 'tb': traceback.format_exc()}
    t2 = time.perf_counter()
    rng = np.random.default_rng(12345)
    by_uuid = {fp.uuid: fp for fp in board.footprints}
    ref_of = {u: d['ref'] for u, d in br['parts'].items()}
    bbox = _bbox(board)
    row = {'id': bid, 'parts': len(board.footprints), 'nets': len(board.nets), 't_load': round(t1 - t0, 3),
           't_brief': round(t2 - t1, 3), 'structures': br['summary']['structures'],
           'unknown': len(br['summary']['unknown_parts']), 'low_conf_parts': len(br['summary']['low_confidence_parts']),
           'low_conf_structures': len(br['summary']['low_confidence_structures']),
           'parts_by_kind': br['summary']['parts_by_kind']}
    S = br['structures']
    # ------------------------------------------------------------ decap
    caps_all = [u for u, d in br['parts'].items() if d['kind'] == 'capacitor' and u in by_uuid]
    cap_xy = {}
    for u in caps_all:
        fp = by_uuid[u]
        cap_xy[u] = (fp.x, fp.y)
    rail_caps = defaultdict(set)
    for u in caps_all:
        fp = by_uuid[u]
        for p in fp.pads:
            if p.net:
                rail_caps[p.net].add(u)
    dec = [s for s in S if s['kind'] == 'decap']
    by_rail = defaultdict(list)
    for s in dec:
        by_rail[s['rail']].append(s)
    own = []                 # (correct, baseline) per cap on a shared rail
    knn = {1: [], 2: [], 3: []}
    knn_rail = {1: [], 2: [], 3: []}
    knn_base = {1: [], 2: [], 3: []}
    group_knn = []
    for rail, groups in by_rail.items():
        pins = []            # (owner uuid, pin xy)
        for s in groups:
            fp = by_uuid.get(s['ic'])
            if fp is None:
                continue
            for pn in s['power_pins']:
                pins.append((s['ic'], _pad_xy(fp, pn), pn))
        if not pins:
            continue
        npins = defaultdict(int)
        for o, _, _ in pins:
            npins[o] += 1
        tot = sum(npins.values())
        owners = set(npins)
        for s in groups:
            for c in s['caps']:
                if c not in cap_xy:
                    continue
                fp = by_uuid[c]
                cxy = _pad_xy(fp, next((p.number for p in fp.pads if p.net == rail), fp.pads[0].number if fp.pads else '1'))
                near = min(pins, key=lambda t: math.hypot(t[1][0] - cxy[0], t[1][1] - cxy[1]))
                if len(owners) >= 2:
                    own.append((near[0] == s['ic'], npins[near[0]] / tot, near[0] == s['ic'] and True))
                # group-level kNN: is c among the 3 nearest caps (any rail) to some power pin of its IC?
                ok = False
                for o, pxy, _ in pins:
                    if o != s['ic']:
                        continue
                    ds = sorted(caps_all, key=lambda u: math.hypot(cap_xy[u][0] - pxy[0], cap_xy[u][1] - pxy[1]))[:3]
                    if c in ds:
                        ok = True
                        break
                group_knn.append(ok)
            # pin-level kNN for the suggested pairing
            fp_ic = by_uuid.get(s['ic'])
            for pn, cl in (s.get('pin_caps') or {}).items():
                if not cl or fp_ic is None:
                    continue
                c = cl[0]
                if c not in cap_xy:
                    continue
                pxy = _pad_xy(fp_ic, pn)
                order = sorted(caps_all, key=lambda u: math.hypot(cap_xy[u][0] - pxy[0], cap_xy[u][1] - pxy[1]))
                rc = sorted(rail_caps.get(rail, ()), key=lambda u: math.hypot(cap_xy[u][0] - pxy[0], cap_xy[u][1] - pxy[1]))
                nr = len(rc)
                for k in (1, 2, 3):
                    knn[k].append(c in order[:k])
                    knn_rail[k].append(c in rc[:k])
                    knn_base[k].append(min(k, nr) / nr if nr else 0.0)
    row['own_all'] = _own_all(br, by_uuid)
    row['decap'] = {'groups': len(dec), 'own_n': len(own), 'own_acc': _mean([o[0] for o in own]),
                    'own_base': _mean([o[1] for o in own]), 'group_knn3': _mean(group_knn), 'group_knn_n': len(group_knn),
                    'pin_n': len(knn[1]), **{f'knn{k}': _mean(knn[k]) for k in (1, 2, 3)},
                    **{f'knn{k}_rail': _mean(knn_rail[k]) for k in (1, 2, 3)},
                    **{f'knn{k}_base': _mean(knn_base[k]) for k in (1, 2, 3)},
                    '_own': [[int(a), b] for a, b, _ in own], '_knn': {k: [int(x) for x in v] for k, v in knn.items()},
                    '_knn_rail': {k: [int(x) for x in v] for k, v in knn_rail.items()},
                    '_knn_base': {k: v for k, v in knn_base.items()}, '_group_knn': [int(x) for x in group_knn]}
    # ------------------------------------------------------------ commutation cells
    cells = []
    for s in S:
        if s['kind'] != 'commutation_cell':
            continue
        pts, tparts, offs = [], [], []
        for term in s['loop']:
            u, pads = term[0], term[1]
            fp = by_uuid.get(u)
            if fp is None:
                continue
            pl = pads if isinstance(pads, list) else [pads]
            xy = [_pad_xy(fp, pn) for pn in pl] or [(fp.x, fp.y)]
            x = sum(a for a, _ in xy) / len(xy)
            y = sum(b for _, b in xy) / len(xy)
            pts.append((x, y))
            tparts.append(u)
            offs.append((x - fp.x, y - fp.y))
        L = _loop_len(pts)
        pct = _pct_random_loop(tparts, offs, L, bbox, rng)
        cells.append({'id': s['id'], 'class': s['class'], 'confidence': s['confidence'], 'loop_mm': round(L, 2),
                      'pct_random': pct, 'members': [ref_of.get(u, u) for u in dict.fromkeys(tparts)]})
    row['cells'] = cells
    # ------------------------------------------------------------ crystals
    xt = []
    for s in S:
        if s['kind'] != 'crystal' or not s.get('ic'):
            continue
        fx, fi = by_uuid.get(s['crystal']), by_uuid.get(s['ic'])
        if fx is None or fi is None:
            continue
        pins = [p for p in (s.get('xin'), s.get('xout')) if p]
        if not pins:
            continue
        d = min(math.hypot(fx.x - _pad_xy(fi, pn)[0], fx.y - _pad_xy(fi, pn)[1]) for pn in pins)
        # random baseline: the crystal at a uniform random place
        x0, y0, x1, y1 = bbox
        rx_ = rng.uniform(x0, x1, N_RAND)
        ry_ = rng.uniform(y0, y1, N_RAND)
        pxy = [_pad_xy(fi, pn) for pn in pins]
        rd = np.min([np.hypot(rx_ - px, ry_ - py) for px, py in pxy], axis=0)
        lc = [math.hypot(by_uuid[c].x - fx.x, by_uuid[c].y - fx.y) for c in s.get('load_caps') or [] if c in by_uuid]
        xt.append({'id': s['id'], 'd_ic_mm': round(d, 2), 'pct_random': float((rd <= d).mean()), 'f_Hz': s.get('f_Hz'),
                   'load_cap_mm': [round(x, 2) for x in lc], 'confidence': s['confidence']})
    row['crystals'] = xt
    # ------------------------------------------------------------ member spread for every structure kind
    spread = defaultdict(list)
    for s in S:
        refs = [u for u in s.get('members_ref', {}) if u in by_uuid and by_uuid[u].on_board]
        if s['kind'] in ('heat_source', 'thermal_victim') or len(refs) < 2 or len(refs) > 12:
            continue
        pts = np.array([[by_uuid[u].x, by_uuid[u].y] for u in refs])
        h = _spread(pts)
        p = _pct_random_spread(len(refs), h, bbox, rng)
        key = s['kind'] + (':' + s['class'] if s['kind'] in ('victim', 'commutation_cell') else '')
        spread[key].append((p, round(h, 2), s['confidence']))
    row['spread'] = {k: v for k, v in spread.items()}
    # protection order: TVS nearer the connector than the protected IC
    order_ok = []
    for s in S:
        if s['kind'] != 'connector_chain' or not s.get('protection') or len(s['chain']) < 3:
            continue
        cu, cp = s['chain'][0]
        last = s['chain'][-1]
        if by_uuid.get(last[0]) is None or by_uuid[last[0]].uuid in s['protection']:
            continue
        for pu in s['protection']:
            fpp = by_uuid.get(pu)
            if fpp is None:
                continue
            jxy = _pad_xy(by_uuid[cu], cp)
            ixy = _pad_xy(by_uuid[last[0]], last[1])
            dj = math.hypot(fpp.x - jxy[0], fpp.y - jxy[1])
            di = math.hypot(fpp.x - ixy[0], fpp.y - ixy[1])
            order_ok.append(dj < di)
    row['protection_order'] = {'n': len(order_ok), 'tvs_nearer_connector': _mean(order_ok)}
    return row


def _own_all(br, F):
    """[(correct, baseline)] per capacitor on rails with two or more candidate owners (all owner kinds)."""
    cons = defaultdict(list)            # rail -> [(owner id, [pin xy], [caps])]
    for s in br['structures']:
        if s['kind'] == 'decap':
            fp = F.get(s['ic'])
            if fp is None or not isinstance(s['rail'], str):
                continue
            f = s.get('function')
            cid = ('entry', s['rail']) if f == 'entry' else ('conv', s['rail']) if f in ('converter_output', 'converter_input') else s['id']
            cons[s['rail']].append((cid, [_pad_xy(fp, pn) for pn in s['power_pins']], list(s['caps']), s['confidence']))
        elif s['kind'] == 'commutation_cell' and len(s['loop']) >= 3:
            fc = F.get(s['loop'][0][0])
            u, pads = s['loop'][1][0], s['loop'][1][1]
            if fc is None or F.get(u) is None:
                continue
            rail = next((pd.net for pd in fc.pads if pd.number == str(s['loop'][0][1])), None)
            caps = [m for m in s['members_ref'] if br['parts'].get(m, {}).get('kind') == 'capacitor' and F.get(m) is not None
                    and any(pd.net == rail for pd in F[m].pads)]
            pl = pads if isinstance(pads, list) else [pads]
            if rail:
                cons[rail].append((s['id'], [_pad_xy(F[u], pn) for pn in pl], caps, s['confidence']))
    for rail, lst in cons.items():           # candidate owners the brief may not name
        src = br['nets'].get(rail, {}).get('source') or {}
        if (src.get('kind') in ('connector', 'battery') or (src.get('kind') == 'derived' and src.get('via') in ('diode', 'fuse'))) \
                and src.get('part') in F and not any(c[0] == ('entry', rail) for c in lst):
            xy = [_pad_xy(F[src['part']], pd.number) for pd in F[src['part']].pads if pd.net == rail]
            if xy:
                lst.append((('entry', rail), xy, [], None))
    for s in br['structures']:
        if s['kind'] != 'commutation_cell' or not s.get('inductor') or s['inductor'] not in F:
            continue
        far = s.get('vout') if s['class'] == 'buck' else s.get('vin') if s['class'] == 'boost' else None
        if far in cons and not any(c[0] == ('conv', far) for c in cons[far]):
            xy = [_pad_xy(F[s['inductor']], pd.number) for pd in F[s['inductor']].pads if pd.net == far]
            if xy:
                cons[far].append((('conv', far), xy, [], None))
    out = []
    for rail, lst in cons.items():
        if len(lst) < 2:
            continue
        pins = [(cid, xy) for cid, xys, _, _ in lst for xy in xys]
        npin = defaultdict(int)
        for cid, _ in pins:
            npin[cid] += 1
        for cid, _, caps, conf in lst:
            for c in caps:
                fc = F.get(c)
                if fc is None:
                    continue
                cxy = _pad_xy(fc, next((pd.number for pd in fc.pads if pd.net == rail), '1'))
                near = min(pins, key=lambda t: math.hypot(t[1][0] - cxy[0], t[1][1] - cxy[1]))[0]
                out.append([int(near == cid), round(npin[cid] / len(pins), 4), conf])
    return out


def _mean(v):
    v = [float(x) for x in v if x is not None]
    return round(sum(v) / len(v), 4) if v else None


def pool_rows(rows):
    P = {}
    own = [o for r in rows if 'decap' in r for o in r['decap']['_own']]
    P['decap_ownership'] = {'n': len(own), 'acc': _mean([o[0] for o in own]), 'baseline': _mean([o[1] for o in own]),
                            'boards': sum(1 for r in rows if r.get('decap', {}).get('own_n'))}
    oa = [o for r in rows for o in r.get('own_all', [])]
    per = [sum(o[0] for o in r['own_all']) / len(r['own_all']) for r in rows if r.get('own_all')]
    bins = {}
    for lo, hi in ((0.0, 0.5), (0.5, 0.7), (0.7, 0.9), (0.9, 1.01)):
        sel = [o[0] for o in oa if o[2] is not None and lo <= o[2] < hi]
        bins[f'{lo:.1f}-{min(hi, 1.0):.1f}'] = {'n': len(sel), 'acc': _mean(sel)}
    P['cap_ownership_all'] = {'n': len(oa), 'acc': _mean([o[0] for o in oa]), 'baseline': _mean([o[1] for o in oa]),
                              'boards': len(per), 'per_board_mean': _mean(per), 'by_structure_confidence': bins}
    gk = [x for r in rows if 'decap' in r for x in r['decap']['_group_knn']]
    P['decap_group_knn3'] = {'n': len(gk), 'acc': _mean(gk)}
    for k in (1, 2, 3):
        a = [x for r in rows if 'decap' in r for x in r['decap']['_knn'][k]]
        ar = [x for r in rows if 'decap' in r for x in r['decap']['_knn_rail'][k]]
        bs = [x for r in rows if 'decap' in r for x in r['decap']['_knn_base'][k]]
        P[f'decap_pin_knn{k}'] = {'n': len(a), 'any_cap': _mean(a), 'same_rail': _mean(ar), 'baseline_same_rail': _mean(bs)}
    cells = [c for r in rows for c in r.get('cells', [])]
    pc = [c['pct_random'] for c in cells if c['pct_random'] is not None]
    P['cells'] = {'n': len(cells), 'median_pct_random': _median(pc), 'share_pct_lt_0.05': _mean([x < 0.05 for x in pc]),
                  'share_pct_lt_0.01': _mean([x < 0.01 for x in pc]), 'median_loop_mm': _median([c['loop_mm'] for c in cells]),
                  'by_class': {k: {'n': len(v), 'median_pct': _median(v), 'share_lt_0.05': _mean([x < 0.05 for x in v])}
                               for k, v in _group([(c['class'], c['pct_random']) for c in cells if c['pct_random'] is not None]).items()}}
    xt = [x for r in rows for x in r.get('crystals', [])]
    P['crystals'] = {'n': len(xt), 'median_d_ic_mm': _median([x['d_ic_mm'] for x in xt]),
                     'share_le_12mm': _mean([x['d_ic_mm'] <= 12 for x in xt]),
                     'median_pct_random': _median([x['pct_random'] for x in xt]),
                     'median_load_cap_mm': _median([c for x in xt for c in x['load_cap_mm']])}
    sp = defaultdict(list)
    for r in rows:
        for k, v in r.get('spread', {}).items():
            sp[k] += [x[0] for x in v]
    P['spread'] = {k: {'n': len(v), 'median_pct': _median(v), 'share_lt_0.05': _mean([x < 0.05 for x in v])} for k, v in sorted(sp.items())}
    po = [r['protection_order'] for r in rows if r.get('protection_order', {}).get('n')]
    P['protection_order'] = {'n': sum(x['n'] for x in po),
                             'tvs_nearer_connector': _mean([x['tvs_nearer_connector'] for x in po for _ in range(x['n'])])}
    P['runtime'] = {'brief_median_s': _median([r['t_brief'] for r in rows if 't_brief' in r]),
                    'brief_max_s': max((r['t_brief'] for r in rows if 't_brief' in r), default=None),
                    'load_median_s': _median([r['t_load'] for r in rows if 't_load' in r])}
    return P


def _group(pairs):
    g = defaultdict(list)
    for k, v in pairs:
        g[k].append(v)
    return g


def _median(v):
    v = sorted(x for x in v if x is not None)
    if not v:
        return None
    n = len(v)
    return round(v[n // 2] if n % 2 else 0.5 * (v[n // 2 - 1] + v[n // 2]), 4)


def suite_md(rows):
    lines = ['| board | parts | cells | decap | xtal | chains | victims | ant | heat | unknown | low-conf parts | low-conf structs | brief s |',
             '|---|---|---|---|---|---|---|---|---|---|---|---|---|']
    for r in sorted(rows, key=lambda r: r['id']):
        if 'error' in r:
            lines.append(f"| {r['id']} | error: {r['error'][:60]} |")
            continue
        s = r['structures']
        lines.append(f"| {r['id'][:48]} | {r['parts']} | {s.get('commutation_cell', 0)} | {s.get('decap', 0)} | {s.get('crystal', 0)} | "
                     f"{s.get('connector_chain', 0)} | {s.get('victim', 0)} | {s.get('antenna', 0)} | {s.get('heat_source', 0)} | "
                     f"{r['unknown']} | {r['low_conf_parts']} | {r['low_conf_structures']} | {r['t_brief']} |")
    return '\n'.join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--tasks', default='kae-work/tasks')
    ap.add_argument('--out', required=True)
    ap.add_argument('-j', type=int, default=2)
    ap.add_argument('--only', default='')
    ap.add_argument('--no-sheets', action='store_true')
    ap.add_argument('--rank-w', type=float, default=None, help='override kae.circuit.structures.RANK_W (ablation)')
    ap.add_argument('--tie', choices=('schematic', 'random'), default=None, help='capacitor tie-break order (ablation)')
    a = ap.parse_args(argv)
    import kae.circuit.structures as _st
    if a.rank_w is not None:
        _st.RANK_W = a.rank_w
    if a.tie:
        _st.TIE_ORDER = a.tie
    paths = sorted(glob.glob(os.path.join(a.tasks, '*', 'reference', 'board.kicad_pcb')))
    if a.only:
        keep = set(a.only.split(','))
        paths = [p for p in paths if p.split('/')[-3] in keep]
    os.makedirs(a.out, exist_ok=True)
    jobs = [(p, not a.no_sheets) for p in paths]
    if a.j > 1:
        with Pool(a.j) as pool:
            rows = pool.map(eval_board, jobs, chunksize=1)
    else:
        rows = [eval_board(j) for j in jobs]
    pooled = pool_rows([r for r in rows if 'error' not in r])
    json.dump({'pooled': pooled, 'rows': rows}, open(os.path.join(a.out, 'eval.json'), 'w'), indent=1, default=str)
    open(os.path.join(a.out, 'suite.md'), 'w').write(suite_md(rows) + '\n')
    print(json.dumps(pooled, indent=1, default=str))
    errs = [r for r in rows if 'error' in r]
    print(f"{len(rows)} boards, {len(errs)} errors")
    for r in errs:
        print(r['id'], r['error'])
    return 0


if __name__ == '__main__':
    sys.exit(main())
