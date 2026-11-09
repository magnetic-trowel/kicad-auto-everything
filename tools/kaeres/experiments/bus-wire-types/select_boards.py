#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Boards for bus-wire-types: one per repo_family of bga ∩ kae_escape_grid ∩ plane_layers, usable_route_test, 30-1500
footprints, ordered by sha256(seed, id). Prints the first N ids; the rest are the pre-registered extension.

    python select_boards.py BOARD_TAGS_DIR MANIFEST N
"""
import hashlib
import json
import sys

SEED = "bus-wire-types-2026-11-09"


def main(tags, manifest, n):
    suites = [{l.strip() for l in open(f"{tags}/suites/{s}.txt") if l.strip()} for s in ("bga", "kae_escape_grid", "plane_layers")]
    us = {r["id"]: r for r in map(json.loads, open(f"{tags}/structural/usability.jsonl"))}
    man = {r["id"]: r for r in map(json.loads, open(manifest))}
    key = lambda b: hashlib.sha256(f"{SEED}:{b}".encode()).hexdigest()   # noqa: E731
    fams = {}
    for b in sorted(suites[0] & suites[1] & suites[2], key=key):
        u, m = us.get(b), man.get(b)
        if u and m and u.get("usable_route_test") and 30 <= m.get("footprints", 0) <= 1500:
            fams.setdefault(u["repo_family"], b)
    print("\n".join(sorted(fams.values(), key=key)[:n]))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], int(sys.argv[3]))
