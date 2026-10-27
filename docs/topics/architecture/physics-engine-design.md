# Physics engine design: data model, kernels, discretization, performance

**TL;DR**
- **Each band is one operator on one discretization, factored once per (operator, band, epoch).** Reciprocity makes it symmetric, so the engine uses supernodal Cholesky (DC, thermal, inductive limit) or pivot-free LDLᵀ (lossy AC), never general LU. A compiled Cholesky refactors real-board operators 6–13× faster than SciPy's SuperLU at 0.08–0.8M nodes, in about half the memory [C].
- **Copper is held three ways:** exact polygons (topology, morphology, critics); disposable discretizations (1-D strips for tracks, sparse-tile quadtrees with P1 elements for pours, Peaceman wells for vias); and stable pieces for passports. A uniform 0.1 mm raster of a large suite board would hold 3–7M cells.
- **Optimizer workers get boundary Schur complements, not Green blocks.** A window's exact macro-model is the trailing block of one factorization with the window ordered last: 1.6 s at 281k nodes, against 51 s for a Green block. Quotes then take 25–110 µs and a committed edit 20–60 ms, within 10⁻¹⁰ of brute force [C].
- **Nothing is re-analysed within an epoch.** Patterns span the design domain; commits are rank-k updates (rank 8 in 3–91 ms at 76k–810k nodes, against 0.03–0.9 s for a compiled refactor and 0.2–9 s with SuperLU); an epoch ends only at a topological event or a pattern change.
- **The build plan's targets hold** with identity tolerances relative to conditioning, a compiled factorization from M1, and Schur windows, without which the 2 s refresh fails.

Tags: [C] one core of a shared 4-core VM (load 1–7; ±30%), by [eng_board_scaling](../../../tools/research/physics/eng_board_scaling.py), [eng_window_schur](../../../tools/research/physics/eng_window_schur.py), [eng_compiled_cholesky](../../../tools/research/physics/eng_compiled_cholesky.py) and [eng_discretization](../../../tools/research/physics/eng_discretization.py), on whole-board models (all nets, layers, vias) of BLDCM-Power (32 mm, 4 layers), bms-c1 (134 × 69 mm, 4 layers) and linecard (184 × 92 mm, 6 layers); [I] inference; [S] secondary. Types, algorithms, licences, tests: [details](physics-engine-design-details.md).

## Key facts

### 1. Data model

**Snapshots.** The engine reads immutable `kae.board` snapshots named by `board_rev` (a content hash) and never mutates one. Optimizer candidates are copy-on-write overlays (lists of `Edit`s) on a base snapshot. A `Quote` or `Candidate` records its `base_rev` and applies only there.

**Epochs.** An epoch key is (topology hash, pattern hash).
- *Topology:* K1's invariants per band (islands, holes, cycle rank, block–cut tree, return words, closures).
- *Pattern:* each operator's sparsity pattern, spanning the **design domain**, all copper that may exist in the current phase. Void cells carry zero admittance and isolated void nodes an identity row.
- Within an epoch only values change, so orderings, symbolic factorizations and windows are reused. An epoch ends at a topological event (λ = 1 at DC) or when the design domain grows.

**Dirty regions.** An edit maps, through KiCad uuid diffs, to changed elements and boxes per layer, which each consumer widens by its reach: K1 to the touched islands, K7 by the rule distance, K3 by 10h, where mutual inductance over a plane has fallen to 4%. Passports are invalidated lazily.

**Geometry has three representations:**

| Representation | Holds | Status | Read by |
|---|---|---|---|
| Polygons with holes per (net, layer), arcs to 1 µm; barrels, pad stacks | the copper | source of truth | K1, K7, critics, discretizers |
| Discretizations, one per (operator, band) | 1-D strips; sparse-tile 2:1 quadtrees with P1 elements; barrels with wells; contracted equipotentials | E1 on a recorded `ModelScope` | K2, K4, K5, K6 |
| PEEC windows | filaments, cells, 4–6 complex images per intact plane | E1; images E3 | K3 |
| Pieces | track segments ≤ 1 mm, pads, vias, pour and plane tiles on a board-anchored 1 mm lattice, part current paths, world conductors | stable ids | passports, jobs, ledger |

Piece ids anchor to KiCad uuids where an item exists and to the lattice for pours, so an edit invalidates only the tiles it touches; rerouted tracks inherit ids by overlap. Every element carries its piece id, so passports aggregate exactly.

**The extended graph.** Per band, nodes are copper islands, part terminals in band models (a capacitor above C_min(band) shorts) and world conductors (chassis, cable, heatsink, enclosure), whose facts stay E5 until answered; C_ext edges come from one electrostatic solve. A `ClosedLoopBudget` names a cycle of this graph, verified by K1. A regime cell per (structure, band) picks the representation.

**Beliefs.** Every number is a `kae.units.Belief`. Its `relative_to` names a content-hashed `ModelScope`: operator, discretization (kind, cell range, refinement level), idealizations (quasi-static, t < δ, ε_r = 1 for C_ext, 20 °C copper), stackup, band, `board_rev` and epoch. Lineage lists kernel versions and input Beliefs, so K8 can correlate shared idealizations.

### 2. Kernels

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

Three decisions sit inside the table:
- **Symmetric factorizations only.** Grounded DC, thermal and inductive-limit operators are positive definite: Cholesky. Lossy AC operators are complex symmetric with positive definite real part, so every leading minor is nonsingular and LDLᵀ needs no pivoting. Stability is proven only when the imaginary part is definite too (Higham 1998) [S], which fails near resonances, so each AC factorization checks its residual and falls back to pivoted LU. Complex costs 1.3× real [C].
- **Exact leverage for every branch by selected inversion** (Takahashi recurrences): a branch's endpoints are adjacent in L's pattern, so its inverse entries come at about one factorization's cost [I]. It replaces the 48-solve sketch (median error 8–12%, [real-board-passports](../physics/real-board-passports.md)).
- **Equipotentials are contracted, not penalized.** Pads, terminals and rigid links become single nodes, so the condition number stays the copper's own.

### 3. Discretization

- **Tracks are 1-D strips:** nodes at vertices, junctions and at most every 1 mm; R = R_s·Δs/w per segment; bends add conformal-map excess squares (0.5587 for a sharp 90° bend) [S]; a track end joins its pad or pour across its width. In 2-D a 0.15 mm track takes about 60 nodes per mm; on BLDCM-Power, small nets at 0.05 mm instead of 0.2 mm raise the model from 76k to 197k nodes [C].
- **Pours, planes and pads are sparse-tile quadtrees.**
  - 64 × 64-cell tiles exist only where copper does. Per-net bounding-box rasters hold 5–11× more cells than the copper on bms-c1 and linecard [C].
  - Leaf size is w_local/3, clamped to 0.025 mm–h_max: K7's width map gives w_local, the regime gives h_max (the gap height in the inductive-limit stack, ℓ_m on AC sheets).
  - The 2:1-balanced quadtree is triangulated into right isosceles triangles carrying P1 elements weighted by copper coverage. Non-obtuse triangles make the stiffness an M-matrix: a resistor network (every K4 identity holds) and a conforming element (one-sided energy bounds, consistent across refinement levels, unlike two-point fluxes over hanging faces).
  - On a curved test conductor (quarter annulus, exact 2.2662 squares), coverage-weighted P1 errs −0.47% at 4 cells across and ≤ 0.05% from 8; the prototypes' cell-centred graph errs −0.60% to +0.49% [C].
- **Vias are barrels with wells.** Where the barrel radius r_w is below the cell, it joins each sheet by Peaceman's well conductance 2π/(R_s·ln(r_e/r_w)), with r_e = 0.1985h on the 5-point and P1 stencil (e^−γ/2√2) and 0.1146h on Q4 [C]. For a 0.3 mm via in a 1 oz plane the well is within 0.9% (h = 0.2 mm) and 0.4% (0.1 mm) of R_s/(2π)·ln(R/r_w); tying the barrel to the cells it touches, as the prototypes do, reads 16% and 14% low [C]. The same r_e gives via inductance in plane pairs.
- **Corners.** Leaves grade toward re-entrant corners; damage budgets use the closed-form corner field r^(π/α−1) (E3).
- **Error control:**
  - *Refinement study:* each budget Belief is recomputed at h and h/2 in its dirty window; the difference is its discretization σ.
  - *Certified brackets* for class-A compliance budgets. Inner and outer pixel geometries, each solved in primal and stream-function form, bracket the true geometry by Rayleigh monotonicity. The bracket always held the exact value but is wide: 84% at 4 cells across, 9.4% at 32, 4.7% at 64 [C]. Tight certificates therefore use a boundary-fitted constrained-Delaunay mesh of the budget's region, primal and dual on one mesh, refined where the element-wise primal–dual gap is largest.
  - *Topology check:* the discretization's islands and holes must equal K1's; a mismatch is refined locally.

### 4. Performance

**Measured costs** [C] (window: 1,600 nodes on all layers; SciPy unless marked):

| Board, cell (nodes) | Build | Factor: SuperLU / compiled | Solve | Schur window | Green block | Rank-8 update, CHOLMOD |
|---|---|---|---|---|---|---|
| BLDCM-Power, 0.2 mm (76k) | 0.8 s | 0.21 / 0.03 s | 6 ms | 1.0 s | 10 s | 3 ms |
| BLDCM-Power, 0.1 mm (281k) | 2.6 s | 1.2 / 0.18 s | 31 ms | 1.6 s | 51 s | 22–34 ms |
| linecard, 0.35 mm (682k) | 19 s | 9.3 / 0.92 s | 140 ms | 8.6 s | 226 s | 91 ms |
| bms-c1, 0.2 mm (810k) | 10–15 s | 6.9–7.2 / 0.78 s | 120 ms | 7.6 s | 233 s | 71–82 ms |

- **Scaling.** Factor time grows as n^1.1–1.4 and fill as n^1.1–1.5 (22k–810k nodes). Fill is 18–31 nonzeros per node under AMD: 0.2–0.4 GB per million nodes per real band, twice that complex. METIS saves up to 22% of fill but takes longer to order than AMD takes to factor.
- **Backends.** faer (Rust, MIT) refactors 6–13× faster than SuperLU at equal fill; CHOLMOD adds rank-k up/downdates.
- **Build.** Point-sampled rasterization (6–11M points per second, 19 per cell) takes 17 of linecard's 19 s once assembly is linear; quadratic branch indexing, since fixed, had added 52 s [C].

**What must be incremental.**
1. *Quotes come from windows without solves:* a k-branch removal is k×k algebra on the window inverse G_W; a batch of Thevenin candidates is one vectorized expression (500 in 0.1–0.8 ms). That gives 9,000–40,000 exact quotes per core-second in numpy, up to ten times [physics-core-v2](../physics/physics-core-v2.md)'s estimate.
2. *Commits never refactor:* a rank-k update of G_W inside a window (20–60 ms), a rank-k up/downdate of the factor globally, and a numeric refactor only when accumulated updates cost more.
3. *Windows are boundary Schur complements.* K_W = Y_WW − Y_W∂·Y_RR⁻¹·Y_∂W, the exact Kron reduction of the board outside window W, is the trailing block of one factorization with W ordered last (|∂W| ≈ 0.12|W| solves give it 5× slower). Its quotes equal the Green block's to 10⁻¹²; it costs one factorization instead of |W| solves and absorbs local commits. An edit outside W marks the window stale.
4. *Topology and morphology* recompute only touched islands and tiles; passports are lazy.

**Memory under 4 GB:** factors 0.2–0.4 GB per million nodes per band; windows 20 MB each; dense passports pieces × budgets × bands × 16 B (40 MB for 10k × 50 × 5); tiles about 32 B per cell; dense right-hand sides capped at 256 MB (an uncapped 200-column block killed a 3M-node run at 10.7 GB [C]).

**Parallelism:** one actor per (operator, band, epoch), one worker per window, vectorized candidate batches, and multi-right-hand-side solves (48 cost 9–15 single solves in faer). Workers stay single-threaded for determinism; threads inside one factorization pay only above about 2M nodes [I].

**GPU:** not for sparse factorization (about 1 s on one core at 1M nodes; NVIDIA cuDSS is proprietary). It serves batched window algebra and candidate quotes, JAX placement kernels and surrogates, and openEMS or Palace finalists ([solver-ladder](../physics/solver-ladder.md)).

**Compiled code by milestone.** M1: CHOLMOD through scikit-sparse behind the `Factorization` protocol, SuperLU as fallback, linear assembly, memory caps. M4, with the router: the `kae-fast` crate (PyO3) with faer, the window quote kernel (about 1 µs per rank-1 quote [I]), a scanline coverage rasterizer, selected inversion and pivot-free complex LDLᵀ.

### 5. Licensing

Everything shipped is GPL-3.0-compatible: numpy, SciPy, Shapely and GEOS, Clipper2, contourpy, scikit-rf; CHOLMOD (LGPL-2.1+ and GPL-2.0+ modules), METIS (Apache-2.0), OpenBLAS; faer, PyO3, rayon (MIT or Apache-2.0); MUMPS (CeCILL-C) if adopted. FastHenry stays internal; Ki-PIDA and Konnect (AGPL) are reference only. Excluded: Shewchuk's Triangle and its wrappers (non-commercial), MKL PARDISO and cuDSS (proprietary). Table: [details §D](physics-engine-design-details.md#d-licences).

### 6. Correctness

- **Identities** against brute force on random edits, with conditioning-relative tolerances; **golden references** from the `rt_*` scripts and closed forms (Peaceman 0.1985, strip over a plane, 0.5587 squares); **refinement studies** on every regression board.
- **Metamorphic tests** (translation, rotation, mirror, reciprocity; floating islands change nothing) and the **mutation benchmark** (each planted fault moves a job verb or binding Belief by more than its σ).
- **Calibration:** coupons and measured boards enter as E4 Beliefs, a bias and spread per stackup, fab and structure class, valid inside the hull of their features. Matrix: [details §E](physics-engine-design-details.md#e-correctness).

### 7. API for three clients

All three read one `PhysicsSession` per board inside the session server ([system-design](system-design.md) §2); every return is a Belief or a container of them.
- **Optimizer** (in-process, batched, incremental): `window(region)` → `WindowModel` with `quote_batch(edits)` and `commit(edit)`; `session.commit(candidate)` at `base_rev`; `evaluate(terms, grad=True)`; `screen(edits)` for stage 1. A `QuoteBatch` is a columnar Belief container: value arrays per budget sharing one exactness, scope and lineage, so the Belief contract holds at array speed.
- **Critics and reports:** `passports(band, pieces, budgets)` → `.npz` tables; `value`, `bracket`, `floors`, `events`, `modes`, `regime`; board-physics-model views.
- **LLM and humans:** the read-only facade of [physics-core-v2-api](../physics/physics-core-v2-api.md) (`why_here`, `what_if`, `where_add`, `explain`, `menu`, `binding`, `unknowns`), answered from caches and stamped with `board_rev`, epoch and scope ids.

Signatures: [details §F](physics-engine-design-details.md#f-api).

### 8. Build order

| Step | Build | Accept when |
|---|---|---|
| E0 (M0) | `units` Belief, ModelScope; physics types; K1 on polygons; K4 on a generic operator; contraction | identities within 10⁻¹⁰ of refactoring on 1,000 random edits (skeleton; c·ε·κ on BLDCM-Power); λ = 1 exactly at disconnects; DC bounds hold; metamorphic tests to 10⁻⁹ |
| E1 (M1) | DC and thermal builder: strips, P1 tiles, wells, linear assembly; CHOLMOD backend | removal quotes within 10⁻⁹ of brute force on 3 real boards; annulus inside its bracket and within 0.5%; via well within 1%; islands equal K1's on 112/112 boards |
| E2 (M1) | passports (`.npz`), leverage, K5; HF stack window; Schur windows | [real-board-passports](../physics/real-board-passports.md) reproduced within 1%; scorecard median ≤ 2, p90 ≤ 10 CPU-min, ≤ 4 GB on ≥ 106/112 boards |
| E3 (M2) | complex K2 with residual check; K6; merged K3; physics actors | f_p within 2% of ls_post_lattice; Q = h/δ; K3 within 3.5% of ls_thin_sheet and 1.3% of PEECN; `what_if` ≤ 50 ms p95; refresh ≤ 2 s p95 |
| E4 (M2–M3) | K7 legalizer; K8; boundary-fitted brackets | vp_floors and in_emi_voi reproduced; legalization keeps K1 invariants; brackets contain closed forms |
| E5 (M4) | `kae-fast`: faer, quote kernel, rasterizer, selected inversion | rank-1 quote ≤ 2 µs; build ≤ 2 s per million copper cells; exact leverage of every branch in ≤ 3 factorizations' time |

## Recommendations for our system

1. Put CHOLMOD behind `Factorization` in M1; keep SuperLU as fallback and for complex bands until `kae-fast`.
2. Give optimizer workers boundary Schur windows; keep Green blocks as a test oracle.
3. Replace bounding-box rasters with sparse tiles and strips before fine-grid suite runs; quote E2 brackets only from boundary-fitted meshes.

## Conflicts and open questions

- **Tolerances and backends.** Identities hold to 10⁻¹² within one factorization; against an independent solver real boards give 2×10⁻¹¹–10⁻⁹ (conditioning), so tests state c·ε·κ. SuperLU takes 7–9 s at 0.7–0.8M nodes and refreshes a window in 7.6 s at 810k, hence a compiled factorization from M1.
- **Untested here:** P1 on graded quadtrees (only a uniform-grid test), selected inversion, pivot-free complex LDLᵀ.
- **Suite run** (110/112 boards logged, grids coarsened to ≤ 300k nodes): passports median 6 s, p90 79 s, maximum 397 s; peak memory median 0.5 GB, maximum 3.4 GB. The scorecard targets hold at that resolution; finer grids need the compiled factorization ([suite-physics-results](../physics/suite-physics-results.md)).
- **scikit-sparse 0.5** timed refactorization inconsistently; its up/downdate needs sorted row indices. Pin and test it.

## Sources

- [C]: the four `eng_*` scripts above, reusing [rb_board_passports](../../../tools/research/physics/rb_board_passports.py) and [vp_floors](../../../tools/research/physics/vp_floors.py); suite timings from [suite_passports](../../../tools/research/physics/suite_passports.py).
- [S]: Higham, Math. Comp. 67 (1998); Peaceman, SPE J. 18 (1978); Takahashi, Fagan, Chin, PICA 1973; Davis and Hager, SIAM J. Matrix Anal. Appl. 20 (1999); Prager and Synge, Q. Appl. Math. 5 (1947).

See also: [details](physics-engine-design-details.md) · [system-design](system-design.md) · [build plan](system-design-build-plan.md) · [physics-core-v2](../physics/physics-core-v2.md) · [real-board-passports](../physics/real-board-passports.md)
