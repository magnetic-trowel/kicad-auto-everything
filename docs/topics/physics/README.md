# Physics-first layout: the philosophy

**TL;DR**
- **A layout is the physical realization that the schematic leaves out.** That is an unintended R, L, M and C network, a set of field structures (loops, cavities, antennas, heat paths) and a manufactured object. Physics-first layout makes that realization *invisible* to the circuit's function and to the outside world, within budgets in physical units, at the lowest manufacturing cost and risk ([schematic-to-physics](schematic-to-physics.md)).
- **About 160 rules of thumb reduce to 12 physical quantities** (L, M, Cm, R, Z, Bal, Vcm, Res, Ins, Th, Mech, Fab). The electrical ones are views of four PEEC primitives (partial R, partial L, capacitance, retardation). A physics-first checker therefore needs about four engines, not 160 rules ([rule-basis-set](rule-basis-set.md)).
- **Rules fail by regime, not by direction.** Physics-origin rules were right in 80 of 91 cases, but habit rules were wrong in 10 of 15. Every rule needs a regime test, and most of them reduce to a dimensionless group ([rule-basis-set](rule-basis-set.md)).
- **The physics is cheaper than it looks.** 143 of 160 rules can be replaced by a closed form, a 2-D solve, PEEC, a thermal network or SPICE. A numpy PEEC loop solve takes about 1 ms and agrees with FastHenry within 1.3%, and one adjoint solve prices every copper edit ([solver-ladder](solver-ladder.md), [copper-shape-synthesis](copper-shape-synthesis.md)).
- **Placement and routing are one optimization problem.** Fixed parts (outline, holes, connectors, antenna, heatsink) act as its boundary conditions, and physics is the objective both halves share ([joint-place-route](joint-place-route.md)).

Tags: [P] primary, [S] secondary, [V] vendor, [I] inference, [C] computed by us (scripts in [`tools/research/physics/`](../../../tools/research/physics/)). Everything in this area is a proposal [I] unless a number is tagged otherwise.

## Key facts

### The thesis

Bogatin: aggressor noise exists "only in the traces and white space of the board, not in the schematic" ([what-good-looks-like](../workflow/what-good-looks-like.md)) [P]. The schematic is an idealization. The board adds a parasitic network, field structures and heat paths that the schematic never shows. Every rule of thumb is a cached solution of that physics for one typical context: a stackup, a rise time, a current or a fab process. The cache is lossy. It keeps the geometry ("3W", "within 2 mm", "45° corners") and drops the conditions that made it right ([myths-and-contested](../rules/myths-and-contested.md)).

Physics-first means three things:
1. **Decompress the rules** into the quantity each one protects, the equation, and the regime where it binds ([rule-genealogy power](rule-genealogy-power-analog-thermal.md), [SI/EMI/RF](rule-genealogy-si-emi-rf.md), [routing/DFM](rule-genealogy-routing-style-dfm.md)).
2. **Evaluate the physics directly** where compute allows, which is almost everywhere ([solver-ladder](solver-ladder.md)).
3. **Optimize placement, routing and copper shapes together** against budgets derived from the circuit, with manufacturing as hard constraints and yield costs ([joint-place-route](joint-place-route.md)).

**Invisibility, made measurable.** Simulate the schematic, extract the layout's parasitics, back-annotate them, re-simulate, and compare. The layout invisibility index LII is the maximum over outputs of deviation ÷ budget. A parasitic that moves no output is free ([schematic-to-physics](schematic-to-physics.md)) [I].

### Fourteen principles

| # | Principle | What it replaces | Evidence |
|---|---|---|---|
| 1 | **Design ports and loops, not wires.** A schematic net is half a port. Every current has a return, and the return is part of the route. | "Route the net"; ground as a symbol | [vocabulary](vocabulary.md): a port with no named return is a validation error (FastHenry gives NaN for the same reason) [P] |
| 2 | **Classify copper by waveform, not by net name.** dv/dt nodes act through E-fields, so minimise their C to the world. di/dt loops act through H-fields, so minimise their L. Heavy DC feeds minimise R and ΔT. Quiet nodes minimise M and C to aggressors. | Name-based net classes | [power-copper](power-copper.md); waveforms come from simulating the schematic ([schematic-to-physics](schematic-to-physics.md)) |
| 3 | **Width trades parasitics; length and height win.** Over a plane, L ∝ h·l/w, C ∝ w·l/h, R ∝ l/w, so widening trades L against C. Only length lowers all three (L·C = l²/v², R·A = R_s·l²). Height to the reference is the strongest knob. | "Short and wide"; "minimise loop area" | Near a plane, loop L follows height × squares (Σ μ0·h·dl/w), not area: equal-area loops differ 1.7× [C]. Plane depth moves a hot loop 0.93 → 4.1 nH, while the go/return gap moves it only 0.89 → 1.35 nH [C] ([pdn-and-commutation](pdn-and-commutation.md)) |
| 4 | **One equation, many physics, each with a length scale.** IR drop, plane spreading inductance, heat spreading, decap reach and via current transfer are all a screened Laplace equation on sheets. Its length scale decides what "close" means. | "Close", "near", "as close as possible" | Via transfer ~0.4–1 mm, decap reach 4–24 mm, heat spreading 8 mm (bare FR-4) to 38–64 mm (copper) [C] ([cross-domain-lessons](cross-domain-lessons.md), [thermal-physics](thermal-physics.md)) |
| 5 | **Shape copper by current flow.** Pours carry DC and quiet returns. Widen the entries first, because 31% of a pour's loss sits within 3 mm of the pads. Via rows go across the flow, because via fields conduct at their edges. Switch-node copper stays as small as the EMI budget demands. | "Pour everything"; "1 via per amp" | [power-copper](power-copper.md), [copper-shape-synthesis](copper-shape-synthesis.md): topology optimization saves 14.5% at equal area, but area matters more than shape [C] |
| 6 | **Return impedance is the SI/EMI currency.** ΔZ_ret(f) × I(f) is a voltage charged to an SI budget and to an EMI budget between cable attachment points. | About a dozen plane, slot, split, via and edge rules | [fields-si-emi](fields-si-emi.md): a slot adds ~0.08–0.13 nH per mm [C] |
| 7 | **Topology before tweaks.** Choose the connector edge, the stackup, the edge rates and the frequency plan before fine geometry. | Long rule lists applied uniformly | EMI: both cables on one edge buys ~40 dB, removing a slot 24 dB, slower edges 3 dB [C] ([fields-emi-budget](fields-emi-budget.md)). Non-geometric levers (0.1 mm prepreg, GND/GND inner layers, bonding the heatsink to DC−) often beat geometry ([worked-thought-experiments](worked-thought-experiments.md)) |
| 8 | **Geometric detail is regime-gated.** Corners, arcs and teardrops matter for SI only below ~30 ps edges. Pads, stubs and vias matter much earlier. Curves pay in HV, pulsed current, ESD, RF and flex, and angled routing pays against fibre weave. Fabs make curves at no extra cost, so allow them wherever physics pays. | "Always 45°"; "never 90°" | 90° corner on 50 Ω with h = 0.1 mm: 0.5% reflection at 100 ps [C] ([rf-geometry](rf-geometry.md)). Corners matter for pulses under ~1 ms ([power-copper](power-copper.md)) and for HV fields ([hv-and-manufacturing-physics](hv-and-manufacturing-physics.md)) |
| 9 | **Budgets come from the circuit, and priority comes from least slack.** Simulate the schematic and get susceptibility from one adjoint (`.noise`) solve. Share each budget in proportion to √(cost × sensitivity). Order the work by τ = budget ÷ achievable floor. | Fixed placement order; invented millimetres | [schematic-to-physics](schematic-to-physics.md), [design-reasoning-architecture](design-reasoning-architecture.md) |
| 10 | **Placement and routing are one problem.** Use one state (part poses, route topologies, copper fields) and one physics objective. Fixed parts are boundary conditions: ports, thermal boundaries, holes in the domain. | Place, gate, route, backtrack | [joint-place-route](joint-place-route.md), [physics-in-the-loop-optimization](physics-in-the-loop-optimization.md) |
| 11 | **Fidelity follows decisions.** Use the cheapest model that ranks candidates correctly, and escalate only when a higher fidelity could flip a decision. | Simulate everything, or nothing | The µs proxy MS2 picks the PEEC-best hot loop 96–98% of the time; loop area does so 16–66% [C] ([solver-ladder](solver-ladder.md)) |
| 12 | **Manufacturing is physics with legal margins.** Legal limits and fab absolute limits are hard constraints. Fab "recommended" values become yield costs (critical area, σ-margin). Physics budgets are soft costs. | One DRC number per rule | [hv-and-manufacturing-physics](hv-and-manufacturing-physics.md) |
| 13 | **Score physics separately from DRC.** DRC-clean is necessary, not sufficient. A physics scorecard and a DRC-equivalent mutation benchmark expose the gap. | "Zero DRC errors" as the goal | [physics-critics](physics-critics.md) |
| 14 | **Beauty is locality of fields.** Fast currents close inside small cells, and only DC and defined signals cross cell boundaries. Where neatness is not a proxy for that (long, neat parallel buses), physics wins. | Taste | [design-reasoning-architecture](design-reasoning-architecture.md) |

Rules survive in four roles: priors and warm starts, move generators for search, retrieval keys for explanation, and legal limits ([rule-replacements](../../ideas/physics-first/rule-replacements.md) RG41–RG42). They are never the judge.

### The basis set and the four engines

| Quantity | Unit | Cheapest adequate engine |
|---|---|---|
| L loop/partial inductance; M mutual and shared-path coupling | nH, pH, mΩ | closed form → PEEC |
| Cm node capacitance | pF, fF | 2-D → 3-D electrostatic |
| R resistance and current density | mΩ, A/mm² | 2-D sheet Laplace |
| Z propagation (impedance, delay, loss); Bal balance | Ω, ps, dB | 2-D cross-section + closed form → full-wave slice |
| Vcm radiating common mode; Res distributed resonance | dBµV/m, MHz, Q | closed-form chain → cavity eigen-solve → full-wave |
| Th thermal; Ins insulation; Mech strain; Fab process margin | K, kV/mm, µε, σ | thermal network/kernel; 2-D field; beam/FEM; yield model |

Source: [rule-basis-set](rule-basis-set.md). "Return-path continuity" and "loop area" are causes, not quantities: they show up in L, Z, Bal, Vcm and Res. The solver inventory and its licences are in [open-solvers](open-solvers.md). The fidelity tiers, F0 (geometry) to F4 (measurement) plus S (surrogates), are defined in [solver-ladder](solver-ladder.md).

### The language

The [vocabulary](vocabulary.md) names the realization with 12 atoms and 5 value types:
- **Atoms:** Port, Node, Loop, Body, Reference, Channel, Cavity, Discontinuity, Antenna, Heat path, Barrier, Coupling.
- **Value types:** Spectrum, Sensitivity, Budget, Band, Regime.

Every structure is either *designed* (it has a spec) or *parasitic* (it has a budget). Operators (widen-to-pour, fold-loop-vertical, overlap-return, stitch, Kelvin-tap, exclusion zone…) carry signed effects on every budget.

[`pcb-intent/0.3`](physics-ir.md) adds `bands`, `symbols`, `physics` and `ops` to the existing [`0.2` IR](../architecture/constraint-ir.md). Two files hold the state:
- **`intent.yaml`:** what is required. Detectors, the LLM and humans write it.
- **`ledger.json`:** what is observed. Only code writes it, from the physics graph.

The LLM writes requirements, allocations, mechanism hypotheses and operator choices. It never writes geometry, regimes or spend. Six worked circuits are in [physics-ir-examples](physics-ir-examples.md).

### The machine

```
schematic + datasheets + fixed constraints (outline, holes, connectors, antenna, heatsink)
  │
  ├─ comprehension (existing pipeline) ──► roles as hypotheses
  ├─ simulate the schematic ──► net passports (swing, dv/dt, di/dt, spectrum), susceptibilities
  ├─ decompose ──► ports + boundary conditions, loops by L·di/dt, nodes by C·dv/dt,
  │                coupling graph per band, energy flow, heat sources
  ├─ budget ──► ledger rows from sensitivities; τ ranking; binding outputs
  ▼
joint placement + routing + copper-shape optimizer
  state: part poses · route homotopy classes, layers, vias · copper density fields
  objective: physics spend (F1/S in the inner loop, F2 on accepted moves) + fab yield cost
  hard: fab and legal limits, fixed parts, keep-outs
  │
  ▼
legalize (projection, Minkowski, CP-SAT) ──► kicad-cli DRC (referee)
  │
  ▼
physics critics (separate scorecard) ──► back-annotate, re-simulate, LII
  │
  └─► LLM explains the binding budgets and proposes repairs (geometry intent,
      stackup, part, edge rate, circuit) ──► human confirms ──► loop
```

Details: [design-reasoning-architecture](design-reasoning-architecture.md), [schematic-to-physics](schematic-to-physics.md), [joint-place-route](joint-place-route.md), [physics-in-the-loop-optimization](physics-in-the-loop-optimization.md), [copper-shape-synthesis](copper-shape-synthesis.md), [physics-critics](physics-critics.md).

### Answers to the questions that started this

| Question | Answer |
|---|---|
| Curves instead of right angles? | For signal integrity, only below ~30 ps edges or on RF lines. For steady current never: peak temperature is within 0.5% [C]. Curves do matter for pulses under ~1 ms (2–8× local J²), on surge, fuse and ESD paths, and in HV, where E-field enhancement at a corner scales as (g/r)^(1/3) and rounding to r ≥ g/2 recovers most inception voltage [C]. Curves cost nothing at the fab, so the system may use them wherever any budget benefits ([rf-geometry](rf-geometry.md), [power-copper](power-copper.md), [hv-and-manufacturing-physics](hv-and-manufacturing-physics.md)). |
| Pours instead of thin traces in power circuits? | Yes for DC feeds and returns, shaped by current flow with the entries widened first. Not for switch nodes, where copper area is capacitance to the world. At equal copper area a synthesized shape beats a good hand tree by ~15%; adding copper beats reshaping it ([copper-shape-synthesis](copper-shape-synthesis.md)). |
| How much R, L and C, and which to maximize? | Per piece of copper, from its waveform: minimise a·L + b·C + g·R, where the weights come from di/dt, dv/dt and I_rms. The cell's switching impedance V/I gives the optimal width ([power-copper](power-copper.md)). The only parasitics worth *maximizing* are the useful ones: plane-pair capacitance (thin dielectric), mutual coupling inside a pair or a go/return overlap, and damping resistance where a resonance needs it ([pdn-and-commutation](pdn-and-commutation.md)). |
| Keep high-current lines away from sensitive pairs? | Distance is the weak lever once a solid plane is close. A plane 0.1 mm under both loops cuts magnetic coupling ~400× at 5 mm [C]. The strong levers are reference continuity, keeping the aggressor loop closed inside its cell, and, for precision analog, DC current exclusion from the measurement's ground region ([worked-thought-experiments](worked-thought-experiments.md), [vocabulary](vocabulary.md) LA7). |
| A physics engine, SPICE, open RF tools? | Four engines cover nearly everything: PEEC (R, L, C, with retardation where needed), a sheet Laplace/thermal solver, SPICE with adjoints, and full-wave (openEMS, Palace) only for finalists and calibration ([open-solvers](open-solvers.md)). |
| Use near-infinite compute how? | Batch F1/S evaluations over candidate populations. Run F2 label factories to train residual surrogates (3.5% median error from 300 labels [C]). Run quality-diversity search over physics descriptors and GPU full-wave on finalists. Never use FDTD for an electrically small loop: ~75 CPU-minutes against ~1 ms of PEEC ([solver-ladder](solver-ladder.md)). |
| Place and route at the same time? | Yes, on a topology-carrying joint state optimized on three timescales: rubber-band re-tightening as parts move, congestion and physics prices as placement forces, and LNS windows that rip up and repair parts and copper together ([joint-place-route](joint-place-route.md), [experiment](joint-place-route-experiment.md)). |

### Challenges to existing docs

| Doc | Challenge | Source |
|---|---|---|
| [hot-loops](../rules/power/hot-loops.md), N7 | Loop-area tiers are a weak proxy near a plane; use height × squares or MS2 | [pdn-and-commutation](pdn-and-commutation.md), [solver-ladder](solver-ladder.md) |
| [high-current](../rules/power/high-current.md) | Current does not share evenly across a via field; edge vias carry most of it | [cross-domain-lessons](cross-domain-lessons.md) |
| [decoupling-pdn](../rules/decoupling-pdn.md) | "As close as possible" is bounded by a screening length; cluster geometry and orientation matter more than via count | [pdn-and-commutation](pdn-and-commutation.md) |
| [buck](../rules/power/buck.md) | The Rohm copper-under-inductor keep-out costs ~0.2% L for shielded parts; keep the plane unless the core is open | [pdn-and-commutation](pdn-and-commutation.md) |
| [placement-methodology](../rules/placement-methodology.md), [hybrid-architecture-options](../architecture/hybrid-architecture-options.md) | A fixed staged order gives way to τ-ordered priorities inside one joint optimizer | [design-reasoning-architecture](design-reasoning-architecture.md) |
| [thermal](../rules/thermal.md) | Spacing hot parts buys little on boards smaller than ~2 spreading lengths | [thermal-physics](thermal-physics.md) |
| [evaluation-stack](../verification/evaluation-stack.md) | FastHenry is internal calibration only (non-commercial notice); Ki-PIDA is AGPL (fixed in that doc) | [open-solvers](open-solvers.md) |

## Recommendations for our system

1. **Adopt the basis set and the vocabulary as the shared contract.** Budget types are the 12 quantity codes. Every rule record carries its origin, regime predicate and replacement budget ([rule-replacements](../../ideas/physics-first/rule-replacements.md) RG1–RG3).
2. **Build one physics core first:** merge the three PEEC prototypes (`sl_`, `pw_`, `fe_`; SIM46) and the sheet-Laplace solvers (`pw_sheet`, `op_topopt_pour`, `xd_sheet`, `tm_board_thermal_fv`) into one library with value, σ, validity and cost on every call.
3. **Make "simulate the schematic" the first stage** ([reasoning](../../ideas/physics-first/reasoning.md) DR1, DR3). Measured waveforms replace name-based roles, and adjoint susceptibilities make budgets mostly automatic.
4. **Build the joint optimizer on the existing solver stack** ([recommended-stack](../solvers/recommended-stack.md)). Physics spend models act as forces and costs, and CP-SAT legalizes. `kicad-cli` stays the referee.
5. **Ship the physics scorecard and the mutation benchmark before any optimizer is trained on physics rewards** (the [V1/V2](../../ideas/original/verification.md) gate).
6. **First experiments** are in the [executive report](../../../reports/Physics-first%20PCB%20layout.md) and the [ideas catalog](../../ideas/physics-first/README.md).

## Conflicts and open questions

- **Numbers that differ between workstreams, from different assumptions.** Name the model in each ledger row ([vocabulary](vocabulary.md)).
  - Heatsink coupling: 22 vs 26 pF.
  - Thermal spreading length: 21–29 mm (one layer) vs 38 mm (two layers + FR-4).
  - The hot-loop LC-step model vs L·di/dt.
- **Unverified models.**
  - The slot inductance formula needs an openEMS check; Ott's measured slot data grow faster with length.
  - The bridging-cap estimate (1.2–3 nH) sits below Ott's 5–10 nH.
  - Thermal reliefs vs tombstoning: our lumped model says reliefs barely matter, against vendor guidance.
- **Calibration debt.** Most [C] numbers come from quasi-static models checked against closed forms, FastHenry or each other, not against measurement. The F4 rung (EVM layouts, published measurements) is still empty.
- **Untested at board scale.** The joint optimizer and the LII objective have been tested only on toys ([experiment](joint-place-route-experiment.md)).

## Sources

All [C] numbers come from scripts in [`tools/research/physics/`](../../../tools/research/physics/). Primary sources are cited in each topic doc. Research notes behind the rules: [rules_highspeed_emi.md](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/rules_highspeed_emi.md), [rules_power_rf_analog_dfm.md](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/rules_power_rf_analog_dfm.md), [verification_rules.md](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_rules.md).

## Map of this area

| Doc | Read it for |
|---|---|
| [rule-basis-set](rule-basis-set.md) + 3 genealogy docs | what each rule protects, its regime, its replacement |
| [vocabulary](vocabulary.md), [physics-ir](physics-ir.md), [physics-ir-examples](physics-ir-examples.md) | the language and schema |
| [design-reasoning-architecture](design-reasoning-architecture.md), [schematic-to-physics](schematic-to-physics.md), [worked-thought-experiments](worked-thought-experiments.md) | how the system thinks before geometry |
| [joint-place-route](joint-place-route.md), [joint-place-route-experiment](joint-place-route-experiment.md) | simultaneous placement and routing |
| [physics-in-the-loop-optimization](physics-in-the-loop-optimization.md), [copper-shape-synthesis](copper-shape-synthesis.md) | physics inside the optimizer; pours from physics |
| [power-copper](power-copper.md), [pdn-and-commutation](pdn-and-commutation.md) | power copper, hot loops, PDN, Kelvin |
| [fields-si-emi](fields-si-emi.md), [fields-emi-budget](fields-emi-budget.md), [rf-geometry](rf-geometry.md) | return paths, EMI chain, cavities, geometry thresholds |
| [thermal-physics](thermal-physics.md), [hv-and-manufacturing-physics](hv-and-manufacturing-physics.md) | heat, insulation, fab processes |
| [open-solvers](open-solvers.md), [solver-ladder](solver-ladder.md) | engines, licences, fidelity tiers |
| [physics-critics](physics-critics.md), [catalog](physics-critics-catalog.md), [validation](physics-critics-validation.md) | measuring "physically right" |
| [cross-domain-lessons](cross-domain-lessons.md) | analogies that transfer from other fields |

See also: [ideas catalog](../../ideas/physics-first/README.md) · [digest](../../digests/physics-first.md) · [executive report](../../../reports/Physics-first%20PCB%20layout.md)
