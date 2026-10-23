# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The physics brief (kae.circuit.brief): the agreed shape, uuid keys, and independence from positions."""
import copy
import json
import os
import random

import pytest
from circuit_fixtures import C, IC, board, buck_board, fp, mcu_parts

from kae.circuit.brief import build

KINDS = {'commutation_cell', 'decap', 'crystal', 'oscillator', 'connector_chain', 'victim', 'heat_source', 'thermal_victim', 'antenna',
         'power_path', 'rail_group'}
NET_ROLES = {'ground', 'rail', 'switch_node', 'clock', 'high_speed', 'analog', 'rf', 'reset', 'boot', 'signal', 'no_connect'}
REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))


def _strip_runtime(b):
    b = copy.deepcopy(b)
    b['summary'].pop('runtime_s', None)
    return b


def test_brief_shape_and_uuid_members():
    b = build(board(buck_board() + mcu_parts()))
    json.dumps(b)                                          # JSON-ready
    uuids = set(b['parts'])
    assert all(u.startswith('uuid-') for u in uuids)
    assert {d['role'] for d in b['nets'].values()} <= NET_ROLES
    assert b['nets']['+3V3']['role'] == 'rail' and b['nets']['+3V3']['volts'] == 3.3
    for s in b['structures']:
        assert s['kind'] in KINDS and s['id'] and 0.0 <= s['confidence'] <= 1.0 and isinstance(s['evidence'], list)
        for u in s['members_ref']:
            assert u in uuids
    cell = next(s for s in b['structures'] if s['kind'] == 'commutation_cell')
    assert cell['class'] == 'buck' and {'rail', 'sw', 'gnd', 'loop', 'excite'} <= set(cell)
    assert all(t[0] in uuids for t in cell['loop'])
    assert cell['loop'][0][0] == cell['loop'][-1][0]       # closed on the commutation capacitor
    assert {'V', 'I', 't_sw_ns'} <= set(cell['excite'])
    dec = next(s for s in b['structures'] if s['kind'] == 'decap')
    assert {'ic', 'power_pins', 'ground_pins', 'rail', 'ground', 'caps'} <= set(dec) and dec['ic'] in uuids
    x = next(s for s in b['structures'] if s['kind'] == 'crystal')
    assert {'ic', 'xin', 'xout', 'crystal', 'load_caps', 'f_Hz'} <= set(x)
    for u, d in b['parts'].items():
        assert {'ref', 'role', 'external', 'P_W'} <= set(d)
    order = [p['priority'] for p in b['placement_order']]
    assert order == sorted(order, reverse=True)
    assert b['placement_order'][0]['id'].startswith('cell:')      # the hot loop goes first


def test_brief_never_reads_positions():
    brd = board(buck_board() + mcu_parts())
    a = _strip_runtime(build(brd))
    rnd = random.Random(7)
    for f in brd.footprints:
        f.x, f.y, f.rot = rnd.uniform(-100, 100), rnd.uniform(-100, 100), rnd.choice([0, 90, 180, 270])
        f.side = rnd.choice(['F', 'B'])
        for p in f.pads:
            p.x, p.y = rnd.uniform(-100, 100), rnd.uniform(-100, 100)
    assert _strip_runtime(build(brd)) == a


def _reference_board():
    # KAE_TASKS points at a tasks directory, as in test_board_corpus.py
    roots = ([os.environ['KAE_TASKS']] if os.environ.get('KAE_TASKS') else []) + \
        [os.path.join(REPO, r, 'tasks') for r in ('kae-work-v2', 'kae-work')]
    for bid in ('pcbcorpus-brenocq-bldc-motor-bldcm-power', 'pcbcorpus-azoninc-doorman-doorman'):
        for root in roots:
            p = os.path.join(root, bid, 'reference', 'board.kicad_pcb')
            if os.path.exists(p):
                return p
    return None


@pytest.mark.skipif(_reference_board() is None, reason='reference boards not prepared (kae-work/tasks)')
def test_real_board_brief_is_position_free():
    from kae.board.kicad_file import load
    brd = load(_reference_board())
    a = _strip_runtime(build(brd))
    assert a['summary']['structures'].get('decap', 0) > 0
    rnd = random.Random(1)
    for f in brd.footprints:
        f.x, f.y = rnd.uniform(0, 300), rnd.uniform(0, 300)
        for p in f.pads:
            p.x, p.y = rnd.uniform(0, 300), rnd.uniform(0, 300)
    assert _strip_runtime(build(brd)) == a


def test_power_path_and_rail_group_members_are_uuids():
    ls = IC('U5', 'TPS22918DBVR', 'Package_TO_SOT_SMD:SOT-23-6', [('1', 'VIN', '+3V3', 'power_in'), ('6', 'VOUT', 'LED_PWR', 'power_out'),
                                                                   ('3', 'ON', 'LED_EN', 'input'), ('2', 'GND', 'GND', 'power_in')])
    leds = [fp(f'D{i}', 'SK6812MINI', 'LED_SMD:LED_SK6812MINI_PLCC4_3.5x3.5mm_P1.75mm',
               [('1', 'LED_PWR', 'VDD', 'power_in'), ('2', f'DO{i}', 'DOUT', 'output'), ('3', 'GND', 'VSS', 'power_in'),
                ('4', f'DO{i - 1}', 'DIN', 'input')]) for i in range(1, 7)]
    parts = buck_board() + mcu_parts() + [ls, C('C40', '1uF', '+3V3', 'GND'), C('C41', '10uF', 'LED_PWR', 'GND', lib='Capacitor_SMD:C_0805_2012Metric')] + \
        leds + [C(f'C{50 + i}', '100nF', 'LED_PWR', 'GND') for i in range(3)]
    b = build(board(parts))
    json.dumps(b)
    uuids = set(b['parts'])
    pp = next(s for s in b['structures'] if s['kind'] == 'power_path')
    assert pp['id'] == 'path:U5' and pp['switches'] == ['uuid-U5'] and pp['stages'] == [['uuid-U5']]
    assert pp['caps_in'] == ['uuid-C40'] and pp['caps_out'] == ['uuid-C41'] and pp['controller'] == 'uuid-U5'
    assert all(t[0] in uuids for t in pp['loop']) and pp['loop'][0][0] == pp['loop'][-1][0] == 'uuid-C40'
    assert {'class', 'rail_in', 'rail_out', 'gnd', 'series', 'group', 'excite', 'R_on_ohm', 'P_W'} <= set(pp)
    import math
    assert pp['priority'] == round(60.0 + 10 * math.log10(1 + pp['P_W']), 2)
    assert b['parts']['uuid-U5']['role'] == 'power_switch' and b['parts']['uuid-U5']['P_W'] >= pp['P_W']
    rg = next(s for s in b['structures'] if s['kind'] == 'rail_group')
    assert rg['id'] == 'rg:LED_PWR' and rg['loads'] == [f'uuid-D{i}' for i in range(1, 7)] and rg['pairing'] == 'nearest_load'
    assert rg['caps'] and all(c in uuids for c in rg['caps']) and set(rg['members_ref'].values()) >= {'D1', 'D6'}
    grouped = [s for s in b['structures'] if s['kind'] == 'decap' and s.get('rail_group') == 'rg:LED_PWR']
    assert grouped and all(s['pairing'] == 'nearest_load' and s['pin_caps'] == {} for s in grouped)
    assert all(s.get('pairing') in ('pin', 'nearest_pin', 'nearest_load') for s in b['structures'] if s['kind'] == 'decap')


def test_power_mux_group_is_the_controller_uuid_and_or_groups_name_the_rail():
    mux = IC('U1', 'TPS2115A', 'Package_SO:TSSOP-8', [('8', 'IN1', 'VUSB', 'power_in'), ('6', 'IN2', 'VBAT', 'power_in'),
                                                     ('7', 'OUT', 'VSYS', 'power_out'), ('5', 'GND', 'GND', 'power_in')])
    parts = [mux, C('C1', '1uF', 'VUSB', 'GND'), C('C2', '1uF', 'VBAT', 'GND'), C('C3', '10uF', 'VSYS', 'GND'),
             fp('J1', 'USB_C', 'Connector_USB:USB_C_Receptacle_GCT_USB4105', [('A4', 'VUSB', 'VBUS', 'passive'), ('A1', 'GND', 'GND', 'passive')])]
    b = build(board(parts))
    ps = [s for s in b['structures'] if s['kind'] == 'power_path']
    assert len(ps) == 2 and all(s['group'] == 'uuid-U1' == s['controller'] for s in ps)
    assert 'uuid-U1' not in {u for s in ps for u in s['members_ref'] if u not in s['switches']}
