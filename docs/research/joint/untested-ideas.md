# Untested ideas for joint place-and-route

**Status:** untested ideas (two had quick numeric checks in the notes, both weak).
**First published:** 2026-10-24, commits [44831ff](https://github.com/magnetic-trowel/kicad-auto-everything/commit/44831ff3f802b1758b9c1299e0ae0b212d581f9a) (catalog) and [7ae90d8](https://github.com/magnetic-trowel/kicad-auto-everything/commit/7ae90d849fd4697b32ecd76ac579b9f7d2558059) (transformations) on branch `claude/keen-wright-mlkjv6`.

Ideas written down with enough mechanism to build, but never run. Two sources: the
[42-idea catalog](../../ideas/original/joint-pnr.md) (ideas without a test) and the transformation notes
[transformations.md](../../../research_notes/transformations/transformations.md) (T3, T5–T12; T1, T2 and
T4 were tested, see [jc-extensions.md](jc-extensions.md) and [pour-models.md](pour-models.md)). Each
entry below is short; the source has the mapping, known results, what breaks, payoff and a test plan.

## Transformations (from the transformation notes)

- **T3 Routed coupling as an additive A* edge cost.** Mutual inductance between a victim route P and
  aggressor currents is M = ∫_P A·dl with A = G ⊛ J the aggressors' vector potential; for traces over a
  plane the per-length kernel is K(s) = (μ₀ / 4π) · ln(1 + (2h / s)²) (image derivation). M is additive
  over path edges, and |A·dl| is a non-negative edge cost that upper-bounds |M| and fits A* exactly.
  Recompute A per PathFinder iteration by one FFT per aggressor class; add w · |A·dl| to the cost of
  nets marked victim. Ranked 4th of the transformations. Aims at the weak link between fast and routed
  physics (Spearman 0.55).
- **T5 Satellite parts by exact assignment.** Tile a ring of candidate slots around each IC from its
  legal map; cost c(part, slot, rotation) from exact physics maps. For a parallel decap group,
  minimizing (Σ 1 / L_i)⁻¹ is maximizing Σ 1 / L_i, which is separable, so a Hungarian matching is exact
  per group; across groups, linearize φ (a Frank–Wolfe step) and re-solve. Run after jc's legalization.
- **T6 Homotopy class as a free-group word.** A connection's class relative to the k ≤ 3 nearest large
  parts is a reduced word read from signed ray crossings (H-signature). Adding the word to the A* state
  gives the best route per class, so jc could pick "around the part" instead of a via at its
  highest-history conflicts.
- **T7 Legalization as optimal transport.** Replace jc's greedy nearest-legal snap with a min-cost
  assignment of overlapping parts onto legal sites (least Σ |Δx|²), then repair pairwise conflicts. Small
  expected payoff.
- **T8 Incremental shortest paths for re-route-per-move annealing.** After a move only edges near the
  old and new footprint change; LPA* / D* Lite repair the search tree. First measure the fraction of
  changed search nodes per move.
- **T9 Frustrated plaquettes as a via-forcing map.** In the planar Ising form of layer assignment, a face
  of the conflict graph with an odd number of "must differ" edges is frustrated; a minimum-weight perfect
  matching of frustrated faces in the dual gives the forced domain walls, i.e. vias. Use the map to steer
  jc restarts, not as a cost term.
- **T10 One-layer routability as a determinant.** With M_ij the walk-generating Green's function from
  source i to sink j ((I − zA)⁻¹ over free cells), det M counts non-intersecting path systems when the
  boundary order allows only the identity (Lindström–Gessel–Viennot; Fomin for loop-erased walks).
  log det is a smooth escape / bus capacity score.
- **T12 Two-pour splits by parametric min-cut.** A two-pour split is a submodular binary labelling;
  graph cuts are exact and one parametric max-flow gives all area multipliers. Low value, since minimal
  boundary is the wrong objective for pours.
- **T11 Extremal-length bounds on pour resistance** (checked numerically in the notes: exact on a
  rectangle, but 2–200× loose on perforated pours; dropped in favour of T4). **DCT-preconditioned CG on
  masked pours** (checked: no convergence in 2,000 iterations at 10⁻⁴ contrast; use sparse LU).
- **Checked and dropped by argument:** braid groups for collapse (only monotone two-row buses are braids,
  already covered by RSK), knot diagrams and gauge views of layers, Noether symmetry, Koopman lifts, jc as
  a tropical / RG flow, Minkowski sums (the FFT legal map already is the C-space convolution), steerable
  filters, eikonal any-angle routing, Radon transforms of demand, Morse / persistence channel widths,
  spectral / SOS / QUBO placement, sheaf cohomology. Reasons per line in the notes.

## Catalog ideas without a test (from the 42-idea catalog)

Numbers are catalog ids.

- **4 Congestion game.** Parts and nets as selfish players in a potential game, iterating best responses
  to a Nash equilibrium: `negotiate` without global prices, to test whether prices matter.
- **5 Auction for board area.** Parts bid for grid regions with budgets set by net criticality
  (Bertsekas auction; ε-optimal assignment).
- **9 Space-colonization growth.** Wires grow one step at a time toward attractor pins while parts still
  move; branches merge into Steiner trees (procedural tree generation).
- **10 Dungeon-generator layout.** Place rooms (blocks), carve corridors (bundles), then move rooms to
  shorten corridors.
- **14 Tabu search over part swaps with route reuse.** Keep the routes of unaffected nets; tabu list on
  (part, pose) pairs.
- **15 CMA-ES over poses.** Fitness = fast route; for rugged routed costs where gradients mislead.
- **17 Elastic-band co-relaxation.** Each net a polyline of beads with tension and repulsion from other
  nets and parts; parts are rigid bodies pushed by the beads; one energy, one descent, snap at the end.
- **18 Copper as charge.** ePlace electrostatic density in which routed copper is charge too, pushing
  parts out of wiring channels (partly inside `grad`, see [forces-and-fields.md](forces-and-fields.md)).
- **21 Homotopy continuation of clearance.** Start with zero clearance and shrunken footprints so all
  fits, then grow both while re-solving.
- **23 Perturbed-optimizer gradients.** Average the routed solution under random cost noise for a
  smoothed differentiable router (Berthet et al. 2020).
- **24 Tutte embedding seed.** Barycentric embedding of the part graph with connectors pinned;
  crossing-free for planar sub-netlists, so a low-via seed.
- **25 Crossing-number objective.** Minimize straight-line ratsnest crossings instead of HPWL (tested only
  as a proxy term in [layer-collapse-analysis.md](layer-collapse-analysis.md), no merit there).
- **27 Planar sub-netlist layering.** Split the netlist into two planar layers up front, place so both
  stay planar.
- **28 Multigrid V-cycle.** Place and route on 1 mm, refine to 0.5 and 0.1 mm, re-solving locally.
- **29 Channel reservation.** Reserve a corridor per bundle before parts are final; parts may not invade.
- **31 LLM-evolved coupling policy.** Evolve the rule that decides when to stop routing and move parts,
  scored on held-out boards.
- **33 Diffusion on joint state.** Denoise placement and a coarse routing-density image together, then
  repair.
- **34 Imitation of human routing order.** Mine net and placement order from the git history of open
  boards.
- **Other-domain transplants (35, 37–42).** Factory-game layout (belt bus first → corridor-first PCB),
  chemical-plant piping MILP (length, bends, supports → vias, bends), ship cable trays (bus bundling),
  urban tensor-field co-generation (a direction field per layer sets routing directions and part
  orientation), microfluidic biochips (no crossings = one-layer routing), protein side-chain packing
  (rotamers with pairwise routed energies, dead-end elimination), origami / knot routing (no merit by
  literature review, [analogs.md](../../../research_notes/layer-collapse/analogs.md)).

Literature mechanisms for many of these: [literature-survey.md](../../../research_notes/joint-pnr/literature-survey.md).

## Related

[README.md](README.md), [scorecard.md](../../ideas/original/scorecard.md).
