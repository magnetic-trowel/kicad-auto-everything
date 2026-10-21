# Placement algorithm families (and what PCB tools actually use)

**TL;DR**
- Real PCB placers fall into four classes: greedy grid heuristics (KiCad), SA/metaheuristics (SA-PCB, B*-tree Fast-SA, GA/PSO, Trace), analytical/force-directed global placement + discrete legalizer (NS-Place, Cypress, NTU 2025, Zhao 2025, PA-ICM), and mathematical programming (HiePlace, MILP/QP legalizers).
- Since 2025 the field converged on **VLSI-style analytical placement adapted to PCBs + MILP/QP/constraint-graph legalization**. Vanilla VLSI placers fail on PCBs without rotation, side-aware density, pad clearance, net-crossing terms and irregular geometry.
- **SA remains the best cheap HPWL optimizer at small N** and the baseline every claim must beat (TILOS lesson).
- **Monolithic exact models break at ~50–100 parts**; exact solvers belong in legalization and local windows ([legalization](legalization.md), [CP-SAT](../solvers/cp-sat-milp-smt.md)).
- **KiCad's autoplacer is a greedy 1 mm grid scan with no rotation since 7.0** — usable only as a seed.

## Key facts

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

**Force-directed / quadratic.** Quadratic placers behave like springs; GORDIAN spreads by recursive partitioning; Kraftwerk/FastPlace/SimPL differ in the spreading "density force"; SimPL alternates lower-bound solves with look-ahead legalization ([SimPL](https://janders.eecg.utoronto.ca/1387/readings/simpl.pdf) [S]). HiePlace notes analytical PCB approaches were validated only on "oversimplified or synthetic" cases ([HiePlace](https://www.cse.cuhk.edu.hk/~byu/papers/J156-TCAD2026-HiePlace.pdf) [P]). PCB revival (NTU): TCAD'25 combines SA pad alignment, force-directed GP guided by **anchor points from power-circuit flows**, window legalization — +13.5% routability, −26% runtime vs ePlace-MS, >50% better routability than Cypress ([DOI](https://doi.org/10.1109/tcad.2025.3618936) [S, abstract]); DAC'25 LBR adds **Separating-Axis-Theorem collision on exact contours/board shapes** and scanline legalization ([DOI](https://doi.org/10.1109/DAC63849.2025.11132719) [S]). kicad-tools ships force-directed, GA, hybrid, CMA-ES and Bayesian strategies with no documented objective ([repo](https://github.com/rjwalters/kicad-tools) [S]).

**Nonlinear analytical.** ePlace: cells as charges, FFT/DCT potential energy as density penalty, Nesterov with Lipschitz step prediction ([ePlace](https://cseweb.ucsd.edu/~jlu/papers/eplace-dac14/paper.pdf) [S]); RePlAce adds routability; DREAMPlace = PyTorch, >30× vs CPU RePlAce, fences (3.0), timing (4.0), BSD-3 ([repo](https://github.com/limbo018/DREAMPlace) [P]). **NS-Place: vanilla RePlAce "fails to find good solutions for multi-layer designs with diversely sized components"** and needs design-specific filler/anchor tuning ([arXiv 2210.14259](https://arxiv.org/pdf/2210.14259) [P]). Details of PCB adaptations: [analytical solvers](../solvers/analytical-differentiable.md), [PCB placers](pcb-placers-2022-2026.md).

**Simulated annealing.** SA-PCB: TimberWolf cooling, Ben-Ameur automatic T₀, cost = HPWL + polygon overlap (Boost.Geometry), 90°/45° rotation, Bookshelf + Eagle converter, BSD-3, archived; parameter-sensitive, weighted nets broken ([SA-PCB](https://github.com/The-OpenROAD-Project/SA-PCB) [S]). Cypress: its "strategy works for small designs but hurts larger ones" ([slides](https://ispd.cc/ispd2026/slides/2025/protected/3_1_slides.pdf) [P]). HiePlace calls B*-tree + SA (wirelength + area) the conventional PCB approach, with incomplete solution-space coverage; its own baseline needed manual adjustments [P]. (VLSI) tuned SA beat Circuit Training 17/17 on proxy, 16/17 on HPWL (ICCAD04), using 320 parallel go-with-the-winners workers for 12.5 h ([TILOS v3](https://arxiv.org/abs/2302.11014) [P], VP-verified). Commercial Trace: Claude analyzes the schematic, floorplan variants seed SA with 8 move types, cost = HPWL + RUDY + group compactness + thermal distribution ([docs](https://docs.buildwithtrace.com/concepts/pcb-layout) [S]). Hier-RTLMP: SA over a cluster tree with named weights (area 0.1, outline 100, WL 100, boundary 50, notch 10, blockage 10, guidance 10, fence 10) ([mpl](https://github.com/The-OpenROAD-Project/OpenROAD/tree/master/src/mpl) [S]). Measured: pure-Python SA reached legal 202–223 mm HPWL in 4–5 s at N=30 vs CP-SAT's 218.5–243.5 mm after 60 s ([benchmarks](../solvers/benchmarks.md) [M]).

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

**Mathematical programming.** Pure MILP placement fails: NS-Place's vanilla MILP found **no feasible placement within 4 h for 10 of 14 boards** (from 28 parts up) [P]; PCBAgent's MILP baseline reached HPWL 2.05× manual and failed spacing legality [P]; Z3 SMT floorplanning with rotation needed up to 45,474 s (n50b) [P]. Details: [CP-SAT/MILP/SMT](../solvers/cp-sat-milp-smt.md), [legalization](legalization.md).

**KiCad autoplacer** ([ar_autoplacer.cpp](https://github.com/KiCad/kicad-source-mirror/blob/master/pcbnew/autorouter/ar_autoplacer.cpp) [P]):
- 1.0 mm occupancy grid hard-coded to 2 routing layers; order by area × pad count, then area × ratsnest count.
- Scans every grid cell; score = `hypot(dx, 2·dy)` to nearest same-net pad + keep-out cost scaled by pad count / `AR_GAIN` (16).
- Keeps each footprint's side (opposite side checked only for THT).
- **No rotation search since 7.0**: commit d649b288 (2021-12-24) removed the 6.0-era 90/180/270 trials and `OrientationPenalty` sliders ([commit](https://gitlab.com/kicad/code/kicad/-/commit/d649b288a62aac5c31489bc41ab22149d7339014) [P]); old 5.x docs still describe rotation.
- UI: Place ▸ Auto-Place (off-board or selected); needs Edge.Cuts; skips locked parts; one undo step. A developer called it "terrible" in 2016 [S].

## Recommendations for our system
- Global placement: Cypress-style analytical engine or SA; never a monolithic exact model above ~50–100 parts [I].
- Keep SA (Rust, incremental cost) as baseline and detailed placer; compare against SA-PCB and tuned SA before claiming wins [I].
- Use sequence pair as the bridge from LLM pairwise relations to guaranteed-legal packings, and ALIGN-style constraint-preserving moves for small module floorplans ([transplants](packing-and-graph-drawing-transplants.md), [analog](analog-constraint-placement.md)) [I].
- Use clustering (netlist "IC + satellites", schematic sheets) to create hierarchy; KiCad autoplacer only as fallback seed [I].

## Conflicts and open questions
- No study compares all families on one open PCB benchmark ([benchmarks](benchmarks-and-metrics.md)).
- No head-to-head CP-SAT vs MILP for PCB legalization was found (our own measurements partly fill this: [benchmarks](../solvers/benchmarks.md)).

## Sources
- research notes: [placement_algorithms.md § Q1](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/placement_algorithms.md); [solver_toolbox.md § 1, § 3](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/solver_toolbox.md); [verification_papers.md § 1](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_papers.md)

See also: [pcb-placers-2022-2026](pcb-placers-2022-2026.md) · [legalization](legalization.md) · [ml-rl-placement](ml-rl-placement.md) · [solvers/recommended-stack](../solvers/recommended-stack.md)
