# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""kae.route.pairs: which nets are a pair, whether it matters, and what the copper shows."""
from types import SimpleNamespace

from kae.board.model import NetClass, Net, Rules, Track, Via
from kae.route import pairs as P


def board(tracks=(), vias=(), custom=(), classes=None, nets=("/USB_D+", "/USB_D-", "/BAT+", "/BAT-", "/SCL"), netclass=None):
    netclass = netclass or {}
    rules = Rules(netclasses=classes or {"Default": NetClass(name="Default", diff_pair_width=0.2, diff_pair_gap=0.25)},
                  custom=list(custom))
    return SimpleNamespace(nets={n: Net(name=n, netclass=netclass.get(n, "Default")) for n in nets},
                           tracks=list(tracks), vias=list(vias), rules=rules, footprints=[])


def track(net, x0, y0, x1, y1, w=0.2, layer="F.Cu"):
    return Track(uuid=f"{net}{x0}{y0}", net=net, layer=layer, width=w, start=(x0, y0), end=(x1, y1))


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


def test_measure_coupled_parallel_tracks():
    b = board(tracks=[track("/USB_D+", 0, 0, 20, 0), track("/USB_D-", 0, 0.45, 20, 0.45)], vias=[])
    m = P.measure(b, P.Pair(p="/USB_D+", n="/USB_D-"))
    assert m["routed"] and m["skew"] == 0.0 and m["coupled_share"] == 1.0 and m["vias_p"] == 0


def test_measure_uncoupled_and_skew():
    b = board(tracks=[track("/USB_D+", 0, 0, 20, 0), track("/USB_D-", 0, 5, 25, 5)],
              vias=[Via(uuid="v", net="/USB_D+", x=20, y=0, size=0.6, drill=0.3, layers=["F.Cu", "B.Cu"])])
    m = P.measure(b, P.Pair(p="/USB_D+", n="/USB_D-"))
    assert m["skew"] == 5.0 and m["coupled_share"] == 0.0 and m["vias_p"] == 1 and m["vias_n"] == 0


def test_hazard_only_for_pairs_that_matter():
    b = board(tracks=[track("/USB_D+", 0, 0, 20, 0), track("/USB_D-", 0, 5, 25, 5),
                      track("/BAT+", 0, 9, 30, 9), track("/BAT-", 0, 12, 30, 12)])
    assert P.hazards(b) == []
    brief = dict(diff_pairs=[dict(p="/USB_D+", n="/USB_D-", interface="usb2", speed="hs", confidence=0.9)])
    hz = P.hazards(b, brief=brief)
    assert [h["code"] for h in hz] == ["pair_uncoupled", "pair_skew"]
    assert "/USB_D+//USB_D-" in hz[0]["objects"][0]


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
