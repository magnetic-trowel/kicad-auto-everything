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

A perturbation is worse or better by the sign of the kind's cost change; it is *material*
when it moves some structure of the kind by at least 1 % of its allocation (|du| >= 0.01).
Shares are worse / (worse + better), reported over all decided perturbations and over the
material ones. The census records where the human boards spend their budgets (value and
utilisation per structure). Every material local perturbation that scores better than the
human placement is classified:

  estimator: route        loop kinds (decap, commutation, esd): with each board hop routed
                          around other nets' pads (pt_grid_route, 45-degree grid router;
                          L'(w, h) per mm of detour) the perturbation is no longer better;
                          the straight-hop model was optimistic;
  estimator: assignment   the moved part sits > 15 mm from every partner in its structure in
                          the human placement (cap far from the pins it is said to decouple,
                          protector far from its connector): the brief's pairing is doubtful;
  human: trade-off        it improves this term but worsens other physics terms or the moved
                          part's signal wirelength (> 0.5 mm): the human balanced them;
  human: slack            a routable, legal move that improves the term and worsens nothing
                          else in the physics: room the human left.
  (loop kinds whose hop has no single-layer route, e.g. BGA escapes, are 'unroutable'.)

Usage:
  python tools/research/physics/pt_human_perturb.py --out kae-work/physics/place-terms/<run> [-j 2]
         [--only id1,id2] [--seed 1] [--local-parts 40] [--shuffles 20]
  python tools/research/physics/pt_human_perturb.py --out DIR --aggregate-only
Needs kae (kae/.venv). Deterministic for a given seed and brief.
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
sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np  # noqa: E402
import shapely  # noqa: E402
from shapely.geometry import box  # noqa: E402
from shapely.ops import unary_union  # noqa: E402

KINDS = ('commutation', 'decap', 'coupling', 'crystal', 'thermal', 'esd', 'world_cm', 'antenna')
LOOP_KINDS = ('decap', 'commutation', 'esd')
EPS = 1e-9
MATERIAL = 0.01          # |du| of some structure of the kind, fraction of its allocation
FAR_MM = 15.0


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


def kind_values(T, ks, i=None, q=None):
    """Values of structures ks, with part i at pose q when given (direct component
    evaluation; the state is restored)."""
    from kae.physics.place_terms import _red
    st = T.st
    saved = None
    if i is not None:
        saved = st.get(i)
        st.set(i, *q)
    try:
        return [_red(T.structs[k].reduce, [c.value(st) for c in T.structs[k].comps], T.structs[k].info.get('weights'))
                for k in ks]
    finally:
        if saved is not None:
            st.set(i, *saved)


def thermal_rise(T, i=None, q=None):
    """(rise vector K, allocations K) at the state, with part i at pose q when given."""
    th = T.thermal
    T0 = T._th_current()
    al = np.array([a.value for a in T._th_alloc])
    if i is None:
        return T0.copy(), al
    st = T.st
    saved = st.get(i)
    st.set(i, *q)
    try:
        Gn = th.G.copy()
        tix = {j: t for t, j in enumerate(th.targets)}
        t = tix.get(i)
        if t is not None:
            if t < len(th.src):
                Gn[:, t] = th.column(st, t)
            Gn[t, :] = th.row(st, t)
        return Gn @ th.P, al
    finally:
        st.set(i, *saved)


def material_du(T, kind, i, q):
    """Largest |change of utilisation| over the kind's structures touched by moving part i."""
    if kind == 'thermal':
        if T.thermal is None or i not in T.th_parts:
            return 0.0
        a, al = thermal_rise(T)
        b, _ = thermal_rise(T, i, q)
        return float(np.max(np.abs(b - a) / al)) if len(al) else 0.0
    ks = [k for k in T.inc.get(i, ()) if T.structs[k].kind == kind]
    if not ks:
        return 0.0
    v0 = kind_values(T, ks)
    v1 = kind_values(T, ks, i, q)
    return max(abs(b - a) / T.structs[k].alloc.value for k, a, b in zip(ks, v0, v1))


def _nearest_pad(bv, st, t, toward):
    from kae.physics.structures import txy
    if not t.ks:
        return txy(st, t)
    best = None
    for k in t.ks:
        x, y = bv.pad_xy(t.i, k, st.X[t.i], st.Y[t.i], st.R[t.i], st.G[t.i])
        d = math.hypot(x - toward[0], y - toward[1])
        if best is None or d < best[0]:
            best = (d, (x, y))
    return best[1]


def hop_detour_nH(T, R, pads, comp):
    """Extra inductance (nH) of a loop component when its board hops are routed around
    other nets' pads: sum of L'(w, h) x (routed - straight length) over the hops (a ground
    hop returned through its own plane is not routed). 0 for components without board hops;
    None when a hop has no single-layer route."""
    from kae.physics.kernels import lprime_hj
    from kae.physics.structures import EsdComp, LoopComp, txy
    st, bv = T.st, T.bv
    hops = []
    if isinstance(comp, LoopComp):
        n = comp.n
        P = [txy(st, t) for t in comp.T]
        for k in range(n):
            if comp.kinds[k] != 'board':
                continue
            t0, t1 = comp.T[k], comp.T[(k + 1) % n]
            if k == comp.g:
                mx, my = 0.5 * (P[k][0] + P[(k + 1) % n][0]), 0.5 * (P[k][1] + P[(k + 1) % n][1])
                side = st.G[t0.i]
                if bv.h_ref(side, mx, my) != float('inf') and bv.plane_net(side, mx, my) in comp.gnd_nets:
                    continue
            hops.append((t0, t1, comp.w[k]))
    elif isinstance(comp, EsdComp):
        hops.append((comp.tc, comp.tp, comp.w))
    else:
        return 0.0
    extra = 0.0
    for t0, t1, w in hops:
        c1 = txy(st, t1)
        a = _nearest_pad(bv, st, t0, c1)
        b = _nearest_pad(bv, st, t1, a)
        straight = math.hypot(b[0] - a[0], b[1] - a[1])
        if straight < 0.05:
            continue
        L = min(R.length(st, sd, a, b, (t0.net, t1.net), w, pads=pads) for sd in {st.G[t0.i], st.G[t1.i]})
        if not math.isfinite(L):
            return None
        h = bv.h_ref(st.G[t0.i], 0.5 * (a[0] + b[0]), 0.5 * (a[1] + b[1]))
        extra += lprime_hj(w, h if h != float('inf') else bv.thickness) * (L - straight)
    return extra


def routed_cost(T, R, ks, i=None, q=None):
    """Cost of structures ks with route detours added to every loop component (part i at
    pose q when given), or None when some hop is unroutable."""
    from kae.physics.place_terms import _red
    st = T.st
    saved = None
    if i is not None:
        saved = st.get(i)
        st.set(i, *q)
    try:
        pads = R.pads_board(st)
        tot = 0.0
        for k in ks:
            s = T.structs[k]
            vals = []
            for c in s.comps:
                e = hop_detour_nH(T, R, pads, c)
                if e is None:
                    return None
                vals.append(c.value(st) + e)
            tot += T._cost(s, _red(s.reduce, vals, s.info.get('weights')))
        return tot
    finally:
        if saved is not None:
            st.set(i, *saved)


def partner_min_dist(T, i, ks):
    """Distance (mm) from part i to its nearest partner over structures ks, at the state."""
    st = T.st
    d = float('inf')
    for k in ks:
        for j in T.structs[k].members:
            if j != i:
                d = min(d, math.hypot(st.X[i] - st.X[j], st.Y[i] - st.Y[j]))
    return d


def credible(T, s):
    """A structure the human placement treats as local: some component has all its board
    hops (straight, pad to pad) within FAR_MM. A loop the human spread over the board is
    more likely a misidentified structure (wrong cap, wrong owner) than a placement the
    physics should rank."""
    from kae.physics.structures import EsdComp, LoopComp, NearestLoopComp, PlanePairLoop, txy
    st = T.st
    for c in s.comps:
        if isinstance(c, NearestLoopComp):
            x, y = txy(st, c.tr)
            c = min(c.loops, key=lambda L: math.dist(txy(st, L.T[0]), (x, y)))
        if isinstance(c, LoopComp):
            P = [txy(st, t) for t in c.T]
            if max((math.dist(P[k], P[(k + 1) % c.n]) for k in range(c.n) if c.kinds[k] == 'board'),
                   default=0.0) <= FAR_MM:
                return True
        elif isinstance(c, EsdComp):
            if math.dist(txy(st, c.tc), txy(st, c.tp)) <= FAR_MM:
                return True
        elif isinstance(c, PlanePairLoop):
            if math.dist(txy(st, c.tp), txy(st, c.tc[0])) <= FAR_MM:
                return True
        else:
            return True
    return False


# ============================================================================ per board
def run_board(path, out_dir, seed, n_local, n_shuffle):
    from kae.board.kicad_file import load
    from kae.circuit.brief import build
    from kae.physics.place_terms import Terms
    from pt_grid_route import HopRouter
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
    router = HopRouter(bv)
    rec['parts'] = len(bv.parts)
    rec['layers'] = len(bv.copper)
    rec['physics_parts'] = len(T.parts())
    rec['warnings'] = T.warnings[:20]
    # ---- census
    census = []
    for r in T.breakdown(poses):
        c = dict(id=r['id'], kind=r['kind'], value=r['value'], unit=r['unit'], alloc=r['alloc']['value'],
                 util=r['util'], conf=r['confidence'])
        if r['kind'] == 'thermal':
            c.update(rise=r['info']['rise_K'], mean=r['info']['board_mean_K'], role=r['info']['role'],
                     P_W=r['info'].get('P_W'))
        census.append(c)
    T.total(poses)
    cred = {s.id for s in T.structs if credible(T, s)}
    for c in census:
        c['credible'] = c['id'] in cred or c['kind'] == 'thermal'
    rec['census'] = census
    rec['base'] = base

    def kind_cost(p, kind, only_credible):
        if kind == 'thermal' or not only_credible:
            return T.total_by_kind(p).get(kind, 0.0)
        return sum(r['cost'] for r in T.breakdown(p) if r['kind'] == kind and r['id'] in cred)
    locked = {p.i for p in bv.parts if p.locked}
    base_c = {k: kind_cost(poses, k, True) for k in base}
    base_tot = sum(base.values())
    results = defaultdict(lambda: defaultdict(Counter))
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
                T.total(poses)
                du = material_du(T, kind, i, q)
                mat = du >= MATERIAL
                results[kind][mtype][res] += 1
                results[kind][mtype + '_material'][res if mat else 'tie'] += 1
                ks_c = [k for k in T.inc.get(i, ()) if T.structs[k].kind == kind]
                if kind == 'thermal' or (ks_c and all(T.structs[k].id in cred for k in ks_c)):
                    results[kind][mtype + '_credible'][res if mat else 'tie'] += 1
                results[kind]['total_local']['worse' if tot > EPS else 'better' if tot < -EPS else 'tie'] += 1
                if res == 'better' and mat:
                    better.append(_explain(T, router, poses, kind, i, q, mtype, dK, dk, du))
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
            allk = T.total_by_kind(p2)
            new = allk.get(kind, 0.0)
            dtot = sum(allk.values()) - base_tot
            newc = kind_cost(p2, kind, True)
            T.total_by_kind(poses)
            results[kind]['shuffle_total']['worse' if dtot > EPS else 'better' if dtot < -EPS else 'tie'] += 1
            res = 'worse' if new - base[kind] > EPS else 'better' if new - base[kind] < -EPS else 'tie'
            results[kind]['shuffle'][res] += 1
            dc = newc - base_c[kind]
            if kind == 'thermal' or any(r['kind'] == kind for r in census if r['credible']):
                results[kind]['shuffle_credible']['worse' if dc > EPS else 'better' if dc < -EPS else 'tie'] += 1
    rec['results'] = {k: {m: dict(c) for m, c in v.items()} for k, v in results.items()}
    rec['better'] = better
    rec['seconds'] = round(time.time() - t0, 1)
    json.dump(rec, open(os.path.join(out_dir, bid + '.json'), 'w'), indent=1, default=float)
    return dict(id=bid, status='ok', seconds=rec['seconds'])


def _explain(T, router, poses, kind, i, q, mtype, dK, dk, du):
    """Classify one material better-than-human local perturbation."""
    bv = T.bv
    T.total(poses)
    ks = [k for k in T.inc.get(i, []) if T.structs[k].kind == kind]
    d0 = partner_min_dist(T, i, ks) if ks else float('nan')
    w0 = net_hpwl(T, poses, i)
    saved = T.st.get(i)
    T.st.set(i, *q)
    d1 = partner_min_dist(T, i, ks) if ks else float('nan')
    w1 = net_hpwl(T, poses, i)
    T.st.set(i, *saved)
    other = sum(v for k2, v in dk.items() if k2 != kind)
    rc0 = rc1 = None
    cat, why = None, ''
    if kind in LOOP_KINDS and ks:
        rc0 = routed_cost(T, router, ks)
        rc1 = routed_cost(T, router, ks, i, q)
        if rc0 is None or rc1 is None:
            cat, why = 'unroutable', 'a hop has no single-layer route (BGA escape, enclosed pin)'
        elif rc1 - rc0 >= -EPS:
            cat, why = 'estimator: route', f'routed cost change {rc1 - rc0:+.4f} (straight {dK:+.4f})'
    if cat is None and kind in ('decap', 'commutation', 'crystal', 'esd') and d0 > FAR_MM:
        cat, why = 'estimator: assignment', f'nearest partner {d0:.1f} mm away in the human placement'
    if cat is None:
        if other > 1e-6 or w1 > w0 + 0.5:
            cat = 'human: trade-off'
            why = f'other physics {other:+.4f}, signal HPWL {w1 - w0:+.1f} mm'
        else:
            cat = 'human: slack'
            why = f'nearest partner {d0:.1f} -> {d1:.1f} mm'
    return dict(kind=kind, part=bv.parts[i].ref, move=mtype, dK=dK, du=du, d_other=other, cat=cat, why=why,
                credible=kind == 'thermal' or all(credible(T, T.structs[k]) for k in ks),
                partner_mm=[d0, d1], hpwl_mm=[w0, w1], routed=[rc0, rc1],
                structs=[T.structs[k].id for k in ks])


# ============================================================================ aggregate
def _share(c):
    n = c.get('worse', 0) + c.get('better', 0)
    t = c.get('tie', 0)
    return dict(worse=c.get('worse', 0) / n if n else float('nan'), n=n, ties=t / (n + t) if n + t else float('nan'))


def aggregate(out_dir):
    recs = []
    for f in sorted(glob.glob(os.path.join(out_dir, '*.json'))):
        if os.path.basename(f).startswith('summary'):
            continue
        recs.append(json.load(open(f)))
    ok = [r for r in recs if r.get('status') == 'ok']
    agg = {k: defaultdict(Counter) for k in KINDS}
    cats = defaultdict(Counter)
    cats_c = defaultdict(Counter)
    census = defaultdict(list)
    boards_with = Counter()
    for r in ok:
        for k, v in (r.get('results') or {}).items():
            boards_with[k] += 1
            for m, c in v.items():
                agg[k][m].update(c)
        for bt in r.get('better', []):
            cats[bt['kind']][bt['cat']] += 1
            if bt.get('credible'):
                cats_c[bt['kind']][bt['cat']] += 1
        for c in r.get('census', []):
            census[c['kind']].append(c)
    lines = [f"boards: {len(recs)} ({len(ok)} ok, {len(recs) - len(ok)} errors)", '',
             'worse = worse / (worse + better) over decided perturbations; material = some structure moves by '
             f'>= {MATERIAL:.0%} of its allocation (the rest count as ties)', '',
             '| term | boards | translate worse (n) | material (n, ties) | material, credible | rotate worse (n) '
             '| material (n, ties) | material, credible | shuffle worse (n) | shuffle, credible | shuffle, all terms '
             '| all terms, local |',
             '|---|---|---|---|---|---|---|---|---|---|---|---|']
    summ = {}

    def f(x):
        return f"{x['worse']:.0%} ({x['n']})" if x['n'] else '-'

    def fm(x):
        return f"{x['worse']:.0%} ({x['n']}, {x['ties']:.0%})" if x['n'] else f"- (0, {x['ties']:.0%})"
    for k in KINDS:
        a = agg[k]
        sh = {m: _share(a[m]) for m in ('translate', 'translate_material', 'translate_credible', 'rotate',
                                       'rotate_material', 'rotate_credible', 'shuffle', 'shuffle_credible',
                                       'shuffle_total', 'total_local')}
        summ[k] = dict(boards=boards_with[k], **sh, better=dict(cats[k]))
        if boards_with[k]:
            lines.append(f"| {k} | {boards_with[k]} | {f(sh['translate'])} | {fm(sh['translate_material'])} | "
                         f"{fm(sh['translate_credible'])} | {f(sh['rotate'])} | {fm(sh['rotate_material'])} | "
                         f"{fm(sh['rotate_credible'])} | {f(sh['shuffle'])} | {f(sh['shuffle_credible'])} | "
                         f"{f(sh['shuffle_total'])} | {f(sh['total_local'])} |")
    lines += ['', '| term | structures (credible) | value median (p90) | utilisation median | p90 | share over budget |',
              '|---|---|---|---|---|---|']
    for k in KINDS:
        cs = census.get(k, [])
        if not cs:
            continue
        u = np.array([c['util'] for c in cs if np.isfinite(c['util'])])
        v = np.array([c['value'] for c in cs if np.isfinite(c['value'])])
        unit = cs[0]['unit']
        ncred = sum(1 for c in cs if c.get('credible', True))
        lines.append(f"| {k} | {len(cs)} ({ncred}) | {np.median(v):.3g} ({np.percentile(v, 90):.3g}) {unit} | {np.median(u):.3g} | "
                     f"{np.percentile(u, 90):.3g} | {(u > 1).mean():.1%} |")
        summ[k]['census'] = dict(n=len(cs), value_median=float(np.median(v)), value_p90=float(np.percentile(v, 90)),
                                 unit=unit, util_median=float(np.median(u)), util_p90=float(np.percentile(u, 90)),
                                 over=float((u > 1).mean()))
    th = census.get('thermal', [])
    if th:
        means = {}
        for r in ok:
            for c in r.get('census', []):
                if c['kind'] == 'thermal' and c.get('mean') is not None:
                    means[r['id']] = c['mean']
        src = [c for c in th if c.get('role') == 'source']
        vic = [c for c in th if c.get('role') == 'victim']
        mv = np.array(list(means.values()))

        def q(v):
            v = np.array(v, float)
            return f"median {np.median(v):.3g}, p90 {np.percentile(v, 90):.3g}, max {v.max():.3g}" if len(v) else '-'
        lines += ['', 'predicted temperature rise on the human boards (K; fin kernel, h = 10 W/m^2K per side):',
                  f"  board mean rise (placement-invariant), {len(mv)} boards: {q(mv)}",
                  f"  sources, absolute rise ({len(src)}): {q([c['rise'] for c in src])}; local excess: "
                  f"{q([c['value'] for c in src])}",
                  f"  victims, absolute rise ({len(vic)}): {q([c['rise'] for c in vic])}; local excess: "
                  f"{q([c['value'] for c in vic])}"]
        summ.setdefault('thermal', {})['rise'] = dict(board_mean=list(map(float, mv)),
                                                      source_abs=[c['rise'] for c in src],
                                                      source_local=[c['value'] for c in src],
                                                      victim_abs=[c['rise'] for c in vic],
                                                      victim_local=[c['value'] for c in vic])
    lines += ['', 'material better-than-human local perturbations by explanation (credible structures in brackets):']
    for k in KINDS:
        if cats[k]:
            lines.append(f"  {k}: " + ', '.join(f'{c} {n} [{cats_c[k][c]}]' for c, n in cats[k].most_common()))
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
