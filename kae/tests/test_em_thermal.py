# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""kae.em.thermal against closed forms."""
import numpy as np
import pytest
from scipy.special import k0

from kae.em import thermal as TH
from kae.em.mesh import Layer, Mesh


def test_point_source_on_a_cooled_copper_sheet_follows_k0():
    """A copper sheet cooled on both faces: T(r) = P / (2 pi k t) K0(r / lam), lam = sqrt(k t / (2 h))."""
    p, half = 1.0, 150.0
    m = Mesh.over(-half, -half, half, half, p, [Layer("C", 0, 0.035, 1)])
    m.rect(0, "X", -half, -half, half, half)
    th = TH.Thermal(m, [], h=10.0, k_fr4=0.0)
    Q = np.zeros(m.lab.shape)
    j, i = m.cell(0.0, 0.0)
    Q[0, j, i] = 1.0
    T = th.solve(Q)[0]
    kt = TH.K_CU * 35e-6
    lam = np.sqrt(kt / (2 * 10.0))
    for r in (5.0, 10.0, 30.0):
        jj, ii = m.cell(r, 0.0)
        ref = 1.0 / (2 * np.pi * kt) * k0(r * 1e-3 / lam)
        assert T[jj, ii] == pytest.approx(ref, rel=0.03), r


def test_uniform_heat_on_a_two_layer_board_leaves_through_both_faces():
    """Uniform heating of a large board: dT = q / (2 h) once conduction through it is negligible."""
    m = Mesh.over(0, 0, 100, 100, 2.0, [Layer("T", 1.6, 0.035, 1), Layer("B", 0, 0.035, 1)])
    m.rect(0, "A", 0, 0, 100, 100)
    m.rect(1, "B", 0, 0, 100, 100)
    th = TH.Thermal(m, [1.6], h=10.0)
    q = 100.0                                    # W/m^2 into the top layer
    Q = np.zeros(m.lab.shape)
    Q[0] = q * (2e-3) ** 2
    T = th.solve(Q)
    # the centre of a finite board: within a few per cent of the infinite one (edges cool only by the faces)
    c = T[:, 25, 25]
    assert c.mean() == pytest.approx(q / (2 * 10.0), rel=0.05)
    assert c[0] > c[1]                           # the heated face is warmer, by q/2 through the laminate


def test_a_cold_plate_under_the_board_takes_the_heat_and_sets_its_temperature():
    """A plate bolted under a heated board with conductance G per cell: far stronger than the air, the board
    settles at the plate's temperature plus q / G per cell (the heat that crosses the interface)."""
    m = Mesh.over(0, 0, 50, 50, 2.0, [Layer("T", 1.6, 0.035, 1), Layer("B", 0, 0.035, 1)])
    m.rect(0, "A", 0, 0, 50, 50)
    m.rect(1, "B", 0, 0, 50, 50)
    ny, nx = m.lab.shape[1:]
    g = 0.05                                     # W/K per 2 mm cell: 12500 W/m^2/K, a thermal pad on aluminium
    q = 1e-3                                     # W into every top cell
    Q = np.zeros(m.lab.shape)
    Q[0] = q
    free = TH.Thermal(m, [1.6], h=10.0).solve(Q)
    th = TH.Thermal(m, [1.6], h=10.0, sinks=[(1, np.full((ny, nx), g))])
    T = th.solve(Q, t_sinks=[15.0])              # the plate 15 K above ambient
    assert free[:, 12, 12].mean() == pytest.approx(q / 4e-6 / 20.0, rel=0.05)   # still air: q/(2h), 12.5 K
    assert T[1, 12, 12] == pytest.approx(15.0 + q / g, rel=0.1)
    assert T[0, 12, 12] > T[1, 12, 12]           # the heat crosses the laminate to reach the plate


def _pad_rise(p, gap, sw, mode):
    """Mean rise of a 2 mm pad carrying 1 W in a 20 mm pour: solid, the relief's true copper, or the relief lumped."""
    from shapely.geometry import box
    from shapely.ops import unary_union
    pad = box(-1, -1, 1, 1)
    ring = pad.buffer(gap, join_style=2).difference(pad)
    w = sw / 2
    spokes = unary_union([box(1, -w, 1 + gap, w), box(-1 - gap, -w, -1, w), box(-w, 1, w, 1 + gap), box(-w, -1 - gap, w, -1)])
    m = Mesh.over(-10, -10, 10, 10, p, [Layer("C", 0, 0.035, 1)])
    if mode == "true":
        m.paint(0, "X", box(-10, -10, 10, 10).difference(ring).union(spokes))
    else:
        m.rect(0, "X", -10, -10, 10, 10)
    cut, links = (), ()
    if mode == "lumped":
        cut = [(0, m.cells_in(ring))]
        ends = (((0.85, 0), (1 + gap + p, 0)), ((-0.85, 0), (-1 - gap - p, 0)), ((0, 0.85), (0, 1 + gap + p)), ((0, -0.85), (0, -1 - gap - p)))
        links = [lk for a, z in ends for lk in TH.spoke_links(m, 0, sw, a, z, gap)]
    padm = m.cells_in(pad)
    Q = np.zeros(m.lab.shape)
    Q[0][padm] = 1.0 / padm.sum()
    return TH.Thermal(m, [], h=10.0, k_fr4=1e-6, cut=cut, links=links).solve(Q)[0][padm].mean()


@pytest.mark.parametrize("gap,sw", [(0.25, 0.3), (0.5, 0.5)])
def test_a_lumped_thermal_relief_matches_the_resolved_copper(gap, sw):
    """Four spokes between a pad and its pour: what they add to the pad's rise over a solid connection, lumped at
    the evaluator's 0.25 mm pitch, against the relief's own copper resolved at 0.05 mm."""
    truth = _pad_rise(0.05, gap, sw, "true") - _pad_rise(0.05, gap, sw, "solid")
    lumped = _pad_rise(0.25, gap, sw, "lumped") - _pad_rise(0.25, gap, sw, "solid")
    assert truth > 20                                     # 1 W through four spokes: tens of kelvin
    assert lumped == pytest.approx(truth, rel=0.12)


def test_a_cooling_variant_solved_on_the_base_factor_matches_its_own_factorization():
    """Other surface cooling and sink conductance: the CG solve on the base factorization equals a fresh one."""
    m = Mesh.over(0, 0, 40, 30, 0.5, [Layer("T", 1.6, 0.035, 1), Layer("B", 0, 0.035, 1)])
    m.rect(0, "A", 0, 0, 25, 30)
    m.rect(1, "B", 10, 0, 40, 30)
    ny, nx = m.lab.shape[1:]
    mask = np.zeros((ny, nx))
    mask[:, nx // 2:] = 1.0
    Q = np.zeros(m.lab.shape)
    Q[0, ny // 2, nx // 4] = 0.5
    base = TH.Thermal(m, [1.6], h=12.0, sinks=[(1, 0.01 * mask)])
    for h, g, t in ((8.0, 0.002, 5.0), (20.0, 0.05, -3.0)):
        fresh = TH.Thermal(m, [1.6], h=h, sinks=[(1, g * mask)]).solve(Q, t_sinks=[t])
        var = base.variant(h=h, sinks=[(1, g * mask)]).solve(Q, t_sinks=[t])
        assert np.allclose(var, fresh, rtol=1e-6, atol=1e-6)


def test_via_barrel_conducts_through_its_annulus():
    """A via's barrel between two layers: k_cu pi (d + t) t / gap, t the IPC-6012 class 2 plating
    (kae.materials; it was pi d t at 25 um)."""
    from kae import materials as MAT
    m = Mesh.over(0, 0, 4, 4, 1.0, [Layer("T", 1.6, 0.035, 1), Layer("B", 0, 0.035, 1)])
    m.via(2.5, 2.5, [0, 1], "A", drill=0.3)
    th = TH.Thermal(m, [1.6], h=10.0, k_fr4=0.0, k_fr4_in=0.0)
    j, i = m.cell(2.5, 2.5)
    a, b = th.idx[0, j, i], th.idx[1, j, i]
    g = -th.A[a, b]
    assert g == pytest.approx(TH.K_CU * MAT.barrel_area_mm2(0.3, 0.020) * 1e-6 / 1.6e-3, rel=1e-9)
    assert MAT.VIA_PLATING_MM == 0.020 and TH.H_AIR == 10.0
