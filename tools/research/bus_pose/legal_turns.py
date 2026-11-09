#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""How many of the rotation turns of placement.md section 4.3 are legal?

For stored placements (kae staged control runs and the human placement of the same boards), for
every bus the campaign analysis called `moved` (extract.py's buses, n >= 6, both levels): the
best rotation pair for planarity and for length, computed on the Problem (pin tables), and
whether the turns it needs are legal. Legality as kae's placer defines it: movable, grid
occupancy (kae.place.state rectangles against every other part, fixed obstacles and the
outline), then the exact polygon check. Also the HPWL the turned part's other nets lose and,
where the board has place terms, whether physics worsens.

Usage: legal_turns.py JOBS.jsonl OUT.jsonl   (one JSON per line: {"board": id, "runs": [...]}).
Human placements are diagnostics here: nothing in kae reads them.
"""
import glob, gzip, json, os, shutil, sys, tempfile, traceback, warnings

warnings.simplefilter('ignore')
import numpy as np  # noqa: E402

BASE = os.path.expanduser('~/kae-baselines/boards')
CORPUS = os.path.expanduser('~/kae-boards/boards')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
HERE = os.path.dirname(os.path.abspath(__file__))


def load_run(run, board_id, tmp):
    from kae.board.kicad_file import load
    d = tempfile.mkdtemp(dir=tmp)
    q = os.path.join(d, 'board.kicad_pcb')
    with gzip.open(os.path.join(run, 'output.kicad_pcb.gz'), 'rb') as f, open(q, 'wb') as g:
        shutil.copyfileobj(f, g)
    for ext in ('kicad_pro', 'kicad_dru'):
        s = f'{CORPUS}/{board_id}/board.{ext}'
        if os.path.exists(s):
            shutil.copy(s, os.path.join(d, f'board.{ext}'))
    b = load(q)
    shutil.rmtree(d, ignore_errors=True)
    return b


def state_of(P, b):
    from kae.place.state import State
    from kae.board import transform
    st = State(P)
    for p in P.parts:
        if not p.movable:
            continue
        fp = p.fp
        X, Y = P.grid_of(fp.x, fp.y)
        rots = [r.rot for r in p.rots]
        k = min(range(len(rots)), key=lambda kk: min(abs(rots[kk] - fp.rot) % 360, 360 - abs(rots[kk] - fp.rot) % 360))
        st.X[p.i], st.Y[p.i], st.K[p.i] = X, Y, k
    return st


def analyse_run(job, run, H, tmp):
    from kae.place import buspose as BP
    from kae.place.problem import Problem
    from kae.place.stubs import make_brief, make_terms
    from kae.place.exact import ExactModel
    from kae.place.pipeline import _net_kinds
    import busmetrics as X
    bid = job['board']
    b = load_run(run, bid, tmp)
    # the task's fixed parts: locked in the kae output; for the human board, the job's `locked` refs
    locked_refs = set(job.get('locked') or ())
    if run == job.get('human'):
        import dataclasses
        b = dataclasses.replace(b, footprints=[dataclasses.replace(f, locked=(f.ref in locked_refs)) for f in b.footprints])
    else:
        locked_refs |= {f.ref for f in b.footprints if f.locked}
    brief = {}
    try:
        brief, _ = make_brief(b)
    except Exception:
        pass
    P = Problem.build(b, net_kinds=_net_kinds(brief), held={f.uuid for f in b.footprints if f.edge_cuts})
    st = state_of(P, b)
    terms = None
    try:
        if (brief or {}).get('structures'):
            terms, _ = make_terms(b, brief, barrier=0.0, u_sat=3.0)
    except Exception:
        terms = None
    # buses as extract.py: the human board's detection, by ref and pad index
    buses, _ = X.detect(H)
    name = {f.ref: i for i, f in enumerate(b.footprints)}
    occ = BP.Occupancy(P, st)
    em = ExactModel(P, st)
    ropt = dict(job=job['board'], run=os.path.basename(run))
    tp = {p.uuid: p for p in P.parts}
    poses = {p.uuid: st.pose(p.i) for p in P.parts} if terms is not None else None
    tparts = set(terms.parts()) if terms is not None else set()
    out = []
    netw = {}
    for B in buses:
        try:
            a, b_ = name[B['a']], name[B['b']]
        except KeyError:
            continue
        pa, pb = [], []
        pa_idx, pb_idx = [], []
        nets_all = set()
        for ln in B['lines']:
            pa_idx.append(ln['pa']); pb_idx.append(ln['pb'])
        pa_idx = np.array(pa_idx, int); pb_idx = np.array(pb_idx, int)
        if pa_idx.max() >= len(P.parts[a].rots[0].pins) or pb_idx.max() >= len(P.parts[b_].rots[0].pins):
            continue
        Bu = BP.Bus(a, b_, pa_idx, pb_idx, [], [])
        bus_nets = {P.parts[a].pad_net[k] for k in pa_idx} | {P.parts[b_].pad_net[k] for k in pb_idx}
        ka0 = int(st.K[a]) if P.parts[a].movable else 0
        kb0 = int(st.K[b_]) if P.parts[b_].movable else 0
        doma = list(range(getattr(P.parts[a], 'n_ortho', len(P.parts[a].rots)))) if P.parts[a].movable else [0]
        domb = list(range(getattr(P.parts[b_], 'n_ortho', len(P.parts[b_].rots)))) if P.parts[b_].movable else [0]
        tab = {}
        for ka in doma:
            for kb in domb:
                lis, lds, L = BP.table(P, st, Bu, ka, kb)
                tab[(ka, kb)] = (lis, lds, L)
        lis0, lds0, L0 = tab[(ka0, kb0)]
        # planarity first
        best_lis = max(tab.items(), key=lambda t: (round(t[1][0], 9), -t[1][2]))
        best_L = min(tab.items(), key=lambda t: (t[1][2], -t[1][0]))

        def legal_part(i, k):
            k0 = int(st.K[i]) if P.parts[i].movable else 0
            if k == k0:
                return dict(status='same', nudge=0, foreign=0.0, physics=0.0)
            p = P.parts[i]
            if not p.movable:
                return dict(status='fixed')
            X0, Y0 = BP.turned_origin(P, st, i, k)
            res = dict(status='grid')
            for r_mm in (0.0, 0.5, 1.0, 2.0):
                done = False
                for dx, dy in BP._nudges(int(round(r_mm / P.g))):
                    if (dx * dx + dy * dy) * P.g * P.g > r_mm * r_mm + 1e-9:
                        continue
                    if occ.legal(i, X0 + dx, Y0 + dy, k):
                        res = dict(status='grid_ok', nudge=r_mm, X=X0 + dx, Y=Y0 + dy)
                        done = True
                        break
                if done:
                    break
            if res['status'] != 'grid_ok':
                return res
            old = (int(st.X[i]), int(st.Y[i]), int(st.K[i]))
            base = {(f['type'], tuple(f['refs'])) for f in em.check(parts=[i])}
            em.set_pose(i, res['X'], res['Y'], k)
            findings = em.check(parts=[i])
            new = [f for f in findings if (f['type'], tuple(f['refs'])) not in base]
            phys = 0.0
            if terms is not None and p.uuid in tparts:
                phys = float(terms.delta(poses, [p.uuid], {p.uuid: st.pose(i)}))
            foreign = BP.foreign_hpwl_delta(P, st, i, k, bus_nets) if False else 0.0
            em.set_pose(i, *old)
            res.update(status='legal' if not new else 'exact', new=[f['type'] for f in new][:4], physics=phys,
                       foreign=BP.foreign_hpwl_delta(P, st, i, k, bus_nets))
            return res

        def combo_status(ka, kb):
            la = legal_part(a, ka); lb = legal_part(b_, kb)
            good = lambda s: s['status'] in ('same', 'legal')
            return la, lb, good(la) and good(lb)

        la, lb, ok_lis = combo_status(*best_lis[0])
        la2, lb2, ok_L = combo_status(*best_L[0])
        # best legal combos, nudge limit 1 mm, physics not worsened
        best_legal_lis = best_legal_L = None
        for key in sorted(tab, key=lambda k: (-round(tab[k][0], 9), tab[k][2])):
            A, B2, ok = combo_status(*key)
            nud_ok = (A.get('nudge', 0) <= 1.0) and (B2.get('nudge', 0) <= 1.0)
            if ok and nud_ok:
                if best_legal_lis is None:
                    best_legal_lis = key
                    break
        for key in sorted(tab, key=lambda k: (tab[k][2], -tab[k][0])):
            A, B2, ok = combo_status(*key)
            nud_ok = (A.get('nudge', 0) <= 1.0) and (B2.get('nudge', 0) <= 1.0)
            if ok and nud_ok:
                best_legal_L = key
                break
        r = dict(ropt, bus=buses.index(B), level=B['level'], n=Bu.n, a=B['a'], b=B['b'],
                 a_movable=P.parts[a].movable, b_movable=P.parts[b_].movable, a_pads=int(sum(1 for j in P.parts[a].pad_net if j >= 0)), b_pads=int(sum(1 for j in P.parts[b_].pad_net if j >= 0)),
                 lis0=lis0, lds0=lds0, L0=L0, doms=[len(doma), len(domb)],
                 best_lis=dict(key=best_lis[0], lis=best_lis[1][0], lds=best_lis[1][1], L=best_lis[1][2], a=la, b=lb, legal=ok_lis),
                 best_L=dict(key=best_L[0], lis=best_L[1][0], lds=best_L[1][1], L=best_L[1][2], a=la2, b=lb2, legal=ok_L),
                 legal_lis=None if best_legal_lis is None else dict(key=best_legal_lis, lis=tab[best_legal_lis][0], lds=tab[best_legal_lis][1], L=tab[best_legal_lis][2]),
                 legal_L=None if best_legal_L is None else dict(key=best_legal_L, lis=tab[best_legal_L][0], lds=tab[best_legal_L][1], L=tab[best_legal_L][2]))
        out.append(r)
    return out


def main():
    tmp = os.environ.get('BUS_TMP') or tempfile.mkdtemp()
    os.makedirs(tmp, exist_ok=True)
    import busmetrics as X
    with open(sys.argv[2], 'a') as out:
        for line in open(sys.argv[1]):
            job = json.loads(line)
            try:
                H = X.read(job['human'])
                for run in job['runs']:
                    try:
                        for r in analyse_run(job, run, H, tmp):
                            out.write(json.dumps(r, default=lambda o: o.tolist() if hasattr(o, 'tolist') else str(o)) + '\n')
                    except Exception:
                        traceback.print_exc()
                        print('ERR', job['board'], run, file=sys.stderr)
                out.flush()
            except Exception:
                traceback.print_exc()
                print('FAIL', job['board'], file=sys.stderr)


if __name__ == '__main__':
    main()
