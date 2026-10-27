# Physics-first ideas: design reasoning (DR)

How a system looks at a schematic plus a partial layout and decides, from physics, what the joint placement+routing optimizer must achieve. The topic docs hold the argument and the numbers:
- [design-reasoning-architecture](../../topics/physics/design-reasoning-architecture.md): pipeline, decomposition, least-slack ordering, roles, hand-off, beauty as coherence;
- [schematic-to-physics](../../topics/physics/schematic-to-physics.md): simulate the schematic, adjoint susceptibility, invisibility index, sensitivity budgets;
- [worked-thought-experiments](../../topics/physics/worked-thought-experiments.md): four boards, with numbers.

Everything here is a proposal [I] unless a number is tagged [C] (computed by `tools/research/physics/dr_*.py`). Tags: **new** (not found in prior docs), **combo** (new combination of existing ideas), **sharp** (sharpens an existing idea). Effort: S (days), M (weeks), L (months). Ids from the original catalog (I1, N7, R2, S4, V4, …) are in [ideas/original](../original/README.md). The joint optimizer the ideas feed is [joint-place-route](../../topics/physics/joint-place-route.md).

## Try first

| Rank | Idea | Why |
|---|---|---|
| 1 | DR1 + DR3 net passport with adjoint susceptibility | Replaces name heuristics with measured physics; one solve per output; demo agrees with ngspice [C] |
| 2 | DR13 output-binding detector | Stops the optimizer squeezing what doesn't matter (48 V bridge: overshoot never binds) [C] |
| 3 | DR17 least-slack priority τ | Turns "what is critical" into a number and a schedule |
| 4 | DR9 square-root budget allocation | Makes the I1 ledger automatic, with a closed form |
| 5 | DR27 isotherm-aligned precision parts | A cheap constraint no rule pack has; 37–110 LSB per resistor at stake [C] |

---

## A. Characterizing the schematic

**DR1. Net passport from schematic simulation** — *new, M.* Simulate each block (ngspice/Xyce, vendor models or stand-ins) and record, per net and branch: DC value, swing, peak dv/dt, current, peak di/dt, spectrum envelope, |Z(f)| and transfer to each output. It replaces keyword and refdes net roles with measured aggressor strength and victim susceptibility per band. Test: on 20 open boards, compare passport-derived critical nets with expert-labelled ones and with the layered classifier of [net-role-classification](../../topics/llm/net-role-classification.md).

**DR2. Hot-loop membership by measured di/dt** — *new, S.* In a transient run, rank branches by current energy above ~10 × f_sw; the branches that step at each edge are the hot loop. Topology tables become a check, not the source, and unusual topologies (SEPIC, multiphase, active clamp) are covered automatically. Test: 30 converters including 5 not in the [hot-loops](../../topics/rules/power/hot-loops.md) table; agreement with expert markup.

**DR3. `.noise` as an adjoint susceptibility engine** — *new, S.* Put fictitious noise resistors at every candidate injection site (large and shunt for C·dv/dt, small and series for M·di/dt or shared impedance) and run one `.noise`. Each `onoise_<device>` divided by that resistor's own density is |H| from that site. Demo: agrees with direct AC to 6e-13 and with ngspice 42 to four digits [C] ([dr_noise_adjoint.py](../../../tools/research/physics/dr_noise_adjoint.py)). Test: 10 blocks; compare timing and accuracy with per-site AC runs.

**DR4. Aggressor–victim matrix per band** — *combo, M.* Form A_k(f) from passports, S_j(f) from DR3, and require Σ S_j·κ_kj·A_k ≤ budget. Solving for κ_kj gives each pair's allowed coupling (fF, pH, mΩ) per band. This is the quantitative version of the I5 criticality field: criticality becomes "allowed coupling is small". Test: check that pairs flagged by the matrix match expert concerns on 10 mixed-signal boards, and count expert concerns the matrix misses.

**DR5. Envelope stand-ins with intervals** — *new, S.* When no model exists, the LLM extracts (V, I, t_r, f, duty) from the datasheet as intervals, and a trapezoid spectrum with interval arithmetic gives A_k(f) bounds. Uncertainty then shrinks budgets (DR16) instead of being ignored. Test: for parts with real models, compare the envelope bounds with simulated spectra; coverage should be ≥ 95 %.

**DR6. Model cards with validation tests** — *combo, M.* Each SPICE model or stand-in carries a card (source, licence, valid range, known gaps) and an LLM-written test against datasheet curves: efficiency, ripple, edge rate, PSRR. V1-style mutation testing checks that the tests are strong enough. This addresses validation ≠ simulation (10.7 % / 4.7 % mismatch, [block-recognition](../../topics/llm/block-recognition.md)). Test: seed 30 wrong models; measure the catch rate.

**DR7. Ground as many nodes** — *new, M.* In the physical netlist, split every ground symbol into per-pin nodes joined by the plane impedance network. The schematic's single ground hides every shared-impedance coupling, and this makes them simulable. Test: on 5 boards with known ground-coupling bugs, check that re-simulation reproduces the symptom.

**DR8. Spec-to-output compiler** — *new, S–M.* The LLM turns requirements (ripple %, ENOB, EMC class, BLE sensitivity, accuracy) into named outputs, budgets and derivation traces (I2). A human confirms the output list, not geometry. Test: 20 specs; expert agreement on outputs and budgets; count of budgets with no traceable source.

**DR55. Rectification flags for linear analysis** — *new, S.* Linear adjoints miss RF rectified into DC offset by op-amp and PGA inputs. Flag those nodes, attach EMIRR data or run a transient with the RF tone, and add a nonlinear susceptibility term. Test: compare predicted offset shifts with bench data on 3 amplifier front ends under injected RF.

## B. Budgets from sensitivities

**DR9. Square-root budget allocation** — *new, S.* With worst-case summation and a squeeze cost k_i/p_i, the optimum gives each structure a budget share ∝ √(k_i·s_i); with RSS summation, ∝ (k_i·s_i)^(1/3). It replaces the LLM's `allocate()` guesses in I1 with a formula. Test: on 10 boards, compare total squeeze cost (area, vias) against equal-share allocation at equal output deviation.

**DR10. Floor-referenced invisibility index** — *new, S.* LII = max over outputs of |y(layout) − y(floor)| ÷ B_y, where "floor" keeps unavoidable parasitics (packages, minimum mounting). A zero-parasitic ideal would make budgets infeasible by construction. A log-sum-exp version is the optimizer's master physics term. Test: rank 30 layouts by LII and by expert review; measure rank correlation.

**DR11. Trust-region re-linearization** — *sharp, S.* Sensitivities hold only near the point of linearization. The 12 V buck hot loop linearized at 0.8 nH predicts 1.01 vs 1.05 nH exact, but a 48 V bridge linearized at 10 nH predicts 16.5 nH where overshoot never binds below 40 nH [C]. Re-linearize after every optimizer round, inside a V4-style radius. Test: budget error vs radius on the two demo cells and 5 SPICE blocks.

**DR12. Closed-form edge budgets** — *new, S.* For any LC excited by an edge (hot loops, gate loops, ESD paths, decap resonances), L_max ≈ σ²/(2·C·ln(1/a′)), with σ = t_r/2.563 and a′ = a·e^(π/2Q). It is within ~30 % of the transient model in the regime where it applies [C]. It gives instant T0 budgets and explains the EPC sigmoid. Test: compare with transient SPICE across 50 cells and with published EPC/TI measurements.

**DR13. Output-binding detector** — *new, S.* For each structure, find which output's budget binds (overshoot, EMI ring, sense integrity, efficiency, thermal) before optimizing. In the 48 V bridge, overshoot never binds, so the loop budget must come from EMI or sensing [C]. Test: on 20 power stages, compare the detected binding output with expert judgment and measurement.

**DR14. Shadow prices to the LLM** — *sharp, S.* The joint optimizer returns each budget's multiplier ("0.1 nH of hot loop costs 2 mm² near U3"). The LLM negotiates and explains from those prices, never from its own estimates; this sharpens I4 from leave-one-out re-solves to duals. Test: LLM relaxation decisions with and without prices on over-constrained boards; overspend and iterations.

**DR15. Corner and statistical budgets** — *sharp, M.* Run Monte Carlo over parasitic-estimator error and part tolerance plus PVT corners, and set budgets at the 99th percentile. Rules of thumb hide their margins; this makes margins explicit and per board. Test: compare yield predictions against a small build with measured spread, e.g. SW overshoot across 20 boards.

**DR16. Uncertainty-discounted budgets** — *new, S.* An effective budget B·(1 − z·σ_model) tightens geometry where models are weak, and shows a price for buying accuracy (escalating fidelity or getting a vendor model). Test: in synthetic studies, check whether the escalation decisions this triggers pay for themselves in area or relaxations.

## C. Decomposition and ordering

**DR17. Least-slack-first priority (τ)** — *new, S.* τ = budget ÷ achievable floor per structure. Ascending τ sets tiers, seeds and continuation order for the joint optimizer, and τ < 1 triggers the ECO menu before optimizing. This is constraint programming's fail-first heuristic in physical units; it replaces fixed recipes such as "connectors, then ICs". Test: τ-ordered vs recipe-ordered continuation on 30 boards; PRC pass and LII at equal compute.

**DR18. Floor oracles** — *new, M.* Run each micro-solver (N7 hot loop, N8 decaps, chain embedders) unopposed to get the best achievable parasitic with these parts and this stackup. It gives τ's denominator and early infeasibility proofs. Test: oracle floors vs best published EVM layouts for 10 converters.

**DR19. Information-first exceptions** — *new, S.* A structure whose uncertainty could change the floorplan (antenna ground needs, unknown connector current) is resolved early by escalation or by asking a human, even when its τ is large. This is value of information, not slack. Test: count late floorplan changes with and without this rule in simulated sessions.

**DR20. Band-split coupling graph** — *new, M.* Label each coupling edge with its mechanism (shared R, M, C, field, thermal) and band (resistive, inductive, cable-mode, wave), and use the band's estimator. The crossover for each structure is where ωL = R. This keeps "returns spread resistively below ~100 kHz" and "returns follow the trace above 1 MHz" from being misapplied. Test: compare predictions with a PEEC solve across bands on 5 structures.

**DR21. Energy-flow DAG** — *combo, S.* Ports → converters → loads → heat, with currents from the operating point. Power trunks, dissipation sites and candidate quiet zones fall out before any geometry. Test: trunk widths and copper area against expert layouts; IR-drop error.

**DR22. Cell decomposition by HF current closure** — *new, M.* Partition the board into cells in which every HF current closes; only DC and declared signals may cross. Each crossing is a cut with an impedance budget. This turns "partition, don't split" into a checkable contract. Test: cell-crossing HF current from a plane solve vs expert partitions; EMI proxy correlation.

## D. Boundary conditions and plans

**DR23. Typed boundary-condition objects** — *new, S–M.* Ingest fixed items as port (current, CM reference, cable model), thermal boundary, chassis bond, radiator (antenna + keep-out + plane strip) or hole, not as locked footprints only. The physics model can then use them. Test: on 10 boards with mechanical constraints, check whether the derived requirements match the designer's (TVS placement, bond points).

**DR24. Connector-pair common-mode budget** — *new, M.* For each pair of cabled connectors, bound V_cm ≈ L_partial(plane path) × di/dt of HF current crossing between their references to ~1 mV (LearnEMC). Make it a differentiable optimizer term from the plane solver. It explains "connectors on one edge" and says when that is not enough. Test: correlate with near-field or cable-current measurements on 5 boards.

**DR25. DC flow field and quiet-zone map** — *combo, M.* Solve the copper sheet with port and load currents, and publish |∇V| (µV/mm) as a field the optimizer uses to keep sensitive references out of current. 0.3 A on a 60 × 40 mm 1 oz plane gives 0.7–4.6 µV/mm everywhere [C]. Test: predicted vs measured offsets on a precision board with movable load current.

**DR26. Current-free peninsula synthesis** — *new, M.* When topology cannot meet a DC budget, synthesize a slot and a narrow neck so that no load current enters the analog region. The interior gradient fell from 2.0 to 0.017 µV/mm (~120×) [C]. Optimize neck width and check that no signal crosses the slot. Test: gradients and measured offsets against a solid plane and a hand-drawn split.

**DR27. Isotherm-aligned precision parts** — *new, S.* From the thermal estimate, orient input-path resistors and junction pairs perpendicular to ∇T, and mirror P/N legs about an axis parallel to ∇T. At 0.21 K/mm, an 0603 aligned with the gradient carries 0.3–1 µV of thermal EMF [C]. Test: bench offset drift vs buck load for aligned and misaligned placements.

**DR28. Heatsink bond-node selection** — *new, S.* Compute tab capacitance × dv/dt for each device on a sink (~22 pF, ~71 mA for a TO-220 switch node at 3.2 V/ns [C]) and choose the bond (DC− at the bridge, shielded insulator, chassis via a capacitor) that closes the current locally. Test: conducted and radiated CM current for each bond on a motor-drive board.

**DR29. Plane roles from currents** — *new, S.* Choose GND/GND or GND/PWR inner layers from rail currents, IR budgets and plane-pair capacitance (3.5 pF/cm² for a 1.1 mm core, negligible [C]). Many 4-layer boards gain return continuity from GND/GND for free. Test: return-path critic findings and EMI proxy for both choices on 10 boards.

**DR30. Stackup chosen by budgets** — *combo, M.* Evaluate the fab's stackup menu against the hot-loop, crosstalk, impedance-width and cost budgets before geometry. 0.1 vs 0.2 mm prepreg halves lateral loop L and cuts the crosstalk factor at 1 mm about 4× [C]. Test: budget spend and cost across 20 boards for default vs chosen stackups.

**DR31. Antenna as a radiator object** — *new, M.* A fixed antenna brings its keep-out plus a protected ground-plane edge strip along which the board current flows, and a target plane length from the reference board. The optimizer treats the strip as a hard no-slot, no-part zone. Test: simulated (openEMS) efficiency of optimizer outputs with and without the strip constraint.

## E. Roles and the agent loop

**DR32. A physicist's toolset for the LLM** — *new, M.* The tools are model selection, a prediction log, a residual reader, an ECO menu, and oracles for closed forms. There are no geometry tools. This puts the LLM where it is strong (documents, mechanisms, code) and away from coordinates ([spatial-reasoning-limits](../../topics/llm/spatial-reasoning-limits.md)). Test: session outcomes and tokens vs an agent that also has move tools.

**DR33. Fidelity escalation by decision value** — *sharp, S.* Escalate to SPICE or a field solve only when |budget − estimate| < z·σ, or when the result could change a τ tier. This sharpens V4 from trust radius to value of information. Test: CPU-hours per correct decision vs fixed escalation schedules.

**DR34. Residual reading** — *sharp, S.* After each simulation, the LLM compares the result with its logged prediction (S4). A surprise must produce a mechanism hypothesis and a falsifying check before any further edits. Test: rate of wrong fixes after surprises, with and without the rule.

**DR35. Non-geometric lever menu** — *new, S–M.* Edge rate (gate resistor, GPIO slew), f_sw and synchronization, part package (low-ESL caps), capacitor matching (C0G 1 %), snubbers, ferrites and stackup, each with a price, sit beside geometry moves. A 4× slower clock edge buys 12 dB at 2.4 GHz [C]. Test: fraction of infeasible cases resolved without overspend, compared with geometry-only repair.

**DR36. Frequency planning** — *new, S.* Choose switching and clock frequencies so that harmonics avoid ADC alias bands (k·f_mod ± passband) and radio channels; build a spur map at each sensitive port. Many layout constraints then disappear. Test: count binding coupling budgets before and after planning on 10 mixed-signal and RF boards.

**DR37. One-page physics brief** — *sharp, S.* Outputs, budgets, model assumptions, binding structures and contested choices go to a human for confirmation, ordered by expected loss (U3). The human confirms physics, not millimetres. Test: designer time to approve and errors caught, compared with a constraint-list review.

## F. Hand-off with the joint optimizer

**DR38. Physics package schema** — *new, M.* The package holds ports and boundary conditions, structures with spend models, budgets, sensitivities, τ tiers, seeds, reservations and discrete alternatives, in the physics IR ([physics-ir](../../topics/physics/physics-ir.md)). It is the only channel from reasoning to geometry. Test: replay determinism; ablate each field and measure the optimizer's outcome change.

**DR39. Explanations from multipliers and derivations** — *new, S.* Generate "X is here because budget B (derived from …) binds at price P" sentences from optimizer duals and I2 derivation traces, never from LLM recall. Rationale precision should rise well above the 0.27 of LLM-drafted rationale ([design-rationale](../../topics/ux/design-rationale-and-intent-record.md)). Test: claim precision against an expert key.

**DR40. Continuation schedule from τ** — *new, S.* Inside the joint optimizer, ramp penalty weights in τ order: the tightest structures settle first while the rest stay soft, without a staged place-then-route pipeline. Test: convergence speed and final LII vs uniform weighting.

**DR41. Infeasibility certificates in physics units** — *new, M.* When budgets cannot coexist, return the minimal conflicting set with its physics, e.g. "tab capacitance × dv/dt alone exceeds the CM budget with a chassis bond". It feeds the ECO menu (S3). Test: certificate correctness on 20 deliberately infeasible cases.

## G. Beauty as coherence

**DR42. Locality index** — *new, M.* The fraction of each aggressor's above-crossover current that closes within its cell's bounding region, from the plane current solution. It is a physics definition of "clean": fields explained by few local structures. Test: correlation with expert "looks right" ratings and with EMI proxies on 30 boards.

**DR43. Physics-tagged convention metrics** — *new, S.* Tag each [looks-right metric](../../topics/verification/looks-right-metrics.md) as a physics proxy, convention-only, or divergent (neat parallel buses, uniform widths). Weight and gate them accordingly, so neatness never overrides physics. Test: reviewer acceptance and PRC pass with tagged vs untagged weights.

**DR44. Delay-and-coupling symmetry instead of shape symmetry** — *sharp, S.* Score differential symmetry by a mode-conversion proxy (skew, coupling imbalance, via asymmetry), not by mirror geometry. Asymmetric-looking routes with matched delay and coupling then pass. Test: proxy vs openEMS Scd21 on 20 pairs.

## H. Ideas from the worked cases

**DR45. Shunt outside the commutation loop** — *new, S.* Return the half-bridge's HF ceramic to the LS source node above the shunt, so the commutation current never crosses the shunt. It removes ~1.3 V/nH spikes from a 40 mV signal and the shunt's common-source inductance [C]. Test: SPICE plus a bench comparison of sense error at mid-PWM, overshoot and shunt di/dt for both returns.

**DR46. Common-source inductance detector** — *new, S.* From the physical netlist, find any inductance shared by a gate-drive loop and a power loop, and report it in volts (L·di/dt) against the gate drive. Test: detect seeded CSI in 20 driver layouts; correlate with measured switching-time change.

**DR47. ESD path as an aggressor** — *new, S.* Treat IEC 61000-4-2 (30 A, 0.8 ns) as a current source at each connector pin and compute the inductance shared between the ESD return and the protected IC's reference. A TVS ground via through 1.6 mm costs ~39 V, and one to L2 at 0.1 mm costs ~0.8 V [C]. Test: TLP or ESD-gun results for layouts ranked by shared inductance.

**DR48. Skew as an EMI budget** — *sharp, S.* Convert intra-pair skew to common-mode volts: V_cm ≈ (V_swing/2)·(Δt/t_r), giving ~3 mV at the USB 2.0 50 mil tolerance [C]. Allocate it together with connector and PHY asymmetry against the cable budget. Test: cable CM current vs skew on a USB test board.

**DR49. Slew rate as a layout variable** — *new, S.* Choose GPIO drive strength and slew jointly with geometry, priced in timing margin. 4× slower edges lower the 2.4 GHz harmonic by 12 dB [C]. Test: desense measurements at two slew settings, with the geometry freedom each buys.

**DR50. Reference layouts as measured floors** — *sharp, S.* When a vendor reference layout exists, extract its parasitics, use them as the floor (DR10, DR18), and require ours to spend no more. Copying becomes verifiable, not blind. Test: ours vs reference parasitics on 10 RF and converter blocks.

## I. Evaluation and learning

**DR51. Thought-experiment benchmark boards** — *new, M.* Build the four worked cases as synthetic KiCad boards with golden "binding outputs" and expected levers. Score whether a system finds the right binding output, not only whether DRC passes. Test: run rule-only and physics-first pipelines and compare.

**DR52. Rule-vs-physics diff report** — *new, S.* For each board, list where rule-following and physics-first disagree, with numbers (prepreg, plane roles, skew vs impedance, heatsink bond). It works as a review artifact and as a teaching tool. Test: designer acceptance rate of physics-first divergences in blind review.

**DR53. Sensitivity cache per block type** — *new, M.* Store S_j(f) and budgets per block family (buck at f_sw, crystal, ADC front end), keyed by parameters, to warm-start boards that lack models. Test: error of cached vs freshly simulated sensitivities on held-out blocks.

**DR54. Mixed-domain coupling edges** — *combo, M.* Add thermal EMF, TCR drift, MLCC piezo/microphonics, leakage under humidity and light (photodiodes) as edges in the coupling graph, each with its own oracle. Test: count field-failure modes from [field-failure-modes](../../topics/ux/field-failure-modes.md) that the extended graph would flag.

**DR56. Physics-first counterfactual from the optimizer** — *new, S.* For the top binding budgets, ask the joint optimizer for the layout with that budget relaxed 20 % and report what moves. A designer sees what each physics requirement is buying. Test: designer trust and understanding in a small user study.
