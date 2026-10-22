# Physics-first ideas: variational principles and energy (VP)

Round-2 lens VP. Nature minimizes energy inside the copper we draw. That gives four things these ideas exploit:
- floors that are provable;
- two-sided bounds;
- gradients that cost nothing for self-energy objectives;
- monotonicity laws, with a known scope.

The argument, derivations and numbers are in [lens-vp](../../topics/physics/lens-vp.md). It defines the principles cited below:

| Principle | Short name |
|---|---|
| V1, V2 | Thomson / Dirichlet (DC) |
| V3 | Maxwell minimum magnetic energy |
| V4 | stationary reaction; eddy spectrum |
| V5 | electrostatic bounds |
| V6 | Rayleigh quotient, domain monotonicity |
| V7 | Tellegen |
| V8 | Poynting |
| V9 | least action, Rayleigh dissipation |
| V10 | composite (Voigt, Hashin–Shtrikman) and capacity bounds |
| BL | bilevel classes: A (self-energy copper lowers), A′ (self-energy copper raises), B (interaction), C (non-variational) |

Scripts:
- [vp_floors.py](../../../tools/research/physics/vp_floors.py)
- [vp_rl_band.py](../../../tools/research/physics/vp_rl_band.py)
- [vp_edit_pricing.py](../../../tools/research/physics/vp_edit_pricing.py)

These ideas build on round-1 ideas without repeating them:
- [optimization](optimization.md): OP2, OP6, OP27, OP43, OP57;
- [joint-place-route](joint-place-route.md): JPR30;
- [reasoning](reasoning.md): DR17, DR18, DR41;
- [power](power.md): PW2, PW29, PW32;
- [si-emi-rf](si-emi-rf.md): FE26, FE27;
- [cross-domain](cross-domain.md): XD84, XD108.

Edit pricing by polarization tensors is not repeated here. It is in CT1/CT2 ([lens-ct](lens-ct.md)) and SY6/SY7/SY9 ([lens-sy](lens-sy.md)), and lens VP confirms it.

**Round-3 corrections (2026-10-22):** floors are certified on the 0.1 mm raster only; a refinement study is needed for real layouts. ([red-team](../../topics/physics/red-team.md))

Tags: *new*, *combo*, *sharp* as in the [catalog](README.md). Effort: S (days), M (weeks), L (months).

## A. Floors and certificates

**VP1. Beckmann floor oracle for every power net.** For any copper of area A, R ≥ R_s·(Σ_k I_k·d_k)²/(A·I²), with d_k the geodesic distance from source to load k. It comes from Cauchy–Schwarz on Thomson's functional and holds for any shape, not only trees. Its cost is microseconds per net.
- **Principle:** V1.
- **Beats:** DR18's floors need a micro-solver run per structure, and JPR30's bounds are geometric proxies. This one is a closed form, provably below every realized layout, and differentiable in pad positions. It was 1.527 mΩ against 1.761 (convex floor) and 1.789 (SIMP design) [C].
- **Test:** check that the floor stays below the realized R on 200 synthesized and human pours. Then compare τ-ordering computed from it with expert criticality.

*sharp (OP6, L2), S*

**VP2. Convex-relaxation floor with a dual certificate.** Solve the variable-thickness relaxation (SIMP with p = 1, no filter), which is convex. Bound it from below with the Lagrangian dual: for any trial potential v, R ≥ (fᵀv)²/(I²·max_ρ vᵀK(ρ)v), where the max is a fractional knapsack. The result is an interval that contains the best possible layout of that area.
- **Principle:** V1, V2, BL-A.
- **Beats:** round 1 could not say how far a pour was from optimal. Here the gap is 4×10⁻⁴ after 400 solves; SIMP sits 1.6% above the floor and the human tree 18.8% [C].
- **Test:** run on 20 board pours. Every manufacturable design must lie above the floor. Report the gap distribution.

*new, S*

**VP3. Avoidable-loss report.** For every pour or trace tree, report (R − R_floor)/R alongside the copper's area elasticity −dlnR/dlnA. The elasticity is exactly 1 at the Beckmann floor; lower values show copper that spreading, not transport, limits.
- **Principle:** V1.
- **Beats:** "should we reshape this copper?" is answered today by taste. The human tree in round 1's test had 15.8% avoidable loss on the 0.1 mm raster (the floor moved 2–13% between grids), and round 1's synthesis recovered 14.5 of those 15.8 points [C]. Below a few percent, reshaping is not worth the review cost.
- **Test:** compute it on high-current nets of 30 open boards. Check whether the boards with the largest avoidable loss are the ones designers later reworked (git history).

*new, S*

**VP4. Convex-first continuation for every compliance objective.** Start topology optimization from the convex p = 1 optimum, then ramp p from 1 to 3 and sharpen the projection. This applies to loss, pour inductance over a mapped h_eff, thermal compliance, and weighted sums of them.
- **Principle:** V1, V3, BL-A.
- **Beats:** round 1's uniform start found a local optimum for inductance-only pours over a slotted reference. The convex start reached 0.546 instead of 0.613 nH, and 2.02 instead of 2.40 mΩ, at areas within 1.2% [C]. It replaces multi-start for class-A terms.
- **Test:** run 20 multi-objective pour problems. Compare final objective and CPU against cold multi-start.

*sharp (OP43, OP2), S*

**VP5. Multi-net floor and area budget by transport work.** For nets sharing a layer, P_total ≥ R_s·(Σ_n W1,n)²/A_total, where W1,n = Σ I·d for net n. The loss-optimal area share goes to each net in proportion to W1,n, before any routing.
- **Principle:** V1.
- **Beats:** OP6 derived the split for trees. This makes it a floor for any shapes and gives a pre-routing area budget per rail with a certificate.
- **Test:** compare with joint multi-rail topology optimization (OP4) on 10 shared layers. Check that the budget split stays within 10% of the optimum's.

*sharp (OP6), S*

**VP6. Transport-work placement term for power nets.** Add Σ_n R_s·W1,n²/A_n to the analytical placer. W1,n is the current-weighted geodesic star distance between a net's source and load pads. Its gradient on load pad k is 2·(P_floor/W1)·I_k along the unit vector away from the source.
- **Principle:** V1, envelope theorem.
- **Beats:** HPWL treats a 10 A feed and a 1 mA feed alike. Pour forces (OP27) need a sheet solve. This is closed-form, admissible and differentiable.
- **Test:** on 10 power-heavy boards, compare post-route loss and worst IR drop against HPWL placement at equal CPU.

*new, S–M*

**VP7. Certified primal–dual evaluators.** Every class-A sheet evaluation runs two solves on the same mesh: the potential (or temperature) problem and its dual (stream function, or equilibrated flux). It returns [lower, upper] instead of a value ± σ.
- **Principle:** V1, V2 (Prager–Synge).
- **Beats:** SIM1's σ is statistical and can be wrong. This one cannot. At 4 cells per width a corner is bracketed at 0.530–0.581 squares, exact 0.5587 [C]. Near-tie decisions are settled whenever brackets separate, without escalating (SIM10).
- **Test:** check coverage on 100 structures against fine solves (100% by construction). Measure cost relative to one solve, and the fraction of optimizer comparisons settled by brackets alone.

*new, M*

**VP8. Bracketed C and L extraction.**
- **Mechanism:** pair two solvers per quantity.
  - Capacitance: Galerkin charge-based MoM gives a lower bound (V5, Thomson form); potential FEM gives an upper bound.
  - High-frequency loop inductance: current-based PEEC with restricted current gives an upper bound (V3); a divergence-free trial B gives a lower bound.
  - Report the bracket as the extraction's own error.
- **Principle:** V3, V5.
- **Beats:** round 1's [C] numbers carry no error bars and disagree between workstreams (22 vs 26 pF). Brackets say which is right, or that both are within error.
- **Test:** on 20 structures, check that brackets contain FasterCap and openEMS results, and plot bracket width against mesh density.

*new, M*

**VP9. Infeasibility certificates from floors.** If a certified floor exceeds the budget (τ < 1), the budget is provably infeasible with these terminals, this stackup and this area. Return the floor's binding term: the distance, the area, h, or the via-set capacity.
- **Principle:** V1–V6, V10.
- **Beats:** DR41 asks for physics-unit infeasibility certificates but has no way to prove one. Floors are proofs.
- **Test:** on 20 deliberately infeasible budget sets, certificates must be issued without optimizing, with zero false certificates on 20 feasible sets.

*sharp (DR41), S*

**VP10. Floor-gated stop rule.** Stop refining a class-A term when (current − floor)/floor falls below the budget slack or the model error, whichever is larger.
- **Principle:** V1, V2.
- **Beats:** OP57's marginal-improvement rule cannot tell a plateau from the optimum. A floor can.
- **Test:** measure wall-clock to a budget-feasible design and wasted iterations, against OP57 and fixed iteration counts.

*sharp (OP57), S*

## B. Vias, perforation and cavities

**VP11. Capacity model and hull floor for via sets.**
- **Mechanism:**
  - Spreading inductance into a plane pair is (μ0·d/2π)·ln(R/cap), with closed forms for one, two and ring-arranged vias, a charge simulation otherwise, and cap ≤ cap(convex hull).
  - N8 then maximizes the capacity of the via set inside the footprint.
  - Vias inside the hull are flagged as low-value.
- **Principle:** V10.
- **Beats:** counting vias. The formula reproduces round 1's grid solves within 2%. The hull floor shows that 4 vias at 2 mm need at least 40.1 pH against 44 realized [C].
- **Test:** compare with PEEC on 50 decap via patterns. Then compare N8 decisions with and without the capacity objective.

*sharp (PW32, N8), S*

**VP12. Hexagonal (staggered) via fields.** Thermal, stitching and power via arrays (not BGA fields) should use a hexagonal lattice. At equal via density and antipad size it keeps the plane within 5% of the Hashin–Shtrikman floor up to D/p_s = 0.95. A square lattice is 15% above it at D/p_s = 0.9 and 40% above at 0.95 [C]. The larger nearest-neighbour spacing also helps drill-to-drill and CAF rules.
- **Principle:** V10.
- **Beats:** grids are chosen by CAD convenience.
- **Test:** unit-cell and board-level solves, plus fab DRC, on 10 thermal pads and power transitions.

*new, S*

**VP13. Perforation floor critic.** For every perforated plane region, report the realized sheet-R multiplier against two floors: 1/(1−f) for any pattern, and (1+f)/(1−f) for isotropic patterns. Regions at the floor can only improve with fewer or smaller antipads. Regions above it are arrangement-limited: stagger them, or merge antipads along the flow.
- **Principle:** V10.
- **Beats:** PW12 finds necks but cannot say whether rearranging would help.
- **Test:** on 10 BGA and connector fields, compare the predicted rearrangement gain with re-solved fields.

*new, S*

**VP14. Two-sided cavity-mode bracket for stitching.**
- **Mechanism:** bound the first mode from both sides.
  - The upper bound is the largest empty circle, a domain-monotonicity bound: f1 ≤ 0.766·c/(D·√εr), with D measured to via edges and open board edges mirrored.
  - The lower estimate is the homogenized via-lattice capacity (wire-medium form). It is not rigorous; round 1 found it within 3–16% of the eigen-solve on grids.
  - Decide stitching without the eigen-solve when the bracket clears the protected band. The upper bound alone can prove a pattern insufficient.
- **Principle:** V6, V10.
- **Beats:** round 1 used the empty circle as a ±30% estimate. It is a one-sided bound: round 1's κ of 0.32–0.64 is always below 0.766.
- **Test:** check bracket containment on round 1's 11 patterns plus 50 random ones, and count the decisions settled.

*sharp (FE26, FE27), S*

## C. Dynamics, spectra and damping

**VP15. Tuned magnetically coupled damping layer.** Put a resistive film, or a copper ring closed through a resistor, between the hot loop and its plane. Choose its sheet resistance so its eddy mode relaxes at the ring frequency, R_s ≈ ω_r·μ0·ℓ_eff/2 (ring: R ≈ ω_r·L_ring). The optimizer treats the layer as a stackup variable.
- **Principle:** V4, V9: loss peaks where a coupled mode's relaxation rate equals ω. The limit is Q ≥ 2/k² − 1.
- **Beats:** copper alone gives Q 30–170 (round 1; lens TH proves Q = h/δ). In 2-D, a film at about 0.1 Ω/sq gave Q_film ≈ 7.6 at 200 MHz [C]. L′ was 0.106 nH/mm with the film, between 0.124 without it and 0.070 with a solid plane at the film's depth. Prior art: Hartmann, Müsing and Kolar (2009) [S]. It complements TH3's tuned snubber.
- **Test:** 3-D PEEC or openEMS of a GaN half-bridge loop with and without the layer, then double-pulse ringing and near-field on a coupon.

*combo, M*

**VP16. Eddy-mode Foster macromodels for plane returns.**
- **Mechanism:** solve the generalized eigenproblem R·v = λ·L·v on the plane's zero-net-current subspace. Each mode becomes one RL section of a passive Foster ladder. Keep modes by their share c_k² of the inductance drop, about 3 per decade.
- **Principle:** V4.
- **Beats:** vector fitting needs passivity enforcement (round 1 saw it fail). This is passive by construction and reproduced the direct solve exactly [C]. It is the fast solver research-gaps gap 2 asked for, aimed at kHz-band precision analog.
- **Test:** compare with full PEEC from 10 Hz to 10 MHz on 5 layouts, plus SPICE runtime and passivity checks.

*combo (SIM33), M*

**VP17. Containment-distance regime predicate.** For each aggressor return and victim at distance D, the return can pass under the victim only below f ≈ R_s/(2π·μ0·D): 12 kHz at 5 mm on 1 oz. Use this per-pair predicate, not one f_x per stackup, to gate star-ground, separation and split rules.
- **Principle:** V3, V4.
- **Beats:** f_x = R_s/(2π·μ0·h) answers a different question (D5 in [lens-vp](../../topics/physics/lens-vp.md)). Containment obeyed f50·ℓ = 56–70 Hz·m for h = 0.1–1.6 mm [C]. This complements SY25's ℓ_d map.
- **Test:** check the predicate against 2-D and 3-D PEEC containment on 30 aggressor–victim pairs, and its rule-gating accuracy against expert verdicts.

*sharp (RG19, SY25), S*

**VP18. Hidden-mode inventory (the adiabatic-elimination test).** List every hidden coordinate the layout adds to the circuit's Lagrangian: eddy relaxation rates, cavity eigenfrequencies, common-mode and ground-loop resonances, and ring modes. Give each its rate or frequency, Q and participation. The layout is visible exactly where a mode lies inside the circuit's band with Q above budget.
- **Principle:** V4, V6, V9.
- **Beats:** these appear today as separate critics, with no single test for invisibility.
- **Test:** on 5 boards with known SI, EMI or analog faults, check whether the inventory lists the culprit mode first or second.

*new, M*

**VP19. Equipartition diagnostic for power copper.** For each switching piece, report W_m/W_e = (½LI²)/(½CV²) at its own I and V, and the energy floor V·I·l/v. A ratio far above 1 means too narrow; far below 1, too wide. Z0 = V/I is matched. The floor shows whether the copper or the parts dominate: 0.8 mW for 2 mm in a 12 V, 10 A, 500 kHz buck [C].
- **Principle:** V3, V5, V8.
- **Beats:** PW2 gives the width. This gives a one-number diagnosis of any existing copper and the irreducible floor.
- **Test:** on 20 vendor EVMs, compare the SW-copper ratios with designers' choices and with EMI results.

*sharp (PW2), S*

## D. Bilevel structure, gradients and monotonicity

**VP20. A/A′/B/C tagging of every objective term.**
- **Mechanism:** tag each optimizer term by class.
  - **A (self-energy that copper lowers: R, L, thermal resistance, 1/C):** convex when relaxed, free gradient, monotone.
  - **A′ (self-energy that copper raises, e.g. a dv/dt node's C):** monotone and free gradient, but concave when relaxed; its floor is the mandatory copper alone.
  - **B (interaction or misaligned):** one adjoint, non-convex.
  - **C (non-variational):** worst-frequency sensitivity.
  - Schedule: optimize A jointly and convexly first, then continue into B, and treat C at its binding frequencies.
- **Principle:** BL.
- **Beats:** round 1 mixes all terms from the start (or by an ad hoc continuation, OP43), and so meets local optima that class A does not have.
- **Test:** joint runs with and without the schedule, comparing final budget spend, runtime and local-optimum rate on 10 boards.

*new, S*

**VP21. Maxwell-stress placement forces for all self-energy terms.** By the envelope theorem, the gradient of a class-A energy with respect to a pad or part pose is a boundary integral of energy density at fixed fields. That holds for conduction, magnetic, electric and thermal terms. One solve per band therefore gives forces on every part at once.
- **Principle:** V1, V3, V5.
- **Beats:** OP27 covers DC loss only. Class-B terms need adjoints; class-A terms never do.
- **Test:** compare forces with finite-difference re-solves on 50 pad moves, then placement quality on power-heavy boards.

*sharp (OP27), M*

**VP22. Transfer-term (Braess) guard for copper additions.** Before any fill, bridge or stitch is accepted, compute the sign of its effect on each protected transfer resistance or coupling with Tellegen's product −ΔV_k^a·ΔV_k^v over the new copper. Block additions that raise a protected term even when they lower loss.
- **Principle:** V7, D7 of [lens-vp](../../topics/physics/lens-vp.md).
- **Beats:** "more copper is always better" holds for self terms only. A bridge that cut loss 1% raised a load's drop 1–3% [C]. CD24 makes the same point for couplings.
- **Test:** on 100 fill edits on mixed-signal boards, compare the predicted sign with exact re-solves.

*combo (CD24, XD122), S*

**VP23. Self and interaction rows in the ledger.** Self rows carry energies that add: watts, joules per event, energy to be absorbed. Interaction rows carry bilinear energies in the victim's own units. The ledger refuses to add nH across loops that carry different currents.
- **Principle:** V7, V8.
- **Beats:** the "nH in watts" and three-commodity-market framings (PW30, S10) treat everything as one currency. That is right for self terms and wrong for victims and EMI masks.
- **Test:** two-auditor review of 10 ledgers before and after, plus automated unit and consistency checks.

*sharp (PW30, I1), S*

**VP24. Monotone-convergence regression tests for solvers.** Free invariants for every solver change:
- coarse PEEC L∞ ≥ fine;
- potential FEM R ≤ true ≤ stream-function FEM R;
- MoM C ≤ true;
- in RL extraction, L(f) non-increasing and R(f) non-decreasing;
- added copper never raises R or L∞.

They catch sign, assembly and units bugs.
- **Principle:** V1–V5.
- **Beats:** SIM6 golden tests need references. These need none. They complement SY4 (reciprocity) and CD5 (Foster sums).
- **Test:** inject 20 known bugs into the PEEC and sheet core and measure the detection rate.

*new, S*

**VP25. Sign-aware proxies as admissible bounds.**
- **Mechanism:** classify each proxy.
  - A trial-field evaluation of the true functional is one-sided. Examples: uniform-current PEEC ≥ L∞, ε·A/h ≤ C, Beckmann ≤ R.
  - Any other approximation has two-sided error.
  - Use one-sided proxies directly as A*-admissible bounds for move pruning.
- **Principle:** V1–V5.
- **Beats:** JPR30 needs bounds that never exceed the realized value and has only geometric ones.
- **Test:** on logged joint runs, measure the false-prune rate (should be 0) and the pruned fraction.

*sharp (JPR30), S*

## E. Conductor energy and Poynting

**VP26. Energy columns for the conductor passport.** For each piece and band, add six columns to CD1's passport:
- guided Poynting flux along its gap;
- partial magnetic energy ½·I_k·(L_p·I)_k;
- partial electric energy ½·q_k·φ_k;
- I²R;
- share of the cell's radiating moment;
- participation in each ringing mode.

Add one more column: the energy density at its boundary, which is its sensitivity. The dominant column names the piece's energetic job.
- **Principle:** V7, V8, V9.
- **Beats:** CD1 records current and charge shares. Energy shares add across mechanisms, which shares of current do not.
- **Test:** explanation quality and reviewer agreement on 10 boards, with and without the energy columns.

*combo (CD1), M*

**VP27. Energy-containment ratio per cell.** For each cell and band, compute the fraction of its E-field and H-field energy stored outside the cell's volume. One PEEC solve and one electrostatic solve give it.
- **Principle:** V8.
- **Beats:** loop area, moment-with-image and "capacitance to whom" are three proxies for one thing: energy that leaves the cell. This puts DR42's locality index in energy units.
- **Test:** correlation with radiated-emission proxies, with DR42 and with expert "looks right" ratings on 20 layouts.

*new, M*

**VP28. Poynting route map for power delivery.** Render S = E × H in each dielectric gap for each rail and band. The map shows where power actually flows from regulator to load, and where it leaks at edges, slots and splits. It is a review view of each rail's "duct".
- **Principle:** V8.
- **Beats:** return-current renderers (RG48, FE9) show current, not the power route. A split under a pour shows up as a blocked duct.
- **Test:** reviewer fault-finding on seeded slot and split faults, against return-current views.

*new, M*

## F. Thermal and robustness

**VP29. Thermal transport floor.** Heat conducted through copper of area A_cu (sheet conductance k·t) to a sink obeys Σ P_k·ΔT_k ≥ (Σ P_k·d_k)²/(k·t·A_cu). That is the Beckmann bound for heat, and convex relaxation tightens it. It says before layout whether a spreader of a given area can possibly meet a ΔT budget. It is valid when the spreader's heat leaves through the designated sink (sealed, vacuum or high-altitude boards, conduction to a cold plate). Where convection matters, add it as a distributed sink in the convex relaxation.
- **Principle:** V1 (thermal form).
- **Beats:** "15.3 cm²/W" and fin rules, which carry no proof of feasibility.
- **Test:** compare with finite-volume thermal solves for 10 parts on copper spreaders; check that the floor never exceeds the solved value.

*new, S*

**VP30. Two-corner etch robustness for self terms.**
- **Mechanism:** self quantities are monotone in copper (V1, V3, V5).
  - The eroded design gives the worst R and L∞ and the best C. The dilated design gives the reverse.
  - So two corners bound every etch outcome for class-A terms, with no Monte Carlo.
  - Transfer terms are not monotone and still need sampling.
- **Principle:** V1, V3, V5.
- **Beats:** TM35 and OP7 sample or optimize over three projections without knowing which terms are bounded by them.
- **Test:** compare the two-corner bounds with Monte Carlo etch on 20 structures. Coverage should be 100% for class-A terms; report the violation rate for class-B terms.

*sharp (OP7, TM35), S*

## Top five to build first

1. **VP2 + VP3:** floors and avoidable-loss reports on the existing sheet solver.
2. **VP4:** convex-first continuation, a few lines of change to OP2.
3. **VP20:** A/A′/B/C tagging in the joint optimizer.
4. **VP11 + VP14:** capacity and empty-circle brackets for vias and stitching.
5. **VP17 + VP16:** containment predicate and Foster eddy models.
