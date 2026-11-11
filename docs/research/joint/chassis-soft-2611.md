<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# The module stage under restarts, its copper locked or rippable (chassis-soft, 2026-11-11)

Scope: whether the joint chassis's physics gain and its cost in open connections come from the module stage, and whether that cost is the module copper acting as a wall to Freerouting. Not here: the windows ([window-budget-2611](window-budget-2611.md), branch `loop-exp`).
Keys: module stage, critical copper, Freerouting wire types, shove_fixed, USER_FIXED, module_soft, copper survival, physics, restarts

**Status:** module stage **partial**: it decidedly improves routed physics but decidedly costs open connections. Rippable module copper (`module_soft`) **did not work** as a fix. Not merged.
**First published:** 2026-11-11, branch `chassis-soft` (`module_soft` and the survival measure in `kae/src/kae/joint/stages.py`), experiment `chassis-soft` (`tools/kaeres/experiments/chassis-soft/PLAN.md`, pre-registered).

## Mechanism checked in code
The first route after the module stage locks every item on the board (`critical_write.edit(..., lock="all")`), so Freerouting gets the module copper as fixed wiring it never rips or shoves. Unlocked copper would be no different: KiCad exports it as `(type route)`, which Freerouting reads as USER_FIXED (branch `bus-wire-types`). `module_soft` sends that copper unlocked and typed `shove_fixed` instead (rippable, not shoved), on the first route only.

## Setup
160 boards (`physics_inputs_ok`, easy or moderate route demand, one per repo family; the boards of `loop-physics-matched`). Three arms under J1's restart wrapper at the same allowance (900 s × sqrt(fp/40), `--parallel 4`), interleaved; KiCad and the physics evaluator scored all 480 runs.
- **R:** staged, no module stage.
- **M:** module stage, copper locked as today.
- **M-soft:** module stage, copper rippable on the first route.

## Results

| | R | M | M-soft |
|---|---|---|---|
| open connections | 992 | 1,555 | 1,656 |
| clean (cp1) | 114 | 101 | 105 |
| legal | 153 | 151 | 153 |
| DRC errors | 124 | 129 | 121 |
| CPU | 95.3 h | 110.2 h | 106.3 h |
| module copper left in place by the first route | | 100 % (155 boards) | 74.8 % of 34,322 mm (154 boards; all kept on 14) |

Paired, on boards both arms route fully (modules valued in both), with a J21 floor of 1.04:

| pair | opens: fewer / more, p | physics median ratio, n, p |
|---|---|---|
| M vs R | 8 / 41, p < 0.0001 (+57 %) | **0.812**, 98, p < 0.0001: better |
| M-soft vs R | 12 / 32, p 0.0007 (+67 %) | **0.914**, 103, p 0.006: better |
| M-soft vs M | 33 / 19, p 0.012 (totals +6.5 %, driven by a few large boards) | 1.072, 95, p 0.14 |

Per kind, M vs R:

| kind | median | n | p |
|---|---|---|---|
| decap | 0.733 | 95 | < 0.001 |
| crystal | 0.381 | 7 | 0.03 |
| chain | 0.931 | 17 | 0.009 |
| cell | 0.909 | 14 | 0.85 |

## Verdict (pre-registered rules)
- **The module stage carries the joint chassis's trade.** Under restarts alone, M against R gives the same picture as joint plus windows against R in `loop-physics-matched`: physics about 19 % better (0.812 vs 0.815) and open connections about 57 % worse (+61 % there). The case for the module stage fails its opens guard.
- **The wall is not the main cause of that cost.** With rippable module copper, Freerouting removes or moves a quarter of it. Per board, M-soft has fewer opens than M (33 better, 19 worse, p 0.012), but it stays far behind R (+67 % in total) and gives back about half of the physics gain (0.914 vs 0.812 against R). M-soft therefore fails as a fix: it trades physics for opens at a worse rate than simply not running the module stage.
- **What remains:** the module stage's placement and copper choices themselves cost routability. A module stage that leaves corridors (routability in its objective), or that runs only on boards that route easily, is the open question, not the wire type.
