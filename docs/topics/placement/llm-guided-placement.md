# LLM/VLM-guided placement (PCBAgent, ModuPlace, Li DAC'26, VeoPlace, MAGE)

**TL;DR**
- Best-supported loop: **LLM → hierarchy, sides, constraints/relations, weights, priorities → numeric placer → exact legalizer → metrics + feature-rich conflict list → LLM**. Never let the LLM emit final coordinates.
- **Hierarchy matters most** (ModuPlace's largest ablation); a fine-tuned 7B model writes better constraint graphs than zero-shot GPT-4o/Claude-3.5.
- Frontier LMMs place with good *connectivity* (OmniLayout RR up to 0.95) but bad *pad-level legality* (79.82% overlap) — they belong at the intent level.
- **Weak anchors win**: VeoPlace's VLM regions help at λ_A = 0.01 and over-constrain at 0.1–1.0; random regions hurt, so the semantics matter. Images are optional (text-only vs image-only differ <0.8%).
- Persist the LLM's relations as the re-solvable design-intent artifact (RAC: 89.5% re-solve pass after resizes; PCB-Migrator).

## Key facts

**PCBAgent** (ASP-DAC'25; HKUST/Huawei/CUHK; [PDF](https://www.cse.cuhk.edu.hk/~byu/papers/C247-ASPDAC2025-PCBAgent.pdf) [P], VP-verified)
- Formulation: min HPWL + λ/NSLW s.t. overlap = beyond-boundary = insufficient-spacing = 0. **Surface Layer Wire**: 2-pin connection fanning toward the nearest edges, crossing no component, with overlapping pad projections.
- RL: decision transformer (ChiPFormer GPT setup), 128×128 grid; state = view/position/wire masks **for each of 4 rotations** + next part size; position mask = boundary OR spacing (logit penalty); bonus −0.01 for pad-aligned/min-spacing cells; HPWL-threshold pruning; r_t = HPWL_{t−1} − HPWL_{t−2}; trajectory score 1000/HPWL + 0.01·NSLW; only hard-legal trajectories enter a prioritized replay buffer (64, batch 8, weights exp(score/α)).
- Order: chips first, then pad-attached parts clockwise from the pad tied to the highest-weight part (weight = size, net count, pad level); chip-centred order cut HPWL 30%/22% vs net-count/area orders.
- LLM agent (model, prompts, tools unnamed): statement obtainment → semantic understanding → tool invocation → command generation; tools find deviating parts; RL score and replay weights are adjusted and **online fine-tuning re-runs on violating parts only**.
- Results: 17 industrial boards (18–414 parts, density 0.33–0.76), legal on all; HPWL 1.04×, NSLW 0.94× manual vs MaskPlace 1.13×, ChiPFormer 1.33×, MILP 2.05× (baselines' spacing legality 0); LLM rounds +39.6% NSLW in 2–3 rounds; "90% of manual quality". Independent: most vias (94.4) in ModuPlace; RR 0.42 in OmniLayout.

**ModuPlace** (DAC'26; CUHK; [PDF](https://yhhan.com/PDFs/ModuPlace_paper.pdf) [P], VP-verified)
- Agent 1 builds a **Hierarchical Modular Tree** from the schematic (RAG over guidelines; recursive split until no leaf exceeds a confidence threshold; netlist heterogeneous graph with sub-circuit matching simplifies the netlist).
- Agent 2 (Qwen-2.5-7B) writes a **Comprehensive Constraint Graph** per HMT layer: edges carry relative offset (x̂, ŷ), rotation offset θ̂, weight w; not limited to adjacent pairs. SFT on **426 expert CCGs** (loss λ1·HPWL + λ2·crossings − λ3·GraphSAGE similarity); customized **GRPO** (36 CCGs/input in groups of 4; advantage ω1·z(HPWL) + ω2·z(crossings) + ω3·e^(−r̂) with r̂ from a **GNN reward trained on pairwise expert rankings**; CCG equivalence test). λ/ω/γ/τ/ψ unpublished; 4×A100.
- Placer: module sizing min t1·BBox + t2·ΣHPWL over 4 rotations; per layer min Σw_ij[γ1·|offset error| + γ2·|angle error|] + γ3·parent overlap + γ4·HPWL; C++/Boost overlap-free detail.
- 11 boards (35–97 parts), PcbRouter + Freerouting multi-config averages, ADS IL/XT. Averages WL/vias/IL/XT: **ModuPlace 1266.5/48.6/5.40/−41.83**; SA-PCB 1528.5/81.7/6.52/−39.22; NS-Place 1490.2/71.5/6.89/−36.25; DeepPCB 1484.6/48.8/7.81/−39.99; PCBAgent 1477.3/94.4/6.62/−38.28. Wins **only on averages** (PCBAgent shorter WL on P6/P8; SA-PCB fewer vias on P8/P9; DeepPCB shorter on P5).
- Ablations: removing HMT hurts most; w/o SFT +35.1% WL/+66.2% vias; w/o GRPO +25.4%/+53.1%. Zero-shot CCG generators (WL/vias): Qwen-2.5-7B 1928.7/97.3, DeepSeek-R1-32B 1824.8/94.6, GPT-4o 1756.8/84.6, Claude-3.5-Sonnet 1707.5/92.1. "Directly generating placement files may lead to severe hallucination problems."

**Li, Peng, Huang, Wu, Zhu — coarse-to-fine PCB placement** (DAC'26; survey description only, [arXiv 2606.19795](https://arxiv.org/pdf/2606.19795) [S]): multimodal serialization, topology-enriched retrieval, two grouping agents, group-aware global placement, constraint-graph/MILP legalization; on 6 industrial boards (same commercial router) routed WL/via gains **55%/73% vs a commercial placer, 34%/26% vs NS-Place, 15%/13% vs Quilter** — possibly the strongest LLM-in-loop PCB result.

**LLM as decision layer for refinement** (Xu et al., CAICE 2026, [DOI](https://doi.org/10.1145/3804601.3804665) [S]): after ECOs, conflicts are featurized (geometric severity, local congestion, part category, violation type); the LLM sets priority and repair strategy, heuristics do geometry; ~15% better resolution, >20% for high-priority conflicts.

**OmniLayout LMM findings** (details in [benchmarks-and-metrics](benchmarks-and-metrics.md)): high RR but pad overlap/OoB failures; structured text conflict lists beat image-based overlap inference; schematic context helps grouping.

**VeoPlace** (Harvard/Kempner + Google DeepMind, 8 authors; ICML'25 workshop → NeurIPS'26 main; [arXiv 2603.28733](https://arxiv.org/pdf/2603.28733) [P], VP-corrected)
- VLM (no fine-tuning) proposes one rectangle per macro on an 84×84 (ChiPFormer) or 512×512 (DREAMPlace) grid. ChiPFormer: out-of-region logits → −∞ (unconstrained fallback for ~20% of suggestions). DREAMPlace: quadratic anchor λ_A·Σ‖x_i − x̂_i‖²; **λ_A = 0.01 best**. ≤256 macros guided, largest/most connected first.
- Loop: 8 unguided rollouts → 1 VLM call returning 8 region sets → 8 guided rollouts (2,000 rollouts = 125 calls); overhead 2–7% wall clock, ~62 s/call, ~$7/run.
- Prompt output contract: **HISTORY SUMMARY** (archetypes, largest-macro analysis, ≥3 principles marked "hypothesis" if weak) → **STRATEGY** (exactly one change to the best archetype, "exploratory" if weak) → **REGIONS** (largest first). Context = **Top Stratified** (K-means on placements, rank-softmax τ = 0.43 over cluster bests, top-C of one cluster); greedy-best context worst.
- Results: DREAMPlace improved on all 8 Superblue designs (**0.5–4.4%**, Gemini 3.6 Flash); ChiPFormer 9/10 benchmarks (peak −32.2%, Gemini 2.5 Flash); **Qwen3-VL 8B/30B-A3B match Gemini**; no-image/no-text/shuffled <0.8% change; random regions sharply degrade; anchor-to-best ≈ DREAMPlace alone.

**MAGE** (UCSD, VLSI, Claude Opus 4.6; [arXiv 2607.18536](https://arxiv.org/pdf/2607.18536) [P]): 6 phases/8 sub-agents — retrieval; **families of structurally similar groups**; group boxes with mandatory flyline-render visual gate (stop <2% or 5 iterations); feasibility (area, packing, channel spacing; recursive split); **reference placement per family, then transform-and-merge**; stateless independent auditor; optional Go-With-The-Winners tournament. vs commercial placers +29.7% rWL, +3.8–4.5% power; vs human "comparable"; vs Hier-RTLMP −9.8% rWL. Removing vision worsens WNS 40.5% and TNS 133% (rWL +2.3%). $220–509 per tournament, ~10 h.

**Trace** (commercial, KiCad): Claude analyzes schematic (groups, critical nets, thermal, edge parts, proximity rules) → floorplan variants → SA [S].

**Hierarchy recipe** (HiePlace, PA-ICM, PCBAgent, Lim, DRLPlace, ModuPlace, MAGE): core IC central → crossing-minimizing ring of first-priority satellites → pack remaining parts in module regions → place modules relative to each other → legalize exactly. KiCad hierarchy sources: schematic sheets, netlist "IC + pin-satellite" clusters, proven sub-layouts via subgraph matching.

**Steerable representations** an LLM can author or read: weighted multi-term costs (Cypress JSON knobs + tuner, PA-ICM α/β/γ, Hier-RTLMP weights); declarative constraints (ALIGN JSON, HiePlace priorities/spacing/alignment); hierarchy and relative-position graphs (HMT/CCG, offset constraint graphs, NS-Place relative positions); region anchors/fences; orders/seeds; raster masks; conflict lists with features. A KiCad AI guide warns API moves skip courtyard checks — run DRC each pass ([pcbeditor.com](https://pcbeditor.com/kicad-ai) [S]).

## Recommendations for our system
- **Typed relation bundle as the LLM's only write API** (ordinal magnitudes, joint realization; RAC/VP synthesis): `group`, `region(group, rule_area)`, `side(part, top|bottom)`, `near(part, part.pin, tight|close|loose)`, `ring(ic, refs, priority)`, `align`, `order`, `symmetric(a, b, axis)`, `board_edge`, `orient_toward`, `keepout`, `spread(heat)`, `away_from`, `loop_compact(nets)`, plus hard `fixed`, `on_edge`, `inside`, `clearance`, `rot_allowed`. Compile each soft relation twice (penalty + exact constraint) ([analog](analog-constraint-placement.md), [legalization](legalization.md)) [I].
- **Hierarchy first**: KiCad sheets → netlist clusters → LLM names modules and sets side, region/edge, adjacency; RAG over datasheet layout sections; optional subgraph-matched reuse [I].
- **LLM assigns sides** ([sides](sides-thermal-emc-reuse.md)); calibrate tight/close/loose mm per component class from human boards (e.g., PCBWorld D3) [I].
- Feedback: multi-tier metric report + **structured text conflict list with features and admissible relaxations**; incremental re-optimization of affected parts only (PCBAgent) [I].
- Port VeoPlace: VLM/LLM proposes regions per functional block → weak anchors or KiCad rule areas/rooms; reuse its 3-section output contract and Top-Stratified context; include a random-region control; run locally with an 8B open VLM [I].
- Exploit repeated channels MAGE-style (place one, replicate by transform) [I].
- Fine-tuning path: mine CCG-like relative-offset graphs from human boards; GNN preference reward from pairwise expert rankings [I].
- Images later: text/relation channel first; renders for structure-level critique only [I].

## Conflicts and open questions
- No study compares LLM-authored vs expert-authored PCB constraint sets beyond ModuPlace's graph similarity and OmniLayout's relational metric.
- No published system yet combines frontier LLM + constraint DSL + PCB-aware analytical engine + router-in-the-loop on an open benchmark; RAC tasks are small/synthetic.
- PCBAgent's and ModuPlace's prompts/code are unreleased; mm calibration of ordinal classes is unpublished.

## Sources
- research notes: [placement_algorithms.md § Q3, Q5, Q6, Q8](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/placement_algorithms.md); [verification_papers.md § 2.2, 2.3, 2.6, 2.8, 2.12, § 3](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_papers.md); [cross_domain_ideas.md § Q7](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/cross_domain_ideas.md)

See also: [scene-layout-transplants](scene-layout-transplants.md) · [routing/llm-routing-evidence](../routing/llm-routing-evidence.md) · [analog-constraint-placement](analog-constraint-placement.md) · [benchmarks-and-metrics](benchmarks-and-metrics.md)
