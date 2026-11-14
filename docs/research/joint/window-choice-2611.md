<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Windows chosen from evidence: blocked diagnosis, tabu, exact legality

Scope: three changes to how `kae.joint` chooses and legalizes its windows, and their test against staged restarts at the same counted allowance (experiment `loop-win`).
Not here:
- why windows lost before: [window-budget-2611](window-budget-2611.md), branch `loop-exp`;
- the design sketches these build: [window-choice-proposal-2611](window-choice-proposal-2611.md), branch `loop-exp`.

Keys: joint loop, windows, window_evidence, kae.route.blocked, tabu, legal_exact, home_grid_illegal, illegal after repair, counted budgets, J15, J16

**Status:** built, under test. No verdict yet.
**First published:** 2026-11-14, branch `loop-win-combo`.

## The evidence these answer
- At equal allowance, staged restarts beat windows: 4,485 vs 5,655 opens on 69 boards, p 0.0001 (`loop-compute-matched`).
- 41-53 % of windows reuse a part set the board already tried. Repeats are kept a third as often as new windows (47 of 919, against 163 of 1,227).
- About a third of windows end "illegal after repair", whatever the legalizer's time (J4).
- A window is the parts at a connection's two ends, not what blocks the connection.

## The changes (each a flag, off by default)
- **`window_evidence`** (branch `loop-win-evidence`): each incumbent is diagnosed once by `kae.route.blocked` (nets in window order, at most 30 s and 5 % of the budget). The diagnosis set-up is charged as one DRC under counted budgets. Its records now name the parts to blame:
  - Not every open connection opens a window. A connection opens none when its binding rule gap is against a pad of its own footprint, or when its pad is walled in by its own footprint: no part move frees it. J3's DRC types open no window either.
  - Congestion means a route exists without our other copper. That route's corridor, and the movable parts beside it, join the window.
  - A rule gap against another part's pad, or a wall of other parts' pads, adds those parts.
- **`tabu`** (branch `loop-win-tabu`): a failed part set waits until a window kept after the failure shares a part with it or lies within the loop margin. Meanwhile the next, larger attempt is tried.
- **`legal_exact`** (branch `loop-win-exact`): the grid rounds outward, so a pose the exact model and KiCad accept can be grid-illegal. A window still grid-illegal after greedy goes to the exact closed loop. It stands if the exact check is clean. Every run now reports `home_grid_illegal`, which says whether the incumbent itself was grid-illegal.
- **No flag** (branch `loop-win-frcharge`): under counted budgets the window router's budget follows charged work, not wall seconds. Before, it moved with host load. Charging Freerouting's start-up and optimizer is `fr-budget-calibration`'s work; it is not merged and not used here.

## Test
Pre-registered in `tools/kaeres/experiments/loop-win/PLAN.md`.
- **Arms:** six, at one commit and the same counted allowance: R (staged restarts), W0 (joint, two budgets of windows, no module stage), then W0 with each flag alone and with all three.
- **Boards and seeds:** the 69 boards where the joint loop leaves opens, with an extension of route_demand hard/extreme boards while the primary is undecided. Seeds 0 and 1 for R, W0 and Wall.
- **Analysis:** `analyze.py`.

## Results
Pending.
