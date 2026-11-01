# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""kae.em.static: layered electrostatics against closed forms."""
import math

import numpy as np
import pytest

from kae.em import static as ST
from kae.em.mesh import Layer, Mesh

EPS0 = ST.EPS0


def test_panel_integral_closed_forms_agree_and_match_quadrature():
    p = 0.25e-3
    for x, y, dz in [(0.0, 0.0, 0.1e-3), (0.3e-3, 0.1e-3, 0.05e-3), (1e-3, -0.4e-3, 0.2e-3)]:
        g, w = np.polynomial.legendre.leggauss(40)
        u, wu = g * p / 2, w * p / 2
        ref = sum(wi * wj / math.sqrt((x - ui) ** 2 + (y - vj) ** 2 + dz * dz)
                  for ui, wi in zip(u, wu) for vj, wj in zip(u, wu))
        assert ST._panel_inv_r3d(p, x, y, dz) == pytest.approx(ref, rel=1e-6)
    # in its own plane the 3-D form tends to Durand's
    assert ST._panel_inv_r3d(p, 0.4e-3, 0.1e-3, 1e-12) == pytest.approx(ST._panel_inv_r(p, p, 0.4e-3, 0.1e-3), rel=1e-6)


def test_spectral_solution_is_free_space_in_a_uniform_medium_and_half_space_on_an_interface():
    k = np.array([10.0, 1e3, 1e4])
    uni = ST.Stack([0.0, 1e-3], [1.0])                    # "slab" of air: no interfaces in effect
    assert uni.spectral(k, 0.5e-3, 0.0) == pytest.approx(np.exp(-k * 0.5e-3) / (2 * EPS0 * k), rel=1e-9)
    thick = ST.Stack([0.0, 1.0], [4.0])                   # a charge on the face of a 1 m slab of eps 4
    # near the charge, the half space: 1 / (2 eps0 (1 + 4) / 2 k)
    assert thick.spectral(np.array([1e4]), 0.0, 0.0)[0] == pytest.approx(1 / (2 * EPS0 * 2.5 * 1e4), rel=1e-6)


def test_smooth_remainder_vanishes_without_layering():
    st = ST.Stack([0.0, 1e-3], [1.0])
    r = np.array([0.0, 1e-4, 1e-3, 1e-2])
    assert np.max(np.abs(ST.smooth_green(st, 0.0, 0.0, r))) * 4 * math.pi * EPS0 * 1e-3 < 1e-4


def _plates(w, h, eps, pitch):
    m = Mesh.over(0, 0, w, w, pitch, [Layer("T", h, 0.035, 1), Layer("B", 0, 0.035, 1)])
    m.rect(0, "A", 0, 0, w, w)
    m.rect(1, "B", 0, 0, w, w)
    return m, ST.Electrostatic(m, ST.Stack([0.0, h * 1e-3], [eps]), [h * 1e-3, 0.0])


def test_parallel_plates_give_eps_a_over_h_plus_fringe():
    w, h, eps = 10.0, 0.2, 4.5
    m, es = _plates(w, h, eps, 0.25)
    C, its = es.capacitance(["A"])
    ideal = EPS0 * eps * (w * 1e-3) ** 2 / (h * 1e-3)
    cm = -C["A"]["B"]
    # fringe of a w/h = 50 capacitor in a dielectric slab with air outside: a few per cent
    assert ideal < cm < 1.06 * ideal
    assert C["A"]["A"] > cm                                # plus its capacitance to the world


def _microstrip_cp(w, h, eps, pitch):
    """C' (F/m) of a zero-thickness microstrip, its edges on cell boundaries, from two lengths."""
    gw = 6.05
    out = []
    for length in (10.0, 20.0):
        m = Mesh.over(0, -gw, length + 2, gw, pitch, [Layer("T", h, 0.035, 1), Layer("G", 0, 0.035, 1)])
        m.rect(1, "GND", 0, -gw, length + 2, gw)
        m.rect(0, "S", 1, -w / 2, 1 + length, w / 2)
        es = ST.Electrostatic(m, ST.Stack([0.0, h * 1e-3], [eps]), [h * 1e-3, 0.0])
        C, _ = es.capacitance(["S"])
        out.append(-C["S"]["GND"])
    return (out[1] - out[0]) / 10e-3                      # the ends cancel


def test_microstrip_per_length_converges_to_hammerstad_jensen():
    w, h, eps = 0.5, 0.2, 4.5
    c1, c2 = _microstrip_cp(w, h, eps, 0.1), _microstrip_cp(w, h, eps, 0.05)
    u = w / h
    a = 1 + math.log((u ** 4 + (u / 52) ** 2) / (u ** 4 + 0.432)) / 49 + math.log(1 + (u / 18.1) ** 3) / 18.7
    bb = 0.564 * ((eps - 0.9) / (eps + 3)) ** 0.053
    eeff = (eps + 1) / 2 + (eps - 1) / 2 * (1 + 10 / u) ** (-a * bb)
    fu = 6 + (2 * math.pi - 6) * math.exp(-(30.666 / u) ** 0.7528)
    c_ref = eeff / (299792458.0 * 60 * math.log(fu / u + math.sqrt(1 + 4 / u ** 2)))
    # first order in the pitch from below (the edge singularity), Richardson to zero pitch
    assert c1 < c2 < c_ref
    assert 2 * c2 - c1 == pytest.approx(c_ref, rel=0.01)
