<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# polish-merit: windows as polish after restarts, on the merit suite (pre-registered)

Written 2026-11-11, before any run of this experiment.

`loop-polish` (branch `loop-exp`, `docs/research/joint/window-budget-2611.md`) found that P-late beats restarts alone at the same allowance. P-late runs restarts for 70 % of the allowance, then the joint loop's windows on the kept board for the last 30 %. On 129 boards it left 5,804 vs 6,417 open connections (−9.6 %), 54 boards fewer and 31 more, p 0.0003. DRC and placement errors were within +3 %, and cp1 was 23 vs 18.

Its boards were chosen where the joint loop leaves connections open, and it ran in wall-clock time on Freerouting 2e1125a. Per its plan, the split is now tested as the candidate wrapper on the merit suite, under counted-work budgets and the production Freerouting build.

## Arms (`setup.sh`; joint-fixed; `restart.py --parallel 1 --first-s 300 --scale-first --slack 1.15 --resume 0.5 --final` lastmile `--check-placement`)
- **R, restarts alone:** the staged pipeline (`kae.joint.cli run --max-iters 0 --no-modules`) restarted for the whole allowance: `loop-polish`'s R.
- **P-late:** R, then `--finish 'kae.joint.cli run --start @BEST@ --no-modules'` with `--finish-s` 30 % of the allowance.
  - The joint loop starts from the kept board with everything on it locked. Its first route joins what is open, then windows and the loop's own finishing stage run.
  - The polished board replaces the kept one only if KiCad ranks it no worse.
  - J3 (`skip_unfixable_drc`) is not on main. The loop runs main's defaults, which is what `loop-polish` ran with J3 off.

**The same in both arms:**
- One process lane (`--parallel 1`), so CPU is matched: the 30 % finish replaces 30 % of single-lane restarts.
- **Allowance:** 3.15 × 900 s × sqrt(fp/40) of nominal work (`KAE_BUDGET=work`, `PYTHONHASHSEED=0`, `KAE_WORKERS=1` on the wrapper and every inner command), `loop-polish`'s allowance.
  - The harness timeout is 4 × that, the wall ceiling (`timeout_cap_s` 57,600).
  - In work mode the last mile (`--final`) gets 15 % of the allowance in both arms. So R's restarts get 85 %, and P-late's restarts get 55 % with a 30 % finish.
- **Freerouting** pinned to the production fork d137fd1 with `KAE_BRIDGE_FREEROUTING`.
- **Code:** main at 3a482ed. It includes #69, which charges the critical router's counted work, and the speedups. Added on top is `restart.py` honouring `--finish-s` in work mode (#70). Before it, work mode gave every finish pass 10 % whatever `--finish-s` said. Without #70, P-late would have run 70/10 with 20 % unused.

Seed 0, k = 1. Both arms of a board run in the same interleaved kaeq jobs (timed class).

**The windows and the module stage.** Both arms run `--no-modules`, so neither runs the joint module stage: not before the first route, and not in the windows.
- With `no_modules`, a window's module redo list is empty (`KaeStages.repair`), and `KaeStages.modules(only=[])` returns before building a session.
- So the module stage's old clock (`module-clock` is not merged; the clock covers only the part-move passes) cannot overrun here, and there is no per-window module time to log.
- For loops run with modules, the window module stage gets `min(window_module_time 20 s, 15 % of what is left)`. The old clock bounds only its move passes, so routing a window's modules can still run past it. Rails are never routed in a window. That is a confound for any later test with modules in the windows, not for this one.

## Boards (213, `boards.txt`)
The merit suite: `merit-500r3`'s 213 boards, none added or dropped. They are also the physics set and Stage 2's `s2-merit213`. They are already one board per repo family (`board-tags` `repo_family2.json`: 213 families; 210 repositories, 3 of which hold two families each).

## Outcomes and decision (P-late against R, paired per board)
- **Primary, open connections:** `d = (o_P − o_R) / (o_P + o_R + 1)`, sign-flip test.
  - P-late wins if mean `d` < 0, p < 0.05, and total opens at least 3 % lower.
  - R wins on the mirror condition.
- **Guards for a P-late win:** total DRC errors and placement errors (score.py `PLACEMENT_ERROR_TYPES`) not above R's by more than 3 %, and cp1 not lower.
- **Also reported:**
  - cp1 and cpk (k = 1, so cpk = cp1), legal and winnable cp1;
  - DRC errors per type;
  - completion, CPU per arm, `ceiling_hit`, time-outs and no-output runs;
  - how often the polished board replaced the kept one.
  - Physics (kaeres Σu) where both arms route fully: modules valued in both, median ratio P/R and sign-flip p, judged against the J21 floor only at n ≥ 38 (1.06 at 38, 1.04 at n ≥ 80).
- **If P-late wins:** it becomes the default wrapper for the merit kae methods.
  - The next candidate combines it with completion-first: R first; if R's board is complete, M-clock for physics; if not, the 30 % windows phase instead of a second restart run. That candidate also needs `module-clock`'s verdict.
- **If R wins or it is undecided:** the windows' gain is specific to the hard boards `loop-polish` chose, and is reported as such.

## Smoke
2 boards × 2 arms, profiled per arm (py-spy one board per arm; time per stage: restarts, last mile, the loop's first route, windows, its finishing stage; judging). Plumbing only: the arms and rules do not change after it unless the smoke shows a plumbing fault, recorded here as an addendum.

## Costs (information only)
See the addendum written at submit time (`exp submit --dry-run` sizes).
