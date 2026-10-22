# Physics IR: schema, compilation targets, who writes what (`pcb-intent/0.3`)

**TL;DR**
- `pcb-intent/0.3` is `0.2` plus four top-level keys: `bands`, `symbols`, `physics` (typed entities from the [vocabulary](vocabulary.md)) and `ops` (an operator plan). Every `0.2` file stays valid. Physics entities *expand to* `0.2` constraints, so the existing `.kicad_dru` emitter and checkers keep working [I].
- Intent and evidence live in two files. `intent.yaml` holds what is *required* (written by detectors, the LLM and humans, with provenance). `ledger.json` holds what is *observed* (written only by code: the physics graph, regimes, budget spend, attribution). Critics diff the two.
- Every number is a dimensioned quantity or an expression over named symbols (I2). The validator refuses bare numbers, unit mismatches, ports without a reference terminal, open loops, and couplings whose mechanism cannot act on the victim.
- The LLM writes requirements, allocations, mechanism hypotheses and operator choices. It never writes geometry, regimes, spend or coordinates. Code drafts most entities from the schematic, IBIS, datasheets and simulation [I].
- One entity compiles to up to six targets: KiCad objects, `.kicad_dru` rules, placer terms, router costs, checkers, and solver/simulator decks (our PEEC, FasterCap, openEMS, ngspice, thermal; FastHenry decks only for internal calibration, see its licence in [open-solvers](open-solvers.md)).

## Key facts

### File layout and versioning

| File | Writer | Content |
|---|---|---|
| `intent.yaml` (`schema: pcb-intent/0.3`) | detectors, LLM, human; provenance on every entity | `tags`, `selectors`, `topologies`, `constraints` (unchanged from [0.2](../architecture/constraint-ir.md)), plus `bands`, `symbols`, `physics`, `ops` |
| `ledger.json` | code only | per-entity observed values, per-(structure, band) regime, budget spend with per-object attribution, model id and trust radius (V4), findings, and the layout invisibility index (max spend ÷ budget over outputs, [schematic-to-physics](schematic-to-physics.md)) |
| `stackup.yaml`, layout cards | code + human | symbol bindings: h, εr, Df, copper weight; part facts (V_abs, C_oss, pin roles) ([part-layout-card](../llm/part-layout-card.md)) |

Unknown keys are refused (KRT-style). Entity ids are stable hierarchical names (`buck1.hot`), so intent diffs (I6) and stamps in the board file (I7) key on them.

### Value grammar (extends I2)

```
quantity  := number unit                       # "1.2 nH", "5 mil", "0.3 uV"
bound     := ("<=" | ">=" | "==") (quantity | expr)
interval  := "[" quantity "," quantity "]"     # min/max, IBIS-style typ optional: {min, typ, max}
expr      := arithmetic over quantities and symbol calls, e.g.
             "0.85*V_abs(U3.VIN) - V_max(VIN)", "tr(buck1.sw)/6*vp(F.Cu)", "LSB(U9)"
```

- Units: SI with prefixes, plus `mil`, `oz`, `dB`, `dBm`, `ppm`, `degC`, `%`. Dimensions are checked (pint-style); `dB` budgets must name the quantity they are a ratio of (`IL`, `S11`, `margin`).
- `symbols:` binds or overrides facts locally with provenance, e.g. `{"tr(buck1.sw)": 2 ns}`. Symbols resolve lazily: stackup (`h(F.Cu,In1.Cu)`, `er(...)`, `vp(layer)`), parts (`V_abs(pin)`, `Coss(Q1)`, `ESL(C10)`), nets (`tr(node)`, `f_sw(cell)`, `I_max(net)`, `UI(iface)`), derived (`didt(loop)`, `dvdt(node)`, `lambda_g(f, layer)`, `LSB(adc)`). Every resolved number carries its derivation chain into the ledger (I2).

### Entity schema

Common fields for every entity in `physics:`:

| Field | Meaning |
|---|---|
| `id`, `kind` | Stable id; kind from the closed set below |
| `intent` | `designed` (the structure is a circuit element with a spec: antenna, channel, shunt, heat spreader) or `parasitic` (it must stay under budget). Default by kind |
| `budget` | map metric → bound, with optional `band`, `alloc` (split across sub-structures, I1; code proposes the √(k·s) split of [schematic-to-physics](schematic-to-physics.md)) and `basis` (the requirement the bound came from) |
| `why` | requirement ids (I3 why-graph edges) |
| `src` | `{by: code|llm|human|pack, rule, evidence, confidence, confirmed_by}` |

Kind-specific fields (required in bold):

| Kind | Fields | Notes |
|---|---|---|
| `port` | **`sig`**, **`ref`** (terminal lists), `use` (power, signal, sense, rf, chassis), `fixed` (edge, pose lock), `z`, `external` (cable, antenna, none) | `ref` may not be empty: a port is a terminal *pair*. `use: sense` adds an implicit budget `I == 0 A` on the tap segment |
| `node` | **`net`**, `excite` (spectrum, as an aggressor), `sense` (sensitivity, as a victim), `z_src` | A dv/dt node; also a high-impedance victim |
| `loop` | **`path`** (ordered terminals, closed), **`return`** (reference or terminals), `class` (commutation, gate, decoupling, signal, sense, power), `excite` | A di/dt loop; `via:GND` marks a via into the return plane |
| `channel` | **`from`**, **`to`** (ports), `through` (series parts), `z`, `ref` (allowed references), `transitions` | Transmission line with its reference; budgets in dB, ps, mV |
| `reference` | **`net`**, **`layers`**, `region`, `serves` (layers or channels), `bands` | Mostly code-derived from the stackup and zones |
| `body` | `net`, `layer`, `shape` (`pour`, `skeleton`) | Geometry-view handle; operators target it |
| `cavity` | **`between`** (two references), `outline` | Code computes f_mn |
| `discontinuity` | **`in`** (reference), `type` (slot, split, edge, antipad_chain, ref_change), `bridge` | Created by code when the reference map shows one under a served structure; the LLM may require a `bridge` |
| `antenna` | **`halves`** (two conductors), **`band`**, `drive` (current, voltage) | Unintended unless `intent: designed` |
| `coupling` | **`aggr`**, **`victim`**, **`mech`** (capacitive, inductive, common_impedance, radiated, conducted, thermal, leakage), **`band`**, `shared` (required for common_impedance) | Source-path-victim triple with a margin budget |
| `exclusion` | **`region`** or **`body`**, **`of`** (loops or classes), `band` | Aggressor current density must stay out of a victim's reference |
| `shield` | **`protects`**, `type` (grounded, driven_guard, fence, can), `pitch` | Intended structure |
| `heat_path` | **`source`**, **`P`**, **`sink`**, `via` | Budget in degC or K/W |
| `barrier` | **`between`** (domains), **`V_work`**, `std`, `pd`, `mg` | Budget creepage, clearance, `C_across` |
| `cell` | **`template`** (buck, boost, half_bridge, flyback, ldo, xtal_pierce, ...), **`parts`** (role → refdes) | Composite; code expands it into loops, nodes, ports and couplings |
| `feed` | **`from`**, **`to`** (ports), `I` | DC power delivery; budgets in mΩ, mV, degC |

In code, each kind is a typed class with `expand()` (to 0.2 constraints) and `compile(target)`, mirroring ALIGN's `HardConstraint.translate(solver)` ([constraint-models-compared](../architecture/constraint-models-compared.md)); cell templates are functions that return entity lists, so YAML and a Python DSL are two spellings of one model.

Spectrum forms for `excite`: `{wave: trapezoid, V|I, f0, duty, tr}`, `{wave: data, rate, tr, V}`, `{wave: sine, f0, V|I}`, `{wave: edge, tr, V|I}` (ESD, hot plug), `{wave: dc, I}`, `{wave: sim, file}` (back-annotated from SPICE). Code derives `dvdt`, `didt` and a piecewise log-log envelope ([LearnEMC trapezoid calculator](https://learnemc.com/ext/calculators/trapezoid_harmonics/index.html) [S]).

Sensitivity form for `sense`: `{threshold, band, transfer}`, where `transfer` names a filter, PSRR or CMRR curve from the layout card, so a victim's threshold applies after its own rejection.

Bands are named intervals: `bands: {sw: ["f_sw(buck1)", "1/(pi*tr(buck1.sw))"], rf24: [2.4 GHz, 2.4835 GHz]}`. Built-ins: `dc`, `esd` (about 0.3–1 GHz for IEC 61000-4-2 edges [I]), and `edge:<node>`.

### Validation rules (prototype: `tools/research/physics/vo_ir_check.py`)

1. Closed kinds, required fields, no unknown keys.
2. Every quantity parses and has the dimension its metric needs (`L_loop` → H, `IL` → dB, `dT` → K).
3. `port.ref` non-empty. FastHenry has the same rule: a port "with no possible return path will always carry zero current", which makes its impedance matrix "nonsense (NaN)" ([FastHenry 3.0 guide § 1.3.5](https://www.fastfieldsolvers.com/Download/FastHenry_User_Guide.pdf) [P]).
4. `loop.path` is closed and names its return.
5. Mechanism compatibility: `capacitive` needs a node or port aggressor; `inductive` a loop, channel or feed aggressor; `common_impedance` a named `shared` conductor; `thermal` a heat path, feed or cell; `leakage` a node or feed.
6. Budgets with `alloc` must sum to at most 100%.
7. Every coupling and antenna names a band.

The prototype catches 12 of 12 errors seeded in a test file, and the 46 entities of the six [worked examples](physics-ir-examples.md) pass with 0 errors [C].

### Derivation from the schematic (what code drafts)

| Step | Input | Output entities |
|---|---|---|
| 1 Net roles | layered classifier ([net-role-classification](../llm/net-role-classification.md)) | role tags |
| 2 Band netlists | per band, replace parts by band models: caps above C_min(band) → short, inductors and beads → open, switches → both states | cycles = candidate `loop`s; low-Z clusters = candidate `reference`s ([LA12](../../ideas/physics-first/language.md)) |
| 3 Templates | topology detectors (hot-loop table in [hot-loops](../rules/power/hot-loops.md)) | `cell` → `loop`, `node`, `port` |
| 4 Spectra | IBIS `[Ramp]`, datasheet f_sw, t_r, I_out; schematic simulation ([schematic-to-physics](schematic-to-physics.md)) | `excite` on nodes and loops |
| 5 Sensitivities | roles: ADC resolution → LSB; FB divider → V_ref tolerance; XIN → ppm/pF; RX sensitivity | `sense` on victims |
| 6 Coupling screen | every aggressor × victim with overlapping bands; worst-case transfer at the closest feasible distance | `coupling` entities with budgets; pairs screened out are logged with their margin |
| 7 Ports and antennas | connectors (with `external: cable`), heatsinks, shields | `port`, `antenna` (V_cm between every pair of external reference terminals) |
| 8 Heat and isolation | P > threshold; isolator parts; net voltage classes | `heat_path`, `barrier` |

The LLM then adjudicates: it confirms templates, fills spectra the documents do not give (flagged as assumptions), links budgets to requirements and standards, and adds mechanism hypotheses the screen missed. A human confirms the top-level budgets ([U3](../../ideas/original/workflow-ux.md) expected-loss ordering).

### Who writes what

| Item | LLM | Code | Human |
|---|---|---|---|
| Topology, cells, roles | adjudicates ambiguous detections | detects | confirms |
| Spectra | flags unknowns; picks sources | computes from IBIS, datasheet, SPICE | answers questions |
| Sensitivities | links victims to requirements | computes thresholds | confirms top-level |
| Budget limits and allocations | proposes from requirements, standards and datasheets | derives expressions; checks sums and dimensions | approves |
| Couplings | hypothesises beyond the screen | screens every pair | — |
| Operators (`ops`) | picks from a ranked menu, with reasons | predicts deltas, executes, verifies | approves applies |
| Regimes, physics graph, ledger, spend | never | computes | reads |
| Geometry and coordinates | never | engines | may edit |

This keeps the RAC result: relations, not coordinates, raise clean-pass from 23.2% to 90.9% ([interfaces-relations-vs-coordinates](../llm/interfaces-relations-vs-coordinates.md)) [P]. Physics entities are relations with physical units instead of ordinal magnitudes.

### Operator plan (`ops`)

```yaml
ops:
  - {op: fold_loop_vertical, target: buck1.hot, args: {return_layer: In1.Cu}, why: [req.vds_margin]}
  - {op: kelvin_tap, target: buck1.fb_sense, args: {at: "C12.1"}}
  - {op: halo, target: buck1.sw, args: {victims: [adc1.ain]}}
```

Code fills `expect` (predicted delta per budget from the operator's sensitivity card, [vocabulary § Operators](vocabulary.md#operators)) before execution and `observed` after. An operator whose observed delta disagrees with `expect` beyond the model's trust radius raises a finding.

### Compilation targets

| Entity | KiCad objects | `.kicad_dru` (KiCad 10) | Placer / router | Checker | Solver / simulator deck |
|---|---|---|---|---|---|
| `port` | locked footprint, edge assertion | `assertion` on `Layer`/`Orientation` | fixed anchor | `DECAP-L`, `PDN-Z` for power-pin ports | openEMS lumped/wave port; FastHenry `.external` |
| `loop` | component class `loop:<id>`, group, rule area on the hull | `disallow track via` for foreign nets inside the hull rule area | N7 nH micro-placer objective; same-layer reservation | `HOTLOOP-L`, `SENSE-M` | FastHenry deck cut at the decoupling cap (`.external`), then ngspice LC-step for V_pk ([dr_switch_cell_budget.py](../../../tools/research/physics/dr_switch_cell_budget.py)) |
| `node` | net class; zone with max area | `clearance` to victim classes from a coupling budget | area-aware cost | `SW-AREA` | FasterCap |
| `channel` | net class, diff pair, tuning profile (ps) | `skew (within_diff_pairs)`, `via_count`, `length` in ps | chain order (N9); PNS diff-pair; shadow return (R2) | `RET-COV`, `RET-VIA`, `DIFF-BAL`, loss spend | scikit-rf cascade; openEMS for transitions |
| `reference` | zones (net, layer, priority) | `return_path` (master; KiCad 11 if it ships) | router cost field | reference map (`RET-COV`) | mesh for PEEC |
| `discontinuity` | stitching vias or caps for `bridge` | — | via-site reservation (R3) | `SPLIT-X`, `RET-VIA` | openEMS for the crossing |
| `coupling` | rule-area halo | `clearance` from D ≥ H·√(1/K − 1) for capacitive budgets | halo repulsion; parallel-run cost | `IO-COUPLE`, `SENSE-M`, `THERM-COUPLE` | FasterCap/FastHenry two-body |
| `exclusion` | rule area | `disallow` foreign tracks | cost field | `IR-DROP` solve, J inside the region | sheet-resistance solver |
| `antenna` | — | — | P8 connector-voltage proxy | `CM-V` (MREMC), `ANT-KEEP` | openEMS far-field |
| `heat_path` | zones, via arrays | `zone_connection solid` on thermal pads | thermal spread term | `THERM-DT` | 2D finite-volume or Elmer |
| `barrier` | rule area, slot | `creepage`, `clearance`, `physical_clearance` | keep-out | creepage path, `HV-FIELD` | — |
| `cell` | design block, group | expands | template with physics slack (P3) | cell checklist | ngspice cell model |

Checker ids are those of the [critic catalog](physics-critics-catalog.md); a `feed` compiles to `IR-DROP`, `J-MAX` and `THERM-DT`. Each emitted DRU rule is named `IR:<entity id>.<metric>` for attribution, ordered general → specific, and linted on a scratch board ([constraint-ir](../architecture/constraint-ir.md)). Where KiCad cannot express a budget, the DRU rule is a labelled proxy and the checker is authoritative; the ledger records which one gave the verdict.

### Mapping from `0.2` kinds

| `0.2` kind | `0.3` source of truth | Becomes |
|---|---|---|
| `bypass` | `port` (pin + return pins) + `loop` (class decoupling) with `L_mount` budget | proximity and via-to-plane become proxies derived from the nH budget |
| `loop_area` | `loop` with `L_loop` budget | area kept as a fallback when no spend model is trusted |
| `via_to_plane` | `reference` transition on a `channel` or `loop` | return-device distance derived from band and data rate |
| `impedance`, `match_group` | `channel` budgets (`Z`, `skew`, `IL`) | unchanged DRU emission |
| `cluster_tight` | `cell` | members from the template |
| `overheated_length` | `feed` + `heat_path` | ΔT budget, not a length fraction |
| `proximity` | any coupling or loop budget | emitted only when no physical spend model exists, tagged [I] |

## Recommendations for our system

- **Ship 0.3 as an additive extension.** Physics entities expand to 0.2 constraints in a first release, so the DRU emitter and checkers can be reused unchanged [I].
- **Make `ledger.json` the only place a computed number lives.** Never write spend into `intent.yaml`. Then intent diffs stay readable and evidence can be regenerated [I].
- **Build the validator before the compiler.** Dimensional analysis and the half-port rule catch most LLM authoring errors cheaply (I2 test plan) [I].
- **Start with five kinds:** `port`, `loop`, `node`, `channel`, `coupling`. These cover hot loops, decoupling, FB routing, USB/PCIe and crosstalk. Add `exclusion`, `heat_path` and `barrier` next [I].
- **Use the FastHenry/FasterCap deck model (nodes, segments, planes, ports as terminal pairs) as the shape of our solver input; it is nearly the physics graph itself.** Ship our own PEEC, PyPEEC (MPL-2.0) and FasterCap (LGPL-2.1). FastHenry's source carries an MIT "internal, noncommercial … distribution strictly prohibited" notice, so FastHenry decks are for internal calibration runs only and FastHenry is never vendored or shipped ([open-solvers](open-solvers.md)) [P].

## Conflicts and open questions

- **Spend-model trust.** The L·di/dt overshoot model and the LC step model disagree when the edge is shorter than the ring period ([dr_switch_cell_budget.py](../../../tools/research/physics/dr_switch_cell_budget.py) [C]). The ledger must name the model per regime, not one formula per budget.
- **Granularity of `alloc`.** Partial inductances are not additive without their mutual terms; allocations over sub-structures are approximate when sub-structures couple strongly [I].
- **`ledger.json` size.** A dense partial-inductance matrix grows as N²; storing it per revision needs sparsification ([vocabulary § physics graph](vocabulary.md#the-physics-graph)).
- **KiCad 11** `CustomRule` protobuf and `return_path` may replace several custom checkers; re-target when it ships.

## Sources

- Research notes: [constraints_verification_benchmarks.md § Q1](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/constraints_verification_benchmarks.md); [verification_kicad_and_tools.md § 2, § 5](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_kicad_and_tools.md)
- FastHenry 3.0 user guide (MIT, 1996): https://www.fastfieldsolvers.com/Download/FastHenry_User_Guide.pdf [P]
- Modelica 3.6 connectors (potential equal, flow sums to zero): https://specification.modelica.org/maint/3.6/connectors-and-connections.html [P]
- Scripts: [vo_ir_check.py](../../../tools/research/physics/vo_ir_check.py), [vo_numbers.py](../../../tools/research/physics/vo_numbers.py)

See also: [vocabulary.md](vocabulary.md), [physics-ir-examples.md](physics-ir-examples.md), [../architecture/constraint-ir.md](../architecture/constraint-ir.md), [../../ideas/original/intent-and-why.md](../../ideas/original/intent-and-why.md), [solver-ladder.md](solver-ladder.md), [../../ideas/physics-first/language.md](../../ideas/physics-first/language.md)
