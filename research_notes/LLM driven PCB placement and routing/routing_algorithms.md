# Automatic PCB Routing Algorithms: Classical, PCB-Specific, ML/RL, Open-Source Engines, and Implications for an LLM-Driven KiCad Router

> Research notes, current to 2026-10-20. **How the sources were gathered:** arXiv, IEEE, ACM, OpenReview, vendor sites and forums were blocked from this sandbox (the proxy returned HTTP 403), and the shared web-search budget ran out partway through. The verified evidence therefore comes from: (a) the first few web-search result snippets; (b) primary source code and docs fetched from GitHub and GitLab (Freerouting master at commit c4755a8 of 2026-10-20, KiCad master, KiCad docs, KiCadRoutingTools, PCBWorld, OrthoRoute, tscircuit, PCBench, Horizon EDA); and (c) the full PCBWorld paper (KDD 2026 workshop, arXiv:2607.05915), read from the PDF in its GitHub repo. That paper's reference list supplied verified DOIs for many classic and recent papers.
>
> **Trust levels:** a claim with a URL was seen in that source this session. Content labelled "background knowledge (unverified this session)" sits in the Gaps sections and should be checked before it is relied on.
>
> **VLSI vs PCB:** every claim is labelled with the domain its evidence comes from.

---

## Q1. Classical routing algorithms (maze/A*, line-probe, gridless/shape-based, negotiated congestion, rip-up-and-reroute, topological, sequential vs concurrent, net ordering)

### Takeaway
Every production-grade open-source PCB router found in 2026 is still a **sequential, cost-driven path search with rip-up-and-reroute and a post-route optimizer**:
- Freerouting runs A* over convex "expansion rooms" in continuous space.
- KiCadRoutingTools runs a Rust grid A* on an octilinear grid.
- KiCad's PNS is a local walkaround/shove engine, not a global router.

Negotiated congestion (PathFinder) appears in PCB tools only in niche form (OrthoRoute), and it scored poorly on ordinary boards. In the one 2026 head-to-head study, the decades-old classical approach (Freerouting) remained the strongest baseline on real boards.

### Cited Findings

**Maze/Lee and A***
- Lee's 1961 algorithm, "An Algorithm for Path Connections and Its Applications" (IRE Trans. Electronic Computers EC-10(3):346–365), is the canonical root of maze routing. PCBWorld cites it as one of the "decades-old heuristics" that industry rule-based routers are still rooted in. — [Lee 1961, doi:10.1109/TEC.1961.5219222](https://doi.org/10.1109/TEC.1961.5219222); [PCBWorld paper](https://arxiv.org/abs/2607.05915)
- Freerouting's own design notes summarize Lee/maze routing (1961) as "simple, O(N²), no congestion awareness". — [Freerouting escape_congestion_research.md](https://github.com/freerouting/freerouting/blob/master/docs/research/escape_congestion_research.md)
- KiCadRoutingTools (KRT) is a "fast Rust-accelerated A* autorouter for KiCad PCB files". It does grid-based, octilinear (H/V/45°) multi-layer routing with automatic vias, and its native Rust core is "~10× faster than pure Python". — [KRT README](https://github.com/drandyhaas/KiCadRoutingTools)

**Shape-based / gridless (expansion rooms)**
- Freerouting works on a continuous plane, not a grid. Free space is split into convex polygonal "expansion rooms", and the core search is A* over rooms through "doors", with cost = geometric distance + via cost. A path may cross a door anywhere along its width rather than at a quantized cell. This comes from a secondary blog plus commit notes of a Python port. — [tinycomputers.io blog (search snippet)](https://tinycomputers.io/posts/the-mathematics-of-pcb-trace-routing.html); [freeroute port commit](https://git.supported.systems/warehack.ing/freeroute/src/commit/6a24ffc540f04216b05e0cf471aeef85c77a8dee)
- The upstream Freerouting source corroborates this. The `autoroute.expansion` package contains `FreeSpaceExpansionRoom`, `ObstacleExpansionRoom`, `ExpansionDoor`, `TargetItemExpansionDoor`, `Sorted45DegreeRoomNeighbours` and `SortedOrthogonalRoomNeighbours`, and `autoroute.maze` contains `MazeSearchEngine`, `MazeRipupResolver` and `MazeTraceShover`. The architecture doc describes the package as "Expansion rooms, doors, and angle-specific room-neighbour calculations used by maze routing". — [Freerouting expansion package](https://github.com/freerouting/freerouting/tree/master/src/main/java/app/freerouting/autoroute/expansion); [architecture.md](https://github.com/freerouting/freerouting/blob/master/docs/architecture.md)

**Rip-up and reroute**
- The classic reference is Dees & Karger, "Automated rip-up and reroute techniques", DAC 1982. — [doi:10.1145/800263.809241](https://doi.org/10.1145/800263.809241) (cited in [PCBWorld](https://arxiv.org/abs/2607.05915))
- Freerouting's maze search can rip up obstacles at a cost:
  - The rip-up cost scales with the obstacle trace's half-width and contact count, and is divided by the detour.
  - Rip-up costs are randomized on later passes (`ripupPassNo >= 4 && ripupPassNo % 3 != 0`).
  - Escalation is global and linear (`ripup_costs = startRipupCosts * (passNo + 1)`), which the maintainers flag as "sub-optimal".

  — [MazeRipupResolver.java](https://github.com/freerouting/freerouting/blob/master/src/main/java/app/freerouting/autoroute/maze/MazeRipupResolver.java); [escape_congestion_research.md](https://github.com/freerouting/freerouting/blob/master/docs/research/escape_congestion_research.md)
- KRT's rip-up flow:
  - A full A* failure returns the blocked "frontier", and early probes (5000 iterations) detect stuck searches.
  - Frontier cells are attributed to previously routed nets, and blockers are ranked by unique/near-endpoint/shared cells.
  - Selection options include `near-target`, `bidir` (blockers seen from both search directions) and `mincut`. `mincut` converts rippable copper to a high soft cost and re-routes once, so the copper the path crosses is the "true joint cut".
  - Diff pairs are ripped and restored as a unit.

  — [KRT rip-up-reroute.md](https://github.com/drandyhaas/KiCadRoutingTools/blob/main/docs/rip-up-reroute.md)
- Linsker's 1984 "iterative-improvement penalty-function-driven wire routing system" (IBM JRD) is an early example of soft-penalty iterative routing. — [doi:10.1147/RD.285.0613](https://doi.org/10.1147/RD.285.0613)

**Negotiated congestion (PathFinder)**
- PathFinder (McMurchie & Ebeling, FPGA 1995) is a negotiation-based router. — [doi:10.1145/201310.201328](https://doi.org/10.1145/201310.201328)
- OrthoRoute applies PathFinder to PCBs:
  - Routing graph: nodes are via-capable grid intersections, edges are trace segments, and each is a shared resource.
  - Iteration 1 routes greedily. Later iterations raise the cost of overused edges and rip up the worst offenders until nothing is over-subscribed.
  - Geometry is a "Manhattan lattice": H-only and V-only layers with blind/buried vias.
  - It uses a CUDA SSSP ("parallel Dijkstra") per net, but "nets are still routed in sequence on a shared congestion map".

  — [OrthoRoute README](https://github.com/bbenchoff/OrthoRoute)
- OrthoRoute's author states it is "not a general-purpose PCB autorouter" and is meant for "extremely large, dense, highly regular multilayer backplanes and BGA escape patterns". On PCBWorld's benchmarks it scored 1% clean-pass on synthetic D2 and 2% (routability 51%) on 99 open-source D3-A boards. — [OrthoRoute README](https://github.com/bbenchoff/OrthoRoute); [PCBWorld Table 3](https://arxiv.org/abs/2607.05915)

**Successive approximation / hypergraph (concurrent-ish)**
- tscircuit's MIT-licensed `capacity-autorouter`:
  - It "is composed of hundreds of algorithms organized in a Pipeline" and "uses successive approximation and Hypergraphs rather than sequential routing".
  - A "capacity mesh" is recursively subdivided (`capacityDepth`, auto-computed for a "target minimum capacity of 0.5").
  - Inputs include optional bus groups.

  — [tscircuit-autorouter README](https://github.com/tscircuit/tscircuit-autorouter); [hypergraph blog post (linked, not fetched)](https://blog.autorouting.com/p/hypergraph-autorouting)

**Net ordering heuristics**
- KRT's default ordering is MPS (Maximum Planar Subset):
  - Each chip's boundary is "unrolled" to a [0,1] position.
  - Two nets cross if their source order is inverted relative to target order. Crossing pairs form a conflict graph.
  - The net with the fewest active conflicts is picked greedily, shorter routing-aware distance first.
  - Alternatives: "inside-out" (for BGA escape), "bus" (bus members middle-out) and original order.

  — [KRT net-ordering.md](https://github.com/drandyhaas/KiCadRoutingTools/blob/main/docs/net-ordering.md)
- Freerouting fanout ordering:
  - Components are processed most-SMD-pins first; pins within a component outermost-first.
  - The maintainers note this "is correct for a single isolated BGA" but "breaks down for adjacent dense components".
  - The batch autorouter uses net-id order, which "tries the cheap items first".

  — [escape_congestion_research.md](https://github.com/freerouting/freerouting/blob/master/docs/research/escape_congestion_research.md); [large-board-autorouter-performance.md](https://github.com/freerouting/freerouting/blob/master/docs/research/large-board-autorouter-performance.md)
- Learned net ordering for VLSI detailed routing exists, e.g. Zhou et al., "Transformer-based RL for Net Ordering in Detailed Routing", IJCAI 2025 (**VLSI**). — [doi:10.24963/ijcai.2025/1055](https://doi.org/10.24963/ijcai.2025/1055)

**Scale/runtime of classical PCB routers (real boards)**
- Freerouting 2.5.0-RC9 profiles:

  | Board | Size | Result |
  |---|---|---|
  | Aleste-520EX | 2210 pins, 2 layers | One autorouter pass took 1748 s and went from 1620 to 882 incompletes; the optimizer never started |
  | logicbone | 8 layers | Fanout took 899 s, then 3 s of autorouter with the incomplete count unchanged |
  | si31-3 | — | Fully routed; router 640 s, optimizer 807 s |
  | perf++ | 1383 pins | Router finished in 32 s |

  "Pin count does not separate the slow boards from the fast ones." A multi-threaded clone-and-shuffle pass was removed because it never beat single-thread enough. — [large-board-autorouter-performance.md](https://github.com/freerouting/freerouting/blob/master/docs/research/large-board-autorouter-performance.md)
- KRT integration test timings:

  | Net group | Routed | Time |
  |---|---|---|
  | FTDI single-ended | 47/47 | 8.6 s |
  | LVDS diff pairs | 28/28 | ~29 s per batch (10–12 M A* iterations) |
  | DDR single-ended | 51/51 | 6.2 s |

  — [KRT README §Performance](https://github.com/drandyhaas/KiCadRoutingTools)

### Inferences
- Gridless room-based search (Freerouting) and fine-grid octilinear A* (KRT) are the only approaches with proven real-board completion in open source. PathFinder-style negotiation shows up only on lattice-structured problems. For general boards, negotiation is better used as a **global/coarse planning layer** (capacity tiles) than as the detailed router.
- Net ordering remains the biggest lever in sequential routers, and it is exactly the kind of decision an LLM can make from net semantics. Inferring "this is DDR, route byte lanes middle-out" cannot be done from geometry alone.

### Gaps
- **Background knowledge (unverified this session; sources blocked).** None of the following could be fetched or verified:
  - Hightower's line-probe router (DAC 1969, "A solution to line-routing problems on the continuous plane").
  - Mikami-Tabuchi line search.
  - Channel routers (left-edge, dogleg, Yoshimura-Kuh) and switchbox routers.
  - Dai/Dayan/Staepelaere's SURF rubber-band topological sketch router (DAC ~1991).
  - TopoR (Eremex): any-angle, topology-first, arc-based router.
  - gEDA PCB's GSoC "toporouter" (Anthony Blake, based on rubber-band/SURF ideas).

  Their mechanics (line probes, channel density, rubber-band sketch then geometric realization, continuous arcs) are well known but uncited here.
- No quantitative runtime or quality comparison of topological routers (TopoR) against maze routers on modern boards was obtained.

---

## Q2. PCB-specific research: BGA escape routing, any-angle routing, length matching/meanders, differential pairs, layer assignment, via minimization, bus routing

### Takeaway
PCB-specific academic work splits the problem into specialized sub-problems, each with an exact or near-exact formulation:
- escape routing as network flow / ILP / SAT;
- length matching as resource allocation plus meander synthesis;
- diff pairs as coupled centerline routing.

None of this is integrated into open-source general routers except in simplified heuristic form (KRT, KiCad's interactive tuning tools). That gap is the opportunity for an orchestration layer.

### Cited Findings

**Escape routing (BGA/area array)**
- Ozdal et al. carried out the first well-known simultaneous escape routing (SER) study, using a graph-based approach to find maximal escape nets. It worked best when the pins of two components were closely aligned. They also proposed a randomized algorithm for large instances; a 2017 paper criticizes its monotonic-escape limit. — [Mobility-based Net Ordering for SER (SAI 2017)](https://saiconference.com/Downloads/Volume8No7/Paper_62-Mobility_based_Net_Ordering_for_Simultaneous_Escape_Routing.pdf)
- Yan & Wong, "A correct network flow model for escape routing", DAC 2009. — [citation in NTHU thesis record](https://etd.lib.nthu.edu.tw/detail/18cb47061231fb21a2463eccf304494a)
  - Freerouting's notes summarize it as showing "earlier flow models were wrong for diagonal routing capacity — an important correctness note for … 45° routing". — [escape_congestion_research.md](https://github.com/freerouting/freerouting/blob/master/docs/research/escape_congestion_research.md)
- Wang, Shi & Cheng (ICCAD 2006) use a network-flow model to find the bottleneck of routable pins in area-array escape routing. — [ICCAD'06 paper 10C.3](https://www.cecs.uci.edu/~papers/iccad06/papers/10C_3.pdf)
- Sattar & Ignjatovic (2016) propose flow models for different inter-pin capacities and a linear network-flow optimization that solves net ordering and net escape together; they report routing more nets than prior algorithms. — [Simultaneous Escape Routing using Network Flow Optimization](https://jml.um.edu.my/index.php/MJCS/article/view/7006)
- Freerouting's summary of escape-routing evolution (secondary): maze → max-flow/min-cost flow (2000s) → multi-commodity min-cost flow for ordered escape (2009–2016) → SAT solver (ICCAD 2016, multiple via types at once) → genetic algorithms → RL/MCTS. It cites "MCMCF-Router (ACM TODAES 2024)" as scaling "to 2000+ pins with formal capacity guarantees". — [escape_congestion_research.md](https://github.com/freerouting/freerouting/blob/master/docs/research/escape_congestion_research.md)
- FanoutNet (AAAI 2023) is a neural PCB fanout automation method using deep RL (**PCB**). — [doi:10.1609/aaai.v37i7.26030](https://doi.org/10.1609/aaai.v37i7.26030); [AAAI PDF](https://ojs.aaai.org/index.php/AAAI/article/view/26030/25802)
- Practitioner tooling gap at fine pitch: at 0.4 mm pitch with 0.2 mm pads, "a standard 0.45 mm via often cannot physically fit", so "most automated fanout tools (including KiCadRoutingTools' own `bga_fanout.py`) fall back to a smaller, sub-spec via". malakaRouter3 instead searches outward in rings for a legal standard-via site 0.3–1.5 mm away. — [malakaRouter3 README](https://github.com/Ivshti/malakaRouter3)
- Freerouting's own fanout has "No congestion analysis of any kind". It places a via "at first feasible location" ("Poor via spread"), and permanently blocked pins were retried every pass up to 20 passes. — [escape_congestion_research.md](https://github.com/freerouting/freerouting/blob/master/docs/research/escape_congestion_research.md)

**Length matching / meanders**
- Ozdal & Wong, "A length-matching routing algorithm for high-performance PCBs" (IEEE TCAD 2006): a Lagrangian-relaxation framework allocates extra routing resources around nets to meet min-max length bounds, with the bounds built into routing. — [HKBU scholars record](https://scholars.hkbu.edu.hk/en/publications/a-length-matching-routing-algorithm-for-high-performance-printed-/)
- "ILP-based Alleviation of Dense Meander Segments with Prioritized Shifting and Progressive Fixing in PCB Routing" (title only seen). — [arXiv:1705.04984](https://arxiv.org/pdf/1705.04984)
- "Obstacle-Aware Length-Matching Routing for Any-Direction Traces in PCB" (2024 preprint):
  - Splits the task into region assignment plus meandering, keeping the original routing.
  - Adds Multi-Scale Dynamic Time Warping (MSDTW) for differential pairs.
  - Venue unconfirmed.

  — [arXiv:2407.19195](https://arxiv.org/html/2407.19195v1)
- KiCad interactive tuning:
  - Three tools: single-track length, diff-pair length, diff-pair skew. Both length and time-domain (delay) tuning are supported.
  - Targets come from custom DRC rules. Patterns are persistent, editable objects.
  - Limitations: tools "only support tuning the length of point-to-point nets between two pads", and diff-pair tuning applies "only to the coupled portions".

  — [KiCad docs, pcbnew_editing.adoc](https://gitlab.com/kicad/services/kicad-doc/-/blob/master/src/pcbnew/pcbnew_editing.adoc)
- KRT length/time matching:
  - Done after routing: trombone meanders are added to shorter routes until within tolerance of the longest, counting via barrels and pad-to-die length.
  - Options: auto DDR4 byte-lane grouping, propagation-delay matching (microstrip vs stripline), intra-pair P/N matching and AC-coupled pair matching.
  - For multipoint nets, the longest MST edge is routed and meandered before taps are added.

  — [KRT length-matching.md](https://github.com/drandyhaas/KiCadRoutingTools/blob/main/docs/length-matching.md)
- Freerouting master now has a `NetMeanderConstraint` rule model with min/max amplitude, spacing, fillet/chamfer corner style and single-sided option. Defaults: 0.2–1.0 mm amplitude; 0.6 mm spacing for single tracks, 1.0 mm for diff pairs. — [NetMeanderConstraint.java](https://github.com/freerouting/freerouting/blob/master/src/main/java/app/freerouting/rules/NetMeanderConstraint.java)

**Differential pairs**
- Lin, Merrill, Wu, Holtz & Cheng, "A Unified PCB Routing Algorithm With Complicated Constraints and Differential Pairs", ASP-DAC 2021 (**PCB**). — [doi:10.1145/3394885.3431568](https://doi.org/10.1145/3394885.3431568)
- KRT diff pairs are routed as a centerline plus offset:
  - "Pose-based A*" searches (x, y, θ) space with a Dubins-path heuristic.
  - Setback positions are scanned over 9 angles, and paths are simplified before P/N perpendicular offsets are generated.
  - Approach/exit tracks at vias keep P/N parallel. GND return vias and per-layer impedance-controlled widths are supported.
  - Automatic polarity resolution swaps pads only if enabled.

  — [KRT differential-pairs.md](https://github.com/drandyhaas/KiCadRoutingTools/blob/main/docs/differential-pairs.md); [KRT README](https://github.com/drandyhaas/KiCadRoutingTools)
- KiCad's interactive diff-pair router takes the gap from design rules (net classes). It "will attempt … to minimize the length of track where the differential pair is not coupled" and handles via placement for pairs. — [KiCad docs](https://gitlab.com/kicad/services/kicad-doc/-/blob/master/src/pcbnew/pcbnew_editing.adoc)
- Freerouting master models diff pairs (`DifferentialPair` record with coupled spacing and max skew, plus `DifferentialPairDetector`). However, in the source tree these classes are referenced only from `rules`, `io.specctra.parser` and `HeadlessBoardManager`, not from the `autoroute` packages. — [DifferentialPair.java](https://github.com/freerouting/freerouting/blob/master/src/main/java/app/freerouting/rules/DifferentialPair.java)

**Any-angle / any-direction**
- Kohira & Takahashi (ASP-DAC 2012) formulate any-angle gridless routing as nonlinear programming solved by a quasi-Newton method, for PCB and package routing. — [ASP-DAC 2012 session 2B](https://www.aspdac.com/aspdac2012/archive/program/2B_abst.html)
- KiCad: Shove and Walk Around modes "always create horizontal, vertical, and 45-degree" tracks; any-angle requires Highlight Collisions mode plus Free Angle Mode. — [KiCad docs](https://gitlab.com/kicad/services/kicad-doc/-/blob/master/src/pcbnew/pcbnew_editing.adoc)
- Chen et al. (2023), "A Novel Global Routing Algorithm for PCBs Based on Triangular Grid" (Electronics 12(24)) (**PCB**). — [doi:10.3390/electronics12244942](https://doi.org/10.3390/electronics12244942)

**Bus routing**
- KRT `--bus`: nets with clustered endpoints are detected as a bus and routed middle-out. Each net gets a cost bonus (default 5000) for running parallel within 5 mm of its neighbor's track. — [KRT bus-routing.md](https://github.com/drandyhaas/KiCadRoutingTools/blob/main/docs/bus-routing.md)
- tscircuit's input format carries optional `buses` groups whose metadata is preserved in the output. — [tscircuit-autorouter README](https://github.com/tscircuit/tscircuit-autorouter)

**Layer assignment / via minimization**
- KRT has upfront layer-swap optimization (`layer_swap_optimization.py`) and a fallback layer swap on failure. Freerouting uses per-layer preferred directions with trace costs of 1.0 (preferred) vs 2.5 (undesired) and `via_costs` = 50 (`plane_via_costs` = 5). — [KRT routing-architecture.md](https://github.com/drandyhaas/KiCadRoutingTools/blob/main/docs/routing-architecture.md); [Freerouting settings.md](https://github.com/freerouting/freerouting/blob/master/docs/settings.md)
- Freerouting's optimizer V2 score measures "Excess wire length, vias, and bends versus placement-derived lower bounds". Completeness and DRC are vetoes, not score terms. — [Freerouting scoring.md / architecture.md](https://github.com/freerouting/freerouting/blob/master/docs/scoring.md)

### Inferences
- Escape routing and length matching are the most "formalizable" PCB sub-problems: flow/ILP for escape; region allocation plus meander synthesis for length. They are good candidates for deterministic solvers that an LLM *configures* (pitch, via type, escape layer budget, match groups, tolerances) rather than performs.
- Diff-pair routing as a coupled centerline in pose space (KRT) is simple, reproducible and well suited to automation. KiCad's DP placer plus skew tuner can refine afterwards.
- Freerouting appears to parse diff-pair and meander constraints without enforcing them during routing. Inference from code structure; not confirmed by maintainers.

### Gaps
- Could not access the full text of the Ozdal-Wong SER/layer-assignment papers (TCAD 2006), the Yan-Chang/Yan-Wong escape and bus papers, Kubo/Kohira "CAFE router", Tan et al., or 2022–2026 ICCAD/DAC PCB papers. Runtimes, benchmark sizes and exact formulations are therefore missing.
- Could not verify the "MCMCF-Router (TODAES 2024)" or "SAT-solver (ICCAD 2016)" papers beyond Freerouting's secondary summary.
- No evidence was found of commercial PCB-specific constrained routers (Cadence Allegro auto-interactive breakout/trunk routing, Altium ActiveRoute, Siemens Sketch Router, Zuken topology router), because vendor sites were blocked.

---

## Q3. ML/RL routing: DeepPCB, RL papers, MCTS, GNN ordering, diffusion/transformers, LLM agents, and VLSI-to-PCB transfer

### Takeaway
The strongest 2026 evidence (PCBWorld, KDD'26 workshop) shows:
- Learned agents are competitive with classical routers only on small boards, and only when they **act through a real routing engine's native operations** (KiCad PNS) rather than moving cell-by-cell on a grid or emitting geometry.
- Freerouting still wins on medium boards. All LLM agents scored 0% clean-pass on 10 medium real boards.
- Most published ML "routing" is VLSI, or uses ML to steer a classical router (net order, fanout).

### Cited Findings

**PCBWorld (LG AI Research, 2026), the key head-to-head** — [arXiv:2607.05915](https://arxiv.org/abs/2607.05915); [GitHub](https://github.com/LGAI-Research/PCBWorld)
- **Engine and API:** a Gymnasium environment wrapping KiCad 9.0.8's push-and-shove router. It exposes 58 Python APIs: 14 reproduce the core routing API of `PNS::ROUTER`, 28 wrap KiCad DRC and board-state extraction, and 16 are utilities. It runs headless and vectorized.
- **Action space:** `net_select`, `start_route`, `make_line(p_end, routing_mode)`, `make_via`, `finish`, `net_end`.
  - `routing_mode` selects push_n_shove, walkaround or mark-obstacles.
  - `finish` invokes PNS to complete to the nearest unconnected pad on the current layer.
  - `p_end` is chosen from engine-provided candidates: pad centers and track/via endpoints.
- **Objective:** min λ_w·wirelength + λ_v·vias subject to zero DRVs. The reward is a potential function Φ with a concave DRV penalty from KiCad's DRC (38 checks).
- **Datasets:** D1 grid (Jumanji Connector replica), D2 synthetic gridless (2 layers, 4–6 nets), and D3 with 679 real open-source boards derived from PCBench:
  - D3-A: 2–13 nets, 6–31 pads
  - D3-B: 5–42 nets, 31–100 pads
  - D3-C: up to 451 nets, 2,103 pads, 8 layers
- **Results (Table 3; CP = clean pass, i.e. fully connected with zero DRVs):**

  | Method | D2 CP | D3-A CP (99 boards) | D3-A time | D3-B CP (10 boards) | D3-B time |
  |---|---|---|---|---|---|
  | Freerouting 2.1.0 | 1.00 | 0.80 | 7.09 s | **0.78** | 9.94 s |
  | KRT (version at the time) | 1.00 | 0.74 | 0.65 s | 0.20 | — |
  | OrthoRoute | 0.01 | 0.02 | — | 0.00 | — |
  | PPO transformer (trained only on synthetic D2) | 1.00 | 0.86 | 1.83 s | 0.45 | — |
  | PPO without `finish` action | 1.00 | **0.94** | — | 0.42 | — |
  | GPT-5.4 interactive | 0.96 | 0.65 | 231 s | 0.00 | 866 s |
  | GPT-5.4-mini interactive | 0.58 | 0.28 | — | 0.00 | — |
  | Qwen3.5-397B interactive | 0.33 | 0.34 | — | 0.00 | — |

  D3-C is "reserved … as a challenge split".
- **Engine engagement matters (Table 4, GPT-5.4 on D3-A):**

  | Mode | CP | Mean DRV |
  |---|---|---|
  | Interactive (per-step engine feedback) | 0.65 | 1.31 |
  | Plan-and-execute (whole action sequence open-loop) | 0.19 | 16.28 |
  | Engine-free (emit raw `.kicad_pcb` segments) | 0.02 | 34.58 |

  For GPT-5.4-nano engine-free, no rollout even loaded as a valid board on 10% of boards.
- **Grid-action RL breaks down at scale:** A2C (Jumanji) collapses by grid 100 and Sable by grid 200, while engine-action PPO stays near-perfect from grid 50 up. The decision horizon is "tied to routed segments and does not grow with grid resolution".
- **Wirelength vs human reference (Table 21, D3-A):** Freerouting's mean wirelength (156 mm) and vias (0.74) were *lower* than the human reference (170 mm, 1.18 vias), yet its CP was only 0.80.
- **PCBWorld's taxonomy of prior RL formulations:**
  1. Cell-by-cell grid movement (Jumanji Connector, He et al. MCTS+DRL, Liao et al. DRL global routing, Sable).
  2. Steering a fixed router via net order, routing pattern or fanout locations. This "cap[s] quality at the router's ceiling".

**Prior ML-for-PCB routing work (verified citations via PCBWorld's references)**
- He, Li, Tian & Bao, "Circuit Routing Using Monte Carlo Tree Search and Deep RL", VLSI-DAT 2022. — [doi:10.1109/VLSI-DAT54769.2022.9768074](https://doi.org/10.1109/VLSI-DAT54769.2022.9768074)
- Youbiao He, PhD dissertation "Towards Automated PCB Routing: Leveraging ML and Heuristic Techniques" (Iowa State, 2024). — [doi:10.31274/td-20240617-74](https://doi.org/10.31274/td-20240617-74)
- Liao, Pan & Chiang, "Automation of PCB Autorouting via World-Model RL and Freerouting Integration", Expert Systems with Applications 311 (2026). It is an example of RL steering Freerouting. — [doi:10.1016/j.eswa.2026.131424](https://doi.org/10.1016/j.eswa.2026.131424)
- Liao et al., "A Deep RL Approach for Global Routing", J. Mech. Design 2020 (grid-based; evaluated on synthetic problems). — [doi:10.1115/1.4045044](https://doi.org/10.1115/1.4045044); [arXiv:1906.08809](https://arxiv.org/pdf/1906.08809.pdf)
- Liao et al., "Attention Routing: Track-Assignment Detailed Routing Using Attention-Based RL", IDETC 2020. — [doi:10.1115/DETC2020-22219](https://doi.org/10.1115/DETC2020-22219)
- Bonnet et al., "Jumanji" (ICLR 2024), whose Connector environment is a grid routing toy problem. Mahjoub et al., "Sable" (ICML 2025), MARL on Connector. — [Sable, PMLR v267](https://proceedings.mlr.press/v267/mahjoub25a.html)
- PCB-Bench (ICLR 2026) benchmarks LLMs on PCB placement and routing *interpretation*. Per PCBWorld it "evaluates an LLM's board interpretation but not its routing ability". — [OpenReview Q5QLu7XTWx](https://openreview.net/forum?id=Q5QLu7XTWx)
- PCBEnv, "A reinforcement learning environment for PCB routing" (C++, small GitHub repo, description only). — [chrisbmr/PCBEnv](https://github.com/chrisbmr/PCBEnv)

**InstaDeep DeepPCB**
- Launched in November 2019 as "first pure AI-powered PCB router":
  - Uses deep RL and "avoids arbitrary heuristics built by human experts".
  - Built on TensorFlow, works with KiCad, and returns results in under 24 h in Specctra session format.

  — [InstaDeep launch post](https://instadeep.com/2019/11/instadeep-launches-first-pure-ai-powered-printed-circuit-board-pcb-router/)
- During the beta, users placed components by hand; the beta supported 2 layers and up to 150 nets. — [mikrocontroller.net news](https://www.mikrocontroller.net/news/deeppcb-ki-basierter-autorouter)
- Cloud TPUs improved DeepPCB agent training throughput and routing quality. — [Google Cloud blog](https://cloud.google.com/blog/products/compute/instadeep-performs-reinforcement-learning-on-cloud-tpus)
- Discussed on the TWIML podcast. — [TWIML #365](https://twimlai.com/podcast/twimlai/automating-electronic-circuit-design-deep-rl-karim-beguir)

**Quilter**
- A third-party API profile describes Quilter as "a physics-driven AI platform that automates PCB placement and routing", which "using reinforcement learning … converts a schematic into multiple fabrication-ready layout candidates". This is a third-party description, not a primary source. — [api-evangelist/quilter](https://github.com/api-evangelist/quilter)

**VLSI ML routing (transferability caveat)**
- DeepPlace/joint P&R (NeurIPS 2021). — [paper](https://proceedings.neurips.cc/paper/2021/file/898aef0932f6aaecda27aba8e9903991-Paper.pdf)
- PRNet "Policy-gradient Placement and Generative Routing Neural Networks" (NeurIPS 2022). — [OpenReview](https://openreview.net/pdf?id=uNYqDfPEDD8)
- "A Neural Network that Routes ICs" (DAC 2020 LBR). — [IEEE 9218598](https://ieeexplore.ieee.org/stamp/stamp.jsp?tp=&arnumber=9218598)
- DRL global routing with a Nesterov quasi-Newton method (NOLTA 2021). — [arXiv:2010.09465](https://arxiv.org/pdf/2010.09465.pdf)
- (All four entries above are listed in [Thinklab-SJTU/awesome-ai4eda](https://github.com/Thinklab-SJTU/awesome-ai4eda).)
- XRoute (2023): an RL environment (DQN/PPO/A3C/MCTS baselines) that trains agents "to order and route all nets" for **VLSI detailed routing** on OpenROAD. — [arXiv:2305.13823](https://arxiv.org/pdf/2305.13823); [xroute_env](https://github.com/xplanlab/xroute_env)
- Chen et al., "RL Guided Detailed Routing for Custom Circuits", ISPD 2023 (**analog/custom IC**). — [doi:10.1145/3569052.3571874](https://doi.org/10.1145/3569052.3571874)
- RL-accelerated detailed routing convergence (2025 preprint, **VLSI**). — [arXiv:2512.03594](https://arxiv.org/pdf/2512.03594)
- Overview: "Towards ML for Placement and Routing in Chip Design: a Methodological Overview". — [arXiv:2202.13564](https://arxiv.org/pdf/2202.13564)

### Inferences
- **Transfer from VLSI is limited.** VLSI routing is gridded, track-based and preferred-direction, with millions of near-identical 2-pin nets and global/detailed separation. PCB routing is gridless, has heterogeneous pads, few layers, through-hole vias that block all layers, and mixed electrical constraints. The VLSI ideas that do transfer are congestion maps (RUDY/G-cell overflow), learned net ordering, and two-stage global→detailed decomposition. Generative "draw the route image" models (PRNet-style) do not transfer: they cannot guarantee DRC-clean geometry, as PCBWorld's engine-free results show for LLMs.
- RL steering of Freerouting and RL engine-action agents are complementary. A compact PPO policy that picks waypoints and shove/walkaround modes is ~100× faster than LLM step-by-step control (1.83 s vs 231 s on D3-A). The LLM is better used at net/group level.

### Gaps
- Could not verify 2023–2026 diffusion/transformer routing papers for VLSI (e.g. HubRouter, NeuralSteiner, diffusion-based global routers) or any GNN-based PCB net-ordering paper. Sources were blocked.
- No primary technical description of DeepPCB's architecture, reward or 2024–2026 product status was obtained (no NeurIPS 2019 paper text).
- No primary information on Quilter, Flux.ai or Cadence/Siemens AI routing features was obtained.
- PCBWorld describes D3 as "679 real open-source boards" derived from PCBench, but the PCBench README says it contains "164 printed circuit boards". The reason (corpus growth, version differences, or counting augmented/converted boards) is unresolved. — [PCBench README](https://github.com/PCBench/PCBench)

---

## Q4. Freerouting internals, KiCad's PNS push-and-shove router, and whether automation can drive push-and-shove programmatically

### Takeaway
**Freerouting** (GPL, Java, Specctra DSN→SES) runs a three-stage pipeline: fanout, batch maze autorouter with rip-up, then a keep-or-undo optimizer. Its search is A* over expansion rooms. By 2026 it also offers a REST API, an MCP server and KiCad IPC integration work.

**KiCad PNS** is a local engine: walkaround via convex hulls in cw and ccw directions, shove via hull sets and re-walking obstacle lines, and corner-cost line optimization. It is **not** a global autorouter.

PNS **can** be driven programmatically:
1. PCBWorld-Engine already exposes `PNS::ROUTER` routing calls to Python (GPLv3 KiCad fork).
2. The KiCad IPC API can trigger router actions such as `pcbnew.InteractiveRouter.Autoroute` and `OptimizeSelected` through `RunAction`, flagged "for low-level prototyping".
3. Horizon EDA shows the router can be embedded as a library.

### Cited Findings

**Freerouting pipeline and settings**
- Pipeline: "DSN input → parser → board and rule model → autorouter → design-rule checking → SES output". Stage order: fanout → autorouter passes → optimizer passes. — [architecture.md](https://github.com/freerouting/freerouting/blob/master/docs/architecture.md)
- **Autorouter:** "solves missing connections one at a time", may "temporarily rip up nearby conflicting traces or vias", and stops a pass series when no useful progress is made. — [architecture.md](https://github.com/freerouting/freerouting/blob/master/docs/architecture.md)
- **Optimizer:** picks an improvable trace, rips up and reroutes it locally, keeps the change only if better, otherwise undoes it. In multi-threaded mode it may try several candidates. — [architecture.md](https://github.com/freerouting/freerouting/blob/master/docs/architecture.md)
- **Default costs:** `via_costs` 50, `plane_via_costs` 5, `start_ripup_costs` 100, preferred-direction trace cost 1.0 vs undesired 2.5, autorouter `max_passes` 100, fanout `max_passes` 20. Settings include per-layer `routable` and `preferred_direction_horizontal`. — [settings.md](https://github.com/freerouting/freerouting/blob/master/docs/settings.md)
- **Board scores (V2):** a router score (0–1000) penalizes incomplete connections and DRC violations scaled by D = max(1, pins × signal layers). A separate optimizer score measures excess length/vias/bends against lower bounds. — [scoring.md](https://github.com/freerouting/freerouting/blob/master/docs/scoring.md)
- **Interfaces:** GUI, CLI (`-de in.dsn -do out.ses`, `-inc` to ignore net classes), REST API, and an MCP server (`npx @freerouting/freerouting-mcp-server`) for "LLM-based coding assistants". The architecture includes a KiCad JSON writer. Integrations: KiCad, Fusion, Target3001!, EasyEDA, tscircuit, pcb-rnd. — [README](https://github.com/freerouting/freerouting); [MCP.md](https://github.com/freerouting/freerouting/blob/master/docs/API/MCP.md)
- **Current version and lineage:** the nightly benchmark runs 2.6.0-RC4 (Oct 2026). The maintainers are porting improvements from a C# port ("freerouting.net" by Erik Gavriluk). — [repo commit log](https://github.com/freerouting/freerouting); [migration doc](https://github.com/freerouting/freerouting/blob/master/docs/migrating_Eriks_improvements_part_2.md)
- **DSN fidelity caveats:**
  - KiCad DSN export omits copper-to-edge clearance (Issue 558).
  - Headless `pcbnew.ImportSpecctraSES` on KiCad 10.0.2 returned false for Freerouting SES.
  - The IPC API "exposes full live design rules", unlike DSN.

  — [Freerouting pcbench README](https://github.com/freerouting/freerouting/blob/master/scripts/pcbench/README.md); [kicad_ipc_api_research.md](https://github.com/freerouting/freerouting/blob/master/docs/research/kicad_ipc_api_research.md)
- **KiCad 11 API round-trip:** `RunBoardJobExportSpecctraDsn` and `ImportSpecctraSession` ("Since: 11.0"). The import repositions footprints, deletes unlocked tracks/vias, and adds session tracks/vias, skipping locked items. This enables a closed loop entirely over the API. — [board_commands.proto](https://gitlab.com/kicad/code/kicad/-/blob/master/api/proto/board/board_commands.proto); [board_jobs.proto](https://gitlab.com/kicad/code/kicad/-/blob/master/api/proto/board/board_jobs.proto)

**KiCad PNS ("KiRouter") internals**
- Origin: "KiRouter - a push-and-(sometimes-)shove PCB router", Copyright CERN 2013–2014, author Tomasz Wlostowski. — [pns_walkaround.cpp](https://gitlab.com/kicad/code/kicad/-/blob/master/pcbnew/router/pns_walkaround.cpp)
- **Modes and settings:** `RM_MarkObstacles`, `RM_Shove`, `RM_Walkaround`; optimizer effort `OE_LOW`/`OE_MEDIUM`/`OE_FULL`; shove and walkaround iteration and time limits; free-angle mode; corner mode (`DIRECTION_45::CORNER_MODE`). — [pns_routing_settings.h](https://gitlab.com/kicad/code/kicad/-/blob/master/pcbnew/router/pns_routing_settings.h)
- **Walkaround:** obstacle clusters are turned into clearance "hulls" (cached by the rule resolver). The line is walked around each hull clockwise and counter-clockwise, and the shorter collision-free result is picked. — [pns_walkaround.cpp](https://gitlab.com/kicad/code/kicad/-/blob/master/pcbnew/router/pns_walkaround.cpp)
- **Shove:** hulls are built at clearance around the current line's segments (and via). Each colliding obstacle line is re-walked around that hull set, recursively.
  - Status codes: `SH_OK`, `SH_INCOMPLETE`, `SH_TRY_WALK`.
  - A "springback" mechanism reverts shove state.

  — [pns_shove.cpp](https://gitlab.com/kicad/code/kicad/-/blob/master/pcbnew/router/pns_shove.cpp)
- The FOSDEM 2015 talk describes "a shove and hug algorithm based on octagonal primitives and force propagation", plus optimization/trace smoothing and length tuning with diff pairs. — [FOSDEM 2015 abstract (search snippet)](https://archive.fosdem.org/2015/schedule/event/pcb_routing/)
- **Optimizer:** `COST_ESTIMATOR::CornerCost` penalizes corners. Optimization flags include `MERGE_SEGMENTS`, `MERGE_OBTUSE`, `MERGE_COLINEAR`, `SMART_PADS` (pad-entry optimization), `FANOUT_CLEANUP`, `KEEP_TOPOLOGY`, `PRESERVE_VERTEX`, `RESTRICT_AREA` and `LIMIT_CORNER_COUNT`. — [pns_optimizer.cpp](https://gitlab.com/kicad/code/kicad/-/blob/master/pcbnew/router/pns_optimizer.cpp)
- **User-facing semantics:**
  - Shove "walk[s] around obstacles that cannot be moved (… pads and locked tracks/vias) and shove[s] obstacles that can be moved". Walk Around does not modify other tracks.
  - "Attempt Finish" auto-routes a single track to the nearest ratsnest anchor "only [on] the current layer; it will not use vias".
  - "Attempt Finish Selected (Autoroute)" (Shift+F) routes multiple selected items in sequence.

  — [KiCad docs](https://gitlab.com/kicad/services/kicad-doc/-/blob/master/src/pcbnew/pcbnew_editing.adoc)
- **Router tool action names:** `pcbnew.InteractiveRouter.SingleTrack`, `.DiffPair`, `.ShoveMode`, `.WalkaroundMode`, `.HighlightMode`, `.AttemptFinish`, `.RouteSelected`, `.Autoroute` ("Attempt Finish Selected (Autoroute)"), `.OptimizeSelected`. — [pcb_actions.cpp](https://gitlab.com/kicad/code/kicad/-/blob/master/pcbnew/tools/pcb_actions.cpp)
- **IPC API:**
  - `RunAction` runs an action by name ("provided for low-level prototyping purposes only").
  - `AddToSelection`/`ClearSelection`/`HitTest` and `CreateItems`/`UpdateItems` within `BeginCommit`/`EndCommit` are available.
  - There is no dedicated "route this connection" or shove RPC.

  — [editor_commands.proto](https://gitlab.com/kicad/code/kicad/-/blob/master/api/proto/common/commands/editor_commands.proto)
- KiCad has no built-in global autorouter. `pcbnew/autorouter/` contains only the footprint autoplacer (`ar_autoplacer`, `spread_footprints`). — [GitLab tree](https://gitlab.com/kicad/code/kicad/-/tree/master/pcbnew/autorouter)
- KiCad ships PNS QA tools (a `pns_log_player`/`pns_debug_tool` and `qa_pns_regressions`) that replay router logs headlessly. — [qa/tools/pns](https://gitlab.com/kicad/code/kicad/-/tree/master/qa/tools/pns)
- Horizon EDA embeds "KiCad's awesome interactive router" (router version 6.0.4, GPLv3), so the router can be used outside pcbnew. — [Horizon EDA README](https://github.com/horizon-eda/horizon)
- Wlostowski was still fixing shove edge cases in early 2025, such as via/trace litter in the shove stack. A forum user reported the shove moving tracks into DRC-violating spots (anecdotal). — [allspice mirror commits](https://hub.allspice.io/AllSpiceMirrors/kicad/commits/branch/master/pcbnew/router); [KiCad forum](https://forum.kicad.info/t/any-info-on-push-and-shove-upgrade/60022)

**Other open-source routers relevant to KiCad**
- **KRT** (MIT, Python + Rust):
  - Features: rip-up/reroute, MPS ordering, diff pairs, length/time matching, bus routing, plane routing, BGA/QFN fanout, a "KiCad-oracle reconnect" pass that routes links KiCad's DRC reports as unconnected, and JSON routing plans runnable headless.
  - Claude Code skills (`/plan-pcb-routing`, `/identify-diff-pairs`, `/find-high-speed-nets`, `/diagnose-routing-failures`, `/review-routed-board`) analyze the board, generate a step-by-step plan, run it and verify.
  - Stated limitations: "No push-and-shove", "No blind or buried vias", "No coarse grid assignment before detailed routing to plan overall topology", "No design rules by region/area".

  — [KRT README](https://github.com/drandyhaas/KiCadRoutingTools); [claude-skills.md](https://github.com/drandyhaas/KiCadRoutingTools/blob/main/docs/claude-skills.md)
- **tscircuit capacity-autorouter** (MIT, TypeScript): pipeline/hypergraph router with a SimpleRouteJson I/O format. — [README](https://github.com/tscircuit/tscircuit-autorouter)

### Inferences
- Freerouting is the safest **bulk router** to wrap: strongest real-board CP in PCBWorld, headless CLI/API/MCP, and a KiCad 11 API round-trip. Its weaknesses are its own documented gaps: no congestion-aware fanout, no diff-pair or length enforcement in the router, and long runtimes on dense 2-layer boards.
- KiCad PNS is the ideal **geometric realizer** for LLM- or RL-chosen waypoints and topology sketches. It guarantees DRC-clean local geometry, 45° style and pad-entry quality, but needs a global planner on top. Practical paths, in order of robustness:
  1. Adopt or port PCBWorld-Engine (GPLv3) for headless, vectorized PNS calls.
  2. Use IPC `AddToSelection` + `RunAction("pcbnew.InteractiveRouter.Autoroute")` for single-layer completion, and `OptimizeSelected` to smooth autorouter output (prototype-grade, GUI-bound).
  3. Extract PNS as a library like Horizon EDA.

### Gaps
- Could not confirm Freerouting's original authorship and history (commonly attributed to Alfons Wirtz, who released it under GPL around 2014). It was not mentioned in the current repo docs.
- Could not confirm whether `RunAction`-triggered router actions work in a headless or non-GUI KiCad session, or whether KiCad 11 plans first-class routing RPCs.
- PCBWorld-Engine's patch set and API surface were not inspected beyond the paper's appendix.

---

## Q5. Why autorouters produce "ugly"/unacceptable results, and what industry autorouter skepticism is based on

### Takeaway
Skepticism rests on four things:
1. **Low completion on real, dense boards.** Classical routers "rarely complete complex production boards end-to-end".
2. **Blindness to intent.** Routers don't know which nets are high-speed, return paths, or user-facing.
3. **Local, greedy artifacts.** Poor via spread, first-feasible via placement, fanout collisions between adjacent parts, detours.
4. **Metrics that miss what humans value.** In PCBWorld, Freerouting beat the human reference on wirelength and vias yet failed DRC or connectivity on 20% of small boards.

Direct practitioner-forum evidence could not be fetched this session.

### Cited Findings
- PCBWorld: "industry still relies mainly on rule-based routers rooted in decades-old heuristics, which automate much of the routing process but rarely complete complex production boards end-to-end". The proven workflow is the human engineer's, "who neither hands the board to an auto-router nor draws every trace by hand" but repeatedly reads the board, judges feasibility, and draws with native operations. — [PCBWorld](https://arxiv.org/abs/2607.05915)
- Freerouting's own engineering notes list fanout problems: no congestion analysis; adjacent components "pointing at each other … mutually block escape"; via "at first feasible location" with poor via spread; static time budgets; dead pins retried every pass. — [escape_congestion_research.md](https://github.com/freerouting/freerouting/blob/master/docs/research/escape_congestion_research.md)
- On D3-B, Freerouting reached 100% routability but only 0.78 clean-pass, with a mean of 10.6 DRVs per board. KRT reached 0.86 routability but 0.20 CP with 44.7 mean DRVs. Wiring everything is not the same as legal wiring. — [PCBWorld Table 21](https://arxiv.org/abs/2607.05915)
- Human reference boards have *longer* wiring (170 mm vs Freerouting's 156 mm on D3-A) and more vias. Human quality is therefore not simply minimal length/vias; humans trade length for structure (spacing, grouping, return paths). — [PCBWorld Table 21](https://arxiv.org/abs/2607.05915)
- OrthoRoute's author: "Never trust the autorouter, but at least this one is fast." He also warns it is "useful to about five people on the planet". — [OrthoRoute README](https://github.com/bbenchoff/OrthoRoute)
- Many automated fanout tools silently fall back to sub-spec vias at fine pitch. — [malakaRouter3 README](https://github.com/Ivshti/malakaRouter3)
- KRT added a "design brief" and "floorplan intent, graded" so that "'the render looks fine' stops being a verdict". This acknowledges that geometric DRC-clean output is not the same as an acceptable board. — [KRT README](https://github.com/drandyhaas/KiCadRoutingTools)
- DSN-based flows lose rules: KiCad DSN export omits copper-to-edge clearance. Round-tripping through an external router can therefore yield boards that are clean in the router but fail KiCad DRC. — [Freerouting pcbench README](https://github.com/freerouting/freerouting/blob/master/scripts/pcbench/README.md)
- The tscircuit dataset README calls autorouting "a decades-old largely unsolved problem". It notes "partial autorouting is very useful for human-assisted routing" and lists quality-versus-ideal-routing and incremental speed as benchmark criteria. — [tscircuit/autorouting README](https://github.com/tscircuit/autorouting)

### Inferences
- Common "ugliness" sources implied by the router designs above, to target with post-processing and constraints:
  - excess bends and non-45° jogs (PNS corner-cost optimization exists for this);
  - acute pad entries (PNS `SMART_PADS`);
  - vias scattered without regard to return paths or planes;
  - high-speed nets routed late and therefore long and wandering;
  - unrelated nets interleaved instead of bused;
  - no reserved space for later meanders.
- Most skepticism is about *ungoverned* autorouting. Engineers do accept constrained, scoped automation (fanout generators, diff-pair and length tools, "attempt finish").

### Gaps
- Could not fetch EEVblog, KiCad forum, Hacker News or Reddit discussions, or vendor white papers, so no direct practitioner quotes beyond those above. The report writer should treat the practitioner-sentiment section as thinly sourced.
- No controlled study quantifying "aesthetic" or SI acceptability of autorouted boards was found.

---

## Q6. Hybrid approaches: human/AI-guided routing (fanout first, critical nets first, then bulk) and topology planning followed by geometric realization

### Takeaway
The best-performing open-source pipelines in 2026 are **staged and intent-driven**:
- planes/pours → BGA/QFN fanout → diff pairs and critical nets → bulk → length matching → cleanup → DRC-oracle repair.
- An LLM generates the plan and parameters; deterministic engines produce the geometry.

Closed-loop, engine-grounded action is essential. Open-loop LLM planning or geometry generation fails DRC badly.

### Cited Findings
- KRT's recommended chain: pour planes, then diff pairs, then one route over all nets including plane nets. The route step welds plane pads, with an in-run "finalize" and an oracle reconnect at the end. The `/plan-pcb-routing` skill:
  - identifies components needing fanout;
  - detects diff pairs and DDR length-matching groups;
  - classifies power nets (plane vs trace);
  - assesses signal speeds for GND return vias;
  - generates and runs a step-by-step plan, then verifies.

  Plans are JSON, replayable headless (`run_plan.py`). — [KRT README](https://github.com/drandyhaas/KiCadRoutingTools); [claude-skills.md](https://github.com/drandyhaas/KiCadRoutingTools/blob/main/docs/claude-skills.md)
- KRT supports "guide corridors and keep-out zones drawn on a User layer". This is a concrete mechanism for human- or LLM-sketched topology to bias a router. — [KRT README](https://github.com/drandyhaas/KiCadRoutingTools)
- malakaRouter3 is designed as "the first stage of a pipeline in front of a general-purpose router" (fine-pitch escape), pairing with KRT for bulk routing. Its successor pipeline is "escape → bulk → planes → refill → sweep" (now superseded by another tool). — [malakaRouter3 README](https://github.com/Ivshti/malakaRouter3)
- Freerouting's stage order is fanout → autorouter → optimizer, and its `-inc` flag ignores net classes (e.g. GND/VCC for planes). A hybrid flow can therefore pre-route critical nets as fixed copper, which Freerouting preserves exactly ("Preserved traces … must retain their exact geometry"). — [Freerouting README](https://github.com/freerouting/freerouting); [architecture.md](https://github.com/freerouting/freerouting/blob/master/docs/architecture.md)
- PCBWorld's engine-engagement ablation is the quantitative case for closed-loop hybrid control: on D3-A, interactive CP 0.65 vs plan-and-execute 0.19 vs engine-free 0.02 (GPT-5.4). — [PCBWorld Table 4](https://arxiv.org/abs/2607.05915)
- Two-stage capacity planning (global) then detailed routing: tscircuit's capacity mesh / hypergraph pipeline. KRT lists the lack of "coarse grid assignment before detailed routing to plan overall topology" as a limitation. — [tscircuit-autorouter README](https://github.com/tscircuit/tscircuit-autorouter); [KRT README §Limitations](https://github.com/drandyhaas/KiCadRoutingTools)
- Freerouting maintainers propose pre-route congestion estimation with a RUDY-style G-cell heatmap, using overflow = max(0, demand − supply) and supply = floor((tile_width − clearance)/(trace_width + clearance)). They want it to drive congestion-aware pin ordering and a cost-field input to maze routing. — [escape_congestion_research.md](https://github.com/freerouting/freerouting/blob/master/docs/research/escape_congestion_research.md)

### Inferences
- A "topology sketch, then geometric realization" design maps onto available pieces:
  1. A coarse capacity grid (RUDY) plus PathFinder negotiation, or an LLM-proposed corridor polyline per net/bus.
  2. Corridors converted into cost fields (KRT User-layer corridors, Freerouting preferred-direction/layer settings) or PNS waypoints.
  3. Realization by an A* or PNS engine with DRC feedback.

  This recovers the main benefit of topological routers (planar, crossing-aware topology decided first) without needing a full rubber-band implementation.

### Gaps
- No published PCB study was found that quantifies the benefit of LLM-chosen net ordering or corridors over default heuristics. KRT's claims are tool documentation, not controlled experiments.

---

## Q7. Benchmarks and datasets for PCB routing

### Takeaway
2024–2026 finally brought usable PCB routing benchmarks in native or near-native formats:
- **PCBench**: 164 real KiCad boards + PCB-RDL JSON + an RL env.
- **PCBWorld-Bench**: D1/D2 synthetic + 679 real boards in `.kicad_pcb`, with 8 engine-checked metrics.
- **tscircuit autorouting dataset**: synthetic problems.
- **Freerouting's fixture corpus**: 175 real DSN boards from bug reports, plus a nightly benchmark.

There is no ISPD/ICCAD-style official PCB contest benchmark that could be verified this session.

### Cited Findings
- **PCBench:** "a dataset consisting of 164 printed circuit boards", each with `raw.kicad_pcb` (professionally routed), `processed.kicad_pcb`, `final.json` in the PCB Routing Description Language (PCB-RDL) and metadata. It includes an augmentation script (random net subsets) and a Python `PCBRoutingEnv` RL environment with grid resolution. PCBWorld lists it as a DAC 2024 work-in-progress poster. — [PCBench README](https://github.com/PCBench/PCBench); [PCBWorld refs](https://arxiv.org/abs/2607.05915)
- **PCBWorld-Bench:**
  - D1 grid sizes 10–500 (Jumanji Connector replica); D2 has 10,000 train / 128 valid / 128 test.
  - D3: 679 boards converted to KiCad 9, kept only if fully connected and DRV-free after conversion, split into D3-A/B/C by pad count. The original routes serve as reference solutions.
  - Metrics: Clean Pass, Potential Gain, Routability, wallclock, DRV, wirelength, vias, Parse-fail; best-of-5 protocol.

  — [PCBWorld](https://arxiv.org/abs/2607.05915)
- **Freerouting:**
  - 175 fixture files (mostly `IssueNNN-*.dsn` from user reports), including `Issue508-DAC2020_bm01.dsn`, used as the quickest smoke-test.
  - A nightly benchmark with baselines and V2 score replay.
  - A PCBench pipeline that strips routing, exports DSN with `pcbnew.ExportSpecctraDSN`, and grades against KiCad DRC on the original.

  — [fixtures/](https://github.com/freerouting/freerouting/tree/master/fixtures); [AGENTS.md](https://github.com/freerouting/freerouting/blob/master/AGENTS.md); [scripts/pcbench/README.md](https://github.com/freerouting/freerouting/blob/master/scripts/pcbench/README.md)
- **tscircuit autorouting:** a dataset of autorouting problems in tscircuit "soup" format with a viewer, test server and benchmark criteria (speed, % fully routed, quality vs ideal, incremental speed, memory). "Largely replaced" by tscircuit-autorouter, which has its own sample datasets (e.g. `srj33`). — [tscircuit/autorouting](https://github.com/tscircuit/autorouting); [tscircuit-autorouter](https://github.com/tscircuit/tscircuit-autorouter)
- **KRT:** "Every change to the router is A/B-tested by replaying a corpus of real open-source boards … grading each one for DRC violations and unconnected nets", with a ~600-file test suite. — [KRT README](https://github.com/drandyhaas/KiCadRoutingTools)
- **VLSI-only RL environments** (not PCB): XRoute (OpenROAD-based detailed routing) and Jumanji Connector (abstract grid). — [XRoute](https://github.com/xplanlab/xroute_env); [PCBWorld Fig. 1 comparison](https://arxiv.org/abs/2607.05915)

### Inferences
- For an LLM-driven KiCad router, the natural evaluation stack is:
  - PCBWorld-Bench D3-A/B for comparability with published numbers (Freerouting CP 0.80/0.78);
  - D3-C as a stretch goal;
  - Freerouting's DSN corpus for regression;
  - SI-aware metrics that no benchmark currently scores: diff-pair coupling %, skew, length-group spread, reference-plane continuity.

### Gaps
- The origin of "DAC2020_bm01" (which DAC 2020 paper or contest) was not identified.
- Could not confirm whether ICCAD CAD Contest or ISPD ever ran a PCB routing problem. A 2018 ICCAD "obstacle-aware on-track bus routing" contest is recalled from memory but unverified.
- DeepPCB public data: none found.

---

## Implications for an LLM-driven KiCad router

### Takeaway
Use the LLM as a **planner and constraint engineer**, never as a geometry generator:
- It classifies nets, chooses per-class algorithms and parameters, orders work, and sketches topology/corridors.
- Deterministic engines realize the geometry: Freerouting for bulk, KRT-style pose A* for diff pairs and buses, KiCad PNS for push-and-shove realization and smoothing, flow/ILP or pattern generators for escape.
- KiCad DRC acts as the oracle in a closed loop.

PCBWorld's numbers make this concrete:
- Engine-grounded interactive control beats open-loop generation by 3–30× on clean-pass.
- Per-step LLM control is ~100× slower than a small RL policy or a classical router.

### Cited Findings
- LLM per-step routing: GPT-5.4 took 231 s per D3-A board vs 1.83 s for PPO and 7.09 s for Freerouting, and scored 0% CP on D3-B. — [PCBWorld](https://arxiv.org/abs/2607.05915)
- Interactive vs plan-and-execute vs engine-free CP on D3-A: 0.65 / 0.19 / 0.02. — [PCBWorld](https://arxiv.org/abs/2607.05915)
- An LLM-planned staged workflow is already practical: KRT's `/plan-pcb-routing` generates and executes JSON plans and verifies with DRC and connectivity checks. — [KRT claude-skills.md](https://github.com/drandyhaas/KiCadRoutingTools/blob/main/docs/claude-skills.md)
- Freerouting is controllable via CLI/API/MCP and round-trips through KiCad 11 API Specctra export/import. — [Freerouting MCP.md](https://github.com/freerouting/freerouting/blob/master/docs/API/MCP.md); [board_commands.proto](https://gitlab.com/kicad/code/kicad/-/blob/master/api/proto/board/board_commands.proto)
- KiCad PNS router actions can be invoked by name via IPC (`RunAction`), and PCBWorld-Engine exposes PNS primitives (start_route, move, fix_route, finish, set_routing_mode, flip_posture, width/via setters) to Python. — [editor_commands.proto](https://gitlab.com/kicad/code/kicad/-/blob/master/api/proto/common/commands/editor_commands.proto); [pcb_actions.cpp](https://gitlab.com/kicad/code/kicad/-/blob/master/pcbnew/tools/pcb_actions.cpp); [PCBWorld appendix](https://github.com/LGAI-Research/PCBWorld)

### Approach comparison matrix

| Approach | Core idea | Design rules / constraints | Scale and runtime evidence | Quality reputation | Open source | Modern-PCB relevance |
|---|---|---|---|---|---|---|
| Lee / maze / grid A* (KRT) | Wavefront or A* on a grid, with via edges between layers | Obstacles inflated by width + clearance; DRC-oracle reconnect | 47–51 nets in 6–9 s; diff-pair batches ~30 s ([KRT](https://github.com/drandyhaas/KiCadRoutingTools)) | D3-A CP 0.74, D3-B CP 0.20 at paper time ([PCBWorld](https://arxiv.org/abs/2607.05915)) | MIT (KRT) | Octilinear H/V/45; diff pairs, length/time matching, buses; no blind/buried vias, no shove |
| Gridless expansion-room A* + rip-up + optimizer (Freerouting) | A* over convex free-space rooms and doors; passes with escalating rip-up; keep-or-undo optimizer | Specctra rules (clearance classes, via rules, preferred directions); diff-pair and meander rules parsed but apparently not enforced | 2210-pin 2-layer board: 1748 s for one pass; si31-3 fully routed in 640 s + 807 s ([perf doc](https://github.com/freerouting/freerouting/blob/master/docs/research/large-board-autorouter-performance.md)) | Strongest baseline on real boards: D3-A CP 0.80, D3-B 0.78 ([PCBWorld](https://arxiv.org/abs/2607.05915)) | GPL (Java) | 45° geometry, multi-layer, fanout stage; weak congestion awareness |
| PathFinder negotiated congestion (OrthoRoute) | Iterative re-routing with present/history congestion costs | Lattice-only geometry | Thousands of nets on GPU (author's claim) | CP ≤ 0.02 on ordinary boards ([PCBWorld](https://arxiv.org/abs/2607.05915)) | Yes (OrthoRoute) | Backplanes, regular BGA lattices; best used as a global planner |
| Hypergraph / capacity mesh (tscircuit) | Successive approximation over a capacity mesh, then detailed routing | SimpleRouteJson obstacles, min trace width, via-in-pad flag | Not measured here | Not measured here | MIT | Concept for global planning; buses |
| Push-and-shove (KiCad PNS) | Local hull-based walkaround/shove plus corner-cost optimizer | Full KiCad rule resolver (clearances, widths, diff-pair gap, length/skew targets) | Interactive speed; PPO-on-PNS solves D3-A boards in ~2 s ([PCBWorld](https://arxiv.org/abs/2607.05915)) | Highly regarded interactively; engine for best learned results (PPO D3-A CP up to 0.94) | GPL (KiCad) | 45°/free-angle, diff pairs, tuning patterns; no global planning |
| Flow / ILP / SAT escape | Network-flow capacity models of escape channels | Pitch, via type and layer capacity built into the model | Large arrays (2000+ pins claimed for MCMCF, secondary source) | Academic, exact for the sub-problem | Mostly not | BGA and fine-pitch escape |
| Length-matching synthesis (Ozdal-Wong LR; region + meander; KiCad/KRT tuners) | Allocate area, then insert meanders or trombones | Min/max length or delay; amplitude and spacing rules | Post-route, fast (tools) | Tools widely used; academic methods not in OSS | KiCad, KRT, partly Freerouting rules | DDR, buses, diff-pair skew |
| Deep RL (grid) | Cell-by-cell policy | Implicit through reward | Collapses at grid ≥ 100–200 ([PCBWorld](https://arxiv.org/abs/2607.05915)) | Poor beyond toy problems | Jumanji, PCBench env | Low |
| Deep RL on engine actions (PCBWorld PPO) | Policy picks waypoints and shove/walkaround mode through PNS | Engine guarantees local DRC; DRC-based reward | ~2 s per small board | Beats Freerouting on D3-A; loses on D3-B ([PCBWorld](https://arxiv.org/abs/2607.05915)) | BSD env + GPL engine | Promising for small and medium boards |
| LLM tool-calling agent (PCBWorld) | LLM issues engine actions step by step | Engine plus DRC feedback | 231–866 s per board | CP 0.65 D3-A, 0.00 D3-B | Env is open | Better as a planner than as a per-segment router |

### Inferences (concrete recommendations)

1. **Architecture: three tiers.**
   - Tier 1, LLM planner: reads the netlist, datasheets and stackup; writes a typed routing plan (JSON).
   - Tier 2, deterministic executors chosen per net class: Freerouting, a KRT-like Rust A*, a PNS driver (PCBWorld-Engine or IPC `RunAction`), and escape/meander generators.
   - Tier 3, verification: KiCad DRC plus connectivity, plus SI checks (coupling %, skew, length spread, via count per net, reference-layer changes without return vias), fed back to Tier 1 as structured failure reports in the style of KRT's blocker attribution.

   The LLM never emits raw track coordinates except as coarse waypoints or corridors that an engine realizes.

2. **Algorithm per net class.**

   | Net class | Algorithm |
   |---|---|
   | Power/ground | Pours and planes first (zones + stitching), or wide-trace routing with neck-down at fine-pitch pads. Exclude from bulk signal routing (Freerouting `-inc`, or KRT plane flow). |
   | BGA / fine-pitch escape | Deterministic pattern fanout (dogbone / via-in-pad chosen by the LLM from pitch, via-in-pad allowed, fab capability) solved with inside-out ordering or a min-cost-flow capacity check. Use a ring search for legal standard vias (malakaRouter3-style) instead of silently using sub-spec vias. Freeze results before bulk routing. |
   | Differential pairs and impedance-controlled nets | Route before bulk with a coupled centerline in pose space (Dubins heuristic, as in KRT) or the KiCad PNS DP placer. Restrict layers to those with computed impedance widths. Symmetric vias with adjacent GND return vias. Then skew-tune with PNS. The LLM derives width/gap per layer from stackup and target Z. |
   | Length/phase groups (DDR byte lanes, parallel buses) | Bus routing middle-out with neighbor attraction, on a layer the LLM reserves. Reserve meander area during planning (region assignment as in arXiv:2407.19195), then add tuning patterns in KiCad or KRT trombones. Use time-domain matching when members change between microstrip and stripline. |
   | Critical clocks / sensitive analog | Short, early, on a single layer, with keep-outs/guard regions declared by the LLM as rule areas. |
   | Bulk low-speed | Freerouting (strongest real-board CP) with LLM-set costs, or negotiated-congestion global routing on a coarse capacity grid followed by A*/PNS detailed realization. Then the Freerouting optimizer and KiCad `OptimizeSelected` for smoothing. |

3. **How the LLM should set net ordering.**
   - Emit *priority tiers and constraints*, not a total order: tier 0 escape, tier 1 diff pairs and clocks, tier 2 length groups and buses, tier 3 short local nets, tier 4 everything else.
   - Within a tier, use algorithmic ordering: MPS crossing-conflict ordering between chip pairs, and inside-out for BGAs.
   - Let the LLM override only with semantic reasons, e.g. "route DQS with its byte lane", "route USB before the nearby SPI".

4. **Cost functions the LLM can tune (exposed in existing engines).**
   - Via cost (Freerouting default 50; raise for SI-critical classes).
   - Per-layer preferred direction with undesired-direction cost (1.0 vs 2.5; alternate H/V on inner layers).
   - Rip-up cost and escalation.
   - Proximity penalties near BGA fields and stubs (KRT).
   - Corridor attraction bonus (KRT bus attraction 5000).
   - Ripped-corridor avoidance.
   - A PathFinder-style history cost per G-cell for multi-iteration runs.
   - Corner cost / 45° preference (PNS `CornerCost`).

   Expose these as named knobs with documented effects so the LLM can reason about trade-offs, e.g. "fewer vias vs completion".

5. **Topology sketches.**
   - The LLM proposes, per bus or critical net, a coarse corridor (sequence of regions/G-cells or a polyline with layer) drawn on a User layer, as KRT already supports.
   - A capacity check (RUDY overflow = max(0, demand − supply)) validates the sketch before detailed routing. If a tile overflows, the LLM revises.
   - Detailed routing then treats corridors as soft attractors, not hard constraints, so completion is not sacrificed.

6. **Push-and-shove in automation.**
   - Use PNS as the "last-mile" realizer and repair tool. Shove mode can complete a failing connection by moving already-routed movable copper, which grid A* routers without shove (KRT) cannot do.
   - Lock pre-routed critical nets so shove cannot disturb them (PNS treats locked tracks as immovable).
   - For large-scale automation, prefer an engine-level binding (PCBWorld-Engine) over GUI `RunAction`.

7. **Make results not ugly.** After completion, always run:
   - an optimizer pass (Freerouting optimizer and/or PNS optimize: merge segments, obtuse corners, `SMART_PADS`, fanout cleanup, `KEEP_TOPOLOGY`);
   - dangling-stub and via cleanup;
   - grading against style metrics: bends per net, acute angles, excess length vs lower bound (Freerouting V2 optimizer score), via spread near BGAs, parallelism of buses.

   A rendered PNG can additionally be reviewed by a vision-capable model for "human acceptability", but DRC and SI metrics remain the gate.

8. **Evaluation protocol.**
   - Report PCBWorld-Bench metrics (CP, routability, wirelength, vias, time) on D3-A and D3-B for comparability: Freerouting CP 0.80 / 0.78 is the bar to beat.
   - Add SI-constraint satisfaction metrics for diff pairs and length groups, which no current benchmark scores.
   - Regress on Freerouting's DSN fixture corpus.

9. **Learning later.** Once the deterministic pipeline is stable, a small RL policy on PNS actions (PCBWorld-style PPO) could replace hand-tuned heuristics for local completion and repair. PPO trained on synthetic boards transferred zero-shot to real small boards (D3-A CP 0.86–0.94). The LLM stays at the planning level.

### Gaps
- No controlled evidence yet that LLM-chosen ordering, corridors or costs beat default heuristics on real boards. This should be the first experiment: ablate the LLM plan against defaults on PCBWorld-Bench D3-B.
- SI-aware evaluation (coupling, return paths, crosstalk) has no open benchmark. A scoring harness would have to be built (e.g. extending PCBWorld's evaluator).
- License interplay needs review: Freerouting GPL, KiCad/PNS GPL, PCBWorld-Engine GPL vs KRT MIT and PCBWorld BSD. It affects whether PNS code can be embedded or only invoked as a separate process.
