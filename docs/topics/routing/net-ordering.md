# Net ordering: why it matters and how to reduce dependence on it

**TL;DR**
- Net order and cost weights are the main levers of sequential routers; most ML that helps on PCBs learns exactly these two.
- The literature conflicts (Abel 1972: aggregate completed ideal length order-independent; textbooks: order "greatly affects" results). Resolution: **order decides which nets get the good resources**, not aggregate completion — a priority decision an LLM can legitimately make.
- Protect aggregate completion with **negotiation/rip-up**, which makes order matter much less (negotiation-based layer assignment; SURF simultaneous global routing; MCTS routers "not prone to net ordering").
- Give the LLM quantified conflict data: toporouter-style **pairwise-interaction scores** and KRT **MPS crossing analysis**.

## Key facts

**Evidence and conflicts** [P-abs]
- Abel (IEEE TC 1972): for one-connection-at-a-time maze routers, total minimum length of completed connections is experimentally independent of order. NYCU slides cite the same paper for "finding the optimal net ordering is proven to be NP-hard" and "net ordering greatly affects routing solutions" — **conflict** (Abel full text unread).
- Servit–Schmidt (CAD 1980): order and source/target choice influenced quality and time.
- Textbook heuristics: ascending pins inside bbox; ascending length when routability-critical (descending when timing-critical); timing criticality ([NYCU lec6](https://tiger.iee.nycu.edu.tw/course/EDAIntro2026Spring/materials/lec6.pdf) [P-slides]).
- Groeneveld (D&T'89): ordering junction pins on region boundaries avoids wire twisting.
- Negotiation-based layer assignment: "net assignment ordering only slightly influences the quality" (Liu–Li ASP-DAC'11) ([layer assignment](layer-assignment-and-vias.md)).

**Ordering inside routers** [P/P-code]
| Router | Rule |
|---|---|
| gEDA rectangle expansion | Smallest bbox first; later passes by previous-pass cost ascending ("easiest first") |
| gEDA toporouter | Pairwise interaction: route each net alone, test others (unaffected/detour/fail); sort by fewest fails, then smallest detour sum |
| PcbRouter | Diff pairs first, then fixed netlist order with escalating costs |
| **KRT MPS (default)** | Unroll chip boundaries to [0,1]; inverted source/target order = crossing; greedy maximum planar subset on the conflict graph; alternatives inside-out (BGAs), bus middle-out ([doc](https://github.com/drandyhaas/KiCadRoutingTools/blob/main/docs/net-ordering.md)) |
| Freerouting | `ItemSelectionStrategy` SEQUENTIAL / PRIORITIZED; fanout most-SMD-pins part first, outermost pins first — "breaks down for adjacent dense components" |
| Altium Situs | Routing Priority rules for difficult or cleanest nets |
| DATE'23 MCTS router | Random order, multi-pin nets built incrementally ([ML/RL routing](ml-rl-routing.md)) |

**Learned ordering**
- DreamerV3 + Freerouting (ESWA'26): latent world model optimizes Freerouting net order "before physical execution"; 96% completion; generalizes to unseen 6-layer boards [P-abs] ([ML/RL routing](ml-rl-routing.md)).
- Ranking Cost: ES-learned ranking parameter + per-net cost maps for A* [P-abs].
- Async RL net-order exploration with transfer (DATE'21 → TCAD'22, VLSI): −26% DRC violations [P-abs].
- ML ordering for layer assignment in multilayer **package substrate** routing beats heuristic score functions ([arXiv 2412.21035](https://arxiv.org/abs/2412.21035) [P-abs]).
- XRoute RL environment; IJCAI'25 transformer RL ordering (VLSI) [P-abs].
- LLM-evolved macro placement order (OrderPlace: −34% HPWL) suggests evolving routing order heuristics too ([LLM-evolved heuristics](../solvers/llm-evolved-heuristics.md)).
- PCBWorld: **the first `net_select` often decides success** ([PCBWorld](pcbworld.md)).
- Security-aware PCB routing assigns routing sequences before trace generation (ISQED'26) [P-abs].
- LLM as MAPF meta-controller: priorities for prioritized planning / PIBT ([cross-domain routing](cross-domain-routing-transplants.md)).

## Recommendations for our system
- LLM sets **priority tiers** (power, high-speed, critical analog first) and the first nets explicitly; negotiation protects aggregate completion [I].
- Compute toporouter-style pairwise scores (O(n²) single-net routes; cheap at ~10² nets) and MPS crossings for critical/medium nets; give the LLM a quantified conflict graph ("A forces B to detour x mm") [I].
- Learn or LLM-propose order + cost schedules for Freerouting/KRT/in-house PathFinder offline (DreamerV3+FR, Ranking Cost, CQL pattern) — legality stays guaranteed by the engine [I].
- Relation API: `order(tiers)` / `net_order(rank)` ([LLM routing evidence](llm-routing-evidence.md)) [I].

## Conflicts and open questions
- No PCB-specific study compares ordering heuristics on modern boards; no GNN PCB net-ordering paper found.
- No study isolates an LLM-chosen net order vs defaults on real multilayer boards.

## Sources
- research notes: [routing_classics_supplement.md § Q6](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/routing_classics_supplement.md); [routing_algorithms.md § Q1, Q3](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/routing_algorithms.md)

See also: [pathfinder-negotiated-congestion](pathfinder-negotiated-congestion.md) · [ml-rl-routing](ml-rl-routing.md) · [topological-routing](topological-routing.md)
