# Physics first: lay out what the schematic leaves out

This report summarizes physics-first placement and routing: the foundations, the derivation of the human rules, the conductor-centric model, the physics core, joint placement and routing, and the validation program. It extends the [first report](LLM%20driven%20PCB%20placement%20and%20routing.md): the LLM still authors intent, never copper. What changes is the currency of that intent, the state the solvers carry, and what counts as evidence. Philosophy: [docs/topics/physics/README](../docs/topics/physics/README.md); short version: [digest](../docs/digests/physics-first.md); ideas: [catalog](../docs/ideas/physics-first/README.md). Status: 2026-10-22.

**Evidence caveat.** Every number tagged [C] comes from our own quasi-static models. They were checked against closed forms, independent re-derivations and FastHenry (four loops), but **never against measurement**. The architecture is untested [I].

## 1. Bottom line

- **The schematic is Maxwell's equations at zeroth order; layout adds the corrections.** The corrections converge only inside the nearest natural mode. Physics-first layout keeps each part of the board's realization in one of three states ([foundations](../docs/topics/physics/foundations.md)):
  - **invisible:** small, and inside that radius;
  - **known:** budgeted with an uncertainty;
  - **designed:** promoted into the circuit as a line, a damper, a sense path or an antenna.
  
  Matching and damping are the two moves that keep a layout gentle.
- **The rules are mostly right physics with the conditions dropped.** Seven principles plus one for damage derive 132 of 160 audited rules: 51 everywhere, 81 inside a stated regime. The millimetres mostly don't derive: only 12 of 67 quoted numbers come from first principles ([derivation-audit](../docs/topics/physics/derivation-audit.md)). Store rules as priors with regime predicates. Compute numbers from budgets.
- **A system can know what each conductor is doing.** That knowledge is the per-piece, per-band column of exact counterfactuals on every budget: currents by source, field energies, couplings, heat, stress and topological role. A netlist keeps only which pins share copper, which is why DRC-correct boards can be physically wrong. It is exact and cheap to compute: one factorization per band, and one diagonal for the removal cost of every piece ([lens-cd](../docs/topics/physics/lens-cd.md), [real-board-passports](../docs/topics/physics/real-board-passports.md)).
- **Two classes of objective need different machinery.**
  - Self terms (loss, loop inductance, thermal resistance) relax to convex problems with certified floors.
  - Interaction terms (couplings, EMI) are sign-indefinite residuals, judged by counterfactuals.
  
  The edit spectrum Σ c_i/(1 − λ_i) prices any edit exactly, and its largest λ tells when first-order reasoning fails ([physics-core-v2](../docs/topics/physics/physics-core-v2.md)).
- **Placement, routing and copper shape belong in one optimizer** on a topology-carrying state, with physics as the shared objective and fixed parts as boundary conditions. On toy boards it works as a refiner after diverse restarts ([joint-place-route](../docs/topics/physics/joint-place-route.md), [experiment](../docs/topics/physics/joint-place-route-experiment.md)).
- **What to do first is measure.** Order the ℓ_m return-band coupon. Lay out the pre-registered two-arm first board (rules vs physics). Run the floor and mutation benchmarks on real boards ([validation-program](../docs/topics/physics/validation-program.md)).

## 2. What the physics changes

| Slogan | Physics replacement | Key number [C] | Doc |
|---|---|---|---|
| "Minimize hot-loop area" | Height × squares or MS2 near a plane; area only without one | Equal-area loops differ 1.7×. At a fixed stackup MS2 picks the best loop 97–100%, area 66–97% | [pdn-and-commutation](../docs/topics/physics/pdn-and-commutation.md), [solver-ladder](../docs/topics/physics/solver-ladder.md) |
| "Short and wide" | Impedance level: Z0 toward ΔV/ΔI per piece (self terms); switch-node copper set by its outside coupling | SW piece self-optimal at 15 mm, but its external dipole grows 7.5× | [foundations](../docs/topics/physics/foundations.md) T1 |
| "Pour the power nets" | Pours for DC feeds; shapes already near their floor; leverage in partitioning and pad connections | Median 4% avoidable on 14 real pours; reliefs cost 7–48% on one board | [validation-program](../docs/topics/physics/validation-program.md) |
| "No 90° corners" | Corners matter for damage, HV, short pulses and sub-30 ps edges, not for loss | 0.56 squares; peak T within 0.5% | [foundations](../docs/topics/physics/foundations.md) T11, [power-copper](../docs/topics/physics/power-copper.md) |
| "Don't cut the plane", "return via within 200 mil" | Exact cut law plus return-path EMF on closed loops | Slit cost (2/π)·R_s·ln sec(πx/2), derived independently four ways; a slot under a trace ≈ 0.08–0.13 nH/mm | [lens-ct](../docs/topics/physics/lens-ct.md), [fields-si-emi](../docs/topics/physics/fields-si-emi.md) |
| "Stitch at λ/20" | Wire medium: ω² = ω_p² + v²k²; pitch from the isolation needed | 10 mm pitch screens 2.45 GHz by 36 dB | [lens-ls](../docs/topics/physics/lens-ls.md), [validation-coupons](../docs/topics/physics/validation-coupons.md) |
| "Keep high current away", "3W", guards | Planes break E/M duality: height helps loops, not wide dv/dt copper; guards ~1% over thin dielectric | Loop coupling ∝ h_a·h_v; node coupling ∝ h^0.19 | [lens-sy](../docs/topics/physics/lens-sy.md) |
| "Star ground for analog" | Topology plus the R–L length band; foreign current kept out of the measurement cycle | Star pays only below ~6 kHz at 10 mm on 1 oz | [derivation-audit](../docs/topics/physics/derivation-audit.md), [lens-ct](../docs/topics/physics/lens-ct.md) |
| Snubbers "as close as possible" | Designed dissipation: a tuned loss channel at the mode's antinode | Tuned snubber: same Q at 72 vs 216 mW | [lens-th](../docs/topics/physics/lens-th.md) |
| "Ground the heatsink", "connectors on one edge" | The world is a node: close displacement current locally | Heatsink bond to DC− vs chassis: −20 to −65 dB cable CM; co-located cables 6–48 dB by orientation | [lens-ct](../docs/topics/physics/lens-ct.md), [validation-coupons](../docs/topics/physics/validation-coupons.md) |
| "Copper under inductors: keep out" | Keep the plane; a body-sized cut-out is worst | Loss 1.05–1.4× with a cut-out | [derivation-audit](../docs/topics/physics/derivation-audit.md) |

## 3. The architecture

| Layer | What | Docs |
|---|---|---|
| Foundations | Gentleness G; principles F1–F7 plus damage; theorems T1–T13 | [foundations](../docs/topics/physics/foundations.md) |
| Understanding | Simulate the schematic: net passports and adjoint susceptibilities, with periodic adjoints for switching. Build conductor passports; the world node is mandatory | [schematic-to-physics](../docs/topics/physics/schematic-to-physics.md), [lens-cd](../docs/topics/physics/lens-cd.md) |
| Language | `pcb-intent` 0.4: ports with named returns, closed-loop budgets, world conductors, Beliefs with exactness | [physics-core-v2-api](../docs/topics/physics/physics-core-v2-api.md), [vocabulary](../docs/topics/physics/vocabulary.md) |
| Core | 8 kernels sharing one factorization per band: topology engine, complex sheet operator, complex-image PEEC, response/edit spectrum, floors, modal Q ledger, morphology, belief/VOI | [physics-core-v2](../docs/topics/physics/physics-core-v2.md) |
| Optimizer | Joint P&R + copper on a topology-carrying state. Convex self terms are scheduled first, interaction terms take exact quotes, and topological events bound gradients. The representation switches when G ≥ 1 | [joint-place-route](../docs/topics/physics/joint-place-route.md), [physics-in-the-loop-optimization](../docs/topics/physics/physics-in-the-loop-optimization.md) |
| Judgement | A physics scorecard separate from cp1/cpk, plus a DRC-equivalent mutation benchmark; rankings never certify compliance | [physics-critics](../docs/topics/physics/physics-critics.md), [lens-in](../docs/topics/physics/lens-in.md) |
| LLM | Reads priced menus, sensitivities, job verbs and binding budgets. Writes mechanism hypotheses, allocations and operator choices, never coordinates | [physics-core-v2](../docs/topics/physics/physics-core-v2.md), [design-reasoning-architecture](../docs/topics/physics/design-reasoning-architecture.md) |

## 4. Roadmap: first experiments

Everything runs beside the [benchmark harness](../bench/README.md) without changing its scoring (CLAUDE.md). Kill criteria are listed in [validation-program](../docs/topics/physics/validation-program.md).

| # | Experiment | Decides |
|---|---|---|
| 1 | ℓ_m return-band coupon (VOI-ranked first) | Whether a transition-band solver is built; precision-ground rules |
| 2 | VAL-1: one 4-layer board (buck, ESP32-S3 + USB, 24-bit ADC, fixed USB-C and holes) laid out by rules and by physics, predictions registered, measured in an enclosure with real cables | The thesis itself |
| 3 | Kernels K1/K2/K4 on a real 4-layer bench board with the mutation benchmark | Whether exact passports and job verbs catch DRC-clean physics faults |
| 4 | Floor and G census on the qualified suite, human vs router boards (separate report) | Where physics optimization can pay; where first-order fails |
| 5 | Rule packs with regime predicates from the derivation table | Whether regime-gated rules cut false violations without missing real ones |
| 6 | Joint vs equal-CPU portfolio on real boards (JPR46) | Whether joint search earns its cost beyond refinement |

## 5. Risks and open questions

- **No measurement yet.** Every [C] number must pass three checks before it steers an optimizer: an independent method, a refinement study, and a reference validated where the optimizer selects ([verification-and-limits](../docs/topics/physics/verification-and-limits.md)).
- **Where rules win.** Robust rules beat model optima when the decisive unknowns are off the board (cables, enclosure, test setup) or the mechanism is unmodelled. The steelman of the rule-based expert in [verification-and-limits](../docs/topics/physics/verification-and-limits.md) is the baseline VAL-1 must beat.
- **Outside the linear frame.** Nonlinear victims, ESD and surge fall outside F2 and need co-simulation.
- **No joint guarantees.** No principle yet prices self and interaction terms jointly with guarantees.
- **Licences.** FastHenry is internal calibration only (MIT non-commercial notice), and Ki-PIDA is AGPL. Ship our PEEC, PyPEEC, FasterCap, openEMS and Palace ([open-solvers](../docs/topics/physics/open-solvers.md)).
