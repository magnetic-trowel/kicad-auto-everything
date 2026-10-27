# PCB placement and routing benchmarks and datasets (corrected numbers)

**TL;DR**
- There are **no ISPD or ICCAD contest problems for PCB or package placement or routing**.
- The closest things to standards:
  - **PCBWorld-Bench** for routing: KiCad-native, 679 real boards in D3 plus synthetic D1/D2, with human reference copper.
  - **Cypress** for placement: NVlabs, Apache-2.0, scored by a Freerouting-routability protocol (Freerouting v1.9.0, VP #37).
- **LLM agents must act through the engine.** On PCBWorld D3-A, GPT-5.4 reaches CP 0.65 interactive vs 0.19 plan-and-execute vs 0.02 engine-free. All LLM agents score 0.00 on D3-B, where Freerouting 2.1.0 scores 0.78 (on the 10 evaluated D3-B boards).
- **Freerouting's published baseline is outdated.** It is version 2.1.0; v2.5.0 raised Freerouting's own clean rate from 30.9% (2.4.1) to 75.0% on its 1,157-board release-note suite, so re-run the baseline before claiming gains. "Clean" there is Freerouting's own check, not KiCad DRC.
- **OmniLayout/OmniRouting** have the strongest metric protocol, but the data licence is disputed (VP #28). **PCBench**'s size differs by source: 164 (README), a 1,182-board `PCBs_version_9` pool of which D3 keeps 679 (VP #7), and 1,157 in Freerouting's release-note table.

## Key facts

Tags: [P] primary; [S] snippet/secondary; [V] vendor; [I] inference. "VK" marks values verified or corrected by the KiCad-tools verification note; "VP" by the papers verification note (verification_papers.md, row numbers given).

### Contest status

- **ICCAD** contest history has no PCB or package problems. Its routing problems are IC-level: obstacle-aware on-track bus routing (2018), routing with cell movement (2020/2021), FPGA TDM routing and LEF/DEF global routing. ICCAD 2026's problems are (A) LLM-Assisted Netlist Exploration, (B) Regression Failure Bucketing and (C) the FloorSet Challenge ([ICCAD 2026](https://www.iccad-contest.org/2026/Problems.html)) [P].
- **ISPD** contests from 2005 to 2027 are all IC or FPGA topics. ISPD 2027 is MCMM post-CTS buffering and sizing on ASAP7 [P].

### PCBWorld-Bench (LG AI Research)

v1.1.0; BSD-3, with a GPLv3 engine; KiCad 9.0.8 ([paper v2](https://arxiv.org/html/2607.05915v2), [repo](https://github.com/LGAI-Research/PCBWorld)) [P].

| Split | Boards | Nets | Pads | Layers |
|---|---|---|---|---|
| D1 (grid) | 10,000 / 128 / 128 | 5 | — | 1 |
| D2 (gridless) | 10,000 / 128 / 128 | 4–6 | — | 2 |
| D3-A (small) | 100 | 2–13 | 6–31 | 2–4 |
| D3-B (medium) | 287 | 5–42 | 31–100 | 2–4 |
| D3-C (large) | 292 | 6–451 | 101–2,103 | 2–8 (VP) |

**How D3 was built.** D3 is "679 boards derived from PCBench's open-source PCB corpus": the survivors of PCBench's 1,182-board `PCBs_version_9` pool converted to KiCad 9 (VP #7). A compatibility pass edited only `.kicad_pro` severities and floors (some checks ignored, some floors zeroed; board files byte-identical), so the design rules were not simply kept. A board was kept only if still fully connected and DRV-free after that pass. Each keeps its original routing as the reference. Zero-shot evaluation uses 99 D3-A and **10** of D3-B's 287 boards (all two-layer, one per pad-count quantile; VP #8); D3-C is an unevaluated challenge split.

**Results, Table 3, @5** (VK VERIFIED). CP@5 is the clean status of the best-potential (Φ) rollout of 5. Freerouting and RL rows are 4-seed means; LLM rows are a single best-of-5 run (VP #8). Freerouting ran at `-mp 10`; its @1 is 0.75 (D3-A) and 0.64 (D3-B) ([pcbworld](../routing/pcbworld.md)):

| Method | D3-A CP | D3-B CP | Time D2 / D3-A / D3-B (s) |
|---|---|---|---|
| Freerouting 2.1.0 | 0.80 | 0.78 | 2.69 / 7.09 / 9.94 |
| KiCadRoutingTools (KRT) | 0.74 | 0.20 | 0.82 / 0.65 / 3.27 |
| OrthoRoute | 0.02 | 0.00 | — |
| PPO (synthetic-only training) | 0.86 | 0.45 | 0.43 / 1.83 / — |
| PPO (w/o finish) | 0.94 | 0.42 | — |
| GPT-5.4 interactive agent | 0.65 | 0.00 | — / 231 / 866 |

**Agent mode matters.**
- GPT-5.4 on D3-A, CP: interactive 0.65, plan-and-execute 0.19, engine-free 0.02. DRV: 1.31, 16.28 and 34.58 respectively.
- The paper's conclusions: "All LLM agents nonetheless obtain 0.00 CP on D3-B"; "Leveraging the native API is essential for design-rule-clean routing."

**Other claims.**
- OrthoRoute routability in paper v2 is 0.34 (D2) and 0.53 (D3-A) at @5. Its README says 30% and 51%, probably from an earlier version or @1 (VK).
- DeepPCB claims "the top one-attempt score on both test sets" (self-reported) [V].

### Other benchmarks and datasets

| Dataset | Facts | Tag |
|---|---|---|
| Freerouting v2.5.0 release-note suite ("PCBench table", 1,157 boards) | Clean 358 (30.9%, v2.4.1) → 868 (75.0%); fully routed 600 → 872; timeouts 78; total time 3,251 → 2,997 s; Tier C (6+ layers) 49.2% clean ([release](https://github.com/freerouting/freerouting/releases/tag/v2.5.0)). "Clean" is Freerouting's own check, not KiCad DRC. A second suite, the nightly benchmark (2026-10-20, 1,142 fixtures), gives 1.9.0 36.2%, 2.4.1 31.3%, 2.5.0 75.2%, 2.6.0-RC3 87.7%; RC4's 92.4% covers only tiers A+B (979 fixtures), so it is not comparable, and per-version time budgets differ up to ~100× ([freerouting](../routing/freerouting.md)) | [P, VK] |
| PCBench | README: "a dataset for PCB routing" with 164 PCBs (raw and processed `.kicad_pcb`, PCB-RDL `final.json`, metadata, PNG), net-subsampling augmentation, grid RL environment ([repo](https://github.com/PCBench/PCBench)) | [P] |
| Cypress (NVlabs; Apache-2.0; DREAMPlace-based) | DOI 10.1145/3698364.3705346, ISPD '25 pp. 31–41, closed-access (VK). Slides: 10 small benchmarks synthesized "based on functionality" (Ethernet controller, power controller, GPIO expander, CPLDs…) plus 5 commercial large ones; repo ships `small-1`…`small-20`. Formulation: SMD non-critical parts, two-sided rectilinear boards, pre-assigned sides, spacing/non-overlap/fixed parts, orientation-aware LogSumExp WL, two-sided electrostatic density, net-crossing model. `enable_rotation` defaults to 0; bottom parts use Bookshelf `FN`. Claims 1–5.9× routability, 1–19.7× shorter routed length, up to 492.3× speedup vs SA-PCB and NS-Place ([repo](https://github.com/NVlabs/Cypress), [slides](https://ispd.cc/ispd2026/slides/2025/protected/3_1_slides.pdf)) | [P] |
| OmniLayout / OmniRouting | 77.24K placement instances; routing on 2–8 layers with human references and four tasks, including tool-augmented agentic routing; from 1,681 Eagle designs (SparkFun, Arduino, Adafruit, GitHub). Promises open data, but a 2026-08-15 audit found Eagle-9.6.2-derived JSON, 5 public sample boards, no data licence and CC BY-NC-ND papers ([audit](https://github.com/rjwalters/kicad-tools/blob/main/docs/research/omnilayout-recon.md)). Conflict (VP #28): the ethics statement says code and dataset are CC-BY-4.0; only the arXiv paper is CC BY-NC-ND. Results: best zero-shot LMM NRR/PRR 12.60/15.41%; agentic refinement 27.98/30.34%; OpenROAD PcbRouter 56.20/71.37%; base outputs average 69.77–431.29 DRC violations; "Feedback quality matters more than iteration count" | [P]/[S] |
| PCB-Bench (ICLR 2026) | Knowledge benchmark: ~3,700 text QA/CQ, ~500 image-text items, 174 OSHWHub designs for screenshot-to-description. Not layout | [P] |
| EEBench | atopile-based; graded deterministically with SPICE corners and BOM cost; Claude Opus 5 61.6% on 13 tasks; "does not yet tell us whether a model can lay out, manufacture and bring up a complete product" ([blog](https://eebench.org/blog/can-ai-design-circuit-boards-yet/)) | [V] |
| RL_PCB | 6 training circuits | [P] |
| tscircuit `dataset-srj18` / SRJ33 | 16 boards from KiCad (5 Arduino + 11 Antmicro); SRJ33 DRC-failure dataset. The SRJ format drops net-class widths, clearances, zones and keepouts (lossy) | [P]/[S] |
| DevFormer DPP | Decap-placement sub-problem with simulator | [P] |
| FloorSet (Intel) | 2 × 1M synthetic floorplans (Prime rectilinear, Lite rectangular) with hard constraints; ICCAD 2026 Problem C | [P] |
| TraceMaker | ≈0.99/1.00/0.90 vs Freerouting **2.2.4** "about 0.7/0.7/0.2", single 60 s runs, third-party self-report (VK) | [S] |
| fastroute (GPL-3.0) | Rust port of Freerouting; `--parity` gives SES output byte-identical to Freerouting's deterministic mode on all 20 benchmark boards; fixes listed Freerouting bugs. A determinism reference (VK) | [P] |
| Practitioner suites | devbisme/ai-circuit-design-tests; KiCad Agentic MCP 18/18 golden tasks; kicad-happy test harness over 5,800+ repos and 3,498 PCB files (VK VERIFIED) | [P] |
| Older academic | Bus, escape and substrate routing mostly on proprietary instances, e.g. SAT-based BGA escape on a 28×28 BGA with ~380 signals (ICCAD 2016) | [S] |

## Recommendations for our system

- **Standards**: use PCBWorld D3 (routing, @5 CP protocol) and the Cypress protocol (placement, Freerouting v1.9.0 routability on two free layers) [I].
- **Re-baselines**: re-run Freerouting 2.5.0 locally on D3-A/B; the paper's 2.1.0 numbers overstate any gain [I].
- **Architecture**: the 0.65 vs 0.02 result means the LLM must act **through** KiCad's router as a tool, never emit raw geometry ([../workflow/llm-field-reports.md](../workflow/llm-field-reports.md)) [I]. Those agents saw no DRC list and no reward in the prompt (VP #1), so the result does not test DRC feedback.
- **Corpus**: build our own by reusing PCBWorld's recipe — convert to the current KiCad version, keep each board's own rules (PCBWorld itself edited `.kicad_pro` severities and floors), drop boards not fully connected and DRV-clean, keep human copper, split by pad count. See [benchmark-plan.md](benchmark-plan.md) [I].
- **Licences**: verify per board before redistributing derived artifacts (PCBWorld D3, PCBench, Cypress) [I].

## Conflicts and open questions

- **PCBench size**: resolved (VP #7). The README says 164; D3 is the 679 survivors of the 1,182-board `PCBs_version_9` pool; Freerouting's "PCBench table" has 1,157 boards.
- **Cypress**: benchmark count is 10 (slides) vs 20 (repo). Award status is "Best Paper" (Cornell news) vs "Best Paper Nominee" (ISPD slides).
- **DeepPCB**: whether PCBWorld's authors evaluated it is unknown; its leaderboard claim is self-reported.
- **Taiwan MOE contest**: whether its domestic CAD contest ever ran a PCB problem is unknown.

## Sources

- research notes: [constraints_verification_benchmarks.md § Q4](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/constraints_verification_benchmarks.md)
- corrections: [verification_kicad_and_tools.md § 1 (#19, #20, #22, #26, #42, #46), § 4](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_kicad_and_tools.md)
- corrections (VP): [verification_papers.md § 1 (#1, #7, #8, #28, #37), § 2.1](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_papers.md)
- research notes: [practitioner_discussions.md § Q1e EEBench, Q2b devbisme](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/practitioner_discussions.md)

See also: [benchmark-plan.md](benchmark-plan.md), [quality-metrics.md](quality-metrics.md), [evaluation-stack.md](evaluation-stack.md), [../routing/pcbworld.md](../routing/pcbworld.md), [../llm/pcb-llm-benchmarks.md](../llm/pcb-llm-benchmarks.md), [../routing/benchmarks-and-datasets.md](../routing/benchmarks-and-datasets.md), [../placement/benchmarks-and-metrics.md](../placement/benchmarks-and-metrics.md)
