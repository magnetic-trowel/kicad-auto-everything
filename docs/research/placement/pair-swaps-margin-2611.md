<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Pair swaps and placement margin (2026-11-09)

Scope: E116, J58, with the handling of E7. Not here: Hungarian assignment on HPWL (no gain, stage 1).
Keys: pair swap, kae.place.swaps, pair_swap, place_margin, auto_margin, polish-ab, E116, J58, E7

**Status:** experiments `pair-swap-ab`, `margin-ab` pre-registered ([PLAN](../../../tools/kaeres/experiments/polish-ab/PLAN.md)); no results yet.

## Mechanism
`kae.place.swaps.polish` ends placement with greedy swaps of equal two-pad parts (same shape and value) when the placer's physics term drops; it rolls back everything if the exact legality check ends worse. Stage 1 measured the term only: over 10% better on 27 of 138 boards, over 50% on 11. `place_margin` adds room between parts (0.2 mm, or auto: about 1 mm on an empty board, 0 above 70% fill).

## E7 (shared-rail decaps)
The placer's term charges a shared-rail cap to its nearest load pin; the routed evaluator drops such caps, so a swap that helps a shared rail shows in the placer term and not in routed physics. E7 is a physics-session fix, not done here; both numbers are reported and the verdict rests on routed opens and valued-module physics.

## Assembly and manufacture
A swap changes which identical part sits in which slot: same footprint set, BOM and feeders, so assembly is unaffected. Margin widens the gaps that set rework nozzle access and AOI shadowing; stage 1 has kae 0.19 mm under the human at the median with the same clean rate, so routing may have room to give.

## Open questions
Results when `polish-ab` finishes.
