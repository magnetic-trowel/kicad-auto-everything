# Research gaps, convergent findings and limits of the physics-first thesis

**TL;DR**
- **Ten results were found independently by two to five workstreams.** That is the strongest signal this pass produced. Two stand out: one regime boundary, f_x = R_s/(2π·μ0·h), and one equation, the screened Laplace equation, keep reappearing. The value of a decision is also front-loaded: stackup, topology and part choice beat geometry tweaks, in one EMI case 24 dB (removing a slot) against 3 dB (slower edges). And every coordination signal we invented (congestion history, adjoint sensitivity, budget share, constraint price tag) is a Lagrange multiplier of one problem.
- **The largest gap is ground truth.** Every [C] number is model against model. The workstreams already disagree in places: bridging cap 1.2–3 nH vs Ott's 5–10 nH, slot inductance vs Ott's data, heatsink 22 vs 26 pF. No open dataset ties a layout to measured physics.
- **The R–L transition was first flagged as the hardest regime; rounds 2–3 re-scoped it.** It is a length band, not a frequency: half the return lies within ℓ_m/2 = R_s/(2π·μ0·f) of the trace. Converter fundamentals above ~300 kHz return within a few mm on 1 oz, and intact planes now have closed forms (complex images, [lens-ls](lens-ls.md)). What stays open is slotted, perforated and finite planes, and DC to tens of kHz near precision analog.
- **Whole physics areas are thin.** Immunity and ESD, nonlinear transients, the system around the board (enclosure, cables, heatsink, mounting), environment and mission profile, lifetime reliability, and platform noise into radios all need more work.
- **The thesis has limits.** Sometimes the board should *be* a component, not be invisible. The schematic is not fixed. "Near-optimal" is provable only for self terms (certified floors, [lens-vp](lens-vp.md)). A second research wave is proposed at the end; §0 says what rounds 2–3 already closed.

Tags: [P] primary, [S] secondary, [I] inference, [C] computed (scripts named). This doc synthesizes the "Conflicts and open questions" sections of all physics-first docs; it adds two calculations (f_x table, altitude cooling) and no new literature search.

## Key facts

### 0. Status after rounds 2 and 3

| Gap | Status | Where |
|---|---|---|
| 1 Ground truth | Still open. Replaced "one coupon per quantity" with a VOI-ranked program and a pre-registered first board | [validation-program](validation-program.md), [lens-in](lens-in.md) |
| 2 R–L transition | Re-scoped; closed forms for intact planes | [lens-ls](lens-ls.md), [lens-vp](lens-vp.md) |
| 3 Floors | Certified for self terms; open for couplings | [lens-vp](lens-vp.md) |
| 5 Infrastructure | Core designed (8 kernels, API, skeleton) | [physics-core-v2](physics-core-v2.md) |
| 6 Immunity | World node and designed damping added; nonlinear victims still open | [lens-ct](lens-ct.md), [lens-th](lens-th.md) |
| 20 Consistency | 76 corrections from an independent re-derivation | [red-team](red-team.md) |


### 1. Convergent findings inside this work

When separate workstreams, given different briefs, derive the same result, the result is probably fundamental and the system should be built around it.

| Finding | Found independently by | What it implies | Still open |
|---|---|---|---|
| **One regime boundary, f_x = R_s/(2π·μ0·h).** Below f_x, current follows resistance; above it, inductance. | Where return current flows ([vocabulary](vocabulary.md)); DC- vs HF-optimal pours ([copper-shape-synthesis](copper-shape-synthesis.md)); paralleled layers stop sharing AC ([cross-domain-lessons](cross-domain-lessons.md)); a plane mirrors loops above 12–125 kHz ([pdn-and-commutation](pdn-and-commutation.md)) | Make f_x a first-class band edge per stackup. Star-ground and split-ground debates are the two sides of this line. | The transition band itself (gap 2) |
| **One equation, the screened Laplace equation on sheets, with a length scale.** | IR drop and pour L (OP1); heat fin length ([thermal-physics](thermal-physics.md)); decap reach and via transfer length ([cross-domain-lessons](cross-domain-lessons.md)); plane spreading L ([pdn-and-commutation](pdn-and-commutation.md)) | One solver core. "Close" means "within λ". | Coupled electro-thermal solves; anisotropic and multi-layer coupling |
| **Loop area is the wrong proxy near a plane.** | Quadrupole loops ([vocabulary](vocabulary.md)); MS2 vs area ([solver-ladder](solver-ladder.md)); height × squares ([pdn-and-commutation](pdn-and-commutation.md)); perimeter ([physics-in-the-loop-optimization](physics-in-the-loop-optimization.md)) | Retire area tiers wherever there is a plane | The right proxy for 2-layer boards, slotted planes and frequencies below f_x |
| **Three PEEC solvers were written separately.** | `sl_`, `pw_`, `fe_` scripts | PEEC is the natural engine, and no open board-level PEEC exists | One maintained core (SIM46); a KiCad → physics-graph exporter |
| **Decisions made early matter most.** | One EMI case: removing a slot 24 dB, a split 38 dB, slower edges 3 dB; co-located cables 6–48 dB by orientation (the often-quoted 40 dB was an assumed input) ([fields-emi-budget](fields-emi-budget.md), [red-team](red-team.md)). Stackup and edge rates beat geometry ([worked-thought-experiments](worked-thought-experiments.md)). Copper area beats copper shape ([copper-shape-synthesis](copper-shape-synthesis.md)). Late co-optimization gains ~2% ([joint-place-route](joint-place-route.md)). Only length lowers L, C and R together ([power-copper](power-copper.md)) | The most leverage is in decisions made before routing | Gap 5 |
| **Everything is a price.** | PathFinder history costs; adjoint shadow prices (OP38); √(k·s) budget shares (DR9); constraint price tags (JPR34, I4); congestion prices as placement forces | One dual vector over budgets, routing resources and constraints. The LLM negotiates by reading duals | Duals of a non-convex problem hold only locally; explanations need a "valid within" margin |
| **Ranking matters more than accuracy.** | Proxies judged by decision quality (SIM7); the EMI chain is ±10–20 dB in absolute terms but ranks fixes correctly; RUDY ranks at chance and HPWL fails on near-ties ([joint-place-route](joint-place-route.md)) | Calibrate estimators on pairwise decisions that actually occur in optimization | No such dataset exists |
| **Return accounting is the central bookkeeping.** | Half-ports (LA1); return-path EMF (FE1); connectivity-qualified reference (PC9); current-free sense paths (XD72); ADC plane gradients ([worked-thought-experiments](worked-thought-experiments.md)) | One rule: no foreign current between the two points of any voltage that matters | Inferring return intent automatically (which pin returns which signal) |
| **Rules are regime-gated.** | 14 dimensionless groups ([rule-basis-set](rule-basis-set.md)); the Regime value type; geometry thresholds ([rf-geometry](rf-geometry.md)); the Paschen switch ([hv-and-manufacturing-physics](hv-and-manufacturing-physics.md)) | Every rule record carries a regime predicate | Discovering regimes automatically (Buckingham π plus simulation sweeps) |
| **Human practice is a good prior and a poor judge.** | 80 of 91 physics rules are right in regime (RG); expert trees sit on the 1-D optimum ([copper-shape-synthesis](copper-shape-synthesis.md)); rules as warm starts (RG41, JPR7) | Seed from rules; judge by physics | Measuring how much a physics-first system beats a good human (needs gap 1) |

### 2. Convergent evolution outside PCB design, and what divergence means

Independent fields converged on the same structures, so physics, not convention, forces them:

| Structure | Fields that converged on it | PCB form |
|---|---|---|
| **Overlapped go and return to confine the field** | Coax, twisted pair, laminated busbars, DBC power modules, bifilar windings, interdigitated IC power grids | Stripline, vertical hot loops, overlapped returns |
| **Periodic walls with a cut-off** | Waveguides below cut-off, Faraday cages, photonic crystals, EBG | Via fences, stitching lattices |
| **Keep foreign current out of the measurement path** | Kelvin four-wire, audio star grounds, single-point aerospace grounds, guard rings | Sense ports, exclusion zones |
| **Trees for steady flow, loops for fluctuating loads and damage tolerance** | Blood vessels, leaf veins, power grids | Traces for steady feeds, planes for decoupling |
| **Negotiated prices** | PathFinder, Wardrop traffic equilibrium, Lagrangian unit commitment, markets | Routing and placement prices |
| **Topology optimization with fab filters** | Structures, photonics, heat sinks, fluidics | Copper pours |

Two lessons follow [I]:
- **Encode convergent structures as strong priors and as move generators**, not as rules to check.
- **Divergence is the research map.** Where human practice diverges (vendor values 5–25× apart, the contested rules in [myths-and-contested](../rules/myths-and-contested.md)), the physics is regime-dependent, which is where computation beats rules first.

### 3. Gaps, ranked by value and neglect

**Tier 1: blocking or highest leverage**

1. **Ground truth (the F4 rung is empty).** No open dataset links layouts to measured R, L, coupling, emissions or temperature, and the CM-voltage and loop-radiation critics have no EMI ground truth ([physics-critics-validation](physics-critics-validation.md)). Round 3 replaced the first proposal (one coupon per basis quantity) with a value-of-information-ranked program: coupons only where rival predictions differ by 13× to 28 dB, led by the ℓ_m return-band coupon, plus a pre-registered two-arm first board (rules vs physics) measured in its enclosure with real cables ([validation-program](validation-program.md), [validation-coupons](validation-coupons.md)). Also mine vendor EVM reports with layouts and measurements.
2. **The R–L transition band (re-scoped in rounds 2–3).** f_x (table below) marks where the band crosses ℓ = h, not a regime boundary. At 100 kHz about 18% of the return still flows beyond ±5 mm (h = 0.1 mm), but above ~300 kHz on 1 oz it returns within a few mm, and 4–6 complex images reproduce intact planes within 0.5–3.5% ([lens-ls](lens-ls.md), [red-team](red-team.md)) [C]. Still open: slotted, perforated and finite planes, and DC to tens of kHz near precision analog, where star grounds pay only below ~6 kHz at 10 mm on 1 oz ([derivation-audit](derivation-audit.md)).

   | Plane copper | f_x at h = 0.075 / 0.1 / 0.2 / 1.6 mm |
   |---|---|
   | 0.5 oz (17.5 µm) | 1.66 / 1.25 / 0.62 MHz / 78 kHz |
   | 1 oz (35 µm) | 830 / 622 / 311 / 39 kHz |
   | 2 oz (70 µm) | 415 / 311 / 156 / 19 kHz |

3. **Physical floors and lower bounds (partly closed in round 2).** Self terms (loss, loop L, thermal R) have certified floors from convex relaxation with dual certificates: round 1's synthesized pour sits within 1.6% of its floor on the 0.1 mm raster, and the floor moves 2–13% with the grid ([lens-vp](lens-vp.md), [red-team](red-team.md)). Still open: floors for couplings and EMI masks, a continuum (not raster) bound, and joint placement.
4. **Front-loaded levers as variables.** The architecture still treats stackup, outline, connector edge, part and package, pinout, switching frequency and edge rate as inputs. The evidence says these levers dominate. Needed:
   - a lever catalog with physics leverage and cost per lever;
   - **stackup synthesis** with a fab cost model;
   - frequency planning against radio bands;
   - deciding which of these to ask the user about, by value of information.
5. **Infrastructure the joint optimizer needs.** An open multi-layer topological router with kinetic maintenance (none exists), one PEEC/sheet core, a KiCad → physics-graph exporter, and zone-arc support checked in KiCad 10/11 ([joint-place-route](joint-place-route.md), [copper-shape-synthesis](copper-shape-synthesis.md)).

**Tier 2: physics the pass covered thinly**

6. **Immunity, ESD and transients.** The corpus is emission-centric. Reciprocity covers linear coupling but not nonlinear victims: resets, latch-up, TVS snapback, op-amp rectification ([schematic-to-physics](schematic-to-physics.md)). An ESD strike carries ~30 A/ns, so 1 nH of shared path is 30 V. ESD, EFT and surge paths should be *designed loops with budgets*, from the cable shield to the chassis or return, never through logic ground. Field-to-trace coupling models (Taylor/Agrawal) are needed for radiated immunity.
7. **Nonlinear, large-signal co-simulation.** The undamped LC-step model predicts near-100% overshoot almost regardless of L ([physics-ir-examples](physics-ir-examples.md)), and linear budgets fail for a slow 48 V bridge ([schematic-to-physics](schematic-to-physics.md)). Needed:
   - extraction → vector fitting or PRIMA with passivity enforcement → a SPICE subcircuit;
   - transients with vendor models;
   - transient adjoint sensitivities.
   
   Encrypted models need validated stand-ins.
8. **The system around the board.** The heatsink acts as a ~22 pF antenna feed ([worked-thought-experiments](worked-thought-experiments.md)). Cable common-mode impedance moves the EMI verdict by 13–21 dB ([fields-emi-budget](fields-emi-budget.md)). Mounting holes are both mechanical anchors and chassis bonds, and so become cavity shorts and CM paths. Needed: a minimal enclosure/cable/mounting description the system must ask for, and the optimum's sensitivity to it.
9. **Environment and mission profile.** Thermal and HV rules assume sea level, 25 °C and still air. With h_conv ∝ ρ^0.5 (laminar natural convection) plus radiation, total h falls from ~12 W/m²K at sea level to ~4–5 at 20 km. Temperature rise per watt on an area-limited board then roughly triples, and the spreading length grows ~1.7× [C, rough model; script inline in this pass, assumptions: h_conv = 7 W/m²K at sea level, ε = 0.9, ISA air]. Gaps sit near the Paschen minimum ([hv-and-manufacturing-physics](hv-and-manufacturing-physics.md)). Cold shifts MLCC capacitance and solder fatigue, and vacuum removes convection. The vocabulary's Regime type should carry pressure, temperature range, humidity and vibration, not only frequency.
10. **Lifetime reliability as layout physics.** Thermal-cycling fatigue (part position relative to edges, screws and large packages), via-barrel fatigue, CAF and electrochemical migration under bias and humidity, creep corrosion, MLCC flex. The basis quantity Mech has 3 rules ([rule-basis-set](rule-basis-set.md)). Needed: a lifetime budget from a mission profile (Coffin-Manson or Engelmaier class models), with placement as the lever.
11. **Platform noise into radios (desense).** The ground plane is part of the antenna. Desense budgets are placeholders ([physics-ir-examples](physics-ir-examples.md)). Needed: near-field coupling of digital and switching harmonics into the antenna port, per channel, as a placement objective.
12. **Precision and analog beyond distance.**
    - DC plane gradients and thermal EMF dominate a 24-bit front end ([worked-thought-experiments](worked-thought-experiments.md)).
    - Leakage, humidity, dielectric absorption, guard design and MLCC microphonics and piezo effects are unexamined.
    - Inductor stray-field libraries are assumed, not measured ([pdn-and-commutation](pdn-and-commutation.md)).

**Tier 3: method gaps**

13. **Robustness to variation.** Process (Dk, etch, registration), part tolerances, temperature, ageing, alternate parts and model σ. The ledger needs σ propagation, and the optimizer needs chance constraints or worst-case corners.
14. **Coupled physics and self-consistency.** Spectra depend on the layout (ringing sets GHz content), resistance depends on temperature (runaway near ΔT₀ ≈ 254 K), and warpage affects joints. Build a coupling-strength matrix, then iterate to a fixed point only where the coupling is strong.
15. **Human reviewability of physics-optimal geometry.** Organic pours, arcs and any-angle routes must survive review, CAM and later edits. The "locality index" is untested against reviewer acceptance or EMC outcomes ([design-reasoning-architecture](design-reasoning-architecture.md)). Needed: a user study, plus a regularity regularizer that trades a little physics for a lot of readability.
16. **LLM physics competence.** Model choice, mechanism hypotheses (LA39) and anticipating results (Bogatin rule #9) are unmeasured. Circuits that simulate can still be wrong: 10.7% / 4.7% in one study ([schematic-to-physics](schematic-to-physics.md)). Needed: a benchmark of "find the coupling mechanism" tasks drawn from the mutation benchmark and known respin causes.
17. **Physics-labelled data.** Synthetic boards with F2/F3 labels (a label factory), real boards with known failures (git repair histories, L5), and EVMs as gold (L4).
18. **Certification risk instead of worst case.** MREMC is a worst case. How far real plastic-enclosure boards sit below it is unknown ([fields-emi-budget](fields-emi-budget.md)). The goal should be a probability of passing, which needs gap 1.
19. **Cost model.** "Lowest manufacturing cost" needs a fab and assembly cost oracle covering layer count, dielectric, via types, minimum features and panel use. The corpus has limits, not prices.
20. **Internal consistency.** Workstreams disagree where assumptions differ: thermal λ of 21–29 vs 38 mm, fill effect −3.7% vs −6.5%. Needed: a physics regression suite that recomputes every [C] number on each change and cross-checks overlapping scripts.

### 4. Limits of our own thesis

- **Invisibility is not always the goal.** Sometimes the board should be part of the circuit: embedded or buried capacitance, planar inductors and transformers, PCB antennas, copper as a heat spreader, trace inductance as a filter element, fusible traces. A physics-first system should also *exploit* the board. That needs designed bodies with specs, which the vocabulary allows but no workstream developed [I].
- **The schematic is not fixed.** The strongest levers were often circuit changes: edge rate, series R, heatsink bonding, frequency choice ([worked-thought-experiments](worked-thought-experiments.md)). The layout system must be allowed to propose ECOs, with costs, to the circuit designer.
- **Worst-case budgets compound pessimism.** Summing worst cases across many structures over-constrains. Statistical budgets (RSS, chance constraints) need the calibration data from gap 1 to be defensible.
- **"Near-optimal" is provable only for self terms on a fixed raster** (lens VP's floors). For continuous layouts it needs a refinement study; for couplings and joint placement it remains unprovable.
- **Models from one author.** Critics and mutants, and estimators and the models that check them, were often written by the same workstream. Independent re-derivation (RG40) and real-escape seeding (V5) are needed before any physics score becomes a reward.

## Recommendations for our system

A second research wave, in this order (each is one workstream, about the size of this pass's):

| Wave-2 workstream | Output | Why first |
|---|---|---|
| A. Validation program ([designed](validation-program.md)) | Order the VOI-ranked coupons and the two-arm first board; mine EVM layouts with measured results | Unblocks every [C] number and gaps 18 and 20 |
| B. f_x transition and thin-sheet RL solver | Solver, per-harmonic return maps of 10 converter layouts | Most converters live there |
| C. Front-loaded levers: stackup synthesis, lever catalog, cost oracle | Stackup optimizer with fab prices; ECO menu with leverage/cost | Largest leverage per decision |
| D. Immunity, ESD and transients | ESD/EFT/surge path budgets, nonlinear victim models, macromodel pipeline | Uncovered physics with field-failure impact |
| E. System and environment | Enclosure, cable, heatsink and mounting boundary model; mission-profile regimes (pressure, temperature, humidity, vibration); lifetime budgets | Rules silently assume sea-level lab conditions |
| F. Bounds and duals | Floor oracles per structure class, relaxation bounds, a unified dual vector with validity margins | Makes "near-optimal" and the explanations honest |

Keep the existing wave's first experiments ([report](../../../reports/Physics-first%20PCB%20layout.md) §4) running in parallel. They do not depend on wave 2 except for calibration.

## Conflicts and open questions

- The altitude cooling figures are a rough model: laminar natural convection scaled by ρ^0.5, radiation to local air temperature, no sun and no forced flow. Real boards in a closed enclosure at altitude need an FV run with measured h.
- Gap ranking is a judgement call [I], ordered by how many results each gap unblocks.

## Sources

- Every physics-first topic doc's "Conflicts and open questions" section (linked inline).
- The f_x table and altitude estimate were computed inline (R_s = ρ_Cu/t; ISA densities); f_x matches [vocabulary](vocabulary.md) [C].

See also: [physics/README](README.md) · [ideas catalog](../../ideas/physics-first/README.md) · [myths-and-contested](../rules/myths-and-contested.md)
