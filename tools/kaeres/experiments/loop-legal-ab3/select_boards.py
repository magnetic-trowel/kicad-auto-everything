#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Boards for loop-legal-ab2 (PLAN.md) from the tight-part scans (JSON lines: board, anchored, ...).
    python3 select_boards.py USABILITY.jsonl PREVIOUS_BOARDS.txt SCAN.jsonl... > boards-all.txt
First the previous experiment's boards, then the rest of the pool in sha256(seed, id) order; one per repo family."""
import hashlib
import json
import sys

SEED = "loop-legal-ab2-2026-11-10"
U = {d["id"]: d for d in map(json.loads, open(sys.argv[1]))}
prev = open(sys.argv[2]).read().split()
pool = set()
for f in sys.argv[3:]:
    for line in open(f):
        d = json.loads(line)
        if d.get("anchored") and U.get(d["board"], {}).get("usable_route_test"):
            pool.add(d["board"])
order = [b for b in prev if b in pool] + sorted(pool - set(prev), key=lambda b: hashlib.sha256(f"{SEED}|{b}".encode()).hexdigest())
seen, out = set(), []
for b in order:
    fam = U[b]["repo_family"]
    if fam not in seen:
        seen.add(fam)
        out.append(b)
print("\n".join(out))
