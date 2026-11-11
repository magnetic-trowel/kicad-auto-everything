<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Anchoring tight parts: big parts with no spot free of the fixed geometry

Scope: why three boards with clean human layouts were never legal under kae placement, and the fix in `kae.place.pipeline`. Not here: legality in general -> [kae-exact-legality](kae-exact-legality.md).
Keys: legality, anchor_tight, tight part, courtyard overhang, allow_overhang, kae.place.pipeline._anchor_tight_parts, J19, openremise, vik-pmw3360, esp32 flight controller

**Status:** partial, not merged. The root cause is verified. A second version (KiCad-verified spots, `loop-legal-ab2`, 60 boards) cuts placement errors 29 % with strong significance in both chains, but fails its pre-registered guard: three small module carriers lose legality to pads hanging off the board edge.
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

`_anchor_tight_parts` runs once after the problem is built, on parts over 5 % of the board that have a courtyard or a connected pad. Logos and similar parts with neither stay with `relax_bodies`: a first version anchored them too (the scan caught it before any run), and a second that required a courtyard dropped vik-pmw3360's sensor carrier, which has a body and connected pads but no courtyard. A part with no grid spot free of the fixed geometry (every other movable part aside) gets the overhang and is placed at the first exactly clean spot, biggest part first, ranked by hugging an edge (the rest of the board stays in one piece; a keep-out or courtyard hanging off the board costs nothing). It is then fixed like a locked part for every later stage. A part with no exactly clean spot is left to the normal stages, overhang kept. `--set anchor_tight=0` turns it off.

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

## A/B: `loop-legal-ab` (2026-11-10)

Plan: `tools/kaeres/experiments/loop-legal-ab/PLAN.md` (pre-registered). Commit dbc70f5: anchors parts with a courtyard or a connected pad. f2f4151 required a courtyard, which dropped vik-pmw3360's carrier, and was corrected before this ran. Boards: the 20 merit boards where the scan finds a tight part (13 anchored, 7 overhang only). Seeds 0-2, J1's restart wrapper, arms interleaved; KiCad scored 240 of 240 runs.

| arm | legal | legal_strict | clean | completion | opens | errors | placement errors | CPU h |
|---|---|---|---|---|---|---|---|---|
| staged, anchoring off | 18 | 18 | 6 | 0.938 | 424 | 2,382 | 912 | 48.4 |
| staged, anchoring on | 21 | 21 | 9 | 0.957 | 326 | 1,699 | 786 | 51.7 |
| joint, anchoring off | 17 | 17 | 6 | 0.951 | 423 | 2,466 | 961 | 49.2 |
| joint, anchoring on | 21 | 21 | 8 | 0.949 | 441 | 1,647 | 733 | 55.0 |

Legal, anchored against control over 60 board x seed cells: Fisher p 0.70 (staged), 0.56 (joint). The pre-registered rule needs p < 0.05, so **it fails**. Most of these boards are illegal for every arm (12 of 20 at 0 of 3 in all four, mostly fixed parts already in conflict in the task input), so the test has few cells that can move.

Placement errors by type, off / on (staged; joint): shorting_items 139 / 115 (139 / 51), pth_inside_courtyard 69 / 0 (76 / 6), courtyards_overlap 39 / 18 (42 / 18), items_not_allowed 25 / 0 (42 / 0), hole_to_hole 1 / 0 (3 / 0); copper_edge_clearance 286 / 294 (289 / 296) and hole_clearance 120 / 126 (120 / 126) rise slightly.

The three boards (legal of 3 seeds, off → on, staged; joint):
- openremise-sniffer: 0 → 3; 0 → 3. Errors 30 → 2; 32 → 1.
- esp32 flight controller: 0 → 3; 0 → 3. Opens 31 → 1; 40 → 7. Errors 83 → 0; 95 → 0.
- vik-pmw3360: 3 → 3; 2 → 3. At this commit the control is mostly legal already, unlike the 2 of 19 stored runs, which came from older code.

The regression: melexinvn-bs-kombo goes from 3 of 3 legal to 0 of 3 in both chains, KiCad reporting 2 hole_clearance errors. Its connector J2 has no grid-free spot, so it was anchored at a spot only the exact check judged. That check passes a hole clearance KiCad then flags, while the control's closed loop found a legal spot anyway. sparkfun-sparkpunk shows the same pattern (BAT1, +2 clearance errors, illegal in every arm). Opens: staged 424 → 326, joint 423 → 441 (+4 %, above the 2.8 % A/A floor). lenaschimmel-bestelampe accounts for most of that rise (42 → 75), and there the part is only given the overhang, not anchored.

**Next.** Keep anchoring for grid-free spots. For a spot only the exact check accepts (openremise needs one), verify it with KiCad's DRC of the placed part before fixing it, or else fall back to the overhang only. Then rerun on these 20 boards. Separately, the exact model's hole_clearance blind spot needs a case of its own.

## Second A/B: `loop-legal-ab2` (2026-11-10)

Plan: `tools/kaeres/experiments/loop-legal-ab2/PLAN.md` on branch `loop-legal-exp2` (commit 9260dbb), pre-registered.
- Change since the first A/B: a spot only the exact check accepts is fixed only if KiCad's DRC agrees, else the part keeps the overhang.
- Both arms carry PR #52's arc fix.
- Boards: 60 tight-part boards (scans of the merit suite, the stored outputs and the qualified corpus), seeds 0-2, J1's restart wrapper. KiCad scored all 720 runs.

| arm | legal | legal_strict | clean | opens | errors | placement errors | CPU h |
|---|---|---|---|---|---|---|---|
| staged, anchoring off | 105 | 104 | 73 | 1,095 | 3,294 | 1,582 | 103.8 |
| staged, anchoring on | 114 | 110 | 77 | 1,134 | 2,260 | 1,148 | 101.5 |
| joint, anchoring off | 105 | 104 | 72 | 1,327 | 3,339 | 1,574 | 116.1 |
| joint, anchoring on | 114 | 111 | 71 | 1,295 | 2,296 | 1,128 | 117.4 |

**Primary passes.** Placement errors per board, paired: staged 9 boards fewer and 2 more, mean d −0.107, p 0.010; joint 10 fewer and 1 more, mean d −0.122, p 0.005. Both are under the plan's 0.025.

By type, off → on (staged; joint):

| Type | staged | joint |
|---|---|---|
| shorting_items | 252 → 79 | 206 → 57 |
| pth_inside_courtyard | 147 → 0 | 151 → 6 |
| courtyards_overlap | 146 → 133 | 176 → 128 |
| items_not_allowed | 61 → 36 | 69 → 36 |
| hole_to_hole | 10 → 1 | 8 → 0 |
| copper_edge_clearance | 465 → 442 | 470 → 444 |
| clearance | 368 → 334 | 356 → 334 |

**The guard fails, so the experiment fails.**
- Three boards legal 3 of 3 under control are 0 of 3 with the change, in both chains: mikeysklar-c7kfo-nicenano-breakout, sparkybobo-dmxdemonstrator-receiver-io and vail-cw-vail-adapter-vail-v1-pcb.
- Each is a tiny carrier (4-6 parts) whose only free part is the anchored module (nice!nano, QT Py). None has a KiCad placement error. All three are illegal by the benchmark's `outside` rule.
- Cause (corrected 2026-11-10, after reproducing it): with the module anchored, no free part was left. `place()` then took its "nothing to place" return, which wrote no poses, so the module stayed at its staged pose off the board. Routing to it added copper_edge errors.
- A first reading blamed the straddle allowance; the reproduction showed the module was never written.
- Fixed in commit "write anchored poses when no free part is left", with a regression test. On seeds 0 and 1, all three boards are legal.
- Staged opens also rise 3.6 % (1,095 → 1,134), beyond the plan's +3 % bound; joint opens fall 2.4 %.

The known boards, legal of 3 seeds (staged; joint, off → on):
- openremise: 0 → 3; 0 → 3.
- esp32 flight: 0 → 3; 0 → 3.
- vik-pmw3360: 3 → 3; 1 → 3.
- melexinvn: 3 → 3; 3 → 3. The first version's regression is fixed by the KiCad check.
- Also fixed, 0 → 3 in both chains: meo98-picostack, hollyrock-ecoconnect, 0rax-xiao-base; zlosynth goes 0-1 → 3.

**Next.** Fix the write, and also require every pad centre of an anchored spot on the board. Then pre-register a third run on the same 60 boards (`loop-legal-ab3`), not this run's 103-board extension.
