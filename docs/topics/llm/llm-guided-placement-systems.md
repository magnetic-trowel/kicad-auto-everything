# LLM-guided placement systems (PCB and IC)

**TL;DR**
- **Every PCB result in which an LLM-involved system beats classical or commercial tools keeps the geometry in a solver** [I]. Examples: Li et al. DAC'26 (LLM grouping plus MILP legalization), ModuPlace (LLM constraint graph plus hierarchical placer), PCBAgent (RL plus legality masks).
- **Li et al. (DAC 2026):** routed WL/vias are **−55%/−73% vs a commercial placer** and **−15%/−13% vs Quilter**. Corrected: this is a different paper from ModuPlace [S, via survey].
- **ModuPlace:** a fine-tuned 7B model trained on 426 expert constraint graphs beats zero-shot GPT-4o and Claude-3.5 by about 26% WL and 43% vias [P].
- **IC lessons that transfer:**
  - **weak anchors** (VeoPlace λ_A = 0.01; 0.1–1.0 over-constrains);
  - a reusable proposal prompt contract;
  - **place one instance per family of repeated groups, then replicate** (MAGE).
- None of ModuPlace, PCBAgent or Li et al. releases code, prompts or hyperparameters [P].

## Key facts

### PCB systems

**PCBAgent** (ASP-DAC'25; HKUST, Huawei Noah's Ark, CUHK) [P] ([PDF](https://www.cse.cuhk.edu.hk/~byu/papers/C247-ASPDAC2025-PCBAgent.pdf)).
- **Objective:** min HPWL + λ/NSLW, subject to Overlap = BeyondBoundary = InsufficientSpacing = 0. Surface-layer wires (SLW) are 2-pin connections that cross no component.
- **Placer:** a decision transformer (ChiPFormer-style) on a 128×128 grid.
  - The state concatenates view, position and wire masks for **each of 4 rotations**.
  - Position mask = boundary OR spacing; pad-aligned cells get a bonus of −0.01; HPWL-threshold pruning.
  - Step reward is ΔHPWL; trajectory score = 1000/HPWL + 0.01·NSLW.
  - Only hard-legal trajectories enter a prioritized replay buffer (64/8).
- **Order:** chips first, then attached parts clockwise from the highest-weight pad.
- **LLM agent:** statement obtainment, semantic understanding, tool invocation, command generation. Its commands reweight the trajectory score and replay weights, then **re-run fine-tuning on violating components only**. The LLM never trains weights. **The LLM model, prompts and tools are unspecified.**
- **Results** on 17 boards (18–414 parts, density 0.33–0.76):
  - HPWL 1.04× and NSLW 0.94× relative to manual; baselines 1.13/1.33/2.05×;
  - "90% of the quality of manual results"; +39.6% on requested wire categories in 2–3 rounds; ordering gives −30%/−22% HPWL.
  - Baselines' spacing-legality rates were **0** (MaskPlace, ChiPFormer, MILP).
- **Independent checks:** most vias in ModuPlace's comparison (94.4); RR 0.42 in OmniLayout.

**ModuPlace** (DAC'26; Han, Li, Zhao, Fu, Ye, Chen, Yu, Ho) [P] ([PDF](https://yhhan.com/PDFs/ModuPlace_paper.pdf)).
- **Pipeline:**
  1. LLM Agent 1 builds a **Hierarchical Modular Tree**, splitting recursively until confidence passes a threshold, with RAG over guidelines and a netlist heterogeneous graph with sub-circuit matching.
  2. Agent 2 emits a **Comprehensive Constraint Graph** per layer. Each edge carries (x̂, ŷ) offset, θ̂ and weight w; non-adjacent pairs are allowed.
  3. The placer:
     - module sizing: min t1·BBox + t2·HPWL over 4 rotations;
     - per layer: min Σ w_ij·[γ1·|Δpos| + γ2·|Δθ|] + γ3·parent overlap + γ4·HPWL;
     - C++/Boost overlap-free detailed placement.
- **Training:** Qwen-2.5-7B.
  - SFT on **426 CCGs**: loss λ1·HPWL + λ2·crossings − λ3·GraphSAGE similarity.
  - GRPO: 36 CCGs per input in groups of 4; advantage ω1·z(HPWL) + ω2·z(crossings) + ω3·e^(−r̂), where r̂ comes from a **GNN trained on pairwise expert rankings**.
  - A CCG equivalence test (common edges ≥ τ, cosine ≥ ψ). Trained on 4×A100. λ, ω, γ, τ and ψ are not given.
- **Evaluation:** 11 boards (35–97 parts, 2–4 layers), routed several times by PcbRouter and Freerouting; IL and XT simulated in Keysight ADS.

  | Method | WL | Vias | IL | XT |
  |---|---|---|---|---|
  | **ModuPlace** | **1266.5** | **48.6** | **5.40** | **−41.83** |
  | PCBAgent | 1477.3 | 94.4 | 6.62 | −38.28 |
  | DeepPCB | 1484.6 | 48.8 | 7.81 | −39.99 |
  | NS-Place | 1490.2 | 71.5 | 6.89 | −36.25 |
  | SA-PCB | 1528.5 | 81.7 | 6.52 | −39.22 |

- **Summary:** WL −17.14%/−15.01% and vias −40.51%/−32.02% vs baselines.
- **Ablations:** without SFT, WL +35.1% and vias +66.2%; without GRPO, +25.4% and +53.1%; removing the HMT hurts most.
- **Zero-shot CCG generators (WL / vias):** Qwen-7B 1928.7/97.3; Qwen-3-14B 1866.1/99.3; InternLM-20B 1874.6/96.7; DeepSeek-R1-32B 1824.8/94.6; Claude-3.5 1707.5/92.1; GPT-4o 1756.8/84.6.
- **Per-board caveat:** baselines win P5, P6, P8, P9 and P11 on some metrics; "beats all" holds only on average.

**Li, Peng, Huang, Wu, Zhu (DAC 2026)**, coarse-to-fine LLM-guided PCB placement [S, via survey] ([2606.19795](https://arxiv.org/pdf/2606.19795)).
- **Pipeline:** multimodal serialization, topology-enriched retrieval, two grouping agents, group-aware global placement, constraint-graph/MILP legalization.
- **Results** on 6 industrial boards, same commercial router: **−55%/−73% vs a commercial placer, −34%/−26% vs NS-Place, −15%/−13% vs Quilter**.
- The survey: "an unlegalized coordinate set is not acceptable even when its estimated HPWL is low."

**Other LLM-plus-PCB items:**
- The GPT-6 Astra KiCad demo hand-protected critical nets, then ran Freerouting [S].
- You et al. 2024: GPT-4 writes layout-generator code [S].
- Zhang et al. 2025 (MDPI): LLM-only routing coordinates with few-shot plus CoT; unread (403) [S].
- LLANA: few-shot LLM net-weight constraints for Bayesian optimization [S].

### IC systems with transferable patterns

**VeoPlace** (NeurIPS 2026 main conference; ICML 2025 EXAIT workshop poster) [P] ([2603.28733 v3](https://arxiv.org/pdf/2603.28733)). Corrected: eight authors at Harvard/Kempner and Google DeepMind, not MSR.
- **Loop:** each iteration runs 8 unguided rollouts, one VLM call returning 8 region suggestion sets, then 8 guided rollouts. A 2,000-rollout budget means 125 calls.
- **Anchoring:** DREAMPlace gets a quadratic anchor λ_A·Σ‖x − x̂‖²; **λ_A = 0.01 is best, 0.1–1.0 over-constrains**. ChiPFormer gets −∞ masks, with a fallback for about 20% of suggestions. At most 256 macros, largest first.
- **Prompt:** objective, grid, macro table (colour group, W×H), rules, and prior episodes as labelled images plus coordinates plus metrics.
- **Output contract:** **HISTORY SUMMARY** (archetypes; at least 3 principles, marked "hypothesis" if weak) → **STRATEGY** (exactly one change to the best archetype, marked "exploratory") → **REGIONS** (largest first).
- **Context selection ("Top Stratified"):** K-means over placement vectors, rank-softmax (τ = 0.43) over cluster best scores, top C from the chosen cluster. It beat FIFO, random, best-only and diverse selection.
- **Results:**
  - ChiPFormer improves on 9 of 10 benchmarks (peak −32.2%); DREAMPlace gains are **0.5–4.4%** (corrected from 4.3%).
  - Gemini 2.5 Flash on the ChiPFormer track, **Gemini 3.6 Flash** on DREAMPlace; Qwen3-VL 8B and 30B-A3B match Gemini.
  - Image vs text <0.8%; random regions sharply worse; anchoring to the best-so-far ≈ no gain.
  - Overhead 2–7%, about 62 s per call, about $7 per run.

**MAGE** (UCSD; Kahng, Kundu, Pramanik; Claude Opus 4.6) [P] ([2607.18536](https://arxiv.org/pdf/2607.18536)).
- **Phases:**
  1. parse and retrieve;
  2. hierarchy-aware grouping into **families of similar groups**;
  3. group boxes behind a mandatory flyline-render visual gate (stop at <2% gain or 5 iterations);
  4. feasibility check (area, packing, channel spacing; recursive split);
  5. **one reference placement per family, then transform-and-merge** (translate, reflect, rotate);
  6. chip-level checks plus a **stateless auditor**.
- **Tournament:** optional Go-With-The-Winners, 6 variants × 6 rounds.
- **Cost:** 78–189M input tokens per variant ($6–14), $220–509 per tournament (average $310), about 10 h.
- **Results (corrected):** +29.7% routed WL against **commercial** placers (power +3.8%/+4.5%); "comparable" to the human expert; −9.8% WL and −1.1% power vs Hier-RTLMP.
- **Vision ablation:** WNS 40.5% worse and TNS 133% worse without it.

**Others:**
- **HyperPlace** (TODAES 2025) [S, via survey]: an LLM proposes *and explains* DREAMPlace/Xplace hyperparameters. Up to 1.66% HPWL on ISPD2005; under fences, +22.24% vs DREAMPlace 3.0 and +19.28% vs Xplace 2.0.
- **CHIP-MAP** (DATE 2026) [S, via survey]: analysis, grouping, floorplan and verification agents exchange JSON; up to 1.5% area; repairs 61.6% of TNS.
- **PDAgent-Bench:** with human instructions, VLM macro placement beat analytical and RL baselines [P].
- **PlaceReasoner-Beta** [S].

### Non-LLM PCB backends (detail lives in the placement area)

| Placer | Key idea | Numbers (verification note) |
|---|---|---|
| NS-Place (ASP-DAC'22 Best Paper) | Laplacian init → net-separation GD → MILP with relative-position constraints | Routed WL −10% vs manual, −6% vs GDMILP (−25% peak); vias −18%/−39%; fails at about 20% whitespace |
| Cypress (ISPD'25, Cornell/NVIDIA) | Differentiable net crossing (Bézier params × bell), Gumbel-Softmax orientation, two-sided density, MOTPE tuning | Routability up to 1.2× SA-PCB, 5.9× NS-Place, 1.6× NS-Place+; 492.3× faster than SA-PCB and 329.7× than Quilter; RR 0.33 in OmniLayout |
| Chen et al. DAC'25 | Power/signal wire-area model, pad clearance, QP legalizer | Best academic in OmniLayout (RR 0.62, similarity 0.86) |
| HiePlace (TCAD'26) | Hierarchical MILP | 7.7× faster, −66% cost, −16% WL, −46% misaligned regions |
| Tsou DAC'24 | Force-directed with power-circuit anchors | — |
| PCB-Migrator (DATE'26) | Offset constraint graph migration | — |
| RL_PCB (DATE'24) | TD3/SAC | −17%/−21% WL vs SA on unseen circuits |

See [../placement/pcb-placers.md](../placement/pcb-placers.md).

## Recommendations for our system

1. The LLM produces grouping, hierarchy and a relation or constraint graph; the solver legalizes it (MILP/CP-SAT) [I].
2. **Weak anchors only:** treat LLM regions as soft penalties at about 1% weight; verify value with a random-region control.
3. **Reuse VeoPlace's prompt contract** for per-block rule-area or room proposals, with Top-Stratified context selection.
4. **Repeated channels:** detect multichannel or design blocks, place one, replicate with transforms, then globally legalize. KiCad's Repeat Layout and placement rule areas are native carriers.
5. Add Cypress's net-crossing and orientation terms and Chen's power/signal demand model to the analytical placer; let the LLM decide `side(part, bottom)` as a relation.
6. **Fine-tuning path:** an open CCG-style dataset mined from PCBWorld D3 boards plus an expert-ranking GNN (see [../data/training-recipes.md](../data/training-recipes.md)).

## Conflicts and open questions

- The Li et al. DAC'26 primary text has not been read; its numbers come from a survey.
- The CCG text schema the LLM emits is unpublished.
- ModuPlace's per-board wins are mixed.
- DRLPlace (ASP-DAC'26) and MARS-Place (Integration'26): details not retrieved.

## Sources
- research notes:
  - [verification_papers.md § 1 rows 12–17, 21–22, 35–38, 42, 44; § 2.2, § 2.3, § 2.5, § 2.6, § 2.8, § 2.12](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_papers.md)
  - [llm_for_eda.md § 1, § 7](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/llm_for_eda.md)

See also: [interfaces-relations-vs-coordinates.md](interfaces-relations-vs-coordinates.md), [code-and-objective-evolution.md](code-and-objective-evolution.md), [agent-loop-patterns.md](agent-loop-patterns.md), [vision-feedback.md](vision-feedback.md)
