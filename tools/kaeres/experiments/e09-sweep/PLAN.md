<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# e09-sweep: Freerouting search-cost sweep on congested boards

Pre-registered 2026-11-09, before any run. Ledger R19, on R20 (running the fork's E09 package through kaebench
so KiCad scores it). The fork's package (`docs/research/experiments/E09-cost-sweep`) is a 16-run resolution IV
fractional factorial over seven settings, settings-only: via cost (A 25/100), start rip-up (B 50/200), SMD-net
via factor (C 0.03/0.3), undesired-direction trace cost (D 0.5/2), pull-tight accuracy (E 160/1600), plane via
cost (F 2/12), fanout pre-pass (G on/off). Control is the current defaults.

**Determinism rule.** E09's three `item_order_seed` arms are removed. One Freerouting run per board per setting
(a designed set of configurations, not a restart).

## Arms
`e09 control` plus `e09 d01` ... `e09 d16` (fork 2e1125a, no `-mp` cap, 900 s, 1 thread; one wrapper per arm,
installed under `~/.cache/kaebench/kae-fr2e1125a-e09-<arm>`, sharing the fork's jar). Harness 7f17a5d, task spec 11.

## Boards
The 40 boards of fr-settings-ab (`boards.txt`, congested: route_demand hard/extreme where the bridge or the
fork leaves opens). Standalone Freerouting, so this answers "does any cost default move on congested boards"
for the router alone; a real effect is confirmed through the bridge before any default changes.

## Measures and decision rule
KiCad: opens, cp1, completion, per-type DRC errors, via count, CPU. For each factor, per board, main effect =
mean over the 8 high runs minus the 8 low runs; across boards, signed-rank test. A default moves only if a
factor has a main effect on opens at least 10 % of the control total, p < 0.01 across boards (Bonferroni over 7
factors), with no increase in DRC errors, and is then confirmed through the bridge. Expected: most effects are
within board-to-board noise ("the defaults are not the lever", the package's own prior). Timed-out boards are
reported apart (wall clock). Cost about 200 CPU-h, informational.
