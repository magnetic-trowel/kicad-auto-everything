# Original ideas: the coupled placement–routing loop and LLM orchestration

Part of the [original-ideas catalog](README.md). Shorthands as in [intent-and-why](intent-and-why.md). These ideas are about how the stages hand work to each other, how the LLM's decisions are recorded and replayed, and how the loop decides where to spend effort. The end-to-end assemblies are in [hybrid-architecture-options](../../topics/architecture/hybrid-architecture-options.md).

---

## S1. Corridor contract between placement and routing — *novel combination*

**Pitch.** Make the hand-off from placement to routing an explicit, checkable contract: bundles assigned to corridors and layers, with capacities. The placer must leave room for the contract, and the routers must honour it.

**Mechanism.**
1. The LLM groups nets into bundles (bus lanes, pairs, power trunks) and sets their priorities.
2. A min-cost multicommodity flow over the block channel graph ([P2](placement.md#p2-contracted-soft-macro-floorplan-with-cut-capacity-check--novel-combination)) assigns each bundle to a corridor and a layer pair within capacity.
3. Contract = {bundle, corridor polygon, layers, capacity used, reserved meander slack}.
4. How each engine uses it:
   - the placer treats corridors as soft keep-outs (density inflation);
   - the legalizer makes them hard for high-priority bundles;
   - routers receive corridor rule areas plus preferred-direction cost biases.
5. A violation is reported against whichever side broke the contract.

**Why it should work.**
- Humans plan top-down while autorouters work bottom-up, one connection at a time ([autorouter-skepticism](../../topics/routing/autorouter-skepticism.md)).
- Experts escape and reserve whole buses, and leave channels between memories ([sub-workflows](../../topics/workflow/sub-workflows-power-bga-ddr.md)).
- Bundling and capacity-mesh routing have precedents ([cross-domain-routing-transplants](../../topics/routing/cross-domain-routing-transplants.md)).

**Builds on.** alg#148, alg#250, alg#302; prac#28, prac#67; [N5](priority-agents-and-negotiation.md#n5-reservation-tokens-with-confidence-hardening--new).

**How to test.** Route 15 multi-bus boards with and without the contract. Metrics: completion, bus crossings and length spread, number of re-place iterations.

**Effort/risk.** M. A rigid contract can trap the design; allow renegotiation through [N1](priority-agents-and-negotiation.md#n1-domain-agents-in-a-resource-market--new).

---

## S2. Decision DAG with deterministic replay and decision bisect — *new*

**Pitch.** Record every LLM decision (side, region, relation, topology, relaxation, engine choice) as a node in a DAG. Geometry is a deterministic function of the decisions. Any alternative is then a cheap replay, and any regression can be bisected to the decision that caused it.

**Mechanism.**
- **Log entry:** {id, parent, type, payload, rationale ids}.
- **Caching:** solver runs are content-addressed by (decision-prefix hash, seeds, tool versions).
- **Branching:** edit a decision, and replay recomputes from the first stage that depends on it. Stages declare their dependencies.
- **Bisect:** given a PRC regression between two states, binary-search the decision prefixes, replaying from cache, until the culprit decision is found. Report it to the LLM and the user.

**Why it should work.**
- Determinism and recorded seeds and versions are trust requirements ([trust-requirements](../../topics/workflow/trust-requirements.md), [agent-tooling-reliability](../../topics/ux/agent-tooling-reliability-patterns.md)).
- Persisted relations re-solve reliably ([interfaces](../../topics/llm/interfaces-relations-vs-coordinates.md)).
- Experts already work with a git commit per state ([expert-state-machine](../../topics/workflow/expert-state-machine.md)).

**Builds on.** llm#326, llm#353, llm#427; prac#4, prac#204.

**How to test.** Seed 30 regressions into long agent sessions. Measure bisect accuracy and the number of replays it needs. Compare the cost of branching with a full re-run.

**Effort/risk.** M. Nondeterministic engines break replay, so force Freerouting `-mt 1`. Freerouting has no seed flag (it seeds `Random(0)` internally), and whether `-mt 1` makes it deterministic is untested: check board hashes over repeated runs before relying on recomputation, and replay from the cache.

---

## S3. Infeasibility to priced ECO menu — *novel combination*

**Pitch.** Turn every "impossible" signal into one menu of priced engineering changes for the LLM to rank and a human to approve. Signals include CP-SAT infeasible subsets, SURF cut overflow, escape UNSAT cores and budget overspend. Changes include relax, substitute, pin-swap, repackage, add a layer pair, enlarge the board, and move a connector.

**Mechanism.**
1. A rule table maps each infeasibility certificate to candidate ECOs.
2. Each candidate gets a quick evaluation: re-solve the affected window or cut, then compute the BOM delta, layer and area cost, schedule risk and budget impact.
3. The menu follows the experts' escalation order: local moves → re-floorplan → repackage, add layers or enlarge → drop a function → ask a human.

**Why it should work.**
- Experts escalate in exactly this fixed order ([expert-state-machine](../../topics/workflow/expert-state-machine.md)).
- An escape solver that says "impossible" is valuable stackup feedback ([escape-routing](../../topics/routing/escape-routing.md)).
- Legalizers should report infeasible subsets ([legalization](../../topics/placement/legalization.md)).
- Pin and part swaps are never delegated ([delegation](../../topics/workflow/delegation-and-expert-review.md)).

**Builds on.** prac#5; alg#75, alg#189–190; eco#135.

**How to test.** On 20 deliberately over-constrained boards, measure time to a feasible design. Compare the ECO cost of the chosen changes with expert choices.

**Effort/risk.** M. ECO cost models are hard; start with layers, area and relaxations.

---

## S4. Predict-before-check, surprise-triggered replanning, earned autonomy — *sharpened*

**Pitch.** The LLM must forecast each tool's outcome (completion, failing nets, PRC deltas) before running it. A large surprise triggers replanning. Calibration per task class decides how much autonomy the agent earns.

**Mechanism.**
- **Forecasts:** each tool call carries a `prediction`; the harness scores it with Brier score or absolute error.
- **Surprise:** above a threshold, the planner must write a diagnosis (evidence, hypothesis, falsifier) before continuing.
- **Autonomy:** rolling calibration plus acceptance rate per task class set the level: propose-only, auto-apply with review, or auto-apply. Any regression demotes the class.
- **Data:** predictions and outcomes are logged as training data.

**Why it should work.**
- Bogatin's rule is to state the expected result before checking ([trust-requirements](../../topics/workflow/trust-requirements.md)).
- Prediction accuracy is already a proposed process metric ([benchmark-plan](../../topics/verification/benchmark-plan.md)).
- Delegation follows predictability ([delegation](../../topics/workflow/delegation-and-expert-review.md)).
- More iterations can hurt ([agent-loop-patterns](../../topics/llm/agent-loop-patterns.md)).

**Builds on.** prac#194, prac#203; llm#58, llm#61, llm#395.

**How to test.** Run agent sessions with and without forecasts. Metrics: wasted iterations, tokens, final quality, calibration curves per class.

**Effort/risk.** S. Predictions could anchor the scorer, so hide them from it.

---

## S5. Intent-preserving refactoring operators — *new*

**Pitch.** Give the LLM a library of layout refactorings with formal pre- and postconditions over the intent graph, verified automatically, like a code agent's rename-refactor. Examples: move a block, mirror it to the other side, rotate a subcircuit, swap equivalent channels, compact a region, re-tighten after a resize.

**Mechanism.** Each operator has three parts:
- **Precondition:** for example, the block is fully reserved and no locked copper crosses its boundary.
- **Transform:** a rigid transform, then re-tighten the topology, then re-legalize the neighbours.
- **Postcondition:** every intent of the block and its interface passes the [V1](verification.md#v1-mutation-tested-layout-unit-tests--new) tests, with budgets inside their margins.

Operators compose into scripts, and a failure rolls the whole script back. The LLM picks operators and targets; the engine performs them.

**Why it should work.**
- Bounded semantic actions and deterministic move libraries win ([agent-loop-patterns](../../topics/llm/agent-loop-patterns.md), [agent-tooling-reliability](../../topics/ux/agent-tooling-reliability-patterns.md)).
- Persisted topology allows re-tightening after a move ([topological-routing](../../topics/routing/topological-routing.md)).

**Builds on.** llm#52, llm#339; alg#168; xd#1; eco#15.

**How to test.** Set 50 refactoring tasks, such as "move the USB block to the other edge". Measure success and intent regressions, compared with LLM coordinate edits and with a human.

**Effort/risk.** M. After a large move, re-tightening may fail; fall back to re-routing the interface nets.

---

## S6. Successive halving over the placement × router candidate matrix — *sharpened*

**Pitch.** Generate many placement candidates, but spend routing compute the way Hyperband spends training compute: cheap probes for everyone, real routes for the survivors, full sign-off for the finalists.

**Mechanism.**
- **Candidates:** N placements (QD archive or seeds) × engine presets.
- **Rungs:**
  - 0: T0 metrics;
  - 1: a 1 s KRT probe;
  - 2: a short Freerouting run;
  - 3: full route, DRC and SI checkers.
- **Selection:** keep the top 1/η at each rung, with MAP-Elites niches so the finalists stay distinct. The finalists feed the alternatives view ([U4](workflow-ux.md#u4-budget-slider-pareto-explorer--sharpened)).

**Why it should work.**
- Proxies cannot separate near-equal candidates, so route the top-k ([open-source-placers](../../topics/landscape/open-source-placers.md), [commercial-architecture-patterns](../../topics/landscape/commercial-architecture-patterns.md)).
- The five-level fidelity ladder already exists ([performance-and-multifidelity](../../topics/solvers/performance-and-multifidelity.md)).

**Builds on.** eco#88, eco#121; alg#303, alg#329.

**How to test.** At equal compute, compare three schemes: successive halving, route-all at low budget, and proxy-rank then route the top 3. Metric: best final score.

**Effort/risk.** S. It depends on scores agreeing across rungs, so measure rung-to-rung correlation.
