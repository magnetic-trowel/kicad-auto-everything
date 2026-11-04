# Solver ladder: multi-fidelity physics for placement, routing and sign-off

Scope: the fidelity rungs F0–F4 + S, the evaluator contract, trust radii, value-of-information escalation, calibration, caching and compute allocation. Not here: engine inventory and licences -> [open-solvers](open-solvers.md); exactness classes -> [physics-core-v2](physics-core-v2.md); independent checks -> [verification-and-limits](verification-and-limits.md).
Keys: solver ladder, F0, F1, F2, F3, F4, S surrogate, T0–T3, C0–C3, evaluator contract, trust radius, V4, validity domain, σ, split-conformal, value of information, escalation, MS2, PEECN, plan-view area, pick-best-of-10, Woodbury, polarization tensor, adjoint price map, dirty region, label factory, regime selection

Tags as in [open-solvers](open-solvers.md). [C] from [sl_loop_peec.py](../../../tools/research/physics/sl_loop_peec.py) and [sl_tier_costs.py](../../../tools/research/physics/sl_tier_costs.py) unless named.

## The rungs

| Rung | Physics | Examples | Cost per evaluation | Accuracy (where known) | Place in the loop |
|---|---|---|---|---|---|
| F0 | geometry and topology | return coverage, path length, loop polygon, clearances | µs–ms | exact geometry, no physics | every move |
| F1 | closed forms | Hammerstad-Jensen, L′(w,h)·length, MS2, cavity model, Johnson K, fin and thermal kernels | 0.05–2.5 µs; cavity 2–300 ms per sweep [C] | 0.2–15% inside validity; wrong outside (IPC-2141 −65% at w/h 6) [C] | placer and router inner loops; ledger spend models |
| S | learned residual or operator | residual-on-MS2, CNN/GNN capacitance, PDN DNN | µs–ms batched | ours: median 3.5%, p95 9.8%, max 114% [C] | inner loop where F1 lacks a formula |
| F2 | quasi-static field solve on real copper | image PEEC, multi-filament PEEC, 2-D FD cross-sections, 2.5-D FV IR/thermal, plane-pair modes, meshed-plane PEEC | PEEC 0.1–1.7 ms; 2-D FD 0.02–12 s; IR 0.1–9 s; meshed plane 7–115 s [C] | image PEEC within 1.3% of FastHenry (100 MHz, 4 loops, w/h 0.3–5); filament-count caveat in [verification-and-limits](verification-and-limits.md#1-claims-verified-by-an-independent-method) [C, rt_loop_proxy] | accepted placements, route batches, post-route critics |
| F3 | full-wave/FEM on slices | openEMS via gerber2ems/si-wrapper, Palace, EMerge, CalculiX/Elmer thermal | min–h on CPU, ~10× less on GPU [I] | VNA-matched "in character and order of magnitude" (Antmicro) [P] | finalists, sign-off, calibration of F1/F2 |
| F4 | measurement and vendor data | coupons (VNA/TDR), thermal camera, near-field scan, EMC pre-scan, vendor S-parameters, EVMs | days per panel; free per part | ground truth within measurement error | bias models per stackup, fab, part family |

FastHenry, the F2 loop reference, is internal calibration only (licence: [open-solvers](open-solvers.md#licence-verdicts)); shipped quasi-static engines are our PEEC, PyPEEC, FasterCap.

### Name mapping

| This ladder | Brief | [Critics](physics-critics-catalog.md) | [Evaluation stack](../verification/evaluation-stack.md) | [Design reasoning](design-reasoning-architecture.md) |
|---|---|---|---|---|
| F0 | — | F0 | T0 (geometry part) | — |
| F1 | T0 | F1 | T0 (Transcalc, IPC) | T0 |
| F2 | T1 | F2 | T2 (padne, KiPI) | — |
| F3 | T2 | F3 | T3 | T3 |
| F4 | T3 | — | — | — |

- F0–F4 + S is proposed canonical; design-reasoning's "T2 SPICE" is the circuit axis C2.
- Exactness classes ([physics-core-v2](physics-core-v2.md) §2) grade guarantees relative to a stated model: E0 topological, E1 algebraic (exact on the discretized model), E2 certified bound, E3 asymptotic, E4 calibrated, E5 conjectured. A result carries both, e.g. (F2, E1); "exact" never covers the model's own error.
- DRC and router probes (evaluation-stack T1) check legality, not physics: separate axis.
- Circuit axis: **C0** budget arithmetic (L·di/dt, I·R, K·V); **C1** linear lumped models (Z(f), LC ring; [dr_switch_cell_budget.py](../../../tools/research/physics/dr_switch_cell_budget.py)); **C2** SPICE transient with vendor models and back-annotated RLGC/K ([schematic-to-physics](schematic-to-physics.md)); **C3** channel statistics (PyBERT/IBIS-AMI). A verdict names a pair, e.g. "hot-loop overshoot at (F2, C1)".

## Cost per sub-problem

F3 rows are [I] estimates: cells from region size and mesh; Δt = Δmin/(c√3); openEMS at 294 Mcell/s (gerber2ems log [P]); GPU at 3 Gcell/s (gprMax 3.4 Gcell/s on Pascal [S]).

| Sub-problem | F1 | F2 (CPU) | F3 CPU / GPU | Comment |
|---|---|---|---|---|
| 5-part hot loop, 10–20 mm | MS2 ~µs vectorized [I]; batched PEEC1 0.3–0.8 µs [C] | image PEEC 0.1–1.7 ms; FastHenry meshed plane 7–115 s [C] | 6.4M cells at 25 µm, 2×10⁵ steps for 10 ns: ~75 min / ~7 min | quasi-static (10 mm ≪ λ/10 at 1 GHz); F3 adds little beyond package and via 3-D effects. Never FDTD here: ~75 CPU-min vs ~1 ms PEEC [C/I] |
| Decap and vias (mounting L) | µs, but via constant matters (Johnson vs Rosa 2–6×) [C] | PEEC with via barrels and plane images: ms; meshed planes: s–min [I] | 7.2M cells, 5 ns: ~50 min / ~5 min | calibrate against vendor S-parameters + coupon (F4) |
| DDR byte lane (11 nets, 30 mm) | Z0, delay, K per segment: µs | 2-D FD per unique cross-section 0.2–1.5 s (Hammerstad-Jensen in µs for plain microstrip), then MTL in SPICE [C/I] | 3.8M cells, 22 ports: ~6 h / ~37 min | cross-sections + cascade suffice; F3 only for breakouts and vias |
| USB3 connector transition | line Z0 only | pad and antipad C: ms–s [I] | 7.7M cells, 4 ports: ~70 min / ~7 min; gerber2ems sample ~34 s per port at ~1M cells [P] | truly 3-D: F3 is the first trustworthy rung |
| Whole-board PDN | cavity model 2–300 ms per sweep (rectangles) [C] | DC IR 0.1–9 s for 27k–436k cells [C]; plane BEM > 10 s [S] | full-wave ~17 min implied by the PDN-DNN paper (10⁴ × 0.1 s) [S] | 0.1 s surrogate exists [S] |
| Whole-board thermal | superposition kernel µs per pair ([thermal-physics](thermal-physics.md)) | FV ~1 s at 0.5 mm, 2 layers | FEM with convection: min–h; CFD: hours [I] | Antmicro FreeCAD/CalculiX flow validated at 2.5/8 W [P] |

## Measured trust radii for loop inductance [C]

Reference: multi-filament image PEEC (PEECN). Test set: 600 random rectangle, hairpin and L loops, w 0.15–4 mm, h 0.08–1.6 mm, sides 1.5–25 mm, ideal plane, plus fixed-stackup families.

| Proxy | Over a plane | Free space | Pick-best-of-10 | Valid where |
|---|---|---|---|---|
| Plan-view area (rule of thumb) | Spearman 0.36 across mixed w/h; 0.88–0.97 at fixed w, h | 0.79 | 66% fixed stackup (regret p95 77%); 16% mixed (median regret 169%) | no plane, or fixed w and h |
| µ0·h·l/w (parallel plate) | biased +50…+1000%; ranks well only for w/h ≥ 3 (Spearman 0.99, still +65% median bias) | wrong | — | ranking only, w/h ≥ 3 |
| MS = Σ l·L′(w,h) | Spearman 0.99; median +13%; +30% for hairpins with s < 4h | wrong (−45%) | 95–96% | over a plane, sides ≥ 4h apart |
| MS2 = MS + coupled-line mutual | Spearman 0.999; median +7.7% vs a graded reference (+9…+14% vs PEECN, partly PEECN's own error); p90 ≤ +31% | wrong | 96–98%, regret p95 0% | over an ideal plane |
| PEEC1 (one filament) | 3–5% for w/h < 1; fails for w/h ≥ 3 | 3–4% | 67% mixed | w/h < 1 |
| Trace length (fixed stackup) | — | — | 82–99% (MS2 97–100% on the same sets) [C, [rt_loop_proxy](../../../tools/research/physics/rt_loop_proxy.py)] | fixed stackup |

Mechanism: over a solid plane at depth h ≪ loop size, the plane carries an image current under each conductor (eddy if floating, return if it is the return), confining the field to the dielectric under the copper. L ∝ path length × L′(w,h) + mutuals between sides closer than a few h. Plan-view area is right only without a plane, or when the return cannot follow. Hence "minimize hot-loop area" ([hot-loops](../rules/power/hot-loops.md), [checkers-power](../rules/checkers-power.md) `loop_area` with `max_mm2`) is a weak objective over a plane (mixed-stackup Spearman 0.36): score nH by MS2 or PEEC; area stays valid for planeless boards.

## 1. One evaluator contract

Every evaluator returns value, σ, validity, provenance and cost; an optimizer may exploit a value only inside the evaluator's trust region ([V4](../../ideas/original/verification.md)); outside it the evaluator escalates.

```
evaluate(quantity, objects, band, rung="auto", budget_s=None) ->
  {value, sigma, unit, rung, validity: "in"|"edge"|"out", features, provenance, cost_s, cache_key}
```

Each evaluator registers: a validity domain (formula's stated range ∩ hull of its calibration set, in dimensionless features w/h, s/h, l/λ, f·t_r); a residual model giving σ per region; a cost model; a canonical input hash. The ledger ([I1](../../ideas/original/intent-and-why.md), [physics-ir](physics-ir.md)) stores the rung with every spent number [I].

## 2. Where each rung sits

| Loop | Calls | Rungs |
|---|---|---|
| Placer inner loop | 10⁵–10⁷ | F0 + F1 + S, vectorized and differentiable (JAX) |
| Router edge costs | precomputed per layer and width | F1 spend per mm (dB, nH, mV), re-priced per net by F2 after routing |
| Outer loop (accepted placement, route batch) | 10²–10⁴ | F2 on dirty regions |
| Post-route critics | per budget | F2 on everything budgeted; F3 queue for the riskiest |
| Sign-off | per budget with thin margin | F3 slices where margin < z·σ_F2; F4 anchors |
| Offline | 10³–10⁶ labels | F2/F3 label factories, calibration fits |

## 3. Trust radius, made concrete (V4)

- σ: split-conformal residual quantiles per feature region (from the calibration sweep), not one global σ [I].
- Re-calibrate on what the optimizer visits: optimizers drift to proxy error regions, so each generation sends the top-k proxy winners to F2; if the F2/F1 ratio drifts, shrink the region (Goodhart audit) [I].
- Out of domain: escalate, or mark "unverified" in the ledger; never reward an out-of-domain value [I].
- Residual surrogates over black boxes: same features, 300 labels, residual on MS2 is 8× more accurate at the median [C]; its 114% outlier is why an out-of-domain check is still needed.

## 4. Value-of-information escalation

Escalate object o from rung k to k+1 when expected loss avoided exceeds the call's cost; escalate on VOI, not on schedule. Triggers [I]:
1. **Budget margin:** |budget − v_k| < z·σ_k; z from the [criticality field](../../ideas/original/intent-and-why.md): ~1 cosmetic, 3 safety.
2. **Ranking:** only candidates whose intervals overlap the leader's, and only if the choice changes something downstream.
3. **Sensitivity:** never when |∂objective/∂v|·σ_k is below tolerance.

Hot-loop data [C]: MS2 errs on 2–4% of choices; a miss costs median 1.2% (max 7%) at fixed stackup, median 5.2% (max 48%) with mixed widths and layers, so escalation is rarely needed, mostly when candidates differ in width or layer. Plan-view area misses 34–84% of choices at median cost 36–226%: it would need escalation almost always.

## 5. Calibration against F4

- Three measurement layers ([validation-program](validation-program.md)): common-factor structures on every board (stackup TDR, pre-scan with real cables, IR image) fixing per-class bias once; a pre-registered bring-up of the first board with predictions logged before fabrication; the value-ranked coupon panel of [validation-coupons](validation-coupons.md), only where models disagree and decisions flip. Measure with VNA/TDR, thermal camera, near-field probe; store bias per (stackup, fab) with provenance [I].
- Vendor data: capacitor and inductor S-parameters, de-embedded from the vendor fixture to our mounting [I].
- External anchors: published measurements (Antmicro VNA slices, EVM data) for F3 [P].

## 6. Caching and incremental re-extraction

- **Memoize per object** on a canonical geometry hash (translation- and rotation-normalized), stackup id and band: segment self-L, pad-and-via mounting L, cross-section RLGC, transition S-parameters [I].
- **Interaction cutoff:** over a plane, mutual between distant parallel segments falls as (2h/D)², so a ~10h cutoff loses little; FMM/FFT/H-matrix only for free-space or whole-board problems ([XD30](../../ideas/physics-first/cross-domain.md)) [I].
- **Dirty regions from IPC commits:** changed items invalidate interactions within the cutoff; only budgets touching them are recomputed [I].
- **Linear solves:** 2-D: refactor (0.6–1.5 s at 10⁵ cells). Stale-LU-preconditioned CG converged in 22–30 iterations but was slower in scipy: 3.9–6.3 s vs 0.65–1.2 s at 1.1×10⁵ cells; at 4.4×10⁵ break-even to 2× slower (10–14 s vs 5–16 s) [C]. 3-D (F3): warm starts and Schur-complement window macro-models [I].
- **Adjoint price maps:** one solve gives ∂loss/∂copper everywhere, but the plain area-weighted map is right only for compact holes: within ~15% there (0.012 vs 0.014 mW; 0.268 vs 0.303 mW); a 6 mm slot across the current priced 30× low (0.27 vs 8.06 mW) [C]. Multiply forward and adjoint fields by the edit's polarization tensor (Δψ crack law for cuts: a slit across the flow costs (π/4)R_s·Δψ_u·Δψ_λ; [lens-ct](lens-ct.md), [lens-sy](lens-sy.md), [xd_sheet.py](../../../tools/research/physics/xd_sheet.py)).
- **Finite edits:** exact Woodbury (removal) and Thevenin (addition) quotes ([lens-cd](lens-cd.md)), each with radius r = max|λ| over the edit spectrum; exact change = Σ c_i/(1 − λ_i), c_i summing to the first-order price, so r says whether first order was safe ([physics-core-v2](physics-core-v2.md) §4).
- **Reuse F3 across boards** via a library of canonical structures (via launches, connector transitions, decap mounts) stored as parameterized surrogates [I].

## 7. Spending "near-infinite" compute

- Batch candidates, not meshes: vectorized PEEC1 does 20,000 loops at 0.3–0.8 µs each on one core [C]; GPU vmap of F1/S 10⁶–10⁸ evaluations/s [I]; feed population optimizers (CMA-ES, QD, beam; [optimization](physics-in-the-loop-optimization.md)).
- F2 re-ranks elites each generation: at ~1 ms per PEEC call, 100 elites = 0.1 s [C].
- Label factories: F2 PEEC at ~1 ms → ~3.6 million labels per core-hour [C]; F3 labels cost minutes: spend by active learning where surrogate σ is high and a decision boundary is close [I].
- GPU for F3: gprMax GPU up to 30× its OpenMP CPU solver [S]; pack many small slices per GPU [I].
- Avoid: FDTD on quasi-static problems; whole-board full-wave; fine 2-D meshes where Hammerstad-Jensen suffices (1–2.5 µs vs 5–12 s for the same ~1%) [C].

## 8. Regime selection: which solver class

- **Electrical size:** largest dimension < λ/10 at f_max and no radiation question → quasi-static (PEEC, FV); else full-wave slice [I].
- **Current distribution:** ωL ≫ R → inductive (image) distribution; R ≫ ωL → resistive. Crossover for a trace over a 35 µm plane ~0.1–1 MHz ([vo_return_spread.py](../../../tools/research/physics/vo_return_spread.py)); skin depth vs thickness sets the R(f) model.
- **Thermal:** steady-state FV unless pulses < ~1 s ([thermal-physics](thermal-physics.md)).

## Open questions

- F3 runtimes are estimates: time a gerber2ems slice of a DDR lane and a USB3 launch on this harness, CPU and GPU.
- σ from few F4 points: per-stackup bias may not transfer across fabs; verify coupon-to-board transfer.
- Ideal-plane PEEC ignores plane voids (need meshed-plane PEEC; [pc_refplane.py](../../../tools/research/physics/pc_refplane.py) flags them first) and the low-frequency return spread.

## Sources

- Research notes: [constraints_verification_benchmarks.md § Q2](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/constraints_verification_benchmarks.md); [solver_toolbox.md § 8](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/solver_toolbox.md).
- [gerber2ems README](https://github.com/antmicro/gerber2ems) (timestep log); [Antmicro 2025 SI flow](https://antmicro.com/blog/2025/07/recent-improvements-to-antmicros-signal-integrity-simulation-flow); [gprMax GPU paper](https://repository.uwl.ac.uk/id/eprint/5755/); [PDN DNN](https://arxiv.org/abs/2106.10693); [openEMS CHANGELOG](https://github.com/thliebig/openEMS/blob/master/CHANGELOG.md).
- Scripts: [sl_loop_peec.py](../../../tools/research/physics/sl_loop_peec.py) (proxies, trust radii, decision quality, surrogate, FastHenry decks); [sl_tier_costs.py](../../../tools/research/physics/sl_tier_costs.py) (Z0, vias, cavity, IR, FDTD throughput, vector fitting).
- Related: [simulation ideas](../../ideas/physics-first/simulation.md), [physics-critics-validation](physics-critics-validation.md), [performance-and-multifidelity](../solvers/performance-and-multifidelity.md).
