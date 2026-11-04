<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# kae pad-edge entry: end a track at the pad edge it approaches, not at the centre

**Status:** partial. The tail re-route (`kae.route.pad_reroute`) on 12 routed boards fixed 397 of 624 oblique or sliver-prone entries: acute entries 107 → 48, oblique 581 → 252. DRC was never worse, no vias were added, and physics moved by 0.5 % or less (4 boards so far). The end-only post-pass (`kae.route.pad_trim`) cut 4 % of track but barely changed angles. The in-router option gained nothing on a 2-board A/B. All three are off by default.
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
- **Post-pass** (`python -m kae.route.pad_trim trim IN OUT --report R.json`, like `power_copper`). On any routed board, a segment from a same-net pad centre to a point outside the pad is cut back to `pad_entry_overlap` inside the edge it crosses, along its own axis. If it enters more than 10° off the edge normal, it is re-ended instead where legal: the segment stops at a turn a width outside the nearest edge, and a new piece runs in along the normal. Each piece is checked exactly with `Space.track_violations`, and the new entry must be within 10° of the normal; otherwise the plain cut is used. Not touched: segments with a via at either end (dog-bones, fan-outs: escape-stage copper), pads with a via in their copper (heat pads, via-in-pad: the thermal stage's joints), pads of ball grids (≥ 9 round SMD pads), and by default rails, grounds and wide tracks. The gate is KiCad DRC on the re-opened board (each error type and the unconnected count). A worse board reverts changes within 1 mm, then 2.5 mm, of each new violation, then every re-end, then all. The JSON report has the planned and kept changes, DRC before and after, and pad-entry counts. When `pad_entry=edge`, the bridge runs the plain cut last (`pad_trim` option).
- **Setting.** `pad_entry` (`constraints.DEFAULTS`): project text variable `KAE_PAD_ENTRY`, opts, else env `KAE_PAD_ENTRY`.

What does not change: the neck rule (power copper's necks find tracks by contact, and current-carrying tracks enter centred), the escape stage, Freerouting's own routing.

## Results

### Post-pass on existing outputs (main result)

`python -m kae.route.pad_trim trim` (cut plus re-end) on the merge3-ab `kae-bridge-main-final` outputs with the human project files; no re-routing. DRC by kicad-cli on the re-opened board. Changes kept / planned (re-ended); entries are segment crossings into a same-net pad; oblique = 10-45° off the edge normal, acute = more than 45°. Script `tools/research/routing/pad_edge_smoke.sh DIR reend`, table `pad_edge_summary.py --variant reend`.

| Board | Kept/planned (re-ended) | DRC errors | Unconnected | Track mm | Centre/edge ends | Oblique / acute |
|---|---|---|---|---|---|---|
| jjhorton pmod-tester | 34/34 (0) | 0 → 0 | 0 → 0 | 309 → 283 | 42/0 → 8/34 | 0/0 → 0/0 |
| dream117er paicorea | 209/209 (2) | 0 → 0 | 1 → 1 | 2477 → 2344 | 251/153 → 38/296 | 124/10 → 112/8 |
| freetronics secsense | 62/62 (0) | 0 → 0 | 0 → 0 | 584 → 555 | 70/1 → 8/63 | 1/0 → 1/0 |
| lenaschimmel bestelampe | 143/143 (4) | 16 → 16 | 0 → 0 | 2361 → 2280 | 149/23 → 6/166 | 23/7 → 21/5 |
| aifryz sensor-hub | 221/221 (9) | 9 → 9 | 0 → 0 | 1973 → 1866 | 318/81 → 97/302 | 113/14 → 105/13 |
| jkiv cm4-carrier | 94/94 (0) | 612 → 605 | 0 → 0 | 1561 → 1518 | 179/18 → 85/112 | 38/6 → 38/6 |
| adafruit metro-m7 | 287/287 (7) | 22 → 22 | 1 → 1 | 2329 → 2145 | 303/70 → 16/357 | 29/19 → 27/14 |
| sparkfun redbot | 154/154 (6) | 133 → 133 | 0 → 0 | 1517 → 1415 | 190/28 → 36/182 | 27/11 → 23/9 |
| greatscottgadgets ubertooth | 287/287 (6) | 37 → 37 | 13 → 13 | 1177 → 1077 | 341/60 → 54/347 | 39/14 → 33/14 |
| adafruit magtag | 241/241 (2) | 51 → 51 | 0 → 0 | 2144 → 2011 | 250/30 → 9/271 | 14/8 → 12/8 |
| circuitmonkey chips-0123 (WLP) | 8/8 (1) | 45 → 45 | 4 → 4 | 33 → 32 | 9/10 → 1/14 | 10/0 → 6/0 |
| zephray nekoink (BGA) | 373/373 (10) | 11 → 11 | 95 → 95 | 3235 → 3083 | 816/129 → 443/502 | 205/25 → 201/19 |

- **DRC never worse**, every change kept on the first check; no new violation of any severity, warnings included. cm4-carrier lost 4 `solder_mask_bridge` and 3 `clearance` errors: Freerouting's tracks wider than a land ran to its centre and bulged beside it.
- **Track length** −5.5 % over the 12 boards (19.70 → 18.61 m): the copper inside lands.
- **Angles barely move.** Oblique 623 → 579, acute 114 → 96. A cut keeps its track's angle; only 47 of 2,113 changes could be re-ended with legal pieces on one segment (the turn needs a track width of free room outside the edge). Most oblique entries are Freerouting's 45° runs into a pad's corner region.
- **BGA and WLP intact.** nekoink's 443 remaining centre ends are its balls and dog-bones (skipped); chips-0123's 4 WLP balls (fewer than 9) were trimmed with the rest, still clean of new errors.
- **DRC noise.** KiCad's `solder_mask_bridge` count on the unchanged magtag board is 24 on one run and 25 on another; an early single-step revert discarded all 241 trims on it. The gate now reverts in steps (1 mm, 2.5 mm, re-ends, all).

**Physics** (`eval_intent.sh`, `KAE_EM_TOL=1e-4`, intents `compiled-6329e71`; terms whose contribution changed by more than 0.05 %):

Physics total (mW_eq, sum of the intent's terms). Two variants: rails cut a width deep (`--rails width`), and rails left at the centre (`--rails centre`, the default).

| Board | Before | Rails cut a width deep | Rails at the centre |
|---|---|---|---|
| jjhorton pmod-tester | 904.1 | 908.7 (+3V3 drop 122.1 → 123.7 mV, copper 140.8 → 142.7 mW) | 904.1 (no term moved) |
| dream117er paicorea | 348.7 | 350.3 (rail drop D1 +0.6 %) | 348.7 |
| freetronics secsense | 15818.6 | 15803.6 (copper −0.5 %, drop D1 +0.3 %) | 15818.6 |
| adafruit metro-m7 | 7442.9 | 7444.1 (supply S0 120.3 → 121.5 mV) | 7443.0 |
| greatscottgadgets ubertooth | 2204.1 | 2207.6 (emission E3 40.12 → 40.21 dBuV/m) | 2208.7 (E3 40.18) |
| jkiv cm4-carrier | 9931.3 | 9938.5 (copper +0.3 %, D1 +0.3 %) | 9931.8 (copper +0.07 %) |
| adafruit magtag | 26972.5 | 26962.7 | 26983.9 (E1 442.9 → 443.3 mV) |
| aifryz sensor-hub | 47275.4 | 46937.3 (supply S1/S4/S7 −0.3 to −0.8 %) | pending |
| lenaschimmel bestelampe | 5237.8 | 5312.7 (supply S0 200.1 → 202.8 mV) | pending |
| sparkfun redbot | 96538.6 | 96556.4 (S1, S5 +0.1-0.3 %) | 96542.9 (copper +0.08 %, S5 206.2 → 206.9 mV) |

With rails cut, the power terms moved by up to 1.3 %, mostly for the worse. With rails left at the centre, 3 of 8 boards are unchanged and the rest move by at most 0.3 % (redbot S5; emission 0.06 dB). That is within the evaluator's grid noise at 0.25 mm pitch.

### Tail re-route (`kae.route.pad_reroute`, 2026-11-04)

The post-pass above changes only the last segment, so it could re-end 47 of 2,113 ends. `python -m kae.route.pad_reroute IN OUT --report R.json` re-routes several segments instead.
- **Which entries.** Every entry more than 10° off the edge normal, plus centre-aimed entries with sliver risk (copper beside the land over 2× what a perpendicular entry leaves).
- **Release point.** The tail is ripped back to the first via, junction (including a T-junction mid-segment), width change, arc or other pad within R. Failing that, it is cut at R along the path, with R = max(3 widths, 1 mm), then 2 mm, then 4 mm.
- **Target.** `pad_entry.approach_targets` gives the edge the release point faces, then the others. The route must reach an approach point one width outside the edge on its normal, then run straight in, overlap-deep. Rails, grounds and 0.4 mm+ tracks enter at the edge middle, a width deep.
- **Route.** Same width, no vias, the land kept out of the search. On boards whose tracks are 90 % or more 45/90°, the route uses 45/90° doglegs.
- **Accept.** Only if every piece is exactly legal, the tail grows by at most 1 mm + 20 %, and then DRC on the whole board is no worse; otherwise the old tail stays.
- **Not touched.** As in the post-pass, plus locked tracks. Pads of several shapes (THT with an SMD twin, custom pads) count as one land, and so does the entry count below.

Same 12 boards, from the original outputs. "trim" is `pad_trim` with rails at the centre; "re-route + trim" is `pad_reroute`, then `pad_trim`. Entries: oblique / acute.

| Board | Candidates | Re-routed | Original | trim | re-route | re-route + trim | DRC err/unconn (orig → re-route + trim) | Track mm: orig → trim / re-route + trim | Re-route s |
|---|---|---|---|---|---|---|---|---|---|
| adafruit magtag | 16 | 12 | 14/8 | 14/8 | 9/2 | 9/2 | 51/0 → 51/0 | 2144 → 2042 / 2044 | 15 |
| adafruit metro-m7 | 42 | 37 | 29/19 | 30/17 | 9/3 | 9/3 | 22/1 → 22/1 | 2329 → 2214 / 2214 | 19 |
| aifryz sensor-hub | 124 | 75 | 113/14 | 109/13 | 46/6 | 45/6 | 9/0 → 9/0 | 1973 → 1881 / 1888 | 17 |
| dream117er paicorea | 89 | 78 | 87/5 | 85/5 | 12/2 | 12/2 | 0/1 → 0/1 | 2477 → 2360 / 2380 | 20 |
| freetronics secsense | 1 | 0 | 1/0 | 1/0 | 1/0 | 1/0 | 0/0 → 0/0 | 584 → 564 / 564 | 4 |
| greatscottgadgets ubertooth | 36 | 21 | 39/13 | 37/13 | 26/6 | 26/6 | 37/13 → 37/13 | 1177 → 1112 / 1115 | 10 |
| jjhorton pmod-tester | 0 | 0 | 0/0 | 0/0 | 0/0 | 0/0 | 0/0 → 0/0 | 309 → 286 / 286 | 3 |
| jkiv cm4-carrier | 40 | 18 | 36/5 | 36/5 | 18/5 | 18/5 | 612/0 → 608/0 | 1561 → 1523 / 1525 | 10 |
| lenaschimmel bestelampe | 28 | 18 | 23/7 | 21/5 | 11/2 | 10/2 | 16/0 → 16/0 | 2361 → 2294 / 2296 | 17 |
| sparkfun redbot | 38 | 11 | 27/11 | 23/9 | 20/8 | 20/7 | 133/0 → 133/0 | 1517 → 1420 / 1422 | 14 |
| circuitmonkey chips-0123 | 2 | 2 | 7/0 | 7/0 | 5/0 | 5/0 | 45/4 → 45/4 | 33 → 33 / 33 | 5 |
| zephray nekoink | 208 | 125 | 205/25 | 204/19 | 95/14 | 94/13 | 11/95 → 11/95 | 3235 → 3127 / 3121 | 63 |
| **total** | 624 | 397 | 581/107 | 567/94 | 252/48 | 249/46 | never worse | 19701 → 18856 / 18889 | 199 |

- **Fixed:** 397 of 624 candidates (64 %); oblique entries fell 57 % and acute ones 57 %, against 2 % and 12 % for trim. No vias were added (1,488 before and after), and the re-routed tails are 65 mm shorter in total.
- **Skipped by rule:** 136 (22 %): the outside end is a via (dog-bone or fan-out stub), or the land holds a via (heat pad, via-in-pad). This is most of what is left on redbot, aifryz and nekoink.
- **Failed:** 91 (15 %).
  - No route in the room left (no_route): 29.
  - No admissible target (no_target): 29. No edge is long enough for the width, or the end would pass the centre or leave the land.
  - Release point within a width of the land (release_at_pad): 20.
  - Longer than 1 mm + 20 % (length): 5.
  - Tail shared with an earlier re-route (overlap): 4.
  - No 45/90° dogleg (style): 2.
  - Illegal final piece: 2.
  - Reverted by DRC: 0.
- **DRC.** No board got worse in any type or severity, and every board's first check was accepted. cm4-carrier lost 4 clearance errors (612 → 608).
- **Runtime.** 3-63 s per board, 199 s for all 12. Most of it is KiCad (DRC, DSN export) and setup (60 s for the export and the Space); the planning and routing itself took 23 s.

**Physics** of re-route + trim (rails at the centre, same evaluator). 4 of 10 boards are done; the other 6 are queued as kaeq tag `physrrt`.

| Board | Before | Re-route + trim | Terms that moved |
|---|---|---|---|
| adafruit magtag | 26972.5 | 26989.7 | E1/S4 442.9 → 443.6 mV, R0 708.5 → 709.1 mV |
| adafruit metro-m7 | 7442.9 | 7447.2 | S1 +0.07 %, S2 194.7 → 194.4 mV |
| dream117er paicorea | 348.7 | 350.0 | D1 121.8 → 122.0 mV, copper 76.25 → 76.32 mW |
| freetronics secsense | 15818.6 | 15818.6 | none |

The re-route changes rail tails too (edge middle, a width deep), so supply terms move by 0.1-0.5 %, mostly for the worse.

### Router A/B (in-router edge ends)

`tools/research/routing/pad_edge_ab.sh`: merge3-ab's bridge-final portfolio, `KAE_PAD_ENTRY` centre vs edge. It was stopped once re-routing was ruled out. On chips-0123 both arms came out clean on 2 seeds. On nekoink (1 seed per arm) the edge arm left 106 open against 67 for centre; the method's stored output left 95, so this is within the noise.

## Verdict

- **Tail re-route + trim: the pad-entry pass to use.** It more than halves oblique and acute entries at no DRC cost, in 3-63 s per board. Before it becomes a bridge stage or a default, it needs a merit-size A/B, and the rail-entry physics cost needs checking on the remaining boards; leaving rails at the centre, as trim does, is the fallback. What is left is mostly fan-out and dog-bone stubs (skipped by rule) and tight spots with no room.
- **End-only post-pass (`pad_trim`): worth running, not yet the default.** It never made DRC worse and cut 5.5 % of track; on one board it removed 7 errors. With rails left at the centre, physics did not move. It does little for what the user cares about most, acute entries (114 → 96 over 12 boards): those come from Freerouting's 45° runs, and re-ending them needs room for a turn outside the pad. Next steps: re-end along the chain of segments rather than one segment, and run it as the bridge's last stage in a merit-sized A/B.
- **Rails and grounds:** keep their centre ends (default `--rails centre`). Cut a width deep, rail drop and copper loss rose 0.1-1.3 % in the evaluator (jjhorton +3V3 drop 122.1 → 123.7 mV).
- **In-router option (`pad_entry=edge`): keep off.** Freerouting completes most connections itself, so the grid router rarely ends a track. Where it does, Freerouting needs a DSN pin tie to see the joint. The one paired BGA run was worse (106 vs 67 open; noisy). Nothing here argues for it.
- **Freerouting cannot be told to end at an edge.** Its pin connection is the pin centre by construction. Any edge entry for its copper has to be a post-pass.

Code: `kae/src/kae/route/{pad_entry,pad_trim}.py`, `critical_grid.GridRouter._edge_end`, `translate.tie_pins`; tests `kae/tests/test_route_pad_entry.py`; scripts `tools/research/routing/pad_edge_{smoke,ab}.sh`, `pad_edge_summary.py`.
