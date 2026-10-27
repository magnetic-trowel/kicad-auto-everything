# kae placer: CP-SAT floorplan and compiled annealing

**Status:** worked.
**First published:** 2026-10-22, commit [64a6858](https://github.com/magnetic-trowel/kicad-auto-everything/commit/64a6858cca92b72ead01cdf56e3b5667a71cb2bc) on branch `claude/vigilant-mayer-i91rrr`.

`kae place` places a KiCad board from its netlist: a quadratic seed, physics macros micro-placed by CP-SAT, a CP-SAT floorplan, a numba simulated annealer pricing wirelength, congestion, legality and the [fast physics terms](kae-physics-terms.md), then grid and exact legalization closed by KiCad's own DRC. On split C (79 boards of the qualified suite) it is legal on 72/72 tasks in a median of about 2 minutes, and its physics score is 1,410 against 35,380 without the physics terms and 4,392 for the human layouts (kae's own uncalibrated estimate). Routing our placements is a different story: see [kae-staged](../joint/kae-staged.md).

## Idea and how it works

Pipeline (`kae/src/kae/place/pipeline.py`): Problem -> [brief](kae-comprehension-brief.md) -> macros -> seed -> anneal -> legalize -> exact closed loop -> order pass -> silk pass -> KiCad DRC loop (<= 6 rounds). The last four steps are on [kae-exact-legality](kae-exact-legality.md). Time budget: finish within min(0.85 x time - 10 s, 20 s + 3 s per movable part); the annealer counts CPU seconds, CP-SAT wall seconds with `--workers` threads. Parts keep their side (no side flips).

**1. Quadratic seed.** Object centres minimize weighted squared spring length (clique model, weight w/(pins - 1); ground nets x0.1, power x0.2; clock, high-speed and RF x1.5, analog x1.2; brief structure nets up-weighted). Locked parts anchor through their pins; connectors are pulled to the nearest board edge; a weak spring pulls to the centre.

**2. Spreading.** Pairwise rectangle repulsion with the springs still active, or on big boards `partition_spread`: recursive bisection of free cells per side in proportion to area.

**3. Physics macros** (`clusters.py`). Brief structures become segments whose L1 length is a geometric proxy (decap: cap rail pad <-> paired IC power pin, cap ground <-> nearest IC ground; crystal: pads <-> XIN/XOUT, load caps <-> crystal; cell: consecutive loop members, closed; chain: consecutive members from the connector pin). Structures sharing parts are unioned (IC + decaps + crystal) and anchored on the largest or locked member. CP-SAT micro-places the members (4 rotations, NoOverlap2D per side, minimize weighted segment length + compactness) and enumerates distinct layouts with no-good cuts on the rotation assignment. The layouts are ranked by the real physics terms (`Terms.breakdown`), the best is annealed on them ("the proxy proposes, the physics decides"), and the best K are kept for the floorplan and for the annealer's re-layout move.

**4. CP-SAT floorplan** (`cpsat.py`). Items are parts or rigid macros, each with variants (rotation x internal layout) as a one-hot choice; optional interval variables per member rectangle (own side; drilled pads and back courtyards on the other side); one NoOverlap2D per side including fixed obstacles; the outline as containment in one of the problem's cover rectangles. Objective: L1 displacement from the spread positions + a rotation-change charge + weighted HPWL. Used up to `FLOORPLAN_MAX_ITEMS = 40` items; bigger boards rely on bisection spreading.

**5. Annealer** (`engine.py`, `anneal.py`, `cost.py`). Cost = w_phys * physics (utilization, linear, saturated at `SA_U_SAT = 3` per structure) + w_wl * HPWL / seed HPWL (+ w_cong * RUDY overflow) + lambda(t) * legality (grid overlap area own side / opposite side / obstacles + area outside the outline; lambda ramped geometrically) + w_disp * L1 displacement from the seed + w_order * protection-order violation + w_label * label distance + w_silk * soft silk overlap. Moves: shift with a radius that shrinks with temperature, rotate in place, swap equal or similar-size footprints, macro shift and rotate, macro re-layout from the top K. Ground and power nets with > 40 pins are frozen out of HPWL. `FastAnnealer` (numba) keeps pin coordinates, per-net bounding boxes, a per-side bucket hash of rectangles, an outline summed-area table, RUDY demand per bin and the order rules incrementally. Non-physics parts move entirely inside compiled batches; physics and macro moves are proposed in Python, priced by `Terms.delta` and evaluated by the same compiled move function; aggressor-loop members are sampled at half rate. The schedule runs over a planned move count, so results are reproducible when the budget does not bind. Engine state is passed by value and every extra field costs move rate (12 fields ~ 10%), so label and silk data are packed into two arrays. The Python `Annealer` stays as reference and fallback.

**6. Grid legalization** (`problem.py`, `legalize.py`, `_fastlegal.py`). `Problem` turns each movable part, per rotation, into rectangles: `own` (courtyard box grown to cover pads inflated by half the clearance, so disjoint `own` rectangles imply legal courtyards and pad clearance), `opp` (drilled pads and back courtyard), `board` (pads inflated by edge clearance, plus courtyard), and pins, all rounded outward to the grid g, so grid-legal implies legal. `legalize` groups nearby violators, frees each group plus its k nearest movable parts in a window and minimizes L1 displacement + rotation charge with CP-SAT, growing windows (k x 1.6) on failure and finally freeing everything. The numba greedy fallback keeps a per-side summed-area occupancy table (O(1) rectangle queries) and finds the nearest free origin by L1 rings. The annealed result is kept only if grid-legal after legalization and not costlier than the legal seed.

## What we tried

- Split-C sweeps from frozen snapshots: `tools/research/place/csweep.py run --split C --time 600 -j 24 --workers 2` (79 tasks; the 6 outline-incomplete tasks and 1 fully locked task held out).
- Physics ablation: the same code with `--no-physics` (routability and legality terms only), then each placement routed by the same probe router.
- Free angles (`--angles STEP`) and other estimator-driven extras: see [kae-routability-estimators](kae-routability-estimators.md).

## Results

All seed 0, single run; "physics" is the linear sum of budget utilization, kae's own estimate, human layouts scored by the same code; "legal" = kae's exact model and kicad-cli DRC on the written board both pass (a kae verdict, not the kaebench score).

| run | legal | physics (ours / human) | wall per board | source |
|---|---|---|---|---|
| split C at e171267 (exact model only) | 66/73 | 1,417 / 4,392; better than human on 62 boards, worse on 4 | median 123 s, max 432 s | [place-split-c-e171267](../../../bench/results/2026-10-23-place-split-c-e171267.md) |
| split C at 34fa56b (with KiCad DRC loop) | 67/72 | | median 125 s, max 394 s | [place-split-c-34fa56b](../../../bench/results/2026-10-23-place-split-c-34fa56b.md) |
| split C at fe68468 | **72/72** | 1,420 / 4,392 | median 124 s, max 354 s | same file |
| ablation at 1ef5bf1, physics on / off (71 boards) | 72/72 both | **1,410** / 35,380 off (human 4,392); better than human on 62 (on) vs 11 (off); over-budget structures 463 on, 1,594 off, 869 human | median 125 s on, 109 s off | [place-physics-ablation-1ef5bf1](../../../bench/results/2026-10-24-place-physics-ablation-1ef5bf1.md) |
| ablation per kind, off -> on | | decap 3,907 -> 573, ESD 693 -> 224, coupling 517 -> 14, commutation 464 -> 153; physics better on 70/71 boards | | same |
| routability probe A+B at 1ef5bf1 (Freerouting-fork bridge, 1800 s, k = 2) | 64/66 on, 65/66 off | cp1 0.758 both arms, cpk 0.788 both (human 0.727 / 0.788); HPWL vs human 0.685 on, 0.657 off | | [place-routability-probe-1ef5bf1](../../../bench/results/2026-10-24-place-routability-probe-1ef5bf1.md) |

Annealer throughput on split C: planned moves finished on 75/79 boards, median 11.7k moves/s (5.0k-40.4k). Silkscreen was the systematic loss in the probe (44 silk_overlap), fixed later ([kae-exact-legality](kae-exact-legality.md)). The seed and the macros were not ablated separately; probe-select runs showed the floorplan pulls jittered seeds back together, so seed jitter barely diversifies candidates.

## Verdict

Worked as a placer: legal on every split-C task with the KiCad loop, physics about 3x better than the human layouts and 25x better than without the terms, with no routability cost on A+B. What it does not do is make boards easier to route: on split C, 30/78 of our placements route clean against 43/78 human ones ([kae-staged](../joint/kae-staged.md)), and no estimator we tried predicts which placements fail ([kae-routability-estimators](kae-routability-estimators.md)). The physics score is uncalibrated and single-seed. `kae place` alone is not a merit method; it runs inside both "kae staged (restarts)" and "kae joint loop (restarts)".

## Code

- `kae/src/kae/place/{pipeline,problem,state,seed,cpsat,clusters,engine,anneal,cost,legalize,_fastlegal}.py`; CLI `kae/src/kae/cli.py`.
- Run: `PYTHONPATH=kae/src python -m kae.cli place IN.kicad_pcb OUT.kicad_pcb --time 600 --seed 0 [--no-physics] [--fix-class connectors,mounting,user] [--anneal-args JSON]`.
- Sweeps: `tools/research/place/csweep.py`. Design notes: [kae-place](../../topics/placement/kae-place.md). Tests: `kae/tests/test_place_*.py`.
- First appearances: seed and legalizer [64a6858](https://github.com/magnetic-trowel/kicad-auto-everything/commit/64a6858cca92b72ead01cdf56e3b5667a71cb2bc); macros and RUDY [537d08f](https://github.com/magnetic-trowel/kicad-auto-everything/commit/537d08feff641d222ae645461b953c66ae414227); Python annealer [9fc7c4e](https://github.com/magnetic-trowel/kicad-auto-everything/commit/9fc7c4edbeab6b517ba6d8b1be8ab24f8d3f9da4); `FastAnnealer` [c5c53c4](https://github.com/magnetic-trowel/kicad-auto-everything/commit/c5c53c40404a972ba3ede1e0d3ab1a5dcc3e58a0); `SA_U_SAT` [d28e7de](https://github.com/magnetic-trowel/kicad-auto-everything/commit/d28e7de1e031ceb3475000ab47c777d56ab9a198); `partition_spread` [5deced4](https://github.com/magnetic-trowel/kicad-auto-everything/commit/5deced48667a7b99e3a2bc20fd0acb1b27f54762); `_fastlegal.py` [6b36f77](https://github.com/magnetic-trowel/kicad-auto-everything/commit/6b36f779771940134a3baaca01538a4df501ef1e); csweep [0a0c2b5](https://github.com/magnetic-trowel/kicad-auto-everything/commit/0a0c2b52c681bae9c53a5d6c81546bcdb787f083).

## Related

[kae-exact-legality](kae-exact-legality.md), [kae-physics-terms](kae-physics-terms.md), [kae-fixed-interface](kae-fixed-interface.md), [kae-routability-estimators](kae-routability-estimators.md), [kae-joint-loop](../joint/kae-joint-loop.md).
