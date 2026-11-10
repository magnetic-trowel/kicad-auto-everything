<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# bus-pose-ab: kae baseline on bus-rich boards and the bus pose compiler (pre-registered plan)

Written 2026-11-09, before any run of this experiment. Campaign items B3 and C2 (X1, X2 of the placement study, kept
in the bus campaign notes). Mechanism: `kae/src/kae/place/buspose.py`. Research page: `docs/research/placement/bus-pose-2611.md`.

## Questions
1. (B3) On boards with memory and wide IC-to-IC buses, how far is kae's staged placement from the human's on bus
   metrics (planar share, layers needed, foreign crossings per line, bus length), and how many bus lines stay open after
   routing with the Freerouting fork? The stored kae placements barely cover these boards.
2. (C2) From pin tables alone, choosing each bus end's rotation so the bus is planar and short: does it lower vias per
   bus line and open bus lines, without raising total open connections or DRC errors, and which of three
   placements of the pass does it best: a final pass after legalization, planarity first or length first, or the
   choice made at the seed and held?

## Boards (`boards.txt`, from `select_boards.py`, seed `bus-pose-ab-2026-11-09`)
`usable_route_test` boards of the board-tag sources, one per `repo_family`, at most 2,000 pads
(as `array-macro-ab`), in two pools ordered by a seeded hash: 80 from `bus_ddr` and 60 with an IC-to-IC bus of width 8 or more
(neither end a header, FFC/FPC or board-to-board connector, per the bus census), not in the first pool. 140 boards. The mechanism filter
(an IC-to-IC or memory bus the compiler's own detector finds, both ends movable with at least two turns) runs on the
placed output of the control: boards with no detected movable bus end are reported as outside the mechanism and excluded from
tests. Task kind `joint-fixed`: mechanical parts (connectors, holes) are locked at the human pose, so a connector end of a bus is
given, not chosen; the compiler conditions on it.

The joint tasks' input carries, from the human layout: the net-to-pin assignment (pin swaps the designer made for
that layout), the side of each part, the board's zones and stackup, and the fixed mechanical parts' poses.
None of it is read by the compiler beyond being the input netlist and fixed poses (see Limits).

## Arms and chassis
All arms at one commit, knobs with `--set` (a change per arm), interleaved in each board's kaeq job, timed class,
one placement and one route: `kae.joint.cli run --max-iters 0 --no-modules`, budget 900 s x sqrt(fp/40), attempts 0-2
(seeds 0-2, k = 3). No restart portfolio, as in `placement-routability`, so the placement's effect is not hidden behind
a portfolio choosing among seeds. Freerouting fork 2e1125a as the bridge's engine, one run per placement and seed (each seed is
a different placement, not a seed sweep of the router). No human layout in any arm's input.

| Arm | Flags |
|---|---|
| control | none (also the B3 baseline) |
| final-planar | `--set bus_pose=final` |
| final-length | `--set bus_pose=final --set bus_pose_mode=length` |
| seed-final | `--set bus_pose=seed` (rotation chosen at the seed from pin tables and held; then the final pass, planarity first) |

## Metrics
`kaeres exp report`: `cp1`, `cpk`, completion, open connections (total and paired), DRC errors total and per type, legal placements,
CPU, wirelength, vias. Bus metrics by arm, from `analyze.py` (`tools/research/bus_pose/busmetrics.py`, the campaign's own
measure, on the buses of the human board's netlist, detection is netlist and footprint geometry only): open lines per bus, vias per
bus line, layers needed (LDS), LIS planar share, full-planar share of buses, foreign ratsnest crossings per line, straight-line
bus length. Per-arm stats of the pass (`stages.place.bus_pose` in the joint report: buses, turns proposed, grid and exact rejections,
physics vetoes). Physics only above its noise floor (J21).

B3 reading (control vs the human placement, which is a measurement here, in no arm's input): ratios of bus length, planar share and
foreign crossings per line on boards where kae placed legally, by pool (DDR, IC-IC wide). Report per-board medians and n.
If kae matches the human on planar share and length within the seed noise, the rotation gap is not on these boards: drop C2's claim
of a gap and report the null.

## Size
Paired seed noise of the per-board sum of bus open lines (log1p, kae staged control, attempts 0/1, 20 merit boards with buses in the stored data):
SD of the difference 0.58 at k = 1, so about 0.33 for the mean of 3 seeds (SD/sqrt(3)). Detecting a 10% change in that metric at
80% power (two-sided 5%) needs about 85 boards. 140 boards leave room for boards with no movable bus end, placements that fail
legality and a split by pool (DDR, IC-IC). Vias per bus line has larger noise in the stored data (about 1.15 at k = 1, heavy-tailed,
dominated by boards with no vias); the paired test handles it, and the planarity effect on vias can be small, so this is
the measurement the extension rule is for.

## Decision rule (each arm vs control, paired per board over the 3 seeds)
Primary metrics (sign-flip test, two-sided, 20,000 resamples, per-board means): `log1p(bus open lines)` and
`log(vias per bus line + 0.1)`, on boards inside the mechanism. An arm is adopted for a follow-up (not a default) only if:
vias per bus line falls at least 10% or bus open lines at least 10% with p < 0.05, total open connections do not rise (paired on
boards; the point estimate not above +3%) and no DRC error type rises beyond +5%, and legal placements do not fall and cp1 does
not fall beyond the noise floor (3 pp at n about 140). Otherwise it stays off.
Manipulation check required before reading the primary: the planar share (or layers needed) moves in the arm's own direction on bus
ends the pass actually turned; if the rotations did not change, the arm is uninformative and reported so, not a negative result.
One pre-registered extension: if an arm shows a 10% effect at p 0.05-0.2, seeds 3-5 are added once for that arm and control.

Default stays off in all cases (a default change is a separate decision, with the human's approval).

## Interactions, so the arms are not confounded
- `placement-routability` (crossing term `place_w_xing`, untangle, channels) and `array-macro-ab` (rigid series-bus and matrix blocks) are on
  their own branches; every arm here runs with them absent, so neither contributes to any arm difference, whatever their outcome. Both can
  touch the same bus (an array block pinned between two ICs; the crossing term also penalises a bus's own crossings quadratically).
  Their overlap with this suite: 5 of the 47 boards of `placement-routability` are in this suite, which is not a confound since
  no arm uses those knobs. Results here are "pose compiler alone" and must be re-tested when either lands: X3 of the campaign
  (each with this experiment's better arm) is that test; for array macros, the ordering (series rows pinned before the seed
  pose) must be decided there.
- Physics terms are the same in every arm. Bus lines' physics is reported, not optimised (no data-bus physics exists in the evaluator).
- The rule "turns may not worsen the place terms" (arms final-*, and the seed-final arm's final pass) means decoupling and other
  structures keep priority; the arms therefore cannot pay physics for bus quality except in seed-final, whose decaps are placed
  around the chosen rotation.

## Limits
What every board inherits from the human layout: net-to-pin assignment (the human chose swaps knowing the human
placement; if that assignment already favours the human's relative pose, part of what we call "rotation" is pin
swapping by the designer), side, zones, stackup, and the locked mechanical parts. The compiler reads only the netlist and footprints; the
human placement is a comparison only. Mirrors (side flips) are not tried: a part keeps its side (no flip move, ledger J42/J44).
Rotation angles are the four right angles only.

## Cost
At most 63 CPU-h per arm-seed if every board used its whole budget; expected 400-800 CPU-h for the 12 arm-seeds. Information, not a cap.

## Addendum, before the full submission (2026-11-10; smoke read, no result of the 140 boards seen)
- Smoke `bus-pose-ab-smoke` (3 boards outside the 140, k = 1): all 12 runs scored by KiCad (DRC evaluator afa09d34bc94), `valid` in every arm;
  placement errors identical across arms on each board (board-inherent: fixed parts' edge clearance, malformed courtyards, outline), so no turn added one.
  The knob took effect only where set: control logs no pass; final-planar turned 0, 0 and 4 parts (planar lines 0.475 -> 0.650 on the nixie board),
  final-length 1, 0, 1; seed-final turned 2, 0, 4 at the seed and held 3, 1, 6 parts. The physics veto refused 3, 0, 6 candidate turns; grid collisions 7, 0, 0-4; no exact
  finding and no joint revert.
- Clarification: in seed-final the final pass cannot turn a part whose rotation the seed held (`Part.rot_hold`), so it acts only on bus ends the seed did not hold.
  The arm is "seed choice, held"; its final pass is a no-op on held parts. Code unchanged; this text replaces "then the final pass" in the arm table.
- Legality of the placement study's turns (`tools/research/bus_pose/legal_summary.py`, 25 merit boards, the study's 263 moved bus-runs of kae staged): the
  best-planarity pair needs a turn on 170; 88 are legal (grid and exact check; none needed a nudge over 1 mm; 82 collide on the grid), and of those 64 worsen the place terms,
  so 24 pass the veto. Fully planar: now 37%, unconstrained best 50%, legal 43% (best legal pair of any rank 47%), legal and physics-safe 40%. Human placements: 43% -> 45%.
- Added as report-only (not in the decision rule), after the bus-alone result that bus completion is mostly escape and pin access: escape facing, the share of a bus's
  pads on the half of each end part that faces the other end (all ends, and ends with 64+ pads), per arm and paired.
