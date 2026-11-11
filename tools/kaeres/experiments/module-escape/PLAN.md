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
