# Original ideas: simultaneous and interleaved place-and-route

Scope: 43 ideas that drop the place → legalize → route order: parts and copper decided together or in short alternating steps, with a real router (not a congestion estimate) inside the placement loop. Part of the [original-ideas catalog](README.md). Not here: verdicts and key numbers -> [scorecard](scorecard.md); runs -> [joint research area](../../research/joint/README.md).
Keys: joint place-and-route, halo grid, PathFinder for everything, Lagrangian price gradient, envelope theorem, beam search, MCTS, LNS, guided local search, elastic band, copper as charge, harmonic field, Physarum, soft-min Bellman–Ford, Tutte embedding, crossing number, multigrid, LLM move proposer, Numberlink SAT, physics place terms

Status tags: **[T]** tested in the pnr lab (`tools/research/pnr/`; verdict in the [scorecard](scorecard.md)), **[Q]** queued, **[I]** idea only. Later status (tested: 1–3, 6–8, 11–13, 16, 17, 19, 20, 22, 23, 26, 30, 32, 36, 43; 17 and 23 folded into soft-route-grad; 18 partly built) is in [research/ideas](../../research/ideas.md#joint-place-and-route-untested-catalog-ideas) and overrides the tags below.

## Shared substrate

One engine for every idea, so they compare fairly:
- Fine grid, 0.05–0.1 mm per copper layer. Clearance by "halo" stamps, not routing pitch: each laid object stamps its copper, expanded by clearance + the other object's half-width, into a track-centre map and a via-centre map; a centreline is legal where no foreign halo covers it. Handles off-grid pads, 45° segments, mixed widths; result written back to KiCad and scored by `kicad-cli` DRC.
- Footprints: rigid pad/courtyard stamps, 4 orientations; side given.
- Router: negotiated congestion (PathFinder), cell cost = present cost × history cost.

## A. One market for parts and wires (negotiation)

1. **Unified negotiated congestion ("PathFinder for everything")** [T: legal and routed within 3 rounds; wire prices must decay]. A footprint is a fat "net" whose candidate routes are poses. Parts and wires share one present/history price field; each round every object rips itself up and re-chooses (wire: A*; part: best pose in a neighbourhood, priced by the cells it would cover + its nets' routed cost). Courtyard/copper overlap allowed but priced; prices rise until no conflict remains. Source: PathFinder (FPGA routing), generalized to placement.
2. **Lagrangian price gradients** [T]. PathFinder history costs = Lagrange multipliers on cell capacity; a footprint consumes capacity, so the multiplier field is a gradient for moving it: parts slide toward cells wires do not want. Source: Lagrangian relaxation of multicommodity flow.
3. **Envelope-theorem wire forces** [T]. ∂(shortest-path length)/∂(endpoint) = unit tangent of the path at that endpoint, so a routed net pulls each pin along the direction its actual track leaves, not toward the net centroid (HPWL); detours become forces that rotate and slide parts. Source: envelope theorem; differentiable shortest paths.
4. **Congestion game / best-response dynamics** [I]. Parts and nets as selfish players in a potential game; iterate best responses to a Nash equilibrium. Mechanics of 1 without global prices: tests whether prices matter.
5. **Auction for board area** [I]. Parts bid for grid regions with budgets set by net criticality (Bertsekas auction algorithm); converges to an ε-optimal assignment.

## B. Grow the board (constructive interleaving)

6. **Place-one, route-it** [T]. Order parts by connectivity (start from the most connected IC); per part try K candidate poses, route the nets that now have both ends placed, keep the cheapest. Mirrors designers (place a block, route it, move on). Source: constructive hand layout; Tetris-style packing.
7. **Beam search over growth orders** [T: merit; completion 0.891 vs 0.868 greedy, physics 0.98× human]. Keep B partial boards; expand each with the next part's best poses; prune by routed cost + look-ahead estimate.
8. **MCTS with routing rollouts** [T: trails beam; too few rollouts at 120 CPU-s]. Tree of 7; rollouts complete the board greedily and route it; UCT allocates effort. Source: AlphaGo, MCTS-based routers.
9. **Space-colonization growth** [I]. Wires grow one step at a time toward "attractor" pins while parts still move; branches merge into Steiner trees. Source: procedural tree generation (Runions et al.).
10. **Dungeon-generator layout** [I]. Place rooms (blocks), carve corridors (bundles), move rooms to shorten corridors. Source: procedural dungeons.

## C. Local search where routing is the cost function

11. **Annealing with incremental rip-up and reroute** [T]. Moves: shift, rotate, swap two same-footprint parts. Cost: unrouted connections, routed length, vias, by re-routing only nets touching the moved part. Source: VPR routability-driven placement with a real router instead of a wiring estimate.
12. **Large-neighbourhood search on windows** [T: `repair`, blocker-directed]. Rip up a window (parts + copper), re-place and re-route it jointly, accept if better. Source: LNS in vehicle routing.
13. **Guided local search on blocked nets** [T: part of `repair`]. Each round raise a penalty on the part blocking most failed routes (A* blocker attribution) and move it. Source: GLS (Voudouris), sparrow nesting.
14. **Tabu over part swaps with route reuse** [I]. Keep routes of unaffected nets; tabu list on (part, pose) pairs.
15. **Evolution strategies (CMA-ES) over poses** [I]. Fitness = fast route; for rugged routed cost where gradients lie.
16. **Quality-diversity archive** [I at catalog time; later T]. MAP-Elites over (board area used, via count, longest net); routing evaluates every elite. Source: warehouse layout QD.

## D. Continuous and physics models

17. **Elastic-band co-relaxation** [I] (the gradient agent chose soft-min paths, 22). Each net = polyline of beads with tension (length) and repulsion from other nets' beads and from parts; parts = rigid bodies pushed by touching beads. One energy, one gradient descent; snap to grid at the end. Source: elastic bands in robot motion planning; Durbin–Willshaw elastic net.
18. **Copper as charge** [Q]. ePlace electrostatic density where routed copper also counts as charge, pushing parts out of wiring channels.
19. **Harmonic-field routing** [I at catalog time; later T]. Solve Laplace's equation per net (pins = sources, parts = walls); harmonic streamlines have no local minima and streamlines of one field never cross; part moves update the field cheaply (multigrid). Source: harmonic potential fields in robotics.
20. **Physarum multicommodity solver** [T: no merit as built]. Tube conductivities grow with flux, decay otherwise; with several commodities and shared capacity the surviving tubes form a routed network; parts feel the flux through their footprint as pressure. Source: slime-mould network models (Tero et al.).
21. **Homotopy continuation of clearance** [Q]. Start with zero clearance and shrunken footprints so everything fits; grow both while re-solving. Source: continuation methods; analog "soft then hard" constraints.
22. **Soft-min Bellman–Ford** [T: gradients no better than HPWL; useful only as a global start for physics descent]. Differentiable shortest-path distances over a smoothed cost field give exact gradients of routed length w.r.t. obstacle masks, hence w.r.t. part positions via a differentiable rasterizer.
23. **Perturbed-optimizer gradients** [I]. Average the routed solution under random cost noise for a smoothed, differentiable routing (Berthet et al. 2020).

## E. Structure first

24. **Tutte embedding seed** [Q]. Barycentric embedding of the part graph with boundary connectors pinned; crossing-free by construction on planar parts of the netlist, so it seeds placements needing few vias.
25. **Crossing-number objective** [Q]. Minimize straight-line ratsnest crossings (proxy for vias on 2 layers) instead of HPWL.
26. **Pin-direction orientation matching** [T]. Choose each part's rotation so its pins face the direction their routes actually leave (from 3), solved as an assignment.
27. **Planar sub-netlist layering** [I]. Split the netlist into two planar layers (thickness-2 graph), assign a layer per net up front, place so both layers stay planar.
28. **Multigrid V-cycle** [Q]. Place and route on a 1 mm grid, refine to 0.5 and 0.1 mm, re-solving locally per level. Source: multigrid solvers; hierarchical FPGA routing.
29. **Channel reservation** [I]. Every bundle gets a corridor before parts are final; parts may not invade it (= corridor contract [S1](system-loop.md)).

## F. Learning and language models

30. **LLM as move proposer** [T: routing inconclusive, physics no merit; use for diagnosis]. The LLM reads a rendered board with failed nets marked and proposes moves ("move U3 left of J1, rotate C4"); the joint optimizer accepts or rejects. The model never writes coordinates.
31. **LLM-evolved coupling policy** [I]. Evolve the rule deciding when to stop routing and move parts (AlphaEvolve-style), scored on held-out boards.
32. **Learned value of partial boards** [I at catalog time; later T]. Small CNN on (partial board → final routed completion) from lab runs, used to prune beam search (7).
33. **Diffusion on joint state** [I]. Denoise placement + coarse routing-density image together, then repair. Long horizon.
34. **Imitation of human routing order** [I]. Mine net order and placement order from git history of open boards.

## G. Other domains, mapped

35. **Factory-game solvers** [I]. Factorio/Shapez tools place machines and belts together with SAT; their "belt bus first" trick maps to corridor-first PCB layout.
36. **Numberlink SAT windows** [T: no merit]. Exact joint solve of a small window: part-pose variables + path variables in one SAT/CP-SAT model.
37. **Chemical plant piping** [I]. Equipment placement and pipe routing co-optimized in MILP with length, bend and support costs; maps to vias and bends.
38. **Ship cable harness** [I]. Equipment and cable trays co-placed; bundles share trays. Maps to bus bundling.
39. **Urban co-generation** [I]. Streets and buildings generated together by tensor fields: a direction field sets preferred routing direction per layer; part orientation follows it.
40. **Microfluidic biochip co-design** [I]. Valve placement and channel routing solved together because channels cannot cross: the one-layer PCB routing constraint.
41. **Protein side-chain packing** [I]. Discrete orientations as rotamers, pairwise energies including routed cost; dead-end elimination prunes poses.
42. **Origami/knot routing** [I]. Net homotopy classes as braids; part moves as braid moves that remove crossings.

## Physics in the objective (added after the first results)

43. **Physics place terms in every objective** [T: merit]. kae.physics `Terms.delta` (~50 µs) added to placement and annealing costs; no completion cost. HPWL alone makes boards that route well and are electrically wrong. Numbers: [physics-objective](../../research/joint/physics-objective.md#results).

## What gets tested first, and why

Ideas 1, 2, 3, 6, 11 and 26 share the router and differ only in how placement reacts to routing: one engine tests them all against two controls, (a) the same router on the human placement, (b) the same router after a conventional HPWL-driven placement. Scored by KiCad DRC on the qualified A/B boards.
