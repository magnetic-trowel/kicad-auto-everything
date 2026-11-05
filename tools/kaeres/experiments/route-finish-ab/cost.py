#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Cost of the route-finish A/B per arm and stage, from stored timings (PLAN.md, cost).

    cost.py [--boards FILE] [--s1 FILE] [--cores 50]

- Routing arms (A, C, D, E): merge3-ab's A0 runs (same wrapper and budget): runtime plus the job's prepare
  share, scoring and in-job physics, at the job's 4 cpus. C, D, E add the finish pass where A0 stopped well
  inside its budget (clean early); elsewhere the finish's reserve comes out of the same budget.
- B: prepare, finish (restart.py finish_estimate: 15 s + 0.17 s per pad + two DRCs), its input DRC and
  scoring, at 2 cpus. A0r (re-score): prepare and scoring.
- Physics: per board, the median finished evaluation of the same board in the queue's history (4 cpus).
  Heavy boards (> 10 min) run at 16 cpus; assumed 2x faster there, so their CPU-hours double.
- Offsets: three shifted rasters of every light board (physics <= 10 min), for the arms named in each stage.
- Step cache: each attempt's three fork boards and one more board-sized blob, gzip, per routing arm.
Wall time is CPU-hours over the share of the queue the experiment gets (--cores), plus the longest
single job (the tail).
"""
import argparse
import csv
import json
import math
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from submit import history  # noqa: E402

STORE = Path(os.path.expanduser(os.environ.get("KAE_RESULTS", "~/kae-baselines")))
A0 = "286c2335844d"


def load():
    rows = {r["board"]: r for r in csv.DictReader(open(STORE / "experiments" / "merge3-ab" / "results.csv"))
            if r["method_id"] == A0}
    out = {}
    for b, r in rows.items():
        d = STORE / "boards" / b / "runs" / "kae-bridge-main-final-restarts.286c2335.a0"
        j = json.loads((d / "run.json").read_text())
        w, js = j.get("work") or {}, j.get("job_steps") or {}
        rt = float(r["runtime_s"])
        att = max(1, w.get("attempts") or 1)
        judge = (w.get("judge_wall_s") or 0.0) / att
        pads, fp = float(r["pads"]), float(r["footprints"] or 0)
        budget = min(4 * 3600, 900 * max(1.0, fp / 40) ** 0.5)
        fin = max(30.0, 15 + 0.17 * pads + 2 * judge + 5) + judge
        gz = (d / "output.kicad_pcb.gz").stat().st_size
        out[b] = dict(rt=rt, prep=js.get("prepare", {}).get("wall_s", 0.0) / 2,
                      score=max(0.0, js.get("run", {}).get("wall_s", rt) - rt), phys_in=js.get("physics", {}).get("wall_s", 0.0) / 2,
                      budget=budget, fin=fin, judge=judge, gz=gz, att=att)
    return out


def costs(boards, T, H):
    """{item: (job-hours, CPU-hours, longest job s)} over `boards`."""
    route = sum(T[b]["rt"] + T[b]["prep"] + T[b]["score"] + T[b]["phys_in"] for b in boards) / 3600
    extra = sum(T[b]["fin"] for b in boards if T[b]["rt"] < 0.8 * T[b]["budget"]) / 3600
    tail_r = max([T[b]["rt"] for b in boards] + [0])
    bh = sum(2 * T[b]["prep"] + T[b]["fin"] + T[b]["judge"] + T[b]["score"] for b in boards) / 3600
    a0h = sum(2 * T[b]["prep"] + T[b]["score"] for b in boards) / 3600
    light = [0.0, 0.0, 0.0]
    heavy = [0.0, 0.0, 0.0]
    for b in boards:
        ev = H.get(b, (None, None))[0]
        if ev is None:
            continue
        if ev > 600:      # 16 cpus, assumed 2x faster than the 4-cpu history
            heavy[0] += ev / 2 / 3600
            heavy[1] += ev / 2 * 16 / 3600
            heavy[2] = max(heavy[2], ev / 2)
        else:
            light[0] += ev / 3600
            light[1] += ev * 4 / 3600
            light[2] = max(light[2], ev)
    return {"route A": (route, route * 4, tail_r), "route C/D/E": (route + extra, (route + extra) * 4, tail_r),
            "fork B": (bh, bh * 2, max([T[b]["fin"] for b in boards] + [0])), "re-score A0": (a0h, a0h * 2, 720.0),
            "physics light": tuple(light), "physics heavy": tuple(heavy),
            "offsets light": (3 * light[0], 3 * light[1], light[2])}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--boards", default=str(HERE.parent / "route-finish-ab.boards.txt"))
    ap.add_argument("--s1", default=str(HERE.parent / "route-finish-ab-s1.boards.txt"))
    ap.add_argument("--cores", type=float, default=50.0, help="cores the queue gives the experiment on average")
    a = ap.parse_args()
    boards = Path(a.boards).read_text().split()
    s1 = Path(a.s1).read_text().split()
    rest = [b for b in boards if b not in s1]
    T, H = load(), history()
    unsolved = [b for b in boards if H.get(b, (None, None))[0] is None]
    heavy = [b for b in boards if (H.get(b, (None, None))[0] or 0) > 600]
    disk = sum(T[b]["gz"] * T[b]["att"] * 4 for b in boards) / 1e9
    print(f"{len(boards)} boards ({len(heavy)} with physics > 10 min at 4 cpus); physics left out (no evaluation "
          f"ever finished): {', '.join(unsolved) or '-'}\n")
    print("| item, per arm | boards | job-hours | CPU-hours | longest job (h) |\n|---|---|---|---|---|")
    for name, bs in (("all", boards), ("stage 1", s1)):
        for k, (jh, ch, tl) in costs(bs, T, H).items():
            print(f"| {k} ({name}) | {len(bs)} | {jh:.1f} | {ch:.0f} | {tl / 3600:.1f} |")
    print(f"\nStep cache: ~{disk:.1f} GB per routing arm on all boards (cap 50 GB).\n")
    C1, CR, CA = costs(s1, T, H), costs(rest, T, H), costs(boards, T, H)
    plans = [
        ("stage 1: 40 boards; route A, C; fork B; physics human, A, B, C; offsets A, B, C", [
            (C1, "route A", 1), (C1, "route C/D/E", 1), (C1, "fork B", 1), (C1, "physics light", 4),
            (C1, "physics heavy", 4), (C1, "offsets light", 3)]),
        ("stage 2: other 173 boards A, C, B; all 213 D, E; A0r; physics light for 7 arms, heavy for human, A, C; "
         "offsets light A-E", [
            (CR, "route A", 1), (CR, "route C/D/E", 1), (CA, "route C/D/E", 2), (CR, "fork B", 1), (CA, "re-score A0", 1),
            (CR, "physics light", 4), (CA, "physics light", 3), (CR, "physics heavy", 3), (CR, "offsets light", 3),
            (CA, "offsets light", 2)]),
        ("stage 2 option: heavy-board physics for B, D, E, A0 too", [(CA, "physics heavy", 4)]),
    ]
    print("| plan | CPU-hours | wall at --cores (h) |\n|---|---|---|")
    for name, items in plans:
        ch = sum(c[i][1] * k for c, i, k in items)
        tl = max(c[i][2] for c, i, _ in items)
        print(f"| {name} | {ch:.0f} | {ch / a.cores + tl / 3600:.1f} |")


if __name__ == "__main__":
    main()
