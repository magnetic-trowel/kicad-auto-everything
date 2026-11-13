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

## Addendum 2026-11-13: via cost is confounded with the job; a swapped-order check (before any factor effect is read)
An interim plumbing check (27 boards; settings shown to act, no factor effect computed) found that `kaeres exp submit` put
each board's control and its 8 `via_costs=100` runs in job :0 and the 8 `via_costs=25` runs in job :1. The two jobs of a
board started a median 0.8 h apart, and 19.8, 18.1, 12.7, 9.0 and 8.8 h apart on nekoink, rdimm, sdi-mipi, otterley
and polarfire. About half the runs stop at Freerouting's 900 s wall clock, so a run's result depends on host load at
the time, and factor A (via cost) carries a job/time effect J: the sweep measures A + J. The other six factors are
balanced across the two jobs (4 + 4 per level in each) and are not affected.

**Check.** `e09-swap`: the 16 design runs again as replicate methods (`replicate=e09swap`, recipes otherwise identical
to d01-d16, checked), on 12 boards (`boards-swap.txt`: the 5 boards whose jobs ran most hours apart, plus 7 of the other
finished boards in a fixed hash order), with the job assignment swapped: the `via_costs=25` runs in job :0 (queued
first) and the `via_costs=100` runs in job :1. Per board, with A defined as opens(100) - opens(25) over the 8 vs 8 runs
(mean of log1p(opens)):
- original order measures A + J, swapped order A - J', so J ~ (A_orig - A_swap) / 2 and A ~ (A_orig + A_swap) / 2,
  if the job effect is about the same size both ways (stated assumption; the 12 boards' J are reported one by one).
- Factor A is reported from the 40-board sweep as "via cost + job", with the bound on J from the 12 boards. A via-cost
  default can be proposed only if A passes the plan's rule on the 40 boards, A_orig and A_swap have the same sign on at
  least 9 of the 12 boards, and the median |J| is under a quarter of the median |A_orig|. Otherwise A is "not separable
  from job timing", whatever its p-value. The swap runs are not pooled into the 40-board test.
- Runs that end `TIMED_OUT` are counted per arm and order, as the plan already asks.
Cost, as information: 12 boards x 16 runs x up to 900 s x 2 cores, about 60-100 CPU-h.
These are replicates of a deterministic setting for a timing measurement, not a seed sweep: each setting still has one
run per board in the sweep itself.
