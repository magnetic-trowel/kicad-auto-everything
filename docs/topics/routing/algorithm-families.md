# Routing algorithm families (maze, line-probe, channel, gridless, rip-up)

**TL;DR**
- Every production-grade open PCB router (Oct 2026) is a **sequential, cost-driven path search + rip-up/reroute + post-route optimizer**: Freerouting (gridless A* over convex rooms), KiCadRoutingTools/KRT (Rust octilinear grid A*); the archived OpenROAD PcbRouter (grid A* with 45°, reads KiCad 5.1.2) follows the same pattern.
- The dominant PCB family is **free-space decomposition + negotiated conflict pricing** (Freerouting rooms, gEDA expanding rectangles, Specctra shapes) — see [PathFinder](pathfinder-negotiated-congestion.md).
- Line probes and channel routers survive only as **passes/patterns** (Situs "Straighten", "Memory").
- KiCad PNS is **not** a path searcher ([PNS](kicad-pns-router.md)). Classical routers led on PCBWorld D3-B and OmniRouting, but an engine-grounded PPO policy led on D3-A (0.86, 0.94 without `finish`, vs Freerouting 0.80 @5) ([PCBWorld](pcbworld.md)).

## Key facts

**Maze / Lee / A\***
- Lee 1961 is the root ([DOI](https://doi.org/10.1109/TEC.1961.5219222)).
- Soukup's fast maze router: line search toward the target, Lee "bubbles" around obstacles; **10–50× faster than Lee on two-layer boards**, complete, suboptimal when congested ([PDF](https://janders.eecg.utoronto.ca/1387/readings/soukup.pdf) [P]).
- Freerouting `DestinationDistance`: admissible lower bound from per-layer minimum trace costs + minimum via costs; `SortedSet` open list ([source](https://github.com/freerouting/freerouting/blob/master/src/main/java/app/freerouting/autoroute/maze/DestinationDistance.java) [P]).
- KRT: grid octilinear A*, Rust "~10× faster than pure Python" ([repo](https://github.com/drandyhaas/KiCadRoutingTools) [P]).
- PcbRouter (BSD-3, ~6.6k lines C++, reads KiCad 5.1.2): grid A*, diagonal width/clearance scaled 1/√2; each iteration routes diff pairs then signal nets; N fixed-order rip-up iterations keep the best, tracking bends ([repo](https://github.com/The-OpenROAD-Project-Attic/PcbRouter) [P]).

**Line-probe** ([RC § Q1](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/routing_classics_supplement.md))
- Hightower (DAC'69): continuous plane ("mil accuracy"; a 9×9 in board would need an 81M-cell grid), stores only segments, one escape point per segment [P-abs].
- Mikami–Tabuchi (1968): every grid point is an escape point. **Conflict**: NYCU slides say Soukup/Mikami/Hightower cannot guarantee shortest paths; a patent says Mikami–Tabuchi does (original unread) [P-slides/S].
- LibrEDA `mycelium-router` line search guarantees a shortest path if one exists [P-doc].
- Altium Situs "Straighten" walks to a corner and probes H/V/45° for a shortcut on the net [P-doc].

**Channel and switchbox**
| Algorithm | Note |
|---|---|
| Left-edge (Hashimoto–Stevens DAC'71) | Born for two-layer PCBs; "requires many via holes" |
| Dogleg (Deutsch '76) | IC |
| Net merging (Yoshimura–Kuh '82) | Optimal on 6/8 examples; 1–2.1 s for 300 terminals/70 nets on a VAX |
| Greedy (Rivest–Fiduccia '82) | Always succeeds, usually ≤1 extra track |
| Switchbox (Luk '85) | Greedy extension |
| Gridless contours (Groeneveld '90) | n-layer |
| **Single-row routing** (Tsui–Smith '81) | Necessary-and-sufficient conditions; basis of a multilayer PCB router |
| **Monotonic BGA package routing** (Tomioka–Takahashi '06) | Necessary-and-sufficient finger-to-ball conditions |

Situs "Memory" routes pins sharing X/Y on different parts; "Adjacent Memory" uses a U pattern [P-doc].

**Gridless / shape / tile**
- Corner stitching (Ousterhout '84): explicit empty-space tiles, ~3× memory; Tile-Expansion Router ('87) minimum jogs, complete [P-abs].
- **Finch et al. DAC'85**: first PCB gridless method [P-abs].
- **gEDA `autoroute.c`** (rectangle expansion after Finch; [source](https://raw.githubusercontent.com/bert/pcb/master/src/autoroute.c) [P-code]): ViaCost 3.5 in + 30× via diameter (80× smoothing); JogPenalty 4000 (20000); CongestionPenalty 1e6; NewLayerPenalty 10× ViaCost; may route over traces with pass-escalating penalties (previous-pass conflicts cheaper than current, 4×); 12 passes + smoothing; first pass ascending bbox area, later passes **easiest first** ("it will do no good to rip [the hardest] up … without first changing any of the other routes").
- **Specctra** (Cooper–Chyan 1989 → Cadence Allegro PCB Router): shape-based; pass 1 connects everything regardless of conflicts; later rip-up + push-and-shove; DSN/SES used by ELECTRA, TopoR, Freerouting (Alfons Wirtz 2004) and DeepPCB [S].
- Olney: shape-based routing time "depends only on available memory, number of objects … and connections" ([PDF](https://www.icd.com.au/articles/Autorouters_PCBD-Nov2015.pdf) [P]).
- VLSI: implicit connection graphs (Zheng '96); DUNE multilayer gridless variable width/spacing with coarse planning + rip-up (Cong '01) [P-abs].
- Freerouting: A* over convex free-space rooms connected by doors, 45° or orthogonal modes ([freerouting](freerouting.md)).

**Rip-up and reroute**
- Dees–Karger DAC'82 classic ([DOI](https://doi.org/10.1145/800263.809241)).
- Freerouting: cost = `ripupCosts × costFactor` (obstacle half-width, contacts) / detour; randomized on passes ≥4 not divisible by 3; global linear escalation (maintainers: "sub-optimal") [P].
- KRT: frontier-based blocker attribution (5000-iteration probes); modes `count`, `near-target`, `bidir`, `mincut` (rippable copper → soft cost, reroute once); diff pairs ripped/restored together ([doc](https://github.com/drandyhaas/KiCadRoutingTools/blob/main/docs/rip-up-reroute.md) [P]).
- gEDA toporouter ROAR rounds with conflict thresholds 2 and 5 + checkpoint restore ([topological](topological-routing.md)).

**Other approaches**
- tscircuit capacity-autorouter (MIT, TypeScript): "hundreds of algorithms organized in a Pipeline", successive approximation over hypergraphs on a recursively subdivided capacity mesh ([repo](https://github.com/tscircuit/tscircuit-autorouter) [P]).
- RRT-PCB (LG AI): grid route then continuous RRT refinement [S].
- Security-aware PCB routing (ISQED'26): sequence-first net prioritization, multilayer A*, RL test-point placement; 100% on evaluated boards [P-abs].
- Polygon-partition MCTS router (DATE'23) and other learned routers: [ML/RL routing](ml-rl-routing.md).
- Python building blocks: `pathfinding` 1.0.22 (MIT; A*, Dijkstra, no Theta*), rustworkx 0.18.1 (Apache-2.0), networkx 3.7 (BSD-3); no maintained Python-bound Theta*/any-angle router was verified ([solver_toolbox.md § 5](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/solver_toolbox.md) [P]).

## Recommendations for our system
- In-house router = Rust A*/PathFinder modelled on KRT (MIT) with Freerouting as baseline/fallback ([recommended stack](../solvers/recommended-stack.md)) [I].
- Add a line-probe "straighten/shortcut" cleanup pass where PNS `OptimizeSelected` is too local [I].
- Let the LLM recognize structured regions (memory pin rows, connector-to-connector buses, BGA perimeters) and dispatch channel/single-row/monotonic pattern routers [I].
- Consider PcbRouter (BSD-3, KiCad-native, DPs first) as a second classical baseline and median-point DP code reference [I].

## Conflicts and open questions
- Mikami–Tabuchi shortest-path guarantee unresolved; DTIC 1985 router comparison inaccessible; no primary description of Siemens/Zuken internals.

## Sources
- research notes: [routing_algorithms.md § Q1, Q4](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/routing_algorithms.md); [routing_classics_supplement.md § Q1](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/routing_classics_supplement.md); [solver_toolbox.md § 5](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/solver_toolbox.md)

See also: [pathfinder-negotiated-congestion](pathfinder-negotiated-congestion.md) · [topological-routing](topological-routing.md) · [net-ordering](net-ordering.md) · [autorouter-skepticism](autorouter-skepticism.md)
