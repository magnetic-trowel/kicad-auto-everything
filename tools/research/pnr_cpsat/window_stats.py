# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Summarize the CP-SAT window log of kaebench runs (attempt-N/cpsat_windows.json).

    python window_stats.py kae-work/results/RUN [...]
"""
import json
import statistics as st
import sys
from pathlib import Path


def main(runs):
    for run in runs:
        rows = []
        for f in Path(run).glob("*/place/*/attempt-0/cpsat_windows.json"):
            rows += json.loads(f.read_text())
        if not rows:
            print(run, "no window logs")
            continue
        n = len(rows)
        solved = [r for r in rows if r.get("obj") is not None]
        moved = [r for r in rows if (r.get("moved") or 0) > 0]
        acc = [r for r in rows if r.get("after") is not None and r["after"] < r["before"] - 1e-6]
        acc_mv = [r for r in acc if (r.get("moved") or 0) > 0]
        med = lambda k, rs=rows: round(st.median([r[k] for r in rs if r.get(k) is not None]), 2) if any(r.get(k) is not None for r in rs) else None
        print(f"{Path(run).name}: windows {n}, parts/window {med('parts')}, cells {med('cells')}, poses {med('poses')}, "
              f"vars {med('vars')}, solve_s {med('solve_s')} (wall), build_s {med('build_s')}")
        print(f"  status: " + ", ".join(f"{s} {sum(1 for r in rows if r.get('status') == s)}"
                                         for s in sorted({r.get('status') for r in rows}, key=str)))
        print(f"  CP-SAT moved >= 1 part: {len(moved)}/{len(solved)} solved; accepted {len(acc)} "
              f"(with a move {len(acc_mv)}); decode illegal {sum(1 for r in rows if r.get('decode'))}")
        miss = [r["cur_obj"] // 3000 for r in rows if r.get("cur_obj") is not None]
        if miss:
            print(f"  model misses at the current poses (phase 1): median {st.median(miss)}, "
                  f"windows with >= 1 miss {sum(1 for m in miss if m >= 1)}/{len(miss)}")


if __name__ == "__main__":
    main(sys.argv[1:])
