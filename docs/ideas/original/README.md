# Original ideas catalog

58 ideas beyond the ~2,000 in the [inventories](../cross-domain-transplants.md). Tags: **new** (not in the corpus), **combo** (novel combination), **sharp** (existing idea made buildable). Theme files give pitch, mechanism, evidence, builds-on, test and effort/risk; assemblies are in [hybrid-architecture-options](../../topics/architecture/hybrid-architecture-options.md). All [I] until tested.

## Intent and the "why" — [intent-and-why.md](intent-and-why.md)
- **I1 Physics budget ledger** (combo): dB/ps/nH/mV budgets the LLM allocates and objects spend.
- **I2 Dimensioned constraint types** (new): typed, symbolic values (3h, t_r/6) with derivation traces.
- **I3 Why-graph** (combo): a physics-mechanism layer between requirements and rules.
- **I4 Constraint price tags** (new): what each constraint costs, plus a cached foil.
- **I5 Criticality field** (combo): one confirmed score allocating solver time, order and simulation.
- **I6 Intent diff** (new): revision diffs over intents and verdicts, not geometry.
- **I7 Intent inside the board file** (sharp): ids and rationale stamped into KiCad-native objects.

## Priority submodules and negotiation — [priority-agents-and-negotiation.md](priority-agents-and-negotiation.md)
- **N1 Resource market** (new): domain agents bid for contested resources; PathFinder pricing, generalized.
- **N2 Iso-physics substitutions** (new): trade parameters that keep the physics constant.
- **N3 Veto-with-proof** (combo): only a failing deterministic check can block; capped objections.
- **N4 Contested-rule court** (combo): briefs, human rulings and reusable precedent.
- **N5 Reservation tokens** (new): tiers publish hardening reservations, not frozen copper.
- **N6 ε-lexicographic compiler** (sharp): tiered objectives with ε taken from budgets.
- **N7 Hot-loop nH micro-placer** (new): switching cells placed to minimize estimated inductance.
- **N8 Decap assignment** (new): caps matched to pins by mounting inductance.
- **N9 Ordered-chain embedder** (combo): I/O and RF chains placed along the pair path.

## Placement — [placement.md](placement.md)
- **P1 Router-probe pseudo-gradients** (combo): router failure attributions become placer forces.
- **P2 Contracted floorplan + cut check** (combo): block port contracts plus SURF cut check before placement.
- **P3 Physics-slack templates** (new): reference layouts deform only within budget slack.
- **P4 Side assignment by graph cut** (sharp): exact top/bottom choice with a second-side activation cost.
- **P5 Verified motif distributions** (sharp): relative-pose mixtures from clean open boards.
- **P6 Slot assignment** (sharp): Hungarian matching of interchangeable parts to slots.
- **P7 Live topological sketch objective** (combo): rubber-band length and cut overflow replace HPWL.
- **P8 Connector-voltage EMI proxy** (new): differentiable common-mode voltage between cable grounds.
- **P9 Pin-mux co-floorplanning** (combo): MCU/FPGA pin functions chosen together with placement.
- **P10 Variant-robust placement** (new): one layout valid for alternate parts.

## Routing — [routing.md](routing.md)
- **R1 Homotopy menus** (sharp): the LLM picks enumerated topology classes; SURF checks.
- **R2 Shadow return nets** (new): a virtual net on the reference plane makes return continuity routable.
- **R3 Joint signal+return via sites** (new): return and power vias solved inside escape.
- **R4 Regret-driven priorities** (sharp): re-prioritize by spend vs solo-optimal route.
- **R5 Router-portfolio bandit** (sharp): learned engine dispatch per context.
- **R6 Verified routing macros** (combo): PRC-tested copper generators per recipe.
- **R7 Plane-partition synthesis** (new): plane splits optimized away from fast nets.
- **R8 Physics-scored PNS beam search** (sharp): checkpointed PNS search scored by budget spend.

## Coupled loop and orchestration — [system-loop.md](system-loop.md)
- **S1 Corridor contract** (combo): bundle→corridor→layer contract binding placer and routers.
- **S2 Decision DAG + bisect** (new): replay LLM decisions; bisect regressions to one.
- **S3 Priced ECO menu** (combo): infeasibility mapped to costed changes.
- **S4 Predict-before-check** (sharp): forecasts, surprise-triggered replanning and earned autonomy.
- **S5 Refactoring operators** (new): layout edits with verified pre- and postconditions.
- **S6 Successive halving** (sharp): Hyperband over the placement × router candidate matrix.

## Verification — [verification.md](verification.md)
- **V1 Mutation-tested layout unit tests** (new): a check counts only if it kills near-miss mutants.
- **V2 Red-team reward hacker** (new): adversarial gate before optimization.
- **V3 Judge licensing** (sharp): the judge gates only categories it passed an exam on.
- **V4 Proxy trust radius** (sharp): proxies are usable only inside their calibrated region.
- **V5 Counterexample-guided rules** (new): sim/bench failures yield validated fast checks.

## Learning and data — [learning-and-data.md](learning-and-data.md)
- **L1 Planted-solution boards** (new): synthetic boards with a known-good layout give an exact gap.
- **L2 Evolve the conductor** (combo): evolve the orchestration policy DSL, not low-level heuristics.
- **L3 Inverse optimization from edits** (sharp): infer house-style weights from designer corrections.
- **L4 EVM as extraction oracle** (combo): check extracted rules against vendor eval layouts.
- **L5 Git-history repair pairs** (new): before/after/message fixes mined from open repos.
- **L6 Fab-query memory** (new): fab EQs become rules and doc checks.

## Workflow and UX — [workflow-ux.md](workflow-ux.md)
- **U1 Physics HUD** (sharp): live budget deltas while the human edits.
- **U2 Intent vs geometry locks** (new): a lock that preserves intent and lets geometry move.
- **U3 Expected-loss brief** (sharp): ask only the questions whose wrong answer costs most.
- **U4 Budget-slider explorer** (sharp): alternatives steered by physical-budget sliders.
- **U5 Semantic ratsnest** (sharp): renders that encode current, criticality, flow and return path.
- **U6 Sketch-to-intent** (combo): scribbles converted to typed relations, never to geometry.
- **U7 Intent-level merge** (new): concurrent human/agent edits merged on intents.

## Joint place-and-route — [joint-pnr.md](joint-pnr.md)
43 ideas for placing and routing together, with measured results in
[joint-pnr-experiments](../../topics/placement/joint-pnr-experiments.md): beam search over
place-one-route-it and physics place terms in the objective have merit; soft routing
gradients, Physarum flow and LLM move proposals did not beat simple controls.

## Top 10 to try first (impact vs effort)
1. **P6 Slot assignment** (S): designer 0.56 vs 0.31–0.39 after swaps; days of work.
2. **N8 Decap assignment** (S): a contested slogan becomes an exact optimization.
3. **N7 Hot-loop micro-placer** (S–M): top rule in every source; no open tool.
4. **V2 Red-team gate** (S): required before RL or evolution; cheap.
5. **V1 Mutation-tested tests** (S–M): makes LLM-written checks trustworthy.
6. **I4 Constraint price tags** (S–M): numbers for explanation and negotiation.
7. **I1+I2 Budget ledger, typed units** (M): the shared "why" vocabulary.
8. **R2 Shadow return nets** (M): closes the route→physics-check gap.
9. **P1 Router-probe pseudo-gradients** (M): fast routers (~0.65 s) replace RUDY.
10. **R1 Homotopy menus** (M): LLM on topology via a bounded menu.

Cheap runners-up: S4 predict-before-check, P4 side cut, U3 expected-loss brief.
