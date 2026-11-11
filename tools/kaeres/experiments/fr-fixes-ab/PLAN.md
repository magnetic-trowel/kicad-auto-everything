<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# fr-fixes-ab: fork fixes #8, #9, #10 against production 2e1125a

Pre-registered 2026-11-10, before any run. Decides whether the user should merge and reinstall the three fork
fixes. Fork branch `kae-fixes-2611` (c2192531f) = 2e1125a + #8 (a collapsed pull-tight result is no change),
#9 (fill-island decomposition, index and per-point cache: result-preserving), #10 (pour cut-off repair stops on a
counted work budget, default 2 x groups + 10 attempts).

## Arms (kaeres methods, kaebench Freerouting adapter, no `-mp` cap, 900 s, 1 thread; one run per board per arm)
| Arm | Method |
|---|---|
| control | `fr-fork 2e1125a nomp fx` (production build, R11's no-cap wrapper) |
| fixes | `fr-fork c219253 nomp fx` (the merged build, same wrapper) |

Side by side: one kaeq job per board, both arms in it. Harness and kae 7f17a5d (task spec 11).

## Boards
- `selected.txt`, 321: every board whose whole-board baseline run (fork 06d2686, `fr-fork master`) spent over 60 s in
  the pour cut-off repair (317), plus the 4 boards with a degenerate-polyline storm in any stored fork run. All
  `usable_route_test`. Selected on the mechanism, so reported apart.
- `unselected.txt`, 150: one per `repo_family`, `usable_route_test`, not selected, seeded sample (26111): shows what
  happens where the fixes should not matter.

## Measures
Per arm and population: timeouts (`final_state` TIMED_OUT), completion, cp1, open connections, per-type DRC errors,
CPU (router), wall time, pour repair line (kept, left, attempts, budget). Boards where both arms' sessions are
byte-identical are counted.

## Decision rule (adopt = recommend merge and reinstall to the user)
All must hold:
1. Selected: timeouts fewer (exact McNemar p < 0.05), and median router CPU not higher.
2. Selected and unselected: total opens not higher by more than 1 % in either population, cp1 not lower, and no DRC
   error type with at least 30 errors worse by more than 25 % (paired sign-flip p < 0.05 against the fixes).
3. Unselected: no board gets worse by more than 2 opens or newly times out without a reason traced to a fix.
Expected: identical sessions on most unselected boards; fewer timeouts and more connected pour groups on selected.
Freerouting is deterministic for runs that finish inside their job timeout; runs that time out move with host load.

## Bridge check (reported, not part of the rule)
Experiment `fr-fixes-bridge`: the production bridge (merge3-ab's "kae bridge main final" recipe, restart wrapper,
4 parallel attempts) on the 40 selected boards with the longest repair (`bridge.txt`), two arms differing only in
`KAE_BRIDGE_FREEROUTING` (2e1125a vs the merged build). Read: what the restart wrapper and repair rounds do after a
Freerouting run that now finishes: attempts started, kept attempt, repair rounds and their router seconds, final
opens and errors, CPU. Bridge restarts are seeded, so differences include restart noise; directional only.

The kae-side `_autorouter_stop` reading (COMPLETED when routing finished but the job hit its timeout in the repair)
is a separate change with its own A/B after this one. Expected cost: about 470 boards x 2 arms of at most 900 s, and
40 boards x 2 bridge arms; informational.
