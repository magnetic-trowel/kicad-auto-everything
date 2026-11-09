# Physics-first ideas: design reasoning (DR)

Scope: ideas for deciding, from schematic + partial layout physics, what the joint place+route optimizer must achieve (DR1–DR56). Not here: pipeline, decomposition, least-slack ordering, roles, hand-off, beauty -> [design-reasoning-architecture](../../topics/physics/design-reasoning-architecture.md); schematic simulation, adjoint susceptibility, invisibility index, sensitivity budgets -> [schematic-to-physics](../../topics/physics/schematic-to-physics.md); four boards with numbers -> [worked-thought-experiments](../../topics/physics/worked-thought-experiments.md); the optimizer -> [joint-place-route](../../topics/physics/joint-place-route.md).
Keys: DR1–DR56, net passport, adjoint susceptibility, `.noise`, aggressor–victim matrix, square-root budget allocation, LII, layout invisibility index, edge budget, output-binding, shadow price, least slack, τ, floor oracle, quiet zone, peninsula, isotherm, heatsink bond, physics package, locality index, ESD aggressor, skew

- All proposals [I] unless [C] (computed by `tools/research/physics/dr_*.py`). Tags: **new** (not in prior docs), **combo** (new combination), **sharp** (sharpens existing). Effort S days, M weeks, L months. Original-catalog ids (I1, N7, R2, S4, V4, …) -> [ideas/original](../original/README.md).

## Try first

| Rank | Idea | Why |
|---|---|---|
| 1 | DR1 + DR3 | net passport + adjoint susceptibility replace name heuristics; one solve per output; demo agrees with ngspice [C] |
| 2 | DR13 | stops squeezing what doesn't bind (48 V bridge: overshoot never binds) [C] |
| 3 | DR17 | "critical" becomes a number τ and a schedule |
| 4 | DR9 | automatic I1 ledger, closed form |
| 5 | DR27 | cheap constraint no rule pack has; tens of LSB per resistor at stake ([case C](../../topics/physics/worked-thought-experiments.md#c-24-bit-adc-next-to-a-switching-supply)) [C] |

## A. Characterizing the schematic

- **DR1** Net passport from schematic simulation (*new, M*): simulate each block (ngspice/Xyce, vendor models or stand-ins); record per net/branch DC value, swing, peak dv/dt, current, peak di/dt, spectrum envelope, |Z(f)|, transfer to each output; replaces keyword/refdes roles. Test: 20 open boards vs expert labels and the layered classifier ([net-role-classification](../../topics/llm/net-role-classification.md)).
- **DR2** Hot-loop membership by measured di/dt (*new, S*): rank branches by current energy above ~10 × f_sw in a transient; branches stepping at each edge = hot loop; topology tables become a check; covers SEPIC, multiphase, active clamp. Test: 30 converters incl. 5 not in the [hot-loops](../../topics/rules/power/hot-loops.md) table.
- **DR3** `.noise` as an adjoint susceptibility engine (*new, S*): fictitious noise resistors at every candidate injection site (large shunt for C·dv/dt, small series for M·di/dt or shared Z), one `.noise` run; `onoise_<device>` ÷ that resistor's density = |H| from the site; demo agrees with direct AC and ngspice [C] ([method, numbers](../../topics/physics/schematic-to-physics.md#susceptibility-from-one-adjoint-solve)). Test: 10 blocks, time/accuracy vs per-site AC.
- **DR4** Aggressor–victim matrix per band (*combo, M*): A_k(f) from passports, S_j(f) from DR3, require Σ S_j·κ_kj·A_k ≤ budget; solve allowed κ_kj (fF, pH, mΩ) per pair per band = quantitative I5 criticality. Test: matrix-flagged pairs vs expert concerns on 10 mixed-signal boards, misses counted.
- **DR5** Envelope stand-ins with intervals (*new, S*): no model → LLM extracts (V, I, t_r, f, duty) intervals from the datasheet; interval trapezoid spectrum bounds A_k(f); uncertainty shrinks budgets (DR16). Test: coverage ≥ 95% vs simulated spectra of modelled parts.
- **DR6** Model cards with validation tests (*combo, M*): each model carries a card (source, licence, valid range, known gaps) + LLM-written test vs datasheet curves (efficiency, ripple, edge rate, PSRR); V1-style mutation checks test strength. Addresses validation ≠ simulation (10.7% / 4.7% mismatch, [block-recognition](../../topics/llm/block-recognition.md)). Test: catch rate on 30 seeded wrong models.
- **DR7** Ground as many nodes (*new, M*): split each ground symbol into per-pin nodes joined by the plane impedance network so shared-impedance couplings become simulable. Test: 5 boards with known ground bugs; symptom reproduced.
- **DR8** Spec-to-output compiler (*new, S–M*): LLM turns requirements (ripple %, ENOB, EMC class, BLE sensitivity, accuracy) into named outputs, budgets, derivation traces (I2); human confirms outputs, not geometry. Test: 20 specs, expert agreement, untraceable budgets.
- **DR55** Rectification flags for linear analysis (*new, S*): linear adjoints miss RF rectified into DC offset at op-amp/PGA inputs; flag those nodes, attach EMIRR data or run a transient with the RF tone, add a nonlinear susceptibility term. Test: offset shifts vs bench on 3 front ends under injected RF.

## B. Budgets from sensitivities

- **DR9** Square-root budget allocation (*new, S*): worst-case sum, share ∝ √(k_i·s_i), RSS ∝ (k_i·s_i)^(1/3) ([derivation](../../topics/physics/schematic-to-physics.md#budgets-from-sensitivities)); replaces `allocate()` guesses in I1. Test: total squeeze cost (area, vias) vs equal shares at equal output deviation, 10 boards.
- **DR10** Floor-referenced invisibility index (*new, S*): LII against a floor of unavoidable parasitics, not a zero-parasitic ideal ([definition](../../topics/physics/schematic-to-physics.md#outputs-deviation-and-the-invisibility-index)); log-sum-exp form = optimizer's master physics term. Test: rank correlation with expert review, 30 layouts.
- **DR11** Trust-region re-linearization (*sharp, S*): linearized budgets hold near the operating point and fail for the slow 48 V bridge ([demo](../../topics/physics/schematic-to-physics.md#budgets-from-sensitivities)) [C]; re-linearize each optimizer round inside a V4-style radius. Test: budget error vs radius, two demo cells + 5 SPICE blocks.
- **DR12** Closed-form edge budgets (*new, S*): any edge-excited LC (hot loops, gate loops, ESD paths, decap resonances): L_max ≈ σ²/(2·C·ln(1/a′)) ([definition](../../topics/physics/schematic-to-physics.md#budgets-from-sensitivities)); within ~30% of the transient model in its regime [C]; instant T0 budgets, explains the EPC sigmoid. Test: transient SPICE on 50 cells, published EPC/TI data.
- **DR13** Output-binding detector (*new, S*): per structure find which output binds (overshoot, EMI ring, sense integrity, efficiency, thermal) before optimizing; 48 V bridge: overshoot never binds, so the loop budget comes from EMI or sensing ([case B](../../topics/physics/worked-thought-experiments.md#b-48-v-half-bridge-motor-driver-with-a-heatsink-and-a-low-side-shunt)) [C]. Test: 20 power stages vs expert and measurement.
- **DR14** Shadow prices to the LLM (*sharp, S*): optimizer returns each budget's multiplier ("0.1 nH of hot loop costs 2 mm² near U3"); LLM negotiates/explains only from prices; sharpens I4 from leave-one-out re-solves to duals. Test: relaxation decisions with/without, over-constrained boards.
- **DR15** Corner and statistical budgets (*sharp, M*): Monte Carlo over estimator error + part tolerance + PVT corners; budgets at the 99th percentile; margins explicit per board. Test: yield prediction vs measured spread (SW overshoot on 20 boards).
- **DR16** Uncertainty-discounted budgets (*new, S*): effective budget B·(1 − z·σ_model) tightens geometry where models are weak and prices buying accuracy (escalation, vendor model). Test: do triggered escalations pay off in area/relaxations (synthetic).

## C. Decomposition and ordering

- **DR17** Least-slack-first priority (τ) (*new, S*): τ = budget / achievable floor per structure ([algorithm](../../topics/physics/design-reasoning-architecture.md#ordering-least-slack-first)); ascending τ sets tiers, seeds, continuation order; τ < 1 triggers the ECO menu first. Fail-first heuristic in physical units; replaces "connectors, then ICs". Test: τ vs recipe order on 30 boards, PRC pass and LII at equal compute.
- **DR18** Floor oracles (*new, M*): run each micro-solver (N7 hot loop, N8 decaps, chain embedders) unopposed → best achievable parasitic with these parts/stackup = τ denominator, early infeasibility proofs. Test: vs best published EVM layouts, 10 converters.
- **DR19** Information-first exceptions (*new, S*): a structure whose uncertainty could change the floorplan (antenna ground needs, unknown connector current) is resolved early (escalation or human) even at large τ: value of information, not slack. Test: late floorplan changes in simulated sessions.
- **DR20** Band-split coupling graph (*new, M*): each coupling edge labelled by mechanism (shared R, M, C, field, thermal) and band (resistive, inductive, cable-mode, wave), with the band's estimator; crossover where ωL = R; prevents misapplying "returns spread resistively below ~100 kHz" / "follow the trace above 1 MHz". Test: vs PEEC across bands, 5 structures.
- **DR21** Energy-flow DAG (*combo, S*): ports → converters → loads → heat with operating-point currents; trunks, dissipation sites, quiet zones before geometry. Test: trunk widths, copper area vs expert; IR-drop error.
- **DR22** Cell decomposition by HF current closure (*new, M*): partition into cells where every HF current closes; only DC and declared signals cross; each crossing = cut with an impedance budget ("partition, don't split" as a contract). Test: cell-crossing HF current from a plane solve vs expert partitions; EMI proxy correlation.

## D. Boundary conditions and plans

- **DR23** Typed boundary-condition objects (*new, S–M*): fixed items ingested as port (current, CM reference, cable model), thermal boundary, chassis bond, radiator (antenna + keep-out + plane strip) or hole, not only locked footprints. Test: derived requirements (TVS placement, bond points) vs designer's on 10 boards.
- **DR24** Connector-pair common-mode budget (*new, M*): per cabled connector pair V_cm ≈ L_partial(plane path) × di/dt of HF current crossing between their references ≤ ~1 mV (LearnEMC); differentiable term from the plane solver; explains "connectors on one edge" and when it is not enough. Test: near-field/cable-current on 5 boards.
- **DR25** DC flow field and quiet-zone map (*combo, M*): solve copper sheet with port/load currents, publish |∇V| (µV/mm) to keep sensitive references out of current ([case C](../../topics/physics/worked-thought-experiments.md#c-24-bit-adc-next-to-a-switching-supply)) [C]. Test: predicted vs measured offsets with movable load current.
- **DR26** Current-free peninsula synthesis (*new, M*): if topology cannot meet a DC budget, synthesize slot + narrow neck so no load current enters the analog region (~120× lower gradient, [case C](../../topics/physics/worked-thought-experiments.md#c-24-bit-adc-next-to-a-switching-supply)) [C]; optimize neck width, check no signal crosses the slot. Test: vs solid plane and hand split.
- **DR27** Isotherm-aligned precision parts (*new, S*): orient input-path resistors and junction pairs ⊥ ∇T, mirror P/N legs about an axis ∥ ∇T ([case C](../../topics/physics/worked-thought-experiments.md#c-24-bit-adc-next-to-a-switching-supply)) [C]. Test: offset drift vs buck load, aligned vs misaligned.
- **DR28** Heatsink bond-node selection (*new, S*): tab C × dv/dt per device on a sink ([case B](../../topics/physics/worked-thought-experiments.md#b-48-v-half-bridge-motor-driver-with-a-heatsink-and-a-low-side-shunt), [IR form](../../topics/physics/physics-ir-examples.md#6-48-v-half-bridge-motor-phase-with-low-side-shunt)) [C]; choose bond (DC− at the bridge, shielded insulator, chassis via a cap) closing current locally. Test: CM current per bond on a motor drive.
- **DR29** Plane roles from currents (*new, S*): GND/GND vs GND/PWR inner layers from rail currents, IR budgets, plane-pair C (negligible for a 1.1 mm core, [case A](../../topics/physics/worked-thought-experiments.md#a-12-v--33-v-buck-mcu-with-a-usb-20-hs-phy-24-mhz-crystal-4-layers-fixed-usb-c)) [C]; many 4-layer boards gain return continuity from GND/GND for free. Test: return critic + EMI proxy, both choices, 10 boards.
- **DR30** Stackup chosen by budgets (*combo, M*): evaluate the fab stackup menu against hot-loop, crosstalk, impedance-width, cost budgets before geometry; e.g. 0.1 mm prepreg in [case A](../../topics/physics/worked-thought-experiments.md#a-12-v--33-v-buck-mcu-with-a-usb-20-hs-phy-24-mhz-crystal-4-layers-fixed-usb-c) [C]. Test: spend and cost, default vs chosen, 20 boards.
- **DR31** Antenna as a radiator object (*new, M*): fixed antenna brings keep-out + protected ground-edge strip (hard no-slot, no-part) + target plane length from the reference board. Test: openEMS efficiency with/without strip constraint.

## E. Roles and the agent loop

- **DR32** A physicist's toolset for the LLM (*new, M*): model selection, prediction log, residual reader, ECO menu, closed-form oracles; no geometry tools ([spatial-reasoning-limits](../../topics/llm/spatial-reasoning-limits.md)). Test: outcomes and tokens vs an agent with move tools.
- **DR33** Fidelity escalation by decision value (*sharp, S*): escalate to SPICE/field solve only if |budget − estimate| < z·σ or a τ tier could change; sharpens V4 from trust radius to VOI. Test: CPU-hours per correct decision vs fixed schedules.
- **DR34** Residual reading (*sharp, S*): after each simulation compare with the logged prediction (S4); a surprise requires a mechanism hypothesis + falsifying check before further edits. Test: wrong fixes after surprises with/without.
- **DR35** Non-geometric lever menu (*new, S–M*): edge rate (gate R, GPIO slew), f_sw/sync, package (low-ESL caps), cap matching (C0G 1%), snubbers, ferrites, stackup, each priced, beside geometry moves ([case D](../../topics/physics/worked-thought-experiments.md#d-24-ghz-radio-with-a-chip-antenna-fixed-at-one-corner)) [C]. Test: infeasible cases resolved without overspend vs geometry-only.
- **DR36** Frequency planning (*new, S*): pick switching/clock frequencies so harmonics avoid ADC alias bands (k·f_mod ± passband) and radio channels; spur map per sensitive port. Test: binding coupling budgets before/after on 10 boards.
- **DR37** One-page physics brief (*sharp, S*): outputs, budgets, assumptions, binding structures, contested choices, ordered by expected loss (U3), confirmed by a human. Test: approval time and errors caught vs constraint-list review.

## F. Hand-off with the joint optimizer

- **DR38** Physics package schema (*new, M*): ports, boundary conditions, structures with spend models, budgets, sensitivities, τ tiers, seeds, reservations, discrete alternatives in the [physics-ir](../../topics/physics/physics-ir.md); sole channel reasoning → geometry. Test: replay determinism; per-field ablation.
- **DR39** Explanations from multipliers and derivations (*new, S*): "X is here because budget B (derived from …) binds at price P" from duals + I2 traces, never LLM recall; target well above the 0.27 precision of LLM-drafted rationale ([design-rationale](../../topics/ux/design-rationale-and-intent-record.md)). Test: claim precision vs expert key.
- **DR40** Continuation schedule from τ (*new, S*): ramp penalty weights in τ order inside the joint optimizer; tightest settle first, no staged place-then-route. Test: convergence speed, final LII vs uniform.
- **DR41** Infeasibility certificates in physics units (*new, M*): minimal conflicting set with its physics ("tab capacitance × dv/dt alone exceeds the CM budget with a chassis bond"), feeding the ECO menu (S3). Test: correctness on 20 infeasible cases.

## G. Beauty as coherence

- **DR42** Locality index (*new, M*): fraction of each aggressor's above-crossover current closing within its cell's bounding region (plane solution) = physics definition of "clean". Test: vs expert "looks right" ratings and EMI proxies, 30 boards.
- **DR43** Physics-tagged convention metrics (*new, S*): tag each [looks-right metric](../../topics/verification/looks-right-metrics.md) physics proxy / convention-only / divergent (neat parallel buses, uniform widths); weight and gate so neatness never overrides physics. Test: acceptance + PRC pass, tagged vs untagged.
- **DR44** Delay-and-coupling symmetry instead of shape symmetry (*sharp, S*): score diff-pair symmetry by a mode-conversion proxy (skew, coupling imbalance, via asymmetry), not mirror geometry. Test: proxy vs openEMS Scd21 on 20 pairs.

## H. Ideas from the worked cases

- **DR45** Shunt outside the commutation loop (*new, S*): return the half-bridge HF ceramic to the LS source node above the shunt; removes shunt-ESL spikes and common-source inductance ([case B](../../topics/physics/worked-thought-experiments.md#b-48-v-half-bridge-motor-driver-with-a-heatsink-and-a-low-side-shunt)) [C]. Test: SPICE + bench, sense error at mid-PWM, overshoot, shunt di/dt.
- **DR46** Common-source inductance detector (*new, S*): find inductance shared by gate-drive and power loops; report L·di/dt in volts vs the gate drive. Test: seeded CSI in 20 driver layouts; switching-time change.
- **DR47** ESD path as an aggressor (*new, S*): IEC 61000-4-2 (30 A, 0.8 ns) as a current source at each connector pin; inductance shared by ESD return and protected IC reference (TVS via depth, [case A](../../topics/physics/worked-thought-experiments.md#a-12-v--33-v-buck-mcu-with-a-usb-20-hs-phy-24-mhz-crystal-4-layers-fixed-usb-c)) [C]. Test: TLP/ESD-gun on layouts ranked by shared L.
- **DR48** Skew as an EMI budget (*sharp, S*): V_cm ≈ (V_swing/2)·(Δt/t_r) ([case A](../../topics/physics/worked-thought-experiments.md#a-12-v--33-v-buck-mcu-with-a-usb-20-hs-phy-24-mhz-crystal-4-layers-fixed-usb-c)) [C]; allocate with connector and PHY asymmetry against the cable budget. Test: cable CM current vs skew, USB test board.
- **DR49** Slew rate as a layout variable (*new, S*): GPIO drive/slew chosen with geometry, priced in timing margin ([case D](../../topics/physics/worked-thought-experiments.md#d-24-ghz-radio-with-a-chip-antenna-fixed-at-one-corner)) [C]. Test: desense at two slew settings, geometry freedom bought.
- **DR50** Reference layouts as measured floors (*sharp, S*): extract a vendor reference layout's parasitics as the floor (DR10, DR18); ours must spend no more. Test: 10 RF and converter blocks.

## I. Evaluation and learning

- **DR51** Thought-experiment benchmark boards (*new, M*): the four worked cases as synthetic KiCad boards with golden binding outputs and expected levers; score finding the binding output, not just DRC. Test: rule-only vs physics-first pipelines.
- **DR52** Rule-vs-physics diff report (*new, S*): per board, where rule-following and physics-first disagree, with numbers (prepreg, plane roles, skew vs impedance, heatsink bond); review + teaching artifact. Test: blind-review acceptance of divergences.
- **DR53** Sensitivity cache per block type (*new, M*): S_j(f) and budgets per block family (buck at f_sw, crystal, ADC front end), keyed by parameters, warm-start model-less boards. Test: cached vs fresh error on held-out blocks.
- **DR54** Mixed-domain coupling edges (*combo, M*): thermal EMF, TCR drift, MLCC piezo/microphonics, leakage under humidity and light (photodiodes) as coupling edges, each with an oracle. Test: [field-failure-modes](../../topics/ux/field-failure-modes.md) flagged.
- **DR56** Physics-first counterfactual from the optimizer (*new, S*): relax each top binding budget 20%, report what moves, showing what each requirement buys. Test: designer trust in a small user study.
