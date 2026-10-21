# Metaheuristics, multi-objective search and quality-diversity

**TL;DR**
- **SA with incremental cost is the strongest simple HPWL optimizer; pair it with a CP-SAT legalizer**: single-threaded Python SA + CP-SAT legalize/polish beat monolithic CP-SAT on every instance (4–46% at N=30–100), beat hierarchical CP-SAT at N=300 (2,278 vs 2,461 mm) and at N=1000 (legal 13,774 vs 22,596 mm) — penalty SA alone leaves residual overlaps (8–25 at N=1000).
- Multi-objective and diversity libraries are mature and permissive: pymoo (Apache-2.0), pyribs (MIT), cma (BSD-3), Nevergrad (MIT), Optuna (MIT); DEAP is LGPL.
- **Quality-diversity has a strong layout precedent**: warehouse layouts optimized for multi-robot throughput with MAP-Elites + MILP repair + a surrogate supported up to 2× more robots — directly analogous to "placement for routability".
- LLM-native QD (ELM mutations, QDAIF judges, MarioGPT inpainting) makes portfolios of diverse, legal, routable placements practical; show them with Zachtronics-style histograms.

## Key facts

**Simulated annealing**
- Our SA (`sa_place.py`, pure Python + NumPy, single thread; cost = HPWL + λ(t)·(overlap + keep-out + out-of-board area + 3·decap excess), λ 0.5→200, geometric cooling, moves shift/rotate/swap): 9.0–11.7k moves/s for N=30–1000 ([benchmarks](benchmarks.md) § E [M]).

| N (0.5 mm, seed 0) | SA alone | + CP-SAT legalize / LNS polish | Hierarchical CP-SAT + LNS | Monolithic CP-SAT 60 s |
|---|---|---|---|---|
| 30 | 195.5 mm (10 s) | **182.0** (+20 s LNS) | – | 218.5–243.5 |
| 100 | 521.5 (60 s) | 503.5 (+60 s) | **480.5** (71 s) | 616.5–643.5 |
| 300 | 2,316, 1 decap viol. (120 s) | legal in 6.9 s → **2,278** (+122 s) | 2,461.5 (124 s) | none |
| 1000 | 13,552.5, 16 overlaps + 2 decap (240 s) | cluster-wise legalize 3.9 s → **13,773.5** | 22,595.5 (294 s) | none |
- At N=1000 full-board CP-SAT legalization failed (none in 120 s); legalization must be windowed per violation cluster (`legalize_clusters.py`) [M].
- Seeds 1–2 at N=100: SA+polish 664 / 517.5 mm vs monolithic CP-SAT 858.5 / 681.0 mm [M].
- Literature SA: SA-PCB, B*-tree Fast-SA, Trace (8 move types), Hier-RTLMP weights, TILOS tuned SA (320 workers × 12.5 h) beating Circuit Training, Make It Home (Metropolis–Hastings), map labeling SA, control-cabinet Pareto SA ([placement families](../placement/algorithm-families.md)).
- Our SA lacks clustering and legalization-aware moves — a lower bar for what SA can do.

**Libraries** (PyPI metadata, 2026-10-20 [P])
| Package | License | Contents |
|---|---|---|
| pymoo 0.6.2 | Apache-2.0 | nsga2, nsga3, unsga3, rnsga2/3, moead, age/age2, ctaea, rvea, sms, spea2, mocmaes, gde3, nsde, mopso_cd, cmopso, dnsga2, pinsga2, kgb |
| ribs (pyribs) 0.12.0 | MIT | MAP-Elites, CMA-ME, CMA-MEGA, CMA-MAE + scalable variants; ask/tell with archive/emitters/scheduler |
| DEAP 1.4.4 | LGPL | CMA-ES, NSGA-II/III, SPEA2, MO-CMA-ES |
| Nevergrad 1.0.12 | MIT | `NGOpt`; last release 2025-04 |
| cma 4.5.0 | BSD-3 | CMA-ES |
| QDax | Apache-2.0 (JAX) | JIT-compiled QD/neuroevolution on GPU/TPU (JMLR'24) [S] |
| SA-PCB | BSD-3 | Upstream `choltz95/c-pcb-annealer`; host OpenROAD PCB-PR-App reads KiCad 5.1.2 boards |

**Quality-diversity precedents**
- **Warehouse layout + multi-robot coordination** (Zhang, Fontaine, Bhatt, Nikolaidis, Li; IJCAI'23; [arXiv 2305.06436](https://arxiv.org/abs/2305.06436) [P]; [code](https://github.com/lunjohnzhang/warehouse_env_gen_public)): optimize the layout instead of the MAPF algorithm; MAP-Elites maximizes lifelong-MAPF throughput (RHCR, DPP) while diversifying measures (connected shelf components, task length); **every candidate repaired by a MILP**; **DSAGE** surrogate predicts both the repaired layout and the simulation outcome; scaled to 200 robots; optimized layouts double supported robots in some cases.
- ELM (LLM as mutation operator in MAP-Elites; OpenELM); **QDAIF** (ICLR'24: LM generates variations and judges quality via yes/no log-probs and diversity via natural-language trait questions; risk of reward hacking); **MarioGPT** (novelty search; mutation replaces a level slice with an LLM sample, a second model inpaints borders); T-DominO, ARCH-Elites, constrained MAP-Elites, FI-MAP-Elites, TileGPT; Autodesk Project Discover (~10,000 office layouts on six stakeholder metrics) [S].
- AlphaEvolve's program database is MAP-Elites + islands; FunSearch uses islands; VeoPlace: greedy-best context is worst, stratified diverse context best ([LLM-evolved heuristics](llm-evolved-heuristics.md)).
- No QD application to chip/PCB floorplanning found.

**Zachtronics UX**: solve first, then optimize against histograms of other players' cost/cycles/area ("tall" vs "deep" solutions) ([cross-domain routing](../routing/cross-domain-routing-transplants.md)) [S].

## Recommendations for our system
- Division of labour [M/I]: analytical (Cypress-style) or SA for wirelength-driven global placement; CP-SAT for legalization (global ≤ ~300 parts, per-violation-cluster windows beyond) and constraint-heavy windows; **SA/tabu with incremental cost in Rust** for detailed placement; pymoo/Optuna for Pareto fronts; pyribs for diverse alternatives to show the LLM/user.
- **PCB QD pipeline** (warehouse port) [I]: layout → placement; throughput → routability (completion, vias, length from PathFinder/MCTS router/Freerouting); MILP repair → legalizer (sparrow-style GLS or CP-SAT NoOverlap2D); DSAGE → CNN/GNN predicting the legalized congestion map and routing success; measures = board area, single- vs double-sided fraction, signal-flow straightness, thermal spread.
- LLM emitters ("swap the power and RF blocks", "rotate U2 to face J1") next to Gaussian/CMA emitters; QDAIF-style VLM yes/no measures ("is the analog section isolated from the switcher?") guarded by hard DRC and routability [I].
- MarioGPT-style region mutation: resample one block with the generator (LLM program or diffusion) and inpaint borders with the legalizer [I].
- Pareto SA for thermal vs wire length (control-cabinet precedent) to show explicit trade-off fronts [I].
- Present portfolios with metric histograms vs prior boards or the archive [I].

## Conflicts and open questions
- No QD study on PCB or chip placement; the warehouse analogy is the closest validated precedent.
- SA+CP-SAT vs hierarchical CP-SAT ordering flips with N (hierarchical better at N=100, SA better from N=300) on single seeds; repeat on real boards before fixing the default pipeline.

## Sources
- research notes: [solver_toolbox.md § 3](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/solver_toolbox.md); [cross_domain_ideas.md § Q9, Q10](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/cross_domain_ideas.md)

See also: [llm-evolved-heuristics](llm-evolved-heuristics.md) · [bayesian-tuning](bayesian-tuning.md) · [benchmarks](benchmarks.md)
