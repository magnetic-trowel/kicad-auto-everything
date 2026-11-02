# Metaheuristics, multi-objective search and quality-diversity

Scope: SA, evolutionary/multi-objective libraries, quality-diversity (QD) precedents and a PCB QD pipeline. Not here: our SA numbers -> [solver benchmarks § E](benchmarks.md#e-simulated-annealing--cp-sat-legalizationpolish); LLM code evolution -> [LLM-evolved heuristics](llm-evolved-heuristics.md).
Keys: simulated annealing, SA, tabu, pymoo, NSGA-II, pyribs, MAP-Elites, CMA-ME, CMA-MAE, DEAP, Nevergrad, cma, QDax, SA-PCB, DSAGE, warehouse layout, ELM, QDAIF, MarioGPT, Zachtronics histograms, Pareto SA

## Simulated annealing

- Our SA (`sa_place.py`, Python + NumPy, 1 thread): HPWL + λ(t)·penalties, λ 0.5→200, 9.0–11.7k moves/s; with CP-SAT legalize/polish it beats monolithic CP-SAT on every instance (4–46% at N=30–100), loses to hierarchical CP-SAT + LNS at N=100 (503.5 vs 480.5 mm), wins at N=300 (2,278 vs 2,461 mm, ~2× wall time) and N=1000 (legal 13,774 vs 22,596 mm); single instances. Penalty SA alone leaves overlaps (8–25 at N=1000 per the note; 16–25 in committed runs). Table and setup → [benchmarks § E](benchmarks.md#e-simulated-annealing--cp-sat-legalizationpolish) [C].
- At N=1000 full-board CP-SAT legalization failed (none in 120 s); legalize per violation cluster (`legalize_clusters.py`) [C].
- Literature SA: SA-PCB, B*-tree Fast-SA, Trace (8 move types), Hier-RTLMP weights, TILOS tuned SA (320 workers × 12.5 h) beating Circuit Training, Make It Home (Metropolis–Hastings), map labeling SA, control-cabinet Pareto SA → [placement families](../placement/algorithm-families.md).
- Division of labour [C/I]: analytical (Cypress-style) or SA for global placement; CP-SAT for legalization (global ≤~300 parts, per-violation-cluster windows beyond) and constraint-heavy windows; SA/tabu with incremental cost in Rust for detailed placement; pymoo/Optuna for Pareto fronts; pyribs for diverse alternatives.
- Pareto SA for thermal vs wire length (control-cabinet precedent) gives explicit trade-off fronts [I].

## Libraries

PyPI metadata, 2026-10-20 [P].

| Package | License | Contents |
|---|---|---|
| pymoo 0.6.2 | Apache-2.0 | nsga2, nsga3, unsga3, rnsga2/3, moead, age/age2, ctaea, rvea, sms, spea2, mocmaes, gde3, nsde, mopso_cd, cmopso, dnsga2, pinsga2, kgb |
| ribs (pyribs) 0.12.0 | MIT | MAP-Elites, CMA-ME, CMA-MEGA, CMA-MAE + scalable variants; ask/tell with archive/emitters/scheduler |
| DEAP 1.4.4 | LGPL | CMA-ES, NSGA-II/III, SPEA2, MO-CMA-ES |
| Nevergrad 1.0.12 | MIT | `NGOpt`; last release 2025-04 |
| cma 4.5.0 | BSD-3 | CMA-ES |
| QDax | Apache-2.0 (JAX) | JIT-compiled QD/neuroevolution on GPU/TPU (JMLR'24) [S] |
| SA-PCB | BSD-3 | Upstream `choltz95/c-pcb-annealer`; host OpenROAD PCB-PR-App reads KiCad 5.1.2 boards |

## Quality-diversity precedents

- **Warehouse layout + multi-robot coordination** (Zhang, Fontaine, Bhatt, Nikolaidis, Li; IJCAI'23; [arXiv 2305.06436](https://arxiv.org/abs/2305.06436) [P]; [code](https://github.com/lunjohnzhang/warehouse_env_gen_public)): optimize the layout instead of the MAPF algorithm; MAP-Elites maximizes lifelong-MAPF throughput (RHCR, DPP) while diversifying measures (connected shelf components, task length); every candidate repaired by a MILP; DSAGE surrogate predicts repaired layout and simulation outcome; scaled to 200 robots; optimized layouts doubled supported robots in some cases. Closest validated analogue of "placement for routability".
- ELM (LLM as MAP-Elites mutation; OpenELM); QDAIF (ICLR'24: LM generates variations, judges quality by yes/no log-probs and diversity by natural-language trait questions; reward-hacking risk); MarioGPT (novelty search; mutation replaces a level slice with an LLM sample, a second model inpaints borders); T-DominO, ARCH-Elites, constrained MAP-Elites, FI-MAP-Elites, TileGPT; Autodesk Project Discover (~10,000 office layouts on six stakeholder metrics) [S].
- AlphaEvolve's program database = MAP-Elites + islands; FunSearch uses islands; VeoPlace: greedy-best context worst, stratified diverse context best → [LLM-evolved heuristics](llm-evolved-heuristics.md).
- No QD application to chip/PCB floorplanning found.
- Zachtronics UX: solve first, then optimize against histograms of other players' cost/cycles/area ("tall" vs "deep" solutions) → [cross-domain routing](../routing/cross-domain-routing-transplants.md) [S].

## PCB QD pipeline (warehouse port)

[I]
- Map: layout → placement; throughput → routability (completion, vias, length from PathFinder/MCTS router/Freerouting); MILP repair → legalizer (sparrow-style GLS or CP-SAT NoOverlap2D); DSAGE → CNN/GNN predicting legalized congestion map and routing success.
- Measures: board area, single- vs double-sided fraction, signal-flow straightness, thermal spread.
- Emitters: LLM ("swap the power and RF blocks", "rotate U2 to face J1") next to Gaussian/CMA emitters; QDAIF-style VLM yes/no measures ("is the analog section isolated from the switcher?") guarded by hard DRC and routability.
- MarioGPT-style region mutation: resample one block with the generator (LLM program or diffusion), inpaint borders with the legalizer.
- Present portfolios with metric histograms vs prior boards or the archive.

## Open questions

- No QD study on PCB or chip placement; the warehouse analogy is the closest precedent.
- SA+CP-SAT vs hierarchical ordering flips with N on single seeds → [benchmarks](benchmarks.md#open-questions).

## Sources

- [solver_toolbox.md § 3](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/solver_toolbox.md); [cross_domain_ideas.md § Q9, Q10](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/cross_domain_ideas.md)
