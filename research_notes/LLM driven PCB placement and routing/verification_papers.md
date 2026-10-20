# Verification of Key Paper Claims and Implementation Deep-Dives: LLM-Driven PCB Placement and Routing

_Compiled 2026-10-20, with full internet access. Primary sources were read directly: arXiv PDFs (full text, including appendices), the ICLR 2026 proceedings PDF, the authors' PDFs for PCBAgent, ModuPlace and HiePlace, the Cypress ISPD 2025 slides, the PCBWorld and PCBWorld-Engine repository docs, NeurIPS/ICML virtual-site pages, and Crossref/Semantic Scholar metadata for venue checks._

_Not reachable: (a) the Cypress paper PDF and two UCSD/Cornell pages, because those hosts serve an incomplete TLS chain and TLS verification was not disabled; (b) ACM DL and Springer full texts (403 or bot challenge); (c) GitHub API calls for repositories not attached to this session. Raw README and doc files from raw.githubusercontent.com were readable._

_Status tags:_
- **VERIFIED**: matches the primary source.
- **CORRECTED**: the notes are wrong or materially imprecise; the corrected value is given.
- **NOT FOUND**: could not be confirmed in any primary source.
- **RESOLVED**: a gap in the notes that is now answered.
- **NEW**: an implementation detail or paper the notes did not have.

---

## 1. Corrections table (claim in existing notes → verified value → source)

### Takeaway
Most headline numbers in the notes are correct. The errors cluster in five areas:
- **PCBWorld's LLM interface and timing.** The prompt carries no reward and no DRC list, and the "0.43 s for routers" figure is wrong.
- **Affiliations and venues.** VeoPlace is not Microsoft Research, and OmniLayout is not led by MSR.
- **Brown scene papers.** The notes treat one work as two.
- **"No numbers or ablations found".** LayoutCopilot has headline numbers and MAGE has a vision ablation.
- **Source attribution.** The OmniRouting <13% figure came from the wrong paper.

Two open questions in the notes are now resolved: the PCBWorld 679-vs-164 board count, and the identity of the "Li et al." LLM-PCB placer.

### Cited Findings

| # | Claim in notes (file) | Status | Verified value | Source |
|---|---|---|---|---|
| 1 | PCBWorld LLM agent gets "board state, legal actions (7 actions), and reward fed back each turn" (llm_for_eda §1) | **CORRECTED** | There are 6 action types plus an internal `idle` fallback, giving 7 parser indices. The per-step prompt contains: the S-expression board state; a 2-turn action history with `[no effect]` tags; a rejection-streak line; and the verbs valid in the current router phase. **No reward and no DRC-violation list appear in the prompt.** Table 7 says DRC is "reward signal only, not echoed in the prompt". Responses are capped at 256 tokens (512 for Qwen), and episodes at T = 200 steps. | [PCBWorld v4 App. E Tab. 7, App. H.1, M.1, Tab. 14](https://arxiv.org/pdf/2607.05915) |
| 2 | "GPT-5.4 took 94.04 s versus 0.43 s for routers and PPO on D2" (llm_for_eda §3) | **CORRECTED** | 0.43 s is PPO only. On D2, Freerouting took 2.69 s, KRT 0.82 s and OrthoRoute 2.54 s per board. | [PCBWorld Tab. 3](https://arxiv.org/pdf/2607.05915) |
| 3 | LLM agents are "about 200× slower" (llm_for_eda §3, §8) | **CORRECTED (qualified)** | On D2, GPT-5.4 is 219× slower than PPO but 35× slower than Freerouting. On D3-A (231.15 s) it is 126× slower than PPO (1.83 s), 33× slower than Freerouting (7.09 s) and 356× slower than KRT (0.65 s). | [PCBWorld Tab. 3](https://arxiv.org/pdf/2607.05915) |
| 4 | "~100× slower than a small RL policy or a classical router (1.83 s vs 231 s on D3-A)" (routing §Q3) | **CORRECTED (qualified)** | 126× versus PPO, but only 33× versus Freerouting. | [PCBWorld Tab. 3](https://arxiv.org/pdf/2607.05915) |
| 5 | Table 3 values: Freerouting CP 1.00/0.80/0.78; GPT-5.4 0.96/0.65/0.00; PPO 1.00/0.86/0.45; PPO w/o finish D3-A 0.94; KRT 1.00/0.74/0.20; mini 0.58/0.28; Qwen 0.33/0.34 | **VERIFIED** (arXiv v4, 11 Sep 2026) | The notes omit GPT-5.4-nano: CP 0.55 on D2 and 0.30 on D3-A. Freerouting's D3-A routability is only 0.91, so it left nets unrouted on some small boards. | [PCBWorld Tab. 3, Tab. 21](https://arxiv.org/pdf/2607.05915) |
| 6 | OrthoRoute "2% (routability 51%) on D3-A" (routing §Q1) | **CORRECTED** | Routability was 0.53 on D3-A, with CP 0.02, 99.7 mean DRVs and 26.97 vias. OrthoRoute ran at its default 0.4 mm grid pitch, and **the board's design rules were not enforced**, so the comparison is structurally unfavourable to it. | [PCBWorld Tab. 21, App. K (OrthoRoute note)](https://arxiv.org/pdf/2607.05915) |
| 7 | "679 real boards… PCBench README says 164 boards; unresolved" (routing §Q3 gaps) | **RESOLVED** | D3 comes from PCBench's `PCBs_version_9` pool of **1,182** boards converted to KiCad 9. A compatibility pass edited only `.kicad_pro` severities and floors; the board files were verified byte-identical. **679** boards survived the pass. They are split by pad count into D3-A (100 boards, ≤31 pads), D3-B (287 boards, ≤100 pads) and D3-C (292 boards). | [PCBWorld App. O.3–O.5](https://arxiv.org/pdf/2607.05915) |
| 8 | Freerouting D3-B row "denominator not verified" (llm_for_eda §7, via kicad-tools PR) | **RESOLVED** | Freerouting and RL rows are means over **4 seeds**, which is why 0.78 appears on 10 boards. Every method uses the same **99 D3-A boards** (one of the 100 cannot be loaded) and **10 D3-B boards**. The D3-B boards are all two-layer, one lower-median board from each of 10 pad-count quantile bins. LLM rows are a single best-of-5 run with no seed repetition. | [PCBWorld §4.2, Tab. 3 caption, App. O.5](https://arxiv.org/pdf/2607.05915); [kicad-tools PR #6702](https://github.com/rjwalters/kicad-tools/pull/6702) |
| 9 | PCBWorld-Engine is a "GPLv3 KiCad fork" exposing PNS to Python (routing §Q3/§Impl) | **VERIFIED, with a conflict** | The engine repository contains "our modified copies of the upstream KiCad files", a headless RL router, a DRC fork and a pybind11 module `kicad_rl_router`. It runs as a child process that talks over a Unix socket. The paper's App. B calls L1 "the unmodified KiCad C++ engine", which contradicts the repository. | [PCBWorld-Engine README](https://github.com/LGAI-Research/PCBWorld-Engine); [PCBWorld README](https://github.com/LGAI-Research/PCBWorld) |
| 10 | Venue "KDD 2026 agentic-eval workshop" (llm_for_eda §1) | **VERIFIED** | "KDD 2026 Workshop on Evaluation and Trustworthiness of Agentic AI". The arXiv comments field says it is non-archival. | [arXiv abs](https://arxiv.org/abs/2607.05915); [README](https://github.com/LGAI-Research/PCBWorld) |
| 11 | Reward: concave DRV penalty from KiCad DRC, 38 checks (routing §Q3) | **VERIFIED + NEW detail** | The 38 checks are 35 stock error-level checks plus DANGLING_VIA, DANGLING_TRACK and NET_CONFLICT. The penalty is f_drv = 3·ln(1+x/2) + Σᵢ ln(1+xᵢ/2), where x is the number of dirty nets and xᵢ the violations on net i. The weights are λ_w = 0.002 and λ_v = 0.1. The shipped repository uses a "newer potential" that adds −unconnected, completion bonuses and a step penalty. | [PCBWorld App. G](https://arxiv.org/pdf/2607.05915); [ENVIRONMENT.md](https://github.com/LGAI-Research/PCBWorld/blob/main/docs/ENVIRONMENT.md) |
| 12 | ModuPlace numbers (placement §Q3): 17.14%/15.01% WL, 40.51%/32.02% vias, DeepPCB +17.22% WL, PCBAgent 14.26%/48.51%; ablations (w/o SFT +35.1% WL / +66.2% vias; w/o GRPO +25.4% / +53.1%); LLM comparison 25.82% / 42.56%; 426 CCGs; Qwen-2.5-7B; 11 boards | **VERIFIED** | One clarification: "outperforms all baselines across all metrics" holds **only on averages**. Per board, baselines win several cases: PCBAgent has shorter WL on P6 (419.7 vs 483.6) and P8 (586.7 vs 816.2); SA-PCB has fewer vias on P8 (12 vs 23) and P9 (20 vs 29) and shorter WL on P11 (1253.8 vs 1382.3); DeepPCB has shorter WL on P5 (1527.5 vs 1594.7). | [ModuPlace Tab. 2](https://yhhan.com/PDFs/ModuPlace_paper.pdf) |
| 13 | PCBAgent: "The LLM never updates the placement policy" (llm_for_eda §1) | **VERIFIED, with nuance** | The LLM does not train weights. Its commands make the RL agent reweight its trajectory score (Eq. 2) and the replay-buffer trajectory weights, then **re-run online fine-tuning (Alg. 2) on the violating components only**. The paper never names the LLM it used or lists its tool library. | [PCBAgent §5](https://www.cse.cuhk.edu.hk/~byu/papers/C247-ASPDAC2025-PCBAgent.pdf) |
| 14 | PCBAgent numbers (placement §Q3): HPWL 1.04×, NSLW 0.94× manual; baselines 1.13/1.33/2.05×; +39.6% NSLW in 2–3 rounds; sequence ordering −30%/−22% HPWL; 17 boards with 18–414 parts and density 0.33–0.76 | **VERIFIED** | Baseline legality rates (within-boundary, non-overlap, spacing): MaskPlace (0.29, 0.82, **0**), ChiPFormer (0.47, 0.59, **0**), MILP (0.12, 0.71, **0**). The conclusion's own summary is "90% of the quality of manual results". | [PCBAgent Tab. 1–4](https://www.cse.cuhk.edu.hk/~byu/papers/C247-ASPDAC2025-PCBAgent.pdf) |
| 15 | VeoPlace is "Google DeepMind; Uchendu & Goel" (llm_for_eda §1) | **CORRECTED** | Eight authors at Harvard/Kempner and Google DeepMind: Uchendu, K.-H. Lee, Goel, J. W. Jiang, Hou, Janapa Reddi, Songhori, Zhuang. | [arXiv v3](https://arxiv.org/abs/2603.28733) |
| 16 | VeoPlace is "ICML 2025; NeurIPS 2026 poster; **Microsoft Research**" (cross_domain §Q8) | **CORRECTED** | It was an ICML 2025 **workshop** poster (EXAIT) and is now a **NeurIPS 2026 main-conference** paper (v3 is the camera-ready). It is **not** Microsoft Research work. | [ICML 2025 EXAIT page](https://icml.cc/virtual/2025/51511); [NeurIPS 2026 poster](https://neurips.cc/virtual/2026/poster/153841); [arXiv abs comments](https://arxiv.org/abs/2603.28733) |
| 17 | VeoPlace uses a "frozen Gemini 2.5 Flash"; DREAMPlace gains "up to 4.3%" (llm_for_eda, placement) | **CORRECTED** | Gemini 2.5 Flash is used for the ChiPFormer track and **Gemini 3.6 Flash** for the DREAMPlace track. Open-weight **Qwen3-VL 8B and 30B-A3B match Gemini**. The DREAMPlace gain is 0.5–**4.4%** in v3 (19 Oct 2026). The 9/10 benchmarks and peak −32.2% figures for ChiPFormer are verified. | [VeoPlace v3 abstract, §5, Tab. 5](https://arxiv.org/pdf/2603.28733) |
| 18 | EvoPlace "IEEE TCAD 2026" (llm_for_eda, placement) | **VERIFIED** | TCAD, DOI 10.1109/TCAD.2026.3652945, published 2026-09 per Crossref. It uses GPT-4o. Generalized (not case-specific) gains are 0.509% (MMS) and 2.85% (ISPD2005); those are measured against DREAMPlace with the BB method. | [Crossref DOI](https://doi.org/10.1109/TCAD.2026.3652945); [arXiv 2504.17801 Tab. IV–V](https://arxiv.org/pdf/2504.17801) |
| 19 | OrderPlace ICML 2026; −34.04% / −14.08% (llm_for_eda) | **VERIFIED** | Published in the Proceedings of the 43rd ICML. The LLM is **claude-sonnet-4.5**. The metric is macro-placement HPWL on ISPD2005. | [arXiv 2606.08904](https://arxiv.org/pdf/2606.08904) |
| 20 | CoEvoP&R: "8 ChiP-Bench Nangate45 designs × 3 seeds, −16.9% rWL, −36.7% congestion, +0.70 ns WNS; Superblue −5.4% / −23.2%" | **VERIFIED** | The benchmark is spelled "ChiPBench". TNS also improves by 912 ns. The default LLM is **gpt-5.4**. | [arXiv 2607.17398](https://arxiv.org/pdf/2607.17398) |
| 21 | MAGE: "Pith notes +29.7% routed WL and about 4% higher power" (llm_for_eda §1, §7) | **VERIFIED, needs context** | That cost is **against the two commercial placers**: Comm-1 gave +29.7% rWL and +3.8% power; Comm-2 gave +29.7% rWL and +4.5% power. Against the **human expert**, rWL and power are "comparable". Against Hier-RTLMP, rWL is −9.8% and power −1.1%. The backbone is **Claude Opus 4.6**. | [MAGE §VI-A, §V](https://arxiv.org/pdf/2607.18536) |
| 22 | MAGE: "No ablation isolating the vision contribution was found" (llm_for_eda §6) | **CORRECTED** | Removing visual feedback worsens WNS by **40.5%** and TNS by **133.0%** and lowers the human-likeness score by 4.2%. rWL (+2.3%) and power (+0.4%) barely change (Ariane and BP on NG45, Table VI). | [MAGE §VI ablations](https://arxiv.org/pdf/2607.18536) |
| 23 | LayoutCopilot: "No headline numbers were found" (llm_for_eda §1) | **CORRECTED** | Command-generation correctness ("Overall"): **93.75%** average for multi-agent with instructions (Claude-3 96.80%, GPT-4 93.92%, GPT-3.5 90.92%), against 87.89% for multi-agent without instructions and 79.98% for single-agent. The venue, IEEE TCAD, is verified (DOI 10.1109/TCAD.2025.3529805). | [LayoutCopilot Tab. II](https://arxiv.org/pdf/2406.18873); [Crossref DOI](https://doi.org/10.1109/TCAD.2025.3529805) |
| 24 | PCB-Bench: Gemini-2.5-Pro 100% and GPT-5 90.9% on Basic Wiring Error Identification (BWEI); open-source models 45–55%; Claude-Opus-4.1 93.3% placement multiple-choice "unconfirmed" (llm_for_eda §2, §6) | **VERIFIED + caveat** | All values match Tables 2–3. The 93.30% is Claude-Opus-4.1 on **Placement Macro-level CQ** accuracy. Every BWEI score (45.45, 54.54, 72.72, 90.90, 100.00) is a multiple of 1/11, which implies the BWEI subset has only about **11 items** (my inference). Treat the 100% vs 90.9% gap as one question. | [PCB-Bench ICLR PDF Tab. 2–3](https://proceedings.iclr.cc/paper_files/paper/2026/file/051f3997af1dd65da8e14397b6a72f8e-Paper-Conference.pdf) |
| 25 | OmniLayout by "Microsoft Research et al."; evaluates "Claude-Sonnet-4.6, GPT-5.5, and Qwen3.6-35B-A3B" (llm_for_eda §1) | **CORRECTED** | Led by **Penn State** (corresponding author M. Gowda), with SJTU, Binghamton, independent researchers and **one** MSR co-author. It evaluates **9 LMMs**: GPT-5.5, GPT-5-mini, Claude Sonnet 4.6, Gemini 3.1 Pro-Preview, Gemini 2.5 Flash(-lite), LLaMA 4 Maverick, Ministral 14B, Qwen3.5-9B and Qwen3.6-35B-A3B. It also evaluates **6 PnR tools** (Quilter, PCBAgent, SA-PCB, NS-Place, Cypress, and Chen et al. DAC'25) against the human reference. | [arXiv 2607.03261 v3, Tab. 2](https://arxiv.org/pdf/2607.03261) |
| 26 | OmniLayout: frontier models have "poor post-route wirelength and completion… even agentic" (llm_for_eda §1, §2, §7) | **VERIFIED, with an important nuance** | On FreeRouting routability (RR), zero-shot scores are GPT-5.5 **0.90**, GPT-5-mini 0.84 and Claude Sonnet 4.6 0.76. Gemini 3.1 Pro scores only 0.34 zero-shot but 0.91–0.92 when given the schematic netlist or image. GPT-5.5 few-shot reaches 0.95, while the Qwen models score 0.31 zero-shot. The best LMM settings are *above* the academic placers in the same table (SA-PCB 0.25, NS-Place 0.23, Cypress 0.33, PCBAgent 0.42, Chen et al. 0.62) and comparable to Quilter (0.84). The human reference is 1.00. The weaknesses that do hold: 79.82% of outputs had at least one pad overlap; 72.89% had at least one part out of bounds; 80% of parts were placed on top; reference similarity was below 60%; the best end-to-end pass rate was 62.6% (GPT-5.5 few-shot). | [OmniLayout Tab. 2, §5.2–5.3](https://arxiv.org/pdf/2607.03261) |
| 27 | OmniLayout/OmniRouting are "EMNLP Findings 2026" (constraints_verification_benchmarks) | **NOT FOUND** | Neither the arXiv v3 PDF nor the abstract-page comments mention a venue. | [arXiv abs](https://arxiv.org/abs/2607.03261) |
| 28 | OmniLayout has "no data license; papers CC BY-NC-ND 4.0" (constraints_verification_benchmarks) | **CONFLICT** | The ethics statement says "the code and dataset are publicly released under the **CC-BY-4.0** license". The arXiv *paper* license is CC BY-NC-ND 4.0. The third-party finding of dead links (2026-08-15) was not re-checked. | [OmniLayout Ethics Statement](https://arxiv.org/pdf/2607.03261); [arXiv abs](https://arxiv.org/abs/2607.03261) |
| 29 | OmniRouting "<13% clean net routability vs about 94% for humans", cited to a Pith summary of **2607.03261** (constraints_verification_benchmarks) | **VERIFIED, wrong source** | OmniRouting itself reports a best zero-shot NRR/PRR of **12.60% / 15.41%**, against **93.58% / 95.91%** for humans. The best agentic result is 27.98% / 30.34%. The open-source PcbRouter reaches 56.20% / 71.37%. | [OmniRouting arXiv 2608.04434](https://arxiv.org/pdf/2608.04434) |
| 30 | PCBInnoBench: 372 tasks; 22.0% vs 7.3% Pass@1 (llm_for_eda) | **VERIFIED** | NeurIPS 2026 poster. Authors are from SJTU (J. Yan) and Huawei Noah's Ark (Kai, Tang, Yuan). No arXiv version was found. | [NeurIPS 2026 poster](https://neurips.cc/virtual/2026/poster/139034) |
| 31 | HWE-Bench: 300 tasks, 2,914 datasheets, best 8.15% (netlist notes) | **VERIFIED** | The best model was Claude Sonnet 4.5 (8.15%), followed by GPT-5.2 (6.58%); others scored 4–5%. | [arXiv 2603.18102](https://arxiv.org/pdf/2603.18102) |
| 32 | GENIE-ASI at MLCAD 2025; F1 1.0 / 0.81 / 0.31 (netlist notes) | **VERIFIED** | MLCAD 2025, DOI 10.1109/MLCAD65511.2025.11189126, TUM plus Sony. Caveat: it targets **transistor-level op-amp SPICE netlists**, not PCB netlists. | [arXiv 2508.19393](https://arxiv.org/pdf/2508.19393); [Crossref DOI](https://doi.org/10.1109/MLCAD65511.2025.11189126) |
| 33 | PCBSchemaGen: "16k → ~300 tokens"; "topology-aware retrieval ablation" (llm_for_eda §3–4) | **VERIFIED, split across versions** | v2 (Jun 2026) states "~300 tokens of JSON" per IC entry. The 16k-token datasheet baseline and the topology-aware retrieval finding appear in **v1** (Feb 2026). v2 reports 227 tasks across 22 domains, with Gemma-4-31B passing 81.3% of PCBBench tasks. NeurIPS 2026 poster verified. | [v2](https://arxiv.org/abs/2602.00510v2); [v1](https://arxiv.org/abs/2602.00510v1); [NeurIPS poster](https://neurips.cc/virtual/2026/poster/149018) |
| 34 | PCBSchemaGen author slides: 86.3 / 84.0 / 61.0% (netlist notes) | **NOT FOUND** in paper | The v2 paper's headline is 81.3% on PCBBench (Gemma-4-31B). | [v2 abstract](https://arxiv.org/abs/2602.00510v2) |
| 35 | NS-Place: tagged [PP]; "best paper" (llm_for_eda §7; placement) | **CORRECTED tag / VERIFIED award** | It is peer-reviewed (ASP-DAC'22, pp. 288–293). IEEE CEDA lists it among the **2022 ASP-DAC Best Paper Award** winners. The *average* routed-WL gain is 10% vs manual and 6% vs GDMILP; "up to 25%" is the peak. Vias drop 18% vs manual and 39% vs GDMILP. Evaluation used **FreeRouting**, with a 4 h MILP time limit. | [arXiv 2210.14259](https://arxiv.org/pdf/2210.14259); [IEEE CEDA awards](https://ieee-ceda.org/paper-award/asp-dac-best-paper-award) |
| 36 | HiePlace: TCAD 45(1), Jan 2026; 7.7× speed-up; 66% cost reduction; −16% WL; −46% misaligned regions (placement) | **VERIFIED** | 19 benchmarks (15 industrial at about 0.80 density, plus 4 academic), solved with Gurobi in under 2 h. Note: the paper wrongly calls Quilter "a widely used open-source tool". | [HiePlace PDF](https://www.cse.cuhk.edu.hk/~byu/papers/J156-TCAD2026-HiePlace.pdf) |
| 37 | Cypress: "PDF could not be fetched"; benchmark "built from real commercial designs" (solver notes) | **RESOLVED (partially) / CORRECTED nuance** | Method details are now available from the authors' ISPD slides (see §2). The benchmark is "**synthesized** from real commercial designs": **10 small synthesized functional benchmarks** plus **5 commercial "big" designs**. The evaluator was Freerouting v1.9.0. DOI 10.1145/3698364.3705346. The slides say "Best Paper **Nominee**"; the award win itself comes from Cornell's news page, which could not be reached because of the TLS chain error. | [ISPD slides](https://ispd.cc/ispd2026/slides/2025/protected/3_1_slides.pdf); [SIGDA ISPD'25 TOC](https://www.sigda.org/publications/ispd-25-toc/) |
| 38 | Lee et al. (chip diffusion), ICML 2025: legality 0.88 → 0.997, HPWL −7.1% (2.976 vs 3.203), 20% below DREAMPlace (cross_domain, placement) | **VERIFIED** | Proceedings of the 42nd ICML. The 20% result is on **clustered** IBM. On ISPD-style mixed-size tests it beats DREAMPlace by 4% on average. | [arXiv 2407.12282 v3](https://arxiv.org/pdf/2407.12282) |
| 39 | Holodeck (2312.09067) and LayoutVLM (2412.02193) IDs "unverified" (llm_for_eda §2 gaps) | **VERIFIED** | Holodeck: CVPR 2024, 10 constraint types in 5 categories, DFS solver by default with MILP as an alternative. LayoutVLM: CVPR 2025. | [Holodeck](https://arxiv.org/abs/2312.09067); [LayoutVLM](https://arxiv.org/abs/2412.02193) |
| 40 | Brown "imperative vs declarative" (2504.05482) and "Procedural Scene Programs" (2510.16147) treated as two separate follow-ups; only the latter has LLM-free correction and the 82%/94% result; 2504.05482 authors unconfirmed (cross_domain §Q1) | **CORRECTED** | Both are versions of **one work** by the same Brown/UCSD group (Gumin, Han, Yoo, Ganeshan, Jones, Aguina-Kang, Morris, Ritchie; Fu is added in the SIGGRAPH Asia 2025 version). 2504.05482v2 **already contains** the LLM-free error correction and the 82%/94% result. The 94% is against **Holodeck** and the 82% against a declarative baseline, DeclBase. Precise figures: 82.9% and 94.3%. | [2504.05482](https://arxiv.org/abs/2504.05482); [2510.16147](https://arxiv.org/abs/2510.16147) |
| 41 | J. Supercomputing 2025 MAPF/CBS PCB routing paper exists; benchmark numbers not retrieved (cross_domain §Q4) | **VERIFIED (existence) / NOT FOUND (numbers)** | Jianhao Cao, Hao Cai, Ning Xu, "PCB routing on unstructured meshes with conflict-based search", *J. Supercomputing* 81(9), article 1063, June 2025. The method is "UGPCB-CBS" on Delaunay grids. The publisher elides the abstract, and Springer's full text is behind a bot challenge. | [Crossref](https://api.crossref.org/works/10.1007/s11227-025-07569-0); [Semantic Scholar](https://api.semanticscholar.org/graph/v1/paper/DOI:10.1007/s11227-025-07569-0); [DOI](https://doi.org/10.1007/s11227-025-07569-0) |
| 42 | RL_PCB "outperforms SA by up to 21% over three unseen circuits" (placement §Q3, from thesis summary) | **CORRECTED/refined** | The DATE'24 abstract says that on unseen circuits, TD3 and SAC policies give **on average 17% and 21%** lower post-routing wirelength than SA. It was trained on 6 circuits. The full text is restricted. | [UM OAR record](https://www.um.edu.mt/library/oar/handle/123456789/131782); [RL_PCB README](https://github.com/LukeVassallo/RL_PCB) |
| 43 | TILOS/Cheng et al.: TCAD update; SA beat CT 17/17 on proxy and 16/17 on HPWL (ICCAD04); 4/6 and 5/6 on modern designs; 12.5 h SA (placement) | **VERIFIED** | v3 is titled "An Updated Assessment of RL for Macro Placement" (10 Mar 2026) and is "accepted and published in IEEE Transactions on CAD". The ICCAD04 counts come from the ISPD'23 version (v2). v3 drops ICCAD04 and adds CT-Ariane-X4 (532 macros), where SA beats AlphaChip. Proxy cost "correlates weakly" with post-route PPA. | [v3](https://arxiv.org/abs/2302.11014); [v2](https://arxiv.org/abs/2302.11014v2) |
| 44 | Handoff survey "Li et al." placement paper: identity and PCB-vs-IC unresolved (llm_for_eda §1 gaps) | **RESOLVED** | J. Li, K. Peng, F. Huang, H. Wu, Z. Zhu, "A coarse-to-fine PCB placement framework via LLM-guided component grouping and group-aware placement," **DAC 2026**. It is a PCB paper. On 6 industrial boards routed by the same commercial router, the survey reports **routed-WL/via gains of 55%/73% vs a commercial placer, 34%/26% vs NS-Place, and 15%/13% vs Quilter**. | [arXiv 2606.19795 §4.2 and ref. 124](https://arxiv.org/pdf/2606.19795) |
| 45 | PCBWorld state and "observation encoding" not detailed (implicit in routing notes) | **NEW** | The LLM view drops **copper zones (pours)**, collapses per-netclass rules into the single strictest envelope, keeps only xy plus layer for pads in S-expression mode, and rounds coordinates to 3 decimals in mm. On `net_select`, the environment pushes the resolved per-class width and via sizes into PNS. | [PCBWorld App. E Tab. 7](https://arxiv.org/pdf/2607.05915) |

### Inferences
- The most consequential correction for system design is #1. PCBWorld's LLM agents routed **without seeing DRC violations or rewards**; they saw only rejection and no-effect tags. Its LLM numbers are therefore a lower bound for a better-instrumented agent, not a ceiling.
- #26 changes the story for placement. Under OmniLayout's FreeRouting-routability metric, frontier LMMs are not worse than the academic PCB placers. Both groups trail humans and Quilter. The real LMM failure is geometric legality at pad level, not connectivity awareness.

### Gaps
- The Cypress full paper (exact loss weights and legalizer details) could not be read: the Cornell host's TLS chain is incomplete, ACM returned 403, and there is no arXiv version. Details here come from the authors' slides and the abstract.
- Neither the abstract nor results of the J. Supercomputing CBS paper are accessible.
- The kicad-tools "fair-95" D3-A subset mentioned in its PR is not a PCBWorld construct. The paper uses 99 boards.

---

## 2. Per-paper deep dives (implementation-relevant details)

### Takeaway
Read in full, three papers give the most reusable engineering detail:
- **PCBWorld**: exact API, observation, reward, prompt and cost data.
- **RAC** (Oct 2026, new): relational actions beat coordinates and candidate selection on PCB tasks for all 9 models tested.
- **Cypress**: differentiable net-crossing and orientation terms.

ModuPlace and PCBAgent describe their LLM interfaces only at a high level. Neither releases prompts, code or hyperparameters, and PCBAgent does not name its LLM.

### Cited Findings

#### 2.1 PCBWorld (arXiv 2607.05915 v4; LG AI Research; KDD'26 workshop, non-archival) — VERIFIED
**Stack.** There are four layers:
- **L4**: a Gymnasium facade (action dispatcher, observation builder, reward potential composer, action mask).
- **L3**: a Python wrapper exposing **58 step-level APIs**. Main-text partition: 14 PNS::ROUTER, 28 DRC/board-state, 16 utilities. Table 6 partition: 25 Action / 25 State / 3 Reward / 5 Utility.
- **L2**: a pybind11 binding.
- **L1**: the KiCad 9.0.8 engine.

Engine calls run in a separate GPLv3 process. — [PCBWorld App. B–C](https://arxiv.org/pdf/2607.05915); [PCBWorld-Engine README](https://github.com/LGAI-Research/PCBWorld-Engine)

**API groups.**
- Configuration: `set_routing_mode`, `set_corner_mode`, `set_track_width`, `set_via_diameter`, `set_via_drill`, `reset_via_mode`.
- Routing: `start_route`, `move`, `fix_route`, `cancel_route`, `finish`, `undo_last_segment`, `flip_posture`, `toggle_via`, `switch_layer`.
- Dragging: `start_drag`, `fix_drag`, `cancel_drag`.
- Rework: `delete_track_by_index`, `delete_track_near`, `delete_via_by_index`, `delete_via_near`.
- State: `get_tracks`, `get_vias`, `get_pads`, `get_ratsnest`, `get_board_outline`, `get_design_rules`, `get_netclass_for_net`, …
- Reward: `get_drc_violation_count`, `get_drc_violations`, `get_reward_snapshot`.

— [PCBWorld Tab. 6](https://arxiv.org/pdf/2607.05915)

**Action space exposed to agents.**
- `net_select(net_id)`
- `start_route(x, y, layer)`
- `make_line(x, y, routing_mode)`
- `make_via(x, y, routing_mode)`
- `finish(routing_mode)`: completes to the Euclidean-nearest unconnected pad on the current layer.
- `net_end`
- `idle`: no-op fallback.

`routing_mode` takes 0 = mark obstacles, 1 = shove, 2 = walk around. **Rework (delete) APIs exist but are excluded from the agent action space.** An FSM mask enforces net_select → start_route → routing. — [PCBWorld Tab. 1, §3.2, App. H](https://arxiv.org/pdf/2607.05915); [ENVIRONMENT.md](https://github.com/LGAI-Research/PCBWorld/blob/main/docs/ENVIRONMENT.md)

**Candidate points.** The pool is built per step from the active net:
- its pads (through-hole pads get one entry per layer);
- its track endpoints and via centres;
- open ratsnest targets;
- an **8-way grid of 0.5 mm offsets around the router head**.

The pool is deduplicated by (x, y, layer) and capped at 64. The RL policy can only point into this pool. The LLM is "prompted toward the same points but may emit free coordinates" for detours, constrained by a guided-decoding regex. — [PCBWorld App. E, H.2](https://arxiv.org/pdf/2607.05915)

**Observation.** A nested dict with these blocks:
- `board_static`: bbox, layer count, edges, nets→pads, net-less obstacles, board constraints.
- `routing_geometry`: tracks, vias and open points per net.
- `router_head`
- `drc_violations` (near the head)
- `action_history`
- `closed_nets`

The LLM sees it as an S-expression, e.g. `(net 1 "NET1" (pads (pad D0 10.000 10.000 1) …))`. The system message holds the static block, to suit prefix caching. The per-step user message holds routing_geometry plus router_head, a 2-turn history, any rejected attempts, and the valid verbs. The output contract is exactly one `<think>…</think><action>…</action>` pair, ASCII only, with a strict parser that falls back to idle on failure. — [PCBWorld App. H.1, M.1](https://arxiv.org/pdf/2607.05915); [ENVIRONMENT.md](https://github.com/LGAI-Research/PCBWorld/blob/main/docs/ENVIRONMENT.md)

**Prompt guidelines (verbatim themes).**
- Priority order: (1) complete all connections, (2) avoid DRC, (3) minimise wirelength.
- Use exact observed coordinates and invent coordinates only for detour waypoints.
- Place layer-change vias **≥1 mm from any pad, never on a pad**.
- Never reach a target pad's xy while on the wrong layer, because that traps the agent.
- Prefer `finish` when a clear path exists.

— [PCBWorld Fig. 24](https://arxiv.org/pdf/2607.05915)

**Reward and metrics.**
- Φ(s) = −f_drv(s) − λ_w·WL − λ_v·vias, as in row 11.
- The terminal reward is Φ(s_T) − Φ(s_0); a per-step shaping variant telescopes to the same value.
- Clean Pass = full connectivity **and** 0 error-level DRVs on the rollout with the highest potential gain, out of 5 rollouts (@5).
- Time is averaged over all 5 rollouts.
- Parse-fail is the share of boards where no rollout loads.
- A board can clean-pass while still carrying the 3 promoted warnings (dangling track or via, net conflict).

— [PCBWorld §4.3, App. G, I](https://arxiv.org/pdf/2607.05915); [METRICS.md](https://github.com/LGAI-Research/PCBWorld/blob/main/docs/METRICS.md)

**Datasets.**
- D1: grid replica of Jumanji Connector, G ∈ {10, 50, 100, 200, 500}, split 10k/128/128.
- D2: synthetic gridless, 2 layers, 4–6 nets, 8–21 pads, split 10k/128/128.
- D3: 679 real boards (see row 7). D3-C (6–451 nets, up to 2,103 pads, 2–8 layers) is a reserved challenge split that has not been evaluated.

— [PCBWorld Tab. 2, App. O](https://arxiv.org/pdf/2607.05915)

**Full baseline table (Table 21, @5).** Columns are CP / Pot. / Rout. / DRV / WL (mm) / Vias / Time (s).
- **D2:**
  - Freerouting 1.00 / 15.47 / 1.00 / 0.00 / 393.9 / 2.32 / 2.69
  - OrthoRoute 0.01 / 0.38 / 0.34 / 8.54 / 323.4 / 11.30 / 2.54
  - KRT 1.00 / 15.52 / 1.00 / 0.00 / 373.9 / 8.09 / 0.82
  - GPT-5.4 0.96 / 16.05 / 1.00 / 0.05 / 401.4 / 1.61 / 94.04
  - GPT-5.4-mini 0.58 / 12.45 / 0.86 / 1.40 / 370.8 / 2.07 / 33.93
  - GPT-5.4-nano 0.55 / 12.23 / 0.85 / 1.45 / 364.6 / 1.91 / 63.39
  - Qwen3.5-397B 0.33 / 9.77 / 0.74 / 2.48 / 325.0 / 1.56 / 47.58
  - PPO 1.00 / 16.24 / 1.00 / 0.00 / 423.8 / 1.70 / 0.43
  - GRPO 1.00 / 14.03 / 1.00 / 0.00 / 581.2 / 6.31 / 1.16
  - PPO-terminal 0.92 / 15.61 / 0.98 / 0.16 / 432.9 / 1.63 / 1.37
  - PPO w/o finish 1.00 / 16.21 / 1.00 / 0.00 / 439.4 / 1.48 / 0.88
- **D3-A:**
  - Reference 1.00 / 23.16 / 1.00 / 0 / 170.2 / 1.18
  - Freerouting 0.80 / 22.71 / 0.91 / 0.86 / 156.2 / 0.74 / 7.09
  - OrthoRoute 0.02 / −6.16 / 0.53 / 99.70 / 129.8 / 26.97 / 2.20
  - KRT 0.74 / 20.00 / 0.94 / 2.38 / 142.8 / 3.69 / 0.65
  - GPT-5.4 0.65 / 19.42 / 0.91 / 1.31 / 150.8 / 2.09 / 231.15
  - mini 0.28 / 14.22 / 0.72 / 3.88 / 127.0 / 0.39 / 56.85
  - nano 0.30 / 14.16 / 0.73 / 3.84 / 129.1 / 0.45 / 100.76
  - Qwen 0.34 / 14.88 / 0.75 / 3.63 / 121.0 / 0.47 / 81.82
  - PPO 0.86 / 21.46 / 0.95 / 0.89 / 165.4 / 0.92 / 1.83
  - GRPO 0.85 / 18.83 / 0.98 / 0.46 / 279.0 / 9.39 / 3.54
  - PPO-terminal 0.82 / 21.02 / 0.95 / 0.67 / 171.3 / 2.61 / 2.58
  - PPO w/o finish 0.94 / 21.78 / 0.99 / 0.21 / 224.1 / 2.16 / 3.05
- **D3-B:**
  - Reference 1.00 / 63.96 / 1.00 / 0 / 570.3 / 6.70
  - Freerouting 0.78 / 61.06 / 1.00 / 10.60 / 535.4 / 3.48 / 9.94
  - OrthoRoute 0.00 / −10.25 / 0.44 / 188.2 / 370.0 / 39.8 / 9.30
  - KRT 0.20 / 40.94 / 0.86 / 44.7 / 472.3 / 11.8 / 3.27
  - GPT-5.4 0.00 / 34.72 / 0.62 / 17.3 / 347.1 / 3.6 / 865.83
  - mini 0.00 / 30.84 / 0.61 / 17.6
  - nano 0.00 / 30.66 / 0.59 / 18.6
  - Qwen 0.00 / 25.99 / 0.51 / 21.2
  - PPO 0.45 / 50.20 / 0.85 / 8.28 / 668.6 / 6.17 / 10.77
  - GRPO 0.10 / 30.00 / 0.69 / 15.82
  - PPO-terminal 0.38 / 44.33 / 0.81 / 10.18
  - PPO w/o finish 0.42 / 46.45 / 0.87 / 7.85

— [PCBWorld Tab. 21](https://arxiv.org/pdf/2607.05915)

**Engine-engagement ablation (Table 4, D3-A).** Columns are CP / Pot. / Rout. / DRV / Parse-fail.
- GPT-5.4: interactive 0.65 / 19.42 / 0.91 / 1.31 / 0; plan-and-execute 0.19 / 12.14 / 0.81 / 16.28 / 0; engine-free 0.02 / 0.76 / 0.55 / 34.58 / 0.
- GPT-5.4-mini: interactive 0.28; plan-and-execute 0.19; engine-free 0.02.
- GPT-5.4-nano: interactive 0.30; plan-and-execute 0.18; engine-free 0.00, with Parse-fail 0.10.

— [PCBWorld Tab. 4](https://arxiv.org/pdf/2607.05915)

**LLM serving and cost.**
- Models: GPT-5.4, mini and nano via the OpenAI API with hidden reasoning; Qwen3.5-397B-A17B in FP4 via Together with thinking off.
- **Tokens per episode:** about 107k on D2, **about 425k on D3-A**, and **about 1.92M on D3-B** for GPT-5.4.

— [PCBWorld Tab. 14, 25–27](https://arxiv.org/pdf/2607.05915)

**Baseline configuration.**
- Freerouting 2.1.0 with `-mp 10` (max passes) and a 4 GiB heap; other options at JAR defaults.
- KRT: 0.1 mm grid, 200k A\* iterations, max rip-up 3, heuristic weight 1.9, "mps" ordering, via cost 50, turn cost 1000.
- OrthoRoute at commit f45dc68, 0.4 mm grid, board rules not enforced.

— [PCBWorld Tab. 18–20, App. K](https://arxiv.org/pdf/2607.05915)

**RL policy.**
- Decoder-only Transformer (d = 128, 4 layers, 8 heads), with Fourier features (32 frequencies, base 1.2) over 13 entity token types and a pointer network over the candidate pool.
- PPO: γ = 0.995, GAE λ = 0.95, 32 parallel environments, episode limit 256 steps, 300 iterations on one L40.

— [PCBWorld Tab. 15, App. H.2](https://arxiv.org/pdf/2607.05915)

**Qualitative failure modes.**
- **The first `net_select` often decides success.** Agents "rarely perform corrective recovery".
- Without delete/redraw actions, agents loop on reroute attempts once congestion appears.
- LLM failures map to DRC codes: via on pad (ANNULAR_WIDTH, HOLE_CLEARANCE); wrong-layer endpoint (DANGLING_TRACK); cross-net contact (SHORTING_ITEMS, CLEARANCE); detour over the board edge (EDGE_CLEARANCE); phantom waypoints (parse/mask rejection); repeated identical attempts.

— [PCBWorld App. N case studies, Tab. 11](https://arxiv.org/pdf/2607.05915)

#### 2.2 ModuPlace (DAC'26; Han, Li, Zhao, Fu, Ye, Chen, Yu, Ho; CUHK/CUHK-SZ/Index) — VERIFIED
**Pipeline.**
1. LLM Agent 1 builds a **Hierarchical Modular Tree (HMT)** from the schematic, with RAG over external design guidelines. Each module is split recursively until no leaf exceeds a confidence threshold (confidence elicitation per Xiong et al. 2024). A **netlist heterogeneous graph with sub-circuit matching** (TopoSizing-style) simplifies the netlist into a form the LLM can read.
2. LLM Agent 2 generates a **Comprehensive Constraint Graph (CCG)** per HMT layer.
3. A hierarchical placer consumes the CCGs.

— [ModuPlace §3.1–3.2](https://yhhan.com/PDFs/ModuPlace_paper.pdf)

**CCG format.** G = (V, E, W). Each edge carries:
- a relative position offset (x̂, ŷ), covering both absolute horizontal and vertical relationships;
- a rotation offset θ̂ (the ideal relative angle);
- a weight w.

Unlike the analog "mixed constraint graph", edges are not limited to adjacent pairs. — [ModuPlace §3.3](https://yhhan.com/PDFs/ModuPlace_paper.pdf)

**Fine-tuning.**
- Base model: Qwen-2.5-7B.
- **SFT** on **426 CCGs** extracted from expert placements. The loss is λ1·HPWL + λ2·net-crossings − λ3·GraphSAGE-embedding similarity to the reference CCG.
- **Customized GRPO:** 36 CCGs are generated per input, in groups of 4. The advantage is ω1·z(HPWL) + ω2·z(crossings) + ω3·e^(−r̂), where r̂ is a within-group rank from a **GNN reward model trained on pairwise expert rankings**.
- A **CCG equivalence test** (common-edge count ≥ τ and cosine similarity of common-edge weight vectors ≥ ψ) makes policy ratios computable.
- Hardware: 4×A100-80GB. **λ, ω, γ, τ, ψ values are not given**, and no code is released.

— [ModuPlace §3.3, §4.1](https://yhhan.com/PDFs/ModuPlace_paper.pdf)

**Placer.**
- Module sizing: minimise t1·BBox(C_q) + t2·ΣHPWL over θ ∈ {0, 90, 180, 270}.
- Each layer: minimise Σ w_ij·[γ1(|x̂_ij − x_ij| + |ŷ_ij − y_ij|) + γ2|θ̂_ij − θ_ij|] + γ3·(area overlap with the parent module) + γ4·HPWL.
- The final step is overlap-free detailed placement in C++/Boost.

— [ModuPlace Eq. 6–7](https://yhhan.com/PDFs/ModuPlace_paper.pdf)

**Evaluation.**
- 11 boards (35–97 parts, 21–81 nets, 2–4 layers, from OpenROAD and industry).
- Every placement was routed several times with PcbRouter and Freerouting under different configurations and averaged.
- Keysight ADS simulated insertion loss and crosstalk.
- Average WL/vias/IL/XT:

  | Method | WL | Vias | IL | XT |
  |---|---|---|---|---|
  | SA-PCB | 1528.5 | 81.7 | 6.52 | −39.22 |
  | NS-Place | 1490.2 | 71.5 | 6.89 | −36.25 |
  | DeepPCB | 1484.6 | 48.8 | 7.81 | −39.99 |
  | PCBAgent | 1477.3 | 94.4 | 6.62 | −38.28 |
  | **ModuPlace** | **1266.5** | **48.6** | **5.40** | **−41.83** |

— [ModuPlace Tab. 1–2](https://yhhan.com/PDFs/ModuPlace_paper.pdf)

**Ablation.** Removing the HMT gives the largest degradation on all four metrics. Removing the NHG, SFT or GRPO each hurts. **Zero-shot LLMs as CCG generators**, as WL / vias:

| Model | WL | Vias |
|---|---|---|
| Qwen-2.5-7B | 1928.7 | 97.3 |
| Qwen-3-14B | 1866.1 | 99.3 |
| InternLM-2.5-20B | 1874.6 | 96.7 |
| DeepSeek-R1-32B | 1824.8 | 94.6 |
| Claude-3.5-Sonnet | 1707.5 | 92.1 |
| GPT-4o | 1756.8 | 84.6 |

— [ModuPlace Tab. 3, Fig. 6](https://yhhan.com/PDFs/ModuPlace_paper.pdf)

#### 2.3 PCBAgent (ASP-DAC'25; Chen et al.; HKUST/Huawei Noah's Ark/CUHK) — VERIFIED
**Formulation.** min HPWL + λ/NSLW, subject to Overlap = BeyondBoundary = InsufficientSpacing = 0. The spacing constraint covers bodies and pads.

**Surface Layer Wire (SLW).** A 2-pin connection whose fan-out heads toward one of the two edges nearest each pad, crosses no other component, and whose pads overlap in horizontal or vertical projection. There are "3-type NSLWs" that users can request to increase. — [PCBAgent §2](https://www.cse.cuhk.edu.hk/~byu/papers/C247-ASPDAC2025-PCBAgent.pdf)

**RL agent.**
- A decision transformer, with an architecture following ChiPFormer's GPT setup.
- The board is scaled to a 128×128 grid.
- The state token concatenates view, position and wire masks **for each of 4 rotations** with the next component's size.
- Position mask = boundary mask OR spacing mask, applied by subtracting a large constant from logits.
- Bonus b = −0.01 for pad-aligned and minimum-spacing cells.
- HPWL-threshold action pruning.
- Step reward r_t = HPWL_{t−1} − HPWL_{t−2}.
- Trajectory score = 1000/HPWL + 0.01·NSLW.
- Only hard-legal trajectories enter a prioritized replay buffer (size 64, batch 8) with weights exp(score/α).

— [PCBAgent §4, §6.1](https://www.cse.cuhk.edu.hk/~byu/papers/C247-ASPDAC2025-PCBAgent.pdf)

**Placement order.** Chips first. Then components attached to chip pads, taken clockwise from the pad linked to the highest-weight component. Component weight is a linear combination of size, net count and pad round/level. Second- and third-degree connections follow. — [PCBAgent §4.3](https://www.cse.cuhk.edu.hk/~byu/papers/C247-ASPDAC2025-PCBAgent.pdf)

**LLM agent.** Four components: statement obtainment, semantic understanding, tool invocation and command generation. It uses in-context demonstrations focused on defect descriptions. Its tools find components that deviate from constraints; the RL score and replay weights are then adjusted, and only those components are re-placed. **The LLM model, prompts and tool list are not specified.** — [PCBAgent §5](https://www.cse.cuhk.edu.hk/~byu/papers/C247-ASPDAC2025-PCBAgent.pdf)

**Later independent comparisons.** ModuPlace found PCBAgent had the most vias (94.4 average) despite low HPWL. OmniLayout measured its FreeRouting routability at RR 0.42. — [ModuPlace Tab. 2](https://yhhan.com/PDFs/ModuPlace_paper.pdf); [OmniLayout Tab. 2](https://arxiv.org/pdf/2607.03261)

#### 2.4 RAC — Relational Agent Contract (arXiv 2610.20935, 14 Oct 2026; Univ. of Washington) — NEW
**Contract.**
- The agent observes exact authoritative state, including coordinates.
- It may **act only through relations over named objects**: proximity, alignment, symmetry, edge association, keepouts, matched routing, layer preference, via limits.
- **No action accepts a coordinate or a metric distance.** Magnitudes are small ordered classes (tight / close / loose), whose metric values are fixed on the solver side.
- The complete relation set is submitted as **one bundle** that the backend realizes jointly.
- An independent DRC plus relation-specific geometric oracles verify the result.
- When realization is infeasible, feedback names the failure type, the conflicting constraints, the violation magnitudes and the **admissible relaxations**.

— [RAC §4–5](https://arxiv.org/pdf/2610.20935)

**Example actions.** `board_edge(J1, left)`, `place_relative(C1, U1.R1, near, tight)`, `route_matched([N2, N3], 5%)`. — [RAC App. A.2](https://arxiv.org/pdf/2610.20935)

**Results.** 98 PCB tasks (42 routing, 31 placement, 17 combined, 8 repair), 6 seeds, at most 5 model calls, 9 models (including Claude-Opus-4.8 and -5, GPT-5.6, Gemini-3.8-Flash). Mean clean-pass rate by interface:

| Interface | Clean-pass |
|---|---|
| Direct coordinates | 23.2% |
| **Coordinates plus Python sandbox** | **21.0%** |
| PCBWorld-style candidate selection | 37.4% |
| Sequential single relations | 62.4% |
| Requirements-only delegation | 74.0% |
| **RAC** | **90.9%** (77.6–95.9% across models) |

RAC also used 22.9–48.5% fewer tokens than candidate selection and was faster for 7 of 9 models. — [RAC Tab. 1, Tab. 5](https://arxiv.org/pdf/2610.20935)

**Robustness.** The same committed relations were re-solved after a 20% board shrink, a 20% expansion and a 25% footprint shrink. **89.5%** passed (411/459), against 65.6% for the best coordinate-reuse control (frozen, affine, or a fresh solve without relations). Board shrink was hardest: 77.1% vs 47.7%. — [RAC App. A.1](https://arxiv.org/pdf/2610.20935)

**Caveats.** The tasks appear small and synthetic; examples contain roughly 5–10 parts. The backend placer and router were not identified in what I read.

#### 2.5 Cypress (ISPD 2025; Zhang, Agnesina, Shbat, Leader, Z. Zhang, Ren; Cornell/NVIDIA) — VERIFIED (slides + abstract + repo)
**Problem scope.** Surface-mount, non-critical components on a rectilinear board, top and bottom, with sides **pre-assigned in the input**. Constraints are spacing, non-overlap, and fixed critical or mechanical parts. — [ISPD slides](https://ispd.cc/ispd2026/slides/2025/protected/3_1_slides.pdf)

**Cost terms.**
- An orientation-aware LogSumExp wirelength.
- A **two-sided electrostatic density** map.
- **Differentiable net crossing.** Each net is decomposed into source→sink pin pairs. For two pairs on the same layer, compute the Bézier intersection parameters t and u (an intersection exists iff both lie in [0, 1]). Pass each through a bell function and multiply, then sum over all same-layer pairs.
- **Orientation** in {N, E, S, W} is relaxed with **Gumbel-Softmax**. Positions and orientations are optimized bi-level, with different schedules and one fixed while the other updates.
- The ablation shows that adding net crossing alone worsens wirelength, while also enabling orientation improves the overall layout.

— [ISPD slides 8–10, 18](https://ispd.cc/ispd2026/slides/2025/protected/3_1_slides.pdf)

**Tuning and evaluation.**
- Multi-objective BO (MOTPE) runs in parallel across GPUs, using **Freerouting-measured routability and track length** as objectives.
- The released configuration space includes the GP learning rate, bin count (256–1024), optimizer (Adam or Nesterov), wirelength model (WA or LSE), density_weight (1e-6–1), γ, initial location, RISA weights, stop_overflow, macro halo and target density.
- The evaluator is Freerouting v1.9.0 with 2 copper layers. Routability is defined as the percentage of routed pin pairs.

— [ISPD slides 11, 14](https://ispd.cc/ispd2026/slides/2025/protected/3_1_slides.pdf); [pcb-configspace.json](https://github.com/NVlabs/Cypress/blob/main/test/tune/pcb-configspace.json)

**Results.**
- Routability up to 1.2× SA-PCB, 5.9× NS-Place and 1.6× NS-Place+ (NS-Place with a Tetris+Abacus legalizer).
- Up to 492.3× faster than SA-PCB and 329.7× faster than Quilter.
- Small benchmarks finish in 200–1765 s on 4 V100s.
- 1–19.7× shorter routed track on fully routed designs.

— [ISPD slides 16–17](https://ispd.cc/ispd2026/slides/2025/protected/3_1_slides.pdf); [SIGDA TOC abstract](https://www.sigda.org/publications/ispd-25-toc/)

**Independent result.** In OmniLayout, Cypress scored RR 0.33 and overlap 0.24. — [OmniLayout Tab. 2](https://arxiv.org/pdf/2607.03261)

#### 2.6 VeoPlace (NeurIPS 2026) — VERIFIED + NEW details
**Loop.** Each iteration runs 8 unguided placer rollouts, one VLM query that returns 8 suggestion sets, and 8 guided rollouts. A budget of 2,000 rollouts therefore means 125 VLM calls.
- For DREAMPlace, suggestions become a quadratic anchor term λ_A·Σ‖x_i − x̂_i‖² on bottom-left corners. **λ_A = 0.01 is best; 0.1–1.0 over-constrains.**
- For ChiPFormer, out-of-region logits are set to −∞. The fallback to unconstrained sampling triggers for about 20% of suggestions.
- At most 256 macros are guided, largest and most connected first.

— [VeoPlace §4, §5.3](https://arxiv.org/pdf/2603.28733)

**Prompt.** It contains:
- objective text;
- a 512×512 (or 84×84) grid with a bottom-left origin;
- a macro table (name, colour group by connectivity, W×H);
- rules: non-overlapping regions, regions large enough;
- prior episodes as **red-outlined labelled canvas images plus macro coordinates plus metrics**.

The required output has three sections:
- **HISTORY SUMMARY**: archetypes by colour group, largest-macro analysis, spatial patterns, standard-cell distribution, and at least 3 key principles, each marked "hypothesis" if the evidence is weak.
- **STRATEGY**: exactly one concrete change to the best archetype, labelled "exploratory" if the evidence is weak.
- **REGIONS**: listed in decreasing size order.

— [VeoPlace App. E.1](https://arxiv.org/pdf/2603.28733)

**Context selection.** The "Top Stratified" default runs K-means on placement coordinate vectors, picks one cluster by rank-softmax (τ = 0.43) over each cluster's best gHPWL, and takes the top C from that cluster. — [VeoPlace App. D.6](https://arxiv.org/pdf/2603.28733)

**Ablations.**
- Removing the image or the text, or shuffling images, changes results by **under 0.8%**.
- A random-regions control "sharply degrades" quality.
- Anchoring to the best-so-far placement ≈ DREAMPlace alone.
- Overhead is 2–7% of wall clock, about 62 s per Gemini 3.6 Flash call (about 2.1 h per run), and about $7 of API cost per run.

— [VeoPlace §5.3–5.5, Tab. 16](https://arxiv.org/pdf/2603.28733)

#### 2.7 EvoPlace, OrderPlace, CoEvoP&R (LLM evolution in IC placement) — VERIFIED + NEW details
**EvoPlace.** Candidates are generated in four steps: (1) LLM analysis of the current code (CoT), (2) a high-level idea, (3) reference code, (4) placer-format code. Selection is diversity-aware (normalized HPWL plus a cosine-distance term over code embeddings), followed by UCB-driven evolution with self-reflection. The LLM can use extra placement inputs (node sizes, pin offsets, net weights, areas). **Compute:** at least 1,000 feasible candidates per component and 1,000 evolution trials per case, on 60×2080Ti plus 150×3090 GPUs. Initialization has the highest generation success rate. — [arXiv 2504.17801 §III–IV](https://arxiv.org/pdf/2504.17801)

**OrderPlace.** The LLM writes ordering policies over exposed features (macro size, area of macros sharing nets, topology). The **three-stage proxy filter** is syntax validation → functional test on a macro subset → parallel Monte Carlo greedy probes (50 samples, 1,800 s limit). The top-4 elite strategies go into each prompt, and the final top-4 are run with a wire-mask greedy placer plus EA. Temperature 0.7; Claude Sonnet 4.5. — [arXiv 2606.08904 §5, App.](https://arxiv.org/pdf/2606.08904)

**CoEvoP&R.**
- The LLM writes objectives through a **restricted interface** over differentiable observables: scalars (smooth WL, density) and maps (density, **RUDY routing demand, pin density, long-net pressure**).
- Candidates pass an AST grammar check and a **finite-value plus autograd gate**.
- Evaluation is tiered by cost: Tier A, placement on every candidate; Tier B, timing proxy on selected ones; Tier C, real OpenROAD routing (3 candidates every 20 generations).
- A MAP-Elites archive with islands and **negative memory of failure reasons** feeds the next prompt.
- A **prompt-only free-form interface underperforms** the restricted interface.
- The method is robust across gpt-5.4, gpt-4.1-mini, claude-opus-4-8 and qwen3.7-max.
- Each run logs configuration, objective program, prompt and response records, metrics and traces, "sufficient to reconstruct candidate lineage".

— [arXiv 2607.17398 §3–5, Tab. ablation](https://arxiv.org/pdf/2607.17398); [CoEvoP-R README](https://github.com/FCHXWH823/CoEvoP-R)

#### 2.8 MAGE (arXiv 2607.18536; Kahng, Kundu, Pramanik; UCSD) — VERIFIED + NEW details
**Six phases and eight sub-agents.**
1. Parse and retrieve from the knowledge corpus.
2. Hierarchy-aware grouping into **families of structurally similar groups**.
3. Group bounding boxes, with a **mandatory flyline-render visual gate**. Stop when flyline length improves by less than 2% or after 5 iterations.
4. Feasibility check: area, packing pattern, routing-channel spacing; recursive split above τ_max.
5. A reference placement for one group per family, then **transform-and-merge** (translate, reflect or rotate) to the other groups.
6. Chip-level checks, then a **stateless independent auditor** with no access to prior reasoning.

An optional tournament adds analysis and reflection agents (Go-With-The-Winners, 6 variants × 6 rounds). — [MAGE §IV, Alg. 1](https://arxiv.org/pdf/2607.18536)

**Cost.** 78–189M input tokens and 1.8–4.3M output tokens per variant, $6–14 per variant, and **$220–509 per tournament** (average $310 per design). Average runtime is 10 h, dominated by P&R evaluation. — [MAGE §VI](https://arxiv.org/pdf/2607.18536)

#### 2.9 OmniLayout and OmniRouting (Penn State–led; 1,681 Eagle-derived designs) — VERIFIED + NEW details
**Data.** Specctra DSN files exported from industrial EDA (EAGLE 9.6.2 XML). There are 77.24K component placements, 168.82K pads and 55.83K netlist graphs. The 139.4K nets each carry *layout* and *schematic* spatial weights, used to score relationship preservation. — [OmniLayout §3, App. A](https://arxiv.org/pdf/2607.03261)

**Placement task input.** Schematic image; board outline as DXF details (JSON); a "netlist with spatial weight"; IC dimensions.
- Output: x, y, side (front or back) and orientation, including back-side mirrored options MR0–MR270.
- Metrics: OO (overlap), OoB (out of bounds), HPWL, net crossings, net separation, FreeRouting-based PRWL / RR / vias, schematic relational distance, reference similarity S_ref = 1/(1 + D_ref), and P-, R- and E2E-pass.

— [OmniLayout App. B, prompts](https://arxiv.org/pdf/2607.03261)

**Agentic tools.** Layout visualization, an overlap/geometry check, and a routability score. **Structured text naming conflicting components and locations (Geo. Check) gave the lowest overlap** for Claude Sonnet 4.6 and Ministral, better than inferring conflicts from images. Combining all tools was not uniformly best. Schematic context improved functional-grouping AUC in all 15 comparisons (+0.079 to +0.091). Few-shot examples barely helped (−0.006 mean AUC). — [OmniLayout §5.2–5.3](https://arxiv.org/pdf/2607.03261)

**OmniRouting.** "More steps do not guarantee improvement": GPT-5.5 went from 16.97 to 20.78 steps while NRR rose from 21.71% to 27.98%, but GPT-5-mini went from 18.38 to 23.65 steps while NRR fell from 9.86% to 6.82%. Pre-routing tools improve local legality and corridor choice more than global connectivity. The **GPCB learned router scores 0.69% NRR**, against PcbRouter's 56.20%. — [OmniRouting §Main Results, Tab. 1–2](https://arxiv.org/pdf/2608.04434)

#### 2.10 Scene-layout precedents (Holodeck, LayoutVLM, Brown PSDL) — VERIFIED + NEW details
**Holodeck.**
- Ten soft relation types in 5 groups: global (edge, middle); distance (near, far); position (in front of, side of, above, on top of); alignment (center aligned); rotation (face to).
- Collisions and boundaries are hard constraints.
- The LLM picks an anchor object, then a DFS solver places the rest. MILP is described as an alternative, linearized with binary auxiliaries for OR conditions.

— [Holodeck §3.4, supp.](https://arxiv.org/pdf/2312.09067)

**LayoutVLM.**
- The VLM outputs initial poses and differentiable relations from images marked with 2 m coordinate points and front-facing arrows.
- **Self-consistent decoding keeps only the relations already satisfied by the VLM's own initial poses**: 𝟙[L(p̂) ≤ ε]·L(p).
- Optimization is projected gradient descent with a DIoU collision loss.
- Average CF / IB / PSA: LayoutVLM 81.8 / 94.9 / 58.8; LayoutGPT 83.8 / 24.2 / 16.6; Holodeck 77.8 / 8.1 / 5.6.
- Ablations, as PSA: without numerical initialization 41.0; without spatial constraints 6.7 (IB falls to 14.1); without self-consistency 46.4; without the image 48.2.

— [LayoutVLM §4, Tab. 2, Tab. 5](https://arxiv.org/pdf/2412.02193)

**Brown PSDL.**
- Positions are expressions relative to placed objects; for example `chair.max.x = table.min.x - 0.1` and `chair.facing = table`. Variables and loops share parameters across objects.
- Repair minimizes loss(L) + d_edit(P, P₀) + d_OT(L, L₀). d_OT is a volume-weighted optimal-transport distance, so large objects move less.
- Elementary edits are constant rewrites (×(±4Y), Y ~ U[−1, 1], 10 samples per constant) and direction rewrites (4 cardinal directions). Greedy local search stops when no edit improves the objective by more than a small threshold.
- About **7.13 adjustments per scene**.
- It corrects 91% of errors, against 96% for gradient descent and 93.5% for flat-program local search, yet wins on human preference because relations survive.
- Model: claude-3-5-sonnet-20241022.

— [arXiv 2510.16147 §4–6, Tab. 2, Tab. 6](https://arxiv.org/pdf/2510.16147)

#### 2.11 Other verified items with implementation relevance
- **LayoutCopilot command set** (11 commands): deviceMove, deviceSwap, arrayAdd, arraySpace, symAdd, netRemove, netReroute, wireWidth, wireSpacing, netPriority, netTopology (a rough guide given as points). Abstract suggestions go to the designer for approval; concrete requests are compiled to these commands. — [LayoutCopilot Tab. I, §III](https://arxiv.org/pdf/2406.18873)
- **NS-Place** pipeline: Laplacian-eigenvector initialization → gradient descent on a net-separation (max-margin) objective (α = 1e-3, λ_NS = λ_D = 1) → MILP legalization **with relative-position constraints that preserve the global structure**. It fails on very high utilization boards (PCB2, about 20% whitespace). — [NS-Place §IV–V](https://arxiv.org/pdf/2210.14259)
- **Chip diffusion (Lee et al.)**: guidance uses legality (overlap) and HPWL potentials through backward universal guidance, with interleaved Lagrange-multiplier updates. Models have 233k, 1.23M and 6.29M parameters. Training is on synthetic v1/v2 datasets, followed by zero-shot use on IBM/ISPD. — [arXiv 2407.12282 §3–5](https://arxiv.org/pdf/2407.12282)
- **TILOS v3**: the SA baseline runs 320 parallel go-with-the-winners workers for 12.5 h. "As baselines should use best available prior algorithms, using weak or outdated baselines may lead to misleading conclusions." — [arXiv 2302.11014 v3 §VIII](https://arxiv.org/pdf/2302.11014)

#### 2.12 Related PCB work the notes missed (found by following references and citations)
- **Li, Peng, Huang, Wu, Zhu — LLM-guided coarse-to-fine PCB placement (DAC 2026).** Multimodal serialization, topology-enriched retrieval, two grouping agents, group-aware global placement, then constraint-graph/MILP legalization. Reported results are in row 44. It may be the strongest reported LLM-in-the-loop PCB placement result; only the survey description was retrieved. — [arXiv 2606.19795](https://arxiv.org/pdf/2606.19795)
- **Chen, Huang, Tsai, Ou, Y.-W. Chang — Clearance-Constrained PCB Global Placement with Heterogeneous Components (DAC 2025).** A wire-area model that gives power and signal nets different routing needs, a pad-to-pad clearance model, a two-sided pad-type-aware density, and a QP legalizer. It was the best academic placer in OmniLayout (RR 0.62, reference similarity 0.86). — [DOI 10.1109/DAC63849.2025.11133056](https://doi.org/10.1109/DAC63849.2025.11133056); [OmniLayout Tab. 2](https://arxiv.org/pdf/2607.03261)
- **Tsou, Lin, Hung, Y.-W. Chang — Modern Automatic PCB Placement with Complex Constraints (DAC 2024 LBR).** Force-directed global placement with **power-circuit anchor points**, SA-based pad alignment for spacing rules, then window-based legalization. — [DOI 10.1145/3649329.3663495](https://doi.org/10.1145/3649329.3663495)
- **PCB-Migrator (Han et al., DATE 2026).** An **offset constraint graph** carries a reference layout's relative positions to a resized or obstructed new board. Routing-path graphs plus graph matching guide re-routing. It is closely related to RAC's relation re-solve. — [S2 citation list of PCBAgent](https://api.semanticscholar.org/graph/v1/paper/DOI:10.1145/3658617.3697736?fields=citations.title); [DATE'26 DOI 10.23919/DATE69613.2026.11539307](https://doi.org/10.23919/DATE69613.2026.11539307)
- **GPCB Routing (Chen, Tu, Wang, … Qian; IEEE TCAD 44(4):1420–1433, 2025).** A GPT-style router over network-flow routing-pattern tokens, with a 2-D sliding window and local memory. It routes in parallel and learns from human routing. It scored 0.69% NRR on OmniRouting. — [DOI 10.1109/TCAD.2024.3486241](https://doi.org/10.1109/TCAD.2024.3486241); [OmniRouting Tab. 1](https://arxiv.org/pdf/2608.04434)
- **DRLPlace (Cai, Cheng; ASP-DAC 2026).** RL for irregular, high-density PCB placement; closed access, details not retrieved. — [DOI 10.1109/ASP-DAC66049.2026.11420655](https://doi.org/10.1109/ASP-DAC66049.2026.11420655)
- **MARS-Place (Wei, Hu, Chai, Zhao, Liu; Integration, May 2026).** Multi-stage, alignment-refined PCB placement and routing; abstract not available. — [DOI 10.1016/j.vlsi.2026.102671](https://doi.org/10.1016/j.vlsi.2026.102671)

### Inferences
- PCBWorld's LLM agent was handicapped in specific, fixable ways: DRC-blind prompts, no zones, a 2-turn history, 256-token replies, no rework actions, and a 200-step cap. A KiCad router agent built for production should fix all of these before concluding that "LLMs can't route". The case study suggests the bigger lever is still net ordering plus a rework action, both decided at a coarse level.
- Three independent lines converge on one design point: RAC (relations, jointly realized), ModuPlace (CCG offsets consumed as soft penalties), and the Brown PSDL work (relative expressions repaired numerically). **The LLM's output should be a relation set, never coordinates.** A Python sandbox does not rescue coordinate emission (RAC 21.0% vs 23.2%), which replicates FloorplanQA's tool-use finding cited in the notes.
- Freerouting is the de facto routability oracle across PCB placement papers: NS-Place, Cypress (v1.9.0), ModuPlace (with PcbRouter) and OmniLayout. Freerouting version and pass limits differ between papers, though (Cypress v1.9.0 defaults; PCBWorld 2.1.0 with `-mp 10`), so cross-paper numbers are not comparable.

### Gaps
- Neither ModuPlace nor PCBAgent releases code, prompts or hyperparameters. The CCG text schema the LLM actually emits is not shown.
- For RAC, the backend placer/router identity and the provenance of the PCB tasks (synthetic vs real) were not found in the sections read.
- The Li et al. DAC'26, Chen et al. DAC'25, DRLPlace and MARS-Place full texts were not retrieved; only abstracts or survey descriptions were available.

---

## 3. Implications for an LLM-driven KiCad placer/router (new points only)

### Takeaway
The verified details sharpen the existing recommendations in six ways:
1. Use **relation bundles with ordinal magnitudes** as the LLM's only write interface.
2. Persist those relations as the re-solvable intent artifact.
3. Feed **structured DRC/conflict evidence with admissible relaxations** back as text.
4. Treat images as optional, not essential.
5. Budget against measured token costs.
6. Benchmark with matched seeds and rollout counts, and with honest router configurations.

### Cited Findings
- **Ordinal magnitude classes beat metric distances in the action schema.** RAC forbids coordinates and metric distances in actions (e.g. `near, tight|close|loose`) and fixes the mm values on the solver side. It reaches 90.9% clean-pass on PCB tasks, against 23.2% for coordinates. — [RAC §5](https://arxiv.org/pdf/2610.20935)
- **Submit relations as one bundle, not one at a time.** Joint realization reached 90.9%, against 62.4% for sequential single relations. — [RAC Tab. 1](https://arxiv.org/pdf/2610.20935)
- **The relation set survives geometry changes (an ECO/resize advantage).** Re-solving the same relations after board or footprint changes passed 89.5%, against 65.6% for coordinate-based reuse. PCB-Migrator's offset constraint graph targets the same use case. — [RAC App. A.1](https://arxiv.org/pdf/2610.20935); [PCB-Migrator DOI](https://doi.org/10.23919/DATE69613.2026.11539307)
- **Infeasibility feedback should list conflicting constraints and admissible relaxations**, so the agent revises commitments instead of geometry. — [RAC §5.1](https://arxiv.org/pdf/2610.20935)
- **Keep LLM anchors weak.** VeoPlace's best anchor weight was λ_A = 0.01; 0.1–1.0 over-constrained the placer. Random regions hurt badly, so the VLM's semantic content is what helps. — [VeoPlace §5.3, Tab. 16](https://arxiv.org/pdf/2603.28733)
- **Images are optional for the proposal step.** VeoPlace with text only and image only differ by under 0.8%. MAGE's vision gate mattered mainly for timing structure (WNS −40.5% without it), not wirelength. OmniLayout found structured text conflict lists beat image-based overlap inference. — [VeoPlace §5.3](https://arxiv.org/pdf/2603.28733); [MAGE Tab. VI](https://arxiv.org/pdf/2607.18536); [OmniLayout §5.3](https://arxiv.org/pdf/2607.03261)
- **The proposal prompt template can be reused almost verbatim.** VeoPlace's output contract is HISTORY SUMMARY (archetypes, principles marked "hypothesis") → STRATEGY (exactly one concrete change to the best archetype, marked "exploratory") → REGIONS (largest first). This maps directly to KiCad rule-area/room proposals per functional block. — [VeoPlace App. E.1](https://arxiv.org/pdf/2603.28733)
- **Context selection for iterative proposals.** Cluster prior placements geometrically, sample one promising cluster by rank-softmax, and show its top-C members. This "Top Stratified" scheme beat FIFO, random, best-only and diverse selection. — [VeoPlace App. D.6](https://arxiv.org/pdf/2603.28733)
- **Exploit repeated channels.** MAGE places one reference group per family of structurally similar groups, then transforms and merges it to the rest. For KiCad this means: detect repeated subcircuits (multichannel/design blocks), place one, and replicate with translation, reflection or rotation before global legalization. — [MAGE §IV-A](https://arxiv.org/pdf/2607.18536)
- **Add Cypress's differentiable net-crossing term to the analytical placer loss.** Use Bézier intersection parameters through a bell function over same-layer pin pairs. Add a Gumbel-Softmax orientation relaxation with bi-level position/orientation updates. Handle two-sided density with sides fixed beforehand, which the LLM can decide as a relation (`side(part, bottom)`). — [ISPD slides 8–10](https://ispd.cc/ispd2026/slides/2025/protected/3_1_slides.pdf)
- **Model power and signal routing demand separately.** Chen et al. (DAC'25) use a wire-area model that distinguishes power from signal nets plus a pad-to-pad clearance model. It was the best academic placer on OmniLayout. — [DOI](https://doi.org/10.1109/DAC63849.2025.11133056); [OmniLayout Tab. 2](https://arxiv.org/pdf/2607.03261)
- **Volume-weighted repair.** When numerically repairing an LLM-authored placement program, add an optimal-transport term weighted by footprint area so connectors and ICs move less than passives. Restrict edits to constants and orientations. Brown PSDL needed about 7 edits per scene and kept human preference. — [arXiv 2510.16147 §5](https://arxiv.org/pdf/2510.16147)
- **Self-consistency filter for LLM relations.** Keep a proposed relation only if the LLM's own coarse placement already satisfies it. Removing this filter cost LayoutVLM 12.4 PSA points. — [LayoutVLM Eq. 1, Tab. 5](https://arxiv.org/pdf/2412.02193)
- **Token cost model for step-wise LLM routing.** GPT-5.4 used about 425k tokens per small board (D3-A, at most 31 pads) and about 1.9M per medium board (D3-B, at most 100 pads), at 231–866 s per episode, and still scored 0 CP on D3-B. Per-segment LLM routing should be ruled out on cost alone. — [PCBWorld Tab. 26–27](https://arxiv.org/pdf/2607.05915)
- **If a step-wise router agent is built anyway, fix PCBWorld's known gaps.**
  - Echo DRC violations (with codes and positions) in the prompt.
  - Include copper zones.
  - Expose per-netclass rules.
  - Add rip-up/delete actions; they exist in PCBWorld's API but were withheld from agents.
  - Keep longer history.
  - Make the first `net_select` an explicit planning decision, since it often decides success.
  - Prefix-cache the static board block (system message).

  — [PCBWorld App. E Tab. 7, App. H.1, App. N](https://arxiv.org/pdf/2607.05915)
- **Benchmark hygiene when comparing against PCBWorld numbers.**
  - Report @5 and @1. GPT-5.4-mini falls from 0.58 to 0.20 CP on D2 under @1, and PPO-terminal from 0.92 to 0.61.
  - Report seed means for stochastic routers.
  - State router settings. Freerouting ran at `-mp 10`; OrthoRoute ran without board design rules.
  - State which potential function was used: the repository's default differs from the paper's.

  — [PCBWorld App. L](https://arxiv.org/pdf/2607.05915); [README](https://github.com/LGAI-Research/PCBWorld)
- **Offline objective evolution needs a restricted, gradient-checked interface.** CoEvoP&R's free-form prompt interface underperformed its restricted observable API. Its pipeline (AST grammar → finite/autograd gate → cost tiers → negative memory) is a ready template for evolving a KiCad placer loss over observables such as HPWL, net crossing, RUDY, decap distance and loop area. — [arXiv 2607.17398](https://arxiv.org/pdf/2607.17398)
- **Budget realistically for evolution.** EvoPlace's case-specific gains needed about 1,000 candidates per component and 1,000 trials per case on about 210 GPUs. Generalized evolved algorithms gained only 0.5–2.9%. Plan cross-board generalization tests from the start. — [arXiv 2504.17801 §IV, Tab. IV–V](https://arxiv.org/pdf/2504.17801)
- **Fine-tuning data for relation generation.** ModuPlace's 426 expert CCGs plus an expert-ranking GNN reward drove large gains over zero-shot GPT-4o and Claude-3.5. An open equivalent could mine relative-offset graphs from the 679 human-routed PCBWorld D3 boards. These boards are KiCad 9-native and each keeps its source license. — [ModuPlace §4](https://yhhan.com/PDFs/ModuPlace_paper.pdf); [PCBWorld App. O.7](https://arxiv.org/pdf/2607.05915)

### Inferences
- **Recommended LLM write API (synthesis).**
  - A typed relation bundle: `group`, `region(group, rule_area)`, `side(part, top|bottom)`, `near(part, part.pin, tight|close|loose)`, `align(parts, axis)`, `symmetric(a, b, axis)`, `board_edge(part, side)`, `orient_toward(part, part.pin)`, `keepout(region, layers)`, `route_matched(nets, tol_class)`, `layer_pref(net, layer)`, `via_limit(net, n)`, `net_order(rank)`.
  - It is realized jointly by the analytical placer plus legalizer and the router.
  - It is verified by independent KiCad DRC plus per-relation oracles.
  - It is returned with conflict sets and relaxation options.
  - It is persisted as the design-intent artifact, so board resizes and ECOs re-solve without new LLM calls (RAC/PCB-Migrator evidence).
- **Images should be a later add-on.** Build the text/relation channel first; add rendered views only for structure-level critiques (grouping, symmetry), where MAGE showed value.
- **Benchmark ladder.**
  - Placement: OmniLayout-style FreeRouting RR/PRWL plus pad-overlap and out-of-bounds metrics, with Chen et al. DAC'25 and Quilter as the reference points to beat. Academic placers are a low bar on that metric.
  - Routing: PCBWorld D3-A/B with matched @k and seed protocol.

### Gaps
- No public study yet combines a relation-only LLM interface with a real-board KiCad backend at PCBWorld D3 scale. RAC's tasks look small and synthetic, so the result needs replication on real boards.
- How ordinal magnitude classes should map to mm per component class (0402 decap vs connector) is unpublished. It must be calibrated, e.g. from distance statistics in human D3 boards.
