<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# The module stage under restarts, its copper locked or rippable (chassis-soft, 2026-11-11)

Scope: whether the joint chassis's physics gain and its cost in open connections come from the module stage, and whether that cost is the module copper acting as a wall to Freerouting. Not here: the windows ([window-budget-2611](window-budget-2611.md), branch `loop-exp`).
Keys: module stage, critical copper, Freerouting wire types, shove_fixed, USER_FIXED, module_soft, copper survival, physics, restarts

**Status:** module stage **partial**: it decidedly improves routed physics but decidedly costs open connections. Rippable module copper (`module_soft`) **did not work** as a fix. Most of the cost in opens comes from a clock bug, found after the verdict: the module stage ran past its time and starved the first route ([gating](#gating-is-there-a-class-where-m-costs-no-opens-and-still-gains-physics)). Re-measured with the clock fixed in `module-escape` (Addendum 3). Not merged.
**First published:** 2026-11-11, branch `chassis-soft` (`module_soft` and the survival measure in `kae/src/kae/joint/stages.py`), experiment `chassis-soft` (`tools/kaeres/experiments/chassis-soft/PLAN.md`, pre-registered).

## Mechanism checked in code
The first route after the module stage locks every item on the board (`critical_write.edit(..., lock="all")`), so Freerouting gets the module copper as fixed wiring it never rips or shoves. Unlocked copper would be no different: KiCad exports it as `(type route)`, which Freerouting reads as USER_FIXED (branch `bus-wire-types`). `module_soft` sends that copper unlocked and typed `shove_fixed` instead (rippable, not shoved), on the first route only.

## Setup
160 boards (`physics_inputs_ok`, easy or moderate route demand, one per repo family; the boards of `loop-physics-matched`). Three arms under J1's restart wrapper at the same allowance (900 s × sqrt(fp/40), `--parallel 4`), interleaved; KiCad and the physics evaluator scored all 480 runs.
- **R:** staged, no module stage.
- **M:** module stage, copper locked as today.
- **M-soft:** module stage, copper rippable on the first route.

## Results

| | R | M | M-soft |
|---|---|---|---|
| open connections | 992 | 1,555 | 1,656 |
| clean (cp1) | 114 | 101 | 105 |
| legal | 153 | 151 | 153 |
| DRC errors | 124 | 129 | 121 |
| CPU | 95.3 h | 110.2 h | 106.3 h |
| module copper left in place by the first route | | 100 % (155 boards) | 74.8 % of 34,322 mm (154 boards; all kept on 14) |

Paired, on boards both arms route fully (modules valued in both), with a J21 floor of 1.04:

| pair | opens: fewer / more, p | physics median ratio, n, p |
|---|---|---|
| M vs R | 8 / 41, p < 0.0001 (+57 %) | **0.812**, 98, p < 0.0001: better |
| M-soft vs R | 12 / 32, p 0.0007 (+67 %) | **0.914**, 103, p 0.006: better |
| M-soft vs M | 33 / 19, p 0.012 (totals +6.5 %, driven by a few large boards) | 1.072, 95, p 0.14 |

Per kind, M vs R:

| kind | median | n | p |
|---|---|---|---|
| decap | 0.733 | 95 | < 0.001 |
| crystal | 0.381 | 7 | 0.03 |
| chain | 0.931 | 17 | 0.009 |
| cell | 0.909 | 14 | 0.85 |

## Verdict (pre-registered rules)
- **The module stage carries the joint chassis's trade.** Under restarts alone, M against R gives the same picture as joint plus windows against R in `loop-physics-matched`: physics about 19 % better (0.812 vs 0.815) and open connections about 57 % worse (+61 % there). The case for the module stage fails its opens guard.
- **The wall is not the main cause of that cost.** With rippable module copper, Freerouting removes or moves a quarter of it. Per board, M-soft has fewer opens than M (33 better, 19 worse, p 0.012), but it stays far behind R (+67 % in total) and gives back about half of the physics gain (0.914 vs 0.812 against R). M-soft therefore fails as a fix: it trades physics for opens at a worse rate than simply not running the module stage.
- **What remains:** the module stage's placement and copper choices themselves cost routability. A module stage that leaves corridors (routability in its objective), or that runs only on boards that route easily, is the open question, not the wire type.

## Follow-up analyses on the same runs (2026-11-11, no new runs; `tools/kaeres/experiments/chassis-soft/gating.py`)
All strata below were chosen after the verdict, so this section is **exploratory**.

### Gating: is there a class where M costs no opens and still gains physics?
M vs R, per stratum (opens: M total vs R total, boards where M has fewer/more; physics: boards both route fully, median M/R):

| stratum | boards | opens M vs R | fewer / more | physics n, median |
|---|---|---|---|---|
| R routed fully (0 opens) | 119 | 23 vs 0 | 0 / 11 | 98, 0.812 |
| R 1-5 opens | 14 | 100 vs 39 | 3 / 10 | 0 |
| R > 5 opens | 27 | 1,432 vs 953 | 5 / 20 | 0 |
| ≤ 129 copper pads | 54 | 21 vs 15 | 1 / 3 (p 0.25) | 45, 0.685 |
| 129-255 pads | 53 | 52 vs 19 | 2 / 11 | 37, 0.875 |
| > 255 pads | 53 | 1,482 vs 958 | 5 / 27 | 16, 0.852 |
| ≤ 3 pads / cm² | 54 | 103 vs 102 | 1 / 3 (p 0.50) | 42, 0.869 |
| 3-7 pads / cm² | 53 | 844 vs 546 | 3 / 20 | 28, 0.769 |
| > 7 pads / cm² | 53 | 608 vs 344 | 4 / 18 | 28, 0.732 |
| 2 copper layers | 123 | 355 vs 237 | 6 / 24 | 84, 0.775 |
| 4+ copper layers | 37 | 1,200 vs 755 | 2 / 17 | 14, 0.853 |
| `route_demand` easy | 101 | 394 vs 243 | 2 / 15 | 74, 0.822 |
| `route_demand` moderate | 59 | 1,161 vs 749 | 6 / 26 | 24, 0.807 |

**Corrected 2026-11-11.** The first version of this table joined the board features (`board-tags/structural/features.jsonl`) to boards by line number, zipped with `all_ids.txt`. The rows are not in that order; each carries its own `id`. Most boards were given another board's pad count, density and layer count, so the pad, density and layer rows were wrong. They are now joined by `id`. The outcome and `route_demand` rows did not use those features and are unchanged.

What changed:
- The first version found no class identifiable before routing where M was free. Joined correctly, there are two: small boards (≤ 129 copper pads: 21 vs 15 opens, more on 3 boards and fewer on 1) and sparse boards (≤ 3 pads / cm²: 103 vs 102). M gains physics on both (median 0.685 on 45 small boards, 0.869 on 42 sparse ones).
- M's cost sits on large boards: 1,482 of its 1,555 opens are on the 53 boards with more than 255 pads. Most of it is on 4+ layer boards (1,200 vs 755), not 2-layer ones as the first version said.

- **By the bare board:** M is nearly free on small or sparse boards and costs opens on everything larger or denser. That is also where the module stage overran its clock and starved the first route. A case study of these runs (in the exploration notes, not in the repository) finds the module stage's measured share of the attempt budget sorts the boards the same way. Below 0.10 of the budget (89 boards), M and R leave 113 vs 106 opens. At 0.25 or more (37 boards), they leave 1,219 vs 700. So a pad-count gate would mostly be a stand-in for the time bug. The gate should be re-measured once the module stage keeps its clock (`module-escape`, Addendum 3).
- **By outcome:** "R routes it fully" is still the class where M is nearly free (11 of 119 boards with any opens, 23 opens in all, 19 % physics gain). It needs R's result, so it is a portfolio rule, not a gate.

### Portfolio: keep M where it routes as well as R, else R
Per board, M is kept if it is legal and its opens are no more than R's; otherwise R. M was chosen on 115 of 160 boards.

| | opens | clean | physics vs R (both routed) | CPU |
|---|---|---|---|---|
| R | 992 | 114 | | 95.3 h |
| portfolio (M + R) | 934 | 111 | n 95, median 0.826 | 205.5 h (M 110.2 + R 95.3) |
| R' (`loop-physics-matched`'s R: `--parallel 1`, 3.15 B wall, same boards) | 904 | 115 | n 102, median 1.023 | 79.7 h |
| best of R and R' | 843 | 119 | | 175.0 h |
| portfolio, harness-ranked (legal, opens, DRC errors; M on 113 boards) | 938 | 114 | n 93, median 0.826 | 205.5 h |

**At comparable compute**, two restart runs (175 h) beat the portfolio (205 h) on opens: 843 vs 934, portfolio worse on 21 boards and better on 5, p 0.019. They also win on clean boards, 119 vs 111. The portfolio is better on physics: median 0.826 against the best restart run, n 97, p < 0.0001.

There is no R at exactly twice the allowance. R' is a different wrapper setting, so "best of R and R'" stands in for it.

The first rule picks M on equal opens even where M has a DRC error that R does not, so its clean count (111) falls below R's (114). Ranked like the harness (legal, then opens, then DRC errors), the portfolio matches R's clean count (114) and keeps the physics gain (0.826): 938 opens, 121 errors against R's 124. It still routes worse than two restart runs (843 opens, 119 clean).

**Reading:** M's physics is real and survives a portfolio. It costs either completion (M alone) or compute that would buy more completion as restarts. A user who values physics on boards that route can run M and R and keep M where it routes. The default for completion stays R.

## Sketch: a module stage with routability in its objective (not built)
The module stage (`kae.route.critical_joint.optimize_modules`: module parts' poses scored by routed physics; the critical copper laid by `kae.route.critical`'s grid router, `critical_grid.Grid`) has no term for what its copper and poses do to the other nets.

Three candidates, cheapest first:
1. **Corridor reservation, already built and off.**
   - `kae.route.critical` has `escape_mm` (0, off) and `escape_cost` (3.0). These reserve escape corridors out of dense ICs' signal pins: other nets' critical tracks pay per cell inside them, and their vias are kept out.
   - Test arm: M with `escape_mm=1.5`. No code needed, but it covers only dense ICs' pins.
2. **Flyline crossings, a new term.**
   - Crossings are the best single routability predictor found in the stored placements (E108: seed-pair rho +0.27; RUDY and HPWL predicted nothing).
   - On the critical router's cost grid, add a raster of how many other nets' flylines cross each cell (minimum spanning tree per net). Critical copper then pays `crossing_cost` × that count per cell, the same way `pour_cost` already works.
   - In `optimize_modules`' candidate scoring, add the number of flylines the module copper and parts would block, weighted against physics with a slack like the joint loop's `phys_slack`.
3. **Pin-access room.**
   - For every non-module pad within a module's window, keep a short escape lane in its natural escape direction free of module copper. That is `escape_corridors` generalized from dense ICs to all pins of nets the module does not own.

**Test:**
- **Boards:** the 41 boards of `chassis-soft` where M has more opens than R (the mechanism set), plus the 98 boards both route fully (physics must hold), all from the same 160.
- **Arms:** M, M-esc (1), and M-cross (2, once built), under the same wrapper. R is reused from `chassis-soft` only if the runs are interleaved again; otherwise R runs again.
- **Primary:** opens against M on the mechanism set, paired.
- **Guard:** physics within the J21 floor of M on the routed set.
- **Success:** closing at least half of M's opens gap to R at no physics loss beyond the floor.
- **Order and cost:** about 0.66 CPU-h per board and arm, so about 100 CPU-h for (1) on 139 boards. Run (1) first; build (2) only if (1) moves opens.

### Completion-first policy (a run-time decision, not a pre-routing gate)
Run R. If R routes the board fully, also run M, and keep M when it ranks no worse than R (legal, then opens, then DRC errors). If R leaves opens, spend the second allowance on another restart run instead and keep the better of the two.

Data: `chassis-soft` R and M, and `loop-physics-matched`'s R as the second restart run R'. R' is another wrapper setting (`--parallel 1`, 3.15 B wall), so this is an approximation. 160 boards; R routed 119 fully, and M was kept on 103 of those.

| policy | opens | clean | legal | DRC errors | physics vs R (both routed) | CPU |
|---|---|---|---|---|---|---|
| (a) R alone | 992 | 114 | 153 | 124 | | 95.3 h |
| (b) best of R and R' (harness-ranked) | 843 | 120 | 159 | 14 | | 175.0 h |
| (c) portfolio M or R (harness-ranked) | 938 | 114 | 154 | 121 | n 93, median 0.826, p < 0.0001 | 205.5 h |
| completion-first | **843** | 117 | 157 | 80 | **n 93, median 0.826**, p < 0.0001 | 195.2 h |

- **Against (b):** completion-first leaves exactly the same open connections (843; identical on every board). Its physics is better: median 0.836 against (b), n 96, p < 0.0001.
- **It does not quite dominate (b):** 3 fewer clean boards (117 vs 120), 2 fewer legal, 66 more DRC errors, and 12 % more CPU.
- **The cause:** on boards R completes but leaves DRC errors, (b) can still pick R', which sometimes has none, while completion-first spends that compute on M.
- **A variant would close it:** "R complete and clean → M; else R'".
- **Reading:** completion-first keeps all of the completion of two restart runs and all of the module stage's physics, at the cost of a few clean boards. It needs no new mechanism, only a policy in the restart wrapper. It is a candidate default to test pre-registered in the wrapper itself (one run, same allowance), not a verdict: these numbers mix two experiments and two wrapper settings.
