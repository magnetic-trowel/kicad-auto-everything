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
