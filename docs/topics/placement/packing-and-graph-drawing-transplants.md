# Packing, graph drawing, cartography and other transplants for PCB placement

Scope: packing, nesting, graph drawing, cartography and protein-design methods transplantable to PCB placement. Not here: geometry libraries -> [geometry](../solvers/geometry-libraries.md).
Keys: sparrow, jagua-rs, hazards, guided local search, irregular nesting, sequence-pair completion, HOLA, IPSep-CoLa, stress majorization, map labeling SA, metro-map MIP, octilinear, DEE, dead-end elimination, libavoid

**Results**
1. sparrow on jagua-rs is a ready open legalizer/compactor (courtyards and keep-outs as hazards).
2. Sequence-pair completion turns acyclic LLM left-of/below relations into a non-overlapping packing; HOLA/IPSep-CoLa give human-grounded layout criteria and hard separation constraints; DEE prunes dominated rotation/side states.
3. Quick wins: map-labeling SA for silkscreen refdes, metro-map MIP for octilinear buses [I].

## Methods and results

**Nesting / packing**
- SVGnest/Deepnest: orbital NFP (Burke 2006) + GA over order and rotation; MIT; deepnest-next moving core to Rust [S/P].
- **jagua-rs** (Gardeyn, Vanden Berghe, Wauters; INFORMS JoC; [arXiv 2508.08341](https://arxiv.org/abs/2508.08341) [P]): collision detection engine that "assumes full responsibility for the geometric challenge"; **hazards** = everything making a placement infeasible (items → interior hazards; container complement → exterior); dynamic **quadtree** broad phase (collides/free/undecided); **fail-fast surrogate** of pole-of-inaccessibility circles; "millions of queries per second"; continuous rotation, reflections, holes, quality zones, minimum separation; notes a robust public NFP generator "remains elusive".
- **sparrow** ([arXiv 2509.13329](https://arxiv.org/abs/2509.13329) [P]): strip packing as a sequence of fixed-length **overlap-elimination** feasibility problems ("rare oases in a vast desert of infeasibility"); smooth overlap proxy from pole-of-inaccessibility circles with decaying penetration depth; **GLS with item-pair weights** that grow for persistent/severe collisions and decay when resolved, heavy items "jump away"; exploration (large shrink steps) then compression (small decaying steps, restore incumbent); 20 min on 3 threads, one parameter set; "consistently outperforms the state of the art".
- **Sequence pair** (Murata, TCAD'96): pair of permutations encodes left-of/below for every pair; complete; decode by longest paths in constraint graphs; SA search [S].
- **Unequal-area facility layout (UAFLP)**: departments of given area minimizing flow × distance (HPWL analog); slicing-tree GA/tabu, MIP [S].

**Graph drawing**
- **HOLA** (Kieffer, Dwyer, Marriott, Wybrow; TVCG'16, InfoVis'15 Best Paper; [PDF](https://ialab.it.monash.edu/~dwyer/papers/hola2015.pdf) [P]): 17 participants hand-drew 8 graphs, 65 ranked them; best human layouts beat yFiles orthogonal (0.621 vs 0.415, p = 1.3e-9). Preference correlates: + compactness, grid-likeness (share of nodes in ≥3-alignments), symmetry, trees outside; − crossings, bends, segment-length SD, stress. Algorithm: tree/core decomposition → stress layout + orthogonalization of core → symmetric trees inserted outside → opportunistic alignment, neighbour-stress distribution; users faster and more accurate than with yFiles; ships in Adaptagrams `libdialect`.
- **IPSep-CoLa** (Dwyer, Koren, Marriott, TVCG'06): stress majorization with **hard separation constraints** x₁ + d ≤ x₂ (non-overlap, alignment, page boundary, downward edges); "constraints are not springies" ([slides](https://www.cs.ubc.ca/~tmm/courses/533-09/slides/dwyer.subset.pdf) [P]); Graphviz `constrained_majorization_ipsep.c`, WebCola [S].
- libavoid orthogonal connector routing (1-bend visibility graph, nudging); netlistsvg/d3-hwschematic ELK layered layout with fixed port order; Cassowary incremental dual simplex with constraint strengths (AutoLayout) [S].

**Cartography**
- **Point-feature label placement** (Christensen, Marks, Shieber, ToG'95): NP-hard; SA (move one label among candidates) worked best; 1997 study: SA outperforms published practical algorithms for variable-size labels ([Harvard](https://dash.harvard.edu/bitstream/1/2032678/2/AnEmpiricalStudy.pdf) [S]).
- **Metro-map MIP** (Nöllenburg & Wolff, TVCG'11): layout + labeling as one MIP, 7 design rules as hard constraints (octilinearity…) and soft costs; finds a drawing whenever one exists; k-linear extensions [S].

**Other domains**
- **Dead-end elimination** (Nature 1992): proves rotamers cannot be in the global minimum; with A* or B&B + MAP bounds (BroMAP) guarantees the optimum for pairwise energies; iMinDEE for continuous flexibility [S].
- **ASP for PCG** (Smith & Mateas 2011): design space as an answer-set program; enumerate/sample valid artifacts. **WFC / model synthesis** (Merrell; Gumin): tile-adjacency propagation; struggles on large outputs [S]. LLM ↔ ASP loops (clingo) improve spatial reasoning; DecompSR [S].
- **Control cabinets**: Pareto SA on wire length vs heat → [sides/thermal](sides-thermal-emc-reuse.md#methods-and-results); duct auto-wiring with fill-level and EMC segregation (Zuken E3.panel) [S].
- **Origami/foldable PCBs**: PCB Origami, PCBend joints free of rigid parts, Miura-ori stretchable boards [S].

## Use in kae
- **sparrow-style legalizer** [I]: fix outline; courtyards = interior hazards; outline complement, keep-outs, hole clearances, connector-overhang zones = hazards with per-type filters (height zones under heatsinks, no-back-side zones); allow overlaps; GLS on weighted overlap proxy + displacement-from-target + HPWL; then compress block bounding boxes. Keep connectivity terms or inflate courtyards by channel margins (nesting ignores nets).
- **Sequence-pair bridge** [I]: LLM pairwise relations = partial SP → complete by topological sort (tie-break by netlist proximity) → longest-path decode = non-overlapping packing (reject cyclic relation sets first; outline/keep-out/fixed-part legality via the legalizer); anneal remaining freedom with the LLM's partial order as hard precedence.
- **Block floorplanning as UAFLP**: LLM supplies flow matrix (net count × criticality) and area estimates; slicing-tree GA or MIP [I].
- **HOLA-style initial placement**: 2-core of the connectivity graph (MCU, regulators, main connectors) by constrained stress; degree-1/2 peripherals (pull-ups, LED+R, test points, ESD) placed symmetrically outside on the side of their pin; then alignment and even spacing; HOLA criteria as an aesthetic score and VLM-judge features [I].
- **IPSep-style hard signal-flow constraints**: `x(J_in) + d ≤ x(U_filter) ≤ …`, containment and non-overlap hard, wirelength/stress as goal [I].
- **Silkscreen refdes placement** by SA or MaxSAT/ILP over candidate positions with a conflict graph (pads, labels, vias, edges) — an LLM triggers it, never hand-places [I].
- **Metro-map MIP** to snap long bus runs to 0/45/90° with hard spacing, soft bends ([topological routing](../routing/topological-routing.md)) [I].
- **DEE + A*/ILP** for rotation × side × snapped-offset states with pairwise wirelength/crossing/conflict energies; explainable ("U3 at 90° is provably dominated") [I].
- **ASP/WFC** for tiled regions (keyboard matrices, LED arrays, multichannel front-ends) inside KiCad multichannel rooms; LLM → ASP facts to catch contradictions, strict-order cycles and edge-slot over-subscription before solving [I].
- Rigid-flex: panel assignment as constrained bin assignment with no rigid parts at folds [I].

## Open questions
- No PCB application of NFP/GLS nesting, HOLA, IPSep, DEE, ASP or WFC found.
- Licenses: jagua-rs MPL-2.0 and sparrow MIT (verified in [solver_toolbox.md § 6](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/solver_toolbox.md)); Adaptagrams license unverified.

## Sources
- [cross_domain_ideas.md § Q3, Q6, Q8, Q10](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/cross_domain_ideas.md); [solver_toolbox.md § 6](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/solver_toolbox.md)
