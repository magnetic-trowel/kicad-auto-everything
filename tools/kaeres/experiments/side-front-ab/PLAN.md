<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# side-front-ab: does the human's side assignment matter? (pre-registered plan)

Written 2026-11-09, before any run. Ledger J42, J43, E113, E114; J44 is decided here. Code: the commit `setup.sh`
records.

## Question
Every placement and joint result inherits each part's side from the human layout (J45; stage 1 J43, E113). Does
withdrawing it cost routing, and how far can a board go towards one reflow? What a side costs: an assembled back
side is a second stencil and a second reflow, parts on the second side's underside have to hold by surface tension or
glue, and every extra side raises the handling that creates damage and warp. Against that, the back side also gives
room, shorter return paths to the parts it holds (decaps directly under BGAs), and a fan-out layer free of
components. A forced-front board trades two-side assembly for routing and placement density.

## Mechanism
A pre-step of the method (`tools/research/place/side_front.py`) writes a copy of the task input with back-side SMD parts
flipped to the front by pcbnew (FOOTPRINT::Flip) and runs the usual staged method from that copy. The score is
unchanged: `score.py` transplants position, rotation and side (a method may always have put a part on the other side).
Never flipped: anchored parts (locked or carrying Edge.Cuts), through-hole parts (their side does not need a reflow), test
points, fiducials, mounting holes and logos. Passives go first, then the rest, each smallest courtyard first, up to
a front fill cap of 0.70 of the board area (sum of courtyards, an upper bound on what they cover), so a board that
cannot hold everything keeps its largest back parts where they were.

## Arms (all joint-fixed, same wrapper as j1-chassis arm (a): `kae.joint.cli --max-iters 0 --no-modules`, restart `--resume 0.5 --final --check-placement`, 900 s x sqrt(fp/40); interleaved per board)
| Arm | Pre-step |
|---|---|
| C control | none (human sides) |
| P passives | flip the two-pad SMD passives |
| S smd | flip every flippable SMD part |

## Boards: `boards.txt` (`select_boards.py`, seed `side-front-ab-2026-11-09`, verified by parsing each board)
150 boards with more than 10 back-side SMD parts and at most 1,000 pads: the 17 merit boards that qualify, and 133 corpus boards from
`usability.jsonl` (`usable_route_test`) one per `repo_family`, assembled courtyards at most 85% of the outline. The J43 count
of 43 merit boards also counted through-hole back parts, which are not an assembly decision. Boards the task cannot be prepared for
(place-fixed round trip) drop from all arms alike. 146 of the 150 are in the structural tag `double_sided_assembly` (the other 4 have no assembled parts on the front), 122 in `back_heavy`; results are reported per tag.

## Metrics (arm vs C, paired per board, attempt 0)
Usual: `cp1`, `cpk` (= `cp1`, k = 1), completion, open connections, DRC errors per type (`errors_by_type`), legality (`legal`), CPU.
Own: flips, parts capped, back SMD parts left, boards that reach one reflow, front fill before and after, read from each
run's `KAE_SIDE` line (the input was written, so these do not depend on placement), and the board's own per-type DRC.
Physics: decap Σu on `physics_inputs_ok` boards, above the noise floor (`stage1/physics-noise/J21.md`, median ratio at
n boards) only.

Noise: the A/A joint-loop twins (`aa-joint`; no staged A/A exists) move cp1 by 0.5 pp (95% CI -1.4 to +2.8) over about 200 boards, total opens by 2.8%. Paired boards: at 150 boards
a cp1 difference under about 6 pp (paired SE with 15 to 20% discordant pairs: 3.2 pp) and an opens ratio under about 1.05 are not visible.
The bounds below are finer than that at 150 boards, so a bound counts as met only when the 95% CI of the paired difference lies inside it; a point estimate inside a bound with a wider CI is undecided, and the experiment then extends to 300 boards.

## Decision rule (pre-registered)
- **Force-front is free**: S arm opens not more than +5% against C, cp1 not more than -3 pp, legality rate not lower by more than 3 pp, on all
  boards and on the merit subset. Then "flip passives to the front when they fit" costs routing nothing for an assembly gain, and is worth
  offering as a method option (default unchanged, report-only until the commander asks for it).
- **The oracle helps**: S arm worse than C by more than those bounds on either metric. Then the human's sides carry information, and
  results on the inherited-side task are not a blank-sheet placement (J45 stands, with the number).
- **Is a real side-assignment move (J44) worth building?** Yes only if per-board spread gives it something to find: at least 15% of the boards
  have S opens lower than C by 20% or more, and at least 15% have S opens higher by 20% or more (the choice matters both ways, so a move has
  gains a fixed prestep cannot reach). A one-sided result (S uniformly better or worse) is answered by the prestep or by keeping the human's
  sides; a flip move would add a large search space for nothing.

No default changes from this experiment: the output is a recommendation and a report.
