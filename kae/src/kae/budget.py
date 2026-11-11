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
stage did work it did not charge). Every deadline check charges a small fixed amount ("poll"), so a loop that
only polls still ends, after a counted number of checks.
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
    # calibrated with tools/research/budget/calibrate.py on three boards (65-328 pins; quiet host, 2026-11-08)
    "poll": 1e-3,               # one deadline check; a loop that only polls still ends after a counted number
                                # of checks. Kept below its measured 19 ms, which is mostly fixed overhead
                                # (loading the board) that a budget does not scale
    "exact": 5e-3,              # one deadline check in the exact-repair loops (a candidate's polygon checks)
    "anneal_move": 1.74e-5,     # one compiled annealer move
    "anneal_move_py": 1.36e-4,  # one Python-priced annealer move (physics terms, macros)
    "cpsat_dtime": 4.0,         # one unit of CP-SAT deterministic time (measured 3.8-4.5 s)
    "fr_pass_pin2": 9e-5,       # one Freerouting pass, per pin^2 of the board (7-9.8e-5 over the three boards;
                                # per MB of .dsn it varied 9x, and the largest board had a smaller .dsn)
    "drc_mb": 4.27,             # one KiCad DRC (with zone refill) per MB of board file
    "lastmile_try": 0.054,      # one last-mile path search (exact grid, one connection)
    # the critical-copper grid router (kae.route.critical_grid; the joint module stage, kae.route.critical),
    # calibrated 2026-11-11 on three boards (178-814 pads, 6 module-stage runs in time mode; shared host, so less
    # exact than the above). Before it was charged, a module stage in work mode cost no budget at all
    "crit_search": 0.10,        # one search with the work since the last clock event (module setup, its physics;
                                # 0.08-0.17 s, the larger boards dearer)
    "crit_expansion": 7.9e-7,   # one A* expansion of that search (3.6e-7 - 1.1e-6 s)
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
        self.profile = bool(os.environ.get("KAE_BUDGET_PROFILE"))    # calibration: wall time per kind
        self.wall_by_kind = defaultdict(float)
        self.last = self.t0
        self.ceiling = None                  # wall seconds after which now() is infinite (work mode)
        self.ceiling_hit = False

    def charge(self, kind, units=1.0):
        """Count `units` of `kind` work; in work mode they advance the clock at RATES[kind]."""
        s = units * self.rates.get(kind, 0.0)
        with _lock:
            if self.profile:                 # the time since the previous clock event went to this work
                t = time.monotonic()
                self.wall_by_kind[kind] += t - self.last
                self.last = t
            self.units[kind] += units
            self.by_kind[kind] += s
            self.spent += s
        return s

    def wall(self):
        return time.monotonic() - self.t0

    def now(self, kind="poll"):
        """time.monotonic() (time mode), or the charged nominal seconds (work mode; infinite past the
        wall ceiling), after charging one `kind` check. Only differences of now() mean anything, so
        every deadline in a process must come from now(), never from time.monotonic()."""
        if self.mode == "time":
            if self.profile:
                self.charge(kind)
            return time.monotonic()
        self.charge(kind)
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
        if self.profile:
            out["wall_by_kind"] = {k: round(v, 3) for k, v in self.wall_by_kind.items()}
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


def start_run(budget_s):
    """A CLI's entry: set the wall ceiling for this run's budget and print the clock's report at exit."""
    set_ceiling(budget_s)
    if work_mode() or clock().profile:
        import atexit
        import json
        atexit.register(lambda: print("[kae.budget] " + json.dumps(clock().report()), flush=True))


def now(kind="poll"):
    return clock().now(kind)


def wall_timeout(seconds):
    """Wall seconds to allow a subprocess a caller gave `seconds` of budget: the same (time mode), or
    what is left to the ceiling, at least an hour without one (work mode): a timeout read from the
    budget would kill a slow step on a busy host, and the budget does not run while it waits."""
    c = clock()
    if c.mode == "time":
        return seconds
    return max(60.0, c.ceiling - c.wall()) if c.ceiling is not None else max(3600.0, float(seconds))


def cpu_now():
    """A stage's own CPU clock: time.process_time() (time mode), the charged work (work mode)."""
    return clock().spent if work_mode() else time.process_time()


def cpsat_limit(params, time_s):
    """Bound a CP-SAT solve by `time_s` budget seconds: wall time (time mode), or the solver's own
    deterministic time with deterministic parallel search (work mode)."""
    if work_mode():
        params.max_deterministic_time = max(0.05, float(time_s) / clock().rates["cpsat_dtime"])
        params.max_time_in_seconds = max(600.0, CEILING_FACTOR * float(time_s))
        params.num_workers = 1                # one worker: CP-SAT is repeatable only so (interleave_search was not)
    else:
        params.max_time_in_seconds = max(0.05, float(time_s))


def cpsat_charge(solver):
    """Charge a finished CP-SAT solve's deterministic time."""
    charge("cpsat_dtime", float(solver.ResponseProto().deterministic_time))


def charge(kind, units=1.0):
    return clock().charge(kind, units)


def work_mode():
    return clock().mode == "work"


