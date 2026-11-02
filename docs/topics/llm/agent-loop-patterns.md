# Agent-loop patterns with evidence

Scope: action-space design, planner/executor splits, consensus, memory, execution infrastructure, iteration budgets, LLM -> MILP/CP formulation. Not here: write interface (relations) -> [interfaces-relations-vs-coordinates](interfaces-relations-vs-coordinates.md); offline code evolution -> [code-and-objective-evolution](code-and-objective-evolution.md); MCP tooling reliability -> [ux/agent-tooling-reliability-patterns](../ux/agent-tooling-reliability-patterns.md).
Keys: action space, operator catalog, edit menu, DRC-Aid, EvoDRC, SCALE, DRC-Coder, Who Plans Who Edits, planner contract, falsifier, token ROI, FluxEDA, rollback, DRCY, consensus, stateless auditor, LayoutCopilot, MFM memory, best-of-N, OPT-Engine, DCP-Bench-Open, CPMpy, over-encoding, reward hacking

## Results

1. Action-space design is the main lever, ahead of agent topology: bounded menus beat free-form generation (DRC-Aid) [P].
2. Deterministic tools realize each choice and independently verify it: "A model can make a repair fail but cannot make a layout pass checks it fails" [P].
3. Planner/executor splits are a cost tool, not a quality guarantee [P].
4. Execution infrastructure (stateful tools, rollback, structured APIs) decides long-horizon reliability [P].
5. More iterations do not guarantee improvement; best-of-N with validators matched an agentic loop [P].

## Bounded action space, deterministic realization, independent check

**"Who Plans, Who Edits?"** (Purdue, Oct 2026, analog LVS/DRC repair; [2610.24234](https://arxiv.org/abs/2610.24234)) [P]:

| Item | Value |
|---|---|
| Workers | memoryless, tool-free, return JSON from bounded catalogs: 8 operators (SKY130), 5 (DAC), 2 (oscillator) |
| Guards | schema, bounds, editable-cell checks; edits on a checkpointed copy with rollback; sign-off re-run after every edit |
| Planner contract | diagnosis (evidence, hypothesis, falsifier) + ordered intents (target, mechanism, operators, scope, expected effect); control returns to planner on regression, stall, inexpressible intent, or double refusal |
| 182 blind runs | cheapest model alone fixed 1 of 11; **16 of 17 under a flagship planner**; cheap planners fail more; "No fixed assignment is cheapest on every task" |
| Costs | tool runs 59–94% of wall time; input context 81% of model spend (22:1 input:output) |
| Bayesian per-task-class controller | fixed 7 of 8 held-out tasks; 15–40% of flagship spend on three tasks, 8% more overall |
| Reward hacking | "DRC-count shortcuts through fixed foundry cells show that legality must be part of the contract" |

Conflict: the note's summary also says "The cheapest verified option on every task was a mid-tier model alone", inconsistent with the quote above.

| System | Mechanism | Result | Source |
|---|---|---|---|
| DRC-Aid | Rule engine turns Calibre violations into an edit menu; LLM selects with budgeted DFS, backtracking, anti-cycle memory bank | **92.5%** clean, LVS-equivalent repair (≈98% violation reduction); heuristic 83.3%, random 54.4%, static prompting 6.6%; LLM advantage grows at ≥6 violations | [2607.22761](https://arxiv.org/abs/2607.22761) [P] |
| EvoDRC | Bounded repair crops; four-role workflow with local DRC and impact-preview tools; layer-wise skill files evolved by Refiner, Summarizer, Judge | 73.5% (abstract) vs 83.6% (conclusion): **internally inconsistent** | [2607.20019](https://arxiv.org/abs/2607.20019) [P] |
| SCALE | Geometry serialized as text; masked-polygon pretraining; synthetic violation pairs fine-tune a DRC-VLM | +12–25% fix rate, up to 97% (100 real sub-2 nm cases) | [2607.21850](https://arxiv.org/abs/2607.21850) [P] |
| DRC-Coder | Rule text and figures -> interpretation LLM -> coding LLM -> checker code; a VLM reads foundry rule illustrations | F1 1.000 vs 0.631, under 4 min per rule | [2412.05311](https://arxiv.org/abs/2412.05311) [P] |
| Ho & Ren (LAD 2024) | ReAct LLM writes cluster constraints for a cell-layout engine | Up to 19.4% smaller (4.65% mean), 100% LVS/DRC-clean, +23.5% clean layouts | [2406.06549](https://arxiv.org/abs/2406.06549) [P] |
| AnalogMaster | LLM does netlist extraction and search setup; classical P&R | 92.9% Pass@1, 99.9% Pass@5 (15 circuits) | [2604.20916](https://arxiv.org/abs/2604.20916) [P] |
| PANDA / AnAutomate (DAC 2026) | Agentic spec-to-layout; AnAutomate uses ALIGN and Calibre | "several hours vs several days" | [S, via survey] |
| "Code, not canvas" (ASP-DAC 2026) | Multi-agent layout as code | Diversity 12.009, DRC-legal | [S, via survey] |
| Weak-verifier aggregation | Many LLM-written verifier programs in a DSL, aggregated with ≈10 labels | Up to 7× F1 over LLM-as-judge; verifier-guided generation +66.2% quality | [2606.05268](https://arxiv.org/abs/2606.05268) [P] |
| RAC | Relation bundle + joint realization + independent checks | 90.9% vs 23.2% coordinates -> [interfaces-relations-vs-coordinates](interfaces-relations-vs-coordinates.md) | [P] |

## Multi-agent, consensus, memory, infrastructure

- **LayoutCopilot** (IEEE TCAD; [2406.18873](https://arxiv.org/pdf/2406.18873)) [P]: command correctness 93.75% multi-agent with instructions (Claude-3 96.80%, GPT-4 93.92%, GPT-3.5 90.92%), 87.89% without instructions, 79.98% single-agent (verification #23). 11 commands: deviceMove, deviceSwap, arrayAdd, arraySpace, symAdd, netRemove, netReroute, wireWidth, wireSpacing, netPriority, netTopology. Abstract suggestions go to the designer for approval; concrete ones compile to commands.
- **DRCY** (AllSpice, production; [2603.15672](https://arxiv.org/abs/2603.15672)) [P]: k parallel group-review agents; consensus agent keeps recurring findings, re-checks singletons against the datasheet, re-examines contradictions; error-grouping agent; no accuracy numbers. Pipeline -> [datasheet-extraction](datasheet-extraction.md#production-datasheet-pipelines).
- **MAGE:** stateless independent auditor with no access to prior reasoning [P].
- **Handoff survey** (115 systems; [2606.19795](https://arxiv.org/abs/2606.19795)) [P]: harness mechanisms in 88 systems, model-parameter optimization in 23; per year 2023/24/25/26: feedback loops 1/16/23/24 > search/evolution 0/4/12/13 > retrieval/memory 0/2/7/8, orchestration 0/5/10/7; RL fine-tuning in 3 systems only. Warning: generated verification collateral "can be mutually consistent yet jointly wrong".
- **Agentic RTL-to-GDS** ([2607.17528](https://arxiv.org/abs/2607.17528)) [P]: skills improve subtask understanding but "do not ensure reliable completion"; 141× token-ROI spread; Tcl version and mode mismatches ("low-level tool-interface mismatches") are a major failure source; advice: "structured tool interfaces, persistent design context, controlled execution, and process-level evaluation".
- **FluxEDA** ([2603.25243](https://arxiv.org/abs/2603.25243)) [P]: stateful gateway, persistent tool instances, structured requests/responses, state reuse, **rollback**.
- **Memory:** MFM persistent multimodal memory (episodic, spatial, semantic, procedural): CUABench-KiCad 0.267 -> 0.440 ([2610.22686](https://arxiv.org/abs/2610.22686)) [P]. RF-workflow agent kept markdown context files and turned review feedback into standing conventions ([2608.31006](https://arxiv.org/abs/2608.31006)) [P].
- **Older systems** [P]: LLM4EDA: P&R too complex for direct LLM use; partition and cluster, or let the LLM "optimize modules or act as a reward system for RL agents" ([2401.12224](https://arxiv.org/abs/2401.12224)). ChatEDA peer-reviewed in TCAD 43(10) ([2308.10204](https://arxiv.org/abs/2308.10204)). SmartonAI (2023): KiCad chat plugin, subtask splitting + RAG over docs + plugin recommender; operates KiCad, no layout ([2307.14740](https://arxiv.org/abs/2307.14740)).

## Iteration and sampling

- OmniRouting: more steps raised NRR for GPT-5.5 and lowered it for GPT-5-mini; not a clean iteration-budget test -> [routing/llm-routing-evidence](../routing/llm-routing-evidence.md#omnirouting), [pcb-llm-benchmarks](pcb-llm-benchmarks.md#omnirouting) [P].
- Agentic constraint-model improvement beat originals in 68.5% of 1,500 cases, but **best-of-5 with the same validators matched it** (101 vs 102.8 of 150) ([2608.08127](https://arxiv.org/abs/2608.08127)) [P].

## LLM -> MILP/CP formulation

| Study | Finding | Source |
|---|---|---|
| OPT-Engine | Solver-integrated reasoning essential; "automated formulation of constraints represents the primary bottleneck"; sensitive to non-canonical wording; tools "help with local calculations [but] still fail to adhere to global optimization constraints" | [2601.19924](https://arxiv.org/abs/2601.19924) [P] |
| DCP-Bench-Open | Python frameworks (CPMpy, OR-Tools) beat MiniZinc; sampling + self-verification adds up to 35%, ≈90–91% on CPMpy; LLMs "over-encode the example instance" | [2506.06052](https://arxiv.org/abs/2506.06052) [P] |
| CSPLib wording study | Accuracy drops sharply under contextual and linguistic variation | [2511.14334](https://arxiv.org/abs/2511.14334) [P] |
| Optimization-modelling survey | Benchmark datasets have a "surprisingly high error rate" | [2508.10047](https://arxiv.org/abs/2508.10047) [P] |
| MCP-Solver | MiniZinc, PySAT, Z3 over MCP, iterated validation | [2501.00539](https://arxiv.org/abs/2501.00539) [P] |
| OptiMUS | LLM -> MILP | [2310.06116](https://arxiv.org/abs/2310.06116) [S] |

No study applies LLM -> MILP formulation to PCB placement; RAC's fixed relation schema sidesteps formulation [I].

## Loop design for our system

1. Loop: LLM proposes a relation bundle -> KiCad-side solvers realize it (group placement, MILP/CP-SAT legalization, critical-net routing, bulk routing via Freerouting or PNS, width/impedance/clearance calculators) -> independent checkers (kicad-cli DRC/ERC, parity, per-relation oracles) -> structured conflicts and relaxations back [I].
2. Repairs from rule-engine-generated menus with DFS, backtracking, anti-cycle memory (DRC-Aid) [I].
3. No per-segment LLM routing (PCBWorld token cost and 0 clean-pass on medium boards); fixes for a step router agent, if built anyway -> [routing/pcbworld](../routing/pcbworld.md#llm-agents) [I].
4. Planner contract: evidence, hypothesis, falsifier, intents; return to planner on regression or stall [I].
5. Models: mid-tier model alone by default; escalate to a flagship planner only on verified failure. Task-class dependent (evidence is analog IC repair) [I]. Keep a per-role ledger of tokens, spend, tool time; compact observations.
6. Stateful sessions with checkpoint and rollback (FluxEDA); no reload per shell call [I].
7. Explicit iteration and spend budgets; best-of-N with validators is the baseline any agent loop must beat [I].
8. LLM-written constraints: Python-embedded API (CPMpy/OR-Tools style), validated on several instances to catch over-encoding [I].
9. Multi-run consensus for safety-critical judgments (DRCY); stateless auditor (MAGE) [I].
10. Legality is in the acceptance contract; never a DRC-count-only reward. Independent checks never come from the interpretation that generated the design [I].

## Open questions

- Role decomposition helped LayoutCopilot, yet a single mid-tier model was cheapest-verified in "Who Plans": task-class dependent.
- No controlled study of tool granularity for KiCad.

## Sources
- [llm_for_eda.md § 1, § 3, § 8](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/llm_for_eda.md)
- [verification_papers.md § 1 row 23, § 2.11](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_papers.md)
