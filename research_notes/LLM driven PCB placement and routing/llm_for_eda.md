# LLMs and Agentic AI for EDA Physical Layout (PCB + IC Placement & Routing), Spatial Reasoning, and Design-Intent Explanation

_Method note for the report writer: compiled 2026-10-20. Direct page fetches failed during this session: WebFetch could not resolve arxiv.org or huggingface.co, the egress proxy refused arxiv.org, and GitHub repos outside this project were not accessible. As a result, every finding below comes from web-search result summaries of the cited pages: abstracts, HTML snippets, review sites such as Pith and papernotes, and vendor blogs. **No paper was read in full.** Numbers are as reported in those snippets and were not checked against the papers' tables. Status flags: **[PR]** = peer-reviewed venue, **[WS]** = workshop, **[PP]** = arXiv preprint / not yet peer-reviewed, **[V]** = vendor/blog/marketing, **[C]** = community/README. The search budget ran out before OmniRouting, Holodeck/LayoutVLM, and the 2023 LLM4EDA survey could be checked; see the Gaps sections._

---

## 1. LLM-for-EDA papers and systems for physical layout (2023–2026): what was tried, what worked, what failed

### Takeaway
The field has converged on a clear pattern. LLMs do well as **orchestrators, strategists, constraint/objective writers, and heuristic evolvers** wrapped around classical engines: VeoPlace, EvoPlace, CoEvoP&R, OrderPlace, LayoutCopilot, and MCP4EDA all report gains. They do poorly as **direct coordinate or geometry generators**. In PCBWorld, engine-free geometry generation reached a 0.02 clean-pass rate, against 0.65 for interactive tool use and 0.80 for Freerouting. LLM agents scored 0.00 on large boards. PCB-specific LLM work is still dominated by benchmarks (PCB-Bench, PCBWorld, OmniLayout, PCBInnoBench, PCB-QA) that show large gaps. The flagship industrial demo, GPT-6 Astra in KiCad (September 2026), relied on Freerouting for the bulk of its routing.

### Cited Findings

**Surveys and framing**
- "Agentic Electronic Design Automation: A Handoff Perspective" (Liu, Han, Lu, Zheng, Yan, Bei Yu; June 2026) reviews 82 agentic EDA systems. It classifies them by "handoff validity": an artifact is valid if it meets the next consumer's acceptance conditions and carries context, evidence, and provenance. The three classes are Stage-Bound, Flow-Bound, and Organization-Bound. [PP] — [arXiv 2606.19795](https://arxiv.org/abs/2606.19795); coverage in [SemiEngineering](https://semiengineering.com/edas-future-is-evidence-driven-automation/)
- "The Dawn of Agentic EDA" survey states that no LLM-driven autonomous agent has yet demonstrated a complete, human-free tape-out of an industrial chip. [PP] — [arXiv 2512.23189](https://arxiv.org/pdf/2512.23189)
- The Duke survey "A Survey of Research in LLMs for EDA" (ACM TODAES) flags that richer design-rationale and constraint documentation is underused in LLM work. It also names LLM black-box-ness as a barrier to tracing reasoning. [PR] — [ACM 10.1145/3715324](https://dl.acm.org/doi/10.1145/3715324); [arXiv 2501.09655](https://arxiv.org/pdf/2501.09655)
- "Large Language Models for EDA: Future or Mirage?" is an ACM TODAES review that covers LayoutCopilot and PCBAgent as human-in-the-loop layout examples. [PR] — [ACM 10.1145/3736167](https://dl.acm.org/doi/10.1145/3736167); related Bei Yu IEEE CEDA talk: [CEDA](https://ieee-ceda.org/presentation/lecture/large-language-model-eda)
- An early-2024 LLM4EDA survey listed physical design and multimodal circuit feature alignment as *future* directions. Physical design was largely unexplored at that point. [PP] — [arXiv 2401.12224](https://arxiv.org/html/2401.12224v1)
- A 2026 PCB-specific survey, "Surveying GenAI-based Automation in Printed Circuit Board Design and Test", exists. Its content could not be retrieved in this session. [PP] — [arXiv 2606.17074](https://arxiv.org/pdf/2606.17074)

**Flow / tool-orchestration agents (IC)**
- **ChatEDA** (Aug 2023): a fine-tuned LLM, "AutoMage", decomposes a natural-language request into sub-tasks, writes Python scripts for EDA tools including OpenROAD, and executes them across RTL→GDSII. The authors claim it beats GPT-4. [PP per sources found] — [arXiv 2308.10204](https://arxiv.org/pdf/2308.10204). The handoff survey calls it the only system in its corpus whose input→output spans RTL to final ASIC layout — [arXiv 2606.19795](https://arxiv.org/pdf/2606.19795)
- **MCP4EDA** (Jul 2025, UMD/Duke): an MCP server that exposes Yosys, Icarus, OpenLane, GTKWave, and KLayout to Claude Desktop/Cursor. In a closed "backend-aware synthesis" loop, the LLM reads post-layout timing/power/area and rewrites synthesis TCL. Self-reported results: 15–30% better timing closure and 10–20% area reduction versus default flows. [PP] — [arXiv 2507.19570](https://www.arxiv.org/abs/2507.19570). NL2GDS criticizes it as tool orchestration that assumes RTL already exists — [arXiv 2603.05489](https://arxiv.org/pdf/2603.05489)
- **AutoEDA**: MCP-based RTL→GDSII microservice agents with locally fine-tuned models, motivated by the privacy risk of external APIs. [PR, ACM TODAES] — [arXiv 2508.01012](https://arxiv.org/html/2508.01012v2); [DOI 10.1145/3842675](https://www.citedrive.com/en/discovery/autoeda-enabling-eda-flow-automation-through-microservice-based-llm-agents/)
- **ORAssistant**: a RAG conversational assistant over OpenROAD, ORFS, Yosys, OpenSTA, and KLayout docs, built on Gemini, answering in prose. The authors report improvements over non-fine-tuned LLMs. [PP] — [arXiv 2410.03845](https://arxiv.org/html/2410.03845v2). A separate project, **OpenROAD-Assistant** (Llama3-8B with retrieval-aware fine-tuning, RAFT), answers in prose or OpenROAD Python — [Zenodo](https://zenodo.org/records/13119166)
- **AuDoPEDA** (UCSD 2026): a coding agent that proposes and submits OpenROAD code changes. Reported results: up to 5.9% lower routed wirelength, 10.0% lower effective clock period, and 19.4% lower power. [PP] — [arXiv 2601.06268](https://arxiv.org/pdf/2601.06268)
- **PDAgent-Bench**: 353 physical-design problems across 11 models. Models did reasonably on concepts but were weak on tool-centric execution, e.g. 42.2% on Innovus script generation. "Human-skill-enhanced" agentic workflows significantly improved end-to-end PD results. [PP] — [arXiv 2606.17253](https://arxiv.org/abs/2606.17253); [leaderboard](https://github.com/fenggev56/PDAGENT-BENCH)

**IC macro / global placement with LLMs or VLMs**
- **VeoPlace** (Google DeepMind; Uchendu & Goel): a frozen Gemini 2.5 Flash VLM acts as a high-level planner and proposes **bounding-box regions** per macro. A specialized low-level placer then places within those regions. The VLM is prompted with a history of prior attempts given as **both text coordinates and canvas images plus metrics**, and is used evolutionarily over generations with no fine-tuning. arXiv v2 reports beating ChiPFormer on 9 of 10 benchmarks, with peak wirelength reductions >32% on ISPD2005/ICCAD2004/Ariane, and DREAMPlace gains on all 8 ICCAD2015 Superblue designs (up to 4.3%). The earlier OpenReview version reported SOTA on 4 of 7. [PP; OpenReview submission] — [arXiv 2603.28733v2](https://arxiv.org/html/2603.28733v2); [OpenReview](https://openreview.net/forum?id=IiU0SeoZHg); [Kempner](https://kempnerinstitute.harvard.edu/news/rethinking-chip-design-with-ai-that-can-see/)
- **EvoPlace** (Yao et al.): an LLM evolves the *optimization algorithm code* (initialization, preconditioning, optimizer updates) inside analytical global placement (DREAMPlace) under HPWL feedback. Reported HPWL gains: 5.05% (MMS), 5.29% (ISPD2005), 8.30% (ISPD2019) on average, up to 17%. [PR, IEEE TCAD 2026] — [IEEE](https://ieeexplore.ieee.org/document/11345590/); [code](https://github.com/yaoxufeng/EvoPlace)
- **CoEvoP&R** (Chen, Xiao, Karri, Han; 2026): an LLM evolves **readable differentiable placement objectives** embedded in DREAMPlace, scored with a timing proxy and an *actual router*, and archived with feedback. On 8 ChiP-Bench Nangate45 designs × 3 seeds it reports −16.9% routed wirelength, −36.7% congestion, and +0.70 ns WNS versus native DREAMPlace. On 8 Superblue designs it reports −5.4% routed wirelength and −23.2% congestion. It logs full prompt/response/metric lineage. [PP] — [arXiv 2607.17398](https://arxiv.org/abs/2607.17398); [code](https://github.com/FCHXWH823/CoEvoP-R)
- **OrderPlace** ("Order Matters"): an LLM evolves code-level **macro placement ordering** strategies, filtered by a cheap deterministic greedy-probe proxy. On ISPD2005 it reports 34.04% lower wirelength than WireMask-EA and 14.08% lower than EGPlace. [PR, ICML 2026 poster] — [arXiv 2606.08904](https://arxiv.org/pdf/2606.08904); [ICML](https://icml.cc/virtual/2026/poster/62576)
- **MAGE** (Kahng et al.): a multimodal multi-agent macro-placement refinement framework with a six-phase workflow. Expert knowledge is supplied as natural-language directives and validation criteria, and a tournament mode compares candidates. Across 9 designs (NanGate45, GF12) it claims geometric-mean WNS gains of 11.1–19.3% and TNS gains of 70–74% versus commercial macro placers. Pith's review notes **+29.7% routed wirelength and about 4% higher power**, single-run results, and ablations on only 2 designs. [PP] — [arXiv 2607.18536](https://arxiv.org/abs/2607.18536); [Pith review](https://pith.science/paper/2607.18536)
- **PlaceReasoner-Beta** (Li, Wang, …, D. Z. Pan, T. Lan): a verifier-guided multi-agent VLM. A planner proposes, a **geometric checker** enforces physical constraints, a PD checker reviews intermediate implementation feedback, and a post-route optimizer uses final PPA/DRC. It reports the best timing and routability across 16 tasks, with the caveat that the floorplan is fixed. [PP] — [arXiv 2609.21263](https://arxiv.org/abs/2609.21263); [Pith](https://pith.science/paper/2609.21263)
- **MacroAgent** (LLM-agent-designed contour algorithms for regularity-aware macro legalization) and **VPR-Evolve** (multi-agent algorithm evolution for FPGA P&R) exist, but only their titles were retrieved. [PP] — [MacroAgent](https://arxiv.org/pdf/2608.24946); [VPR-Evolve](https://arxiv.org/pdf/2607.24998)

**Analog IC layout**
- **LayoutCopilot** (Peking Univ.; Liu, Huang et al.): a multi-agent LLM framework for interactive analog layout. An *Abstract Request Processor* turns high-level intents into concrete requests that match the tool manual, and a *Concrete Request Processor* emits executable layout-tool scripts. MAGICAL produces an initial unconstrained placement, and the agents then propose symmetry constraints on identified device pairs, e.g. differential pairs. Abstract suggestions are executed only **after the designer accepts them**. No headline numbers were found. [PR, IEEE TCAD] — [arXiv 2406.18873v2](https://arxiv.org/abs/2406.18873v2); [v3 HTML](https://arxiv.org/html/2406.18873v3); review summary in [ACM TODAES "Future or Mirage?"](https://dl.acm.org/doi/10.1145/3736167)
- **Simulation-Aware In-Context Policy Improvement (ICPI)** (Liu, Wei, Gao, D. Z. Pan): wraps an analog layout generator (MAGICAL-style) and tunes its exposed parameters (net weights, placement bias, symmetry constraints, routing priorities, wire widths) in an **act–observe–reflect loop with a "design journal"**, without weight updates. With tens of post-layout simulations it beats built-in heuristics and BO. On OTA1 it reports FoM 1.104, versus 1.003 without ICPI and 0.979 for BO. Pith flags n=1 runs and an under-specified BO baseline. The authors note that scaling is hard because state representation grows and simulation is costly. [PR, to appear ICLAD 2026] — [arXiv 2608.13767](https://arxiv.org/abs/2608.13767); [Pith](https://pith.science/paper/2608.13767)
- **LLANA**: uses LLM few-shot learning to generate design-dependent layout parameter constraints (e.g. net weights) that speed up Bayesian optimization of analog layout. [PP] — [arXiv 2406.05250](https://arxiv.org/pdf/2406.05250)
- **ACDC** ("LLMs for Analog Circuit Design Continuum"): fine-tunes Mistral-7B and GPT-oss-20B to place transistors sequentially on a grid under symmetry, non-overlap, and area objectives, using masked-layout prediction. A secondary digest says the authors later moved from grid to **continuous coordinates**. No accuracy numbers were retrieved. [PP] — [arXiv 2512.09199](https://arxiv.org/pdf/2512.09199)

**PCB-specific**
- **PCBAgent** (ASP-DAC 2025; Jianye Hao, Bei Yu et al.): an **RL agent** (decision-transformer style, building on ChiPFormer) handles layout inference and fine-tuning. An **LLM agent** translates user requests into optimization commands for interactive optimization. The LLM never updates the placement policy. The authors report that it outperforms SOTA on 17 industrial high-density tasks, with baselines including MaskPlace, ChiPFormer, and a MILP post-optimizer. [PR] — [ACM DL](https://dl.acm.org/doi/10.1145/3658617.3697736); [author PDF](https://www.cse.cuhk.edu.hk/~byu/papers/C247-ASPDAC2025-PCBAgent.pdf); description in [arXiv 2606.19795](https://arxiv.org/pdf/2606.19795)
- The handoff survey also describes a placement approach by "Li et al." that uses **multimodal serialization, topology-enriched retrieval, two grouping agents, group-aware global placement, and constraint-graph/MILP legalization**. The exact paper and whether it targets PCB or IC were not identified. [PP survey] — [arXiv 2606.19795](https://arxiv.org/pdf/2606.19795)
- **PCBWorld** (LG AI Research; Song et al., 2026): an open-source routing environment built on **KiCad's push-and-shove router**, with DRC feedback, three dataset families (two synthetic generators plus 679 real open-source boards), and PCBWorld-Bench, which scores with KiCad's own outputs. It compares rule-based routers (Freerouting, OrthoRoute, KiCadRoutingTools), RL agents (PPO, GRPO, A2C, Sable), and LLM agents (GPT-5.4 family, Qwen3.5-397B). The LLM agent gets **one API call per step, with board state, legal actions (7 actions), and reward fed back each turn**. [PP + WS, KDD 2026 agentic-eval workshop] — [arXiv 2607.05915](https://arxiv.org/abs/2607.05915); [workshop PDF](https://kdd-eval-workshop.github.io/agenticai-evaluation-kdd2026/assets/papers/42_PCBWorld_A_Benchmark_Enviro.pdf); [GitHub](https://github.com/LGAI-Research/PCBWorld). Full numbers are in Section 7.
- **PCB-Bench** (ICLR 2026; Jindong Li, Lianrong Chen et al.): about 3,700 expert-annotated text items, about 500 image+text problems, and 174 complete OSHWHub (JLCPCB) projects. It finds "substantial gaps in current models' ability to reason over spatial placements, follow domain-specific constraints, and interpret professional engineering artifacts". PCBWorld notes that PCB-Bench tests board interpretation, not routing ability. [PR] — [ICLR proceedings](https://proceedings.iclr.cc/paper_files/paper/2026/hash/051f3997af1dd65da8e14397b6a72f8e-Abstract-Conference.html); [GitHub](https://github.com/digailab/PCB-Bench); [PCBWorld HTML](https://arxiv.org/html/2607.05915v2)
- **OmniLayout** (Microsoft Research et al., July 2026): 1,681 industrial schematic-coupled PCB layouts and 77.24K IC-placement instances. Its four tasks are geometric placement, routability-aware placement, electrical/schematic-relation preservation, and tool-augmented agentic reasoning. It evaluates Claude-Sonnet-4.6, GPT-5.5, and Qwen3.6-35B-A3B against experienced human layout engineers. Results show weak geometric reasoning, poor routability, and incomplete preservation of schematic relationships. Per Pith, models produced **overlapping components, underused the back side, and had poor post-route wirelength and completion across zero-shot, few-shot, and agentic settings**. [PP] — [arXiv 2607.03261](https://arxiv.org/abs/2607.03261); [MSR page](https://www.microsoft.com/en-us/research/publication/omnilayout-a-schematic-coupled-multimodal-benchmark-for-constraint-aware-geometric-reasoning-in-pcb-layout/); [Pith](https://pith.science/paper/2607.03261)
- **OmniRouting**, a companion "semantic-coupled multimodal benchmark for constraint-aware spatial reasoning in PCB routing", exists, but its content was not retrieved. [PP] — [arXiv 2608.04434](https://arxiv.org/html/2608.04434v1)
- **PCBInnoBench** (NeurIPS 2026 poster): 372 expert-designed KiCad editing tasks from real projects, graded with hidden structural, task-specific, and cross-artifact checks. The best agent reached **22.0% Pass@1 when given an expert's editing trajectory and 7.3% with the objective only**. [PR] — [NeurIPS](https://neurips.cc/virtual/2026/poster/139034)
- **PCB-QA**: 480 QA pairs from early-stage KiCad files covering connections, datasheet details, and SPICE behaviour, evaluated over text serializations such as JSON netlists and SPICE. Scores were not retrieved. [PP] — [arXiv 2606.23704](https://arxiv.org/pdf/2606.23704)
- Schematic-side PCB LLM work: **PCBSchemaGen** (training-free LLM code synthesis with a datasheet-derived knowledge graph and a deterministic 5-layer verifier with pin-level error localization) [PP] — [arXiv 2602.00510](https://arxiv.org/abs/2602.00510); **pcbGPT** (natural language to KiCad schematic via datasheet retrieval; explicitly stops before placement and routing) [PP] — [arXiv 2606.01188](https://arxiv.org/html/2606.01188v1); **HWE-Bench** (board-level schematic design) [PP] — [arXiv 2603.18102](https://arxiv.org/pdf/2603.18102); **MMCircuitEval** (3,614 multimodal circuit QA pairs, with the largest gaps in back-end design) [PP] — [arXiv 2507.19525](https://arxiv.org/html/2507.19525v1)
- **GPT-6 Astra KiCad demo** (OpenAI, Sept 4, 2026): a short clip of the model placing and routing in KiCad. Quilter calls it a real step for LLMs operating CAD, but says it is a condensed clip with no PCB-specific benchmark. [V] — [Quilter](https://www.quilter.ai/blog/llm-pcb-layout-gpt-6-astra). JLCPCB's reproduction turned a four-line brief into a 44×34 mm, 2-layer board. The model **first defined and protected the power, bootstrap, and switching connections, then ran local Freerouting for the remaining low-current nets**. KiCad reported **46 schematic-parity issues**. [V] — [JLCPCB KiCad review](https://jlcpcb.com/blog/gpt-6-astra-pcb-design-in-kicad). NextPCB found the workflow was DSN export → Freerouting → SES import, i.e. an existing autorouter did the routing. [V] — [NextPCB](https://www.nextpcb.com/blog/gpt-6-astra-kicad-pcb-routing-test). zerowithdot reported 168 DRC violations on the AI board versus 0 on the human board. [C] — [zerowithdot](https://zerowithdot.com/blog/gpt-6-astra-impact-on-cad/). A single LinkedIn post claims that with the autorouter off, Astra routed only three trace segments in an hour (unverified). [C] — [LinkedIn](https://at.linkedin.com/in/gregor-markus-christandl). A vendor claims 97% first-pass fab yield on 40 boards behind its own verification gate; this is unverified. [V] — [Cherry Blossom](https://www.trycherryblossom.com/blog/gpt-6-astra-pcb-design)
- **EEBench** (run by atopile): argues that agents do much better editing a **declarative circuit-as-code** representation than "drawing lines in a GUI". V1 grades simulated circuit design (13 tasks) and **excludes layout**. Claude Opus 5 led at 61.6% as of September 2026, and a reported 69.3% for GPT-6 Astra is disputed. The vendor conflict of interest is disclosed. [V] — [EEBench blog](https://eebench.org/blog/can-ai-design-circuit-boards-yet/); [methodology](https://eebench.org/methodology.html); [Hackaday](https://hackaday.com/2026/09/05/can-ai-now-design-pcbs-that-just-work/); [zerowithdot](https://zerowithdot.com/blog/gpt-6-astra-impact-on-cad/)
- **Quilter's position**: its engine is "not an LLM". It is RL plus classical solvers plus computational geometry, generating many candidates checked by physics rules. A neural model proposes moves and a deterministic engine validates them. Values such as differential-pair spacing should be **computed from stackup and impedance targets, not guessed by a network**. [V] — [Quilter blog](https://www.quilter.ai/blog/llm-pcb-layout-gpt-6-astra); [Quilter autorouter post](https://www.quilter.ai/blog/pcb-autorouter-was-the-right-idea); [Quilter about](https://www.quilter.ai/about). A competitor claims Quilter lacks circuit-aware checks such as bypass-cap loop and switching-converter layout checks [V, competitor] — [Protoflow](https://www.protoflow.ai/blog/ai-pcb-design-2026-guide)
- **KiCad MCP ecosystem**: several open-source MCP servers expose KiCad to LLMs, including Gato513/kicad-mcp (32 tools: placement, copper, Freerouting autoroute, ERC/DRC, export), Konnect (a single Rust binary on the KiCad 10 IPC API; 217 tools per its repo, 228 per a third party), and KiCAD-MCP-Server (Freerouting plus JLCPCB part search). In nearly all of them **routing is delegated to Freerouting or KiCad engines**. One overview says "the routing quality is KiCad's, not the model's". kicad-mcp-pro's author deliberately treats placement and routing as experimental and focuses on validation, DFM, and release gating. [C] — [Gato513/kicad-mcp](https://github.com/Gato513/kicad-mcp); [Konnect](https://github.com/mixelpixx/Konnect); [kicad-mcp-pro](https://github.com/oaslananka/kicad-mcp-pro); [KiCAD-MCP-Server](https://ubos.tech/mcp/kicad-mcp-server/); [pcbeditor overview](https://pcbeditor.com/kicad-ai); [KiCad forum MCP post](https://forum.kicad.info/t/i-built-an-open-source-mcp-server-for-ai-assisted-kicad-workflows/68678)
- **kicad-tools** (rjwalters) is benchmarking its own `kct route` on PCBWorld D3-A/B against the published Freerouting and KiCadRoutingTools figures. [C] — [issue #5942](https://github.com/rjwalters/kicad-tools/issues/5942); [PR #6702](https://github.com/rjwalters/kicad-tools/pull/6702)

### Inferences
- The successful IC systems share one shape: **the LLM edits a low-dimensional, semantically meaningful control surface**. Examples are bounding regions (VeoPlace), objective terms (CoEvoP&R), algorithm code (EvoPlace), ordering rules (OrderPlace), and generator parameters (ICPI, LLANA). A trusted numerical engine then turns those decisions into exact geometry. None of the reported wins come from the LLM emitting final coordinates or traces.
- PCB work is about 1–2 years behind IC work in LLM integration. IC placement already has LLM-in-the-loop systems that beat SOTA baselines. For PCB, the strongest LLM-involved placer (PCBAgent) puts the LLM in a thin command-translation role around an RL engine, and the newest PCB results are mostly negative benchmarks.
- The GPT-6 Astra workflow ("protect critical nets manually, autoroute the rest") is essentially the human expert workflow. It is a reasonable template, but the evidence (parity errors, DRC counts) shows that verification gates are mandatory.

### Gaps
- Full-text quantitative tables (PCB-Bench per-model scores, OmniLayout per-model numbers, PCB-QA scores, LayoutCopilot metrics, ChatEDA PPA numbers) were not retrievable because arXiv fetches were blocked.
- No source was found for "LLM4Placement" as a named system, nor for "LLM-generated routing scripts" for PCB beyond MCP/tool calls. AlphaRoute ([arXiv 2607.19768](https://arxiv.org/pdf/2607.19768)) cites VLSI global-routing work, but its method was not retrieved.
- No search found an LLM generating placement constraints directly for **ALIGN**. The closest are LayoutCopilot and ICPI, which use MAGICAL-style generators.
- The identity of the "Li et al." multimodal-serialization + MILP-legalization placement paper was not resolved.
- DeepPCB (RL-based cloud placement/routing) appeared in results, but no technical details were retrieved — [DeepPCB](https://deeppcb.ai/2025/04/15/ai-powered-pcb-placement-by-deeppcb/).

---

## 2. LLM spatial reasoning: capabilities, limits, failure modes, and which representations help

### Takeaway
Text-only LLMs show consistent failures on 2D layout reasoning: coordinate and alignment drift, overlap and boundary violations, lost state over multi-step edits, and errors when combining areas. Vision does **not** reliably fix this. VLMs often underperform their own LLM backbones on spatial tasks, and redundant text plus image helps most. Structured, code-like representations such as CSS-style boxes or JSON help. Tool use fixes arithmetic but not optimization. Layout-specific benchmarks (PCB-Bench, OmniLayout) confirm these weaknesses on real boards.

### Cited Findings
- **TopoBench** (hard grid/topology puzzles): frontier models solved fewer than a quarter of hard instances. Failure modes include repeated move loops, **state-tracking failures where the model's claimed board diverges from its own actions**, and constraint violations. The authors attribute part of this to flattening 2D grids into token sequences, which makes row/column alignment hard. [PP] — [arXiv 2603.12133](https://arxiv.org/html/2603.12133)
- **GridRoute** (LLM route planning on grids): failures include invalid non-unit steps, paths through obstacles, out-of-bounds paths, and wrong endpoints. [PP] — [arXiv 2505.24306](https://arxiv.org/pdf/2505.24306)
- **PlanarBench** (planar graph drawing in ASCII): the most common error is **missing edges, especially at high-degree nodes**. Edge count predicts difficulty better than vertex count. Some errors come from the ASCII medium itself. [PP] — [arXiv 2606.02010](https://arxiv.org/html/2606.02010)
- **Grid Spatial Understanding (GSU)**: models handle basic grid concepts but struggle with frames of reference and with identifying shapes from **coordinate lists**. [PP] — [arXiv 2603.17333](https://arxiv.org/html/2603.17333v1)
- A mechanistic probing study found near-chance orientation tracking, with errors biased toward frequent compass words. The authors read this as reliance on linguistic priors rather than geometric state. [PP] — [arXiv 2603.26323](https://arxiv.org/pdf/2603.26323)
- **FloorplanQA** (2,000 structured JSON/XML 2D layouts, 16,000 questions): models fail to respect physical constraints and overlaps. A common error was **summing object areas and ignoring overlaps**. Giving models a **Python interpreter improved arithmetic but made the "Max Box" optimization results worse**. [PR, ICML 2026] — [arXiv 2507.07644](https://arxiv.org/html/2507.07644v3); [ICML poster](https://icml.cc/virtual/2026/poster/62946); [Lacuna summary](https://lacuna.tiptreesystems.com/work/floorplanqa-a-benchmark-for-spatial-reasoning-in-llms-using-structured/wrk_82594f0d17bb048f48ab07aecaa3ec8b)
- **SpatialEval** ("Is a Picture Worth a Thousand Words?"): VLMs often **under-perform their LLM counterparts** on spatial tasks (relations, navigation, counting) despite visual input. They rely less on the image when text is sufficient, and vision-only rarely beats the LLM backbone. **Redundant vision plus text significantly improves performance**. [PR, NeurIPS 2024] — [NeurIPS poster](https://neurips.cc/virtual/2024/poster/94371); [paper PDF](https://proceedings.neurips.cc/paper_files/paper/2024/file/89cc5e613d34f90de90c21e996e60b30-Paper-Conference.pdf)
- **LayoutGPT**: formatting layouts as **CSS-like (left, top, width, height)** with in-context exemplars and normalization (values rescaled to ≤256) helps LLMs interpret the spatial meaning of numbers. The authors argue that plain number sequences are hard to interpret. It outperformed text-to-image systems by 20–40% on numerical/spatial correctness and matched human users. [PR, NeurIPS 2023] — [arXiv 2305.15393](https://arxiv.org/pdf/2305.15393); [supplement](https://papers.neurips.cc/paper_files/paper/2023/file/3a7f9e485845dac27423375c934cb4db-Supplemental-Conference.pdf)
- **PCB-Bench (domain-specific)**: models may know routing *theory* but fail to locate a physical wiring error in an image. Secondary summaries report Gemini-2.5-Pro at 100% and GPT-5 at 90.9% on Basic Wiring Error Identification, while open-source models drop to 45–55% on that fine-grained visual task. A Claude-Opus-4.1 figure of 93.3% placement multiple-choice accuracy is unconfirmed. [PR; numbers from secondary summaries] — [papernotes](https://en.papernotes.org/ICLR2026/llm_evaluation/pcb-bench_benchmarking_llms_for_printed_circuit_board_placement_and_routing/); [Liner review](https://liner.com/review/pcbbench-benchmarking-llms-for-printed-circuit-board-placement-and-routing); [ICLR](https://proceedings.iclr.cc/paper_files/paper/2026/hash/051f3997af1dd65da8e14397b6a72f8e-Abstract-Conference.html)
- **OmniLayout (domain-specific)**: frontier models produce overlapping components, underuse the board's back side, and give poor post-route wirelength and completion, **even in agentic/tool-augmented settings**. [PP] — [Pith](https://pith.science/paper/2607.03261); [arXiv 2607.03261](https://arxiv.org/abs/2607.03261)
- Footprint geometry: inconsistencies between EDA files and datasheet diagrams prevent LLMs from accurately inferring geometric details from visual information alone (ICGeo8K). [PP] — [arXiv 2508.03725](https://arxiv.org/html/2508.03725v1)
- ACDC moved from grid-based to continuous-coordinate representations for LLM transistor placement (per a secondary digest). [PP] — [arXiv 2512.09199](https://arxiv.org/pdf/2512.09199)
- MAGE splits checking by modality. **Scripts enforce hard constraints** (overlap, boundary, channel spacing), while **vision judges soft qualities** (stacking regularity, pin accessibility, whitespace organization). [PP] — [arXiv 2607.18536](https://arxiv.org/abs/2607.18536)

### Inferences
- Do not ask an LLM to do coordinate arithmetic, overlap detection, or counting. Precompute these as **derived facts** (distances, overlaps, neighbor lists, crossing counts) and hand them over as text.
- The best representation is likely **multi-channel**: structured JSON/CSS-like boxes for exact data, plus relational/semantic summaries ("C5 is 1.2 mm from U1.VIN on the top side"), plus a rendered image with overlays for gestalt judgments. SpatialEval's redundancy result and the VeoPlace and MAGE designs all point this way.
- ASCII grids are risky at board scale. Alignment breaks over long token sequences (TopoBench) and the medium itself causes errors (PlanarBench). They may still work for small local views, e.g. a 20×20 neighborhood of a congested area.
- Relative constraints are the representation that best matches LLM strengths (language and priors) while leaving metric satisfaction to solvers. The direct evidence is LayoutCopilot's symmetry constraints, ICPI's generator parameters, and VeoPlace's regions.

### Gaps
- No head-to-head study was found that compares ASCII grid, coordinate list, scene graph, SVG, and image representations **on PCB placement specifically**. OmniLayout or PCB-Bench may contain such ablations in their full text, which was not retrievable.
- Holodeck-style "LLM emits spatial relations → constraint solver" and LayoutVLM-style "VLM emits relations → differentiable optimization" from 3D scene layout are relevant precedents. **These were not verified in this session** because the search budget ran out. From background knowledge they are Holodeck (arXiv 2312.09067) and LayoutVLM (arXiv 2412.02193); treat these IDs as unverified.
- No quantitative results were found on SVG as an LLM layout representation.

---

## 3. Agent architectures: planner + solver, LLM→constraints/MILP, LLM-guided search, self-critique with DRC, multi-agent, RAG, evolutionary LLM-in-the-loop

### Takeaway
Five architectures have evidence behind them:
- **LLM as high-level planner over a numerical solver**: VeoPlace, PCBAgent, LayoutCopilot.
- **LLM as evolver of solver code, objectives, or orderings** (FunSearch/EoH/ReEvo style): EvoPlace, CoEvoP&R, OrderPlace, AlphaEvolve. These give the most robust *quantified* gains.
- **Interactive tool-use agents with engine feedback**: PCBWorld, PDAgent-Bench. These clearly beat open-loop LLM generation but remain below classical routers and are about 200× slower.
- **Verifier-gated multi-agent loops**: MAGE, PlaceReasoner-Beta, DRC-Aid, EvoDRC.
- **Retrieval/knowledge-grounded orchestration**: ORAssistant, PCBSchemaGen's knowledge graph.

Open-ended self-correction loops need explicit bounds and edit menus to converge.

### Cited Findings
- **Interactive beats open-loop.** In PCBWorld on D3-A, GPT-5.4 interactive reached Clean Pass 0.65, versus 0.19 for plan-then-execute and 0.02 for engine-free geometry generation. [PP] — [arXiv 2607.05915v2](https://arxiv.org/html/2607.05915v2); summary via [alphaXiv](https://www.alphaxiv.org/fr/abs/2607.05915)
- **Interactive LLMs are slow.** GPT-5.4 took 94.04 s versus 0.43 s for routers and PPO on D2, because every action needs a full model inference. [PP] — [arXiv 2607.05915v2](https://arxiv.org/html/2607.05915v2)
- **Planner/executor split with images and history.** VeoPlace's VLM sees text coordinates plus canvas images plus metrics of prior attempts, proposes regions, and lets a placer execute. [PP] — [arXiv 2603.28733v2](https://arxiv.org/html/2603.28733v2)
- **LLM as translator to optimizer commands.** In PCBAgent the LLM converts user requests into optimization commands for an RL placer. [PR] — [ACM DL](https://dl.acm.org/doi/10.1145/3658617.3697736)
- **Two-stage intent → concrete command agents.** LayoutCopilot uses specialized agents to limit prompt dilution, e.g. a classifier that labels requests abstract or concrete (detail from an AI-written review, treat with caution). [PR] — [arXiv 2406.18873](https://arxiv.org/html/2406.18873v3); [Moonlight review](https://themoonlight.io/review/layoutcopilot-an-llm-powered-multi-agent-collaborative-framework-for-interactive-analog-layout-design)
- **LLM-evolved objectives with real router feedback.** CoEvoP&R gives the LLM the allowed objective interface, baseline context, an archive of prior candidates, and placement/timing/router feedback. It outputs readable differentiable objectives. [PP] — [arXiv 2607.17398](https://arxiv.org/abs/2607.17398)
- **LLM-evolved algorithms and orderings.** See EvoPlace ([IEEE TCAD](https://ieeexplore.ieee.org/document/11345590/)) and OrderPlace with its cheap **proxy filter** for expensive evaluations ([arXiv 2606.08904](https://arxiv.org/pdf/2606.08904)).
- **AlphaEvolve in hardware**: Google's Gemini-based evolutionary coding agent proposed a Verilog rewrite that removed unnecessary bits from an arithmetic circuit for matrix multiplication in an upcoming TPU, which Google's hardware team validated. Separately it reported a 23% speedup on a Gemini matmul kernel (about 1% lower training time) and up to 32.5% on FlashAttention. These come from secondary sources and are not layout results. [V/press] — [TechRepublic](https://www.techrepublic.com/article/news-google-deepmind-alphaevolve-coding-ai/); [Mexico Business News](https://mexicobusiness.news/cloudanddata/news/deepmind-unveils-alphaevolve-ai-agent-algorithm-design)
- **Background on LLM heuristic-evolution methods**: FunSearch is multi-island evolution with a single prompt strategy; ReEvo adds short- and long-term reflection; EoH co-evolves "thoughts" and code. Comparisons on routing problems (TSP/CVRP, not VLSI) show no consistent winner, e.g. ReEvo ahead at CVRP20 and EoH ahead at CVRP50/100. RouteRepair adds instance-level failure diagnosis and repair to LLM heuristic design. [PP/PR mix] — [ReEvo arXiv 2402.01145](https://arxiv.org/pdf/2402.01145); [EoH-S AAAI](https://ojs.aaai.org/index.php/AAAI/article/view/41038/44999); [RouteRepair arXiv 2609.11452](https://arxiv.org/pdf/2609.11452); [LLM-HCJG arXiv 2609.02353](https://arxiv.org/html/2609.02353v1)
- **LLM to MILP formulation.** OptiMUS formulates and solves MILPs from natural language, writing and debugging solver code and validating solutions. It reports solving 67% more problems than basic prompting in v1, "nearly twice as many" in a later version, and more than 80% of benchmark problems per a co-author's talk. It is general OR, not layout. [PP] — [arXiv 2310.06116](https://arxiv.org/abs/2310.06116v1); [PapersWithCode](https://physics.paperswithcode.com/paper/optimus-optimization-modeling-using-mip)
- **Verifier-gated DRC repair.** DRC-Aid has a rule engine **convert Calibre violations into a menu of candidate edits**. The LLM picks one, the toolkit applies it and re-runs Calibre, in an Observe → Reason → Execute → Validate loop. [PP] — [arXiv 2607.22761](https://arxiv.org/html/2607.22761v1). EvoDRC partitions the layout into bounded repair regions, each with an LLM agent plus local DRC, connectivity, and impact-preview tools, and grows a skill database. A secondary summary reports a 73.5% DRV reduction on 7 blocks. [PP] — [arXiv 2607.20019](https://arxiv.org/abs/2607.20019); [Pith](https://pith.science/paper/2607.20019). SCALE uses a fine-tuned VLM to propose top-k fixes that a coding agent applies with DRC/LVS. [PP] — [arXiv 2607.21850](https://arxiv.org/pdf/2607.21850)
- **Self-correction instability.** A 2026 multi-agent test-repair study found that the self-correction–executor loop "acts as a central source of instability, introducing non-convergence risk without explicit bounds". [PP] — [arXiv 2605.01471](https://arxiv.org/html/2605.01471v1)
- **Multi-agent with independent audit.** MAGE requires each sub-agent to render, run checks, inspect the image, and write a structured report before revising or accepting. A **stateless independent auditor** then does a separate visual audit, and a tournament mode propagates feedback from winners. [PP] — [arXiv 2607.18536](https://arxiv.org/abs/2607.18536); [Pith](https://pith.science/paper/2607.18536)
- **Verifier roles split by abstraction level.** PlaceReasoner-Beta uses a planner, a geometric checker, a PD checker, and a post-route PPA/DRC optimizer. [PP] — [arXiv 2609.21263](https://arxiv.org/abs/2609.21263)
- **Human skills injected into workflows** improve end-to-end PD results significantly (PDAgent-Bench). Expert trajectories triple KiCad-editing pass rates (PCBInnoBench: 22.0% versus 7.3%). [PP/PR] — [arXiv 2606.17253](https://arxiv.org/abs/2606.17253); [NeurIPS](https://neurips.cc/virtual/2026/poster/139034)
- **Retrieval over topology.** PCBSchemaGen's ablation suggests that circuit retrieval needs **topology-aware metrics rather than purely semantic embeddings**. [PP] — [arXiv 2602.00510](https://arxiv.org/html/2602.00510v2)
- **In-context policy improvement with a design journal** (ICPI): memory of act/observe/reflect records replaces fine-tuning. [PR, ICLAD 2026] — [arXiv 2608.13767](https://arxiv.org/abs/2608.13767)
- **Code/DSL interfaces beat GUI manipulation** for agents (EEBench/atopile experience). [V] — [EEBench blog](https://eebench.org/blog/can-ai-design-circuit-boards-yet/)

### Inferences
- Use the LLM where decisions are *few, semantic, and high-leverage*: what groups go where, which nets are critical, what the objective weights are, which constraint to relax. Use solvers where decisions are *many, metric, and combinatorial*: exact positions, legalization, maze or push-and-shove routing.
- Offline LLM evolution of heuristics or objectives across a corpus (CoEvoP&R/EvoPlace style) is the most cost-effective path. The LLM's cost is paid once, and run time stays classical-fast. That avoids PCBWorld's roughly 200× latency problem.
- Repair loops should present the LLM with **enumerated legal edits** (DRC-Aid) rather than free-form geometry, and should have iteration and budget caps.
- An independent, stateless auditor (MAGE) is a cheap defense against an agent rationalizing its own output.

### Gaps
- No published work was found that applies OptiMUS-style **LLM→MILP/SMT/CP-SAT formulation to PCB or IC placement constraints** specifically. PCBAgent and NS-Place use MILP but not LLM-written formulations.
- No published OPRO-style "LLM as optimizer over placements" result for PCB was found.
- No direct VLSI-routing application of FunSearch/EoH/ReEvo was found beyond VPR-Evolve (title only) and the placement works above.

---

## 4. Datasheet / application-note understanding for layout recommendations

### Takeaway
**No published system was found that automatically extracts *layout* recommendations from datasheets**, e.g. "place input cap within 2 mm of VIN" or "minimize the SW node loop". The closest work extracts **pin roles and electrical constraints into a per-IC knowledge graph** for schematic synthesis (PCBSchemaGen), retrieves datasheet information for schematic generation (pcbGPT), or aligns footprint diagrams (ICGeo8K). This is an open opportunity for the project.

### Cited Findings
- **PCBSchemaGen** builds a per-IC knowledge graph from the datasheet PDF in three stages: (1) **layout-aware PDF parsing** of pin tables and application-circuit text; (2) **low-temperature LLM pin-role assignment** from a closed 32-role ontology; (3) **instantiation of four types of constraint predicates** against the labeled pins. This shrinks per-IC context from about 16k tokens (a typical datasheet) to about 300 tokens. The constraints are pin-level and electrical, not board-layout. [PP] — [arXiv 2602.00510v2](https://arxiv.org/html/2602.00510v2)
- **pcbGPT** retrieves datasheet and reference-circuit information to generate KiCad schematics, explicitly scoped to the early design stage before placement and routing. [PP] — [arXiv 2606.01188](https://arxiv.org/html/2606.01188v1)
- **ICGeo8K** uses LLMs to locate footprint diagrams in datasheets and align them with EDA pin data. It notes that EDA/datasheet inconsistencies defeat vision-only inference. [PP] — [arXiv 2508.03725](https://arxiv.org/html/2508.03725v1)
- A **datasheet-aware hardware compatibility verification** knowledge graph preserves each property's operating conditions, modes, and device variants, and deduplicates properties repeated in a datasheet. It targets pre-schematic compatibility, not layout. [PP] — [arXiv 2608.25217](https://arxiv.org/pdf/2608.25217)
- JITX's practitioner report: Gemini's very large context window was very helpful for pulling component data out of datasheets, and they recommend cross-referencing extractions to improve accuracy. [V] — [JITX blog](https://blog.jitx.com/jitx-corporate-blog/testing-generative-ai-for-circuit-board-design)
- PCB-QA includes datasheet-detail questions over KiCad projects; scores were not retrieved. [PP] — [arXiv 2606.23704](https://arxiv.org/pdf/2606.23704)
- Layout rules are **conditional**, which an extractor must capture. Per published decoupling guides: one local capacitor per power pin unless the datasheet says pins share an internal plane; close placement can be impossible for wide-pitch packages or BGAs, where plane pairs dominate; and capacitor effectiveness depends on frequency band (a 100 nF 0402 has an SRF of about 50–80 MHz and is inductive above that). [V] — [NextPCB decoupling](https://www.nextpcb.com/blog/decoupling-capacitor-placement-pcb); [JLCPCB decoupling](https://jlcpcb.com/blog/decoupling-capacitors-guide); [Sierra Circuits](https://www.protoexpress.com/blog/decoupling-capacitor-placement-guidelines-pcb-design/)
- A generic KG survey notes that LLMs given reference documents plus a knowledge graph can produce candidate rules informed by document text. This is not PCB-specific. [PR] — [LLMs and KGs survey](https://d-nb.info/1378253507/34)

### Inferences
- The PCBSchemaGen pipeline (layout-aware parsing → closed ontology → predicate templates → compact knowledge graph) transfers directly. A **layout predicate ontology** would include `near(part, pin, d_max)`, `min_loop(nets[])`, `same_side(a, b)`, `kelvin(sense_net, pad)`, `keepout(region, layers)`, `thermal_vias(pad, n)`, `plane_under(region, net)`, `orient(part, toward=pin)`, `no_route_under(part, layers)`, and `width_for_current(net, I)`. Each instance should store page/figure provenance and validity conditions (package, frequency, current).
- Extraction should be verified twice: by a second LLM pass or cross-reference (JITX), and by checking the extracted predicates are executable against the board.

### Gaps
- No benchmark or dataset of datasheet layout-guideline extractions was found.
- No work was found on parsing **reference-layout figures** (e.g. the EVM layout images in TI/ADI datasheets) into constraints.
- No work was found on app-note retrieval (RAG over reference layouts) for PCB placement. ORAssistant-style RAG is limited to tool documentation.

---

## 5. Explainability and design-intent capture ("the why")

### Takeaway
Explicit rationale capture is recognized as a **gap**; no layout system logs a standardized "why" graph. The best available patterns are:
- LayoutCopilot's human-accepted *suggestions* derived from high-level intents.
- CoEvoP&R's **readable objectives with full lineage logs**.
- ICPI's **design journal**.
- MAGE's mandatory **structured reports** per iteration.
- The handoff survey's call for artifacts to carry **context, evidence, and provenance**.

### Cited Findings
- The ACM TODAES survey says understanding the reasoning behind EDA design decisions matters, that design-rationale documentation is underused, and that interactive natural-language explanations are an emerging direction. [PR] — [ACM 10.1145/3715324](https://dl.acm.org/doi/10.1145/3715324)
- An evaluation of LLMs on real engineering tasks found they **often miss design intentions or rationale** even when given functional models or full system descriptions. [PP] — [arXiv 2505.13484](https://arxiv.org/pdf/2505.13484)
- LayoutCopilot converts abstract designer intent into concrete suggestions that become executable commands **only after designer acceptance**. This is a human-in-the-loop explanation and approval pattern. [PR] — [arXiv 2406.18873](https://arxiv.org/abs/2406.18873v2); [ACM "Future or Mirage?"](https://dl.acm.org/doi/10.1145/3736167)
- CoEvoP&R stores "the resolved configuration, objective program, prompt and response records, candidate metrics, component and state traces". These are "sufficient to reconstruct candidate lineage and the evidence used by the archive". Its objectives are designed to be human-readable, in contrast to opaque learned surrogates. [PP] — [GitHub](https://github.com/FCHXWH823/CoEvoP-R); [arXiv 2607.17398](https://arxiv.org/abs/2607.17398)
- ICPI's "design journal" stores experience from act/observe/reflect cycles. [PR, ICLAD 2026] — [arXiv 2608.13767](https://arxiv.org/abs/2608.13767)
- MAGE requires a structured report (visual observations plus check results) before each revise/accept decision, and encodes expert knowledge as natural-language directives and validation criteria. [PP] — [arXiv 2607.18536](https://arxiv.org/abs/2607.18536)
- The handoff survey defines valid handoff artifacts as carrying enough context, evidence, and provenance for the next consumer. Its "Organization-Bound" systems maintain source grounding, provenance, scope, and admissibility. [PP] — [arXiv 2606.19795](https://arxiv.org/abs/2606.19795)
- In verification, one line of work captures designer intent as comment strings specifying properties to check, then feeds them to an LLM for assertion generation. This pattern could carry over to layout rules. [PR review] — [ACM "Future or Mirage?"](https://dl.acm.org/doi/10.1145/3736167)
- PCBSchemaGen's verifier gives interpretable, pin-localized violation feedback. [PP] — [arXiv 2602.00510](https://arxiv.org/abs/2602.00510)
- General design-rationale literature (capture and reconstruction methods) is available as a source of schemas. [C] — [Wikipedia: Design rationale](https://en.wikipedia.org/wiki/Design_rationale)

### Inferences
- The most trustworthy "why" is **constructive, not post-hoc**. Every placement or routing decision should trace to an explicit constraint or objective term. That term should trace to evidence (a datasheet page, an app note, a heuristic id, or a user instruction) and to a measured verification result. A post-hoc LLM narrative should be generated *from* this graph, not invented.
- The comment-as-intent pattern from verification maps well to KiCad. Intent records can live as structured fields, e.g. a sidecar JSON keyed by refdes/net, or KiCad rule areas and custom DRC rules with comments. They then double as checks.

### Gaps
- No standard schema for PCB design-intent graphs was found.
- No user study was found on whether LLM-generated layout explanations are accurate or useful to engineers.

---

## 6. Vision feedback: rendered layout images as feedback to multimodal models

### Takeaway
Vision feedback has shown value in **IC macro placement** (VeoPlace, MAGE, PlaceReasoner-Beta), **always paired with text metrics and coordinates and with scripted hard-constraint checks**. No PCB-specific system was found that feeds rendered board images back to a VLM inside a placement loop. General and PCB benchmarks warn that VLMs are weak at fine-grained visual judgment (PCB-Bench, SpatialEval). Use images for gestalt and qualitative critique, not for measurement.

### Cited Findings
- VeoPlace feeds the VLM canvas images plus text coordinates plus metrics of prior attempts. This frozen-VLM-plus-placer design gave the strongest IC placement gains among LLM-in-the-loop works: beating ChiPFormer on 9 of 10 benchmarks and improving DREAMPlace on 8 of 8 Superblue designs. [PP] — [arXiv 2603.28733v2](https://arxiv.org/html/2603.28733v2)
- MAGE renders core boundaries, group boxes, IO pins, **flylines**, and a **coverage overlay of unclaimed area**. A Pith review also mentions whitespace heatmaps and boundary-coverage maps. The VLM must report "visual-only facts", and scripts handle overlap, boundary, and spacing checks. No ablation isolating the vision contribution was found, and ablations cover only 2 designs. [PP] — [arXiv 2607.18536](https://arxiv.org/abs/2607.18536); [Pith](https://pith.science/paper/2607.18536)
- PlaceReasoner-Beta is a VLM multi-agent loop with geometric and PD checkers. [PP] — [arXiv 2609.21263](https://arxiv.org/abs/2609.21263)
- SCALE uses a fine-tuned VLM to analyze DRC violations and propose fixes; drcAgent uses a Qwen2.5-VL fixer trained against Calibre feedback (per survey description). [PP] — [arXiv 2607.21850](https://arxiv.org/pdf/2607.21850); [DRC search summary citing survey](https://arxiv.org/pdf/2606.19795)
- PCB-Bench: frontier VLMs score high on basic wiring-error identification in images (Gemini-2.5-Pro 100%, GPT-5 90.9% per secondary summaries), but open-source models drop to 45–55%. Summaries also say models "know the theory of routing but fail to identify a physical wiring error in an image". [PR; secondary] — [papernotes](https://en.papernotes.org/ICLR2026/llm_evaluation/pcb-bench_benchmarking_llms_for_printed_circuit_board_placement_and_routing/); [Liner](https://liner.com/review/pcbbench-benchmarking-llms-for-printed-circuit-board-placement-and-routing)
- SpatialEval: vision-only rarely beats the LLM backbone, while text plus image redundancy helps. [PR] — [NeurIPS 2024](https://neurips.cc/virtual/2024/poster/94371)
- UniPCB is a VLM benchmark for open-ended PCB *quality inspection* (manufactured boards, not layout). [PP] — [arXiv 2601.19222](https://arxiv.org/pdf/2601.19222)

### Inferences
- For KiCad, render purpose-built **diagnostic views** rather than photoreal 3D. Useful views: ratsnest/flylines colored by net class; group bounding boxes with labels; a congestion or crossing-density heatmap; critical-loop polygons (e.g. buck hot loop) with area annotated in text; DRC markers with ids that match a text list; and a top/bottom split.
- Always pair an image with an aligned text table that uses the same ids (SpatialEval redundancy; VeoPlace). Ask the VLM qualitative questions ("Is signal flow left to right? Are decoupling caps visually adjacent to their pins? Is there an obvious ratsnest tangle?") and verify any claimed metric with code.

### Gaps
- No PCB-specific measurement was found of how much rendered-image feedback improves placement quality over text-only feedback.
- No vision ablation numbers were found for MAGE or VeoPlace in the retrieved snippets.

---

## 7. Quantitative comparisons of LLM-driven layout versus classical tools

### Takeaway
- **IC placement:** LLM-in-the-loop methods report beating classical and learned baselines when the LLM steers a classical engine. Reported gains are roughly 4–34% HPWL or routed wirelength and 23–37% congestion, all self-reported preprints except EvoPlace (TCAD) and OrderPlace (ICML). MAGE's timing gains come with a wirelength penalty.
- **PCB routing:** classical routers (Freerouting) and even PPO RL beat LLM agents, and **LLMs score zero on large boards**.
- **PCB placement:** frontier models trail human engineers (OmniLayout).

### Cited Findings
- **PCBWorld (PCB routing, Clean Pass = CP)**:
  - Freerouting: CP 1.00 on synthetic D2, 0.80 on D3-A, 0.78 on D3-B.
  - GPT-5.4 interactive: CP 0.96 on D2 (mini 0.58, nano 0.55) and 0.65 on D3-A.
  - **All LLM agents: 0.00 CP on large D3-B**.
  - PPO: 0.86 on D3-A, 0.45 on D3-B. The paper says PPO beat everything on small boards and was second only to the strongest rule-based router on larger ones.
  - KiCadRoutingTools: 0.74 / 0.20.
  - A kicad-tools PR flags the Freerouting row as "denominator not verified".
  - [PP/WS; partly via third-party GitHub issue] — [arXiv 2607.05915](https://arxiv.org/abs/2607.05915); [kicad-tools #5942](https://github.com/rjwalters/kicad-tools/issues/5942); [kicad-tools PR #6702](https://github.com/rjwalters/kicad-tools/pull/6702)
- **OmniLayout (PCB placement)**: Claude-Sonnet-4.6, GPT-5.5, and Qwen3.6 were benchmarked against experienced human layout engineers. They showed weak geometric reasoning, poor routability, and incomplete schematic-relation preservation across zero-shot, few-shot, and agentic settings. [PP] — [arXiv 2607.03261](https://arxiv.org/abs/2607.03261)
- **PCBInnoBench (KiCad editing)**: the best agent scored 22.0% Pass@1 with expert-trajectory guidance and 7.3% without. [PR] — [NeurIPS](https://neurips.cc/virtual/2026/poster/139034)
- **PCBAgent**: outperforms SOTA (MaskPlace, ChiPFormer, MILP post-optimizer) on 17 industrial PCB tasks; specific numbers were not retrieved. [PR] — [ACM DL](https://dl.acm.org/doi/10.1145/3658617.3697736)
- **VeoPlace**: beats ChiPFormer on 9 of 10 benchmarks, with peak wirelength reduction >32%, and improves DREAMPlace by up to 4.3% on 8 of 8 Superblue designs. [PP] — [arXiv 2603.28733v2](https://arxiv.org/html/2603.28733v2)
- **EvoPlace**: HPWL −5.05% (MMS), −5.29% (ISPD2005), −8.30% (ISPD2019) versus DREAMPlace-based baselines, up to 17%. [PR] — [IEEE TCAD](https://ieeexplore.ieee.org/document/11345590/)
- **CoEvoP&R**: routed wirelength −16.9%, congestion −36.7%, WNS +0.70 ns (Nangate45); −5.4% and −23.2% (Superblue) versus native DREAMPlace. [PP] — [arXiv 2607.17398](https://arxiv.org/abs/2607.17398)
- **OrderPlace**: −34.04% wirelength versus WireMask-EA and −14.08% versus EGPlace on ISPD2005. [PR, ICML 2026] — [arXiv 2606.08904](https://arxiv.org/pdf/2606.08904)
- **MAGE**: WNS +11.1–19.3% and TNS +70–74% versus commercial macro placers, but routed wirelength +29.7% and power about +4% (per Pith). [PP] — [Pith](https://pith.science/paper/2607.18536)
- **MCP4EDA**: timing closure +15–30% and area −10–20% versus default synthesis flows (self-reported). [PP] — [arXiv 2507.19570](https://www.arxiv.org/abs/2507.19570)
- **AuDoPEDA**: up to −5.9% routed wirelength, −10.0% clock period, −19.4% power in OpenROAD. [PP] — [arXiv 2601.06268](https://arxiv.org/pdf/2601.06268)
- **ICPI (analog)**: OTA1 FoM 1.104, versus 1.003 without ICPI and 0.979 for BO; n=1 caveat. [PR, ICLAD] — [arXiv 2608.13767](https://arxiv.org/abs/2608.13767)
- **GPT-6 Astra (anecdotal)**: 46 schematic-parity issues (JLCPCB) and 168 DRC violations versus 0 for a human board (zerowithdot); bulk routing was done by Freerouting. [V/C] — [JLCPCB](https://jlcpcb.com/blog/gpt-6-astra-pcb-design-in-kicad); [zerowithdot](https://zerowithdot.com/blog/gpt-6-astra-impact-on-cad/); [NextPCB](https://www.nextpcb.com/blog/gpt-6-astra-kicad-pcb-routing-test)
- **Classical PCB placement reference**: NS-Place (Laplacian seed → net-crossing minimization → **MILP legalization**) cuts net-separation cost by 77% versus manual and 41% versus GDMILP. This shows the strength of classical solvers on PCB placement sub-problems. [PP] — [arXiv 2210.14259](https://arxiv.org/pdf/2210.14259)

### Inferences
- The quantitative case is strong for "LLM improves or steers the classical engine" and weak or negative for "LLM replaces the engine". Every PCB benchmark where an LLM directly places or routes shows it trailing classical or human baselines.
- Self-reported preprint gains in IC placement are large but unreplicated. MAGE shows how optimizing one metric (timing) can hide regressions in another (wirelength, power), so any KiCad system's evaluation should report a full metric vector.

### Gaps
- No independent replication of any LLM-placement result was found.
- No LLM-versus-Freerouting comparison on *placement-plus-routing jointly* for PCB was found. PCBWorld routes pre-placed boards.

---

## 8. Implications for an LLM-driven KiCad placer/router

### Takeaway
Build a **neuro-symbolic system**:
- The LLM owns *semantics, intent, strategy, constraints, objective weights, and explanation*.
- Deterministic solvers own *geometry, legality, and bulk routing*.
- Every LLM decision is a **checkable, provenance-carrying constraint** in a design-intent graph.
- Feedback comes from deterministic verifiers (KiCad DRC, parity, custom constraint checkers), with rendered diagnostic images as a secondary qualitative channel.
- Expensive LLM creativity goes offline, into evolving heuristics and objectives over a board corpus, not online, step-by-step routing.

### Cited Findings (evidence base for the recommendations)
- Open-loop LLM geometry fails (PCBWorld engine-free 0.02 CP); interactive tool use helps (0.65) but trails Freerouting (0.80), scores 0.00 on large boards, and is about 200× slower — [arXiv 2607.05915v2](https://arxiv.org/html/2607.05915v2)
- The successful pattern is VLM-proposed regions plus a numerical placer (VeoPlace) — [arXiv 2603.28733v2](https://arxiv.org/html/2603.28733v2); LLM-evolved objectives, algorithms, and orderings (CoEvoP&R, EvoPlace, OrderPlace) — [arXiv 2607.17398](https://arxiv.org/abs/2607.17398), [IEEE TCAD](https://ieeexplore.ieee.org/document/11345590/), [arXiv 2606.08904](https://arxiv.org/pdf/2606.08904)
- Scripts enforce hard constraints while vision judges soft qualities, with a structured report per iteration and an independent auditor (MAGE) — [arXiv 2607.18536](https://arxiv.org/abs/2607.18536)
- Present repair as a menu of rule-engine-generated edits (DRC-Aid); unbounded self-correction risks non-convergence — [arXiv 2607.22761](https://arxiv.org/html/2607.22761v1); [arXiv 2605.01471](https://arxiv.org/html/2605.01471v1)
- A datasheet → compact knowledge graph with closed ontology and predicates cuts about 16k tokens to about 300 per IC (PCBSchemaGen) — [arXiv 2602.00510v2](https://arxiv.org/html/2602.00510v2)
- Expert trajectories and skills help agents dramatically (PCBInnoBench 22.0% vs 7.3%; PDAgent-Bench) — [NeurIPS](https://neurips.cc/virtual/2026/poster/139034); [arXiv 2606.17253](https://arxiv.org/abs/2606.17253)
- Declarative code interfaces work better for agents than GUI drawing (EEBench/atopile) — [EEBench](https://eebench.org/blog/can-ai-design-circuit-boards-yet/)
- CSS-like box formats help LLMs read layouts (LayoutGPT); VLMs need text redundancy (SpatialEval); Python tools fix arithmetic but not optimization (FloorplanQA) — [arXiv 2305.15393](https://arxiv.org/pdf/2305.15393); [NeurIPS 2024](https://neurips.cc/virtual/2024/poster/94371); [Lacuna/FloorplanQA](https://lacuna.tiptreesystems.com/work/floorplanqa-a-benchmark-for-spatial-reasoning-in-llms-using-structured/wrk_82594f0d17bb048f48ab07aecaa3ec8b)
- Electrically computable values (impedance, diff-pair spacing) should come from calculators, not networks (Quilter) — [Quilter](https://www.quilter.ai/blog/llm-pcb-layout-gpt-6-astra)
- The practical expert workflow that GPT-6 Astra imitated: protect power, bootstrap, and switching nets first, then autoroute the rest. It still produced parity and DRC issues — [JLCPCB](https://jlcpcb.com/blog/gpt-6-astra-pcb-design-in-kicad); [zerowithdot](https://zerowithdot.com/blog/gpt-6-astra-impact-on-cad/)
- Ready-made KiCad-native evaluation exists: PCBWorld (679 real boards, push-and-shove engine, DRC), OmniLayout (placement), PCB-Bench (comprehension), PCBInnoBench (editing) — [PCBWorld GitHub](https://github.com/LGAI-Research/PCBWorld); [arXiv 2607.03261](https://arxiv.org/abs/2607.03261); [PCB-Bench GitHub](https://github.com/digailab/PCB-Bench); [NeurIPS](https://neurips.cc/virtual/2026/poster/139034)

### Inferences (concrete recommendations; these are my synthesis, not sourced claims)

**A. Representations (what the LLM sees)**
1. **Canonical board-state JSON** generated from the `.kicad_pcb` file via the KiCad IPC API or pcbnew. Per footprint: refdes, value, footprint, courtyard bbox as CSS-like `{x, y, w, h}` in mm (fixed 0.1 mm precision), rotation, side, locked flag, functional group id, and pins (pin name, net, **pin role** from the datasheet knowledge graph). Per net: class, criticality tag, current, and frequency/edge-rate tag. Keep ids stable across turns so the model never has to re-identify objects (TopoBench state-tracking failures).
2. **Derived-facts layer, computed by code and never by the LLM**: pairwise overlaps; courtyard clearance violations; for each intent constraint, the *measured value and pass/fail*; neighbor lists (k nearest parts with distances); ratsnest crossing count and per-net HPWL; per-region pin density and estimated congestion; loop area of tagged critical loops; and board-edge and keepout distances. This sidesteps the arithmetic and overlap failures seen in FloorplanQA and OmniLayout.
3. **Hierarchical abstraction**: LLM reasoning happens mostly at the **group/zone level**, e.g. "power input", "buck converter", "MCU + decoupling", "USB connector + ESD", "analog front end". Groups are presented as boxes with ports. This matches VeoPlace regions and MAGE group boxes. Drill into a local view only for critical clusters.
4. **Rendered diagnostic images as a secondary channel**, always with the same ids as the text. Use the overlays listed in Section 6. Use them for qualitative critique (signal flow, clustering, symmetry, obvious tangles), never as the source of truth for numbers.
5. **Avoid whole-board ASCII grids.** Small local ASCII or occupancy grids may be acceptable for a congested neighborhood, but prefer coordinates plus derived facts.

**B. Division of labor**
- **LLM responsibilities**:
  - (i) Functional understanding of the netlist and partitioning into groups.
  - (ii) Extracting layout predicates from datasheets and app notes into the knowledge graph, with page provenance and validity conditions.
  - (iii) Tagging nets by criticality: hot loops, high di/dt, sensitive analog, high-speed pairs, Kelvin sense, thermal paths.
  - (iv) Writing a **constraint/intent program** in a small DSL: zones, relative proximities, orientation toward pins, same-side rules, symmetry, keepouts, routing order and priority, net-class widths derived by a calculator, via budgets, and layer assignments.
  - (v) Choosing solver objective weights and relaxing constraints when infeasible.
  - (vi) Interpreting verifier output and selecting among enumerated repairs.
  - (vii) Producing explanations from the intent graph.
- **Solver responsibilities**:
  - (i) Exact placement: analytical or SA global placement with constraint penalties, then **CP-SAT/MILP legalization** honoring hard constraints (NS-Place and PCBAgent show MILP is effective for PCB legalization).
  - (ii) Critical-net routing through a router primitive the LLM *parameterizes* ("route net SW: Q1.D→L1.1, F.Cu, width from calculator, minimize loop with C_in") rather than drawing.
  - (iii) Bulk routing via Freerouting or KiCad push-and-shove (or kicad-tools `kct route`).
  - (iv) DRC/ERC/parity via kicad-cli.
  - (v) Impedance and current-width calculators.
- **Interface style**: a code/DSL or MCP tool surface with **coarse, semantic, idempotent operations** (`assign_zone`, `add_constraint`, `place_group`, `route_critical`, `autoroute_remaining`, `run_checks`) rather than hundreds of low-level GUI-like tools. Large tool surfaces like Konnect's 200+ tools are not evidence of quality, and EEBench's experience favors declarative code.

**C. Feedback loops**
1. **Inner loop (deterministic, fast)**: solver → checks → structured report listing hard-constraint violations, intent-constraint pass/fail with measured values, DRC items, unrouted nets, parity issues, and metric vector (HPWL, via count, completion, loop areas). Only the delta from the previous iteration goes to the LLM.
2. **Repair loop (bounded)**: a rule engine turns each violation into 2–6 candidate edits (nudge, rotate, swap side, relax soft constraint, reroute with different layer). The LLM picks and justifies. Cap iterations and token budget, and detect cycles (DRC-Aid pattern; non-convergence warning).
3. **Strategy loop (best-of-N plus audit)**: generate K alternative intent programs, e.g. different zonings, run the full pipeline on each, and let a **stateless auditor** compare the metric vectors and diagnostic images (MAGE tournament plus auditor). Report the full metric vector to avoid MAGE-style hidden regressions.
4. **Offline evolution loop**: use an LLM (EoH/ReEvo/CoEvoP&R style) to evolve the *placement objective terms, group-ordering heuristics, and repair-menu generators* across a corpus such as PCBWorld's 679 real boards plus internal boards. Score each candidate with real routing completion and DRC. At run time this costs nothing extra, and it directly targets the PCBWorld result that LLMs are too slow for step-wise routing.
5. **Memory**: an ICPI-style **design journal** storing (situation, action, outcome, lesson), plus retrieval of expert trajectories and skills. PCBInnoBench shows expert trajectories roughly triple success. Retrieve reference layouts by *topology* (subcircuit graph similarity), not text embedding (PCBSchemaGen ablation).

**D. "The why": design-intent graph**
- Nodes: **Intent** (a natural-language goal, e.g. "minimize buck hot-loop area"), **Evidence** (datasheet page/figure, app-note section, rule-of-thumb id, user instruction), **Constraint** (a DSL predicate with hard/soft weight and validity conditions), **Decision** (a concrete placement or routing action and its solver run id), and **Verification** (measured value and pass/fail, DRC refs).
- Edges: Intent → Constraint (derived_from) → Evidence (justified_by); Decision → Constraint (satisfies or violates); Verification → Constraint.
- Persist this graph as a sidecar JSON next to the `.kicad_pcb`. Optionally mirror hard constraints into KiCad custom DRC rules with comments so the intent survives tool round-trips.
- Explanations ("why is C7 here?") are generated by traversing the graph: C7 → near(C7, U3.VIN, 2 mm) → TPSxxxx datasheet §10.1 Fig. 34 → measured 1.4 mm, PASS. A post-hoc narrative is not acceptable. Every LLM-proposed constraint must cite evidence or be labeled "heuristic" or "assumption" so engineers can audit it. This also addresses the finding that LLMs often miss rationale.

**E. Evaluation plan**
- Routing: PCBWorld D2/D3-A/D3-B CP@1/CP@5 against Freerouting and kicad-tools.
- Placement: OmniLayout tasks.
- Comprehension and grounding regression: PCB-Bench and PCB-QA.
- End-to-end editing: PCBInnoBench.
- Always report the metric vector (completion, DRC count, parity issues, wirelength, vias, critical-loop areas, intent-constraint satisfaction %) and wall-clock and token cost.

### Gaps
- No published evidence yet on whether an LLM-written intent DSL plus CP-SAT/MILP placement beats Freerouting-era classical placers on real PCBs. This needs to be built and measured.
- The optimal granularity of LLM decisions (group-level vs part-level) for PCB is untested in the literature.
- Unverified in this session: Holodeck/LayoutVLM-style "LLM relations → solver" precedents, OmniRouting results, and the "Li et al." MILP-legalization agentic placement paper. All are worth a follow-up search when budget allows.
