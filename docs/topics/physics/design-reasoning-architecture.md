# Design-reasoning architecture: from schematic and fixed constraints to a physics model

Scope: the reasoning layer R1–R7 that turns schematic, datasheets and fixed constraints into a physics model of the board-to-be (ports, loops, nodes, coupling graph, budgets, τ priorities) for the joint optimizer; roles of LLM, solvers, simulators, human. Not here: schematic simulation -> [schematic-to-physics](schematic-to-physics.md); optimizer -> [joint-place-route](joint-place-route.md); worked numbers -> [worked-thought-experiments](worked-thought-experiments.md); vocabulary atoms -> [vocabulary](vocabulary.md).
Keys: reasoning pipeline R1–R7, physics package, physics brief, least slack, tightness ratio τ, floor oracle, N5, N6, N7, N8, budget ledger I1, I2, coupling graph, bands, boundary conditions, ECO menu, shadow price, infeasibility certificate, locality index, clean and beautiful, rule-following vs physics-first

## The working hypothesis

A layout is the physical realization the schematic leaves out: an unintended R, L, C, M network, field structures, heat paths, a manufactured object. Physics-first layout makes it invisible to the circuit's function and to the outside world, within budgets in physical units, at lowest manufacturing cost and risk [I]. Bogatin: aggressor noise exists "only in the traces and white space of the board, not in the schematic" ([what-good-looks-like](../workflow/what-good-looks-like.md)) [P/E]. Invisibility is measured on the outputs that matter; a parasitic that moves no output is free ([schematic-to-physics](schematic-to-physics.md)).

The layer's product is a **physics model**, not a placement: ports and boundary conditions, an energy-flow graph, loops ranked by L·di/dt, nodes ranked by C·dv/dt, an aggressor→victim coupling graph per band, budgets in physical units with sensitivities. One joint place+route optimizer consumes it [I].

## Rule-following vs physics-first

| Aspect | Rule-following | Physics-first |
|---|---|---|
| Unit | mm, counts, yes/no | nH, mΩ, mV, ps, dB, K, V/mm, each with conditions |
| Scope of a statement | one rule, local, context-free | one budget per output, shared by every structure that spends it |
| Irrelevance | rules accumulate; nothing says "does not matter here" | quantified: a 90° corner on a 25 mm USB 2.0 line; a 1 pF crystal stray against a 500 ppm USB budget |
| Conflicts | priority lists, taste | trades in output deviation; shadow prices show each budget's cost |
| Levers | geometry | geometry, stackup, part, edge rate, frequency plan, circuit change |
| Fixed parts | positions to avoid | ports, thermal boundaries, common-mode references, domain holes |
| Order | fixed recipe | least slack first, computed per board |
| Typical failure | over-constraint, cargo cult, couplings no rule names | model error, missing models, over-trusted estimators |

Hubing's first common error is "blindly following guidelines"; a board meeting 90% of them "may be much worse" than one meeting a few ([placement-methodology](../rules/placement-methodology.md), [myths-and-contested](../rules/myths-and-contested.md)) [P]. Rules are cached physics solutions for a typical context: use them as priors, seeds and sanity checks; override them when the physics model has data ([rule-basis-set](rule-basis-set.md)) [I].

## The reasoning pipeline

```
 schematic + datasheets + partial layout (outline, connectors, heatsink, antenna,
 keep-outs) + stackup options + fab profile + enclosure + spec
   │
 R1 Comprehension: topology, blocks, roles as hypotheses (existing pipeline)
 R2 Characterize: simulate the schematic → net/branch passports, susceptibilities
 R3 Boundary conditions: ports, thermal BCs, CM references, domain holes
 R4 Decompose: energy flow, loops (L·di/dt), nodes (C·dv/dt), coupling graph, bands
 R5 Budget: allocate allowed output deviation by sensitivity → ledger rows (I1)
 R6 Plan: DC flow field, return-path plan, plane roles, stackup choice, τ ranking
   │  physics package
   ▼
 Joint placement+routing optimizer  ── realized parasitics, spend, shadow prices,
   ▲                                    infeasibility certificates ──┐
   │                                                                 ▼
 R7 Verify and explain: back-annotate, re-simulate, invisibility index, binding
    budgets → repair (geometry intent, stackup, part, edge rate, circuit) → R5/R6
```

- R1 reuses the [design-understanding pipeline](../llm/design-understanding-pipeline.md) and [comprehension](comprehension.md).
- R2 replaces name-based [net-role classification](../llm/net-role-classification.md) with measured physics, names as fallback. Build R2 and R5 before any new geometry engine: they make every later critic and optimizer term numeric [I].
- R5 makes the budget ledger and dimensioned constraints ([intent-and-why I1/I2](../../ideas/original/intent-and-why.md)) quantitative and mostly automatic.
- The package is written in the [vocabulary](vocabulary.md) and [physics IR](physics-ir.md); solver per question: [solver ladder](solver-ladder.md).

## Decomposition: the structures that get ranked

Rows map to vocabulary atoms Loop, Node, Channel, Port, Heat path, Barrier.

| Structure | Aggressor metric | Victim metric | Typical members |
|---|---|---|---|
| Current loop | L·di/dt (V per nH), dipole moment I·A | flux capture area, transfer to output | hot, gate, decap, ESD, sense loops |
| Voltage node | C·dv/dt (A per pF), copper area at swing | \|Z(f)\|, transfer to output | switch nodes, high-Z analog, crystal, PLL filter |
| Signal path + return | t_r vs electrical length, spectrum to 1/(π t_r) | noise margin, jitter = v_n / slew | clocks, diff pairs, RF lines |
| Port (connector) | CM voltage between cable references | ESD/EFT injection, susceptibility | USB-C, power inputs, sensor cables |
| Heat path | W dissipated | ΔT, ∇T (thermal EMF, drift) | FETs, shunts, references, crystals |
| HV gap | V across gap | E field, creepage | isolation barriers, bridge legs |

Coupling graph: one edge per aggressor–victim pair with non-negligible transfer, labelled by mechanism (shared impedance, M, C, field, thermal) and band:

| Band (indicative) | Governing return/coupling physics |
|---|---|
| DC – ~100 kHz | resistive spreading: plane gradients (µV/mm), thermal EMF, IR drop |
| ~100 kHz – 30 MHz | inductive: returns follow the trace, M·di/dt, shared inductance |
| 30 MHz – 1 GHz | field and cable modes: CM voltage on cables, resonances |
| > 1 GHz | geometry at λ/20: transmission lines, cavities, antennas, corners on RF only |

- Band edges are stackup-dependent: return crossover f_x ≈ R_□/(2π·µ0·h), values -> [vocabulary](vocabulary.md#bands-and-regimes).
- Output deviation: Δy(f) ≈ Σ_kj S_j(f)·κ_kj(f)·A_k(f); A = aggressor strength, κ = coupling (what layout controls), S = susceptibility from schematic simulation.

## Ordering: least slack first

τ_s = b_s / m_s, with b_s the R5 budget and m_s the achievable floor (best value any geometry reaches with these parts and stackup, e.g. the N7 hot-loop placer run with no competition).

```
for s in structures: b_s ← sensitivity allocation; m_s ← floor oracle; τ_s ← b_s/m_s
if any τ_s < 1: infeasible → ECO menu (stackup, part, edge rate, frequency, circuit)
rank by τ ascending; break ties by consequence class, then by uncertainty
emit to the optimizer: tiers (ε-lexicographic, N6), seed templates for τ < 2,
      weight-ramp order for continuation, reservations (N5)
on optimizer return: recompute τ from realized spend; re-rank; repeat
```

- = "most constrained variable first" of constraint programming, priced in physical units [I]. "Connectors, then ICs, then…" falls out only where physics agrees.
- Example ([case A](worked-thought-experiments.md#a-12-v--33-v-buck-mcu-with-a-usb-20-hs-phy-24-mhz-crystal-4-layers-fixed-usb-c) step 4): buck hot loop τ ≈ 1.7 leads; the crystal's τ is large, so it follows the MCU pins.
- τ answers the expert's "which circuits are critical?" ([placement-methodology](../rules/placement-methodology.md)), called tacit by Pease, as a number with an audit trail.
- Ordering is not sequence: the optimizer is joint, J = Σ w·φ(spend/budget) ([joint-place-route](joint-place-route.md)); τ sets weights w, barrier-steepening order and seed templates, not place-then-route order. Treat τ < 1 as an ECO question before optimization.

## The partial layout as boundary conditions

Ingest fixed items as typed boundary-condition objects (port, thermal BC, chassis bond, radiator, hole), not only locked footprints [I].

| Fixed item | Physics boundary condition | What reasoning derives |
|---|---|---|
| Connector | current port with CM reference; cable = antenna; ESD injection point | power entry; plane regions kept free of HF current between connectors; TVS and CMC location |
| Heatsink | thermal Dirichlet boundary; a capacitor (tab-to-sink ~20 pF, TO-220 on a 0.2 mm pad) to whatever it is bonded to | device location; bonding (to DC− near the bridge, or shielded); drift-sensitive parts off the gradient |
| Mounting hole | chassis bond: ESD and CM return; mechanical stress | where CM current may leave; MLCC keep-outs near flex points |
| Antenna "here" | radiator with ground-plane counterpoise; receiver port with sensitivity floor | plane shape and continuity from the feed, keep-out, per-clock spur budgets |
| Outline, slots, keep-outs | holes in the field and flow domain | plane inductance, spreading resistance, crowding |
| Enclosure | metal or plastic at a distance | antenna detuning, chassis capacitance, airflow |

Thermal and HV side: [thermal-physics](thermal-physics.md), [thermal-hv-mfg ideas](../../ideas/physics-first/thermal-hv-mfg.md).

## Plans made before geometry

- **DC power flow as a field:** sheet solve with injection at power ports, draw at loads; shape pours to the flow ([power-copper](power-copper.md), [copper-shape-synthesis](copper-shape-synthesis.md)). The same solve shows where references must not sit; a current-free peninsula cuts the gradient ~100× ([case C](worked-thought-experiments.md#c-24-bit-adc-next-to-a-switching-supply)) [C].
- **Signals with their returns:** every net longer than ~t_r/6 of electrical length, and every loop with a budget, gets an explicit return object (R2 shadow returns, R3 joint via sites in [routing ideas](../../ideas/original/routing.md)).
- **Planes as current-carrying structures:** assign each plane its DC and AC currents, choose roles from them. 4-layer, ≤ 0.5 A rails: GND/GND inner pair beats GND/PWR ([case A](worked-thought-experiments.md#a-12-v--33-v-buck-mcu-with-a-usb-20-hs-phy-24-mhz-crystal-4-layers-fixed-usb-c) step 3) [C].

## Roles and the agent loop

| Actor | Does | Never does |
|---|---|---|
| LLM (physicist) | topology; picks models and stand-ins; spec → outputs and budgets ("what the circuit owes"); names bands; writes a prediction with uncertainty before each simulation; reads residuals; proposes circuit, part, stackup, edge-rate alternatives; explains | emits coordinates, copper or parasitic values without a tool; gets no geometry tools |
| Deterministic solvers | geometry: joint place+route, micro-placers (N7, N8), plane and pour synthesis, legalization | choose outputs or budgets |
| Simulators, estimators | T0 closed forms, T2 SPICE with back-annotation, T3 field solves for finalists ([solver ladder](solver-ladder.md)) | decide what to simulate |
| Human | confirms the physics brief (outputs, budgets, model assumptions, contested choices); signs off | re-derive what tools derived |

Loop per structure:
1. **Hypothesize** mechanism and fix ("SW node couples into XIN through C"). Bogatin rule 9, "never perform a measurement or simulation without first anticipating the results", made mandatory ([what-good-looks-like](../workflow/what-good-looks-like.md)) [P/E].
2. **Estimate** with a T0 closed form and its calibrated σ.
3. **Escalate only if it can change the decision:** |budget − estimate| < z·σ, or the result could move the structure across a τ tier ([V4 proxy trust radius](../../ideas/original/verification.md) applied to fidelity) [I].
4. **Compare** with the budget; log prediction vs outcome (S4 in [system-loop](../../ideas/original/system-loop.md)).
5. **Modify** from a priced menu: geometry intent, stackup, part, edge rate, frequency plan, circuit change.

## Hand-off to and from the joint optimizer

| To the optimizer | Back from the optimizer |
|---|---|
| ports, thermal BCs, holes, fixed antenna region | realized parasitics per structure (nH, fF, pH, mΩ, K) |
| structures with spend models (cheap, ideally differentiable estimators of L, C, M, R, ΔT) | spend per budget, margin |
| budgets (hard or soft) and sensitivities spend → output deviation | shadow price of each budget in area, vias, length or another budget |
| tiers and continuation order from τ; seed templates for τ < 2 | infeasibility certificates (budgets that cannot coexist) |
| discrete alternatives (stackup A/B, edge rate, part swap) as decision variables | Pareto alternatives along the binding budgets |

Explanations come from binding budgets and derivation traces (I2) (example: [case A hand-off](worked-thought-experiments.md#a-12-v--33-v-buck-mcu-with-a-usb-20-hs-phy-24-mhz-crystal-4-layers-fixed-usb-c)). Numbers come from optimizer multipliers, never from the LLM [I].

## "Clean and beautiful" as physical coherence

"Clean" is mostly locality of fields: fast currents close inside small cells; only DC and defined signals cross cell boundaries [I].

| What experts call good-looking | Physical reason | Agree? |
|---|---|---|
| short, compact power loops | loop L and dipole moment scale with area and plane depth | agree |
| intact planes, no slots under traces | return continuity; low plane L | agree |
| symmetric differential structures | mismatch converts DM to CM | agree, but symmetry of *delay and coupling*, not shape |
| functional cells along signal flow | fewer long-range currents; short returns | agree |
| smooth, wide pours on power | uniform current density, lower IR drop and heating | agree for DC and thermal |
| aligned, same-orientation parts | inspection, assembly, reviewability | neutral |
| 45° corners, few bends | none below multi-GHz; manufacturing, editability | neutral |
| neat long parallel buses | crosstalk grows with parallel length | **diverge**: spacing or shorter runs |
| uniform trace widths | width should follow current | **diverge** |
| mirror-looking layouts of asymmetric circuits | currents are not symmetric | **diverge** |
| copper pour everywhere | floating/poorly stitched islands resonate; copper near antennas detunes | **diverge** near RF |

**Locality index** (candidate): fraction of each aggressor's HF current (above its band crossover) closing inside its cell's bounding region, from the plane current solution. Report it and binding budgets with shadow prices beside convention metrics ([looks-right-metrics](../verification/looks-right-metrics.md)); never let a convention term override a physics budget [I].

## Open questions

- [hybrid-architecture-options](../architecture/hybrid-architecture-options.md) Option A and [placement-methodology](../rules/placement-methodology.md) describe staged orders (mechanical → anchors → templates → … → route); we keep their substrate, replace stage order by τ priorities in one joint optimizer.
- τ needs a floor oracle per structure class; only hot loop (N7) and decap assignment (N8) have one designed. Coupling-budget floors (crystal, ADC input) are weaker: "far enough" depends on everything else.
- Locality index untested; no study links it or any aesthetic to measured EMC or reviewer acceptance ([what-good-looks-like](../workflow/what-good-looks-like.md)).
- LLM skill at model selection and residual reading unmeasured; spatial benchmarks say nothing about it ([spatial-reasoning-limits](../llm/spatial-reasoning-limits.md)).

## Sources

- Research notes: [expert_workflow_and_checklists.md § Q1](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/expert_workflow_and_checklists.md), [rules_power_rf_analog_dfm.md § 7, § 19](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/rules_power_rf_analog_dfm.md).
- Bogatin, "20 rules for engineers", [SI Journal](https://www.signalintegrityjournal.com/blogs/4-eric-bogatin-signal-integrity-journal-technical-editor/post/1539-bogatins-20-rules-for-engineers) [P].
- Hubing, seven common errors, [IEEE SCV slides](https://r6.ieee.org/scv-emcs/wp-content/uploads/sites/111/022019ToddHubing.pdf) [P].
- Scripts [C]: [dr_switch_cell_budget.py](../../../tools/research/physics/dr_switch_cell_budget.py), [dr_coupling_oracles.py](../../../tools/research/physics/dr_coupling_oracles.py), [dr_noise_adjoint.py](../../../tools/research/physics/dr_noise_adjoint.py).
- Related: [physics-critics-catalog](physics-critics-catalog.md), [reasoning ideas](../../ideas/physics-first/reasoning.md), [constraint-ir](../architecture/constraint-ir.md), [expert-state-machine](../workflow/expert-state-machine.md).
