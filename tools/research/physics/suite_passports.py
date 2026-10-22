# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Conductor passports for any routed board: inferred roles, per-rail DC passports, HF hot loops.

Suite version of rb_board_passports.py (which is tuned for one motor-drive board). It imports that
script's parser, DC network, terminals and HF hot-loop model and adds:

  1. Role inference for general boards, each role with its evidence and a confidence
     (high / medium / low), written to the JSON and, early, to --roles-out (read by pc_refplane.py):
       ground net(s)     name (GND_RE), copper area, capacitor and IC ground-pin connections;
       power rails       name (PWR_RE), pins typed power_out / power_in in the board file, regulator
                         outputs, inductor outputs, non-ground pours, capacitors to ground; control
                         and signal names (FB, EN, ...) count against;
       sources per rail  regulator outputs (power_out pins, regulator-like parts) > inductor outputs >
                         series power-entry parts (fuse, diode, bead, jumper, low-ohm R) > supply
                         connectors (fewest nets first; battery holders); lower-priority candidates on a
                         rail that has a source become loads (exports);
       loads per rail    IC pins on the rail (power_in pins when typed), connectors that export it;
       decoupling caps   2-pin capacitors between a rail and a ground net, with pin assignment and
                         distance to the nearest load pin;
       switching cells   IC + inductor (switch node), integrated bridge drivers with shunts (the logic of
                         rb_board_passports.infer_roles), discrete half-bridges (two transistors sharing a
                         node, one on a rail, one on ground or a shunt);
       shunts            2-pin resistors with 0 < R <= 0.2 ohm.
  2. Per rail, a DC passport on one sparse factorization shared by all rails and the ground (each net
     rasterized on its own grid, grids coarsened to a node budget): per-load supply-path resistance
     (rail copper) and ground-return resistance (load ground pins to source ground pins), the
     loss-equivalent resistance for all loads drawing equal shares, worst drop per ampere, peak
     current density, necks (1 mm tiles away from terminals holding a large share of the rail's
     resistance; exact leverage of the most loaded faces), via bottlenecks (one via carrying >= 50% of a
     load's current with exact leverage >= 0.8; exact removal cost by Woodbury), dead copper share, and
     the Beckmann floor R_B = R_s W1^2 / A for rails with a pour (avoidable fraction <= 1 - R_B / R).
  3. Ground topology: per-layer ground islands, the vias that tie each to the rest, the parts whose
     ground pins sit on it; exposed pads of ICs without vias.
  4. Per switching cell, rb_board_passports.run_hf: loop inductance in the stack-local inductive-limit
     model (uncalibrated: shares, rankings and ratios only), image currents by layer and net, via shares,
     the best added ground via, the remove-plane and swap-plane counterfactuals.

Every stage runs inside try/except; a failure is recorded in the JSON ("errors", "coverage") with its
reason, and later stages still run where their inputs exist. The JSON is rewritten after each stage,
so a run killed by a timeout leaves the stages it finished.

Usage:
  python -I suite_passports.py BOARD.kicad_pcb --json OUT.json [--roles-out ROLES.json]
         [--max-nodes 300000] [--max-loads 12] [--max-rails 24] [--max-cells 3] [--budget-s 540] [--no-hf]
Deterministic. OMP_NUM_THREADS=1 is set here. Thresholds marked "screening" are defaults for counting
findings across a suite, not budgets.
"""
import os

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

import argparse  # noqa: E402
import contextlib  # noqa: E402
import io  # noqa: E402
import json  # noqa: E402
import math  # noqa: E402
import re  # noqa: E402
import resource  # noqa: E402
import sys  # noqa: E402
import time  # noqa: E402
import traceback  # noqa: E402
from collections import Counter, defaultdict  # noqa: E402
from types import SimpleNamespace  # noqa: E402

import numpy as np  # noqa: E402
import scipy.sparse as sp  # noqa: E402
import shapely  # noqa: E402
from scipy.sparse.csgraph import connected_components  # noqa: E402
from shapely.geometry import LineString, Point, Polygon  # noqa: E402
from shapely.ops import unary_union  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rb_board_passports as rb  # noqa: E402
from pc_refplane import PWR_RE as PC_PWR_RE  # noqa: E402

T_START = time.perf_counter()
GND_RE = rb.GND_RE
GND_ANY = re.compile(r'GND|VSS|EARTH|CHASSIS', re.I)     # ground-like names GND_RE misses (XADCGND, CHASSISGND)
SIG_TYPES = ('input', 'output', 'bidirectional', 'tri_state', 'open_collector', 'open_emitter')
PWR_RE = PC_PWR_RE                      # the critics' regex: name evidence for a rail
PWR_WEAK_RE = re.compile(r'VOUT|VREF|VDD|VCC|VBUS|VBAT|VIN|PWR|SUPPLY|BATT|\bV\d|^P\d+V\d*', re.I)
CTRL_RE = re.compile(r'(^|[^A-Z])(FB|VFB|BOOT|BST|BS|EN|ENABLE|COMP|SS|PG|PGOOD|ILIM|RT|CT|TRK|SENSE|SNS|ISNS|CS|'
                     r'XTAL|XI|XO|OSC|RST|RESET|NRST|ADC|AIN|SDA|SCL|TXD?|RXD?|LED|GATE|HO|LO|PWM|SIG|DATA|CLK|'
                     r'INT|IRQ|MISO|MOSI|SCK|CSN?|USB|D[PMN+-]|CC\d?|SBU\d?)([^A-Z]|$)', re.I)
SW_PIN_RE = re.compile(r'^(SW|LX|PH|PHASE|SW\d|LX\d|L\d|SWA|SWB)$', re.I)
OUT_PIN_RE = re.compile(r'^(V?OUT\d?|VO|OUTPUT|VREG|V_?OUT)$', re.I)
IN_PIN_RE = re.compile(r'^(P?VIN\d?|VCC|VDD|IN|VS|VBAT|PVDD|AVIN|VSUP|VSYS|V\+)$', re.I)
GND_PIN_RE = re.compile(r'^(P?GND\d?|AGND|DGND|VSS|EP|EPAD|PAD|GND_?EP|THERMAL|TAB|GNDA|GNDD|VSSA|0V)$', re.I)
REG_RE = re.compile(r'LDO|REG|1117|LM317|LM78|LM79|L78|L79|78[0-9]{2}|AP2[0-9]{3}|AP7[0-9]{3}|AP63|MCP1[67]\d\d|XC6[0-9]|'
                    r'RT9|RT8|TLV7|TLV1117|TPS7|TPS6|TPS5|TPS4|LM2|LMR|LMZ|MP1|MP2|MP8|SY8|AOZ|LT1|LT3|LTC3|LTM|ADP|NCP|NCV|'
                    r'MIC5|MIC29|MIC2|SPX|BD9|HT7|ME6|LP29|LP38|LP59|ISL8|MAX15|MAX17|MAX16|BUCK|BOOST|DCDC|DC-DC|PMIC|'
                    r'TPS|LM3671|AMS|R1[0-9]{3}|XL[0-9]{4}|SX1308|MT3608|ETA|SGM2|SGM6|RP[0-9]{3}|NCP1|LD39|LD29|ST1S|'
                    r'IRM|RAC|TSR|VXO|R-78|TMR|TEN', re.I)
BEAD_RE = re.compile(r'bead|ferrite|BLM|MPZ|BK\d|HZ\d|FBMH|ohm@|Ω@|R@|@100', re.I)
ACTIVE_PFX = {'U', 'IC', 'MOD', 'M', 'A', 'PS', 'VR', 'REG', 'MCU', 'IC_', 'DA', 'DD', 'AR', 'N'}
CONN_PFX = {'J', 'P', 'X', 'CN', 'CON', 'USB', 'BT', 'TB', 'XS', 'XP', 'JK', 'PWR', 'BAT', 'H'}
SERIES_PFX = {'F', 'FB', 'D', 'JP', 'L', 'R', 'FUSE', 'PTC', 'FL', 'E', 'SJ', 'NT'}


# ============================================================================ small helpers
def now():
    return time.perf_counter() - T_START


def log(msg=""):
    print(msg, flush=True)


def pfx(ref):
    m = re.match(r'[A-Za-z_]+', ref or '')
    return m.group(0).upper().rstrip('_') if m else ''


def short(net):
    return (net or '').split('/')[-1] or (net or '')


def jsonable(x):
    """Convert numpy, inf/nan and tuples for json.dump."""
    if isinstance(x, dict):
        return {str(k): jsonable(v) for k, v in x.items()}
    if isinstance(x, (list, tuple, set)):
        return [jsonable(v) for v in x]
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, (np.floating, float)):
        v = float(x)
        if math.isnan(v):
            return None
        if math.isinf(v):
            return 'inf' if v > 0 else '-inf'
        return v
    if isinstance(x, np.ndarray):
        return jsonable(x.tolist())
    if isinstance(x, (np.bool_,)):
        return bool(x)
    return x


def rnd(v, k=4):
    if v is None:
        return None
    try:
        v = float(v)
    except (TypeError, ValueError):
        return v
    if not math.isfinite(v):
        return v
    if v == 0:
        return 0.0
    return float(f"{v:.{k}g}")


def parse_value(val, unit):
    """Value in SI from a footprint value field: unit 'F' (capacitance) or 'H' (inductance).

    Accepts '10u', '100nF', '4.7uF/25V', '1µF', '2u2', '10uH', '0.1', '22u 6.3V'. Returns None if unreadable."""
    if not val:
        return None
    v = val.replace('µ', 'u').replace('μ', 'u')
    mult = {'p': 1e-12, 'n': 1e-9, 'u': 1e-6, 'm': 1e-3}
    m = re.search(r'(?<![\w.])(\d+)([pnum])(\d+)(?![\w.])', v)          # 2u2, 4n7
    if m:
        return float(f"{m.group(1)}.{m.group(3)}") * mult[m.group(2)]
    m = re.search(r'(?<![\w.])(\d+(?:\.\d+)?)\s*([pnum])' + unit + r'?(?![a-zA-Z])', v)
    if m:
        return float(m.group(1)) * mult[m.group(2)]
    m = re.search(r'(?<![\w.])(\d+(?:\.\d+)?)\s*' + unit + r'(?![a-zA-Z])', v)
    if m:
        return float(m.group(1))
    if unit == 'F':
        m = re.fullmatch(r'\s*(0?\.\d+|\d+(?:\.\d+)?)\s*', v)
        if m and float(m.group(1)) < 1:                                   # bare "0.1" means uF by convention
            return float(m.group(1)) * 1e-6
    return None


PKG_RE = re.compile(r'(?<![\d.])[RCL]?(0201|0402|0603|0805|1206|1210|1812|2010|2512)(?!\d)', re.I)


def ohms(val):
    """rb.parse_ohms after removing package codes ('10k/R0402' would otherwise read as 0.0402 ohm)."""
    return rb.parse_ohms(PKG_RE.sub(' ', val or ''))


def parse_volts(net):
    """Nominal voltage from a rail name ('+3V3', '5V', 'VCC_12V', '+1.8V'); None if absent."""
    n = short(net)
    m = re.search(r'(\d+)V(\d+)', n, re.I)
    if m:
        return float(f"{m.group(1)}.{m.group(2)}")
    m = re.search(r'(\d+(?:\.\d+)?)V(?![A-Z0-9])', n, re.I)
    if m:
        return float(m.group(1))
    return None


# ============================================================================ board with per-net indexes
class SBoard(rb.KBoard):
    """KBoard with per-net indexes: same copper() and fill_report() semantics, fast on large boards."""

    def __init__(self, path):
        super().__init__(path)
        self.t_by, self.p_by, self.v_by, self.z_by = (defaultdict(list) for _ in range(4))
        for t in self.tracks:
            self.t_by[t['net']].append(t)
        for p in self.pads:
            self.p_by[p['net']].append(p)
        for v in self.vias:
            self.v_by[v['net']].append(v)
        for zi, z in enumerate(self.zones):
            self.z_by[z['net']].append(zi)
        self.fill_approx = {}
        if self.outline is not None and self.pads:
            inside = shapely.contains_xy(self.outline, np.array([p['x'] for p in self.pads]), np.array([p['y'] for p in self.pads]))
            if inside.mean() < 0.8:      # the largest closed Edge.Cuts face is a cut-out: the real outline is open
                self.outline = None
                self.outline_note = f'Edge.Cuts face holds only {100 * inside.mean():.0f}% of the pads'
        if self.outline is None:
            parts = [g for z in self.zones for g in z['fills'].values()]
            parts += [p['poly'] for p in self.pads]
            parts += [LineString(t['pts']).buffer(t['w'] / 2) for t in self.tracks[:20000]]
            env = unary_union(parts).envelope if parts else Polygon()
            self.outline_src = 'envelope of copper (' + getattr(self, 'outline_note', 'no closed Edge.Cuts') + ')'
            self.outline = env if not env.is_empty else None
        else:
            self.outline_src = 'Edge.Cuts'

    def fill_report(self):
        lines, self.fill_approx = [], {}
        by_layer = {}
        for ly in self.cu:
            geoms, nets = [], []
            for t in self.tracks:
                if t['layer'] == ly:
                    geoms.append(LineString(t['pts']).buffer(t['w'] / 2, quad_segs=4))
                    nets.append(t['net'])
            for p in self.pads:
                if ly in p['layers']:
                    geoms.append(p['poly'])
                    nets.append(p['net'])
            for v in self.vias:
                if ly in v['layers']:
                    geoms.append(Point(v['x'], v['y']).buffer(v['size'] / 2, quad_segs=6))
                    nets.append(v['net'])
            by_layer[ly] = (np.array(geoms, dtype=object), np.array(nets, dtype=object),
                            shapely.STRtree(geoms) if geoms else None)
        for zi, z in enumerate(self.zones):
            for ly in z['layers']:
                geoms, nets, tree = by_layer.get(ly, (None, None, None))
                if ly in z['fills']:
                    f = z['fills'][ly]
                    ov = 0.0
                    if tree is not None and not f.is_empty:
                        idx = tree.query(f, predicate='intersects')
                        idx = idx[nets[idx] != z['net']]
                        if len(idx):
                            ov = float(shapely.area(shapely.intersection(geoms[idx], f)).sum())
                    tag = 'saved fill' + (f'; OVERLAPS other-net copper by {ov:.2f} mm2 (stale fill?)' if ov > 0.02 else '')
                    lines.append((z['net'], ly, z['outline'].area, f.area, tag))
                else:
                    g = z['outline']
                    if self.outline is not None:
                        g = g.intersection(self.outline)
                    if tree is not None and not g.is_empty:
                        idx = tree.query(g, predicate='intersects')
                        idx = idx[nets[idx] != z['net']]
                        if len(idx):
                            g = g.difference(unary_union(list(geoms[idx])).buffer(z['clearance']))
                    self.fill_approx[(zi, ly)] = g
                    lines.append((z['net'], ly, z['outline'].area, g.area, 'NO saved fill: outline minus clearance (approx.)'))
        return lines

    def copper(self, net, layer):
        key = (net, layer)
        if key in self._geo:
            return self._geo[key]
        parts = []
        for zi in self.z_by.get(net, ()):
            z = self.zones[zi]
            if layer in z['layers']:
                if layer in z['fills']:
                    parts.append(z['fills'][layer])
                elif (zi, layer) in self.fill_approx:
                    parts.append(self.fill_approx[(zi, layer)])
        parts += [LineString(t['pts']).buffer(t['w'] / 2, quad_segs=4) for t in self.t_by.get(net, ()) if t['layer'] == layer]
        base = unary_union(parts) if parts else Polygon()
        end = (self.cu[0], self.cu[-1])
        extra = []
        for p in self.p_by.get(net, ()):
            if layer in p['layers'] and (p['kind'] != 'thru_hole' or layer in end or base.intersects(p['poly'])):
                extra.append(p['poly'])
        for v in self.v_by.get(net, ()):
            if layer in v['layers']:
                c = Point(v['x'], v['y']).buffer(v['size'] / 2, quad_segs=6)
                if layer in (v['layers'][0], v['layers'][-1]) or base.intersects(c):
                    extra.append(c)
        g = unary_union([base] + extra) if extra else base
        self._geo[key] = g
        return g

    def area_est(self):
        """Cheap copper area (mm2, all layers, overlaps counted twice) and conductor length per net."""
        A, Lp = defaultdict(float), defaultdict(float)
        for z in self.zones:
            for ly, g in z['fills'].items():
                A[z['net']] += g.area
                Lp[z['net']] += g.length
        for t in self.tracks:
            ln = LineString(t['pts']).length
            A[t['net']] += ln * t['w']
            Lp[t['net']] += 2 * ln
        for p in self.pads:
            A[p['net']] += p['poly'].area * max(1, len(p['layers']) if p['kind'] == 'thru_hole' else 1)
            Lp[p['net']] += p['poly'].length
        for v in self.vias:
            A[v['net']] += math.pi * v['size'] ** 2 / 4 * 2
        A.pop(None, None)
        Lp.pop(None, None)
        return A, Lp


# ============================================================================ role inference
def is_cap(f):
    p = pfx(f['ref'])
    return len(f['pads']) == 2 and (p == 'C' or re.search(r'(^|:)C_|Capacitor', f['lib'] or '') is not None
                                    or (p[:1] == 'C' and p not in ('CN', 'CON', 'CONN', 'CR', 'CJ')
                                        and parse_value(f['value'], 'F') is not None))


def is_res(f):
    p = pfx(f['ref'])
    return len(f['pads']) == 2 and (p == 'R' or re.search(r'(^|:)R_|Resistor', f['lib'] or '') is not None
                                    or (p[:1] == 'R' and p not in ('RV', 'RT', 'RN', 'RLY', 'RL')
                                        and ohms(f['value']) is not None))


def is_ind(f):
    p = pfx(f['ref'])
    return len(f['pads']) == 2 and (p in ('L', 'FB') or re.search(r'(^|:)L_|Inductor|Ferrite', f['lib'] or '') is not None
                                    or (p[:1] == 'L' and p not in ('LED', 'LD', 'LS') and parse_value(f['value'], 'H') is not None))


def diode_side(f, net):
    """'A' or 'K' for the pad of diode f on net (pin function, else KiCad's pad 1 = cathode); None if unknown."""
    for p in f['pads']:
        if p['net'] == net:
            fn = (p.get('pinfunction') or '').strip().upper()
            if fn in ('A', 'ANODE', 'A1', 'A2'):
                return 'A'
            if fn in ('K', 'C', 'CATHODE', 'K1', 'K2'):
                return 'K'
            if p['num'] in ('1', '2') and re.search(r'(^|:)D_|Diode|SOD|SMA|SMB|SMC|DO-', f['lib'] or ''):
                return 'K' if p['num'] == '1' else 'A'
    return None


def is_bead(f):
    return pfx(f['ref']) == 'FB' or BEAD_RE.search((f['value'] or '') + ' ' + (f['lib'] or '')) is not None


def is_conn(f):
    p = pfx(f['ref'])
    return (p in CONN_PFX and not p.startswith('PS') and not (p == 'H' and len(f['pads']) <= 1)) \
        or re.search(r'Connector|BarrelJack|DC_?Jack|USB|TerminalBlock|Battery|PinHeader|PinSocket', f['lib'] or '') is not None


def is_active(f):
    p = pfx(f['ref'])
    return (p in ACTIVE_PFX and len(f['pads']) >= 3) or (p == 'U')


def infer_roles_general(b):
    """Roles for any board, with evidence and confidence. Returns (roles, log lines)."""
    L = []
    A, Lp = b.area_est()
    nets = sorted(set(A) | {p['net'] for p in b.pads if p['net']})
    fps = b.fps
    pads_by_net = b.p_by
    netset_of = {id(f): {p['net'] for p in f['pads'] if p['net']} for f in fps}

    # ---- ground
    def cap_other_counts(n):
        return sum(1 for f in fps if is_cap(f) and n in netset_of[id(f)] and len(netset_of[id(f)]) == 2)
    gnd_pin_count = Counter(p['net'] for p in b.pads if p['net'] and GND_PIN_RE.match((p.get('pinfunction') or '').strip()))
    strict = [n for n in nets if GND_RE.search(n) and not n.lower().startswith('unconnected')]
    loose = [n for n in nets if n not in strict and GND_ANY.search(short(n)) and not n.lower().startswith('unconnected')]
    gcands = strict + loose
    gscore = {n: cap_other_counts(n) + gnd_pin_count[n] + A.get(n, 0) / 100.0 for n in gcands}
    ground = {}
    if gcands:
        primary = max(strict or loose, key=lambda n: gscore[n])
        largest = max(nets, key=lambda n: A.get(n, 0))
        conf = 'high' if (primary == largest or cap_other_counts(primary) >= 2) else 'medium'
        ground[primary] = dict(confidence=conf, primary=True, evidence=[
            'name matches GND_RE', f'copper {A.get(primary, 0):.0f} mm2' + (' (largest net)' if primary == largest else ''),
            f'{cap_other_counts(primary)} capacitors', f'{gnd_pin_count[primary]} pins named like ground'])
        for n in gcands:
            if n != primary and len(pads_by_net.get(n, ())) >= 2:
                ground[n] = dict(confidence='medium' if (cap_other_counts(n) or gnd_pin_count[n]) else 'low', primary=False,
                                 evidence=['name matches GND_RE' if n in strict else 'name contains GND/VSS/EARTH/CHASSIS',
                                           f'copper {A.get(n, 0):.0f} mm2', f'{cap_other_counts(n)} capacitors'])
    else:
        # no ground name: the net with the most capacitor connections among the three largest nets, if it has some
        big = sorted(nets, key=lambda n: -A.get(n, 0))[:3]
        if big:
            primary = max(big, key=lambda n: (cap_other_counts(n) + gnd_pin_count[n], A.get(n, 0)))
            if cap_other_counts(primary) + gnd_pin_count[primary] >= 2:
                ground[primary] = dict(confidence='low', primary=True, evidence=[
                    'no net name matches GND_RE', f'largest-copper net with most capacitor connections ({cap_other_counts(primary)})'])
    gnds = set(ground)
    gnd = next((n for n, r in ground.items() if r['primary']), None)
    L.append("ground: " + (", ".join(f"'{n}' ({r['confidence']}; {'; '.join(r['evidence'])})" for n, r in ground.items()) or 'none found'))

    # ---- shunts and inductors
    shunts = []
    for f in fps:
        if is_res(f):
            ohm = ohms(f['value'])
            nn = [p['net'] for p in f['pads']]
            if ohm is not None and 0 < ohm <= 0.2 and all(nn) and nn[0] != nn[1]:
                shunts.append(dict(ref=f['ref'], ohm=ohm, nets=nn, fp=f))
    shunt_nets = {n for s in shunts for n in s['nets']}
    conn_nets_all = {p['net'] for g in fps if is_conn(g) for p in g['pads'] if p['net']}

    def one_sided(f):          # shunts this part touches on one side only, whose other side reaches a connector (a bridge
        out = []               # output to an off-board load, not a sense amplifier or a resistor between stacked domains)
        for s in shunts:
            touch = set(s['nets']) & netset_of[id(f)]
            if len(touch) == 1 and (set(s['nets']) - touch) & conn_nets_all:
                out.append(s)
        return out
    bridge_phase = set()
    for f in fps:
        if is_active(f) and len(one_sided(f)) >= 2:
            for s in one_sided(f):
                bridge_phase |= set(s['nets'])

    # ---- rail evidence
    caps_to_gnd = defaultdict(list)       # rail -> [(cap fp, rail pad, gnd pad)]
    for f in fps:
        if is_cap(f):
            n0, n1 = f['pads'][0]['net'], f['pads'][1]['net']
            if n0 and n1 and n0 != n1:
                if n1 in gnds and n0 not in gnds:
                    caps_to_gnd[n0].append((f, f['pads'][0], f['pads'][1]))
                elif n0 in gnds and n1 not in gnds:
                    caps_to_gnd[n1].append((f, f['pads'][1], f['pads'][0]))
    pour_area = defaultdict(float)
    for z in b.zones:
        pour_area[z['net']] += sum(g.area for g in z['fills'].values())
    act = [f for f in fps if is_active(f)]
    regs = [f for f in act if REG_RE.search((f['value'] or '') + ' ' + (f['lib'] or ''))]
    # switch nodes: an inductor (not a bead, >= 0.2 uH or unreadable) with one side on an active part's pin
    cells_sw = []
    for f in fps:
        if not is_ind(f) or is_bead(f):
            continue
        hv = parse_value(f['value'], 'H')
        if hv is not None and hv < 0.2e-6:
            continue
        nn = [p['net'] for p in f['pads']]
        if not all(nn) or nn[0] == nn[1] or any(n in gnds for n in nn):
            continue
        best = None
        for k in (0, 1):
            sw, other = nn[k], nn[1 - k]
            ics = [g for g in act if any(p['net'] == sw for p in g['pads'])]
            if not ics:
                continue
            swpin = [p for g in ics for p in g['pads'] if p['net'] == sw and SW_PIN_RE.match((p.get('pinfunction') or '').strip())]
            # an IC power-input pin on the candidate node means it is a filtered rail, not a switch node
            pin_in = sum(1 for g in ics for p in g['pads'] if p['net'] == sw and (p.get('pintype') or '').startswith('power_in'))
            score = 3 * bool(swpin) - 2 * (pin_in > 0 and not swpin) - 2 * bool(PWR_RE.search(short(sw))) \
                - len(caps_to_gnd.get(sw, ())) + (1 if (PWR_RE.search(short(other)) or caps_to_gnd.get(other)) else 0)
            ic = (swpin[0]['fp'] if swpin else max(ics, key=lambda g: sum(p['net'] == sw for p in g['pads'])))
            if best is None or score > best[0]:
                best = (score, sw, other, ic, bool(swpin))
        if best and best[0] >= 0:
            cells_sw.append(dict(L=f, sw=best[1], out=best[2], ic=best[3], sw_pin_named=best[4], score=best[0]))
    sw_nets = {c['sw'] for c in cells_sw} | bridge_phase

    def feat(n):
        ps = pads_by_net.get(n, ())
        pin_out = [p for p in ps if (p.get('pintype') or '').startswith('power_out')]
        pin_in = [p for p in ps if (p.get('pintype') or '').startswith('power_in') and is_active(p['fp'])]
        reg_out = [p for p in ps if p['fp'] in regs and OUT_PIN_RE.match((p.get('pinfunction') or '').strip())]
        ind_out = [c for c in cells_sw if c['out'] == n]
        ic_pins = [p for p in ps if is_active(p['fp'])]
        sig = [p for p in ic_pins if (p.get('pintype') or '').split('+')[0] in SIG_TYPES]
        conns = {p['ref'] for p in ps if is_conn(p['fp']) and netset_of[id(p['fp'])] & gnds}
        wmax = max((t['w'] for t in b.t_by.get(n, ())), default=0.0)
        return dict(name=bool(PWR_RE.search(short(n))), weak_name=bool(PWR_WEAK_RE.search(short(n))),
                    ctrl=bool(CTRL_RE.search(short(n))), pin_out=pin_out, pin_in=pin_in, reg_out=reg_out, ind_out=ind_out,
                    ncaps=len(caps_to_gnd.get(n, ())), pour=pour_area.get(n, 0.0), ic_pins=ic_pins, npads=len(ps),
                    sig=sig, conns=conns, wmax=wmax)
    rails, rejected = {}, {}
    for n in nets:
        if n in gnds or n in sw_nets or n.lower().startswith('unconnected') or GND_ANY.search(short(n)):
            continue
        F = feat(n)
        ev, score = [], 0
        if F['name']:
            score += 2
            ev.append('name matches PWR_RE')
        elif F['weak_name']:
            score += 1
            ev.append('name contains a supply word')
        if F['pin_out'] or F['reg_out']:
            score += 3
            ev.append(f"{len(F['pin_out']) or len(F['reg_out'])} power_out/regulator-output pin(s) "
                      f"({', '.join(sorted({p['ref'] for p in (F['pin_out'] or F['reg_out'])}))})")
        if F['ind_out']:
            score += 3
            ev.append('output of inductor ' + ', '.join(c['L']['ref'] for c in F['ind_out']))
        if F['pin_in']:
            score += 2
            ev.append(f"{len(F['pin_in'])} power_in pin(s) on {len({p['ref'] for p in F['pin_in']})} part(s)")
        if F['ncaps']:
            score += min(F['ncaps'], 3)
            ev.append(f"{F['ncaps']} capacitor(s) to ground")
        if F['pour'] > 1.0:
            score += 2
            ev.append(f"pour {F['pour']:.0f} mm2")
        if len({p['ref'] for p in F['ic_pins']}) >= 2:
            score += 1
            ev.append(f"pins on {len({p['ref'] for p in F['ic_pins']})} ICs")
        if F['conns'] and (F['name'] or F['weak_name']):
            score += 1
            ev.append(f"on {len(F['conns'])} connector(s) with ground pins")
        if F['wmax'] >= 0.5:
            score += 1
            ev.append(f"tracks up to {F['wmax']:.2f} mm wide")
        powered = F['pin_out'] or F['reg_out'] or F['ind_out'] or F['pin_in']
        counter = []
        if F['ctrl'] and not (F['pin_out'] or F['reg_out'] or F['ind_out'] or F['name']):
            score -= 4
            counter.append('control/signal name (FB, EN, data, ...)')
        if F['sig'] and not powered:
            score -= 3
            counter.append(f"{len(F['sig'])} IC pin(s) typed as signals ({F['sig'][0]['pintype']}) and none typed power")
        if F['npads'] <= 2 and F['pour'] <= 1.0 and not (F['pin_out'] or F['reg_out']):
            score -= 2
            counter.append('two pads or fewer and no pour')
        ev += [c + ': counts against' for c in counter]
        strong = F['name'] or powered or F['ncaps'] >= 2 or F['pour'] > 1.0
        if not strong:
            continue
        conf = 'high' if score >= 6 else 'medium' if score >= 3 else 'low'
        if conf == 'low' and (F['name'] or F['weak_name']) and counter:
            rejected[n] = f"counter-evidence (score {score}): " + '; '.join(counter)
        rails[n] = dict(confidence=conf, score=score, evidence=ev, volts=parse_volts(n))
    # regex power names that are switch nodes
    for n in nets:
        if n not in rails and n not in gnds and PWR_RE.search(short(n)) and n not in rejected and n in sw_nets:
            rejected[n] = 'switch node'
    L.append(f"power rails: {sum(r['confidence'] == 'high' for r in rails.values())} high, "
             f"{sum(r['confidence'] == 'medium' for r in rails.values())} medium, {sum(r['confidence'] == 'low' for r in rails.values())} low"
             f" confidence; name-matched nets rejected: {len(rejected)}")
    for n, r in sorted(rails.items(), key=lambda t: -t[1]['score']):
        L.append(f"  rail '{n}' ({r['confidence']}, score {r['score']}): " + '; '.join(r['evidence']))
    for n, why in rejected.items():
        L.append(f"  not a rail: '{n}': {why}")

    # ---- sources and loads per rail
    def gpads(f, gset=None):
        gset = gset or gnds
        return [p for p in f['pads'] if p['net'] in gset]

    def conn_nets(f):
        return len(netset_of[id(f)])
    live = [n for n, r in rails.items() if r['confidence'] != 'low']

    def primary_sources(n):
        F = feat(n)
        srcs = []
        outs = F['pin_out'] or F['reg_out']
        for ref in sorted({p['ref'] for p in outs}):
            f = next(p['fp'] for p in outs if p['ref'] == ref)
            srcs.append(dict(kind='regulator_output', ref=ref, value=f['value'], pads=[p for p in outs if p['ref'] == ref],
                             gnd_pads=gpads(f), confidence='high' if F['pin_out'] else 'medium',
                             evidence='pin typed power_out' if F['pin_out'] else 'regulator-like part, output pin name'))
        for c in F['ind_out']:
            lp = next(p for p in c['L']['pads'] if p['net'] == n)
            srcs.append(dict(kind='inductor_output', ref=c['L']['ref'], value=c['L']['value'], pads=[lp],
                             gnd_pads=gpads(c['ic']), confidence='high' if c['sw_pin_named'] else 'medium',
                             evidence=f"inductor driven by {c['ic']['ref']} (switch node '{short(c['sw'])}')"))
        if not srcs:   # regulator-like part with a pin on the rail and a pin on another rail, no typed output
            for f in regs:
                fp_nets = netset_of[id(f)]
                if n in fp_nets and (fp_nets & set(rails)) - {n} and fp_nets & gnds:
                    rp = [p for p in f['pads'] if p['net'] == n]
                    if rp and not any(IN_PIN_RE.match((p.get('pinfunction') or '').strip()) for p in rp) \
                            and not any((p.get('pintype') or '').startswith('power_in') for p in rp):
                        srcs.append(dict(kind='regulator_output', ref=f['ref'], value=f['value'], pads=rp, gnd_pads=gpads(f),
                                         confidence='low', evidence='regulator-like part between two rails (pin roles untyped)'))
        conns = [f for f in fps if is_conn(f) and n in netset_of[id(f)] and netset_of[id(f)] & gnds]
        if not srcs:
            for f in conns:
                if pfx(f['ref']) in ('BT', 'BAT') or 'Battery' in (f['lib'] or ''):
                    srcs.append(dict(kind='supply_connector', ref=f['ref'], value=f['value'],
                                     pads=[p for p in f['pads'] if p['net'] == n], gnd_pads=gpads(f), confidence='high',
                                     evidence='battery holder'))
        if not srcs:
            few = sorted((f for f in conns if conn_nets(f) <= 6), key=lambda f: (conn_nets(f), f['ref']))
            if few:
                f = few[0]
                srcs.append(dict(kind='supply_connector', ref=f['ref'], value=f['value'], pads=[p for p in f['pads'] if p['net'] == n],
                                 gnd_pads=gpads(f), confidence='medium',
                                 evidence=f"connector with rail and ground pins ({conn_nets(f)} nets)"))
        return srcs

    def series_parts(n):
        """2-pin series parts from rail n to another non-ground net o, oriented: a diode feeds only its cathode net."""
        out = []
        for f in fps:
            if len(f['pads']) != 2 or pfx(f['ref']) not in SERIES_PFX or is_cap(f):
                continue
            nn = [p['net'] for p in f['pads']]
            if n not in nn or nn[0] == nn[1]:
                continue
            o = nn[1 - nn.index(n)]
            if o is None or o in gnds or o in sw_nets:
                continue
            if is_res(f):
                ohm = ohms(f['value'])
                if ohm is None or ohm > 1.0:
                    continue
            if pfx(f['ref']) == 'D' and diode_side(f, n) == 'A':
                continue
            if pfx(f['ref']) == 'L' and not is_bead(f) and o not in rails:
                continue
            out.append((f, o))
        return out
    srcmap = {n: primary_sources(n) for n in live}
    for _ in range(4):         # propagate through series parts from rails (or connector nets) that have a source
        changed = False
        for n in live:
            if srcmap[n]:
                continue
            for f, o in series_parts(n):
                cn = [g for g in fps if is_conn(g) and o in netset_of[id(g)] and netset_of[id(g)] & gnds]
                if srcmap.get(o) or cn:
                    up_src = srcmap[o][0] if srcmap.get(o) else None
                    gp = up_src['gnd_pads'] if up_src else gpads(min(cn, key=conn_nets))
                    srcmap[n] = [dict(kind='power_entry_series', ref=f['ref'], value=f['value'],
                                      pads=[p for p in f['pads'] if p['net'] == n], gnd_pads=gp, upstream=o, confidence='medium',
                                      evidence=f"series part {f['ref']} ({f['value']}) from '{short(o)}'"
                                      + (f" (source {up_src['ref']})" if up_src else f" (connector {min(cn, key=conn_nets)['ref']})"))]
                    changed = True
                    break
        if not changed:
            break
    for n in live:             # last resort: a connector with many nets
        if not srcmap[n]:
            conns = [f for f in fps if is_conn(f) and n in netset_of[id(f)] and netset_of[id(f)] & gnds]
            if conns:
                f = min(conns, key=lambda f: (conn_nets(f), f['ref']))
                srcmap[n] = [dict(kind='supply_connector', ref=f['ref'], value=f['value'], pads=[p for p in f['pads'] if p['net'] == n],
                                  gnd_pads=gpads(f), confidence='low',
                                  evidence=f"only connector on the rail ({conn_nets(f)} nets): source or export, undecided")]
    for n in live:
        r = rails[n]
        srcs = srcmap[n]
        src_refs = {s['ref'] for s in srcs}
        loads = []
        for f in fps:
            if f['ref'] in src_refs:
                continue
            rp = [p for p in f['pads'] if p['net'] == n]
            if not rp:
                continue
            if is_active(f):
                typed = [p for p in rp if (p.get('pintype') or '').startswith('power_in')]
                loads.append(dict(kind='ic', ref=f['ref'], value=f['value'], pads=typed or rp, gnd_pads=gpads(f),
                                  typed=bool(typed)))
            elif is_conn(f):
                loads.append(dict(kind='connector_export', ref=f['ref'], value=f['value'], pads=rp, gnd_pads=gpads(f), typed=False))
        decaps = []
        for f, rp, gp_ in caps_to_gnd.get(n, ()):
            dmin, near = float('inf'), None
            for ld in loads:
                for p in ld['pads']:
                    d = math.hypot(p['x'] - rp['x'], p['y'] - rp['y'])
                    if d < dmin:
                        dmin, near = d, ld['ref']
            decaps.append(dict(ref=f['ref'], value=f['value'], farads=parse_value(f['value'], 'F'), rail_pad=rp['num'],
                               gnd_pad=gp_['num'], gnd_net=gp_['net'], nearest_load=near, dist_mm=dmin, fp=f, rp=rp, gp=gp_))
        r.update(sources=srcs, loads=loads, decaps=decaps)
    for n, r in rails.items():
        if 'sources' not in r:
            continue
        L.append(f"  '{n}': sources " + (', '.join(f"{s['ref']} [{s['kind']}, {s['confidence']}]" for s in r['sources']) or 'none')
                 + f"; {len(r['loads'])} loads ({sum(ld['kind'] == 'ic' for ld in r['loads'])} ICs, "
                 f"{sum(ld['typed'] for ld in r['loads'])} with typed power_in pins); {len(r['decaps'])} decoupling caps")

    # ---- switching cells
    cells = []
    for c in cells_sw:
        ic = c['ic']
        icnets = netset_of[id(ic)]
        cand = [n for n in icnets if n in rails and n not in (c['sw'], c['out'])]
        if not cand and c['out'] in rails and rails[c['out']]['confidence'] != 'low':
            cand = []
        def rank(n):
            ps = [p for p in ic['pads'] if p['net'] == n]
            return (any((p.get('pintype') or '').startswith('power_in') or IN_PIN_RE.match((p.get('pinfunction') or '').strip())
                        for p in ps), len(caps_to_gnd.get(n, ())), len(ps))
        vin = max(cand, key=rank) if cand else None
        gn = Counter(p['net'] for p in ic['pads'] if p['net'] in gnds).most_common(1)
        cells.append(dict(type='regulator+inductor', ref=ic['ref'], value=ic['value'], inductor=c['L']['ref'],
                          inductor_value=c['L']['value'], sw=c['sw'], out=c['out'], rail=vin, gnd=gn[0][0] if gn else gnd,
                          confidence='high' if c['sw_pin_named'] else 'medium',
                          evidence=(f"pin named like SW on {ic['ref']}" if c['sw_pin_named'] else f"{ic['ref']} pin on the inductor's node")
                          + (f"; hot-loop rail '{short(vin)}' (IC pin on a rail other than the switch node and the inductor output)"
                             if vin else '; no input rail pin found (boost with external diode?)'),
                          _ic=ic, _L=c['L']))
    # integrated bridge drivers with shunts: the rb_board_passports logic
    bridge = None
    if shunts:
        dcands = []
        for f in fps:
            if pfx(f['ref']) in ('U', 'Q', 'IC'):
                fn = netset_of[id(f)]
                k = len(one_sided(f))
                if k >= 2 and fn & set(rails) and gnd in fn:
                    dcands.append((k, sum(1 for p in f['pads'] if p['net'] in set(rails) | gnds), f))
        if dcands:
            drv = max(dcands, key=lambda t: (t[0], t[1]))[2]
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    rr, rl = rb.infer_roles(b, SimpleNamespace(driver=drv['ref']))
                bridge = rr
                cells.append(dict(type='bridge-driver', ref=drv['ref'], value=drv['value'], rail=rr['rail'], gnd=rr['gnd'],
                                  sw=None, out=None, inductor=None, confidence='medium',
                                  evidence=f"pads on {len(netset_of[id(drv)] & shunt_nets)} shunt nets (rb_board_passports.infer_roles)",
                                  _rb=rr))
                L.extend('  [rb] ' + x for x in rl)
            except (SystemExit, Exception) as e:        # noqa: BLE001  (rb raises SystemExit when it finds no rail)
                L.append(f"bridge driver {drv['ref']}: rb_board_passports.infer_roles failed: {e}")
    # discrete half-bridges
    qs = [f for f in fps if pfx(f['ref']) in ('Q', 'T', 'VT') and len(f['pads']) >= 3]
    seen = set()
    shunt_to_gnd = {s['nets'][k]: s for s in shunts for k in (0, 1) if s['nets'][1 - k] in gnds}
    live_rails = {n for n, r in rails.items() if r['confidence'] != 'low'}
    for X in sorted({p['net'] for q in qs for p in q['pads'] if p['net']} - gnds - live_rails):
        on = [q for q in qs if X in netset_of[id(q)]]
        if len(on) < 2:
            continue
        hi = [q for q in on if (netset_of[id(q)] - {X}) & live_rails]
        lo = [q for q in on if q not in hi and ((netset_of[id(q)] - {X}) & gnds or (netset_of[id(q)] - {X}) & set(shunt_to_gnd))]
        x_ind = any(is_ind(f) and not is_bead(f) for f in fps if X in netset_of[id(f)])
        x_conn = any(is_conn(f) for f in fps if X in netset_of[id(f)])
        big = max((p['poly'].area for q in on for p in q['pads']), default=0) >= 4.0
        if hi and lo and (x_ind or x_conn or big):      # not a logic gate: drives an inductor, a connector, or power packages
            qa, qb = hi[0], lo[0]
            key = (qa['ref'], qb['ref'])
            if key in seen:
                continue
            seen.add(key)
            rail = sorted((netset_of[id(qa)] - {X}) & live_rails)[0]
            cells.append(dict(type='half-bridge', ref=f"{qa['ref']}+{qb['ref']}", value=f"{qa['value']} / {qb['value']}",
                              rail=rail, gnd=gnd, sw=X, out=None, inductor=None, confidence='medium',
                              evidence=f"{qa['ref']} between '{short(rail)}' and '{short(X)}', {qb['ref']} between '{short(X)}' and ground"
                              + (" (through a shunt)" if not (netset_of[id(qb)] - {X}) & gnds else ''),
                              _qa=qa, _qb=qb))
    for c in cells:
        L.append(f"switching cell [{c['type']}, {c['confidence']}] {c['ref']} ({c['value']}): {c['evidence']}")
    L.append("shunts (0 < R <= 0.2 ohm): " + (', '.join(f"{s['ref']} {s['ohm'] * 1e3:.0f} mOhm '{short(s['nets'][0])}'-'{short(s['nets'][1])}'"
                                                       for s in shunts) or 'none'))
    roles = dict(gnd=gnd, ground=ground, rails=rails, rejected_power=rejected, cells=cells, shunts=shunts,
                 switch_nodes=sorted(sw_nets), area=A, perim=Lp, regs=[f['ref'] for f in regs], bridge=bridge)
    return roles, L


def roles_for_critics(roles):
    """The board-wide role inputs pc_refplane.py can use (--roles)."""
    return dict(
        tool='suite_passports', ground=sorted(roles['ground']),
        ground_confidence={n: r['confidence'] for n, r in roles['ground'].items()},
        power=sorted(n for n, r in roles['rails'].items() if r['confidence'] in ('high', 'medium')),
        power_confidence={n: r['confidence'] for n, r in roles['rails'].items()},
        rejected_power=roles['rejected_power'], switch_nodes=roles['switch_nodes'])


def roles_json(roles):
    def padref(ps):
        return [f"{p['ref']}.{p['num']}" for p in ps]
    rails = {}
    for n, r in roles['rails'].items():
        d = dict(confidence=r['confidence'], score=r['score'], evidence=r['evidence'], volts=r['volts'])
        if 'sources' in r:
            d['sources'] = [dict(kind=s['kind'], ref=s['ref'], value=s['value'], pads=padref(s['pads']), gnd_pads=padref(s['gnd_pads']),
                                 confidence=s['confidence'], evidence=s['evidence']) for s in r['sources']]
            d['loads'] = [dict(kind=ld['kind'], ref=ld['ref'], value=ld['value'], pads=padref(ld['pads']), typed_power_in=ld['typed'],
                               gnd_pads=padref(ld['gnd_pads'])) for ld in r['loads']]
            d['decaps'] = [dict(ref=c['ref'], value=c['value'], farads=c['farads'], rail_pad=c['rail_pad'], gnd_pad=c['gnd_pad'],
                                gnd_net=c['gnd_net'], nearest_load=c['nearest_load'], dist_mm=rnd(c['dist_mm']))
                           for c in r['decaps']]
        rails[n] = d
    return dict(ground=roles['ground'], rails=rails, rejected_power=roles['rejected_power'],
                switch_nodes=roles['switch_nodes'], regulators=roles['regs'],
                cells=[{k: v for k, v in c.items() if not k.startswith('_')} for c in roles['cells']],
                shunts=[dict(ref=s['ref'], ohm=s['ohm'], nets=s['nets']) for s in roles['shunts']])


# ============================================================================ DC passports
def choose_grids(nets, gnd, A, Lp, max_nodes):
    """Per-net grid (mm): rb's defaults (0.2 for ground and pours over 150 mm2, else 0.05-0.1), coarsened
    together until the estimated node count fits max_nodes."""
    h = {}
    for n in nets:
        a = A.get(n, 0.0)
        h[n] = 0.2 if (n == gnd or a > 150) else (0.05 if a < 40 else 0.1)

    def est(hh):
        return sum(A.get(n, 0) / hh[n] ** 2 + 1.5 * Lp.get(n, 0) / hh[n] for n in nets)
    e0 = est(h)
    s = 1.0
    while est({n: min(1.0, h[n] * s) for n in nets}) > max_nodes and s < 20:
        s *= 1.1
    return {n: min(1.0, h[n] * s) for n in nets}, e0


def rail_order(roles, max_rails):
    out = []
    for n, r in roles['rails'].items():
        if r['confidence'] == 'low' or not r.get('sources') or not r.get('loads'):
            continue
        out.append(n)
    out.sort(key=lambda n: ({'high': 0, 'medium': 1}[roles['rails'][n]['confidence']], -len(roles['rails'][n]['loads']),
                            -roles['area'].get(n, 0)))
    return out[:max_rails], out[max_rails:]


def run_dc(b, roles, args, res, errors):
    """Per-rail DC passports and ground topology on one factorization."""
    gnd = roles['gnd']
    rails_all, dropped = rail_order(roles, args.max_rails)
    out = dict(rails={}, ground={}, model={}, skipped_rails={})
    for n in dropped:
        out['skipped_rails'][n] = f'over --max-rails {args.max_rails}'
    for n, r in roles['rails'].items():
        if n not in rails_all and n not in dropped:
            why = ('low confidence' if r['confidence'] == 'low' else 'no source identified' if not r.get('sources')
                   else 'no load identified')
            out['skipped_rails'][n] = why
    nets = ([gnd] if gnd else []) + rails_all
    if not nets:
        out['status'] = 'skipped: no ground and no rail with a source and a load'
        return out, None
    t0 = now()
    hnet, est0 = choose_grids(nets, gnd, roles['area'], roles['perim'], args.max_nodes)
    N = rb.build_dc(b, nets, hnet, [])
    # COLAMD (rb's default): minimum degree on A'+A collapses on the terminals' high-degree electrode nodes
    # (100-400 s and > 4 GB on boards COLAMD factors in 1-3 s)
    N.permc = 'COLAMD'
    T = rb.Terminals(N, b)
    t_build = now() - t0
    # terminal groups (all created before the factorization)
    plan = {}
    bad_pads = []

    def group(name, pads):
        ok = []
        for p in pads:
            try:
                T.pad(p)
                ok.append(p)
            except ValueError as e:
                bad_pads.append(str(e))
        return T.group_of(name, ok) if ok else None
    for n in rails_all:
        r = roles['rails'][n]
        src_pads = [p for s in r['sources'] for p in s['pads']]
        sg = [p for s in r['sources'] for p in s['gnd_pads'] if p['net'] == gnd]
        src = group(f"{n}|src", src_pads)
        srcg = group(f"{n}|srcgnd", sg) if sg else None
        loads = []
        far = sorted(r['loads'], key=lambda ld: -min(math.hypot(p['x'] - q['x'], p['y'] - q['y'])
                                                     for p in ld['pads'] for q in src_pads))
        for ld in far[:args.max_loads]:
            node = group(f"{n}|load|{ld['ref']}", ld['pads'])
            lg = [p for p in ld['gnd_pads'] if p['net'] == gnd]
            gnode = group(f"gnd|{ld['ref']}", lg) if lg else None
            loads.append(dict(ld=ld, node=node, gnode=gnode))
        plan[n] = dict(src=src, srcg=srcg, loads=loads, nloads_total=len(r['loads']))
    N.finalize()
    N.factor()
    deg = np.bincount(np.r_[N.a, N.b], minlength=N.nn)
    out['model'] = dict(nodes=int(N.nn), branches=int(N.nb), components=int(N.ncomp), est_nodes_default_grid=int(est0),
                        max_degree=int(deg.max()), lu_nnz=int(sum(lu.L.nnz + lu.U.nnz for lu in N.lu.values())),
                        grids_mm={n: rnd(hnet[n], 3) for n in nets}, barrels=len(N.vias), t_build_s=rnd(t_build, 3),
                        t_factor_s=rnd(N.t_factor, 3), ordering=N.permc, pads_without_cells=len(bad_pads))
    log(f"\n== DC model: {N.nn} nodes, {N.nb} branches, {N.ncomp} components; grids "
        + ", ".join(f"{short(n)} {hnet[n]:.3g}" for n in nets) + f" mm; {len(N.vias)} barrels; build {t_build:.1f} s, "
        f"factor {N.t_factor:.1f} s")
    face = N.kind <= 1
    tcu = np.array([b.tcu.get(ly, 0.035) if ly in b.tcu else 0.035 for ly in N.lay])
    via_of_seg = {}
    for vi, v in enumerate(N.vias):
        for s_ in v['segs']:
            via_of_seg[s_] = vi
    nodeflow_rail = np.zeros(N.nn)
    nodeflow_gnd = np.zeros(N.nn)
    gnd_cols_done = 0
    keep_ib = {}
    cell_rails = {c['rail'] for c in roles['cells'] if c.get('rail')}
    for n in rails_all:
        if now() > args.budget_s * 0.6:
            out['skipped_rails'][n] = 'time budget'
            continue
        P = plan[n]
        rr = dict(confidence=roles['rails'][n]['confidence'], grid_mm=rnd(hnet[n], 3), loads_total=P['nloads_total'],
                  loads_modelled=0, per_load=[], notes=[])
        out['rails'][n] = rr
        try:
            if P['src'] is None:
                rr['status'] = 'skipped: source pads have no copper cells'
                continue
            cols, meta = [], []
            for L_ in P['loads']:
                if L_['node'] is None:
                    rr['notes'].append(f"load {L_['ld']['ref']}: pads have no copper cells")
                    continue
                if N.comp[L_['node']] != N.comp[P['src']]:
                    rr['notes'].append(f"load {L_['ld']['ref']}: not connected to the source through '{short(n)}' copper"
                                       " (path through a part, or a split net)")
                    continue
                s = np.zeros(N.nn)
                s[P['src']] += 1.0
                s[L_['node']] -= 1.0
                cols.append(s)
                meta.append(('rail', L_))
                if L_['gnode'] is not None and P['srcg'] is not None and N.comp[L_['gnode']] == N.comp[P['srcg']] \
                        and L_['gnode'] != P['srcg']:
                    s = np.zeros(N.nn)
                    s[L_['gnode']] += 1.0
                    s[P['srcg']] -= 1.0
                    cols.append(s)
                    meta.append(('gnd', L_))
            if not cols:
                rr['status'] = 'skipped: no load reachable through the rail copper'
                continue
            S = np.stack(cols, 1)
            Phi = N.solve(S)
            Ib = N.currents(Phi)
            Z = np.einsum('ij,ij->j', S, Phi)
            rc = [k for k, m in enumerate(meta) if m[0] == 'rail']
            gc = {id(meta[k][1]): k for k, m in enumerate(meta) if m[0] == 'gnd'}
            rr['loads_modelled'] = len(rc)
            for k in rc:
                L_ = meta[k][1]
                kg = gc.get(id(L_))
                rr['per_load'].append(dict(ref=L_['ld']['ref'], kind=L_['ld']['kind'], r_rail_mohm=rnd(Z[k] * 1e3),
                                           r_gnd_mohm=rnd(Z[kg] * 1e3) if kg is not None else None,
                                           r_loop_mohm=rnd((Z[k] + (Z[kg] if kg is not None else 0)) * 1e3)))
            # all loads drawing equal shares of 1 A
            sA = S[:, rc].mean(1)
            IbA = Ib[:, rc].mean(1)
            RA = float(sA @ Phi[:, rc].mean(1))
            gk = [gc[id(meta[k][1])] for k in rc if id(meta[k][1]) in gc]
            RAg = float(S[:, gk].mean(1) @ Phi[:, gk].mean(1)) if len(gk) == len(rc) and gk else None
            rr['r_eff_mohm'] = rnd(RA * 1e3)
            rr['r_eff_gnd_mohm'] = rnd(RAg * 1e3) if RAg is not None else None
            loops = [x['r_loop_mohm'] for x in rr['per_load'] if x['r_gnd_mohm'] is not None]
            rails_only = [x['r_rail_mohm'] for x in rr['per_load']]
            worst = max(rr['per_load'], key=lambda x: x['r_loop_mohm'])
            rr['worst_drop_mv_per_a'] = worst['r_loop_mohm']
            rr['worst_load'] = worst['ref']
            rr['worst_includes_ground'] = worst['r_gnd_mohm'] is not None
            rr['median_rail_mohm'] = rnd(float(np.median(rails_only)))
            rr['median_loop_mohm'] = rnd(float(np.median(loops))) if loops else None
            if n in cell_rails:
                keep_ib[n] = IbA + (Ib[:, gk].mean(1) if (len(gk) == len(rc) and gk) else 0)
            # current density and necks (all-loads pattern)
            fm = face & (N.net == n)
            if fm.any():
                J = np.abs(IbA[fm]) / np.maximum(N.w[fm] * tcu[fm], 1e-12)          # A/mm2 per A
                jm = int(np.argmax(J))
                lyr = N.lay[fm][jm]
                rr['j_peak_a_mm2_per_a'] = rnd(J[jm])
                rr['j_peak_at'] = [rnd(N.mx[fm][jm], 5), rnd(N.my[fm][jm], 5), lyr]
                rr['w_equiv_at_peak_mm'] = rnd(1.0 / (J[jm] * b.tcu.get(lyr, 0.035)))
                cu = (N.kind <= 3) & (N.net == n)
                loss = IbA[cu] ** 2 / N.g[cu]
                tot = float(loss.sum())
                key = np.floor(N.mx[cu]).astype(np.int64) * 1000003 + np.floor(N.my[cu]).astype(np.int64)
                u, inv = np.unique(key, return_inverse=True)
                acc = np.bincount(inv, weights=loss)
                order = np.argsort(-acc)[:5]
                term = unary_union([p['poly'] for s_ in roles['rails'][n]['sources'] for p in s_['pads']]
                                   + [p['poly'] for L_ in P['loads'] for p in L_['ld']['pads']])
                tiles = []
                for o in order:
                    tx, ty = int(u[o] // 1000003), int(u[o] % 1000003)
                    if acc[o] / tot < 0.05:
                        break
                    near_term = term.distance(Polygon([(tx, ty), (tx + 1, ty), (tx + 1, ty + 1), (tx, ty + 1)])) <= 0.5
                    sel = cu.copy()
                    sel[cu] = inv == o
                    lys = sorted(set(N.lay[sel]) - {'barrel'})
                    tiles.append(dict(tile=[tx, ty], share=rnd(acc[o] / tot, 3), at_terminal=bool(near_term), layers=lys,
                                      has_via=bool(np.any(N.kind[sel] >= 2))))
                rr['hot_tiles'] = tiles
                rr['necks'] = [t for t in tiles if not t['at_terminal'] and t['share'] >= args.neck_share]
                # exact leverage on the most loaded faces
                idx = np.nonzero(fm)[0]
                top = idx[np.argsort(-np.abs(IbA[idx]))[:args.lev_faces]]
                top = top[np.abs(IbA[top]) > 0.02]
                if len(top):
                    rho = N.g[top] * N.reff(top)
                    ser = top[rho > 0.9]
                    rr['series_faces'] = int(len(ser))
                    rr['series_faces_loss_share'] = rnd(float((IbA[ser] ** 2 / N.g[ser]).sum() / tot) if len(ser) else 0.0, 3)
                    rr['lev_median_top_faces'] = rnd(float(np.median(rho)), 3)
            # via bottlenecks: one via carrying >= 50% of the rail's (or its ground return's) total current, all loads on
            term_pads = [p for L_ in P['loads'] for p in L_['ld']['pads'] + L_['ld']['gnd_pads']] \
                + [p for s_ in roles['rails'][n]['sources'] for p in s_['pads'] + s_['gnd_pads']]
            term_ids = {id(p) for p in term_pads}
            gk_all = [k for k, m in enumerate(meta) if m[0] == 'gnd']
            pats = [('rail', n, IbA, Phi[:, rc].mean(1), RA)]
            if gk_all:
                pats.append(('gnd', gnd, Ib[:, gk_all].mean(1), Phi[:, gk_all].mean(1),
                             float(S[:, gk_all].mean(1) @ Phi[:, gk_all].mean(1))))
            vb = []
            for kind, net_, IbP, PhiP, RP in pats:
                for vi, v in enumerate(N.vias):
                    if not v['segs'] or v['net'] != net_ or (v['kind'] == 'pth' and id(v['src']) in term_ids):
                        continue
                    segs = np.array(v['segs'])
                    sh = float(np.abs(IbP[segs]).max())
                    if sh < 0.5:
                        continue
                    kmax = segs[np.argmax(np.abs(IbP[segs]))]
                    rho = float(N.g[kmax] * N.reff(np.array([kmax]))[0])
                    dz = N.woodbury(segs, PhiP, PhiP)
                    # the lstsq residual test misses near-singular cases: a sole path (rho ~ 1) disconnects
                    cut = (not np.isfinite(dz)) or rho >= 0.999 or (RP > 0 and abs(dz / RP) > 100)
                    vb.append(dict(column=kind, share=rnd(sh, 3), rho=rnd(rho, 3), kind=v['kind'],
                                   at=[rnd(v['x'], 5), rnd(v['y'], 5)], drill=rnd(v['d'], 3),
                                   removal='disconnects' if cut else rnd(100 * dz / RP, 3) if RP > 0 else None,
                                   sole_path=bool(cut), flagged=bool(rho >= 0.8 or cut)))
            rr['via_bottlenecks'] = vb
            # loads whose own current passes >= 90% through one via (statistic, not a finding)
            single = 0
            for k in rc:
                for v in N.vias:
                    if v['segs'] and v['net'] == n and not (v['kind'] == 'pth' and id(v['src']) in term_ids) \
                            and np.abs(Ib[np.array(v['segs']), k]).max() >= 0.9:
                        single += 1
                        break
            rr['loads_through_one_via'] = single
            # dead copper bookkeeping
            sm_r = np.max(np.abs(Ib[:, rc]), axis=1)
            np.maximum.at(nodeflow_rail, N.a, sm_r)
            np.maximum.at(nodeflow_rail, N.b, sm_r)
            gks = [k for k, m in enumerate(meta) if m[0] == 'gnd']
            if gks:
                sm_g = np.max(np.abs(Ib[:, gks]), axis=1)
                np.maximum.at(nodeflow_gnd, N.a, sm_g)
                np.maximum.at(nodeflow_gnd, N.b, sm_g)
                gnd_cols_done += len(gks)
            cells_n = (N.node_kind == 0) & (N.node_net == n)
            if cells_n.any():
                rr['dead_share'] = rnd(float(np.mean(nodeflow_rail[cells_n] < 1e-3)), 3)
            # Beckmann floor where the rail has a pour
            pour = sum(sum(g.area for g in b.zones[zi]['fills'].values()) for zi in b.z_by.get(n, ()))
            if pour > 1.0:
                srcp = unary_union([p['poly'] for s_ in roles['rails'][n]['sources'] for p in s_['pads']])
                lds = [L_ for k_, (kind, L_) in enumerate(meta) if kind == 'rail']
                w1 = sum(srcp.distance(unary_union([p['poly'] for p in L_['ld']['pads']])) for L_ in lds) / len(lds)
                term_a = {ly: sum(p['poly'].area for p in [q for s_ in roles['rails'][n]['sources'] for q in s_['pads']]
                                  + [q for L_ in lds for q in L_['ld']['pads']] if ly in p['layers']) for ly in b.cu}
                gsum = sum(max(b.copper(n, ly).area - term_a[ly], 1e-3) / b.rs[ly] for ly in b.cu if not b.copper(n, ly).is_empty)
                RB = (w1 ** 2) / gsum if gsum > 0 else None
                rr['pour_mm2'] = rnd(pour)
                rr['beckmann_mohm'] = rnd(RB * 1e3) if RB is not None else None
                rr['avoidable_max'] = rnd(max(0.0, 1 - RB / RA), 3) if RB is not None and RA > 0 else None
            rr['status'] = 'ok'
            log(f"   rail {short(n):14s} ({rr['confidence']}): {rr['loads_modelled']}/{rr['loads_total']} loads; R_eff {rr['r_eff_mohm']} mOhm"
                f" (+ ground {rr['r_eff_gnd_mohm']}); worst drop {rr['worst_drop_mv_per_a']} mV/A at {rr['worst_load']};"
                f" J_peak {rr.get('j_peak_a_mm2_per_a')} A/mm2/A; necks {len(rr.get('necks', []))};"
                f" via bottlenecks {sum(v['flagged'] for v in vb)}; dead {rr.get('dead_share')};"
                f" avoidable <= {rr.get('avoidable_max')}")
        except MemoryError:
            raise
        except Exception as e:         # noqa: BLE001
            rr['status'] = f'error: {type(e).__name__}: {e}'
            errors.append(dict(stage=f'dc rail {n}', error=f'{type(e).__name__}: {e}', trace=traceback.format_exc()[-1500:]))
        finally:
            for v_ in ('S', 'Phi', 'Ib'):
                locals().pop(v_, None)
    # ground: dead copper, islands, exposed pads
    G = out['ground']
    if gnd:
        try:
            cells_g = (N.node_kind == 0) & (N.node_net == gnd)
            G['net'] = gnd
            G['grid_mm'] = rnd(hnet[gnd], 3)
            G['return_columns'] = gnd_cols_done
            if gnd_cols_done and cells_g.any():
                G['dead_share'] = rnd(float(np.mean(nodeflow_gnd[cells_g] < 1e-3)), 3)
            G.update(ground_islands(b, N, roles, hnet[gnd]))
        except MemoryError:
            raise
        except Exception as e:      # noqa: BLE001
            errors.append(dict(stage='dc ground', error=f'{type(e).__name__}: {e}', trace=traceback.format_exc()[-1500:]))
    out['status'] = 'ok'
    N.lu, N.G = {}, None          # the HF stage needs only the barrels and the kept currents
    return out, (N, keep_ib)


def ground_islands(b, N, roles, h):
    """Per-layer ground islands (in-layer face connectivity), the barrels tying each, and the parts on it."""
    gnd = roles['gnd']
    cell = (N.node_kind == 0) & (N.node_net == gnd)
    ids = np.nonzero(cell)[0]
    if not len(ids):
        return dict(islands=[], n_islands=0)
    pos = -np.ones(N.nn, np.int64)
    pos[ids] = np.arange(len(ids))
    fm = (N.kind <= 1) & (N.net == gnd)
    a, c = pos[N.a[fm]], pos[N.b[fm]]
    ok = (a >= 0) & (c >= 0)
    A = sp.coo_matrix((np.ones(ok.sum()), (a[ok], c[ok])), shape=(len(ids), len(ids)))
    nc, lab = connected_components(A + A.T, directed=False)
    area = np.bincount(lab, minlength=nc) * h * h
    lay = N.node_lay[ids]
    # barrels per island
    bar_node = {}
    for vi, v in enumerate(N.vias):
        if v['net'] == gnd:
            for nd in v['nodes']:
                bar_node[int(nd)] = vi
    cm = (N.kind == 3) & (N.net == gnd)
    isl_bar = defaultdict(set)
    for aa, bb in zip(N.a[cm], N.b[cm]):
        vi = bar_node.get(int(aa))
        if vi is not None and pos[bb] >= 0:
            isl_bar[int(lab[pos[bb]])].add(vi)
    # parts with ground pins on each island
    decap_refs = {c['ref'] for r in roles['rails'].values() for c in r.get('decaps', ())}
    cell_caps = set()
    for cl in roles['cells']:
        r = roles['rails'].get(cl.get('rail'), {})
        for c in r.get('decaps', ()):
            if c['dist_mm'] is not None and c['nearest_load'] is not None:
                pass
        for c in r.get('decaps', ()):
            ic = cl.get('_ic') or (cl.get('_rb') or {}).get('driver')
            if ic is not None:
                d = min(math.hypot(c['rp']['x'] - p['x'], c['rp']['y'] - p['y']) for p in ic['pads'])
                if d < 12:
                    cell_caps.add(c['ref'])
    isl_parts = defaultdict(set)
    pad_isl = {}
    for p in b.p_by.get(gnd, ()):
        f = p['fp']
        if not (is_cap(f) or is_active(f)):
            continue
        for ly, sel in rb.pad_cells(N, b, p):
            for nd in sel:
                if pos[nd] >= 0:
                    isl_parts[int(lab[pos[nd]])].add(f['ref'])
                    pad_isl.setdefault(id(p), set()).add(int(lab[pos[nd]]))
    gl = sorted(set(lay))
    main_comp = N.comp[ids[np.argmax(np.bincount(lab, minlength=nc)[lab])]]
    first_node = np.full(nc, -1)
    first_node[lab[::-1]] = np.arange(len(ids))[::-1]
    isl_lay = lay[first_node]
    biggest = {}
    for k in np.argsort(-area):
        biggest.setdefault(isl_lay[k], int(k))
    out = []
    floating_area = 0.0
    for k in range(nc):
        ly = lay[first_node[k]]
        in_main = N.comp[ids[first_node[k]]] == main_comp
        if not in_main:
            floating_area += area[k]
        if area[k] < 0.3 or k == biggest.get(ly):
            continue
        parts = sorted(isl_parts.get(k, ()))
        nb_ = len(isl_bar.get(k, ()))
        if parts and nb_ <= 2 and len(gl) > 1:
            out.append(dict(layer=ly, area_mm2=rnd(area[k], 3), barrels=nb_, parts=parts[:12], n_parts=len(parts),
                            decaps=sorted(set(parts) & decap_refs)[:8], hot_loop_caps=sorted(set(parts) & cell_caps),
                            in_main_ground=bool(in_main)))
    out.sort(key=lambda d: (-len(d['hot_loop_caps']), d['barrels'], -d['n_parts']))
    # exposed pads without vias: active parts whose largest pad is a >= 2 mm2 ground pad
    ep = []
    for f in b.fps:
        if not is_active(f):
            continue
        gp = [p for p in f['pads'] if p['net'] == gnd]
        if not gp or len(f['pads']) < 4:
            continue
        big = max(f['pads'], key=lambda p: p['poly'].area)
        if big['net'] != gnd or big['poly'].area < 2.0 or big['kind'] == 'thru_hole':
            continue
        nv = sum(1 for v in b.v_by.get(gnd, ()) if big['poly'].buffer(0.05).contains(Point(v['x'], v['y'])))
        nv += sum(1 for p in f['pads'] if p is not big and p['kind'] == 'thru_hole' and p['net'] == gnd
                  and big['poly'].contains(Point(p['x'], p['y'])))
        if nv == 0:
            power = any(cl['ref'] == f['ref'] or f['ref'] in cl['ref'].split('+') for cl in roles['cells']) \
                or f['ref'] in roles['regs']
            ep.append(dict(ref=f['ref'], value=f['value'], pad=big['num'], area_mm2=rnd(big['poly'].area, 3), power_ic=bool(power)))
    return dict(n_islands=int(nc), weak_islands=out[:20], n_weak_islands=len(out), floating_mm2=rnd(floating_area, 3),
                layers=gl, ep_without_vias=ep)


# ============================================================================ HF hot loops
def cell_roles(b, roles, cell):
    """rb.run_hf's role dict for one switching cell."""
    if cell['type'] == 'bridge-driver':
        return cell['_rb']
    gnd = cell['gnd'] or roles['gnd']
    rail = cell['rail']
    if rail is None:
        raise ValueError('no hot-loop rail (IC pin on a rail other than the switch node)')
    if cell['type'] == 'regulator+inductor':
        drv = cell['_ic']
        L_ = cell['_L']
        lpad = next(p for p in L_['pads'] if p['net'] == cell['sw'])
        phases = [dict(shunt=None, net_in=cell['sw'], net_out=cell['out'], load=None, amp=None, inductor=L_, lpad=lpad)]
    else:
        qa, qb = cell['_qa'], cell['_qb']
        if qa['layer'] != qb['layer']:
            raise ValueError('half-bridge transistors on opposite sides: the stack model needs one part side')
        lo_g = [p for p in qb['pads'] if p['net'] in roles['ground']]
        if not lo_g:             # low side returns through a shunt: the body ends at the shunt's ground pad
            qbn = {p['net'] for p in qb['pads']}
            sh = next((s_ for s_ in roles['shunts'] if set(s_['nets']) & qbn and set(s_['nets']) & set(roles['ground'])), None)
            if sh is None:
                raise ValueError('low-side transistor has no ground pad and no shunt to ground')
            lo_g = [p for p in sh['fp']['pads'] if p['net'] in roles['ground']]
            cell['body_note'] = f"synthetic body ends at shunt {sh['ref']}'s ground pad"
        pads = [p for p in qa['pads'] if p['net'] == rail] + lo_g
        gnd = lo_g[0]['net']
        drv = dict(ref=cell['ref'], value=cell['value'], lib='', layer=qa['layer'], x=(qa['x'] + qb['x']) / 2,
                   y=(qa['y'] + qb['y']) / 2, pads=pads)
        phases = []
        for f in b.fps:          # the inductor on the switch node, if any (synchronous buck with discrete transistors)
            if is_ind(f) and not is_bead(f) and any(p['net'] == cell['sw'] for p in f['pads']):
                lpad = next(p for p in f['pads'] if p['net'] == cell['sw'])
                other = next((p['net'] for p in f['pads'] if p is not lpad), None)
                phases = [dict(shunt=None, net_in=cell['sw'], net_out=other, load=None, amp=None, inductor=f, lpad=lpad)]
                break
    rp = [p for p in drv['pads'] if p['net'] == rail]
    gp = [p for p in drv['pads'] if p['net'] == gnd]
    if not rp or not gp:
        raise ValueError(f"driver {drv['ref']} has no pad on the rail '{short(rail)}' or on '{short(gnd)}'")
    decaps = []
    for f in b.fps:
        if is_cap(f) and {p['net'] for p in f['pads']} == {rail, gnd}:
            d = min(math.hypot(f['x'] - p['x'], f['y'] - p['y']) for p in rp)
            decaps.append((d, f))
    decaps.sort(key=lambda t: t[0])
    if not any(d < 12.0 for d, _ in decaps):
        raise ValueError(f"no capacitor between '{short(rail)}' and '{short(gnd)}' within 12 mm: hot loop undefined")
    epad = max(gp, key=lambda p: p['poly'].area)
    foot = [p for p in gp if p is not epad and min(math.hypot(p['x'] - q['x'], p['y'] - q['y']) for q in rp) <= 1.0] \
        if cell['type'] != 'half-bridge' else []
    return dict(gnd=gnd, rail=rail, driver=drv, decaps=decaps, foot=foot, epad=epad, phases=phases)


def hf_window(b, rr):
    """The window rb.run_hf will use (same rule), for choosing the HF grid."""
    drv, gnd = rr['driver'], rr['gnd']
    near = [f for d, f in rr['decaps'] if d < 12.0]
    pts = [(p['x'], p['y']) for p in drv['pads']] + [(p['x'], p['y']) for f in near for p in f['pads']]
    for p in (q for q in drv['pads'] if q['net'] == gnd):
        gv = sorted((v for v in b.v_by.get(gnd, ())), key=lambda v: math.hypot(v['x'] - p['x'], v['y'] - p['y']))
        pts += [(v['x'], v['y']) for v in gv[:4]]
    for ph in rr['phases']:
        pts += [(p['x'], p['y']) for p in (ph['shunt']['fp']['pads'] if ph['shunt'] else ph['inductor']['pads'])]
        if ph['load']:
            pts += [(p['x'], p['y']) for p in ph['load']['pads']]
    xs, ys = zip(*pts)
    w = [min(xs) - 3, min(ys) - 3, max(xs) + 3, max(ys) + 3]
    if b.outline is not None:
        bx = b.outline.bounds
        w = [max(w[0], bx[0]), max(w[1], bx[1]), min(w[2], bx[2]), min(w[3], bx[3])]
    return w


def hf_summary(res, rail, gnd):
    out = dict(L_board_nH=rnd(res['L_board'] * 1e9), L_esl_nH=rnd(res['L_esl'] * 1e9),
               cap_split={k: rnd(abs(v), 3) for k, v in res['split'].items()},
               energy_by_gap={k: rnd(v, 3) for k, v in res['Egap'].items() if v > 0.005})
    per = sorted(((k, v) for k, v in res['per'].items() if not k[1].startswith('@')), key=lambda t: -t[1])
    tot = sum(v for _, v in per) or 1.0
    out['current_by_layer_net'] = [dict(layer_index=int(k[0]), net=k[1], a_mm_per_a=rnd(v, 3)) for k, v in per[:8]]
    induced = sum(v for k, v in per if k[1] not in (rail, gnd))
    out['foreign_net_current_share'] = rnd(induced / tot, 3)
    out['vias'] = [dict(share=rnd(c, 3), at=[rnd(x, 5), rnd(y, 5)], net=net) for c, x, y, net in res.get('vias', [])[:8]]
    if res.get('plane_cf'):
        net, ly, L0, L2 = res['plane_cf']
        out['remove_plane'] = dict(net=net, layer=ly, ratio=rnd(L2 / L0, 3) if L2 < 1e-6 else None,
                                   opens_loop=bool(L2 >= 1e-6))
    if res.get('swap'):
        pn, la, lb_, L0, L3 = res['swap']
        out['swap_planes'] = dict(plane=pn, layers=[la, lb_], change=rnd(L3 / L0 - 1, 3))
    if res.get('add'):
        x, y, L0, Lc, Lbf, med = res['add']
        out['best_added_via'] = dict(at=[rnd(x, 5), rnd(y, 5)], change=rnd(Lc / L0 - 1, 3), brute_force_change=rnd(Lbf / L0 - 1, 3),
                                     median_site_change=rnd(med / L0 - 1, 3))
    out['switch_node_charge'] = {k: dict(pF=rnd(v[0] * 1e12), to={n: rnd(c / v[0], 3) for n, c in
                                                                  sorted(v[1].items(), key=lambda t: -t[1])[:3]})
                                 for k, v in res.get('charge', {}).items()}
    out['window_mm'] = [rnd(v, 5) for v in res['window']]
    return out


def run_cells(b, roles, dcN, args, res, errors, flush):
    cells = roles['cells']
    order = sorted(range(len(cells)), key=lambda i: ({'bridge-driver': 0, 'regulator+inductor': 1, 'half-bridge': 2}[cells[i]['type']],
                                                     -(roles['rails'].get(cells[i].get('rail') or '', {}).get('volts') or 0)))
    out = []
    N, keep_ib = dcN if dcN else (None, {})
    for rank, i in enumerate(order):
        c = cells[i]
        rec = dict(type=c['type'], ref=c['ref'], value=c['value'], rail=c.get('rail'), sw=c.get('sw'), confidence=c['confidence'],
                   calibrated=False, body=('two-transistor strip from the high-side rail pad to the low-side ground pad'
                                           if c['type'] == 'half-bridge' else 'package lead strips and paddle (rb_board_passports)'))
        out.append(rec)
        if rank >= args.max_cells:
            rec['status'] = f'skipped: over --max-cells {args.max_cells}'
            continue
        if now() > args.budget_s * 0.85:
            rec['status'] = 'skipped: time budget'
            continue
        t0 = now()
        try:
            rr = cell_roles(b, roles, c)
            w = hf_window(b, rr)
            area = max(1.0, (w[2] - w[0]) * (w[3] - w[1]))
            h = max(args.h_hf, math.sqrt(area * (len(b.cu) + 1) / args.max_hf_cells))
            hargs = SimpleNamespace(h_hf=round(h, 3), h_out=10.0, h_comp=0.3, quick=False)
            rec['grid_mm'] = rnd(h, 3)
            sdef, col, Ib = {}, {}, np.zeros((1, 1))
            if N is not None and rr['rail'] in keep_ib:
                sdef = {f"feed {short(rr['rail'])}": None}
                col = {f"feed {short(rr['rail'])}": 0}
                Ib = keep_ib[rr['rail']][:, None]
            buf = io.StringIO()
            tries = []

            def attempt():
                nonlocal buf
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    return rb.run_hf(b, rr, N, Ib, sdef, col, hargs)
            while True:
                try:
                    r = attempt()
                    break
                except (MemoryError, RuntimeError) as e:     # SuperLU allocation failure: one retry on a coarser grid
                    if (not isinstance(e, MemoryError) and 'MALLOC' not in str(e).upper()) or 'coarser grid' in tries:
                        raise
                    hargs.h_hf = round(hargs.h_hf * 1.35, 3)
                    tries.append('coarser grid')
                except ValueError as e:
                    # adjacent lead strips merge on the raster and leave no cut for the drive EMF: first drop the
                    # bridge-return strips (one strip from the supply pin into the ground pad), then a finer grid
                    if 'no complete cut' not in str(e) or len(tries) >= 2:
                        raise
                    if rr.get('foot'):
                        rr = dict(rr, foot=[])
                        tries.append('no bridge-return strips')
                    else:
                        hn = round(hargs.h_hf * 0.67, 3)
                        if area * (len(b.cu) + 1) / hn ** 2 > 1.5 * args.max_hf_cells:
                            raise
                        hargs.h_hf = hn
                        tries.append('finer grid')
            if tries:
                rec['retry'] = '; '.join(tries)
                rec['grid_mm'] = hargs.h_hf
            txt = buf.getvalue()
            log(txt.rstrip())
            if r['L_esl'] > 1e-6:      # > 1 uH: no closed return path inside the window (open loop), not a loop inductance
                raise ValueError(f"open loop: the capacitor return does not reach the driver's ground inside the window"
                                 f" (L = {r['L_esl']:.3g} H)")
            rec.update(hf_summary(r, rr['rail'], rr['gnd']))
            m = re.search(r'(\d+) sheet cells', txt)
            rec['sheet_cells'] = int(m.group(1)) if m else None
            rec['decaps_in_loop'] = [f['ref'] for d, f in rr['decaps'] if d < 12.0]
            if c.get('body_note'):
                rec['body'] += '; ' + c['body_note']
            rec['status'] = 'ok'
        except MemoryError:
            rec['status'] = 'error: MemoryError'
            errors.append(dict(stage=f"hf {c['ref']}", error='MemoryError'))
        except (SystemExit, Exception) as e:        # noqa: BLE001
            rec['status'] = f'error: {type(e).__name__}: {e}'
            errors.append(dict(stage=f"hf {c['ref']}", error=f'{type(e).__name__}: {e}', trace=traceback.format_exc()[-1500:]))
        rec['t_s'] = rnd(now() - t0, 3)
        res['hf'] = dict(cells=out)
        flush()
    return out


# ============================================================================ topological hot-loop check
def hotloop_split_ground(b, roles):
    """Decoupling-loop critic (real-board-passports rec. 3b): does each switching cell's input capacitor reach the
    IC's ground through the same top-side ground copper, or only through different via groups?"""
    out = []
    for c in roles['cells']:
        try:
            rr = cell_roles(b, roles, c)
        except (SystemExit, Exception):        # noqa: BLE001
            continue
        drv, gnd = rr['driver'], rr['gnd']
        side = drv['layer']
        g = b.copper(gnd, side)
        isl = list(getattr(g, 'geoms', [g]))
        def island_of(p):
            return next((k for k, q in enumerate(isl) if q.intersects(p['poly'])), None)
        dg = {island_of(p) for p in drv['pads'] if p['net'] == gnd} - {None}
        for d, f in rr['decaps']:
            if d >= 12.0:
                continue
            gp = next(p for p in f['pads'] if p['net'] == gnd)
            if f['layer'] != side:
                continue
            k = island_of(gp)
            same = k in dg
            nv = 0
            if k is not None and not same:
                nv = sum(1 for v in b.v_by.get(gnd, ()) if isl[k].contains(Point(v['x'], v['y'])))
            out.append(dict(cell=c['ref'], cap=f['ref'], dist_mm=rnd(d, 3), same_top_ground=bool(same),
                            cap_island_mm2=rnd(isl[k].area, 3) if k is not None else None, cap_island_vias=nv))
    return out


# ============================================================================ findings
def make_findings(res, args):
    F = []
    roles = res.get('roles', {})
    for n, r in (res.get('dc') or {}).get('rails', {}).items():
        conf = r.get('confidence')
        for t in r.get('necks', []):
            F.append(dict(type='DC-NECK', net=n, role_confidence=conf, measured=t['share'], unit='share of rail R',
                          detail=f"1 mm tile at {t['tile']} ({'/'.join(t['layers'])}) holds {100 * t['share']:.0f}% of the rail's"
                                 f" supply-path resistance, away from terminals" + (' (via in tile)' if t['has_via'] else '')))
        for v in r.get('via_bottlenecks', []):
            if v['flagged']:
                F.append(dict(type='DC-VIA-BOTTLENECK', net=n if v['column'] == 'rail' else (res.get('dc') or {}).get('ground', {}).get('net'),
                              role_confidence=conf, measured=v['share'], unit='share of load current',
                              detail=f"{v['kind']} at {v['at']} carries {100 * v['share']:.0f}% of the rail's"
                                     f" {'supply' if v['column'] == 'rail' else 'ground-return'} current, all loads on (rho {v['rho']});"
                                     f" removal: {v['removal']}{'' if v['removal'] == 'disconnects' else '% R'}"))
        if r.get('dead_share') is not None and r['dead_share'] >= args.dead_share:
            F.append(dict(type='DC-DEAD-COPPER', net=n, role_confidence=conf, measured=r['dead_share'], unit='share of area',
                          detail=f"{100 * r['dead_share']:.0f}% of the rail's copper carries < 0.1% of every modelled load current"))
        if r.get('worst_drop_mv_per_a') is not None and r['worst_drop_mv_per_a'] >= args.drop_mv_per_a:
            F.append(dict(type='DC-IR-DROP', net=n, role_confidence=conf, measured=r['worst_drop_mv_per_a'], unit='mV per A',
                          detail=f"worst load {r['worst_load']}: {r['worst_drop_mv_per_a']} mV per A of its own current"
                                 + (' (rail + ground)' if r.get('worst_includes_ground') else ' (rail only)')))
        if r.get('avoidable_max') is not None and r['avoidable_max'] >= args.avoidable:
            F.append(dict(type='DC-FLOOR-GAP', net=n, role_confidence=conf, measured=r['avoidable_max'], unit='fraction',
                          detail=f"Beckmann floor {r['beckmann_mohm']} mOhm vs {r['r_eff_mohm']} mOhm on {r.get('pour_mm2')} mm2:"
                                 f" at most {100 * r['avoidable_max']:.0f}% avoidable by reshaping at equal area"))
    G = (res.get('dc') or {}).get('ground', {})
    for isl in G.get('weak_islands', []):
        if isl['n_parts'] < 2 and not isl['hot_loop_caps']:
            continue          # one part's pads tied by their own vias: ordinary via-in-pad practice
        F.append(dict(type='GND-ISLAND', net=G.get('net'), role_confidence=(roles.get('ground', {}).get(G.get('net')) or {}).get('confidence'),
                      measured=isl['barrels'], unit='vias',
                      detail=f"{isl['area_mm2']} mm2 ground island on {isl['layer']} with {isl['n_parts']} part(s)"
                             f" ({', '.join(isl['parts'][:4])}) tied by {isl['barrels']} via(s)"
                             + (f"; holds hot-loop caps {', '.join(isl['hot_loop_caps'])}" if isl['hot_loop_caps'] else '')))
    if G.get('dead_share') is not None and G['dead_share'] >= args.dead_share:
        F.append(dict(type='DC-DEAD-COPPER', net=G.get('net'), role_confidence=None, measured=G['dead_share'], unit='share of area',
                      detail=f"{100 * G['dead_share']:.0f}% of ground copper carries < 0.1% of every modelled return current"))
    for e in G.get('ep_without_vias', []):
        F.append(dict(type='EP-NO-VIA', net=G.get('net'), role_confidence=None, measured=0, unit='vias',
                      detail=f"{e['ref']} ({e['value']}) exposed pad {e['pad']} ({e['area_mm2']} mm2) has no via"
                             + (' (power IC)' if e['power_ic'] else '')))
    for h in res.get('hotloop_split_ground', []):
        if not h['same_top_ground']:
            F.append(dict(type='HOTLOOP-SPLIT-GND', net=None, role_confidence=None, measured=h['dist_mm'], unit='mm',
                          detail=f"{h['cap']} ground pad of cell {h['cell']} sits on a different top-side ground island"
                                 f" ({h['cap_island_mm2']} mm2, {h['cap_island_vias']} vias) from the IC's ground pins"))
    for c in (res.get('hf') or {}).get('cells', []):
        if c.get('status') != 'ok':
            continue
        if c.get('swap_planes') and c['swap_planes']['change'] <= -args.hf_gain:
            F.append(dict(type='HF-PLANE-ORDER', net=c['swap_planes']['plane'], role_confidence=c['confidence'],
                          measured=c['swap_planes']['change'], unit='fraction of L',
                          detail=f"cell {c['ref']}: swapping the {c['swap_planes']['plane']} plane with ground changes hot-loop L by"
                                 f" {100 * c['swap_planes']['change']:+.0f}% (uncalibrated model)"))
        if c.get('best_added_via') and c['best_added_via']['change'] <= -args.hf_gain:
            F.append(dict(type='HF-VIA-SITE', net=None, role_confidence=c['confidence'], measured=c['best_added_via']['change'],
                          unit='fraction of L',
                          detail=f"cell {c['ref']}: one added ground via changes hot-loop L by {100 * c['best_added_via']['change']:+.0f}%"
                                 f" (median site {100 * c['best_added_via']['median_site_change']:+.1f}%)"))
        if c.get('remove_plane') and (c['remove_plane'].get('ratio') or 0) >= 1.5:
            F.append(dict(type='HF-INDUCED-PLANE', net=c['remove_plane']['net'], role_confidence=c['confidence'],
                          measured=c['remove_plane']['ratio'], unit='L ratio',
                          detail=f"cell {c['ref']}: the {c['remove_plane']['net']} plane ({c['remove_plane']['layer']}) is an image"
                                 f" conductor; without it L x{c['remove_plane']['ratio']:.2f}"))
    return F


# ============================================================================ main
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('board')
    ap.add_argument('--json', required=True)
    ap.add_argument('--roles-out')
    ap.add_argument('--max-nodes', type=int, default=300000, help='DC node budget (grids coarsen to fit)')
    ap.add_argument('--max-loads', type=int, default=12, help='loads modelled per rail (farthest from the source first)')
    ap.add_argument('--max-rails', type=int, default=24)
    ap.add_argument('--max-cells', type=int, default=3, help='switching cells given the HF analysis')
    ap.add_argument('--max-hf-cells', type=int, default=120000, help='HF window cells x layers budget (~2 GB at 120k)')
    ap.add_argument('--h-hf', type=float, default=0.15)
    ap.add_argument('--lev-faces', type=int, default=40, help='exact leverage for this many most loaded faces per rail')
    ap.add_argument('--budget-s', type=float, default=540.0, help='soft time budget; later stages are skipped past it')
    ap.add_argument('--no-hf', action='store_true')
    # screening thresholds for counting findings (not budgets)
    ap.add_argument('--neck-share', type=float, default=0.2)
    ap.add_argument('--dead-share', type=float, default=0.5)
    ap.add_argument('--drop-mv-per-a', type=float, default=100.0)
    ap.add_argument('--avoidable', type=float, default=0.9)
    ap.add_argument('--hf-gain', type=float, default=0.10)
    args = ap.parse_args(argv)
    res = dict(tool='suite_passports', schema=1, board=os.path.abspath(args.board), coverage={}, errors=[], timing={})
    errors = res['errors']

    def flush():
        res['timing']['total_s'] = rnd(now(), 4)
        res['peak_rss_mb'] = rnd(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0, 4)
        tmp = args.json + '.tmp'
        with open(tmp, 'w') as f:
            json.dump(jsonable(res), f, indent=1)
        os.replace(tmp, args.json)

    def stage(name, fn):
        t0 = now()
        try:
            v = fn()
            res['coverage'].setdefault(name, 'ok')
            return v
        except MemoryError:
            res['coverage'][name] = 'error: MemoryError'
            errors.append(dict(stage=name, error='MemoryError'))
        except (SystemExit, Exception) as e:      # noqa: BLE001
            res['coverage'][name] = f'error: {type(e).__name__}: {e}'
            errors.append(dict(stage=name, error=f'{type(e).__name__}: {e}', trace=traceback.format_exc()[-2000:]))
        finally:
            res['timing'][name] = rnd(now() - t0, 4)
            flush()
        return None

    b = stage('parse', lambda: SBoard(args.board))
    if b is None:
        return 2

    def board_info():
        fills = b.fill_report()
        info = dict(file_version=b.version, layers=list(b.cu), stackup=b.stackup_note,
                    copper_um={ly: rnd(b.tcu[ly] * 1e3, 3) for ly in b.cu},
                    outline_mm2=rnd(b.outline.area) if b.outline is not None else None, outline_src=b.outline_src,
                    footprints=len(b.fps), pads=len(b.pads), tracks=len(b.tracks), vias=len(b.vias), zones=len(b.zones),
                    zone_layers_saved=sum(1 for f in fills if 'NO saved' not in f[4]),
                    zone_layers_approx=sum(1 for f in fills if 'NO saved' in f[4]),
                    zone_layers_stale=sum(1 for f in fills if 'OVERLAPS' in f[4]))
        log(f"== {os.path.basename(args.board)}: {len(b.cu)} layers ({b.stackup_note}), {len(b.fps)} footprints, {len(b.tracks)} tracks,"
            f" {len(b.vias)} vias, {len(b.zones)} zones; fills saved/approx/stale {info['zone_layers_saved']}/"
            f"{info['zone_layers_approx']}/{info['zone_layers_stale']}")
        res['board_info'] = info
    stage('board_info', board_info)

    roles_box = {}

    def roles_stage():
        roles, L = infer_roles_general(b)
        roles_box['r'] = roles
        log("\n== Roles (inferred; evidence and confidence)")
        for line in L:
            log("   " + line)
        res['roles'] = roles_json(roles)
        res['roles']['log'] = L
        if args.roles_out:
            with open(args.roles_out, 'w') as f:
                json.dump(jsonable(roles_for_critics(roles)), f, indent=1)
    stage('roles', roles_stage)
    roles = roles_box.get('r')
    if roles is None:
        res['coverage']['dc'] = res['coverage']['hf'] = 'skipped: no roles'
        flush()
        return 1

    dc_box = {}

    def dc_stage():
        out, dcN = run_dc(b, roles, args, res, errors)
        res['dc'] = out
        dc_box['N'] = dcN
        if out.get('status', '').startswith('skipped'):
            res['coverage']['dc'] = out['status']
    stage('dc', dc_stage)
    stage('hotloop_split_ground', lambda: res.__setitem__('hotloop_split_ground', hotloop_split_ground(b, roles)))
    if args.no_hf:
        res['coverage']['hf'] = 'skipped: --no-hf'
    elif not roles['cells']:
        res['coverage']['hf'] = 'skipped: no switching cell identified'
        res['hf'] = dict(cells=[])
    else:
        stage('hf', lambda: run_cells(b, roles, dc_box.get('N'), args, res, errors, flush))
    stage('findings', lambda: res.__setitem__('findings', make_findings(res, args)))
    res['findings_by_type'] = dict(Counter(f['type'] for f in res.get('findings', [])))
    log(f"\n== Findings: {res['findings_by_type']}; errors: {len(errors)}; total {now():.0f} s")
    flush()
    return 0


if __name__ == '__main__':
    sys.exit(main())
