<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Freerouting fork fixes: runaway pull-tight, slow pour repair, repair budget

Scope: three fork fixes found while sizing Freerouting timeouts, and their A/B against the production build 2e1125a. Not here: setting experiments (fr-settings-ab, e09-sweep) and pour truth ([freerouting-pour-truth](freerouting-pour-truth.md)).
Keys: degenerate polyline, pull-tight loop, connectPourCutOffs, fill islands, decomposeAreaIntoIslands, pour_repair_attempts, fr-fixes-ab, fr-fixes-bridge2.

**Status:** passed its pre-registered rule; merging and reinstalling is the user's decision. **First published:** 2026-11-11, branch `fr-fixes-ab`. **Code:** fork branch `kae-fixes-2611` (c2192531f) = 2e1125a + PRs [#8](https://github.com/magnetic-trowel/freerouting/pull/8), [#9](https://github.com/magnetic-trowel/freerouting/pull/9), [#10](https://github.com/magnetic-trowel/freerouting/pull/10). **Plan:** [PLAN](../../../tools/kaeres/experiments/fr-fixes-ab/PLAN.md).

## 1. The bugs

| Fix | Mechanism | Found on |
|---|---|---|
| #8 pull-tight | `TraceTightener45.reduceCorners` can shortcut a loop trace to one point; the line-less result counted as a change while `change()` kept the trace, so `optChangedArea` pulled the same trace tight until the job timeout | 5 of 18,015 stored fork runs, each with 0.45-5.9 M "Polyline: must contain at least 2 different points" warnings; all timed out |
| #9 fill islands | Island decomposition compared every pair of fill contours; island lookups scanned every island and tested points against islands with thousands of edges, again and again while the fill was unchanged. Fixed by a grid for contour pairs, a grid index for lookups and a per-point cache; results unchanged (byte-identical sessions) | The repair after routing that reconnects copper cut off from a pour (`connectPourCutOffs`): over 60 s on 317 of 14,579 whole-board baseline runs, over 300 s on 75, 27.5 h in total |
| #10 repair budget | The repair stops after `autorouter.pour_repair_attempts` attempts (default 2 x groups + 10), counted work, so it stops at the same point on any machine; a stopped repair keeps every connection it made | Fully routed boards that spent the rest of the job in the repair and ended TIMED_OUT |

Single-board effect, `-mp 10`, 60-min job timeout: a 466-net board's repair took 45.4 min before #9, 4.9 min after (job 48.8 -> 8.1 min, same session); a 53-net fully routed board's repair did not finish in 773 s before, 82 s after.

## 2. A/B: standalone Freerouting (`fr-fixes-ab`)

Arms: production 2e1125a vs c219253, kaebench adapter, no `-mp` cap, 900 s, one run per board per arm, both in one job per board. Harness 7f17a5d, task spec 11. 470 of 471 boards paired; the one unpaired board is in section 4.

| Population | Timeouts | Opens | cp1 | Completion | DRC errors | Router CPU median |
|---|---|---|---|---|---|---|
| Selected (321: repair over 60 s in the baseline, plus the storm boards) | 233 -> 209 (25 only control, 1 only fixes, McNemar p 8e-7) | 16,421 -> 16,069 (-2.1 %; 44 better, 11 worse, 266 equal; p < 0.001) | 2 -> 2 | 0.8441 -> 0.8481 | 37,454 -> 37,441 | 723.6 -> 704.5 s |
| Unselected (149, one per repo family) | 19 -> 19 (no new timeout) | 5,390 -> 5,395 (+0.1 %; 1 better, 2 worse) | 16 -> 16 | 0.8705 -> 0.8705 | 7,092 -> 7,081 | 10.9 -> 11.0 s |

- Per-type DRC: no type with at least 30 errors changes by more than 1 % in either population. `hole_to_hole`, raised by one smoke board (9 -> 16), is 518 -> 524 on the selected boards (2 boards worse, 1 better, p 0.75) and 17 -> 17 on the unselected ones.
- Unselected sessions: 144 of 149 byte-identical. The 5 that differ all timed out in both arms (wall-clock stops move with host load); the worst board is +5 opens (461 -> 466), both arms timed out.
- Selected: polyline storms 3 -> 0; pour groups reconnected 1,800 -> 2,104; the repair budget did not bind on any board.

Verdict by the pre-registered rule: passes (timeouts fewer, CPU not higher; opens within 1 % and lower where selected; cp1 equal; no DRC type worse; no unexplained regression on unselected boards).

## 3. Through the bridge (`fr-fixes-bridge2`)

Production bridge recipe ("kae bridge main final": restart wrapper, 4 parallel attempts), 40 selected boards with the longest repair; arms differ only in `KAE_BRIDGE_FREEROUTING`. Every non-zero attempt records its cause ([PR #55](https://github.com/magnetic-trowel/kicad-auto-everything/pull/55)).

| | 2e1125a | c219253 |
|---|---|---|
| Clean | 6 / 40 | 6 / 40 |
| Opens | 446 | 374 (-16 %; 17 better, 6 worse, 17 equal; p 0.035) |
| DRC errors | 3,237 | 3,233 (types equal within 3) |
| CPU (restart wrapper) | 73.4 h | 69.0 h |
| First-wave failures | 21: 18 Freerouting killed at its hard limit with no session, 3 DRC timeouts | 12: DRC timeouts on 3 big boards |
| Kept attempt: Freerouting COMPLETED / TIMED_OUT | 6 / 10 | 18 / 4 |
| Repair rounds in the kept attempt (median), their router time | 0, 801 s | 2.5, 2,240 s |

What changes downstream: Freerouting ends on its own more often and writes its session in time, so the bridge's repair rounds, which the stuck runs starved, now run. The restart wrapper starts as many attempts as before.

## 4. Caveats

- One board (`sinara-hw-diot-tester`) has no fixes-arm result: Freerouting had not written its session when the adapter killed it at 900 s. Its job had started 46 s after the JVM (DSN load on a loaded host) and its passes ran 10-15 % slower than the control's, with identical scores for passes 1-5, so the job timeout fell inside pass 6 and the stop plus write did not fit in the adapter's margin. Rerun alone with the fixed build, the same board stopped at its job timeout mid-pass 8 and wrote its session 2.5 s later: the stop request is honoured; the missing output was the wall-clock margin.
- A bridge smoke once had all four first-wave attempts of the fixes arm end without a board; it did not recur in a sandboxed reproduction or in the 40-board run, where failures are recorded and explained above.
- Wall-clock budgets: boards that time out in both arms move with host load; counted-work budgets for the whole job (R45) are not in.

## 5. Adopting it

- Merge fork PRs #8, #9, #10, install with `tools/research/routing/install_freerouting_fork.sh c2192531f --pin` (after kae PR #53), or the merge commit of the PRs.
- Every bridge and kaeres method pins its Freerouting binary, so adoption means new method ids (a new `KAE_BRIDGE_FREEROUTING` path or binary hash) and new runs: earlier results stay comparable only to runs of the same build. The combined baseline (Stage 2) should use the new build from the start.
