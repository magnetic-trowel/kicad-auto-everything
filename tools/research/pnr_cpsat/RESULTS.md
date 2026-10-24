<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Exact CP-SAT window place-and-route as LNS (tag `cpsat`)

**Verdict: no merit** at these window sizes and budgets. Every window run reported here
(about 750) ended FEASIBLE, INFEASIBLE or UNKNOWN, never OPTIMAL. Running the same loop with
the CP-SAT step removed scores the same, and `methods.repair` beats both.

## Idea and source
Catalog ideas 12 and 36. SP&R (Lee et al., TCAD 2021) places and routes standard cells
exactly with SMT. Numberlink and Factorio-SAT solve small grids with SAT path encodings. The
idea here: free a window of 2–6 parts and solve it exactly.

## Mechanism (`cpsat_lns.py:cpsat`)
- **Start and window:** start from `seq_phys`. Pick an unrouted or most detoured net and a
  ≤ 9 mm window with 2–3 movable parts. Rip up those parts and every net that touches them or
  crosses the window.
- **Grid:** 0.6 mm pitch (≥ the track halo), 2 layers. Cells blocked by fixed copper on the
  0.1 mm grid get no variables.
- **Poses:** Booleans over the current pose plus the top-6 `Kit.candidates` poses, on the
  fine grid (a coarse lattice is optional). Legality is checked against the fixed keep-out
  planes, `NoOverlap2D` runs per plane, and pad halos keep other nets out of their cells.
- **Routing:** terminals are pose-dependent pad cells, fixed pads, a border exit priced by
  its distance to the outside pins, and the crossings of nets that only pass through. A
  minimum spanning tree splits each net into 2-terminal connections. Each connection is a
  Numberlink path (degree 1 at its two endpoints, 0 or 2 elsewhere). Cells are exclusive per
  net, and a via clears its 8 neighbours.
- **Objective:** 3000 per missed connection, plus length, plus 2 mm per via, plus exit
  cost, plus 2 × the kae physics delta of each pose.
- **Solve:** first route with the current poses fixed (as assumptions), which gives a
  complete hint, then free the poses. CP-SAT runs with 1 worker, no LP, no presolve, and
  3 deterministic s.
- **Decode:** snap to the engine grid, re-route the ripped nets with PathFinder, and accept
  if routed cost + 2 × physics fell.

## What failed, and why exactness does not pay here
- **Flow encoding:** a flow per net missed 9 of 16 terminals with the parts fixed, after
  30 s on 4 workers. The Numberlink encoding, LP off (incumbents 4× better) and presolve off
  (probing took 4 s) were needed just to get usable incumbents. Without the phase-1 hint,
  free models ended UNKNOWN.
- **Routing never converges.** With the parts fixed, a 5-connection window (8k variables)
  scored 672 at 1 s, 404 at 3 s and 292 at 10 s, and was still not proven optimal at 30 s.
  At 3 s, the model left ≥ 1 connection unrouted at the current poses in 40 % of dev6
  windows, on boards the engine routes completely. Pose choices therefore follow search
  noise and grid artefacts.
- **Head-to-head on identical windows and states:** 28 windows were run with 4 model
  variants (lattice, LP on, radius 3), 112 CP-SAT runs in all.
  - The repair heuristic improved 14 of the 28 windows.
  - CP-SAT moved a part in 17 of 112 runs and improved the board in 6.
  - CP-SAT beat the heuristic in **0** of 112.

## Window statistics (harness logs; medians)
| run | windows | parts | cells | poses | vars | solve wall | moved | accepted (with move) |
|---|---|---|---|---|---|---|---|---|
| dev6, 3 s | 163 | 2 | 208 | 43 | 10.9k | 7.9 s | 39/147 | 10 (2) |
| dev6, 10 s | 72 | 2 | 209 | 29 | 10.9k | 14 s | 17/67 | 6 (2) |
| phys10, 3 s | 398 | 3 | 199 | 41 | 10.2k | 2.3 s | 71/306 | 21 (4) |

"Moved" counts windows where CP-SAT moved at least one part, out of the windows it solved.
In the "accepted" column, the number in brackets is how many accepted windows included a
CP-SAT move.

## Results (120 CPU-s, engine v5)
The length column covers the boards that every run in the comparison completed.

**dev6:**

| run | legal | clean | completion | length (4 boards) | vias | wall t |
|---|---|---|---|---|---|---|
| pnr-seq-v5 | 0.667 | 0.667 | 0.904 | 682 | 8 | 45 |
| cpsat-repairctl (`methods.repair`) | 0.833 | 0.500 | 0.921 | 594 | 5 | 214 |
| cpsat-null (same loop, no CP-SAT) | 0.667 | 0.667 | 0.908 | 681 | 8 | 257 |
| **cpsat** | 0.667 | 0.667 | 0.908 | 680 | 6 | 353 |
| cpsat-t10 | 0.667 | 0.667 | 0.908 | 685 | 6 | 205 |

**phys10:**

| run | legal | clean | completion | length (5 boards) | place terms ×human | routed ×human |
|---|---|---|---|---|---|---|
| pnr-seq-v5 | 0.70 | 0.30 | 0.858 | 1224 | 4.05 | 1.39 |
| pnr-seq_phys-v5 (cpsat's start) | 0.70 | 0.30 | 0.859 | 1260 | 1.52 | 1.26 |
| **cpsat-phys10** | 0.70 | 0.30 | 0.869 | 1341 | 1.67 | 1.24 |

- **Physics scoring:** `pnr_phys/physics_score.py`, as the geometric mean of method / human.
  pnr-anneal_phys-v5 had only 7 of its 10 boards when scored (place terms 1.98).
- **Load:** the load average was about 11 on 4 cores. Budgets are CPU seconds, and CP-SAT
  uses deterministic time.
- **Coverage:** not run on all 33 boards (not promising). The ab33 pnr-repair-v5 baseline
  did not exist yet, so the dev6 repair control was run here instead.

## Next step
Keep only the exact *joint pose choice*. Run CP-SAT over a few candidates per part, with
pair costs measured by the engine's own router (each pose pair routed once and cached)
instead of a coarse cell model. That is a small quadratic assignment, which CP-SAT proves
optimal in milliseconds.
