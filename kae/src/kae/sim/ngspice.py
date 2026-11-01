# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Run a deck in ngspice (batch mode) and read its `.meas` results.

ngspice is found on PATH, else inside the KiCad container (KAE_KICAD_WRAP, which ships ngspice).
Batch mode exits 0 when a `.meas` fails or a line is ignored, so the exit code is not trusted: a
measurement that does not print a value is reported as failed, and warning and error lines are kept.
"""
from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

_VAL = re.compile(r"^\s*([a-z_][a-z0-9_]*)\s*=\s*([-+]?(?:\d+\.?\d*|\.\d+)(?:e[-+]?\d+)?)", re.I)


@dataclass
class Result:
    meas: dict = field(default_factory=dict)      # name (lower case) -> value
    failed: list = field(default_factory=list)
    problems: list = field(default_factory=list)  # warning and error lines
    seconds: float = 0.0
    ok: bool = True


def command():
    if shutil.which("ngspice"):
        return ["ngspice"]
    wrap = os.environ.get("KAE_KICAD_WRAP")
    if wrap:
        return shlex.split(wrap) + ["ngspice"]
    raise RuntimeError("ngspice not found: put it on PATH or set KAE_KICAD_WRAP (the KiCad container ships it)")


def run(deck, workdir, names, timeout=900):
    """Run `deck` (text) in `workdir`; `names`: the .meas names to read."""
    wd = Path(workdir)
    wd.mkdir(parents=True, exist_ok=True)
    (wd / "deck.cir").write_text(deck)
    t0 = time.time()
    try:
        p = subprocess.run(command() + ["-b", "deck.cir"], cwd=wd, capture_output=True, text=True, timeout=timeout)
        out = p.stdout + "\n" + p.stderr
    except subprocess.TimeoutExpired as e:
        out = (e.stdout or "") if isinstance(e.stdout, str) else ""
        r = Result(ok=False, problems=[f"timeout after {timeout} s"], seconds=time.time() - t0)
        r.failed = [n.lower() for n in names]
        return r
    (wd / "ngspice.log").write_text(out)
    r = Result(seconds=time.time() - t0)
    want = {n.lower() for n in names}
    for line in out.splitlines():
        m = _VAL.match(line)
        if m and m.group(1).lower() in want and m.group(1).lower() not in r.meas:
            r.meas[m.group(1).lower()] = float(m.group(2))
        low = line.lower()
        if ("error" in low or "warning" in low) and "no compatibility mode" not in low:
            r.problems.append(line.strip()[:300])
    if re.search(r"timestep too small|simulation\(s\) aborted", out, re.I):
        # an aborted run: anything measured after it (a .control block) saw a partial waveform
        r.problems.append("analysis aborted: " + (re.findall(r".*timestep too small.*", out, re.I) or ["?"])[0].strip()[:200])
        r.meas = {}
    r.failed = sorted(want - set(r.meas))
    r.ok = not r.failed and not any("error" in x.lower() for x in r.problems)
    return r
