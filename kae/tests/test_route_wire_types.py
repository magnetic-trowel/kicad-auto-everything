# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""translate.set_wire_types: the unlocked wiring Freerouting sees, and how much of a reservation survives."""
from types import SimpleNamespace

from kae.route import pair_route, specctra as S, translate


def tree():
    return ["pcb", "x", ["wiring",
                         ["wire", ["path", "F.Cu", "100", "0", "0", "100", "0"], ["net", "A"], ["type", "route"]],
                         ["wire", ["path", "F.Cu", "100", "0", "0", "100", "0"], ["net", "B"], ["type", "route"]],
                         ["wire", ["path", "F.Cu", "100", "0", "0", "100", "0"], ["net", "C"], ["type", "fix"]],
                         ["via", "V", "0", "0", ["net", "A"], ["type", "route"]]]]


def types(t):
    return [str(S.find(w, "type")[1]) for w in S.find(t, "wiring")[1:]]


def test_route_is_the_default_and_changes_nothing():
    t = tree()
    assert translate.set_wire_types(t, "route") == dict(wires=0, vias=0)
    assert t == tree()


def test_soft_types_touch_only_unlocked_wiring():
    t = tree()
    assert translate.set_wire_types(t, "shove_fixed") == dict(wires=2, vias=1)
    assert types(t) == ["shove_fixed", "shove_fixed", "fix", "shove_fixed"]


def test_scope_limits_to_the_named_nets():
    t = tree()
    assert translate.set_wire_types(t, "normal", nets={"A"}) == dict(wires=1, vias=1)
    assert types(t) == ["normal", "route", "fix", "normal"]


def test_unknown_type_is_refused():
    import pytest
    with pytest.raises(ValueError):
        translate.set_wire_types(tree(), "protect")


def test_copper_survival(tmp_path, monkeypatch):
    t = lambda net, a, b: SimpleNamespace(net=net, layer="F.Cu", start=a, end=b, locked=True)  # noqa: E731
    v = lambda net, x, y: SimpleNamespace(net=net, x=x, y=y, locked=True)                      # noqa: E731
    reserved = SimpleNamespace(tracks=[t("P", (0, 0), (10, 0)), t("N", (0, 1), (10, 1))], vias=[v("P", 0, 0)])
    routed = SimpleNamespace(tracks=[t("P", (0, 0), (10, 0)), t("N", (0, 5), (10, 5))], vias=[v("P", 0, 0)])
    monkeypatch.setattr(pair_route, "load", lambda p: reserved if "res" in str(p) else routed)
    out = pair_route.copper_survival(tmp_path / "res", tmp_path / "rt")
    assert (out["share"], out["kept_mm"], out["vias_kept"], out["vias"]) == (0.5, 10.0, 1, 1)
    assert out["nets"] == {"P": 1.0, "N": 0.0}
