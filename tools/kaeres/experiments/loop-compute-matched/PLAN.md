<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# loop-compute-matched: is integrated place-and-route worth its compute against restarting? (pre-registered)

Written 2026-11-10, before any run of this experiment. Follows `loop-window-bench-v2` (`docs/research/joint/window-budget-2611.md`):
two budgets of window time cut open connections 16 % against the joint loop's natural split, at 2.8 times the CPU. That
extra compute could instead buy restarts, which is how the merit runs spend it. This pair asks which use of the same compute is better.

## Arms (`setup.sh`, commit f2f4151, joint-fixed, both on one process lane, same harness timeout 3.15 x B, B = 900 s x sqrt(fp/40))
- **W, joint + windows:** `kae.joint.cli run --time B --set window_budget_factor=2 --set skip_unfixable_drc=0`. This is the bench's `w2 ctl` recipe, run again here so that both arms share the same days and load.
- **R, staged + restarts:** J1's staged arm (`--max-iters 0 --no-modules`) under `restart.py --parallel 1 --time 3.15 B` with J1's other wrapper flags (`--first-s 300 --scale-first --slack 1.15 --resume 0.5 --final lastmile --check-placement`). Attempts run one after another in the same wall time.

Seed 0, k = 1, interleaved in the kaeq timed class.

## Boards
- **First batch (69):** the 40 window-bench boards and the 29 boards of its extension (the 31 minus the 2 smoke boards). These are boards where kae's joint loop leaves connections open, one per repo family.
- **Extension (`boards-extension.txt`):** qualified, usable corpus boards tagged `route_demand` hard or extreme, outside the merit suite, one per new repo family, in sha256(`loop-compute-matched-2026-11-10`, id) order.
  - The tag was spot-checked before use: on merit boards the joint loop left opens on 21 of 24 hard or extreme boards, against 25 of 124 easy ones.
  - The extension runs in batches of 60 while the primary is undecided.

## Outcomes and decision
- **Primary:** open connections, paired per board. `d = (o_W − o_R) / (o_W + o_R + 1)`, sign-flip test.
  - W wins if mean `d` < 0 with p < 0.05 and total opens at least 3 % lower. R wins on the mirror condition.
  - Anything else is undecided and triggers the next extension batch. After the corpus pool is used up, the verdict is reported as undecided.
- **Compute match:** the two arms' total CPU must be within a factor of 1.25. If not, the comparison is not compute-matched: report it, and rerun the cheaper arm with its timeout scaled to match before calling a winner.
- **Secondary, reported:** cp1 (clean), completion, DRC errors total and per type, CPU per board, restart attempts used, loop windows and kept, and physics on boards both arms route fully, above the J21 floor, when there are at least 20 such boards.

## Addendum, before the full submission (2026-11-10, after a 2-board smoke)
The smoke ran two boards of the first batch (circuitmonkey class-d amp, tinkerforge motion detector), which stay in the batch. The plumbing works: both arms finished within the timeout, KiCad scored them, the joint report holds the window deadline, and the wrapper ran 12 and 26 attempts one at a time.
The smoke showed a design fact that the compute rule above did not foresee. The joint loop stops when it has no window left (248 s on one board), while the wrapper spends its whole allowance looking for a clean board (2,592 s). So actual CPU cannot be matched by scaling a timeout. The rule changes before any decision data:
- **Compute is matched by allowance.** Both arms get the same timeout, each may stop early, and the CPU each actually used is reported per board and in total.
- The opens rule decides at equal allowance. The verdict states the CPU ratio: a W win at lower CPU is a win at lower compute; an R win at higher CPU is a win at equal allowance, not at equal CPU.
- The rule about rerunning the cheaper arm is withdrawn.
