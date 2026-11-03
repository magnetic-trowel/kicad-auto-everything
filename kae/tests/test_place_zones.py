# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""kae.place.zones: fixed copper zones as placement facts. The pull term prices pads off their
own net's zone (with a slope toward it), the keep-out term pads whose mask opening would
bridge another net's outer zone; both engines price them alike; weight 0 switches them off."""
import random
from pathlib import Path

import numpy as np
import pytest
from shapely.geometry import box

from kae.board.kicad_file import load
from kae.board.model import Zone
from kae.place import zones as Z
from kae.place.anneal import Annealer
from kae.place.problem import Problem
from kae.place.state import State

FIXTURE = Path(__file__).parent / "data" / "board" / "fixture.kicad_pcb"
ISLAND = (40.0, 10.0, 50.0, 20.0)       # mm: a VCC island on In1.Cu
POUR = (5.0, 25.0, 20.0, 35.0)          # mm: a VCC pour on F.Cu


def _board(mask=None):
    b = load(FIXTURE)
    b.zones = list(b.zones) + [
        Zone(uuid="z-island", name="", net="VCC", layers=["In1.Cu"], outline=box(*ISLAND), priority=2, clearance=0.2),
        Zone(uuid="z-pour", name="", net="VCC", layers=["F.Cu"], outline=box(*POUR), priority=2, clearance=0.2)]
    if mask is not None:
        for f in b.footprints:
            if f.ref == "U1":
                for pd in f.pads:
                    if pd.kind == "smd":      # (a drilled pad would bridge the board-wide B.Cu GND)
                        pd.mask_margin = mask
    return b


def _problem(mask=None):
    P = Problem.build(_board(mask))
    return P, State(P)


def _put(P, st, i, k, x, y, pad):
    """Part i at rotation k with pad `pad` at board (x, y) mm."""
    r = P.parts[i].rots[k]
    st.X[i] = int(round((x - P.ox - r.pins[pad, 0]) / P.g))
    st.Y[i] = int(round((y - P.oy - r.pins[pad, 1]) / P.g))
    st.K[i] = k


def _ref(P):
    return {p.ref: p.i for p in P.parts}


def test_pull_rewards_a_pad_over_its_zone_and_slopes_toward_it():
    P, st = _problem()
    T = Z.build(P, pull=1.0, keepout=0.0)
    assert T is not None and T.info["pull_pads"] > 0
    # the GND pour on B.Cu covers the board: a solid plane, every pad over it anywhere
    assert "GND" in T.info["solid_planes"]
    i = _ref(P)["U1"]
    vcc = [k for k, pd in enumerate(P.parts[i].fp.pads) if pd.net == "VCC"][0]
    cost = []
    for x in (45.0, 52.0, 58.0):
        _put(P, st, i, 0, x, 15.0, vcc)
        cost.append(T.part(i, int(st.X[i]), int(st.Y[i]), 0))
    assert cost[0] == 0.0 < cost[1] < cost[2]          # over it: free; then further costs more
    # the drilled VCC pad reaches the F.Cu pour as well as the In1 island
    _put(P, st, i, 0, 12.0, 30.0, vcc)
    assert T.part(i, int(st.X[i]), int(st.Y[i]), 0) == 0.0
    rep = Z.report(P, st, Z.build(P))
    assert rep["pads_with_zone"] >= rep["pads_on_own_zone"] >= 1


def test_an_smd_pad_reaches_inner_zones_but_not_the_far_side():
    P, st = _problem()
    T = Z.build(P, pull=1.0, keepout=0.0)
    U4 = P.parts[_ref(P)["U4"]]           # a back-side part: its VCC pad is drilled (all layers)
    assert U4.side == "B"
    lays = Z.pad_reach(U4.fp.pads[0], ["In1.Cu"])
    assert lays == {"B.Cu", "In1.Cu"}     # SMD on B.Cu: its layer and the inner ones by a via
    assert T is not None


def test_keepout_prices_only_pads_whose_mask_would_bridge():
    # mask expansion 0 against a 0.2 mm gap: KiCad's fill keeps clear, nothing to price
    P, st = _problem()
    assert Z.build(P, pull=0.0, keepout=1.0) is None or Z.build(P, pull=0.0, keepout=1.0).info["keepout_pads"] == 0
    # 0.5 mm expansion: U1's SIG1 / GND pads on F.Cu would bridge the VCC pour
    P, st = _problem(mask=0.5)
    T = Z.build(P, pull=0.0, keepout=1.0)
    assert T is not None and T.info["keepout_pads"] >= 2
    i = _ref(P)["U1"]
    sig = [k for k, pd in enumerate(P.parts[i].fp.pads) if pd.net == "SIG1"][0]
    _put(P, st, i, 0, 12.0, 30.0, sig)
    inside = T.part(i, int(st.X[i]), int(st.Y[i]), 0)
    _put(P, st, i, 0, 30.0, 15.0, sig)
    assert inside > 0.0 == T.part(i, int(st.X[i]), int(st.Y[i]), 0)
    _put(P, st, i, 0, 12.0, 30.0, sig)
    assert Z.report(P, st, T)["foreign_in_outer_zone"] >= 1


def test_weights_zero_switch_the_term_off():
    P, st = _problem(mask=0.5)
    assert Z.build(P, pull=0.0, keepout=0.0) is None
    T = Z.build(P, pull=1.0, keepout=1.0)
    rng = np.random.default_rng(0)
    for i in P.mov:
        st.X[i], st.Y[i] = rng.integers(50, 550), rng.integers(50, 350)
    a0 = Annealer(P, st.copy(), seed=0)
    a1 = Annealer(P, st.copy(), seed=0, zones=T, w_zone=0.0)
    a2 = Annealer(P, st.copy(), seed=0, zones=T, w_zone=1.0)
    assert a1.cost(1.0) == a0.cost(1.0)
    assert a2.cost(1.0) > a0.cost(1.0)
    assert "zone" not in a1.terms_report() and "zone" in a2.terms_report()


def test_engine_prices_the_zones_like_the_reference():
    engine = pytest.importorskip("kae.place.engine")
    if not engine.HAVE_NUMBA:
        pytest.skip("numba not installed (kae[fast])")
    P, st = _problem(mask=0.5)
    T = Z.build(P, pull=1.0, keepout=1.0)
    rng = np.random.default_rng(1)
    for i in P.mov:
        st.X[i], st.Y[i] = rng.integers(50, 550), rng.integers(50, 350)
    A = Annealer(P, st.copy(), w_cong=30.0, zones=T, w_zone=1.0)
    F = engine.FastAnnealer(P, st.copy(), w_cong=30.0, zones=T, w_zone=1.0)
    E = F.E
    assert abs(A.cost(3.0) - F.cost(3.0)) < 1e-9
    r = random.Random(2)
    changed = 0
    for _ in range(2000):
        i = r.choice(P.mov)
        k = r.randrange(len(P.parts[i].rots))
        X, Y = A.X[i] + r.randint(-150, 150), A.Y[i] + r.randint(-150, 150)
        z0 = A._zone((i,))
        _, da = A.try_move((i,), [(X, Y, k)], 1e30, 3.0, "x")
        changed += A._zone((i,)) != z0
        _, de = engine.try_move(E, np.array([i], np.int64), np.array([X], np.int64), np.array([Y], np.int64),
                                np.array([k], np.int64), 1, 1e30, 3.0, 0.0, 0.0, True)
        assert abs(da - de) < 1e-9 * max(1.0, abs(da))
    assert changed > 50
    assert abs(E.tot[engine.T_ZONE] - A._zone(A.mov)) < 1e-9


def test_lattice_prices_like_part_and_pinning_puts_a_package_over_its_zone():
    from kae.place import seed as seedmod
    P, st = _problem(mask=0.5)
    T = Z.build(P, pull=1.0, keepout=1.0)
    i = _ref(P)["U1"]
    Xs, Ys = np.arange(-20, P.ncx + 20, 37), np.arange(-20, P.ncy + 20, 29)
    for k in range(len(P.parts[i].rots)):
        L = T.lattice(i, k, Xs, Ys)
        for a in range(0, len(Xs), 3):
            for b in range(0, len(Ys), 3):
                assert abs(L[a, b] - T.part(i, int(Xs[a]), int(Ys[b]), k)) < 1e-12
    # with the bar lowered to one pad, U1 is pinned where its VCC pad is over a VCC zone
    objs, owner = seedmod._objects(P, [])
    pos = seedmod.quadratic(P, objs, owner, {n.i: n.weight for n in P.nets})
    pins = Z.pin_packages(T, P, objs, pos, min_pads=1.0)
    assert owner[i] in pins
    X, Y, k = pins[owner[i]][2][i]
    vcc = [kk for kk, pd in enumerate(P.parts[i].fp.pads) if pd.net == "VCC"][0]
    x = P.ox + X * P.g + P.parts[i].rots[k].pins[vcc, 0]
    y = P.oy + Y * P.g + P.parts[i].rots[k].pins[vcc, 1]
    assert (ISLAND[0] <= x <= ISLAND[2] and ISLAND[1] <= y <= ISLAND[3]) or \
           (POUR[0] <= x <= POUR[2] and POUR[1] <= y <= POUR[3])
