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
from .roles import (ANALOG_NET, ANALOG_PIN, BOOT_PIN, CP_PIN, EN_PIN, FB_PIN, IN_PIN, INT_OUT_PIN, OUT_PIN, PWR_PIN, SW_PIN, Roles, belief,
                    cap_class)

CTRL_PIN = re.compile(r'^(N?PG|PGOOD|POK|MODE\w*|SYNC\w*|SS\w*|TR|TRK|RT\w*|ILIM\w*|COMP|SEL\w*|CFG\w*|PS|FSW|FREQ|CTRL|'
                      r'DIS|N?SLEEP|N?FAULT|STAT\w*)$', re.I)
REGULATOR_SUBS = ('regulator_linear', 'regulator_switching', 'regulator_module', 'pmic', 'charger', 'charge_pump')
LOAD_KINDS = ('ic', 'module', 'oscillator', 'led', 'optocoupler', 'microphone', 'crystal')

# switching frequency (Hz) and rated output current (A) by part-number prefix: datasheet values,
# typical where the part is programmable (E5 in the brief, with the table as basis)
SWITCHER_TABLE = [
    (r'AP6320[35]', 1.1e6, 2.0), (r'AP6320[01]', 500e3, 2.0), (r'AP6330[35]', 1.1e6, 3.0), (r'AP6330[01]', 500e3, 3.0), (r'AP63357', 450e3, 3.5), (r'AP62300', 750e3, 3.0),
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

    def caps_between(self, a, b_):
        """Two-terminal capacitors from rail `a` to rail `b_` (split-supply decoupling, V+ to V-)."""
        if not hasattr(self, '_rr'):
            self._rr = defaultdict(list)
            for ref, part in self.nl.parts.items():
                t = self.nl.two_nets(part)
                if t and self.k(ref) == 'capacitor' and not part.dnp and t[0] in self.r.rails and t[1] in self.r.rails:
                    self._rr[frozenset(t)].append(ref)
        return sorted(self._rr.get(frozenset((a, b_)), []), key=_refkey)

    def cap_pad(self, cref, net):
        return self.pad_sel(cref, net)

    def supply_pads(self, ref, net):
        """The part's pads on a rail that carry the power current: control pins tied to the rail (EN, MODE,
        PG pull-ups, FB) are left out unless nothing else is there."""
        ps = [p for p in self.nl.parts[ref].pins_on(net) if not (EN_PIN.match(p.fn) or FB_PIN.match(p.fn) or CTRL_PIN.match(p.fn))]
        return sorted({p.number for p in ps}, key=_natkey) or self.pads(ref, net)

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
    for c in cells:
        _cell_members(b, c)
    return cells


def _cell_members(b: _B, c):
    """Second-step members of a cell: the bootstrap capacitor (directly or through a resistor), charge-pump
    capacitors of a bridge or gate driver, and RC snubbers on the switch node."""
    sws = c.get('sw_nets') or ([c['sw']] if c.get('sw') else [])
    ctrl = c.get('controller')
    boot, boot_r = None, None
    for swn in sws:
        boot, boot_r = _bootstrap(b, ctrl, swn)
        if boot:
            break
    c['bootstrap_cap'], c['bootstrap_r'] = boot, boot_r
    c['charge_pump_caps'] = _charge_pump_caps(b, ctrl, c.get('rail')) if ctrl else []
    sn = []
    for swn in sws:
        sn += [x for x in _snubbers(b, swn, c.get('gnd'), c.get('rail')) if x not in sn]
    c['snubbers'] = sn
    c.setdefault('series_shunt', [])


def _series_shunt(b: _B, ctrl, rail, avoid):
    """Low-ohm resistors from `rail` to a net that only the controller, the shunts and filter parts touch:
    the switch current enters the controller through them. -> (shunts, net, controller pins on it)."""
    found = defaultdict(list)
    for p in b.nl.pins(rail):
        if b.k(p.ref) != 'resistor' or len(b.nl.parts[p.ref].nets) != 2:
            continue
        part = b.nl.parts[p.ref]
        o = b.nl.other_net(part, rail)
        ohm = V.resistance(part.value)
        if o is None or o in avoid or o in b.g or o == rail:
            continue
        if (ohm is not None and 0 < ohm <= 0.2) or b.r.parts[p.ref].subtype == 'shunt':
            found[o].append(p.ref)
    for n, shunts in sorted(found.items()):
        cp = sorted({q.number for q in b.nl.pins(n) if q.ref == ctrl}, key=_natkey)
        others = {q.ref for q in b.nl.pins(n)} - set(shunts) - {ctrl}
        if cp and all(b.k(x) in ('capacitor', 'resistor', 'test_point') for x in others):
            return sorted(shunts, key=_refkey), n, cp
    return [], None, []


def _bootstrap(b: _B, ctrl, swn):
    """(capacitor, resistor) from the switch node to the controller's bootstrap pin (BST/BOOT/CB/HB/VB, or an
    unnamed pin), directly or through a resistor of 100 ohm or less (slowed turn-on)."""
    if not ctrl or swn not in b.nl.nets:
        return None, None
    pins = {}
    for p in b.nl.parts[ctrl].active_pins():
        pins.setdefault(p.net, []).append(p)

    def boot_pin(net):
        ps = pins.get(net) or []
        return any(BOOT_PIN.match(p.fn) or not p.fn or p.fn == p.number for p in ps) and \
            not any(PWR_PIN.match(p.fn) or FB_PIN.match(p.fn) for p in ps)
    for q in sorted(b.nl.pins(swn), key=lambda x: _refkey(x.ref)):
        if b.k(q.ref) != 'capacitor' or len(b.nl.parts[q.ref].nets) != 2:
            continue
        x = b.nl.other_net(b.nl.parts[q.ref], swn)
        if x is None or x in b.g or x in b.r.rails:
            continue
        if boot_pin(x):
            return q.ref, None
        for r in b.nl.pins(x):
            if b.k(r.ref) != 'resistor' or len(b.nl.parts[r.ref].nets) != 2:
                continue
            y = b.nl.other_net(b.nl.parts[r.ref], x)
            ohm = V.resistance(b.nl.parts[r.ref].value)
            if y and boot_pin(y) and ohm is not None and ohm <= 100:
                return q.ref, r.ref
    return None, None


def _charge_pump_caps(b: _B, ic, rail):
    """Capacitors on a driver's charge-pump pins: flying (pin to pin) and storage (VCP to the supply or ground)."""
    part = b.nl.parts[ic]
    cp_nets = {p.net for p in part.active_pins() if CP_PIN.match(p.fn)}
    ic_supply = {p.net for p in part.active_pins() if p.net in b.r.rails}
    out = []
    for n in sorted(cp_nets):
        for q in b.nl.pins(n):
            if b.k(q.ref) != 'capacitor' or q.ref in out or len(b.nl.parts[q.ref].nets) != 2:
                continue
            o = b.nl.other_net(b.nl.parts[q.ref], n)
            if o in cp_nets or o == rail or o in b.g or o in ic_supply:
                out.append(q.ref)
    return sorted(out, key=_refkey)


def _snubbers(b: _B, swn, gnd, rail):
    """RC snubbers from the switch node to ground or to the input rail: [resistor, capacitor] pairs whose
    middle net carries nothing else."""
    out = []
    for q in b.nl.pins(swn):
        k = b.k(q.ref)
        if k not in ('resistor', 'capacitor') or len(b.nl.parts[q.ref].nets) != 2:
            continue
        m = b.nl.other_net(b.nl.parts[q.ref], swn)
        if m is None or m in b.g or m in b.r.rails or m == swn:
            continue
        others = {x.ref for x in b.nl.pins(m)} - {q.ref}
        if len(others) != 1:
            continue
        x = next(iter(others))
        if {k, b.k(x)} != {'resistor', 'capacitor'} or len(b.nl.parts[x].nets) != 2:
            continue
        o = b.nl.other_net(b.nl.parts[x], m)
        if o in b.g or (rail and o == rail):
            out.append([q.ref, x] if k == 'resistor' else [x, q.ref])
    return out


def _vin_pins(b: _B, ic: str, exclude: set, suffix: str = '', token: str = ''):
    """Supply-input pins of a controller (VIN, PVIN, VCC, VDDSMPS, VREG_VIN ...) on non-ground nets not in
    `exclude`; pins sharing the switch pin's channel suffix or token (SMPS, VREG) first. Without a named
    input pin, the controller's pins on decoupled rails stand in (libraries without pin names)."""
    part = b.nl.parts[ic]
    named = re.compile(r'^P?VIN\w*|^VIN\d?$|^PVIN\w*|^VS$|^VCC$|^VM$|^VBAT$|^VSYS$|^AVIN$|^VDD_?SMPS|^VREG_?(VIN|IN)|^VIN_?SMPS|'
                       r'^VDD_?(DCDC|BUCK|REG)|^(DCDC|BUCK|SMPS)_?(VIN|IN|VDD)')
    pins = [p for p in part.active_pins() if p.net not in b.g and p.net not in exclude and (IN_PIN.match(p.fn) or named.match(p.fn))]
    if suffix:
        same = [p for p in pins if p.fn.endswith(suffix)]
        pins = same or pins
    if token:
        same = [p for p in pins if token in p.fn]
        pins = same or pins
    if not pins:
        # no named input: the controller's power_in pins on decoupled rails it does not itself feed
        pins = [p for p in part.active_pins() if p.net not in b.g and p.net not in exclude and p.net in b.r.rails
                and b.r.caps_to.get(p.net) and not FB_PIN.match(p.fn) and not EN_PIN.match(p.fn) and not _downstream_of(b, p.net, ic)]
        if any(b.r.sem(p) == 'supply' for p in pins):
            pins = [p for p in pins if b.r.sem(p) == 'supply']
    # rank: named PVIN/VIN first, then nets with capacitors
    pins.sort(key=lambda p: (not re.match(r'^P?VIN', p.fn), -len(b.r.caps_to.get(p.net, ())), _natkey(p.number)))
    return pins


def _downstream_of(b: _B, net, ic, depth=4) -> bool:
    """True when `net` is the far end of one of `ic`'s power inductors, or derives from one through series
    parts: the converter's own output, which cannot be its input. (A PMIC's VSYS output still feeds its bucks.)"""
    ic_nets = set(b.nl.parts[ic].nets)
    outs = {d_out for sw, d in b.r.switch_nodes.items() if sw in ic_nets
            for L in d.get('inductors', []) for d_out in [b.nl.other_net(b.nl.parts[L], sw)] if d_out}
    for _ in range(depth):
        if net in outs:
            return True
        nr = b.r.rails.get(net)
        src = (nr.attrs.get('source') if nr else None) or {}
        net = src.get('upstream') if src.get('kind') == 'derived' else None
        if not net:
            return False
    return False


def _gnd_pins(b: _B, ic: str, suffix: str = '', token: str = ''):
    part = b.nl.parts[ic]
    pins = [p for p in part.active_pins() if p.net in b.g]
    if token:
        tk = [p for p in pins if token in p.fn]
        if tk:
            return tk
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
        if b.k(p.ref) in LOAD_KINDS and b.r.sem(p) in ('supply', 'supply_out'):
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
    suffix = token = ''
    if sw_pins:
        m = re.search(r'(\d|[AB])$', sw_pins[0].fn)
        suffix = m.group(1) if m else ''
        mt = re.search(r'SMPS|VREG|DCDC|BUCK|BOOST', sw_pins[0].fn)
        token = mt.group(0) if mt else ''
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
    vin_pins = _vin_pins(b, ctrl, {swn, other}, suffix, token) if ctrl else []
    out_pins = [p for p in b.nl.parts[ctrl].active_pins() if OUT_PIN.match(p.fn) and p.net not in (swn,) and p.net not in b.g] if ctrl else []
    ctrl_in_on_other = ctrl and any(p.net == other and b.r.sem(p) == 'supply' and not SW_PIN.match(p.fn) for p in b.nl.parts[ctrl].active_pins())
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
    series_shunt = []
    if kind == 'buck':
        if hs and hs_rail != other:
            loop += [[hs, b.pad_sel(hs, rail)], [hs, b.pad_sel(hs, swn)]]
        elif ctrl:
            series_shunt, sn, sn_pins = _series_shunt(b, ctrl, rail, {swn, other})
            if series_shunt:
                # the switch current enters the controller through an input shunt (TX4138 ILIM, MC34063 Rsc)
                sh = series_shunt[0]
                loop += [[sh, b.pad_sel(sh, rail)], [sh, b.pad_sel(sh, sn)], [ctrl, sn_pins]]
                evs.append(ev('topology', f"input shunt {', '.join(series_shunt)} from '{b.short(rail)}' into {ctrl} "
                                          f"(pins {', '.join(sn_pins)}): inside the switch current path", MODERATE))
            else:
                loop.append([ctrl, [p.number for p in vin_pins if p.net == rail] or b.supply_pads(ctrl, rail)])
            if d_catch or ls:
                loop.append([ctrl, b.pads(ctrl, swn)])
        if ls:
            loop += [[ls, b.pad_sel(ls, swn)], [ls, b.pad_sel(ls, ls_ret)]]
        elif d_catch:
            loop += [[d_catch, b.pad_sel(d_catch, swn)], [d_catch, b.pad_sel(d_catch, gnd)]]
        elif ctrl:
            gp = _gnd_pins(b, ctrl, suffix, token)
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
            loop.append([ctrl, b.supply_pads(ctrl, rail)])
            loop.append([ctrl, sorted({p.number for p in _gnd_pins(b, ctrl, suffix)}, key=_natkey)])
    if hf:
        loop.append([hf, b.cap_pad(hf, gnd if gnd in b.nl.parts[hf].nets else next(iter(b.nl.parts[hf].nets - {rail})))])
    core = loop[1:-1] if hf else loop
    vin_net = rail if kind == 'buck' else other
    V_ = b.volts(rail)
    exc = _excite(b, ctrl, L, V_, kind)
    out_caps = _hf_order(b.nl, b.caps_on(out if kind == 'buck' else other))
    conf_cap = min(b.r.nets[swn].confidence, b.r.parts[L].kind_confidence + 0.2)
    cid = f"cell:{kind}:{ctrl or L}" + (f":{suffix}" if suffix else '')
    return _struct('commutation_cell', cid, evs, conf_cap=conf_cap, prior=-0.5,
                   **{'class': kind, 'loop': loop, 'rail': rail, 'sw': swn, 'gnd': gnd, 'excite': exc,
                      'controller': ctrl, 'inductor': L, 'caps': caps, 'caps_p': cp,
                      'switches': {'high': hs or (ctrl if kind == 'buck' else None), 'low': ls or d_catch or (ctrl if not d_boost else None),
                                   'rectifier': (d_boost[0] if d_boost else d_catch)},
                      'vin': vin_net, 'vout': out if kind == 'buck' else rail, 'output_caps': out_caps[:6] if kind == 'buck' else [],
                      'input_caps': out_caps[:6] if kind == 'boost' else [], 'series_shunt': series_shunt,
                      'integrated_switches': bool(ctrl and not hs and not ls),
                      'loop_core': core, 'cap_rail': rail, 'cap_gnd': gnd, 'anchor': ctrl or hs or L})


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
        loop = ([[hf, b.cap_pad(hf, rail)]] if hf else []) + [[ctrl, b.supply_pads(ctrl, rail)], [ctrl, gp]] + \
               ([[hf, b.cap_pad(hf, gnd)]] if hf else [])
        evs = [ev('topology', f"both ends of {L} are switch nodes of {ctrl} (4-switch buck-boost)", STRONG),
               ev('pinfunction', f"{kind} side: {ctrl} pins on '{b.short(rail)}'", MODERATE)]
        if not caps:
            evs.append(ev('topology', 'no capacitor on that rail', -2.0))
        out.append(_struct('commutation_cell', f"cell:{kind}:{ctrl}", evs, conf_cap=0.9, prior=-0.5,
                           **{'class': kind, 'loop': loop, 'rail': rail, 'sw': swn, 'gnd': gnd,
                              'excite': _excite(b, ctrl, L, b.volts(rail), kind), 'controller': ctrl, 'inductor': L,
                              'caps': caps, 'caps_p': cp, 'topology': 'buck_boost_4switch', 'integrated_switches': True,
                              'loop_core': [[ctrl, b.supply_pads(ctrl, rail)], [ctrl, gp]], 'cap_rail': rail, 'cap_gnd': gnd,
                              'anchor': ctrl}))
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
                      'integrated_switches': False, 'loop_core': loop[1:-1] if hf else loop, 'cap_rail': rail, 'cap_gnd': gnd,
                      'anchor': hs})


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
    loop = ([[hf, b.cap_pad(hf, rail)]] if hf else []) + [[ic, b.supply_pads(ic, rail)], [ic, gp]] + ([[hf, b.cap_pad(hf, gnd)]] if hf else [])
    shunts = []
    for o in outs:
        for p in b.nl.pins(o):
            if b.k(p.ref) == 'resistor' and b.r.parts[p.ref].role == 'shunt':
                shunts.append(p.ref)
    return _struct('commutation_cell', f"cell:half_bridge:{ic}", evs, conf_cap=0.95, prior=-0.5,
                   **{'class': 'half_bridge', 'loop': loop, 'rail': rail, 'sw': outs[0], 'sw_nets': outs, 'gnd': gnd,
                      'excite': _excite(b, ic, None, b.volts(rail), 'half_bridge'), 'controller': ic, 'caps': caps, 'caps_p': cp,
                      'integrated_switches': True, 'phase_shunts': sorted(set(shunts), key=_refkey),
                      'bridge': {'legs': len(outs), 'type': 'integrated', 'sw_nets': outs},
                      'loop_core': [[ic, b.supply_pads(ic, rail)], [ic, gp]], 'cap_rail': rail, 'cap_gnd': gnd, 'anchor': ic})


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
                      'integrated_switches': True, 'integrated_inductor': True,
                      'loop_core': loop[1:-1], 'cap_rail': rail, 'cap_gnd': gnd, 'anchor': ref})


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
        sem = b.r.sem(p)
        if sem == 'supply':
            func = 'load'
            if sub in REGULATOR_SUBS and (IN_PIN.match(p.fn) or re.match(r'^P?VIN', p.fn)):
                func = 'regulator_input'
                if {q.ref for q in b.nl.pins(n) if b.k(q.ref) != 'capacitor'} == {ref} and not re.match(r'^P?VIN', p.fn):
                    func = 'bypass'      # a converter's VCC/VDD bias pin on its own capacitor-only node (internal LDO)
            out.append((p, func))
        elif sem == 'supply_out' or re.match(r'^(VREFOUT|REFOUT|VREF)$', p.fn):
            if sub in REGULATOR_SUBS or b.k(ref) in ('ic', 'module'):
                src = sub in REGULATOR_SUBS + ('load_switch',) and (OUT_PIN.match(p.fn) or p.ptype == 'power_out' or sem == 'supply_out')
                func = 'regulator_output' if src else 'bypass'
                out.append((p, func))
    return out


RANK_W = 0.0        # weight of a linear rank-order term in capacitor ownership; 0 measured best (eval ablation)
TIE_ORDER = 'schematic'   # 'schematic': equal scores fill consumers in reference order with capacitors in
                          # reference order (block rank order); 'random': seeded shuffle (ablation)
CELL_BASE = 2.0     # commutation cells claim their rail's capacitors first
CELL_QUOTA = 2      # one HF commutation cap and one more
CELL_CLASS = 'count'   # 'count': cells prefer small ceramics (<= 1 uF) only when the loads' pins leave some spare
                       # (else the bulk ones, largest first); 'hf': always prefer them (ablation)
CONVERTER_OUT = True   # a buck's output (a boost's input) bulk capacitors (>= 10 uF) belong at its inductor
CELL_HF_SCARCE = -3.0  # a cell's score offset for a small ceramic when the loads need them all ('count' mode)
ENTRY_BULK = True      # polarized bulk capacitors (>= 10 uF) on a rail fed by a connector stay at the entry


def _decap_groups(b: _B, cells) -> list:
    """Power pins grouped per (IC, rail, function); a converter's pins on its cell's rail belong to the cell."""
    # the controller's pins that close a cell's loop belong to the cell; its other supply pins on the same
    # rail (an MCU's IOVDD beside its internal SMPS input) stay loads
    in_cell = defaultdict(set)
    for c in cells:
        if c.get('controller'):
            for t in c.get('loop_core') or []:
                if t[0] == c['controller']:
                    in_cell[(c['controller'], c['cap_rail'])].update(t[1] if isinstance(t[1], list) else [t[1]])
    groups = {}
    for ref, part in b.nl.parts.items():
        if b.k(ref) not in LOAD_KINDS or part.dnp:
            continue
        for p, func in _power_pins(b, ref):
            if p.number in in_cell.get((ref, p.net), ()) or (func in ('regulator_input', 'regulator_output') and (ref, p.net) in in_cell):
                continue           # the converter's own loop pins on its cell's rail are the cell (input or output side)
            g = groups.setdefault((ref, p.net, func), {'ref': ref, 'rail': p.net, 'function': func, 'pins': []})
            if p.number not in g['pins']:
                g['pins'].append(p.number)
    # split supplies: an IC with supply pins on two rails and capacitors straight across them (an op-amp's
    # V+ to V-) owns one of those capacitors; the higher rail is the 'rail', the lower one the return
    by_ic = defaultdict(dict)
    for (ref, rail, func), g in groups.items():
        if func == 'load':
            by_ic[ref][rail] = g['pins']
    for ref, rp in by_ic.items():
        rails = sorted(rp, key=lambda n: (-(b.volts(n) if b.volts(n) is not None else 0.0), n))
        for i, hi in enumerate(rails):
            for lo in rails[i + 1:]:
                if b.caps_between(hi, lo):
                    groups[(ref, (hi, lo), 'split_supply')] = {'ref': ref, 'rail': (hi, lo), 'function': 'split_supply',
                                                               'pins': list(rp[hi]), 'return_pins': list(rp[lo])}
    if CONVERTER_OUT:
        # the output filter of a buck (input filter of a boost): bulk capacitors at the inductor's far terminal
        for c in cells:
            L = c.get('inductor')
            far = c.get('vout') if c['class'] == 'buck' else c.get('vin') if c['class'] == 'boost' else None
            if not L or not far or far == c.get('cap_rail') or far not in b.r.rails:
                continue
            big = [x for x in b.caps_on(far) if (cap_class(b.nl.parts[x])[1] or 0) >= 9.9e-6 or b.nl.parts[x].package.polarized]
            pins = b.pads(L, far)
            if big and pins:
                # the converter's own filter is its first one or two bulk capacitors; more of them on the rail sit
                # at the loads (they stay its leftovers, owned but not pinned)
                func = 'converter_output' if c['class'] == 'buck' else 'converter_input'
                groups[(L, far, func)] = {'ref': L, 'rail': far, 'function': func, 'pins': pins, 'quota': min(2, len(big)),
                                          'cell': c['id']}
    if ENTRY_BULK:
        # a rail that enters through a connector (or its series diode or fuse) keeps its polarized bulk
        # capacitors at the entry: they hold the cable's inductance up, not one load's pins
        for rail, nr in b.r.rails.items():
            src = nr.attrs.get('source') or {}
            if src.get('kind') not in ('connector', 'battery') and not (src.get('kind') == 'derived' and src.get('via') in ('diode', 'fuse')):
                continue
            big = [c for c in b.caps_on(rail) if _entry_cap(b, c)]
            pins = b.pads(src['ref'], rail) if src.get('ref') in b.nl.parts else []
            if big and pins:
                groups[(src['ref'], rail, 'entry')] = {'ref': src['ref'], 'rail': rail, 'function': 'entry', 'pins': pins,
                                                       'quota': len(big)}
    return list(groups.values())


def _entry_cap(b: _B, c) -> bool:
    part = b.nl.parts[c]
    far = cap_class(part)[1]
    return part.package.polarized and (far is None or far >= 9.9e-6)


def allocate_caps(b: _B, cells, groups):
    """Joint per-rail allocation of rail-to-ground capacitors to commutation cells and decap groups.

    Score of capacitor c for consumer j: a base (cells CELL_BASE, groups log(1 + power pins)),
    plus schematic affinity (same sheet +2 / other -1, same reference block +1.5), plus a class
    preference (loads take small ceramics; cells take them too unless the loads' pins need every one, then
    the largest bulk ones; regulator outputs take bulk), plus RANK_W times the
    agreement of c's reference rank with j's rank on that rail. Greedy assignment by score with
    quotas (cells CELL_QUOTA, loads one per power pin, regulator pins one); leftovers go to the
    best-scoring consumer. Ownership probabilities are the softmax of the same scores."""
    cons = defaultdict(list)
    for c in cells:
        cons[c['cap_rail']].append(('cell', c, c['anchor']))
    for g in groups:
        cons[g['rail']].append(('decap', g, g['ref']))
    for rail, lst in cons.items():
        lst.sort(key=lambda t: (_refkey(t[2]), t[0]))
        caps = b.caps_between(*rail) if isinstance(rail, tuple) else sorted(b.caps_on(rail), key=_refkey)
        for _, x, _ in lst:
            x['caps'], x['caps_p'], x['quota_caps'] = [], {}, []
        if not caps:
            continue
        ncap, ng = len(caps), len(lst)
        cls = {c: cap_class(b.nl.parts[c])[0] for c in caps}
        far = {c: cap_class(b.nl.parts[c])[1] for c in caps}
        known = sorted(f for f in far.values() if f)
        med = known[len(known) // 2] if known else None
        # schematic rank order: the k-th load (by reference) tends to own the k-th capacitors; sources and
        # bypass pins sit outside that order (a regulator drawn first would shift every load by one)
        ranked = [j for j, (typ, x, _) in enumerate(lst) if typ == 'cell' or x['function'] == 'load']
        rank_of = {j: (k / (len(ranked) - 1) if len(ranked) > 1 else 0.5) for k, j in enumerate(ranked)}
        S = {}
        n_hf = sum(cls[c] in ('hf', 'mid') for c in caps)
        n_load = sum(len(x['pins']) for t, x, _ in lst if t == 'decap' and x['function'] == 'load')
        hf_spare = CELL_CLASS == 'hf' or n_hf > n_load
        for i, c in enumerate(caps):
            rc = i / (ncap - 1) if ncap > 1 else 0.5
            big = math.log10(far[c] / med) if far[c] and med else 0.0
            for j, (typ, x, anchor) in enumerate(lst):
                if typ == 'cell':
                    if hf_spare:
                        v = CELL_BASE + (0.5 if cls[c] in ('hf', 'mid') else 0.3)
                    else:
                        # the loads' pins need every small ceramic: the converter takes the bulk ones, largest first,
                        # and a small one only if the loads leave it over
                        v = CELL_BASE + (CELL_HF_SCARCE if cls[c] in ('hf', 'mid') else 0.5 + 0.1 * max(0.0, big))
                else:
                    v = 0.0               # pin counts enter through the quotas, not the score (layout check)
                    f = x['function']
                    if f in ('regulator_output', 'regulator_input'):
                        v += 0.5 + 0.5 * big          # sources and inputs take the larger capacitors
                    elif f in ('converter_output', 'converter_input'):
                        if not ((far[c] or 0) >= 9.9e-6 or b.nl.parts[c].package.polarized):
                            S[(c, j)] = None      # an exclusive owner: only its eligible capacitors, never a leftover
                            continue
                        v += 0.5 + 0.5 * big
                    elif f == 'bypass':
                        v += 0.5 if cls[c] in ('mid', 'bulk') else 0.0
                    elif f in ('load', 'split_supply'):
                        v += 0.3 if cls[c] == 'hf' else 0.0
                    elif f == 'entry':
                        if not _entry_cap(b, c):
                            S[(c, j)] = None
                            continue
                        v += 1.0
                v += _affinity(b, c, anchor)
                if len(ranked) > 1 and j in rank_of:
                    v += RANK_W * (1.0 - abs(rc - rank_of[j]))
                S[(c, j)] = v
        quota = [CELL_QUOTA if t == 'cell' else (len(x['pins']) if x['function'] in ('load', 'split_supply') else x.get('quota', 1))
                 for t, x, _ in lst]
        count = [0] * ng
        owner = {}
        if TIE_ORDER == 'random':
            import random
            import zlib
            rnd = random.Random(zlib.crc32(rail.encode()))
            corder = {c: rnd.random() for c in caps}
            jorder = {j: rnd.random() for j in range(ng)}
            tie = lambda t: (-t[0], corder[t[1]], jorder[t[2]])   # noqa: E731
        else:
            tie = lambda t: (-t[0], _refkey(t[1]), t[2])          # noqa: E731
        for v, c, j in sorted(((v, c, j) for (c, j), v in S.items() if v is not None), key=tie):
            if c in owner or count[j] >= quota[j]:
                continue
            owner[c] = j
            count[j] += 1
            lst[j][1].setdefault('quota_caps', []).append(c)      # within quota: the ones a pin pairing may name
        for c in caps:
            if c in owner:
                continue
            ok = [j for j in range(ng) if S[(c, j)] is not None]
            if not ok:
                continue
            # leftovers: among the owners that score within 0.5 of the best, the one with the fewest capacitors
            # per pin (not always the first in reference order)
            top = max(S[(c, j)] for j in ok)
            near = [j for j in ok if S[(c, j)] >= top - 0.5]
            j0 = min(near, key=lambda j: (count[j] / max(1, quota[j]), -S[(c, j)], j))
            owner[c] = j0
            count[j0] += 1
        for c in caps:
            if c not in owner:
                continue
            sp = [S[(c, j)] + (math.log(quota[j]) if lst[j][0] == 'decap' else 0.0) if S[(c, j)] is not None else None
                  for j in range(ng)]
            mx = max(v for v in sp if v is not None)
            z = [math.exp(v - mx) if v is not None else 0.0 for v in sp]
            tz = sum(z)
            j0 = owner[c]
            lst[j0][1]['caps'].append(c)
            lst[j0][1]['caps_p'][c] = round(z[j0] / tz, 3)
        for j, (typ, x, _) in enumerate(lst):
            x['shared_by'] = ng
            if typ == 'cell' and not x['caps']:
                # more converters than capacitors: borrow the best-scoring one, flagged as shared
                c = max(caps, key=lambda c: S[(c, j)] if S[(c, j)] is not None else -99.0)
                x['caps'] = [c]
                x['caps_p'] = {c: 0.0}
                x['cap_shared'] = True


def _finish_cells(b: _B, cells):
    for c in cells:
        caps = _hf_order(b.nl, c['caps'])
        c['caps'] = caps
        rail, gnd = c['cap_rail'], c['cap_gnd']
        if caps:
            hf = caps[0]
            gpad = b.cap_pad(hf, gnd) if gnd in b.nl.parts[hf].nets else b.cap_pad(hf, next(iter(b.nl.parts[hf].nets - {rail})))
            c['loop'] = [[hf, b.cap_pad(hf, rail)]] + c['loop_core'] + [[hf, gpad]]
            if c.get('cap_shared'):
                c['evidence'].append(ev('count', f"no capacitor left for this converter on '{b.short(rail)}'; {hf} is shared", -1.0))
            elif c.get('shared_by', 1) > 1:
                c['evidence'].append(ev('count', f"{c['shared_by']} consumers on '{b.short(rail)}'; ownership {c['caps_p'].get(hf, 0):.2f}",
                                        0.0))
        else:
            c['loop'] = list(c['loop_core'])
            c['evidence'].append(ev('topology', f"no capacitor from '{b.short(rail)}' to ground: the loop is open", -2.0))
        c['confidence'] = round(min(c['confidence'], confidence(c['evidence'], prior=-0.5) + 0.0), 3) if not caps or c.get('cap_shared') \
            else c['confidence']
        for k in ('loop_core', 'cap_rail', 'cap_gnd', 'anchor', 'shared_by'):
            c.pop(k, None)


def decaps(b: _B, groups) -> list:
    out = []
    b.uncovered = []
    by_rail = defaultdict(list)
    for g in groups:
        by_rail[g['rail']].append(g)
    split_ok = {(g['ref'], r) for g in groups if g['function'] == 'split_supply' and g.get('caps') for r in g['rail']}
    for key, gs in by_rail.items():
        split = isinstance(key, tuple)
        n_pins = sum(len(g['pins']) for g in gs)
        ncap = len(b.caps_between(*key) if split else b.caps_on(key))
        for g in sorted(gs, key=lambda g: (_refkey(g['ref']), g['function'])):
            rail = key[0] if split else key
            mine = g.get('caps') or []
            if not mine:
                if g['function'] == 'load' and (g['ref'], rail) not in split_ok:
                    b.uncovered.append((g['ref'], rail, len(g['pins'])))
                continue
            ref = g['ref']
            ng = g.get('shared_by', len(gs))
            if split:
                gnd = key[1]
                gpins = sorted(g['return_pins'], key=_natkey)
            else:
                gnd = _decap_ground(b, ref, rail)
                gpins = sorted({p.number for p in b.nl.parts[ref].active_pins() if p.net == gnd}, key=_natkey)
            cls = {c: cap_class(b.nl.parts[c])[0] for c in mine}
            hf = [c for c in mine if cls[c] in ('hf', 'mid')]
            bulk = [c for c in mine if c not in hf]
            pins = sorted(g['pins'], key=_natkey)
            cp = g['caps_p']
            # a pin pairing only where the netlist decides it: one power pin, and capacitors this group owns with
            # p >= 0.5. Several pins on one net: the placer pairs each capacitor with the nearest pin.
            qc = [c for c in g.get('quota_caps') or [] if c in mine]
            # a load pins only its small ceramics (their place is at the pin); its bulk capacitors serve the rail
            pool = [c for c in qc if c in hf] if g['function'] in ('load', 'split_supply') else ([c for c in qc if c in hf] or qc)
            sure = [c for c in pool if cp.get(c, 0.0) >= 0.5]
            pin_caps = {pins[0]: sure} if len(pins) == 1 and sure and g['function'] != 'entry' else {}
            # bulk at a cable entry may sit anywhere on the rail: no pin of the connector claims it
            pairing = 'pin' if pin_caps else ('nearest_load' if g['function'] == 'entry' else 'nearest_pin')
            if g['function'] == 'entry':
                evs = [ev('topology', f"'{b.short(rail)}' enters through {ref}; polarized bulk capacitor(s) {', '.join(mine)}", MODERATE)]
            elif g['function'] in ('converter_output', 'converter_input'):
                evs = [ev('topology', f"bulk capacitor(s) {', '.join(mine)} on '{b.short(rail)}' at power inductor {ref} "
                                      f"({'output' if g['function'] == 'converter_output' else 'input'} filter of {g['cell']})", MODERATE)]
            else:
                evs = [ev('topology', f"{len(pins)} power pin(s) of {ref} on '{b.short(rail)}'", MODERATE)]
            if split:
                evs.append(ev('topology', f"capacitor(s) straight across {ref}'s supply pins ('{b.short(rail)}' to '{b.short(gnd)}')", STRONG))
                if ng > 1:
                    evs.append(ev('count', f"{ng} ICs share the {ncap} capacitor(s) across these rails", 0.0))
            elif ng == 1:
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
            if split:
                conf_cap = min(conf_cap, b.r.nets[gnd].confidence if gnd in b.r.nets else 0.6)
            sid = f"decap:{ref}:{b.short(rail)}" + (f"~{b.short(gnd)}" if split else '') + ('' if g['function'] == 'load' else f":{g['function']}")
            out.append(_struct('decap', sid, evs,
                               conf_cap=conf_cap, prior=0.0,
                               ic=ref, power_pins=pins, ground_pins=gpins, rail=rail, ground=gnd, caps=sorted(mine, key=_refkey),
                               caps_p=cp, hf_caps=hf, bulk_caps=bulk, pin_caps=pin_caps, pairing=pairing, function=g['function'],
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
    cell_parts = getattr(b, 'cell_parts', set())
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
            if p.ref in cell_parts:
                continue
            o_clamp = b.nl.other_net(b.nl.parts[p.ref], cur) if k == 'diode' else None
            if (k == 'diode' and sub in PROTECT_SUBS and (sub == 'esd_array' or o_clamp is None or o_clamp in b.g or o_clamp in b.r.rails)) \
                    or k == 'varistor' or (k == 'diode' and _clamps(b, p.ref, cur)):
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
            if p.ref in cell_parts:
                continue           # a converter's inductor or rectifier is the cell, not a cable filter
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
    """A plain diode from a signal net to a ground or rail acts as a clamp; one from a supply input
    into a rail (OR-ing, reverse protection) is a series power part, not a clamp."""
    part = b.nl.parts[ref]
    o = b.nl.other_net(part, net)
    if o is None or not (o in b.g or o in b.r.rails) or b.sub(ref) not in ('signal', 'schottky') or net in b.r.rails:
        return False
    if o in b.r.rails and not any(b.k(p.ref) in ('ic', 'module') for p in b.nl.pins(net)):
        return False          # nothing on the input but the connector: the diode carries the supply
    return True


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
            unnamed = not p.fn or p.fn == p.number
            if not (FB_PIN.match(p.fn) or (unnamed and pr.subtype in REGULATOR_SUBS and re.search(r'(^|[^A-Z])V?FB([^A-Z]|$)', b.short(p.net)))) \
                    or p.net in b.g:
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
                        div['vref_source'] = 'table'
                        div['vout_implied_V'] = round(vals[0] * ratio, 3)
                        if vrail and abs(vals[0] * ratio - abs(vrail)) <= 0.06 * abs(vrail):
                            evs.append(ev('derived', f"Vref {vals[0]} V x {ratio:.3f} = {vals[0] * ratio:.2f} V matches '{b.short(top[1])}'", MODERATE))
                    elif vrail:
                        for vr in (0.5, 0.6, 0.765, 0.8, 0.9, 1.0, 1.21, 1.23, 1.25):
                            if abs(vr * ratio - abs(vrail)) <= 0.04 * abs(vrail):
                                div['vref_V'] = vr
                                div['vref_source'] = 'matched to the rail name'
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


def divider_victims(b: _B, taken: set) -> list:
    """Resistive dividers that are not regulator feedback: a node with one resistor from a rail, a switch
    node, a connector net or an analog net, and one resistor to ground, read by an IC or a connector
    (voltage monitors, back-EMF sense, thresholds). The node is high impedance: a victim."""
    out = []
    for m, nv in sorted(b.nl.nets.items()):
        if m in taken or m in b.g or m in b.r.rails or m in b.r.switch_nodes:
            continue
        res = [p for p in nv.pins if b.k(p.ref) == 'resistor' and len(b.nl.parts[p.ref].nets) == 2]
        if len(res) < 2 or len(res) > 3:
            continue
        top = bot = None
        for p in res:
            o = b.nl.other_net(b.nl.parts[p.ref], m)
            if o in b.g:
                bot = bot or p.ref
            elif o is not None:
                onr = b.r.nets.get(o)
                feeds = o in b.r.rails or o in b.r.switch_nodes or (onr and onr.role in ('analog', 'switch_node')) or \
                    any(b.k(q.ref) == 'connector' for q in b.nl.pins(o))
                if feeds and top is None:
                    top = (p.ref, o)
        if not top or not bot:
            continue
        others = [p for p in nv.pins if p.ref not in (top[0], bot)]
        if any(b.k(p.ref) == 'transistor' for p in others):
            continue          # a gate network, not a measurement
        readers = [p for p in others if b.k(p.ref) in ('ic', 'module', 'connector')]
        if not readers:
            continue
        src = (b.r.rails[top[1]].attrs.get('source') or {}) if top[1] in b.r.rails else {}
        vtop = b.volts(top[1])
        analog_reader = any(ANALOG_PIN.match(p.fn) or any(ANALOG_PIN.match(x) for x in p.fn.split('/')) for p in readers
                            if b.k(p.ref) in ('ic', 'module'))
        if src.get('kind') in ('regulator', 'converter', 'internal', 'module', 'derived') and vtop is not None and abs(vtop) <= 5.5 \
                and not ANALOG_NET.search(b.short(m)) and not analog_reader:
            continue          # a strap or bias on a logic pin from a regulated rail, not a measurement
        rt, rb = V.resistance(b.nl.parts[top[0]].value), V.resistance(b.nl.parts[bot].value)
        evs = [ev('topology', f"divider {top[0]} from '{b.short(top[1])}' and {bot} to ground on '{b.short(m)}', read by {readers[0].label}",
                  MODERATE + 0.5)]
        if rt is not None and rb is not None and rt + rb > 0:
            evs.append(ev('value', f"ratio {rb / (rt + rb):.3f}", 0.3))
        loop = [[top[0], b.pad_sel(top[0], m)], [bot, b.pad_sel(bot, m)]] + [[p.ref, p.number] for p in readers[:2]]
        out.append(_struct('victim', f"victim:divider:{b.short(m)}", evs, conf_cap=0.9, prior=0.0,
                           **{'class': 'analog', 'subclass': 'divider', 'nets': [m], 'loop': loop,
                              'divider': {'top': top[0], 'bottom': bot, 'sense_net': top[1], 'r_top_ohm': rt, 'r_bot_ohm': rb,
                                          'ratio': round(rb / (rt + rb), 4) if rt and rb else None}}))
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
                # shunt parts on the IC-side net belong to the match too
                for p in sorted(b.nl.pins(cur), key=lambda x: _refkey(x.ref)):
                    if p.ref not in match and b.k(p.ref) in RF_PASS and b.nl.other_net(b.nl.parts[p.ref], cur) in b.g:
                        match.append(p.ref)
                        feed.append([p.ref, p.number])
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
                if (OUT_PIN.match(p.fn) or b.r.sem(p) == 'supply_out') and b.volts(p.net):
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


def _apply_dividers(b: _B, fb, cells):
    """A feedback divider with a known reference states its rail's voltage: Vout = Vref (1 + Rtop/Rbot).
    It fills rails whose voltage is unknown or only estimated, flags conflicts with a stated one, and
    refreshes the excitation of cells on those rails."""
    for v in fb:
        d = v.get('divider') or {}
        net, vo = d.get('sense_net'), d.get('vout_implied_V')
        if not net or not vo or net not in b.r.rails or d.get('vref_source') != 'table':
            continue
        nr = b.r.rails[net]
        vb = nr.attrs.get('volts') or {}
        src = f"feedback divider {d.get('top')}/{d.get('bottom')} x Vref {d.get('vref_V')} V of {v['ic']}"
        if vb.get('value') is None or str(vb.get('relative_to', '')).startswith('estimate'):
            nr.attrs['volts'] = belief(vo, 'V', src, round(vo * 0.95, 3), round(vo * 1.05, 3), lineage=[vb.get('relative_to', '')] if vb else [])
        elif abs(abs(vb['value']) - vo) > 0.08 * abs(vb['value']):
            vb.setdefault('lineage', []).append(f"conflict: {src} gives {vo:g} V")
    for c in cells:
        ex = c['excite']
        v = b.volts(c['rail'])
        vb = (b.r.nets.get(c['rail']).attrs.get('volts') or {}) if b.r.nets.get(c['rail']) else {}
        if v is not None and ex.get('V') != v:
            ex['V'] = v
            ex['basis'] = [x for x in ex['basis'] if not x.startswith('V ')] + [f"V from '{b.short(c['rail'])}': {vb.get('relative_to', '')}"]
        elif v is not None and str(vb.get('relative_to', '')).startswith('estimate'):
            ex['basis'].append(f"V {v:g} V is an estimate from capacitor ratings")


# =============================================================================== entry
def find_structures(nl: Netlist, roles: Roles) -> dict:
    b = _B(nl, roles)
    cells = commutation_cells(b)
    b.cell_parts = {x for c in cells for x in [c.get('inductor')] + list((c.get('switches') or {}).values()) if x and x != c.get('controller')}
    groups = _decap_groups(b, cells)
    allocate_caps(b, cells, groups)
    by_id = {c['id']: c for c in cells}
    for g in groups:
        if g['function'] in ('converter_output', 'converter_input') and g.get('caps') and g.get('cell') in by_id:
            by_id[g['cell']]['output_caps' if g['function'] == 'converter_output' else 'input_caps'] = sorted(g['caps'], key=_refkey)
    _finish_cells(b, cells)
    st = {'commutation_cells': cells}
    st['decaps'] = decaps(b, groups)
    st['uncovered'] = [{'ic': r, 'rail': n, 'pins': k} for r, n, k in getattr(b, 'uncovered', [])]
    st['crystals'] = crystals(b)
    st['oscillators'] = oscillators(b)
    st['chains'] = connector_chains(b)
    fb = feedback_victims(b)
    _apply_dividers(b, fb, cells)
    se = sense_victims(b)
    taken = {n for v in fb + se for n in v.get('nets', [])}
    dv = divider_victims(b, taken)
    taken |= {n for v in dv for n in v['nets']}
    se = se + dv
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
    pp, ph = power_paths(b, cells)
    st['power_paths'] = pp
    have = {h['part']: i for i, h in enumerate(hs)}
    for h in ph:                       # a pass element's I^2 R joins the heat sources (the larger estimate wins)
        i = have.get(h['part'])
        if i is None:
            hs.append(h)
        elif h['P_W'] > hs[i]['P_W']:
            hs[i] = h
        if h['P_W'] > (pw.get(h['part']) or (0.0,))[0]:
            pw[h['part']] = (h['P_W'], h['P_W_belief']['basis'])
    st['heat_sources'] = hs
    st['P_W'] = pw
    st['thermal_victims'] = thermal_victims(b)
    return st


# =============================================================================== power paths (no switching)
# R_ds(on) of pass elements by part number (datasheet typical at Vgs = 10 V / 4.5 V for logic-level parts), E5
FET_RON_TABLE = [(r'IPT012N08N5', 1.2e-3), (r'IRF1018E', 8.4e-3), (r'DMG2305U', 52e-3), (r'DMG3415U', 39e-3), (r'DMP3013SFV', 13e-3),
                 (r'DMP6023LSS', 28e-3), (r'DMP510DL', 5.0), (r'AO3401', 50e-3), (r'AO3400', 30e-3), (r'SI2301', 110e-3),
                 (r'SI2302', 60e-3), (r'IRLML6402', 65e-3), (r'IRLML2502', 45e-3), (r'IRF9540', 0.2), (r'IRF540', 44e-3), (r'IRLZ44', 22e-3),
                 (r'BSC0\d\dN', 3e-3), (r'CSD1\d{4}', 5e-3), (r'PSMN\d', 5e-3), (r'NVMFS|NTMFS', 3e-3), (r'IPB\d|IPD\d', 5e-3)]
# rated current and on-resistance of load-switch, eFuse, power-mux and ideal-diode ICs (datasheet), E5
LOAD_SWITCH_TABLE = [(r'NCP4556\d', 24.0, 3.3e-3), (r'TPS2211\d|TPS22918', 2.0, 52e-3), (r'TPS22919', 1.5, 90e-3), (r'TPS2115', 1.25, 84e-3),
                     (r'TPS2121', 4.5, 56e-3), (r'TPS2116', 2.5, 40e-3), (r'TPS259\d', 4.0, 30e-3), (r'AP2280\d|AP22802', 2.0, 70e-3),
                     (r'AP2171|AP2191', 1.0, 100e-3), (r'AP2553|AP255\d', 2.5, 70e-3), (r'TPS205\d', 0.5, 70e-3), (r'SY6280', 2.0, 110e-3),
                     (r'LM66100', 1.5, 79e-3), (r'MIC20\d\d', 0.5, 90e-3), (r'RT9742', 1.5, 70e-3), (r'MAX17613', 3.0, 260e-3),
                     (r'SLG5NT', 4.0, 15e-3)]
FET_CLASS = [(r'TOLL|HSOF|LFPAK|D2PAK|TO-?263|TO-?247', 30.0, 2e-3), (r'TO-?220|DPAK|TO-?252', 10.0, 10e-3),
             (r'PowerPAK|PowerDI|SON|DFN|SO-?8|SOIC-?8|PG-|TDSON|SuperSO', 5.0, 10e-3), (r'SOT-?223|SOT-?89', 2.0, 50e-3),
             (r'SOT-?23|SOT-?323|SC-?70|SOT-?563|SOT-?723|DFN1006', 1.0, 80e-3)]
SMALL_FET = re.compile(r'BSS\d|2N7002|BS170|BS250|MMBF|NTR4003|DMG1012|FDV30\d|SI1\d{3}|PMV\d{2}X|NX\d{4}|DMN6\d|DMN2\d{3}U?W', re.I)
IN_SW_PIN = re.compile(r'^(P?VIN\d*|IN\d?|VIN_?[A-Z0-9]*|IN_?[12AB]|VBUS|VBAT|PVIN)$', re.I)
OUT_SW_PIN = re.compile(r'^(V?OUT\d*|OUT_?[A-Z0-9]*|VOUT_?[A-Z0-9]*|PVOUT)$', re.I)
CONN_CURRENT = {'usb': 3.0, 'power': 2.0, 'battery': 2.0, 'header': 1.0, 'wire_to_board': 1.0, 'board_to_board': 1.0}


def _gds(b: _B, ref):
    """{'G': net, 'D': net, 'S': net} of a MOSFET from its pin functions, or None."""
    by = {}
    for p in b.nl.parts[ref].active_pins():
        f = (p.fn or '')[:1].upper()
        if f in 'GDS' and (len(p.fn) == 1 or p.fn[1:].isdigit() or p.fn[1:2] in '_ '):
            by.setdefault(f, set()).add(p.net)
    if not all(len(by.get(k, ())) == 1 for k in 'GDS'):
        return None
    return {k: next(iter(v)) for k, v in by.items()}


def _fet_ron(b: _B, ref):
    part = b.nl.parts[ref]
    t = part.text()
    for rx_, r in FET_RON_TABLE:
        if re.search(rx_, t, re.I):
            return r, f"R_ds(on) {r * 1e3:g} mOhm for {re.search(rx_, t, re.I).group(0)} (table)"
    for rx_, _, r in FET_CLASS:
        if re.search(rx_, part.lib_id, re.I):
            return r, f"R_ds(on) {r * 1e3:g} mOhm, package class {re.search(rx_, part.lib_id, re.I).group(0)}"
    return 50e-3, 'R_ds(on) 50 mOhm, default class'


def _power_net(b: _B, n, fet_nets=None) -> bool:
    """A net that carries supply current: a rail, a ground, or a net with IC supply pins, decoupling, or the
    main terminals of two or more power FETs (an OR node)."""
    if n in b.r.rails or n in b.g:
        return True
    if fet_nets and fet_nets.get(n, 0) >= 2:
        return True
    if b.r.caps_to.get(n):
        return True
    for p in b.nl.pins(n):
        if b.k(p.ref) in ('ic', 'module') and b.r.sem(p) in ('supply', 'supply_out'):
            return True
    return False


def _up_score(b: _B, n) -> float:
    """How much `n` looks like the supply side of a path (sources, input names) rather than the load side."""
    nr = b.r.rails.get(n)
    src = (nr.attrs.get('source') if nr else None) or {}
    sc = {'battery': 3.0, 'connector': 2.5, 'rectifier': 2.0, 'regulator': 2.0, 'converter': 2.0, 'module': 1.5, 'internal': 1.0,
          'derived': 1.0}.get(src.get('kind'), 0.0)
    s = b.short(n)
    if re.search(r'BAT|VIN|_IN\b|IN$|RAW|VBUS|USB|INPUT|SUPPLY|SRC', s):
        sc += 1.0
    if re.search(r'OUT|PROT|LOAD|SYS|_SW\b|SWITCHED|PACK', s):
        sc -= 0.75
    sc -= 0.1 * sum(1 for p in b.nl.pins(n) if b.k(p.ref) in ('ic', 'module') and b.r.sem(p) == 'supply')
    return sc


def _gate_drive(b: _B, q, g, d, s):
    """'ground' (gate held at ground: reverse-polarity protection), 'mirror' (a bipolar pair or an ideal-diode
    controller drives it), 'switch' (a GPIO, transistor, switch or driver turns it on and off) or None."""
    if g in b.g:
        return 'ground'
    parts = [p for p in b.nl.pins(g) if p.ref != q]
    kinds = {b.k(p.ref) for p in parts}
    for p in parts:
        pr = b.r.parts[p.ref]
        if pr.kind == 'ic' and re.search(r'ideal diode|LTC4412|LM5050|LTC435\d|LM7480|TPS2113|MAX40200', b.nl.parts[p.ref].text(), re.I):
            return 'mirror'
        if pr.kind == 'transistor' and pr.subtype in ('pnp', 'bjt') and len(set(b.nl.parts[p.ref].nets) & {d, s}) >= 1:
            return 'mirror'
    if 'ic' in kinds or 'module' in kinds or 'switch' in kinds or 'transistor' in kinds:
        return 'switch'
    res = [p for p in parts if b.k(p.ref) == 'resistor']
    for p in res:                      # a driver one resistor away: GPIO, switch, transistor, connector control pin
        o = b.nl.other_net(b.nl.parts[p.ref], g)
        if o and o not in b.g and o not in b.r.rails and o not in (d, s) and \
                any(b.k(x.ref) in ('ic', 'module', 'switch', 'transistor', 'connector') and x.ref != q for x in b.nl.pins(o)):
            return 'switch'
    if res and all(b.nl.other_net(b.nl.parts[p.ref], g) in b.g or b.nl.other_net(b.nl.parts[p.ref], g) in (s,) for p in res) and \
            any(b.nl.other_net(b.nl.parts[p.ref], g) in b.g for p in res):
        return 'ground'
    return None


def _path_current(b: _B, sws, rail_in, rail_out, series, ic=None, stages=None):
    """(I, basis) for a power path: fuse rating > load-switch table > shunt full scale > connector or FET class."""
    for f in series + [p.ref for n in (rail_in, rail_out) for p in b.nl.pins(n) if b.k(p.ref) == 'fuse']:
        v = b.nl.parts[f].value
        m = re.search(r'(\d+(?:\.\d+)?)\s*A\b', v) or re.search(r'(?<![\d.])(\d+(?:\.\d+)?)A(?![a-z])', v)
        if m:
            return float(m.group(1)), f"fuse {f} rated {m.group(1)} A ('{v}')"
        m = re.search(r'MF-\w*?(\d{3})|0ZC[A-Z](\d{4})', v)
        if m:
            amps = int(m.group(1)) / 100 if m.group(1) else int(m.group(2)) / 100
            return amps, f"fuse {f} hold current {amps:g} A from its part number"
    if ic:
        for rx_, amps, _ in LOAD_SWITCH_TABLE:
            if re.search(rx_, b.nl.parts[ic].text(), re.I):
                return amps, f"{ic} rated {amps:g} A (table)"
    for sh in series:
        if b.r.parts[sh].subtype == 'shunt':
            ohm = b.r.parts[sh].attrs.get('ohms') or V.resistance(b.nl.parts[sh].value)
            if ohm:
                return round(0.05 / ohm, 2), f"shunt {sh} ({ohm * 1e3:g} mOhm) at an assumed 50 mV full scale"
    best = (1.0, 'default 1 A')
    conns = [b.r.parts[p.ref].subtype for n in (rail_in, rail_out) for p in b.nl.pins(n) if b.k(p.ref) == 'connector']
    if conns:
        amps = max(CONN_CURRENT.get(c or 'header', 1.0) for c in conns)
        best = (amps, f"connector class ({', '.join(sorted({c or 'header' for c in conns}))}) {amps:g} A")
    n_par = min(len(st_) for st_ in stages) if stages else 1
    for q in sws[:1]:
        for rx_, amps, _ in FET_CLASS:
            if re.search(rx_, b.nl.parts[q].lib_id, re.I) and amps * n_par > best[0]:
                best = (amps * n_par, f"package class of {q} ({re.search(rx_, b.nl.parts[q].lib_id, re.I).group(0)}) "
                                      f"{amps:g} A x {n_par} in parallel")
                break
    return best


PKG_WATTS = [(r'TOLL|HSOF|LFPAK|D2PAK|TO-?263|TO-?247', 5.0), (r'TO-?220|DPAK|TO-?252', 3.0),
             (r'PowerPAK|PowerDI|SON|DFN|SO-?8|SOIC-?8|PG-|TDSON|SuperSO', 2.0), (r'SOT-?223|SOT-?89', 1.0),
             (r'SOT-?23|SOT-?323|SC-?70|SOT-?563|SOT-?723|DFN1006', 0.35)]


def _dissipation_cap(b: _B, p):
    """The largest current the path's pass elements can carry at their package's dissipation (a designer who
    picked a SOT-23 FET with 5 ohm on-resistance did not plan amperes through it), or None."""
    if p.get('ic') or not p['ron']:
        return None
    worst = None
    for st_ in p['stages']:
        w = next((w for rx_, w in PKG_WATTS if re.search(rx_, b.nl.parts[st_[0]].lib_id, re.I)), None)
        if w is None:
            return None
        r1, _ = _fet_ron(b, st_[0])
        i_max = len(st_) * math.sqrt(w / r1)
        worst = i_max if worst is None else min(worst, i_max)
    return worst


def _path_series(b: _B, net):
    """Shunts and fuses continuing the path from `net` (an output into a connector through a shunt)."""
    out = []
    for p in b.nl.pins(net):
        k, sub = b.k(p.ref), b.r.parts[p.ref].subtype
        if (k == 'resistor' and sub == 'shunt') or k == 'fuse':
            out.append(p.ref)
    return sorted(set(out), key=_refkey)


def power_paths(b: _B, cells) -> tuple[list, list]:
    """Non-switching power paths (load switches, power muxes, ideal-diode OR, reverse-polarity FETs, FET banks):
    -> (power_path structures, heat_source structures)."""
    cell_parts = getattr(b, 'cell_parts', set()) | {c.get('controller') for c in cells}
    paths = []
    # ---- integrated load switches, eFuses, power muxes
    for ref, pr in sorted(b.r.parts.items(), key=lambda t: _refkey(t[0])):
        if pr.kind != 'ic' or pr.subtype != 'load_switch' or ref in cell_parts:
            continue
        part = b.nl.parts[ref]
        ins = sorted({p.net for p in part.active_pins() if IN_SW_PIN.match(p.fn) and p.net not in b.g and _power_net(b, p.net)})
        outs = sorted({p.net for p in part.active_pins() if OUT_SW_PIN.match(p.fn) and p.net not in b.g} - set(ins))
        if not ins or not outs:
            continue
        cls = 'power_mux' if len(ins) >= 2 else ('ideal_diode' if re.search(r'ideal diode|LM66100|LTC4412|TPS2113', part.text(), re.I)
                                                 else 'load_switch')
        _, _, ron = next(((a, i, r) for a, i, r in LOAD_SWITCH_TABLE if re.search(a, part.text(), re.I)), (None, None, 0.1))
        rbasis = (f"R_on {ron * 1e3:g} mOhm for {ref} (table)" if any(re.search(a, part.text(), re.I) for a, _, _ in LOAD_SWITCH_TABLE)
                  else 'R_on 100 mOhm, load-switch class')
        for rin in ins:
            paths.append({'class': cls, 'switches': [ref], 'stages': [[ref]], 'controller': ref, 'rail_in': rin, 'rail_out': outs[0],
                          'ron': ron, 'ron_basis': rbasis, 'ic': ref, 'group': ref if len(ins) >= 2 else None})
    # ---- discrete MOSFETs: banks (same drain and source) chained through middle nets
    fets = {}
    for ref, pr in b.r.parts.items():
        if pr.kind != 'transistor' or pr.subtype not in ('nmos', 'pmos', 'mosfet') or ref in cell_parts:
            continue
        t = _gds(b, ref)
        if not t or t['D'] == t['S'] or t['D'] in b.r.switch_nodes or t['S'] in b.r.switch_nodes:
            continue
        both = (t['D'] in b.r.rails or t['D'] in b.g) and (t['S'] in b.r.rails or t['S'] in b.g)
        if SMALL_FET.search(b.nl.parts[ref].text()) and not both:
            continue
        fets[ref] = t
    # FET groups joined through middle nets that reach both a rail and a ground are totem poles (CMOS logic,
    # half-bridges), not power paths
    term = lambda n: n in b.g or n in b.r.rails   # noqa: E731
    comp = {}
    for ref in sorted(fets):
        if ref in comp:
            continue
        stack, seen = [ref], {ref}
        while stack:
            x = stack.pop()
            for n in (fets[x]['D'], fets[x]['S']):
                if term(n):
                    continue
                for y, t in fets.items():
                    if y not in seen and n in (t['D'], t['S']):
                        seen.add(y)
                        stack.append(y)
        for x in seen:
            comp[x] = frozenset(seen)
    for grp in set(comp.values()):
        ends = {n for x in grp for n in (fets[x]['D'], fets[x]['S']) if term(n)}
        if len(grp) >= 2 and any(n in b.g for n in ends) and any(n not in b.g for n in ends):
            for x in grp:
                fets.pop(x, None)
    banks = defaultdict(list)
    fet_nets = defaultdict(int)
    for ref, t in fets.items():
        banks[frozenset((t['D'], t['S']))].append(ref)
        fet_nets[t['D']] += 1
        fet_nets[t['S']] += 1
    bank_nets = {k: tuple(sorted(k)) for k in banks}
    adj = defaultdict(list)
    for k, (a, c) in bank_nets.items():
        if _power_net(b, a, fet_nets) and _power_net(b, c, fet_nets):   # a pre-charge FET into a resistor is no stage
            adj[a].append(k)
            adj[c].append(k)
    used = set()
    for k in sorted(banks, key=lambda k: sorted(banks[k])):
        if k in used:
            continue
        a, c = bank_nets[k]
        chain, ends = [k], [a, c]
        # extend through a middle net that only FET main terminals (and gate/bias parts) touch: back-to-back banks
        def middle(n):
            if n in b.g or len(adj[n]) != 2:
                return False
            other = {p.ref for p in b.nl.pins(n)} - {q for kk in adj[n] for q in banks[kk]}
            return n not in b.r.rails or all(b.k(x) in ('resistor', 'capacitor', 'diode', 'test_point') for x in other)
        for i in (0, 1):
            n = ends[i]
            while middle(n):
                k2 = next(x for x in adj[n] if x not in chain)
                if k2 in used:
                    break
                chain.append(k2)
                a2, c2 = bank_nets[k2]
                n = c2 if a2 == n else a2
                ends[i] = n
        e0, e1 = ends
        if not (_power_net(b, e0, fet_nets) and _power_net(b, e1, fet_nets)) or e0 == e1:
            continue
        if e0 in b.g and e1 in b.g:
            continue
        if (e0 in b.g or e1 in b.g) and len(chain) >= 2:
            continue           # a totem pole from a rail to ground through a middle node: a logic gate or a half-bridge
        if (e0 in b.g or e1 in b.g) and len(chain) == 1:
            other = e1 if e0 in b.g else e0
            src = (b.r.rails.get(other).attrs.get('source') if other in b.r.rails else None) or {}
            if src.get('kind') in ('regulator', 'converter', 'battery', 'internal', 'module', 'rectifier') or \
                    (src.get('kind') == 'connector' and 'input connector' in (src.get('note') or '')):
                continue       # a FET straight across a supply rail is a crowbar or a clamp, not a load path
        used |= set(chain)
        sws = sorted({q for kk in chain for q in banks[kk]}, key=_refkey)
        q0 = banks[chain[0]][0]
        t0, sub = fets[q0], b.sub(q0)
        drive = _gate_drive(b, q0, t0['G'], t0['D'], t0['S'])
        if e0 in b.g or e1 in b.g:                       # low side: the load's return through the FET to ground
            rin, rout = (e1, e0) if e0 in b.g else (e0, e1)
        elif sub == 'pmos' and drive in ('mirror', 'ground') and len(chain) == 1:
            rin, rout = t0['D'], t0['S']                 # body diode forward: ideal diode or reverse-polarity PMOS
        elif sub == 'pmos' and drive == 'switch' and len(chain) == 1:
            rin, rout = t0['S'], t0['D']                 # high-side load switch
        else:
            rin, rout = (e0, e1) if _up_score(b, e0) >= _up_score(b, e1) else (e1, e0)
        if len(sws) >= 2 or len(chain) >= 2:
            cls = 'fet_bank'
        elif rout in b.g or (sub == 'nmos' and t0['S'] in b.g and t0['D'] not in b.g and drive == 'switch'):
            cls = 'fet_switch'
        elif drive == 'ground' or (sub == 'nmos' and t0['S'] in b.g):
            cls = 'reverse_polarity'
        elif drive == 'mirror':
            cls = 'ideal_diode'
        else:
            cls = 'fet_switch'
        stages = [sorted(banks[kk], key=_refkey) for kk in chain]
        ron, rb = 0.0, []
        for st_ in stages:
            r1, basis = _fet_ron(b, st_[0])
            ron += r1 / len(st_)
            rb.append(basis + (f", {len(st_)} in parallel" if len(st_) > 1 else ''))
        ctrl = None
        for p in b.nl.pins(t0['G']):
            if b.k(p.ref) in ('ic', 'module'):
                ctrl = p.ref
        if ctrl is None:
            for p in b.nl.pins(t0['G']):
                if b.k(p.ref) == 'resistor':
                    o = b.nl.other_net(b.nl.parts[p.ref], t0['G'])
                    if not o or o in b.g or o in b.r.rails:
                        continue             # a gate pull to ground or a rail names no controller
                    ctrl = next((x.ref for x in b.nl.pins(o) if b.k(x.ref) in ('ic', 'module')), None)
                    if ctrl:
                        break
        paths.append({'class': cls, 'switches': sws, 'stages': stages, 'controller': ctrl, 'rail_in': rin, 'rail_out': rout,
                      'ron': ron, 'ron_basis': '; '.join(rb), 'ic': None, 'group': None, 'drive': drive})
    # ---- OR groups: several paths into one output
    by_out = defaultdict(list)
    for p in paths:
        by_out[p['rail_out']].append(p)
    for out, ps in by_out.items():
        if len(ps) >= 2 and all(p['class'] in ('ideal_diode', 'reverse_polarity', 'power_mux', 'load_switch', 'fet_switch') for p in ps) \
                and out not in b.g:
            for p in ps:
                p['group'] = p['group'] or f"or:{b.short(out)}"
                if p['class'] in ('reverse_polarity',) and p.get('drive') != 'ground':
                    p['class'] = 'ideal_diode'
    # ---- structures
    out_s, heat_s = [], []
    for p in paths:
        rin, rout = p['rail_in'], p['rail_out']
        gnd = b.r.gnd if rout not in b.g else rout
        series = _path_series(b, rout) + [x for x in _path_series(b, rin) if x not in _path_series(b, rout)]
        caps_in = _hf_order(b.nl, b.caps_on(rin, gnd)) if rin not in b.g else []
        caps_out = _hf_order(b.nl, b.caps_on(rout, gnd)) if rout not in b.g else []
        sw0 = p['switches'][0]
        last = p['stages'][-1][0]
        loop = []
        if caps_in:
            loop.append([caps_in[0], b.cap_pad(caps_in[0], rin)])
        loop += [[sw0, b.pad_sel(sw0, rin)], [last, b.pad_sel(last, rout)]]
        if caps_out:
            loop += [[caps_out[0], b.cap_pad(caps_out[0], rout)], [caps_out[0], b.cap_pad(caps_out[0], next(iter(b.nl.parts[caps_out[0]].nets - {rout})))]]
        if caps_in:
            loop.append([caps_in[0], b.cap_pad(caps_in[0], next(iter(b.nl.parts[caps_in[0]].nets - {rin})))])
        I_, ibasis = _path_current(b, p['switches'], rin, rout, series, p['ic'], p['stages'])
        cap = _dissipation_cap(b, p)
        if cap is not None and cap < I_:
            ibasis = f"{ibasis}, capped at {cap:.2g} A by what the pass element(s) can dissipate"
            I_ = round(cap, 3)
        V_ = b.volts(rin) if rin not in b.g else b.volts(rout)
        P_ = round(I_ ** 2 * p['ron'], 4)
        evs = [ev('topology', f"{p['class'].replace('_', ' ')}: {', '.join(p['switches'])} from '{b.short(rin)}' to '{b.short(rout)}'", STRONG)]
        if p.get('drive'):
            evs.append(ev('topology', f"gate drive: {p['drive']}", WEAK))
        if not caps_in or not caps_out:
            evs.append(ev('topology', 'no capacitor on one side: the loop closes off the board', -1.0))
        if p['group']:
            evs.append(ev('topology', f"one of several paths into '{b.short(rout)}' (group {p['group']})", 0.0))
        pid = f"path:{'+'.join(p['switches'][:3])}" + (f":{b.short(rin)}" if p['ic'] and p['group'] else '')
        out_s.append(_struct('power_path', pid, evs, conf_cap=0.9, prior=0.5,
                             **{'class': p['class'], 'switches': p['switches'], 'stages': p['stages'], 'controller': p['controller'],
                                'rail_in': rin, 'rail_out': rout, 'gnd': gnd, 'series': series, 'caps_in': caps_in[:4],
                                'caps_out': caps_out[:4], 'loop': loop, 'group': p['group'],
                                'excite': {'V': V_, 'I': I_, 'basis': [ibasis], 'I_belief': belief(I_, 'A', ibasis, round(I_ / 3, 3), I_)},
                                'R_on_ohm': {'value': round(p['ron'], 6), 'unit': 'ohm', 'class': 'E5', 'basis': p['ron_basis']},
                                'P_W': P_}))
        for st_ in p['stages']:
            for q in st_:
                r1, rbasis = (p['ron'], p['ron_basis']) if p['ic'] else _fet_ron(b, q)
                Pq = round((I_ / len(st_)) ** 2 * r1, 4)
                if Pq >= 0.05:
                    basis = f"(I/n)^2 x R_on: I {I_:g} A ({ibasis}) over {len(st_)} parallel, {rbasis}"
                    heat_s.append(_struct('heat_source', f"heat:{q}", [ev('derived', basis, MODERATE)], conf_cap=0.6, prior=0.0,
                                          part=q, P_W=Pq, P_W_belief={'value': Pq, 'unit': 'W', 'class': 'E5', 'basis': basis,
                                                                      'interval': [round(Pq / 9, 4), round(Pq, 4)]}))
    return out_s, heat_s
