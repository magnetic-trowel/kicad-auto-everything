# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Build the place terms' structures from a physics brief (Contract 2).

Brief shape consumed (unknown keys are ignored; members reference parts by footprint
uuid, or by reference designator as a fallback):

  nets: {name: {role: ground|rail|switch_node|clock|analog|rf|..., volts}}
  parts: {uuid: {ref, role, external: cable|antenna|null, P_W}}
  structures: [{id, kind, confidence, evidence, budget: {quantity: {value, unit, class, basis}}, ...}]
    commutation_cell: loop [[uuid, pad|[pads]], ...] closed, in current order;
                      class buck|boost|bridge_driver|half_bridge; rail, sw, gnd; excite {V, I, t_sw_ns}
    decap:            ic (an IC, module, LED, connector, diode, fuse or inductor), power_pins [nums],
                      ground_pins [nums] (may be empty: the loop closes through the plane), rail,
                      ground (split_supply: the V- rail), caps, hf_caps, caps_p, pin_caps, function
                      (load, bypass, regulator_input/output, converter_input/output, entry,
                      split_supply), pairing (pin | nearest_pin: the IC's pin clusters, each with
                      its paired and all unpaired caps in parallel; nearest_load: each cap to the
                      nearest load pin on the rail), shared_by
    crystal:          ic, xin, xout, crystal, load_caps [uuids], f_Hz
    victim:           class feedback|sense|analog|crystal|reference; loop [[uuid, pad], ...] and/or nets
    heat_source:      ref (uuid), P_W;   thermal_victim: ref (uuid), class
    connector_chain:  connector, chain [[uuid, pad], ...] connector first, protection [uuids], external
    antenna:          ref, feed [[uuid, pad], ...], f_Hz

Missing budgets and excitations come from kae.physics.priors (E5).
"""
from __future__ import annotations

import math
import re

import numpy as np

from . import priors as PR
from .kernels import fin_params
from .structures import (
    CmComp,
    CouplingComp,
    CouplingEngine,
    CrystalComp,
    DecapLoop,
    EsdComp,
    FeedComp,
    LoopComp,
    LoopShape,
    NearestLoopComp,
    NodeShape,
    Term,
    ThermalField,
    _Coupled,
)

GND_RE = re.compile(r'(^|[^A-Z])(A|D|P|S|C)?GND|^/?VSS|^0V$|GROUND|EARTH', re.I)


def _volts(name):
    s = (name or '').split('/')[-1].upper().replace('_', '')
    m = re.search(r'(\d+)V(\d+)', s)
    if m:
        return float(f'{m.group(1)}.{m.group(2)}')
    m = re.search(r'(\d+(?:\.\d+)?)V', s)
    if m:
        return float(m.group(1))
    if re.search(r'VBUS|USB', s):
        return 5.0
    return None


class _Ctx:
    def __init__(self, terms):
        self.t = terms
        self.bv = terms.bv
        b = terms.brief or {}
        self.nets = b.get('nets', {}) or {}
        self.parts = b.get('parts', {}) or {}
        self.ref2i = {}
        for p in self.bv.parts:
            self.ref2i.setdefault(p.ref, p.i)
        gn = {n for n, r in self.nets.items() if (r or {}).get('role') == 'ground'}
        if not gn:
            gn = {n for n in self.bv.nets if GND_RE.search(n.split('/')[-1] or n)}
        self.gnd = gn
        gm = self.bv.gmask(gn) if gn else None
        self.has_plane = bool(gm is not None and gm.any())

    def part(self, key):
        if key is None:
            return None
        i = self.t.u2i.get(key)
        if i is None:
            i = self.ref2i.get(key)
        return i

    def pads(self, i, pads):
        p = self.bv.parts[i]
        if pads is None:
            return []
        if not isinstance(pads, (list, tuple)):
            pads = [pads]
        want = {str(x) for x in pads}
        return [k for k, num in enumerate(p.pad_num) if num in want]

    def term(self, i, ks, net=None):
        p = self.bv.parts[i]
        if not ks:
            return None
        lx = float(np.mean(p.pad_lx[ks]))
        ly = float(np.mean(p.pad_ly[ks]))
        x0 = float(np.min(p.pad_lx[ks] - p.pad_sx[ks] / 2))
        x1 = float(np.max(p.pad_lx[ks] + p.pad_sx[ks] / 2))
        y0 = float(np.min(p.pad_ly[ks] - p.pad_sy[ks] / 2))
        y1 = float(np.max(p.pad_ly[ks] + p.pad_sy[ks] / 2))
        a = max(x1 - x0, y1 - y0) if len(ks) > 1 else min(p.pad_sx[ks[0]], p.pad_sy[ks[0]])
        return Term(i, lx, ly, a, net if net is not None else p.pad_net[ks[0]], ks)

    def member_term(self, m):
        if not m:
            return None
        i = self.part(m[0])
        if i is None:
            return None
        ks = self.pads(i, m[1] if len(m) > 1 else None)
        return self.term(i, ks)

    def conf(self, s, default=0.7):
        c = s.get('confidence', default)
        try:
            return float(c)
        except (TypeError, ValueError):
            return default

    def budget(self, s, quantity):
        b = (s.get('budget') or {}).get(quantity)
        if isinstance(b, dict) and b.get('value') is not None:
            return PR.Belief(float(b['value']), b.get('unit', ''), b.get('basis', 'brief'), b.get('class', 'brief'))
        return None

    def ic_power_pins(self, i):
        """Number of a part's pads on supply rails (brief role 'rail'), every rail."""
        P = self.bv.parts[i]
        rails = self.__dict__.get('_rails')
        if rails is None:
            rails = self._rails = {n for n, r in self.nets.items() if (r or {}).get('role') == 'rail'}
        return sum(1 for n in P.pad_net if n in rails)

    def is_module(self, i):
        p = self.parts.get(self.bv.parts[i].uuid) or {}
        return (p.get('kind') or p.get('role')) == 'module'

    def decap_alloc(self, s, ic, vr, pp):
        """(budget per pin cluster as a function of its pin count, per-pin flag) of a decap spec."""
        b = self.budget(s, 'L_nH')
        per_pin = s.get('function') not in PR.STABILITY_FUNCTIONS and not self.is_module(ic)
        if b is None:
            b = PR.decap_budget(vr, len(self.bv.parts[ic].pad_num), len(pp), function=s.get('function'),
                                n_ic_power_pins=self.ic_power_pins(ic), module=self.is_module(ic))
        return b, per_pin

    def net_volts(self, net):
        r = self.nets.get(net) or {}
        v = r.get('volts')
        return float(v) if v else _volts(net)


def _is_ic(p):
    return len(p.pad_num) > 4


def _hop_width(ctx, a0, a1, power):
    tmin = max(ctx.bv.track_min, 0.15)
    w = min(a0, a1)
    return float(min(max(w, tmin), 3.0 if power else 1.0))


def _loop_comp(ctx, terms, power, kind, gnd_hop=None):
    bv = ctx.bv
    n = len(terms)
    kinds, widths, zb = [], [], []
    body_min = [0.0] * n
    g = None
    for k in range(n):
        a, b = terms[k], terms[(k + 1) % n]
        if a.i == b.i:
            kinds.append('body')
            p = bv.parts[a.i]
            widths.append(0.3 if _is_ic(p) else float(min(max(min(a.a, b.a), 0.2), 3.0)))
            zb.append(p.zbody)
            if a.ks and b.ks:
                body_min[k] = float(min(math.hypot(p.pad_lx[u] - p.pad_lx[v], p.pad_ly[u] - p.pad_ly[v])
                                        for u in a.ks for v in b.ks))
        else:
            kinds.append('board')
            widths.append(_hop_width(ctx, a.a, b.a, power))
            zb.append(0.0)
            if g is None and a.net in ctx.gnd and b.net in ctx.gnd:
                g = k
    return LoopComp(bv, terms, kinds, widths, zb, gnd_hop=g if gnd_hop is None else gnd_hop,
                    gnd_nets=ctx.gnd, knobs=ctx.t.knobs, kern=ctx.t.kern, body_min=body_min,
                    detour=ctx.t.knobs.detour(kind))


def _cluster(points, dmax=3.0):
    """Single-linkage clusters of 2-D points (indices)."""
    n = len(points)
    lab = list(range(n))

    def f(a):
        while lab[a] != a:
            lab[a] = lab[lab[a]]
            a = lab[a]
        return a
    for a in range(n):
        for b in range(a + 1, n):
            if math.dist(points[a], points[b]) <= dmax:
                ra, rb = f(a), f(b)
                if ra != rb:
                    lab[rb] = ra
    out = {}
    for a in range(n):
        out.setdefault(f(a), []).append(a)
    return list(out.values())


def _pour_pairs(ctx, rail):
    """Layer pairs (Lr, Lg, d) on which the rail and a ground net both have zones, in the
    order a decap loop tries them: inner layers before outer ones (an outer pour under the
    parts is perforated by their pads), then the thinner dielectric d."""
    bv = ctx.bv
    rl = set(bv.net_plane_layers(rail)) if rail else set()
    if not rl:
        return []
    gl = set()
    for g in ctx.gnd:
        gl |= set(bv.net_plane_layers(g))
    outer = {bv.copper[0], bv.copper[-1]}
    out = []
    for a in rl:
        for b in gl:
            if a != b:
                out.append(((a in outer) + (b in outer), abs(bv.zcu[a] - bv.zcu[b]), a, b))
    out.sort()
    return [(a, b, d) for _, d, a, b in out]


def build_structures(terms):
    ctx = _Ctx(terms)
    S = terms.structs
    specs = (terms.brief or {}).get('structures', []) or []
    cells = []
    low = []
    from .place_terms import Struct
    for s in specs:
        kind = s.get('kind')
        try:
            if kind == 'commutation_cell':
                st = _commutation(ctx, s, Struct)
                if st:
                    S.append(st)
                    cells.append((st, s))
            elif kind == 'power_path':
                st = _power_path(ctx, s, Struct)
                if st:
                    S.append(st)
            elif kind == 'decap':
                if _low_ownership(s):
                    low.append(s)
                else:
                    S.extend(_decap(ctx, s, Struct, low))
            elif kind == 'crystal':
                st = _crystal(ctx, s, Struct)
                if st:
                    S.append(st)
            elif kind == 'connector_chain':
                st = _esd(ctx, s, Struct)
                if st:
                    S.append(st)
            elif kind == 'antenna':
                st = _antenna(ctx, s, Struct)
                if st:
                    S.append(st)
        except Exception as e:      # noqa: BLE001 - a bad structure must not kill the others
            terms.warnings.append(f"{s.get('id', kind)}: {type(e).__name__}: {e}")
    try:
        groups = [s for s in specs if s.get('kind') == 'rail_group']
        S.extend(_decap_nearest(ctx, low, Struct, [s for s in specs if s.get('kind') == 'decap'], groups))
    except Exception as e:      # noqa: BLE001
        terms.warnings.append(f'nearest-load decaps: {type(e).__name__}: {e}')
    # aggressors: hot loops (inductive) with their switch-node copper (capacitive), and clocks
    aggs = []
    for st, s in cells:
        lc = st.comps[0]
        loop = LoopShape(lc.T, closed=True)
        node = _node_of(ctx, st.info.get('sw_nets') or [], w=1.0)
        aggs.append((st, loop, node, st.info['excite']))
    for s in specs:
        if s.get('kind') == 'oscillator' and s.get('out_net'):
            node = _node_of(ctx, [s['out_net']], w=0.2)
            if node is not None:
                ex = dict(didt=0.0, dvdt=3.3 / 2.0, I=0.0, V=3.3, t_sw=2.0)     # E5: 3.3 V CMOS, 2 ns edges
                st = Struct(id=s.get('id') or 'osc', kind='aggressor', conf=ctx.conf(s), alloc=PR.Belief(1, '', ''),
                            comps=[], info=dict(excite=ex))
                st.comps_parts = node.parts
                aggs.append((st, None, node, ex))
    for s in specs:
        if s.get('kind') == 'victim':
            try:
                st = _victim(ctx, s, aggs, Struct)
                if st:
                    S.append(st)
            except Exception as e:  # noqa: BLE001
                terms.warnings.append(f"{s.get('id')}: {type(e).__name__}: {e}")
    S.extend(_world_cm(ctx, specs, aggs, Struct))
    # every coupling sub-term in one engine, for batched evaluation (Terms.delta)
    coupled = [c for s in S for c in s.comps if isinstance(c, _Coupled)]
    terms.engine = CouplingEngine(ctx.bv, coupled) if coupled else None
    _thermal(ctx, specs)


# ----------------------------------------------------------------------------- (a)
def _commutation(ctx, s, Struct):
    """Hot loop through each candidate input cap: the caps whose calibrated ownership is at
    least half the best one's, in parallel (the loop through the nearest dominates); the
    structure's weight is the brief's confidence times that best ownership."""
    bv = ctx.bv
    loop = s.get('loop') or []
    T = [ctx.member_term(m) for m in loop]
    if len(T) < 3 or any(t is None for t in T):
        return None
    cap_i = T[0].i if T[0].i == T[-1].i else None
    caps = [ctx.part(c) for c in (s.get('caps') or s.get('input_caps') or [])]
    caps = [c for c in caps if c is not None]
    pmap = {ctx.part(k): PR.ownership_calibrated(v) for k, v in (s.get('caps_p') or {}).items()
            if ctx.part(k) is not None and v is not None}
    if cap_i is None or not caps:
        variants = [(T, 1.0, bv.parts[T[0].i].ref)]
    else:
        rail_net, gnd_net = T[0].net, T[-1].net
        variants = []
        for c in dict.fromkeys([cap_i] + caps):
            cp = bv.parts[c]
            kr = [k for k, n in enumerate(cp.pad_net) if n == rail_net]
            kg = [k for k, n in enumerate(cp.pad_net) if n == gnd_net]
            if not kr or not kg:
                continue
            Tc = [ctx.term(c, kr[:1])] + T[1:-1] + [ctx.term(c, kg[:1])]
            variants.append((Tc, pmap.get(c, 1.0 if c == cap_i else PR.ownership_calibrated(0.5)), cp.ref))
    pmax = max(w for _, w, _ in variants)
    variants = [v for v in variants if v[1] >= 0.5 * pmax]          # the caps this cell most likely owns
    comps = [_loop_comp(ctx, Tc, True, 'commutation') for Tc, _, _ in variants]
    labels = [lab for _, _, lab in variants]
    cls = s.get('class') or 'unknown'
    ex = s.get('excite') or {}
    vin = ex.get('V') or ctx.net_volts(s.get('rail')) or PR.V_IN_UNKNOWN.value
    alloc = ctx.budget(s, 'L_nH') or PR.hot_loop_budget(cls, vin, t_sw_ns=ex.get('t_sw_ns'))
    excite = PR.hot_loop_excite(cls, vin, ex.get('I'), ex.get('t_sw_ns'))
    return Struct(id=s.get('id') or f'cell:{bv.parts[T[1].i].ref}', kind='commutation', conf=ctx.conf(s) * pmax,
                  alloc=alloc, comps=comps, reduce='parallel', labels=labels,
                  info=dict(cls=cls, V_in=vin, excite=excite, ownership=pmax, sw=s.get('sw'),
                            sw_nets=s.get('sw_nets') or ([s.get('sw')] if s.get('sw') else [])))


def _power_path(ctx, s, Struct):
    """Loop of a power path (load switch, eFuse, ideal diode, reverse-polarity or discrete
    FET switch): C_in+ -> pass elements -> C_out+ -> C_out- -> C_in-, priced like a cell
    against PR.power_path_budget. The parallel elements of a stage carry the current side
    by side: each one's variant of the loop counts in parallel."""
    bv = ctx.bv
    T = [ctx.member_term(m) for m in s.get('loop') or []]
    if len(T) < 3 or any(t is None for t in T):
        return None
    variants = [(T, bv.parts[T[1].i].ref)]
    for stage in s.get('stages') or []:
        el = [i for i in (ctx.part(u) for u in stage) if i is not None]
        at = [k for k, t in enumerate(T) if t.i in el]
        if len(el) < 2 or not at or len({T[k].i for k in at}) != 1:
            continue
        i0 = T[at[0]].i
        for j in el:
            if j == i0 or len(variants) >= 4:
                continue
            Tj = list(T)
            for k in at:
                ks = ctx.pads(j, [bv.parts[i0].pad_num[q] for q in T[k].ks])
                Tj[k] = ctx.term(j, ks) if ks else None
            if all(t is not None for t in Tj):
                variants.append((Tj, bv.parts[j].ref))
        break
    comps = [_loop_comp(ctx, Tv, True, 'power_path') for Tv, _ in variants]
    ex = s.get('excite') or {}
    v = ex.get('V') or ctx.net_volts(s.get('rail_in')) or ctx.net_volts(s.get('rail_out')) or 5.0
    i = ex.get('I') or 1.0
    alloc = ctx.budget(s, 'L_nH') or PR.power_path_budget(v, i)
    return Struct(id=s.get('id') or f'path:{bv.parts[T[1].i].ref}', kind='power_path', conf=ctx.conf(s), alloc=alloc,
                  comps=comps, reduce='parallel', labels=[lab for _, lab in variants],
                  info=dict(cls=s.get('class'), V=v, I=i, rail_in=s.get('rail_in'), rail_out=s.get('rail_out')))


# ----------------------------------------------------------------------------- (b)
def _decap_side(ctx, s):
    """(ic index, rail, power pads, ground pads, ground net) of a decap spec. The 'ic' is the
    load or source the caps serve: an IC, a module, an LED, or (functions entry,
    converter_input/output) a connector, diode, fuse or inductor; split_supply names the
    return rail (V-) as its ground."""
    ic = ctx.part(s.get('ic'))
    if ic is None:
        return None
    P = ctx.bv.parts[ic]
    rail = s.get('rail')
    gnd = s.get('ground')
    pp = ctx.pads(ic, s.get('power_pins')) if s.get('power_pins') else [k for k, n in enumerate(P.pad_net) if n == rail]
    if not rail and pp:
        rail = P.pad_net[pp[0]]
    if s.get('ground_pins'):
        gp = ctx.pads(ic, s.get('ground_pins'))
    else:
        gp = [k for k, n in enumerate(P.pad_net) if n in ctx.gnd or (gnd and n == gnd)]
    if not gnd:
        gnd = next((P.pad_net[k] for k in gp), None) or next(iter(sorted(ctx.gnd)), 'GND')
    return ic, rail, pp, gp, gnd


def _decap_caps(ctx, s, rail, gnd):
    """(cap index, rail pad, ground pad) of the spec's HF caps (all caps when none is HF)."""
    out = []
    for c in (s.get('hf_caps') or s.get('caps') or []):
        i = ctx.part(c)
        if i is None:
            continue
        cp = ctx.bv.parts[i]
        kr = [k for k, n in enumerate(cp.pad_net) if n == rail]
        kg = [k for k, n in enumerate(cp.pad_net) if n == gnd or n in ctx.gnd]
        if kr and kg:
            out.append((i, kr[:1], kg[:1]))
    return out


def _ic_terms(ctx, ic, ks, rail, gp, gnd):
    """Power terminal (centroid of the pin cluster ks) and its return terminal: the ground
    pad nearest to it, or, for a part without a return pin (inductor, diode, fuse), the same
    point on the ground net: the return then closes through the plane (or laterally) under
    the power pin."""
    P = ctx.bv.parts[ic]
    tp = ctx.term(ic, ks, rail)
    if gp:
        def gdist(k):
            return math.hypot(P.pad_lx[k] - tp.lx, P.pad_ly[k] - tp.ly) - 0.5 * min(P.pad_sx[k], P.pad_sy[k])
        tg = ctx.term(ic, [min(gp, key=gdist)])
    else:
        tg = Term(ic, tp.lx, tp.ly, tp.a, gnd, ks)
    return tp, tg


def _low_ownership(s):
    """A decap whose capacitors serve whichever load on the rail they sit next to: the
    brief's pairing 'nearest_load' (rail groups, entry bulk); briefs without a pairing:
    raw ownership <= OWNERSHIP_NEAREST on a rail shared by >= 3 loads."""
    if s.get('pairing'):
        return s['pairing'] == 'nearest_load'
    ps = [float(v) for v in (s.get('caps_p') or {}).values() if v is not None]
    return bool(ps) and max(ps) <= PR.OWNERSHIP_NEAREST and (s.get('shared_by') or 1) >= 3


def _unowned(s):
    """Caps of a kae.brief/1 decap spec (one with a pairing) that it does not own (caps_p <
    0.5): they serve whichever load they sit next to."""
    if not s.get('pairing'):
        return set()
    return {u for u, p in (s.get('caps_p') or {}).items() if p is not None and float(p) < 0.5}


def _decap(ctx, s, Struct, pool):
    """A decap spec's structures. pairing 'pin' (and briefs without a pairing): one
    structure per power-pin cluster, its paired capacitors and the spec's other owned ones
    in parallel; 'nearest_pin': one structure per owned capacitor, charged its loop to the
    nearest of the IC's pin clusters at the current poses. Unowned capacitors (caps_p <
    0.5) go to `pool`, the nearest-load decaps."""
    side = _decap_side(ctx, s)
    if side is None:
        return []
    ic, rail, pp, gp, gnd = side
    bv = ctx.bv
    P = bv.parts[ic]
    unowned = {ctx.part(u) for u in _unowned(s)}
    if unowned:
        pool.append(dict(s, caps=[u for u in (s.get('caps') or []) if ctx.part(u) in unowned],
                         hf_caps=[u for u in (s.get('hf_caps') or []) if ctx.part(u) in unowned]))
    caps = [c for c in _decap_caps(ctx, s, rail, gnd) if c[0] not in unowned]
    pmap = {ctx.part(k): PR.ownership_calibrated(v) for k, v in (s.get('caps_p') or {}).items()
            if ctx.part(k) is not None and v is not None}
    pin_caps = {str(k): {ctx.part(u) for u in v} for k, v in (s.get('pin_caps') or {}).items()}
    if not pp or not caps:
        return []
    groups = _cluster([(P.pad_lx[k], P.pad_ly[k]) for k in pp], 1.6)
    vr = ctx.net_volts(rail) or 3.3
    alloc_pin, per_pin = ctx.decap_alloc(s, ic, vr, pp)
    pairs = _pour_pairs(ctx, rail)
    sid = s.get('id') or f'decap:{P.ref}:{rail}'

    def cluster_alloc(ks):
        if not per_pin:
            return alloc_pin
        return PR.Belief(alloc_pin.value / max(1, len(ks)), 'nH',
                         alloc_pin.basis + f'; {len(ks)} pin(s) in this cluster', alloc_pin.cls)
    out = []
    if s.get('pairing') == 'nearest_pin':
        clusters = []
        for grp in groups:
            ks = [pp[j] for j in grp]
            clusters.append((ks, *_ic_terms(ctx, ic, ks, rail, gp, gnd)))
        a = cluster_alloc(min((c[0] for c in clusters), key=len))
        for i, kr, kgc in caps:
            tr = ctx.term(i, kr)
            tc = ctx.term(i, kgc)
            loops = [_decap_loop(ctx, tp, tr, tc, tg, rail, pairs) for _, tp, tg in clusters]
            w = pmap.get(i, 1.0)
            out.append(Struct(id=f'{sid}#{bv.parts[i].ref}', kind='decap', conf=ctx.conf(s) * w, alloc=a,
                              comps=[NearestLoopComp(loops)], reduce='single', labels=[bv.parts[i].ref],
                              info=dict(rail=rail, pins=[P.pad_num[k] for k in pp], pairing='nearest_pin',
                                        pour_pairs=[f'{x}/{y}' for x, y, _ in pairs], ownership=w,
                                        function=s.get('function'), _careful=per_pin)))
        return out
    for gi, grp in enumerate(groups):
        ks = [pp[j] for j in grp]
        tp, tg = _ic_terms(ctx, ic, ks, rail, gp, gnd)
        comps, labels, weights = [], [], []
        paired = set()
        for k in ks:
            paired |= pin_caps.get(P.pad_num[k], set())
        all_paired = set().union(*pin_caps.values()) if pin_caps else set()
        # the cluster's own paired capacitors and every unpaired owned one of the spec, in
        # parallel (current takes the lowest-inductance path, so the nearest dominates);
        # briefs without caps_p calibration drop the unlikely ones by ownership
        use = [c for c in caps if c[0] in paired or c[0] not in all_paired] or caps
        if use:
            pm = max(pmap.get(c[0], 1.0) for c in use)
            use = [c for c in use if pmap.get(c[0], 1.0) >= 0.5 * pm]
        for i, kr, kgc in use:
            tr = ctx.term(i, kr)
            tc = ctx.term(i, kgc)
            comps.append(_decap_loop(ctx, tp, tr, tc, tg, rail, pairs))
            labels.append(bv.parts[i].ref)
            weights.append(pmap.get(i, 1.0))
        if not comps:
            continue
        out.append(Struct(id=sid + (f'#{gi}' if len(groups) > 1 else ''),
                          kind='decap', conf=ctx.conf(s) * max(weights), alloc=cluster_alloc(ks), comps=comps,
                          reduce='parallel', labels=labels,
                          info=dict(rail=rail, pins=[P.pad_num[k] for k in ks], pairing=s.get('pairing') or 'pin',
                                    pour_pairs=[f'{x}/{y}' for x, y, _ in pairs],
                                    ownership=max(weights), function=s.get('function'), _careful=per_pin)))
    return out


def _decap_nearest(ctx, pool, Struct, decaps=(), groups=()):
    """Capacitors that serve whichever load they sit next to (pairing 'nearest_load', caps a
    spec does not own, legacy low-ownership specs): one structure per capacitor, charged its
    loop to the nearest load power-pin cluster on its rail at the current poses
    (NearestLoopComp), with the median per-pin budget of those clusters. A capacitor of a
    rail group chooses among the group's loads only."""
    bv = ctx.bv
    # load pin clusters per rail, from every decap spec on it whose 'ic' is a load (not an
    # entry connector or a converter's inductor)
    cands = {}
    src = ('entry', 'converter_output', 'converter_input')
    for s in list(decaps) + list(pool):
        if s.get('function') in src:
            continue
        side = _decap_side(ctx, s)
        if side is None:
            continue
        ic, rail, pp, gp, gnd = side
        if not pp:
            continue
        P = bv.parts[ic]
        vr = ctx.net_volts(rail) or 3.3
        b, per_pin = ctx.decap_alloc(s, ic, vr, pp)
        seen = cands.setdefault(rail, {})
        for grp in _cluster([(P.pad_lx[k], P.pad_ly[k]) for k in pp], 1.6):
            ks = tuple(sorted(pp[j] for j in grp))
            seen.setdefault((ic, ks), (gp, gnd, b.value / max(1, len(ks)) if per_pin else b.value))
    in_group = {}
    for g in groups:
        loads = {ctx.part(u) for u in g.get('loads') or []} - {None}
        for c in g.get('caps') or []:
            i = ctx.part(c)
            if i is not None and loads:
                in_group[(g.get('rail'), i)] = (g.get('id'), loads)
    caps = {}
    for s in pool:
        side = _decap_side(ctx, s)
        if side is None:
            continue
        rail, gnd = side[1], side[4]
        for i, kr, kg in _decap_caps(ctx, s, rail, gnd):
            caps.setdefault((rail, i), (kr, kg, ctx.conf(s)))
    out = []
    for (rail, i), (kr, kg, conf) in caps.items():
        grp = in_group.get((rail, i))
        cl = [(ic, ks, v) for (ic, ks), v in (cands.get(rail) or {}).items()
              if ic != i and (grp is None or ic in grp[1])]
        if not cl:
            continue
        tr = ctx.term(i, kr)
        tc = ctx.term(i, kg)
        pairs = _pour_pairs(ctx, rail)
        loops = []
        for ic, ks, (gp, gnd, _) in cl:
            tp, tg = _ic_terms(ctx, ic, list(ks), rail, gp, gnd)
            loops.append(_decap_loop(ctx, tp, tr, tc, tg, rail, pairs))
        budget = float(np.median([v[2] for _, _, v in cl]))
        alloc = PR.Belief(budget, 'nH', f'median per-pin budget of the {len(cl)} load pin cluster(s) on {rail}'
                          + (f' in {grp[0]}' if grp else '') + ' (nearest-load decap)')
        out.append(Struct(id=f'decap:{rail}:{bv.parts[i].ref}:nearest', kind='decap', conf=conf, alloc=alloc,
                          comps=[NearestLoopComp(loops)], reduce='single', labels=[bv.parts[i].ref],
                          info=dict(rail=rail, nearest=True, candidates=len(loops), function='load',
                                    pairing='nearest_load', rail_group=grp[0] if grp else None, _careful=True)))
    return out


def _mount(ctx, pitch, w, z, cache):
    """Mounting inductance (nH) of a two-terminal part on the board: its body (width w,
    height z above the surface) and two vias at its terminals (pitch apart) down to a plane
    at depth h, as a function of h (cached)."""
    from . import fastloop as FL

    def f(h):
        key = round(h, 3)
        v = cache.get(key)
        if v is None:
            H = [(0.0, 0.0, pitch, 0.0, w, h + z)]
            V = [(0.0, 0.0, 0.0, h + z, 0.15), (pitch, 0.0, h + z, 0.0, 0.15)]
            v = FL.loop_fast(H, V)
            cache[key] = v
        return v
    return f


def _decap_loop(ctx, tp, tr, tc, tg, rail, pairs):
    """A decap loop [IC power pin, cap rail pad, cap ground pad, IC return]: through the
    rail and ground pours when both join its ends, else straight hops (DecapLoop)."""
    bv = ctx.bv
    loop = _loop_comp(ctx, [tp, tr, tc, tg], False, 'decap')
    if not pairs or not ctx.t.knobs.pour_decaps:
        return loop
    for a, b, _ in pairs:              # label the pours now, not on the first move
        bv.zone_labels(a)
        bv.zone_labels(b)
    cp = bv.parts[tr.i]
    ip = bv.parts[tp.i]
    mc = _mount(ctx, max(math.hypot(tr.lx - tc.lx, tr.ly - tc.ly), 0.3), max(min(tr.a, tc.a), 0.2), cp.zbody, {})
    pitch_ic = math.hypot(tp.lx - tg.lx, tp.ly - tg.ly) if tp.i == tg.i else 0.0
    mi = _mount(ctx, max(pitch_ic, 0.3), 0.3 if _is_ic(ip) else max(tp.a, 0.2), ip.zbody, {})
    return DecapLoop(bv, loop, pairs, rail, ctx.gnd, mc, mi)


# ----------------------------------------------------------------------------- (d)
def _crystal(ctx, s, Struct):
    bv = ctx.bv
    ic = ctx.part(s.get('ic'))
    y = ctx.part(s.get('crystal'))
    if ic is None or y is None:
        return None
    ki = ctx.pads(ic, s.get('xin'))
    ko = ctx.pads(ic, s.get('xout'))
    if not ki or not ko:
        return None
    ni, no = bv.parts[ic].pad_net[ki[0]], bv.parts[ic].pad_net[ko[0]]

    def side_terms(net, kic):
        ts = [ctx.term(ic, kic)]
        for i in [y] + [ctx.part(c) for c in s.get('load_caps') or []]:
            if i is None:
                continue
            ks = [k for k, n in enumerate(bv.parts[i].pad_net) if n == net]
            if ks:
                ts.append(ctx.term(i, ks[:1]))
        return ts
    ti, to = side_terms(ni, ki), side_terms(no, ko)
    alloc, sens = PR.crystal_budget(s.get('f_Hz'))
    alloc = ctx.budget(s, 'ppm') or alloc
    comp = CrystalComp(bv, ti, to, sens, detour=ctx.t.knobs.detour('crystal'))
    return Struct(id=s.get('id') or f'xtal:{bv.parts[y].ref}', kind='crystal', conf=ctx.conf(s), alloc=alloc,
                  comps=[comp], labels=['pulling'], info=dict(nets=[ni, no], S_ppm_per_pF=sens))


# ----------------------------------------------------------------------------- (c)
def _node_of(ctx, nets, w=0.2, max_pads=24):
    bv = ctx.bv
    ts, areas = [], []
    for net in nets:
        for i, k in bv.nets.get(net, [])[:max_pads]:
            p = bv.parts[i]
            ts.append(Term(i, p.pad_lx[k], p.pad_ly[k], 0.3, net))
            areas.append(float(p.pad_sx[k] * p.pad_sy[k]))
    return NodeShape(ts, areas, w=w) if ts else None


def _victim(ctx, s, aggs, Struct):
    if not aggs:
        return None
    bv = ctx.bv
    T = [ctx.member_term(m) for m in s.get('loop') or []]
    T = [t for t in T if t is not None]
    nets = s.get('nets') or sorted({t.net for t in T if t.net and t.net not in ctx.gnd})
    loop = None
    if len(T) >= 2:
        n = len(T)
        if ctx.has_plane:
            # a return hop between two ground terminals runs in the plane: open the loop
            # there (the path then closes through the plane by vias at both ends)
            for k in range(n):
                if T[k].net in ctx.gnd and T[(k + 1) % n].net in ctx.gnd:
                    T = T[k + 1:] + T[:k + 1]
                    break
        open_ = ctx.has_plane and T[0].net in ctx.gnd and T[-1].net in ctx.gnd
        loop = LoopShape(T, closed=not open_)
    elif nets and len(bv.nets.get(nets[0], [])) >= 2:
        # a signal net returning through the reference plane: its pads in netlist order
        pads = bv.nets[nets[0]][:8]
        T = [Term(i, bv.parts[i].pad_lx[k], bv.parts[i].pad_ly[k], 0.3, nets[0]) for i, k in pads]
        loop = LoopShape(T, closed=False)
    node = _node_of(ctx, nets, w=0.2)
    if loop is None and node is None:
        return None
    cls = s.get('class') or 'analog'
    alloc, zv = PR.victim_budget(cls)
    alloc = ctx.budget(s, 'V_mV') or alloc
    comps, labels = [], []
    gp = bool(ctx.gnd)
    vparts = set((loop.parts if loop else ()) + (node.parts if node else ()))
    for st, aloop, anode, ex in aggs:
        own = set(st.comps[0].parts) if st.comps else set(getattr(st, 'comps_parts', ()))
        if own & vparts and st.kind == 'commutation' and s.get('class') != 'feedback':
            continue        # the victim is part of the aggressor's own cell
        comps.append(CouplingComp(bv, aloop, anode, loop, node, ex['didt'], ex['V'], ex['t_sw'], zv, gp))
        comps[-1].kern = ctx.t.kern
        labels.append(st.id)
    if not comps:
        return None
    return Struct(id=s.get('id') or f'victim:{cls}', kind='coupling', conf=ctx.conf(s), alloc=alloc, comps=comps,
                  reduce='sum', labels=labels, info=dict(cls=cls, z_victim=zv))


# ----------------------------------------------------------------------------- (f)
def _esd(ctx, s, Struct):
    """Surge path of a protected connector pin: connector pin -> first protector on the chain
    (its pad on the protected line) -> protected part (the chain's far end)."""
    ch = s.get('chain') or []
    prot = [u for u in (s.get('protection') or [])
            if ((ctx.parts.get(u) or {}).get('role') or 'connector_protection') == 'connector_protection']
    if len(ch) < 2 or not prot:
        return None
    tc = ctx.member_term(ch[0])
    if tc is None:
        return None
    tp = None
    for m in ch[1:]:
        if m and m[0] in prot:
            tp = ctx.member_term(m)
            break
    if tp is None:
        # a shunt protector hanging off the line: its pad on the connector pin's net
        i = ctx.part(prot[0])
        if i is None:
            return None
        ks = [k for k, n in enumerate(ctx.bv.parts[i].pad_net) if n == tc.net]
        if not ks:
            return None
        tp = ctx.term(i, ks[:1])
    ti = ctx.member_term(ch[-1]) if len(ch) > 2 else None
    if ti is not None and ti.i in (tc.i, tp.i):
        ti = None
    comp = EsdComp(ctx.bv, tc, tp, ti, None, detour=ctx.t.knobs.detour('esd'))
    alloc = ctx.budget(s, 'L_nH') or PR.esd_budget()
    return Struct(id=s.get('id') or f'esd:{ctx.bv.parts[tc.i].ref}', kind='esd', conf=ctx.conf(s), alloc=alloc,
                  comps=[comp], labels=['surge path'], info=dict(protector=ctx.bv.parts[tp.i].ref,
                                                                   protected=ctx.bv.parts[ti.i].ref if ti else None))


def _antenna(ctx, s, Struct):
    T = [ctx.member_term(m) for m in s.get('feed') or []]
    T = [t for t in T if t is not None]
    if len(T) < 2:
        return None
    alloc = ctx.budget(s, 'dB') or PR.feed_budget()
    return Struct(id=s.get('id') or 'antenna', kind='antenna', conf=ctx.conf(s), alloc=alloc,
                  comps=[FeedComp(T, PR.WORLD['feed_alpha_db_mm'])], labels=['feed'])


def _world_cm(ctx, specs, aggs, Struct):
    if not aggs:
        return []
    bv = ctx.bv
    conns = {}
    for u, p in (ctx.parts or {}).items():
        if (p or {}).get('external') == 'cable':
            i = ctx.part(u)
            if i is not None:
                conns[i] = p
    for s in specs:
        if s.get('kind') == 'connector_chain' and s.get('external', 'cable') == 'cable':
            i = ctx.part(s.get('connector'))
            if i is not None:
                conns.setdefault(i, {})
    out = []
    for i in sorted(conns):
        p = bv.parts[i]
        ks = [k for k, n in enumerate(p.pad_net) if n]
        if len(ks) < 2:
            continue
        ts = [Term(i, p.pad_lx[k], p.pad_ly[k], 0.5, p.pad_net[k]) for k in ks]
        areas = [float(p.pad_sx[k] * p.pad_sy[k]) for k in ks]
        # pin row as a loop closed through the plane: the cable's conductors over the board reference
        far = max(range(len(ks)), key=lambda j: math.hypot(ts[j].lx - ts[0].lx, ts[j].ly - ts[0].ly))
        cl = LoopShape([ts[0], ts[far]], closed=False)
        cn = NodeShape(ts, areas, w=0.0)
        comps, labels = [], []
        for st, aloop, anode, ex in aggs:
            if st.comps and i in st.comps[0].parts:
                continue
            comps.append(CmComp(bv, aloop, anode, cl, cn, ex['I'], ex['V'], ex['t_sw'], bool(ctx.gnd), PR.WORLD))
            comps[-1].kern = ctx.t.kern
            labels.append(st.id)
        if comps:
            out.append(Struct(id=f'cm:{p.ref}', kind='world_cm', conf=0.5, alloc=PR.cm_budget(), comps=comps,
                              reduce='sum', labels=labels))
    return out


# ----------------------------------------------------------------------------- (e)
def _cell_losses(ctx, specs):
    """{controller part index: [(part index, W, basis)]} for converters whose loss the brief
    puts on the controller: split between controller (or discrete switches), rectifier
    diode and inductor by PR.converter_loss_split."""
    out = {}
    for s in specs:
        if s.get('kind') != 'commutation_cell':
            continue
        ctrl = ctx.part(s.get('controller'))
        if ctrl is None:
            continue
        sw = s.get('switches') or {}
        hi, lo, rect = ctx.part(sw.get('high')), ctx.part(sw.get('low')), ctx.part(sw.get('rectifier'))
        ind = ctx.part(s.get('inductor'))
        ex = s.get('excite') or {}
        diode = rect is not None and rect != ctrl and \
            (ctx.parts.get(sw.get('rectifier')) or {}).get('kind') == 'diode'
        ext = hi is not None and hi != ctrl and not diode
        out[ctrl] = dict(v_in=ex.get('V') or ctx.net_volts(s.get('vin') or s.get('rail')),
                         v_out=ctx.net_volts(s.get('vout')), i_out=ex.get('I'), boost=s.get('class') == 'boost',
                         diode=rect if diode else None, inductor=ind, high=hi if ext else None,
                         low=lo if ext and lo != hi else None)
    return out


def _thermal(ctx, specs):
    bv = ctx.bv
    t = ctx.t
    src, vic, conf_s, conf_v, alloc_v = [], [], [], [], []
    seen = set()
    cells = _cell_losses(ctx, specs)
    split_notes = []

    def add_src(i, pw, conf):
        p = bv.parts[i]
        a0, b0, a1, b1 = p.cy_bbox
        rad = max(0.5, 0.5 * math.sqrt(max((a1 - a0) * (b1 - b0), 0.25)))
        for k, (j, w0, r0) in enumerate(src):
            if j == i:
                src[k] = (j, w0 + float(pw), r0)
                return
        src.append((i, float(pw), rad))
        conf_s.append(conf)

    for s in specs:
        if s.get('kind') == 'heat_source':
            i = ctx.part(s.get('part') or s.get('ref'))
            if i is None or i in seen:
                continue
            seen.add(i)
            pw = s.get('P_W')
            if pw is None:
                role = ((ctx.parts.get(s.get('part') or '') or {}).get('role') or '').lower()
                kind = 'ldo' if 'ldo' in role else 'buck' if ('buck' in role or 'regulator' in role) else \
                    'fet' if ('fet' in role or 'transistor' in role) else 'mcu' if role in ('mcu', 'fpga', 'soc', 'processor') else 'generic'
                pw = PR.source_power_prior(kind, n_pins=len(bv.parts[i].pad_num), pkg=bv.parts[i].lib_id)[0]
            c = cells.get(i)
            if c is not None and (c['diode'] is not None or c['inductor'] is not None or c['high'] is not None):
                sp = PR.converter_loss_split(float(pw), c['v_in'], c['v_out'], c['i_out'], c['boost'],
                                             c['diode'] is not None, c['high'] is not None)
                for key, part in (('ic', i), ('diode', c['diode']), ('inductor', c['inductor']),
                                  ('high', c['high']), ('low', c['low'])):
                    if key in sp and part is not None:
                        add_src(part, sp[key], ctx.conf(s))
                    elif key in sp:
                        add_src(i, sp[key], ctx.conf(s))
                split_notes.append(f'{bv.parts[i].ref} {float(pw):.2g} W -> ' +
                                   ', '.join(f'{k} {v:.2g}' for k, v in sp.items()))
            else:
                add_src(i, pw, ctx.conf(s))
    srcset = {x[0] for x in src}
    for s in specs:
        if s.get('kind') == 'thermal_victim':
            i = ctx.part(s.get('part') or s.get('ref'))
            if i is None or i in srcset or i in vic:
                continue
            cls = s.get('class') or 'precision'
            if cls == 'crystal':
                f = None
                for s2 in specs:
                    if s2.get('kind') == 'crystal' and ctx.part(s2.get('crystal')) == i:
                        f = s2.get('f_Hz')
                if f is not None and f < 2e5:
                    cls = 'crystal_32k'
            dt = ctx.budget(s, 'dT_K')
            dt = dt or PR.Belief(PR.THERMAL_VICTIM.get(cls, 5.0), 'K', f'{cls}: allowed rise from neighbours')
            vic.append(i)
            conf_v.append(ctx.conf(s))
            alloc_v.append(dt)
    if not src:
        return
    # fin parameters from the stackup: planes (zones >= 50 % of the board) filled, others 20 %
    tc, fill = [], []
    for ly in bv.copper:
        cov = max([f for n, f in _layer_cov(bv, ly).items()] or [0.0])
        tc.append(bv.tcu.get(ly, 0.035))
        fill.append(PR.THERMAL['plane_fill'] if cov >= 0.5 else PR.THERMAL['signal_fill'])
    fr4 = max(bv.thickness - sum(tc), 0.1)
    gs, lam = fin_params(tc, fill, fr4, PR.THERMAL['k_cu'], PR.THERMAL['k_fr4'], PR.THERMAL['h_top'], PR.THERMAL['h_bot'])
    th = ThermalField(bv, src, vic, gs, lam, rings=1, kern=t.kern)
    t.thermal = th
    loc = PR.THERMAL['source_local_K']
    t._th_alloc = [PR.Belief(loc, 'K', 'hot spot above the board mean rise (design rule of thumb)')] * len(src) + alloc_v
    t._th_conf = conf_s + conf_v
    t._th_info = dict(gs_W_per_K=gs, lambda_mm=lam, mean_rise_K=th.T_mean, split=split_notes)


def _layer_cov(bv, ly):
    out = {}
    for n, l2, g in bv.zones:
        if l2 == ly:
            out[n] = out.get(n, 0.0) + g.area / max(bv.area, 1e-9)
    return out
