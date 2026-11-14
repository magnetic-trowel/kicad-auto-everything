<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# cf-windows: completion-first with windows on open boards (CF-W) against completion-first (CF) (pre-registered)

Written 2026-11-14, before any run of this experiment.

`completion-first` passed non-inferiority against the best of two restart runs: opens 515 vs 573, clean 115 vs 114, physics 0.833.
- On a board left open after phase 1, CF spends its second allowance on another restart run R'.
- `loop-polish` found that the joint loop's windows on the kept board remove opens on hard boards (−9.6 %, p 0.0003).
- `polish-merit` found no gain where boards end nearly complete.
- CF-W asks whether the windows beat R' exactly where they are used: boards still open after phase 1.

## Change under test (branch `cfw-test`, off `restart-completion-first` dd80151)
- `restart.py --open-alt CMD`. In the completion-first policy, when phase 1's board is not clean, phase 2 runs CMD once on that board (`@BEST@`) instead of COMMAND with the next seed.
  - Its board is kept when it ranks no worse.
  - Its time is the restart phase's work: `--parallel` × the remaining half, because a restart phase runs that many lanes and the loop runs one. This keeps counted work matched.
- Without `--open-alt` nothing changes.

## Arms (`setup.sh`; joint-fixed; the completion-first wrapper as tested: `--parallel 4 --first-s 300 --scale-first --slack 1.15 --resume 0.5 --final lastmile --check-placement --policy completion-first`)
- **CF:** `--alt` M-clock (`--max-iters 0 --set module_clock=1`), as in `completion-first`, run again.
- **CF-W:** CF plus `--open-alt 'kae.joint.cli run --start @BEST@ --no-modules'`: `loop-polish`'s windows phase on phase 1's board.

**The same in both arms:**
- Counted-work budgets (`KAE_BUDGET=work`, `PYTHONHASHSEED=0`, `KAE_WORKERS=1`), `--time` two R allowances.
- Freerouting d137fd1.
- Seed 0, k = 1, interleaved jobs.
- Phase 1 is the same command and seed in both arms, so the open-board subset is defined by phase 1.

**Caveat:** Freerouting's optimizer is not charged or capped in work mode (`fr-budget-calibration` pending). The two arms are exposed differently here: R' runs Freerouting, while the loop's windows run it less. So `timed_out` counts are read per arm.

## Boards
`completion-first`'s 160 (`boards.txt`).

## Decision (CF-W against CF, paired per board)
- **Primary, opens on the open subset:** boards whose phase-1 board is not clean (CF's `phases[0].rank[1]`). Paired `d = (o_W − o_CF)/(o_W + o_CF + 1)`, sign-flip.
  - CF-W wins if mean `d` < 0, p < 0.05, and total opens at least 3 % lower. CF wins on the mirror.
- **Guards for a CF-W win, all 160 boards:**
  - clean not lower by more than 2 boards;
  - DRC errors not above CF's by more than 3 %;
  - physics on boards both route fully: median Σu ratio CF-W/CF within the J21 floor.
- **Also reported:**
  - opens and clean on all boards; legal; errors per type;
  - phase-1 agreement between arms;
  - CF-W's phase-2 choices;
  - per arm, real CPU (the harness's measured CPU) against charged work (the nominal allowance);
  - optimizer `timed_out` counts.

## Smoke
2 boards × 2 arms, of which at least one is open after phase 1. Plumbing only.

## Smoke (2 boards, 828d8f9): plumbing only
Both boards were open after phase 1, and phase 1 was identical in both arms.
- **dxem:** both arms went from 4 to 2 opens. CF got there with R', CF-W with `open-alt`, which was kept.
- **gos2022:** CF's R' was worse and phase 1 was kept. CF-W's windows tied phase 1 and were kept.

Every run was scored. No rule changes.
