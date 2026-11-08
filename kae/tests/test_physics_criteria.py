# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Shared criteria: switch-node overshoot and cable common mode (docs/research/physics/component-priors.md)."""
import math

import pytest

from kae.excite import harm as HA
from kae.excite import observe as O
from kae.physics import criteria as CR
from kae.physics import priors as PR


# ----------------------------------------------------------------------------- cable common mode
def test_cable_limit_follows_ott_below_the_knee_and_the_resonant_cap_above():
    for f in (30e6, 60e6, 90e6):
        assert O.cm_v_lim(f) == pytest.approx(3.77e4 / f, rel=0.01)       # the old 3.8e4 / f line
    knee = CR.E_CAP_K / CR.OTT_K
    assert knee == pytest.approx(95.5e6, rel=0.01)
    assert O.cm_v_lim(150e6) == pytest.approx(O.cm_v_lim(230e6))          # flat past the knee
    assert 3.8e4 / 230e6 / O.cm_v_lim(230e6) == pytest.approx(1 / 2.4, rel=0.03)   # 7.6 dB looser at 230 MHz


def test_cm_worst_harmonic_moves_from_230_mhz_to_the_knee_for_fast_edges():
    # 1 MHz switching, 1 ns edges (corner 318 MHz, above the band): the harmonic voltage is flat in f, so its
    # ratio to the limit rises to the knee and is flat beyond (a tie, reported at its lowest frequency)
    u, f = HA.cm(1e-9, 1.0, 1e6, 1e-9)
    assert f == pytest.approx(96e6, abs=1.01e6)
    v = 2 * math.pi * f * 1e-9 * 2 / (round(f / 1e6) * math.pi)
    assert u == pytest.approx(v / O.cm_v_lim(f))


def test_placer_cm_budget_is_the_evaluators_line():
    assert PR.WORLD["i_cm_budget_uA"] == pytest.approx(CR.cable_i_lim(1e8) * 1e6, rel=1e-3)
    assert 2.5 < PR.WORLD["i_cm_budget_uA"] < 2.8


# ----------------------------------------------------------------------------- overshoot
def test_overshoot_limits_derate_the_rating():
    ok, at_abs, va, known = CR.overshoot_limits(12.0, 30.0)
    assert (ok, at_abs, va, known) == (pytest.approx(13.5), pytest.approx(18.0), 30.0, True)
    ok, _, va, known = CR.overshoot_limits(12.0)
    assert va == 16.0 and not known and ok == pytest.approx(1.6)


def test_overshoot_hazard_blocks_past_a_known_abs_max():
    assert CR.overshoot_hazard("cell:U1", ["U1"], 12.0, 10.0, 30.0) is None
    h = CR.overshoot_hazard("cell:U1", ["U1"], 12.0, 15.0, 30.0)
    assert h["severity"] == "warn" and h["code"] == "overshoot_over_derating"
    h = CR.overshoot_hazard("cell:U1", ["U1"], 12.0, 19.0, 30.0)
    assert h["severity"] == "block" and h["code"] == "overshoot_over_abs_max" and h["evidence"]["peak_V"] == 31.0
    h = CR.overshoot_hazard("cell:U1", ["U1"], 12.0, 5.0)                 # past the prior's 16 V: may be rated higher
    assert h["severity"] == "warn" and h["evidence"]["V_abs_source"] == "prior"
    assert {"code", "severity", "category", "message", "objects", "evidence", "fix"} <= set(h)


def test_evaluator_bound_is_the_placers_criterion():
    assert HA.overshoot_bound({"V_V": 12.0, "V_max_V": 30.0}, 9.9) == pytest.approx(13.5)
    assert HA.overshoot_bound({"V_V": 12.0}, 9.9) == pytest.approx(0.85 * 16 - 12)
    assert HA.overshoot_bound({}, 9.9) == 9.9
    # the router's legacy prices (KAE_SHARED_OVERSHOOT off)
    assert HA.overshoot_bound({"V_V": 12.0, "V_max_V": 30.0}, 9.9, legacy=2.4) == pytest.approx(18.0)
    assert HA.overshoot_bound({"V_V": 12.0}, 9.9, legacy=2.4) == 2.4
    # the placer's budget reaches the same peak: a = (0.85 V_abs - V_in) / V_in
    assert "a = 0.13" in PR.hot_loop_budget("buck", 12.0, 120, 1.5).basis
    assert "a = 0.42" in PR.hot_loop_budget("buck", 12.0, 120, 1.5, v_abs=20.0).basis
    assert PR.hot_loop_budget("buck", 12.0, 120, 1.5, v_abs=30.0).value == 50.0    # never reaches 25.5 V


def test_overshoot_hazard_over_corners_keeps_the_worst():
    vals = [{"V_V": 12.0, "V_max_V": 30.0}, {"V_V": 13.2, "V_max_V": 30.0}]
    h = HA.overshoot_hazard("c", ["U1"], vals, [14.0, 17.0])
    assert h["severity"] == "block" and h["evidence"]["corners_over"] == 2


def test_shared_overshoot_switch(monkeypatch):
    monkeypatch.delenv("KAE_SHARED_OVERSHOOT", raising=False)
    assert PR.budget_v_abs({"V_abs": 30.0}) is None
    monkeypatch.setenv("KAE_SHARED_OVERSHOOT", "1")
    assert PR.budget_v_abs({"V_abs": 30.0}) == 30.0


def test_place_report_flags_a_loop_past_the_abs_max():
    from kae.place.pipeline import hot_loop_hazards
    row = dict(id="cell:U1", kind="commutation", value=3.0, members=["U1", "C1"],
               info=dict(L_abs_nH=1.6, V_abs=16.0, V_abs_known=False, V_in=12.0))
    h = hot_loop_hazards([row, dict(row, value=1.0)])
    assert len(h) == 1 and h[0]["severity"] == "warn"
    assert hot_loop_hazards([dict(row, info=dict(row["info"], V_abs_known=True))])[0]["severity"] == "block"
