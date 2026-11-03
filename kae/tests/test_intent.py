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


def test_a_min_bound_is_judged_at_its_lowest_corner():
    """'worst' for a min bound is the smallest corner (max judged it at its best: 50/10/90 mV against
    min 40 mV read 90 mV, met)."""
    ev = {"board": "synthetic", "total": {"complete": True}, "questions": [],
          "observations": [_ob("drop.rail", "V", [0.050, 0.010, 0.090], kind="dc_drop", rail="+3V3")]}
    st = OB.evaluate(ev, {"terms": [{"id": "T1", "tier": "hard", "obs": "drop.rail", "min": "40 mV", "why": "w"}]}, BRIEF)
    t1 = next(r for r in st["terms"] if r["id"] == "T1")
    assert t1["met"] is False and st["tiers"]["hard"] > 0
    assert OB._agg([5.0, 1.0, 9.0, 3.0, 7.0], "cvar20", "min") == 1.0
    assert OB._agg([5.0, 1.0, 9.0, 3.0, 7.0], "cvar20") == 9.0


def test_an_evaluation_without_observations_has_no_score():
    """Missing data is not zero harm: an evaluation with no observations (kae.excite.wideband's) ranked
    as perfect (0, 0)."""
    st = OB.evaluate({"board": "synthetic", "total": {"complete": True}, "harms": [{"u": 9.0}]}, None, BRIEF)
    assert st["tiers"] is None and OB.key(st) == (float("inf"), float("inf"))


def test_a_db_limit_on_a_log_unit_observation_is_not_converted_twice():
    ev = {"board": "synthetic", "total": {"complete": True}, "questions": [],
          "observations": [_ob("emission.cable_E", "dBuV/m", [30.0, 36.0], kind="cm", connectors=["J1"])]}
    st = OB.evaluate(ev, {"terms": [{"id": "E1", "tier": "hard", "obs": "emission.cable_E", "max": "40 dB",
                                     "why": "w"}]}, BRIEF)
    e1 = next(r for r in st["terms"] if r["id"] == "E1")
    assert e1["met"] is True and e1["value"].startswith("36")


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


def _open(ev, missing):
    """The same evaluation with some sources not computed (open copper), their observations absent."""
    ev = dict(ev, total={"complete": False, "not_computed": list(missing)})
    drop = {"dc"} & set(missing)
    ev["observations"] = [o for o in ev["observations"]
                          if not (o["id"] in OB.DC_KINDS and drop) and o["scope"].get("source") not in missing]
    return ev


def test_an_open_source_leaves_only_the_terms_it_feeds_unpriced():
    it = {"terms": [{"id": "T1", "tier": "cost", "obs": "loss.copper", "rate": "1 mW_eq/mW", "why": "loss"},
                    {"id": "T2", "tier": "limit", "obs": "pickup.peak", "max": "2 mV", "rate": "10 mW_eq/mV", "why": "fb"}]}
    st = OB.evaluate(_open(WIDE, ["dc"]), it, BRIEF)
    rows = {r["id"]: r for r in st["terms"]}
    assert rows["T1"]["incomplete"] and rows["T1"]["not_computed"] == ["dc"]
    assert not rows["T2"].get("incomplete") and rows["T2"]["contribution"] == pytest.approx(20.0)
    assert st["tiers"]["cost"] == 0.0 and st["tiers"]["limit"] == pytest.approx(20.0)   # loss not read as zero cost:
    assert st["incomplete_terms"] == ["T1"] and "T1" in st["why_incomplete"]            # it is listed as missing


def test_a_term_scoped_to_other_sources_stays_complete():
    it = {"terms": [{"id": "T2", "tier": "cost", "obs": "pickup.peak", "where": {"source": "cell:*"},
                     "rate": "10 mW_eq/mV", "why": "fb"},
                    {"id": "T3", "tier": "cost", "obs": "pickup.peak", "rate": "10 mW_eq/mV", "why": "any"}]}
    st = OB.evaluate(_open(WIDE, ["clk:SCK"]), it, BRIEF)
    rows = {r["id"]: r for r in st["terms"]}
    assert not rows["T2"].get("incomplete")
    assert rows["T3"]["incomplete"] and rows["T3"]["not_computed"] == ["clk:SCK"]


def test_layouts_are_compared_only_on_the_terms_all_of_them_computed():
    it = {"terms": [{"id": "T1", "tier": "cost", "obs": "loss.copper", "rate": "1 mW_eq/mW", "why": "loss"},
                    {"id": "T2", "tier": "cost", "obs": "pickup.peak", "rate": "10 mW_eq/mV", "why": "fb"}]}
    a, b = OB.evaluate(WIDE, it, BRIEF), OB.evaluate(_open(THIN, ["dc"]), it, BRIEF)
    common = OB.common_terms([a, b])
    assert common == {"T2"}
    assert OB.key(b, common) < OB.key(a, common)          # THIN picks up less; its loss is not counted for either


def test_part_temperatures_in_celsius_meet_limits_in_celsius():
    ev = {"board": "synthetic", "total": {"complete": True}, "questions": [], "observations": [
        _ob("temp.junction", "C", [80.0, 130.0], kind="heat", observer="heat:U3", source="dc", parts=["U3"]),
        _ob("loss.part", "W", [0.2, 0.3], kind="part_loss", observer="loss:U3", source="dc", parts=["U3"])]}
    it = {"terms": [{"id": "T0", "tier": "hard", "obs": "temp.junction", "where": {"part": ["U3"]}, "max": "125 C",
                     "why": "rating"},
                    {"id": "M0", "tier": "limit", "obs": "temp.junction", "where": {"part": ["U3"]}, "max": "105 C",
                     "rate": "2 mW_eq/C", "why": "margin"},
                    {"id": "P2", "tier": "cost", "obs": "loss.part", "rate": "1 mW_eq/mW", "agg": "worst", "why": "loss"}]}
    st = OB.evaluate(ev, it, BRIEF)
    rows = {r["id"]: r for r in st["terms"]}
    assert rows["T0"]["met"] is False and st["tiers"]["hard"] > 0          # 130 C over 125 C: a hard violation
    assert rows["M0"]["contribution"] == pytest.approx(2 * 25.0)          # 25 K over the margin at 2 mW_eq/C
    assert rows["T0"]["value"] == "130 C"
    assert rows["P2"]["contribution"] == pytest.approx(300.0)


def test_a_dc_band_gap_also_leaves_temperatures_and_part_losses_unpriced():
    it = {"terms": [{"id": "T0", "tier": "hard", "obs": "temp.junction", "max": "125 C", "why": "rating"},
                    {"id": "P4", "tier": "cost", "obs": "loss.loop_ac", "rate": "1 mW_eq/mW", "why": "loop"}]}
    st = OB.evaluate(_open(WIDE, ["dc"]), it, BRIEF)
    rows = {r["id"]: r for r in st["terms"]}
    assert rows["T0"]["incomplete"] and not rows["P4"].get("incomplete")


def test_an_implausible_observation_is_priced_at_its_cap_for_every_layout():
    """kae.excite flags supply noise beyond half its rail; kae.intent prices it clipped at that cap, so two
    layouts past the cap price alike (left unpriced, the worse one escaped its term); the status lists it."""
    from kae.excite import observe as O
    sup = O.Observer("supply:IC1:PWRSTAT", "supply", "a", "g", bound=0.165, meta=dict(ref="IC1", rail="PWRSTAT", V=3.3))
    ok = O.Observer("supply:U2:VBAT", "supply", "a", "g", bound=0.185, meta=dict(ref="U2", rail="VBAT", V=3.7))
    assert O.implausible(sup, [0.5, 15.2]) and O.implausible(ok, [0.05, 0.2]) is None
    src = O.Observer("core:IC1:PWRSTAT", "core", "a", "g")
    it = {"terms": [{"id": "S1", "tier": "limit", "obs": "supply.peak", "max": "0.1 V", "rate": "100 mW_eq/V", "why": "test"}]}
    costs = []
    for peak in (15.2, 4.0):                       # two layouts, both past the 1.65 V cap
        ev = _ev([0.037] * 2, [0.004] * 2)
        bad = O.observation(type("BD", (), {"pads_of": {}})(), sup, src, [0.5, peak], [0.0, 0.0])
        assert bad["implausible"] and bad["cap_V"] == pytest.approx(1.65)
        ev["observations"].append(bad)
        st = OB.evaluate(ev, it, BRIEF)
        s1 = next(r for r in st["terms"] if r["id"] == "S1")
        assert s1["matched"] == 1 and s1["contribution"] > 0
        assert st["implausible"][0]["label"] == bad["label"] and st["implausible"][0]["capped_at"] == pytest.approx(1.65)
        costs.append(s1["contribution"])
    assert costs[0] == pytest.approx(costs[1])
    # an evaluation from before cap_V: the cap is read from the reason (half of the 3.3 V rail)
    ev = _ev([0.037] * 2, [0.004] * 2)
    old = O.observation(type("BD", (), {"pads_of": {}})(), sup, src, [0.5, 15.2], [0.0, 0.0])
    old.pop("cap_V")
    ev["observations"].append(old)
    s1 = next(r for r in OB.evaluate(ev, it, BRIEF)["terms"] if r["id"] == "S1")
    assert s1["contribution"] == pytest.approx(costs[0])


DROP = {"board": "synthetic", "total": {"complete": True}, "questions": [],
        "observations": [_ob("drop.rail", "V", [0.050] * 3, kind="dc_drop", rail="+3V3", load="U5", parts=["U5"],
                             nets=["+3V3"])]}


def test_an_observation_is_priced_by_its_most_specific_term_only():
    """Specificity (intent-driven-objectives.md §5): a board-wide drop cost and a +3V3 one at the same rate
    priced the drop twice (100 instead of 50)."""
    it = {"terms": [{"id": "B", "tier": "cost", "obs": "drop.rail", "rate": "1 mW_eq/mV", "why": "w"},
                    {"id": "R", "tier": "cost", "obs": "drop.rail", "where": {"rail": "+3V3"}, "rate": "1 mW_eq/mV",
                     "why": "w"}]}
    st = OB.evaluate(DROP, it, BRIEF)
    assert st["tiers"]["cost"] == pytest.approx(50.0)
    b = next(r for r in st["terms"] if r["id"] == "B")
    assert b["matched"] == 0 and b["overridden_by"] == ["R"]


def test_terms_of_other_tiers_or_sides_do_not_compete():
    it = {"terms": [{"id": "Lo", "tier": "limit", "obs": "drop.rail", "min": "10 mV", "rate": "1 mW_eq/mV", "why": "w"},
                    {"id": "Hi", "tier": "limit", "obs": "drop.rail", "max": "40 mV", "rate": "1 mW_eq/mV", "why": "w"},
                    {"id": "H", "tier": "hard", "obs": "drop.rail", "max": "60 mV", "why": "w"}]}
    st = OB.evaluate(DROP, it, BRIEF)
    assert all(r["matched"] == 1 for r in st["terms"] if r["id"] in ("Lo", "Hi", "H"))
    assert st["tiers"]["limit"] == pytest.approx(10.0)


def test_equal_specificity_overlap_is_an_error_naming_both_terms():
    it = {"terms": [{"id": "A", "tier": "cost", "obs": "drop.rail", "where": {"rail": "+3V3"}, "rate": "1 mW_eq/mV",
                     "why": "w"},
                    {"id": "B", "tier": "cost", "obs": "drop.*", "where": {"load": "U5"}, "rate": "2 mW_eq/mV",
                     "why": "w"}]}
    with pytest.raises(OB.IntentError, match=r"\['A', 'B'\]"):
        OB.evaluate(DROP, it, BRIEF)


def test_a_drop_limit_costs_the_router_nothing_until_it_is_exceeded():
    """'Limits have epsilon-constraint semantics: once met they cost nothing' (§6). k_R charged a drop limit's
    rate on every net, whatever its bound or its where.load (2000 per V.A on an unrelated signal net)."""
    from kae.intent import route as IR
    lim = {"id": "T2", "tier": "limit", "obs": "drop.rail", "where": {"load": "U5"}, "max": "27 mV",
           "rate": "2 mW_eq/mV", "why": "w"}
    p, base = IR.Policy({"terms": [lim]}), IR.Policy({})
    for net in ("+5V", "SOME_SIGNAL"):
        assert p.k_R(net, [1.0] * 3) == base.k_R(net, [1.0] * 3)
    # a cost on +5V's drop prices +5V's copper, not other nets'
    c = IR.Policy({"terms": [{k: v for k, v in dict(lim, id="C", tier="cost", where={"rail": "+5V"}).items() if k != "max"}]})
    assert c.k_R("+5V", [1.0] * 3)[0] > base.k_R("+5V", [1.0] * 3)[0]
    assert c.k_R("SOME_SIGNAL", [1.0] * 3) == base.k_R("SOME_SIGNAL", [1.0] * 3)
    # in physics routing the limit is priced by its excess at the load it names only
    ob = dict(loss=(0.0, 0.0, 1.0), drops=[("U5", "+5V", 0.0, 0.030, 0.0), ("U6", "+5V", 0.0, 0.040, 0.0)])
    assert p.dc_cost(ob) == pytest.approx(2000 * 0.003)
    assert p.dc_cost(dict(ob, drops=[("U5", "+5V", 0.0, 0.020, 0.0)])) == 0.0


def test_router_scopes_must_all_hold():
    from kae.intent import route as IR
    t = {"id": "X", "where": {"rail": "+5V", "part": "U5"}}
    assert not IR._net_matches(t, "+5V", {})          # a part scope says nothing about a bare net
    assert IR._net_matches({"id": "Y", "where": {"rail": "+5*"}}, "+5V", {})
    assert IR._net_matches({"id": "Z"}, "ANY", {})
