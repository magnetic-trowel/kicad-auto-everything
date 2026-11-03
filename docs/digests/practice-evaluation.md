# Digest: expert practice, trust, verification and constraint IR

Scope: expert workflow, trust, review, evaluation, benchmarks, our harness and dev-eval, constraint IR. Not here: KiCad tools -> [ecosystem](ecosystem.md); rules -> [rules-hs-emi-interfaces](rules-hs-emi-interfaces.md), [rules-power-rf-analog-dfm](rules-power-rf-analog-dfm.md); physics scorecard -> [physics-first](physics-first.md). Ideas: [inventory](../ideas/inventory-practice-evaluation.md).
Keys: expert state machine, review gates, Olney 85% gate, layer count, EVM reuse, delegation, autorouter distrust, trust requirements, review checklist, critic stack, respins, fab holds, looks-right metrics, evaluation tiers, kaebench, score v2, harness defects, cp1_mean, pcb-intent

## Expert workflow
- Experts work constraint-first and spend judgment on placement: an 18-state backtracking state machine, three review gates (Gates 1, 3 human); placement → routing gate is Olney's 2012 test autoroute ≥85% (one source, uncalibrated). → [states](../topics/workflow/expert-state-machine.md#state-table)
- Power stage: input cap first after the IC; BGA: fan out while placing, decaps lowest mounting inductance first (value order contested). → [power](../topics/workflow/sub-workflows-power-bga-ddr.md#power-stage-switching-converter), [BGA](../topics/workflow/sub-workflows-power-bga-ddr.md#bga--cpu--memory-feranec)
- Routing ladder: power/ground and susceptible nets by hand → clocked → rest; DDR reserves channels for a whole group before finishing any. → [ladder](../topics/workflow/sub-workflows-power-bga-ddr.md#routing-priority-ladder), [DDR](../topics/workflow/sub-workflows-power-bga-ddr.md#ddr-escape-and-reserve)
- Size, layers, stackup are generate-and-test: fit check, minimum layers with clean references, +1 pair above 70% channel use (one vendor blog), fab template stackup. → [procedure](../topics/workflow/board-size-layers-stackup.md#procedure-for-the-agent)
- Copying the EVM layout is least risk, but app notes are "Wrong until Proven Right"; multichannel needs KiCad ≥9.0, design blocks ≥10.0. → [practice](../topics/workflow/layout-reuse.md#expert-practice), [KiCad primitives](../topics/workflow/layout-reuse.md#kicad-reuse-primitives)

## Practitioners
- Physics first: continuous adjacent reference plane, transfer vias at layer changes, no split crossings, rise time not clock; "looks good" is necessary, not sufficient. → [physics core](../topics/workflow/what-good-looks-like.md#physics-core-experts)
- Never delegated: stackup, floorplan and mechanics, critical nets, topology, pin/part swaps, known-good blocks; delegation follows predictability; review is side-by-side with datasheets plus an adversarial pass. → [never](../topics/workflow/delegation-and-expert-review.md#never-delegated-or-only-on-a-leash), [review](../topics/workflow/delegation-and-expert-review.md#how-experts-review)
- Autorouters are distrusted (DRC-clean ≠ works, missing intent, costly setup); trusted as probes, not producers. → [root causes](../topics/workflow/autorouter-distrust.md#root-causes), [probe vs producer](../topics/workflow/autorouter-distrust.md#where-routers-help-probe-vs-producer)
- LLMs help with review and orchestration, fail at geometry (backwards connectors, unrequested edits, score gaming). → [failures](../topics/workflow/llm-field-reports.md#where-llms-fail)
- Trust needs deterministic judges, bounded diffs with undo and locks, untouched known-good work, explanations and lower total effort including setup. → [11 requirements](../topics/workflow/trust-requirements.md#the-11-trust-requirements-practitioners-words)

## Review and verification
- 299 checklist items, 41 Critical, 80–83% of those at least semi-automatable given a semantic role layer: build it first. → [facts](../topics/verification/review-checklist.md#checklist-facts), [Critical](../topics/verification/review-checklist.md#all-41-critical-items), [full rows](../topics/verification/review-checklist.md#full-checklist-files), [sources](../topics/verification/checklist-sources.md#source-checklists-and-keys)
- Critic stack: Tier A (DRC), S (semantic geometry), J (judgment); findings carry measured value, threshold, source, image, fix; order documentation → geometry → physics. → [rules](../topics/verification/critic-stack.md#critic-stack-rules), [tiers](../topics/verification/critic-stack.md#critic-tiers)
- Respins are routine (~2.8–2.9 per project); top fab holds (AtlasPCB, self-reported): ambiguous stackup 28%, undefined impedance 22%. → [counts](../topics/verification/respin-and-fab-hold-data.md#respin-counts-and-costs), [holds](../topics/verification/respin-and-fab-hold-data.md#dfm-and-fab-holds)
- "Looks right" is measurable (orientation entropy, grid snap, Manhattan ratio); pair each neatness term with a coupling penalty. → [metrics](../topics/verification/looks-right-metrics.md#proposed-metrics)
- Tiers T0–T3: geometry per move, `kicad-cli` DRC plus router probe, PI at gates, openEMS/FEM for finalists; calibrate proxies before rewarding on them. → [tiers](../topics/verification/evaluation-stack.md#tiers)
- Router probes suit a placement loop only on small boards (KRT ≈0.65 s, Freerouting ≈7 s at ≤31 pads); large boards hit 600 s / 900 s timeouts. → [rules](../topics/verification/evaluation-stack.md#evaluation-rules)
- Metrics: union of legality (CP, NRR/PRR), efficiency and physics (Quilter PRCs); human boards score NRR 93.58%; MGS is diagnostic only; kaebench `cpk` (any-clean@k) is ≥ PCBWorld CP@5. → [rules](../topics/verification/quality-metrics.md#metric-rules), [cpk](../topics/verification/quality-metrics.md#kaebench-cpk-vs-cp5)

## Benchmarks, harness and dev-eval
- No ISPD/ICCAD PCB contest exists; PCBWorld-Bench (routing) and Cypress (placement) are de-facto standards; re-run Freerouting 2.5.0, not the published 2.1.0 baseline. → [conclusions](../topics/verification/benchmarks.md#benchmark-conclusions)
- LLMs must act through the engine: GPT-5.4 CP 0.65 interactive vs 0.02 engine-free (D3-A); PCBWorld evaluates 99 D3-A and 10 of 287 D3-B boards. → [LLM agents](../topics/routing/pcbworld.md#llm-agents), [datasets](../topics/routing/pcbworld.md#datasets)
- Plan: 11 tracks: routing/placement leaderboards plus intent, physics, checklist, trust, blind review. → [tracks](../topics/verification/benchmark-plan.md#benchmark-tracks)
- kaebench: no method scores itself; score v2 rebuilds the board from allowed changes only and runs `kicad-cli` DRC in a fresh process; external methods run sandboxed; 112 of 297 boards qualify on KiCad 10.0.7. → [invariants](../topics/verification/harness.md#harness-invariants), [yield](../topics/verification/harness.md#qualification-yield-and-first-baseline)
- Dev-eval plan: fix harness defects H1–H12 first, then routing/placement strategies; LLM arms only after measured headroom, against zero-token controls. → [summary](../topics/verification/dev-eval-plan.md#plan-summary), [defects](../topics/verification/dev-eval-plan.md#harness-defects-found)
- Protocol: gate `valid`; primary `cp1_mean`; report `cp1` and `cpk`; boards paired; guardrails fixed in advance. → [protocol](../topics/verification/dev-eval-protocol.md#evaluation-protocol)

## Constraint and intent representation
- `pcb-intent`: strict, specificity-resolved IR compiled to `.kicad_dru`, Python checkers (authoritative) and penalties; LLM proposes with provenance, human confirms. → [definition](../topics/architecture/constraint-ir.md#definition)
- Build `proximity`, `via_to_plane`, `loop_area`, `layer_switch_count` checkers first: KiCad DRC cannot express them. → [compiling](../topics/architecture/constraint-ir.md#compiling-to-kicad-10)
- Resolution differs: KiCad last match (net-class values floored at board minimum, custom rules not), Altium priority, JITX specificity, Allegro CSets; timing belongs on pad-to-pad paths. → [families](../topics/architecture/constraint-models-compared.md#three-families), [KiCad](../topics/kicad/drc-rule-language-reference.md#clearance-resolution)
- IPC-2581C carries impedance specs but no clearance or length/skew rules. → [why an IR](../topics/architecture/constraint-ir.md#why-an-ir-evidence)

## Key corrections
- `microvia_stack_depth` is master-only (`microvia_aspect_ratio` → `hole_aspect_ratio`); units only mm/mil/in/deg/ps/fs; DRC JSON has no rule-name field; KiCad 10 SES import deletes unlocked copper. → [master-only](../topics/kicad/drc-rule-language-reference.md#master-only-constraints-kicad-11-development), [units](../topics/kicad/drc-rule-language-reference.md#units), [schema](../topics/kicad/drc-report-and-repair-loop.md#schema-drcv1json-identical-on-100-and-master), [SES](../topics/kicad/specctra-freerouting-integration.md#kicad-side-dsnses)
