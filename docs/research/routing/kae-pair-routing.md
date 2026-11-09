<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Routing differential pairs as pairs (E37, R61, 2026-11)

Scope: kae's pair router and where it runs in the pipeline. Not here: which nets are a pair, how a pair is measured, hazards -> [kae-diff-pair-report](kae-diff-pair-report.md); pair physics and rules -> [diff-pairs](../../topics/rules/diff-pairs.md); router survey -> [diff-pair-routing](../../topics/routing/diff-pair-routing.md).
Keys: kae.route.pair_route, pairs first, pair envelope, spine, fan-in, skew bump, stitching vias, pseudo-net, post-pass, diffpair-ab

**Status:** built; A/B `diffpair-ab3` (first and post against the bridge, 120 boards, pre-registered) queued 2026-11-09, no result yet. **First published:** 2026-11-09, branch `diffpair-route`.

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
