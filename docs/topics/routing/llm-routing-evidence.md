# LLMs and routing: OmniRouting, RAC, and the relations-not-coordinates rule

Scope: evidence on LLMs routing PCBs directly vs through relations; the routing relation vocabulary. Not here: PCBWorld benchmark detail -> [PCBWorld](pcbworld.md); LLM placement -> [LLM-guided placement](../placement/llm-guided-placement.md).
Keys: OmniRouting, NRR, PRR, Multi-Scale Graph Similarity, RAC, Relational Agent Contract, relation bundle, ordinal magnitudes, admissible relaxations, clean-pass, PCB-Bench, BWEI, plan-pcb-routing, relational planner, route_class, pair, match_group, corridor, order, keepout, lock, return_vias, layer_pref, via_limit

**Results**
1. LLMs should not emit copper. OmniRouting: best LMM 12.60% net routability zero-shot, 27.98% agentic, vs PcbRouter 56.20%, humans 93.58%; PCBWorld engine-free 0.02.
2. Relations beat coordinates across 9 models (RAC): relation bundles 90.9% clean-pass vs 23.2% direct coordinates; a Python sandbox does not rescue coordinates (21.0%).
3. Use ordinal magnitudes (tight/close/loose) fixed solver-side, submit relations as one bundle (90.9% vs 62.4% sequential), return conflicting constraints + admissible relaxations.
4. Relations survive geometry change: re-solve after resizes 89.5% vs 65.6% for coordinate reuse: persist relations as the intent artifact.
5. Tools help local legality and corridor choice more than global connectivity; "feedback quality matters more than iteration count".

## OmniRouting

Penn State et al., Aug 2026; [arXiv 2608.04434](https://arxiv.org/abs/2608.04434) [P], VP-verified.
- 1,681 schematic-coupled EAGLE designs (SparkFun, Arduino, Adafruit, Seeed, ProtoCentral, GitHub); 31.5–18,903 mm², 2–8 layers; 77.24K placements, 168.82K pads, 55.83K net connections, 84.60K vias, 4.31K pours. Prior PCB routing studies mostly used <20 real boards.
- Tasks: geometric, design-rule-aware, electrical-functionality, tool-augmented agentic routing. Metrics: NRR, PRR, opens, shorts, DRC, Multi-Scale Graph Similarity to the human reference.

| Router | NRR | PRR |
|---|---|---|
| Best zero-shot LMM | 12.60% | 15.41% |
| Best agentic | 27.98% | 30.34% |
| Human reference | 93.58% | 95.91% |
| PcbRouter (open, classical) | 56.20% | 71.37% |
| GPCB (learned) | 0.69% | — |

- Base LMM outputs: 69.8–431.3 DRC violations on average (human 0.80), 20–78% shorts; failures include routing GND as traces instead of pours/return paths.
- Preroute tool raised graph similarity for all 8 models (GPT-5.5 18.45 → 30.23%) while connectivity stayed low; more steps ≠ better (GPT-5.5 16.97 → 20.78 steps, NRR 21.71 → 27.98%; GPT-5-mini 18.38 → 23.65 steps, NRR 9.86 → 6.82%).
- Data "will open-source" (unconfirmed; licence unknown); "EMNLP Findings" venue NOT FOUND.

## RAC: Relational Agent Contract

Univ. of Washington, 14 Oct 2026; [arXiv 2610.20935](https://arxiv.org/abs/2610.20935) [P], VP-detailed.
- Agent observes exact authoritative state (incl. coordinates) but acts only through relations over named objects: proximity, alignment, symmetry, edge association, keepouts, matched routing, layer preference, via limits. No action accepts a coordinate or metric distance; magnitudes are ordinal classes with solver-side mm values.
- Examples: `board_edge(J1, left)`, `place_relative(C1, U1.R1, near, tight)`, `route_matched([N2, N3], 5%)`.
- Full set = one bundle realized jointly; independent DRC + relation-specific geometric oracles verify; infeasibility feedback names failure type, conflicting constraints, violation magnitudes, admissible relaxations.

| Interface (98 tasks: 42 routing, 31 placement, 17 combined, 8 repair; 6 seeds; ≤5 calls; 9 models) | Clean-pass |
|---|---|
| Direct coordinates | 23.2% |
| Coordinates + Python sandbox | 21.0% |
| PCBWorld-style candidate selection | 37.4% |
| Sequential single relations | 62.4% |
| Requirements-only delegation | 74.0% |
| **RAC** | **90.9%** (77.6–95.9% across models) |

- 22.9–48.5% fewer tokens than candidate selection; faster for 7/9 models; "the engineering contract matters more than model selection".
- Robustness: same relations re-solved after 20% board shrink/expansion and 25% footprint shrink: 89.5% (411/459) vs 65.6% best coordinate-reuse control; board shrink hardest (77.1% vs 47.7%).
- Caveats: tasks small/synthetic (~5–10 parts); backend placer/router unidentified. Replication at real-board scale (PCBWorld D3) is the key experiment.

## Other LLM evidence

- PCBWorld: interactive 0.65 vs plan-and-execute 0.19 vs engine-free 0.02 (D3-A); DRC-blind prompts; huge token cost → [PCBWorld](pcbworld.md#llm-agents).
- PCB-Bench (ICLR'26): ~3,700 text QA, ~500 multimodal, >170 projects; comprehension only, no routing generation; reveals spatial-reasoning gaps; BWEI subset ~11 items (100% vs 90.9% gap = one question) ([ICLR](https://iclr.cc/virtual/2026/poster/10009621) [P], VP).
- Hybrids that work are staged and intent-driven [P/V]: DeepPCB (human routes critical nets → Cooper fixes setup → RL finishes); KRT `/plan-pcb-routing` Claude skill (analyzes fanout, diff pairs, DDR groups, power nets and speeds; generates/runs a replayable JSON plan: pours → diff pairs → bulk → length matching → repair) ([doc](https://github.com/drandyhaas/KiCadRoutingTools/blob/main/docs/claude-skills.md)); DreamerV3+FR (RL order → Freerouting draws); FanoutNet (RL fanout → negotiated A*); Freerouting preserves fixed copper exactly, so critical nets can be pre-routed and frozen.
- Negative results elsewhere: LLMs fail at direct MAPF even with 2 agents in a maze → [cross-domain routing](cross-domain-routing-transplants.md); PlanarBench crossing-free drawing → [scene transplants](../placement/scene-layout-transplants.md).

## Three-layer architecture and relation vocabulary

[I]
1. LLM as relational planner: classify nets, set constraints, choose per-class engine, order work, sketch corridors as relations.
2. Deterministic realizers: Freerouting bulk; KRT-style A* or PNS DP placer for pairs/buses; PNS waypoint realization, shove repair, smoothing; KiCad tuning; optional DeepPCB for non-SI bulk.
3. KiCad DRC + SI checks returning per-predicate evidence.
- Vocabulary: `route_class(net_class, engine, layers, width, via_policy)`, `pair(netP, netN, gap, max_uncoupled)`, `match_group(nets, tol_ps, reserve_area=region)`, `corridor(net|bus, via=[regions], layer)`, `order(tiers)`, `keepout(region, classes)`, `lock(nets)`, `return_vias(pair|class)`, `layer_pref`, `via_limit`.
- Loop: topology sketch → capacity check (RUDY / SURF cut test, [topological](topological-routing.md)) → realization → DRC → per-predicate failures to the LLM.
- Calibrate ordinal classes per component/net class from human boards (PCBWorld D3 excluding the 99 D3-A + 10 D3-B evaluation boards, which must never be mined, fitted or calibrated on). Track LLM tokens and time per board.

## Open questions

- No study isolates an LLM-chosen order/corridor vs defaults on multilayer boards.

## Sources

- [routing_algorithms.md § Q3, Q6, Implications](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/routing_algorithms.md); [routing_classics_supplement.md § Q7](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/routing_classics_supplement.md); [verification_papers.md § 1 rows 24, 29; § 2.4, 2.9; § 3](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_papers.md)
