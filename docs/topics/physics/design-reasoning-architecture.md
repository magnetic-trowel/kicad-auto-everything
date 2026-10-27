# Design-reasoning architecture: from schematic and fixed constraints to a physics model

**TL;DR**
- The reasoning layer does not produce a placement. It produces a **physics model of the board-to-be**: ports and boundary conditions, an energy-flow graph, current loops ranked by L·di/dt, nodes ranked by C·dv/dt, an aggressor→victim coupling graph per frequency band, and budgets in physical units with sensitivities. One joint placement+routing optimizer consumes that model ([joint-place-route](joint-place-route.md)) [I].
- Physics-first reasoning differs from rule-following in five ways. It works in quantities, not slogans. It measures what matters on *this* board and says what does not. It resolves conflicts as trades in one currency (output deviation against budget), not by priority lists. It treats fixed parts as boundary conditions, not just positions. It can change the stackup, a part, an edge rate, a frequency or the circuit, not only the copper [I].
- Priority comes from **least slack**: the tightness ratio τ = budget ÷ physically achievable floor of each structure sets the optimizer's tiers, seeds and continuation schedule. "Connectors, then ICs, then…" falls out only where the physics agrees [I].
- Roles: the LLM is the physicist (topology, model choice, outputs, bands, predictions, explanations); deterministic solvers make geometry; simulators verify; a human confirms the physics brief. The loop is hypothesize → estimate → simulate only when the margin is inside the estimator's error → compare with budget → modify [I].
- "Clean and beautiful" is mostly **locality of fields**: fast currents close inside small cells, and only DC and defined signals cross cell boundaries. Where neatness is not a proxy for that (long neat parallel buses, uniform widths, mirror-looking but asymmetric circuits), physics wins [I].

## Key facts

The working hypothesis: a layout is the physical realization the schematic leaves out (an unintended R, L, C and M network, field structures, heat paths and a manufactured object). Physics-first layout makes that realization invisible to the circuit's function and to the outside world, within budgets in physical units, at the lowest manufacturing cost and risk. Bogatin's version: aggressor noise exists "only in the traces and white space of the board, not in the schematic" ([what-good-looks-like](../workflow/what-good-looks-like.md)) [P/E]. "Invisible" is measured on the outputs that matter, so a parasitic that moves no output is free (see [schematic-to-physics](schematic-to-physics.md)).

### Rule-following vs physics-first

| Aspect | Rule-following | Physics-first |
|---|---|---|
| Unit | mm, counts, yes/no | nH, mΩ, mV, ps, dB, K, V/mm, each with its conditions |
| Scope of a statement | one rule, local, context-free | one budget per output, shared by every structure that spends it |
| Irrelevance | rules accumulate; nothing says "this does not matter here" | quantifies it: a 90° corner on a 25 mm USB 2.0 line, or a 1 pF crystal stray against a 500 ppm USB budget |
| Conflicts | priority lists, taste | trades in output deviation; shadow prices show what each budget costs |
| Levers | geometry | geometry, stackup, part, edge rate, frequency plan, circuit change |
| Fixed parts | positions to avoid | ports, thermal boundaries, common-mode references, holes in the domain |
| Order | fixed recipe | least slack first, computed per board |
| Typical failure | over-constraint, cargo cult, misses couplings no rule names | model error, missing models, over-trusted estimators |

Hubing's first common error is "blindly following guidelines", and a board meeting 90% of them "may be much worse" than one meeting a few ([placement-methodology](../rules/placement-methodology.md), [myths-and-contested](../rules/myths-and-contested.md)) [P]. Rules still earn a place: they are cached solutions of the physics for a typical context. We use them as priors, seeds and sanity checks, and override them when the physics model has data ([rule-genealogy](rule-basis-set.md)) [I].

### The reasoning pipeline

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

R1 reuses the [design-understanding pipeline](../llm/design-understanding-pipeline.md). R2 replaces name-based [net-role classification](../llm/net-role-classification.md) with measured physics, keeping names as a fallback. R5 makes the budget ledger and dimensioned constraints ([intent-and-why I1/I2](../../ideas/original/intent-and-why.md)) quantitative and mostly automatic. The package is written in the [vocabulary](vocabulary.md) and [physics IR](physics-ir.md); solver choice per question is in the [solver ladder](solver-ladder.md).

### Decomposition: the structures that get ranked

Rows map to the vocabulary's atoms: Loop, Node, Channel, Port, Heat path, Barrier.

| Structure | Aggressor metric | Victim metric | Typical members |
|---|---|---|---|
| Current loop | L·di/dt (V per nH), loop dipole moment I·A | flux capture area, transfer to output | hot loops, gate loops, decap loops, ESD path, sense loops |
| Voltage node | C·dv/dt (A per pF), copper area at swing | node impedance \|Z(f)\|, transfer to output | switch nodes, high-Z analog, crystal, PLL filter |
| Signal path + return | t_r vs electrical length, spectrum to 1/(π t_r) | noise margin, jitter = v_n / slew | clocks, diff pairs, RF lines |
| Port (connector) | common-mode voltage between cable references | ESD/EFT injection, susceptibility | USB-C, power inputs, sensor cables |
| Heat path | W dissipated | ΔT, gradient ∇T (thermal EMF, drift) | FETs, shunts, references, crystals |
| HV gap | V across gap | E field, creepage | isolation barriers, bridge legs |

The coupling graph has an edge for each aggressor–victim pair whose transfer is not negligible, labelled by mechanism (shared impedance, M, C, field, thermal) and by band:

| Band | Physics that governs return and coupling |
|---|---|
| DC – ~100 kHz | resistive spreading: plane gradients (µV/mm), thermal EMF, IR drop |
| ~100 kHz – 30 MHz | inductive: returns follow the trace, M·di/dt, shared inductance |
| 30 MHz – 1 GHz | field and cable modes: common-mode voltage on cables, resonances |
| > 1 GHz | geometry at λ/20: transmission lines, cavities, antennas, corners on RF only |

The band edges are indicative. For returns, the crossover is the vocabulary's regime boundary f_x ≈ R_□/(2π·µ0·h): 0.31 MHz at h = 0.2 mm and 39 kHz at h = 1.6 mm for 1 oz copper ([vocabulary](vocabulary.md)) [C]. Deviation at an output y sums over pairs: Δy(f) ≈ Σ_kj S_j(f) · κ_kj(f) · A_k(f), with aggressor strength A, coupling κ (what the layout controls) and susceptibility S from the schematic simulation.

### Ordering: least slack first

For each structure s, R5 gives a budget b_s and a micro-solver gives the achievable floor m_s (the best value any geometry can reach with these parts and this stackup, e.g. the N7 hot-loop placer run with no competition). τ_s = b_s / m_s.

```
for s in structures: b_s ← sensitivity allocation; m_s ← floor oracle; τ_s ← b_s/m_s
if any τ_s < 1: infeasible → ECO menu (stackup, part, edge rate, frequency, circuit)
rank by τ ascending; break ties by consequence class, then by uncertainty
emit to the optimizer: tiers (ε-lexicographic, N6), seed templates for τ < 2,
      weight-ramp order for continuation, reservations (N5)
on optimizer return: recompute τ from realized spend; re-rank; repeat
```

This is the "most constrained variable first" heuristic of constraint programming, priced in physical units [I]. In the 12 V buck of the [worked cases](worked-thought-experiments.md), the hot-loop budget is 1.05 nH (17 V peak on a 20 V switch node at 13.2 V input) [C] against an estimated floor of about 0.6 nH [I], so τ ≈ 1.7 and it leads. The crystal's 1 mV injection budget is met by 1.5 mm of separation from switch copper on a 0.1 mm prepreg [C], so its τ is large and it simply follows the MCU's pins. τ also answers the expert's question "which circuits are critical?" ([placement-methodology](../rules/placement-methodology.md)), which Pease called tacit; here it is a computed number with an audit trail.

Ordering does not mean sequence. The optimizer is joint, with one objective J = Σ w·φ(spend/budget) ([joint-place-route](joint-place-route.md)). τ sets the weights w, the order in which barriers steepen, and which structures get seed templates, not a place-then-route order.

### The partial layout as boundary conditions

| Fixed item | Physics boundary condition | What the reasoning derives |
|---|---|---|
| Connector | current port with a common-mode reference; the cable is an antenna; ESD injection point | power entry point; which plane regions must stay free of HF current between connectors; TVS and CMC location |
| Heatsink | thermal Dirichlet boundary; a capacitor (tab-to-sink, ~20 pF for a TO-220 on a 0.2 mm pad) to whatever the sink is bonded to | device location; heatsink bonding (to DC− near the bridge, or shielded); keep drift-sensitive parts off the gradient |
| Mounting hole | chassis bond: ESD and CM return path; mechanical stress | where CM current may leave; MLCC keep-outs near flex points |
| Antenna "here" | radiator whose counterpoise is the ground plane; receiver port with a sensitivity floor | plane shape and continuity from the feed, keep-out, spur budgets per clock |
| Outline, slots, keep-outs | holes in the field and flow domain | plane inductance and spreading resistance, current crowding |
| Enclosure | metal or plastic at a distance | antenna detuning, chassis capacitance, airflow |

The thermal and HV side is in [thermal-physics](thermal-physics.md) and the [thermal-hv-mfg ideas](../../ideas/physics-first/thermal-hv-mfg.md); this table is the interface.

### Plans made before geometry

- **DC power flow as a field.** Solve the copper as a sheet with current injected at power ports and drawn at loads, and shape pours to the flow; see [power-copper](power-copper.md) and [copper-shape-synthesis](copper-shape-synthesis.md). The same solve shows where sensitive references must not sit: 0.3 A of load return across a 60 × 40 mm 1 oz plane gives 0.7–4.6 µV/mm everywhere on the board, and a current-free peninsula cuts that about 100× ([dr_coupling_oracles.py](../../../tools/research/physics/dr_coupling_oracles.py)) [C].
- **Signals with their returns.** Every net whose length exceeds about t_r/6 of electrical length, and every loop with a budget, gets an explicit return object (R2 shadow returns, R3 joint via sites in [routing ideas](../../ideas/original/routing.md)).
- **Planes as current-carrying structures.** Assign each plane its DC and AC currents; choose plane roles from them. On a 4-layer board with ≤0.5 A rails, a GND/GND inner pair beats GND/PWR, because the 1.1 mm core gives only 3.5 pF/cm² of plane capacitance and every layer change can then return through a ground via [C].

### Roles and the agent loop

| Actor | Does | Never does |
|---|---|---|
| LLM (physicist) | identifies topology; picks models and stand-ins; turns the spec into outputs and budgets ("what the circuit owes"); names bands; writes a prediction with uncertainty before each simulation; reads residuals; proposes circuit, part, stackup and edge-rate alternatives; explains | emits coordinates, copper, or parasitic values without a tool |
| Deterministic solvers | geometry: joint place+route, micro-placers (N7, N8), plane and pour synthesis, legalization | choose outputs or budgets |
| Simulators and estimators | T0 closed forms, T2 SPICE with back-annotation, T3 field solves for finalists ([solver ladder](solver-ladder.md)) | decide what to simulate |
| Human | confirms the physics brief (outputs, budgets, model assumptions, contested choices); signs off | re-derive what the tools derived |

The loop for each structure:

1. **Hypothesize** a mechanism and a fix ("SW node couples into XIN through C").
2. **Estimate** with a T0 closed form and its calibrated error σ.
3. **Escalate only when it can change the decision**: when |budget − estimate| < z·σ, or when the result could move the structure across a τ tier. This is the [V4 proxy trust radius](../../ideas/original/verification.md) applied to fidelity [I].
4. **Compare** with the budget; log the prediction against the outcome (S4 in [system-loop](../../ideas/original/system-loop.md)).
5. **Modify** from a bounded menu: geometry intent, stackup, part, edge rate, frequency plan, circuit change. Each has a price.

Bogatin's rule 9, "never perform a measurement or simulation without first anticipating the results", is step 1 made mandatory ([what-good-looks-like](../workflow/what-good-looks-like.md)) [P/E].

### Hand-off to and from the joint optimizer

| To the optimizer | Back from the optimizer |
|---|---|
| ports, thermal BCs, holes, fixed antenna region | realized parasitics per structure (nH, fF, pH, mΩ, K) |
| structures with spend models (cheap, ideally differentiable estimators of L, C, M, R, ΔT from geometry) | spend per budget and margin |
| budgets, hard or soft, and sensitivities that convert spend to output deviation | shadow price (Lagrange multiplier) of each budget in area, vias, length or another budget |
| tiers and continuation order from τ; seed templates for τ < 2 | infeasibility certificates (which budgets cannot coexist) |
| discrete alternatives (stackup A/B, edge rate, part swap) as decision variables | Pareto alternatives along the binding budgets |

Explanations come from the binding budgets and their derivation traces (I2), for example: "C_IN sits 0.4 mm from U3 because the hot-loop budget (1.05 nH, from a 17 V peak limit at 13.2 V input) binds; relaxing it by 0.1 nH would free 2 mm² for the crystal." The numbers in such a sentence come from the optimizer's multipliers, never from the LLM [I].

### "Clean and beautiful" as physical coherence

| What experts call good-looking | Physical reason | Agree? |
|---|---|---|
| short, compact power loops | loop L and dipole moment scale with area and plane depth | agree |
| intact planes, no slots under traces | return continuity; low plane inductance | agree |
| symmetric differential structures | mismatch converts differential to common mode | agree, but symmetry of *delay and coupling*, not of shape |
| parts in functional cells along signal flow | fewer long-range currents; short return paths | agree |
| smooth, wide pours on power | uniform current density, lower IR drop and heating | agree for DC and thermal |
| aligned, same-orientation parts | inspection, assembly, reviewability | neutral (manufacturing and cognition) |
| 45° corners, few bends | none below multi-GHz; manufacturing and editability | neutral |
| neat long parallel buses | crosstalk grows with parallel length | **diverge**: physics wants spacing or shorter runs |
| uniform trace widths | width should follow current | **diverge** |
| mirror-looking layouts of asymmetric circuits | currents are not symmetric | **diverge** |
| copper pour everywhere | floating or poorly stitched islands resonate; copper near antennas detunes | **diverge** near RF |

A candidate metric: the **locality index**, the fraction of each aggressor's HF current (above its band crossover) that closes inside its cell's bounding region, from the plane current solution. A layout reads as clean when its fields are explainable by a few local structures. Convention metrics stay as a separate score for review cost ([looks-right-metrics](../verification/looks-right-metrics.md)) [I].

## Recommendations for our system

1. Build R2 (schematic characterization) and R5 (sensitivity budgets) before any new geometry engine; they make every later critic and optimizer term numeric ([schematic-to-physics](schematic-to-physics.md)) [I].
2. Compute τ for every structure and hand tiers, seeds and continuation order to the joint optimizer; treat τ < 1 as an ECO question before optimization [I].
3. Ingest fixed items as typed boundary-condition objects (port, thermal BC, chassis bond, radiator, hole), not as locked footprints only [I].
4. Give the LLM a physicist's toolset (model selection, prediction log, residual reader, ECO menu) and no geometry tools [I].
5. Report the locality index and the binding budgets with shadow prices alongside convention metrics; never let a convention term override a physics budget [I].

## Conflicts and open questions

- [hybrid-architecture-options](../architecture/hybrid-architecture-options.md) Option A and [placement-methodology](../rules/placement-methodology.md) describe staged orders (mechanical → anchors → templates → … → route). We keep their substrate but replace the stage order with τ-derived priorities inside one joint optimizer.
- τ needs a floor oracle per structure class; only the hot loop (N7) and decap assignment (N8) have one designed. Floors for coupling budgets (crystal, ADC input) are weaker because "far enough" depends on everything else.
- The locality index is untested, and no study links it, or any aesthetic, to measured EMC or reviewer acceptance ([what-good-looks-like](../workflow/what-good-looks-like.md)).
- How an LLM performs at model selection and residual reading is unmeasured; spatial benchmarks say nothing about it ([spatial-reasoning-limits](../llm/spatial-reasoning-limits.md)).

## Sources

- research notes: [expert_workflow_and_checklists.md § Q1](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/expert_workflow_and_checklists.md), [rules_power_rf_analog_dfm.md § 7, § 19](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/rules_power_rf_analog_dfm.md)
- Bogatin, "20 rules for engineers", [SI Journal](https://www.signalintegrityjournal.com/blogs/4-eric-bogatin-signal-integrity-journal-technical-editor/post/1539-bogatins-20-rules-for-engineers) [P]
- Hubing, seven common errors, [IEEE SCV slides](https://r6.ieee.org/scv-emcs/wp-content/uploads/sites/111/022019ToddHubing.pdf) [P]
- our scripts: [dr_switch_cell_budget.py](../../../tools/research/physics/dr_switch_cell_budget.py), [dr_coupling_oracles.py](../../../tools/research/physics/dr_coupling_oracles.py), [dr_noise_adjoint.py](../../../tools/research/physics/dr_noise_adjoint.py) [C]

See also: [schematic-to-physics](schematic-to-physics.md), [worked-thought-experiments](worked-thought-experiments.md), [joint-place-route](joint-place-route.md), [physics-critics](physics-critics-catalog.md), [reasoning ideas](../../ideas/physics-first/reasoning.md), [constraint-ir](../architecture/constraint-ir.md), [expert-state-machine](../workflow/expert-state-machine.md)
