<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Side assignment: what a part's side costs (2026-11-09)

Scope: J42, J43, E113, E114: does withdrawing the human's side assignment change routing and assembly? Not here: a real side-flip move in the annealer (J44), decided by this experiment.
Keys: side assignment, force-front, single reflow, second reflow, double-sided assembly, side_front.py, side-front-ab, J42, J43, J44, J45, E113, E114

**Status:** experiment `side-front-ab` pre-registered ([PLAN](../../../tools/kaeres/experiments/side-front-ab/PLAN.md)); no results yet.

## Mechanism
Every place and joint result inherits each part's side from the human layout (no placer flips a part; [bench/README](../../../bench/README.md), J45). `tools/research/place/side_front.py` withdraws it: before placing, it flips back-side SMD parts on the task input with pcbnew (passives first, then the rest, smallest first, up to a front courtyard fill of 0.70 of the board). Scoring is unchanged (`score.py` transplants side). Through-hole parts, anchored parts, test points, fiducials and logos stay.

## What a side costs, not only in routing
- **Assembly.** A populated back is a second stencil and a second reflow, and the first side's joints re-melt on the second pass: parts on the underside must hold by surface tension or glue, so heavy parts and BGAs want the first side, and a mis-sized part falls. A board with no SMD on the back needs one reflow pass; `single_reflow` in the `KAE_SIDE` line is that count.
- **Thermal mass.** One side carrying all parts concentrates the thermal mass on it: soak and peak are set by the heaviest area, and a dense top with an empty bottom loads differently than two thinner halves. The front fill after flipping is reported as the proxy; no thermal-mass solver is run.
- **Routing.** Back-side parts are obstacles on B.Cu. Moving them frees the layer and crowds the front.
- **Function.** Decaps directly under BGAs sit on the back for loop inductance: flipping them lengthens that path.

## Scope of the data
Merit boards with more than 10 back parts are 43 by count, but that count includes through-hole parts drawn on the back (freedsp's are all through-hole); 17 merit boards pass every filter (more than 10 SMD parts on the back when parsed, at most 1,000 pads, assembled courtyards at most 85% of the outline, `usable_route_test`), so 133 corpus boards fill the 150-board suite.

## Open questions
Results and the J44 verdict when `side-front-ab` finishes.
