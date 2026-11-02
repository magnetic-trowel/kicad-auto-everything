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
