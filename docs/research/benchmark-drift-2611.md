<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Host-load drift: the same run, days apart, is not the same result (2026-11)

Scope: how much a wall-clock-budgeted benchmark run moves with the shared host's load, which comparisons that invalidates, and the guard and budget change it led to. Not here: the experiments' own verdicts -> [zone-aware placement](placement/zone-aware-placement.md), [BGA window repair](routing/bga-window-repair.md).
Keys: host load, drift, reproducibility, wall-clock budget, reused runs, replicate, --reuse-runs, kaeres exp create, SMT, work budget, counted budget, zone-keepout-ab2, post-audit baselines

**Status:** measured; guard in kaeres (branch `results-2611b`); budgets in counted work instead of
seconds are the fix being built.
**First published:** 2026-11-08.

## The measurement

kae staged at 7221e4a (method `c797ddafd9f5`, run in zone-ab on 2026-11-03/04) and the identical recipe
registered again with `--param replicate=b` (`c7c6fd72d6d3`, run in zone-keepout-ab2 on 2026-11-05/07):
same code, harness, seeds, time budget (900 s × √(footprints/40)), restart wrapper, Freerouting fork, JDK,
KiCad image and numba cache.

| | open connections | runs fewer / more | boards better / worse / within 2 % | errors per run |
|---|---|---|---|---|
| first runs | 9,736 | | | 27.1 |
| same recipe, days later | 11,090 (+13.9 %) | 21 / 54 (p < 0.001) | 6 / 22 / 19 | 29.0 |

139 pairs on 47 boards. Small boards moved too: aifryz sensor hub 1–2 → 5–9 open, kestrel ESC 10–25 →
39–53. In kestrel's logs the restart wrapper's first five attempts (same seeds 0–4, same 626 s budgets)
ended at 106–129 open the first time and 159–200 the second: every stage got less done in the same
seconds.

The jobs' CPU accounting barely differs (3.9 vs 4.4 cores busy per 4-core job, a few minutes of waiting
for a CPU). The likely cause is invisible to it: with more of the 128 hardware threads busy, two threads
share each core and each gets less work done per CPU-second. This is an inference; the host blocks
hardware counters for users (`perf_event_paranoid = 4`), so it was not measured.

## What it invalidates

kaeres stores one run per method, board and attempt and reused it in every later experiment, so an A/B
could silently compare a fresh arm against runs made days before.

- **zone-ab:** 5 of 48 boards' base runs came from bga-next-ab. Those 5 carried the whole apparent loss
  (+9.9 %); the 42 side-by-side boards were even (−3.1 %, p = 1.0). See
  [zone-aware placement](placement/zone-aware-placement.md#zone-ab-pull-3-and-keep-out-1-against-the-base-placer).
- **zone-keepout-ab (cancelled):** +14 % against zone-ab's base; the fresh replicate pair was +0.4 %.
- **Post-audit baselines:** kae staged −4.6 % against merge3-ab, a different week
  ([post-audit baselines](routing/post-audit-baselines.md)). Within the drift; not evidence either way.
- **Unaffected:** experiments whose arms ran in the same jobs: escape-ab3, bga-next-ab,
  region-complete-ab, zone-keepout-ab2.

Earlier "load-stable board" filtering (keep boards where Freerouting's result did not move) assumed only
the large boards drift; small boards drift too.

## Guard

`kaeres exp create` refuses methods that already have runs from other experiments on its boards and says
how to register a replicate (same recipe plus `--param replicate=<tag>`); `--reuse-runs` overrides, and
`exp report` then warns about boards whose methods' runs were made more than 12 h apart. See
[tools/kaeres/README.md](../../tools/kaeres/README.md#running-an-experiment-without-wasting-it).

## Fix: budgets in counted work, not seconds

Side-by-side arms only make comparisons fair; each result still depends on the load during the run, so
numbers from different weeks never compare and seed noise is inflated. The fix is to stop on counted
work (annealer moves, solver deterministic time, Freerouting passes, repair rounds, restart attempts)
with wall time kept only as a safety ceiling, so a run does the same work whatever the host is doing.
Profiling says three stages take most of the time and get converted first: Freerouting (40–72 % of
wall time), the placer's annealer (25–40 %) and the last mile (11–29 %)
([audit § performance](audit-2611.md#performance-measured-alongside)).
