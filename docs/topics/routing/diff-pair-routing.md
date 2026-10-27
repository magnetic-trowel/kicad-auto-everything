# Differential-pair routing algorithms and tool support

**TL;DR**
- Three recurring patterns: (1) **median-point / centerline routing** (route one virtual wire between P/N merge points, then offset); (2) **gateway enumeration** for coupled entry/exit (KiCad PNS); (3) **joint LP/ILP/SAT** constraints (same layer, protection zones, length match).
- Most autorouters (Altium Situs, Freerouting) still expect diff pairs routed and locked by hand; Freerouting parses DP rules but does not route pairs.
- Open implementations: KiCad PNS DP placer (GPL), KRT pose-space centerline A* with Dubins heuristic (MIT), PcbRouter median points (BSD-3).
- Recommended pipeline: median-point detection → coupled centerline plan → PNS gateway realization → skew tuning → return vias.

## Key facts

**Algorithms** [P-abs unless noted]
| Work | Method | Result |
|---|---|---|
| Fang, Ho, Chang ICCAD'08 | First chip-package-board co-design router with DPs; LP/ILP global routing with 95%/99% variable/constraint reduction "without loss of optimality"; any-angle detail | 100% routability, optimal global WL on 5 industry designs ([IEEE 4681623](https://ieeexplore.ieee.org/document/4681623/)) |
| Yan, Wu, Ma, Wong ICCAD'10 | Optimal single DP + two-stage multi-DP; characterized as negotiated-congestion DP routing ignoring length matching | — |
| **Li, Chen, Cai, Chen ASP-DAC'12** | Min-cost **median points** connecting two pins by shortest equal-length wires, then min-cost max-flow routes all pairs simultaneously | Large skew reductions ([IEEE 6164934](https://ieeexplore.ieee.org/document/6164934/)) |
| Electronics Letters 2019 | One-stage median points + paths | 100% length matching |
| J.-T. Yan Integration'15 | Length-constrained DP escape, two phases | — |
| **Wang, Wang, Dong ISPD'13** | Unified ILP for mixed single-ended + DP escape on staggered arrays: **DP protection** (no other signal near before P/N meet), length matching, non-crossing, resources, width, acute angles; slice-based pruning | ([slides](https://ispd.cc/ispd2026/slides/2013/5_wang.pdf) [P-slides]) |
| Bayless et al. ICCAD'16 | SAT escape with paired vias forced to the same layer | ([escape](escape-routing.md)) |
| **Lin, Merrill, Wu, Holtz, Cheng ASP-DAC'21** | Full-board router for complicated constraints and DPs | 100% routability, 0 DRVs, while two SOTA routers failed some cases ([DOI](https://doi.org/10.1145/3394885.3431568)); likely PcbRouter lineage (inferred) |
| Analog IC DP routing (ICICM'24) | Symmetry, EM, IR aware | Low transfer |

**Implemented tools** [P/P-code]
- **KiCad PNS DP router**: a `DP_GATEWAY` is "a pair of points (anchors) with certain orientation, spacing and (optionally) predefined entry paths"; gateways built from pads, primitive pairs, cursor and via fitting; `FitGateways` enumerates every entry × target pair (diagonal and straight), scores by gateway priority, coupled ratio and aspect ratio, rejects non-obtuse entry angles, then walks/shoves the coupled pair; DP gap pickup ratio 2.5; `TUNE_DIFF_PAIR` and `TUNE_DIFF_PAIR_SKEW` modes ([pns_diff_pair.h](https://gitlab.com/kicad/code/kicad/-/blob/master/pcbnew/router/pns_diff_pair.h)).
- **KRT**: centerline in (x, y, θ) with a Dubins heuristic, then P/N offset; pairs ripped/restored as a unit; LVDS batch 28/28 in ~29 s (10–12 M iterations) ([doc](https://github.com/drandyhaas/KiCadRoutingTools/blob/main/docs/differential-pairs.md)).
- **PcbRouter**: `GridDiffPairNet` routed before signal nets each iteration; pins paired by nearest HPWL; median (merging) points added as pseudo through-hole pins ([GridDiffPairNet.cpp](https://raw.githubusercontent.com/The-OpenROAD-Project-Attic/PcbRouter/master/src/GridDiffPairNet.cpp)).
- **Freerouting**: `DifferentialPair` record (coupled spacing, max skew) parsed, but no autoroute package references it; DeepPCB: Freerouting "doesn't natively route differential pairs as pairs" [V].
- **Altium Situs**: "Differential pairs nets must be manually routed and locked before using the autorouter" [P-doc].
- **TopoR**: arc-smoothed wires keep constant maximal gap, "important … for differential pairs" [V].
- **gEDA toporouter**: paired-net awareness (`netlist->pair`) [P-code].
- **FanoutNet MCR**: diff-pair term c3 in the A* cost [P].
- **DeepPCB**: routes diff pairs (vendor), excludes length matching/skew [V].

## Recommendations for our system
- Pipeline [I]: (1) median-point detection (pair pins, compute P/N merge points); (2) coupled centerline routing in the planner (KRT-style pose-space A*); (3) realization with KiCad's gateway DP placer from planner-chosen waypoints (the LLM supplies corridor and side-of-obstacle relations, never coordinates); (4) PNS skew tuning; (5) return/stitching vias at layer changes.
- For BGAs with many pairs, use median points + min-cost flow (Li 2012) for simultaneous DP escape; DP protection zones as constraints ([escape](escape-routing.md)) [I].
- Relation API: `pair(netP, netN, gap, max_uncoupled)`, `return_vias(pair|class)`, layer preference, via limits ([LLM routing evidence](llm-routing-evidence.md)) [I].
- Route and lock pairs before bulk routing (Situs/DeepPCB practice); PcbRouter (BSD-3) code is a median-point reference [I].

## Conflicts and open questions
- No gridless DP router with published coupled-gap guarantees during area routing (as opposed to escape) was found.
- Lin et al. ASP-DAC'21 full text not obtained; link to PcbRouter inferred.

## Sources
- research notes: [routing_classics_supplement.md § Q5](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/routing_classics_supplement.md); [routing_algorithms.md § Q2, Q4](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/routing_algorithms.md)

See also: [escape-routing](escape-routing.md) · [length-matching-and-buses](length-matching-and-buses.md) · [kicad-pns-router](kicad-pns-router.md)
