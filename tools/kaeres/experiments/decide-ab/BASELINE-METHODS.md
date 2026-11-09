<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Combined baseline: what each session needs (collected 2026-11-08)

On hold until counted-work budgets pass their acceptance test: the same recipe at two load levels must
give the same result. Run it at the integrated commit after that (integrate-2611b plus the
counted-budget change). Whichever session has queue room runs it, as one campaign.

**Prerequisites:** PR #43 (counted budgets) and PR #32 (layer limit, task spec 11) merged, and all task
folders re-prepared at that spec.

**Inputs**
- The current board corpus. Its 10 boards with repaired `.kicad_dru` files
  (`tools/research/board-sourcing/dru_fixes.py`, manifest `dru_fix`) get new task ids.
- kaeres at or after 2c22c18.

**How to run it**
- Every job `--class timed`.
- One-board smoke first.
- Size the kaeq timeout for the hardest board (see the lessons in `tools/kaeres/README.md`).

**Counted budgets** (branch work-budget, `kae.budget`; exact flags come with the counted-budget commit)
- Every kae method runs with `KAE_BUDGET=work PYTHONHASHSEED=0 KAE_WORKERS=1` in its command env, so
  "900 s × sqrt-fp40" means nominal seconds of counted work, not wall time.
- Acceptance (same recipe, two load levels): identical on the router, staged and the restart wrapper.
  Staged without restarts differed by one connection on a medium board (KiCad's ratsnest ties), so expect
  small residual noise.
- Freerouting gets a pass cap automatically through the kae bridge. The stock 2.5.0 and fork methods that
  call it directly are still wall-clock and need their own settings: run them to their own stop (passes
  cap, generous job timeout), so their results do not depend on load either.
- Wall time is then only a safety ceiling, 4× the nominal budget. A run that hits it reports
  `ceiling_hit` and counts as failed, not as a partial result. Investigate every ceiling hit before
  analysing: each one means a stage did uncounted work.

**Routing and physics** (intent/physics work)
- Boards: the 213 physics-set boards. Kind: route. k = 1.
- Restart portfolio: parallel 4, first-s 60, scale-first, slack 1.15, `--resume 0.5 --final`
  last mile, 900 s × sqrt-fp40.
- Methods:
  - kae bridge (restarts) at its defaults;
  - the same with `--finish`;
  - Freerouting 2.5.0, and the fork;
  - the human reference, with physics;
  - stage-2 arms as extra methods: `import_tails`, `escape_ground_vias`.
- Recipes: `route-finish-ab.sh` on branch route-finish-ab.
- Physics: the frozen recompiled intent set for the 213 boards (its location comes from the physics
  work), with pitch 0.25, `KAE_EM_TOL=1e-4` and `eval_intent.sh` as on route-finish.

**Placement** (placement / escape work)
- kae staged (restarts) on joint-fixed: 900 s × sqrt(footprints/40),
  `restart --resume 0.5 --screen --final --check-placement`, k = 3.
  - Boards: the 48 of `zone-ab.boards.txt` plus the 10 of `escape-ab-grid.boards.txt`.
- On the same boards: kae bridge on the human placement (route), k = 2; the Freerouting fork once per
  board (it is deterministic).
- place and place-fixed with physics, on the 213 merit boards, k = 1.

**Audit / decide**
- The 213 merit boards, k = 1:
  - kae joint loop (restarts), joint-fixed;
  - kae staged (restarts);
  - kae critical+bridge (restarts), route.
- Report `legal_strict` and `clean_strict` (score v12), hazard counts and placement shorts per board,
  alongside cp1 and cpk.

**Scoring**
- Score v12 = route zones + strict columns + content-matched duplicate keys.
- A baseline is a snapshot, not a control: each later A/B runs its own control side by side, which the
  kaeres guard from results-2611b enforces.
