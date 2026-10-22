# Physics-first ideas catalog

About 650 ideas from the eleven physics-first workstreams. They build on the [original-ideas catalog](../original/README.md) (I1 budget ledger, N7 hot-loop placer, N8 decap assignment, R2 shadow returns, V1/V2 verification gates) and do not repeat it. The philosophy and principles are in [topics/physics/README](../../topics/physics/README.md). Tags inside each file: **new** (not in the corpus), **combo** (known parts, new combination), **sharp** (an existing idea made buildable or given a number). Effort: S (days), M (weeks), L (months). Everything is untested [I] unless a number is tagged [C] (computed by us) or [P].

## Theme files

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

## Start here: 30 ideas in build order

Picked from each workstream's own top list, then ordered so that each step gives the next one something to stand on.

**1. Measure before optimizing** (the scorecard comes before any physics reward, per the V1/V2 gate)
- **PC29** DRC-equivalent mutation benchmark: planted faults that leave DRC counts unchanged.
- **PC30** physics-labelled mutants: each fault carries its physics delta, so improvements and regressions are scored separately.
- **PC6** RPQF-lite, a closed-form return-path quality factor per net.
- **PC9** a fill counts as reference copper only if it is connected and stitched.
- **PC44** layer-type hygiene: planes typed `signal` invite the router to route through them.

**2. One physics core**
- **SIM46** merge the three PEEC prototypes into one core.
- **SIM16** image-plane multi-filament PEEC as the default quasi-static (F2) solve.
- **SIM15** MS2 as the µs loop-inductance spend model.
- **OP1** one sheet operator for IR drop, pour inductance and heat.
- **TM2** image-lattice thermal kernel.
- **SIM7** judge every proxy by decision quality, not R².
- **SIM34** residual surrogates on physics baselines.

**3. Understand the circuit as physics**
- **DR1** net passports from schematic simulation.
- **DR3** `.noise` as an adjoint susceptibility engine.
- **DR13** find the binding output before optimizing.
- **DR17** least-slack-first priority (τ).
- **PW1** copper roles from waveforms.
- **LA1** half-port promotion: every net gets a named return.
- **LA12** band netlists for loop discovery.

**4. Replace slogans with budgets**
- **RG2** regime predicates as dimensionless groups.
- **RG11** return-transition budget in pH.
- **FE1** return-path EMF ledger.
- **PW25** height × squares instead of loop area (same as **OP22**).
- **FE26** cavity-eigenvalue critic.

**5. Optimize jointly with physics**
- **JPR1** band-tension ("rope and pulley") placement forces.
- **JPR14** channel-width constraint-graph legalizer.
- **JPR41** delayed-acceptance joint SA.
- **FE11** EMI margin as a placement loss.
- **OP38** adjoint copper advisor.
- **JPR34** constraint price tags for mechanical constraints (with **JPR33**, board size as a priced variable).

Runners-up worth a day each: PW2 width optimum, PW41 shunt inductive error, PW46 shield-class selector for copper under coils, XD2 slot cost from the stream function, XD22 via rows sized by transfer length, XD39 width exponent chosen by objective, XD47 reverse-return feeding, XD113 decap reach from a screening length, TM20+TM22 HV inception critic and corner fillets, TM30 critical-area yield cost, TM39 tombstoning pad check, LA7 current exclusion zones, OP29 power trees with width ∝ current, FE40 pad-void synthesis, JPR46 joint-vs-portfolio protocol.

## Same idea, several names

Merge these when building; the ids stay valid as aliases.

| Concept | Ids |
|---|---|
| Loop inductance from length × height / width, not area | PW25, OP22, SIM15, OP21 |
| One PEEC core | SIM46, SIM16, OP21 |
| One screened-Laplace sheet solver (IR drop, pour L, heat, decap reach) | OP1, XD113, TM2, OP23, XD112 |
| Real physics kernels in an ePlace-style placer | XD112, OP24, OP23 |
| Keep-away halos solved from coupling curves | RG53, LA25, XD68 |
| Sense ports / Kelvin generalized | LA8, XD72, PW41 |
| Commutation cells as the placement unit | XD12, LA9 |
| Return-path metric per net | FE1, PC6, RG11 |
| Rules as priors and move generators | RG41, RG42, JPR (move sets) |
| Constraint and budget prices | JPR34, OP38 (adjoint shadow prices), DR9, I4 |

## How these relate to the original catalog

- **I1/I2 budget ledger and dimensioned types:** made concrete by the basis set (RG), the vocabulary (LA) and budgets from sensitivity (DR9).
- **N7 hot-loop nH placer:** should use MS2 or height × squares rather than area (PW25, SIM15).
- **N8 decap assignment:** should optimize cluster geometry and orientation, not count (PW, [pdn-and-commutation](../../topics/physics/pdn-and-commutation.md)).
- **R2 shadow return nets:** generalized by the return-path EMF ledger (FE1).
- **P1, P7 and S1 (router probes, live topological sketch, corridor contract):** subsumed by the joint state (JPR).
- **V1/V2 gates:** instantiated by the mutation benchmark (PC29/PC30).
