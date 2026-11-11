#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Calibrate kae.budget.RATES: nominal seconds per unit of counted work, from runs on a quiet host.

Run kae commands in time mode with KAE_BUDGET_PROFILE=1: at exit each prints a line
`[kae.budget] {...}` with, per kind of work, the units counted and the wall seconds that passed
before those charges (each charge is attributed the time since the previous clock event). This
script reads such logs and prints each kind's rate per board and the median over the boards, to
paste into RATES.

    calibrate.py LOG [LOG ...]
"""
from __future__ import annotations

import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path


def reports(path):
    for line in Path(path).read_text(errors="replace").splitlines():
        if line.startswith("[kae.budget] "):
            yield json.loads(line.split(" ", 2)[2] if line.startswith("[kae.budget]  ") else line[len("[kae.budget] "):])


def main(paths):
    per = defaultdict(list)
    tot_wall, tot_kinds = 0.0, defaultdict(float)
    for p in paths:
        for r in reports(p):
            walls = r.get("wall_by_kind") or {}
            for kind, w in walls.items():
                u = r["units"].get(kind) or 0
                tot_kinds[kind] += w
                if u > 0:
                    per[kind].append((w / u, u, w, Path(p).name))
            tot_wall += r.get("wall_s", 0.0)
    print(f"{'kind':18} {'median s/unit':>14} {'min':>10} {'max':>10} {'runs':>5} {'wall share':>10}")
    for kind, rows in sorted(per.items(), key=lambda kv: -tot_kinds[kv[0]]):
        rs = [x[0] for x in rows]
        print(f"{kind:18} {statistics.median(rs):14.3g} {min(rs):10.3g} {max(rs):10.3g} {len(rs):5d} "
              f"{tot_kinds[kind] / max(tot_wall, 1e-9):10.1%}")
    print("RATES = {")
    for kind, rows in sorted(per.items()):
        print(f'    "{kind}": {statistics.median(x[0] for x in rows):.3g},')
    print("}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
