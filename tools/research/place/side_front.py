#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Force parts of a place task's input onto the front: the side assignment experiment's pre-step.

    side_front.py --input IN --output OUT --arm passives|smd [--max-fill F] [--report FILE]

A place or joint method inherits every part's side from the human layout (the input keeps it,
the placer never changes it). This writes a copy of IN with back-side parts flipped to the
front before the placer sees them, so the method assigns no side and the human's assignment
is withdrawn for those parts. A flip is a pose change (score.py transplants position,
rotation and side), so scoring is unchanged and nothing here touches it.

What may flip (`is_flippable`): a footprint on the back, with pads, none of them drilled,
not anchored (locked or carrying Edge.Cuts, which the scorer requires unmoved), and not a
test point, fiducial, mounting hole or logo (those have a side for a reason that is not
layout: a bed of nails or a fixture reaches them, and they carry no assembled part).

  passives  two-pad SMD passives (R, C, L, D, F, FB, Y): the case that costs an assembler
            a second reflow most cheaply removed
  smd       every flippable part
  rule      no human side at all: every assembled SMD part that may move (front or back) is assigned by
            rule, front first in the same order, and the parts that do not fit the cap go to the back
            (so a board that does not fit keeps its largest parts on the back, whatever the human did)

Order: passives first, then the rest, smallest courtyard first. A flip is skipped when it
would take the courtyards drawn on the front past `max_fill` of the board area (sum of
courtyards, so an upper bound on what they cover): the front is not assumed to have room.
What stays on the back is listed in the report; a board that keeps no back-side SMD part
needs one reflow.

The report (and a `KAE_SIDE {json}` stdout line) gives the counts, the fill, and whether the
board can now be built in one reflow. Report-only: nothing reads it back.
"""
import argparse
import json
import re
import shutil
import sys
from pathlib import Path

ARMS = ("passives", "smd", "rule")
NOT_ASSEMBLED = re.compile(r"^(TP|FID|H\d|MH|LOGO|REF|G\d)", re.I)
PASSIVE_PREFIXES = ("R", "C", "L", "D", "F", "FB", "Y")
PROJECT_SUFFIXES = (".kicad_pro", ".kicad_prl", ".kicad_dru", ".kicad_sch")


def ref_prefix(ref):
    return ref.rstrip("0123456789")


def is_smd(fp):
    return bool(fp.pads) and all(not p.drill and p.kind in ("smd", "connect") for p in fp.pads)


def is_passive(fp):
    return is_smd(fp) and len(fp.pads) == 2 and ref_prefix(fp.ref).upper() in PASSIVE_PREFIXES


def is_movable_smd(fp):
    return is_smd(fp) and not fp.locked and not fp.edge_cuts and not NOT_ASSEMBLED.match(fp.ref)


def is_flippable(fp):
    return (fp.side == "B" and is_smd(fp) and not fp.locked and not fp.edge_cuts
            and not NOT_ASSEMBLED.match(fp.ref))


def courtyard_area(fp):
    """Area of the part's courtyard, else the box around its pads (with 1 mm margin each side)."""
    a = sum(c.area for c in fp.courtyard or [])
    if a > 0.0:
        return a
    if not fp.pads:
        return 0.0
    xs, ys = [p.x for p in fp.pads], [p.y for p in fp.pads]
    return (max(xs) - min(xs) + 2.0) * (max(ys) - min(ys) + 2.0)


def rule_sides(parts, board_area, max_fill):
    """parts: [(key, area, passive?, side, movable smd?)]. The rule arm: {key: 'F' | 'B'} for every movable SMD
    part, front first (passives, then smallest), the rest to the back once the front reaches max_fill. Fixed
    parts keep their side and count toward the fill."""
    budget = max_fill * board_area - sum(a for _, a, _, side, ok in parts if side == "F" and not ok)
    out = {}
    for key, area, _, _, _ in sorted((p for p in parts if p[4]), key=lambda p: (not p[2], p[1], p[0])):
        if area <= budget:
            out[key] = "F"
            budget -= area
        else:
            out[key] = "B"
    return out


def choose_flips(parts, board_area, arm, max_fill):
    """parts: [(key, area, passive?, side, flippable?)]. Returns (keys to flip, keys capped, fill before, fill after)."""
    front = sum(a for _, a, _, side, _ in parts if side == "F")
    candidates = [p for p in parts if p[4] and (arm == "smd" or p[2])]
    # passives first, then by area: the cheapest second-reflow removal, and small parts fit gaps
    candidates.sort(key=lambda p: (not p[2], p[1], p[0]))
    budget = max_fill * board_area - front
    flips, capped = [], []
    for key, area, _, _, _ in candidates:
        if area <= budget:
            flips.append(key)
            budget -= area
        else:
            capped.append(key)
    before = front / board_area if board_area > 0 else 0.0
    after = (front + sum(p[1] for p in candidates if p[0] in set(flips))) / board_area if board_area > 0 else 0.0
    return flips, capped, before, after


def board_area(board):
    return sum(o.area for o in board.outline or [])


def copy_project_files(src, dst):
    """Copy the project files of src beside dst, under dst's stem (KiCad reads the rules from them)."""
    src, dst = Path(src), Path(dst)
    for s in PROJECT_SUFFIXES:
        f = src.with_suffix(s)
        if f.is_file():
            shutil.copyfile(f, dst.with_suffix(s))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--arm", choices=ARMS, required=True)
    ap.add_argument("--max-fill", type=float, default=0.7,
                    help="stop flipping when the front's courtyards reach this share of the board area")
    ap.add_argument("--report")
    a = ap.parse_args(argv)
    from kae.board import pcbnew_io
    from kae.board.kicad_file import load

    board = load(a.input)
    by_key = {fp.uuid: fp for fp in board.footprints}
    area = board_area(board)
    if a.arm == "rule":
        parts = [(fp.uuid, courtyard_area(fp), is_passive(fp), fp.side, is_movable_smd(fp)) for fp in board.footprints if fp.pads]
        sides = rule_sides(parts, area, a.max_fill)
        flips = [u for u, sd in sides.items() if sd != by_key[u].side]
        capped = [u for u, sd in sides.items() if sd == "B"]
        front = sum(p[1] for p in parts if (sides.get(p[0]) or p[3]) == "F")
        before = sum(p[1] for p in parts if p[3] == "F") / area if area > 0 else 0.0
        after = front / area if area > 0 else 0.0
        poses = {u: (by_key[u].x, by_key[u].y, by_key[u].rot, sides[u]) for u in flips}
    else:
        parts = [(fp.uuid, courtyard_area(fp), is_passive(fp), fp.side, is_flippable(fp)) for fp in board.footprints if fp.pads]
        flips, capped, before, after = choose_flips(parts, area, a.arm, a.max_fill)
        poses = {u: (by_key[u].x, by_key[u].y, by_key[u].rot, "F") for u in flips}
    out = Path(a.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    if poses:
        res = pcbnew_io.write_poses(a.input, a.output, poses)
    else:
        shutil.copyfile(a.input, a.output)
        res = dict(moved=0, flipped=0)
    copy_project_files(a.input, a.output)
    back_smd = [fp for fp in board.footprints if fp.side == "B" and is_smd(fp) and not NOT_ASSEMBLED.match(fp.ref)]
    side_after = {fp.uuid: (poses[fp.uuid][3] if fp.uuid in poses else fp.side) for fp in board.footprints}
    left = sum(1 for fp in board.footprints if side_after[fp.uuid] == "B" and is_smd(fp) and not NOT_ASSEMBLED.match(fp.ref))
    report = dict(arm=a.arm, max_fill=a.max_fill, flips=len(flips), capped=len(capped), back_smd_before=len(back_smd),
                  back_smd_after=left, single_reflow=left == 0, front_fill_before=round(before, 4),
                  front_fill_after=round(after, 4), board_area_mm2=round(area, 2), flipped_refs=sorted(by_key[u].ref for u in flips), to_back=sum(1 for u in poses if poses[u][3] == "B"),
                  capped_refs=sorted(by_key[u].ref for u in capped), written=res.get("flipped", 0))
    if a.report:
        Path(a.report).write_text(json.dumps(report))
    print("KAE_SIDE " + json.dumps(report), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
