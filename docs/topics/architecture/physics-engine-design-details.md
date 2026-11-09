# Physics engine design, details: types, API, licences, tests, build order

Scope: reference for the `kae.physics` engine: frozen types, `PhysicsSession` API, dependency licences, correctness matrix, calibration, build order E0–E5. Design rationale, algorithms and measured costs -> [physics-engine-design](physics-engine-design.md).
Keys: Exactness E0–E5, Belief, EpochKey, ModelScope, DirtyRegion, Piece, WorldConductor, Discretization, Operator, Factorization protocol, WindowModel, Edit, TopoEvent, Quote, passports .npz, ledger.json, PhysicsSession, EditBatch, QuoteBatch, CommitResult, physics actors, licence gate, CHOLMOD licence, faer, Triangle excluded, cuDSS, correctness matrix, metamorphic tests, mutation benchmark, calibration, E4 Belief, schema v0, build order E0–E5

Tags as in [physics-engine-design](physics-engine-design.md).

## Types

Freeze these as schema v0 in M0, with the `.npz` passport layout documented in `schemas/`. Belief and Exactness live in `kae.units`, the rest in `kae.physics`: frozen dataclasses for epochs, scopes, pieces, edits, quotes, events; arrays for discretizations, operators, windows; `.npz` tables for passports.

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

`Job`, `Passport`, `Mode`, `Floor`, `RegimeCell`, `ClosedLoopBudget` keep the fields of [physics-core-v2-api](../physics/physics-core-v2-api.md) §2, with ids replacing embedded objects.

Implement `Factorization` for SuperLU and CHOLMOD first and test both against each other on every regression board.

## API signatures

One `PhysicsSession` per board inside the session server ([system-design](system-design.md) §2) serves three clients; every return is a Belief or a container of them. LLM and human calls are the read-only facade of [physics-core-v2-api](../physics/physics-core-v2-api.md) §4, answered from caches and stamped with `board_rev`, epoch and scope ids.

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

- `EditBatch`: edits as padded branch-index arrays with admittance changes, so a batch is one vectorized expression.
- `QuoteBatch`: columnar Belief container (value arrays per budget sharing one exactness, scope and lineage per column), so arrays cross the package boundary as Beliefs at array speed.
- `CommitResult`: new `rev`, events, passport diffs, whether the epoch changed.
- Critics and reports read `passports` as `.npz` tables plus board-physics-model `views`.
- Physics actors answer `solve`, `schur`, `updown`, `refactor`, `passports` messages keyed by (operator, band, epoch) and refuse stale revisions.

## Licences

Every dependency is GPL-3.0-compatible or kept out of shipped code. Re-check rows tagged [S] at the M0 licence gate.

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

## Correctness matrix

Make this E-level matrix the CI gate for `kae.physics`. Every kernel has an independent check.

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

## Build order E0–E5

| Step | Build | Accept when |
|---|---|---|
| E0 (M0) | `units` Belief, ModelScope; physics types; K1 on polygons; K4 on a generic operator; contraction | identities within 10⁻¹⁰ of refactoring on 1,000 random edits (skeleton; c·ε·κ on BLDCM-Power); λ = 1 exactly at disconnects; DC bounds hold; metamorphic tests to 10⁻⁹ |
| E1 (M1) | DC and thermal builder: strips, P1 tiles, wells, linear assembly; CHOLMOD backend | removal quotes within 10⁻⁹ of brute force on 3 real boards; annulus inside its bracket and within 0.5%; via well within 1%; islands equal K1's on 112/112 boards |
| E2 (M1) | passports (`.npz`), leverage, K5; HF stack window; Schur windows | [real-board-passports](../physics/real-board-passports.md) reproduced within 1%; scorecard median ≤ 2, p90 ≤ 10 CPU-min, ≤ 4 GB on ≥ 106/112 boards |
| E3 (M2) | complex K2 with residual check; K6; merged K3; physics actors | f_p within 2% of ls_post_lattice; Q = h/δ; K3 within 3.5% of ls_thin_sheet and 1.3% of PEECN; `what_if` ≤ 50 ms p95; refresh ≤ 2 s p95 |
| E4 (M2–M3) | K7 legalizer; K8; boundary-fitted brackets | vp_floors and in_emi_voi reproduced; legalization keeps K1 invariants; brackets contain closed forms |
| E5 (M4) | `kae-fast`: faer, quote kernel, rasterizer, selected inversion | rank-1 quote ≤ 2 µs; build ≤ 2 s per million copper cells; exact leverage of every branch in ≤ 3 factorizations' time |

## Sources

- [C]: [eng_board_scaling](../../../tools/research/physics/eng_board_scaling.py), [eng_window_schur](../../../tools/research/physics/eng_window_schur.py), [eng_compiled_cholesky](../../../tools/research/physics/eng_compiled_cholesky.py), [eng_discretization](../../../tools/research/physics/eng_discretization.py); [pc2_core_skeleton](../../../tools/research/physics/pc2_core_skeleton.py); [rb_board_passports](../../../tools/research/physics/rb_board_passports.py).
- Related: [open-solvers](../physics/open-solvers.md), [verification-and-limits](../physics/verification-and-limits.md).
