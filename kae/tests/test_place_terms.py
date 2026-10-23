# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""kae.physics.place_terms: API, incrementality, monotonicity and the physics guards
(docs/topics/physics/place-terms.md)."""
import math
import random

import numpy as np
import pytest

from kae.physics import kernels as K
from kae.physics import priors as PR
from kae.physics.place_terms import Terms
from kae.physics.priors import Knobs

from place_terms_fixtures import buck_board, decap_board, wide_ic_board


def _terms(b, brief, jit='off'):
    return Terms(b, brief, knobs=Knobs(jit=jit))


def _value(T, poses, sid):
    for r in T.breakdown(poses):
        if r['id'] == sid:
            return r['value']
    raise KeyError(sid)


# ----------------------------------------------------------------------------- API
def test_api_parts_structures_breakdown():
    b, brief = buck_board()
    T = _terms(b, brief)
    poses = T.bv.pose0()
    assert {'uuid-U1', 'uuid-C2', 'uuid-D2'} <= T.parts()
    sids = T.structures_of('uuid-C2')
    assert 'cell:buck:U1' in sids
    kinds = {r['kind'] for r in T.breakdown(poses)}
    assert {'commutation', 'coupling', 'esd', 'thermal'} <= kinds
    for r in T.breakdown(poses):
        assert r['unit'] and r['alloc']['value'] > 0 and r['alloc']['basis']
        assert math.isfinite(r['value']) and r['value'] >= 0
        assert r['util'] == pytest.approx(r['value'] / r['alloc']['value'])
    assert T.total(poses) == pytest.approx(sum(r['cost'] for r in T.breakdown(poses)), rel=1e-9)


def test_delta_equals_total_difference():
    b, brief = buck_board()
    T = _terms(b, brief)
    poses = T.bv.pose0()
    rng = random.Random(3)
    uu = sorted(T.parts())
    for _ in range(60):
        u = rng.choice(uu)
        x, y, r, s = poses[u]
        q = (x + rng.uniform(-4, 4), y + rng.uniform(-4, 4), rng.choice((0.0, 90.0, 180.0, 270.0)), s)
        d = T.delta(poses, [u], [q])
        p2 = dict(poses)
        p2[u] = q
        full = T.total(p2) - T.total(poses)
        assert d == pytest.approx(full, rel=1e-6, abs=1e-9)
    # the pose dict may be mutated by the caller between calls
    p3 = dict(poses)
    p3['uuid-C2'] = (14.0, 24.0, 90.0, 'F')
    assert T.total(p3) == pytest.approx(T.total(dict(p3)))


def test_no_structures_no_kernels():
    b, brief = decap_board()
    brief = dict(brief, structures=[])
    T = Terms(b, brief)
    assert T.structs == [] and T.thermal is None and T.kern is None
    assert T.total(T.bv.pose0()) == 0.0


# ----------------------------------------------------------------------------- (b) decap
def test_decap_grows_with_distance_and_bad_orientation():
    vals = []
    for dx in (1.5, 3.0, 6.0, 12.0):
        b, brief = decap_board(cap_xy=(18.0 - dx, 20.0), cap_rot=90.0)
        T = _terms(b, brief)
        vals.append(_value(T, T.bv.pose0(), 'decap:U1:3V3'))
    assert all(b > a for a, b in zip(vals, vals[1:])), vals
    # pad 1 (3V3) facing the IC's 3V3 pin vs reversed
    out = []
    for rot in (180.0, 0.0):
        b, brief = decap_board(cap_xy=(16.5, 20.5), cap_rot=rot)
        T = _terms(b, brief)
        out.append(_value(T, T.bv.pose0(), 'decap:U1:3V3'))
    assert out[1] > out[0]


def test_decap_floor_and_no_collapse_wide_ic():
    """siderakb-pmw3610: with the cap beyond the far (GND) pin the straight VDDIO hop ran
    along the IC's own internal path and cancelled it (0.006 nH). The hop under the part is
    taken on the far layer, and the loop is floored at the parts' mounting loops."""
    b, brief = wide_ic_board(cap_xy=(23.0, 20.0))        # next to the VDDIO pin (the human's choice)
    T = _terms(b, brief)
    near = _value(T, T.bv.pose0(), 'decap:U2:VDDIO')
    b, brief = wide_ic_board(cap_xy=(38.0, 20.0))        # beyond the GND pin: VDDIO hop under the IC
    T = _terms(b, brief)
    far = _value(T, T.bv.pose0(), 'decap:U2:VDDIO')
    assert far >= 0.3
    assert far >= 0.7 * near, (near, far)


def test_decap_positive_for_any_pose():
    b, brief = wide_ic_board(cap_xy=(23.0, 20.0))
    T = _terms(b, brief)
    poses = T.bv.pose0()
    rng = random.Random(1)
    for _ in range(300):
        p2 = dict(poses)
        p2['uuid-C3'] = (rng.uniform(15, 45), rng.uniform(12, 28), rng.choice((0.0, 90.0, 180.0, 270.0)), 'F')
        v = _value(T, p2, 'decap:U2:VDDIO')
        assert v >= 0.3 and math.isfinite(v)


# ----------------------------------------------------------------------------- (a) hot loop
def test_hot_loop_grows_when_input_cap_moves_away():
    b, brief = buck_board()
    T = _terms(b, brief)
    poses = T.bv.pose0()
    base = _value(T, poses, 'cell:buck:U1')
    for dx, dy in ((-4, 0), (-8, 0), (0, -6), (-6, -6)):
        p2 = dict(poses)
        x, y, r, s = poses['uuid-C2']
        p2['uuid-C2'] = (x + dx, y + dy, r, s)
        assert _value(T, p2, 'cell:buck:U1') > base


def test_null_input_voltage_uses_high_prior():
    b, brief = buck_board()
    brief['structures'][0]['excite'] = {'V': None, 'I': 3.3, 't_sw_ns': 5.0}
    brief['nets'] = dict(brief['nets'], VIN={'role': 'rail'})
    T = _terms(b, brief)
    st = [s for s in T.structs if s.id == 'cell:buck:U1'][0]
    assert st.info['V_in'] == PR.V_IN_UNKNOWN.value
    assert st.alloc.value > 0


# ----------------------------------------------------------------------------- (e) thermal
def test_thermal_heat_balance_and_loss_split():
    b, brief = buck_board(p_w=5.4)
    T = _terms(b, brief)
    th = T.thermal
    # the brief's 5.4 W on U1 is split between U1, the catch diode and the inductor
    assert float(th.P.sum()) == pytest.approx(5.4)
    refs = {T.bv.parts[i].ref: p for i, p in zip(th.src, th.P)}
    assert set(refs) == {'U1', 'D2', 'L1'} and refs['U1'] < 5.4
    # mean rise = total power / (h_tot * board area)
    lx, ly = th.box[2], th.box[3]
    htot = (PR.THERMAL['h_top'] + PR.THERMAL['h_bot']) * 1e-6        # W/(K mm^2)
    assert th.T_mean == pytest.approx(5.4 / (htot * lx * ly), rel=0.02)


def test_thermal_term_cannot_dominate_on_small_hot_board():
    """olimex-dcdc: 5.4 W of converter loss on a 51 x 36 mm board makes the whole board hot
    (heat balance), which no placement changes; the budgets apply to the local excess, so
    the human-like placement stays near budget and the electrolytic is not pushed away."""
    b, brief = buck_board(p_w=5.4)
    T = _terms(b, brief)
    poses = T.bv.pose0()
    th = {r['id']: r for r in T.breakdown(poses) if r['kind'] == 'thermal'}
    assert th['thermal:C1']['util'] < 2.0
    assert th['thermal:U1']['util'] < 3.0
    assert th['thermal:U1']['info']['rise_K'] > th['thermal:U1']['info']['board_mean_K']


def test_thermal_kernel_matches_infinite_fin():
    """A source in the middle of a board much larger than lambda: the field is K0(r/lam) /
    (2 pi G_s) (images negligible)."""
    from kae.physics.structures import State, ThermalField
    bv = type('BV', (), {'bbox': (0.0, 0.0, 2000.0, 2000.0)})()
    st = State(3)
    st.set(0, 1000.0, 1000.0, 0.0, 1)
    st.set(1, 1010.0, 1000.0, 0.0, 1)
    st.set(2, 1030.0, 1000.0, 0.0, 1)
    gs, lam = K.fin_params([0.035, 0.035], [1.0, 1.0], 1.53)
    th = ThermalField(bv, [(0, 1.0, 1.0)], [1, 2], gs, lam, rings=1)
    T = th.full(st)
    for t, r in ((1, 10.0), (2, 30.0)):
        assert T[t] - th.T_mean == pytest.approx(K.fin_point(r, gs, lam), rel=0.02)


# ----------------------------------------------------------------------------- (c), (f)
def test_coupling_falls_with_distance():
    b, brief = buck_board()
    T = _terms(b, brief)
    poses = T.bv.pose0()
    vals = []
    for dy in (0.0, 8.0, 20.0):
        p2 = dict(poses)
        for u in ('uuid-R1', 'uuid-R2'):
            x, y, r, s = poses[u]
            p2[u] = (x, y - dy * 0.6, r, s) if dy < 20 else (x + 12.0, y - 10.0, r, s)
        vals.append(_value(T, p2, 'victim:analog:SENS'))
    assert vals[0] > vals[1] > vals[2] > 0


def test_esd_surge_path_grows_with_protector_distance():
    b, brief = buck_board()
    T = _terms(b, brief)
    poses = T.bv.pose0()
    vals = []
    for dx in (0.0, 8.0, 20.0):
        p2 = dict(poses)
        x, y, r, s = poses['uuid-D1']
        p2['uuid-D1'] = (x + dx, y, r, s)
        vals.append(_value(T, p2, 'chain:J1:1'))
    assert vals[0] < vals[1] < vals[2]


# ----------------------------------------------------------------------------- priors and currency
def test_phi_is_continuous_and_saturates():
    for b in (1.0, 4.0):
        for u0 in (1.0, 10.0):
            lo, hi = PR.phi(u0 - 1e-9, b), PR.phi(u0 + 1e-9, b)
            assert hi - lo < 1e-6
    assert PR.phi(1000.0) < 0.05 * (1000.0 + 4.0 * 999.0 ** 2)


def test_ownership_calibration_matches_reliability():
    assert PR.ownership_calibrated(0.24) == pytest.approx(0.52, abs=0.01)
    assert PR.ownership_calibrated(0.96) == pytest.approx(0.91, abs=0.01)
    ps = np.linspace(0.02, 0.98, 30)
    q = [PR.ownership_calibrated(p) for p in ps]
    assert all(b > a for a, b in zip(q, q[1:]))


def test_loss_split_sums_to_total():
    sp = PR.converter_loss_split(5.4, 50.0, 12.0, 3.3, has_diode=True)
    assert sum(sp.values()) == pytest.approx(5.4)
    assert set(sp) == {'ic', 'diode', 'inductor'}
    sp = PR.converter_loss_split(2.0, 12.0, 1.0, 10.0, external_switches=True)
    assert sum(sp.values()) == pytest.approx(2.0) and sp['high'] > sp['low']


# ----------------------------------------------------------------------------- kernels
def test_strip_self_per_length_is_hammerstad_jensen():
    for w, h in ((0.2, 0.1), (1.0, 0.2), (3.0, 0.1)):
        l1, l2 = 40.0, 80.0
        per_len = (K.strip_self(l2, w, h) - K.strip_self(l1, w, h)) / (l2 - l1)
        assert per_len == pytest.approx(K.lprime_hj(w, h), rel=0.01)


def test_rectangular_loop_free_space():
    """Rectangle a x b of round wire radius r in free space, Grover's closed form."""
    a, b, r = 20.0, 10.0, 0.1
    pts = [(0, 0, 1), (a, 0, 1), (a, b, 1), (0, b, 1)]
    segs = [dict(p0=pts[k], p1=pts[(k + 1) % 4], r=r) for k in range(4)]
    d = math.hypot(a, b)
    # nH with lengths in mm; a thin tube (GMD r): no internal-inductance term
    grover = 0.4 * (a * math.log(2 * a / r) + b * math.log(2 * b / r) + 2 * d - a * math.asinh(a / b)
                    - b * math.asinh(b / a) - 2 * (a + b))
    assert K.loop_L(segs, plane=False) == pytest.approx(grover, rel=0.01)


def test_patch_strength_vs_parallel_plate_limit():
    from kae.physics.jit import PY
    # a large patch close to the plane tends to eps0 A / h plus its edge fringe
    A, h = 25.0, 0.1
    c = PY.cext(A, h)
    assert c > K.EPS0 * A / h and c < 1.2 * K.EPS0 * A / h


def test_loop_fast_mixed_plane_heights_and_order_symmetry():
    """loop_fast stays finite when only some strips have no plane, and does not depend on
    segment order for open element sets (regressions reported by the critical router)."""
    import math
    from kae.physics.fastloop import loop_fast
    inf = float('inf')
    H = [(0, 0, 4, 0, 0.5, 0.2), (4, 0, 4, 2, 0.5, 0.2), (4, 2, 0, 2, 0.5, 0.2), (0, 2, 0, 0, 0.5, inf)]
    v = loop_fast(H)
    assert math.isfinite(v) and v > 0
    # two strips leaving one pad: no shared end-to-start corner, so the general rule applies
    a, b = (0, 0, 3, 0, 0.4, 0.3), (0, 0, 2, 1.5, 0.4, 0.3)
    assert abs(loop_fast([a, b]) - loop_fast([b, a])) < 1e-12
    # strips over no plane still use the exact corner formula (inf == inf counts as same height)
    Hn = [(0, 0, 4, 0, 0.5, inf), (4, 0, 4, 2, 0.5, inf), (4, 2, 0, 2, 0.5, inf), (0, 2, 0, 0, 0.5, inf)]
    assert math.isfinite(loop_fast(Hn)) and loop_fast(Hn) > 0
