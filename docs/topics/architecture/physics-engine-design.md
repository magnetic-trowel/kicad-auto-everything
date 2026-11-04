# Physics engine design: data model, kernels, discretization, performance

Scope: design of the `kae.physics` engine (not built): data model, kernels K1–K8 and their update rules, discretization, measured costs. Not here: types, API signatures, licence table, test matrix, build order E0–E5 -> [details](physics-engine-design-details.md); session server -> [system-design](system-design.md); milestones -> [build plan](system-design-build-plan.md).
Keys: physics engine, `kae.physics`, epoch, EpochKey, design domain, board_rev, ModelScope, Belief, dirty region, piece, passport, extended graph, world conductor, regime cell, K1–K8, supernodal Cholesky, CHOLMOD, scikit-sparse, faer, SuperLU, `Factorization`, pivot-free LDLᵀ, boundary Schur complement, Kron reduction, window, G_W, Green block, Woodbury/Thevenin quote, edit spectrum λ, rank-k up/downdate, selected inversion, Takahashi, leverage, strip, sparse tile, P1 quadtree, Peaceman well, sandwich bracket, Prager–Synge, Beckmann bound, `kae-fast`, AMD, METIS

Tags: [C] one core of a shared 4-core VM (load 1–7; ±30%), by [eng_board_scaling](../../../tools/research/physics/eng_board_scaling.py), [eng_window_schur](../../../tools/research/physics/eng_window_schur.py), [eng_compiled_cholesky](../../../tools/research/physics/eng_compiled_cholesky.py), [eng_discretization](../../../tools/research/physics/eng_discretization.py), on whole-board models (all nets, layers, vias) of BLDCM-Power (32 mm, 4 layers), bms-c1 (134 × 69 mm, 4 layers), linecard (184 × 92 mm, 6 layers); [I] inference; [S] secondary.

## Results

- One symmetric operator per band on one discretization, factored once per (operator, band, epoch): supernodal Cholesky (DC, thermal, inductive limit) or pivot-free LDLᵀ (lossy AC), never general LU; compiled Cholesky, not SuperLU.
- Copper held as exact polygons, disposable discretizations and stable pieces, not a uniform raster (0.1 mm of a large suite board = 3–7M cells).
- Optimizer workers get boundary Schur complements, not Green blocks; nothing is re-analysed within an epoch; commits are rank-k updates.
- The build plan's targets hold with conditioning-relative identity tolerances, a compiled factorization from M1 and Schur windows; without Schur windows the 2 s refresh fails.
- Benchmark numbers: [kae-exact-physics-before-routing](../../research/placement/kae-exact-physics-before-routing.md#engine-benchmarks).

## Data model

- **Snapshot:** immutable `kae.board` snapshot named by `board_rev` (content hash). Optimizer candidates = copy-on-write overlays (lists of `Edit`) on a base snapshot. A `Quote` or `Candidate` records `base_rev` and applies only there.
- **Epoch key** = (topology hash, pattern hash).
  - Topology: K1 invariants per band (islands, holes, cycle rank, block–cut tree, return words, closures).
  - Pattern: each operator's sparsity pattern over the **design domain** (all copper that may exist in the current phase). Void cells carry zero admittance; isolated void nodes get an identity row.
  - Within an epoch only values change: orderings, symbolic factorizations, windows are reused. Epoch ends at a topological event (λ = 1 at DC) or when the design domain grows.
- **Dirty region:** an edit maps via KiCad uuid diffs to changed elements and boxes per layer; each consumer widens by its reach: K1 to touched islands, K7 by rule distance, K3 by 10h (mutual inductance over a plane has fallen to 4%). Passports invalidate lazily.

| Representation | Holds | Status | Read by |
|---|---|---|---|
| Polygons with holes per (net, layer), arcs to 1 µm; barrels, pad stacks | the copper | source of truth | K1, K7, critics, discretizers |
| Discretizations, one per (operator, band) | 1-D strips; sparse-tile 2:1 quadtrees with P1 elements; barrels with wells; contracted equipotentials | E1 on a recorded `ModelScope` | K2, K4, K5, K6 |
| PEEC windows | filaments, cells, 4–6 complex images per intact plane | E1; images E3 | K3 |
| Pieces | track segments ≤ 1 mm, pads, vias, pour/plane tiles on a board-anchored 1 mm lattice, part current paths, world conductors | stable ids | passports, jobs, ledger |

- **Piece ids** anchor to KiCad uuids where an item exists, to the lattice for pours: an edit invalidates only touched tiles; rerouted tracks inherit ids by overlap. Elements carry piece ids, so passports aggregate exactly.
- **Extended graph** (per band): nodes = copper islands, part terminals in band models (a capacitor above C_min(band) shorts), world conductors (chassis, cable, heatsink, enclosure; facts E5 until answered); C_ext edges from one electrostatic solve. A `ClosedLoopBudget` names a cycle of this graph, verified by K1. A regime cell per (structure, band) picks the representation.
- **Belief:** every number is a `kae.units.Belief`; `relative_to` names a content-hashed `ModelScope`: operator, discretization (kind, cell range, refinement level), idealizations (quasi-static, t < δ, ε_r = 1 for C_ext, 20 °C copper), stackup, band, `board_rev`, epoch. Lineage lists kernel versions and input Beliefs, so K8 can correlate shared idealizations.

## Kernels K1–K8

| Kernel | Algorithm | Exactness | Cost [C] | Incremental rule | Seed |
|---|---|---|---|---|---|
| K1 topology | polygon unions; union-find over pieces; Tarjan bridges; holes from ring counts; return words | E0 on polygons | O(V + E) | touched islands; a changed invariant is an event | pc2_core_skeleton, ct_cut_topology |
| K2 sheet operator | assembly; Cholesky or pivot-free LDLᵀ; shift-invert Lanczos for modes | E1 | 0.03–0.9 s at 76k–810k nodes, compiled | rank-k updates; refactor reusing the analysis | rb_board_passports, pc2_core_skeleton, pw_sheet |
| K3 PEEC | Grover/Ruehli partials; complex images; meshed planes at slots; mesh form NᵀZN, dense LDLᵀ | E1; images E3 | 0.1–1.7 ms per loop; 1.5–3 s per band at 4.4k branches | bordered rank-k updates | sl_loop_peec, pw_peec, cd_conductor_passport, ls_thin_sheet |
| K4 response | states, adjoints, lead fields, Tellegen attribution, Woodbury and Thevenin quotes with edit spectrum λ and radius r, leverage | E1; DC first-order bounds E2 | 25–110 µs per window quote; 0.07–7 s direct | rank-k update of the window inverse | pc2_core_skeleton, cd_conductor_passport |
| K5 certificates | Beckmann bound; convex relaxation with Frank–Wolfe gap; primal–dual brackets | E2 within scope | µs; 8 s at 4.3k cells | per move; warm-started per epoch | vp_floors |
| K6 modal Q ledger | port-and-mode reduction; eigenproblem; 1/Q = Σ1/Q_k; class per (budget, band) | E1; cavity forms E3 | ms–s | Rayleigh shifts; recompute at events | th_damping_ledger, fe_cavity |
| K7 morphology | exact distance transform per tile; width map; offsets; necks; critical area | exact geometry | 0.16–0.36 s per Mpixel | dirty tiles plus rule distance | op_topopt_pour |
| K8 belief, VOI | lineage-aware propagation; fusion; EVPPI; z = Φ⁻¹(1 − c/L) | bookkeeping | s per decision | changed footprints | in_emi_voi |

- **Symmetric factorizations only.** Grounded DC, thermal, inductive-limit operators are positive definite: Cholesky. Lossy AC operators are complex symmetric with positive definite real part: every leading minor is nonsingular, so LDLᵀ needs no pivoting. Stability is proven only if the imaginary part is definite too (Higham 1998) [S], which fails near resonances. Complex costs 1.3× real [C].
- **Equipotentials contracted, not penalized:** pads, terminals, rigid links become single nodes, so the condition number stays the copper's own.

## Algorithms and update rules

**Quotes (K4).** Edit removing branches B (incidence A_B, admittances y_B), port injections U = Y⁻¹E:
- S_B = A_Bᵀ·Y⁻¹·A_B; ΔZ = Vᵀ(diag(1/y_B) − S_B)⁻¹V, V = A_BᵀU; λ = eig(diag(y_B)·S_B); r = max|λ|.
- Adding z between nodes m, n: ΔZ = −ΔφΔφᵀ/(z + Z_th), Z_th = aᵀY⁻¹a.
- Inside a window every Y⁻¹ entry comes from G_W: no solve. A k-branch removal is k×k algebra; 500 Thevenin candidates are one vectorized expression (0.1–0.8 ms): 9,000–40,000 exact quotes per core-second in numpy, up to 10× [physics-core-v2](../physics/physics-core-v2.md)'s estimate [C].
- Singular Woodbury matrix = K1 event (λ = 1): infinite if a terminal is cut off, finite if copper merely floats.

**Windows (boundary Schur complements).** Give optimizer workers these; keep Green blocks as a test oracle.
- K_W = Y_WW − Y_WR·Y_RR⁻¹·Y_RW: exact Kron reduction of the board outside W = trailing block L_WW·L_WWᵀ of one factorization ordered R (by AMD), then W. Pivot-free; agrees with the boundary-solve form to 5×10⁻¹⁴ on bms-c1; quotes equal the Green block's to 10⁻¹² [C]. Cost: one factorization instead of |W| solves; |∂W| ≈ 0.12|W| boundary solves give it 5× slower.
- Sources outside W enter as ŝ_W = s_W − Y_WR·Y_RR⁻¹·s_R.
- Commit Y + A·D·Aᵀ inside W: G' = G − GA(D⁻¹ + AᵀGA)⁻¹AᵀG, φ' = G'ŝ: 20–60 ms for rank 8 at |W| = 1,600 vs 0.3–0.4 s to re-invert [C]. An edit outside W marks it stale; one factorization refreshes it.
- Default size: 1,600–3,200 nodes on all layers (3 mm square at 0.1 mm, 6 mm at 0.2 mm, 4 layers), |∂W| ≈ 190–260; larger regions take several windows.

**Global commits (never refactor per commit).** C = A_B·diag(√|y_B|) is a downdate (removal) or update (addition) of the Cholesky factor (Davis–Hager), touching only columns on the edit's elimination-tree paths. Refactor numerically when accumulated update flops exceed one refactorization. A K1 event changes the ground set: re-analyse (new epoch).

**AC factorization (K2, K3).** Pivot-free LDLᵀ on the symmetric pattern, one step of iterative refinement; if ‖Yx − b‖/‖b‖ > 10⁻¹⁰, refactor with threshold (pivoted) LU, which near-resonant bands may need. At the skeleton's 900 MHz anti-resonance, symmetric-mode SuperLU stayed within 4×10⁻¹¹ of refactoring ([physics-core-v2](../physics/physics-core-v2.md)) [C].

**Leverage.** M1: 48-solve Johnson–Lindenstrauss sketch for every branch (median error 8–12%) plus exact values for loaded and series pieces ([real-board-passports](../physics/real-board-passports.md)). M4: exact by selected inversion: Z = Y⁻¹ on L's pattern by the Takahashi recurrences (column by column from the last); a branch's endpoints are adjacent in L's pattern, so ρ_b = y_b(Z_aa + Z_bb − 2Z_ab) for every branch at about one factorization's cost; removals of pieces whose nodes share a supernode come from the same Z [I].

**Certificates (K5).** Primal φ with Dirichlet terminals overestimates conductance; dual stream function ψ (one unknown constant per hole) overestimates resistance; together they bracket R (Prager–Synge). Element gap ∫_K |σ∇φ − J_ψ|²/σ drives refinement. Beckmann bound R_s·W₁²/A and Frank–Wolfe floor follow [vp_floors](../../../tools/research/physics/vp_floors.py).

**Modes (K6).** Passive port-and-mode reduction (PRIMA-type Krylov projection); dense generalized eigenproblem; channel shares from Rayleigh quotients 1/Q_k = x*R_k x/(ω·x*M x).

**Morphology (K7).** Signed exact Euclidean distance transform per tile → width map (2 × SDF on ridges), which sets legality and cell size. Necks = ridge minima below w_min. Legalization: Clipper offsets (close by the gap, open by the width), accepted only if K1 invariants are unchanged or the change is intended.

**Beliefs (K8).** Var y = sᵀΣs, Σ correlating inputs that share an idealization (lineage); inverse-variance fusion within a lineage class; EVPPI by nested Monte Carlo ([in_emi_voi](../../../tools/research/physics/in_emi_voi.py)).

## Discretization rules

Replace bounding-box rasters with sparse tiles and strips before fine-grid suite runs.

**Tracks: 1-D strips.**
- Nodes at polyline vertices, at junctions with tracks, vias, pads, and at most every min(1 mm, 4w). Segment conductance w/(R_s·Δs).
- Sharp 90° bend: corner square counts 0.5587 squares (conformal map), 0.441 below the centreline count ([vp_floors](../../../tools/research/physics/vp_floors.py) `bracket`) [S].
- At a pad or pour the end node links to sheet nodes across the track width, each in proportion to its width share.
- In 2-D a 0.15 mm track takes about 60 nodes per mm; on BLDCM-Power, small nets at 0.05 mm instead of 0.2 mm raise the model from 76k to 197k nodes [C].

**Pours, planes, pads: sparse-tile quadtrees.**
- 64 × 64 finest-cell tiles exist only where copper does; per-net bounding-box rasters hold 5–11× more cells than the copper on bms-c1 and linecard [C].
- Each tile holds a 2:1-balanced quadtree, leaves 1–16 finest cells; a leaf splits while h > w_local/3 or h > h_max. Leaf size clamped to 0.025 mm–h_max; w_local from K7's width map, h_max from the regime (gap height in the inductive-limit stack, ℓ_m on AC sheets).
- Right isosceles triangles carry P1 elements weighted by copper coverage (exact Clipper2 clipping). Edge weights ½(cot α + cot β): ½ per leg, 0 across the hypotenuse. Hanging nodes resolved by standard right-isosceles templates, so every triangle stays non-obtuse → stiffness is an M-matrix: a resistor network (every K4 identity holds) and a conforming element (one-sided energy bounds, consistent across refinement levels, unlike two-point fluxes over hanging faces).
- Curved test conductor (quarter annulus, exact 2.2662 squares): coverage-weighted P1 errs −0.47% at 4 cells across, ≤ 0.05% from 8; the prototypes' cell-centred graph errs −0.60% to +0.49% [C].

**Vias and electrodes.**
- Barrel with r_w < h/2 joins each layer's nearest node by Peaceman's well conductance 2π/(R_s·ln(r_e/r_w)), r_e = 0.1985h on the 5-point and P1 stencil (e^−γ/2√2), 0.1146h on Q4 [C]; otherwise its annulus nodes are contracted into the barrel node. The same r_e gives via inductance in plane pairs.
- 0.3 mm via in a 1 oz plane: well within 0.9% (h = 0.2 mm) and 0.4% (0.1 mm) of R_s/(2π)·ln(R/r_w); tying the barrel to the cells it touches (the prototypes) reads 16% and 14% low [C].
- Barrel segments: ρ·l/(π(d + t)t), plating t = 20 µm unless the stackup says otherwise. Pads with an equipotential terminal are contracted.
- Corners: leaves grade toward re-entrant corners; damage budgets use the closed-form corner field r^(π/α−1) (E3).

**AC and HF grids.** Inductive-limit stack window: one grid across layers, cells ≤ ½ smallest gap; its outer-field thickness (moved L by 14% in [real-board-passports](../physics/real-board-passports.md)) goes into the scope. Telegrapher sheets: cells ≤ min(ℓ_m/2, λ/20). PEEC: ≥ 31 graded filaments where w/h > 10 ([verification-and-limits](../physics/verification-and-limits.md)).

**Error control.**
- Refinement study: each reported Belief recomputed at h/2 inside its dirty window + 2 mm; value ± |Δ| = discretization spread (E3 when the Richardson ratio is consistent, else flagged).
- Sandwich bracket (class-A compliance budgets): inner raster = cells entirely inside copper, outer = every cell touching it; R(outer, primal) ≤ R_true ≤ R(inner, dual) for self terms (Rayleigh monotonicity + Prager–Synge). Annulus: always held, width 84% at 4 cells across, 39% at 8, 19% at 16, 9.4% at 32, 4.7% at 64 [C]. Too wide: quote E2 brackets only from boundary-fitted meshes.
- Boundary-fitted certificate: constrained Delaunay mesh of the budget's region (spade, MIT/Apache-2.0, or CGAL, GPL-3.0+), P1 primal and dual on one mesh, refined by the element gap (where the element-wise primal–dual gap is largest) until the bracket < budget margin / z.
- Topology check: discretization islands and holes must equal K1's; a mismatch is refined locally.

## Performance

Measured costs per board (build, factor, solve, window, Green block, rank-8 update), scaling, backends and build time: [engine benchmarks](../../research/placement/kae-exact-physics-before-routing.md#engine-benchmarks) [C]. Consequences:

- **Backends:** faer (Rust, MIT) for refactorization; CHOLMOD for rank-k up/downdates.
- **Incremental:** topology and morphology recompute only touched islands and tiles; passports lazy.
- **Memory < 4 GB:** factors 0.2–0.4 GB per million nodes per band; windows 20 MB each; dense passports pieces × budgets × bands × 16 B (40 MB for 10k × 50 × 5); tiles ≈ 32 B per cell; dense right-hand sides capped at 256 MB (an uncapped 200-column block killed a 3M-node run at 10.7 GB [C]).
- **Parallelism:** one actor per (operator, band, epoch), one worker per window, vectorized candidate batches, multi-RHS solves (48 cost 9–15 single solves in faer). Workers single-threaded for determinism; threads inside one factorization pay only above ≈ 2M nodes [I].
- **GPU:** not for sparse factorization (≈ 1 s on one core at 1M nodes; NVIDIA cuDSS proprietary); it serves batched window algebra and candidate quotes, JAX placement kernels and surrogates, openEMS or Palace finalists ([solver-ladder](../physics/solver-ladder.md)).
- **Compiled code by milestone.** M1: put CHOLMOD (scikit-sparse) behind the `Factorization` protocol; keep SuperLU as fallback and for complex bands until `kae-fast`; linear assembly; memory caps. M4 (with the router): `kae-fast` crate (PyO3) with faer, window quote kernel (≈ 1 µs per rank-1 quote [I]), scanline coverage rasterizer, selected inversion, pivot-free complex LDLᵀ.
- **Licensing:** every shipped dependency is GPL-3.0-compatible → [licence table](physics-engine-design-details.md#licences).

## Open questions

- **Tolerances and backends.** Identities hold to 10⁻¹² within one factorization; against an independent solver real boards give 2×10⁻¹¹–10⁻⁹ (conditioning), so tests state c·ε·κ. SuperLU takes 7–9 s at 0.7–0.8M nodes and refreshes a window in 7.6 s at 810k: hence a compiled factorization from M1.
- **Untested here:** P1 on graded quadtrees (only a uniform-grid test); selected inversion, including for multi-node pieces, which relies on supernodes aligned with tiles [I]; pivot-free complex LDLᵀ; stream-function duals on real copper with holes (one unknown constant per hole).
- **Suite run** (110/112 boards logged, grids coarsened to ≤ 300k nodes): passports median 6 s, p90 79 s, max 397 s; peak memory median 0.5 GB, max 3.4 GB. Scorecard targets hold at that resolution; finer grids need the compiled factorization ([suite-physics-results](../physics/suite-physics-results.md)).
- **scikit-sparse 0.5** timed refactorization inconsistently; its up/downdate needs sorted row indices. Pin and test it.

## Sources

- [C]: the four `eng_*` scripts above, reusing [rb_board_passports](../../../tools/research/physics/rb_board_passports.py), [pc2_core_skeleton](../../../tools/research/physics/pc2_core_skeleton.py) and [vp_floors](../../../tools/research/physics/vp_floors.py); suite timings from [suite_passports](../../../tools/research/physics/suite_passports.py).
- [S]: Higham, Math. Comp. 67 (1998); Peaceman, SPE J. 18 (1978), wells; Takahashi, Fagan, Chin, PICA 1973, selected inversion; Davis and Hager, SIAM J. Matrix Anal. Appl. 20 (1999), up/downdate; Prager and Synge, Q. Appl. Math. 5 (1947), brackets; Odabasioglu, Celik, Pileggi (1998), PRIMA; Felzenszwalb and Huttenlocher (2012), distance transforms.
