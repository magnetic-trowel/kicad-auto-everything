# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The bridge's start rip-up cost on big boards (bridge.ripup_cost, fr-ripup-ab6)."""
from types import SimpleNamespace

from kae.route import bridge, constraints


def _plan(pins):
    return SimpleNamespace(edge_clearance=0.3, neck_width=None, min_width=None,
                           pin_class={("U1", str(i)): "c" for i in range(pins)})


def _opts(**kw):
    o = {**bridge.DEFAULT_OPTS, "ripup_cost_big": constraints.DEFAULTS["ripup_cost_big"],
         "ripup_big_pads": constraints.DEFAULTS["ripup_big_pads"]}
    o.update(kw)
    return o


def test_big_board_gets_the_dearer_ripup():
    s = bridge.router_settings(_plan(1001), _opts())
    assert s["scoring.start_ripup_costs"] == "200"
    assert bridge.router_settings(_plan(1001), _opts(), repair=True)["scoring.start_ripup_costs"] == "200"


def test_small_board_and_overrides_keep_freeroutings_default():
    assert "scoring.start_ripup_costs" not in bridge.router_settings(_plan(1000), _opts())
    assert "scoring.start_ripup_costs" not in bridge.router_settings(_plan(5000), _opts(ripup_cost_big=100))
    assert bridge.router_settings(_plan(600), _opts(ripup_big_pads=500))["scoring.start_ripup_costs"] == "200"


def test_last_mile_only_opts_keep_the_default():
    # last_mile_only does not resolve the setting: the A/B's final pass ran at Freerouting's default
    assert "scoring.start_ripup_costs" not in bridge.router_settings(_plan(5000), dict(bridge.DEFAULT_OPTS))
