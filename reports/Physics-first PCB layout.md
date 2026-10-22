# Physics first: lay out the board the schematic leaves out

This report covers the physics-first pass over the project's layout research: eleven workstreams, about 30 topic docs, about 650 ideas and about 40 small solver scripts. It extends the [first report](LLM%20driven%20PCB%20placement%20and%20routing.md): the LLM still authors intent, never copper. What changes is the currency of that intent and what the solvers optimize. The philosophy is in [docs/topics/physics/README](../docs/topics/physics/README.md), the short version in the [digest](../docs/digests/physics-first.md) and the ideas in the [catalog](../docs/ideas/physics-first/README.md). Status: 2026-10-22.

**Evidence caveat.** Numbers tagged [C] come from our own quasi-static models (PEEC, 2-D Laplace, thermal finite volume, closed-form chains), checked against closed forms, published anchors or FastHenry, but not against measurement. Everything architectural is untested [I]. Topic docs carry the tags and conditions.

## 1. Bottom line

- **Autorouters produce boards that are DRC-correct and physically wrong because they optimize the wrong thing.** A layout is an unintended R, L, M and C network plus field structures, heat paths and a manufactured object. The goal is to make that realization invisible to the circuit and the outside world, within budgets in nH, mΩ, mV, ps, dB, K and V/mm ([physics/README](../docs/topics/physics/README.md)).
- **The physics is simpler than the rules.**
  - About 160 rules of thumb reduce to 12 quantities (L, M, Cm, R, Z, Bal, Vcm, Res, Ins, Th, Mech, Fab). The electrical ones come from four PEEC primitives.
  - 143 of 160 rules are replaceable by closed forms, 2-D solves, PEEC, a thermal network or SPICE.
  - Rules fail by regime, not direction ([rule-basis-set](../docs/topics/physics/rule-basis-set.md)).
- **The physics is also cheap.**
  - A numpy PEEC hot-loop solve takes ~1 ms and agrees with FastHenry within 1.3% [C].
  - One adjoint solve prices every copper edit [C].
  - A µs proxy (MS2) picks the best of 10 candidate loops 96–98% of the time, against 16–66% for "loop area" [C] ([solver-ladder](../docs/topics/physics/solver-ladder.md)).
- **Start from the circuit, not the net names.**
  - Simulate the schematic to get every net's dv/dt, di/dt and spectrum.
  - Get every susceptibility from one adjoint (`.noise`) solve.
  - Derive budgets from sensitivities, and order work by least slack ([schematic-to-physics](../docs/topics/physics/schematic-to-physics.md)).
- **Place, route and shape copper in one optimizer.**
  - The state carries topology (part poses, homotopy classes, layers, vias).
  - Physics is the shared objective.
  - Fixed parts (outline, holes, connectors, antenna, heatsink) are boundary conditions.
  - DRC stays a hard referee ([joint-place-route](../docs/topics/physics/joint-place-route.md)).
- **Measure physics separately.** A physics scorecard sits next to cp1/cpk and is never blended into them. A DRC-equivalent mutation benchmark gives it ground truth ([physics-critics](../docs/topics/physics/physics-critics.md)).

## 2. What the physics changes

| Slogan | Physics replacement | Key number | Doc |
|---|---|---|---|
| "Minimize hot-loop area" | Height × squares (Σ μ0·h·dl/w) or MS2 near a plane; area only without one | Equal-area loops differ 1.7×; plane depth moves L 0.93 → 4.1 nH [C] | [pdn-and-commutation](../docs/topics/physics/pdn-and-commutation.md) |
| "Pour the power nets" | Copper role from waveform; pours for DC feeds shaped by flow, widened at entries first; switch node limited by EMI | 31% of a pour's loss within 3 mm of the pads; topology-optimized shape −14.5% at equal area [C] | [power-copper](../docs/topics/physics/power-copper.md), [copper-shape-synthesis](../docs/topics/physics/copper-shape-synthesis.md) |
| "No 90° corners" | Regime-gated: SI below ~30 ps edges; pulsed current under ~1 ms; HV, ESD, RF, flex | 90° corner: 0.5% reflection at 100 ps; steady-current peak T within 0.5% [C] | [rf-geometry](../docs/topics/physics/rf-geometry.md) |
| "Return via within 200 mil", "no slots", "connectors on one edge"… | Return-path EMF ΔZ_ret(f)·I(f) charged to SI and EMI budgets | Slot ≈ 0.08–0.13 nH/mm; same-edge cables ~40 dB, slower edges ~3 dB [C] | [fields-si-emi](../docs/topics/physics/fields-si-emi.md), [fields-emi-budget](../docs/topics/physics/fields-emi-budget.md) |
| "3W" | Per-victim noise budget by layer type | At 3W: 1.3% NEXT in microstrip, 0.02% in stripline [C] | [fields-si-emi](../docs/topics/physics/fields-si-emi.md) |
| "Decaps as close as possible", "1 via per amp" | Screening length; cluster geometry and orientation; via fields conduct at their edges | 4 vias at 0.6 mm = 0.71× one via; decap reach 4–24 mm [C] | [pdn-and-commutation](../docs/topics/physics/pdn-and-commutation.md), [cross-domain-lessons](../docs/topics/physics/cross-domain-lessons.md) |
| "Keep hot parts apart" | Board as a fin with a spreading length; kernel + edge images | λ = 8 mm bare FR-4, 38–64 mm with copper; kernel within ~2% of a full solve [C] | [thermal-physics](../docs/topics/physics/thermal-physics.md) |
| "Round HV copper", altitude tables | Inception margin from the field; air density | E_max ∝ (g/r)^(1/3); IEC altitude factors = pressure ratio within ~1% [C] | [hv-and-manufacturing-physics](../docs/topics/physics/hv-and-manufacturing-physics.md) |
| "Keep high current away from sensitive lines" | Coupling with plane images; DC current exclusion for precision grounds | A plane 0.1 mm under both loops cuts coupling ~400× at 5 mm [C] | [worked-thought-experiments](../docs/topics/physics/worked-thought-experiments.md) |

## 3. The architecture

```
schematic + datasheets + fixed constraints
   → comprehension → simulate the schematic → decompose (ports, loops, nodes, couplings, heat)
   → budgets from sensitivities, τ ranking  (pcb-intent/0.3: intent.yaml)
   → joint place + route + copper-shape optimizer over the solver ladder (F1/S inner, F2 on accepted moves)
   → legalize (projection, Minkowski, CP-SAT) → kicad-cli DRC
   → physics critics (ledger.json, separate scorecard) → back-annotate, re-simulate, LII
   → LLM explains binding budgets and proposes repairs → human confirms
```

| Layer | What it is | Docs |
|---|---|---|
| Language | 12 atoms, 5 value types, signed operators; `pcb-intent/0.3` extends `0.2` additively | [vocabulary](../docs/topics/physics/vocabulary.md), [physics-ir](../docs/topics/physics/physics-ir.md), [examples](../docs/topics/physics/physics-ir-examples.md) |
| Reasoning | Net passports from simulation; adjoint susceptibility; √(cost × sensitivity) budget shares; least slack first | [design-reasoning-architecture](../docs/topics/physics/design-reasoning-architecture.md), [schematic-to-physics](../docs/topics/physics/schematic-to-physics.md) |
| Optimizer | Topology-carrying joint state on three timescales; physics spend models with gradients; topology-optimized copper with fab filters inside | [joint-place-route](../docs/topics/physics/joint-place-route.md), [physics-in-the-loop-optimization](../docs/topics/physics/physics-in-the-loop-optimization.md), [copper-shape-synthesis](../docs/topics/physics/copper-shape-synthesis.md) |
| Engines | F0 geometry → F1 closed forms → F2 PEEC/sheet/thermal → F3 full-wave slices → F4 measurement; S residual surrogates; escalate on value of information | [solver-ladder](../docs/topics/physics/solver-ladder.md), [open-solvers](../docs/topics/physics/open-solvers.md) |
| Judgement | ~40 physics critics, markers, a scorecard, a mutation benchmark | [physics-critics](../docs/topics/physics/physics-critics.md), [catalog](../docs/topics/physics/physics-critics-catalog.md), [validation](../docs/topics/physics/physics-critics-validation.md) |

**Joint placement and routing, proof of concept** ([experiment](../docs/topics/physics/joint-place-route-experiment.md)), on synthetic 2-layer boards with equal CPU [C]:
- **30 parts:** joint search beat a longer sequential run on 5/5 boards (median −17% routed objective) and a restart portfolio on 3/5. It did so through fewer vias (16 vs 24) and smaller hot loops, not shorter wire.
- **50 parts:** it won only 2/5. Routed moves cost ~25× an HPWL move, and restarts escape bad starting basins that local joint moves cannot.
- **Proxies:** HPWL tracks routed cost overall (Spearman 0.87–0.94), but 44% of pairs within 3% HPWL differed by more than 10% once routed.
- **Reading:** joint search is a refiner after a fast sequential start, with hard constraints kept hard inside the loop. It is not a cold start.

## 4. Roadmap: first experiments

All of these run beside the [benchmark harness](../bench/README.md) without changing its scoring (CLAUDE.md rules). Kill criteria are our proposals [I].

| # | Experiment | Baseline | Metric | Kill or exit criterion |
|---|---|---|---|---|
| 0 | Merge the PEEC and sheet-Laplace prototypes into one physics core (SIM46, OP1) | The three separate scripts | Same numbers within 1%; one API returning value, σ, validity, cost | None: prerequisite |
| 1 | Physics scorecard on the qualified suite: Freerouting outputs vs the human boards (PC6, PC9, PC44) | DRC only | How often routers create DRC-clean physics faults; per-critic false-alarm rate with roles | If router and human boards are indistinguishable, the critics are blind: fix them before anything trains on them |
| 2 | DRC-equivalent mutation benchmark with mutants written by a different author than the critics (PC29, PC30) | DRC; unvalidated checks | Detection vs false alarm, physics-labelled | Gate before any physics reward: ≥90% detection at ≤5% false alarm [I] |
| 3 | Proxy decision quality on 30 vendor EVM hot loops and decap fields (SIM7, SIM15, PW25) | Loop area; mm rules | Best-of-k agreement with F2 and one F3 slice per board | Replace N7's area term if MS2 or height × squares wins (expected) |
| 4 | Simulate the schematic on 10 reference designs (DR1, DR3, DR13) | Name-based net roles; expert criticality map | Agreement on aggressors and victims; budgets that bind | Keep name roles as default if passports disagree with experts without a physics reason |
| 5 | Copper synthesis on power rails of 10 boards (OP2, OP38, OP29) | Designer pours at equal area | Loss, worst IR drop, ΔT, DRC | Stop if under 5% gain where currents are ≥5 A |
| 6 | Joint vs sequential at board scale on placement-stripped qualified boards (JPR1, JPR14, JPR41, JPR46) | Equal-CPU sequential portfolio | Completion, vias, physics scorecard | Joint must beat the equal-CPU portfolio, not just a single sequential run |
| 7 | Layout invisibility index on 3 converter boards (DR, schematic-to-physics) | Rule-following layout | Predicted ripple and overshoot vs F3 or bench | Keep LII only as a ranking signal if predictions miss by more than 2× |

## 5. Risks and open questions

- **Calibration debt.** Most [C] numbers are model-vs-model. The F4 rung (EVM layouts, published measurements, bench) is empty, and the slot inductance and bridging-cap estimates disagree with Ott's measurements ([physics/README](../docs/topics/physics/README.md)).
- **Models.** Missing or encrypted SPICE models and switching nonlinearity limit "simulate the schematic". Fall back to envelopes with uncertainty ([schematic-to-physics](../docs/topics/physics/schematic-to-physics.md)).
- **Engines.** There is no maintained open multi-layer topological router, which the joint state needs. Board-scale joint search has only been tested on toys ([joint-place-route](../docs/topics/physics/joint-place-route.md)).
- **Licences.** FastHenry is internal-calibration only (MIT non-commercial notice). Ki-PIDA is AGPL. Ship our PEEC, PyPEEC (MPL-2.0), FasterCap (LGPL-2.1), openEMS (GPL-3) and Palace (Apache-2.0) ([open-solvers](../docs/topics/physics/open-solvers.md)).
- **Reward hacking.** Physics scores invite gaming (stitching islands, floating fills that fake coverage). The V1/V2 gate and connectivity-qualified reference (PC9) come first ([physics-critics-validation](../docs/topics/physics/physics-critics-validation.md)).
- **Challenges to existing docs** (hot-loop area tiers, via current sharing, decap distance, staged placement order, copper under inductors) are listed in [physics/README](../docs/topics/physics/README.md). The rule docs keep their evidence and now link to the physics replacement.
