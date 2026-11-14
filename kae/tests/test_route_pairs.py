# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""kae.route.pairs: which nets are a pair, whether it matters, and the hazard from the bus scorecard's pair rows."""
from types import SimpleNamespace

from kae.board.model import NetClass, Net, Rules
from kae.route import pairs as P


def board(tracks=(), vias=(), custom=(), classes=None, nets=("/USB_D+", "/USB_D-", "/BAT+", "/BAT-", "/SCL"), netclass=None):
    netclass = netclass or {}
    rules = Rules(netclasses=classes or {"Default": NetClass(name="Default", diff_pair_width=0.2, diff_pair_gap=0.25)},
                  custom=list(custom))
    return SimpleNamespace(nets={n: Net(name=n, netclass=netclass.get(n, "Default")) for n in nets},
                           tracks=list(tracks), vias=list(vias), rules=rules, footprints=[])


def test_detect_finds_kicad_pairs_and_ranks_them():
    ps = P.detect(board(), brief=dict(diff_pairs=[dict(p="/USB_D+", n="/USB_D-", interface="usb2", speed="hs", confidence=0.9)]))
    tiers = {p.p.strip("/"): p.tier for p in ps}
    assert tiers == {"BAT+": "name", "USB_D+": "interface"}
    assert all(p.kicad for p in ps)


def test_class_with_its_own_pair_rule_is_rule_tier():
    classes = {"Default": NetClass(name="Default", diff_pair_width=0.2, diff_pair_gap=0.25),
               "HS": NetClass(name="HS", diff_pair_width=0.17, diff_pair_gap=0.15)}
    b = board(classes=classes, netclass={"/BAT+": "HS", "/BAT-": "HS"})
    assert [p.tier for p in P.detect(b) if p.p.endswith("BAT+")] == ["rule"]


def test_custom_rule_is_rule_tier():
    custom = [dict(name="dp", condition="A.inDiffPair('*')", constraints=[dict(type="diff_pair_gap", min=0.15)])]
    tiers = {p.tier for p in P.detect(board(custom=custom))}
    assert tiers == {"rule"}


def test_hazard_entries_only_for_measured_pairs_that_matter():
    row = lambda p, tier, cpl, skew, lim: dict(p=p, n=p[:-1] + "-", tier=tier, coupled_3w=cpl, skew_mm=skew, len_mean=20.0,  # noqa: E731
                                              limit=dict(skew_mm=lim, source="test"))
    rows = [row("/USB_D+", "interface", 0.1, 3.0, 1.27), row("/BAT+", "name", 0.0, 9.0, None),
            row("/TX+", "rule", 0.9, 0.05, 0.127), dict(p="/RX+", n="/RX-", tier="rule", coupled_3w=None)]
    hz = P.hazard_entries(rows)
    assert [h["code"] for h in hz] == ["pair_uncoupled", "pair_skew"]
    assert hz[0]["objects"] == ["/USB_D+//USB_D-"] and hz[1]["objects"] == ["/USB_D+//USB_D-"]
    assert P.hazard_entries([row("/TX+", "rule", 0.9, 0.05, 0.127)]) == []


def _usb_board(gap):
    """Two connectors 20 mm apart joined by D+/D-, the D- leg `gap` from D+ (centre to centre) along its run."""
    from test_bus import CONN, fp, mk_board, tr
    j = fp("J1", CONN, [(0.0, 0.0), (0.0, 0.65), (0.0, 3.0)], ["/USB_D+", "/USB_D-", "/ID"])     # a terminal: 3 signal pins
    u = fp("J2", CONN, [(20.0, 0.0), (20.0, 0.65), (20.0, 3.0)], ["/USB_D+", "/USB_D-", "/ID"])
    b = mk_board([j, u])
    b.tracks += tr("/USB_D+", (0.0, 0.0), (20.0, 0.0))
    b.tracks += tr("/USB_D-", (0.0, 0.65), (0.0, gap), (20.0, gap), (20.0, 0.65))
    return b


def test_scorecard_pair_rows_carry_tier_and_feed_the_hazard():
    from kae.bus.scorecard import board_scorecard
    near, far = _usb_board(0.45), _usb_board(6.0)
    rows = P.report(near, board_scorecard(near))
    assert rows and rows[0]["p"] in ("/USB_D+", "/USB_D-") and rows[0]["tier"] == "interface"
    assert rows[0]["coupled_3w"] > 0.5 and "no_ref_mm" in rows[0]
    assert [h["code"] for h in P.hazards(near)] == []
    assert "pair_uncoupled" in [h["code"] for h in P.hazards(far)]


def test_scorecard_tier_sees_a_pair_class_with_no_interface():
    from kae.board.model import NetClass, Rules
    from kae.bus.scorecard import board_scorecard
    from test_bus import CONN, fp, mk_board, tr
    nets = ["/SIG_P", "/SIG_N", "/X"]
    b = mk_board([fp("J1", CONN, [(0.0, 0.0), (0.0, 0.65), (0.0, 3.0)], nets), fp("J2", CONN, [(20.0, 0.0), (20.0, 0.65), (20.0, 3.0)], nets)])
    b.rules = Rules(netclasses={"Default": NetClass(name="Default", diff_pair_width=0.2, diff_pair_gap=0.25),
                                "HS": NetClass(name="HS", diff_pair_width=0.12, diff_pair_gap=0.12)})
    for n in ("/SIG_P", "/SIG_N"):
        b.nets[n].netclass = "HS"
    b.tracks += tr("/SIG_P", (0.0, 0.0), (20.0, 0.0)) + tr("/SIG_N", (0.0, 0.65), (20.0, 0.65))
    rows = [r for r in board_scorecard(b)["pairs"] if r.get("p") in ("/SIG_P", "/SIG_N")]
    assert rows and rows[0]["tier"] == "rule"


def test_offset_polyline_right_angle_is_mitred():
    from kae.route.pair_route import offset_polyline
    pts = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0)]
    left = offset_polyline(pts, 0.5)
    assert left[0] == (0.0, 0.5) and left[-1] == (9.5, 10.0)
    assert abs(left[1][0] - 9.5) < 1e-9 and abs(left[1][1] - 0.5) < 1e-9     # mitre corner
    right = offset_polyline(pts, -0.5)
    assert abs(right[1][0] - 10.5) < 1e-9 and abs(right[1][1] + 0.5) < 1e-9


def test_cut_and_empty_ends():
    from kae.route.pair_route import _cut, _with_empty_ends
    assert _cut([(0.0, 0.0), (10.0, 0.0)], 2.0, end=False)[0] == (2.0, 0.0)
    assert _cut([(0.0, 0.0), (10.0, 0.0)], 2.0, end=True)[-1] == (8.0, 0.0)
    runs = [("B.Cu", [(0.0, 0.0), (5.0, 0.0)]), ("F.Cu", [(5.0, 0.0), (9.0, 0.0)])]
    vias = [(0.0, 0.0), (5.0, 0.0)]                  # the route changed layer on its first cell
    out = _with_empty_ends(runs, vias, ["F.Cu"], ["F.Cu"])
    assert [l for l, _ in out] == ["F.Cu", "B.Cu", "F.Cu"] and len(out[0][1]) == 1


def test_bump_adds_the_length_asked():
    import math
    from kae.route.pair_route import _bump, bump_gain
    pts = _bump((0.0, 0.0), (10.0, 0.0), 0.5, side=1.0)
    L = sum(math.dist(a, b) for a, b in zip(pts[:-1], pts[1:]))
    assert abs((L - 10.0) - bump_gain(0.5)) < 1e-9
    assert max(p[1] for p in pts) == 0.5 and min(p[1] for p in pts) == 0.0
