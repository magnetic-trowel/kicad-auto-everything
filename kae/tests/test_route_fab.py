# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""kae.route.fab: fab classes clip and label suggested relaxations."""
import pytest

from kae.route import fab


def test_cheapest_class_and_floor_follow_the_layer_count():
    j = fab.profile("jlcpcb")
    assert fab.cheapest(j, 4, "track", 0.09) == "standard" and fab.cheapest(j, 2, "track", 0.09) is None
    assert fab.cheapest(j, 4, "track", 0.08) == "advanced" and fab.cheapest(j, 4, "track", 0.07) == "hdi"
    assert fab.cheapest(j, 4, "track", 0.05) is None
    assert fab.floor(j, 4, "track") == 0.069 and fab.floor(j, 2, "track") == 0.10
    assert fab.cheapest(j, 4, "via", (0.45, 0.2)) == "standard" and fab.cheapest(j, 4, "via", (0.3, 0.2)) == "advanced"
    assert fab.cheapest(j, 4, "via", (0.45, 0.15)) == "advanced"
    # JLCPCB fills and caps vias in pads at no charge from 6 layers
    assert fab.cheapest(j, 6, "via_in_pad", True) == "standard" and fab.cheapest(j, 4, "via_in_pad", True) == "advanced"
    o = fab.profile("oshpark")
    assert fab.cheapest(o, 2, "via_in_pad", True) is None and fab.floor(o, 4, "space") == 0.127


def test_hazard_only_beyond_standard():
    j = fab.profile("jlcpcb")
    e = dict(rule="track width", value=0.09, **fab.label(j, 4, "track", 0.09))
    assert fab.hazard(j, 4, e, ["U1"], "U1") is None
    e = dict(rule="track width", value=0.076, **fab.label(j, 4, "track", 0.076))
    h = fab.hazard(j, 4, e, ["U1"], "U1 escape")
    assert h["severity"] == "warn" and h["category"] == "manufacturing" and "advanced" in h["message"]
    assert h["evidence"]["standard_limit"] == 0.09 and "surcharge" in h["message"]


def test_profile_selection_and_overrides():
    assert fab.profile(opts={})["key"] == "jlcpcb"
    assert fab.profile(opts=dict(fab="PCBWay"))["name"] == "PCBWay"
    mine = dict(name="Mine", multilayer=dict(standard=dict(track=0.05, space=0.05, pad_track=0.05, via=(0.2, 0.1))))
    assert fab.profile(opts=dict(fab="mine", fab_profiles=dict(mine=mine)))["name"] == "Mine"
    with pytest.raises(KeyError):
        fab.profile("nofab")
