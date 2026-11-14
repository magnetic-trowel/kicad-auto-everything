<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Voids, slots and all-layer keepouts as barriers (2026-11-09)

Scope: E104, E105: keeping parts and nets off barriers the router cannot cross. Not here: the region scan method -> stage 1.
Keys: barrier split, fit_split, barrier-fit-ab, region capacity, true region split, voids, slots, HV keepout, rule area, barrier_split, barrier_net_weight, kae.place.barriers, barrier-ab, E104, E105

**Status:** `barrier-weight-ab2` done: `barrier_net_weight` stays 1. `barrier-split-ab2` done: `barrier_split=1` not adopted (legality guard). `barrier_split=2` (fit probe) pre-registered as `barrier-fit-ab` ([PLAN](../../../tools/kaeres/experiments/barrier-fit-ab/PLAN.md)); results pending.

## Mechanism
`kae.place.barriers.true_split` takes the outline less board-level rule areas that forbid tracks on every copper layer, drops pieces under 2% of the board, and when several regions remain assigns each part: anchored parts by their pads, movable parts by label propagation over signal nets, then power nets, then by area. Each region is then placed on its own with its own outline and only its parts, so a part cannot land across a split. `barrier_net_weight` multiplies the weight of nets whose seed MST edges cross a void or all-copper keepout on one-region boards.

## Facts from the scan
Of 3,310 usable boards (at most 1,500 pads) with outline holes, extra outlines or a track keepout, 332 are true splits: 274 have no all-copper keepout (separate outlines only), 58 have at least one (beems-mini-orion, one outline, is cut into three regions by an HV isolation rule area on both copper layers). The `slots` tag counts oval drills (connector pegs), not walls. On one-region boards leaving-edge counts alone do not cost opens (fortitude60, dilshan, E104), so the soft term must show opens, not only fewer crossings.

## Assembly and manufacture
A part on the wrong side of a panel split cannot be connected: a re-spin. Parts near a V-score or tab are at risk when the panel is broken. HV keepouts are the clearance the design was built around; a track across one fails DRC here and creepage at hipot.

## Results: barrier_net_weight (barrier-weight-ab2, 2026-11-13)
80 one-region boards with voids or all-copper keepouts, C vs W (`barrier_net_weight=3`), kae 4087578, staged joint-fixed with restarts, k = 1, the same task and the same explicitly set Freerouting build (fork 2e1125a) in both arms; arms ran side by side (median start gap 0.06 h; one board 13 h). Report: `~/kae-baselines/experiments/barrier-weight-ab2/REPORT.md`.

- **The weight acted on half the boards.** A seed-only re-run at 4087578 reweighted 435 nets on 40 of 79 boards; the other boards had no net crossing a barrier at the seed.
- **Score:** cp1 0.212 -> 0.212 (+1 / -1 board), completion 0.896 -> 0.894, `legal` 39 -> 38 boards. Open connections 1,451 -> 1,421 (ratio 0.979, 95 % CI 0.926-1.045; W lower on 22 boards, higher on 13, sign test p = 0.18). CPU 69.6 h -> 69.7 h.
- **Crossings did not fall:** recomputed on the final boards, crossing nets 377 -> 382 and MST edges 576 -> 557 (boards 15 lower, 11 higher, p = 0.56). Why is not measured (the stored runs keep no placer report).
- **DRC** errors 3,335 -> 3,418: copper_edge_clearance 668 -> 706, hole_clearance 107 -> 128 (one board), starved_thermal 45 -> 67, silk_overlap 4 -> 17 (one board); other types equal.
- Post-hoc only: on the 40 boards the weight touched, opens 973 -> 940 (15 lower, 5 higher, p = 0.04 uncorrected) with crossings 370 -> 377. On the 39 untouched boards, 478 -> 481, as an A/A would be.

**Verdict:** the pre-registered rule needs fewer crossings and fewer opens with no cp1 or legality loss. Crossings did not fall, the opens drop is inside the ~5 % the plan can see, and one board lost legality, so `barrier_net_weight` stays 1. A follow-up would pre-register only boards whose seed crosses a barrier, and must show crossings falling as well as opens; an opens gain without fewer crossings is not this mechanism.

## Results: barrier_split=1 (barrier-split-ab2, 2026-11-14)
100 true-split boards, C vs S (`barrier_split=1`), kae 4087578, staged joint-fixed with restarts, k = 1, Freerouting fork 2e1125a in both arms. Report: `~/kae-baselines/experiments/barrier-split-ab2/REPORT.md`.

- Opens 2,926 -> 2,621 (-10.4 %, ratio CI 0.78-0.99; S lower on 54, higher on 16, p < 0.0001). The split acted on 73 boards; the 27 it skipped (over capacity) behaved as an A/A (1,406 -> 1,390).
- `legal` 42 -> 36 (6 boards lost, 0 gained, McNemar p = 0.03): past the 3 pp guard, so not adopted. DRC errors 5,034 -> 5,247.
- Post hoc: no part moved for room (59 boards) opens 1,070 -> 678; parts moved for room (14 boards) 450 -> 553, legal 7 -> 3.

## Why moving parts broke legality (2026-11-14)
Placement-only reruns of the split on the prepared task inputs (ab2 code) and the kept attempts' ranks:
1. All 7 boards whose split arm kept an illegal placement (restart `--check-placement`) are among the 14 with parts moved for room; no board without moves had one.
2. On every moved board with an illegal region, that region is the one parts were moved out of. The parts left illegal are not the moved ones (0 of 11-20 per board). Its front side is 75-82 % used by the placer's own measure: the area test (`CAPACITY` 0.85 of the region per side) passed once enough parts had left, but courtyard area is not room. len42 audiout: a eurorack panel region holds 10 fixed jacks and pots and kept 7 movable parts; the legalizer found no spot for the two DIPs (U2, U3: "no spot clean of the outline, locked parts and rule areas").
3. The moves themselves pointed the right way: on len42 audiout the 41 parts moved are where the human placed them (0 of 48 before the moves, 41 after); on the len42 boards label propagation from the panel's anchored jacks first sends every part to the panel.
4. Placement-level legality on the boards scanned: control legal on all 9 moved boards, `barrier_split=1` on 4.

So the fix is a real fit test, not fewer moves: `fit_split` (`barrier_split=2`) probes each region with the placer's seed and legalizer, moves the parts a region finds no spot for to the region they are most tied to, probes again, and places the board whole if a region still cannot hold its parts. On len42 audiout it moves 4 parts in 2 rounds, cuts signal nets across regions 33 -> 22 and the placement is legal.

## Open questions
`barrier_split=2`: results of `barrier-fit-ab` on 120 (up to 211) fresh true-split boards.
