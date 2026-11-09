#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Boards for loop-window-bench (see PLAN.md). Pool: the 71 boards of placement-decide-joint (joint leaves opens),
usable for routing tests, one per repo_family. Order: sha256(seed, id) within footprint quartiles; first batch
40 boards (10 per quartile), the rest as the pre-registered extension.
    python3 select_boards.py ~/kae-baselines /var/tmp/.../usability.jsonl > boards.txt"""
import hashlib
import json
import sys
from pathlib import Path

SEED = "loop-window-bench-2026-11-09"
base, usability = Path(sys.argv[1]).expanduser(), sys.argv[2]
U = {d["id"]: d for d in map(json.loads, open(usability))}
pool = [b for b in (base / "experiments/placement-decide-joint/boards.txt").read_text().split()
        if b in U and U[b]["usable_route_test"]]
fp = {b: json.loads((base / "boards" / b / "board.json").read_text()).get("footprints") or 0 for b in pool}
order = sorted(pool, key=lambda b: fp[b])
quart = [order[i * len(order) // 4:(i + 1) * len(order) // 4] for i in range(4)]
pick = lambda L: sorted(L, key=lambda b: hashlib.sha256(f"{SEED}|{b}".encode()).hexdigest())
first = [b for q in quart for b in pick(q)[:10]]
rest = [b for q in quart for b in pick(q)[10:]]
print("\n".join(first + rest))
