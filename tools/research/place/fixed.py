# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The fixed-part classifier (kae.place.fixed.classify: the benchmark's mech_rules) on the
human boards: per class and split, parts and boards, the deciding rules, and the parts a rule
frees (test points, jumpers, trimmers, programming / debug headers, ...) with why.

    python tools/research/place/fixed.py kae-work-v3/tasks [--json rows.json] [--show N]
"""
import argparse
import collections
import glob
import json
import os
import sys

from kae.board.kicad_file import load
from kae.place import fixed


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("tasks")
    ap.add_argument("--json")
    ap.add_argument("--show", type=int, default=6)
    a = ap.parse_args(argv)
    rows = []
    per = collections.Counter()
    boards = collections.defaultdict(set)
    rules = collections.defaultdict(collections.Counter)
    freed = collections.defaultdict(list)
    for d in sorted(glob.glob(os.path.join(a.tasks, "*"))):
        bp = os.path.join(d, "route", "input", "board.kicad_pcb")
        if not os.path.exists(bp):
            continue
        tid = os.path.basename(d)
        split = json.load(open(os.path.join(d, "task.json"))).get("split", "?")
        try:
            got, free = fixed.classify(load(bp), with_free=True)
        except Exception as e:      # noqa: BLE001
            print(f"{tid}: {type(e).__name__}: {e}", file=sys.stderr)
            continue
        for c in got.values():
            per[(c["cls"], split)] += 1
            per[(c["cls"], "all")] += 1
            boards[c["cls"]].add(tid)
            rules[c["cls"]][c["why"].split(":")[0]] += 1
            rows.append(dict(id=tid, split=split, **c))
        for c in free.values():
            what = c["why"].split("(")[0].replace("exclude:", "").strip()
            freed[what].append((tid, c["ref"], c["lib_id"], c["value"], c["why"]))
    if a.json:
        json.dump(rows, open(a.json, "w"), indent=0)
    print(f"{'class':12s} {'A':>5s} {'B':>5s} {'C':>5s} {'all':>5s} {'boards':>6s}  deciding rule")
    for cl in fixed.CLASSES:
        print(f"{cl:12s} {per[(cl, 'A')]:5d} {per[(cl, 'B')]:5d} {per[(cl, 'C')]:5d} {per[(cl, 'all')]:5d} "
              f"{len(boards[cl]):6d}  {dict(rules[cl].most_common())}")
    for k, v in sorted(freed.items(), key=lambda kv: -len(kv[1])):
        print(f"\nfreed: {k}: {len(v)}")
        for x in v[:a.show]:
            print("   ", x[0][:40], x[1], x[2][:50], x[3][:20], "|", x[4][:90])


if __name__ == "__main__":
    main()
