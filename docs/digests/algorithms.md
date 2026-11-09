# Digest: placement and routing algorithms, engines, transplants, solvers

Scope: survey conclusions on placement and routing algorithms, PCB placers and routers, ML/RL, solvers, cross-domain transplants. Not here: KiCad and tool landscape -> [ecosystem](ecosystem.md); LLM interfaces -> [llm-data-ux](llm-data-ux.md); kae's placer and router -> [physics-first](physics-first.md). Ideas: [inventory](../ideas/inventory-algorithms.md), [ranked transplants](../ideas/cross-domain-transplants.md).
Keys: placement families, analytical placement, legalization, Cypress, Chen DAC'25, OmniLayout routability, side assignment, PathFinder, negotiated congestion, topological routing, SURF cut test, escape routing, MonoSAT, net ordering, RAC, OmniRouting, PCBWorld CP@5, Freerouting nightly, PNS realizer, CP-SAT scaling, SA + CP-SAT, MOTPE, LLAMBO, fidelity ladder, PCB-PSDL

## Placement
- Four placer families; since 2025 the field converged on VLSI-style analytical placement plus MILP/QP/constraint-graph legalization; KiCad's greedy autoplacer is only a fallback seed. → [families](../topics/placement/algorithm-families.md#families-overview)
- Cypress (Apache-2.0, reads KiCad) is the only open PCB-aware analytical engine: two-sided density, differentiable net crossing, Gumbel-Softmax orientation. → [placers](../topics/placement/pcb-placers-2022-2026.md#methods-and-results), [Cypress](../topics/solvers/analytical-differentiable.md#cypress)
- OmniLayout routability bars: Chen DAC'25 0.62 (best academic), Quilter 0.84 (best tool). → [metrics](../topics/placement/benchmarks-and-metrics.md#use-in-kae)
- Hierarchy matters most (core IC → satellite ring → modules → exact legalization). → [LLM-guided](../topics/placement/llm-guided-placement.md#methods-and-results)
- No academic placer optimizes component sides, so side assignment is an LLM decision [I]. → [sides](../topics/placement/sides-thermal-emc-reuse.md#methods-and-results)
- Frontier LMMs place with good connectivity (GPT-5.5 routability 0.90–0.95) but 79.82% of outputs have a pad overlap: keep them at the intent level. → [metrics](../topics/placement/benchmarks-and-metrics.md#methods-and-results)
- Analog pattern to copy: soft penalty in global placement, exact constraint at legalization; ALIGN's typed JSON is a ready vocabulary. → [analog](../topics/placement/analog-constraint-placement.md#use-in-kae), [legalization](../topics/placement/legalization.md#use-in-kae)
- End-to-end RL placers are unproven on PCBs; ML helps where it orders, groups, masks or proposes regions; VeoPlace's weak VLM anchors win (λ_A = 0.01). → [ML/RL](../topics/placement/ml-rl-placement.md#use-in-kae), [VeoPlace](../topics/placement/llm-guided-placement.md#methods-and-results)

## Routing
- Every production-grade open router is sequential path search + rip-up/reroute + optimizer; start in-house from PathFinder with the VPR schedule after normalizing base costs. → [families](../topics/routing/algorithm-families.md), [PathFinder](../topics/routing/pathfinder-negotiated-congestion.md#pathfinder-cost-and-vpr-defaults)
- Topology first: SURF's cut test names bottlenecks, exact only for a single-layer sketch. → [SURF](../topics/routing/topological-routing.md#surf)
- Octilinear costs ~5% more length than any-angle for a fixed topology: spend LLM effort on homotopy, persist routes as topology. → [topology tier](../topics/routing/topological-routing.md#topology-tier-for-kae-tier-15)
- Escape is exactly solvable (flow/MCF/SAT); MonoSAT's minimal layer counts hold only within its discretized model; pin/bank swap is a first-class LLM action. → [MonoSAT](../topics/routing/escape-routing.md#monosat-multi-layer-escape), [escape](../topics/routing/escape-routing.md#escape-in-kae)
- Reserve meander area while planning, with explicit meander rules; diff pairs: median points → centerline → PNS gateway placer. → [length](../topics/routing/length-matching-and-buses.md#length-matching-in-kae), [pairs](../topics/routing/diff-pair-routing.md#diff-pair-pipeline-for-kae)
- With negotiation, net order decides who gets good resources; in sequential routing it also decides completion. → [ordering](../topics/routing/net-ordering.md#order-as-a-lever)
- Relations, not coordinates: RAC relation bundles 90.9% clean-pass vs 23.2%; OmniRouting best LMM 27.98% of nets vs PcbRouter 56.20%. → [RAC](../topics/routing/llm-routing-evidence.md#rac-relational-agent-contract), [OmniRouting](../topics/routing/llm-routing-evidence.md#omnirouting)
- PCBWorld CP@5, D3-A/D3-B (99/10 boards): Freerouting 2.1.0 0.80/0.78, PPO 0.86/0.45, GPT-5.4 0.65/0.00 at ~425k–1.92M tokens per episode. → [results](../topics/routing/pcbworld.md#results-table-21-5), [agents](../topics/routing/pcbworld.md#llm-agents)
- ML transfers best as learned control of a classical router; DeepPCB's vendor scores exclude DDR, length matching, impedance, RF. → [transfer](../topics/routing/ml-rl-routing.md#transferability-ranking)
- Freerouting's self-reported nightly clean rate: 31.3% (2.4.1) → 75.2% (2.5.0) → 87.7% (2.6.0-RC3), partly a DRC-measurement fix; pin v2.5.0, re-score with KiCad DRC. → [nightly](../topics/routing/freerouting.md#nightly-benchmark), [use](../topics/routing/freerouting.md#use-in-kae)
- PNS is a local realizer, not a searcher; PCBWorld-Engine (KiCad 9.0.8) adds checkpoint/restore, enabling search over waypoints. → [PNS](../topics/routing/kicad-pns-router.md#pns-in-kae)
- Score what practitioners reject: via density, adjacent-layer overlap, bottlenecks, return-path breaks. → [metrics](../topics/routing/autorouter-skepticism.md#practitioner-metrics-to-score)

## Solvers
- Monolithic CP-SAT is feasible to ~200 parts, HPWL-competitive to ~100; hierarchical CP-SAT + LNS to 1000; free rotation drives difficulty, so fix orientations upstream. → [CP-SAT](../topics/solvers/cp-sat-milp-smt.md), [ablation](../topics/solvers/benchmarks.md#d-ablation-what-makes-n--300-hard)
- SA + CP-SAT legalization beats monolithic at N=30–100, loses to hierarchical at 100, wins at 300 (~2× time) and 1000; single instances. → [SA runs](../topics/solvers/benchmarks.md#e-simulated-annealing--cp-sat-legalizationpolish)
- Tune with Optuna MOTPE, LLAMBO for the first ~10 trials; QD portfolios follow the warehouse precedent. → [tuning](../topics/solvers/bayesian-tuning.md#tuning-recipe), [QD](../topics/solvers/metaheuristics-and-qd.md#pcb-qd-pipeline-warehouse-port)
- LLM-evolved heuristics need restricted, gradient-checked APIs and generalization tests (EvoPlace generalized 0.5–2.9%). → [evolution](../topics/solvers/llm-evolved-heuristics.md#offline-evolution-loop-for-kae)
- Geometry: Shapely/pyclipper/jagua-rs, never `triangle`; hot loops in Rust; L0–L4 fidelity ladder ends at Freerouting + `kicad-cli` DRC. → [geometry](../topics/solvers/geometry-libraries.md#library-choice-per-task), [ladder](../topics/solvers/performance-and-multifidelity.md#multi-fidelity-evaluation-ladder)

## Cross-domain
- Top transplant: PCB-PSDL imperative placement with LLM-free repair; also a VLM pros/cons judge, sparrow legalizer, HOLA/IPSep criteria, LLM PUCT prior over an MCTS router. → [scene](../topics/placement/scene-layout-transplants.md#use-in-kae), [packing](../topics/placement/packing-and-graph-drawing-transplants.md#use-in-kae), [routing](../topics/routing/cross-domain-routing-transplants.md#game-search)

## Recommended stack
- LLM owns intent, solvers geometry, DRC + checkers legality; Gurobi, OptiMathSAT, Triangle, GPL-2.0-only stay out. → [division](../topics/solvers/recommended-stack.md#division-of-responsibility), [excluded](../topics/solvers/recommended-stack.md#excluded-and-restricted-components)
- First ablations: relational planner vs Freerouting/DeepPCB on D3 with SI; topology plan + cut check vs router; VLM regions vs random regions. → [build order](../topics/solvers/recommended-stack.md#build-order-and-first-ablations)
- Our own results and dead ends. → [routing](../research/routing/README.md#paths), [placement](../research/placement/README.md), [joint](../research/joint/README.md)
