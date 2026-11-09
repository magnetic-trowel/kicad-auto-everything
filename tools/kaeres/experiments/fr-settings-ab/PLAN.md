<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# fr-settings-ab: Freerouting settings through the bridge, one congested suite, one shared control

Pre-registered 2026-11-09, before any run. Ledger R16, R18, R43, R57, R59/J71. Budget, bridge command and
restart wrapper as in merge3-ab's "kae bridge main final" (900 s scaled by sqrt(footprints/40), 4 parallel
attempts, `--resume 0.5 --final`).

## Arms (kaeres methods, kae and harness 7f17a5d, attempt 0, one method run per board)
| Arm | Options on `kae.route.cli route` | Ledger | Why |
|---|---|---|---|
| control | none | | the production bridge at this commit |
| twin | none (`replicate=twin`) | A/A | measured noise of this suite, side by side |
| fanout | `--fanout` | R16 | fanout on with the fork's width floor, which turns the fork's fallback ladder back on |
| ladder | `--set fr.autorouter.fallback_strategies=no-neck,continue-fine-neck` | R16 | fanout-off ladder: re-route without or with a fine neck after stagnation |
| outside | `--pad-shapes outside` | R57 | pin shapes circumscribe the pads |
| neck | `--neckdown` | R57 | neck-down at pins, floored |
| outside+neck | both | R57 | the bundle seen before, untested alone |
| start_necked off | `--set fr.autorouter.start_necked=false` | R43 | a neck stays local to where it was needed |
| cost cycle | `--set fr_cycle=<4 presets>` | R18 | attempts differ by search costs: via/rip-up/direction; deterministic, each attempt a different configuration (arguable under the determinism rule; flagged in the page) |
| repair pass cap 3 | `--set repair_passes=3` | R59/J71 | caps repair rounds' Freerouting passes at 3 |
| repair pass cap 1 | `--set repair_passes=1` | R59/J71 | route-timesplit: pass 1 had the fewest unrouted in 231 of 297 repair rounds |

The `ladder` arm is a no-op on boards with no neck width (fork `RoutingFallback.java`): reported by whether
the plan has `neck_width`. Native pad entries stay off. E09's cost sweep (R19) and explore_patience (R41,
whose bandit includes a `seed` kind) are separate; see the page.

## Boards
`boards.txt`: 40 boards. All 21 merit boards in `route_demand.hard/extreme` where the bridge final
(merge3-ab) left opens, plus 19 of `route_demand.hard/extreme` (usable_route_test, one per `repo_family`,
fork 2e1125a-master leaves at least 3 opens in fr-baseline, sampled at random with seed 2611). No board that
everything routes clean. Tag `route_demand` is a heuristic: 19 of these are additionally selected by
Freerouting leaving at least 3 opens, so a spot-check is built in.

## Measures
cp1, cpk (k = 1 here), completion, open connections, per-type DRC errors, CPU, via count. Telemetry from
#40: per-pass unrouted, stop reasons, fallback attempts, neck counts. No physics claim: the arms that change
copper (necks, costs) get a physics read only if they pass the routing bar.

## Decision rule (per arm against control)
Adopt into the bridge default only if, against the control, all hold: total opens at least 10 % lower with a
paired sign test p < 0.05; cp1 not lower; DRC errors not higher by more than 2 % in total and no error type
with at least 30 errors worse by more than 25 %. The twin against the control measures noise: an arm's
difference counts only if it clears the twin's difference on the same statistic. Anything else is
"no decision", and an arm is extended to more boards if its effect is within 2x of the twin difference.

Expected cost: 40 boards x 11 arms, about 1,000 CPU-h with the bridge at 4 attempts; informational.

## Changes before the full run
2026-11-09, before any run of the experiment's boards: the `start_necked off` arm (R43) is dropped from the
full run. R43's precondition (ledger: A/B only if the bridge necks power nets much more than humans) failed: over
170 merit boards, power/ground net track length below class width is 13.5 % under the bridge against 14.6 %
for the human boards (median 0 for both; 29 vs 34 boards above 5 %). The arm ran on the two smoke boards only.
