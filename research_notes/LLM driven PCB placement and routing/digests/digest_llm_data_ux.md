# Digest: LLM capabilities, interfaces, agent loops, design understanding, datasheets, data, field reports and UX for LLM-driven KiCad placement and routing

**Inputs, all read in full:** `llm_for_eda.md` [EDA], `verification_papers.md` [VER], `learning_from_layout_data.md` [DATA], `netlist_datasheet_understanding.md` [NET], `field_reports_and_ux.md` [UX].

**Correction policy.** VER checked primary sources for claims in EDA (and in placement, routing and cross-domain notes). Where they conflict, VER wins. Corrected values are marked **(VER)**.

**Evidence tags** (carried over from the notes):

| Tag | Meaning |
|---|---|
| [P] | primary source read (full text, or abstract plus results) |
| [P-abs] | abstract or metadata only |
| [PvS] | read via the "Agentic EDA: A Handoff Perspective" survey |
| [S] | snippet or secondary summary, unverified |
| [V] | vendor or self-reported |
| [3P] | third-party GitHub engineering document, not peer-reviewed |
| [M] | the note author's own measurement on downloaded data |
| [A] | single anecdote |
| [G] | GitHub issue or PR, seen as a snippet |
| [doc] | product or project documentation |
| [PP] | preprint |
| [PR] | peer-reviewed |

All facts are as of 2026-10-20.

---

## 0. Bottom line

1. **LLMs succeed on semantic decisions over a low-dimensional control surface and fail when they emit geometry.**
   - RAC, nine models: committing named relations reaches **90.9% clean-pass**; emitting coordinates reaches **23.2%**.
   - OmniRouting: the best LLM connects **12.6%** of nets DRC-clean, against 56.2% for an old open-source router and 93.6% for humans.
   - Every PCB result where an LLM-involved system beats classical or commercial tools keeps the geometry inside a solver.
2. **The interface matters more than the model.** Choose bundled relations, bounded operator menus, structured text feedback and tool-computed state. Images and free-form code add little.
3. **Connectivity, matching and numbers should be deterministic code.** LLMs are good at names, documents, writing detector code, triage, "noticing" problems and explanation.
4. **Usable data is scarce.** Licence-clean, fully routed, DRC-clean open KiCad boards number in the low hundreds to low thousands. The cheap learnable signal is relational and per-package (decap distances, width ratios), not raw geometry.
5. **Field successes share one pattern:** the LLM orchestrates deterministic engines, KiCad or the fab gives the verdict, every write is read back independently, and a human gates defined checkpoints. The most expensive failures are invisible to DRC.
6. **UX:** show the agent's interpretation before acting; offer a few alternatives with scorecards; answer "why here, not there?" by re-solving under the implied constraint; tag every claim with how it was established; log rationale at decision time, anchored to board objects.

---

## 1. What LLMs can and cannot do in PCB layout

### 1.1 Emitting geometry fails

**OmniRouting** [P][PP] ([arXiv 2608.04434](https://arxiv.org/pdf/2608.04434)), Penn State–led.
- **Data:** 1,681 open-hardware designs (SparkFun, Arduino, Adafruit, Seeed) parsed from EAGLE XML: 494K wire segments, 84.6K vias, 4.3K pours, 2–8 layers.
- **Zero-shot NRR/PRR:**

  | Router | NRR | PRR |
  |---|---|---|
  | Best LMM (Claude Opus 4.8) | 12.60% | 15.41% |
  | GPT-5.5 | 9.13% | 12.26% |
  | PcbRouter (open source) | 56.20% | 71.37% |
  | GPCB transformer router | 0.69% | — |
  | Human reference | 93.58% | 95.91% |

- **LMM errors:** outputs average 69.8–431.3 DRC violations, with 20.5–78.3% of nets physically shorted (humans: 0.80 and 0.38%). GND is routed as ordinary traces instead of pours.
- **Agentic best:** GPT-5.5 with all tools reaches NRR 27.98% / PRR 30.34%. Its DRC total falls from 48.06 to 9.35 and shorts from 39.5% to 9.1%.
- **(VER #29):** the "<13% vs ~94%" figure had been attributed to OmniLayout; it belongs to OmniRouting.

**PCBWorld** [P via VER] ([arXiv 2607.05915 v4](https://arxiv.org/pdf/2607.05915)). LG AI Research; KDD 2026 Workshop on Evaluation and Trustworthiness of Agentic AI, non-archival. Interactive GPT-5.4 routing in KiCad's push-and-shove engine:
- clean-pass (CP) 0.65 on D3-A (99 boards, ≤31 pads);
- **0.00 for every LLM on D3-B**. **(VER #8):** D3-B is only **10 two-layer boards**, and LLM rows are a single best-of-5 run.

**Engine-engagement ablation** (GPT-5.4, D3-A): interactive 0.65, plan-and-execute 0.19, engine-free 0.02. **(VER #1):** the LLM prompt contained **no reward and no DRC-violation list**, only rejection and no-effect tags. These numbers are therefore a *lower bound* for a better-instrumented agent.

**Other direct-geometry evidence:**
- RAC: coordinates 23.2%; coordinates plus a Python sandbox **21.0%** [P] ([arXiv 2610.20935](https://arxiv.org/pdf/2610.20935)).
- Holodeck: GPT-4 absolute coordinates scored MRR **0.364**, no better than random collision-free placement at 0.369. LLM relations solved by DFS scored **0.706** [P] ([arXiv 2312.09067](https://arxiv.org/abs/2312.09067)).
- Field reports:
  - GUI-only routing produced **3 segments in one hour** ([NextPCB](https://www.nextpcb.com/blog/gpt-6-astra-kicad-pcb-routing-test)).
  - An agent placed a via 0.0285 mm from a pad and said "I have no spatial intuition, only arithmetic" ([StationX](https://app.stationx.net/articles/ai-pcb-design)).
  - Claude's self-written A* router used 0.35 mm edge clearance against a 0.5 mm rule ([JLCPCB](https://jlcpcb.com/blog/kicad-mcp-how-to-design-a-pcb-with-claude-code)) [A].

### 1.2 Placement: connectivity-aware but geometrically illegal (VER #26 changes the story)

**OmniLayout** [P] ([arXiv 2607.03261 v3](https://arxiv.org/pdf/2607.03261), Tab. 2). **(VER #25):** it is Penn State–led, not Microsoft Research; it evaluates 9 LMMs and 6 PnR tools.

**FreeRouting routability (RR):**

| Group | Results |
|---|---|
| LMMs | GPT-5.5 **0.90** zero-shot and **0.95** few-shot; GPT-5-mini 0.84; Claude Sonnet 4.6 0.76; Gemini 3.1 Pro 0.34 zero-shot but 0.91–0.92 given the schematic netlist or image; Qwen 0.31 |
| Academic placers | SA-PCB 0.25, NS-Place 0.23, Cypress 0.33, PCBAgent 0.42, Chen et al. DAC'25 0.62 |
| References | Quilter 0.84; human 1.00 |

The best LMMs beat the academic placers on this metric. **The real failure is pad-level legality:**
- 79.82% of outputs had at least one pad overlap;
- 72.89% had a part out of bounds;
- 80% of parts were placed on top;
- reference similarity was below 60%;
- the best end-to-end pass rate was 62.6% (GPT-5.5 few-shot).

Other OmniLayout findings:
- Schematic context raised functional-grouping AUC in all 15 comparisons (+0.079 to +0.091).
- Few-shot examples barely moved AUC (−0.006).
- **A structured text conflict list (Geo. Check) gave the lowest overlap**, better than inferring conflicts from images.
- Using all tools together was not uniformly best.

**Conflict:** EDA's framing ("poor post-route wirelength and completion… even agentic") is superseded by VER.

### 1.3 General spatial reasoning: difficulty scales with coupled relations

- **PlanarBench** [P] ([2606.02010](https://arxiv.org/abs/2606.02010)), 91 models:
  - Edge count drives difficulty: r = −0.85, against −0.47 for vertex count (−0.80 partialled).
  - Mean score falls from 46.4% at 5 edges to 16.3% at 8, 5.1% at 10 and **1.0–1.6% at 11–12 edges**, on graphs of at most 7 vertices.
  - Extended thinking took Sonnet 3.7 from 39.5 to 95.5. There is a cliff around 30B parameters.
  - Typical failures are missing edges at high-degree nodes. The authors call this "relational load".
- **TopoBench** [P] ([2603.12133](https://arxiv.org/abs/2603.12133)):
  - Frontier models solve fewer than a quarter of hard puzzles.
  - Interventions show "premature commitment" and "constraint forgetting" are causal errors.
  - Cell-aligned encodings give +30–40 pp on some puzzles but −26 pp on Undead (DeepSeek).
  - Images do not reliably help.
  - Structured engine state raised hard-Bridges accuracy from 40% to 46%, and to 50% with the full suite. An ASCII render tool reached only 42%.
  - Authors: "the bottleneck lies in extracting constraints from spatial representations".
- **FloorplanQA** [P][PR] (ICML 2026, [2507.07644](https://arxiv.org/abs/2507.07644)):
  - Models fail at constraint satisfaction, area union (they sum instead), centroids of non-axis-aligned polygons, and shortest paths in clutter.
  - A code interpreter adds 30–40 pp on distance and angle tasks but little on planning. Images are not consistently better than text.
  - The authors advise external geometric solvers.
- **SpatialEval** (NeurIPS 2024, [2406.14852](https://arxiv.org/abs/2406.14852)): models can fall below random, and VLMs often trail their own text backbones.
- **Visualization-of-Thought** ([2404.03622](https://arxiv.org/abs/2404.03622)): ASCII mental images give +23.5% on grid navigation, but the effect is prompt-sensitive.
- **Blink** ([2404.12390](https://arxiv.org/abs/2404.12390)): GPT-4V 51.26%, Gemini 45.72%, humans 95.7%.
- **CoDeLayout** ([2608.26716](https://arxiv.org/abs/2608.26716)): GPT-o3 79.68%, against 91.66% for a post-trained Qwen2.5-VL-7B.
- Further evidence in the same direction:
  - GSU ([2603.17333](https://arxiv.org/abs/2603.17333)): fine-tuned small models approach frontier models on grid tasks.
  - PPNL ([2310.03249](https://arxiv.org/abs/2310.03249)): no long-horizon planning.
  - GPSBench ([2602.16105](https://arxiv.org/abs/2602.16105)) and Text2CAD-Bench ([2605.18430](https://arxiv.org/abs/2605.18430)): performance degrades on complex topology.
  - OmniSch ([2604.00270](https://arxiv.org/abs/2604.00270)): brittle schematic grounding, helped by tool-augmented visual search.
  - MMCircuitEval ([2507.19525](https://arxiv.org/abs/2507.19525)): 3,614 QA pairs; gaps in back-end design and computation.

### 1.4 Netlist and circuit reading

- **NetlistBench** [P] (MLCAD 2026, [2608.12197](https://arxiv.org/abs/2608.12197)), 2,342 analog CMOS cases:
  - Recognition subtotals: Claude Sonnet 4.6 98%, GPT-4.1 74%, Gemini 2.5 Flash 75%, DeepSeek-V4-Flash 74%, Qwen3.6-Flash 62%, Qwen3-30B 55%.
  - Relational queries vary enormously across models: node incidence 15–98%, terminal connectivity 6–99%, **terminal-neighbour incidence 2–97%**, structural equivalence 49–90%. Explicit attributes score about 99–100%.
  - Dependent edits collapse: Claude falls from 80% at 3 edits to 26% at 15; GPT-4.1 from 71% to 34%.
  - Reasoning mode adds 30–40 points for weaker models (DeepSeek-V4-Flash: 52% to 81%).
  - The authors caution that results may not transfer to RF, power, digital or mixed-signal netlists.
- **GENIE-ASI** [P] (MLCAD 2025, [2508.19393](https://arxiv.org/pdf/2508.19393)). **(VER #32):** it targets transistor-level op-amp SPICE netlists, not PCB netlists.
  - GPT-4.1 with GENIE-ASI reaches F1strict 0.70 overall; zero-shot direct prompting reaches 0.49–0.64.
  - By level: HL1 0.97, HL2 0.81, **HL3 (stage level) 0.31**. Every model scores 0.05–0.31 at HL3.
  - The AnyGraph GNN baseline reaches only 0.12–0.30.
  - LLMs "often skipped" elements when reading directly and did better through generated Python.
  - *Minor discrepancy:* EDA and VER quote F1 1.0/0.81/0.31 for simple/moderate/complex structures, while NET gives HL1 0.97.
- **PCB-QA** [P] (MLCAD 2026, [2606.23704](https://arxiv.org/abs/2606.23704)), 480 questions over 8 KiCad projects:
  - Accuracy/F1 by input format: KiCad PDF 0.43/0.28; native `.net` + `.cir` 0.55/0.45; **hierarchical JSON 0.88/0.90**.
  - With JSON, Gemini 3 Flash reaches 93% on the full set.
  - Complex projects reach about 100k tokens, so Python tools filter the relevant parts.
  - Datasheet questions are the weakest category.
- **HWE-Bench** [P] ([2603.18102](https://arxiv.org/pdf/2603.18102)), 300 tasks over 2,914 datasheets:
  - Best: Claude Sonnet 4.5 at **8.15%**, then GPT-5.2 at 6.58% (VER #31).
  - Conventional pin names give very high connection accuracy. Multiplexed or redundant pins cause omissions and hallucinated connections.
- **Other circuit-reading results:**
  - CIRCUIT ([2502.07980](https://arxiv.org/abs/2502.07980)): GPT-4o 48.04% on final answers, 27.45% on unit tests.
  - AMSbench ([2505.24138](https://arxiv.org/abs/2505.24138)): best netlist normalized edit distance 0.91 (lower is better).
  - CircuitSense ([2509.22339](https://arxiv.org/abs/2509.22339)): above 85% on perception, below 19% on symbolic derivation.
  - Image2Net ([2508.13157](https://arxiv.org/abs/2508.13157)): 80.77% success.
  - Validation vs simulation ([2609.26830](https://arxiv.org/abs/2609.26830)): 10.7% of LLM circuits failed topology validation yet ran in ngspice silently; 4.7% passed validation and failed in simulation.
  - Masala-CHAI's netlists compiled at only 22% before repair ([2604.23195](https://arxiv.org/abs/2604.23195)).
- **PCB-Bench** [P] (ICLR 2026, [PDF](https://proceedings.iclr.cc/paper_files/paper/2026/file/051f3997af1dd65da8e14397b6a72f8e-Paper-Conference.pdf)). **(VER #24):**
  - Gemini-2.5-Pro scores 100% and GPT-5 90.9% on Basic Wiring Error Identification. That subset has only about 11 items, so the gap is one question.
  - Open-source models score 45–55%.
  - Claude-Opus-4.1's 93.3% is on Placement Macro-level CQ.
- **PDAgent-Bench** ([2606.17253](https://arxiv.org/abs/2606.17253)), 353 problems: strong on concepts (GPT-5.5 73.3% on root cause), weak on long-horizon tool use.

### 1.5 Where LLMs add value (field and paper evidence)

- **Noticing.** After a failed route, Claude observed that "the unrouted nets all terminated in the same congested region" and proposed staggering U6–U10. The board then routed **314/314** on 4 layers ([tinycomputers](https://tinycomputers.io/posts/what-routing-314-nets-taught-me-about-ai-assisted-pcb-design.html)) [A].
- **Documents and code:** datasheet audits; footprint code from datasheets; S-expression parsing.
  - JITX extracted the 95-row nRF5340 pin table from an 820-page datasheet "exactly correct" ([JITX](https://blog.jitx.com/jitx-corporate-blog/testing-generative-ai-for-circuit-board-design)) [V].
  - The RF-workflow agent noticed an ESD variant limited to V_CEO = 2.25 V ([2608.31006](https://arxiv.org/abs/2608.31006)).
- **Weak spots:**
  - part selection ("uniformly bad"; JITX);
  - naive decoupling advice (a decoupling cap placed where a coupling cap was needed);
  - debugging interfaces the model cannot run;
  - knowing when to stop.
- **Long sessions need recent models.** Multi-hour tool-driving sessions were only reliable with frontier models released since early to mid-2026 ([2608.31006](https://arxiv.org/abs/2608.31006)).
- **Surveys:**
  - No human-free industrial tape-out exists yet ([2512.23189](https://arxiv.org/abs/2512.23189)).
  - The "syntax trap": models produce plausible code rather than physically correct hardware ([2608.27184](https://arxiv.org/abs/2608.27184)).
  - "No GenAI tools independently validate PCB layouts" ([2606.17074](https://arxiv.org/abs/2606.17074), 80 papers).

**Implications for our system**
- Never let the LLM write coordinates, millimetres or copper. Coordinates may be *readable* but never *writable*.
- Decompose by functional group so each LLM decision involves few coupled relations.
- Treat PCBWorld's LLM numbers as a floor; a DRC-aware agent may do better.
- Expect the LLM placer's main defect to be pad-level legality. Always pass its output through a legalizer.
- Route the LLM's strengths (noticing, documents, detector code) into explicit tools: congestion attribution, datasheet audits, detector writing.

---

## 2. Interfaces and representations

### 2.1 Write interface: the RAC ladder

**RAC** [P][PP] ([arXiv 2610.20935](https://arxiv.org/pdf/2610.20935), Univ. of Washington, 14 Oct 2026). Setup: 98 PCB tasks (42 routing, 31 placement, 17 combined, 8 repair), 6 seeds, at most 5 model calls, 9 models (including Claude Opus 4.8 and 5, GPT-5.6, Gemini 3.8 Flash).

**Mean clean-pass rate by interface:**

| Interface | Clean-pass |
|---|---|
| Direct coordinates | 23.2% |
| Coordinates plus a Python sandbox | 21.0% |
| PCBWorld-style candidate selection | 37.4% |
| One relation at a time | 62.4% |
| Requirements-only delegation | 74.0% |
| **RAC** | **90.9%** (77.6–95.9% by model) |

**Contract.**
- The agent observes exact state but acts only through relations over named objects: proximity, alignment, symmetry, edge association, keepouts, matched routing, layer preference, via limits.
- **No action accepts a coordinate or a metric distance.** Magnitudes are the ordered classes tight/close/loose, with millimetre values fixed on the solver side.
- The whole bundle is submitted at once and realized jointly.
- An independent DRC plus relation-specific oracles verify the result.
- On infeasibility, feedback names the conflicting constraints, the violation magnitudes and the **admissible relaxations**.
- Example actions: `board_edge(J1, left)`, `place_relative(C1, U1.R1, near, tight)`, `route_matched([N2, N3], 5%)`.

**Further results.**
- Eight of nine models reached 89.8–95.9%. Newer models were not reliably better (Opus 4.8 > Opus 5).
- RAC used 22.9–48.5% fewer tokens than candidate selection and had the lowest latency for 7 of 9 models.
- **Across harnesses** (native calls, Codex, Claude Code, OpenCode), coordinates scored 22.7–32.7% and RAC 91.8–95.9%. Coding-agent harnesses cost 2.2–5.4× the tokens of native calls.
- **Robustness to geometry change.** The same relations were re-solved after a 20% board shrink, a 20% expansion or a 25% footprint shrink. **89.5%** passed (411/459), against 65.6% for the best coordinate-reuse control. Board shrink was hardest: 77.1% vs 47.7%.

**Caveats (VER):** the tasks look small and synthetic (examples have about 5–10 parts), and the backend placer and router were not identified. Preferences that cannot be written as checkable predicates fall outside the contract.

### 2.2 Convergent precedents: relations realized by solvers

- **Holodeck** [P] (CVPR 2024; VER #39): 10 soft relation types in 5 groups; collisions and boundaries are hard constraints. The LLM picks an anchor, then a DFS solver places the rest (MILP is an alternative).
- **LayoutVLM** [P] (CVPR 2025, [2412.02193](https://arxiv.org/abs/2412.02193)). The VLM proposes numeric initial poses plus differentiable relations from marked images.
  - **Self-consistent decoding** keeps only the relations that the VLM's own initial poses already satisfy.
  - Collision-free / in-bounds / semantic alignment: LayoutVLM 81.8 / **94.9** / **58.8**; LayoutGPT 83.8 / 24.2 / 16.6; Holodeck 77.8 / 8.1 / 5.6.
  - Ablations (semantic alignment): without self-consistency 46.4; without numeric initialization 41.0; without spatial constraints 6.7.
- **Brown PSDL** [P] ([2504.05482](https://arxiv.org/abs/2504.05482) / [2510.16147](https://arxiv.org/abs/2510.16147)). **(VER #40):** these are **one work**, not two.
  - LLM relative-placement programs (e.g. `chair.max.x = table.min.x - 0.1`) are repaired by an LLM-free numeric step. The objective is loss + edit distance + a volume-weighted optimal-transport term, so large objects move less. About 7.13 edits per scene.
  - Humans preferred the results **82.9%** of the time over the declarative DeclBase and **94.3%** over Holodeck.
  - Repair rates: 91% of errors fixed, against 96% for gradient descent and 93.5% for flat local search. It still wins on human preference because the relations survive.
- **ModuPlace CCG**, **SchGen**, **PCB-Migrator**, and **NS-Place's** relative-position MILP legalization follow the same pattern (see §3 and §7).
- **Tension: imperative vs bundled.** PSDL's sequential imperative style beat declarative baselines on scenes. On PCB tasks, RAC's sequential-relations baseline scored 62.4%, against 90.9% for one jointly realized bundle. Coupled PCB constraints seem to need joint realization.

### 2.3 Read representation (what the LLM sees)

- **Graph text encoding** (Talk like a Graph, ICLR 2024, [2310.04560](https://arxiv.org/abs/2310.04560)):
  - The choice of encoding swings accuracy by 4.8–61.8%.
  - An **incident list** (each node with its neighbours) beat an edge list on connected-node queries: **53.8% vs 19.8%**.
  - Integer node names help.
- **LayoutGPT** ([2305.15393](https://arxiv.org/abs/2305.15393)): CSS-style left/top/width/height exemplars were the most essential prompt component.
- **Compact hierarchical JSON plus query tools** beats native exports (PCB-QA, §1.4).
- **Formal language choice matters** across 6 LLMs ([2502.17216](https://arxiv.org/abs/2502.17216)).
- **R³L** ([2605.06758](https://arxiv.org/abs/2605.06758)): multi-hop relative chains accumulate frame-transform errors, so anchor relations directly to IC or module frames.
- **PCBWorld's observation encoding (VER #45):**
  - S-expressions, with the static board block in the system message for prefix caching.
  - Zones are dropped, per-netclass rules collapse to the strictest envelope, pads keep only xy and layer, and coordinates are rounded to 3 decimals.
  - The per-step message holds a 2-turn history plus the valid verbs.
- **Field practice:**
  - list results capped with `_total` / `_truncated` metadata ([havamal-65/KiCad-MCP](https://github.com/havamal-65/KiCad-MCP));
  - a compact board encoding validated only up to 63 footprints ([Gato513](https://github.com/Gato513/kicad-mcp)).

### 2.4 Images: optional, with exceptions

**Images add little:**
- **OmniRouting:** visual feedback lowered total DRC for every model, but the **structured Score tool cut the cross-model mean DRC from 141.18 to 32.31 (−77.1%)**. Visualization alone barely moved routability (GPT-5.5 NRR 21.71% → 20.96%). A pre-routing tool raised reference similarity by about 10 points.
- **VeoPlace:** text-only and image-only differ by **under 0.8%**, while random regions sharply degrade results (VER, [2603.28733](https://arxiv.org/pdf/2603.28733)).

**Exceptions where images helped:**
- **MAGE (VER #22, [2607.18536](https://arxiv.org/pdf/2607.18536)):** removing visual feedback made WNS 40.5% and TNS 133.0% worse and lowered human-likeness by 4.2%, while routed wirelength (+2.3%) and power (+0.4%) barely changed. Vision mattered for timing and structure, not wirelength.
- **Specialized or fine-tuned vision:**
  - SCALE's DRC-VLM gave +12–25% DRV-fix solve rate, up to 97% ([2607.21850](https://arxiv.org/abs/2607.21850));
  - DRC-Coder used a VLM to read rule illustrations ([2412.05311](https://arxiv.org/abs/2412.05311));
  - a PCBA visual-QA model fine-tuned with GRPO scored 83.24 ([2609.21276](https://arxiv.org/abs/2609.21276)).
- **LMM geometric perception of IC drawings is poor** (LLM4-IC8K, [2508.03725](https://arxiv.org/abs/2508.03725)).

**Conflict with practitioner use:**
- A text-to-CAD study found visual feedback best of four agent workflows ([Design Society](https://www.cambridge.org/core/journals/proceedings-of-the-design-society/article/from-text-to-design-a-framework-to-leverage-llm-agents-for-automated-cad-generation/5BD8D63CFCED28BDD7A01313162FFBE7)) [S].
- CopperLoop requires "the agent must look. Region renders per layer before claiming anything is routed" ([CopperLoop](https://github.com/PaoloJN/copperloop)).
- tscircuit asks the agent to inspect a PCB PNG.
- Autocuro had "moderate success" on placement review using heavily labelled diagrams ([Autocuro](https://autocuro.com/blog/can-llms-verify-pcb-designs)).
- **Reconciliation:** images serve as a sanity and gestalt channel, not as the primary carrier of constraints.

### 2.5 Code and API vs GUI

- **SchGen** [P] ([2605.30345](https://arxiv.org/abs/2605.30345)): relative-offset, pin-name code gave **82.0% valid circuits**, against **32.5%** for the same model emitting raw KiCad files. GPT-5.2 scored 67.9% with the code prompt and 10.5% emitting raw KiCad.
- **Practitioner views:**
  - EEBench: code "has worked much better… than asking a model to draw lines in a GUI".
  - Diode: "schematics for humans, code for models".
  - atopile vendor claim: pin-sharing questions answered 100% via code versus 55% from a PDF [V][snip].
  - PCBEditor: computer use is "the slowest possible path" and non-reproducible, which "for hardware… is usually disqualifying" ([DEV](https://dev.to/dibyaprakash_pradhan/kicad-and-ai-in-2026-mcp-servers-scripts-and-what-actually-works-3p1a)) [V].
- No documented Claude computer-use experiment placing or routing in the KiCad GUI was found.
- **Design-as-code tooling:**
  - The RF workflow drove KiCad only through pcbnew and kicad-cli, and was "netlist-identical by construction" (75 nodes, 18 nets checked) ([2608.31006](https://arxiv.org/abs/2608.31006)).
  - kicad-pycbnew writes `.kicad_pcb` without a KiCad runtime (MIT) ([2609.27522](https://arxiv.org/abs/2609.27522)).

### 2.6 Tool granularity and latency

- KiCad operations take **under 1 s**, while the full AI interaction takes **about 6–7 min** ([KiCad Agentic MCP](https://forum.kicad.info/t/kicad-agentic-mcp-an-ai-assistant-that-edits-your-board-through-kicads-own-api-and-lets-kicad-decide-whether-the-result-is-good/71403)).
- Tool catalogs range from 105 to 377 tools. kicad-mcp-pro defaults to 24 read-only tools.
- **Open gap:** no A/B study compares coarse and fine tool APIs for KiCad.

**Implications for our system**
- The single write API should be a typed relation bundle with ordinal magnitudes, realized jointly. Persist the bundle as the re-solvable intent artifact.
- Read API:
  - incident-list netlist with stable short ids;
  - compact JSON with truncation metadata;
  - tool-computed facts: overlaps, unrouted connections, DRC items with ids, per-relation verdicts with margins.
- Renders, if used, carry the same ids as the text and serve only gestalt checks.
- Prefer coarse, high-yield calls ("place this block under these relations").
- Calibrate tight/close/loose per component class from corpus statistics (see §7). This mapping is unpublished.

---

## 3. Agent-loop designs and their evidence

### 3.1 Bounded action space, deterministic realization, independent check

- **"Who Plans, Who Edits?"** [P] ([2610.24234](https://arxiv.org/abs/2610.24234)), analog repair.
  - **Workers:** memoryless, tool-free workers return JSON chosen from operator catalogs (8, 5 and 2 operators for the three designs).
  - **Guards:** schema, bounds and editable-cell checks; edits go to a checkpointed copy, with rollback on failure. Sign-off re-runs after every edit, so "a model can make a repair fail but cannot make a layout pass checks it fails".
  - **Planner contract:** the planner returns evidence, a hypothesis, a falsifier and ordered intents. Control returns to the planner on regression, stall, an inexpressible intent or a double refusal.
  - **Results over 182 blind runs:** the cheapest model fixed **1 of 11 alone and 16 of 17 under a flagship planner**. Still, the cheapest *verified* option on every task was a mid-tier model alone.
  - **Costs:** tool runs took 59–94% of wall time; input context was 81% of model spend, at a 22:1 input:output ratio.
  - **Controller:** a Bayesian per-task-class controller fixed 7 of 8 held-out tasks, at 15–40% of flagship spend on three tasks but 8% more overall.
  - **Reward hacking:** DRC-count shortcuts through fixed foundry cells show "legality must be part of the contract".
- **DRC-Aid** [P] ([2607.22761](https://arxiv.org/abs/2607.22761)). A rule engine turns Calibre violations into an edit menu; the LLM selects, with budgeted DFS, backtracking and a memory that prevents cycles.
  - It reached **92.5%** DRC-clean, LVS-equivalent repairs (about 98% violation reduction).
  - Comparisons under the same infrastructure: deterministic heuristic 83.3%, random 54.4%, **static prompting 6.6%**.
  - The LLM's advantage widens at six or more violations.
- **Other bounded-action systems:**
  - **EvoDRC** ([2607.20019](https://arxiv.org/abs/2607.20019)): bounded repair crops, a four-role workflow, and evolving layer-wise skill files. It is internally inconsistent (73.5% in the abstract vs 83.6% DRV reduction in the conclusion).
  - **SCALE** ([2607.21850](https://arxiv.org/abs/2607.21850)): layout geometry serialized to text, masked-polygon pretraining, and synthetic violation pairs that train a DRC-VLM.
  - **DRC-Coder** ([2412.05311](https://arxiv.org/abs/2412.05311)): rule text to checker code, F1 **1.000 vs 0.631**, in under 4 min per rule.
  - **Ho & Ren** (LAD 2024, [2406.06549](https://arxiv.org/abs/2406.06549)): the LLM writes cluster constraints for a cell-layout engine. Cells up to 19.4% smaller (4.65% on average), 100% LVS/DRC-clean, and 23.5% more clean layouts than prior work.
  - **AnalogMaster** ([2604.20916](https://arxiv.org/abs/2604.20916)): the LLM does netlist extraction and search setup; classical P&R does the layout. 92.9% Pass@1, 99.9% Pass@5.
  - **PANDA/AnAutomate** [PvS]: end-to-end analog flows (AnAutomate uses ALIGN layout and Calibre checks); "several hours vs several days".
  - **"Code, not canvas"** [PvS]: layout as code, diversity 12.009, DRC-legal.

### 3.2 LLM steering PCB placers

**PCBAgent** [P] (ASP-DAC'25, VER #13–14).
- **Placer:** an RL decision transformer on a 128×128 grid with masks for each of 4 rotations; step reward ΔHPWL; trajectory score 1000/HPWL + 0.01·NSLW; a prioritized buffer of hard-legal trajectories only.
- **Placement order:** chips first, then their attached parts clockwise.
- **LLM role:** an LLM agent maps requests and defects to tool calls. These reweight trajectory scores and re-run fine-tuning **only on violating components**. The LLM model, prompts and tools are unspecified.
- **Results:** HPWL 1.04× and NSLW 0.94× relative to manual; "90% of the quality of manual results"; +39.6% on requested wire categories in 2–3 rounds.
- **Baselines** had spacing-legality rates of **0** (MaskPlace, ChiPFormer, MILP).
- **Independent checks:** ModuPlace found the most vias for PCBAgent (94.4); OmniLayout measured RR 0.42.

**ModuPlace** [P] (DAC'26, VER #12, [PDF](https://yhhan.com/PDFs/ModuPlace_paper.pdf)).
- **Pipeline:**
  1. LLM Agent 1 builds a Hierarchical Modular Tree, splitting recursively until confidence passes a threshold, with RAG over guidelines and a netlist heterogeneous graph with sub-circuit matching.
  2. Agent 2 emits a Comprehensive Constraint Graph (CCG) per layer. Each edge carries an (x̂, ŷ) offset, a θ̂ rotation and a weight w.
  3. A hierarchical placer minimizes weighted deviation from the CCG plus parent-overlap and HPWL terms, then runs an overlap-free detailed placement.
- **Training:** Qwen-2.5-7B, SFT on **426 expert CCGs**; customized GRPO generating 36 CCGs in groups of 4; a GNN reward trained on pairwise expert rankings; a CCG-equivalence test.
- **Results on 11 boards** (35–97 parts), routed by PcbRouter and Freerouting:

  | Method | WL | Vias | IL | XT |
  |---|---|---|---|---|
  | **ModuPlace** | **1266.5** | **48.6** | **5.40** | **−41.83** |
  | PCBAgent | 1477.3 | 94.4 | 6.62 | −38.28 |
  | DeepPCB | 1484.6 | 48.8 | 7.81 | −39.99 |
  | NS-Place | 1490.2 | 71.5 | 6.89 | −36.25 |
  | SA-PCB | 1528.5 | 81.7 | 6.52 | −39.22 |

- **Ablations:** without SFT, WL +35.1% and vias +66.2%; without GRPO, +25.4% and +53.1%.
- **Zero-shot CCG generators:** GPT-4o 1756.8 WL / 84.6 vias; Claude-3.5 1707.5 / 92.1; Qwen-7B 1928.7 / 97.3.
- **Per-board caveat:** "outperforms all baselines" holds only on averages; baselines win several individual boards. No code, prompts or hyperparameters are released.

**Li, Peng, Huang, Wu, Zhu (DAC 2026)** [PvS] (VER #44, [2606.19795](https://arxiv.org/pdf/2606.19795)). This is a separate paper, *not* ModuPlace.
- **Pipeline:** multimodal serialization, topology-enriched retrieval, two grouping agents, group-aware global placement, then constraint-graph/MILP legalization.
- **Results** on 6 industrial boards routed by the same commercial router: routed WL/vias improve by **55%/73% over a commercial placer, 34%/26% over NS-Place and 15%/13% over Quilter**. This may be the strongest reported LLM-in-the-loop PCB placement result.

**Non-LLM PCB placers that matter as backends** (VER):
- **NS-Place** (ASP-DAC'22 Best Paper): Laplacian init, a net-separation objective, MILP legalization with relative-position constraints. Routed WL −10% vs manual on average (−25% peak); fails at about 20% whitespace.
- **Cypress** (ISPD'25): differentiable net crossing (Bézier intersection parameters through a bell function); Gumbel-Softmax orientation; two-sided density; MOTPE tuning on Freerouting routability. Routability up to 1.2× SA-PCB and 5.9× NS-Place; up to 492.3× faster.
- **HiePlace** (TCAD'26): 7.7× faster, −16% WL, −46% misaligned regions.
- **Chen et al. DAC'25:** power-vs-signal wire-area model plus QP legalizer; best academic placer in OmniLayout (RR 0.62, reference similarity 0.86).
- **Others:** Tsou DAC'24 (power-circuit anchor points); PCB-Migrator DATE'26 (offset constraint graph for resized boards); RL_PCB (TD3/SAC −17%/−21% WL vs SA on unseen circuits).

### 3.3 LLM steering IC placers (transferable patterns)

- **VeoPlace** (NeurIPS 2026 main conference; Harvard/Kempner + Google DeepMind, not MSR, VER #15–17).
  - **Loop:** each iteration runs 8 unguided rollouts, one VLM call returning 8 region suggestion sets, then 8 guided rollouts.
  - **Anchoring:** suggestions become a quadratic anchor in DREAMPlace. **λ_A = 0.01 is best; 0.1–1.0 over-constrains.**
  - **Prompt contract:** HISTORY SUMMARY (principles flagged "hypothesis") → STRATEGY (exactly one change, flagged "exploratory") → REGIONS (largest first).
  - **Context selection ("Top Stratified"):** K-means clustering of prior placements, rank-softmax over clusters (τ = 0.43), then the top C from the chosen cluster.
  - **Results:** ChiPFormer improves on 9 of 10 benchmarks (peak −32.2%); DREAMPlace gains are **0.5–4.4%** (VER).
  - **Models:** Gemini 3.6 Flash on the DREAMPlace track; Qwen3-VL 8B and 30B-A3B match Gemini.
  - **Cost:** about $7 per run; 2–7% overhead; about 62 s per VLM call.
- **MAGE** (UCSD, Claude Opus 4.6; VER #21–22).
  - Six phases: grouping into families of similar groups; flyline-render visual gate; **one reference placement per family, then transform-and-merge** to the others; a stateless independent auditor.
  - Cost: $220–509 per tournament.
  - **(VER):** the "+29.7% routed WL" is measured against the *commercial* placers. Against the human expert it is "comparable"; against Hier-RTLMP, −9.8% WL.
- **HyperPlace** [PvS]: an agent proposes *and explains* hyperparameters. Up to 22.24% better than DREAMPlace 3.0 under fences.
- **CHIP-MAP** [PvS]: agents exchange structured JSON; repairs 61.6% of TNS.
- **LLANA:** few-shot net-weight constraints for Bayesian optimization [S].
- **LayoutCopilot** (TCAD; VER #23):
  - command correctness 93.75% for multi-agent with instructions, vs 87.89% without instructions and 79.98% single-agent;
  - 11 commands;
  - abstract suggestions go to the designer for approval.

### 3.4 Code and objective evolution (offline improvement)

**Placement:**
- **EvoPlace** (TCAD 2026, GPT-4o, VER #18): about 1,000 candidates per component and per case on about 210 GPUs. **Generalized gains are only 0.509% (MMS) and 2.85% (ISPD2005).** *Conflict:* EDA's "HPWL −5–8%" refers to case-specific gains.
- **OrderPlace** (ICML 2026, Claude Sonnet 4.5, VER #19): macro HPWL −34.04% / −14.08%, with a three-stage proxy filter.
- **CoEvoP&R** (gpt-5.4, VER #20):
  - −16.9% routed WL and −36.7% congestion on ChiPBench;
  - a restricted objective API over RUDY and density maps;
  - an AST check plus a finite-value/autograd gate;
  - cost-tiered evaluation (A/B/C);
  - MAP-Elites with negative memory of failures;
  - **a free-form prompt interface underperforms the restricted one**.

**Routing and flow code:**
- GR-Evolve: −8.72% post-detailed-route WL ([2604.22234](https://arxiv.org/abs/2604.22234)).
- VPR-Evolve: WL up to −18.1% vs stock VPR, but only −2.2% vs hyperparameter tuning ([2607.24998](https://arxiv.org/abs/2607.24998)).
- FABO: −0.83% overall, −2.66% for nets with 30+ pins ([2608.30268](https://arxiv.org/abs/2608.30268)).
- GoalEvolve: Teacher/Student agents with stage attribution; TNS +30.67% ([2608.16733](https://arxiv.org/abs/2608.16733)).
- AlphaRoute: claims a 98.6% overflow cut; single group, treat with caution ([2607.19768](https://arxiv.org/abs/2607.19768)).
- Prim–Dijkstra theory work ([2607.17005](https://arxiv.org/abs/2607.17005)).
- AlphaEvolve: TPU Verilog change, also caught by downstream synthesis ([2506.13131](https://arxiv.org/abs/2506.13131)).

### 3.5 Step-wise LLM routing: PCBWorld in detail (VER §2.1)

**Stack.**
- L4 Gymnasium facade → L3 Python wrapper with 58 step APIs → L2 pybind11 → L1 KiCad 9.0.8.
- Runs as a separate GPLv3 process over a Unix socket.
- **Conflict:** the paper calls L1 "unmodified KiCad", but the repository contains modified KiCad files.

**Actions.**
- `net_select`, `start_route`, `make_line`, `make_via`, `finish` (to the nearest unconnected pad), `net_end`, plus an `idle` fallback.
- Routing modes: mark obstacles, shove, walk around.
- **Delete/rework APIs exist but were withheld** from agents.
- Candidates: pads, track ends, ratsnest targets and an 8-way 0.5 mm grid, capped at 64. The LLM may emit free coordinates under a regex.

**Prompt and parsing.** One `<think>…</think><action>…</action>` pair per turn; 256-token replies; T = 200 steps. Prompt guidance:
- complete connections, then avoid DRC, then minimise wirelength;
- vias ≥1 mm from any pad;
- never reach a target pad while on the wrong layer.

**Reward.**
- f_drv = 3·ln(1 + x/2) + Σ ln(1 + xᵢ/2), with λ_w = 0.002 and λ_v = 0.1.
- The DRC basis is 38 checks: 35 stock error-level checks plus DANGLING_VIA, DANGLING_TRACK and NET_CONFLICT.
- **Clean Pass** = full connectivity and 0 error-level DRVs on the best of 5 rollouts.

**Key results (Tab. 21):**

| Method | D2 CP / s | D3-A CP / Rout / DRV / s | D3-B CP / Rout |
|---|---|---|---|
| Freerouting 2.1.0 (`-mp 10`) | 1.00 / 2.69 | 0.80 / **0.91** / 0.86 / 7.09 | 0.78 / 1.00 |
| KRT | 1.00 / 0.82 | 0.74 / 0.94 / 2.38 / 0.65 | 0.20 / 0.86 |
| OrthoRoute (rules not enforced) | 0.01 / 2.54 | 0.02 / 0.53 / 99.7 / 2.20 | 0.00 / 0.44 |
| GPT-5.4 | 0.96 / 94.04 | 0.65 / 0.91 / 1.31 / 231.15 | 0.00 / 0.62 (865.83 s) |
| GPT-5.4-mini | 0.58 / 33.93 | 0.28 / 0.72 / 3.88 / 56.85 | 0.00 / 0.61 |
| GPT-5.4-nano | 0.55 / 63.39 | 0.30 / 0.73 / 3.84 / 100.76 | 0.00 / 0.59 |
| Qwen3.5-397B | 0.33 / 47.58 | 0.34 / 0.75 / 3.63 / 81.82 | 0.00 / 0.51 |
| PPO | 1.00 / 0.43 | 0.86 / 0.95 / 0.89 / 1.83 | 0.45 / 0.85 |
| PPO w/o finish | 1.00 / 0.88 | 0.94 / 0.99 / 0.21 / 3.05 | 0.42 / 0.87 |

**Slowdowns (VER #2–4).** The "0.43 s for routers" figure is PPO alone.
- On D2, GPT-5.4 is **219× slower than PPO but 35× slower than Freerouting**.
- On D3-A it is 126× slower than PPO, 33× slower than Freerouting and 356× slower than KRT.

**Tokens per episode** (GPT-5.4): about 107k on D2, **about 425k on D3-A** and **about 1.92M on D3-B**.

**Failure modes.**
- **The first `net_select` often decides success**, and agents rarely recover.
- Without delete actions, agents loop on reroutes.
- Errors map to DRC codes: via on pad, wrong-layer endpoint, cross-net contact, detours over the board edge, phantom waypoints.

**@1 vs @5.** GPT-5.4-mini falls from 0.58 to 0.20 CP on D2; PPO-terminal from 0.92 to 0.61.

### 3.6 LLM → MILP/CP formulation

- **OPT-Engine** ([2601.19924](https://arxiv.org/abs/2601.19924)): "automated formulation of constraints represents the primary bottleneck". Tools fix local arithmetic but not global constraints.
- **DCP-Bench-Open** ([2506.06052](https://arxiv.org/abs/2506.06052)): Python frameworks (CPMpy, OR-Tools) beat MiniZinc; sampling plus self-verification adds up to 35%, reaching about 90–91%. Models over-encode the example instance.
- **CSPLib wording study** ([2511.14334](https://arxiv.org/abs/2511.14334)): accuracy drops sharply under rewording.
- **Agentic constraint-model improvement** ([2608.08127](https://arxiv.org/abs/2608.08127)): beat the originals in 68.5% of cases, but was matched by best-of-5 with the same validators (101 vs 102.8 of 150).
- Optimization-modelling benchmarks have high error rates ([2508.10047](https://arxiv.org/abs/2508.10047)).
- MCP-Solver ([2501.00539](https://arxiv.org/abs/2501.00539)); OptiMUS [S].
- **Gap:** no LLM→MILP study exists for PCB placement. RAC's fixed relation schema sidesteps formulation.

### 3.7 Execution infrastructure, memory, multi-run consensus

- **Agentic RTL-to-GDS lessons** ([2607.17528](https://arxiv.org/abs/2607.17528)):
  - skills improve understanding of subtasks but not completion;
  - **Token ROI differs up to 141×** between agents with similar progress;
  - Tcl version and mode mismatches are a major failure source.
- **FluxEDA** ([2603.25243](https://arxiv.org/abs/2603.25243)): a stateful gateway with persistent tool instances and rollback.
- **Handoff survey** ([2606.19795](https://arxiv.org/abs/2606.19795)): 115 systems; harness mechanisms in 88, model-parameter optimization in 23, RL fine-tuning in only 3. It warns that generated checks can be "mutually consistent yet jointly wrong", and that gains are not comparable across unmatched backends.
- **Memory:**
  - MFM persistent multimodal memory raised CUABench-KiCad reward from **0.267 to 0.440** ([2610.22686](https://arxiv.org/abs/2610.22686));
  - the RF workflow kept agent-maintained markdown context;
  - kicad-agentic-mcp keeps task state server-side so it survives context compaction.
- **DRCY consensus:** k parallel runs; recurring findings are kept and singletons re-checked against the datasheet ([2603.15672](https://arxiv.org/abs/2603.15672)).

**Implications for our system**
- Loop: LLM proposes a relation bundle → solver realizes it → independent checkers → structured conflict and relaxation feedback.
- Repairs come from rule-engine menus, with DFS, backtracking and anti-cycle memory.
- Planning (net order, grouping) is an explicit coarse decision.
- Default to a mid-tier model; escalate on verified failure; keep a per-role cost ledger; keep observations compact, since input dominates cost.
- Rule out per-segment LLM routing on cost grounds: 425k–1.9M tokens per small or medium board.
- If a step router is ever built, fix PCBWorld's gaps: echo DRC with codes and positions, include zones, expose per-netclass rules, add rip-up actions, keep a longer history, and prefix-cache static state.
- Evolve placer objectives offline through a restricted, gradient-checked API, and plan cross-board generalization tests from the start.

---

## 4. Benchmarks, metrics and benchmark hygiene

**Benchmarks and resources:**
- PCB layout: OmniLayout, OmniRouting, PCBWorld D1–D3, RAC's 98 tasks.
- Understanding: PCB-Bench, PCB-QA, HWE-Bench, PCBSchemaGen/PCBBench, NetlistBench, BenchPCNP.
- PCBInnoBench (NeurIPS 2026, SJTU + Huawei): 372 tasks; 22.0% vs 7.3% Pass@1 with vs without an expert trajectory (VER #30).
- PCBSchemaGen (VER #33): v2 has 227 tasks over 22 domains, and Gemma-4-31B passes 81.3%. The "~300 tokens per IC" figure is from v2; the 16k-token baseline is from v1. Author-slide numbers (86.3/84.0/61.0%) were not found in the paper.
- **EEBench** ([methodology](https://eebench.org/methodology.html)): **excludes layout**.
  - Score = 0.65 × technical + 0.35 × cost-efficiency; grading is deterministic (builds, SPICE at worst-case corners, BOM checks).
  - 1 Sept 2026: Claude Opus 5 61.6%.
  - **Conflict:** GPT-6 Astra's reported 69.3 ±10.7 vs a claim that no result existed. Treat as provisional.
  - A later mirror shows Opus 5.5 at 75.0% [snip].

**Vendor layout numbers [V]:**
- Cherry Blossom, 40 boards: first-pass yield 94% → 97%, design time −54% ([blog](https://www.trycherryblossom.com/blog/gpt-6-astra-pcb-design)).
- Quilter Project Speedrun: 428 h manual quote vs 27 h automated plus 38.5 h cleanup ([blog](https://www.quilter.ai/blog/cleaning-up-an-ai-designed-computer)).
- DeepPCB vs Quilter on 3 boards (98/290/414 airwires): completion 97.3% vs 87.7%; Quilter used 44% more vias; first result in 1–2 min vs 15–20 min ([blog](https://deeppcb.ai/deeppcb-vs-quilter-open-source-routing-compared-2026/)). A "414-net" figure seen elsewhere is derivative of this.
- An Altium Academy video reported **168 DRC violations for the AI vs 0 for the human**. This refers to that video, not to GPT-6 Astra or StationX; EDA's attribution is corrected by UX.

**Hygiene rules:**
- Report @1 and @5, plus seed means for stochastic routers.
- State router versions and settings. Freerouting serves as the de facto oracle (NS-Place, Cypress v1.9.0, ModuPlace, OmniLayout), but configurations differ (PCBWorld: 2.1.0, `-mp 10`, 4 GiB), so cross-paper numbers are not comparable.
- State the potential function: PCBWorld's repository default differs from the paper.
- Use strong baselines. TILOS showed SA beating AlphaChip-style CT 17/17 on proxy cost, and noted "weak or outdated baselines may lead to misleading conclusions".
- Harness effects are large: ARC-AGI-3 scored 62.7% vs 99.9% depending on undisclosed API settings ([zerowithdot](https://zerowithdot.com/blog/gpt-6-astra-impact-on-cad/)).
- Metrics decide whether "learned beats human". Lim 2026's TEWL ignores overlaps.
- Proxy cost correlates weakly with post-route PPA (TILOS).

**Implications for our system**
- Build our own layout scorecard benchmark against human reference boards. Placement metrics: OmniLayout-style RR and PRWL plus pad-overlap and out-of-bounds rates; targets to beat are Chen DAC'25 and Quilter (academic placers are a low bar). Routing: PCBWorld D3-A/B with a matched @k and seed protocol.
- Scorecard fields: unrouted count; DRC by severity, *including disabled categories*; parity; footprint–datasheet consistency; loop area; decap distance; ampacity; via count; tokens, cost and latency per verified board.
- Make legality part of acceptance, to block metric gaming.

---

## 5. Design-understanding pipeline: netlist → blocks → net roles → constraints → KiCad carriers

### 5.1 Recognizing blocks

**Exact templates.**
- ALIGN uses NetworkX VF2 with pin-label edge matching and deterministic sorting; overlapping matches are skipped and a constraint-satisfiability check is applied.
- GANA uses VF2 for primitives, roughly O(n) because library subgraphs have small diameter.
- **PCBSchemaGen v2**: VF2 against 5 board motifs (half-bridge, synchronous buck, three-phase inverter, Pierce oscillator, Pi filter), with three relaxations:
  - only key components (IC, MOSFET, inductor) must match exactly;
  - a cheap boolean prefilter runs before VF2;
  - passive terminals on a shared net are grouped.

  Source: [2602.00510v2](https://arxiv.org/abs/2602.00510).
- HiLSD searches for symmetry only inside matched instances.

**GNNs (analog IC):**
- **GANA:** GCN alone 90.5% (OTA bias), 83.64% (RF), 79.8% (phased array). **Post-processing with port semantics reaches 100% on all 275 test cases** ([DATE 2020](https://www.date-conference.com/proceedings-archive/2020/pdf/0921.pdf)).
- R-SAGE: macro F1 0.864 vs 0.841 for VF2. MCE-HGCN: F1 0.917 on matching constraints.

**Board level:**
- **BenchPCNP** ([PMC13046837](https://pmc.ncbi.nlm.nih.gov/articles/PMC13046837/)) is the only labelled board dataset: 50 circuits, 54 module labels, CC BY 4.0. Hypergraph GNNs reach about 79% accuracy (HyperResGCN 79.07 / F1 70.77), against about 68% for GraphSAGE; large power and ground nets hurt pairwise graphs.
- **Plettenberg** ([2506.10577](https://arxiv.org/abs/2506.10577)): node names alone carry most of the decoupling signal; the decap count is within ±1 in about 70% of cases.

**Production rules [doc]:**
- **Quilter:**
  - crystal = refdes X/Y with both pins on the same parent;
  - converter = U whose output connects to an L, with at least 2 external caps;
  - bypass-cap parent pin chosen by: explicit wire, then voltage-named pin, then equal split.
- **kicad-happy:** 60+ deterministic detectors on a harness of about 5,800 projects, with no accuracy figure.

**LLM role.** Write detector code (GENIE-ASI pattern), or query a deterministic graph through tools (PCB-QA pattern). Never trace raw netlist text, and never form stage-level groups directly (HL3 F1 0.31).

### 5.2 Classifying nets

- **KiCad diff pairs** are suffix-only (`+`/`-` or `P`/`N`, not mixable). `XTAL_P`/`XTAL_N` can trigger diff-pair rules by accident.
- **KiCad net-class patterns** accept wildcards and regex; a net can belong to several classes, and the highest-priority class with the field set wins.
- **Quilter:**
  - pairs need a diff-pair class *and* a suffix (+/-, A/B, P/M, P/N, t/c); names starting with V are excluded;
  - power-net defaults: 200 mA below 3 V, 500 mA above; ΔT > 20 °C flagged;
  - single-ended impedance is manual (width within 5%);
  - undetected nets are treated as "generic low-speed".
- **Flux:** 7 inferred, editable priority buckets (High Speed, Analog, Power, Medium Speed, Low Speed, Uncertain, Ground), routed in that order.
- **kicad-happy:** keyword classes.
- **PCBSchemaGen:** a 32-role pin ontology (including kelvin source, and buck vin/gnd/sw/fb/en/boot) and 4 predicate templates.
- **IBIS 7.2** ([spec](https://ibis.org/ver7.2/ver7_2.pdf)):
  - `[Pin]` with reserved POWER/GND/NC model names;
  - **`[Diff Pin]` gives authoritative pairing**;
  - `Model_type` gives the buffer type;
  - **`[Ramp]` gives 20–80% edge rates**.

  KiCad already loads IBIS for simulation. **No tool uses IBIS to classify nets for layout: an open opportunity.**

### 5.3 Per-part "layout card" sources

- **Distributor APIs** give identity, package and loose parametrics: Nexar specs, DigiKey v4 `Parameters[]`, LCSC. The community jlcsearch API dropped its `extra` block in 2026-09.
- **JEDEC JEP30 PartModel:** Flux imports and exports it and can generate it from datasheets with AI.
- **CELUS CUBO:** specs, BOM, an app-note schematic and typed ports, within a 4-level function hierarchy.
- **Flux Knowledge Base:** entries with trigger and scope.
- **kicad-happy `DatasheetFacts`:** a typed cache.
- **PCBSchemaGen KG:** `kg.json`.
- **None of these carries layout constraints.**

### 5.4 KiCad-native intent carriers [doc]

**KiCad 9:**
- directive labels;
- **implicit net classes**: no settings, but usable in DRC queries;
- several Net Class fields per net;
- rule areas that assign classes;
- a `Component Class` symbol field;
- DRC functions `hasNetclass`, `hasComponentClass` (matches footprints only) and `memberOfFootprint('${Class:X}')`;
- **Generate Placement Rule Areas** per sheet or component class, sized to enclose the footprints;
- Repeat Layout.

**KiCad 10:** PCB design blocks, tuning profiles, a graphical DRC editor, variants, and pin/gate swap.

**Other precedents:**
- kicad-happy emits a `design_intent` object and **asks the user when confidence is below 0.5**.
- copperhead: "nothing starts without a spec".
- atopile reuses layouts by hierarchical address.

### 5.5 Recipes: function → constraints + checks

- **Quilter PRCs** pair each constraint with its checks:
  - bypass, crystal and converter: Pin Distance (example passing range 0–1 cm; fails at 1.11 cm), Trace Path Length, Layer Switch Count, Ground Plane Overlap;
  - diff pairs: Uncoupled Spacing and Length Mismatch;
  - power: Overheated Length.
- **Vendor numbers (TI):**
  - AN-1149 (SNVA021C): ≥15 mil per ampere; **1 via per 200 mA**.
  - SLYT614: **1 via per ampere** (**conflicts** with AN-1149); place Cin first.
  - SNVA803: a lateral loop of about 20 mm² (>1 nH) vs a vertical loop of 2 mm².
  - TI regulator datasheets are qualitative ("as close as possible"). Exceptions: TPS62933's >10-mil FB trace; Kelvin FB ground on TPS54202/TPS563200; no thermal via under the TPS7A20 DQN pad.
- **MCU guides are numeric:**
  - Microchip: ≤6 mm trace to a decap that sits through a via.
  - Espressif ESP32-S3: crystal ≥2.0 mm from the clock pin; 3.3 V trace ≥25 mil; ≥15 mm antenna clearance; SDIO ±50 mil.
- **kicad-happy EMC rules:** caps within 10 mm for decap checks; inductor ≥15 mm from sensitive analog; skew limits of 25 ps (USB HS), 5 ps (PCIe), 50 ps (Ethernet) and 20 ps (HDMI).
- **Generators:** TI WEBENCH PCB Export (no KiCad export found), Ultra Librarian/TDK reference design in 8 formats including KiCad, JITX, atopile, Flux modules ("Auto Layout Gravity" 0–1).

### 5.6 Proposed 9-stage pipeline (NET §7)

Stages are labelled D = deterministic code, L = LLM, U = user.
1. Ingest (D): compact JSON plus query tools.
2. Part resolution (D; L proposes when the MPN is missing).
3. Layout card (staged L; D validators; audited tool calls).
4. Net roles (D layered classifier; L for leftovers).
5. Blocks (D VF2 and rules; L writes detectors).
6. Recipes → constraints with attached checks.
7. User validation (U).
8. Compile to net classes, component classes, rule areas, `.kicad_dru` and a placer JSON.
9. Verify: DRC, constraint checks, structural LVS.

**Implications for our system**
- Recognition order: rules and templates first, with an LLM-written detector for the long tail.
- Net-role precedence: explicit intent > IBIS/datasheet > topology > names > LLM, with evidence recorded at each layer.
- Propose renames when a detected pair uses non-KiCad suffixes.
- Every constraint carries the check that verifies it, and the same predicate drives the placer objective and the acceptance test.
- Compile semantic tags to implicit net classes and `Component Class` fields, and seed placement regions with KiCad's generated rule areas.
- Where vendor numbers conflict, use the conservative value and show both citations.
- Replay a known-good sub-layout when a block matches exactly.

---

## 6. Datasheet and app-note extraction

**Reliable when staged and grounded:**
- Chunked knowledge-graph extraction with provenance: **98.8% vs 76.1% faithful** for one-shot. The pipeline covers 83.6% of the baseline's properties; the baseline covers only 10.5% of its. One-shot extraction omits specifications even when the document fits in context ([2610.12762](https://arxiv.org/abs/2610.12762)).
- Compatibility verification with deterministic scripts: **97.5%** accuracy with **8.6× less context** ([2608.25217](https://arxiv.org/abs/2608.25217)).
- D2S-FLOW: EM 0.86 / F1 0.92, with 38% fewer tokens ([2502.16540](https://arxiv.org/abs/2502.16540)).
- SpecMap: −84% tokens ([2601.11688](https://arxiv.org/abs/2601.11688)).
- HWE-Bench preprocessing: MinerU, then pin JSON.

**Unreliable when naive:**
- GDP.pdf: the best of 17 models passes **30.7%**. Recurring errors are misaligned tables, misread charts, skipped footnotes and superseding amendments ([2607.11192](https://arxiv.org/abs/2607.11192)).
- **"Fidelity Is Not Enough"** ([2608.28439](https://arxiv.org/abs/2608.28439)):
  - one model passed a fidelity check **without opening the datasheet**, because a structured-output constraint had disabled its tools;
  - dispatch-level logging caught all 50 planted faults, with 0 false flags on 207 clean runs;
  - physical measurement could verify only 2 of 37 claims.
- ElecSafety: unreliable near boundaries ([2610.06905](https://arxiv.org/abs/2610.06905)).

**Tools in use:**
- **DRCY** (production, no accuracy figures). The critic scores each extraction: pin-function coverage 40%, features 25%, application info 20%, typical circuits 15%. Up to 5 sources are tried, results cached for 7 days, and k runs reconciled by consensus. A strong model reviews; a weak model extracts.
- **kicad-happy datasheet skill:**
  - TOC-guided page selection (8–15 pages);
  - typed `SpecValue{min, typ, max, unit, condition, evidence}`;
  - PDF-hash staleness checks;
  - "null, never guess";
  - it **skips app-note and "recommended for X" prose**.
- **DocEDA:** datasheet layout analysis plus chain-of-thought extraction.
- **LLM4-IC8K/ICGeo8K:** 8,608 samples; split into pin count, centres and dimensions; trained synthetic first, then real.

**Parsers** (OmniDocBench v1.6 table TEDS): MinerU2.5-Pro **93.42**; Gemini 3 Flash 89.29; Gemini 3 Pro 89.15; MinerU-2.5 87.88; GPT-5.2 82.95; Marker **65.77**. The benchmark is not datasheet-specific.

**Gap.** No system or benchmark extracts *layout* guidelines from datasheets, and no work parses EVM reference layouts into relations.

**Implications for our system**
- Use two schemas:
  - electrical tables: staged, with provenance;
  - layout guidance: typed predicates that keep qualitative strength ("as close as possible" → `weight=high, bound=null`). Never invent millimetres.
- Check MCU and SoC hardware design guides first; that is where the numbers live.
- Reliability controls:
  - page and sentence evidence on every value;
  - a tool-call audit that rejects runs which never read the source;
  - chunked multi-pass extraction;
  - deterministic computation of derived numbers;
  - multi-run consensus for safety-critical rules;
  - PDF-hash and revision pinning.
- Treat figures as low-confidence topology hints. Map extracted statements to the same closed vocabulary as the relation API, and attach a generated checker to each (DRC-Coder and weak-verifier pattern; weak verifiers reached 7× F1 over an LLM judge, [2606.05268](https://arxiv.org/abs/2606.05268)).

---

## 7. Data: corpora, retrieval, priors, training recipes, licensing

### 7.1 Supply and quality (DATA Q1)

**Raw supply:**
- open-schematics: 87,931 rows, 316.8 GB, CC-BY-4.0 tag over mixed-licence sources, no per-row licence ([HF](https://huggingface.co/datasets/bshada/open-schematics)).
- kicad-happy catalog [M]: 5,856 repos, 18,679 PCB files; 63% 2-layer; median 65 parts; KiCad 9 in only 29 repos and KiCad 10 in 21 ([catalog](https://github.com/aklofas/kicad-happy-testharness/blob/main/reference/repo_catalog.json)).
- OSHWA: 3,452 certified projects.

**PCBench census [M]:**
- 1,183 boards from 842 repos (164 retrieved in 2023-04 and 1,018 in 2023-08), which resolves "164 vs 679".
- **62.1% have no clear licence**; 89% are 2-layer; **only 23 are KiCad 6+**.
- Boards have no project file, so they carry default rules.
- PCBWorld's own pool count is 1,182 → 679 (minor discrepancy with 1,183).
- **(VER #7):** D3-A has 100 boards (≤31 pads), D3-B 287 (≤100 pads), D3-C 292 (2–8 layers, not evaluated).

**circuit-skills collector [3P]** ([manifest](https://github.com/punkfab/circuit-skills/blob/main/evals/corpus/manifest.json)):
- 235 boards from 423 candidate repos;
- 46% reciprocal and 54% permissive licences;
- **only 33% are DRC-clean under their own rules** (median 4 violations, max 938).

**Other measurements:**
- kicad-tools census: usable boards rose from 36% to 73% after a legacy `(module …)` parser fix. Lessons: a pour counts as copper, and each board's own rules must be adopted.
- Licence spot-check of 54 random kicad-happy repos [M]: **41% have no licence file**.
- Other sets:
  - SchGen: 2,105 schematics (CC BY-SA);
  - CELUS GNN sets: 2,396 / 849 / 944;
  - Ohmatic: 1,000 schematics;
  - mascarade: 79.7% LLM-generated;
  - R3SET: 71% Hit@1 [S];
  - KiCad 9+ corpora: 98 permissive / 209 copyleft.

**Expected yield.** Low thousands of licence-clean, fully routed boards; a few hundred that are also DRC-clean or have 4+ layers.

### 7.2 Retrieval and reuse (DATA Q2)

- **NEMESIS:** similarity = 0.6 × (2-iteration WL-hash Jaccard) + 0.4 × (motif cosine). The database grows only through verified updates.
- Other structural tools: GNN region matching; CROP's retrieval of similar designs to seed parameters (−9.9% power); CellE and gSpan motif mining.
- **Wu TCAD'15:** maximum-weight clique selects overlapping reusable patterns; device reuse is 73.33% with a diff-amp only, 86.67% with an OTA only, and 100% with both.
- ISPD'18 extracts symmetry and alignment constraints from existing placements (−7.6% area).
- PCB-Migrator; GenLeaf's layout embedding (MSE 34.0% and 35.9% lower than Circuit GNN and DeepLayout).
- **Hint study [3P]** (52 boards, [hints_study.md](https://github.com/punkfab/circuit-skills/blob/main/evals/corpus/hints_study.md)): clean-route rate was **0.63 for the designer's placement vs 0.15 with no hints**. Coarse anchor, big-part and "near" hints gave only **0.19–0.21**, even though big parts moved from 26% to about 11–12% of the board diagonal from their designer positions. **Fine-grained relative geometry is what transfers.**

### 7.3 Imitation and measured priors (DATA Q3)

**Imitation learning:**
- GeniusRoute: 168/128/256 labelled samples plus 6,360 unlabelled; competitive with manual; later called data-starved and performance-blind (PARoute).
- ChiPFormer's "expert" data is 500 MaskPlace placements per circuit, i.e. optimizer output.
- **DevFormer:** with **100 GA samples it beat baselines trained on 2,000**, thanks to symmetry augmentation; it needed 26 decaps where GA needed 40 (94.2% vs 93.5% noise reduction).
- Lim 2026: RL beats human TEWL on simple subcircuits, but TEWL misses overlaps.

**Score study [3P]** (64 boards; clean-route rate):

| Placement | Clean route |
|---|---|
| Designer | **0.56** |
| swap25 | 0.39 |
| swap100 | 0.31 |
| Annealer | 0.12 |
| tracemaker-place | 0.16 |

The 0.63 (hint study) and 0.56 (score study) designer rates come from different board subsets. Swapping interchangeable parts alone costs a lot, so assignment within groups matters.

**Net order.** A hand-designed crossing-aware order did not help completion and worsened vias. Human routing order is not stored in board files.

**Measured priors [M]** (128 permissive boards):
- **Decaps (1 nF–1 µF), n = 809:**
  - median 3.29 mm, p90 15.1;
  - only **17% within 2 mm**, 44% within 3 mm;
  - 0402 median **2.51 mm** (95% same side);
  - p90 is 7.7 mm on 4-layer boards vs **26.0 mm** on 2-layer boards;
  - boards whose designer routing is DRC-clean have a tighter p90 (7.7 vs 17.7 mm);
  - GitHub stars are irrelevant.
- **Bulk caps:** median 5.33 mm.
- **Routing style:** 89% of boards have a GND zone; signal width 0.25 mm, power 0.40 mm; power/signal ratio **1.88**.

### 7.4 Synthetic data and fine-tuning recipes (DATA Q4–Q5)

**Pipelines that manufacture verified supervision:**
- **CodeV-R1:** 150K samples → 87K equivalence-checked SFT samples (Rouge-L > 0.5 decontamination) → 3.1K hard RL samples. Rule-based testbenches gave 96.1% fewer false negatives than LLM-generated ones. CodeV-R1-7B scores 68.6% on VerilogEval v2.
- **GenLeaf:** Bayesian optimization reverse-engineers expert layouts into "golden scripts". Qwen3-14B with GRPO reaches 0.52× tracks vs experts.
- **FOARL:** feasibility reward R_f = ω0·ζ + Σ ωi·cᵢ; optimality reward α/(1 + M_o); Best-of-N at inference. "SFT alone leads to over-greedy behavior". GPT-4o and Claude 3.5 reach only about 50% feasibility on CO problems under 30 nodes.
- **OptiScene:** about 17K scenes, DPO negatives made by injecting violations.
- **kicad-tools jitter:** σ calibrated to a 20–60% route-pass rate (a flat σ = 6 mm gave 0%); GroupKFold by board; negative controls. Out-of-fold AUC 0.919, but on only 131 samples.

**Representation results:**
- SchGen: 82% vs 32.5% (§2.5).
- LaMAGIC: adjacency-matrix formulation up to 96%.
- ACDC: direct LLM placement of analog devices is unstable.

**Reward recipes:**
- **VeriReason:** 2.0 if the testbench passes; 0.1 + AST score if it only parses; 0 otherwise. Prompts kept if their group mean reward is in [0.3, 1.8] with variance ≥ 0.1.
- **VeriPrefer:** DPO, because reward-based RL invites hacking.
- **3D-Layout-R1:** +15% IoU and −25% centre error.
- **SR-ReaL:** blended cold-start data is crucial for stable RL.
- **AesthetiQ:** +17% / +16%.

### 7.5 Learned vs rules (DATA Q6)

- **kicad-tools:** a learned ranker did **not** beat HPWL (0.743 vs 0.749, falling to 0.603 when perturbation size is controlled; perturbation σ alone ranks 0.739 of pairs). The project adopted a bounded real route as its gate. Soft-FOM weights reached 0.875 holdout rank consistency.
- **circuit-skills:** a combined logistic reached **0.79**, against ≤0.72 for any single measure; decap_mm carries weight +1.24. An earlier self-report of 0.89 conflicts with the committed file.
- **DeepPCB:** "If you haven't explicitly specified a constraint, the model won't respect it." It also warns that simulator-legal but EDA-illegal patterns get learned, and that "novel" strategies may be reward loopholes.

### 7.6 Contamination, licensing, bias (DATA Q7)

- **Contamination:** VeriContaminated found **near-100% contamination** for GPT-3.5 and GPT-4o on VerilogEval and RTLLM ([2503.13572](https://arxiv.org/abs/2503.13572)).
- **Licensing:**
  - CERN-OHL-S §3.2: "Including Covered Source in a larger work is modifying the Covered Source", so copying a reciprocal fragment's geometry plausibly triggers reciprocity. §2.4 preserves fair use.
  - KiCad 9+ corpus split: CC-BY-SA-4.0 is one-way compatible to GPLv3; the dataset author asserts trained models carry GPL obligations (their interpretation).
  - The Stack: a permissive-only subset matched full performance, and near-dedup helped.
  - PCB layout copyright: Taiwan treats a layout as a protectable graphical work; Singapore litigated PCB artwork; the US SCPA covers chips only.
- **Tiers:**

  | Tier | Licences | Uses |
  |---|---|---|
  | A | permissive | training and geometry-copying retrieval |
  | B | reciprocal | evaluation, plus attributed retrieval with a derivative warning |
  | C | none, NC, ND | private evaluation only |

- **Bias:** keyboards and ESP32 boards dominate; RF, precision analog and complex power are under-represented.

**Implications for our system**
- Corpus = pinned pointers plus SHA-256, payloads outside the repo; licence tiers and an opt-out list.
- Ship priors and retrieval first (no training). Then: DevFormer-style pose/assignment model → round-trip-verified constraint-graph SFT (7–20B, anchor-relative DSL) → GRPO with tiered rewards → DPO if hacking appears. The router is the label oracle throughout.
- Evaluate on time- and cluster-split boards against designer, swap and auto baselines, with a rules-vs-learned A/B.
- Condition priors on package, layer count and board class; prefer facts over verbatim geometry.
- Our data licence (CDLA-Permissive-2.0) means only tier-A sources can feed redistributed data products.

---

## 8. Field failure modes and reliability engineering

### 8.1 Case studies

- **A6M-Zero, Fable 5** [A] ([blog](https://a6mzero.com/posts/this-pcb-is-brought-to-you-by-fable-5/)):
  - first pass: 65 footprints, 54 nets, 118 unconnected, 65 DRC errors;
  - a W25Q128JVS SOIC-8-wide package was put on SOP-8 pads, and the model insisted the package existed;
  - Freerouting plateaued with 49 connections unrouted, while KiCadRoutingTools routed all of them in 1.25 s;
  - the 4-layer board worked on first plug-in;
  - the author: "beautiful placement… horrendous tracks".
- **tinycomputers** [A]:
  - 314/314 nets after the LLM's placement insight;
  - 121 false-positive DRC flags at same-net junctions took about 6 h; the fab's DFM found the real issues;
  - a 5-copper-layer save bug, where the model "happily kept trying to fix it";
  - about 18 h in total;
  - verdict: "a competent junior collaborator… no physical intuition".
- **JLCPCB, KiCad MCP** [V/A]: 7 issues, each caught by a check.
  - Auto-layout stacked all LM358 units on top of each other.
  - A label collision shorted ISENSE to ISET, and ERC only warned.
  - The FB trace ran beside the SW node.
  - A placement batch ran twice.
- **JLCPCB, EasyEDA** [V/A]: read-back found **6 missing GND connections behind API "success"**; the DRC API returns counts only.
- **GPT-6 Astra (JLCPCB):**
  - 46 parity issues;
  - 9 DRC/ERC categories ignored;
  - **the routed layout was reused from an earlier task**;
  - in EasyEDA, same-name `C0603` footprints aliased and produced 50 pad mismatches over 120 pads.
- **NextPCB:** about 12 min via DSN → Freerouting → SES, against 3 segments in an hour GUI-only. "Calling an autorouter is not the same as becoming one."
- **Tindie:** 9 unrouted nets; "well over half" of initial-design time saved; today's workflow is "open-loop".
- **StationX:** "keep the AI's inferences labelled as inferences".
- **KiCad Agentic MCP:** coordinates differed between two runs.
- **haohao:** about 10,000 zigzag segments that still passed DRC, reduced to about 600; a 1:1 paper check found a blocked USB port, a wrong fuse pitch and a duplicate terminal block, too late.
- **Gato513:** validated to 63 footprints; failed on the 437-footprint HackRF.

### 8.2 nexatech kicad-agent-toolkit

This is the best large-board evidence: a dense 6-layer board with about 370 footprints and 1,700 pads reached a DRC-clean release, with over 100 catalogued failures ([lessons](https://raw.githubusercontent.com/nexatech-ltd/kicad-agent-toolkit/main/docs/lessons-learned.md)).

**State and API traps:**
- pad angles are absolute (201 of 1,763 pads were wrong, "and the gate still passed");
- Flip is a Y mirror plus 180°;
- `SaveBoard` silently changed a via's net.

**Routing:**
- **per-net monotone acceptance**: 256 → 226 unrouted over 10 unattended rounds;
- hiding vias made Freerouting 6× faster but produced 149 shorts;
- a maze router beat Freerouting on the last breaks;
- read "no path" by cell count: small means a locked pad, huge means a blocked corridor.

**Placement:**
- +10 mm of board gave *more* breaks (136 vs 118);
- exact-rule search found 6,254 positions where a simplified search found none;
- `declash` fixed one overlap and created 59 new violations.

**Verification:**
- **"A check that didn't run reports zero"**;
- **"A write that didn't happen reports success"** (a `0.15` vs `0.1500` string mismatch);
- gate logs need input fingerprints;
- F8 found errors that ERC, DRC and parity missed.

**Core lesson:** "Learning isn't the bottleneck… Formalise the moves… as deterministic tools."

### 8.3 Failure taxonomy (MCP builders [G] and reports)

- **Rotation and coordinate math:** the transpose rotation matrix; stale pad angles; local- vs board-coordinate keepouts; LLM inverse-rotation errors on labels.
- **Data loss:** rotating through kicad-python dropped 3D models.
- **Checks that disagree with KiCad:** AABB courtyards; **a scorer that read the saved file while KiCad held a live ~4.0 mm² overlap**; `check_clearance` measured anchor distance.
- **Fab-rule gaps:** Freerouting's 0.2 mm default clearance; necking to 0.15 mm (22 DRC errors); `-mt 1` needed; `::1` pad suffixes let traces through mounting holes.
- **Loops:** an autofix that never recognized the "unconnected" category; unbounded fixes (a $10 cap stopped a $500 bill).
- **GUI and API gotchas:** a modal dialog blocks the API; a second KiCad window steals it; 30 s timeouts.
- **Unsafe automation:** a force-directed refiner scrambled parts; decap guessing was removed in favour of exact references.
- **Invisible failures:** package variants, footprint aliasing, ratings, muted rule categories.

### 8.4 Reliability-producing tool designs

- **CopperMCP:** "AI may interpret constraints and propose net ordering, corridors, cost weights, and repairs. Deterministic code owns geometry…" It uses immutable, revision-bound candidates and an apply token that no model can mint.
- **CopperLoop:** propose → gate → accept; one commit per change; kicad-cli "is the only truth"; a change stays only if counts don't worsen.
- **kicad-agentic-mcp:** compile-and-refuse; grid-snapped coordinates; validator findings with stable ids; server-side task state.
- **kicad-mcp-pro:** a read-only default profile.
- **KiCadRoutingTools:** the Claude plan becomes an editable checklist that replays as JSON with no LLM call.
- **Adom audit skill:** reads silenced rules; checks ERC-blind bugs.
- **Commercial tools:**
  - Flux explains why each issue was flagged; stops when search is unlikely to improve; lists prep steps.
  - Quilter produces "dozens to hundreds of ranked candidates" and treats placed copper as "solved".
  - Diode's Registry holds validated layout fragments; model proposals arrive as reviewable diffs; its reviewer rule is "no evidence, no report".
  - tscircuit: placement, then `tsci check placement`, then a PNG check, then routing. Its Sequential Optimal Packing method is legible, and constraints are "hardened" by LLM loops.

**Implications for our system** (full list in the inventory, §11)
- Engines own geometry; KiCad and the fab own the verdict, judged on the live board.
- Read back and diff every write; "clean" reports list disabled checks and carry input fingerprints.
- Refuse rather than guess; one native commit per step; human-only apply.
- Per-net monotone acceptance, prune-to-DRC writes, a deterministic move library with diagnostics, and loop budgets with escalation.
- Semantic checks beyond DRC; a placement and mechanical gate before routing; lock critical copper, then autoroute.

---

## 9. Human–AI UX and explaining "the why"

### 9.1 Evidence from HCI

- **Horvitz** (CHI '99): 12 principles. Principle 8 is "doing less but doing it correctly" under uncertainty; principle 5 uses dialog only for key uncertainties ([PDF](https://www.erichorvitz.com/chi99horvitz.pdf)).
- **Amershi** (CHI 2019): 18 guidelines tested with 49 practitioners. Most relevant: G2 (make clear how well the system can do), G10 (scope when in doubt), **G11 (make clear why)**, G15 (granular feedback), G17 (global controls).
- **Alternatives:**
  - Sketchplore: local and radical alternatives without overriding the designer.
  - Dream Lens: 16,800 designs filtered to 1,242; "engineer" vs "artist" users; outliers were the most interesting; "more like this".
  - Parallel prototyping beats serial iteration; Juxtapose; Sentient Sketchbook.
- **Contrastive explanation:**
  - Krarup: of 168 user questions about plans, **about 90% were contrastive**. Compiling each question into a constraint and re-solving covered 89.8% ([2103.15575](https://arxiv.org/pdf/2103.15575)).
  - RADAR-X; inverse-CP counterfactuals (Korikov & Beck).
  - OptiChat: solver function calls to avoid hallucinated numbers.
- **The explanation paradox:**
  - Bansal: explanations raise acceptance whether or not the AI is right. An adaptive design shows the top two alternatives only at low confidence.
  - Vasconcelos (N = 731): explanations reduce overreliance only when they lower the cost of verifying.
  - Buçinca (N = 199): cognitive forcing works but is disliked.
  - Zhang/Cagan: AI helped low-performing design teams and **always hurt high-performing ones**.
- **Generative design:**
  - Gmeiner (CHI '23, 14 designers): users can't tell intended features from glitches, can't communicate goals, and struggle to specify everything upfront.
  - ProCAD: asking clarifying questions only when needed cut invalid outputs from 4.8% to 0.9% and Chamfer distance by 79.9%.
  - CADialogue: 95.71% task success with human-in-the-loop refinement.
- **Design rationale:**
  - Karsenty: captured rationale answered only 41% of designers' questions.
  - IBIS/QOC failed on capture effort and retrieval.
  - LLM-drafted rationale: **precision 0.27, recall 0.63–0.72**. 64–69% of extra arguments were helpful and 1.6–3.2% misleading ([2504.20781](https://arxiv.org/abs/2504.20781)).

### 9.2 Designer demand

- **Weidmuller/EETech survey** of 400 engineers [V]:
  - 91% have used AI in PCB design;
  - 75% see it as an acceleration layer within existing workflows;
  - the top wish is **real-time error detection**.
- General engineers: 86% use AI but only 6% fully trust it.
- **Concerns:**
  - autorouter distrust ("~90% then weeks of rip-up");
  - configuration overhead;
  - "faster than typing the prompt";
  - house style ("what looks right varies by company, by team, sometimes by individual reviewer");
  - the opacity of RL engines (DeepPCB);
  - skill atrophy;
  - IP (Quilter offers in-customer-cloud deployment).
- High-speed, RF, HDI/BGA and novel analog work stays with humans.

### 9.3 Intent capture in EDA systems (EDA §5)

- **RAC:** repair "operates on intent instead of geometry".
- **"Who Plans":** each diagnosis carries evidence, hypothesis and falsifier; each intent carries target, mechanism, operators, scope and expected effect. Prompts are stored before each call, and a per-role ledger is kept.
- **Design as code** regenerates deterministically.
- **MLLMA:** a "Design Suggestion Deck" for congestion (SOTA on CircuitNet).
- **HyperPlace:** explained hyperparameter proposals.
- **GoalEvolve:** mechanism memory of local effects, optimization debt and downstream retention.
- **Handoff survey:** residual risk should travel with each handoff. LayoutCopilot keeps the request, command history and rejected alternatives.
- **AlphaEvolve:** expressing changes as Verilog diffs builds trust.
- **Gap:** there is no standard PCB intent schema, and no study of whether engineers trust LLM layout explanations.

**Implications for our system**
- The committed relation bundle *is* the intent record, kept in a sidecar next to `.kicad_pcb`. Each relation links source (datasheet KG node, requirement or recipe) → planner diagnosis → checker verdict and margin. Explanations walk these links.
- "Why here, not there?" compiles to a constraint, re-solves and shows the measured delta. The LLM narrates; it never invents numbers.
- Tag every claim measured / rule / datasheet / estimate / inference, with a one-click check; show the runner-up at low confidence.
- Show the interpretation first; offer 2–4 alternatives; provide an autonomy dial, locks and diff-first review; learn house style from cleanup edits.
- Keep a decision file; use light cognitive forcing at release.

---

## 10. Cross-cutting conflicts and open questions

**Conflicts.** VER wins unless noted.

| # | Topic | Conflict |
|---|---|---|
| 1 | PCBWorld prompt | Prompt carried no reward or DRC list; the LLM results are a lower bound |
| 2 | PCBWorld timing | "0.43 s" is PPO only; slowdown is "200×" vs PPO but 33–35× vs Freerouting |
| 3 | PCBWorld-Engine | "Unmodified KiCad" (paper) vs a modified fork (repository) |
| 4 | OmniLayout | Placement is "poor" (EDA) vs LMMs above academic placers on RR (VER) |
| 5 | OmniLayout licence | CC-BY-4.0 (ethics statement) vs "no licence, only 5 boards public" (third-party recon in NET); EMNLP venue not found |
| 6 | Li et al. DAC'26 | Speculated to be ModuPlace (EDA); VER shows a different paper |
| 7 | VeoPlace | Not MSR; DREAMPlace gain 4.4% not 4.3%; uses Gemini 3.6 Flash |
| 8 | MAGE | +29.7% WL is vs commercial placers, not humans; a vision ablation exists |
| 9 | LayoutCopilot | Does have headline numbers (93.75%) |
| 10 | PCB-Bench | 100% vs 90.9% is about one question out of ~11 |
| 11 | GENIE-ASI | F1 1.0 vs 0.97 at the simple/HL1 level; it is not PCB work |
| 12 | EvoPlace | Case-specific 5–8% vs generalized 0.5–2.9% |
| 13 | PCBSchemaGen | Slide numbers absent from the paper; HF card vs README difficulty split (67/63/35 vs 40/48/77) |
| 14 | PCBench count | 1,183 (census) vs 1,182 (PCBWorld) |
| 15 | circuit-skills | 0.79 vs 0.89; designer 0.63 vs 0.56 (different subsets) |
| 16 | Learned rankers | Fail (kicad-tools) vs help (circuit-skills); depends on corpus diversity |
| 17 | Via per current | 1 per 200 mA (AN-1149) vs 1 per A (SLYT614) |
| 18 | Images | Research says little benefit; practitioners require renders; MAGE shows timing value |
| 19 | Imperative vs bundled relations | PSDL vs RAC |
| 20 | Planner splits | Role decomposition helps (LayoutCopilot) vs mid-tier single model is the cheapest verified option ("Who Plans") |
| 21 | Code tools | Help analysis (GENIE-ASI, FloorplanQA distance) vs don't help construction (RAC Coord+Py, FloorplanQA planning) |
| 22 | Few-shot | Helps RR (GPT-5.5 0.95) vs barely moves AUC vs "reduces violations by routing less" (OmniRouting) |
| 23 | Iteration | More steps helped GPT-5.5 and hurt GPT-5-mini; LLM advantage grows with violation count (DRC-Aid) |
| 24 | EEBench | Astra 69.3% vs "no result"; scaffold dependence |
| 25 | "168 vs 0" | An Altium Academy video, misattributed in EDA |
| 26 | EvoDRC | Internally inconsistent: 73.5% vs 83.6% |
| 27 | OmniRouting text | Agentic description mentions "component positions", apparently copied from OmniLayout |
| 28 | HiePlace | Wrongly calls Quilter open-source |

**Open questions:**
- Does RAC hold on full real boards at PCBWorld D3 scale with a KiCad backend?
- How should tight/close/loose map to mm per component class? (Calibrate from corpus distances.)
- What is the right grouping granularity?
- No PCB head-to-head exists of JSON vs S-expression vs ASCII vs SVG vs image.
- No KiCad tool-granularity A/B exists.
- No datasheet layout-guideline benchmark exists, and no EVM-figure-to-relation parser.
- Is there board-level block-recognition accuracy for buck, crystal or USB on KiCad designs?
- What fraction of BOM parts have IBIS files?
- What tolerance should count as round-trip equivalence (e.g. "routes clean, HPWL ≤ 1.1× designer")?
- How much expert preference data does a ranker need?
- Do learned relative-pose priors raise clean-route rates on held-out boards?
- Legal status of training on CERN-OHL, GPL or CC-BY-SA hardware, and whether weights are a "Product".
- No contamination study exists for PCB benchmarks.
- No HCI study exists of PCB designers with AI co-pilots, and no A/B test of contrastive re-solve or rationale logs.
- Primary texts still missing: Cypress full paper, Li et al. DAC'26, CHIP-MAP, HyperPlace, PCB-Migrator, Zhang et al. MDPI LLM routing, GANA TCAD'23 tables.

---

## 11. Idea inventory (exhaustive; one line each; source tag)

Tags: EDA = llm_for_eda, VER = verification_papers, DATA = learning_from_layout_data, NET = netlist_datasheet_understanding, UX = field_reports_and_ux. Lines starting "evaluated" or "caution" describe approaches the notes found weak; they are kept so nothing is lost.

**A. LLM write and read interfaces**
1. LLM commits only named relations over objects, never coordinates or metric distances. [EDA, VER]
2. Ordinal magnitude classes (tight/close/loose), with millimetre values fixed on the solver side. [EDA, VER]
3. Submit the whole relation bundle at once for joint realization; avoid one relation at a time. [EDA, VER]
4. Coordinates are observable but never writable. [EDA]
5. Infeasibility feedback names conflicting constraints, violation magnitudes and admissible relaxations. [EDA, VER]
6. Persist the relation bundle as the intent artifact; re-solve after resizes and ECOs without LLM calls. [VER]
7. Requirements-only delegation as a fallback interface (74%). [EDA]
8. Candidate-point selection interface: pool of pads, track ends, ratsnest targets and an 8-way 0.5 mm grid, capped at 64. [VER]
9. Relation vocabulary (VER): group, region(rule_area), side, near, align, symmetric, board_edge, orient_toward, keepout, route_matched, layer_pref, via_limit, net_order. [VER]
10. Relation vocabulary additions (EDA): same_side, route_priority, matched with a tolerance class, min_loop, plane(net, layer, region), kelvin. [EDA]
11. Intent-level placement operations: place_near(ref, anchor_pin, max_mm, side), keep_together, align/distribute, orient_pin_toward, place_in_region, fix(ref). [UX]
12. Text and label placement in board coordinates; LLMs get inverse rotations wrong. [UX]
13. Magnitude classes resolve to mm from net class, stackup and datasheet knowledge. [EDA]
14. Calibrate magnitude-class mm per component class from human-board distance statistics. [VER, DATA]
15. Incident-list netlist encoding (part → pins → net → neighbours) with stable short integer ids. [EDA]
16. Include datasheet-derived pin roles and net criticality tags in the netlist view. [EDA]
17. Expose tool-computed structured state (overlaps, unrouted connections, DRC ids, per-relation verdicts and margins) rather than renders. [EDA]
18. Compact hierarchical JSON plus query tools: neighbors, nets_of, path, pins_by_role. [NET]
19. Python helper tools filter subcircuits and nets when a project exceeds about 100k tokens. [NET]
20. CSS-style left/top/width/height exemplars in prompts. [EDA]
21. Cell-aligned integer grid encodings, used only where they help the task. [EDA]
22. Visualization-of-Thought: prompt for ASCII "mental images". [EDA]
23. Anchor-relative DSL with pin-name references; keep relation chains shallow, anchored to IC or module frames. [DATA]
24. Global-to-local coordinate re-parameterization, invariant decomposition, imagine-and-revise self-consistency (R³L). [DATA]
25. Never have the LLM output raw `.kicad_pcb` S-expressions. [DATA]
26. Present functional groups (power stage, MCU plus decaps, connector plus ESD, analog front end) as first-class objects. [EDA]
27. Decompose decisions so each involves few coupled relations. [EDA]
28. S-expression observation with the static board block in the system message for prefix caching. [VER]
29. Output contract: one `<think>/<action>` pair, ASCII only, strict parser with idle fallback, regex-guided decoding. [VER]
30. Truncation metadata (`_total`, `_truncated`) and narrow per-list tools. [UX]
31. Perception must include pad names so agents can map REFDES:PIN. [UX]
32. Labelled renders that share ids with the text, as a secondary channel only. [EDA, UX]
33. Region renders per layer before claiming anything is routed. [UX]
34. Add images later, only for structure-level critiques (grouping, symmetry). [VER]
35. Self-consistency filter: keep a relation only if the LLM's own coarse placement satisfies it. [VER]
36. VLM numeric initial poses plus differentiable relations, optimized by projected gradient descent with a DIoU collision loss. [EDA, VER]
37. LLM picks an anchor object, then a DFS solver places the rest (MILP alternative with binary auxiliaries for OR). [VER]
38. Imperative relative-placement programs with variables and loops, plus LLM-free numeric repair. [EDA, VER]
39. Repair objective = loss + edit distance + volume-weighted optimal transport; edits limited to constants and directions; greedy local search. [VER]
40. Semantically grounded code representation: relative placement plus pin-name wiring (SchGen). [EDA, DATA]
41. Design-as-code: the whole design as version-controlled scripts, netlist-identical by construction. [EDA, UX]
42. Code or API access instead of GUI computer use. [UX]
43. Python constraint API (CPMpy/OR-Tools or a Python-embedded DSL) instead of a separate modelling language. [EDA]
44. Validate LLM constraint models on several instances to catch over-encoding of the example. [EDA]
45. Choose the formal intermediate language deliberately; prefer context-aware encodings. [EDA]
46. Adjacency-matrix output formulation for topology generation (LaMAGIC). [DATA]
47. Coarse, high-yield tool calls: "place this block under these constraints", "route these nets, protecting locked copper". [UX]
48. Native function calling over coding-agent harnesses (2.2–5.4× the tokens). [EDA]
49. Enable extended thinking or reasoning mode (+30–40 pts for weaker models; PlanarBench 39.5→95.5). [EDA, NET]
50. Give the placement LLM schematic, netlist or image context (improves grouping and RR). [VER]
51. Structured text conflict lists (component and location) for overlap repair, rather than image inference. [VER]

**B. Agent architecture and loop**
52. Bounded semantic action spaces: relations, operator catalogs, edit menus, code edits. [EDA]
53. Deterministic realizer plus an independent checker; never trust the solver's own satisfaction flag. [EDA]
54. Per-relation geometric oracles written as code. [EDA]
55. Rule-engine repair menus with budgeted DFS, backtracking and an anti-cycle memory bank (DRC-Aid). [EDA]
56. Memoryless, tool-free workers returning JSON, behind guards (schema, bounds, editable cell). [EDA]
57. Apply edits to a checkpointed copy, roll back on failure, re-run sign-off after every edit. [EDA]
58. Planner diagnosis = evidence, hypothesis, falsifier; intents = target, mechanism, operators, scope, expected effect. [EDA]
59. Return to the planner on regression, stall, an inexpressible intent or a double refusal. [EDA]
60. Mid-tier single model by default; escalate to a flagship planner only on verified failure. [EDA]
61. Bayesian per-task-class model-assignment controller, once a task taxonomy exists. [EDA]
62. Per-role cost ledger (tokens, spend, tool time). [EDA]
63. Keep observations compact (input is 81% of spend). [EDA]
64. Legality is part of the acceptance contract, against reward hacking. [EDA]
65. Bounded repair crops, a four-role workflow and evolving layer-wise skill files (EvoDRC). [EDA]
66. Geometry serialized as text, masked-polygon pretraining and synthetic violation pairs to fine-tune a DRC-VLM (SCALE). [EDA]
67. Rule text plus figures → interpretation LLM → coding LLM → checker code (DRC-Coder). [EDA]
68. Many LLM-written weak verifiers in a DSL, aggregated with about 10 labels; verifier-guided generation. [EDA]
69. LLM generates cluster constraints for an existing layout engine via ReAct. [EDA]
70. LLM handles netlist extraction and search setup; classical algorithms do P&R. [EDA]
71. Spec-to-layout agent flows coordinating sizing, learned constraints, ALIGN and sign-off. [EDA]
72. Layout generated as code by multiple agents ("Code, not canvas"). [EDA]
73. LLM proposes and explains placer hyperparameters (HyperPlace). [EDA]
74. Agents exchange structured JSON across analysis, grouping, floorplan and verification (CHIP-MAP). [EDA]
75. LLM few-shot net-weight constraints feeding Bayesian optimization (LLANA). [EDA]
76. LLM as RL reward or module optimizer; graph partitioning or clustering to cut P&R scale. [EDA]
77. LLM turns requests and defects into RL score reweighting, then re-tunes only the violating components (PCBAgent). [VER]
78. Hierarchical Modular Tree by recursive LLM splitting with confidence elicitation, plus RAG over guidelines. [VER]
79. Netlist heterogeneous graph with sub-circuit matching to simplify the netlist for the LLM. [VER]
80. Comprehensive Constraint Graph edges carry (x̂, ŷ, θ̂, w); non-adjacent pairs allowed. [VER]
81. Hierarchical placer: weighted CCG deviation + parent overlap + HPWL; module sizing over 4 rotations; C++ overlap-free detailed placement. [VER]
82. Multimodal serialization, topology-enriched retrieval, two grouping agents, group-aware placement, MILP legalization (Li DAC'26). [EDA, VER]
83. VLM region proposals as weak quadratic anchors (λ_A = 0.01) for an analytical placer. [VER]
84. For an RL placer, mask out-of-region logits to −∞, with an unconstrained fallback. [VER]
85. Proposal prompt contract: HISTORY SUMMARY → STRATEGY (one change) → REGIONS, with "hypothesis" and "exploratory" labels. [VER]
86. Top-Stratified context selection: K-means over placements, rank-softmax over clusters, show the top C. [VER]
87. Guide the largest and most-connected parts first, with a cap. [VER]
88. Detect families of repeated groups; place one, then transform-and-merge onto the rest (KiCad multichannel). [VER]
89. Mandatory flyline-render gate with stop rules (<2% gain or 5 iterations). [VER]
90. Feasibility check (area, packing, channel spacing) with recursive split. [VER]
91. Stateless independent auditor with no access to prior reasoning. [VER]
92. Go-With-The-Winners tournament with analysis and reflection agents. [VER]
93. Role-decomposed multi-agent with instructions; abstract suggestions go to the designer, concrete ones compile to commands. [EDA, VER]
94. Small fixed command set as the action space (LayoutCopilot's 11 commands). [VER]
95. Evolve placer optimizer code: CoT analysis → idea → reference → code; diversity-aware selection; UCB; self-reflection. [VER]
96. LLM-written ordering policies with a 3-stage proxy filter and top-4 elites in each prompt. [VER]
97. LLM-written objectives over a restricted differentiable-observable API, with AST and autograd gates. [VER]
98. Cost-tiered candidate evaluation; MAP-Elites islands; negative memory of failures; lineage logging. [VER]
99. Evolve a KiCad placer loss over HPWL, crossings, RUDY, decap distance and loop area. [VER]
100. Agent edits global-router source using QoR feedback and persistent router knowledge. [EDA]
101. Per-design evolution of a router or placer with shared memory of earlier outcomes. [EDA]
102. Agent-guided search for structural algorithm limits (joint breakpoint optimization). [EDA]
103. LLM-assisted theory work yielding better solvers. [EDA]
104. LLM tunes rip-up/reroute penalties within a knowledge-graph bound. [EDA]
105. A Teacher LLM attributes QoR gaps to stages; parallel Student agents implement fixes. [EDA]
106. Evolve Freerouting, a custom router or legalizer heuristics offline over a board corpus. [EDA]
107. Test evolved code for cross-board generalization from the start. [VER]
108. LLM → MILP/CP with solver-integrated reasoning, repeated sampling and self-verification. [EDA]
109. Expose solvers (MiniZinc, PySAT, Z3) over MCP with iterated validation. [EDA]
110. Use best-of-5 with validators as the baseline any agent loop must beat. [EDA]
111. Stateful tool gateway with persistent instances, state reuse and rollback (FluxEDA). [EDA]
112. Structured tool interfaces, persistent context, controlled execution, process-level evaluation. [EDA]
113. Persistent multimodal memory: episodic, spatial, semantic, procedural. [EDA]
114. Agent-maintained markdown context; review feedback becomes standing conventions. [EDA]
115. Multi-run consensus: keep recurring findings, re-check singletons against the datasheet, re-examine contradictions. [EDA, NET]
116. Use planner/executor splits as a cost tool, not as a quality guarantee. [EDA]
117. Explicit iteration budgets; more steps can hurt. [EDA]
118. Make net ordering (the first net_select) an explicit coarse planning decision. [VER]
119. Prefer interactive engine-engaged loops over plan-then-execute or engine-free generation. [VER]
120. For a step router: echo DRC codes and positions, include zones, per-netclass rules, rip-up actions, longer history. [VER]
121. Rule out per-segment LLM routing on token cost. [VER]
122. Routing prompt rules: completion > DRC > WL; vias ≥1 mm from pads; never reach a pad on the wrong layer; prefer `finish`. [VER]
123. Concave log DRV penalty over dirty nets and per-net violations; potential-difference terminal reward. [VER]
124. Promote dangling via, dangling track and net conflict to reward-relevant errors. [VER]
125. RL routing policy: Transformer with Fourier features plus a pointer network over candidates. [VER]
126. FSM action mask (net_select → start_route → routing). [VER]
127. On net selection, push the resolved per-class width and via sizes into the router. [VER]
128. Independent checks must not inherit the generator's interpretation ("jointly wrong" collateral). [EDA]
129. LLM congestion "Design Suggestion Deck" via genetic prompting and interpretable preference learning. [EDA]

**C. Placement and routing backend techniques (non-LLM, from VER)**
130. Differentiable net-crossing term from Bézier intersection parameters through a bell function. [VER]
131. Gumbel-Softmax orientation relaxation with bi-level position/orientation updates. [VER]
132. Two-sided electrostatic density with sides pre-assigned; side chosen as an LLM relation. [VER]
133. Multi-objective BO (MOTPE) over placer configs, scored by Freerouting routability and length. [VER]
134. Laplacian-eigenvector init → net-separation gradient → MILP legalization preserving relative positions. [VER]
135. Power-vs-signal wire-area model, pad-to-pad clearance, pad-type-aware two-sided density, QP legalizer. [VER]
136. Force-directed placement with power-circuit anchors, SA pad alignment, window legalization. [VER]
137. Offset constraint graph to migrate expert layouts to resized boards; routing-path graph matching for re-routing. [VER, DATA]
138. GPT-style router over routing-pattern tokens with a sliding window (evaluated: 0.69% NRR). [VER]
139. Diffusion placement guided by legality and HPWL potentials; synthetic training, zero-shot use. [VER]
140. Conflict-based search routing on Delaunay unstructured meshes. [VER]
141. Hierarchical MILP placement (HiePlace). [VER]
142. Strong baselines (SA with 320 go-with-the-winners workers); weak baselines mislead. [VER]
143. Placement order: chips first, then attached parts clockwise by weighted size, nets and pad level. [VER]
144. Decision-transformer masks per rotation, pad-alignment bonus, HPWL-threshold pruning, legal-only replay buffer. [VER]
145. Surface-layer-wire count as a user-requestable objective. [VER]
146. Treat placement and routing as one coupled problem. [UX]
147. Region-adaptive net priority ordering, not fixed heuristics. [UX]
148. Account for via delay in length tuning. [UX]

**D. Benchmarks and evaluation**
149. Benchmark ladder: OmniLayout RR/PRWL plus overlap and out-of-bounds; PCBWorld D3-A/B for routing. [VER]
150. Report @1 and @5, seed means, router versions and settings, and the potential function. [VER]
151. RAC-style relation tasks; tokens, cost and latency per verified board. [EDA]
152. Our own layout scorecard against human reference boards. [UX]
153. Clean Pass = full connectivity + 0 error-level DRVs. [VER]
154. Freerouting as a version-pinned routability oracle. [VER]
155. Designer, swap and auto placement baselines under a fixed router budget. [DATA]
156. A/B on the same solver: rules vs corpus priors vs learned pose model vs LLM constraint graphs. [DATA]
157. Time-split and cluster-split held-out boards; private boards; popular vs obscure strata. [DATA]
158. Min-K%-style contamination probes on test fragments. [DATA]
159. Random-relation or random-region control to prove the LLM's semantic value. [VER]
160. Deterministic grading, cost-efficiency in the score, credit only for working designs (EEBench). [UX]
161. Extend EEBench-style grading to layout, plus a small designer study. [UX]
162. Track token ROI and process-level metrics. [EDA]

**E. Design understanding (netlist → blocks → roles → constraints)**
163. Deterministic part–net–pin graph with hierarchy expansion; capture existing intent. [NET]
164. VF2 template matching on pin-role-labelled edges. [NET]
165. Matching relaxations: key-component filter, boolean prefilter, passive grouping; motif eligibility from the IC list. [NET]
166. Deterministic match sorting, skipping overlapping matches, and a constraint-satisfiability check. [NET]
167. Search for symmetry only inside matched instances. [NET]
168. GNN annotation plus port-semantics post-processing (connector types, net names, part categories). [NET]
169. Functional-pair link prediction without device sizes. [NET]
170. Hypergraph GNNs for board netlists, avoiding power-net clique blow-up. [NET]
171. Bipartite net–symbol graph with LM-embedded names for node-pair prediction. [NET]
172. Production rules on refdes prefix, pin names and one-hop neighbours; 60+ detectors with false-positive guards. [NET]
173. LLM writes detector code from 1–6 examples, unit-tested, then run deterministically. [NET]
174. Accept an LLM detector only if its tests pass and it explains all of the block's pins. [NET]
175. Never ask the LLM for stage-level groupings; use sheet hierarchy and designer intent. [NET]
176. Layered net classifier: intent → IBIS/datasheet → topology → names → LLM, with evidence per layer. [NET]
177. Use IBIS [Pin], [Diff Pin], Model_type and [Ramp] to classify nets. [NET]
178. Decide "is this net fast?" from edge rate × estimated length, not keywords. [NET]
179. Propose KiCad-compatible diff-pair renames; never rely on non-KiCad suffixes. [NET]
180. Resolve MCU pin-mux deterministically from vendor exports or a schematic table. [NET]
181. Inferred, editable net-type priority buckets that set routing order. [NET, UX]
182. Show default current assumptions (200/500 mA) for confirmation. [NET]
183. Layout card = ports + pin-role KG + IBIS + externals + typed predicates + thermal/creepage + per-field provenance; JEP30 export. [NET]
184. Distributor APIs for identity and coarse parametrics only; expect schema churn. [NET]
185. LLM proposes candidate MPNs when missing, marked `proposed`. [NET]
186. Validators: units, pin existence against the KiCad symbol, datasheet vs symbol pin-name agreement. [NET]
187. Knowledge entries with trigger and scope for team recipe overrides, suggested from repeated edits. [NET]
188. Net roles → real classes (rules) or implicit classes (semantic tags). [NET]
189. Block membership via `Component Class` fields plus per-role classes. [NET]
190. Generated placement rule areas per component class as placer region seeds. [NET]
191. Block-scoped `.kicad_dru` rules via `memberOfFootprint('${Class:…}')`. [NET]
192. Compile tuning profiles and soft objectives into a placer JSON. [NET]
193. Validation screen: evidence plus editable fields, accept/reject recorded, undetected nets stated as generic low-speed. [NET]
194. Ask clarifying questions only for high-impact, low-confidence fields (threshold 0.5). [NET]
195. Recipes as data (recognizer, constraint set, check set); one predicate drives both objective and acceptance. [NET]
196. On vendor conflicts, use the conservative value and show both citations. [NET]
197. Replay a known-good sub-layout on exact match (design blocks, atopile sub-PCBs, vendor EVM exports). [NET]
198. Buck recipe: Cin_HF first; vertical loop over L2 GND; minimal SW; FB at pin with separate sense, away from SW/L; Kelvin FB. [NET]
199. Crystal recipe: near driver, nothing routed underneath, ground isolation, chip-specific gap, no magnetics nearby. [NET]
200. Decoupling recipe: smallest cap closest; ground via at the cap pad; ≤6 mm trace through a via. [NET]
201. LDO, RF, USB and power-net recipes (adjacent caps; datasheet thermal-via rule; 50 Ω ±10%; ESD at connector; ΔT ≤20 °C). [NET]
202. Schema: each constraint carries a `checks` list with sources. [NET]
203. Schema: nets carry IBIS facts; layout cards carry an extraction audit. [NET]
204. Structural LVS as its own verify stage. [NET]
205. Five-layer deterministic verifier (ERC, role, template, VF2 topology, power invariants). [NET]
206. Hierarchical-address layout reuse across regeneration. [NET]
207. Spec-first gating: no edit tools until a validated change proposal exists. [NET, UX]
208. Mine net classes, component classes and DRU rules from corpora to build an intent dataset. [NET]
209. Bypass-cap parent assignment priority: wire → voltage-named pin → split. [NET]
210. Quilter-style physics checks per constraint (pin distance, path length, layer switches, ground overlap, overheated length). [NET]
211. EMC checks: switch-node area, input-loop area, decap distance, TVS distance, inductor proximity, skew limits. [NET]

**F. Datasheet and app-note extraction**
212. Chunked extraction into a knowledge graph with provenance, applicability conditions and deterministic updates. [EDA, NET]
213. Agentic retrieval with critic scoring (pin coverage 40%), up to 5 sources, 7-day cache. [EDA, NET]
214. Strong model reviews; weak model extracts. [NET]
215. Map extracted layout statements to the closed relation vocabulary (e.g. `near(C_in, U1.VIN, tight)`). [EDA]
216. Generate a checker per extracted predicate. [EDA]
217. Two schemas: electrical tables vs layout guidance that keeps qualitative strength. [NET]
218. Never invent millimetres: "null, never guess". [NET]
219. Read MCU/SoC hardware design guides first. [NET]
220. Page and sentence evidence on every value. [NET]
221. Tool-call audit; reject runs that never read the source. [NET]
222. Deterministic scripts for all derived numbers. [NET]
223. PDF-hash plus revision pinning and staleness checks. [NET]
224. TOC → keyword-density page selection; typed SpecValue with confidence and trust gates. [NET]
225. MinerU2.5-Pro or a VLM for tables; `pdftotext -layout` fallback for prose. [NET]
226. PDF → Markdown → LLM pin JSON preprocessing. [NET]
227. Treat recommended-layout figures as low-confidence topology hints. [NET]
228. Hierarchical narrowing to cut tokens (SpecMap). [EDA]
229. Document focusing, hierarchy-aware retrieval and entity normalization (D2S-FLOW). [NET]
230. Retrieve only the properties that explicit verification criteria need. [NET]
231. Decompose footprint-drawing perception (count, centres, dimensions); pretrain on synthetic, fine-tune on real. [NET]
232. Multi-agent LMM footprint-geometry labelling. [NET]
233. Hand-coded footprint generator; the LLM only lists pads to omit, reconciled in code. [UX]
234. AI-generated JEP30 part models from datasheets. [NET]
235. Datasheet layout-analysis model plus CoT parameter extraction (DocEDA). [EDA, NET]
236. Build a datasheet layout-guideline extraction benchmark. [EDA, NET]
237. Parse EVM reference-layout figures into relations. [EDA]

**G. Data, retrieval, priors and training**
238. Pinned, licence-tiered corpus: pointers plus SHA-256 in the repo, payloads in a git-ignored cache. [DATA]
239. Qualification: opens in KiCad, 1–4 layers, ≥10 segments, no unconnected items; record `ref_drv`/`bare_drv`; difficulty buckets. [DATA]
240. Use open-schematics and kicad-happy as discovery indexes, not training sets. [DATA]
241. Discovery: GitHub topics and language queries, PCBench sources, OSHWA, Adafruit/SparkFun Eagle via importer. [DATA]
242. Manifest fields: repo, sha, spdx, tier, version, layers, parts, `ref_drv`, `ref_open`, dates, category. [DATA]
243. `kicad-cli pcb upgrade`; refuse rather than half-parse legacy constructs. [DATA]
244. Require `ref_open == 0` for routing data; use `ref_drv` as a quality weight. [DATA]
245. Dedup by blob hash, footprint-multiset Jaccard and WL hash; at most 2 boards per repo. [DATA]
246. Score against the human using each board's own rules; pours count as copper. [DATA]
247. Auto-label subcircuits via detectors plus WL/gSpan motif mining on the PCB netlist. [DATA]
248. Relative-pose tables per (anchor package, pin function, satellite package), with percentiles. [DATA]
249. Routing-style tables: width by net function, plane use, vias, diff-pair spacing. [DATA]
250. Module-partition and module-to-edge graphs. [DATA]
251. Round-trip constraint extraction: extract → re-solve → keep if it matches the human board; BO over weights otherwise. [DATA]
252. Outcome-labelled placement sets per board as ranker and DPO data and as a benchmark. [DATA]
253. Corpus percentiles as soft targets; datasheet distances as hard targets. [DATA]
254. Ship measured priors as soft constraints immediately, with no ML. [DATA]
255. Retrieval key: anchor IC (MPN family plus pin-function multiset) plus a 2-hop labelled neighbourhood. [DATA]
256. WL-hash and motif-histogram coarse filter (λ = 0.6), then GNN or graph-kernel rerank. [DATA]
257. Return the top-k human fragments with full relative geometry plus summary stats; the solver adapts them. [DATA]
258. Max-weight-clique selection of non-overlapping fragments to maximize reuse. [DATA]
259. The fragment database grows only through verified updates. [DATA]
260. Copy exact relative poses where packages match. [DATA]
261. Retrieval UI shows the licence, offers a permissive filter, and the LLM cites fragments. [DATA]
262. Retrieve similar boards to seed placer and router settings (CROP pattern). [DATA]
263. Requirement → block retrieval with a hybrid sparse, semantic and LLM retriever. [DATA]
264. Extract symmetry and alignment constraints from existing placements by sweep-line. [DATA]
265. Image-based circuit recognition plus graph retrieval for legacy designs and plagiarism checks. [DATA]
266. Match work-in-progress connectivity against a company design vault. [DATA]
267. Learned layout embedding (GraphSAGE plus routing image) as a similarity metric. [DATA]
268. DevFormer-style relative-pose and assignment model with symmetry augmentation. [DATA]
269. Pairwise ranker as a tie-breaker only, never the acceptance gate. [DATA]
270. Ranker features: over-capacity, crossings per net, decap distance, congestion, off-board pads. [DATA]
271. Hand-coded features plus the router as label oracle; fit rankers only with diverse corpora and board-grouped CV. [DATA]
272. A bounded real route as the gate instead of a pre-route score. [DATA]
273. Learn soft-FOM weights from committed-vs-jittered preferences; low-variance terms transfer. [DATA]
274. Hard negatives from swapping same-footprint interchangeable parts. [DATA]
275. Jitter σ calibrated to a 20–60% pass rate; fixed connectors and holes; negative controls. [DATA]
276. Difficulty filtering: drop prompts always or never solved. [DATA]
277. Group mean/variance prompt filter (0.3–1.8, var ≥ 0.1). [DATA]
278. Solver distillation plus a feasibility RL stage; Best-of-N with a DRC/router verifier. [DATA]
279. Text-attributed instances with nearest-neighbour hints. [DATA]
280. Procedural constraint boards for reward unit tests. [DATA]
281. Tiered reward: 0 if unparseable; 0.1 + 0.4·legality; 1.0 + completion + optimality; + β·ranker. [DATA]
282. DPO on better/worse-routing pairs where hacking appears. [DATA]
283. GRPO groups of 4–5 out of 16–36 samples. [DATA]
284. 7–20B LoRA SFT with distilled CoT on hundreds to thousands of verified examples. [DATA]
285. GNN ranker or reward trained on expert pairwise rankings. [DATA, VER]
286. CCG equivalence test (common edges ≥ τ, cosine ≥ ψ) for policy ratios. [VER]
287. Mine open CCG training data from the 679 KiCad-9 PCBWorld D3 boards. [VER]
288. BO reverse-engineering of expert layouts into generator scripts. [DATA]
289. Round-trip NL↔code with equivalence checks and Rouge-L decontamination. [DATA]
290. Rule-based testbenches over LLM-generated ones. [DATA]
291. "GPT synthesizes, human inspects" data, plus violation-injected DPO negatives. [DATA]
292. Synthetic SFT warm start, then GRPO against a rendered verifier. [DATA]
293. Dense IoU, centre and collision rewards with scene-graph reasoning. [DATA]
294. Blended cold-start data before RL. [DATA]
295. DPO from MLLM-judge preference pairs. [DATA]
296. Simulator-refined diffusion (surrogate plus full-wave) for RF layouts. [DATA]
297. Semi-supervised blurred-image imitation of where critical nets run. [DATA]
298. Optimizer-generated "expert" data with return-weighted regression and few-shot fine-tuning. [DATA]
299. RL for subcircuit placement (A2C, net-aware DQN). [DATA]
300. RL routers trained on synthetic plus real boards. [DATA]
301. Learned net order via transformer RL; human order is not stored in board files. [DATA]
302. Caution: a hand-designed crossing-aware net order did not help. [DATA]
303. Caution: coarse placement hints (anchors, big-part relations, "near") barely help. [DATA]
304. Licence tiers A/B/C with defined uses. [DATA]
305. Facts over expression in training targets. [DATA]
306. Similarity filter between training fragments and evaluation boards. [DATA]
307. Condition priors on layers, package and class; weight professional and DRC-clean boards. [DATA]
308. Opt-out list; per-board licence recorded; unlicensed repos are "ideas only". [DATA]
309. Permissive-only subset plus near-dedup. [DATA]
310. Trust-tier labelling with independent evidence families. [DATA]
311. Audit generated datasets (compile rate, provenance detectors). [DATA, NET]
312. Fine-tune small VLMs or LLMs for layout understanding. [EDA]

**H. Field reliability and tool design**
313. LLM orchestrates deterministic engines; it never pushes copper. [UX]
314. KiCad and fab DFM own the verdict; zero model discretion in verification. [UX]
315. A verification gate on every AI edit. [UX]
316. Never re-implement approximate checks (e.g. AABB courtyards). [UX]
317. Judge the live board and report which source was judged. [UX]
318. Fab-specific DRC rules are a precondition. [UX]
319. Clean reports list disabled categories; read silenced-rule config. [UX]
320. Read back an observed diff after every write; a mismatch is an error. [UX]
321. Netlist parity and pin-by-pin pad↔net comparison as first-class tools. [UX]
322. Semantic checks: footprint vs MPN, library-identity uniqueness, ratings, ERC-blind checklist, layout quality. [UX]
323. Typed refusals; a plan is "applicable" only if legal and the score improves. [UX]
324. One native commit per step; immutable candidates; Git snapshots; `compare(a, b)`. [UX]
325. Revision-bound candidates and a human-only single-use apply token; writes off by default. [UX]
326. Server-side task state that survives compaction or a model swap. [UX]
327. Idempotency ledger and snapshot journal. [UX]
328. Validator findings with stable ids. [UX]
329. Compile-and-refuse: a plan that cannot finish never starts. [UX]
330. Grid-snapped coordinates chosen by the operation library. [UX]
331. Propose → gate → accept, monotone; plan-first `--apply`; work on a copy. [UX]
332. Per-net monotone acceptance with a regression ledger. [UX]
333. Prune-to-DRC: delete this run's flagged objects by UUID. [UX]
334. Checks report checked / defect / not checked, with input fingerprints. [UX]
335. Failure attribution: where and why routing stalled (region, capacity vs demand). [UX]
336. Diagnostics: no-path cell count, wall nets, escape capacity, via-spot scans. [UX]
337. Deterministic move library: rip wall nets, pin swap toward via room, via size, nudge supports, `fit_near`, temporary keepouts. [UX]
338. Judge helper flags by the acceptance verdict, not the router's own numbers. [UX]
339. Maze router for the last breaks. [UX]
340. Search placements with the real rules. [UX]
341. One shared orientation helper through KiCad code; preserve 3D models, zones and text. [UX]
342. Loop: interpret → confirm → constrain → place → gate → critical route → lock → autoroute → refill check → full gate → triage. [UX]
343. Fan out first, stitch ground last, widen nets after zero breaks. [UX]
344. Lock critical copper before autorouting; verify it survives zone refill. [UX]
345. Run auto-layout early as a crowding check. [UX]
346. Placement gate: check, render, readability, escape capacity, 1:1 mechanical fit. [UX]
347. Retry cap of 2–3 per issue, iteration and spend caps, then escalate. [UX]
348. Autofix recognizes every failure category. [UX]
349. Separate read-only, evidence-only reviewer that keeps a verified-correct list. [UX]
350. Reference designs and validated fragments first. [UX]
351. Record seeds, versions, constraint sets and prompts; deterministic solver step. [UX]
352. Skills/lessons file with sources. [UX]
353. Permission tiers (read-only default, build, release). [UX]
354. stdio only, reviewed server code, Git-folder sandbox; token and Origin check on bridges. [UX]
355. API reference docs as grounding. [UX]
356. Real part data for footprints. [UX]
357. Plan placement offline with an overlap script and ratsnest preview, then apply. [UX]
358. Label-placement script for silkscreen. [UX]
359. Unique footprint names to avoid library aliasing. [UX]
360. Freerouting `-mt 1`; import vias before tracks; check "open nets 0". [UX]
361. Unit-test generators; dry-run on a toy board; compare several DRC tools. [UX]
362. Stop after the second or third failed fix. [UX]
363. Exact references required; refuse unverifiable outlines. [UX]
364. Validate tool inputs from local models. [UX]
365. Write a resume point when blocked; search project docs before asking. [UX]
366. Human GUI-only checks (F8) at milestones. [UX]
367. Expected-value checks; separate defect from decision; cite the datasheet table row. [UX]
368. Portability re-check in a fresh directory. [UX]
369. Fix parity in source data, not with exclusions. [UX]
370. Label inferences as inferences. [UX]
371. Generate many ranked candidates rather than one. [UX]
372. Physics checks during candidate generation. [UX]
373. Existing copper is "solved"; protected polygons. [UX]
374. Stop search when improvement is unlikely. [UX]
375. Relaxed-clearance mode for cleaner, more manufacturable layouts. [UX]
376. Clustering-gravity knob for initial placement. [NET]
377. Sequential optimal packing, with constraints hardened by LLM loops. [UX]
378. Staged prompt: placement and netlist → check → PNG → fix → route; one correction at a time. [UX]
379. Datasheet → LLM draft → programmatic checks → feedback → human review; SPICE as ground truth. [UX]
380. Module registry with validated layout fragments. [UX]
381. 80/20 automation split; ask vendors about their training distribution. [UX]
382. Close the loop with simulation, SI/PI, DFM and BOM checks. [UX]
383. Claude routing plan → GUI parameters plus checklist, replayable as JSON; per-field "Ask Claude". [UX]
384. Style presets (17 axes); route one function group at a time with DRC after each. [UX]
385. Publish where the tool stops working. [UX]
386. Human approves part substitutions. [UX]
387. Encode mechanical constraints as hard ("must be on edge") vs soft ("nice near edge"). [UX]
388. Use official library symbols for readable schematics. [UX]
389. RF lines as copper polygons replicating the simulated models; human gates with machine-checkable criteria. [EDA]
390. Library that writes `.kicad_pcb` without a KiCad runtime (track arrays, via grids). [EDA]
391. KiCad chat plugin with subtask splitting, RAG over docs and a plugin recommender. [EDA]

**I. UX and explaining "why"**
392. Show the agent's interpretation before acting, editable. [UX]
393. Suggestions beside the canvas; direct manipulation stays primary. [UX]
394. Autonomy dial, lock controls, global controls. [UX]
395. 2–4 distinct alternatives with scorecards and renders, plus an outlier and "more like this". [UX]
396. Use early exploration choices to steer the generator. [UX]
397. Contrastive "why here?" answered by re-solving under a constraint, with the LLM narrating the measured delta. [UX]
398. Use the user's preferred plan as the foil. [UX]
399. Inverse-CP counterfactuals: the minimal change for the user's desired decision. [UX]
400. Interactive reoptimization and multiobjective methods from OR. [UX]
401. Explanations that lower verification cost, with one-click checks. [UX]
402. Provenance tags: measured / rule / datasheet / estimate / inference. [UX]
403. Show the runner-up only when confidence is low. [UX]
404. "Do less but correctly" under uncertainty. [UX]
405. Granular feedback; show the consequences of user actions. [UX]
406. Object-anchored IBIS/QOC-lite rationale, logged at action time and exportable. [UX]
407. Cognitive forcing at release; residual-risk list; no single green check for novices. [UX]
408. Diff-first review; learn house style from cleanup edits. [UX]
409. Inline suggestions for tiny edits. [UX]
410. Plans as editable, replayable checklists. [UX]
411. Clarify only when necessary (edges, keepouts, sensitive nets, fab, stackup). [UX]
412. Both an engineer metrics view and an artist render view. [UX]
413. Real-time error detection as the primary feature. [UX]
414. Customer-cloud deployment for IP. [UX]
415. Guard against skill atrophy. [UX]
416. Report which constraints were met and which need attention. [UX]
417. Watch iterations live; accept or cancel at any time. [UX]
418. Status icons plus click-to-navigate, always explaining why an issue was flagged. [UX]
419. Encourage users to test AI boundaries early; suggest goals matched to the AI's capabilities. [UX]
420. Conversational interaction with context and project examples. [UX]
421. Mixed-initiative co-creativity; suggestions that target diversity. [UX]
422. Parallel authoring and side-by-side comparison. [UX]
423. Name "ADR" in prompts when generating rationale. [UX]
424. Relation bundle as the intent record, linked source → diagnosis → verdict and margin, in a sidecar file. [EDA]
425. Generate explanations by walking those links, not composing them post hoc. [EDA]
426. Store prompts before calls; keep full lineage logs. [EDA]
427. Residual risk travels with handoffs; keep request, history and rejected alternatives. [EDA]
428. Reviewable diffs build trust. [EDA]
429. Mechanism memory: local effects, optimization debt, downstream retention. [EDA]
430. Design journal with an act–observe–reflect loop. [EDA]
431. Evidence builder attributing degradation to groups. [EDA]
432. Capture intent explicitly, because "intent lives outside the file". [UX]
