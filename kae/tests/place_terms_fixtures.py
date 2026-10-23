# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Small positioned boards and hand-written physics briefs for the kae.physics tests.

Built from kae.board.model (Contract 1) dataclasses; units mm. `pads` are given as
(number, net, lx, ly, w, h) in the library frame; parts default to the front side.
"""
from shapely.geometry import box

from kae.board.model import Board, Footprint, Net, Pad, Rules, Stackup, Zone


def fp(ref, lib, pads, x, y, rot=0.0, side='F', value='', court=None, kind='smd'):
    ps = [Pad(number=str(n), net=net, kind=kind, shape='rect', size=(w, h), lx=lx, ly=ly, lrot=0.0, x=0.0, y=0.0,
              layers=['F.Cu'])
          for n, net, lx, ly, w, h in pads]
    if court is None:
        xs = [p.lx for p in ps]
        ys = [p.ly for p in ps]
        hw = max(p.size[0] for p in ps) / 2 + 0.25
        hh = max(p.size[1] for p in ps) / 2 + 0.25
        court = box(min(xs) - hw, min(ys) - hh, max(xs) + hw, max(ys) + hh)
    return Footprint(ref=ref, value=value, lib_id=lib, uuid=f'uuid-{ref}', x=x, y=y, rot=rot, side=side, locked=False,
                     attrs=['smd'], fields={'Reference': ref, 'Value': value}, pads=ps, courtyard=[court])


def cap0402(ref, a, b, x, y, rot=0.0, side='F', value='100nF'):
    return fp(ref, 'Capacitor_SMD:C_0402_1005Metric', [('1', a, -0.5, 0.0, 0.5, 0.55), ('2', b, 0.5, 0.0, 0.5, 0.55)],
              x, y, rot, side, value)


def cap1206(ref, a, b, x, y, rot=0.0, value='10uF'):
    return fp(ref, 'Capacitor_SMD:C_1206_3216Metric', [('1', a, -1.5, 0.0, 1.1, 1.8), ('2', b, 1.5, 0.0, 1.1, 1.8)],
              x, y, rot, 'F', value)


def stack(n=4, thickness=1.6):
    if n == 2:
        return Stackup(copper=['F.Cu', 'B.Cu'], cu_thickness=[0.035, 0.035], gaps=[thickness - 0.07], er=[4.5],
                       thickness=thickness)
    return Stackup(copper=['F.Cu', 'In1.Cu', 'In2.Cu', 'B.Cu'], cu_thickness=[0.035] * 4, gaps=[0.1, thickness - 0.34, 0.1],
                   er=[4.3, 4.5, 4.3], thickness=thickness)


def board(fps, size=(60.0, 40.0), layers=4, planes=(('GND', 'In1.Cu'),)):
    outline = box(0.0, 0.0, size[0], size[1])
    nets = {}
    for f in fps:
        for p in f.pads:
            if p.net:
                nets.setdefault(p.net, Net(name=p.net)).pads.append((f.ref, p.number))
    zones = [Zone(uuid=f'z{k}', name='', net=net, layers=[ly], outline=outline) for k, (net, ly) in enumerate(planes)]
    return Board(path='fixture.kicad_pcb', version=20250114, footprints=list(fps), nets=nets, outline=[outline],
                 zones=zones, stackup=stack(layers), rules=Rules(clearance=0.15, track_min=0.15))


NETS = {'GND': {'role': 'ground'}, '3V3': {'role': 'rail', 'volts': 3.3}, 'VIN': {'role': 'rail', 'volts': 12.0},
        'SW': {'role': 'switch_node'}, 'VOUT': {'role': 'rail', 'volts': 12.0}, 'SENS': {'role': 'analog'},
        'VDDIO': {'role': 'rail', 'volts': 1.8}}


def decap_board(cap_xy=(17.0, 20.0), cap_rot=0.0, layers=4):
    """QFN-ish IC U1 at (20, 20) with 3V3 on pin 1 (-2, 0.5) and GND on pin 2 (-2, -0.5);
    one 0402 decap C1."""
    u1 = fp('U1', 'Package_DFN_QFN:QFN-16', [('1', '3V3', -2.0, 0.5, 0.8, 0.3), ('2', 'GND', -2.0, -0.5, 0.8, 0.3),
                                              ('3', 'SIG', 2.0, 0.5, 0.8, 0.3), ('4', 'SIG2', 2.0, -0.5, 0.8, 0.3),
                                              ('5', 'X1', 0.5, 2.0, 0.3, 0.8), ('6', 'X2', -0.5, 2.0, 0.3, 0.8)],
            20.0, 20.0, court=box(-2.6, -2.6, 2.6, 2.6))
    c1 = cap0402('C1', '3V3', 'GND', cap_xy[0], cap_xy[1], cap_rot)
    b = board([u1, c1], layers=layers, planes=(('GND', 'In1.Cu'),) if layers == 4 else (('GND', 'B.Cu'),))
    brief = dict(nets=NETS, parts={'uuid-U1': {'ref': 'U1', 'kind': 'ic', 'role': 'mcu'},
                                   'uuid-C1': {'ref': 'C1', 'kind': 'capacitor', 'role': 'decoupling'}},
                 structures=[dict(id='decap:U1:3V3', kind='decap', confidence=0.9, ic='uuid-U1', power_pins=['1'],
                                  ground_pins=['2'], rail='3V3', ground='GND', caps=['uuid-C1'], hf_caps=['uuid-C1'],
                                  caps_p={'uuid-C1': 0.95}, pin_caps={'1': ['uuid-C1']}, function='load', shared_by=1)])
    return b, brief


def wide_ic_board(cap_xy, layers=2):
    """The case that collapsed (siderakb pmw3610): an IC whose VDDIO and GND pins sit on
    opposite sides, 10.7 mm apart; one 0402 decap; two-layer board, bottom ground pour."""
    u2 = fp('U2', 'Sensor:PMW3610', [('1', 'VDDIO', -5.35, 0.0, 0.6, 1.0), ('2', 'GND', 5.35, 0.0, 0.6, 1.0),
                                     ('3', 'S1', -5.35, 2.0, 0.6, 1.0), ('4', 'S2', 5.35, 2.0, 0.6, 1.0)],
            30.0, 20.0, court=box(-6.2, -4.5, 6.2, 4.5))
    c3 = cap0402('C3', 'VDDIO', 'GND', cap_xy[0], cap_xy[1], 0.0)
    b = board([u2, c3], layers=layers, planes=(('GND', 'B.Cu'),))
    brief = dict(nets=NETS, parts={'uuid-U2': {'ref': 'U2', 'kind': 'ic', 'role': 'sensor'},
                                   'uuid-C3': {'ref': 'C3', 'kind': 'capacitor', 'role': 'decoupling'}},
                 structures=[dict(id='decap:U2:VDDIO', kind='decap', confidence=0.9, ic='uuid-U2', power_pins=['1'],
                                  ground_pins=['2'], rail='VDDIO', ground='GND', caps=['uuid-C3'], hf_caps=['uuid-C3'],
                                  caps_p={'uuid-C3': 0.95}, pin_caps={'1': ['uuid-C3']}, function='load', shared_by=1)])
    return b, brief


def buck_board(cin_xy=(14.0, 20.0), cap_far=False, p_w=5.4, size=(50.8, 35.6)):
    """A 50 V -> 12 V non-synchronous buck: controller U1 (VIN, SW, GND, FB), catch diode D2,
    inductor L1, input cap C2, electrolytic C1 (thermal victim), a sense divider R1/R2 (an
    analog victim); a connector J1 with a TVS D1 on VIN. The brief puts the whole loss on U1 (as kae.circuit
    does)."""
    u1 = fp('U1', 'Package_SO:SOIC-8-1EP', [('1', 'VIN', -2.5, 1.9, 0.6, 1.5), ('2', 'SW', -0.6, 1.9, 0.6, 1.5),
                                            ('3', 'GND', 0.6, 1.9, 0.6, 1.5), ('4', 'FB', 2.5, 1.9, 0.6, 1.5),
                                            ('9', 'GND', 0.0, 0.0, 2.3, 2.3)], 20.0, 20.0, court=box(-3.2, -3.2, 3.2, 3.2))
    d2 = fp('D2', 'Diode_SMD:D_SMC', [('1', 'SW', -3.4, 0.0, 2.5, 3.3), ('2', 'GND', 3.4, 0.0, 2.5, 3.3)], 20.0, 28.0,
            court=box(-5.2, -3.5, 5.2, 3.5))
    l1 = fp('L1', 'Inductor_SMD:L_12x12mm', [('1', 'SW', -4.9, 0.0, 2.6, 4.6), ('2', 'VOUT', 4.9, 0.0, 2.6, 4.6)],
            34.0, 22.0, court=box(-6.5, -6.5, 6.5, 6.5))
    c2 = cap1206('C2', 'VIN', 'GND', cin_xy[0] if not cap_far else 44.0, cin_xy[1] if not cap_far else 30.0, 90.0)
    c1 = fp('C1', 'Capacitor_SMD:CP_Elec_8x10', [('1', 'VIN', -3.1, 0.0, 3.0, 2.0), ('2', 'GND', 3.1, 0.0, 3.0, 2.0)],
            10.0, 10.0, court=box(-4.6, -4.6, 4.6, 4.6))
    r1 = fp('R1', 'Resistor_SMD:R_0402_1005Metric', [('1', 'VOUT', -0.5, 0.0, 0.5, 0.55), ('2', 'SENS', 0.5, 0.0, 0.5, 0.55)],
            25.0, 14.0, rot=90.0)
    r2 = fp('R2', 'Resistor_SMD:R_0402_1005Metric', [('1', 'SENS', -0.5, 0.0, 0.5, 0.55), ('2', 'GND', 0.5, 0.0, 0.5, 0.55)],
            27.0, 14.0, rot=90.0)
    j1 = fp('J1', 'Connector:Terminal_2P', [('1', 'VIN', 0.0, -2.5, 2.0, 2.0), ('2', 'GND', 0.0, 2.5, 2.0, 2.0)], 4.0, 25.0,
            court=box(-3.0, -5.0, 3.0, 5.0))
    d1 = fp('D1', 'Diode_SMD:D_SMA', [('1', 'VIN', -2.0, 0.0, 1.5, 1.7), ('2', 'GND', 2.0, 0.0, 1.5, 1.7)], 9.0, 30.0,
            court=box(-3.2, -1.6, 3.2, 1.6))
    b = board([u1, d2, l1, c2, c1, r1, r2, j1, d1], size=size, layers=4,
              planes=(('GND', 'In1.Cu'), ('GND', 'In2.Cu'), ('GND', 'B.Cu')))
    parts = {f'uuid-{r}': {'ref': r, 'kind': k, 'role': role} for r, k, role in (
        ('U1', 'ic', 'switching_regulator'), ('D2', 'diode', 'freewheel_diode'), ('L1', 'inductor', 'power_inductor'),
        ('C2', 'capacitor', 'input'), ('C1', 'capacitor', 'bulk'), ('R1', 'resistor', 'divider'),
        ('R2', 'resistor', 'divider'), ('J1', 'connector', 'power_in'), ('D1', 'diode', 'connector_protection'))}
    parts['uuid-J1']['external'] = 'cable'
    cell = dict(id='cell:buck:U1', kind='commutation_cell', confidence=0.95, **{'class': 'buck'},
                loop=[['uuid-C2', '1'], ['uuid-U1', ['1']], ['uuid-U1', ['2']], ['uuid-D2', '1'], ['uuid-D2', '2'],
                      ['uuid-C2', '2']],
                rail='VIN', sw='SW', gnd='GND', excite={'V': 50.0, 'I': 3.3, 't_sw_ns': 5.0}, controller='uuid-U1',
                inductor='uuid-L1', caps=['uuid-C2'], caps_p={'uuid-C2': 0.95},
                switches={'high': 'uuid-U1', 'low': 'uuid-D2', 'rectifier': 'uuid-D2'}, vin='VIN', vout='VOUT')
    structs = [cell,
               dict(id='heat:U1', kind='heat_source', confidence=0.6, part='uuid-U1', P_W=p_w),
               dict(id='tvictim:C1', kind='thermal_victim', confidence=0.8, part='uuid-C1', **{'class': 'electrolytic'}),
               dict(id='victim:analog:SENS', kind='victim', confidence=0.9, **{'class': 'analog'},
                    loop=[['uuid-R2', '2'], ['uuid-R2', '1'], ['uuid-R1', '2']], nets=['SENS']),
               dict(id='chain:J1:1', kind='connector_chain', confidence=0.9, connector='uuid-J1', pin='1', net='VIN',
                    chain=[['uuid-J1', '1'], ['uuid-D1', '1'], ['uuid-U1', '1']], protection=['uuid-D1'],
                    external='cable', pin_kind='power')]
    return b, dict(nets=NETS, parts=parts, structures=structs)
