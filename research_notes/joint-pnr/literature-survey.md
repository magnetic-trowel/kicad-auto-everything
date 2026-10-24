# Joint PCB placement + routing: mechanisms from other fields

Scope: mechanisms you can build into a grid-based Python/numba prototype for 2-layer boards with 10–50 parts. **W** rates how easily each fits in a weekend prototype (1 = hard, 5 = easy). Verification: I checked every citation by web search (October 2026). Where I only saw secondary sources, the entry says so. Ideas marked *(synthesis)* are my own extrapolations, not claims from a paper.

---

## 1. VLSI/FPGA placement with real routing in the loop

**Nag & Rutenbar, "Performance-Driven Simultaneous Placement and Routing for FPGAs", IEEE TCAD, June 1998** (IEEE Xplore; cited e.g. in https://www.dejazzer.com/doc/2005_TCAD_ppff.pdf). This is simulated annealing over placement in which every move rips up and re-routes the affected nets with an actual (detailed) router. The cost is the real routed delay and routability, not an estimate. Later papers report up to about 15% better performance at 6–11x the runtime of timing-driven VPR (TVPR). *Transfer:* at 10–50 parts that runtime cost doesn't matter. A move (shift, swap or rotate) rips up only the nets on the moved part and re-routes them with a numba A* over the current occupancy, and the cost is routed length + vias + unrouted penalty. **W5.**

**Sharma, Ebeling & Hauck, "Independence: architecture-adaptive routability-driven placement for FPGAs", FPGA 2005** (https://people.ece.uw.edu/hauck/publications/Independence_J.pdf). Puts a PathFinder negotiated-congestion router (McMurchie & Ebeling 1995) in the inner loop of the annealer, replacing the placement cost estimate with actual routing results. *Transfer:* keep PathFinder's **history costs persistent across placement moves**. They then act as a memory of where the board is chronically congested, which steers later moves away from those spots. **W4.**

**Pan & Chu, "IPR: An Integrated Placement and Routing Algorithm", DAC 2007** (https://home.engineering.iastate.edu/cnchu/pubs/c46.pdf). Runs global routing (FastRoute) inside the placement flow (FastPlace/FastDP). Placement changes are driven by the routed overflow map rather than an estimate. It reports 36% less overflow than the earlier ROOSTER placer. *Transfer:* outer loop of place → route all nets → locate overflow and detour hot spots → move parts locally → re-route. **W4.**

**Kim, Hu, Lee & Markov, "A SimPLR Method for Routability-driven Placement", ICCAD 2011** (https://web.eecs.umich.edu/~imarkov/pubs/conf/iccad11-simplr.pdf). Couples the BFG-R global router to the SimPL analytical placer. "Lookahead routing" of the intermediate placement gives a congestion map. Cells in congested regions are **dynamically bloated** (spread apart), and cells in uncongested regions are pulled together. *Transfer:* inflate each footprint's effective keep-out in proportion to the routed congestion around it, re-legalize, and repeat. Simple and robust. **W5.**

**Routability-driven placement with congestion estimates**: RippleFPGA (Chen et al., TCAD 2018, https://www.cse.cuhk.edu.hk/~byu/papers/J33-TCAD2018-RippleFPGA.pdf) and NTUplace4dr (Huang et al., TCAD 2018, https://scholars.lib.ntu.edu.tw/handle/123456789/405629). Both rely on congestion estimates plus routing-aware legalization and detailed placement. **W2.**

**Learned differentiable congestion**: Liu et al., "Global Placement with Deep Learning-Enabled Explicit Routability Optimization", DATE 2021 (https://past.date-conference.com/proceedings-archive/2021/pdf/1290.pdf), uses an FCN congestion predictor inside DREAMPlace and backpropagates its gradient to cell positions. RoutePlacer (arXiv 2406.02651, 2024) does the same with a GNN. *Transfer:* train a small CNN on your own router's congestion outputs, then use it as a fast differentiable proxy between real routes. **W2–3** (needs data).

**Lee et al., "SP&R: SMT-Based Simultaneous Place-and-Route for Standard Cell Synthesis of Advanced Nodes", IEEE TCAD 40(10), 2021** (https://cseweb.ucsd.edu/classes/fa23/cse248-a/papers/cells/SMT-Based.pdf). Encodes placement and routing on a grid as one SMT problem with multi-objective optimization, using dynamic pin allocation and symmetry breaking. It solves cells with up to 36 FETs and 27 nets, **about the same size as a small PCB**. *Transfer:* encode a coarse grid (e.g. 1 mm pitch) for CP-SAT (OR-Tools), or use it as a large-neighbourhood repair: free a window holding 3–6 parts and their nets and solve that window exactly. **W3.**

## 2. Differentiable routing and routed-cost gradients

**Berthet et al., "Learning with Differentiable Perturbed Optimizers", NeurIPS 2020** (arXiv 2002.08676). Defines y_ε(θ) = E[argmin(θ+εZ)] and gets the gradient by Monte Carlo over noisy solver calls. *Transfer:* the cost grid θ (from footprints, existing traces and history) depends on part positions. Run the numba A* N times under cost noise; the average path occupancy is a **soft routing density** and d(expected cost)/dθ. Chain it to (x, y) through a smoothed footprint mask. **W4.**

**Vlastelica Pogančić et al., "Differentiation of Blackbox Combinatorial Solvers", ICLR 2020** (arXiv 1912.02175). Uses a gradient proxy (y(θ+λ·∂L/∂y) − y(θ))/λ that needs only two solver calls; it was shown on grid shortest paths. *Transfer:* the same use as above, but deterministic and cheap. **W4.**

**Mensch & Blondel, "Differentiable Dynamic Programming", ICML 2018** (arXiv 1802.03676) and **Petersen et al., "Learning with Algorithmic Supervision via Continuous Relaxations", NeurIPS 2021** (arXiv 2110.05651, relaxed Bellman-Ford). Replacing min with soft-min (log-sum-exp) gives a smooth value function whose gradient with respect to the edge costs is the expected edge usage. *Transfer:* soft value iteration from each pin in numba gives a smooth "where would this net go" field. Summing it over nets gives a differentiable congestion map, and footprint overlap with that map yields forces on the parts. **W4.**

**"DGR: Differentiable Global Router", DAC 2024** (https://dl.acm.org/doi/10.1145/3649329.3656530). Builds a DAG forest of candidate routing trees (pattern routes) per net, relaxes the choice with Gumbel-softmax plus temperature annealing and top-p selection, and minimizes overflow + wirelength on a GPU, with one tree chosen per net. *Transfer:* generate K candidates per net (L, Z, U and A* variants, each on either layer). Then optimize the candidate logits **and** continuous part positions together; candidates are defined relative to pins, so they translate with the parts. **W3.**

**Lagrangian view of negotiated congestion** *(synthesis, grounded in Lagrangian global routing, e.g. "Pathfinding Model and Lagrangian-Based Global Routing", DAC 2023).* PathFinder's history costs act like Lagrange multipliers on capacity constraints. At a routing equilibrium the envelope theorem applies: d(routed cost)/dx_part equals the partial derivative with the routes held fixed. That gives two terms: (a) at each pin, the unit vector of the first route segment, pointing out of the pad (a "tension"); (b) where routes wrap around the moved footprint, the boundary cells weighted by their multipliers. *Transfer:* a cheap, exact-at-equilibrium gradient taken straight from existing routes, which can drive a force-directed placer between re-routes. **W5.**

## 3. Other domains with coupled layout and networks

**Columba (Tseng, Li, Li, Ho, Schlichtmann), DAC 2016; Columba 2.0, TCAD 2018; Columba S, DAC 2018** (https://mediatum.ub.tum.de/doc/1349440/document.pdf). Microfluidic chips with simultaneous P&R of the flow and control layers. The key is a **planarity-guaranteed architectural model**: placement is restricted to a template in which routing is guaranteed to exist. Columba S uses straight-channel routing to scale past 200 units. *Transfer:* restrict placement to rows or columns with reserved routing channels, a template where a channel router always succeeds, then relax the template. This works well for 2 layers (one layer horizontal, the other vertical). **W3.**

**Zhou et al., "Apollo: Automated Routing-Informed Placement for Large-Scale Photonic ICs", ICCAD 2025** (arXiv 2504.18813). An analytical placer with an asymmetric bending-aware wirelength, explicit penalties for **waveguide crossings** and congestion, and constraints enforced gradually by projection. *Transfer:* on 2 layers every crossing between nets costs a via or a layer change. Penalize the crossing count of the net MSTs or star segments with a smooth segment-intersection term. **W4.**

**Ou, Chien & Chang, "Simultaneous Analog Placement and Routing with Current Flow and Current Density Considerations", DAC 2013** (DOI 10.1145/2463209.2488739). An enhanced B*-tree represents modules **and their interconnect** together, so annealing over the tree perturbs both. *Transfer:* add wire-channel pseudo-blocks between connected parts to a sequence-pair or B*-tree packing, so routing space is reserved during packing. **W3.**

**Facility layout with aisles and I/O points**: Kim & Goetschalckx (contour-distance block layout with I/O points, https://www2.isye.gatech.edu/~mgoetsch/cali/ierc_2003_portland/Detailed%20Layout%20with%20Contour%20Distances%20IERC%202003%20Final.pdf). Klausnitzer & Lasch, "Optimal facility layout and material handling network design", Computers & OR, 2019 (I only saw the bibliographic record). The block layout, the I/O point locations and the aisles are chosen together, with distances measured *around* blocks. *Transfer:* treat part rotation and pin side as the I/O-point choice and score with routed (contour) distance rather than HPWL. **W4.**

**Process plant and ship routing**: Guirardello & Swaney, "Optimization of process plant layout with pipe routing", Computers & Chem. Eng., 2005 (MILP; I saw it only through citations). Ship cable laying uses a two-level GA over net order with A* paths (https://english.ship-research.com/en/article/doi/10.19693/j.issn.1673-3185.04499). Belov et al., "From Multi-Agent Pathfinding to Pipe Routing", 2019 (arXiv 1905.08412), maps MAPF solvers such as CBS onto 3D pipe routing. *Transfer:* CBS-style conflict resolution for multi-net grid routing inside the placement loop. **W4.**

**Urban and floorplan network design**: Peng et al., "Computational Network Design from Functional Specifications", SIGGRAPH 2016 (arXiv 1510.09203), designs street or corridor networks on a tiled domain with integer programming and hard connectivity constraints. **W2.**

**Procedural dungeons (TinyKeep)** (https://gamedev.net/forums/topic/642621-my-procedural-dungeon-generation-algorithm-explained-for-my-game-tinykeep/; details only from secondary write-ups). Random rooms are separated by steering forces, followed by a Delaunay triangulation of the rooms, an MST, about 10–15% of the triangulation edges added back, and L-shaped corridors. Ma et al., "Game Level Layout from Design Specification", Eurographics 2014, handles placement from a graph with configuration spaces. *Transfer:* separate overlapping footprints while springs along the net MSTs keep the topology. Route L-shapes right away, and when one fails, add a spring or repulsion and continue separating. **W5.**

(Quantum chips: Qplacer, ISCA 2025, is placement-only. Origami and 3D printing: I found no joint P&R algorithm.)

## 4. Physics- and biology-inspired methods

**Physarum**: Tero et al., J. Theor. Biol. 2007; "Rules for Biologically Inspired Adaptive Network Design", Science 2010. Bonifaci et al., "Physarum-Inspired Multi-Commodity Flow Dynamics" (arXiv 2009.01498; TCS 2022). Each edge conductivity D evolves as dD/dt = f(|Q|) − D, where Q comes from a Poisson/Kirchhoff solve between terminals. The multi-commodity version provably minimizes construction cost + routing cost. *Transfer:* per-net potential solves on the grid with conductivity shared across nets (capacity). Footprints have zero conductivity, and parts are electrodes that feel net force from the flux at their pads, so they move toward where flow wants to go. It thresholds to trees naturally. **W4.**

**Elastic net** (Durbin & Willshaw, Nature 326, 1987). An elastic ring is pulled toward targets while tension shortens it. *Transfer:* nets as elastic polylines repelled by footprints and other nets. The pads feel equal and opposite band tension, giving a continuous joint relaxation of parts and routes, followed by snapping to the grid with A*. **W4.**

**Force-directed edge bundling** (Holten & van Wijk, CGF/EuroVis 2009). Edges are subdivided and compatible segments attract each other. *Transfer:* attraction between compatible nets (buses), repulsion between incompatible ones to pull crossings apart, with reaction forces on the parts. **W4.**

**Space colonization** (Runions et al., SIGGRAPH 2005, leaf veins; Runions, Lane & Prusinkiewicz 2007, trees). Growing tips consume attraction points. *Transfer:* grow every net's Steiner tree **at the same time** from its pads toward its unreached pins; nets compete for free cells. **W4.**

**Cellular-automaton wavefronts** (Lee 1961, a maze router is a CA wavefront). *Transfer (synthesis):* expand all nets' wavefronts at once (multi-source BFS). The collision fronts partition the board into net territories. A net whose territory gets cut off shows which part is blocking it, so move or rotate that part. **W5.**

**Ant colony** (Dorigo et al. 1996). Per-net pheromone with evaporation. Moving a part lets evaporation forget stale trails. **W3.**

## 5. ML/LLM approaches (2021–2026)

- **DeepPR** (Cheng & Yan, NeurIPS 2021, arXiv 2111.00234): RL for macro placement with routing in the reward. **W2.**
- **Vassallo & Bajada, DATE 2024**: RL PCB placement with adaptive rewards (https://www.um.edu.mt/library/oar/handle/123456789/131782). Placement only. **W2.**
- **He & Bao, "Circuit Routing Using MCTS and DNNs", 2020** (arXiv 2006.13607): MCTS over routing order and paths beats sequential A*. *Transfer:* MCTS whose actions mix "place next part" and "route next net". **W3.**
- **Chip Placement with Diffusion Models** (Lee et al., ICML 2025, arXiv 2407.12282): places everything at once by denoising, with guided sampling. *Transfer:* the guidance could be the routed-cost gradient from §2. **W2.**
- **CoEvoP&R** (Chen et al., arXiv 2607.17398, 2026): an LLM evolves readable, differentiable placement objectives, each checked in DREAMPlace and scored by a timing proxy and an **actual router**, with an archive. It reports −16.9% routed wirelength and −36.7% congestion versus DREAMPlace. Related: EvoPlace (arXiv 2504.17801, 2025), VPR-Evolve (arXiv 2607.24998), GR-Evolve (arXiv 2604.22234). *Transfer:* use kaebench as the evaluator and evolve the move selector, cost weights and rip-up policy. **W4.**
- **PCBWorld** (arXiv 2607.05915, 2026): a KiCad routing environment with DRC feedback for RL and LLM agents on 679 boards. Useful as a reference benchmark.
- **GFlowNets** (Bengio et al., NeurIPS 2021): torchgfn ships a chip-placement environment (about 15 macros on an 8x8 grid, https://torchgfn.readthedocs.io/en/latest/autoapi/gfn/gym/chip_design/index.html), the same scale as a small PCB. *Transfer:* sample diverse placements with probability ∝ exp(−routed cost) to seed annealing. **W3.**
- **Commercial**: Quilter describes RL agents that place, route and run physics checks (https://quilter.ai/technology), with no technical paper. I found no technical paper for InstaDeep's DeepPCB. Treat both as unverified claims.

## 6. Puzzle and game analogies

- **Numberlink / Flow Free**: Yoshinaka et al., "Finding All Solutions and Instances of Numberlink and Slitherlink by ZDDs", Algorithms 2012. Secondary sources say Matt Zucker found a simple SAT encoding beat his tuned A* solver. *Transfer:* SAT path encoding (degree-2 cells, per-net colour) for exact window repair (see SP&R). **W4.**
- **Factorio**: Patterson et al., "Towards Automatic Design of Factorio Blueprints", 2023 (arXiv 2310.01505), uses constraint models for belt routing. Reid et al., "The Factory Must Grow", 2021 (arXiv 2102.04871), models belts as an IP and compares SA, GP and evolutionary RL. Factorio-SAT (https://github.com/R-O-C-K-E-T/Factorio-SAT) gives SAT-exact balancer layouts. A bachelor's thesis (seen only via Reddit, unverified) used **SA placement over CBS+A* belt routing**, which is exactly the place-route loop. The Factorio Learning Environment (Hopkins et al., NeurIPS 2025, arXiv 2503.09617) finds LLMs weak at spatial layout, which argues for LLMs writing heuristics rather than layouts. **W4.**
- **Zachtronics, Silicon Zeroes, Infinifactory, Shapez**: I found no published automatic placement + routing solvers, so I left them out.

---

## Top 10 mechanisms for joint PCB P&R, ranked

1. **Annealing where each move re-routes** (Nag–Rutenbar, Independence). Each move rips up and re-routes only the moved part's nets with numba A*. PathFinder history costs persist across moves. It is the most direct path to true joint optimization at this size.
2. **Route-informed footprint bloating** (SimPLR, IPR). Outer loop: route → inflate parts in proportion to local overflow and detours, pull parts in sparse regions together → re-place. Cheap and proven.
3. **Envelope-theorem gradients from current routes** *(synthesis)*. Pin tension along the first segment plus obstacle-boundary terms weighted by history costs drive a continuous placer between re-routes.
4. **Soft-min Bellman-Ford / perturbed A*** for a differentiable routing-density field (Mensch–Blondel, Berthet, Vlastelica). It gives congestion gradients with respect to positions without training data.
5. **Wavefront territory competition** (CA/Lee, space colonization). Simultaneous multi-net growth pinpoints blocking parts and suggests moves or rotations.
6. **Crossing/planarity penalty + pin-facing rotation** (Apollo, facility I/O points, TinyKeep MST). On 2 layers, net crossings are vias, so minimize MST crossings during placement and choose rotations by routed contour distance.
7. **Gumbel-softmax over route candidates, optimized with positions** (DGR). Candidates are pattern routes relative to the pins.
8. **Exact SAT/CP-SAT window repair** (SP&R, Numberlink, Factorio-SAT) as an LNS step: free 3–6 parts and their nets, solve placement + routing exactly in the window.
9. **Physarum or elastic-net co-relaxation**. Nets are conductive or elastic and parts feel reaction forces, giving a continuous joint relaxation before discrete routing.
10. **LLM evolutionary search over heuristics with a real-router evaluator** (CoEvoP&R, EvoPlace), using kaebench's `kicad-cli` DRC score as the fitness. Best once items 1–3 exist as a parameterized skeleton.
