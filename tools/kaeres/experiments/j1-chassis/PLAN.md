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

## Addendum, before the full submission (2026-11-08, after two smokes on 4 boards outside the 80; no result of the 80 boards was seen)
- Physics: "both-fully-routed" means, in both arms, `unconnected` 0, `n_missing` 0 and `n_open` 0 for the board. If fewer than
  20 boards qualify for an arm pair, physics is inconclusive for that pair. (The smokes showed boards whose modules all score
  "missing" for every arm and the human: a flat Σu floor. They are excluded by this definition, not judged.)
- cp1 noise: "about 3 pp at this n" above is the A/A noise at n = 213 (95 % CI -1.4 to +2.8 pp). At 80 boards scale it by
  sqrt(213/80): about 5 pp. Still report-only: the decision rule is unchanged.
- Smoke record (plumbing only, not results): experiments `j1-chassis-smoke` and `j1-chassis-smoke2`. Loop reports are stored;
  all four arms show the intended flags in their reports; KiCad scored every run; the inputs have no copper.

## Addendum 2: extension rule and J11 (2026-11-08, written while the 80 boards run; no J1 result of the 80 was read)
This addendum replaces the `Costs` limit (the 300 CPU-h cap is withdrawn), the "Physics ties / Opens tie" definitions of the
decision rule, and the J11 reasoning above. Everything else stands.

**1. The 80 boards stay.** No resubmission and no change to the running jobs. They are the first batch.

**2. Outcomes of each decision.** The four tests are (b) vs (d) and (c) vs (d), each on physics and on opens, each paired against (d), at
family alpha 0.05 (Bonferroni, 0.0125 each). A test ends as **different**, **equivalent** or **undecided**.

*How looks are handled.* The J21 bound is a fixed-n bound, so it is not valid on its own once extending depends on what was seen. Decisions use
anytime-valid evidence, which stays valid under any number of looks and stops. The sign-flip test at the final n is reported, descriptively only.
- Physics. Unit: `x = ln(Σu_arm / Σu_d)` on both-routed boards (definition in Addendum 1), one per board per batch; ties at the tested value are dropped.
  For a hypothesised ratio θ, with `S` of `n` units above `ln θ`, a batch's e-value is `2^n · B(S+½, n−S+½) / B(½,½)`. The evidence is the product over
  batches, and θ is rejected at evidence >= 80. **Different** needs θ = 1 rejected and the observed median outside the J21 floor for that test's n
  (excluding identical pairs, next smaller table entry; n < 20 has no floor and cannot be different). **Equivalent** needs every θ outside
  [1/1.06, 1.06] rejected. The margin is fixed at 1.06, the J21 floor at the set this test was designed for (n about 38), because the floor shrinks with n and would be a moving target.
  Note that a true effect of the size of the earlier 0.955 module-stage figure would count as equivalent.
- Opens. Unit: `d = (o_arm − o_d) / (o_arm + o_d + 1)`, in (−1, 1), on all boards both arms ran. A two-sided hedged-capital confidence sequence for the mean of `d`
  (Waudby-Smith and Ramdas, JRSS B 2024), level 0.0125, boards in sha256(seed, id) order within each batch. **Different**: the sequence excludes 0 and total opens differ by more than 3 %.
  **Equivalent**: the sequence lies within ±0.03 and total opens are within 3 %. The ±0.03 on `d` is about ±6 % in per-board ratio, looser than the 3 % on totals, so both are required.

**3. Extension.** After each batch, compute per arm pair the number of both-routed boards and its J21 bound, and classify the four tests. While any test is undecided, run the next stage, and repeat until
each is different or equivalent. A true effect sitting at the margin can take unbounded data, so after every round report the confidence sequences; the user decides whether to continue. That is a report, not a cap.
- *Stage 2: the remaining 129 merit boards.* The 213 merit boards minus the 80 minus the 4 smoke boards, whose results were read and so are excluded. This includes boards over 500 pads. Same four methods (ids unchanged,
  harness 74fd46c), k = 1, arms interleaved board by board, a new experiment `j1-chassis-ext` so kaeres keeps runs per batch. Big boards need the job timeout and memory estimated for them; retry time-outs before reading.
- *Stage 3 and later: more seeds.* One further attempt per round on one pre-fixed board set: all 209 boards with results, chosen before any round so looks cannot select it (`--attempts N`, new experiment with `--reuse-runs`; attempt N−1 is the round's data, read from
  the run folders, since results.csv holds attempt 0 only). Each round is one batch, one unit per board. Attempts are of the kae arms: never a Freerouting seed sweep on its own.

A batch is its own e-value so that load drift between batches cannot enter within a pair. Limits: the both-routed set depends on the arms' own outcomes, so physics claims hold for boards both arms route; the J21 floor comes from an older evaluator
and a seed-0 A/A, so it is approximate.

**4. `--screen` (J11), restored.** It was left out only for the cost cap. A fifth arm cannot be side by side with the jobs already queued, so J11 is a **separate interleaved pair**, experiment `j1-screen`, same harness:
`kae j1 joint twin` (the arm (d) recipe registered with `--param replicate=j1-screen`, so its control runs side by side instead of reusing (d)'s runs) against `kae j1 joint screen` (the same recipe plus `--screen` on `restart.py`, which then replaces the `--resume` schedule with
successive halving). Boards: the same 80, k = 1, the same outcomes and extension rule, as one pair (physics and opens at 0.025 each). If `--screen` is different beyond the floor on physics or opens, the ladder's no-screen verdict is limited to that wrapper, and (a) with `--screen` is added as a further pair to check whether the chassis conclusion holds under it.

Nothing in this addendum is submitted yet; the extension and `j1-screen` are triggered after the 80 are complete.
