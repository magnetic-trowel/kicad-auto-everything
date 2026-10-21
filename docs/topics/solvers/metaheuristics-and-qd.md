# Metaheuristics, multi-objective search and quality-diversity

**TL;DR**
- **SA with incremental cost is the strongest simple HPWL optimizer at small–medium N**: pure-Python SA beat 60 s of 4-worker CP-SAT on HPWL at N=30 in a few seconds — but it does not guarantee legality (needs a legalizer).
- Multi-objective and diversity libraries are mature and permissive: pymoo (Apache-2.0), pyribs (MIT), cma (BSD-3), Nevergrad (MIT), Optuna (MIT); DEAP is LGPL.
- **Quality-diversity has a strong layout precedent**: warehouse layouts optimized for multi-robot throughput with MAP-Elites + MILP repair + a surrogate supported up to 2× more robots — directly analogous to "placement for routability".
- LLM-native QD (ELM mutations, QDAIF judges, MarioGPT inpainting) makes portfolios of diverse, legal, routable placements practical; show them with Zachtronics-style histograms.

## Key facts

**Simulated annealing**
- Our SA (`sa_place.py`, pure Python + NumPy, ramped overlap penalty, moves shift/rotate/swap): ~10–11k moves/s at N=30; legal **202–223 mm HPWL in 4–5 s** vs CP-SAT's best 218.5–243.5 mm after 60 s; one 5 s run ended with 2 overlaps; CP-SAT LNS polishing (3×2 s windows) of a 202 mm result found no improvement ([benchmarks](benchmarks.md) [M]).
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
- Division of labour [I]: analytical (Cypress-style) or SA for wirelength-driven global placement; CP-SAT for legalization and constraint-heavy windows; **SA/tabu with incremental cost in Rust** for detailed placement; pymoo/Optuna for Pareto fronts; pyribs for diverse alternatives to show the LLM/user.
- **PCB QD pipeline** (warehouse port) [I]: layout → placement; throughput → routability (completion, vias, length from PathFinder/MCTS router/Freerouting); MILP repair → legalizer (sparrow-style GLS or CP-SAT NoOverlap2D); DSAGE → CNN/GNN predicting the legalized congestion map and routing success; measures = board area, single- vs double-sided fraction, signal-flow straightness, thermal spread.
- LLM emitters ("swap the power and RF blocks", "rotate U2 to face J1") next to Gaussian/CMA emitters; QDAIF-style VLM yes/no measures ("is the analog section isolated from the switcher?") guarded by hard DRC and routability [I].
- MarioGPT-style region mutation: resample one block with the generator (LLM program or diffusion) and inpaint borders with the legalizer [I].
- Pareto SA for thermal vs wire length (control-cabinet precedent) to show explicit trade-off fronts [I].
- Present portfolios with metric histograms vs prior boards or the archive [I].

## Conflicts and open questions
- No QD study on PCB or chip placement; the warehouse analogy is the closest validated precedent.
- `{{SA}}` results section in the source notes is still pending at time of writing ([benchmarks](benchmarks.md)).

## Sources
- research notes: [solver_toolbox.md § 3](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/solver_toolbox.md); [cross_domain_ideas.md § Q9, Q10](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/cross_domain_ideas.md)

See also: [llm-evolved-heuristics](llm-evolved-heuristics.md) · [bayesian-tuning](bayesian-tuning.md) · [benchmarks](benchmarks.md)
