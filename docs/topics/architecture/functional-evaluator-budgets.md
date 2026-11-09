<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Functional evaluator: budgets and loop-measure cross-check (`kae.sim.budget`)

Scope: loop-inductance budgets from the board's own testbench, and the boost loop's measures cross-checked. Not here: the rest of `kae.sim` -> [functional-evaluator](functional-evaluator.md).
Keys: kae.sim.budget, `budgets`, board.budgets.json, `Vloop`, cell_body_floor, stand-in, hot loop, pt_mesh_loop, critical_cli route --budgets, power profile

**Results**
- `kae.sim.cli budgets` derives a cell's loop-inductance budget from the board's own testbench; it is applied only from a trusted requirement, when achievable and independent of the stand-in, and only by methods that opt in. On the two smoke boards none passes [M].
- On the boost's routed loop the router's closed form (9.37 nH copper) is within about 5% of a solid-plane mesh reference; the plane slot adds about 1.7 nH it cannot see. The SPICE power-profile extraction reads −38% and must not judge loops [M].

Split from [functional-evaluator](functional-evaluator.md) (§5a there). Tags: [M] measured here, [I] design choice.

## Key facts

### Budgets

The placer and the critical router price every structure as spend over allocation, with the allocation taken from a closed form unless the brief's structure carries a `budget`. `kae.sim.cli budgets` derives that budget from the board's own testbench: for a cell, a series inductance is swept at the cell's loop insertion point (`Vloop`) on the ideal circuit, at every corner. The budget is the loop's ideal inductance plus the largest addition at which the requirement holds at every corner. Budgets are written to `board.budgets.json` and applied only by methods that opt in (`critical_cli route --budgets`). Evaluators never apply them, so a method's budgets cannot change its score.

A budget is applied only if all three hold; otherwise the closed-form allocation stays, and the file records every reason:
1. **The requirement comes from a trusted source:** human, board rule, datasheet, board value, schematic or standard. A budget derived from a prior bound is no better than the closed-form allocation, and on the boost below it was worse.
2. **It is achievable:** at least the loop inductance of the parts' own internal paths alone (`critical_recheck.cell_body_floor`, the router's model). No layout of those parts can go lower.
3. **It does not depend on the stand-in:** the sweep runs with a conservative stand-in (body-diode transit 20 ns, C_oss loss 0.05 Ω) and a lenient one (2 ns, 1 Ω). The budget is the conservative value, and is used only if the lenient one is within 3× of it.

A sweep point where any corner gave no value, up to the first failing point, also blocks the budget: the requirement is then not known to hold at every corner.

On the two smoke boards, no budget passes [M]. Both bounds are priors.
- **Boost:** 1.16 nH, against a floor of 3.12 nH.
- **Motor driver:** 0.24 to 1.78 nH across the stand-ins, against a floor of 7.1 nH. Its prior, a ring that never reaches the rating at 50 ns edges and so is capped at 50 nH, ignores recovery altogether.

The boost's closed-form allocation, 2.08 nH, is itself below its floor: the router can never meet it there.

### Loop measures, cross-checked [M]

On the boost's routed loop, the router's closed form gives 13.2 nH, and PEEC on the same pieces gives 13.1 nH. Without the parts' bodies it gives 9.4 nH of copper. The SPICE loop test, once it covers the whole commutation loop (switch-node copper included), gives 6.6 nH of copper plus 1.0 nH of capacitor ESL. An earlier loop test stopped at the switch pins and gave 2.7 nH; it was not the same loop, and comparing the two was wrong. The copper, drawn: the switch-node trace cuts IC1's ground pad off from C5's on F.Cu, so the return detours to a via 6.5 mm away, as the router models it. A B.Cu track slots the reference plane under the loop, which both fast models ignore. `tools/research/physics/pt_mesh_loop.py` is the reference. It is a nodal PEEC of all the copper in a window, with planes meshed and no plane assumed; it reads −2.4% against an image plane at 0.5 mm pitch.

| Copper-only loop, boost | nH | vs reference |
|---|---|---|
| Reference, F.Cu 0.25 mm, B.Cu 0.5 mm (0.35 / 0.7 mm: 10.96) | 10.59 | |
| Reference with B.Cu filled solid (0.35 / 0.7 mm) | 9.25 | the slot adds about 1.7 nH (+18%) |
| Router's closed form | 9.37 | −11%; within about 5% of the solid-plane reference |
| SPICE extraction, power profile | 6.57 | −38% |

So the router's loop model is the authority for loop inductance. Its error on this loop is the plane slot, which it cannot see. The SPICE extraction has no mutual inductance in the power profile and an ideal plane under each piece, so it must not judge loops (it stays for DC drop and loss, where it was checked). One loop is one data point: the next step is a sample of hot loops across the corpus, to put an error band on the closed form.

## Conflicts and open questions

- One loop is one data point; an error band on the closed form needs a corpus sample of hot loops.
- Stand-in fidelity and numerics: [functional-evaluator § Conflicts and open questions](functional-evaluator.md#open-questions).

## Sources

- Code: [`kae/src/kae/sim/`](../../../kae/src/kae/sim/) (`budget`), [`critical_recheck.py`](../../../kae/src/kae/route/critical_recheck.py) (`cell_body_floor`), [`pt_mesh_loop.py`](../../../tools/research/physics/pt_mesh_loop.py).

See also: [functional-evaluator](functional-evaluator.md), [physics-driven-design](physics-driven-design.md), [critical-net-routing](../routing/critical-net-routing.md).
