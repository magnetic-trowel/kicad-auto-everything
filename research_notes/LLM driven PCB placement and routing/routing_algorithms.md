# Automatic PCB Routing Algorithms: Classical, PCB-Specific, ML/RL, Open-Source Engines, and Implications for an LLM-Driven KiCad Router

> Research notes, current to 2026-10-20. This is the second, deepened pass. The first pass ran with arXiv, IEEE and vendor sites blocked. In this pass, direct fetches of arXiv, InstaDeep/DeepPCB, OpenAlex, CUHK, AAAI, NeurIPS and similar sites worked, but the shared web-search budget ran out again mid-pass. Some topics are therefore backed by direct primary fetches only, not by fresh searches.
>
> **Division of labour:** a companion file, `routing_classics_supplement.md` (written by another agent), covers in depth:
> - line-probe and channel/switchbox routers;
> - topological/rubber-band routing (SURF, TopoR, toporouter);
> - BGA escape ILP/flow formulations;
> - length-matching and bus routing algorithms;
> - diff-pair algorithms;
> - autorouter skepticism.
>
> Q1, Q2 and Q5 below keep only brief pointers and tool/ML-specific evidence on those topics. The depth here is on ML/RL routing, KiCad PNS internals and scripting, Freerouting internals and benchmarks, datasets, and the earlier gaps.
>
> **Evidence tags** (on every bullet):
> - **[P]** = read in full from the primary source: full paper text, source code, an official doc page, or repo files.
> - **[A]** = abstract or metadata only (arXiv API, OpenAlex, proceedings page).
> - **[S]** = search-result snippet or a secondary summary.
> - **[V]** = a vendor's own marketing or benchmark page. It is primary for "what the vendor claims", but not independently verified.
>
> **VLSI vs PCB:** every claim is labelled with its domain whenever that is not obvious.

---

## Q1. Classical routing algorithms (maze/A*, line-probe, gridless/shape-based, negotiated congestion, rip-up-and-reroute, topological, sequential vs concurrent, net ordering)

### Takeaway
Every production-grade open-source PCB router examined in October 2026 is a **sequential, cost-driven path search with rip-up-and-reroute and a post-route optimizer**:
- **Freerouting:** gridless A* over convex "expansion rooms".
- **KiCadRoutingTools (KRT):** Rust octilinear grid A*.
- **OpenROAD PcbRouter:** grid A* with 45° moves and fixed-order rip-up iterations.

KiCad's PNS is **not a path searcher**. It is a local walkaround/shove engine that needs waypoints. Negotiated congestion (PathFinder) appears in PCB tools only in niche or hybrid form: OrthoRoute, and FanoutNet's internal router. Classical routers remained the strongest open baselines on real boards in every 2026 benchmark found. Line-probe, channel, topological and escape-flow theory are covered in the companion supplement.

### Cited Findings

**Maze/Lee and A***
- [P] Lee 1961 is the canonical root of maze routing. PCBWorld cites it among the "decades-old heuristics" behind industry rule-based routers. — [doi:10.1109/TEC.1961.5219222](https://doi.org/10.1109/TEC.1961.5219222); [PCBWorld](https://arxiv.org/abs/2607.05915)
- [P] **Freerouting's A* heuristic** (`DestinationDistance`) computes "a good lower bound for the distance between a new MazeExpansionElement and the destination set". It uses per-layer minimum trace costs (component side, solder side and inner layers kept separately) plus minimum via costs, so the heuristic stays admissible when layer changes are needed. The open list is a `SortedSet<MazeListElement>`. — [DestinationDistance.java](https://github.com/freerouting/freerouting/blob/master/src/main/java/app/freerouting/autoroute/maze/DestinationDistance.java); [MazeSearchEngine.java](https://github.com/freerouting/freerouting/blob/master/src/main/java/app/freerouting/autoroute/maze/MazeSearchEngine.java)
- [P] **KRT:** "fast Rust-accelerated A* autorouter", grid-based and octilinear (H/V/45°), "~10× faster than pure Python". — [KRT README](https://github.com/drandyhaas/KiCadRoutingTools)
- [P] **OpenROAD PcbRouter** (BSD-3, C++, ~6.6k lines):
  - A grid-based router that reads `.kicad_pcb` (KiCad 5.1.2 format).
  - Diagonal moves use width and clearance scaled by 1/√2.
  - Each iteration routes diff pairs first, then signal nets (`routeSingleIteration` → `routeDiffPairs`, then `routeSignalNets`).
  - It runs `gNumRipUpReRouteIteration` passes of "Fixed-Order Rip-Up and Re-Route all nets", keeping the best solution and tracking bends per net.

  — [PcbRouter repo](https://github.com/The-OpenROAD-Project-Attic/PcbRouter) (`src/GridBasedRouter.cpp`)

**Shape-based / gridless**
- [P] **Freerouting's search space:** packages `FreeSpaceExpansionRoom`, `ObstacleExpansionRoom`, `ExpansionDoor`, `TargetItemExpansionDoor`, `Sorted45DegreeRoomNeighbours`, `SortedOrthogonalRoomNeighbours`, plus `MazeSearchEngine`, `MazeRipupResolver`, `MazeTraceShover`. That is, A* runs over convex free-space rooms connected by doors, in 45° or orthogonal angle modes. — [expansion package](https://github.com/freerouting/freerouting/tree/master/src/main/java/app/freerouting/autoroute/expansion); [architecture.md](https://github.com/freerouting/freerouting/blob/master/docs/architecture.md)
- [S] A secondary blog and a Python port describe the same thing: a continuous plane, convex polygonal rooms, and "A* over rooms-through-doors (cost = geometric distance + via cost)". — [tinycomputers.io](https://tinycomputers.io/posts/the-mathematics-of-pcb-trace-routing.html); [freeroute port](https://git.supported.systems/warehack.ing/freeroute/src/commit/6a24ffc540f04216b05e0cf471aeef85c77a8dee)

**Rip-up and reroute**
- [P] Dees & Karger, DAC 1982, is the classic reference. — [doi:10.1145/800263.809241](https://doi.org/10.1145/800263.809241)
- [P] **Freerouting rip-up cost:** rip-up cost = `ripupCosts × costFactor`, where `costFactor` scales with obstacle trace half-width and contact count. It is then divided by the detour, and randomized on passes ≥4 that are not multiples of 3. Escalation is global and linear (`startRipupCosts * (passNo+1)`), which the maintainers call "sub-optimal". — [MazeRipupResolver.java](https://github.com/freerouting/freerouting/blob/master/src/main/java/app/freerouting/autoroute/maze/MazeRipupResolver.java); [escape_congestion_research.md](https://github.com/freerouting/freerouting/blob/master/docs/research/escape_congestion_research.md)
- [P] **KRT rip-up:**
  - Frontier-based blocker attribution with early probes (5000 iterations).
  - Blocker-selection modes `count`, `near-target`, `bidir` and `mincut`. The `mincut` mode turns rippable copper into high soft cost and re-routes once.
  - Diff pairs are ripped and restored as a unit.

  — [KRT rip-up-reroute.md](https://github.com/drandyhaas/KiCadRoutingTools/blob/main/docs/rip-up-reroute.md)

**Negotiated congestion (PathFinder)**
- [P] PathFinder (McMurchie & Ebeling, FPGA 1995). — [doi:10.1145/201310.201328](https://doi.org/10.1145/201310.201328)
- [P] **OrthoRoute:**
  - PathFinder on a Manhattan via-grid lattice (H-only and V-only layers, blind/buried vias).
  - A CUDA SSSP per net, but "nets are still routed in sequence on a shared congestion map".
  - The author says it is "not a general-purpose PCB autorouter".

  — [OrthoRoute README](https://github.com/bbenchoff/OrthoRoute)
- [P] **FanoutNet's internal Multi-Constraint Router (PCB):**
  - A 3-D A* whose cost is g = c1·wirelength + c2·layer-change + c3·diff-pair + c4·reference-layer-shielding + c5·spacing.
  - The heuristic is "shortest possible wire length constrained by 135° routing angle".
  - It adopts PathFinder congestion negotiation, raising the spacing weight c5 over iterations.

  — [FanoutNet, AAAI 2023](https://ojs.aaai.org/index.php/AAAI/article/view/26030/25802)

**Successive approximation / hypergraph**
- [P] tscircuit's MIT `capacity-autorouter` is "hundreds of algorithms organized in a Pipeline", using "successive approximation and Hypergraphs rather than sequential routing" over a recursively subdivided capacity mesh. — [tscircuit-autorouter README](https://github.com/tscircuit/tscircuit-autorouter)

**Learned cost maps on top of A***
- [A] "Ranking Cost" (Huang et al., 2021) combines A* with Evolution Strategies. It learns per-net "cost maps" that steer A* toward a global objective, plus a learned ranking parameter for net order. It reports better connectivity and scalability than sequential A* and a canonical RL baseline. — [arXiv:2110.03939](https://arxiv.org/abs/2110.03939)

**Net ordering heuristics**
- [P] KRT's default **MPS (Maximum Planar Subset)** ordering:
  - Chip boundaries are "unrolled" to [0,1], inverted source/target order detects crossings, and the conflict graph is processed greedily.
  - Alternatives: inside-out (for BGAs) and bus middle-out.

  — [KRT net-ordering.md](https://github.com/drandyhaas/KiCadRoutingTools/blob/main/docs/net-ordering.md)
- [P] **Freerouting ordering:**
  - `ItemSelectionStrategy` has `SEQUENTIAL` and `PRIORITIZED`.
  - Fanout goes most-SMD-pins component first, then outermost pins first. The maintainers note this "breaks down for adjacent dense components".

  — [ItemSelectionStrategy.java](https://github.com/freerouting/freerouting/blob/master/src/main/java/app/freerouting/autoroute/ItemSelectionStrategy.java); [escape_congestion_research.md](https://github.com/freerouting/freerouting/blob/master/docs/research/escape_congestion_research.md)

**Scale/runtime (real boards)**
- [P] **Freerouting 2.5.0-RC9 profiles:**
  - Aleste-520EX (2210 pins, 2 layers): one pass of 1748 s took incompletes from 1620 to 882.
  - logicbone (8 layers): fanout took 899 s.
  - si31-3: router 640 s plus optimizer 807 s.
  - "Pin count does not separate the slow boards from the fast ones."

  — [large-board-autorouter-performance.md](https://github.com/freerouting/freerouting/blob/master/docs/research/large-board-autorouter-performance.md)
- [P] **KRT integration tests:**

  | Group | Routed | Time |
  |---|---|---|
  | FTDI | 47/47 | 8.6 s |
  | LVDS diff-pair batch | 28/28 | ~29 s (10–12 M iterations) |
  | DDR single-ended | 51/51 | 6.2 s |

  — [KRT README](https://github.com/drandyhaas/KiCadRoutingTools)

### Inferences
- Gridless room search (Freerouting) and fine-grid octilinear A* (KRT, PcbRouter) are the open approaches with real-board completion evidence. PathFinder-style negotiation works best as a congestion layer inside such routers (as in FanoutNet's MCR) or as a coarse global planner, not as a lattice-only detailed router.
- Net order and cost weights are the main levers of sequential routers. The ML papers that actually help, covered in Q3, mostly learn those two things.

### Gaps
- Classic line-probe, channel/switchbox and topological router material is deferred to `routing_classics_supplement.md`.

---

## Q2. PCB-specific research: BGA escape, any-angle, length matching/meanders, differential pairs, layer assignment, via minimization, bus routing

### Takeaway
The core algorithmic literature for these topics is in the companion supplement. This section keeps the **tool- and ML-specific PCB evidence**:
- FanoutNet: learned fanout, 100% routability on Huawei 6-layer HDI boards.
- TRouter: ML-guided thermal-aware PCB routing.
- What KiCad PNS, KRT, PcbRouter and Freerouting actually implement for diff pairs and length tuning.

### Cited Findings

**Fanout / escape (ML and tools)**
- [P] **FanoutNet** (Li, Zhang, Xu, Liu; AAAI 2023; Wuhan Univ. of Technology / Huawei Device) — [AAAI PDF](https://ojs.aaai.org/index.php/AAAI/article/view/26030/25802):
  - PCB fanout (layer assignment, fanout locations, pin-to-location routing) is posed as an MDP with one action per net. The action is a pair of per-pin choices (layer, offset, direction), sampled from a policy.
  - The reward is the routability (N_succ/N_total) obtained by a downstream router.
  - The network is a CNN over multi-channel layout images plus a 4-layer attention encoder over a per-net feature vector, trained with PPO (K=20 epochs; learning rates 3e-4 policy, 1e-3 value).
  - Benchmarks:
    - 11 open-source 2–4-layer boards (bm1–bm11) from the ASP-DAC 2021 PCBBenchmarks repo.
    - 5 industrial Huawei 6-layer HDI boards (94–368 nets, 277–937 pins).
  - Industrial results (Table 6):

    | Method | Avg routability | Avg runtime |
    |---|---|---|
    | FanoutNet | 100% | 245 min |
    | Freerouting 1.4.5.1 | 81% (">24 h" on 4 of 5 cases) | — |
    | ELECTRA 5.91 | 91% | ~1 min |
    | NB-A* (negotiation-based A*, Lin et al.) | 95% | 69 min |

- [P] Practitioner gap at fine pitch: "most automated fanout tools … fall back to a smaller, sub-spec via". — [malakaRouter3](https://github.com/Ivshti/malakaRouter3)
- [P] Freerouting fanout: "No congestion analysis of any kind"; vias placed "at first feasible location". — [escape_congestion_research.md](https://github.com/freerouting/freerouting/blob/master/docs/research/escape_congestion_research.md)

**Thermal-aware routing with ML (PCB)**
- [P] **TRouter** (Chen, Xiong, He, Yu; IEEE TCAD 42(10), Oct 2023):
  - A nonlocal criss-cross-attention network predicts the board thermal map from pads, vias, components and wires.
  - Per-cell gradients from backpropagation are folded into a full-board router to steer "thermal-aware wire detour and via punching".
  - Parallelism comes from a conflict graph over net convex hulls.
  - Benchmarks come from PCBRouter (the OpenROAD PcbRouter set). It beats PCBRouter on runtime and temperature, verified with HyperLynx.

  — [TRouter PDF](https://www.cse.cuhk.edu.hk/~byu/papers/J94-TCAD2023-TRouter.pdf)

**Differential pairs (implemented tools)**
- [P] **KiCad PNS DP placer:**
  - Builds sets of "gateways" (anchor pairs with orientation and spacing) at the start primitive pair and at the cursor or target pair.
  - Fits every entry/target gateway combination (`FitGateways`).
  - Scores fits by `score` and `coupledRatio`, rejecting non-obtuse entry angles first.
  - Then walks or shoves the coupled pair.

  — [pns_diff_pair_placer.cpp](https://gitlab.com/kicad/code/kicad/-/blob/master/pcbnew/router/pns_diff_pair_placer.cpp); [pns_diff_pair.h](https://gitlab.com/kicad/code/kicad/-/blob/master/pcbnew/router/pns_diff_pair.h)
- [P] KRT routes diff pairs as a centerline in (x, y, θ) with a Dubins heuristic, then offsets P/N. — [KRT differential-pairs.md](https://github.com/drandyhaas/KiCadRoutingTools/blob/main/docs/differential-pairs.md)
- [P] PcbRouter routes diff pairs (`GridDiffPairNet`) before signal nets in every rip-up iteration. — [PcbRouter src](https://github.com/The-OpenROAD-Project-Attic/PcbRouter)
- [P] Freerouting master parses diff pairs (`DifferentialPair` record with coupled spacing and max skew), but no `autoroute` package references them. Separately, DeepPCB's marketing says Freerouting "doesn't natively route differential pairs as pairs" [V]. — [DifferentialPair.java](https://github.com/freerouting/freerouting/blob/master/src/main/java/app/freerouting/rules/DifferentialPair.java); [deeppcb.ai/freerouting-vs-deeppcb](https://deeppcb.ai/freerouting-vs-deeppcb/)

**Length tuning (implemented tools)**
- [P] **KiCad PNS meander engine:**
  - Shape types: `MT_SINGLE`, `MT_START`, `MT_FINISH`, `MT_TURN`, `MT_CORNER`, `MT_ARC`, `MT_EMPTY`. Corner styles: round (90° arc) or chamfer (45°). Single- or dual-sided.
  - `MeanderSegment` greedily fills each segment of the chosen span with maximal meanders that pass `CheckFit` collision checks against the world.
  - `tuneLineLength` then trims: it ends the chain once the max elongation would exceed the target, and spreads the excess length reduction across meanders by searching each one's amplitude (`findAmplitudeForLength`).
  - Time-domain targets are converted via `CalculateLengthForDelay` in the router interface.

  — [pns_meander.cpp](https://gitlab.com/kicad/code/kicad/-/blob/master/pcbnew/router/pns_meander.cpp); [pns_meander_placer_base.cpp](https://gitlab.com/kicad/code/kicad/-/blob/master/pcbnew/router/pns_meander_placer_base.cpp); [pns_meander_placer.cpp](https://gitlab.com/kicad/code/kicad/-/blob/master/pcbnew/router/pns_meander_placer.cpp); [pns_router.h](https://gitlab.com/kicad/code/kicad/-/blob/master/pcbnew/router/pns_router.h)
- [P] KiCad user docs: tuning works only on "point-to-point nets between two pads", and DP tuning "only to the coupled portions". — [pcbnew_editing.adoc](https://gitlab.com/kicad/services/kicad-doc/-/blob/master/src/pcbnew/pcbnew_editing.adoc)
- [P] KRT: post-route trombones, DDR4 auto-grouping, time matching. Freerouting: a `NetMeanderConstraint` rule model (0.2–1.0 mm amplitude defaults). — [KRT length-matching.md](https://github.com/drandyhaas/KiCadRoutingTools/blob/main/docs/length-matching.md); [NetMeanderConstraint.java](https://github.com/freerouting/freerouting/blob/master/src/main/java/app/freerouting/rules/NetMeanderConstraint.java)

### Inferences
- FanoutNet is the strongest *PCB-specific* evidence that RL helps. It helps by making a **pre-routing resource-allocation decision** (fanout locations and layers) for a classical negotiated A* router, not by drawing wires. Its own runtime (~4 h) is longer than the classical baselines.
- KiCad's tuning engine is a sound local "meander synthesizer" an automated system can call after routing. It does not reserve area, so the global planner must leave room for it.

### Gaps
- Academic escape, length-matching, bus and diff-pair formulations are covered in `routing_classics_supplement.md`.

---

## Q3. ML/RL routing: DeepPCB, RL papers 2019–2026, MCTS, generative/transformer routing, LLM agents, and VLSI-to-PCB transfer

### Takeaway
1. **Evidence from 2026 converges:** learned or LLM agents do best when they act through engine-native operations or semantic relations that a deterministic tool realizes, not when they emit coordinates. The evidence:
   - PCBWorld: interactive engine actions beat plan-and-execute and engine-free generation.
   - RAC: semantic relations reach 90.9% clean-pass vs 23.2% for direct coordinates.
   - OmniRouting: the best LLM reaches 12.6% net routability zero-shot and 28% with tools, vs 93.6% for humans and 56.2% for a classical router.
2. **DeepPCB** is a commercial RL router: a custom C++ simulator, actor/learner training on TPUs, cloud API, and an open-source KiCad plugin. Its **vendor-run** PCBWorld-Bench results (0.929 / 0.800 one-attempt clean-pass on small/medium boards) would make it the top published result if independently confirmed. Its own pages exclude DDR, length matching and complex BGA fanout.
3. **The ML that works on PCBs so far:**
   - learns a decision a classical router consumes (fanout locations: FanoutNet; net ordering: DreamerV3+Freerouting; cost maps: Ranking Cost);
   - or trains a compact policy over engine actions (PCBWorld PPO).
4. **VLSI generative global routers** (PRNet, HubRouter, NeuralSteiner, DSBRouter) are evaluated on ISPD gcell grids with overflow metrics. They transfer poorly to gridless, DRC-bound PCB geometry. One PCB transformer router (GPCB) reported strong in-house results but scored 0.69% net routability on OmniRouting's real boards.

### Cited Findings

**DeepPCB (InstaDeep)**
- [P] **Training stack** (InstaDeep / Google Cloud blog, Oct 2023) — [InstaDeep TPU post](https://instadeep.com/2023/10/reinforcement-learning-on-google-cloud-tpus-to-improve-deeppcb/):
  - DeepPCB's team "developed a high-speed simulation engine to efficiently train reinforcement learning agents", but "commonly used RL libraries fall short in terms of training throughput".
  - Moving the simulator to the Sebulba actor/learner architecture on Cloud TPUs gave "a 15x-235x acceleration". Environments are stepped in a shared pool of C++ threads; JAX `pmap` updates the learner; PPO was used for the Atari validation.
  - A full training run went from "~24 hours … approximately $260" on a high-end GPU to "6 minutes at a mere $20".
- [P] **Platform blog** (`deeppcb.ai`, ~2024) — [DeepPCB cloud blog](https://deeppcb.ai/bringing-ai-and-cloud-to-pcb-routing/):
  - "cloud-native, fully automated", with "placement, routing, or both" jobs run "within the time budget you assigned".
  - RL workloads are distributed with Ray/KubeRay on GKE via InstaDeep's AIchor platform.
  - The internal benchmark board (444 airwires, 157 nets, 2 layers) saw ">50% reduction in via count" over a year. The team was tackling the 6-layer BeagleBone Black (1,223 airwires, 310 nets).
  - Supports "DRC, net clearance matrices, differential pairs, and power plane area maximization".
  - Intermediate routings are downloadable, and an API exists.
- [V] **Product page, Oct 2026** — [deeppcb.ai](https://deeppcb.ai/):
  - "A learned routing engine: over seven years of reinforcement learning R&D, published at top AI conferences like NeurIPS and ICML."
  - The **Cooper** setup agent "reads the board and reports what it understood: stackup, net classes, differential pairs, planes, clearances" and takes plain-language setup instructions.
  - Workflow: "critical nets were routed by hand first and the engine finished the rest".
  - Explicitly *not* for "DDR nets, length matching, advanced impedance control, and RF-specific constraints".
- [V] **KiCad plugin page:**
  - Routes "signal nets … diff pairs · blind & buried vias · 8 layers".
  - "Completion falls past ~1,200 airwires"; free tier 30 min / 4 layers / 150 airwires.
  - "Length matching & skew · crosstalk · DDR · complicated BGA fanout" are left to the user.
  - The board, rules and optionally the schematic are uploaded to `api.deeppcb.ai`. Results arrive "as a single commit in KiCad's own undo stack".

  — [DeepPCB KiCad plugin page](https://deeppcb.ai/kicad-autorouter-plugin/)
- [P] The plugin is Apache-2.0 and open-source. It is a KiCad ≥6 scripting-plugin that creates a cloud routing job and downloads the routed board. — [instadeepai/deeppcb-kicad-plugin](https://github.com/instadeepai/deeppcb-kicad-plugin)
- [V] **PCBWorld-Bench self-evaluation** (published 2026-09-28) — [DeepPCB PCBWorld-Bench results](https://deeppcb.ai/benchmark/pcbworld-bench-deeppcb-results/):
  - One attempt per board on its "standard routing model … not our most powerful one", no tuning: **D3-A 0.929** (92/99 boards) and **D3-B 0.800** (24/30 attempts, 3 per board).
  - The vendor compares this with the paper's best @1 results of 0.81 (PPO w/o finish) and 0.64 (Freerouting).
  - Median time to first clean board: 38 s and 46 s, scored at 3 minutes.
  - Vias 0.59× and 0.50× the reference, track length 0.94–0.95× (on nets without pours).
  - Caveats the vendor states itself: 98 of 99 D3-A boards and all D3-B boards are 2-layer; D3-B is only 10 boards (95% CI [0.627, 0.905]); the 3-minute cut-off was chosen "after seeing the curve"; a width-rounding write-back fix was needed.
- [V] **Marketing vs Freerouting:**
  - DeepPCB claims Freerouting "was state-of-the-art in 2005", gets "60–75% on complex boards" and "frequent violations", while DeepPCB reaches "95.6% of KiCad boards hit 95%+ completion".
  - These numbers conflict with PCBWorld's independent measurement: Freerouting 2.1.0 at 0.80/0.78 clean-pass on small/medium real boards.
  - They also ignore Freerouting's 2025–26 gains; see Q4.

  — [deeppcb.ai/freerouting-vs-deeppcb](https://deeppcb.ai/freerouting-vs-deeppcb/)
- [V] DeepPCB's RL explainer describes RL routing generically: state, extend/via/complete/rip-up actions, reward terms for DRC, vias and length, training in simulation. It **does not disclose** DeepPCB's actual observation, action or reward design. — [deeppcb.ai RL explainer](https://deeppcb.ai/reinforcement-learning-pcb-routing-explained/)
- [S]/[V] A competitor (Quilter) blog states that DeepPCB is "trained through self-play iterations inside a custom C++ simulation engine", that InstaDeep was "acquired by BioNTech … in 2023", and that the public tier is capped at "1,000 components, 2,200 pins, 1,200 airwires, and 8 layers". It describes Quilter's own approach as "physics-driven reinforcement learning" with multi-candidate generation and a Simbeor field-solver scorecard. Openly biased. — [Quilter 2026 guide](https://www.quilter.ai/blog/the-2026-guide-to-autonomous-pcb-design-quilter-vs-deeppcb-vs-flux-ai)
- [P] InstaDeep's open **Jumanji `Connector`** environment is the grid toy problem many RL routing baselines use: agents leave impassable paths on a grid, 5 actions per agent. — [Jumanji connector docs](https://github.com/instadeepai/jumanji/blob/main/docs/environments/connector.md)

**PCBWorld (LG AI Research; KDD 2026 workshop; arXiv v1 Jul 7, v4 Sep 11 2026)** — [arXiv:2607.05915](https://arxiv.org/abs/2607.05915); [repo](https://github.com/LGAI-Research/PCBWorld)
- [P] **Setup:**
  - A Gym environment over KiCad 9.0.8's PNS router: 58 Python APIs, 14 reproducing `PNS::ROUTER`.
  - Actions: `net_select`, `start_route`, `make_line(p_end, routing_mode)`, `make_via`, `finish`, `net_end`. `p_end` is chosen from engine candidates.
  - Reward potential: Φ = −(f_drv + λ_w·WL + λ_v·vias), with KiCad DRC (38 checks).
  - Datasets: D1 grid, D2 synthetic, and D3 with 679 real boards split A/B/C.
- [P] **Results, best-of-5 clean-pass (Table 3, identical in v1 and v4):**

  | Method | D3-A (99 boards) | D3-B (10 boards) |
  |---|---|---|
  | Freerouting 2.1.0 | 0.80 | 0.78 |
  | KRT | 0.74 | 0.20 |
  | PPO | 0.86 | 0.45 |
  | PPO (w/o finish) | 0.94 | — |
  | GPT-5.4 interactive | 0.65 | 0.00 |
  | OrthoRoute | 0.02 | 0.00 |

  Single-rollout (@1) values in v4 Table 22 are lower: on D3-A, Freerouting 0.75 and PPO-w/o-finish 0.81; on D3-B, Freerouting 0.64 (as quoted by DeepPCB). — [PCBWorld v4 HTML](https://arxiv.org/html/2607.05915v4)
- [P] **Engine engagement** (GPT-5.4 on D3-A): interactive CP 0.65, plan-and-execute 0.19, engine-free 0.02.
- [P] **Grid-action RL collapses:** A2C at grid ≥100, Sable at ≥200.

**RL / MCTS / learned routing papers (PCB or generic circuit), read in full or by abstract**
- [P] **He & Bao, "Circuit Routing Using MCTS and DNNs"** (arXiv 2020; VLSI-DAT 2022) — [arXiv:2006.13607](https://arxiv.org/abs/2006.13607):
  - Routing is a Go-like sequential process of adding grid vertices.
  - MCTS uses a *maximum*-reward UCT (not average), with a DFS + trained-DNN rollout policy.
  - Experiments use randomly generated **single-layer 30×30 grids** with two-pin nets. The authors claim it solves cases sequential A* and Lee's algorithm cannot, and beats vanilla MCTS.
- [A] **Liao, Pan & Chiang, "DreamerV3+FR"** (Expert Systems with Applications, Feb 2026) — [OpenAlex record (doi:10.1016/j.eswa.2026.131424)](https://api.openalex.org/works/doi:10.1016/j.eswa.2026.131424); [code](https://github.com/yinqimakeitfun/dreamer-Autorouting/tree/main):
  - Model-based RL "integrating a latent world model with the FreeRouting environment", using "latent imagination … to optimize net ordering before physical execution".
  - Reports "96% completion", 21% less training time than DQN, and generalization "to unseen 6-layer PCBs".
  - Reports that PPO fails in the sparse-reward setting, and that VAE+GAN and LLM agents "falter due to probabilistic design rule violations and spatial hallucinations".
- [A] **Liao et al., "A Deep RL Approach for Global Routing"** (J. Mech. Design 2020): DQN on generated global-routing problem sets, beating sequential A*. Synthetic grids. — [arXiv:1906.08809](https://arxiv.org/abs/1906.08809)
- [A] **GPCB Routing** (Chen, Tu, Wang, …, Qian; IEEE TCAD 44(4), Apr 2025) and its precursor **PRG** (ISEDA 2024) — [doi:10.1109/tcad.2024.3486241](https://doi.org/10.1109/tcad.2024.3486241); [PRG doi:10.1109/iseda62518.2024.10617906](https://doi.org/10.1109/iseda62518.2024.10617906) (abstracts via [OpenAlex](https://api.openalex.org/works/doi:10.1109/tcad.2024.3486241)):
  - Converts detailed routing into "network flow-based encodings" and tokenizes routing patterns, so routing becomes token prediction.
  - Uses a 2-D sliding window with local memory, and learns "from human experts". It predicts multiple routes in parallel.
  - Claims it "consistently outperforms in terms of routability, runtime, and wirelength".
- [P] **Contradicting evidence:** on OmniRouting's real boards, "GPCBRouter" scored **0.69% net routability ratio** with 99% open nets, vs PcbRouter's 56.20%. — [OmniRouting](https://arxiv.org/abs/2608.04434)
- [A] **Ranking Cost** (A* + ES-learned cost maps). — [arXiv:2110.03939](https://arxiv.org/abs/2110.03939)
- [P] **FanoutNet** (PPO for fanout feeding a negotiated A*). See Q2. — [AAAI 2023](https://ojs.aaai.org/index.php/AAAI/article/view/26030/25802)
- [P] **TRouter** (attention network predicting thermal maps to guide routing). See Q2. — [TCAD 2023](https://www.cse.cuhk.edu.hk/~byu/papers/J94-TCAD2023-TRouter.pdf)

**LLM/LMM PCB routing benchmarks and agent interfaces**
- [P] **OmniRouting** (Penn State et al., arXiv Aug 2026) — [arXiv:2608.04434](https://arxiv.org/abs/2608.04434):
  - 1,681 schematic-coupled real designs parsed from EAGLE files (SparkFun, Arduino, Adafruit, Seeed, ProtoCentral, GitHub). Board areas 31.5–18,903 mm²; 2–8 layers.
  - Four tasks: geometric, design-rule-aware, electrical-functionality, and tool-augmented agentic routing.
  - Results:

    | Router | Net routability ratio (NRR) | Pad-to-pad routability (PRR) |
    |---|---|---|
    | Best zero-shot LMM | 12.60% | 15.41% |
    | Agentic (with tools) | 27.98% | 30.34% |
    | Human reference | 93.58% | 95.91% |
    | PcbRouter (classical) | 56.20% | 71.37% |

  - Base LMM outputs average 69.8–431.3 DRC violations, vs 0.80 for humans.
  - Tools improve "local legality and routing-corridor selection more than global connectivity". "Feedback quality matters more than iteration count."
  - It notes most prior PCB routing studies used "fewer than 20 real-world board designs".
- [P] **RAC — Relational Agent Contract** (Zheng et al., arXiv Oct 2026) — [arXiv:2610.20935](https://arxiv.org/abs/2610.20935):
  - Agents emit only *relations over named objects* (proximity, alignment, keepouts, "matched routing, layer preference, and via limits"), never coordinates. A seeded deterministic backend realizes them, and an independent checker returns per-predicate repair evidence.
  - On 98 PCB placement/routing/repair tasks with 9 models, average clean-pass was:

    | Interface | Clean-pass |
    |---|---|
    | RAC (relations) | **90.9%** |
    | Requirements-only delegation | 74.0% |
    | Sequential relations | 62.4% |
    | Tool candidates (PCBWorld-style) | 37.4% |
    | Direct coordinates | 23.2% |

  - "The engineering contract matters more than model selection." Relations also survive board resizes (89.5% vs 65.6% re-solve pass).
- [A]/[P] **PCB-Bench** (ICLR 2026) evaluates LLMs on ~3,700 text QA instances, ~500 multimodal problems and >170 PCB projects (comprehension). It reveals "substantial gaps" in spatial reasoning but **does not test routing generation**. — [ICLR poster page](https://iclr.cc/virtual/2026/poster/10009621); [data](https://github.com/digailab/PCB-Bench)
- [P] **PCBWorld LLM results:** see above.

**VLSI learned routers and transferability**
- [S] **HubRouter** (NeurIPS 2023): two-phase "hub generation" with a generative model, then actor-critic pin-hub connection. It beats earlier generative global routers on wirelength, overflow and runtime, but "further decrease on overflow needs a reroute process". — [NeurIPS 2023](https://proceedings.neurips.cc/paper_files/paper/2023/hash/f7f98663c516fceb582354ee2d9d274d-Abstract-Conference.html)
- [S] **NeuralSteiner** (NeurIPS 2024): predicts candidate Steiner points from spatial and overflow information, with a graph post-process. Claims up to 99.8% overflow reduction with ≤1.8% wirelength loss vs generative routers. — [NeurIPS poster](https://neurips.cc/virtual/2024/poster/93636)
- [S] **DSBRouter** (ICML 2025): an end-to-end diffusion Schrödinger bridge between pin layout and routes, needing no connectivity post-step. Claims SOTA overflow on ISPD98 and part of ISPD07. — [PMLR v267](https://proceedings.mlr.press/v267/shi25k.html)
- [P] **PRNet** (NeurIPS 2022): one-shot conditional generative global router paired with RL macro placement. Its authors leave detailed routing out of scope. — [awesome-ai4eda list](https://github.com/Thinklab-SJTU/awesome-ai4eda); [OpenReview](https://openreview.net/pdf?id=uNYqDfPEDD8)
- [A] **CQL detailed-routing scheduler** (Khan & Rovinski, arXiv Dec 2025): an offline conservative Q-learning model "dynamically select[s] the routing cost weights" of an iterative detailed router. It reaches 1.56× average (up to 3.01×) faster convergence on ISPD19 with equal or better DRVs, with "signs of generalization across technologies". — [arXiv:2512.03594](https://arxiv.org/abs/2512.03594)
- [A] **XRoute** (2023): an RL environment over OpenROAD for net ordering and routing, with PPO/DQN vs TritonRoute baselines. **IJCAI 2025** follow-up: transformer RL net ordering. — [arXiv:2305.13823](https://arxiv.org/abs/2305.13823); [doi:10.24963/ijcai.2025/1055](https://doi.org/10.24963/ijcai.2025/1055)
- [P] **Background warning:** the ISPD 2024 invited talk "Challenges for Automating PCB Layout" (Liu, Agnesina, Ren — NVIDIA) frames PCB design as "typically semi-automated or fully manual". DeepPCB quotes it as citing a "lack of research progress in PCB routing algorithms" [V]. — [OpenAlex record (doi:10.1145/3626184.3635285)](https://api.openalex.org/works/doi:10.1145/3626184.3635285); [DeepPCB history blog](https://deeppcb.ai/the-60-year-routing-problem-nobody-solved/)

### Inferences
- **Transferability ranking from VLSI to PCB:**
  1. **High:** learned *control of a classical router*, i.e. cost-weight scheduling (CQL), net ordering (XRoute/IJCAI, DreamerV3+FR) and cost maps (Ranking Cost). These stay correct by construction because the classical router still guarantees legality.
  2. **Medium:** congestion and thermal predictors used as cost fields (TRouter, RUDY-style maps).
  3. **Low:** generative "draw the route" models (PRNet, HubRouter, DSBRouter, GPCB). Their outputs are gcell-level or need repair, and evaluation uses overflow on ISPD grids, not DRC on real boards. GPCB's 0.69% NRR on OmniRouting is the cautionary data point.
- DeepPCB's numbers, if they hold up, show a well-engineered RL router plus a setup agent can beat Freerouting on small 2-layer boards. The vendor's own scope still excludes the SI-critical net classes an LLM-driven system most needs help with (DDR, length matching, complex BGA fanout).
- RAC, PCBWorld and OmniRouting together give a design rule for the LLM layer: **LLM decides relations and intent; engines decide coordinates; checkers decide legality.**

### Gaps
- No peer-reviewed DeepPCB paper describing its observation, action or reward design was found. The "NeurIPS/ICML" publication claim is unverified; InstaDeep's known RL papers, such as Jumanji, are not routing papers. DeepPCB's PCBWorld-Bench numbers are vendor-run and not yet independently reproduced.
- The full texts of HubRouter, NeuralSteiner, DSBRouter, GPCB and DreamerV3+FR were not read (abstract or snippet only). The web-search budget ran out before PCBAgent (ASP-DAC 2025, a placement agent) and the 2025 "LLMs for PCB routing" (Engineering Proceedings) paper could be traced.
- Quilter's algorithm is known only from marketing and competitor pages.

---

## Q4. Freerouting internals, KiCad's PNS push-and-shove router, and how to drive push-and-shove programmatically

### Takeaway
**Freerouting** (GPL, Java, DSN→SES; v2.5.0 released 2026-10-05; 2.6.0-RC4 nightly):
- Pipeline: fanout, then batch A* over expansion rooms with escalating rip-up, then a keep-or-undo optimizer.
- Its own nightly benchmark shows "clean" completion rising from ~31–36% (v1.9/2.4.1) to 92.4% (2.6.0-RC4) on ~1,000 real boards, partly from DRC-measurement fixes.
- Published comparisons that used Freerouting 2.1.0 (PCBWorld) therefore likely understate it.

**KiCad PNS:**
- A local engine: build an initial 45° two-segment line toward a target point. Then:
  - **walkaround**: cw/ccw around clearance hulls, iteration-limited;
  - **shove**: a line stack, nearest obstacle by kind (solid→via→segment→hole), re-walk obstacles around hull sets, springback through branched NODE states.
- Then a corner-cost optimizer. Its "Autoroute/Finish" is just ≤5 `Move()` calls toward the nearest ratsnest anchor, **not a global search**.

**Scripting PNS:**
- PCBWorld-Engine (GPLv3) already exposes it to Python through a pybind11 module with ~90 calls, including checkpoint/restore.
- KiCad's IPC API offers only `RunAction` for router actions, a Specctra DSN export / session import round trip (KiCad 11), and item CRUD.

### Cited Findings

**Freerouting: lineage, pipeline, settings, scoring**
- [P] **Lineage:** v1.9.0's `project-info.gradle` lists developers "Andras Fuchs, Michael Hoffer, Andrey Belomutskiy, Alfons Wirtz". Its Eagle ULP acknowledges "an earlier design by Thomas Kaeubler and Alfons Wirtz". Current master is porting 260 commits of improvements from a C# port ("freerouting.net" by Erik Gavriluk). — [v1.9.0 project-info.gradle](https://github.com/freerouting/freerouting/blob/v1.9.0/gradle/project-info.gradle); [eagle2freerouting.ulp](https://github.com/freerouting/freerouting/blob/v1.9.0/integrations/Eagle/eagle2freerouting.ulp); [migration doc](https://github.com/freerouting/freerouting/blob/master/docs/migrating_Eriks_improvements_part_2.md)
- [P] **Releases:** v2.4.1 (2026-09-03) and v2.5.0 (2026-10-05), from the git history. Other tags back to v1.9.0 include v2.0.0–v2.4.0. — [freerouting git history](https://github.com/freerouting/freerouting)
- [P] **Pipeline:** "DSN input → parser → board and rule model → autorouter → design-rule checking → SES output". The optimizer rips up and reroutes locally, keeping a change only if better. — [architecture.md](https://github.com/freerouting/freerouting/blob/master/docs/architecture.md)
- [P] **Default costs:** `via_costs` 50, `plane_via_costs` 5, `start_ripup_costs` 100, preferred/undesired trace cost 1.0/2.5, autorouter `max_passes` 100, fanout `max_passes` 20. — [settings.md](https://github.com/freerouting/freerouting/blob/master/docs/settings.md)
- [P] **V2 scores:**
  - Router score (0–1000) = 1000 minus penalties for incomplete connections and clearance violations, scaled by D = max(1, pins × signal layers).
  - Optimizer score: excess length, vias and bends vs placement-derived lower bounds, with completeness and DRC as gates.

  — [scoring.md](https://github.com/freerouting/freerouting/blob/master/docs/scoring.md)
- [P] **Interfaces:** CLI, REST API, MCP server (`npx @freerouting/freerouting-mcp-server`), KiCad JSON writer, KiCad IPC research. — [README](https://github.com/freerouting/freerouting); [MCP.md](https://github.com/freerouting/freerouting/blob/master/docs/API/MCP.md); [kicad_ipc_api_research.md](https://github.com/freerouting/freerouting/blob/master/docs/research/kicad_ipc_api_research.md)
- [P] **Nightly benchmark** (report generated 2026-10-20, Ryzen 5 3600) — [benchmarks.md](https://github.com/freerouting/freerouting/blob/master/scripts/benchmark/results/benchmarks.md):

  | Version | Fixtures | Clean (0 DRC) | Fully routed |
  |---|---|---|---|
  | 1.9.0 | 1,142 | 36.2% | 49.3% |
  | 2.4.1 | 1,142 | 31.3% | 52.3% |
  | 2.5.0 | 1,142 | 75.2% | 75.5% |
  | 2.6.0-RC3 | 1,142 | 87.7% | 87.8% |
  | 2.6.0-RC4 | 979 (smaller set) | 92.4% | 92.5% |

  - By tier: Tier A (452 two-layer canaries) is 100% clean from 2.6.0-RC1. Tier B (527 boards, 2–4 layers) reaches 86.0% at RC4. Tier C (141 dense/6+-layer boards) reaches 69.5% at RC3. Tier D (22 stress boards) stays at only 13.6–18.2%.
  - Fixtures include ~1,143 PCBench-derived DSNs, the DAC2020 bm01–bm11 boards, and KiCad 10 demo boards.
- [P] **Caveat on what "clean" means:**
  - "Clean (0 DRC)" counts Freerouting's own clearance check ("0 unrouted, 0 clearance violations expected"), not KiCad DRC.
  - The 2.4.1→2.5.0 window includes "eliminate false-positive clearance violations on composite pads and rounding noise" (#925). Part of the jump is measurement change, not routing change.
  - The PCBench README warns "KiCad DSN export omits copper-to-edge clearance (Issue 558)" and treats KiCad DRC as the arbiter.

  — [MarkdownExporter.ps1](https://github.com/freerouting/freerouting/blob/master/scripts/benchmark/lib/MarkdownExporter.ps1); [git log](https://github.com/freerouting/freerouting); [pcbench README](https://github.com/freerouting/freerouting/blob/master/scripts/pcbench/README.md)
- [P] **KiCad 11 API round trip:** `RunBoardJobExportSpecctraDsn` and `ImportSpecctraSession` ("Since: 11.0"; repositions footprints, replaces unlocked tracks/vias). — [board_commands.proto](https://gitlab.com/kicad/code/kicad/-/blob/master/api/proto/board/board_commands.proto); [board_jobs.proto](https://gitlab.com/kicad/code/kicad/-/blob/master/api/proto/board/board_jobs.proto)

**KiCad PNS internals (KiCad master, read from source)**
- [P] **Router API** (`PNS::ROUTER`):
  - Routing: `StartRouting(p, item, layer)`, `Move(p, item)`, `FixRoute(p, item, forceFinish, forceCommit)`, `Finish()`, `ContinueFromEnd`, `UndoLastSegment`, `CommitRouting`, `StopRouting`.
  - Session controls: `SwitchLayer`, `ToggleViaPlacement`, `FlipPosture`, `SetOrthoMode`, `ToggleCornerMode`.
  - Dragging: `StartDragging(p, item|itemset, mode)` with modes `DM_CORNER`/`SEGMENT`/`VIA`/`FREE_ANGLE`/`ARC`/`COMPONENT`/`BLOCK`.
  - Settings: `SetMode` (`PNS_MODE_ROUTE_SINGLE`, `ROUTE_DIFF_PAIR`, `TUNE_SINGLE`, `TUNE_DIFF_PAIR`, `TUNE_DIFF_PAIR_SKEW`), `UpdateSizes`, `LoadSettings`, `GetNearestRatnestAnchor`.

  — [pns_router.h](https://gitlab.com/kicad/code/kicad/-/blob/master/pcbnew/router/pns_router.h)
- [P] **Host abstraction (`ROUTER_IFACE`):** a host must provide:
  - world sync and item add/update/remove;
  - visibility and flashing queries;
  - `Commit`, `ImportSizes`, `StackupHeight`, `GetRuleResolver`;
  - length and delay calculators (`CalculateRoutedPathLength`, `CalculateRoutedPathDelay`, `CalculateLengthForDelay`);
  - layer mapping.

  This interface is what lets PNS run outside the pcbnew GUI, as in Horizon EDA and PCBWorld-Engine. — [pns_router.h](https://gitlab.com/kicad/code/kicad/-/blob/master/pcbnew/router/pns_router.h); [Horizon EDA README](https://github.com/horizon-eda/horizon)
- [P] **World model (`NODE`):** a "spatial-indexed container", collision search and clearance checking, "assembly of lines connecting joints", and "lightweight cloning/branching (for recursive optimization and shove springback)". Key calls: `Branch()`, `Commit()`, `NearestObstacle`, `CheckColliding`, `AssembleLine`. — [pns_node.h](https://gitlab.com/kicad/code/kicad/-/blob/master/pcbnew/router/pns_node.h)
- [P] **Line placer logic:**
  - **Walkaround** (`rhWalkBase`): an initial 45° line is built (`buildInitialLine`), and `WALKAROUND::Route` is run with cw/ccw policies. Both results are optimized (`MERGE_SEGMENTS`), and the shorter collision-free one is taken.
  - **Shove** (`rhShoveOnly`): first walks around *solids only* (pads cannot be shoved), then runs `SHOVE` on the new head. If shove fails it **falls back to walkaround**. Smart-pads optimization is applied in 45° corner modes.

  — [pns_line_placer.cpp](https://gitlab.com/kicad/code/kicad/-/blob/master/pcbnew/router/pns_line_placer.cpp)
- [P] **Walkaround internals:** obstacle clusters are turned into cached clearance hulls, and the line is walked around each hull (`LINE::Walkaround`) clockwise and counter-clockwise. The loop runs until an iteration limit, with early abort when the path length exceeds a length-expansion factor of the initial path. — [pns_walkaround.cpp](https://gitlab.com/kicad/code/kicad/-/blob/master/pcbnew/router/pns_walkaround.cpp)
- [P] **Shove internals:**
  - A line stack drives the loop. Each iteration finds the nearest obstacle of the current line, searching kinds in the order SOLID → VIA → SEGMENT → HOLE, and dispatches it:
    - solids → walk around;
    - vias → push or shove the via with a force vector;
    - segments/arcs → re-walk the obstacle line around a hull set built at clearance around the current line's segments and via.
  - Status codes: `SH_OK`, `SH_INCOMPLETE`, `SH_TRY_WALK`.
  - The main loop stops on stack empty, `SH_INCOMPLETE`, the time limit or the iteration limit.
  - "Springback" keeps a stack of branched NODEs and pops frames that no longer collide with the head.
  - Per-line shove policies: `SHP_SHOVE`, `SHP_WALK_FORWARD`/`BACK`, `SHP_IGNORE`, `SHP_DONT_OPTIMIZE`, `SHP_DONT_LOCK_ENDPOINTS`.
  - Changed lines are then re-optimized.

  — [pns_shove.cpp](https://gitlab.com/kicad/code/kicad/-/blob/master/pcbnew/router/pns_shove.cpp); [pns_shove.h](https://gitlab.com/kicad/code/kicad/-/blob/master/pcbnew/router/pns_shove.h)
- [P] **Default limits:** shove iteration limit 250, shove time limit 1000 ms, walkaround iteration limit 40, walkaround hug-length threshold 1.5, diff-pair gap pickup ratio 2.5. — [pns_routing_settings.cpp](https://gitlab.com/kicad/code/kicad/-/blob/master/pcbnew/router/pns_routing_settings.cpp)
- [P] **Optimizer:** `COST_ESTIMATOR::CornerCost`, plus flags `MERGE_SEGMENTS`, `MERGE_OBTUSE`, `MERGE_COLINEAR`, `SMART_PADS`, `FANOUT_CLEANUP`, `KEEP_TOPOLOGY`, `PRESERVE_VERTEX`, `RESTRICT_AREA`, `LIMIT_CORNER_COUNT`. Effort levels are `OE_LOW`/`MEDIUM`/`FULL`. — [pns_optimizer.cpp](https://gitlab.com/kicad/code/kicad/-/blob/master/pcbnew/router/pns_optimizer.cpp); [pns_routing_settings.h](https://gitlab.com/kicad/code/kicad/-/blob/master/pcbnew/router/pns_routing_settings.h)
- [P] **"Autoroute" is not search:**
  - `ROUTER::Finish()` gets the nearest ratsnest anchor, then calls `Move(otherEnd)` up to 5 times until the head stops moving. It calls `FixRoute` only if the head reached the anchor on an overlapping layer.
  - `ROUTER_TOOL::RouteSelected` (the action `pcbnew.InteractiveRouter.Autoroute`, "Attempt Finish Selected (Autoroute)") loops over selected items in selection order, posting `AttemptFinish` per ratsnest edge and grouping successes into one undo commit.
  - Per the docs, it uses only the current layer, with no vias.

  — [pns_router.cpp](https://gitlab.com/kicad/code/kicad/-/blob/master/pcbnew/router/pns_router.cpp); [router_tool.cpp](https://gitlab.com/kicad/code/kicad/-/blob/master/pcbnew/tools/router_tool.cpp); [pcb_actions.cpp](https://gitlab.com/kicad/code/kicad/-/blob/master/pcbnew/tools/pcb_actions.cpp); [KiCad docs](https://gitlab.com/kicad/services/kicad-doc/-/blob/master/src/pcbnew/pcbnew_editing.adoc)
- [P] **KiCad has no global autorouter.** `pcbnew/autorouter/` holds only the footprint autoplacer. — [GitLab tree](https://gitlab.com/kicad/code/kicad/-/tree/master/pcbnew/autorouter)
- [P] **IPC API:** `RunAction` (by name; "low-level prototyping purposes only"), selection, `HitTest`, commit-scoped item CRUD. There is no route or shove RPC. — [editor_commands.proto](https://gitlab.com/kicad/code/kicad/-/blob/master/api/proto/common/commands/editor_commands.proto)
- [P] **Headless replay:** KiCad ships `qa/tools/pns` (log player, debug tool, `qa_pns_regressions`) that replays router logs. — [qa/tools/pns](https://gitlab.com/kicad/code/kicad/-/tree/master/qa/tools/pns)

**PCBWorld-Engine: a working recipe for scripted PNS** — [PCBWorld-Engine repo](https://github.com/LGAI-Research/PCBWorld-Engine) ([CHANGELOG](https://github.com/LGAI-Research/PCBWorld-Engine/blob/main/CHANGELOG.md), [`pns_rl_bindings.cpp`](https://github.com/LGAI-Research/PCBWorld-Engine/blob/main/kicad-patches/rl/pns_rl_bindings.cpp))
- [P] **Build:**
  - Pins upstream KiCad 9.0.8 as a submodule and overlays full-file patches.
  - Patched files: `pns_router`, `pns_node`, `pns_shove`, `pns_walkaround`, `pns_line_placer`, `pns_optimizer`, `pns_topology`, `pns_kicad_iface`, `pns_item`, `pns_joint`, `pns_mouse_trail_tracer`, `pns_routing_settings`, `ratsnest_data`, `tracks_cleaner`, `drc_engine`, `drc_rtree`, `kiid`, among others.
  - New code (~8.8k lines): a headless RL router (`pns_rl_router.cpp`, 3.7k lines), a DRC fork, and the pybind11 module `kicad_rl_router`.
- [P] **Exposed calls (selection):**
  - routing: `set_routing_mode`, `set_corner_mode`, `set_track_width`, `start_route`, `move`, `fix_route`, `finish`, `cancel_route`, `undo_last_segment`, `flip_posture`, `set_via_placement`, `switch_layer`;
  - dragging: `start_drag`/`fix_drag`;
  - DRC: `run_drc`, `run_drc_incremental`, `get_drc_violations_by_net`;
  - board state: `get_ratsnest`, `get_unrouted_count`, `get_tracks`/`get_vias`/`get_pads`;
  - state management: `checkpoint`/`restore`/`restore_incremental`, `optimize_all_lines` (v1.1.0), `lock_net`, `delete_routing_of_nets`, `set_shove_iter_limit`, `save`.
- [P] **Determinism:** "PNS items are ordered by geometry … with UUIDs only as a tie-break", "Shove and walkaround loops are bounded by iteration limits rather than wall-clock time", and the KIID generator can be seeded.
- [P] **DRC changes:** the stock per-type report caps are lifted (exact counts), and an R-tree leak is fixed.
- [P] **License boundary:** the GPL engine runs as a separate server process. The BSD environment talks to it over a unix socket and they are "never combined into one distributable".

**Other open routers usable with KiCad**
- [P] **KRT** (MIT):
  - Rust A*, MPS ordering, rip-up, diff pairs, length/time matching, buses, planes, BGA/QFN fanout, and Claude Code skills that plan and run routing.
  - Stated limits: "No push-and-shove", "No blind or buried vias", "No coarse grid assignment", "No design rules by region".

  — [KRT README](https://github.com/drandyhaas/KiCadRoutingTools)
- [P] **PcbRouter** (OpenROAD, BSD-3; `.kicad_pcb` v5.1.2): grid A* with diff pairs and rip-up. — [repo](https://github.com/The-OpenROAD-Project-Attic/PcbRouter)
- [P] **OrthoRoute:** PathFinder on GPU, via KiCad IPC. — [repo](https://github.com/bbenchoff/OrthoRoute)
- [P] **tscircuit capacity-autorouter** (MIT). — [repo](https://github.com/tscircuit/tscircuit-autorouter)
- [P]/[V] **DeepPCB plugin:** commercial cloud engine via an Apache-2.0 plugin. — [repo](https://github.com/instadeepai/deeppcb-kicad-plugin)

### Inferences
- **PNS is the right "geometric realizer", but only with a planner.** `Finish()` is a cursor-follow heuristic, so global success depends on someone supplying waypoints, layer changes and order. That someone could be RL (PCBWorld PPO), an LLM, or a global router.
- PCBWorld-Engine's `checkpoint`/`restore` plus deterministic loops make PNS usable inside **search**: beam search or MCTS over waypoint and mode choices, with DRC deltas as rewards. That is a natural next step beyond PCBWorld's single-policy rollouts.
- **Freerouting has changed materially in the last six weeks** (v2.5.0, 2.6.0-RC series). Any comparison should pin a version and re-score with KiCad DRC.

### Gaps
- Whether `RunAction("pcbnew.InteractiveRouter.Autoroute")` works in a headless KiCad 10/11 session, and whether KiCad plans first-class routing RPCs, was not confirmed. A web search for KiCad API routing plans could not run: the search budget was exhausted.
- The algorithmic content of the C# freerouting.net improvements being ported was not reviewed beyond the migration plan's phase list.
- No independent KiCad-DRC re-scoring of Freerouting 2.5/2.6 on PCBWorld-Bench was found.

---

## Q5. Why autorouters produce "ugly"/unacceptable results; the basis of autorouter skepticism

### Takeaway
The companion supplement covers this in depth. Evidence added in this pass from benchmarks and vendors:
- Classical routers fail most on dense multilayer stress boards: Freerouting Tier D is 14–18% clean.
- LLMs fail badly on raw geometry: OmniRouting's base LMMs average 70–431 DRC violations vs 0.8 for humans.
- Even vendors of AI routers scope out SI-critical classes.
- Humans optimize for structure, not just length and vias. Human reference boards are longer than DeepPCB's and Freerouting's outputs, yet are the gold standard.

### Cited Findings
- [P] PCBWorld: rule-based routers "rarely complete complex production boards end-to-end". On D3-A, Freerouting's wirelength (156 mm) and vias (0.74) beat the human reference (170 mm, 1.18) while its CP was 0.80. — [PCBWorld](https://arxiv.org/abs/2607.05915)
- [P] Freerouting nightly, Tier D (22 "high net-count and large surface-area stress boards"): only 13.6–18.2% clean across 2.6.0-RC2/RC3. — [benchmarks.md](https://github.com/freerouting/freerouting/blob/master/scripts/benchmark/results/benchmarks.md)
- [P] OmniRouting: LMM failures include "routing GND as ordinary traces instead of implementing continuous ground polygons and return-current paths". — [arXiv:2608.04434](https://arxiv.org/abs/2608.04434)
- [V] DeepPCB scopes out "DDR nets, length matching, advanced impedance control, and RF-specific constraints". A competitor says DeepPCB's public checks are geometric only, with no circuit-aware SI/PI checks. — [deeppcb.ai](https://deeppcb.ai/); [Quilter guide](https://www.quilter.ai/blog/the-2026-guide-to-autonomous-pcb-design-quilter-vs-deeppcb-vs-flux-ai)
- [P] ISPD 2024 talk (NVIDIA): PCB design "is typically semi-automated or fully manual". — [OpenAlex](https://api.openalex.org/works/doi:10.1145/3626184.3635285)

### Inferences
- "Ugly" has two separate causes that need different fixes:
  - **Legality and completion failures**, fixed by better engines and DRC loops.
  - **Intent failures** (return paths, grouping, SI), fixed by explicit constraints and relational intent from the planner.

### Gaps
- Practitioner-forum sentiment is in the supplement.

---

## Q6. Hybrid approaches: human/AI-guided routing and topology planning followed by geometric realization

### Takeaway
Every successful 2026 system is staged and intent-driven:
- **DeepPCB:** a human routes the critical nets, Cooper fixes the setup, the RL engine finishes the rest.
- **KRT:** an LLM plan of pours → diff pairs → bulk → length matching → repair.
- **DreamerV3+FR:** RL chooses the net order, Freerouting draws.
- **FanoutNet:** RL fanout feeds a negotiated A*.

RAC gives the cleanest experimental support for the split: let the model own **semantic relations** and a deterministic realizer own **geometry**.

### Cited Findings
- [V] DeepPCB: "the critical nets were routed by hand first and the engine finished the rest". Cooper takes plain-language setup ("mark these as diff pairs") "before a trace is drawn". — [deeppcb.ai](https://deeppcb.ai/)
- [P] KRT `/plan-pcb-routing`: analyzes fanout needs, diff pairs, DDR groups, power nets and speeds, then generates and runs a JSON plan, replayable headless. — [KRT claude-skills.md](https://github.com/drandyhaas/KiCadRoutingTools/blob/main/docs/claude-skills.md)
- [A] DreamerV3+FR: world-model RL optimizes Freerouting net ordering "before physical execution". — [OpenAlex](https://api.openalex.org/works/doi:10.1016/j.eswa.2026.131424)
- [P] FanoutNet: RL decides fanout, and the MCR (negotiated 3-D A*) routes. — [AAAI 2023](https://ojs.aaai.org/index.php/AAAI/article/view/26030/25802)
- [P] RAC: relational actions reach 90.9% vs direct coordinates 23.2% and requirements-only 74.0%. Relations stay reusable when the board changes. — [arXiv:2610.20935](https://arxiv.org/abs/2610.20935)
- [P] PCBWorld engine engagement: interactive CP 0.65 vs plan-and-execute 0.19 vs engine-free 0.02. — [PCBWorld](https://arxiv.org/abs/2607.05915)
- [P] OmniRouting: a "Preroute" tool raised reference-similarity (MGS) for all eight models (GPT-5.5 from 18.45% to 30.23%), while connectivity stayed low. Tools help corridor selection more than completion. — [arXiv:2608.04434](https://arxiv.org/abs/2608.04434)
- [P] Freerouting preserves fixed copper exactly ("Preserved traces … must retain their exact geometry") and can ignore net classes (`-inc`). Critical nets can therefore be pre-routed and frozen before bulk autorouting. — [architecture.md](https://github.com/freerouting/freerouting/blob/master/docs/architecture.md); [README](https://github.com/freerouting/freerouting)

### Inferences
- "Topology sketch, then realization" maps onto the evidence:
  1. The LLM emits relations and corridors, RAC-style.
  2. A capacity check (RUDY overflow) validates them.
  3. Realization uses Freerouting, KRT-style A*, or PNS waypoints.
  4. KiCad DRC verifies, and per-predicate failures return to the LLM.

### Gaps
- No study yet isolates an *LLM-chosen* net order or corridor against defaults on real multilayer boards. RAC's tasks are small synthetic placement/routing tasks.

---

## Q7. Benchmarks and datasets for PCB routing

### Takeaway
Public real-board PCB routing data grew sharply in 2024–2026:
- **PCBench**: 1,194 KiCad designs from 846 repos per its metadata; its README still says 164.
- **PCBWorld-Bench**: 679 cleaned PCBench boards plus synthetic sets, with KiCad-DRC metrics.
- **OmniRouting**: 1,681 EAGLE designs, 2–8 layers.
- **PCB-Bench**: LLM QA and comprehension.
- **ASP-DAC 2021 PCBBenchmarks** (bm1–bm11, KiCad): reused by FanoutNet, TRouter and Freerouting as "DAC2020".
- **Freerouting's** ~1,142-fixture nightly corpus.

Industrial benchmarks (e.g. FanoutNet's Huawei boards) remain private.

### Cited Findings
- [P] **PCBench:**
  - `master_metadata.json` reports "Num. Unique pcb designs": 1194 from 846 repos (133 from Kitspace; KiCad-only).
  - Each board has `raw.kicad_pcb`, `processed.kicad_pcb` and PCB-RDL `final.json`.
  - The README still says "164 printed circuit boards". PCBWorld's 679 is the subset still fully connected and DRV-free after conversion to KiCad 9. This resolves the first-pass discrepancy.

  — [PCBench master_metadata.json](https://github.com/PCBench/PCBench/blob/main/PCBs/master_metadata.json); [PCBench README](https://github.com/PCBench/PCBench); [PCBWorld](https://arxiv.org/abs/2607.05915)
- [V] DeepPCB notes that "the benchmark's data cleaning re-routes every copper-pour net with an autorouter (PCBench notes)". It therefore compares against the reference only on nets without pours. — [DeepPCB PCBWorld-Bench page](https://deeppcb.ai/benchmark/pcbworld-bench-deeppcb-results/)
- [P] **PCBWorld-Bench:**
  - D1 grid (Jumanji-Connector replica, sizes 10–500).
  - D2 synthetic gridless (10,000/128/128 split).
  - D3-A/B/C (100/287/292 boards by pad count; up to 451 nets, 2,103 pads, 8 layers).
  - 8 metrics; best-of-5 and @1 protocols.

  — [PCBWorld](https://arxiv.org/abs/2607.05915)
- [P] **OmniRouting:** 1,681 designs; 77.24K placements, 168.82K pads, 55.83K annotated net connections, 84.60K vias, 4.31K pours. Metrics are NRR, PRR, opens, shorts, DRC and Multi-Scale Graph Similarity to the human reference. — [arXiv:2608.04434](https://arxiv.org/abs/2608.04434)
- [P] **ASP-DAC 2021 PCBBenchmarks:** "KiCad PCB benchmarks for automated layout", bm1–bm11, blinded for review. Freerouting's `Issue508-DAC2020_bm01.dsn` header path reads `…\DAC_2020_Benchmarks_Without_Routing\bm1\bm1.unrouted.dsn`, matching this set. FanoutNet lists bm1–bm11 at 15–99 nets and 2–4 layers. TRouter uses "benchmarks … from PCBRouter". — [PCBBenchmarks repo](https://github.com/aspdac-submission-pcb-layout/PCBBenchmarks); [Freerouting fixture](https://github.com/freerouting/freerouting/blob/master/fixtures/Issue508-DAC2020_bm01.dsn); [FanoutNet](https://ojs.aaai.org/index.php/AAAI/article/view/26030/25802); [TRouter](https://www.cse.cuhk.edu.hk/~byu/papers/J94-TCAD2023-TRouter.pdf)
- [P] **Freerouting nightly:** 1,142 fixtures in tiers A–D; a PCBench pipeline that strips routing, exports DSN with `pcbnew.ExportSpecctraDSN`, and records ground truth via KiCad DRC. — [benchmarks.md](https://github.com/freerouting/freerouting/blob/master/scripts/benchmark/results/benchmarks.md); [pcbench README](https://github.com/freerouting/freerouting/blob/master/scripts/pcbench/README.md)
- [P] **PCB-Bench (ICLR 2026):** ~3,700 text instances, ~500 multimodal, >170 projects. Comprehension only. — [ICLR page](https://iclr.cc/virtual/2026/poster/10009621)
- [P] **tscircuit autorouting dataset:** synthetic problems with speed, completion and quality criteria. — [tscircuit/autorouting](https://github.com/tscircuit/autorouting)
- [P] **VLSI-only environments:** XRoute and Jumanji Connector. — [XRoute](https://github.com/xplanlab/xroute_env); [Jumanji Connector](https://github.com/instadeepai/jumanji/blob/main/docs/environments/connector.md)

### Inferences
- **A credible evaluation stack for an LLM-driven KiCad router:**
  - PCBWorld-Bench D3-A/B with @1 and @5 scoring, beside published Freerouting, KRT, PPO and DeepPCB numbers.
  - D3-C plus Freerouting Tier C/D as stress sets.
  - OmniRouting for multilayer and schematic-coupled tests (EAGLE-sourced; needs conversion).
  - A custom SI-constraint harness (coupling, skew, length-group spread, return vias), which no public benchmark scores.

### Gaps
- No ISPD/ICCAD PCB routing contest could be verified. The search budget was exhausted.
- The OmniRouting data release status ("will open-source") and its license are not yet confirmed.

---

## Implications for an LLM-driven KiCad router

### Takeaway
Build a **three-layer system**:
1. **LLM as relational planner.** It classifies nets, sets constraints, chooses the per-class engine, orders work, and sketches corridors as relations, not coordinates.
2. **Deterministic realizers.** Freerouting (latest 2.6.x) for bulk; KRT-style A* or the PNS DP placer for diff pairs and buses; PNS via a PCBWorld-Engine-style binding for waypoint realization, shove-based repair and smoothing; KiCad tuning for meanders; optionally DeepPCB's cloud engine for non-SI bulk nets.
3. **KiCad DRC plus SI checks** as the verifier, returning per-predicate evidence.

The 2026 evidence for this split:
- RAC: 90.9% vs 23.2% clean-pass.
- PCBWorld: 0.65 vs 0.02.
- OmniRouting: LLMs at 12.6% zero-shot NRR vs PcbRouter at 56.2%.

### Cited Findings
- [P] Relational actions beat coordinate emission across nine models. — [RAC](https://arxiv.org/abs/2610.20935)
- [P] Engine-grounded interaction beats open-loop. LLM per-step control is ~100× slower than a small PPO policy (231 s vs 1.83 s per D3-A board). — [PCBWorld](https://arxiv.org/abs/2607.05915)
- [P] PNS `Finish` is a ≤5-step cursor-follow, not a global router. — [pns_router.cpp](https://gitlab.com/kicad/code/kicad/-/blob/master/pcbnew/router/pns_router.cpp)
- [P] PCBWorld-Engine offers deterministic, checkpointable PNS calls from Python behind a process boundary. — [PCBWorld-Engine](https://github.com/LGAI-Research/PCBWorld-Engine)
- [P] Freerouting 2.5/2.6 are much stronger on its own corpus than the 2.1.0 used in PCBWorld. — [benchmarks.md](https://github.com/freerouting/freerouting/blob/master/scripts/benchmark/results/benchmarks.md)
- [V] DeepPCB reports top one-attempt PCBWorld-Bench scores. It routes signal nets and diff pairs with blind/buried vias up to 8 layers, but not DDR or length matching. — [DeepPCB results](https://deeppcb.ai/benchmark/pcbworld-bench-deeppcb-results/); [DeepPCB KiCad plugin](https://deeppcb.ai/kicad-autorouter-plugin/)
- [A] Learned cost-weight scheduling (CQL) and learned net ordering transfer best from VLSI. — [arXiv:2512.03594](https://arxiv.org/abs/2512.03594); [DreamerV3+FR](https://api.openalex.org/works/doi:10.1016/j.eswa.2026.131424)

### Approach comparison matrix

| Approach | Core idea | Rules / constraints | Scale and runtime evidence | Quality evidence | Open source | PCB relevance |
|---|---|---|---|---|---|---|
| Freerouting 2.x (gridless room A* + rip-up + optimizer) | A* over convex rooms with admissible multi-layer lower bound; escalating rip-up; keep-or-undo optimizer | Specctra rules; diff-pair and meander rules parsed, not routed | 1,142-board nightly; 2210-pin 2-layer pass 1748 s (RC9) | PCBWorld CP 0.80/0.78 (v2.1.0); own corpus 92% "clean" (RC4, internal DRC) | GPL | Bulk nets; 45° geometry; weak on SI classes |
| KRT (Rust octilinear A*) | Grid A* + MPS ordering + blocker-analysis rip-up | KiCad rules, diff pairs, length/time matching, buses | 47–51 nets in 6–9 s | PCBWorld CP 0.74/0.20 (paper-time version) | MIT | Direct KiCad integration, LLM skills; no shove |
| OpenROAD PcbRouter | Grid A* with 45°; diff pairs first; fixed-order rip-up iterations | Net classes, diff pairs | Not measured here | OmniRouting NRR 56.2% (best non-human) | BSD-3 | Permissive-license baseline; old KiCad 5 format |
| KiCad PNS (walkaround/shove) | Local cursor-follow line placement with hull walkaround, recursive shove and springback | Full KiCad rule resolver, DP gap, length/delay | Interactive; PPO-on-PNS ~2 s per small board | Engine behind best open learned results (PPO CP 0.86–0.94 on D3-A) | GPL | Ideal realizer and repair engine; needs a planner |
| PathFinder (OrthoRoute) | Negotiated congestion on a lattice | Lattice geometry only | GPU, thousands of nets (author claim) | CP ≤ 0.02 on ordinary boards | Yes | Backplanes; global planning concept |
| FanoutNet (PPO fanout + negotiated A*) | RL picks fanout location and layer per net; MCR routes | Diff pairs, shielding, spacing in A* cost | 245 min average on 6-layer industrial boards | 100% routability vs Freerouting 81%, NB-A* 95% | No | BGA/HDI fanout planning |
| DreamerV3 + Freerouting | World-model RL chooses net order | Freerouting rules | Not reported here | 96% completion (abstract) | Code linked | Learned ordering for bulk router |
| PCBWorld PPO (engine actions) | Small transformer picks waypoint and mode via PNS | Engine plus DRC reward | ~2–15 s per board | Beats Freerouting 2.1.0 on D3-A, loses on D3-B | BSD env + GPL engine | Learned local completion |
| DeepPCB (commercial RL) | Custom C++ simulator, TPU/Ray-trained RL engine, setup agent | Clearance matrices, net classes, diff pairs, planes; no DDR or length matching | Minutes per typical board; completion falls past ~1,200 airwires | Vendor @1 CP 0.929/0.800 on D3-A/B (2-layer) | Plugin only (Apache-2.0) | Optional cloud bulk router |
| LLM direct geometry | LLM emits coordinates | None (post-hoc DRC) | Slow | OmniRouting NRR ≤12.6% zero-shot; PCBWorld engine-free CP 0.02 | — | Do not use |
| LLM relational (RAC) | LLM emits relations; tool realizes | Checker per predicate | ≤5 model calls per task | 90.9% CP on 98 small tasks | Paper | Recommended LLM interface |
| Generative VLSI routers (HubRouter, NeuralSteiner, DSBRouter, GPCB) | Generate gcell routes or tokens | Overflow only (VLSI); GPCB PCB | GPU-fast | ISPD overflow SOTA; GPCB 0.69% NRR on OmniRouting | Some | Low transfer |

### Inferences (concrete recommendations)

1. **Action interface for the LLM (RAC-style).** No coordinates. Use typed relations such as:
   - `route_class(net_class, engine, layers, width, via_policy)`
   - `pair(netP, netN, gap, max_uncoupled)`
   - `match_group(nets, tol_ps, reserve_area=region)`
   - `corridor(net|bus, via=[regions], layer)`
   - `order(tiers)`, `keepout(region, classes)`, `lock(nets)`, `return_vias(pair|class)`

   Realizers turn these into geometry, and the checker returns per-relation pass/fail with object IDs.

2. **Engine per net class.**
   - **Escape/fanout first.** Use deterministic pattern generators or a ring search for legal standard vias; FanoutNet-style learned fanout is a research option. Lock the result.
   - **Diff pairs and impedance nets.** Pose-space centerline A* (KRT) or PNS DP placer with LLM-chosen waypoints. Then PNS skew tuning and return vias.
   - **Length groups.** Bus routing with reserved meander regions, then PNS meander tuning (point-to-point only) or KRT trombones.
   - **Bulk.** Freerouting 2.6.x with LLM-set costs (via cost, layer directions, rip-up), or DeepPCB's API where cloud upload is acceptable and the nets are not SI-critical.
   - **Repair and smoothing.** PNS shove-mode re-routes of failed connections from waypoints, then `optimize_all_lines`/`OptimizeSelected`.

3. **Search over PNS.** Use PCBWorld-Engine `checkpoint`/`restore` to run beam search or MCTS over (waypoint candidate, walk/shove mode, layer switch) for the hardest residual connections, with reward = ΔDRC + Δunrouted − λ·Δlength. This uses the engine's deterministic, iteration-bounded loops.

4. **Cheap ML that transfers.** Learn (or let the LLM propose and an optimizer refine) **net order and cost-weight schedules** for Freerouting or KRT. This mirrors DreamerV3+FR, Ranking Cost and CQL. It keeps legality guaranteed by the classical engine.

5. **Evaluation.**
   - Report PCBWorld-Bench @1 and @5. The bar is Freerouting 0.80/0.78 @5 (v2.1.0); DeepPCB's vendor @1 is 0.929/0.800.
   - Re-score the latest Freerouting with KiCad DRC.
   - Add SI predicates and an OmniRouting multilayer subset.
   - Track LLM tokens and time per board: per-step LLM control costs ~100× more time than RL or classical routers.

6. **Licensing pattern.** Keep GPL engines (PNS fork, Freerouting) as separate processes behind a socket or CLI, as PCBWorld-Engine does. This keeps the orchestration layer's license choice open.

### Gaps
- There is still no head-to-head of an LLM relational planner plus classical realizers vs Freerouting/DeepPCB on real multilayer boards with SI constraints. This is the key experiment to run first.
- Whether DeepPCB's API permits automated, programmatic use inside a third-party orchestration system (terms, rate limits) was not reviewed.
