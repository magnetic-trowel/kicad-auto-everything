# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Copper's temperature coefficient in the heat band (kae.excite.heat.tcr_solve, kae.excite.evaluate.apply_tcr)."""
import numpy as np
import pytest

from kae.em import thermal as TH
from kae.em.mesh import ALPHA_CU, Layer, Mesh
from kae.excite import heat as HT
from kae.excite.evaluate import apply_tcr


def _board():
    m = Mesh.over(0, 0, 20, 20, 1.0, [Layer("T", 1.6, 0.035, 1), Layer("B", 0, 0.035, 1)])
    m.rect(0, "PWR", 0, 0, 20, 20)
    m.rect(1, "GND", 0, 0, 20, 20)
    return m, TH.Thermal(m, [1.6], h=10.0)


def _one_cell(m, w):
    Q = np.zeros(m.lab.shape)
    j, i = m.cell(10.0, 10.0)
    Q[0, j, i] = w
    return Q, (0, j, i)


def test_single_heated_cell_follows_the_closed_form():
    """Copper heat in one cell only: T = T0 / (1 - alpha T0 / a0), T0 its rise at the ambient's resistance
    (thermal-physics.md: dT = dT0 / (1 - alpha dT0) at a0 = 1)."""
    m, th = _board()
    Qc0, at = _one_cell(m, 0.5)
    for a0 in (1.0, 1.0 + ALPHA_CU * 30):
        T0 = th.solve(a0 * Qc0)[at]
        T, Qc, info = HT.tcr_solve(th, np.zeros_like(Qc0), Qc0, a0)
        assert info["converged"] and not info["runaway"]
        assert T[at] == pytest.approx(T0 / (1 - ALPHA_CU * T0 / a0), rel=1e-3)
        assert Qc.sum() == pytest.approx(Qc0.sum() * (a0 + ALPHA_CU * T[at]), rel=1e-6)


def test_part_heat_raises_the_copper_loss_but_is_not_scaled():
    m, th = _board()
    Qc0, at = _one_cell(m, 0.2)
    Qp = np.zeros_like(Qc0)
    Qp[1, 5, 5] = 2.0
    T, Qc, info = HT.tcr_solve(th, Qp, Qc0, 1.0)
    T_cold = th.solve(Qp + Qc0)
    assert info["converged"]
    assert T[at] > T_cold[at]
    # the part's 2 W heat the copper cell too: its factor is more than its own heat alone would give
    _, Qc_alone, _ = HT.tcr_solve(th, np.zeros_like(Qc0), Qc0, 1.0)
    assert Qc.sum() > Qc_alone.sum()


def test_no_fixed_point_is_thermal_runaway():
    """Loop gain alpha * theta * Qc0 >= 1: the copper heats without bound."""
    m, th = _board()
    unit, at = _one_cell(m, 1.0)
    theta = th.solve(unit)[at]                      # K/W of the cell onto itself
    Qc0 = unit * (1.3 / (ALPHA_CU * theta))
    T, _, info = HT.tcr_solve(th, np.zeros_like(Qc0), Qc0, 1.0)
    assert not info["converged"] and info["runaway"]
    assert info["gain"] > 0.98
    # just below the limit it converges, slowly
    Qc0 = unit * (0.5 / (ALPHA_CU * theta))
    _, _, info = HT.tcr_solve(th, np.zeros_like(Qc0), Qc0, 1.0)
    assert info["converged"] and info["gain"] == pytest.approx(0.5, abs=0.05)


def test_apply_tcr_scales_dc_rows_totals_and_adds_a_runaway_hazard():
    ob = dict(values=[0.1, 0.2], u=[0.5, 1.2], label="DC drop")
    rows = [dict(observer="dc:copper_loss", u=0.3, u_lo=0.3, u_hi=0.6, P_mW=10.0,
                 _tcr=dict(us=[0.3, 0.6], vals=[0.01, 0.02], nets=None, key="P_mW", scale=1e3)),
            dict(observer="dc:drop:U1@+3V3", u=0.5, u_lo=0.5, u_hi=1.2, dV_mV=100.0,
                 _tcr=dict(us=[0.5, 1.2], vals=[0.1, 0.2], nets=["+3V3", "GND"], key="dV_mV", scale=1e3, obs=ob)),
            dict(observer="heat:U1", u=0.4, u_lo=0.4, u_hi=0.4)]
    tcr = dict(factor=[1.1, 1.3], a0=[1.0, 1.1], net_factor=[{"+3V3": 1.05, "GND": 1.2}, {}],
               runaway=[dict(corner=1, runaway=True, gain=1.4, T_max_C=400.0, T_amb_C=50.0, copper_W_at_20C=3.0,
                             nets=["+3V3"])])
    tot = [10.0, 10.0]
    hz = []
    apply_tcr(rows, tcr, tot, [], hz)
    assert all("_tcr" not in r for r in rows)
    assert rows[0]["u"] == pytest.approx(0.33) and rows[0]["u_hi"] == pytest.approx(0.78)
    assert rows[0]["P_mW"] == pytest.approx(11.0)
    # a drop takes the largest factor of its rail and grounds; a corner without their heat, the ambient's
    assert rows[1]["u"] == pytest.approx(0.6) and rows[1]["u_hi"] == pytest.approx(1.32)
    assert ob["values"] == pytest.approx([0.12, 0.22]) and ob["u"] == pytest.approx([0.6, 1.32])
    from kae.excite.harm import phi
    assert tot[1] == pytest.approx(10.0 + phi(0.78) - phi(0.6) + phi(1.32) - phi(1.2))
    assert len(hz) == 1 and hz[0]["code"] == "thermal_runaway_copper" and hz[0]["severity"] == "block"
    assert hz[0]["objects"] == ["+3V3"]


def test_field_harm_within_the_mesh_error_band_gets_a_hazard():
    from kae.excite.evaluate import bias_hazards
    harms = [dict(observer="ovs:Q1", source="cell:U1", kind="overshoot", u_hi=1.1),
             dict(observer="ovs:Q2", source="cell:U2", kind="overshoot", u_hi=1.4),
             dict(observer="sup:U3", source="cell:U1", kind="supply", u_hi=0.97),
             dict(observer="sup:U4", source="cell:U1", kind="supply", u_hi=0.9),
             dict(observer="dc:drop:U1@3V3", source="dc", kind="dc_drop", u_hi=1.05)]
    hz = bias_hazards(harms, 0.25)
    assert [(h["objects"][0], h["severity"]) for h in hz] == [("ovs:Q1", "info"), ("sup:U3", "warn")]
    assert hz[1]["category"] == "electrical" and hz[0]["evidence"]["error_band"] == [-0.05, 0.16]
    assert bias_hazards(harms, 0.125) == []          # half the pitch, half the band: 0.97 and 1.1 lie outside it
