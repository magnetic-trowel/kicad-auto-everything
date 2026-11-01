# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""kae.em: the raster PEEC field solver against independent closed forms."""
import numpy as np
import pytest
from numpy.polynomial.legendre import leggauss

from kae.em import kernels as K
from kae.em import solve as S
from kae.em.mesh import Layer, Mesh

INF = float("inf")


def _quad(b1, b2, n=10):
    g, w = leggauss(n)

    def pts(a0, a1):
        return (a0 + a1) / 2 + (a1 - a0) / 2 * g, (a1 - a0) / 2 * w
    P1 = [pts(b1[2 * i], b1[2 * i + 1]) for i in range(3)]
    P2 = [pts(b2[2 * i], b2[2 * i + 1]) for i in range(3)]
    G1 = [a.ravel() for a in np.meshgrid(*[p[0] for p in P1], indexing="ij")]
    G2 = [a.ravel() for a in np.meshgrid(*[p[0] for p in P2], indexing="ij")]
    W1 = np.einsum("i,j,k", *[p[1] for p in P1]).ravel()
    W2 = np.einsum("i,j,k", *[p[1] for p in P2]).ravel()
    r = np.sqrt(sum((a[:, None] - b[None]) ** 2 for a, b in zip(G1, G2)))
    A1 = (b1[3] - b1[2]) * (b1[5] - b1[4])
    A2 = (b2[3] - b2[2]) * (b2[5] - b2[4])
    return K.K * np.sum(W1[:, None] * W2[None] / r) / A1 / A2


def test_bar_mutual_matches_quadrature():
    p, t = 0.25e-3, 35e-6
    b1 = (-p / 2, p / 2, -p / 2, p / 2, 0, t)
    for dx, dy, dz in [(1.5 * p, 0.3 * p, 0.2e-3), (0, 2 * p, 0), (3 * p, p, 0.1e-3)]:
        b2 = (b1[0] + dx, b1[1] + dx, b1[2] + dy, b1[3] + dy, dz, dz + t)
        assert K.bar_mutual(b1, b2) == pytest.approx(_quad(b1, b2, 12), rel=1e-9)


def test_bar_self_matches_ruehli():
    l, w, t = 10e-3, 1e-3, 35e-6
    L = K.bar_mutual((0, l, 0, w, 0, t), (0, l, 0, w, 0, t))
    ref = K.MU0 * l / (2 * np.pi) * (np.log(2 * l / (w + t)) + 0.5 + 0.2235 * (w + t) / l)
    assert L == pytest.approx(ref, rel=0.005)


def test_near_far_kernels_meet():
    p, t = 0.25e-3, 35e-6
    b1 = (-p / 2, p / 2, -p / 2, p / 2, 0, t)
    for j, i in [(0, K.NEAR + 1), (K.NEAR + 1, 0), (5, 5)]:
        b2 = (i * p - p / 2, i * p + p / 2, j * p - p / 2, j * p + p / 2, 0.1e-3, 0.1e-3 + t)
        fil = K.fil_mutual(-p / 2, p / 2, i * p - p / 2, i * p + p / 2, np.hypot(j * p, 0.1e-3))
        assert fil == pytest.approx(K.bar_mutual(b1, b2), rel=0.005)


def _strip(pitch):
    m = Mesh.over(0, 0, 10, 1, pitch, [Layer("F", 0, 0.035, 1)])
    m.rect(0, "A", 0, 0, 10, 1)
    X, _ = m.centres()
    m.terminal("a", 0, mask=X < pitch)
    m.terminal("b", 0, mask=X > 10 - pitch)
    m.port("p", "a", "b")
    return m


def test_strip_dc_resistance_exact_and_hf_below_uniform():
    r = S.solve(_strip(0.25), [0.0, INF])
    l = (10 - 0.25) * 1e-3
    assert r["R"][0, 0, 0] == pytest.approx(l / (5.8e7 * 1e-3 * 35e-6), rel=1e-6)
    uniform = K.bar_mutual((0, l, 0, 1e-3, 0, 35e-6), (0, l, 0, 1e-3, 0, 35e-6))
    # at high frequency the current crowds to the edges: below the uniform-current value
    assert 0.95 * uniform < r["L"][1, 0, 0] < uniform


def _microstrip(l, pitch, nsub=2, w=0.5, h=0.2, t=0.035):
    m = Mesh.over(0, -5, l + 2, 5, pitch, [Layer("T", h + t, t, nsub), Layer("G", 0, t, nsub)])
    m.rect(1, "GND", 0, -5, l + 2, 5)
    m.rect(0, "S", 1, -w / 2, 1 + l, w / 2)
    X, Y = m.centres()
    near = (X < 1 + pitch) & (X > 1) & (abs(Y) < w / 2)
    far = (X > 1 + l - pitch) & (X < 1 + l) & (abs(Y) < w / 2)
    m.terminal("s", 0, mask=near)
    m.terminal("g", 1, mask=near)
    m.terminal("se", 0, mask=far)
    m.terminal("ge", 1, mask=far)
    m.part("se", "ge")
    m.port("p", "s", "g")
    return S.solve(m, [INF])["L"][0, 0, 0]


def hj_L(w, h, t):
    """Hammerstad-Jensen air microstrip (with thickness correction): L' = Z0 / c, H/m."""
    u, tn = w / h, t / h
    u = u + tn / np.pi * np.log(1 + 4 * np.e / (tn / np.tanh(np.sqrt(6.517 * u)) ** 2))
    f = 6 + (2 * np.pi - 6) * np.exp(-(30.666 / u) ** 0.7528)
    return 376.73 / (2 * np.pi) * np.log(f / u + np.sqrt(1 + 4 / u ** 2)) / 2.998e8


def test_microstrip_per_length_approaches_closed_form_from_above():
    Lp = (_microstrip(8, 0.125) - _microstrip(4, 0.125)) / 4e-3
    ref = hj_L(0.5, 0.2, 0.035)
    # a raster restricts the current space, so its inductance is an upper bound (variational)
    assert ref < Lp < 1.12 * ref


def test_open_loop_is_an_error():
    m = Mesh.over(0, 0, 4, 2, 0.25, [Layer("F", 0, 0.035, 1)])
    m.rect(0, "A", 0, 0, 1.5, 2)
    m.rect(0, "B", 2.5, 0, 4, 2)
    X, _ = m.centres()
    m.terminal("a", 0, mask=X < 0.25)
    m.terminal("b", 0, mask=X > 3.75)
    m.port("p", "a", "b")
    with pytest.raises(ValueError, match="open loop"):
        S.solve(m, [INF])
