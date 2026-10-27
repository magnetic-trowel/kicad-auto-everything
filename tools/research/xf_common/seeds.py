# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Seed spread of kaebench joint runs (and place runs with --probe self): compare.py
reads attempt-0 only.

    python seeds.py $XF_WORK/results/RUN1 [RUN2 ...] [--suite FILE]

Per run and attempt (seed): legal, clean, mean completion over the suite's boards; then
mean +- sd over seeds and best-of-k (a board counts as clean if any seed is clean). Uses
the same definitions as tools/research/pnr/compare.py.
"""
import argparse
import json
import statistics as st
from collections import defaultdict
from pathlib import Path


def load(run):
    rows = defaultdict(dict)  # attempt -> id -> metrics
    for f in [*Path(run).glob("*/place/*/attempt-*/attempt.json"), *Path(run).glob("*/joint/*/attempt-*/attempt.json")]:
        r = json.loads(f.read_text())
        s = r.get("score") or {}
        # joint tasks (harness score v7) carry placement and routing in one score
        p = s if r.get("kind") == "joint" else ((r.get("probe") or {}).get("score") or {})
        rows[r["attempt"]][r["id"]] = dict(
            legal=bool(s.get("legal")), clean=bool(s.get("legal")) and bool(p.get("clean")),
            completion=p.get("completion", 0.0) if s.get("valid") else 0.0)
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("runs", nargs="+")
    ap.add_argument("--suite")
    a = ap.parse_args()
    ids = None
    if a.suite:
        ids = [x.strip() for x in Path(a.suite).read_text().split() if x.strip() and not x.startswith("#")]
    print("| run | seeds | boards | legal (mean +- sd) | clean (mean +- sd) | completion (mean +- sd) | clean best-of-k |")
    print("|---|---|---|---|---|---|---|")
    for run in a.runs:
        rows = load(run)
        seeds = sorted(rows)
        if not seeds:
            print(f"| {Path(run).name} | 0 | | | | | |")
            continue
        board_ids = ids or sorted(set().union(*rows.values()))
        per = {k: [] for k in ("legal", "clean", "completion")}
        for sd in seeds:
            for k in per:
                per[k].append(sum(rows[sd].get(i, {}).get(k, 0.0) for i in board_ids) / len(board_ids))
        best = sum(any(rows[sd].get(i, {}).get("clean") for sd in seeds) for i in board_ids) / len(board_ids)
        missing = sum(i not in rows[sd] for sd in seeds for i in board_ids)

        def fmt(xs):
            return f"{st.mean(xs):.3f} +- {st.stdev(xs):.3f}" if len(xs) > 1 else f"{xs[0]:.3f}"
        note = f" ({missing} attempts missing)" if missing else ""
        print(f"| {Path(run).name} | {len(seeds)} | {len(board_ids)}{note} | {fmt(per['legal'])} | "
              f"{fmt(per['clean'])} | {fmt(per['completion'])} | {best:.3f} |")


if __name__ == "__main__":
    main()
