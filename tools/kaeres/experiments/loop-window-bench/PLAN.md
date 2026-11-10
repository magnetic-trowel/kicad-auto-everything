<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# loop-window-bench: does the joint loop's window stage pay when it has a real budget? (pre-registered)

Written 2026-11-09, before any run. Ledger J2, J3, J4, J5, J14, J15, J16. Code: `loop-exp` (main plus the loop-report change
and the four branches under test). Windows have never had a real budget: under the restart wrapper 18 of the first 24 J1 joint
boards got 0 windows, and in the 136 older reports the median was one window per board.

## Questions, each against its own control
1. J3: does skipping DRC types no part move can change (`skip_unfixable_drc`) free windows for spots a move can fix, at no loss?
2. J4: does a real legalizer budget (`legal_time`, the `replace_time`/`replace_share` cap lifted), with and without the incumbent
   fallback (`revert_illegal`), cut the 32 % of windows that die illegal after repair?
3. J2, J5, J14: inside the normal budget, do the window share (`route_share 0.4`, `finish_share 0.1`, `min_iter_s 25`), the floor
   alone (`min_iter_s 25`) or the first route's last mile (`first_last_mile=1`) change the result?
4. What does the loop gain as window budget grows, and where does it stop paying?

## Boards (`boards.txt`, `select_boards.py`, seeded)
The 71 boards of `placement-decide-joint` (joint leaves connections open on them; the mechanism exists there), all usable for
routing tests, all from different repo families. First batch: 40 boards, 10 per footprint quartile in sha256(seed, id) order.
`boards-extension.txt` (31 boards) is the pre-registered extension. J3 additionally runs on `loop-j3-unfixable` (below),
because only 34 of the 71 have a DRC type J3 filters. k = 1, seed 0.

## Arms (`setup.sh`; all `joint-fixed`, one run of `kae.joint.cli`, no restart wrapper, B = 900 s x sqrt(fp/40))
| Arm | Window budget | Flags | Tests |
|---|---|---|---|
| ctl | natural | J3 off | control for j2, j5, j14 |
| j2 | natural | `route_share=0.4 finish_share=0.1 min_iter_s=25` | J2 |
| j5 | natural | `min_iter_s=25` | J5 |
| j14 | natural | `first_last_mile=1` | J14 |
| w2 ctl | 2 B after iteration 0 | J3 off, old legalizer | control for w2 j3, j4t, j4 |
| w2 j3 | 2 B | J3 on | J3 |
| w2 j4t | 2 B | legalizer time and share | J4, time alone |
| w2 j4 | 2 B | ... plus `revert_illegal=1` | J4, full |
| w2 all | 2 B | J3 + J4 | together |
| w4 all | 4 B | J3 + J4 | anytime curve of question 4 |

Iteration 0 is the same in every window-bench arm of a board (same seed and shares; only wall-clock binding can differ). There is
no restart wrapper because it hides what is measured here: the J1 reports show wrapped first waves leave no time for windows.
Arms run interleaved in the kaeq timed class, same boards, same day. Counted-work budgets are not on main; a loaded host costs each
arm alike. J1 decides the base method separately; these results are against their own controls and hold under either verdict.

## Outcomes
Per pair, from `results.csv` and each run's report (`adapter.log.gz` holds the loop's JSON): `cp1`, `cpk`, completion, open connections
(total and paired per board), DRC errors total and per type, CPU. From the reports: windows per board, kept windows, stop reason,
windows by reason, windows ending "illegal after repair". Routed physics on boards both arms route fully, above the J21 floor
(median Σu ratio, n 20: 1.12, 30: 1.08, 38: 1.06).

## Decision rules (paired, per board)
- **Opens.** Unit `d = (o_arm − o_ctl) / (o_arm + o_ctl + 1)`. Better: mean `d` < 0 with sign-flip p < 0.05 and total opens at least 3 % lower. Same for worse. A/A noise on total opens is 2.8 % (`aa-joint`).
- **Errors, cp1.** Must not get worse beyond noise (cp1 noise at n = 40 is about 8 pp, so cp1 is reported, not decided).
- **J3 passes** if windows opened on fixable spots rise (reports), and opens and errors are not worse.
- **J4 passes** if "illegal after repair" falls well under the control's rate (at least by half), kept windows rise, opens no worse.
- **J2, J5, J14 pass** on opens better without errors worse, on the natural budget; J2 is then split into J5 and the shares by arm j5.
- **Question 4.** Read from `w4 all`'s iterations (cumulative window seconds against open connections and errors of the incumbent, per board), medians over boards, at 0.5, 1, 2 and 4 B. It stops paying where the median gain from doubling is under one open connection and under 5 % of the board's opens.

If a primary is undecided at 40 boards, run `boards-extension.txt` as a second batch. Anything else undecided: report it as undecided.

## Costs (information only)
Natural arms about B each, window arms about 3-5 B each, on an average B of about 1,300 s, less when a board finishes early: about 200-300 CPU-h for the first batch.

## Addendum, before the full submission (2026-11-09, after the smoke; no run of the 40 boards exists)
Smoke: experiment `loop-window-bench-smoke`, arms `ctl`, `w2 ctl`, `w2 all`, on two boards of `boards-extension.txt` (sparkfun-edison-micro-sd-block, protocentral-tinyecg), which are therefore dropped from the extension batch. Read as plumbing only: all six runs finished inside their timeouts, KiCad scored them, the flags reached the loop (`skip_unfixable_drc`, `window_deadline_s`, greedy no longer out of time and parts reverted with the J4 flags), and the stored logs hold the full loop report. No decision rule, arm or board set changed.
One thing to read for in the results: with `revert_illegal` on, a window can still end illegal after all its moved parts are restored, when the incumbent poses are themselves grid-illegal (seen on a board with 64 `copper_edge_clearance` errors). "Illegal after repair" is reported as is; J4's pass rule is unchanged.

## Addendum 2, before the full submission (2026-11-09; no run of the 40 boards exists)
The first full submission (commit b086071) was cancelled before any job started: the tight-part scan showed the anchoring also caught body-only parts such as logos. Anchoring now takes only parts with a courtyard, and arms, boards and rules are unchanged. Methods are at commit f2f4151 and the experiments are named `loop-window-bench-v2` and `loop-j3-unfixable-v2`; the empty records under the old names hold no runs. The smoke ran at b086071, which differs only in that filter and a comment.

Note (2026-11-09): `loop-window-bench-v2` and `loop-j3-unfixable-v2` stay at f2f4151, where anchoring requires a courtyard. A body-only part with connected pads, such as a module drawn without a courtyard, is not anchored in any of their arms, as on main. Anchoring is not what these arms test, and each compares against its own control.

## Addendum 3 (2026-11-10, after the 40-board results; written before any extension run)
Only J14 was undecided at 40 boards. Per the extension rule, `ctl` and `j14` (the same method ids) run on `boards-extension-j14.txt`: the 31 extension boards minus the 2 smoke boards, 29 boards. This is experiment `loop-j14-ext`.
Decision on all 69 boards pooled (40 + 29), with the plan's opens rule: mean `d` < 0, sign-flip p < 0.05, and total opens at least 3 % lower, with errors not worse beyond noise. Anything else is reported as undecided.
The other arms do not run on the extension: they were decided at 40 boards (J2, J5, J3, J4 failed; w2 against natural was better).
