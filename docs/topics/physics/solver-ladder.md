# Solver ladder: multi-fidelity physics for placement, routing and sign-off

**TL;DR**
- **Five rungs plus surrogates:**
  - F0 geometry;
  - F1 closed forms (µs);
  - F2 quasi-static solves on the board's own copper (ms–min);
  - F3 full-wave/FEM on sliced regions (min–h);
  - F4 measurement and vendor data;
  - S: learned residuals on F1, trained on F2/F3 labels.

  Names match the [critic catalog](physics-critics-catalog.md). The brief's T0–T3 are F1–F4.
- **Every evaluator returns value, σ, validity, provenance and cost.** An optimizer may exploit a value only inside the evaluator's trust region ([V4](../../ideas/original/verification.md)); outside it the evaluator escalates.
- **Escalate on value of information, not on schedule.** Call a higher rung only when its answer could flip a decision. Choosing the best of 10 hot-loop candidates, the µs proxy MS2 picks the PEEC-best 96–98% of the time; plan-view loop area picks it 66% (fixed stackup) or 16% (mixed widths and layers) [C]; at a fixed stackup plain trace length picks it 82–99% [C, [rt_loop_proxy](../../../tools/research/physics/rt_loop_proxy.py)].
- **Incremental work:**
  - Cache per-object physics by geometry and stackup hash, and re-extract only dirty neighbourhoods.
  - In 2-D, simply refactor (0.6–1.5 s at 10⁵ cells).
  - One adjoint solve gives the first-order price of every small edit once the edit's polarization tensor is applied: a slit across the flow costs (π/4)R_s·Δψ_u·Δψ_λ (lenses [CT](lens-ct.md), [SY](lens-sy.md)). The plain area-weighted adjoint missed a 6 mm slot 30× (0.27 vs 8.1 mW) [C].
  - Finite edits use exact Woodbury (removal) and Thevenin (addition) quotes ([lens CD](lens-cd.md)). Each comes with its radius r = max|λ| over the edit spectrum: exact change = Σ c_i/(1 − λ_i), the c_i summing to the first-order price, so r says whether first-order was safe ([physics-core-v2](physics-core-v2.md) §4).
- **Spend compute on batched F1/S over candidate populations, F2 label factories and GPU F3 for finalists.** Never use FDTD for an electrically small loop: ~75 CPU-minutes versus ~1 ms of PEEC for the same quasi-static answer [C/I].

## Key facts

Tags as in [open-solvers](open-solvers.md). [C] numbers come from [sl_loop_peec.py](../../../tools/research/physics/sl_loop_peec.py) and [sl_tier_costs.py](../../../tools/research/physics/sl_tier_costs.py).

### The rungs

| Rung | Physics | Examples | Cost per evaluation | Accuracy (where known) | Place in the loop |
|---|---|---|---|---|---|
| F0 | Geometry and topology | Return coverage, path length, loop polygon, clearances | µs–ms | Exact geometry, no physics | Every move |
| F1 | Closed forms | Hammerstad-Jensen, L′(w,h)·length, MS2, cavity model, Johnson K, fin and thermal kernels | 0.05–2.5 µs; cavity 2–300 ms per sweep [C] | 0.2–15% inside validity; wrong outside (IPC-2141 −65% at w/h 6) [C] | Placer and router inner loops; ledger spend models |
| S | Learned residual or operator | Residual-on-MS2, CNN/GNN capacitance, PDN DNN | µs–ms batched | Ours: median 3.5%, p95 9.8%, max 114% [C] | Inner loop where F1 lacks a formula |
| F2 | Quasi-static field solve on real copper | Image PEEC, multi-filament PEEC, 2-D FD cross-sections, 2.5-D FV IR/thermal, plane-pair modes, meshed-plane PEEC | PEEC 0.1–1.7 ms; 2-D FD 0.02–12 s; IR 0.1–9 s; meshed plane 7–115 s [C] | Image PEEC within 1.3% of FastHenry at 100 MHz on 4 loops with w/h 0.3–5. With 7 equal filaments it reads 11% (w/h 10–20) to 21% (w/h 20–60, p10 42%) low; use ≥ 31 cosine-graded filaments [C, rt_loop_proxy] | Accepted placements, route batches, post-route critics |
| F3 | Full-wave/FEM on slices | openEMS via gerber2ems/si-wrapper, Palace, EMerge, CalculiX/Elmer thermal | Minutes–hours on CPU, ~10× less on GPU [I] | VNA-matched "in character and order of magnitude" (Antmicro) [P] | Finalists, sign-off, calibration of F1/F2 |
| F4 | Measurement and vendor data | Coupons (VNA/TDR), thermal camera, near-field scan, EMC pre-scan, vendor S-parameters, EVMs | Days per panel; free per part | Ground truth within measurement error | Bias models per stackup, fab and part family |

### Name mapping

| This ladder | Brief | [Critics](physics-critics-catalog.md) | [Evaluation stack](../verification/evaluation-stack.md) | [Design reasoning](design-reasoning-architecture.md) |
|---|---|---|---|---|
| F0 | — | F0 | T0 (geometry part) | — |
| F1 | T0 | F1 | T0 (Transcalc, IPC) | T0 |
| F2 | T1 | F2 | T2 (padne, KiPI) | — |
| F3 | T2 | F3 | T3 | T3 |
| F4 | T3 | — | — | — |

The rungs grade accuracy. [physics-core-v2](physics-core-v2.md) §2 adds exactness classes that grade guarantees relative to a stated model: E0 topological, E1 algebraic (exact on the discretized model), E2 certified bound, E3 asymptotic, E4 calibrated, E5 conjectured. A result carries both, e.g. (F2, E1); "exact" never covers the model's own error.

DRC and router probes (evaluation-stack T1) check legality, not physics, so they sit on a separate axis. Circuit simulation is a second axis too:
- **C0:** budget arithmetic (L·di/dt, I·R, K·V).
- **C1:** linear lumped models (Z(f), LC ring; [dr_switch_cell_budget.py](../../../tools/research/physics/dr_switch_cell_budget.py)).
- **C2:** SPICE transient with vendor models and back-annotated RLGC/K ([schematic-to-physics](schematic-to-physics.md); design-reasoning's "T2").
- **C3:** channel statistics (PyBERT/IBIS-AMI).

A verdict therefore names a pair, e.g. "hot-loop overshoot at (F2, C1)".

### Cost per sub-problem

F3 rows are [I] estimates. Cells come from the region size and mesh. Δt = Δmin/(c√3); openEMS speed is the 294 Mcell/s of the gerber2ems log [P]; the GPU figure assumes 3 Gcell/s (gprMax reported 3.4 Gcell/s on Pascal [S]).

| Sub-problem | F1 | F2 (CPU) | F3 CPU / GPU | Comment |
|---|---|---|---|---|
| 5-part hot loop, 10–20 mm | MS2 ~µs vectorized [I]; batched PEEC1 0.3–0.8 µs [C] | Image PEEC 0.1–1.7 ms; FastHenry meshed plane 7–115 s [C] | 6.4M cells at 25 µm, 2×10⁵ steps for 10 ns: ~75 min / ~7 min | Quasi-static (10 mm ≪ λ/10 at 1 GHz). F3 adds little beyond package and via 3-D effects |
| Decap and its vias (mounting L) | µs, but the via constant matters (Johnson vs Rosa: 2–6×) [C] | PEEC with via barrels and plane images: ms; meshed planes: s–min [I] | 7.2M cells, 5 ns: ~50 min / ~5 min | Calibrate against vendor S-parameters plus a coupon (F4) |
| DDR byte lane (11 nets, 30 mm) | Z0, delay, K per segment: µs | 2-D FD per unique cross-section 0.2–1.5 s (Hammerstad-Jensen in µs for plain microstrip), then MTL in SPICE [C/I] | 3.8M cells, 22 ports: ~6 h / ~37 min | Cross-sections and a cascade suffice for lines; use F3 only for breakouts and vias |
| USB3 connector transition | Line Z0 only | Pad and antipad C: ms–s [I] | 7.7M cells, 4 ports: ~70 min / ~7 min. gerber2ems sample: ~34 s per port at ~1M cells [P] | A truly 3-D discontinuity: F3 is the first trustworthy rung |
| Whole-board PDN | Cavity model 2–300 ms per sweep (rectangles) [C] | DC IR 0.1–9 s for 27k–436k cells [C]; plane BEM > 10 s [S] | Full-wave ~17 min implied by the PDN-DNN paper (10⁴ × 0.1 s) [S] | Surrogate at 0.1 s exists in the literature [S] |
| Whole-board thermal | Superposition kernel µs per pair ([thermal-physics](thermal-physics.md)) | FV ~1 s at 0.5 mm, 2 layers ([thermal-physics](thermal-physics.md)) | FEM with convection: minutes–hours; CFD: hours [I] | Antmicro FreeCAD/CalculiX flow validated at 2.5/8 W [P] |

### Measured trust radii for loop inductance [C]

Reference: multi-filament image PEEC (PEECN), itself within 1.3% of FastHenry on 4 cases (w/h 0.3–5 only; with 7 equal filaments it reads low on wide traces, see F2 above). The test set is 600 random rectangle, hairpin and L loops: w 0.15–4 mm, h 0.08–1.6 mm, sides 1.5–25 mm, over an ideal plane, plus fixed-stackup families.

| Proxy | Over a plane | Free space | Pick-best-of-10 | Valid where |
|---|---|---|---|---|
| Plan-view area (the rule of thumb) | Spearman 0.36 across mixed w/h; 0.88–0.97 at fixed w and h | 0.79 | 66% at fixed stackup (regret p95 77%); 16% mixed (median regret 169%) | No plane, or fixed w and h |
| µ0·h·l/w (parallel plate) | Biased +50…+1000%; ranks well only for w/h ≥ 3 (Spearman 0.99, still +65% median bias) | Wrong | — | Ranking only, w/h ≥ 3 |
| MS = Σ l·L′(w,h) | Spearman 0.99; median +13%; +30% for hairpins with s < 4h | Wrong (−45%) | 95–96% | Over a plane, sides ≥ 4h apart |
| MS2 = MS + coupled-line mutual | Spearman 0.999; median +7.7% against a graded reference (+9…+14% against PEECN, part of which is PEECN's own error); p90 ≤ +31% | Wrong | 96–98%, regret p95 0% | Over an ideal plane |
| PEEC1 (one filament) | 3–5% for w/h < 1; fails for w/h ≥ 3 | 3–4% | 67% mixed | w/h < 1 |

The physics behind the table:
- Over a solid plane at depth h, much smaller than the loop, the plane carries an image current directly under each conductor (eddy current if the plane floats, return current if it is the return), so the field is confined to the dielectric under the copper.
- L then scales with path length × L′(w,h), plus mutual terms between sides closer than a few h.
- Plan-view area is the right variable only with no plane, or when the return cannot follow.

## Recommendations for our system

### 1. One evaluator contract

```
evaluate(quantity, objects, band, rung="auto", budget_s=None) ->
  {value, sigma, unit, rung, validity: "in"|"edge"|"out", features, provenance, cost_s, cache_key}
```

Each evaluator registers four things:
- a validity domain (the formula's stated range ∩ the hull of its calibration set, in dimensionless features w/h, s/h, l/λ, f·t_r);
- a residual model giving σ per region;
- a cost model;
- a canonical input hash.

The ledger ([I1](../../ideas/original/intent-and-why.md), [physics-ir](physics-ir.md)) stores the rung with every spent number [I].

### 2. Where each rung sits

| Loop | Calls | Rungs |
|---|---|---|
| Placer inner loop | 10⁵–10⁷ | F0 + F1 + S, vectorized and differentiable (JAX) |
| Router edge costs | Precomputed per layer and width | F1 spend per mm (dB, nH, mV), re-priced per net by F2 after routing |
| Outer loop (accepted placement, route batch) | 10²–10⁴ | F2 on dirty regions |
| Post-route critics | Per budget | F2 on everything budgeted; F3 queue for the riskiest |
| Sign-off | Per budget with thin margin | F3 slices where the margin is < z·σ_F2; F4 anchors |
| Offline | 10³–10⁶ labels | F2/F3 label factories, calibration fits |

### 3. Trust radius, made concrete (V4)

- **σ:** split-conformal residual quantiles per feature region, not one global σ. Regions come from the calibration sweep [I].
- **Re-calibrate on what the optimizer visits.** Optimizers drift to the proxy's error regions, so each generation sends the top-k proxy winners to F2. If the F2/F1 ratio drifts, shrink the region (Goodhart audit) [I].
- **Out of domain:** escalate, or mark "unverified" in the ledger. Never reward an out-of-domain value [I].
- **Residual surrogates over black boxes:** with the same features and 300 labels, the residual on MS2 is 8× more accurate at the median [C]. Its 114% outlier shows why an out-of-domain check is still needed.

### 4. Value-of-information escalation

Escalate object o from rung k to k+1 when the expected loss avoided exceeds the cost of the call. In practice there are three triggers [I]:
1. **Budget margin.** Escalate if |budget − v_k| < z·σ_k. z comes from the [criticality field](../../ideas/original/intent-and-why.md): about 1 for cosmetic items, 3 for safety items.
2. **Ranking.** Escalate only candidates whose intervals overlap the leader's, and only when the choice changes something downstream.
3. **Sensitivity.** Never escalate when |∂objective/∂v|·σ_k is below tolerance.

The hot-loop data supports this. MS2 errs on 2–4% of choices. At fixed stackup a miss costs a median 1.2% (max 7%); with mixed widths and layers, a median 5.2% (max 48%). So escalation is rarely needed, and mostly when candidates differ in width or layer. Plan-view area misses 34–84% of choices at a median cost of 36–226%, so it would need escalation almost always [C].

### 5. Calibration against F4

- **Coupon panel per stackup and fab:**
  - hot loops of known geometry;
  - decap mounts;
  - via transitions;
  - slots across references;
  - thermal pads.
  
  Measure with VNA/TDR, thermal camera and near-field probe. Store the bias per (stackup, fab) with provenance [I].
- **Vendor data:** capacitor and inductor S-parameters, de-embedded from the vendor fixture to our mounting [I].
- **External anchors:** published measurements (Antmicro VNA slices, EVM data) as anchors for F3 [P].

### 6. Caching and incremental re-extraction

- **Memoize per object.** Key on a canonical geometry hash (translation- and rotation-normalized), stackup id and band. Objects include segment self-L, pad-and-via mounting L, cross-section RLGC and transition S-parameters [I].
- **Interaction lists with a cutoff.** Over a plane, the mutual between distant parallel segments falls as (2h/D)², so a ~10h cutoff loses little. Use FMM/FFT/H-matrix compression only for free-space or whole-board problems ([XD30](../../ideas/physics-first/cross-domain.md)) [I].
- **Dirty-region tracking from IPC commits.** Changed items invalidate interactions within the cutoff. Only budgets that touch them are recomputed [I].
- **Linear solves:**
  - 2-D: refactor. Stale-LU-preconditioned CG converged in 22–30 iterations but was slower in scipy: 3.9–6.3 s vs 0.65–1.2 s at 1.1×10⁵ cells; at 4.4×10⁵ it ranged from break-even to 2× slower (10–14 s vs 5–16 s) [C].
  - 3-D (F3): use warm starts and Schur-complement window macro-models [I].
- **Adjoint price maps.** One solve gives ∂loss/∂copper everywhere, but the plain area-weighted map is only right for compact holes.
  - Compact holes: within ~15% (0.012 vs 0.014 mW; 0.268 vs 0.303 mW).
  - A slot across the current: 30× low (0.27 vs 8.06 mW) [C].
  
  Multiply forward and adjoint fields by the edit's polarization tensor (the Δψ crack law for cuts, [xd_sheet.py](../../../tools/research/physics/xd_sheet.py)); quote finite edits exactly by Woodbury and check r.
- **Reuse F3 across boards** through a library of canonical structures (via launches, connector transitions, decap mounts), stored as parameterized surrogates [I].

### 7. Spending "near-infinite" compute

- **Batch candidates, not meshes.**
  - Vectorized PEEC1 evaluates 20,000 loops at 0.3–0.8 µs each on one core [C].
  - A GPU vmap of F1/S reaches 10⁶–10⁸ evaluations per second [I].
  - Feed population optimizers (CMA-ES, quality-diversity, beam search; [optimization](physics-in-the-loop-optimization.md)).
- **F2 re-ranks elites each generation.** At ~1 ms per PEEC call, 100 elites cost 0.1 s [C].
- **Label factories.** F2 PEEC at ~1 ms gives ~3.6 million labels per core-hour, so loop and coupling surrogates are never data-starved [C]. F3 labels cost minutes each: spend them by active learning, where the surrogate's σ is high and a decision boundary is close [I].
- **GPU for F3.** gprMax's GPU engine is up to 30× its OpenMP CPU solver [S]. Pack many small slices per GPU [I].
- **Avoid:**
  - FDTD on quasi-static problems;
  - whole-board full-wave;
  - fine 2-D meshes where Hammerstad-Jensen suffices (1–2.5 µs vs 5–12 s for the same ~1%) [C].

### 8. Regime selection: which solver class

- **Electrical size.** Largest dimension < λ/10 at f_max, and no radiation question: quasi-static (PEEC, FV). Otherwise use a full-wave slice [I].
- **Current distribution.** ωL ≫ R gives the inductive (image) distribution, R ≫ ωL the resistive one. The crossover for a trace over a 35 µm plane lies around 0.1–1 MHz ([vo_return_spread.py](../../../tools/research/physics/vo_return_spread.py)). Skin depth versus thickness sets the R(f) model.
- **Thermal.** Steady-state FV unless pulses are shorter than ~1 s ([thermal-physics](thermal-physics.md)).

## Conflicts and open questions

- **Round-3 corrections (2026-10-22):** adjoint pricing needs the edit's polarization tensor and Woodbury quotes with radius r; PEEC's FastHenry match is scoped to w/h 0.3–5; MS2 bias restated against a graded reference; exactness classes E0–E5 added ([red-team](red-team.md)).
- **Tier names.** Four schemes coexist (table above). We propose F0–F4 + S as canonical. design-reasoning's "T2 SPICE" is the circuit axis (C2).
- **"Minimize hot-loop area"** ([hot-loops](../rules/power/hot-loops.md), [checkers-power](../rules/checkers-power.md) `loop_area` with `max_mm2`) is a weak objective over a plane (mixed-stackup Spearman 0.36). Score nH with MS2 or PEEC. Area stays valid for planeless boards.
- **F3 runtimes are estimates.** Time a gerber2ems slice of a DDR lane and a USB3 launch on this harness, CPU and GPU.
- **σ from few F4 points.** Per-stackup bias may not transfer across fabs. Verify coupon-to-board transfer.
- **Licences.** FastHenry is a calibration-only tool ([open-solvers](open-solvers.md)), which conflicts with [physics-ir](physics-ir.md)'s "first solver target".
- **Ideal-plane PEEC** ignores plane voids, which need meshed-plane PEEC ([pc_refplane.py](../../../tools/research/physics/pc_refplane.py) flags them first), and the low-frequency return spread.

## Sources

- research notes: [constraints_verification_benchmarks.md § Q2](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/constraints_verification_benchmarks.md); [solver_toolbox.md § 8](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/solver_toolbox.md)
- [gerber2ems README](https://github.com/antmicro/gerber2ems) (timestep log); [Antmicro 2025 SI flow](https://antmicro.com/blog/2025/07/recent-improvements-to-antmicros-signal-integrity-simulation-flow); [gprMax GPU paper](https://repository.uwl.ac.uk/id/eprint/5755/); [PDN DNN](https://arxiv.org/abs/2106.10693); [openEMS CHANGELOG](https://github.com/thliebig/openEMS/blob/master/CHANGELOG.md)
- Scripts: [sl_loop_peec.py](../../../tools/research/physics/sl_loop_peec.py) (proxies, trust radii, decision quality, surrogate, FastHenry decks); [sl_tier_costs.py](../../../tools/research/physics/sl_tier_costs.py) (Z0, vias, cavity, IR, FDTD throughput, vector fitting)

See also: [open-solvers](open-solvers.md) · [simulation ideas](../../ideas/physics-first/simulation.md) · [physics-critics-validation](physics-critics-validation.md) · [design-reasoning-architecture](design-reasoning-architecture.md) · [performance-and-multifidelity](../solvers/performance-and-multifidelity.md) · [evaluation-stack](../verification/evaluation-stack.md)
