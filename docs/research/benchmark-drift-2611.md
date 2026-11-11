<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Host-load drift: the same run, days apart, is not the same result (2026-11)

Scope: how much a wall-clock-budgeted benchmark run moves with the shared host's load, which comparisons that invalidates, and the guard and budget change it led to. Not here: the experiments' own verdicts -> [zone-aware placement](placement/zone-aware-placement.md), [BGA window repair](routing/bga-window-repair.md).
Keys: host load, drift, reproducibility, wall-clock budget, reused runs, replicate, --reuse-runs, kaeres exp create, SMT, work budget, counted budget, zone-keepout-ab2, post-audit baselines

**Status:** measured; guard in kaeres; counted-work budgets built and accepted on five of six flows
(section "Fix"), one limit left in KiCad's ratsnest.
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
numbers from different weeks never compare and seed noise is inflated. Hardware cycle counters are not
available to users on this host, so budgets count work. `KAE_BUDGET=work` (with `PYTHONHASHSEED=0` and
`KAE_WORKERS=1`) makes `--time` mean nominal seconds of counted work (`kae.budget`, branch `work-budget`);
the default stays wall time.

| stage | counted | nominal seconds per unit |
|---|---|---|
| annealer | moves (compiled / Python-priced) | 1.74e-5 / 1.36e-4 |
| CP-SAT floorplan, legaliser | the solver's deterministic time, one worker | 4.0 |
| Freerouting | passes done × pins² of the board; its budget becomes a pass cap | 9e-5 |
| KiCad DRC | runs × MB of board file | 4.27 |
| last mile | path searches | 0.054 |
| any deadline check | one poll (a loop that only polls still ends) | 1e-3 (exact repair 5e-3) |

Rates are medians over three boards (65–328 pins) on a quiet host (`tools/research/budget/calibrate.py`).
Per-pass Freerouting time follows pins² (7–9.8e-5 s per pin²); per MB of `.dsn` it varied 9×.
Wall time is only a ceiling: 4× a run's budget, past which every deadline has passed and the report says
`ceiling_hit` (the run has failed). `restart.py` runs attempts in batches, judged whole and in launch order,
so its schedule does not depend on which attempt ends first.

Load dependence that had to go, beyond the clock itself:
- CP-SAT `interleave_search` was not repeatable even with one worker (seed wirelength 258 vs 434); plain
  single-worker search is.
- The compiled annealer steered proposals by measured physics-term time.
- KiCad writes copper in UUID order, and a routed board's UUIDs are new on every import. Two unloaded runs
  differed because of it. The loader, pcbnew's lists, DRC reports and the board copy DRC reads are sorted by
  content, and DSN wires are split into canonical two-point pieces (KiCad's export joins consecutive
  segments depending on file order).
- The step cache is off in work mode (a replay charges its recorded seconds).

### Acceptance: the same command alone and under load

`tools/research/budget/acceptance.py` pins a command to 2 CPUs, runs it alone and again with busy loops on
those CPUs, and compares placement and copper. Before the change a 60 s placement of a 25-part board put all
25 parts elsewhere. After it:

| flow | board | result | loaded / alone wall time |
|---|---|---|---|
| placement | 25 parts | identical | 0.31 (first run paid numba's compile) |
| router | small | identical, 222 items | 1.55 |
| router | medium | identical, 818 items | 1.58 |
| staged | large | identical, 1,319 items | 0.69 (other jobs slowed the unloaded run; 1.77 at an earlier commit, same hash) |
| restart wrapper, staged inside | medium | identical, 667 items, same attempt kept | 1.84 |
| staged, no restarts | medium | same placement and first Freerouting run; **16 vs 15 open** | 1.20 |

The last row is the known limit: KiCad's ratsnest names one of several equally near pieces of copper in an
unconnected item, not by file order, and a repair round's rip-up follows what it names. On that board it moved
the result by one connection. Determinism is not proven beyond these boards.

Counted budgets start a new benchmark era: results are not comparable with wall-clock runs.
