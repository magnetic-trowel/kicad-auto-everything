#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Pick the J1 chassis boards deterministically from the merit suite.

    select_boards.py AA_JOINT_RESULTS_CSV REPO_FAMILY_JSON [--out boards.txt] [--n 80]

From the aa-joint control method's rows: split B or C, at most 500 pads, one board per repo family.
Boards are ordered by sha256(SEED + id), taken in that order within each split, in proportion to the
split's share of the pool. Stable: the same inputs always give the same list.
"""
import argparse
import csv
import hashlib
import json

SEED = "j1-chassis-2026-11-08"
CONTROL = "kae joint decide control 680c30e (restarts)"


def key(bid):
    return hashlib.sha256((SEED + "\0" + bid).encode()).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("results"), ap.add_argument("families")
    ap.add_argument("--out", default="boards.txt"), ap.add_argument("--n", type=int, default=80)
    a = ap.parse_args()
    fam = json.load(open(a.families))
    rows = [r for r in csv.DictReader(open(a.results)) if r["method"] == CONTROL]
    pool = [r for r in rows if r["split"] in ("B", "C") and r["pads"] and int(r["pads"]) <= 500]
    best = {}
    for r in sorted(pool, key=lambda r: key(r["board"])):
        best.setdefault(fam.get(r["board"]) or r["board"], r)
    pool = list(best.values())
    by_split = {s: sorted((r for r in pool if r["split"] == s), key=lambda r: key(r["board"])) for s in ("B", "C")}
    take = {s: round(a.n * len(v) / len(pool)) for s, v in by_split.items()}
    take["C"] += a.n - sum(take.values())
    chosen = sorted(r["board"] for s, v in by_split.items() for r in v[:take[s]])
    with open(a.out, "w") as f:
        f.write("\n".join(chosen) + "\n")
    print(f"pool {len(pool)} ({ {s: len(v) for s, v in by_split.items()} }), chose {len(chosen)} ({take}), seed {SEED}")


if __name__ == "__main__":
    main()
