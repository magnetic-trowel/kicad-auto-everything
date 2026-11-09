<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Bus pose compiler: rotations of bus ends from pin tables (2026-11-09)

Status: built, default off; experiment `bus-pose-ab` created, smoke queued, no result yet.
Code: `kae/src/kae/place/buspose.py` (branch `exp-bus-pose`). Plan: `tools/kaeres/experiments/bus-pose-ab/PLAN.md`.

## Why
Whether a bus between two parts can run without crossings, and how long it is, depends mostly on the two
end parts' rotations: the pin order at one end against the pin order at the other is a table lookup on footprint
geometry. A study of stored placements (the bus campaign's placement notes) found kae's buses 1.21x the human's length
and less often planar (35% vs 43% of moved buses), and that turning the two ends in place would reach the human's
level (49% planar, 1.03x length). That study did not check whether the turns were legal.

## Mechanism
- **Detection** from the netlist and footprints only: two ICs (6+ connected pads, 4+ on signal nets) joined by 6+
  signal lines, a line traced through two-pin series parts. No placement is read.
- **Table** per bus and rotation pair: planar share (longest non-crossing subset of the lines, the better of a
  projection and a cyclic frame), layers needed (longest decreasing subsequence) and straight-line length, with
  each end turned about its pad centre.
- **Choice**, per connected set of parts sharing buses: exact enumeration up to 200,000 combinations, else
  coordinate descent. Planarity first (non-planar lines, then layers, then length) or length first.
- **Final pass** (`bus_pose=final`), after legalization and the exact repair: a turn is a candidate only if the
  placer's grid accepts it (nudged up to 1 mm), the exact polygon check finds nothing new, and the place terms
  do not worsen. The part's other nets pay: weighted HPWL, 2 mm per line made planar. Turned parts are
  re-checked together.
- **Seed** (`bus_pose=seed`): the same choice after the quadratic seed and spread, then held through the floorplan,
  annealer and legalizers (`Part.rot_hold`); the final pass still runs.
- Mirrors are not offered: a part keeps its side (no flip move).

## First look at legality (one board, not a result)
On polarfire-som (kae staged control, two seeds) most best-planarity turns of the SoC passed the grid and the exact
check. But every SoC turn worsened the place terms by 10-25 (decoupling loops), and several DRAM turns collided.
So the final-pass arms, which may not worsen physics, will refuse most SoC turns on memory boards. The seed arm is
the one that can turn the SoC, since its decaps are placed around the chosen rotation. The 25-board legality check
(`tools/research/bus_pose/legal_turns.py`, kaeq owner `bus-pose`, tag `legal-turns`) is queued.

## What it still inherits from the human layout
The compiler reads only the netlist and footprints. The benchmark task still carries the designer's net-to-pin
assignment, made for the human's placement; the campaign found the human assignment beats a random one in 79% of
IC-to-IC buses. It also carries each part's side, the zones and stackup, and, in joint-fixed tasks, the locked
connectors' poses. A rotation gain measured here is a gain given those.

## Interactions
The crossing term of `placement-routability` and the array macros of `array-macro-ab` are absent from every arm, so
they cannot confound it. Both act on the same buses: the crossing term counts a bus's own crossings
quadratically, and an array block is pinned between a bus's ends. Their joint test comes after both verdicts.
