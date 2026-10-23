# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Place terms after the routed-copper calibration (docs/topics/physics/place-terms.md):
expected hop detours, consistent plane referencing, pour-aware decaps, the decap budget
priors, and the batched coupling engine."""
import random

import numpy as np
import pytest
from place_terms_fixtures import NETS, buck_board, cap0402, decap_board, fp
from shapely.geometry import Polygon, box

from kae.board.model import Zone
from kae.physics import jit
from kae.physics import priors as PR
from kae.physics.build import _pour_pairs
from kae.physics.place_terms import Terms
from kae.physics.priors import Knobs
from kae.physics.structures import CmComp, DecapLoop, LoopComp


def _terms(b, brief, **kn):
    return Terms(b, brief, knobs=Knobs(jit='off', **kn))


def _decap_value(T):
    return next(s for s in T.structs if s.kind == 'decap')


# ----------------------------------------------------------------------------- detours
def test_detour_knob_semantics():
    k = Knobs()
    assert k.detour('decap') == PR.HOP_DETOUR['decap']
    assert Knobs(hop_detour=0.0).detour('decap') == 0.0
    assert Knobs(hop_detour={'decap': 0.3}).detour('decap') == 0.3
    assert Knobs(hop_detour={'decap': 0.3}).detour('esd') == PR.HOP_DETOUR['esd']


def test_detour_stretches_far_hops_more():
    """1 + c sqrt(l): the far decap's loop grows by more than the near one's."""
    ratios = []
    for x in (17.0, 5.0):
        b, brief = decap_board(cap_xy=(x, 20.0))
        T0 = _terms(b, brief, hop_detour=0.0)
        T1 = _terms(b, brief)
        ratios.append(T1.breakdown(T1.bv.pose0())[0]['value'] / T0.breakdown(T0.bv.pose0())[0]['value'])
    assert 1.0 < ratios[0] < ratios[1]


# ----------------------------------------------------------------------------- plane referencing
def test_hop_over_a_hole_keeps_its_plane():
    """A straight hop crossing a hole in the ground plane (or a notch of the outline) is
    routed round it over the plane: the loop must not turn into a free-space loop."""
    b, brief = decap_board(cap_xy=(45.0, 20.0))
    T = _terms(b, brief, hop_detour=0.0)
    v_full = T.breakdown(T.bv.pose0())[0]['value']
    hole = Polygon(box(0, 0, 60, 40).exterior.coords, [box(28, 15, 36, 25).exterior.coords])
    b.zones = [Zone(uuid='zh', name='', net='GND', layers=['In1.Cu'], outline=hole)]
    T = _terms(b, brief, hop_detour=0.0)
    v_hole = T.breakdown(T.bv.pose0())[0]['value']
    assert v_hole == pytest.approx(v_full, rel=0.05)
    b.zones = []
    T = _terms(b, brief, hop_detour=0.0)
    assert T.breakdown(T.bv.pose0())[0]['value'] > 2.0 * v_full        # no plane at all: much larger


# ----------------------------------------------------------------------------- pour-aware decaps
def _pour_board(cap_x, rail_zone=None):
    b, brief = decap_board(cap_xy=(cap_x, 20.0))
    rz = rail_zone or box(0, 0, 60, 40)
    b.zones = [Zone(uuid='zg', name='', net='GND', layers=['In1.Cu'], outline=box(0, 0, 60, 40)),
               Zone(uuid='zr', name='', net='3V3', layers=['In2.Cu'], outline=rz),
               Zone(uuid='zo', name='', net='GND', layers=['F.Cu'], outline=box(0, 0, 60, 40))]
    return b, brief


def test_pour_pairs_prefer_inner_layers():
    b, brief = _pour_board(45.0)
    T = _terms(b, brief)
    from kae.physics.build import _Ctx
    pairs = _pour_pairs(_Ctx(T), '3V3')
    assert pairs[0][:2] == ('In2.Cu', 'In1.Cu')          # inner pair before the outer F.Cu pour
    assert all(a != b_ for a, b_, _ in pairs)


def test_far_decap_through_pours_is_cheap_and_falls_back_off_the_pour():
    b, brief = _pour_board(45.0)
    T = _terms(b, brief)
    c = _decap_value(T).comps[0]
    assert isinstance(c, DecapLoop)
    v_pour = c.value(T.st)
    assert c.mode == 'pour'
    v_hops = c.loop.value(T.st)
    assert v_pour < 0.3 * v_hops                         # 25 mm through a plane pair vs a 25 mm trace
    near = _pour_board(17.0)
    Tn = _terms(*near)
    v_near = _decap_value(Tn).comps[0].value(Tn.st)
    assert v_near < v_pour                               # spreading still grows with distance
    # the rail pour covers only the left half: the far cap is off it, the loop is straight hops
    b, brief = _pour_board(45.0, rail_zone=box(0, 0, 30, 40))
    T = _terms(b, brief)
    c = _decap_value(T).comps[0]
    assert c.value(T.st) == pytest.approx(c.loop.value(T.st))
    assert c.mode == 'hops'
    assert _terms(*_pour_board(45.0), pour_decaps=False).structs[0].comps[0].__class__ is LoopComp


# ----------------------------------------------------------------------------- decap budgets
def test_stability_and_module_priors():
    for f in ('bypass', 'regulator_output'):
        assert PR.decap_budget(1.2, 100, 1, function=f).value == PR.L_STABILITY_NH
    assert PR.decap_budget(3.3, 40, 1, module=True).value == PR.L_STABILITY_NH


def test_transient_splits_over_all_power_pins_of_the_ic():
    """A 100-pin MCU's single VDDA pin is charged its share of the IC's transient, not all of it."""
    one = PR.decap_budget(3.3, 100, 1).value
    split = PR.decap_budget(3.3, 100, 1, n_ic_power_pins=8).value
    assert split == pytest.approx(8 * one)
    assert PR.decap_budget(3.3, 100, 6, n_ic_power_pins=8).value == pytest.approx(split)


def test_bypass_spec_gets_the_stability_budget():
    b, brief = decap_board(cap_xy=(17.0, 20.0))
    brief['structures'][0]['function'] = 'bypass'
    T = _terms(b, brief)
    assert _decap_value(T).alloc.value == PR.L_STABILITY_NH


def test_unpaired_capacitor_joins_the_pin_in_parallel():
    """A capacitor the brief does not pair with the pin still serves it if it sits nearer."""
    b, brief = decap_board(cap_xy=(40.0, 20.0))
    c2 = cap0402('C2', '3V3', 'GND', 16.5, 20.0)
    b.footprints.append(c2)
    s = brief['structures'][0]
    s['caps'] = s['hf_caps'] = ['uuid-C1', 'uuid-C2']
    s['caps_p'] = {'uuid-C1': 0.95, 'uuid-C2': 0.6}
    brief['parts']['uuid-C2'] = {'ref': 'C2', 'kind': 'capacitor', 'role': 'decoupling'}
    T = _terms(b, brief)
    st = _decap_value(T)
    assert st.labels == ['C1', 'C2']
    vals = [c.value(T.st) for c in st.comps]
    assert T.breakdown(T.bv.pose0())[0]['value'] < min(vals)


# ----------------------------------------------------------------------------- coupling engine
def test_engine_matches_single_evaluations_and_delta_is_exact():
    b, brief = buck_board()
    T = Terms(b, brief, knobs=Knobs(jit='auto'))
    p = T.bv.pose0()
    T.total(p)
    assert T.engine is not None
    for s in T.structs:
        for ci, c in enumerate(s.comps):
            if hasattr(c, 'subparts'):
                k = T.structs.index(s)
                assert T._cv[k][ci] == pytest.approx(c.value_sub(T.st, 0) + c.value_sub(T.st, 1), rel=1e-9, abs=1e-12)
    T2 = Terms(b, brief, knobs=Knobs(jit='auto'))
    rng = random.Random(3)
    uu = sorted(T.parts())
    poses = dict(p)
    for _ in range(60):
        us = rng.sample(uu, 1 if rng.random() < 0.7 else 2)
        newp = []
        for u in us:
            x, y, r, sd = poses[u]
            newp.append((x + rng.uniform(-4, 4), y + rng.uniform(-4, 4), (r + rng.choice([0, 90])) % 360, sd))
        d = T.delta(poses, us, newp)
        p2 = dict(poses)
        p2.update(zip(us, newp))
        full = T2.total(p2) - T2.total(poses)
        assert d == pytest.approx(full, rel=1e-7, abs=1e-9)
        if rng.random() < 0.5:
            poses = p2


def test_cable_pickup_window():
    """CmComp is exactly zero once the copper gap passes cm_r1_mm and continuous before."""
    nb = jit.PY
    assert nb.window(0.0, 15.0, 30.0) == 1.0
    assert nb.window(30.0, 15.0, 30.0) == 0.0
    assert nb.window(22.5, 15.0, 30.0) == pytest.approx(0.5)
    b, brief = buck_board()
    T = _terms(b, brief)
    cm = [c for s in T.structs if s.kind == 'world_cm' for c in s.comps if isinstance(c, CmComp)]
    assert cm
    c = cm[0]
    i = c.cl.T[0].i
    x0 = T.st.X[i]
    vals = []
    for dx in (0.0, 60.0, 200.0):
        T.st.set(i, x0 + dx, T.st.Y[i], T.st.R[i], T.st.G[i])
        vals.append(c.value(T.st))
    assert vals[0] > 0.0 and vals[-1] == 0.0


def test_engine_inductive_term_is_the_loop_mutual():
    """The engine's inductive sub-term is k_l |M| of the two loops (jit.loop_mutual_core)."""
    b, brief = buck_board()
    T = Terms(b, brief, knobs=Knobs(jit='off'))
    T.total(T.bv.pose0())
    c = next(c for s in T.structs if s.kind == 'coupling' for c in s.comps if c.k_l)
    h = T.bv.h_ref(T.st.G[c.al.T[0].i], *c.al.geo(T.st)[1])
    zb = 1.6 if h == float('inf') else h
    sc = [np.zeros((512, 3)) for _ in range(4)]
    m = jit.PY.loop_mutual_core(c.al.arr(T.st), c.al.closed, zb + c.al.z, c.tl.arr(T.st), c.tl.closed, zb + c.tl.z, h,
                                *jit.GAUSS, *sc)
    assert c.value_sub(T.st, 0) == pytest.approx(c.k_l * m, rel=1e-12)


def test_board_with_a_notch_keeps_the_loop_referenced():
    """doorman: straight decap hops across a notch of the outline, where no plane is; the
    route goes round it over the plane, so the loop stays referenced."""
    from place_terms_fixtures import board
    d3 = fp('D3', 'LED_SMD:LED_WS2812B', [('1', '3V3', -2.0, 0.5, 0.8, 0.8), ('3', 'GND', -2.0, -0.5, 0.8, 0.8)],
            55.0, 10.0)
    c1 = cap0402('C1', '3V3', 'GND', 5.0, 12.0)
    brief = dict(nets=NETS, parts={'uuid-D3': {'ref': 'D3', 'kind': 'led'}, 'uuid-C1': {'ref': 'C1', 'kind': 'capacitor'}},
                 structures=[dict(id='decap:D3:3V3', kind='decap', confidence=0.9, ic='uuid-D3', power_pins=['1'],
                                  ground_pins=['3'], rail='3V3', ground='GND', caps=['uuid-C1'], hf_caps=['uuid-C1'],
                                  caps_p={'uuid-C1': 0.9}, pin_caps={'1': ['uuid-C1']}, function='load')])
    vals = []
    for notch in (None, box(12, 0, 48, 15)):
        b = board([d3, c1], planes=())
        out = box(0, 0, 60, 40) if notch is None else box(0, 0, 60, 40).difference(notch)
        b.outline = [out]
        b.zones = [Zone(uuid='zg', name='', net='GND', layers=['In1.Cu'], outline=out)]
        T = _terms(b, brief, hop_detour=0.0)
        vals.append(T.breakdown(T.bv.pose0())[0]['value'])
    assert vals[1] == pytest.approx(vals[0], rel=0.02)


# ----------------------------------------------------------------------------- kae.brief/1 schema
def _two_pin_ic_board(pairing, caps_p):
    """U1 with two 3V3 pins 8 mm apart and two caps, one beside each pin."""
    u1 = fp('U1', 'Package_QFP:LQFP-32', [('1', '3V3', -4.0, 0.0, 0.8, 0.3), ('2', 'GND', -4.0, -0.8, 0.8, 0.3),
                                           ('3', '3V3', 4.0, 0.0, 0.8, 0.3), ('4', 'GND', 4.0, -0.8, 0.8, 0.3),
                                           ('5', 'S', 0.0, 4.0, 0.3, 0.8)], 30.0, 20.0, court=box(-4.6, -4.6, 4.6, 4.6))
    c1 = cap0402('C1', '3V3', 'GND', 24.5, 20.0)
    c2 = cap0402('C2', '3V3', 'GND', 35.5, 20.0)
    from place_terms_fixtures import board
    b = board([u1, c1, c2])
    brief = dict(nets=NETS, parts={f'uuid-{r}': {'ref': r, 'kind': k} for r, k in
                                   (('U1', 'ic'), ('C1', 'capacitor'), ('C2', 'capacitor'))},
                 structures=[dict(id='decap:U1:3V3', kind='decap', confidence=0.9, ic='uuid-U1', power_pins=['1', '3'],
                                  ground_pins=['2', '4'], rail='3V3', ground='GND', caps=['uuid-C1', 'uuid-C2'],
                                  hf_caps=['uuid-C1', 'uuid-C2'], caps_p=caps_p, pin_caps={}, pairing=pairing,
                                  function='load')])
    return b, brief


def test_nearest_pin_charges_each_cap_to_its_nearest_pin():
    b, brief = _two_pin_ic_board('nearest_pin', {'uuid-C1': 0.9, 'uuid-C2': 0.9})
    T = _terms(b, brief)
    ds = [s for s in T.structs if s.kind == 'decap']
    assert sorted(s.id for s in ds) == ['decap:U1:3V3#C1', 'decap:U1:3V3#C2']
    v = {s.id: T.breakdown(T.bv.pose0())[k]['value'] for k, s in enumerate(T.structs) if s.kind == 'decap'}
    # both caps sit beside a pin: their loops are short and alike
    assert abs(v['decap:U1:3V3#C1'] - v['decap:U1:3V3#C2']) < 0.2 * max(v.values())
    # moving C2 beside pin 1 keeps it cheap: it then serves pin 1
    u = 'uuid-C2'
    p = T.bv.pose0()
    d = T.delta(p, [u], [(24.5, 22.0, 0.0, 'F')])
    assert abs(d) < 0.2


def test_unowned_caps_and_rail_groups_go_to_the_nearest_load():
    b, brief = _two_pin_ic_board('pin', {'uuid-C1': 0.9, 'uuid-C2': 0.3})
    brief['structures'][0]['pin_caps'] = {'1': ['uuid-C1']}
    T = _terms(b, brief)
    ids = sorted(s.id for s in T.structs if s.kind == 'decap')
    assert 'decap:3V3:C2:nearest' in ids
    near = next(s for s in T.structs if s.id == 'decap:3V3:C2:nearest')
    assert near.info['pairing'] == 'nearest_load'
    # a rail group limits the candidates to its loads
    brief['structures'].append(dict(id='rg:3V3', kind='rail_group', rail='3V3', ground='GND', loads=['uuid-U1'],
                                    caps=['uuid-C2'], pairing='nearest_load'))
    T = _terms(b, brief)
    near = next(s for s in T.structs if s.id == 'decap:3V3:C2:nearest')
    assert near.info['rail_group'] == 'rg:3V3'


def test_nearest_load_cache_keeps_delta_exact():
    """NearestLoopComp caches each candidate's loop against its parts' pose ids: random
    moves with accepts must still give delta == the total difference of a fresh Terms."""
    b, brief = _two_pin_ic_board('pin', {'uuid-C1': 0.9, 'uuid-C2': 0.3})
    brief['structures'][0]['pin_caps'] = {'1': ['uuid-C1']}
    T = _terms(b, brief)
    near = next(s for s in T.structs if s.id == 'decap:3V3:C2:nearest')
    assert len(near.comps[0].loops) == 2
    poses = dict(T.bv.pose0())
    T.total(poses)
    rng = random.Random(5)
    uu = ['uuid-U1', 'uuid-C1', 'uuid-C2']
    for _ in range(40):
        u = rng.choice(uu)
        x, y, r, sd = poses[u]
        q = (x + rng.uniform(-6, 6), y + rng.uniform(-3, 3), (r + rng.choice([0, 90, 180])) % 360, sd)
        d = T.delta(poses, [u], [q])
        p2 = dict(poses)
        p2[u] = q
        T2 = _terms(b, brief)
        assert d == pytest.approx(T2.total(p2) - T2.total(poses), rel=1e-7, abs=1e-9)
        if rng.random() < 0.5:
            poses = p2


def test_power_path_loop_and_budget():
    b, brief = buck_board()
    brief['structures'].append(dict(id='path:D2', kind='power_path', confidence=0.8, **{'class': 'ideal_diode'},
                                    switches=['uuid-D2'], stages=[['uuid-D2']], rail_in='VIN', rail_out='SW',
                                    gnd='GND', loop=[['uuid-C2', '1'], ['uuid-D2', '2'], ['uuid-D2', '1'],
                                                     ['uuid-C2', '2']], excite={'V': 12.0, 'I': 2.0}))
    T = _terms(b, brief)
    pp = next(s for s in T.structs if s.kind == 'power_path')
    assert pp.alloc.value == pytest.approx(PR.power_path_budget(12.0, 2.0).value)
    assert PR.power_path_budget(12.0, 2.0).value == pytest.approx(0.05 * 12.0 * 100.0 / 2.0)
    assert T.breakdown(T.bv.pose0())[T.structs.index(pp)]['value'] > 0.0


def test_decap_budget_held_to_careful_layout():
    """The budget lies between the loop of the capacitor beside the pin (L_c) and 2 L_c, so
    a careful layout is within budget and a far capacitor is over it."""
    assert PR.decap_careful(0.3, 1.5) == 1.5            # unattainable target: floor at L_c
    assert PR.decap_careful(40.0, 1.5) == 3.0           # loose target: 2 L_c
    assert PR.decap_careful(2.0, 1.5) == 2.0
    assert PR.decap_careful(10.0, 12.0, hf=False) == 12.0
    us = []
    for x in (16.8, 4.0):
        b, brief = decap_board(cap_xy=(x, 20.5), cap_rot=180.0)
        T = _terms(b, brief)
        r = T.breakdown(T.bv.pose0())[0]
        lc = r['info']['L_careful']
        assert lc <= r['alloc']['value'] <= 2.0 * lc + 1e-9
        us.append(r['util'])
    assert us[0] <= 1.0 < us[1]
