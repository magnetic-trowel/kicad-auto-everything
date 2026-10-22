# Joint placement and routing: why, prior art, and the recommended architecture

**TL;DR**
- Staged place-then-route gets stuck for three measurable reasons: placement proxies do not rank routed outcomes where it matters (equal crossings, routability 0.83–0.94 across 12,000 placements; RUDY at chance), the router cannot move parts, and the physics that decides quality (loop inductance, plane cuts, coupling) only exists once copper exists.
- Truly simultaneous P&R works but is expensive per move (PROXI 1995: 8–15% better delay at 6–11× CPU). Everything that scaled since couples placement to routing at the **right granularity**: global routing or topology inside placement (IPR, SimPLR, Ripple), or cell moves with partial reroute (Starfish). Commercial PCB tools run placement × router matrices, not joint search.
- **Recommendation: a topology-carrying joint state optimized on three timescales.** The state is part poses plus each net's homotopy class, layer plan and via sites; geometry is derived. Part moves re-tighten rubber bands with no rip-up until a topological event. Congestion prices and physics gradients act as placement forces, and LNS windows destroy and repair parts and copper together.
- Physics is the shared objective that makes this work: hot-loop inductance, return-path continuity and via count pull placement and routing the same way. Score loop inductance as height × squares (Σ μ0·h·dl/w) or MS2 whenever a reference plane is near; plan-view area is a planeless-board simplification. Thermal spreading, isolation and density are the real conflicts.
- Proof of concept on synthetic 2-layer boards ([experiment](joint-place-route-experiment.md)): at equal CPU, joint SA beat a longer sequential run on 5/5 30-part boards (median −17%, mostly fewer vias and smaller hot loops; p = 0.06) and a restart portfolio on 3/5, but 2/5 at 50 parts, where ~25× costlier moves let restarts catch up. Over both sizes it ties the portfolio 5/10 (median J ratio 0.96, 95% CI 0.83–1.24); what is supported is refining a sequential start (10/10, −18%) [C, rt_jpr_stats].

## Key facts

### 1. Why staged place-then-route gets stuck

| Failure | Evidence |
|---|---|
| Proxies do not rank near-equal placements | Cadence ran 12,000 GA placements of one 350-part board, each autorouted: HPWL r = −0.923 and crossings r = −0.898 with routability overall, but at equal normalized crossings (≈0.075) routability ranged 0.83–0.94 while re-routing one placement varied σ ≈ 0.005 ([patents_and_industry.md](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/patents_and_industry.md) [P-pat]) |
| Congestion proxies are weak on PCBs | kicad-tools: HPWL 0.749 pairwise accuracy, 0.698 on same-perturbation pairs; RUDY "at or near chance" (0.46–0.57); a fitted 10-signal ranker never beat the best single signal, so the project adopted "a bounded real route" as its gate. circuit-skills: 0.79 with a fitted combination over 64 boards ([learning_from_layout_data.md § Q6](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/learning_from_layout_data.md) [P, unreviewed]) |
| Wirelength/density placers ignore routability | Apollo reports 51% routability for DREAMPlace and Cypress in its domain vs 95% for a bending-aware placer ([analytical-differentiable](../solvers/analytical-differentiable.md) [S]) |
| Placement quality sets routing cost | DeepPCB: a 6-min placement needed 7 h of routing and 111 vias, a 14-h placement 4.5 h and 79 ([deeppcb](../landscape/deeppcb.md) [V]) |
| The router cannot move parts; experts loop | Olney's 85% test-route gate sends work back to placement; the expert flow has 18 states and loop-backs from routing to S2–S8; experts "move / rotate parts while doing the routing… swapping equivalent pins" ([expert-state-machine](../workflow/expert-state-machine.md) [P]). Quilter: "Router is very sequential… we can't do some sort of backtracking" ([quilter](../landscape/quilter.md) [V]) |
| Late co-optimization has little headroom | CR&P re-places and re-routes an already routed VLSI design: −2.06% vias, −0.14% wirelength ([DATE'22](https://past.date-conference.com/proceedings-archive/2022/html/0201.html) [P-abs]). The gains are in topology, early |

Three structural causes follow [I]:
1. **Objective mismatch.** Placement minimizes HPWL or RUDY, routing length, vias and overflow, physics loop inductance, plane breaks and coupling: three different objectives.
2. **Asymmetric authority.** The placer cannot see copper and the router cannot move parts, pins or sides; each stage's best response to the other is not a joint optimum (a coordinate-descent trap).
3. **Physics observability.** Loop inductance, return-path breaks and coupled length are functions of routed copper; a placement-only proxy (pin triangles, distances) diverges whenever routing detours, which is when it matters. On our synthetic boards the straight-line loop proxy ranked routed loop area with Spearman 0.23–0.79 [C] ([experiment](joint-place-route-experiment.md)).

### 2. Prior art on joint placement and routing

| System | What is joint | Scale and result | Lesson |
|---|---|---|---|
| PROXI, Nag & Rutenbar (ICCAD'95; TCAD'98) | SA placement that rips up and re-routes every disturbed net after each move | 8–15% better delay than Xilinx XACT 5.0 at 6–11× CPU on 12×12–16×16 FPGA arrays; apparent O(n³) ([Marquardt et al., FPGA 2000](https://www.eecg.utoronto.ca/~jayar/pubs/marq/fpga2000_arm.pdf) [P]) | Detailed-route joint search wins; cost per move kills scale |
| Independence (Sharma, Ebeling, Hauck 2005) | SA with PathFinder in the loop | Within 5% of VPR, 17% better than HSRA's tool; adapts to any architecture ([UW](https://people.ece.uw.edu/hauck/publications/independenceFPGA05.pdf) [S]) | Router-in-the-loop buys rule generality, which PCBs need |
| IPR (Pan & Chu, DAC'07) | FastPlace + FastRoute integrated | −36% overflow, −3.6% global-route length, −36% runtime vs ROOSTER ([PDF](https://home.engineering.iastate.edu/cnchu/pubs/c46.pdf) [S]) | Global routing inside placement scales |
| SimPLR, Ripple (ICCAD'11), Xplace (BSD-3) | Look-ahead global routing and routing-path cell inflation inside analytical placement; Xplace adds a routability mode with cell inflation and a GPU global router (GGR) | SimPLR beat every ISPD'11 contestant ([SimPLR](https://web.eecs.umich.edu/~imarkov/pubs/conf/iccad11-simplr.pdf) [S]); Xplace's README documents GGR only as final evaluation ([Xplace](https://github.com/cuhk-eda/Xplace) [P]) | Now standard in VLSI: route coarsely, inflate, re-place |
| Starfish (ICCAD'21), ATLAS (ICCAD'22) | Cell moves with A*-based partial reroute of broken nets, SA acceptance | Beat all ICCAD'20 "routing with cell movement" contestants ([HKBU](https://scholars.hkbu.edu.hk/en/publications/starfish-an-efficient-pampr-co-optimization-engine-with-a-based-p/) [S]) | The closest analogue of our PoC |
| Chi et al. (DATE'21), analog | Crossing-aware global route on a compact placement, then layout migration adjusts placement and routing together | Better routing-resource estimates and circuit performance ([PDF](https://past.date-conference.com/proceedings-archive/2021/pdf/1701.pdf) [P]) | Route first on a compact placement, then make room |
| CGRA mappers (e.g. Chin & Anderson, DAC'18) | Exact ILP over placement and routing | Small arrays only [S] | Exact joint is a window tool |
| TopoR, Altium Situs | Topological map first; TopoR moves parts on a routed board "preserving the topology" | Vendor claims, unaudited ([topological-routing](../routing/topological-routing.md) [V]) | Persisting topology makes moves cheap |
| Quilter, DeepPCB, Cadence, Zuken | Quilter X.Y = placement × router matrix ranked by PRCs; DeepPCB places then routes; Cadence patents dispatch Place/Via/Route agents with a learned routability reward; Zuken needs parts placed | [V]/[P-pat] ([commercial patterns](../landscape/commercial-architecture-patterns.md)) | Portfolios, not joint search, are the commercial state of the art |
| Warehouse layout + MAPF (IJCAI'23) | Layout scored by routed robot throughput; MAP-Elites, MILP repair | Up to 2× robots ([metaheuristics-and-qd](../solvers/metaheuristics-and-qd.md) [P]) | Score layouts by routing |

### 3. Candidate joint formulations

| Formulation | Joint state | Strength | Weakness | Verdict |
|---|---|---|---|---|
| Grid joint SA with incremental rip-up (PROXI, Starfish, our PoC) | Poses + grid routes | Simple, exact routed cost | ~30× costlier per move than HPWL SA (measured); path-dependent route state | Inner-loop tool and baseline |
| Lagrangian/ADMM price coupling | Poses; routes; congestion prices | Scales; prices are explanations | Oscillation; needs damping | Middle loop |
| Joint LNS (destroy parts + copper in a window, repair with CP-SAT + router) | Poses + routes | Exact locally, escapes local minima | Window choice; CPU per iteration | Inner loop for dense windows |
| Hierarchical coarse-to-fine (floorplan + corridors + layer budgets → cells → detail) | Regions, corridors, then poses | Necessary for scale; matches experts | Commits early | Scaffold for everything |
| MCTS or beam over coarse decisions with fast rollouts | Sides, regions, orientations, homotopy picks | Uses compute and LLM priors | Rollout quality; patent proximity | Outer loop |
| Differentiable relaxation of both | Soft poses + soft route densities | Gradients, GPU | Discretization gap; homotopy is discrete | Forces in the middle loop only |
| **Topological elastic state (recommended)** | Poses + homotopy class + layer plan + via sites; geometry derived | Moves re-tighten without rip-up; physics evaluable; explicit events | No maintained open multi-layer engine | Substrate for all loops |

## Recommendations for our system

### How close to joint we can get
Fully joint search over detailed geometry does not scale (PROXI's cost per move), so the recommended system is **joint over placement and topology, staged only for geometry**. The split's loss is bounded: for a fixed topology, octilinear realization costs ~5% more length than the any-angle optimum (SURF, five layouts), plus the realizer's DRC repair [I]. Placement, sides, homotopy classes, layer plans and via sites are decided together.

### The joint state
State = (P, T, C):
- **P**: part poses (x, y, θ, side) with locks and admissible-pose masks.
- **T**: per net, a Steiner topology and a homotopy class relative to the obstacle set (the ordered list of triangulation edges it crosses, per layer), plus layer plan and via sites; bundles share corridor assignments ([S1](../../ideas/original/system-loop.md)).
- **C**: pour and plane regions, owned by the copper-shape work ([copper-shape-synthesis](copper-shape-synthesis.md)).

Geometry is derived: each band is the shortest path in its homotopy class (Hershberger–Snoeyink), realized octilinearly at ~5% extra length ([topological-routing](../routing/topological-routing.md)). Physics critics and budgets read (P, T, C) through the physics IR ([physics-ir](physics-ir.md)).

**Kinetic maintenance.** Keep the triangulation and band homotopies as a kinetic data structure: each band stays valid while its certificates (orientation and in-circle tests) hold ([Basch–Guibas–Hershberger](https://users.cs.fiu.edu/~giri/teach/6405/s04/MobileDataStruct.pdf) [S]). A part move re-tightens affected bands in time linear in their size. A certificate failure is a **topological event**: a pin reaches a band, two bands swap order in a channel, or a cut overflows. Each event is a decision: slip the band (homotopy change), shove it, or block the move (JPR3).

**Band tension replaces HPWL springs.** The derivative of a taut path's length with respect to its endpoint is the unit tangent of its first segment; a part a band wraps around feels the sum of both tensions, like a pulley [I]. Summed per part, these are exact routed-length gradients (JPR1). Cut congestion presses on the parts bounding the cut, priced PathFinder-style (JPR11); physics terms add their own gradients ([physics-in-the-loop-optimization](physics-in-the-loop-optimization.md)).

### The algorithm: three timescales

| Loop | Time | Decides | Method |
|---|---|---|---|
| Outer | minutes | block regions, sides, big-part orientations, corridor and layer budgets, critical-net homotopy picks; by spatial scale (world, stackup, cells, copper), then τ | MCTS/beam/QD with LLM menu proposals (JPR25, JPR48); rollouts = short middle loops |
| Middle | seconds | continuous poses | analytical placement driven by band tension + congestion prices + physics gradients; topology updated at events |
| Inner | milliseconds | local discrete repair | re-tightening, LPA* repair (JPR6), joint LNS windows (JPR19), exact micro-solves for critical cells (JPR20); accept on exact stage-2 quotes, not first-order prices |

**Convergence strategy** [I]:
1. **Annealed coupling.** Congestion and physics weights ramp like PathFinder's present factor (×1.3 per round) and ePlace's density weight; prices follow damped dual ascent.
2. **Topological temperature.** Homotopy changes are free early, pay a hysteresis penalty mid-run and freeze at the end (JPR13). Structures freeze by least slack, the tightness ratio τ from [design-reasoning](design-reasoning-architecture.md), topology only, never copper (JPR7).
3. **Trust regions from the kinetic structure.** A continuous step never crosses the next certificate failure, so the band linearization is exact inside each step (JPR2). It also stops where the copper edit's Woodbury radius r reaches 0.5 ([physics-core-v2](physics-core-v2.md) §4).
4. **Switch rule.** Leave the continuous phase when density overflow is under 10% and topological events fall under 1 per 100 steps (JPR17); then legalize exactly with a channel-width constraint graph from the topology, which makes the room routes need (JPR14).
5. **Diagnostic.** Stop when the share of nets changing topology per outer round plateaus (JPR18).
6. **Realization.** Corridor rule areas and band waypoints go to PNS/Freerouting for geometry; `kicad-cli` DRC on the re-opened board scores it (bench rules).

Why not plain joint SA? It is the right inner loop and honest baseline, but pays an A* per move, its route state drifts (in the PoC, failed nets a fresh re-route avoided), and legality must stay hard: end-of-run legalization erased its gains. The topological state makes small moves free.

### Fixed constraints as boundary conditions

| Constraint | Enters as | Price reported |
|---|---|---|
| Board outline | Domain Ω for poses and the routing graph; optionally a scale or edge variable with fab cost per cm² (JPR33) | ∂J/∂edge in mm, vias, nH |
| Mounting holes, screw heads | Fixed obstacles with keep-out radius on all layers; chassis-return ports (JPR36) | Multiplier of the keep-out |
| Connectors, antennas at edges | Fixed poses; ports that inject and return current; antenna keep-out volume on all layers; chain order antenna → match → IC | Leave-one-out joint re-solve of the anchor (JPR35) |
| Heatsinks | Locked poses, height zone, thermal boundary condition (h·A) in the thermal term ([thermal-physics](thermal-physics.md)) | °C per mm of displacement |
| Height zones, sides, mechanical keep-outs | Admissible-pose masks: proposals never violate them (JPR37) | Mask-relaxation re-solve |
| Test points | Reserved access sites that consume bottom-side resources | Sites per net vs vias |

**Finding the binding constraint.** Every hard constraint carries a multiplier: the legalizer's LP dual, the augmented-Lagrangian multiplier on a cut (JPR12), or the penalty weight at convergence. Rank by multiplier, confirm the top k by background leave-one-out joint re-solves, report in physical units: the [I4 price tag](../../ideas/original/intent-and-why.md) with routed and physics consequences included, which placement-only prices miss (JPR34).

### Physics as the shared objective

| Term | Placement wants | Routing wants | Aligned? |
|---|---|---|---|
| Hot-loop inductance (MS2 or height × squares near a plane; area only without one) | Input cap next to the switch pins, pins facing | Short, wide, no vias, return on the adjacent layer | Yes |
| Return continuity (plane cuts, unstitched layer changes) | Planar net ordering, few crossings | Stay above the plane, stitch at transitions | Yes |
| Via count and inductance | Few netlist crossings | Few layer changes | Yes |
| Crosstalk | Aggressor and victim groups apart | Spacing, short parallel runs | Mostly; conflicts with compactness |
| EMI at cables | Noisy parts away from connectors | Short loops, inner layers | Mostly; conflicts with wirelength near connectors |
| Thermal | Hot parts spread, copper area for heat | Wide copper, thermal vias | **Conflicts** with loop compactness |
| Isolation, creepage | Distance across barriers | Slots, keep-outs | **Conflicts** with density |

Each term uses the cheapest model that ranks candidates correctly: for loops over a plane that is MS2 (Σ length·L′(w,h) minus coupled-line mutuals), which picks the PEEC-best loop 97–100% of the time at a fixed stackup, where plain trace length picks it 82–99% and plan-view area 66–97% ([solver-ladder](solver-ladder.md), [pdn-and-commutation](pdn-and-commutation.md)) [C, rt_loop_proxy]. One objective: J = Σ w·φ(spend/budget) over the I1 budget ledger, with φ flat below about 70% of budget and a steep barrier towards 100%, plus manufacturing cost (JPR29). Term owners: [power-copper](power-copper.md), [pdn-and-commutation](pdn-and-commutation.md), [fields-si-emi](fields-si-emi.md), [fields-emi-budget](fields-emi-budget.md), [rf-geometry](rf-geometry.md), [thermal-physics](thermal-physics.md), [hv-and-manufacturing-physics](hv-and-manufacturing-physics.md). Conflicting pairs get a local two-objective LNS and priced Pareto choice (JPR31). Design reasoning sets budgets and weights ([design-reasoning-architecture](design-reasoning-architecture.md)); this optimizer consumes them.

### Compute
- **Measured gap** [C]: in the PoC, HPWL SA ran 12–14k moves per CPU second, joint SA 510–550 routed moves: ~25× in pure Python ([experiment](joint-place-route-experiment.md)).
- **Closing it** [I]: Rust (~10×, per KRT), delayed acceptance that routes only moves a cheap first stage accepts (JPR41), a kinetic state that makes most small moves reroute-free, and speculative parallel moves with disjoint footprints (JPR38, ×cores).
- **Using massive compute** [I]: island search with block crossover (JPR39), a shared-incumbent portfolio of SA, LNS, analytical and MCTS workers (JPR40), successive halving over restarts with joint refinement (JPR45), background price probes (JPR35). GPU pays only above a few hundred parts (JPR44; [performance-and-multifidelity](../solvers/performance-and-multifidelity.md)).

### Build order and kill criteria
1. **Joint LNS and SA in Rust on grid windows**, as refinement after a fast sequential placement, with delayed acceptance. Kill if it does not beat the equal-CPU sequential portfolio (JPR46) on PCBWorld D3 and the Cypress small suite.
2. **Price coupling** of PathFinder history into the Cypress-style placer (supersedes P1). Kill if completion does not beat RUDY at equal CPU.
3. **Topological state for 2-layer boards** (CDT + kinetic bands, from Topola or toporouter code) plus the channel-width legalizer. Kill if band length does not out-predict HPWL for routed length.
4. **Outer MCTS/QD** over coarse decisions, with LLM menus.

## Conflicts and open questions
- **Round-3 corrections (2026-10-22):** joint ties an equal-CPU portfolio 5/10 (restated as refinement); fixed-stackup MS2 numbers; trust regions add r < 0.5 ([red-team](red-team.md)).
- **Phase order.** [Hybrid architecture options](../architecture/hybrid-architecture-options.md) builds the staged Option A first and topology-first Option C last, for critical nets only. We argue the topological state should be the substrate for all nets once phase 1 works, since it makes joint moves cheap; geometry stays engine-made in both.
- **Quilter.** [quilter](../landscape/quilter.md) summarizes Quilter as "one coupled search"; it discloses a ranked placement × router matrix (X.Y): a portfolio, not joint search [I].
- **The 85% gate.** In a joint flow, Olney's test-route gate ([expert-state-machine](../workflow/expert-state-machine.md)) becomes a continuous objective signal, not a stage gate.
- **Patents.** Keep search deterministic over placement-level decisions; use per-board online surrogates only, never a pretrained routability fitness (Cadence) or NN-guided particle look-ahead over net orders (DeepPCB) ([patents-watchlist](../landscape/patents-watchlist.md)).
- **Unverified.** PROXI and Independence numbers come from citing papers; IPR, SimPLR, Starfish from abstracts. Kinetic bands with multi-layer vias are unstudied; band-tension forces are untested.

## Sources
- research notes: [patents_and_industry.md § Cadence](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/patents_and_industry.md); [learning_from_layout_data.md § Q6](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/learning_from_layout_data.md); [routing_classics_supplement.md § Q2](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/routing_classics_supplement.md); [cross_domain_ideas.md § Q9](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/cross_domain_ideas.md)
- primary and secondary: [Marquardt, Betz, Rose 2000 (PROXI)](https://www.eecg.utoronto.ca/~jayar/pubs/marq/fpga2000_arm.pdf); [Independence](https://people.ece.uw.edu/hauck/publications/Independence_J.pdf); [IPR](https://home.engineering.iastate.edu/cnchu/pubs/c46.pdf); [SimPLR](https://web.eecs.umich.edu/~imarkov/pubs/conf/iccad11-simplr.pdf); [Xplace](https://github.com/cuhk-eda/Xplace); [Starfish](https://scholars.hkbu.edu.hk/en/publications/starfish-an-efficient-pampr-co-optimization-engine-with-a-based-p/); [CR&P](https://past.date-conference.com/proceedings-archive/2022/html/0201.html); [Chi et al. DATE'21](https://past.date-conference.com/proceedings-archive/2021/pdf/1701.pdf); [kinetic data structures](https://users.cs.fiu.edu/~giri/teach/6405/s04/MobileDataStruct.pdf); [delayed acceptance MCMC](https://arxiv.org/pdf/1806.05982)

See also: [joint-place-route-experiment](joint-place-route-experiment.md) · [ideas: joint placement and routing](../../ideas/physics-first/joint-place-route.md) · [topological-routing](../routing/topological-routing.md) · [pathfinder-negotiated-congestion](../routing/pathfinder-negotiated-congestion.md) · [hybrid-architecture-options](../architecture/hybrid-architecture-options.md) · [physics-critics-catalog](physics-critics-catalog.md) · [solver-ladder](solver-ladder.md)
