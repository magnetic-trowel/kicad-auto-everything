<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# loop-j3-unfixable: windows on DRC types no move can change (pre-registered)

Written 2026-11-09, before any run. Ledger J3. Part of the `loop-window-bench` design (`../loop-window-bench/PLAN.md`), which holds
the arms: `kae wb w2 ctl` (J3 off) and `kae wb w2 j3` (J3 on), both with two budgets of window time so windows exist. This
experiment adds boards where the filtered types occur at all: 30 merit boards with at least one of those types in stored runs, usable, one per repo family, in sha256(seed, id) order,
outside the window-bench pool (`boards.txt`). J3 is also read on the 34 window-bench boards that have them.

Data behind the rule, from stored runs and reports, before any run of this experiment: in every kae placement of a board (one evaluator), footprint_type_mismatch, unresolved_variable,
annular_width, zones_intersect, invalid_outline, malformed_courtyard, text_on_edge_cuts, padstack and drill_out_of_range have the same count: 0 of 194 board x evaluator pairs vary. Windows opened only for
these: 75 of 440, kept 0 (136 older reports). Silk and solder-mask counts do vary with placement, so those types keep their windows.

Decision: J3 passes if the windows spent on the filtered types go to 0 and windows on other reasons rise, without worse opens or errors (paired, as in the window-bench plan).
