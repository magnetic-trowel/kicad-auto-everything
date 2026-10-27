# Exact physics in the optimizer before routing (dead end) and the fidelity switch

**Status:** did not work for placement decisions; the exact evaluator works as a tool (`--physics-fidelity`); cached thermal FV untested in the placer; physics engine design only.
**First published:** 2026-10-23, commit [c5c53c4](https://github.com/magnetic-trowel/kicad-auto-everything/commit/c5c53c40404a972ba3ede1e0d3ab1a5dcc3e58a0) on branch `claude/vigilant-mayer-i91rrr` (designs and polish [6d731a8](https://github.com/magnetic-trowel/kicad-auto-everything/commit/6d731a8168626034c1c30f3954f8e346a2507f53); fidelity switch [0591403](https://github.com/magnetic-trowel/kicad-auto-everything/commit/05914032a3de8de6a67ff4f0680e70dda33f23c4), A/B [92afed4](https://github.com/magnetic-trowel/kicad-auto-everything/commit/92afed425d64f665ec8783cf806f37f94d3cd24a)).

Would the placer choose better if it priced moves with exact physics (PEEC loop inductance, finite-volume thermal) instead of the [fast place terms](kae-physics-terms.md)? We measured cost and decision value for eight designs. Exact pricing is 10^3-10^4 times slower per move, and before routing the "exact" reference is itself as uncertain as the fast estimate, because the copper does not exist yet: a greedy polish choosing by PEEC ends only 1.9% better (median of 10 boards). We kept exact physics only after routing, as an optional switch; on splits A+B it changed 0 of 50 decisions.

## Idea and how it works

**Evaluators at the same poses.** fast (place terms); detour (fast with the routed-detour stretch); cf (each hop routed on a 0.1 mm grid by any-angle Dijkstra plus string pulling, then closed forms); cfm (Manhattan routing); PEEC (multi-filament, image plane, inductive limit); FV thermal (heat into the outer layer, or into every layer = perfectly stitched).

**Decision flips.** Candidates: up to 6 parts per structure kind on all 112 boards, three 1-5 mm translations and three rotations each. A flip is two candidates ordered differently by two evaluators when the reference separates them by >= 1% of an allocation. Comparing route style alone (cf vs cfm) gives the "route floor": the disagreement that comes only from not knowing how the copper will run.

**Designs evaluated** (`ex_*` scripts): (a) a global exact `delta` in the annealer; (b) multi-fidelity top-K (fast ranks, exact re-scores the best K); (c) per-structure bias correction; (d) Schur-complement windows; (e) exact only where copper exists (after routing); (f) a learned surrogate for the residual; (g) asynchronous exact evaluation on 50 cores; (h) placement-invariant operators (FV with cached source fields, a Green's-function table).

**Fidelity switch** (`kae.physics.exact`, design (e) then (b)). `loop_value(lp)` evaluates the routed-loop network that the module stage and the routed recheck already build (strips at a height over the reference plane, vertical pieces, KCL-tied alternatives) by PEEC: each strip split into nw filaments across its width (filament < h/3, <= 60, >= 1.2 t), vias as 6-filament rings, partial inductances by Neumann's integral (Grover closed forms for parallel filaments, zero for perpendicular, Gauss-Legendre graded toward the closest approach for oblique or crossing ones), images with reversed current; loop L = the minimum magnetic energy under the pieces' current sums and the KCL rows with non-negative alternatives. Filament-matrix blocks are cached per piece pair (warm quotes about 1-2 ms). `--physics-fidelity fast|exact|multi`: `exact` makes `Loop.value` PEEC; `multi` re-scores the fast top K (default 4) of each decision with `exact.pick(cands, rescore)`; final reported values are PEEC; `exact.configure(mode, k)` makes the joint loop's acceptance physics exact.

**ThermalFV with cached source fields** (design (h)). The thermal operator (zones as placed, FR-4, convection) does not change when parts move, so a 2.5-D finite-volume model is factored once; the field of each 1 W source is solved once per source pose and cached; a victim move only reads fields, a source move costs one solve.

**Physics engine design** (not built). Each band (DC, thermal, inductive limit, lossy AC) is one symmetric operator on one discretization, factored once per (operator, band, epoch) by supernodal Cholesky (pivot-free LDL^T for AC); copper held as exact polygons with disposable discretizations (1-D strips for tracks, sparse P1 tile quadtrees for pours, Peaceman wells for vias); optimizer windows get boundary Schur complements (window ordered last in one factorization) rather than Green blocks; commits as rank-k up- and downdates; an epoch ends only at a topological event. Details: [physics-engine-design](../../topics/architecture/physics-engine-design.md).

## Results

| measure | result | source |
|---|---|---|
| cost per move, exact vs fast | 12-363 ms vs 10-154 us (median by board), 10^3-10^4x; 0.1-35 CPU-h per board at today's move count; routing is 83-94% of the exact cost | [exact-physics-options](../../topics/physics/exact-physics-options.md) |
| route floor (route style alone) | flips 8-11% of pairs; PEEC vs closed forms on the same copper 0.3-3.3% | same |
| fast vs PEEC flips | commutation 15%, decap 15%, ESD 10%, crystal 19%, coupling 17%, thermal (vs FV) 26-30%; PEEC's best is in fast's top 3 in 91-100% | same |
| greedy polish choosing by PEEC | 1.9% lower exact cost, median of 10 boards (2.3x better to 1.8x worse per board) | same |
| correction factors, leave-one-board-out surrogate | removed almost no flips | same |
| Green's 1 mm thermal table | 2k-6k solves, 16-137 MB; still flips 14% vs direct FV | same |
| exact values missing | 44% of decap evaluations (caps on the far side) | same |
| fidelity switch vs reference | equals `pw_peec` to 1e-12 on Manhattan copper, 2e-6 oblique (18 tests) | [exact-physics-in-kae](../../topics/physics/exact-physics-in-kae.md) |
| `multi` locally, 5 boards | PEEC changed 4 of 41 decisions (decap via sites, -0.2 to -1.0% each); closed forms read +1.8 to +6.4% high per board median | same |
| A/B at 92afed4, critical router, A+B, 33 boards, k = 2, 1800 s | fast vs multi: cp1 0.667 / 0.667, cpk 0.697 / 0.697; 50 decisions re-scored (226 PEEC calls, 1.1 s), **0 changed** | [physics-fidelity-92afed4](../../../bench/results/2026-10-24-physics-fidelity-92afed4.md) |
| `multi` in the joint loop, 6 boards, 2 seeds, local | not better (14 / 10 vs 11 / 8 unconnected; noise) | [joint-loop-b6](../../../bench/results/2026-10-24-joint-loop-b6.md) |
| ThermalFV | unit-tested (rises within 1e-9 of the FV reference); not wired into the placer | [exact-physics-in-kae](../../topics/physics/exact-physics-in-kae.md) |
| engine benchmarks (whole-board DC operators of 3 open boards) | compiled Cholesky refactors 6-13x faster than SuperLU at 0.08-0.8M nodes in about half the memory; Schur window 1.6 s at 281k nodes vs 51 s for a Green block; quotes 25-110 us; commit 20-60 ms; within 1e-10 of brute force | [physics-engine-design](../../topics/architecture/physics-engine-design.md) |

All numbers compare models with models (PEEC, FV); none is a measurement.

## Verdict

Exact physics before routing did not pay: the reference is only as good as the guess about where copper will run (route floor 8-11%), the routed objective is rugged (one board 1.8x worse), and each move costs milliseconds. Fast terms plus detour calibration are good enough to choose by. Exact physics is worth having where the reported number matters (finished-board physics) and it costs little there. Left open: split-C boards with larger cells might still change `multi` decisions (untested); planes are ideal per strip; the cached ThermalFV could fix the weak thermal term but was never wired into the annealer; the physics engine was not built.

## Code

- `kae/src/kae/physics/exact.py` (PEEC loop values, `pick`, `configure`, `ThermalFV`); flags `--physics-fidelity`, `--physics-k` in `kae.route.critical_cli` and `kae.joint.cli`. Test: `kae/tests/test_physics_exact.py`.
- Studies: `tools/research/physics/ex_exact.py`, `ex_decision_flips.py`, `ex_cost_table.py`, `ex_scaling.py`, `ex_polish.py`, `ex_surrogate.py`, `ex_thermal_table.py`, `ex_window_quotes.py`, `ex_fidelity.py`, `ex_fidelity_report.py`; engine benchmarks `eng_board_scaling.py`, `eng_compiled_cholesky.py`, `eng_discretization.py`, `eng_window_schur.py`.
- First appearances: [c5c53c4](https://github.com/magnetic-trowel/kicad-auto-everything/commit/c5c53c40404a972ba3ede1e0d3ab1a5dcc3e58a0), [6d731a8](https://github.com/magnetic-trowel/kicad-auto-everything/commit/6d731a8168626034c1c30f3954f8e346a2507f53), [0591403](https://github.com/magnetic-trowel/kicad-auto-everything/commit/05914032a3de8de6a67ff4f0680e70dda33f23c4); engine benchmarks [05c03b6](https://github.com/magnetic-trowel/kicad-auto-everything/commit/05c03b682433c116f6042d2fdbfd2870f45f0425), [34a12a8](https://github.com/magnetic-trowel/kicad-auto-everything/commit/34a12a8e561cd161f1e7e5983700aa50f0b47d1f), [fdd1b35](https://github.com/magnetic-trowel/kicad-auto-everything/commit/fdd1b35ff79e2a4dcc7c23622148480138eb92f6).

## Related

[kae-physics-terms](kae-physics-terms.md), [physics: solver ladder and core](../physics/physics-ir-and-core.md), [critical copper routing](../routing/kae-critical-copper.md), [kae-joint-loop](../joint/kae-joint-loop.md).
