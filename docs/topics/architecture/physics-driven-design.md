<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Physics-driven design: the formal problem, feasibility and the build

Scope: the formal placement/routing problem with circuit-derived prices, its reduction to J ≈ ⟨W, Z(D)⟩, the three solver tiers, feasibility, milestones M1–M6 with gates G1–G5. Not here: what is built and measured -> [physics-driven-build](physics-driven-build.md); frequency coverage -> [physics-frequency-coverage](physics-frequency-coverage.md); engine internals -> [physics-engine-design](physics-engine-design.md).
Keys: price matrix W, Z(D), ⟨W, Z⟩, J(D), φ margin price, R1–R5 tractability properties, gentleness test, T1 T2 T3 tiers, price fields Π, plane-integrity map, sequential linearization, SPICE re-pricing, sign-off, M1–M6, G1–G5, PEEC, block-Toeplitz FFT

Tags: [C] computed (model against model); [I] inference. Theory: [foundations](../physics/foundations.md), [lens-ls](../physics/lens-ls.md), [lens-vp](../physics/lens-vp.md), [schematic-to-physics](../physics/schematic-to-physics.md), [solver-ladder](../physics/solver-ladder.md).

**Verdict: feasible** [I]: every component is established physics with a known method at a cost fitting its tier (§7). Open risks: router integration, excitations for unmodelled parts, no measured ground truth.

## 1. The problem, formally

Givens: netlist N (parts with behavioural models: vendor, stand-in or envelope); operating envelope E (inputs, loads, corners); fixed mechanics (outline, connectors, holes); stackup S (layers, dielectric heights h, copper weights).

- Design D = (x, r): part poses x, copper r (tracks, vias, pours, plane shapes).
- Physics: copper + laminate = linear, passive, reciprocal multiport P(D); ports = part pins + world nodes (chassis, cables). Built board N ⊕ P(D); behaviour y(D) = circuit solved with P attached ([foundations](../physics/foundations.md) F1–F2).
- Requirements r_k(y) ≤ b_k, each with a source (datasheet, standard, human, prior): regulation, efficiency, overshoot vs V_DS(max), gate false turn-on, ADC input noise, timing, CISPR 32 emissions, part temperature.
- Hard constraints: completion, DRC, creepage/clearance (IEC 60664/62368), impedance where specified.

  min over legal, complete D of  J(D) = Σ_k φ(r_k(y(D)) / b_k)

- φ: the placer's margin price ([place-terms](../physics/place-terms.md)), linear below 1, barrier above.
- Unstated requirements: flagged defaults from standards (logic noise margins, CISPR 32 class B, part ratings).
- Exact evaluation (full-wave + nonlinear transient per corner) costs hours per candidate vs µs needed; §2–§5 reduce it.

## 2. Five properties that make it tractable

| # | Property | Consequence | Fails where | Detect by |
|---|---|---|---|---|
| R1 | **Linear interconnect**: copper, laminate, air superpose; nonlinearity only in parts | P(D) computed without the circuit, circuit without P | ferrite saturation, self-heating, breakdown | part classes; one electro-thermal fixed point |
| R2 | **Electrically small**: θ = ωℓ/v ≪ 1 for most energy | quasi-static partial elements R, L_p, P exact to O(θ²); long nets -> TEM lines (2-D cross-section + 1-D propagation) | intentional radiators; fast edges on long structures | θ per net from length and edge rate |
| R3 | **Perturbation**: y ≈ y₀ + Σ s_i·p_i | margins linear in parasitics; s from one adjoint solve per requirement and band ([schematic-to-physics](../physics/schematic-to-physics.md)) | resonance (\|δL/L\| > 1/Q), a parasitic that sets operation, thresholds | gentleness test G < 1 per structure ([foundations](../physics/foundations.md) §1) |
| R4 | **Locality**: over a plane mutual L, C fall as (h/d)²; heat as e^(−r/λ) | a copper decision touches ~10h (2–15 mm); local cost updates | no plane; slots, splits; cavity modes | plane-integrity map; θ vs cavity size |
| R5 | **Variational**: loss, loop L, thermal resistance are energy minima | cheap models are bounds of known sign (coarse PEEC reads HF L high); certifiable floors; self terms monotone in added copper | interaction terms, either sign ([lens-vp](../physics/lens-vp.md) class B) | term class per band |

**Factorization.** Under R1–R3, Z_b(D) = interconnect quantities read in band b: self R + jωL of each excited loop; mutual jωM between loops; mutual C_m between nodes; thermal resistances source -> part.

  r_k(D) ≈ r_k⁰ + Σ_b Re ⟨S_k,b, Z_b(D)⟩

Energy-type requirements (loss, emitted power) are quadratic in currents, still linear in Z. **Price matrix** (gradient of J in Z):

  W = Σ_k φ′(r_k/b_k)·S_k / b_k

W = excitation × sensitivity per unit margin; sparse (rows zero except the few loops with large di/dt and nodes with large dV/dt).

**Sequential linearization** J(D) ≈ J(D₀) + ⟨W, Z(D) − Z(D₀)⟩: fast loop (T1 in the router) lowers ⟨W, Z⟩ at fixed W; slow loop (SPICE beside it) re-solves the circuit with extracted parasitics -> new margins, prices, gentleness check. "SPICE concurrent with routing" = periodic re-pricing, not a simulation per decision.

## 3. Why W and Z do different damage

Layouts A, B of one structure differ in J by W_ii·(Z_ii(A) − Z_ii(B)) + local cross terms, W_ii > 0: **ranking within a structure depends only on copper physics**; W only sets exchange rates between structures (e.g. hot-loop L vs a quieter ADC input).

- Z errors reverse decisions: validate Z at every tier.
- W needs right order of magnitude and membership: 2× off misallocates margin but still improves both structures. Dangerous W error = classification (switch node called quiet, missed high-Z input). Simulate membership (branches whose current steps at each edge; name-based roles only as cross-check); price a stand-in at the upper end of its interval; report every structure and its W.
- Budget sweep threshold moved 7× with the stand-in's recovery data ([functional-evaluator-budgets](functional-evaluator-budgets.md)); a price moving that much cannot reverse a ranking. Judge thresholds only at sign-off (§5).

## 4. The copper quantities and their operators

| Family | Quantity in Z | Operator | Regime |
|---|---|---|---|
| Efficiency, IR drop, current density | R per band | sheet Laplace ∇·(σt∇φ) per layer + vias | resistive spreading below f_x ≈ R_s/(2πμ₀h) (~300 kHz, 1 oz over 0.2 mm); inductive above ([lens-vp](../physics/lens-vp.md)) |
| Ringing, overshoot, switching loss, gate integrity | loop L (hot, gate, Kelvin, decap) | partial inductance L_p with plane images; meshed planes at slots | inductive limit for edges; images hold > a few h from plane edges |
| Magnetic crosstalk, ground bounce, common mode | M; shared-path L between loops and world ports | L_p off-diagonal | CM voltage between cable ports = shared-path L × di/dt ([lens-ct](../physics/lens-ct.md) T6) |
| Capacitive crosstalk, high-Z victims | C_m; node C to world | potential operator P (layered electrostatics) | voltage-forced: height barely helps; distance and shielding do |
| PDN | Z_load(f) | L_p, R with capacitor models; plane cavity | near anti-resonance (class C): evaluate \|Z(f)\| on a grid, don't linearize |
| SI on long nets | Z₀, delay, NEXT/FEXT | 2-D cross-section L′, C′ | only where θ is not small; a constraint, not a price |
| Thermal | R_θ source -> part | layered fin ∇·(kt∇T) = h_c·T | one electro-thermal fixed point (0.39 %/K) |
| Safety | distance, field | geometry, standards tables | hard constraint, never priced |
| Radiators, RF matching | not priced | full-wave on slices (F3) | keep-outs, datasheet rules, flagged |

- Four operators suffice: sheet (R, thermal), partial inductance, potential, 2-D line cross-section.
- Return path is in Z (a loop's L_p sum includes its return), so a plane slot is a Z change like any other. Today's critical router prices loops over the nearest zone's outline, blind to slots inside it; that slot is its whole boost-loop error, 1.7 nH of 13 ([functional-evaluator-budgets](functional-evaluator-budgets.md)).

## 5. Three tiers of the same quantities

| Tier | Runs | Computes | Cost | Trusted because |
|---|---|---|---|---|
| **T1 fields** | inside placer and router | closed forms with images; price fields Π; plane-integrity map; L′(w, h), R′; thermal kernels | ~10–100 ns per edge lookup; ~30 µs per committed segment [I] | ranks like T2 (G2); per-structure T2 corrections |
| **T2 board solver** | beside the router, on snapshots | raster PEEC with planes, slots; sheet DC and thermal; potential solve for C_m; parasitic netlist | minutes per board, seconds per window | agrees with T3 on a reference suite (G1) |
| **T3 reference** | offline | FastHenry, FasterCap (independent codes); openEMS where θ not small; analytic cases; published measurements | hours | independent methods; measurement where it exists |

**T1 price fields.** A_j(x) = vector potential per unit current of loop j's existing copper, return included (images on intact planes). Candidate segment e of net n adds

  ΔJ(e) = Σ_{loops i ∋ n} [ W_ii·L_p(e,e) + 2·∫_e Σ_j W_ij·A_j · dl ]

- One field per loop, Π_i = Σ_j W_ij·A_j; line integrals add along a path, so A* and negotiated congestion use them unchanged.
- Capacitive fields: same from potentials of dV/dt nodes; resistive price R′·I² per length.
- Negative mutuals are physical (return beside forward path); floor each edge cost at its self term.
- Coarse grid, cutoff ~10h, local update per committed segment.
- Plane cut: integrity map adds the forced return's detour L, ℓ/ln(4ℓ/g) for a slot ([verification-and-limits](../physics/verification-and-limits.md) §2), replaced by T2's value at the next snapshot.

**T2 feasibility** [C]:
Uniform raster per layer -> L_p block-Toeplitz -> mat-vec by FFT: 0.16 s per product per direction, one core, at 100 × 100 mm, 4 layers, 0.25 mm (640k cells per direction); GMRES 50–200 iterations with sparse preconditioner ≈ 0.5–2 min per board, seconds per window. Sheet operators by sparse Cholesky: 0.03–0.9 s at 76k–810k nodes ([physics-engine-design](physics-engine-design.md)). T2 = [pt_mesh_loop](../../../tools/research/physics/pt_mesh_loop.py) (raster, via barrels, pitch rule, ports) + FFT products + potential operator + multiport output.

**Calibration loop.** T2 per snapshot -> per-structure T2/T1 ratios (multiplicative T1 corrections); hot spots (return crowding, coupling above price) -> rip-up; parasitic netlist -> SPICE re-pricing. Ratio moving > 30% between snapshots = outside T1 validity: price by T2 + local first-order update until the next snapshot.

**Never evaluate with T1**: scores and sign-off use T2 + SPICE, T3 on samples; an optimizer graded by its own model drifts into its errors ([verification-and-limits](../physics/verification-and-limits.md) §3).

**Sign-off**: finished board's T2 netlist in SPICE at every corner; each requirement reported with its source class, or "unknown" (gentleness test fails, model missing); thresholds (e.g. overshoot vs V_DS(max)) judged only here.

## 6. Placement and routing

| Stage | Today | Gap against this design |
|---|---|---|
| Brief (`kae.circuit`) | structures from names, values, footprints; excitations = E5 table priors (`physics/priors.py`); no per-net current, di/dt, sensitivity | W from simulation (M3) |
| Placer | simulated annealing on `place_terms` (loop, decap, coupling, crystal, thermal, ESD, common-mode; closed forms) | allocations -> prices |
| Critical router | A* on length × cell multipliers; physics = discrete choice among quoted candidates (widths, layers, via sites, poses), each quoted by a closed-form `Loop` over zone outlines | price fields in search; slots; coupling |
| Bulk routing (Freerouting) | no physics beyond 4× plane-layer cost and locked critical copper | cost-map hook |
| Score | `physics_total`: routed u per module, capped at 5, missing module = 3; kaebench scores no physics | T2 + SPICE (M6) |

**Placement** (decides most of every loop and separation): keep terms and delta evaluation (22–40 µs per move); W replaces priors; loop L = body floor (`cell_body_floor`, [critical_recheck](../../../kae/src/kae/route/critical_recheck.py)) + predicted path. Smooth closed-form kernels keep a gradient placer possible.

**Routing** (largest build item):
1. Route nets with non-zero W rows first, by ΣW, on price fields (the critical stage generalized from a fixed structure list).
2. Route other nets with aggressor fields as soft cost layers and the integrity map as crossing cost (cost-map hook in the bulk router).
3. Completion first: physics is a bounded cost, never a block.

**Copper synthesis** (pours, splits, stitching): sheet-operator adjoint for class-A gradients; convex floors certify remaining gain ([copper-shape-synthesis](../physics/copper-shape-synthesis.md)).

## 7. Feasibility

| Component | Method and status | Cost for its role | Risk |
|---|---|---|---|
| W: excitations, sensitivities | adjoint sensitivity (Director–Rohrer 1969); SPICE `.noise` as adjoint, reproduced to 6×10⁻¹³ | minutes per subcircuit per corner, beside layout | **High**: parts without models; mitigated by intervals, simulated membership, reporting |
| T1 closed forms | Grover and Ruehli partials with images; median error 5% vs PEEC on 324 routed loops | µs | Medium: slots, plane edges (integrity map, T2) |
| Price fields in the router | line integral of A = mutual-inductance contribution (standard) | ns per lookup | **Medium–high**: engineering inside the bulk router |
| T2 solver | PEEC (Ruehli 1974); FastHenry's mesh formulation; FFT products | minutes per board [C] | Low–medium: preconditioning; ports at pads |
| T3 references | FastHenry, FasterCap, openEMS (FastHenry for internal calibration only, by its licence) | hours | Low |
| Sign-off | SPICE with back-annotated RLCK | minutes per corner | Medium: same model gaps as W, shown as unknowns |
| Ground truth | none measured ([validation-program](../physics/validation-program.md)) | — | **High** for absolute claims, low for rankings |

**Physics vs good rules.** At fixed stackup "minimize length × h/w" picks the best hot loop 82–99% of the time ([verification-and-limits](../physics/verification-and-limits.md) §3), so no single-loop win. Claimed wins [I]: generality (loops, victims derived where no rule table exists); numeric trade-offs between structures; cross terms rules miss; zero W rows free copper for routability. Falsifiable by G5; not yet shown.

Out of scope: absolute emissions (rankings only); antennas, RF (rules + F3); ESD/immunity beyond path inductance; mechanics.

## 8. The build, with gates registered in advance

Criteria fixed before results; a failed gate stops dependent milestones.

| M | Build | Gate |
|---|---|---|
| M1 | **T2 solver**: pt_mesh_loop -> multiport extractor (FFT products; L, R, C_m per port pair; planes, slots). Reference suite: analytic cases, FastHenry/FasterCap geometries, 30 corpus windows | **G1**: ≥ 90% of suite cases within 10% of T3 for L and R, 15% for C_m; refinement study on each |
| M2 | **T1 fields**: strip, loop, mutual forms; integrity map; price-field grid with local updates | **G2**: on 200 perturbed pairs from real boards, T1 orders like T2 on ≥ 95% of pairs differing by > 20%; after T2 correction within 20% on 90% |
| M3 | **W from the circuit**: subcircuit partition; simulated di/dt, dV/dt per branch/node; adjoint sensitivities per requirement and band; stand-in intervals; gentleness test | **G3**: on 20 boards across classes every hand-identified hot loop and high-Z victim found, none silently missing |
| M4 | **Router integration**: priced nets on price fields; cost-map hook for bulk; concurrent T2 calibration and SPICE re-pricing | **G4**: completion and DRC no worse than the current portfolio on the qualified suite |
| M5 | **Placement on W**: place terms take W instead of priors | inside G5 |
| M6 | **Sign-off and comparison**: T2 + SPICE on finished boards; physics-driven vs Freerouting vs human on a stratified 60-board sample | **G5**: by the evaluator (T2 + SPICE, never T1), J better than Freerouting on ≥ 80% of boards, no worse than human on ≥ 50%; human boards must beat their own shuffles |

Order: M1 ∥ M3; M2 after M1; M4 after M2 and M3. M1–M3 ≈ 2–3 weeks of work + a day of queued compute [I].

## 9. What this keeps and stops

Keep: kernels, place terms, PEEC, pt_mesh_loop, testbench machinery (-> W extractor and sign-off), body floors, φ. Stop: SPICE budget sweep as router input (diagnostic only); new theory docs until M1–M4 pass (~50 physics docs and 96 research scripts exist, none imported by kae: the gap is building, not theory).
