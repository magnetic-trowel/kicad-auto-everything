<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# module-escape: escape corridors in the module stage's critical router (pre-registered)

Written 2026-11-11, before any run of this experiment. This is test (a) of the sketch in `docs/research/joint/chassis-soft-2611.md` (branch `chassis-soft`).
`chassis-soft` found that the module stage (M) improves routed physics (median Σu ratio 0.812 against staged R), but leaves 57 % more open connections. Rippable module copper did not fix that.

## Change under test (branch `module-escape`, off main 425acb7)
- `kae.route.critical` already reserves escape corridors out of dense ICs' signal pins (`escape_mm`, `escape_cost` 3.0, ICs with at least `escape_pins` 32 pads): another net's critical track pays per cell inside a corridor, and its vias are kept out. It is off by default.
- Before this branch the joint stages could not set it: the module stage's session got `rails="none"` only. The branch makes the three keys stage keys and passes them to the session. The module stage now reports `escape_corridors`, the number laid.
- Defaults are unchanged.

## Arms (`setup.sh`; joint-fixed; J1's restart wrapper `--parallel 4 --first-s 300 --scale-first --slack 1.15 --resume 0.5 --final lastmile --check-placement`)
- **M:** `kae.joint.cli run --max-iters 0`, J1's arm b, the control. It is run again here in the same jobs as M-esc.
  - The stored `chassis-soft` M runs are not reused: the mechanism boards were chosen on M's own outcomes, so a stored control would build regression to the mean into the comparison.
- **M-esc:** M with `--set escape_mm=1.5`.

**Budgets and builds**, the same for both arms:
- Counted-work budgets: `KAE_BUDGET=work`, `PYTHONHASHSEED=0`, `KAE_WORKERS=1`, set for the wrapper and every inner command. `--time` is 900 s × sqrt(fp/40) of nominal work; the harness timeout, 4 × that, is the wall ceiling.
- Freerouting is pinned in both arms with `KAE_BRIDGE_FREEROUTING` to the production fork build d137fd1.
- `chassis-soft` ran on fork 2e1125a with wall-clock budgets, so numbers across the two experiments are not directly comparable. Only the paired M vs M-esc comparison here is.

Seed 0, k = 1. Both arms of a board run in the same kaeq job pair, at priority 0.

## Boards (139; `boards.txt` = `boards-mechanism.txt` ∪ `boards-physics.txt`, disjoint)
- **Mechanism set (41):** `chassis-soft` boards where M left more open connections than R.
- **Physics set (98):** `chassis-soft` boards that M and R both routed fully, with valued modules whose physics differed between them.

Corridors exist only where an IC has at least 32 pads. On a board without one the two arms run the same code path, so results are also reported on the boards where M-esc laid at least one corridor (from its report), as a descriptive subset.

## Outcomes and decision
- **Primary, opens on the mechanism set:** paired `d = (o_Mesc − o_M) / (o_Mesc + o_M + 1)`, sign-flip test.
  - M-esc **moves opens** if mean `d` < 0, p < 0.05, and total opens at least 3 % lower.
  - **Success** as in the sketch: M-esc closes at least half of M's opens gap to R on these boards. The gap is measured against `chassis-soft`'s R, as a reference only: other build and budgets, so this part is descriptive.
- **Guard, physics on the physics set:** on boards both arms route fully, modules valued in both, the median Σu ratio M-esc/M must not be above the J21 floor (1.04 at n ≥ 80; 1.06 at 38). Otherwise the guard fails.
- **Pooled (139 boards):** opens and physics reported the same way.
- **Also reported:** cp1, legal, DRC errors per type, CPU per arm, module stage `escape_corridors`.
- **Decision on (b):** if M-esc moves opens and the guard holds, (b) (flyline-crossing cost) is built and tested next. If it does not move opens, (b) is still the open idea, but this cheap version is recorded as not enough.

## Costs (information only)
About 0.7 CPU-h per board and arm under the wrapper: about 200 CPU-h for 139 boards and 2 arms.

## Addendum, before any run (2026-11-11): ablation arms; the experiment is `module-ablation`
A 2-board smoke of the two arms above was queued and cancelled before it started, so no run of this design exists. Reading `stages.py` and `critical.py` shows that `chassis-soft`'s M-soft unlocked the module copper but kept the guard pours. `KaeStages.route` appends the modules' guard zones on every route: keep-out ground pours under each cell, path and crystal module's hull plus 0.5 mm, on the plane layer. On a 2-layer board, 137 of the 160, that is the bottom pour. Other pre-laid pieces are suspects as well.

**Code** (same branch, next commit):
- `--set crit.KEY=VALUE` passes any option of the module stage's critical session (its DEFAULTS, plus `rails_joint`). This replaces the escape-only keys above, and `escape_mm` is now `crit.escape_mm`.
- `--set module_poses_only=1` keeps the module stage's part moves and drops all its copper and guard pours before the first route.
- Defaults are unchanged.

**Arms**, all in the same interleaved jobs per board, sharing one M control:

| arm | flags (on top of `--max-iters 0`) | what it removes or adds |
|---|---|---|
| M | none | control |
| M-esc | `crit.escape_mm=1.5` | adds escape corridors out of dense ICs |
| M-noguard | `crit.guards=[]` | no guard pours |
| M-norails | `crit.rails_joint=none` | no rail copper (critical_rails) |
| M-nojoin | `crit.complete_mm=0`, `crit.island_mm=0` | no completion and island joins |
| M-poses | `module_poses_only=1` | the module stage's placement only; no copper, no guards |

**Decision, per arm against M**, with five comparisons, so p < 0.01 each:
- Primary: opens on the 41 mechanism boards (paired `d`, sign-flip).
- Guard: physics on the 98 physics boards (median Σu ratio arm/M against the J21 floor).
- The aim is descriptive as well: where M's opens cost lives, and what share of M's physics gain each piece carries. M-poses bounds the share from placement alone.
- Pooled 139-board results are reported for every arm.
- The success criterion for M-esc above stands (half of M's gap to R on the mechanism set).
- An arm that moves opens and holds physics is the lead for a fix. One that moves opens but loses physics names the piece that carries both.

**Costs (information only):** six arms × 139 boards × about 0.7 CPU-h, about 580 CPU-h.

## Addendum 2, before any run (2026-11-11)
To check in the smoke that each knob took effect, the module stage now also reports `copper_by_owner` (what it laid, by module kind or rail and by piece, counted before an ablation drops it) and `guard_zones`. The first route already reports its `guards`. That is a new commit, so the methods are registered again at it and the experiment is named `module-ablation2`; `module-ablation` holds no runs. Arms, boards and rules are unchanged.

## Addendum 3, before any run of this design (2026-11-11): the module stage's clock; the experiment is `module-clock`
`module-ablation2` is not run (its 4-job smoke and the profiling runs of its arms are the only runs). A case study of `chassis-soft`'s stored runs found that 72 % of M's extra open connections over R come from a time bug: the module stage's clock covered only its part-move passes. Routing every module, the rails (with their completion joins) and the corner joins ran past it, up to 8×, and the first route got what was left (23 s instead of 180-345 s on the largest boards). Every arm above inherits that overrun, so the ablation is redesigned on a fixed base.

**Corrections to the text above:**
- On the 160 boards, 123 are 2-layer, not 137 (`chassis-soft`'s `gating.py` joined board features by line; fixed on that branch).
- `crit.complete_mm` and `crit.island_mm` do nothing in the joint module stage: completion and island joins run only in `kae.route.critical.Session.route`. M-nojoin would have been M. The joins the joint stage does lay are the rails' own completion joins (inside `route_rails`, owner `rail/pad`) and the corner joins (necks to pad centres, so Freerouting sees the module copper connected).
- Profiling (gecko5 cpuaddon, 814 pads, time mode): of 240 s in the module stage, 46 s were the modules and 186 s the rails; the profile is dominated by `route_rails` → `_complete_net` → `route_hop` → `_entry_by_physics`.

**Code** (branch `module-escape`, next commit):
- `--set module_clock=1` (a loop and stage option, off by default). The module stage then keeps `module_time` (90 s, or 5 % of the budget) for all of its work, counted from the stage's start, Session build included. The deadline is checked before every module, every candidate trial, each rail, rail branch, rail completion join and ground return, and the tightening; whatever is not started is reported in the stage's `clock.skipped`. The corner joins always run (they connect copper already laid, under a second on the largest board profiled). Modules go decaps, rail groups and crystals first, then cells and paths, chains last (`MODULE_CLOCK_RANK`), in the brief's order within a rank.
- With `module_clock` the first route gets `route_share` (0.6) of what was left before the module stage, the time it would get without modules, capped at 90 % of what is left after it.
- **Counted work for the module stage.** The critical grid router charged no work, so in work mode (`KAE_BUDGET=work`, as here) the module stage's clock never advanced and M did not overrun at all: `module-ablation2`'s M would not have shown the bug. Each grid search now charges `crit_search` (0.10 nominal s, with the setup and physics since the previous clock event) and its A* expansions `crit_expansion` (7.9e-7 s each), calibrated in time mode with `KAE_BUDGET_PROFILE=1` on three boards (178-814 pads, `tools/research/budget/calibrate.py`). This applies to every arm, M included: M's module stage now spends work as it spends time, so M reproduces the overrun under counted budgets.
- `crit.kinds=decap,crystal` (a comma list) selects module kinds without JSON quoting in the wrapper's command.
- The module stage reports `opt_phase_s` (modules, rails, joins and tightening), `phase_s` and `clock`; `copper_by_owner` now reads the owners from the critical space (it reported `?/?` before).

**Arms** (`setup-clock.sh`, all at the new commit, same wrapper, budgets and Freerouting d137fd1 as above; every arm `--max-iters 0`):

| arm | flags | question |
|---|---|---|
| M | none | the module stage as it was (control for the bug) |
| M-clock | `module_clock=1` | the fixed base |
| M-clock-local | `module_clock=1`, `crit.kinds=decap,crystal`, `crit.rails_joint=none` | only decap and crystal copper: no cells, paths, chains or rails, so no rail joins (corner joins stay, they are connectivity) |
| M-clock-noguard | `module_clock=1`, `crit.guards=[]` | no guard pours |
| M-clock-norails | `module_clock=1`, `crit.rails_joint=none` | no rail copper |

M-esc and M-poses are dropped. M-esc adds grid cost to a stage that overran; the case study expects little from it before the clock is fixed. M-poses is bounded by M-clock-local, which keeps the moves and the copper that carries the physics.

**Boards (142, `boards-clock.txt`):** the 139 above plus the 3 boards of the share set below that were in neither (`ebothor-dts-board-cc-debug`, `jduanen-acoustic-camera-front-end`, `pcbcorpus-brown-studios-minuet-minuet`).
- **Share set (37, `boards-share37.txt`):** the `chassis-soft` boards where M's module stage took at least 25 % of its first-wave attempt budget (stage seconds / the budget of the wrapper's attempt 0, both from M's stored reports). 24 of them are in the mechanism set.
- Mechanism set (41) and physics set (98) as above.

**Decision:**
- **The bug's effect, M-clock vs M:** opens on the share set (primary) and on the 41, paired `d`, sign-flip. M-clock fixes the bug if mean `d` < 0 with p < 0.05 on the share set and its total opens there are at least 3 % lower (the rule above). Guard: physics on the 98, median Σu ratio M-clock/M within the J21 floor.
- **Each ablation against M-clock** (3 comparisons, p < 0.017 each): opens on the share set (primary) and on the 41; the same physics guard on the 98. Interpretation as in the first addendum: an arm that moves opens and holds physics is the lead for the default; one that moves opens but loses physics names the piece that carries both.
- Pooled 142-board results, cp1, legal, DRC errors per type, CPU per arm, and per arm the knob check from the reports (`copper_by_owner`, `guard_zones`, `clock`, the first route's `router_s`) are reported for every arm.
- `chassis-soft`'s R is a reference only (other build and budgets).

**Costs (information only):** five arms × 142 boards × about 0.7 CPU-h, about 500 CPU-h; fewer if M-clock's shorter module stage holds.

## Addendum 4, after profiling and before any full run (2026-11-11): every module routed before any moves; the experiment is `module-clock2`
Before submitting, the five arms were profiled directly: one attempt each under py-spy, counted work, at f1fb619, on whippet-106 (459 pads) and gecko5 cpuaddon (814 pads). A 2-board kaeres smoke of `module-clock` also ran at f1fb619. Findings:
- **M overruns in work mode now.** The critical router's work is charged (also PR #69). M's module stage spent 175 (whippet) and 173 (gecko5) nominal s against its 90 s. M-clock spent 93.5 and 93.2, and its first route got the time back (596 vs 504 s and 551 vs 473 s of routing stage).
- **A fault in the first clock design.** On gecko5, M-clock routed only the crystal: the crystal module's move trials (2 passes × 3 parts × up to 6 candidates, each re-routing the module) spent the whole 90 s, so every decap, the buck cell and the power path were skipped. M-clock-local was then the same board as M-clock.
- **Fix (next commit):** with `module_clock`, every module is first routed at its pose in value order, and only then do the move passes run with what is left. Re-checked on gecko5 in work mode: all 18 modules routed, the rails started and were cut at the deadline, and the stage spent 90.6 of 90 nominal s. Without `module_clock` nothing changes (M is as before).
- **The knobs, on these two boards.**
  - Guard zones were 0 in M-clock-noguard and 1 in the other M-clock arms on gecko5.
  - M laid rail copper (`rail/*` owners) on both boards. The re-checked M-clock laid it on gecko5 until the deadline cut it.
  - M-clock-local laid only decap and crystal owners.
  - On whippet the clock skipped the rails in every M-clock arm, so the rail ablations were the same board there. The kaeres smoke at the new commit checks the knobs again per arm. Where the clock leaves no time for rails, M-clock-norails equals M-clock by construction. That is part of the answer (the rails then cost nothing), not a fault.
- Arms, boards, rules and thresholds are unchanged. The methods are registered again at the new commit, and the experiment is named `module-clock2`. `module-clock` holds only the smoke at f1fb619.

## Addendum 5, after the `module-clock2` smoke (2026-11-11, before the other 140 boards)
Plumbing only, and the two boards stay in the experiment. Commit 6499398, smoke on whippet-106 and gecko5 cpuaddon. Every arm ran to the end with a scored board.
- **whippet, all five arms.**
  - The module stage took 1.34× its budget in M and 1.05× in every M-clock arm.
  - The first route's router time was 80 s in M and 105-123 s in the M-clock arms.
  - Opens were 17 in M and 9 in M-clock: one board, no inference.
  - Rails were skipped by the clock in M-clock and M-clock-noguard, and off by flag in the other two.
- **gecko5, M-clock-local and M-clock-norails.**
  - M-clock-local laid only decap and crystal copper and kept the crystal's guard (1 zone).
  - M-clock-norails kept cell, path, decap and crystal copper and no rail copper (3 guard zones).
  - Both routed every module within the clock: 93.7 and 91.3 nominal s of 90.
- gecko5's M, M-clock and M-clock-noguard were the last job still running when the full run was submitted. The same arms ran in the direct profiling at the previous commit, and M-clock was re-checked at this one (Addendum 4).
- **Sizing:** gecko5 jobs peaked at 10.4 GB against kaeres's 8.5 GB request. kaeq's measured admission grows grants, so this is left to it.
No rule changes.

## Note (2026-11-11, after submission): Freerouting's optimizer in work mode
Another session found that in work mode Freerouting's optimizer phase (on boards it routes completely) is neither charged nor capped by passes.
- It normally stops when a pass improves less than its threshold, which is deterministic.
- It can also be cut by the 4× wall ceiling (`optimizer: timed_out` in the bridge's route stops). That depends on host load.
- A fix that caps optimizer passes from the budget is on branch `fr-budget-calibration`.

`module-clock2` predates that fix, and every arm shares the exposure, so the paired comparisons stand. `analyze_clock.py` reports each run's optimizer stops and, per arm, the number of runs with a `timed_out` optimizer. This covers the kept attempt's and its origin's stored reports; other attempts' reports are not stored. An imbalance between arms is read before any conclusion.

## Addendum 6 (2026-11-13): module-clock2 read, and `module-rails` (pre-registered before any run)
**module-clock2 results** (all 142 boards, analysis `analyze_clock.py`):
- M-clock vs M: share37 opens 539 vs 851 (−36.7 %, p 0.0008). The physics guard holds. M-clock fixes the bug.
- The ablations against M-clock are undecided.
- **Rail check** (`rails_check.py`): M-clock's clock skipped the rails on 43 boards. On `worst_rail_mohm` (Σu does not cover rail drop), M-clock/M paired:
  - those boards, both routed fully: n 8, median 1.26, 6 worse / 2 better, p 0.14;
  - those boards, any routing: n 43, median 1.37, p 0.84;
  - pooled, both routed fully: n 25, median 1.05, p 0.12.
  - So the direction is a rail loss, not decided.

**module-rails:**
- **Arms:** M-clock (control) and M-clock-rails, which is M-clock with `--set module_rail_share=0.3`. The modules and their moves stop at 70 % of the module stage's time, and the rails keep the last 30 % (only where rails run).
- **Code:** next commit on this branch. With the default share of 0, nothing changes.
- **Boards (50, `boards-rails.txt`):** the 43 rail-skipped boards ∪ share37.
- **Setup:** wrapper, budgets and Freerouting as `module-clock2` (`setup-rails.sh`).
- **Primary:** `worst_rail_mohm` on boards both arms route fully, paired log ratio M-clock-rails/M-clock, sign-flip.
  - M-clock-rails wins if the median ratio is < 1 with p < 0.05.
  - It is also reported on all boards, any routing.
- **Guard:** opens against M-clock, paired `d`. The guard fails if total opens are more than 3 % higher with p < 0.05.
- **Also reported:** Σu on both-routed boards against the J21 floor, rails skipped, and stage times.
- **Caveat:** Freerouting's optimizer is uncharged in work mode; the fix is pending (note above). Both arms share it.
- **module-rails smoke (whippet, gecko5; dd358a6):** plumbing only, every run was scored. M-clock-rails split its 91 s as 65 s modules and 26 s rails on both boards; M-clock skipped the rails on gecko5. No rule changes.

**module-rails result (2026-11-14, 50 boards, `analyze_rails.py`): the rail share does not work.**
- **Primary, `worst_rail_mohm` on both-routed boards:** n 12, median ratio M-clock-rails/M-clock 0.906, 6 better / 6 worse, p 0.24. Not decided. On any routing: n 43, median 0.876, p 0.98.
- **Guard, opens:** 666 vs 576 (+15.6 %), 5 boards fewer and 18 more, p 0.014. **The guard fails.**
- Σu: n 12, median 0.993 (floor 1.12). CPU 107.1 vs 101.7 h. Clean 17 vs 18.
- **Reading:** rails laid as locked copper cost completion, even inside the clock. The rail-drop question needs another mechanism, such as rails as Freerouting net classes with widths (case study, proposal 2), not a share of module-stage time. M-clock stays without rails when its clock runs out.
