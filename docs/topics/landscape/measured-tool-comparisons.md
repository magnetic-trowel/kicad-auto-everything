# Measured comparisons of existing routers, agents and AI tools (and the datasets behind them)

**TL;DR**
- **PCBWorld-Bench** (LG AI Research, KDD 2026 workshop) is the only neutral multi-tool routing comparison:
  - Freerouting 2.1.0 has the best rule-based clean-pass: 0.80 (D3-A, 99 boards) and 0.78 (D3-B, 10 boards), @5.
  - GPT-5.4 driving KiCad's router interactively reaches 0.65, then **0.00 on D3-B**.
  - A small PPO policy scores 0.86 / 0.45 [P].
- **Engine engagement decides LLM success:** GPT-5.4 scores 0.65 interactive vs 0.19 plan-then-execute vs 0.02 engine-free [P].
- **Freerouting v2.5.0 self-reports 30.9% → 75.0% clean** on its 1,157-board suite. That makes PCBWorld's 2.1.0 baseline stale [P].
- **No placement benchmark exists, and there is no independent benchmark of Quilter, DeepPCB or Flux.** Vendor numbers are not comparable [P].
- **"0 DRC" is a weak metric.** A no-tools Claude Code board passed DRC while routing through the GND plane [P].

## Key facts

### PCBWorld / PCBWorld-Bench
- **Paper:** Song, Park, Choi, Bae, Jeong, Park, Lee, "PCBWorld: A Benchmark Environment for Engine-Grounded PCB Design Automation", arXiv:2607.05915, KDD 2026 Workshop on Evaluation and Trustworthiness of Agentic AI (non-archival) [P] ([arXiv](https://arxiv.org/abs/2607.05915)).
- **Environment:** BSD-3 Gymnasium, v1.1.0, 31★, with a GPLv3 engine behind a socket.
  - Actions: `ACT_NET_SELECT`, `ACT_START_ROUTE`, `ACT_MAKE_LINE`, `ACT_NET_END`. The agent picks from a **masked candidate point set**.
  - State is exact mm geometry, with an S-expression text wrapper for LLMs.
  - Reward is potential-based with a log-shaped DRC penalty [P].
- **Datasets:**
  - D1: synthetic grid (Jumanji Connector-style, sizes 10–500).
  - D2: synthetic gridless 2-layer multi-pin.
  - D3: 679 boards from PCBench, normalized to KiCad 9, fully connected and DRV-free, split by pad count into D3-A/B/C. Zero-shot uses 99 D3-A and 10 D3-B boards; D3-C ("hundreds of nets") is a challenge split.
  - D3 is rebuilt at run time with `prepare_pcbench.sh` [P].
- **Metrics:** Clean Pass (all nets connected, zero DRC), Potential Gain, Routability, Time, DRV, wirelength, vias; best of 5 ("@5").

**@5 results (arXiv v2 Table 3, confirmed by VK)**

| Method | D2 CP | D3-A CP / Rout. | D3-B CP / Rout. |
|---|---|---|---|
| Freerouting 2.1.0 | 1.00 | 0.80 / 0.91 | 0.78 / 1.00 |
| KiCadRoutingTools | 1.00 | 0.74 / 0.94 | 0.20 / 0.86 |
| OrthoRoute | 0.01 (rout. 0.34) | 0.02 / 0.53 | 0.00 / 0.44 |
| GPT-5.4 via PCBWorld tools | 0.96 | 0.65 / 0.91 | 0.00 / 0.62 |
| GPT-5.4-mini / -nano / Qwen3.5-397B | 0.58 / 0.55 / 0.33 | 0.28 / 0.30 / 0.34 | 0.00 |
| PPO transformer (trained on synthetic D2 only) | 1.00 | 0.86 | 0.45 |

- **Mean time on D3-A:** Freerouting 7.09 s, KRT 0.65 s, GPT-5.4 231 s (231–866 s per board per VK), PPO 1.83 s. "All LLM agents nonetheless obtain 0.00 CP on D3-B" [P].
- **Engine engagement (Table 4, GPT-5.4, D3-A):** interactive CP 0.65 (DRV 1.31); plan-and-execute 0.19 (DRV 16.28); engine-free 0.02. "Generating raw wire segments while keeping every track within the design rules is beyond current models". GPT-5.4-nano engine-free produced no loadable file in any of 5 rollouts on 10% of boards [P].
- **One-attempt results (v4 Tables 21–22, as reproduced by DeepPCB):** GPT-5.4 0.42 / 0.00; Freerouting 0.75 / 0.64; PPO (without finish) 0.81 / 0.22; KRT 0.74 / 0.20; Qwen3.5-397B 0.19 / 0.00; OrthoRoute 0.02 / 0.00. DeepPCB claims 0.929 / 0.800 [V] ([DeepPCB post](https://deeppcb.ai/benchmark/pcbworld-bench-deeppcb-results/)). **Do not mix @5 and one-attempt numbers.**
- **OrthoRoute's README** quotes 30% and 51% routability, probably @1 or an older version, versus the paper's 0.34 / 0.53 [P].

### Other measurements
| Item | Numbers | Tag |
|---|---|---|
| Freerouting v2.5.0 on its PCBench suite (1,157 boards) | Clean 358 (30.9%) → 868 (75.0%); fully routed 600 → 872 (75.4%); timeouts 78 → 78; total time 3,251 s → 2,997 s; Tier C (6+ layers) 49.2% clean, Tier D 50% | [P] self-reported ([release](https://github.com/freerouting/freerouting/releases/tag/v2.5.0)) |
| fastroute vs Freerouting (20 boards) | 510 s (420 s with PGO) vs 2,102 s; 20–300 MB vs 1–2 GB | [P] self-reported |
| kicad-tools TraceMaker | ≈0.99 / 1.00 / 0.90 vs Freerouting 2.2.4 ≈0.7 / 0.7 / 0.2 (single 60 s runs) | [P] self-reported (corrected baseline, VK) |
| KRT | 47/47 FTDI nets in 8.6 s; 28/28 LVDS pairs in 29.7 s; ongoing A/B on open-source boards | [P] self-reported |
| devbisme dual-ADC test | 8 AI tools plus a null baseline; all routed boards used Freerouting; null baseline $11.16 "DRC clean" with signals on the GND plane. Table in [kicad-ai-tools-and-mcp-servers.md](kicad-ai-tools-and-mcp-servers.md) | [P], unvalidated |
| POA A/B | Plain Claude Code 18/18 single edits vs 3/18 with an MCP-only plugin; 1.8× context. See [../kicad/mcp-server-lessons.md](../kicad/mcp-server-lessons.md) | [P], small |
| DeepPCB | 27,721 boards, 95.6% hit ≥95%; mean completion 96.1%; Quilter comparison. See [deeppcb.md](deeppcb.md) | [V] |
| Quilter Speedrun | 38.5 h vs 428 h quoted; SOM placement human. See [quilter.md](quilter.md) | [V] |
| Cadence and Zuken | ">10X"; 25 vs 70 min placement (EMA); 45 min → 30 s (Zuken) | [V] |
| EEVblog 2010 | Freerouting 11 vias vs 18 manual on one board | [S] |

### Agent-level and other benchmarks
- **EEBench** (atopile): agents submit atopile bundles. Deterministic build, SPICE at worst-case corners and BOM checks; score = 0.65 × technical + 0.35 × cost efficiency. "**Layout is deliberately out of scope** — sequenced, not forgotten"; V2 will add layout and fabrication. Tasks are private. Snapshot (Sept 2026): Claude Opus 5.5 75.0%, GPT-6 Astra 69.3% [P/S] ([methodology](https://eebench.org/methodology.html)).
- **EDA-bench:** 35 Harbor tasks; the agent must reconstruct a full KiCad project, checked on schematic, PCB, connectivity, physical realization, ERC/DRC and a functional contract. ICML 2026 paper "EDA Bench: Functional Failure Modes in PCB-Generating Agents" [S]. No model results in the README [P].
- **comma.ai PCBGolf:** score = PCBA bounding-box volume (mm³) + 50 × vias + 5,000 × copper layers; JLCPCB-manufacturable; $1,000 prize, deadline 2026-10-12 (past). **No licence file**, so fetch-only [P].
- **tscircuit:**
  - `autorouting-dataset-01` (200 problems);
  - `tscircuit/autorouting` (archived);
  - `dataset-zero-obstacle-high-density-z01`;
  - **Z01**: 1M 2-layer input/output images for vision models, made with `@tscircuit/high-density-a01` on random 10×10 mm problems (Hugging Face, 2026-02-26);
  - SRJ33 (37 DRC-failure inputs) and an Autorouter Benchmark Dashboard;
  - `dsn-converter` [P].
- **PCBench:** the repo is MIT, 21★. The README says "164 printed circuit boards", but `master_metadata.json` lists **1,194 designs from 846 repos** (2023-08). It ships `raw.kicad_pcb`, `processed.kicad_pcb`, a PCB-RDL `final.json`, augmentation and an RL environment. PCBWorld derives 679; Freerouting cites 1,157. Per-board licences are mixed (54% none); see [../licensing/data-rulepacks-weights.md](../licensing/data-rulepacks-weights.md) [P].

## Recommendations for our system
- **Primary routing benchmark:** PCBWorld-Bench, fetched at run time. Secondary: Freerouting's PCBench suite and scores, and tscircuit sets [I].
- **Re-run current baselines:** Freerouting 2.5.0, fastroute, kicad-tools and the tscircuit router on D3-A/B. Comparing with the paper's 2.1.0 numbers would overstate gains [I].
- **Report:** clean pass, routability, DRV, vias, length versus lower bounds (`V2_LOWER_BOUND`), wall time, plus layout-quality checks DRC misses [I].
- **Publish a placement benchmark:** strip placement from D3 boards and score downstream clean pass, wirelength, vias and rule proxies (decap distance). Add multilayer boards. Publish failures, with PRO-style attempt accounting ([../kicad/mcp-server-testing-practices.md](../kicad/mcp-server-testing-practices.md)) [I].
- **Showcases (fetch-only):** PCBGolf and the devbisme dual-ADC test.
- **Optional external baselines:** DeepPCB (API), Quilter (manual upload), Electra (licence). Never dependencies [I].
- The evaluation stack design itself belongs to the `verification/` area.

## Conflicts and open questions
- PCBench counts (164 / 679 / 1,157 / 1,194) are only partly reconciled. The 1,194 vs 1,157 gap is perhaps loadable or convertible boards [I].
- PCBWorld did not evaluate Freerouting 2.5, fastroute, kicad-tools, tscircuit, Quilter or Flux. DeepPCB's leaderboard claim is self-reported.
- No independent SI measurement of AI-routed boards exists.

## Sources
- research notes:
  - [existing_tools_and_apis.md § 5](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/existing_tools_and_apis.md)
  - [verification_kicad_and_tools.md § 1 (#19–20, #26, #46), § 5 (9–10)](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_kicad_and_tools.md)
  - [patents_and_industry.md § 2, § 4, § 6](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/patents_and_industry.md)
  - [licensing.md § 1G](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/licensing.md)
- primary: [PCBWorld paper v2](https://arxiv.org/html/2607.05915v2), [PCBWorld repo](https://github.com/LGAI-Research/PCBWorld), [PCBench](https://github.com/PCBench/PCBench), [Freerouting scoring.md](https://github.com/freerouting/freerouting/blob/master/docs/scoring.md)

See also: [open-source-routers.md](open-source-routers.md), [kicad-ai-tools-and-mcp-servers.md](kicad-ai-tools-and-mcp-servers.md), [deeppcb.md](deeppcb.md)
