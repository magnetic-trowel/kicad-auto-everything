<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Transformations of joint placement and routing

**Question.** Which transforms, dualities or equivalences move part of PCB placement
and routing into a space where another field already has exact results or fast
algorithms, and has nobody applied them here yet?
**Grounding:** [scorecard](../../docs/ideas/original/scorecard.md),
[layer-collapse](../../docs/ideas/original/layer-collapse.md),
[analogs](../layer-collapse/analogs.md) (its findings are not repeated here),
[joint-pnr-experiments](../../docs/topics/placement/joint-pnr-experiments.md),
`tools/research/collapse_joint/jc.py`, and the `kae.physics` place-term sources.

**Tags.** [P] read in a primary source; [S] abstract or secondary source only;
[U] unverified; [I] our own derivation; [N] numerical check run for this note (scripts
kept in the session scratchpad, not committed).

## TL;DR

- Every expensive piece of our objective falls into one of three algebras:
  1. **Sum-product over translations** (legality, thermal, coupling, pour damage). These
     are convolutions, done by FFT or DCT.
  2. **Min-plus over paths** (route cost as a function of a pad's position). These are
     tropical convolutions, done by distance transforms or one Dijkstra run.
  3. **Elliptic energies** (pour resistance, return current, temperature). Here the
     variational principles (Dirichlet, Thomson) turn one solve into a sensitivity map
     for every position at once.
  Our engine uses (1) only for legality, and uses none of the three for physics or
  route cost.
- **Strongest transforms, in our judgment:**
  - **(T1) min-plus best-response maps:** jc's HPWL and L1 tension map replaced by
    geodesic route-cost fields on the β-priced grid;
  - **(T2) Green's-function physics maps** at full resolution, replacing `coarse_map`'s
    1.2 mm sampling. The thermal term is exactly a DCT solve [N];
  - **(T3) routed coupling as an additive A\* edge cost** through the aggressors' vector
    potential;
  - **(T4) Dirichlet-principle pour-damage maps** [N: Spearman 0.97 against exact
    re-solves].
- **Our checks refuted or demoted several of the suggested examples:**
  - Braid words, knots, Noether symmetry, Koopman operators and gauge views add nothing
    over what [analogs](../layer-collapse/analogs.md) already found.
  - Extremal-length bounds on pour resistance are exact on rectangles but 2–200× loose
    on slotted or perforated pours [N].
  - A DCT-preconditioned CG solver on a masked pour stalled [N].
  - jc's β-continuation is an exterior-penalty path, not a tropical (temperature) limit.

## 1. The problem, reduced to its bases

- **State:**
  - Part poses q_k ∈ R² × D₄ (side fixed; D₄ = 4 rotations, ×2 mirror when the side
    flips).
  - Per net i, copper C_i ⊂ Ω × {1..L}, connected through vias, each joining its
    terminals T_i(q).
- **Constraints:**
  - local exclusion: Minkowski-dilated sets disjoint per layer and side;
  - global connectivity: H₀ of each net's copper is one component, so each net forms a
    single connected piece.
- **Objective:**
  - routed length, vias, and physics functionals;
  - almost all physics functionals are quadratic forms ⟨J, G J⟩ of a current or charge
    distribution with a Green's function G of an elliptic operator:
    - magnetostatic: partial inductance with ground-plane images;
    - electrostatic: patch capacitance;
    - thermal: the fin equation (∇² − λ⁻²)T = −q/G_s with adiabatic edges;
    - resistive: pour conductance.
- **Three structural facts drive every transform below:**
  1. The board is (nearly) **translation-invariant** in-plane: Green's functions depend
     on r − r′, up to edges handled by images.
  2. Routing cost is a **shortest-path functional**: the min-plus semiring.
  3. Elliptic energies obey **variational principles**: one solve gives first-order
     sensitivities everywhere.

## 2. Decomposition into subproblems

| # | Subproblem | Precise form | Algebra / class |
|---|---|---|---|
| 1 | Net topology | Steiner tree of T_i in an obstacle metric | min-plus; NP-hard, Hanan/1-Steiner heuristics |
| 2 | Homotopy class per net | element of π₁(Ω∖obstacles) (free group) for each connection | topology; [analogs](../layer-collapse/analogs.md) cut conditions |
| 3 | Layer assignment | label per copper segment ∈ {1..L} | Potts / Max-k-cut (analogs) |
| 4 | Via placement | choose points where the layer label changes; cost v each | Ising domain walls (analogs, CVM) |
| 5 | Pin escape | vertex-disjoint paths from a pad array to its boundary | flow / circle graphs (analogs) |
| 6 | Bus pin order | permutation σ between two pin rows | RSK / LDS (analogs, tested) |
| 7 | Part orientation | r_k ∈ D₄ | discrete group action |
| 8 | Part position | x_k ∈ R², minimise F(x) with no overlap | continuous plus exclusion |
| 9 | Exclusion / legality | (A_k ⊕ B_c + x_k) ∩ (A_j + x_j) = ∅ | Minkowski sums → convolution (Kavraki) |
| 10 | Density / spreading | push a density ρ toward capacity | Poisson (ePlace) / optimal transport |
| 11 | Final legalisation | snap overlapping parts to legal sites with least motion | assignment / transport |
| 12 | Wirelength proxy | HPWL(x) separable in x and y | piecewise-linear, separable |
| 13 | Route-cost of a pad position | min over paths of the priced cost from pad to net tree | min-plus convolution |
| 14 | Congestion | multicommodity flow with capacities | LP duality → PathFinder prices |
| 15 | Decap-loop inductance | L(D) = L_mount + 0.2·d·ln(D²/r²) nH (pour mode) or a partial-inductance loop | closed-form in one distance |
| 16 | Hot-loop inductance | partial inductance of a terminal chain with images | Neumann double integral |
| 17 | Inductive crosstalk | M = ∮∮ G(r − r′) dl·dl′ (images) | bilinear in currents; convolution |
| 18 | Capacitive crosstalk | patch mutual capacitance C_m(r − r′) | bilinear; convolution |
| 19 | Crystal pulling | trace capacitance of XIN/XOUT ∝ length | linear in length |
| 20 | Thermal | (∇² − λ⁻²)T = −q/G_s, adiabatic edges | screened Poisson; DCT-diagonal |
| 21 | Cable common-mode / ESD | loop or window functionals of distances | closed-form |
| 22 | Return current in planes | J = argmin energy, div J = sources, J·n = 0 at slots | Hodge / Neumann projection |
| 23 | Pour shape | maximise conductance given clearance and area | elliptic plus free boundary |
| 24 | Pour fragmentation | components of pour minus signal halos | H₀ / Euler characteristic (analogs) |
| 25 | Length matching | ℓ(path) = target ± tol | constrained shortest path |
| 26 | Diff pair | two paths at fixed separation | path in a doubled configuration space |
| 27 | Satellite placement | decaps and series parts around one IC | assignment on site lattice |
| 28 | Obstruction detection | where L layers are too few | cuts (analogs), price maps (jc) |
| 29 | Legality check | DRC: clearance, mask, silk, spokes | local predicates |
| 30 | Incremental re-evaluation | Δcost after one move | dynamic shortest paths, low-rank updates |
| 31 | Mixed search | discrete (D₄, layers, classes) × continuous (x) | continuation, beam, LNS |
| 32 | Continuation schedule | β path from lifted to legal | exterior penalty homotopy |

## 3. Transformation catalog

Each entry gives (a) the mapping, (b) the known result, (c) what breaks, (d) the payoff,
(e) a cheap test, and (f) novelty.

### T1. Best-response maps as tropical (min-plus) convolutions
- **(a) Mapping.** In jc a part's best response is a whole-board argmin of a map. Today
  that map is HPWL plus an L1 distance to route "anchors" 2 mm out (`jc.tension_map`).
  The cost of connecting pad k at position y to its net is a function of y alone:
  D_n(y) = min over paths from y to the rest of net n of the β-priced path cost. For a
  uniform metric, D_n is the min-plus convolution of the net's indicator with the
  distance kernel. With prices and obstacles, D_n is one multi-source Dijkstra run from
  the net's other pins or tree cells. The part's map is
  C(x, r) = Σ_k D_{n(k)}(x + R_r p_k), a shift-and-add of a few fields, which is the
  min-plus analogue of the FFT correlation jc already does.
- **(b) Known results.**
  - Min-convolution with convex kernels runs in linear time (Felzenszwalb–Huttenlocher
    2012 [S]).
  - Dijkstra and fast marching run in O(N log N) (Sethian [S]).
- **(c) What breaks.**
  - D_n is computed with the net's own pad absent, so it treats the other pins as fixed
    (envelope approximation).
  - Multi-pin nets get "distance to tree", an upper bound on the Steiner increment.
  - Two pads of the same part on the same net are double-counted (take the min).
- **(d) Payoff.**
  - The lifted cost ranks placements by routed cost at ρ 0.85, against 0.51 for HPWL
    ([collapse_assign](../../tools/research/collapse_assign/RESULTS.md)). T1 brings that
    signal into every best response, priced at the current β.
  - It is the exact discrete version of the envelope-theorem pin tension, which failed as
    a *gradient* (`tension`, `grad`) and has not been tried as a *global argmin*.
- **(e) Test.** One Dijkstra at 0.4 mm (125²) takes 2 ms; at 0.1 mm (500²) it takes 63 ms
  [N, scipy csgraph]. Plan in §5.1.
- **(f) Novelty.**
  - Maze-distance placement cost models exist in VLSI routability work, but are rarely
    used as full-board argmin maps [U].
  - We found no PCB use.

### T2. Physics place terms as Green's-function fields
- **(a) Mapping.** `Phys.coarse_map` calls `Terms.delta` (~50 µs) every 1.2 mm. On a
  50 × 50 mm board that is ~1,700 calls (~85 ms) per part and rotation [I]. The terms
  split three ways:
  - **Thermal.** The victim-rise map for a moving victim is the temperature field of all
    other sources. The effect of a moving source on all victims is the correlation of the
    victim-weight map with G. Both are one screened-Poisson solve with Neumann edges,
    which the DCT-II diagonalises. The DCT's even reflection *is* kae's adiabatic-image
    lattice, with all rings included.
  - **Decap, ESD, CM, crystal.** Their dependence on the moving part's position is a
    closed form of a few distances: pour mode 0.2·d·ln(D²/r²), or a hop length. These
    vectorise over the grid; no FFT is needed. This corrects the example in the brief: the
    decap map is analytic, not a convolution.
  - **Coupling.** For a rigid victim pattern, M(x) is the cross-correlation of the two
    current rasters (x and y components) with the in-plane-invariant image kernel. That
    is exact for the part-internal current. Board hops stretch with x, so they are not a
    convolution; use the vector-potential line integral (T3) for them.
- **(b) Known results.**
  - Neumann Laplacian ↔ DCT-II: standard.
  - Green's function plus DCT thermal placement (Liu et al. TVLSI 2014 [S]); power
    blurring as convolution (Ziabari et al. [S]); ePlace's FFT Poisson density
    (Lu et al. 2015 [S]).
  - Our check [N]: on a 40 × 60 mm board at 0.1 mm, the DCT solve matches the K0
    image sum to 3·10⁻⁴ relative (r > 1 mm) and takes 12 ms. kae's rings = 1 is already
    converged; rings = 0 errs by 0.85%.
- **(c) What breaks.**
  - Uniform G_s is assumed; real copper varies. Then use the DCT solve as a
    preconditioner, or treat G_s as piecewise constant per region.
  - φ(u) is nonlinear, so maps are of spend, and φ is applied pointwise. That is exact
    for a single structure.
  - Hop stretching limits the coupling term (see above).
- **(d) Payoff.**
  - Exact full-resolution physics in jc's best response, instead of 1.2 mm samples
    filled in by nearest neighbour.
  - Physics is where jc wins (0.82× human), so its accuracy in the argmin matters.
  - Thermal maps become effectively free: one solve per iteration for all victims.
- **(e) Test.** Replace `coarse_map` with vectorised and DCT maps. Check that the maps
  equal `Terms.delta` at sample points, then run jc on the 10 physics boards.
- **(f) Novelty.**
  - Thermal: low (done for ICs).
  - The set of all kae terms as maps feeding a whole-board argmin: we found no
    precedent [U].

### T3. Routed coupling as an additive edge cost (vector-potential transform)
- **(a) Mapping.** The mutual inductance between a victim route P and aggressor currents
  is M = ∫_P A_agg·dl, where A_agg = G ⊛ J_agg is the vector potential. M is **linear and
  additive over the path's edges**. For traces over a plane the per-length kernel is
  K(s) = (μ₀/4π)·ln(1 + (2h/s)²) [I: image derivation, with A = 0 on the plane]. This
  matches the image-current picture and Johnson's 1/(1 + (D/h)²) return-current
  spread [S].
  - Edge cost |A·dl| is an upper bound on |M| by the triangle inequality, it is
    non-negative, and it fits A\* exactly.
  - The capacitive part works the same way with a potential field.
- **(b) Known results.**
  - Linearity of flux in the path (Stokes); FFT convolution.
  - Crosstalk-aware routing does exist: sensitive-net costs per global cell (Hung et al.
    ISQED 2008 [S]), and a higher-order RLCK maze cost (Bhaduri–Vemuri DATE 2005 [S]).
    Neither uses a convolved field [S].
- **(c) What breaks.**
  - Signed cancellation is lost (the cost is a bound).
  - Aggressor routes change during negotiation, so the field must be recomputed per
    PathFinder iteration (one FFT per aggressor class).
  - Victims that are not plane-referenced need the full loop.
- **(d) Payoff.**
  - Attacks the gap where fast physics predicts routed physics only at Spearman 0.55. The
    router itself would minimise routed coupling.
  - jc_full gains most from routed physics (0.80×), which suggests the leverage is there.
- **(e) Test.** For nets marked victim in kae's brief, add w·|A·dl| to the router cost on
  the 10 physics boards. Score with `RoutedPhys`.
- **(f) Novelty.** Moderate. The field-convolution form inside a PCB maze router has no
  precedent we found.

### T4. Pour-damage maps from the Dirichlet principle
- **(a) Mapping.** Pour conductance is G = min over potentials u of ∫σ|∇u|²
  (unit voltage). Removing copper S (a part's antipads or keep-out, or a signal's
  halo) gives G′ ≤ G − ∫_S σ|∇v|². So one solve v gives a **provable lower bound** on the
  loss for every S. The map over all positions of a part is the correlation of its mask
  with the energy density σ|∇v|²: one FFT, using jc's `FFTCorr`.
  - The same density used as a router cost for signals crossing a pour layer is the
    Hodge/return-current statement: do not cut where pour current flows.
- **(b) Known results.** Dirichlet/Thomson principles and Rayleigh monotonicity
  (classical [S]); topological derivatives in shape optimisation [S].
  - Our check [N]: on a perforated sheet with two pads, we cut 24 random part-sized holes
    and compared the cell-energy estimate with exact re-solves. The ratio ranged from
    0.82 to 1.78 (median 1.17; the cell sum double-counts edges, and the strict
    edge version is the bound). **Spearman 0.97.**
  - Cost [N]: a sparse LU at 0.4 mm (14.5k unknowns) takes 52 ms to factor and 2 ms per
    solve; at 0.2 mm, 227 ms and 9 ms.
- **(c) What breaks.**
  - The bound is first-order: large holes, or holes that cut a neck, lose more than
    predicted.
  - The pour outline is itself a function of the placement, so the map must be refreshed
    per iteration.
- **(d) Payoff.**
  - Full pour resistance tracks routed physics at ρ 0.65, but the cheap score used so far
    tracks it at only 0.11 ([collapse_pour](../../tools/research/collapse_pour/RESULTS.md)).
  - T4 makes the accurate one cheap enough for best responses and router costs.
- **(e) Test.** Plan in §5.3.
- **(f) Novelty.** We found no use as a placement or routing map for PCB pours [U].

### T5. Satellite parts by exact assignment
- **(a) Mapping.** Decaps, pull-ups and series terminations each attach to one IC.
  - Tile a ring of non-overlapping candidate slots around the IC from its legal map,
    spaced so that any rotation fits.
  - Cost c(part, slot, rotation) comes from the T2 maps.
  - For a parallel decap group, minimising L_par = (Σ 1/L_i)⁻¹ is equivalent to
    maximising Σ 1/L_i, which is **separable**.
  - Min-cost bipartite matching (Hungarian) is then exact for one group.
  - Across groups, linearise φ at the current u (a Frank–Wolfe step) and re-solve.
- **(b) Known results.**
  - Hungarian / min-cost flow.
  - Independent-set matching in VLSI detailed placement (NTUplace3 [U]; batched in
    ABCDPlace [S]).
  - PCB decap optimisation in the literature is GA or greedy over PDN ports [S].
- **(c) What breaks.**
  - Slot tiling wastes area.
  - Coupling between satellites of different ICs is ignored in one solve.
  - Caps shared by two ICs need a joint group.
- **(d) Payoff.** Decap and hot-loop terms dominate the HPWL placements' 4× physics
  deficit. An exact local optimum per IC is cheap (n ≤ 20).
- **(e) Test.** After jc's legalisation, re-assign the satellites of each IC. Compare the
  physics terms and DRC against jc.
- **(f) Novelty.** As a transplant to PCB with physics costs: moderate.

### T6. Homotopy class as a free-group word (H-signature) for route alternatives
- **(a) Mapping.** A connection's class relative to the k nearest large parts is a reduced
  word in the free group F_k, read from signed ray crossings. Augment A\* state with the
  word (truncated to k ≤ 3 obstacles near a conflict) to get the best route *per class*.
  jc can then choose classes jointly (going around a part instead of using a via).
- **(b) Known results.**
  - H-signature search (Bhattacharya, Kumar, Likhachev, Auton. Robots 2012 [S]).
  - Rubber-band topological routing (SURF, Dai et al. 1991 [S]).
- **(c) What breaks.**
  - The state space grows with the number of classes.
  - On two layers with vias every class is realisable, so classes matter for cost, not
    feasibility.
  - The user's "layer collapse = braid word problem" idea fails here. Braids model only
    monotone strands between two rows, where the problem reduces to the permutation/RSK
    case already done. With vias no braid is an obstruction.
- **(d) Payoff.**
  - jc uses 70% more vias than combo on large boards.
  - Its conflicts are mostly corridor sharing
    ([collapse_assign](../../tools/research/collapse_assign/RESULTS.md)).
  - Class alternatives could replace via hops.
- **(e) Test.** For the conflict cells with the highest jc history, enumerate 2–4 classes
  per involved net and pick a combination by local search. Count vias and clean.
- **(f) Novelty.** Low to moderate (topological routers exist; the H-signature in a grid
  PCB router appears new [U]).

### T7. Displacement-minimal legalisation as optimal transport
- **(a) Mapping.** jc ends by snapping each overlapping part greedily to its nearest legal
  pose. Instead, pose this as transport of the overlapping parts onto the legal free
  sites at least total |Δx|²: an assignment or min-cost flow over candidate sites from
  `legal_map`.
  - The linearised Monge–Ampère equation det(I + D²φ) ≈ 1 + Δφ is Poisson, so ePlace
    density is the small-displacement limit [I, standard].
- **(b) Known results.**
  - Brenier/OT [S].
  - Transportation-based placement (BonnPlace; Brenner–Struzyna DAC 2005 [S]).
  - Wasserstein-gradient-flow reading of Poisson floorplanning (arXiv 2510.08126 [S]).
- **(c) What breaks.**
  - Parts are not mass: a site is either free or not.
  - Rotations matter.
  - Legality is pairwise among the moved parts. Solve the assignment, then repair
    conflicts sequentially.
- **(d) Payoff.** Keeps routes from the collapse valid. Small: legal is already 0.879.
- **(e) Test.** Swap jc's end step; measure the routed-cost change across the snap.
- **(f) Novelty.** Low (VLSI legalisation uses flows).

### T8. Incremental shortest paths for re-route-per-move annealing
- **(a) Mapping.** After a move only edges near the old and new footprint change cost.
  LPA\*/D\* Lite repair the search tree instead of re-routing.
- **(b) Known results.** D\* Lite (Koenig–Likhachev AAAI 2002 [S]).
- **(c) What breaks.** PathFinder history changes every cost slightly, which hurts
  incrementality. It works only inside one annealing temperature.
- **(d) Payoff.** More moves per CPU-second in `anneal_phys` and in jc's polish stage. A
  2–5× gain is plausible [U].
- **(e) Test.** Count the fraction of search nodes that change per move on dev6 before
  implementing anything.
- **(f) Novelty.** Low (ECO routing).

### T9. Frustrated plaquettes as a via-forcing map
- **(a) Mapping.** In the planar Ising/CVM form (analogs), a face of the conflict graph
  with an odd number of "must differ" edges is frustrated. A minimum-weight perfect
  matching of frustrated faces in the dual gives the forced domain walls, that is, the
  vias.
- **(b) Known results.** Bieche et al. 1980 / Barahona 1982 [S via 0801.3143].
- **(c) What breaks.** It needs junctions of degree ≤ 3 (analogs). Via-proxy terms did not
  help in the joint loop
  ([collapse_cplace](../../tools/research/collapse_cplace/RESULTS.md)).
- **(d) Payoff.** A map of where vias are forced. Use it to steer jc restarts, which is
  jc's own stated next step, not a cost term.
- **(e) Test.** Correlate frustrated-face density with realised vias per region.
- **(f) Novelty.** The matching duality is known in CVM; a frustration map for steering is
  new [U].

### T10. Non-crossing routability as a determinant (Lindström–Gessel–Viennot, Fomin)
- **(a) Mapping.** For a bus or escape region on one layer, let M_ij be the
  walk-generating Green's function from source i to sink j, with fugacity z per cell
  (that is, (I − zA)⁻¹ restricted to the free cells). Then det M counts non-intersecting
  path systems when the boundary order permits only the identity (LGV, for acyclic
  graphs). For undirected walks it counts loop-erased non-intersection (Fomin 2001 [S]).
  log det is a smooth "one-layer routing entropy".
- **(b) Known results.** LGV lemma; Fomin, Trans. AMS 2001 [S].
- **(c) What breaks.**
  - Interior pads break the boundary-order condition, and the determinant then becomes
    signed.
  - Widths and clearances are coarse-grained into the cell size.
  - Vias make the one-layer case only a part of the problem.
- **(d) Payoff.** A differentiable escape and bus capacity score for the dense
  sensor-board failures. Speculative.
- **(e) Test.** On 0.5 mm-pitch escapes, check whether log det predicts which pins went
  unrouted.
- **(f) Novelty.** Not found in routing [U].

### T11. Extremal-length sandwich for pour resistance (tested: weak)
- **(a)/(b) Mapping and result.** With constant metrics, R_s·d²/A ≤ R ≤ R_s·A/w², where
  d is the geodesic distance between terminals, A the copper area and w the shortest
  separating cut. This rests on Duffin's 1962 reciprocity [S].
- **(c) What breaks [N]:**
  - It is exact on a rectangle (2.95–3.00 against 2.975).
  - On an L-shape the ratio of the bounds' geometric mean to R is 0.78; on a 75% slot it
    is 2.4; on a perforated sheet with pads the upper bound is 2–200× loose.
  - The lower bound alone stays within 0.37–1.0 of R.
- **(d)–(f) Payoff, test and novelty.** Superseded by T4 (exact solve plus the
  sensitivity map). Drop.

### T12. Exact single-pour splits by parametric min-cut
- **(a)/(b) Mapping and result.** A two-pour split of a layer is a binary labelling with a
  boundary cost (submodular). Graph cuts are exact (Boykov–Kolmogorov [U]). All
  area-multiplier values λ come from one parametric max-flow
  (Gallo–Grigoriadis–Tarjan 1989 [S]).
- **(c) What breaks.** collapse_pour showed that minimal boundary is the wrong objective:
  the shape should follow conductance.
- **(d)–(f) Payoff, test and novelty.** An exact replacement for MBO, which had no merit.
  Low.

### Checked and dropped (one line each)

| Idea | Verdict | Reason |
|---|---|---|
| Braid groups / word problem for collapse | Refuted | Only monotone two-row buses are braids (→ RSK, done). With vias no word is an obstruction (analogs: topology never forces > 2 layers) |
| Knot diagrams, gauge / fiber bundle of layers | No gain | The Z_L gauge with vias as defects is the Potts / CVM model already in analogs |
| Noether symmetry | Diagnostic only | Translation invariance gives Σ forces on movable parts = −(reactions of edges and locked parts) at stationarity. The grid and edges break it; no algorithm follows |
| Koopman lift of the annealing dynamics | No payoff | No low-dimensional linear observable is evident for discrete moves |
| jc as tropical limit / RG flow | Reframed | β multiplies the conflict penalty: an exterior-penalty homotopy, not a temperature. The soft-min (Maslov) limit was tested in `grad` (no merit). The tropical content that pays is T1. RG = scale homotopy = untested idea 28 (multigrid), known in VLSI multilevel placers |
| Minkowski sums / support functions | Already used | The FFT legal map *is* Kavraki's C-space convolution (1995 [S]). No-fit polygons add nothing for near-rectangular courtyards |
| Steerable filters for rotations | Small | Small horizontal loops have a vertical moment, so the far field is rotation-invariant. The 90° steps are exact raster rotations anyway |
| Eikonal / Fermat any-angle routes | Low | The Lee maze router is already its discrete form. Heat-method distances (Crane 2013 [S]) give smooth gradients, but gradient placement already failed |
| Radon transform of demand (all line cuts) | Low | Cut capacity never binds on our boards (collapse_obst) |
| Morse / persistence of the distance transform (channel widths) | Low | Same reason; useful only for a global-routing graph |
| Spectral placement, Lasserre / SOS, QUBO, tensor networks | Low | Known (Hall 1970 quadratic placement), too heavy, or no hardware; CP-SAT windows already failed |
| Sheaf cohomology of local legality | No algorithm | Local-to-global repair is what blocker-directed LNS does. The sheaf Laplacian adds no solver we can use |
| DCT-preconditioned CG on masked pours | Failed [N] | Fictitious domain at 10⁻⁴ contrast: no convergence in 2,000 iterations. Use a sparse LU at 0.4 mm instead |

## 4. Top-10 ranking

Score = expected payoff × plausibility ÷ test cost, each judged on a 1–5 scale [I].

| Rank | Transform | Payoff | Plaus. | Cost | Score | One line |
|---|---|---|---|---|---|---|
| 1 | T1 min-plus best-response maps | 5 | 4 | 1.5 | 13.3 | Price-aware route-cost fields replace HPWL and L1 tension in jc's argmin (lifted ρ 0.85 vs 0.51) |
| 2 | T2 Green's-function physics maps | 4 | 5 | 2 | 10.0 | Full-resolution physics in the argmin; thermal = one DCT solve (verified 3·10⁻⁴, 12 ms) |
| 3 | T4 Dirichlet pour-damage maps | 4 | 4 | 2 | 8.0 | One pour solve plus FFT: a lower bound on conductance lost at every position (Spearman 0.97) |
| 4 | T3 vector-potential coupling cost | 5 | 3 | 2.5 | 6.0 | Router minimises a bound on routed crosstalk; targets the 0.55 fast-to-routed gap |
| 5 | T5 satellite assignment | 3 | 4 | 2 | 6.0 | Exact Hungarian re-placement of decaps around each IC with physics costs |
| 6 | T6 H-signature route classes | 3 | 3 | 3 | 3.0 | Per-class alternatives to cut jc's +70% vias |
| 7 | T9 frustration map for restarts | 2 | 3 | 2 | 3.0 | Steer jc restarts to via-forced regions |
| 8 | T8 incremental shortest paths | 2 | 3 | 3 | 2.0 | More annealing moves per second |
| 9 | T7 OT legalisation | 1.5 | 4 | 2 | 3.0* | Least-motion snap at jc's end (*capped: legality already 0.88) |
| 10 | T10 LGV determinant routability | 3 | 1.5 | 3 | 1.5 | Differentiable one-layer escape capacity |

T7 is ranked below T8 despite its score because its upside is bounded by the legality
already reached.

## 5. Experiment plans (top 3)

### 5.1 T1: min-plus best responses in jc
- **Hypothesis.** Replacing jc's `hpwl_map` and `tension_map` with Σ_k D_{n(k)}(x + R_r p_k)
  on the current priced grid lowers routed length and vias at equal legality, because
  each argmin then sees obstacles and prices.
- **Build** (`tools/research/xf_minplus/`, new files; no edits to `pnr/` or
  `collapse_joint/`; subclass jc's driver):
  1. Per net, cost field c(cell) = 1 + β·(foreign occupancy + history) on a 0.4 mm
     max-pooled copy of the grid (layer-min over L, plus via cost for switching side).
  2. D_n = multi-source Dijkstra from the cells of the net's route or tree excluding the
     moving part's pads. Cache per iteration; invalidate only nets that re-routed.
  3. For a part, C(x, r) = Σ_k shift(D_{n(k)}, R_r p_k), upsampled to 0.1 mm. Take the
     min over pads sharing a net.
  4. Best-response map = C/g + phys_w·physics + β·conflict (unchanged). Add the switch
     `minplus_w ∈ {0, 0.5, 1}` as a blend with HPWL.
- **Controls.** jc (same seed and restarts), jc with tension_w = 0.
- **Runs.**
  - dev6 at 120 CPU-s, seeds 0–2, then ab33 seeds 0–2, using
    `kae-work/runext.sh … xf_minplus-ab33-v1 120 kae-work/ab33.txt 1`.
  - Compare with `jcollapse-jc-ab33-v3` using `pnr/compare.py`.
- **Metrics.** Legal, clean, completion, length, vias; fast and routed physics on the 10
  boards; time per iteration.
- **Success.** At least 5% less length or 20% fewer vias, with legal and completion within
  0.01, on 3 seeds.
- **Kill.** Iteration time more than doubles with no gain on dev6.
- **Diagnostic.** Spearman of C(x) against the realised re-routed cost for 200 random
  moves, compared with HPWL. This should reproduce the 0.85 vs 0.51 result at the
  single-move level.

### 5.2 T2: exact physics maps
- **Hypothesis.** jc's physics advantage is limited by `coarse_map`'s 1.2 mm sampling and
  the cost of computing it. Exact maps improve fast and routed physics and free CPU for
  restarts.
- **Build** (`tools/research/xf_physmap/`):
  1. For each structure touching a part, classify its dependence:
     - analytic-distance (decap pour mode, ESD, CM window, crystal length): vectorised
       numpy over the grid;
     - thermal: DCT solves with kae's G_s and λ;
     - coupling: FFT correlation of the part-internal current rasters plus exact
       evaluation of the hop segments on a 2 mm-step grid near the part (far field by a
       dipole).
  2. Apply φ(u) pointwise per structure and sum the deltas.
- **Validation first.**
  - At 500 random sample points per (part, rotation) on the 10 physics boards, the map
    must equal `Terms.delta` within 1% (thermal) or 5% (coupling, dipole far field).
  - Report the cases that fail.
- **Runs.** jc and jc_full with `coarse_map` replaced, 10 physics boards plus ab33, 3 seeds.
  Record the CPU share saved and the number of restarts achieved.
- **Success.** Fast physics at least 5% lower and routed physics not worse, with clean
  and completion unchanged.
- **Kill.** The validation fails on coupling and exact maps bring no gain from the
  thermal and analytic terms alone.

### 5.3 T4: pour-damage maps in placement and routing
- **Hypothesis.** A Dirichlet energy map of each pour lets placement and routing avoid
  destroying pour conductance. This improves the routed physics terms that depend on pours
  (decap pour mode, CM) at negligible routing cost.
- **Build** (`tools/research/xf_pour/`):
  1. Per pour net and layer, at 0.4 mm, take the region the pour would fill (board minus
     foreign keep-outs and halos).
  2. Solve the Laplace problem between the pour's high-current terminals with a sparse
     LU (52 ms factor; refactor only when the outline changes by more than 2%).
  3. E = σ|∇v|² per cell.
  4. Placement: add w_p·(mask_k ⋆ E) into jc's best-response map via `FFTCorr` (one extra
     kernel per part).
  5. Routing: add w_r·E to the cell cost of foreign nets on the pour's layer.
- **Validation.**
  - On 21 real pour nets (the `collapse_pour` set), compare the map's predicted loss for
    50 random footprint drops against exact re-solves. Require Spearman ≥ 0.9; we got
    0.97 on synthetic sheets.
  - Report the ratio range.
- **Runs.** jc ± T4 on the 10 physics boards and ab33, 3 seeds. Also report the pour
  resistance against human (collapse_pour scorer) as a secondary score.
- **Success.** Pour resistance ≤ 0.9× jc and routed physics lower, with completion
  within 0.01.
- **Kill.** No routed-physics change, which would mean pours are not on the critical
  path of kae's routed recheck.

## 6. Notes on the brief's examples

- **"Decap loop as a Green's-function convolution, so the best cap position is one
  FFT."** Partly wrong. The decap spend depends on one distance: the map is analytic and
  needs no FFT. The terms that are many-source sums (thermal, coupling, pour damage) are
  the convolutions.
- **"Two-layer via minimisation as Z₂ gauge / Ising with matching duality."** Correct, but
  already recorded with its degree-3 limit, and it had no merit as a router. The new use
  is the frustration map (T9).
- **"Homotopy class as braid word; collapse feasibility as a word problem."** The class of
  one net is a free-group word (useful: T6). Feasibility is capacity, not a word problem.
- **"Obstacle routing as conformally flat geodesics."** True: that is the eikonal equation,
  and the maze router already discretises it. The payoff is the min-plus field (T1), not
  continuous routes.
- **"Noether."** Gives an identity, not an algorithm.
- **"Minkowski and support functions."** The FFT legal map already realises them
  (Kavraki).
- **"Continuation as RG or tropical limit."** Reframed above.

## References

1. Kavraki, L. E. "Computation of configuration-space obstacles using the fast Fourier
   transform." IEEE Trans. Robotics and Automation 11(3):408–413, 1995. [S]
2. Lu, J. et al. "ePlace: Electrostatics-based placement using fast Fourier transform and
   Nesterov's method." ACM TODAES 20(2):17, 2015. [S]
3. Liu, S. S.-Y., Luo, Aroonsantidecha, Chin, Chen. "Fast thermal aware placement with
   accurate thermal analysis based on Green function." IEEE TVLSI 22(6):1404–1415, 2014.
   [S]
4. Ziabari, A. et al. "Power blurring: fast static and transient thermal analysis method
   for packaged integrated circuits and power devices." IEEE TVLSI, 2014. [S]
5. Felzenszwalb, P., Huttenlocher, D. "Distance transforms of sampled functions." Theory
   of Computing 8:415–428, 2012. [S]
6. Sethian, J. A. "A fast marching level set method for monotonically advancing fronts."
   PNAS 93:1591–1595, 1996. [S]
7. Crane, K., Weischedel, C., Wardetzky, M. "Geodesics in heat." ACM TOG 32(5), 2013.
   [S]
8. Bhattacharya, S., Likhachev, M., Kumar, V. "Topological constraints in search-based
   robot path planning." Autonomous Robots 33(3):273–290, 2012. [S]
9. Dai, W. W.-M., Dayan, T., Staepelaere, D. "Topological routing in SURF: generating a
   rubber-band sketch." DAC 1991. [S]
10. Koenig, S., Likhachev, M. "D\* Lite." AAAI 2002, 476–483. [S]
11. Bieche, I. et al. 1980; Barahona, F. 1982: planar spin-glass ground states by
    matching. Cited via Pardella & Liers, arXiv:0801.3143. [S]
12. Fomin, S. "Loop-erased walks and total positivity." Trans. AMS 353:3563–3583, 2001
    (arXiv math/0004083). [S]
13. Lindström 1973; Gessel & Viennot 1985: non-intersecting lattice paths determinant
    lemma. [U: not re-read]
14. Duffin, R. J. "The extremal length of a network." J. Math. Anal. Appl., 1962. [S via
    later citations]
15. Gallo, G., Grigoriadis, M. D., Tarjan, R. E. "A fast parametric maximum flow
    algorithm and applications." SIAM J. Comput. 18(1):30–55, 1989. [S]
16. Buzbee, B. L., Dorr, F. W., George, J. A., Golub, G. H. "The direct solution of the
    discrete Poisson equation on irregular regions." SIAM J. Numer. Anal. 8(4):722–736,
    1971. [S]
17. Freeman, W. T., Adelson, E. H. "The design and use of steerable filters." IEEE TPAMI
    13(9):891–906, 1991. [S]
18. Johnson, H., Graham, M. *High-Speed Digital Design*, eq. 5.2 (return current
    ∝ 1/(1 + (D/H)²)), as quoted by the author at sigcon.com. [S]
19. Hung, Lou, Li: crosstalk-aware global and track routing, ISQED 2008; Bhaduri,
    Vemuri: RLCK-moment maze routing, DATE 2005. [S]
20. Lin, Y. et al. "ABCDPlace: accelerated batch-based concurrent detailed placement."
    (independent-set matching), 2020. [S]
21. Brenner, U., Struzyna, M. "Faster and better global placement by a new
    transportation algorithm." DAC 2005. [S]
22. "Poisson energy formulation for floorplanning: variational analysis and mathematical
    foundations." arXiv:2510.08126, 2025. [S]
23. Boykov, Y., Kolmogorov, V. Max-flow/min-cut for energy minimisation in vision, IEEE
    TPAMI 2004. [U]
24. Hall, K. M. "An r-dimensional quadratic placement algorithm." Management Science,
    1970. [U]
25. Paul, C. R. *Inductance: Loop and Partial* (wire-above-plane images). [S: table of
    contents only; the kernel in T3 is our derivation]
