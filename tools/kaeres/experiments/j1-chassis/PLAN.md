<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# J1: chassis ablation ladder (pre-registered plan)

Written 2026-11-08, before any run of this experiment. Ledger J1 and J11. Code: the commit recorded by `setup.sh`
(main 353d3e0 plus the loop-report change in this branch; `kae/` is unchanged from main).

## Question
`kae staged` has no module stage, `kae.joint` does; the two have only ever been compared together. Does the
full joint chassis (module stage + windows + finish) beat a staged pipeline with the module stage alone, on
routed physics and on open connections? Which of modules, finish and windows earns what?

## Boards (`boards.txt`, seeded, reproducible)
80 boards from the merit suite: split B or C with at most 500 pads, one board per `repo_family` (all 166 boards that
qualify have distinct families). Selection: `select_boards.py` with seed `j1-chassis-2026-11-08`: boards ordered by
sha256(seed, id), taken within each split in proportion to the split's share of the pool: 35 of 72 split B and 45 of
94 split C. Smoke uses 3 boards outside the 80. Corpus and task spec as of the code commit. k = 1 (attempt 0, seed 0
wrapped by the restart portfolio, as every merit run; a new experiment-level seed is not needed for k = 1).

## Arms (all `joint-fixed`, 900 s x sqrt(fp/40), same restart wrapper: `--resume 0.5 --final lastmile --check-placement`, no `--screen`)
Checked against `kae/src/kae/joint/{cli,loop}.py` at the commit above:

| Arm | Flags of `kae.joint.cli run` | Runs |
|---|---|---|
| (a) staged | `--max-iters 0 --no-modules` | place, bridge (bridge's own last mile on). Finish off (`cli.py` `finish` default is false at `--max-iters 0`) |
| (b) +modules | `--max-iters 0` | place, module stage, bridge. No finish, no windows (iteration cap stops the loop) |
| (c) +finish | `--max-iters 0 --set finish=1` | (b) plus the finish stage after iteration 0 (first-route last mile off, as for default joint: `lopts["finish"]` true; finish stage then ends in its own last mile) |
| (d) full joint | no flags | `max_iters=None` (windows until time) + finish (default true) |

Arms run interleaved: kaeres splits each board's methods into 2 jobs placed next to each other in the queue (kaeq timed
class, never frozen), same day, same boards. Counted-work budgets are not on main, so arms share the host's load by
running together. The resumed waves of the wrapper (`kae.route.cli route` from the best board) and the
`--final` last mile are the same for all arms (late attempts keep their last mile; a final pass exists in every arm).

**J11 (`--screen`).** The confound (staged had `--screen`, joint did not) is removed: all four arms use the same
wrapper, without `--screen` (the joint recipe's wrapper; the fairest era of the earlier comparison had no `--screen` for
either). A fifth arm with `--screen` is left out: one arm on these 80 boards is about 53 CPU-h, so a fifth arm takes
the experiment from about 240 to about 300 CPU-h, beyond the approved 180-240. The `--screen` question stays with J11
(simulate from the restarts logs first, then a separate pair).

## Metrics (paired, per board, one evaluator)
All from `kaeres exp report` / `results.csv`, attempt 0, one physics and one DRC evaluator:
- `cp1`, `cpk` (= cp1 at k = 1), completion, open connections (total and paired), DRC errors total and per type
  (`errors_by_type`), CPU (`cpu_s` in results.csv, not `runs.cpu_s`), attempts.
- Routed physics on both-fully-routed boards (no open or missing module in either arm): paired median Σu ratio of
  each arm against (d). Physics is compared only above the noise floor below.
- `xc` (clean net of the route task's `input_drc`) is not computed: it is only fair for route-only methods; these arms
  are joint-fixed and place their own parts.
- Joint loop reports (`restart-report.json`, `restart-report-origin.json`): iterations, windows, stop reason, per board.
  Descriptive only; do not decide.
- Per-split (B, C) tables, n stated. No class claims from small subsets.

**Physics noise floor (J21, A/A aa-joint twins, median paired Σu ratio, two-sided 95 %, excluding identical pairs):**
n 20: 1.12, 30: 1.08, 38: 1.06, 50: 1.05, 60: 1.04, 80: 1.04. A difference inside the bound at the observed number of
both-routed boards is not a difference. Open-connection noise floor: A/A total opens differed by 2.8 % (`aa-joint`).

## Decision rule (from the plan, pre-registered)
Compare (b) and (c) to (d), each paired over all 80 boards:

- **Physics ties (d)**: |median Σu ratio - 1| within the floor for the arm's number of both-routed boards (use the
  table entry for the next smaller n).
- **Opens tie (d)**: total open connections within 3 % of (d) and the paired sign-flip test on per-board opens is not
  significant (two-sided p >= 0.05).

If **(b) or (c)** ties (d) on both: the base becomes staged+modules (+finish if (c) was needed), with windows off until
the loop fixes land (J2-J9). If (d) is better than both beyond the floors: `kae.joint` stays the base. Anything else:
inconclusive; say so, keep `kae.joint`, no default changes. cp1 and completion are reported and must not contradict
(a cp1 difference larger than the A/A noise, about 3 pp at this n, is called out), but they do not change the rule above.

No default changes in this experiment: the outcome is a recommendation.

## Costs
Control arm (d) on these 80 boards: about 53 CPU-h (from `aa-joint`). Four arms plus scoring and physics: about
240 CPU-h. Limit 300 CPU-h: above it the experiment is not submitted.
