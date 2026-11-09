# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""kae.bus: detection from a bare board and the report-only scorecard (no KiCad needed)."""
import math
from dataclasses import replace

import pytest

from kae.board.model import Board, Footprint, Net, Pad, Track, Via
from kae.bus import detect_board
from kae.bus import limits as L
from kae.bus.scorecard import board_scorecard, open_items_from_drc


def fp(ref, lib, pts, nets, value=''):
    pads = []
    for i, ((x, y), net) in enumerate(zip(pts, nets)):
        pads.append(Pad(number=str(i + 1), net=net, kind='smd', shape='rect', size=(0.4, 0.4), lx=x, ly=y, lrot=0.0,
                        x=x, y=y, layers=['F.Cu'], pinfunction='', pintype=''))
    return Footprint(ref=ref, value=value or ref, lib_id=lib, uuid=f'u-{ref}', x=pts[0][0], y=pts[0][1], rot=0.0, side='F', locked=False,
                     attrs=['smd'], fields={'Reference': ref, 'Value': value or ref}, pads=pads)


def mk_board(fps):
    nets = {}
    for f in fps:
        for p in f.pads:
            n = nets.setdefault(p.net, Net(name=p.net, netclass='Default'))
            n.pads.append((f.ref, p.number))
    return Board(path='x', version=20250114, footprints=fps, nets=nets, layers={'F.Cu': 'signal', 'B.Cu': 'signal'})


def tr(net, *pts, layer='F.Cu', w=0.2):
    return [Track(uuid=f'{net}{i}', net=net, layer=layer, width=w, start=pts[i], end=pts[i + 1]) for i in range(len(pts) - 1)]


CONN = 'Connector_PinHeader_2.54mm:PinHeader_1x08_P2.54mm'


def bend_bus(n=8):
    """n lanes, 1 mm apart, running east then turning to +y: lane i = (0,i) -> (20-i,i) -> (20-i,30)."""
    nets = [f'D{i}' for i in range(n)]
    a = fp('J1', CONN, [(0.0, float(i)) for i in range(n)], nets)
    b = fp('J2', CONN, [(20.0 - i, 30.0) for i in range(n)], nets)
    board = mk_board([a, b])
    for i, net in enumerate(nets):
        board.tracks += tr(net, (0.0, float(i)), (20.0 - i, float(i)), (20.0 - i, 30.0))
    return board


def test_named_bus_detected_and_bare_invariant():
    board = bend_bus()
    bs = detect_board(board)
    assert len(bs.buses) == 1
    assert bs.buses[0]['width'] == 8 and {bs.buses[0]['a'], bs.buses[0]['b']} == {'J1', 'J2'}
    bare = replace(board, tracks=[], vias=[])
    bb = detect_board(bare)
    assert [b['names'] for b in bb.buses] == [b['names'] for b in bs.buses]


def test_scorecard_geometry_and_turning_identity():
    # the identity skew = 2d per 90 degree mitre: lane lengths 50-2i, so skew is 2*(n-1); the turning term predicts it exactly
    n = 5
    card = board_scorecard(bend_bus(n), decompose=True)
    assert card['opens_src'] == 'copper'
    b = card['buses'][0]
    assert b['complete'] and b['lanes_open'] == 0 and b['measured'] == n
    assert b['skew_mm'] == pytest.approx(2 * (n - 1), abs=0.01)
    assert b['vias_lane'] == 0 and b['via_equal'] == 1 and b['layer_agreement'] == 1.0
    dec = b['skew_decomp']
    assert dec['trunked'] == n
    shares = {k: v[0] / dec['mm_yy'] for k, v in dec['mm'].items()}
    assert sum(shares.values()) == pytest.approx(1.0, abs=1e-6)     # terms add up, by construction
    assert shares['turn'] == pytest.approx(1.0, abs=0.15)           # a pure bend: everything is the turning term


def test_opens_come_from_drc_when_given():
    board = bend_bus(4)
    drc = dict(unconnected_items=[dict(items=[dict(description='Pad 1 [D2] of J1 on F.Cu'), dict(description='Pad 1 [D2] of J2 on F.Cu')])])
    b = board_scorecard(board, drc=drc)['buses'][0]
    assert b['lanes_open'] == 1 and not b['complete']


def test_drc_net_names_with_brackets():
    counts, capped = open_items_from_drc(dict(unconnected_items=[dict(items=[dict(description='Pad 2 [sdram_dq[0]] of U4 on F.Cu')])]))
    assert counts == {'sdram_dq[0]': 1} and not capped


def test_vias_count_only_layer_changes_on_the_lane():
    board = bend_bus(3)
    net = 'D1'
    board.tracks = ([t for t in board.tracks if t.net != net] + tr(net, (0.0, 1.0), (10.0, 1.0))
                    + tr(net, (10.0, 1.0), (19.0, 1.0), (19.0, 25.0), layer='B.Cu') + tr(net, (19.0, 25.0), (19.0, 30.0)))
    board.vias = [Via(uuid=f'v{i}', net=net, x=x, y=y, size=0.5, drill=0.2, layers=['F.Cu', 'B.Cu']) for i, (x, y) in enumerate([(10.0, 1.0), (19.0, 25.0)])]
    b = board_scorecard(board)['buses'][0]
    assert b['measured'] == 3 and b['via_max'] == 2 and b['via_spread'] == 2 and b['via_equal'] == 0 and b['via_span_mismatch'] == 1


def test_limits_keyed_by_controller_and_generation():
    fpd = lambda v, c: dict(fp=replace_fp(v), cls=c, kind='ic', subtype=None)
    def replace_fp(v):
        return Footprint(ref='U', value=v, lib_id='', uuid='', x=0, y=0, rot=0, side='F', locked=False, fields={}, pads=[], attrs=[])
    row = dict(kind='ddr_byte', a='U1', b='U2')
    # DDR3 with a recognised controller is keyed to that controller; unrecognised falls back to a marked assumption
    part = {'U1': fpd('MT41K256M16TW', 'dram'), 'U2': fpd('XC7A100T', 'fpga')}
    lim = L.for_bus(row, part)
    assert lim.skew_mm == 0.5 and not lim.keyed
    part['U2'] = fpd('AM625x', 'mcu')
    assert L.for_bus(row, part).keyed and L.for_bus(row, part).skew_mm == 0.3
    assert L.for_bus(dict(kind='connector_ribbon'), {}).skew_mm is None
    assert L.dram_generation('MT40A512M16LY') == 'ddr4'
    assert L.for_bus(dict(kind='pair', iface='USB3'), {}).skew_mm == 0.127
