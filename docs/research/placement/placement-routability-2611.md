<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Routability inside the placer: ratsnest crossings, routing channels, routing failures as placer input

Scope: the mechanism and A/Bs of four placer changes aimed at placements that fail to route: the untangle pass (ledger J70), a crossing term in the annealer, routing history fed to the global placer across restart attempts (J6), the routing-channel term (J46). Not here: legality failures of the placer (J19) -> [kae-exact-legality](kae-exact-legality.md).
Keys: untangle, ratsnest crossings, place_untangle, place_w_xing, kae.place.crossings, place_w_chan, channel_grid, place_history, cong_history, placement-routability

**Status:** experiments queued 2026-11-09; numbers follow in this page when they finish. Each change is off by default until its A/B says otherwise.

## Why crossings

Facts from stage 1 ([E108], 11,803 placements, 213 boards): within a board HPWL predicts open connections hardly at all (median Spearman +0.01), RUDY is flat, and ratsnest crossings are the best single feature (seed pairs rho +0.27, sign agreement 61%). Alignment is a marker of human placements, not a cause.

The mechanism is topological:

1. **A crossing is an obligation; length is not.** Two nets whose ratsnest segments cross must change layer at least once between them. On a through-via stackup that is a via pair: two holes, each with a keepout, on every layer, placed in the region where the two nets already compete. Copper can detour around a long net; it cannot route two crossed nets without a layer change.
2. **HPWL and RUDY are permutation-blind.** Two parallel two-pin connections have the same bounding boxes whether their ends are in order or swapped. RUDY spreads the same boxes. So the search cannot see the difference between a bus in pin order and the same bus reversed, a resistor one way or turned, or two equal capacitors swapped.
3. **The annealer randomizes exactly those moves.** A swap of two equal parts or a half turn of a resistor changes HPWL by little; moves near zero cost are accepted at any temperature. What the annealer leaves is a random permutation of the degrees of freedom HPWL does not price, and the crossing count of the result is whatever those random moves left. A human doing the same job orders bus bits and flips the resistors so the fan-out does not tangle.
4. **Crossings bite where the board is dense.** On a dense board there are few spare positions for the vias a crossing forces and few layers to change to; the same crossing costs nothing on a sparse one. The expected effect is therefore on boards with opens, on 2-layer and tightly-packed 4-layer boards first.

What follows for a placer: a term must see the degrees of freedom HPWL does not; it must not fight legality (swaps of equal shapes and half turns keep rectangles); and it should be priced in the same currency as length, which is why the term here is mm of HPWL per crossing.

## Design

- **Untangle pass** (`kae.place.crossings.untangle`, `--set place_untangle=1`): after legalization, greedily swap parts of equal `shape_key` and half-turn parts, when that removes crossings, costs at most `place_untangle_x_mm` (2 mm) of weighted HPWL per crossing removed, and does not worsen physics or zone cost. Labelled, protection-order and zone-pinned parts stay. At the end of the placement because it needs a legal state, and because the moves it uses keep legality without the annealer's machinery; the question of the same moves inside the loop is the crossing term's.
- **Crossing term** (`--set place_w_xing=X`, default off): X mm of weighted HPWL per crossing, added to the annealer's delta (compiled kernel `_x_delta`, MST of each net touched, box-pruned test against the others). Joins at 25% of the schedule (`place_xing_from`), when parts stop wandering.
- **Routing-channel term** (`--set place_w_chan=W`): the existing `channel_grid` halos, previously reachable only from `kae place --anneal-args`.
- **Routing history across attempts** (`--set place_history=DIR --set place_w_cong=30`): each routed attempt saves its failed corridors (`CongestionHistory`); a fresh attempt's global placement reads the mean of what earlier attempts left, as extra congestion demand in the annealer's RUDY bins. The history is inert unless the RUDY term is on, so the arm needs a control with the term on and no history.

## Experiments

Pre-registered plans: `tools/kaeres/experiments/placement-routability/PLAN.md`. Boards are the placements that fail to route (47 boards, selection in the plan).

### Placer-only smoke (not a routing result)

2 boards, 2 seeds, 300 s, placement only, 2026-11-09 (ratsnest crossings at the end of the placement, HPWL in mm):

| Board | Control | Untangle | Term, 2 mm | Term, 5 mm |
|---|---|---|---|---|
| metro-m7 (seed 0, 1) | 374, 286 crossings; HPWL 1765, 1438 | 358, 176 (the pass took 389->358, 200->176); 1622, 1338 | 91, 104; 1537, 1381 | 90, 118; 1561, 1418 |
| vspeed (seed 0, 1) | 18, 35; HPWL 360, 446 | 43, 30 (56->43, 32->30); 493, 402 | 24, 25; 503, 427 | 15, 18; 375, 471 |

CPU contention affects these runs' move counts (440-810 k moves); the seed-to-seed spread in HPWL is as large as any difference
between arms, and two boards decide nothing. What they show: on metro-m7 the term cuts crossings about 3x (374, 286 to 91, 104) at no
worse HPWL, at about 10% fewer moves per second (7.4-8.2 k to 6.7-7.0 k); on the small vspeed board it changes little (18, 35 to 24, 25).
The pass alone removes 6-23% of the crossings it sees (1-3 swaps and 1-4 half turns a run), so most crossings are not removable by
equal-shape swaps and half turns: the pass is the small version of the idea, the term the large one. 2 and 5 mm behave alike here, so one
weight (2 mm) goes into the routing test.

**Results of the routing test: pending.**
