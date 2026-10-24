# Docs index

Load the smallest doc that answers your question. Start from a digest
(<= 800 words), follow its links to one topic doc, and only open the raw
[research notes](../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/)
when you need the underlying evidence. Authoring rules: [CONVENTIONS.md](CONVENTIONS.md).

## Start here

- [Executive report](../reports/LLM%20driven%20PCB%20placement%20and%20routing.md): conclusions, recommended architecture, roadmap.
- [Hybrid architecture options](topics/architecture/hybrid-architecture-options.md)
- **Building it:** [one-month plan](topics/architecture/month-plan.md) (physics-first joint placement and routing), [joint loop](topics/architecture/joint-loop.md) (`kae.joint`: routing feedback into windowed re-placement and re-routing), [system design](topics/architecture/system-design.md), [build plan](topics/architecture/system-design-build-plan.md), [physics engine design](topics/architecture/physics-engine-design.md).
- [Original ideas](ideas/original/README.md): new ideas, top 10 to try first.
- [Physics-first report](../reports/Physics-first%20PCB%20layout.md), [philosophy](topics/physics/README.md) and [foundations](topics/physics/foundations.md): circuits as Maxwell at zeroth order, rules derived from first principles, what each conductor is doing, joint place+route, validation.

## Digests

| Digest | Covers |
|---|---|
| [algorithms](digests/algorithms.md) | placement and routing algorithms, PCB placers, ML/RL, solvers, cross-domain transplants |
| [llm-data-ux](digests/llm-data-ux.md) | what LLMs can and can't do in layout, interfaces, agent loops, design understanding, data, UX |
| [ecosystem](digests/ecosystem.md) | KiCad API/CLI/DRC, routers and placers to reuse, MCP lessons, commercial tools, patents, licensing |
| [rules-hs-emi-interfaces](digests/rules-hs-emi-interfaces.md) | SI/EMC physics, stackup, diff pairs, per-interface rule packs, SI/EMI checkers |
| [rules-power-rf-analog-dfm](digests/rules-power-rf-analog-dfm.md) | converters and hot loops, decoupling/PDN, RF, analog, isolation, thermal, DFM, power checkers |
| [practice-evaluation](digests/practice-evaluation.md) | expert workflow, trust, review checklist, constraint IR, evaluation stack, benchmarks |
| [physics-first](digests/physics-first.md) | foundations (gentleness, 7 principles, 13 theorems), rules derived from physics, conductor passports, exact edit pricing, certified floors, physics core v2, joint place+route, verification and validation |

## By task

| If you are... | Read |
|---|---|
| Talking to a live KiCad board | [kicad/ipc-api-10-vs-11](topics/kicad/ipc-api-10-vs-11.md), [kicad/transform-math-pitfalls](topics/kicad/transform-math-pitfalls.md) |
| Generating or parsing DRC rules/reports | [kicad/drc-rule-language-reference](topics/kicad/drc-rule-language-reference.md), [kicad/drc-report-and-repair-loop](topics/kicad/drc-report-and-repair-loop.md) |
| Designing the constraint/intent format | [architecture/constraint-ir](topics/architecture/constraint-ir.md), [rules/rule-pack-format](topics/rules/rule-pack-format.md) |
| Designing LLM tools or an MCP server | [llm/interfaces-relations-vs-coordinates](topics/llm/interfaces-relations-vs-coordinates.md), [kicad/mcp-tool-surface-spec](topics/kicad/mcp-tool-surface-spec.md), [llm/agent-loop-patterns](topics/llm/agent-loop-patterns.md) |
| Building the placer | [placement/pcb-placers-2022-2026](topics/placement/pcb-placers-2022-2026.md), [placement/legalization](topics/placement/legalization.md), [solvers/recommended-stack](topics/solvers/recommended-stack.md) |
| Integrating a router | [routing/freerouting-constraint-bridge](topics/routing/freerouting-constraint-bridge.md) (`kae.route`: every KiCad constraint into Freerouting, repair after import, shared rules API), [routing/critical-net-routing](topics/routing/critical-net-routing.md) (`kae.route.critical`: hot loops, decoupling, crystals, protection and rails routed first at their physical optimum, locked for the bridge), [routing/freerouting](topics/routing/freerouting.md), [kicad/specctra-freerouting-integration](topics/kicad/specctra-freerouting-integration.md), [routing/kicad-pns-router](topics/routing/kicad-pns-router.md) |
| Recognizing circuit blocks and net roles | [physics/comprehension](topics/physics/comprehension.md) (`kae.circuit`, the physics brief, measured accuracy), [llm/design-understanding-pipeline](topics/llm/design-understanding-pipeline.md), [llm/net-role-classification](topics/llm/net-role-classification.md) |
| Encoding rules for one interface or converter | `topics/rules/interfaces/<iface>.md`, `topics/rules/power/<topology>.md` (start at [power/hot-loops](topics/rules/power/hot-loops.md)) |
| Writing a checker | [rules/checkers-si-emi](topics/rules/checkers-si-emi.md), [rules/checkers-power](topics/rules/checkers-power.md), [verification/critic-stack](topics/verification/critic-stack.md) |
| Evaluating results | [verification/evaluation-stack](topics/verification/evaluation-stack.md), [verification/benchmarks](topics/verification/benchmarks.md), [verification/benchmark-plan](topics/verification/benchmark-plan.md) |
| Planning placer/router development and evaluation | [verification/dev-eval-plan](topics/verification/dev-eval-plan.md), [routing/strategy-candidates](topics/routing/strategy-candidates.md), [placement/strategy-candidates](topics/placement/strategy-candidates.md) |
| Running the benchmark harness | [bench/README](../bench/README.md), [verification/harness](topics/verification/harness.md), [data/open-board-sources](topics/data/open-board-sources.md) |
| Planning the agent's workflow | [workflow/expert-state-machine](topics/workflow/expert-state-machine.md), [workflow/trust-requirements](topics/workflow/trust-requirements.md) |
| Understanding the physics-first principles | [physics/foundations](topics/physics/foundations.md), then one `physics/lens-*.md` |
| Replacing a rule of thumb with physics | [physics/derivation-audit-table](topics/physics/derivation-audit-table.md) (one row per rule), [physics/rule-basis-set](topics/physics/rule-basis-set.md) |
| Knowing what each conductor is doing | [physics/lens-cd](topics/physics/lens-cd.md), [physics/real-board-passports](topics/physics/real-board-passports.md), [physics/suite-physics-results](topics/physics/suite-physics-results.md) (whole suite, router vs human), [physics/physics-core-v2](topics/physics/physics-core-v2.md) |
| Writing physics budgets or the physics IR | [physics/vocabulary](topics/physics/vocabulary.md), [physics/physics-ir](topics/physics/physics-ir.md), [physics/schematic-to-physics](topics/physics/schematic-to-physics.md) |
| Choosing a field/circuit/thermal solver | [physics/physics-core-v2](topics/physics/physics-core-v2.md), [physics/solver-ladder](topics/physics/solver-ladder.md), [physics/open-solvers](topics/physics/open-solvers.md) |
| Checking a physics claim or planning a measurement | [physics/verification-and-limits](topics/physics/verification-and-limits.md), [physics/validation-program](topics/physics/validation-program.md), [physics/validation-coupons](topics/physics/validation-coupons.md) |
| Placing and routing together | [physics/joint-place-route](topics/physics/joint-place-route.md), [physics/physics-in-the-loop-optimization](topics/physics/physics-in-the-loop-optimization.md), [physics/place-terms](topics/physics/place-terms.md) (`kae.physics`: placement cost terms, validated against PEEC and human boards), [physics/exact-physics-options](topics/physics/exact-physics-options.md) (when to use exact physics instead: costs, decision flips, designs), [physics/exact-physics-in-kae](topics/physics/exact-physics-in-kae.md) (`--physics-fidelity fast|exact|multi`: PEEC on routed copper, validation, measured decisions) |
| Shaping pours and power copper | [physics/power-copper](topics/physics/power-copper.md), [physics/copper-shape-synthesis](topics/physics/copper-shape-synthesis.md) |
| Checking that a board is physically right, not just DRC-clean | [physics/physics-critics](topics/physics/physics-critics.md), [physics/physics-critics-catalog](topics/physics/physics-critics-catalog.md) |
| Reusing third-party code or data | [licensing/reuse-matrix](topics/licensing/reuse-matrix.md), [data/licensing-tiers-and-contamination](topics/data/licensing-tiers-and-contamination.md) |

## Topic areas

`topics/` holds about 150 focused docs, each <= 3,000 words, in these areas:
[architecture](topics/architecture/), [placement](topics/placement/),
[routing](topics/routing/), [solvers](topics/solvers/), [llm](topics/llm/),
[data](topics/data/), [ux](topics/ux/), [kicad](topics/kicad/),
[landscape](topics/landscape/), [licensing](topics/licensing/),
[rules](topics/rules/) (with `interfaces/` and `power/`),
[workflow](topics/workflow/), [verification](topics/verification/),
[physics](topics/physics/) (start at its [README](topics/physics/README.md)).

Canonical docs where two areas overlap: PCBWorld →
[routing/pcbworld](topics/routing/pcbworld.md); LLM-guided placers →
[placement/llm-guided-placement](topics/placement/llm-guided-placement.md)
(LLM-role view in [llm/llm-guided-placement-systems](topics/llm/llm-guided-placement-systems.md));
LLM field reports → [ux/field-reports](topics/ux/field-reports.md)
(forum-sourced views in [workflow/llm-field-reports](topics/workflow/llm-field-reports.md)).

## Idea inventories

Every approach found in the survey, one line each, linked to its topic doc:
[algorithms](ideas/inventory-algorithms.md),
[llm-data-ux](ideas/inventory-llm-data-ux.md),
[ecosystem](ideas/inventory-ecosystem.md),
[rules-hs-emi](ideas/inventory-rules-hs-emi.md),
[rules-power](ideas/inventory-rules-power.md),
[practice-evaluation](ideas/inventory-practice-evaluation.md),
[cross-domain transplants (ranked)](ideas/cross-domain-transplants.md),
[physics-first catalog](ideas/physics-first/README.md) (~890 ideas in 11 theme files and 7 lens files).
