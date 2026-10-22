# Physics-first ideas: simulation and the solver ladder (SIM)

These ideas make physics cheap enough to call inside optimizers and trustworthy enough to sign off with. Detail and evidence:
- [solver-ladder](../../topics/physics/solver-ladder.md): rungs F0–F4 + S, trust radius, escalation, caching, compute;
- [open-solvers](../../topics/physics/open-solvers.md): engines, licences, speed, KiCad paths.

Numbers tagged [C] come from [sl_loop_peec.py](../../../tools/research/physics/sl_loop_peec.py) and [sl_tier_costs.py](../../../tools/research/physics/sl_tier_costs.py). The ideas build on [V4 proxy trust radius](../original/verification.md), the [I1 ledger and I5 criticality field](../original/intent-and-why.md), [N7/N8 exact specialist placers](../original/priority-agents-and-negotiation.md) and the [physics IR](../../topics/physics/physics-ir.md).

Tags: *new* (not found in prior PCB work), *combo* (known parts, new combination for PCB), *sharp* (makes an existing rule or idea precise). Effort: S (days), M (weeks), L (months).

**Try first:**
1. SIM15 (MS2 spend model);
2. SIM16 (image PEEC as F2);
3. SIM7 + SIM10 (decision-quality calibration and VOI escalation);
4. SIM34 (residual surrogates);
5. SIM24 + SIM25 (adjoint and Δψ edit screening).

Each is cheap and already has a measured result behind it.

## A. Evaluator contract and infrastructure

**SIM1. Evaluator contract with σ, validity and cost.** — *combo, S.* Every physics call returns {value, σ, unit, rung, validity in/edge/out, provenance, cost, cache key}. Optimizers, critics and the ledger all consume this one record. A bare number cannot tell a downstream optimizer whether it may exploit it; this record can. Test: with V1-style mutants, an out-of-domain value must never raise a reward.

**SIM2. Validity domains as code.** — *sharp, S.* Each closed form ships its published range (w/h, εr, frequency, t/h, geometry class) and flags or refuses calls outside it. IPC-2141 drifts from +2% to −65% as w/h goes from 1 to 6 [C], and nothing in today's rule packs stops that use. Test: run a validity linter over every formula in the rule packs on 50 boards; count out-of-domain uses and their error against a 2-D solve.

**SIM3. Two-axis verdicts: field rung × circuit rung.** — *new, S.* Every verdict names a pair such as (F2, C1): PEEC inductance fed into a lumped LC ring model. Each budget declares the minimum pair it needs for sign-off; a USB3 channel might need (F3, C3). This stops a C0 estimate (L·di/dt) from passing as a SPICE-level verdict. Test: a sign-off audit fails whenever a budget's verdict sits below its declared pair.

**SIM4. Regime selector from dimensionless numbers.** — *new, S.* Compute l/λ, t/δ (skin depth), ωL/R and τ_thermal/t_pulse once per object and pick the solver class from them. A hot loop with l/λ < 0.03 at 1 GHz never goes to FDTD, which would take ~75 CPU-minutes against ~1 ms of PEEC [C/I]. Rules of thumb hide the regime; this makes it explicit. Test: on 100 objects, the selected class must agree with F3 within 10%.

**SIM5. Port synthesis from the physics IR.** — *combo, M.* The IR declares ports as terminal pairs. Deck writers for PEEC, FastHenry (internal use only), openEMS and Palace generate geometry and ports, and check that each port's reference terminal sits on the intended return conductor. Wrong port references are the classic silent field-solver error [I]. Test: auto-decks against hand-built decks on 10 structures, plus 10 seeded port mistakes.

**SIM6. Solver golden tests in CI.** — *sharp, S.* Fixed decks with known answers run on every commit:
- Hammerstad-Jensen inside its range;
- the four FastHenry rectangles (PEEC within 1.3%; 4 loops, w/h 0.3–5, 100 MHz);
- the cavity f₁₀;
- Ott's radiation formulas.

They catch unit, mesh and port regressions in our wrappers. Test: seed 10 plumbing bugs (mm vs m, εr on the wrong layer, a flipped port); CI must catch all of them.

**SIM46. One PEEC core for every tool.** — *sharp, S.* Three PEEC prototypes exist: image-plane loops ([sl_loop_peec.py](../../../tools/research/physics/sl_loop_peec.py)), nodal R + jωL with vias ([pw_peec.py](../../../tools/research/physics/pw_peec.py)) and a meshed plane ([fe_peec_plane.py](../../../tools/research/physics/fe_peec_plane.py)). They share the same Grover kernels. Merge them into one library behind SIM1, so critics, placers and the ledger cannot disagree through re-implementation. Test: the three scripts' published [C] numbers reproduce through the merged library within 1%.

## B. Trust, calibration and escalation

**SIM7. Calibrate on decision quality, not R².** — *new, S.* Score each proxy by how often it picks the true best from realistic candidate sets, and by the regret when it doesn't. For best-of-10 hot loops, plan-view area picks the PEEC-best 66% (fixed stackup) or 16% (mixed) of the time; MS2 picks it 96–98% [C]; at a fixed stackup, plain trace length picks it 82–99% and MS2 97–100% [C, rt_loop_proxy]. Correlation over random layouts overstates usefulness when an optimizer's choices are near-ties. Test: report both metrics for every registered proxy; check which one predicts final-design quality.

**SIM8. Conformal σ per feature region.** — *combo, S.* Split-conformal residual quantiles (F1 vs F2, F2 vs F3) give intervals with finite-sample coverage. They widen automatically where calibration data is sparse, unlike one global Gaussian σ. Test: empirical coverage within ±3% of nominal on held-out loop families and on optimizer outputs.

**SIM9. Goodhart audit every generation.** — *sharp, S.* Each generation, send the top-k proxy winners (not random samples) to the next rung and track their F2/F1 ratio. When it drifts, shrink the trust region. Optimizers concentrate exactly where a proxy errs, so random-layout calibration is biased. Test: CMA-ES on area, MS and MS2 with and without the audit; measure true-nH regret.

**SIM10. Value-of-information escalation.** — *combo, S.* Escalate an object only when:
- |budget − value| < z·σ, with z from the criticality field; or
- its interval overlaps the leader's among the top-k and the choice matters downstream.

In the hot-loop data MS2 misses only 2–4% of choices, at a median cost of 1–5% [C], so escalation is rare. Test: same final quality as "always F2" with far fewer calls, on 30 boards.

**SIM11. Cross-solver disagreement as a model-error alarm.** — *new, S.* Run two independent F2 methods on critical objects: image PEEC and a meshed-plane solve, or PEEC and FV. Disagreement beyond their calibrated errors triggers F3. Calibration σ cannot catch modelling mistakes such as a missed plane void or a wrong port; disagreement can. Test: detection rate on seeded modelling faults.

**SIM12. Coupon panel per stackup (F4).** — *new, M.* A standard test panel per stackup and fab, measured by VNA/TDR, thermal camera and near-field probe:
- hot-loop ladders of known geometry;
- decap mounts with 1–4 vias;
- via transitions;
- slots across references;
- thermal pads with via arrays.

Residuals train per-stackup bias models stored in the ledger with provenance. Test: does the bias fitted on lot A predict lot B within σ?

**SIM13. Vendor data with mounting de-embedding.** — *combo, M.* Vendor capacitor and inductor S-parameters are measured in a fixture. De-embed the fixture, re-embed our own pad + via + plane mounting from F2, and get the in-situ ESL. Then vector-fit and cache the result per part number. "An 0402 has ESL X" is a fixture statement, not a board statement. Test: in-situ predictions against coupon VNA for 5 parts.

**SIM14. Calibrate on the optimizer's own distribution.** — *sharp, M.* Weight calibration samples by the density ratio between optimizer-visited and random layouts (covariate-shift correction), so σ is right where it is used. Test: calibration error on optimizer outputs with and without weighting.

## C. Fast physics kernels (F1/F2)

**SIM15. MS2 as the default loop-inductance spend model.** — *sharp, S.* MS2 = Σ length·L′(w,h) (air Hammerstad Z0/c) minus coupled-line mutual terms −2·overlap·(µ0/4π)·ln(1+(2h/s)²). It costs µs and has Spearman 0.999 against multi-filament PEEC with a stable bias (+7.7% against a graded-filament reference) that one scalar per stackup removes [C, rt_loop_proxy]. It replaces both "minimize loop area" (Spearman 0.36 over a plane) and µ0·h·l/w (+50…+1000% bias). Test: N7 micro-placer designs optimized with MS2 vs with area, scored by PEEC.

**SIM16. Image-plane multi-filament PEEC as the F2 default.** — *sharp, S.* N filaments across each width, the high-frequency current split solved, and a PEC image for the plane. It costs 0.25–1.7 ms per loop and agrees with FastHenry on a meshed plane within 1.3% (4 loops, w/h 0.3–5, 100 MHz; FastHenry: 7–115 s) [C]. With 7 equal filaments it reads 11–65% low for w/h ≥ 10; use ≥ 31 graded filaments. Escalate to meshed-plane solves only where RET-COV finds voids within ~3h. Test: 30 extracted hot loops, some with voids, against meshed-plane references.

**SIM17. Hybrid image + local plane mesh.** — *new, M.* Keep the image for intact plane areas and mesh only the plane cells within a few h of voids, slots and antipad rows. Cost then scales with the defect, not the board. Test: accuracy against full meshed planes on slot crossings; cost against FastHenry's 56–115 s per case.

**SIM18. Cross-section table service.** — *combo, S.* Solve each unique cross-section once with a 2-D FD/BEM (0.2–1.5 s) and cache its RLGC:
- stackup;
- layer;
- width and gap;
- neighbours;
- solder mask;
- etch profile.

Routers price per mm from the table; Hammerstad-Jensen (1–2.5 µs, within 0.7%) covers plain microstrip inside its range [C]. Test: cache hit rate across 50 boards; error against per-instance solves.

**SIM19. Plane-pair modal basis for real fills.** — *combo, M.* Compute the first N eigenmodes of each plane pair's 2-D Helmholtz problem once, on the fill raster. Port impedances for any IC or decap position are then modal sums (2–300 ms per sweep, like the rectangle cavity model [C]), and moving a decap only re-weights terms. This extends the cavity model from rectangles to real, perforated fills. Test: against a 2.5-D solve and Palace eigenmodes on 5 boards.

**SIM20. Differentiable F1/F2 in JAX.** — *combo, M.* Implement MS2, the PEEC solve and the FV sheet solve with implicit differentiation, so placers get ∂nH/∂x, ∂mV/∂x and ∂°C/∂x at the cost of one adjoint solve per objective. Test: gradient check against finite differences; N7 cell quality with gradients vs without.

**SIM21. Via-constant audit.** — *sharp, S.* Johnson's 5.08h[ln(4h/d)+1] gives 2–6× the Rosa/Goldfarb-Pucel partial inductance [C], and it is used in our loop estimator ([checkers-power](../../topics/rules/checkers-power.md)). Replace it with loop models that include the return via or plane, because a lone via's partial L is not a loop quantity. Test: PEEC of via pairs and via-to-plane loops against each formula on 20 geometries.

## D. Incremental extraction and caching

**SIM22. Canonical-geometry memoization.** — *sharp, S.* Normalize each object (translate, rotate, mirror, sort terminals) and hash it with the stackup id and band. Results are then reused across candidates, revisions and boards; hot loops, decap mounts and launches repeat heavily. Test: cache hit rate during a placement run and across a 50-board corpus.

**SIM23. Dirty-region invalidation from IPC commits.** — *sharp, S.* Each commit lists the changed items. Invalidate pairwise interactions within a cutoff (~10h over planes, where mutual inductance falls as (2h/D)²) and recompute only the budgets that touch them. Test: agreement and speedup of incremental vs full recompute over a 1,000-edit session.

**SIM24. Adjoint price maps for copper edits.** — *combo, S.* One adjoint solve per objective gives the first-order cost of adding or removing copper anywhere: IR loss, plane inductance, thermal resistance. Render it as a map for the router, the placer and the LLM. It was within ~15% for compact holes (0.268 vs 0.303 mW) [C]; cuts need the edit's polarization tensor and finite edits exact Woodbury updates ([solver-ladder](../../topics/physics/solver-ladder.md)). Test: rank 100 random edits by price vs exact re-solve.

**SIM25. Stream-function (Δψ) screen for cuts.** — *new, S.* A line of removed copper across the current is a topological change. First-order adjoint underestimated a 6 mm slot 30× (0.27 vs 8.06 mW) [C]. The current crossing the proposed cut, Δψ along it, predicts the harm instead ([xd_sheet.py](../../../tools/research/physics/xd_sheet.py)). Run it before accepting slots, splits and antipad rows. Test: Δψ against exact ΔR for 100 slots.

**SIM26. Schur-complement window macro-models.** — *combo, M.* Condense everything outside an edit window onto the window boundary once. Each later edit then solves only the window plus a dense boundary block. For 2-D sheets plain refactoring is already fast (0.6–1.5 s at 10⁵ cells; a stale-LU-preconditioned CG was ~5× slower in scipy [C]). The payoff is in micro-placers making thousands of moves in one window, and in 3-D. Test: speedup for 1,000 moves in a 5×5 mm window of a 4-layer PDN model.

**SIM27. Mesh as a fidelity knob, with continuation.** — *combo, S.* Optimize on coarse grids first (5 cells/h: 20–64 ms, about −2% Z0 [C]) and refine as candidates converge. Report discretization error by Richardson extrapolation from two grids. Test: final quality vs fine-grid-only at 10× less compute.

## E. Full-wave (F3) workflow

**SIM28. Physics component library.** — *new, M.* Solve canonical 3-D structures once at F3 over parameter sweeps and store them as parameterized surrogates or S-parameter tables with provenance:
- via transitions per stackup;
- connector launches;
- decap mounts;
- BGA breakouts;
- test-point stubs.

F3 cost moves from per-board to per-stackup. Test: library prediction against a fresh F3 slice for 20 instances.

**SIM29. Slice-and-stitch with overlap verification.** — *combo, M.* Cut F3 slices with overlapping boundaries (si-wrapper style) and cascade their S-parameters in scikit-rf. Comparing the overlap as computed in both slices estimates the slicing error. Test: stitched vs single-domain F3 on 5 nets.

**SIM30. Batched small-domain FDTD on GPU.** — *new, M.* Pack hundreds of small candidate geometries (via and launch variants) into one batched kernel instead of one big domain: JAX vmap/fdtdx now, the openEMS GPU engine later. GPUs favour many independent small domains, and design sweeps are exactly that. Test: candidates per GPU-hour vs sequential openEMS.

**SIM31. Early stopping on decision confidence.** — *new, S.* Stop an FDTD run once the uncertainty of the S-parameter estimate, from energy decay or harmonic-inversion extrapolation, can no longer change the pass/fail verdict against the budget. Much F3 time goes on late-time ringing that does not move the verdict [I]. Test: decision agreement with full-length runs; time saved.

**SIM32. Multi-fidelity Bayesian optimization for 3-D transitions.** — *combo, M.* Co-kriging over F1/F2/F3 for parametric structures (antipad radius, launch pad, stitching-via positions), with an acquisition function that weighs information per CPU-second. Test: F3 calls needed to reach a target return loss vs F3-only BO.

**SIM33. Passive macromodels for SPICE.** — *combo, M.* Turn F2 extractions (PEEC networks, plane pairs) into small passive subcircuits with PRIMA/Loewner or vector fitting plus passivity enforcement, cached per block for C2 transient runs. Our test [C]:
- a damped PDN fit passively with 6–9 complex pole pairs in 2–7 s (rms 2×10⁻³ to 1×10⁻⁴);
- an undamped cavity did not, and enforcement failed.

So order selection and passivity must be gates, not afterthoughts. Test: passivity rate and transient error against the full network.

## F. Surrogates and learning

**SIM34. Residual surrogates on physics baselines.** — *sharp, S.* Learn log(F2/F1) instead of F2. With 300 PEEC labels, the residual on MS2 reached median 3.5% (p95 9.8%) against 28% (p95 100%) for the same model on raw features [C]. Physics supplies the scaling law; the learner only fixes the bias. Test: data-efficiency curves for loop L, crosstalk and mounting L.

**SIM35. Label factories with coverage audits.** — *combo, M.* Procedural generators for hot loops, decap mounts, coupled sections and plane fills, labelled by F2. PEEC at ~1 ms gives ~3.6M labels per core-hour [C]. Coverage is measured against feature distributions from the open-board corpus, so the surrogate's domain matches real boards. Test: out-of-domain rate of real-board objects against the training hull.

**SIM36. Active learning at decision boundaries.** — *combo, M.* Spend F3 labels where surrogate σ × |∂decision/∂value| is largest (near budgets and near ties), not uniformly. Test: labels needed to reach a target decision accuracy vs random sampling.

**SIM37. Graph surrogate on the physics graph.** — *combo, L.* A GNN over physics-IR entities (segments, vias, pads, plane patches) predicts per-net loop L, coupling and IR drop. It is the post-layout counterpart of ParaGraph (pre-layout, R² 0.772 [S]). Test: accuracy against F2 on held-out boards; latency per board.

**SIM38. Neural operator for board-scale fields.** — *combo, L.* An FNO or U-Net maps layer rasters (copper, sources, sinks, h-map) to IR-drop, temperature and plane-voltage fields in ms on a GPU, trained on F2 solves. Use it only inside its trust region, with F2 spot checks. Test: field error and decision accuracy against F2 on 100 boards.

## G. Spending compute

**SIM39. Candidate-batched evaluation by default.** — *sharp, S.* Evaluate populations, not single moves. Vectorized PEEC1 evaluates 20,000 loops at 0.3–0.8 µs each on one core [C], and a GPU should reach 10⁶–10⁸ F1/S calls per second [I]. Population optimizers (CMA-ES, quality-diversity, beam search) then explore far more widely than one annealing trajectory. Test: quality vs wall-clock, population vs sequential search, on N7 cells.

**SIM40. A compute market priced by expected value.** — *combo, M.* Each critic bids for F2/F3 time with (expected decision change × consequence) / cost, and a scheduler allocates the board's compute budget. This extends the N1 resource market and the I5 criticality field. Test: escaped physics failures per CPU-hour vs uniform allocation.

**SIM41. Speculative pre-evaluation.** — *new, S.* While the LLM deliberates or a human reviews, run F2/F3 on the likely next candidates (top proposals, Pareto neighbours) so verdicts are ready when asked for. Idle compute becomes lower latency. Test: median wait for verdicts in agent sessions.

**SIM42. Tolerance sweeps on the cheap rungs.** — *combo, S.* Monte Carlo over fab tolerances (εr, h, etch, plating, mask) and part spreads with F1/S. Only the worst corners go to F2/F3. Designs then pass physics with margin, not just at nominal. Test: worst cases found vs running F2 everywhere.

**SIM47. GPU-resident multigrid sheet solver.** — *new, M.* Keep the board's layer rasters on the GPU and solve IR-drop, thermal and plane-spreading problems with geometric multigrid, warm-started from the previous candidate. SuperLU on one core needs 6–9 s at 4.4×10⁵ cells [C]; a GPU multigrid V-cycle at that size should take milliseconds [I], which moves whole-board F2 into the placer's outer loop. Test: time and agreement against SuperLU on 20 pours and 2-layer thermal cases.

## H. Interfaces and benchmarks

**SIM43. Open physics-evaluator benchmark.** — *new, M.* A public set of canonical PCB structures with FastHenry-class, F3 and measured ground truth. It scores evaluators on accuracy, decision quality (SIM7) and cost, as the pattern libraries behind CNN-Cap do in IC extraction. Nothing comparable exists for PCBs [I]. Test: reproducibility of rankings across tools and machines.

**SIM44. The LLM sees sensitivities, not fields.** — *sharp, S.* The LLM receives ledger deltas and the top-k sensitivities (∂budget/∂object, with units) from adjoint solves or finite differences. It asks "what if" by naming objects and never reads raw fields, which keeps it in intent space while staying grounded in physics. Test: quality of LLM-proposed edits with and without sensitivity tables.

**SIM45. Fidelity as a priced agent action.** — *new, M.* An LLM or RL agent chooses when to call F2/F3 and pays the compute cost in its reward, so it learns escalation policies instead of using fixed thresholds. Test: cost and escaped failures against the SIM10 rule.
