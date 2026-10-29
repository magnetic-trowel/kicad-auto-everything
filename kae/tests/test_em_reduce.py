# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""kae.em.reduce and kae.excite.spectrum: the reduced model against direct solves, energy conservation,
and the whole-spectrum totals."""
import numpy as np
import pytest

from kae.em import reduce as RD
from kae.em import solve as ES
from kae.em.mesh import Layer, Mesh
from kae.excite import spectrum as SP


def _line(pitch=0.5):
    """A 20 mm microstrip over a plane, driven at its near end (with a 1 kOhm shunt), an RC load at its
    far end (0.2 Ohm + 2 nF: a series resonance with the line's inductance, Q about 10)."""
    m = Mesh.over(0, -3, 22, 3, pitch, [Layer("T", 0.235, 0.035, 2), Layer("G", 0, 0.035, 2)])
    m.rect(1, "GND", 0, -3, 22, 3)
    m.rect(0, "S", 1, -0.5, 21, 0.5)
    X, Y = m.centres()
    near, far = (X > 1) & (X < 1 + pitch) & (abs(Y) < 0.5), (X < 21) & (X > 21 - pitch) & (abs(Y) < 0.5)
    for nm, lay, mask in (("s0", 0, near), ("g0", 1, near), ("s1", 0, far), ("g1", 1, far)):
        m.terminal(nm, lay, mask=mask)
    m.part("s1", "g1", name="load", zf=lambda w: 0.2 + 1 / (1j * w * 2e-9))
    m.part("s0", "g0", name="shunt", zf=lambda w: 1e3 + 0j)
    return m


@pytest.fixture(scope="module")
def model():
    m = _line()
    op = ES.Operator(ES.Network(m))
    ports = [{"s0": 1.0, "g0": -1.0}, {"s1": 1.0, "g1": -1.0}]
    return RD.Reduced(op, ports, log=lambda *a: None).build(3e8, fmin=1e3, tol=1e-4, f0=(0.0, 10e6), max_snapshots=10)


def test_model_resolves_the_resonance_between_its_snapshots(model):
    fs = np.logspace(6, np.log10(3e8), 600)
    z = np.array([abs(model.Z(f)[0, 0]) for f in fs])
    k = int(np.argmin(z))                                  # the driving point dips at the series resonance
    f0 = fs[k]
    assert 10e6 < f0 < 200e6 and z[k] < 0.2 * np.median(z)
    assert min(abs(np.log(f0 / g)) for g in model.freqs if g > 0) > 0.05      # not on a snapshot
    for f in (3e4, 2e6, f0, 1.5e8):
        sy = ES.System(model.op, f)
        X, _ = sy.solve_many(model.P, tol=1e-10, maxiter=3000)
        Zd = model.P.T @ (X[model.nb:] / sy.kap)
        Zr = model.Z(f)
        assert np.max(np.abs(Zr - Zd)) <= 1e-3 * np.max(np.abs(Zd)), f


def test_delivered_power_is_copper_plus_parts(model):
    for f in (0.0, 1e5, 4.1e7, 2e8):
        pw = model.powers(f)
        lost = pw["copper"] + pw["parts"].sum(0)
        assert np.allclose(pw["delivered"], lost, rtol=1e-3), f


def test_trapezoid_series_rebuilds_the_waveform():
    I, D, tr, fsw = 2.0, 0.3, 20e-9, 1e6
    n = np.arange(1, 20001)
    c0, c = I * D, SP.trapezoid(I, D, tr, fsw, n)
    t = np.linspace(0, 1 / fsw, 400, endpoint=False)
    x = c0 + 2 * np.real(np.exp(2j * np.pi * fsw * np.outer(t, n)) @ c)
    # the trapezoid: rising from t = -tr/2 to tr/2, falling from D T - tr/2 to D T + tr/2
    T = 1 / fsw
    ref = np.clip(np.minimum((t + tr / 2) / tr, (D * T + tr / 2 - t) / tr), 0, 1) * I
    ref = np.maximum(ref, np.clip((t - (T - tr / 2)) / tr, 0, 1) * I)          # the next period's rise
    assert np.max(np.abs(x - ref)) < 2e-3 * I


def test_totals_conserve_energy_and_parseval(model):
    r = SP.totals(model, 0, [1], I=1.0, D=0.4, t_r=5e-9, f_sw=2e6, f_max=3e8)
    assert r["balance"] < 1e-3
    assert r["delivered"] == pytest.approx(r["copper"] + sum(r["parts"].values()), rel=1e-3)
    # the waveform's mean square is the observer's RMS squared (Parseval of the synthesis)
    assert np.mean(r["wave"][0] ** 2) == pytest.approx(r["rms"][0] ** 2, rel=1e-9)
    assert 0 < r["left_out"] < 0.05


def test_a_rings_magnetic_moment_is_its_current_times_its_area():
    p = 0.25
    m = Mesh.over(-6, -6, 6, 6, p, [Layer("C", 0, 0.035, 1)])
    for x0, y0, x1, y1 in ((-5, -5, 5, -4), (-5, 4, 5, 5), (-5, -5, -4, 5), (4, -5, 5, 5)):
        m.rect(0, "R", x0, y0, x1, y1)
    m.lab[0, m.cell(4.5, -0.1)[0]:m.cell(4.5, 0.1)[0] + 1, :] = np.where(
        np.arange(m.nx)[None, :] >= m.cell(4.0, 0)[1], -1, m.lab[0, m.cell(4.5, -0.1)[0]:m.cell(4.5, 0.1)[0] + 1, :])
    X, Y = m.centres()
    lo, hi = m.cell(4.5, -0.1)[0], m.cell(4.5, 0.1)[0]
    m.terminal("a", 0, mask=(X > 4) & (np.arange(m.ny)[:, None] == lo - 1))
    m.terminal("b", 0, mask=(X > 4) & (np.arange(m.ny)[:, None] == hi + 1))
    op = ES.Operator(ES.Network(m))
    md = RD.Reduced(op, [{"b": 1.0, "a": -1.0}], log=lambda *a: None)
    md.snapshot(0.0)
    mz = md.moment(md.solve(0.0))[:, 0]
    assert abs(mz[2]) == pytest.approx(81e-6, rel=0.05)
    assert abs(mz[0]) + abs(mz[1]) < 1e-3 * abs(mz[2])
