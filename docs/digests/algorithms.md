# Digest: placement and routing algorithms, engines, transplants, solvers

Executive statements only; each links to the topic doc with numbers and sources. Corrections from `verification_papers.md` are applied. Full idea list: [inventory](../ideas/inventory-algorithms.md); ranked transplants: [cross-domain](../ideas/cross-domain-transplants.md).

## Placement
- PCB placers fall into four families. Since 2025 the field has converged on VLSI-style analytical global placement adapted to PCBs, followed by an exact MILP/QP/constraint-graph legalizer. KiCad's own autoplacer is a greedy grid scan with no rotation, so use it only as a seed. → [algorithm families](../topics/placement/algorithm-families.md)
- **Cypress** is the only open PCB-aware analytical engine (Apache-2.0, reads KiCad). Its terms are two-sided density, differentiable net crossing and Gumbel orientation. On OmniLayout routability, **Chen DAC'25 (0.62) is the best academic placer and Quilter (0.84) the best tool**. → [PCB placers](../topics/placement/pcb-placers-2022-2026.md), [analytical](../topics/solvers/analytical-differentiable.md)
- Hierarchy matters most: core IC → satellite ring → modules → exact legalization. **No academic placer chooses component sides**, so side assignment is an LLM job. → [LLM-guided](../topics/placement/llm-guided-placement.md), [sides/thermal/EMC](../topics/placement/sides-thermal-emc-reuse.md)
- Frontier LMMs place with good connectivity (GPT-5.5 routability 0.90–0.95) but with bad pad legality (79.82% of outputs overlap). Keep them at the intent level. → [metrics](../topics/placement/benchmarks-and-metrics.md)
- Analog flows show the pattern to copy: a soft penalty during global placement plus an exact constraint at legalization. ALIGN's typed JSON gives a ready constraint vocabulary. → [analog](../topics/placement/analog-constraint-placement.md), [legalization](../topics/placement/legalization.md)
- End-to-end RL placers have not shown their claims on PCBs. ML helps where it orders, groups, masks or proposes regions. VeoPlace's VLM regions help as weak anchors (λ = 0.01); images are optional. → [ML/RL](../topics/placement/ml-rl-placement.md)

## Routing
- Every strong open router is a sequential A* search with rip-up and negotiated conflict pricing. PathFinder with the VPR schedule (normalized base costs) is the in-house starting point. → [families](../topics/routing/algorithm-families.md), [PathFinder](../topics/routing/pathfinder-negotiated-congestion.md)
- **Topology first.** SURF's cut-capacity test names bottlenecks (exact only for a single-layer sketch). Octilinear routing costs only ~5% more length than any-angle, so spend LLM effort on homotopy rather than angles, and persist routes as topology. → [topological](../topics/routing/topological-routing.md)
- Escape routing is exactly solvable with flow/MCF/SAT. MonoSAT proved minimal escape-layer counts (within its model) on 1755-signal FPGAs. Pin/bank swap should be a first-class LLM action. → [escape](../topics/routing/escape-routing.md)
- Reserve meander area during planning, and make meander SI rules explicit. Diff pairs: median points → centerline → PNS gateway placer. → [length/buses](../topics/routing/length-matching-and-buses.md), [diff pairs](../topics/routing/diff-pair-routing.md)
- With negotiation, net order decides which nets get the good resources; without it, order also decides completion. Give the LLM quantified pairwise conflict graphs. → [net ordering](../topics/routing/net-ordering.md), [layers/vias](../topics/routing/layer-assignment-and-vias.md)
- **Relations, not coordinates.** RAC reached 90.9% clean-pass vs 23.2% for coordinates. On OmniRouting, LLMs route ≤28% of nets vs 56% for PcbRouter. → [LLM evidence](../topics/routing/llm-routing-evidence.md)
- PCBWorld clean-pass @5 on D3-A/D3-B (99 and 10 boards): Freerouting 2.1.0 0.80/0.78, PPO 0.86/0.45, GPT-5.4 0.65/0.00. LLM step-routing costs 0.4–1.9M tokens per board. → [PCBWorld](../topics/routing/pcbworld.md)
- ML transfers best when it controls a classical router (order, cost schedules, fanout). DeepPCB's vendor scores exclude DDR, length matching and RF. → [ML/RL routing](../topics/routing/ml-rl-routing.md)
- Freerouting improved sharply in Oct 2026: on its own 1,142-fixture nightly, by its own check, 31.3% (2.4.1) → 75.2% (2.5.0) → 87.7% (2.6.0-RC3); RC4's 92.4% covers only tiers A+B. Pin v2.5.0 and re-score with KiCad DRC. → [Freerouting](../topics/routing/freerouting.md)
- KiCad PNS is a realizer, not a search engine. PCBWorld-Engine (a KiCad 9.0.8 fork) makes it scriptable and checkpointable, which enables search over waypoints. → [PNS](../topics/routing/kicad-pns-router.md)
- Score what practitioners reject: via density, parallel overlap, bottlenecks, return-path breaks. → [skepticism](../topics/routing/autorouter-skepticism.md), [benchmarks](../topics/routing/benchmarks-and-datasets.md)

## Solvers
- Monolithic CP-SAT stays feasible to ~200 parts but has competitive HPWL only to ~100. Hierarchical CP-SAT + LNS stays feasible to 1000. **Fixing orientations upstream is the key lever.** SA + CP-SAT beats monolithic at 30–100 parts and hierarchical at ≥300 (with ~2× the time); hierarchical wins at 100. Single instances. → [CP-SAT](../topics/solvers/cp-sat-milp-smt.md), [measurements](../topics/solvers/benchmarks.md)
- Use Optuna MOTPE with an LLAMBO warm start for tuning. QD portfolios follow the warehouse precedent (2× robots). LLM-evolved heuristics need restricted APIs and generalization tests. → [tuning](../topics/solvers/bayesian-tuning.md), [QD](../topics/solvers/metaheuristics-and-qd.md), [evolution](../topics/solvers/llm-evolved-heuristics.md)
- Geometry: Shapely/pyclipper/jagua-rs; avoid `triangle`. Put the hot loops in Rust. Use a five-level fidelity ladder ending at a pinned Freerouting plus KiCad DRC. → [geometry](../topics/solvers/geometry-libraries.md), [performance](../topics/solvers/performance-and-multifidelity.md)

## Cross-domain
- Top transplants: PCB-PSDL imperative placement with LLM-free repair (indoor scenes: 94.3% preferred over Holodeck), self-consistent relations, VLM regions, a VLM pros/cons judge, a sparrow GLS legalizer, HOLA/IPSep layouts, an MCTS polygon router. → [scene](../topics/placement/scene-layout-transplants.md), [packing/graph](../topics/placement/packing-and-graph-drawing-transplants.md), [generative](../topics/placement/generative-placement.md), [routing transplants](../topics/routing/cross-domain-routing-transplants.md)

## Recommended stack
- Under GPL-3.0-or-later, GPL engines may run in-process; Gurobi, OptiMathSAT, Triangle and GPL-2.0-only code stay out. The LLM supplies intent. Pipeline: CP-SAT clusters → analytical global placement → CP-SAT legalization → Rust SA/LNS → exact escape → topology tier → PNS/Freerouting/PathFinder → DRC + SI. → [stack](../topics/solvers/recommended-stack.md)
- First experiments: (1) a relational planner vs Freerouting/DeepPCB on PCBWorld D3 with SI constraints; (2) a topology plan + cut check vs the router alone; (3) VLM regions vs a random-region control.
