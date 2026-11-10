<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# barrier-ab: keeping parts and nets off voids and all-layer keepouts (pre-registered plan)

Written 2026-11-09, before any run. Ledger E104, E105. Code: the commit `setup.sh` records.

## Question
The placer sees the outline as one mask. E104 shows the two separate cases. A **true split** (the outline less barriers falls apart:
panels, eurorack module and its panel PCB, HV isolation rule areas on every copper layer) cannot be crossed by copper at all: parts
placed on the wrong side leave opens no router fixes (sycamore 29 of 31 opens are geometry; beems 37 opens cross an HV keepout).
One-region boards with voids: copper goes around, and E104 says leaving-edge counts alone do not cost opens (fortitude60, dilshan),
davang's trouble is not congestion. Do true-split boards route better when each region is placed by itself? Does weighting the nets
a seed places across a void or keepout help the one-region boards, or just pull parts around?

For assembly and manufacture: a part on the wrong region of a panel is a re-spin, the worst kind of scrap (boards that cannot be connected).
Regions matter for depanelization too: a part straddling a V-score or tab gets cracked when the panel is broken. Barriers (HV isolation) are
safety rules; a placement that needs a track across one fails creepage/clearance at hipot, or is forbidden by the rule area at DRC.

## Mechanisms (setting, both off by default)
- `barrier_split=1`: `kae.place.barriers.true_split` finds regions (outline less board-level rule areas that forbid tracks on every
  copper layer; pieces under 2% of the board ignored), assigns parts by anchors and net neighbours (signal nets first, then power, then
  by area), and places each region on its own with its own outline. `slots` (oval drills) are holes, not walls.
- `barrier_net_weight=3`: on the seed, signal nets whose straight-line MST edges cross a void or all-copper keepout get 3x weight in the
  annealer. Nets that span regions on a true split are unaffected.
Report keys `barrier_split` (regions, areas, parts per region, assignment, cross nets) and `barrier_crossings` (nets, MST edges) are the mechanism's own metric.

## Arms (joint-fixed, staged: `kae.joint.cli --max-iters 0 --no-modules`, restart `--resume 0.5 --final`, 900 s x sqrt(fp/40); interleaved per board)
| Experiment | Boards | Arms |
|---|---|---|
| `barrier-split-ab` | `split.boards.txt`: 100, one per family, merit first, at most 1,000 pads, from the 332-board scan of usable_route_test boards | C control, S split |
| `barrier-weight-ab` | `weight.boards.txt`: 80, one region with outline holes of at least 3% of the area or at least one all-copper keepout | C control, W weight 3 |

Board facts and the `split`-scan are from `select_boards.py` on the barrier scan (`kae.place.barriers.regions`). Boards a task cannot be prepared for drop out of all arms.
Never on plain outlines (the code path does not run; no regression there is possible by construction).

## Metrics (paired, attempt 0)
`cp1`, `cpk` (= `cp1`, k = 1), completion, open connections, `legal`, DRC per type (`errors_by_type`), CPU, `barrier_split` / `barrier_crossings`.

Noise: the A/A joint-loop twins (`aa-joint`; no staged A/A exists) move total opens by 2.8% and cp1 by about 0.5 pp at 200 boards. At these sizes a paired ratio of about 1.05 in opens, and about 6-8 pp in cp1, is the visible limit.
Physics not reported: neither mechanism changes module structure; open-connections and legality are the mechanism's direct metric.

## Decision rule (pre-registered)
- `barrier_split` becomes the default if the split arm lowers total opens by at least 5% on the split boards (paired sign test, p < 0.05 or tying at p >= 0.05 only if cp1 also rises by more than 3 pp), no regression of cp1 larger than 3 pp, no drop in `legal` larger than 3 pp, and `barrier_split` lands no region part outside its region. Otherwise it stays off with its numbers in the docs.
- `barrier_net_weight`: default stays 1 unless W lowers both `barrier_crossings` and opens with no cp1/legal regression; a drop in crossings alone is not enough (E104: crossings alone cost no opens).
- A/B runs on boards where the mechanism exists only. Extension: if the split arm's paired total-opens CI crosses 1 at 100 boards and cp1 is flat, run the rest of the 332-board scan.

## Amendment after the smoke (2026-11-09, before any full run)
The smoke (`barrier-smoke2`, code c3654d7) showed two faults, fixed before the full run: parts without pads (logos) were in no region and stayed
staged off the board; and on pdp7-memory-display, whose outline parses as two 17 mm2 loops, every part was sent into one loop (1,013 DRC errors,
about 207 parts outside, against 262 errors for the control). Now pad-less parts are assigned by area, anchored parts no region holds are obstacles
in every region, and a split whose regions cannot hold their parts is skipped (placed whole, reported as `barrier_split.skipped`). The split board
list is redrawn without boards whose parts cannot fit the outline as parsed (courtyards over 90% of it on a side; same seed and rule otherwise).
The corpus scan's own over-capacity flag was not used: without the task's anchors it puts whole netlists in one region. The weight list is unchanged.
