# Physics first: lay out what the schematic leaves out

Scope: executive map of physics-first placement and routing (status 2026-10-22): foundations, rule derivation, conductor passports, physics core, joint P&R, validation; conclusions only. Extends the [first report](LLM%20driven%20PCB%20placement%20and%20routing.md): the LLM still authors intent, never copper; what changes is the currency of intent, the solver state and what counts as evidence. Not here: philosophy -> [physics README](../docs/topics/physics/README.md); short version -> [digest](../docs/digests/physics-first.md); ideas -> [catalog](../docs/ideas/physics-first/README.md); build -> [physics-driven-design](../docs/topics/architecture/physics-driven-design.md).
Keys: physics-first, gentleness G, three states, derivation audit, conductor passports, edit spectrum, self vs interaction terms, kernels K1-K8, VAL-1, ℓ_m coupon

Evidence caveat: every [C] number comes from our quasi-static models, checked against closed forms, independent re-derivations and FastHenry (four loops), **never against measurement**. The architecture is untested [I].

## Conclusions

1. **Schematic = Maxwell at zeroth order; layout adds the corrections,** which converge only inside the nearest natural mode. Each part of the realization is in one of three states: invisible (small, inside that radius), known (budgeted with uncertainty), designed (promoted into the circuit as line, damper, sense path or antenna). Matching and damping keep a layout gentle ([foundations](../docs/topics/physics/foundations.md)).
2. **Rules are mostly right physics with conditions dropped.** Seven principles + one for damage derive 132 of 160 audited rules (51 everywhere, 81 inside a stated regime); only 12 of 67 quoted millimetre numbers derive from first principles. Store rules as priors with regime predicates; compute numbers from budgets ([derivation-audit](../docs/topics/physics/derivation-audit.md)).
3. **A system can know what each conductor does:** per-piece, per-band exact counterfactuals on every budget (currents by source, field energies, couplings, heat, stress, topological role). A netlist keeps only which pins share copper, so DRC-correct boards can be physically wrong. Cost: one factorization per band, one diagonal for every piece's removal cost. On a real open motor-drive board passports found an exposed pad without vias, an island capacitor ground carrying 86% of switching current, and the best of 511 via sites (−15% loop inductance) ([lens-cd](../docs/topics/physics/lens-cd.md), [real-board-passports](../docs/topics/physics/real-board-passports.md)).
4. **Two objective classes need different machinery:** self terms (loss, loop L, thermal R) relax to convex problems with certified floors; interaction terms (couplings, EMI) are sign-indefinite residuals judged by counterfactuals. Edit spectrum Σ c_i/(1 − λ_i) prices any edit exactly; its largest λ says when first order fails ([physics-core-v2](../docs/topics/physics/physics-core-v2.md)).
5. **Placement, routing and copper shape belong in one optimizer** on a topology-carrying state, physics as shared objective, fixed parts as boundary conditions; on toy boards it works as a refiner after diverse restarts ([joint-place-route](../docs/topics/physics/joint-place-route.md), [experiment](../docs/topics/physics/joint-place-route-experiment.md)).
6. **Measure first:** order the ℓ_m return-band coupon; lay out the pre-registered two-arm first board (rules vs physics); run floor and mutation benchmarks on real boards ([validation-program](../docs/topics/physics/validation-program.md)).

## Slogans and their physics replacements

| Slogan | Replacement | Key number [C] | Home |
|---|---|---|---|
| "Minimize hot-loop area" | height × squares, or MS2 near a plane; area only without one | equal-area loops differ 1.7×; fixed stackup: MS2 picks best loop 97–100%, area 66–97% | [pdn-and-commutation](../docs/topics/physics/pdn-and-commutation.md), [solver-ladder](../docs/topics/physics/solver-ladder.md) |
| "Short and wide" | impedance level: Z0 → ΔV/ΔI per piece (self terms); switch-node copper set by its outside coupling | SW piece self-optimal at 15 mm, but its external dipole grows 7.5× | [foundations](../docs/topics/physics/foundations.md) T1 |
| "Pour the power nets" | pours for DC feeds; shapes near floor; leverage in partitioning and pad connections | median 4% avoidable on 14 real pours; reliefs cost 7–48% on one board | [validation-program](../docs/topics/physics/validation-program.md) |
| "No 90° corners" | matter for damage, HV, short pulses, sub-30 ps edges; not loss | 0.56 squares; peak T within 0.5% | [foundations](../docs/topics/physics/foundations.md) T11, [power-copper](../docs/topics/physics/power-copper.md) |
| "Don't cut the plane", "return via within 200 mil" | exact cut law + return-path EMF on closed loops | slit cost (2/π)·R_s·ln sec(πx/2), derived four independent ways; slot under a trace ≈ 0.08–0.13 nH/mm | [lens-ct](../docs/topics/physics/lens-ct.md), [fields-si-emi](../docs/topics/physics/fields-si-emi.md) |
| "Stitch at λ/20" | wire medium ω² = ω_p² + v²k²; pitch from isolation needed | 10 mm pitch screens 2.45 GHz by 36 dB | [lens-ls](../docs/topics/physics/lens-ls.md), [validation-coupons](../docs/topics/physics/validation-coupons.md) |
| "Keep high current away", "3W", guards | planes break E/M duality: height helps loops, not wide dv/dt copper; guards ~1% over thin dielectric | loop coupling ∝ h_a·h_v; node coupling ∝ h^0.19 | [lens-sy](../docs/topics/physics/lens-sy.md) |
| "Star ground for analog" | topology + R–L length band; foreign current out of the measurement cycle | star pays only below ~6 kHz at 10 mm on 1 oz | [derivation-audit](../docs/topics/physics/derivation-audit.md), [lens-ct](../docs/topics/physics/lens-ct.md) |
| Snubbers "as close as possible" | designed dissipation: tuned loss channel at the mode's antinode | same Q at 72 vs 216 mW | [lens-th](../docs/topics/physics/lens-th.md) |
| "Ground the heatsink", "connectors on one edge" | the world is a node: close displacement current locally | heatsink to DC− vs chassis: −20 to −65 dB cable CM; co-located cables 6–48 dB by orientation | [lens-ct](../docs/topics/physics/lens-ct.md), [validation-coupons](../docs/topics/physics/validation-coupons.md) |
| "Copper under inductors: keep out" | keep the plane; body-sized cut-out is worst | loss 1.05–1.4× with a cut-out | [derivation-audit](../docs/topics/physics/derivation-audit.md) |

## Architecture layers

| Layer | What | Home |
|---|---|---|
| Foundations | gentleness G; principles F1–F7 + damage; theorems T1–T13 | [foundations](../docs/topics/physics/foundations.md) |
| Understanding | simulate the schematic: net passports, adjoint susceptibilities (periodic adjoints for switching); conductor passports; world node mandatory | [schematic-to-physics](../docs/topics/physics/schematic-to-physics.md), [lens-cd](../docs/topics/physics/lens-cd.md) |
| Language | `pcb-intent` 0.4: ports with named returns, closed-loop budgets, world conductors, Beliefs with exactness | [physics-core-v2-api](../docs/topics/physics/physics-core-v2-api.md), [vocabulary](../docs/topics/physics/vocabulary.md) |
| Core | 8 kernels on one factorization per band: topology engine, complex sheet operator, complex-image PEEC, response/edit spectrum, floors, modal Q ledger, morphology, belief/VOI | [physics-core-v2](../docs/topics/physics/physics-core-v2.md); engine design [physics-engine-design](../docs/topics/architecture/physics-engine-design.md) |
| Optimizer | joint P&R + copper on a topology-carrying state; convex self terms scheduled first, interaction terms take exact quotes, topological events bound gradients; representation switches when G ≥ 1 | [joint-place-route](../docs/topics/physics/joint-place-route.md), [physics-in-the-loop-optimization](../docs/topics/physics/physics-in-the-loop-optimization.md) |
| Judgement | physics scorecard separate from cp1/cpk + DRC-equivalent mutation benchmark; rankings never certify compliance | [physics-critics](../docs/topics/physics/physics-critics.md), [lens-in](../docs/topics/physics/lens-in.md) |
| LLM | reads priced menus, sensitivities, job verbs, binding budgets; writes mechanism hypotheses, allocations, operator choices, never coordinates | [physics-core-v2](../docs/topics/physics/physics-core-v2.md), [design-reasoning-architecture](../docs/topics/physics/design-reasoning-architecture.md) |

## First experiments

All run beside the [benchmark harness](../bench/README.md) without changing its scoring (CLAUDE.md); kill criteria in [validation-program](../docs/topics/physics/validation-program.md).

| # | Experiment | Decides |
|---|---|---|
| 1 | ℓ_m return-band coupon (VOI-ranked first) | whether a transition-band solver is built; precision-ground rules |
| 2 | VAL-1: one 4-layer board (buck, ESP32-S3 + USB, 24-bit ADC, fixed USB-C and holes) laid out by rules and by physics, predictions registered, measured in an enclosure with real cables | the thesis |
| 3 | kernels K1/K2/K4 on a real 4-layer bench board + mutation benchmark | whether exact passports and job verbs catch DRC-clean physics faults |
| 4 | floor and G census on the qualified suite, human vs router boards | where physics optimization can pay; where first order fails |
| 5 | rule packs with regime predicates from the derivation table | whether regime gating cuts false violations without missing real ones |
| 6 | joint vs equal-CPU portfolio on real boards (JPR46) | whether joint search earns its cost beyond refinement |

## Risks and open questions

- No measurement yet: every [C] number needs an independent method, a refinement study and a reference validated where the optimizer selects before it steers an optimizer ([verification-and-limits](../docs/topics/physics/verification-and-limits.md)).
- Rules win when decisive unknowns are off the board (cables, enclosure, test setup) or the mechanism is unmodelled; the steelman rule-based expert in [verification-and-limits](../docs/topics/physics/verification-and-limits.md) is the baseline VAL-1 must beat.
- Nonlinear victims, ESD and surge fall outside F2: co-simulation needed.
- No principle yet prices self and interaction terms jointly with guarantees.
- Licences: FastHenry internal calibration only (MIT non-commercial notice); Ki-PIDA AGPL. Ship our PEEC, PyPEEC, FasterCap, openEMS, Palace ([open-solvers](../docs/topics/physics/open-solvers.md)).
