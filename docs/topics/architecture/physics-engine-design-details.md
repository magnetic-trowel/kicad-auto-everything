# Physics engine design, details: types, algorithms, licences, tests, API

**TL;DR**
- **Types:** frozen dataclasses for epochs, scopes, pieces, edits, quotes and events; arrays for discretizations, operators and windows; `.npz` tables for passports. Belief and Exactness live in `kae.units`, the rest in `kae.physics`.
- **Algorithms:** quotes on a window inverse; Kron-reduced windows from a factorization with the window last; rank-k up/downdates for commits; selected inversion for leverage; pivot-free complex LDLᵀ with a residual check.
- **Discretization:** strips, P1 quadtree tiles, Peaceman wells, contracted electrodes; refinement studies and primal–dual certificates.
- **Every dependency** is GPL-3.0-compatible or kept out of shipped code; **every kernel** has an independent check; **three clients** share one session API.

Tags as in [physics-engine-design](physics-engine-design.md), whose decisions this specifies.

## Key facts

### A. Types

```python
# kae.units
class Exactness(IntEnum):
    E0 = 0; E1 = 1; E2 = 2; E3 = 3; E4 = 4; E5 = 5   # topological ... conjectured

@dataclass(frozen=True, slots=True)
class Belief:
    id: str                                  # content hash; cited by explanations
    value: complex | float
    unit: str
    exactness: Exactness
    relative_to: str                         # ModelScope.id
    interval: tuple[float, float] | None = None    # E2: guaranteed; E4: calibrated coverage
    spread: Mapping[str, float] | None = None      # {"disc": .., "level": .., "shape": ..}
    validity: Literal["in", "edge", "out"] = "in"
    lineage: tuple[str, ...] = ()            # kernel@version and input Belief ids

# kae.physics: versions and scope
@dataclass(frozen=True, slots=True)
class EpochKey:
    topology: str        # hash of K1 invariants for every band
    pattern: str         # hash of every operator's sparsity pattern (the design domain)

@dataclass(frozen=True, slots=True)
class ModelScope:
    id: str              # content hash of the fields below
    board_rev: str
    epoch: EpochKey
    operator: str        # dc | thermal | stack_L | telegrapher | peec | mna
    band: str
    discretization: str  # "p1-quadtree 0.025-0.4mm L2" | "strip 1mm" | "peec nf=31 img=6"
    idealizations: tuple[str, ...]  # quasi-static, t<delta, eps_r=1 C_ext, 20C copper, no solder
    stackup: str
    kernels: tuple[str, ...]

@dataclass(frozen=True, slots=True)
class DirtyRegion:
    layer: str
    box: tuple[float, float, float, float]          # mm
    items: tuple[str, ...]                          # KiCad uuids
    elements: Mapping[tuple, np.ndarray]            # operator key -> changed element ids

# pieces and the world
@dataclass(frozen=True, slots=True)
class Piece:
    id: str              # "trk:<uuid>:3", "via:<uuid>", "pour:GND:In2.Cu:41,17", "world:heatsink1"
    kind: str            # track | arc | pad | via | pour | plane | part | world
    net: str
    layers: tuple[str, ...]
    anchor: str          # KiCad uuid, or the 1 mm lattice index of a tile
    bbox: tuple[float, float, float, float]

@dataclass(frozen=True, slots=True)
class WorldConductor:
    id: str
    role: str            # chassis | cable | heatsink | enclosure | earth | lisn | test_setup
    facts: Mapping[str, Belief]              # C_ext, Z_cm(f): E5 until answered
    bonds: tuple[tuple[str, str], ...]       # (piece id, Belief id of the bond impedance)

# operators, factorizations, windows
@dataclass(frozen=True, slots=True)
class Discretization:
    key: tuple[str, str, EpochKey]           # (operator, band, epoch)
    node_xyl: np.ndarray                     # (n, 3) float32: x, y in mm, layer index
    node_piece: np.ndarray                   # (n,) int32
    elem_nodes: np.ndarray                   # (m, 3) int32: triangle; strip and barrel pad with -1
    elem_piece: np.ndarray                   # (m,) int32
    elem_weight: np.ndarray                  # (m,) coverage x sheet coefficient
    electrodes: Mapping[str, int]            # contracted equipotentials -> node
    scope: ModelScope

@dataclass(slots=True)
class Operator:
    key: tuple[str, str, EpochKey]
    Y: sp.csc_array                          # symmetric; lower triangle stored
    branch_a: np.ndarray; branch_b: np.ndarray; branch_y: np.ndarray; branch_piece: np.ndarray
    blocks: tuple["CoupledBlock", ...]       # dense admittance blocks (stack faces, PEEC mesh)
    ports: Mapping[str, sp.csc_array]        # source and observation injections
    scope: ModelScope

class Factorization(Protocol):              # CHOLMOD, faer or SuperLU behind one interface
    key: tuple[str, str, EpochKey]
    def solve(self, B: np.ndarray) -> np.ndarray: ...
    def updown(self, C: sp.csc_array, sign: int) -> None: ...   # rank-k, in place
    def refactor(self, Y: sp.csc_array) -> None: ...            # same pattern
    def schur(self, window: np.ndarray) -> np.ndarray: ...      # K_W, window ordered last
    def rcond(self) -> float: ...

@dataclass(slots=True)
class WindowModel:
    key: tuple[str, str, EpochKey]
    base_rev: str
    nodes: np.ndarray                        # (W,) global node ids
    K: np.ndarray                            # (W, W) Kron-reduced operator
    G: np.ndarray                            # K^-1
    src: np.ndarray                          # (W, S) Kron-reduced source vectors
    phi: np.ndarray                          # (W, S) = G @ src
    lead: np.ndarray                         # (W, B) adjoint (lead) fields of the budgets
    stale: bool = False

# edits, quotes, events
@dataclass(frozen=True, slots=True)
class Edit:
    kind: str            # remove | add | cut | widen | add_via | move_part | reroute | stackup | eco
    target: tuple[str, ...]
    params: Mapping[str, object]
    base_rev: str

@dataclass(frozen=True, slots=True)
class TopoEvent:
    kind: str            # disconnect | float_island | {cycle,hole,bridge}_{created,destroyed}
                         # | return_word_changed | closure_changed
    band: str
    pieces: tuple[str, ...]
    before: Mapping[str, object]
    after: Mapping[str, object]

@dataclass(frozen=True, slots=True)
class Quote:
    edit: Edit
    base_rev: str
    epoch: EpochKey
    stage: int                               # 1: E2/E3 screen; 2: exact (E1)
    deltas: Mapping[str, Belief]             # budget -> change
    lam: np.ndarray                          # edit spectrum
    r: float                                 # max |lam|; first order is safe only for r << 1
    events: tuple[TopoEvent, ...]
    cost: Mapping[str, float]                # mm2, vias, fab class

# ledger: passports/<band>.npz holds pieces (P,), budgets (K,), sources (S,), share (P,S) f4,
# attribution (P,K) c8, removal (P,K) c8, r (P,) f4, leverage (P,) f4, jobs (P,K) i1, scope;
# ledger.json holds the Beliefs they cite.
```

`Job`, `Passport`, `Mode`, `Floor`, `RegimeCell` and `ClosedLoopBudget` keep the fields of [physics-core-v2-api](../physics/physics-core-v2-api.md) §2, with ids replacing embedded objects.

### B. Algorithms and update rules

**Quotes (K4).** For an edit removing branches B (incidence A_B, admittances y_B) with port injections U = Y⁻¹E:
- S_B = A_Bᵀ·Y⁻¹·A_B; ΔZ = Vᵀ(diag(1/y_B) − S_B)⁻¹V with V = A_BᵀU; λ = eig(diag(y_B)·S_B); r = max|λ|.
- An addition of z between nodes m, n: ΔZ = −ΔφΔφᵀ/(z + Z_th), Z_th = aᵀY⁻¹a.
- Inside a window, every Y⁻¹ entry comes from G_W, so a quote needs no solve. A singular Woodbury matrix is a K1 event (λ = 1): infinite if a terminal is cut off, finite if copper merely floats.

**Windows.**
- K_W = Y_WW − Y_WR·Y_RR⁻¹·Y_RW is the trailing block L_WW·L_WWᵀ of a factorization ordered R (by AMD), then W; it is pivot-free and agreed with the boundary-solve form to 5×10⁻¹⁴ on bms-c1 [C]. Sources outside W enter as ŝ_W = s_W − Y_WR·Y_RR⁻¹·s_R.
- A commit Y + A·D·Aᵀ inside W updates G' = G − GA(D⁻¹ + AᵀGA)⁻¹AᵀG and φ' = G'ŝ: 20–60 ms for rank 8 at |W| = 1,600, against 0.3–0.4 s to re-invert [C]. An edit outside W marks it stale; one factorization refreshes it.
- Default: 1,600–3,200 nodes on all layers (a 3 mm square at 0.1 mm, 6 mm at 0.2 mm, on 4 layers), |∂W| ≈ 190–260; larger regions take several windows.

**Global commits.** C = A_B·diag(√|y_B|) is a downdate (removal) or update (addition) of the Cholesky factor (Davis–Hager), touching only the columns on the edit's elimination-tree paths. The engine refactors numerically when the accumulated update flops exceed one refactorization. A K1 event changes the ground set, so it re-analyses (a new epoch).

**AC factorization (K2, K3).** Pivot-free LDLᵀ on the symmetric pattern, then one step of iterative refinement; if ‖Yx − b‖/‖b‖ still exceeds 10⁻¹⁰, refactor with threshold pivoting, which near-resonant bands may need. At the skeleton's 900 MHz anti-resonance, symmetric-mode SuperLU stayed within 4×10⁻¹¹ of refactoring ([physics-core-v2](../physics/physics-core-v2.md)) [C].

**Leverage.** M1 uses the 48-solve Johnson–Lindenstrauss sketch for every branch, plus exact values for loaded and series pieces ([real-board-passports](../physics/real-board-passports.md)). M4 computes Z = Y⁻¹ on the pattern of L by the Takahashi recurrences (column by column from the last), then ρ_b = y_b(Z_aa + Z_bb − 2Z_ab) for every branch; removals of pieces whose nodes share a supernode come from the same Z [I].

**Certificates (K5).** The primal φ with Dirichlet terminals overestimates conductance, and the dual stream function ψ (one unknown constant per hole) overestimates resistance; together they bracket R (Prager–Synge), and the element gap ∫_K |σ∇φ − J_ψ|²/σ drives refinement. The Beckmann bound R_s·W₁²/A and the Frank–Wolfe floor follow [vp_floors](../../../tools/research/physics/vp_floors.py).

**Modes (K6).** Reduce to ports and modes passively (PRIMA-type Krylov projection); solve the dense generalized eigenproblem; channel shares follow from Rayleigh quotients, 1/Q_k = x*R_k x/(ω·x*M x).

**Morphology (K7).** A signed exact Euclidean distance transform per tile gives the width map (2 × SDF on ridges), which sets both legality and cell size. Necks are ridge minima below w_min. Legalization uses Clipper offsets (close by the gap, then open by the width) and is accepted only if K1's invariants are unchanged or the change is intended.

**Beliefs (K8).** Var y = sᵀΣs, with Σ correlating inputs that share an idealization (lineage); inverse-variance fusion within a lineage class; EVPPI by nested Monte Carlo ([in_emi_voi](../../../tools/research/physics/in_emi_voi.py)).

### C. Discretization rules

**Strips.**
- Nodes sit at polyline vertices, at junctions with tracks, vias and pads, and at most every min(1 mm, 4w).
- A segment's conductance is w/(R_s·Δs).
- A sharp 90° bend's corner square counts 0.5587 squares, 0.441 below the centreline count ([vp_floors](../../../tools/research/physics/vp_floors.py) `bracket`).
- At a pad or pour, the end node links to the sheet nodes across the track width, each in proportion to its share of the width.

**Tiles.**
- Each 64 × 64 finest-cell tile holds a 2:1-balanced quadtree whose leaves span 1–16 finest cells; a leaf splits while h > w_local/3 or h > h_max.
- Coverage per triangle comes from exact clipping of the copper polygons (Clipper2).
- P1 edge weights are ½(cot α + cot β): ½ per leg of a right isosceles triangle, 0 across its hypotenuse.
- Hanging nodes are resolved by the standard right-isosceles templates, so every triangle stays non-obtuse.

**Vias and electrodes.**
- A barrel with r_w < h/2 joins each layer's nearest node by Peaceman's conductance; otherwise its annulus nodes are contracted into the barrel node.
- Pads with an equipotential terminal are contracted.
- Barrel segments carry ρ·l/(π(d + t)t) with plating t = 20 µm unless the stackup says otherwise.

**AC and HF grids.** The inductive-limit stack window keeps one grid across layers, with cells at most half the smallest gap; its outer-field thickness, which moved L by 14% in [real-board-passports](../physics/real-board-passports.md), goes into the scope. Telegrapher sheets use cells ≤ min(ℓ_m/2, λ/20); PEEC uses ≥ 31 graded filaments where w/h > 10 ([verification-and-limits](../physics/verification-and-limits.md)).

**Refinement study.**
- Each reported Belief is recomputed at h/2 inside its dirty window plus 2 mm.
- Value ± |Δ| becomes its discretization spread (E3 when the Richardson ratio is consistent, otherwise flagged).

**Sandwich bracket.**
- The inner raster holds only cells entirely inside the copper; the outer raster holds every cell touching it.
- R(outer, primal) ≤ R_true ≤ R(inner, dual) for self terms (Rayleigh plus Prager–Synge).
- On the annulus test it held at every resolution, with a width of 84% at 4 cells across, 39% at 8, 19% at 16, 9.4% at 32 and 4.7% at 64 [C].

**Boundary-fitted certificates.**
- A constrained Delaunay mesh of the budget's region (spade, MIT/Apache-2.0, or CGAL, GPL-3.0+) carries P1 primal and dual on the same mesh.
- It is refined by the element gap until the bracket is below the budget's margin divided by z.

### D. Licences

| Dependency | Use | Licence | Status |
|---|---|---|---|
| numpy | arrays | BSD-3-Clause (bundled 0BSD, MIT, Zlib, CC0) [C: metadata] | ship |
| SciPy | sparse, SuperLU, ARPACK, EDT | BSD-3-Clause [C] | ship |
| Shapely, GEOS | polygons | BSD-3-Clause [C]; LGPL-2.1+ [S] | ship |
| Clipper2 / pyclipper | robust offsets | BSL-1.0 / MIT [S] | ship |
| contourpy | contours for legalization | BSD-3-Clause [C] | ship |
| pyamg | AMG for large thermal models | MIT [C] | ship |
| scikit-rf | Touchstone, vector fitting | BSD-3-Clause | ship |
| scikit-sparse 0.5 | CHOLMOD bindings | BSD-2-Clause [C] | ship |
| CHOLMOD | factorization, up/downdate | Core, Cholesky, Partition LGPL-2.1+; Supernodal, Modify, MatrixOps GPL-2.0+ [S] | ship (GPL-3.0 combined) |
| AMD, CAMD, COLAMD | orderings | BSD-3-Clause [S] | ship |
| METIS 5.x | nested dissection | Apache-2.0 [S] | ship |
| OpenBLAS | dense kernels | BSD-3-Clause [S] | ship |
| faer, gemm, pulp, dyn-stack | Rust factorization | MIT [C: Cargo.toml] | ship (`kae-fast`) |
| PyO3, rayon | bindings, threads | MIT or Apache-2.0 [C for rayon] | ship |
| spade or CGAL 2D | constrained Delaunay | MIT or Apache-2.0 / GPL-3.0+ [S] | ship |
| MUMPS | complex symmetric LDLᵀ with Schur output, if adopted | CeCILL-C [S] | ship |
| JAX | placement kernels, surrogates | Apache-2.0 | ship |
| ngspice, Xyce, openEMS, Palace, FasterCap, PyPEEC | external engines | per [open-solvers](../physics/open-solvers.md) | ship or subprocess |
| FastHenry | calibration decks | non-commercial notice | internal only |
| Ki-PIDA, Konnect | reference | AGPL-3.0 | reference only |
| Triangle (Shewchuk), `triangle`, `meshpy` | — | non-commercial clause [S] | excluded |
| MKL PARDISO, pypardiso | — | proprietary | excluded |
| NVIDIA cuDSS | — | proprietary | excluded |

### E. Correctness

| Level | Test | Tolerance | Measured [C] |
|---|---|---|---|
| E1 algebra | Woodbury, Thevenin, Tellegen, Foster against refactoring, 1,000 random edits per operator kind (DC, thermal, stack inductance, telegrapher, PEEC mesh) | c·ε·κ (κ from `rcond`); 10⁻¹⁰ after contraction | window vs direct 7×10⁻¹⁶–9×10⁻¹⁵; window commit vs refactoring 4×10⁻¹³–8×10⁻¹¹; up/downdate vs SuperLU 2×10⁻¹¹–10⁻⁹ |
| E0 events | λ = 1 at every K1 disconnect of a grown cut; discretization islands and holes equal the polygons' | exact | skeleton λ = 1.00000 |
| E2 bounds | DC first-order bounds on all tile removals; brackets contain closed forms (annulus, L-bend 0.5587, notched strip) | never violated | 0/444 and 0/296; 5/5 resolutions |
| E3 forms | Peaceman 0.1985; strip over a plane μ0hl/w; via pair in a plate pair; complex images; cut law | 10⁻³; 0.7%; 5×10⁻⁵; 3.5%; 6 digits | 0.1985 |
| Goldens | `rt_*` scripts frozen; they never import `kae` | as registered | — |
| Refinement | h → h/2 on every regression board | change inside the reported spread | — |
| Metamorphic | lattice-step translation and 90° rotation leave Beliefs within 10⁻⁹; mirror symmetry; Z_qp = Z_pq to 10⁻¹²; doubling copper thickness halves R; a floating island changes nothing | as stated | — |
| Mutation | planted DRC-neutral faults (≥ 8 operators, ≥ 50 boards) move a job verb or binding Belief by more than its spread; benign twins do not | recall ≥ 90%, false alarms ≤ 5% (build plan) | 31/31 and 0/7 ([physics-critics](../physics/physics-critics.md)) |
| Cross-solver | FastHenry (internal), padne and KiPI (DC), openEMS or Palace slices | recorded as model-form spread | PEECN vs FastHenry 1.3% |

**Calibration as Beliefs.** A measurement is a record (coupon or board id, instrument, uncertainty, conditions). A calibration model per (stackup, fab, structure class) holds a bias and a conformal residual spread over the measured features (w/h, f/f_x, ℓ/ℓ_m). Applied to an E1 or E3 value it yields an E4 Belief whose lineage names scope and calibration, valid inside the hull of those features; outside, the raw Belief is reported with validity "out" and its model-form spread. Registered predictions ([validation-program](../physics/validation-program.md)) are scored against the same records.

### F. API

```python
class PhysicsSession:                        # one per board, inside the session server
    @classmethod
    def open(cls, snap: SnapshotView, intent: Intent, bands: Sequence[Band],
             cfg: EngineConfig) -> "PhysicsSession": ...
    rev: str
    epoch: EpochKey
    # optimizer: in-process, batched, incremental
    def window(self, region: Box | Sequence[str], bands: Sequence[str]) -> WindowModel: ...
    def screen(self, edits: EditBatch) -> QuoteBatch: ...         # stage 1: E2/E3 screens, µs
    def quote(self, edits: EditBatch, stage: int = 2) -> QuoteBatch: ...
    def commit(self, cand: Candidate) -> CommitResult: ...        # refused unless cand.base_rev == rev
    def evaluate(self, terms: Sequence[str], grad: bool = True) -> Evaluation: ...
    # critics and reports
    def value(self, budget: str, band: str) -> Belief: ...
    def bracket(self, budget: str, band: str) -> Belief: ...     # E2, boundary-fitted
    def passports(self, band: str, pieces=None, budgets=None) -> PassportTable: ...
    def floors(self, budgets=None) -> list[Floor]: ...
    def events(self, since: str | None = None) -> list[TopoEvent]: ...
    def modes(self, scope: str, band: str) -> list[Mode]: ...
    def regime(self, structure: str, band: str) -> RegimeCell: ...
    def views(self) -> BoardPhysicsModel: ...                    # reference map, planes, via spans
    # LLM and humans: read-only facade of physics-core-v2-api §4
    def why_here(self, piece: str) -> list[Job]: ...
    def what_if(self, edit: Edit) -> Quote: ...
    def where_add(self, kind: str, budget: str, region=None, k: int = 10) -> list[Quote]: ...
    def explain(self, budget: str) -> Explanation: ...
    def menu(self, budget: str) -> list[Quote]: ...
    def binding(self) -> list[BindingRow]: ...
    def unknowns(self) -> list[VoiRow]: ...

class WindowModel:                           # held by an optimizer worker
    def quote_batch(self, edits: EditBatch) -> QuoteBatch: ...   # deltas (E, K), r (E,), events (E,)
    def commit(self, edit: Edit) -> None: ...                     # rank-k update of G, phi, lead
    def refresh(self) -> None: ...                                # one factorization, W last
```

`EditBatch` packs edits as padded branch-index arrays with admittance changes, so a batch is one vectorized expression; `QuoteBatch` is a columnar Belief container (one exactness, scope and lineage per column), so arrays cross the package boundary as Beliefs. `CommitResult` carries the new `rev`, events, passport diffs and whether the epoch changed. Physics actors answer `solve`, `schur`, `updown`, `refactor` and `passports` messages keyed by (operator, band, epoch) and refuse stale revisions.

## Recommendations for our system

1. Freeze these types as schema v0 in M0, with the `.npz` passport layout documented in `schemas/`.
2. Implement `Factorization` for SuperLU and CHOLMOD first, and test both against each other on every regression board.
3. Make the E-level matrix of §E the CI gate for `kae.physics`.

## Conflicts and open questions

- **Untested on real boards:** stream-function duals on copper with holes (one unknown constant per hole), and selected inversion for multi-node pieces, which relies on supernodes aligned with tiles [I].
- **Licences tagged [S]** must be re-checked at the M0 licence gate.

## Sources

- [C]: [eng_board_scaling](../../../tools/research/physics/eng_board_scaling.py), [eng_window_schur](../../../tools/research/physics/eng_window_schur.py), [eng_compiled_cholesky](../../../tools/research/physics/eng_compiled_cholesky.py), [eng_discretization](../../../tools/research/physics/eng_discretization.py); [pc2_core_skeleton](../../../tools/research/physics/pc2_core_skeleton.py); [rb_board_passports](../../../tools/research/physics/rb_board_passports.py).
- [S]: Davis and Hager (1999), up/downdate; Takahashi, Fagan, Chin (1973), selected inversion; Peaceman (1978), wells; Prager and Synge (1947), brackets; Odabasioglu, Celik, Pileggi (1998), PRIMA; Felzenszwalb and Huttenlocher (2012), distance transforms.

See also: [physics-engine-design](physics-engine-design.md) · [system-design](system-design.md) · [physics-core-v2-api](../physics/physics-core-v2-api.md) · [open-solvers](../physics/open-solvers.md) · [verification-and-limits](../physics/verification-and-limits.md)
