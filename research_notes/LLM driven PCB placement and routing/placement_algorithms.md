# Automatic Component Placement Algorithms for PCBs (and Transferable VLSI / Analog Placement Methods)

**Scope tags.** Each finding is tagged **[PCB]** (evaluated on real printed circuit boards), **[VLSI]** (digital IC benchmarks only) or **[Analog IC]**. Unless a finding says otherwise, assume a VLSI result has **not** been shown to carry over to PCBs.

**Read-depth tags.** Each citation also says how deeply it was read:
- **(P)** = primary full text or source code, read directly (PDF, repository code, or KiCad source/commit history).
- **(A)** = abstract or bibliographic metadata only (arXiv abstract page, Semantic Scholar/OpenAlex abstract, publisher listing, or README).
- **(S)** = search-engine summary only; treat as lower confidence.

**How this was researched.**
- *First pass.* Only GitHub was reachable. PCBAgent and ModuPlace were read in full from PDF copies on GitHub.
- *Second pass.* arXiv and university PDFs became reachable via curl. Read in full in this pass: NS-Place, the double-layer placer (arXiv 2502.14012), Lim 2026, HiePlace, OmniLayout, the MAGICAL ICCAD'19 paper, the ALIGN overview paper, "Revisiting Floorplan Representations" (ISPD'01), the GenAI-for-PCB survey (arXiv 2606.17074), and two thermal-surrogate papers.
- *Source code read:* Cypress (NVlabs), ALIGN's placer, and KiCad's autoplacer at the 5.1/6.0/7.0/8.0/9.0/master branches, plus the GitLab commit history.
- *Not reachable:* ACM DL and IEEE full texts (bot-blocked), and Cornell/UMich PDFs (TLS chain failures).
- *Budgets:* the shared web-search budget ran out a second time in this pass. OpenAlex's anonymous daily budget also ran out, so citation-following for some recent papers used Semantic Scholar instead.
- *Verification:* a separate track is verifying headline numbers for NS-Place, HiePlace, Cypress, RL_PCB, PCBAgent, ModuPlace, VeoPlace, EvoPlace, OrderPlace, chip diffusion and TILOS. Where a number below comes from my own full-text read, it is marked (P).

---

## Q1. Classical placement methods (force-directed, analytical, SA, GA, partitioning, floorplan representations, CP/ILP/SMT): what they are, and which ones PCB tools actually use

### Takeaway
Real PCB placers, in shipping tools and in academia, fall into four classes:
- **Greedy grid heuristics.** KiCad's built-in autoplacer.
- **SA and metaheuristics.** SA-PCB, B*-tree SA, GA/PSO, commercial Trace.
- **Analytical / force-directed global placement plus a discrete legalizer.** NS-Place, Zhao 2025, PA-ICM, Cypress, and the 2025 NTU (Yao-Wen Chang) placers.
- **Mathematical programming.** HiePlace, MILP/QP legalizers.

Since 2025 the field has converged on **VLSI-style analytical global placement adapted for PCBs**. The adaptations are rotation variables (Gumbel-softmax, evolutionary, or enumeration), two-sided density maps, pad-to-pad clearance and net-crossing terms, and exact or irregular footprint geometry. These feed **MILP/QP/constraint-graph legalization**. VLSI analytical placers do not work out of the box: NS-Place reports that vanilla RePlAce "fails to find good solutions for multi-layer designs with diversely sized components."

### Cited Findings

**Force-directed / quadratic (spring) placement [VLSI foundational; PCB origin]**
- The earliest PCB placer in this lineage is Quinn & Breuer's "A forced directed component placement procedure for printed circuit boards" (IEEE Trans. Circuits Syst., 1979). HiePlace cites it as the exemplar of force-directed PCB placement, and notes that analytical PCB approaches have been validated on "oversimplified or synthetic" cases. — [HiePlace PDF (P)](https://www.cse.cuhk.edu.hk/~byu/papers/J156-TCAD2026-HiePlace.pdf)
- Quadratic analytical placers are called "force-directed" because they behave like point masses joined by springs. — [Sigl et al., ACM DL (S)](https://dl.acm.org/doi/pdf/10.1145/127601.127707)
- GORDIAN (Kleinhans et al., TCAD 1991) minimizes quadratic wirelength and spreads cells by recursive partitioning. Kraftwerk, FastPlace and SimPL share this framework and differ in how they compute the spreading "density force". — [Wikipedia: Placement (EDA) (S)](https://en.wikipedia.org/wiki/Placement_(electronic_design_automation)); [Cheong & Si survey (S)](https://journals.sagepub.com/doi/abs/10.1177/1473871618821740)
- Kraftwerk2 (Spindler et al., TCAD 2008) is a force-directed quadratic placer with the Bound2Bound net model. — [ResearchGate (S)](https://www.researchgate.net/publication/3225893_Force-Directed_Methods_for_Generic_Placement)
- SimPL (Kim, Lee, Markov, TCAD 2012) alternates a lower-bound quadratic solve with an upper-bound look-ahead legalization. — [SimPL PDF (S)](https://janders.eecg.utoronto.ca/1387/readings/simpl.pdf)
- **[PCB, 2025–26]** Two force-directed placers from NTU (Yao-Wen Chang's group):
  - The TCAD 2025 paper "Modern Automatic PCB Placement With Complex Constraints" (Tsou, Lin, Hung, Chang) combines SA-based **pad alignment** to reduce wire crossings, **force-directed global placement guided by anchor points extracted from power-circuit flows**, and window-based legalization. On real industrial designs it reports **+13.5% routability and −26% runtime vs ePlace-MS, and >50% better routability than Cypress**. — [OpenAlex/S2 abstract (A)](https://doi.org/10.1109/tcad.2025.3618936)
  - The DAC 2025 Late-Breaking Result (Tsou, Lee, Chang) uses **Separating-Axis-Theorem collision detection on exact component contours and board shapes**, multi-stage force-directed placement that adapts attraction and repulsion to clearance and routability, and scanline legalization. — [abstract (A)](https://doi.org/10.1109/DAC63849.2025.11132719)
- kicad-tools (an open-source LLM-agent toolkit for KiCad) ships a force-directed `PlacementOptimizer`, a GA, a hybrid of the two, and CMA-ES/Bayesian strategies. No objective is documented. — [rjwalters/kicad-tools (A)](https://github.com/rjwalters/kicad-tools)

**Nonlinear analytical / electrostatic placement: ePlace, RePlAce, DREAMPlace, and the PCB adaptations [VLSI → PCB]**
- ePlace (Lu et al., DAC'14 / TODAES'15) models cells as charges, takes the electrostatic potential energy (via FFT) as the density penalty, and optimizes with Nesterov's method using Lipschitz step prediction. — [ePlace DAC'14 PDF (S)](https://cseweb.ucsd.edu/~jlu/papers/eplace-dac14/paper.pdf); [ePlace-MS (S)](https://cseweb.ucsd.edu/~jlu/papers/eplace-ms-tcad14/paper.pdf)
- RePlAce (TCAD 2019) adds routability work on top of ePlace. — [RePlAce PDF (S)](https://vlsicad.ucsd.edu/Publications/Journals/j126.pdf)
- DREAMPlace recasts analytical placement as neural-network training in PyTorch, claims more than 30x speedup over CPU RePlAce on ISPD05, and has added fence regions (3.0), timing (4.0), and more. BSD-3. — [DREAMPlace GitHub (A)](https://github.com/limbo018/DREAMPlace)
- **[PCB] NS-Place reports that vanilla RePlAce "fails to find good solutions for multi-layer designs with diversely sized components"** and that its convergence depends on design-specific parameters such as filler cells and anchor weights. — [NS-Place arXiv 2210.14259 (P)](https://arxiv.org/pdf/2210.14259)
- **[PCB] Cypress** (Zhang, Agnesina, Shbat, Leader, Z. Zhang, Ren; Cornell + NVIDIA; ISPD'25) is built directly on DREAMPlace. **Read in its source code (Apache-2.0):**
  - **Orientation:** learned per-component **orientation logits** are sampled through **Gumbel-softmax** and optimized with a separate Adam optimizer.
  - **Board sides:** each component's side comes from its input orientation (an "F" prefix means bottom). Side is **not optimized**.
  - **Density:** **separate top and bottom electric-potential density maps and overflow**.
  - **Legalization:** run **per side**, using macro, greedy and Abacus legalizers.
  - **Added ops:** a differentiable **net-crossing** cost that is side-aware via `pin_side` (flag on by default; weight is a parameter), a **RUDY**-guided area adjustment, and an **RMST wirelength** op.
  - **Tuning:** BOHB hyperparameter tuning through hpbandster (`tuner/run_tuner.sh`).
  - **Benchmarks:** 20 Bookshelf benchmarks (`small-1..20`) and 10 KiCad `.kicad_pcb` artifacts.
  - **Converters:** from KiCad and from the NS-Place benchmark format (`pcb-util/kicad_converter.py`, `nsplace_converter.py`).
  - Sources: [NVlabs/Cypress code (P)](https://github.com/NVlabs/Cypress)
- **Cypress paper abstract:** commercial designs exceed 10,000 components. Reported results are **1–5.9x higher routability** and **1–19.7x shorter routed track length** on fully routed designs, and up to **492.3x** GPU speedup. Cypress also introduces a PCB benchmark suite "synthesized from real commercial designs". — [S2/ACM abstract (A)](https://dl.acm.org/doi/10.1145/3698364.3705346). The ISPD'25 slides say Cypress improves routability by up to 1.2x over SA-PCB. — [search summary of slides (S)](https://ispd.cc/ispd2026/slides/2025/protected/3_1_slides.pdf)
- Award status conflicts. Cornell reports Cypress won ISPD'25 Best Paper, but the ISPD slides label it a nominee. — [Cornell news (S)](https://zhang.ece.cornell.edu/news/cypress_ispd_bpa.html)
- **[PCB] Clearance-Constrained PCB Global Placement with Heterogeneous Components** (Chen, Huang, Tsai, Ou, Chang; DAC'25) has four parts:
  - a **wire-area model** that accounts for the different routing-resource needs of power and signal nets;
  - a **pad-to-pad clearance model**;
  - a **two-sided, pad-type-aware density model**;
  - a **QP-based legalizer** for components of varying shapes.
  It reports better post-routing quality than "two state-of-the-art academic placers" on academic and industrial benchmarks. — [abstract (A)](https://doi.org/10.1109/dac63849.2025.11133056)
- **[PCB] Zhao, Hu, Chai, Liu (Integration, 2025)** optimize **rotation jointly with position during gradient descent**, then apply Hanan-grid legalization and "insensitive component" fine-tuning to open up routing space. Tested on 10 PCB designs with an open-source router. — [ScienceDirect (A)](https://www.sciencedirect.com/science/article/abs/pii/S016792602500224X). A follow-on from the same group, **MARS-Place** ("Multi-stage alignment-refined strategy for PCB placement and routing optimization", Integration 2026), was seen only as a title. — [S2 record (A)](https://doi.org/10.1016/j.vlsi.2026.102671)
- **[PCB] PA-ICM** (Li, Yang, Pang, Xu, Chen; Wuhan Univ. of Technology; arXiv 2502.14012, also ICICM 2025). **Read in full:**
  - **Model.** Mixed-variable: orientations r_i ∈ {0, π/2, π, 3π/2}, optimized by a distribution evolutionary algorithm (DEA-PPM), plus coordinates optimized by a **conjugate subgradient algorithm**.
  - **Top-layer objective.** α·HPWL + β·√(overlap area) + γ·(out-of-contour length), with α=1, β=20, γ=100.
  - **Bottom layer.** Uses **DBSCAN clustering of the IC's pins**, so each cluster is optimized independently.
  - **Legalization.** Directional push-apart (1-unit shifts), then a spacing table, then maximal empty rectangles for out-of-bounds parts, then re-sampling of "close-to-pin" parts from N(pin, σ=2).
  - **Fixed-outline floorplanning benchmarks.** It beat Parquet 4.5 and IARFP on HPWL for ami49 through n300 at about 1–4 s per run, but lost on ami33.
  - **Industrial cases.** Four cases (80–148 blocks; up to 1,932 IC-pin terminals) ran in roughly 3–33 s on a laptop.
  - **Evaluation gap.** No routing evaluation.
  - Sources: [arXiv 2502.14012 (P)](https://arxiv.org/pdf/2502.14012); [ICICM 2025 abstract (A)](https://doi.org/10.1109/ICICM66614.2025.11316007)

**Simulated annealing (TimberWolf lineage) [VLSI origin; PCB use confirmed]**
- SA-PCB (OpenROAD/UCSD) is a "C++ annealer for simple PCB placement of polygonal components". It uses a TimberWolf-style cooling schedule, Ben-Ameur automatic initial temperature, and cost = HPWL + analytical polygon overlap (Boost.Geometry). Rotation is 90°/45° (free rotation in progress); input is Bookshelf with an Eagle converter. Known issues: parameter sensitivity and broken weighted nets. BSD-3, archived. — [SA-PCB GitHub (A)](https://github.com/The-OpenROAD-Project/SA-PCB)
- **[PCB]** SA-PCB is now the standard open baseline:
  - In ModuPlace's 11-board study, routed wirelength averaged 1528.5 for SA-PCB vs 1266.5 for ModuPlace, and vias 81.7 vs 48.6. — [ModuPlace PDF (P)](https://yhhan.com/PDFs/ModuPlace_paper.pdf)
  - OmniLayout also uses SA-PCB as a baseline. — [OmniLayout arXiv 2607.03261 (P)](https://arxiv.org/abs/2607.03261)
- **[PCB]** HiePlace describes the conventional PCB approach as "B*-tree representations … wirelength and area … SA", and notes that tree representations suffer from incomplete solution-space coverage. Its own baseline is B*-tree + Fast-SA **with manual adjustments**. — [HiePlace (P)](https://www.cse.cuhk.edu.hk/~byu/papers/J156-TCAD2026-HiePlace.pdf)
- **[VLSI]** A tuned multithreaded SA beat Circuit Training on proxy cost in 17/17 ICCAD04 cases. — [TILOS MacroPlacement (A)](https://github.com/TILOS-AI-Institute/MacroPlacement)
- **[Commercial, PCB] Trace** (KiCad-integrated). Claude first analyzes the schematic (groups, critical nets, thermal, edge parts, proximity rules), then several floorplan variants seed SA. SA uses 8 move types; cost = HPWL + RUDY + group compactness + thermal distribution. — [Trace docs (S)](https://docs.buildwithtrace.com/concepts/pcb-layout)
- **[PCB]** Lim 2026 compares SA with DQN and A2C on a discretized component-centric layout. Results are in Q3. — [arXiv 2602.23540 (P)](https://arxiv.org/abs/2602.23540)

**Greedy grid placement: KiCad's built-in autoplacer [PCB tool]. Rotation question resolved from source.**
- **Current algorithm (master and 9.0, read in source):**
  - **Grid.** A 1.0 mm occupancy matrix (`STEP_AR_MM`), hard-coded to two routing layers.
  - **Order.** Footprints are picked in order of area × pad count, then area × ratsnest-connection count.
  - **Search.** For each footprint, every grid position is scanned. Score = ratsnest cost (`hypot(dx, 2·dy)` to the nearest same-net pad) + a keep-out cost whose margin scales with pad count / `AR_GAIN` (16).
  - **Sides.** Footprints keep their layer. The other side is checked only when the footprint has through-hole pads.
  - **No rotation search.**
  - Sources: [ar_autoplacer.cpp master (P)](https://github.com/KiCad/kicad-source-mirror/blob/master/pcbnew/autorouter/ar_autoplacer.cpp)
- **History of rotation (P):**
  - Up to and including **KiCad 6.0**, the autoplacer tried 180°, 90° and 270° from the initial orientation. Each trial cost was multiplied by an `OrientationPenalty[0..10]` table (2.0 down to 1.0) driven by per-footprint "CntRot90/CntRot180" rotation-cost sliders, where 0 meant rotation prohibited. — [ar_autoplacer.cpp at 6.0 (P)](https://github.com/KiCad/kicad-source-mirror/blob/6.0/pcbnew/autorouter/ar_autoplacer.cpp)
  - Commit **d649b288 (Jeff Young, 2021-12-24)**, "Swap out autoplace rotation costs for private footprint layers" (fixes issues #2291 and #5391), removed the sliders and rotation logic. They are therefore **absent from 7.0, 8.0, 9.0 and master** (zero rotation references in those files). — [GitLab commit (P)](https://gitlab.com/kicad/code/kicad/-/commit/d649b288a62aac5c31489bc41ab22149d7339014)
  - This explains the conflict noted in my first pass: the archived kicad-doc (5.x era) still describes 0/90/−90/180 trials. — [kicad-doc (P)](https://github.com/KiCad/kicad-doc/blob/master/src/pcbnew/pcbnew_footprint_placement.adoc)
- **UI in 9.0/master:** Place ▸ Auto-Place Footprints ▸ "Place Off-Board Footprints" / "Place Selected Footprints". It requires an Edge.Cuts outline, skips locked footprints, and commits as one undo step. — [menubar_pcb_editor.cpp 9.0 (P)](https://github.com/KiCad/kicad-source-mirror/blob/9.0/pcbnew/menubar_pcb_editor.cpp); [autoplace_tool.cpp (P)](https://github.com/KiCad/kicad-source-mirror/blob/master/pcbnew/autorouter/autoplace_tool.cpp)
- In 2016 a developer called the autoplacer "terrible" and argued for removing it. — [Launchpad bug 1633256 (S)](https://bugs.launchpad.net/kicad/+bug/1633256)

**Partitioning-based (min-cut) placement [VLSI]**
- Capo (Caldwell, Kahng, Markov, DAC 2000) asked whether recursive min-cut bisection alone yields routable placements. Its components: a multilevel min-cut partitioner (UCLA MLPart), small-tolerance partitioning, optimal end-case partitioners and placers, and block splitting. It does **not** use multi-way partitioning, analytical placement or congestion estimation. Later Capo versions added mixed-size, fixed-outline floorplanning and incremental placement. — [Capo DAC'00 PDF (S)](https://web.eecs.umich.edu/~imarkov/pubs/conf/c015.pdf); [Capo book chapter (S)](https://web.eecs.umich.edu/~imarkov/pubs/book/ispdbk-capo.pdf)
- ROOSTER, a min-cut placer modelling nets as rectilinear Steiner minimal trees, is cited by NS-Place as a congestion-aware technique. NS-Place argues that such techniques suffer from inadequate estimation or prohibitive cost. — [NS-Place (P)](https://arxiv.org/pdf/2210.14259)
- GORDIAN used partitioning for spreading (see above). Today, partitioning survives mostly as **clustering for hierarchy**: hMETIS in Circuit Training, and DBSCAN in PA-ICM. — [circuit_training (A)](https://github.com/google-research/circuit_training); [PA-ICM (P)](https://arxiv.org/pdf/2502.14012)

**Floorplan representations: sequence pair, B*-tree, O-tree, corner block list, Polish expression [VLSI/analog; used for PCB module floorplanning]**
- Yao, Chen, Cheng and Graham ("Revisiting Floorplan Representations", ISPD'01) compare representations by solution-space size and transform time:

  | Representation | Solution space | Transform time |
  |---|---|---|
  | Sequence pair | O((n!)²) | O(n log log n) |
  | Bounded-sliceline grid | n!·C(n², n), highly redundant | O(n²) |
  | O-tree | O(n!·2^(2n−2)/n^1.5) | O(n) |
  | Corner block list (Hong et al., ICCAD'00) | O(n!·2^(3n−3)/n^1.5) | O(n) |

  The paper also counts **mosaic floorplans** (Baxter numbers) and **slicing floorplans** (Schröder numbers), and proposes twin binary trees as a non-redundant mosaic representation. A CBL represents a **mosaic floorplan**, which covers all slicing floorplans and all non-slicing floorplans with exactly n rooms for n blocks. — [ISPD'01 PDF (P)](https://www.esa.informatik.tu-darmstadt.de/archive/twiki/pub/Lectures/AlgorithmenImChipEntwurf06De/floorplan-ispd01.pdf)
- CBL cannot represent empty rooms, so CBL-based search cannot always reach the optimum. Extended CBL (ECBL) adds empty rooms, and there are 3-D and boundary-constrained CBL extensions. — [Atlantis Press (S)](https://www.atlantis-press.com/article/215.pdf); [Springer (S)](https://link.springer.com/article/10.1360/01yf0558); [J. Semicond. (S)](https://www.jos.ac.cn/article/id/4d2a4e22-8266-418d-996a-1c6e0cdbb06f)
- B*-tree Fast-SA (Chen & Chang) perturbs by rotating a block, moving a node, or swapping nodes. — [NTU chapter (S)](https://cc.ee.ntu.edu.tw/~ywchang/Courses/PD_Source/EDA_floorplanning.pdf); [Fast-SA ISPD'05 (S)](https://cc.ee.ntu.edu.tw/~ywchang/Papers/ispd05-floorplanning.pdf)
- **[PCB]** Topological representations are used for PCB, but less and less:
  - PA-ICM states that representation-based methods (sequence pair, B*-tree, O-tree) "cannot accommodate" IC-centred two-layer modules efficiently, so it prefers analytic methods. It does cite a 2024 PCB **centralized block placement based on sequence pair** (Li et al., ICCCAS'24) and a multi-constraint PCB placer (Wang et al., ICCCAS'24). — [PA-ICM refs (P)](https://arxiv.org/pdf/2502.14012)
  - Older PCB-specific SP work includes "VLSI/PCB placement with predefined coordinate alignment constraint based on sequence pair" (Liu et al., ASICON 2001) and the "Relay-race algorithm" for VLSI/PCB (Sheng et al., ISVLSI 2011). — [HiePlace refs (P)](https://www.cse.cuhk.edu.hk/~byu/papers/J156-TCAD2026-HiePlace.pdf)
- OpenROAD Hier-RTLMP: SA over a cluster hierarchy, with named default weights (area 0.1, outline 100, wirelength 100, boundary 50, notch 10, blockage 10, guidance 10, fence 10). — [OpenROAD src/mpl (A)](https://github.com/The-OpenROAD-Project/OpenROAD/tree/master/src/mpl)

**Constraint programming / ILP / MILP / QP / SMT [PCB legalization confirmed]**
- **[PCB] NS-Place** (Cheng, Ho, Holtz, UCSD; ASP-DAC'22). **Read in full:**
  - **Global objective.** Σ[WA wirelength + λ_NS·net-separation] + λ_D·density. Density is the APlace-style bin overlap.
  - **Net separation.** Models each net's routing region as the **convex hull of its pins** and penalizes failure of an SVM-style separating hyperplane with margin between net pairs (alternating minimization over hyperplanes and positions).
  - **Initialization.** **Laplacian eigenvectors** (Hall's quadratic placement / sparsest-cut approximation), enumerating relative orientations to choose the seed.
  - **Legalization.** **MILP** over overlap, boundary and orientation binaries, minimizing Σ HPWL + (max − min HPWL), i.e. a wirelength-variance term. It is pruned by **relative-position constraints derived from global placement** when components are more than k apart.
  - **Benchmarks.** 14 boards (8–64 parts, plus one with 1,570 parts and 947 locked; 1–4 layers), routed with **FreeRouting** and DRC-checked in KiCad.
  - **Runtime.** About 5–10 s for tiny boards, about 1–1.7 h for 34–64-part boards, and a 4 h cap.
  - **Averages in the body text:** routed wirelength −10% vs manual and −6% vs GDMILP; vias −18% and −39%; DRVs + unrouted nets about −80% / −70% / −75% vs manual / MILP / GDMILP; 34% fewer vias on the four largest boards.
  - **Failure case.** PCB2, at about 80% utilization.
  - Sources: [arXiv 2210.14259 (P)](https://arxiv.org/pdf/2210.14259)
- **[PCB] HiePlace** (Li, Zhuang, Liu, Sheng, Yu, Ho; CUHK + Huawei; TCAD Jan 2026; CC BY-NC-ND). **Read in full:**
  - **Problem.** A module is one core chip plus its surrounding components; components get **priorities** (first priority = parts tied to the chip's outermost pins). The objective is weighted wirelength + white-space ratio, with **alignment** (same-size parts aligned, misalignment count "MC") and **few crossings between high-priority nets**.
  - **Flow, step 1: preprocessing.** Irregular outlines are filled with fixed blocks; stacked or irregular parts are sliced into sub-rectangles bound by cohesion constraints.
  - **Step 2: grouping.** Same-size connected small parts are grouped into patterns (1×4, 2×2, …).
  - **Step 3: first-priority placement.** The chip boundary is unrolled to 1-D. A pairwise-swap reorder minimizes crossings, then wirelength, and a **DP 0/1-knapsack** selects which parts go in the first row.
  - **Step 4: relaxation.** Modules become circles (R = α√area), solved with **SLSQP** to get relative module positions.
  - **Step 5: MP legalization.** Uses cardinal up/down/left/right relations to eliminate most Boolean variables; chips and first-priority parts are not rotated.
  - **Step 6: alignment fine-tuning.** Greedy, with a 300 s timeout. Solver is **Gurobi**.
  - **Benchmarks.** 19 boards: 15 industrial (mostly **mobile phones, density ≈0.80**, irregular outlines) and 4 academic built from a public "PCBBenchmarks" repo.
  - **Baselines.** Floorplet (an ILP chiplet floorplanner, which hit its 4 h limit with no feasible solution on PCB11–15), B*-tree SA with manual tweaks, and Quilter on the 4 academic boards.
  - **Results.** Cost −66% and −18% vs the two baselines at **13% of their runtime**; the largest case finishes in under 2 h. Against Floorplet on the first 10 boards: −16% first-priority wirelength and −46% misaligned regions. Against Quilter: cost −76.7% to −91.3%, and seconds vs 34–75 min.
  - **Self-reported limitations.** No double-sided layout, no arbitrary rotation angles, no thermal or mechanical handling, and routability measured only by proxies.
  - **Note.** HiePlace calls Quilter "open-source", which conflicts with Quilter being a commercial product.
  - Sources: [HiePlace PDF (P)](https://www.cse.cuhk.edu.hk/~byu/papers/J156-TCAD2026-HiePlace.pdf)
- **[PCB] Constraint Graph-based PCB Legalization** (Ou, Chen, Chang; DAC'25) is described as the first constraint-graph legalizer for **dense, heterogeneous, irregular-shaped, any-oriented components on double-sided PCBs**. It slices each component into a set of rectangles instead of a bounding box and uses **MILP rather than LP** to widen the solution space. — [abstract (A)](https://doi.org/10.1109/DAC63849.2025.11133304)
- **[PCB]** "Graph-based legalization for PCB placement" (Chen & Deng, J. Phys. Conf. Ser. 2025) builds a constraint graph that preserves placement geometry, then applies adaptive packing and iterative adjustment, reporting 100% legality and fewer ratsnest intersections on industrial samples. — [abstract (A)](https://doi.org/10.1088/1742-6596/3079/1/012071)
- **[PCB]** PCBAgent's MILP post-optimizer baseline (Funke et al.) reached HPWL 2.05x manual and failed spacing legality. — [PCBAgent (P)](https://www.cse.cuhk.edu.hk/~byu/papers/C247-ASPDAC2025-PCBAgent.pdf)
- **[VLSI]** Hard-rectangle floorplanning has been encoded in SMT (Z3). — [arXiv 1709.07241 (S)](https://arxiv.org/pdf/1709.07241)

**Genetic / evolutionary / swarm metaheuristics [PCB, mostly older]**
- Both NS-Place and PCBAgent list GA (Jain & Gea 1996), self-organizing GA (Ismail 2012), GA + Lee routing (Badriyah 2016) and PSO thermal design (Alexandridis 2017) as prior PCB placers. NS-Place says they "suffer from drawbacks — e.g. are computationally expensive, incapable of rotating components, or evaluated on synthetic or toy benchmarks." — [NS-Place (P)](https://arxiv.org/pdf/2210.14259); [PCBAgent (P)](https://www.cse.cuhk.edu.hk/~byu/papers/C247-ASPDAC2025-PCBAgent.pdf)
- PA-ICM shows a hybrid evolutionary (orientation) + subgradient (coordinates) scheme that is fast (seconds) on industrial modules. — [PA-ICM (P)](https://arxiv.org/pdf/2502.14012)

### Inferences
- The 2025–26 PCB literature agrees on what an analytical PCB placer needs on top of DREAMPlace:
  1. rotation as an optimization variable;
  2. side-aware density;
  3. pad-to-pad clearance and pad-type awareness;
  4. a net-crossing or net-separation term;
  5. exact or irregular geometry;
  6. a discrete legalizer (MILP, QP, constraint graph or scanline).

  Cypress is the only one of these placers that is **open-source** and reads KiCad, which makes it the most practical engine to build on (Apache-2.0).
- Hierarchy and MP-based methods (HiePlace) win on dense, highly regular, industry-style boards. Force-directed and analytical methods with anchor and pad-alignment terms (NTU TCAD'25) claim the best routability. No single study compares all of them on a common open benchmark yet; OmniLayout and the Cypress suite could serve as that benchmark.
- KiCad's native autoplacer is a greedy 1 mm-grid ratsnest heuristic and has had **no rotation search since 7.0**. It is useful at most as a seed.

### Gaps
- Full texts of the Cypress ISPD'25 paper, the NTU DAC'25 and TCAD'25 papers, DRLPlace, MARS-Place and the Zhao 2025 paper were not reachable (ACM/IEEE bot walls; Cornell TLS errors). Their algorithmic details here come from abstracts, plus Cypress's source code.
- The public "PCBBenchmarks" repository HiePlace cites (`github.com/aspdac-submission-pcblayout/PCBBenchmarks`) returned 404 at check time.
- No head-to-head CP-SAT vs Gurobi/MILP study for PCB legalization was found.

---

## Q2. Analog IC placement with symmetry, proximity and matching constraints (closest analogue to PCB "keep this cap next to that pin")

### Takeaway
Analog layout flows split constraint handling into **soft penalties during global placement** and **hard equality or ordering constraints in an LP/ILP legalization step**.
- **MAGICAL** (UT Austin) uses an analytical global placer with a symmetry penalty, then constraint-graph LP compaction with exact symmetry equalities, then LP detailed placement.
- **ALIGN** (Minnesota/TAMU/Intel) uses SA over **sequence pairs whose perturbations preserve order and symmetry**, and evaluates each sequence pair with an **ILP** (SYMPHONY or lp_solve) that sets coordinates and flips under symmetry, alignment and ordering constraints. It also offers an electrostatic (ePlace-style) analytical placer.

This penalty-then-exact-legalization split, and ALIGN's JSON constraint vocabulary, are directly reusable for an LLM-authored PCB constraint layer.

### Cited Findings
- **MAGICAL placer.** From the ICCAD'19 paper by Xu, Zhu, Liu, Lin, Li, Tang, Sun and Pan, read in full:
  - **Global placement.** Minimizes **f_WL + a·f_OL + b·f_BND + c·f_SYM** with nonlinear conjugate gradient. HPWL and max/min terms are smoothed with log-sum-exp. f_OL is an area-overlap penalty, f_BND a target-bounding-box penalty for area, whitespace and aspect ratio. f_SYM requires each symmetric pair in a group to mirror about a **shared axis** and self-symmetric devices to sit on that axis. Weights a, b, c rise each iteration until penalties fall below thresholds.
  - **Legalization.** Builds horizontal and vertical **constraint graphs** by plane sweep, greedily keeps one spreading direction per overlapping pair, adds missing edges found by DFS, applies transitive reduction, and solves an **LP compaction** with topology-order plus **symmetry constraints**.
  - **Detailed placement.** An **LP-based detailed placement** for wirelength.
  - **Feasibility rule.** Each device may carry at most **one** symmetry constraint.
  - **Constraint extraction.** A transistor-pattern library plus **signal-flow graph traversal** from seed differential pairs, which then detects bias-circuit symmetry.
  - Net criticality can be specified as net weights.
  - Sources: [MAGICAL ICCAD'19 PDF (P)](https://yibolin.com/publications/papers/ANALOG_ICCAD2019_Xu.pdf); [MAGICAL GitHub (A)](https://github.com/magical-eda/MAGICAL)
- MAGICAL's placer builds on "Device layer-aware analytical placement for analog circuits" (Xu et al., ISPD'19) and "Hierarchical and analytical placement techniques for high-performance analog circuits" (ISPD'17). — [MAGICAL refs (P)](https://yibolin.com/publications/papers/ANALOG_ICCAD2019_Xu.pdf)
- **ALIGN placer.** From the overview paper and the placer source (BSD-3):
  - The paper says the placer "is based on prior work using the sequence pair method" (Ma et al., TCAD 2011, "Simultaneous handling of symmetry, common centroid, and general placement constraints") and handles symmetry, matching and alignment, with hierarchical block assembly and multiple aspect-ratio options per block.
  - **SA.** In code, SA runs over `SeqPair` with defaults T₀=0.5, T_min=0.05, α=0.995 and 10,000 iterations. A source comment notes "PerturbationNew honors order and symmetry."
  - **ILP evaluation.** Each sequence pair becomes coordinates and flips through an **ILP** (`ILP_solver::FrameSolveILPCore`, using SYMPHONY or lp_solve). The objective combines HPWL (linearized with absolute-value constraints, including pin positions under flips) and area, with symmetry-axis, alignment and ordering constraints.
  - **Small designs.** All sequence pairs consistent with ordering constraints are **enumerated** (topological-sort enumerator).
  - **Alternatives.** An optional pure-ILP placer (`use_ILP_placer`, falling back to SA on timeout) and an optional **electrostatic analytical placer** (`EA_placer`: FFT-based e-density force, **Nesterov** iterations, LSE wirelength, a "symmetric force matrix", alignment, ordering and common-centroid support).
  - Sources: [ALIGN overview arXiv 2008.10682 (P)](https://arxiv.org/pdf/2008.10682); [ALIGN placer source (P)](https://github.com/ALIGN-analoglayout/ALIGN-public)
- ALIGN's constraint schema (`align/schema/constraint.py`) defines three kinds of constraint:
  - **Hard:** Order, Align, Spread, AspectRatio, Boundary, SymmetricBlocks, AssignBboxVariables.
  - **User:** AlignInOrder, Floorplan.
  - **Soft:** PlaceCloser, PlaceOnBoundary, CompactPlacement, SameTemplate, PowerPorts/GroundPorts/ClockPorts, DoNotIdentify.

  Constraints come from a per-hierarchy `<name>.const.json` file. — [constraint.py (A)](https://github.com/ALIGN-analoglayout/ALIGN-public/blob/master/align/schema/constraint.py)
- ALIGN extracts hierarchically nested symmetry constraints with graph traversal plus ML, even under approximate matches. It translates electrical constraints into maximum parasitics or wire limits, with an ML inference engine planned inside the placer loop. — [ALIGN overview (P)](https://arxiv.org/pdf/2008.10682)
- **Symmetry islands / ASF-B*-trees** (Lin, Chang, Lin, TCAD 2009) place each symmetry group as one connected island. This was the first method to handle 2D as well as 1D symmetry. Hierarchical HB*-trees co-optimize islands with free modules in linear-time packing. — [TCAD'09 PDF (S)](https://cc.ee.ntu.edu.tw/~ywchang/Papers/tcad09-analog-placement.pdf)
- Follow-ups extend this to matching and hierarchical proximity groups. — [DAC'08 (S)](https://dl.acm.org/doi/pdf/10.1145/1391469.1391484); [US7873928B2 (S)](https://patents.google.com/patent/US7873928B2/en)
- Gao et al. (DAC'21 / TCAD'22) introduced "mixed constraint graphs" for interactive analog layout editing. ModuPlace calls them too imprecise for PCBs, since they constrain only adjacent pairs. — [DAC'21 PDF (S)](https://yibolin.com/publications/papers/ANALOG_DAC2021_Gao.pdf); [ModuPlace (P)](https://yhhan.com/PDFs/ModuPlace_paper.pdf)
- **GNN constraint extraction [Analog IC].** Symmetry annotation from netlists (ASP-DAC'21, Pan co-author) and GAT-based extraction (2023). — [ACM (S)](https://dl.acm.org/doi/10.1145/3394885.3431545); [arXiv 2312.14405 (S)](https://arxiv.org/pdf/2312.14405)
- **Performance-guided analog placement.** A GNN predicts performance to guide the placer (ICCAD'20). — [PDF (S)](http://people.ece.umn.edu/~sachin/conf/iccad20yl.pdf)
- **LLM agents for analog layout.** LayoutCopilot (TCAD 2025). Also "LLM-Enhanced Bayesian Optimization for Efficient Analog Layout Constraint Generation" (Chen, Zhu, Kim, Zhu, Lai, Yu, Pan; arXiv 2406.05250), as cited by the GenAI-PCB survey. — [arXiv 2406.18873 (S)](https://arxiv.org/abs/2406.18873); [survey refs (P)](https://arxiv.org/pdf/2606.17074)

### Inferences
- PCB proximity rules (decap within X mm of a power pin, crystal at the oscillator pins, ESD at the connector) map to ALIGN `PlaceCloser`/`Order`/`Align`/`PlaceOnBoundary`. Symmetric PCB sub-circuits (differential front ends, half-bridge legs, RF chains) map to `SymmetricBlocks`.
- **Recommended handling pattern, from MAGICAL and ALIGN:** express each LLM-authored constraint twice. During global placement it is a **smooth penalty** (with weights the LLM can tune). During legalization it is an **exact linear constraint** (MILP/LP), with infeasibility reported back to the LLM.
- ALIGN's "perturbations that preserve constraints" idea transfers to an SA module floorplanner. Edge anchoring, ordering and symmetry can be guaranteed by construction rather than penalized.

### Gaps
- I did not read Ma et al. 2011 (symmetry-feasible sequence pairs with common centroid) or Xu et al. ISPD'19 in full.
- No PCB paper was found that directly reuses analog symmetry-island or sequence-pair-with-symmetry formulations.

---

## Q3. Machine learning for placement: Google RL and the controversy, MaskPlace, ChiPFormer, EfficientPlace, diffusion, GNN, LLM-evolved heuristics, and PCB-specific ML

### Takeaway
- **VLSI.** Independent reproductions contradict Nature-2021-style claims that end-to-end learned macro placers beat tuned SA or analytical placers; Google disputes the reproductions. The credible recent ML is guidance and refinement: VLM region hints, RL as a refiner, LLM-evolved placer code.
- **Real PCBs.** The best evidence comes from **hybrids**: PCBAgent (RL with masks plus an LLM steering weights) and ModuPlace (an LLM writing a hierarchy and constraint graph for a numeric placer). Pure RL PCB placers (RL_PCB, Crocker, Lim 2026, DRLPlace) are evaluated on small or private sets against weak baselines.
- **Frontier models.** The OmniLayout benchmark (Sept 2026) shows **2026 frontier multimodal LLMs (Claude Sonnet 4.6, GPT-5.5, Gemini 3.1 Pro) still cannot place PCBs directly**, even with tools.

### Cited Findings

**Google RL macro placement and critiques [VLSI]** (other details are left to the verification track)
- Circuit Training/AlphaChip: hundreds of macros (cells clustered by hMETIS); proxy wirelength, congestion and density; placements taped out in TPU-v5 per Google; a pre-trained checkpoint on 20 TPU blocks. — [circuit_training (A)](https://github.com/google-research/circuit_training)
- Proxy cost = 1.0·WL + 1.0·density (top-10% grid cells × 0.5) + 0.5·congestion (top-5% smoothed). — [TILOS ProxyCost (A)](https://github.com/TILOS-AI-Institute/MacroPlacement/tree/main/Docs/ProxyCost)
- Cheng/Kahng et al. (ISPD'23; TCAD update accepted Dec 2025) found SA beat CT in nearly all cases with less compute, CT depends on its initial placement, and proxy cost does not track timing. — [arXiv 2302.11014 (S)](https://arxiv.org/abs/2302.11014v1); [TILOS (A)](https://github.com/TILOS-AI-Institute/MacroPlacement)
- Markov's CACM 2024 meta-analysis says the integrity of the Nature paper is "substantially undermined". — [ACM DL (S)](https://dl.acm.org/doi/10.1145/3676845)
- Goldie, Mirhoseini and Dean's rebuttal ("That Chip Has Sailed") is not peer reviewed. — [arXiv 2411.10053 (S)](https://arxiv.org/pdf/2411.10053)

**RL / offline RL / BBO successors [VLSI]**
- MaskPlace (NeurIPS'22): PPO over **position, wire and view masks**. — [GitHub (A)](https://github.com/laiyao1/maskplace)
- ChiPFormer (ICML'23): an offline decision transformer. — [GitHub (A)](https://github.com/laiyao1/chipformer)
- WireMask-BBO (NeurIPS'23): a greedy wire-mask decoder plus RS/BO/EA. — [GitHub (A)](https://github.com/lamda-bbo/WireMask-BBO)
- MaskRegulate (NeurIPS'24): RL that refines DREAMPlace output. — [GitHub (A)](https://github.com/lamda-bbo/macro-regulator)
- On adaptec1 HPWL (×10⁵), EfficientPlace 5.94, ChiPFormer 6.62, MaskPlace 7.62. — [arXiv 2609.34452 (S)](https://arxiv.org/html/2609.34452)

**Generative and LLM/VLM placement [VLSI]**
- Chip diffusion (Lee et al., ICML'25): trained on synthetic data, places all components at once, guided sampling with `hpwl_guidance_weight` and `legality_potential_target`. — [chipdiffusion GitHub (A)](https://github.com/vint-1/chipdiffusion); [arXiv 2407.12282 (S)](https://arxiv.org/abs/2407.12282v3)
- EvoPlace (Yao, …, Lin, Yu; TCAD 2026): LLMs evolve the placer's optimization code; the evolved initialization gives most of the gain. — [arXiv 2504.17801 (S)](https://arxiv.org/pdf/2504.17801)
- VeoPlace (Google DeepMind, 2026): a VLM proposes sub-regions, which become soft anchors for DREAMPlace or action masks for RL. — [arXiv 2603.28733 (S)](https://arxiv.org/html/2603.28733v1)
- Also seen (abstracts only): CoEvoP&R, OrderPlace, PlaceReasoner-Beta, MacroAgent. — [CoEvoP&R (S)](https://arxiv.org/pdf/2607.17398); [OrderPlace (S)](https://arxiv.org/pdf/2606.08904); [PlaceReasoner-Beta (S)](https://arxiv.org/pdf/2609.21263); [MacroAgent (S)](https://arxiv.org/pdf/2608.24946)

**PCB-specific ML placement [PCB]**
- **RL_PCB** (Vassallo & Bajada, DATE'24): each component is an agent; TD3/SAC; reward from HPWL, Euclidean wirelength and overlap; trained on 6 circuits; A* routing evaluation vs SA; parses KiCad; MIT license. — [RL_PCB GitHub (A)](https://github.com/LukeVassallo/RL_PCB); [IEEE (S)](https://ieeexplore.ieee.org/document/10546526)
- A search summary reports 17% and 21% lower post-routing wirelength than SA on unseen circuits. — [UM repository (S)](https://www.um.edu.mt/library/oar/handle/123456789/131782)
- The thesis summary reports up to 21% better than SA on three unseen circuits. — [MSc summary (S)](https://www.lukevassallo.com/wp-content/uploads/2024/01/MSc_thesis_summary_lv.pdf)
- **Lim 2026** (A*STAR IME, "Component Centric Placement Using Deep RL"; 4-page preprint). **Read in full:**
  - **Discretization.** The main IC is fixed at the centre and passives choose among **N discrete candidate slots around its border** (20–48 actions).
  - **State.** A one-hot token of passive ID concatenated with net ID ("DQNnet").
  - **Reward.** α·non-overlap + (1−α)·net-proximity. Proximity is relaxed with a **Top-K** set of slots near the correct power pin.
  - **Methods.** DQN, A2C and SA.
  - **Metric.** Total Euclidean wirelength (TEWL), argued to correlate better with routed length than HPWL.
  - **Data.** 9 in-house sub-circuits (8–24 passives, 4–14 nets) extracted from larger boards. U20 was originally double-sided but forced single-sided.
  - **Results.** A2C was generally best and DQNnet improved TEWL over DQN. Most methods beat human TEWL except on the two hardest cases, **but still produced overlaps and routing conflicts**: across boards, SA had 14 overlapping passives and 22 routing conflicts, DQN 12/13, A2C 4/16, DQNnet 6/16.
  - **Not covered.** Rotation, routing, two-sided evaluation.
  - Sources: [arXiv 2602.23540 (P)](https://arxiv.org/abs/2602.23540)
- **DRLPlace** (Cai, Cheng, Zhang, Li, Ye; Hubei Univ. of Technology; ASP-DAC'26):
  - PPO with **per-step reward prediction**.
  - A **pre-trained ResNet policy-value model** over layout, net and density-map features (to cope with few samples).
  - **Chip-centric clustering** initialization.
  - **Boundary-aware push-and-reflection legalization** for irregular outlines.
  - Reports up to 16% lower HPWL than manual designs.
  - Sources: [abstract via S2/OpenAlex (A)](https://doi.org/10.1109/ASP-DAC66049.2026.11420655)
- Crocker (MIT MEng 2021): no overlaps or crossings, routing-based metrics, curriculum reward. — [MIT DSpace (S)](https://dspace.mit.edu/handle/1721.1/139247)
- **PCBAgent** (ASP-DAC'25). Read in full:
  - Decision-transformer RL with view, position and wire masks for each of **4 rotations**; boundary and spacing masks enforce legality.
  - **Chip-centred placement order**: ICs first, pads walked clockwise.
  - A **Surface Layer Wire** metric.
  - An LLM agent maps user language to reweighting and incremental re-optimization.
  - 17 industrial boards (18–414 parts): legal on all 17, HPWL 1.04x and NSLW 0.94x of manual, vs MaskPlace 1.13x, ChiPFormer 1.33x and MILP 2.05x. LLM rounds gave +39.6% NSLW.
  - Sources: [PCBAgent PDF (P)](https://www.cse.cuhk.edu.hk/~byu/papers/C247-ASPDAC2025-PCBAgent.pdf)
- **ModuPlace** (DAC'26). Read in full:
  - An LLM builds a **Hierarchical Modular Tree**; a fine-tuned Qwen-2.5-7B (SFT on 426 expert graphs, then GRPO with a GNN preference reward) writes **Comprehensive Constraint Graphs** (relative x/y, rotation offset, weight); a numeric hierarchical placer consumes them.
  - 11 boards, routed with PcbRouter and FreeRouting and EM-simulated in ADS.
  - vs SA-PCB / NS-Place: routed wirelength −17.14% / −15.01%, vias −40.51% / −32.02%. Also beats DeepPCB and PCBAgent.
  - Ablation: removing the hierarchy hurts most.
  - **GPT-4o and Claude-3.5-Sonnet generating constraint graphs zero-shot did substantially worse** than the fine-tuned 7B model.
  - Sources: [ModuPlace PDF (P)](https://yhhan.com/PDFs/ModuPlace_paper.pdf)
- **LLM as a decision layer for PCB placement refinement** (Xu, Chen, Chen, Li, Li; CAICE 2026). After engineering changes (package updates, part substitutions), detected conflicts are characterized by geometric severity, local congestion, component category and violation type. The LLM sets conflict priority and chooses a repair strategy, while classical heuristics do the geometry. It reports about 15% better overall conflict resolution and more than 20% better high-priority resolution. — [abstract (A)](https://doi.org/10.1145/3804601.3804665)
- **OmniLayout** (Lu, …, Gowda; Penn State/SJTU/MSR; arXiv 2607.03261 v3, Sept 2026). **Read in full:**
  - **Data.** 1,681 schematic-coupled layouts from **EAGLE XML DIY/open-source designs**: 2–8 layers, 31.5–22,459 mm², 77.24K placement instances. Code and data are **CC-BY-4.0**.
  - **Models tested.** Claude-Sonnet-4.6, GPT-5.5, GPT-5-mini, Gemini-3.1-Pro-Preview, Gemini-2.5-Flash-Lite, LLaMA-4-Maverick, Ministral-14B and Qwen 3.5/3.6, in **zero-shot** and **agentic** settings. The agentic tools are layout visualization, overlap checking and FreeRouting-based routability scoring, with up to 50 turns.
  - **Baselines.** Quilter, SA-PCB, NS-Place, Cypress and others.
  - **Findings.**
    - Models do reasonably on simple boards (under about 40 components) but degrade with density.
    - They place **about 80% of components on the top layer**.
    - They show weak routability awareness and only partial preservation of schematic relationships.
    - Every model in the headline figure produced more than 5 overlap violations.
    - Tools improve legality but are not applied reliably.
  - Sources: [OmniLayout PDF (P)](https://arxiv.org/abs/2607.03261)
- **Commercial [vendor claims only]:**
  - DeepPCB (RL; TPU training 15–235x throughput). — [DeepPCB blog (S)](https://deeppcb.ai/ai-powered-pcb-placement-by-deeppcb/)
  - Cadence Allegro X AI (claims more than 10x faster turnaround). — [press release (S)](https://www.cadence.com/en_US/home/company/newsroom/press-releases/pr/2023/cadence-introduces-allegro-x-ai-accelerating-pcb-design-with.html)
  - Quilter (RL with physics checks). — [Quilter guide (S)](https://www.quilter.ai/blog/the-2026-guide-to-autonomous-pcb-design-quilter-vs-deeppcb-vs-flux-ai)
  - In HiePlace's independent test on 4 academic boards, Quilter took 34–75 min and had a 4–11x higher cost. — [HiePlace (P)](https://www.cse.cuhk.edu.hk/~byu/papers/J156-TCAD2026-HiePlace.pdf)
  - In ModuPlace's test, DeepPCB's routed wirelength was 17.22% higher than ModuPlace's. — [ModuPlace (P)](https://yhhan.com/PDFs/ModuPlace_paper.pdf)
  - A Cadence patent describes a neural network as a learned routability fitness. — [US 12223248 (S)](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/12223248)

### Inferences
- On PCBs, learned components help most where they **order, partition, mask or prioritize** (PCBAgent's sequence and masks, ModuPlace's hierarchy, DRLPlace's chip-centric init, the conflict-prioritization LLM). Exact geometry is consistently left to classical solvers.
- OmniLayout is the strongest current evidence against having an LLM emit coordinates. Even 2026 frontier models with checking tools fail at dense legal placement. The LLM should stay at the level of hierarchy, constraints, priorities and strategy.

### Gaps
- Not readable in full: EfficientPlace, DRLPlace, RL_PCB DATE'24, and the Cypress paper (code only).
- OmniLayout's per-model numeric tables did not extract cleanly from the PDF. Only qualitative findings are reported here.

---

## Q4. PCB-specific placement literature: routability, thermal, EMC, double-sided, hierarchy grouping, mechanical constraints, and benchmarks/datasets

### Takeaway
Since 2022 PCB placement has become an active subfield, centred on four groups:
- **UCSD** (Cheng/Holtz): SA-PCB, NS-Place, PcbRouter.
- **CUHK/HKUST/Huawei** (Bei Yu, Tsung-Yi Ho): HiePlace, PCBAgent, ModuPlace, PCB-Migrator.
- **NTU** (Yao-Wen Chang): four 2025 DAC/TCAD papers.
- **NVIDIA/Cornell**: Cypress.

There are smaller Chinese groups too (WHUT PA-ICM, Zhao/Liu analytical, Hubei DRLPlace, Fuzhou subgraph reuse). Routability is now judged **after routing** with FreeRouting or PcbRouter. **Two-sided placement** handling has improved but sides are still mostly fixed inputs, not optimized. Thermal-aware and EMC-aware placement remain separate, older, mostly metaheuristic literatures, plus power-electronics loop-inductance layout tools. Open benchmarks now exist: Cypress's suite (10 KiCad and 20 Bookshelf boards) and OmniLayout (1,681 EAGLE boards, CC-BY-4.0).

### Cited Findings

**Routability-oriented [PCB]**
- NS-Place: margin-based net separation over pin convex hulls, MILP legalization, FreeRouting evaluation (details in Q1). — [arXiv 2210.14259 (P)](https://arxiv.org/pdf/2210.14259)
- Cypress: differentiable side-aware net-crossing cost, RUDY-guided inflation, RMST wirelength; reports routability (fraction routed) and routed track length. — [Cypress code (P)](https://github.com/NVlabs/Cypress); [abstract (A)](https://dl.acm.org/doi/10.1145/3698364.3705346)
- NTU DAC'25: a wire-area model separating power-net and signal-net routing resources, plus pad-to-pad clearance. — [abstract (A)](https://doi.org/10.1109/dac63849.2025.11133056)
- NTU TCAD'25: pad alignment to reduce crossings; reports +13.5% routability vs ePlace-MS. — [abstract (A)](https://doi.org/10.1109/tcad.2025.3618936)
- PCBAgent's Surface Layer Wire count; ModuPlace's net crossings with routed wirelength, vias and EM metrics; HiePlace's high-priority net crossings plus alignment. — [PCBAgent (P)](https://www.cse.cuhk.edu.hk/~byu/papers/C247-ASPDAC2025-PCBAgent.pdf); [ModuPlace (P)](https://yhhan.com/PDFs/ModuPlace_paper.pdf); [HiePlace (P)](https://www.cse.cuhk.edu.hk/~byu/papers/J156-TCAD2026-HiePlace.pdf)

**PCB vs IC differences, as stated by PCB papers [PCB]**
- PCBAgent lists density up to 76%, irregular boundaries and spacing, surface-layer wires, rotation, and sequence sensitivity. — [PCBAgent (P)](https://www.cse.cuhk.edu.hk/~byu/papers/C247-ASPDAC2025-PCBAgent.pdf)
- HiePlace makes three further points:
  - VLSI puts macros at the boundary, while **good PCB practice puts the large core chip in the centre** with related parts around it;
  - PCBs need pairwise spacing tables;
  - industrial outlines are irregular and **some parts overlap symmetrically (stacked)**.
  — [HiePlace (P)](https://www.cse.cuhk.edu.hk/~byu/papers/J156-TCAD2026-HiePlace.pdf)
- NS-Place notes arbitrary component shapes, board boundaries, multiple layers and routing constraints. — [NS-Place (P)](https://arxiv.org/pdf/2210.14259)
- ModuPlace notes arbitrary rotation, two sides, irregular shapes, and modular expert practice. — [ModuPlace (P)](https://yhhan.com/PDFs/ModuPlace_paper.pdf)

**Double-sided placement [PCB]**
- **Cypress**: two-sided electrostatic density and per-side legalization, but each part's side comes fixed from its input orientation. — [Cypress code (P)](https://github.com/NVlabs/Cypress)
- **NTU DAC'25**: a "two-sided, pad-type-aware density model" (it distinguishes through-hole from SMD pads, which matter on both sides), and a double-sided MILP constraint-graph legalizer for any-oriented irregular parts. — [Clearance-constrained (A)](https://doi.org/10.1109/dac63849.2025.11133056); [CG legalization (A)](https://doi.org/10.1109/DAC63849.2025.11133304)
- **PA-ICM**: top layer has the IC with accessories around it; bottom layer has pin-oriented placement **within the IC outline** (i.e., bottom-side passives under the IC, such as decaps), clustered by DBSCAN on IC pins. Sides are given per component; "close-to-pin" nets have priority. — [arXiv 2502.14012 (P)](https://arxiv.org/pdf/2502.14012)
- **HiePlace**: lists double-sided layout as future work ("treat the PCB as two interconnected planes … additional weights for interlayer connection costs … minimizing vias"). — [HiePlace (P)](https://www.cse.cuhk.edu.hk/~byu/papers/J156-TCAD2026-HiePlace.pdf)
- **Lim 2026**: forced a double-sided board to a single side. — [arXiv 2602.23540 (P)](https://arxiv.org/abs/2602.23540)
- **OmniLayout**: LLMs leave about 80% of parts on the top side. — [OmniLayout (P)](https://arxiv.org/abs/2607.03261)
- **KiCad autoplacer**: keeps each footprint's side and checks the opposite side only for through-hole pads. — [ar_autoplacer.cpp (P)](https://github.com/KiCad/kicad-source-mirror/blob/master/pcbnew/autorouter/ar_autoplacer.cpp)
- **Patents**: older two-sided raw-then-refined placement. — [US 5481474 (S)](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/5481474)

**Thermal-aware [PCB and transferable]**
- Older PCB work: a GA minimizing peak temperature plus wirelength with a thermal-resistance network (IEICE ELEX 2020); CLPSO with a 3D thermal model; NN surrogates for junction temperature (skipping evaluation when parts overlap); ant colony optimization; SOGA. — [J-STAGE (S)](https://www.jstage.jst.go.jp/article/elex/17/3/17_17.20190737/_article); [ResearchGate CLPSO (S)](https://www.researchgate.net/publication/224107144_Thermal_optimization_formulation_strategies_for_multi-constraints_electronic_devices_placement_on_PCB); [ResearchGate NN (S)](https://www.researchgate.net/publication/3426137_Multidisciplinary_Placement_Optimization_of_Heat_Generating_Electronic_Components_on_a_Printed_Circuit_Board_in_an_Enclosure); [ResearchGate ACO (S)](https://www.researchgate.net/publication/326710377_Thermal_optimization_of_electronic_devices_on_PCB_based_on_the_ant_colony_algorithm)
- **TRouter** (Chen, Xiong, He, Yu; TCAD 2023) is a **thermal-driven PCB router**. A crisscross-attention network predicts the board's thermal map from pads, vias, components and wires, and **per-grid gradients from backpropagation guide detours and via punching**. This shows a differentiable thermal surrogate inside a PCB physical-design loop, and the same idea transfers to a placement density or penalty term. — [S2 abstract (A)](https://doi.org/10.1109/TCAD.2023.3243544)
- **HSL-TFP benchmark** (Chen et al., arXiv 2103.11177) is a DNN surrogate benchmark for temperature-field prediction from heat-source layouts. It is motivated by the cost of thermal simulation inside layout optimization; PCB design is cited as a motivating application by a secondary summary. — [arXiv 2103.11177 (P, abstract and intro)](https://arxiv.org/pdf/2103.11177)
- **Surrogate-assisted SA for thermal chiplet placement** (Zhang, Liang, Xu, Chen; the same WHUT group as PA-ICM; IEEE JETCAS 2025): an RBF network approximates the thermal field inside SA that minimizes wirelength plus maximum temperature. [Chiplet, transferable.] — [arXiv 2504.03808 (P, abstract and intro)](https://arxiv.org/pdf/2504.03808)
- HiePlace lists thermal considerations as future work. — [HiePlace (P)](https://www.cse.cuhk.edu.hk/~byu/papers/J156-TCAD2026-HiePlace.pdf)

**EMC / SI / power-loop-aware [PCB]**
- **ModuPlace** is the only placement paper found that measures EM performance after routing (Keysight ADS insertion loss and crosstalk). It attributes part of the gain to modular grouping by frequency and power domain. — [ModuPlace (P)](https://yhhan.com/PDFs/ModuPlace_paper.pdf)
- **Power-electronics layout automation** is the main algorithmic EMC-placement literature:
  - GA-based automatic PCB layout of a DC-DC converter under EMC constraints, with parasitics extracted by ANSYS Q3D in the loop. — [ResearchGate (S)](https://www.researchgate.net/publication/355865177_Automatic_PCB_Layout_Optimization_of_a_DC-DC_Converter_Through_Genetic_Algorithm_Regarding_EMC_Constraints)
  - A graph-model generative layout for SiC multichip modules, with a GA Pareto front of loop inductance vs branch mismatch, validated on a 1200 V/240 A half-bridge. — [ResearchGate (S)](https://www.researchgate.net/publication/359124822_Graph-Model-Based_Generative_Layout_Optimization_for_Heterogeneous_SiC_Multichip_Power_Modules_With_Reduced_and_Balanced_Parasitic_Inductance)
  - PowerSynth-based placement for high-density DC-DC converters (inductance vs junction temperature). — [ResearchGate (S)](https://www.researchgate.net/publication/388859171_Physical_Layout_Design_Automation_for_High-Power_Density_DC-DC_Converter)
  - A hierarchical-RL thesis that keeps critical current loops small. — [ResearchGate (S)](https://www.researchgate.net/publication/375759135_Design_Automation_of_PCB_Layout_for_Power_Electronics_with_Reinforcement_Learning)
  - GaN work names the gate loop and power loop as the two critical loops to minimize. — [DTU PDF (S)](https://backend.orbit.dtu.dk/ws/portalfiles/portal/236953218/IAS_accepted_PCB_for_GaN_2020.pdf)
- **NTU TCAD'25** extracts **anchor points from power-circuit flows** to guide force-directed placement, which is a structural way to keep power paths compact. — [abstract (A)](https://doi.org/10.1109/tcad.2025.3618936)
- **Rule-level guidance only:** partition by function and EM characteristics, put crystals next to their loads, put connectors at the edge. These are written guidelines, not algorithms. — [Altium (S)](https://resources.altium.com/p/component-placement-for-emc)
- **Quilter's check list** covers bypass-cap distance, via-in-loop, converter coil proximity and crystal placement. — [Quilter guide (S)](https://www.quilter.ai/blog/the-2026-guide-to-autonomous-pcb-design-quilter-vs-deeppcb-vs-flux-ai)

**Mechanical, fixed parts, reuse [PCB]**
- KiCad's documented workflow locks connectors and critical parts before autoplacing. — [kicad-doc (P)](https://github.com/KiCad/kicad-doc/blob/master/src/pcbnew/pcbnew_footprint_placement.adoc)
- Benchmarks include fixed parts: NS-Place 1–947 locked, ModuPlace 1–6 fixed, HiePlace preplaced parts and obstacles. — [NS-Place (P)](https://arxiv.org/pdf/2210.14259); [ModuPlace (P)](https://yhhan.com/PDFs/ModuPlace_paper.pdf); [HiePlace (P)](https://www.cse.cuhk.edu.hk/~byu/papers/J156-TCAD2026-HiePlace.pdf)
- **Reference / reuse placement.** "Subgraph Matching Based Reference Placement for PCB Designs" (Su et al., DAC'22; journal version in J. Supercomputing 2024) finds placed templates in new netlists with the D2BS inexact subgraph-matching algorithm (100% accuracy on PCB instances, faster than VF3). — [DAC'22 abstract (A)](https://doi.org/10.1145/3489517.3530670); [J. Supercomput. (A)](https://doi.org/10.1007/s11227-024-06338-9)
- **PCB-Migrator** (Han et al., DATE'26) maps a reference layout onto a changed board using an **offset constraint graph** and routing-path graph matching. — [S2 abstract (A)](https://doi.org/10.23919/DATE69613.2026.11539307)

**PCB routers used for evaluation**
- FreeRouting is used by NS-Place, ModuPlace and OmniLayout; PcbRouter by ModuPlace. — [NS-Place (P)](https://arxiv.org/pdf/2210.14259); [ModuPlace (P)](https://yhhan.com/PDFs/ModuPlace_paper.pdf); [OmniLayout (P)](https://arxiv.org/abs/2607.03261); [PcbRouter (A)](https://github.com/The-OpenROAD-Project/PcbRouter)

**Benchmarks and datasets**

| Dataset | Boards | Format / access | Notes |
|---|---|---|---|
| NS-Place | 14 | Not stated as released | 8–64 parts plus one 1,570-part board; 1–4 layers; utilization 0.10–0.79 |
| PCBAgent | 17 industrial tasks | Not released | 18–414 parts |
| HiePlace | 19 | 15 industrial phone boards (density ≈0.8) + 4 academic from a now-404 public repo | |
| ModuPlace | 11 | OpenROAD + industry | |
| Cypress | 10 KiCad + 20 Bookshelf | Released in repo, Apache-2.0 | "Synthesized from real commercial designs" |
| OmniLayout | 1,681 | EAGLE, CC-BY-4.0 | 2–8 layers; DIY/open-source origin |
| PCBWorld | 679 open-source boards + generators | `.kicad_pcb` | Routing environment, reusable for placement |

Sources: [NS-Place (P)](https://arxiv.org/pdf/2210.14259); [PCBAgent (P)](https://www.cse.cuhk.edu.hk/~byu/papers/C247-ASPDAC2025-PCBAgent.pdf); [HiePlace (P)](https://www.cse.cuhk.edu.hk/~byu/papers/J156-TCAD2026-HiePlace.pdf); [ModuPlace (P)](https://yhhan.com/PDFs/ModuPlace_paper.pdf); [Cypress repo (P)](https://github.com/NVlabs/Cypress); [OmniLayout (P)](https://arxiv.org/abs/2607.03261); [PCBWorld (S)](https://arxiv.org/html/2607.05915)

- OmniLayout's own comparison table lists Cypress as 10 layouts (2.6K components) against its 1,681. It also notes that most PCB placement works use private sets of only 10–20 boards. — [OmniLayout (P)](https://arxiv.org/abs/2607.03261)
- NVIDIA's ISPD'24 invited talk "Challenges for Automating PCB Layout" (Liu, Agnesina, Ren) is a tutorial on how PCB design is done today and where automation opportunities lie. — [ACM abstract (A)](https://doi.org/10.1145/3626184.3635285)

### Inferences
- Evaluation norms are converging: (a) route with FreeRouting; (b) report routability (fraction of nets routed), routed length, vias and DRVs; (c) report crossings and alignment proxies. A KiCad system can adopt exactly this and compare against SA-PCB, NS-Place and Cypress on the Cypress KiCad boards and an OmniLayout subset.
- **Side assignment is an open problem.** Every academic placer found here takes component sides as input. An LLM is well placed to decide sides from design intent (decaps under BGAs, tall or THT parts on top), with the numeric placer then handling each side.
- **Thermal and EMC placement have no maintained open tool.** The most transferable designs are a differentiable thermal surrogate (TRouter-style) as a penalty term, and power-loop anchoring (NTU) or loop-area penalties.

### Gaps
- No general-purpose **EMC-aware placement algorithm** with a coupling or loop-area objective was found for mixed-signal boards. The only automated loop-inductance work found is for power-converter and power-module layout.
- The web-search budget ran out before more recent (2024–26) **thermal-aware PCB placement** papers could be found. The thermal items above are older PCB work, or chiplet and routing analogues.
- OpenAlex's anonymous budget was also exhausted. Citation-following used Semantic Scholar only, so DAC'25/26, ICCAD'25 and ISEDA'25 PCB papers without a Semantic Scholar link may be missing.

---

## Q5. Hierarchical / cluster-based approaches: placing functional blocks as macros, then refining inside

### Takeaway
Every strong PCB placer since 2024 has a cluster or module level. On PCBs the module is almost always **"core IC + its satellites"** (HiePlace, PA-ICM, PCBAgent, Lim 2026, DRLPlace) or an **LLM-derived functional module** (ModuPlace, Trace). The common recipe:
1. place the IC centrally;
2. arrange first-priority satellites around its pins (ordered to avoid crossings);
3. pack the remaining parts into module regions;
4. place modules relative to each other (relaxation or SA);
5. legalize exactly.

### Cited Findings
- **HiePlace hierarchy:**
  - Modules (chip + surrounding parts) are relaxed to circles of radius α√area and placed with SLSQP.
  - Inside each module, the chip and first-priority parts keep fixed relative positions. The **first ring is chosen by DP knapsack along the unrolled chip boundary**, after crossing-minimizing reordering, and the remaining parts are confined to a module rectangle solved by MP.
  - Same-size connected small parts are pre-grouped into patterns.
  - If MP is infeasible, it backtracks: groups are relaxed and chip movement is enlarged.
  - Sources: [HiePlace (P)](https://www.cse.cuhk.edu.hk/~byu/papers/J156-TCAD2026-HiePlace.pdf)
- **PA-ICM:** the top layer is a centralized layout around the IC, initialized by attaching each passive to its nearest IC pin and pushing it outside the IC. The bottom layer uses DBSCAN clusters of IC pins, optimized independently with cluster-size-adaptive overlap weights. — [PA-ICM (P)](https://arxiv.org/pdf/2502.14012)
- **PCBAgent:** chip-centred ordering cut HPWL by 30% and 22% vs net-count and area orderings. — [PCBAgent (P)](https://www.cse.cuhk.edu.hk/~byu/papers/C247-ASPDAC2025-PCBAgent.pdf)
- **Lim 2026:** a fixed main IC with discrete slots around it, and the passive-near-power-pin prior baked into the reward. — [Lim (P)](https://arxiv.org/abs/2602.23540)
- **DRLPlace:** chip-centric clustering initialization. — [abstract (A)](https://doi.org/10.1109/ASP-DAC66049.2026.11420655)
- **ModuPlace:** an LLM-built Hierarchical Modular Tree, placed layer by layer under constraint-graph guidance. Removing the hierarchy hurt the most. — [ModuPlace (P)](https://yhhan.com/PDFs/ModuPlace_paper.pdf)
- **NTU TCAD'25:** anchor points from power-circuit flows. — [abstract (A)](https://doi.org/10.1109/tcad.2025.3618936)
- **Hier-RTLMP (VLSI):** a multilevel cluster tree with weighted SA. **ALIGN (analog):** hierarchical block assembly with multiple shape options per block. — [OpenROAD mpl (A)](https://github.com/The-OpenROAD-Project/OpenROAD/tree/master/src/mpl); [ALIGN (P)](https://arxiv.org/pdf/2008.10682)
- **Reuse as hierarchy:** subgraph-matched templates (D2BS) and PCB-Migrator's offset constraint graphs reuse proven sub-layouts as fixed modules. — [DAC'22 (A)](https://doi.org/10.1145/3489517.3530670); [PCB-Migrator (A)](https://doi.org/10.23919/DATE69613.2026.11539307)

### Inferences
- For KiCad, hierarchy usually comes from three places:
  - schematic sheets;
  - "IC + passives on its pins" clusters, which can be computed from the netlist;
  - a library of proven sub-layouts (datasheet reference layouts, or the user's own past boards), reused through subgraph matching.

  An LLM can name and refine these modules, and decide module sides, regions and adjacency.
- HiePlace's DP-knapsack "ring around the chip" step is a cheap, explainable way to place decoupling and support parts. An LLM can set its priorities, for example "VDDCORE decaps first".

### Gaps
- No PCB study compares module-area estimation methods (circles in HiePlace, bounding-box joint optimization in ModuPlace) or measures their sensitivity.

---

## Q6. Which methods produce explainable intermediate representations an LLM could reason about or steer?

### Takeaway
The most steerable representations are:
- **(a) weighted multi-term costs:** Hier-RTLMP, SA-PCB, Trace, PCBAgent score weights, PA-ICM α/β/γ, Cypress parameters plus its BOHB tuner;
- **(b) declarative constraints:** ALIGN JSON, MAGICAL symmetry groups, HiePlace priorities, spacing tables and alignment, PA-ICM "close-to-pin" nets;
- **(c) hierarchy and relative-position graphs:** ModuPlace's modular tree and constraint graphs, PCB-Migrator's offset constraint graphs, NS-Place's relative-position constraints;
- **(d) region anchors and fences:** VeoPlace, DREAMPlace fences, Hier-RTLMP guidance, NTU power-flow anchors;
- **(e) placement orders and seeds:** PCBAgent chip-centred order, HiePlace crossing-minimizing order, NS-Place spectral seeds, EvoPlace evolved initialization;
- **(f) raster masks a VLM can read:** MaskPlace/PCBAgent position and wire masks, Cypress RUDY maps;
- **(g) conflict lists with features:** the LLM conflict-prioritization paper.

End-to-end neural placers (CT, ChiPFormer, diffusion, DRLPlace) are the least explainable.

### Cited Findings
- **PCBAgent:** the LLM reweights the score and re-optimizes only violating components. — [PCBAgent (P)](https://www.cse.cuhk.edu.hk/~byu/papers/C247-ASPDAC2025-PCBAgent.pdf)
- **ModuPlace:** constraint-graph edges carry (x̂, ŷ, θ̂, w). Directly generating placement files "may lead to severe hallucination problems." — [ModuPlace (P)](https://yhhan.com/PDFs/ModuPlace_paper.pdf)
- **OmniLayout:** even with visualization, overlap-checking and routability tools, 2026 LMMs fail at dense legal placement, which argues against coordinate-level LLM output. — [OmniLayout (P)](https://arxiv.org/abs/2607.03261)
- **LLM conflict prioritization:** the LLM chooses priority and repair strategy from a conflict feature vector (severity, congestion, category, violation type), and heuristics do the geometry. — [abstract (A)](https://doi.org/10.1145/3804601.3804665)
- **MAGICAL:** soft symmetry penalty with rising weight, then exact symmetry in LP legalization. **ALIGN:** constraint-preserving sequence-pair moves plus ILP. — [MAGICAL (P)](https://yibolin.com/publications/papers/ANALOG_ICCAD2019_Xu.pdf); [ALIGN source (P)](https://github.com/ALIGN-analoglayout/ALIGN-public)
- **NS-Place:** relative positions from global placement become explicit MILP constraints that preserve global structure. **PCB-Migrator:** an offset constraint graph extracted from a reference design. — [NS-Place (P)](https://arxiv.org/pdf/2210.14259); [PCB-Migrator (A)](https://doi.org/10.23919/DATE69613.2026.11539307)
- **Cypress:** a single JSON config of weights and flags (net-crossing weight, density weight, RUDY adjustment, rotation enable) plus a BOHB tuner, i.e. a ready-made "knob surface" for an LLM. — [Cypress code (P)](https://github.com/NVlabs/Cypress)
- **HiePlace:** priority classes, spacing tables, an alignment metric and grouping patterns (1×4, 2×2) are all human-readable. — [HiePlace (P)](https://www.cse.cuhk.edu.hk/~byu/papers/J156-TCAD2026-HiePlace.pdf)
- **VeoPlace:** VLM regions become soft anchors in DREAMPlace. **EvoPlace:** an LLM edits placer code. — [VeoPlace (S)](https://arxiv.org/html/2603.28733v1); [EvoPlace (S)](https://arxiv.org/pdf/2504.17801)
- **Hier-RTLMP:** named weights and guidance regions. **ALIGN:** typed JSON constraints. — [OpenROAD mpl (A)](https://github.com/The-OpenROAD-Project/OpenROAD/tree/master/src/mpl); [ALIGN constraint.py (A)](https://github.com/ALIGN-analoglayout/ALIGN-public/blob/master/align/schema/constraint.py)
- A KiCad AI guide warns that API-driven moves do not check courtyards, so DRC should run after every pass. — [pcbeditor.com (S)](https://pcbeditor.com/kicad-ai)

### Inferences
- The best-supported loop is: **LLM → hierarchy, constraints, weights, priorities and side assignment → numeric placer → exact legalizer → metrics and conflict list → LLM**. Cypress's config, ALIGN-style constraints and the conflict-feature format give concrete interface designs for each arrow.

### Gaps
- No study measures LLM-authored vs expert-authored PCB constraint sets, beyond ModuPlace's constraint-graph similarity and OmniLayout's relational-preservation metric.

---

## Q7. Evaluation metrics used in placement

### Takeaway
On PCBs, HPWL is necessary but insufficient. Current PCB papers report six kinds of metric:
- **legality:** overlap, out-of-boundary, spacing/clearance;
- **proxies:** HPWL, total Euclidean wirelength, RMST, net crossings, net separation, Surface Layer Wire count, first-priority HPWL, misalignment count, area ratio, RUDY;
- **post-route ground truth:** routability (fraction of nets routed), routed wirelength or track length, vias, DRVs or unrouted nets;
- **EM:** insertion loss and crosstalk;
- **runtime;**
- for LLM benchmarks, **schematic-relation preservation** and **reference similarity**.

### Cited Findings
- **NS-Place:** pre-route HPWL and net-separation cost; post-route FreeRouting wirelength, vias, and DRVs + unrouted nets from KiCad DRC. — [NS-Place (P)](https://arxiv.org/pdf/2210.14259)
- **HiePlace:** HPWL_all, area ratio (sweepline), cost (priority-weighted wirelength), runtime, first-priority HPWL, misalignment count (MC), and crossings between the chip and first-priority parts. — [HiePlace (P)](https://www.cse.cuhk.edu.hk/~byu/papers/J156-TCAD2026-HiePlace.pdf)
- **Cypress:** routability, routed track length, runtime. Its code has HPWL, RMST, net-crossing and RUDY ops. — [abstract (A)](https://dl.acm.org/doi/10.1145/3698364.3705346); [code (P)](https://github.com/NVlabs/Cypress)
- **OmniLayout:** overlap area (OO), out-of-boundary count (OoB), runtime, HPWL, net crossings (NC), net separation (NS), predicted routed wirelength (PRWL), routed ratio (RR), vias, schematic relational distance, and reference similarity; plus agentic constraint satisfaction, step count and refinement quality. — [OmniLayout (P)](https://arxiv.org/abs/2607.03261)
- **Lim 2026:** total Euclidean wirelength (TEWL), argued to correlate better with routed length than HPWL, plus visual counts of overlaps and routing conflicts. — [Lim (P)](https://arxiv.org/abs/2602.23540)
- **PCBAgent:** HPWL, NSLW and a legality triple. **ModuPlace:** HPWL and crossings for training; routed wirelength, vias, IL and XT for evaluation. — [PCBAgent (P)](https://www.cse.cuhk.edu.hk/~byu/papers/C247-ASPDAC2025-PCBAgent.pdf); [ModuPlace (P)](https://yhhan.com/PDFs/ModuPlace_paper.pdf)
- **VLSI:** the CT proxy (normalized HPWL, top-10% density, top-5% congestion) does not reliably track timing. RUDY (Spindler & Johannes 2007) is cited by SA-PCB and NS-Place and used by Trace. — [TILOS ProxyCost (A)](https://github.com/TILOS-AI-Institute/MacroPlacement/tree/main/Docs/ProxyCost); [NS-Place refs (P)](https://arxiv.org/pdf/2210.14259); [Trace (S)](https://docs.buildwithtrace.com/concepts/pcb-layout)
- **Thermal:** peak or junction temperature from thermal networks, FEM, or NN/RBF surrogates. — [arXiv 2504.03808 (P)](https://arxiv.org/pdf/2504.03808); [J-STAGE (S)](https://www.jstage.jst.go.jp/article/elex/17/3/17_17.20190737/_article)

### Inferences
- Recommended KiCad metric stack:
  1. **hard legality:** courtyard overlap, Edge.Cuts and keep-out containment, clearance (KiCad DRC);
  2. **fast proxies:** net-class-weighted HPWL or TEWL, net crossings, RUDY map, SLW-like count, alignment count;
  3. **domain rules:** decap-to-pin distance, crystal distance, switching-loop area, connector at edge, thermal spacing;
  4. **periodic ground truth:** FreeRouting routability, routed length, vias, DRC errors.

### Gaps
- No PCB study validates proxy-to-routed correlation across many boards. OmniLayout's PRWL vs RR data might allow this, but I could not extract its tables.

---

## Q8. Implications for an LLM-driven KiCad placer (concrete suggestions)

### Takeaway
Build a **hybrid, constraint-centric pipeline**. The LLM owns **hierarchy, side assignment, constraints, weights, priorities and conflict strategy**. An open PCB-aware analytical engine owns geometry: Cypress (DREAMPlace-based, Apache-2.0, reads KiCad), extended with NTU-style clearance and pad-type density, or a simpler SA or force-directed engine. An **exact legalizer** (MILP or constraint graph) runs next, then a **FreeRouting-in-the-loop evaluator**. Do not let the LLM emit coordinates (OmniLayout, ModuPlace), and do not start with RL training.

### Cited Findings (evidence underpinning the suggestions)
- **Hierarchy matters most.** It is ModuPlace's largest ablation effect, and every strong 2025 PCB placer is chip- or module-centric. — [ModuPlace (P)](https://yhhan.com/PDFs/ModuPlace_paper.pdf); [HiePlace (P)](https://www.cse.cuhk.edu.hk/~byu/papers/J156-TCAD2026-HiePlace.pdf); [PA-ICM (P)](https://arxiv.org/pdf/2502.14012)
- **LLMs cannot place directly.** 2026 frontier multimodal models fail at dense legal PCB placement even with tools; GPT-4o and Claude-3.5 wrote worse constraint graphs than a fine-tuned 7B model. — [OmniLayout (P)](https://arxiv.org/abs/2607.03261); [ModuPlace (P)](https://yhhan.com/PDFs/ModuPlace_paper.pdf)
- **LLMs work as decision layers.** Steering by reweighting gave +39.6% NSLW (PCBAgent). Conflict prioritization gave +15% conflict resolution. — [PCBAgent (P)](https://www.cse.cuhk.edu.hk/~byu/papers/C247-ASPDAC2025-PCBAgent.pdf); [conflict-prioritization abstract (A)](https://doi.org/10.1145/3804601.3804665)
- **Open engine available.** Cypress offers two-sided density, Gumbel-softmax rotation, net-crossing and RUDY terms, KiCad and NS-Place converters, and a BOHB tuner. The NTU TCAD'25 paper reports beating it by more than 50% in routability using power-flow anchors and pad alignment, which suggests what to add. — [Cypress code (P)](https://github.com/NVlabs/Cypress); [NTU TCAD'25 (A)](https://doi.org/10.1109/tcad.2025.3618936)
- **Legalizer patterns:** MILP with relative-position pruning (NS-Place), cardinal-relation MP (HiePlace), MILP constraint-graph legalization of sliced irregular parts (NTU DAC'25), and LP compaction with symmetry equalities (MAGICAL). — [NS-Place (P)](https://arxiv.org/pdf/2210.14259); [HiePlace (P)](https://www.cse.cuhk.edu.hk/~byu/papers/J156-TCAD2026-HiePlace.pdf); [NTU CG legalization (A)](https://doi.org/10.1109/DAC63849.2025.11133304); [MAGICAL (P)](https://yibolin.com/publications/papers/ANALOG_ICCAD2019_Xu.pdf)
- **Evaluate after routing.** HPWL-only optimization can be unroutable (ModuPlace's critique of PCBAgent). The community evaluates with FreeRouting. — [ModuPlace (P)](https://yhhan.com/PDFs/ModuPlace_paper.pdf); [NS-Place (P)](https://arxiv.org/pdf/2210.14259)
- **KiCad's built-in autoplacer is weak.** It is greedy on a 1 mm grid with no rotation since 7.0. — [ar_autoplacer.cpp (P)](https://github.com/KiCad/kicad-source-mirror/blob/master/pcbnew/autorouter/ar_autoplacer.cpp); [commit d649b288 (P)](https://gitlab.com/kicad/code/kicad/-/commit/d649b288a62aac5c31489bc41ab22149d7339014)
- **Open benchmarks exist** (Cypress KiCad set, OmniLayout CC-BY-4.0). — [Cypress (P)](https://github.com/NVlabs/Cypress); [OmniLayout (P)](https://arxiv.org/abs/2607.03261)

### Inferences (my concrete suggestions)
1. **Use a typed constraint DSL as the LLM's main output,** modelled on ALIGN plus PCB additions:
   - *Hard:* `fixed`, `on_edge(edge, offset)`, `keepout(region, side)`, `side(ref|group)`, `rot_allowed`, `inside(group, region)`, `clearance(class_a, class_b, mm)`.
   - *Soft:* `near(ref, pin, max_mm, w)`, `ring(ic, refs, priority)` (HiePlace-style first ring), `align(refs, axis)`, `order(refs, dir)`, `symmetric(pairs, axis)`, `group(refs, w)`, `spread(heat_refs, min_mm)`, `away_from(ref, region, min_mm)`, `loop_compact(nets)` (power loops).
   - Each soft term is compiled twice, MAGICAL/ALIGN-style: a smooth penalty during global placement, and an exact linear constraint during legalization, with infeasibility reported back.
2. **Make hierarchy the LLM's first job.** Start from KiCad sheets, then compute "IC + pin-satellite" clusters from the netlist, then have the LLM name the modules and assign side preference, region or edge, and adjacency. Use RAG over datasheet layout-guideline sections, and optionally subgraph-match against a library of proven sub-layouts (D2BS-style reuse).
3. **Have the LLM assign sides explicitly.** No academic placer optimizes sides, and LLMs left alone put about 80% of parts on top. Examples: decaps and small passives under BGAs or QFNs on the bottom, tall, THT and user-facing parts on top. Then run two-sided density (Cypress) with PA-ICM-style "bottom pins under the IC" clustering.
4. **Geometric engine, in order of preference:**
   - (a) Fork **Cypress**. Add pad-to-pad clearance, pad-type-aware two-sided density and power-flow anchor terms (from NTU DAC'25 and TCAD'25), and expose its JSON knobs to the LLM.
   - (b) For small boards (under 100 parts) or tight constraints, use an SA module floorplanner over sequence pairs whose moves preserve constraints (ALIGN-style), then in-module placement with a HiePlace-style DP ring plus a small MP or force-directed step.
5. **Legalize exactly with CP-SAT or MILP on sliced footprint rectangles** (NTU DAC'25), using relative-position pruning from global placement (NS-Place) and cardinal module relations (HiePlace) so it scales to a few hundred parts. Report the infeasible constraint subset to the LLM.
6. **Score with a multi-tier report:** KiCad DRC legality; HPWL/TEWL, crossings, RUDY and alignment; domain rules; and periodic FreeRouting routability, length and vias. Emit a **conflict list with features** (severity, congestion, part category, violation type) so the LLM can prioritize and pick repair strategies, as in the 2026 conflict-prioritization paper. Re-optimize incrementally, as PCBAgent does.
7. **Use images selectively.** Render placements with RUDY, thermal and legal-position masks, and let a multimodal LLM propose module regions (VeoPlace-style soft anchors). Never use its output as final coordinates; OmniLayout shows LMMs are weak at fine geometry.
8. **Handle thermal and EMC with explicit, explainable terms.** Use a fast thermal surrogate (RBF or CNN, TRouter- and HSL-TFP-style) as a differentiable penalty or SA cost. For switching converters, add loop-area or anchor terms that keep the hot loop (input cap, switch, diode or inductor) compact, plus `away_from` constraints between aggressors and victims.
9. **Pre-place mechanical anchors** (connectors, holes, switches, LEDs) as fixed or edge constraints, as KiCad's own workflow recommends.
10. **Benchmark before claiming wins.** Run SA-PCB, NS-Place (if the code can be obtained) and Cypress baselines on the Cypress KiCad boards and an OmniLayout subset, using FreeRouting metrics. Use an EvoPlace-style offline loop to let the LLM evolve your placer's initialization and cost heuristics against that benchmark.
11. **Keep it deterministic and explainable.** Fix seeds, log the constraint set, weights and solver versions, and write a per-module "why" listing the binding constraints.
12. **KiCad integration.** Apply results through the IPC API or pcbnew Python as one undo step, respect locked footprints, and run DRC after each pass. Use KiCad's built-in autoplacer only as a seed or fallback (greedy grid, no rotation since 7.0).

### Gaps
- No published system yet combines a frontier LLM, a constraint DSL, a PCB-aware analytical engine and router-in-the-loop on an open benchmark. Expected gains are extrapolated.
- Licensing and reuse of NS-Place code (no public repository found) and of HiePlace (paper is CC BY-NC-ND; no code found) are unresolved. Cypress (Apache-2.0), SA-PCB (BSD-3), DREAMPlace (BSD-3), ALIGN and MAGICAL (BSD-3) and OmniLayout data (CC-BY-4.0) are the reusable assets identified.
- FreeRouting runtimes for in-the-loop evaluation on 300–500-part boards were not measured in any source found.
