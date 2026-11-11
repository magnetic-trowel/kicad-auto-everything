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
