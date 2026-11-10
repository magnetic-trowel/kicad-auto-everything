#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Queue the bus-only views (view_bus.py) of an experiment's runs and of the human layouts; write runs.csv for analyze.py.

Usage: submit_views.py EXPERIMENT WORK_DIR [--chunk N]. WORK_DIR holds busnets/, and gets views/, runs.csv, view-tasks/."""
import argparse
import json
import os
import subprocess
from pathlib import Path

STORE = Path(os.path.expanduser(os.environ.get("KAE_RESULTS", "~/kae-baselines")))
HERE = Path(__file__).resolve().parent
ARMS = {"c55ff7cd5c00": "control"}   # the alone arm: --alone-method (v1 a3a4a1a9933c failed in plumbing)
HUMAN = "537e5ef2"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("exp"), ap.add_argument("work"), ap.add_argument("--chunk", type=int, default=12)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--early", action="store_true", help="also view control and human runs of boards whose bus-alone run is not done")
    a = ap.parse_args()
    work = Path(a.work)
    boards = (STORE / "experiments" / a.exp / "boards.txt").read_text().split()
    rows = []
    for bid in boards:
        found = {}
        for rj in sorted((STORE / "boards" / bid / "runs").glob("*/run.json")):
            r = json.loads(rj.read_text())
            arm = ARMS.get(r["method_id"])
            if arm == "control" and r.get("experiment") == "fr-baseline" and r.get("status") == "ok" and "control" not in found:
                found[arm] = rj.parent
            elif arm == "alone" and r.get("experiment", "").startswith("bus-alone-b1") and r.get("status") == "ok":
                found[arm] = rj.parent
            elif r["method_id"].startswith(HUMAN) and "human" not in found:
                found["human"] = rj.parent
        if "control" in found and ("alone" in found or a.early):
            rows += [(bid, arm, str(d)) for arm, d in sorted(found.items())]
    if not a.early:
        (work / "runs.csv").write_text("".join(f"{b},{arm},{d}\n" for b, arm, d in rows))
    todo = [r for r in rows if not (work / "views" / f"{r[0]}.{r[1]}.json").exists()]
    td = work / "view-tasks"
    td.mkdir(parents=True, exist_ok=True)
    jobs = []
    for i in range(0, len(todo), a.chunk):
        f = td / f"{a.exp}-{i // a.chunk:05d}.txt"
        f.write_text("".join(f"{b} {arm} {d}\n" for b, arm, d in todo[i:i + a.chunk]))
        cmd = (f"bash -c 'source ~/.cache/kaebench/env.sh && export APPTAINER_BIND=/var/tmp/eriks && ulimit -v 40000000 && "
               f"python3 {HERE / 'view_bus.py'} {f} {work / 'views'} {work / 'busnets'}'")
        jobs.append(dict(cmd=cmd, name=f"busview-{i // a.chunk}", cpus=2, mem="3G", timeout="4h"))
    print(f"{len(rows)} runs, {len(todo)} views to make, {len(jobs)} jobs")
    if jobs and not a.dry_run:
        jf = td / f"{a.exp}-jobs.jsonl"
        jf.write_text("".join(json.dumps(j) + "\n" for j in jobs))
        subprocess.run(["kaeq", "submit", "--jobs", str(jf), "--tag", f"busview-{a.exp}"], check=True,
                       env=dict(os.environ, KAEQ_OWNER=f"busview-{a.exp}"))


if __name__ == "__main__":
    main()
