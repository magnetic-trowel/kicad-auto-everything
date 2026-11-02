# Joint placement and routing: why, prior art, and the recommended architecture

Scope: why staged place-then-route gets stuck, prior art on joint P&R, candidate formulations, and the recommended topology-carrying joint state on three timescales. Not here: the PoC numbers -> [joint-place-route-experiment](joint-place-route-experiment.md); physics terms -> [physics-in-the-loop-optimization](physics-in-the-loop-optimization.md); budgets and τ -> [design-reasoning-architecture](design-reasoning-architecture.md).
Keys: joint P&R, place-then-route, PROXI, Independence, IPR, SimPLR, Ripple, Xplace, Starfish, ATLAS, CR&P, TopoR, homotopy class, topological elastic state, kinetic data structure, topological event, band tension, three timescales, LNS, MCTS, QD, binding constraint, multiplier, MS2, height × squares, JPR1–JPR48

**Results:**
- Staged flow fails for three measurable reasons: proxies do not rank routed outcomes where it matters, the router cannot move parts, and the deciding physics (loop L, plane cuts, coupling) exists only with copper (§1).
- Truly simultaneous P&R works but costs per move (PROXI: 8–15% better delay at 6–11× CPU); what scaled couples at the right granularity: global routing or topology inside placement (IPR, SimPLR, Ripple) or cell moves with partial reroute (Starfish). Commercial PCB tools run placement × router matrices, not joint search (§2).
- Recommended: joint over placement and topology, staged only for geometry: state = poses + per-net homotopy class, layer plan, via sites; geometry derived; part moves re-tighten bands with no rip-up until a topological event; congestion prices and physics gradients are placement forces; LNS windows destroy and repair parts and copper together.
- Physics is the shared objective that makes this work: hot-loop L, return continuity and via count pull placement and routing the same way; thermal spreading, isolation and density are the real conflicts (§6).
- PoC: joint refines a sequential start 10/10 (−18%) and ties an equal-CPU restart portfolio 5/10 → [experiment](joint-place-route-experiment.md) [C].

## 1. Why staged place-then-route gets stuck

| Failure | Evidence |
|---|---|
| Proxies do not rank near-equal placements | Cadence: 12,000 GA placements of one 350-part board, each autorouted: HPWL r = −0.923, crossings r = −0.898 with routability across all placements, but at equal normalized crossings (≈ 0.075) routability ranged 0.83–0.94 while re-routing one placement varied σ ≈ 0.005 ([patents_and_industry.md](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/patents_and_industry.md) [P-pat]) |
| Congestion proxies weak on PCBs | kicad-tools: HPWL 0.749 pairwise accuracy, 0.698 on same-perturbation pairs; RUDY "at or near chance" (0.46–0.57); a fitted 10-signal ranker never beat the best single signal, so it adopted "a bounded real route" as gate. circuit-skills: 0.79 with a fitted combination over 64 boards ([learning_from_layout_data.md § Q6](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/learning_from_layout_data.md) [P, unreviewed]) |
| Wirelength/density placers ignore routability | Apollo: 51% routability for DREAMPlace and Cypress in its domain vs 95% for a bending-aware placer ([analytical-differentiable](../solvers/analytical-differentiable.md) [S]) |
| Placement quality sets routing cost | DeepPCB: 6-min placement → 7 h routing, 111 vias; 14-h placement → 4.5 h, 79 ([deeppcb](../landscape/deeppcb.md) [V]) |
| Router cannot move parts; experts loop | Olney's 85% test-route gate sends work back to placement; expert flow has 18 states with loop-backs from routing to S2–S8; experts "move / rotate parts while doing the routing… swapping equivalent pins" ([expert-state-machine](../workflow/expert-state-machine.md) [P]). Quilter: "Router is very sequential… we can't do some sort of backtracking" ([quilter](../landscape/quilter.md) [V]) |
| Late co-optimization has little headroom | CR&P re-places and re-routes a routed VLSI design: −2.06% vias, −0.14% wirelength ([DATE'22](https://past.date-conference.com/proceedings-archive/2022/html/0201.html) [P-abs]); gains are in topology, early |

Structural causes [I]:
1. **Objective mismatch:** placement minimizes HPWL or RUDY; routing length, vias, overflow; physics loop L, plane breaks, coupling.
2. **Asymmetric authority:** placer cannot see copper, router cannot move parts, pins or sides; each stage's best response to the other is not a joint optimum (coordinate-descent trap).
3. **Physics observability:** loop L, return breaks, coupled length are functions of routed copper; a placement-only proxy diverges whenever routing detours, which is when it matters (straight-line loop proxy vs routed loop area: Spearman 0.23–0.79 [C], [experiment](joint-place-route-experiment.md)).

## 2. Prior art on joint placement and routing

| System | What is joint | Scale and result | Lesson |
|---|---|---|---|
| PROXI, Nag & Rutenbar (ICCAD'95; TCAD'98) | SA placement ripping up and re-routing every disturbed net after each move | 8–15% better delay than Xilinx XACT 5.0 at 6–11× CPU on 12×12–16×16 FPGA arrays; apparent O(n³) ([Marquardt et al., FPGA 2000](https://www.eecg.utoronto.ca/~jayar/pubs/marq/fpga2000_arm.pdf) [P]) | detailed-route joint search wins; cost per move kills scale |
| Independence (Sharma, Ebeling, Hauck 2005) | SA with PathFinder in the loop | within 5% of VPR, 17% better than HSRA's tool; any architecture ([UW](https://people.ece.uw.edu/hauck/publications/independenceFPGA05.pdf) [S]) | router-in-the-loop buys rule generality, which PCBs need |
| IPR (Pan & Chu, DAC'07) | FastPlace + FastRoute integrated | −36% overflow, −3.6% global-route length, −36% runtime vs ROOSTER ([PDF](https://home.engineering.iastate.edu/cnchu/pubs/c46.pdf) [S]) | global routing inside placement scales |
| SimPLR, Ripple (ICCAD'11), Xplace (BSD-3) | look-ahead global routing and routing-path cell inflation inside analytical placement; Xplace routability mode with cell inflation and GPU global router (GGR) | SimPLR beat every ISPD'11 contestant ([SimPLR](https://web.eecs.umich.edu/~imarkov/pubs/conf/iccad11-simplr.pdf) [S]); Xplace README documents GGR only as final evaluation ([Xplace](https://github.com/cuhk-eda/Xplace) [P]) | standard in VLSI: route coarsely, inflate, re-place |
| Starfish (ICCAD'21), ATLAS (ICCAD'22) | cell moves with A*-based partial reroute, SA acceptance | beat all ICCAD'20 "routing with cell movement" contestants ([HKBU](https://scholars.hkbu.edu.hk/en/publications/starfish-an-efficient-pampr-co-optimization-engine-with-a-based-p/) [S]) | closest analogue of our PoC |
| Chi et al. (DATE'21), analog | crossing-aware global route on a compact placement, then layout migration adjusts both | better routing-resource estimates and circuit performance ([PDF](https://past.date-conference.com/proceedings-archive/2021/pdf/1701.pdf) [P]) | route first on a compact placement, then make room |
| CGRA mappers (e.g. Chin & Anderson, DAC'18) | exact ILP over placement and routing | small arrays only [S] | exact joint is a window tool |
| TopoR, Altium Situs | topological map first; TopoR moves parts on a routed board "preserving the topology" | vendor claims, unaudited ([topological-routing](../routing/topological-routing.md) [V]) | persisting topology makes moves cheap |
| Quilter, DeepPCB, Cadence, Zuken | Quilter X.Y = placement × router matrix ranked by PRCs; DeepPCB places then routes; Cadence patents dispatch Place/Via/Route agents with a learned routability reward; Zuken needs parts placed | [V]/[P-pat] ([commercial patterns](../landscape/commercial-architecture-patterns.md)) | portfolios, not joint search, are commercial state of the art |
| Warehouse layout + MAPF (IJCAI'23) | layout scored by routed robot throughput; MAP-Elites, MILP repair | up to 2× robots ([metaheuristics-and-qd](../solvers/metaheuristics-and-qd.md) [P]) | score layouts by routing |

## 3. Candidate joint formulations

| Formulation | Joint state | Strength | Weakness | Verdict |
|---|---|---|---|---|
| Grid joint SA with incremental rip-up (PROXI, Starfish, our PoC) | poses + grid routes | simple, exact routed cost | ~25× costlier per routed move than HPWL SA (measured, [experiment](joint-place-route-experiment.md#results-c)); path-dependent route state | inner-loop tool and baseline |
| Lagrangian/ADMM price coupling | poses; routes; congestion prices | scales; prices are explanations | oscillation; needs damping | middle loop |
| Joint LNS (destroy parts + copper in a window, repair with CP-SAT + router) | poses + routes | exact locally, escapes local minima | window choice; CPU per iteration | inner loop for dense windows |
| Hierarchical coarse-to-fine (floorplan + corridors + layer budgets → cells → detail) | regions, corridors, then poses | necessary for scale; matches experts | commits early | scaffold for everything |
| MCTS or beam over coarse decisions with fast rollouts | sides, regions, orientations, homotopy picks | uses compute and LLM priors | rollout quality; patent proximity | outer loop |
| Differentiable relaxation of both | soft poses + soft route densities | gradients, GPU | discretization gap; homotopy is discrete | forces in the middle loop only |
| **Topological elastic state (recommended)** | poses + homotopy class + layer plan + via sites; geometry derived | moves re-tighten without rip-up; physics evaluable; explicit events | no maintained open multi-layer engine | substrate for all loops |

## 4. The joint state

Fully joint search over detailed geometry does not scale (PROXI's cost per move). Split loss is bounded: for a fixed topology, octilinear realization costs ~5% more length than the any-angle optimum (SURF, five layouts), plus the realizer's DRC repair [I].

State = (P, T, C):
- **P**: part poses (x, y, θ, side) with locks and admissible-pose masks.
- **T**: per net, a Steiner topology and a homotopy class relative to the obstacle set (ordered list of triangulation edges crossed, per layer), plus layer plan and via sites; bundles share corridor assignments ([S1](../../ideas/original/system-loop.md)).
- **C**: pour and plane regions ([copper-shape-synthesis](copper-shape-synthesis.md)).

Geometry derived: each band is the shortest path in its homotopy class (Hershberger–Snoeyink), realized octilinearly ([topological-routing](../routing/topological-routing.md)). Critics and budgets read (P, T, C) through the [physics IR](physics-ir.md).

- **Kinetic maintenance:** triangulation and band homotopies as a kinetic data structure; a band stays valid while its certificates (orientation, in-circle tests) hold ([Basch–Guibas–Hershberger](https://users.cs.fiu.edu/~giri/teach/6405/s04/MobileDataStruct.pdf) [S]). A part move re-tightens affected bands in time linear in their size. Certificate failure = **topological event** (a pin reaches a band, two bands swap order in a channel, a cut overflows); each is a decision: slip (homotopy change), shove, or block the move (JPR3).
- **Band tension replaces HPWL springs:** ∂(taut path length)/∂(endpoint) = unit tangent of its first segment; a part a band wraps feels the sum of both tensions, like a pulley [I]. Summed per part: exact routed-length gradients (JPR1). Cut congestion presses on the parts bounding the cut, priced PathFinder-style (JPR11); physics terms add their own gradients ([physics-in-the-loop-optimization](physics-in-the-loop-optimization.md)).

## 5. The algorithm: three timescales

| Loop | Time | Decides | Method |
|---|---|---|---|
| Outer | minutes | block regions, sides, big-part orientations, corridor and layer budgets, critical-net homotopy picks; by spatial scale (world, stackup, cells, copper), then τ | MCTS/beam/QD with LLM menu proposals (JPR25, JPR48); rollouts = short middle loops |
| Middle | seconds | continuous poses | analytical placement by band tension + congestion prices + physics gradients; topology updated at events |
| Inner | milliseconds | local discrete repair | re-tightening, LPA* repair (JPR6), joint LNS windows (JPR19), exact micro-solves for critical cells (JPR20); accept on exact stage-2 quotes, not first-order prices |

Convergence [I]:
1. **Annealed coupling:** congestion and physics weights ramp like PathFinder's present factor (×1.3 per round) and ePlace's density weight; prices by damped dual ascent.
2. **Topological temperature:** homotopy changes free early, hysteresis penalty mid-run, frozen at the end (JPR13). Structures freeze by least slack τ ([design-reasoning](design-reasoning-architecture.md#ordering-least-slack-first)), topology only, never copper (JPR7).
3. **Trust regions from the kinetic structure:** a continuous step never crosses the next certificate failure, so band linearization is exact inside each step (JPR2); it also stops where the copper edit's Woodbury radius r reaches 0.5 ([physics-core-v2](physics-core-v2.md) §4).
4. **Switch rule:** leave the continuous phase when density overflow < 10% and topological events < 1 per 100 steps (JPR17); then legalize exactly with a channel-width constraint graph from the topology, making the room routes need (JPR14).
5. **Diagnostic:** stop when the share of nets changing topology per outer round plateaus (JPR18).
6. **Realization:** corridor rule areas and band waypoints to PNS/Freerouting for geometry; `kicad-cli` DRC on the re-opened board scores it.

Plain joint SA is the right inner loop and honest baseline, but pays an A* per move, its route state drifts, and legality must stay hard ([experiment method lessons](joint-place-route-experiment.md#method-lessons-c)); the topological state makes small moves free.

### Fixed constraints as boundary conditions

| Constraint | Enters as | Price reported |
|---|---|---|
| Board outline | domain Ω for poses and routing graph; optionally a scale or edge variable with fab cost per cm² (JPR33) | ∂J/∂edge in mm, vias, nH |
| Mounting holes, screw heads | fixed obstacles with keep-out radius on all layers; chassis-return ports (JPR36) | keep-out multiplier |
| Connectors, antennas at edges | fixed poses; ports that inject and return current; antenna keep-out volume on all layers; chain order antenna → match → IC | leave-one-out joint re-solve of the anchor (JPR35) |
| Heatsinks | locked poses, height zone, thermal BC (h·A) in the thermal term ([thermal-physics](thermal-physics.md)) | °C per mm of displacement |
| Height zones, sides, mechanical keep-outs | admissible-pose masks; proposals never violate them (JPR37) | mask-relaxation re-solve |
| Test points | reserved access sites consuming bottom-side resources | sites per net vs vias |

**Binding constraint.** Every hard constraint carries a multiplier (legalizer LP dual, augmented-Lagrangian multiplier on a cut (JPR12), or penalty weight at convergence). Rank by multiplier, confirm the top k by background leave-one-out joint re-solves, report in physical units: the [I4 price tag](../../ideas/original/intent-and-why.md) including routed and physics consequences, which placement-only prices miss (JPR34).

## 6. Physics as the shared objective

| Term | Placement wants | Routing wants | Aligned? |
|---|---|---|---|
| Hot-loop L (MS2 or height × squares near a plane; area only without one) | input cap next to switch pins, pins facing | short, wide, no vias, return on adjacent layer | yes |
| Return continuity (plane cuts, unstitched layer changes) | planar net ordering, few crossings | stay above the plane, stitch at transitions | yes |
| Via count and inductance | few netlist crossings | few layer changes | yes |
| Crosstalk | aggressor and victim groups apart | spacing, short parallel runs | mostly; conflicts with compactness |
| EMI at cables | noisy parts away from connectors | short loops, inner layers | mostly; conflicts with wirelength near connectors |
| Thermal | hot parts spread, copper for heat | wide copper, thermal vias | **conflicts** with loop compactness |
| Isolation, creepage | distance across barriers | slots, keep-outs | **conflicts** with density |

- Each term uses the cheapest model that ranks correctly. Loops over a plane: MS2 (Σ length·L′(w,h) minus coupled-line mutuals) picks the PEEC-best loop 97–100% at fixed stackup, trace length 82–99%, plan-view area 66–97% ([solver-ladder](solver-ladder.md), [pdn-and-commutation](pdn-and-commutation.md)) [C, rt_loop_proxy]. Plan-view area is a planeless-board simplification.
- One objective: J = Σ w·φ(spend/budget) over the I1 budget ledger, φ flat below ~70% of budget and a steep barrier toward 100%, plus manufacturing cost (JPR29). Conflicting pairs get a local two-objective LNS and priced Pareto choice (JPR31). Budgets and weights come from [design-reasoning-architecture](design-reasoning-architecture.md).
- Term owners: [power-copper](power-copper.md), [pdn-and-commutation](pdn-and-commutation.md), [fields-si-emi](fields-si-emi.md), [fields-emi-budget](fields-emi-budget.md), [rf-geometry](rf-geometry.md), [thermal-physics](thermal-physics.md), [hv-and-manufacturing-physics](hv-and-manufacturing-physics.md).

## 7. Compute

- Measured gap: ~25× per routed move in pure Python ([experiment](joint-place-route-experiment.md#results-c)) [C].
- Closing it [I]: Rust (~10×, per KRT); delayed acceptance routing only moves a cheap first stage accepts (JPR41); kinetic state making most small moves reroute-free; speculative parallel moves with disjoint footprints (JPR38, ×cores).
- Massive compute [I]: island search with block crossover (JPR39); shared-incumbent portfolio of SA, LNS, analytical and MCTS workers (JPR40); successive halving over restarts with joint refinement (JPR45); background price probes (JPR35). GPU pays only above a few hundred parts (JPR44; [performance-and-multifidelity](../solvers/performance-and-multifidelity.md)).

## 8. Build order and kill criteria

1. **Joint LNS and SA in Rust on grid windows**, as refinement after a fast sequential placement, with delayed acceptance; reject illegal moves before routing; admissible-pose masks and channel-width legalizer in the loop (JPR37, JPR14). Kill if it does not beat the equal-CPU sequential portfolio (JPR46) on PCBWorld D3 and the Cypress small suite.
2. **Price coupling** of PathFinder history into the Cypress-style placer (supersedes P1). Kill if completion does not beat RUDY at equal CPU.
3. **Topological state for 2-layer boards** (CDT + kinetic bands, from Topola or toporouter code) + channel-width legalizer. Kill if band length does not out-predict HPWL for routed length.
4. **Outer MCTS/QD** over coarse decisions, with LLM menus.

## Open questions

- **Phase order:** [hybrid-architecture-options](../architecture/hybrid-architecture-options.md) builds staged Option A first and topology-first Option C last, for critical nets only. We argue the topological state should be the substrate for all nets once phase 1 works; geometry stays engine-made in both.
- **Quilter** presents P&R as one coupled search [V]; what it discloses is a ranked placement × router matrix (X.Y): a portfolio ([quilter](../landscape/quilter.md)) [I].
- **The 85% gate** ([expert-state-machine](../workflow/expert-state-machine.md)) becomes a continuous objective signal in a joint flow, not a stage gate.
- **Patents:** keep search deterministic over placement-level decisions; per-board online surrogates only, never a pretrained routability fitness (Cadence) or NN-guided particle look-ahead over net orders (DeepPCB) ([patents-watchlist](../landscape/patents-watchlist.md)).
- **Unverified:** PROXI and Independence numbers from citing papers; IPR, SimPLR, Starfish from abstracts. Kinetic bands with multi-layer vias unstudied; band-tension forces untested.

## Sources

- Research notes: [patents_and_industry.md § Cadence](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/patents_and_industry.md); [learning_from_layout_data.md § Q6](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/learning_from_layout_data.md); [routing_classics_supplement.md § Q2](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/routing_classics_supplement.md); [cross_domain_ideas.md § Q9](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/cross_domain_ideas.md).
- Primary and secondary: [Marquardt, Betz, Rose 2000 (PROXI)](https://www.eecg.utoronto.ca/~jayar/pubs/marq/fpga2000_arm.pdf); [Independence](https://people.ece.uw.edu/hauck/publications/Independence_J.pdf); [IPR](https://home.engineering.iastate.edu/cnchu/pubs/c46.pdf); [SimPLR](https://web.eecs.umich.edu/~imarkov/pubs/conf/iccad11-simplr.pdf); [Xplace](https://github.com/cuhk-eda/Xplace); [Starfish](https://scholars.hkbu.edu.hk/en/publications/starfish-an-efficient-pampr-co-optimization-engine-with-a-based-p/); [CR&P](https://past.date-conference.com/proceedings-archive/2022/html/0201.html); [Chi et al. DATE'21](https://past.date-conference.com/proceedings-archive/2021/pdf/1701.pdf); [kinetic data structures](https://users.cs.fiu.edu/~giri/teach/6405/s04/MobileDataStruct.pdf); [delayed acceptance MCMC](https://arxiv.org/pdf/1806.05982).
- Related: [ideas: joint placement and routing](../../ideas/physics-first/joint-place-route.md), [pathfinder-negotiated-congestion](../routing/pathfinder-negotiated-congestion.md), [physics-critics-catalog](physics-critics-catalog.md).
