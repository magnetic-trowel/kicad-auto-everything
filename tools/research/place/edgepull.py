# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""How often the human puts each class of connector / mounting hole at the board edge.

For every footprint of an edge class (kae.place.edgepull.fp_class) on the human placement
(the route task's input), the courtyard's distance from the board edge, and, where the
footprint has an inferable mating side (kae.place.edgepull.mating), whether that side faces
the nearest edge. Per class and split: count, share within EDGE_MM, share facing out.
Classes at >= 90% within EDGE_MM in every split with enough parts are the ones the edge
term (anneal_args w_edge) turns on by default.

    python tools/research/place/edgepull.py kae-work-v3/tasks [--json out.json] [--movable]
"""
import argparse
import collections
import glob
import json
import os
import sys

import shapely

from kae.board.kicad_file import load
from kae.place import edgepull, stubs


def board_rows(task_dir, movable_only=False):
    tj = json.load(open(os.path.join(task_dir, "task.json")))
    b = load(os.path.join(task_dir, "route", "input", "board.kicad_pcb"))
    if not b.outline:
        return []
    outline = shapely.union_all(b.outline)
    brief = stubs.make_brief(b)[0]
    kinds = {u: v["kind"] for u, v in brief["parts"].items()}
    rows = []
    for f in b.footprints:
        if movable_only and f.locked:
            continue
        cl = edgepull.fp_class(f, kinds.get(f.uuid, ""))
        if cl is None:
            continue
        d = edgepull.edge_distance(outline, f)
        if d is None:
            continue
        tht = any(pd.kind == "thru_hole" for pd in f.pads)
        rows.append(dict(id=tj["id"], split=tj.get("split", "?"), ref=f.ref, cls=cl, tht=tht, locked=f.locked,
                         d=round(d, 2), out=edgepull.faces_out(outline, f)))
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("tasks")
    ap.add_argument("--json")
    ap.add_argument("--movable", action="store_true")
    a = ap.parse_args(argv)
    rows = []
    for d in sorted(glob.glob(os.path.join(a.tasks, "*"))):
        if os.path.exists(os.path.join(d, "route", "input", "board.kicad_pcb")):
            try:
                rows += board_rows(d, a.movable)
            except Exception as e:      # noqa: BLE001
                print(f"{os.path.basename(d)}: {type(e).__name__}: {e}", file=sys.stderr)
    if a.json:
        json.dump(rows, open(a.json, "w"), indent=0)
    agg = collections.defaultdict(lambda: [0, 0, 0, 0, set()])
    for r in rows:
        for key in ((r["cls"], r["split"]), (r["cls"], "all")):
            g = agg[key]
            g[0] += 1
            g[1] += r["d"] <= edgepull.EDGE_MM
            if r["out"] is not None:
                g[2] += 1
                g[3] += bool(r["out"])
            g[4].add(r["id"])
    print(f"{'class':16s} {'split':5s} {'n':>4s} {'boards':>6s} {'edge%':>6s} {'mating':>6s} {'out%':>5s}")
    for (cl, sp), (n, e, m, o, ids) in sorted(agg.items()):
        print(f"{cl:16s} {sp:5s} {n:4d} {len(ids):6d} {100 * e / n:6.0f} {m:6d} "
              f"{(100 * o / m if m else float('nan')):5.0f}")


if __name__ == "__main__":
    main()
