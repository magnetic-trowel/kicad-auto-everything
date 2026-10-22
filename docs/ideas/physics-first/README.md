# Physics-first ideas catalog

About 890 ideas: ~660 from the eleven round-1 workstreams and 232 from the seven round-2 first-principles lenses. They build on the [original-ideas catalog](../original/README.md) (I1 budget ledger, N7 hot-loop placer, N8 decap assignment, R2 shadow returns, V1/V2 verification gates) and do not repeat it.

The philosophy is in [topics/physics/README](../../topics/physics/README.md) and the principles in [foundations](../../topics/physics/foundations.md). Corrections found by the [red team](../../topics/physics/red-team.md) override the numbers quoted in individual ideas.

Tags inside each file: **new** (not in the corpus), **combo** (known parts, new combination), **sharp** (an existing idea made buildable or given a number). Effort: S (days), M (weeks), L (months). Everything is untested [I] unless a number is tagged [C] (computed by us) or [P].

## Theme files (round 1)

| File | Ids | Count | Covers |
|---|---|---|---|
| [rule-replacements](rule-replacements.md) | RG1–RG53 | 53 | rule records, regime predicates, physics replacements for slogans, rule-retirement tests, rules as warm starts |
| [language](language.md) | LA1–LA52 | 52 | the vocabulary and `pcb-intent/0.3`: ports, loops, bands, budgets, operators, glyphs |
| [reasoning](reasoning.md) | DR1–DR56 | 56 | simulate the schematic, adjoint susceptibility, budgets from sensitivity, least-slack ordering, explanation |
| [joint-place-route](joint-place-route.md) | JPR1–JPR51 | 51 | simultaneous placement and routing, topology-carrying state, convergence, constraint prices |
| [optimization](optimization.md) | OP1–OP57 | 57 | physics spend models with gradients, adjoints, topology optimization of copper, legalization, search at scale |
| [simulation](simulation.md) | SIM1–SIM47 | 47 | fidelity ladder, proxies judged by decision quality, surrogates, caching, compute strategy |
| [power](power.md) | PW1–PW52 | 52 | waveform-derived copper roles, width optimum, commutation cells, PDN, Kelvin, inductor fields |
| [si-emi-rf](si-emi-rf.md) | FE1–FE56 | 56 | return-path EMF ledger, EMI chain as a placement loss, cavities and stitching, pad voids, RF structures |
| [thermal-hv-mfg](thermal-hv-mfg.md) | TM1–TM54 | 54 | thermal kernels, HV inception margin, altitude, yield and σ-margin costs, solder and stress physics |
| [critics](critics.md) | PC1–PC44 | 44 | physics scorecard, DRC-equivalent mutation benchmark, return-path quality, calibration |
| [cross-domain](cross-domain.md) | XD1–XD125 | 125 | IC power grids, power modules, stream-function coils, flow networks, topology optimization, graphics, biology |

## Lens files (round 2)

| File | Ids | Count | Covers |
|---|---|---|---|
| [lens-vp](lens-vp.md) | VP1–VP30 | 30 | certified floors and dual certificates, avoidable-loss reports, convex-first continuation, via capacity, equipartition, objective classes |
| [lens-ct](lens-ct.md) | CT1–CT32 | 32 | cut prices, topological events, board–world charge ledger, cycle census per band, grounding synthesis, topological gates |
| [lens-sy](lens-sy.md) | SY1–SY32 | 32 | adjoints and lead fields, periodic adjoints, slit and bridge prices, node budgets in ∫V dA, mode-conversion ledgers, scaled coupons |
| [lens-ls](lens-ls.md) | LS1–LS32 | 32 | complex-image PEEC, impedance-level classifier, wire medium and f_p band plan, regime plane, non-perturbative trigger, coupons |
| [lens-th](lens-th.md) | TH1–TH35 | 35 | modal Q ledger, tuned snubbers, damper placement, fluctuation–dissipation noise, thermoelectric checks, electro-thermal margin, life maps |
| [lens-in](lens-in.md) | IN1–IN37 | 37 | belief ledger, VOI engine, decision invariance, evaluator nuggets, ranking vs compliance, pre-registered bring-up |
| [lens-cd](lens-cd.md) | CD1–CD34 | 34 | conductor passports, exact removal and addition costs, leverage, job verbs, cancellation index, cycle-rank budgeting |

## Start here: 30 ideas in build order

Ordered so that each step gives the next one something to stand on. Round 3 reordered this list: measurement and exact kernels now come before optimization.

**1. Anchor in reality** ([validation-program](../../topics/physics/validation-program.md))
- **IN27** pre-registered bring-up as the measurement rung: predict every budget before the first board is built.
- **LS30** the ℓ_m return-band coupon: highest value per cost, and it decides whether a transition-band solver gets built.
- **PC29 + PC30** DRC-equivalent mutation benchmark with physics-labelled mutants.
- **IN13 + IN17** report P(LII ≤ 1), and use separate evaluators for ranking and for compliance.

**2. Exact kernels** ([physics-core-v2](../../topics/physics/physics-core-v2.md))
- **CT27 + CT28** topological gate first, metric weight second; physics events in the joint state.
- **CD1 + CD2 + CD3** piece passports; the exact removal cost of every piece from one diagonal; Thevenin additions.
- **SY7 / CT1** cut price for any objective (four lenses derived the same law).
- **VP2 + VP3 + VP7** certified floors with dual certificates, avoidable-loss reports, and evaluators that return guaranteed intervals.
- **LS1** complex-image PEEC across the R–L band.
- **SIM46** one PEEC core for every workstream.

**3. Understand the circuit as physics**
- **DR1 + DR3** net passports from schematic simulation, and `.noise` as the adjoint susceptibility engine.
- **SY2** periodic adjoint for switching and sampled victims.
- **CT9 + CT16** board–world charge ledger; the world node made mandatory.
- **LS5** impedance-level classifier with Z0 targets.
- **TH1 + TH2** modal Q ledger and an alarm for modes damped only by copper.

**4. Replace slogans with budgets**
- **RG2** regime predicates as dimensionless groups.
- **CT22 / SY22** every voltage budget names its closed loop.
- **FE1** return-path EMF ledger.
- **PW25** height × squares instead of loop area (with MS2, SIM15).
- **LS8 + LS9** wire-medium model and the f_p band plan, replacing λ/20 stitching.

**5. Optimize jointly with physics**
- **VP4 + VP20** convex-first continuation; tag every term as self, interaction or mask.
- **JPR1 + JPR14 + JPR41** band-tension placement forces, a channel-width legalizer, delayed acceptance.
- **LS15** switch representation (to modes, lines or dampers) when the loop gain reaches 1.
- **TH3** tuned snubber synthesis.
- **OP38** adjoint copper advisor (with the edit-shape correction).
- **JPR46** joint-versus-portfolio protocol at equal CPU.

Runners-up worth a day each: PW2, PW41, PW46, XD2, XD22, XD39, XD47, TM20+TM22, TM30, TM39, LA7, OP29, FE40, CD10, CD18, SY11, TH14, TH24, VP11, CT19, IN8+IN9.

## Same idea, several names

Merge these when building; the ids stay valid as aliases. Independent rediscovery is evidence, so these concepts carry more weight.

| Concept | Ids |
|---|---|
| Exact cut and edit pricing (four lenses) | CT1, CT2, SY6, SY7, SY9, CD2, CD3, CD6, VP (edit shape), XD2, SIM25, OP41 |
| The R–L return band as a length (four lenses) | VP16, VP17, SY25, LS1, LS2, LS12, CD17, CD19, RG19 |
| Impedance level, Z0 toward ΔV/ΔI (four directions) | LS5, LS6, VP19, PW2, XD19 (foundations T1) |
| World node and off-board conductors | CT9, CT16, IN6, SY27, TH11, DR28, FE14 |
| Designed dissipation | TH1–TH5, TH11, LS15, VP15, FE31, PW29, PW31 |
| Self vs interaction rows | VP20, VP23, CD9, CD11, SY23, LA45 |
| Budgets on closed loops | CT22, SY22, SY23, CD34, LA21 |
| Loop inductance from length × height / width, not area | PW25, OP22, SIM15, OP21, LA26 |
| One PEEC core | SIM46, SIM16, OP21, LS1 |
| One sheet operator (IR, pour L, heat, decap reach) | OP1, XD113, TM2, OP23, XD112, LS8 |
| Real physics kernels in an ePlace-style placer | XD112, OP24, OP23, VP21 |
| Keep-away halos from coupling curves | RG53, LA25, XD68, SY12, LS2 |
| Sense ports / Kelvin generalized | LA8, XD72, PW41, CD34, SY28 |
| Commutation cells as the placement unit | XD12, LA9, CT31, LS25 |
| Coupons chosen by decision value | IN28, LS30, LS31, SY31, PC37, SIM12, RG35, TM29, PW50 |
| Rules as priors and move generators | RG41, RG42, IN22, IN24 |
| Constraint and budget prices | JPR34, OP38, OP40, DR9, I4, VP9 |

## How these relate to the original catalog

- **I1/I2 budget ledger and dimensioned types:** made concrete by the basis set (RG), the vocabulary (LA), budgets from sensitivity (DR9) and closed-loop budgets (CT22).
- **N7 hot-loop nH placer:** should use MS2 or height × squares, not area (PW25, SIM15), and take floors from VP1.
- **N8 decap assignment:** should optimize cluster geometry and orientation (PW32, PW33, VP11) inside the wire-medium model (LS8).
- **R2 shadow return nets:** generalized by the return-path EMF ledger (FE1) and return words (CT29).
- **P1, P7 and S1 (router probes, live topological sketch, corridor contract):** subsumed by the joint state (JPR) and topological events (CT28).
- **V1/V2 gates:** instantiated by the mutation benchmark (PC29/PC30, CD16, IN36).
