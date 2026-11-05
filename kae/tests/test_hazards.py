# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
import json

import pytest

from kae import hazards as H


def test_make_validates():
    h = H.make("short", "block", "electrical", "a short", objects=["GND", None, ""], evidence=dict(n=1), fix="move")
    assert h == dict(code="short", severity="block", category="electrical", message="a short", objects=["GND"],
                     evidence=dict(n=1), fix="move")
    with pytest.raises(ValueError):
        H.make("x", "error", "electrical", "m")
    with pytest.raises(ValueError):
        H.make("x", "warn", "elec", "m")


def test_normalize_hand_written():
    h = H.normalize(dict(code="c", severity="fatal", category="?", objects="U1"))
    assert h["severity"] == "warn" and h["category"] == "data" and h["objects"] == ["U1"]
    assert h["evidence"]["severity_given"] == "fatal"
    assert H.normalize(dict(severity="block")) is None


def test_dedupe_keeps_most_severe_and_sources():
    a = dict(H.make("c", "warn", "data", "m", objects=["B", "A"]), source="x")
    b = dict(H.make("c", "block", "data", "m", objects=["A", "B"]), source="y")
    out = H.dedupe([a, b, H.make("c", "warn", "data", "m", objects=["C"])])
    assert len(out) == 2
    assert out[0]["severity"] == "block" and out[0]["sources"] == ["y", "x"]


def test_sort_and_cap():
    es = [H.make("w", "warn", "data", "m", objects=[str(i)]) for i in range(20)]
    es += [H.make("b", "block", "electrical", "m", objects=[str(i)]) for i in range(3)]
    es += [H.make("i", "info", "data", "m")]
    shown, omitted = H.cap(es, max_entries=6, max_per_code=4)
    assert [h["code"] for h in shown[:3]] == ["b"] * 3
    assert len(shown) == 6 and omitted == dict(w=17, i=1)


def test_cap_never_drops_block_for_space():
    es = [H.make(f"b{i}", "block", "electrical", "m") for i in range(5)]
    shown, omitted = H.cap(es, max_entries=2)
    assert len(shown) == 5 and not omitted


def test_compact_truncates_with_counts():
    h = H.make("c", "warn", "data", "x" * 1000, objects=[f"N{i}" for i in range(30)])
    shown, _ = H.cap([h])
    assert len(shown[0]["message"]) == H.MAX_MESSAGE and shown[0]["objects_more"] == 30 - H.MAX_OBJECTS


def test_finalize_hoists_nested_and_derives_flags():
    rep = dict(status="ok",
               critical=dict(hazards=[H.make("a", "warn", "data", "m")],
                             modules=[dict(flags=[dict(flag="class_max_below_ipc", hop=0, net="+12V", I_A=5.0,
                                                       ipc_mm=4.1, cap_mm=3.0)])]),
               iterations=[dict(hazards=[H.make("a", "warn", "data", "m")]),
                           dict(hazards=[H.make("s", "block", "electrical", "short", objects=["GND", "+5V"])])],
               place=dict(dru_rejected="unknown token", bodies_relaxed=["J1", "J2"],
                         steps=[dict(step="bodies relaxed", relaxed=["J1"])]),
               hazards=[H.make("top", "info", "data", "m")])
    H.finalize(rep)
    assert list(rep)[-2:] == ["hazards", "hazard_summary"]
    codes = [h["code"] for h in rep["hazards"]]
    assert codes[0] == "s"
    assert sorted(codes) == sorted(["s", "a", "class_max_below_ipc", "dru_rejected", "top"])
    # relaxed bodies are reported only by Problem.relaxed_body_hazards (body_overlap / body_relaxed)
    assert "bodies_relaxed" not in codes
    assert "hazards" not in rep["critical"] and "hazards" not in rep["iterations"][0]
    s = rep["hazard_summary"]
    assert s["blocked"] and s["block"] == 1 and s["warn"] == 3 and s["info"] == 1 and s["total"] == 5
    assert s["block_codes"] == dict(s=1)
    a = next(h for h in rep["hazards"] if h["code"] == "a")
    assert a["sources"] == ["critical", "iterations[0]"]
    json.dumps(rep)
    H.finalize(rep)                       # idempotent
    assert rep["hazard_summary"]["total"] == 5


def test_finalize_empty():
    rep = H.finalize(dict(status="ok"))
    assert rep["hazards"] == [] and rep["hazard_summary"]["blocked"] is False


def test_derive_escape_checked_and_physics():
    cert = dict(package="U1", constraint="escape", demand=40, escapable=31.5, short=9, layers=["F.Cu", "B.Cu"],
                relaxations=[dict(rule="clearance", value=0.09, all=True), dict(rule="2 more signal layers", all=False)])
    rep = dict(iterations=[dict(route=dict(blocked=dict(packages=[cert])))],
               final=dict(checked=dict(drc=False, physics=True, brief=True), modules={"cell:U3": 1.8, "decap:U1": 0.4,
                                                                                       "x": None}))
    hz = {h["code"]: h for h in H.derive(rep)}
    assert hz["escape_infeasible"]["severity"] == "block" and "clearance 0.09 mm" in hz["escape_infeasible"]["fix"]
    assert hz["check_not_run"]["objects"] == ["drc"]
    assert hz["physics_over_budget"]["objects"] == ["cell:U3"] and hz["physics_over_budget"]["evidence"]["u"] == 1.8


def test_sim_hazards():
    ev = dict(tests=[dict(id="t1", kind="rail_dc", nets=["+3V3"], status="fail",
                          requirements=[dict(op=">=", bound=3.2, status="fail", routed=dict(typ=3.1))]),
                     dict(id="t2", kind="rail_dc", nets=["+5V"], status="pass")])
    hz = H.sim_hazards(ev)
    assert [(h["code"], h["severity"], h["objects"]) for h in hz] == [("sim_fail", "warn", ["+3V3"])]


def test_derive_place_and_rules_flags():
    rep = dict(legal=False, exact=[1, 2], outline_incomplete=["J9"],
               plan=dict(notes=dict(unsupported_functions=["inDiffPair"], rule_errors=[])))
    hz = {h["code"]: h for h in H.derive(rep)}
    assert hz["outline_incomplete"]["severity"] == "block" and hz["outline_incomplete"]["objects"] == ["J9"]
    assert hz["placement_illegal"]["evidence"]["exact_findings"] == 2
    assert hz["rules_not_modelled"]["objects"] == ["inDiffPair"] and "rule_errors" not in hz


def test_capped_rail_flags_are_left_to_the_copper_heat_hazards():
    """rail_max_cap / ipc_floor_unroutable flags are not derived: the same hop already carries
    copper_below_ipc_width / rail_left_narrow with its computed rise (one cause, one entry)."""
    rep = dict(modules=[dict(flags=[dict(flag="rail_max_cap", hop=0, net="+12V", I_A=10.0, ipc_mm=7.2, cap_mm=3.0),
                                    dict(flag="ipc_floor_unroutable", hop=1, net="+12V", I_A=10.0, floor_mm=7.2)])])
    assert H.derive(rep) == []
