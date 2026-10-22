# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Place terms vs the human placement on the kaebench suite (docs/topics/physics/place-terms.md).

For every reference board (kae-work/tasks/*/reference/board.kicad_pcb) this builds the
physics brief (kae.circuit.brief) and the place terms (kae.physics.place_terms) and asks,
per term kind, whether the human placement scores better than its own perturbations:

  local    each involved (unlocked) part, one at a time: translate 1-5 mm in a random
           direction (3 tries), rotate in place by 90, 180 and 270 degrees;
  global   all involved parts of the kind re-placed at random legal-ish poses (shuffle);
  legal-ish: the part's courtyard adds no overlap with same-side courtyards beyond what
           the human placement already has, and stays inside the board outline.

It records the share of perturbations that score worse than the human placement, where
the human boards spend their budgets (utilisation per structure), and every case in which a
local perturbation scores better, classified as either an estimator error or a human
choice:

  estimator: quadrature   the exact-in-model reference (kernels.loop_L: all pairs, oblique
                          pairs by quadrature, lateral return) disagrees in sign;
  estimator: route        the perturbed straight hop crosses another part's courtyard, so
                          the expected route would detour (route model optimistic);
  estimator: assignment   the structure pairs parts the human placed far apart (> 15 mm)
                          while nothing forced it (brief pairing doubtful);
  human: slack            a legal move improves the term and nothing else in the physics
                          gets worse (room the human left);
  human: trade-off        it improves this term but worsens other physics terms or the
                          moved part's signal wirelength (the human balanced them).

Usage:
  python tools/research/physics/pt_human_perturb.py --out kae-work/physics/place-terms/<run> [-j 2]
         [--only id1,id2] [--seed 1] [--local-parts 40] [--shuffles 20]
  python tools/research/physics/pt_human_perturb.py --out DIR --aggregate-only
Needs kae (kae/.venv). Deterministic for a given seed.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
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

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'kae' / 'src'))

import numpy as np  # noqa: E402
import shapely  # noqa: E402
from shapely.geometry import LineString, box  # noqa: E402
from shapely.ops import unary_union  # noqa: E402

KINDS = ('commutation', 'decap', 'coupling', 'crystal', 'thermal', 'esd', 'world_cm', 'antenna')
EPS = 1e-9


# ============================================================================ legality
class Legal:
    """Courtyard overlap and outline checks against the human placement."""

    def __init__(self, T):
        from kae.board.transform import place_geom
        self.place = place_geom
        self.T = T
        bv = T.bv
        self.outline = bv.outline
        self.lib = []
        for p in bv.parts:
            g = unary_union(p.cy_polys) if p.cy_polys else box(*p.cy_bbox)
            self.lib.append(g.buffer(0) if not g.is_valid else g)
        self.geo = {}
        self.side = {}
        for p in bv.parts:
            self.geo[p.i] = self.place(self.lib[p.i], p.x0, p.y0, p.rot0, 'F' if p.side0 > 0 else 'B')
            self.side[p.i] = p.side0
        self._tree()
        self.base_ov = {i: self.overlap(i, self.geo[i], self.side[i]) for i in self.geo}
        self.base_out = {i: self.geo[i].difference(self.outline).area for i in self.geo}

    def _tree(self):
        self.ids = {s: [i for i in self.geo if self.side[i] == s] for s in (1, -1)}
        self.trees = {s: shapely.STRtree([self.geo[i] for i in self.ids[s]]) for s in (1, -1)}

    def overlap(self, i, g, side, extra=()):
        tot = 0.0
        ids = self.ids[1 if side > 0 else -1]
        for k in self.trees[1 if side > 0 else -1].query(g):
            j = ids[k]
            if j == i:
                continue
            a = g.intersection(self.geo[j]).area
            tot += a
        for j, gj, sj in extra:
            if j != i and sj == side:
                tot += g.intersection(gj).area
        return tot

    def at(self, i, pose):
        x, y, r, s = pose
        return self.place(self.lib[i], x, y, r, s)

    def ok(self, i, pose, extra=()):
        g = self.at(i, pose)
        side = -1 if pose[3] == 'B' else 1
        if g.difference(self.outline).area > self.base_out[i] + 0.05:
            return False
        return self.overlap(i, g, side, extra) <= self.base_ov[i] + 0.02


# ============================================================================ helpers
def kind_parts(T, kind):
    if kind == 'thermal':
        return set(T.thermal.parts) if T.thermal is not None else set()
    out = set()
    for s in T.structs:
        if s.kind == kind:
            out |= set(s.members)
    return out


def structs_of_kind(T, kind):
    return [k for k, s in enumerate(T.structs) if s.kind == kind]


def partner_dist(T, poses, i, kind):
    """Mean distance (mm) from part i to the other members of its structures of this kind."""
    st = T.st
    ds = []
    for k in T.inc.get(i, []):
        s = T.structs[k]
        if s.kind != kind:
            continue
        for j in s.members:
            if j != i:
                ds.append(math.hypot(st.X[i] - st.X[j], st.Y[i] - st.Y[j]))
    return float(np.mean(ds)) if ds else float('nan')


def net_hpwl(T, poses, i):
    """Signal-net half-perimeter wirelength of the nets on part i's pads (ground and rails
    excluded), with all parts at the poses in the state."""
    bv = T.bv
    st = T.st
    gnd = getattr(T, '_gnd_nets', set())
    tot = 0.0
    for net in set(bv.parts[i].pad_net):
        if not net or net in gnd or net in T._rail_nets:
            continue
        pins = bv.nets.get(net, [])
        if len(pins) < 2 or len(pins) > 64:
            continue
        xs, ys = [], []
        for j, k in pins:
            p = bv.parts[j]
            c, s, g = st.C[j], st.S[j], st.G[j]
            ly = p.pad_ly[k] * g
            xs.append(st.X[j] + p.pad_lx[k] * c + ly * s)
            ys.append(st.Y[j] - p.pad_lx[k] * s + ly * c)
        tot += max(xs) - min(xs) + max(ys) - min(ys)
    return tot


def loop_reference(T, comp):
    """Exact-in-model reference of a LoopComp at the current state: kernels.loop_L on the
    same straight segments (lateral return; all pairs; oblique pairs by quadrature)."""
    from kae.physics import kernels as K
    from kae.physics.structures import txy
    bv = T.bv
    st = T.st
    P = [txy(st, t) for t in comp.T]
    n = len(P)
    cx = sum(p[0] for p in P) / n
    cy = sum(p[1] for p in P) / n
    side = st.G[comp.T[0].i]
    h = bv.h_ref(side, cx, cy)
    plane = h != float('inf')
    hb = h if plane else 1.0
    segs = []
    for k in range(n):
        a, b = P[k], P[(k + 1) % n]
        if comp.kinds[k] == 'body':
            z = comp.zb[k]
            r = K.gmd_rect(comp.w[k])
            segs.append(dict(p0=(a[0], a[1], hb), p1=(a[0], a[1], hb + z), r=r))
            segs.append(dict(p0=(a[0], a[1], hb + z), p1=(b[0], b[1], hb + z), w=comp.w[k]))
            segs.append(dict(p0=(b[0], b[1], hb + z), p1=(b[0], b[1], hb), r=r))
        else:
            if math.hypot(b[0] - a[0], b[1] - a[1]) > 1e-6:
                segs.append(dict(p0=(a[0], a[1], hb), p1=(b[0], b[1], hb), w=comp.w[k]))
    return K.loop_L(segs, plane=plane)


def crosses_courtyard(T, legal, comp, moved):
    """True when a board hop of the loop that touches a moved part crosses another part's
    courtyard (the router would detour)."""
    from kae.physics.structures import txy
    st = T.st
    P = [txy(st, t) for t in comp.T]
    n = len(P)
    for k in range(n):
        if comp.kinds[k] == 'body':
            continue
        a, b = comp.T[k], comp.T[(k + 1) % n]
        if a.i not in moved and b.i not in moved:
            continue
        seg = LineString([P[k], P[(k + 1) % n]])
        if seg.length < 0.3:
            continue
        side = 1 if st.G[a.i] > 0 else -1
        ids = legal.ids[side]
        for q in legal.trees[side].query(seg):
            j = ids[q]
            if j in (a.i, b.i):
                continue
            g = legal.geo[j] if j not in moved else legal.at(j, st.get(j))
            if g.intersection(seg).length > 0.3:
                return True
    return False


# ============================================================================ per board
def run_board(path, out_dir, seed, n_local, n_shuffle):
    from kae.board.kicad_file import load
    from kae.circuit.brief import build
    from kae.physics.place_terms import Terms
    from kae.physics.structures import LoopComp
    bid = Path(path).parents[1].name
    rng = random.Random(f'{seed}:{bid}')
    t0 = time.time()
    rec = dict(id=bid, status='ok')
    try:
        b = load(path)
        brief = build(b)
        T = Terms(b, brief)
    except Exception as e:      # noqa: BLE001
        rec.update(status='error', error=f'{type(e).__name__}: {e}', trace=traceback.format_exc()[-1500:])
        json.dump(rec, open(os.path.join(out_dir, bid + '.json'), 'w'), indent=1)
        return rec
    bv = T.bv
    T._gnd_nets = {n for n, r in (brief.get('nets') or {}).items() if (r or {}).get('role') == 'ground'}
    T._rail_nets = {n for n, r in (brief.get('nets') or {}).items() if (r or {}).get('role') == 'rail'}
    poses = bv.pose0()
    base = T.total_by_kind(poses)
    legal = Legal(T)
    rec['parts'] = len(bv.parts)
    rec['layers'] = len(bv.copper)
    rec['physics_parts'] = len(T.parts())
    rec['warnings'] = T.warnings[:20]
    # ---- census
    census = []
    for r in T.breakdown(poses):
        census.append(dict(id=r['id'], kind=r['kind'], value=r['value'], unit=r['unit'], alloc=r['alloc']['value'],
                           util=r['util'], conf=r['confidence']))
    rec['census'] = census
    rec['base'] = base
    locked = {p.i for p in bv.parts if p.locked}
    results = defaultdict(lambda: dict(translate=Counter(), rotate=Counter(), shuffle=Counter(), total_local=Counter()))
    better = []
    for kind in KINDS:
        if kind not in base:
            continue
        parts = sorted(kind_parts(T, kind) - locked)
        if not parts:
            continue
        sample = parts if len(parts) <= n_local else rng.sample(parts, n_local)
        for i in sample:
            u = T.uids[i]
            x, y, r, s = poses[u]
            moves = []
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
            for mtype, q in moves:
                dk = T.delta_by_kind(poses, [u], [q])
                dK = dk.get(kind, 0.0)
                tot = sum(dk.values())
                res = 'worse' if dK > EPS else 'better' if dK < -EPS else 'tie'
                results[kind][mtype][res] += 1
                results[kind]['total_local']['worse' if tot > EPS else 'better' if tot < -EPS else 'tie'] += 1
                if res == 'better':
                    better.append(_explain(T, legal, poses, kind, i, u, q, mtype, dK, dk, LoopComp))
        # ---- global shuffles of the kind's parts
        for _ in range(n_shuffle):
            p2 = dict(poses)
            placed = []
            for i in parts:
                u = T.uids[i]
                s = poses[u][3]
                x0, y0, x1, y1 = bv.bbox
                for _try in range(60):
                    q = (rng.uniform(x0, x1), rng.uniform(y0, y1), rng.choice((0.0, 90.0, 180.0, 270.0)), s)
                    if legal.ok(i, q, extra=placed):
                        break
                else:
                    q = poses[u]
                p2[u] = q
                placed.append((i, legal.at(i, q), -1 if s == 'B' else 1))
            new = T.total_by_kind(p2).get(kind, 0.0)
            T.total_by_kind(poses)
            res = 'worse' if new - base[kind] > EPS else 'better' if new - base[kind] < -EPS else 'tie'
            results[kind]['shuffle'][res] += 1
    rec['results'] = {k: {m: dict(c) for m, c in v.items()} for k, v in results.items()}
    rec['better'] = better
    rec['seconds'] = round(time.time() - t0, 1)
    json.dump(rec, open(os.path.join(out_dir, bid + '.json'), 'w'), indent=1, default=float)
    return dict(id=bid, status='ok', seconds=rec['seconds'])


def _explain(T, legal, poses, kind, i, u, q, mtype, dK, dk, LoopComp):
    """Classify one better-than-human local perturbation."""
    bv = T.bv
    st = T.st
    T.total(poses)
    d0 = partner_dist(T, poses, i, kind)
    w0 = net_hpwl(T, poses, i)
    saved = st.get(i)
    # the structures of this kind that changed, with their loop comps
    ks = [k for k in T.inc.get(i, []) if T.structs[k].kind == kind]
    loops = [(k, ci, c) for k in ks for ci, c in enumerate(T.structs[k].comps)
             if isinstance(c, LoopComp) and i in c.parts]
    def lateral(c):
        g = c.g
        c.g = -1
        try:
            return c.value(st)
        finally:
            c.g = g
    ref0 = [loop_reference(T, c) for _, _, c in loops]
    est0 = [lateral(c) for _, _, c in loops]
    st.set(i, *q)
    d1 = partner_dist(T, poses, i, kind)
    w1 = net_hpwl(T, poses, i)
    ref1 = [loop_reference(T, c) for _, _, c in loops]
    est1 = [lateral(c) for _, _, c in loops]
    crosses = any(crosses_courtyard(T, legal, c, {i}) for _, _, c in loops)
    st.set(i, *saved)
    other = sum(v for k2, v in dk.items() if k2 != kind)
    far_pair = False
    for k in ks:
        s = T.structs[k]
        for j in s.members:
            if j != i and math.hypot(bv.parts[i].x0 - bv.parts[j].x0, bv.parts[i].y0 - bv.parts[j].y0) > 15.0:
                far_pair = True
    cat, why = None, ''
    if loops:
        sgn_est = sum(e1 - e0 for e0, e1 in zip(est0, est1))
        sgn_ref = sum(r1 - r0 for r0, r1 in zip(ref0, ref1))
        if sgn_est < 0 <= sgn_ref:
            cat, why = 'estimator: quadrature', f'fast {sgn_est:+.3f} nH, reference {sgn_ref:+.3f} nH (lateral)'
    if cat is None and crosses:
        cat, why = 'estimator: route', 'perturbed hop crosses another courtyard'
    if cat is None and far_pair and kind in ('decap', 'commutation', 'crystal', 'esd'):
        cat, why = 'estimator: assignment', 'members > 15 mm apart in the human placement'
    if cat is None:
        if other > EPS or w1 > w0 + 0.5:
            cat = 'human: trade-off'
            why = f'other physics {other:+.3f}, signal HPWL {w1 - w0:+.1f} mm'
        else:
            cat = 'human: slack'
            why = f'partner distance {d0:.1f} -> {d1:.1f} mm'
    return dict(kind=kind, part=bv.parts[i].ref, move=mtype, dK=dK, d_other=other, cat=cat, why=why,
                partner_mm=[d0, d1], hpwl_mm=[w0, w1], est=[est0, est1], ref=[ref0, ref1],
                structs=[T.structs[k].id for k in ks])


# ============================================================================ aggregate
def aggregate(out_dir):
    recs = []
    for f in sorted(glob.glob(os.path.join(out_dir, '*.json'))):
        if os.path.basename(f).startswith('summary'):
            continue
        recs.append(json.load(open(f)))
    ok = [r for r in recs if r.get('status') == 'ok']
    agg = {k: dict(translate=Counter(), rotate=Counter(), shuffle=Counter(), total_local=Counter()) for k in KINDS}
    cats = defaultdict(Counter)
    census = defaultdict(list)
    boards_with = Counter()
    for r in ok:
        for k, v in (r.get('results') or {}).items():
            boards_with[k] += 1
            for m, c in v.items():
                agg[k][m].update(c)
        for bt in r.get('better', []):
            cats[bt['kind']][bt['cat']] += 1
        for c in r.get('census', []):
            census[c['kind']].append(c)
    lines = [f"boards: {len(recs)} ({len(ok)} ok, {len(recs) - len(ok)} errors)"]
    lines.append('worse = share of decided perturbations (worse + better) that score worse than the human placement')
    lines.append('| term | boards | local translate worse | local rotate worse | shuffle worse | total J worse (local) |')
    lines.append('|---|---|---|---|---|---|')
    summ = {}
    for k in KINDS:
        a = agg[k]

        def share(c):
            n = c['worse'] + c['better']
            return (c['worse'] / n, n, c['tie'] / max(1, n + c['tie'])) if n else (float('nan'), 0, float('nan'))
        st, sr, ss, sj = share(a['translate']), share(a['rotate']), share(a['shuffle']), share(a['total_local'])
        summ[k] = dict(boards=boards_with[k], translate=st, rotate=sr, shuffle=ss, total=sj,
                       better=dict(cats[k]))
        if boards_with[k]:
            lines.append(f"| {k} | {boards_with[k]} | {st[0]:.1%} of {st[1]} (ties {st[2]:.0%}) | "
                         f"{sr[0]:.1%} of {sr[1]} (ties {sr[2]:.0%}) | {ss[0]:.1%} of {ss[1]} | {sj[0]:.1%} |")
    lines.append('')
    lines.append('| term | structures | value median (p90) | utilisation median | p90 | share over budget |')
    lines.append('|---|---|---|---|---|---|')
    for k in KINDS:
        cs = census.get(k, [])
        if not cs:
            continue
        u = np.array([c['util'] for c in cs if np.isfinite(c['util'])])
        v = np.array([c['value'] for c in cs if np.isfinite(c['value'])])
        unit = cs[0]['unit']
        lines.append(f"| {k} | {len(cs)} | {np.median(v):.3g} ({np.percentile(v, 90):.3g}) {unit} | {np.median(u):.3g} | "
                     f"{np.percentile(u, 90):.3g} | {(u > 1).mean():.1%} |")
        summ[k]['census'] = dict(n=len(cs), value_median=float(np.median(v)), value_p90=float(np.percentile(v, 90)),
                                 unit=unit, util_median=float(np.median(u)), util_p90=float(np.percentile(u, 90)),
                                 over=float((u > 1).mean()))
    lines.append('')
    lines.append('better-than-human local perturbations by explanation:')
    for k in KINDS:
        if cats[k]:
            lines.append(f"  {k}: " + ', '.join(f'{c} {n}' for c, n in cats[k].most_common()))
    json.dump(summ, open(os.path.join(out_dir, 'summary.json'), 'w'), indent=1, default=float)
    open(os.path.join(out_dir, 'summary.md'), 'w').write('\n'.join(lines) + '\n')
    print('\n'.join(lines))


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', required=True)
    ap.add_argument('--tasks', default=str(ROOT / 'kae-work' / 'tasks'))
    ap.add_argument('-j', type=int, default=2)
    ap.add_argument('--only', default='')
    ap.add_argument('--seed', type=int, default=1)
    ap.add_argument('--local-parts', type=int, default=40)
    ap.add_argument('--shuffles', type=int, default=20)
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
        with cf.ProcessPoolExecutor(max_workers=a.j) as ex:
            futs = {ex.submit(run_board, p, a.out, a.seed, a.local_parts, a.shuffles): p for p in todo}
            for n, f in enumerate(cf.as_completed(futs), 1):
                try:
                    r = f.result()
                except Exception as e:      # noqa: BLE001
                    r = dict(id=futs[f], status=f'crash {e}')
                print(f"[{n}/{len(todo)} {time.time() - t0:.0f}s] {r.get('id')}: {r.get('status')} {r.get('seconds', '')}",
                      flush=True)
    aggregate(a.out)


if __name__ == '__main__':
    main()
