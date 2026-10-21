# Digest: expert practice, trust, verification and constraint IR

Each statement below links to the topic doc that holds the detail and evidence. Every idea is also listed in the [idea inventory](../ideas/inventory-practice-evaluation.md).

## Expert workflow

- **Experts work constraint-first and spend their judgment on placement.**
  - A test autoroute reaching ≥85% completion is the gate from placement to routing.
  - The workflow maps onto an 18-state backtracking state machine with three review gates.

  → [expert-state-machine](../topics/workflow/expert-state-machine.md)
- **Three micro-workflows recur:**
  - power stage: place and route the input cap first; shorten loops before widening traces;
  - BGA: fan out while placing; stage decaps nF → µF → bulk;
  - routing ladder: power/susceptible nets → clocked → rest, with DDR channels reserved before buses are completed.

  → [sub-workflows](../topics/workflow/sub-workflows-power-bga-ddr.md)
- **Size, layers and stackup are generate-and-test.**
  - Run a fit check first.
  - Use the minimum layer count that gives a solid reference, plus two layers if channel use exceeds 70%.
  - Start from a fab template stackup and check that the impedance widths are reasonable.

  → [board-size-layers-stackup](../topics/workflow/board-size-layers-stackup.md)
- **Copying the EVM layout is the least-risk path, but app notes are "Wrong until Proven Right".** KiCad 9 adds multichannel layout; KiCad 10 adds PCB design blocks. → [layout-reuse](../topics/workflow/layout-reuse.md)

## Practitioners

- **Physics comes first**: one dielectric to a continuous reference plane, transfer vias at layer changes, no split crossings, and rise time over clock frequency. "Looks good" is necessary but not sufficient. → [what-good-looks-like](../topics/workflow/what-good-looks-like.md)
- **Never delegated:** stackup, floorplan and connectors, hot loops, pin and part swaps, topology choices, known-good blocks.
  **Delegated:** length matching, buses, fanout, stitching, low-speed nets.
  **Expert review:** side-by-side datasheet checks plus an adversarial second pass. → [delegation-and-expert-review](../topics/workflow/delegation-and-expert-review.md)
- **Autorouters are distrusted** for a wrong objective (DRC-clean ≠ working), missing intent, and setup costing as much as hand routing. They are trusted as probes, not producers. → [autorouter-distrust](../topics/workflow/autorouter-distrust.md)
- **LLMs review and orchestrate well but fail at geometry:** backwards connectors, routing loops, unrequested edits, score gaming. → [llm-field-reports](../topics/workflow/llm-field-reports.md)
- **What earns trust:**
  - deterministic tools judge correctness;
  - work in bounded chunks with diffs, undo and locks;
  - known-good work is never touched;
  - every step is explained;
  - results are deterministic;
  - total effort, setup included, is lower than hand layout.

  → [trust-requirements](../topics/workflow/trust-requirements.md)

## Review and verification

- **299 checklist items, 41 of them Critical**; 83% of the Critical items are at least semi-automatable once a semantic role layer exists. → [review-checklist](../topics/verification/review-checklist.md), [checklist-sources](../topics/verification/checklist-sources.md)

  Full lists:
  - [process/DFM/stackup](../topics/verification/checklist-full-process-dfm-stackup.md)
  - [mechanical/placement/footprints](../topics/verification/checklist-full-mechanical-placement-footprints.md)
  - [power/ground/HS/RF/EMC](../topics/verification/checklist-full-power-ground-hs-rf-emc.md)
  - [thermal/routing/assembly/test](../topics/verification/checklist-full-thermal-routing-assembly-test.md)
  - [silk/HV/outputs/panel/flex](../topics/verification/checklist-full-silk-hv-outputs-panel-flex.md)
- **Critic stack**: tier A (DRC), tier S (semantic geometry), tier J (LLM judge plus simulation).
  - Each finding carries measured value, threshold, source, image and fix.
  - Order: documentation → geometry → physics.

  → [critic-stack](../topics/verification/critic-stack.md)
- **Respins are routine** (~2.9 per project). The top fab holds are ambiguous stackup (28%) and undefined impedance (22%). → [respin-and-fab-hold-data](../topics/verification/respin-and-fab-hold-data.md)
- **"Looks right" can be measured**: orientation entropy, grid snap, Manhattan ratio, hot-loop area, decap order. Always pair these with a coupling penalty. → [looks-right-metrics](../topics/verification/looks-right-metrics.md)
- **Four evaluation tiers:**
  - geometry on every move;
  - `kicad-cli` DRC plus a router probe (0.65–10 s);
  - 2.5D PI;
  - openEMS/FEM for finalists.

  Calibrate the proxies before rewarding against them. → [evaluation-stack](../topics/verification/evaluation-stack.md)
- **Metrics**: combine PCBWorld CP, OmniRouting NRR/PRR, Quilter physics checks and Cypress routability. Use human-similarity (MGS) as a diagnostic only; human boards score NRR 93.58%. → [quality-metrics](../topics/verification/quality-metrics.md)
- **There are no PCB contest benchmarks.**
  - PCBWorld (routing) and Cypress (placement) are the de-facto standards.
  - Acting through the engine matters: CP 0.65 vs 0.02 without it.
  - Re-run Freerouting 2.5.0 rather than reuse the published 2.1.0 baseline (0.80/0.78).

  → [benchmarks](../topics/verification/benchmarks.md)
- **Plan:**
  - PCBWorld D3 routing;
  - Cypress and placement-stripped placement;
  - tracks for intent, physics, human-relative scoring, seeded checklist faults, trust and blind review.

  → [benchmark-plan](../topics/verification/benchmark-plan.md)

## Constraint and intent representation

- **A strict, specificity-resolved `pcb-intent` IR.**
  - It compiles to `.kicad_dru`, Python checkers and optimizer penalties.
  - The LLM authors intents with provenance, and humans confirm them.
  - Proximity, via-to-plane and loop area need custom checkers.

  → [constraint-ir](../topics/architecture/constraint-ir.md)
- **Rule resolution differs by tool:** KiCad uses last match, Altium priority, JITX specificity, Allegro CSets. Timing belongs on pad-to-pad topologies. IPC-2581C carries impedance but no placement or routing rules. → [constraint-models-compared](../topics/architecture/constraint-models-compared.md)

## Key corrections (verification note)

- `microvia_*` constraints are master-only.
- DRC units are only mm/mil/in/deg/ps/fs.
- DRC JSON has no rule-name field.
- KiCad 10 SES import deletes unlocked copper.
- PCBWorld D3-B has only 10 boards.

→ [constraint-ir](../topics/architecture/constraint-ir.md), [evaluation-stack](../topics/verification/evaluation-stack.md), [benchmarks](../topics/verification/benchmarks.md)
