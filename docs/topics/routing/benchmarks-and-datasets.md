# Routing benchmarks and datasets

Scope: public PCB routing datasets, published score bars, contests. Not here: PCBWorld internals -> [PCBWorld](pcbworld.md); placement benchmarks -> [placement metrics](../placement/benchmarks-and-metrics.md).
Keys: PCBench, PCBWorld-Bench, D3-A, D3-B, D3-C, OmniRouting, ASP-DAC 2021 PCBBenchmarks, bm1–bm11, Freerouting nightly, tiers A–D, PCB-Bench, tscircuit autorouting, FanoutNet Huawei boards, NRR, clean-pass @5, @1, ICCAD contest, SI harness

## Datasets

| Dataset | Content | Notes |
|---|---|---|
| **PCBench** ([metadata](https://github.com/PCBench/PCBench/blob/main/PCBs/master_metadata.json)) | 1,194 unique KiCad designs from 846 repos (133 Kitspace); per board `raw.kicad_pcb`, `processed.kicad_pcb`, PCB-RDL `final.json` | README still says 164; PCBWorld uses a 1,182 pool; cleaning re-routes copper-pour nets with an autorouter (DeepPCB note) [P/V] |
| **PCBWorld-Bench** | D1 grid (10–500), D2 synthetic gridless (10k/128/128), D3 679 real boards: A 100 (≤31 pads), B 287 (≤100), C 292 (unevaluated); 8 metrics; @5 and @1 | Evaluations use 99 D3-A + 10 D3-B (2-layer) boards; 4-seed means for routers/RL → [PCBWorld](pcbworld.md#datasets) |
| **OmniRouting** | 1,681 EAGLE designs, 2–8 layers; NRR, PRR, opens, shorts, DRC, multi-scale graph similarity | Release "will open-source", licence unconfirmed → [LLM evidence](llm-routing-evidence.md#omnirouting) |
| **ASP-DAC 2021 PCBBenchmarks** | bm1–bm11 KiCad boards, 15–99 nets, 2–4 layers | Reused by FanoutNet, TRouter (via PcbRouter set) and Freerouting ("DAC2020") ([repo](https://github.com/aspdac-submission-pcb-layout/PCBBenchmarks)) |
| **Freerouting nightly** | 1,142 fixtures (PCBench DSNs via `pcbnew.ExportSpecctraDSN`, DAC2020, KiCad 10 demos) in tiers A–D; "clean" = Freerouting's own check, not KiCad DRC (KiCad DRC is PCBench's arbiter for the human boards) | Tier D 13.6–18.2% clean (RC2/RC3); v2.5.0 release notes use a different 1,157-board suite → [freerouting](freerouting.md) |
| **PCB-Bench** (ICLR'26) | ~3,700 text QA, ~500 multimodal, >170 projects | Comprehension only |
| **tscircuit autorouting** | Synthetic problems with speed/completion/quality criteria | ([repo](https://github.com/tscircuit/autorouting)) |
| FanoutNet Huawei boards | 5 industrial 6-layer HDI | Private |
| Cypress / OmniLayout placement sets | Can be routed for end-to-end tests | → [placement metrics](../placement/benchmarks-and-metrics.md) |
| VLSI-only | XRoute, Jumanji Connector | — |

## Published bars

| Benchmark | Result |
|---|---|
| PCBWorld D3-A / D3-B @5 and @1 | Freerouting 2.1.0 (`-mp 10`), KRT, PPO, GPT-5.4 on 99 D3-A + 10 D3-B boards → [PCBWorld](pcbworld.md#results-table-21-5) |
| PCBWorld-Bench (DeepPCB, vendor @1) | 0.929 / 0.800, vendor-run → [DeepPCB](../landscape/deeppcb.md#vendor-reported-numbers) [V] |
| OmniRouting NRR / PRR | PcbRouter 56.20 / 71.37%; best agentic LMM 27.98 / 30.34%; human 93.58 / 95.91% |
| FanoutNet industrial | FanoutNet 100%, NB-A* 95%, ELECTRA 91%, Freerouting 1.4.5.1 81% |
| DATE'23 MCTS router | 10/10 boards vs FreeRouting 8/10, DeepPCB 8/10 |

## Contests and SI coverage

- No ISPD/ICCAD PCB routing contest exists: ICCAD 2015–2026 problem titles contain no PCB/board/package problem; ICCAD 2018 Problem B (bus routing) is IC → [length matching](length-matching-and-buses.md).
- No public benchmark scores SI constraints (coupling, skew, length-group spread, return vias): kae must add an SI harness [I].

## Evaluation stack for kae

[I]
- PCBWorld D3-A/B with @1 and @5 next to published Freerouting/KRT/PPO/DeepPCB numbers; D3-C + Freerouting Tier C/D as stress sets; OmniRouting multilayer subset (EAGLE, needs conversion); a custom SI-constraint harness (coupling, skew, length-group spread, return vias, plane-reference changes) plus practitioner metrics → [skepticism](autorouter-skepticism.md#practitioner-metrics-to-score).
- Re-score every router with KiCad DRC; pin router versions and flags; report seed means and tokens/time per board.
- First key experiment: LLM relational planner + classical realizers vs Freerouting/DeepPCB on real multilayer boards with SI constraints.

## Open questions

- PCBench count: 1,194 (metadata) vs 164 (README) vs PCBWorld's 1,182 pool.
- OmniRouting release status/licence unconfirmed.

## Sources

- [routing_algorithms.md § Q7](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/routing_algorithms.md); [verification_papers.md § 1 rows 5–8, § 2.1](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_papers.md)
