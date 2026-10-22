# Open problems and limits of physics-first layout

**TL;DR**
- **The largest open problem is ground truth.** Every [C] number is model against model, and no open dataset ties a layout to measured physics. The value-of-information-ranked program in [validation-program](validation-program.md) is the plan.
- **Open physics regimes:** slotted, perforated and finite planes, and DC to tens of kHz near precision analog. The R–L return band is a length, ℓ_m = R_s/(π·μ0·f), with closed forms for intact planes ([lens-ls](lens-ls.md)).
- **Thinly covered physics:**
  - immunity, ESD and nonlinear victims;
  - large-signal transients;
  - the system around the board (enclosure, cables, heatsink, mounting);
  - environment and mission profile;
  - lifetime reliability;
  - platform noise into radios.
- **Open method problems:** floors for couplings and EMI masks, continuum (not raster) bounds, robustness to variation, decisions made before routing (stackup, parts, frequencies) as optimization variables, and reviewability of physics-optimal geometry.
- **Limits of the thesis:** sometimes the board should *be* a component, the schematic is not fixed, worst-case budgets compound pessimism, and near-optimality is provable only for self terms.

Tags: [P] primary, [S] secondary, [I] inference, [C] computed. The f_x table and the altitude estimate were computed for this doc with numpy (R_s = ρ_Cu/t; ISA air).

## Key facts

### Tier 1: blocking or highest leverage

1. **Ground truth.** No open dataset links layouts to measured R, L, coupling, emissions or temperature. The common-mode and loop-radiation critics have no EMI ground truth. Two measurements anchor everything else ([validation-program](validation-program.md), [validation-coupons](validation-coupons.md)):
   - coupons placed only where rival predictions differ by 13× to 28 dB, led by the ℓ_m return-band coupon;
   - a pre-registered two-arm first board (rule-following vs physics-first), measured in its enclosure with real cables.
   
   Vendor EVM reports with both layout and measurements are the cheapest further source.
2. **Slotted, finite and low-frequency return paths.** The return spreads over a length band: half lies within ℓ_m/2 of the trace. Above ~300 kHz on 1 oz copper it closes within a few mm. At 100 kHz about 18% still flows beyond ±5 mm (h = 0.1 mm). Four to six complex images reproduce intact planes within 0.5–3.5% [C] ([lens-ls](lens-ls.md), [lens-vp](lens-vp.md)). Open:
   - slotted, perforated and finite planes, which need a thin-sheet RL solver validated against meshed-plane PEEC;
   - DC to tens of kHz near precision analog, where star grounds pay only below ~6 kHz at 10 mm on 1 oz ([derivation-audit](derivation-audit.md)).
   
   The table gives the frequency at which the band crosses ℓ = h:

   | Plane copper | f_x at h = 0.075 / 0.1 / 0.2 / 1.6 mm |
   |---|---|
   | 0.5 oz (17.5 µm) | 1.66 / 1.25 / 0.62 MHz / 78 kHz |
   | 1 oz (35 µm) | 830 / 622 / 311 / 39 kHz |
   | 2 oz (70 µm) | 415 / 311 / 156 / 19 kHz |

3. **Floors and bounds beyond self terms.** Self terms (loss, loop L, thermal R) have certified floors from convex relaxation with dual certificates, on a given raster; the floor moves 2–13% between 0.2 and 0.1 mm grids ([lens-vp](lens-vp.md)) [C]. Open:
   - floors for couplings and EMI masks;
   - continuum bounds (refinement studies);
   - joint placement.
4. **Decisions made before routing, as variables.** Stackup, outline, connector edge, part and package, pinout, switching frequency and edge rate carry the most leverage; for example, one EMI case gives 24 dB for removing a slot against 3 dB for slower edges ([fields-emi-budget](fields-emi-budget.md)). Needed:
   - a lever catalog with physics leverage and cost;
   - stackup synthesis with a fab cost model;
   - frequency planning against radio bands and plane-pair resonances;
   - questions to the user chosen by value of information.
5. **Infrastructure.** Needed:
   - an open multi-layer topological router with kinetic maintenance (none exists);
   - one PEEC and sheet core ([physics-core-v2](physics-core-v2.md));
   - a KiCad → physics-graph exporter;
   - zone-arc support checked in KiCad 10/11.

### Tier 2: physics covered thinly

6. **Immunity, ESD and transients.** Reciprocity covers linear coupling, not nonlinear victims: resets, latch-up, TVS snapback, op-amp rectification ([schematic-to-physics](schematic-to-physics.md)). An ESD strike carries ~30 A/ns, so 1 nH of shared path is 30 V. ESD, EFT and surge paths are designed loops with budgets, from the cable shield to the chassis or return, never through logic ground. Radiated immunity needs field-to-trace coupling models (Taylor, Agrawal).
7. **Large-signal co-simulation.** Linearized budgets fail for slow-edged bridges, and an undamped LC-step model gives near-100% overshoot almost regardless of L ([schematic-to-physics](schematic-to-physics.md), [physics-ir-examples](physics-ir-examples.md)). Needed:
   - extraction → vector fitting or PRIMA with passivity enforcement → a SPICE subcircuit;
   - transients with vendor models, and validated stand-ins for encrypted ones;
   - transient and periodic adjoints.
8. **The system around the board.** The heatsink is a ~22 pF feed to the outside ([worked-thought-experiments](worked-thought-experiments.md)). Cable common-mode impedance moves the EMI verdict by 13–21 dB ([fields-emi-budget](fields-emi-budget.md)). Mounting holes are mechanical anchors, chassis bonds, cavity shorts and CM paths at once. Needed: the minimal enclosure, cable and mounting description the system must ask for, and the optimum's sensitivity to it.
9. **Environment and mission profile.** Thermal and HV practice assumes sea level, 25 °C and still air. With h_conv ∝ ρ^0.5 (laminar natural convection) plus radiation, total h falls from ~12 W/m²K at sea level to ~4–5 at 20 km [C, rough]. Temperature rise per watt on an area-limited board then roughly triples, and the spreading length grows ~1.7×. Near 20 km, gaps sit near the Paschen minimum ([hv-and-manufacturing-physics](hv-and-manufacturing-physics.md)). Cold shifts MLCC capacitance and solder fatigue; vacuum removes convection. Regimes must carry pressure, temperature range, humidity and vibration as well as frequency.
10. **Lifetime reliability.** Thermal-cycling fatigue (part position relative to edges, screws and large packages), via-barrel fatigue, CAF and electrochemical migration under bias and humidity, creep corrosion, MLCC flex. Needed: a lifetime budget from a mission profile (Coffin–Manson or Engelmaier class models), with placement as the lever ([lens-th](lens-th.md)).
11. **Platform noise into radios.** The ground plane is part of the antenna. Needed: near-field coupling of digital and switching harmonics into the antenna port, per channel, as a placement objective.
12. **Precision analog beyond distance.** DC plane gradients and thermal EMF dominate a 24-bit front end ([worked-thought-experiments](worked-thought-experiments.md)). Leakage, humidity, dielectric absorption, guard design, MLCC microphonics and inductor stray fields need measured libraries.

### Tier 3: method problems

13. **Robustness to variation.** Process (Dk, etch, registration), part tolerances, temperature, ageing, alternate parts and model σ. The ledger needs σ propagation; the optimizer needs chance constraints or worst-case corners.
14. **Coupled physics and self-consistency.** Spectra depend on the layout (ringing sets GHz content), resistance depends on temperature, and warpage affects joints. Build a coupling-strength matrix, and iterate to a fixed point only where coupling is strong.
15. **Reviewability.** Organic pours, arcs and any-angle routes must survive review, CAM and later edits. Needed: a user study, and a regularity term that trades a little physics for a lot of readability.
16. **LLM physics competence.** Model choice, mechanism hypotheses (LA39) and anticipating results are unmeasured. Circuits that simulate can still be wrong. Needed: a benchmark of "find the coupling mechanism" tasks, drawn from the mutation benchmark and known respin causes.
17. **Physics-labelled data.** Synthetic boards with field-solver labels, real boards with known failures (git repair histories), and EVMs as references.
18. **Certification probability.** MREMC is a worst case. The goal is a probability of passing, which needs gap 1.
19. **Cost model.** "Lowest manufacturing cost" needs a fab and assembly cost oracle covering layer count, dielectric, via types, minimum features and panel use.
20. **Regression suite.** Every [C] number recomputed on each change, with overlapping scripts cross-checked, to the standard in [verification-and-limits](verification-and-limits.md).

### Limits of the thesis

- **The board can be a component.** Embedded capacitance, planar magnetics, PCB antennas, copper heat spreaders, trace inductance in filters and fusible traces are designed bodies with specs. The vocabulary allows them, but they need their own design methods [I].
- **The schematic is not fixed.** Edge rate, series R, heatsink bonding and frequency choice are often the strongest levers ([worked-thought-experiments](worked-thought-experiments.md)). The layout system proposes ECOs, with costs, to the circuit designer.
- **Worst-case budgets compound pessimism.** Statistical budgets (RSS, chance constraints) need calibration data to be defensible.
- **Near-optimality is provable only for self terms**, on a given raster ([lens-vp](lens-vp.md)).
- **Independent checks are required.** Critics and the faults that test them, and estimators and their references, must come from independent methods before any physics score becomes an optimization reward (RG40, V5).

## Recommendations for our system

Next research, in order:

| Work | Output | Why first |
|---|---|---|
| Validation program | VOI-ranked coupons and the two-arm first board; mined EVM data | Anchors every [C] number and gap 18 |
| Thin-sheet RL solver | Return maps for slotted and finite planes; precision-ground rules | Decides gap 2 |
| Levers before routing | Stackup optimizer with fab prices; ECO menu with leverage and cost | Largest leverage per decision |
| Immunity, ESD and transients | Path budgets, nonlinear victim models, macromodel pipeline | Uncovered physics with field-failure impact |
| System and environment | Enclosure, cable, heatsink and mounting model; mission-profile regimes; lifetime budgets | Practice assumes sea-level lab conditions |
| Bounds and duals | Floors for couplings, continuum bounds, duals with validity margins | Makes "near-optimal" and explanations exact |

## Conflicts and open questions

- The altitude cooling figures are a rough model: laminar natural convection scaled by ρ^0.5, radiation to local air temperature, no sun and no forced flow. Real boards in a closed enclosure at altitude need a finite-volume run with measured h.
- The gap ranking is a judgement [I], ordered by how many results each gap unblocks.

## Sources

The "Conflicts and open questions" sections of the physics-first topic docs (linked inline), and [verification-and-limits](verification-and-limits.md).

See also: [physics/README](README.md) · [cross-workstream-synthesis](cross-workstream-synthesis.md) · [ideas catalog](../../ideas/physics-first/README.md)
