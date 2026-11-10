<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# bus-escape-order: bus lanes out of their pins as ordered ribbons (pre-registered plan)

Written 2026-11-10, before any run. Branch `bus-escape`. Bus campaign wave 2 (escape and pin access), after B1
(`bus-alone-b1`) and its follow-up diagnosis (`docs/research/routing/bus-escape-2611.md`).

## Why
In B1, 68% of the bus lanes open on the whole board are also open when the bus routes alone, and 82% of the buses that
fail alone have a BGA, grid or sub-0.5 mm end. The follow-up read every lane open in the bus-alone outputs (17,969 lanes,
265 boards): at 77% of them an end pad has no copper at all (68% the fine end), mostly balls of ring 1 and deeper; only 1%
reach out of both end parts' pin fields and die in the trunk. So the lanes never leave their pins. kae's escape planner
(`kae.route.escape.plan_grid`) plans every ball of a grid (layer, side, dog-bone via, path to the edge), but the bridge lays
only its fixed dog-bones by default, and the plan laid as copper was a wall to Freerouting (`(type route)`; D1 tests it
soft in `bus-wire-types`). Nothing in it knows buses.

## Mechanism under test
`--set escape_bus=true` (with `escape_lay=plan`, `wire_type=shove_fixed`): the bare-board bus detector (`kae.bus`, no
copper) gives each bus lane's net at a grid end and its pin at the bus's other end (`kae.route.bus_escape.orders`). In
`plan_grid`, a bus's lanes prefer the package side facing that end (stage 2's side commodity), and are split into the
fewest chains that keep the other end's order (greedy best fit; their number is the permutation's LDS), one layer per
chain, the outermost chain on the ball layer (a stage-1 cost of 250 on any other layer: preference, not a rule). The
plan's escapes end 0.75 pitch past the package edge: on each layer the bus's lanes arrive there as ordered ports (the
compress line), handed to Freerouting as rippable copper (`shove_fixed`), which routes the trunk from them. No pin swaps,
no lateral compression of the ports, fine-pitch rings (QFN/QFP) untouched (the planner covers grids only).

## Arms (one kaeq job per board runs all six, side by side; bare placement: the benchmark's route task)
`kae.route.cli route`, Freerouting fork 2e1125a, k = 1, seed 0. Only these flags differ:
- **control**: the bridge's defaults (fixed dog-bones, escape copper as `(type route)`)
- **plan**: `--set escape_lay=plan --set wire_type=shove_fixed` (the whole plan laid soft; D1's `wt-plan-shove`, here as the
  reference that separates bus order from laying the plan)
- **bus**: plan plus `--set escape_bus=true`

Budgets 900 s and 300 s for every arm (bundling and soft copper can cost completion when the budget is tight).

## Boards
`boards.txt` (`select_boards.py`, seed `bus-escape-order-2026-11-10`): boards with a bus that fails alone in B1 and has a
ball-grid end (B1's end type names `bga` or `grid`), in `bga` or `kae_escape_grid`, `usable_route_test`, one per
`repo_family`: 133 boards (B1 ran the `.n100` suites, one board per family). The mechanism acts on these boards only.
Extension (one look): the same rule on `bus-alone-b1-ext`'s buses.csv when it is done, if the decision below is undecided.

## Outcomes
Primary: **bus lanes open** on the buses with a grid end (kae.bus lanes, the B1 bus list), from a bus-only `kicad-cli` view of
each output (B1's `view_bus.py`), summed per arm; paired per board, 95% board-clustered bootstrap of the ratio bus / control
(1,000 resamples, seed 1234). Secondary, always reported: **whole-board open connections** (KiCad, harness DRC), cp1, cpk,
completion, DRC errors per type, vias per bus lane (bus scorecard, `kaeres bus`), CPU, planner telemetry (`report.escape`:
lanes planned, on their side, in order). Each read at 900 s and 300 s, and separately for boards where the control finished
2 Freerouting passes (`router.report`) and where it did not.

## Decision (900 s, bus vs control)
- **helps**: bus lanes open fall by 10% or more with the interval excluding 0, and whole-board opens and DRC errors not worse
  by more than 5% (interval upper bound). Noise: the A/A moved total opens 2.8% at 213 boards; about 4% at 133.
- **no effect**: the bus-lane interval within +-10%.
- **hurts**: bus lanes or whole-board opens rise by more than 5% with the interval excluding 0.
- bus vs plan, same test, reads the share due to order; plan vs control reads laying the plan soft.
- Undecided (an interval straddling an edge): the extension, then report the combined interval. Nothing becomes a default from
  this experiment alone.

## What would change the verdict
A bus-only view that miscounts (checked on the smoke boards against the harness DRC); the escape stage's time cap (`escape_share`)
cutting the plan short on big boards (read `report.escape` per arm); arms run at different times (one job per board runs all
six in turn).

## Expected cost (information)
About 0.3 CPU-h per board-arm at 900 s, 0.13 at 300 s: about 170 CPU-h; one job per board of about 70 min wall.

## Amendments (before any result)
- 2026-11-10: methods at c046276; experiments `bus-escape-order-smoke` (`smoke.txt`, 2 boards, queued) and `bus-escape-order`
  (created, submitted only after the smoke is read end to end). kaeres splits each board into two jobs of three arms (900 s,
  then 300 s); the arms of one budget still run side by side.
- Numba cache `numba-kae-dp-c046276` warmed by one 200 s bus-arm route of a KiCad-10 copy of the olimex smoke board with its
  copper stripped (not a task run, not scored). It showed the risk to read first: on its 0.5 mm-pitch eMMC the planner planned
  9 escapes and laid 1 (planned paths fail the exact check at that pitch). The laid share per arm (`report.escape`) is read
  before any outcome.
