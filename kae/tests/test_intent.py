# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""kae.intent: the objective a board is held to comes from its intent; the evaluator only measures."""
import pytest

from kae.excite import harm as HA
from kae.intent import objective as OB
from kae.intent import units as U

# a converter section (cell U3 with L1, C1 on SW and VIN) and a GNSS section (U7 with its RF_IN net)
BRIEF = {"parts": {"u3": {"ref": "U3"}, "l1": {"ref": "L1"}, "c1": {"ref": "C1"}, "u7": {"ref": "U7"},
                   "j1": {"ref": "J1"}, "j2": {"ref": "J2"}},
         "structures": [{"id": "cell:buck:U3", "kind": "commutation_cell", "controller": "u3", "inductor": "l1",
                         "input_caps": ["c1"], "sw": "SW"},
                        {"id": "victim:analog:U7", "kind": "victim", "ic": "u7", "nets": ["RF_IN"]}]}


def _ob(id_, unit, values, u=None, ref=None, **scope):
    return dict(id=id_, unit=unit, values=values, u=u or [0.0] * len(values), scope=scope,
                reference=dict(value=ref, basis="old bound"), label=f"{id_} {scope.get('observer', '')}")


def _ev(loss_W, pickup_V, cm_V=1e-3):
    n = len(loss_W)
    return {"board": "synthetic", "total": {"complete": True}, "questions": [], "observations": [
        _ob("loss.copper", "W", loss_W, u=[x / 0.036 for x in loss_W], ref=0.036, kind="dc_loss", nets=["VIN"]),
        _ob("pickup.peak", "V", pickup_V, u=[x / 0.01 for x in pickup_V], ref=0.01, kind="victim",
            observer="victim:analog:U7.3", source="cell:buck:U3", from_struct="cell:buck:U3", from_parts=["U3"],
            from_nets=["SW"], to_parts=["U7"], to_nets=["RF_IN"]),
        dict(_ob("cable_cm.v", "V", [cm_V] * n, kind="cm", observer="cm:J1-J2", source="cell:buck:U3",
                 from_struct="cell:buck:U3", connectors=["J1", "J2"]), f_Hz=[1e8] * n)]}


WIDE = _ev([0.037] * 5, [0.004] * 5)        # wide traces: low loss, more pickup
THIN = _ev([0.128] * 5, [0.001] * 5)        # thin traces: 3.5x the loss, less pickup


def test_with_no_intent_only_copper_loss_is_priced():
    a, b = OB.evaluate(WIDE, None, BRIEF), OB.evaluate(THIN, None, BRIEF)
    assert a["tiers"]["cost"] == pytest.approx(37.0) and b["tiers"]["cost"] == pytest.approx(128.0)
    assert OB.key(a) < OB.key(b)
    assert {u["obs"] for u in a["unclaimed"]} == {"pickup.peak", "cable_cm.v"}       # reported, not priced
    assert any(q["id"] == "Q-cables" for q in a["questions"])


def test_a_contract_between_sections_can_reverse_the_ranking():
    it = {"terms": [{"id": "C1", "tier": "limit", "obs": "pickup.peak",
                     "where": {"from": "cell:buck:U3", "to": "victim:analog:U7"}, "max": "2 mV",
                     "rate": "100 mW_eq/mV", "why": "the GNSS front end must not see the buck"}]}
    a, b = OB.evaluate(WIDE, it, BRIEF), OB.evaluate(THIN, it, BRIEF)
    c1 = next(r for r in a["terms"] if r["id"] == "C1")
    assert c1["met"] is False and c1["contribution"] == pytest.approx(200.0)     # 2 mV over at 100 per mV
    assert next(r for r in b["terms"] if r["id"] == "C1")["met"] is True
    assert OB.key(b) < OB.key(a)


def test_a_boundary_term_does_not_match_the_wrong_direction():
    it = {"terms": [{"id": "C1", "tier": "report", "obs": "pickup.peak",
                     "where": {"from": "victim:analog:U7", "to": "cell:buck:U3"}, "why": "reverse"}]}
    assert next(r for r in OB.evaluate(WIDE, it, BRIEF)["terms"] if r["id"] == "C1")["matched"] == 0


def test_a_hard_violation_outranks_any_cost():
    it = {"terms": [{"id": "H1", "tier": "hard", "obs": "loss.copper", "max": "50 mW", "why": "thermal budget"}]}
    a, b = OB.evaluate(WIDE, it, BRIEF), OB.evaluate(THIN, it, BRIEF)
    assert a["tiers"]["hard"] == 0 and b["tiers"]["hard"] > 0 and OB.key(a) < OB.key(b)


def test_declared_cables_turn_common_mode_into_a_field_at_10_m():
    it = {"environment": {"cables": [{"connector": "J1", "length_m": 1.5}]},
          "terms": [{"id": "E1", "tier": "limit", "obs": "emission.cable_E", "max": "30 dBuV/m", "rate": "5 mW_eq/dB",
                     "source": "CISPR 32 class B"}]}
    st = OB.evaluate(WIDE, it, BRIEF)
    e1 = next(r for r in st["terms"] if r["id"] == "E1")
    E = U.to_log(1.26e-6 * 1e8 * 1.5 * (1e-3 / 150) / 10, "dBuV/m")
    assert e1["value"].startswith(f"{E:.4g}") and e1["met"] == (E <= 30)
    assert not any(q["id"] == "Q-cables" for q in st["questions"])


def test_legacy_profile_reproduces_the_evaluators_sum():
    st = OB.evaluate(THIN, {"defaults": "legacy/u"}, BRIEF)
    tot = [sum(HA.phi(o["u"][c]) for o in THIN["observations"]) for c in range(5)]
    assert st["tiers"]["cost"] == pytest.approx(HA.robust(tot)[0], abs=0.01)


@pytest.mark.parametrize("term, says", [
    ({"id": "X", "tier": "limit", "obs": "drop.rail", "max": "27 mV", "why": "w"}, "needs a 'rate'"),
    ({"id": "X", "tier": "cost", "obs": "loss.copper", "rate": "1 mW_eq/mV", "why": "w"}, "per V"),
    ({"id": "X", "tier": "hard", "obs": "loss.copper", "max": "50 mQ", "why": "w"}, "unit 'mQ' unknown"),
    ({"id": "X", "tier": "report", "obs": "ripple", "why": "w"}, "matches no kind"),
    ({"id": "X", "tier": "report", "obs": "loss.copper"}, "say why"),
    ({"id": "X", "tier": "report", "obs": "pickup.peak", "where": {"to": "radio"}, "why": "w"}, "names no section"),
])
def test_errors_say_how_to_fix_them(term, says):
    with pytest.raises((OB.IntentError, U.UnitError)) as e:
        OB.evaluate(WIDE, {"terms": [term]}, BRIEF)
    assert says in str(e.value)


def test_the_copper_policy_widens_with_current_and_follows_the_area_knob():
    from kae.intent import route as IR
    ladder = (0.15, 0.2, 0.25, 0.3, 0.4, 0.5, 0.6, 0.8, 1.0, 1.2, 1.5, 2.0, 2.5, 3.0)
    p = IR.Policy({})                                     # neutral/1: copper loss at 1 mW_eq/mW
    w = [p.width("VIN", [i] * 5, 0.035, 0.2, ladder, 0.2, None)[0] for i in (0.05, 0.3, 1.0)]
    assert w[0] == 0.2 and w[0] < w[1] < w[2]
    # w* = sqrt(k rho / (t a)): four times the area cost halves the width
    q = IR.Policy({"knobs": {"route.area_cost": 0.2}})
    assert q.width("VIN", [0.3] * 5, 0.035, 0.2, ladder, 0.2, None)[0] < w[1]
    # a heating limit floors the width at IPC-2221's
    h = IR.Policy({"terms": [{"id": "H", "tier": "hard", "obs": "heat.track", "max": "5 K", "why": "w"}],
                   "knobs": {"route.area_cost": 100}})
    from kae.route.critical_physics import ipc2221_width
    assert h.width("VIN", [2.0] * 5, 0.035, 0.2, ladder, 0.2, None)[0] >= ipc2221_width(2.0, 5, 0.035)
