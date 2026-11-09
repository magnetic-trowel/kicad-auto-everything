#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Boards of the placement-routability experiments (see PLAN.md): placements that fail to route.

Primary: every merge3-ab board where the staged arm left connections open, the human layout has
none open, and the bridge on the human placement left fewer than staged (the placement costs
opens), less the two the E107 attribution blames on rule-area barriers, plus mystorm and ubertooth
(E107 placement-caused; their human layouts have 3 and 2 open, so they miss the first rule).
Secondary: boards tagged route_demand.hard/extreme or pad_density.very_dense/extreme where the
staged arm left opens, with no more than 3 open on the human layout (more is the board's own)
and at most 2000 pads. local_hotspot is left out (an unverified heuristic). Writes boards.txt
(all), boards-primary.txt, boards-secondary.txt; deterministic.
"""
import csv
import json
import os
from pathlib import Path

EXP = Path(os.path.expanduser("~/kae-baselines/experiments/merge3-ab/results.csv"))
TAGS_DIR = Path(os.environ.get("KAE_BOARD_TAGS", f"/var/tmp/{os.environ.get('USER', '')}/board-tags"))
SUITES = TAGS_DIR / "suites"
TAGS = ("route_demand.hard", "route_demand.extreme", "pad_density.very_dense", "pad_density.extreme")
STAGED, BRIDGE = "kae staged main screen final (restarts)", "kae bridge main (restarts)"
BARRIER = ("davang-breakout-boards", "gregification-beems")  # E107: rule areas, not the placement
ADD = ("folknology-mystorm-mystorm", "greatscottgadgets-ubertooth-ubertooth-one")

by = {}
for r in csv.DictReader(open(EXP)):
    by.setdefault(r["board"], {})[r["method"]] = r
tagged = set()
for t in TAGS:
    tagged |= {x.strip() for x in open(SUITES / f"{t}.txt") if x.strip()}
usable = {}
for line in open(TAGS_DIR / "structural" / "usability.jsonl"):
    d = json.loads(line)
    usable[d["id"]] = d.get("usable_route_test")


def n(d, m):
    return int(d[m]["unconnected"] or 0)


primary, secondary = [], []
for b, d in sorted(by.items()):
    if not all(m in d for m in (STAGED, BRIDGE, "human")) or not usable.get(b):
        continue
    so, bo, hu = n(d, STAGED), n(d, BRIDGE), n(d, "human")
    pads = int(d[STAGED]["pads"] or 0)
    if b.startswith(BARRIER):
        continue
    if b in ADD or (so > 0 and hu == 0 and so > bo):
        primary.append(b)
    elif so > 0 and b in tagged and hu <= 3 and pads <= 2000:
        secondary.append(b)
here = Path(__file__).resolve().parent
(here / "boards-primary.txt").write_text("".join(x + "\n" for x in primary))
(here / "boards-secondary.txt").write_text("".join(x + "\n" for x in secondary))
(here / "boards.txt").write_text("".join(x + "\n" for x in sorted(primary + secondary)))
print(len(primary), len(secondary))
