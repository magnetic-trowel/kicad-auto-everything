# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Budgets in counted work instead of wall seconds.

On a shared host the same run with the same seeds and the same wall-clock budget left 13.9 % more
open connections a few days later (docs/research/benchmark-drift-2611.md): how much a stage gets
done in a second depends on the host's load. In work mode a run's budget is spent by the work its
stages count (annealer moves, solver deterministic time, router passes and rounds), so the same
budget buys the same work whatever the host is doing.

The unit stays the second: a nominal second is the work a stage does in one wall second on an idle
reference host (RATES, calibrated by tools/research/budget/calibrate.py), so budgets, defaults and
settings written in seconds keep their meaning.

Use: code that sets or checks a deadline calls `now()` instead of `time.monotonic()`; a stage that
does counted work calls `charge(kind, units)`. In time mode (the default) `now()` is
time.monotonic() and `charge` only counts, so swapping the calls in changes nothing.

Work mode: KAE_BUDGET=work (or `set_mode("work")`). `now()` is the charged nominal seconds and
nothing else, so a deadline means the same work on any host. Wall time enters only as a safety
ceiling (`set_ceiling`, CEILING_FACTOR x the run's budget): past it `now()` is infinite, every
deadline has passed, stages wind down, and the report says `ceiling_hit` (the run has failed: a
stage did work it did not charge). A stage that loops on a deadline must charge, or it ends only at
the ceiling.
"""
from __future__ import annotations

import math
import os
import threading
import time
from collections import defaultdict

# nominal seconds per unit of counted work, from an idle reference host (calibrate.py); a kind
# missing here is charged at 0 and counted only
RATES = {
    "anneal_move": 0.0,         # one proposed annealer move (set by calibration)
    "cpsat_dtime": 1.0,         # CP-SAT deterministic time unit (OR-tools' own ~1 s on a reference core)
    "seconds": 1.0,             # work already measured in nominal seconds by the caller
}
CEILING_FACTOR = 4.0    # a run past CEILING_FACTOR x its nominal budget in wall time has failed

_lock = threading.Lock()


class Clock:
    def __init__(self, mode=None, rates=None):
        self.mode = mode or os.environ.get("KAE_BUDGET", "time")
        if self.mode not in ("time", "work"):
            raise ValueError(f"KAE_BUDGET must be 'time' or 'work', not {self.mode!r}")
        self.rates = dict(RATES, **(rates or {}))
        self.t0 = time.monotonic()
        self.spent = 0.0                     # charged nominal seconds
        self.units = defaultdict(float)      # counted units per kind (both modes)
        self.by_kind = defaultdict(float)    # charged nominal seconds per kind
        self.ceiling = None                  # wall seconds after which now() is infinite (work mode)
        self.ceiling_hit = False

    def charge(self, kind, units=1.0):
        """Count `units` of `kind` work; in work mode they advance the clock at RATES[kind]."""
        s = units * self.rates.get(kind, 0.0)
        with _lock:
            self.units[kind] += units
            self.by_kind[kind] += s
            self.spent += s
        return s

    def wall(self):
        return time.monotonic() - self.t0

    def now(self):
        """time.monotonic() (time mode), or the charged nominal seconds (work mode; infinite past the
        wall ceiling). Only differences of now() mean anything, so every deadline in a process must
        come from now(), never from time.monotonic()."""
        if self.mode == "time":
            return time.monotonic()
        if self.ceiling is not None and self.wall() > self.ceiling:
            self.ceiling_hit = True
            return math.inf
        return self.spent

    def deadline(self, seconds):
        return self.now() + float(seconds)

    def left(self, deadline):
        n = self.now()
        return -1.0 if n == math.inf else deadline - n

    def report(self):
        w = self.wall()
        out = dict(mode=self.mode, wall_s=round(w, 2), charged_s=round(self.spent, 2),
                   units={k: round(v, 3) for k, v in self.units.items()},
                   charged_by_kind={k: round(v, 2) for k, v in self.by_kind.items()})
        if self.mode == "work":
            out.update(ceiling_s=self.ceiling, ceiling_hit=self.ceiling_hit)
        return out


_clock = None


def clock():
    """The process's clock (created on first use from KAE_BUDGET)."""
    global _clock
    if _clock is None:
        _clock = Clock()
    return _clock


def set_mode(mode, rates=None):
    """Start a fresh process clock in `mode` (CLIs, tests)."""
    global _clock
    _clock = Clock(mode, rates)
    return _clock


def set_ceiling(budget_s):
    """Fail the run (now() infinite) past CEILING_FACTOR x `budget_s` wall seconds from the clock's
    start; work mode only, no effect in time mode."""
    clock().ceiling = CEILING_FACTOR * float(budget_s)


def now():
    return clock().now()


def charge(kind, units=1.0):
    return clock().charge(kind, units)


def work_mode():
    return clock().mode == "work"


