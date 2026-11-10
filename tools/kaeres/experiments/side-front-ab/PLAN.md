<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# side-front-ab: side assignment without the human's sides (pre-registered plan)

Written 2026-11-09, before any full run (revised after the smoke, see the end). Ledger J42, J43, E113, E114; J44 is decided here.
Code: the commit `setup.sh` records.

## Question
Every placement and joint result inherits each part's side from the human layout (J45; stage 1 J43, E113). Production must never rely
on a human layout (user, 2026-11-09), so an inherited side is not an option for kae: kae has to assign sides itself. This experiment
measures what production-feasible side policies cost against the human's assignment, which here is only an **oracle reference**
(control C), and whether a real side-assignment move (J44) is needed to close a gap.

What a side costs: an assembled back is a second stencil and a second reflow, parts on the second side's underside must hold by surface
tension or glue, and every extra pass is handling that creates damage and warp. Against that, the back gives room, short return paths
to the parts it holds (decaps directly under BGAs), and a fan-out layer free of components.

## Mechanism
A pre-step of the method (`tools/research/place/side_front.py`) writes a copy of the task input with sides set by a policy, by pcbnew
(FOOTPRINT::Flip), and runs the usual staged method from that copy. The score is unchanged: `score.py` transplants position, rotation
and side. Never touched: anchored parts (locked or carrying Edge.Cuts: a fixed part's side is part of the task, like its position),
through-hole parts, test points, fiducials, mounting holes and logos.

## Arms (all joint-fixed, same wrapper as j1-chassis arm (a): `kae.joint.cli --max-iters 0 --no-modules`, restart `--resume 0.5 --final --check-placement`, 900 s x sqrt(fp/40); interleaved per board)
| Arm | Pre-step | Human side information used |
|---|---|---|
| C oracle | none (human sides) | every part: the reference production cannot have |
| P passives | two-pad SMD passives on the back moved to the front (smallest first, to a front fill of 0.70) | the other parts' sides |
| R rule | every movable SMD part assigned by rule: front first (passives, then smallest), the rest to the back once the front reaches 0.70 fill | none |

R is the production-feasible policy: one reflow when the parts fit, otherwise the largest parts on the back. P shows how much of a gap
passives alone close. Fill is the sum of courtyards (an upper bound on what they cover) over the board area.

## Boards: `boards.txt` (`select_boards.py`, seed `side-front-ab-2026-11-09`, verified by parsing each board)
300 boards in the `double_sided_assembly` or `back_heavy` suite with more than 10 back-side SMD parts and at most 1,000 pads: the 17
merit boards that qualify and 283 corpus boards from `usability.jsonl` (`usable_route_test`), one per `repo_family`, assembled courtyards
at most 85% of the outline. The J43 count of 43 merit boards also counted through-hole back parts, which are not an assembly decision.
Boards the task cannot be prepared for drop out of all arms. Results are reported per tag (`back_heavy`, fill bands, BGA boards).

## Metrics (arm vs C, paired per board, attempt 0)
Usual: `cp1`, `cpk` (= `cp1`, k = 1), completion, open connections, DRC errors per type (`errors_by_type`), legality (`legal`), CPU.
Own: flips, parts sent to the back, back SMD parts left, boards that reach one reflow, front fill before and after (each run's `KAE_SIDE`
line), checked against the output board's sides. Physics: decap Σu on `physics_inputs_ok` boards, above the noise floor
(`stage1/physics-noise/J21.md`, median ratio at n boards) only.

Noise: the A/A joint-loop twins (`aa-joint`; no staged A/A exists) move cp1 by 0.5 pp (95% CI -1.4 to +2.8) over about 200 boards,
total opens by 2.8%. Paired over 300 boards, a cp1 difference of about 4.5 pp (paired SE 2.2-2.6 pp with 15 to 20% discordant pairs) and
an opens ratio of about 1.04 are the visible limit. A bound counts as met only when the 95% CI of the paired difference lies inside it;
otherwise the answer is undecided and the experiment extends to the rest of the qualifying pool (about 1,700 boards). Expected cost, as
information: about 450 CPU-h.

## Decision rule (pre-registered)
- **R is the side policy**: if R's opens are not more than +5% against C, cp1 not lower by more than 3 pp and legality not lower by more
  than 3 pp, on all boards and on the merit subset, R becomes kae's side assignment (one reflow when the parts fit); no annealer move needed.
- **The oracle carries information**: if R is worse than C beyond those bounds, the human's sides held something R lacks. Then J44 (a
  side move in the annealer, priced on routing and on the assembly cost of a second side) is worth building, with the R-C gap as its
  target. If P is within the bounds and R is not, the information sits in the non-passive parts' sides: J44 starts with those.
- **Heterogeneity**: if at least 15% of boards have R opens lower than C by 20% or more and at least 15% higher by 20% or more, a
  per-board choice has gains no fixed policy reaches: J44 is worth building either way.

No default changes from this experiment alone: the output is a recommendation and a report.

## Smoke and revision (2026-11-09, before any full run)
`side-front-smoke` (3 boards, code 9324fac, arms C, P and S = every back SMD to the front with overflow kept on the human's back) checked
the plumbing: every run valid and scored by KiCad, flips present in the output boards (back SMD parts C/P/S: 16/8/3, 17/15/0, 24/1/0), no
copied human copper (`copy` not suspect). On sdtv2csi, all 24 back parts on the front left 15-16 open against 10. S was replaced by R, which
uses no human side; the list grew from 150 to 300 boards from the suites.
