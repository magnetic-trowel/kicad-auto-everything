# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Gate: kae.place's exact check must not flag the human placement where KiCad does not.

For every task of a split, the reference board (human poses) is read into a placement
Problem and checked by kae.place.exact with every part in scope. Each finding type is
compared with KiCad's DRC report of the same reference board (reference/drc.json, made by
kaebench prepare): a type kae reports where KiCad has no error of that type is a false
positive of the model (it would make the placer avoid spots KiCad allows, or call a legal
board illegal). pad_outside is compared with the pads the reference record lists outside;
kae-only types with no KiCad counterpart (over_cutout, kicad_feedback) are reported apart.

    python tools/research/place/humangate.py --tasks kae-work-v3/tasks --split C [--ids a,b] [--out FILE]

Exit status 1 when any task has a false positive.
"""
from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

KICAD_TYPES = {"courtyards_overlap", "clearance", "hole_clearance", "hole_to_hole", "solder_mask_bridge",
               "items_not_allowed", "copper_edge_clearance", "npth_inside_courtyard", "pth_inside_courtyard",
               "shorting_items"}


def check_task(tdir):
    from kae.board.kicad_file import load
    from kae.place.exact import ExactModel
    from kae.place.problem import Problem
    from kae.place.state import State
    t = json.loads((tdir / "task.json").read_text())
    ref = load(tdir / "reference" / "board.kicad_pcb")
    P = Problem.build(ref)
    P.set_margin(0.0)
    st = State(P)
    for p in P.parts:
        if p.movable:
            st.X[p.i], st.Y[p.i] = P.grid_of(p.x0, p.y0)
            st.K[p.i] = min(range(len(p.rots)), key=lambda k: abs(((p.rots[k].rot - p.rot0) + 180) % 360 - 180))
    # judge the true poses, not their grid snap: put every part exactly where the human has it
    for p in P.parts:
        if p.movable:
            p.movable_saved = True
    E = ExactModel(P, st)
    for p in P.parts:
        E.sh[p.i] = E._shapes(p.i, (p.x0, p.y0, p.rot0, p.fp.side))
        E.env[p.i] = E.sh[p.i]["env"]
    found = E.check(parts=range(len(P.parts)), max_items=100000)
    drc = json.loads((tdir / "reference" / "drc.json").read_text())
    kicad = collections.Counter(v["type"] for v in drc.get("violations", []) if v.get("severity") == "error")
    ours = collections.Counter(v["type"] for v in found)
    allowed = (t.get("reference") or {}).get("pads_outside") or {}
    fp = {}
    for ty, n in ours.items():
        if ty == "pad_outside":
            out = collections.Counter(P.parts[v["parts"][0]].uuid for v in found if v["type"] == "pad_outside")
            over = {u: c for u, c in out.items() if c > allowed.get(u, 0)}
            if over:
                fp[ty] = sum(over.values())
        elif ty in KICAD_TYPES and kicad.get(ty, 0) == 0:
            fp[ty] = n
    examples = [v for v in found if v["type"] in fp][:6]
    return dict(id=tdir.name, ours=dict(ours), kicad=dict(kicad), false_positive=fp,
                examples=[(v["type"], v["refs"], v["detail"]) for v in examples])


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tasks", default="kae-work-v3/tasks")
    ap.add_argument("--split", default="C")
    ap.add_argument("--ids")
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    want = set(a.ids.split(",")) if a.ids else None
    rows = []
    for tj in sorted(Path(a.tasks).glob("*/task.json")):
        t = json.loads(tj.read_text())
        if t.get("split") != a.split or (want and t["id"] not in want):
            continue
        try:
            r = check_task(tj.parent)
        except Exception as e:      # noqa: BLE001 - one unreadable task must not end the gate
            r = dict(id=t["id"], error=f"{type(e).__name__}: {e}")
        rows.append(r)
        if r.get("false_positive") or r.get("error"):
            print(json.dumps(r), flush=True)
    bad = [r for r in rows if r.get("false_positive")]
    print(f"{len(rows)} tasks, {len(bad)} with false positives, {sum(1 for r in rows if r.get('error'))} errors")
    if a.out:
        Path(a.out).write_text(json.dumps(rows, indent=1))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
