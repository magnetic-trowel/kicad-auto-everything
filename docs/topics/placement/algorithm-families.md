# Placement algorithm families (and what PCB tools actually use)

Scope: placement algorithm families and which PCB tools use them. Not here: 2022–2026 PCB placers in detail -> [PCB placers](pcb-placers-2022-2026.md); legalizers -> [legalization](legalization.md).
Keys: force-directed, quadratic, GORDIAN, Kraftwerk2, FastPlace, SimPL, ePlace, RePlAce, DREAMPlace, simulated annealing, SA-PCB, TimberWolf, B*-tree, Fast-SA, Trace, Hier-RTLMP, TILOS, GA, PSO, PA-ICM, Capo, min-cut, sequence pair, O-tree, CBL, BSG, Baxter numbers, MILP, KiCad autoplacer, ar_autoplacer.cpp, AR_GAIN

**Results**
1. Real PCB placers fall into four classes: greedy grid heuristics (KiCad), SA/metaheuristics (SA-PCB, B*-tree Fast-SA, GA/PSO, Trace), analytical/force-directed global placement + discrete legalizer (NS-Place, Cypress, NTU 2025, Zhao 2025, PA-ICM), and mathematical programming (HiePlace, MILP/QP legalizers).
2. Since 2025 the field converged on **VLSI-style analytical placement adapted to PCBs + MILP/QP/constraint-graph legalization**. Vanilla VLSI placers fail on PCBs without rotation, side-aware density, pad clearance, net-crossing terms and irregular geometry.
3. **SA remains the best cheap HPWL optimizer at small N** and the baseline every claim must beat (TILOS lesson → [ML/RL](ml-rl-placement.md#methods-and-results)).
4. **Monolithic exact models scale poorly**; exact solvers belong in legalization and local windows ([legalization](legalization.md), [CP-SAT](../solvers/cp-sat-milp-smt.md)).

## Families overview

| Family | Representatives | PCB status |
|---|---|---|
| Force-directed / quadratic | Quinn & Breuer 1979 (first PCB FD placer), GORDIAN, Kraftwerk2 (Bound2Bound), FastPlace, SimPL | Revived by NTU 2024–25 with power-flow anchors and pad alignment |
| Nonlinear analytical / electrostatic | ePlace, RePlAce, DREAMPlace | Basis of Cypress, Chen DAC'25, Zhao 2025, NS-Place |
| Simulated annealing | TimberWolf lineage, SA-PCB, B*-tree Fast-SA, Trace, Hier-RTLMP | SA-PCB is the standard open PCB baseline |
| GA / evolutionary / swarm | Jain & Gea 1996, SOGA 2012, GA+Lee 2016, PSO thermal 2017, PA-ICM DEA | Mostly older, toy-scale; PA-ICM hybrid is fast |
| Partitioning / min-cut | Capo, ROOSTER | Survives as clustering (hMETIS, DBSCAN) |
| Floorplan representations | Sequence pair, B*-tree, O-tree, CBL, BSG, Polish expr. | Declining for PCB; useful as constraint-preserving search spaces |
| Mathematical programming | HiePlace MP, NS-Place MILP, NTU CG-MILP, QP legalizers, SMT | Standard for legalization; fails monolithically |
| Greedy grid | KiCad autoplacer | Weak |

**Force-directed / quadratic.** Quadratic placers behave like springs; GORDIAN spreads by recursive partitioning; Kraftwerk/FastPlace/SimPL differ in the spreading "density force"; SimPL alternates lower-bound solves with look-ahead legalization ([SimPL](https://janders.eecg.utoronto.ca/1387/readings/simpl.pdf) [S]). HiePlace notes analytical PCB approaches were validated only on "oversimplified or synthetic" cases ([HiePlace](https://www.cse.cuhk.edu.hk/~byu/papers/J156-TCAD2026-HiePlace.pdf) [P]). PCB revival (NTU, Tsou et al.): force-directed GP guided by **anchor points from power-circuit flows**, SA pad alignment, SAT collision on exact contours → [PCB placers](pcb-placers-2022-2026.md#methods-and-results). kicad-tools ships force-directed, GA, hybrid, CMA-ES and Bayesian strategies with no documented objective ([repo](https://github.com/rjwalters/kicad-tools) [S]).

**Nonlinear analytical.** ePlace: cells as charges, FFT/DCT potential energy as density penalty, Nesterov with Lipschitz step prediction ([ePlace](https://cseweb.ucsd.edu/~jlu/papers/eplace-dac14/paper.pdf) [S]); RePlAce adds routability; DREAMPlace = PyTorch, >30× vs CPU RePlAce, fences (3.0), timing (4.0), BSD-3 ([repo](https://github.com/limbo018/DREAMPlace) [P]). **NS-Place: vanilla RePlAce "fails to find good solutions for multi-layer designs with diversely sized components"** and needs design-specific filler/anchor tuning ([arXiv 2210.14259](https://arxiv.org/pdf/2210.14259) [P]). Details of PCB adaptations: [analytical solvers](../solvers/analytical-differentiable.md), [PCB placers](pcb-placers-2022-2026.md).

**Simulated annealing.** SA-PCB: TimberWolf cooling, Ben-Ameur automatic T₀, cost = HPWL + polygon overlap (Boost.Geometry), 90°/45° rotation, Bookshelf + Eagle converter, BSD-3, archived; parameter-sensitive, weighted nets broken ([SA-PCB](https://github.com/The-OpenROAD-Project/SA-PCB) [S]). Cypress: its "strategy works for small designs but hurts larger ones" ([slides](https://ispd.cc/ispd2026/slides/2025/protected/3_1_slides.pdf) [P]). HiePlace calls B*-tree + SA (wirelength + area) the conventional PCB approach, with incomplete solution-space coverage; its own baseline needed manual adjustments [P]. (VLSI) tuned SA beat Circuit Training → [TILOS](ml-rl-placement.md#methods-and-results). Commercial Trace: Claude analyzes the schematic, floorplan variants seed SA with 8 move types, cost = HPWL + RUDY + group compactness + thermal distribution ([docs](https://docs.buildwithtrace.com/concepts/pcb-layout) [S]). Hier-RTLMP: SA over a cluster tree with named weights (area 0.1, outline 100, WL 100, boundary 50, notch 10, blockage 10, guidance 10, fence 10) ([mpl](https://github.com/The-OpenROAD-Project/OpenROAD/tree/master/src/mpl) [S]). Our SA vs CP-SAT measurements → [benchmarks § E](../solvers/benchmarks.md#e-simulated-annealing--cp-sat-legalizationpolish) [C].

**GA / swarm.** NS-Place: older GA/PSO PCB placers "are computationally expensive, incapable of rotating components, or evaluated on synthetic or toy benchmarks" [P]. PA-ICM's hybrid (distribution EA for orientation + conjugate subgradient for coordinates) runs in seconds on industrial modules ([arXiv 2502.14012](https://arxiv.org/pdf/2502.14012) [P]).

**Partitioning.** Capo: recursive multilevel min-cut bisection (MLPart), optimal end-case placers, no analytical placement or congestion estimation ([Capo](https://web.eecs.umich.edu/~imarkov/pubs/conf/c015.pdf) [S]); ROOSTER uses RSMT net models. Today partitioning survives as **clustering for hierarchy** (hMETIS in Circuit Training, DBSCAN in PA-ICM) [P].

**Floorplan representations** (Yao et al., ISPD'01, [PDF](https://www.esa.informatik.tu-darmstadt.de/archive/twiki/pub/Lectures/AlgorithmenImChipEntwurf06De/floorplan-ispd01.pdf) [P]):

| Representation | Solution space | Transform |
|---|---|---|
| Sequence pair (complete; longest-path decode, Murata 1996) | O((n!)²) | O(n log log n) |
| Bounded-sliceline grid | n!·C(n², n), redundant | O(n²) |
| O-tree | O(n!·2^(2n−2)/n^1.5) | O(n) |
| Corner block list (mosaic) | O(n!·2^(3n−3)/n^1.5) | O(n) |

Mosaic floorplans are counted by Baxter numbers, slicing by Schröder numbers; twin binary trees are non-redundant. CBL cannot represent empty rooms → ECBL, 3-D and boundary-constrained variants [S]. B*-tree Fast-SA perturbs by rotate/move/swap [S]. PCB use: PA-ICM says SP/B*/O-tree "cannot accommodate" IC-centred two-layer modules; still published: SP centralized block placement (Li, ICCCAS'24), SP with predefined coordinate alignment (Liu, ASICON 2001), "Relay-race" (Sheng, ISVLSI 2011) [P].

**Mathematical programming.** Pure MILP placement fails: NS-Place vanilla MILP found no feasible placement in 4 h for 9–10 of 14 boards (most boards above ~20 parts); PCBAgent's MILP baseline reached HPWL 2.05× manual and failed spacing legality [P]; Z3 SMT with rotation up to 45,474 s (n50b) [P] → per-board detail [CP-SAT/MILP/SMT](../solvers/cp-sat-milp-smt.md#pcb-scale-exact-solver-literature), [legalization](legalization.md).

**KiCad autoplacer** ([ar_autoplacer.cpp](https://github.com/KiCad/kicad-source-mirror/blob/master/pcbnew/autorouter/ar_autoplacer.cpp) [P]):
- 1.0 mm occupancy grid hard-coded to 2 routing layers; order by area × pad count, then area × ratsnest count.
- Scans every grid cell; score = `hypot(dx, 2·dy)` to nearest same-net pad + keep-out cost scaled by pad count / `AR_GAIN` (16).
- Keeps each footprint's side (opposite side checked only for THT).
- **No rotation search since 7.0**: commit d649b288 (2021-12-24) removed the 6.0-era 90/180/270 trials and `OrientationPenalty` sliders ([commit](https://gitlab.com/kicad/code/kicad/-/commit/d649b288a62aac5c31489bc41ab22149d7339014) [P]); old 5.x docs still describe rotation.
- UI: Place ▸ Auto-Place (off-board or selected); needs Edge.Cuts; skips locked parts; one undo step. A developer called it "terrible" in 2016 [S].

## Use in kae
- Global placement: Cypress-style analytical engine or SA; never a monolithic exact model above ~100 parts: our monolithic CP-SAT stays feasible to ~200 parts but has competitive HPWL only to ~100 (single synthetic solver-bench instance, 4 workers) [C/I]. kae's production model, with macros and sliced rectangles, is capped at 40 items ([kae-placer](../../research/placement/kae-placer.md)).
- Keep SA (Rust, incremental cost) as baseline and detailed placer; compare against SA-PCB and tuned SA before claiming wins [I].
- Use sequence pair as the bridge from LLM pairwise relations to non-overlapping packings (cyclic relation sets have no completion; outline, keep-out and fixed-part legality still needs the legalizer), and ALIGN-style constraint-preserving moves for small module floorplans ([transplants](packing-and-graph-drawing-transplants.md), [analog](analog-constraint-placement.md)) [I].
- Use clustering (netlist "IC + satellites", schematic sheets) to create hierarchy; KiCad autoplacer (greedy 1 mm grid, no rotation since 7.0) only as fallback seed [I].

## Open questions
- No study compares all families on one open PCB benchmark ([benchmarks](benchmarks-and-metrics.md)).
- No head-to-head CP-SAT vs MILP for PCB legalization was found (our own measurements partly fill this: [benchmarks](../solvers/benchmarks.md)).

## Sources
- [placement_algorithms.md § Q1](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/placement_algorithms.md); [solver_toolbox.md § 1, § 3](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/solver_toolbox.md); [verification_papers.md § 1](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_papers.md)
