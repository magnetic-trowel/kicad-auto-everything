# Placement benchmarks, datasets and metrics

**TL;DR**
- Open placement data now exists: **Cypress suite** (Apache-2.0, KiCad + Bookshelf), **OmniLayout** (1,681 EAGLE designs, CC-BY-4.0 data per ethics statement), and the **PCBWorld D3** KiCad 9 boards (679, reusable for placement).
- Evaluation norm: route with FreeRouting, report routability, routed length, vias, DRVs, plus crossings/alignment proxies — but **Freerouting versions differ across papers**, so numbers are not comparable.
- **OmniLayout (VP-corrected):** frontier LMMs reach high FreeRouting routability (GPT-5.5 0.90 zero-shot, 0.95 few-shot) — above academic placers — but fail pad-level legality (79.82% of outputs have ≥1 pad overlap).
- HPWL is necessary but insufficient; **proxy-to-routed correlation on PCBs rests on little, weak evidence** (one third-party unreviewed study of 64 boards; one Cadence patent dataset of one board) — calibrate before use ([learned scores](../data/imitation-and-learned-scores.md), [patents](../landscape/patents-watchlist.md)).

## Key facts

**Datasets**
| Dataset | Boards | Access | Notes |
|---|---|---|---|
| NS-Place | 14 | not released | 8–64 parts + one 1,570-part board; utilization 0.10–0.79 |
| PCBAgent | 17 industrial | private | 18–414 parts, density 0.33–0.76 |
| HiePlace | 19 | 15 private phone boards + 4 from a now-404 repo | density ≈0.80 |
| ModuPlace | 11 | OpenROAD + industry | 35–97 parts |
| Cypress | small + big | Apache-2.0 repo | 10 small "synthesized from real commercial designs" + 5 commercial big designs (VP); repo 20 Bookshelf + 10 KiCad vs slides 10 small (41–476 parts) + 5 big (5,118–6,628) — **conflict**; the KiCad files have no Edge.Cuts outline, no copper and a stale net table ([open board sources](../data/open-board-sources.md)) |
| **OmniLayout** | 1,681 | CC-BY-4.0 data (paper CC BY-NC-ND; third-party dead-link report) | EAGLE 9.6.2 → DSN; 2–8 layers; 77.24K placements, 168.82K pads, 139.4K nets with layout and schematic spatial weights |
| PCBWorld D3 | 679 | KiCad 9, per-board source licenses | see [routing benchmarks](../routing/benchmarks-and-datasets.md) |

OmniLayout notes most PCB works use private sets of 10–20 boards and lists Cypress as 10 layouts (2.6K components) ([arXiv 2607.03261](https://arxiv.org/pdf/2607.03261) [P]). Area range 31.5–22,459 mm² (OmniLayout notes) vs 31.5–18,903 mm² (OmniRouting) — **conflict**.

**OmniLayout task and results** (Penn State-led, one MSR co-author; VP-corrected) [P]
- Input: schematic image, DXF outline (JSON), netlist with spatial weights, IC dimensions. Output: x, y, side, orientation incl. mirrored MR0–MR270.
- Metrics: overlap (OO), out-of-bounds (OoB), HPWL, net crossings (NC), net separation (NS), FreeRouting PRWL / routed ratio (RR) / vias, schematic relational distance, S_ref = 1/(1+D_ref), P/R/E2E pass.
- 9 LMMs (GPT-5.5, GPT-5-mini, Claude Sonnet 4.6, Gemini 3.1 Pro, Gemini 2.5 Flash-lite, LLaMA 4 Maverick, Ministral 14B, Qwen3.5-9B, Qwen3.6-35B-A3B) + 6 PnR tools.

| Method | FreeRouting RR |
|---|---|
| Human reference | 1.00 |
| GPT-5.5 few-shot / zero-shot | 0.95 / 0.90 |
| Gemini 3.1 Pro with schematic / zero-shot | 0.91–0.92 / 0.34 |
| Quilter | 0.84 |
| GPT-5-mini | 0.84 |
| Claude Sonnet 4.6 | 0.76 |
| Chen et al. DAC'25 | 0.62 |
| PCBAgent | 0.42 |
| Cypress | 0.33 |
| Qwen (zero-shot) | 0.31 |
| SA-PCB | 0.25 |
| NS-Place | 0.23 |

- LMM failures: 79.82% outputs ≥1 pad overlap; 72.89% ≥1 part out of bounds; ~80% parts on top; reference similarity <60%; best E2E pass 62.6% (GPT-5.5 few-shot); weaker on dense boards (>~40 parts).
- Agentic tools (visualization, geometry check, routability score, ≤50 turns): **structured text naming conflicting parts and locations gave the lowest overlap**, better than images; combining all tools not uniformly best; schematic context raised functional-grouping AUC in 15/15 comparisons (+0.079–0.091); few-shot barely changed AUC (−0.006).

**Metric families in PCB papers** [P]
- Legality: overlap, out-of-boundary, spacing/clearance.
- Proxies: HPWL, total Euclidean WL (Lim: correlates better with routed length), RMST, net crossings, net separation, Surface Layer Wire count (PCBAgent), first-priority HPWL, misalignment count, area ratio (HiePlace), RUDY.
- Post-route: routability (fraction routed), routed length, vias, DRVs/unrouted.
- EM: insertion loss, crosstalk (ModuPlace).
- LLM benchmarks: schematic-relation preservation, reference similarity.
- VLSI warning: Circuit Training proxy (1.0·WL + 1.0·density top-10%×0.5 + 0.5·congestion top-5%) "correlates weakly" with post-route PPA (VP-verified).
- Router configurations differ: Cypress Freerouting v1.9.0 2-layer, % routed pin pairs; PCBWorld 2.1.0 `-mp 10`; ModuPlace averages PcbRouter + Freerouting configs.

## Recommendations for our system
- Metric stack [I]: (1) hard legality via KiCad DRC (courtyard, Edge.Cuts, keep-outs, clearance); (2) fast proxies (net-class-weighted HPWL/TEWL, crossings, RUDY, SLW-like count, alignment count); (3) domain rules (decap-to-pin, crystal distance, switching-loop area, connector at edge, thermal spacing); (4) periodic ground truth (pinned Freerouting RR, routed length, vias, DRC).
- Benchmark ladder: OmniLayout-style RR/PRWL + pad-overlap/OoB, with **Chen DAC'25 and Quilter as bars**; Cypress KiCad boards (after synthesizing outlines and rebuilding the net table); OmniLayout subset; PCBWorld D3 boards with routing stripped [I].
- Calibrate proxies against Freerouting on a held-out set before trusting them inside tuners ([multi-fidelity](../solvers/performance-and-multifidelity.md)) [I].
- Return structured text conflict lists to the LLM, not images ([LLM-guided](llm-guided-placement.md)) [I].

## Conflicts and open questions
- OmniLayout/OmniRouting "EMNLP Findings 2026" venue claim: NOT FOUND.
- OmniLayout per-model tables were first unextractable; VP values above come from Tab. 2.
- Proxy-to-routed correlation across many PCBs is barely measured: one unreviewed 64-board study and one single-board patent dataset ([learned scores](../data/imitation-and-learned-scores.md)); OmniLayout PRWL vs RR could enable a larger test.

## Sources
- research notes: [placement_algorithms.md § Q4, Q7](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/placement_algorithms.md); [verification_papers.md § 1 rows 25–29, § 2.9](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_papers.md)

See also: [pcb-placers-2022-2026](pcb-placers-2022-2026.md) · [routing/benchmarks-and-datasets](../routing/benchmarks-and-datasets.md) · [solvers/benchmarks](../solvers/benchmarks.md)
