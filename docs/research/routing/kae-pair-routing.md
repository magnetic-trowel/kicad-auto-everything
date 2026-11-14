<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Routing differential pairs as pairs (E37, R61, 2026-11)

Scope: kae's pair router and where it runs in the pipeline. Not here: which nets are a pair, how a pair is measured, hazards -> [kae-diff-pair-report](kae-diff-pair-report.md); pair physics and rules -> [diff-pairs](../../topics/rules/diff-pairs.md); router survey -> [diff-pair-routing](../../topics/routing/diff-pair-routing.md).
Keys: kae.route.pair_route, pairs first, pair envelope, spine, fan-in, skew bump, stitching vias, pseudo-net, post-pass, diffpair-ab

**Status:** failed its A/B (`diffpair-ab3`, 2026-11-14): not merged; kept on branch `diffpair-route`. **First published:** 2026-11-09, branch `diffpair-route`.

## What a pair needs, and when it can be built

| Need | Physics | Consequence for the router |
|---|---|---|
| Coupling | a pair is one line; each leg alone is a different line with the wrong Z and no field cancellation | the legs must be searched together, not as two nets |
| Skew at the receiver | common mode from skew: V_cm = dV dt/(2 t_r) | compensate near the mismatch; a corner gives the outer leg 2p tan(theta/2) |
| Return path | each leg returns under itself on the adjacent plane | price cells with no adjacent plane; a pair crossing a split is the case to avoid |
| Via symmetry | equal count on both legs, side by side | a pair via is one object with two barrels |
| Via return | current changes reference at a layer change | ground via beside the signal via when the plane changes |

These are the most constrained nets on the board, and the freedom they need exists only early. A router that has already placed the rest leaves a corridor of one trace's width; the second leg has nowhere to go (Freerouting's outputs here: at most 17 % of a leg at constant pitch, [taut](kae-taut-arcs.md)). So the pair is routed first, as locked copper, and everything else goes around it. This is what designers and the commercial tools do (Situs, DeepPCB: route pairs first and lock).

## Alternatives considered

**Pseudo-net in the DSN** (r2's suggestion: a net of width 2w+g, split afterwards) would let Freerouting's rip-up treat the pair like any other net, so congestion would be shared. Rejected without a prototype, for reasons that compound: a trace only connects to a Freerouting pin at its exact centre, so each pair end needs a pseudo-pin at the pads' midpoint with the real pads hidden as obstacles; a via must be one padstack wide enough to hold two real vias side by side (about 1.4 mm), which dense boards cannot place; the split must offset a push-and-shove wire and re-join two pads per end, inside `translate.fix_session`; and all of the repair loop then sees nets the DSN never had. It remains the fallback if pairs-first leaves too many opens on dense boards.

**Post-pass** (`--pairs post`, `pair_route.post_pass` plus the last mile, kept only if KiCad finds the board no worse): the routed board's pairs are re-laid as pairs in place, per pair (old copper ripped, restored on failure), so it can never lose a connection it had. But it needs a free strip 2w+g wide where the first route left one trace, so it works where room exists.

A comparison on 13 boards at 400 s (one per repo family, real pairs from `if_*` and `diffpair_*` tags, boards routed once each; post had a last mile on top of its time budget, so its opens are flattered):

| arm | opens | errors | coupled median (by board) | skew median, mm (by board) |
|---|---|---|---|---|
| control | 803 | 803 | 0.07 | 2.14 |
| first | 950 | 799 | 0.615 | 0.51 |
| post | 677 | 820 | 0.246 | 2.07 |

Pairs first gives the coupling and skew a reviewer wants; it cost opens on dense boards (felixheld 44 to 144, olimex 91 to 123, pcbcorpus 25 to 50, against gains elsewhere), plausibly because the locked pairs close corridors the rest needs; the cause is not yet read. Post cannot break what the general router connected, but it left most pairs at or near the control's coupling on the boards where the pair's strip was not free. Both go to the A/B.

## The router (`kae.route.pair_route`)

1. **Ends.** Each P pad is matched with its nearest N pad (same footprint first, within 6 mm); an end is their midpoint, and any same-net pad within 1.6 mm is also a landing site (a USB-C row has the partner on both sides). Pairs whose pads are nowhere paired stay with the bridge.
2. **Spine.** One A* (kae.route.critical_grid) over the pair's envelope, width 2w+g, with the two nets merged (`merged`: the partner's pads and tracks are not obstacles) so the legs are one object. Layers from the stackup; inner plane layers out. Cells without an adjacent plane cost 1.5x, a pair via 8 mm-equivalents and only where two side-by-side real vias fit on one of four axes (`PairGrid.via_allowed`). The spine starts in a disc around each end, trying radii 0.4 to 4.5 mm: the discs stop at the first radius whose legs and fan-ins close.
3. **Legs** at centreline +- (w+g)/2, mitred; at a via they flare to the two via centres on the chosen axis; polarity set to shorten the fan-ins. Each leg checked exactly (`Space.track_violations`) with real nets; ends that clear only narrowly against the partner's pad are left to the fan-in.
4. **Fan-in** with `GridRouter.connect` at the pair's width, then at the board minimum (a neck into a fine-pitch pad). Both orders of the two legs are tried, farther pad first.
5. **Skew.** Bumps of at most 1.5 mm on the shorter leg, each checked exactly, until skew <= 0.1 mm.
6. **Return vias** (`stitch`): a ground via next to each signal via when ground covers the location.

Width and gap are the board's: `diff_pair_gap` custom rules, then the net class's `diff_pair_width`/`diff_pair_gap`, clamped by KiCad's own clearance for the pair. Everything is locked; pairs that do not close are left to the bridge and listed in the report.

Runs: `kae.route.cli route --pairs first` or `--pairs post` (`opts["pairs"]`, off by default). A pair the spine or the fan-ins cannot close stays with the general router.

## A/B result (diffpair-ab3, 2026-11-14)

Pre-registered (`tools/kaeres/experiments/diffpair-ab/PLAN.md`, amended 2026-11-11 to the bus scorecard). 120 boards with real pairs, one per repo family; control, first and post at 486f2f1, 900 s, k = 1, run side by side; pairs from bus scorecards (evaluator `0ff1f9452b8d`), tier from the human board. Intervals: 95 % bootstrap over boards.

| | control | first | post |
|---|---|---|---|
| pairs measured (boards) | | 413 (75) | 473 (72) |
| coupled_3w median | 0.147 / 0.125 | 0.738 | 0.25 |
| coupled change, median paired | | +0.40 [0.30, 0.51] | 0.00 [0, 0] |
| skew median, mm | 1.91 / 2.04 | 0.63 | 2.01 |
| skew ratio, median paired | | 0.36 [0.29, 0.48] | 1.00 |
| vias per pair change, mean | | -1.47 [-1.83, -1.14] | +0.03 |
| opens (total 12,367) | | +15.6 % [8.2, 28] | +11.1 % [6.7, 18] |
| DRC errors (total 8,633) | | +5.0 % [0.1, 17.5] | +13.8 % [8.5, 21] |
| clean boards (cp1) | 6 (0.05) | 3 (0.025) | 6 (0.05) |
| completion, mean | 0.844 | 0.821 | 0.819 |
| CPU s, mean | 938 | 891 | 802 |
| physics Σu ratio, both complete | | 0.999 (n 17) | 1.000 (n 23) |

New error types: first `track_width` 0 to 199 and `diff_pair_gap_out_of_range` 0 to 173 (defects of the pair router: fan-in necks below a rule's minimum, legs outside a gap rule's maximum), `starved_thermal` 45 to 82; post `starved_thermal` 45 to 1,008 (its 240 s reserve came out of the repair rounds), `track_width` 78.

**Verdict: fail for both arms.** First makes the pairs a reviewer wants (coupled 0.15 to 0.74, skew a third, 1.5 fewer vias per pair; the gain holds across planes and layer changes: pairs crossing a plane change in control, coupled 0.06 to 0.76, plane changes per pair 2.9 to 1.1), but the coupled interval's lower end (0.296) touches the +0.30 threshold, and both guardrails fail: 16 % more opens (73 boards worse, 24 better) and new rule errors. Post fails its primaries: it re-laid almost nothing (median change 0), and cost opens and errors through the time it took from repair. No extension: the opens interval lies wholly above +5 %.

What would change it: first without its rule defects (necks only to the rule's own minimum, legs held inside `diff_pair_gap` max) and with the locked pairs no longer closing corridors (pairs routed first but unlocked, or opens-guarded per pair), re-tested as a new pre-registered A/B.
