# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The physics brief (Contract 2): what each part, net and structure is doing physically.

    from kae.board.kicad_file import load
    from kae.circuit.brief import build, write
    brief = build(load('board.kicad_pcb'))          # a JSON-ready dict
    write(board, 'brief.json')

    python -m kae.circuit.brief BOARD.kicad_pcb [-o brief.json] [--no-sheets]

Shape (keys beyond these are additions the consumers ignore):
- `nets`: {name: {role, subrole, volts, confidence, evidence, ...}}; role is one of ground,
  rail, switch_node, clock, high_speed, analog, rf, reset, boot, signal, no_connect; `volts`
  is a float or null and `volts_belief` the full E5 Belief.
- `parts`: {footprint uuid: {ref, kind, subtype, role, external, P_W, confidence, evidence, ...}};
  `external` is 'cable', 'antenna', 'board' or null.
- `structures`: a list of dicts with `id`, `kind`, `confidence`, `evidence` and members by
  footprint uuid (`members_ref` maps them back to references for reading). Kinds:
  commutation_cell, decap, crystal, oscillator, connector_chain, victim, heat_source,
  thermal_victim, antenna. `budget` entries {quantity: {value, unit, class, basis}} appear only
  where the board states a budget-relevant fact; generic priors live in kae.physics.priors.
- `diff_pairs`, `placement_order` (structure ids, physically decisive first), `summary`.

Inputs are only what the .kicad_pcb states (names, values, footprints, lib ids, pin functions
and types, fields, net classes, schematic sheet names); positions are never read.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time

from .evidence import evidence_json
from .netlist import Netlist
from .roles import ZDIFF, ZDIFF_SRC, infer_roles
from .structures import EXTERNAL, find_structures

SCHEMA = 'kae.brief/1'
REF_FIELDS = {'controller', 'inductor', 'ic', 'crystal', 'connector', 'part', 'shunt', 'amp', 'bootstrap_cap', 'series_r',
              'feedback_r', 'caps', 'hf_caps', 'bulk_caps', 'load_caps', 'protection', 'series', 'match', 'output_caps',
              'input_caps', 'filter', 'phase_shunts', 'top', 'bottom', 'feedforward_cap', 'high', 'low', 'rectifier', 'bond'}
PAIR_FIELDS = {'loop', 'chain', 'feed', 'loads', 'ic_pins'}
KEYED_FIELDS = {'caps_p', 'caps_p_all'}
NESTED = {'switches', 'divider', 'pin_caps'}
STRUCT_ORDER = ('commutation_cells', 'antennas', 'crystals', 'oscillators', 'decaps', 'victims', 'chains', 'heat_sources',
                'thermal_victims')


# ------------------------------------------------------------------------------- uuid rewriting
class _Ids:
    """Part key -> footprint uuid (the reference when a loader gives no uuid)."""

    def __init__(self, nl: Netlist):
        self.u = {ref: (p.uuid or ref) for ref, p in nl.parts.items()}

    def __call__(self, ref):
        return None if ref is None else self.u.get(ref, ref)


def _rewrite(d: dict, ids: _Ids) -> dict:
    out = {}
    for k, v in d.items():
        if k == 'evidence':
            out[k] = evidence_json(v)
        elif k in REF_FIELDS:
            out[k] = [ids(x) for x in v] if isinstance(v, list) else ids(v) if isinstance(v, str) else v
        elif k in PAIR_FIELDS:
            out[k] = [[ids(x[0])] + list(x[1:]) for x in v] if v else v
        elif k in KEYED_FIELDS:
            out[k] = {ids(r): p for r, p in v.items()}
        elif k in NESTED and isinstance(v, dict):
            if k == 'pin_caps':
                out[k] = {pin: [ids(x) for x in refs] for pin, refs in v.items()}
            else:
                out[k] = {kk: (ids(vv) if kk in REF_FIELDS and isinstance(vv, str) else vv) for kk, vv in v.items()}
        else:
            out[k] = v
    return out


# ------------------------------------------------------------------------------- part roles from structures
def _structure_roles(st: dict) -> dict:
    """ref -> (role, structure id) for parts whose role a structure decides."""
    r = {}

    def put(ref, role, sid):
        if ref and ref not in r:
            r[ref] = (role, sid)
    for c in st['commutation_cells']:
        sid = c['id']
        caps = c.get('caps') or []
        if caps:
            put(caps[0], 'commutation_cap', sid)
            for x in caps[1:]:
                put(x, 'commutation_cap_bulk' if c['class'] != 'boost' else 'commutation_cap_bulk', sid)
        put(c.get('inductor'), 'power_inductor', sid)
        sw = c.get('switches') or {}
        if sw.get('high') and sw['high'] != c.get('controller'):
            put(sw['high'], 'high_side_switch', sid)
        if sw.get('low') and sw['low'] not in (c.get('controller'), sw.get('rectifier')):
            put(sw['low'], 'low_side_switch', sid)
        if sw.get('rectifier'):
            put(sw['rectifier'], 'freewheel_diode' if c['class'] == 'buck' else 'boost_rectifier', sid)
        put(c.get('bootstrap_cap'), 'bootstrap_cap', sid)
        for x in c.get('output_caps') or []:
            put(x, 'output_cap', sid)
        put(c.get('controller'), 'switching_regulator' if c['class'] in ('buck', 'boost') else 'bridge', sid)
        put(c.get('shunt'), 'shunt', sid)
    for x in st['crystals']:
        for cpr in x.get('load_caps') or []:
            put(cpr, 'crystal_load_cap', x['id'])
        for rr in x.get('series_r') or []:
            put(rr, 'crystal_series_r', x['id'])
        for rr in x.get('feedback_r') or []:
            put(rr, 'crystal_feedback_r', x['id'])
    for v in st['victims']:
        if v['class'] == 'feedback' or v.get('subclass') == 'divider':
            d = v.get('divider') or {}
            put(d.get('top'), 'divider_top', v['id'])
            put(d.get('bottom'), 'divider_bottom', v['id'])
            put(d.get('feedforward_cap'), 'feedforward_cap', v['id'])
        if v['class'] == 'sense':
            for f in v.get('filter') or []:
                put(f, 'sense_filter', v['id'])
    for d in st['decaps']:
        for cpr in d.get('hf_caps') or []:
            put(cpr, 'decoupling' if d['function'] in ('load', 'bypass', 'split_supply') else d['function'] + '_cap', d['id'])
        for cpr in d.get('bulk_caps') or []:
            put(cpr, 'bulk' if d['function'] in ('load', 'bypass') else d['function'] + '_cap', d['id'])
    for c in st['chains']:
        for pr in c.get('protection') or []:
            put(pr, 'connector_protection', c['id'])
        for s in c.get('series') or []:
            put(s, 'connector_series', c['id'])
    for a in st['antennas']:
        for m in a.get('match') or []:
            put(m, 'rf_match', a['id'])
    return r


# ------------------------------------------------------------------------------- priorities
def _priority(s: dict) -> tuple[float, str]:
    k = s['kind']
    if k == 'commutation_cell':
        ex = s.get('excite') or {}
        p = abs(ex.get('V') or 5.0) * (ex.get('I') or 1.0)
        return 100 + 10 * math.log10(1 + p), f"{s['class']} hot loop, ~{p:.1f} W switched"
    if k == 'antenna':
        return 85.0, 'antenna feed and keep-out'
    if k == 'crystal':
        f = s.get('f_Hz') or 0
        return 75.0 + (2 if f and f < 1e6 else 0), 'crystal loop (pF budget)'
    if k == 'victim':
        return {'sense': 70.0, 'feedback': 65.0, 'crystal': 60.0, 'reference': 45.0}.get(s['class'], 40.0), f"{s['class']} victim"
    if k == 'oscillator':
        return 60.0, 'clock source next to its load'
    if k == 'decap':
        n = len(s.get('power_pins') or [])
        base = 55.0 if s.get('function', 'load') != 'load' else 50.0
        return base + 5 * math.log10(1 + n), f"decoupling of {n} power pin(s)"
    if k == 'connector_chain':
        return (45.0 if s.get('protection') else 20.0), 'protection order at a cable' if s.get('protection') else 'cable pin'
    if k == 'heat_source':
        return 30.0 + 10 * min(3.0, s.get('P_W') or 0), 'heat source'
    if k == 'thermal_victim':
        return 25.0, 'thermal victim'
    return 10.0, k


# ------------------------------------------------------------------------------- build
def build(board, *, use_sheets: bool = True) -> dict:
    """The brief for a kae.board Board (or any object with Contract 1 field names)."""
    t0 = time.perf_counter()
    nl = Netlist.from_board(board)
    if not use_sheets:
        for p in nl.parts.values():
            p.sheet = None
    roles = infer_roles(nl)
    st = find_structures(nl, roles)
    ids = _Ids(nl)
    sroles = _structure_roles(st)
    member_of = {}
    for key in STRUCT_ORDER:
        for s in st[key]:
            for ref in _refs_in(s):
                member_of.setdefault(ref, []).append(s['id'])
    # ---- nets (a victim structure makes a signal net analog-sensitive)
    for v in st['victims']:
        for n in v.get('nets', []):
            nr = roles.nets.get(n)
            if nr is not None and nr.role in ('signal',):
                nr.role, nr.subrole = 'analog', v.get('subclass') or v['class']
                nr.confidence = max(nr.confidence, v['confidence'])
                nr.evidence = list(nr.evidence) + [e for e in v['evidence'] if e.weight > 0][:2]
    nets = {}
    for name, nr in sorted(roles.nets.items()):
        vb = nr.attrs.get('volts')
        d = {'role': nr.role, 'subrole': nr.subrole, 'volts': vb.get('value') if vb else None,
             'confidence': round(nr.confidence, 3), 'evidence': evidence_json(nr.evidence, 6)}
        if vb:
            d['volts_belief'] = vb
        for k in ('interface', 'speed', 'pair', 'source'):
            if nr.attrs.get(k):
                d[k] = nr.attrs[k]
        if nr.tags:
            d['tags'] = nr.tags
        if nr.role == 'switch_node':
            d['switch'] = {k: v for k, v in nr.attrs.items() if k in ('kind', 'inductors', 'high', 'low', 'ic', 'via', 'of')}
        cls = nl.netclass(name)
        if cls:
            d['netclass'] = cls
        nets[name] = d
    # ---- parts
    parts = {}
    for ref, pr in nl.parts.items():
        r = roles.parts[ref]
        role, sid = sroles.get(ref, (r.role, None))
        ext = None
        if r.kind == 'connector':
            ext = EXTERNAL.get(r.subtype, 'cable')
        elif r.kind == 'antenna':
            ext = 'antenna'
        d = {'ref': pr.refdes, 'kind': r.kind, 'subtype': r.subtype, 'role': role, 'external': ext,
             'P_W': (st['P_W'][ref][0] if ref in st['P_W'] else None),
             'confidence': round(r.confidence if sid is None else max(r.confidence, min(r.kind_confidence, 0.9)), 3),
             'kind_confidence': round(r.kind_confidence, 3),
             'evidence': evidence_json(r.evidence, 6), 'value': pr.value, 'lib_id': pr.lib_id}
        if r.attrs:
            d['attrs'] = {k: v for k, v in r.attrs.items() if v is not None}
        if member_of.get(ref):
            d['structures'] = member_of[ref]
        if pr.dnp:
            d['dnp'] = True
        if r.kind == 'mounting_hole' and any(p.net in roles.grounds for p in pr.pins):
            d['world'] = 'chassis_bond'
        parts[ids(ref)] = d
    # ---- structures
    structures = []
    for key in STRUCT_ORDER:
        for s in st[key]:
            refs = _refs_in(s)
            out = _rewrite(s, ids)
            out['members_ref'] = {ids.u.get(r, r): r.split('#')[0] for r in refs}
            pr_, why = _priority(s)
            out['priority'] = round(pr_, 2)
            structures.append(out)
    # ---- diff pairs
    pairs = []
    for dp in roles.pairs:
        d = {'p': dp.p, 'n': dp.n, 'interface': dp.interface, 'speed': dp.speed, 'confidence': round(dp.confidence, 3),
             'evidence': evidence_json(dp.evidence, 6)}
        if dp.interface in ZDIFF:
            z, tol = ZDIFF[dp.interface]
            d['budget'] = {'Zdiff': {'value': z, 'unit': 'ohm', 'class': 'E5', 'basis': ZDIFF_SRC[dp.interface],
                                     'interval': [round(z * (1 - tol), 1), round(z * (1 + tol), 1)]}}
        pairs.append(d)
    order = sorted(structures, key=lambda s: (-s['priority'], s['id']))
    placement_order = [{'id': s['id'], 'priority': s['priority'], 'confidence': s['confidence']} for s in order
                       if s['kind'] not in ('thermal_victim',)]
    # ---- summary
    kinds = {}
    for s in structures:
        kinds[s['kind']] = kinds.get(s['kind'], 0) + 1
    by_kind = {}
    for r in roles.parts.values():
        by_kind[r.kind] = by_kind.get(r.kind, 0) + 1
    summary = {
        'parts': len(nl.parts), 'nets': len(nl.nets), 'structures': kinds, 'parts_by_kind': by_kind,
        'unknown_parts': sorted(nl.parts[r].refdes for r, x in roles.parts.items() if x.kind == 'unknown'),
        'low_confidence_parts': sorted(nl.parts[r].refdes for r, x in roles.parts.items() if x.kind != 'unknown' and x.kind_confidence < 0.6),
        'low_confidence_structures': [s['id'] for s in structures if s['confidence'] < 0.5],
        'grounds': roles.grounds, 'rails': {n: (roles.rails[n].attrs.get('volts') or {}).get('value') for n in roles.rails},
        'switch_nodes': sorted(roles.switch_nodes), 'sheets_used': use_sheets and any(p.sheet for p in nl.parts.values()),
        'power_pins_without_caps': [{'ic': nl.parts[u['ic']].refdes, 'rail': u['rail'], 'pins': u['pins']} for u in st['uncovered']],
        'runtime_s': round(time.perf_counter() - t0, 3),
    }
    return {'schema': SCHEMA, 'board': {'path': str(getattr(board, 'path', '') or ''), 'footprints': len(nl.parts),
                                        'nets': len(nl.nets)},
            'generator': {'module': 'kae.circuit', 'inputs': 'names, values, footprints, lib ids, pin functions and types, '
                                                             'fields, net classes, zones (net only), schematic sheet names; no positions'},
            'nets': nets, 'parts': parts, 'structures': structures, 'diff_pairs': pairs,
            'placement_order': placement_order, 'summary': summary}


def _refs_in(s: dict) -> list:
    out = []

    def add(x):
        if isinstance(x, str) and x and x not in out:
            out.append(x)
    for k, v in s.items():
        if k in REF_FIELDS:
            for x in (v if isinstance(v, list) else [v]):
                add(x)
        elif k in PAIR_FIELDS and v:
            for x in v:
                add(x[0])
        elif k in NESTED and isinstance(v, dict):
            if k == 'pin_caps':
                for refs in v.values():
                    for x in refs:
                        add(x)
            else:
                for kk, vv in v.items():
                    if kk in REF_FIELDS:
                        add(vv)
    return out


def write(board, path, **kw) -> dict:
    brief = build(board, **kw)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(brief, f, indent=1, default=_json_default)
    return brief


def _json_default(o):
    if isinstance(o, float) and not math.isfinite(o):
        return None
    if isinstance(o, (set, frozenset, tuple)):
        return list(o)
    return str(o)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('board')
    ap.add_argument('-o', '--out', default=None)
    ap.add_argument('--no-sheets', action='store_true', help='ignore schematic sheet names (ablation)')
    a = ap.parse_args(argv)
    from kae.board.kicad_file import load
    b = load(a.board)
    brief = build(b, use_sheets=not a.no_sheets)
    txt = json.dumps(brief, indent=1, default=_json_default)
    if a.out:
        open(a.out, 'w', encoding='utf-8').write(txt)
        s = brief['summary']
        print(f"{a.out}: {s['parts']} parts, {sum(s['structures'].values())} structures {s['structures']}, {s['runtime_s']} s")
    else:
        sys.stdout.write(txt + '\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())
