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
