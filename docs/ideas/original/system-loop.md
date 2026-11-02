# Original ideas: the coupled placement–routing loop and LLM orchestration

Scope: S1–S6, how stages hand work to each other, how LLM decisions are recorded and replayed, where the loop spends effort. Part of the [original-ideas catalog](README.md); shorthands as in [intent-and-why](intent-and-why.md). End-to-end assemblies: [hybrid-architecture-options](../../topics/architecture/hybrid-architecture-options.md). Test status: [research/ideas](../../research/ideas.md#original-ideas-58).
Keys: S1 corridor contract, bundle, S2 decision DAG, replay, bisect, S3 priced ECO menu, infeasibility certificate, S4 predict-before-check, earned autonomy, S5 refactoring operators, S6 successive halving, Hyperband, rungs

## S1. Corridor contract between placement and routing — *novel combination*

Idea: the placement → routing hand-off as an explicit, checkable contract (bundles assigned to corridors and layers, with capacities); the placer leaves room for it, routers honour it.
Mechanism:
1. The LLM groups nets into bundles (bus lanes, pairs, power trunks) and sets priorities.
2. Min-cost multicommodity flow over the block channel graph ([P2](placement.md#p2-contracted-soft-macro-floorplan-with-cut-capacity-check--novel-combination)) assigns each bundle a corridor and layer pair within capacity.
3. Contract = {bundle, corridor polygon, layers, capacity used, reserved meander slack}.
4. Engines: placer treats corridors as soft keep-outs (density inflation); legalizer makes them hard for high-priority bundles; routers get corridor rule areas + preferred-direction cost biases.
5. A violation is reported against whichever side broke the contract.
Evidence [I]: humans plan top-down while autorouters work bottom-up, one connection at a time ([autorouter-skepticism](../../topics/routing/autorouter-skepticism.md)); experts escape and reserve whole buses and leave channels between memories ([sub-workflows](../../topics/workflow/sub-workflows-power-bga-ddr.md)); bundling and capacity-mesh routing have precedents ([cross-domain-routing-transplants](../../topics/routing/cross-domain-routing-transplants.md)).
Builds on: alg#148, alg#250, alg#302; prac#28, prac#67; [N5](priority-agents-and-negotiation.md#n5-reservation-tokens-with-confidence-hardening--new) · Test: 15 multi-bus boards with vs without the contract; metrics completion, bus crossings and length spread, re-place iterations · Effort/risk: M; a rigid contract can trap the design: renegotiate through [N1](priority-agents-and-negotiation.md#n1-domain-agents-in-a-resource-market--new).

## S2. Decision DAG with deterministic replay and decision bisect — *new*

Idea: every LLM decision (side, region, relation, topology, relaxation, engine choice) is a DAG node; geometry is a deterministic function of the decisions, so alternatives are cheap replays and regressions bisect to the causing decision.
Mechanism: log entry {id, parent, type, payload, rationale ids}; solver runs content-addressed by (decision-prefix hash, seeds, tool versions); edit a decision → replay from the first stage depending on it (stages declare dependencies); bisect: given a PRC regression between two states, binary-search decision prefixes, replaying from cache, until the culprit is found; report it to the LLM and the user.
Evidence [I]: determinism and recorded seeds/versions are trust requirements ([trust-requirements](../../topics/workflow/trust-requirements.md), [agent-tooling-reliability](../../topics/ux/agent-tooling-reliability-patterns.md)); persisted relations re-solve reliably ([interfaces](../../topics/llm/interfaces-relations-vs-coordinates.md)); experts already work with a git commit per state ([expert-state-machine](../../topics/workflow/expert-state-machine.md)).
Builds on: llm#326, llm#353, llm#427; prac#4, prac#204 · Test: seed 30 regressions into long agent sessions; bisect accuracy and replays needed; branching cost vs full re-run · Effort/risk: M; nondeterministic engines break replay: force Freerouting `-mt 1`. Freerouting has no seed flag (seeds `Random(0)` internally) and whether `-mt 1` makes it deterministic is untested: check board hashes over repeated runs before relying on recomputation; replay from the cache.

## S3. Infeasibility to priced ECO menu — *novel combination*

Idea: every "impossible" signal (CP-SAT infeasible subsets, SURF cut overflow, escape UNSAT cores, budget overspend) becomes one menu of priced engineering changes (relax, substitute, pin-swap, repackage, add a layer pair, enlarge the board, move a connector) for the LLM to rank and a human to approve.
Mechanism:
1. Rule table: infeasibility certificate → candidate ECOs.
2. Quick evaluation per candidate: re-solve the affected window or cut; BOM delta, layer and area cost, schedule risk, budget impact.
3. Menu in the experts' escalation order: local moves → re-floorplan → repackage, add layers or enlarge → drop a function → ask a human.
Evidence [I]: experts escalate in exactly this fixed order ([expert-state-machine](../../topics/workflow/expert-state-machine.md)); an escape solver saying "impossible" is valuable stackup feedback ([escape-routing](../../topics/routing/escape-routing.md)); legalizers should report infeasible subsets ([legalization](../../topics/placement/legalization.md)); pin and part swaps are never delegated ([delegation](../../topics/workflow/delegation-and-expert-review.md)).
Builds on: prac#5; alg#75, alg#189–190; eco#135 · Test: 20 deliberately over-constrained boards; time to a feasible design; ECO cost of chosen changes vs expert choices · Effort/risk: M; ECO cost models are hard: start with layers, area, relaxations.

## S4. Predict-before-check, surprise-triggered replanning, earned autonomy — *sharpened*

Idea: the LLM forecasts each tool's outcome (completion, failing nets, PRC deltas) before running it; a large surprise triggers replanning; calibration per task class sets the autonomy earned.
Mechanism: each tool call carries a `prediction`, scored by Brier score or absolute error; surprise above a threshold → planner must write a diagnosis (evidence, hypothesis, falsifier) before continuing; rolling calibration + acceptance rate per task class set the level (propose-only, auto-apply with review, auto-apply); any regression demotes the class; predictions and outcomes logged as training data.
Evidence [I]: Bogatin's rule: state the expected result before checking ([trust-requirements](../../topics/workflow/trust-requirements.md)); prediction accuracy is already a proposed process metric ([benchmark-plan](../../topics/verification/benchmark-plan.md)); delegation follows predictability ([delegation](../../topics/workflow/delegation-and-expert-review.md)); more iterations can hurt ([agent-loop-patterns](../../topics/llm/agent-loop-patterns.md)).
Builds on: prac#194, prac#203; llm#58, llm#61, llm#395 · Test: agent sessions with vs without forecasts; metrics wasted iterations, tokens, final quality, calibration curves per class · Effort/risk: S; predictions could anchor the scorer: hide them from it.

## S5. Intent-preserving refactoring operators — *new*

Idea: a library of layout refactorings (move a block, mirror it to the other side, rotate a subcircuit, swap equivalent channels, compact a region, re-tighten after a resize) with formal pre- and postconditions over the intent graph, verified automatically, like a code agent's rename-refactor.
Mechanism: operator = precondition (e.g. block fully reserved, no locked copper crossing its boundary) + transform (rigid transform → re-tighten topology → re-legalize neighbours) + postcondition (every intent of the block and its interface passes the [V1](verification.md#v1-mutation-tested-layout-unit-tests--new) tests, budgets inside margins). Operators compose into scripts; a failure rolls back the whole script. The LLM picks operators and targets; the engine performs them.
Evidence [I]: bounded semantic actions and deterministic move libraries win ([agent-loop-patterns](../../topics/llm/agent-loop-patterns.md), [agent-tooling-reliability](../../topics/ux/agent-tooling-reliability-patterns.md)); persisted topology allows re-tightening after a move ([topological-routing](../../topics/routing/topological-routing.md)).
Builds on: llm#52, llm#339; alg#168; xd#1; eco#15 · Test: 50 refactoring tasks ("move the USB block to the other edge"); success and intent regressions vs LLM coordinate edits and vs a human · Effort/risk: M; re-tightening may fail after a large move: fall back to re-routing the interface nets.

## S6. Successive halving over the placement × router candidate matrix — *sharpened*

Idea: many placement candidates, routing compute spent like Hyperband spends training compute: cheap probes for all, real routes for survivors, full sign-off for finalists.
Mechanism: candidates = N placements (QD archive or seeds) × engine presets; rungs 0 T0 metrics → 1 a 1 s KRT probe → 2 a short Freerouting run → 3 full route + DRC + SI checkers; keep the top 1/η per rung with MAP-Elites niches so finalists stay distinct; finalists feed the alternatives view ([U4](workflow-ux.md#u4-budget-slider-pareto-explorer--sharpened)).
Evidence [I]: proxies cannot separate near-equal candidates, so route the top-k ([open-source-placers](../../topics/landscape/open-source-placers.md), [commercial-architecture-patterns](../../topics/landscape/commercial-architecture-patterns.md)); the five-level fidelity ladder already exists ([performance-and-multifidelity](../../topics/solvers/performance-and-multifidelity.md)).
Builds on: eco#88, eco#121; alg#303, alg#329 · Test: equal compute, successive halving vs route-all at low budget vs proxy-rank then route the top 3; metric best final score · Effort/risk: S; depends on scores agreeing across rungs: measure rung-to-rung correlation.
