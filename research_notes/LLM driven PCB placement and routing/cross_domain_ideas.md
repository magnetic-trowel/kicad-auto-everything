# Cross-Domain Generative Layout and Spatial-Optimization Techniques Transplantable to LLM-Driven PCB Placement and Routing

Research notes, deep pass, as of 2026-10-20. Scope: methods from OTHER fields mapped onto a KiCad placer/router driven by an LLM. The fields covered are graphic/UI layout, 3D scene synthesis, floorplans, CAD code generation, VLSI ML, nesting/packing, robotics/MAPF, game search and puzzles, graph drawing and cartography, LLM-evolved algorithms, quality-diversity, microfluidics/quantum/photonics/harness/urban/package design, procedural content generation, answer-set programming, analog layout, warehouses, origami and control cabinets.

**Provenance legend.** Each finding is tagged [P] or [S].
- **[P]** means I read the primary full text: the PDF from arXiv, the conference or publisher site, or the author's site, extracted with `pdftotext` or HTML parsing.
- **[S]** means I saw only a search snippet, an abstract, or a secondary or aggregator page.

The first pass was snippet-only because arxiv, CVF and Springer were unreachable. In this deep pass the top-ranked transplants were read in full: Holodeck, LayoutVLM, both Brown imperative/PSDL papers, the open-universe layout language, SceneCraft, VeoPlace, jagua-rs, sparrow, chip-placement diffusion, HOLA, the DATE 2023 MCTS PCB router, warehouse QD layout, AlphaEvolve, FunSearch (Nature), AlphaFold2 (Nature), PlanarBench, Graph-Drawing-for-LLMs, LayoutCopilot, LLM-for-MAPF, R3L, HSM and Diffusion-CCSP. The Springer "CBS for PCB" paper still returned a JavaScript challenge page, so it remains [S]. All "Transfer to PCB" paragraphs are my own inferences and sit under "Inferences".

---

## Q1. LLM-driven layout generation in other fields (graphic/UI, 3D indoor scenes, floorplans, CAD code): which use "LLM emits relational constraints → optimizer solves geometry", and how well does it work?

### Takeaway
The field has moved through three generations:
1. **LLM emits absolute coordinates** (LayoutGPT). This gives collisions and out-of-bounds errors.
2. **LLM emits relational constraints and a solver places objects** (Holodeck, Brown's open-universe DSL, SceneCraft, I-Design). This is more reliable, but it breaks down with many objects or highly structured scenes, and the LLM misuses complex DSL commands.
3. **Hybrids that keep the LLM's numeric intent and repair it.** LayoutVLM uses numeric poses plus self-consistent differentiable relations and beat I-Design by 40.8 PSA points. Brown's imperative/PSDL programs use LLM-free coordinate-descent repair; humans preferred them 82% and 94% of the time over two declarative systems, and 95.2% over Holodeck in scenes with 40 or more objects.

For PCB the strongest evidence points to generation 3: let the LLM write *structured, relative-placement code with shared variables*, then repair numerically while staying close to that intent.

### Cited Findings
**Graphic/UI layout**
- **LayoutGPT** (NeurIPS 2023): serializes layouts as CSS, with categories as selectors and positions and sizes as declarations, normalized to 256px. It reports 20–40% gains in numerical and spatial correctness over text-to-image baselines, and parity with supervised methods on 3D indoor synthesis. [S] — [arXiv 2305.15393](https://arxiv.org/pdf/2305.15393); [NeurIPS](https://proceedings.neurips.cc/paper_files/paper/2023/hash/3a7f9e485845dac27423375c934cb4db-Abstract.html)
- **LayoutPrompter** (NeurIPS 2023): training-free in-context learning with three parts: serialization, dynamic exemplar selection, and a ranker over several samples. It matches or beats trained SOTA, especially with little data. [S] — [NeurIPS](https://proceedings.neurips.cc/paper_files/paper/2023/hash/88a129e44f25a571ae8b838057c46855-Abstract.html)
- **LayoutNUWA** (ICLR 2024): layout conditions become HTML with masked slots, an LLM fills them, and the result is rendered ("Code Instruct Tuning"). It claims more than 50% gains on some datasets. [S] — [ICLR](https://proceedings.iclr.cc/paper_files/paper/2024/hash/a6a1e4c756d700d9aedcc1896a7e6fb0-Abstract-Conference.html)

**Holodeck** (CVPR 2024; [code](https://github.com/allenai/Holodeck)) [P] — [arXiv 2312.09067](https://arxiv.org/abs/2312.09067)
- *Why relations instead of numbers:* the paper says letting the LLM output absolute bounding boxes "frequently leads to out-of-boundary errors and object collisions" when placing many diverse assets.
- *Constraint vocabulary:* ten types in five categories. Global: edge, middle. Distance: near, far. Position: in front of, side of, above, on top of. Alignment: center aligned. Rotation: face to. All relational constraints are soft; collision and room boundary are hard.
- *DFS solver:* each object is (x, y, w, d, rotation ∈ {0, 90, 180, 270}). The solver builds a grid, places the LLM-chosen **anchor object** first, then places the rest depth-first. It scores placements by the number of satisfied soft constraints, runs **for a fixed 30 s**, and returns the candidate satisfying the most constraints.
- *MILP solver:* each object is (x, y, rotate90, rotate180), with booleans encoding four rotations. Disjunctions such as "A_x = B_x OR A_y = B_y" use binary auxiliary variables, solved with Gurobi. All constraints are hard except near and far, which go into the objective. The README recommends DFS for better layouts.
- *Ablation:* humans ranked layouts by mean reciprocal rank (MRR) as follows: constraint-based 0.706, put-everything-at-the-edge 0.645, LLM absolute coordinates 0.364, random 0.369.
- *Human study:* 680 graduate students across studies. Against ProcTHOR, Holodeck was preferred overall 64.4%, for asset selection 59.8%, and for layout coherence 56.9%. The asset library has 51,464 assets.
- **Holodeck 2.0** (2025) types each constraint as (type, relation, source, target) and uses a backtracking DFS with topological ordering of dependencies, timeout and node limits. [S/P-abstract] — [arXiv 2508.05899](https://arxiv.org/abs/2508.05899)

**LayoutVLM** (CVPR 2025) [P] — [arXiv 2412.02193](https://arxiv.org/abs/2412.02193); [project](https://ai.stanford.edu/~sunfanyun/layoutvlm/)
- *Representation:* numeric initial poses plus a set of **five differentiable relations**:
  - `distance(a, b, lo, hi)`: penalized outside [lo, hi]
  - `on_top_of`
  - `align_with(a, b, angle)`
  - `point_towards(a, b, angle)`
  - `against_wall`

  These relations deliberately avoid a fixed reference frame, unlike `in_front_of` or `left_of`.
- *Self-consistent decoding:* only relations already satisfied by the VLM's own initial poses (loss ≤ ε) are kept for optimization: L_semantic = Σ 1[L(p̂) ≤ ε]·L(p). The idea is that relations agreeing with the poses capture the intent worth preserving.
- *Physics term:* Distance-IoU loss between oriented bounding boxes, optimized with **projected gradient descent** that projects back inside the room every fixed number of iterations.
- *Visual prompting:* renders are annotated with coordinate points every 2 m, coordinate frames, and front-facing arrows on each object. An LLM groups assets so they are placed one group at a time, re-rendering between groups so the VLM sees the free space.
- *Results:* 11 room types, up to 80 assets per room. LayoutVLM improves PSA (physics-weighted semantic alignment) by 40.8 over I-Design, the best baseline. The paper says Holodeck "struggles… due to its search-based approach, which becomes ineffective with the large number of assets."
- *Ablations:* spatial constraints matter most for preventing overlap; good numeric initialization matters most for semantics; the VLM beats an LLM.
- *Fine-tuning:* relations auto-extracted from about 9,000 3D-Front rooms. LoRA fine-tuning of LLaVA-NeXT-Interleave on this representation beats fine-tuning on raw numeric poses.

**Open-Universe Indoor Scene Generation** (Aguina-Kang et al., Brown, 2024) [P] — [arXiv 2403.09675](https://arxiv.org/abs/2403.09675)
- The LLM writes a Python-embedded declarative DSL with relations such as `adjacent(a, b, dir1, dir2)`, `aligned(list, dir)`, `facing(a, b)`, `on(a, b)`, `surround(objs, center)` and next-to-wall. A gradient solver minimizes the sum of constraint losses from random initial positions.
- *Custom no-overlap gradient:* overlap loss is flat when boxes cross in a "+" shape, so the gradient is defined along the centroid-to-centroid vector, with magnitude equal to the overlap region's minimum side length.
- *Repel forces:* force-directed-style repulsion stops unspecified adjacencies. The schedule is: random init → descent with repel → set "facing" orientations → descent without repel, so it converges to the true constraint solution.
- *Error taxonomy and auto-repair:*
  1. Hallucination (undefined names) and misuse (bad arguments): caught by executing the program and deleting the offending line.
  2. Contradiction: found by pattern-matching six contradictory subgraph patterns (object adjacent to itself, next to two opposing walls, a↔b adjacency in non-opposite directions, and so on) and deleting the last-declared constraint.
  3. Unsatisfiability: declared if loss is still non-zero after 10 random restarts, then the system backtracks to re-generate the relations.

**Imperative vs. Declarative / Procedural Scene Programs (PSDL)** (Gumin, Han, Yoo, Ganeshan, Jones, Aguina-Kang, Morris, Ritchie; arXiv 2504.05482 v2 Oct 2025, published as SIGGRAPH Asia 2025 paper 2510.16147; the same study, retitled) [P] — [arXiv 2504.05482](https://arxiv.org/abs/2504.05482); [arXiv 2510.16147](https://arxiv.org/abs/2510.16147)
- *Critique of declarative DSLs:* they cannot express structured patterns (alternating rows, spirals) without new relations, and each new relation needs more prompt documentation. Solver time grows at least linearly with relation count, which grows roughly quadratically with object count. LLMs persistently confuse argument meanings, for example `dir_1` vs `dir_2` in `adjacent`, "even after extensive prompting". Semantic errors only show up after solving, and LLM self-repair rarely fixes them.
- *PSDL design:* every object exposes `.min`, `.max`, `.center`, `.facing` ∈ {X_NEG, X_POS, Y_NEG, Y_POS}, and width/depth. Assignments like `chair.max.x = table.min.x - 0.1` move the object through an overloaded assignment operator. Loops and **shared variables** let one spacing variable control a whole row. `set_coordinate_frame(o)` lets the LLM build sub-layouts in a local frame. Programs are arbitrary Python.
- *Repair = LLM-free local search over program constants:*
  - Loss: out-of-bounds protrusion, plus pairwise overlap (cube root of intersection volume), plus standing and mounted support losses. Doors and windows get enlarged collision boxes to reserve opening space.
  - Neighborhood: each float constant is multiplied by 2 or 0.5 or shifted by ±δ, and each orientation is flipped by 90°.
  - Objective: pick the best neighbor under f(L) = loss(L) + d_OT(L, L₀). The second term is an optimal-transport "mass transport" distance to the original layout, weighted by object volume so large objects resist moving. Stop when improvement falls below ε.
  - On average **7.13 edits per scene**.
- *Error counts (Table 5):* Claude 3.5 Sonnet went from 17.57 errors to 2.10 after correction; GPT-4o 17.80 → 3.34; o1 17.29 → 3.24; Gemini-exp-1206 14.67 → 3.14. o1 was "not noticeably better than GPT-4o".
- *Ablation of repair methods:*

  | Repair method | Errors left | Time | Preference |
  |---|---|---|---|
  | Gradient descent | 0.5 | 2.6 s | 61.4% |
  | LLM self-repair | 5.7 | 106.7 s | 68.1% |
  | Local search on unstructured imperative code | 0.8 | 25.2 s | 71.4% |
  | PSDL local search (reference method) | 1.1 | 9.3 s | — |

  PSDL search fixes 91% of errors, against 96% for gradient descent and 93.5% for unstructured local search. It still wins on preference because moving individual objects "breaks intended relationships". Shared variables make search about 3× faster than on unstructured imperative code.
- *Human studies:* participants preferred PSDL over DeclBase (the open-universe DSL) 82.9% and over Holodeck 94.3% of the time. The gap was largest for large, structured scenes; against Holodeck with ≥ 40 objects the preference was 95.2% (auto metric).
- *Automatic judge:* a multimodal LLM is shown two layouts and asked to list **pros and cons before choosing**. This agreed with humans about 77% of the time; VQAScore and Davidsonian Scene Graph were near chance.
- *Timing:* 37.9 s per imperative scene vs 40.8 s per declarative scene.
- *Limitations:* only four cardinal orientations; repair cannot fix identity swaps or x/y swaps.

**SceneCraft** (Hu et al., ICML 2024) [P] — [arXiv 2403.01248](https://arxiv.org/abs/2403.01248)
- The scene is a **relational bipartite graph G = (assets, relation nodes, edges)**. Each relation node (proximity, alignment, parallelism, …) connects to a *subset* of assets, which is effectively a hyperedge.
- *Inner loop:* the LLM writes Blender code that turns relations into numeric constraints; GPT-V critiques renders and identifies problematic relations to fix.
- *Outer loop:* "library learning" summarizes recurring code patterns across scenes into a **spatial skill library**.
- Reports 45.1% and 40.9% CLIP-score gains over a baseline LLM agent (BlenderGPT) on generated scenes.

**Other scene-layout systems**
- **R3L** (2026): multi-hop relative relations ("A in front of B, C in front of A…") **accumulate reference-frame errors**, causing semantic and metric drift. Fixes: invariant spatial decomposition (break relation chains), an imagine-and-revise self-consistency loop, and global-to-local coordinate reparameterization; code public. It also criticizes grid DFS solvers for trading semantic fidelity for feasibility. [P-abstract] — [arXiv 2605.06758](https://arxiv.org/abs/2605.06758)
- **HSM — Hierarchical Scene Motifs** (2025): finds *support regions* at each level of a hierarchy (floor → furniture → surfaces) and fills them with reusable **motifs learned from a few examples**, applied across scales. [P-abstract] — [arXiv 2503.16848](https://arxiv.org/abs/2503.16848)
- **RoomCraft** (heuristic-DFS placement order plus collision-avoiding optimization) [S] — [arXiv 2506.22291](https://arxiv.org/pdf/2506.22291)
- **I-Design** (multi-agent LLM → scene graph → placement) [S] — [mlanthology](https://mlanthology.org/eccvw/2024/celen2024eccvw-idesign)
- **LLplace** (fine-tuned Llama-3 outputs layouts directly; add/remove dialogue) [S] — [HF 2406.03866](https://huggingface.co/papers/2406.03866)
- **DiagrammerGPT** (COLM 2024): an LLM "diagram plan" of entities, relationships and 2D boxes, refined in a **planner–auditor feedback loop** (including multimodal auditors) before rendering; code public. [S] — [arXiv 2310.12128](https://arxiv.org/abs/2310.12128); [GitHub](https://github.com/aszala/DiagrammerGPT)
- **Make It Home** (SIGGRAPH 2011, pre-LLM): ergonomic priors (accessibility, visibility, pairwise relations learned from examples) assembled into a cost function and optimized by **simulated annealing with Metropolis–Hastings moves**. [S] — [UCLA CAM report](https://ww3.math.ucla.edu/camreport/cam11-49.pdf)

**Floorplans and CAD**
- House-GAN (graph-constrained GAN) [S] — [arXiv 2003.06988](https://arxiv.org/abs/2003.06988)
- HouseDiffusion (graph-masked attention diffusion producing vector floorplans) [S] — [arXiv 2211.13287](https://arxiv.org/abs/2211.13287v1)
- HouseTune (LLM chain-of-thought draft → diffusion refine; "LLM alone lacks precise geometry") [S] — [arXiv 2411.12279](https://arxiv.org/abs/2411.12279v4)
- RLVR floorplanning (Lara et al., ACL Findings 2026; at least 94% relative reduction in "Compatibility" error) [S] — [ACL author page](https://aclanthology.org/people/luis-lara/)
- Text-to-CadQuery (top-1 exact match 58.8% → 69.3%) [S] — [HF 2505.06507](https://huggingface.co/papers/2505.06507)
- CAD-Coder (GRPO with a Chamfer-distance reward; mean CD 6.54 vs 29.29) [S] — [NeurIPS 2025](https://proceedings.neurips.cc/paper_files/paper/2025/hash/564a224e88f2490f3c1deaae877d37e3-Abstract-Conference.html)

**Direct evidence on LLM spatial-layout ability**
- **PlanarBench** (2026): models produce crossing-free ASCII drawings of planar graphs with only 2–7 vertices. Across 91 model configurations and 199 graphs, **edge count (constraints) predicts difficulty far better than vertex count** (r = −0.85 vs −0.47; partial r = −0.80). The best model scored 159.5/199, most models under 30B parameters scored below 25, and "substantial failures remain among frontier systems". [P] — [arXiv 2606.02010](https://arxiv.org/abs/2606.02010)
- **Graph Drawing for LLMs** (Didimo et al., 2025): when GPT-4o and Claude 3.7 Sonnet answer graph questions from *images*, the layout paradigm (straight-line force-directed vs orthogonal) and human-readability metrics of the drawing significantly change accuracy. [P] — [arXiv 2505.03678](https://arxiv.org/abs/2505.03678)
- An earlier study found ChatGPT could apply graph layout algorithms "not perfect, but promising". [S] — [EuroVis short paper](https://diglib.eg.org/handle/10.2312/evs20231047)

### Inferences
- **Overall verdict.** "LLM emits constraints → solver" beat raw coordinates in 2023–24 (Holodeck MRR 0.706 vs 0.364). By 2025 the Brown group showed that a well-designed *imperative relative-placement language with shared variables*, plus cheap LLM-free repair, beats declarative pipelines by a wide margin, especially for large, structured layouts. A PCB is a large, highly structured layout: rows of passives, arrays, decoupling rings, bus fan-outs. PlanarBench and R3L add that LLMs should not do global crossing-free geometry or long chains of relative references themselves.
- **Transfer to PCB — "PCB-PSDL" imperative placement language (top transplant).**
  - *Object model.* Each footprint exposes `.min/.max/.center` (courtyard box), `.facing` ∈ {0°, 90°, 180°, 270°}, `.side` ∈ {F, B} and pin handles (`U1.pin["VDD"]`, `U1.pin(12).pos`). PCB parts are overwhelmingly on four orientations, so PSDL's main limitation (four cardinals) suits PCBs.
  - *Operators.* `set_frame(U1)` places decoupling caps in the IC's local frame. `row(R1..R8, pitch=p)` and `ring(caps, around=U1, gap=g)` use **shared variables** such as `p` and `g`, so repair moves whole groups coherently.
  - *Repair loop.* Execute the program, then run PSDL-style coordinate descent over numeric constants (×2, ×0.5, ±δ, flip 90°). The loss is courtyard overlap + board-outline protrusion + keepout intrusion + hole and connector clearance, plus PCB-specific terms (decap-to-pin distance, crystal loop length). The tie-break penalty d_OT is weighted by footprint area, so big ICs and connectors stay put while passives move, as the paper's volume weighting does for furniture.
  - *Hard failures.* Fall back to LLM regeneration only for identity or semantic errors.
- **Transfer to PCB — PSDL's automatic judge.** Render two candidate boards (and, optionally, their ratsnest) and ask a VLM to **list pros and cons, then choose**. This is cheap, about 77% human-aligned in scenes, and gives a ranking signal for best-of-N and for evolutionary loops (Q7).
- **Transfer to PCB — LayoutVLM's self-consistency trick.** Ask the LLM for *both* rough (x, y, θ) and relations, then keep only the relations already satisfied by its own rough poses as preserved constraints. This automatically discards hallucinated or contradictory relations. Combine with a DIoU-style courtyard overlap loss and projected gradient descent that clamps into the board outline. Place in groups (power block, MCU block, connectors) with a re-render between groups so the VLM sees the remaining free area.
- **Transfer to PCB — use frame-free and pin-anchored relations (LayoutVLM, R3L).** Avoid relations like "C5 left of R3" chained through other parts. Use frame-free relations (`distance`, `align_with`, `point_towards`) or anchor every relation to a single parent IC's pins or to the board frame. This avoids the reference-frame drift R3L measured.
- **Transfer to PCB — open-universe auto-repair rules.** Implement the error taxonomy directly:
  - Run the LLM's constraint program and delete lines that raise exceptions (hallucinated refdes or misused API calls).
  - Detect PCB contradiction patterns, for example `edge(J1, W)` and `edge(J1, E)`; `near(C1, U1, 1mm)` for 12 caps whose combined courtyards cannot fit within 1 mm; a part mounted on both sides.
  - After k non-zero-loss restarts, declare the set unsatisfiable and ask the LLM to relax it.
  - Use the custom centroid-direction no-overlap gradient and the repel-then-no-repel schedule in any gradient placer, because courtyard "+"-shaped overlaps are common.
- **Transfer to PCB — Holodeck's anchor-first DFS as a baseline.** For small boards (< 50 parts), a 30-second DFS over a courtyard-aligned grid with four rotations, anchor-first (connectors and mounting holes, then the MCU), scoring soft-constraint satisfaction, is a simple, explainable baseline. LayoutVLM's finding that DFS collapses with many assets suggests switching to gradient or PSDL repair above roughly 50–80 parts.
- **Transfer to PCB — SceneCraft relation hypergraph and skill library.** Represent design intent as relation nodes linked to footprint *subsets*: `Align-1 → {R1..R8}`, `DecapRing-U1 → {C1..C6}`, `DiffPairSymmetry → {R10, R11, C20, C21}`. Accumulate verified macros (QFN decap ring, buck hot-loop, USB-C + ESD cluster, crystal + load caps) into a skill library that the LLM calls instead of re-deriving.
- **Transfer to PCB — HSM support regions.** The hierarchy maps cleanly: board → functional-block regions (KiCad rule areas/rooms) → per-IC neighbourhoods → pin-adjacent slots for decaps. Learn small motifs ("2 caps + ferrite on VDDA") from a few example boards and apply them at each level.
- **Transfer to PCB — DiagrammerGPT planner–auditor loop.** First generate a *board plan* (blocks, relations, rough boxes), audit it textually and visually, then hand it to the placer. This separates "what goes where roughly" from geometric legalization.
- **Transfer to PCB — VLM input style matters (Graph Drawing for LLMs).** When showing a VLM the board or ratsnest, readable renders (orthogonal ratsnest previews, labeled refdes, consistent colors per net class) should measurably improve its judgments. Treat the render style as a tunable hyperparameter.

### Gaps
- No published system applies a Holodeck/PSDL-style language to PCB placement (none found).
- How PSDL-style repair behaves under PCB-specific hard constraints (pad-to-pad clearance, via-in-pad rules) is untested.
- The Holodeck 2.0 solver changes relative to v1 were only partially extracted.

---

## Q2. Diffusion / flow-matching / transformer models for layout, and whether a netlist-conditioned layout diffusion model is plausible for PCBs

### Takeaway
Plausibility is high, and the chip literature supplies a cheap recipe. Lee et al. (ICML 2025) built synthetic training data by **inverting the problem**: generate a random legal placement first, then sample a netlist that makes that placement near-optimal. They produced 100k "circuits" of about 200 objects per day on 32 CPUs, trained a small GNN+attention denoiser (233k–6.29M parameters), and steered sampling with legality and HPWL potentials using Lagrangian dual ascent. Its scale (~200 objects) is almost exactly PCB scale. Compositional energy-based diffusion (Diffusion-CCSP) and AlphaFold-style recycling suggest how to add PCB-specific constraint types and iterative refinement.

### Cited Findings
**Chip Placement with Diffusion Models** (Lee, Nguyen, Elzeiny, Deng, Abbeel, Wawrzynek; ICML 2025) [P] — [arXiv 2407.12282](https://arxiv.org/abs/2407.12282); [PMLR](https://proceedings.mlr.press/v267/lee25y.html)
- *Synthetic data:*
  1. Sample object sizes uniformly and place them randomly but legally, retrying on overlap.
  2. Sample pins per object from a power law (Rent's rule).
  3. Sample an edge between pins on different objects with probability p ∝ exp(−l/s), where l is L1 distance and s a scale parameter, so the placement is near-optimal for the netlist.

  Result: 100k circuits of about 200 objects per day on 32 CPUs, with no commercial tools. Dataset design choices (notably the scale s) strongly affect zero-shot transfer to real circuits.
- *Architecture:* interleaved message-passing GNN layers and attention layers. The attention fixes GNN oversmoothing and links objects far apart in the netlist but close on the canvas. Inputs include 2D sinusoidal position encodings, which improve precise placement of small objects.
- *Guidance:* "backwards universal guidance" on the predicted x̂₀ with potential φ = w_legality·φ_legality + w_hpwl·φ_hpwl.
  - φ_legality = Σ min(0, d_ij)², where d_ij is the signed distance between rectangles.
  - φ_hpwl is computed as a parameter-free GNN message-passing layer in PyG.
  - The constraint is enforced by **interleaved gradient steps on x and dual ascent on w_legality** (a Lagrangian).
- *Results:* guidance raised legality from about 0.88 to 0.997 and cut HPWL 7.1% on clustered IBM benchmarks; HPWL averaged 20% below DREAMPlace on clustered circuits. These figures are from the first-pass snippet and were not re-verified in this pass.
- DiffPlace (2025) [S] — [arXiv 2510.15897](https://arxiv.org/html/2510.15897v1); MacroDiff+ (IJCAI 2026) [S] — [IJCAI PDF](https://www.ijcai.org/proceedings/2026/0735.pdf)

**Graphic-layout generative models**
- **LayoutDM** (CVPR 2023): discrete diffusion with constraints injected at inference by masking or logit adjustment. [S] — [CVF](https://openaccess.thecvf.com/content/CVPR2023/html/Inoue_LayoutDM_Discrete_Diffusion_Model_for_Controllable_Layout_Generation_CVPR_2023_paper.html)
- **LayoutFlow** (ECCV 2024): flow matching, comparable to SOTA but significantly faster. [S] — [ECCV](https://ecva.net/papers/eccv_2024/papers_ECCV/html/5246_ECCV_2024_paper.php)

**Compositional energy-based generation (robotics)**
- **Diffusion-CCSP** (Yang, Mao et al., CoRL 2023): a continuous constraint satisfaction problem is a **factor graph**. Each constraint *type* (collision-free, qualitative relation, stability…) gets its own diffusion model, read as an implicit energy. Global satisfaction is achieved by **summing energies** during sampling. It generalizes to *novel combinations* and *more* constraints than seen in training. [P] — [arXiv 2309.00966](https://arxiv.org/abs/2309.00966)
- **StructDiffusion** (RSS 2023): a language-conditioned object-centric diffusion model plus a **collision discriminator** builds physically valid arrangements of unseen objects, with about 16% higher success than a multimodal-transformer baseline. [S] — [arXiv 2211.04604](https://arxiv.org/abs/2211.04604); [RSS](https://roboticsproceedings.org/rss19/p031.html)

**Protein structure: iterative refinement and conditional generation**
- **AlphaFold2 recycling** (Jumper et al., Nature 2021): "iterative refinement using the whole network (which we term 'recycling')" feeds outputs recursively into the same modules and "contributes markedly to accuracy with minor extra training time". With 4 recycling iterations × 48 Evoformer blocks, the model produces a 192-step trajectory of intermediate structures. [P] — [Nature](https://www.nature.com/articles/s41586-021-03819-2)
- A Nature News & Views piece notes the network performs learned geometric refinements rather than imposing physical rules. [S] — [Nature N&V PDF](https://media.nature.com/original/magazine-assets/d41586-021-02265-4/d41586-021-02265-4.pdf)
- **RFdiffusion**: fine-tunes the RoseTTAFold structure predictor into a denoiser and does motif scaffolding, i.e. conditional inpainting around fixed motifs. [S] — [PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC10468394)
- Motif scaffolding conditioning is unified via Doob's h-transform. [S] — [arXiv 2312.09236](https://arxiv.org/abs/2312.09236v3)

### Inferences
- **Transfer to PCB — synthetic-data diffusion placer.** Port Lee et al.'s generator to PCBs:
  1. Sample real KiCad footprints (courtyard polygons, pad positions) instead of uniform rectangles.
  2. Place them legally at random.
  3. Sample nets with p ∝ exp(−l/s) *between pads*, plus PCB-structured nets: a power net touching many parts, decap pairs at very short distance, connector-to-IC buses.

  At about 200 parts per board the compute budget matches the paper's directly. Condition the GNN+attention denoiser on footprint geometry, side and four-way rotation (discrete, LayoutDM-style). Use the PCB DSL from Q1 as guidance potentials (courtyard overlap, outline, keepouts, decap distance, HPWL) with dual ascent on the legality weight.
- **Transfer to PCB — compositional constraint energies (Diffusion-CCSP).** Train small diffusion or energy models per PCB constraint type: decap-near-pin, connector-on-edge, thermal spacing, diff-pair symmetry, keepout. Compose them at sampling time according to the LLM-written constraint graph, so new boards combine constraint types without retraining. This is a learned analog of the LLM → DSL → solver pipeline.
- **Transfer to PCB — collision discriminator (StructDiffusion).** Pair a generative placer with a learned or exact courtyard-collision checker (jagua-rs, Q3) as a rejection or reranking stage.
- **Transfer to PCB — AlphaFold-style recycling.** Iterate the placement model: feed the predicted placement, together with derived features (congestion map, ratsnest crossings, DRC hotspots), back in as input for k "recycling" passes. A placement transformer becomes an iterative refiner, and the 192-step trajectory idea gives inspectable intermediate states the LLM can comment on.
- **Transfer to PCB — motif-scaffolding inpainting.** Fix mechanically constrained parts (connectors, mounting holes, displays, buttons dictated by the enclosure) and inpaint the rest. Sample many inpaintings for diversity (Q9).
- **Risk.** Synthetic netlists lack PCB semantics (EMI, thermal, current loops). These have to come from guidance potentials and LLM-labeled classes, not the prior.

### Gaps
- No PCB-specific diffusion placer or public PCB placement dataset found. An open PCB environment, PCBWorld (2026), reports an RL policy trained on synthetic boards transferring zero-shot to real ones, which supports the synthetic-data route. [S] — [arXiv 2607.05915](https://arxiv.org/abs/2607.05915)
- How the Lee et al. synthetic recipe transfers to irregular courtyards and multi-pin footprints is untested.

---

## Q3. 2D irregular packing / nesting (no-fit polygon, Deepnest/SVGnest, bin packing): relevance to dense component packing with courtyards

### Takeaway
The 2024–2026 KU Leuven work changed the state of open-source nesting. **jagua-rs** cleanly separates geometry from optimization (collision detection as a service with a "hazard" abstraction, quadtree broad phase and fail-fast surrogates, millions of queries per second). **sparrow** shows the winning strategy is to **turn optimization into a sequence of feasibility problems**: fix the container, *allow temporary overlaps*, and eliminate them with guided local search using adaptive pair weights. It outperforms the state of the art, "in some cases by an unexpectedly wide margin". This is directly reusable as a PCB legalizer/compactor with courtyards and keepouts as hazards.

### Cited Findings
- **SVGnest/Deepnest**: orbital NFP (Burke et al. 2006) plus a genetic algorithm over order and rotation; open source. [S] — [GitHub SVGnest](https://github.com/Jack000/SVGnest); [Deepnest docs](https://docsearch.algolia.com/mcp/docs/repo/jack000/deepnest)
- **jagua-rs** (Gardeyn, Vanden Berghe, Wauters, KU Leuven; INFORMS Journal on Computing) [P] — [arXiv 2508.08341](https://arxiv.org/abs/2508.08341); [docs.rs](https://docs.rs/jagua-rs)
  - Claim: a general collision detection engine that "assumes full responsibility for the geometric challenge", so optimizers can ignore geometry.
  - Notes that a robust public NFP generator "remains elusive"; even the most popular NFP generator on GitHub is acknowledged as not feature-complete.
  - **Hazards**: everything that can make a placement infeasible. Items induce *interior* hazards and containers induce *exterior* hazards (the complement of the container). A placement is feasible if it collides with no hazard.
  - **Quadtree** broad phase over hazards, dynamically updated as items are placed or removed, answering "collides / free / undecided" per edge query.
  - **Fail-fast surrogate**: a few inscribed circles at the "pole of inaccessibility" catch obvious collisions cheaply before exact edge tests.
  - Resolves "millions of queries per second".
- **sparrow** ("An open-source heuristic to reboot 2D nesting research", Gardeyn et al., v4 Oct 2026) [P] — [arXiv 2509.13329](https://arxiv.org/abs/2509.13329)
  - Strip packing becomes a sequence of feasibility problems at fixed strip length, an "Overlap Elimination Problem". Rationale: good solutions are "rare oases in a vast desert of infeasibility", so the search must cross infeasible space.
  - Overlap is quantified with an **overlap proxy built from pole-of-inaccessibility circles**, using a *decaying* penetration depth so the proxy is smooth and continuous.
  - **Guided local search** with dynamic item-pair weights: weights of persistently colliding pairs grow (fastest for the most severe collisions) and decay back to 1 once resolved. Items in heavily weighted regions then "jump away" to new areas.
  - Two phases: *exploration* (large shrink steps, broad search) and *compression* (small, decaying shrink ratios that restore to the incumbent).
  - Runs were 20 minutes on 3 threads with one parameter set for all benchmarks, plus ten new real-world instances. "Consistently outperforms the state of the art".
- A 2026 geometry-aware RL nesting paper uses scriptable Deepnest as its open-source GA baseline. [S] — [arXiv 2606.10611](https://arxiv.org/pdf/2606.10611)
- **Sequence pair** (Murata et al., IEEE TCAD 1996): a pair of permutations (Γ+, Γ−) encodes, for every module pair, whether one is left-of or below the other. The representation is complete: every non-overlapping packing has a sequence pair and every sequence pair decodes to one, via longest paths in horizontal and vertical constraint graphs. Searched with simulated annealing. [S] — [UT Austin course copy](https://users.ece.utexas.edu/~dpan/EE382V_PDA/papers/sp.pdf)
- **Unequal-area facility layout problem (UAFLP)**: place departments of given areas in a plan to minimize material-handling cost (flow × distance), the HPWL analog; slicing-tree and GA/tabu methods are common. [S] — [UAFLP review](https://rcs.cic.ipn.mx/2021_150_3/The%20Unequal-Area%20Facility%20Layout%20Problem_%20A%20Review.pdf)

### Inferences
- **Transfer to PCB — a sparrow-style legalizer (high value, low-to-medium effort).** After the LLM or global placer produces a rough placement:
  1. Fix the board outline. Courtyards become interior hazards; the board-outline complement, keepouts, mounting-hole clearances and the connector-overhang zone become exterior or interior hazards.
  2. Allow overlaps and run guided local search: move items to minimize weighted overlap proxy + displacement from target + HPWL, with GLS pair weights.
  3. Then run a compression phase that shrinks the "board area budget" or the bounding box of each block.

  This handles irregular courtyards (L-shaped connectors, castellated modules) and naturally preserves LLM intent through the displacement term.
- **Transfer to PCB — jagua-rs hazards fit PCB rules.** PCB keepouts are typed: courtyard-vs-courtyard, component-vs-board-edge clearance, height-restricted zones under heatsinks, no-components-on-back zones. Hazards with per-type filters (an item ignores hazards that do not apply to it) express these directly. The fail-fast surrogate fits dense passive fields well, since most candidate moves collide obviously.
- **Transfer to PCB — sequence pair as the target for LLM relations.** Every pairwise left-of/below relation the LLM emits is a partial sequence pair. Completing it (a topological sort with tie-breaking by netlist proximity) yields a *guaranteed* non-overlapping packing via longest-path decoding. Annealing in sequence-pair space can then optimize HPWL while keeping the LLM's partial order fixed as hard precedence. This gives a crisp, complete bridge from "LLM relations" to "legal geometry".
- **Transfer to PCB — the facility-layout view of block floorplanning.** At block level (power, MCU, RF, analog front-end, connectors), PCB floorplanning *is* an unequal-area facility layout problem with "flow" = net count × criticality between blocks. Slicing-tree GAs or MIP formulations apply directly, and the LLM can supply the flow matrix and area estimates.
- **Caveat.** Nesting ignores connectivity, so any packing step must keep HPWL or routability terms or inflate courtyards by routing-channel margins.

### Gaps
- Licenses of jagua-rs and sparrow were not checked in this pass. The repository is public; the license should be verified before reuse.
- No PCB application of NFP or GLS nesting found.

---

## Q4. Robotics motion planning applied to routing: RRT/PRM, visibility graphs, configuration space, MAPF. Are there papers applying MAPF to PCB/VLSI routing?

### Takeaway
Yes. CBS has been applied to PCB routing on Delaunay meshes (2025). Factorio hobby and academic projects use CBS-style MAPF for belt routing. MAPF has moved to very large scale: PIBT handles 1,000 agents in about 5 s and LaCAM* solved 99% of benchmark instances with up to 1,000 agents in 10 s. Lifelong MAPF in warehouses even **co-optimizes the layout for routability** (Q9). A crucial negative result: LLMs asked to solve MAPF *directly* fail even on small maze maps. The LLM should therefore steer MAPF or negotiated-congestion solvers (priorities, conflict choices, homotopy hints), not replace them.

### Cited Findings
- **CBS** (Sharon et al., AAAI 2012): two-level conflict-tree search; optimal; fewer expansions than A*. [S] — [AAAI](https://ojs.aaai.org/index.php/AAAI/article/view/8140)
- **MAPF for Large Agents / MC-CBS** (Li et al., AAAI 2019): geometric (non-point) agents; adds multiple constraints per branch; up to three orders of magnitude faster than CBS. [S] — [AAAI](https://ojs.aaai.org/index.php/AAAI/article/view/4756)
- **PCB routing on unstructured meshes with CBS** ("UGPCB-CBS", Journal of Supercomputing 2025): Delaunay triangulation plus artificial-potential-field path generation, then CBS. The full text was blocked by a JavaScript challenge. [S] — [Springer](https://link.springer.com/article/10.1007/s11227-025-07569-0)
- **PIBT** (Okumura et al., Artificial Intelligence 2022): about 5 s for 1,000 agents on a warehouse grid, average sub-optimality below 1.5; designed for lifelong replanning; incomplete for one-shot MAPF. [S] — [arXiv 1901.11282](https://arxiv.org/abs/1901.11282)
- **LaCAM*** (Okumura 2023): anytime and eventually optimal; solved 99% of instances with up to 1,000 agents within 10 s. [S] — [ar5iv 2305.03632](https://ar5iv.labs.arxiv.org/html/2305.03632)
- Follow-ups add local guidance and lifelong variants, noting fast solvers push agents into central bottlenecks. [S] — [arXiv 2510.19072](https://arxiv.org/pdf/2510.19072v2); [alphaXiv 2605.16855](https://www.alphaxiv.org/abs/2605.16855)
- **LLMs solving MAPF directly** (Chen, Koenig, Dilkina, 2024): an LLM plans step by step with a collision checker giving feedback. It succeeds on an empty 8×8 room but "completely fail[s] on the MAZE-32-32-2 map even with only 2 agents"; success drops as agents increase. The authors attribute this to weak constraint and duplicate-detection reasoning, context-length limits (restarts make it forget state), and poor understanding of obstacle layouts, even with image prompts. [P] — [arXiv 2401.03630](https://arxiv.org/abs/2401.03630)
- **PathFinder** negotiated congestion (McMurchie & Ebeling 1995) underpins production FPGA routers. [S] — [ACM DOI](https://www.doi.org/10.1145/201310.201328); [UW news](https://news.cs.washington.edu/2012/03/01/cses-carl-ebeling-wins-top-25-in-20-from-fpga)
- **RRT-PCB** (LG AI Research): grid route, then continuous RRT refinement reusing grid paths. [S] — [LG AI Research](https://www.lgresearch.ai/blog/view?seq=510)
- **Topological / homotopy routing**: JITX topo-routes are defined as homotopy classes, with a "rubber band equivalent" when geometry fails; TopoR does any-angle routing. [S] — [JITX docs](https://docs.jitx.com/en/4.0/essentials/physical_design/autorouter.html); [TopoR listing](https://www.criticalcomms.com.au/content/unknown/product/topological-pcb-autorouter-726535972)
- **Factorio as a routing testbed**:
  - A Python framework uses SMT solvers (Z3/CVC5/Yices) with A* and MAPF for belt and pipe routing. [S] — [ecosyste.ms listing](https://science.ecosyste.ms/projects/38421)
  - A student project combined CBS over A* for belts with simulated annealing for assembler placement. [S] — [arXiv 2310.01505 (related ModRef paper)](https://arxiv.org/abs/2310.01505)
  - A 2021 paper defines the "logistic belt optimization problem", comparing parallel simulated annealing and evolutionary RL. [S] — [arXiv 2102.04871](https://arxiv.org/abs/2102.04871)
- **XRoute** is an RL environment for net selection and routing [S] — [ar5iv 2305.13823](https://ar5iv.labs.arxiv.org/html/2305.13823); Ju et al. (2021) proposed multi-agent-RL detailed routing for conflicting nets, cited there [S].

### Inferences
- **Transfer to PCB — the LLM as MAPF "meta-controller", not path planner.** Given the LLM-MAPF failure, use the LLM to:
  1. assign **net priorities and ordering** for prioritized planning or PIBT-style priority inheritance (power and high-speed first, as designers do);
  2. pick the conflict to branch on and the net to yield at stalled CBS nodes;
  3. emit **homotopy hints** ("USB pair passes north of U4");
  4. set per-net-class cost multipliers in PathFinder.

  The path computation stays in A*, PathFinder, CBS or LaCAM.
- **Transfer to PCB — PIBT/LaCAM for "many short connections".** PCB fan-out regions (hundreds of two-pin escapes) behave like dense MAPF with spatially extended agents. LaCAM's speed and anytime-optimal behaviour suggests a fast first feasible routing that CBS or rip-up-and-reroute then improves. Note the bottleneck caveat from the lifelong-MAPF work: add guidance (spread corridors) to avoid central congestion.
- **Transfer to PCB — homotopy-first routing remains the most LLM-compatible routing interface.** LLMs handle topology ("which side of C7") far better than geometry (PlanarBench, Q1). Verify homotopy specs topologically before geometric realization.
- **Transfer to PCB — Factorio projects as a design pattern.** "SAT/SMT for local exact layout + MAPF for routing + annealing for placement" is the same stack a PCB tool needs, and hobby projects show it is buildable.

### Gaps
- UGPCB-CBS numbers remain unread (JavaScript challenge).
- No VLSI detailed-routing paper with an explicit MAPF formulation found beyond the 2021 MARL work cited in XRoute.

---

## Q5. Game AI and search: AlphaZero/MuZero-style MCTS for placement/routing, puzzle solvers (Numberlink/Flow Free via SAT), Zachtronics-style human strategies

### Takeaway
MCTS has a concrete, published PCB router. He, Li, Luo and Bao (DATE 2023) partition the free space into polygons by extending pad edges, run **MCTS over sequences of polygons** (global routing), ground them with A*, and **re-partition after every routed net** so global routability equals detailed routability. It routed all 10 real two-layer open-source boards, while FreeRouting and DeepPCB each failed on two. The LLM-as-MCTS-prior literature (PUCT with an LLM action prior) provides the hook for LLM guidance. Numberlink is studied inside the Japanese EDA community as "island-in-cavity" routing, with topological and ZDD solvers. Zachtronics games have no formal strategy study, but their multi-metric post-solve histograms are a UX transplant.

### Cited Findings
- **Two-stage PCB routing using polygon-based dynamic partitioning and MCTS** (He, Li, Luo, Bao; DATE 2023) [P] — [DATE PDF](https://past.date-conference.com/proceedings-archive/2023/DATA/603.pdf)
  - *Partitioning:* each pad or obstacle is a polygon; extending all its edges to infinity splits each layer's routable region into routable polygons.
  - *Global routing:* MCTS builds a global path as a sequence of neighbouring polygons (shared border on a layer, or vertical overlap across layers). A **DFS-with-backtracking rollout** reveals after the first MCTS iteration whether any global path exists.
  - *Detailed routing:* A* with g = w₁·wirelength + w₂·C_res, where C_res = max over pads p of 1/d(x, p). This term pushes traces away from pads so early nets do not block later ones.
  - *Dynamic re-partitioning:* every polygon a routed path crosses is split in two by that path, guaranteeing that any remaining global solution has a detailed realization.
  - *Rip-up and reroute:* hierarchical; DFS with backtracking at the top level, MCTS for each global path.
  - *Net order:* random, with multi-pin nets built incrementally.
  - *Results:* on 10 real open-source two-layer boards (mixed SMD and through-hole) it routed all 10, while FreeRouting and DeepPCB each failed on 2. Wirelength was better; via count was worse.
- **Circuit Routing Using MCTS and DNNs** (He & Bao 2020): MCTS with a DFS plus neural-network rollout policy on random single-layer grids. It solves cases sequential A* and Lee's algorithm cannot, and is "not prone to net ordering", in contrast to sequential maze routers that are "very sensitive to the net orders". [P] — [arXiv 2006.13607](https://arxiv.org/abs/2006.13607)
- **EfficientPlace** (ICML 2024): global tree search plus local RL policy for macro placement. [S] — [mlanthology](https://mlanthology.org/icml/2024/geng2024icml-reinforcement)
- **Kaphle (MIT thesis 2022)**: MCTS self-generates PCB synthesis datasets for offline RL. [S] — [DSpace@MIT](https://dspace.mit.edu/handle/1721.1/145108)
- **Patents** ("Electrical circuit design"): a neural network guides sequential Monte Carlo to choose connection order, scored by length, vias, congestion and turns. [S] — [USPTO 12019968](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/12019968)
- **LLM as MCTS prior**:
  - LLM-MCTS (NeurIPS 2023) uses the LLM as world model and policy heuristic. [S] — [arXiv 2305.14078](https://export.arxiv.org/abs/2305.14078)
  - LLM-First Search (2025): the LLM gives value estimates and an action prior used in PUCT. [S] — [arXiv 2506.05213](https://arxiv.org/abs/2506.05213)
  - Scattered Forest Search (2024): PUCT with a transformer prior for code search. [S] — [arXiv 2411.05010](https://arxiv.org/abs/2411.05010)
- **Numberlink in EDA**:
  - Tanaka and Takahashi (DA Symposium 2014) treat Numberlink as island-in-cavity routing related to planar IC routing, using CHORD-LAST routing order and area division. [S] — [Titech T2R2](https://t2r2.star.titech.ac.jp/rrws/file/CTT100676101/ATD100000413/)
  - A faster topological-routing solver followed (IEICE VLD 2015). [S] — [IEICE](https://www.ieice.org/ken/paper/20150302JBY8/eng/)
  - ZDD enumeration of all Numberlink and Slitherlink solutions (Algorithms 2012). [S] — [Tohoku](https://www.iss.is.tohoku.ac.jp/publications/2012-01-algorithms/)
  - SAT encodings: Permanganate and a Leiden thesis with cycle prevention. [S] — [docs.rs permanganate](https://docs.rs/permanganate); [LIACS thesis](https://theses.liacs.nl/pdf/2025-2026-LelipalyJJoshua.pdf)
  - Zig-zag Numberlink is NP-complete. [S] — [arXiv 1410.5845](https://arxiv.org/abs/1410.5845)
- **Factorio-SAT**: tiles are encoded as booleans (direction, underground, splitter side, colour), with no-crossing and colour-consistency clauses; the solver returns a layout or proves none exists; it lays out a *hand-chosen topology*. A SAT verifier checks 64×64 balancers in under 1 s. [S] — [GitHub Factorio-SAT](https://github.com/R-O-C-K-E-T/Factorio-SAT); [verifactory](https://awesome.ecosyste.ms/projects/github.com%2Falegnani%2Fverifactory)
- **Zachtronics**: solving only requires correct output; optimization happens afterwards against post-solve **histograms of other players' cost, cycles and area** ("tall" fast-parallel vs "deep" long-program solutions; aesthetics as an unscored third goal). No formal academic study found. [S] — [Wikipedia](https://en.wikipedia.org/wiki/Zachtronics); [PC Gamer](https://www.pcgamer.com/au/perfectly-solving-opus-magnums-puzzles-is-impossible-but-thats-ok); [blog](https://biggieblog.com/playing-opus-magnum-by-different-rules/)

### Inferences
- **Transfer to PCB — adopt the DATE 2023 polygon-zone global router plus an LLM prior.** It is PCB-native, handles mixed SMD and through-hole, and was evaluated on real KiCad boards. Add an LLM in two places:
  1. as the **PUCT prior** over which neighbouring polygon to extend into, conditioned on net class and the LLM's homotopy hint;
  2. as the chooser of **net order** and of which nets to rip up during hierarchical rip-up and reroute.

  The dynamic re-partitioning invariant (global feasible ⇒ detailed feasible) is worth copying into any router regardless of MCTS.
- **Transfer to PCB — MCTS over placement decisions.** Coarse placement choices (block-to-region, top or bottom side, major IC orientation) form a shallow tree. Rollouts are a fast analytical placer plus a routability preview, and the LLM supplies the prior P(a|s), AlphaZero-style.
- **Transfer to PCB — SAT/ZDD for local windows.** BGA escape and connector fan-out windows can be solved exactly as Numberlink with vias as "bridges" (SAT, CP-SAT, or ZDD enumeration of *all* solutions for the LLM to choose between). Like Factorio-SAT, the LLM or human chooses the topology and SAT realizes or refutes it.
- **Transfer to PCB — Zachtronics UX.** After each auto-placement or route, show **histograms** of this design's metrics (area, vias, total length, worst decap distance, crossings) against a library of prior boards or of the QD archive (Q9). This turns optimization into a game the user (or the LLM) can push along chosen axes, matching the Pareto and portfolio framing.

### Gaps
- No AlphaZero/MuZero-trained PCB placer found.
- The DATE paper is a two-page short paper with limited quantitative detail (no per-board table in the text).
- No academic study of Zachtronics player strategies.

---

## Q6. Graph drawing and VLSI-inspired layout: orthogonal drawing, Sugiyama, constrained force-directed / stress majorization (WebCola, IPSep-CoLa), relevance to schematic-flow-aware placement

### Takeaway
Graph drawing offers both *algorithms* and *human-grounded objectives*. HOLA turned a user study into measurable criteria: positive correlations with compactness, grid-likeness and symmetry; negative with crossings, bends, segment-length variance and stress. It then built an algorithm (tree/core decomposition → stress layout → orthogonalization → symmetric trees inserted outside → opportunistic alignment) that users preferred and performed better with. IPSep-CoLa provides *hard* separation and alignment constraints inside stress majorization, unlike soft "springies". Cartography adds two directly useful pieces: simulated-annealing **map labeling** (for silkscreen reference designators) and **MIP octilinear metro-map layout** (for 45° bus aesthetics).

### Cited Findings
- **HOLA** (Kieffer, Dwyer, Marriott, Wybrow; IEEE TVCG 2016; InfoVis 2015 Best Paper) [P] — [paper PDF](https://ialab.it.monash.edu/~dwyer/papers/hola2015.pdf)
  - *Formative study:* 17 participants hand-laid-out 8 graphs; 65 others ranked the results in a tournament.
  - *Findings:* the best human layouts beat yFiles orthogonal layout (normalized rank score 0.621 vs 0.415, Wilcoxon p = 1.3e-9). Humans keep crossings and bends when doing so reveals symmetry, separates clusters, shortens segments or improves compactness; they also add "aesthetic bend points".
  - *Correlates of preference:*
    - positive: compactness (R3), grid-like node placement (R4: share of nodes in an alignment of three or more), symmetry (R5);
    - negative: crossings (R6), bends (R7), standard deviation of segment length (R8), stress (R9);
    - also: trees placed on the outside (R1).
  - *Algorithm:*
    1. Decompose into trees and core.
    2. Stress-minimizing layout of the core → greedy orthogonalization → orthogonal edge routing.
    3. Symmetric tree layouts → planarize the core → insert trees → stress layout.
    4. Opportunistic alignment, node distribution by "neighbour stress", rotation, final routing.
  - *Summative study:* users were significantly faster and more accurate on HOLA layouts than on yFiles. HOLA now ships in Adaptagrams `libdialect`. [S] — [Adaptagrams](https://www.adaptagrams.org/documentation/libdialect.html)
- **IPSep-CoLa** (Dwyer, Koren, Marriott, IEEE TVCG 12(5), 2006): fast stress majorization subject to **separation constraints** x₁ + d ≤ x₂ (for example x₁ + (w₁ + w₂)/2 ≤ x₂ for non-overlap). The slides stress that "constraints are not springies, they must be satisfied", whereas springies only modify the goal function. Demonstrated constraint types: downward-pointing edges, page boundary, non-overlap, alignment. [P (slides)] — [Dwyer slides](https://www.cs.ubc.ca/~tmm/courses/533-09/slides/dwyer.subset.pdf)
  - Graphviz's `constrained_majorization_ipsep.c` supports directed-edge, non-overlap and cluster-containment constraints. [S] — [Graphviz source](https://archive.graphviz.org/Archive/development/doxygen/html/constrained__majorization__ipsep_8c_source.html)
  - WebCola monotonically reduces stress. [S] — [cola.js](https://ialab.it.monash.edu/webcola/examples/unconstrained.html)
- **libavoid** orthogonal connector routing (optimal object-avoiding routes; 1-bend visibility graph; nudging). [S] — [libavoid](https://www.adaptagrams.org/documentation/libavoid.html); [Wybrow thesis](https://ialab.it.monash.edu/~mwybrow/papers/wybrow-thesis-2008.pdf)
- **netlistsvg / d3-hwschematic**: ELK layered (Sugiyama) layout of netlists with `portConstraints = FIXED_ORDER`. [S] — [netlistsvg](https://github.com/shuckc/netlistsvg); [d3-hwschematic](https://www.npmjs.com/package/d3-hwschematic)
- **Cassowary** (incremental dual-simplex solver with constraint strengths required, strong, medium, weak; the basis of Apple AutoLayout). [S] — [UW tech report](https://constraints.cs.washington.edu/solvers/cassowary-tr.html); [docs.rs](https://docs.rs/cassowary)
- **Point-feature label placement** (Christensen, Marks, Shieber, ACM ToG 1995): NP-hard. In their empirical comparison **simulated annealing** worked best: move one label among candidate positions, accept worse moves with a temperature-controlled probability. A 1997 study found SA "outperforms all previously published practical algorithms" for variable-sized labels. [S] — [Harvard DASH](https://dash.harvard.edu/bitstream/1/2032678/2/AnEmpiricalStudy.pdf); [MERL TR97-13](https://merl.com/publications/docs/TR97-13.pdf)
- **Metro-map MIP** (Nöllenburg & Wolff, IEEE TVCG 2011): combined layout and labeling as one MIP, encoding seven real-world design rules as hard constraints (octilinearity, …) and soft costs. It finds a drawing satisfying all hard constraints whenever one exists. It extends to k-linear and arbitrary slope sets. [S] — [KIT PDF](https://i11www.iti.kit.edu/extra/publications/nw-dlhqm-10.pdf); [k-linear](https://ac.tuwien.ac.at/files/pub/smw19-paper-6.pdf)

### Inferences
- **Transfer to PCB — a HOLA-style "core + trees" placement.** Take the 2-core of the component connectivity graph (MCU, regulators, main connectors, high-degree ICs) as the **core**, laid out by constrained stress majorization. The **trees** are degree-1 or degree-2 peripherals: pull-ups, LEDs with resistors, test points, ESD diodes on single lines. Lay them out symmetrically and attach them *outside* the core on the side of the pin they serve, which is HOLA's R1 "trees on the outside". Then run opportunistic alignment of passives (R4 gridiness) and neighbour-stress distribution (even spacing, R8). This gives a principled initial placement that already looks "designed".
- **Transfer to PCB — HOLA's criteria as an aesthetic score.** Compactness, gridiness (share of parts in alignments of three or more), symmetry (mirror pairs, especially for differential and analog circuits), crossings (ratsnest), bends and segment-length variance can all be computed on a placed board and its ratsnest. Use them as the "human-likeness" part of the objective and as features for the VLM judge.
- **Transfer to PCB — hard separation constraints (IPSep-CoLa) for signal flow.** Keep signal-flow ordering (`x(J_in) + d ≤ x(U_filter) ≤ …`), board-boundary containment, block containment and non-overlap as *hard* separation constraints, and wirelength and stress as the goal. This matches the LLM-writes-constraints pattern while guaranteeing satisfaction, the property the Holodeck/PSDL lineage lacked when solvers could only satisfy relations softly.
- **Transfer to PCB — silkscreen reference-designator placement via map labeling (quick win).** Each refdes has a few candidate positions (above, below, left, right of the courtyard, rotated 0° or 90°). Conflicts with pads, other labels, vias and board edges form a conflict graph. Simulated annealing (Christensen et al.) or a small MaxSAT/ILP solves it. This is a common, tedious KiCad clean-up task that an LLM agent can trigger but should not do by hand.
- **Transfer to PCB — metro-map MIP for bus and route schematization.** After topological routing, a MIP that snaps long bus runs to octilinear (0°/45°/90°) segments with hard spacing and soft bend and length costs gives "professional-looking" 45° routing. The hard/soft split mirrors DRC versus aesthetics.
- **Transfer to PCB — Sugiyama/ELK seeding and libavoid previews** are unchanged from the first pass: layer index as x-order; orthogonal connector routing as a cheap routability and crossing metric.

### Gaps
- Full IPSep-CoLa paper text not retrieved (slides only).
- No paper applies HOLA or constrained stress majorization to PCB placement.

---

## Q7. Program synthesis / LLM-evolved algorithms (FunSearch, AlphaEvolve, EoH, ReEvo, OPRO): reported gains, and VLSI-specific evidence

### Takeaway
LLM-guided evolution of code or solutions now works on physical design.
- **FunSearch** (Nature) evolved a bin-packing priority function starting from best-fit that beat first-fit and best-fit on all OR-Library sets, and came within 0.03% of the lower bound on 100k-item Weibull instances.
- **AlphaEvolve** (2025) adds a MAP-Elites + island program database, evaluation cascades and LLM-generated feedback. It recovered 0.7% of Google's fleet compute via an evolved vector bin-packing priority function and found a simplification in a TPU arithmetic circuit. It also advises *evolving constructor functions for symmetric problems and bespoke search algorithms for asymmetric ones*.
- **VeoPlace** (NeurIPS 2026) has a VLM, with no fine-tuning, propose rectangular regions for macros. These act as action masks for ChiPFormer or soft anchors for DREAMPlace, evolved through an in-context history buffer. It improved DREAMPlace on all 8 Superblue designs (up to 4.4%) and ChiPFormer on 9 of 10 benchmarks (up to 32%). Open-weight Qwen3-VL-8B matched Gemini, and a random-region control lost.

### Cited Findings
- **FunSearch** (Nature 2023) [P] — [Nature](https://www.nature.com/articles/s41586-023-06924-6)
  - Evolves the heuristic starting from best fit; trained on OR1-sized instances; "outperforms both first fit and best fit across all datasets" and "generalizes… performing even better on large instances". On Weibull data it is "only 0.03% off the lower bound on the optimum for 100,000 items".
  - The discovered heuristic packs into the least-capacity bin only if the fit is very tight, "avoid[ing] leaving small gaps in bins that are unlikely to ever be filled".
  - Uses an island-based program database to keep diversity.
  - OR1–OR4 excess-bin figures (5.30/4.19/3.11/2.47% vs best fit 5.81/6.06/5.37/4.94%) are from secondary sources. [S] — [Wikipedia](https://en.wikipedia.org/wiki/FunSearch); [GitHub](https://github.com/google-deepmind/funsearch)
- **AlphaEvolve** (DeepMind 2025) [P] — [arXiv 2506.13131](https://arxiv.org/abs/2506.13131); [blog](https://deepmind.google/blog/alphaevolve-a-gemini-powered-coding-agent-for-designing-advanced-algorithms/)
  - *Loop:* parent program and "inspirations" sampled from the program database → prompt → LLM produces a diff → apply → evaluate → add back. The database combines MAP-Elites with island populations.
  - *Evaluation cascade:* candidates must pass increasingly hard test sets before full evaluation.
  - *LLM-generated feedback:* LLMs score properties that are hard to code as metrics.
  - *Multiple evaluation criteria:* programs that excel on different definitions of "good" are mixed into prompts.
  - *Abstraction choice:* evolve the raw solution, a constructor function, or a bespoke search algorithm. "For problems with highly symmetric solutions it is advantageous to evolve constructor functions… for problems with non-symmetric solutions it works better to evolve customized search algorithms."
  - *Results:* a data-center scheduling heuristic framed as two-dimensional vector bin packing (CPU, memory) recovers "on average 0.7% of Google's fleet-wide" resources. For a TPU arithmetic circuit it found a Verilog rewrite removing unnecessary bits, verified by TPU designers (also caught later by synthesis tools). New packing results (points, polygons in polygons, Heilbronn variants). The 11-dimensional kissing number lower bound rose from 592 to 593.
- **OpenEvolve** reproduced AlphaEvolve's n=26 circle packing at 2.634. [S] — [HF blog](https://huggingface.co/blog/codelion/openevolve)
- **EoH** (ICML 2024; evolves natural-language "thoughts" with code; beats FunSearch at low query budget) [S] — [arXiv 2401.02051](https://arxiv.org/html/2401.02051v3)
- **ReEvo** (NeurIPS 2024; LLM reflections as "verbal gradients") [S] — [arXiv 2402.01145](https://arxiv.org/abs/2402.01145v3)
- **OPRO** (ICLR 2024; meta-prompt of solution–score pairs) [S] — [arXiv 2309.03409](https://arxiv.org/pdf/2309.03409)
- **VeoPlace — "See it to Place it"** (Uchendu et al., Harvard/Google DeepMind; NeurIPS 2026; arXiv v3 Oct 2026) [P] — [arXiv 2603.28733](https://arxiv.org/abs/2603.28733)
  - *Interface:* the VLM outputs one rectangular region per macro on an 84×84 grid (ChiPFormer) or a 512×512 grid (DREAMPlace).
    - For learning-based placers, out-of-region logits are set to −∞ and renormalized, so the policy still picks exact coordinates inside the region.
    - For analytical placers, regions become **soft anchor terms** with weight λ_A. Low weights work best (λ_A = 0.01); λ_A ∈ {0.1, 1} over-constrains macros and blocks standard cells.
  - *Loop:* each iteration runs 8 unguided rollouts, then 1 VLM query returning 8 candidate region sets, then 8 guided rollouts. 2,000 rollouts means 125 VLM calls.
  - *Prompt:* a lightweight structured scaffold with the canvas image, macro properties and grid spec; developed only on adaptec1 to avoid overfitting.
  - *Context selection:* "Top Stratified" (sample across clusters, favour the best within clusters) is the default. Greedy "Best" selection performed worst, because elitism traps the loop in local minima.
  - *Ablations:*
    - Removing the image or the text, or shuffling images, changed results by under 0.8%; gains do not depend on one modality.
    - Random-region and anchor-to-best controls given 2× the rollouts both lost on all 8 Superblue designs.
    - Open-weight Qwen3-VL 8B/30B served locally matched Gemini 3.6 Flash.
  - *Results:* DREAMPlace improved on all 8 ICCAD-2015 Superblue designs (up to 4.4%); ChiPFormer improved on 9 of 10 benchmarks (up to 32%).
  - The earlier ICML 2025 version reported SOTA on 4 of 7. [S] — [ICML 2025](https://icml.cc/virtual/2025/51511)
- **OrderPlace** (2026; LLM-evolved macro placement order; −34.04% and −14.08% wirelength vs WireMask-EA and EGPlace) [S] — [Takara TLDR](https://tldr.takara.ai/p/2606.08904)
- **EvoPlace / LLM-evolved global-placement optimizers** (2025) [S] — [arXiv 2504.17801](https://arxiv.org/abs/2504.17801)
- **Evolution through Large Models (ELM)** (Lehman et al., 2022): code LLMs as **mutation operators** inside MAP-Elites produced hundreds of thousands of working Sodarace walker programs in a domain the model never saw, then trained a conditional model on them. OpenELM is the open implementation. [S] — [arXiv 2206.08896](https://arxiv.org/abs/2206.08896)
- **LLMs writing constraint models** (directly relevant to "LLM writes a CP-SAT placement model"):
  - Text2Zinc: GPT-4 reaches at most 25.39% solution accuracy on MiniZinc modeling. [S] — [arXiv 2503.10642](https://arxiv.org/abs/2503.10642)
  - CP-Bench: documentation-rich prompts plus repeated sampling and self-verification reach about 70%; Python frameworks (CPMpy, OR-Tools CP-SAT) are easier for LLMs than MiniZinc. [S] — [arXiv 2506.06052](https://arxiv.org/abs/2506.06052)
  - Per-global-constraint agent ensembles improve on chain-of-thought. [S] — [arXiv 2509.08970](https://arxiv.org/abs/2509.08970)

### Inferences
- **Transfer to PCB — a VeoPlace port (high payoff, medium effort, strongly evidenced).** Render the board with placed parts and block colours, and have a VLM propose a **region per functional block or per major IC** on a coarse grid. Feed the regions to a classical placer as soft anchors (λ ≈ 0.01-equivalent, i.e. weak) or as KiCad rule areas or rooms. Keep a history buffer of (render, region set, score), with top-stratified context selection and not greedy-best. Evaluate with routability-aware metrics. Since open 8B VLMs matched Gemini, this can run locally. The random-region control should be part of the PCB evaluation to show the VLM adds value.
- **Transfer to PCB — evolve router and placer heuristics with AlphaEvolve mechanics.**
  - *Evaluation cascade:* (1) runs and passes courtyard legality on 3 toy boards → (2) HPWL and congestion proxy on 20 boards → (3) full Freerouting or PathFinder routing and KiCad DRC on held-out boards.
  - *Evolution target:* PathFinder's `net_priority()`/`edge_cost()`, the PSDL repair neighborhood, the placement-order heuristic (OrderPlace), or the legalizer's GLS weight schedule.
  - *Abstraction choice:* evolve **constructor functions** for symmetric structures (LED matrices, memory buses, analog differential pairs) and **search algorithms** for irregular boards.
- **Transfer to PCB — "pros/cons" VLM feedback as AlphaEvolve's LLM-generated feedback.** Hard-to-code aesthetics (does it "look designed"? are decaps visibly adjacent?) can be added as an LLM-scored criterion within the multi-criteria database.
- **Transfer to PCB — don't make the LLM write the whole CP model from scratch.** Text2Zinc and CP-Bench suggest that LLM-written constraint models are unreliable unless the framework is Python (CP-SAT, CPMpy), documentation-rich, sampled repeatedly and self-verified. Better: provide a fixed, tested CP-SAT placement *template* (NoOverlap2D, board bounds, rotation booleans) and let the LLM add only typed constraints from a vocabulary. This is the PSDL lesson again.

### Gaps
- No LLM-evolved heuristic for PCB routing or placement published (none found).
- VeoPlace has not been tested with LLM-proposed regions on non-macro (fine-grained) placement, which is closer to PCB passives.

---

## Q8. Analogies from other physical-design domains: protein design, urban/road networks, chip-package co-design, microfluidics, quantum chips, photonics, wire harnesses

### Takeaway
Neighbouring domains contribute concrete subroutines:
- PACOR length-matched escape (DME + min-cost flow) for DDR-style buses;
- Qplacer frequency-aware electrostatic repulsion for EMI and noise-aware placement;
- photonic bending-aware wirelength and curvy A* for RF and high-speed traces;
- harness Pareto bundling for bus corridors;
- chip-package min-cost-flow RDL routing and bump assignment for MCU/FPGA pin-swap optimization;
- tensor-field street modeling for preferred routing directions;
- protein-design dead-end elimination (DEE) and AlphaFold recycling (Q2) for discrete orientation choice and iterative refinement.

### Cited Findings
- **Microfluidics**:
  - PACOR (DME Steiner + min-cost-flow escape + bounded-length detours; 100% completion) [S] — [NYCU](https://ir.lib.nycu.edu.tw/handle/11536/135751)
  - McDaniel et al. (negotiated-congestion escape routing on the PCB of a biochip) [S] — [UCR PDF](https://webarchive.ucr.edu/public/archived-sites/microfluidics.cs/microfluidics.cs.ucr.edu/media/371/tcad17-pcb_escape_routing4429.pdf)
  - RABER (control-port sharing) [S] — [TUM](https://mediatum.ub.tum.de/doc/1747600/1747600.pdf)
- **Quantum — Qplacer** (frequency-aware electrostatic placement; components as charges with a "frequency repulsive force"; ISCA 2025). Sources disagree on area savings (2.14× vs about 22–26%). [S] — [arXiv 2401.17450](https://www.arxiv.org/abs/2401.17450v3); [DAC tutorial](https://archive.dac.com/portals/0/62dac/quantum_tutorial.5ea54a3ce6.pdf)
- **Photonics**:
  - APR (curvy A*, adaptive crossing insertion, about 14% lower insertion loss) [S] — [arXiv 2410.01260](https://arxiv.org/html/2410.01260v1)
  - Apollo (bending-aware wirelength, GPU placement) [S] — [arXiv 2504.18813](https://arxiv.org/html/2504.18813v2)
  - LiDAR 2.0 [S] — [arXiv 2505.17239](https://arxiv.org/html/2505.17239v1)
- **Wire harness**:
  - Chalmers/Volvo (length vs **bundling** vs restricted zones; Pareto front; near-optimal in seconds to minutes) [S] — [Chalmers](https://research.chalmers.se/en/publication/540371)
  - TU Delft road-map + refinement [S] — [TU Delft](https://repository.tudelft.nl/file/File_e00f6f6b-a232-4af2-bea6-4150ed41044c?preview=1)
- **Chip-package**:
  - Min-cost max-flow RDL routing with 100% completion [S] — [ICCAD 2008](https://cecs.uci.edu/~papers/iccad08/PDFs/Papers/07A.4.pdf)
  - Routability-driven bump assignment inspired by board escape routing [S] — [ASP-DAC 2014](https://www.aspdac.com/aspdac2014/technical_program/pdf/6B-3.pdf)
  - Chiplet RDL co-design [S] — [TODAES 2025](https://e3da.csce.uark.edu/pub/doc/2025/Z.Zhuang-ACM.TODAES-2025.pdf)
  - Any-angle die-to-die routing (ISPD 2026) [S] — [slides](https://ispd.cc/slides/2026/protected/slides_3_3.pdf)
- **Urban**:
  - Tensor-field street modeling (SIGGRAPH 2008) [S] — [project](https://www.sci.utah.edu/~chengu/street_sig08/street_project.htm)
  - **LLM participatory urban planning** (2024): an LLM planner drafts a land-use plan; many LLM "resident" agents with profiles discuss it in a "fishbowl" mechanism; the planner revises. On two Beijing regions it reports SOTA resident satisfaction and inclusion, and better service accessibility and ecology metrics than human experts. [S] — [arXiv 2402.17161](https://arxiv.org/abs/2402.17161)
- **Protein design — dead-end elimination**: DEE (Nature 1992) proves certain rotamers (discrete side-chain states) cannot be in the global minimum and prunes them. Combined with A*, or with branch-and-bound plus MAP bounds (BroMAP), it guarantees the global optimum for pairwise energies; iMinDEE extends this to continuous flexibility. [S] — [Nature 1992](https://www.nature.com/articles/356539a0); [BroMAP](https://people.csail.mit.edu/tlp/pdf/2009/rotamer_optimization.pdf)

### Inferences
- **Transfer to PCB — DEE for orientation and side assignment.** After a coarse placement, each footprint's discrete state (4 rotations × 2 sides × a few snapped offsets) is a "rotamer". Pairwise "energies" are pin-to-pin wirelength and crossing counts between neighbours, plus courtyard conflicts. DEE prunes dominated states, then A* or ILP picks the global optimum over the remaining combinations. This is exact, fast for sparse interaction graphs, and explainable to the LLM ("U3 rotated 90° is provably dominated").
- **Transfer to PCB — LLM "stakeholder" agents (urban planning).** Use subsystem agents (power-integrity agent, SI/high-speed agent, thermal agent, DFM/assembly agent, mechanical/enclosure agent), each critiquing a proposed floorplan from its own profile. A planner agent revises, as in the fishbowl loop. This structures the LLM's multi-objective reasoning into explicit, auditable critiques. LayoutCopilot (Q10) is the analog-layout precedent.
- **Transfer to PCB — Qplacer, PACOR, photonics, harness, package and tensor-field transplants** are unchanged from the first pass: aggressor/victim repulsion terms; DME + min-cost-flow length matching; bend and via-aware costs for RF; bundling rewards for buses; pin-swap co-optimization using datasheet pin-mux knowledge; field-derived preferred directions.

### Gaps
- No PCB use of DEE found; the transfer is speculative but mechanically direct.
- Qplacer's area-savings figures conflict between sources.

---

## Q9. Quality-diversity (MAP-Elites) and generative design for producing multiple diverse layout candidates

### Takeaway
The closest analog to "PCB placement for routability" is in warehouse robotics. Zhang et al. (IJCAI 2023) optimized *warehouse layouts* for *lifelong-MAPF throughput* with MAP-Elites. Infeasible layouts were repaired by a MILP solver, and a deep surrogate predicted both the repaired layout and its throughput, so few expensive simulations were needed. The optimized layouts doubled the number of robots the warehouse supported in some cases. LLM-native QD variants (ELM: LLM as mutation operator; QDAIF: LLM judges quality and diversity; MarioGPT: novelty search with inpainting mutations) and fast libraries (pyribs, QDax on JAX) make this practical.

### Cited Findings
- **Multi-Robot Coordination and Layout Design for Automated Warehousing** (Zhang, Fontaine, Bhatt, Nikolaidis, Li; IJCAI 2023) [P] — [arXiv 2305.06436](https://arxiv.org/abs/2305.06436); [code](https://github.com/lunjohnzhang/warehouse_env_gen_public)
  - Instead of better MAPF algorithms, optimize the layout. Human-designed regular layouts congest with many robots.
  - MAP-Elites maximizes throughput from a lifelong-MAPF simulator (RHCR, DPP) while diversifying measures (number of connected shelf components, average task length).
  - Each candidate is **repaired by a MILP** to be valid and well-formed.
  - **DSAGE** trains an online surrogate that predicts both the MILP-repaired layout and the simulation outcome, so the archive can be explored on the surrogate.
  - Scaled to 200 robots. Optimized layouts reduce congestion and "improve the scalability… by doubling the number of robots in some cases".
- **pyribs** (CMA-ME, CMA-MAE; archive, emitters and optimizer modules) [S] — [GitHub](https://github.com/icaros-usc/pyribs)
- **QDax** (JAX; JIT-compiled QD, neuroevolution and RL on GPU/TPU; JMLR 2024) [S] — [arXiv 2308.03665](https://arxiv.org/abs/2308.03665); [docs](https://qdax.readthedocs.io/)
- **ELM**: LLM as mutation operator in MAP-Elites. [S] — [arXiv 2206.08896](https://arxiv.org/abs/2206.08896)
- **QDAIF** (ICLR 2024): an LM generates variations *and* evaluates quality (yes/no log-probabilities) and diversity (natural-language trait questions such as sentiment). Better coverage than non-QD baselines; human raters broadly agree with the AI evaluations; possible reward hacking; weaker correlation at the top of the quality range. [S] — [arXiv 2310.13032](https://arxiv.org/abs/2310.13032)
- **MarioGPT** (NeurIPS 2023): novelty search where a mutation replaces a slice of a level with a new LLM sample, and a second model (MarioBert) **inpaints the borders** to keep the level consistent. [S] — [arXiv 2302.05981](https://arxiv.org/abs/2302.05981)
- **VeoPlace** context-selection ablation: greedy-best context is worst; stratified diverse context is best. [P] — [arXiv 2603.28733](https://arxiv.org/abs/2603.28733)
- **AlphaEvolve's** program database is MAP-Elites plus islands; FunSearch uses islands. [P] — [arXiv 2506.13131](https://arxiv.org/abs/2506.13131); [Nature](https://www.nature.com/articles/s41586-023-06924-6)
- **T-DominO, ARCH-Elites, constrained MAP-Elites, FI-MAP-Elites, TileGPT, Autodesk Project Discover** (about 10,000 office layouts scored on six stakeholder metrics). [S] — [T-DominO](https://arxiv.org/pdf/2207.01439); [FI-MAP-Elites](https://github.com/konsfik/FI-MAP-Elites); [Autodesk](https://www.autodesk.com/autodesk-university/article/Hands-Project-Rediscover-Generatively-Designing-Autodesk-Toronto-Office-2020)
- No QD application to chip floorplanning or placement was found. [S] — search returned only GA/SA floorplanning, for example [arXiv 2607.21408](https://arxiv.org/pdf/2607.21408)

### Inferences
- **Transfer to PCB — a direct port of the warehouse pipeline (strong analogy).**

  | Warehouse | PCB |
  |---|---|
  | Layout | Placement |
  | Lifelong-MAPF throughput | Routability (routing completion, vias and length from PathFinder, the DATE MCTS router, or Freerouting) |
  | MILP repair | Legalizer (sparrow-style GLS or CP-SAT NoOverlap2D) |
  | DSAGE surrogate | CNN/GNN predicting the legalized placement's congestion map and routing success |
  | Diversity measures | Board area, single- vs double-sided fraction, signal-flow straightness, thermal spread |

  The output is a portfolio of placements that are all routable but differ in useful ways.
- **Transfer to PCB — LLM emitters and judges.** Use ELM-style LLM mutations ("swap the power block and the RF block", "rotate U2 to face J1") as one emitter type next to Gaussian/CMA emitters. Use QDAIF-style VLM questions as soft measures ("does the analog section look isolated from the switching regulator? yes/no"). Guard against reward hacking with hard DRC and routability metrics.
- **Transfer to PCB — MarioGPT-style region mutation plus inpainting.** Re-sample one *region* of the board (a block) with the generator (LLM program or diffusion, Q2) and inpaint the border with the legalizer so the rest stays consistent. These are local, coherent mutations.
- **Transfer to PCB — diversity in the LLM's context (VeoPlace).** When feeding past attempts back to an LLM or VLM, sample diverse good attempts, not just the best ones.

### Gaps
- No QD study on PCB or chip placement exists; the warehouse analogy is the closest validated precedent.

---

## Q10. Sweep of further domains: procedural content generation with constraints (WaveFunctionCollapse, answer-set programming), analog layout (retargeting, LLM copilots), origami/foldable boards, control cabinets, LLM→logic/constraint translation

### Takeaway
Four more families transfer well:
1. **Declarative PCG**: ASP "design-space" generators and WFC/model-synthesis constraint propagation. These suit tiled and repetitive board regions and give exhaustive or uniform sampling of valid configurations.
2. **Analog layout automation**: template extraction and retargeting (IPRAIL), LLM multi-agent layout copilots that turn designer intent into symmetry, array and matching commands (LayoutCopilot, LLANA). This is the closest existing "LLM drives a layout tool" precedent in EDA.
3. **Control-cabinet layout**: Pareto simulated annealing over wire length and heat, plus duct-based auto-wiring. This is a 3D-ish cousin of PCB placement with thermal co-objectives.
4. **LLM → ASP/constraint translation** for spatial reasoning. It improves reliability when the LLM translates and the solver reasons, but direct LLM constraint modeling is still error-prone.

### Cited Findings
- **ASP for procedural content generation** (Smith & Mateas, IEEE TCIAIG 2011): describe the generator's *design space* declaratively as an answer-set program and let the solver enumerate or sample valid artifacts. Applied to levels, mazes and dungeons. [S] — [paper PDF](https://course.ccs.neu.edu/cs5150f14/readings/smith_asp4pcg.pdf); [PCG book ch. 8](https://www.pcgbook.com/chapter08.pdf)
- **Model synthesis / WaveFunctionCollapse**:
  - Merrell's model synthesis (2007–2009) propagates tile-adjacency constraints.
  - Maxim Gumin's WFC (observe → propagate, overlapping patterns from one example image) popularized it. Gumin is also the first author of the Brown PSDL papers in Q1.
  - Merrell's 2021 comparison argues they are the same algorithm family, and that WFC struggles on large outputs because of cell ordering and lack of block modification.
  - WFC is used inside QD layout pipelines (TileGPT, T-DominO; Q9).

  [S] — [Wikipedia: Model synthesis](https://en.wikipedia.org/wiki/Model_synthesis); [Merrell comparison](https://paulmerrell.org/wp-content/uploads/2021/07/comparison.pdf); [WFC explained](https://boristhebrave.com/2020/04/13/wave-function-collapse-explained)
- **LLM + ASP for spatial reasoning**: LLM↔ASP feedback loops improve spatial-reasoning benchmarks; the LLM maps "A right of B" to `right(A, B)` and clingo infers the answer; DecompSR (2025) evaluates multi-hop spatial reasoning via LLM→ASP. [S] — [arXiv 2411.18564](https://arxiv.org/abs/2411.18564); [StepGame review](https://themoonlight.io/review/advancing-spatial-reasoning-in-large-language-models-an-in-depth-evaluation-and-enhancement-using-the-stepgame-benchmark); [arXiv 2511.02627](https://arxiv.org/abs/2511.02627)
- **Analog layout**:
  - **LayoutCopilot** (Peking University, 2024–25): a multi-agent LLM framework for interactive analog layout. Agents for classification, analysis, solution refinement and solution adaptation turn abstract intents ("improve matching") into concrete tool commands (`symAdd`, `deviceMove`, `deviceSwap`, array and `arraySpace`, `netTopology`), with the designer choosing among high-level options. Reports high accuracy on real designs. [P] — [arXiv 2406.18873](https://arxiv.org/abs/2406.18873)
  - **LLANA** (2024): LLM-enhanced Bayesian optimization for design-dependent constraint generation, including symmetry detection; code open. [S] — [CUHK PDF](https://webarchive.lib.cuhk.edu.hk/20241030001211mp_/http:/www.cse.cuhk.edu.hk/~byu/papers/C241-LLANA.pdf)
  - **Multi-level multi-agent RL** placement exploring *asymmetric* analog placements (DAC 2025 LBR). [S] — [arXiv 2503.22958](https://arxiv.org/abs/2503.22958)
  - **ACDC** (2025): a 10,000-sample synthetic benchmark of grid placement with y-axis symmetry, non-overlap and area minimization for LLMs. [S] — [arXiv 2512.09199](https://arxiv.org/abs/2512.09199)
  - **Layout retargeting/migration**: IPRAIL extracts a *structural template* from a tuned layout and re-applies it with new sizes and design rules (op-amps moved from 0.25 µm to 0.18 µm); template-based reuse in Virtuoso; abstract-device constraint-graph retargeting. [S] — [IPRAIL](https://labs.ece.uw.edu/ssrl/workspace/iprail/web_IPRAIL/JOURNAL_ELSEVIER.pdf); [Castro-López et al.](https://idus.us.es/handle/11441/92228)
- **Origami / foldable PCBs**:
  - PCB Origami (Sterman, Demaine, Oxman, 2013) folds 2D-fabricated PCB arrays into 3D products. [S] — [Demaine](https://erikdemaine.org/papers/PCBOrigami_MR2013/)
  - PCBend software designs foldable joints free of rigid components. [S] — [news summary](https://cursus.edu/en/28660/pcbend-electronic-origami)
  - Miura-ori stretchable boards, whose fold layouts are constrained by component dimensions. [S] — [npj Flex. Electron.](https://doaj.org/article/236ace2290f3475695c4f0b532b8e5b5)
- **Control cabinets**:
  - Pareto simulated annealing minimizing wire length and heat convection on a 14-component cabinet gave about 2× better wire length and 1.6× better heat while evaluating about 4.7% of feasible configurations. [S] — [arXiv 1906.04825](https://ar5iv.labs.arxiv.org/html/1906.04825)
  - Commercial tools auto-route wires through ducts by shortest path with fill-level and EMC-segregation checks. [S] — [Zuken E3.panel](https://zuken.com/en/product/e3series/cabinet-layout-and-routing/e3-panel)

### Inferences
- **Transfer to PCB — ASP or WFC for tiled and repetitive regions.** Keyboard matrices (switch + diode tiles), LED arrays, multichannel front-ends and connector breakout rows are tile systems. Encode allowed tile adjacencies (diode orientation, via sharing, trace channels) and let ASP (clingo) enumerate all valid tilings or WFC sample them. Choose by HPWL or routability. ASP's "design-space description" style also gives the LLM a declarative target that can be checked exhaustively on small regions. The KiCad 9 multichannel "rooms" are the natural host.
- **Transfer to PCB — LLM → ASP for relational sanity checks.** Before solving geometry, translate the LLM's relational constraints into ASP facts (`left_of(J1, U1)`, `near(C5, U1)`, `edge(J1, w)`) and let clingo detect contradictions, cycles in strict orders, and over-subscription of edge slots. This is an exact version of the open-universe contradiction patterns in Q1.
- **Transfer to PCB — the LayoutCopilot agent pattern.** The closest EDA precedent for this project:
  - an intent-classifier agent decides whether a request is concrete ("move C5 closer to U1") or abstract ("improve power integrity");
  - an analyzer agent proposes high-level options grounded in a knowledge base (PI, SI, EMI guidelines);
  - a refiner agent negotiates with the user;
  - an adapter agent maps the chosen option onto concrete KiCad API calls or DSL constraints.

  The "present options, let the designer choose" step is a human-in-the-loop version of QD portfolios.
- **Transfer to PCB — template retargeting (IPRAIL) for design reuse.** Extract a structural template (relative ordering, alignments, symmetry, spacing variables) from a good existing layout of a subcircuit (a reference buck converter layout from a datasheet, or a past board) and re-apply it to a new board with different footprints and rules. This fits PSDL: the template *is* an imperative program with variables, and retargeting is re-running it with new sizes plus repair.
- **Transfer to PCB — foldable/rigid-flex as a packing variant.** For rigid-flex or folded designs, panel assignment (which components go on which rigid segment) is a constrained bin assignment with no rigid parts allowed at fold joints. QD or ASP could enumerate fold layouts consistent with an enclosure.
- **Transfer to PCB — control-cabinet thermal co-objective.** Thermal spreading (distance between hot parts, keeping heat sources away from sensitive or temperature-rated parts) can be a second Pareto objective next to wire length, explored by Pareto SA. This gives the user explicit trade-off fronts rather than a single weighted sum.

### Gaps
- No ASP or WFC application to PCB layout found.
- LayoutCopilot's per-task accuracy table was only partially extracted.
- PCBend's primary paper not read.

---

## Q11. Most promising transplants, ranked by expected payoff vs effort (revised after primary reading)

### Takeaway
The deep pass *strengthened* the top of the ranking and moved two items up:
- **VeoPlace-style VLM regions**: robust across modalities, works with open 8B VLMs, beats random-region controls.
- **Synthetic-data diffusion**: the data recipe is cheap and PCB-scale.

It added three new high-value, low-effort items:
- the **sparrow GLS legalizer** on jagua-rs hazards;
- the **DATE 2023 polygon MCTS router** with an LLM PUCT prior;
- **map-labeling SA for silkscreen**.

Consistent negative evidence shapes the design. LLMs fail at direct MAPF (even 2 agents in a maze), at crossing-free drawing beyond tiny graphs (PlanarBench), at long relative-reference chains (R3L), and at free-form constraint modeling (Text2Zinc ≤ 25%). The LLM's job should therefore be **intent, structure, topology, priorities and critique**, with geometry handled by solvers and repaired near the LLM's intent.

### Cited Findings
Key evidence behind the ranking:
- PSDL imperative + LLM-free repair: 82.9% / 94.3% human preference; 7.13 edits per scene; 9.3 s; beats gradient descent and LLM self-repair on preference. [P] — [arXiv 2510.16147](https://arxiv.org/abs/2510.16147)
- LayoutVLM self-consistent relations + numeric poses: +40.8 PSA over I-Design. [P] — [arXiv 2412.02193](https://arxiv.org/abs/2412.02193)
- VeoPlace: all 8 Superblue designs improved; open 8B VLM matches Gemini; random-region control loses. [P] — [arXiv 2603.28733](https://arxiv.org/abs/2603.28733)
- sparrow and jagua-rs: open-source SOTA nesting via overlap elimination with GLS; millions of collision queries per second. [P] — [arXiv 2509.13329](https://arxiv.org/abs/2509.13329); [arXiv 2508.08341](https://arxiv.org/abs/2508.08341)
- DATE 2023 MCTS PCB router: 10/10 real boards routed vs 8/10 for FreeRouting and DeepPCB. [P] — [DATE PDF](https://past.date-conference.com/proceedings-archive/2023/DATA/603.pdf)
- HOLA human-derived criteria and algorithm. [P] — [HOLA PDF](https://ialab.it.monash.edu/~dwyer/papers/hola2015.pdf)
- Diffusion synthetic-data recipe at about 200 objects. [P] — [arXiv 2407.12282](https://arxiv.org/abs/2407.12282)
- Warehouse QD with MILP repair and surrogate: up to 2× robots supported. [P] — [arXiv 2305.06436](https://arxiv.org/abs/2305.06436)
- AlphaEvolve mechanics and FunSearch generalization. [P] — [arXiv 2506.13131](https://arxiv.org/abs/2506.13131); [Nature](https://www.nature.com/articles/s41586-023-06924-6)
- Negative results: LLM-MAPF [P] [arXiv 2401.03630](https://arxiv.org/abs/2401.03630); PlanarBench [P] [arXiv 2606.02010](https://arxiv.org/abs/2606.02010); R3L [P] [arXiv 2605.06758](https://arxiv.org/abs/2605.06758); Text2Zinc [S] [arXiv 2503.10642](https://arxiv.org/abs/2503.10642)
- Map labeling by SA [S] — [Harvard DASH](https://dash.harvard.edu/bitstream/1/2032678/2/AnEmpiricalStudy.pdf)

### Inferences
Ranked list (payoff and effort are my judgment; H/M/L):

| # | Transplant (source) | Concrete PCB mechanism | Payoff | Effort | Evidence / code |
|---|---|---|---|---|---|
| 1 | **PCB-PSDL imperative placement program + LLM-free repair** (Brown 2025) | Footprints with `.min/.max/.center/.facing/.side`, pin handles; `set_frame(U1)`, `row`, `ring` with **shared variables**; repair = coordinate descent over constants (×2, ×0.5, ±δ, flip 90°), loss = overlap + outline + keepouts + decap distance; tie-break with area-weighted transport distance to the LLM layout | H | L–M | [P] strong human study; PCB parts are 4-orientation, matching PSDL's assumption |
| 2 | **Hybrid numeric poses + self-consistent relations + projected-gradient placer** (LayoutVLM; open-universe repair rules) | LLM gives rough (x, y, θ) and frame-free relations; keep only self-consistent relations; DIoU-style courtyard loss; projected gradient descent into the outline; group-by-group placement with re-render; open-universe contradiction/unsat handling and centroid no-overlap gradient | H | M | [P] |
| 3 | **VLM region proposals + classical placer + in-context evolution** (VeoPlace) | VLM proposes block/IC regions on a grid → soft anchors (weak λ) or KiCad rooms; 8 unguided + 1 VLM query + 8 guided per iteration; top-stratified history; include a random-region control | H | M | [P]; works with local Qwen3-VL 8B |
| 4 | **Render → VLM pros/cons judge + best-of-N + skill library** (PSDL auto-metric, SceneCraft, LayoutPrompter) | Pairwise VLM comparison with a pros/cons list (about 77% human agreement in scenes); ranker for N candidates; library of verified subcircuit macros | H | L | [P] |
| 5 | **sparrow-style overlap-elimination legalizer on jagua-rs hazards** (nesting) | Fix outline; courtyards and keepouts as hazards; allow overlaps; GLS pair weights; exploration then compression; displacement-to-target term preserves intent | M–H | L–M | [P] open source (check license) |
| 6 | **HOLA core/tree decomposition + IPSep-CoLa hard separation constraints** (graph drawing) | 2-core ICs laid out by constrained stress; peripheral trees placed symmetrically outside; signal-flow and containment as hard separations; HOLA criteria as aesthetic score | H | L–M | [P] HOLA; [P-slides] IPSep; Adaptagrams/Graphviz code |
| 7 | **Polygon-zone MCTS global router + A* + dynamic re-partitioning, with LLM PUCT prior and LLM net ordering** (DATE 2023; LLM-MCTS) | Pad-edge-extension partitions; MCTS over polygon sequences; C_res pushes traces off pads; re-split after each net; LLM supplies prior and rip-up choices | M–H | M | [P] PCB-native, real boards |
| 8 | **LLM-evolved heuristics with AlphaEvolve mechanics** (FunSearch, AlphaEvolve, OrderPlace, EvoPlace) | Evolve PathFinder costs, net order, placement order, repair neighborhoods; evaluation cascade; constructor functions for symmetric blocks; LLM-scored aesthetics as a criterion | H (long run) | M (compute) | [P]; OpenEvolve |
| 9 | **QD portfolio with legalizer repair + routability surrogate + LLM emitters/judges** (warehouse DSAGE, ELM, QDAIF, MarioGPT) | MAP-Elites over (area, sidedness, flow straightness, thermal spread); legalizer as repair; congestion/routability surrogate; LLM mutations; VLM yes/no measures; region resample + inpaint | M–H | M | [P] warehouse; pyribs/QDax |
| 10 | **Synthetic-data netlist-conditioned diffusion placer with DSL guidance** (Lee et al.; Diffusion-CCSP; AlphaFold recycling) | Random legal footprint placement → sample pad nets with p ∝ exp(−l/s); GNN+attention denoiser; guidance = courtyard overlap + DSL potentials with dual ascent; per-constraint-type composable energies; recycling passes | H (long run) | H | [P]; data recipe cheap at PCB scale |
| 11 | **Silkscreen refdes placement by map-labeling SA** (cartography) | Candidate label positions per footprint; conflict graph (pads, vias, labels, edges); SA or MaxSAT | M | L | [S]; classic |
| 12 | **Sequence-pair completion of LLM pairwise relations** (VLSI floorplanning) | LLM left-of/below relations → partial sequence pair → complete → longest-path decode guarantees legality; anneal the remainder | M | L–M | [S]; classic |
| 13 | **DEE + A*/ILP for discrete orientation and side states** (protein design) | Footprint rotation/side states as rotamers; pairwise wirelength, crossing and conflict energies; provable pruning | M | M | [S] |
| 14 | **Homotopy-first routing with LLM topology hints** (topological routing) | LLM states side-of-obstacle sequences; topological crossing check; rubber-band realization | H (potential) | H | [S] |
| 15 | **LLM as MAPF/negotiation meta-controller** (CBS/MC-CBS, PIBT/LaCAM, PathFinder) | LLM sets net priorities, conflict choices, per-class costs; solvers compute paths (never the LLM) | M | M–H | [P] negative LLM-MAPF result motivates this split |
| 16 | **ASP/WFC for tiled regions + LLM→ASP sanity checks** (PCG) | Enumerate valid tilings for matrices and arrays; clingo checks LLM relation sets for contradictions | M (niche) | L–M | [S] |
| 17 | **SAT/ZDD local windows** (Numberlink, Factorio-SAT) | Exact escape and fan-out solving or enumeration in small windows; LLM picks topology | M | M | [S] |
| 18 | **LLM stakeholder agents + analog-copilot pattern** (urban LLM planning, LayoutCopilot) | Power-integrity, SI, thermal, DFM and mechanical critic agents; planner revises; options presented to the user; adapter maps to KiCad calls | M | L–M | [P] LayoutCopilot; [S] urban |
| 19 | **Template retargeting of reference layouts** (analog IPRAIL) | Extract a structural template (orders, alignments, spacing variables) from a datasheet or past layout → re-run as a PSDL program with new footprints + repair | M–H | M | [S] |
| 20 | Pin-swap co-optimization (package bump assignment), Qplacer-style EMI repulsion, PACOR length matching, harness bundling, tensor-field direction fields, Pareto thermal co-objective (control cabinets) | As described in Q8/Q10 | L–M each | L–M | [S] |

**Suggested composite architecture:**
1. LLM/VLM produces a *board plan*: blocks, regions (VeoPlace-style) and relations.
2. LLM writes a PCB-PSDL placement program using skill-library macros.
3. Run it, then apply LLM-free repair (#1). Where repair stalls, hand over to the hybrid projected-gradient placer (#2), seeded with HOLA/IPSep layout (#6).
4. Legalize with sparrow-style GLS on jagua-rs hazards (#5); resolve orientations exactly with DEE (#13).
5. Place silkscreen labels (#11).
6. Route with the polygon-MCTS or PathFinder router guided by LLM priorities and homotopy hints (#7, #14, #15), with SAT windows for hard escapes (#17).
7. Rank candidates with the VLM pros/cons judge (#4) and present a QD portfolio with Zachtronics-style metric histograms (#9).
8. Improve the heuristics offline with AlphaEvolve-style evolution (#8).
9. Long-horizon research track: the diffusion prior (#10), trained on synthetic and QD-generated data.

### Gaps
- No head-to-head PCB benchmark exists for these transplants. PCBWorld (2026), an open KiCad routing environment with DRC-grounded feedback, may serve as one. [S] — [arXiv 2607.05915](https://arxiv.org/abs/2607.05915)
- Licenses of key open-source components (jagua-rs/sparrow, HOLA/Adaptagrams, Holodeck, LayoutVLM, DATE router code if any) were not verified in this pass.
- Payoff/effort scores are judgment calls, not measurements.
