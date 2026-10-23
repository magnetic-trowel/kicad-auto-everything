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

Incrementality: every structure is a reduction of components that depend on a few parts;
a coupling component is two additive sub-terms (inductive over the two loops' parts,
capacitive over the two nodes' parts). Each sub-term's cached value is marked dirty when
one of its parts changes pose; `delta` re-reads the poses of the touched structures'
members from `poses` (identity, then equality), so callers may mutate their pose dict
freely between calls. A moved aggressor part re-evaluates the affected sub-term of all of
that aggressor's victims and cable connectors in one kernel call (structures.AggGroup).
"""
from __future__ import annotations

from dataclasses import dataclass, field


from . import priors as PR
from .boardview import BoardView
from .structures import (State)

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
        self.groups = []                  # structures.AggGroup: an aggressor's coupling targets
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
                for g in self.groups:
                    g.kern = self.kern
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
        # sub-terms: (k, ci, si) per part; one per component unless it has `subparts`
        self._psub = {}
        self._nsub = []
        where = {}
        for k, s in enumerate(self.structs):
            ns = []
            for ci, c in enumerate(s.comps):
                sp = getattr(c, 'subparts', None)
                if sp is None:
                    sp = (c.parts,)
                ns.append(len(sp))
                for si, ps in enumerate(sp):
                    for i in ps:
                        self._psub.setdefault(i, []).append((k, ci, si))
                where[id(c)] = (k, ci)
            self._nsub.append(ns)
        self._sub = [[[0.0] * m for m in ns] for ns in self._nsub]
        self._sd = [[[True] * m for m in ns] for ns in self._nsub]
        self._cv = [[0.0] * len(s.comps) for s in self.structs]
        self._sval = [0.0] * len(self.structs)
        self._scost = [0.0] * len(self.structs)
        self._sdirty = [True] * len(self.structs)
        # aggressor groups: their (k, ci) per target, aggressor and target parts per sub-term
        self._gkc = {}
        self._gagg = {}
        self._gtgt = {}
        for g in self.groups:
            self._gkc[id(g)] = [where[id(c)] for c in g.comps]
            g.stale = [True, True]
            g.tparts = [[set((c.tl if si == 0 else c.tn).parts) if c.subparts[si] else set() for c in g.comps]
                        for si in (0, 1)]
            for si in (0, 1):
                for i in g.agg_parts(si):
                    self._gagg.setdefault(i, []).append((g, si))
                for i in g.target_parts(si):
                    self._gtgt.setdefault(i, []).append((g, si))
        self._nbr = {i: tuple(sorted(set().union(*(self.structs[k].members for k in ks)))) for i, ks in self.inc.items()}
        self._last = [None] * n
        self._epoch = [0] * n
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
        for k in range(len(self.structs)):
            self._value(k)
            tot += self._scost[k]
        if self.thermal is not None:
            tot += self._th_cost(self._th_current())
        return tot

    def total_by_kind(self, poses):
        """{kind: cost} at these poses."""
        self._sync_all(poses)
        out = {}
        for k, s in enumerate(self.structs):
            self._value(k)
            out[s.kind] = out.get(s.kind, 0.0) + self._scost[k]
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
            moved = (mv[0][0],)
            touched = inc.get(moved[0], ())
            nbr = self._nbr.get(moved[0], ())
        else:
            moved = tuple(i for i, _ in mv)
            ts, nb = set(), set()
            for i in moved:
                ts.update(inc.get(i, ()))
                nb.update(self._nbr.get(i, ()))
            touched = sorted(ts)
            nbr = nb
        st = self.st
        structs = self.structs
        uids = self.uids
        last = self._last
        # 1. bring the touched structures' members in step with `poses`; current values
        for j in nbr:
            p = poses.get(uids[j])
            if p is not None and p is not last[j]:
                self._sync(j, poses)
        sdirty = self._sdirty
        for k in touched:
            if sdirty[k]:
                self._value(k)
        batches = []
        if self._gagg:
            seen = set()
            for i in moved:
                for g, si in self._gagg.get(i, ()):
                    if (id(g), si) not in seen:
                        seen.add((id(g), si))
                        g.ensure(si, st)
                        batches.append((g, si))
        # 2. trial values of the sub-terms the moved parts touch
        saved = [(i, st.get(i)) for i in moved]
        for i, p in mv:
            st.set(i, *p)
        new = {}
        for g, si in batches:
            out = g.batch(si, st)
            kc = self._gkc[id(g)]
            tp = g.tparts[si]
            for t, c in enumerate(g.comps):
                if c.subparts[si] and not any(i in tp[t] for i in moved):
                    k, ci = kc[t]
                    new[(k, ci, si)] = float(out[t])
        nsub = self._nsub
        for i in moved:
            for key in self._psub.get(i, ()):
                if key not in new:
                    k, ci, si = key
                    c = structs[k].comps[ci]
                    new[key] = c.value_sub(st, si) if nsub[k][ci] > 1 else c.value(st)
        for i, p in saved:
            st.set(i, *p)
        # 3. changed structures only
        sub = self._sub
        chg = {}
        for (k, ci, si), v in new.items():
            if v != sub[k][ci][si]:
                chg.setdefault(k, {}).setdefault(ci, {})[si] = v
        d = 0.0
        for k, cs in chg.items():
            s = structs[k]
            vals = list(self._cv[k])
            for ci, sv in cs.items():
                old = sub[k][ci]
                if len(old) == 1:
                    vals[ci] = sv[0]
                else:
                    vals[ci] = sv.get(0, old[0]) + sv.get(1, old[1])
            dk = self._cost(s, _red(s.reduce, vals, s.info.get('weights'))) - self._scost[k]
            d += dk
            if per_kind is not None:
                per_kind[s.kind] = per_kind.get(s.kind, 0.0) + dk
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
            comps = [dict(label=lab, value=round(c, 6)) for lab, c in zip(s.labels, self._cv[k])]
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
        sd = self._sd
        sdirty = self._sdirty
        for k, ci, si in self._psub.get(j, ()):
            sd[k][ci][si] = True
            sdirty[k] = True
        for g, si in self._gagg.get(j, ()):
            g.stale[si] = True
        for g, si in self._gtgt.get(j, ()):
            g.invalidate(si)

    def _sync_all(self, poses):
        for j in set(self.inc) | self.th_parts:
            self._sync(j, poses)

    def _refresh_group(self, g, si):
        """Sub-term si of all of g's targets at the synced poses, in one kernel call."""
        g.ensure(si, self.st)
        out = g.batch(si, self.st)
        sub = self._sub
        sd = self._sd
        for (k, ci), c, v in zip(self._gkc[id(g)], g.comps, out):
            if c.subparts[si] and sd[k][ci][si]:
                sub[k][ci][si] = float(v)
                sd[k][ci][si] = False
                self._sdirty[k] = True
                self._cv[k][ci] = sub[k][ci][0] + sub[k][ci][1]
        g.stale[si] = False

    def _value(self, k):
        if not self._sdirty[k]:
            return self._sval[k]
        s = self.structs[k]
        st = self.st
        subk = self._sub[k]
        sdk = self._sd[k]
        cv = self._cv[k]
        for ci, c in enumerate(s.comps):
            d = sdk[ci]
            if len(d) == 1:
                if d[0]:
                    v = c.value(st)
                    subk[ci][0] = v
                    cv[ci] = v
                    d[0] = False
                continue
            if d[0] or d[1]:
                for si in (0, 1):
                    if d[si]:
                        g = c.group
                        if g is not None and g.stale[si]:
                            self._refresh_group(g, si)
                        if d[si]:
                            subk[ci][si] = c.value_sub(st, si)
                            d[si] = False
                cv[ci] = subk[ci][0] + subk[ci][1]
        v = _red(s.reduce, cv, s.info.get('weights'))
        self._sval[k] = v
        self._scost[k] = self._cost(s, v)
        self._sdirty[k] = False
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
