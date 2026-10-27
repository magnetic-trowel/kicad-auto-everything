# Original ideas: simultaneous and interleaved place-and-route

Part of the [original-ideas catalog](README.md). The other catalog files assume a
pipeline (place, legalize, then route). These ideas drop that order: parts and copper
are decided together, or in short alternating steps, and a real router (not a
congestion estimate) runs inside the placement loop. Test results live in
[placement/joint-pnr-experiments](../../topics/placement/joint-pnr-experiments.md).

Status tags: **[T]** tested in the pnr lab (`tools/research/pnr/`), **[Q]** queued,
**[I]** idea only.

## Shared substrate

Every idea below runs on one engine, so they can be compared fairly:
- A fine grid (0.05 to 0.1 mm) per copper layer. Clearance is enforced by "halo"
  stamps, not by coarse routing pitch: each laid object stamps its copper, expanded
  by clearance plus the other object's half-width, into a track-centre map and a
  via-centre map. A centreline is legal where no foreign halo covers it. This
  handles off-grid pads, 45° segments and mixed widths, and the result is written
  back to KiCad and scored by `kicad-cli` DRC.
- Footprints are rigid pad/courtyard stamps with 4 orientations; side is given.
- A negotiated-congestion (PathFinder) router: present cost × history cost per cell.

## A. One market for parts and wires (negotiation)

1. **Unified negotiated congestion ("PathFinder for everything")** [T: legal and routed within 3 rounds; wire prices must decay].
   A footprint is a fat "net" whose candidate routes are poses. Parts and wires
   share one present/history price field; each round every object rips itself up
   and re-chooses (wire: A*; part: best pose in a neighbourhood, priced by the cells
   it would cover plus its nets' routed cost). Overlap of courtyards and copper is
   allowed but priced, and prices rise until no conflict remains. Source: PathFinder
   (FPGA routing), generalized to placement.
2. **Lagrangian price gradients** [T]. PathFinder history costs are Lagrange
   multipliers on cell capacity. A part's footprint consumes capacity, so the
   multiplier field gives a gradient for moving it: parts slide toward cells wires
   do not want. Source: Lagrangian relaxation of multicommodity flow.
3. **Envelope-theorem wire forces** [T]. The derivative of a shortest path's length
   with respect to its endpoint is the unit tangent of the path at that endpoint.
   So a routed net pulls each pin along the direction its actual track leaves, not
   along the straight line to the net centroid (HPWL). Detours around obstacles
   then show up as forces that rotate and slide parts. Source: envelope theorem;
   differentiable shortest paths.
4. **Congestion game / best-response dynamics** [I]. Parts and nets as selfish
   players in a potential game; iterate best responses to a Nash equilibrium.
   Same mechanics as 1 without global prices; tests whether prices matter.
5. **Auction for board area** [I]. Parts bid for grid regions with budgets set by
   net criticality (Bertsekas auction algorithm). Converges to an assignment with
   ε-optimality guarantees.

## B. Grow the board (constructive interleaving)

6. **Place-one, route-it** [T]. Order parts by connectivity (start from the most
   connected IC). For each part, try K candidate poses, and for each pose actually
   route the nets that now have both ends placed; keep the cheapest. This is how
   designers work: place a block, route it, move on. Source: constructive placement
   in hand layout; Tetris-style packing.
7. **Beam search over growth orders** [T: merit, best method; completion 0.891 vs 0.868 greedy, physics 0.98× human]. Keep B partial boards; expand each with
   the next part's best poses; prune by routed cost plus a look-ahead estimate.
8. **MCTS with routing rollouts** [T: trails beam; too few rollouts at 120 CPU-s]. Same tree as 7, with rollouts that complete
   the board greedily and route it; UCT allocates effort. Source: AlphaGo,
   MCTS-based routers.
9. **Space-colonization growth** [I]. Wires grow toward "attractor" pins one step at
   a time while parts are still moving; branches merge into Steiner trees. Source:
   procedural tree generation (Runions et al.).
10. **Dungeon-generator layout** [I]. Place rooms (blocks), then carve corridors
    (bundles), then move rooms to shorten corridors. Source: procedural dungeons.

## C. Local search where routing is the cost function

11. **Annealing with incremental rip-up and reroute** [T]. Moves: shift, rotate, swap
    two same-footprint parts. Cost: unrouted connections, routed length, vias,
    computed by re-routing only nets touching the moved part. Source: VPR's
    routability-driven placement with a real router instead of a wiring estimate.
12. **Large-neighbourhood search on windows** [T: `repair`, blocker-directed]. Rip up a window (parts + copper),
    re-place and re-route it jointly, accept if better. Source: LNS in vehicle
    routing.
13. **Guided local search on blocked nets** [T: part of `repair` (A* blocker attribution)]. Each round, raise a penalty on the
    part that blocks most failed routes (from A* blocker attribution) and move it.
    Source: GLS (Voudouris), sparrow nesting.
14. **Tabu over part swaps with route reuse** [I]. Keep routes of unaffected nets;
    tabu list on part-pose pairs.
15. **Evolution strategies (CMA-ES) over poses** [I]. Fitness = fast route. Good when
    the routed cost is rugged and gradients lie.
16. **Quality-diversity archive** [I]. MAP-Elites over (board area used, via count,
    longest net); routing evaluates every elite. Source: warehouse layout QD.

## D. Continuous and physics models

17. **Elastic-band co-relaxation** [I] (the gradient agent chose soft-min paths, 22). Each net is a polyline of beads with tension
    (length) and repulsion from other nets' beads and from parts; parts are rigid
    bodies pushed by the beads that touch them. One energy, one gradient descent;
    snap to the grid at the end. Source: elastic bands in robot motion planning;
    Durbin–Willshaw elastic net.
18. **Copper as charge** [Q]. Electrostatic (ePlace) density where routed copper
    counts as charge too, so parts are pushed out of wiring channels.
19. **Harmonic-field routing** [I]. Solve Laplace's equation per net with pins as
    sources and parts as walls; streamlines of a harmonic field have no local
    minima, and streamlines of one field never cross. Part moves update the field
    cheaply (multigrid). Source: harmonic potential fields in robotics.
20. **Physarum multicommodity solver** [T: no merit as built]. Tube conductivities grow with flux and
    decay otherwise; with several commodities and shared capacity, the surviving
    tubes form a routed network. Parts feel the flux through their footprint as
    pressure. Source: slime-mould network models (Tero et al.).
21. **Homotopy continuation of clearance** [Q]. Start with zero clearance and
    shrunken footprints so everything fits, then grow both while re-solving.
    Source: continuation methods; analog "soft then hard" constraints.
22. **Soft-min Bellman–Ford** [T: gradients no better than HPWL; useful only as a global start for physics descent]. Differentiable shortest-path distances over a
    smoothed cost field give exact gradients of routed length w.r.t. obstacle
    masks, hence w.r.t. part positions via a differentiable rasterizer.
23. **Perturbed-optimizer gradients** [I]. Average the routed solution under random
    cost noise to get a smoothed, differentiable routing (Berthet et al. 2020).

## E. Structure first

24. **Tutte embedding seed** [Q]. Barycentric embedding of the part graph with
    boundary connectors pinned; for planar parts of the netlist it is crossing-free
    by construction, so it seeds placements that need few vias.
25. **Crossing-number objective** [Q]. Optimize the number of straight-line ratsnest
    crossings (a proxy for vias on 2 layers), not HPWL.
26. **Pin-direction orientation matching** [T]. Choose each part's rotation so its
    pins face the direction their routes actually leave (from idea 3), solved as an
    assignment.
27. **Planar sub-netlist layering** [I]. Split the netlist into two planar layers
    (thickness-2 graph), assign a layer per net up front, and place so both layers
    stay planar.
28. **Multigrid V-cycle** [Q]. Place and route on a 1 mm grid, refine to 0.5 and
    0.1 mm, re-solving locally at each level. Source: multigrid solvers; hierarchical
    FPGA routing.
29. **Channel reservation** [I]. Give every bundle a corridor before parts are
    final; parts may not invade reserved corridors (corridor contract, S1).

## F. Learning and language models

30. **LLM as move proposer** [T: routing inconclusive, physics no merit; use for diagnosis]. The LLM reads a rendered board with failed nets
    marked and proposes "move U3 left of J1, rotate C4" moves; the joint optimizer
    accepts or rejects them. The model never writes coordinates directly.
31. **LLM-evolved coupling policy** [I]. Evolve the rule that decides when to stop
    routing and move parts (AlphaEvolve-style), scored on held-out boards.
32. **Learned value of partial boards** [I]. Train a small CNN on (partial board →
    final routed completion) from lab runs; use it to prune beam search (7).
33. **Diffusion on joint state** [I]. Denoise placement and a coarse routing-density
    image together, then repair. Long horizon.
34. **Imitation of human routing order** [I]. Mine net order and placement order
    from git history of open boards.

## G. Other domains, mapped

35. **Factory-game solvers** [I]. Factorio/Shapez layout tools place machines and
    belts together with SAT; their trick of placing "belt bus" first maps to
    corridor-first PCB layout.
36. **Numberlink SAT windows** [T: no merit; CP-SAT windows never optimal, 0/112 wins over heuristic repair]. Exact joint solve of a small window: part pose
    variables plus path variables in one SAT/CP-SAT model.
37. **Chemical plant piping** [I]. Equipment placement and pipe routing co-optimized
    with pipe cost terms (length, bends, supports) in MILP; maps to vias and bends.
38. **Ship cable harness** [I]. Equipment and cable trays co-placed; bundles share
    trays. Maps to bus bundling.
39. **Urban co-generation** [I]. Streets and buildings generated together by tensor
    fields: a direction field sets preferred routing directions per layer and part
    orientation follows it.
40. **Microfluidic biochip co-design** [I]. Valve placement and channel routing
    solved together because channels cannot cross; same constraint as one-layer
    PCB routing.
41. **Protein side-chain packing** [I]. Discrete orientations as rotamers with
    pairwise energies including routed cost; dead-end elimination prunes poses.
42. **Origami/knot routing** [I]. Homotopy classes of nets as braids; part moves
    are braid moves that remove crossings.

## Physics in the objective (added after the first results)

43. **Physics place terms in every objective** [T: merit]. kae.physics `Terms.delta`
    (~50 µs) added to placement and annealing costs: place terms 4.05× → 1.52× human
    (`seq_phys`), 0.98× with beam search, no completion cost. HPWL alone makes boards that
    route well and are electrically wrong.

## What gets tested first, and why

Ideas 1, 2, 3, 6, 11 and 26 share the router and differ only in how placement
reacts to routing, so one engine tests them all against two controls: (a) the same
router on the human placement and (b) the same router after a conventional
HPWL-driven placement. Everything is scored by KiCad DRC on the qualified A/B
boards.
