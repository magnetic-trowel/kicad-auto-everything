<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# The joint loop's windows at a real budget (loop-window-bench, 2026-11-10)

Scope: what `kae.joint`'s window stage gains as its budget grows, and the window fixes J2, J4, J5, J14 (J3: [window-outcomes-2611](window-outcomes-2611.md) on branch `loop-j3-unfixable-drc`). Not here: the chassis verdict (J1).
Keys: joint loop, windows, window_budget_factor, budget curve, min_iter_s, route_share, first_last_mile, legal_time, revert_illegal, J2, J4, J5, J14, J15

**Status:** windows work, but only with time beyond today's budget. With two budgets of window time open connections fall 16 % (27 boards better, 10 worse, p 0.033) at 2.8 times the CPU. A third and fourth budget add little. No fix to how the budget is split or to the legalizer passed.
**First published:** 2026-11-10, branch `loop-exp`, experiment `loop-window-bench-v2` (plan `tools/kaeres/experiments/loop-window-bench/PLAN.md`, pre-registered), commit f2f4151.

## Setup
40 boards where joint leaves open connections (from `placement-decide-joint`), one per repo family, 10 per footprint quartile. One run of `kae.joint.cli` each, seed 0, no restart wrapper. B = 900 s x sqrt(fp/40). Arms ran interleaved, and KiCad scored all 400 runs. Physics is not reported: no board was fully routed in both arms of any pair (the boards were chosen for leaving opens), so the J21 floor cannot be applied.

## Per arm (40 boards)

| arm | window budget | cp1 | opens | DRC errors | boards with windows | windows | illegal after repair | kept | repeated windows | CPU h |
|---|---|---|---|---|---|---|---|---|---|---|
| ctl | natural | 1 | 3,845 | 2,000 | 35 | 166 | 39 | 26 | 43 | 18.4 |
| j2 (`route_share 0.4, finish_share 0.1, min_iter_s 25`) | natural | 0 | 3,952 | 2,121 | 40 | 334 | 77 | 53 | 118 | 18.5 |
| j5 (`min_iter_s 25`) | natural | 0 | 3,725 | 1,984 | 37 | 188 | 57 | 29 | 40 | 18.3 |
| j14 (`first_last_mile 1`) | natural | 1 | 3,425 | 2,025 | 37 | 135 | 37 | 18 | 21 | 18.0 |
| w2 ctl | +2 B | 1 | 3,217 | 2,148 | 40 | 1,260 | 423 | 128 | 531 | 50.9 |
| w2 j3 | +2 B | 1 | 3,237 | 2,020 | 40 | 1,324 | 571 | 115 | 587 | 51.9 |
| w2 j4t (legalizer time, share) | +2 B | 1 | 3,269 | 2,091 | 40 | 1,237 | 446 | 146 | 480 | 50.9 |
| w2 j4 (+ incumbent fallback) | +2 B | 1 | 3,111 | 1,948 | 40 | 1,200 | 394 | 120 | 468 | 53.0 |
| w2 all (J3 + J4) | +2 B | 1 | 3,485 | 1,930 | 40 | 1,165 | 372 | 121 | 492 | 50.7 |
| w4 all | +4 B | 1 | 3,360 | 2,077 | 40 | 1,936 | 644 | 150 | 1,024 | 80.5 |

"Repeated windows": windows whose part set an earlier window on the same board already used (J15).

## Pairs (paired per board; d = (o_arm − o_ctl) / (o_arm + o_ctl + 1), sign-flip p)

| pair | opens | boards fewer / more | mean d, p | verdict |
|---|---|---|---|---|
| w2 ctl vs ctl | −16.3 % | 27 / 10 | −0.105, 0.033 | better (rule met), at 2.8x CPU |
| w4 all vs w2 all | −3.6 % | 24 / 11 | −0.076, 0.055 | undecided |
| w4 all vs ctl | −12.6 % | 24 / 11 | −0.163, 0.002 | better, at 4.4x CPU |
| j2 vs ctl | +2.8 % | 12 / 22 | +0.039, 0.42 | fails (no gain) |
| j5 vs ctl | −3.1 % | 15 / 19 | +0.024, 0.53 | fails (no gain) |
| j14 vs ctl | −10.9 % | 24 / 13 | −0.072, 0.11 | undecided |
| w2 j4t vs w2 ctl | +1.6 % | 17 / 16 | −0.018, 0.68 | fails: illegal after repair 446 vs 423, not halved |
| w2 j4 vs w2 ctl | −3.3 % | 18 / 19 | −0.052, 0.21 | fails: illegal 394 vs 423, not halved |
| w2 j3 vs w2 ctl | +0.6 % | 15 / 19 | +0.011, 0.77 | fails (as on its own 30 boards) |
| w2 all vs w2 ctl | +8.3 % | 13 / 18 | +0.010, 0.81 | fails |

Errors: w2 ctl's 2,148 against ctl's 2,000 is one board. seeed-studio jetson's `starved_thermal` goes from 15 to 190, and the same happens in w4 and j2. solder_mask_bridge falls 497 to 470 (441 in w2 all). The other placement types barely move, and cp1 is 1 of 40 everywhere (these boards leave opens).

## Where it stops paying (w4 all, windows alone, before the finishing stage)
Opens the windows removed from iteration 0's board, after this much window time:

| window time | median removed | mean | total |
|---|---|---|---|
| 0.5 B | 2.5 | 7.2 | 287 |
| 1 B | 3.5 | 10.3 | 412 |
| 2 B | 8.0 | 16.3 | 652 |
| 4 B | 8.5 | 21.0 | 841 |

Doubling from 1 to 2 B removes 4.5 more opens per board (median). From 2 to 4 B it removes 0.5, under the plan's threshold of one open, so the stage stops paying at about 2 B of window time. The reason is in the windows: repeats rise from 42 % of windows (w2) to 53 % (w4). The loop runs out of new windows to try, J15's mechanism, and J3 found the same limit. "Illegal after repair" stays at a third of windows in every arm.

## What it means
- The gain is real but bought with compute: w2 is 2.8 times ctl's CPU. Inside the same budget, re-splitting the time (j2, j5) gains nothing. So the default stays, and the open question is compute-matched: does 3 B of joint with windows beat 3 B of restarts of the staged pipeline, which is how the merit runs spend extra time?
- J4 fails, so the legalizer was not the limit. More time and the incumbent fallback leave a third of windows illegal: the windows ask for moves that have no legal spot.
- J14 (`first_last_mile=1`, −11 %, 24 of 37 boards better) is the only change at today's budget that looks promising. It is undecided at 40 boards; the plan's extension (31 boards) would decide it.
- What would change this: a window choice that does not repeat (J15) or that targets blocked corridors (`kae.route.blocked`), measured on the same boards.
