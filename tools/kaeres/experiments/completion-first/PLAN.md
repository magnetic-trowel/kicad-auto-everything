<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# completion-first: the module stage only where restarts already complete the board (pre-registered draft)

Written 2026-11-11, before any run of this experiment. **Not submitted:** it waits for `module-ablation2` to read out, unless the queue is idle.

## Background
- **Physics:** the module stage (M, J1 arm b) improves routed physics against staged (R): median Σu 0.812 on 98 boards in `chassis-soft`. But it leaves 57 % more open connections.
- **Exploratory replay:** `docs/research/joint/chassis-soft-2611.md`, from two experiments and two wrapper settings. Spending a second allowance on M only where R's board is complete, and on another restart otherwise, matched two restart runs on opens (843 = 843). It kept M's physics (0.826 vs R) with 3 fewer clean boards.
- **This test:** the same policy run inside the wrapper, compute-matched by construction.

## Change under test (branch `restart-completion-first`, off main)
`tools/kaeres/restart.py --policy completion-first [--alt COMMAND]`, off by default:
- Two runs of the wrapper in `--time`, half each.
- Phase 1 runs COMMAND. Phase 2 runs `--alt` when phase 1's board is clean under the harness's ranking (legal, no opens, no DRC error beyond the input's); otherwise it runs COMMAND again with the next seed.
- `--alt`'s board is kept when it ranks no worse; a second restart's board only when it ranks better.
- Each phase is a full run of the wrapper (waves, resumes, `--final`, `--finish`).
- Tests: `tools/kaeres/tests/test_restart.py` with a stand-in KiCad, covering both branches and the seeds. One test there (`test_judge_reports_unconnected_items_a_project_ignores`) also fails on main and is unrelated.

## Arms (`setup.sh`; joint-fixed; J1's wrapper settings `--parallel 4 --first-s 300 --scale-first --slack 1.15 --resume 0.5 --final lastmile --check-placement`)
- **bestR:** `--policy completion-first` without `--alt`. This is always two restart runs of R (`--max-iters 0 --no-modules`), seeds S and S+1, best kept: best-of-two-R through the same code.
- **CF:** `--policy completion-first --alt M-clock`, where M-clock is `--max-iters 0 --set module_clock=1`: the module stage keeping its clock, with the first route's time from the attempt budget (branch `module-escape`, its PLAN's Addendum 3, merged into this branch). The module stage as it was ran past its clock and starved the first route, which caused most of its cost in open connections. This draft is held until `module-clock` reads out, and the choice of M-clock or an ablation of it as `--alt` follows that result.

**Budgets and builds:**
- `--time` is two R allowances: 2 × 900 s × sqrt(fp/40) of nominal work, counted-work budgets (`KAE_BUDGET=work`, `PYTHONHASHSEED=0`, `KAE_WORKERS=1`). The harness timeout, 4 × that, is the wall ceiling.
- kaeres's fixed 4-hour per-attempt cap would bind above about 160 footprints and cut phase 2 short exactly where the arms differ, so it is lifted. The harness timeout is 8,000 s × sqrt(fp/40): the wrapper's own ceiling (4 × the two phases' nominal budget) plus about 10 % for its DRCs and physics, with `timeout_cap_s` 200,000 (PR #59, merged into this branch). The largest of the 160 boards (395 footprints) gets about 7 h, within kaeq's 24-hour job limit.
- Freerouting is pinned to the production fork d137fd1 (`KAE_BRIDGE_FREEROUTING`).
- Seed 0, k = 1, both arms of a board in the same interleaved jobs.

## Boards
The 160 `chassis-soft` boards (`boards.txt`): `physics_inputs_ok` and route demand easy or moderate, one per repo family.

## Decision (CF against bestR, paired per board)
**Primary, non-inferiority on completion; both must hold:**
- **Opens:** CF's total open connections at most 3 % above bestR's (A/A noise 2.8 %), and the paired sign-flip test on `d = (o_CF − o_bestR)/(o_CF + o_bestR + 1)` not significant against CF (two-sided p ≥ 0.05, or mean d ≤ 0).
- **Clean:** CF's clean count at least bestR's minus 3 boards (2 % of 160), and McNemar's test on the discordant boards not significant against CF (p ≥ 0.05).

**Secondary, physics:** on boards both arms route fully, modules valued in both, the median Σu ratio CF/bestR against the J21 floor (1.04 at n ≥ 80). Reported as better, equal or worse.

**Verdict:**
- CF is a candidate default if the primary holds and physics is better beyond the floor.
- If the primary holds and physics is not better, CF is equivalent but costs a mechanism. Report it, no default.
- If the primary fails, CF is not a default.

**Also reported:** legal, DRC errors per type, CPU per arm, and CF's phase-2 choices (`second`: alt or restart, and which phase was kept).

## Costs (information only)
Each arm is about two R runs: R was about 0.6 CPU-h per board under J1's wrapper in `chassis-soft`. So about 2 × 1.2 CPU-h × 160 ≈ 400 CPU-h.

## Addendum before any run (2026-11-13)
- **`--alt` is M-clock** (`--set module_clock=1`). The code is `module-escape` at dd358a6, merged here: the route-first ordering, and the critical router's work charges (#69). Its rail share stays at 0, so this is M-clock exactly as in `module-clock2`.
- **Caveat: Freerouting's optimizer is not charged or capped in work mode.** On boards Freerouting routes completely, its optimizer runs until a pass gains less than its threshold. That is deterministic, but a load-dependent 4× wall ceiling can cut it (`optimizer: timed_out`). The fix (`fr-budget-calibration`) is pending. Both arms share the exposure. `analyze.py` reports `timed_out` counts per arm.
- **Added descriptive comparison: staged-only R against M-clock.** Phase 1 of every run is R (`--max-iters 0 --no-modules`, seed S), with one allowance, the same allowance and build of R as `module-clock2`'s. `analyze.py` compares phase 1's opens (from `summary.json` → `phases[0].rank[2]`) with `module-clock2`'s M-clock and M on the shared boards. That shows how much of the old M's gap to R the clock fix closes. It is descriptive, not a decision: the compared runs come from different experiments.

**Smoke (2 boards, ea90c7e):** both boards were clean after phase 1 in both arms. CF ran M-clock as phase 2 and kept it (a tie keeps `--alt`). bestR ran a second R and kept phase 1 (a tie keeps the first run). Every run was scored. Plumbing only; no rule changes. These arms' code was profiled in `module-clock2`'s smoke.
