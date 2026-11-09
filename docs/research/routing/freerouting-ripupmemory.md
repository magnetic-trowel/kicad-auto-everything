<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Upstream RipupMemory on oscillating boards: no gain

Scope: A/B of Freerouting upstream `847e7dae3` cherry-picked onto the fork. Not here: a rebase onto 2.6.0 (ledger R12), the partial-board optimizer `c78ee54` (conflicts in the fork's optimizer; not ported or tested).
Keys: RipupMemory, 847e7da, oscillation, board restore, STOP_AT_PASS_MODULO, ripupmemory-ab.

**Status:** did not work; stays out of the fork. **First published:** 2026-11-09, branch `fr-settings-ab`. **Code:** fork branch `fr-ripupmemory` 061507e5d against 2e1125a. **Plan:** [PLAN](../../../tools/kaeres/experiments/ripupmemory-ab/PLAN.md).

## Mechanism

RipupMemory records which net ripped which and keeps a rerouted net from ripping back the net it was moved for; a pair that still fails twice is retired.

## Result

Standalone Freerouting, 900 s, one thread, no `-mp` cap, one run per board per arm, side by side. 55 merit boards with at least 4 sign flips in the control's unrouted count in R11 and opens left at the end. Harness 7f17a5d. KiCad scores.

| Boards | n | Opens, control → memory | Better / worse / equal | Clean | DRC errors | Median CPU ratio |
|---|---|---|---|---|---|---|
| Finished in both arms (pre-registered) | 39 | 804 → 804 (0.0 %) | 7 / 4 / 28, sign p 0.55 | 0 → 0 | 1,455 → 1,424 (-2.1 %) | 0.999 |
| Timed out in either arm | 16 | 832 → 845 (+1.6 %) | 4 / 8 / 4 | 0 → 0 | 938 → 951 (+1.4 %) | 1.000 |
| All | 55 | 1,636 → 1,649 (+0.8 %) | 11 / 12 / 32 | 0 → 0 | 2,393 → 2,375 (-0.8 %) | 0.999 |

Per-type DRC, finished boards (types with at least 30 errors, paired sign-flip): solder_mask_bridge 523 → 521, copper_edge_clearance 397 → 388, clearance 148 → 148, starved_thermal 130 → 125, annular_width 89 → 89, shorting_items 45 → 40, courtyards_overlap 43 → 43; none significant. Below the size bar: hole_clearance 26 → 15. On all 55 boards clearance rose from 362 to 387, all of it on boards that timed out.

Sign flips of the unrouted count, finished boards: median 48 → 52, total 1,783 → 1,867. The oscillating boards did not improve. Verdict by the pre-registered rule (opens at least 5 % lower, p < 0.05): fails.

## What the oscillation in the logs is

The selection metric overstates pair trading. `AutorouteBatchLoop` restores an earlier, better board at every 4th pass from pass 8 (`STOP_AT_PASS_MODULO`, `STOP_AT_PASS_MINIMUM`), and the logged count after a restore is the restored board's. In the control runs with at least 16 passes, 31 of 53 boards have a lower unrouted count at every 4th pass, and a median of 45 % of passes equal the count four passes earlier: for example 3, 6, 6, 3, 7, 6, 6, 3. So much of the sawtooth is restore, then the same work again. The test therefore says RipupMemory does not help these boards; it does not isolate boards with real net-pair trading. What repeats deterministically after a restore is the more promising target (not tested).
