# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Can a cheap correction learned from exact solves remove the decision flips?
(docs/topics/physics/exact-physics-options.md, designs f and h)

Reads the candidates of ex_decision_flips.py (every candidate pose with its fast and PEEC
values per loop component) and, for each candidate, computes features that need no routing:

  per board hop of the component: straight length, the length of the straight segment that
  crosses other nets' pads on its side (pads inflated by half the minimum track width plus the
  clearance, as the router's obstacles), the number of such pads, w and h;
  per component: fast value, hop count, own-plane return, kind.

Two corrections of the fast value, trained leave-one-board-out on log(PEEC / fast) per
component (ridge regression, numpy):

  blocked  physics-shaped: fast + kappa L'(w, h) x blocked length (one coefficient per kind,
           least squares), i.e. a lazy detour that only looks at pads the straight hop crosses;
  ridge    a residual surrogate on all features (log-linear).

For each, the decision flips against PEEC among each part's candidates are recounted exactly as
ex_decision_flips.aggregate counts them (same materiality), next to fast and to the routed
detour.

Usage:  python tools/research/physics/ex_surrogate.py --flips kae-work/physics/exact-options/flips
        [--out kae-work/physics/exact-options/surrogate]
"""
from __future__ import annotations

import argparse
import glob
import json
import math
import os
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / 'kae' / 'src'))
sys.path.insert(0, str(HERE))

import numpy as np  # noqa: E402

LOOP = ('commutation', 'decap', 'esd')


def seg_rect_len(a, b, r):
    """Length of segment a-b inside the axis-aligned rectangle r = (x0, y0, x1, y1)."""
    (ax, ay), (bx, by) = a, b
    t0, t1 = 0.0, 1.0
    dx, dy = bx - ax, by - ay
    for p, q in ((-dx, ax - r[0]), (dx, r[2] - ax), (-dy, ay - r[1]), (dy, r[3] - ay)):
        if abs(p) < 1e-15:
            if q < 0:
                return 0.0
        else:
            t = q / p
            if p < 0:
                t0 = max(t0, t)
            else:
                t1 = min(t1, t)
    return max(0.0, t1 - t0) * math.hypot(dx, dy)


def features(bid, cands):
    """[(kind, part, row index, struct id, comp index, feature dict)] for one board."""
    import ex_exact as X
    from kae.board.kicad_file import load
    from kae.circuit.brief import build
    from kae.physics.place_terms import Terms
    from kae.physics.structures import EsdComp, LoopComp, NearestLoopComp
    from pt_grid_route import HopRouter
    path = ROOT / 'kae-work-v2' / 'tasks' / bid / 'reference' / 'board.kicad_pcb'
    b = load(str(path))
    T = Terms(b, build(b))
    bv = T.bv
    T.total(bv.pose0())
    hr = HopRouter(bv)
    ref2i = {p.ref: p.i for p in bv.parts}
    sid2k = {s.id: k for k, s in enumerate(T.structs)}
    st = T.st
    out = []
    for ci, cand in enumerate(cands):
        if cand['kind'] not in LOOP:
            continue
        i = ref2i.get(cand['part'])
        if i is None:
            continue
        for ri, row in enumerate(cand['rows']):
            if 'structs' not in row:
                continue
            saved = st.get(i)
            st.set(i, *row['pose'])
            px, py, hx, hy, G = hr.pads_board(st)
            try:
                for sid, rec in row['structs'].items():
                    if rec['kind'] != cand['kind'] or sid not in sid2k:
                        continue
                    s = T.structs[sid2k[sid]]
                    for c_idx, c in enumerate(s.comps):
                        if isinstance(c, (LoopComp, NearestLoopComp)):
                            lc = X.loop_comps(c, st)
                            hops = X.board_hops(T, lc)
                            terms = lc.T
                            nets = [(terms[k].net, terms[(k + 1) % lc.n].net) for k, *_ in hops]
                            side = st.G[terms[0].i]
                        elif isinstance(c, EsdComp):
                            a = X._nearest_pad(bv, st, c.tc, X.txy(st, c.tp))
                            bb = X._nearest_pad(bv, st, c.tp, a)
                            side = st.G[c.tp.i]
                            h = bv.h_ref(side, *bb)
                            hops = [(0, a, bb, c.w, False, h)]
                            nets = [(c.tc.net, c.tp.net)]
                        else:
                            continue
                        f = dict(kind=s.kind, fast=rec['comps'][c_idx]['fast'], peec=rec['comps'][c_idx].get('peec'),
                                 nhops=len(hops), straight=0.0, blocked=0.0, nblock=0, own=0, lp_blocked=0.0,
                                 h=None, w=0.0)
                        infl = 0.5 * bv.track_min + bv.clearance
                        for (k, a, bb, w, own, h), nn in zip(hops, nets):
                            L = math.hypot(bb[0] - a[0], bb[1] - a[1])
                            f['straight'] += L
                            f['own'] += int(own)
                            f['h'] = h if h != float('inf') else 1.6
                            f['w'] = max(f['w'], w)
                            if own or L < 1e-6:
                                continue
                            own_ids = {hr.net_id.get(n, -1) for n in nn}
                            on = hr.tht | (G == side)
                            x0, x1 = min(a[0], bb[0]), max(a[0], bb[0])
                            y0, y1 = min(a[1], bb[1]), max(a[1], bb[1])
                            sel = on & ~np.isin(hr.nid, list(own_ids)) & (px + hx + infl >= x0) & (px - hx - infl <= x1) & \
                                (py + hy + infl >= y0) & (py - hy - infl <= y1)
                            blk = 0.0
                            nb = 0
                            for cx, cy, ex, ey in zip(px[sel], py[sel], hx[sel] + infl, hy[sel] + infl):
                                ln = seg_rect_len(a, bb, (cx - ex, cy - ey, cx + ex, cy + ey))
                                if ln > 0:
                                    blk += ln
                                    nb += 1
                            f['blocked'] += blk
                            f['nblock'] += nb
                            from kae.physics.kernels import lprime_hj
                            f['lp_blocked'] += lprime_hj(w, h if h != float('inf') else 1.6) * blk
                        out.append((ci, ri, sid, c_idx, f))
            finally:
                st.set(i, *saved)
    return out


def design(fs):
    X = []
    for f in fs:
        X.append([1.0, math.log(max(f['fast'], 1e-6)), math.log(max(f['straight'], 0.05)), f['blocked'],
                  math.log1p(f['blocked']), f['nblock'], f['own'], math.log(max(f['h'] or 1.6, 0.05)),
                  math.log(max(f['w'], 0.05)), f['nhops'], f['lp_blocked'] / max(f['fast'], 1e-6)])
    return np.array(X)


def ridge(X, y, lam=1e-2):
    mu = X[:, 1:].mean(0)
    sd = X[:, 1:].std(0) + 1e-9
    Z = np.c_[X[:, :1], (X[:, 1:] - mu) / sd]
    A = Z.T @ Z + lam * len(y) * np.diag([0.0] + [1.0] * (Z.shape[1] - 1))
    w = np.linalg.solve(A, Z.T @ y)
    return lambda Xn: np.c_[Xn[:, :1], (Xn[:, 1:] - mu) / sd] @ w


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--flips', default=str(ROOT / 'kae-work' / 'physics' / 'exact-options' / 'flips'))
    ap.add_argument('--out', default=str(ROOT / 'kae-work' / 'physics' / 'exact-options' / 'surrogate'))
    a = ap.parse_args(argv)
    os.makedirs(a.out, exist_ok=True)
    import ex_decision_flips as D
    feats = {}
    recs = {}
    t0 = time.time()
    for f in sorted(glob.glob(os.path.join(a.flips, '*.json'))):
        if os.path.basename(f).startswith('summary'):
            continue
        r = json.load(open(f))
        if r.get('status') != 'ok' or not any(c['kind'] in LOOP for c in r.get('candidates', [])):
            continue
        cache = os.path.join(a.out, r['id'] + '.feat.json')
        if os.path.exists(cache):
            fl = json.load(open(cache))
        else:
            fl = features(r['id'], r['candidates'])
            json.dump(fl, open(cache, 'w'), default=float)
        feats[r['id']] = fl
        recs[r['id']] = r
    print(f'features for {len(feats)} boards ({time.time() - t0:.0f} s)', flush=True)
    boards = sorted(feats)
    # leave-one-board-out predictions of log(peec / fast) per component
    pred = {b: {} for b in boards}
    kappa_all = {}
    for kind in LOOP:
        for b in boards:
            tr = [f for bb in boards if bb != b for (_, _, _, _, f) in feats[bb]
                  if f['kind'] == kind and f['peec'] and f['fast'] > 0]
            te = [(ci, ri, sid, cj, f) for (ci, ri, sid, cj, f) in feats[b] if f['kind'] == kind and f['fast'] > 0]
            if len(tr) < 20 or not te:
                continue
            y = np.array([math.log(f['peec'] / f['fast']) for f in tr])
            model = ridge(design(tr), y)
            # blocked: peec - fast ~ c0 fast + kappa lp_blocked (least squares)
            A = np.array([[f['fast'], f['lp_blocked']] for f in tr])
            yy = np.array([f['peec'] - f['fast'] for f in tr])
            coef = np.linalg.lstsq(A, yy, rcond=None)[0]
            kappa_all.setdefault(kind, []).append(coef.tolist())
            pr = model(design([f for *_, f in te]))
            for (ci, ri, sid, cj, f), p in zip(te, pr):
                pred[b][(ci, ri, sid, cj)] = (f['fast'] * math.exp(p), f['fast'] * (1 + coef[0]) + coef[1] * f['lp_blocked'])
    # recount flips with the corrected component values
    from kae.physics.place_terms import _red
    cnt = defaultdict(Counter)
    for b in boards:
        r = recs[b]
        for ci, cand in enumerate(r['candidates']):
            kind = cand['kind']
            if kind not in LOOP:
                continue
            rows = [x for x in cand['rows'] if 'error' not in x]
            if len(rows) < 2:
                continue
            costs = defaultdict(list)
            for ri, row in enumerate(cand['rows']):
                if 'error' in row:
                    continue
                for m in ('fast', 'detour', 'peec', 'ridge', 'blocked'):
                    tot = 0.0
                    for sid, rec in row['structs'].items():
                        if rec['kind'] != kind:
                            continue
                        if m in ('ridge', 'blocked'):
                            vals = []
                            for cj, c in enumerate(rec['comps']):
                                pv = pred[b].get((ci, ri, sid, cj))
                                vals.append(c['fast'] if pv is None else pv[0 if m == 'ridge' else 1])
                            v = float(_red(rec.get('reduce', 'parallel'), vals))
                        else:
                            v = rec.get(m)
                        c = D.struct_cost(rec, v)
                        if c is None:
                            tot = None
                            break
                        tot += c
                    costs[m].append(tot)
            for x in range(len(rows)):
                for y in range(x + 1, len(rows)):
                    if costs['peec'][x] is None or costs['peec'][y] is None:
                        continue
                    if not D.material(rows[x], rows[y], kind, 'peec'):
                        continue
                    db = costs['peec'][x] - costs['peec'][y]
                    grp = 'human' if x == 0 else 'other'
                    for m in ('fast', 'detour', 'ridge', 'blocked'):
                        if costs[m][x] is None or costs[m][y] is None:
                            continue
                        da = costs[m][x] - costs[m][y]
                        cnt[(kind, m, grp)]['n'] += 1
                        cnt[(kind, m, grp)]['flip'] += ((da > 0) != (db > 0)) or abs(da) < 1e-15
    lines = ['| kind | evaluator | pairs (human) | flips (human) | pairs (other) | flips (other) |', '|---|---|---|---|---|---|']
    summ = {}
    for kind in LOOP:
        for m in ('fast', 'detour', 'blocked', 'ridge'):
            h = cnt[(kind, m, 'human')]
            o = cnt[(kind, m, 'other')]
            if not h['n'] and not o['n']:
                continue
            lines.append(f"| {kind} | {m} | {h['n']} | {100 * h['flip'] / max(1, h['n']):.1f}% | {o['n']} | "
                         f"{100 * o['flip'] / max(1, o['n']):.1f}% |")
            summ[f'{kind}|{m}'] = dict(n_h=h['n'], flip_h=h['flip'], n_o=o['n'], flip_o=o['flip'])
    for kind, cs in kappa_all.items():
        cs = np.array(cs)
        lines.append(f'{kind}: blocked fit (c0, kappa) median {np.median(cs[:, 0]):.3f}, {np.median(cs[:, 1]):.2f}')
    json.dump(summ, open(os.path.join(a.out, 'summary.json'), 'w'), indent=1)
    open(os.path.join(a.out, 'summary.md'), 'w').write('\n'.join(lines) + '\n')
    print('\n'.join(lines))


if __name__ == '__main__':
    main()
