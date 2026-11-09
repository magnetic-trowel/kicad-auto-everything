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


def test_ignored_clearance_floor_is_overridable(tmp_path):
    import json
    from kae.route import constraints as C
    info = dict(copper=COPPER, settings=dict(SETTINGS, min_clearance=0.0), netclasses=CLASSES, nets={"A": {}, "PWR": {}})
    a, p = track("A"), track("PWR", nc="Power")
    pro = {"board": {"design_settings": {"rule_severities": {"clearance": "ignore"}}}}
    (tmp_path / "board.kicad_pro").write_text(json.dumps(pro))
    rb = C.rule_board(info, tmp_path / "board.kicad_pcb")
    assert R.strictest(rb, "clearance", a, p, "F.Cu").min == C.DEFAULTS["ignored_clearance_floor"]
    rb = C.rule_board(info, tmp_path / "board.kicad_pcb", dict(ignored_clearance_floor=0.08))
    assert R.strictest(rb, "clearance", a, p, "F.Cu").min == 0.08              # run option
    pro["text_variables"] = {"KAE_IGNORED_CLEARANCE_FLOOR": "0.05"}
    (tmp_path / "board.kicad_pro").write_text(json.dumps(pro))
    rb = C.rule_board(info, tmp_path / "board.kicad_pcb", dict(ignored_clearance_floor=0.08))
    assert R.strictest(rb, "clearance", a, p, "F.Cu").min == 0.05              # the project wins


def test_zero_length_edge_shapes_are_skipped():
    from kae.route import constraints as C
    info = dict(outline=[[[(0, 0), (10, 0), (10, 10), (0, 10)]]],
                edges=[dict(kind="segment", layer="Edge.Cuts", pts=[(5, 5), (5, 5)]),
                       dict(kind="segment", layer="Edge.Cuts", pts=[(2, 2), (3, 3)])])
    cut, stray, board = C._edge_geoms(info)   # raised GEOSException on the zero-length segment
    assert board is not None and len(stray) == 1


def test_condition_precedence_is_kicads_not_cs():
    """&& binds looser than ||, and ! binds tighter than comparisons
    (docs/topics/kicad/drc-rule-language-reference.md, Precedence)."""
    A, B = ("prop", "A", "NetClass"), ("prop", "B", "NetClass")
    c = R.compile_condition("A.NetClass == 'PUSB' || A.NetClass == 'PA' && B.NetClass == 'PGND'")
    assert c == ("and", ("or", ("cmp", "==", A, ("str", "PUSB")), ("cmp", "==", A, ("str", "PA"))),
                 ("cmp", "==", B, ("str", "PGND")))
    assert R.compile_condition("!A.Name == ''") == ("cmp", "==", ("not", ("prop", "A", "Name")), ("str", ""))
    # rustaphor lightrelay: a PUSB track is held off PGND only, not off every other net
    def t(expr, a, b):
        return R.truth(R.ev(R.compile_condition(expr), R.Ctx(a, b, "F.Cu", "clearance")))
    e = "A.NetClass == 'PUSB' || A.NetClass == 'PA' && B.NetClass == 'PGND'"
    assert t(e, track("V", "PUSB"), track("G", "PGND"))
    assert not t(e, track("V", "PUSB"), track("S", "Default"))
    # trident pcbleakage: '!A.Name' is a number, never equal to '', so the zone part never holds
    e = "A.Type == 'Zone' && !A.Name == '' && B.Type == 'Zone' && B.Name == '' || B.Type == 'Via'"
    zone = dict(type="Zone", net="G", netclass="Default", copper=True, connected=True, name="", layers=["F.Cu"])
    assert not t(e, dict(zone, name="Z1"), dict(zone))
    assert not t(e, zone, via("A"))


def test_unitless_numbers_in_conditions_are_nm():
    """drc-rule-language-reference.md: a unitless value inside a condition is nm."""
    ctx = R.Ctx(track("A", width=0.25), None, "F.Cu", "track_width")
    def t(expr):
        return R.truth(R.ev(R.compile_condition(expr), ctx))
    assert t("A.Width > 200000") and not t("A.Width > 300000") and t("A.Width == 250000")
    assert t("A.Width > 0.2mm") and t("A.Width == 0.25mm") and t("A.Width < 10mil")
    assert t("A.Width > 0.1mm + 100000") and t("A.Width * 2 == 0.5mm")


def test_a_second_condition_overwrites_the_first(tmp_path):
    """drc-rule-language-reference.md: a second (condition) silently overwrites the first
    (beaglebone-ai's EMMC rule, azonenberg's switch engine); both readers keep the last."""
    from kae.board import kicad_file
    dru = """(version 1)
(rule two (condition "A.Type == 'Zone'") (condition "B.Type == 'Via'")
  (constraint clearance (min 0.7mm)))
"""
    b = board(dru, tmp_path)
    assert b.rules[-1].text == "B.Type == 'Via'"
    assert R.evaluate(b, "clearance", track("A"), via("B"), "F.Cu").min == 0.7
    assert kicad_file.read_dru(tmp_path / "board.kicad_dru")[0]["condition"] == "B.Type == 'Via'"


def test_a_custom_rule_that_is_not_an_error_does_not_bind(tmp_path):
    """drc-rule-language-reference.md: an ignore rule still overrides earlier rules but KiCad
    reports nothing for it (a warning is not a scored error), so strictest() keeps only the
    floor of an ignored clearance check, and the net-class limits for anything else."""
    from kae.route import constraints as C
    dru = """(version 1)
(rule wall (severity ignore) (condition "A.NetClass == 'Power'") (constraint clearance (min 0.8mm)))
(rule wide (severity warning) (condition "A.NetName == 'B'") (constraint track_width (min 0.6mm) (max 0.7mm)))
(rule hard (condition "A.NetName == 'D_P'") (constraint track_width (min 0.6mm)))
"""
    (tmp_path / "board.kicad_dru").write_text(dru)
    info = dict(copper=COPPER, settings=SETTINGS, netclasses=CLASSES, nets={"A": {}, "B": {}, "D_P": {}, "PWR": {}})
    rb = C.rule_board(info, tmp_path / "board.kicad_pcb")
    a, p = track("A"), track("PWR", nc="Power")
    assert R.evaluate(rb, "clearance", a, p, "F.Cu").min == 0.8           # KiCad's resolution is unchanged
    assert R.strictest(rb, "clearance", a, p, "F.Cu").min == 0.15         # board minimum (>= 0.1 floor)
    w = R.strictest(rb, "track_width", track("B"), None, "F.Cu")
    assert (w.min, w.max) == (0.13, None)                                 # net class and board setup
    assert R.strictest(rb, "track_width", track("D_P"), None, "F.Cu").min == 0.6   # error severity binds


def test_a_rules_file_kicad_drops_gives_no_custom_rules(tmp_path, capsys):
    """drc-rule-language-reference.md: KiCad drops the whole .kicad_dru on any parse error and
    its DRC runs with net-class and board rules only; both readers do the same, say why on
    stderr and record it for the route and place reports."""
    from kae.board import kicad_file
    from kae.route import constraints as C
    dru = """(version 1)
(rule big (constraint clearance (min 0.9mm)))
(rule typo (constraint clearence (min 0.1mm)))
"""
    (tmp_path / "board.kicad_dru").write_text(dru)
    info = dict(copper=COPPER, settings=SETTINGS, netclasses=CLASSES, nets={"A": {}, "B": {}})
    rb = C.rule_board(info, tmp_path / "board.kicad_pcb")
    assert rb.dru_rejected.startswith("board.kicad_dru:3:")
    assert not [r for r in rb.rules if r.source == "custom"]
    assert R.strictest(rb, "clearance", track("A"), track("B"), "F.Cu").min == 0.2   # net class, not 0.9
    r = kicad_file.read_rules(tmp_path / "board.kicad_pcb")
    assert r.custom == [] and r.dru_rejected == rb.dru_rejected
    assert "KiCad drops this rules file" in capsys.readouterr().err
    (tmp_path / "board.kicad_dru").write_text(dru.replace("clearence", "clearance").replace("0.1mm", "0.1mm) (max 1mm"))
    rb = C.rule_board(info, tmp_path / "board.kicad_pcb")
    assert not rb.dru_rejected and R.strictest(rb, "clearance", track("A"), track("B"), "F.Cu").min == 0.1


def test_a_negative_or_zero_override_is_no_override():
    """ubertooth U3's thermal vias carry a pad clearance of -0.099 mm: KiCad 10.0.7 requires the
    0.2 mm class clearance there (a track 0.131 mm away is a violation); flooring the override at
    the board minimum let the router come to the board minimum."""
    b = board()
    for v in (-0.09906, 0.0):
        c = R.evaluate(b, "clearance", track("A"), pad("B", override=v), "F.Cu")
        assert c.min == 0.2 and c.rule != "local override"
        assert R.evaluate(b, "hole_clearance", track("A"), pad("B", override=v, drilled=True), "F.Cu").rule != \
            "local override"


def test_the_coupled_diff_pair_gap_holds_between_tracks_not_pads():
    """KiCad 10.0.7 (aifryz sensor-hub): coupled tracks may sit at the pair gap, but a pad of one
    net keeps the class clearance from the other net's track."""
    cl = dict(CLASSES, Default=dict(CLASSES["Default"], dp_gap=0.09))
    b = R.build(COPPER, SETTINGS, cl, {"D_P", "D_N"})
    assert R.evaluate(b, "clearance", track("D_P"), track("D_N"), "F.Cu").min == 0.15     # the gap, at the board minimum
    assert R.evaluate(b, "clearance", track("D_P"), pad("D_N"), "F.Cu").min == 0.2
    assert R.evaluate(b, "clearance", pad("D_P"), track("D_N"), "F.Cu").min == 0.2
