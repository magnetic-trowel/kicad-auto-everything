# Recommended engine stack for LLM-driven KiCad placement and routing

**TL;DR**
- **Division of responsibility**: the LLM owns intent (hierarchy, sides, relations/constraints with ordinal magnitudes, priorities, per-class engine choice, topology hints, pin-swap proposals); solvers own geometry; KiCad DRC + domain checkers own legality.
- **Placement**: clusters/sides from LLM + netlist → per-cluster CP-SAT soft macros → Cypress-style differentiable global placement (or CP-SAT soft-macro floorplan) → CP-SAT min-displacement legalization → Rust SA + windowed CP-SAT LNS → multi-tier metrics + conflict list back to the LLM.
- **Routing**: escape by exact solvers → diff pairs/buses by centerline A* + PNS DP placer with reserved meander area → bulk by Freerouting (pinned v2.5.0 until 2.6.0 is released; `-mt 1` in final runs) and/or in-house Rust A*/PathFinder → PNS shove repair/smoothing (+ search over PNS) → KiCad tuning → KiCad DRC + SI checks.
- **Tuning and improvement**: Optuna MOTPE (+ LLAMBO warm start); pyribs portfolios; offline LLM evolution of orders/costs/objectives through restricted APIs.
- Code is **GPL-3.0-or-later**: GPL engines (Freerouting, KiCad PNS / PCBWorld-Engine, CGAL) may be integrated in-process; exclude Gurobi, OptiMathSAT, Triangle, GPL-2.0-only code; AGPL reference-only.

## Key facts

**Evidence behind the stack** [P/M]
- Decomposition is mandatory: NS-Place's vanilla MILP found no feasible placement in 4 h on 9–10 of 14 boards; HiePlace's ILP baseline gave no result at 308–404 parts; our monolithic CP-SAT (feasible to ~200 parts) found nothing at 300/1000 parts in 300 s; hierarchical CP-SAT + LNS stays feasible at 100–1000 ([benchmarks](benchmarks.md)).
- Cypress's differentiable recipe ran on boards of up to 6,628 parts, of which at most 2,152 were movable, with MOTPE + Freerouting evaluation ([analytical](analytical-differentiable.md)).
- Freerouting has the best clean-pass on medium real boards in PCBWorld (D3-B, 10 boards); KRT is fastest; LLM agents are not routers ([PCBWorld](../routing/pcbworld.md)).
- Relations beat coordinates (RAC 90.9% vs 23.2%) ([LLM routing evidence](../routing/llm-routing-evidence.md)); hierarchy matters most (ModuPlace) ([LLM-guided placement](../placement/llm-guided-placement.md)).
- pyclipr lacks Linux wheels; pyclipper and jagua-rs are viable ([geometry](geometry-libraries.md)).

**Subproblem → tool mapping** (licenses re-assessed for GPL-3.0-or-later)
| Subproblem | Primary tool | Alternatives / notes | License | Fit |
|---|---|---|---|---|
| Board I/O, writing placements/tracks | kicad-python IPC (`create_items`/commit, `get_pad_shapes_as_polygons`); KiCad 11 DSN/SES RPCs | pcbnew SWIG; `.kicad_pcb` parsing | MIT (KiCad GPL-3+) | OK |
| Clustering, sides, constraints | LLM + netlist graph (rustworkx / NetworkX) + rules | Cypress assumes pre-assigned sides | Apache-2.0 / BSD-3 | OK |
| Cluster placement (≤50 parts, hard decap/keep-out/alignment) | CP-SAT formulation A, 0.5 mm grid, "opt2", ≥2 aspect variants ([CP-SAT](cp-sat-milp-smt.md)) | HiePlace-style MP with HiGHS/SCIP (not Gurobi) | Apache-2.0 | OK |
| Global placement 100–1000 parts | Cypress-style JAX/PyTorch loss (Gumbel orientation, two-sided density, net crossing, decap/keep-out/thermal/loop penalties) or CP-SAT soft-macro floorplan | Cypress itself (GPU); DREAMPlace (BSD-3, old toolchain); SA | Apache-2.0 | OK |
| Legalization | CP-SAT min-displacement with hard constraints: full board (`hier_place.py::legalize`) up to ~300 parts, per violation cluster (`legalize_clusters.py`) beyond, since the full-board model found no solution at N=1000 ([benchmarks](benchmarks.md), [legalization](../placement/legalization.md)) | Tetris + Abacus; sparrow GLS on jagua-rs; greedy (Rust) | Apache / MIT / MPL-2.0 | OK |
| Orientation/side cleanup | DEE + A*/ILP (transplant) | CP-SAT | own | OK |
| Detailed placement | SA (Rust, incremental HPWL/RUDY) + windowed CP-SAT LNS | tabu | own | OK |
| Weight tuning / Pareto | Optuna MOTPE / NSGA-II (+ OptunaHub LLAMBO first ~10 trials) ([tuning](bayesian-tuning.md)) | SMAC, BoTorch, pymoo | MIT / BSD / Apache | OK |
| Diverse alternatives | pyribs CMA-MAE / MAP-Elites over weights or layouts ([QD](metaheuristics-and-qd.md)) | pymoo fronts, QDax | MIT / Apache | OK |
| Algorithm self-improvement | ReEvo/EoH/AlphaEvolve/CoEvoP&R-style evolution against a sandboxed benchmark ([LLM-evolved](llm-evolved-heuristics.md)) | LLM4AD, OpenEvolve | own | OK |
| Escape / fan-out | Network-flow MILP (HiGHS/SCIP) or CP-SAT; MonoSAT for multi-layer ([escape](../routing/escape-routing.md)) | SAT ordered escape; CBS/ECBS (libMultiRobotPlanning) | MIT / Apache; MonoSAT MIT **only with `-DGPL=OFF`** (default links GPLv2 code — avoid unless it is "or later") | OK with flag |
| Topology tier | CDT (PythonCDT) + SURF cut check ([topological](../routing/topological-routing.md)) | gEDA toporouter code (GPLv2+) | MPL/BSD/Apache; GPLv2+ | OK |
| Diff pairs / buses | KRT-style pose-space centerline A* + KiCad PNS DP placer ([diff pairs](../routing/diff-pair-routing.md)) | PcbRouter median points | MIT / GPL-3 / BSD-3 | OK |
| Bulk routing | In-house Rust A*/PathFinder (VPR schedule, normalized base costs) ([PathFinder](../routing/pathfinder-negotiated-congestion.md)) + Freerouting v2.5.0 headless, pinned until 2.6.0 is released ([freerouting](../routing/freerouting.md)) | KRT (MIT, reuse), tscircuit (MIT, Node), DeepPCB cloud (proprietary service, Apache-2.0 plugin; non-SI nets only) | own / MIT / GPL-3 | OK |
| Realization, repair, smoothing | KiCad PNS via PCBWorld-Engine-style bindings (the engine is pinned to KiCad 9.0.8), checkpoint/restore search ([PNS](../routing/kicad-pns-router.md)) | KiCad `qa/tools/pns` | GPL-3 | OK in-process |
| Length tuning | Reserved-area planning + PNS meander engine ([length matching](../routing/length-matching-and-buses.md)) | KRT trombones | GPL-3 / MIT | OK |
| Geometry | Shapely 2 (batch), pyclipper (offset, Minkowski), grid hash/NumPy inner loop, jagua-rs (Rust exact) | rtree, PythonCDT, CGAL (GPLv3+) | BSD / MIT / MPL / GPL | OK; **avoid `triangle`** |
| Verification | `kicad-cli pcb drc --format json --schematic-parity --severity-all --refill-zones --exit-code-violations` (add `--all-track-errors` in repair loops) + PCBWorld clean-pass metric + SI/practitioner checks ([skepticism](../routing/autorouter-skepticism.md)) | Freerouting `-drc` JSON | GPL | OK |

**Excluded / restricted**: Gurobi (proprietary — HiePlace and Holodeck used it; substitute CP-SAT/HiGHS/SCIP); OptiMathSAT (research-only); Shewchuk Triangle (non-commercial); GPL-2.0-only components; AGPL reference-only; HiePlace text CC BY-NC-ND (reimplement from description, no code exists); DeepPCB cloud requires uploading boards (terms unreviewed). Apache-2.0 → GPLv3 compatibility per the ASF; MPL-2.0 combinable per Mozilla FAQ; LGPL fine [P/I].

**End-to-end loop** [I]
1. LLM builds hierarchy (sheets → netlist clusters → named modules), assigns sides, writes a relation bundle (and optionally a PCB-PSDL placement program) using skill-library macros; optional VLM region proposals as weak anchors ([scene transplants](../placement/scene-layout-transplants.md)).
2. Self-consistency and contradiction checks (ASP/clingo or pattern rules); compile relations twice (penalty + exact).
3. Global placement → legalization → detailed placement; silkscreen labeling by SA/MaxSAT.
4. Evaluation ladder L0–L4 ([multi-fidelity](performance-and-multifidelity.md)); structured text conflict list with admissible relaxations → LLM revises commitments, not geometry.
5. Routing tiers: escape solver (may return "impossible" → stackup/pin-swap ECO) → topology sketch + cut check → pairs/buses with reserved meander area → bulk router with LLM-set priorities/costs → PNS repair/search → tuning → DRC + SI.
6. Rank candidates (VLM pros/cons judge + hard metrics); present a QD portfolio with metric histograms; persist relations as re-solvable intent for ECOs.
7. Offline: tune knobs (MOTPE), evolve heuristics (restricted API + cascade), learn negotiation schedules from logs; long-horizon diffusion prior.

## Recommendations for our system
- Build in this order: I/O + metrics/DRC harness → relation API + CP-SAT legalizer → analytical global placer → Freerouting integration → topology tier + escape solvers → PNS realization/search → tuning/QD → evolution [I].
- First ablations: (a) LLM relational planner + classical realizers vs Freerouting/DeepPCB on PCBWorld D3 with SI constraints; (b) LLM topology plan + cut check vs router alone; (c) VLM regions vs random-region control [I].

## Conflicts and open questions
- No end-to-end open implementation of this stack exists; pieces are validated separately; real-board validation of the placement half (PCBWorld D3, Cypress small suite) is the next experiment; Cypress's KiCad files need synthesized outlines and rebuilt net tables first ([open board sources](../data/open-board-sources.md)).
- PCBWorld-Engine maintenance cost across KiCad 10/11 unknown; MonoSAT's GPL component version not confirmed.

## Sources
- research notes: [solver_toolbox.md § 9](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/solver_toolbox.md); [placement_algorithms.md § Q8](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/placement_algorithms.md); [routing_algorithms.md § Implications](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/routing_algorithms.md); [routing_classics_supplement.md § Implications](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/routing_classics_supplement.md); [cross_domain_ideas.md § Q11](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/cross_domain_ideas.md); [verification_papers.md § 3](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_papers.md)

See also: [../../digests/algorithms](../../digests/algorithms.md) · [../../ideas/inventory-algorithms](../../ideas/inventory-algorithms.md) · [benchmarks](benchmarks.md)
