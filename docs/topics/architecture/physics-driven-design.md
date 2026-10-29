<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Physics-driven design: the formal problem, feasibility and the build

**TL;DR**
- **Problem.** Choose placement and copper so the built circuit (the schematic plus a linear multiport of copper P(D)) meets its function with the most margin. Completion and DRC stay hard constraints.
- **Five properties make it tractable:**
  - the interconnect is linear;
  - the board is electrically small;
  - copper is a detectable small perturbation of the circuit;
  - interactions over a plane are local;
  - self terms are energy minima.
- **So, to first order, J = ⟨W, Z(D)⟩.**
  - W is the circuit's price per nH, pF or mΩ (excitation × sensitivity), computed by SPICE beside the routing.
  - Z(D) is the copper, read by the router as line integrals of price fields.
- **What errors in each can do:**
  - a W error misallocates margin between structures, but cannot reverse the ranking of two layouts of one structure;
  - a Z error can reverse that ranking, so Z is validated hardest.
- **Verdict: feasible.** Every component is established physics with a known method, at a cost that fits its tier (§7). The open risks are router integration, excitations for unmodelled parts, and the lack of measured ground truth.
- **Build:** six milestones, each with an acceptance gate registered in advance (§8).

Tags: [C] computed (model against model); [I] inference. Theory: [foundations](../physics/foundations.md), [lens-ls](../physics/lens-ls.md), [lens-vp](../physics/lens-vp.md), [schematic-to-physics](../physics/schematic-to-physics.md), [solver-ladder](../physics/solver-ladder.md). Engine internals: [physics-engine-design](physics-engine-design.md).

## 1. The problem, formally

**Givens:**
- a netlist N, whose parts have behavioural models (vendor, stand-in or envelope);
- an operating envelope E (inputs, loads, corners);
- fixed mechanics (outline, connectors, holes);
- a stackup S (layers, dielectric heights h, copper weights).

**Design:** D = (x, r), with part poses x and copper r (tracks, vias, pours, plane shapes).

**Physics.** Copper and laminate form a linear, passive, reciprocal multiport P(D). Its ports are the part pins plus world nodes (chassis, cables). The built board is N ⊕ P(D), and its behaviour y(D) is the circuit solved with P attached ([foundations](../physics/foundations.md) F1–F2).

**Specification:**
- Requirements r_k(y) ≤ b_k, each with a source: datasheet, standard, human or prior. Examples: regulation, efficiency, overshoot against V_DS(max), gate false turn-on, ADC input noise, timing, CISPR 32 emissions, part temperature.
- Hard constraints: completion, DRC, creepage and clearance (IEC 60664/62368), impedance where specified.

**Problem:**

  min over legal, complete D of  J(D) = Σ_k φ(r_k(y(D)) / b_k)

- φ is the placer's existing margin price ([place-terms](../physics/place-terms.md)): linear below 1, a barrier above.
- Requirements nobody stated get defaults from standards (logic noise margins, CISPR 32 class B, part ratings), flagged as defaults.

Exact evaluation (full-wave fields coupled to a nonlinear transient at every corner) takes hours per candidate; the optimizer needs microseconds. The rest of this doc is the reduction that closes the gap.

## 2. Five properties that make it tractable

| # | Property | Consequence | Fails where | Detect by |
|---|---|---|---|---|
| R1 | **Linear interconnect.** Copper, laminate and air superpose; all nonlinearity is in the parts | P(D) is computed without the circuit, and the circuit without P | ferrite saturation, self-heating, breakdown | part classes; one electro-thermal fixed point |
| R2 | **Electrically small.** θ = ωℓ/v ≪ 1 for most of the energy | Quasi-static partial elements R, L_p, P are exact to O(θ²). Long nets become TEM lines (2-D cross-section plus 1-D propagation) | intentional radiators; fast edges on long structures | θ per net from length and edge rate |
| R3 | **Perturbation.** y ≈ y₀ + Σ s_i·p_i | Margins are linear in parasitics, with sensitivities s from one adjoint solve per requirement and band ([schematic-to-physics](../physics/schematic-to-physics.md)) | resonance (\|δL/L\| > 1/Q), a parasitic that sets operation, thresholds | gentleness test G < 1 per structure ([foundations](../physics/foundations.md) §1) |
| R4 | **Locality.** Over a plane, mutual L and C fall as (h/d)²; heat as e^(−r/λ) | A copper decision touches ~10h (2–15 mm), so cost updates are local | no plane; slots and splits; cavity modes | plane-integrity map; θ against cavity size |
| R5 | **Variational.** Loss, loop L and thermal resistance are energy minima | Cheap models are bounds with known sign (coarse PEEC reads HF L high); floors are certifiable; self terms are monotone in added copper | interaction terms, which can have either sign ([lens-vp](../physics/lens-vp.md) class B) | term class per band |

**The factorization.** Under R1–R3, let Z_b(D) be the interconnect quantities the requirements read in band b:
- the self impedance R + jωL of each excited current loop;
- the mutual jωM between loops;
- the mutual C_m between nodes;
- the thermal resistances between heat sources and parts.

Then

  r_k(D) ≈ r_k⁰ + Σ_b Re ⟨S_k,b, Z_b(D)⟩

Energy-type requirements (loss, emitted power) are quadratic in the currents but still linear in Z. The gradient of J with respect to Z is the **price matrix**

  W = Σ_k φ′(r_k/b_k)·S_k / b_k

- W is excitation × sensitivity per unit margin.
- W is sparse: few loops carry large di/dt and few nodes large dV/dt, and every other net's row is zero.

**Sequential linearization.** Locally, J(D) ≈ J(D₀) + ⟨W, Z(D) − Z(D₀)⟩.
- **Fast loop (tier 1, inside the router):** lower ⟨W, Z⟩ with W held fixed.
- **Slow loop (SPICE, beside the router):** re-solve the circuit with the parasitics extracted from the current copper. That gives new margins, new prices and a new gentleness check.

That is what "SPICE running concurrently with routing" means: periodic re-pricing, not a simulation per decision.

## 3. Why W and Z do different damage

Two layouts A and B of one structure differ in J by W_ii·(Z_ii(A) − Z_ii(B)), plus local cross terms. For a self term W_ii > 0. So **the ranking within a structure depends only on the copper physics.** W sets the exchange rate between structures, for example how much hot-loop inductance to give up for a quieter ADC input.

- **Z must rank correctly.** Its errors reverse decisions, so it is validated at every tier.
- **W must be the right order of magnitude, with the right membership.** A W that is 2× off misallocates margin but still improves both structures. The dangerous error is classification: a switch node called quiet, or a missed high-impedance input. Mitigations:
  - membership is simulated (the branches whose current steps at each edge), and name-based roles stay only as a cross-check;
  - a stand-in's interval is carried through, and its upper end sets the price;
  - every structure and its W are reported.
- **The lesson of the budget sweep:** its threshold moved 7× with the stand-in's recovery data ([functional-evaluator](functional-evaluator.md) §5a). A price moves by that much or less and cannot reverse a ranking. Thresholds belong to sign-off (§5).

## 4. The copper quantities and their operators

| Family | Quantity in Z | Operator | Regime |
|---|---|---|---|
| Efficiency, IR drop, current density | R per band | sheet Laplace ∇·(σt∇φ) per layer, plus vias | Resistive spreading below f_x ≈ R_s/(2πμ₀h), ~300 kHz on 1 oz over 0.2 mm; inductive above ([lens-vp](../physics/lens-vp.md)) |
| Ringing, overshoot, switching loss, gate integrity | Loop L (hot, gate, Kelvin, decap) | partial inductance L_p with plane images; meshed planes at slots | Inductive limit for edges; images hold a few h from plane edges |
| Magnetic crosstalk, ground bounce, common mode | M; shared-path L between loops and world ports | L_p, off-diagonal | Common-mode voltage between cable ports is shared-path L × di/dt ([lens-ct](../physics/lens-ct.md) T6) |
| Capacitive crosstalk, high-Z victims | C_m; node C to the world | potential operator P (layered electrostatics) | Voltage-forced: height barely helps, distance and shielding do |
| PDN | Z_load(f) | L_p and R with capacitor models; plane cavity | Near anti-resonance (class C): evaluate \|Z(f)\| on a grid, don't linearize |
| SI on long nets | Z₀, delay, NEXT/FEXT | 2-D cross-section L′, C′ | Only where θ is not small; a constraint, not a price |
| Thermal | R_θ source to part | layered fin ∇·(kt∇T) = h_c·T | One electro-thermal fixed point (0.39 %/K) |
| Safety | distance, field | geometry, standards tables | Hard constraint, never priced |
| Radiators, RF matching | not priced | full-wave on slices (F3) | Keep-outs and datasheet rules, flagged |

Two observations:
- **Four operators cover everything the optimizer needs:** the sheet operator (R, thermal), partial inductance, potential, and the 2-D line cross-section.
- **The return path is not an add-on.** A loop's L_p sum includes its return copper, so a plane slot is a change in Z like any other.
  - Today the critical router prices each loop over the nearest zone's outline, so a slot inside that zone is invisible while it searches.
  - That slot is the whole of the router's error on the boost loop: 1.7 nH of 13 ([functional-evaluator](functional-evaluator.md) §5a).

## 5. Three tiers of the same quantities

| Tier | Runs | Computes | Cost | Trusted because |
|---|---|---|---|---|
| **T1 fields** | inside placer and router | closed forms with images; price fields Π; plane-integrity map; L′(w, h), R′; thermal kernels | ~10–100 ns per edge lookup; ~30 µs per committed segment [I] | ranks like T2 (gate G2); per-structure T2 corrections |
| **T2 board solver** | beside the router, on snapshots | raster PEEC with planes and slots; sheet DC and thermal; potential solve for C_m; the parasitic netlist | minutes per board, seconds per window | agrees with T3 on a reference suite (G1) |
| **T3 reference** | offline | FastHenry and FasterCap (independent codes); openEMS where θ is not small; analytic cases; published measurements | hours | independent methods; measurement where it exists |

**T1 price fields.** For each excited loop j, precompute A_j(x): the vector potential per unit current of its existing copper, return included (images on intact planes). A candidate segment e of net n adds

  ΔJ(e) = Σ_{loops i ∋ n} [ W_ii·L_p(e,e) + 2·∫_e Σ_j W_ij·A_j · dl ]

- This is a line integral of one field per loop, Π_i = Σ_j W_ij·A_j. It is additive along a path, so A* and negotiated congestion use it unchanged.
- Capacitive price fields come the same way from the potentials of dV/dt nodes. Resistive prices are R′·I² per unit length.
- Negative mutual terms are physical: a return routed beside its forward path lowers L. The search floors each edge's cost at its self term.
- Fields decay over planes, so each one lives on a coarse grid with a cutoff of about 10h and is updated locally when a segment commits.
- At a plane cut, the plane-integrity map adds the detour inductance of the forced return, ℓ/ln(4ℓ/g) for a slot ([verification-and-limits](../physics/verification-and-limits.md) §2). T2's solved value replaces it at the next snapshot.

**T2 feasibility.**
- A raster mesh is uniform per layer, so the partial-inductance matrix is block-Toeplitz and its matrix–vector product is an FFT convolution.
- On a 100 × 100 mm, 4-layer board at 0.25 mm (640k cells per current direction), one product takes 0.16 s per direction on one core [C].
- GMRES at 50–200 iterations with a sparse preconditioner is then about 0.5–2 minutes per board, and seconds per window.
- The sheet operators are sparse Cholesky: 0.03–0.9 s at 76k–810k nodes ([physics-engine-design](physics-engine-design.md)).
- [pt_mesh_loop](../../../tools/research/physics/pt_mesh_loop.py) already has the raster, the via barrels, the pitch rule and the port handling. T2 is that tool plus FFT products, the potential operator and multiport output.

**Calibration loop.** T2 runs on each snapshot and returns three things:
- per-structure T2/T1 ratios, which become multiplicative corrections in T1;
- hot spots (return-current crowding, coupling above price), which go to rip-up;
- the parasitic netlist, which goes to the SPICE re-pricing.

A structure whose ratio moves by more than 30% between snapshots is outside T1's validity. Until the next snapshot it is priced by T2 plus a local first-order update.

**The evaluator is never T1.** Scores and sign-off use T2 plus SPICE, with T3 on samples. An optimizer graded by its own model drifts into that model's errors ([verification-and-limits](../physics/verification-and-limits.md) §3).

**Sign-off.**
- The finished board's T2 netlist runs in SPICE at every corner.
- Each requirement is reported with its source class, or as "unknown" where the gentleness test fails or a model is missing.
- Thresholds, such as overshoot against V_DS(max), are judged only here.

## 6. Placement and routing

**Where we are.**

| Stage | What it does today | Gap against this design |
|---|---|---|
| Brief (`kae.circuit`) | Structures from names, values and footprints. Excitations are E5 table priors (`physics/priors.py`). No per-net current, di/dt or sensitivity | W must come from simulation (M3) |
| Placer | Simulated annealing on `place_terms`: loop, decap, coupling, crystal, thermal, ESD and common-mode terms, as closed forms | Allocations must become prices |
| Critical router | A* on length × cell multipliers. Physics enters as discrete choices among quoted candidates (widths, layers, via sites, poses), each quoted by a closed-form `Loop` over zone outlines | Price fields inside the search; slots; coupling |
| Bulk routing (Freerouting) | No physics, apart from a 4× plane-layer cost and locked critical copper | A cost-map hook |
| Score | `physics_total`: routed u per module, capped at 5, with a missing module counted as 3. kaebench scores no physics | T2 plus SPICE (M6) |

**Placement** decides most of every loop and every separation. The placer keeps its existing terms, and its annealer keeps evaluating them as deltas (22–40 µs per move). Two things change:
- **Weights:** W replaces the priors.
- **Loop L:** it becomes the body floor (`cell_body_floor` in [critical_recheck](../../../kae/src/kae/route/critical_recheck.py)) plus the predicted path.

The kernels are smooth closed forms, so a gradient placer stays possible.

**Routing** is the largest build item:
1. **Priced nets route first, on price fields.** Every net with a non-zero W row is routed, in order of ΣW. This generalizes the critical stage from a fixed structure list to whatever the circuit says matters.
2. **Every other net** routes with the aggressor fields as soft cost layers and the plane-integrity map as a crossing cost. This needs a cost-map hook in the bulk router.
3. **Completion stays first.** Physics is a bounded cost, never a block.

**Copper synthesis** (pours, splits, stitching) uses the sheet operator's adjoint for class-A gradients, with convex floors to certify what is left to gain ([copper-shape-synthesis](../physics/copper-shape-synthesis.md)).

## 7. Feasibility

| Component | Method and status | Cost for its role | Risk |
|---|---|---|---|
| W: excitations and sensitivities | adjoint sensitivity (Director–Rohrer 1969); SPICE `.noise` as the adjoint, reproduced to 6×10⁻¹³ | minutes per subcircuit per corner, beside layout | **High**: parts without models. Mitigated by intervals, simulated membership and reporting |
| T1 closed forms | Grover and Ruehli partials with images; median error 5% against PEEC on 324 routed loops | µs | Medium: slots and plane edges, covered by the integrity map and T2 |
| Price fields in the router | the line integral of A is the mutual-inductance contribution (standard) | ns per lookup | **Medium–high**: engineering inside the bulk router |
| T2 solver | PEEC (Ruehli 1974); FastHenry's mesh formulation; FFT products | minutes per board [C] | Low–medium: preconditioning; ports at pads |
| T3 references | FastHenry, FasterCap, openEMS (FastHenry for internal calibration only, by its licence) | hours | Low |
| Sign-off | SPICE with back-annotated RLCK | minutes per corner | Medium: the same model gaps as W, shown as unknowns |
| Ground truth | none measured ([validation-program](../physics/validation-program.md)) | — | **High** for absolute claims, low for rankings |

**What physics adds over good rules.** At a fixed stackup, "minimize length × h/w" picks the best hot loop 82–99% of the time ([verification-and-limits](../physics/verification-and-limits.md) §3), so physics does not win on any one loop. It wins in four places:
1. **Generality:** a circuit no rule table covers still gets its loops and victims derived.
2. **Trade-offs with numbers:** it knows which of two competing structures gets the margin.
3. **Interactions:** rules handle self terms and miss cross terms.
4. **Knowing what doesn't matter:** a zero W row frees copper for routability.

The thesis is falsifiable by gate G5 and is not yet shown.

**Out of scope:**
- absolute emissions (rankings only);
- antennas and RF (rules plus F3);
- ESD and immunity beyond path inductance;
- mechanics.

## 8. The build, with gates registered in advance

Criteria are fixed before results are seen, and a failed gate stops the milestones that depend on it.

| M | Build | Gate |
|---|---|---|
| M1 | **T2 solver:** pt_mesh_loop grown into the multiport extractor (FFT products; L, R, C_m per port pair; planes and slots). Reference suite: analytic cases, FastHenry and FasterCap geometries, 30 corpus windows | **G1:** ≥ 90% of suite cases within 10% of T3 for L and R, and within 15% for C_m; a refinement study on each |
| M2 | **T1 fields:** strip, loop and mutual forms; plane-integrity map; price-field grid with local updates | **G2:** on 200 perturbed pairs from real boards, T1 orders like T2 on ≥ 95% of pairs differing by > 20%. After T2 correction, within 20% on 90% |
| M3 | **W from the circuit:** subcircuit partition; simulated di/dt and dV/dt per branch and node; adjoint sensitivities per requirement and band; stand-in intervals; gentleness test | **G3:** on 20 boards across classes, every hand-identified hot loop and high-Z victim is found, and none is silently missing |
| M4 | **Router integration:** priced nets on price fields; cost-map hook for the bulk; T2 calibration and SPICE re-pricing concurrently | **G4:** completion and DRC no worse than the current portfolio on the qualified suite |
| M5 | **Placement on W:** the existing place terms take W in place of priors | inside G5 |
| M6 | **Sign-off and comparison:** T2 plus SPICE on finished boards; physics-driven vs Freerouting vs human on a stratified 60-board sample | **G5:** by the evaluator (T2 plus SPICE, never T1), J better than Freerouting on ≥ 80% of boards and no worse than human on ≥ 50%. Human boards must beat their own shuffles |

M1 and M3 run in parallel, M2 needs M1, and M4 needs M2 and M3. M1–M3 are roughly 2–3 weeks of work and a day of queued compute [I].

## 9. What this keeps and stops

- **Keeps:**
  - kernels and place terms;
  - PEEC and pt_mesh_loop;
  - the testbench machinery, which becomes the W extractor and the sign-off;
  - body floors;
  - φ.
- **Stops:**
  - the SPICE budget sweep as a router input (it stays as a diagnostic);
  - new theory docs until M1–M4 pass. About fifty physics docs and 96 research scripts already exist, and none of the scripts is imported by kae: the gap is building, not theory.
