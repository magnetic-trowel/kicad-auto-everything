# Digest: LLM interfaces, agent loops, design understanding, data and UX

Scope: what LLMs can do in layout; interfaces, agent loops, design understanding, data, UX. Not here: algorithms -> [algorithms](algorithms.md); KiCad, MCP, tools -> [ecosystem](ecosystem.md); expert workflow, evaluation -> [practice-evaluation](practice-evaluation.md). Ideas: [inventory](../ideas/inventory-llm-data-ux.md).
Keys: LLM limits, coupled relations, RAC, relation bundle, ordinal magnitude, read state, vision feedback, DRC-Aid, bounded action space, design understanding, NetlistBench, net roles, staged datasheet extraction, PCBench licences, measured priors, field failure modes, intent record

## What LLMs can and cannot do
- LLMs fail at emitting copper: OmniRouting best LMM 12.60% NRR zero-shot, 27.98% agentic, vs PcbRouter 56.20%, humans 93.58%. → [OmniRouting](../topics/routing/llm-routing-evidence.md#omnirouting)
- LLM placement is connectivity-aware but illegal: frontier routability beats academic placers, yet 79.82% of outputs have a pad overlap. → [results](../topics/llm/pcb-llm-benchmarks.md#results)
- Difficulty scales with coupled relations, not objects; tools fix arithmetic, not planning (Python lowered RAC coordinate clean-pass 23.2% -> 21.0%). → [limits](../topics/llm/spatial-reasoning-limits.md#limits)
- PCBWorld LLM numbers are a lower bound, yet ~425k (D3-A) to ~1.92M (D3-B) tokens per episode rules out per-segment LLM routing. → [LLM agents](../topics/routing/pcbworld.md#llm-agents)

## Interfaces and representations
- The write interface matters more than the model: RAC bundles 90.9% clean-pass vs 23.2% for coordinates; relations carry ordinal magnitudes, never coordinates. → [RAC](../topics/llm/interfaces-relations-vs-coordinates.md#rac-relational-agent-contract)
- Persist relations as intent: re-solving after geometry changes passes 89.5% vs 65.6% for the best coordinate-reuse control. → [RAC](../topics/llm/interfaces-relations-vs-coordinates.md#rac-relational-agent-contract)
- Read side: incident-list netlist; hierarchical JSON 0.88 vs 0.43 for KiCad PDF; raw KiCad files 32.5% in SchGen. → [read state](../topics/llm/read-representations.md#read-state-design), [PCB-QA](../topics/llm/read-representations.md#pcb-qa-input-formats), [SchGen](../topics/llm/read-representations.md#schgen-relative-code-vs-raw-kicad)
- Structured feedback beats images (Score tool: DRC −77.1%); renders are a gestalt channel. → [evidence](../topics/llm/vision-feedback.md#evidence)

## Agent loops
- Bounded menus + deterministic realization + independent checks win (DRC-Aid 92.5% clean vs 6.6% static prompting). → [pattern](../topics/llm/agent-loop-patterns.md#bounded-action-space-deterministic-realization-independent-check)
- Default to a mid-tier model; escalate on verified failure (evidence: analog IC repair). → [loop design](../topics/llm/agent-loop-patterns.md#loop-design-for-our-system)
- LLM placement roles that worked: grouping + MILP legalization (Li DAC'26: 15%/13% WL/vias vs Quilter, 6 boards, [S]), fine-tuned constraint graphs (ModuPlace), weak VLM anchors (VeoPlace). → [roles](../topics/llm/llm-guided-placement-systems.md#llm-roles-across-systems), [systems](../topics/placement/llm-guided-placement.md#methods-and-results)
- Offline LLM evolution of placer code: generalized gains small (EvoPlace 0.509–2.85%), unreplicated. → [systems](../topics/llm/code-and-objective-evolution.md#systems)

## Design understanding and datasheets
- Pipeline: deterministic graph → VF2/rules → LLM via tools (adjudication, detector code) → user validation → KiCad-native intent → per-constraint checks. → [pipeline](../topics/llm/design-understanding-pipeline.md#pipeline)
- LLMs cannot trace raw netlists (NetlistBench terminal-neighbour 2–97%) or form stage-level groups (HL3 F1 0.31). → [benchmarks](../topics/llm/block-recognition.md#llm-netlist-reading-benchmarks), [order](../topics/llm/block-recognition.md#recognition-order)
- Net roles from layered evidence (intent → IBIS/datasheet → topology → names → LLM). → [classifier](../topics/llm/net-role-classification.md#layered-classifier)
- Recipes are data: recognizer → constraints → per-constraint check; vendor conflicts are recorded. → [recipes](../topics/llm/function-to-recipe-mapping.md#recipe--recognizer--constraints--checks)
- Staged, provenance-keeping extraction reaches 98.8% faithfulness vs 76.1% one-shot; naive PDF Q&A fails (GDP.pdf best 30.7%). → [pipelines](../topics/llm/datasheet-extraction.md#pipelines-and-reliability)
- Our kaesynth typed IR builds clean schematics, but independent LLM review rated every design "not ready". → [kaesynth](../research/llm-design/kaesynth.md#results)

## Data
- Usable data is scarce: PCBench has no or unclear licence on 62.1% of per-board `metadata.json` files (54.3% by `master_metadata.json`); 33% of licensed routed human boards pass their own DRC; expect low thousands usable. → [PCBench](../topics/data/corpora-and-yield.md#pcbench-source-pool-of-pcbworld-d3), [yield](../topics/data/corpora-and-yield.md#supply-vs-usable-yield)
- Our corpus: 14,318 boards from 8,757 repos, 17% DRC-clean as committed under their own rules. → [board corpus](../research/data/board-corpus.md#results)
- Only licence tier A feeds our CDLA-Permissive-2.0 data; GPL-3.0-or-later code does not change data tiers; time/cluster splits against contamination. → [tiers](../topics/data/licensing-tiers-and-contamination.md#licence-tiers-i), [contamination](../topics/data/licensing-tiers-and-contamination.md#contamination)
- The learnable signal is relational and per-package (0402 decap median 2.51 mm; 4-layer p90 7.7 mm vs 26 mm all-board tail; power/signal width 1.88): ship as soft priors. → [decap](../topics/data/measured-priors.md#decoupling-distance-priors), [style](../topics/data/measured-priors.md#routing-style-priors-same-128-boards)
- Coarse human-derived hints barely help (clean route 0.19–0.21 vs designer 0.63): retrieval must transfer fine relative geometry. → [transfer](../topics/data/layout-retrieval-and-reuse.md#how-much-do-coarse-human-derived-constraints-transfer)
- Designer placements route clean 0.56 vs 0.12–0.16 for auto-placers; fitted rankers never beat the best fixed signal: gate on a bounded real route. → [measures](../topics/data/imitation-and-learned-scores.md#which-placement-measures-predict-a-clean-route), [calibration](../topics/data/imitation-and-learned-scores.md#kicad-tools-calibration-studies)
- Training order: retrieval + priors → pose/assignment model → constraint SFT → GRPO with tiered reward → DPO if hacking appears. → [plan](../topics/data/data-pipeline-plan.md#5-train-in-order)

## Field reports and UX
- Working boards: LLM orchestrates engines, KiCad or the fab gives the verdict, writes are read back, a human gates. → [implications](../topics/ux/field-reports.md#design-implications)
- The costliest failures are invisible to DRC: package variants, library aliasing, label shorts, muted checks. → [taxonomy](../topics/ux/field-failure-modes.md#failure-categories)
- Reliability: read-back, refusals, one commit per change, keep only if counts don't worsen. → [ingredients](../topics/ux/agent-tooling-reliability-patterns.md#reliability-ingredients-seen-in-the-field)
- Designers want a real-time, auditable co-pilot that learns house style and honours locks. → [implications](../topics/ux/designer-demand-and-trust.md#design-implications-i)
- Explain "why" by re-solving under the implied constraint; offer 2–4 alternatives; tag claims by provenance. → [co-pilot](../topics/ux/explanations-and-alternatives.md#design-implications-for-a-pcb-co-pilot-i)
- The committed relation bundle is the "why" record, logged at decision time. → [sidecar](../topics/ux/design-rationale-and-intent-record.md#intent-sidecar-design-i)

## Open questions
- Does RAC hold on full real boards with a KiCad backend; how are tight/close/loose calibrated? → [RAC](../topics/llm/interfaces-relations-vs-coordinates.md#open-questions)
- No layout-guideline extraction benchmark, board-level recognition accuracy, or PCB designer co-pilot study exists. → [extraction](../topics/llm/datasheet-extraction.md#open-questions), [recognition](../topics/llm/block-recognition.md#open-questions), [HCI](../topics/ux/explanations-and-alternatives.md#open-questions)
