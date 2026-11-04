<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# kae pad-edge entry: end a track at the pad edge it approaches, not at the centre

**Status:** partial. The tail re-route (`kae.route.pad_reroute`) on 12 routed boards fixed 397 of 624 oblique or sliver-prone entries: acute 107 → 46, oblique 581 → 249 with the trim after it. DRC was never worse and no vias were added; physics moved by at most 1.5 % per board, in both directions. The end-only post-pass (`kae.route.pad_trim`) cut 4 % of track but barely changed angles. The in-router option gained nothing on a 2-board A/B. All three are off by default.
**First published:** 2026-11-03, branch `pad-edge-entry` (off `power-copper`).

Every routing stage aimed at a pad's centre. A connection only needs to reach the pad's copper, so the run from the edge to the centre is copper inside the land (or, for a track wider than the land, a bulge beside it), and the snap to the centre adds a last piece at whatever angle the centre lies.

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

- **DRC never worse.** Every change was kept on the first check, with no new violation of any severity. cm4-carrier lost 4 `solder_mask_bridge` and 3 `clearance` errors: Freerouting's tracks wider than a land had run to its centre and bulged beside it.
- **Track** −4 % (19.70 → 18.86 m), all of it copper inside lands.
- **Angles barely move** (oblique / acute 581/107 → 567/94). A cut keeps its track's angle, and only 47 of 2,113 ends could be re-ended within one segment.
- **BGA and WLP intact.** Balls and dog-bones are skipped.
- **DRC noise.** KiCad's `solder_mask_bridge` count on the unchanged magtag board is 24 on one run and 25 on another, so the gate reverts in steps.
- **Physics.** With rails cut a width deep, rail drop and copper loss rose up to 1.4 % (jjhorton +3V3 drop 122.1 → 123.7 mV; lenaschimmel +1.4 %). With rails left at the centre (the default), no board got worse by more than 0.2 %, and aifryz improved by 0.6 %.

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

- **Fixed:** 397 of 624 candidates (64 %). 136 (22 %) were skipped by rule: via-ended stubs, or vias in the land.
- **Failed:** 91 (15 %): no route 29, no admissible edge 29, release point at the land 20, too long 5, tail shared 4, no 45/90° dogleg 2, illegal final piece 2. DRC reverted none.
- **DRC:** no board worse in any type or severity; cm4-carrier went 612 → 608 errors. No vias added; the re-routed tails are 65 mm shorter in total.
- **Runtime:** 3-63 s per board, 199 s for all 12, of which 23 s is planning and routing.
- **Physics** (10 boards, intent totals in the results): with rail tails into the edge middle, 8 boards moved by 0.4 % or less. lenaschimmel improved 1.5 % (supply S0 200.1 → 193.5 mV) and aifryz got 1.1 % worse (S1 1.114 → 1.131 V). With rail tails left at the centre, every board stayed within 0.4 %.

### Router A/B (in-router edge ends)

`tools/research/routing/pad_edge_ab.sh` ran merge3-ab's bridge-final portfolio with `KAE_PAD_ENTRY` set to centre vs edge. It was stopped once re-routing was ruled out. chips-0123: both arms clean on 2 seeds. nekoink, 1 seed each: edge 106 open vs centre 67, against 95 in the stored output (noise).

## Verdict

- **Tail re-route + trim: the pad-entry pass to use.** It more than halves oblique and acute entries at no DRC cost, in 3-63 s per board. It needs a merit-size A/B before it becomes a bridge stage or a default. What is left is mostly fan-out and dog-bone stubs (skipped by rule) and tight spots with no room.
- **Rail tails: into the edge middle (the default, `--rails middle`).** Leaving them at the centre gives up a third of the fixes (acute 46 → 75, oblique 249 → 365). The physics difference is not one-sided: lenaschimmel 1.5 % better, aifryz 1.1 % worse, the rest within 0.2 %. Use `--rails centre` where a supply term has no margin.
- **End-only post-pass (`pad_trim`): worth running, not yet the default.** It never made DRC worse and cut 5.5 % of track; on one board it removed 7 errors. With rails left at the centre, physics did not move. It does little for what the user cares about most, acute entries (114 → 96 over 12 boards): those come from Freerouting's 45° runs, and re-ending them needs room for a turn outside the pad. Next steps: re-end along the chain of segments rather than one segment, and run it as the bridge's last stage in a merit-sized A/B.
- **Rails in `pad_trim`: keep their centre ends (default `--rails centre`).** Cutting them a width deep only removes copper; rail drop and copper loss rose up to 1.4 %.
- **In-router option (`pad_entry=edge`): keep off.** Freerouting completes most connections itself, so the grid router rarely ends a track. Where it does, Freerouting needs a DSN pin tie to see the joint. The one paired BGA run was worse (106 vs 67 open; noisy). Nothing here argues for it.
- **Freerouting cannot be told to end at an edge.** Its pin connection is the pin centre by construction. Any edge entry for its copper has to be a post-pass.

Code: `kae/src/kae/route/{pad_reroute,pad_entry,pad_trim}.py`, `critical_grid.GridRouter._edge_end`, `translate.tie_pins`; tests `kae/tests/test_route_pad_entry.py`; scripts `tools/research/routing/pad_edge_{smoke,ab}.sh`, `pad_edge_summary.py`, `pad_entry_compare.py`; per-board results in the [results](../../../bench/results/2026-11-04-pad-edge-entry-59caa02.md).
