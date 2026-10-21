# Docs index

Load the smallest doc that answers your question. Start from a digest
(<= 800 words), follow its links to one topic doc, and only open the raw
[research notes](../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/)
when you need the underlying evidence. Authoring rules: [CONVENTIONS.md](CONVENTIONS.md).

## Start here

- [Executive report](../reports/LLM%20driven%20PCB%20placement%20and%20routing.md): conclusions, recommended architecture, roadmap.
- [Hybrid architecture options](topics/architecture/hybrid-architecture-options.md)
- [Original ideas](ideas/original/README.md): new ideas, top 10 to try first.

## Digests

| Digest | Covers |
|---|---|
| [algorithms](digests/algorithms.md) | placement and routing algorithms, PCB placers, ML/RL, solvers, cross-domain transplants |
| [llm-data-ux](digests/llm-data-ux.md) | what LLMs can and can't do in layout, interfaces, agent loops, design understanding, data, UX |
| [ecosystem](digests/ecosystem.md) | KiCad API/CLI/DRC, routers and placers to reuse, MCP lessons, commercial tools, patents, licensing |
| [rules-hs-emi-interfaces](digests/rules-hs-emi-interfaces.md) | SI/EMC physics, stackup, diff pairs, per-interface rule packs, SI/EMI checkers |
| [rules-power-rf-analog-dfm](digests/rules-power-rf-analog-dfm.md) | converters and hot loops, decoupling/PDN, RF, analog, isolation, thermal, DFM, power checkers |
| [practice-evaluation](digests/practice-evaluation.md) | expert workflow, trust, review checklist, constraint IR, evaluation stack, benchmarks |

## By task

| If you are... | Read |
|---|---|
| Talking to a live KiCad board | [kicad/ipc-api-10-vs-11](topics/kicad/ipc-api-10-vs-11.md), [kicad/transform-math-pitfalls](topics/kicad/transform-math-pitfalls.md) |
| Generating or parsing DRC rules/reports | [kicad/drc-rule-language-reference](topics/kicad/drc-rule-language-reference.md), [kicad/drc-report-and-repair-loop](topics/kicad/drc-report-and-repair-loop.md) |
| Designing the constraint/intent format | [architecture/constraint-ir](topics/architecture/constraint-ir.md), [rules/rule-pack-format](topics/rules/rule-pack-format.md) |
| Designing LLM tools or an MCP server | [llm/interfaces-relations-vs-coordinates](topics/llm/interfaces-relations-vs-coordinates.md), [kicad/mcp-tool-surface-spec](topics/kicad/mcp-tool-surface-spec.md), [llm/agent-loop-patterns](topics/llm/agent-loop-patterns.md) |
| Building the placer | [placement/pcb-placers-2022-2026](topics/placement/pcb-placers-2022-2026.md), [placement/legalization](topics/placement/legalization.md), [solvers/recommended-stack](topics/solvers/recommended-stack.md) |
| Integrating a router | [routing/freerouting](topics/routing/freerouting.md), [kicad/specctra-freerouting-integration](topics/kicad/specctra-freerouting-integration.md), [routing/kicad-pns-router](topics/routing/kicad-pns-router.md) |
| Recognizing circuit blocks and net roles | [llm/design-understanding-pipeline](topics/llm/design-understanding-pipeline.md), [llm/net-role-classification](topics/llm/net-role-classification.md) |
| Encoding rules for one interface or converter | `topics/rules/interfaces/<iface>.md`, `topics/rules/power/<topology>.md` (start at [power/hot-loops](topics/rules/power/hot-loops.md)) |
| Writing a checker | [rules/checkers-si-emi](topics/rules/checkers-si-emi.md), [rules/checkers-power](topics/rules/checkers-power.md), [verification/critic-stack](topics/verification/critic-stack.md) |
| Evaluating results | [verification/evaluation-stack](topics/verification/evaluation-stack.md), [verification/benchmarks](topics/verification/benchmarks.md), [verification/benchmark-plan](topics/verification/benchmark-plan.md) |
| Getting or using the local board corpus (~13.7k boards) | [data/local-board-corpus](topics/data/local-board-corpus.md) |
| Running the benchmark harness | [bench/README](../bench/README.md), [verification/harness](topics/verification/harness.md), [data/open-board-sources](topics/data/open-board-sources.md), [data/wide-board-corpus](topics/data/wide-board-corpus.md) |
| Planning the agent's workflow | [workflow/expert-state-machine](topics/workflow/expert-state-machine.md), [workflow/trust-requirements](topics/workflow/trust-requirements.md) |
| Reusing third-party code or data | [licensing/reuse-matrix](topics/licensing/reuse-matrix.md), [data/licensing-tiers-and-contamination](topics/data/licensing-tiers-and-contamination.md) |

## Topic areas

`topics/` holds about 150 focused docs, each <= 3,000 words, in these areas:
[architecture](topics/architecture/), [placement](topics/placement/),
[routing](topics/routing/), [solvers](topics/solvers/), [llm](topics/llm/),
[data](topics/data/), [ux](topics/ux/), [kicad](topics/kicad/),
[landscape](topics/landscape/), [licensing](topics/licensing/),
[rules](topics/rules/) (with `interfaces/` and `power/`),
[workflow](topics/workflow/), [verification](topics/verification/).

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
[cross-domain transplants (ranked)](ideas/cross-domain-transplants.md).
