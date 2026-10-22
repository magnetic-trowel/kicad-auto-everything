# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Test stand-in for the physics brief (Contract 2) until kae.circuit.brief lands.

Deliberately small and position-free (like the real brief, it reads names, values,
footprints, pin functions and netlist topology, never where parts sit), so validation
runs do not encode the human placement into the structures. It emits the brief shape that
kae.physics.build documents, members keyed by footprint uuid. Do not grow real logic here:
kae.circuit owns comprehension.
"""
from __future__ import annotations

import re
from collections import defaultdict

from . import priors as PR

GND_RE = re.compile(r'(^|[^A-Z])(A|D|P|S|C)?GND|^/?VSS|^0V$|GROUND|EARTH', re.I)
PWR_RE = re.compile(r'^/?(\+?\d+(\.\d+)?V\d*|\+[A-Z0-9_.]+|V(CC|DD|BUS|IN|SYS|BAT|MOT|M|PP|REG|CORE|CAP|S)[A-Z0-9_.]*|'
                    r'[AD]V(DD|CC)[A-Z0-9_]*|\d+V\d+|[0-9]+V[0-9]*_?[A-Z]*)$', re.I)
REG_RE = re.compile(r'LDO|REG|1117|LM317|78[0-9]{2}|AP2[0-9]{3}|AP7[0-9]{3}|AP63|MCP1[67]\d\d|XC6|RT9|RT8|TLV7|TPS|LM2|LMR|'
                    r'MP1|MP2|MP8|SY8|AOZ|LT1|LT3|LTC3|ADP|NCP|MIC5|MIC29|SPX|BD9|HT7|ME6|LP29|LP38|LP59|MAX15|MAX17|'
                    r'BUCK|BOOST|DCDC|PMIC|AMS1|XL[0-9]{4}|SX1308|MT3608|SGM2|SGM6|RP[0-9]{3}|LD39|LD29|ST1S', re.I)
SW_PIN = re.compile(r'^(SW|LX|PH|PHASE|SW\d|LX\d|SWA|SWB)$', re.I)
IN_PIN = re.compile(r'^(P?VIN\d?|VCC|VDD|IN|VS|VBAT|PVDD|AVIN|VSUP|VSYS|V\+)$', re.I)
TVS_RE = re.compile(r'TVS|ESD|PESD|SMAJ|SMBJ|SMCJ|USBLC|TPD\d|PRTR|SP05|SRV05|RCLAMP|IP4|NUP|CDSOT|SOD-?923', re.I)
SENS_RE = re.compile(r'NTC|THERM|TMP\d|LM35|DS18B20|SHT\d|BME\d|BMP\d|HDC\d|SI70|MCP98|STTS|PT100|PT1000', re.I)
REF_RE = re.compile(r'\bREF\d|LM4040|TL431|ADR\d|LT6656|REF50|MAX603|LM4050', re.I)
ANT_RE = re.compile(r'ANTENNA|ANT_|CHIP.?ANT|WROOM|WROVER|RFM9|U\.?FL|SMA', re.I)


def _get(o, k, d=None):
    return o.get(k, d) if isinstance(o, dict) else getattr(o, k, d)


def _pfx(ref):
    m = re.match(r'[A-Za-z_]+', ref or '')
    return m.group(0).upper() if m else ''


def _val(text, unit):
    from re import search
    s = (text or '').replace('µ', 'u').replace('μ', 'u')
    m = search(r'(\d+(?:\.\d+)?)\s*([pnumkKM]?)' + unit, s) or search(r'(\d+)([pnumkKM])(\d+)', s)
    if not m:
        return None
    mult = {'p': 1e-12, 'n': 1e-9, 'u': 1e-6, 'm': 1e-3, '': 1.0, 'k': 1e3, 'K': 1e3, 'M': 1e6}
    try:
        if m.lastindex == 3:
            return float(f'{m.group(1)}.{m.group(3)}') * mult.get(m.group(2), 1.0)
        return float(m.group(1)) * mult.get(m.group(2), 1.0)
    except ValueError:
        return None


def provisional_brief(board):
    fps = list(_get(board, 'footprints', []) or [])
    parts = []
    for f in fps:
        pads = list(_get(f, 'pads', []) or [])
        parts.append(dict(uuid=_get(f, 'uuid', ''), ref=_get(f, 'ref', ''), value=_get(f, 'value', '') or '',
                          lib=_get(f, 'lib_id', '') or '', pads=[(str(_get(p, 'number', '')), _get(p, 'net', '') or '',
                                                                   _get(p, 'pinfunction', '') or '',
                                                                   _get(p, 'pintype', '') or '') for p in pads]))
    by_net = defaultdict(list)
    for j, p in enumerate(parts):
        for num, net, fn, ty in p['pads']:
            if net:
                by_net[net].append((j, num))
    gnd = {n for n in by_net if GND_RE.search(n.split('/')[-1] or n)}
    if not gnd and by_net:
        gnd = {max(by_net, key=lambda n: len(by_net[n]))}

    def nets(p):
        return {n for _, n, _, _ in p['pads'] if n}

    def is_cap(p):
        return len(p['pads']) == 2 and (_pfx(p['ref']) == 'C' or 'Capacitor' in p['lib'] or ':C_' in p['lib'])

    def is_ic(p):
        return len(p['pads']) > 4 and _pfx(p['ref']) in ('U', 'IC', 'Q', 'VR', 'PS')

    caps_by_rail = defaultdict(list)
    for j, p in enumerate(parts):
        if is_cap(p):
            n0, n1 = p['pads'][0][1], p['pads'][1][1]
            if n0 in gnd and n1 and n1 not in gnd:
                caps_by_rail[n1].append(j)
            elif n1 in gnd and n0 and n0 not in gnd:
                caps_by_rail[n0].append(j)
    rails = {n for n in caps_by_rail if len(caps_by_rail[n]) >= 1 and
             (PWR_RE.search(n.split('/')[-1]) or len(caps_by_rail[n]) >= 2)}
    S = []
    # decaps
    for j, p in enumerate(parts):
        if not is_ic(p):
            continue
        gp = [num for num, n, _, _ in p['pads'] if n in gnd]
        for r in sorted(nets(p) & rails):
            pp = sorted({num for num, n, _, _ in p['pads'] if n == r})
            caps = [parts[c]['uuid'] for c in caps_by_rail[r]]
            if pp and gp and caps:
                S.append(dict(id=f"decap:{p['ref']}:{r.split('/')[-1]}", kind='decap', ic=p['uuid'], power_pins=pp,
                              ground_pins=sorted(set(gp)), rail=r, ground=sorted(gnd)[0], caps=caps, confidence=0.6))
    # commutation cells: IC switch pin on an inductor
    inductors = [j for j, p in enumerate(parts) if _pfx(p['ref']) == 'L' and len(p['pads']) == 2
                 and not re.search(r'bead|ferrite|BLM|FB', p['value'] + p['lib'], re.I)]
    sw_nets = set()
    for j in inductors:
        lp = parts[j]
        for k in (0, 1):
            sw, other = lp['pads'][k][1], lp['pads'][1 - k][1]
            if not sw or sw in gnd:
                continue
            for q, ic in enumerate(parts):
                if not is_ic(ic):
                    continue
                swp = [num for num, n, fn, _ in ic['pads'] if n == sw and SW_PIN.match(fn.strip())]
                if not swp:
                    continue
                vin = [(num, n) for num, n, fn, _ in ic['pads'] if IN_PIN.match(fn.strip()) and n in rails]
                if not vin:
                    continue
                rail = vin[0][1]
                vpins = sorted({num for num, n in vin if n == rail})
                gpins = sorted({num for num, n, fn, _ in ic['pads'] if n in gnd})
                cls = 'boost' if other == rail else 'buck'
                for c in caps_by_rail[rail]:
                    cp = parts[c]
                    cr = next(num for num, n, _, _ in cp['pads'] if n == rail)
                    cg = next(num for num, n, _, _ in cp['pads'] if n in gnd)
                    S.append(dict(id=f"cell:{ic['ref']}:{cp['ref']}", kind='commutation_cell', cls=cls,
                                  **{'class': cls}, rail=rail, sw=sw, gnd=sorted(gnd)[0],
                                  loop=[[cp['uuid'], cr], [ic['uuid'], vpins], [ic['uuid'], gpins], [cp['uuid'], cg]],
                                  confidence=0.5 if len(caps_by_rail[rail]) > 1 else 0.7))
                sw_nets.add(sw)
                S.append(dict(id=f"heat:{ic['ref']}", kind='heat_source', ref=ic['uuid'],
                              P_W=PR.source_power_prior(cls, PR_volts(rail), PR_volts(other), len(ic['pads']), ic['lib'])[0],
                              confidence=0.5))
                break
    # half-bridges: two transistors sharing a node, one on a rail, one on ground
    qs = [j for j, p in enumerate(parts) if _pfx(p['ref']) in ('Q', 'T') and len(p['pads']) >= 3]
    seen = set()
    for X in sorted({n for j in qs for n in nets(parts[j])} - gnd - rails):
        on = [j for j in qs if X in nets(parts[j])]
        hi = [j for j in on if (nets(parts[j]) - {X}) & rails]
        lo = [j for j in on if j not in hi and (nets(parts[j]) - {X}) & gnd]
        if not hi or not lo or (hi[0], lo[0]) in seen:
            continue
        seen.add((hi[0], lo[0]))
        qa, qb = parts[hi[0]], parts[lo[0]]
        rail = sorted((nets(qa) - {X}) & rails)[0]
        for c in caps_by_rail[rail][:4]:
            cp = parts[c]
            cr = next(num for num, n, _, _ in cp['pads'] if n == rail)
            cg = next(num for num, n, _, _ in cp['pads'] if n in gnd)
            S.append(dict(id=f"cell:{qa['ref']}+{qb['ref']}:{cp['ref']}", kind='commutation_cell', **{'class': 'half_bridge'},
                          rail=rail, sw=X, loop=[[cp['uuid'], cr],
                                                 [qa['uuid'], sorted({num for num, n, _, _ in qa['pads'] if n == rail})],
                                                 [qa['uuid'], sorted({num for num, n, _, _ in qa['pads'] if n == X})],
                                                 [qb['uuid'], sorted({num for num, n, _, _ in qb['pads'] if n == X})],
                                                 [qb['uuid'], sorted({num for num, n, _, _ in qb['pads'] if n in gnd})],
                                                 [cp['uuid'], cg]], confidence=0.4))
        sw_nets.add(X)
        for q in (qa, qb):
            S.append(dict(id=f"heat:{q['ref']}", kind='heat_source', ref=q['uuid'],
                          P_W=PR.source_power_prior('fet', pkg=q['lib'])[0], confidence=0.4))
    # crystals
    for j, p in enumerate(parts):
        if _pfx(p['ref']) not in ('Y', 'X', 'XTAL') or len(p['pads']) not in (2, 3, 4):
            continue
        if not re.search(r'Crystal|XTAL|Hz|Resonator', p['lib'] + ' ' + p['value'], re.I):
            continue
        xn = sorted({n for _, n, _, _ in p['pads'] if n and n not in gnd})
        if len(xn) != 2:
            continue
        ic = next((q for q, ic in enumerate(parts) if is_ic(ic) and set(xn) <= nets(ic)), None)
        if ic is None:
            continue
        icp = parts[ic]
        xi = next(num for num, n, _, _ in icp['pads'] if n == xn[0])
        xo = next(num for num, n, _, _ in icp['pads'] if n == xn[1])
        lc = [parts[c]['uuid'] for c in range(len(parts)) if is_cap(parts[c]) and nets(parts[c]) & set(xn)]
        f = _val(p['value'], 'Hz')
        S.append(dict(id=f"xtal:{p['ref']}", kind='crystal', ic=icp['uuid'], xin=xi, xout=xo, crystal=p['uuid'],
                      load_caps=lc, f_Hz=f, confidence=0.8))
        S.append(dict(id=f"victim:{p['ref']}", kind='victim', **{'class': 'crystal'}, nets=xn, confidence=0.6))
        S.append(dict(id=f"tv:{p['ref']}", kind='thermal_victim', ref=p['uuid'],
                      **{'class': 'crystal_32k' if (f and f < 2e5) else 'crystal'}, confidence=0.6))
    # feedback victims: IC pins named FB
    for j, p in enumerate(parts):
        for num, n, fn, _ in p['pads']:
            if n and re.match(r'^V?FB\d?$', fn.strip(), re.I):
                S.append(dict(id=f"victim:{p['ref']}.FB", kind='victim', **{'class': 'feedback'}, nets=[n], confidence=0.6))
    # connectors and protection chains
    conns = [j for j, p in enumerate(parts) if _pfx(p['ref']) in ('J', 'P', 'CN', 'USB', 'X') and len(p['pads']) >= 2
             and not re.search(r'Crystal|TestPoint|Tag-?Connect|Pogo|MountingHole|Fiducial', p['lib'], re.I)]
    prot = [j for j, p in enumerate(parts) if TVS_RE.search(p['value'] + ' ' + p['lib']) and _pfx(p['ref']) in ('D', 'U', 'TVS', 'ESD')]
    briefparts = {}
    for j in conns:
        c = parts[j]
        briefparts[c['uuid']] = dict(ref=c['ref'], role='connector', external='cable')
        for num, n, _, _ in c['pads']:
            if not n or n in gnd:
                continue
            pr = next((q for q in prot if n in nets(parts[q])), None)
            if pr is None:
                continue
            tgt = next((q for q, ic in enumerate(parts) if is_ic(ic) and q != pr and n in nets(ic)), None)
            pp = parts[pr]
            chain = [[c['uuid'], num], [pp['uuid'], next(m for m, nn, _, _ in pp['pads'] if nn == n)]]
            if tgt is not None:
                chain.append([parts[tgt]['uuid'], next(m for m, nn, _, _ in parts[tgt]['pads'] if nn == n)])
            S.append(dict(id=f"esd:{c['ref']}.{num}", kind='connector_chain', connector=c['uuid'], chain=chain,
                          protection=[pp['uuid']], external='cable', confidence=0.6))
    # heat sources: regulators, large ICs
    for j, p in enumerate(parts):
        if not is_ic(p) and not (_pfx(p['ref']) in ('U', 'VR') and len(p['pads']) >= 3):
            continue
        if any(s.get('ref') == p['uuid'] and s['kind'] == 'heat_source' for s in S):
            continue
        txt = p['value'] + ' ' + p['lib']
        if REG_RE.search(txt):
            pn = sorted(nets(p) & rails)
            vin = max((PR_volts(n) or 0) for n in pn) if pn else None
            vout = min((PR_volts(n) or 99) for n in pn) if pn else None
            P, _ = PR.source_power_prior('ldo', vin, vout if vout != 99 else None, len(p['pads']), p['lib'])
            S.append(dict(id=f"heat:{p['ref']}", kind='heat_source', ref=p['uuid'], P_W=P, confidence=0.5))
        elif len(p['pads']) > 32:
            P, _ = PR.source_power_prior('mcu', n_pins=len(p['pads']))
            S.append(dict(id=f"heat:{p['ref']}", kind='heat_source', ref=p['uuid'], P_W=P, confidence=0.4))
    # thermal victims
    for j, p in enumerate(parts):
        txt = p['value'] + ' ' + p['lib']
        cls = None
        if is_cap(p) and re.search(r'Elec|CP_|Polarized|Tantal', p['lib'], re.I) and 'Tantal' not in p['lib']:
            cls = 'electrolytic'
        elif SENS_RE.search(txt):
            cls = 'sensor'
        elif REF_RE.search(txt):
            cls = 'reference'
        elif _pfx(p['ref']) == 'BT' or re.search(r'Battery', p['lib'], re.I):
            cls = 'battery'
        if cls:
            S.append(dict(id=f"tv:{p['ref']}", kind='thermal_victim', ref=p['uuid'], **{'class': cls}, confidence=0.5))
    netinfo = {n: dict(role='ground') for n in gnd}
    for n in rails:
        netinfo[n] = dict(role='rail', volts=PR_volts(n))
    for n in sw_nets:
        netinfo[n] = dict(role='switch_node')
    return dict(source='kae.physics.provisional_brief (test stand-in)', nets=netinfo, parts=briefparts, structures=S)


def PR_volts(name):
    from .build import _volts
    return _volts(name)
