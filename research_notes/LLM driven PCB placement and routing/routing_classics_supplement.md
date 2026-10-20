# Classical, Topological and Constrained PCB Routing: Supplement to `routing_algorithms.md`

> Research notes, current to 2026-10-20. This file fills the gaps listed in `routing_algorithms.md`. It does not repeat material already covered there: PCBWorld, Freerouting internals, KiCad PNS shove/walkaround, KiCadRoutingTools, PathFinder/OrthoRoute, tscircuit, PCBench.
>
> **How sources were read.** Full internet access was available for most of this pass. Primary sources were read through:
> - IEEE Xplore abstract records;
> - Semantic Scholar and Crossref metadata;
> - HKBU/UIUC scholar pages;
> - full PDFs (Staepelaere's SURF thesis, Dayan and Dai's layer-assignment report, Bayless et al. ICCAD'16, Unet-Astar, the Samsung substrate-topology preprint, the OmniRouting HTML, Olney's column, Luzin and Polubasov's PCD&F article, the TopoR length-tuning paper);
> - source code (gEDA PCB `toporouter.c` and `autoroute.c`; KiCad `pns_meander*.cpp` and `pns_diff_pair*.cpp`; OpenROAD PcbRouter);
> - vendor documentation (Altium Situs, Altium length tuning, Eremex TopoR, Siemens sketch routing).
>
> ACM DL and DBLP pages were blocked (HTTP 403 or bot wall). For ACM papers, abstracts came from Semantic Scholar, Crossref or HKBU.
>
> **Evidence tags** (on every bullet):
>
> | Tag | Meaning |
> |---|---|
> | **[P-full]** | Full primary text read |
> | **[P-abs]** | Primary abstract or official record read |
> | **[P-code]** | Source code read |
> | **[P-doc]** | Official documentation read |
> | **[V]** | Vendor or marketing claim, not independently verified |
> | **[S]** | Search-engine snippet or secondary summary only |
> | **[T]** | Title or metadata only |
>
> **Domain tags:** (PCB), (VLSI/IC), (MCM), (package). Evidence from VLSI does not automatically transfer to PCB.

---

## Q1. Line-probe, channel/switchbox, and gridless/shape-based/tile routing: what they are and what survives in PCB tools

### Takeaway
- **Line-probe routers** (Hightower 1969; Mikami-Tabuchi 1968) and the **channel router family** were PCB-born or PCB-era ideas:
  - Hashimoto and Stevens' left-edge router was introduced for two-layer PCBs.
  - VLSI later adopted and developed both families.
- In 2026 PCB tools they survive only as **components**:
  - line probes appear as a "Straighten" pass;
  - channel- and river-style patterns appear in "Memory" passes and BGA escape models.
- **Gridless shape/tile expansion** clearly dominates open and commercial PCB routers:
  - Specctra/Allegro (1989);
  - gEDA's rectangle-expansion router (based on Finch et al. 1985);
  - Freerouting's expansion rooms.
- Nearly every production router layers **negotiation-style conflict pricing** on top of its search: route first while ignoring conflicts, then raise penalties.

### Cited Findings

**Line-probe routing**
- Hightower (DAC 1969) describes a line router on the **continuous plane**. Its claimed advantages:
  1. no grid-precision limit ("nodes on a printed circuit board … can be input with mil accuracy"; a 9×9 in board at that precision would otherwise need an 81,000,000-cell matrix);
  2. it stores only line segments, so "only the segments that are currently defined need be investigated".
  - It was programmed in FORTRAN for the IBM 7094/360 and applied to mazes, PCBs, substrates and PERT diagrams. (PCB) [P-abs]
  - Sources: [doi:10.1145/800260.809014](https://doi.org/10.1145/800260.809014); reprint [doi:10.1145/62882.62883](https://doi.org/10.1145/62882.62883).
- Mikami and Tabuchi, "A computer program for optimal routing of printed circuit connectors" (IFIP 1968): **every grid point is an escape point**. In Hightower's algorithm, by contrast, there is **a single escape point per line segment**, placed "just past the endpoint" when a line parallels blocked cells. Per the same slides, Soukup, Mikami and Hightower "cannot guarantee shortest paths". — [NYCU EDA lecture 6 (Jiang), 2026](https://tiger.iee.nycu.edu.tw/course/EDAIntro2026Spring/materials/lec6.pdf) [P-full slides]
  - **Conflict:** a US patent states that Mikami-Tabuchi "assures that the path found is the shortest path", with O(L) time and space in the number of line segments. The original 1968 paper could not be obtained to resolve this. — [US 7137097 (snippet)](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/7137097) [S]
- LibrEDA notes that line-probing "does not necessarily need a grid". Its own experimental `mycelium-router` uses a line-search that does guarantee a shortest path if one exists. (VLSI) — [LibrEDA book §11.4](https://libreda.codeberg.page/book/pnr/line_probe_routing.html) [P-doc]
- Soukup's "Fast Maze Router" combines the two styles. A line search heads toward the target; on hitting an obstacle, Lee-style expansion "bubbles" around it before the line search resumes. It is "10–50 times faster than the Lee algorithm on typical two-layer boards" and still guarantees a connection if one exists, but routes are "suboptimal when the area becomes congested". (PCB) — [Soukup, Fast Maze Router (PDF)](https://janders.eecg.utoronto.ca/1387/readings/soukup.pdf) [P-full]
- **Survival in commercial PCB tools.** Altium's Situs "Straighten" pass is literally a line probe: it "walk[s] along the route to a corner, then from that corner performs a (horizontal/vertical/45up/45down) probe searching for another routed point on the net" and keeps the shortcut if it reduces length. (PCB) — [Altium Situs docs](https://www.altium.com/documentation/altium-designer/automated-board-layout-situs-topological-autorouter) [P-doc]

**Channel and switchbox routers**
- **Left-edge.** Hashimoto and Stevens (DAC 1971) introduced channel-assignment routing "for two layer printed circuit boards"; the method "requires many via holes". (PCB) — [doi:10.1145/800158.805069](https://doi.org/10.1145/800158.805069) [P-abs/TLDR]
- **Dogleg.** Deutsch's "Dogleg" channel router (DAC 1976) was developed for the LTX IC layout system. (IC) — [doi:10.1145/800146.804843](https://doi.org/10.1145/800146.804843) [P-abs/TLDR]
- **Merging.** Yoshimura and Kuh (TCAD 1982) "merge nets instead of assigning horizontal tracks to individual nets". They produced optimal solutions in 6 of 8 published examples, taking 1.0–2.1 s for a 300-terminal, 70-net channel on a VAX 11/780. (IC) — [IEEE 1269993](https://ieeexplore.ieee.org/document/1269993/) [P-abs]
- **Greedy.** Rivest and Fiduccia's greedy channel router (DAC 1982) works column by column. It "always succeeds, usually using no more than one track more than required by channel density", may place a net on several tracks and later collapse it with a jog, and may add tracks or go "off the end". (IC) — [IEEE 1585533](https://ieeexplore.ieee.org/document/1585533/) [P-abs]
- **Switchbox.** Luk (1985) extended the greedy channel router into a switchbox router. (IC) — [doi:10.1016/0167-9260(85)90029-x](https://doi.org/10.1016/0167-9260(85)90029-x) [P-abs/TLDR]
- **Gridless contour-based.** Groeneveld's n-layer gridless channel router (TCAD 1990) uses contours. (IC) — [doi:10.1109/43.62773](https://doi.org/10.1109/43.62773) [P-abs/TLDR]
- **PCB-specific channel-like model.** Single-row routing (Tsui and Smith, DAC 1981) gives necessary and sufficient conditions for routing two-point nets in a single row without vias, as the basis of a "high-density multilayer PCB router". (PCB) — [IEEE 1585384](https://ieeexplore.ieee.org/document/1585384/) [P-abs]
- **BGA package analogue.** Monotonic routing in BGA packages (Tomioka and Takahashi, ASP-DAC 2006) gives necessary and sufficient conditions for monotonic finger-to-ball routes. (package) — [IEEE 1594758](https://ieeexplore.ieee.org/document/1594758/) [P-abs]
- **Modern survival.** Situs's "Memory" pass routes pins on different components that "share X or Y coordinates" (pattern routing for aligned memory pins). "Adjacent Memory" routes adjacent same-net pins with a "simple U pattern". (PCB) — [Altium Situs docs](https://www.altium.com/documentation/altium-designer/automated-board-layout-situs-topological-autorouter) [P-doc]

**Gridless, shape-based and tile-based routing**
- **Corner stitching** (Ousterhout, TCAD 1984) represents empty space explicitly as rectangular tiles "stitched together at their corners". It gives linear or constant expected-time search, creation, deletion, stretching and compaction, at about 3× the memory of the simplest representation. (IC) — [IEEE 1270061](https://ieeexplore.ieee.org/document/1270061/) [P-abs]
- **Tile expansion.** Margarino et al.'s Tile-Expansion Router (TCAD 1987) is built on corner stitching. It finds connections "with a minimum number of jogs" and "ensures that a possible solution will be found", on two Manhattan layers. (IC) — [IEEE 1270299](https://ieeexplore.ieee.org/document/1270299/) [P-abs]
- **First PCB gridless method.** Finch, Mackenzie, Balsdon and Symonds, "A Method for Gridless Routing of Printed Circuit Boards" (DAC 1985), was motivated by fine-line PCB technology that "stretched most previous automatic routing algorithms to the limit". (PCB) — [IEEE 1585990](https://ieeexplore.ieee.org/document/1585990/) [P-abs]
- **gEDA PCB autorouter** (`autoroute.c`, C. Scott Ananian 2001, harry eaton 2006/2009): "implements a rectangle-expansion router, based on [Finch et al. 1985]". "Expansion areas can grow from corners and in all directions at once." (PCB) [P-code]
  - **Cost model:** `ViaCost` = 3.5 in + 30× via diameter (80× in smoothing passes); `JogPenalty` = 4000 (20000 smoothing); `CongestionPenalty` = 1e6; `NewLayerPenalty` = 10× ViaCost.
  - **Conflict pricing:** a pass may route *over other traces*, with penalties that rise with the pass number. Conflicts with traces laid in the previous pass are cheaper (`LastConflictPenalty`) than those in the current pass (`ConflictPenalty` = 4×).
  - **Schedule:** 12 passes plus smoothing passes. The first pass routes nets in ascending bounding-box area. Each later pass routes "easiest nets from this pass first on next pass", because "the hardest is the last one routed … it will do no good to rip it up and try it again without first changing any of the other routes".
  - Source: [gEDA pcb autoroute.c (mirror)](https://raw.githubusercontent.com/bert/pcb/master/src/autoroute.c)
- **Specctra** (Cooper and Chyan, 1989; Cadence 1997; now Allegro PCB Router) is a "shape-based" router. (PCB) [S/secondary]
  - Its first pass connects everything "regardless of the presence of conflicts". Later passes reduce conflicts by rip-up-and-retry and push-and-shove.
  - DSN/SES are also used by ELECTRA, TopoR, Alfons Wirtz's FreeRouting (2004, GitHub 2014) and DeepPCB. This answers the Freerouting-authorship gap in the earlier notes.
  - Source: [Wikipedia: Specctra](https://en.wikipedia.org/wiki/Specctra)
- Barry Olney summarizes the router types:
  - Maze and line-search routers use a grid. A gridless router "uses a workspace with available polygon areas". A shape-based router represents entities as polygons with no grid, so "routing time depends only on the available memory, the number of objects … and … connections".
  - Specctra was "probably the most popular shape-based router, 20 years ago". Intergraph/VeriBest technology became Mentor Xpedition/PADS routing.
  - (PCB) — [Olney, "Why Autorouters Don't Work: The Mindset!", PCB Design 2015](https://www.icd.com.au/articles/Autorouters_PCBD-Nov2015.pdf) [P-full]
- **VLSI gridless lineage, for reference only:**
  - Zheng, Lim and Iyengar's implicit connection graphs (TCAD 1996) build only the searched part of a sparse connection graph on the fly. — [IEEE 486276](https://ieeexplore.ieee.org/document/486276/) [P-abs]
  - DUNE (Cong, Fang and Khoo, TCAD 2001) is a multilayer gridless variable-width/variable-spacing router. It uses an implicit non-uniform grid graph proved to contain a minimum-cost gridless connection, plus coarse-grid wire planning and rip-up. — [IEEE 920694](https://ieeexplore.ieee.org/document/920694/) [P-abs]

### Inferences
- The three dominant PCB router families are all **free-space-decomposition routers with negotiated conflict pricing**:
  - Freerouting's rooms;
  - gEDA's expanding rectangles;
  - Specctra's shapes.

  Line probes and channel algorithms survive as *passes or patterns*, not as the main engine.
- Line probes are cheap "straighten/shortcut" post-passes. They are worth adding to a KiCad cleanup stage where PNS `OptimizeSelected` is unavailable or too local.
- Channel-style reasoning (single-row, monotonic, left-edge track assignment) is directly useful for **structured regions**: connector-to-connector buses, memory pin rows, BGA perimeters. An LLM can recognize these and dispatch a specialized pattern router.

### Gaps
- The original Mikami-Tabuchi (IFIP 1968) paper was not accessible, so the shortest-path conflict above is unresolved.
- No primary description of Mentor/Siemens or Zuken router internals was found.
- A DTIC 1985 PCB-router comparison (grid-expansion vs channel vs "linear expansion") appeared in search but returned HTTP 403. — [ADA155600](https://apps.dtic.mil/sti/pdfs/ADA155600.pdf)

---

## Q2. Topological / rubber-band routing (SURF, TopoR, gEDA toporouter, homotopy): principles, advantages, limitations

### Takeaway
Topological routers work in two stages:
1. Decide each wire's **homotopy class**: which side of every obstacle and wire it passes, and on which layer. The usual representation is a rubber-band sketch over a constrained Delaunay triangulation, checked for routability by cut capacity.
2. Realize the geometry: spokes for spacing, then conversion to any-angle, octilinear or rectilinear wiring.

**What the evidence shows:**
- **Primary MCM data (SURF):** for a *fixed* topology, octilinear realization costs only **~5%** more wirelength than any-angle, and rectilinear costs **23–31%** more.
- **Vendor data (TopoR):** 15–45% fewer vias and 13–21% shorter wiring than unnamed competitors. These figures are unaudited.
- **Commercial adoption:** Altium Situs uses the "topological map → push-and-shove realization" architecture, so the pattern is in commercial use.

**Limitations:**
- Tool-format incompatibility with arcs and any-angle wiring.
- Complexity: gEDA's toporouter stayed "EXPERIMENTAL" and was abandoned.
- Weak independent benchmarking.

### Cited Findings

**SURF (UC Santa Cruz)**
- **Pipeline.** SURF is "an area router designed primarily for routing multi-chip module (MCM) substrates". Its phases are global routing → local routing (together the *topological routing*) → spoke creation → geometric wiring. (MCM) — [Staepelaere MS thesis, UCSC 1992](https://tr.soe.ucsc.edu/sites/default/files/technical-reports/UCSC-CRL-92-39.pdf) [P-full]
- **Topological model.** Wires are "zero-width flexible curves with fixed endpoints" that can be deformed without crossing. A *rubber-band sketch* is the canonical shortest form of a topology. [P-full, same thesis]
- **Routability test.** A sketch is routable "if and only if no cut has a flow that exceeds its capacity" (cut = segment between two points; flow = number of wires crossing). Spoke creation either produces a legal "extended rubber-band sketch" or "locate[s] all of the endpoints that participate in overflowing cuts". [P-full]
- **Claimed advantages:**
  - fewer segments;
  - incremental modification;
  - variable-width traces, including width as a function of length for damping;
  - an easier manual-editing model.

  [P-full]
- **Geometric conversion.** A sketch with n rubber-band segments converts to minimum-length topologically equivalent rectilinear or octilinear wiring with m segments in **O(n log n + m)**, with heuristic jog reduction. [P-full]
- **Wirelength by realization (Table 6.1, same topology).** Ratios are computed from the thesis table. [P-full]

  | Example | Any-angle (Euclidean) | Rectilinear | Octilinear |
  |---|---|---|---|
  | test5 | 10,763 | 14,120 (+31%) | 11,349 (+5.4%) |
  | layer0 | 39,820 | 51,635 (+30%) | 41,841 (+5.1%) |
  | layer1 | 29,187 | 35,864 (+23%) | 30,734 (+5.3%) |
  | phone0 (analog MCM) | 236,458 | 297,341 (+26%) | 249,255 (+5.4%) |
  | phone1 (analog MCM) | 224,804 | 279,077 (+24%) | 236,613 (+5.3%) |

  Final jogs on layer0: 391 rectilinear vs 322 octilinear.
- **DAC'91 paper.** Dai, Dayan and Staepelaere describe a multi-layer topological router that does "hierarchical top-down partitioning to perform global routing for all nets simultaneously". It uses successive refinement, layer assignment during partitioning "to generate routing that has fewer vias and is not restricted to one-layer one-direction", and a "region connectivity graph" for shortest-path rubber-band local routing. (MCM) — [doi:10.1145/127601.127622](https://doi.org/10.1145/127601.127622) [P-abs]
- **IEEE D&T 1993 summary.** SURF supports "rectilinear, octilinear, and all-angle wiring patterns", "one-and-a-half-layer routing", "even wiring distribution", and incremental spoke-based DRC: as objects move or wires are resized, "wires are adjusted incrementally so that they maintain the same wiring topology". (MCM) — [IEEE 245960](https://ieeexplore.ieee.org/document/245960/) [P-abs]
- **Layer assignment and its design philosophy** (Dayan and Dai, UCSC-CRL-93-04). (MCM) — [UCSC-CRL-93-04](https://tr.soe.ucsc.edu/sites/default/files/technical-reports/UCSC-CRL-93-04.pdf) [P-full]
  - SURF follows "decision should be deferred as much as possible".
  - Global routing "analyzes all the nets 'simultaneously' and as a result … does not suffer from the net ordering problem".
  - Local routing represents rubber bands "as paths over a constrained Delaunay triangulation" and routes nets one at a time by shortest path. It then optimizes by "relocating vias and Steiner points".
  - Layer assignment uses steepest descent on Cost = K_v·ViaCost + WiringCost, so a user-set K_v trades vias against length.

**gEDA PCB "toporouter"** (Anthony Blake, Google-funded, 2008–2009, mentored by DJ Delorie)
- **Basis.** The source header lists its basis: Dayan and Dai's layer assignment (UCSC-CRL-92-50), SURF DAC'91, SURF D&T'93, Dayan's 1997 PhD thesis "Rubber-band based topological router", and Staepelaere's thesis. It warns "This is *EXPERIMENTAL* code". GPLv2+, 7,879 lines in the mirror read. (PCB) — [toporouter.c (mirror)](https://raw.githubusercontent.com/bert/pcb/master/src/toporouter.c) [P-code]
- **Mechanics** (same file). [P-code]
  - Per-layer constrained Delaunay triangulation via the GTS library.
  - A* (`route()`) over triangulation vertices and temporary points on edges, with layer change costed as `viacost` (default 100 mil of equivalent length).
  - Edge capacity = edge length; edge flow = summed spacing of wires already crossing.
  - The router knows about paired nets (`netlist->pair`).
  - Output as lines plus **arcs**, with a `serpintine` generator present.
- **Net ordering by pairwise interaction** (`order_nets_preroute_greedy`). [P-code]
  - Each net is routed alone. With it in place, every other net is routed to see if it is unaffected, detours, or fails.
  - Nets are sorted by fewest `pairwise_fails`, then smallest `pairwise_detour_sum`.
- **Router passes** (`hybrid_router`). [P-code]
  - The "RUBIX" ordered pass runs first.
  - Then up to 6 rounds alternate "ROAR" (rip-out-and-reroute) with conflict thresholds 2 and 5 and a detour-reduction router. ROAR rips conflicting routes, re-routes them, and restores checkpoints if more than *threshold* re-routes fail.
- **Status and claims.** Wikipedia: mostly based on Dayan's 1997 thesis; "adapted for use with the open-source KiCad project as well". The KiCad adaptation was *not* verified. (PCB) — [Wikipedia: PCB (software)](https://en.wikipedia.org/wiki/PCB_(software)) [S]
- **Practitioner experience.** Stefan Salewski, who later wrote a Ruby rubber-band router on CGAL (Delaunay plus Apollonius graph), found the toporouter's "about 8k lines of C code" hard to grasp and noted "the initial author has retired". He considered Dayan's thesis "the most detailed description" of rubber-band sketch generation. His own prototype "crashes or generates invalid routings" for some inputs. (PCB) — [Salewski, PCB Routing (Draft)](https://ssalewski.de/Router.html.en) [P-full]

**TopoR (Eremex)**
- **History and positioning:**
  - Work on a flexible topological router began in 1988, became the DOS "FreeStyle Router" (Dial Engineering, P-CAD interface), then Windows TopoR from 2001.
  - Characteristics: no preferred routing directions; wires with or without arcs; it "routes all connections, even if this entails violating design constraints", with violations corrected later.
  - It also features: automatic wire reshaping when components or vias move; parallel optimization of several layout variants, discarding the worst by length and via count; trace necking; teardrops; a BGA strategy; a single-layer mode.
  - (PCB) — [Wikipedia: TopoR](https://en.wikipedia.org/wiki/TopoR) [S]
- **Current product page** (Russian). (PCB) — [Eremex: Delta Design TopoR](https://www.eremex.ru/products/delta-design/topor/) [P-doc/V]
  - Since Delta Design 3.0, TopoR is "fully integrated into the PCB editor and is one of two routing modes".
  - It routes 100% of connections "practically instantly", violating constraints if necessary, then runs "multicriteria optimization".
  - In the topological editor, touching or an *even* number of crossings between two wires is not a violation; wires "tighten and move apart" when the mode is switched.
  - Components can be moved on a routed board "preserving the topology".
- **Vendor comparison table** (same technology rules; competitors unnamed). [V]

  | Test | Nets / comps / pins | Vias (TopoR vs other) | Layers | Length |
  |---|---|---|---|---|
  | 1 | 548 / 253 / 2588 | 1110 vs 1619 | 2 vs 8 | 47 m vs 48 m |
  | 2 | 1095 / 1131 / 5708 | 2832 vs 3932 | 4 vs 4 | 73 m vs 86 m |
  | 3 | 891 / 571 / 5050 | 1800 vs 3301 | 4 vs 4 | 83 m vs 97 m |

  - Test 2's competitor is a "first-class shape-based router".
  - The same page's prose example for the 2-vs-8-layer board says **42 m / 1097 vias**, inconsistent with Test 1's 47 m / 1110.
- **Other vendor examples** (same page). [V]
  - Manual 2-week board: 510 vias, 6.5 m. TopoR in 1 h (20 min auto + 40 min edit): 432 vias, 5.11 m.
  - Flex board: shape-based 346 in / 61 vias vs TopoR 322 in / 0 vias.
  - Single-layer board: shape-based routed 56.3% vs TopoR complete in <1 s.
  - FPGA with pin equivalence enabled: 67 → 17 vias, 5.21 → 3.79 m.
  - Arc-smoothed wires give uniform maximal clearance. With 45° routing, gaps "are uneven and their minimum is about 30% smaller".
- **Eremex authors' own argument** (Luzin and Polubasov, PCD&F 2009). (PCB) — [Luzin & Polubasov, "Advantages of Isotropic PCB Routing", PCD&F 2009](https://pcdandf.com/pcdesign/index.php/2009-archive-articles/5203-advantages-of-isotropic-pcb-routing) [P-full/V]
  - Conventional routers lock each laid path into the maze, so "routes are often excessively long … the number of vias increases". Later improvements are applied "to the single topology variant … refinement possibilities … are quite modest".
  - Overlooked quality indicators: "the number of bottlenecks with minimal clearance and their length, the length of parallel paths on each layer, and the conductor overlap area on adjacent layers".
  - Isotropic routing "can help reduce the total wire length by 25% to 40%, while reducing the number of vias".
  - Cost and EMI context they give: via inductance ~1.1 nH (0.4 mm × 1.5 mm); about $1 per extra 300 vias/dm² above 250; a drill lasts ~1000 hits; 2.5–3 min of extra drilling per 1000 holes per stack.
- **TopoR length tuning** (Lysenko and Polubasov 2009, CC-BY). (PCB) — [TKEA 2009 no.4 (abstract page)](https://www.tkea.com.ua/index.php/journal/article/view/TKEA2009.4.03); [PDF](https://www.tkea.com.ua/index.php/journal/article/download/TKEA2009.4.03/588/) [P-full]
  - Arc-based serpentines are inscribed in a user-adjustable **arbitrary trapezoid**, with target length held "with a maximum tolerance of 50 nm".
  - It contrasts this with Specctra's rectangular "accordion" and "trombone". Meander pitch is "usually not less than 3w".
  - Straight-line approximations are used for CAD formats without arcs.

**Altium Situs**
- Situs "uses advanced topological mapping first to define the routing path, then calls on a variety of proven routing algorithms to convert this 'human-like' path to a high-quality route". (PCB) — [Altium Situs docs](https://www.altium.com/documentation/altium-designer/automated-board-layout-situs-topological-autorouter) [P-doc]
  - Its topological mapping is "not dependent on obstacle shape or coordinates".
  - The "Main" pass "uses the topological map to find a routing path, then uses the push and shove router to convert the proposed path to actual routing".
  - "Globally Optimised Main" "ignores contentions/violations on its first iteration. It then reroutes connections, with increased conflict costs, until there are no violations remaining" (negotiated congestion).
  - Other passes: Fan out Signal/Plane, Memory, Layer Patterns (routes only connections aligned with a layer direction), Completion (cheaper vias, dearer wrong-way), Hug, Spread, Straighten, Recorner, Clean Pad Entries. Strategies include "Via Miser".
  - Layer directions include 1/2/4/5 o'clock and 45°.
  - "Differential pairs nets must be manually routed and locked before using the autorouter."

**Homotopic routing theory** (VLSI/computational geometry; establishes that rubber bands are shortest paths within a homotopy class)
- **Leiserson and Maley (STOC 1985):** algorithms for routing and routability testing of planar layouts that "subsume most of the polynomial-time algorithms … for planar routing and routability testing in the rectilinear grid model". — [doi:10.1145/22145.22153](https://doi.org/10.1145/22145.22153) [P-abs/TLDR]
- **Cole and Siegel (FOCS 1984):** "Detailed Routing given a Homotopy" in O(n + m log m + D(m)). — [doi:10.1109/sfcs.1984.715902](https://doi.org/10.1109/sfcs.1984.715902) [P-abs/TLDR]
- **Gao, Jerrum, Kaufmann, Mehlhorn et al. (SoCG 1988):** continuous homotopic one-layer routing via a sweep in the universal cover. — [doi:10.1145/73393.73433](https://doi.org/10.1145/73393.73433) [P-abs/TLDR]
- **Kaufmann and Mehlhorn (SIAM J. Comput. 1994):** linear-time homotopic routing in grid graphs that "guarantees to find a solution for any solvable homotopic routing problem". — [doi:10.1137/s0097539789162109](https://doi.org/10.1137/s0097539789162109) [P-abs]
- **Hershberger and Snoeyink (CGTA 1994):** minimum-length paths of a given homotopy class via the universal cover. — [doi:10.1016/0925-7721(94)90010-8](https://doi.org/10.1016/0925-7721(94)90010-8) [P-abs/TLDR]
- **Early two-step topological routing for PCB/IC.** Hsu, "Minimum-Via Topological Routing" (TCAD 1983), proposes "topological routing and geometrical mapping". (IC, two-layer) — [IEEE 1270041](https://ieeexplore.ieee.org/document/1270041/) [P-abs]

**Recent topological work (package substrates)**
- Samsung SDS (Seong, Yang, Han, arXiv 2021, preprint) maps a substrate layer to a "Circular Frame" (a polygonal schema) and routes as non-crossing chords. (package) — [arXiv:2105.07892](https://arxiv.org/abs/2105.07892) [P-full]
  - **Results.** Completion over 1000 random instances per size, n = 2–10 nets:
    - Circular Frame: 1000/1000 at every n.
    - Grid A* (4-neighbour): 1000 → 209.
    - Grid A* (8-neighbour): 934 → 220.
    - Mean time at n = 10: 0.085 s vs 22–47 s.
  - **Caveat:** the baselines are naive sequential A* in Python without rip-up, on single-layer toy instances.

### Inferences
- **Where topological routers' gains come from.** The SURF numbers isolate geometry from topology: for a fixed topology, octilinear vs any-angle is worth only ~5% length. TopoR-style claims of 15–40% must therefore come mainly from **topology decisions** (side-of-obstacle choices, crossing and layer assignment, global simultaneity) and from **post-move re-tightening**, not from curved wires per se.

  KiCad PNS already produces good octilinear geometry. An LLM-driven router should put its intelligence into topology, not angle freedom.
- **Cut capacity as a feasibility oracle.** The SURF cut-capacity condition is an exact, cheap planar routability test for a single-layer sketch. It is a principled feasibility check for LLM-proposed corridors or sketches, sharper than tile overflow (RUDY): it identifies the specific overflowing cut and endpoints.
- **Commercial precedent.** Situs "topological map → push-and-shove" is precisely the "sketch then PNS realization" architecture the earlier notes proposed. This is evidence the pattern works commercially. Situs's own docs also show its limit: diff pairs must be pre-routed by hand.

### Gaps
- No independent, controlled benchmark of TopoR, Situs or the toporouter against maze/shape routers on public boards was found. All TopoR numbers are vendor figures, and the TopoR page contains internal inconsistencies.
- Dayan's 1997 PhD thesis could not be downloaded (archive link failed). Details of its region-split algorithm were read only second-hand.
- No evidence was found of whether KiCad ever merged a toporouter port.

---

## Q3. BGA/escape routing: network-flow, ILP/SAT formulations, ordered/simultaneous/differential/pin-swap-aware escape

### Takeaway
- **Escape routing is the most mathematically "closed" PCB sub-problem.**
  - Single-layer escape reduces exactly to network flow, provided diagonal capacity is modeled correctly (Yan and Wong 2009).
  - Ordered escape needs multi-commodity flow or SAT.
  - Multi-layer escape with via placement needs SAT plus flow (MonoSAT). This approach proved minimal layer counts for real 2000-pin FPGAs in minutes to about an hour.
- **Industrial evidence:** academic escape routers repeatedly matched or beat Cadence Allegro on industrial cases (B-escape; NCER; Lin et al. 2021).
- **Joint optimization:** pin assignment, bus sequencing and diff-pair pairing can be optimized jointly with escape in polynomial time for important cases.

### Cited Findings

**Simultaneous escape routing (SER) and layer assignment (Ozdal and Wong line)**
- Ozdal and Wong (ICCAD 2004 → TCAD 2006) separate "routing under dense components from routing in the intermediate area". (PCB) — [IEEE 1637740](https://ieeexplore.ieee.org/document/1637740/); [ICCAD'04](https://doi.org/10.1109/iccad.2004.1382689) [P-abs]
  - SER for multiple components minimizes crossings in the intermediate area, modeled as "longest path with forbidden pairs".
  - An exact polynomial algorithm finds the maximal planar solution on one layer, plus a randomized scalable variant.
  - Layer assignment takes "the maximal subset of planar nets [for] each layer", with leftovers distributed at the end.
- Ozdal, Wong and Honsinger (ICCAD 2005) add high-speed constraints and "reduce the via requirements of industrial test cases on average by 39%" vs the 2004 algorithm. (PCB) — [IEEE 1560166](https://ieeexplore.ieee.org/document/1560166/) [P-abs]

**Bus-aware escape**
- **Bus sequencing.** Kong, Yan, Wong and Ozdal (ICCAD 2007) note that net-centric escape "will result in mixing nets of different buses". They define bus sequencing as a longest common interval sequence problem, solved optimally in O(n log n), which is also a lower bound. They state that "no commercial CAD software can provide an automatic solution for high-end boards". (PCB) — [IEEE 4397296](https://ieeexplore.ieee.org/document/4397296/) [P-abs]
- **Minimum layers.** Yan, Kong and Wong (ICCAD 2009) find the minimum number of layers for bus escape. The earlier max-subset-per-layer method was only a heuristic. (PCB) — [HKBU record](https://scholars.hkbu.edu.hk/en/publications/optimal-layer-assignment-for-escape-routing-of-buses/) [P-abs]
- **Consecutive layers.** Ma, Young and Wong (DAC 2011) solve it optimally by branch-and-bound, including buses "required to be assigned on consecutive layers". (PCB) — [HKBU record](https://scholars.hkbu.edu.hk/en/publications/an-optimal-algorithm-for-layer-assignment-of-bus-escape-routing-o/) [P-abs]
- **Pin-assignment-aware escape.** Kong, Yan and Wong (ASP-DAC 2010) show "simultaneous pin assignment and escape routing can be solved optimally in polynomial time". On an industrial board with 80 buses (>7000 nets), all 80 were solved in <5 CPU minutes. They note that prior pin assignment used "simple (heuristic) metrics … no guarantee". (PCB) — [IEEE 5419881](https://ieeexplore.ieee.org/document/5419881/) [P-abs]

**Exact models: ordered escape and correct flow**
- **SAT ordered escape.** Luo and Wong (ASP-DAC 2008): existing approaches "cannot guarantee to find a routing solution even if one exists"; their SAT formulation solves OER exactly. Luo and Wong (ASP-DAC 2009) fix a "major deficiency" of that formulation and scale it to large problems. (PCB) — [IEEE 4483950](https://ieeexplore.ieee.org/document/4483950/); [HKBU record (2009)](https://scholars.hkbu.edu.hk/en/publications/on-using-sat-to-ordered-escape-problems/) [P-abs]
- **Correct flow.** Yan and Wong (DAC 2009; TCAD 2012): "none of the previous works correctly models the diagonal capacity, which is essential for 45° routing". Prior algorithms could therefore produce illegal routings or miss legal ones. Their model gives "the first optimal algorithm for escape routing" and handles missing pins. (PCB/package) — [HKBU record](https://scholars.hkbu.edu.hk/en/publications/a-correct-network-flow-model-for-escape-routing/); [TCAD 2012](https://doi.org/10.1109/TCAD.2011.2169258) [P-abs]
- **Staggered pin arrays:**
  - Ho, Lee and Chang (ICCAD 2011) use an LP/ILP "orthogonal-side wiring style". — [IEEE 6105346](https://ieeexplore.ieee.org/document/6105346/) [P-abs]
  - Wu and Wong (ASP-DAC 2013) give flow models "guaranteed to find an escape routing satisfying the capacity constraints if there exists one". — [IEEE 6509595](https://ieeexplore.ieee.org/document/6509595/) [P-abs]
  - (PCB)
- **Ordered escape via multi-commodity flow:**
  - Jiao and Dong (ASP-DAC 2016): min-cost multi-commodity flow with non-crossing, ordering and capacity transformations; 100% routability on their tests. — [IEEE 7428042](https://ieeexplore.ieee.org/document/7428042/) [P-abs]
  - Multi-capacity extension (ISQED 2023): up to 308 pins. — [ISQED'23 abstract](https://isqed.org/English/Archives/2023/Technical_Sessions/103.html) [P-abs]
  - MCMCF-Router (Gao, Dong, Tang, Yu, TODAES 2024): up to 525 pins, 100% routability in <810 s. — [doi:10.1145/3695253](https://doi.org/10.1145/3695253) [P-abs]
  - (PCB) These confirm the earlier notes' secondary "MCMCF-Router" mention, but the claimed scale is **525 pins**, not "2000+".
- **Mobility-based ordering.** Sattar and Ignjatovic (2016/2017): an LP network-flow SER that solves net ordering and escape together. (PCB) — [doi:10.22452/mjcs.vol29no2.2](https://doi.org/10.22452/mjcs.vol29no2.2) [P-abs]

**Multi-layer escape with SAT**
- Bayless, Hoos and Hu, "Scalable, High-Quality, SAT-Based Multi-Layer Escape Routing" (ICCAD 2016). (PCB) — [PDF (UBC)](https://www.cs.ubc.ca/labs/isd/Projects/monosat/monosat_bga_iccad2016.pdf); [doi:10.1145/2966986.2967072](https://doi.org/10.1145/2966986.2967072) [P-full]
  - **Why SAT:** multi-layer escape "cannot be modelled as a pure network flow problem". Most practice "rel[ies] on a greedy, layer-by-layer approach".
  - **Formulation:** MonoSAT (SAT modulo monotonic theories with flow constraints) places traces *and* vias simultaneously. It supports 45°/90° and through, blind, buried and any-layer micro-vias, and interoperates with partial solutions.
  - **Results with blind vias (Table 1):**
    - TI AM5716 (28×28, 382 signals): 3 layers greedy vs **2, proven minimal**.
    - TI TMS320C: 4 vs 3.
    - Xilinx XCVU440 (54×54, 1755 signals): 4 vs **3, proven minimal**, in 1597 s + 2727 s.
  - **Results with through-hole vias (Table 2):** TMS320C and AM52E02 need 5 layers greedy vs 3.
  - **Costs and extras:** average trace length is slightly longer (e.g., 21.6 vs 20.0 mm). Differential pairs are supported by forcing both signals of a pair onto the same layer.
- **MonoSAT licence.** MIT, but it links GPLv2 code by default; building with `-DGPL=OFF` keeps it MIT. — [MonoSAT README](https://raw.githubusercontent.com/sambayless/monosat/master/README.md) [P-doc]

**Negotiated and boundary-based escape vs commercial tools**
- **NCER.** Ma, Yan and Wong (ISQED 2010) built a negotiated-congestion escape router and compared it with Allegro on 14 industrial cases. Each tool completely routed 7, and together they routed 11, with "complementary behaviors". (PCB) — [IEEE 5450514](https://ieeexplore.ieee.org/document/5450514/) [P-abs]
- **B-escape.** Luo, Yan, Ma, Wong and Shibuya (ISPD 2010), boundary routing: solved all industrial escape problems, while "Cadence Allegro PCB router was only able to complete … half". (PCB) — [doi:10.1145/1735023.1735033](https://doi.org/10.1145/1735023.1735033) [P-abs/TLDR]
- **Multiple components.** Chin and Chen (EDAPS 2013) handle SER on multiple components when "two or more busses are connected to the same component". (PCB) — [IEEE 6724408](https://ieeexplore.ieee.org/document/6724408/) [P-abs]
- **Full flow.** Lin, Wang, Kuo, Chen and Li (DAC 2021), "complete PCB routing methodology": SER that does layer assignment and escape order, then post-SER refinement, then gridless area routing, with length matching and diff pairs "satisfied in each stage". It "can complete routings for seven commercial PCB designs, whereas the commercial PCB tool cannot complete any of them". (PCB) — [doi:10.1109/DAC18074.2021.9586143](https://doi.org/10.1109/DAC18074.2021.9586143) [P-abs]

**Differential pairs in escape** (see also Q5)
- **Yan, Wu, Ma and Wong (ICCAD 2010):** optimal routing of a single DP, plus simultaneous multi-DP routing in a two-stage scheme. — [IEEE 5654214](https://ieeexplore.ieee.org/document/5654214/) [P-abs] An ISPD 2013 talk characterizes it as a "negotiated congestion-based differential-pair routing" that ignores length matching. — [Wang, Wang, Dong ISPD'13 slides](https://ispd.cc/ispd2026/slides/2013/5_wang.pdf) [P-full slides]
- **Li, Chen, Cai and Chen (ASP-DAC 2012):** first find "min-cost median points which connect two pins by shortest and equal wire lengths", then run min-cost max-flow to route all pairs simultaneously, with large skew reductions. — [IEEE 6164934](https://ieeexplore.ieee.org/document/6164934/) [P-abs]
- **Electronics Letters 2019:** one-stage optimization of median points and paths, with "100% length-matching results". — [doi:10.1049/el.2019.0522](https://doi.org/10.1049/el.2019.0522) [P-abs]
- **J.-T. Yan (Integration 2015):** length-constrained DP escape, two-phase. — [doi:10.1016/j.vlsi.2014.07.006](https://doi.org/10.1016/j.vlsi.2014.07.006) [P-abs/TLDR]
- **Wang, Wang and Dong (ISPD 2013):** a unified ILP for mixed single-ended and DP escape on staggered arrays, with constraints for "differential-pair protection" (no other signal near before P/N meet), length matching, non-crossing, resources, width and acute angles. A slice-based heuristic prunes the ILP. — [ISPD'13 slides](https://ispd.cc/ispd2026/slides/2013/5_wang.pdf) [P-full slides]
- All (PCB).

**Package-level escape context**
- Kubo and Takahashi (ISPD 2005; TCAD 2006): 2-layer BGA package global routing where "the global routing for each net is uniquely determined by a via assignment", improved by swapping and moving vias. (package) — [IEEE 1610736](https://ieeexplore.ieee.org/document/1610736/) [P-abs]

**ML for escape** (see Q7)
- A DQN on a simulated 25×26 grid with 30/60/90 pins (SPIE 2025): toy scale. (PCB) — [SPIE 13510](https://remotesensing.spiedigitallibrary.org/conference-proceedings-of-spie/13510/135101B/Escape-routing-using-deep-reinforcement-learning/10.1117/12.3058004.full) [S]
- Learned dual predictions warm-start ε-relaxation min-cost flow, giving a **1.64×** average speedup on chip escape routing (arXiv 2026). (IC) — [arXiv:2601.20203](https://arxiv.org/abs/2601.20203) [P-abs]

### Inferences
- **Hand escape to exact solvers.** For BGA/FPGA escape, the LLM should not route. It should choose the via technology, layer budget, DP and bus groupings and swappable pins, then call an exact solver (flow/MCF for single layer, SAT+flow for multi-layer).
  - An *infeasibility proof* ("no 2-layer escape exists for this BGA with through vias") is unique, high-value information. The LLM can relay it to the user as a stackup or HDI decision.
- **Pin assignment is part of escape.** Bus sequencing and pin assignment are polynomial and jointly optimizable with escape. Making "pin/bank swap" a first-class action (with ECO back-annotation) is likely the cheapest large win; vendor examples show 4× via reductions. That decision depends on datasheet semantics an LLM can read.

### Gaps
- None of these academic escape routers appear to have public code. Exceptions: MonoSAT (general solver; its BGA-specific scripts were not found) and PcbRouter (Q5).
- The industrial benchmark sets (B-escape, NCER, Lin 2021) are not public.

---

## Q4. Length matching, bus routing, meander/trombone/sawtooth generation, and CAD-contest problems

### Takeaway
Academic length matching moved through three stages:
1. Lagrangian-relaxation resource allocation during routing (Ozdal-Wong 2003/2006).
2. Gridless area assignment. BSG-Route solved one case in 88 s where LR took more than a day.
3. LP/ILP/flow area assignment for any-direction multilayer PCBs (2024–2026).

In practice:
- Commercial and open tools tune *after* routing with pattern generators (accordion/trombone/sawtooth; KiCad greedy fill-then-trim).
- Bus routing research addresses twisted-bus untangling and multi-bus skew.
- **No ICCAD CAD Contest problem on PCB routing was found for 2015–2026.** The only bus-routing contest (ICCAD 2018 Problem B) was an IC on-track problem.

### Cited Findings

**Length-matching algorithms (PCB)**
- **Ozdal and Wong LR (TCAD 2006).** There was "no sophisticated algorithm … that ensures that minimum length constraints are also satisfied". They use Lagrangian relaxation "to allocate extra routing resources around nets simultaneously during routing", with a graph model ensuring allocated resources can be used to extend length. The algorithm "automatically prioritizes resource allocation for shorter nets and length minimization for longer nets". — [IEEE 4015547](https://ieeexplore.ieee.org/document/4015547/) [P-abs]; [ICCAD'03](https://doi.org/10.1109/iccad.2003.159717) [T]
- **Single-layer bus (Ozdal and Wong, TCAD 2006).** A provably optimal algorithm for minimum-area, maximum-length constraints in O(A) and a near-optimal one for exact bounds in O(A log A), where A is the intermediate-region area. — [IEEE 1597384](https://ieeexplore.ieee.org/document/1597384/) [P-abs]
- **Two-layer bus (Ozdal and Wong, TODAES 2006).** Processes one track at a time, choosing net subsets, with length extension during routing. — [doi:10.1145/1124713.1124726](https://doi.org/10.1145/1124713.1124726) [P-abs]
- **BSG-Route (Yan and Wong, ICCAD 2008 → TCAD 2009).** This is *not* Kubo/Yan/Chang, as the assignment prompt suggested.
  - Previous length-constrained routers "all have assumptions on the routing topology". BSG-Route handles general topology, is gridless, and treats length matching as **area assignment** using the bounded-sliceline grid (a placement structure), solved by iterative math programming.
  - Example: 88 s, vs "more than one day" for Ozdal-Wong LR.
  - Source: [IEEE 5290341](https://ieeexplore.ieee.org/document/5290341/) [P-abs]
- **CAFE router (Kohira and Takahashi, ASP-DAC 2010).** Greedily extends each net from pin to pin so its length approaches a *target* length on a single-layer grid with obstacles. — [IEEE 5419882](https://ieeexplore.ieee.org/document/5419882/) [P-abs]
- **Obstacle-aware length-matching bus routing (Yan and Chen, ISPD 2011).** O(mn+s³), saving 80.5% CPU with zero length error. — [doi:10.1145/1960397.1960412](https://doi.org/10.1145/1960397.1960412) [P-abs/TLDR]
- **Disordered pins (Zhang, Pan, Zhu, Watanabe, ASP-DAC 2015).** Uses LCS of pin pairs for layer assignment, single-commodity flow for base routes, then "R-flip and C-flip" length adjustment. — [IEEE 7059038](https://ieeexplore.ieee.org/document/7059038/) [P-abs]
- **Multiple-bus routing (J.-T. Yan, TCPMT 2022).** Single-layer, obstacle-aware: 10.7% more buses routed, and maximum skew reduced from 14.25 to 1.38 on average. — [doi:10.1109/TCPMT.2022.3175069](https://doi.org/10.1109/TCPMT.2022.3175069) [P-abs]
- **Any-direction multilayer area assignment (Lin, Guo, Fang, TODAES 2026).** LP, then ILP with obstacle "utility constraints", then a combinatorial minimum-weight hierarchical flow algorithm, near-optimal by LP primal-dual. It "allows the modification of the wire topology". This continues Fang et al. DAC 2024 (MSDTW meandering), which the earlier notes covered. — [doi:10.1145/3795795](https://doi.org/10.1145/3795795) [P-abs]
- **Ant colony optimization (2025).** Min/max length constraints, with "two-ant synchronized routing" for DPs. Weak venue; no benchmark details seen. — [doi:10.1142/s0129156425405777](https://doi.org/10.1142/s0129156425405777) [P-abs]

**SI side-effect of meanders**
- Tseng, Li, Ho and Schlichtmann (ICCAD 2013): dense meanders cause a "speedup effect due to crosstalks between the segments of the same wire", so equal physical length does not give equal delay. ILP post-processing roughly doubles meander width and spacing "even under very tight area constraints". (PCB) — [IEEE 6691193](https://ieeexplore.ieee.org/document/6691193/) [P-abs]

**Pattern generation in tools**
- **Altium.** Three tuning patterns, inserted "according to the available space, design constraints, and obstacles". (PCB) — [Altium length tuning docs](https://www.altium.com/documentation/altium-designer/pcb/high-speed-design/length-tuning) [P-doc]
  - **Accordion:** Max Amplitude, Space, Miter %, Style (Mitered Lines / Mitered Arcs / Rounded; "Rounded … most compact").
  - **Trombone:** Space and Style.
  - **Sawtooth:** Tooth Width, minimum height, Angle (edge slope), Actual Height.
- **KiCad PNS meander** (master, Oct 2026). (PCB) — [pns_meander.h](https://gitlab.com/kicad/code/kicad/-/raw/master/pcbnew/router/pns_meander.h); [pns_meander.cpp](https://gitlab.com/kicad/code/kicad/-/raw/master/pcbnew/router/pns_meander.cpp); [pns_meander_placer_base.cpp](https://gitlab.com/kicad/code/kicad/-/raw/master/pcbnew/router/pns_meander_placer_base.cpp) [P-code]
  - **Shapes:** `MT_SINGLE` (single-sided), `MT_START`, `MT_FINISH`, `MT_TURN`, corner and arc primitives.
  - **Fill step:** `MeanderSegment` greedily walks each base segment, fitting start/turn/finish or single bumps alternately on each side. `MEANDER_SHAPE::Fit` tries amplitudes from max down to min in `m_step` until collision-free. A comment notes the minimum corner radius is half the width because square corners on "high-speed nets (e.g., DDR4)" cause reflections.
  - **Trim step:** `tuneLineLength` accumulates elongation along the fitted meanders, converts the last needed one to an end shape, and empties the rest (fill, then trim).
  - **New in master:** `MEANDER_SETTINGS` now carries **chain-level** fields ("additional pre-existing length contributed by other nets in the same logical chain"). This relaxes the earlier notes' point that tuning was point-to-point only; scope and UI not verified.
- **TopoR:** trapezoid-inscribed arc serpentines with 50 nm tolerance (see Q2). — [TKEA 2009](https://www.tkea.com.ua/index.php/journal/article/view/TKEA2009.4.03) [P-full]
- **Cadence Allegro:** Auto-interactive Delay Tuning (AiDT) tunes "selected signal sets, such as a byte lane or entire interface". Pegatron reported ~67% less routing time. (PCB) — [Cadence/Pegatron success story](https://www.cadence.com/en_US/home/resources/success-stories/pegatron-and-cadence-ss.html) [S/V]

**Bus untangling (PCB)**
- **Yan and Wong (ICCAD 2007; TODAES 2009):** prior bus routers "assume matched pin ordering"; real buses are "twisted". They introduce "single-detour routing" with a necessary-and-sufficient condition and a DP algorithm that includes inter-pin capacity. — [IEEE 4397297](https://ieeexplore.ieee.org/document/4397297/); [doi:10.1145/1529255.1529268](https://doi.org/10.1145/1529255.1529268) [P-abs]
- **Lin, Dong, Chen and Goto (ASP-DAC 2012):** optimal O(n) one-sided single-detour untangling, versus an earlier O(n³) DP. — [IEEE 6164936](https://ieeexplore.ieee.org/document/6164936/) [P-abs]
- **Two-sided untangling:** Yan and Chen (DAC 2010) — [doi:10.1145/1837274.1837325](https://doi.org/10.1145/1837274.1837325) [T]; J.-T. Yan (TODAES 2019) adds internal detours (+2.8–3.5% routability). — [doi:10.1145/3363184](https://doi.org/10.1145/3363184) [P-abs]

**CAD contests**
- **ICCAD 2018 Problem B, "Obstacle-Aware On-Track Bus Routing"** (Synopsys Taiwan) is an **IC** problem. — [contest page](https://www.iccad-contest.org/2018/index.html) [P-doc]; [CFP](https://www.iccad-contest.org/2018/CFPv3-2018_CAD_Contest.pdf) [P-doc]
  - Winners: CUHK team CU-Bus (advisor E. Young), then Bus_Driver (S.-Y. Fang), then a team advised by M. Fujita and Y.-W. Chang.
  - Task: all bits of a bus must share one topology while avoiding small obstacles on non-uniform tracks. — [CUHK news (snippet)](https://www.cse.cuhk.edu.hk/news/achievements/computer-science-engineering-cse-students-won-the-champion-in-2018-cad-contest-at-the-ieee-acm-international-conference-on-computer-aided-design-iccad/) [S]
- **DAG-based follow-up.** Hsu, Hung, Chen, Sun and Chang (DAC 2019; TCAD 2021): bus clustering, a DAG algorithm for topology-matching, and rip-up. The top-3 contest routers had "145%, 158%, and 420% higher costs". (IC) — [doi:10.1145/3316781.3317740](https://doi.org/10.1145/3316781.3317740); [TCAD](https://doi.org/10.1109/tcad.2020.3002546) [P-abs]
- **No PCB contest problem found.** Contest home pages for 2015–2026 were fetched and their problem titles scanned. None contains "PCB", "printed circuit", "board" or "package". The 2012–2014 pages did not load. — e.g. [2019](https://www.iccad-contest.org/2019/), [2026](https://www.iccad-contest.org/2026/) [P-doc]
  - The 2019 problems include FPGA routing and an open-source LEF/DEF global router; the 2026 problems are LLM netlist exploration, regression bucketing and the FloorSet challenge.

### Inferences
- **Reserve area before routing.** Three independent lines point the same way: academic area-assignment (BSG, LP-based), Situs pass design, and TopoR trapezoids. The router should reserve meander *area* during planning rather than rely on KiCad's post-hoc greedy fill, which fails when neighbours have consumed the space.
  - An LLM can convert DDR/bus constraints into per-net "extension budgets" and keep-out regions *before* routing.
- **Encode meander SI limits as rules.** Meander pitch and amplitude should be explicit rules the LLM sets (≥3w per TopoR; avoid the dense-meander speedup per Tseng), not left to defaults.

### Gaps
- Taiwan's domestic CAD contest and ISPD contests were not checked for PCB problems.
- No academic length-matching code was found to be public.
- The Allegro AiDT/AiBT algorithms are undocumented beyond marketing.

---

## Q5. Differential-pair routing algorithms (gridless, coupled path planning)

### Takeaway
Three algorithmic patterns recur.
1. **Median-point / centerline routing:** route one virtual wire between P/N "median points", then offset. Used by Li et al. 2012 and OpenROAD PcbRouter, and by KRT (earlier notes).
2. **Gateway enumeration for coupled entry and exit:** KiCad PNS.
3. **Joint LP/ILP or SAT constraints:** same-layer pairs, protection zones, length match.

Most autorouters, including Altium Situs, still expect diff pairs to be routed and locked by hand before bulk autorouting.

### Cited Findings
- **Chang et al.** (likely what the assignment calls "Chang et al. diff pair"): Fang, Ho and Chang (ICCAD 2008) give "the first routing algorithm … for chip-package-board co-design with differential-pair considerations". (package/PCB) — [IEEE 4681623](https://ieeexplore.ieee.org/document/4681623/) [P-abs]
  - LP/ILP global routing across chip, package and PCB, with variable and constraint reductions of 95% and 99% "without loss of … optimality", followed by **any-angle** detailed routing.
  - 100% routability and optimal global wirelength on five industry designs.
- **Lin, Merrill, Wu, Holtz and Cheng (ASP-DAC 2021):** a full-board router for complicated constraints and DPs. It achieves "100% routability without any design rule violation while the other two state-of-the-art routers fail to complete the routing for some test cases and incur design rule violations". (PCB) — [doi:10.1145/3394885.3431568](https://doi.org/10.1145/3394885.3431568) [P-abs]
- **OpenROAD PcbRouter** (BSD-3; reads `.kicad_pcb` from KiCad 5.1.2; archived in "The-OpenROAD-Project-Attic"). (PCB) — [README](https://raw.githubusercontent.com/The-OpenROAD-Project-Attic/PcbRouter/master/README.md) [P-doc]; [GridBasedRouter.cpp](https://raw.githubusercontent.com/The-OpenROAD-Project-Attic/PcbRouter/master/src/GridBasedRouter.cpp); [GridDiffPairNet.cpp](https://raw.githubusercontent.com/The-OpenROAD-Project-Attic/PcbRouter/master/src/GridDiffPairNet.cpp) [P-code]
  - It routes DPs first, as a `GridDiffPairNet`. Pins of the two nets are paired by nearest HPWL, and "median (merging) points" are added as pseudo through-hole pins.
  - Signal nets follow. Then N "fixed-order rip-up and re-route" iterations each add `gStepTraObsCost`/`gStepViaObsCost` to every net's obstacle costs (escalating, negotiation-like) and keep the best total cost.
  - Inference (not confirmed in the repo): it appears to be the code behind the UCSD/Cheng-group PCB papers above.
- **KiCad PNS DP router** (master). (PCB) — [pns_diff_pair.h](https://gitlab.com/kicad/code/kicad/-/raw/master/pcbnew/router/pns_diff_pair.h); [pns_diff_pair.cpp](https://gitlab.com/kicad/code/kicad/-/raw/master/pcbnew/router/pns_diff_pair.cpp) [P-code]
  - A `DP_GATEWAY` is "a pair of points (anchors) with certain orientation, spacing and (optionally) predefined entry paths. The routing algorithm connects such gateways with parallel lines".
  - `FitGateways` enumerates every entry × target gateway pair, both diagonal and straight. It builds an initial coupled pair for each, scored by gateway priority, coupled ratio and aspect ratio.
  - Gateways are built from pads, primitive pairs, cursor position and via fitting.
- **Bayless et al. 2016:** DP support in SAT escape by forcing paired signals' vias to the same layer assignment. (PCB) — [ICCAD'16 PDF](https://www.cs.ubc.ca/labs/isd/Projects/monosat/monosat_bga_iccad2016.pdf) [P-full]
- **Analog IC DP routing (2024):** symmetry, EM and IR aware. (IC, low transferability) — [IEEE ICICM 2024](https://doi.org/10.1109/icicm63644.2024.10814254) [P-abs]
- **TopoR:** arc-smoothed wires keep a constant, maximal gap along the whole length, "important, for example, for differential pairs". (PCB) — [Eremex TopoR](https://www.eremex.ru/products/delta-design/topor/) [V]
- **Altium Situs:** "Differential pairs nets must be manually routed and locked before using the autorouter. If you do not [do] this, the routing is very likely to change and alter the signal integrity". (PCB) — [Altium Situs docs](https://www.altium.com/documentation/altium-designer/automated-board-layout-situs-topological-autorouter) [P-doc]
- **Escape-level DP methods:** see Q3 (Yan et al. 2010; Li et al. 2012; Yan 2015; Wang et al. 2013).

### Inferences
- **Recommended DP pipeline:**
  1. Median-point detection: pair pins and compute where P and N merge.
  2. Coupled centerline routing in a planner.
  3. Realization with KiCad's gateway-based DP placer.
  4. Skew tuning.
- **For BGAs with many pairs,** the median-point + min-cost-flow formulation (Li et al. 2012) generalizes to simultaneous DP escape. A KiCad-native, BSD-licensed reference (PcbRouter) exists to borrow from, subject to a licence and porting review.

### Gaps
- The Lin et al. ASP-DAC 2021 full text was not obtained, and the link to PcbRouter is inferred.
- No gridless DP router with published coupled-gap guarantees *during area routing* (as opposed to escape) was found.

---

## Q6. Via minimization, layer assignment, and net ordering (why order matters and how to reduce dependence on it)

### Takeaway
**Via minimization**
- Unconstrained topological via minimization is **NP-complete** (Marek-Sadowska 1984).
- Constrained via minimization (CVM) for two-layer PCBs has polynomial optimal cases (Chen-Kajitani-Chan 1983) and fast heuristics (signed hypergraphs).
- Modern practice treats via count as a cost term: Situs "Via Miser" and a vias slider; Freerouting via costs. Topology-first and SAT approaches show the largest reported reductions.

**Net ordering**
- The literature conflicts: Abel (1972) found total completed ideal length experimentally order-independent, while textbooks and lectures say ordering "greatly affects" results.
- The robust lesson is that **simultaneous/negotiated methods reduce order sensitivity**:
  - SURF's simultaneous global routing;
  - negotiation-based layer assignment;
  - Specctra's and Situs's conflict-tolerant first passes.

### Cited Findings

**Via minimization and layer assignment**
- **Hsu (TCAD 1983).** Topological routing selects via a circle graph "a maximal set of nets that can be routed without vias". Layer assignment is cast as **max-cut** on an edge-weighted graph and solved greedily, then geometrical mapping follows. (IC, two-layer) — [IEEE 1270041](https://ieeexplore.ieee.org/document/1270041/) [P-abs]
- **Chen, Kajitani and Chan (IEEE TCAS 1983).** A graph-theoretic via minimization algorithm "for certain types of two-layer printed circuit boards", polynomial-time. It handles junction degrees 2–8 and is guaranteed minimum for ≤3 segments per junction. It also covers pre-assigning segments to layers. (PCB) — [IEEE 1085357](https://ieeexplore.ieee.org/document/1085357/) [P-abs]
- **Marek-Sadowska (TCAD 1984).** "The simplest problem of this type is NP-complete"; a heuristic for topological via minimization. — [IEEE 1270074](https://ieeexplore.ieee.org/document/1270074/) [P-abs]
- **Shi (GLSVLSI 1992).** A signed-hypergraph model of general CVM, with a linear-time heuristic for two layers. — [IEEE 218350](https://ieeexplore.ieee.org/document/218350/) [P-abs]
- **Chang and Cong (DAC 1997).** "An Efficient Approach to Multi-layer Layer Assignment with Application to Via Minimization". (IC) — [doi:10.1145/266021.266294](https://doi.org/10.1145/266021.266294) [T]
- **Liu and Li (ASP-DAC 2011), negotiation-based layer assignment (NVM).** (VLSI) — [IEEE 5722248](https://ieeexplore.ieee.org/document/5722248/) [P-abs]
  - Traditional via-count layer assignment "tends to produce varying qualities … using different net orderings". With negotiation, "net assignment ordering only slightly influences the quality".
  - Additional via cost is 10.8% and 2.5% lower than two prior methods; via overflow improves 11.5% with a two-stage method.
- **Dayan and Dai rubber-band layer assignment:** steepest descent with a K_v via-vs-length knob (see Q2). (MCM) — [UCSC-CRL-93-04](https://tr.soe.ucsc.edu/sites/default/files/technical-reports/UCSC-CRL-93-04.pdf) [P-full]
- **Situs.** A "More/Less Vias" slider trades "greater routing speed" against "fewer vias". The "Via Miser" default strategy does "aggressive via minimization". The Completion pass makes vias cheaper. Blind/buried via use follows the Layer Stack Manager via types. (PCB) — [Altium Situs docs](https://www.altium.com/documentation/altium-designer/automated-board-layout-situs-topological-autorouter) [P-doc]
- **Escape-specific layer minimization** (Ozdal-Wong; Yan-Kong-Wong; Ma-Young-Wong; Bayless): see Q3.

**Net ordering: evidence and conflicts**
- **Abel (IEEE TC 1972).** For maze routers that route one connection at a time, "experimental evidence is presented … to show that the performance of a router, when measured in terms of the total of the minimum (or ideal) lengths of the connections successfully completed, is, in fact, independent of the order". (PCB-era) — [IEEE 1672075](https://ieeexplore.ieee.org/document/1672075/) [P-abs]
  - **Conflict:** NYCU lecture slides cite the same Abel paper for "finding the optimal net ordering is proven to be NP-hard" and state "net ordering greatly affects routing solutions". — [NYCU lec6](https://tiger.iee.nycu.edu.tw/course/EDAIntro2026Spring/materials/lec6.pdf) [P-full slides]
- **Servit and Schmidt (CAD 1980).** "The order of net processing influenced the quality of the solution", and source/target choice influenced time and quality. (PCB) — [doi:10.1016/0010-4485(80)90027-5](https://doi.org/10.1016/0010-4485(80)90027-5) [P-abs/TLDR]
- **Textbook ordering heuristics** (same slides): ascending number of pins inside the bounding box; ascending length when routability is critical (descending when timing is); timing criticality. (VLSI) — [NYCU lec6](https://tiger.iee.nycu.edu.tw/course/EDAIntro2026Spring/materials/lec6.pdf) [P-full slides]
- **Groeneveld (IEEE D&T 1989).** Ordering *junction pins* on region boundaries "avoids unnecessary wire twisting". (IC) — [IEEE 41670](https://ieeexplore.ieee.org/document/41670/) [P-abs]
- **Ordering inside open-source PCB routers** [P-code]:

  | Router | Ordering rule |
  |---|---|
  | gEDA rectangle-expansion | Smallest bounding box first; then previous-pass cost ascending |
  | gEDA toporouter | Pairwise-interaction (fails, then detour sum) |
  | PcbRouter | Diff pairs first, then fixed netlist order with escalating costs |

  Sources: [autoroute.c](https://raw.githubusercontent.com/bert/pcb/master/src/autoroute.c); [toporouter.c](https://raw.githubusercontent.com/bert/pcb/master/src/toporouter.c); [PcbRouter](https://raw.githubusercontent.com/The-OpenROAD-Project-Attic/PcbRouter/master/src/GridBasedRouter.cpp)
- **Situs:** "Routing Priority rules" put higher priority on "difficult nets, or those that you want to have the cleanest routing". (PCB) — [Altium Situs docs](https://www.altium.com/documentation/altium-designer/automated-board-layout-situs-topological-autorouter) [P-doc]
- **Learned ordering:**
  - Asynchronous RL net-order exploration with transfer learning: 26% fewer DRC violations, plus a 1.2% reduction in a second metric that the abstract text seen was cut off before naming (VLSI detailed routing; DATE 2021 → TCAD 2022). — [doi:10.1109/TCAD.2021.3117505](https://doi.org/10.1109/TCAD.2021.3117505) [P-abs]
  - ML ordering for layer assignment in **multilayer package substrate** global routing "supersedes conventional net ordering techniques based on heuristic score functions" (arXiv 2024; package, the closest domain to PCB). — [arXiv:2412.21035](https://arxiv.org/abs/2412.21035) [P-abs]
  - The earlier notes cover IJCAI 2025 transformer RL ordering.

### Inferences
- **Resolving the ordering conflict.** Abel's metric (total ideal length of completed connections) can stay flat while *which* nets fail changes. Ordering matters for *who* gets the good resources (critical nets) more than for aggregate completion. This is a priority decision an LLM can legitimately make. Aggregate completion should be protected with negotiation or rip-up rather than clever ordering.
- **Pairwise-interaction scoring as an LLM input.** The toporouter's score costs O(n²) single-net routes. That is cheap for the ~10²-net boards in PCBWorld D3-A/B. It gives the LLM a *quantified conflict graph* (A forces B to detour by x mm), which complements MPS crossing analysis (KRT, earlier notes).

### Gaps
- Abel's full paper was not read, so the exact experimental setup behind "order-independent" is unknown.
- No PCB-specific study was found comparing ordering heuristics on modern boards.

---

## Q7. ML for routing order, routability and route generation (VLSI 2019–2026) and transferability to PCB

### Takeaway
VLSI ML routing moved from one-shot generative global routing to:
- connectivity-guaranteed hybrids (HubRouter, NeuralSteiner);
- end-to-end diffusion/bridge models (DSBRouter);
- differentiable concurrent routing (DGR);
- learning to *schedule a classical router's costs* (offline RL: 1.56–3× faster convergence, −92% DRVs).

PCB-specific ML remains small-scale:
- Unet-Astar: learned search-region masks speed up A* about 4× on generated problems.
- Ranking Cost: learned cost maps plus A*.
- FanoutNet (earlier notes).

The 2026 OmniRouting benchmark confirms that LLMs emitting PCB routes directly fail badly (best 12.6% net routability zero-shot, 28% agentic). A 2019-era open grid router (PcbRouter) scored 56%.

### Cited Findings

**VLSI global-routing generative models** (ISPD98/07 benchmarks; low direct transfer)
- **HubRouter (NeurIPS 2023, Du, Wang, Zhong, Yan).** Generative global routers "suffer from the non-connectivity of generated routes". HubRouter generates "hubs" (key route points) with a generative model, then connects pins and hubs with an actor-critic RSMT module. — [NeurIPS abstract](https://proceedings.neurips.cc/paper_files/paper/2023/hash/f7f98663c516fceb582354ee2d9d274d-Abstract-Conference.html) [P-abs]
  - The authors' slides list limitations: not end-to-end; needs "a large amount of training data". — [S]
  - Name collision: an unrelated 2026 "HubRouter" is a sequence-model primitive. — [arXiv:2604.22442](https://arxiv.org/abs/2604.22442) [P-abs]
- **NeuralSteiner (NeurIPS 2024):** predicts Steiner-point locations with full-net spatial and overflow information, then graph post-processing, giving overflow-avoiding RSTs. — [doi:10.52202/079017-4045](https://doi.org/10.52202/079017-4045) [P-abs]
- **DSBRouter (ICML 2025, Shi et al.):** a Diffusion Schrödinger Bridge between pins and routes. It is "end-to-end … does not require a post-step to ensure connectivity", uses evaluation-guided sampling, and achieves SOTA overflow on ISPD98 and part of ISPD07. — [PMLR v267](https://proceedings.mlr.press/v267/shi25k.html) [P-abs]
- **DGR (DAC 2024):** a differentiable global router over a DAG forest of pattern routes for "hundreds of thousands of nets", relaxed to continuous and solved on GPU. Wirelength drops 0.95–4.08% and vias 1.28–2.54% on congested cases vs academic global routers. — [doi:10.1145/3649329.3656530](https://doi.org/10.1145/3649329.3656530) [P-abs]
- **GAT-Steiner (2024):** a graph attention net predicts RSMT Steiner points; 99.846% of ISPD19 nets correct. — [arXiv:2407.01440](https://arxiv.org/abs/2407.01440) [P-abs]
- **"Routing as autoregressive sequence generation"** with transformers: no 2025–2026 routing (not placement) paper was found. The search surfaced only diffusion and flow models for *placement*. — [S]

**Learning to tune classical routers** (VLSI; high transfer potential)
- **Offline RL with conservative Q-learning** dynamically selects routing cost weights per iteration. Prior routers "statically schedule the cost weights". It is 1.56× faster on average (up to 3.01×) on ISPD19 at equal or better DRVs, with some cross-technology generalization. — [arXiv:2512.03594](https://arxiv.org/abs/2512.03594) [P-abs]
- **History-aware LSTM variant (2026):** −92% DRVs vs the top public baseline and −10% runtime in dense regimes. It "can be integrated into any cost-based router … does not interfere with the core search". — [arXiv:2609.08232](https://arxiv.org/abs/2609.08232) [P-abs]

**PCB-specific ML**
- **Ranking Cost (2021).** A* plus evolution strategies learn per-net "cost maps" and a ranking (ordering) parameter, end to end, with no human data. It beats sequential A* and an RL baseline on connectivity rate and scalability (PCB/VLSI-generic grids). — [arXiv:2110.03939](https://arxiv.org/abs/2110.03939) [P-abs]
- **Unet-Astar (IEEE Access 2023).** A U-Net predicts "recommended regions" to restrict A* in a reimplementation of Lin et al.'s DAC 2021 unified router. (PCB) — [IEEE 10274949](https://ieeexplore.ieee.org/document/10274949/) [P-full]; [repo](https://github.com/Firesuiry/Unet-Astar-For-PCB-Routing)
  - On 200 *generated* problems: runtime 302 → 78 (paper units), vias 331 → 257 (−22%), wirelength −0.2%, both 100% routable.
  - Includes a parameterized problem generator. The repo README says code "will be provided after the paper is accepted".
- **Security-aware PCB routing (ISQED 2026).** Nets are prioritized "by assigning routing sequences prior to trace generation", routed with multilayer A*, and RL places test points. 100% routing success on the evaluated boards. (PCB) — [ISQED'26 abstract](https://isqed.org/English/Archives/2026/Technical_Sessions/131.html) [P-abs]
- **DeepPCB's own explanation of its RL.** (PCB) — [DeepPCB blog](https://deeppcb.ai/reinforcement-learning-pcb-routing-explained/) [P-doc/V]
  - Actions: "extend a trace in a particular direction, change layers via a via, complete a net, or … rip up". Typical granularity: "extend this trace segment by one grid unit".
  - The reward penalizes vias and DRC and rewards completion. Agents are trained in simulation on "a large corpora of designs".
  - Stated limitations: the model "doesn't understand intent", may not capture physics beyond training, "confidence doesn't correlate reliably with correctness", and may exploit "reward-function loophole[s]".
  - This fills part of the earlier notes' DeepPCB architecture gap; no paper-level detail.

**LLM PCB-routing benchmark (new in 2026, not in the earlier notes)**
- OmniRouting (arXiv, Aug 2026) contains 1,681 industrial-grade schematic-coupled PCB designs. (PCB) — [arXiv:2608.04434](https://arxiv.org/abs/2608.04434) [P-full HTML]
  - **Tasks:** geometric, DRC-aware, electrical-functionality and tool-augmented agentic routing.
  - **Net routability (NRR):** best zero-shot LMM 12.60% (PRR 15.41%); agentic best 27.98%; human reference 93.58%. The open-source **PcbRouter baseline reached 56.20% NRR / 71.37% PRR**.
  - **Errors:** base LMM outputs average 69.8–431.3 DRC violations and 20–78% physical shorts.
  - **Tools:** "tools improve local legality and routing-corridor selection more than global connectivity". The Preroute tool raised graph similarity by about 10 points.
  - "More steps do not guarantee improvement … Feedback quality matters more than iteration count".
- Companion OmniLayout benchmark: placement reasoning on the same 1,681 designs. — [arXiv:2607.03261](https://arxiv.org/abs/2607.03261) [P-abs]

**Industry framing**
- The ISPD 2024 invited talk "Challenges for Automating PCB Layout" (Wen-Hao Liu, Anthony Agnesina, Haoxing Ren; affiliations not verified): PCB design is "typically semi-automated or fully manual", and PCB houses seek automation for productivity. — [doi:10.1145/3626184.3635285](https://doi.org/10.1145/3626184.3635285) [P-abs]
  - DeepPCB quotes this keynote as concluding that "lack of research progress in PCB routing algorithms" made routing "a bottleneck". That wording is **not** in the published abstract. — [DeepPCB essay](https://deeppcb.ai/the-60-year-routing-problem-nobody-solved/) [S]

### Inferences
- **Transfer is highest for meta-level learning,** where the classical PCB router stays in charge:
  - cost-schedule learning (offline RL);
  - search-region pruning (Unet-Astar);
  - flow warm starts (dual predictions);
  - net ordering.

  Generative global routing (HubRouter, DSBRouter) assumes G-cell grids, Manhattan layers and huge homogeneous net counts, so transfer to PCB is low.
- **Two LLM-on-real-boards benchmarks now agree.** OmniRouting and PCBWorld both find that LLMs should not emit copper, and that tools help local repair more than global connectivity. Global decisions (topology, order, layer, escape) belong to solvers that the LLM *configures*.

### Gaps
- No GNN-based PCB net-ordering or routability paper was found.
- The Heatmap Router (Iowa State 2022) was seen as a title only. — [doi:10.31274/cc-20240624-819](https://doi.org/10.31274/cc-20240624-819) [T]
- OmniRouting's dataset and tool interfaces were announced as "will open-source"; release not verified.

---

## Q8. Practitioner "autorouter skepticism": specific failure modes experts cite

### Takeaway
Experts consistently cite:
1. too many vias;
2. wasted space from strict X/Y layer bias;
3. cleanup taking longer than manual routing;
4. setup complexity, where "too many rules can bog it down";
5. blindness to intent (current, noise, return current, clocks, analog);
6. a bottom-up, one-connection-at-a-time process that clashes with designers' top-down planning.

Vendors responded with *guided* automation rather than full autorouting:
- sketch routing that reuses existing fanout vias;
- topological mapping;
- flow planning with bundles;
- delay tuning on byte lanes.

### Cited Findings
- **Barry Olney (PCB Design, Nov 2015).** (PCB) — [Olney 2015](https://www.icd.com.au/articles/Autorouters_PCBD-Nov2015.pdf) [P-full]
  - "Ask any group of PCB designers what they think of autorouters and the majority will say that they do not use them because they do not work."
  - Early autorouters "added too many vias, wasted space due to the strict XY bias, and the quality was poor". He recalls a weekend mainframe run "50% complete by Monday morning".
  - His remedy is constraints set up front: stackup with "clear, uninterrupted return paths", via spans, SI and PI analysis, FPGA I/O pin swapping to reduce crossovers, and placement.
  - He warns "too many rules can also bog it down".
  - The Sketch router "can optimize the trace fanouts … avoiding additional vias … [and] gloss the finished route to look much like a manual route".
- **Altium history article (2016).** (PCB) — [Altium: "To Autoroute or Not to Autoroute"](https://resources.altium.com/p/to-autoroute-or-not-to-autoroute-a-history-of-failed-design-automation) [P-full/V]
  - Early tools "offered no guidelines or configurations to preserve signal integrity, often adding an excessive amount of vias", were "limited to a strict X/Y grid … layer biased", and fixing their output "often took more time than it would have to route a board manually".
  - Side-effects: "incomplete and poorly optimized routes", "setup complexities that required expert configurations", and "time spent … to fix poor autorouting paths".
  - **Core mismatch:** engineers plan "at 10,000 feet" and "sketch the bus system … on paper", whereas autorouters work "from the bottom up, one interconnect at a time".
  - Route-planning tools took longer to configure "than a manual routing process".
- **Siemens white paper and blog (2015, 2023).** (PCB) — [Siemens white paper](https://resources.sw.siemens.com/en-US/white-paper-a-stroke-of-genius-saving-time-and-effort-with-sketch-routing) [P-doc/V]; [Siemens blog 2015](https://blogs.sw.siemens.com/electronic-systems-design/2015/05/19/to-autoroute-or-not-to-autoroute-that-is-the-question/) [P-doc]; [Siemens blog 2023](https://blogs.sw.siemens.com/electronic-systems-design/2023/07/19/pcb-routing/) [P-doc]
  - Reasons for "shunning autorouting": "the intimidation factor of trying to set up the autorouter … to translate the designer's vision", cleanup time, and "too many vias – or, the general inability … to complete a design with the elegance" of an expert.
  - Sketch routing: the designer "draws a line to dictate the path"; "the most common method … uses the existing via fan-outs and does not add any additional vias".
  - A "hug router" "push[es], shove[s], and squeak[s]" in the last nets.
- **SparkFun forum (practitioners, anecdotal).** (PCB) — [SparkFun forum](https://community.sparkfun.com/t/whats-wrong-with-autorouters/11623) [P-full]
  - The autorouter "has no way of knowing what the traces … are designed to do … or how much current may be flowing".
  - "Critical tracks like supplies and grounds, and clocks, are routed manually."
  - "No-one would think of autorouting an analogue circuit."
  - Poor grouping "will definitely lead to more vias than needed".
- **Element14 forum (snippet only).** Autorouters encourage sloppy routing; newcomers miss "how much return current flow matters"; via placement and layer side matter for high-speed or low-noise designs. — [Element14 thread](https://community.element14.com/products/eagle/f/eagle-user-chat-english/2104/re-optimize-after-autoroute/85705) [S]
- **Luzin and Polubasov (Eremex, 2009),** critique of orthogonal and preferred-direction routers. (PCB) — [PCD&F 2009](https://pcdandf.com/pcdesign/index.php/2009-archive-articles/5203-advantages-of-isotropic-pcb-routing) [P-full/V]
  - "Numerous bent wires that are easy to explain but not to justify."
  - The global uniform direction per layer causes warpage ("twisting").
  - Long parallel runs on adjacent layers form "a long film capacitor".
  - Unmeasured quality factors: bottlenecks, parallel run length, adjacent-layer overlap.
- **Vendor docs that concede limits.** (PCB) — [Altium Situs docs](https://www.altium.com/documentation/altium-designer/automated-board-layout-situs-topological-autorouter) [P-doc]
  - Situs: "If the board contains an area that can not be routed by hand, then it will not be autorouted either."
  - Diff pairs "must be manually routed and locked".
  - It obeys "all Electrical and Routing design rules, except the Routing Corners rule".
  - "Avoid … excessive or unnecessary rules – the more rules, the more processing time".
- **DeepPCB essay (2026, vendor).** Routing is "a resource allocation problem wrapped in geometry wrapped in physics". Autorouters are "too sophisticated to abandon but too limited to trust". The essay attributes to Altium's documentation an "80% autorouter completion as the benchmark for a well-prepared design"; that Altium source was **not verified**. (PCB) — [DeepPCB](https://deeppcb.ai/the-60-year-routing-problem-nobody-solved/) [P-full/V]
- **Cadence's answer: planning plus auto-interactive tools.** (PCB) — [EMA/Cadence webinar summary](https://ema-eda.com/ema-resources/blog/accelerate-your-design-route-faster); [Cadence success stories (Cavium)](https://resources.pcb.cadence.com/i/1436019/1) [S/V]
  - Interconnect Flow Planner bundles connections into flows.
  - Auto-interactive breakout (AiBT) and trunk routing (AiTR) check whether package pin-outs need more layers.

### Inferences
- Each practitioner complaint maps to a measurable check an LLM router can run and report:

  | Complaint | Check |
  |---|---|
  | Vias | Via count and via density per dm², using Luzin's cost thresholds |
  | Layer bias and crosstalk | Adjacent-layer parallel overlap length; long same-direction runs |
  | Bottlenecks | Total length of segments at minimum clearance |
  | Return current | Reference-plane changes without stitching vias; crossings of plane splits |
  | Intent | Per-net current vs width; clock and analog keep-outs |
  | Cleanup burden | Bends and jogs per net; acute angles |

- **The most cited unmet need is planning-level control.** The single biggest complaint is that autorouters work bottom-up while designers plan top-down. Vendors answered with sketch, flow and bundle planning, which requires a human to draw. An LLM that **generates the sketch or flow plan from schematic semantics** fills exactly that gap.

### Gaps
- No controlled study was found measuring human acceptance of autorouted vs manual boards.
- EEVblog, Hacker News and Reddit threads were not systematically surveyed.
- Rick Hartley and Lee Ritchey's direct statements on autorouters were not located.

---

## Implications for an LLM-driven KiCad router (new points only, beyond `routing_algorithms.md`)

### Takeaway
Classical and topological research supports these additions to the existing three-tier architecture:
1. A **topology layer with an exact cut-capacity feasibility check** (from SURF).
2. **Exact solvers for escape and pin assignment** (flow, SAT/MonoSAT), with infeasibility proofs fed back to the LLM.
3. **Area-reserving length-matching planning** instead of post-hoc meanders.
4. A **learned or LLM-configured conflict-penalty schedule**, because every production router negotiates.
5. A **BSD-licensed KiCad-native classical baseline** (OpenROAD PcbRouter) beside Freerouting.

The LLM's value concentrates on decisions geometry cannot infer:
- pin and bank swaps;
- bus membership and allowed bit swaps;
- net priority tiers;
- via technology and layer budget;
- which side of obstacles critical groups pass.

### Cited Findings
- For a fixed topology, any-angle vs octilinear wiring differs by ~5% length, and rectilinear by 23–31%. — [Staepelaere 1992, Table 6.1](https://tr.soe.ucsc.edu/sites/default/files/technical-reports/UCSC-CRL-92-39.pdf)
- A sketch is routable iff no cut's flow exceeds its capacity, and the spoke step identifies overflowing cuts. — [Staepelaere 1992](https://tr.soe.ucsc.edu/sites/default/files/technical-reports/UCSC-CRL-92-39.pdf)
- Altium Situs: topological map, then push-and-shove realization; diff pairs pre-routed. — [Altium Situs docs](https://www.altium.com/documentation/altium-designer/automated-board-layout-situs-topological-autorouter)
- MonoSAT multi-layer escape proves minimal layer counts on real BGAs (e.g., 3 instead of 4 layers on a 1755-signal Xilinx part). — [Bayless et al. 2016](https://www.cs.ubc.ca/labs/isd/Projects/monosat/monosat_bga_iccad2016.pdf)
- Pin assignment plus escape is polynomial-optimal: 80 buses and 7000 nets in <5 min. — [Kong, Yan, Wong 2010](https://ieeexplore.ieee.org/document/5419881/)
- Bus sequencing is O(n log n) optimal. — [Kong et al. 2007](https://ieeexplore.ieee.org/document/4397296/)
- Twisted-bus untangling is O(n). — [Lin et al. 2012](https://ieeexplore.ieee.org/document/6164936/)
- BSG-Route took 88 s vs more than a day for LR. — [Yan & Wong 2009](https://ieeexplore.ieee.org/document/5290341/)
- Negotiation appears everywhere in production routers:
  - Specctra's conflict-tolerant first pass — [Wikipedia: Specctra](https://en.wikipedia.org/wiki/Specctra)
  - Situs "Globally Optimised Main" — [Altium docs](https://www.altium.com/documentation/altium-designer/automated-board-layout-situs-topological-autorouter)
  - gEDA conflict penalties — [autoroute.c](https://raw.githubusercontent.com/bert/pcb/master/src/autoroute.c)
  - PcbRouter escalating costs — [GridBasedRouter.cpp](https://raw.githubusercontent.com/The-OpenROAD-Project-Attic/PcbRouter/master/src/GridBasedRouter.cpp)
- Offline-RL cost schedules: 1.56–3.01× faster convergence and −92% DRVs (VLSI). — [arXiv:2512.03594](https://arxiv.org/abs/2512.03594); [arXiv:2609.08232](https://arxiv.org/abs/2609.08232)
- OmniRouting: best LLM 12.6% / 28% NRR, PcbRouter 56.2%, human 93.6%. — [arXiv:2608.04434](https://arxiv.org/abs/2608.04434)
- TopoR (vendor): routes everything while allowing violations, then optimizes; moving components preserves topology; pin-equivalence cuts vias 67 → 17. — [Eremex TopoR](https://www.eremex.ru/products/delta-design/topor/)

### Inferences (concrete new recommendations)

1. **Add a topology-plan representation and a cut-capacity check (Tier 1.5).**
   - Represent each LLM-proposed critical route or bus as a *homotopy class*: the ordered list of constrained-Delaunay edges it crosses per layer, plus via points. Do not use a polyline.
   - Before any geometry, run the SURF cut test (flow = Σ(width + spacing) of wires crossing ≤ edge length) to reject or repair infeasible sketches and name the exact bottleneck.
   - gEDA's `toporouter.c` has working CDT, capacity, flow and A*-over-triangulation code to study. It is GPLv2+, so reuse is limited to separate-process use or reimplementation.
   - This complements the earlier notes' RUDY tiles with an exact check.

2. **Spend LLM effort on topology, not angle.** SURF's ~5% octilinear vs any-angle gap means KiCad's 45°/arc geometry is not the bottleneck. The LLM should choose:
   - side-of-obstacle;
   - layer per group;
   - crossing locations;
   - which bus goes inner vs outer.

   It should not ask for free-angle routing except on flex or single-layer boards, where topological routers show their largest (vendor) wins.

3. **Persist topology to make placement–routing iteration cheap.** Store routes as topology (homotopy class plus vias), not coordinates. After the LLM or user nudges a component, re-tighten (rubber-band) and re-realize instead of re-routing, as TopoR and SURF do. This matters for an agent that alternates placement tweaks and routing.

4. **Treat escape as a solver call that can return "impossible".**
   - For BGAs and fine-pitch parts, call a flow model with correct diagonal capacity (Yan-Wong) for single-layer escape, or MonoSAT (built MIT with `-DGPL=OFF`) for multi-layer escape with via-type choices and diff-pair same-layer constraints.
   - Feed back either a solution or a *proof that N layers or this via technology is insufficient*. The LLM then proposes an HDI or stackup change, or pin swaps, to the user.
   - Runtimes of minutes to about an hour on 2000-pin parts are acceptable for a planning step.

5. **Make pin/bank/bit swapping a first-class, LLM-proposed action.**
   - The LLM reads datasheets and schematics to mark swappable groups: FPGA I/O banks, MCU alternate functions, DDR DQ bits within a byte lane, connector pins, resistor arrays.
   - An exact pin-assignment-plus-escape solver (Kong-Yan-Wong) or bus sequencing (LCIS) optimizes within those groups, then the LLM writes an ECO back to the schematic.
   - Geometry-only routers cannot do this. Vendor and practitioner evidence (TopoR, Olney) suggests large via savings.

6. **Untangle buses before routing.** When a bus's pin orders mismatch, run single-detour untangling (O(n)) to plan where the twist happens, ideally inside escape or near one end. The LLM decides whether bit swaps are allowed, which removes the twist entirely.

7. **Reserve meander area during planning; set meander SI rules explicitly.**
   - Convert match groups into extension budgets and allocate regions (BSG/LP-style area assignment) *before* bulk routing.
   - Constrain KiCad tuning patterns with spacing ≥ 3w and minimum corner radius, and avoid tight meanders (Tseng's crosstalk speedup).
   - KiCad master's new chain-level tuning fields should be checked for multi-segment nets.

8. **Expose a conflict-penalty schedule, and plan to learn it.**
   - Every production router (Specctra, Situs, gEDA, PcbRouter, Freerouting) negotiates conflicts across passes.
   - Expose the schedule (initial conflict cost, growth per pass, history weight, via-cost ramp) as a typed knob set.
   - Begin with LLM-chosen presets per board class (dense 2-layer, BGA 6-layer, RF). Later, train an offline-RL scheduler on logged runs; the VLSI results suggest 1.5–3× faster convergence. This is cheaper and more robust than per-step LLM control.

9. **Add OpenROAD PcbRouter as a second classical baseline.**
   - BSD-3, reads `.kicad_pcb`, routes diff pairs first, rip-up with escalating costs. OmniRouting measured it at 56% NRR on industrial designs, far above LLMs.
   - Its licence is friendlier than Freerouting's GPL for embedding.
   - Caveats: archived, KiCad 5.1.2 format, grid-based. Suitable as a fallback, a baseline and a code reference for median-point diff pairs.

10. **Provide pairwise-interaction conflict data to the LLM.** Compute toporouter-style pairwise scores (does routing net A alone make net B fail or detour, and by how much) for critical and medium nets. Hand the LLM this quantified conflict graph so its priority tiers are evidence-based, and let negotiation protect aggregate completion.

11. **Use "route everything, allow violations" as a fast feasibility probe.** A conflict-tolerant first pass works like TopoR's "instant 100%" or Situs and Specctra pass 1. A topological variant can estimate layer count and hotspot locations in seconds, before committing to slow detailed routing. The LLM uses the violation map to revise placement, layer budget or keep-outs.

12. **Score what practitioners complain about.** Extend the evaluation harness with metrics drawn from the experts above (via density, adjacent-layer parallel overlap, minimum-clearance bottleneck length, plane-reference changes without stitching, bends per net). Report them next to completion and DRC. These are the reasons humans reject DRC-clean autorouted boards.

### Gaps
- No experiment yet shows that an LLM-generated topology plan plus cut check beats Freerouting or PcbRouter alone on PCBWorld D3-B or OmniRouting. That should be the first ablation.
- The licence interplay needs review: gEDA toporouter (GPLv2+), MonoSAT (MIT only with `-DGPL=OFF`), PcbRouter (BSD-3), KiCad (GPL).
- Situs, TopoR and Allegro planning internals remain proprietary. The architectural lessons above come from their documentation, not their code.
