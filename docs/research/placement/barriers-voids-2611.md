<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Voids, slots and all-layer keepouts as barriers (2026-11-09)

Scope: E104, E105: keeping parts and nets off barriers the router cannot cross. Not here: the region scan method -> stage 1.
Keys: barrier split, true region split, voids, slots, HV keepout, rule area, barrier_split, barrier_net_weight, kae.place.barriers, barrier-ab, E104, E105

**Status:** experiments `barrier-split-ab2`, `barrier-weight-ab2` queued ([PLAN](../../../tools/kaeres/experiments/barrier-ab/PLAN.md)); no results yet.

## Mechanism
`kae.place.barriers.true_split` takes the outline less board-level rule areas that forbid tracks on every copper layer, drops pieces under 2% of the board, and when several regions remain assigns each part: anchored parts by their pads, movable parts by label propagation over signal nets, then power nets, then by area. Each region is then placed on its own with its own outline and only its parts, so a part cannot land across a split. `barrier_net_weight` multiplies the weight of nets whose seed MST edges cross a void or all-copper keepout on one-region boards.

## Facts from the scan
Of 3,310 usable boards (at most 1,500 pads) with outline holes, extra outlines or a track keepout, 332 are true splits: 274 have no all-copper keepout (separate outlines only), 58 have at least one (beems-mini-orion, one outline, is cut into three regions by an HV isolation rule area on both copper layers). The `slots` tag counts oval drills (connector pegs), not walls. On one-region boards leaving-edge counts alone do not cost opens (fortitude60, dilshan, E104), so the soft term must show opens, not only fewer crossings.

## Assembly and manufacture
A part on the wrong side of a panel split cannot be connected: a re-spin. Parts near a V-score or tab are at risk when the panel is broken. HV keepouts are the clearance the design was built around; a track across one fails DRC here and creepage at hipot.

## Open questions
Results when `barrier-ab` finishes.
