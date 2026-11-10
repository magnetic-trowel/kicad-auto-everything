<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# What the joint loop's windows did before they had a budget

Scope: how the windows of `kae.joint` ended, from stored loop reports, and what that rules in or out for the window fixes (ledger J3, J4, J15, J16). Not here: the arms that test the fixes -> `tools/kaeres/experiments/loop-window-bench/`; the loop itself -> [kae-joint-loop](kae-joint-loop.md).
Keys: joint loop, windows, illegal after repair, greedy legalizer, skip_unfixable_drc, NO_MOVE_FIXES, J3, J4, J15, J16

**Status:** analysis of stored runs. J3 (skip windows on these types) **did not work** in its A/B, below: it removes the futile windows, but the loop does not spend the time saved on useful ones. The other fixes are not finished.
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

## J3 A/B: `loop-j3-unfixable-v2` (2026-11-10)

Plan: `tools/kaeres/experiments/loop-j3-unfixable/PLAN.md` (pre-registered). 30 merit boards that have the filtered types, one per repo family, k = 1, commit f2f4151. Arms: `w2 ctl` (filter off) and `w2 j3` (filter on). Both give the windows two budgets beyond iteration 0 and use no restart wrapper; they ran interleaved. KiCad scored every run (60 of 60).

| | w2 ctl | w2 j3 |
|---|---|---|
| cp1 | 0 / 30 | 0 / 30 (none of these boards can be clean: the filtered types stay) |
| legal | 18 | 18 |
| open connections (total; boards fewer / more) | 20 | 31 (1 / 5; mean paired d +0.040, sign-flip p 0.28) |
| DRC errors (total) | 476 | 487 |
| windows (kept) | 596 (36) | 416 (34) |
| windows only on the filtered types (kept) | 172 (1) | 0 |
| windows on other reasons: unrouted, other DRC, physics (kept) | 424 (35) | 416 (34) |
| illegal after repair | 103 | 88 |
| stop: no improvement / no window left / time | 24 / 5 / 1 | 16 / 13 / 1 |
| CPU (method) | 7.6 h | 8.1 h |

Per type, the filtered types are identical in both arms (annular_width 77, invalid_outline 16, footprint_type_mismatch 14, unresolved_variable 10, malformed_courtyard 9, drill_out_of_range 4, zones_intersect 2). The other types barely move (solder_mask_bridge 240 vs 250, starved_thermal 3 vs 5, items_not_allowed 18 vs 17).

Opens and errors are identical on 23 of 30 boards. The 7 that differ go both ways. A different window sequence changes every later seed, so these look like path noise, not an effect, and the opens difference is not significant.

**Verdict: fails the pre-registered rule.** Windows on the filtered types went to 0 (172, 1 kept), but windows on other reasons did not rise (424 to 416), and CPU did not fall. With the futile windows gone, the loop runs out of windows sooner ("no window left" on 13 boards against 5) and the time goes to the finishing stage, not to other repairs. The filter does no harm beyond path noise, but it saves no CPU and buys nothing. It is not merged. The real limit is that the loop has no more useful work for the time: what fills the windows (window choice, J15's repeats, J4's illegal windows) is what decides gains, which the window bench measures. J3 is also read on the window bench's 34 boards with these types.
