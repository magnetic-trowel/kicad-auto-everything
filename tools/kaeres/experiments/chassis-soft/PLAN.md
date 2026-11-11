<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# chassis-soft: the module stage under restarts, with its copper locked or rippable (pre-registered)

Written 2026-11-11, before any run of this experiment.

## Background
`loop-physics-matched`: at equal allowance, joint + windows beat staged + restarts on routed physics (median Σu ratio 0.815, 95 boards, p < 0.0001). It lost open connections (+61 %) and clean boards (101 vs 115 of 160). The physics most likely comes from the module stage (critical copper placed and routed first), which staged lacks. The open-connection loss may come from how that copper reaches Freerouting.

## How module copper reaches Freerouting today (checked in code, `kae/src/kae/joint/stages.py` `route`)
The first route locks every item on the board (`critical_write.edit(..., lock="all")`), the module stage's copper included. KiCad exports locked wiring as fixed, which Freerouting never rips or shoves. Unlocked pre-routes are no better: KiCad exports them as `(type route)`, which Freerouting reads as USER_FIXED, also a wall (finding of branch `bus-wire-types`, `translate.set_wire_types`). So on the first route the module copper is a wall, whatever its lock. Later finishing passes lock only the critical copper.

## Arms (`setup.sh`; joint-fixed; J1's restart wrapper `--parallel 4 --first-s 300 --scale-first --slack 1.15 --resume 0.5 --final lastmile --check-placement`; 900 s x sqrt(fp/40); interleaved)
- **R:** staged without the module stage (`kae.joint.cli --max-iters 0 --no-modules`, J1 arm a).
- **M:** staged with the module stage, its copper locked as today (`--max-iters 0`, J1 arm b).
- **M-soft:** as M, but on the first route the module copper is unlocked and typed `shove_fixed`, so Freerouting may rip it, not shove it (`--set module_soft=1`, commit "module_soft" on branch `chassis-soft`). Resumed waves and the final last mile are as in M.

Code: branch `chassis-soft` (main, the loop-report change, `bus-wire-types` for the wire types, and `module_soft`). Seed 0, k = 1.

## Boards
The 160 boards of `loop-physics-matched` (`boards.txt`): `physics_inputs_ok` and `route_demand` easy or moderate, usable and qualified, one per repo family. On these, 95 boards were fully routed by both arms of that experiment, which is above the 80 the J21 floor needs. Extension: `boards-extension.txt` (160), run once if the primary is undecided.

## Outcomes and decision (`analyze.py`)
**Primary, physics.** For each of M vs R and M-soft vs R: on boards both arms route fully, over modules valued in both, `x = ln(Σ min(u,5) arm / Σ min(u,5) R)`.
- Better: median ratio below 1 by more than the J21 floor for the number of differing boards (1.04 at n ≥ 80), with sign-flip p < 0.025 (two comparisons).
- Worse: the mirror case.
- Otherwise undecided: run the extension once.

**Opens guard.** An arm's total open connections at most 3 % above R's, and not significantly worse (paired sign-flip on `d = (o_arm − o_R)/(o_arm + o_R + 1)`, p < 0.05 against the arm).
- "The case for the module stage" is physics better and the opens guard held.

**The soft mechanism, M-soft vs M.** Opens, paired as above; reported with its p, not a pass/fail.

**Reported:**
- Survival of module copper: from each run's kept attempt (`route.module_copper`: share of length the first route left in place). Expected about 100 % for M, since it is locked. For M-soft it says how much Freerouting ripped.
- Also: cp1, legal, completion, DRC errors total and per type, CPU per arm, and physics per structure kind.

## Costs (information only)
J1's wrapper is about 0.66 CPU-h per board and arm: about 320 CPU-h for 160 boards and 3 arms.

## Addendum after the 2-board smoke (2026-11-11, before the other 158)
Plumbing only, and both boards stay in the batch. All 6 runs finished and were scored, with physics evaluated. The survival record works:
- On jordanaceto-micro-ox, M kept all 31 module tracks (44.7 mm) on the first route; M-soft kept 10 of 27 (19.0 of 41.8 mm).
- The other board had no module copper (no record).

"Kept" means the same geometry. Copper Freerouting ripped and re-laid elsewhere counts as not kept. No rule changes.
