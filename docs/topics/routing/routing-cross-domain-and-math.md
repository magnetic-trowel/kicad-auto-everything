# Dense-region routing: neighbouring domains, math and topology

**TL;DR**
- Our earlier region-wide PathFinder oscillated. FPGA routers have three shipped fixes for that:
  - history-centric negotiation: present cost held constant or grown slowly, history doing the work (nextpnr `alt-weights`, the HUS switch, "Revisiting PathFinder");
  - connection-based rip-up of conflicted connections only, with dynamic bounding boxes;
  - a log-linear failure predictor that stops a run that will not converge.
- Two transplants fit "re-route a BGA window" better than global PathFinder:
  - **MAPF-LNS2**: repair a few conflicting nets at a time and accept only moves that do not increase conflicts, so progress is monotone.
  - **TritonRoute's clip schedule**: small windows, shifted offsets, three boxes per clip, decaying marker history, and a 3×3 cost portfolio for stubborn tiles.
- Fixed boundary crossings inherited from Freerouting can make a window infeasible on their own. GRIP-style **floating terminals** let the solver choose where nets cross the window edge.
- The math gives exact tests only in narrow cases:
  - max-flow, for unordered escape;
  - Okamura–Seymour, for terminals on one face;
  - the Cole–Siegel and Schrijver cut condition, for a fixed topology;
  - the longest decreasing subsequence and circle-graph clique, for layer counts with a fixed order.
  Everything else is a sound but loose bound. [Certificates](routing-infeasibility-certificates.md) turns these into a ladder.
- Choosing the topology is the NP-hard part (single-layer routing NP-complete; edge-disjoint paths NP-complete even in grids). Exact search only pays on small residual windows.

This doc extends [cross-domain-routing-transplants](cross-domain-routing-transplants.md), [pathfinder-negotiated-congestion](pathfinder-negotiated-congestion.md) and [topological-routing](topological-routing.md) without repeating them.

## Key facts

### 1. FPGA routers: convergence machinery

| Router | Mechanism | Parameters |
|---|---|---|
| VPR / VTR 8 ([docs](https://docs.verilogtorouting.org/en/latest/vpr/command_line_usage/), [`route.cpp`, `routing_predictor.cpp`](https://github.com/verilog-to-routing/vtr-verilog-to-routing) [P]) | Dynamic bounding boxes: a net whose tree touches its box gets a bigger box. Initial history is seeded on channels predicted above 50% use. Keeps the best legal routing and re-converges with present cost reset. "CONFLICTED" mode stops delay-driven rip-up and widens every box; the source comment says small boxes "can cause conflicts to oscillate back and forth" | Defaults are in [pathfinder-negotiated-congestion](pathfinder-negotiated-congestion.md) |
| VPR failure predictor [P] | Least-squares fit of log(overused nodes) against iteration over the last 50% of iterations, from iteration 8 on. Aborts if the predicted zero-overuse iteration is more than 3× the budget (`safe`) or 1.5× (`aggressive`). Never aborts below 100 overused nodes | Lower that floor for windows with tens of conflicts |
| Connection router / CRoute (Vansteenkiste, Bruneel, Stroobandt) [S] | Unit is the source→sink connection, not the net; only connections on overused nodes are re-routed. Cost divided by (1 + same-net users) rewards sharing within a net | 84% faster than VPR on hard cases |
| RWRoute (RapidWright, [code](https://github.com/Xilinx/RapidWright) [P]) | Cost = base·hist·present/sharing + a bias toward the net centre. Reroutes when unrouted, congested or critical | present 0.5 ×2 per iteration, history 1, ≤ 100 iterations |
| HUS (Zang, Lin, Lin, Liu, Young, [arXiv 2407.00009](https://arxiv.org/abs/2407.00009) [P]) | If iteration 1 flags the design as congested, switch once to history-centric costs when most remaining conflicts are in congested areas | present multiplier 2 → 1.1, history 1 → 2. Up to 4.5× faster and 16% less wirelength on congested FPGA'24-contest designs. Thresholds 0.5 / 0.4 are from a secondary reading [S] |
| "Revisiting PathFinder" (Zha & Li, FPGA'22, cited by HUS) [S] | Fast present-cost growth is the source of order dependence. Constant present cost plus history removes it, given enough iterations | p_f 1, h_f 5, up to 1,500 iterations |
| nextpnr router2 ([`router2.cc`](https://github.com/YosysHQ/nextpnr/blob/master/common/route/router2.cc) [P]) | Present weight grows additively (+2 per iteration). `alt-weights` mode: present weight constant at 5, history 0.5. Failed nets are re-shuffled each iteration. Legal arcs are kept. An arc that fails in its box is retried without the box. No iteration cap | weighted A* 1.25, bb margin 3 |

### 2. VLSI detailed routing: windows with fixed boundaries

**TritonRoute** (Kahng, Wang, Xu, TCAD 2021, [PDF](https://vlsicad.ucsd.edu/Publications/Journals/j133.pdf) [P]):
- Clips are 7×7 GCells, one worker per clip. Offsets shift between iterations so seams move.
- Each clip has three nested boxes:
  - a *route box*, where objects may change;
  - a *DRC box*, where markers count;
  - an *extended box*, loaded as fixed context.
- Nets crossing the clip edge get boundary pins, so connectivity outside never changes.
- Worker loop:
  1. add marker cost;
  2. rip up the nets touching markers, ordered by distance to the marker;
  3. reserve every ripped net's pin-access via;
  4. route the nets one by one;
  5. run DRC.
- Edge cost = length × (1 + 8·[object cost] + 64·[marker cost]). The authors call the pessimistic object cost a guard against cycling.

**OpenROAD search-and-repair schedule** (`FlexDR.cpp` `strategy()`, [repo](https://github.com/The-OpenROAD-Project/OpenROAD/tree/master/src/drt) [P]):
- 65 rows.
- Early rows rip up everything in a clip; later rows only the nets with violations.
- Maze iterations per worker 8 → 64.
- DRC cost ×1 → ×64, marker cost ×1 → ×16, marker decay 0.95 → 0.999.
- Periodic rip-all rows at clip sizes 5 and 3 as kicks.
- Below about 100 violations: "stubborn tiles", where each marker cluster runs 9 workers with cost multipliers {½, 1, 2}², and the best wins.

**TritonRoute-WXL** ([PDF](https://vlsicad.ucsd.edu/Publications/Journals/j136.pdf) [P]):
- A queue replaces batch rounds. A marker's earlier-routed net (the aggressor) is re-routed; the later net (the victim) is only re-checked.
- Stale queue entries are skipped, and each net has a reroute cap.
- It converged on all ISPD'18/19 cases and cut runtime by 33.5%.

**Dr. CU** ([TCAD 2020](https://chengengjie.github.io/papers/J3-TCAD20-DrCU.pdf) [P]):
- History is charged only on the violating interval of a wire, and it fades.
- Min-area is a soft Lagrangian penalty.
- Four rip-up iterations.
- Non-overlapping nets are batched in parallel.

None of these routers claims convergence. They plateau at 0–5 violations and finish with portfolios.

### 3. Global routing ideas

- **GRIP** (Wu, Davoodi, Linderoth, DAC'09, [PDF](https://jlinderoth.github.io/papers/Wu-Davoodi-Linderoth-09.pdf) [P]):
  - Path ILP: min Σ c·x + M·Σ slack, one route per net or slack, Σ usage ≤ capacity.
  - Solved by column generation (pricing = a shortest path under the duals), then branch-and-bound.
  - Recursive regions with **floating terminals** on region borders.
  - Zero overflow on all ISPD'07 cases except the known-unroutable newblue3.
- **BonnRoute min-max resource sharing** (Müller, Radke, Vygen, [MPC 2011](https://doi.org/10.1007/s12532-011-0023-y); [slides](https://www.or.uni-bonn.de/home/vygen/files/rs-new.pdf) [P]):
  - Multiplicative-weights prices with a σ(1+ω) approximation.
  - Any price vector gives a lower bound ([certificates](routing-infeasibility-certificates.md)).
- **Other global routers** [S]:
  - FastRoute: virtual capacity, i.e. a dual update on edges that stay overflowed.
  - NTHU-Route 2.0: history-based costs, congested regions routed in order of region size.
  - NCTU-GR 2.0: bounded-length maze routing, so detours stay bounded under high history.
  - Archer: history read as Lagrange multipliers.
  - CUGR / CUGR2 (DAC'20 / DAC'23): 3D pattern DP, then maze routing, rip-up of overflowed nets only, logistic congestion cost.
  - HeLEM-GR ([ICCAD'24](https://doi.org/10.1145/3676536.3676650)): exponential multipliers, a resource-sharing-like update.
- **GPU ideas usable in numba** [S]:
  - GAMER ([ICCAD'21](https://ieeexplore.ieee.org/document/9643563)): alternating row and column prefix-min sweeps compute exact grid shortest paths in parallel. This suits computing every net's exact cost under given prices.
  - InstantGR and Dr. CU: batches of non-overlapping nets are deterministic and parallel.

### 4. Flip-chip, InFO and RDL

- InFO RDL (Lin, Lin, Chang, [ICCAD'16](https://doi.org/10.1145/2966986.2967070) [S]): concentric-circle model, flow for free pad assignment.
- Cai, Hsu, Chang (TCAD'22) [S]:
  - Layer assignment is a weighted **maximum planar subset of chords**: nets whose ends sit on a circle may share a layer only if their chords do not cross. Supowit's DP solves it in O(n²) to O(n³).
  - A* on octagonal tiles; MCMF for chip-to-board nets.
- Fang/Chang flip-chip [S]: MCF for free assignment, ILP for pre-assigned nets.

### 5. MAPF, beyond what we have

**MAPF-LNS2** (Li, Chen, Harabor, Stuckey, Koenig, [AAAI'22](https://ojs.aaai.org/index.php/AAAI/article/view/21266), [code](https://github.com/Jiaoyang-Li/MAPF-LNS2) [P]):
- Start: prioritized planning; agents it cannot route get minimum-collision paths.
- Loop until there are 0 colliding pairs:
  1. pick a neighbourhood of N = 8 agents;
  2. re-plan them in random order, each minimising soft collisions, ties broken by length;
  3. accept if colliding pairs ≤ before (plateau moves allowed).
- Neighbourhood generators:
  - a random-walk component of the collision graph;
  - *failure-based*: the agents blocking a high-degree agent's start or goal;
  - random, weighted by degree + 1.
- Generators are chosen adaptively: w ← 0.1·Δconflicts + 0.9·w.
- The adaptive mix beat each single generator: success at 400 agents 0.48–0.76 → 0.88.
- 300 agents on random-32-32-20 in 2.7 s, where prioritized planning with restarts failed. Unsolved runs ended with 1–2 colliding pairs.
- In a static setting the planner, SIPPS, reduces to lexicographic A* on (conflicts, length).

**Symmetry reasoning** (CBSH2-RTC, [arXiv 2103.07116](https://arxiv.org/abs/2103.07116) [P, partial]):
- Rectangle and corridor conflicts are resolved in one branch, either by barrier constraints or by "who passes first".
- Up to 4 orders of magnitude fewer nodes.
- The static analogue is two nets wanting the one track between two balls: branch on gap ownership.

**Others** [S]: EECBS (bounded-suboptimal, about 50 conflicting agents), LaCAM3, large-agent MAPF (footprint = width + clearance), BCP (branch-and-cut-and-price with LP bounds).

### 6. Other domains, transferable ideas only [S]

- **Optical routing and wavelength assignment.** Path-LP column generation gives bounds that are often integral or nearly so. This is evidence that a GRIP-style LP bound is tight on small windows.
- **Railway path allocation.** Pairwise conflicts are aggregated into clique constraints, e.g. "≤ 1 net through this gap's clearance zone". These tighten the LP where plain capacities miss crossings.
- **Warehouses (highways).** One-way lanes are the analogue of per-layer escape directions (Pfeil's layer-biased escapes, [BGA survey](bga-routing-survey.md)).
- **Robotics braids.** Multirobot mixing via braid groups (Diaz-Mercado & Egerstedt, T-RO 2017) and H-signatures are invariants for deduplicating homotopy classes. They are not certificates. No PCB or VLSI braid-group formulation was found.
- **Quantum-chip wiring and microfluidics.** Nothing beyond small ILPs on planar instances.

### 7. Math and topology

| Result | Precise statement | What it gives us |
|---|---|---|
| NP-completeness | Disjoint paths are NP-complete, even planar (Lynch 1975). Two-point nets in a grid are NP-complete (Kramer–van Leeuwen 1984, [report](https://dspace.library.uu.nl/handle/1874/16302)). Eulerian edge-disjoint paths in grids are NP-complete (Marx, [DAM 2004](https://doi.org/10.1016/j.dam.2003.12.003)). Single-layer routing without a given topology is NP-complete (Richards 1984) [S] | No exact polynomial certificate in general; exact proofs need SAT or ILP on small windows |
| Robertson–Seymour, fixed k; planar k-disjoint paths (Schrijver [SIAM J. Comput. 1994](https://dblp.dagstuhl.de/rec/journals/siamcomp/Schrijver94.html); Cygan et al. [FOCS'13](https://www.cs.bme.hu/~dmarx/papers/cygan-planardir-focs2013.pdf)) [S] | Polynomial or FPT in k, with tower-type constants | Useless at k in the hundreds. The idea "enumerate topology, then solve fixed homotopy" is the usable one |
| One-face vertex-disjoint paths (Robertson–Seymour, in Schrijver "Homotopic routing methods", [CWI](https://ir.cwi.nl/pub/2348/2348D.pdf), Thm 3 [P]) | Terminals on one face: routable iff every closed curve crosses G at least as often as the pairs it separates, and no two pairs interleave around the face | Exact test for nets whose ends are all on a window border |
| Okamura–Seymour 1981 ([lecture](https://math.mit.edu/~goemans/18438F09/OLD/lec23-o.pdf) [P]) | G planar, all terminals on the outer face, G + demand edges Eulerian: edge-disjoint paths exist iff the cut condition holds. Only O(b²) boundary-interval cuts need checking (b = boundary length), each a dual shortest path. Okamura 1983 extends this to two faces if each pair sits on one face. Without parity: half-integral. Hurkens–Schrijver–Tardos: fractional feasible but integrally infeasible. Linear time (Wagner–Weihe, [PDF](https://math.mit.edu/~goemans/18438F09/wagnerweihe.pdf)). No exact node-capacity version ([arXiv 1209.2744](https://arxiv.org/abs/1209.2744)) [S] | BGA balls are interior terminals, so it does not fit directly. It fits the *outside* of an escaped window only when destinations are also on the border |
| Flow–cut gaps | Planar graphs with terminals on γ faces: O(log γ), tight ([arXiv 1811.02685](https://arxiv.org/abs/1811.02685)). General planar: O(√log n). General graphs: O(log k) [S] | Cut bounds are close to the fractional optimum on grids. The integrality gap is the larger practical gap |
| Cole–Siegel / Leiserson–Maley, as restated by Iso, Kawaguchi, Hirata ([ASP-DAC'97](https://www.cecs.uci.edu/~papers/compendium94-03/papers/1997/aspdac97/pdffiles/09c_3.pdf) [P]) | Single layer, topology given: routable iff for every cut (a segment between two mutually visible features) capacity ≥ the number of wires that must cross it. On a unit lattice the capacity is the L∞ distance − 1. Cut (a, b) is redundant if an empty triangle abc has cap(a,b) ≥ cap(a,c) + cap(c,b) | Exact per-layer test of a *given* topology; names the failing pad pair |
| Schrijver homotopic theorems ([CWI](https://ir.cwi.nl/pub/2348/2348D.pdf) Thm 31, 33; [edge-disjoint](https://ir.cwi.nl/pub/2371/2371D.pdf) [P]) | Vertex-disjoint paths of given homotopy in a planar graph with any number of holes: polynomial; exact iff the curves are cross-free, the cut condition cr(G,D) ≥ Σ mincr(C_i,D) holds, and a strict version holds on "doubly odd" closed curves. Edge-disjoint homotopic: NP-complete in general (Kaufmann–Maley), exact with parity in the straight-line case | Generalises SURF and Cole–Siegel to our grid graph with every pad as a hole |
| Maley thesis "Single-layer wire routing" ([MIT 1987](https://dspace.mit.edu/handle/1721.1/14657)) [S] | Only shortest cuts and rubber-band wires matter; fewer critical cuts in the rectilinear metric | Prunes the cut set |
| Channel lower bounds [S] | Density (max nets across a column); vertical-constraint cycles force doglegs (Szymanski TCAD'85, NP-complete). Baker–Bhatt–Leighton *flux* ([MIT TM-238](https://dspace.mit.edu/handle/1721.1/149048)): width ≥ about √(nets leaving a central window); routes in 2d + O(f) | Density is the gap cut between balls; flux is the ring cut |
| Book embedding, circle graphs (Chung–Leighton–Rosenberg 1987; Unger [STACS'88](https://doi.org/10.1007/BFb0035832); [arXiv 2309.02258](https://arxiv.org/abs/2309.02258)) [S] | With a fixed boundary order, via-free layer assignment = colouring the chords' crossing graph. NP-complete for k ≥ 4. Unger's 3-colouring algorithm was shown wrong in 2023, so k = 3 is open. 2 is a bipartite test. Max clique is polynomial (Gavril), so ω ≤ layers | Exact cheap lower bound on via-free layers |
| Permutation graphs (Dilworth) [S] | Two-sided fixed order (bus to connector): min via-free layers = the longest decreasing subsequence, O(n log n). Inversions = forced crossings | Bus layer bound; pin swap that shortens the LDS saves a layer |
| Thickness [S] | θ ≥ ⌈m/(3n − 6)⌉; computing it is NP-hard | Weak on PCBs, because vias are free-standing |

## Recommendations for our system

1. **Window reroute (work item 2) as LNS, not global PathFinder.** Treat a BGA window as MAPF-LNS2:
   - every window net routed with conflicts allowed;
   - lexicographic A* on (conflicting cells with other nets, length + via cost);
   - repair 4–16 nets at a time, chosen adaptively from three generators;
   - accept if conflicting pairs do not rise.
   This reuses `lastmile.py`'s grid and A*, and replaces its greedy rip-up rounds inside the window [I].
2. **If PathFinder stays,** use history-centric costs from iteration 1 (router2 `alt-weights`: present 5, history 0.5) or the HUS switch:
   - connection-based reroute, with the order shuffled under a seed;
   - dynamic boxes;
   - keep the best state;
   - a VPR-style predictor with a floor of about 3 conflicts. Stop and hand over to the certificate ladder when the slope of log(conflicts) is ≥ 0 for 10 iterations [I].
3. **Floating terminals.** Let each net's window crossing be an interval of the border on any allowed layer (one super-terminal), and re-stitch outside the window with the last mile [I].
4. **TritonRoute clips for big BGAs:**
   - clips about 6–10 ball pitches wide, offsets shifted per pass;
   - route, DRC and context boxes;
   - reserve pin-access vias first;
   - marker history with decay;
   - a 3×3 cost portfolio on stubborn tiles [I].
5. **Exact residual solve.** With ≤ about 10 conflicting nets left, run CP-SAT or MonoSAT on the residual sub-window with the other nets fixed, or CBS branching on gap ownership. UNSAT proves only "infeasible with the others fixed", so then grow the free set (an LNS neighbourhood) [I].
6. **Topology test after Freerouting.** Run the Cole–Siegel/Schrijver cut test per layer on the routed topology. If the rules-level certificates pass and this test fails, the fix is re-topologising (rip-up), not relaxing rules [I].

## Conflicts and open questions
- The HUS thresholds (0.5, 0.4) were not visible in the arXiv HTML; only the 2 → 1.1 and 1 → 2 switch values were.
- CRoute, NCTU-GR, NTHU-Route, FastRoute and EECBS were read from abstracts or memory only.
- No study measures LNS against PathFinder on PCB windows; that is our experiment to run.

## Sources
- Primary sources are linked inline.
- See also: [pathfinder-negotiated-congestion](pathfinder-negotiated-congestion.md) · [topological-routing](topological-routing.md) · [cross-domain-routing-transplants](cross-domain-routing-transplants.md) · [routing-infeasibility-certificates](routing-infeasibility-certificates.md) · [bga-routing-survey](bga-routing-survey.md)
