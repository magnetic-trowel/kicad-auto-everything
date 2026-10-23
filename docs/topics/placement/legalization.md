# Placement legalization (exact and heuristic)

**TL;DR**
- Every 2025–26 PCB placer ends with a **discrete legalizer**: MILP (NS-Place), cardinal-relation MP (HiePlace), constraint-graph MILP on sliced rectangles (NTU DAC'25), QP (Chen DAC'25), Tetris + Abacus (Cypress), scanline/window (NTU), LP compaction with symmetry (MAGICAL).
- Exact legalizers scale only with **pruning from global placement** (relative positions, cardinal relations) or windows; vanilla MILP found no feasible placement in 4 h on 9–10 of 14 boards (the note's count and per-board list disagree).
- **CP-SAT min-displacement legalization** with NoOverlap2D, keep-outs, decap distance and rotation literals is our measured, Apache-2.0 option ([CP-SAT](../solvers/cp-sat-milp-smt.md)).
- A **sparrow-style overlap-elimination legalizer** (guided local search on jagua-rs hazards) handles irregular courtyards and preserves LLM intent via a displacement term.
- Legalizers must report the **infeasible constraint subset** back to the LLM.

## Key facts

| Legalizer | Mechanism | Evidence |
|---|---|---|
| NS-Place MILP | Big-M non-overlap with orientation binaries r_i and relative-position binaries p_ij, q_ij (`x_i + r_i h_i + (1−r_i) w_i ≤ x_j + W(p_ij+q_ij)`); objective ΣHPWL + (max − min HPWL); **pruned by relative positions from GD placement** when parts are >k apart | Vanilla MILP: feasible only for PCB1 (8 parts, 2.7 s) and PCB2 (18, 6.3 s), 4 h with feasible for PCB3/8/12 (34/36/58 parts), none for PCB4 (28 parts, 6 locked). With GD relative positions: 4.9–6,008 s for ≤64 parts; 1,570-part board hit 14,400 s ([arXiv 2210.14259](https://arxiv.org/pdf/2210.14259) [P]); solver unnamed |
| HiePlace MP | Cardinal up/down/left/right relations eliminate most Booleans; chips and first-priority parts not rotated; greedy alignment fine-tune (300 s timeout); backtrack (relax groups, enlarge chip movement) if infeasible; Gurobi | 13–404 parts in 0.02–120 min; ILP baseline Floorplet found no solution at 308–404 parts in 4 h ([PDF](https://www.cse.cuhk.edu.hk/~byu/papers/J156-TCAD2026-HiePlace.pdf) [P]) |
| NTU CG legalization | Constraint graph for dense, heterogeneous, irregular, any-oriented, double-sided parts; each part **sliced into rectangles**; MILP rather than LP | DAC'25 ([DOI](https://doi.org/10.1109/DAC63849.2025.11133304) [S]) |
| Chen DAC'25 QP | QP legalizer for varied shapes | [S] |
| Chen & Deng graph-based | Constraint graph preserving geometry + adaptive packing + iterative adjustment | 100% legality, fewer ratsnest intersections on industrial samples ([DOI](https://doi.org/10.1088/1742-6596/3079/1/012071) [S]) |
| Cypress | Per-side Tetris then Abacus row legalization (+ macro, greedy) | Also used as "NS-Place+" (routability 1.6× below Cypress) [P] |
| NTU TCAD'25 / DAC'25 LBR | Window-based / scanline | [S] |
| PA-ICM | 1-unit push-apart → spacing table → maximal empty rectangles → resample close-to-pin parts from N(pin, σ=2) | [P] |
| DRLPlace | Boundary-aware push-and-reflection for irregular outlines | [S] |
| Zhao 2025 | Hanan-grid legalization | [S] |
| MAGICAL (analog) | Constraint graphs by plane sweep + transitive reduction + LP compaction with exact symmetry | [P] |
| ALIGN (analog) | ILP per sequence pair (symmetry, alignment, order) | [P] |
| CP-SAT (ours) | Min-displacement model with hard decap/keep-out/edge/fixed constraints; hints from global placement; windowed LNS | Tested only on nearly legal SA outputs: full-board model legal in 3.8–6.9 s at N=30–300 (1 violation each), no solution at N=1000 in 134 s; per-violation-cluster windows (`legalize_clusters.py`) legalized N=1000 (18 violations) in 3.9 s ([benchmarks](../solvers/benchmarks.md) [M]). (Hierarchical CP-SAT + LNS, a placer, stayed feasible at 100–1000.) |
| sparrow GLS (transplant) | Fixed container, allow overlaps, guided local search with adaptive pair weights, exploration then compression | SOTA open 2D nesting ([packing transplants](packing-and-graph-drawing-transplants.md)) |

**Design patterns**
- *Relative-position pruning* (NS-Place): structure from global placement becomes explicit constraints that shrink the MILP and preserve intent.
- *Slice irregular parts into rectangles* (NTU, HiePlace) instead of bounding boxes; keep-outs and outline complement become fixed boxes in the same NoOverlap2D ([CP-SAT](../solvers/cp-sat-milp-smt.md)).
- *Penalty in GP, exact in legalization* (MAGICAL/ALIGN) for every LLM-authored constraint.
- *Infeasibility handling*: HiePlace backtracks by relaxing groups; open-universe scene repair declares unsat after k restarts and asks the LLM to relax; RAC returns conflicting constraints + admissible relaxations ([scene transplants](scene-layout-transplants.md), [LLM routing evidence](../routing/llm-routing-evidence.md)).
- *Exact orientation/side cleanup*: dead-end elimination (DEE) + A*/ILP over discrete rotation × side states with pairwise wirelength/crossing/conflict energies ([packing transplants](packing-and-graph-drawing-transplants.md)) [I].

## Recommendations for our system
- Primary: CP-SAT min-displacement legalizer on sliced footprint rectangles, 0.5 mm grid globally, finer only in windows; relative-position pruning from global placement and cardinal module relations to scale to a few hundred parts; beyond ~300 parts use per-violation-cluster windows, since the full-board model failed at N=1000 and has only been tested on nearly legal inputs [I].
- Alternative/secondary: sparrow-style GLS legalizer for irregular courtyards (MIT/MPL Rust core) with displacement-to-target + HPWL terms [I].
- Always return the infeasible subset (or unsat core proxy) with admissible relaxations; never silently drop LLM constraints [I].
- Follow with SA/LNS detailed placement ([metaheuristics](../solvers/metaheuristics-and-qd.md)) [I].

## Conflicts and open questions
- No head-to-head CP-SAT vs MILP vs GLS legalization study on real PCBs; CP-SAT cannot prove infeasibility of packings in most cases (cpsat-primer).
- NS-Place's MILP solver is unnamed; HiePlace relies on Gurobi (avoid — proprietary; substitute CP-SAT/HiGHS/SCIP).

## Sources
- research notes: [placement_algorithms.md § Q1, Q8](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/placement_algorithms.md); [solver_toolbox.md § 1](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/solver_toolbox.md); [cross_domain_ideas.md § Q3](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/cross_domain_ideas.md)

See also: [algorithm-families](algorithm-families.md) · [solvers/cp-sat-milp-smt](../solvers/cp-sat-milp-smt.md) · [packing-and-graph-drawing-transplants](packing-and-graph-drawing-transplants.md)
