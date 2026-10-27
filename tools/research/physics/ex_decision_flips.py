# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Where do the fast place terms and exact physics rank candidate placements differently?
(docs/topics/physics/exact-physics-options.md, decision flips)

Candidates are the local perturbations of pt_human_perturb.py on the human reference boards
(kae-work-v2/tasks/*/reference/board.kicad_pcb): for a sampled part of a structure kind, its
human pose, three legal 1-5 mm translations and the legal 90/180/270 degree rotations in place.
Every candidate is priced, for every structure the part belongs to, by

  fast     the place terms (kae.physics.place_terms: straight hops, closed forms);
  detour   fast + L'(w, h) x (routed - straight) per board hop (a fresh any-angle route);
  cf       closed forms on any-angle routes of every hop (the module stage's model);
  cfm      closed forms on Manhattan routes;
  peec     multi-filament PEEC on the Manhattan routes (the validation's reference);
  thermal: fast = fin kernel with edge images; fv = finite volume with the zones as placed,
           heat into the part's outer layer; fvs = the same with heat into every layer under
           the part (a perfectly stitched footprint): the true rise lies between the two.
(ex_exact.py holds the evaluators; crystal: routed length x field-solver C'; coupling: PEEC
 currents of the routed aggressor, EMF along the routed victim, capacitive part as fast.)

Per board, one JSON with every candidate's per-structure values and the time each evaluator
took. --aggregate-only reads them back and prints, per structure kind and per pair of
evaluators, how often two candidates of one part are ordered differently (a flip), among pairs
that the reference separates materially (some structure moves by >= 1% of its allocation),
plus top-1 agreement and regret over each part's candidate set, and the flips left after
three cheap corrections anchored at the human pose:

  ratio    per-structure factor exact/fast at the anchor (a control variate in log space);
  offset   per-structure additive exact - fast at the anchor;
  hops     per-hop detour ratio routed/straight at the anchor, applied to the candidate's
           straight hop (no routing per move).

Usage:
  python tools/research/physics/ex_decision_flips.py --out kae-work/physics/exact-options/flips [-j 1]
         [--only id1,id2] [--parts 6] [--seed 1] [--max-parts 300]
  python tools/research/physics/ex_decision_flips.py --out DIR --aggregate-only
Deterministic for a given seed. Never writes boards; outputs stay under kae-work/ (git-ignored).
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import copy
import glob
import json
import math
import os
import random
import sys
import time
import traceback
from collections import Counter, defaultdict
from pathlib import Path

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / 'kae' / 'src'))
sys.path.insert(0, str(HERE))

import numpy as np  # noqa: E402

KINDS = ('commutation', 'decap', 'esd', 'crystal', 'coupling', 'thermal')
LOOP_MODES = ('detour', 'cf', 'cfm', 'peec')
MATERIAL = 0.01


def _f(v):
    return None if v is None else float(v)


# ============================================================================ per board
def eval_structs(T, R, ks, X, modes=LOOP_MODES):
    """{struct id: {fast, <mode>: value, comps: [...], t: {mode: s}}} at the current state."""
    from kae.physics.place_terms import _red
    from kae.physics.structures import CouplingComp, CrystalComp, EsdComp, LoopComp, NearestLoopComp, PlanePairLoop
    st = T.st
    R.refresh()
    out = {}
    for k in ks:
        s = T.structs[k]
        rec = dict(kind=s.kind, alloc=s.alloc.value, conf=s.conf, reduce=s.reduce, comps=[], t={})
        vals = {m: [] for m in ('fast',) + modes}
        for c in s.comps:
            row = dict(fast=float(c.value(st)))
            vals['fast'].append(row['fast'])
            loopish = isinstance(c, (LoopComp, NearestLoopComp))
            if loopish:
                lc = X.loop_comps(c, st)
                hops = X.board_hops(T, lc)
                row['hops'] = [(int(hk), math.hypot(b[0] - a[0], b[1] - a[1]), float(w), bool(own),
                                None if h == float('inf') else float(h)) for hk, a, b, w, own, h in hops]
            coup = None
            for m in modes:
                t0 = time.perf_counter()
                if isinstance(c, CouplingComp):
                    if m == 'detour':
                        v, info = c.value(st), {}
                    elif coup is None:
                        v, info = X.eval_coupling(T, c, R, 'peec')
                        coup = (v, info)
                    else:
                        v, info = coup
                elif isinstance(c, (LoopComp, NearestLoopComp, PlanePairLoop)):
                    v, info = X.eval_loop(T, c, R, m)
                elif isinstance(c, EsdComp):
                    v, info = X.eval_esd(T, c, R, m)
                elif isinstance(c, CrystalComp):
                    if m == 'detour':
                        v, info = X.eval_crystal(T, c, R, 'detour')
                    elif coup is None:
                        v, info = X.eval_crystal(T, c, R, 'cf')
                        coup = (v, info)
                    else:
                        v, info = coup
                else:
                    v, info = c.value(st), {}
                dt = time.perf_counter() - t0
                rec['t'][m] = rec['t'].get(m, 0.0) + dt
                row[m] = _f(v)
                if isinstance(info, dict):
                    if m == 'cf' and 'hops' in info:
                        row['hop_routed'] = {str(hk): v2[0] for hk, v2 in info['hops'].items()}
                    if 'note' in info and v is None:
                        row['note_' + m] = info['note']
                    if 'filaments' in info:
                        row['fil'] = info['filaments']
                vals[m].append(v)
            rec['comps'].append(row)
        w = s.info.get('weights')
        for m, vs in vals.items():
            rec[m] = None if any(v is None for v in vs) else float(_red(s.reduce, vs, w))
        out[s.id] = rec
    return out


def run_board(path, out_dir, seed, n_parts, max_parts):
    import ex_exact as X
    from kae.board.kicad_file import load
    from kae.circuit.brief import build
    from kae.physics.place_terms import Terms
    from pt_human_perturb import Legal, kind_parts
    bid = Path(path).parents[1].name
    rng = random.Random(f'{seed}:{bid}')
    t_board = time.time()
    rec = dict(id=bid, status='ok')
    try:
        b = load(path)
        brief = build(b)
        T = Terms(b, brief)
    except Exception as e:      # noqa: BLE001
        rec.update(status='error', error=f'{type(e).__name__}: {e}')
        json.dump(rec, open(os.path.join(out_dir, bid + '.json'), 'w'))
        return dict(id=bid, status='error')
    bv = T.bv
    poses = bv.pose0()
    T.total(poses)
    rec['parts'] = len(bv.parts)
    rec['layers'] = len(bv.copper)
    if len(bv.parts) > max_parts:
        rec['status'] = 'skipped (size)'
        json.dump(rec, open(os.path.join(out_dir, bid + '.json'), 'w'))
        return dict(id=bid, status=rec['status'])
    X.attach_aggressors(T)
    R = X.Router(T)
    F = Fs = None
    if T.thermal is not None:
        t0 = time.perf_counter()
        F = X.FVThermal(T, inject='surface')
        Fs = copy.copy(F)
        Fs.inject = 'stack'
        Fs.cache = {}
        rec['fv'] = dict(nodes=F.nodes, dx=F.dx, t_build=F.t_build, t_factor=F.t_factor, nnz_lu=F.nnz_lu,
                         t_total=time.perf_counter() - t0)
    legal = Legal(T)
    locked = {p.i for p in bv.parts if p.locked}
    cands_out = []
    st = T.st
    for kind in KINDS:
        parts = sorted(kind_parts(T, kind) - locked)
        if kind != 'thermal':
            parts = [i for i in parts if any(T.structs[k].kind == kind for k in T.inc.get(i, ()))]
        if not parts:
            continue
        sample = parts if len(parts) <= n_parts else rng.sample(parts, n_parts)
        for i in sample:
            u = T.uids[i]
            x, y, r, s = poses[u]
            moves = [('human', (x, y, r, s))]
            for _ in range(3):
                for _try in range(20):
                    ang = rng.uniform(0, 2 * math.pi)
                    d = rng.uniform(1.0, 5.0)
                    q = (x + d * math.cos(ang), y + d * math.sin(ang), r, s)
                    if legal.ok(i, q):
                        moves.append(('translate', q))
                        break
            for dr in (90.0, 180.0, 270.0):
                q = (x, y, (r + dr) % 360.0, s)
                if legal.ok(i, q):
                    moves.append(('rotate', q))
            if len(moves) < 2:
                continue
            ks = sorted(T.inc.get(i, ()))
            if kind != 'thermal':
                ks = [k for k in ks if T.structs[k].kind == kind] + [k for k in ks if T.structs[k].kind != kind]
            rows = []
            for mtype, q in moves:
                saved = st.get(i)
                st.set(i, *q)
                try:
                    row = dict(move=mtype, pose=list(q))
                    if kind == 'thermal':
                        t0 = time.perf_counter()
                        rf, mf = X.fast_rise(T)
                        t1 = time.perf_counter()
                        re_, me = F.rise()
                        t2 = time.perf_counter()
                        rs, ms = Fs.rise()
                        t3 = time.perf_counter()
                        row['thermal'] = dict(fast=X.thermal_cost(T, rf, mf), fv=X.thermal_cost(T, re_, me),
                                              fvs=X.thermal_cost(T, rs, ms),
                                              rise_fast=[float(v - mf) for v in rf], rise_fv=[float(v - me) for v in re_],
                                              rise_fvs=[float(v - ms) for v in rs],
                                              alloc=[a.value for a in T._th_alloc], conf=list(T._th_conf),
                                              t=dict(fast=t1 - t0, fv=t2 - t1, fvs=t3 - t2))
                    else:
                        row['structs'] = eval_structs(T, R, ks, X)
                    rows.append(row)
                except Exception as e:      # noqa: BLE001
                    rows.append(dict(move=mtype, error=f'{type(e).__name__}: {e}', trace=traceback.format_exc()[-800:]))
                finally:
                    st.set(i, *saved)
            cands_out.append(dict(kind=kind, part=bv.parts[i].ref, rows=rows))
    R.refresh()
    rec['candidates'] = cands_out
    rec['router'] = R.stats
    if F is not None:
        rec['fv_solves'] = dict(surface=F.solves, stack=Fs.solves, t_surface=F.t_solve, t_stack=Fs.t_solve)
    rec['seconds'] = round(time.time() - t_board, 1)
    json.dump(rec, open(os.path.join(out_dir, bid + '.json'), 'w'), default=float)
    return dict(id=bid, status='ok', seconds=rec['seconds'], cands=len(cands_out))


# ============================================================================ aggregate
def _phi(u, beta=4.0, usat=10.0):
    from kae.physics import priors as PR
    return PR.phi(u, beta, usat)


def struct_cost(rec, v):
    if v is None:
        return None
    a = rec['alloc']
    return rec['conf'] * _phi(v / a if a > 0 else 0.0)


def corrected(rec, anchor, cand, how):
    """Fast value of one structure at a candidate, corrected with anchor data."""
    f = cand['fast']
    exact_kind = rec['kind'] in ('commutation', 'decap', 'esd', 'crystal', 'coupling')
    if how in ('ratio', 'offset') and not exact_kind:
        return f                  # no exact model for this kind: nothing to correct
    if how == 'ratio':
        if anchor.get('peec') is None or anchor['fast'] <= 0:
            return None
        return f * anchor['peec'] / anchor['fast']
    if how == 'offset':
        if anchor.get('peec') is None:
            return None
        return f + anchor['peec'] - anchor['fast']
    if how == 'hops':
        from kae.physics.kernels import lprime_hj
        from kae.physics.place_terms import _red
        vals = []
        for ca, cc in zip(anchor['comps'], cand['comps']):
            v = cc['fast']
            hr = ca.get('hop_routed') or {}
            for (hk, sl, w, own, h), (hk2, sl_a, *_r) in zip(cc.get('hops') or [], ca.get('hops') or []):
                if own or str(hk) not in hr or sl_a < 1e-6:
                    continue
                ratio = max(1.0, hr[str(hk)] / sl_a)
                v += lprime_hj(w, h if h is not None else 1.6) * (ratio - 1.0) * sl
            vals.append(v)
        return float(_red(rec.get('reduce', 'parallel'), vals)) if vals else f
    return f


def kind_cost(row, kind, mode, anchor_row=None, how=None, only_kind=True):
    """Cost of the candidate's structures of `kind` (or all kinds) under one evaluator."""
    tot = 0.0
    for sid, rec in row['structs'].items():
        if only_kind and rec['kind'] != kind:
            continue
        if how is not None:
            v = corrected(rec, anchor_row['structs'][sid], rec, how)
        else:
            v = rec.get(mode)
            if mode != 'fast' and v is None and rec['kind'] not in ('commutation', 'decap', 'esd', 'crystal', 'coupling'):
                v = rec['fast']           # kinds without an exact model: fast stands in
        c = struct_cost(rec, v)
        if c is None:
            return None
        tot += c
    return tot


def material(row_a, row_b, kind, mode):
    """Some structure of the kind moves by >= MATERIAL of its allocation under `mode`."""
    for sid, ra in row_a['structs'].items():
        if ra['kind'] != kind:
            continue
        rb = row_b['structs'].get(sid)
        if rb is None or ra.get(mode) is None or rb.get(mode) is None:
            continue
        if abs(ra[mode] - rb[mode]) / max(ra['alloc'], 1e-12) >= MATERIAL:
            return True
    return False


def aggregate(out_dir):
    recs = [json.load(open(f)) for f in sorted(glob.glob(os.path.join(out_dir, '*.json')))
            if not os.path.basename(f).startswith('summary')]
    ok = [r for r in recs if r.get('status') == 'ok']
    pairs = defaultdict(Counter)          # (kind, A, B) -> Counter(flip, n)
    top1 = defaultdict(Counter)
    regret = defaultdict(list)
    topk = defaultdict(Counter)
    times = defaultdict(list)
    notes = defaultdict(Counter)
    ratios = defaultdict(list)
    errors = Counter()
    boards_with = Counter()
    REF = 'peec'
    comps_pairs = [('fast', 'peec'), ('fast', 'cf'), ('detour', 'peec'), ('cf', 'peec'), ('cfm', 'peec'),
                   ('cf', 'cfm'), ('fast', 'detour')]
    th_pairs = [('fast', 'fv'), ('fast', 'fvs'), ('fv', 'fvs')]
    for r in ok:
        kinds_here = set()
        for cand in r.get('candidates', []):
            kind = cand['kind']
            rows = [x for x in cand['rows'] if 'error' not in x]
            errors[kind] += len(cand['rows']) - len(rows)
            if len(rows) < 2:
                continue
            kinds_here.add(kind)
            if kind == 'thermal':
                for row in rows:
                    for m, t in row['thermal']['t'].items():
                        times[('thermal', m)].append(t)
                for a in range(len(rows)):
                    for b in range(a + 1, len(rows)):
                        ta, tb = rows[a]['thermal'], rows[b]['thermal']
                        # material: some target's excess moves by >= 1% of its allocation (fv)
                        mat = any(abs(x - y) / al >= MATERIAL for x, y, al in zip(ta['rise_fv'], tb['rise_fv'], ta['alloc']))
                        for A, B in th_pairs:
                            da, db = ta[A] - tb[A], ta[B] - tb[B]
                            key = ('thermal', A, B, 'human' if a == 0 else 'other')
                            if not mat:
                                continue
                            pairs[key]['n'] += 1
                            pairs[key]['flip'] += (da > 0) != (db > 0) or da == 0
                best_f = min(range(len(rows)), key=lambda q: rows[q]['thermal']['fast'])
                for refm in ('fv', 'fvs'):
                    best_r = min(range(len(rows)), key=lambda q: rows[q]['thermal'][refm])
                    top1[('thermal', refm)]['n'] += 1
                    top1[('thermal', refm)]['agree'] += best_f == best_r
                    order = sorted(range(len(rows)), key=lambda q: rows[q]['thermal']['fast'])
                    for K in (1, 2, 3):
                        topk[('thermal', refm, K)]['n'] += 1
                        topk[('thermal', refm, K)]['hit'] += best_r in order[:K]
                continue
            for row in rows:
                for sid, rec in row['structs'].items():
                    if rec['kind'] != kind:
                        continue
                    for m, t in rec['t'].items():
                        times[(kind, m)].append(t)
                    for c in rec['comps']:
                        for m in LOOP_MODES:
                            if c.get('note_' + m):
                                notes[(kind, m)][c['note_' + m]] += 1
                        if c.get('fil'):
                            times[(kind, 'filaments')].append(c['fil'])
                    if rec.get('peec') and rec['fast'] > 0:
                        ratios[kind].append(rec['peec'] / rec['fast'])
            # pairwise flips among the part's candidates
            costs = {}
            for m in ('fast',) + LOOP_MODES:
                costs[m] = [kind_cost(row, kind, m) for row in rows]
            for how in ('ratio', 'offset', 'hops'):
                costs['fast+' + how] = [kind_cost(row, kind, None, rows[0], how) for row in rows]
            costs['total_fast'] = [kind_cost(row, kind, 'fast', only_kind=False) for row in rows]
            costs['total_peec'] = [kind_cost(row, kind, 'peec', only_kind=False) for row in rows]
            costs['total_fast+ratio'] = [kind_cost(row, kind, None, rows[0], 'ratio', only_kind=False) for row in rows]
            costs['total_fast+offset'] = [kind_cost(row, kind, None, rows[0], 'offset', only_kind=False) for row in rows]
            for a in range(len(rows)):
                for b in range(a + 1, len(rows)):
                    if costs[REF][a] is None or costs[REF][b] is None:
                        continue
                    mat = material(rows[a], rows[b], kind, REF)
                    grp = 'human' if a == 0 else 'other'
                    for A, B in comps_pairs + [('fast+ratio', 'peec'), ('fast+offset', 'peec'), ('fast+hops', 'peec'),
                                               ('total_fast', 'total_peec'), ('total_fast+ratio', 'total_peec'),
                                               ('total_fast+offset', 'total_peec')]:
                        ca, cb = costs[A], costs[B]
                        if None in (ca[a], ca[b], cb[a], cb[b]):
                            continue
                        if not mat:
                            continue
                        da, db = ca[a] - ca[b], cb[a] - cb[b]
                        key = (kind, A, B, grp)
                        pairs[key]['n'] += 1
                        pairs[key]['flip'] += ((da > 0) != (db > 0)) or abs(da) < 1e-15
            valid = [q for q in range(len(rows)) if costs[REF][q] is not None and costs['fast'][q] is not None]
            if len(valid) >= 2:
                spread = max(costs[REF][q] for q in valid) - min(costs[REF][q] for q in valid)
                best_r = min(valid, key=lambda q: costs[REF][q])
                for m in ('fast', 'detour', 'cf', 'fast+hops'):
                    vv = [q for q in valid if costs[m][q] is not None]
                    if len(vv) < 2:
                        continue
                    best_m = min(vv, key=lambda q: costs[m][q])
                    top1[(kind, m)]['n'] += 1
                    top1[(kind, m)]['agree'] += best_m == best_r
                    reg = costs[REF][best_m] - costs[REF][best_r]
                    regret[(kind, m)].append(reg)
                    order = sorted(vv, key=lambda q: costs[m][q])
                    for K in (1, 2, 3):
                        topk[(kind, m, K)]['n'] += 1
                        topk[(kind, m, K)]['hit'] += best_r in order[:K]
                    if spread > 0:
                        regret[(kind, m, 'rel')].append(reg / spread)
        for k in kinds_here:
            boards_with[k] += 1
    lines = [f'boards: {len(recs)} ({len(ok)} ok)', '',
             'flip = two candidates of one part ordered differently, among pairs the reference (peec; fv for thermal) '
             'separates by >= 1% of some allocation; human = pairs with the human pose, other = among perturbations', '']
    summ = dict(pairs={}, top1={}, topk={}, regret={}, times={}, notes={}, ratios={}, boards=dict(boards_with))
    lines.append('| kind | A vs B | pairs (human) | flips (human) | pairs (other) | flips (other) |')
    lines.append('|---|---|---|---|---|---|')
    for kind in KINDS:
        prs = th_pairs if kind == 'thermal' else comps_pairs + [('fast+ratio', 'peec'), ('fast+offset', 'peec'),
                                                               ('fast+hops', 'peec'), ('total_fast', 'total_peec'),
                                                               ('total_fast+ratio', 'total_peec'),
                                                               ('total_fast+offset', 'total_peec')]
        for A, B in prs:
            h = pairs.get((kind, A, B, 'human'), Counter())
            o = pairs.get((kind, A, B, 'other'), Counter())
            if not h['n'] and not o['n']:
                continue
            fh = h['flip'] / h['n'] if h['n'] else float('nan')
            fo = o['flip'] / o['n'] if o['n'] else float('nan')
            lines.append(f'| {kind} | {A} vs {B} | {h["n"]} | {100 * fh:.1f}% | {o["n"]} | {100 * fo:.1f}% |')
            summ['pairs'][f'{kind}|{A}|{B}'] = dict(n_h=h['n'], flip_h=h['flip'], n_o=o['n'], flip_o=o['flip'])
    lines += ['', '| kind | evaluator | parts | top-1 agrees with ref | ref best in top-2 | top-3 | regret median (p90), cost units | regret / spread median (p90) |',
              '|---|---|---|---|---|---|---|---|']
    for key, c in sorted(top1.items()):
        kind, m = key
        if kind == 'thermal':
            k2 = topk[('thermal', m, 2)]
            k3 = topk[('thermal', m, 3)]
            lines.append(f'| thermal | fast vs {m} | {c["n"]} | {100 * c["agree"] / c["n"]:.0f}% | '
                         f'{100 * k2["hit"] / max(1, k2["n"]):.0f}% | {100 * k3["hit"] / max(1, k3["n"]):.0f}% | | |')
            summ['top1'][f'thermal|{m}'] = dict(n=c['n'], agree=c['agree'], top2=k2['hit'], top3=k3['hit'])
            continue
        rg = np.array(regret[(kind, m)])
        rr = np.array(regret.get((kind, m, 'rel'), [0.0]))
        k2 = topk[(kind, m, 2)]
        k3 = topk[(kind, m, 3)]
        lines.append(f'| {kind} | {m} | {c["n"]} | {100 * c["agree"] / c["n"]:.0f}% | '
                     f'{100 * k2["hit"] / max(1, k2["n"]):.0f}% | {100 * k3["hit"] / max(1, k3["n"]):.0f}% | '
                     f'{np.median(rg):.3g} ({np.percentile(rg, 90):.3g}) | {np.median(rr):.2f} ({np.percentile(rr, 90):.2f}) |')
        summ['top1'][f'{kind}|{m}'] = dict(n=c['n'], agree=c['agree'], top2=k2['hit'], top3=k3['hit'],
                                           regret_med=float(np.median(rg)), regret_p90=float(np.percentile(rg, 90)),
                                           rel_med=float(np.median(rr)), rel_p90=float(np.percentile(rr, 90)))
    lines += ['', '| kind | evaluator | evaluations | median ms | p90 ms |', '|---|---|---|---|---|']
    for key in sorted(times):
        v = np.array(times[key])
        if key[1] == 'filaments':
            lines.append(f'| {key[0]} | PEEC filaments | {len(v)} | {np.median(v):.0f} | {np.percentile(v, 90):.0f} |')
            summ['times'][f'{key[0]}|filaments'] = dict(n=len(v), med=float(np.median(v)), p90=float(np.percentile(v, 90)))
            continue
        lines.append(f'| {key[0]} | {key[1]} | {len(v)} | {1e3 * np.median(v):.2f} | {1e3 * np.percentile(v, 90):.2f} |')
        summ['times'][f'{key[0]}|{key[1]}'] = dict(n=len(v), med_ms=float(1e3 * np.median(v)),
                                                   p90_ms=float(1e3 * np.percentile(v, 90)))
    lines += ['', 'peec / fast value ratio per kind (median, p10-p90):']
    for kind, v in ratios.items():
        v = np.array(v)
        lines.append(f'  {kind}: {np.median(v):.3f} ({np.percentile(v, 10):.3f}-{np.percentile(v, 90):.3f}), n {len(v)}')
        summ['ratios'][kind] = dict(n=len(v), med=float(np.median(v)), p10=float(np.percentile(v, 10)),
                                    p90=float(np.percentile(v, 90)))
    lines += ['', 'evaluations without an exact value (reason counts):']
    for key, c in sorted(notes.items()):
        lines.append(f'  {key[0]} {key[1]}: ' + ', '.join(f'{k} {n}' for k, n in c.most_common()))
        summ['notes'][f'{key[0]}|{key[1]}'] = dict(c)
    fvs = [r['fv'] for r in ok if r.get('fv')]
    if fvs:
        lines += ['', f"FV thermal: {len(fvs)} boards, nodes median {np.median([f['nodes'] for f in fvs]):.0f} "
                      f"(max {max(f['nodes'] for f in fvs)}), factor median {np.median([f['t_factor'] for f in fvs]):.2f} s "
                      f"(max {max(f['t_factor'] for f in fvs):.2f} s)"]
        summ['fv'] = fvs
    lines.append(f'candidate errors: {dict(errors)}; boards with candidates: {dict(boards_with)}')
    json.dump(summ, open(os.path.join(out_dir, 'summary.json'), 'w'), indent=1, default=float)
    open(os.path.join(out_dir, 'summary.md'), 'w').write('\n'.join(lines) + '\n')
    print('\n'.join(lines))


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', required=True)
    ap.add_argument('--tasks', default=str(ROOT / 'kae-work-v2' / 'tasks'))
    ap.add_argument('-j', type=int, default=1)
    ap.add_argument('--only', default='')
    ap.add_argument('--seed', type=int, default=1)
    ap.add_argument('--parts', type=int, default=6, help='parts sampled per structure kind and board')
    ap.add_argument('--max-parts', type=int, default=300, help='skip boards with more footprints')
    ap.add_argument('--aggregate-only', action='store_true')
    ap.add_argument('--force', action='store_true')
    a = ap.parse_args(argv)
    os.makedirs(a.out, exist_ok=True)
    if not a.aggregate_only:
        paths = sorted(glob.glob(os.path.join(a.tasks, '*', 'reference', 'board.kicad_pcb')))
        if a.only:
            keys = a.only.split(',')
            paths = [p for p in paths if any(k in p for k in keys)]
        todo = [p for p in paths if a.force or not os.path.exists(os.path.join(a.out, Path(p).parents[1].name + '.json'))]
        t0 = time.time()
        if a.j <= 1:
            for n, p in enumerate(todo, 1):
                try:
                    r = run_board(p, a.out, a.seed, a.parts, a.max_parts)
                except Exception as e:      # noqa: BLE001
                    r = dict(id=Path(p).parents[1].name, status=f'crash {type(e).__name__}: {e}')
                print(f"[{n}/{len(todo)} {time.time() - t0:.0f}s] {r.get('id')}: {r.get('status')} {r.get('seconds', '')} "
                      f"{r.get('cands', '')}", flush=True)
        else:
            with cf.ProcessPoolExecutor(max_workers=a.j) as ex:
                futs = {ex.submit(run_board, p, a.out, a.seed, a.parts, a.max_parts): p for p in todo}
                for n, f in enumerate(cf.as_completed(futs), 1):
                    try:
                        r = f.result()
                    except Exception as e:      # noqa: BLE001
                        r = dict(id=futs[f], status=f'crash {e}')
                    print(f"[{n}/{len(todo)} {time.time() - t0:.0f}s] {r.get('id')}: {r.get('status')} "
                          f"{r.get('seconds', '')}", flush=True)
    aggregate(a.out)


if __name__ == '__main__':
    main()
