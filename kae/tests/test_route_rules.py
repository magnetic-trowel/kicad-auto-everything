# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""kae.route.rules: KiCad's rule resolution in Python (no KiCad needed; the agreement with
KiCad's own engine is checked in test_route_kicad.py)."""
import pytest

from kae.route import rules as R

COPPER = ["F.Cu", "In1.Cu", "In2.Cu", "B.Cu"]
SETTINGS = dict(min_clearance=0.15, min_track=0.13, min_via=0.45, min_annular=0.1, min_drill=0.3,
                hole_clearance=0.25, hole_to_hole=0.25, edge_clearance=0.3, min_uvia=0.2, min_uvia_drill=0.1)
CLASSES = {
    "Default": dict(clearance=0.2, track_width=0.25, via_diameter=0.6, via_drill=0.3, dp_width=0.2, dp_gap=0.25),
    "Power": dict(clearance=0.3, track_width=0.5, via_diameter=0.8, via_drill=0.4),
    "HS,Default": dict(clearance=0.2, track_width=0.15, via_diameter=0.6, via_drill=0.3, dp_width=0.2, dp_gap=0.1),
}


def board(dru_text=None, tmp_path=None, nets=("A", "B", "D_P", "D_N", "PWR")):
    path = None
    if dru_text is not None:
        path = tmp_path / "board.kicad_dru"
        path.write_text(dru_text)
    return R.build(COPPER, SETTINGS, CLASSES, set(nets), str(path) if path else None)


def track(net, nc="Default", layer="F.Cu", width=0.2):
    return dict(type="Track", net=net, netclass=nc, constituents=nc.split(","), copper=True, connected=True,
                layer=layer, width=width, layers=[layer])


def via(net, nc="Default"):
    return dict(type="Via", net=net, netclass=nc, constituents=nc.split(","), copper=True, connected=True,
                via_type="Through", drilled=True, layers=COPPER)


def pad(net, nc="Default", **kw):
    d = dict(type="Pad", net=net, netclass=nc, constituents=nc.split(","), copper=True, connected=True,
             pad_type="SMD", fab_property="None", ref="U1", lib="Lib:QFN", layers=["F.Cu"])
    d.update(kw)
    return d


def test_condition_language():
    ctx = R.Ctx(track("GND_1", "HS,Default"), pad("X", pad_type="Through-hole"), "In1.Cu", "clearance")
    def t(expr):
        return R.truth(R.ev(R.compile_condition(expr), ctx))
    assert t("A.Type == 'track'") and t("A.Type == 'TRACK'")          # case-insensitive
    assert t("A.NetName == 'GND_*'") and not t("A.NetName == 'GND'")  # wildcards in the literal
    assert t("A.NetClass == 'HS'") and t("A.NetClass == 'Default'")   # constituents match
    assert t("B.isPlated()") and not t("A.isPlated()")
    assert t("A.Layer == 'In?.Cu'") and t("A.Width == 0.2mm") and t("A.Width < 10mil")
    assert t("B.Pad_Type == 'Through-hole' && !(A.Type == 'Via')")
    assert t("A.Net != B.Net")
    # an unterminated literal runs to the end, as KiCad's lexer reads it
    assert R.compile_condition("A.NetClass == 'Diff")[3] == ("str", "Diff")


def test_undefined_compares_false_both_ways():
    ctx = R.Ctx(track("A"), None, "F.Cu", "clearance")
    for expr in ("B.Type == 'track'", "B.Type != 'track'"):
        assert not R.truth(R.ev(R.compile_condition(expr), ctx))


def test_netclass_clearance_takes_the_larger_class_and_board_minimum():
    b = board()
    assert R.evaluate(b, "clearance", track("A"), track("PWR", "Power"), "F.Cu").min == 0.3
    assert R.evaluate(b, "clearance", track("A"), track("B"), "F.Cu").min == 0.2
    lo = R.build(COPPER, dict(SETTINGS, min_clearance=0.22), CLASSES, {"A", "B"})
    c = R.evaluate(lo, "clearance", track("A"), track("B"), "F.Cu")
    assert c.min == 0.22 and c.rule == "board minimum"


def test_track_width_opt_is_the_netclass_width_and_min_the_board_minimum():
    b = board()
    c = R.evaluate(b, "track_width", track("A"), None, "F.Cu")
    assert (c.min, c.opt) == (0.13, 0.25)
    c = R.evaluate(b, "track_width", track("D_P"), None, "F.Cu")  # diff pair: dp width
    assert c.opt == 0.2


def test_custom_rules_last_match_wins_and_may_go_below_board_minimum(tmp_path):
    dru = """(version 1)
(rule a (constraint clearance (min 0.5mm)) (condition "A.Type == 'track'"))
(rule b (constraint clearance (min 0.1mm)) (layer outer) (condition "A.Type == 'track' && B.Type == A.Type"))
"""
    b = board(dru, tmp_path)
    assert R.evaluate(b, "clearance", track("A"), track("B"), "F.Cu").min == 0.1      # b wins, below 0.15
    assert R.evaluate(b, "clearance", track("A"), track("B", layer="In1.Cu"), "In1.Cu").min == 0.5
    assert R.evaluate(b, "clearance", pad("B"), track("A"), "F.Cu").min == 0.5        # commutative


def test_local_override_wins_floored_at_board_minimum(tmp_path):
    b = board("(version 1)\n(rule big (constraint clearance (min 0.9mm)))\n", tmp_path)
    assert R.evaluate(b, "clearance", track("A"), pad("B", override=0.1), "F.Cu").min == 0.15
    assert R.evaluate(b, "clearance", track("A"), pad("B", override=0.4), "F.Cu").min == 0.4
    assert R.evaluate(b, "clearance", track("A"), pad("B"), "F.Cu").min == 0.9


def test_geometric_conditions_take_the_strictest(tmp_path):
    dru = """(version 1)
(rule neck (constraint clearance (min 0.1mm)) (constraint track_width (min 0.1mm)) (condition "A.intersectsCourtyard('U1')"))
(rule zone (constraint clearance (min 0.6mm)) (condition "A.intersectsArea('X')"))
"""
    b = board(dru, tmp_path)
    # outside both areas 0.2; inside X 0.6 (tightening applies); inside U1 0.1 (relaxation ignored)
    assert R.strictest(b, "clearance", track("A"), track("B"), "F.Cu").min == 0.6
    assert R.strictest(b, "track_width", track("A"), None, "F.Cu").min == 0.13


def test_hole_to_hole_needs_a_drilled_hole():
    b = board()
    assert R.evaluate(b, "hole_to_hole", via("A"), via("B")).min == 0.25
    assert R.evaluate(b, "hole_to_hole", track("A"), pad("B")).min is None


def test_diff_pair_helpers():
    assert R.diff_base("USB_D+") == "USB_D" and R.complement_net("USB_D+") == "USB_D-"
    assert R.complement_net("LVDS_P_3") == "LVDS_N_3" and R.diff_base("GND") is None


@pytest.mark.parametrize("text", ["A.Type == 'track' &&", "A.foo(", "A.Type ="])
def test_bad_conditions_raise(text):
    with pytest.raises(ValueError):
        R.compile_condition(text)


def test_ignored_clearance_keeps_only_the_floor(tmp_path):
    import json
    from kae.route import constraints as C
    (tmp_path / "board.kicad_pro").write_text(json.dumps(
        {"board": {"design_settings": {"rule_severities": {"clearance": "ignore", "hole_clearance": "error"}}}}))
    info = dict(copper=COPPER, settings=SETTINGS, netclasses=CLASSES, nets={"A": {}, "PWR": {}})
    rb = C.rule_board(info, tmp_path / "board.kicad_pcb")
    a, p = track("A"), track("PWR", nc="Power")
    assert R.strictest(rb, "clearance", a, p, "F.Cu").min == 0.15   # board minimum (>= 0.1 floor), not Power's 0.3
    assert R.strictest(rb, "hole_clearance", via("A"), a, "F.Cu").min == 0.25   # still checked
    rb2 = C.rule_board(info, tmp_path / "other.kicad_pcb")              # no project: nothing ignored
    assert R.strictest(rb2, "clearance", a, p, "F.Cu").min == 0.3
