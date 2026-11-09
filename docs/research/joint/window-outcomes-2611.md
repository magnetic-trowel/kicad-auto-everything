<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# What the joint loop's windows did before they had a budget

Scope: how the windows of `kae.joint` ended, from stored loop reports, and what that rules in or out for the window fixes (ledger J3, J4, J15, J16). Not here: the arms that test the fixes -> `tools/kaeres/experiments/loop-window-bench/`; the loop itself -> [kae-joint-loop](kae-joint-loop.md).
Keys: joint loop, windows, illegal after repair, greedy legalizer, skip_unfixable_drc, NO_MOVE_FIXES, J3, J4, J15, J16

**Status:** analysis of stored runs; the fixes it motivates are not finished (A/B queued).
**First published:** 2026-11-09, branch `loop-j3-unfixable-drc`.

Data: 136 single-run reports (`kae joint loop`, commit 45efe00, 900 s, no restart wrapper; the JSON report is in each run's `adapter.log.gz`), 440 windows. Single seed. Later code changed the windows' details, but not the shares or the legalizer's time.

## How windows end

| Outcome | Windows |
|---|---|
| Routed, then judged | 262 |
| Illegal after repair | 139 |
| Re-route window with no routing to rip up | 20 |
| No part moved | 11 |
| Exact violations left | 6 |
| No time left to route | 2 |

40 of the 440 were kept.

**Illegal after repair (J4).** Greedy ran on 259 windows: 120 ended legal, 93 ran out of time and 46 finished with no spot. More legalizer time can reach the 93 at most. The 46 need a different fallback.

**Placement-only windows (J16).** 67 windows, none kept: 37 illegal after repair, 20 routed with no improvement, 10 made something worse.

**Repeats (J15).** 181 of the 440 windows (41 %) redo a window with the same parts as an earlier one on that board. On the 30 boards with at least 5 windows, the median share of distinct part sets is 0.5. The worst board spent 25 windows on 5 part sets and kept none.

## DRC types no move can change (J3)

Within one evaluator, across every kae placement of a board, these nine types have the same count on every board that has them: footprint_type_mismatch (42 board and evaluator pairs), unresolved_variable (41), annular_width (31), zones_intersect (30), invalid_outline (26), malformed_courtyard (10), text_on_edge_cuts (6), padstack (5), drill_out_of_range (3). None of the 194 pairs varies. Windows opened only for these: 75 of the 440, none kept.

The audit's list also had `silk_over_copper` and `silk_overlap`. Those do vary with placement (10 of 10 and 8 of 9 pairs) and 4 windows on them were kept, so they keep their windows.

Windows opened by type (a window can have several; kept in brackets): solder_mask_bridge 69 (6), clearance 48 (2), footprint_type_mismatch 45 (0), silk_over_copper 36 (2), items_not_allowed 29 (0), shorting_items 24 (0), copper_edge_clearance 17 (0), courtyards_overlap 16 (0), annular_width 14 (0), silk_overlap 8 (2).

## Windows barely run under the restart wrapper

On the first 40 boards finished in the J1 chassis experiment's joint arm (restart wrapper, first wave about 300 s), the best attempt's report has 24 windows in all, and 32 boards have none. Only the best attempt's report is stored, and the counts are descriptive: J1's verdict is separate.
