# Let LLMs author intent, never copper

Scope: executive map of LLM-driven KiCad placement and routing (status 2026-10-21); conclusions only, each linking to its evidence. Not here: physics-first layout -> [Physics-first report](Physics-first%20PCB%20layout.md); full map -> [docs/INDEX.md](../docs/INDEX.md).
Keys: intent compiler, Option A, pcb-intent, relations vs coordinates, PCBWorld D3, OmniRouting, Cypress, top-10 ideas, patents, KiCad 10 vs 11

Evidence caveat: many numbers are vendor-reported [V] or single-study; cross-paper scores are rarely comparable (router versions, @k, seeds, harnesses differ: [pcb-llm-benchmarks](../docs/topics/llm/pcb-llm-benchmarks.md)). Tags: [P] primary, [S] secondary, [V] vendor, [I] inference. Every architecture and original idea below is untested [I].

## Conclusions

1. **LLMs fail at geometry, succeed at semantic choices made for a solver.** Every PCB win with legal / DRC-clean output kept geometry inside an engine ([spatial-reasoning-limits](../docs/topics/llm/spatial-reasoning-limits.md), [llm-routing-evidence](../docs/topics/routing/llm-routing-evidence.md)).
2. **The write interface matters more than the model:** relation bundles 90.9% clean-pass vs coordinates 23.2% ([interfaces-relations-vs-coordinates](../docs/topics/llm/interfaces-relations-vs-coordinates.md)).
3. **The LLM's value is the criticality map and the "why"** (blocks, net roles, applicable and contested rules), confirmed by a human ([design-understanding-pipeline](../docs/topics/llm/design-understanding-pipeline.md), [checkers-power](../docs/topics/rules/checkers-power.md)).
4. **Setup is the bottleneck, not routing:** "Autorouters don't fail at routing. Nobody configures them" (DeepPCB [V]); experts distrust autorouters for wrong objective and missing intent ([commercial-architecture-patterns](../docs/topics/landscape/commercial-architecture-patterns.md), [autorouter-distrust](../docs/topics/workflow/autorouter-distrust.md)).
5. **Build Option A, a staged intent compiler, as the spine:** LLM → `pcb-intent` IR → DRC rules, placer terms, router presets, tests → engines → critics → LLM repairs commitments → human approves. Later phases add domain negotiation (B), topology-first routing for critical nets (C), overnight search (D) ([hybrid-architecture-options](../docs/topics/architecture/hybrid-architecture-options.md#recommendation); chosen design: [system-design](../docs/topics/architecture/system-design.md)).
6. **Priority submodules are exact specialist solvers** (hot-loop nH placer, decap assignment, I/O chain embedder, homotopy menus); no open tool provides any ([domain → submodule table](../docs/topics/architecture/hybrid-architecture-options.md#priority-domains--specialist-submodules)).
7. **Harness first:** built ([harness](../docs/topics/verification/harness.md), [dev-eval-plan](../docs/topics/verification/dev-eval-plan.md)). Target: beat Freerouting 2.5+ alone on PCBWorld D3 and beat Cypress-protocol routability ([benchmark-plan](../docs/topics/verification/benchmark-plan.md)).
8. **Main risks:** KiCad 10 API gaps, scarce licence-clean data, pending NVIDIA patent resembling any LLM constraint loop ([risks](#risks-and-open-questions)).

## Evidence map

| Finding | Headline number | Home |
|---|---|---|
| LLMs cannot route | OmniRouting best model 12.6% nets DRC-clean (28.0% agentic) vs open router 56.2%, humans 93.6% | [pcb-llm-benchmarks](../docs/topics/llm/pcb-llm-benchmarks.md) |
| Engines beat LLM routing | PCBWorld D3-A/B clean-pass @5: Freerouting 0.80/0.78, PPO 0.86/0.45; GPT-5.4 0.65/0.00 (a floor) | [pcbworld](../docs/topics/routing/pcbworld.md#results-table-21-5) |
| Act through the engine | GPT-5.4: 0.65 interactive, 0.19 plan-then-execute, 0.02 engine-free | [pcbworld](../docs/topics/routing/pcbworld.md#llm-agents) |
| Per-step LLM routing too costly | 0.4–1.9M tokens/board; 126× slower than PPO | [pcbworld](../docs/topics/routing/pcbworld.md#llm-agents) |
| LLM placement: connectivity-aware but illegal | OmniLayout routability 0.90–0.95 (GPT-5.5) vs 0.23–0.62 academic placers, but ~80% of outputs overlap pads (pooled, not like-for-like) | [benchmarks-and-metrics](../docs/topics/placement/benchmarks-and-metrics.md) |
| Relations, not coordinates | RAC clean-pass: bundle 90.9%, sequential relations 62.4%, coordinates 23.2%, Python 21.0%; re-solve after resizes 89.5% vs 65.6% | [interfaces-relations-vs-coordinates](../docs/topics/llm/interfaces-relations-vs-coordinates.md) |
| Bounded loops win | DRC-Aid (IC, Calibre) 92.5% vs 6.6% static; structured scores −77.1% DRC errors; images marginal | [agent-loop-patterns](../docs/topics/llm/agent-loop-patterns.md), [vision-feedback](../docs/topics/llm/vision-feedback.md) |
| LLM-guided placers work at intent level | Li DAC'26 ([S], 6 boards): −15% wirelength, −13% vias vs Quilter; VeoPlace (IC macros): VLM regions help as weak anchors (λ_A = 0.01), random regions hurt | [llm-guided-placement](../docs/topics/placement/llm-guided-placement.md) |
| Placement quality gap | OmniLayout routability: best academic 0.62, Quilter 0.84 [P]; designer placements route clean 0.56 vs 0.12–0.16 auto-placers (one unreviewed 64-board study) | [pcb-placers-2022-2026](../docs/topics/placement/pcb-placers-2022-2026.md), [imitation-and-learned-scores](../docs/topics/data/imitation-and-learned-scores.md) |
| Understanding needs tools | raw-netlist tracing 2–97% (analog CMOS); stage grouping F1 0.31 (transistor op-amps, not PCB); staged datasheet extraction 98.8% vs 76.1% one-shot | [block-recognition](../docs/topics/llm/block-recognition.md), [datasheet-extraction](../docs/topics/llm/datasheet-extraction.md) |
| Offline evolution: small gains | LLM-evolved placer/router code 0.5–2.9% generalized | [code-and-objective-evolution](../docs/topics/llm/code-and-objective-evolution.md) |
| No PCB contest benchmark | PCBWorld (routing; D3-B on 10 of 287 boards; relaxed DRC chain) and Cypress (placement) are de-facto; nothing measures guideline compliance, arbitration or trust | [benchmarks](../docs/topics/verification/benchmarks.md) |

## Why the task is hard

| Difficulty | Fact | Home |
|---|---|---|
| Combinatorics | exact placement with rotation competitive to ~100 parts; our CP-SAT: first feasible at 150–200 parts, none at 300 in 300 s; via minimization NP-complete; net order allocates resources | [cp-sat-milp-smt](../docs/topics/solvers/cp-sat-milp-smt.md), [solver benchmarks](../docs/topics/solvers/benchmarks.md), [layer-assignment-and-vias](../docs/topics/routing/layer-assignment-and-vias.md), [net-ordering](../docs/topics/routing/net-ordering.md) |
| Coupling | only quantified place→route gate: Olney ≥85% test-autoroute completion, in an 18-state backtracking workflow | [expert-state-machine](../docs/topics/workflow/expert-state-machine.md) |
| Rules conditional, vendor-keyed, contested | vendor values differ 5–25×; myths (90° corners on single-ended nets below ~2 Gb/s, 3W ≈ D/H crosstalk budget) need physics; 20-H, guards, split grounds need a selector | [rule-pack-format](../docs/topics/rules/rule-pack-format.md), [datasheet-to-constraints](../docs/topics/rules/datasheet-to-constraints.md), [myths-and-contested](../docs/topics/rules/myths-and-contested.md) |
| DRC-clean ≠ working | review checklist 299 items, 41 Critical; costliest failures invisible to DRC; ~2.9 respins/project (Lifecycle Insights, vendor-cited only) | [review-checklist](../docs/topics/verification/review-checklist.md), [field-failure-modes](../docs/topics/ux/field-failure-modes.md), [respin-and-fab-hold-data](../docs/topics/verification/respin-and-fab-hold-data.md) |

Priority domains (what dominates → rules doc):
- Power conversion: hot-loop nH (AN-139: 187 nH single-layer vs 13 nH over a plane); order IC → CIN → L/SW → COUT → [hot-loops](../docs/topics/rules/power/hot-loops.md), [buck](../docs/topics/rules/power/buck.md), [power/](../docs/topics/rules/power/).
- Decoupling / PDN: mounting inductance, not value; target impedance → [decoupling-pdn](../docs/topics/rules/decoupling-pdn.md).
- High-speed SI: continuous return path; rise time, not clock period; stubs → [si-fundamentals](../docs/topics/rules/si-fundamentals.md), [stackup](../docs/topics/rules/stackup.md).
- Diff pairs, interfaces: not self-returning; skew → common mode; vendor packs with loss budgets → [diff-pairs](../docs/topics/rules/diff-pairs.md), [interfaces/](../docs/topics/rules/interfaces/).
- RF: match at the pin; only ground under RF; module data primary → [rf](../docs/topics/rules/rf.md).
- EMI/EMC: CM voltage between cables; connectors on one edge; connector → TVS → IC → [emc-placement](../docs/topics/rules/emc-placement.md).
- Proximity-critical: crystal annulus, FB divider, ESD, Kelvin sense → [crystals-clocks](../docs/topics/rules/crystals-clocks.md), [current-sense-kelvin](../docs/topics/rules/power/current-sense-kelvin.md).
- Analog, isolation, thermal, DFM: dominant-error rules, creepage lookup chains, ΔT screening, fab minimums → [analog-mixed-signal](../docs/topics/rules/analog-mixed-signal.md), [isolation-creepage](../docs/topics/rules/isolation-creepage.md), [thermal](../docs/topics/rules/thermal.md), [dfm-fab-limits](../docs/topics/rules/dfm-fab-limits.md).

## What exists to build on

| Layer | Reuse | Limit | Home |
|---|---|---|---|
| KiCad 10 | four channels: IPC commits, `.kicad_dru` writes, `kicad-cli pcb drc` referee, SWIG DSN/SES | IPC: no DRC, rules, export, headless, route/place | [ipc-api-10-vs-11](../docs/topics/kicad/ipc-api-10-vs-11.md), [kicad-cli](../docs/topics/kicad/kicad-cli.md) |
| DRC rule language | 35 constraints, 23 functions | last matching custom rule wins, but pad/footprint clearance overrides beat every custom rule, net ties force 0, net-class values and overrides (not custom rules) floored at Board Setup minimum ([P] [drc_engine.cpp @10.0](https://gitlab.com/kicad/code/kicad/-/blob/10.0/pcbnew/drc/drc_engine.cpp)); JSON report has no rule name | [drc-rule-language-reference](../docs/topics/kicad/drc-rule-language-reference.md), [drc-report-and-repair-loop](../docs/topics/kicad/drc-report-and-repair-loop.md) |
| KiCad built-ins | component classes, Repeat Layout, design blocks | legacy autoplacer: weak baseline only, not a seed | [built-in-automation-features](../docs/topics/kicad/built-in-automation-features.md) |
| Routers | Freerouting (GPL-3.0, bulk baseline); KiCad PNS via PCBWorld-Engine (pinned KiCad 9.0.8); KRT/kicad-tools (MIT) | Freerouting: no diff pairs or meanders; KiCad 10.0 SES import deletes unlocked copper, re-adds locked | [freerouting](../docs/topics/routing/freerouting.md), [specctra-freerouting-integration](../docs/topics/kicad/specctra-freerouting-integration.md), [kicad-pns-router](../docs/topics/routing/kicad-pns-router.md) |
| Placers | Cypress (Apache-2.0) analytical | no constraint-aware open placer | [open-source-placers](../docs/topics/landscape/open-source-placers.md) |
| MCP servers | tool gating (~95% fewer catalogue tokens), plan → revision-bound apply, source tags, one undo per step | hundreds of repos; all seven routed-board tools one tester found used Freerouting; zero AI plugins in the PCM | [kicad-ai-tools-and-mcp-servers](../docs/topics/landscape/kicad-ai-tools-and-mcp-servers.md), [mcp-server-lessons](../docs/topics/kicad/mcp-server-lessons.md), [mcp-tool-surface-spec](../docs/topics/kicad/mcp-tool-surface-spec.md) |
| Checkers | kicad-happy, EMI Guardian, RF-tools | none closes constraints → route → physics check | [checkers-si-emi](../docs/topics/rules/checkers-si-emi.md) |
| Commercial | Quilter (RL + solvers, comprehension, 8 PRCs, no API [V]); DeepPCB (RL router + LLM setup agent, claims 0.929 on D3-A [V], skips DDR and length matching) | pattern: LLM configures, engines construct, checkers rank, humans approve | [quilter](../docs/topics/landscape/quilter.md), [deeppcb](../docs/topics/landscape/deeppcb.md), [commercial-incumbents-and-startups](../docs/topics/landscape/commercial-incumbents-and-startups.md) |

Missing: verified intent → DRC compiler; constraint-aware placer with independent scorer; in-loop hot-loop/PDN/return-path checkers ([checkers-power](../docs/topics/rules/checkers-power.md)); maintained multilayer topological router ([topological-routing](../docs/topics/routing/topological-routing.md)); open placement benchmark ([ecosystem digest](../docs/digests/ecosystem.md)).

## Recommended architecture

Option A spine plus a substrate (budgets, reservations, decision DAG, mutation-tested critics) that B/C/D plug into without rewrites. Domain → submodule table, phases and kill criteria: [hybrid-architecture-options](../docs/topics/architecture/hybrid-architecture-options.md#option-a--intent-compiler-on-a-staged-engine-pipeline).

1. Comprehension: deterministic detectors (VF2, rules, IBIS) + layout cards; LLM adjudicates and writes detector code ([design-understanding-pipeline](../docs/topics/llm/design-understanding-pipeline.md), [part-layout-card](../docs/topics/llm/part-layout-card.md)).
2. Brief: human confirms IR, budgets, criticality field ([constraint-ir](../docs/topics/architecture/constraint-ir.md)).
3. Compile: IR → `.kicad_dru`, placer terms, router presets, unit tests ([rule-pack-format](../docs/topics/rules/rule-pack-format.md)).
4. Place: sides → floorplan + cut check → recipe solvers → analytical GP → CP-SAT legalize → SA/LNS ([recommended-stack](../docs/topics/solvers/recommended-stack.md)); gate: probe completion ≥85% (Olney's full-test-autoroute threshold), a profile parameter calibrated per probe router.
5. Route: escape + via sites → macros → critical nets (PNS diff-pair placer, meanders in reserved slack) → bulk Freerouting/KRT → PNS repair ([diff-pair-routing](../docs/topics/routing/diff-pair-routing.md), [escape-routing](../docs/topics/routing/escape-routing.md)).
6. Critics → LLM repair: DRC + semantic + physics findings with price tags; LLM relaxes/substitutes commitments from bounded menus; human approves each apply ([critic-stack](../docs/topics/verification/critic-stack.md)).

The LLM never emits coordinates. Estimated cost 50–200k tokens/board (not derived or measured) vs 0.4–1.9M for PCBWorld step-routing agents [I]. Phase-1 exit: beat Freerouting 2.5+ alone on D3 (clean pass with SI PRCs) and Cypress-protocol routability. Phase 3 keeps topology-first only if critical-net SI PRC pass and vias beat PNS+Freerouting at <50k tokens/board ([phases](../docs/topics/architecture/hybrid-architecture-options.md#recommendation)).

## First ideas and experiments

Try first (of 58 ideas): P6 slot assignment, N8 decap-to-pin, N7 hot-loop nH micro-placer, V2 red-team reward hacker, V1 mutation-tested tests, I4 price tags, I1+I2 budget ledger and typed units, R2 shadow returns, P1 router-probe pseudo-gradients, R1 homotopy menus → [top 10](../docs/ideas/original/README.md#top-10-to-try-first-impact-vs-effort). P6 first: swapping interchangeable parts drops designer clean-route 0.56 → 0.31–0.39 (one unreviewed study; the swaps also added pre-route DRC errors). P1 cost: KRT ~0.65 s per ≤31-pad D3-A board. Runners-up S4, P4, U3. Transplants (PCB-PSDL program with LLM-free repair: 3-D scenes preferred 94.3% over Holodeck, 82.9% over a declarative DSL; self-consistent relations; VLM regions; sparrow-style legalizer) → [cross-domain-transplants](../docs/ideas/cross-domain-transplants.md).

Experiments run in the harness (pinned KiCad, re-opened saved files, no method scores itself); kill criteria marked [I] are our proposals:

| # | Experiment | Baseline | Kill criterion |
|---|---|---|---|
| 0 | harness: PCBWorld D3 @5, Cypress protocol, placement-stripped D3 (kaebench built; D3 import and Cypress protocol to add) | published Freerouting 0.80/0.78, KRT 0.74/0.20; re-run Freerouting 2.5.0 pinned | no agent work until reproduced within [dev-eval-plan](../docs/topics/verification/dev-eval-plan.md) tolerance [I]; kaebench `cpk` = any-clean@k, never below PCBWorld best-potential CP@5 |
| 1 | relational planner + engines on D3 with SI constraints | Freerouting alone; DeepPCB | Phase-1 exit (clean pass, SI PRC pass, tokens) |
| 2 | P6 slot stage on/off | same placer without P6 | no clean-route gain [I] |
| 3 | N7 on 30 converters, 5 checked with FastHenry/openEMS | EVM layout; generic placer with `loop_area` | worse nH than generic placer, or L_est disagrees with extraction [I] |
| 4 | N8 on 20 MCU/FPGA boards | "smallest closest"; designer | weighted L_mount, PDN peak/Z_t no better than smallest-closest [I] |
| 5 | R1 homotopy menu vs free-form hints | Freerouting alone | Phase-3 criterion (tokens <50k) |
| 6 | VLM regions as weak anchors | random-region control | no routability gain [I] |
| 7 | V1/V2: 100 seeded faults on 10 boards | DRC alone; unvalidated LLM tests | gate: no RL or evolution until escaped-defect rate passes |

## Risks and open questions

- Patents (identification only, not legal analysis): Cadence US 11,599,699, 12,223,248; InstaDeep US 11,842,136, 12,019,968, 12,159,094 (NN-guided SMC over net orders); pending NVIDIA US 2025/0315590 A1 (LLM in a ReAct loop updating constraints) resembles all four options: collect prior art from before 2024-04-03. No granted patent on LLM-driven PCB layout found ([patents-watchlist](../docs/topics/landscape/patents-watchlist.md)).
- Licensing: GPL-3.0-or-later code runs GPL engines in-process; policy and denied families -> [LICENSING.md](../LICENSING.md#rules-for-dependencies-and-reused-material); per-component verdicts (OptiMathSAT AVOID, Gurobi never bundled) -> [reuse-matrix](../docs/topics/licensing/reuse-matrix.md); base models Apache/MIT only -> [data-rulepacks-weights](../docs/topics/licensing/data-rulepacks-weights.md#model-weights).
- Data: PCBench 54–62% unlicensed (docs disagree), 23 KiCad 6+ boards; 33% of licensed boards pass own DRC; expect low thousands usable → priors, synthetic, planted-solution boards ([corpora-and-yield](../docs/topics/data/corpora-and-yield.md), [learning-and-data](../docs/ideas/original/learning-and-data.md)).
- KiCad 10 vs 11: neither exposes run-DRC/route/place over IPC; 11 (~Q1 2027) adds headless, rules, DSN/SES; 9→10 dialects can silently miswire; PCBWorld-Engine pins 9.0.8, so Option A's PNS stages (critical nets, repair) carry this risk from Phase 1. Keep a `BoardSession` abstraction ([ipc-api-10-vs-11](../docs/topics/kicad/ipc-api-10-vs-11.md), [file-format-and-version-hazards](../docs/topics/kicad/file-format-and-version-hazards.md), [kicad-pns-router](../docs/topics/routing/kicad-pns-router.md)).
- Unverified: Quilter, DeepPCB, TopoR, Freerouting "clean" rates are self-reported (Freerouting nightly uses its own check, not KiCad DRC) ([freerouting](../docs/topics/routing/freerouting.md)); RAC untested on real boards with a KiCad backend; budget spend models and EMI proxy uncalibrated.
- Open: does a domain market converge? how to calibrate tight/close/loose? no PCB designer-trust study ([explanations-and-alternatives](../docs/topics/ux/explanations-and-alternatives.md), [trust-requirements](../docs/topics/workflow/trust-requirements.md)).

## Where to find details

Digests: [algorithms](../docs/digests/algorithms.md), [llm-data-ux](../docs/digests/llm-data-ux.md), [ecosystem](../docs/digests/ecosystem.md), [rules-hs-emi-interfaces](../docs/digests/rules-hs-emi-interfaces.md), [rules-power-rf-analog-dfm](../docs/digests/rules-power-rf-analog-dfm.md), [practice-evaluation](../docs/digests/practice-evaluation.md). Ideas: [original catalog](../docs/ideas/original/README.md). Raw evidence: [research notes](../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/).
