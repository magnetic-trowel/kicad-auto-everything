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
    decap:            ic, power_pins [nums], ground_pins [nums], rail, ground, caps [uuids]
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
from .structures import (CmComp, CouplingComp, CrystalComp, EsdComp, FeedComp, LoopComp, LoopShape,
                         NodeShape, PlanePairLoop, Term, ThermalField)

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
        return Term(i, lx, ly, a, net if net is not None else p.pad_net[ks[0]])

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


def _loop_comp(ctx, terms, power, gnd_hop=None):
    bv = ctx.bv
    n = len(terms)
    kinds, widths, zb = [], [], []
    g = None
    for k in range(n):
        a, b = terms[k], terms[(k + 1) % n]
        if a.i == b.i:
            kinds.append('body')
            p = bv.parts[a.i]
            widths.append(0.3 if _is_ic(p) else float(min(max(min(a.a, b.a), 0.2), 3.0)))
            zb.append(p.zbody)
        else:
            kinds.append('board')
            widths.append(_hop_width(ctx, a.a, b.a, power))
            zb.append(0.0)
            if g is None and a.net in ctx.gnd and b.net in ctx.gnd:
                g = k
    return LoopComp(bv, terms, kinds, widths, zb, gnd_hop=g if gnd_hop is None else gnd_hop,
                    gnd_nets=ctx.gnd, knobs=ctx.t.knobs, kern=ctx.t.kern)


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


def _plane_pair(ctx, rail):
    """(d, rail layer, ground layer) when the rail and a ground net form an adjacent plane pair
    over most of the board."""
    bv = ctx.bv
    rl = {ly: f for ly, f in bv.net_plane_layers(rail).items() if f >= 0.3}
    if not rl:
        return None
    gl = {}
    for g in ctx.gnd:
        for ly, f in bv.net_plane_layers(g).items():
            if f >= 0.3:
                gl[ly] = f
    best = None
    for a in rl:
        for b in gl:
            if a == b:
                continue
            d = abs(bv.zcu[a] - bv.zcu[b])
            if d <= 0.6 and (best is None or d < best[0]):
                best = (d, a, b)
    return best


def build_structures(terms):
    ctx = _Ctx(terms)
    bv = ctx.bv
    S = terms.structs
    specs = (terms.brief or {}).get('structures', []) or []
    cells = []
    from .place_terms import Struct
    for s in specs:
        kind = s.get('kind')
        try:
            if kind == 'commutation_cell':
                st = _commutation(ctx, s, Struct)
                if st:
                    S.append(st)
                    cells.append((st, s))
            elif kind == 'decap':
                S.extend(_decap(ctx, s, Struct))
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
    _thermal(ctx, specs)


# ----------------------------------------------------------------------------- (a)
def _commutation(ctx, s, Struct):
    """Hot loop through each candidate input cap; caps in parallel weighted by the brief's
    ownership probability (expected admittance 1/L = sum_c p_c / L_c)."""
    bv = ctx.bv
    loop = s.get('loop') or []
    T = [ctx.member_term(m) for m in loop]
    if len(T) < 3 or any(t is None for t in T):
        return None
    cap_i = T[0].i if T[0].i == T[-1].i else None
    caps = [ctx.part(c) for c in (s.get('caps') or s.get('input_caps') or [])]
    caps = [c for c in caps if c is not None]
    pmap = {ctx.part(k): float(v) for k, v in (s.get('caps_p') or {}).items() if ctx.part(k) is not None}
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
            variants.append((Tc, pmap.get(c, 1.0 if c == cap_i else 0.5), cp.ref))
    comps = [_loop_comp(ctx, Tc, power=True) for Tc, _, _ in variants]
    weights = [w for _, w, _ in variants]
    labels = [lab for _, _, lab in variants]
    cls = s.get('class') or 'unknown'
    ex = s.get('excite') or {}
    vin = ex.get('V') or ctx.net_volts(s.get('rail')) or 12.0
    alloc = ctx.budget(s, 'L_nH') or PR.hot_loop_budget(cls, vin, t_sw_ns=ex.get('t_sw_ns'))
    excite = PR.hot_loop_excite(cls, vin, ex.get('I'), ex.get('t_sw_ns'))
    return Struct(id=s.get('id') or f'cell:{bv.parts[T[1].i].ref}', kind='commutation', conf=ctx.conf(s),
                  alloc=alloc, comps=comps, reduce='wparallel', labels=labels,
                  info=dict(cls=cls, V_in=vin, excite=excite, weights=weights, sw=s.get('sw'),
                            sw_nets=s.get('sw_nets') or ([s.get('sw')] if s.get('sw') else [])))


# ----------------------------------------------------------------------------- (b)
def _decap(ctx, s, Struct):
    bv = ctx.bv
    ic = ctx.part(s.get('ic'))
    if ic is None:
        return []
    P = bv.parts[ic]
    rail = s.get('rail')
    pp = ctx.pads(ic, s.get('power_pins')) if s.get('power_pins') else [k for k, n in enumerate(P.pad_net) if n == rail]
    if not rail and pp:
        rail = P.pad_net[pp[0]]
    gp = ctx.pads(ic, s.get('ground_pins')) if s.get('ground_pins') else [k for k, n in enumerate(P.pad_net) if n in ctx.gnd]
    caps = []
    pmap = {ctx.part(k): float(v) for k, v in (s.get('caps_p') or {}).items() if ctx.part(k) is not None}
    for c in (s.get('hf_caps') or s.get('caps') or []):
        i = ctx.part(c)
        if i is None:
            continue
        cp = bv.parts[i]
        kr = [k for k, n in enumerate(cp.pad_net) if n == rail]
        kg = [k for k, n in enumerate(cp.pad_net) if n in ctx.gnd or n == s.get('ground')]
        if kr and kg:
            caps.append((i, kr[:1], kg[:1]))
    pin_caps = {str(k): {ctx.part(u) for u in v} for k, v in (s.get('pin_caps') or {}).items()}
    if not pp or not gp or not caps:
        return []
    groups = _cluster([(P.pad_lx[k], P.pad_ly[k]) for k in pp], 1.6)
    vr = ctx.net_volts(rail) or 3.3
    npins = len(P.pad_num)
    alloc_pin = ctx.budget(s, 'L_nH') or PR.decap_budget(vr, npins, len(pp))
    pair = _plane_pair(ctx, rail)
    out = []
    for gi, grp in enumerate(groups):
        ks = [pp[j] for j in grp]
        tp = ctx.term(ic, ks, rail)
        cx, cy = tp.lx, tp.ly

        def gdist(k):
            return math.hypot(P.pad_lx[k] - cx, P.pad_ly[k] - cy) - 0.5 * min(P.pad_sx[k], P.pad_sy[k])
        kg = min(gp, key=gdist)
        tg = ctx.term(ic, [kg])
        comps, labels, weights = [], [], []
        paired = set()
        for k in ks:
            paired |= pin_caps.get(P.pad_num[k], set())
        all_paired = set().union(*pin_caps.values()) if pin_caps else set()
        if paired:
            use = [c for c in caps if c[0] in paired]
            wfac = 1.0
        else:
            use = [c for c in caps if c[0] not in all_paired]
            wfac = 1.0
            if not use:
                use, wfac = caps, 0.25
        for i, kr, kgc in use:
            tr = ctx.term(i, kr)
            tc = ctx.term(i, kgc)
            if pair is not None:
                comps.append(_plane_pair_comp(ctx, tp, tr, tc, pair[0], bv.parts[i]))
            else:
                comps.append(_loop_comp(ctx, [tp, tr, tc, tg], power=False))
            labels.append(bv.parts[i].ref)
            weights.append(pmap.get(i, 1.0) * wfac)
        if not comps:
            continue
        a = PR.Belief(alloc_pin.value / max(1, len(ks)), 'nH',
                      alloc_pin.basis + f'; {len(ks)} pin(s) in this cluster', alloc_pin.cls)
        out.append(Struct(id=(s.get('id') or f'decap:{P.ref}:{rail}') + (f'#{gi}' if len(groups) > 1 else ''),
                          kind='decap', conf=ctx.conf(s), alloc=a, comps=comps, reduce='wparallel', labels=labels,
                          info=dict(rail=rail, pins=[P.pad_num[k] for k in ks], plane_pair=pair is not None,
                                    weights=weights, function=s.get('function'))))
    return out


def _plane_pair_comp(ctx, tp, tr, tc, d, cap_part):
    """Mounting of the cap (body + two vias at its pads down to the pair) plus spreading."""
    from . import fastloop as FL
    zc = cap_part.zbody
    pitch = math.hypot(tr.lx - tc.lx, tr.ly - tc.ly)
    wb = max(min(tr.a, tc.a), 0.2)
    cache = {}

    def mount(h):
        key = round(h, 3)
        v = cache.get(key)
        if v is None:
            H = [(0.0, 0.0, pitch, 0.0, wb, h + zc)]
            V = [(0.0, 0.0, 0.0, h + zc, 0.15), (pitch, 0.0, h + zc, 0.0, 0.15)]
            v = FL.loop_fast(H, V)
            cache[key] = v
        return v
    return PlanePairLoop(ctx.bv, tp, (tr, tc), d, mount, 0.3)


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
    comp = CrystalComp(bv, ti, to, sens)
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
        open_ = T[0].net in ctx.gnd and T[-1].net in ctx.gnd
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
    ch = s.get('chain') or []
    if len(ch) < 2 or not s.get('protection'):
        return None
    tc = ctx.member_term(ch[0])
    tp = ctx.member_term(ch[1])
    ti = ctx.member_term(ch[2]) if len(ch) > 2 else None
    if tc is None or tp is None:
        return None
    comp = EsdComp(ctx.bv, tc, tp, ti, None)
    alloc = ctx.budget(s, 'L_nH') or PR.esd_budget()
    return Struct(id=s.get('id') or f'esd:{ctx.bv.parts[tc.i].ref}', kind='esd', conf=ctx.conf(s), alloc=alloc,
                  comps=[comp], labels=['esd path'])


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
def _thermal(ctx, specs):
    bv = ctx.bv
    t = ctx.t
    src, vic, conf_s, conf_v, alloc_v = [], [], [], [], []
    seen = set()
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
            p = bv.parts[i]
            a0, b0, a1, b1 = p.cy_bbox
            rad = max(0.5, 0.5 * math.sqrt(max((a1 - a0) * (b1 - b0), 0.25)))
            src.append((i, float(pw), rad))
            conf_s.append(ctx.conf(s))
    for s in specs:
        if s.get('kind') == 'thermal_victim':
            i = ctx.part(s.get('part') or s.get('ref'))
            if i is None or any(i == x[0] for x in src) or i in vic:
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
    rise = PR.THERMAL['source_rise_K']
    t._th_alloc = [PR.Belief(rise, 'K', 'board-level rise at a heat source (40 K design target)')] * len(src) + alloc_v
    t._th_conf = conf_s + conf_v
    t._th_info = dict(gs_W_per_K=gs, lambda_mm=lam)


def _layer_cov(bv, ly):
    out = {}
    for n, l2, g in bv.zones:
        if l2 == ly:
            out[n] = out.get(n, 0.0) + g.area / max(bv.area, 1e-9)
    return out
