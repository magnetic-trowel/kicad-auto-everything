<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Exact CP-SAT window place-and-route as LNS (tag `cpsat`)

**Verdict: no merit** at these window sizes and budgets. CP-SAT never proved a window optimal.
Its part moves almost never survived real routing. The same LNS loop without CP-SAT (rip up
and re-route only) scores the same, and the heuristic window repair beats it.

## Idea and source
Catalog ideas 12 and 36 (`docs/ideas/original/joint-pnr.md`). SP&R (Lee et al., TCAD 2021)
solves placement and routing of a standard cell exactly with SMT. Numberlink / Flow-Free and
Factorio-SAT show that SAT path encodings beat A* on small grids. The transfer: free a window
of 2–6 parts and solve it exactly.

## Mechanism (`cpsat_lns.py`)
- **Start:** `methods_phys.seq_phys`. Each round: pick a target net (unrouted, else most
  detoured), and a ≤ 9 mm window around it holding 2–3 movable parts (blockers and the net's
  own parts first). Rip up those parts and every net that touches them or crosses the window.
- **Coarse grid:** pitch 0.6 mm (the smallest even multiple of the cell that is ≥ the
  track-to-track halo), 2 layers. Cells blocked by fixed copper on the 0.1 mm grid get no
  variables.
- **Poses:** one Boolean each, drawn from the current pose plus the top-6 HPWL candidates of
  `Kit.candidates`, on the fine grid. A coarse lattice is optional. Legality is checked
  against the fixed keep-out planes, `NoOverlap2D` keeps keep-out boxes apart per plane, and
  each pad's halo keeps other nets out of its cells.
- **Routing:** each net's terminals are pad cells chosen by the poses, fixed pads, a
  window-border exit priced by its distance to the outside pins, and the boundary crossings
  of nets that only pass through. A minimum spanning tree turns the terminals into
  2-terminal connections. Each connection is a Numberlink path: a chosen endpoint has degree
  1, any other cell has degree 0 or 2. Cells are exclusive per net, and a via clears its 8
  neighbours.
- **Objective:** 3000 × missed connections, plus wirelength (0.1 mm units), plus 20 per via,
  plus exit cost, plus 2 × the kae physics delta of each pose (first order).
- **Solve:** first route with the parts at their current poses (as assumptions), which gives
  a complete hint. Then free the poses. CP-SAT runs with 1 worker, no LP, no presolve, and
  3 deterministic s.
- **Decode:** snap to the engine grid, check with `part_violation`, re-route the ripped nets
  with PathFinder, and accept if routed cost + 2 × physics fell.

## What failed along the way
- **Single-commodity flow per net:** with the parts fixed, it still missed 9 of 16 terminals
  after 30 s on 4 workers. The degree (Numberlink) encoding fixed most of that.
- **Defaults:** with the LP on, incumbents were about 4× worse. Presolve probing took 4 s.
  Without the phase-1 full hint, free-pose models ended UNKNOWN even with the current poses
  hinted.
- **Bounding boxes:** exact boxes made the current placement infeasible, because legal
  touching parts share a raster row. The boxes are now shrunk by one cell, and 9 of 235
  decodes were illegal and were rejected.
- **Routing is the bottleneck, not placement.** With the parts fixed, one 5-connection window
  (8k vars) reached objective 672 at 1 s, 404 at 3 s and 292 at 10 s, and still was not
  optimal at 30 s. At 3 s, the model left at least one connection unrouted at the current
  poses in 40 % of windows, on boards the engine routes completely. The CP-SAT objective is
  therefore mostly search noise and grid artefacts, and pose choices follow that noise.

## Window statistics (dev6 harness runs)
| run | windows | parts | cells | poses | vars | solve (wall) | OPTIMAL | moved ≥ 1 part | accepted (with a move) |
|---|---|---|---|---|---|---|---|---|---|
| cpsat, 3 s | 163 | 2 | 208 | 43 | 10.9k | 7.9 s | 0 | 39/147 | 10 (2) |
| cpsat, 10 s | 72 | 2 | 209 | 29 | 10.9k | 14 s | 0 | 17/67 | 6 (2) |

**Head-to-head on identical windows and states** (3 boards, 28 windows × 4 model variants,
including LP on and a lattice with radius 3):
- The repair heuristic (`methods.repair` inner loop) improved 14/28 windows.
- CP-SAT moved a part in 17/112 and improved in 6/112.
- CP-SAT beat the heuristic in **0/112**.

## Results vs baselines (dev6, 120 CPU-s, engine v5)
| run | legal | clean | completion | length (4 complete boards) | vias | wall t (s) |
|---|---|---|---|---|---|---|
| pnr-seq-v5 | 0.667 | 0.667 | 0.904 | 682 | 8 | 45 |
| cpsat-repairctl (methods.repair) | 0.833 | 0.500 | 0.921 | 594 | 5 | 214 |
| cpsat-null (same loop, no CP-SAT) | 0.667 | 0.667 | 0.908 | 681 | 8 | 257 |
| **cpsat** (3 s) | 0.667 | 0.667 | 0.908 | 680 | 6 | 353 |
| cpsat-t10 (10 s) | 0.667 | 0.667 | 0.908 | 685 | 6 | 205 |

Wall times are under a load average of about 11 on 4 cores, and budgets are CPU seconds.
The run was not taken to all 33 boards because it was not promising.

PHYS_PLACEHOLDER

## Next step
Exact cell-level routing does not pay at 0.6 mm and a few seconds. The useful part of the
exactness is the discrete joint choice of poses. The next thing to try is CP-SAT over a few
heuristic candidates per part, with pairwise costs measured by the engine's own router
(route each pose pair once, cache it) rather than a coarse grid model. That would turn the
window into a small quadratic assignment, which CP-SAT proves optimal in milliseconds.
