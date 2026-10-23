# Let LLMs author intent, never copper

LLMs can make KiCad layout much better only by changing their job: instead of drawing geometry, they compile design intent, the "why", into constraints, priorities and repairs that solvers carry out. Each statement links to the [docs tree](../docs/INDEX.md), which holds numbers, sources and caveats. Status: 2026-10-21.

**Evidence caveat.** Many numbers are vendor-reported or single-study, and cross-paper scores are rarely comparable (router versions, @k, seeds and harnesses differ; [pcb-llm-benchmarks](../docs/topics/llm/pcb-llm-benchmarks.md)). The topic docs tag each claim [P] primary, [S] secondary, [V] vendor or [I] inference. Every architecture and original idea here is untested [I].

## 1. Bottom line

- **LLMs fail at geometry and succeed at semantic choices made for a solver.** Every PCB result where an LLM system won with a legal or DRC-clean output kept the geometry inside an engine ([spatial-reasoning-limits](../docs/topics/llm/spatial-reasoning-limits.md), [llm-routing-evidence](../docs/topics/routing/llm-routing-evidence.md)).
- **The write interface matters more than the model.** Relation bundles reach 90.9% clean-pass against 23.2% for coordinates ([interfaces-relations-vs-coordinates](../docs/topics/llm/interfaces-relations-vs-coordinates.md)).
- **The LLM's real value is the criticality map and the "why":** blocks, net roles, applicable rules and contested rules, all confirmed by a human ([checkers-power](../docs/topics/rules/checkers-power.md), [design-understanding-pipeline](../docs/topics/llm/design-understanding-pipeline.md)).
- **Setup is the bottleneck, not routing.** "Autorouters don't fail at routing. Nobody configures them" (DeepPCB [V]). Experts distrust autorouters for their wrong objective and missing intent ([commercial-architecture-patterns](../docs/topics/landscape/commercial-architecture-patterns.md), [autorouter-distrust](../docs/topics/workflow/autorouter-distrust.md)).
- **Build a staged intent compiler (Option A):** LLM → `pcb-intent` IR → DRC rules, placer terms, router presets and tests → engines → critics → the LLM repairs commitments → a human approves. Add domain negotiation, topology-first routing for critical nets, and overnight search as later phases ([hybrid-architecture-options](../docs/topics/architecture/hybrid-architecture-options.md)).
- **Priority submodules should be exact specialist solvers** (hot-loop nH placer, decap assignment, I/O chain embedder, homotopy menus). No open tool provides any of them ([original ideas](../docs/ideas/original/README.md)).
- **Build the benchmark harness first.** It now exists ([harness](../docs/topics/verification/harness.md)); its development and evaluation plan is [dev-eval-plan](../docs/topics/verification/dev-eval-plan.md). The target is to beat Freerouting 2.5+ alone on PCBWorld D3 and to beat Cypress-protocol routability ([benchmark-plan](../docs/topics/verification/benchmark-plan.md)).
- **Main risks:** KiCad 10 API gaps, scarce licence-clean data, and a pending NVIDIA patent that resembles any LLM constraint loop (see §8).

## 2. What the evidence says

| Finding | Key numbers | Detail |
|---|---|---|
| LLMs cannot route | OmniRouting: best model 12.6% of nets DRC-clean (28.0% agentic), against 56.2% for an open router and 93.6% for humans | [pcb-llm-benchmarks](../docs/topics/llm/pcb-llm-benchmarks.md) |
| Engines beat LLM routing on real boards | PCBWorld D3-A/B clean-pass @5 (99 and 10 evaluation boards): Freerouting 2.1.0 (`-mp 10`) 0.80/0.78 and PPO 0.86/0.45, both 4-seed means; GPT-5.4 0.65/0.00, one best-of-5 run. LLMs ran without DRC feedback, so their scores are a floor | [pcbworld](../docs/topics/routing/pcbworld.md) |
| Acting through the engine is decisive | GPT-5.4: 0.65 interactive, 0.19 plan-then-execute, 0.02 engine-free | [measured-tool-comparisons](../docs/topics/landscape/measured-tool-comparisons.md) |
| Per-step LLM routing is too costly | 0.4–1.9M tokens per board (2-layer boards of ≤31 and ≤100 pads); 126× slower than PPO | [pcbworld](../docs/topics/routing/pcbworld.md) |
| LLM placement is connectivity-aware but illegal | Routability 0.90–0.95 (GPT-5.5) against 0.23–0.62 for academic placers, but ~80% of outputs overlap pads | [benchmarks-and-metrics](../docs/topics/placement/benchmarks-and-metrics.md) |
| Relations, not coordinates | RAC clean-pass: bundle 90.9%, sequential relations 62.4%, coordinates 23.2%, Python 21.0%. Re-solve after resizes: 89.5% against 65.6% | [interfaces-relations-vs-coordinates](../docs/topics/llm/interfaces-relations-vs-coordinates.md) |
| Bounded loops win | DRC-Aid (IC layouts, Calibre) 92.5% vs 6.6% for static prompting. Structured scores cut DRC errors 77.1%; images help only marginally | [agent-loop-patterns](../docs/topics/llm/agent-loop-patterns.md), [vision-feedback](../docs/topics/llm/vision-feedback.md) |
| LLM-guided placers work at the intent level | Li DAC'26 (survey-reported [S], 6 boards): −15% wirelength and −13% vias vs Quilter. VeoPlace (IC macro placement): VLM regions help as weak anchors (its λ_A = 0.01); random regions hurt | [llm-guided-placement](../docs/topics/placement/llm-guided-placement.md) |
| Placement quality gap | OmniLayout routability: best academic placer 0.62, Quilter 0.84 [P]. Designer placements route clean 0.56 vs 0.12–0.16 for auto-placers (one unreviewed 64-board study) | [pcb-placers-2022-2026](../docs/topics/placement/pcb-placers-2022-2026.md), [imitation-and-learned-scores](../docs/topics/data/imitation-and-learned-scores.md) |
| Understanding needs tools | Raw-netlist tracing 2–97% accurate (analog CMOS netlists); stage grouping F1 0.31 (transistor-level op-amps, not PCB). Staged datasheet extraction reaches 98.8% vs 76.1% one-shot | [block-recognition](../docs/topics/llm/block-recognition.md), [datasheet-extraction](../docs/topics/llm/datasheet-extraction.md) |
| Offline evolution gives small gains | LLM-evolved placer and router code: 0.5–2.9% generalized gain | [code-and-objective-evolution](../docs/topics/llm/code-and-objective-evolution.md) |

**Benchmarks.** No PCB contest benchmark exists; PCBWorld (routing; its published D3-B results use 10 of its 287 boards, and its chain edited `.kicad_pro` severities, ignoring some checks and zeroing some floors) and Cypress (placement) are de-facto standards. Nothing measures guideline compliance, cross-domain arbitration or designer trust ([benchmarks](../docs/topics/verification/benchmarks.md)).

## 3. Why the task is hard

- **Combinatorics.** Monolithic exact placement with rotation stays competitive only to ~100 parts; our CP-SAT found first feasible solutions at 150–200 parts and none at 300 within 300 s ([cp-sat-milp-smt](../docs/topics/solvers/cp-sat-milp-smt.md), [measurements](../docs/topics/solvers/benchmarks.md)). Via minimization is NP-complete ([layer-assignment-and-vias](../docs/topics/routing/layer-assignment-and-vias.md)). Net order decides which nets get the good resources ([net-ordering](../docs/topics/routing/net-ordering.md)).
- **Coupling.** Placement sets routability. The one quantified placement-to-routing gate is Olney's ≥85% test-autoroute completion, inside an 18-state backtracking workflow ([expert-state-machine](../docs/topics/workflow/expert-state-machine.md)).
- **Rules are conditional, vendor-keyed and contested.** Vendor values differ 5–25×, and many published numbers have lost their conditions. Myths such as 90° corners (on single-ended nets below about 2 Gb/s) and 3W (a stand-in for a D/H crosstalk budget) need a physics replacement; contested or context-dependent rules such as 20-H, guard traces and split grounds need a selector ([rule-pack-format](../docs/topics/rules/rule-pack-format.md), [datasheet-to-constraints](../docs/topics/rules/datasheet-to-constraints.md), [myths-and-contested](../docs/topics/rules/myths-and-contested.md)).
- **DRC-clean ≠ working.** The review checklist has 299 items, 41 of them Critical. The costliest failures are invisible to DRC, and respins average ~2.9 per project (Lifecycle Insights, cited only in vendor marketing; [review-checklist](../docs/topics/verification/review-checklist.md), [field-failure-modes](../docs/topics/ux/field-failure-modes.md), [respin-and-fab-hold-data](../docs/topics/verification/respin-and-fab-hold-data.md)).

| Priority domain | What dominates | Rules docs |
|---|---|---|
| Power conversion | Hot-loop inductance in nH (AN-139: 187 nH single-layer vs 13 nH over a plane, for a 10 × 10 cm test loop at 27 MHz; real hot loops are 2–20 mm², SNVA803: 2 mm² < 0.5 nH); order IC → CIN → L/SW → COUT | [hot-loops](../docs/topics/rules/power/hot-loops.md), [buck](../docs/topics/rules/power/buck.md), [power/](../docs/topics/rules/power/) |
| Decoupling / PDN | Mounting inductance, not capacitor value; target impedance | [decoupling-pdn](../docs/topics/rules/decoupling-pdn.md) |
| High-speed SI | Continuous return path; rise time, not clock period; stubs | [si-fundamentals](../docs/topics/rules/si-fundamentals.md), [stackup](../docs/topics/rules/stackup.md) |
| Diff pairs, interfaces | Pairs are not self-returning; skew turns into common mode; vendor packs with loss budgets | [diff-pairs](../docs/topics/rules/diff-pairs.md), [interfaces/](../docs/topics/rules/interfaces/) |
| RF | Match at the pin; only ground under RF; module data is primary | [rf](../docs/topics/rules/rf.md) |
| EMI/EMC | Common-mode voltage between cables; connectors on one edge; connector → TVS → IC order | [emc-placement](../docs/topics/rules/emc-placement.md) |
| Proximity-critical | Crystal annulus, FB divider, ESD, Kelvin sense | [crystals-clocks](../docs/topics/rules/crystals-clocks.md), [current-sense-kelvin](../docs/topics/rules/power/current-sense-kelvin.md) |
| Analog, isolation, thermal, DFM | Dominant-error rules; creepage lookup chains; ΔT screening; fab minimums | [analog-mixed-signal](../docs/topics/rules/analog-mixed-signal.md), [isolation-creepage](../docs/topics/rules/isolation-creepage.md), [thermal](../docs/topics/rules/thermal.md), [dfm-fab-limits](../docs/topics/rules/dfm-fab-limits.md) |

## 4. What exists to build on

| Layer | Reuse | Limits |
|---|---|---|
| KiCad 10 | Four-channel backend: IPC commits, `.kicad_dru` writes, `kicad-cli pcb drc` as referee, SWIG DSN/SES | IPC has no DRC, rules, export, headless mode or route/place calls ([ipc-api-10-vs-11](../docs/topics/kicad/ipc-api-10-vs-11.md), [kicad-cli](../docs/topics/kicad/kicad-cli.md)) |
| DRC rule language | 35 constraints, 23 functions | The last matching custom rule wins, but pad/footprint clearance overrides beat every custom rule, net ties force 0, and net-class values and overrides (not custom rules) are floored at the Board Setup minimum ([P] [drc_engine.cpp @10.0](https://gitlab.com/kicad/code/kicad/-/blob/10.0/pcbnew/drc/drc_engine.cpp)); the JSON report has no rule name ([drc-rule-language-reference](../docs/topics/kicad/drc-rule-language-reference.md), [drc-report-and-repair-loop](../docs/topics/kicad/drc-report-and-repair-loop.md)) |
| KiCad built-ins | Component classes, Repeat Layout, design blocks | Use the legacy autoplacer only as a weak baseline, not as a seed ([built-in-automation-features](../docs/topics/kicad/built-in-automation-features.md)) |
| Routers | Freerouting (GPL-3.0, bulk baseline); KiCad PNS via PCBWorld-Engine (pinned to KiCad 9.0.8); KRT/kicad-tools (MIT) | Freerouting does not route diff pairs or meanders; SES import in KiCad 10.0 deletes unlocked copper and re-adds locked copper ([freerouting](../docs/topics/routing/freerouting.md), [specctra-freerouting-integration](../docs/topics/kicad/specctra-freerouting-integration.md), [kicad-pns-router](../docs/topics/routing/kicad-pns-router.md)) |
| Placers | Cypress (Apache-2.0) analytical engine | No constraint-aware open placer exists ([open-source-placers](../docs/topics/landscape/open-source-placers.md)) |
| MCP servers | Lessons: tool gating (~95% fewer catalogue tokens), plan → revision-bound apply, source tags, one undo per step | Hundreds of repos; all seven tools one tester found that produced routed boards used Freerouting; zero AI plugins in the PCM ([kicad-ai-tools-and-mcp-servers](../docs/topics/landscape/kicad-ai-tools-and-mcp-servers.md), [mcp-server-lessons](../docs/topics/kicad/mcp-server-lessons.md), [mcp-tool-surface-spec](../docs/topics/kicad/mcp-tool-surface-spec.md)) |
| Checkers | kicad-happy, EMI Guardian, RF-tools | No tool closes the loop from constraints to route to physics check ([checkers-si-emi](../docs/topics/rules/checkers-si-emi.md)) |
| Commercial | Quilter: RL + solvers, comprehension, 8 PRCs, no API [V]. DeepPCB: RL router + LLM setup agent; claims 0.929 on D3-A [V]; skips DDR and length matching | Shared pattern: the LLM configures, engines construct, checkers rank, humans approve ([quilter](../docs/topics/landscape/quilter.md), [deeppcb](../docs/topics/landscape/deeppcb.md), [commercial-incumbents-and-startups](../docs/topics/landscape/commercial-incumbents-and-startups.md)) |

**What is missing:** a verified intent → DRC compiler; a constraint-aware placer with an independent scorer; in-loop hot-loop, PDN and return-path checkers ([checkers-power](../docs/topics/rules/checkers-power.md)); a maintained multilayer topological router ([topological-routing](../docs/topics/routing/topological-routing.md)); an open placement benchmark ([ecosystem digest](../docs/digests/ecosystem.md)).

## 5. Recommended architecture

Build **Option A, a staged intent compiler, as the spine**, with a substrate (budgets, reservations, decision DAG, mutation-tested critics) that later options plug into without rewrites ([hybrid-architecture-options](../docs/topics/architecture/hybrid-architecture-options.md)).

1. **Comprehension.** Deterministic detectors (VF2, rules, IBIS) and layout cards; the LLM adjudicates and writes detector code ([design-understanding-pipeline](../docs/topics/llm/design-understanding-pipeline.md), [part-layout-card](../docs/topics/llm/part-layout-card.md)).
2. **Brief.** A human confirms the IR, budgets and criticality field ([constraint-ir](../docs/topics/architecture/constraint-ir.md)).
3. **Compile.** The IR compiles to `.kicad_dru`, placer terms, router presets and unit tests ([rule-pack-format](../docs/topics/rules/rule-pack-format.md)).
4. **Place:** sides → floorplan with cut check → recipe solvers → analytical global placement → CP-SAT legalization → SA/LNS ([recommended-stack](../docs/topics/solvers/recommended-stack.md)). Gate: probe completion ≥85%, Olney's threshold for a full test autoroute, kept as a profile parameter to calibrate per probe router ([expert-state-machine](../docs/topics/workflow/expert-state-machine.md)).
5. **Route:** escape and via sites → macros → critical nets (PNS diff-pair placer, meanders in reserved slack) → bulk with Freerouting/KRT → PNS repair ([diff-pair-routing](../docs/topics/routing/diff-pair-routing.md), [escape-routing](../docs/topics/routing/escape-routing.md)).
6. **Critics, then LLM repair.** DRC plus semantic and physics checkers produce findings with price tags. The LLM relaxes or substitutes commitments from bounded menus, and a human approves each apply ([critic-stack](../docs/topics/verification/critic-stack.md)).

The LLM never emits coordinates. Its estimated cost, not yet derived or measured, is 50–200k tokens per board, against 0.4–1.9M for PCBWorld's step-routing agents on 2-layer boards of ≤31 and ≤100 pads [I].

**Priority submodules mapped to domains** ([hybrid-architecture-options](../docs/topics/architecture/hybrid-architecture-options.md)):

| Domain | Submodule | Engine | Tier |
|---|---|---|---|
| Power conversion | N7 nH micro-placer, R6 hot-loop macros, R7 plane partitions | CP-SAT/DFS, generators | 1 |
| RF | N9 antenna→match→IC chain, R6 RF macros | DP + CP-SAT | 1 |
| High-speed, diff pairs | N9 I/O chains, R1 homotopy menus, R2 shadow returns, R3 via sites, R8 PNS beam | MCF/SAT escape, PNS | 2 |
| Proximity-critical | P3 slack templates, N9, R6 | PSDL program + repair | 2 |
| Decoupling / PDN | N8 assignment + PDN screener | min-cost flow, lumped RLC | 2 |
| EMI/EMC, thermal | P8 connector-voltage proxy, P4 side cut; ΔT budgets | analytical penalties, screeners | spans tiers |
| DFM / mechanical | fab packs, locked anchors | legalizer constraints | hard |
| Bulk signals | R5 router-portfolio bandit | Freerouting / KRT / PathFinder | last |

**Phases** ([hybrid-architecture-options](../docs/topics/architecture/hybrid-architecture-options.md)):

| Phase | Adds | Kill / exit criterion |
|---|---|---|
| 1 A-core | Substrate, eight of the top-10 ideas (R1 and R2 come in Phase 3), Freerouting/KRT bulk; review mode ships first | Beat Freerouting 2.5+ alone on D3 (clean pass with SI PRCs) and Cypress-protocol routability |
| 2 B-lite | Veto-with-proof, rule court, reservations, ε-lexicographic tiers; N1 market only for contested resources | Drop N1 if it doesn't beat ε-lexicographic on per-domain PRC pass |
| 3 C on critical nets | R1, R2, R3, R8 on HS/RF nets only | Keep only if critical-net SI PRC pass and vias beat PNS+Freerouting at <50k tokens/board |
| 4 D overnight | Successive halving, QD alternatives, bandit dispatch, evolved orchestration | Better best-of-portfolio at equal wall-clock; the red team finds no new hacks |

## 6. Original ideas: top 10 to try first

Out of 58 ideas ([catalog](../docs/ideas/original/README.md)):

| # | Idea | Why first | Effort | Detail |
|---|---|---|---|---|
| 1 | P6 Slot assignment | Swapping interchangeable parts drops designer clean-route from 0.56 to 0.31–0.39 (one unreviewed study; the swaps also added pre-route DRC errors) | S | [placement](../docs/ideas/original/placement.md) |
| 2 | N8 Decap-to-pin assignment over mounting L | Turns a contested slogan into an exact optimization | S | [priority-agents](../docs/ideas/original/priority-agents-and-negotiation.md) |
| 3 | N7 Hot-loop nH micro-placer | The top rule in every source; no open tool | S–M | [priority-agents](../docs/ideas/original/priority-agents-and-negotiation.md) |
| 4 | V2 Red-team reward hacker | Required before RL or evolution | S | [verification](../docs/ideas/original/verification.md) |
| 5 | V1 Mutation-tested layout tests | Makes LLM-written checks sensitive to near-miss faults (not proof that their limits are right) | S–M | [verification](../docs/ideas/original/verification.md) |
| 6 | I4 Constraint price tags | Puts numbers behind negotiation and explanation | S–M | [intent-and-why](../docs/ideas/original/intent-and-why.md) |
| 7 | I1+I2 Physics budget ledger, typed units | Shared "why" vocabulary in nH, ps, dB | M | [intent-and-why](../docs/ideas/original/intent-and-why.md) |
| 8 | R2 Shadow return nets | Makes return continuity routable | M | [routing](../docs/ideas/original/routing.md) |
| 9 | P1 Router-probe pseudo-gradients | Probe forces augment RUDY (KRT ~0.65 s per ≤31-pad D3-A board; slower on larger boards) | M | [placement](../docs/ideas/original/placement.md) |
| 10 | R1 Homotopy menus | Puts the LLM on topology through a bounded menu | M | [routing](../docs/ideas/original/routing.md) |

Cheap runners-up are S4 predict-before-check, P4 side cut and U3 expected-loss brief. The top cross-domain transplants are the PCB-PSDL placement program with LLM-free repair (3-D scenes: preferred 94.3% over Holodeck, 82.9% over a declarative DSL), self-consistent relations, VLM regions and a sparrow-style legalizer ([cross-domain-transplants](../docs/ideas/cross-domain-transplants.md)).

## 7. Roadmap: first experiments

Run everything in the harness: pinned KiCad, re-opened saved files, no method scoring itself ([benchmark-plan](../docs/topics/verification/benchmark-plan.md), [harness](../docs/topics/verification/harness.md), [dev-eval-plan](../docs/topics/verification/dev-eval-plan.md)). Test designs come from the [idea docs](../docs/ideas/original/README.md); kill criteria marked [I] are our proposals.

| # | Experiment | Baseline | Metric | Kill criterion |
|---|---|---|---|---|
| 0 | Harness (kaebench is built; D3 import and the Cypress protocol are still to add): PCBWorld D3 @5, Cypress protocol, placement-stripped D3 | Published Freerouting 0.80/0.78 and KRT 0.74/0.20; re-run Freerouting 2.5.0 (pinned) | Reproduction within the tolerance set in [dev-eval-plan](../docs/topics/verification/dev-eval-plan.md). kaebench's `cpk` is any-clean@k, never below PCBWorld's best-potential CP@5 | No agent work until it reproduces [I] |
| 1 | Relational planner + engines on D3 with SI constraints ([routing/llm-routing-evidence](../docs/topics/routing/llm-routing-evidence.md)) | Freerouting alone; DeepPCB | Clean pass, SI PRC pass, tokens | Phase-1 exit above |
| 2 | P6 slot stage on/off | Same placer without P6 | Clean-route rate, crossings | No clean-route gain [I] |
| 3 | N7 on 30 converters; 5 checked with FastHenry/openEMS | EVM layout; generic placer with `loop_area` | Estimated nH, area | Worse nH than the generic placer, or L_est disagrees with extraction [I] |
| 4 | N8 on 20 MCU/FPGA boards | "Smallest closest"; designer | Weighted L_mount, PDN peak/Z_t | No gain over smallest-closest [I] |
| 5 | R1 homotopy menu vs free-form hints | Freerouting alone | Critical-net SI PRC, completion, tokens <50k | Phase-3 criterion |
| 6 | VLM regions as weak anchors | Random-region control | Routability | No gain over the random control [I] |
| 7 | V1/V2: 100 seeded faults on 10 boards | DRC alone; unvalidated LLM tests | Escaped-defect rate | Gate: no RL or evolution until passed |

## 8. Risks and open questions

- **Patents (identification only, not legal analysis):**
  - Cadence US 11,599,699 and 12,223,248.
  - InstaDeep US 11,842,136, 12,019,968 and 12,159,094 (NN-guided SMC over net orders).
  - Pending NVIDIA US 2025/0315590 A1: an LLM in a ReAct loop updating constraints. All four architecture options resemble it, so collect prior art from before 2024-04-03.
  - No granted patent on LLM-driven PCB layout was found ([patents-watchlist](../docs/topics/landscape/patents-watchlist.md)).
- **Licensing.** Code is GPL-3.0-or-later, so Freerouting, PNS, PCBWorld-Engine and kiutils can run in-process. Avoid GPL-2.0-only, AGPL (reference only), non-commercial code, Triangle, OptiMathSAT and bundled Gurobi. Datasets are CDLA-Permissive-2.0, rule packs CC0, and weights Apache-2.0 from Apache/MIT bases only ([reuse-matrix](../docs/topics/licensing/reuse-matrix.md), [data-rulepacks-weights](../docs/topics/licensing/data-rulepacks-weights.md), [compliance-checklist](../docs/topics/licensing/compliance-checklist.md)).
- **Data scarcity.** PCBench is 54–62% unlicensed (the docs disagree) with only 23 KiCad 6+ boards; only 33% of licensed boards pass their own DRC. Expect low thousands of usable boards, so lean on priors, synthetic data and planted-solution boards ([corpora-and-yield](../docs/topics/data/corpora-and-yield.md), [learning-and-data](../docs/ideas/original/learning-and-data.md)).
- **KiCad 10 vs 11.** Neither version exposes run-DRC, route or place over IPC; KiCad 11 (~Q1 2027) adds headless mode, rules and DSN/SES. 9→10 dialects can silently miswire boards. The existing Python binding to PNS, PCBWorld-Engine, pins KiCad 9.0.8, so Option A's PNS stages (critical nets, repair) carry this risk from Phase 1. Keep a `BoardSession` abstraction ([ipc-api-10-vs-11](../docs/topics/kicad/ipc-api-10-vs-11.md), [file-format-and-version-hazards](../docs/topics/kicad/file-format-and-version-hazards.md), [kicad-pns-router](../docs/topics/routing/kicad-pns-router.md)).
- **Unverified numbers.** Quilter, DeepPCB, TopoR and Freerouting's "clean" rates are self-reported (Freerouting's own check, not KiCad DRC; on the 1,142-fixture nightly suite the latest full-suite rate is 87.7% for 2.6.0-RC3, while RC4's 92.4% covers tiers A+B only, 979 fixtures, and time budgets differ up to ~100× across versions); RAC is untested on real boards with a KiCad backend; budget spend models and the EMI proxy are uncalibrated ([freerouting](../docs/topics/routing/freerouting.md), [interfaces-relations-vs-coordinates](../docs/topics/llm/interfaces-relations-vs-coordinates.md)).
- **Open questions.** Does a domain market converge? How should tight/close/loose be calibrated? No PCB designer-trust study exists ([explanations-and-alternatives](../docs/topics/ux/explanations-and-alternatives.md), [trust-requirements](../docs/topics/workflow/trust-requirements.md)).

## 9. Where to find details

- [docs/INDEX.md](../docs/INDEX.md): the map, with task-oriented entry points.
- Digests: [algorithms](../docs/digests/algorithms.md), [llm-data-ux](../docs/digests/llm-data-ux.md), [ecosystem](../docs/digests/ecosystem.md), [rules-hs-emi-interfaces](../docs/digests/rules-hs-emi-interfaces.md), [rules-power-rf-analog-dfm](../docs/digests/rules-power-rf-analog-dfm.md), [practice-evaluation](../docs/digests/practice-evaluation.md).
- Architecture: [hybrid-architecture-options](../docs/topics/architecture/hybrid-architecture-options.md). Ideas: [original catalog](../docs/ideas/original/README.md), [cross-domain transplants](../docs/ideas/cross-domain-transplants.md).
- Raw evidence: [research notes](../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/), cited through the topic docs.
