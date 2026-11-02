# PCB placement and routing benchmarks and datasets (corrected numbers)

Scope: public PCB placement/routing benchmarks and datasets with corrected numbers: contest status, PCBWorld-Bench and Freerouting suites (pointers), PCBench, Cypress, OmniLayout, others. Not here: our plan -> [benchmark-plan.md](benchmark-plan.md); metrics -> [quality-metrics.md](quality-metrics.md); PCBWorld details -> [../routing/pcbworld.md](../routing/pcbworld.md); routing/placement dataset surveys -> [../routing/benchmarks-and-datasets.md](../routing/benchmarks-and-datasets.md), [../placement/benchmarks-and-metrics.md](../placement/benchmarks-and-metrics.md), [../llm/pcb-llm-benchmarks.md](../llm/pcb-llm-benchmarks.md).
Keys: benchmarks, datasets, ISPD, ICCAD, PCBWorld-Bench, D3-A, D3-B, D3-C, CP@5, Freerouting 2.1.0, Freerouting 2.5.0, PCBench, PCBs_version_9, Cypress, NVlabs, OmniLayout, OmniRouting, PCB-Bench, EEBench, RL_PCB, tscircuit SRJ, DevFormer DPP, FloorSet, TraceMaker, fastroute, VK, VP
Tags: [P] primary; [S] snippet/secondary; [V] vendor; [I] inference. "VK" = verified/corrected by the KiCad-tools verification note; "VP" = papers verification note (verification_papers.md, row numbers given).

## Benchmark conclusions
1. No ISPD or ICCAD contest problem exists for PCB or package placement or routing. Closest standards: **PCBWorld-Bench** (routing; KiCad-native, 679 real D3 boards + synthetic D1/D2, human reference copper; use the @5 CP protocol) and **Cypress** (placement; NVlabs, Apache-2.0; Freerouting v1.9.0 routability on two free layers, VP #37) [I].
2. LLM agents must act **through** the engine (numbers → [PCBWorld LLM agents](../routing/pcbworld.md#llm-agents)): the LLM uses KiCad's router as a tool, never emits raw geometry ([../workflow/llm-field-reports.md](../workflow/llm-field-reports.md)) [I]. Those agents saw no DRC list and no reward in the prompt (VP #1), so the result does not test DRC feedback.
3. Freerouting's published baseline (2.1.0) is outdated ([self-reported gains](../routing/freerouting.md#release-note-benchmark-v250)). Re-run 2.5.0 locally on D3-A/B before claiming gains [I].
4. OmniLayout/OmniRouting have the strongest metric protocol, but the data licence is disputed (VP #28). Verify licences per board before redistributing derived artifacts (PCBWorld D3, PCBench, Cypress) [I].
5. Corpus: reuse PCBWorld's recipe -> [benchmark-plan.md](benchmark-plan.md#construction-recipe-for-our-own-corpus).

## Contest status

- **ICCAD** contest history has no PCB or package problems. Its routing problems are IC-level: obstacle-aware on-track bus routing (2018), routing with cell movement (2020/2021), FPGA TDM routing and LEF/DEF global routing. ICCAD 2026's problems are (A) LLM-Assisted Netlist Exploration, (B) Regression Failure Bucketing and (C) the FloorSet Challenge ([ICCAD 2026](https://www.iccad-contest.org/2026/Problems.html)) [P].
- **ISPD** contests from 2005 to 2027 are all IC or FPGA topics. ISPD 2027 is MCMM post-CTS buffering and sizing on ASAP7 [P].

## PCBWorld-Bench

LG AI Research; v1.1.0; BSD-3 with a GPLv3 engine; KiCad 9.0.8. Splits (D1–D3), how D3 was built (VP #7/#8), @5 Table 21 (= v2 Table 3, VK VERIFIED), @1, agent modes, OrthoRoute routability and DeepPCB's claim → [../routing/pcbworld.md](../routing/pcbworld.md#datasets) [P].

## Other benchmarks and datasets

| Dataset | Facts | Tag |
|---|---|---|
| Freerouting release-note suite (1,157 boards) and nightly (1,142 fixtures) | Self-reported clean rates, tiers, time budgets → [../routing/freerouting.md](../routing/freerouting.md#release-note-benchmark-v250) | [P, VK] |
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

## Open questions

- **PCBench size**: resolved (VP #7): README 164; D3 = 679 survivors of the 1,182-board `PCBs_version_9` pool; Freerouting's "PCBench table" 1,157 boards.
- **Cypress**: benchmark count is 10 (slides) vs 20 (repo). Award status is "Best Paper" (Cornell news) vs "Best Paper Nominee" (ISPD slides).
- **DeepPCB**: whether PCBWorld's authors evaluated it is unknown; its leaderboard claim is self-reported.
- **Taiwan MOE contest**: whether its domestic CAD contest ever ran a PCB problem is unknown.

## Sources

- [constraints_verification_benchmarks.md § Q4](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/constraints_verification_benchmarks.md)
- corrections: [verification_kicad_and_tools.md § 1 (#19, #20, #22, #26, #42, #46), § 4](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_kicad_and_tools.md)
- corrections (VP): [verification_papers.md § 1 (#1, #7, #8, #28, #37), § 2.1](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_papers.md)
- [practitioner_discussions.md § Q1e EEBench, Q2b devbisme](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/practitioner_discussions.md)
- See also [evaluation-stack.md](evaluation-stack.md).
