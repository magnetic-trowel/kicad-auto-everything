# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Placement terms: fast, incremental estimators of what a placement does to each physical
budget (Contract 3 of docs/topics/architecture/month-plan.md).

    t = Terms(board, brief)            # board: kae.board.model.Board; brief: Contract 2 dict
    t.total(poses)                     # poses: {footprint uuid: (x, y, rot, 'F'|'B')}
    t.delta(poses, moved_uuids, new_poses)   # change of total if moved parts take new poses
    t.breakdown(poses)                 # per structure: value, unit, allocation, utilisation
    t.parts()                          # uuids any term touches
    t.structures_of(uuid)              # ids of the structures a part belongs to

One currency: each structure reports spend / allocation (utilisation u); the objective is
sum_s c_s phi(u_s) with c_s the brief's confidence and phi(u) = u + beta max(0, u-1)^2 up to
u_sat = 10, logarithmic beyond
(knobs in priors.Knobs). Allocations come from the brief's budgets or, when absent, from
the E5 priors in kae.physics.priors. Terms:

  commutation  (a) hot-loop inductance (nH) vs the overshoot budget
  decap        (b) decoupling-loop inductance per IC power-pin cluster (nH) vs target impedance
  coupling     (c) aggressor-victim noise (mV), inductive M di/dt + capacitive C dv/dt
  crystal      (d) Pierce load pulling from trace capacitance (ppm)
  thermal      (e) local temperature rise above the board mean at sensitive parts and sources (K)
  world        (f) cable common-mode current (uA), ESD path inductance (nH), antenna feed (dB)

Routability (wirelength, congestion, escape) is not here: it lives in kae.place.cost.

Incrementality: every structure is a reduction of components that depend on a few parts.
A component's cached value is valid while the pose epochs of its parts are unchanged;
`delta` re-reads the poses of the touched structures' members from `poses` (identity, then
equality), so callers may mutate their pose dict freely between calls.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from . import priors as PR
from .boardview import BoardView
from .structures import (CmComp, CouplingComp, CrystalComp, EsdComp, FeedComp, LoopComp, LoopShape,
                         NodeShape, PlanePairLoop, State, Term, ThermalField)

INF = float('inf')


@dataclass
class Struct:
    id: str
    kind: str
    conf: float
    alloc: PR.Belief
    comps: list
    reduce: str = 'single'          # single | sum | parallel
    members: tuple = ()
    labels: list = field(default_factory=list)   # per component, for breakdown
    info: dict = field(default_factory=dict)


def _red(kind, vals, weights=None):
    if kind == 'sum':
        return sum(vals)
    if kind == 'parallel':
        inv = sum(1.0 / v for v in vals if v > 1e-12)
        return 1.0 / inv if inv > 0 else INF
    if kind == 'wparallel':
        # expected admittance over alternatives present with probability w
        inv = sum(w / v for v, w in zip(vals, weights) if v > 1e-12)
        return 1.0 / inv if inv > 0 else INF
    if kind == 'max':
        return max(vals) if vals else 0.0
    return vals[0] if vals else 0.0


class Terms:
    def __init__(self, board, brief=None, knobs=None):
        self.bv = board if isinstance(board, BoardView) else BoardView.from_board(board)
        self.knobs = knobs or PR.Knobs()
        if brief is None:
            from .provisional_brief import provisional_brief
            brief = provisional_brief(board)
        self.brief = brief
        bv = self.bv
        n = len(bv.parts)
        self.st = State(n)
        self.uids = [p.uuid for p in bv.parts]
        self.u2i = {u: i for i, u in enumerate(self.uids) if u}
        for p in bv.parts:
            self.st.set(p.i, p.x0, p.y0, p.rot0, p.side0)
        self.structs: list[Struct] = []
        self.thermal = None
        self.warnings = []
        self.kern = None
        from .build import build_structures
        build_structures(self)
        if self.structs or self.thermal is not None:
            # JIT kernels only when some term needs them; each compiles (or loads from
            # numba's on-disk cache) on its first call, not here
            from . import jit as _jit
            if self.knobs.jit == 'on' or (self.knobs.jit == 'auto' and _jit.enabled()):
                self.kern = _jit.nb()
                for s in self.structs:
                    for c in s.comps:
                        if hasattr(c, 'kern'):
                            c.kern = self.kern
                if self.thermal is not None:
                    self.thermal.kern = self.kern
        # incidence
        self.inc = {}
        for k, s in enumerate(self.structs):
            mem = set()
            for c in s.comps:
                mem |= set(c.parts)
            s.members = tuple(sorted(mem))
            for i in s.members:
                self.inc.setdefault(i, []).append(k)
        self.th_parts = set(self.thermal.parts) if self.thermal is not None else set()
        for s in self.structs:
            cof = {}
            for ci, c in enumerate(s.comps):
                for i in c.parts:
                    cof.setdefault(i, []).append(ci)
            s.info['_cof'] = cof
        self._last = [None] * n
        self._epoch = [0] * n
        self._ccache = [[None] * len(s.comps) for s in self.structs]
        self._scache = [None] * len(self.structs)
        self._th_epochs = None
        self._th_T = None

    # ------------------------------------------------------------------ API
    def parts(self):
        """Footprint uuids that any physics term touches."""
        idx = set(self.inc) | self.th_parts
        return {self.uids[i] for i in idx}

    def structures_of(self, uuid):
        i = self.u2i.get(uuid)
        if i is None:
            return []
        out = [self.structs[k].id for k in self.inc.get(i, [])]
        if i in self.th_parts:
            out += [f'thermal:{self.bv.parts[j].ref}' for j in self._th_targets_of(i)]
        return out

    def total(self, poses):
        self._sync_all(poses)
        tot = 0.0
        for k, s in enumerate(self.structs):
            tot += self._cost(s, self._value(k))
        if self.thermal is not None:
            tot += self._th_cost(self._th_current())
        return tot

    def total_by_kind(self, poses):
        """{kind: cost} at these poses."""
        self._sync_all(poses)
        out = {}
        for k, s in enumerate(self.structs):
            out[s.kind] = out.get(s.kind, 0.0) + self._cost(s, self._value(k))
        if self.thermal is not None:
            out['thermal'] = self._th_cost(self._th_current())
        return out

    def delta(self, poses, moved_uuids, new_poses):
        return self._delta(poses, moved_uuids, new_poses, None)

    def delta_by_kind(self, poses, moved_uuids, new_poses):
        """Like delta, split by structure kind: {kind: change of that kind's cost}."""
        out = {}
        self._delta(poses, moved_uuids, new_poses, out)
        return out

    def _delta(self, poses, moved_uuids, new_poses, per_kind):
        if isinstance(new_poses, dict):
            new_poses = [new_poses[u] for u in moved_uuids]
        mv = []
        u2i = self.u2i
        inc = self.inc
        for u, p in zip(moved_uuids, new_poses):
            i = u2i.get(u)
            if i is not None and (i in inc or i in self.th_parts):
                mv.append((i, p))
        if not mv:
            return 0.0
        if len(mv) == 1:
            touched = inc.get(mv[0][0], ())
        else:
            touched = set()
            for i, _ in mv:
                touched.update(inc.get(i, ()))
        st = self.st
        structs = self.structs
        uids = self.uids
        last = self._last
        # 1. bring the touched structures' members in step with `poses`; current values
        cur = []
        for k in touched:
            for j in structs[k].members:
                p = poses.get(uids[j])
                if p is not None and p is not last[j]:
                    self._sync(j, poses)
            cur.append(self._value(k))
        # 2. new values with the moved parts at their trial poses
        saved = [(i, st.get(i)) for i, _ in mv]
        for i, p in mv:
            st.set(i, *p)
        d = 0.0
        for idx, k in enumerate(touched):
            s = structs[k]
            cof = s.info['_cof']
            cache = self._ccache[k]
            if len(s.comps) == 1:
                new = _red(s.reduce, [s.comps[0].value(st)], s.info.get('weights'))
            else:
                vals = [c[0] for c in cache]
                for i, _ in mv:
                    for ci in cof.get(i, ()):
                        vals[ci] = None
                for ci, v in enumerate(vals):
                    if v is None:
                        vals[ci] = s.comps[ci].value(st)
                new = _red(s.reduce, vals, s.info.get('weights'))
            dk = self._cost(s, new) - self._cost(s, cur[idx])
            d += dk
            if per_kind is not None:
                per_kind[s.kind] = per_kind.get(s.kind, 0.0) + dk
        for i, p in saved:
            st.set(i, *p)
        if self.thermal is not None:
            for i, _ in mv:
                if i in self.th_parts:
                    dt = self._th_delta(poses, mv)
                    d += dt
                    if per_kind is not None:
                        per_kind['thermal'] = per_kind.get('thermal', 0.0) + dt
                    break
        return d

    def breakdown(self, poses):
        self._sync_all(poses)
        out = []
        for k, s in enumerate(self.structs):
            v = self._value(k)
            u = v / s.alloc.value if s.alloc.value > 0 else 0.0
            comps = [dict(label=lab, value=round(c[0], 6)) for lab, c in zip(s.labels, self._ccache[k])]
            out.append(dict(id=s.id, kind=s.kind, confidence=s.conf,
                            members=[self.bv.parts[i].ref for i in s.members],
                            uuids=[self.uids[i] for i in s.members],
                            value=v, unit=s.alloc.unit, alloc=s.alloc.to_json(), util=u,
                            cost=self._cost(s, v), components=comps, info=s.info))
        if self.thermal is not None:
            T = self._th_current()
            th = self.thermal
            for t, i in enumerate(th.targets):
                a = self._th_alloc[t]
                loc = max(float(T[t]) - th.T_mean, 0.0)
                out.append(dict(id=f'thermal:{self.bv.parts[i].ref}', kind='thermal', confidence=self._th_conf[t],
                                members=[self.bv.parts[i].ref], uuids=[self.uids[i]], value=loc, unit='K',
                                alloc=a.to_json(), util=loc / a.value,
                                cost=self._th_conf[t] * PR.phi(loc / a.value, self.knobs.barrier, self.knobs.u_sat),
                                components=[], info=dict(role='source' if t < len(th.src) else 'victim',
                                                         rise_K=float(T[t]), board_mean_K=th.T_mean,
                                                         P_W=float(th.P[t]) if t < len(th.src) else None)))
        return out

    # ------------------------------------------------------------------ internals
    def _cost(self, s, v):
        u = v / s.alloc.value if s.alloc.value > 0 else 0.0
        c = s.conf if self.knobs.use_confidence else 1.0
        return c * PR.phi(u, self.knobs.barrier, self.knobs.u_sat)

    def _sync(self, j, poses):
        p = poses.get(self.uids[j])
        if p is None or p is self._last[j]:
            return
        last = self._last[j]
        if last is not None and p == last:
            self._last[j] = p
            return
        self._last[j] = p
        self.st.set(j, *p)
        self._epoch[j] += 1

    def _sync_all(self, poses):
        for j in set(self.inc) | self.th_parts:
            self._sync(j, poses)

    def _value(self, k):
        s = self.structs[k]
        ep = self._epoch
        e = tuple([ep[i] for i in s.members])
        sc = self._scache[k]
        if sc is not None and sc[0] == e:
            return sc[1]
        cache = self._ccache[k]
        vals = []
        for ci, c in enumerate(s.comps):
            ce = tuple([ep[i] for i in c.parts])
            cc = cache[ci]
            if cc is None or cc[1] != ce:
                cc = (c.value(self.st), ce)
                cache[ci] = cc
            vals.append(cc[0])
        v = _red(s.reduce, vals, s.info.get('weights'))
        self._scache[k] = (e, v)
        return v

    # thermal ---------------------------------------------------------------
    def _th_targets_of(self, i):
        th = self.thermal
        if i in th.src:
            return th.targets
        return [i]

    def _th_current(self):
        th = self.thermal
        ep = tuple(self._epoch[i] for i in th.targets)
        if self._th_epochs is None:
            th.full(self.st)
        else:
            old = self._th_epochs
            changed = [t for t, (a, b) in enumerate(zip(old, ep)) if a != b]
            ns = len(th.src)
            for t in changed:
                if t < ns:
                    th.G[:, t] = th.column(self.st, t)
            for t in changed:
                th.G[t, :] = th.row(self.st, t)
        self._th_epochs = ep
        self._th_T = th.G @ th.P
        return self._th_T

    def _th_cost(self, T):
        b = self.knobs.barrier
        m = self.thermal.T_mean
        return float(sum(c * PR.phi(max(T[t] - m, 0.0) / a.value, b, self.knobs.u_sat)
                         for t, (a, c) in enumerate(zip(self._th_alloc, self._th_conf))))

    def _th_delta(self, poses, mv):
        th = self.thermal
        for j in th.parts:
            self._sync(j, poses)
        T0 = self._th_current()
        G = th.G
        saved = [(i, self.st.get(i)) for i, _ in mv]
        for i, p in mv:
            self.st.set(i, *p)
        Gn = G.copy()
        tindex = {i: t for t, i in enumerate(th.targets)}
        ns = len(th.src)
        for i, _ in mv:
            t = tindex.get(i)
            if t is None:
                continue
            if t < ns:
                Gn[:, t] = th.column(self.st, t)
            Gn[t, :] = th.row(self.st, t)
        for i, p in saved:
            self.st.set(i, *p)
        T1 = Gn @ th.P
        return self._th_cost(T1) - self._th_cost(T0)
