# Physics core v2 API: types, kernel protocols, facade, IR changes

**TL;DR**
- **Three layers.** Types (Piece, WorldConductor, Passport, Job, ClosedLoopBudget, Belief, Quote, TopoEvent, RegimeCell, Mode, Floor); eight kernel protocols over one `Operator`/`Factorization` protocol; and a `PhysicsCore` facade with read-only queries for the LLM and humans and an edit interface for the optimizer.
- **Every return is a Belief** or a container of Beliefs, each with an exactness class and a `relative_to` model. Edits are quoted before they are committed; a commit returns topological events and passport diffs.
- **One operator protocol serves all physics.** Anything that exposes incidence, branch admittances and a solve can be priced by the response kernel: sheets, PEEC in mesh form, thermal networks, circuit MNA, harmonic-balance conversion matrices.
- **pcb-intent 0.4** adds `world`, `symmetry`, `hypotheses`, loop-named budgets and criticality to `intent.yaml`, and pieces, passports, jobs, beliefs, events, regimes, modes, floors, quotes and VOI to `ledger.json`. It deprecates net × layer bodies as the physics unit, `mech`-keyed allocation, two-point AC voltage budgets and point LII.
- **The skeleton runs.** [pc2_core_skeleton.py](../../../tools/research/physics/pc2_core_skeleton.py) implements a subset (operator, quotes, attribution, leverage, events, passport, `why_here`, `what_if`, `explain`, `where_add`); its identities match re-factorization to ≤ 4×10⁻¹¹ [C].

Tags: [C] computed by the skeleton on the 30 × 20 mm plane pair of [physics-core-v2](physics-core-v2.md); [I] inference. The design rationale is in that doc.

## Key facts

### 1. Rules the API enforces

1. **No bare numbers.** Everything is a `Belief` with exactness E0–E5 and the model it is exact relative to.
2. **Stable ids, private meshes.** Pieces, budgets, modes and events have ids; meshes are disposable.
3. **Quote, then commit.** Queries never mutate. Edits are quoted at stage 1 (screens) or stage 2 (exact). A commit returns events and passport diffs and bumps the epoch at topological events.
4. **Budgets name loops.** The validator refuses an AC voltage budget without a closed observation loop.
5. **Class by code.** A, A′, B, C, D or L is computed per (budget, band). Explanations follow it: attribution when χ ≥ 0.5, counterfactuals otherwise.
6. **The world is first class.** Unknown world facts are E5 Beliefs ranked by VOI, and the core asks about them.
7. **Pure kernels.** Kernel results depend only on (model, epoch) and are cached by geometry hash, stackup, band and epoch.
8. **A narrow write surface for the LLM:** hypotheses, allocations, menu choices, declarations and world facts.

### 2. Types

```python
class Exactness(IntEnum):
    E0_TOPOLOGICAL = 0; E1_ALGEBRAIC = 1; E2_CERTIFIED = 2
    E3_ASYMPTOTIC = 3; E4_CALIBRATED = 4; E5_CONJECTURED = 5

@dataclass(frozen=True)
class Belief:
    """Every number the core returns."""
    value: complex
    unit: str
    exactness: Exactness
    relative_to: str                  # model id: kernel, mesh, assumptions, epoch
    interval: tuple | None = None     # E2: guaranteed relative_to; E4: calibrated coverage
    spread: dict | None = None        # model-form sigma split {"level": b, "shape": u}
    validity: str = "in"              # in | edge | out of the model's domain
    lineage: tuple[str, ...] = ()     # kernels and input beliefs; shared idealizations correlate

PieceId = str   # "GND.In1.t(26,14)", "via:GND:U3.7/2", "world:heatsink1"

@dataclass
class Piece:
    id: PieceId
    net: str
    layer: str
    kind: str          # track | pad | via | pour_tile | plane_tile | part_body | world
    geometry: str      # polygon or raster-window handle; the mesh stays private
    designed: dict[str, bool] = field(default_factory=dict)   # per job verb

@dataclass
class WorldConductor(Piece):
    role: str = "chassis"   # chassis | cable | heatsink | enclosure | earth | test_setup
    facts: dict[str, Belief] = field(default_factory=dict)    # C_ext, Z_cm(f), bonds; E5 until known

@dataclass(frozen=True)
class Band:
    name: str
    f_lo: float
    f_hi: float
    f_eval: tuple[float, ...]   # evaluation frequencies; 0 = DC
    spectra: str                # source spectra for spectrum-weighted metrics

@dataclass
class RegimeCell:
    structure: str
    band: str
    numbers: dict[str, float]   # lm/h, lm/a, lm/W, theta, Z0/Z, omega*tau_e, f/f_p, r
    representation: str         # sheet_R | sheet_complex | peec_complex_image | peec_meshed
                                # | line | modal | cosim | fullwave

@dataclass
class ClosedLoopBudget:
    id: str
    loop: tuple[str, ...]       # the victim's terminals plus the pieces that close its loop
    sources: tuple[str, ...]    # aggressor ports, or ("*",) for every source of a class
    metric: str                 # R | L | |Z| | V_spec | dT | Q | J_max | E_max | life
    bound: Belief
    bands: tuple[str, ...]
    criticality: float = 0.16   # c/L: escalation cost / wrong-accept cost -> z
    cls: dict[str, str] = field(default_factory=dict)   # per band: A, A', B, C, D, L (code)

@dataclass
class Job:
    verb: str          # carries | returns | images | lowers | raises | senses | anchors
                       # | spreads_heat | holds_charge | damps | radiates | bonds | shields | dead
    objects: tuple[str, ...]    # budgets, modes or world conductors
    band: str
    delta: Belief               # the exact counterfactual behind the verb
    value: float                # sum_k price_k * |dB_k| / slack_k
    designed: bool = False

@dataclass
class Passport:
    piece: PieceId
    band: str
    epoch: int
    topo_role: frozenset[str]   # bridge, shared_edge, chord, dead_end, ring, handle, cut_member, linked
    share: dict[str, Belief]    # source -> current through the piece
    kappa: dict[str, float]     # transport vs circulation
    charge_to: dict[str, float] # own return, victims, world
    energy: dict[str, Belief]   # stored E and M, dissipated, radiated share
    removal: dict[str, Belief]  # budget -> exact change if removed
    r: float                    # Woodbury radius of that removal; 1 = event at DC
    damping: dict[str, float]   # mode -> Q_m / Q_m,piece
    regime: RegimeCell
    jobs: list[Job]

@dataclass
class TopoEvent:
    kind: str   # disconnect | float_island | cycle_created | cycle_destroyed | hole_created
                # | hole_destroyed | bridge_created | return_word_changed | closure_changed
    band: str
    pieces: tuple[PieceId, ...]
    before: dict
    after: dict

@dataclass
class Edit:
    kind: str   # remove | add | cut | widen | add_via | add_part | move_part | reroute | stackup | eco
    target: tuple[str, ...]
    params: dict

@dataclass
class Quote:
    """What an edit would do, before anything changes."""
    edit: Edit
    stage: int                    # 1: E2/E3 screens; 2: exact (E1)
    deltas: dict[str, Belief]     # budget -> change
    r: float                      # first-order is safe only where r << 1
    events: list[TopoEvent]
    cost: dict[str, float]        # mm2, vias, BOM, fab class
    cpu_s: float

@dataclass
class Mode:
    id: str
    s: complex                    # complex frequency
    q: float
    channels: dict[str, float]    # 1/Q = sum 1/Q_k over copper, dielectric, devices, dampers, radiation
    participation: dict[PieceId, float]

@dataclass
class Floor:
    budget: str
    value: Belief                 # E2
    kind: str                     # beckmann | convex | capacity | hs | cavity | fab
    certificate: object           # the dual potential or trial field that proves it
    tau: float                    # bound / floor; < 1 is infeasible: an ECO question
```

### 3. Kernel protocols

```python
class Operator(Protocol):
    """Any linear(ized) reciprocal operator: sheet, PEEC (mesh form), thermal, MNA, HB."""
    n: int
    def incidence(self, branches: np.ndarray): ...         # sparse n x k
    def admittance(self, branches: np.ndarray): ...        # diagonal, or a dense block if coupled
    def factor(self) -> "Factorization": ...

class Factorization(Protocol):
    epoch: int
    def solve(self, rhs: np.ndarray) -> np.ndarray: ...
    def green_block(self, nodes: np.ndarray) -> np.ndarray: ...  # (Y^-1)[nodes, nodes] for hot windows

class Topology(Protocol):                                  # K1, exact (E0)
    def invariants(self, band: str) -> dict: ...           # b0, b1, blocks, holes, closure types
    def return_word(self, net: str, band: str) -> tuple[str, ...]: ...
    def events(self, edit: Edit) -> list[TopoEvent]: ...   # predicted before applying
    def check_symmetry(self, decl: dict) -> Belief: ...

class Sheet(Protocol):                                     # K2
    def build(self, layers: list[str], band: Band) -> Operator: ...
    def bracket(self, budget: str) -> Belief: ...          # phi and psi conforming solves (E2)
    def modes(self, region: str, k: int) -> list[Mode]: ...

class Peec(Protocol):                                      # K3
    def build(self, pieces: list[PieceId], band: Band, images: int = 6) -> Operator: ...
    def capacitance(self, world: bool = True) -> dict: ...  # incl. C_ext
    def reduce(self, ports: list[str]) -> str: ...         # passive SPICE subcircuit

class Response(Protocol):                                  # K4, on any Factorization
    def state(self, f, sources: list[str]) -> np.ndarray: ...
    def adjoint(self, f, budget: str, periodic: tuple | None = None) -> np.ndarray: ...
    def lead_field(self, f, budget: str) -> np.ndarray: ...
    def attribution(self, f, budget: str) -> tuple[dict[PieceId, Belief], float]: ...  # and chi
    def quote(self, f, edit: Edit, stage: int = 2) -> Quote: ...
    def leverage(self, f, method: str = "sketch", k: int = 48) -> dict[PieceId, Belief]: ...
    def foster_residual(self, f) -> float: ...

class Floors(Protocol):                                    # K5
    def floor(self, budget: str, kind: str = "best") -> Floor: ...

class Modes(Protocol):                                     # K6
    def ledger(self, scope: str, band: str) -> list[Mode]: ...
    def r_estimate(self, edit: Edit) -> float: ...         # eps*Q, no solves
    def classify(self, budget: str, band: str) -> str: ...
    def damper_menu(self, mode: str) -> list[Quote]: ...

class Morphology(Protocol):                                # K7
    def legalize(self, field, rules: dict): ...
    def etch_corners(self, geometry, sigma_um: float) -> tuple: ...
    def critical_area(self, geometry, defects: dict) -> Belief: ...

class BeliefEngine(Protocol):                              # K8
    def propagate(self, inputs: dict[str, Belief], sens: dict[str, complex]) -> Belief: ...
    def fuse(self, beliefs: list[Belief]) -> Belief: ...   # lineage-aware
    def voi(self, decision: str) -> dict[str, float]: ...  # EVPPI per cost; robustify included
    def escalate(self, budget: str) -> bool: ...           # margin < z*sigma, z = Phi^-1(1 - c/L)
```

### 4. The facade

```python
class PhysicsCore:
    """One board and its world, bands, factorizations (per operator, band, epoch) and caches."""
    def __init__(self, board: str, intent: str, stackup: str): ...
    # read-only queries: LLM and humans
    def passport(self, piece: PieceId, band: str) -> Passport: ...
    def why_here(self, piece: PieceId) -> list[Job]: ...           # jobs by value, all bands
    def what_if(self, edit: Edit, stage: int = 2) -> Quote: ...      # "what breaks if I cut here?"
    def where_add(self, kind: str, budget: str, region=None, k: int = 10) -> list[Quote]: ...
    def explain(self, budget: str) -> dict: ...                     # attribution or counterfactuals
    def menu(self, budget: str) -> list[Quote]: ...                  # operators priced on all binding budgets
    def binding(self) -> list[dict]: ...                             # tau, margin, P(pass), multiplier
    def regime(self, structure: str, band: str) -> RegimeCell: ...
    def unknowns(self) -> list[dict]: ...                            # VOI-ranked asks and measurements
    # the optimizer
    def evaluate(self, terms: list[str], grad: bool = True) -> dict: ...  # values, grads by class, trust radius
    def commit(self, edit: Edit) -> tuple[list[TopoEvent], list[dict]]: ...  # events, passport diffs
```

### 5. Worked exchange on the test board [C]

What the LLM reads for the Kelvin-tap budget:

```yaml
budget: Z_SA@DC      # what the tap pair reads per ampere drawn by load A
value: {v: 110.4 uOhm, exactness: E1, relative_to: "M:DC-sheet-0.5mm-e0"}
class: B             # chi = 0.48 -> counterfactual explanations only
counterfactuals:     # exact removals
  - {piece: PWR.t07.05, delta: +46.6%}   # tile beside the slot tip
  - {piece: PWR.t09.05, delta: +31.8%}
menu:
  - op: bridge                   # 0.5 mm copper bridge across the slot at y = 16.75 mm
    deltas: {Z_SA: -24.5%, Z_AA: -7.9%, Z_BA: -8.6%}   # stage 2, exact Thevenin
    r: 1.75                      # DC addition: first-order over-promises 2.75x
    events: [hole_created]       # K1 (geometric): the slot below the bridge closes into a hole
  - op: extend_slot              # zero-width cut down to y = 6 mm
    deltas: {Z_SA: +39.2%, Z_AA: +37.1%, Z_BA: +47.9%}  # first-order price: +2.4%
    r: 0.955
    events: []
```

The `hole_created` event matters at AC: a closed hole carries a circulation driven by the flux through it, a potential shorted turn ([lens-ct](lens-ct.md) CT-P5). K1's hole count (the copper's Euler characteristic) would flag it before anyone commits the bridge; the skeleton's K1 checks only connectivity and bridges, so this event is stated [I], not computed.

What the LLM writes back:

```yaml
hypotheses:
  - id: H1
    mechanism: "A's current crowds through the neck under the slot tip; the taps straddle it"
    prediction: {observable: Z_SA@DC, after: bridge@16.75, interval: [75, 90] uOhm}
    discriminator: "what_if(remove PWR.t07.05) above +30% supports H1"
choices: [{op: bridge, at: slot@16.75, because: [H1], accepts_events: [hole_created]}]
```

A human asks, and the answers come straight from passports and quotes:
- `why_here(PWR.t07.05)` → "DC: lowers coupling Z_SA, +46.6% without it (exact), 1.86 × slack; lowers Z_BA, +17.5%; carries Z_AA, +15.2%."
- `why_here(C3)` → "300 MHz: lowers Z_BA, +25.5% without it; raises Z_SA, −19.0%; carries Z_AA, +12.4%." That is a job conflict.
- `what_if(cut to y = 0)` → "infinite at DC: disconnects A, B and S (K1); +27% at 300 MHz, where the right half floats on displacement current."

### 6. Changes to pcb-intent: 0.3 → 0.4

| Place | Add | Change | Deprecate |
|---|---|---|---|
| `intent.yaml` `physics` | `world` (world conductors, known facts, open asks); `symmetry` declarations ([SY13](../../ideas/physics-first/lens-sy.md)); `hypotheses` with registered predictions ([IN31](../../ideas/physics-first/lens-in.md)); `criticality` (c/L) per budget | budgets name a `loop`: a port plus its closure. `designed` applies per (piece or entity, job) | `mech` as an allocation key (explanation only); `alloc` on class-B budgets |
| `intent.yaml` `ops` | `damp`, `bond`, `close_locally`, `separate_jobs`, `bury_victim`, `antiphase_pair`, `designed_cut`, `set_fp` | `expect` comes from stage-2 quotes, with r and events | sign-only effect cards |
| `ledger.json` | `pieces`, `passports` (sparse, per band and epoch), `jobs`, `beliefs`, `events`, `regimes`, `modes`, `floors` (with τ and certificates), `quotes`, `voi` | every number is a Belief; LII is reported as P(LII ≤ 1) | point LII; spender bars on interaction budgets |
| Validator | refuse AC voltage budgets without a closed loop and `alloc` on class-B budgets; require provenance on world facts | — | — |
| Bands | regime cells per structure (code) | `bands` stay named intervals | the fixed band-edge table; a single f_x |

### 7. Vocabulary changes

| Add | Why |
|---|---|
| **Piece** (below Body) | The physics unit; Body becomes a view, the union of a net's pieces on one layer ([lens-cd](lens-cd.md)) |
| **World conductor** (atom) | Chassis, cable, heatsink, enclosure, earth or LISN, test setup carry CM physics and most VOI ([lens-ct](lens-ct.md), [lens-in](lens-in.md)) |
| **Passport, Job** (value types) | Observed relations become signed, share-valued and counterfactual. `carries` and `returns_through` stop being booleans |
| **Closed-loop budget** | A Budget gains a loop and a class per band ([lens-sy](lens-sy.md) P5, [lens-ct](lens-ct.md) D4) |
| **Belief, Exactness** | Every quantity states what it is exact relative to ([lens-in](lens-in.md), [lens-vp](lens-vp.md)) |
| **Mode** | Extends Cavity and Res with complex frequency and a Q ledger ([lens-th](lens-th.md)) |
| **Regime cell** | Regime gains scales: the ℓ–f plane replaces labels ([lens-ls](lens-ls.md)) |
| **Event, epoch, floor, closure type, symmetry declaration** | Topology and bounds become first-class ([lens-ct](lens-ct.md), [lens-vp](lens-vp.md), [lens-sy](lens-sy.md)) |
| **Operators** `damp`, `bond`, `close_locally`, `separate_jobs`, `bury_victim`, `antiphase_pair`, `designed_cut`, `set_fp` | Lens levers that 0.3 has no operator for |

Deprecate or demote:
- Body as the physics unit (it stays a geometry handle);
- `mech` as a budget key;
- "voltage between two points" at AC;
- designed/parasitic per structure;
- Regime as a label;
- f_x as one boundary.

The twelve atoms stay as the language of intent; pieces and jobs are the language of observation.

## Recommendations for our system

1. Turn the skeleton into a package: the types, `GraphOperator`, K4 and K1 first, with its checks as unit tests.
2. Ship the 0.4 validator before any optimizer reads budgets; the loop rule catches the commonest gauge errors.
3. Give the LLM thin tools over the facade (`why_here`, `what_if`, `where_add`, `explain`, `menu`, `binding`, `unknowns`), each returning Beliefs; no geometry tools.
4. Version `ledger.json` by epoch so passports diff; raise role-change alarms on commits.
5. Keep E1 counterfactuals and E2 brackets in separate fields; let verdicts choose.

## Conflicts and open questions

- **Piece ids under big edits.** Reroutes and part moves remap tiles; ids anchored to net, layer and nearest feature need an overlap-based matcher, or passport diffs will misattribute.
- **Ledger size.** Passports are pieces × bands × budgets. Store only binding budgets and jobs above threshold, and recompute the rest on demand.
- **Coupled branches.** For PEEC, `admittance()` returns dense blocks and K4 works in mesh form; the nodal skeleton does not test this path ([lens-cd](lens-cd.md) did).
- **Class boundaries.** K6's one-dominant-energy test needs a threshold, and bands near resonances may flip class between epochs.
- **Periodic adjoints** depend on a harmonic-balance operator that does not exist in open SPICE yet.

## Sources

- [pc2_core_skeleton.py](../../../tools/research/physics/pc2_core_skeleton.py) [C].
- Contracts this extends: [physics-ir](physics-ir.md), [vocabulary](vocabulary.md), the evaluator contract in [solver-ladder](solver-ladder.md), the critic contract in [physics-critics](physics-critics.md).

See also: [physics-core-v2](physics-core-v2.md) · [lens-cd](lens-cd.md) · [lens-ct](lens-ct.md) · [lens-in](lens-in.md) · [physics-ir-examples](physics-ir-examples.md) · [design-reasoning-architecture](design-reasoning-architecture.md)
