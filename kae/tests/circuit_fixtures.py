# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Small boards for the kae.circuit tests, built from kae.board.model (Contract 1) dataclasses.

Positions are all zero: comprehension must not need them. Helpers take nets in pin order:
`R('R1', '10k', 'A', 'B')` is a resistor from net A (pad 1) to net B (pad 2); `D(ref, value, k, a)`
puts the cathode on pad 1 (KiCad's convention); `IC(ref, value, lib, [(num, function, net, type), ...])`.
"""
from kae.board.model import Board, Footprint, Net, Pad


def fp(ref, value, lib_id, pins, fields=None, attrs=None, sheet=''):
    pads = []
    for num, net, fn, typ in pins:
        pads.append(Pad(number=str(num), net=net or '', kind='smd', shape='rect', size=(1.0, 1.0), lx=0.0, ly=0.0, lrot=0.0,
                        x=0.0, y=0.0, pinfunction=fn or '', pintype=typ or ''))
    f = dict(fields or {})
    f.setdefault('Reference', ref)
    f.setdefault('Value', value)
    return Footprint(ref=ref, value=value, lib_id=lib_id, uuid=f'uuid-{ref}', x=0.0, y=0.0, rot=0.0, side='F', locked=False,
                     attrs=list(attrs or ['smd']), fields=f, pads=pads, sheet=sheet)


def board(fps, netclasses=None):
    nets = {}
    for f in fps:
        for p in f.pads:
            if p.net:
                n = nets.setdefault(p.net, Net(name=p.net, netclass=(netclasses or {}).get(p.net, 'Default')))
                n.pads.append((f.ref, p.number))
    return Board(path='fixture.kicad_pcb', version=20250114, footprints=list(fps), nets=nets)


def R(ref, value, a, b, lib='Resistor_SMD:R_0402_1005Metric', **kw):
    return fp(ref, value, lib, [('1', a, '', 'passive'), ('2', b, '', 'passive')], **kw)


def C(ref, value, a, b, lib='Capacitor_SMD:C_0402_1005Metric', **kw):
    return fp(ref, value, lib, [('1', a, '', 'passive'), ('2', b, '', 'passive')], **kw)


def L(ref, value, a, b, lib='Inductor_SMD:L_1210_3225Metric', **kw):
    return fp(ref, value, lib, [('1', a, '', 'passive'), ('2', b, '', 'passive')], **kw)


def D(ref, value, k, a, lib='Diode_SMD:D_SOD-123', **kw):
    return fp(ref, value, lib, [('1', k, 'K', 'passive'), ('2', a, 'A', 'passive')], **kw)


def Q(ref, value, g, d, s, lib='Package_TO_SOT_SMD:SOT-23', **kw):
    return fp(ref, value, lib, [('1', g, 'G', 'input'), ('2', s, 'S', 'passive'), ('3', d, 'D', 'passive')], **kw)


def IC(ref, value, lib, pins, **kw):
    return fp(ref, value, lib, [(n, net, fn, t) for n, fn, net, t in pins], **kw)


# ------------------------------------------------------------------------------- reusable circuits
def buck_board():
    """12 V -> 3.3 V synchronous buck (integrated switches), with a feedback divider, an MCU load."""
    u = IC('U1', 'TPS54202', 'Package_TO_SOT_SMD:SOT-23-6', [
        ('1', 'GND', 'GND', 'power_in'), ('2', 'SW', 'SW', 'power_out'), ('3', 'VIN', '+12V', 'power_in'),
        ('4', 'FB', 'FB', 'input'), ('5', 'EN', '+12V', 'input'), ('6', 'BOOT', 'BST', 'passive')])
    parts = [
        u,
        C('C1', '10uF', '+12V', 'GND', lib='Capacitor_SMD:C_1206_3216Metric'),
        C('C2', '100nF', '+12V', 'GND'),
        C('C3', '100nF', 'BST', 'SW'),
        L('L1', '10uH 2A', 'SW', '+3V3'),
        C('C4', '22uF', '+3V3', 'GND', lib='Capacitor_SMD:C_0805_2012Metric'),
        C('C5', '22uF', '+3V3', 'GND', lib='Capacitor_SMD:C_0805_2012Metric'),
        R('R1', '45.3k', '+3V3', 'FB'),
        R('R2', '10k', 'FB', 'GND'),
        fp('J1', 'Barrel_Jack', 'Connector_BarrelJack:BarrelJack_Horizontal',
           [('1', '+12V', '', 'passive'), ('2', 'GND', '', 'passive')]),
    ]
    return parts


def mcu_parts(rail='+3V3', sheet=''):
    """An STM32 with four VDD pins, VDDA, a crystal and decoupling."""
    pins = [('1', 'VDD', rail, 'power_in'), ('2', 'VDD', rail, 'power_in'), ('3', 'VDD', rail, 'power_in'),
            ('4', 'VDD', rail, 'power_in'), ('5', 'VDDA', '+3V3A', 'power_in'), ('6', 'VSS', 'GND', 'power_in'),
            ('7', 'VSS', 'GND', 'power_in'), ('8', 'PH0-OSC_IN', 'XIN', 'input'), ('9', 'PH1-OSC_OUT', 'XOUT', 'output'),
            ('10', 'NRST', 'NRST', 'input'), ('11', 'PA11', 'USB_DM', 'bidirectional'), ('12', 'PA12', 'USB_DP', 'bidirectional'),
            ('13', 'PA0', 'ADC_IN0', 'bidirectional'), ('14', 'BOOT0', 'BOOT0', 'input')]
    return [
        IC('U2', 'STM32F405RGT6', 'Package_QFP:LQFP-64_10x10mm_P0.5mm', pins, sheet=sheet),
        C('C10', '100nF', rail, 'GND', sheet=sheet), C('C11', '100nF', rail, 'GND', sheet=sheet),
        C('C12', '100nF', rail, 'GND', sheet=sheet), C('C13', '100nF', rail, 'GND', sheet=sheet),
        C('C14', '4.7uF', rail, 'GND', lib='Capacitor_SMD:C_0805_2012Metric', sheet=sheet),
        fp('FB1', 'BLM18PG121SN1', 'Inductor_SMD:L_0603_1608Metric', [('1', rail, '', 'passive'), ('2', '+3V3A', '', 'passive')]),
        C('C15', '1uF', '+3V3A', 'GND', sheet=sheet),
        fp('Y1', '8MHz', 'Crystal:Crystal_SMD_3225-4Pin_3.2x2.5mm',
           [('1', 'XIN', '1', 'passive'), ('2', 'GND', '2', 'passive'), ('3', 'XOUT', '3', 'passive'), ('4', 'GND', '4', 'passive')]),
        C('C16', '20pF', 'XIN', 'GND'), C('C17', '20pF', 'XOUT', 'GND'),
        R('R10', '10k', rail, 'NRST'),
        R('R11', '1k', 'SENSOR', 'ADC_IN0'), C('C18', '10nF', 'ADC_IN0', 'GND'),
    ]
