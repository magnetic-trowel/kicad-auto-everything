<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# A Freerouting fallback ladder without fanout or neck width (2026-11-14)

Status: **running, no verdict.** Plan: `tools/kaeres/experiments/fr-ladder-ab/PLAN.md`.

## The gap
After a pass loop stops with open connections, the fork re-routes the board under named setting changes
and keeps the best result (`RoutingFallback`, `RoutingFallbackRunner`). Every strategy in the default list
needs the fanout pre-pass, and the bridge turns fanout off, so the bridge never had a ladder. With at
most 4 opens the board is continued once (`residual_repair_max_open`); with more, the job returned. The
neck strategies do nothing without a neck width. That is why fr-settings-ab's ladder arm
(`no-neck,continue-fine-neck`) never fired on 13 boards.

## The change
Fork branch `kae-ladder-no-neck` (40c89c3, on the production pin d137fd1, 6 files, unit tests 12/12).
When fanout does not run and no configured strategy applies, `autorouter.no_fanout_fallback_strategies`
runs (default `no-neck,vias-cheaper,vias-dearer,continue-ripped`):

| Strategy | Starts from | What changes | Why it can help |
|---|---|---|---|
| `vias-cheaper` | input | via cost / 2 | nets change layer around a wall of other nets' tracks |
| `vias-dearer` | input | via cost x 2 | fewer vias, whose pads and clearances block every layer |
| `continue-ripped` | best board | other nets' tracks and vias within 1.5 mm of open pins removed, then a new pass loop | the open nets' escape area is cleared before they route |
| `no-neck` | input | neck width 0 | only when the job necks |

**Fanout off and the ladder.** The bridge disables fanout because the pre-pass narrows tracks and its
vias fight kae's own escapes. So fanout off is read as "no fanout pre-pass and nothing narrower than
the job's settings", in the ladder as everywhere else, and not as "no ladder". No default strategy runs
fanout or narrows; `continue-fine-neck`, which narrows, is left out. An explicit strategy list that
applies still wins. `no_fanout_fallback_strategies=none` restores d137fd1's behaviour.

The work-budget patch (kae-work-budget 9cf145d) merges cleanly with this branch. Each ladder attempt is a
separate pass loop, so a per-loop `max_work` adds up across the ladder. A `WORK_BUDGET` stop is not
retryable, so the ladder does not run after one.

## Smoke (can485, 172 pads, 4 layers, one run per arm, production chassis, profiled)
- **The ladder fires.** It ran in 8 of 21 attempts: 8 default attempts ended in stagnation, then
  `vias-cheaper` (8), `vias-dearer` (4) and `continue-ripped` (1). It replaced the default board once
  (`vias-cheaper`). Control logged no ladder strategy. On a single first route (bridge, no repair),
  Freerouting's own count went 13 → 11 open with `vias-cheaper`, but KiCad counted 22 against 23. Whole chassis: 7 opens (control) against 9 (ladder). One
  board, so neither is a result.
- **Default path unchanged.** The ladder build's default attempt took the same per-pass unrouted path
  as d137fd1's.
- **Cost.** Wall time is the same (fixed chassis budget). The ladder fills Freerouting's job time that
  the repair rounds would otherwise use. Method CPU was 1995 s against 2443 s (Freerouting is single-threaded,
  and the repair's KiCad DRC calls are not). Peak RSS was 0.69 GB against 0.67 GB.
- **Where the time goes (py-spy on the inner python, both arms alike):** Freerouting 62-66 %, last mile and
  repair 19-21 %, KiCad DRC 7 %, pcbnew calls 4 %, imports and numba 3 %. JFR shows the usual maze
  hotspots (`ShapeSearchTree45Degree.completeShapeUnlocked`, `PriorityQueue.siftUp`) and nothing from
  the ladder itself. No cheap speedup is specific to this change.

## A/B
`fr-ladder-ab`: 40 congested boards (fr-settings-ab's set) x {d137fd1, ladder build}, at kae 6fdfc89
(main), one run per board. The primary set is the boards where the ladder fired. Decision rule and
extension are in the plan. kaeq owner `exp-fr-ladder-ab`, jobs #96580-#96659.
