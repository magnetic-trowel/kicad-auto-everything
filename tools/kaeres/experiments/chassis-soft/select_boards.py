#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Boards for loop-physics-matched (PLAN.md): physics_inputs_ok and route_demand easy or moderate, usable and
qualified, one per repo family, in sha256(seed, id) order.
    python3 select_boards.py SUITES_DIR USABILITY.jsonl > boards-all.txt"""
import hashlib
import json
import sys
from pathlib import Path

SEED = "loop-physics-matched-2026-11-10"
suites, usab = Path(sys.argv[1]), sys.argv[2]
U = {d["id"]: d for d in map(json.loads, open(usab))}
S = lambda n: set((suites / f"{n}.txt").read_text().split())  # noqa: E731
pool = [b for b in S("physics_inputs_ok") & (S("route_demand.easy") | S("route_demand.moderate"))
        if b in U and U[b]["usable_route_test"] and U[b]["task_qualified"]]
seen, out = set(), []
for b in sorted(pool, key=lambda b: hashlib.sha256(f"{SEED}|{b}".encode()).hexdigest()):
    if U[b]["repo_family"] not in seen:
        seen.add(U[b]["repo_family"])
        out.append(b)
print("\n".join(out))
