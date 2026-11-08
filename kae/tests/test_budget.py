# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""kae.budget: time mode is the wall clock; work mode advances by charged work only, wall time only
past the safety ceiling, and reports what it counted."""
import time

import pytest

from kae import budget


def test_time_mode_is_the_wall_clock_and_only_counts():
    c = budget.Clock("time", rates={"x": 10.0})
    a = c.now()
    c.charge("x", 5)
    assert abs(c.now() - time.monotonic()) < 0.05 and c.now() - a < 1.0
    assert c.units["x"] == 5 and c.report()["charged_s"] == 50.0


def test_work_mode_advances_by_charged_work_only():
    c = budget.Clock("work", rates={"move": 1 / 64})
    d = c.deadline(1.0)
    n = 0
    while c.now() < d:
        c.charge("move")
        n += 1
    assert n == 64                       # exactly the counted work, whatever the host does
    assert c.report()["units"]["move"] == 64


def test_work_mode_ignores_wall_time_until_the_ceiling(monkeypatch):
    c = budget.Clock("work")
    t = [100.0]
    monkeypatch.setattr(budget.time, "monotonic", lambda: t[0])
    c.t0 = 100.0
    d = c.deadline(1.0)
    t[0] += 50.0                         # a slow host: nothing charged, no budget spent
    assert c.left(d) == 1.0
    c.ceiling = 60.0
    t[0] += 20.0                         # past the ceiling: every deadline has passed
    assert c.now() == float("inf") and c.left(d) < 0 and c.report()["ceiling_hit"]


def test_mode_from_environment(monkeypatch):
    monkeypatch.setenv("KAE_BUDGET", "work")
    assert budget.Clock().mode == "work"
    monkeypatch.setenv("KAE_BUDGET", "fast")
    with pytest.raises(ValueError):
        budget.Clock()
