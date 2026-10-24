# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""kae.physics.exact: PEEC of routed loops against the research solver (pw_peec) and its
validation numbers, oblique filaments against Grover and adaptive quadrature, the finite-volume
thermal operator against tm_board_thermal_fv and ex_exact, and the fidelity switch in the
critical router's module stage (docs/topics/physics/exact-physics-in-kae.md)."""
import math
import sys
from pathlib import Path

import numpy as np
import pytest

from kae.physics import exact as EX
from kae.physics import fastloop as FL
from kae.route.critical_physics import Loop

RESEARCH = Path(__file__).resolve().parents[2] / "tools" / "research" / "physics"


@pytest.fixture(scope="module")
def research():
    if not (RESEARCH / "pw_peec.py").exists():
        pytest.skip("tools/research/physics not present")
    sys.path.insert(0, str(RESEARCH))
    import pw_peec
    return pw_peec


@pytest.fixture(autouse=True)
def _fast():
    with EX.scope("fast"):
        EX.stats(reset=True)
        yield


# ----------------------------------------------------------------------------- PEEC vs pw_peec
def _segs_pieces(segs, t=EX.T_CU):
    """pt_validate_kernels.peec_L's discretization of its routed segments as exact pieces."""
    ps = []
    for s in segs:
        p0, p1 = np.array(s["p0"], float), np.array(s["p1"], float)
        d = p1 - p0
        ax = int(np.argmax(np.abs(d)))
        L = float(abs(d[ax]))
        if L < 1e-9:
            continue
        if ax == 2:
            if "r" in s and not s.get("plate"):
                ps.append(EX.ring(p0[0], p0[1], p0[2], p1[2], s["r"]))
            else:
                bw = s.get("b", 0.5)
                ps.append(EX.bar((p0[0] - 0.015, p0[1] - bw / 2, min(p0[2], p1[2])), 2, L, 0.03, bw, nw=1, nt=8,
                                 reverse=p1[2] < p0[2]))
            continue
        th = s.get("t", t)
        ps.append(EX.strip(p0[:2], p1[:2], s["w"], p0[2], th, nw=EX.nw_strip(s["w"], p0[2], th)))
    return ps


def _loop_of(segs):
    lp = Loop()
    for s in segs:
        p0, p1 = s["p0"], s["p1"]
        if abs(p1[2] - p0[2]) > 1e-9:
            lp.vert(p0[0], p0[1], p0[2], p1[2], s["r"])
        else:
            lp.strip(p0[:2], p1[:2], s["w"], p0[2])
    return lp


CELLS = [(h, w, d, rot, ret) for h in (0.1, 0.4, 1.5) for w, d in ((0.4, 2.5), (0.4, 7.0)) for rot in (0, 90)
         for ret in ("lateral", "via")]


@pytest.fixture(scope="module")
def cells(research):
    import pt_validate_kernels as PT
    out = []
    for h, w, d, rot, ret in CELLS:
        cfg = dict(h=h, w=w, cap=(1.9, 1.25, 0.4), ic=(0.95, 0.3, 0.25), cap_center=(-d, 0.3), cap_rot=rot, ret=ret)
        segs = PT.cell_segments(cfg)
        if segs is not None:
            out.append((cfg, segs, PT.peec_L(segs)))
    return out


def test_peec_reproduces_pw_peec_on_the_validation_loops(cells):
    """The research's hot-loop validation geometry (pt_validate_kernels.cell_segments: A*-
    routed Manhattan loops, PEC plane): exact PEEC equals pw_peec to rounding."""
    assert len(cells) >= 20
    for cfg, segs, ref in cells:
        EX.clear_cache()
        assert EX.network_value({"A": _segs_pieces(segs)}, (), True) == pytest.approx(ref, rel=1e-9)


def test_closed_forms_within_the_validated_band_of_peec(cells):
    """place-terms.md section 2: the closed forms on routed loops are within 5 % of PEEC
    (median), 9.4 % max. Loop.value (the module stage's model) against exact.loop_value on
    the same Loop network."""
    errs = []
    for cfg, segs, ref in cells:
        lp = _loop_of(segs)
        errs.append(abs(lp.value() / EX.loop_value(lp) - 1.0))
    assert float(np.median(errs)) < 0.06
    assert max(errs) < 0.15


def test_pw_validate_numbers(research):
    """pw_peec.exp_validate: square wire over a plane (81.16, 150.63 nH) and a 10 mm strip
    (130.5, 242.7, 549.4 pH), with the same filaments."""
    a, l = 0.5, 200.0
    for h, ref in ((1.0, 81.16), (5.0, 150.63)):
        ps = [EX.bar((-a, -a / 2, 0.0), 2, h - a / 2, a, a, 2, 2),
              EX.bar((0.0, -a / 2, h - a / 2), 0, l, a, a, 4, 4),
              EX.bar((l, -a / 2, 0.0), 2, h - a / 2, a, a, 2, 2, reverse=True)]
        assert EX.network_value({"A": ps}, (), True) == pytest.approx(ref, abs=0.006)
    w = 10.0
    for h, ref_ph in ((0.1, 130.5), (0.2, 242.7), (0.5, 549.4)):
        nw = research._nw(w * 1e-3, h * 1e-3)
        t = 0.035
        ps = [EX.bar((-t, -w / 2, 0.0), 2, h, t, w, 1, nw),
              EX.bar((0.0, -w / 2, h), 0, w, w, t, nw, 1),
              EX.bar((w, -w / 2, 0.0), 2, h, t, w, 1, nw, reverse=True)]
        assert 1e3 * EX.network_value({"A": ps}, (), True) == pytest.approx(ref_ph, abs=0.06)


def test_parallel_returns_match_pw_peecs_nodal_solve(research):
    """A loop whose return runs as a surface track in parallel with vias through the plane:
    the element/KCL formulation equals pw_peec's nodal solve."""
    import ex_exact as EE
    h, w = 0.2, 0.5
    g = EE.LoopGeo(h)
    g.branches = [("N0", "N1", "A", [("strip", (0, 0), (6, 0), w, h)], "board"),
                  ("N1", "N2", "A", [("strip", (6, 0), (6, 3), w, h)], "board"),
                  ("N2", "N3", "lat", [("strip", (6, 3), (0, 3), w, h)], "board"),
                  ("N2", "N3", "via", [("vert", (6, 3), h, 0.0, 0.15), ("vert", (0, 3), 0.0, h, 0.15)], "via"),
                  ("N3", "NE", "A", [("strip", (0, 3), (0, 0), w, h)], "board")]
    ref, _ = EE.peec_L(g)
    lp = Loop()
    lp.path([(0, 0), (6, 0), (6, 3)], w, h)
    lp.strip((6, 3), (0, 3), w, h, "lat")
    lp.vert(6, 3, h, 0.0, 0.15, "via")
    lp.vert(0, 3, 0.0, h, 0.15, "via")
    lp.strip((0, 3), (0, 0), w, h)
    lp.kcl({"lat": 1.0, "via": 1.0})
    val, x = EX.loop_value(lp, shares=True)
    assert val == pytest.approx(ref, rel=1e-9)
    assert x["lat"] + x["via"] == pytest.approx(1.0) and 0 < x["via"] < 1


# ----------------------------------------------------------------------------- oblique filaments
def _fil(a, b):
    return EX.Piece([a], [b], [0.01], key=("f", a, b))


@pytest.mark.parametrize("ang", [30, 45, 60, 120, 135])
def test_corner_filaments_match_grover(ang):
    l1, l2 = 2.0, 1.5
    a = math.radians(ang)
    B = np.array([l1, 0.0, 0.0])
    C = B + l2 * np.array([math.cos(a), math.sin(a), 0.0])
    m = EX.mutual(_fil((0.0, 0.0, 0.0), tuple(B)), B[None], C[None])[0, 0]
    ref = -FL.m_corner(l1, l2, -math.cos(a), float(np.linalg.norm(C)))
    assert m == pytest.approx(ref, rel=1e-5)


def test_oblique_filaments_match_adaptive_quadrature():
    from scipy.integrate import quad
    P = _fil((0.0, 0.0, 0.0), (3.0, 0.0, 0.0))
    for q0, q1 in (((1, 1, 0.2), (2.5, 2.7, 0.2)), ((0.5, 0.05, 0.0), (1.5, 1.2, 0.0)), ((1, -1, 0), (2, 1, 0))):
        q0, q1 = np.array(q0, float), np.array(q1, float)
        lq = float(np.linalg.norm(q1 - q0))
        v = (q1 - q0) / lq

        def F(s):
            r = np.array([s, 0.0, 0.0]) - q0
            tau = float(r @ v)
            rho = math.sqrt(max(float(r @ r) - tau * tau, 1e-30))
            return math.asinh((lq - tau) / rho) + math.asinh(tau / rho)
        I = quad(F, 0.0, 3.0, limit=400, epsabs=1e-12, epsrel=1e-10, points=[1.5])[0]
        ref = 0.1 * float(v[0]) * I
        assert EX.mutual(P, q0[None], q1[None])[0, 0] == pytest.approx(ref, rel=2e-6)


def test_any_angle_loop_is_rotation_invariant():
    """A loop with 45-degree hops, and the same loop turned by 45 degrees (oblique and axis-
    aligned pieces swap): PEEC agrees to quadrature accuracy."""
    pts = [(0, 0), (4, 0), (6, 2), (6, 5), (2, 5), (0, 3)]

    def lp_at(a):
        c, s = math.cos(a), math.sin(a)
        P = [(c * x - s * y, s * x + c * y) for x, y in pts]
        lp = Loop()
        lp.path(P + [P[0]], 0.6, 0.3)
        lp.vert(P[0][0], P[0][1], 0.3, 0.0, 0.15)
        return lp
    v0 = EX.loop_value(lp_at(0.0))
    for a in (math.pi / 4, 0.3):
        assert EX.loop_value(lp_at(a)) == pytest.approx(v0, rel=2e-5)
    # and the closed form is within the validated band of it
    assert lp_at(0.0).value() == pytest.approx(v0, rel=0.10)


# ----------------------------------------------------------------------------- fidelity switch
def _cell_loop(via_x):
    lp = Loop()
    lp.path([(0, 0), (5, 0), (5, 2)], 1.0, 0.2)
    lp.strip((5, 2), (0, 2), 1.0, 0.2, "lat")
    lp.vert(5, 2, 0.2, 0.0, 0.15, "via")
    lp.vert(via_x, 2.4, 0.0, 0.2, 0.15, "via")
    lp.strip((via_x, 2.4), (0, 2), 0.6, 0.2, "via")
    lp.strip((0, 2), (0, 0), 1.0, 0.2)
    lp.kcl({"lat": 1.0, "via": 1.0})
    return lp


def test_loop_value_follows_the_fidelity():
    lp = _cell_loop(0.5)
    cf = lp.value()
    pe = EX.loop_value(lp)
    assert cf != pytest.approx(pe, rel=1e-6)
    with EX.scope("exact"):
        assert lp.value() == pytest.approx(pe, rel=1e-12)
    with EX.scope("multi"):
        assert lp.value() == cf                         # multi searches with the closed forms
        with EX.exact_now():
            assert lp.value() == pytest.approx(pe, rel=1e-12)
    assert lp.value() == cf
    assert EX.stats()["exact_calls"] == 2


def test_pick_keeps_the_fast_choice_unless_multi():
    cands = [(3.0, "a"), (1.0, "b"), (1.0, "c"), (2.0, "d"), (5.0, "e")]
    exact = {"a": 0.5, "b": 2.0, "c": 1.0, "d": 1.5, "e": 0.1}
    assert EX.pick(cands, lambda c: exact[c[1]]) == (1.0, "b")      # first of the lowest
    with EX.scope("exact"):
        assert EX.pick(cands, lambda c: exact[c[1]]) == (1.0, "b")  # values are exact already
    with EX.scope("multi", k=3):
        assert EX.pick(cands, lambda c: exact[c[1]], what="t") == (1.0, "c")   # among b, c, d
        with EX.scope("multi", k=5):
            assert EX.pick(cands, lambda c: exact[c[1]], what="t") == (5.0, "e")
    s = EX.stats()
    assert s["decisions"] == 2 and s["changed"] == 2 and s["what"]["t"] == [2, 2]
    assert EX.pick([], lambda c: 0) is None


def test_final_fidelity_runs_finished_boards_exact():
    lp = _cell_loop(0.5)
    f = EX.final_fidelity(lambda: lp.value())
    assert f() == lp.value()
    with EX.scope("multi"):
        assert f() == pytest.approx(EX.loop_value(lp), rel=1e-12)


def test_cli_flags():
    import argparse
    a = EX.add_cli_args(argparse.ArgumentParser()).parse_args(["--physics-fidelity", "multi", "--physics-k", "3"])
    assert (a.physics_fidelity, a.physics_k) == ("multi", 3)
    with pytest.raises(ValueError):
        EX.configure("bogus")


def test_module_stage_in_every_fidelity(tmp_path):
    """The critical router's module stage on the synthetic board: every fidelity routes the
    same modules legally; multi re-scores its via decisions; the exact value of what it chose
    is no worse than the exact value of the fast choice (per module, small tolerance)."""
    import critical_fixtures as F
    from kae.route.critical_modules import modules_from_brief, route_module
    res = {}
    for mode in ("fast", "multi", "exact"):
        with EX.scope(mode, k=4):
            EX.stats(reset=True)
            s = F.session(tmp_path / mode, kinds=("cell", "decap", "chain"), rails="none")
            mods = modules_from_brief(s.brief, ("cell", "decap", "chain"))
            for m in mods:
                route_module(s.ctx, m)
            st = EX.stats()
            res[mode] = ({m.id: (m.status, EX.module_values(s.ctx, m)) for m in mods}, st)
    fast, multi, exact = res["fast"][0], res["multi"][0], res["exact"][0]
    status = [{k: v[0] for k, v in r.items()} for r in (fast, multi, exact)]
    assert status[0] == status[1] == status[2]
    assert res["fast"][1]["decisions"] == 0 and res["fast"][1]["exact_calls"] == 0
    assert res["multi"][1]["decisions"] > 0
    assert res["exact"][1]["exact_calls"] > res["multi"][1]["exact_calls"] > 0
    for mid, (status, (vf, ve)) in fast.items():
        if ve is None or multi[mid][1][1] is None:
            continue
        assert multi[mid][1][1] <= ve * 1.02


# ----------------------------------------------------------------------------- thermal (FV)
def test_fv_operator_matches_tm_board_thermal_fv_and_the_fin(research):
    """tm_board_thermal_fv E0: a uniform 2-layer 1 oz board, 1 W into 2 x 2 mm with 49 vias:
    FV 11.59, 8.14, 4.87, 2.21 K at r = 5, 10, 20, 40 mm (analytic fin 12.06 ... 2.16 K)."""
    import scipy.sparse.linalg as spla
    import tm_board_thermal_fv as tm
    b = tm.two_layer(lx=200e-3, ly=200e-3, dx=1e-3)
    b.cov[:] = True
    c = 100e-3
    m = b.rect(c - 1e-3, c - 1e-3, c + 1e-3, c + 1e-3)
    b.add_power(m, 1.0)
    for x in np.arange(c - 3e-3, c + 4e-3, 1e-3):
        for y in np.arange(c - 3e-3, c + 4e-3, 1e-3):
            b.add_via(x + 0.5e-3, y + 0.5e-3)
    A = EX.fv_operator(b.t_cu, b.d, b.cov, b.via, b.dx, *b.h)
    T = spla.spsolve(A.tocsc(), b.p.ravel()).reshape(b.nl, b.nx, b.ny)
    j = int(c / b.dx)
    for r, ref in ((5e-3, 11.59), (10e-3, 8.14), (20e-3, 4.87), (40e-3, 2.21)):
        i = int((c + r) / b.dx)
        assert 0.5 * (T[0, i, j] + T[1, i, j]) == pytest.approx(ref, abs=0.006)


def test_thermal_fv_matches_ex_exact_and_caches_source_fields(research):
    import ex_exact as EE
    from kae.physics.place_terms import Terms
    from kae.physics.priors import Knobs
    from place_terms_fixtures import buck_board
    b, brief = buck_board(p_w=5.4)
    T = Terms(b, brief, knobs=Knobs(jit="off"))
    mine, ref = EX.ThermalFV(T, dx=1.0), EE.FVThermal(T, dx=1.0)
    r1, m1 = mine.rise()
    r0, m0 = ref.rise()
    assert np.allclose(r1, r0, rtol=1e-9) and m1 == pytest.approx(m0)
    n = mine.solves
    mine.rise()                                         # nothing moved: every field is cached
    assert mine.solves == n
    assert mine.cost() == pytest.approx(EE.thermal_cost(T, r0, m0), rel=1e-9)
