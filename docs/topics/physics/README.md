# Physics-first layout: area map

Scope: map of docs/topics/physics (one row per doc: what it holds, Keys) plus one-line answers to the questions that started the area. Not here: any fact of its own; principles and theorems -> [foundations](foundations.md); symbols -> [vocabulary](vocabulary.md#glossary); ideas -> [catalog](../../ideas/physics-first/README.md); summary -> [digest](../../digests/physics-first.md).
Keys: physics-first layout, area map, philosophy, gentleness G, F1–F7, T1–T13, passports, physics core, critics, validation, solvers, joint place and route

Tags: [P] primary, [S] secondary, [V] vendor, [I] inference, [C] computed by scripts in [`tools/research/physics/`](../../../tools/research/physics/) (listed in [tools/research/README](../../../tools/research/README.md)), quasi-static and uncalibrated unless stated.

Thesis in one line: a circuit is Maxwell at zeroth order; layout adds corrections that converge only inside the gentleness radius G < 1; keep every omitted effect invisible, known (budgeted with σ) or designed ([foundations](foundations.md)).

## Map

### Core principles and vocabulary

| Doc | What it holds | Keys |
|---|---|---|
| [foundations](foundations.md) | circuit as zeroth-order Maxwell, gentleness G, principles F1–F7 + D, theorems T1–T13, what a conductor is doing | G, F1–F7, T1–T13, invisible/known/designed |
| [foundations-derivations](foundations-derivations.md) | derivations D1–D9 of G and T1–T11; 26 rules traced to theorems | Neumann series, Bode-Fano, Woodbury, wedge singularity |
| [vocabulary](vocabulary.md) | glossary of every symbol; 12 atoms, value types, relations, bands and regimes | glossary, Port, Loop, Node, Budget, f_x, ℓ_m |
| [physics-graph](physics-graph.md) | operators, the physics graph, visual glyphs | operators, physics graph, glyphs |

### Rules decompressed and tested

| Doc | What it holds | Keys |
|---|---|---|
| [rule-basis-set](rule-basis-set.md) | 12 quantities behind 160 rules; proxy words; regime selectors; conflicts | basis set, L, M, Cm, R, Z, Vcm, Th |
| [rule-genealogy-power-analog-thermal](rule-genealogy-power-analog-thermal.md) | rules P01–P59: origin, physics, verdict, replacement budget | P01–P59, hot loop, Kelvin, creepage |
| [rule-genealogy-si-emi-rf](rule-genealogy-si-emi-rf.md) | rules S01–S55 | S01–S55, return path, 3W, MREMC |
| [rule-genealogy-routing-style-dfm](rule-genealogy-routing-style-dfm.md) | rules R01–R46 | R01–R46, 90° corners, teardrops, thermal reliefs |
| [derivation-audit](derivation-audit.md) | method and verdicts: 132 of 160 rules derive (51 cleanly, 81 with a regime); 12 of 67 numbers derive | derivable, habit-wrong, principle D |
| [derivation-audit-table](derivation-audit-table.md) | one row per rule: principles, derivation, regime, number status | verdict, number status |

### First-principles lenses

| Doc | What it holds | Keys |
|---|---|---|
| [lens-vp](lens-vp.md) | variational principles, term classes, certified floors, via capacity, R–L crossover | Thomson, floors, class A/B/C, Beckmann |
| [lens-ct](lens-ct.md) | conservation and topology: world node, cut-flux law, necks | KCL/KVL, I_CM, articulation point |
| [lens-sy](lens-sy.md) | reciprocity, lead fields, duality, images, mode conversion | reciprocity, duality, imbalance χ |
| [lens-ls](lens-ls.md) | circuit-window edges, complex images, wire medium, regime map | θ, ℓ_m, f_p, decap reach |
| [lens-th](lens-th.md) | dissipation, modal Q ledger, noise, electro-thermal coupling, damage | Q = h/δ, tuned snubber, 4kT Re Z |
| [lens-in](lens-in.md) | decisions under belief: VOI, ranking vs compliance, epistemic ledger | VOI, EVPI, optimizer's curse |
| [lens-cd](lens-cd.md) | per-piece passports, Tellegen attribution, exact counterfactuals, leverage, jobs | passport, ρ, χ, Woodbury |

### Domain physics

| Doc | What it holds | Keys |
|---|---|---|
| [power-copper](power-copper.md) | node/branch classes, width trade, pours, corners, AC resistance | R_s, squares, w*, cut pricing |
| [pdn-and-commutation](pdn-and-commutation.md) | loop inductance, via clusters, decap mounting, plane spreading, Kelvin, gate loops | height × squares, via cluster, Kelvin |
| [fields-si-emi](fields-si-emi.md) | return paths, discontinuities, crosstalk, cavities, pairs | slot ΔL, return via, cavity, 3W |
| [fields-emi-budget](fields-emi-budget.md) | edge rate → dBµV/m chain; fix ranking; 1 mV and 5 µA rules | MREMC, CM current, CISPR 32 |
| [rf-geometry](rf-geometry.md) | when corners, pads, stubs, vias, weave matter; RF lines, keep-outs | \|Γ\| ≈ Z0·ΔC/(2t_r), teardrop, stub |
| [thermal-physics](thermal-physics.md) | board as 2-D fin, h coefficients, IPC-2221/2152 vs network, heatsinks | G_s, λ, K₀, 261 K/W via |
| [hv-and-manufacturing-physics](hv-and-manufacturing-physics.md) | clearance, creepage, CAF, Paschen, fab processes, solder joints | creepage, Paschen, etch undercut |
| [cross-domain-lessons](cross-domain-lessons.md) | transplants L1–L12 from coils, grids, plumbing, antennas, graphics | stream function ψ, Murray's law |
| [worked-thought-experiments](worked-thought-experiments.md) | four boards worked rule-first vs physics-first | buck, half-bridge, ADC, 2.4 GHz |

### The system

| Doc | What it holds | Keys |
|---|---|---|
| [design-reasoning-architecture](design-reasoning-architecture.md) | reasoning pipeline R1–R7, least-slack τ, boundary conditions, roles of LLM/solvers/human, locality index | τ = budget/floor, physics package, ECO menu |
| [schematic-to-physics](schematic-to-physics.md) | simulate the schematic: net passports, adjoint susceptibility, LII, √(k·s) budgets | `.noise`, LII, back-annotation |
| [comprehension](comprehension.md) | `kae.circuit` brief: roles, structures, confidences; measured accuracy on 112 boards | brief, caps_p, pairing, power_path |
| [physics-ir](physics-ir.md) | `pcb-intent/0.3` schema, validation, compile targets | intent.yaml, ledger.json, entity kinds |
| [physics-ir-examples](physics-ir-examples.md) | six circuits in the IR with their binding budgets | buck, USB3, crystal, ADC, 2.4 GHz, 48 V |
| [physics-core-v2](physics-core-v2.md) | core design: Piece/Passport/Belief, E0–E5, kernels K1–K8, edit spectrum r, classes A–L, build order | K1–K8, Woodbury radius, E0–E5 |
| [physics-core-v2-api](physics-core-v2-api.md) | types, kernel protocols, `PhysicsCore` facade, pcb-intent 0.4 | Belief, Quote, why_here, what_if |
| [real-board-passports](real-board-passports.md) | exact passports on BLDCM-Power: findings no netlist shows, ranked fixes | exposed pad, plane swap, 511 via sites |
| [suite-physics-results](suite-physics-results.md) | passports and critics on 112 qualified boards; Freerouting vs human | via bottleneck, COLAMD, plane order |

### Optimization

| Doc | What it holds | Keys |
|---|---|---|
| [joint-place-route](joint-place-route.md) | why staged P&R stalls, prior art, topology-carrying joint state, three timescales | homotopy, kinetic bands, PROXI, Starfish |
| [joint-place-route-experiment](joint-place-route-experiment.md) | PoC: joint SA vs sequential and equal-CPU portfolio; proxy study | refiner 10/10, portfolio tie 5/10 |
| [physics-in-the-loop-optimization](physics-in-the-loop-optimization.md) | physics terms with gradients, adjoints, routing as current flow, legalization | loop kernel, Gilbert tree, price field |
| [place-terms](place-terms.md) | `kae.physics.place_terms`: one currency u = v/a, closed forms, validation, speed | φ(u), detour 1 + c√ℓ, delta µs |
| [copper-shape-synthesis](copper-shape-synthesis.md) | topology optimization of pours: methods, DFM mapping, POC, zone export | SIMP, −14.5%, f_c |
| [exact-physics-options](exact-physics-options.md) | cost and decision flips of exact physics in placement; designs (a)–(h) | route floor, multi-fidelity top-K |
| [exact-physics-in-kae](exact-physics-in-kae.md) | shipped `--physics-fidelity fast\|exact\|multi` (PEEC, FV) | PEEC, kae.physics.exact |

### Engines

| Doc | What it holds | Keys |
|---|---|---|
| [open-solvers](open-solvers.md) | open engines per rung, licence verdicts, speed, KiCad bridges, surrogates | FastHenry licence, openEMS, Palace, PyPEEC |
| [solver-ladder](solver-ladder.md) | rungs F0–F4 + S, evaluator contract, trust radii, VOI escalation, caching | MS2, trust radius, escalation |

### Judgement and truth

| Doc | What it holds | Keys |
|---|---|---|
| [physics-critics](physics-critics.md) | what DRC cannot see, suite architecture, scorecard, mutation benchmark, prototype | scorecard, BPM, pc_refplane |
| [physics-critics-catalog](physics-critics-catalog.md) | 41 critic definitions | RET-COV, HOTLOOP-L, CM-V … |
| [physics-critics-validation](physics-critics-validation.md) | calibration, planted faults, gaming guards per critic | equivalent mutant, Ott slot fit |
| [functional-evaluation](functional-evaluation.md) | whether a board works: ideal vs routed testbenches (`kae.sim`) | capability, verdicts, rail_dc |
| [verification-and-limits](verification-and-limits.md) | claims checked by independent methods, scopes, steelman of rules, falsification | PEECN filaments, steelman |
| [validation-program](validation-program.md) | VOI-ranked measurement plan, VAL-1, floor census, kill criteria | VAL-1, EVPI, kill criteria |
| [validation-coupons](validation-coupons.md) | five coupons with registered predictions | LM, FP, SS, NL, CM |

### Synthesis

| Doc | What it holds | Keys |
|---|---|---|
| [cross-workstream-synthesis](cross-workstream-synthesis.md) | nine shared mathematical objects, convergences, synergies S1–S11, transfers | chained adjoints, ψ cut pricing |
| [research-gaps](research-gaps.md) | ranked open problems, limits of the thesis | gap 1 ground truth, gap 2 slotted planes |

## Answers to the questions that started this

| Question | Answer (canonical home) |
|---|---|
| Curves instead of right angles? | Only where damage, HV, fast pulses (shorter than ~w²/κ) or RF edges below ~30 ps make the corner field matter (T11, [foundations](foundations.md), [rf-geometry](rf-geometry.md)). For loss a sharp corner adds ~0.56 squares and changes peak temperature by under 0.5% [C] ([rule-genealogy-routing-style-dfm](rule-genealogy-routing-style-dfm.md)). Fabs make curves at no extra cost: allow them where a budget pays. |
| Pours instead of thin traces? | Yes for DC feeds and returns; shapes already sit near their floor (median 4% avoidable), the leverage is partitioning and pad connections ([validation-program](validation-program.md#4-computational-track-no-hardware-start-now)); switch-node copper is set by coupling to the outside (T1 vs T3). |
| How much R, L, C, and which to maximize? | Per piece from ΔV/ΔI vs Z0 (T1). Low-impedance pieces want wide copper over thin dielectric, high-impedance nodes little capacitance; useful parasitics: plane-pair C, go/return overlap, designed damping R (T10) ([foundations](foundations.md)). |
| Keep high current away from sensitive lines? | Loops: a close plane beats distance (coupling ∝ h_a·h_v); wide dv/dt copper: height barely helps, use distance or bury the victim (T9, [lens-sy](lens-sy.md)); precision analog: keep foreign current out of the measurement cycle (T5, T7). |
| A physics engine, SPICE, open RF tools? | Eight kernels in one core, SPICE adjoints for the circuit, full-wave (openEMS, Palace) only for finalists and calibration ([physics-core-v2](physics-core-v2.md), [open-solvers](open-solvers.md)). |
| Near-infinite compute? | Exact counterfactuals, certified floors, QD search, surrogates on solver labels ([solver-ladder](solver-ladder.md#7-spending-near-infinite-compute)); it does not fix a divergent series or unknown cables: those need a new representation or a measurement ([validation-program](validation-program.md)). |
| Place and route together? | Yes, on a topology-carrying state with physics as shared objective, as a refiner after diverse starts ([joint-place-route](joint-place-route.md), [experiment](joint-place-route-experiment.md)). |

## Next steps (owned elsewhere)

1. Measure first: LM coupon and both VAL-1 arms ([validation-program](validation-program.md#6-schedule), [validation-coupons](validation-coupons.md#9-ordering-and-use)).
2. Build K1, K2, K4 on one real 4-layer board with the mutation benchmark (PC29) ([physics-core-v2](physics-core-v2.md#9-build-order-and-acceptance-tests)).
3. Turn [derivation-audit-table](derivation-audit-table.md) rows into rule-pack records with board-computed regime predicates.
4. Floor and G census on the qualified bench suite, as a separate report that never touches cp1/cpk.

Open problems: no principle or number has met a measurement (11 kill criteria in [validation-program](validation-program.md#5-kill-criteria)); no joint self + interaction pricing with guarantees; nonlinear victims, ESD and surge lie outside F2; off-board unknowns hold 10–84% of decision value depending on priors ([verification-and-limits](verification-and-limits.md)); good rules beat model optima when decisive unknowns are off the board (steelman in [verification-and-limits](verification-and-limits.md#3-where-competent-rule-following-beats-physics-first)). Full list: [research-gaps](research-gaps.md).

## Sources

Primary sources are cited per topic doc. Research notes behind the rules: [rules_highspeed_emi.md](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/rules_highspeed_emi.md), [rules_power_rf_analog_dfm.md](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/rules_power_rf_analog_dfm.md), [verification_rules.md](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_rules.md). See also: [executive report](../../../reports/Physics-first%20PCB%20layout.md).
