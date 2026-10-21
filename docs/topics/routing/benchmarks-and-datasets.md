# Routing benchmarks and datasets

**TL;DR**
- Public real-board routing data grew sharply in 2024–26: **PCBench** (1,194 KiCad designs per metadata), **PCBWorld-Bench** (679 cleaned KiCad 9 boards + synthetic sets, KiCad-DRC metrics), **OmniRouting** (1,681 EAGLE designs, 2–8 layers), **Freerouting nightly** (~1,142 fixtures in tiers A–D), ASP-DAC'21 bm1–bm11.
- Bars to beat: PCBWorld D3-A/B **Freerouting 0.80 / 0.78 @5** (v2.1.0), **PPO 0.86 / 0.45**, DeepPCB vendor **@1 0.929 / 0.800**; OmniRouting **PcbRouter 56.2% NRR**.
- No public benchmark scores SI constraints (coupling, skew, length-group spread, return vias) — we must add an SI harness.
- No ISPD/ICCAD PCB routing contest exists.

## Key facts

| Dataset | Content | Notes |
|---|---|---|
| **PCBench** ([metadata](https://github.com/PCBench/PCBench/blob/main/PCBs/master_metadata.json)) | 1,194 unique KiCad designs from 846 repos (133 Kitspace); per board `raw.kicad_pcb`, `processed.kicad_pcb`, PCB-RDL `final.json` | README still says 164; cleaning re-routes copper-pour nets with an autorouter (DeepPCB note) [P/V] |
| **PCBWorld-Bench** | D1 grid (10–500), D2 synthetic gridless (10k/128/128), D3 679 real boards from a 1,182-board KiCad 9 pool: A 100 (≤31 pads), B 287 (≤100), C 292 (≤451 nets, ≤2,103 pads, 8 layers); 8 metrics; @5 and @1 | Evaluations use 99 D3-A + 10 D3-B (2-layer) boards; 4-seed means for routers/RL ([PCBWorld](pcbworld.md)) |
| **OmniRouting** | 1,681 EAGLE designs; 77.24K placements, 168.82K pads, 55.83K net connections, 84.60K vias, 4.31K pours; NRR, PRR, opens, shorts, DRC, multi-scale graph similarity | Release "will open-source", license unconfirmed ([LLM evidence](llm-routing-evidence.md)) |
| **ASP-DAC 2021 PCBBenchmarks** | bm1–bm11 KiCad boards, 15–99 nets, 2–4 layers | Reused by FanoutNet, TRouter (via PcbRouter set) and Freerouting ("DAC2020") ([repo](https://github.com/aspdac-submission-pcb-layout/PCBBenchmarks)) |
| **Freerouting nightly** | 1,142 fixtures (PCBench DSNs via `pcbnew.ExportSpecctraDSN`, DAC2020, KiCad 10 demos) in tiers A–D; ground truth via KiCad DRC | Tier D 13.6–18.2% clean ([freerouting](freerouting.md)) |
| **PCB-Bench** (ICLR'26) | ~3,700 text QA, ~500 multimodal, >170 projects | Comprehension only |
| **tscircuit autorouting** | Synthetic problems with speed/completion/quality criteria | ([repo](https://github.com/tscircuit/autorouting)) |
| FanoutNet Huawei boards | 5 industrial 6-layer HDI | Private |
| Cypress / OmniLayout placement sets | Can be routed for end-to-end tests | ([placement metrics](../placement/benchmarks-and-metrics.md)) |
| VLSI-only | XRoute, Jumanji Connector | — |

**Published bars**
| Benchmark | Result |
|---|---|
| PCBWorld D3-A / D3-B @5 | Freerouting 2.1.0 0.80 / 0.78; KRT 0.74 / 0.20; PPO 0.86 / 0.45; PPO w/o finish 0.94 / 0.42; GPT-5.4 0.65 / 0.00 |
| PCBWorld @1 | D3-A Freerouting 0.75, PPO w/o finish 0.81; D3-B Freerouting 0.64 |
| PCBWorld-Bench (DeepPCB, vendor @1) | 0.929 / 0.800 |
| OmniRouting NRR / PRR | PcbRouter 56.20 / 71.37%; best agentic LMM 27.98 / 30.34%; human 93.58 / 95.91% |
| FanoutNet industrial | FanoutNet 100%, NB-A* 95%, ELECTRA 91%, Freerouting 1.4.5.1 81% |
| DATE'23 MCTS router | 10/10 boards vs FreeRouting 8/10, DeepPCB 8/10 |

**Contests**: ICCAD 2015–2026 problem titles contain no PCB/board/package problem; ICCAD 2018 Problem B (bus routing) is IC ([length matching](length-matching-and-buses.md)).

## Recommendations for our system
- Evaluation stack [I]: PCBWorld D3-A/B with @1 and @5 next to published Freerouting/KRT/PPO/DeepPCB numbers; D3-C + Freerouting Tier C/D as stress sets; OmniRouting multilayer subset (EAGLE, needs conversion); a custom **SI-constraint harness** (coupling, skew, length-group spread, return vias, plane-reference changes) plus practitioner metrics ([skepticism](autorouter-skepticism.md)).
- Re-score every router with KiCad DRC; pin router versions and flags; report seed means and tokens/time per board [I].
- First key experiment: LLM relational planner + classical realizers vs Freerouting/DeepPCB on real multilayer boards with SI constraints [I].

## Conflicts and open questions
- PCBench count: 1,194 (metadata) vs 164 (README) vs PCBWorld's 1,182 pool.
- OmniRouting release status/licence unconfirmed; no contest found.

## Sources
- research notes: [routing_algorithms.md § Q7](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/routing_algorithms.md); [verification_papers.md § 1 rows 5–8, § 2.1](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_papers.md)

See also: [pcbworld](pcbworld.md) · [freerouting](freerouting.md) · [placement/benchmarks-and-metrics](../placement/benchmarks-and-metrics.md)
