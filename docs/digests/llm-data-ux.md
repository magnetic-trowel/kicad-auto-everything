# Digest: LLM interfaces, agent loops, design understanding, data and UX

Executive statements; detail is in the linked topic docs and every idea in [the inventory](../ideas/inventory-llm-data-ux.md).

## What LLMs can and cannot do
- **LLMs fail at emitting geometry and succeed at semantic choices made for a solver.**
  - OmniRouting: best model 12.6% of nets DRC-clean (28.0% agentic) vs 56.2% for an open router and 93.6% for humans.
  - Every PCB win for an LLM system with a legal or DRC-clean output keeps geometry in a solver.

  → [spatial-reasoning-limits](../topics/llm/spatial-reasoning-limits.md), [pcb-llm-benchmarks](../topics/llm/pcb-llm-benchmarks.md)
- **Corrected:** LLM placement is connectivity-aware but illegal. Frontier models beat academic placers on routability (0.90–0.95, legality gating unstated) but about 80% of outputs have pad overlaps. → [pcb-llm-benchmarks](../topics/llm/pcb-llm-benchmarks.md)
- **Difficulty scales with coupled relations; tools fix arithmetic, not planning.** → [spatial-reasoning-limits](../topics/llm/spatial-reasoning-limits.md)
- **Corrected:** PCBWorld's LLM routers ran without DRC feedback (0.65 clean-pass is a floor), yet 0.4–1.9M tokens per board rules out per-segment LLM routing. → [routing/pcbworld](../topics/routing/pcbworld.md), [agent-loop-patterns](../topics/llm/agent-loop-patterns.md)

## Interfaces and representations
- **The write interface matters more than the model.** On RAC, relation bundles reach 90.9% clean-pass against 23.2% for coordinates (21.0% with Python) and 62.4% for sequential relations. Use ordinal magnitudes and relaxation feedback. → [interfaces-relations-vs-coordinates](../topics/llm/interfaces-relations-vs-coordinates.md)
- **Persist relations as intent.** Re-solving after resizes passes 89.5%, against 65.6% for coordinate reuse. → [interfaces-relations-vs-coordinates](../topics/llm/interfaces-relations-vs-coordinates.md), [design-rationale-and-intent-record](../topics/ux/design-rationale-and-intent-record.md)
- **Read side:** incident-list netlists, compact JSON plus query tools (0.88 vs 0.43 for PDF), relative pin-name code (82% vs 32.5% for raw KiCad). → [read-representations](../topics/llm/read-representations.md)
- **Structured feedback beats images on DRC:** scoring cut DRC 77.1%, visuals less; neither clearly lifted routability. Images are a gestalt channel only. → [vision-feedback](../topics/llm/vision-feedback.md)

## Agent loops
- **Bounded menus plus deterministic realization plus independent checks win** (DRC-Aid 92.5% vs 6.6% for static prompting). Default to a mid-tier model; budget iterations. → [agent-loop-patterns](../topics/llm/agent-loop-patterns.md)
- **Placement roles that worked:**
  - grouping plus MILP legalization (Li DAC'26: −15%/−13% WL/vias vs Quilter);
  - fine-tuned constraint graphs (ModuPlace);
  - weak VLM anchors (λ = 0.01);
  - place-one-replicate for repeated channels.

  → [llm-guided-placement-systems](../topics/llm/llm-guided-placement-systems.md), [placement/llm-guided-placement](../topics/placement/llm-guided-placement.md)
- **Offline LLM evolution** of placer and router code works through restricted, gradient-checked interfaces; generalized gains are small (0.5–2.9%). → [code-and-objective-evolution](../topics/llm/code-and-objective-evolution.md)

## Design understanding and datasheets
- **Pipeline:** deterministic graph → VF2 and rule recognition → LLM via tools (adjudication, detector code) → user validation → KiCad-native intent (implicit net classes, component classes, generated rule areas, `.kicad_dru`) → per-constraint checks. → [design-understanding-pipeline](../topics/llm/design-understanding-pipeline.md)
- **LLMs can't trace raw netlists** (terminal-neighbour accuracy 2–97%) or form stage-level groups (F1 0.31). They can write detector code. → [block-recognition](../topics/llm/block-recognition.md)
- **Net roles:** layered evidence (intent → IBIS/datasheet → topology → names → LLM). IBIS `[Diff Pin]` and `[Ramp]` are an unused source for layout classification. → [net-role-classification](../topics/llm/net-role-classification.md)
- **Recipes are data:** each constraint carries its own check; vendor conflicts are surfaced. → [function-to-recipe-mapping](../topics/llm/function-to-recipe-mapping.md)
- **Staged, provenance-preserving extraction** reaches 98.8% faithfulness vs 76.1% one-shot. Naive PDF Q&A fails (30.7%); tool-call audits catch faked reads. → [datasheet-extraction](../topics/llm/datasheet-extraction.md), [part-layout-card](../topics/llm/part-layout-card.md)

## Data
- **Usable data is scarce:**
  - PCBench is 62% unlicensed with only 23 KiCad 6+ boards;
  - only 33% of licensed human boards pass their own DRC;
  - expect low thousands of usable boards.

  → [corpora-and-yield](../topics/data/corpora-and-yield.md)
- **Licence tiers A/B/C:** only permissive sources feed our CDLA-Permissive data. GPL-3.0-or-later code lets GPL engines run in-process; data tiers are unchanged. Use time and cluster splits against contamination. → [licensing-tiers-and-contamination](../topics/data/licensing-tiers-and-contamination.md)
- **The learnable signal is relational and per-package:** 0402 decap median 2.5 mm; 4-layer p90 7.7 mm vs 26 mm on 2-layer; power/signal width 1.88. Ship these as soft priors now. → [measured-priors](../topics/data/measured-priors.md)
- **Coarse hints from human placements barely help** (0.19–0.21 vs designer 0.63), so retrieval must transfer fine relative geometry. → [layout-retrieval-and-reuse](../topics/data/layout-retrieval-and-reuse.md)
- **Designer placements route clean 0.56 vs 0.12–0.16 for auto-placers.** Learned rankers rarely beat HPWL on small corpora; gate on a bounded real route. → [imitation-and-learned-scores](../topics/data/imitation-and-learned-scores.md)
- **Training order:** priors and retrieval, then a pose and assignment model, then round-trip-verified constraint SFT, then GRPO with tiered rewards, with DPO if hacking appears. → [training-recipes](../topics/data/training-recipes.md), [data-pipeline-plan](../topics/data/data-pipeline-plan.md)

## Field reports and UX
- **Working boards share one pattern:** the LLM orchestrates engines, KiCad or the fab gives the verdict, writes are read back, a human gates. → [field-reports](../topics/ux/field-reports.md)
- **The costliest failures are invisible to DRC:** footprint variants, library aliasing, label shorts, muted or silently skipped checks. → [field-failure-modes](../topics/ux/field-failure-modes.md)
- **Reliability comes from:**
  - live-board verdicts;
  - observed diffs;
  - refusals;
  - one commit per step with a human-only apply;
  - per-net monotone acceptance;
  - a deterministic move library with diagnostics.

  → [agent-tooling-reliability-patterns](../topics/ux/agent-tooling-reliability-patterns.md)
- **Designers want real-time error detection, auditability, house style and locks.** → [designer-demand-and-trust](../topics/ux/designer-demand-and-trust.md)
- **Explain "why" by re-solving under the implied constraint** and showing measured deltas. Offer 2–4 alternatives; tag claims by provenance; make explanations cut verification cost. → [explanations-and-alternatives](../topics/ux/explanations-and-alternatives.md)
- **The relation bundle is the "why" record,** linked source → diagnosis → verdict, logged at decision time. → [design-rationale-and-intent-record](../topics/ux/design-rationale-and-intent-record.md)

## Open questions
- Does RAC hold on real boards with a KiCad backend? How should tight/close/loose be calibrated? → [interfaces-relations-vs-coordinates](../topics/llm/interfaces-relations-vs-coordinates.md)
- No layout-guideline benchmark, board-level recognition accuracy, or PCB designer-trust study exists. → [datasheet-extraction](../topics/llm/datasheet-extraction.md), [block-recognition](../topics/llm/block-recognition.md), [explanations-and-alternatives](../topics/ux/explanations-and-alternatives.md)
