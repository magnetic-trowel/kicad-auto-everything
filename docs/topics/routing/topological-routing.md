# Topological / rubber-band routing (SURF, TopoR, gEDA toporouter, Situs)

**TL;DR**
- Topological routers first choose each wire's **homotopy class** (which side of every obstacle, which layer) as a rubber-band sketch over a constrained Delaunay triangulation, then realize geometry.
- **SURF's cut-capacity test** — a sketch is routable iff no cut's flow exceeds its capacity — is an exact, cheap feasibility oracle that names the bottleneck; sharper than RUDY.
- **For a fixed topology, octilinear costs only ~5% more length than any-angle (rectilinear 23–31%)**: gains come from topology decisions, so LLM effort belongs on topology, not angles.
- Commercial precedent: **Altium Situs = topological map → push-and-shove realization** (diff pairs pre-routed by hand). TopoR claims 15–45% fewer vias (vendor, unaudited).
- Persisting routes as topology makes placement–routing iteration cheap (re-tighten instead of re-route).

## Key facts

**SURF** (UCSC, MCM substrates; [Staepelaere thesis](https://tr.soe.ucsc.edu/sites/default/files/technical-reports/UCSC-CRL-92-39.pdf) [P])
- Phases: global routing → local routing (= topological routing) → spoke creation → geometric wiring. Wires are zero-width flexible curves; a rubber-band sketch is the canonical shortest form.
- Routability: iff no cut (segment between two points) has flow (wires crossing) above capacity; spokes yield a legal extended sketch or locate endpoints of overflowing cuts.
- Conversion: n rubber-band segments → minimum-length topologically equivalent rectilinear/octilinear wiring with m segments in **O(n log n + m)**, heuristic jog reduction.
- Wirelength by realization (Table 6.1, same topology): test5 10,763 / 14,120 (+31%) / 11,349 (+5.4%); layer0 39,820 / 51,635 (+30%) / 41,841 (+5.1%); layer1 +23% / +5.3%; phone0 +26% / +5.4%; phone1 +24% / +5.3% (any-angle / rectilinear / octilinear). Jogs on layer0: 391 rectilinear vs 322 octilinear.
- DAC'91: hierarchical top-down partitioning routes all nets simultaneously; layer assignment during partitioning; region connectivity graph ([DOI](https://doi.org/10.1145/127601.127622) [P-abs]). D&T'93: rectilinear/octilinear/all-angle, 1.5-layer routing, even wiring distribution, **incremental spoke-based DRC preserving topology as objects move** [P-abs].
- Dayan & Dai layer assignment: "defer decisions"; simultaneous global routing "does not suffer from the net ordering problem"; local routing = shortest paths over a CDT, then relocate vias/Steiner points; steepest descent on K_v·ViaCost + WiringCost ([UCSC-CRL-93-04](https://tr.soe.ucsc.edu/sites/default/files/technical-reports/UCSC-CRL-93-04.pdf) [P]).
- Claimed advantages: fewer segments, incremental modification, variable-width traces (width as a function of length for damping), easier manual editing.

**gEDA PCB toporouter** (Anthony Blake, 2008–09; GPLv2+; 7,879 lines; "EXPERIMENTAL", abandoned; [toporouter.c](https://raw.githubusercontent.com/bert/pcb/master/src/toporouter.c) [P-code])
- Per-layer CDT (GTS); A* over triangulation vertices and edge points; via cost 100 mil-equivalent; edge capacity = length, flow = summed spacing of crossing wires; paired-net awareness; arcs; `serpintine` generator.
- **Pairwise-interaction net ordering**: route each net alone, then test every other net (unaffected / detour / fail); sort by fewest fails, then smallest detour sum.
- Passes: RUBIX ordered pass, then ≤6 rounds alternating ROAR (rip-out-and-reroute, thresholds 2 and 5, checkpoint restore) with detour reduction.
- Salewski (CGAL Delaunay + Apollonius graph Ruby router) found the code hard and his prototype "crashes or generates invalid routings"; Dayan's 1997 thesis is the most detailed description (not downloaded) [P]. A KiCad adaptation claimed by Wikipedia is unverified [S].

**TopoR** (Eremex; [product page](https://www.eremex.ru/products/delta-design/topor/) [V])
- Since 1988 (FreeStyle Router → TopoR 2001 → integrated in Delta Design 3.0); no preferred directions; arcs optional; **routes 100% instantly while violating constraints, then multicriteria optimization**; even crossing counts not violations in the topological editor; components move on a routed board "preserving the topology"; parallel variant optimization; necking, teardrops, BGA strategy.
- Vendor tables: 548 nets: 1110 vs 1619 vias, 2 vs 8 layers; 1095 nets: 2832 vs 3932 vias, 73 vs 86 m; 891 nets: 1800 vs 3301 vias, 83 vs 97 m (prose example inconsistent: 42 m/1097 vias). Manual 2-week board 510 vias/6.5 m vs TopoR 1 h 432 vias/5.11 m; flex 61 → 0 vias; FPGA pin equivalence 67 → 17 vias, 5.21 → 3.79 m; arcs give ~30% larger minimum gaps than 45°.
- Luzin & Polubasov (PCD&F 2009): conventional routers lock paths into the maze; overlooked metrics = bottleneck count/length at minimum clearance, parallel run length per layer, adjacent-layer overlap; isotropic routing cuts length 25–40%; via inductance ~1.1 nH (0.4 × 1.5 mm); ~$1 per extra 300 vias/dm² above 250; ~1000 hits per drill ([PCD&F](https://pcdandf.com/pcdesign/index.php/2009-archive-articles/5203-advantages-of-isotropic-pcb-routing) [P/V]).

**Altium Situs** ([docs](https://www.altium.com/documentation/altium-designer/automated-board-layout-situs-topological-autorouter) [P-doc]): topological mapping "not dependent on obstacle shape or coordinates"; "Main" pass converts the map path with push-and-shove; "Globally Optimised Main" negotiates; passes Fan out Signal/Plane, Memory, Layer Patterns, Completion (cheaper vias, dearer wrong-way), Hug, Spread, Straighten, Recorner, Clean Pad Entries; Via Miser; layer directions incl. 1/2/4/5 o'clock and 45°; obeys all rules except Routing Corners; **"Differential pairs nets must be manually routed and locked"**.

**Homotopy theory** [P-abs]: Leiserson–Maley STOC'85 (subsumes polynomial planar routing/routability tests); Cole–Siegel FOCS'84 (detailed routing given a homotopy, O(n + m log m + D(m))); Gao et al. SoCG'88 (universal-cover sweep); **Kaufmann–Mehlhorn '94 (linear-time, complete for solvable homotopic problems)**; Hershberger–Snoeyink '94 (minimum-length paths in a homotopy class); Hsu '83 minimum-via topological routing + geometric mapping.

**Recent / other**: Samsung SDS "Circular Frame" (substrate layer → polygonal schema, routes as non-crossing chords): 1000/1000 completions at n = 2–10 vs grid A* falling to 209–220; 0.085 s vs 22–47 s at n=10 — but baselines are naive Python A* without rip-up on toy instances ([arXiv 2105.07892](https://arxiv.org/abs/2105.07892) [P]). JITX topo-routes as homotopy classes with rubber-band fallback [S]; Topola (Rust, MIT, NLnet-funded, WIP) [S]; gEDA and Numberlink "island-in-cavity" topological solvers ([cross-domain routing](cross-domain-routing-transplants.md)).

## Recommendations for our system
- Add a **topology tier (Tier 1.5)**: represent each LLM-proposed critical route/bus as a homotopy class (ordered CDT edges crossed per layer + via points), not a polyline; run the SURF cut test (flow = Σ(width + spacing) ≤ edge length) to reject/repair sketches and **name the exact bottleneck** before geometry [I].
- LLM chooses side-of-obstacle, layer per group, crossing locations, inner vs outer buses; request free-angle only on flex/single-layer boards [I].
- Persist routes as topology + vias; after placement nudges, re-tighten and re-realize (TopoR/SURF) instead of re-routing [I].
- Realize sketches with PNS walk/shove waypoints (Situs pattern) ([PNS](kicad-pns-router.md)); snap long buses with a metro-map MIP ([packing/graph-drawing](../placement/packing-and-graph-drawing-transplants.md)) [I].
- Under GPL-3.0-or-later, toporouter's GPLv2+ CDT/capacity/A* code may be studied or reused [I].

## Conflicts and open questions
- No independent benchmark of TopoR, Situs or toporouter vs maze/shape routers; TopoR page is internally inconsistent.
- No experiment shows an LLM topology plan + cut check beats Freerouting/PcbRouter alone (first ablation to run).

## Sources
- research notes: [routing_classics_supplement.md § Q2, Implications](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/routing_classics_supplement.md); [cross_domain_ideas.md § Q4](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/cross_domain_ideas.md)

See also: [algorithm-families](algorithm-families.md) · [kicad-pns-router](kicad-pns-router.md) · [net-ordering](net-ordering.md) · [cross-domain-routing-transplants](cross-domain-routing-transplants.md)
