# Docs index

Scope: entry point: lookup, digests, task table, area maps. Not here: facts (linked docs hold them); authoring rules -> [CONVENTIONS.md](CONVENTIONS.md).
Keys: docs index, entry point, where to start, digests, by task, topic areas, idea inventories, research map, SUBJECTS.md, IDS.md

## How to look things up

1. Term: `grep -i '<term>' docs/SUBJECTS.md`, open the first link (one section).
2. Idea id (XD113, OP38, N7): `grep -w <id> docs/IDS.md`.
3. Otherwise read one digest (one linked line per conclusion), then the one section it points to.
4. Raw evidence: [research notes](../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/), only via a topic doc's `Sources`.

Executive reports: [LLM-driven placement and routing](../reports/LLM%20driven%20PCB%20placement%20and%20routing.md), [physics-first layout](../reports/Physics-first%20PCB%20layout.md).

## Digests

| Digest | Covers |
|---|---|
| [algorithms](digests/algorithms.md) | placement and routing algorithms, ML/RL, solvers, transplants |
| [llm-data-ux](digests/llm-data-ux.md) | LLM limits, interfaces, agent loops, design understanding, data, UX |
| [ecosystem](digests/ecosystem.md) | KiCad API/CLI/DRC, reusable engines, MCP, commercial tools, patents, licensing |
| [rules-hs-emi-interfaces](digests/rules-hs-emi-interfaces.md) | SI/EMC physics, stackup, diff pairs, per-interface rule packs, SI/EMI checkers |
| [rules-power-rf-analog-dfm](digests/rules-power-rf-analog-dfm.md) | hot loops, converters, PDN, RF, analog, isolation, thermal, DFM, power checkers |
| [practice-evaluation](digests/practice-evaluation.md) | expert workflow, trust, review checklist, constraint IR, evaluation, benchmarks, harness |
| [physics-first](digests/physics-first.md) | physics models, critics, kae physics engine, placer, router, joint loop, validation |

## By task

| Task | Read |
|---|---|
| Talking to a live KiCad board | [ipc-api coverage](topics/kicad/ipc-api-10-vs-11.md#coverage-matrix), [transform math](topics/kicad/transform-math-pitfalls.md#kicad-local-to-board-formula-y-down) |
| Generating or parsing DRC rules/reports | [rule language](topics/kicad/drc-rule-language-reference.md#grammar-and-evaluation), [report and repair loop](topics/kicad/drc-report-and-repair-loop.md#rule-name-protocol) |
| Designing the constraint/intent format | [constraint-ir](topics/architecture/constraint-ir.md#ir-sketch), [rule-pack format](topics/rules/rule-pack-format.md#pack-schema-v0) |
| Designing LLM tools or an MCP server | [relations vs coordinates](topics/llm/interfaces-relations-vs-coordinates.md#write-interface-rule), [MCP surface](topics/kicad/mcp-tool-surface-spec.md#tools), [agent loops](topics/llm/agent-loop-patterns.md#loop-design-for-our-system) |
| Building the placer | [PCB placers](topics/placement/pcb-placers-2022-2026.md#methods-and-results), [legalization](topics/placement/legalization.md#legalizers), [engine stack](topics/solvers/recommended-stack.md#subproblem--tool-mapping) |
| Integrating a router | [Freerouting](topics/routing/freerouting.md#use-in-kae), [DSN/SES](topics/kicad/specctra-freerouting-integration.md#pitfalls-seen-in-our-benchmark-kicad-1007-freerouting-250), [PNS](topics/routing/kicad-pns-router.md#pns-in-kae) |
| Recognizing circuit blocks and net roles | [pipeline](topics/llm/design-understanding-pipeline.md#pipeline), [net roles](topics/llm/net-role-classification.md#layered-classifier) |
| Encoding rules for one interface or converter | `topics/rules/interfaces/<iface>.md`, `topics/rules/power/<topology>.md`; start at [hot loops](topics/rules/power/hot-loops.md#hot-loop-rules-all-topologies) |
| Writing a checker | [SI/EMI](topics/rules/checkers-si-emi.md#custom-checker-specifications), [power](topics/rules/checkers-power.md#checker-design-rules), [critic stack](topics/verification/critic-stack.md#critic-tiers) |
| Evaluating results | [evaluation stack](topics/verification/evaluation-stack.md#tiers), [benchmarks](topics/verification/benchmarks.md#benchmark-conclusions), [benchmark plan](topics/verification/benchmark-plan.md#benchmark-tracks) |
| Running the benchmark harness | [bench/README](../bench/README.md), [harness](topics/verification/harness.md#pipeline-stages), [kaeq queue](../tools/kaeq/README.md), [kaeres results](../tools/kaeres/README.md) |
| Planning placer/router development and evaluation | [dev-eval plan](topics/verification/dev-eval-plan.md#plan-summary), [protocol](topics/verification/dev-eval-protocol.md#evaluation-protocol), [routing](topics/routing/strategy-candidates.md#strategy-table) and [placement](topics/placement/strategy-candidates.md#strategy-table) candidates |
| Seeing what we tried and how it went | [research map](research/README.md#areas), [scorecard](ideas/original/scorecard.md), [bench/results](../bench/results/) |
| Building on kae's router | [constraint bridge](topics/routing/freerouting-constraint-bridge.md#pipeline), [last mile](topics/routing/last-mile-and-restarts.md#last-mile-in-brief), [critical nets](topics/routing/critical-net-routing.md#what-is-routed), [routing research](research/routing/README.md#paths) |
| Routing BGAs and dense regions, or proving they can't be routed | [ranked ideas](topics/routing/bga-routing-ranked-ideas.md#top-10-ideas-ranked-for-our-case), [certificates](topics/routing/routing-infeasibility-certificates.md#the-ladder-for-a-bga-region), [closing open connections](research/routing/kae-closing-open-connections.md) |
| Building on kae's placer or joint loop | [kae-place](topics/placement/kae-place.md#pipeline), [joint loop](topics/architecture/joint-loop.md#the-loop), [hazards](topics/architecture/hazards.md) (what every report flags), [pnr lab](topics/placement/joint-pnr-experiments.md#method-index), [joint research](research/joint/README.md#merit-list) |
| Modelling the physics of a layout | [physics map](topics/physics/README.md#map), [engine design](topics/architecture/physics-engine-design.md#data-model) ([details](topics/architecture/physics-engine-design-details.md)), [solver ladder](topics/physics/solver-ladder.md#the-rungs) |
| Using exact physics or physics prices inside kae | [exact physics](topics/physics/exact-physics-in-kae.md#3-using-it), [hop ports](topics/architecture/physics-hop-ports.md#2-the-model), [physics research](research/physics/README.md) |
| Scoring physical rightness next to DRC | [physics critics](topics/physics/physics-critics.md#2-suite-architecture), [critics validation](topics/physics/physics-critics-validation.md), [suite results](topics/physics/suite-physics-results.md) |
| Designing kae physics end to end: formal problem, DC-to-quasi-static model, what "better" means | [physics-driven design](topics/architecture/physics-driven-design.md#1-the-problem-formally), [frequency coverage](topics/architecture/physics-frequency-coverage.md#4-the-design), [intent objectives](topics/architecture/intent-driven-objectives.md#intent-document) ([build plan](topics/architecture/intent-driven-objectives-build.md)) |
| Judging whether a routed board works | [functional evaluation](topics/physics/functional-evaluation.md#3-checks), [`kae.sim`](topics/architecture/functional-evaluator.md#1-modules) ([budgets](topics/architecture/functional-evaluator-budgets.md)), [intent interchange](topics/architecture/intent-interchange.md#formats-evaluated) |
| Generating schematics from a description | [landscape](topics/synthesis/schematic-generation-landscape.md#papers-and-benchmarks-20242026), [part selection](topics/synthesis/part-selection-and-verification.md#schematic-verification-beyond-erc-q3), [kaesynth](research/llm-design/README.md) |
| Getting or using board corpora | [local corpus (~14k boards)](topics/data/local-board-corpus.md#getting-the-corpus), [open sources](topics/data/open-board-sources.md#pointer-manifest), [wide corpus](topics/data/wide-board-corpus.md#corpus-at-a-glance), [corpus research](research/data/README.md) |
| Planning the agent's workflow | [state machine](topics/workflow/expert-state-machine.md#state-table), [trust](topics/workflow/trust-requirements.md#the-11-trust-requirements-practitioners-words) |
| Choosing the overall architecture | [system design](topics/architecture/system-design.md#packages), [hybrid options](topics/architecture/hybrid-architecture-options.md#comparison), [status 2026-10-25](topics/architecture/status-2026-10-25.md#results-at-handoff) |
| Reusing third-party code or data | [reuse matrix](topics/licensing/reuse-matrix.md#summary-rules), [data licence tiers](topics/data/licensing-tiers-and-contamination.md#licence-tiers-i) |

## Topic areas

- [architecture](topics/architecture/): system, IR, joint loop, physics engine -> [system design](topics/architecture/system-design.md).
- [physics](topics/physics/) -> [area map](topics/physics/README.md).
- [placement](topics/placement/), [routing](topics/routing/), [solvers](topics/solvers/) -> [algorithms digest](digests/algorithms.md).
- [llm](topics/llm/), [data](topics/data/), [ux](topics/ux/), [synthesis](topics/synthesis/) -> [llm-data-ux digest](digests/llm-data-ux.md).
- [kicad](topics/kicad/), [landscape](topics/landscape/), [licensing](topics/licensing/) -> [ecosystem digest](digests/ecosystem.md).
- [rules](topics/rules/) (with `interfaces/`, `power/`) -> [high-speed](digests/rules-hs-emi-interfaces.md) and [power](digests/rules-power-rf-analog-dfm.md) digests.
- [workflow](topics/workflow/), [verification](topics/verification/) -> [practice-evaluation digest](digests/practice-evaluation.md).

Canonical where areas overlap: PCBWorld -> [routing/pcbworld](topics/routing/pcbworld.md); LLM-guided placers -> [placement/llm-guided-placement](topics/placement/llm-guided-placement.md); LLM field reports -> [ux/field-reports](topics/ux/field-reports.md).

## Research (our own methods)

Map and status legend: [research/README](research/README.md). Areas: [routing](research/routing/README.md), [placement](research/placement/README.md), [joint place-and-route](research/joint/README.md), [physics](research/physics/README.md), [data](research/data/README.md), [LLM circuit design](research/llm-design/README.md); untested ideas: [research/ideas](research/ideas.md).

## Idea inventories

Surveyed approaches, one line each: [algorithms](ideas/inventory-algorithms.md), [llm-data-ux](ideas/inventory-llm-data-ux.md), [ecosystem](ideas/inventory-ecosystem.md), [rules-hs-emi](ideas/inventory-rules-hs-emi.md), [rules-power](ideas/inventory-rules-power.md), [practice-evaluation](ideas/inventory-practice-evaluation.md), [cross-domain transplants (ranked)](ideas/cross-domain-transplants.md).
Our catalogs: [original ideas](ideas/original/README.md) ([joint place-and-route](ideas/original/joint-pnr.md), [layer collapse](ideas/original/layer-collapse.md), [scorecard](ideas/original/scorecard.md)); [physics-first catalog](ideas/physics-first/README.md).
