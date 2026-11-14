<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# fr-ladder-ab: a Freerouting fallback ladder for jobs without fanout or neck width

Pre-registered 2026-11-14, before any full run (one smoke board per arm, profiled). Ledger R16.

## Why
The fork's fallback ladder (`RoutingFallback`, `RoutingFallbackRunner`) re-routes a board whose
pass loop stopped with opens under named setting changes and keeps the best. Its default list
(`direct-first,fanout-retry,short-escape,open-escape,no-fanout`) is all fanout strategies, and the
bridge turns fanout off, so the bridge never had a ladder: above `residual_repair_max_open` (4)
opens the job just returned. The neck strategies (`no-neck`, `continue-fine-neck`) are no-ops without a
neck width, which is why fr-settings-ab's ladder arm never fired on 13 boards (addendum db2d2f55).

## Change (fork branch `kae-ladder-no-neck`, 40c89c3 on the production pin d137fd1)
When fanout does not run and none of `fallback_strategies` applies, the new
`autorouter.no_fanout_fallback_strategies` run instead (default
`no-neck,vias-cheaper,vias-dearer,continue-ripped`):
- `vias-cheaper` / `vias-dearer`: re-route the input at half / twice the via cost. A stagnated board is
  usually walled in on one layer pair; cheaper vias let nets change layer around the wall, dearer vias
  free the space via pads and their clearances take on every layer. Which one helps depends on the
  board, so both run and the best is kept.
- `continue-ripped`: continue the best board after removing other nets' traces and vias within 1.5 mm
  of pins that are still open (the escape neighbourhood), so the open nets' pass loop starts with room.
- `no-neck`: only while the job necks (a board neck width); it never adds necking.

**What fanout off means for the ladder (decision):** the bridge turns fanout off because the fanout
pre-pass narrows tracks and its vias fight kae's own escapes. So fanout off means no fanout pre-pass
anywhere and no track narrower than the job's own settings, including in the ladder. It does not mean
"no ladder". None of the four strategies runs fanout or narrows; `continue-fine-neck` (narrows) is not
in the default list. An explicit `fallback_strategies` that applies still wins, and
`no_fanout_fallback_strategies=none` gives d137fd1's behaviour.

The work-budget patch (kae-work-budget, 9cf145d, unmerged) touches the pass loop and `describe()` only;
the two branches merge without conflict. Note for it: each ladder attempt is its own pass loop, so a
per-loop `max_work` multiplies with the ladder, and a `WORK_BUDGET` stop is not retryable (no ladder).

## Arms (kaeres methods, kae and harness 6fdfc89 = main, attempt 0, one run per board)
| Arm | Freerouting | Everything else |
|---|---|---|
| frl control | `kae-freerouting-fork-d137fd1` (production pin) | production bridge recipe, as fr-settings-ab control: 900 s x sqrt(footprints/40), 4 parallel attempts, `--resume 0.5`, `--final` last mile |
| frl ladder | `kae-fr-ladder-40c89c3` | identical |

Freerouting is deterministic: one run per board per arm, no seeds. The arms run side by side (kaeres
interleaves the methods of a board in one job).

## Boards
`boards.txt`: fr-settings-ab's 40 congested boards (21 merit boards in `route_demand.hard/extreme` the
bridge left open, plus 19 `route_demand.hard/extreme`, `usable_route_test`, one per `repo_family`, that
the fork leaves at least 3 opens on). The mechanism needs a Freerouting pass loop that stops by itself
(stagnation) with more than 4 opens; on fr-settings-ab's control runs, that is estimated for 25 of 29
boards (pass time well under the attempt budget, more than 4 open), so the suite exercises it.

## Measures
cp1, completion, open connections (KiCad, re-opened board), per-type DRC errors, via count, CPU and wall,
by tag where relevant. **Manipulation check:** per run, `restarts.json` `attempt_log[].fr.first.fallback.attempts`
lists the ladder's strategies; a board counts as *exercised* when the ladder arm logs at least one of
`vias-cheaper`, `vias-dearer`, `continue-ripped`, `no-neck`. The control must log none of them.

## Noise
fr-settings-ab's twin (same chassis, 2e1125a): total opens +2.4 % against control on 11 boards (-2.0 % on
28), per-board SD of the log1p(opens) difference 0.04; DRC errors vary about 3.4 % between identical runs.

## Decision rule
Primary set: exercised boards. Keep the ladder as the fork default (PR into the fork, then a new pin) only
if, on the primary set, all hold: total opens at least 10 % lower with a paired sign test p < 0.05; cp1
not lower; DRC errors not higher by more than 4 % in total (above the 3.4 % A/A spread) and no error type
with at least 30 errors worse by more than 25 %. All 40 boards are reported too, as a check that
unexercised boards do not move beyond noise. Anything else is "no decision"; if the opens effect is
between 2.4 % and 10 %, or p is between 0.05 and 0.2, extend with 40 more `route_demand.hard/extreme`
boards (`usable_route_test`, one per `repo_family`, not in this set, random seed 2611). A worse result
(opens higher beyond noise, or the guards fail) rejects it, and the branch stays unmerged.

Expected cost (information): 40 boards x 2 arms at about 2.3 CPU-h per board-arm, about 190 CPU-h.
