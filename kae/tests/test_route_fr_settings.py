# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Freerouting settings passed through the bridge options, for setting experiments."""
from types import SimpleNamespace

from kae.route import bridge


PLAN = SimpleNamespace(edge_clearance=0.5, neck_width=0.2, min_width=0.15)


def test_no_overrides_by_default():
    s = bridge.router_settings(PLAN, dict(seed=0))
    assert s["fanout.enabled"] == "false" and not any("scoring" in k for k in s)
    assert bridge.fr_overrides(dict(seed=3)) == {}


def test_fr_keys_become_settings_and_booleans_are_lower_case():
    s = bridge.router_settings(PLAN, {"fr.scoring.via_costs": 25, "fr.autorouter.start_necked": False, "seed": 0})
    assert s["scoring.via_costs"] == "25" and s["autorouter.start_necked"] == "false"


def test_cycle_picks_one_preset_per_attempt():
    cycle = "scoring.via_costs=25;scoring.via_costs=100,scoring.start_ripup_costs=50"
    assert bridge.fr_overrides(dict(fr_cycle=cycle, seed=0)) == {"scoring.via_costs": "25"}
    assert bridge.fr_overrides(dict(fr_cycle=cycle, seed=1)) == {"scoring.via_costs": "100", "scoring.start_ripup_costs": "50"}
    assert bridge.fr_overrides(dict(fr_cycle=cycle, seed=2)) == {"scoring.via_costs": "25"}
