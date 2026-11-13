# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Power copper's neck at plated through-hole pads (power_copper.neck_rule tht=True): grown copper
within neck_len of a soldered THT pad stays at the routed track's width or the width the pad's
current needs; exceptions (tht_wide, unsoldered parts, hot parts, pads joined to a zone); the
tht_pad_necked decision entry and the tht_pad_heatsunk hazard. Runs without KiCad (synthetic
export info, no fills)."""
import json

import pytest
from shapely.geometry import LineString, Point, box

import critical_fixtures as F
from kae.route import power_copper as pc

J1_1 = (104.0, 111.0)     # J1 pad 1 (VIN), a 1.4 mm through-hole pad, 0.8 mm drill


# ----------------------------------------------------------------------------- the pure rule
def test_neck_rule_tht():
    # no current: the floor; the routed track (never narrowed) is the real width
    assert pc.neck_rule(1.7, "reflow", 0.0, tht=True) == pytest.approx(pc.THT_NECK_MIN)
    # a current: the width it needs, in any process
    need = pc.current_need(0.3)
    for proc in ("reflow", "wave", "hand"):
        assert pc.neck_rule(1.7, proc, 0.3, tht=True) == pytest.approx(need)
    # the current needs more than a relief's webs (60 % of the land): no neck
    assert pc.current_need(3.0) > 0.6 * 1.7
    assert pc.neck_rule(1.7, "reflow", 3.0, tht=True) is None
    assert pc.neck_rule(1.7, "reflow", 0.0) == pytest.approx(1.7)        # the SMD rule is unchanged


def test_land_necks_tht_shares_the_smd_rule():
    lands = {"J1": [("j1", False, "VIN", 1.7), ("j2", False, "GND", 1.7)],
             "C1": [("c1", True, "VIN", 0.6), ("c2", True, "GND", 0.6)]}
    necks0, series0 = pc.land_necks(lands, {"VIN"}, {"GND"}, {"VIN": 0.3}, "reflow")
    assert set(necks0) == {"c1", "c2"}                           # without tht_current: the SMD rule alone
    necks, series = pc.land_necks(lands, {"VIN"}, {"GND"}, {"VIN": 0.3}, "reflow",
                                  tht_current={"j1": 0.3, "j2": 3.0})
    assert necks["c1"] == necks0["c1"] and necks["c2"] == necks0["c2"]
    assert necks["j1"] == pytest.approx(pc.current_need(0.3))
    assert "j2" not in necks and series["j2"] == 3.0             # needs more than a relief: no neck


def test_exemptions_and_settings(monkeypatch):
    wide = pc.tht_wide_set("J1, J3.2;K4")
    assert wide == {"J1", "J3.2", "K4"} and pc.tht_wide_set(["J9"]) == {"J9"} and pc.tht_wide_set("") == set()
    ex = pc.tht_exempt
    assert ex("J1", "1", "connector", (), set(), False, wide) == "tht_wide"
    assert ex("J3", "2", "connector", (), set(), False, wide) == "tht_wide"
    assert ex("J3", "1", "connector", (), set(), False, wide) is None
    assert ex("H1", "1", "mounting_hole", (), set(), False, set()) == "unsoldered"
    assert ex("X1", "1", None, ("board_only",), set(), False, set()) == "unsoldered"
    assert ex("Q1", "2", "transistor", (), {"Q1"}, False, set()) == "hot"
    assert ex("J2", "1", "connector", (), set(), True, set()) == "zone"
    from kae.route import constraints as CN
    assert CN.setting_env("tht_neck") == "on" and CN.setting_env("tht_wide") == ""
    monkeypatch.setenv("KAE_THT_NECK", "off")
    assert CN.setting_env("tht_neck") == "off"
    monkeypatch.setenv("KAE_THT_NECK", "on")
    assert CN.setting_env("tht_neck", opts=dict(tht_neck="off")) == "off"   # opts win over env


# ----------------------------------------------------------------------------- on a board
SEG = '\t(segment\n\t\t(start {} {})\n\t\t(end {} {})\n\t\t(width 0.25)\n\t\t(layer "F.Cu")\n\t\t(net "{}")\n\t\t(uuid "{}")\n\t)\n'


def _board(tmp_path, text_vars=None, passing=False):
    """The critical fixture with a 0.25 mm VIN track from J1 pad 1 (a THT connector pad) east to U1's VIN
    pin, with free room on both sides for power copper to grow; `passing`: also a GND track that runs past
    J1 pad 2 (GND) without ending in it."""
    from kae.board.kicad_file import load
    p = F.write_board(tmp_path)
    s = p.read_text()
    i = s.rindex("\t(embedded_fonts no)")
    seg = SEG.format(*J1_1, 114, 111, "VIN", "0000000a-0000-0000-0000-00000000aaaa")
    seg += SEG.format(114, 111, 119.69, 110.95, "VIN", "0000000a-0000-0000-0000-00000000aaab")
    if passing:
        seg += SEG.format(101.5, 114.6, 110, 114.6, "GND", "0000000a-0000-0000-0000-00000000aaac")
    s = s[:i] + seg + s[i:]
    p.write_text(s)
    if text_vars:
        pro = json.loads(p.with_suffix(".kicad_pro").read_text())
        pro.setdefault("text_variables", {}).update(text_vars)
        p.with_suffix(".kicad_pro").write_text(json.dumps(pro))
    return p, load(p)


def _pc(tmp_path, text_vars=None, operating=None, passing=False, **opts):
    p, b = _board(tmp_path, text_vars, passing)
    if operating is not None:
        op = tmp_path / "op.json"
        op.write_text(json.dumps(operating))
        opts["operating"] = str(op)
    obj = pc.PowerCopper(p, dict(opts, vias=False, stitch=False), info=F.synth_info(b), fills={}, log=lambda *a: None)
    obj.widen()
    return obj


def _width_near(obj, xy, r, net="VIN"):
    """Widest planned piece of the net's tracks within r of the point."""
    nets = {t.uuid: t.net for t in obj.board.tracks}
    ws = [w for u, pieces in obj.edits.items() if nets.get(u) == net for a, b, w, *_ in pieces
          if LineString([a, b]).distance(Point(xy)) < r]
    return max(ws, default=0.25)


@pytest.fixture
def plan(monkeypatch):
    """Set the DC plan's injections power copper sees (kae.excite.dc.planned_injections)."""
    from kae.excite import dc
    box_ = {}
    monkeypatch.setattr(dc, "planned_injections", lambda *a, **k: dict(box_))

    def set_(inj):
        box_.clear()
        box_.update(inj)
    return set_


def test_tht_pad_necked_by_default_with_a_decision_entry(tmp_path, plan):
    plan({"J1.1": 0.05, "U1.3": -0.05})
    obj = _pc(tmp_path)
    assert "VIN" in obj.power
    assert obj.tht_stats()["necked_pads"] >= 1
    pad_r = 0.7                                                  # J1.1's half size
    assert _width_near(obj, J1_1, pad_r + obj.o["neck_len"] - 0.05) == pytest.approx(0.25)   # the routed width
    assert _width_near(obj, (112.0, 111.0), 0.1) > 0.25 + 1e-6                              # wide further out
    hz = [h for h in obj.tht_hazards() if h["code"] == "tht_pad_necked"]
    assert len(hz) == 1
    h = hz[0]
    assert h["severity"] == "info" and h["category"] == "assembly"
    assert h["objects"][:2] == ["J1", "J1.1"]
    e = h["evidence"]["pads"][0]
    assert e["pad"] == "J1.1" and e["net"] == "VIN" and e["got_w_mm"] == pytest.approx(0.25)
    assert e["would_w_mm"] > e["got_w_mm"] and e["current_a"] == pytest.approx(0.05)
    assert "KAE_THT_WIDE" in h["fix"] and "'J1'" in h["fix"] and "'J1.1'" in h["fix"]


@pytest.mark.parametrize("how", ["text_var", "opts", "pad", "off"])
def test_tht_wide_keeps_the_width(tmp_path, how, plan):
    plan({"J1.1": 0.05, "U1.3": -0.05})
    tv, opts = None, {}
    if how == "text_var":
        tv = {"KAE_THT_WIDE": "J1"}
    elif how == "opts":
        opts = dict(tht_wide=["J1"])
    elif how == "pad":
        tv = {"KAE_THT_WIDE": "J1.1"}
    else:
        tv = {"KAE_THT_NECK": "off"}
    obj = _pc(tmp_path, tv, **opts)
    assert obj.tht_stats()["necked_pads"] == (1 if how == "pad" else 0)     # "J1.1": J1.2 (GND) stays necked
    assert _width_near(obj, J1_1, 0.7 + obj.o["neck_len"] - 0.05) > 0.25 + 1e-6
    assert not [h for h in obj.tht_hazards() if h["code"].startswith("tht_")]


def test_tht_neck_env_default(tmp_path, monkeypatch, plan):
    plan({"J1.1": 0.05, "U1.3": -0.05})
    monkeypatch.setenv("KAE_THT_NECK", "off")
    obj = _pc(tmp_path)
    assert obj.tht_stats()["skipped"].get("off", 0) >= 1 and obj.tht_stats()["necked_pads"] == 0


def test_tht_current_widens_the_neck_or_keeps_the_width_with_a_hazard(tmp_path, plan):
    # the DC plan: J1 feeds VIN, U1 draws it; the track into J1.1 carries all of it
    plan({"J1.1": 0.6, "U1.3": -0.6})
    small = _pc(tmp_path / "a")
    assert small.tht_amps and max(small.tht_amps.values()) == pytest.approx(0.6, rel=1e-3)
    need = pc.current_need(0.6)
    assert need > 0.25
    w = _width_near(small, J1_1, 0.7 + small.o["neck_len"] - 0.05)
    assert 0.25 < w <= need + 1e-6
    plan({"J1.1": 3.0, "U1.3": -3.0})
    big = _pc(tmp_path / "b")
    assert big.tht_stats()["unnecked_for_current"] >= 1
    hz = [h for h in big.tht_hazards() if h["code"] == "tht_pad_heatsunk"]
    assert len(hz) == 1 and hz[0]["severity"] == "warn" and hz[0]["category"] == "assembly"
    assert hz[0]["objects"][0] == "J1.1" and hz[0]["evidence"]["track_w_mm"] > hz[0]["evidence"]["relief_w_mm"]
    assert not [h for h in big.tht_hazards() if h["code"] == "tht_pad_necked"]
    # a rail written as a pour (zone_above_a) joins the pad solid: the same hazard
    big.edits = {}
    assert not [h for h in big.tht_hazards() if h["code"] == "tht_pad_heatsunk"]
    big.zones = [("VIN", "F.Cu", box(103, 109.5, 108, 112.5), "z1")]
    hz = [h for h in big.tht_hazards() if h["code"] == "tht_pad_heatsunk"]
    assert len(hz) == 1 and hz[0]["evidence"]["track_w_mm"] == pytest.approx(3.0)


def test_hot_part_and_zone_joined_pads_are_left_alone(tmp_path, plan):
    plan({"J1.1": 0.05, "U1.3": -0.05})
    hot = _pc(tmp_path / "a", operating={"parts": {"J1": {"P_sustained_W": 1.0}}})
    assert hot.tht_stats()["skipped"].get("hot", 0) >= 1 and hot.tht_stats()["necked_pads"] == 0
    p, b = _board(tmp_path / "b")
    z = pc.PowerCopper(p, dict(vias=False, stitch=False), info=F.synth_info(b),
                       fills={"VIN": {"B.Cu": [box(103, 110, 106, 112)]}}, log=lambda *a: None)
    assert z.tht_stats()["skipped"] == {"zone": 1} and z.tht_stats()["necked_pads"] == 1     # J1.2 (GND) has no fill


def test_decision_entries_capped_per_code(tmp_path, plan):
    plan({"J1.1": 0.05, "U1.3": -0.05})
    obj = _pc(tmp_path)
    rec = next(iter(obj.tht_necked.values()))
    from kae import hazards as H

    class P:
        def __init__(self, k):
            self.owner, self.net, self.geom = (f"J{k}", "1"), "VIN", rec["pad"].geom
    obj.tht_necked = {k: dict(pad=P(k), would=1.0 + k / 100, got=0.25, layers={"F.Cu"}) for k in range(20)}
    hz = [h for h in obj.tht_hazards() if h["code"] == "tht_pad_necked"]
    assert len(hz) == H.MAX_PER_CODE
    assert hz[-1]["evidence"]["parts"] == 20 - (H.MAX_PER_CODE - 1)
    rep = H.finalize(dict(hazards=hz))
    assert len(rep["hazards"]) == H.MAX_PER_CODE and not rep["hazard_summary"].get("omitted")


def test_decision_reaches_the_pass_report_and_the_portfolio(tmp_path, monkeypatch, plan):
    """power_copper.run (finish's "power" part, no gate) returns the entries in its hazards, finish
    adds every part's hazards to its report, and the portfolio carries a kept finish's hazards into
    the kept board's report (kae.route.cli's, which finalize caps)."""
    from kae.board import pcbnew_io
    from kae.route import critical_recheck, portfolio
    plan({"J1.1": 0.05, "U1.3": -0.05})
    p, b = _board(tmp_path)
    monkeypatch.setattr(pcbnew_io, "export_dsn", lambda *a, **k: F.synth_info(b))
    monkeypatch.setattr(critical_recheck, "fills_of", lambda *a, **k: {})
    (tmp_path / "out").mkdir()
    rep = pc.run(p, tmp_path / "out" / "board.kicad_pcb", opts=dict(vias=False, stitch=False),
                 workdir=tmp_path / "w", log=lambda *a: None, gate=False)
    codes = [h["code"] for h in rep["hazards"]]
    assert "tht_pad_necked" in codes and rep["tht"]["necked_pads"] >= 1
    rec = dict(kept=True, own_hazards=rep["hazards"])
    assert any(h["code"] == "tht_pad_necked" for h in portfolio.finish_hazards(rec))


def test_theta_marks_a_part_hot(tmp_path, plan):
    plan({"J1.1": 0.05, "U1.3": -0.05})
    obj = _pc(tmp_path, operating={"parts": {"J1": {"theta_jb_C_W": 5.3}}})
    assert obj.tht_stats()["skipped"].get("hot", 0) == 2 and obj.tht_stats()["necked_pads"] == 0


def test_without_a_dc_plan_connector_pins_stay_wide_with_a_decision_entry(tmp_path, plan):
    plan({})
    obj = _pc(tmp_path / "a")
    assert obj.tht_stats()["skipped"].get("no_current") == 2 and obj.tht_stats()["necked_pads"] == 0
    assert _width_near(obj, J1_1, 0.7 + obj.o["neck_len"] - 0.05) > 0.25 + 1e-6
    hz = [h for h in obj.tht_hazards() if h["code"] == "tht_pad_kept_wide"]
    assert len(hz) == 1 and hz[0]["severity"] == "info" and hz[0]["category"] == "assembly"
    assert hz[0]["objects"][0] == "J1" and "KAE_THT_NARROW" in hz[0]["fix"]
    # the commanding LLM necks them anyway
    obj = _pc(tmp_path / "b", {"KAE_THT_NARROW": "J1"})
    assert obj.tht_stats()["necked_pads"] == 2
    assert _width_near(obj, J1_1, 0.7 + obj.o["neck_len"] - 0.05) == pytest.approx(0.25)
    assert not [h for h in obj.tht_hazards() if h["code"] == "tht_pad_kept_wide"]


def test_branch_currents_through_a_chain():
    """A rail through three pads in a row: the track into the first carries all three loads."""
    from shapely.geometry import box as B_
    from types import SimpleNamespace as N

    def t(a, b):
        return N(net="V", layer="F.Cu", width=0.5, start=a, end=b)
    pads = [(f"J{i}.1", B_(10 * i - 0.5, -0.5, 10 * i + 0.5, 0.5), ["F.Cu"]) for i in range(4)]
    tracks = [t((10 * i, 0), (10 * i + 10, 0)) for i in range(3)]
    inj = {"J0.1": 0.6, "J1.1": -0.2, "J2.1": -0.2, "J3.1": -0.2}
    out = pc.branch_currents("V", tracks, [], pads, {}, inj)
    assert out["J0.1"] == pytest.approx(0.6, rel=1e-6) and out["J1.1"] == pytest.approx(0.6, rel=1e-6)
    assert out["J2.1"] == pytest.approx(0.4, rel=1e-6) and out["J3.1"] == pytest.approx(0.2, rel=1e-6)


def test_passing_copper_is_not_necked(tmp_path, plan):
    """A GND track that runs past J1.2 (GND) without ending in it widens there, keeping tht_gap off the pad;
    the old rule held it at its routed width within neck_len."""
    plan({"J1.1": 0.05, "U1.3": -0.05})
    obj = _pc(tmp_path, passing=True)
    from kae.route import power_copper as P
    j12 = next(p for p in obj.sp.pads if p.owner == ("J1", "2") and id(p) in obj.tht_necks)
    w = _width_near(obj, (104.0, 114.6), 0.05, net="GND")
    assert w > 0.25 + 1e-6
    # its copper keeps the gap: the widest piece there stays tht_gap off the pad
    nets = {t.uuid: t.net for t in obj.board.tracks}
    for u, pieces in obj.edits.items():
        if nets.get(u) != "GND":
            continue
        for a, b, wd, *_ in pieces:
            if wd > 0.25 + 1e-6:
                assert LineString([a, b]).buffer(wd / 2).distance(j12.geom) >= P.DEFAULTS["tht_gap"] - 0.01
