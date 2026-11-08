#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Acceptance test for counted-work budgets: the same command at two load levels must give the
same board.

Runs COMMAND twice with KAE_BUDGET=work, both pinned to the same CPUs: once alone, once while busy
loops share those CPUs (each busy loop takes about one CPU's worth of time, so the command gets
roughly half the speed). The load stays inside the CPUs this job was given (run it through kaeq),
so no other user's work is slowed. Compares the two outputs' placement (footprint reference,
position, rotation, side) and copper (tracks, arcs, vias), and prints the wall times and the
first differences.

    acceptance.py --cpus 2 --hogs 2 --workdir W -- python -m kae.joint.cli run IN {out} --seed 0 --time 300

`{out}` in COMMAND is replaced by each run's output board. Exit 0: identical; 1: different.
"""
from __future__ import annotations

import argparse
import hashlib
import multiprocessing as mp
import os
import re
import subprocess
import sys
import time
from pathlib import Path

ITEM = re.compile(r"^\s*\((footprint|segment|arc|via)\b")


def _spin(cpus):
    os.sched_setaffinity(0, cpus)
    x = 0
    while True:
        x = (x * 1103515245 + 12345) & 0xFFFFFFFF


def _items(text):
    """Placement and copper of a .kicad_pcb as sorted canonical strings (uuids and timestamps
    dropped: they are not geometry)."""
    out, depth, cur, kind = [], 0, [], None
    for line in text.splitlines():
        if kind is None:
            m = ITEM.match(line)
            if not m:
                continue
            kind, depth, cur = m.group(1), 0, []
        cur.append(line.strip())
        depth += line.count("(") - line.count(")")
        if depth <= 0:
            s = " ".join(cur)
            s = re.sub(r"\((uuid|tstamp)\s+[^)]*\)", "", s)
            if kind == "footprint":
                ref = re.search(r'\(property "Reference" "([^"]*)"', s)
                at = re.search(r"\(at ([^)]*)\)", s)
                side = re.search(r'\(layer "([^"]*)"\)', s)
                s = f"fp {ref.group(1) if ref else '?'} at {at.group(1) if at else '?'} {side.group(1) if side else '?'}"
            out.append(s)
            kind = None
    return sorted(out)


def run(cmd, out, cpus, hogs, env, timeout):
    procs = [mp.Process(target=_spin, args=(cpus,), daemon=True) for _ in range(hogs)]
    for p in procs:
        p.start()
    try:
        t0 = time.monotonic()
        argv = [a.replace("{out}", str(out)) for a in cmd]
        r = subprocess.run(argv, env=env, timeout=timeout, preexec_fn=lambda: os.sched_setaffinity(0, cpus),
                           capture_output=True, text=True)
        dt = time.monotonic() - t0
    finally:
        for p in procs:
            p.terminate()
    return r, dt


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--cpus", type=int, default=2, help="CPUs to pin both runs to (from this process's own set)")
    ap.add_argument("--hogs", type=int, default=2, help="busy loops sharing those CPUs in the loaded run")
    ap.add_argument("--workdir", required=True)
    ap.add_argument("--timeout", type=float, default=7200)
    ap.add_argument("cmd", nargs=argparse.REMAINDER)
    a = ap.parse_args()
    cmd = a.cmd[1:] if a.cmd[:1] == ["--"] else a.cmd
    if not cmd:
        ap.error("no command")
    mine = sorted(os.sched_getaffinity(0))
    if len(mine) < a.cpus:
        ap.error(f"only {len(mine)} CPUs available")
    cpus = set(mine[:a.cpus])
    wd = Path(a.workdir)
    wd.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, KAE_BUDGET="work", OMP_NUM_THREADS="1", KAE_WORKERS="1")
    res = {}
    for name, hogs in (("alone", 0), ("loaded", a.hogs)):
        out = wd / f"{name}.kicad_pcb"
        r, dt = run(cmd, out, cpus, hogs, env, a.timeout)
        (wd / f"{name}.log").write_text(r.stdout + r.stderr)
        res[name] = (r.returncode, dt, out)
        print(f"{name}: rc {r.returncode}, {dt:.0f} s wall, log {wd / (name + '.log')}", flush=True)
    a_items, b_items = (_items(res[n][2].read_text()) if res[n][2].exists() else None for n in ("alone", "loaded"))
    if a_items is None or b_items is None:
        print("FAIL: an output is missing")
        return 1
    ha = hashlib.sha256("\n".join(a_items).encode()).hexdigest()[:12]
    hb = hashlib.sha256("\n".join(b_items).encode()).hexdigest()[:12]
    slow = res["loaded"][1] / max(1e-9, res["alone"][1])
    print(f"alone {len(a_items)} items {ha}; loaded {len(b_items)} items {hb}; loaded run took {slow:.2f}x the wall time")
    if ha == hb:
        print("PASS: identical placement and copper")
        return 0
    sa, sb = set(a_items), set(b_items)
    only_a, only_b = sorted(sa - sb), sorted(sb - sa)
    print(f"FAIL: {len(only_a)} items only alone, {len(only_b)} only loaded")
    for s in only_a[:5]:
        print("  alone :", s[:160])
    for s in only_b[:5]:
        print("  loaded:", s[:160])
    return 1


if __name__ == "__main__":
    sys.exit(main())
