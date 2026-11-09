<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Anchoring tight parts: big parts with no spot free of the fixed geometry

Scope: why three boards with clean human layouts were never legal under kae placement, and the fix in `kae.place.pipeline`. Not here: legality in general -> [kae-exact-legality](kae-exact-legality.md).
Keys: legality, anchor_tight, tight part, courtyard overhang, allow_overhang, kae.place.pipeline._anchor_tight_parts, J19, openremise, vik-pmw3360, esp32 flight controller

**Status:** not finished: mechanism and root cause verified, the deciding A/B (`loop-legal-ab`) queued.
**First published:** 2026-11-09, branch `loop-legality`.

## The failure

Stored runs (one evaluator per run, joint-fixed task, kae staged and joint arms): on boards with no placement error in the human layout,

| Board | Legal runs | Placement errors (typical run) | The part |
|---|---|---|---|
| openremise-sniffer | 0 of 15 | shorting_items, pth_inside_courtyard, npth_inside_courtyard | A1, a Raspberry Pi Pico module, 54 mm tall on a 61.6 mm board, with a USB cable keep-out it owns |
| esp32 flight controller | 0 of 18 | items_not_allowed, courtyards_overlap, shorting_items, clearance | U1, an ESP32 dev board |
| vik-pmw3360 | 2 of 19 | clearance, hole_to_hole, copper_edge_clearance | U1001, a sensor carrier |

In each the failing items are one big part against connectors, mounting holes or the outline the task holds fixed. `legal_strict` agrees with `legal` on the fixed runs so far (esp32 and openremise, one seed each).

## Root cause

The placer's check that a part can go anywhere (`Problem._fit_check`) asks one thing: does the courtyard rectangle fit inside the outline? On these boards it does, on an empty board. With the fixed connectors standing, no spot remains. Openremise's Pico needs its courtyard 1.7 mm over the top edge, which is what the human layout does: KiCad checks copper against the edge, not courtyards.

The rule for that exists (`Problem.allow_overhang`), but only as an escalation step of the closed exact repair, after the first re-seed, and on a part the annealer has spent the whole run failing to legalize. The repair then has no time left: on openremise the closed loop got 5 s of its budget, found 11 findings, moved nothing (`reseeds: []`), and diagnosed `no_room`. On that board the annealer ran out its budget with the part illegal: 10,000 of 172,000 planned moves at 102 moves/s without the fix, against 560,000 moves at 36,544 moves/s with it (one run each; why the rate differs that much is not established).

There is a second, smaller layer: the grid's rectangles of a fixed through-hole part (the pad inflated by its clearance) are a conservative cover, so on openremise no grid-free spot exists even with the overhang. The exact check is the judge there: it accepts the human pose.

## The fix

`_anchor_tight_parts` runs once after the problem is built, on parts with a courtyard over 5 % of the board (body-only parts such as logos stay with `relax_bodies`: a first version anchored them too, caught by the scan before any run). A part with no grid spot free of the fixed geometry (every other movable part aside) gets the overhang and is placed at the first exactly clean spot, biggest part first, ranked by hugging an edge (the rest of the board stays in one piece; a keep-out or courtyard hanging off the board costs nothing). It is then fixed like a locked part for every later stage. A part with no exactly clean spot is left to the normal stages, overhang kept. `--set anchor_tight=0` turns it off.

## Numbers so far

`kae place` alone, 95 s budget, KiCad judging the placement through the benchmark's transplant (before = main, after = branch):

| Board | Seed | Before | After |
|---|---|---|---|
| openremise-sniffer | 2 | illegal (11 exact findings, `no_room`) | legal, 30 s total (was 178 s) |
| esp32 flight controller | 2 | not run on this seed; stored runs 0 of 18 legal | legal |
| vik-pmw3360 | 2, 3 | illegal: copper_edge_clearance; clearance, copper_edge_clearance, hole_to_hole | legal, legal |

These are single-seed placements, not routed results. The experiment that decides, `tools/kaeres/experiments/loop-legal-ab/`, runs the full staged and joint chains on the boards where a part is anchored.

## Scope of the change

The code path does nothing unless a part over 5 % of the board has no spot free of the fixed geometry, so boards without such a part are untouched.

## Open

- Choosing among exactly clean spots by connectivity rather than edge-hugging. The current ranking is a heuristic: it never competes with an alternative here because the alternative was no legal spot at all.
- Exact-model false positive noted at openremise's human pose (R2 inside A1's keep-out, reported by the exact check and not by KiCad).
