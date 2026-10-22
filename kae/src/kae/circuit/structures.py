# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Physical structures from roles and connectivity: what the placer must put first.

Every structure is a dict in the brief's shape (docs/topics/physics/comprehension.md), with
members named by part key (reference designator; brief.py rewrites them as footprint uuids):

- commutation_cell: buck, boost and half-bridge hot loops. `loop` lists [part, pad or [pads]]
  in current order and closes on the commutation capacitor (Cin+ ... Cin- for a buck, Cout+
  ... Cout- for a boost, Cbus+ ... Cbus- for a bridge), following the membership table of
  docs/topics/rules/power/hot-loops.md. A 4-switch buck-boost is a buck cell plus a boost
  cell; an integrated bridge IC is one half_bridge cell (Cbus+, IC supply pins, IC ground
  pins, Cbus-); a regulator module with its inductor inside is a buck cell without a switch
  node. `excite` carries V, I and t_sw_ns (E5 estimates, with their basis).
- decap: per (IC, rail, ground): the IC's power and ground pins and the capacitors that serve
  them. Ownership of capacitors on a rail shared by several ICs is a probability (`caps_p`),
  from pin counts, schematic sheet and reference blocks; never from positions.
- crystal: crystal, IC pins (xin, xout), load capacitors, series and feedback resistors.
- oscillator (extra kind): active oscillator, output net and its loads.
- connector_chain: per connector pin, the path connector -> protection -> series parts -> IC.
- victim: feedback dividers (FB node), Kelvin sense loops of shunts, analog-sensitive nets,
  references, crystal nets.
- heat_source / thermal_victim: parts that dissipate, parts whose function drifts with heat.
- antenna: antennas, RF connectors and integrated-antenna modules with their feed chains.

Each structure carries `confidence` (logistic of summed evidence, capped by the weakest
member role it depends on) and `evidence` (list of Evidence).
"""
from __future__ import annotations

import math
import re
from collections import defaultdict

from . import values as V
from .evidence import MODERATE, STRONG, WEAK, confidence, ev
from .netlist import Netlist, Part
from .roles import (BOOT_PIN, EN_PIN, FB_PIN, GND_PIN, IN_PIN, OUT_PIN, PWR_PIN, SW_PIN, XTAL_PIN, Roles, belief,
                    cap_class, regulator_vout)

REGULATOR_SUBS = ('regulator_linear', 'regulator_switching', 'regulator_module', 'pmic', 'charger', 'charge_pump')
LOAD_KINDS = ('ic', 'module', 'oscillator', 'led', 'optocoupler', 'microphone', 'crystal')

# switching frequency (Hz) and rated output current (A) by part-number prefix: datasheet values,
# typical where the part is programmable (E5 in the brief, with the table as basis)
SWITCHER_TABLE = [
    (r'AP6320[0-9]', 500e3, 2.0), (r'AP6330[0-9]', 500e3, 3.0), (r'AP63357', 450e3, 3.5), (r'AP62300', 750e3, 3.0),
    (r'AP3441', 1.5e6, 1.0), (r'TPS54202', 500e3, 2.0), (r'TPS561201', 580e3, 1.0), (r'TPS56\d', 600e3, 2.0),
    (r'TPS5430', 500e3, 3.0), (r'TPS6213\d', 2.5e6, 3.0), (r'TPS6216\d', 2.25e6, 1.0), (r'TPS6223\d', 2e6, 0.5),
    (r'TPS6208\d', 4e6, 0.5), (r'TPS62\d{3}', 2e6, 1.0), (r'TLV6256[89]', 1.5e6, 2.0), (r'TLV6256[5-7]', 1.5e6, 1.0),
    (r'TLV62\d{3}', 1.5e6, 1.0), (r'TPS6102\d', 1e6, 1.5), (r'TPS6132\d', 1.6e6, 1.0), (r'TPS61\d{3}', 1e6, 1.0),
    (r'TPS63802', 2.1e6, 2.0), (r'TPS63\d{3}', 2.4e6, 1.0), (r'TPS55340', 1.2e6, 1.0), (r'MP1584', 1.5e6, 3.0),
    (r'MP2307', 340e3, 3.0), (r'MP2315', 500e3, 3.0), (r'MP23\d\d', 500e3, 2.0), (r'MP1\d{3}', 1e6, 1.0),
    (r'MPM3683', 1e6, 8.0), (r'MPM54304', 1.2e6, 3.0), (r'MPM\d{4}', 1e6, 2.0), (r'LM2596', 150e3, 3.0),
    (r'LM2576', 52e3, 3.0), (r'LM267\d', 260e3, 3.0), (r'LM2731', 1.6e6, 0.5), (r'LM27313', 1.6e6, 0.5), (r'LM2735', 1.6e6, 1.0),
    (r'LM3671', 2e6, 0.6), (r'LM3670', 1e6, 0.35), (r'LMR36006', 2.1e6, 0.6), (r'LMR3801\d', 400e3, 1.0),
    (r'LMR54406', 1.1e6, 0.6), (r'LMR\d{5}', 1e6, 1.0), (r'LM25119', 400e3, 10.0), (r'LT8364', 1e6, 2.0),
    (r'LT1373', 250e3, 1.5), (r'MT3608', 1.2e6, 2.0), (r'SX1308', 1.2e6, 2.0), (r'MT2492', 600e3, 2.0),
    (r'SY8201', 500e3, 1.0), (r'SY8\d{3}', 1e6, 2.0), (r'XL4015', 180e3, 5.0), (r'XL6009', 400e3, 4.0),
    (r'TPSM863257', 1.2e6, 3.0), (r'TPSM365R\d', 1e6, 0.5), (r'TPSM\d', 1e6, 2.0), (r'FAN5622', 1e6, 0.1),
    (r'MIC28517', 300e3, 8.0), (r'nPM1300', 3e6, 0.2), (r'TX4138', 380e3, 3.0), (r'MYMGK', 1e6, 5.0), (r'LMZ\d', 1e6, 2.0),
]
MOTOR_TABLE = [(r'TMC6300', 1.2), (r'DRV8411', 4.0), (r'DRV8876', 3.5), (r'DRV8426', 1.5), (r'MCF8316', 4.0), (r'DRV8316', 4.0),
               (r'DRV2603', 0.5), (r'TB6612', 1.2), (r'DRV88\d\d', 2.0), (r'A49\d\d', 2.0), (r'L298', 2.0), (r'TMC2\d{3}', 1.5)]
VREF_TABLE = [(r'TPS54202', 0.596), (r'TPS561201', 0.768), (r'TLV6256', 0.6), (r'TPS62', 0.8), (r'MP1584', 0.8), (r'MT3608', 0.6),
              (r'SX1308', 0.6), (r'LM2596', 1.23), (r'LM2576', 1.23), (r'LM317', 1.25), (r'1117', 1.25), (r'LMR3600', 1.0), (r'LMR3801', 1.0),
              (r'LM2731', 1.23), (r'LM27313', 1.23), (r'LT8364', 1.6), (r'TPS6102', 0.5), (r'TPS613221', 0.6), (r'TPS63802', 0.5),
              (r'MIC28517', 0.6), (r'AP3441', 0.6), (r'AP62300', 0.8), (r'AP63357', 0.8), (r'MT2492', 0.6), (r'SY8201', 0.6),
              (r'TLV767', 0.8), (r'TLV757', 0.55), (r'TPS7A', 0.8), (r'LT1129', 3.75), (r'LT1373', 1.245), (r'LM25119', 0.8),
              (r'TPSM863257', 0.6), (r'LMR54406', 0.8), (r'MPM3683', 0.6)]


# =============================================================================== helpers
class _B:
    """Board accessors shared by the detectors."""

    def __init__(self, nl: Netlist, roles: Roles):
        self.nl = nl
        self.r = roles
        self.g = set(roles.grounds)

    def k(self, ref):
        return self.r.parts[ref].kind

    def sub(self, ref):
        return self.r.parts[ref].subtype

    def pads(self, ref, net):
        return sorted({p.number for p in self.nl.parts[ref].pins_on(net)}, key=_natkey)

    def pad_sel(self, ref, net):
        ps = self.pads(ref, net)
        return ps[0] if len(ps) == 1 else ps

    def pins_named(self, ref, rx_):
        return [p for p in self.nl.parts[ref].pins if p.net and not p.nc and rx_.match(p.fn)]

    def gnd_of(self, ref):
        """The part's ground net: the ground with most of its pins (PGND-named pins win)."""
        part = self.nl.parts[ref]
        cnt = defaultdict(float)
        for p in part.pins:
            if p.net in self.g:
                cnt[p.net] += 1 + (2 if re.match(r'^P?GND|^PGND', p.fn) and 'A' not in p.fn[:2] else 0)
        return max(cnt, key=cnt.get) if cnt else self.r.gnd

    def caps_on(self, net, gnd=None):
        """Capacitors from `net` to a ground (the given one first)."""
        lst = self.r.caps_to.get(net, [])
        if gnd:
            lst = sorted(lst, key=lambda t: (t[1] != gnd, _refkey(t[0])))
        return [c for c, _ in lst]

    def cap_pad(self, cref, net):
        return self.pad_sel(cref, net)

    def volts(self, net):
        nr = self.r.nets.get(net)
        b = (nr.attrs.get('volts') if nr else None) or {}
        return b.get('value')

    def short(self, net):
        return self.nl.nets[net].short if net in self.nl.nets else str(net)

    def two(self, ref):
        return self.nl.two_nets(self.nl.parts[ref])


def _natkey(s):
    return [int(t) if t.isdigit() else t for t in re.split(r'(\d+)', str(s))]


def _refkey(ref):
    m = re.match(r'([A-Za-z_#]*)(\d*)', ref)
    return (m.group(1), int(m.group(2)) if m.group(2) else 0, ref)


def _hf_order(nl, refs):
    """Commutation-cap preference: ceramic before polarized, smallest body, smallest value."""
    def key(ref):
        part = nl.parts[ref]
        cls, farads, _ = cap_class(part)
        pk = part.package
        return (pk.polarized, pk.area_mm2 if pk.area_mm2 is not None else 50.0, farads if farads is not None else 1.0, _refkey(ref))
    return sorted(refs, key=key)


def _struct(kind, sid, evs, conf_cap=1.0, prior=0.0, **kw):
    c = min(conf_cap, confidence(evs, prior=prior))
    d = {'id': sid, 'kind': kind, 'confidence': round(c, 3), 'evidence': evs}
    d.update(kw)
    return d


def diode_side(part: Part, net: str) -> str | None:
    """'A' or 'K' for the diode pad on `net`: pin function, else KiCad's convention (pad 1 = K)."""
    for p in part.pins_on(net):
        fn = p.fn
        if fn in ('A', 'ANODE', 'A1', 'A2', '+'):
            return 'A'
        if fn in ('K', 'C', 'CATHODE', 'K1', 'K2', '-'):
            return 'K'
        if len(part.active_pins()) == 2 and p.number in ('1', '2'):
            return 'K' if p.number == '1' else 'A'
    return None


def fet_terminals(b: _B, ref: str, mid: str):
    """For a transistor with a terminal on `mid`: (gate net, other main-terminal net) from pin functions,
    else from nets (the gate is the net that is neither `mid` nor a rail/ground)."""
    part = b.nl.parts[ref]
    by = {p.fn: p.net for p in part.active_pins()}
    if 'G' in by and ('D' in by or 'S' in by):
        others = {by.get('D'), by.get('S')} - {mid}
        return by['G'], (others.pop() if len(others) == 1 else None)
    if 'B' in by and ('C' in by or 'E' in by):
        others = {by.get('C'), by.get('E')} - {mid}
        return by['B'], (others.pop() if len(others) == 1 else None)
    nets = set(part.nets) - {mid}
    if len(nets) != 2:
        return None, None
    a, c = sorted(nets)
    pa = a in b.g or a in b.r.rails or b.r.caps_to.get(a) or a in b.r.switch_nodes
    pc = c in b.g or c in b.r.rails or b.r.caps_to.get(c) or c in b.r.switch_nodes
    if pa and not pc:
        return c, a
    if pc and not pa:
        return a, c
    return None, None


def _inductor_current(part: Part) -> float | None:
    m = re.search(r'(?<![\w.])(\d+(?:\.\d+)?)\s*A(?![a-zA-Z])', part.value + ' ' + ' '.join(str(v) for v in part.fields.values()))
    if m:
        v = float(m.group(1))
        return v if 0.05 <= v <= 100 else None
    return None


def _table(text, table):
    for pat, *vals in table:
        if re.search(pat, text, re.I):
            return pat, vals
    return None, None


# =============================================================================== commutation cells
def commutation_cells(b: _B) -> list:
    cells = []
    used_sw = set()
    sw = b.r.switch_nodes
    # ---------------------------------------------------------------- inductor-based converters
    by_ind = {}
    for net, d in sw.items():
        if d['kind'] == 'inductor':
            for L in d['inductors']:
                by_ind.setdefault(L, []).append(net)
    for L, swnets in sorted(by_ind.items(), key=lambda t: _refkey(t[0])):
        lpart = b.nl.parts[L]
        t = b.two(L)
        if not t:
            continue
        if len(swnets) >= 2:          # both ends switched: 4-switch buck-boost
            cells += _buck_boost(b, L, swnets)
            used_sw |= set(swnets)
            continue
        swn = swnets[0]
        other = t[0] if t[1] == swn else t[1]
        c = _converter(b, L, lpart, swn, other)
        if c:
            cells.append(c)
            used_sw.add(swn)
    # ---------------------------------------------------------------- discrete half-bridges, grouped into bridges
    legs = []
    for net, d in sw.items():
        if d['kind'] != 'half_bridge' or net in used_sw:
            continue
        leg = _half_bridge_leg(b, net, d)
        if leg:
            legs.append(leg)
    by_rail = defaultdict(list)
    for leg in legs:
        by_rail[leg['rail']].append(leg)
    for rail, ls in by_rail.items():
        n = len(ls)
        for i, leg in enumerate(sorted(ls, key=lambda x: x['sw'])):
            leg['bridge'] = {'legs': n, 'type': {1: 'half_bridge', 2: 'full_bridge', 3: 'three_phase'}.get(n, f'{n}_legs'),
                             'sw_nets': [x['sw'] for x in ls]}
            cells.append(leg)
    # ---------------------------------------------------------------- integrated bridges (motor drivers, class D)
    by_ic = defaultdict(list)
    for net, d in sw.items():
        if d['kind'] == 'bridge_output':
            by_ic[d['ic']].append(net)
    for ic, outs in sorted(by_ic.items(), key=lambda t: _refkey(t[0])):
        c = _integrated_bridge(b, ic, sorted(outs))
        if c:
            cells.append(c)
    # ---------------------------------------------------------------- regulator modules with the inductor inside
    covered = {c.get('controller') for c in cells}
    for ref, pr in b.r.parts.items():
        if pr.kind in ('ic', 'module') and pr.subtype == 'regulator_module' and ref not in covered:
            c = _module_cell(b, ref)
            if c:
                cells.append(c)
    return cells


def _vin_pins(b: _B, ic: str, exclude: set, suffix: str = ''):
    """Supply-input pins of a controller (VIN, PVIN, VCC ...) on non-ground nets not in `exclude`."""
    part = b.nl.parts[ic]
    pins = [p for p in part.active_pins() if p.net not in b.g and p.net not in exclude and
            (IN_PIN.match(p.fn) or re.match(r'^P?VIN\w*|^VIN\d?$|^PVIN\w*|^VS$|^VCC$|^VM$|^VBAT$|^VSYS$|^AVIN$', p.fn))]
    if suffix:
        same = [p for p in pins if p.fn.endswith(suffix)]
        pins = same or pins
    # rank: named PVIN/VIN first, then nets with capacitors
    pins.sort(key=lambda p: (not re.match(r'^P?VIN', p.fn), -len(b.r.caps_to.get(p.net, ())), p.number))
    return pins


def _gnd_pins(b: _B, ic: str, suffix: str = ''):
    part = b.nl.parts[ic]
    pins = [p for p in part.active_pins() if p.net in b.g]
    pg = [p for p in pins if re.match(r'^PGND', p.fn)]
    if suffix and pg:
        same = [p for p in pg if p.fn.endswith(suffix)]
        pg = same or pg
    if pg:
        return pg
    # exposed pad / GND pins: the ones named GND or EP, else all on the ground net
    gp = [p for p in pins if re.match(r'^(GND|EP|PAD|EPAD|THERMAL|VSS|E?PAD)\w*$', p.fn) or not p.fn or p.fn == p.number]
    return gp or pins


def _excite(b: _B, ctrl, L, V_, kind):
    """E5 estimates of the switched voltage, current and edge time, with their basis."""
    basis = []
    text = b.nl.parts[ctrl].text() if ctrl else ''
    pat, vals = _table(text, SWITCHER_TABLE) if ctrl else (None, None)
    f_sw = vals[0] if vals else None
    I_ = None
    if L:
        ir = _inductor_current(b.nl.parts[L])
        if ir:
            I_ = round(0.6 * ir, 3)
            basis.append(f"I = 0.6 x the {ir:g} A rating in {L}'s value")
    if I_ is None and vals:
        I_ = vals[1]
        basis.append(f"I = rated output of {pat} ({vals[1]:g} A)")
    if I_ is None and ctrl:
        mpat, mv = _table(text, MOTOR_TABLE)
        if mv:
            I_ = mv[0]
            basis.append(f"I = rated output of {mpat} ({mv[0]:g} A)")
    if I_ is None:
        I_ = {'buck': 1.0, 'boost': 0.5, 'half_bridge': 5.0}.get(kind, 1.0)
        basis.append(f"I = class default for {kind} ({I_:g} A), no rating found")
    if f_sw:
        basis.append(f"f_sw = {V.si(f_sw, 'Hz')} for {pat}")
    if kind == 'half_bridge' and ctrl and b.r.parts[ctrl].subtype in ('motor_driver', 'audio_amp'):
        t_sw = 50.0 if b.r.parts[ctrl].subtype == 'motor_driver' else 5.0
        basis.append(f"t_sw = {t_sw:g} ns, class default for an integrated {b.r.parts[ctrl].subtype}")
    elif kind == 'half_bridge':
        gan = ctrl and re.search(r'EPC|GaN|LMG', text)
        t_sw = 1.0 if gan else 15.0
        basis.append(f"t_sw = {t_sw:g} ns, class default for a {'GaN' if gan else 'discrete Si MOSFET'} half-bridge")
    else:
        t_sw = 2.0 if (V_ or 5) <= 24 else 5.0
        basis.append(f"t_sw = {t_sw:g} ns, class default for an integrated converter at {V_ or '?'} V")
    if V_ is None:
        basis.append('V unknown: the rail has no voltage in its name or part numbers')
    return {'V': V_, 'I': I_, 't_sw_ns': t_sw, 'f_sw_Hz': f_sw, 'basis': basis}


def _caps_with_p(b: _B, rail, gnd, owner, competitors=()):
    """Commutation-cap candidates on (rail, gnd) in preference order, with ownership probability:
    split by pin count when other consumers sit on the same rail."""
    caps = _hf_order(b.nl, b.caps_on(rail, gnd))
    if not caps:
        return [], {}
    n_comp = len(competitors)
    p = {}
    for c in caps:
        aff = _affinity(b, c, owner)
        others = sum(math.exp(_affinity(b, c, o)) for o in competitors)
        p[c] = round(math.exp(aff) / (math.exp(aff) + others), 3) if n_comp else 1.0
    order = {c: i for i, c in enumerate(caps)}
    caps = sorted(caps, key=lambda c: (-p[c], order[c]))
    return caps, p


def _affinity(b: _B, cap, owner) -> float:
    """Schematic affinity of a capacitor to a part: same sheet, same reference block. Not positions."""
    a = 0.0
    pc, po = b.nl.parts[cap], b.nl.parts[owner]
    if pc.sheet and po.sheet and _multi_sheet(b):
        a += 2.0 if pc.sheet == po.sheet else -1.0
    if _blocks(b) and pc.number is not None and po.number is not None and pc.number >= 100 and po.number >= 100:
        a += 1.5 if pc.number // 100 == po.number // 100 else -0.5
    return a


def _multi_sheet(b: _B) -> bool:
    if not hasattr(b, '_ms'):
        b._ms = len({p.sheet for p in b.nl.parts.values() if p.sheet}) >= 2
    return b._ms


def _blocks(b: _B) -> bool:
    """True when references are numbered in per-sheet blocks of 100 (U301, C305 ...)."""
    if not hasattr(b, '_bl'):
        nums = [p.number for p in b.nl.parts.values() if p.number is not None and p.prefix in ('C', 'R', 'U')]
        b._bl = len(nums) >= 10 and sum(n >= 100 for n in nums) >= 0.7 * len(nums)
    return b._bl


def _consumers(b: _B, rail, exclude=()):
    """Parts that draw from a rail through power pins (for cap ownership)."""
    out = []
    for p in b.nl.pins(rail):
        if p.ref in exclude or p.ref in out:
            continue
        if b.k(p.ref) in LOAD_KINDS and (p.ptype in ('power_in', 'power_out') or PWR_PIN.match(p.fn) or IN_PIN.match(p.fn)):
            out.append(p.ref)
    return out


def _cell_ground(b: _B, ctrl, other_hint=None):
    if ctrl:
        gp = _gnd_pins(b, ctrl)
        if gp:
            cnt = defaultdict(int)
            for p in gp:
                cnt[p.net] += 1
            return max(cnt, key=cnt.get)
    return other_hint or b.r.gnd


def _converter(b: _B, L, lpart, swn, other):
    nv = b.nl.nets[swn]
    evs = [ev('topology', f"power inductor {L} ({lpart.value}) between '{b.short(swn)}' and '{b.short(other)}'", MODERATE)]
    evs += [e for e in b.r.switch_nodes[swn]['evidence'] if e.weight > 0][:3]
    ics = sorted({p.ref for p in nv.pins if b.k(p.ref) in ('ic', 'module') and p.ref != L}, key=_refkey)
    sw_pins = [p for p in nv.pins if p.ref in ics and SW_PIN.match(p.fn)]
    ctrl = sw_pins[0].ref if sw_pins else (ics[0] if ics else None)
    fets = sorted({p.ref for p in nv.pins if b.k(p.ref) == 'transistor'}, key=_refkey)
    diodes = sorted({p.ref for p in nv.pins if b.k(p.ref) == 'diode' and b.sub(p.ref) not in ('tvs', 'esd_array', 'zener')}, key=_refkey)
    suffix = ''
    if sw_pins:
        m = re.search(r'(\d|[AB])$', sw_pins[0].fn)
        suffix = m.group(1) if m else ''
    # gate driver/controller for external FETs
    if ctrl is None and fets:
        for q in fets:
            gate, _ = fet_terminals(b, q, swn)
            if gate:
                drv = [p.ref for p in b.nl.pins(gate) if b.k(p.ref) in ('ic', 'module')]
                if not drv:      # through a gate resistor
                    for p in b.nl.pins(gate):
                        if b.k(p.ref) == 'resistor':
                            o = b.nl.other_net(b.nl.parts[p.ref], gate)
                            drv += [x.ref for x in b.nl.pins(o) if b.k(x.ref) in ('ic', 'module')] if o else []
                if drv:
                    ctrl = drv[0]
                    evs.append(ev('topology', f"{ctrl} drives the gate of {q}", WEAK))
                    break
    # ---- hypotheses
    hs = ls = None
    hs_rail = ls_ret = None
    for q in fets:
        gate, o = fet_terminals(b, q, swn)
        if o is None:
            continue
        if o in b.g or (o not in b.r.rails and any(b.k(p.ref) == 'resistor' and (V.resistance(b.nl.parts[p.ref].value) or 1) <= 0.2
                                                   for p in b.nl.pins(o))):
            ls, ls_ret = q, o
        elif o != other and (o in b.r.rails or b.r.caps_to.get(o)):
            hs, hs_rail = q, o
        elif o == other:
            hs, hs_rail = q, o      # sync boost: high-side FET to the output
    d_catch = d_boost = None
    for d in diodes:
        dpart = b.nl.parts[d]
        side = diode_side(dpart, swn)
        o = b.nl.other_net(dpart, swn)
        if side == 'K' and o in b.g:
            d_catch = d
        elif side == 'A' and o and o not in b.g and o != other:
            d_boost = (d, o)
    vin_pins = _vin_pins(b, ctrl, {swn, other}, suffix) if ctrl else []
    out_pins = [p for p in b.nl.parts[ctrl].active_pins() if OUT_PIN.match(p.fn) and p.net not in (swn,) and p.net not in b.g] if ctrl else []
    ctrl_in_on_other = ctrl and any(p.net == other and (IN_PIN.match(p.fn) or p.ptype == 'power_in') for p in b.nl.parts[ctrl].active_pins())
    sb, eb, sbo, ebo = 0.0, [], 0.0, []
    if vin_pins:
        sb += 2.0
        eb.append(ev('pinfunction', f"{ctrl} input pin {vin_pins[0].label} on '{b.short(vin_pins[0].net)}' (not the inductor's far end)", 2.0))
    if hs and hs_rail != other:
        sb += 2.5
        eb.append(ev('topology', f"high-side switch {hs} from '{b.short(hs_rail)}' to the switch node", 2.5))
    if d_catch:
        sb += 2.0
        eb.append(ev('topology', f"catch diode {d_catch}: cathode on the switch node, anode on ground", 2.0))
    if b.r.caps_to.get(other):
        sb += 0.5
        eb.append(ev('topology', f"{len(b.r.caps_to[other])} capacitor(s) on the far end (output)", 0.5))
    if d_boost:
        sbo += 3.0
        ebo.append(ev('topology', f"rectifier {d_boost[0]}: anode on the switch node, cathode on '{b.short(d_boost[1])}'", 3.0))
    if ctrl_in_on_other:
        sbo += 2.0
        ebo.append(ev('pinfunction', f"{ctrl} supply pin on the inductor's far end '{b.short(other)}' (inductor fed from the input)", 2.0))
    if out_pins and any(p.net != other for p in out_pins) and ctrl and b.sub(ctrl) != 'regulator_linear':
        sbo += 1.5
        ebo.append(ev('pinfunction', f"{ctrl} output pin {out_pins[0].label} on another net", 1.5))
    if ls and not hs and not d_catch:
        sbo += 1.5
        ebo.append(ev('topology', f"low-side switch {ls} only", 1.5))
    txt = b.nl.parts[ctrl].text() if ctrl else ''
    if re.search(r'boost|step.?up|TPS61|TLV61|MT3608|SX1308|LM2731|LM27313|LM2735|LT1373|LT8364|XL6009|MCP16[45]|AP3012|AP3015|ME2108|HT77', txt, re.I):
        sbo += 1.5
        ebo.append(ev('table', f"boost part number in '{b.nl.parts[ctrl].value}'", 1.5))
    if re.search(r'buck|step.?down|TPS5|TPS62|TLV62|LMR\d|LM259|LM257|MP1584|MP2\d|AP63|AP62|AP3441|MT2492|SY8|XL4|TPSM|LMZ|MPM', txt, re.I):
        sb += 1.5
        eb.append(ev('table', f"buck part number in '{b.nl.parts[ctrl].value}'", 1.5))
    if sb == 0 and sbo == 0:
        return None
    kind = 'buck' if sb >= sbo else 'boost'
    margin = abs(sb - sbo)
    evs += eb if kind == 'buck' else ebo
    if margin < 1.0:
        evs.append(ev('derived', f"buck {sb:g} vs boost {sbo:g}: topology ambiguous", -1.5))
    if kind == 'buck':
        rail = vin_pins[0].net if vin_pins else hs_rail
        out = other
    else:
        rail = d_boost[1] if d_boost else (next((p.net for p in out_pins if p.net != other), None) or (hs_rail if hs_rail and hs_rail != other else None))
        out = rail
    if rail is None:
        return None
    gnd = _cell_ground(b, ctrl, ls_ret if ls_ret in b.g else None)
    if ls_ret and ls_ret not in b.g:       # low-side through a shunt: the shunt's ground
        for p in b.nl.pins(ls_ret):
            if b.k(p.ref) == 'resistor':
                o2 = b.nl.other_net(b.nl.parts[p.ref], ls_ret)
                if o2 in b.g:
                    gnd = o2
    excl = {ctrl} if ctrl else set()
    comp = [x for x in _consumers(b, rail, exclude=excl | {L}) if x != ctrl]
    caps, cp = _caps_with_p(b, rail, gnd, ctrl or L, comp)
    if not caps:
        evs.append(ev('topology', f"no capacitor from '{b.short(rail)}' to ground: no commutation capacitor found", -2.0))
    hf = caps[0] if caps else None
    loop = []
    if hf:
        loop.append([hf, b.cap_pad(hf, rail)])
    if kind == 'buck':
        if hs and hs_rail != other:
            loop += [[hs, b.pad_sel(hs, rail)], [hs, b.pad_sel(hs, swn)]]
        elif ctrl:
            loop.append([ctrl, [p.number for p in vin_pins if p.net == rail] or b.pads(ctrl, rail)])
            if d_catch or ls:
                loop.append([ctrl, b.pads(ctrl, swn)])
        if ls:
            loop += [[ls, b.pad_sel(ls, swn)], [ls, b.pad_sel(ls, ls_ret)]]
        elif d_catch:
            loop += [[d_catch, b.pad_sel(d_catch, swn)], [d_catch, b.pad_sel(d_catch, gnd)]]
        elif ctrl:
            gp = _gnd_pins(b, ctrl, suffix)
            loop.append([ctrl, sorted({p.number for p in gp}, key=_natkey)])
    else:
        if d_boost:
            loop += [[d_boost[0], b.pad_sel(d_boost[0], rail)], [d_boost[0], b.pad_sel(d_boost[0], swn)]]
            if ls:
                loop += [[ls, b.pad_sel(ls, swn)], [ls, b.pad_sel(ls, ls_ret)]]
            elif ctrl:
                loop.append([ctrl, b.pads(ctrl, swn)])
                loop.append([ctrl, sorted({p.number for p in _gnd_pins(b, ctrl, suffix)}, key=_natkey)])
        elif hs:
            loop += [[hs, b.pad_sel(hs, rail)], [hs, b.pad_sel(hs, swn)]]
            if ls:
                loop += [[ls, b.pad_sel(ls, swn)], [ls, b.pad_sel(ls, ls_ret)]]
        elif ctrl:
            loop.append([ctrl, b.pads(ctrl, rail)])
            loop.append([ctrl, sorted({p.number for p in _gnd_pins(b, ctrl, suffix)}, key=_natkey)])
    if hf:
        loop.append([hf, b.cap_pad(hf, gnd if gnd in b.nl.parts[hf].nets else next(iter(b.nl.parts[hf].nets - {rail})))])
    vin_net = rail if kind == 'buck' else other
    V_ = b.volts(rail)
    exc = _excite(b, ctrl, L, V_, kind)
    boot = None
    if ctrl:
        for p in b.pins_named(ctrl, BOOT_PIN):
            for c in b.nl.pins(p.net):
                if b.k(c.ref) == 'capacitor' and swn in b.nl.parts[c.ref].nets:
                    boot = c.ref
    out_caps = _hf_order(b.nl, b.caps_on(out if kind == 'buck' else other))
    conf_cap = min(b.r.nets[swn].confidence, b.r.parts[L].kind_confidence + 0.2)
    cid = f"cell:{kind}:{ctrl or L}" + (f":{suffix}" if suffix else '')
    return _struct('commutation_cell', cid, evs, conf_cap=conf_cap, prior=-0.5,
                   **{'class': kind, 'loop': loop, 'rail': rail, 'sw': swn, 'gnd': gnd, 'excite': exc,
                      'controller': ctrl, 'inductor': L, 'caps': caps, 'caps_p': cp,
                      'switches': {'high': hs or (ctrl if kind == 'buck' else None), 'low': ls or d_catch or (ctrl if not d_boost else None),
                                   'rectifier': (d_boost[0] if d_boost else d_catch)},
                      'vin': vin_net, 'vout': out if kind == 'buck' else rail, 'output_caps': out_caps[:6] if kind == 'buck' else [],
                      'input_caps': out_caps[:6] if kind == 'boost' else caps[:6], 'bootstrap_cap': boot,
                      'integrated_switches': bool(ctrl and not hs and not ls)})


def _buck_boost(b: _B, L, swnets):
    """A 4-switch buck-boost: one buck cell on the input half-bridge, one boost cell on the output half-bridge."""
    nv = [b.nl.nets[n] for n in swnets]
    ics = sorted({p.ref for v in nv for p in v.pins if b.k(p.ref) in ('ic', 'module')}, key=_refkey)
    if not ics:
        return []
    ctrl = ics[0]
    part = b.nl.parts[ctrl]
    vin = _vin_pins(b, ctrl, set(swnets))
    outs = [p for p in part.active_pins() if OUT_PIN.match(p.fn) and p.net not in swnets and p.net not in b.g]
    if not vin or not outs:
        return []
    rin, rout = vin[0].net, outs[0].net
    gnd = _cell_ground(b, ctrl)
    gp = sorted({p.number for p in _gnd_pins(b, ctrl)}, key=_natkey)
    out = []
    for kind, rail, swn in (('buck', rin, swnets[0]), ('boost', rout, swnets[1])):
        comp = [x for x in _consumers(b, rail, exclude={ctrl, L})]
        caps, cp = _caps_with_p(b, rail, gnd, ctrl, comp)
        hf = caps[0] if caps else None
        loop = ([[hf, b.cap_pad(hf, rail)]] if hf else []) + [[ctrl, b.pads(ctrl, rail)], [ctrl, gp]] + \
               ([[hf, b.cap_pad(hf, gnd)]] if hf else [])
        evs = [ev('topology', f"both ends of {L} are switch nodes of {ctrl} (4-switch buck-boost)", STRONG),
               ev('pinfunction', f"{kind} side: {ctrl} pins on '{b.short(rail)}'", MODERATE)]
        if not caps:
            evs.append(ev('topology', 'no capacitor on that rail', -2.0))
        out.append(_struct('commutation_cell', f"cell:{kind}:{ctrl}", evs, conf_cap=0.9, prior=-0.5,
                           **{'class': kind, 'loop': loop, 'rail': rail, 'sw': swn, 'gnd': gnd,
                              'excite': _excite(b, ctrl, L, b.volts(rail), kind), 'controller': ctrl, 'inductor': L,
                              'caps': caps, 'caps_p': cp, 'topology': 'buck_boost_4switch', 'integrated_switches': True}))
    return out


def _half_bridge_leg(b: _B, swn, d):
    hi = [q for q in d.get('high', [])]
    lo = [q for q in d.get('low', [])]
    if not hi or not lo:
        return None
    hs, ls = hi[0], lo[0]
    _, rail = fet_terminals(b, hs, swn)
    _, ret = fet_terminals(b, ls, swn)
    if rail is None or ret is None:
        return None
    gnd = ret if ret in b.g else None
    shunt = None
    if gnd is None:
        for p in b.nl.pins(ret):
            if b.k(p.ref) == 'resistor' and (V.resistance(b.nl.parts[p.ref].value) or 1) <= 0.2:
                o2 = b.nl.other_net(b.nl.parts[p.ref], ret)
                if o2 in b.g:
                    gnd, shunt = o2, p.ref
    gnd = gnd or b.r.gnd
    evs = list(d['evidence'])
    comp = _consumers(b, rail)
    caps, cp = _caps_with_p(b, rail, gnd, hs, [c for c in comp])
    hf = caps[0] if caps else None
    if not caps:
        evs.append(ev('topology', f"no bus capacitor on '{b.short(rail)}'", -2.0))
    loop = ([[hf, b.cap_pad(hf, rail)]] if hf else []) + [[hs, b.pad_sel(hs, rail)], [hs, b.pad_sel(hs, swn)],
                                                         [ls, b.pad_sel(ls, swn)], [ls, b.pad_sel(ls, ret)]]
    if shunt:
        loop += [[shunt, b.pad_sel(shunt, ret)], [shunt, b.pad_sel(shunt, gnd)]]
    if hf:
        loop.append([hf, b.cap_pad(hf, gnd)])
    drv = None
    gate, _ = fet_terminals(b, hs, swn)
    if gate:
        cand = [p.ref for p in b.nl.pins(gate) if b.k(p.ref) in ('ic', 'module')]
        for p in b.nl.pins(gate):
            if b.k(p.ref) == 'resistor':
                o = b.nl.other_net(b.nl.parts[p.ref], gate)
                cand += [x.ref for x in b.nl.pins(o) if b.k(x.ref) in ('ic', 'module')] if o else []
        drv = cand[0] if cand else None
    exc = _excite(b, drv, None, b.volts(rail), 'half_bridge')
    return _struct('commutation_cell', f"cell:half_bridge:{hs}+{ls}", evs, conf_cap=b.r.nets[swn].confidence, prior=-0.5,
                   **{'class': 'half_bridge', 'loop': loop, 'rail': rail, 'sw': swn, 'gnd': gnd, 'excite': exc,
                      'controller': drv, 'switches': {'high': hs, 'low': ls}, 'shunt': shunt, 'caps': caps, 'caps_p': cp,
                      'integrated_switches': False})


def _integrated_bridge(b: _B, ic, outs):
    part = b.nl.parts[ic]
    sup = [p for p in part.active_pins() if p.net not in b.g and p.net not in outs and
           re.match(r'^(VM\w*|VMOT\w*|VBB\w*|PVDD\w*|VS\d?|VCC|VIN|PVIN\w*|VBAT|V\+|VDD|AVDD|VPWR)$', p.fn)]
    sup = [p for p in sup if b.r.caps_to.get(p.net)]
    if not sup:
        return None
    # the supply with the largest capacitance is the bridge bus
    def bus_rank(p):
        tot = 0.0
        for c in b.caps_on(p.net):
            f = cap_class(b.nl.parts[c])[1]
            tot += f or 1e-7
        return (re.match(r'^(VM|VMOT|VBB|PVDD)', p.fn) is not None, tot)
    rail = max(sup, key=bus_rank).net
    gnd = _cell_ground(b, ic)
    gp = sorted({p.number for p in _gnd_pins(b, ic)}, key=_natkey)
    comp = [x for x in _consumers(b, rail) if x != ic]
    caps, cp = _caps_with_p(b, rail, gnd, ic, comp)
    hf = caps[0] if caps else None
    evs = [ev('pinfunction', f"{ic} ({part.value}) bridge outputs on {len(outs)} net(s)", STRONG),
           ev('pinfunction', f"supply pin(s) on '{b.short(rail)}'", MODERATE)]
    loop = ([[hf, b.cap_pad(hf, rail)]] if hf else []) + [[ic, b.pads(ic, rail)], [ic, gp]] + ([[hf, b.cap_pad(hf, gnd)]] if hf else [])
    shunts = []
    for o in outs:
        for p in b.nl.pins(o):
            if b.k(p.ref) == 'resistor' and b.r.parts[p.ref].role == 'shunt':
                shunts.append(p.ref)
    return _struct('commutation_cell', f"cell:half_bridge:{ic}", evs, conf_cap=0.95, prior=-0.5,
                   **{'class': 'half_bridge', 'loop': loop, 'rail': rail, 'sw': outs[0], 'sw_nets': outs, 'gnd': gnd,
                      'excite': _excite(b, ic, None, b.volts(rail), 'half_bridge'), 'controller': ic, 'caps': caps, 'caps_p': cp,
                      'integrated_switches': True, 'phase_shunts': sorted(set(shunts), key=_refkey),
                      'bridge': {'legs': len(outs), 'type': 'integrated', 'sw_nets': outs}})


def _module_cell(b: _B, ref):
    part = b.nl.parts[ref]
    if re.search(r'A05|A12|B05|URB|MORNSUN|RAC|IRM|TMR|TEN|isolat', part.text(), re.I):
        return None             # isolated module: no exposed commutation loop
    vin = _vin_pins(b, ref, set())
    if not vin:
        return None
    rail = vin[0].net
    gnd = _cell_ground(b, ref)
    caps, cp = _caps_with_p(b, rail, gnd, ref, [x for x in _consumers(b, rail) if x != ref])
    if not caps:
        return None
    hf = caps[0]
    gp = sorted({p.number for p in _gnd_pins(b, ref)}, key=_natkey)
    loop = [[hf, b.cap_pad(hf, rail)], [ref, [p.number for p in vin if p.net == rail]], [ref, gp], [hf, b.cap_pad(hf, gnd)]]
    evs = [ev('table', f"regulator module '{part.value}' (inductor inside)", MODERATE),
           ev('pinfunction', f"input pin {vin[0].label}", MODERATE)]
    return _struct('commutation_cell', f"cell:buck:{ref}", evs, conf_cap=0.85, prior=-0.5,
                   **{'class': 'buck', 'loop': loop, 'rail': rail, 'sw': None, 'gnd': gnd,
                      'excite': _excite(b, ref, None, b.volts(rail), 'buck'), 'controller': ref, 'caps': caps, 'caps_p': cp,
                      'integrated_switches': True, 'integrated_inductor': True})


# =============================================================================== decoupling
def _power_pins(b: _B, ref):
    """Pins that draw from a rail (power_in or supply-named, on a rail or a capacitor-decoupled net)."""
    part = b.nl.parts[ref]
    sub = b.sub(ref)
    out = []
    for p in part.active_pins():
        n = p.net
        if n in b.g or n in b.r.switch_nodes:
            continue
        on_rail = n in b.r.rails or bool(b.r.caps_to.get(n))
        if not on_rail:
            continue
        if p.ptype == 'power_in' or PWR_PIN.match(p.fn) or IN_PIN.match(p.fn):
            func = 'load'
            if sub in REGULATOR_SUBS and (IN_PIN.match(p.fn) or re.match(r'^P?VIN', p.fn)):
                func = 'regulator_input'
            out.append((p, func))
        elif p.ptype == 'power_out' or OUT_PIN.match(p.fn) or re.match(r'^(VCAP\w*|VREG\w*|VDDCORE|VCORE|DCPL\w*|BYP\w*|VREFOUT|REFOUT|'
                                                                          r'VDD_?CORE|LDO\w*|VREF)$', p.fn):
            if sub in REGULATOR_SUBS or b.k(ref) in ('ic', 'module'):
                src = sub in REGULATOR_SUBS + ('load_switch',) and (OUT_PIN.match(p.fn) or p.ptype == 'power_out')
                func = 'regulator_output' if src else 'bypass'
                out.append((p, func))
    return out


RANK_W = 0.5        # weight of the schematic rank-order term in capacitor ownership (ablated in the eval)


def decaps(b: _B, cells) -> list:
    """Decoupling per (IC, rail, function). Capacitors on a rail shared by several ICs are split by a
    greedy assignment with quotas (one per power pin), scored by pin count, schematic sheet,
    reference block, capacitor class and schematic rank order; `caps_p` is the softmax of the same
    scores (ownership probability)."""
    in_cell = set()
    for c in cells:
        if c.get('controller'):
            in_cell.add((c['controller'], c['rail']))
    groups = {}         # (ref, rail, function) -> dict
    for ref, part in b.nl.parts.items():
        if b.k(ref) not in LOAD_KINDS or part.dnp:
            continue
        for p, func in _power_pins(b, ref):
            if (ref, p.net) in in_cell and func == 'regulator_input':
                continue
            key = (ref, p.net, func)
            g = groups.setdefault(key, {'ref': ref, 'rail': p.net, 'function': func, 'pins': []})
            if p.number not in g['pins']:
                g['pins'].append(p.number)
    by_rail = defaultdict(list)
    for key, g in groups.items():
        by_rail[g['rail']].append(g)
    out = []
    b.uncovered = []
    for rail, gs in by_rail.items():
        gs.sort(key=lambda g: (_refkey(g['ref']), g['function']))
        caps = sorted(b.caps_on(rail), key=_refkey)
        if not caps:
            b.uncovered += [(g['ref'], rail, len(g['pins'])) for g in gs if g['function'] == 'load']
            continue
        ncap, ng = len(caps), len(gs)
        cls = {c: cap_class(b.nl.parts[c])[0] for c in caps}
        S = {}
        for i, c in enumerate(caps):
            rc = i / (ncap - 1) if ncap > 1 else 0.5
            for j, g in enumerate(gs):
                rg = j / (ng - 1) if ng > 1 else 0.5
                v = math.log(1 + len(g['pins'])) + _affinity(b, c, g['ref'])
                if g['function'] == 'regulator_output':
                    v += 1.0 if cls[c] in ('bulk', 'mid') else 0.0
                elif g['function'] == 'bypass':
                    v += 0.5 if cls[c] in ('mid', 'bulk') else 0.0
                elif g['function'] == 'load':
                    v += 0.3 if cls[c] == 'hf' else 0.0
                if ng > 1:
                    v += RANK_W * (1.0 - abs(rc - rg))
                S[(c, j)] = v
        quota = [len(g['pins']) if g['function'] == 'load' else 1 for g in gs]
        count = [0] * ng
        owner = {}
        for v, c, j in sorted(((v, c, j) for (c, j), v in S.items()), key=lambda t: (-t[0], _refkey(t[1]), t[2])):
            if c in owner or count[j] >= quota[j]:
                continue
            owner[c] = j
            count[j] += 1
        for c in caps:
            if c not in owner:
                owner[c] = max(range(ng), key=lambda j: (S[(c, j)], -j))
        pmap = {}
        for c in caps:
            mx = max(S[(c, j)] for j in range(ng))
            z = [math.exp(S[(c, j)] - mx) for j in range(ng)]
            tz = sum(z)
            for j in range(ng):
                pmap[(c, j)] = round(z[j] / tz, 3)
        n_pins = sum(len(g['pins']) for g in gs)
        for j, g in enumerate(gs):
            mine = [c for c in caps if owner[c] == j]
            if not mine:
                if g['function'] == 'load':
                    b.uncovered.append((g['ref'], rail, len(g['pins'])))
                continue
            ref = g['ref']
            gnd = _decap_ground(b, ref, rail)
            gpins = sorted({p.number for p in b.nl.parts[ref].active_pins() if p.net == gnd}, key=_natkey)
            hf = [c for c in mine if cls[c] in ('hf', 'mid')]
            bulk = [c for c in mine if c not in hf]
            pins = sorted(g['pins'], key=_natkey)
            pin_caps = {pn: [hf[i % len(hf)]] for i, pn in enumerate(pins)} if hf else {}
            cp = {c: pmap[(c, j)] for c in mine}
            evs = [ev('topology', f"{len(pins)} power pin(s) of {ref} on '{b.short(rail)}'", MODERATE)]
            if ng == 1:
                evs.append(ev('topology', f"only consumer on the rail: all {ncap} capacitor(s) to ground serve it", STRONG))
            else:
                mp = sum(cp.values()) / len(cp)
                evs.append(ev('count', f"{ng} consumers share the rail ({n_pins} power pins, {ncap} caps); mean ownership {mp:.2f}",
                              math.log(max(mp, 0.05) / max(1 - mp, 0.05))))
                if _multi_sheet(b) and b.nl.parts[ref].sheet:
                    same = [c for c in mine if b.nl.parts[c].sheet == b.nl.parts[ref].sheet]
                    if same:
                        evs.append(ev('sheet', f"{len(same)} of the caps on {ref}'s schematic sheet '{b.nl.parts[ref].sheet}'", WEAK))
            if len(hf) >= len(pins):
                evs.append(ev('count', f"{len(hf)} HF caps for {len(pins)} pins", WEAK))
            conf_cap = min(b.r.nets[rail].confidence if rail in b.r.nets else 0.6, 0.97)
            out.append(_struct('decap', f"decap:{ref}:{b.short(rail)}" + ('' if g['function'] == 'load' else f":{g['function']}"), evs,
                               conf_cap=conf_cap, prior=0.0,
                               ic=ref, power_pins=pins, ground_pins=gpins, rail=rail, ground=gnd, caps=mine,
                               caps_p=cp, hf_caps=hf, bulk_caps=bulk, pin_caps=pin_caps, function=g['function'],
                               shared_by=ng))
    return out


def _decap_ground(b: _B, ref, rail):
    part = b.nl.parts[ref]
    gnds = defaultdict(int)
    for p in part.active_pins():
        if p.net in b.g:
            gnds[p.net] += 1
    if not gnds:
        cap_g = defaultdict(int)
        for c, gn in b.r.caps_to.get(rail, []):
            cap_g[gn] += 1
        return max(cap_g, key=cap_g.get) if cap_g else b.r.gnd
    if len(gnds) > 1 and re.search(r'A(VDD|VCC)|VDDA|VCCA|VREF|ANA', b.short(rail)):
        ag = [n for n in gnds if b.r.nets[n].subrole == 'analog_ground']
        if ag:
            return ag[0]
    cap_g = defaultdict(int)
    for c, gn in b.r.caps_to.get(rail, []):
        cap_g[gn] += 1
    return max(gnds, key=lambda n: (cap_g.get(n, 0), gnds[n]))


# =============================================================================== crystals and oscillators
XIN_FN = re.compile(r'(XIN|X_?IN|^XI$|^X1$|OSC_?IN|OSC\d?_?IN|OSCI$|XTAL_?IN|XTAL1|XTALI|XTAL_?P|HSE_?IN|LSE_?IN|OSC32_?IN|CLKIN|EXTAL|XC1|XT1|XA|PH0|PC14|XTAL$)')
XOUT_FN = re.compile(r'(XOUT|X_?OUT|^XO$|^X2$|OSC_?OUT|OSC\d?_?OUT|OSCO$|XTAL_?OUT|XTAL2|XTALO|XTAL_?N|HSE_?OUT|LSE_?OUT|OSC32_?OUT|XTAL$|XC2|XT2|XB|PH1|PC15)')


def crystals(b: _B) -> list:
    out = []
    for ref, pr in sorted(b.r.parts.items(), key=lambda t: _refkey(t[0])):
        if pr.kind != 'crystal' or b.nl.parts[ref].dnp:
            continue
        part = b.nl.parts[ref]
        xn = sorted({p.net for p in part.active_pins() if p.net not in b.g}, key=str)
        if len(xn) < 2:
            continue
        xn = xn[:2] if len(xn) == 2 else xn
        evs = [ev('topology', f"crystal {ref} ({part.value}) between '{b.short(xn[0])}' and '{b.short(xn[1])}'", MODERATE)]
        side = {}
        series = {}
        for n in xn:
            ics = [p for p in b.nl.pins(n) if b.k(p.ref) in ('ic', 'module')]
            if ics:
                side[n] = (n, ics)
                continue
            for p in b.nl.pins(n):
                if b.k(p.ref) == 'resistor':
                    rp = b.nl.parts[p.ref]
                    o = b.nl.other_net(rp, n)
                    ohm = V.resistance(rp.value)
                    if o and o not in xn and o not in b.g and (ohm is None or ohm <= 10e3):
                        ics2 = [x for x in b.nl.pins(o) if b.k(x.ref) in ('ic', 'module')]
                        if ics2:
                            side[n] = (o, ics2)
                            series[n] = p.ref
        common = None
        if len(side) >= 2:
            refs = [set(x.ref for x in v[1]) for v in side.values()]
            inter = set.intersection(*refs)
            if inter:
                common = sorted(inter, key=_refkey)[0]
        if common is None:
            cand = [x.ref for v in side.values() for x in v[1]]
            common = cand[0] if cand else None
            if common:
                evs.append(ev('topology', f"only one crystal terminal reaches {common}", -1.0))
        if common is None:
            evs.append(ev('topology', 'no IC on the crystal nets', -2.0))
        xin = xout = None
        if common:
            pins = {n: [p for p in b.nl.parts[common].active_pins() if p.net == side[n][0]] for n in side if n in side}
            for n, ps in pins.items():
                for p in ps:
                    if XIN_FN.search(p.fn) and not XOUT_FN.search(p.fn):
                        xin = (n, p)
                    elif XOUT_FN.search(p.fn) and not XIN_FN.search(p.fn):
                        xout = (n, p)
            named = xin is not None or xout is not None
            if xin is None or xout is None:
                rest = [(n, ps[0]) for n, ps in pins.items() if ps and (not xin or n != xin[0]) and (not xout or n != xout[0])]
                for n, p in sorted(rest, key=lambda t: _natkey(t[1].number)):
                    if xin is None and (not series.get(n)):
                        xin = (n, p)
                    elif xout is None:
                        xout = (n, p)
                    elif xin is None:
                        xin = (n, p)
            if named:
                evs.append(ev('pinfunction', f"oscillator pins {', '.join(x[1].label for x in (xin, xout) if x)}", STRONG))
            elif xin and xout:
                evs.append(ev('pinfunction', 'IC pins on both crystal nets (unnamed: xin/xout order from pin numbers)', WEAK))
        loads = []
        for n in xn:
            for c in b.caps_on(n):
                loads.append(c)
            if series.get(n):
                far = side[n][0]
                loads += [c for c in b.caps_on(far) if c not in loads]
        if loads:
            vals = [cap_class(b.nl.parts[c])[1] for c in loads]
            evs.append(ev('topology', f"load capacitors {', '.join(loads)} ({', '.join(V.si(v, 'F') for v in vals)})", MODERATE))
        fb = [p.ref for p in b.nl.pins(xn[0]) if b.k(p.ref) == 'resistor' and set(b.nl.parts[p.ref].nets) == set(xn[:2])]
        f = V.frequency(part.value) or V.frequency(' '.join(str(v) for v in part.fields.values()))
        st = _struct('crystal', f"xtal:{ref}", evs, conf_cap=pr.kind_confidence, prior=0.0,
                     ic=common, xin=(xin[1].number if xin else None), xout=(xout[1].number if xout else None), crystal=ref,
                     load_caps=loads, f_Hz=f, nets=xn, series_r=[series[n] for n in series], feedback_r=fb,
                     xin_fn=(xin[1].function if xin else None), xout_fn=(xout[1].function if xout else None))
        if common and re.search(r'ESP32', b.nl.parts[common].text(), re.I):
            dmin = 2.0 if re.search(r'S3', b.nl.parts[common].text()) else 2.7
            st['budget'] = {'d_min': {'value': dmin, 'unit': 'mm', 'class': 'E5',
                                      'basis': 'Espressif hardware design guidelines, crystal distance from the chip (docs/topics/rules/crystals-clocks.md XTAL-DMIN)'}}
        out.append(st)
    return out


def oscillators(b: _B) -> list:
    out = []
    for ref, pr in sorted(b.r.parts.items(), key=lambda t: _refkey(t[0])):
        if pr.kind != 'oscillator':
            continue
        part = b.nl.parts[ref]
        outs = [p for p in part.active_pins() if p.net not in b.g and p.net not in b.r.rails and
                (re.match(r'^(OUT\w*|CLK\w*|OUTPUT|Q|FOUT|CLKOUT)$', p.fn) or (not p.fn or p.fn == p.number) and p.number == '3')]
        if not outs:
            continue
        o = outs[0]
        loads = []
        series = None
        for p in b.nl.pins(o.net):
            if p.ref != ref and b.k(p.ref) in ('ic', 'module'):
                loads.append([p.ref, p.number])
            elif b.k(p.ref) == 'resistor':
                rp = b.nl.parts[p.ref]
                far = b.nl.other_net(rp, o.net)
                if far and far not in b.g and (V.resistance(rp.value) or 0) <= 200:
                    series = p.ref
                    loads += [[x.ref, x.number] for x in b.nl.pins(far) if b.k(x.ref) in ('ic', 'module')]
        evs = [ev('topology', f"oscillator {ref} output {o.label} on '{b.short(o.net)}'", MODERATE)]
        if loads:
            evs.append(ev('topology', f"drives {', '.join(r for r, _ in loads[:3])}", MODERATE))
        f = V.frequency(part.value) or V.frequency(' '.join(str(v) for v in part.fields.values()))
        out.append(_struct('oscillator', f"osc:{ref}", evs, conf_cap=pr.kind_confidence, part=ref, out_net=o.net, out_pin=o.number,
                           loads=loads, series_r=series, f_Hz=f))
    return out


# =============================================================================== connector chains
PROTECT_SUBS = ('tvs', 'esd_array', 'zener')
EXTERNAL = {'usb': 'cable', 'power': 'cable', 'ethernet': 'cable', 'audio': 'cable', 'wire_to_board': 'cable', 'can': 'cable',
            'hdmi': 'cable', 'sfp': 'cable', 'header': 'cable', 'debug': 'cable', 'rf': 'antenna', 'board_to_board': None,
            'ffc_fpc': None, 'card': None}
SHIELD_FN = re.compile(r'^(SHIELD\w*|SH\d*|S\d|EH\d?|MH\d?|MP\d?|SHELL\w*|GND_?SHIELD|CASE|MOUNT\w*|FRAME|PE|EARTH)$')


def connector_chains(b: _B) -> list:
    out = []
    seen_shield = set()
    for ref, pr in sorted(b.r.parts.items(), key=lambda t: _refkey(t[0])):
        if pr.kind != 'connector':
            continue
        part = b.nl.parts[ref]
        ext = EXTERNAL.get(pr.subtype, 'cable')
        for p in sorted(part.active_pins(), key=lambda x: _natkey(x.number)):
            n = p.net
            if not n:
                continue
            is_shield = bool(SHIELD_FN.match(p.fn)) or (b.r.nets.get(n) and b.r.nets[n].subrole == 'chassis')
            if n in b.g and not is_shield:
                continue
            if is_shield:
                if (ref, n) in seen_shield:
                    continue
                seen_shield.add((ref, n))
                bond, kind_b, evs = _shield_bond(b, ref, p, n)
                out.append(_struct('connector_chain', f"chain:{ref}:{p.number}", evs, conf_cap=pr.kind_confidence, prior=0.5,
                                   connector=ref, pin=p.number, net=n, chain=[[ref, p.number]] + [[x, b.pad_sel(x, n)] for x in bond],
                                   protection=[x for x in bond if b.k(x) in ('diode', 'varistor')], external=ext,
                                   connector_type=pr.subtype, series=[], pin_kind='shield', bond=bond, shield_bond=kind_b))
                continue
            chain, prot, series_parts, evs = _walk_chain(b, ref, p, n)
            if len(chain) < 2 or (ext is None and not prot):
                continue
            out.append(_struct('connector_chain', f"chain:{ref}:{p.number}", evs, conf_cap=pr.kind_confidence, prior=0.5,
                               connector=ref, pin=p.number, net=n, chain=chain, protection=prot, external=ext,
                               connector_type=pr.subtype, series=series_parts, protected=bool(prot),
                               pin_kind='power' if n in b.r.rails else 'signal'))
    return out


def _shield_bond(b: _B, cref, pin, net):
    """How a connector shield reaches the board's ground: directly, through parts (R, C, bead, TVS), or not."""
    if net in b.g and b.r.nets[net].subrole != 'chassis':
        return [], 'direct_to_ground', [ev('topology', f"shield pin {pin.label} on ground '{b.short(net)}' (direct bond)", MODERATE)]
    bond = []
    for p in b.nl.pins(net):
        if p.ref == cref:
            continue
        part = b.nl.parts[p.ref]
        o = b.nl.other_net(part, net)
        if o in b.g and b.k(p.ref) in ('resistor', 'capacitor', 'ferrite', 'inductor', 'diode', 'varistor', 'jumper', 'net_tie'):
            bond.append(p.ref)
    kinds = sorted({b.k(x) for x in bond})
    kind_b = ('rc_to_ground' if {'resistor', 'capacitor'} <= set(kinds) else '+'.join(kinds) + '_to_ground') if bond else 'floating'
    return bond, kind_b, [ev('topology', f"shield pin {pin.label} on '{b.short(net)}' bonded {kind_b.replace('_', ' ')}", MODERATE)]


def _walk_chain(b: _B, cref, pin, net):
    chain = [[cref, pin.number]]
    prot, series_parts = [], []
    evs = [ev('topology', f"connector pin {pin.label} on '{b.short(net)}'", WEAK)]
    seen_nets = {net}
    cur = net
    for depth in range(4):
        nxt = None
        ic_pins = []
        for p in sorted(b.nl.pins(cur), key=lambda x: _refkey(x.ref)):
            if p.ref == cref:
                continue
            k = b.k(p.ref)
            sub = b.sub(p.ref)
            if (k == 'diode' and sub in PROTECT_SUBS) or k == 'varistor' or (k == 'diode' and _clamps(b, p.ref, cur)):
                if p.ref not in prot:
                    prot.append(p.ref)
                    chain.append([p.ref, p.number])
                    evs.append(ev('topology', f"{sub or k} {p.ref} on '{b.short(cur)}'", MODERATE))
            elif k in ('ic', 'module') and b.sub(p.ref) != 'esd_array':
                ic_pins.append(p)
        if ic_pins:
            ip = ic_pins[0]
            chain.append([ip.ref, ip.number])
            evs.append(ev('topology', f"reaches {ip.label}", WEAK))
            break
        for p in sorted(b.nl.pins(cur), key=lambda x: _refkey(x.ref)):
            k = b.k(p.ref)
            part = b.nl.parts[p.ref]
            if p.ref == cref or k not in ('resistor', 'ferrite', 'inductor', 'fuse', 'common_mode_choke', 'capacitor', 'diode', 'jumper', 'net_tie'):
                continue
            if k == 'diode' and (b.sub(p.ref) in PROTECT_SUBS or _clamps(b, p.ref, cur)):
                continue
            o = _through(b, p.ref, cur)
            if o is None or o in seen_nets or o in b.g:
                continue
            if k == 'resistor' and (V.resistance(part.value) or 0) > 10e3:
                continue           # a pull resistor, not a series element
            if k == 'capacitor' and not (b.r.nets.get(cur) and b.r.nets[cur].role == 'high_speed'):
                continue           # only AC-coupling capacitors on fast lines count as series parts
            chain += [[p.ref, p.number], [p.ref, b.pad_sel(p.ref, o)]]
            series_parts.append(p.ref)
            evs.append(ev('topology', f"series {k} {p.ref} to '{b.short(o)}'", WEAK))
            nxt = o
            break
        if nxt is None:
            break
        seen_nets.add(nxt)
        cur = nxt
    return chain, prot, series_parts, evs


def _clamps(b: _B, ref, net):
    """A plain diode from a signal net to a ground or rail acts as a clamp."""
    part = b.nl.parts[ref]
    o = b.nl.other_net(part, net)
    return o is not None and (o in b.g or o in b.r.rails) and b.sub(ref) in ('signal', 'schottky') and net not in b.r.rails


def _through(b: _B, ref, net):
    part = b.nl.parts[ref]
    if b.k(ref) == 'common_mode_choke':
        ps = [p for p in part.active_pins()]
        mine = [p for p in ps if p.net == net]
        if not mine:
            return None
        num = mine[0].number
        # windings 1-4/2-3 (KiCad L_CommonMode) unless numbering says 1-2/3-4
        pairs = {'1': '4', '4': '1', '2': '3', '3': '2'} if len(ps) == 4 else {}
        tgt = pairs.get(num)
        o = next((p.net for p in ps if p.number == tgt), None)
        return o
    return b.nl.other_net(part, net)


# =============================================================================== victims
def feedback_victims(b: _B) -> list:
    out = []
    for ref, pr in sorted(b.r.parts.items(), key=lambda t: _refkey(t[0])):
        if pr.kind not in ('ic', 'module'):
            continue
        part = b.nl.parts[ref]
        if pr.subtype not in REGULATOR_SUBS + ('led_driver', 'motor_driver', None) and not any(SW_PIN.match(p.fn) for p in part.pins):
            continue
        for p in part.active_pins():
            if not FB_PIN.match(p.fn) or p.net in b.g:
                continue
            f = p.net
            if f in b.r.rails and not re.search(r'FB', b.short(f)):
                continue      # fixed-output part sensing its rail directly
            top = bot = None
            for q in b.nl.pins(f):
                if b.k(q.ref) != 'resistor':
                    continue
                o = b.nl.other_net(b.nl.parts[q.ref], f)
                if o is None:
                    continue
                if o in b.g:
                    bot = (q.ref, o)
                elif top is None or o in b.r.rails:
                    top = (q.ref, o)
            if not top and not bot:
                continue
            evs = [ev('pinfunction', f"feedback pin {p.label} on '{b.short(f)}'", STRONG)]
            loop = [[ref, p.number]]
            div = {}
            if top:
                loop.insert(0, [top[0], b.pad_sel(top[0], f)])
                div['top'], div['sense_net'] = top[0], top[1]
                div['r_top_ohm'] = V.resistance(b.nl.parts[top[0]].value)
            if bot:
                loop.append([bot[0], b.pad_sel(bot[0], f)])
                div['bottom'] = bot[0]
                div['r_bot_ohm'] = V.resistance(b.nl.parts[bot[0]].value)
            if top and bot:
                evs.append(ev('topology', f"divider {top[0]} (to '{b.short(top[1])}') / {bot[0]} (to ground)", STRONG))
                rt, rb = div['r_top_ohm'], div['r_bot_ohm']
                if rt and rb:
                    ratio = 1 + rt / rb
                    div['ratio'] = round(ratio, 4)
                    pat, vals = _table(part.text(), [(p_, v_) for p_, v_ in VREF_TABLE])
                    vrail = b.volts(top[1])
                    if vals:
                        div['vref_V'] = vals[0]
                        div['vout_implied_V'] = round(vals[0] * ratio, 3)
                        if vrail and abs(vals[0] * ratio - abs(vrail)) <= 0.06 * abs(vrail):
                            evs.append(ev('derived', f"Vref {vals[0]} V x {ratio:.3f} = {vals[0] * ratio:.2f} V matches '{b.short(top[1])}'", MODERATE))
                    elif vrail:
                        for vr in (0.5, 0.6, 0.765, 0.8, 0.9, 1.0, 1.21, 1.23, 1.25):
                            if abs(vr * ratio - abs(vrail)) <= 0.04 * abs(vrail):
                                div['vref_V'] = vr
                                div['vout_implied_V'] = round(vr * ratio, 3)
                                evs.append(ev('derived', f"a common Vref {vr} V x {ratio:.3f} matches '{b.short(top[1])}' ({vrail} V)", WEAK))
                                break
            cff = [q.ref for q in b.nl.pins(f) if b.k(q.ref) == 'capacitor' and top and top[1] in b.nl.parts[q.ref].nets]
            if cff:
                loop.append([cff[0], b.pad_sel(cff[0], f)])
                div['feedforward_cap'] = cff[0]
            out.append(_struct('victim', f"victim:feedback:{ref}:{p.number}", evs, conf_cap=0.95, prior=0.0,
                               **{'class': 'feedback', 'loop': loop, 'nets': [f], 'ic': ref, 'fb_pin': p.number, 'divider': div}))
    return out


def sense_victims(b: _B) -> list:
    out = []
    for ref, pr in sorted(b.r.parts.items(), key=lambda t: _refkey(t[0])):
        if pr.role != 'shunt':
            continue
        part = b.nl.parts[ref]
        act = part.active_pins()
        nets = sorted({p.net for p in act}, key=str)
        four = len(nets) >= 3 and len(act) >= 4
        if len(nets) < 2:
            continue
        if four:
            # Kelvin pads: the two nets carrying fewest pins elsewhere are the sense nets
            cnt = sorted(nets, key=lambda n: len(b.nl.pins(n)))
            sense_nets, power_nets = cnt[:2], cnt[2:]
        else:
            sense_nets, power_nets = nets[:2], nets[:2]
        a, c = sense_nets[0], sense_nets[1]
        # amplifier: an IC with pins on both sense nets, directly or through filter resistors (<= 1 kohm)
        reach = {}
        filt = []
        for n in (a, c):
            reach[n] = {(p.ref, p.number) for p in b.nl.pins(n) if b.k(p.ref) in ('ic', 'module')}
            for p in b.nl.pins(n):
                if b.k(p.ref) == 'resistor' and p.ref != ref:
                    rp = b.nl.parts[p.ref]
                    o = b.nl.other_net(rp, n)
                    ohm = V.resistance(rp.value)
                    if o and o not in b.g and (ohm is not None and ohm <= 1e3):
                        hits = {(x.ref, x.number) for x in b.nl.pins(o) if b.k(x.ref) in ('ic', 'module')}
                        if hits:
                            reach[n] |= hits
                            filt.append(p.ref)
        amps = {r for r, _ in reach[a]} & {r for r, _ in reach[c]}
        evs = [ev('value', f"shunt {ref} ({part.value}, {V.si(pr.attrs.get('ohms'), 'Ω')})", STRONG)]
        if not amps:
            evs.append(ev('topology', 'no IC reads both sides', -1.0))
            amp = None
        else:
            amp = sorted(amps, key=lambda r: (b.sub(r) != 'current_sense', _refkey(r)))[0]
            evs.append(ev('topology', f"{amp} ({b.nl.parts[amp].value}) reads both sides", STRONG))
        loop = [[ref, b.pad_sel(ref, a)]]
        if amp:
            pa = sorted(x[1] for x in reach[a] if x[0] == amp)
            pc = sorted(x[1] for x in reach[c] if x[0] == amp)
            loop += [[amp, pa[0]], [amp, pc[0]]]
        loop.append([ref, b.pad_sel(ref, c)])
        low_side = any(n in b.g for n in power_nets)
        kelvin = 'four_terminal' if four else 'pad_inner_edge'
        if low_side and not four:
            evs.append(ev('topology', 'low-side shunt: the amplifier ground side must tap the shunt pad, not the plane', WEAK))
        out.append(_struct('victim', f"victim:sense:{ref}", evs, conf_cap=pr.confidence, prior=0.0,
                           **{'class': 'sense', 'loop': loop, 'nets': sense_nets, 'shunt': ref, 'ohms': pr.attrs.get('ohms'),
                              'amp': amp, 'kelvin': kelvin, 'filter': sorted(set(filt), key=_refkey), 'low_side': low_side,
                              'power_nets': power_nets}))
    return out


def analog_victims(b: _B, taken_nets: set) -> list:
    out = []
    for net, nr in sorted(b.r.nets.items()):
        if net in taken_nets:
            continue
        conf = nr.confidence if nr.role == 'analog' else nr.tags.get('analog', 0.0)
        if conf < 0.5 or (nr.role == 'clock' and nr.subrole == 'xtal'):
            continue
        sub = nr.subrole if nr.role == 'analog' else 'analog'
        cls = 'reference' if sub == 'reference' else 'feedback' if sub == 'feedback' else 'sense' if sub == 'sense' else 'analog'
        pins = [[p.ref, p.number] for p in b.nl.pins(net) if b.k(p.ref) in ('ic', 'module')]
        evs = list(nr.evidence)[:4]
        out.append(_struct('victim', f"victim:{cls}:{b.short(net)}", evs, conf_cap=conf, prior=0.0,
                           **{'class': cls, 'nets': [net], 'subclass': sub, 'ic_pins': pins}))
    return out


# =============================================================================== antennas
RF_PASS = ('capacitor', 'inductor', 'resistor', 'ferrite')


def antennas(b: _B) -> list:
    out = []
    for ref, pr in sorted(b.r.parts.items(), key=lambda t: _refkey(t[0])):
        part = b.nl.parts[ref]
        is_ant = pr.kind == 'antenna'
        is_rfc = pr.kind == 'connector' and pr.subtype == 'rf'
        is_mod = pr.kind in ('module', 'ic') and re.search(r'WROOM|WROVER|MINI-1|C3-MINI|SUPERMINI|NORA-B1|BL54L|XBEE|XB24|ESP-\d\d|'
                                                            r'SC14CVMDECT|Pico\s*W|PicoW|XIAO.*(ESP32|nRF)|nRF52\d+-\w*module', part.text(), re.I)
        if not (is_ant or is_rfc or is_mod):
            continue
        evs = []
        feed = []
        match = []
        f = None
        if is_mod and not is_ant and not is_rfc:
            ant_pins = [p for p in part.active_pins() if re.search(r'(^|[^A-Z])(ANT|RF)', p.fn)]
            if ant_pins:
                continue     # module with an antenna pin: its antenna part or connector carries the structure
            evs.append(ev('table', f"module '{part.value}' with an integrated antenna", MODERATE))
            f = 2.45e9
            out.append(_struct('antenna', f"ant:{ref}", evs, conf_cap=pr.kind_confidence, part=ref, feed=[], f_Hz=f, integrated=True,
                               external=None))
            continue
        sig = [p for p in part.active_pins() if p.net not in b.g]
        if not sig:
            continue
        start = sig[0]
        feed = [[ref, start.number]]
        cur = start.net
        seen = {cur}
        ic_pin = None
        for depth in range(6):
            nxt = None
            for p in b.nl.pins(cur):
                if p.ref == ref:
                    continue
                k = b.k(p.ref)
                if k in ('ic', 'module'):
                    ic_pin = p
                    break
            if ic_pin:
                break
            for p in sorted(b.nl.pins(cur), key=lambda x: _refkey(x.ref)):
                if p.ref == ref or p.ref in [x[0] for x in feed]:
                    continue
                k = b.k(p.ref)
                if k not in RF_PASS:
                    continue
                o = b.nl.other_net(b.nl.parts[p.ref], cur)
                if o is None:
                    continue
                if o in b.g:
                    match.append(p.ref)
                    feed.append([p.ref, p.number])
                    continue
                if o in seen:
                    continue
                if nxt is None:
                    feed += [[p.ref, p.number], [p.ref, b.pad_sel(p.ref, o)]]
                    match.append(p.ref)
                    nxt = o
            if nxt is None:
                break
            seen.add(nxt)
            cur = nxt
        if ic_pin:
            feed.append([ic_pin.ref, ic_pin.number])
            evs.append(ev('topology', f"feed reaches {ic_pin.label}", STRONG))
            t = b.nl.parts[ic_pin.ref].text()
            if re.search(r'LORA|RFM9|SX127|SX126|868|915', t, re.I):
                f = 868e6 if '868' in t else 915e6
            elif re.search(r'GPS|GNSS|L1', t):
                f = 1.575e9
            elif re.search(r'ESP|nRF|BLE|WiFi|2\.4|BL54|NORA|CC25|CC26', t, re.I):
                f = 2.45e9
        else:
            evs.append(ev('topology', 'feed does not reach an IC', -1.0))
        if re.search(r'2450|2\.4', part.text()):
            f = f or 2.45e9
        evs.insert(0, ev('lib_id' if is_rfc else 'value', f"{'RF connector' if is_rfc else 'antenna'} {ref} ({part.value})", STRONG))
        if match:
            evs.append(ev('topology', f"matching parts {', '.join(match[:5])}", WEAK))
        out.append(_struct('antenna', f"ant:{ref}", evs, conf_cap=pr.kind_confidence, part=ref, feed=feed, f_Hz=f, match=match,
                           integrated=False, external='antenna' if is_rfc else None))
    return out


# =============================================================================== heat
def heat(b: _B, cells) -> tuple[list, dict]:
    """Heat sources with an E5 power estimate, and the per-part P_W map."""
    pw = {}
    out = []
    cell_by_ctrl = {c.get('controller'): c for c in cells if c.get('controller')}
    for ref, pr in b.r.parts.items():
        part = b.nl.parts[ref]
        P = basis = None
        if pr.kind == 'ic' and pr.subtype == 'regulator_linear':
            vin = vout = None
            for p in part.active_pins():
                if IN_PIN.match(p.fn) and b.volts(p.net):
                    vin = b.volts(p.net)
                if (OUT_PIN.match(p.fn) or p.ptype == 'power_out') and b.volts(p.net):
                    vout = b.volts(p.net)
            vo = pr.attrs.get('vout', {}).get('value') if pr.attrs.get('vout') else None
            vout = vout or vo
            if vin and vout and vin > vout:
                pk = part.lib_id
                I_ = 0.8 if re.search(r'TO-?220|TO-?263|D2PAK', pk) else 0.5 if re.search(r'SOT-?223|TO-?252|DPAK', pk) else \
                    0.3 if re.search(r'SOT-?89|DFN|SON', pk) else 0.15
                P = round((vin - vout) * I_, 3)
                basis = f"(Vin {vin:g} - Vout {vout:g}) V x {I_:g} A, the load current assumed from the {part.package.text or 'package'} class"
        elif ref in cell_by_ctrl and cell_by_ctrl[ref]['class'] in ('buck', 'boost'):
            c = cell_by_ctrl[ref]
            ex = c['excite']
            vout = b.volts(c.get('vout') or '') if c.get('vout') else None
            if ex.get('I') and (vout or ex.get('V')):
                pout = abs(vout or ex['V']) * ex['I'] * (1 if vout else 0.5)
                P = round(pout * (1 - 0.88) / 0.88, 3)
                basis = f"conversion loss at 88% efficiency of {pout:.2f} W (I from {ex['basis'][0] if ex['basis'] else '?'})"
        elif ref in cell_by_ctrl and cell_by_ctrl[ref]['class'] == 'half_bridge':
            ex = cell_by_ctrl[ref]['excite']
            if ex.get('I'):
                P = round(min(3.0, 0.15 * ex['I'] ** 1.5), 3)
                basis = f"integrated bridge conduction and switching loss, class estimate at {ex['I']:g} A"
        elif pr.kind == 'ic' and pr.subtype == 'fpga':
            n = len(part.active_pins())
            P = 2.0 if n > 300 else 1.0 if n > 100 else 0.3
            basis = f"FPGA class estimate by pin count ({n})"
        elif pr.kind == 'ic' and pr.subtype == 'phy':
            P = 0.4
            basis = 'PHY/bridge class estimate'
        elif pr.kind in ('ic', 'module') and pr.subtype == 'mcu' and len(part.active_pins()) > 100:
            P = 0.5
            basis = 'large MCU/SoC class estimate'
        if P is not None and P > 0:
            pw[ref] = (P, basis)
            if P >= 0.1:
                out.append(_struct('heat_source', f"heat:{ref}", [ev('derived', basis, MODERATE)], conf_cap=0.6, prior=0.0,
                                   part=ref, P_W=P, P_W_belief={'value': P, 'unit': 'W', 'class': 'E5', 'basis': basis,
                                                                'interval': [round(P / 3, 3), round(P * 3, 3)]}))
    return out, pw


def thermal_victims(b: _B) -> list:
    out = []
    for ref, pr in sorted(b.r.parts.items(), key=lambda t: _refkey(t[0])):
        part = b.nl.parts[ref]
        cls = None
        if pr.kind == 'capacitor' and part.package.polarized and not re.search(r'Tantal|CP_Tantal', part.lib_id, re.I):
            cls, why = 'electrolytic', f"aluminium electrolytic body '{part.package.text}'"
        elif pr.kind in ('crystal', 'oscillator'):
            cls, why = 'crystal', f"{pr.kind} '{part.value}'"
        elif pr.kind == 'ic' and pr.subtype == 'reference':
            cls, why = 'reference', f"voltage reference '{part.value}'"
        elif pr.kind == 'thermistor' or (pr.kind in ('ic', 'module') and pr.subtype == 'sensor' and
                                          re.search(r'BME|BMP|SHT|HDC|Si70|TMP|MCP98|LM75|AT30TS|DS18|DHT|MAX318|MAX6675|temp|humid|press', part.text(), re.I)):
            cls, why = 'sensor', f"temperature/humidity/pressure sensing part '{part.value}'"
        elif pr.kind == 'battery':
            cls, why = 'battery', f"battery '{part.value}'"
        if cls:
            out.append(_struct('thermal_victim', f"tvictim:{ref}", [ev('derived', why, MODERATE)], conf_cap=pr.kind_confidence,
                               part=ref, **{'class': cls}))
    return out


# =============================================================================== entry
def find_structures(nl: Netlist, roles: Roles) -> dict:
    b = _B(nl, roles)
    cells = commutation_cells(b)
    st = {'commutation_cells': cells}
    st['decaps'] = decaps(b, cells)
    st['uncovered'] = [{'ic': r, 'rail': n, 'pins': k} for r, n, k in getattr(b, 'uncovered', [])]
    st['crystals'] = crystals(b)
    st['oscillators'] = oscillators(b)
    st['chains'] = connector_chains(b)
    fb = feedback_victims(b)
    se = sense_victims(b)
    taken = {n for v in fb + se for n in v.get('nets', [])}
    xv = []
    for x in st['crystals']:
        taken |= set(x['nets'])
        loop = ([[x['ic'], x['xin']]] if x['ic'] and x['xin'] else []) + [[x['crystal'], b.pads(x['crystal'], n)[0]] for n in x['nets'][:2]] + \
               ([[x['ic'], x['xout']]] if x['ic'] and x['xout'] else [])
        xv.append(_struct('victim', f"victim:crystal:{x['crystal']}", [ev('topology', f"crystal {x['crystal']} terminals (high impedance)", STRONG)],
                          conf_cap=x['confidence'], **{'class': 'crystal', 'nets': x['nets'][:2], 'loop': loop}))
    st['victims'] = fb + se + xv + analog_victims(b, taken)
    st['antennas'] = antennas(b)
    hs, pw = heat(b, cells)
    st['heat_sources'] = hs
    st['P_W'] = pw
    st['thermal_victims'] = thermal_victims(b)
    return st
