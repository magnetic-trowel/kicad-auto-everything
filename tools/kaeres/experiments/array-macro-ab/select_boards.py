#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Boards for array-macro-ab: where the netlist detector (kae.place.arrays) finds an array.

    select_boards.py SCAN.jsonl USABILITY MERIT [--n 100]

The scan is arrays.matrices / arrays.buses on the movable parts of the tagged boards (repeated_matrix, repeated_cells aligned,
line_array, radial_array, parallel_bus). A board qualifies with a matrix of at least 16 parts or a bus of at least 6, one board
per repo_family, sha256(SEED, id) order, merit boards first, at most 2,000 pads. Deterministic.
"""
import argparse
import hashlib
import json

SEED = "array-macro-ab-2026-11-09"


def key(b):
    return hashlib.sha256((SEED + "\0" + b).encode()).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("scan"), ap.add_argument("usability"), ap.add_argument("merit"), ap.add_argument("--n", type=int, default=100)
    a = ap.parse_args()
    use = {r["id"]: r for r in map(json.loads, open(a.usability))}
    merit = {x.strip() for x in open(a.merit) if x.strip()}
    pool = [r for r in map(json.loads, open(a.scan)) if "err" not in r and use.get(r["board"], {}).get("usable_route_test")
            and r["pads"] <= 2000 and (r["matrices"] or r["buses"])]
    fams, chosen = set(), []
    for r in sorted(pool, key=lambda r: (r["board"] not in merit, key(r["board"]))):
        f = use[r["board"]].get("repo_family") or r["board"]
        if f in fams and r["board"] not in merit:
            continue
        fams.add(f)
        chosen.append(r)
        if len(chosen) >= a.n:
            break
    open("boards.txt", "w").write("\n".join(sorted(r["board"] for r in chosen)) + "\n")
    with open("boards.jsonl", "w") as h:
        for r in chosen:
            h.write(json.dumps(dict(r, merit=r["board"] in merit)) + "\n")
    print("pool", len(pool), "chosen", len(chosen), "merit", sum(r["board"] in merit for r in chosen),
          "with matrix", sum(1 for r in chosen if r["matrices"]), "with bus", sum(1 for r in chosen if r["buses"]))


if __name__ == "__main__":
    main()
