<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Combined baseline: what each session needs (collected 2026-11-08)

On hold until counted-work budgets pass their acceptance test: the same recipe at two load levels must
give the same result. Run it at the integrated commit after that (integrate-2611b plus the
counted-budget change). Whichever session has queue room runs it, as one campaign.

**Inputs**
- The current board corpus. Its 10 boards with repaired `.kicad_dru` files
  (`tools/research/board-sourcing/dru_fixes.py`, manifest `dru_fix`) get new task ids.
- kaeres at or after 2c22c18.

**How to run it**
- Every job `--class timed`.
- One-board smoke first.
- Size the kaeq timeout for the hardest board, and retry time-outs before analysing (see the lessons in
  `tools/kaeres/README.md`).

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
