# Physics-first layout: the philosophy

**TL;DR**
- **A circuit is Maxwell's equations at zeroth order. Layout adds a series of corrections that converges only inside the nearest natural mode** (the gentleness criterion G). Physics-first layout keeps every part of what the schematic leaves out in one of three states:
  - *invisible*: small, and inside that radius;
  - *known*: budgeted, with an uncertainty;
  - *designed*: promoted into the circuit with a spec, such as a line, a damper, a sense path or an antenna.
  
  See [foundations](foundations.md).
- **Seven principles, plus one for damage, derive 132 of 160 audited rules of thumb**: 51 everywhere and 81 inside a stated regime. The principles survive; the millimetres mostly don't. Only 12 of the 67 numbers the rules quote can be derived ([derivation-audit](derivation-audit.md)).
- **"What a conductor is doing" is computable.** For each piece of copper and each frequency band, it is the column of exact counterfactuals on every budget. A netlist keeps only which pins share copper. Passports for a whole board need one matrix factorization per band, and they matched brute-force re-solves to 2×10⁻⁹ [C] ([lens-cd](lens-cd.md), [real-board-passports](real-board-passports.md)).
- **Two classes of objective need different machinery.** Self terms (loss, loop inductance, thermal resistance) relax to convex problems with certified floors. Interaction terms (couplings, EMI) are sign-indefinite residuals, judged by counterfactuals. The edit spectrum Σ c_i/(1 − λ_i) prices any copper edit exactly, and its largest λ is the trust radius ([physics-core-v2](physics-core-v2.md)).
- **Every number is model against model.** The core mathematics is verified by independent methods; a pre-registered validation program decides the rest ([verification-and-limits](verification-and-limits.md), [validation-program](validation-program.md)).

Tags: [P] primary, [S] secondary, [V] vendor, [I] inference, [C] computed by scripts in [`tools/research/physics/`](../../../tools/research/physics/), quasi-static and uncalibrated unless stated. Ideas: [catalog](../../ideas/physics-first/README.md).

## Key facts

### The starting point: gentleness

A schematic keeps Maxwell's exact, metric-free half: charge conservation and Faraday's law per cycle. It lumps the material half into parts. It stays right while a few ratios stay small:
- electrical length θ = ωℓ/v;
- the series and shunt parasitic ratios ε_L = θ·Z0/Z and ε_C = θ·Z/Z0;
- the plane's resolution length ℓ_m = R_s/(π·μ0·f) against feature size;
- insulator relaxation;
- thermal feedback ([lens-ls](lens-ls.md)).

**G, the gentleness criterion.** Eliminating any hidden coordinate (a mode, a reflection, an eddy pattern, temperature, an edit's own current redistribution) gives the circuit a factor (I − G)⁻¹ = Σ Gⁿ. "Schematic plus parasitics" stops at first order. That is valid only while G's spectral radius is below 1, for example |δL/L| < 1/Q at a resonance. Beyond that radius, more fidelity does not help: the coordinate must join the circuit as a line, a mode or a fixed point. Two moves keep a layout gentle: **match** (removes the mode) and **damp** (moves it off the band). They are one idea ([foundations](foundations.md) §1).

### Principles

| # | Principle | One line |
|---|---|---|
| F1 | Conservation and topology | Total current (conduction plus displacement) always closes, and each cycle's EMF is its flux. This is exact once the chassis, cable and heatsink join as a world node. Only cycle sums are physical |
| F2 | Linear, passive, reciprocal, causal media | Copper and laminate superpose per band with Z = Zᵀ. All model error lives here; nonlinearity lives in the parts |
| F3 | Extremum | Nature minimizes energy inside the copper we draw: Thomson at DC, minimum magnetic energy at HF. Self terms are monotone and convex in copper; the R–L band is only stationary |
| F4 | Symmetry and duality | Images, parity, sheet duality (cut ↔ needle) and wedge scaling make geometry exact. A broken symmetry is a source |
| F5 | Locality and scale | Every interaction has a decay class and a natural length. A plane mirrors only patterns larger than ℓ_m; delay ≥ ℓ/v |
| F6 | Dissipation and fluctuation | Each mode's losses add as 1/Q. Every loss is a noise and heat source; heat paths are electrical paths |
| F7 | Decisions under belief | Learn when the value of information exceeds its cost. Rank with differences, certify with absolutes, buy robustness when cheaper than knowledge |
| D | Extremes and accumulation | Breakdown, fracture, fatigue and ageing follow local maxima and accumulated rates, not energies. Energy principles alone cannot see a corner; damage can ([derivation-audit](derivation-audit.md)) |

### Design theorems that replace the rules

Full statements, conditions and the derivation tree are in [foundations](foundations.md) §4 and [foundations-derivations](foundations-derivations.md).

| Theorem | Statement | Replaces |
|---|---|---|
| T1 Impedance level | Length sets θ, shape sets Z0. A piece stores the least energy when Z0 = ΔV/ΔI, and is then a pure delay. Between resistive ends, a mismatch costs only phase at first order and magnitude at second, so matching matters most where a reactive part makes a resonance. Damp with R = Z0. Self terms only | "Short and wide", "small loop", PDN target impedance, RF matching, snubber sizing |
| T2 Copper damping | The copper-only Q of wide copper is h/max(δ, δ²/t): ½ at the R–L crossover and 30–170 for hot-loop rings. Copper damps plane pairs below ~30 MHz, not rings | Relying on copper loss or "more copper" to tame ringing |
| T3 Self vs interaction | An interaction is a difference of self energies. It has no fixed sign, Rayleigh monotonicity doesn't protect it, and per-piece attributions cancel | "Pour everything; more copper never hurts" (true for self terms only) |
| T4 Exact edit pricing | Exact change = Σ c_i/(1 − λ_i), where the c_i sum to the first-order price. A slit costs (2/π)·R_s·ln sec(πx/2) for intercepted current fraction x | "A cut costs the copper it removes"; per-area sensitivity maps |
| T5 Closed loops | Budgets live on cycles. A two-point AC voltage depends on the path | "Ground bounce between A and B" |
| T6 The world is a node | I_CM = −jω·Σ C_i,ext·V_i with world-referenced V. A bond moves a displacement edge inside the boundary | "Ground the heatsink", "connectors on one edge" |
| T7 Topology is exact | Articulation points pass zero foreign current. A neck leaks ∝ w² on the aggressor's flank and ∝ w⁴ at its stagnation point. Vias, cuts and joins are discrete events | Star grounds, single ties, "don't cross a split" |
| T8 Band-limited mirrors | A plane images patterns larger than ℓ_m. Decaps and stitching vias form one wire medium, ω² = ω_p² + v²k² | Decap distance, λ/20 stitching |
| T9 Symmetry residuals | Mode conversion happens where the current-division factor χ changes. Over a plane, loops are current-forced (height helps) and wide dv/dt nodes voltage-forced (height barely helps) | 3W, guards, "tight coupling" |
| T10 Designed dissipation | A mode whose excitation × Q exceeds budget needs a tuned loss channel at its antinode | Snubber folklore, "stitch the edges" |
| T11 Loss vs damage | Loss is an energy norm, finite at any corner. Damage is local and sees the corner singularity r^(π/α−1) | "Never 90°" (true for damage, HV and pulses only) |
| T12 Exactness ladder | Topology (exact) → variational floors (certified) → rank-k counterfactuals (exact in the model) → closed forms → fields (±σ) → measurement | One fidelity ladder |
| T13 Ranking vs compliance | Bias cancels in a ranking but not in a verdict. Cut sensitivity or uncertainty, whichever is cheaper | "Proxies are good enough" |

### What a conductor is doing

A piece of copper (strip, via, pad cell, plane region) does whatever would change if it changed: its column of exact counterfactuals on every budget, per band ([foundations](foundations.md) §6). Its *passport* explains the column through eight things:
1. currents by source;
2. charges and where their field lines end;
3. stored, dissipated and radiated energy;
4. topological role and leverage;
5. imbalance and impedance level;
6. share of each mode's damping, noise and heat;
7. field stress and damage rate;
8. belief, with exactness and lineage.

Its *jobs* are the signs of that column, and "designed" or "parasitic" belongs to a (piece, job) pair.

A netlist collapses each conductor to a point. That is how an autorouter can be DRC-correct and physically wrong: two layouts of one netlist differ only in what the netlist drops.

Computed so far [C]:
- **Synthetic buck plus ADC board** ([lens-cd](lens-cd.md)): passports for 4,415 pieces × 4 bands × 10 budgets.
  - 62% of the ADC's DC error sits in two plane regions.
  - One 0.5 mm slot bridge removes 78% of the high-frequency coupling.
  - Deleting "useless" copper in one batch cost 7.3× its summed single costs.
- **A real open board** (BLDCM-Power, MIT; 4 layers, 32 mm, three-phase bridge with shunts; [real-board-passports](real-board-passports.md)). The exact DC passport takes seconds, and removal costs match brute force to 3.5×10⁻¹¹. Four findings no netlist or DRC shows:
  - The bridge IC's exposed pad has no vias and joins ground through one corridor.
  - The input capacitors' ground is an island: its vias carry under 5% of DC current but 86% of the switching current.
  - The 3.3 V plane carries the hot loop's largest high-frequency current, all of it induced. Without the plane, loop inductance would be 2.8× higher.
  - One via in the exposed pad cuts loop inductance by 15%, the best of 511 candidate sites (the median site gives 0.4%).
- **Pilot floor census of 14 pours on four open boards** ([validation-program](validation-program.md)): shapes sit near their certified floors (median 4% avoidable). Losses come from thermal-relief gaps and plane partitioning.

### The machine

```
schematic + datasheets + fixed constraints (outline, holes, connectors, antenna, heatsink, enclosure, cables)
  │  simulate the schematic: per-net swing, dv/dt, di/dt, spectra; susceptibilities by adjoint
  ▼
physics brief (pcb-intent 0.4): ports with named returns, closed-loop budgets, world conductors,
  boundary conditions, least-slack priorities from certified floors
  ▼
joint placement + routing + copper optimizer           ◄── physics core v2 (8 kernels, one factorization
  state: poses · route topologies · copper fields          per band and topology epoch): topology engine,
  self terms: convex, floor-scheduled first                complex sheet operator, complex-image PEEC,
  interaction terms: exact counterfactual quotes           response/edit spectrum, floors, modal Q ledger,
  topological events bound every gradient                  morphology, belief/VOI
  G ≥ 1 → change representation (mode, line, damper)
  ▼
legalize inside the loop → kicad-cli DRC (referee)
  ▼
passports + critics (separate physics scorecard) → LLM explains binding budgets and proposes priced
operators (geometry, stackup, part, edge rate, damper, bond) → human confirms
```

Details: [physics-core-v2](physics-core-v2.md), [API](physics-core-v2-api.md), [joint-place-route](joint-place-route.md), [design-reasoning-architecture](design-reasoning-architecture.md), [physics-critics](physics-critics.md). On toy boards, joint search improves a sequential start 10 times out of 10 (−18%) and ties an equal-CPU restart portfolio, 5 of 10 ([joint-place-route-experiment](joint-place-route-experiment.md)). It is a refiner after diverse starts.

### Answers to the questions that started this

| Question | Answer now |
|---|---|
| Curves instead of right angles? | Only where damage, HV, fast pulses (shorter than ~w²/κ) or RF edges below ~30 ps make the corner field matter (T11). For loss, a sharp corner adds ~0.56 squares and changes peak temperature by under 0.5% [C]. Fabs make curves at no extra cost, so allow them where a budget pays. |
| Pours instead of thin traces? | Yes for DC feeds and returns. Pour shapes already sit near their floor (median 4% avoidable); the leverage is in partitioning and in pad connections. Switch-node copper is set by its coupling to the outside, not its self optimum (T1 vs T3). |
| How much R, L and C, and which to maximize? | Per piece, from ΔV/ΔI against Z0 (T1). Low-impedance pieces (input caps, plane pairs) want wide copper over thin dielectric. High-impedance nodes want little capacitance. Useful parasitics to maximize: plane-pair capacitance, go/return overlap, and designed damping resistance (T10). |
| Keep high current away from sensitive lines? | For loops, a close plane matters more than distance (coupling ∝ h_a·h_v). For wide dv/dt copper, height barely helps and distance or burying the victim matters (T9). For precision analog, keep foreign current out of the measurement cycle (T5, T7). |
| A physics engine, SPICE, open RF tools? | Eight kernels in one core, with SPICE adjoints for the circuit and full-wave (openEMS, Palace) only for finalists and calibration ([physics-core-v2](physics-core-v2.md), [open-solvers](open-solvers.md)). |
| Near-infinite compute? | Exact counterfactuals for every piece, certified floors, quality-diversity search, and surrogates trained on field-solver labels. But compute does not fix a divergent series or unknown cables: those need a new representation or a measurement ([validation-program](validation-program.md)). |
| Place and route together? | Yes, on a topology-carrying state with physics as the shared objective, run as a refiner after diverse starts ([joint-place-route](joint-place-route.md)). |

## Recommendations for our system

1. **Measure first:** order the ℓ_m return-band coupon and lay out both arms of the pre-registered first board ([validation-program](validation-program.md), [validation-coupons](validation-coupons.md)).
2. **Build kernels K1, K2 and K4 of [physics-core-v2](physics-core-v2.md)** (topology, sheet operator, exact response). Run them on one real 4-layer board with the mutation benchmark (PC29). Pass means exactness against re-factorization, the trust radius logged on every quote, and a job verb changing at every planted fault.
3. **Turn the [derivation-audit-table](derivation-audit-table.md) into rule-pack records** with regime predicates computed from the board, so regime-bound rules fire only where they hold and arbitrary numbers come from budgets.
4. **Run a floor and G census on the qualified bench suite**, as a separate report that never touches cp1/cpk.

## Conflicts and open questions

- **Measurement.** No principle or number here has been checked against a measurement. The validation program lists 11 kill criteria.
- **Joint terms.** No principle yet prices self and interaction terms jointly with guarantees.
- **Outside F2.** Nonlinear victims, ESD and surge fall outside linear media.
- **Off-board unknowns.** Their share of decision value is 10–84% depending on priors ([lens-in](lens-in.md), [verification-and-limits](verification-and-limits.md)).
- **Where rules win.** Good rules beat model optima when the decisive unknowns are off the board or the mechanism is unmodelled. The steelman of the rule-based expert in [verification-and-limits](verification-and-limits.md) is the baseline the validation program must beat.

## Sources

All [C] numbers come from scripts in [`tools/research/physics/`](../../../tools/research/physics/), listed in [tools/research/README](../../../tools/research/README.md). Primary sources are cited in each topic doc. Research notes behind the rules: [rules_highspeed_emi.md](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/rules_highspeed_emi.md), [rules_power_rf_analog_dfm.md](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/rules_power_rf_analog_dfm.md), [verification_rules.md](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_rules.md).

## Map of this area

| Read it for | Docs |
|---|---|
| The core | [foundations](foundations.md), [foundations-derivations](foundations-derivations.md) |
| Rules decompressed and tested | [rule-basis-set](rule-basis-set.md), genealogy ([power](rule-genealogy-power-analog-thermal.md), [SI/EMI/RF](rule-genealogy-si-emi-rf.md), [routing/DFM](rule-genealogy-routing-style-dfm.md)), [derivation-audit](derivation-audit.md), [table](derivation-audit-table.md) |
| First-principles lenses | [VP](lens-vp.md), [CT](lens-ct.md), [SY](lens-sy.md), [LS](lens-ls.md), [TH](lens-th.md), [IN](lens-in.md), [CD](lens-cd.md) |
| Conductor understanding | [lens-cd](lens-cd.md), [real-board-passports](real-board-passports.md) |
| The system | [physics-core-v2](physics-core-v2.md), [API](physics-core-v2-api.md), [vocabulary](vocabulary.md), [physics-ir](physics-ir.md), [examples](physics-ir-examples.md), [design-reasoning-architecture](design-reasoning-architecture.md), [schematic-to-physics](schematic-to-physics.md), [worked-thought-experiments](worked-thought-experiments.md) |
| Optimization | [joint-place-route](joint-place-route.md), [experiment](joint-place-route-experiment.md), [physics-in-the-loop-optimization](physics-in-the-loop-optimization.md), [copper-shape-synthesis](copper-shape-synthesis.md) |
| Domain physics | [power-copper](power-copper.md), [pdn-and-commutation](pdn-and-commutation.md), [fields-si-emi](fields-si-emi.md), [fields-emi-budget](fields-emi-budget.md), [rf-geometry](rf-geometry.md), [thermal-physics](thermal-physics.md), [hv-and-manufacturing-physics](hv-and-manufacturing-physics.md) |
| Engines | [open-solvers](open-solvers.md), [solver-ladder](solver-ladder.md) |
| Judgement and truth | [physics-critics](physics-critics.md), [catalog](physics-critics-catalog.md), [validation](physics-critics-validation.md), [verification-and-limits](verification-and-limits.md), [validation-program](validation-program.md), [coupons](validation-coupons.md) |
| Synthesis | [cross-workstream-synthesis](cross-workstream-synthesis.md), [research-gaps](research-gaps.md), [cross-domain-lessons](cross-domain-lessons.md) |

See also: [ideas catalog](../../ideas/physics-first/README.md) · [digest](../../digests/physics-first.md) · [executive report](../../../reports/Physics-first%20PCB%20layout.md)
