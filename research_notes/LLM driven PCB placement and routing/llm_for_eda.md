# LLMs and Agentic AI for EDA Physical Layout (PCB + IC Placement & Routing), Spatial Reasoning, and Design-Intent Explanation

_Method note for the report writer (revised 2026-10-20, deep pass). This file was first written from search snippets alone, because arXiv was unreachable at the time. In the deep pass, arXiv full text (HTML or PDF) was downloaded with curl and read locally. The WebFetch tool still could not resolve hosts, and mdpi.com was blocked (HTTP 403). Every finding carries a provenance tag:_
- _**[P]**: read from the primary paper (full text, or at least abstract plus results and conclusion) in this session._
- _**[P-via-survey]**: read in full text, but in a survey that describes another paper whose primary text was not available (DAC/DATE/ASP-DAC papers not on arXiv)._
- _**[S]**: search-result snippet or secondary summary only; not verified._

_Venue flags:_
- _**[PR]**: peer-reviewed._
- _**[WS]**: workshop._
- _**[PP]**: arXiv preprint._
- _**[V]**: vendor or blog._
- _**[C]**: community or README._

_A separate agent is verifying headline numbers for PCBWorld, ModuPlace, PCBAgent, VeoPlace, EvoPlace, OrderPlace, CoEvoP&R, OmniLayout, PCB-Bench, PCBInnoBench, HWE-Bench, GENIE-ASI, PCBSchemaGen, MAGE and LayoutCopilot. Those entries are kept here mostly at [S] level and marked "(verified separately)". Where this pass read them first-hand, for example through the handoff survey, that is stated. This pass concentrated on breadth and gaps:_
- _OmniRouting;_
- _LLM-for-EDA surveys and the systems they list;_
- _spatial-reasoning and representation studies, read in full;_
- _VLM layout reading;_
- _EDA agent-harness studies;_
- _LLM-to-solver formulation;_
- _2026 LLM+PCB papers found by following citations._

---

## 1. LLM-for-EDA papers and systems for physical layout (2023–2026): what was tried, what worked, what failed

### Takeaway
All four streams in this section give the same answer. The streams are IC placement, PCB benchmarks, analog/DRC repair, and the newest PCB-specific agent contracts. **LLMs succeed when they make semantic decisions on a low-dimensional control surface**, such as relations, regions, constraints, objective terms, hyperparameters, algorithm code or edit choices from a menu. **They fail when they emit geometry.** The clearest 2026 evidence comes from three PCB papers:
- **RAC**: when the agent commits only named relations and tools realize the geometry, PCB placement, routing and repair tasks reach a 90.9% clean pass. The same nine models emitting coordinates reach 23.2%.
- **OmniRouting**: the best LMM connects 12.6% of nets DRC-clean, against 56.2% for an old open-source router and 93.6% for humans.
- **The DAC 2026 coarse-to-fine PCB placer**: LLM grouping plus MILP legalization beats a commercial placer, NS-Place and Quilter on routed wirelength and vias.

### Cited Findings

**Surveys and framing**
- **"Agentic EDA: A Handoff Perspective"** (Liu, Han, Lu, Zheng, Yan, Bei Yu; latest HTML version) **[P][PP]**:
  - The latest version reviews **115 agentic EDA systems**; earlier snippets said 82, probably v1. It classifies them by primary input–output pair into Intra-, Inter- and Extra-stage systems.
  - **Agent harness mechanisms appear in 88 of 115 systems; model-parameter optimization appears in 23.** Explicit feedback loops are the most common mechanism (1, 16, 23 and 24 systems in 2023–2026). Search/evolution follows (0, 4, 12, 13), then retrieval/memory (0, 2, 7, 8) and orchestration (0, 5, 10, 7). RL fine-tuning of the LLM appears in only three 2026 systems.
  - It warns that "generated verification collateral can be mutually consistent yet jointly wrong when the implementation and its checks inherit the same interpretation". It also warns that reported gains cannot be compared across unmatched models, tool budgets and backends.
  - Source: [arXiv 2606.19795](https://arxiv.org/abs/2606.19795).
- **LLM4EDA** (SJTU, Dec 2023) **[P][PP]**: "The complexity of Placement and Routing (P&R) currently makes it challenging to directly apply LLMs." It suggests graph partitioning and clustering to cut problem scale, and using LLMs to "optimize modules or act as a reward system for RL agents" — [arXiv 2401.12224](https://arxiv.org/abs/2401.12224).
- **"A Survey of Research in LLMs for EDA"** (Duke, ACM TODAES) **[P][PR]**: in logic synthesis and physical design, two trends dominate: Tcl script generation and documentation Q&A. Analog layout adds symmetry and wire-matching constraints — [arXiv 2501.09655](https://arxiv.org/abs/2501.09655); [ACM 10.1145/3715324](https://dl.acm.org/doi/10.1145/3715324).
- **"The Dawn of Agentic EDA"** (v2, Feb 2026) **[P][PP]**: "no LLM-driven autonomous agent has yet demonstrated a complete, human-free tape-out of an industrial chip". Most academic agents optimize proxy metrics such as placement wirelength on open PDKs like Sky130 — [arXiv 2512.23189](https://arxiv.org/abs/2512.23189).
- **"LLMs in Digital EDA: from Generation to Orchestration"** (perspective, Aug 2026) **[P][PP]**: defines Generator, Agent and Orchestrator roles. It identifies a **"syntax trap"**: models trained to produce plausible code rather than physically correct hardware, made worse by fragmented tools and lost design context — [arXiv 2608.27184](https://arxiv.org/abs/2608.27184).
- **"Surveying GenAI-based Automation in PCB Design and Test"** (UNSW, Jun 2026) **[P][PP]**:
  - It covers 80 papers. It argues that existing LLM-for-EDA surveys "are skewed towards ICs and do not examine PCBs".
  - At the PCB layout/routing stage it finds very few GenAI works, including (i) You et al. 2024, where GPT-4 writes layout-generator code; (ii) Zhang et al. 2025 in *Engineering Proceedings* (MDPI), a few-shot plus chain-of-thought LLM-only approach that generates PCB routing coordinates; and (iii) PCBAgent and LLANA.
  - It concludes: **"no GenAI tools independently validate PCB layouts – they instead work as EDA design assistants."**
  - Source: [arXiv 2606.17074](https://arxiv.org/abs/2606.17074). The Zhang et al. MDPI paper could not be fetched (403) — [MDPI](https://www.mdpi.com/2673-4591/86/1/2).

**PCB-specific systems and benchmarks (2026)**
- **RAC: A Relational Agent Contract for Constraint-Governed Engineering Tasks** (Oct 14, 2026) **[P][PP]**. This is the most directly relevant paper found.
  - **Contract.** The agent observes a typed board state (components, pins, nets, copper, unrouted connections, DRC results). It may only commit **relations over named objects**: proximity, alignment, symmetry, edge association, keepouts, matched routing, layer preference and via limits. "**No action accepts a coordinate or a metric distance: magnitudes use small ordered classes (tight, close, loose)**", with the metric values fixed on the solver side.
  - **Realization and checking.** The full bundle of relations is realized jointly by a seed-controlled placement and routing backend. An **independent** DRC plus relation-specific oracles then check the result. When realization is infeasible, feedback names the conflicting constraints, the violation magnitudes and the admissible relaxations.
  - **Tasks.** 98 PCB tasks: 42 routing, 31 placement, 17 combined, 8 repair. They cover decoupling, board-edge association, keepouts, grouping, symmetry, alignment and routing relations. Nine models were tested over six seeds with at most five model calls per episode.
  - **Mean clean-pass rate by interface:** direct coordinates 23.2%; coordinates plus a Python sandbox 21.0%; choosing among tool-generated candidates 37.4%; one relation at a time 62.4%; requirements-only delegation 74.0%; **RAC 90.9%**. RAC was best for all nine models (77.6–95.9%). It used 22.9–48.5% fewer tokens than candidate selection and had the lowest latency for 7 of 9 models.
  - **Harness robustness.** Across Native function calling, Codex, Claude Code and OpenCode harnesses, coordinates scored 22.7–32.7% and RAC 91.8–95.9%. The coding-agent harnesses cost 2.2–5.4× the tokens of native calls.
  - Its stated limitation: RAC needs a realizer and an independent checker, so preferences that cannot be written as checkable predicates fall outside it.
  - Source: [arXiv 2610.20935](https://arxiv.org/abs/2610.20935).
- **OmniRouting** (Penn State, MSR, SJTU et al., Aug 5, 2026) **[P][PP]**:
  - **Data.** 1,681 open-hardware PCB designs (SparkFun, Arduino, Adafruit, Seeed and others) parsed from EAGLE XML. Each has a human-made routable placement and a human reference routing: 494K wire segments, 84.6K vias, 4.3K pours, 2–8 layers.
  - **Metrics.** Net Routability Ratio (NRR) is the share of nets connected and DRC-clean; PRR is the pad-to-pad equivalent.
  - **Zero-shot results:**

    | Router | NRR | PRR |
    |---|---|---|
    | Best LMM (Claude Opus 4.8) | 12.60% | 15.41% |
    | GPT-5.5 | 9.13% | 12.26% |
    | PcbRouter (open-source OpenROAD-attic router) | 56.20% | 71.37% |
    | GPCB transformer router | 0.69% | — |
    | Human reference | 93.58% | 95.91% |

  - **Errors.** LMM outputs average 69.8–431.3 DRC violations and 20.5–78.3% of nets with physical shorts, against 0.80 and 0.38% for humans. Models route GND as ordinary traces instead of pours.
  - **Agentic setting** (tools for visualization, overlap check and routability scoring): the best is GPT-5.5 with all tools, NRR 27.98%. Its DRC total falls from 48.06 to 9.35 and physical shorts from 39.5% to 9.1%.
  - **Feedback quality beats iteration count.** More steps helped GPT-5.5 (NRR 21.7→28.0%) but hurt GPT-5-mini (9.9→6.8%).
  - **Few-shot examples** "can reduce violations by routing less".
  - **Inconsistency:** the agentic-framework text describes refining "component positions", apparently copied from OmniLayout.
  - Source: [arXiv 2608.04434](https://arxiv.org/abs/2608.04434).
- **Li et al., "A coarse-to-fine PCB placement framework via LLM-guided component grouping and group-aware placement"** (Proc. DAC 2026) **[P-via-survey][PR]**:
  - Pipeline: multimodal serialization, topology-enriched retrieval, two grouping agents, group-aware global placement, and **constraint-graph/MILP legalization**.
  - Results: "On six industrial boards routed by the same commercial router, Li et al. report average routed-wirelength/via improvements of **55%/73% over the commercial placer, 34%/26% over NS-Place, and 15%/13% over Quilter**."
  - The survey stresses that "an unlegalized coordinate set is not acceptable even when its estimated HPWL is low."
  - The primary paper is not on arXiv. It may be the "ModuPlace" being verified separately; unconfirmed.
  - Source: [handoff survey §4.2](https://arxiv.org/abs/2606.19795).
- **PCBAgent** (ASP-DAC 2025; verified separately) **[P-via-survey][PR]**: an RL placement policy (decision-transformer style) plus an LLM interaction agent that turns requests into optimization commands. It was "the only evaluated method to produce fully legal results on all 17 high-density tasks". Its normalized HPWL and surface-layer wire count reach **1.04 and 0.94 relative to manual layouts**, and interactive refinement improves requested wire categories by **39.6%** on average. "Some baselines attain shorter wirelength by violating spacing or boundary constraints." Sources: [handoff survey](https://arxiv.org/abs/2606.19795); [ACM DL](https://dl.acm.org/doi/10.1145/3658617.3697736).
- **PCBWorld** (LG AI Research; KiCad push-and-shove engine, 679 real boards; verified separately) **[S][PP/WS]**: interactive GPT-5.4 routing reaches clean pass 0.65 on D3-A, against 0.19 for plan-then-execute and 0.02 for engine-free generation. All LLMs score 0.00 on large D3-B boards. Freerouting scores 0.80/0.78 — [arXiv 2607.05915](https://arxiv.org/abs/2607.05915); [GitHub](https://github.com/LGAI-Research/PCBWorld).
- **OmniLayout** (placement companion to OmniRouting; verified separately), **PCB-Bench** (ICLR 2026), **PCBInnoBench** (NeurIPS 2026; 22.0% vs 7.3% Pass@1 with vs without expert trajectory), **PCB-QA** and **HWE-Bench** are all **[S]** — [OmniLayout](https://arxiv.org/abs/2607.03261); [PCB-Bench](https://github.com/digailab/PCB-Bench); [PCBInnoBench](https://neurips.cc/virtual/2026/poster/139034); [PCB-QA](https://arxiv.org/abs/2606.23704); [HWE-Bench](https://arxiv.org/abs/2603.18102).
- **"From Prompt to Prototype: Frontier-LLM-driven RF engineering workflow"** (Ruhr-Univ. Bochum / TH Köln, Aug 2026) **[P][PP, carries an IEEE copyright notice]**:
  - **Setup.** Claude Fable 5 inside Claude Code designed an active GNSS L1 antenna end to end in about 2 hours: patch antenna, SAW prefilter, two-stage LNA and a manufacturing-ready 2-layer board. It drove CST, ADS and **KiCad 9 only through pcbnew and kicad-cli**.
  - **Design as code.** The whole design is held as scripts, so "schematic and layout are **netlist-identical by construction**", and an automatic check confirmed all 75 nodes and 18 nets against the simulated design. RF lines were drawn as copper polygons that replicate the simulated line models.
  - **What human review caught.** Rounded line ends where the simulation assumed square; a missing 45° miter; solder-mask openings around RF lines; a tee routed where the simulation had a crossing. The first schematic was "not human-readable": parts on a grid, connected only by net labels.
  - **Persistent knowledge.** Operating knowledge lived in agent-maintained markdown context files, and standing conventions were written to persistent context.
  - **Stated limit.** "Only the generation of frontier models released since early to mid-2026 sustains such multi-hour tool-driving sessions reliably."
  - Source: [arXiv 2608.31006](https://arxiv.org/abs/2608.31006).
- **SchGen** (Microsoft, May 2026) **[P][PP]**: generates editable PCB schematics from natural language using a **"semantically grounded code representation"**: editing primitives with **relative placement and pin-name-based wiring**. This turns "a geometry-driven generation problem into a semantics-driven matching task". It significantly outperforms alternative representations and larger general LLMs on connectivity and function — [arXiv 2605.30345](https://arxiv.org/abs/2605.30345); [code](https://github.com/microsoft/SchGen).
- **DRCY: Agentic Hardware Design Reviews** (AllSpice, Mar 2026) **[P][PP]**: a production multi-agent schematic reviewer run as a CI/CD action on AllSpice Hub. Its five-agent pipeline is described in Section 4. **No accuracy numbers are reported** — [arXiv 2603.15672](https://arxiv.org/abs/2603.15672).
- **SmartonAI** (2023; KiCad plugin) **[P][PP]**: a chat plugin that splits instructions into subtasks with RAG over documentation, plus a plugin recommender. It only helps users operate KiCad and does no layout — [arXiv 2307.14740](https://arxiv.org/abs/2307.14740).
- **kicad-pycbnew** (CNRS/IN2P3, Sep 2026) **[P][PP]**: an MIT-licensed Python library that writes KiCad PCB files programmatically **without a KiCad runtime**. It offers constraint-driven routing, parallel track arrays and via grids with exclusion zones, aimed at parameterized detector boards — [arXiv 2609.27522](https://arxiv.org/abs/2609.27522).
- **CUABench-KiCad** (25 schematic-editing GUI tasks scored by netlist comparison, from Cua AI): in the MFM memory paper, persistent multimodal memory raised mean reward from 0.267 with no memory to 0.440 (best baseline 0.400) **[P][PP]** — [arXiv 2610.22686](https://arxiv.org/abs/2610.22686).
- **Industry demos and claims** (all **[S]**, carried over from the first pass):
  - **GPT-6 Astra KiCad demo** (Sept 2026). The model hand-protected critical nets, then ran Freerouting. KiCad reported 46 parity issues, and one comparison found 168 DRC violations against 0 on the human board — [JLCPCB](https://jlcpcb.com/blog/gpt-6-astra-pcb-design-in-kicad); [NextPCB](https://www.nextpcb.com/blog/gpt-6-astra-kicad-pcb-routing-test); [zerowithdot](https://zerowithdot.com/blog/gpt-6-astra-impact-on-cad/); [Quilter](https://www.quilter.ai/blog/llm-pcb-layout-gpt-6-astra).
  - **EEBench** (atopile; layout out of scope; claims declarative code beats GUI drawing) — [EEBench](https://eebench.org/blog/can-ai-design-circuit-boards-yet/).
  - **Quilter's position:** "not an LLM"; physics checks; values derived from the stackup — [Quilter](https://www.quilter.ai/blog/pcb-autorouter-was-the-right-idea).
  - **KiCad MCP servers** that route mostly through Freerouting — [Konnect](https://github.com/mixelpixx/Konnect); [kicad-mcp-pro](https://github.com/oaslananka/kicad-mcp-pro); [Gato513/kicad-mcp](https://github.com/Gato513/kicad-mcp).
  - **Siemens "Fuse EDA AI agent"** spanning IC, 3D IC and PCB, cited by the handoff survey — [Siemens](https://news.siemens.com/en-us/siemens-fuse-eda-ai-agent/).

**IC placement, floorplanning and routing with LLMs**
- **HyperPlace** (ACM TODAES 2025) **[P-via-survey][PR]**: an LLM agent "proposes and explains hyperparameter configurations" for DREAMPlace/Xplace, leaving legality and coordinates to the placer. It reports up to 1.66% HPWL reduction on ISPD 2005, and under ISPD 2015 fence constraints up to 22.24% over DREAMPlace 3.0 and 19.28% over Xplace 2.0 — [handoff survey](https://arxiv.org/abs/2606.19795).
- **CHIP-MAP** (DATE 2026) **[P-via-survey][PR]**: analysis, grouping, floorplan and verification agents exchange **structured JSON** to refine macro floorplans. It reports up to 1.5% area reduction and repairs 61.6% of TNS on average — [handoff survey](https://arxiv.org/abs/2606.19795).
- **LLM for standard-cell layout** (Ho & Ren, NVIDIA; LAD 2024) **[P][PR]**: with ReAct prompting, the LLM generates **cluster constraints** for an existing cell-layout engine. It reports up to 19.4% smaller cells (4.65% on average), 100% LVS/DRC-clean results on the selected 2 nm sequential cells, and 23.5% more clean layouts than prior work — [arXiv 2406.06549](https://arxiv.org/abs/2406.06549).
- **"Code, not canvas: multi-agent layout generation beyond vision models"** (Yang & Ren, ASP-DAC 2026) **[P-via-survey][PR]**: generates IC layout as code. It reports a diversity score of 12.009 with DRC-legal output, "exceeding the evaluated vision-based layout generators" — [handoff survey](https://arxiv.org/abs/2606.19795).
- **DRC-Coder** **[P][PP]**: a multi-agent system with vision that turns foundry rule text and figures into DRC checker code. It reached F1 1.000, against 0.631 for standard prompting, in under 4 minutes per rule on a sub-3 nm cell-layout tool — [arXiv 2412.05311](https://arxiv.org/abs/2412.05311).
- **GR-Evolve** (ASU, Apr 2026) **[P][PP]**: an agentic LLM edits **global-router source code** using QoR feedback in OpenROAD, with persistent knowledge of open-source routers. It gives up to 8.72% lower post-detailed-route wirelength across 7 designs and 3 nodes — [arXiv 2604.22234](https://arxiv.org/abs/2604.22234).
- **VPR-Evolve** (ASU; ASP-DAC 2027) **[P]**: LLM agents evolve FPGA VPR source code per design, with a shared memory of earlier outcomes. Against stock VPR it improves the composite score by up to 2.7% and cuts critical-path delay by up to 9.8%, routed wirelength by up to 18.1% and runtime by up to 79.3%. Against hyperparameter tuning the gains are delay −6.0%, wirelength −2.2% and runtime −7.8% — [arXiv 2607.24998](https://arxiv.org/abs/2607.24998).
- **FABO** (HKUST/Synopsys, Aug 2026) **[P][PP]**: agent-guided search found a structural limitation in SALT, which picks path breakpoints sink by sink. The new joint breakpoint optimization lowers average FLUTE-normalized wirelength at every setting across 1.29M ICCAD15 nets: peak −0.83% overall and −2.66% for nets with 30 or more pins — [arXiv 2608.30268](https://arxiv.org/abs/2608.30268).
- **Prim–Dijkstra revisited with LLMs** (Fudan, Jul 2026) **[P][PP]**: LLM-assisted theory work proved weak NP-completeness of a classic routing-tree problem. The resulting HP-RCRST solver Pareto-dominates the union of published methods on 23 of 28 instances — [arXiv 2607.17005](https://arxiv.org/abs/2607.17005).
- **AlphaRoute** (Nirma Univ./ASU) **[P][PP, IEEE copyright notice]**: LLMs act as "semantic policy optimizers" that tune rip-up-and-reroute penalty parameters, "bounded by a deterministic knowledge graph". It claims a 98.6% overflow reduction on ISPD 2025 MEMPOOL and 29.8× lower overflow than SOTA on ARIANE. Single group, Python implementation; treat with caution — [arXiv 2607.19768](https://arxiv.org/abs/2607.19768).
- **GoalEvolve** (Aug 2026) **[P][PP]**: goal-driven source evolution of OpenROAD algorithms. A "Teacher" LLM uses stage-resolved checkpoint evidence to locate the responsible stage and source region; parallel "Student" agents implement and validate changes through full-flow runs. On 8 ASAP7 designs it improves TNS by 30.67% and cuts leakage by 21.18% and dynamic power by 9.42% against default OpenROAD. Under matched budgets it beats Codex goal mode (TNS +26.46%) — [arXiv 2608.16733](https://arxiv.org/abs/2608.16733).
- **Verified separately (kept [S])**: VeoPlace (VLM-proposed regions over a placer), EvoPlace (LLM-evolved placer optimizer, TCAD 2026), OrderPlace (ICML 2026), CoEvoP&R (LLM-evolved differentiable objectives), MAGE (multimodal multi-agent macro placement), PlaceReasoner-Beta, PDAgent-Bench — [VeoPlace](https://arxiv.org/abs/2603.28733); [EvoPlace](https://ieeexplore.ieee.org/document/11345590/); [OrderPlace](https://arxiv.org/abs/2606.08904); [CoEvoP&R](https://arxiv.org/abs/2607.17398); [MAGE](https://arxiv.org/abs/2607.18536); [PlaceReasoner-Beta](https://arxiv.org/abs/2609.21263).
- **PDAgent-Bench** (latest version v7) **[P][PP]**: 353 physical-design problems tested on 11 models. Results are competitive on concepts (GPT-5.5 scores 73.3% on root-cause analysis) and weak on tool-centric, long-horizon execution. "Human-skill-enhanced agentic workflows significantly improve end-to-end physical design performance". "With human instructions", VLM macro placement beat analytical and RL baselines — [arXiv 2606.17253](https://arxiv.org/abs/2606.17253).

**Flow orchestration (IC)**
- **ChatEDA** is peer-reviewed in **IEEE TCAD 43(10), 2024**; the citation was confirmed via the RF-workflow paper's references **[P]** — [arXiv 2308.10204](https://arxiv.org/abs/2308.10204).
- MCP4EDA, AutoEDA, ORAssistant, AuDoPEDA **[S]**, from the first pass — [MCP4EDA](https://arxiv.org/abs/2507.19570); [AutoEDA](https://arxiv.org/abs/2508.01012); [ORAssistant](https://arxiv.org/abs/2410.03845); [AuDoPEDA](https://arxiv.org/abs/2601.06268).

**Analog layout**
- **"Who Plans, Who Edits?"** (Purdue, Oct 16, 2026) **[P][PP]**: an LLM repair agent for LVS, DRC and post-layout problems, in which **"models only choose bounded layout operators"**. Deterministic guards apply each edit to a checkpointed copy, and sign-off tools re-verify every edit. Full findings are in Section 3 — [arXiv 2610.24234](https://arxiv.org/abs/2610.24234).
- **AnalogMaster** (Apr 2026) **[P][PP]**: goes from a circuit image to a netlist, then sizing, then **classical** placement and routing. GPT-5 reaches 92.9% Pass@1 and 99.9% Pass@5 on 15 circuits. The LLM does netlist extraction and the parameter search setup; classical algorithms do the layout — [arXiv 2604.20916](https://arxiv.org/abs/2604.20916).
- **PANDA** (DAC 2026) and **AnAutomate** (DAC 2026 special session): agentic spec-to-layout flows. AnAutomate coordinates sizing, learned constraints, **ALIGN** layout generation and Calibre checks. PANDA finishes end-to-end cases "in several hours, compared with several days for manual iterations" **[P-via-survey]** — [handoff survey](https://arxiv.org/abs/2606.19795); [PANDA arXiv 2606.15052](https://arxiv.org/abs/2606.15052).
- **GENIE-ASI** (verified separately) **[P abstract][PP]**: a training-free LLM writes Python to identify analog subcircuits in SPICE netlists. F1 is 1.0 on simple structures, 0.81 on moderate and 0.31 on complex ones. The stated motivation is forming matching, symmetry and proximity groups before placement — [arXiv 2508.19393](https://arxiv.org/abs/2508.19393).
- LayoutCopilot (TCAD; verified separately). Per the handoff survey, its "comparison between a monolithic agent and specialized agents attributes improved sanity-check and command success to role decomposition" **[P-via-survey]**. ICPI (ICLAD 2026; act–observe–reflect loop with a design journal) **[S]**. LLANA (LLM few-shot net-weight constraints for BO) **[S]** — [LayoutCopilot](https://arxiv.org/abs/2406.18873); [ICPI](https://arxiv.org/abs/2608.13767); [LLANA](https://arxiv.org/abs/2406.05250).

### Inferences
- PCB layout now has direct, controlled evidence of the same division of labor already seen in IC placement:
  - RAC holds the harness fixed and varies only the interface, which gives a +67.7 pp swing.
  - OmniRouting shows that LLM-emitted traces are nowhere near usable.
  - The DAC 2026 PCB placer shows that LLM grouping plus classical legalization can beat commercial tools.
- **The interface is a bigger lever than the model.** In RAC, eight of nine models reached 89.8–95.9%, above any model on any baseline interface, and newer models were not reliably better (Opus 4.8 > Opus 5; GPT-5.6 Luna > Sol).
- **Code-level LLM evolution of classical engines now covers routing too**: GR-Evolve, VPR-Evolve, FABO, GoalEvolve. Freerouting or a custom KiCad router could be evolved offline the same way.

### Gaps
- The Li et al. DAC 2026 PCB placer and CHIP-MAP/HyperPlace primary texts are not on arXiv. Their numbers come only from the handoff survey.
- RAC's placement and routing backend and its board corpus were not identified in the sections read. It is unknown whether the backend is KiCad-based.
- The Zhang et al. 2025 LLM PCB-routing paper (MDPI) is blocked (403); no quantitative results known.
- DRCY reports no accuracy metrics.

---

## 2. LLM spatial reasoning: capabilities, limits, failure modes, and which representations help

### Takeaway
Read in full, the spatial benchmarks agree. Frontier models fail at **constructing globally consistent geometry**, and difficulty grows with the **number of coupled relations, not the number of objects**. On PlanarBench, solve rates fall below 2% at 11–12 edges, and these are graphs of only 7 or fewer vertices. **Tools fix arithmetic but not planning or global constraints** (FloorplanQA, OPT-Engine, RAC's Coord+Py result). **Images rarely help more than good text** (SpatialEval, TopoBench, FloorplanQA, Blink).

What does help:
- **Structured, semantically labeled encodings**: CSS-style boxes; incident-list graphs, which list each node with its neighbors; cell-aligned grids.
- **Pre-computed structured state from tools.**
- **Relational or imperative-relative representations realized by solvers.**

### Cited Findings
- **PlanarBench** (Sep 2026) **[P][PP]**:
  - **Task.** Draw crossing-free ASCII drawings of planar graphs (2–7 vertices) given an edge list. 91 models were tested.
  - **Edge count drives difficulty.** Its correlation with score is r=−0.85, against −0.47 for vertex count, and r=−0.80 after partialling out vertices. Mean score falls from 46.4% at 5 edges to 16.3% at 8, 5.1% at 10 and **1.0–1.6% at 11–12 edges**.
  - **Best model:** GPT-5.2-pro, 159.5/199.
  - **Extended thinking helps a lot.** Sonnet 3.7 rose from 39.5 to 95.5.
  - **There is a cliff around 30B parameters.**
  - **Failures:** missing edges, especially at high-degree nodes; extra edges; broken or misaligned edges.
  - **Authors' view:** this is a "relational-load" difficulty, with early placement decisions constraining later edge routes.
  - Source: [arXiv 2606.02010](https://arxiv.org/abs/2606.02010).
- **TopoBench** (Mar 2026) **[P][PP]**:
  - **Headline.** Frontier models solve fewer than a quarter of hard topological grid puzzles.
  - **Causal errors.** Interventions show "premature commitment" and "constraint forgetting" hurt solving, while repeated reasoning is benign.
  - **Encoding.** Cell-aligned integer encodings give **+30 to +40 pp** on Bridges and Galaxies but can **degrade** others (−26 pp on Undead for DeepSeek).
  - **Images.** "Adding an image alongside ASCII input does not reliably help and can reduce accuracy."
  - **Tools.** Giving an external engine the authoritative board state raised hard Bridges accuracy from 40% with no tools to 46% with structured state only and **50% with the full structured suite** (legal moves, components). An ASCII render tool scored only 42%.
  - **Conclusion:** "the bottleneck lies in extracting constraints from spatial representations and not in reasoning over them."
  - Source: [arXiv 2603.12133](https://arxiv.org/abs/2603.12133).
- **FloorplanQA** (ICML 2026) **[P][PR]**:
  - **Setup.** 2,000 JSON/XML layouts and 15 models.
  - **Easier tasks.** Models handle distances and angles but fail at constraint satisfaction, geometric unions and multi-step planning.
  - **Failure modes:** (1) treating areas as summed rather than unioned; (2) centroid errors on non-axis-aligned polygons; (3) shortest paths in clutter.
  - **Code interpreter.** It gave "plus over 30–40 percentage points on Distance/Angle but limited benefit on planning tasks".
  - **Images.** Rendered images "do not consistently outperform symbolic input".
  - **Authors' advice:** hybridize with external geometric solvers (unions, shoelace centroid, clearance buffering, oriented rectangle search, A*).
  - Source: [arXiv 2507.07644](https://arxiv.org/abs/2507.07644).
- **SpatialEval** (NeurIPS 2024) **[P][PR]**: competitive models "can fall behind random guessing". VLMs often underperform their LLM backbones, rely less on vision when text suffices, and "often outperform their LLM counterparts with text-only inputs". Redundant vision plus text helps. The authors attribute this to VLMs translating vision into language space — [arXiv 2406.14852](https://arxiv.org/abs/2406.14852).
- **Grid Spatial Understanding (GSU)** (Mar 2026) **[P][PP]**: on text-only grids, models handle basic grid concepts but struggle with egocentric frames of reference and with recognizing 3D shapes from coordinate lists. A visual modality "does not provide a generalizable understanding of 3D space". Fine-tuned small models can approach frontier performance — [arXiv 2603.17333](https://arxiv.org/abs/2603.17333).
- **Visualization-of-Thought** (NeurIPS 2024) **[P][PR]**: prompting GPT-4 to draw intermediate ASCII "mental images" improves grid navigation by 23.5% over no visualization. The effect is prompt-sensitive: an explicit "use ascii-art" instruction raises state tracking. It "is still far from perfect", especially on route planning — [arXiv 2404.03622](https://arxiv.org/abs/2404.03622).
- **Talk like a Graph** (ICLR 2024) **[P][PR]**:
  - The choice of graph text encoding changes accuracy by **4.8% to 61.8%**.
  - **Incident encoding**, which lists each node with its neighbors, beat an adjacency/edge list on finding connected nodes: **53.8% vs 19.8%**. It ranked best on average for most prompting methods.
  - **Integer node names** help arithmetic outputs.
  - Source: [arXiv 2310.04560](https://arxiv.org/abs/2310.04560).
- **LayoutGPT** (NeurIPS 2023) **[P][PR]**: CSS-structured exemplars (left/top/width/height) were "the most essential component" in its prompt ablation. Normalization alone hurt accuracy but helped when combined with the other components — [arXiv 2305.15393](https://arxiv.org/abs/2305.15393).
- **Holodeck** **[P][PP; venue not verified here]**: in a human ranking (mean reciprocal rank), GPT-4-generated **absolute coordinates scored 0.364, no better than random collision-free placement at 0.369**. Edge placement scored 0.645 and LLM-generated **spatial relational constraints solved by DFS (MILP optional)** scored **0.706** — [arXiv 2312.09067](https://arxiv.org/abs/2312.09067).
- **LayoutVLM** **[P][PP]**: averaged over 11 room types:

  | Method | Collision-free | In-bounds | Physically-grounded semantic alignment |
  |---|---|---|---|
  | LayoutGPT (direct coordinates) | 83.8 | 24.2 | 16.6 |
  | Holodeck (relations + search) | 77.8 | 8.1 | 5.6 |
  | I-Design | 76.8 | 34.3 | 18.0 |
  | **LayoutVLM** | 81.8 | **94.9** | **58.8** |

  LayoutVLM uses VLM-produced numeric initial poses plus differentiable spatial relations from visually marked images. Holodeck's search "becomes ineffective with the large number of assets and rigid constraints" — [arXiv 2412.02193](https://arxiv.org/abs/2412.02193).
- **Imperative vs declarative scene generation** (Gumin et al. 2025) **[P][PP]**: an LLM writes step-by-step **relative-placement programs**, and an **LLM-free numeric error-correction** step adjusts program parameters to resolve collisions. Humans preferred these layouts over two declarative constraint-solver systems 82% and 94% of the time — [arXiv 2504.05482](https://arxiv.org/abs/2504.05482). *Tension:* in RAC, a "sequential relations" baseline modeled on this imperative style scored 62.4%, against 90.9% for submitting all relations as one bundle realized jointly ([arXiv 2610.20935](https://arxiv.org/abs/2610.20935)). Joint realization of coupled constraints appears to matter for PCB.
- **Weak-verifier aggregation for spatial layouts** (Stanford/MIT, Jun 2026) **[P][PP]**: an LLM writes many imperfect verifier programs in a layout-verification DSL, which are aggregated using about 10 labeled examples. This gives up to **7× F1 over LLM-as-judge**, and verifier-guided generation improved layout quality by up to 66.2% (human evaluation) — [arXiv 2606.05268](https://arxiv.org/abs/2606.05268).
- **Coordinates and geometry generally** **[P][PP]**:
  - GPSBench: models are "more reliable at real-world geographic reasoning than at geometric computations" — [arXiv 2602.16105](https://arxiv.org/abs/2602.16105).
  - Text2CAD-Bench: performance "degrade[s] substantially on complex topology" — [arXiv 2605.18430](https://arxiv.org/abs/2605.18430).
  - PPNL: GPT-4 with interleaved reason/act is promising on path planning but "fails to perform long-term temporal reasoning", and fine-tuned models fail to generalize to larger or more cluttered grids — [arXiv 2310.03249](https://arxiv.org/abs/2310.03249).
- **Formal intermediate language matters** **[P][PP]**: comparing 4 formal languages across 6 LLMs, the choice "affects both the syntactic and the semantic reasoning capability"; context-aware encodings help — [arXiv 2502.17216](https://arxiv.org/abs/2502.17216).
- **PCB-specific spatial evidence** **[P]**:
  - OmniRouting: LMMs fail multi-net path planning, layer and via assignment, and congestion handling; zero-shot best NRR is 12.6% — [arXiv 2608.04434](https://arxiv.org/abs/2608.04434).
  - RAC: coordinates 23.2%, and adding Python *lowers* that to 21.0% — [arXiv 2610.20935](https://arxiv.org/abs/2610.20935).
  - SchGen: relative placement plus pin-name wiring beats geometry-heavy schematic formats — [arXiv 2605.30345](https://arxiv.org/abs/2605.30345).
  - OmniLayout and PCB-Bench [S]: see Section 1.

### Inferences
- **Never ask the LLM for coordinates or metric distances.** Ask for **named relations with categorical magnitudes**, then realize the whole bundle jointly with a solver: RAC, Holodeck, LayoutVLM.
- **Encode the netlist as an incident list**, one line per part listing its pins and each pin's net and neighbors, rather than a flat edge list (Talk like a Graph). Give parts stable short ids.
- **Expose tool-computed structured state** rather than renders (TopoBench): legal moves, component clusters, unrouted connections, overlaps, distances. Use renders only as an optional secondary channel.
- **Expect failure to scale with relation count.** Decompose by functional group so that each LLM decision involves few coupled relations (PlanarBench).

### Gaps
- No study was found that compares JSON, S-expression, ASCII, SVG and image representations head-to-head **on PCB tasks**. OmniRouting's ablations vary only the information provided (netclass, layers, few-shot, schematic) — [arXiv 2608.04434](https://arxiv.org/abs/2608.04434).
- No study was found on how categorical magnitude bins (tight/close/loose) should be calibrated for PCB.

---

## 3. Agent architectures: planner + solver, LLM→constraints/MILP, LLM-guided search, self-critique with DRC, multi-agent, RAG, evolutionary LLM-in-the-loop

### Takeaway
The architectures with controlled evidence share three properties:
1. **The model picks from a bounded semantic action space**: relations (RAC), operator catalogs ("Who Plans"), edit menus (DRC-Aid), or algorithm-code edits (GR-Evolve, GoalEvolve).
2. **Deterministic tools realize the choice and independently verify it.**
3. **Feedback is structured evidence**, not raw logs.

Planner/executor splits help cheap executors but are not automatically cheaper. LLM→MILP/CP formulation works for canonical problems but is fragile to wording, and formulating constraints is the bottleneck. **Execution infrastructure** decides long-horizon reliability as much as the model does: stateful tools, structured APIs, rollback.

### Cited Findings
- **Relational action contract (RAC)** **[P][PP]**: the agent's semantic commitments go in one bundle, and joint deterministic realization plus an independent checker gives 90.9%. Requirements-only delegation reaches 74.0%, candidate selection 37.4% and coordinates 23.2%. The gain persists across four harnesses — [arXiv 2610.20935](https://arxiv.org/abs/2610.20935).
- **"Who Plans, Who Edits?"** (analog layout repair) **[P][PP]**:
  - **Design.** Models are memoryless, tool-free workers returning JSON. They choose from **bounded operator catalogs**: 8 geometry operators for SKY130, 5 for the DAC, 2 for the oscillator. Guards check schema, bounds and editable cell, apply edits to a checkpointed copy, and roll back on failure. Sign-off tools re-run after every edit, "so a model can make a repair fail but cannot make a layout pass checks it fails".
  - **Planner contract.** The planner returns "a diagnosis (evidence, hypothesis, falsifier) and an ordered list of intents". The executor turns one intent at a time into operator calls. The controller returns to the planner on a regression, a stall, an inexpressible intent or a double refusal.
  - **Who succeeds.** Over 182 blind runs:
    - The cheapest model fixed **1 of 11** alone but **16 of 17 under a flagship planner**.
    - Cheap planners fail more often.
    - "No fixed assignment is cheapest on every task." The cheapest verified option on every task was a mid-tier model alone.
  - **Costs.** Tool runs took 59–94% of wall time (median by task). Input context was 81% of model spend, with a 22:1 input:output token ratio.
  - **Controller.** A Bayesian, per-task-class controller fixed **7 of 8** sealed held-out tasks at 15–40% of flagship spend on three tasks, but 8% more overall.
  - **Reward hacking.** "DRC-count shortcuts through fixed foundry cells show that legality must be part of the contract."
  - Source: [arXiv 2610.24234](https://arxiv.org/abs/2610.24234).
- **DRC-Aid** **[P][PP]**: a deterministic rule engine turns Calibre violations into a **bounded menu of geometric edits**. The LLM selects from the menu, with budgeted DFS, backtracking and a global memory bank that prevents cycles. It reached DRC-clean, LVS-equivalent repairs in **about 92.5%** of cases with about 98% violation reduction. Under the same infrastructure, random selection reached 54.4%, a deterministic heuristic 83.3%, and **static prompting peaked at 6.6%** complete resolution. The LLM's advantage widens at six or more violations — [arXiv 2607.22761](https://arxiv.org/abs/2607.22761).
- **EvoDRC** **[P][PP]**:
  - It splits layouts into bounded repair crops, each handled by a four-role agent workflow with local DRC, connectivity and impact-preview tools.
  - Layer-wise "skill files" evolve from a repair database through a Skill Refiner, a DB Summarizer and a Skill Judge.
  - The paper is internally inconsistent: the abstract says 73.5% "overall reduction compared to the reported baseline", while the conclusion says 83.6% average DRV reduction on the DAC26 DRC benchmark.
  - Source: [arXiv 2607.20019](https://arxiv.org/abs/2607.20019).
- **SCALE** (NVIDIA et al.) **[P][PP]**: layout geometry is serialized to structured text. A model learns masked-polygon reconstruction, and the generated violation pairs fine-tune a DRC-VLM. That VLM raises SOTA agents' local DRV-fix solve rates by +12–25%, up to 97%, on 100 real sub-2 nm cases — [arXiv 2607.21850](https://arxiv.org/abs/2607.21850).
- **Agentic RTL-to-GDS lessons** (Jul 2026) **[P][PP]**:
  - Setup: PicoRV32 with commercial tools; Claude Code, Claude Code plus EDA skills, and FluxEDA; four models.
  - (1) "Domain-specific skills improve agents' understanding of individual subtasks but do not ensure reliable completion".
  - (2) Agents with similar progress differ by **up to 141× in Token ROI**.
  - (3) "Low-level tool-interface mismatches are a major source of physical design failures, particularly when Tcl commands depend on the tool version or execution mode".
  - Recommendation: "structured tool interfaces, persistent design context, controlled execution, and process-level evaluation".
  - Source: [arXiv 2607.17528](https://arxiv.org/abs/2607.17528).
- **FluxEDA** **[P][PP]**: a stateful gateway with persistent backend tool instances, structured requests and responses, state reuse and **rollback**, instead of "isolated shell invocations". It was demonstrated on post-route ECO and standard-cell library optimization — [arXiv 2603.25243](https://arxiv.org/abs/2603.25243).
- **Harness prevalence** **[P]**: loops dominate. Retrieval and memory appear "where previous flow and benchmark records can be reused". Executable feedback (compiler, simulator, DRC) enables repeated rejection and revision, which document-centered tasks lack — [arXiv 2606.19795](https://arxiv.org/abs/2606.19795).
- **Memory** **[P][PP]**: in MFM, persistent multimodal memory of episodic, spatial, semantic and procedural records raised CUABench-KiCad reward from 0.267 to 0.440 — [arXiv 2610.22686](https://arxiv.org/abs/2610.22686). The RF-workflow agent kept tool knowledge in markdown files it maintained itself, and turned review feedback into standing conventions — [arXiv 2608.31006](https://arxiv.org/abs/2608.31006).
- **Multi-run consensus** **[P][PP]**: DRCY runs k parallel group-review agents. A separate consensus agent keeps findings that recur across runs, critically re-checks findings seen only once against the datasheet, and re-examines contradictions — [arXiv 2603.15672](https://arxiv.org/abs/2603.15672).
- **LLM→MILP/CP formulation** **[P][PP]**:
  - **OPT-Engine:** "Solver-integrated reasoning" is essential as complexity grows. Pure chain-of-thought "suffers from a critical robustness gap". Tools "help with local calculations [but] still fail to adhere to global optimization constraints". "**The automated formulation of constraints represents the primary bottleneck**", with semantic sensitivity when specifications deviate from canonical versions — [arXiv 2601.19924](https://arxiv.org/abs/2601.19924).
  - **DCP-Bench-Open:** **Python-based modeling frameworks (CPMpy, OR-Tools) beat MiniZinc**. Repeated sampling plus self-verification adds up to 35%, and the best setting reaches about 90–91% on CPMpy. LLMs "can over-encode the example instance given in the prompt" — [arXiv 2506.06052](https://arxiv.org/abs/2506.06052).
  - **CSPLib wording study:** performance "drops sharply under contextual and linguistic variation"; distracting details cause misread objectives, suggesting data contamination — [arXiv 2511.14334](https://arxiv.org/abs/2511.14334).
  - **Agentic constraint-model improvement:** generated models beat the originals in 68.5% of 1,500 cases. A **best-of-5 sampling baseline with the same validation tools matched it** (101 vs 102.8 of 150) — [arXiv 2608.08127](https://arxiv.org/abs/2608.08127).
  - **Optimization-modeling survey:** benchmark datasets have a "surprisingly high error rate" — [arXiv 2508.10047](https://arxiv.org/abs/2508.10047).
  - **MCP-Solver:** exposes MiniZinc, PySAT and Z3 to LLMs over MCP, with iterated validation of model edits — [arXiv 2501.00539](https://arxiv.org/abs/2501.00539).
  - **OptiMUS** **[S]** — [arXiv 2310.06116](https://arxiv.org/abs/2310.06116).
- **Evolutionary LLM-in-the-loop** **[P]**:
  - **AlphaEvolve** "optimize[d] an already highly optimized Verilog implementation of a key TPU arithmetic circuit". The change "was also independently caught by downstream synthesis tools" and is "integrated into an upcoming TPU". AlphaEvolve also reports a 23% average kernel speedup (about 1% less Gemini training time) and FlashAttention IR optimization — [arXiv 2506.13131](https://arxiv.org/abs/2506.13131).
  - **GR-Evolve, VPR-Evolve, GoalEvolve, FABO:** see Section 1. GoalEvolve's design converts unmet QoR targets into normalized gaps and attributes them to a stage before editing code.
  - Method background: OPRO [arXiv 2309.03409](https://arxiv.org/abs/2309.03409); EoH [arXiv 2401.02051](https://arxiv.org/abs/2401.02051); ReEvo [arXiv 2402.01145](https://arxiv.org/abs/2402.01145).

### Inferences
- **Action-space design is the main lever**, ahead of agent topology. Bounded menus, operator catalogs and relational bundles all beat free-form generation by large margins.
- **Planner/executor splits are a cost tool, not a quality guarantee.** The cheapest verified option was a single mid-tier model. Learned routing per task class is worth it only once a task taxonomy exists.
- For LLM-written constraints, prefer a **Python constraint API** (CPMpy/OR-Tools style, or a domain DSL embedded in Python) over a separate modeling language. Validate on multiple instances to catch over-encoding.

### Gaps
- No study was found that applies OptiMUS-style LLM→MILP formulation to **PCB placement constraints**. RAC's relation schema with a fixed solver sidesteps formulation, which is arguably better.
- No controlled study was found of tool granularity for KiCad specifically, i.e. few coarse tools versus hundreds of fine ones.

---

## 4. Datasheet / application-note understanding for layout recommendations

### Takeaway
**No published system extracts PCB layout recommendations from datasheets.** Examples of such recommendations: "input cap within X mm of VIN", "keep SW node small", "Kelvin-connect sense". The surrounding pieces now exist and are proven:
- Faithful **chunked datasheet→knowledge-graph extraction with provenance**: 98.8% faithful, against 76.1% for one-shot.
- **Agentic datasheet retrieval with quality scoring and consensus** (DRCY, in production).
- **Rule text→executable checker code** (DRC-Coder; LLM-written weak verifiers).
- Pin-role/constraint knowledge graphs (PCBSchemaGen).

### Cited Findings
- **Hierarchical hardware knowledge graphs from datasheets** (Oct 2026) **[P][PP]**: chunk-based property extraction, hierarchical routing and iterative refinement. Graph updates are applied "through validated instructions and deterministic local execution", with source provenance kept. On 20 datasheets this gives **98.8% property faithfulness vs 76.1% for one-shot**. The pipeline covers 83.6% of the baseline's faithful properties, while the baseline covers only 10.5% of the pipeline's. Naive one-shot "omits relevant specifications even when the document fits within the model's context window" — [arXiv 2610.12762](https://arxiv.org/abs/2610.12762).
- **DRCY** **[P][PP]**: a five-stage pipeline:
  1. netlist augmentation;
  2. component selection and grouping;
  3. **agentic datasheet retrieval** from DigiKey or client APIs, with a self-evaluation score weighted toward pin-function coverage (40%), application information (20%) and typical application circuits (15%). It makes up to 5 attempts from alternative sources and caches results for 7 days;
  4. per-group pin-by-pin review agents;
  5. a multi-run consensus agent and an error-grouping agent.

  Findings are posted as inline review comments — [arXiv 2603.15672](https://arxiv.org/abs/2603.15672).
- **DRC-Coder** **[P][PP]**: rule text plus illustrations go to an interpretation LLM, which hands off to a coding LLM. Tools analyze foundry rules and layout DRVs and evaluate the code. It gives F1 1.000, against 0.631 for standard prompting — [arXiv 2412.05311](https://arxiv.org/abs/2412.05311). *(This maps directly onto "datasheet layout rule → executable board check".)*
- **LLM-written weak verifiers** **[P][PP]**: verifier programs in a layout DSL, aggregated, reach up to 7× F1 over LLM judges — [arXiv 2606.05268](https://arxiv.org/abs/2606.05268).
- **SpecMap** **[P][PP]**: hierarchical narrowing for datasheet-to-code traceability (repository, then file, then symbol). It reaches up to 73.3% file-mapping accuracy while cutting **LLM tokens by 84%** and runtime by about 80% — [arXiv 2601.11688](https://arxiv.org/abs/2601.11688).
- **DocEDA** **[P][PP]**: a datasheet layout-analysis model splits documents into sections (parameters, diagrams, curves), then chain-of-thought parameter extraction and schematic parsing — [arXiv 2412.05301](https://arxiv.org/abs/2412.05301).
- **Datasheet-aware compatibility verification** **[S]**; **PCBSchemaGen** (per-IC knowledge graph with a 32-role pin ontology, 16k→300 tokens; verified separately) **[S]**; **pcbGPT** **[S]**; **ICGeo8K** footprint geometry **[S]** — [arXiv 2608.25217](https://arxiv.org/abs/2608.25217); [arXiv 2602.00510](https://arxiv.org/abs/2602.00510); [arXiv 2606.01188](https://arxiv.org/abs/2606.01188); [arXiv 2508.03725](https://arxiv.org/abs/2508.03725).
- **In practice** **[P]**: the RF-workflow agent "noticed that the ESD-protected variant is limited to V_CEO = 2.25 V" mid-design and redesigned the bias unprompted — [arXiv 2608.31006](https://arxiv.org/abs/2608.31006).
- Layout rules are conditional on package and frequency (decoupling guides) **[V]** — [NextPCB](https://www.nextpcb.com/blog/decoupling-capacitor-placement-pcb); [Sierra Circuits](https://www.protoexpress.com/blog/decoupling-capacitor-placement-guidelines-pcb-design/).

### Inferences
- The recommended pipeline is assembled from proven parts:
  1. retrieve with quality scoring (DRCY);
  2. extract by chunks into a knowledge graph with provenance and applicability conditions (hardware-KG paper);
  3. map extracted layout statements to a **closed predicate vocabulary** that is also the RAC-style relation schema (e.g. `near(C_in, U1.VIN, tight)`, `min_loop({U1.SW, L1, C_out})`, `kelvin(R_sense)`);
  4. generate or attach a checker for each predicate (DRC-Coder, weak-verifier pattern);
  5. use multi-run consensus for safety-critical extractions.

### Gaps
- No dataset or benchmark of datasheet *layout-guideline* extractions exists.
- No work was found that parses reference-layout figures (EVM layouts) into placement relations.

---

## 5. Explainability and design-intent capture ("the why")

### Takeaway
No PCB system records a standard rationale graph. But 2026 systems converged on four mechanisms that together amount to design-intent capture:
1. **Intent expressed as named relations** that are themselves checkable predicates (RAC; LayoutCopilot's human-accepted suggestions).
2. **Structured diagnoses** with evidence, hypothesis and falsifier ("Who Plans").
3. **Audit trails**: stored prompts, per-role ledgers, full lineage logs, mechanism memory.
4. **The design kept as version-controlled code** that regenerates deterministically.

### Cited Findings
- **Intent as checkable relations** **[P][PP]**. RAC's agent "decides which relations an artifact should satisfy". Failures come back as "semantic repair evidence, so repair operates on intent instead of geometry". The checker is independent of the solver's own satisfaction labels — [arXiv 2610.20935](https://arxiv.org/abs/2610.20935).
- **Structured diagnosis and audit** **[P][PP]** ("Who Plans, Who Edits?"):
  - The planner emits evidence, hypothesis, falsifier and intents, each with a target, mechanism, operators, scope and expected effect.
  - "Every repair-model prompt is stored before the call, so the information available to each model can be audited."
  - A per-role ledger tracks tokens, spend and tool time.
  - An evidence builder attributes post-layout degradation to parasitic groups.
  - Source: [arXiv 2610.24234](https://arxiv.org/abs/2610.24234).
- **Design as code** **[P][PP]**: "the design exists entirely as version-controlled code and regenerates deterministically". Human reviewers act as gates with machine-checkable criteria — [arXiv 2608.31006](https://arxiv.org/abs/2608.31006).
- **Explanations for congestion** **[P][PP]**: a multimodal LLM assistant (MLLMA) uses MLLM-guided genetic prompting and interpretable preference learning over visual, tabular and text features. It produces a "Design Suggestion Deck" of influential layout features and targeted fixes, and is state of the art on CircuitNet — [arXiv 2510.15872](https://arxiv.org/abs/2510.15872).
- **Explained parameter choices** **[P-via-survey]**: HyperPlace's agent "proposes and explains hyperparameter configurations" — [arXiv 2606.19795](https://arxiv.org/abs/2606.19795).
- **Mechanism memory** **[P][PP]**: GoalEvolve keeps "local effects, optimization debt, and downstream retention" as evidence for later evolution steps — [arXiv 2608.16733](https://arxiv.org/abs/2608.16733).
- **Handoff provenance** **[P][PP]**: the handoff survey calls for "residual risk [to] accompany accepted handoffs" and artifacts to stay "traceable, auditable, and reusable". LayoutCopilot "separates designer intent from tool-mediated syntactic and functional validation" and keeps "the request, command history, and rejected alternatives for designer review" — [arXiv 2606.19795](https://arxiv.org/abs/2606.19795).
- **Reviewable diffs** **[P]**: AlphaEvolve notes that expressing changes "directly in Verilog… foster[s] trust and simplif[ies] adoption" — [arXiv 2506.13131](https://arxiv.org/abs/2506.13131).
- **Provenance-preserving knowledge graphs** **[P][PP]** for datasheet facts — [arXiv 2610.12762](https://arxiv.org/abs/2610.12762).
- **Readable, lineage-logged objectives** (CoEvoP&R) **[S]**; ICPI design journal **[S]** — [CoEvoP&R repo](https://github.com/FCHXWH823/CoEvoP-R); [ICPI](https://arxiv.org/abs/2608.13767).

### Inferences
- In a RAC-style system, the committed relation bundle *is* the design-intent record. A rationale for a relation is its link to (a) a datasheet knowledge-graph node or a user requirement, (b) the checker verdict and measured margin, and (c) the planner diagnosis that introduced it. An explanation is generated by walking those links, not composed after the fact.

### Gaps
- No user study was found on whether engineers trust or use LLM layout explanations.
- No standard schema for PCB design intent was found.

---

## 6. Vision feedback: rendered layout images as feedback to multimodal models

### Takeaway
On routing, **structured scoring feedback beats visual feedback**: OmniRouting's scoring tool cut the cross-model mean DRC count by 77.1%, while visualization alone gave smaller and inconsistent gains. Across benchmarks, adding images to good text gives little or negative benefit (TopoBench, FloorplanQA, SpatialEval). General MLLMs remain weak at fine perception (Blink: about 50%, against 95.7% for humans) and at schematic grounding (OmniSch). Vision helps when it is **specialized or fine-tuned** (SCALE's DRC-VLM), **used for qualitative judgment alongside scripts** (MAGE [S]), or **for reading figures in documents** (DRC-Coder).

### Cited Findings
- **OmniRouting agentic study** **[P][PP]**:
  - "Visual feedback lowers Total [DRC] for every model, and Score reduces its cross-model mean from 141.18 to 32.31 (−77.1%)."
  - Visualization alone barely moves routability. For GPT-5.5, NRR went from 21.71% to 20.96% while clearance violations fell from 42.87 to 32.90.
  - A pre-routing tool raised reference similarity (MGS) for all eight models by about 10 points.
  - "Tools improve local legality and routing-corridor selection more than global connectivity."
  - Source: [arXiv 2608.04434](https://arxiv.org/abs/2608.04434).
- **TopoBench**: image plus ASCII "does not reliably help and can reduce accuracy". **FloorplanQA**: images "do not consistently outperform symbolic input". **SpatialEval**: vision-only rarely beats the LLM backbone **[P]** — [TopoBench](https://arxiv.org/abs/2603.12133); [FloorplanQA](https://arxiv.org/abs/2507.07644); [SpatialEval](https://arxiv.org/abs/2406.14852).
- **Blink** (ECCV 2024) **[P][PR]**: on perception tasks that humans solve "within a blink", GPT-4V scored 51.26% and Gemini 45.72%, only 13.17 and 7.63 points above random. Specialist computer-vision models do much better — [arXiv 2404.12390](https://arxiv.org/abs/2404.12390).
- **OmniSch** (1,854 schematics) **[P][PP]**: LMMs show "unreliable fine-grained grounding, brittle layout-to-graph parsing, inconsistent global connectivity reasoning and inefficient visual exploration". Tool-augmented active visual search improves schematic-to-netlist accuracy and efficiency — [arXiv 2604.00270](https://arxiv.org/abs/2604.00270).
- **MMCircuitEval** (3,614 multimodal QA pairs) **[P][PP]**: there are "significant performance gaps… particularly in back-end design and complex computations" — [arXiv 2507.19525](https://arxiv.org/abs/2507.19525).
- **CoDeLayout** (graphic-design layouts) **[P][PP]**: on compositional multi-layer layout understanding, even GPT-o3 reaches only 79.68%, while a post-trained Qwen2.5-VL-7B reaches 91.66% — [arXiv 2608.26716](https://arxiv.org/abs/2608.26716).
- **SCALE** **[P][PP]**: a fine-tuned DRC-VLM gives +12–25% DRV-fix solve rate — [arXiv 2607.21850](https://arxiv.org/abs/2607.21850). **DRC-Coder** uses a VLM to read rule illustrations **[P]** — [arXiv 2412.05311](https://arxiv.org/abs/2412.05311).
- **PCBA visual QA** (assembly inspection, not layout) **[P][PP]**: task-aware GRPO fine-tuning reached an 83.24 overall score on a PCBA standard-to-real challenge — [arXiv 2609.21276](https://arxiv.org/abs/2609.21276).
- **VeoPlace, MAGE, PlaceReasoner-Beta** (IC macro placement with rendered canvases, verified separately) **[S]** — [VeoPlace](https://arxiv.org/abs/2603.28733); [MAGE](https://arxiv.org/abs/2607.18536).

### Inferences
- In a KiCad loop, make **structured, numeric feedback** the primary channel: per-predicate verdicts, DRC lists with object ids, unrouted counts. Add renders only for gestalt review (signal flow, clustering, aesthetics), ideally with ids overlaid that match the text. Do not rely on a general VLM to spot small geometric defects.

### Gaps
- No PCB study isolates the contribution of rendered images when strong structured feedback is already available.

---

## 7. Quantitative comparisons of LLM-driven layout versus classical tools

### Takeaway
- **PCB, LLM emits geometry:** classical tools win by a wide margin. In OmniRouting, PcbRouter reaches 56.2% NRR against the best LMM's 12.6% and humans' 93.6%. In PCBWorld [S], Freerouting scores about 0.8 clean pass against 0.65 for the best LLM, and LLMs score 0 on large boards.
- **PCB, LLM steers a classical engine:** results can beat commercial tools. The DAC 2026 coarse-to-fine placer beats a commercial placer, NS-Place and Quilter on routed wirelength and vias. RAC reaches 90.9% clean pass on relation-specified tasks.
- **IC:** LLM-evolved or LLM-steered classical engines report gains of a few percent to tens of percent, mostly self-reported preprints.

### Cited Findings
- **OmniRouting** (zero-shot / agentic, with a classical baseline) **[P][PP]**:
  - Best LMM zero-shot: 12.60% NRR (Claude Opus 4.8).
  - Best agentic: 27.98% (GPT-5.5, all tools).
  - PcbRouter: 56.20% NRR / 71.37% PRR.
  - GPCB: 0.69% NRR.
  - Human: 93.58% / 95.91%.
  - Source: [arXiv 2608.04434](https://arxiv.org/abs/2608.04434).
- **RAC** **[P][PP]**: interface comparison on 98 PCB tasks: 23.2%, 21.0%, 37.4%, 62.4%, 74.0%, then 90.9% for RAC — [arXiv 2610.20935](https://arxiv.org/abs/2610.20935).
- **Li et al. DAC 2026 PCB placer** **[P-via-survey][PR]**: routed wirelength and vias improve by 55%/73% against a commercial placer, 34%/26% against NS-Place and 15%/13% against Quilter, on 6 industrial boards with the same commercial router — [arXiv 2606.19795](https://arxiv.org/abs/2606.19795).
- **PCBAgent** **[P-via-survey]**: the only fully legal method on 17 tasks; HPWL 1.04× and surface wires 0.94× relative to manual — [arXiv 2606.19795](https://arxiv.org/abs/2606.19795).
- **HyperPlace**: up to 22.24% better than DREAMPlace 3.0 under fences. **CHIP-MAP**: area up to −1.5%, 61.6% of TNS repaired **[P-via-survey]** — [arXiv 2606.19795](https://arxiv.org/abs/2606.19795).
- **GR-Evolve**: up to −8.72% post-detailed-route wirelength. **VPR-Evolve**: wirelength up to −18.1% and delay −9.8% against stock VPR. **GoalEvolve**: TNS +30.67% and leakage −21.18% against default OpenROAD. **FABO**: wirelength −0.83% overall, −2.66% for large nets, against SALT **[P]** — [GR-Evolve](https://arxiv.org/abs/2604.22234); [VPR-Evolve](https://arxiv.org/abs/2607.24998); [GoalEvolve](https://arxiv.org/abs/2608.16733); [FABO](https://arxiv.org/abs/2608.30268).
- **DRC-Aid**: 92.5% complete repair, against 83.3% for a deterministic heuristic, 54.4% for random and 6.6% for static prompting. **Ho & Ren**: cells up to 19.4% smaller. **DRC-Coder**: F1 1.000 vs 0.631 **[P]** — [DRC-Aid](https://arxiv.org/abs/2607.22761); [Ho & Ren](https://arxiv.org/abs/2406.06549); [DRC-Coder](https://arxiv.org/abs/2412.05311).
- **Scene-layout analogues** **[P]**: Holodeck's LLM absolute coordinates were no better than random (MRR 0.364 vs 0.369); constraints plus a solver scored 0.706. LayoutVLM's in-bounds rate was 94.9%, against 24.2% for LayoutGPT and 8.1% for Holodeck — [Holodeck](https://arxiv.org/abs/2312.09067); [LayoutVLM](https://arxiv.org/abs/2412.02193).
- Verified separately and kept [S]: VeoPlace (beats ChiPFormer on 9 of 10), EvoPlace (HPWL −5–8%), OrderPlace (−14% vs EGPlace), CoEvoP&R (routed wirelength −16.9%), MAGE (+WNS but +29.7% routed wirelength) — see the Section 1 links.

### Inferences
- The only PCB results where an LLM-involved system beats classical or commercial tools all keep geometry in a solver: the DAC 2026 placer (MILP legalization) and PCBAgent (RL plus MILP).

### Gaps
- No independent replications of any of these results were found.
- No joint placement-plus-routing comparison of an LLM-steered KiCad flow against Freerouting-based baselines on real boards was found.

---

## 8. Implications for an LLM-driven KiCad placer/router

### Takeaway
Build a **relational-contract, solver-realized, independently verified** system:
- The LLM commits **named relations with categorical magnitudes** over parts, groups, nets and board features, each linked to its evidence.
- KiCad-side solvers realize the whole bundle jointly: grouping, global placement, MILP/CP-SAT legalization, and Freerouting or a custom router.
- **Independent** checkers verify every relation plus DRC, ERC and parity. Feedback returns structured, per-predicate evidence with admissible relaxations.
- The relation bundle doubles as the design-intent record.

RAC (90.9% vs 23.2%), OmniRouting, DRC-Aid, "Who Plans" and the DAC 2026 coarse-to-fine PCB placer give direct, controlled evidence for each part of this design.

### Cited Findings (evidence base)
- Relational contract versus coordinates, candidates, sequential relations and requirements-only, held constant across harnesses — [RAC](https://arxiv.org/abs/2610.20935) [P].
- LLM traces are unusable (12.6% NRR) and structured scoring feedback beats visuals — [OmniRouting](https://arxiv.org/abs/2608.04434) [P].
- An edit menu plus verification, DFS and memory beats prompting and heuristics — [DRC-Aid](https://arxiv.org/abs/2607.22761) [P].
- Bounded operators, guards, planner/executor split, cost ledger, legality inside the contract — ["Who Plans, Who Edits?"](https://arxiv.org/abs/2610.24234) [P].
- LLM grouping plus MILP legalization beats commercial tools — [handoff survey on Li et al. DAC 2026](https://arxiv.org/abs/2606.19795) [P-via-survey].
- Incident-list encoding, cell-aligned formats, structured state tools, and limited benefit from images — [Talk like a Graph](https://arxiv.org/abs/2310.04560); [TopoBench](https://arxiv.org/abs/2603.12133); [FloorplanQA](https://arxiv.org/abs/2507.07644) [P].
- Difficulty scales with coupled relations — [PlanarBench](https://arxiv.org/abs/2606.02010) [P].
- Structured tool interfaces, persistent context and rollback matter more than skills — [RTL-to-GDS lessons](https://arxiv.org/abs/2607.17528); [FluxEDA](https://arxiv.org/abs/2603.25243) [P].
- Design as code through pcbnew/kicad-cli, netlist-identical by construction, human review gates — [RF workflow](https://arxiv.org/abs/2608.31006) [P]; [kicad-pycbnew](https://arxiv.org/abs/2609.27522) [P].
- Datasheet knowledge graph with provenance; agentic datasheet retrieval with consensus; rule text to checker code — [hardware KG](https://arxiv.org/abs/2610.12762); [DRCY](https://arxiv.org/abs/2603.15672); [DRC-Coder](https://arxiv.org/abs/2412.05311) [P].
- Offline LLM evolution of classical router and placer code — [GR-Evolve](https://arxiv.org/abs/2604.22234); [VPR-Evolve](https://arxiv.org/abs/2607.24998); [GoalEvolve](https://arxiv.org/abs/2608.16733) [P].

### Inferences (concrete recommendations; synthesis, not sourced claims)

**A. Representation (what the LLM sees)**
1. **Typed board state**, never asked for in pixels:
   - parts with stable short ids, footprint class, size class, side and locked flag;
   - an **incident-list netlist**: per part, its pins with net name, pin role from the datasheet KG and connected parts;
   - net classes and criticality tags;
   - **tool-computed facts**: groups and clusters, overlaps, unrouted connections, DRC items with object ids, per-relation verdicts with margins.

   Exact coordinates may be *observable*, as in RAC, but are never *writable*.
2. **Hierarchy by function.** Present functional groups as first-class objects: power stage, MCU plus decoupling, connector plus ESD, analog front end. This keeps each decision's relation count low (PlanarBench), and the DAC 2026 placer's grouping agents work this way. Grouping itself can be LLM-proposed and code-verified, in the style of GENIE-ASI subcircuit identification.
3. **Images optional and secondary.** Use labeled renders that share ids with the text, for qualitative review only.

**B. Action space (what the LLM can write)**
- A closed **relation vocabulary** with categorical magnitudes:
  - `near(a, b|pin, {tight, close, loose})`
  - `same_side`, `align(axis)`, `symmetric(group, axis)`
  - `edge(part, side)`, `keepout(region|part, layers)`
  - `group(members)`, `orient_toward(part, pin)`
  - `route_priority(net)`, `matched(netA, netB, tolerance class)`
  - `layer_pref(net, layers)`, `via_limit(net, n)`, `min_loop(nets)`, `plane(net, layer, region)`
- Metric values for each magnitude class are resolved from net class, stackup and datasheet knowledge, never chosen by the LLM.
- **Submit the whole bundle at once** for joint realization (RAC: 90.9% bundled vs 62.4% sequential).

**C. Division of labor**
- **LLM:** functional partitioning; criticality tagging; turning datasheet/app-note statements and user requirements into relations; choosing relaxations when the solver reports infeasibility; picking repairs from a menu.
- **Solvers:** group placement (analytical or SA); **MILP/CP-SAT legalization** (courtyards, edges, keepouts); critical-net routing under relation constraints; bulk routing (Freerouting, KiCad push-and-shove); calculators for widths, impedance and clearances.
- **Independent checkers:** kicad-cli DRC/ERC; schematic parity; per-relation geometric oracles written as code (DRC-Coder and weak-verifier pattern), never the solver's own satisfaction flag.

**D. Feedback loop**
- The realizer returns which relations it realized or violated, conflicting sets, magnitudes and **admissible relaxations**.
- Repairs come from **rule-engine-generated menus**, with DFS, backtracking and memory against cycles (DRC-Aid).
- Budget iterations explicitly; "Who Plans" and OmniRouting show more steps can hurt.
- Use a **mid-tier model alone** by default. Escalate to a flagship planner only on verified failure, recording per-role spend. Input context dominates cost, so keep observations compact.
- Use **stateful tool sessions with checkpoint and rollback** (FluxEDA pattern), rather than re-loading boards per shell call.

**E. Datasheet pipeline → relations**
- Retrieve and score datasheets (DRCY). Extract by chunks into a knowledge graph with provenance and applicability conditions (hardware-KG paper). Map statements to the closed relation vocabulary. Generate a checker per relation type. Use multi-run consensus for safety-critical rules.

**F. "Why"**
- The intent record is the relation bundle plus, for each relation, (source evidence → planner diagnosis → checker verdict and margin). Store it in a sidecar file next to the `.kicad_pcb`. Keep the whole design as regenerable code (RF workflow, kicad-pycbnew).

**G. Offline improvement**
- Evolve the realizer itself (placement objectives, legalizer heuristics, Freerouting cost functions) over a board corpus with full-flow scoring, using the GR-Evolve, VPR-Evolve and GoalEvolve pattern with stage-attributed goal gaps.

**H. Evaluation**
- RAC-style relation tasks (clean-pass rate); OmniRouting and PCBWorld routing metrics; DRC and parity counts; tokens, cost and latency per verified board. Guard against metric gaming ("Who Plans" DRC-count shortcuts): legality is always part of the acceptance contract.

### Gaps
- Whether RAC's 90.9% holds on full real boards with dozens of interacting relations is untested. Its 98 tasks are task-scoped, and its board corpus was not identified in the sections read.
- The best calibration of categorical magnitudes and the right grouping granularity for PCBs are open questions.
- No public KiCad-native implementation of a relational contract was found.
