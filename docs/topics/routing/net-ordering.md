# Net ordering: why it matters and how to reduce dependence on it

Scope: evidence on net-order sensitivity, ordering rules inside routers, learned ordering. Not here: negotiation schedules -> [PathFinder](pathfinder-negotiated-congestion.md).
Keys: net ordering, net order, priority tiers, Abel 1972, easiest first, pairwise interaction score, toporouter, KRT MPS, maximum planar subset, inside-out, middle-out, ItemSelectionStrategy, DreamerV3, Ranking Cost, net_select, order(tiers), net_order(rank)

## Order as a lever
1. Net order and cost weights are the main levers of sequential routers; most ML that helps on PCBs learns exactly these two.
2. With negotiation/rip-up, order mainly decides which nets get the good resources: a priority decision an LLM can legitimately make. In sequential routing it also decides completion (PCBWorld: the first `net_select` often decides success; a learned Freerouting order reached 96% completion).
3. Negotiation/rip-up makes order matter much less (negotiation-based layer assignment; SURF simultaneous global routing; MCTS routers "not prone to net ordering").

## Evidence and conflicts

[P-abs]
- Abel (IEEE TC 1972): for one-connection-at-a-time maze routers, total minimum length of completed connections is experimentally order-independent. NYCU slides cite the same paper for "finding the optimal net ordering is proven to be NP-hard" and "net ordering greatly affects routing solutions": conflict (Abel full text unread).
- Servit–Schmidt (CAD 1980): order and source/target choice influence quality and time.
- Textbook heuristics: ascending pins inside bbox; ascending length when routability-critical (descending when timing-critical); timing criticality ([NYCU lec6](https://tiger.iee.nycu.edu.tw/course/EDAIntro2026Spring/materials/lec6.pdf) [P-slides]).
- Groeneveld (D&T'89): ordering junction pins on region boundaries avoids wire twisting.
- Liu–Li ASP-DAC'11: "net assignment ordering only slightly influences the quality" in negotiation-based layer assignment → [layer assignment](layer-assignment-and-vias.md).

## Ordering inside routers

[P/P-code]
| Router | Rule |
|---|---|
| gEDA rectangle expansion | Smallest bbox first; later passes by previous-pass cost ascending ("easiest first") |
| gEDA toporouter | Pairwise interaction: route each net alone, test others (unaffected/detour/fail); sort by fewest fails, then smallest detour sum |
| PcbRouter | Diff pairs first, then fixed netlist order with escalating costs |
| **KRT MPS (default)** | Unroll chip boundaries to [0,1]; inverted source/target order = crossing; greedy maximum planar subset on the conflict graph; alternatives inside-out (BGAs), bus middle-out ([doc](https://github.com/drandyhaas/KiCadRoutingTools/blob/main/docs/net-ordering.md)) |
| Freerouting | `ItemSelectionStrategy` SEQUENTIAL / PRIORITIZED; fanout most-SMD-pins part first, outermost pins first: "breaks down for adjacent dense components" |
| Altium Situs | Routing Priority rules for difficult or cleanest nets |
| DATE'23 MCTS router | Random order, multi-pin nets built incrementally → [ML/RL routing](ml-rl-routing.md) |
| Security-aware PCB routing (ISQED'26) | Routing sequences assigned before trace generation [P-abs] |

## Learned ordering

[P-abs]
- DreamerV3 + Freerouting (ESWA'26): latent world model optimizes Freerouting net order "before physical execution"; 96% completion; generalizes to unseen 6-layer boards → [ML/RL routing](ml-rl-routing.md).
- Ranking Cost: ES-learned ranking parameter + per-net cost maps for A*.
- Async RL net-order exploration with transfer (DATE'21 → TCAD'22, VLSI): −26% DRC violations.
- ML ordering for layer assignment in multilayer package-substrate routing beats heuristic score functions ([arXiv 2412.21035](https://arxiv.org/abs/2412.21035)).
- XRoute RL environment; IJCAI'25 transformer RL ordering (VLSI).
- OrderPlace (LLM-evolved macro order, −34% HPWL) suggests evolving routing order heuristics → [LLM-evolved heuristics](../solvers/llm-evolved-heuristics.md) [I].
- LLM as MAPF meta-controller (priorities for prioritized planning / PIBT) → [cross-domain routing](cross-domain-routing-transplants.md).

## Ordering in kae

[I]
- LLM sets priority tiers (power, high-speed, critical analog first) and the first nets explicitly; negotiation protects aggregate completion.
- Compute toporouter-style pairwise scores (O(n²) single-net routes; cheap at ~10² nets) and MPS crossings for critical/medium nets; give the LLM a quantified conflict graph ("A forces B to detour x mm").
- Learn or LLM-propose order + cost schedules for Freerouting/KRT/in-house PathFinder offline (DreamerV3+FR, Ranking Cost, CQL pattern); the engine keeps legality.
- Relation API: `order(tiers)` / `net_order(rank)` → [LLM routing evidence](llm-routing-evidence.md).

## Open questions

- No PCB-specific study compares ordering heuristics on modern boards; no GNN PCB net-ordering paper found; no study isolates an LLM-chosen net order vs defaults on real multilayer boards.

## Sources

- [routing_classics_supplement.md § Q6](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/routing_classics_supplement.md); [routing_algorithms.md § Q1, Q3](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/routing_algorithms.md)
