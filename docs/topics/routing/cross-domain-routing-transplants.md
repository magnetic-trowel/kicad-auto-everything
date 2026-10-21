# Cross-domain routing transplants (MAPF, MCTS, puzzles/SAT, photonics, harness, packages)

**TL;DR**
- **LLMs fail at direct MAPF** (complete failure on a 32×32 maze with only 2 agents) — so the LLM should be a **meta-controller** (priorities, conflict choices, homotopy hints, per-class costs) for CBS/PIBT/LaCAM/PathFinder, never the path planner.
- **CBS has been applied to PCB routing on Delaunay meshes** (UGPCB-CBS, J. Supercomput. 2025; numbers inaccessible); fast MAPF (PIBT ~5 s for 1,000 agents; LaCAM* 99% of instances ≤1,000 agents in 10 s) suits dense fan-out regions.
- **LLM as PUCT prior** over the DATE'23 polygon MCTS router is the most concrete LLM+search hook.
- Numberlink/Factorio-SAT show "human/LLM picks topology, SAT realizes or refutes" for small windows; Zachtronics-style metric histograms are a UX transplant.
- Neighbouring physical-design domains contribute subroutines: PACOR length-matched escape, curvy/bend-aware A* (photonics), harness bundling Pareto, package bump assignment, tensor-field direction fields.

## Key facts

**MAPF / robotics** [S unless noted]
| Method | Fact |
|---|---|
| CBS (Sharon AAAI'12) | Two-level conflict-tree search; optimal |
| MC-CBS (Li AAAI'19) | Geometric (non-point) agents; multiple constraints per branch; up to 1000× faster than CBS |
| **UGPCB-CBS** (Cao, Cai, Xu; J. Supercomput. 81(9) art. 1063, June 2025) | Delaunay mesh + artificial-potential-field paths + CBS for PCB routing; abstract and numbers not accessible (VP) |
| PIBT (Okumura AIJ'22) | ~5 s for 1,000 agents, avg sub-optimality <1.5; lifelong; incomplete one-shot |
| LaCAM* (2023) | Anytime, eventually optimal; 99% of instances ≤1,000 agents within 10 s |
| Lifelong-MAPF follow-ups | Fast solvers push agents into central bottlenecks; add guidance |
| **LLM solves MAPF directly** (Chen, Koenig, Dilkina 2024, [arXiv 2401.03630](https://arxiv.org/abs/2401.03630) [P]) | Works on empty 8×8; "completely fail[s] on MAZE-32-32-2 even with only 2 agents"; weak constraint/duplicate reasoning, context limits, poor obstacle understanding even with images |
| PathFinder | Underpins production FPGA routers ([PathFinder](pathfinder-negotiated-congestion.md)) |
| RRT-PCB (LG AI) | Grid route then continuous RRT refinement |
| Warehouse layout for MAPF throughput | MAP-Elites + MILP repair + surrogate; up to 2× robots ([QD](../solvers/metaheuristics-and-qd.md)) |
| libMultiRobotPlanning (MIT, C++14) | A*, focal A*, SIPP, CBS, ECBS; no Python bindings ([README](https://raw.githubusercontent.com/whoenig/libMultiRobotPlanning/main/README.md) [P]) |

**Game search** [S unless noted]
- DATE'23 polygon MCTS PCB router and He & Bao MCTS+DNN ([ML/RL routing](ml-rl-routing.md)) [P].
- LLM as MCTS prior: LLM-MCTS (NeurIPS'23, world model + policy heuristic), LLM-First Search (value + PUCT prior), Scattered Forest Search (PUCT with transformer prior for code).
- Patent US 12019968: NN-guided sequential Monte Carlo for connection order, scored by length, vias, congestion, turns.

**Puzzles / SAT** [S]
- Numberlink in EDA: Tanaka–Takahashi (DA Symposium 2014) as island-in-cavity routing with CHORD-LAST order and area division; faster topological solver (IEICE VLD 2015); ZDD enumeration of all Numberlink/Slitherlink solutions (Algorithms 2012); SAT encodings (Permanganate; Leiden thesis with cycle prevention); zig-zag Numberlink NP-complete.
- **Factorio-SAT**: tiles as booleans (direction, underground, splitter side, colour), no-crossing and colour clauses; returns a layout or proves none exists for a **hand-chosen topology**; verifier checks 64×64 balancers in <1 s. Factorio frameworks combine SMT (Z3/CVC5/Yices) + A* + MAPF for belts and SA for assembler placement; "logistic belt optimization" with parallel SA vs evolutionary RL.
- **Zachtronics**: solving needs only correct output; optimization happens afterward against **histograms of other players' cost, cycles and area**; aesthetics unscored.

**Other physical-design domains** [S]
- Microfluidics: **PACOR** (DME Steiner + min-cost-flow escape + bounded-length detours; 100% completion); McDaniel negotiated escape on a biochip PCB; RABER control-port sharing.
- Photonics: APR curvy A* + adaptive crossing insertion (~14% lower insertion loss); Apollo bending-aware wirelength GPU placement (routability 94.79% vs DREAMPlace 50.85%, Cypress 51.38%); LiDAR 2.0.
- Wire harness: Chalmers/Volvo length vs **bundling** vs restricted zones Pareto, near-optimal in seconds–minutes; TU Delft road-map + refinement.
- Chip-package: min-cost max-flow RDL routing (100% completion); routability-driven bump assignment inspired by board escape; chiplet RDL co-design; any-angle die-to-die routing (ISPD'26).
- Urban: tensor-field street modeling (SIGGRAPH'08) for direction fields.
- Graph drawing/cartography for routes: libavoid orthogonal connectors, metro-map MIP ([packing/graph drawing](../placement/packing-and-graph-drawing-transplants.md)).
- Homotopy routing interfaces: JITX topo-routes, TopoR ([topological](topological-routing.md)).

## Recommendations for our system
- **LLM as MAPF/negotiation meta-controller** [I]: (1) net priorities/ordering for prioritized planning or PIBT-style inheritance; (2) choose the conflict to branch on and the net to yield at stalled CBS nodes; (3) homotopy hints ("USB pair passes north of U4"); (4) per-net-class cost multipliers in PathFinder.
- PIBT/LaCAM-style fast first feasible routing for hundreds of short fan-out escapes, improved by CBS or rip-up; add spreading guidance against central congestion [I].
- Homotopy-first interfaces are the most LLM-compatible; verify topologically before geometry [I].
- SAT/CP-SAT/ZDD for small escape/fan-out windows with vias as bridges; ZDD can enumerate all solutions for the LLM to choose between [I].
- "SAT/SMT for local exact layout + MAPF for routing + annealing for placement" is the Factorio-proven stack shape [I].
- UX: after each run, show histograms of area, vias, length, worst decap distance, crossings vs prior boards or a QD archive [I].
- Subroutines: DME + MCF length matching (PACOR) for DDR-style buses; bend/via-aware costs (photonics) for RF/high-speed; bundling rewards for bus corridors; datasheet pin-mux knowledge for bump/pin-swap co-optimization; field-derived preferred directions; Qplacer-style repulsion for aggressor/victim separation [I].

## Conflicts and open questions
- UGPCB-CBS numbers unread; no VLSI detailed-routing paper with explicit MAPF formulation beyond a 2021 MARL work; no academic study of Zachtronics strategies.

## Sources
- research notes: [cross_domain_ideas.md § Q4, Q5, Q8](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/cross_domain_ideas.md); [verification_papers.md § 1 row 41](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_papers.md); [solver_toolbox.md § 5](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/solver_toolbox.md)

See also: [ml-rl-routing](ml-rl-routing.md) · [pathfinder-negotiated-congestion](pathfinder-negotiated-congestion.md) · [../../ideas/cross-domain-transplants](../../ideas/cross-domain-transplants.md)
