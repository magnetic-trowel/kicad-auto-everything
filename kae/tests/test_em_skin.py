# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""kae.em.skin: the slab's surface impedance, its n-filament limit, and the reduced model's correction."""
import math

import numpy as np
import pytest

from kae.em import skin as SK

T = 35e-6


def test_skin_depth_and_slab_limits():
    assert SK.delta(1e6) == pytest.approx(66.1e-6, rel=2e-3)
    assert SK.delta(100e6) == pytest.approx(6.61e-6, rel=2e-3)
    assert SK.slab(1e3, T) == pytest.approx(1.0, abs=1e-6)
    # thick limit: all the current in one skin depth, R / R_dc -> t / delta
    assert SK.slab(1e10, T) == pytest.approx(T / SK.delta(1e10), rel=1e-3)
    # Dowell's single-layer form (sinh 2D + sin 2D) / (cosh 2D - cos 2D) D
    D = T / SK.delta(30e6)
    ref = D * (math.sinh(2 * D) + math.sin(2 * D)) / (math.cosh(2 * D) - math.cos(2 * D))
    assert SK.slab(30e6, T) == pytest.approx(ref, rel=1e-9)


def test_filament_slab_converges_to_the_exact_slab():
    for f in (10e6, 100e6, 200e6):
        assert SK.slab_filaments(f, T, 1) == pytest.approx(1.0)
        assert SK.slab_filaments(f, T, 32) == pytest.approx(SK.slab(f, T), rel=0.01)
    # two equal halves fall short above ~10 MHz: 0.60 of the exact ratio at 100 MHz, 0.43 at 200 MHz
    assert SK.slab_filaments(100e6, T, 2) / SK.slab(100e6, T) == pytest.approx(0.595, abs=0.01)
    assert SK.slab_filaments(200e6, T, 2) / SK.slab(200e6, T) == pytest.approx(0.43, abs=0.01)
    assert SK.correction(1e6, T, 2) == pytest.approx(1.0, abs=0.01)
    assert SK.correction(0.0, T, 2) == 1.0


def test_reduced_model_scales_copper_resistance_per_layer():
    """A trace over a plane: with the correction on, the reduced model's port R at f is the full system's R
    with every copper bar's resistance times k(f) (vias none here), to the model's accuracy."""
    from kae.em import reduce as RD
    from kae.em import solve as S
    from kae.em.mesh import Layer, Mesh
    m = Mesh.over(0, -2, 9, 2, 0.25, [Layer("T", 0.135, 0.035, 2), Layer("G", 0, 0.035, 2)])
    m.rect(1, "GND", 0, -2, 9, 2)
    m.rect(0, "S", 1, -0.25, 8, 0.25)
    X, Y = m.centres()
    near = (X > 1) & (X < 1.25) & (abs(Y) < 0.25)
    far = (X > 7.75) & (X < 8) & (abs(Y) < 0.25)
    m.terminal("s", 0, mask=near, net="S")
    m.terminal("g", 1, mask=near)
    m.terminal("se", 0, mask=far, net="S")
    m.terminal("ge", 1, mask=far)
    m.part("se", "ge")
    net = S.Network(m)
    op = S.Operator(net)
    model = RD.Reduced(op, [{"s": 1.0, "g": -1.0}], log=lambda *a: None)
    model.build(200e6, tol=1e-4)
    f = 100e6
    z0 = model.Z(f)[0, 0]
    pw0 = model.powers(f)["copper"][0]
    model.skin_correction()
    z1 = model.Z(f)[0, 0]
    k = SK.correction(f, 35e-6, 2)
    assert k > 1.5
    # the copper is all of the port's resistance: R scales by about k (the current pattern shifts a little)
    assert z1.real == pytest.approx(k * z0.real, rel=0.05)
    assert model.powers(f)["copper"][0] == pytest.approx(k * pw0, rel=0.05)
    assert abs(z1.imag - z0.imag) < 0.02 * abs(z0.imag)
    model.skin_correction(False)
    assert model.Z(f)[0, 0] == pytest.approx(z0)
