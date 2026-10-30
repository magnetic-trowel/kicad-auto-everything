# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""kae.em.cprice: capacitive price fields against fresh static solves, and the victim's edge model."""
import math

import numpy as np
import pytest

from kae.em import cprice as CP
from kae.em import static as ST
from kae.em.mesh import Layer, Mesh


def _setup(h=0.2, er=4.5, pitch=0.25):
    m = Mesh.over(0, 0, 20, 12, pitch, [Layer("F", h, 0.035, 1), Layer("B", 0, 0.035, 1)])
    m.rect(1, "GND", 0, 0, 20, 12)
    m.rect(0, "A", 3, 5.5, 17, 6.5)
    m.rect(0, "V", 18, 1, 19, 2)
    es = ST.Electrostatic(m, ST.Stack([0.0, h * 1e-3], [er]), [h * 1e-3, 0.0])
    cp = CP.CapPrices.bare([dict(obs="k", src="s", a="A", n="V", bound=1e-3, R=3e4, Cc=5e-12, V0=5.0)],
                           {"s": [{"V_V": 5.0, "t_v_s": 1e-9}]}, es, ["F", "B"], tol=1e-7)
    F = CP.Fields(m)
    cp._drive(es, F, ["A", "V"])
    cp._pairs(F)
    return cp, F


def test_victim_hop_beside_aggressor_predicted_as_solved():
    cp, F = _setup()
    key = ("k", "A", "V")
    # Maxwell's matrix is symmetric: the two columns agree
    a, n = F.nets.index("A"), F.nets.index("V")
    assert -F.col["A"][n] == pytest.approx(-F.col["V"][a], rel=0.02)
    for d in (0.25, 1.0):
        y = 6.5 + d + 0.125
        G, r = cp.after_hop(F, "V", [("F", (6.0, y), (14.0, y))], [], 0.25, 0.6, ["F", "B"])
        pred, solved = r[key]
        assert solved > 0
        assert 0.85 < pred / solved < 1.2
        assert G.Cm[key] == pytest.approx(F.Cm[key] + solved)
    # reciprocity: the victim's field prices the aggressor's copper the same way
    G, r = cp.after_hop(F, "A", [("F", (6.0, 4.0), (14.0, 4.0))], [], 0.25, 0.6, ["F", "B"])
    pred, solved = r[key]
    assert 0.8 < pred / solved < 1.25


def test_prices_follow_the_aggressor_field_and_are_non_negative():
    cp, F = _setup()
    cp.set_weights(F, [0], lambda u: 1.0)
    c = cp.cost(F, "V", 0.25, 0, (slice(None), slice(None)))
    assert (c >= 0).all()
    j_near, j_far, i = int(7.0 / 0.25), int(10.0 / 0.25), int(10.0 / 0.25)
    assert c[j_near, i] > 10 * c[j_far, i]
    assert cp.cost(F, "GND", 0.25, 0, (slice(None), slice(None))) is None


def test_edge_gain_limits():
    R, C, V = 3e4, 5e-12, 5.0
    # fast edge: the capacitive divider V / C per farad of C_m
    assert CP.edge_gain(V, 1e-10, R, C) == pytest.approx(V / C, rel=1e-3)
    # slow edge: R dV/dt
    assert CP.edge_gain(V, 1e-4, R, C) == pytest.approx(R * V / 1e-4, rel=1e-3)
    assert CP.edge_gain(V, 1e-9, R, math.inf) == 0.0
    assert CP.edge_gain(V, 1e-9, 0.0, C) == 0.0


def test_strip_capacitance_closed_form_against_raster():
    k = CP.raster_kappa(0.5, 1.51, 4.5, 0.25, True)
    assert 0.85 < k < 1.05                          # the raster's 2-cell strip within its pitch error
    assert np.all(np.diff(CP.strip_C_per_mm(np.array([0.25, 0.5, 1.0]), 1.51, 4.5, True)) > 0)
