# Untested ideas, with mechanisms

**Status:** untested idea, unless an entry says otherwise.
**First published:**
- original ideas: 2026-10-21, commit [7ac84d6](https://github.com/magnetic-trowel/kicad-auto-everything/commit/7ac84d621fa687fb17ce63f0cb1f350594fa7ee9) on `main`;
- cross-domain transplants: 2026-10-21, commit [0ea98bf](https://github.com/magnetic-trowel/kicad-auto-everything/commit/0ea98bff673d70b65a5459dcdf547046dd3fac34) on `main`;
- joint place-and-route catalog: 2026-10-24, commit [44831ff](https://github.com/magnetic-trowel/kicad-auto-everything/commit/44831ff3f802b1758b9c1299e0ae0b212d581f9a) on branch `claude/keen-wright-mlkjv6`;
- problem transformations: 2026-10-24, commit [7ae90d8](https://github.com/magnetic-trowel/kicad-auto-everything/commit/7ae90d849fd4697b32ecd76ac579b9f7d2558059) on the same branch.

This page lists ideas we wrote down but did not build, one short paragraph each, grouped by
theme. Each paragraph gives enough of the mechanism to build the idea. The full entries, with
pitch, evidence, test plan and effort, are in the source files linked under each heading.

Where part of an idea was tried, the paragraph links to the page that has the result.

**Surveys of others' work.** We also surveyed other people's approaches (about 1,700 one-line
items). Those are prior art by others, not our ideas, so they are linked rather than restated
here:
- [algorithms](../ideas/inventory-algorithms.md)
- [ecosystem](../ideas/inventory-ecosystem.md)
- [LLM, data and UX](../ideas/inventory-llm-data-ux.md)
- [practice and evaluation](../ideas/inventory-practice-evaluation.md)
- [rules: high-speed and EMI](../ideas/inventory-rules-hs-emi.md)
- [rules: power](../ideas/inventory-rules-power.md)

## Contents

- [Original ideas (58)](#original-ideas-58)
- [Cross-domain transplants (33)](#cross-domain-transplants-33)
- [Joint place and route: untested catalog ideas](#joint-place-and-route-untested-catalog-ideas)
- [Problem transformations](#problem-transformations)
- [Untested pieces of the kae line](#untested-pieces-of-the-kae-line)
- [The physics-first catalog (about 890 ideas)](#the-physics-first-catalog-about-890-ideas)

## Original ideas (58)

Source: [docs/ideas/original/](../ideas/original/README.md). The catalog's "top 10 to try first"
were P6, N8, N7, V2, V1, I4, I1+I2, R2, P1 and R1. Only two of them were tried, both in part:
V2 as a fixed suite and P1 in a discrete form.

### Intent and why (I)

Source: [intent-and-why](../ideas/original/intent-and-why.md).

- **I1 Physics budget ledger.**
  - Each design intent declares budgets: dB of loss at Nyquist, ps of skew, hot-loop inductance
    L_max = 0.2·V_DS,max/(di/dt), mounting inductance from the target impedance, crosstalk mV
    via K = 1/(1+(D/H)²), and ΔT.
  - Deterministic spend models charge every object against these budgets. A track costs dB/mm, a
    via counts as about 25–50 mm of equivalent length, and loop nH follows from loop area and
    plane depth.
  - The ledger keeps one row per budget: {budget, limit, allocation, spent, top spenders}. The LLM
    only writes `allocate(...)` calls.
  - The physics-first catalog refines this idea.
- **I2 Dimensioned constraint types.** Constraints are `Quantity(expr, dim)` values that refer to
  stackup symbols (h, Dk, w_50Ω), net facts (t_r from IBIS) and part facts. A pint-style checker
  refuses an unbound "3W" or a unitless skew. Constraints compile to mm or ps with a derivation
  trace, and re-resolve when the stackup changes.
- **I3 Why-graph.** A typed DAG runs Requirement → Mechanism (a closed catalogue of about 40) →
  Constraint/Budget → Object → Check. Its edges are requires, explained-by, enforced-by,
  realized-by and verified-by. An `impact()` query answers "what breaks if this changes".
- **I4 Constraint price tags with foils.**
  - Each binding constraint gets a price, taken from LP duals and placer multipliers, or from
    leave-one-out warm re-solves of the top k.
  - It also gets a bounded re-route without the keep-out (the "foil").
  - Output: `prices.json` holding {Δhpwl, Δvias, Δarea, Δcompletion, foil_id} per constraint.
- **I5 Criticality field.** Criticality = consequence × physics risk (length relative to t_r,
  di/dt, impedance level, RF band) × uncertainty. It drives LNS window probability, beam width,
  routing tier, simulation budget and the order of questions to the user.
- **I6 Intent diff across revisions.** Diff the persisted intent graphs on stable ids, together with
  the verdict deltas. Report the result as a pre-commit hook or a PR comment.
- **I7 Intent inside `.kicad_pcb`.** Store intent in KiCad's own objects so it survives a round trip
  through KiCad:
  - a footprint field `Intent`;
  - component classes, rule areas named `IR:...`, and groups;
  - DRU rules named `IR:<id>` with a mechanism comment;
  - a sidecar hash on a user layer.

  Reconcile on load.

### Priority agents and negotiation (N)

Source: [priority-agents-and-negotiation](../ideas/original/priority-agents-and-negotiation.md).

- **N1 Resource market.**
  - Domain agents bid, in budget units × criticality, for scarce resources: placement cells near
    anchor pins, edge segments, cut capacity, plane adjacency and BGA via sites.
  - Prices of over-subscribed resources rise, PathFinder-style, until demand clears.
  - Closest test: unified negotiated congestion of parts and wires, which partly worked
    ([negotiate](joint/jc.md)).
- **N2 Iso-physics substitutions.** A library of substitutions per mechanism, each with a computed
  iso-curve: distance ↔ parallel vias ↔ plane depth, length ↔ via balance, spacing ↔ parallel
  length ↔ h. A checker verifies that the budget is unchanged after a trade.
- **N3 Veto with proof.** An objection is {agent, check_id, measured, limit, objects, fix}. It
  counts only if a referee re-runs the check and reproduces it. Each agent may raise k objections
  per round, and rejected objections lower that agent's weight.
- **N4 Contested-rule court.** Write a one-page brief with both variants, context features and
  cheap metrics. A human rules on it, and the ruling is stored with the context vector. Later, the
  nearest precedent applies automatically.
- **N5 Reservation tokens.** Tiers (hot loops → RF → SerDes → clocks → DDR → analog → PDN → bulk)
  emit polygon reservations with slack, at soft, firm or locked confidence. A reservation hardens
  after surviving k iterations or a probe route.
- **N6 ε-lexicographic compiler.** Tiered objectives compile to sequential CP-SAT solves with bounds,
  staged penalties or barriers in the placer, and class cost ordering in routers. ε comes from the
  budgets, e.g. tier-1 loop L may use up to 90% of its budget.
- **N7 Hot-loop nH micro-placer.**
  - Detect the switching cell, then enumerate 3–6 parts × 4 rotations on a 0.25 mm grid in a
    15 mm window, with CP-SAT or DFS.
  - Minimize L_est from loop area, plane depth and via count.
  - Constraints: CIN on the IC's layer, SW copper capped, FB outside the SW/L half-plane.
  - Later physics work says to estimate loop L from height × squares, not area
    ([physics](physics/README.md)).
- **N8 Decap-to-pin assignment.** Min-cost bipartite matching (or flow) of capacitors to pins over
  sites, minimizing Σ w_pin·L_mount (pad + via + plane-depth model). Use a MILP when the PDN target
  couples the choices, and screen candidates with a lumped Z(f) ≤ Z_t. padne is DC-only, so it
  cannot validate this.
- **N9 Ordered-chain embedder.** Lay a centerline from connector to IC. Place the chain parts as
  ordered stations along it, by DP over stations plus CP-SAT spacing. Rules: no via or stub before
  the TVS, AC caps at one end, matching at the pin.

### Placement (P)

Source: [placement](../ideas/original/placement.md). The ids here are not the P0–P7 ids of
[strategy-candidates](../topics/placement/strategy-candidates.md).

- **P1 Router-probe pseudo-gradients.**
  - Every k steps, legalize a snapshot and run a fast router.
  - Blocked nets push their blockers perpendicular to the corridor. Overflowing cuts inflate local
    density. Pin sides that cross suggest rotations.
  - Forces decay over time, and a per-board online linear surrogate learns from the probes.
  - **Partial:** the discrete form was tried twice: blame-driven re-annealing
    ([ap-sa-loop](placement/autoplace.md)) and blocker-directed window repair
    ([blocker-repair](joint/anneal-and-repair.md)). The continuous-force version is untested.
- **P2 Contracted floorplan with a cut check.**
  - Blocks become soft macros with area, aspect variants and port contracts, floorplanned by
    CP-SAT or a slicing GA.
  - A SURF-style cut test compares demand with capacity (cut length × layers / pitch).
  - Overflowing cut lines go back to the LLM.
  - Cut-capacity bounds as layer predictors did not work ([collapse-obst](joint/layer-collapse-analysis.md)),
    but that is a different use.
- **P3 Physics-slack templates.** Store a relative-pose program plus, for each part, the slack
  region found by sampling perturbations that keep every budget. Linearize the regions to boxes or
  ellipses for the placer and legalizer.
- **P4 Side assignment by graph cut.** Give each part a binary side variable:
  - unary terms: tall, heavy and THT parts on top; heat-sunk parts on the bottom;
  - pairwise terms: must-same and prefer-opposite.

  Solve with an s-t min-cut, plus CP-SAT for the remainder, both with and without a cost for using
  the bottom side.
- **P5 Verified motif distributions.** Canonicalize satellite parts into their anchor IC's frame.
  Fit a Gaussian mixture per (anchor family, pin function, package, layer count) on DRC-clean open
  boards, and use −log p as a weak prior. The data step exists as measured decap priors
  ([measured-priors](../topics/data/measured-priors.md)).
- **P6 Slot assignment.** Group parts into interchange classes (same footprint, same role,
  swappable pins). Run a Hungarian assignment per class on HPWL + crossings + budget spend, and
  iterate to a fixed point. Pin swaps are proposals.
- **P7 Live topological sketch objective.** Keep Toporouter-style topological routes up to date on
  every move. The objective is sketch length + λ·cut overflow + critical crossings. The closest
  test is the lifted layer-collapse cost as a placement measure, which ranked placements at ρ 0.85
  vs 0.51 for HPWL ([collapse-assign](joint/layer-collapse-analysis.md)).
- **P8 Connector-voltage EMI proxy.** V_ab ≈ Σ I_k·2πf_k·L_plane·g(d_k) between cabled
  connectors, with softplus(V_ab − V_budget) as a differentiable placer loss.
- **P9 Pin-mux co-floorplanning.** Solve the pin-mux CSP from vendor tables jointly with IC
  rotation in CP-SAT. The geometry cost scores pin side against block direction, plus crossings.
- **P10 Variant-robust placement.** Use the union of the alternates' courtyards and worst-case
  budgets, priced per slot.

### Routing (R)

Source: [routing](../ideas/original/routing.md).

- **R1 Homotopy menus.** Build a CDT per layer. For each critical net, find the k ≈ 3–5 shortest
  non-homotopic rubber-band paths, each summarized by length, vias, cut loads and a plain-words
  note. The LLM picks one, a joint SURF check validates the picks, and the waypoints go to KiCad's
  PNS router.
- **R2 Shadow return nets.** A virtual net is the projection of a signal onto its reference plane,
  within ±3h. Voids and splits under it are forbidden, and a layer change requires a stitching via
  or cap within d_max. The physics-first catalog generalizes this.
- **R3 Joint signal and return via sites.** Model typed via-site nodes in a flow or SAT escape
  model, with a return via within d_max of every signal via that changes reference. An UNSAT core
  becomes a menu of ECOs.
- **R4 Regret-driven priorities.** Route each of the top N nets alone. Regret is the actual spend
  minus the solo spend, and the culprits are the nets on the solo path. Apply bounded
  re-prioritization.
- **R5 Router-portfolio bandit.** Context (net class, density, region) × arms (engine × preset),
  with Thompson sampling and a lexicographic reward. A fixed restart portfolio, which is not a
  bandit, worked ([restart-portfolio-and-budgets](routing/kae-restart-portfolio.md)).
- **R6 Verified routing macros.** A macro is a precondition, stackup-derived parameters, a
  deterministic generator and postconditions. The LLM picks macros from a menu.
- **R7 Plane-partition synthesis.** Assign grid cells × plane layers to rails, with penalties for
  IR drop, fast-corridor crossings and slivers.
- **R8 Physics-scored PNS beam search.** Run a beam over PNS checkpoints (waypoint shifts, layer,
  walkaround or shove, via candidates), scored by ledger spend and shadow-return feasibility.

### System loop (S)

Source: [system-loop](../ideas/original/system-loop.md).

- **S1 Corridor contract.** The LLM bundles nets. A min-cost multicommodity flow assigns bundles to
  corridors and layer pairs. The placer (as soft keep-outs), the legalizer and the routers all
  honour the contract.
- **S2 Decision DAG and bisect.** Log every decision and keep a content-addressed solver cache.
  Replay on edit, and binary-search over decision prefixes to find regressions.
- **S3 Priced ECO menu.** Turn an infeasibility certificate into candidate ECOs, each evaluated by
  window re-solve and BOM, area or layer cost, offered in the order experts escalate.
- **S4 Predict before check.** Every tool call carries a prediction, scored by Brier or absolute
  error. A surprise forces a written diagnosis, and calibration gates the level of autonomy.
- **S5 Refactoring operators.** A layout edit has a precondition, a rigid transform, then
  re-tighten, re-legalize and postconditions. A script rolls back on failure.
- **S6 Successive halving.**
  - Push N placements × router presets through rungs: T0 metrics → a 1 s router → a short
    Freerouting run → full route + DRC + SI.
  - Keep the top 1/η at each rung, with MAP-Elites niches.
  - **Partial:** best-of-N ranked by in-loop DRC reached 12/14 ([ap-sa-best](placement/autoplace.md)).
    A QD archive did not beat `jc` ([qd-archive](joint/jc-extensions.md)).

### Verification (V)

Source: [verification](../ideas/original/verification.md).

- **V1 Mutation-tested layout checks.** A check maps (board, intent) → verdict. Mutate the actual
  board: move a part across a threshold, flip a side, insert a via before the TVS, delete a
  stitching via, skew a leg, narrow a neck. Accept a check only above a mutation score and with no
  false positives on compliant perturbations.
- **V2 Red-team reward-hacker gate.**
  - A sandboxed agent with the scorer API tries forbidden outcomes: plane shorts, deleted nets,
    relaxed rules, ignored severities, net-tie abuse, off-board copper, edits to locked parts and
    hidden layers.
  - Optimization starts only once it finds no new hack.
  - **Partial:** a fixed, hand-written red-team suite guards the benchmark
    ([redteam_cheats.py](../../bench/tests/redteam_cheats.py)). There is no adversarial agent.
- **V3 Judge licensing.** Give each judge per-category exams with seeded faults. License it at
  recall ≥ R and precision ≥ P, and re-examine on every model change.
- **V4 Proxy trust radius.** Fit the region where each proxy (loop nH, K, V_ab, thermal) agrees
  with high-fidelity simulation. Scores outside that region do not count.
- **V5 Counterexample-guided rules (CEGAR).** A failure prompts an LLM-written check tied to a
  mechanism. The check must fire on the counterexample, stay at or below f false positives on N
  passing boards, and meet the V1 mutation score.

### Learning and data (L)

Source: [learning-and-data](../ideas/original/learning-and-data.md).

- **L1 Planted-solution boards.** Compose boards from verified recipe blocks and route them fully,
  then strip and perturb them. The reward is the gap to the planted reference, which is not an
  optimum. Difficulty is adjustable.
- **L2 Evolve the conductor.** An LLM mutates an orchestration-policy DSL under AST checks. Policies
  are evaluated in a cascade, from synthetic boards through the benchmark splits, with MAP-Elites
  and a negative memory.
- **L3 Inverse optimization from edits.** Classify each designer edit. Solve the local inverse
  problem for the smallest Δweights that would make the human result better, and store the edit as
  a preference pair.
- **L4 EVM layouts as extraction oracle.** Run predicates extracted from datasheets on the vendor's
  own evaluation layouts. A disagreement means re-extract or flag.
- **L5 Git-history repair pairs.** Take a semantic diff of consecutive `.kicad_pcb` commits whose
  messages look like fixes. Critics label the before and after. The [board corpus](data/board-corpus.md)
  pins single commits only.
- **L6 Fab-query memory.** Extract issues from fab engineering queries into intent and fab-profile
  updates, doc checks and a precedent store.

### Workflow and UX (U)

Source: [workflow-ux](../ideas/original/workflow-ux.md).

- **U1 Physics HUD.** Poll KiCad's IPC API at about 5 Hz, recompute the cheap checks for the
  intents an edit touches, and show them in a side panel.
- **U2 Intent locks vs geometry locks.** Lock what must hold, such as a loop budget, not where a
  part sits.
- **U3 Expected-loss brief.** Ask the user only the top 5–10 questions, ranked by
  (1 − confidence) × consequence × rework cost.
- **U4 Budget-slider Pareto explorer** over a quality-diversity archive.
- **U5 Semantic ratsnest.** Style the ratsnest by intent, with bundled buses and return-path
  ghosts. The render style is a hyperparameter of any visual judge.
- **U6 Sketch to intent.** A VLM plus a stroke classifier turns sketches into intent. Hit-testing is
  deterministic.
- **U7 Intent-level merge.** Merge branches by taking the union of their intent graphs, and write a
  brief for each conflict.

## Cross-domain transplants (33)

Source: [cross-domain-transplants](../ideas/cross-domain-transplants.md). These are other fields'
methods; the PCB mapping and the ranking are ours. The source table links the topic doc behind
each.

1. **Placement program with LLM-free repair** (scene programs). Footprints expose `.min`, `.max`,
   `.center`, `.facing`, `.side` and pin handles. The program uses `set_frame(U1)`, `row` and
   `ring` with shared variables. Greedy local search repairs it by rewriting constants and 90°
   directions, minimizing loss + edit distance to the program + area-weighted transport.
2. **Numeric poses with self-consistent relations and projected gradient** (LayoutVLM). Keep only
   the relations that the LLM's own rough poses satisfy. Use a DIoU courtyard loss, project into
   the outline, and re-render group by group.
3. **VLM region proposals as weak anchors or KiCad rooms** (VeoPlace). Propose regions per block,
   with an anchor weight calibrated by sweep against a random-region control.
4. **Render, then a pairwise VLM judge** listing pros and cons. Rank N candidates, and keep a library
   of verified subcircuit macros.
5. **Overlap-elimination legalizer** (sparrow/jagua-rs nesting). Overlaps are allowed during search.
   Guided-local-search pair weights drive the overlaps out, in an exploration phase then a
   compression phase, with a displacement-to-target term.
6. **HOLA core/tree layout with IPSep-CoLa separations.** Place 2-core ICs by constrained stress and
   degree-1/2 peripherals symmetrically outside. Signal flow and containment become hard separation
   constraints.
7. **Polygon-partition MCTS global router.** Partition the board by extending pad edges into
   polygons, run MCTS over polygon sequences, and re-partition after each net. An LLM gives the PUCT
   prior and the net order. Tried in a related form: MCTS did not work at our budget
   ([mcts](joint/tree-search.md)).
8. **LLM-evolved heuristics** (FunSearch/AlphaEvolve). Evolve PathFinder costs, net and placement
   order, repair neighbourhoods and legalizer schedules, through an evaluation cascade with a
   restricted API.
9. **Quality-diversity portfolio with legalizer repair.** MAP-Elites over area, sidedness, flow
   straightness and thermal spread, with LLM mutation operators. Tried: no gain over `jc`
   ([qd-archive](joint/jc-extensions.md)).
10. **Netlist-conditioned diffusion placer.** Train on synthetic random legal placements whose pad
    nets connect with p ∝ exp(−l/s), using a GNN plus attention denoiser. Constraints are
    composable energy potentials with dual ascent, plus recycling and inpainting.
11. **Silkscreen reference designators by map labelling.** Generate candidate label positions, build
    a conflict graph (pads, vias, labels, edges), and solve with SA or MaxSAT/ILP. The `kae` placer
    has a related silk pass ([placement](placement/README.md)).
12. **Sequence-pair completion of LLM relations.** Turn left-of and below relations into a partial
    sequence pair, complete it if the relations are acyclic, and decode by longest path into a
    non-overlapping placement. Anneal the rest, with the LLM's order as a hard precedence.
13. **Dead-end elimination for orientation and side states** (protein design). Rotation × side ×
    offset states play the role of rotamers, with pairwise wirelength, crossing and conflict
    energies, and provable pruning.
14. **Homotopy-first routing with LLM topology hints.** The LLM states which side of each obstacle a
    net passes. A SURF cut check validates the plan, rubber bands realize it, and the topology
    persists for re-tightening.
15. **LLM as a MAPF meta-controller.** The LLM sets priorities, conflict branches, yielding nets and
    per-class costs, while CBS or PathFinder compute the paths. Our grid router uses PathFinder
    without an LLM ([pnr-engine](joint/engine.md)).
16. **ASP/WFC for tiled regions.** Enumerate valid tilings for key matrices, LED arrays and
    multichannel blocks. clingo flags contradictions, order cycles and over-subscribed edge slots.
17. **SAT/ZDD local windows.** Solve escape and fan-out windows exactly, with vias as bridges, and
    let a ZDD enumerate the alternatives. Tried as exact CP-SAT windows: no merit
    ([cpsat-windows](joint/anneal-and-repair.md)).
18. **Stakeholder critic agents.** PI, SI, thermal, DFM and mechanical critics advise, and a planner
    revises.
19. **Template retargeting of reference layouts.** Extract orders, alignments and spacing variables
    from a datasheet or past layout, then re-run them as a placement program with the new
    footprints.
20. **Domain subroutines:**
    - package pin assignment;
    - frequency repulsion;
    - DME plus multicommodity-flow length matching;
    - harness bundling;
    - bend-aware A*;
    - tensor-field direction fields;
    - Pareto thermal SA.
21. **Anchor-first DFS baseline.** Place connectors and holes, then the MCU, then the rest on a
    courtyard grid, for boards under 50 parts.
22. **Hierarchical support regions** (board → block rooms → IC neighbourhoods → pin slots), with
    few-shot motifs such as "2 caps + ferrite on VDDA".
23. **Planner–auditor board plan.** Plan blocks, relations and rough boxes, and audit them as text
    and visually before placement.
24. **Render style as a hyperparameter.** For VLM inputs, use orthogonal ratsnest previews,
    labelled reference designators and net-class colours.
25. **Collision discriminator** to rerank generative samples.
26. **MCTS over coarse placement decisions with an LLM prior.** The tree decides block-to-region,
    side and major IC orientation; rollouts are a fast placer plus a routability preview. Related
    result: [mcts](joint/tree-search.md).
27. **PIBT/LaCAM first routing for dense fan-out,** treated as dense multi-agent path finding, then
    improved by CBS or rip-up.
28. **Metric histograms.** Show area, vias, length, worst decap distance and crossings against prior
    boards or a QD archive.
29. **Unequal-area facility layout for block floorplanning.** The LLM supplies the flow matrix and
    area estimates; a slicing-tree GA or MIP solves.
30. **Metro-map MIP bus schematization.** Snap long bus runs to 0/45/90°, with hard spacing and
    soft bends.
31. **Sugiyama/ELK seeding.** The signal-flow layer index gives the x order. libavoid connector
    routing gives a cheap crossing metric.
32. **Rigid-flex panel assignment** as constrained bin assignment, with no rigid parts at folds.
33. **SAT/SMT local + MAPF routing + annealing placement** as an architecture check.

## Joint place and route: untested catalog ideas

Source: the 42-idea catalog
[docs/ideas/original/joint-pnr.md](https://github.com/magnetic-trowel/kicad-auto-everything/blob/claude/keen-wright-mlkjv6/docs/ideas/original/joint-pnr.md)
on branch `claude/keen-wright-mlkjv6`, and its
[literature survey](https://github.com/magnetic-trowel/kicad-auto-everything/blob/claude/keen-wright-mlkjv6/research_notes/joint-pnr/literature-survey.md).
The tested ideas (1–3, 6–8, 11–13, 16, 17, 19, 20, 22, 23, 26, 30, 32, 36, 43) have pages in the
[joint area](joint/README.md); 17 and 23 were folded into the differentiable-routing test
([soft-route-grad](joint/forces-and-fields.md)). The untested ones are below.

- **4 Congestion game.** Parts and nets are selfish players in a potential game. Iterate best
  responses to a Nash equilibrium. This is the same mechanics as negotiated congestion without
  global prices, so it tests whether prices matter.
- **5 Auction for board area.** Parts bid for grid regions with budgets set by net criticality,
  using Bertsekas' auction algorithm, which reaches an ε-optimal assignment.
- **9 Space-colonization growth.** Wires grow one step at a time toward attractor pins while the
  parts still move. Branches merge into Steiner trees.
- **10 Dungeon-generator layout.** Place rooms (blocks), carve corridors (bundles), then move the
  rooms to shorten the corridors.
- **14 Tabu search over part swaps with route reuse.** Keep the routes of unaffected nets, and keep
  a tabu list on (part, pose) pairs.
- **15 CMA-ES over poses,** with a fast route as the fitness function. Suited to rugged routed
  cost, where gradients mislead.
- **18 Copper as charge.** In an ePlace-style electrostatic density, routed copper counts as charge,
  so it pushes parts out of wiring channels. Only the overflow-pushes-pads part exists, inside
  [soft-route-grad](joint/forces-and-fields.md).
- **21 Homotopy continuation of clearance.** Start with zero clearance and shrunken footprints so
  everything fits. Grow both while re-solving.
- **24 Tutte embedding seed.** Use a barycentric embedding of the part graph with the boundary
  connectors pinned. It is crossing-free on planar sub-netlists, so it seeds placements that need
  few vias.
- **25 Crossing-number objective.** Minimize straight-line ratsnest crossings instead of HPWL, as a
  proxy for vias on two layers. Tried only as a term inside other objectives
  ([collapse-cplace](joint/layer-collapse-analysis.md), [ap-crossing-halo-ablation](placement/autoplace.md)).
- **27 Planar sub-netlist layering.** Split the netlist into two planar layers (a thickness-2 graph),
  assign each net a layer up front, and place so that both layers stay planar.
- **28 Multigrid V-cycle.** Place and route on a 1 mm grid, then refine to 0.5 mm and 0.1 mm,
  re-solving locally at each level.
- **29 Channel reservation.** Give every bundle a corridor before the parts are final; parts may not
  invade it. This is the corridor contract, S1.
- **31 LLM-evolved coupling policy.** Evolve the rule that decides when to stop routing and move
  parts, AlphaEvolve-style, scored on held-out boards.
- **33 Diffusion on the joint state.** Denoise the placement and a coarse routing-density image
  together, then repair.
- **34 Imitation of human routing order.** Mine net order and placement order from the git history
  of open boards.
- **35 Factory-game solvers.** Lay the "belt bus" first, as Factorio and Shapez tools do, which maps
  to corridor-first PCB layout.
- **37 Chemical plant piping.** Co-optimize equipment placement and pipe routing in a MILP with
  length, bend and support costs, which map to vias and bends.
- **38 Ship cable harness.** Co-place equipment and cable trays, with bundles sharing trays. Maps to
  bus bundling.
- **39 Urban co-generation.** A tensor direction field sets the preferred routing direction per
  layer, and part orientation follows it.
- **40 Microfluidic biochip co-design.** Valve placement and channel routing are solved together
  because channels cannot cross, which is the same constraint as one-layer PCB routing.
- **41 Protein side-chain packing.** Discrete orientations are rotamers, with pairwise energies that
  include routed cost. Dead-end elimination prunes poses.
- **42 Origami and knot routing.** Homotopy classes of nets are braids, and part moves are braid
  moves that remove crossings. A literature review found no merit.

## Problem transformations

Source:
[research_notes/transformations/transformations.md](https://github.com/magnetic-trowel/kicad-auto-everything/blob/claude/keen-wright-mlkjv6/research_notes/transformations/transformations.md)
on `claude/keen-wright-mlkjv6`. Each entry there gives the mapping, known results, what breaks,
the payoff, a test plan and a novelty note. Three of them were built and run:
- T1, min-plus best-response maps: [minplus-maps](joint/jc-extensions.md);
- T2, exact Green's-function physics maps: [exact-physics-maps](joint/jc-extensions.md);
- T4, pour-damage maps: [pour-damage-maps](joint/pour-models.md).

The rest:

- **T3 Coupling as an additive A\* edge cost.**
  - Compute the aggressors' vector potential A = G ⊛ J over a plane, with kernel
    (μ0/4π)·ln(1 + (2h/s)²).
  - |A·dl| along a candidate path bounds the mutual inductance, so coupling becomes an edge cost.
  - This was ranked 4th of the transformations.
- **T5 Satellite assignment.** Assign decaps and pull-ups to tiled slots around each IC by exact
  Hungarian matching on a separable Σ1/L_i cost, with Frank–Wolfe steps across groups.
- **T6 Homotopy class in the A\* state.** Carry the H-signature (a free-group word) in the A\* state
  to get per-class route alternatives.
- **T7 Legalization as optimal transport,** minimizing total displacement.
- **T8 LPA\*/D\* Lite incremental re-routing** after annealing moves.
- **T9 Frustrated plaquettes → via-forcing map.** Find the places where vias are forced by
  min-weight matching in the dual graph.
- **T10 Lindström–Gessel–Viennot / Fomin determinant** as a one-layer routability score.
- **T12 Parametric min-cut** for splitting a region between two pours.
- **Tested in notes only, dropped:**
  - T11, extremal-length bounds on pour resistance: exact on rectangles but 2–200× loose on
    perforated pours;
  - DCT-preconditioned CG on masked pours: did not converge.

  Also checked and dropped without tests: braids, knots, Noether, Koopman, a tropical reading of
  `jc`, Minkowski sums, steerable filters, eikonal, Radon, Morse, spectral/SOS/QUBO and sheaves.

## Untested pieces of the kae line

These were built on branch `claude/vigilant-mayer-i91rrr` but never measured.

- **Free part angles.**
  - `kae place --angles STEP` lets parts take any multiple of STEP degrees in the annealer.
    Heatsink-mount packages keep right angles, and CP-SAT stays on right angles.
  - `tools/research/place/anglepolish.py` is the paired test. Both arms start from the same
    finished legal placement and get the same number of low-temperature moves (geometric
    schedule T0·hot → T0·1e-4, final legality weight, same seed), scored on HPWL and the physics
    scorecard.
  - There is no recorded paired result. Off by default.
  - First appeared in [6a32272](https://github.com/magnetic-trowel/kicad-auto-everything/commit/6a322723ca7e85f6136de3655071a9c132c2b163) and [e171267](https://github.com/magnetic-trowel/kicad-auto-everything/commit/e171267e73ad11b230df15ac32a9ef9e2e832be0), 2026-10-23.
- **Edge-mate.** Footprints that carry Edge.Cuts (edge connectors, cut-outs) are placed by mating
  their outline segments to the board outline (`kae/src/kae/place/edges.py`, `--edge-mate`). It is
  implemented and off by default. The six outline-incomplete tasks stayed held out, so there is no
  result. First appeared in [1120fc0](https://github.com/magnetic-trowel/kicad-auto-everything/commit/1120fc039a1dbb970fe7f05bfe731f6513094e5d), 2026-10-22.

The tested parts of this line are in the [routing](routing/README.md),
[placement](placement/README.md), [joint](joint/README.md) and [physics](physics/README.md)
areas.

## The physics-first catalog (about 890 ideas)

[docs/ideas/physics-first/](https://github.com/magnetic-trowel/kicad-auto-everything/tree/claude/vigilant-mayer-i91rrr/docs/ideas/physics-first)
on branch `claude/vigilant-mayer-i91rrr` holds about 890 ideas: about 660 in eleven theme files
and 232 in seven first-principles lens files. The themes are:
- rule replacements, a design language, reasoning and joint place-route;
- optimization and simulation;
- power, SI/EMI/RF, and thermal, high-voltage and manufacturing;
- critics and cross-domain transplants.

They build on the original ideas above (I1, N7, N8, R2, V1, V2) without repeating them. Everything
in that catalog is untested unless a number in it is tagged [C] (computed by us). The computed
parts are written up in the [physics area](physics/README.md). This page does not repeat the
catalog.
