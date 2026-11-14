# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Units and job times: sizes, durations, CPU lists, how long a job has run and been frozen."""
import re
import time

from .consts import GB


def parse_cpus(spec):
    out = set()
    for part in str(spec).split(","):
        if "-" in part:
            a, b = part.split("-")
            out.update(range(int(a), int(b) + 1))
        elif part.strip():
            out.add(int(part))
    return out


def parse_size(s):
    m = re.fullmatch(r"([\d.]+)\s*([kmgt]?)b?", str(s).strip().lower())
    if not m:
        raise ValueError(f"bad size {s!r} (use e.g. 512M, 8G)")
    return float(m.group(1)) * {"": 1 << 20, "k": 1 << 10, "m": 1 << 20, "g": GB, "t": GB << 10}[m.group(2)]


def parse_dur(s):
    m = re.fullmatch(r"([\d.]+)\s*([smhd]?)", str(s).strip().lower())
    if not m:
        raise ValueError(f"bad duration {s!r} (use e.g. 90s, 15m, 2h)")
    return int(float(m.group(1)) * {"": 1, "s": 1, "m": 60, "h": 3600, "d": 86400}[m.group(2)])


def fgb(mb):
    return f"{mb / 1024:.1f}G"


def fdur(s):
    s = int(s)
    return f"{s}s" if s < 120 else f"{s // 60}m" if s < 7200 else f"{s // 3600}h"


def frozen_for(j, now):
    """Seconds this attempt of a job has spent frozen (waiting for memory), the current freeze included."""
    fs = j["frozen_since"] if "frozen_since" in j.keys() else 0
    return (j["frozen_s"] if "frozen_s" in j.keys() else 0) + (max(0.0, now - fs) if fs else 0.0)


def active_for(j, now):
    """Seconds this attempt of a job has been allowed to run: wall time since its start minus time frozen.
    --timeout counts this, so a job the queue pauses often is not penalized for it."""
    if not j["started"]:
        return 0.0
    if j["state"] == "queued":     # requeued: its last attempt's times were moved to lost_*
        return 0.0
    end = j["finished"] if j["state"] != "running" and j["finished"] else now
    return max(0.0, end - j["started"] - frozen_for(j, end))


def times(j, now=None):
    """A job's time accounting in one phrase: active time (what --timeout counts), time frozen waiting for memory
    and how often, CPU time, and what earlier attempts that were thrown away (requeued) had used."""
    now = now or time.time()
    out = f"ran {fdur(active_for(j, now))}"
    fz = frozen_for(j, now)
    if fz or j["freezes"]:
        out += f" (+{fdur(fz)} frozen, {j['freezes']}x{', now' if j['frozen_since'] else ''})"
    if j["cpu_s"]:
        out += f" cpu {fdur(j['cpu_s'])}"
    if "squeezed_mb" in j.keys() and j["squeezed_mb"] >= 1:
        out += f" (squeezed {fgb(j['squeezed_mb'])} of cold memory into zram)"
    if "cpu_wait_s" in j.keys() and j["cpu_wait_s"] >= 1:
        out += f" (waited for CPUs {fdur(j['cpu_wait_s'])}, all threads {fdur(j['cpu_stall_s'])})"
    if j["lost_run_s"]:
        out += f" | earlier attempts {fdur(j['lost_run_s'])}, cpu {fdur(j['lost_cpu_s'])}"
    return out
