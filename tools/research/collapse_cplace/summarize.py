# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Multi-seed comparison of place runs (kaebench --probe self), as pnr/compare.py but over
attempts 0..k-1 (attempt N = seed N).

    python summarize.py --suite kae-work/ab33.txt [--seeds 0,1,2] RUN_DIR [RUN_DIR ...]

Per run: mean over the seeds present of legal, clean, completion; length and vias summed
over (board, seed) pairs that every run completed (only seeds every run has); DRC error
types over all its attempts.
"""
import argparse
import json
from collections import Counter
from pathlib import Path


def load(run, ids):
    rows = {}
    for f in Path(run).glob("*/place/*/attempt-*/attempt.json"):
        r = json.loads(f.read_text())
        if r["id"] not in ids:
            continue
        s = r.get("score") or {}
        p = (r.get("probe") or {}).get("score") or {}
        rows[(r["id"], int(r["attempt"]))] = dict(
            legal=bool(s.get("legal")), clean=bool(s.get("legal")) and bool(p.get("clean")),
            completion=p.get("completion", 0.0) if s.get("valid") else 0.0,
            length=p.get("track_length_mm"), vias=p.get("vias"), errors=p.get("errors_by_type") or {})
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("runs", nargs="+")
    ap.add_argument("--suite", required=True)
    ap.add_argument("--seeds", default=None)
    a = ap.parse_args()
    ids = set(Path(a.suite).read_text().split())
    data = {Path(r).name: load(r, ids) for r in a.runs}
    seeds = sorted(set.intersection(*[{k[1] for k in d} for d in data.values()]))
    if a.seeds:
        seeds = [s for s in seeds if s in {int(x) for x in a.seeds.split(",")}]
    keys = sorted(set.intersection(*[set(d) for d in data.values()]))
    keys = [k for k in keys if k[1] in seeds]
    full = [k for k in keys if all(d[k]["completion"] >= 1.0 and d[k]["length"] for d in data.values())]
    nb = len({k[0] for k in keys})
    print(f"boards {nb}, seeds {seeds}, (board, seed) pairs {len(keys)}, all-complete pairs {len(full)}\n")
    print("| run | legal | clean | completion | clean per seed | length (all-complete) | vias | top DRC errors |")
    print("|---|---|---|---|---|---|---|---|")
    for name, d in data.items():
        rows = [d[k] for k in keys]
        n = len(rows)
        errs = Counter()
        for r in rows:
            errs.update(r["errors"])
        per = " / ".join(f"{sum(d[k]['clean'] for k in keys if k[1] == s) / nb:.3f}" for s in seeds)
        print(f"| {name} | {sum(r['legal'] for r in rows) / n:.3f} | {sum(r['clean'] for r in rows) / n:.3f} "
              f"| {sum(r['completion'] for r in rows) / n:.3f} | {per} | {sum(d[k]['length'] for k in full):.0f} "
              f"| {sum(d[k]['vias'] for k in full)} | {dict(errs.most_common(3))} |")


if __name__ == "__main__":
    main()
