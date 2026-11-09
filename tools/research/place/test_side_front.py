# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""choose_flips: passives first, smallest first, stops at the fill cap."""
from side_front import choose_flips


def part(key, area, passive, side="B", ok=True):
    return (key, area, passive, side, ok)


def test_passives_first_then_small():
    parts = [part("big", 40.0, False), part("mid", 10.0, True), part("small", 1.0, True), part("f", 10.0, False, side="F", ok=False)]
    # board 100 mm2, cap 0.70: front starts at 10; budget 60: small (1), mid (10) passive first, big (40) still fits
    flips, capped, before, after = choose_flips(parts, 100.0, "smd", 0.7)
    assert flips == ["small", "mid", "big"] and not capped
    assert abs(before - 0.1) < 1e-9 and abs(after - 0.61) < 1e-9


def test_cap_skips_part_that_does_not_fit():
    parts = [part("a", 30.0, True), part("b", 25.0, True), part("c", 20.0, False)]
    flips, capped, _, _ = choose_flips(parts, 100.0, "smd", 0.5)
    # budget 50: b (25, smaller passive), a (30) no, c (20) no: passives ordered by area
    assert flips == ["b", "c"] and capped == ["a"]


def test_passives_arm_never_flips_an_ic():
    parts = [part("r", 1.0, True), part("ic", 1.0, False)]
    assert choose_flips(parts, 100.0, "passives", 0.9)[0] == ["r"]


def test_only_flippable_parts_are_candidates():
    parts = [part("locked", 1.0, True, ok=False), part("r", 1.0, True)]
    assert choose_flips(parts, 100.0, "smd", 0.9)[0] == ["r"]
