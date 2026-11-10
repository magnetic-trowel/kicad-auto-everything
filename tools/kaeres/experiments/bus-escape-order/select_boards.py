#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Boards for bus-escape-order: boards with a bus that fails alone in bus-alone-b1 (buses.csv, class `fails_alone`) and
has a ball-grid end (end type naming `bga` or `grid`), in the `bga` or `kae_escape_grid` suite, `usable_route_test`,
one per `repo_family`, ordered by sha256(seed, id).

    python select_boards.py BUSES_CSV BOARD_TAGS_DIR > boards.txt
"""
import csv
import hashlib
import json
import sys

SEED = "bus-escape-order-2026-11-10"


def main(buses_csv, tags):
    grid = {r["board"] for r in csv.DictReader(open(buses_csv))
            if r["cls"] == "fails_alone" and any(k in (r["a_type"] or "") + (r["b_type"] or "") for k in ("bga", "grid"))}
    suite = set()
    for s in ("bga", "kae_escape_grid"):
        suite |= {l.strip() for l in open(f"{tags}/suites/{s}.txt") if l.strip()}
    us = {r["id"]: r for r in map(json.loads, open(f"{tags}/structural/usability.jsonl"))}
    key = lambda b: hashlib.sha256(f"{SEED}:{b}".encode()).hexdigest()   # noqa: E731
    fams = {}
    for b in sorted(grid & suite, key=key):
        u = us.get(b)
        if u and u.get("usable_route_test"):
            fams.setdefault(u["repo_family"], b)
    print("\n".join(sorted(fams.values(), key=key)))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
