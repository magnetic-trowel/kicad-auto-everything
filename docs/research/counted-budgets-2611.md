<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->

# Counted budgets in practice: repeatability, pricing, and what they did to boards (2026-11)

Scope: making `KAE_BUDGET=work` repeatable on large boards, Freerouting's own work budget, the refitted prices, where work ran unbudgeted, and the board-quality regression the budget caused. Not here: why wall-clock budgets were dropped -> [host-load drift](benchmark-drift-2611.md).
Keys: counted budget, work budget, KAE_BUDGET, RATES, max_work, autorouter.max_work, WORK_BUDGET, work_fill_weight, work_optimizer_step_weight, FillWorkMeter, fr_work, KAE_FR_WORK_BUDGET, KAE_BUDGET_GAP, KAE_BUDGET_PROFILE, budget gap reporter, DRC determinism, canonical unconnected, canonical_copper_order, shuffle test, twin runs, starved_thermal, starved thermal, spokes, SPOKES_MIN_S, close_loop, greedy legaliser, exact_pair, Freerouting pin, kae-freerouting.pin

**Status:** merged (kae #97, #101, #102, #103, #105, #110, #113, #114; freerouting #12, #13, #14). Freerouting's per-step price spread is open.

Follows [host-load drift](benchmark-drift-2611.md), which introduced `KAE_BUDGET=work`. Over the next week (2026-11-11
to 11-19), budgets were made repeatable on large boards, prices were refitted, and Freerouting got a work budget of
its own. That surfaced six places where work ran unbudgeted, and one board-quality regression the budget itself caused.
The budget code is in `kae.budget` and the rates are in its `RATES`; every rate there carries its evidence in a comment.

## Repeatability on large boards

On small boards, two runs of the same work-mode command gave the same board. On an 821-pin board, twins of one
joint-loop attempt still diverged: about 450–500 items differed. The divergence was traced to KiCad, not kae:

- **KiCad's DRC is not repeatable on a byte-identical file.** It reports the same number of unconnected items, but it
  names different endpoint pairs for some of them from run to run. These are ties: a pad against the track ending on
  it, two equally long tracks, a via against the track under it, a connector's front and back pads at one position.
  Single-threaded KiCad (`MaximumThreads=1`) and running with ASLR off still varied, in 3 of 4 repeats.
- **The same copper with a different file order or different UUIDs gives different counts** (13 against 15 errors,
  96 against 97 open connections).
- **The names feed decisions.** The joint loop's congestion history (`joint/feedback.unrouted_spots`), last mile,
  repair rounds and the restart judge all read them. In the twins, the history differed, so the window placer started
  from a different cost, and the boards drifted apart from there.

**Fix** (`kae.route.drc.run`, work mode only):

1. DRC runs on a temporary canonical copy of the board: copper in content order, UUIDs derived from content. The
   report's UUIDs are mapped back to the board's, because thermal-via repair and joint feedback find copper by UUID.
2. The open connections are rebuilt per net as a minimum spanning tree between pcbnew's connected clusters, with ties
   broken by position. This is used whenever its edge count matches KiCad's.
3. The restart judge does the same in `tools/kaeres/restart.py`, and leaves its report beside the attempt's board.

Result: twins of the 821-pin attempt came out identical. `tools/research/budget/shuffle.py` writes a copy of a board
with its copper shuffled and new UUIDs, and `kae/tests/test_det_shuffle.py` runs route, last mile and joint on a board
and its shuffled copy. On small boards that test passed even before the fix: small boards have too few ties to matter.

**Still not covered:**

- For some checks (`solder_mask_bridge`, for example), KiCad names whichever partner it finds first.
- KiCad names a connection zone-to-zone in one run and pad-to-track in another.

One twin pair diverged once after byte-identical Freerouting output (14 against 10 solder-mask bridges), under four
parallel attempts. Four parallel copies of that attempt did not reproduce it.

## A Freerouting work budget

Before this week, kae could only cap Freerouting's passes and charge passes × pins². That price was off by 1.1–4.4×
between boards, and the stop depended on wall time. The fork now takes `autorouter.max_work`, a budget in counted work:

| fork PR | adds |
|---|---|
| freerouting#12 | `max_work` in search steps (master's step meter) plus per-pass weighted terms. One budget for the whole job, which fallback attempts share. A `WORK_BUDGET` stop is final, and the optimizer starts no pass once the budget is spent. |
| freerouting#13 | Optimizer work counts towards `max_work` and is checked before each pass and after each candidate. Pour fill work is counted (`FillWorkMeter`, `work_fill_weight`). Optimizer steps are weighted (`work_optimizer_step_weight`). |
| freerouting#14 | `max_work` is checked before each item inside a pass, not only between passes. A pass that runs out stops and keeps the best board seen. |

With these settings unset, sessions and boards are byte-identical to the fork's master on three boards. kae
(`route/freerouting.py`) passes the remaining budget as `max_work`, and charges a run by the work it logs plus
start-up and DSN size. `KAE_FR_WORK_BUDGET=0` turns the hook off for any build, and the run is then charged like
d137fd1.

The pinned build moved d137fd1 → 9a5512d → f1c41d3 → 37b1a8b (`~/.cache/kaebench/kae-freerouting.pin`; each old
pin is kept as `.bak`). The control is now fork master plus the work budget. Runs on d137fd1 are not comparable with
runs on these builds.

## Prices

Medians, fitted on shared-host runs. Calibration and acceptance tools are in `tools/research/budget/` (`calibrate.py`,
`fr_fit.py`, `acceptance.py`).

| work | unit | price |
|---|---|---|
| Freerouting search step | at 430 pins, × `(pins/430)^1.43`, capped at 3× | 9.2e-6 s |
| Freerouting pass started | per board pin; per unrouted connection and pin | 0.012 s; 6.7e-5 s |
| Freerouting pour fill | per fill unit | 2.7e-4 s |
| Freerouting optimizer step | in routing steps | 5 |
| Freerouting run | start-up, plus per kB of DSN | 3.9 s + 0.009 s |
| KiCad DRC | per run, per MB, per zone layer refilled | 1.9 s, 0.84 s, 0.23 s |
| KiCad Python call (pcbnew) | per call, per MB, per zone layer refilled | 0.4 s, 0.06 s, 0.165 s |
| board load | per MB of `.kicad_pcb` | 0.5 s |
| annealer move | compiled; Python-priced | 1.74e-5 s; 2.1e-4 s |
| CP-SAT | per unit of deterministic time, model build included | 5.0 s |
| last mile | per search; per window cell × layer | 0.005 s; 2.5e-7 s |
| exact checks | per `findings_at` call plus each neighbour pair | 7.5e-3 s |
| greedy legaliser | fit test; grid cell; table cell; rectangle marked | 1.45e-7 s; 1e-8 s; 1.75e-9 s; 7.1e-4 s |
| critical router | per search; per A* expansion | 0.10 s; 7.9e-7 s |
| deadline check | per poll | 1e-3 s |

On the Stage 2 arms, wall time per unit of budget came to 0.92–1.15 on a 148-pin and an 821-pin board, down from up
to 2.1 (worst 1.27 on the fork-master build). The Freerouting per-step spread found later (see Open) means other boards
can be well off this.

## Where work ran unbudgeted

Each one of these was found from a run that overran its budget or hit the 4× wall ceiling. The gap reporter
(`KAE_BUDGET_PROFILE=1 KAE_BUDGET_GAP=S`) names the call site of any uncharged stretch over S seconds.

| what | symptom | fix |
|---|---|---|
| Freerouting's optimizer on partly routed boards (fork master) | First route ran 9,858 s against ~290 s charged, then timed out | freerouting#13 |
| Pour fill recomputation inside Freerouting | 51 % of routing time and 79 % of optimizer time on a pour-heavy board, uncounted | freerouting#13 |
| A single Freerouting pass | One pass cost 17× `max_work` on a large FPGA board (budget checked only between passes) | freerouting#14; kae #114 sets Freerouting's own timeout to 4× its budget |
| Exact checks (`findings_at`) | A flat 5e-3 s per poll; real cost 7.5e-3 s per neighbour pair | per-pair charge |
| Greedy legaliser scans | `kae place` ran at 4.06× its charge, near the ceiling | legaliser charges (#102): 0.84× after |
| Closed-loop diagnoses (`exact.close_loop`) | Unbounded when the caller gave no deadline: 465 s after a 42 s repair at `--time 150` | defaults to `time_s` (#103) |
| KiCad Python calls and DRC zone refills | 270 s over 202 calls uncharged; DRC 2.3× under | per-call, per-MB and per-zone-layer charges (#110) |

A missing numba cache shows up as poll gaps of 50–150 s at the annealer's first calls. That is compile time, not
work: give each code version a warm `NUMBA_CACHE_DIR`.

## Effect on boards: starved thermal reliefs

Switching the pin from d137fd1 to the work-budget builds added about 20 KiCad `starved_thermal` errors per board on
pour-heavy boards. These are pads joined to a pour by fewer spokes than the zone requires. Every other error type
stayed the same. The fork was not the cause: with the same placement and kae code, both builds came out the same.

The cause was kae's own budget:

- After the first route, kae's repair round 1 draws short spoke tracks into the pour for starved pads. That normally
  clears the 14–21 starved reliefs the first route leaves.
- Round 1 only runs if enough time is left after routing.
- d137fd1 couldn't take `max_work`, stopped at its pass cap, and left time for it. The work-budget builds spend the
  router's whole share, so on short restart attempts round 1 never ran.

Two fixes were tried and dropped:

- **A separate spokes-only round** took last-mile time: 2 more open connections on one board.
- **A 45 s reserve out of the router's share** took 15–25 % of Freerouting's work on short attempts: up to 5 more
  open connections.

What shipped (#113): the pending spokes go into the last mile's first round, and that round's DRC judges spokes and
joins together. A spokes-only round runs only when the last mile does not.

Over 6 restart attempts on 4 boards:

| | main | #113 |
|---|---|---|
| starved thermal reliefs | 76 | 11 |
| open connections | 189 | 180 |

No other error type changed. Of the 11 left:

- 2 are a ranked-judge trade-off: the last mile's joins starve 2 pads and close 4 connections.
- 9 are on an attempt with no time left after routing, where neither the spokes nor the last mile run.

## Open

- **Freerouting's per-step cost varies 0.25–3.2× across boards** (25 boards, 8,358 passes). No model in pins, layers
  or zones does better than a factor of 2.5. The JVM heap is not the cause (2 GB on 2 CPUs and 6 GB on 1 CPU gave the
  same time). In joint-loop windows Freerouting is still undercharged about 2.3×. On a board at the size cap it is
  overcharged 3.3×. A better work count in the fork is in progress in another session.
- **The critical router on large boards:** `critical_grid._within` (`shapely.contains_xy`) takes 111–597 s per raster
  on an 821-pin board. That is a performance problem, not a price.
- **Measured CPU is still about 2× the charged time** in the loop-win smokes, mostly from the Freerouting spread.

Arms on the same code and board stay comparable. Absolute budgets do not hold across boards until the Freerouting
spread is fixed.

## Sources

kae PRs #97 (repeatability, recalibration), #101 and #105 (Freerouting rates), #102 and #103 (placer charges), #110 (KiCad Python and DRC charges), #113 (starved thermals), #114 (Freerouting's own timeout); freerouting PRs #12, #13, #14. Loop-win smokes 3, 6 and 8 (`kaeres exp report loop-win-smoke8`).
