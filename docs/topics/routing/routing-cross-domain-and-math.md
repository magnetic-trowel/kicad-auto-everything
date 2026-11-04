# Dense-region routing: neighbouring domains, math and topology

Scope: convergence machinery from FPGA/VLSI routers, global-routing ideas, MAPF-LNS2, and exact routability theorems, for re-routing dense (BGA) windows. Not here: basic PathFinder/VPR defaults -> [PathFinder](pathfinder-negotiated-congestion.md); MAPF basics -> [cross-domain transplants](cross-domain-routing-transplants.md); certificate ladder -> [certificates](routing-infeasibility-certificates.md).
Keys: oscillation, history-centric negotiation, alt-weights, HUS, Revisiting PathFinder, connection-based rip-up, CRoute, RWRoute, nextpnr router2, VPR failure predictor, dynamic bounding box, TritonRoute, clip, route box, DRC box, stubborn tiles, FlexDR strategy, TritonRoute-WXL, Dr. CU, GRIP, floating terminals, column generation, BonnRoute, resource sharing, FastRoute, CUGR, GAMER, InFO RDL, MAPF-LNS2, SIPPS, CBSH2-RTC, Okamura–Seymour, cut condition, Cole–Siegel, Schrijver homotopic, flux, circle graph, LDS, thickness

**Results**
1. Our earlier region-wide PathFinder oscillated. FPGA routers ship three fixes: history-centric negotiation (present cost constant or slow, history does the work: nextpnr `alt-weights`, HUS switch, "Revisiting PathFinder"); connection-based rip-up of conflicted connections only, with dynamic bounding boxes; a log-linear failure predictor that stops non-converging runs.
2. Better fits than global PathFinder for "re-route a BGA window": MAPF-LNS2 (repair a few conflicting nets, accept only non-increasing conflicts: monotone progress) and TritonRoute's clip schedule (small shifted windows, three boxes per clip, decaying marker history, 3×3 cost portfolio for stubborn tiles).
3. Fixed boundary crossings inherited from Freerouting can alone make a window infeasible; GRIP-style floating terminals let the solver choose where nets cross the window edge.
4. Exact tests exist only in narrow cases: max-flow (unordered escape); Okamura–Seymour (terminals on one face); Cole–Siegel/Schrijver cut condition (fixed topology); longest decreasing subsequence and circle-graph clique (layer counts with fixed order). Everything else is a sound but loose bound → [certificates](routing-infeasibility-certificates.md).
5. Choosing the topology is the NP-hard part (single-layer routing NP-complete; edge-disjoint paths NP-complete even in grids): exact search pays only on small residual windows.

### 1. FPGA routers: convergence machinery

| Router | Mechanism | Parameters |
|---|---|---|
| VPR / VTR 8 ([docs](https://docs.verilogtorouting.org/en/latest/vpr/command_line_usage/), [`route.cpp`, `routing_predictor.cpp`](https://github.com/verilog-to-routing/vtr-verilog-to-routing) [P]) | Dynamic bounding boxes: a net whose tree touches its box gets a bigger box. Initial history seeded on channels predicted above 50% use. Keeps the best legal routing; re-converges with present cost reset. "CONFLICTED" mode stops delay-driven rip-up and widens every box; source comment: small boxes "can cause conflicts to oscillate back and forth" | Defaults → [PathFinder](pathfinder-negotiated-congestion.md) |
| VPR failure predictor [P] | Least-squares fit of log(overused nodes) vs iteration over the last 50% of iterations, from iteration 8. Aborts if predicted zero-overuse iteration > 3× budget (`safe`) or 1.5× (`aggressive`). Never aborts below 100 overused nodes | Lower that floor for windows with tens of conflicts |
| Connection router / CRoute (Vansteenkiste, Bruneel, Stroobandt) [S] | Unit = source→sink connection, not net; only connections on overused nodes re-routed. Cost ÷ (1 + same-net users) rewards sharing within a net | 84% faster than VPR on hard cases |
| RWRoute (RapidWright, [code](https://github.com/Xilinx/RapidWright) [P]) | Cost = base·hist·present/sharing + bias toward net centre; reroutes when unrouted, congested or critical | present 0.5 ×2 per iteration, history 1, ≤ 100 iterations |
| HUS (Zang, Lin, Lin, Liu, Young, [arXiv 2407.00009](https://arxiv.org/abs/2407.00009) [P]) | If iteration 1 flags the design congested, switch once to history-centric costs when most remaining conflicts are in congested areas | present multiplier 2 → 1.1, history 1 → 2; up to 4.5× faster, 16% less wirelength on congested FPGA'24-contest designs. Thresholds 0.5 / 0.4 from a secondary reading [S] |
| "Revisiting PathFinder" (Zha & Li, FPGA'22, cited by HUS) [S] | Fast present-cost growth causes order dependence; constant present cost + history removes it given enough iterations | p_f 1, h_f 5, up to 1,500 iterations |
| nextpnr router2 ([`router2.cc`](https://github.com/YosysHQ/nextpnr/blob/master/common/route/router2.cc) [P]) | Present weight +2 per iteration (additive). `alt-weights`: present constant 5, history 0.5. Failed nets re-shuffled each iteration; legal arcs kept; an arc failing in its box retried without the box; no iteration cap | weighted A* 1.25, bb margin 3 |

### 2. VLSI detailed routing: windows with fixed boundaries

**TritonRoute** (Kahng, Wang, Xu, TCAD 2021, [PDF](https://vlsicad.ucsd.edu/Publications/Journals/j133.pdf) [P]):
- Clips 7×7 GCells, one worker per clip; offsets shift between iterations so seams move.
- Three nested boxes per clip: route box (objects may change), DRC box (markers count), extended box (fixed context). Nets crossing the clip edge get boundary pins: outside connectivity never changes.
- Worker loop: (1) add marker cost; (2) rip up nets touching markers, ordered by distance to marker; (3) reserve every ripped net's pin-access via; (4) route nets one by one; (5) DRC.
- Edge cost = length × (1 + 8·[object cost] + 64·[marker cost]); pessimistic object cost guards against cycling (authors).

**OpenROAD search-and-repair schedule** (`FlexDR.cpp` `strategy()`, [repo](https://github.com/The-OpenROAD-Project/OpenROAD/tree/master/src/drt) [P]): 65 rows; early rows rip up everything in a clip, later rows only nets with violations; maze iterations per worker 8 → 64; DRC cost ×1 → ×64; marker cost ×1 → ×16; marker decay 0.95 → 0.999; periodic rip-all rows at clip sizes 5 and 3 as kicks; below ~100 violations "stubborn tiles": each marker cluster runs 9 workers with cost multipliers {½, 1, 2}², best wins.

**TritonRoute-WXL** ([PDF](https://vlsicad.ucsd.edu/Publications/Journals/j136.pdf) [P]): queue replaces batch rounds; a marker's earlier-routed net (aggressor) is re-routed, the later net (victim) only re-checked; stale entries skipped; per-net reroute cap; converged on all ISPD'18/19 cases, −33.5% runtime.

**Dr. CU** ([TCAD 2020](https://chengengjie.github.io/papers/J3-TCAD20-DrCU.pdf) [P]): history charged only on a wire's violating interval, fading; min-area as soft Lagrangian penalty; four rip-up iterations; non-overlapping nets batched in parallel.

None of these claims convergence: they plateau at 0–5 violations and finish with portfolios.

### 3. Global routing ideas

- **GRIP** (Wu, Davoodi, Linderoth, DAC'09, [PDF](https://jlinderoth.github.io/papers/Wu-Davoodi-Linderoth-09.pdf) [P]): path ILP min Σ c·x + M·Σ slack, one route per net or slack, Σ usage ≤ capacity; column generation (pricing = shortest path under duals) then branch-and-bound; recursive regions with floating terminals on region borders; zero overflow on all ISPD'07 cases except known-unroutable newblue3.
- **BonnRoute min-max resource sharing** (Müller, Radke, Vygen, [MPC 2011](https://doi.org/10.1007/s12532-011-0023-y); [slides](https://www.or.uni-bonn.de/home/vygen/files/rs-new.pdf) [P]): multiplicative-weights prices, σ(1+ω) approximation; any price vector gives a lower bound → [certificates](routing-infeasibility-certificates.md).
- Other global routers [S]: FastRoute virtual capacity (dual update on edges that stay overflowed); NTHU-Route 2.0 history-based costs, congested regions in order of size; NCTU-GR 2.0 bounded-length maze routing (detours bounded under high history); Archer history as Lagrange multipliers; CUGR / CUGR2 (DAC'20 / DAC'23) 3D pattern DP → maze, rip-up of overflowed nets only, logistic congestion cost; HeLEM-GR ([ICCAD'24](https://doi.org/10.1145/3676536.3676650)) exponential multipliers, resource-sharing-like update.
- GPU ideas usable in numba [S]: GAMER ([ICCAD'21](https://ieeexplore.ieee.org/document/9643563)) alternating row/column prefix-min sweeps give exact grid shortest paths in parallel (fits computing every net's exact cost under given prices); InstantGR and Dr. CU batch non-overlapping nets deterministically in parallel.

### 4. Flip-chip, InFO and RDL

[S]
- InFO RDL (Lin, Lin, Chang, [ICCAD'16](https://doi.org/10.1145/2966986.2967070)): concentric-circle model, flow for free pad assignment.
- Cai, Hsu, Chang (TCAD'22): layer assignment = weighted maximum planar subset of chords (nets with ends on a circle share a layer only if chords do not cross), Supowit's DP O(n²)–O(n³); A* on octagonal tiles; MCMF for chip-to-board nets.
- Fang/Chang flip-chip: MCF for free assignment, ILP for pre-assigned nets.

### 5. MAPF, beyond what we have

**MAPF-LNS2** (Li, Chen, Harabor, Stuckey, Koenig, [AAAI'22](https://ojs.aaai.org/index.php/AAAI/article/view/21266), [code](https://github.com/Jiaoyang-Li/MAPF-LNS2) [P]):
1. Start: prioritized planning; unroutable agents get minimum-collision paths.
2. Loop until 0 colliding pairs: pick a neighbourhood of N = 8 agents; re-plan in random order, each minimizing soft collisions, ties by length; accept if colliding pairs ≤ before (plateau moves allowed).
3. Neighbourhood generators: random-walk component of the collision graph; failure-based (agents blocking a high-degree agent's start or goal); random weighted by degree + 1. Adaptive choice w ← 0.1·Δconflicts + 0.9·w.
- Adaptive mix beats each single generator: success at 400 agents 0.48–0.76 → 0.88. 300 agents on random-32-32-20 in 2.7 s where prioritized planning with restarts failed; unsolved runs ended with 1–2 colliding pairs.
- Static setting: the planner SIPPS reduces to lexicographic A* on (conflicts, length).

**Symmetry reasoning** (CBSH2-RTC, [arXiv 2103.07116](https://arxiv.org/abs/2103.07116) [P, partial]): rectangle and corridor conflicts resolved in one branch (barrier constraints or "who passes first"); up to 4 orders of magnitude fewer nodes. Static analogue: two nets wanting the one track between two balls → branch on gap ownership.

Others [S]: EECBS (bounded-suboptimal, ~50 conflicting agents), LaCAM3, large-agent MAPF (footprint = width + clearance), BCP (branch-and-cut-and-price with LP bounds).

### 6. Other domains, transferable ideas only

[S]
- Optical routing and wavelength assignment: path-LP column generation bounds often integral or nearly: evidence that a GRIP-style LP bound is tight on small windows.
- Railway path allocation: pairwise conflicts aggregated into clique constraints (e.g. "≤ 1 net through this gap's clearance zone"); tightens the LP where plain capacities miss crossings.
- Warehouse highways: one-way lanes ≈ per-layer escape directions (Pfeil's layer-biased escapes, [BGA survey](bga-routing-survey.md)).
- Robotics braids: multirobot mixing via braid groups (Diaz-Mercado & Egerstedt, T-RO 2017) and H-signatures deduplicate homotopy classes; not certificates. No PCB/VLSI braid-group formulation found.
- Quantum-chip wiring and microfluidics: nothing beyond small ILPs on planar instances.

### 7. Math and topology

| Result | Precise statement | What it gives us |
|---|---|---|
| NP-completeness | Disjoint paths NP-complete, even planar (Lynch 1975). Two-point nets in a grid NP-complete (Kramer–van Leeuwen 1984, [report](https://dspace.library.uu.nl/handle/1874/16302)). Eulerian edge-disjoint paths in grids NP-complete (Marx, [DAM 2004](https://doi.org/10.1016/j.dam.2003.12.003)). Single-layer routing without given topology NP-complete (Richards 1984) [S] | No exact polynomial certificate in general; exact proofs need SAT or ILP on small windows |
| Robertson–Seymour, fixed k; planar k-disjoint paths (Schrijver [SIAM J. Comput. 1994](https://dblp.dagstuhl.de/rec/journals/siamcomp/Schrijver94.html); Cygan et al. [FOCS'13](https://www.cs.bme.hu/~dmarx/papers/cygan-planardir-focs2013.pdf)) [S] | Polynomial or FPT in k, tower-type constants | Useless at k in the hundreds; usable idea: enumerate topology, then solve fixed homotopy |
| One-face vertex-disjoint paths (Robertson–Seymour, in Schrijver "Homotopic routing methods", [CWI](https://ir.cwi.nl/pub/2348/2348D.pdf), Thm 3 [P]) | Terminals on one face: routable iff every closed curve crosses G at least as often as the pairs it separates, and no two pairs interleave around the face | Exact test for nets whose ends all lie on a window border |
| Okamura–Seymour 1981 ([lecture](https://math.mit.edu/~goemans/18438F09/OLD/lec23-o.pdf) [P]) | G planar, all terminals on outer face, G + demand edges Eulerian: edge-disjoint paths exist iff the cut condition holds. Only O(b²) boundary-interval cuts (b = boundary length), each a dual shortest path. Okamura 1983: two faces if each pair sits on one face. Without parity: half-integral. Hurkens–Schrijver–Tardos: fractional feasible but integrally infeasible. Linear time (Wagner–Weihe, [PDF](https://math.mit.edu/~goemans/18438F09/wagnerweihe.pdf)). No exact node-capacity version ([arXiv 1209.2744](https://arxiv.org/abs/1209.2744)) [S] | BGA balls are interior terminals: no direct fit. Fits the outside of an escaped window only when destinations are also on the border |
| Flow–cut gaps | Planar, terminals on γ faces: O(log γ), tight ([arXiv 1811.02685](https://arxiv.org/abs/1811.02685)). General planar: O(√log n). General graphs: O(log k) [S] | Cut bounds close to fractional optimum on grids; integrality gap is the larger practical gap |
| Cole–Siegel / Leiserson–Maley, restated by Iso, Kawaguchi, Hirata ([ASP-DAC'97](https://www.cecs.uci.edu/~papers/compendium94-03/papers/1997/aspdac97/pdffiles/09c_3.pdf) [P]) | Single layer, topology given: routable iff every cut (segment between two mutually visible features) has capacity ≥ wires that must cross it. Unit lattice: capacity = L∞ distance − 1. Cut (a, b) redundant if an empty triangle abc has cap(a,b) ≥ cap(a,c) + cap(c,b) | Exact per-layer test of a given topology; names the failing pad pair |
| Schrijver homotopic theorems ([CWI](https://ir.cwi.nl/pub/2348/2348D.pdf) Thm 31, 33; [edge-disjoint](https://ir.cwi.nl/pub/2371/2371D.pdf) [P]) | Vertex-disjoint paths of given homotopy, planar graph, any number of holes: polynomial; exact iff curves cross-free, cut condition cr(G,D) ≥ Σ mincr(C_i,D), and a strict version on "doubly odd" closed curves. Edge-disjoint homotopic: NP-complete in general (Kaufmann–Maley), exact with parity in the straight-line case | Generalizes SURF and Cole–Siegel to our grid graph with every pad as a hole |
| Maley thesis "Single-layer wire routing" ([MIT 1987](https://dspace.mit.edu/handle/1721.1/14657)) [S] | Only shortest cuts and rubber-band wires matter; fewer critical cuts in the rectilinear metric | Prunes the cut set |
| Channel lower bounds [S] | Density (max nets across a column); vertical-constraint cycles force doglegs (Szymanski TCAD'85, NP-complete). Baker–Bhatt–Leighton flux ([MIT TM-238](https://dspace.mit.edu/handle/1721.1/149048)): width ≥ ~√(nets leaving a central window); routes in 2d + O(f) | Density = gap cut between balls; flux = ring cut |
| Book embedding, circle graphs (Chung–Leighton–Rosenberg 1987; Unger [STACS'88](https://doi.org/10.1007/BFb0035832); [arXiv 2309.02258](https://arxiv.org/abs/2309.02258)) [S] | Fixed boundary order: via-free layer assignment = colouring the chords' crossing graph; NP-complete for k ≥ 4; Unger's 3-colouring algorithm shown wrong in 2023 (k = 3 open); 2 = bipartite test; max clique polynomial (Gavril), so ω ≤ layers | Exact cheap lower bound on via-free layers |
| Permutation graphs (Dilworth) [S] | Two-sided fixed order (bus to connector): min via-free layers = longest decreasing subsequence, O(n log n); inversions = forced crossings | Bus layer bound; a pin swap that shortens the LDS saves a layer |
| Thickness [S] | θ ≥ ⌈m/(3n − 6)⌉; NP-hard to compute | Weak on PCBs (vias are free-standing) |

### 8. Proposed window-routing method for kae

[I]
1. Window reroute (work item 2) as LNS, not global PathFinder: treat a BGA window as MAPF-LNS2; every window net routed with conflicts allowed; lexicographic A* on (conflicting cells with other nets, length + via cost); repair 4–16 nets at a time, chosen adaptively from three generators; accept if conflicting pairs do not rise. Reuses `lastmile.py`'s grid and A*, replaces its greedy rip-up rounds inside the window.
2. If PathFinder stays: history-centric costs from iteration 1 (router2 `alt-weights`: present 5, history 0.5) or the HUS switch; connection-based reroute, order shuffled under a seed; dynamic boxes; keep the best state; VPR-style predictor with a floor of ~3 conflicts; stop and hand over to the certificate ladder when the slope of log(conflicts) ≥ 0 for 10 iterations.
3. Floating terminals: each net's window crossing = an interval of the border on any allowed layer (one super-terminal); re-stitch outside the window with the last mile.
4. TritonRoute clips for big BGAs: clips ~6–10 ball pitches wide, offsets shifted per pass; route, DRC and context boxes; reserve pin-access vias first; marker history with decay; 3×3 cost portfolio on stubborn tiles.
5. Exact residual solve: with ≤ ~10 conflicting nets left, CP-SAT or MonoSAT on the residual sub-window with other nets fixed, or CBS branching on gap ownership. UNSAT proves only "infeasible with the others fixed": then grow the free set (LNS neighbourhood).
6. Topology test after Freerouting: Cole–Siegel/Schrijver cut test per layer on the routed topology. Rules-level certificates pass + this test fails → fix = re-topologize (rip-up), not relax rules.

## Open questions

- HUS thresholds (0.5, 0.4) not visible in the arXiv HTML; only the 2 → 1.1 and 1 → 2 switch values were.
- CRoute, NCTU-GR, NTHU-Route, FastRoute and EECBS read from abstracts or memory only.
- No study measures LNS vs PathFinder on PCB windows: our experiment to run.

## Sources

- Primary sources linked inline. Related: [PathFinder](pathfinder-negotiated-congestion.md) · [topological](topological-routing.md) · [cross-domain transplants](cross-domain-routing-transplants.md) · [certificates](routing-infeasibility-certificates.md) · [BGA survey](bga-routing-survey.md)
