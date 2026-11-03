# Measured comparisons of existing routers, agents and AI tools (and the datasets behind them)

Scope: published numbers comparing routers, LLM agents and AI layout tools; benchmark datasets. Not here: PCBWorld stack, reward and per-metric tables -> [../routing/pcbworld.md](../routing/pcbworld.md); Freerouting internals and nightly tiers -> [../routing/freerouting.md](../routing/freerouting.md); our evaluation stack -> `verification/`.
Keys: PCBWorld-Bench, D3-A, D3-B, D3-C, clean pass, CP@5, @1, routability, engine engagement, Freerouting 2.1.0, 2.5.0, PCBench, EEBench, EDA-bench, PCBGolf, tscircuit datasets, Z01, SRJ33, TraceMaker, fastroute, devbisme, placement benchmark, 0 DRC

## Headline facts
1. PCBWorld-Bench is the only neutral multi-tool routing comparison [P].
2. No placement benchmark exists; no independent benchmark of Quilter, DeepPCB or Flux; vendor numbers are not comparable [P].
3. "0 DRC" is a weak metric: a no-tools Claude Code board passed DRC while routing signals through the GND plane (devbisme test) [P].
4. PCBWorld's Freerouting baseline (2.1.0) is stale (2.5.0 numbers below) [P].

## PCBWorld / PCBWorld-Bench
Paper, datasets, CP@5 definition (best-Φ rollout of 5, not "any of 5 clean"), @5 and @1 tables for Freerouting 2.1.0, KRT, PPO, GPT-5.4, OrthoRoute, engine engagement and times → [../routing/pcbworld.md](../routing/pcbworld.md#results-table-21-5). DeepPCB's own @1 claim → [deeppcb.md](deeppcb.md#vendor-reported-numbers) [V].

## Other router and tool measurements
| Item | Numbers | Tag |
|---|---|---|
| Freerouting self-reported suites | v2.5.0 release notes: 30.9% → 75.0% clean on 1,157 boards; nightly (1,142 fixtures): 2.6.0-RC3 87.7%, RC4 92.4% on tiers A+B only; "clean" = Freerouting's own check → [../routing/freerouting.md](../routing/freerouting.md#nightly-benchmark) | [P] self-reported |
| fastroute vs Freerouting (20 boards) | 510 s (420 s with PGO) vs 2,102 s; 20–300 MB vs 1–2 GB | [P] self-reported |
| kicad-tools TraceMaker | ≈0.99 / 1.00 / 0.90 vs Freerouting 2.2.4 ≈0.7 / 0.7 / 0.2 (single 60 s runs) | [P] self-reported (corrected baseline, VK) |
| KRT | 47/47 FTDI nets in 8.6 s; 28/28 LVDS pairs in 29.7 s; ongoing A/B on open-source boards | [P] self-reported |
| devbisme dual-ADC test | 8 AI tools + null baseline; all routed boards used Freerouting; null baseline $11.16 "DRC clean" with signals on the GND plane. Table → [kicad-ai-tools-and-mcp-servers.md](kicad-ai-tools-and-mcp-servers.md) | [P], unvalidated |
| POA A/B | Plain Claude Code 18/18 single edits vs 3/18 with an MCP-only plugin; 1.8× context → [../kicad/mcp-server-lessons.md](../kicad/mcp-server-lessons.md) | [P], small |
| DeepPCB | KiCad page 27,721 boards, 95.6% ≥95%, median 96.9%; platform mean 96.1% but only 87% ≥95% (the two vendor sources disagree) → [deeppcb.md](deeppcb.md#vendor-reported-numbers) | [V] |
| Quilter Speedrun | 38.5 h vs 428 h quoted; SOM placement human → [quilter.md](quilter.md#project-speedrun-dec-2025) | [V] |
| Cadence, Zuken | ">10X"; 25 vs 70 min placement (EMA); 45 min → 30 s (Zuken) → [commercial-incumbents-and-startups.md](commercial-incumbents-and-startups.md#incumbent-eda-vendors) | [V] |
| EEVblog 2010 | Freerouting 11 vias vs 18 manual on one board | [S] |

## Agent-level benchmarks and datasets
| Benchmark | Facts |
|---|---|
| **EEBench** (atopile) | Agents submit atopile bundles; deterministic build, SPICE at worst-case corners, BOM checks; score = 0.65 × technical + 0.35 × cost efficiency. "**Layout is deliberately out of scope** — sequenced, not forgotten"; V2 adds layout and fabrication. Tasks private. Snapshot Sept 2026: Claude Opus 5.5 75.0%, GPT-6 Astra 69.3% [P/S] ([methodology](https://eebench.org/methodology.html)) |
| **EDA-bench** | 35 Harbor tasks; agent reconstructs a full KiCad project, checked on schematic, PCB, connectivity, physical realization, ERC/DRC, functional contract. ICML 2026 "EDA Bench: Functional Failure Modes in PCB-Generating Agents" [S]; no model results in README [P] |
| **comma.ai PCBGolf** | score = PCBA bounding-box volume (mm³) + 50 × vias + 5,000 × copper layers; JLCPCB-manufacturable; $1,000 prize; deadline 2026-10-12 (past). **No licence file** → fetch-only [P] |
| **tscircuit** | `autorouting-dataset-01` (200 problems); `tscircuit/autorouting` (archived); `dataset-zero-obstacle-high-density-z01`; **Z01**: 1M 2-layer input/output images for vision models from `@tscircuit/high-density-a01` on random 10×10 mm problems (Hugging Face, 2026-02-26); SRJ33 (37 DRC-failure inputs) + Autorouter Benchmark Dashboard; `dsn-converter` [P] |
| **PCBench** | MIT, 21★. README "164 printed circuit boards", but `master_metadata.json` lists **1,194 designs from 846 repos** (2023-08). Ships `raw.kicad_pcb`, `processed.kicad_pcb`, PCB-RDL `final.json`, augmentation, RL environment. PCBWorld derives 679; Freerouting cites 1,157. Per-board licences mixed (54% none) → [../licensing/data-rulepacks-weights.md](../licensing/data-rulepacks-weights.md) [P] |

## Benchmark plan for our system
Tracks and corpus recipe → [../verification/benchmark-plan.md](../verification/benchmark-plan.md). Additions from the tool survey [I]:
- Secondary routing sets: Freerouting's PCBench suite and scores, tscircuit sets. Re-run current baselines (Freerouting 2.5.0, fastroute, kicad-tools, tscircuit router) on D3-A/B: comparing with the paper's 2.1.0 overstates gains.
- Report length vs lower bounds (`V2_LOWER_BOUND`) and layout-quality checks DRC misses, next to clean pass, routability, DRV, vias, wall time.
- Placement benchmark: strip placement from D3 boards, score downstream clean pass, wirelength, vias, rule proxies (decap distance); add multilayer boards; publish failures with PRO-style attempt accounting ([../kicad/mcp-server-testing-practices.md](../kicad/mcp-server-testing-practices.md)).
- Showcases (fetch-only): PCBGolf, devbisme dual-ADC test. Optional external baselines, never dependencies: DeepPCB (API), Quilter (manual upload), Electra (licence).

## Open questions
- PCBench counts (164 / 679 / 1,142 / 1,157 / 1,194) only partly reconciled; 1,194 vs 1,157 is perhaps loadable or convertible boards [I]. Release-note (1,157) and nightly (1,142) suites differ; tier definitions may too.
- PCBWorld did not evaluate Freerouting 2.5, fastroute, kicad-tools, tscircuit, Quilter or Flux; DeepPCB's leaderboard claim is self-reported.
- No independent SI measurement of AI-routed boards exists.

## Sources
- research notes: [existing_tools_and_apis.md § 5](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/existing_tools_and_apis.md); [verification_kicad_and_tools.md § 1 (#19–20, #26, #46), § 5 (9–10)](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_kicad_and_tools.md); [patents_and_industry.md § 2, § 4, § 6](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/patents_and_industry.md); [licensing.md § 1G](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/licensing.md)
- primary: [PCBench](https://github.com/PCBench/PCBench), [Freerouting scoring.md](https://github.com/freerouting/freerouting/blob/master/docs/scoring.md)
