<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# loop-polish: windows as polish after restarts, against restarts alone (pre-registered)

Written 2026-11-10, before any run of this experiment. This is the last window experiment unless it wins.
- `loop-compute-matched`: at equal allowance, staged + restarts left 1,170 fewer open connections than joint + windows (26 %, p 0.0001).
- The window-choice replay found no design with a plausible path to beating restarts by replacing them.
- What is left is windows on top of restarts.

## Arms (`setup.sh`, commit f2f4151, joint-fixed, one process lane, the same harness timeout 3.15 B for all)
- **R, restarts alone:** J1's staged arm (`--max-iters 0 --no-modules`) under `restart.py --parallel 1`, with J1's wrapper flags including `--final` lastmile.
  - It uses the whole allowance and is `loop-compute-matched`'s R, run again (`replicate=loop-polish`) so all arms share days and load.
- **P-late:** R, then the joint loop on the kept board through `restart.py --finish` (`kae.joint.cli run --start BEST --no-modules`, the bench's settings with J3 off).
  - The loop starts from the kept board: everything on it is locked, the first route only joins what is open, then windows and the loop's finish.
  - Its time, 30 % of the allowance, is reserved from the start, so the restarts get 70 %.
  - Why 30 %: in `loop-compute-matched`, R's kept board appeared after a median 68 % of its allowance (deciles 27 % … 98 %). So about 30 % is the time restarts typically spend after their best attempt, which is the time "they leave unused".
  - The polished board replaces the kept one only if KiCad ranks it no worse.
- **P-half:** as P-late, with 50 % of the allowance for the windows.

Seed 0, k = 1, interleaved in the kaeq timed class.

## Boards
- First batch: `loop-compute-matched`'s 69 boards (`boards.txt`), where the joint loop leaves connections open.
- Extension: its `route_demand` hard or extreme corpus boards (`boards-extension.txt`), in batches of 60 while undecided.

## Decision (each P arm against R, paired per board; two comparisons, so p < 0.025 each)
- **Primary:** open connections, `d = (o_P − o_R) / (o_P + o_R + 1)`, sign-flip test.
  - P wins if mean `d` < 0, p < 0.025, and total opens at least 3 % lower.
  - R wins on the mirror condition.
  - Otherwise undecided: run the next extension batch. After the pool is used up, report undecided.
- **Guards for a P win:** DRC errors and placement errors not above R's total by more than 3 %, and cp1 not lower.
- **Secondary, reported:** routed physics on boards all compared arms route fully. Modules valued in both, median ratio and sign-flip, judged against the J21 floor only when there are at least 38 such boards. Also CPU used per arm, R's attempts, P's windows and kept windows, and how often the polished board replaced the kept one.

## What follows
- If neither P arm wins, the windows line is concluded: windows do not earn their compute, neither instead of restarts nor on top of them. The research docs say so.
- If a P arm wins, its split becomes the candidate for the merit methods' wrapper, tested next on the merit suite.

## Addendum after the 2-board smoke (2026-11-10, before the other 67)
Plumbing only, and the two boards stay in the batch:
- All six runs finished inside the timeout, and KiCad scored them.
- In both P arms the wrapper ran the joint loop as its `--finish` pass on the kept board. It ran 326-1,379 s, and on one board its board was kept.
- The pass gets the time left after the restarts, at least its reserve. When the restarts' last attempt ends early it can get more than the nominal split (1,646 s on one board). This is how `restart.py --finish` works and is the same for both splits.
No rule changes.
