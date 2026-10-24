# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Physics over seeds: mean +- sd of physics_score's per-seed ratios.

    python physseeds.py OUT_DIR

OUT_DIR holds seed-N/<run>.json from physics_score_xf.py --attempt N (score.sh writes
them). Per run: fast physics (place terms total, method/human gmean) and routed physics
(board physics on the real copper, method/human gmean), mean +- sd over the seeds, with
the boards scored per seed.
"""
import json
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path


def fmt(xs):
    xs = [x for x in xs if x is not None]
    if not xs:
        return "-"
    return f"{st.mean(xs):.2f} +- {st.stdev(xs):.2f}" if len(xs) > 1 else f"{xs[0]:.2f}"


def main(out):
    runs = defaultdict(dict)  # run -> seed -> summary
    for f in sorted(Path(out).glob("seed-*/*.json")):
        runs[f.stem][int(f.parent.name.split("-")[1])] = json.loads(f.read_text())["summary"]
    print("| run | seeds | fast phys x human (mean +- sd) | routed phys x human (mean +- sd) | boards scored fast / routed (per seed) |")
    print("|---|---|---|---|---|")
    for run, by in runs.items():
        seeds = sorted(by)
        print(f"| {run} | {len(seeds)} | {fmt([by[s]['place_gmean_ratio'] for s in seeds])} | "
              f"{fmt([by[s]['routed_gmean_ratio'] for s in seeds])} | "
              f"{', '.join(str(by[s]['place_scored']) for s in seeds)} / {', '.join(str(by[s]['routed_scored']) for s in seeds)} |")


if __name__ == "__main__":
    main(sys.argv[1])
