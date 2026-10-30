# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""kae.em.spectral: the waveform-peak weights against finite differences, and a hop's price from the
reduced model's basis fields against the exact change of a transfer impedance."""
import numpy as np
import pytest

from kae.em import reduce as RD
from kae.em import solve as ES
from kae.em.mesh import Layer, Mesh
from kae.em.spectral import Spectral, peak
from kae.excite import spectrum as SP


def test_peak_weights_are_its_derivative():
    rng = np.random.default_rng(1)
    n = np.arange(1, 41)
    a = 2 * SP.trapezoid(1.3, 0.3, 4e-9, 1.2e6, n)
    H = (rng.normal(size=40) + 1j * rng.normal(size=40)) * np.exp(-n / 15) * 1e-2 * n
    p0, sg, th = peak(a * H)
    for _ in range(5):
        dH = (rng.normal(size=40) + 1j * rng.normal(size=40)) * 1e-9
        lin = sg * float(np.real(np.sum(np.exp(1j * th) * a * dH)))
        p1 = peak(a * (H + dH))[0]
        assert p1 - p0 == pytest.approx(lin, rel=1e-4, abs=1e-15)


def _board(pitch, hop):
    """A 12 mm trace over a plane driven through a 200 pF switch-node capacitance and closed by a capacitor
    with ESL (it rings near 330 MHz); a victim 1 mm away whose pads an unrouted (field-free) connection
    joins, or (hop) its trace."""
    m = Mesh.over(0, 0, 16, 8, pitch, [Layer("F", 0.235, 0.035, 2), Layer("B", 0, 0.035, 2)])
    m.rect(1, "GND", 0, 0, 16, 8)
    m.rect(0, "A", 2, 3, 14, 3.5)
    m.rect(0, "V", 2, 4.5, 2.5, 5)
    m.rect(0, "V", 13.5, 4.5, 14, 5)
    if hop:
        m.rect(0, "V", 2, 4.5, 14, 5)
    X, Y = m.centres()
    for nm, lay, x0, y0 in (("as", 0, 2, 3), ("ag", 1, 2, 3), ("ae", 0, 13.5, 3), ("aeg", 1, 13.5, 3),
                            ("vs", 0, 2, 4.5), ("vg", 1, 2, 4.5), ("ve", 0, 13.5, 4.5), ("veg", 1, 13.5, 4.5)):
        m.terminal(nm, lay, mask=(X > x0) & (X < x0 + 0.5) & (Y > y0) & (Y < y0 + 0.5))
    m.part("as", "ag", zf=lambda w: 1 / (1j * w * 200e-12))
    m.part("ae", "aeg", zf=lambda w: 0.02 + 1j * w * 0.5e-9 + 1 / (1j * w * 1e-6))
    m.part("ve", "veg")
    if not hop:
        m.part("vs", "ve")
    return m


def test_basis_price_predicts_the_hops_coupling_over_the_spectrum():
    pitch = 0.25
    ports = [{"as": 1.0, "ag": -1.0}, {"vs": 1.0, "vg": -1.0}]
    m = _board(pitch, False)
    net = ES.Network(m)
    op = ES.Operator(net)
    model = RD.Reduced(op, ports, log=lambda *a: None).build(3e8, fmin=1e4, tol=1e-4, f0=(0.0, 1e7), snap_tol=1e-9)
    bf = Spectral._basis(None, model, net, op, m, None)
    X, Y = m.centres()
    rows = np.nonzero(abs(Y[:, 0] - 4.75) < 0.25)[0]
    i0, i1 = m.cell(2.25, 4.75)[1], m.cell(13.75, 4.75)[1]
    ii = np.arange(i0, i1 + 1)
    fl = sum((0.5 * (bf["Px"][0][:, j, ii[:-1]] + bf["Px"][0][:, j, ii[1:]])).sum(1) for j in rows) / len(rows)
    post = ES.Network(_board(pitch, True))
    op2 = ES.Operator(post)
    P2 = RD.Reduced(op2, ports, log=lambda *a: None).P
    for f in (1e7, 6e7, 1.5e8, 2.5e8):           # above the R-L transition (below it the return spreads)
        Z = []
        for o, P in ((op, model.P), (op2, P2)):
            sy = ES.System(o, f)
            Xs, _ = sy.solve_many(P, tol=1e-9, maxiter=3000)
            Z.append((P.T @ (Xs[-P.shape[0]:] / sy.kap))[1, 0])
        # the price counts the hop's whole coupling: the short's own return through the plane, the same for
        # every path the hop could take, is already in Z_vs before it (Z[0])
        pred = 1j * 2 * np.pi * f * (fl @ model.solve(f)[:, 0])
        assert abs(pred / Z[1] - 1) < 0.1, (f, pred / Z[1])
