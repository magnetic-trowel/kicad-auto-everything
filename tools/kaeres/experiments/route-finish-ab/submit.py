#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""kaeq jobs for the route-finish-ab arms that kaeres does not run: forks (B, A0) and measures (geometry
stats and physics). Writes a JSONL job file; submits it only with --submit.

    submit.py fork --arm B --a-id ID --sha SHA --boards FILE [--submit]
    submit.py fork --arm A0 --sha SHA --boards FILE
    submit.py measure --arm human|A0|B|ID --sha SHA --boards FILE [--offsets] [--submit]

Physics resources per board come from the queue's history of earlier evaluations of the same board
(owners phys-*, rescore-*, ab4): --mem 1.3 x the largest observed peak (at least 4 GB), 16 cpus for boards
whose evaluation took over 10 min at 4 cpus (else 4), timeout 3 x that time + 30 min (1-12 h). Boards no
evaluation ever finished are left out unless --include-unsolved. --offsets adds the three shifted rasters
(PLAN.md, noise) for the boards given. Jobs run in this folder of a snapshot of the caller's tree.
"""
import argparse
import json
import os
import re
import sqlite3
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OFFSETS = ((0.0625, 0.0625), (0.125, 0.125), (0.1875, 0.1875))   # quarter-pitch steps of the 0.25 mm raster


def history():
    """{board: (eval_s at 4 cpus or None, peak_mb or None)} from the kaeq database."""
    db = Path(f"/var/tmp/{os.environ.get('USER', '')}/kaeq/queue.db")
    out = {}
    if not db.exists():
        return out
    c = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    q = ("select owner, cmd, peak_mb, started, finished, state from jobs where (owner like 'phys-%' or owner like "
         "'rescore-%' or owner = 'ab4' or owner = 'rf-ab') and state in ('ok', 'timeout')")
    for owner, cmd, peak, t0, t1, state in c.execute(q):
        m = re.search(r"boards/([^/ ]+)/board\.kicad_pcb", cmd) or re.search(r"/ab4/([^ /]+)", cmd) \
            or re.search(r"measure\.sh (\S+) ", cmd)
        if not m or not t0 or not t1:
            continue
        s, p = out.setdefault(m.group(1), [[], []])
        if peak:
            p.append(peak)
        if state == "ok" and owner not in ("ab4",):   # ab4 jobs hold three evaluations and the passes
            s.append(t1 - t0)
    return {b: (sorted(s)[len(s) // 2] if s else None, max(p) if p else None) for b, (s, p) in out.items()}


def size_mb(b):
    p = Path.home() / "kae-boards" / "boards" / b / "board.kicad_pcb"
    return p.stat().st_size / 2 ** 20 if p.exists() else 1.0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("what", choices=("fork", "measure"))
    ap.add_argument("--arm", required=True)
    ap.add_argument("--sha", required=True)
    ap.add_argument("--a-id", help="arm A's kaeres method id (fork B)")
    ap.add_argument("--boards", required=True, help="file of board ids, or a comma list")
    ap.add_argument("--out", default=f"/var/tmp/{os.environ.get('USER', '')}/rf-ab")
    ap.add_argument("--offsets", action="store_true")
    ap.add_argument("--include-unsolved", action="store_true")
    ap.add_argument("--owner", default="rf-ab")
    ap.add_argument("--prio", type=int, default=0)
    ap.add_argument("--submit", action="store_true")
    a = ap.parse_args()
    boards = Path(a.boards).read_text().split() if Path(a.boards).exists() else a.boards.split(",")
    env = f"SHA={a.sha} OUT={a.out}" + (f" A_ID={a.a_id}" if a.a_id else "")
    hist = history() if a.what == "measure" else {}
    jobs, skipped, est = [], [], 0.0
    for b in boards:
        short = b[:40]
        if a.what == "fork":
            big = size_mb(b) > 20
            jobs.append(dict(cmd=f"env {env} bash fork.sh {a.arm} {b}", name=f"rfab:{a.arm}:{short}", cpus=2,
                             mem="24G" if big else "8G", disk="8G" if big else "2G", timeout="6h", prio=a.prio))
            continue
        ev, peak = hist.get(b, (None, None))
        if ev is None and not a.include_unsolved:
            skipped.append(b)
            continue
        ev = ev or 6 * 3600.0
        cpus = 16 if ev > 600 else 4
        mem = max(4096, int(1.3 * (peak or 3000)))
        tmo = int(min(12 * 3600, max(3600, 3 * ev + 1800)))
        for off in (OFFSETS if a.offsets else (None,)):
            cmd = f"env {env} bash measure.sh {b} {a.arm}" + (f" {off[0]} {off[1]}" if off else "")
            jobs.append(dict(cmd=cmd, name=f"rfab:m:{a.arm[:8]}:{short}" + (f"@{off[0]}" if off else ""), cpus=cpus,
                             mem=f"{mem}M", disk="4G", timeout=f"{tmo}s", prio=a.prio))
            est += ev
    f = Path(a.out) / f"jobs-{a.what}-{a.arm[:12]}{'-off' if a.offsets else ''}.jsonl"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text("".join(json.dumps(j) + "\n" for j in jobs))
    print(f"{len(jobs)} jobs -> {f}" + (f"; physics ~{est / 3600:.1f} job-h at 4 cpus" if est else "")
          + (f"; left out (no evaluation ever finished): {' '.join(skipped)}" if skipped else ""))
    if a.submit and jobs:
        if a.prio > 5:
            sys.exit("priority above 5 needs the user's say-so")
        subprocess.run(["kaeq", "submit", "--jobs", str(f), "--owner", a.owner, "--tag", f"rfab-{a.what}-{a.arm[:12]}",
                        "--retries", "1"], check=True, cwd=HERE)


if __name__ == "__main__":
    main()
