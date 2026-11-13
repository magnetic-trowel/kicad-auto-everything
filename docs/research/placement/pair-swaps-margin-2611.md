<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Pair swaps and placement margin (2026-11-09)

Scope: E116, J58, with the handling of E7. Not here: Hungarian assignment on HPWL (no gain, stage 1).
Keys: pair swap, kae.place.swaps, pair_swap, place_margin, auto_margin, polish-ab, E116, J58, E7

**Status:** experiments `pair-swap-ab` and `margin-ab` ([PLAN](../../../tools/kaeres/experiments/polish-ab/PLAN.md)) are complete; results are in the sections below.
- Pair swaps: off (negative result).
- Margin: the rule is met; the auto margin (`place_margin=-1`) wins the tie-break.

## Mechanism
`kae.place.swaps.polish` ends placement with greedy swaps of equal two-pad parts (same shape and value) when the placer's physics term drops; it rolls back everything if the exact legality check ends worse. Stage 1 measured the term only: over 10% better on 27 of 138 boards, over 50% on 11. `place_margin` adds room between parts (0.2 mm, or auto: about 1 mm on an empty board, 0 above 70% fill).

## E7 (shared-rail decaps)
The placer's term charges a shared-rail cap to its nearest load pin; the routed evaluator drops such caps, so a swap that helps a shared rail shows in the placer term and not in routed physics. E7 is a physics-session fix, not done here; both numbers are reported and the verdict rests on routed opens and valued-module physics.

## Assembly and manufacture
A swap changes which identical part sits in which slot: same footprint set, BOM and feeders, so assembly is unaffected. Margin widens the gaps that set rework nozzle access and AOI shadowing; stage 1 has kae 0.19 mm under the human at the median with the same clean rate, so routing may have room to give.

## Results: pair-swap-ab (2026-11-13)
**Setup.** Both arms are at 1edecfe with Freerouting fork 2e1125a, set explicitly. There are 27 boards, the same task per board, attempt 0. All 54 runs were ok.

**The pass often did not stick.** restart.py does not keep per-attempt logs, so the in-run `pair_swap` before/after report was lost. Instead, the placer terms (barrier 0, SA u_sat) were rebuilt on both kept placements, along with the greedy swap gain still left on each.
- On 7 boards the pass clearly acted: the SW board has no gain left where C still has some.
- On 20 boards the kept SW board carries as much swap gain as C. The pass was skipped, rolled back or lost in the restarts.

| C → SW | value |
|---|---|
| cp1 (= cpk) | 0.074 → 0.000 (2 boards lost, one open each; McNemar p 0.5) |
| completion | 0.881 → 0.879 |
| open connections | 2109 → 2191 (+3.9%; 11 boards worse, 7 better; sign-flip p 0.53) |
| DRC errors | 1572 → 1671 (silk_overlap 30 → 96 and silk_over_copper 89 → 110, all on nekoink; copper_edge_clearance 137 → 156) |
| CPU | 41.6 → 42.3 h |
| placer term, median SW/C | 0.904 (13 boards gained more than 10%, 5 lost more than 10%) |
| HPWL, median SW/C | 0.988 |
| valued routed physics, median paired ratio | 1.026 (n 25), inside the J21 floor (about 1.10) |

**Verdict: off.** The rule needs a median term ratio of 0.9 or below; 0.904 misses it.

Scoring only the 7 boards where the pass acted does not rescue it:
- the term fell (median 0.864) and valued physics improved (0.845);
- but opens rose 821 → 942 (+15%; 5 boards worse, 0 better), past the 5% bound.

The likely cause is that swapping equal decaps changes which nets sit next to each other, and the router pays for that. This split is post hoc and not significant on its own.

The pre-registered extension to 138 boards is not triggered: opens and valued physics were not positive. Rerunning would need a pass that acts reliably and logs its report, or a swap priced on routability as well as physics.

## Results: margin-ab (2026-11-13)
**Setup.** The arms are C, M2 (0.2 mm) and MA (auto margin), with the same code and Freerouting fork as above. There are 60 boards, the same task per board. All 180 runs were ok.

**The margin acted.** Placements differ from C on 53 of 60 boards, and the p50 gap rose on 37. Gaps follow the stage-1 definition: pad bbox to the nearest same-side part.

| | C | M2 | MA |
|---|---|---|---|
| cp1 (= cpk) | 0.400 | 0.383 | 0.383 |
| completion | 0.967 | 0.967 | 0.969 |
| open connections | 1558 | 1553 (−0.3%) | 1536 (−1.4%) |
| DRC errors | 538 | 575 | 591 |
| CPU h | 36.6 | 40.7 | 38.2 |
| p50 gap − human, median | −0.195 mm | −0.048 mm | 0.000 mm |
| share of gaps < 0.5 mm (human 0.201) | 0.335 | 0.192 | 0.169 |
| valued physics, median paired ratio | | 1.010 | 1.067 |

**Clean results and DRC.** The only change in clean results is one board lost in both arms: a DIP protoboard where the widened gaps produced solder-mask bridges and edge-clearance errors. MA's other added errors are starved thermals on one board, which also went from 2 opens to 0.

**Verdict: the rule is met by both arms.**
- Gap toward the human: +0.147 mm (M2), +0.195 mm (MA).
- Clean rate: −1.7 pp, inside the 3 pp bound.
- Opens: not worse.

The tie-break (gap closer to the human) picks MA, `place_margin=-1`. Two caveats:
- **Overshoot.** MA overshoots on roomy boards: its median per-board |p50 − human| is 0.29 mm, against 0.25 for M2 and C.
- **Physics.** MA's valued physics ratio sits at the noise floor for n 33 (about 1.07). M2 is the conservative choice if physics is weighed.

At n 60, cp1 losses under about 8 pp cannot be seen; a larger confirmation could reverse this.
