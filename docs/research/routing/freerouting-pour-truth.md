<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Freerouting says routed, KiCad says open: pours

Scope: why Freerouting reports a pour board fully routed while KiCad finds open connections; whether `plane_as_obstacle` helps; what the fork's pour model misses. Not here: pour handling in kae's repair loop ([kae-repair-loop](kae-repair-loop.md)).
Keys: pour truth, plane_as_obstacle, fill fragmentation, zone min width, thermal spokes, PlaneFillConnectivity, R5, R6, E14.

**Status:** root cause measured; `plane_as_obstacle` did not work (A/B stopped early, `r6-plane-obstacle`).
**First published:** 2026-11-09, branch `fr-pours`. **Commit measured:** fork 06d2686 stored runs (`fr-baseline`); tools in `tools/research/routing/fr_pour_truth/`.

## 1. The gap (ledger R5)

Freerouting 2.5.0 reports 0 unrouted and KiCad reports opens on 2,545 of 10,655 pour boards (18 of 2,055 no-pour boards); fork 3,602 of 11,378; 69 % of the open items involve a zone. On R5's 30 boards the fork's fill model (`PlaneFillConnectivity`, its post-pass `connectPourCutOffs`) reports no remaining cut-off on most boards where KiCad finds opens.

## 2. Root cause: routing cuts pours that Freerouting models as whole, by rules it does not see

Method: for each of the 30 boards, KiCad's connectivity after a refill of the routed board, and of the same board stripped of routing (the task's input as the router sees it). 141 open connections in total, matching the DRC's counts.

| Finding | Opens of 141 |
|---|---|
| Pads the bare fill connects and the routing separates (cut by routing) | 124 (88 %) |
| Pads already separate in the bare fill | 17 (12 %) |

Which KiCad fill rule makes the separation (the routed board, refilled under changed zone rules):

| Variant of the routed board | Opens left |
|---|---|
| As is | 141 |
| Zone minimum width near 0 (necks KiCad removes survive) | 89 |
| Solid pad connections instead of thermal spokes | 104 |
| Both | 67 |

So at least half the opens Freerouting does not see are the two rules its pour model ignores: minimum zone width (a fill neck below it is removed) and thermal spokes (spokes that do not reach fill leave the pad unconnected, where Freerouting treats the pad as inside the plane); the other 67 are tracks cutting the fill outright that the post-pass did not reconnect.

Physically: Freerouting treats a plane net as connected whenever a pad lies in the pour polygon, and routes other nets through the same area. A real pour is what is left after clearances, minimum-width trimming and island removal; a foreign track can split it into pieces.

Bridge consequence: this gap costs kae almost nothing. Under `kae bridge main final` (merge3-ab, 213 merit boards, final boards) 261 of 2,671 opens involve a zone, and the zone-only opens block exactly 1 board from being complete; the bridge's repair rounds and last mile close them with KiCad's real fill. A fork patch for fill rules would mostly help the plain Freerouting control.

## 3. `plane_as_obstacle` A/B (did not work)

Fork 2e1125a, 900 s, one run per board per arm, side by side; plan in [PLAN](../../../tools/kaeres/experiments/r6-plane-obstacle/PLAN.md). Stopped early, which the plan did not provide for, with 42 of 90 boards done: the bar was out of reach.

| Boards | n | Opens, control | Opens, plane obstacle | Worse / better / equal |
|---|---|---|---|---|
| Selected on the control's failure (R5) | 17 | 84 | 1,212 | 17 / 0 / 0 |
| Unselected (`complex_pours`, `power_pours`) | 25 | 6,138 | 12,129 | 19 / 1 / 5 |

Mean completion: selected 0.909 against 0.035; unselected 0.761 against 0.319. Mechanism: a pour covering a layer shuts foreign nets out of that layer, so the board cannot route. Keep `plane_as_obstacle` off. Do not build R36/E14 for kae on this evidence: section 2's bridge result says the gap costs kae one merit board.
