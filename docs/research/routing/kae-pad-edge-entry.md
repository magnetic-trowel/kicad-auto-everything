<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# kae pad-edge entry: end a track at the pad edge it approaches, not at the centre

**Status:** partial. Rule D (`pad_reroute --target centreline`, the default) fixed 419 of 636 oblique, sliver-prone or overhanging entries on 12 boards (acute 107 → 44, oblique 581 → 241), every end on the pad's long centre line or as near as the land allows, no copper past the land; DRC never worse. The edge rule fixed 397. The end-only post-pass (`kae.route.pad_trim`) cut 4 % of track but barely changed angles. The in-router option gained nothing on a 2-board A/B. All three are off by default.
**First published:** 2026-11-03, branch `pad-edge-entry` (off `power-copper`).

Every routing stage aimed at a pad's centre. A connection only needs to reach the pad's copper; the run to the centre is copper inside the land (or a bulge beside it), and the snap to the centre adds a last piece at whatever angle the centre lies.

## Where the ends were set (survey, branch base d1f36d6)

| Stage | Where | End |
|---|---|---|
| Freerouting (bridge) | DSN pins are KiCad's padstacks; no pin-entry setting is written | always the pin centre: a pin's connection shape is its centre point (`DrillItem.getTraceConnectionShape`); a trace touches a pin only when its end equals it (`Trace.getNormalContacts`). `pin_edge_to_turn_dist` (straight run out of a box pad's short side) is switched off while the autorouter inserts a route (`FoundConnectionInserter`) |
| Grid router (last mile, critical modules and rails, plane escapes) | `critical_grid.GridRouter._geometry` / `_snap_end` | the A* ends in any free cell inside the pad; `_snap_end` then moves the end onto the centre when that piece is legal |
| Rim entries | `critical_grid._escapes` (`pad_entry_overlap`, 0.05 mm) | already off-centre: the end may sit past a tight pad while overlapping it |
| Escape stage | `escape.dog_bone`, `escape` grid routes | centre to via / tile, on purpose (via between balls) |
| Repair (starved thermals) | `repair.py` ray from the pad centre into the fill | centre (a ground joint) |
| Power copper | `power_copper.ground_vias` (centre to via), widening of existing tracks, necks | centre; necks measure tracks that touch the land |

## How it works

- **Geometry** (`kae.route.pad_entry`). From the last path point outside the pad: the nearest edge (where it faces a corner, the edge it lies most squarely in front of); on a straight edge at least the track width long, the foot of the approach, kept half a width from the corners, so the whole width lands on one edge; on a round pad or short chord, radially. The path turns onto the edge normal a width before the edge and ends `pad_entry_overlap` inside, along its own axis. A direct piece is a second candidate only within 20° of the normal. Acute copper wedges are acid traps ([rf](../../topics/rules/rf.md) "acute angles are an acid-trap fab concern", [autorouter-skepticism](../../topics/routing/autorouter-skepticism.md) cleanup metric).
- **Current.** Rails and grounds (name rules of `physics.provisional_brief`) and tracks wider than their class width (in the post-pass: 0.4 mm or wider) enter at the middle of the edge, a width deep: an edge entry would otherwise halve the joint. The post-pass leaves their centre ends alone by default (`--rails centre`; physics below). An end that would pass the centre, or whose round end would leave the far side of the pad, keeps the centre.
- **Grid router.** With `pad_entry=edge`, `_geometry` string-pulls first, then `_edge_end` replaces the tail inside the pad; each new piece must pass `Space.track_violations` exactly, else the centre snap runs as before. The escape stage's router is pinned to `centre`.
- **Freerouting's view.** A wire ending off the pin centre reads as a tail and its pin as open, so `translate.tie_pins` adds a `(type fix)` 0.05 mm wire from each such end to the centre in the DSN. Fixed wiring is never written to the session, so the board keeps the edge end.
- **Post-pass** (`python -m kae.route.pad_trim trim IN OUT --report R.json`, like `power_copper`). On any routed board, a segment from a same-net pad centre to a point outside the pad is cut back to `pad_entry_overlap` inside the edge it crosses. One entering more than 10° off the normal is re-ended within that segment where every piece is exactly legal. Skipped: via-ended segments (dog-bones, fan-outs), lands holding a via (heat pads, via-in-pad), ball grids (≥ 9 round SMD pads), and by default rails, grounds and wide tracks. A worse DRC (by error type, or unconnected count) reverts in steps: 1 mm, then 2.5 mm, around each new violation, then re-ends, then all. With `pad_entry=edge` the bridge runs the plain cut last.
- **Setting.** `pad_entry` (`constraints.DEFAULTS`): project text variable `KAE_PAD_ENTRY`, opts, else env `KAE_PAD_ENTRY`.

What does not change: the neck rule (power copper's necks find tracks by contact, and current-carrying tracks enter centred), the escape stage, Freerouting's own routing.

## Results

All per-board tables are in [results](../../../bench/results/2026-11-04-pad-edge-entry-59caa02.md). 12 boards: the 10-board power-copper smoke set plus chips-0123 (WLP) and nekoink (BGA), each the merge3-ab `kae-bridge-main-final` output; nothing is re-routed whole.

### End-only post-pass (`pad_trim`)

- **DRC never worse**, every change kept on the first check; cm4-carrier lost 4 `solder_mask_bridge` and 3 `clearance` errors (Freerouting's tracks had bulged beside lands). KiCad's `solder_mask_bridge` count on the unchanged magtag board is 24 or 25 from run to run, so the gate reverts in steps.
- **Track** −4 % (19.70 → 18.86 m), all inside lands. **Angles barely move** (581/107 → 567/94): a cut keeps its track's angle; 47 of 2,113 ends could be re-ended within one segment. Balls and dog-bones are skipped.
- **Physics.** With rails cut a width deep, rail drop and copper loss rose up to 1.4 %; with rails left at the centre (the default), no board got worse by more than 0.2 %.

### Tail re-route (`kae.route.pad_reroute`, 2026-11-04)

`python -m kae.route.pad_reroute IN OUT --report R.json` re-routes several segments where `pad_trim` changed only the last.
- **Entries:** more than 10° off the edge normal, or centre-aimed with sliver risk (copper beside the land over 2× what a perpendicular entry leaves).
- **Release:** the first via, junction (a T-junction mid-segment included), width change, arc or other pad within R; else a cut at R = max(3 widths, 1 mm), then 2, then 4 mm.
- **Target:** `pad_entry.approach_targets`. An approach point one width outside the edge the release point faces, then straight in along the normal, overlap-deep. Rails, grounds and 0.4 mm+ tracks enter at the edge middle, a width deep (`--rails middle`; `--rails centre` leaves them).
- **Route:** the grid router, same width, no vias, the land kept out of the search; 45/90° doglegs on boards whose tracks are 90 % or more 45/90°.
- **Accept:** every piece exactly legal, the tail at most 1 mm + 20 % longer, then whole-board DRC no worse; otherwise the old tail stays.
- **Not touched:** as in `pad_trim`, plus locked tracks. Touching same-net shapes (THT with an SMD twin, custom pads) count as one land, here and in the counts.

Re-route then trim, totals over the 12 boards:

| | Oblique / acute | Track m | Vias |
|---|---|---|---|
| Original | 581 / 107 | 19.70 | 1488 |
| `pad_trim` | 567 / 94 | 18.86 | 1488 |
| re-route + trim, rails into the edge middle | 249 / 46 | 18.89 | 1488 |
| re-route + trim, rails left at the centre | 365 / 75 | 18.89 | 1488 |

- **Fixed:** 397 of 624 candidates; 136 skipped by rule (via-ended stubs, vias in the land); 91 failed (no route 29, no admissible edge 29, release point at the land 20, other 13). DRC reverted none.
- **DRC:** no board worse in any type; cm4-carrier 612 → 608 errors. No vias added; tails 65 mm shorter. 199 s for all 12 boards.
- **Physics** (10 boards): with rail tails into the edge middle, 8 moved by 0.4 % or less; lenaschimmel 1.5 % better, aifryz 1.1 % worse. With rail tails left at the centre, all within 0.4 %.

### Rule D: end on the long centre line (`--target centreline`, the default since 2026-11-04)

The edge rule ends a track `pad_entry_overlap` past the edge it reaches. Rule D (`pad_entry.centreline_targets`) ends it on the pad's long centre line instead: the segment along the long axis between the points (w − h)/2 from the centre. For round and near-square pads (|w − h| ≤ 10 % of w) that is the centre point; for an oval it is the segment between the end-circle centres. The track then sits centred across the pad. The straight piece that crosses the outline must be within 10° of the outline's normal there.
- **Path.** Straight from the approach direction to the nearest centre-line point if that line already crosses within 10°, with no corner. Otherwise the shortest legal of (a) a corner one width outside the long edge the release point faces, then in along its normal, and (b) a corner one width outside the short edge on the axis, then along the axis to the centre line's end. A round end (stadium, round pad) is entered radially.
- **Choice.** Every candidate is routed and the shortest legal one kept; no copper may hang past the land (below). Rails get no special case; where no target is reachable legally, the old tail stays.
- **Unchanged.** Release walk, grid search, exact legality, DRC gate, length limit and skip rules. `--target edge` keeps the edge rule.

On the same 12 boards, both rules from the original outputs (per board in the [results](../../../bench/results/2026-11-04-pad-edge-entry-59caa02.md#4-rule-d-against-the-edge-rule)):

| | Kept | Oblique / acute | Ends on the centre line | Track m | DRC reverted | Time s |
|---|---|---|---|---|---|---|
| Original | – | 581 / 107 | 2922 of 3385 | 19.70 | – | – |
| Edge rule | 397 | 252 / 48 | 2613 | 19.64 | 0 | 229 |
| Rule D | 414 | 240 / 44 | 3016 | 19.74 | 19 | 258 |

- **Fixed:** D re-routed 433 of 624 candidates and DRC kept 414 (edge rule: 397). D failed fewer: no route 27, release point at the land 20, tail shared 4, too long 2, no 45/90° dogleg 1, illegal final piece 1. It never lacked a target (the edge rule had 29 such failures: no edge long enough for the width).
- **Board by board:** D fixed more on 9 boards and fewer on 2. On cm4-carrier it kept 3 against 18: 16 long-edge re-routes into fine-pitch lands were reverted for 4 new `solder_mask_bridge` errors. On dream, 3 were reverted for one unconnected.
- **DRC:** after the gate, no board worse in any error type. nekoink has one more `track_dangling` warning: a 0.1 mm stub where a tail was split at a tap that overlapped it 0.05 mm off its centreline (still connected).
- **Track:** +36 mm against −65 mm for the edge rule, since D runs on to the centre line. No vias added.
- **Physics** (rails as D routes them): 8 of 10 boards within 0.25 %, as with the edge rule. lenaschimmel improved 1.7 % (edge rule 1.5 %). aifryz got 5.1 % worse (S4/S7 supply peak 1.305 → 1.377 V); the edge rule cost 1.1 % there. D re-routes 8 segments of +BATT on aifryz that the edge rule did not touch. `--rails centre` leaves rail, ground and wide-track tails as they are under D too.

### Tracks wider than the land (2026-11-04)

Rule D tested only that a track's round end stayed inside the pad along its direction of travel. A 0.8 or 1.2 mm track into a 1.0 × 0.6 mm land got the axial entry, its sides 0.1–0.3 mm past both long edges: copper beside the land enlarges the joint (tombstoning, solder wicking; [dfm-fab-limits](../../topics/rules/dfm-fab-limits.md), [necks](kae-power-copper.md#necks-at-small-lands-tombstoning-and-manufacturability-2026-11-03)). The long-edge entry, which overhangs less, was dropped for its tip. A 1.0 mm track had no target on a 0.6 mm square land and kept its oblique centre-aimed tail.
- **Overhang** (`pad_entry.overhang`). The final piece buffered by w/2, minus the pad and the pad's shadow toward the approach (the pad swept back along the piece). The shadow is what any track arriving that way needs (the approach, and shoulders at a round outline); what is left hangs past the land or out of its far side. At most 2·10⁻⁴ mm² is allowed (copper within 5 µm of the outline counts as on it). Measured against copper (the DSN export has no mask openings; copper beside a land is exposed land or a heat sink under mask).
- **One rule for all candidates** (`centreline_targets`). A round end that pokes out is pulled back along the piece, at least 0.05 mm inside. A long-edge entry whose width hangs past the edge's ends slides toward the edge's middle. A 0.8 mm track into the 1.0 × 0.6 land now enters through the long edge.
- **Neck** (`neck_width`, `pad_reroute._neck_or_wide`). When nothing fits, the last piece takes the widest width that does, in 0.01 mm steps. It is at most the land width (short side) and at least the board minimum and what the pad's current needs (`power_copper.current_need`, IPC-2221 at 3 × I, the floor of `neck_rule`). The wide copper ends neck_len + w/2 (0.5 mm + w/2) before the outline, and its route keeps that far from the land. The width steps at the wide track's round end (an obtuse corner). Pad currents: `power_copper.pad_currents` on the operating facts (`--operating` or `KAE_OPERATING`), by the neck's rules.
- **Hazard.** If the current needs more than any entry allows (or than the land), the wide copper stays (rule D with the tip test alone) and the report gets `land_enlarged_by_track` (warn, assembly) in the [hazards](../../topics/architecture/hazards.md) schema of `decide-2611`, with pad, net, track, land and needed widths. The outcome counts `hazard`, `necked`, and `overhang_in` (square entries re-routed only because they overhang).

On the same 12 boards, rule D before and after (per board in the [results](../../../bench/results/2026-11-04-pad-edge-entry-59caa02.md#5-tracks-wider-than-the-land)):

| | Candidates | Kept | Oblique / acute | Overhanging entries (input 30) | Necks | Hazards | Track Δ mm | Time s |
|---|---|---|---|---|---|---|---|---|
| Rule D (75d1e2b) | 624 | 414 | 240 / 44 | 23 | – | – | +36.0 | 183 |
| Rule D with the overhang test | 636 | 419 | 241 / 44 | 18 | 0 | 0 | +36.8 | 202 |

- **No track on these boards is wider than its land.** The one entry whose track is wider than its land's short side enters one shape of a two-shape pad (lenaschimmel IC4), 0.4 mm wide merged. The overhangs here are round ends poking out of narrow IC lands, or corner crossings. So no neck was made and no hazard raised; tests cover both (a 1.0 mm track between two 0.6 mm lands is necked to 0.6 at both ends, every piece legal).
- **Fixed:** 5 more entries kept (magtag +2, metro +1, redbot +2); 9 boards are byte-identical. The 18 left are on skipped lands or tails with no legal route. magtag has one more oblique entry: a new tail into IC4 pin 16 crosses the corner of pin 1 (same net); the grid search keeps only the target land out.
- **DRC:** no board worse than before in any type. magtag reads 24 `solder_mask_bridge` against 25, KiCad's run-to-run noise on that board.
- **Physics:** the three changed boards moved by at most 0.01 % against rule D before (redbot +0.25 → +0.26 %); the others, aifryz included (+5.07 %), are unchanged.

### Router A/B (in-router edge ends)

`tools/research/routing/pad_edge_ab.sh` ran merge3-ab's bridge-final portfolio with `KAE_PAD_ENTRY` set to centre vs edge. It was stopped once re-routing was ruled out. chips-0123: both arms clean on 2 seeds. nekoink, 1 seed each: edge 106 open vs centre 67, against 95 in the stored output (noise).

## Verdict

- **Tail re-route with rule D: the pad-entry pass to use (the default).** It fixes the most entries (419 of 636), adds no copper past a land, and needs no rail special case or trim after it. A merit-size A/B still comes first; necks and land hazards still need boards whose tracks are wider than their lands (power-copper outputs). On boards with fine-pitch lands the long-edge approach can bridge solder mask; DRC catches it (cm4-carrier). Physics is unchanged on 8 boards. The exception is the supply peak on aifryz, where D re-routed rail tails (+5 %). Until that is understood, run D with `--rails centre` on boards with supply limits.
- **Rail tails under the edge rule (`--target edge`): into the edge middle (`--rails middle`).** Leaving them at the centre gives up a third of the fixes (acute 46 → 75, oblique 249 → 365). The physics difference is not one-sided: lenaschimmel 1.5 % better, aifryz 1.1 % worse, the rest within 0.2 %. Use `--rails centre` where a supply term has no margin.
- **End-only post-pass (`pad_trim`): worth running, not yet the default.** It never made DRC worse and cut 5.5 % of track, but does little for acute entries (114 → 96): those come from Freerouting's 45° runs, and re-ending them needs room for a turn outside the pad.
- **Rails in `pad_trim`: keep their centre ends (default).** Cutting them a width deep raised rail drop and copper loss up to 1.4 %.
- **In-router option (`pad_entry=edge`): keep off.** The grid router rarely ends a track, Freerouting then needs a DSN pin tie, and the one paired BGA run was worse (106 vs 67 open; noisy).
- **Freerouting cannot be told to end at an edge.** Its pin connection is the pin centre by construction. Any edge entry for its copper has to be a post-pass.

Code: `kae/src/kae/route/{pad_reroute,pad_entry,pad_trim}.py`, `critical_grid.GridRouter._edge_end`, `translate.tie_pins`; tests `kae/tests/test_route_pad_entry.py`; scripts `tools/research/routing/pad_edge_{smoke,ab}.sh`, `pad_edge_summary.py`, `pad_entry_compare.py`, `pad_wide_summary.py`; per-board results in the [results](../../../bench/results/2026-11-04-pad-edge-entry-59caa02.md).
