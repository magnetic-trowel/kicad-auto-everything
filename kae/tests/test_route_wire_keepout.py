# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""A rule area that forbids tracks but allows vias: tracks stop at it, vias pass."""
from shapely.geometry import box

from kae.route.critical_space import Item, Space


def need(it, kind):
    return Space.need(None, it, "A", kind, "In2.Cu")


def test_tracks_only_keepout_lets_vias_through():
    it = Item("keepout", None, ["In2.Cu"], box(0, 0, 1, 1), tracks_only=True)
    assert need(it, "track") == 0.0
    assert need(it, "via") is None


def test_plain_and_via_only_keepouts_unchanged():
    assert need(Item("keepout", None, ["In2.Cu"], box(0, 0, 1, 1)), "via") == 0.0
    assert need(Item("keepout", None, ["In2.Cu"], box(0, 0, 1, 1), vias_only=True), "track") is None
