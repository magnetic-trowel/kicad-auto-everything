# Physics-first ideas: joint placement and routing (JPR)

Workstream 11. Each idea is a numbered entry with a bold name, its mechanism, why it beats staged place-then-route, and how to test it. Tags: *new* (not found in the survey), *combo* (known parts, new combination), *sharp* (a sharpened version of an existing idea). Effort: S (days), M (weeks), L (months). Evidence and the recommended architecture are in [joint-place-route](../../topics/physics/joint-place-route.md); the proof of concept is in [joint-place-route-experiment](../../topics/physics/joint-place-route-experiment.md). Existing ideas referenced: P1, P7, S1, S6, R1, R2, I1, I4 in the [original catalog](../original/README.md).

## Top 5 to try first

1. **JPR14** channel-width constraint-graph legalizer: legalization that makes exactly the room the routes need.
2. **JPR1** band-tension ("rope and pulley") placement forces: the gradient of routed length replaces HPWL springs.
3. **JPR41** delayed-acceptance joint SA: route only the moves a cheap first stage already likes.
4. **JPR46** joint-versus-portfolio protocol: every joint claim is compared against equal-CPU sequential restarts.
5. **JPR34** joint constraint price tags (with JPR33 board size as a priced variable): the optimizer reports what each mechanical constraint costs in routed and physical units.

---

## A. Joint state and representation

**JPR1. Band-tension placement forces ("rope and pulley").** Keep each net as a taut rubber band in its homotopy class. The gradient of a taut path's length with respect to an endpoint is the unit tangent of its first segment, and a part that a band wraps around feels the vector sum of the two tensions, like a pulley. Sum these forces per part and use them in place of HPWL springs in the analytical placer. This replaces a proxy with the derivative of the routed quantity itself, so the placer sees detours that HPWL cannot. Test: rank correlation of band length vs HPWL against final routed length on 20 boards, then placement quality at equal CPU. *new*, M.

**JPR2. Kinetic topology certificates as the trust region.** Maintain the constrained Delaunay triangulation and band homotopies as a kinetic data structure (Basch–Guibas–Hershberger certificates). Each continuous placement step is clipped to the time at which the first certificate fails. Inside that radius the band linearization is exact; at the boundary a discrete topological event occurs. This gives a principled step size that staged flows lack. Test: steps and wall time to converge vs fixed step sizes on the same placer. *new*, L.

**JPR3. Topological event menu.** When a moving pin is about to cross a band, offer three resolutions: the band slips over the pin (its homotopy class changes by one generator), the band is shoved ahead, or the move is blocked. Score each on the joint objective and take the best. This is the discrete half of a joint optimizer that a staged flow handles only by rip-up after the fact. Test: count of rip-ups avoided and final J vs rip-up-and-reroute on the same move sequence. *new*, M.

**JPR4. Homotopy flips as SA moves.** Add "flip net n around obstacle o" and "swap the order of two bands in a channel" to the move set beside part moves, and allow compound moves (move part + flip the bands it disturbs). Placement and topology then anneal together instead of topology being frozen by the router's first choice. Test: joint SA with and without topology moves at equal CPU. *combo*, M.

**JPR5. Layer assignment as a fast inner solve.** After each topology change, assign layers to band segments by a min-cut on the crossing graph of the affected region (via minimization), as in Dayan–Dai "defer decisions". It keeps the expensive discrete choice out of the placement loop but still lets placement see via counts. Test: via count and runtime vs fixed preferred-direction layers. *sharp*, M.

**JPR6. Incremental route repair with LPA*/D* Lite.** When a part moves, update only the graph costs that changed and repair affected paths with lifelong A*, instead of ripping them up. Reroute work then scales with the size of the change, which is what makes per-move routing affordable. Test: nodes expanded per move vs rip-up-and-A* in the PoC script. *sharp*, M.

**JPR7. Lock topology, not copper.** Experts route and lock critical nets before bulk routing. Instead, freeze a critical net's homotopy class and layer plan but keep its geometry elastic, so later part moves re-tighten it rather than collide with it. This keeps expert priorities without the rigidity that forces late rip-ups. Test: number of re-place iterations and critical-net length drift on boards with locked vs topology-locked critical nets. *new*, S.

**JPR8. Unified occupancy market.** Put courtyards, keep-outs, tracks, vias and pours on one per-layer resource map with one PathFinder pricing rule. Parts are "nets" that demand area, and nets demand tracks; both pay present and history congestion. Placement and routing then negotiate for the same resources in the same currency. Test: completion and J vs staged on dense 2-layer boards. *new*, M.

**JPR9. Fanout-carrying macros.** Treat each fine-pitch IC plus its escape vias and stubs as one rigid macro whose ports are the escape endpoints. Joint moves drag the escape with the part, and bands attach to ports. This avoids re-solving escape per move and matches how experts plan BGA fanout before placement. Test: joint SA move throughput and completion with and without macros on BGA boards. *sharp*, S.

**JPR10. Planar-embedding seeds.** Compute a crossing-minimized planarization of the netlist graph (each crossing is at least one via pair on two layers) and seed placement from that embedding. Placement then starts from a low-via topology rather than from a wirelength optimum that later needs vias. Test: vias and bottom-layer length after routing, seeded vs HPWL-seeded, on 2-layer boards. *new*, M.

## B. Coupling, convergence and continuation

**JPR11. Congestion prices as pressure forces.** Turn PathFinder history costs on cuts into a pressure on the courtyards that bound each cut, proportional to price times overflow, and feed it to the placer as a force; update the prices by dual ascent (ADMM-style) with damping. This replaces RUDY with the router's own scarcity signal. It sharpens P1 by using prices rather than one-off probes. Test: oscillation (price variance) and final completion vs P1 probe forces. *sharp*, M.

**JPR12. Augmented Lagrangian on cut capacities.** Write every SURF cut as a constraint flow ≤ capacity with a multiplier and a quadratic penalty, and let the placer minimize the augmented Lagrangian. The multipliers are channel prices the LLM can read ("the channel between U3 and J1 is worth 4 mm per track"). Test: convergence on 20 boards and agreement of multipliers with leave-one-out channel widening. *sharp*, M.

**JPR13. Topological temperature.** Run a separate annealing temperature for homotopy changes. Early, bands may jump over pins freely; mid-run, a change costs a hysteresis penalty; at the end, topology is frozen and only geometry moves. This gives a controlled path from global exploration to a stable routing plan. Test: final J and topology-change rate across schedules. *new*, S.

**JPR14. Channel-width constraint-graph legalizer.** Build the legalizer's constraint graph from the routing topology: the minimum gap between two parts equals the summed width plus spacing of the bands that pass between them, on each layer. A CP-SAT or LP compaction then legalizes and makes exactly the room the routes need, no more. Staged legalizers make room for nobody, which is why routers fail at 85% density. Test: completion and board-area utilization vs a plain min-displacement legalizer on the same global placements. *new*, M.

**JPR15. Route on a compact placement, then make room.** Route topologically on an overlapping, compact placement, then legalize with JPR14 so the parts spread around their routes. This is the analog "route then migrate" pattern (Chi et al., DATE'21) and TopoR's "route everything while violating, then optimize". Test: compare with place-then-route on boards above 70% utilization. *combo*, M.

**JPR16. Multigrid continuation.** Run the joint search first on 2 mm global-routing cells, then 0.5 mm grid, then gridless realization, warm-starting each level from the last. Coarse levels move parts far cheaply; fine levels settle detail. Test: J vs CPU curves for single-level and multigrid joint SA. *sharp*, M.

**JPR17. Explicit continuous-to-discrete switch rule.** Leave the elastic (continuous) phase when density overflow is below 10% (the ePlace stop rule) and fewer than one topological event occurs per 100 steps; then legalize exactly and switch to discrete LNS. Test: final J sensitivity to the two thresholds. *sharp*, S.

**JPR18. Topology-stability convergence diagnostic.** Track the fraction of nets whose homotopy class or layer plan changed since the last outer iteration. Stop or escalate (larger LNS windows) when it plateaus above a threshold. Staged flows have no convergence signal at all. Test: correlation of the diagnostic with remaining J improvement. *new*, S.

## C. Search operators

**JPR19. Joint LNS window: destroy parts and copper together.** Pick a window, remove its movable parts and every track and via inside it, then repair placement and routing together: enumerate a few candidate poses per part with CP-SAT and route each candidate with a windowed A*, accepting on the joint objective. Test: J improvement per CPU second vs single-part SA moves. *combo*, M.

**JPR20. Exact joint micro-solve for critical cells.** For eight parts or fewer and their nets (a buck power stage, a crystal, an RF match), solve placement and routing exactly in one CP-SAT model on a 0.25 mm grid, with nets as flows and the routed loop area as objective. The result becomes a hard macro. The cells that matter most physically get a provable joint optimum. Test: routed loop area vs staged and vs expert reference layouts. *new*, M.

**JPR21. Joint MaxSAT for escape plus decoupling.** Decide decap positions, their via sites and the IC escape routing in one MaxSAT or CP-SAT model, because each decap via competes with escape vias for the same sites. Test: decap mounting inductance and escape completion vs decaps-first then escape. *combo*, M.

**JPR22. Pin and gate swaps as joint moves.** Swapping equivalent pins (FPGA banks, MCU pin-mux, resistor-pack gates) changes topology without moving parts. Include swaps in the move set with incremental reroute. Experts do this while routing; staged flows cannot, because the schematic is frozen. Test: crossings and vias with and without swap moves on MCU boards. *sharp*, S.

**JPR23. Side flips with real via cost.** Evaluate flipping a part to the bottom side on the joint state, which counts the through vias, the changed loop areas and the thermal path, instead of a fixed second-side penalty. Test: side choices vs P4 graph cut on double-sided boards. *sharp*, S.

**JPR24. Drag moves with copper.** Move a part together with the stubs, vias and band segments that are private to it, so the move does not break its own routing. This cuts per-move reroute work for passives, which are most of the parts. Test: accepted moves per second in the PoC script. *new*, S.

**JPR25. MCTS over coarse joint decisions with elastic rollouts.** The tree branches on block regions, sides, big-part orientations and critical homotopy picks; each rollout runs a short elastic joint phase and returns J. Keep the search over placement-level decisions with deterministic evaluation, away from the DeepPCB SMC patent claims. Test: best J at equal CPU vs random restarts of the same rollout. *combo*, M.

## D. Physics as the shared objective

**JPR26. Routed hot-loop area, not the pin triangle.** Compute hot-loop area from the actual band paths plus the return path on the reference plane, including the vertical extent of any segment on another layer. The PoC shows the straight-line proxy and the routed area diverge once routing detours exist. Test: proxy vs routed area rank correlation; nH from a loop solver on the final boards. *sharp*, S.

**JPR27. Plane-cut length as a joint term.** Charge every millimetre of copper on a layer that should be a solid reference, and every slot it leaves, in budget units. Placement influences it through crossings, routing through layer choice; neither stage can minimize it alone. Test: plane-cut length and return-path checker findings, staged vs joint. *new*, S.

**JPR28. Co-routed return bands.** Route each critical signal together with an explicit return band (its plane region or GND trace) so loop area is a property of the pair. This extends R2 shadow return nets into the joint state, where moving a part re-tightens both. Test: loop area and plane splits on mixed-signal boards. *combo*, M.

**JPR29. Budget-normalized objective with a soft barrier.** Normalize every physics term by its budget from the I1 ledger and sum w·φ(spend), where φ is flat below about 70% of budget and rises steeply towards 100%. Placement and routing then trade nH against mV against °C in one dimensionless currency. Test: budget violations and Pareto spread vs a weighted sum of raw units. *sharp*, S.

**JPR30. Admissible physics lower bounds for pruning.** At each fidelity level use a bound that never exceeds the realized value: straight-line loop area below routed loop area, cut-capacity overflow below routed overflow. Moves whose lower bound is already worse than the incumbent are pruned without routing, as A* prunes with an admissible heuristic. Test: fraction of moves pruned and absence of false prunes on logged runs. *new*, M.

**JPR31. Local Pareto LNS for thermal versus loop conflicts.** Where thermal spreading and loop compactness pull apart (two FETs, one heatsink), run a two-objective LNS in that window and hand the front to the LLM or user, priced in nH per °C. Test: whether the chosen point beats both single-objective solutions on the budget ledger. *combo*, S.

**JPR32. Coupling-aware homotopy choice.** Score each candidate homotopy of a victim net by its parallel-run length next to aggressor bands in shared channels, using the coupling formula from the rule pack. Placement then sees that moving a part changes which channels a victim must share. Test: crosstalk checker findings vs a router with spacing rules only. *sharp*, M.

## E. Boundary conditions and constraint prices

**JPR33. Board size as a priced variable.** Make the outline scale (or each free edge) a continuous variable with a fab cost per cm², and report ∂J/∂edge. Shrinking stops where routing and physics cost more than area saves. Test: area vs J trade-off curve against expert-chosen board sizes. *new*, S.

**JPR34. Joint constraint price tags.** Read the multiplier of every fixed constraint (connector pose, mounting-hole keep-out, height zone) from the joint optimizer and confirm the top k with leave-one-out joint re-solves. Unlike placement-only prices, these include routed and physics consequences ("moving J1 4 mm left saves 3 vias and 0.6 nH"). This sharpens I4. Test: agreement of multipliers with re-solves; usefulness ratings by designers. *sharp*, M.

**JPR35. Mechanical sensitivity map for the ME.** Background jobs perturb each mechanical anchor by ±δ in x, y and angle and re-run a short joint optimization. The result is a map the mechanical engineer can read ("if the USB-C moves 3 mm towards the MCU: −2 vias, −0.4 nH"). It turns the expert loop-back to S1 mechanics into numbers. Test: did any anchor move reveal a gain larger than 5% of J on real boards? *new*, M.

**JPR36. Connectors, antennas and holes as ports.** Model connectors and antenna feeds as fixed terminals that inject and return current, and mounting holes as chassis-return ports. The PDN, return-path and EMI terms then have physical boundary conditions instead of keep-out rectangles alone. Test: return-path findings near connectors, joint vs staged. *sharp*, S.

**JPR37. Admissible-pose sampling.** Encode height zones, side bans, antenna keep-out volumes and screw-head keep-outs as per-part pose masks, and draw proposals only from admissible poses instead of penalizing violations afterwards. Hard boundary conditions then cost no search time. Test: accepted-move rate with masks vs penalties. *sharp*, S.

## F. Compute and parallelism

**JPR38. Speculative parallel joint moves.** Evaluate many candidate moves at once on all cores; commit a maximal subset whose affected nets and windows are disjoint (a graph-colouring step), then repeat. Throughput scales with cores while each committed move stays exact. Test: moves per second and final J vs a single chain at equal wall time. *combo*, M.

**JPR39. Island model with block crossover.** Run islands of the joint search from different floorplans; crossover swaps whole blocks (parts plus internal copper) between islands when their corridor ports match. Good sub-layouts spread without being re-discovered. Test: best J at equal CPU vs independent restarts. *new*, L.

**JPR40. Shared-incumbent portfolio.** Run joint SA, joint LNS, price-coupled analytical placement and the MCTS outer loop concurrently, sharing the best solution and the current congestion prices, as CP-SAT workers share bounds. Test: portfolio vs best single method at equal CPU. *combo*, M.

**JPR41. Delayed-acceptance joint SA.** Make each move pass a cheap first Metropolis test on HPWL, crossings and loop proxies, and route only moves that pass; the second test on the routed objective corrects the first (Christen–Fox delayed acceptance), so the chain still targets the routed objective. The PoC measured a ~10–100× per-move cost gap between proxy and routed moves; most routed evaluations are spent on moves a proxy would reject. Test: J vs CPU against plain joint SA. *sharp*, S.

**JPR42. Online per-board surrogate for move screening.** Fit a small linear model of ΔJ on cheap features (ΔHPWL, Δcrossings, Δband length, Δloop proxy) from the board's own exact evaluations and use it as the first stage of JPR41. The model is per board and never pretrained, which keeps clear of the learned-routability patents. Test: screening precision and recall over a run. *combo*, S.

**JPR43. Bandit over move types and regions.** Learn online which move types (shift, swap, homotopy flip, LNS window) and which regions yield accepted improvements, and sample them more. Test: J vs CPU with and without the bandit. *sharp*, S.

**JPR44. GPU batched window routing.** Batch thousands of small-window shortest-path relaxations as tensor wavefronts on a GPU to evaluate candidate moves or LNS repairs en masse. Use it only once the CPU version is the bottleneck on boards above 300 parts. Test: evaluations per second per watt vs Rust A* on CPU cores. *new*, L.

**JPR45. Successive halving over joint fidelity.** Seeds get topology-only evaluation, survivors get grid routing, finalists get Freerouting plus `kicad-cli` DRC plus physics critics. This extends S6 from placement × router candidates to joint candidates. Test: best final score at equal CPU vs route-all-at-low-budget. *sharp*, S.

## G. LLM role, explanation and evaluation

**JPR46. Joint-versus-portfolio protocol.** Every claim that a joint method helps must beat an equal-CPU portfolio of sequential runs (restarts with a new seed, each routed and scored) and a longer single sequential run, scored by the same referee router. The PoC shows the portfolio is the control that matters. Test: adopt in the bench harness as a required baseline. *sharp*, S.

**JPR47. Planted-optimum joint instances.** Generate boards backwards: draw a planar, physically good routed layout first, then derive its netlist and perturb the placement. The joint optimum is then known, so the gap of each method can be measured. Test: gap distribution for staged, joint and portfolio methods. *combo*, M.

**JPR48. LLM proposes topology moves from a bounded menu.** In the outer loop the LLM picks from menus (swap two blocks' corridors, flip a block to the bottom, reroute a bundle around the other side of U4), and the inner joint loop evaluates each pick. The LLM never writes coordinates, which matches the evidence that relations beat coordinates. Test: J and tokens per board vs no LLM moves. *sharp*, S.

**JPR49. Event narration from the joint state.** Every topological event and every newly binding constraint generates one line of explanation ("C12 moved under U3's escape, so the USB pair now goes around the left side: +1.8 mm, +0 vias"). Designers get the why that staged autorouters never give. Test: designer ratings of explanations vs plain DRC reports. *new*, S.

**JPR50. Three-timescale controller.** Organize the system as an outer discrete loop (minutes: regions, sides, orientations, critical homotopies), a middle elastic loop (seconds: band-tension placement with congestion prices) and an inner incremental loop (milliseconds: re-tightening, local reroutes, LNS windows), with the hand-off rules of JPR13, JPR17 and JPR18. This is the recommended architecture in [joint-place-route](../../topics/physics/joint-place-route.md). Test: the phased plan in that doc, each phase with a kill criterion. *combo*, L.

---

See also: [joint-place-route](../../topics/physics/joint-place-route.md) · [joint-place-route-experiment](../../topics/physics/joint-place-route-experiment.md) · [original placement ideas](../original/placement.md) · [original routing ideas](../original/routing.md) · [system loop](../original/system-loop.md) · [physics-in-the-loop optimization](../../topics/physics/physics-in-the-loop-optimization.md) · [copper-shape synthesis](../../topics/physics/copper-shape-synthesis.md)
