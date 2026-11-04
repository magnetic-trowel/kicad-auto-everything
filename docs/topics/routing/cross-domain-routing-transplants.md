# Cross-domain routing transplants (MAPF, MCTS, puzzles/SAT, photonics, harness, packages)

Scope: routing methods from MAPF, game search, puzzles/SAT and neighbouring physical-design domains, and how an LLM steers them. Not here: MAPF-LNS2, FPGA/VLSI convergence and routability math -> [dense-region math](routing-cross-domain-and-math.md).
Keys: MAPF, CBS, MC-CBS, UGPCB-CBS, PIBT, LaCAM*, lifelong MAPF, libMultiRobotPlanning, LLM meta-controller, MCTS, PUCT prior, LLM-MCTS, Numberlink, ZDD, Factorio-SAT, Zachtronics histograms, PACOR, DME, photonics curvy A*, Apollo, wire harness bundling, bump assignment, RDL, tensor field, homotopy hints

**Results**
1. LLMs fail at direct MAPF (complete failure on a 32×32 maze with only 2 agents): the LLM is a meta-controller (priorities, conflict choices, homotopy hints, per-class costs) for CBS/PIBT/LaCAM/PathFinder, never the path planner.
2. CBS has been applied to PCB routing on Delaunay meshes (UGPCB-CBS, 2025; numbers inaccessible); fast MAPF (PIBT ~5 s for 1,000 agents; LaCAM* 99% of instances ≤1,000 agents in 10 s) suits dense fan-out regions.
3. LLM as PUCT prior over the DATE'23 polygon MCTS router is the most concrete LLM+search hook.
4. Numberlink/Factorio-SAT pattern: human/LLM picks topology, SAT realizes or refutes, for small windows.

## MAPF and robotics

[S unless noted]
| Method | Fact |
|---|---|
| CBS (Sharon AAAI'12) | Two-level conflict-tree search; optimal |
| MC-CBS (Li AAAI'19) | Geometric (non-point) agents; multiple constraints per branch; up to 1000× faster than CBS |
| **UGPCB-CBS** (Cao, Cai, Xu; J. Supercomput. 81(9) art. 1063, June 2025) | Delaunay mesh + artificial-potential-field paths + CBS for PCB routing; abstract and numbers not accessible (VP) |
| PIBT (Okumura AIJ'22) | ~5 s for 1,000 agents, avg sub-optimality <1.5; lifelong; incomplete one-shot |
| LaCAM* (2023) | Anytime, eventually optimal; 99% of instances ≤1,000 agents within 10 s |
| Lifelong-MAPF follow-ups | Fast solvers push agents into central bottlenecks; add guidance |
| **LLM solves MAPF directly** (Chen, Koenig, Dilkina 2024, [arXiv 2401.03630](https://arxiv.org/abs/2401.03630) [P]) | Works on empty 8×8; "completely fail[s] on MAZE-32-32-2 even with only 2 agents"; weak constraint/duplicate reasoning, context limits, poor obstacle understanding even with images |
| PathFinder | Underpins production FPGA routers → [PathFinder](pathfinder-negotiated-congestion.md) |
| RRT-PCB (LG AI) | Grid route then continuous RRT refinement |
| Warehouse layout for MAPF throughput | MAP-Elites + MILP repair + surrogate; up to 2× robots → [QD](../solvers/metaheuristics-and-qd.md) |
| libMultiRobotPlanning (MIT, C++14) | A*, focal A*, SIPP, CBS, ECBS; no Python bindings ([README](https://raw.githubusercontent.com/whoenig/libMultiRobotPlanning/main/README.md) [P]) |

LLM as MAPF/negotiation meta-controller [I]: (1) net priorities/ordering for prioritized planning or PIBT-style inheritance; (2) choose the conflict to branch on and the net to yield at stalled CBS nodes; (3) homotopy hints ("USB pair passes north of U4"); (4) per-net-class cost multipliers in PathFinder. PIBT/LaCAM-style fast first feasible routing for hundreds of short fan-out escapes, improved by CBS or rip-up, with spreading guidance against central congestion [I].

## Game search

[S unless noted]
- DATE'23 polygon MCTS PCB router and He & Bao MCTS+DNN → [ML/RL routing](ml-rl-routing.md) [P].
- LLM as MCTS prior: LLM-MCTS (NeurIPS'23, world model + policy heuristic), LLM-First Search (value + PUCT prior), Scattered Forest Search (PUCT with transformer prior for code).
- Patent US 12019968: NN-guided sequential Monte Carlo for connection order, scored by length, vias, congestion, turns.

## Puzzles and SAT

[S]
- Numberlink in EDA: Tanaka–Takahashi (DA Symposium 2014) island-in-cavity routing with CHORD-LAST order and area division; faster topological solver (IEICE VLD 2015); ZDD enumeration of all Numberlink/Slitherlink solutions (Algorithms 2012); SAT encodings (Permanganate; Leiden thesis with cycle prevention); zig-zag Numberlink NP-complete.
- Factorio-SAT: tiles as booleans (direction, underground, splitter side, colour), no-crossing and colour clauses; returns a layout or proves none exists for a hand-chosen topology; verifier checks 64×64 balancers in <1 s. Factorio frameworks: SMT (Z3/CVC5/Yices) + A* + MAPF for belts, SA for assembler placement; "logistic belt optimization" with parallel SA vs evolutionary RL. Stack shape "SAT/SMT for local exact layout + MAPF for routing + annealing for placement" [I].
- Zachtronics: solving needs only correct output; optimization afterward against histograms of other players' cost, cycles and area; aesthetics unscored. kae UX: after each run show histograms of area, vias, length, worst decap distance, crossings vs prior boards or a QD archive [I].
- Use SAT/CP-SAT/ZDD for small escape/fan-out windows with vias as bridges; ZDD can enumerate all solutions for the LLM to choose between [I].

## Other physical-design domains

[S]
| Domain | Methods | kae subroutine [I] |
|---|---|---|
| Microfluidics | PACOR (DME Steiner + min-cost-flow escape + bounded-length detours; 100% completion); McDaniel negotiated escape on a biochip PCB; RABER control-port sharing | DME + MCF length matching for DDR-style buses |
| Photonics | APR curvy A* + adaptive crossing insertion (~14% lower insertion loss); Apollo bending-aware wirelength GPU placement (routability 94.79% vs DREAMPlace 50.85%, Cypress 51.38%); LiDAR 2.0 | Bend/via-aware costs for RF/high-speed |
| Wire harness | Chalmers/Volvo length vs bundling vs restricted zones Pareto, near-optimal in seconds–minutes; TU Delft road-map + refinement | Bundling rewards for bus corridors |
| Chip-package | Min-cost max-flow RDL routing (100% completion); routability-driven bump assignment inspired by board escape; chiplet RDL co-design; any-angle die-to-die routing (ISPD'26) | Datasheet pin-mux knowledge for bump/pin-swap co-optimization |
| Urban | Tensor-field street modeling (SIGGRAPH'08) | Field-derived preferred directions |
| Graph drawing/cartography | libavoid orthogonal connectors, metro-map MIP → [packing/graph drawing](../placement/packing-and-graph-drawing-transplants.md) | — |
| Homotopy interfaces | JITX topo-routes, TopoR → [topological](topological-routing.md) | Homotopy-first interfaces are the most LLM-compatible; verify topologically before geometry |
| Quantum placement | Qplacer repulsion | Aggressor/victim separation |

## Open questions

- UGPCB-CBS numbers unread; no VLSI detailed-routing paper with an explicit MAPF formulation beyond a 2021 MARL work; no academic study of Zachtronics strategies.

## Sources

- [cross_domain_ideas.md § Q4, Q5, Q8](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/cross_domain_ideas.md); [verification_papers.md § 1 row 41](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_papers.md); [solver_toolbox.md § 5](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/solver_toolbox.md)
- Related: [cross-domain idea inventory](../../ideas/cross-domain-transplants.md)
