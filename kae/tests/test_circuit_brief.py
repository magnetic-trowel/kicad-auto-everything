# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The physics brief (kae.circuit.brief): the agreed shape, uuid keys, and independence from positions."""
import copy
import json
import os
import random

import pytest
from circuit_fixtures import board, buck_board, mcu_parts

from kae.circuit.brief import build

KINDS = {'commutation_cell', 'decap', 'crystal', 'oscillator', 'connector_chain', 'victim', 'heat_source', 'thermal_victim', 'antenna'}
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
    for bid in ('pcbcorpus-brenocq-bldc-motor-bldcm-power', 'pcbcorpus-azoninc-doorman-doorman'):
        for root in ('kae-work-v2', 'kae-work'):
            p = os.path.join(REPO, root, 'tasks', bid, 'reference', 'board.kicad_pcb')
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
