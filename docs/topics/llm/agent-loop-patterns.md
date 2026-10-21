# Agent-loop patterns with evidence

**TL;DR**
- **Action-space design is the main lever,** ahead of agent topology. Bounded menus and operator catalogs beat free-form generation by large margins. DRC-Aid: **92.5%** repairs vs **6.6%** for static prompting [P].
- **Deterministic tools realize each choice and independently verify it.** "A model can make a repair fail but cannot make a layout pass checks it fails" [P].
- **Planner/executor splits are a cost tool, not a quality guarantee.** The cheapest verified option was often a mid-tier model alone. Input context was 81% of spend [P].
- **Execution infrastructure** (stateful tools, rollback, structured APIs) decides long-horizon reliability; similar agents differ by up to **141× in token ROI** [P].
- More iterations can hurt. Budget the loop and stop on stall [P].

## Key facts

### Bounded action space, deterministic realization, independent check

**"Who Plans, Who Edits?"** (Purdue, Oct 2026, analog LVS/DRC repair) [P] ([2610.24234](https://arxiv.org/abs/2610.24234)).
- **Workers:** memoryless, tool-free workers return JSON, choosing from bounded catalogs (8 operators for SKY130, 5 for the DAC, 2 for the oscillator).
- **Guards:** schema, bounds and editable-cell checks; edits go to a checkpointed copy with rollback; sign-off re-runs after every edit.
- **Planner contract:** the planner returns a diagnosis (evidence, hypothesis, falsifier) and ordered intents (target, mechanism, operators, scope, expected effect). Control returns to the planner on regression, stall, an inexpressible intent or a double refusal.
- **Results over 182 blind runs:** the cheapest model fixed 1 of 11 alone but **16 of 17 under a flagship planner**. Cheap planners fail more often. "No fixed assignment is cheapest on every task."
- **Costs:** tool runs took 59–94% of wall time; input context was 81% of model spend (22:1 input:output).
- **Controller:** a Bayesian per-task-class controller fixed 7 of 8 held-out tasks, at 15–40% of flagship spend on three tasks but 8% more overall.
- **Reward hacking:** "DRC-count shortcuts through fixed foundry cells show that legality must be part of the contract."

**Other systems:**

| System | Mechanism | Result | Source |
|---|---|---|---|
| DRC-Aid | A rule engine turns Calibre violations into an edit menu; the LLM selects with budgeted DFS, backtracking and an anti-cycle memory bank | **92.5%** clean, LVS-equivalent repair (about 98% violation reduction); heuristic 83.3%, random 54.4%, static prompting 6.6%; LLM advantage grows at ≥6 violations | [2607.22761](https://arxiv.org/abs/2607.22761) [P] |
| EvoDRC | Bounded repair crops; a four-role workflow with local DRC and impact-preview tools; layer-wise skill files evolved by Refiner, Summarizer and Judge | 73.5% (abstract) vs 83.6% (conclusion): **internally inconsistent** | [2607.20019](https://arxiv.org/abs/2607.20019) [P] |
| SCALE | Geometry serialized as text; masked-polygon pretraining; synthetic violation pairs fine-tune a DRC-VLM | +12–25% fix rate, up to 97% | [2607.21850](https://arxiv.org/abs/2607.21850) [P] |
| DRC-Coder | Rule text and figures → interpretation LLM → coding LLM → checker code | F1 1.000 vs 0.631, under 4 min per rule | [2412.05311](https://arxiv.org/abs/2412.05311) [P] |
| Ho & Ren (LAD 2024) | ReAct LLM writes cluster constraints for a cell-layout engine | Up to 19.4% smaller (4.65% on average), 100% LVS/DRC-clean, +23.5% clean layouts | [2406.06549](https://arxiv.org/abs/2406.06549) [P] |
| AnalogMaster | LLM does netlist extraction and search setup; classical P&R | 92.9% Pass@1, 99.9% Pass@5 (15 circuits) | [2604.20916](https://arxiv.org/abs/2604.20916) [P] |
| PANDA / AnAutomate (DAC 2026) | Agentic spec-to-layout; AnAutomate uses ALIGN and Calibre | "several hours vs several days" | [S, via survey] |
| "Code, not canvas" (ASP-DAC 2026) | Multi-agent layout as code | Diversity 12.009, DRC-legal | [S, via survey] |
| Weak-verifier aggregation | Many LLM-written verifier programs in a DSL, aggregated with about 10 labels | Up to 7× F1 over LLM-as-judge; verifier-guided generation +66.2% quality | [2606.05268](https://arxiv.org/abs/2606.05268) [P] |
| RAC | Relation bundle plus joint realization plus independent checks | 90.9% vs 23.2% for coordinates | see [interfaces-relations-vs-coordinates.md](interfaces-relations-vs-coordinates.md) |

### Multi-agent, consensus, memory, infrastructure

- **LayoutCopilot** (IEEE TCAD) [P] ([2406.18873](https://arxiv.org/pdf/2406.18873)):
  - command correctness **93.75%** for multi-agent with instructions (Claude-3 96.80%, GPT-4 93.92%, GPT-3.5 90.92%), vs 87.89% without instructions and **79.98%** single-agent (verification #23);
  - 11 commands: deviceMove, deviceSwap, arrayAdd, arraySpace, symAdd, netRemove, netReroute, wireWidth, wireSpacing, netPriority, netTopology;
  - abstract suggestions go to the designer for approval.
- **DRCY** (AllSpice, production) [P] ([2603.15672](https://arxiv.org/abs/2603.15672)):
  - k parallel group-review agents; a consensus agent keeps recurring findings, re-checks singletons against the datasheet and re-examines contradictions;
  - plus an error-grouping agent;
  - no accuracy numbers published.
- **MAGE:** a stateless independent auditor with no access to prior reasoning; see [llm-guided-placement-systems.md](llm-guided-placement-systems.md) [P].
- **Handoff survey** (115 systems) [P] ([2606.19795](https://arxiv.org/abs/2606.19795)):
  - harness mechanisms appear in 88 systems and model-parameter optimization in 23;
  - feedback loops (1/16/23/24 systems in 2023–2026) > search/evolution (0/4/12/13) > retrieval/memory (0/2/7/8) and orchestration (0/5/10/7);
  - RL fine-tuning appears in only 3 systems;
  - warning: generated verification collateral "can be mutually consistent yet jointly wrong".
- **Agentic RTL-to-GDS lessons** [P] ([2607.17528](https://arxiv.org/abs/2607.17528)):
  - skills improve subtask understanding but "do not ensure reliable completion";
  - **141× token-ROI spread**;
  - Tcl version and mode mismatches are a major failure source;
  - recommendation: "structured tool interfaces, persistent design context, controlled execution, and process-level evaluation".
- **FluxEDA** [P] ([2603.25243](https://arxiv.org/abs/2603.25243)): a stateful gateway with persistent tool instances, structured requests and responses, state reuse and **rollback**.
- **Memory:**
  - MFM persistent multimodal memory (episodic, spatial, semantic, procedural) took CUABench-KiCad from **0.267 to 0.440** ([2610.22686](https://arxiv.org/abs/2610.22686)) [P];
  - the RF-workflow agent maintained markdown context files and turned review feedback into standing conventions ([2608.31006](https://arxiv.org/abs/2608.31006)) [P].
- **Older systems:**
  - LLM4EDA: P&R is too complex to apply LLMs directly; partition and cluster, or use the LLM to "optimize modules or act as a reward system for RL agents" ([2401.12224](https://arxiv.org/abs/2401.12224)) [P].
  - ChatEDA is peer-reviewed in TCAD 43(10) ([2308.10204](https://arxiv.org/abs/2308.10204)) [P].

### Iteration and sampling

- OmniRouting: more steps helped GPT-5.5 (NRR 21.7% → 28.0%) and hurt GPT-5-mini (9.9% → 6.8%) [P].
- Agentic constraint-model improvement beat originals in 68.5% of 1,500 cases, but **best-of-5 with the same validators matched it** (101 vs 102.8 of 150) ([2608.08127](https://arxiv.org/abs/2608.08127)) [P].

### LLM → MILP/CP formulation

| Study | Finding | Source |
|---|---|---|
| OPT-Engine | Solver-integrated reasoning is essential; "automated formulation of constraints represents the primary bottleneck"; semantic sensitivity to non-canonical wording | [2601.19924](https://arxiv.org/abs/2601.19924) [P] |
| DCP-Bench-Open | Python frameworks (CPMpy, OR-Tools) beat MiniZinc; sampling plus self-verification adds up to 35%, reaching about 90–91% on CPMpy; LLMs "over-encode the example instance" | [2506.06052](https://arxiv.org/abs/2506.06052) [P] |
| CSPLib wording study | Accuracy drops sharply under contextual and linguistic variation | [2511.14334](https://arxiv.org/abs/2511.14334) [P] |
| Optimization-modelling survey | Benchmark datasets have a "surprisingly high error rate" | [2508.10047](https://arxiv.org/abs/2508.10047) [P] |
| MCP-Solver | MiniZinc, PySAT and Z3 over MCP, with iterated validation | [2501.00539](https://arxiv.org/abs/2501.00539) [P] |
| OptiMUS | LLM → MILP | [2310.06116](https://arxiv.org/abs/2310.06116) [S] |

No study applies LLM → MILP formulation to PCB placement. RAC's fixed relation schema sidesteps formulation, which is arguably better [I].

## Recommendations for our system

1. **Loop:** the LLM proposes a relation bundle; KiCad-side solvers realize it (group placement, MILP/CP-SAT legalization, critical-net routing, bulk routing via Freerouting or PNS, calculators for width, impedance and clearance); independent checkers (kicad-cli DRC/ERC, parity, per-relation oracles) verify it; feedback is structured conflicts and relaxations [I].
2. **Repairs** come from rule-engine-generated menus, with DFS, backtracking and anti-cycle memory (DRC-Aid).
2a. **No per-segment LLM routing.** PCBWorld shows about 425k–1.9M tokens per small or medium board and 0 clean-pass on medium boards. If a step router agent is built anyway, fix PCBWorld's gaps:
   - echo DRC codes and positions;
   - include zones;
   - expose per-netclass rules;
   - add rip-up and delete actions;
   - keep a longer history;
   - prefix-cache static state;
   - make the first net selection an explicit planning step.

   See [../routing/pcbworld.md](../routing/pcbworld.md).
3. **Planner contract:** evidence, hypothesis, falsifier and intents; return to the planner on regression or stall.
4. **Models:** a mid-tier model alone by default, escalating to a flagship planner only on verified failure. Keep a per-role ledger of tokens, spend and tool time. Keep observations compact.
5. **Stateful sessions** with checkpoint and rollback (FluxEDA); no reload per shell call.
6. **Explicit iteration and spend budgets.** Use best-of-N with validators as the baseline any agent loop must beat.
7. **For LLM-written constraints:** a Python-embedded API (CPMpy/OR-Tools style), validated on several instances to catch over-encoding.
8. **Multi-run consensus** for safety-critical judgments (DRCY); a stateless auditor (MAGE).
9. **Legality is in the acceptance contract;** never a DRC-count-only reward.
10. **Independent checks** must not come from the same interpretation that generated the design.

## Conflicts and open questions

- Role decomposition improved LayoutCopilot, yet a single mid-tier model was the cheapest verified option in "Who Plans". It depends on the task class.
- No controlled study exists of tool granularity for KiCad.
- EvoDRC's numbers are internally inconsistent.

## Sources
- research notes:
  - [llm_for_eda.md § 1, § 3, § 8](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/llm_for_eda.md)
  - [verification_papers.md § 1 row 23, § 2.11](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_papers.md)

See also: [code-and-objective-evolution.md](code-and-objective-evolution.md), [llm-guided-placement-systems.md](llm-guided-placement-systems.md), [../ux/agent-tooling-reliability-patterns.md](../ux/agent-tooling-reliability-patterns.md), [interfaces-relations-vs-coordinates.md](interfaces-relations-vs-coordinates.md)
